You are writing the final human-readable summary for an upgrade risk
report that has already been extracted and critiqued. Do not add, remove,
or alter any risk paths or conditions - they are final. Your only job is
to write:

1. `summary`: 2-4 sentences describing the upgrade and its major risk
   categories in plain language, suitable as the top-level summary of a
   report a human engineer will skim first. Mention the most severe/likely
   risks by name, not just "there are several risks."
2. `overall_confidence`: `high`, `medium`, or `low` - your holistic
   judgment of how confident this whole report is, considering the mix of
   confidence levels across all conditions and how many open questions
   remain. If most conditions are `low` confidence or there are many open
   questions, the overall confidence should not be `high`.
3. `open_questions`: carry forward (and lightly deduplicate/merge) the
   `open_questions` already identified during evidence review, plus add any
   further top-level caveat you think a reader needs (e.g. "this pipeline
   only reviewed public documentation, not the target application's actual
   code").

Upgrade: {{project}} {{current_version}} -> {{target_version}}

Final risk paths:

{{risk_paths_json}}

Evidence summary from the critic pass:

{{evidence_summary_json}}
