# Sync-revision fence defer rides the shared contention budget

## What changed

`defer_sync_revision_fence` — the conversation-finalization persistence
fence's yield, which returns a still-owned finalization job to the durable
sync-revision replay queue when a sibling processor won the
`sync_content_revision` CAS — now runs its transactional yield through
`run_with_transaction_contention_retry` (operation name
`finalization_sync_revision_defer`) instead of running the decorated
transaction bare on a single `client.transaction()`.

## Why

Every other custody writer in
`database/conversation_finalization_jobs.py` (claim, complete, fence,
fanout, retry, dead-letter, intent, replay-sweep writers) rides the shared
bounded contention budget; this yield was the one bare invocation left in
the file. The yield rewrites the same hot job document the budgeted writers
contend on, so a read-time `Aborted` exactly when the yield fires was a
routine event — and because the yield ran outside the budget, that abort
escaped as a raw SDK error from the losing processor's finalization attempt.
The redispatch a fresh transaction would have landed was lost with the
attempt: the job stayed leased on a row whose content revision had already
moved on, the finalization attempt failed wholesale instead of ending in the
clean `deferred` disposition, and the row waited for the reconciler to
recover it. Contention on the shared document therefore amplified itself
into failed sessions instead of backing off.

The enrolled boundary replays a replayable abort (including expired-chain
retirements) on a fresh transaction; the attempt cap surfaces as the typed
`FirestoreContentionExhausted` the finalization lane already handles, and an
ambient `transaction_retry_deadline_scope` bounds the chain exactly like it
bounds every sibling writer.

## Shape

The direct-transactional shape matches the sibling yield writer
`defer_finalization_replay`: the transactional body runs as the budget's
operation, one fresh transaction per outer attempt, with no inner restart
ladder. Expired-transaction retirements replay at the outer budget layer,
which owns tighter bounds than an inner ladder would (three fresh chains
without a wall-clock budget, the attempt cap with one). The gate walk and
the written yield document inside `_defer_sync_revision_fence_txn` are
unchanged.

## Tests

- `tests/unit/test_sync_revision_defer_budget_enrollment.py` — enrollment
  behavior; the contention, expiry and deadline tests fail against the
  bare-transactional parent.
- `tests/unit/sync_revision_defer_budget_grid_harness.py` +
  `tests/unit/test_sync_defer_budget_grid_*.py` — cross-verified grids:
  the full job-row x conversation-row gate matrix under clean and
  contention-recovery contexts, identity-gate x fault-program sweeps, the
  exact yield-document shape across knob values, budget fault programs x
  attempt caps, deadline reserve-gate and sleep-refusal walks, and
  expired-chain ceiling semantics.

Failure-Class: FC-sync-revision-yield-commit-runs-outside-the-shared-contention-budget
