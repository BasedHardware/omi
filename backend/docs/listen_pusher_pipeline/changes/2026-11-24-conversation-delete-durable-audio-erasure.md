# Conversation delete erases its audio durably, without taking a live sibling's staging

## What changed

`DELETE /v1/conversations/{id}` now erases the conversation's audio in both cascade modes. This reland of #26215
covers the canonical audio packs, the conversation and merge-donor audio prefixes, and the sync staging of the
uploads that fed the conversation (`syncing/{uid}/{job_id}/`). Before #26215, a default `cascade=false` delete
erased no audio at all. David approved the wider default scope on 2026-11-24 at 10:24Z (SCA-1819), on condition
that the audio cleanup is durable: failures are retried, not only logged.

- **Sibling-safe staging.** One upload job's staging directory can feed several conversations. The directory is
  erased only when every conversation that job fed has a deletion tombstone and every ledger row naming the job
  is `completed` (`database/sync_ledger_sources.staging_plan`). A fed conversation counts as deleted when it has
  a tombstone, when it is the deleting conversation or one of its merge donors (whose audio this deletion owns, even
  before the cascade writes their tombstones), or when neither its row nor a tombstone exists.
  - If a fed conversation is still live, the bytes stay, and that conversation's own deletion removes them.
  - If the upload has not completed, its staging is kept and retried later.
  - Ledger-linked batch rows follow the same all-tombstoned rule, as in #26215. Owed segment ids are now
    journaled up front, so a resumed purge whose cursor is already past discovery still erases them.
- **Durable retry.** The delete arms one `conversation_audio_erasure_jobs` obligation after the tombstone and
  before it deletes the primary row. If arming fails, the delete answers 503 and keeps the row.
  - The existing conversation-obligation reconciler dispatches the obligation on the conversation-erasure queue
    with `kind: audio_erasure`, spread per account.
  - `run_audio_erasure_job` needs only the tombstone, so it finishes even after the row is gone. A missing
    tombstone means an account wipe already erased everything; the obligation completes.
  - Every step runs under the account's `audio_conversation_deletion` gate, which refuses an active legal hold.
  - Object holds (`StoragePrefixPurgeBlocked`) are recorded on the obligation (`last_reason=storage_hold`,
    `blocked_objects`) and rechecked hourly.
  - In-flight staging (`last_reason=staging_in_flight`) is rechecked hourly for 14 days. After that, the
    obligation is never discharged while the staging is kept: it stays owed as `last_reason=staging_unsettled`,
    is logged at error level as `event=conversation_audio_erasure outcome=staging_unsettled` on every pass, and is
    rechecked daily.
  - If the conversation row is still visible (the delete failed after arming and answered 503), the runner waits
    (`last_reason=conversation_row_live`, rechecked after 5 minutes) instead of erasing the audio.
  - On its first run the obligation records every staging job it reaches, with all the conversations that job
    fed (`staging_sources`), before any hold or kill-switch check. Content-ledger rows expire after 45 days, and a
    held obligation can outlive them. The recorded set is used together with any fresh ledger read: its prefixes
    stay owed, and its recorded siblings still count as live. Every pass that left staging waiting
    (`staging_in_flight`, `staging_unsettled` or `staging_kept_for_live_sibling`) re-reads the ledger and merges new
    siblings into the record; the record never shrinks. A recorded job also records whether a pass ever saw all its
    ledger rows `completed` (`staging_settled`). Once its ledger rows expire, only a job recorded as settled counts as
    settled; any other recorded job stays in flight and is held, because a conversation it fed after the record could
    be unknown.
  - The obligation is never discharged while a recorded prefix is kept for a live sibling. It stays held
    (`last_reason=staging_kept_for_live_sibling`, rechecked daily) and erases the prefix once that sibling is
    deleted.
  - Contention on the account's audio gate counts as `busy` (30 s retry), not as a failure.
  - A held canonical audio-pack object (`objectUnderActiveHold`, `retentionPolicyNotMet`) is reported like any other
    held object (`storage_hold`), and the other steps still run.
  - Deliberate holds (`storage_hold`, `staging_*`, `switched_off`, `conversation_row_live`, a legal hold) reset the
    dispatch attempt count, so they do not trip the reconciler's "still pending" error; real failures still count.
    Each outcome clears detail fields left by an earlier outcome that it does not set.
  - Ledger-read and provider failures redrive.
  - Accepted (busy-gate) cascades arm the same obligation, with the donors recorded at acceptance.
