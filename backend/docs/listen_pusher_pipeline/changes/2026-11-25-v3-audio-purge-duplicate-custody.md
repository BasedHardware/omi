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

A merge target's retained donors are kept on the row
(`v3_audio_purge_source_ids`) until the erase runs. The erase then deletes their
canonical audio, as a user delete does with `sync_merged_from`. A successor that
still names an erased donor gets a refusal: handoff authority, live upload and
merge publication all reject a donor that is deleted, tombstoned or no longer
settled.

Rows without custody are unchanged: the claim makes the same reads and writes as
before.

`omi_conversations_v3_audio_purges_total{outcome}` counts `custody_invalidated`,
`intakes_pending`, `intakes_failed` and `erased`. The `audio-outbox/` prefix is
now listed with the other voice prefixes under `retain_until_user_deletes` in the
retention contract. Rollback: revert the PR.
[Pipeline contract](../../listen_pusher_pipeline.mdx#recording-derived-conversations-v3)
