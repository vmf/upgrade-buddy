"""Sequences the 5 pipeline stages for one upgrade and persists every
stage's output under data/ for inspectability (deliverable: "intermediate
extraction artifacts").
"""

from __future__ import annotations

import json
from pathlib import Path

from core.claude import Claude
from pipeline import stages
from schema.risk_model import UpgradeRiskModel
from sources.seed_urls import resolve_project

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def _write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, default=str))


def run_pipeline(project: str, current_version: str, target_version: str, claude: Claude) -> dict:
    project_key, config = resolve_project(project)
    display_name = config.get("display_name", project_key)
    intermediate_dir = DATA_DIR / "intermediate" / project_key
    output_dir = DATA_DIR / "output"

    print(f"[1/5] gather: {display_name} {current_version} -> {target_version}")
    sources, raw_docs, registry_metadata = stages.stage1_gather(
        project_key, config, current_version, target_version, claude
    )
    _write_json(intermediate_dir / "01_sources.json", [s.model_dump() for s in sources])
    _write_json(intermediate_dir / "01_raw_docs.json", raw_docs)
    print(f"  gathered {len(sources)} trusted sources")

    print("[2/5] process")
    candidate_chunks = stages.stage2_process(
        sources, raw_docs, display_name, current_version, target_version, claude
    )
    _write_json(intermediate_dir / "02_candidate_chunks.json", candidate_chunks)

    print("[3/5] extract")
    raw_risk_paths = stages.stage3_extract(
        display_name, current_version, target_version, candidate_chunks, registry_metadata, claude
    )
    _write_json(intermediate_dir / "03_risk_paths_raw.json", [p.model_dump() for p in raw_risk_paths])
    print(f"  extracted {len(raw_risk_paths)} raw risk paths")

    print("[4/5] ground")
    grounded_risk_paths, evidence_summary = stages.stage4_ground(
        display_name, current_version, target_version, raw_risk_paths, candidate_chunks, sources, claude
    )
    _write_json(intermediate_dir / "04_risk_paths_grounded.json", [p.model_dump() for p in grounded_risk_paths])
    _write_json(intermediate_dir / "04_evidence_summary.json", evidence_summary.model_dump())
    print(f"  {len(grounded_risk_paths)} risk paths survived grounding")

    print("[5/5] assemble")
    final_model = stages.stage5_assemble(
        display_name, current_version, target_version, grounded_risk_paths, sources, evidence_summary, claude
    )
    UpgradeRiskModel.model_validate(final_model)  # hard schema-validation gate

    _write_json(output_dir / f"{display_name}.json", final_model)
    _write_json(
        output_dir / f"{display_name}_sources.json",
        {
            "project": display_name,
            "current_version": current_version,
            "target_version": target_version,
            "sources": final_model["source_inventory"],
        },
    )
    _write_json(
        output_dir / f"{display_name}_evidence_summary.json",
        {
            "project": display_name,
            "upgrade": f"{current_version}_to_{target_version}",
            "evidence_summary": evidence_summary.model_dump(),
        },
    )
    print(f"Wrote {output_dir / f'{display_name}.json'}")
    return final_model
