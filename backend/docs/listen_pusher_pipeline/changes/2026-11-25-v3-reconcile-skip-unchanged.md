# SCA-4432 · Skip unchanged v3 projection writes

Projection batches compare the final protected derived documents and recording patches with the
snapshots read under the existing transaction fences. An unchanged conversation skips the source
write and its Home dirty receipt. The Home feed hook still handles real changes. Protected blob
comparisons are local and require the same storage representation. The owner lease, account deletion,
tombstone, and recurring voice checks still run. The comparison adds zero Firestore reads.

Repeated pending marks preserve the existing outbox timestamp and still request the named task. A
legacy marker missing its timestamp is repaired so the ordered loader and sweep can find it. A
new manual close still persists the close marker and gets its own task name. The existing sweeper
can recover a pending marker when a minute task has already completed.

Set `CONVERSATIONS_V3_SKIP_UNCHANGED_WRITES=off` to restore unconditional writes.
`omi_conversations_v3_projection_rows` records written and skipped rows before commit hooks by
caller. `omi_conversations_v3_reconcile_billed_writes` records confirmed writes after those hooks,
including lease writes, when the Firestore write probe is enabled. Downstream notes processing
uses separate write attribution.
