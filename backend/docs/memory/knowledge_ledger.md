# Intent-backed knowledge ledger

This is the proposed target architecture for Omi knowledge. It is additive
until the evaluation, migration, supported-client, and zero-consumer gates in
the JIT project plan pass; the currently locked tiered lifecycle remains product
authority before that cutover. The proposed physical authority remains
canonical `memory_items` plus its apply control, operation journal, evidence,
commits, graph/assertion compatibility, privacy state, and outbox. No second
`MemoryDB` collection is introduced.

## Semantic rows

Every `knowledge_ledger.v1` row is one of:

| `kind` | `content` | Optional data | Current-view rule |
|---|---|---|---|
| `fact` | One durable fact or episodic observation | `slot`, validity, subject | Only open, intent-backed, primary-user slotted facts render into profile |
| `document` | One-line playbook description | bounded `body` | Profile exposes only `memory_id: description`; `read_playbook` loads body |
| `trigger` | Standing-intent description | bounded structured condition | Compiles into the local watchlist; never injected as a profile fact |

Common fields are `memory_id`, `kind`, `content`, `subject_scope`,
`subject_entity_id`, `valid_from`, `valid_to`, `superseded_by`,
`curation_weight`, `intent_backed`, `write_reason`, evidence, sensitivity,
visibility, account generation, item revision, and ledger commit/sequence.
`tier=long_term` is emitted only for directional compatibility with released
clients and is not ledger lifecycle state.

Stable fact slots initially include `home_city`, `employer`, and `age_years`.
Preferences remain unslotted unless a domain-specific stable key is ratified;
this avoids silently treating unrelated preferences as one replaceable value.

## Write authorization

Allowed reasons are direct user statement, explicit remember, reusable
conclusion derived while serving the current request, recurring workflow,
standing trigger, onboarding, bounded daily reconciliation, and legacy
migration. Only direct statement, explicit remember, and onboarding set
`user_asserted=true`. Legacy migration is the sole reason allowed to be
non-intent-backed and never enters the rendered profile.

Every write carries a stable action ID and source ID/type/version. Evidence
preserves artifact and quote references where available. Third-party facts
require a stable person/entity ID and `subject_scope=third_party`; they never
enter the user's rendered profile.

## Atomic semantics

- IDs derive from account, action identity, semantic row, and supersession set.
- Retry with the same action is idempotent.
- Apply compares the account-global head plus target revisions/content hashes.
- A head mismatch replans; a stale target never blind-writes.
- Amendment appends the replacement and closes every named predecessor in the
  same apply commit and outbox sequence.
- Closing sets `valid_to` and a non-active status without deleting history.
- Privacy deletion remains a tombstone/purge operation and outranks history.

## Read and prompt policy

Keyword and vector providers return candidate IDs only. Authoritative rows are
hydrated and policy-filtered before use. Current fact, historical fact,
document, and trigger searches are semantic filters over the same authority.

Omi chat currently exposes the additive `search_knowledge` and
`read_playbook` tools. Search is owner-scoped, policy-filtered, and restricted
to active `knowledge_ledger.v1` rows; it returns bounded handles and
descriptions without document bodies or trigger payloads. Reading a playbook
is an explicit second, owner-scoped lookup and admits only active primary-user
documents. Historical ledger search remains gated on its separate retention
and privacy policy, so these tools do not authorize a capture cutover.

`get_entity_timeline` is a separate, owner-scoped multi-source read for an
agent that has already selected a stable entity. The agent explicitly chooses
ledger, conversation-summary, calendar-title, or screen-app/window sources;
there is no query-word heuristic and the default remains the cheap ledger-only
path. A people document ID is the entity authority. Current names, bounded
retained names, and emails are exact match-only aliases and are never returned
as timeline content. Aliases that collide with the owner or another bounded
owner-scoped person record are suppressed; if the people scan is not exhaustive,
alias joins fail closed while stable person-ID joins remain available. Source
readers perform exact owner/entity joins, merge by
stable time/source/record ordering, disclose unavailable or truncated sources,
and return only compact source-appropriate facts, summaries, titles, and
app/window metadata. Transcript text, calendar notes and attendees, OCR text,
pixels, playbook bodies, and trigger payloads remain excluded. Closed or
rejected ledger rows require the explicit history and audit flags; wording in
the agent's query never enables them.

The deterministic prompt view sorts open, intent-backed, primary-user slotted
facts by descending curation weight, slot, validity time, and ID, then fits
whole lines into 2,400 characters. The playbook index fits whole one-line
handles into 800 characters. Closed facts, unslotted observations, third-party
facts, document bodies, and trigger bodies are excluded.

## Capture and retrieval

At the target cutover, conversation finalization produces the user-facing
summary/action items and required indexes, but no memory. The released
finalizer still runs memory extraction until the replacement quality gates
pass; this contract does not authorize disabling it. Bounded JIT conversation
retrieval remains explicitly default-off. When its gate is enabled, the agent
prompt directs bounded literal, entity, semantic, and date-only summary
triage, one bounded reformulation before reporting no result, and selective
hydration of at most 24 transcript segments or three matched snippets per
conversation. The target first-open flow preserves the same no-memory fence.

Screen OCR/app/window/time/vector metadata stays local/searchable. Pixels are
interpreted only after a relevant frame is selected, except one
policy-compliant conversation keyframe. Evidence responses must represent
loading, offline, pruned, failed, and available states without blocking the
text answer.

## Migration and removal

Existing Long-term rows adapt in place with `write_reason=legacy_migration`
unless already user-asserted. Existing Short-term rows require a separate,
explicit adjudication; the migration planner never silently promotes them.
Per-row revision markers make planning deterministic and resumable.
The checked-in hermetic fixture proves planner counts, minimum provenance
identity, profile rendering, and resume bookkeeping only. A migration gate
still requires the real canonical apply transaction plus persisted readback in
an authorized non-production store or cohort.

Old clients may temporarily decode ledger rows through the Long-term
compatibility projection. Removing that projection, historical adapters,
promotion code, indexes, schedules, or rollback state requires zero live
reader/writer evidence, supported-client adoption, and account
deletion/export/privacy regression proof.

Until those gates pass, this document specifies candidate contracts and guard
tests only. It does not authorize capture cutover, scheduled-job removal,
production migration, cohort activation, deployment, or deletion.