- **Unchanged.** Tombstone-first ordering, the held-account deferral (no erasure while a hold is active), the
  existing batch-purge and cascade-erasure obligations, the account gate, and automatic empty-generation
  teardown, which keeps its audio.

## Retention exceptions

Only the durable obligation retries staging that has to stay. These paths erase best-effort with the same
sibling-safe rule, but keep in-flight or shared staging without a retry:

- The after-response background erasure, used when the kill switch is off or obligation dispatch is not configured
  (dev, local). That path is the kill switch's documented fallback. Its whole sweep holds the account's
  `audio_conversation_deletion` gate (`storage.delete_conversation_audio_under_gate`). A legal hold placed after the
  delete was accepted, an unreadable hold authority, or a busy gate therefore stops it before any erasure. Because
  this path has no retry, the audio is then retained and logged as
  `event=conversation_audio_purge outcome=retained reason=<LegalHoldActive|...>`.
- The conversations-v3 recording audio purge (`utils/conversations/v3/service.purge_audio`). It erases a
  recording's audio, which is not a user conversation delete. It has no tombstone, which is the runner's only
  authority to erase, so arming an obligation there would complete as `no_tombstone`.

In both, a later deletion of a sibling conversation through the route arms its own obligation, which owes the
shared staging. A sibling deleted more than 45 days later, after the ledger rows expired and with no obligation
recorded in the meantime, cannot be traced to the job. Account deletion still sweeps `syncing/{uid}/`.

## Rollout and flags

The change ships on, behind the kill switch `CONVERSATION_AUDIO_ERASURE_OBLIGATION_ENABLED` (`ops_kill` in
`config/feature-flags.yaml`, default on).
- `false/off/0/no` restores the best-effort after-response background erasure.
- The switch only takes effect where conversation obligation dispatch is configured (backend-sync). Dev and local
  keep the background path.
- **Switch off with obligations armed.** The reconciler stops dispatching audio obligations, and a task already
  queued holds its obligation (`last_reason=switched_off`) instead of erasing. Nothing is dropped: switching back
  on resumes them. Deletes made while the switch is off use the best-effort background erasure and arm nothing.
- **Rollback to an image without `conversation_audio_erasure_jobs`.** An older reconciler never reads that
  collection, and an older consumer drops `kind: audio_erasure`. Audio owed by deletes made on this image would
  then wait unserved. Before rolling back backend-sync, keep the new consumer serving until the collection is empty,
  or record its remaining rows and redeploy a serving consumer afterwards. The rows are never lost: they stay due.
  Rolling back only the request-serving backend is safe.
- The sibling-safe staging rule is not switchable.
- The new collection's read budget is in `.github/firestore-collection-budgets.json`.

Verification after serving:
- `conversation_audio_erasure_jobs` drains. The reconciler's `audio_erasures_dispatched` counts track deletes,
  and the `conversation audio erasure obligation still pending` error log stays rare.
- `event=conversation_audio_erasure outcome=storage_held` and `outcome=staging_in_flight` are bounded, and each
  maps to a held object or a running upload.
- For a synthetic account with a shared A/B upload: deleting A keeps `syncing/{uid}/{job}/`, and deleting B
  removes it.

## Evidence

- SCA-1819: the Owners FIX BEFORE RELEASE review (09:50Z), David's ruling (10:24Z), and the reland PR.
- [Ledger rule](../../../tests/unit/test_sync_ledger_sources.py),
  [storage steps](../../../tests/unit/test_owner_storage_purge_and_gate.py),
  [obligation runner](../../../tests/unit/test_conversation_batch_purge_resumable.py),
  [route arming](../../../tests/unit/test_conversation_tombstones.py).
