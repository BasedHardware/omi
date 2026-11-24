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
  before the cascade writes their tombstones), when neither its row nor a tombstone exists, or when its row is a
  deletion marker (`conversations_db.is_soft_deleted`). An absorbed merge donor (a `deleted` row with
  `sync_merged_into`) counts as its survivor: its redirect chain is resolved with the sync redirect resolver
  (`sync_conversation_snapshot.resolve_snapshot`), and the donor is deleted only when the chain ends deleted or at
  the deleting conversation.
  - Sibling reads are batched (`get_all`) and capped at 200 per pass. Siblings found deleted are recorded on the
    obligation (`staging_deleted_siblings`) and not read again. A job with unread siblings and no live one waits
    (`last_reason=staging_siblings_pending`, `unchecked_siblings`) and continues after 60 s.
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
  - The arming request writes `delete_completed_at` on the obligation right after it deletes the primary row (an
    ordinary delete in either cascade mode deletes the row outright; an accepted delete hides it with
    `deleted=True`). With that marker the runner erases without looking at the row, and the marker makes a run that
    held for the row due at once. A request that fails after arming never writes it.
  - Without the marker, if the conversation row is still visible (the delete failed after arming and answered 503), the runner waits
    (`last_reason=conversation_row_live`) instead of erasing the audio. It rechecks after 5 minutes, doubling to
    hourly. After 24 hours (`row_live_since`) it rechecks daily, and those passes count toward the stuck-obligation
    alert.
  - Owed batch segment ids are journaled in chunks of at most 400 per transaction (Firestore allows 500 writes).
    A cursor already past discovery is rewound and persisted first, and dependent cleanup runs only after every
    chunk is recorded.
  - On its first run the obligation records every staging job it reaches, with all the conversations that job
    fed (`staging_sources`), before any hold or kill-switch check. Content-ledger rows expire after 45 days, and a
    held obligation can outlive them. The recorded set is used together with any fresh ledger read: its prefixes
    stay owed, and its recorded siblings still count as live. Every pass re-reads the ledger, read-only and before
    any hold (legal hold, switch off, row still visible, storage hold, staging waiting), and merges new siblings and
    settled state into the record. The record never shrinks. A recorded job also records whether a pass ever saw all its
    ledger rows `completed` (`staging_settled`). Once its ledger rows expire, only a job recorded as settled counts as
    settled; any other recorded job stays in flight and is held, because a conversation it fed after the record could
    be unknown.
  - The obligation is never discharged while a recorded prefix is kept for a live sibling. It stays held
    (`last_reason=staging_kept_for_live_sibling`, rechecked daily) and erases the prefix once that sibling is
    deleted. A settled job whose prefix is already empty in every staging bucket (one `list_blobs(max_results=1)`
    each) keeps nothing, so it no longer holds the obligation.
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
shared staging.

- **Deletes after the ledger TTL (accepted by Shipping on 2026-11-24, pending Owners' custody review).** A
  conversation deleted more than 45 days after its upload, once the content-ledger rows have expired and with no
  obligation recorded in the meantime, cannot be traced to its staging prefix. That prefix is retained. Reasons:
  - Before #26215, the default delete never touched staging at all.
  - Staging is normally removed by sync cleanup once processing completes, with a custody receipt.
  - Account deletion sweeps `syncing/{uid}/`.

  The runner logs `event=conversation_audio_erasure outcome=staging_undiscoverable_after_ledger_ttl` (info) when a
  sync-sourced conversation finds neither ledger rows nor a record. No new machinery tracks these.

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
  [route arming](../../../tests/unit/test_conversation_tombstones.py),
  [real route on the Firestore emulator](../../../tests/integration/test_conversation_batch_purge_emulator.py).
