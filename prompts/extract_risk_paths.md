You are extracting **upgrade risk paths** for a downstream system that will
later check whether a specific application/deployment is affected. You must
be precise, specific, and strictly evidence-grounded.

Upgrade under review: {{project}} {{current_version}} -> {{target_version}}

An upgrade risk path is a specific, checkable way this upgrade could break
an application, require migration work, or create operational risk -
NOT a vague restatement like "there are breaking changes" or "some APIs
changed." Bad: "The app may need migration." Good: "The app fails at
startup if it references the removed `django.conf.urls.url()` function,
which is removed in Django {{target_version}}."

Each risk path has one or more **conditions** - the specific, checkable
facts that must hold for the risk to apply (e.g. "target version >= X",
"application calls API Y", "config option Z is set"). Distinguish:
- **Required** conditions (`required: true`): must hold for the risk to
  apply at all (e.g. the target-version condition itself).
- **Alternative** conditions/paths: if there are multiple, mutually
  exclusive ways a risk manifests, model them as separate risk paths rather
  than cramming alternatives into one path's condition list.
- Conditions that are merely **contextual** (true, but don't gate whether
  the risk applies) do NOT belong here at all - leave them out entirely
  rather than padding the condition list.

Rules (read carefully, these are graded):
1. Every condition's `evidence` list must cite only chunks provided below,
   using their exact `source_id`. Do not invent source_ids. Do not cite a
   source for a claim it doesn't actually support.
2. If you cannot find a chunk that supports a condition you believe is
   real, leave `evidence` empty, set `confidence` to `low`, and add a note
   to `ambiguities` explaining what's missing. NEVER fabricate a quote to
   fill an evidence slot - an empty evidence list is honest; a fabricated
   one is not, and will be caught and rejected downstream.
3. `quote_or_summary` in each evidence item should be a short direct quote
   or close paraphrase actually taken from that chunk's text - not a
   generic restatement of the condition.
4. Always include at least one condition whose `category` is `"version"`
   (checking the application/environment is actually on a version in the
   affected range) when the risk is version-gated - which is almost always,
   for an upgrade risk.
5. Where the risk is about application code, configuration, or deployment
   (not just "this version exists"), include at least one condition whose
   `category` reflects that surface (`api_usage`, `configuration`,
   `dependency`, `deployment`, `database`, etc.) so the downstream system
   has something concrete to check against a real codebase/deployment -
   not just a version condition.
6. Set `risk_level` based on likely blast radius and how commonly the
   affected surface is used, not on how dramatic the wording sounds.
7. `suggested_actions` should be concrete verification/migration steps
   (e.g. "grep the codebase for `django.conf.urls.url(`"), not generic
   advice like "test thoroughly."

Candidate risk-bearing chunks (already pre-filtered by keyword match and an
earlier classification pass - not everything here is necessarily a real
risk; use your judgment):

{{evidence_chunks_json}}

Supplementary structured evidence (registry/dependency metadata, if
available - use only to support runtime/dependency-requirement conditions,
never as a stand-in for documentation evidence about API/behavior changes):

{{supplementary_evidence_json}}

Extract every distinct risk path you can support with the evidence above.
It is fine to extract fewer, more solid risk paths than many weak ones.
