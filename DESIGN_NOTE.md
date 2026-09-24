# Design Note: Upgrade Risk Extraction Pipeline

## 1. How did you decompose the extraction problem into workflow stages?

Five stages, each a plain Python function in `pipeline/stages.py`, sequenced
by `pipeline/orchestrator.py::run_pipeline`. Every stage's input/output is
persisted to `data/intermediate/<project>/` so each is independently
inspectable and re-runnable:

1. **Gather** (`stage1_gather`) - fetch curated seed URLs (trusted by
   construction), GitHub releases/issues (candidates), and package-registry
   metadata; triage the GitHub candidates with an LLM call before trusting
   them. Produces a `source_inventory` + raw document text.
2. **Process** (`stage2_process`) - deterministically chunk every raw
   document by heading (Markdown `#`/RST underline styles), deduplicate
   near-identical chunks, keyword-prefilter, then classify the survivors
   with an LLM call into a risk category and an `is_candidate_risk` flag.
3. **Extract** (`stage3_extract`) - the core LLM reasoning stage: turns the
   candidate-risk chunks into `risk_paths[]`/`conditions[]`, forced into the
   exact target schema via Anthropic tool-use forcing (`tool_choice`).
4. **Ground** (`stage4_ground`) - a deterministic hard gate (strip
   evidence citing unknown sources; drop conditions/paths left with none)
   followed by an LLM critic pass that cross-checks evidence, recalibrates
   confidence, and produces the evidence summary.
5. **Assemble** (`stage5_assemble`) - normalize IDs, an LLM pass to write
   the human-readable `summary`/`overall_confidence`, then a hard pydantic
   schema-validation gate before writing the final JSON.

This is a **fixed pipeline, not an autonomous agent**: the orchestrator
calls each stage in order rather than letting the model decide what to do
next. See Q7 for why, and for how that would change at scale.

## 2. What role did the LLM play?

Five distinct, narrow LLM calls, each forced into a specific output schema
via tool-use forcing (see `schema/risk_model.py::to_anthropic_tool` and
`pipeline/prompting.py::call_structured`):
`triage.md` (rank/filter discovered sources), `classify_chunk.md`
(categorize document sections), `extract_risk_paths.md` (the main
extraction), `critic.md` (evidence audit + confidence calibration),
`normalize_output.md` (final summary). No single unstructured "do
everything" prompt exists anywhere in the pipeline.

## 3. What parts of the pipeline are deterministic?

Seed-URL selection, HTTP fetching, HTML-to-text conversion, heading-based
chunking, near-duplicate detection (normalized-text fingerprint), the
keyword pre-filter before classification, ID normalization, the
evidence-citation hard gate (`stages.py::_filter_unsupported`), and final
pydantic schema validation. Roughly half the pipeline's actual code is
deterministic Python; the LLM is used specifically where judgment is
required (relevance, categorization, synthesis, self-critique) and nowhere
else.

## 4. How did you prevent hallucinated upgrade risks?

Four layers: (a) `extract_risk_paths.md` explicitly instructs the model to
leave `evidence` empty and mark `confidence: low` rather than fabricate a
quote when it can't find support; (b) a deterministic gate strips any
evidence citing a `source_id` that isn't in the actual source inventory,
and drops any condition/path left with zero evidence - this doesn't rely on
the model behaving, it's enforced in Python; (c) `critic.md` cross-checks
every remaining condition's quote against the original chunk text and
downgrades/flags mismatches; (d) final pydantic validation
(`FinalCondition`) mechanically rejects any condition with an empty
evidence list, so a malformed result can never reach `data/output/`.

## 5. How did you decide real risk condition vs. useful-but-contextual fact?

`classify_chunk.md` has an explicit `context_only` category with guidance
("a new feature announcement... not itself a risk condition") and
instructs conservative use of `is_candidate_risk`. `extract_risk_paths.md`
separately instructs: conditions that are true but don't gate whether the
risk applies should be omitted entirely rather than padded into the
condition list. The critic pass is a second check on the same question -
it can drop a condition it judges too vague to be "real."

## 6. How did you handle conflicting or incomplete public documentation?

Both are surfaced, never silently resolved. Conflicts: `critic.md`
instructs the model to keep a disputed condition but record the conflicting
`source_id`s in `evidence_summary.sources_with_disagreements` and explain
the disagreement in `ambiguities`, rather than picking a side.
Incompleteness: a condition with no supporting chunk gets `confidence: low`
+ an `ambiguities` note instead of being invented; anything the pipeline
itself couldn't resolve (dead seed URL, empty extraction, a path dropped
for lack of evidence) is appended to `open_questions` as an explicit
data-quality caveat, not hidden.

