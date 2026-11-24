# 2026-11-19: batch projection applies v3 admission to the rows it creates

## Why

Sync intake (`utils/conversations/lifecycle.py` `ingest_sync_conversation`) marks a new pendant or
phone row as a v3 recording (`triggers.mark_new`) for owners admitted to conversations v3, then wakes
the v3 reconcile (`triggers.changed`) when the assigned row is a recording. Batch projection
(`utils/batch_pipeline/projection.py`, Cloud Run `backend-integration`) projects the same sync audio
through `conversations_db.assign_sync_conversation` directly and skipped both steps.

So every row projection created for an admitted owner was a legacy completed conversation
(`relevance_decision.trigger` `sync_intake`, then `sync_update` on enrichment) beside that owner's v3
recordings: a duplicate Home card, plus full legacy notes, memories and action items (double LLM spend).
Projection appends to an existing v3 recording also never woke its reconcile.

## What changed

- Projection calls `triggers.mark_new(owner, incoming)` right before assignment, the same boundary and
  the same admission (`conversations_v3_enabled`) as sync intake. Owners not admitted are unchanged.
- After a committed assignment whose row is a recording, projection calls `triggers.committed_sync_assignment` (wraps `triggers.changed`). The call
  is post-commit and never fatal, so a failure cannot replay the unit; it logs
  `event=batch_projection action=v3_wake outcome=error`.
- `tests/unit/test_batch_projection_v3_admission.py` covers admitted, not admitted, append-to-recording
  and wake-failure cases, and statically requires every caller of `assign_sync_conversation` that can
  create rows from new speech to call `mark_new` (`utils/sync/bridge.py` re-assigns existing rows and is
  exempt).

## Rollout

No new flag. `CONVERSATIONS_V3=off` (kill switch) and the stage gate still decide admission. Rows created
before this change stay legacy; the cleanup is a separate, operator-run step.
