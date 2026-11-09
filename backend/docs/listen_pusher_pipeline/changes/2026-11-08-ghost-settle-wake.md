# Fence ghost settlement and wake settled projection rows

Lead2 ruling 934856: successful ghost settles hand their segment ids to
`Projector.owe_followups`, behind the current discovery page. The existing
follow-up queue deduplicates owed ids and caps them at 256; overflow resets
discovery. Completion still uses `complete_content` and its deletion/privacy
fences. No timestamps, caps, indexes or job types change.

Lead2 ruling 12c359: before the ghost write, the enabled selector reuses the
normal release `_target_restorable` fence inside the transaction. Missing or
unrestorable targets yield skip class `target_not_restorable`, with no writes
or wake. Flag-off count-only mode still uses only the existing job/result reads.

`BATCH_PIPELINE_PROJECTION_GHOST_SETTLE_WAKE_ENABLED` defaults to true. Set false
to stop these handoffs; settled ready rows remain recoverable by discovery.
The settle selector remains a separate control. Process death can lose the
in-memory wake but preserves the durable ready row.
