"""The five pipeline stages: gather -> process -> extract -> ground -> assemble.

Each function takes/returns plain data (pydantic models or dicts) so
pipeline/orchestrator.py can persist every stage's output to
data/intermediate/<project>/ for inspection, independent of how any one
stage is implemented.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime

from core.claude import Claude
from pipeline.chunking import Chunk, chunk_document, keyword_prefilter
from pipeline.prompting import call_structured, load_prompt, render_prompt
from schema.risk_model import (
    APPLICATION_OR_DEPLOYMENT_CATEGORIES,
    APPLICATION_OR_DEPLOYMENT_SURFACES,
    ChunkClassifications,
    Condition,
    CriticOutput,
    EvidenceSummary,
    Evidence,
    ExtractedRiskPaths,
    FinalRiskPath,
    OutputNormalization,
    RiskPath,
    Source,
    SourceTriageResult,
)
from sources.seed_urls import ProjectConfig
from tools import fetch, github, registry


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
    return slug or "item"


def _dedupe_ids(items: list, get_id, set_id) -> None:
    seen: dict[str, int] = {}
    for item in items:
        base = _slugify(get_id(item))
        count = seen.get(base, 0)
        seen[base] = count + 1
        set_id(item, base if count == 0 else f"{base}_{count}")


# ---------------------------------------------------------------------------
# Stage 1: gather
# ---------------------------------------------------------------------------


def stage1_gather(
    project_key: str,
    config: ProjectConfig,
    current_version: str,
    target_version: str,
    claude: Claude,
) -> tuple[list[Source], dict[str, str], dict | None]:
    """Returns (sources, raw_docs, registry_metadata).

    Seed URLs are trusted by construction (a human curated them - see
    sources/seed_urls.py) and skip triage entirely. GitHub releases/issues
    are *candidates* that must pass the triage.md LLM step before being
    trusted as sources, since they were discovered automatically rather
    than hand-picked.
    """
    display_name = config.get("display_name", project_key)
    now = datetime.now(UTC).isoformat()
    sources: list[Source] = []
    raw_docs: dict[str, str] = {}

    for i, seed in enumerate(config.get("seed_urls", [])):
        source_id = f"seed_{i:02d}"
        fetched = fetch.fetch_document(seed["url"])
        if fetched["error"] or not fetched["text"].strip():
            print(f"  [gather] WARN could not fetch seed {seed['url']}: {fetched['error']}")
            continue
        raw_docs[source_id] = fetched["text"]
        sources.append(
            Source(
                source_id=source_id,
                title=seed["title"],
                url=seed["url"],
                source_type=seed["source_type"],
                retrieved_at=now,
                why_relevant=(
                    f"Official {seed['source_type'].replace('_', ' ')} published by the "
                    f"{display_name} project; hand-curated as directly relevant to the "
                    f"{current_version} -> {target_version} upgrade."
                ),
            )
        )

    github_repo = config.get("github_repo")
    candidates: list[dict] = []
    idx = 0
    if github_repo:
        for release in github.list_releases(github_repo, per_page=8):
            if not release["body"].strip():
                continue
            cid = f"ghrel_{idx:02d}"
            idx += 1
            candidates.append(
                {
                    "source_id": cid,
                    "kind": "github_release",
                    "title": release["name"] or release["tag_name"],
                    "url": release["url"],
                    "snippet": release["body"][:1500],
                }
            )
            raw_docs[cid] = release["body"]

        search_terms = config.get("github_search_terms", [])
        for issue in github.search_issues(github_repo, search_terms, per_page=8) if search_terms else []:
            if not issue["body"].strip():
                continue
            cid = f"ghiss_{idx:02d}"
            idx += 1
            candidates.append(
                {
                    "source_id": cid,
                    "kind": "github_issue_or_pr",
                    "title": issue["title"],
                    "url": issue["url"],
                    "snippet": issue["body"][:1500],
                }
            )
            raw_docs[cid] = issue["body"]

    if candidates:
        prompt = render_prompt(
            load_prompt("triage.md"),
            project=display_name,
            current_version=current_version,
            target_version=target_version,
            candidates_json=candidates,
        )
        triage_result = call_structured(
            claude,
            prompt=prompt,
            output_model=SourceTriageResult,
            tool_name="record_triage_decisions",
            tool_description="Record keep/discard decisions for candidate sources.",
        )
        decisions = {d.source_id: d for d in triage_result.decisions}
        for candidate in candidates:
            decision = decisions.get(candidate["source_id"])
            if decision and decision.keep:
                sources.append(
                    Source(
                        source_id=candidate["source_id"],
                        title=candidate["title"],
                        url=candidate["url"],
                        source_type=decision.source_type,
                        retrieved_at=now,
                        why_relevant=decision.why_relevant,
                    )
                )
            else:
                raw_docs.pop(candidate["source_id"], None)

    registry_metadata = None
    if config.get("registry"):
        registry_type, package = config["registry"]
        registry_metadata = (
            registry.pypi_metadata(package, target_version)
            if registry_type == "pypi"
            else registry.npm_metadata(package, target_version)
        )
        if registry_metadata:
            cid = "registry_meta"
            raw_docs[cid] = json.dumps(registry_metadata, indent=2)
            sources.append(
                Source(
                    source_id=cid,
                    title=f"{registry_type} registry metadata for {package}",
                    url=(
                        f"https://pypi.org/project/{package}/"
                        if registry_type == "pypi"
                        else f"https://www.npmjs.com/package/{package}"
                    ),
                    source_type="package_registry_metadata",
                    retrieved_at=now,
                    why_relevant=(
                        f"Registry metadata for the {target_version} release of {package}, "
                        "used to corroborate runtime/dependency-requirement conditions."
                    ),
                )
            )

    return sources, raw_docs, registry_metadata


# ---------------------------------------------------------------------------
# Stage 2: process
# ---------------------------------------------------------------------------


def _dedupe_chunks(chunks: list[Chunk]) -> list[Chunk]:
    seen_hashes: set[str] = set()
    kept: list[Chunk] = []
    for chunk in chunks:
        normalized = re.sub(r"\W+", "", chunk.text.lower())[:400]
        fingerprint = hashlib.sha1(normalized.encode()).hexdigest()
        if fingerprint in seen_hashes:
            continue
        seen_hashes.add(fingerprint)
        kept.append(chunk)
    return kept


def stage2_process(
    sources: list[Source],
    raw_docs: dict[str, str],
    project: str,
    current_version: str,
    target_version: str,
    claude: Claude,
    batch_size: int = 25,
) -> list[dict]:
    """Chunk every source, dedupe, keyword-prefilter, then classify the
    survivors with an LLM pass. Returns full-text candidate-risk chunks
    ready for extraction, each annotated with its source's type.
    """
    source_type_by_id = {s.source_id: s.source_type for s in sources}

    all_chunks: list[Chunk] = []
    for source_id, text in raw_docs.items():
        all_chunks.extend(chunk_document(source_id, text))

    deduped = _dedupe_chunks(all_chunks)
    candidates = keyword_prefilter(deduped)
    print(f"  [process] {len(all_chunks)} chunks -> {len(deduped)} deduped -> {len(candidates)} keyword candidates")

    if not candidates:
        return []

    classifications: dict[str, dict] = {}
    for start in range(0, len(candidates), batch_size):
        batch = candidates[start : start + batch_size]
        prompt = render_prompt(
            load_prompt("classify_chunk.md"),
            project=project,
            current_version=current_version,
            target_version=target_version,
            chunks_json=[
                {"chunk_id": c.chunk_id, "heading": c.heading, "text_preview": c.text[:700]} for c in batch
            ],
        )
        result = call_structured(
            claude,
            prompt=prompt,
            output_model=ChunkClassifications,
            tool_name="record_chunk_classifications",
            tool_description="Record a category and risk-candidate flag for each chunk.",
            max_tokens=8000,
        )
        for classification in result.classifications:
            classifications[classification.chunk_id] = classification.model_dump()

    selected: list[dict] = []
    for chunk in candidates:
        classification = classifications.get(chunk.chunk_id)
        if not classification or not classification["is_candidate_risk"]:
            continue
        selected.append(
            {
                "chunk_id": chunk.chunk_id,
                "source_id": chunk.source_id,
                "source_type": source_type_by_id.get(chunk.source_id, "unknown"),
                "heading": chunk.heading,
                "text": chunk.text,
                "category": classification["category"],
            }
        )
    print(f"  [process] {len(selected)} chunks classified as risk-candidates")
    return selected


# ---------------------------------------------------------------------------
# Stage 3: extract
# ---------------------------------------------------------------------------


def stage3_extract(
    project: str,
    current_version: str,
    target_version: str,
    candidate_chunks: list[dict],
    registry_metadata: dict | None,
    claude: Claude,
) -> list[RiskPath]:
    supplementary = [{"source_id": "registry_meta", "content": registry_metadata}] if registry_metadata else []
    prompt = render_prompt(
        load_prompt("extract_risk_paths.md"),
        project=project,
        current_version=current_version,
        target_version=target_version,
        evidence_chunks_json=[
            {
                "source_id": c["source_id"],
                "source_type": c["source_type"],
                "chunk_id": c["chunk_id"],
                "heading": c["heading"],
                "text": c["text"],
            }
            for c in candidate_chunks
        ],
        supplementary_evidence_json=supplementary,
    )
    result = call_structured(
        claude,
        prompt=prompt,
        output_model=ExtractedRiskPaths,
        tool_name="emit_risk_paths",
        tool_description="Record the extracted upgrade risk paths and their conditions.",
        max_tokens=16000,
    )
    normalize_risk_path_ids(result.risk_paths)
    return result.risk_paths


def normalize_risk_path_ids(risk_paths: list[RiskPath]) -> None:
    """Slugifies + de-duplicates path_id/condition_id in place. Done right
    after extraction (not at assembly) so every later stage - grounding
    notes, the critic's evidence_summary references, normalization - refers
    to the same stable ids as the final output.
    """
    _dedupe_ids(risk_paths, lambda p: p.path_id, lambda p, v: setattr(p, "path_id", v))
    for path in risk_paths:
        _dedupe_ids(path.conditions, lambda c: c.condition_id, lambda c, v: setattr(c, "condition_id", v))


# ---------------------------------------------------------------------------
# Stage 4: ground
# ---------------------------------------------------------------------------


def _filter_unsupported(risk_paths: list[RiskPath], valid_source_ids: set[str]) -> tuple[list[RiskPath], list[str]]:
    """Deterministic hard gate: drops any evidence item citing an unknown
    source_id, drops any condition left with zero evidence, and drops any
    risk path left with zero conditions. Returns (surviving_paths, notes)
    where notes record what was dropped and why, for transparency.
    """
    notes: list[str] = []
    surviving_paths: list[RiskPath] = []
    for path in risk_paths:
        surviving_conditions: list[Condition] = []
        for condition in path.conditions:
            valid_evidence: list[Evidence] = [e for e in condition.evidence if e.source_id in valid_source_ids]
            dropped = len(condition.evidence) - len(valid_evidence)
            if dropped:
                notes.append(
                    f"Dropped {dropped} evidence item(s) with unknown source_id from "
                    f"condition {condition.condition_id!r} in path {path.path_id!r}."
                )
            if not valid_evidence:
                notes.append(
                    f"Dropped condition {condition.condition_id!r} in path {path.path_id!r}: "
                    "no valid evidence after grounding check."
                )
                continue
            surviving_conditions.append(condition.model_copy(update={"evidence": valid_evidence}))
        if not surviving_conditions:
            notes.append(f"Dropped risk path {path.path_id!r} ({path.path_name!r}): no conditions had valid evidence.")
            continue
        surviving_paths.append(path.model_copy(update={"conditions": surviving_conditions}))
    return surviving_paths, notes


def _enforce_coverage_rules(risk_paths: list[RiskPath]) -> tuple[list[RiskPath], list[str]]:
    """Deterministic structural gate mirroring
    tests/test_condition_coverage.py: every risk path must have >=1
    `version`-category condition, and >=1 condition in a matching
    application/deployment category when its `affected_surface` implies
    one. A path that loses its only qualifying condition during evidence
    grounding (see _filter_unsupported) is a real, if disappointing,
    outcome - drop it here rather than let it reach `data/output/` in a
    structurally incomplete state, and record why.
    """
    notes: list[str] = []
    surviving: list[RiskPath] = []
    for path in risk_paths:
        categories = {c.category for c in path.conditions}
        if "version" not in categories:
            notes.append(f"Dropped risk path {path.path_id!r}: no surviving condition checks the target version.")
            continue
        needs_surface_condition = path.affected_surface in APPLICATION_OR_DEPLOYMENT_SURFACES
        if needs_surface_condition and not (categories & APPLICATION_OR_DEPLOYMENT_CATEGORIES):
            notes.append(
                f"Dropped risk path {path.path_id!r}: affects {path.affected_surface!r} but no surviving "
                "condition is application/deployment-facing (likely lost its evidence during grounding)."
            )
            continue
        surviving.append(path)
    return surviving, notes


def stage4_ground(
    project: str,
    current_version: str,
    target_version: str,
    risk_paths: list[RiskPath],
    candidate_chunks: list[dict],
    sources: list[Source],
    claude: Claude,
) -> tuple[list[RiskPath], EvidenceSummary]:
    valid_source_ids = {s.source_id for s in sources}
    gated_paths, gate_notes = _filter_unsupported(risk_paths, valid_source_ids)
    for note in gate_notes:
        print(f"  [ground] {note}")

    if not gated_paths:
        return [], EvidenceSummary(open_questions=gate_notes or ["No risk path survived the evidence-grounding gate."])

    prompt = render_prompt(
        load_prompt("critic.md"),
        project=project,
        current_version=current_version,
        target_version=target_version,
        risk_paths_json=[p.model_dump() for p in gated_paths],
        evidence_chunks_json=[
            {"source_id": c["source_id"], "chunk_id": c["chunk_id"], "heading": c["heading"], "text": c["text"]}
            for c in candidate_chunks
        ],
    )
    critic_result = call_structured(
        claude,
        prompt=prompt,
        output_model=CriticOutput,
        tool_name="record_critic_review",
        tool_description="Record the corrected risk paths and the evidence summary.",
        max_tokens=16000,
    )

    evidence_gated_paths, second_gate_notes = _filter_unsupported(critic_result.risk_paths, valid_source_ids)
    for note in second_gate_notes:
        print(f"  [ground] (post-critic) {note}")

    final_paths, coverage_notes = _enforce_coverage_rules(evidence_gated_paths)
    for note in coverage_notes:
        print(f"  [ground] (coverage) {note}")

    evidence_summary = critic_result.evidence_summary
    all_notes = [*gate_notes, *second_gate_notes, *coverage_notes]
    if all_notes:
        evidence_summary = evidence_summary.model_copy(
            update={"open_questions": [*evidence_summary.open_questions, *all_notes]}
        )
    return final_paths, evidence_summary


# ---------------------------------------------------------------------------
# Stage 5: assemble
# ---------------------------------------------------------------------------


def stage5_assemble(
    project: str,
    current_version: str,
    target_version: str,
    risk_paths: list[RiskPath],
    sources: list[Source],
    evidence_summary: EvidenceSummary,
    claude: Claude,
) -> dict:
    prompt = render_prompt(
        load_prompt("normalize_output.md"),
        project=project,
        current_version=current_version,
        target_version=target_version,
        risk_paths_json=[p.model_dump() for p in risk_paths],
        evidence_summary_json=evidence_summary.model_dump(),
    )
    normalization = call_structured(
        claude,
        prompt=prompt,
        output_model=OutputNormalization,
        tool_name="record_output_normalization",
        tool_description="Record the final summary, overall confidence, and open questions.",
    )

    final_risk_paths = [FinalRiskPath.model_validate(p.model_dump()) for p in risk_paths]
    model = {
        "project": project,
        "current_version": current_version,
        "target_version": target_version,
        "summary": normalization.summary,
        "source_inventory": [s.model_dump() for s in sources],
        "risk_paths": [p.model_dump() for p in final_risk_paths],
        "open_questions": normalization.open_questions,
        "overall_confidence": normalization.overall_confidence,
    }
    return model
