You are screening chunks of official documentation for an open-source
upgrade risk assessment. Each chunk is one section of a release note,
changelog, migration guide, or deprecation notice.

Upgrade under review: {{project}} {{current_version}} -> {{target_version}}

For each chunk, decide:
1. Its category - what *kind* of upgrade-relevant fact it describes, if any.
2. Whether it is a genuine **risk-candidate** section (`is_candidate_risk`)
   worth extracting a risk path/condition from later, as opposed to
   background/contextual material that doesn't itself describe a way the
   upgrade could break something (e.g. "New feature: added a widget" with
   no removal/behavior-change/requirement implication).

Categories:
- `removed_api` - an API, method, class, or feature was removed.
- `changed_default` - a default value/behavior changed.
- `changed_behavior` - behavior changed under specific conditions, without
  necessarily being a "default".
- `dependency_requirement` - a dependency's supported/required version
  changed.
- `runtime_requirement` - a language/runtime/platform version requirement
  changed (Python, Node.js, etc.).
- `configuration_change` - a config option was renamed, removed, or its
  meaning changed.
- `data_migration` - a database/data-format migration is required.
- `migration_step` - an explicit instruction the user must follow to
  upgrade (may accompany any of the above).
- `known_incompatibility` - a documented known issue/incompatibility with
  specific other software.
- `operational_risk` - a deployment/operational concern (e.g. a required
  restart, an index rebuild, a one-time migration cost) not covered above.
- `context_only` - useful background but not itself a risk condition (a new
  feature announcement, an internal refactor with no user-visible risk, a
  performance improvement, marketing/framing text).
- `unknown` - genuinely unclear from this chunk alone.

Be conservative: only mark `is_candidate_risk=true` when the chunk
describes something a specific application could concretely break on, be
required to change for, or need to validate against - not just "this
version has changes."

Chunks to classify:

{{chunks_json}}

Return exactly one classification per chunk, matching `chunk_id`.
