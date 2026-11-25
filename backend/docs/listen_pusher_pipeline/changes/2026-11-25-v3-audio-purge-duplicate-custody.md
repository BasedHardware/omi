# v3 audio purge invalidates record-WAL duplicate custody

The `conversations-v3-sweep` purge erases a recording's audio once the user deleted
the last derived conversation that claimed it. A user erasure outranks
record-WAL duplicate custody, as it already does for a direct conversation delete
and for account deletion. Before this change, the purge erased the audio but left
the custody fields, the `wal_duplicate_<file>` and `wal_duplicate_terminal_<job>`
intakes, and the alias in place.

Now `claim_audio_purge` clears `wal_duplicate_settled_v1`,
`wal_duplicate_retained_donors_v1`, `wal_duplicate_merge_target_v1` and
`wal_duplicate_merge_plan_v1` in the same commit that closes the owner and writes
the tombstone. The same commit records that the recording's batch intakes are
owed erasure (`v3_audio_purge_intakes`). When conversation batch-purge dispatch is
configured, it also arms the per-conversation `conversation_batch_purge_jobs`
obligation that a user delete arms. Otherwise the sweep runs `purge_batch_owner`
inline. In both cases the blobs are erased only after the intake purge has
finished. A failure or an obligation that is still armed raises, and the
existing 5-minute retry keeps the row pending.

Legal holds: nothing is deleted while a hold is active. The purge runs the
obligation runner's hold preflight (`assert_account_deletion_permitted`) before
the claim. The inline `purge_batch_owner` calls run under the account gate a
synchronous user delete holds (`destructive_operation_gate`, kind
`explicit_memory_deletion`), and acquiring that gate re-checks the hold in its
transaction. Every blob deletion then runs under one gate of kind
`audio_conversation_deletion`, the kind the user-delete blob helper uses: the
canonical packs, the recording's raw prefixes, and every donor's packs and
prefixes. Its acquisition re-checks the hold, and while it runs
`place_legal_hold` refuses (`DestructiveOperationInProgress`), so a hold cannot
land between the canonical and the prefix deletes. The storage helpers' own
audio gate nests in it (same uid and kind) instead of taking and releasing a
second one. A hold placed after the intake gate releases is seen when the audio
gate is acquired, before any blob delete. A held purge raises, stays pending, is
counted as `held`, and the sweep re-checks it every 5 minutes.

Merge targets: the claim keeps the retained donors on the row
(`v3_audio_purge_source_ids`) until the erase runs. In the same commit it writes
each donor's tombstone (the batch purge requires one, and handoff, live upload
and merge publication refuse a tombstoned donor), clears the donor's custody
fields and, with dispatch, arms the donor's own obligation. The erase then purges
each donor's batch owner, deletes the donors' canonical packs with the
recording's, and deletes each donor's `raw-live/`, `audio-outbox/` and
`record-wal/` prefixes (`delete_conversation_audio_files`). Every step is
idempotent, and the pending bit clears only after the last one, so a partial
failure is retried whole. A donor that another target now retains is skipped.

Residual identifiers: the final update clears `v3_audio_purge_source_ids`. When
the erased row is itself a donor, the claim removes it from its successor's
`wal_duplicate_retained_donors_v1` and `sync_merged_from` in the same
transaction. Both lists drop the same id, so the equality a later merge checks
still holds.

Cost per purged row:
- Every row: 1 legal-hold read, the claim as before (row and tombstone reads;
  tombstone and row writes), and the audio gate's acquire and release (2 short
  transactions: 3 reads, 2 writes). Rows with canonical audio paid that gate
  before this change too; the helper now reuses it.
- Custody rows add 1 obligation read, the successor read when the row is a
  donor, and one `purge_batch_owner` (the cost a user delete pays), or the
  obligation run when dispatch is configured.
- Each retained donor (16 at most) adds 3 reads (row, tombstone, obligation),
  up to 3 writes (tombstone, custody clear, obligation), one `purge_batch_owner`
  and one `delete_conversation_audio_files`. That last call lists the user's
  `raw-sync/` and `raw-mobile-batch/` originals, as a user delete does.
- A retry repeats the reads and the idempotent deletes.

`omi_conversations_v3_audio_purges_total{outcome}` counts `custody_invalidated`,
`held`, `intakes_pending`, `intakes_failed` and `erased`. The `audio-outbox/`
prefix is now listed with the other voice prefixes under
`retain_until_user_deletes` in the retention contract. Rollback: revert the PR.
[Pipeline contract](../../listen_pusher_pipeline.mdx#recording-derived-conversations-v3)
