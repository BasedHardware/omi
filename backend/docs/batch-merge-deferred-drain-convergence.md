# Deferred publication-drain convergence: a lost ordered merge converges on a bounded lane

`event=batch_merge outcome=retry exception_type=FirestoreContentionExhausted`
burned at the publication boundary because the pump swallowed a failed ordered
drain and left convergence to an incidental later drain: a sibling's next
publication for the same owner, or the leader-gated maintenance ready page one
or more sweeps later. An owner whose last results raced a hot document — the
common shape is one long recording whose final segments commit into a
contention wave — sat merged-but-unprojected until one of those coincidences
happened, and the only trace was one ERROR line per failed drain with no
retry attribution, no attempt budget, and no convergence proof.

Failure-Class: FC-publication-drain-contention-exhaustion-left-without-a-convergence-owner

## What changed

- `utils/batch_pipeline/pump.py` gains a deferred publication-drain lane.
  When `_drain_after_publication` catches a failed ordered drain, it arms the
  owner in a bounded ledger (`DRAIN_RETRY_LEDGER_CAP` entries,
  oldest-armed-first eviction) and a lane task wakes at the earliest armed due
  time to re-drain it. The lane exists only while the ledger is non-empty.
- The re-drain schedule is bounded exponential backoff
  (`deferred_drain_delay`): 0.5s, 1s, 2s, 4s, then 8s capped, at most
  `DRAIN_RETRY_MAX_ATTEMPTS` armed re-drains per owner per episode. The
  attempt budget is carried forward across catch sites — repeated losses
  converge on one budget instead of resetting it.
- A drain that ends at the 100-commit bound with the owner's log possibly
  still pending is not convergence: `drain_owner` re-offers the remainder
  immediately (no backoff — the bound, not contention, ended the drain) under
  its own smaller cap (`DRAIN_BACKLOG_CONTINUATION_ATTEMPTS`).
- `Pump.run` stops the lane and flushes every armed owner once at teardown.
  A flush loss is logged and dropped: `drain_owner` state is durable, so the
  maintenance ready page still converges the owner after restart. The lane
  also refuses to resurrect itself during loop teardown.
- Logging taxonomy: an armed deferral logs INFO
  `event=batch_merge_drain outcome=deferred exception_type=...`; a converged
  re-drain logs INFO `event=batch_merge_drain outcome=converged attempt=...`;
  when the attempt cap refuses to re-arm, the loss reports on its honest
  channel: a contention loss — the storm-shaped case the lane exists to
  absorb — logs WARNING
  `event=batch_merge_drain outcome=maintenance_backstop attempt=... cap=...
  retry_after_ms=...[ operation=...] exception_type=...` because the handoff
  to the maintenance-sweep backstop is the designed recovery, not a fault;
  a non-contention fault keeps the historical ERROR
  `event=batch_merge outcome=retry exception_type=...` line byte-for-byte.
- Storm-window alignment: when a drained chain loses to contention,
  `FirestoreStore.run` stamps the retry-after its storm damper actually
  armed for the drain's label onto the raised
  `FirestoreContentionExhausted.retry_after` (0.0 when no damper ran). A
  re-arm that carries that signal waits out the measured window first —
  `due_at = now + max(documented backoff step, retry_after)` — instead of
  re-striking on the fixed ladder while the damper window is still armed.
  Without it every lane attempt collided inside the armed window: the
  consult in `store.run` delayed it, the chain burned all five attempts
  against the same hot document, and the lockstep burn repeated until the
  six-attempt budget died and the ERROR line fired. The signal never
  changes the budget or its ceiling: the retry-after is clamped to
  `DRAIN_RETRY_MAX_SECONDS`, a non-contention loss or a foreign exception
  keeps the legacy schedule, and a continuation re-offer whose drain lost
  to contention aligns the same way (the cap-exhausted contention handoff
  reports `event=batch_merge_drain outcome=maintenance_backstop`; only a
  non-contention fault still books the historical
  `event=batch_merge outcome=retry` ERROR).

  Failure-Class: FC-deferred-drain-restrike-collides-inside-the-armed-storm-window

## The cap-exhausted handoff reports on its honest channel

Before this change a drain that spent its whole budget inside one storm
booked the contention twice on the ERROR fault channel: the retry engine's
`firestore_transaction_contention ... outcome=exhausted` signal when the
chain died, and the lane's own `event=batch_merge outcome=retry` line at
the cap. The pull lane's reporting already fixed the same double-booking
for pull storms. The drain lane's cap terminal now reports the designed
handoff at WARNING with the diagnostics the old line never carried: the
spent attempt, the lane cap (6 re-drains, 4 for a continuation), the storm
window the store's damper last armed (`retry_after_ms`), the losing store
operation label when one was stamped and validates, and the exception
type. The teardown flush's last re-offer follows the same split. A storm
shifts WHEN convergence lands (the sweep), never whether it
lands: the durable backstop is unchanged, no flag gates the report, and
non-contention faults keep the historical ERROR line byte-for-byte.

Failure-Class: FC-drain-cap-storm-handoff-booked-as-production-error

## What did not change

- `drain_owner` still raises to its callers; the maintenance held re-offer,
  ready page and marked-marker paths keep their own catch-and-continue
  contracts. The lane never widens publication ordering: re-drains go through
  the same per-owner serial lock, so commits stay strictly capture-ordered.
- No feature flag: the lane is a bounded robustness property of the pump, not
  a rollout lever. Its budgets are module constants, so retuning them is a
  reviewed code change.

## Boundary notes

- A cancelled lane keeps its armed owners: cancellation re-arms the popped
  entry before propagating, so nothing is lost between the ledger pop and the
  drain.
- The armed-owner ledger is bounded by count, not by owner; a storm cannot
  grow pump state without bound. An evicted owner keeps its durable
  `result_ready` rows, and the maintenance ready page remains its convergence
  path — the lane is an accelerator in front of the durable backstop, never a
  replacement for it.

## Carried suite repair

While landing this change the full unit lane failed on
`tests/unit/test_flag_budget.py` for reasons upstream of it: the
`SYNC_BACKFILL_WORKER_API_URL` / `SYNC_BACKFILL_WORKER_AUDIENCE` budget
exceptions (owner `infracost / syncsplit`) carried `review_by: 2026-11-09`,
and the gate compares against the UTC date, so every run after 19:00 EST on
2026-11-09 failed the suite on the parent commit itself. Both names are live
(running sync-split runtime reads them), so per ADR-0006 the entries were
renewed one month to `2026-12-09` rather than deleted. No env surface change:
`budget` and the seeded/replacement slot count are untouched.
