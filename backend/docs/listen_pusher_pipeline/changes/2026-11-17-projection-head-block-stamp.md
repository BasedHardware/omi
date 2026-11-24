# Stuck owner chains and held-partial uploads

Two batch-projection fixes. Neither changes a flag or a default.

**Head-wait bound.** A chain head that fails with a retryable error, such as a recent awaiting-writer conflict, waits up to
`PROJECTION_HEAD_RETRY_SECONDS` (24 h). After that it takes the held disposition, and its owner's chain advances.
The bound runs from `projection_blocked_since`. That stamp was written in a transaction that never began, so it never landed,
and those heads froze their chains indefinitely. The stamp now goes through `ProjectionStore.note_head_blocked`
(`@firestore.transactional`). The release reset clears it, and now the source-fallback `merge_ready` does too. A privacy replay keeps it,
because it continues the same head-wait episode. After deploy, heads that have waited for days are stamped on their next visit and hold about 24 h later.
Their successors then project, so expect a one-time rise in held units and in follow-up drain work in that window.
Held units keep their audio and use the existing hold-recovery path.

**Held-partial cursor.** `Projector.sweep_held` settles an upload whose only unit is `failed_held` as `partial`.
It used to resume from an in-memory cursor, and instances restart far more often than one pass wraps the held backlog.
Late IDs were therefore never examined. The cursor is now kept in `control/projection_held_partial_cursor`, using the release
scan's helpers. This adds one read and at most one write per segment.

Watch: `omi_batch_projection_*` holds and backlog, `event=batch_held_partial` segment and pass lines, and
`head_block_note outcome=retry` (expected to drop to about zero).
Regression coverage: `backend/tests/unit/test_batch_projection_head_block_note.py`,
`test_batch_pipeline_quarantine_recovery.py::test_restarted_instance_resumes_the_held_pass_from_the_durable_cursor`,
`test_batch_pipeline_source_reuse.py::test_fallback_restart_replaces_same_log_slot_and_charges_own_speech`.