## 7. How would you scale this from 5 upgrades to thousands of projects/versions?

The main bottleneck is `sources/seed_urls.py` being hand-curated. At scale
this would become an automated discovery step: query the project's PyPI/npm
metadata for its homepage/repo URL, use the GitHub repo's own structure
(does it have a `CHANGELOG.md`? a `docs/` folder? a "migration guide" in
its README?) to auto-derive candidate seed URLs, and route everything
through the same `triage.md` step already built for GitHub-discovered
candidates rather than trusting seeds unconditionally. This is also where
the already-scaffolded `tools/websearch_stub.py` becomes load-bearing
instead of a no-op. At that point the fixed 5-stage pipeline would likely
need to become a true agentic loop for stage 1 specifically (let the model
decide which of several possible doc locations to check, stopping once it
has enough signal) - deterministic for the 5 known projects, agentic when
the source structure is unknown. Caching (`data/intermediate/`) and
per-project rate-limit-aware fetching become mandatory rather than nice-
to-have at that volume.

## 8. How would you evaluate precision and recall of extracted risks?

Implemented today: `tests/test_condition_coverage.py` (structural
sanity - every path has a version condition, application/deployment paths
have a matching condition) and `tests/test_schema_validation.py` (every
condition traces to real evidence). Neither measures precision/recall
against ground truth. The bonus-tier approach I'd add with more time: hand-
write a small gold set of ~10-15 known risks per upgrade (e.g., for Django
4.2, "`USE_L10N` removed" and "`django.conf.urls.url()` removed" are
well-documented, checkable facts), then score extracted risk paths against
it by embedding-similarity or LLM-judged match on `path_name`/`description`
to compute recall (gold risks found) and precision (extracted risks that
correspond to a real, checkable fact rather than a hallucinated or
duplicate one).

## 9. What would you improve with more time?

Automated seed-URL discovery (Q7); a human-review Markdown report rendered
from each JSON output; source-authority ranking to weight official over
community sources when they disagree instead of just flagging the
disagreement; semantic (embedding-based) chunk dedup instead of exact-match
fingerprinting; GitHub API rate-limit backoff/retry; a gold-set precision/
recall harness (Q8); concrete code-search query suggestions per condition
(e.g. a ripgrep pattern for `django.conf.urls.url(`) so the downstream
engine's "check a real codebase" step is closer to push-button.

## 10. How would this output be consumed by a downstream upgrade-assessment engine?

`schema/risk_model.py::UpgradeRiskModel` is the integration contract. Each
condition's `category`/`operator`/`expected_value` are structured
specifically so a downstream engine can programmatically evaluate them
against a real codebase/environment (e.g. `category: "api_usage",
operator: "present", expected_value: "django.conf.urls.url("` maps
directly to a grep/AST check) rather than requiring the engine to re-parse
prose. `required` distinguishes conditions that must all hold from ones
that are merely corroborating; separate `risk_paths` entries capture
mutually-exclusive alternative ways a risk manifests, so the engine can
evaluate each path independently and report per-path applicability rather
than one flat yes/no per upgrade. `confidence` and `ambiguities` let the
engine (or a human) prioritize triage - e.g. surface only `high`-confidence,
`required` conditions in a CI gate, while routing `low`-confidence /
disputed ones to manual review.

---

## Notes on what was trusted vs. not, and where this can fail

- **Trusted unconditionally**: hand-curated seed URLs (a human picked
  these specifically because they're each project's own official docs).
- **Trusted only after LLM triage**: GitHub-discovered releases/issues/PRs.
- **Not trusted as primary evidence**: nothing in this run - no community
  writeups were used as seeds; `tools/websearch_stub.py` is a documented
  no-op, so no un-vetted web content entered the pipeline for the 5
  required upgrades.
- **Known failure modes**: a seed URL going stale/moving (handled by
  skipping it with a warning, not crashing); GitHub's anonymous rate limit
  under heavy use; the heading-based chunker doing a mediocre job on a
  document with no headings and no paragraph breaks (falls back to
  fixed-size splitting, which is worse for evidence-quote precision); the
  critic pass itself being an LLM and therefore imperfect - it raises the
  bar but is not a formal guarantee, unlike the deterministic evidence
  gate it sits alongside.
