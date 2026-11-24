# Conversation delete erases its audio durably, without taking a live sibling's staging

## What changed

`DELETE /v1/conversations/{id}` now erases the conversation's audio in both cascade modes. This reland of #26215
covers the canonical audio packs, the conversation and merge-donor audio prefixes, and the sync staging of the
uploads that fed the conversation (`syncing/{uid}/{job_id}/`). Before #26215, a default `cascade=false` delete
erased no audio at all. David approved the wider default scope on 2026-11-24 at 10:24Z (SCA-1819), on condition
that the audio cleanup is durable: failures are retried, not only logged.

- **Sibling-safe staging.** One upload job's staging directory can feed several conversations. The directory is
  erased only when every conversation that job fed has a deletion tombstone and every ledger row naming the job
  is `completed` (`database/sync_ledger_sources.staging_plan`).
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
  - In-flight staging (`last_reason=staging_in_flight`) is retried for up to 14 days, then reported with
    `event=conversation_audio_erasure outcome=staging_unsettled`.
  - Ledger-read and provider failures redrive.
  - Accepted (busy-gate) cascades arm the same obligation, with the donors recorded at acceptance.
- **Unchanged.** Tombstone-first ordering, the held-account deferral (no erasure while a hold is active), the
  existing batch-purge and cascade-erasure obligations, the account gate, and automatic empty-generation
  teardown, which keeps its audio.

## Rollout and flags

The change ships on, behind the kill switch `CONVERSATION_AUDIO_ERASURE_OBLIGATION_ENABLED` (`ops_kill` in
`config/feature-flags.yaml`, default on).
- `false/off/0/no` restores the best-effort after-response background erasure.
- The switch only takes effect where conversation obligation dispatch is configured (backend-sync). Dev and local
  keep the background path.
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
