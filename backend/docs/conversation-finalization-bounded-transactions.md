# Conversation-finalization transactions ride the bounded lane runner

Failure-Class: FC-finalization-transaction-attempts-replay-one-retired-id-five-times

Twenty-seven transactional entries in `conversation_finalization_jobs` (the
Cloud Tasks `conversation-finalization` lane behind conversation completion)
already handed their bodies to the bounded contention engine — five outer
attempts, equal-jitter rungs, replayed aborts and expired-transaction
retirements — but they handed it the Firestore SDK's DEFAULT transaction
factory (`client.transaction`, max_attempts unset).

## What burned

- Every outer attempt minted a transaction whose own commit loop replays a
  commit-time `Aborted` on the SAME transaction id up to five times. Against
  the hot job, receipt and recovery-state rows a single collision therefore
  spent a 5×5 grid of commit replays inside one contention wave: the chain's
  wall-clock budget and its jitter spacing were sized for five bodies, not
  twenty-five same-id strikes, and the chain exhausted
  (`attempt=5/5 outcome=exhausted`) while the wave was still live.
- The same-id replay is exactly the shape that cannot survive a retired
  transaction id: a commit that comes back
  `400 The referenced transaction has expired or is no longer valid` was
  replayed four more times on the same retired id before the chain gave up.
- Exhaustion surfaced on the generic engine channel with no flow identity
  beyond the operation label, and the lane's own exhaustion marker
  (`event=<flow>_contention_exhausted`) never fired.

## What changed

Every entry now runs through
`database.bounded_lane_transaction.run_bounded_lane_transaction` — the same
doctrine the Chat-first, candidate-outbox and job-lane families adopted: five
fresh single-commit transactions per chain, equal-jitter rungs between
attempts, replayed aborts and expired-transaction retirements, single-shot
foreign refusals, and a typed, per-entry-labeled
`FirestoreContentionExhausted` whose lane marker
(`event=<flow>_contention_exhausted`) lands on the lane channel. The static
per-entry operation labels (`conversation_finalization_intent`,
`finalization_worker_claim`, `finalization_complete`,
`finalization_fanout_*`, `finalization_dead_letter`,
`meeting_receipt_*`, `finalization_replay_*`, the sweep-cursor advances,
`processing_admission_stamp`, the orphan terminals,
`deferred_processing_reacquire`, `recover_deferred_processing_failure`,
`byok_resume_for_live_session`, `abandon_byok_finalization_job`) are
unchanged, so dashboards grouped by operation keep their identity; the lane
marker is new, per-flow, and lands next to the engine's contention channel.

The two lambda-bodied sweep-cursor entries (`byok_reclaim_sweep_cursor`) also
pin their inner `run_transactional` restart to `attempts=1`, so the outer
chain — not an inner three-restart loop minting default transactions — owns
every attempt, per the shared runner's nesting contract.

## Semantics preserved

- The bounded engine already replayed every body on a fresh transaction for
  read-time aborts; only the commit path narrows. Aborted and expired chains
  are atomic (nothing was written) and every body re-reads its documents
  inside its transaction, so single-commit replays are safe.
- Foreign domain refusals (CAS generation mismatches, unknown jobs, blocked
  BYOK claims) still pass through single-shot on the first attempt, exactly
  as before.
- Callers catch the same `FirestoreContentionExhausted` type with the same
  message; the recovery paths (deferred re-offer, sweep continuation) are
  unchanged.

## Coverage

`tests/unit/test_finalization_lane_transaction_joins.py` drives all 27
entries against a client whose transactional reads abort, asserting five
fresh single-commit mints and the per-flow lane marker; it fails on a tree
without the join (default-mint factories, no lane marker). The generated
`test_bounded_lane_grid_cf_*` suites freeze the runner's full observable
accounting — fresh-transaction identity, ladder sleeps at the pinned jitter
draw, deadline reserve and never-past-deadline cuts, the no-deadline
expired-chain ceiling — cell by cell across every joined lane label.
