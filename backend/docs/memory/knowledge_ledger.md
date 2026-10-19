# Intent-backed knowledge ledger

This describes the retained knowledge-ledger data contract. The JIT migration
and on-demand conversation-retrieval paths were retired on 2026-10-18; no
runtime migration is active. Existing ledger rows remain subject to the normal
read, export, deletion, and retention paths. The physical authority remains
canonical `memory_items` plus its apply control, operation journal, evidence,
commits, graph/assertion compatibility, privacy state, and outbox. No second
`MemoryDB` collection is introduced.

## Semantic rows

Every `knowledge_ledger.v1` row is one of:

| `kind` | `content` | Optional data | Current-view rule |
|---|---|---|---|
| `fact` | One durable fact or episodic observation | `slot`, validity, subject | Only open, intent-backed, primary-user slotted facts render into profile |
| `document` / `trigger` | Legacy stored kinds | bounded body/condition | Retained for stored-data compatibility; no active JIT tool surface writes or reads these kinds |
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

Current runtime retrieval and memory mutation stay on their existing owner-scoped services. The retired JIT-only search, playbook, entity-timeline, and on-demand write tools are no longer exposed. Historical ledger rows remain available to account export and deletion paths.

The deterministic prompt view sorts open, intent-backed, primary-user slotted
facts by descending curation weight, slot, validity time, and ID, then fits
whole lines into 2,400 characters. Closed facts, unslotted observations,
third-party facts, document bodies, and trigger bodies are excluded.

## Capture and retrieval

Conversation finalization continues to run eager memory extraction and required
indexes for every eligible user. The retired JIT conversation-retrieval and
first-open paths do not gate or replace that processing, and this document does
not authorize a change to the independent demand-driven processing system.

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
