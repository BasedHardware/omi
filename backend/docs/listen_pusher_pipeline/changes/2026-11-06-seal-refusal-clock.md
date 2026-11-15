# First-refusal clock on producer-pending record seals

Phase 1 adds `record_seal_refused_at`, an epoch float set only on the first
`producer_pending` refusal inside `seal_record_audio.commit`'s existing
transaction. A second refusal preserves the first clock without another update.
Successful `seal_record_audio` closure writes `record_audio_closed=True` and clears an existing
clock to null in the same transaction. Partial-audio early returns do not close
or clear the clock. Other refusal reasons retain their no-write behavior.

`RECORD_SEAL_REFUSED_STAMP_ENABLED` defaults to **true** (lead2, bus 430238).
False restores refusal's zero-write behavior and disables sweeper observations.
Normal successful seal still clears a prior stamp. Rollback is the environment switch
on the relevant processes, or reverting this change; old stamps are harmless
ignored metadata. No backfill, cleanup, token mutation or data migration is needed.

The existing bounded sweeper summary emits `omi_record_seal_refused_count` and
`omi_record_seal_refused_age_seconds` (maximum observed age, clamped to zero),
including stamped rows skipped for legacy bare tokens. Only finite numeric
clocks on unclosed rows in the existing `record_pending` job page count. The
stamp is meaningful only while `record_audio_closed` is false. A stamped row
whose audio is already closed is stale metadata and contributes neither count
nor age, including when a repair/nojob seal left the stamp in place. The
sample describes rows classified in this run, before apply, not total fleet
stock. No new query or write is added to the sweeper. Failed/partial discovery
must not be interpreted as complete stock. These are gauge-valued structured
summary fields; this PR does not provision external log metrics or alerts.

The state table declares `record_audio:seal_refused`, its entry writer,
callback-only seal exit, age metric and intended agent alert identity. It keeps
the clock out of `PHASE_FIELDS`. Strict expected failures retain the missing
automatic exit/deadline and authoritative fleet metric/committed-alert gaps.
General live-producer dwell remains a gap: the first-refusal subset does not
measure every producer. Phase 4 can consume this clock without changing phase
1's seal authority or `is_debt` completion gate.

Custody/privacy: one content-free timestamp, at most one refusal update while the
first-entry clock is present, inside the existing transaction. No audio, identifiers,
producer tokens, full-proof repair, privacy predicates or seal authority change.
Exact-token finish and proof repair retain their existing authority. Legacy
three-attempt retirement and durable-drain retry/backoff semantics are unchanged.
A successful `seal_record_audio` call clears the clock. Per the uicleanup
read-side ruling, separate repair/nojob writers remain unchanged and may retain
a stamp on a closed row. The sweeper excludes that row before updating backlog,
refusal count or maximum refusal age; it does not clear or rewrite the stamp.
The state-table row describes this unclosed-only observation, not a persisted
phase independent of `record_audio_closed`. A later reopen can retain its original
first-refusal epoch until normal successful seal; this PR does not redefine it.

Verification uses strict transaction unit tests, writer/state-table invariants,
registry/deployment contracts and the emulator lifecycle simulator. The added
simulator regression SIGKILLs an owned pusher, starts a fresh pusher, verifies
clock persistence/age and retry idempotence, then exercises exact-token finish
and atomic seal clearing. Sweeper regressions cover a stale closed stamp both
alone and beside an open row, plus a row sealed through the real proof-repair
transaction whose retained stamp is excluded on the next sweep. These tests
use synthetic rows and local storage only.

Not measured: production refused-row stock/age; no-job refused rows; whether
production uses legacy drains; deployed flags or monitoring; released-client
field consumption; real vendor/model quality; production recovery or latency.
No GCP tier or production access is used, and this PR is not a deployment.
