You are triaging *candidate* sources discovered via GitHub search for an
open-source upgrade risk assessment. These candidates were found
automatically (GitHub issue/PR search, GitHub releases) and have **not**
been vetted by a human, unlike a project's own official documentation.

Upgrade under review: {{project}} {{current_version}} -> {{target_version}}

Your job is to decide, for each candidate, whether it is worth keeping as a
source of evidence about upgrade risk, and if so, to classify it and explain
why it's relevant.

Guidance:
- Prefer official/authoritative signal (a release, a maintainer's PR,
  an issue confirmed by a maintainer) over noise (an unrelated user
  question, a duplicate, a issue about something unrelated to this
  specific upgrade path).
- A GitHub issue/PR is worth keeping only if its title or body plausibly
  describes a breaking change, deprecation, removed feature, changed
  default, dependency/runtime requirement, or migration step relevant to
  going from {{current_version}} to {{target_version}} specifically -
  not just "any bug in this project ever."
- When in doubt about relevance, keep=false rather than inventing
  significance that isn't there.
- Third-party/community sources are acceptable only as *supporting*
  context, never as the primary basis for a required condition - note this
  in `why_relevant` if it applies.

Candidates to triage:

{{candidates_json}}

For every candidate in the list, produce exactly one decision with the
matching `source_id`, `keep`, the correct `source_type`
(`github_release` for a release, `github_issue_or_pr` for an issue/PR), and
a one-sentence `why_relevant` (or why not, if `keep` is false - still
explain briefly).
