# Batch-live transcript projection arms first-summary debt

The [summary custody contract](../../listen_pusher_pipeline.mdx#batch-projection-summary-custody)
now covers a completed capture whose finalizer binding remains after successful
handoff. Previously that binding made `stamp_projection_debt` refuse the row as
`generation_owned`; a pending-only receipt clock independently prevented a
missing due time from being armed. Placeholder-title admission alone could not
remove either guard.

The assignment codec verifies a bound finalizer in the projection transaction,
before writes: owner, conversation, positive revision, terminal success,
completed fanout and immutable non-BYOK custody must match. It persists the
generation-bound `summary_projection_finalization` proof with the transcript
and debt. A different job ID or revision restores the fence. Missing job
documents, invalid ID types and IDs containing a path separator refuse summary
admission without preventing transcript projection.
Valid non-future numeric pending clocks are retained, invalid/future clocks use
projection acceptance, existing due times stay fixed, and expired clocks are
not restarted. Structured title provenance stays unchanged so later apps,
goals, memories, folders and vectors retain their existing behavior.

This verifies a finalizer **when one is bound**. The existing unbound route is
preserved: `lifecycle.complete_orphan_batch_capture` deliberately completes a
proven orphan without a finalization job before canonical batch projection.
Unbound records still pass the ordinary debt, privacy and processing guards;
they do not receive a finalizer-custody exception.

The extra read is conditional: one bound-job lookup per qualifying advancing
projection transaction attempt. It is not a new sweep or provider call.
Projection and repair retain the same conversation-keyed enrichment outbox;
repair does not dispatch over an active lease. The new custody admission does
not reset job status, lifecycle status, summary budgets or existing task tokens.

The existing default-on `SUMMARY_PROJECTION_DEBT_ENABLED` is the kill switch.
False stops new enrollment and pauses proof-based repair for already-armed
rows, retaining their clocks. Existing enrichment continues. Re-enabling
restores proof admission only while the other generation, privacy, BYOK,
summary and age gates pass. A pause past the age window requires a fresh
residue count and separate approval before enrollment. The independent repair
enablement is unchanged. No backfill, rollout, production write or deployment
is performed by this source change.

Verification covers the real projection/session/assignment/codec commit and
stored due time in `tests/unit/test_batch_live_summary_arming.py`, the unbound
replacement contract in `tests/unit/test_batch_pipeline_live.py`, and the
existing repair refusal/lease contracts. CI-cost changes remain test-only:
shared AST parsing, statement-only constant discovery, and real lazy dependency
setup preserve the unchanged call-phase CPU guard and replay assertions.
