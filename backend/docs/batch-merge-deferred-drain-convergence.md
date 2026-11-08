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
  the historical ERROR `event=batch_merge outcome=retry exception_type=...`
  line remains only when the attempt cap refuses to re-arm — the
  maintenance-sweep backstop takes over from there.

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
