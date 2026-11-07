# Batch admission: rejoin fairness seed reads the frontier as an advisory hint

Status: shipped on the batch record lane. Owner: batch record lane / rollout lead.

## What problem this solves

Every batch job a shard wins adds virtual service to that shard's control
document (`p{N}_service += cost / owner_count` in the pull transaction), so the
max-service control document is — by construction — the hottest document in the
control collection: every lease of the currently busiest shard rewrites it.

Whenever a shard's ring drains empty, the sweep marks its priority inactive
(`active = bool(ring)`); the next append for that owner — a fresh admission, a
retry requeue, a recovery restore, a dead redrive — reactivates the shard, and
`control.activate` used to seed its service credit with
`tx.service_frontier(priority)`: an indexed query **inside the caller's
transaction** ordered by `p{N}_service` descending, limit 1. That query reads
exactly the argmax document above, so every rejoining admission joined the
hottest abort set in the fleet for a value it only uses as a fairness seed. Any
concurrent lease of the busiest shard aborted the rejoin; five attempts later
the admission had burned its whole budget:

```
firestore_transaction_contention operation=... attempt=5/5 outcome=exhausted
event=batch_merge outcome=retry exception_type=FirestoreContentionExhausted
```

That signature family (x1744 + x932 + x159 + x59 per 30-minute window in the
Loop S prod-log sensor at this writing) is the largest worker error class, and
rejoin waves fire precisely when contention is worst: under load, shards churn
between empty and non-empty constantly. Prior lanes in this family removed
adjacent joins — the queue FIFO link (the queue document as ordering
authority), advisory probes for the merge head, per-operation attribution and
the storm damper. This closes the last transactional read against the control
collection's hottest document.

Failure-Class: FC-rejoin-frontier-seed-read-joins-the-argmax-shard-abort-set

## Design

The frontier seed moves to the store's advisory-probe family, exactly like
`head_pending`, `longest_ready_pending` and `fresh_pending` before it:

- `database/batch_pipeline_store.py` retires the transactional
  `Transaction.service_frontier` (and its Postgres twin) and gains the
  non-transactional `FirestoreStore.service_frontier_hint(priority)` — same
  collection, same `p{N}_service` descending order, same limit 1, no
  transaction binding, therefore no query lock and no abort-set membership.
- `utils/batch_pipeline/scheduler.py` gains `rejoin_frontiers(store,
  priorities)`: one map per entry point, read **before** `store.run`, degraded
  to `0.0` with an `event=batch_frontier_hint outcome=degraded` warning when a
  read fails. The seed must never fail admission; it is a fairness bias.
- `control.activate(tx, control, priority, now, frontier)` seeds
  `max(own, frontier)` from the passed hint. Every append entry point threads
  the seed: `Scheduler.enqueue`, `enqueue_in_transaction` (via `admit`'s
  `frontiers` map from upload admission), the recover sweep's legacy migration
  and retry requeues, `redrive_dead` (probe-gated on the row's priority), the
  artifact-missing restore, and the intake status redrive (probe-gated on an
  incomplete ledger so completed polls pay nothing).

### Why a stale seed is safe

The seed is advisory by construction — it never authorizes, gates, orders or
bills anything:

- Hint too **low** (frontier grew between the hint read and the commit): the
  rejoining shard starts slightly under-served and wins a few extra fairness
  scans until its service catches up. Bounded by the leases it actually wins;
  self-correcting within one scheduling round.
- Hint too **high** (credit retired since the read): the shard starts slightly
  over-served and loses scans until the fleet catches up. Same bound.
- Read **failed**: `rejoin_frontiers` degrades to `0.0` — the empty-collection
  seed — and logs. Admission proceeds; the next rejoin re-reads.
- Empty collection: `0.0`, identical to the previous query's empty result.

Custody, ordering, privacy and admission fences all live in the same
transaction body as before and re-verify everything they act on; only the
fairness seed's read left the transaction.

## Rollout

No flag. The change is observable-only through scheduling fairness and the
removed query; the probe-family precedent (`head_pending`, t267) shipped the
same way. Kill switches for the surrounding contention machinery
(`BATCH_PIPELINE_CONTENTION_RETRY_ENABLED`,
`BATCH_PIPELINE_CONTENTION_STORM_DAMPER_ENABLED`) are unchanged.

## In-tree migration

- `database/batch_pipeline_store.py`: `Transaction.service_frontier` removed
  from the Protocol and `FirestoreTransaction`; `service_frontier_hint` added
  to the `Store` Protocol and `FirestoreStore`; module function renamed
  `service_frontier_hint` (non-transactional).
- `database/jobstore/postgres_store.py`: `PostgresTransaction.service_frontier`
  removed; `service_frontier_hint` / `service_frontier_hint_in` added (same
  max-over-rows SQL, read outside any transaction).
- `utils/batch_pipeline/control.py`: `activate` and `migrate_legacy` take the
  seed instead of reading it.
- `utils/batch_pipeline/scheduler.py`: `rejoin_frontiers` helper; `_append` /
  `_append_fifo_array` carry the seed; entry points pre-read it; the
  `_OwnWrites` passthrough for the retired transactional read is gone.
- `database/batch_pipeline_intake.py` (`admit` accepts `frontiers`),
  `utils/batch_pipeline/intake.py` (`accept_upload`, `durable_status`),
  `database/batch_pipeline_artifact_missing.py` (`restore_reupload`).
- Simulators: `testing/pipeline_sim/store.py`, `testing/pipeline_sim/
  postgres_store.py`; conformance harness moved to the store-level hint.
- Query driver registry: `database.batch_pipeline_store.service_frontier_hint`
  replaces the retired transactional driver and its covered-by entry.
