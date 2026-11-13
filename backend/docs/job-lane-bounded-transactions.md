# Sync-backfill and conversation-job transactions ride the bounded engine

Failure-Class: FC-bare-sync-backfill-and-conversation-job-transactions-fail-on-first-contention

Twenty-four transactional entries across `sync_backfill_sequencer` (14:
owner repair, registration, retirement, claim, begin, renew, finish, worker
claim/fail, owner defer, budget-deferral note, expired release, the
release-due fence, redrive), `conversation_merge_jobs` (6: admission, claim,
renew, finish, recovery begin/finish), `conversation_processing_recovery`
(3: the admission-fence stamp and both orphan terminalizations) and
`oversized_conversation_terminal` (1) handed their bodies to the Firestore
SDK's bare transaction path.

## What burned

- The SDK's `_Transactional` wrapper replays a commit-time `Aborted` on the
  SAME transaction id (`retry_id`). Once Firestore has retired that id, the
  replay usually fails again: one hot owner/job/conversation document turned
  a single collision into a failed sync dispatch, a failed merge lifecycle
  transition, or a failed orphan sweep pass.
- A read-time `Aborted` — the contention shape Firestore actually raises on
  transactional reads — was never retried at all: it escaped each entry as an
  unclassified server error, failing the user-visible flow on the first
  collision.
- When every replay was spent, the fault surfaced as an anonymous exception
  with no label, indistinguishable in the logs from a real write failure.

## What changed

Every entry now runs through `database.bounded_lane_transaction.
run_bounded_lane_transaction` — the same doctrine the Chat-first and
candidate-outbox lanes adopted: five fresh single-commit transactions per
chain, equal-jitter rungs between attempts, replayed aborts and
expired-transaction retirements, single-shot foreign refusals, and a typed,
per-entry-labeled `FirestoreContentionExhausted` whose lane marker
(`event=<flow>_contention_exhausted`) lands on the driving module's logger.
Static operation labels per flow (`sync_backfill_*`, `merge_job_*`,
`processing_recovery_*`, `oversized_in_progress_terminal`) make every
residual exhaustion attributable.

A fresh transaction is a safe replay: every joined body re-reads its
documents inside the transaction and keeps its fencing checks inside the same
atomic scope, so an aborted or expired chain that wrote nothing can be
replayed without double effects. Foreign refusals (a sequencing fence miss, a
`NotFound` on a concurrently deleted owner, a stale-epoch mismatch) are never
contention: they pass through single-shot exactly as before, and the
entries' existing `except NotFound` handlers are unchanged.

The read-only diagnostics keep their legacy mints byte-for-byte: dry-run
owner repair (`client.transaction(read_only=True)`), the waiting sample and
preparation snapshots, and the non-transactional reads. Only write-bearing
entries — plus the release-due fence, whose read-time abort protection is the
point — join the lane.

## Verification

- 24 site-join tests (`test_job_lane_transaction_joins.py`) drive each real
  entry against a client whose transactional operations all abort: on the
  joined tree they raise the typed, labeled exhaustion after five fresh
  transactions; on the pre-join tree they fail with the raw `Aborted` fault.
- 24 grid files × 3,780 cells cross-verified cell by cell at emit time
  against an independent model walk of the engine's documented accounting
  (fresh-transaction-per-attempt, equal-jitter rungs at the pinned draw,
  deadline reserve and never-past-deadline rules, the no-deadline
  expired-chain ceiling), each cell re-driven at suite time against the
  frozen observable literal.
- Existing per-module suites stayed green (sequencer, merge jobs, oversized
  close, orphan terminalization).
