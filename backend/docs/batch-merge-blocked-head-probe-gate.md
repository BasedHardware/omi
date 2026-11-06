# Batch merge: blocked-head drains probe before they transact

Status: shipped on the batch record lane. Owner: batch record lane / rollout lead.

## What problem this solves

Every ordered-merge drain opens with one strict `batch_merge_commit`
transaction whose first act is a query for the owner's earliest pending row
(the head). While any capture of that owner is still in flight — the normal
state during live sessions, where workers lease and complete segments
out of order — that head is a *leased* row whose document every lease
heartbeat keeps rewriting. A transaction that reads it joins its abort set,
so every concurrent heartbeat aborts the drain:

```
firestore_transaction_contention operation=batch_merge_commit attempt=5/5 outcome=exhausted
event=batch_merge outcome=retry exception_type=FirestoreContentionExhausted
```

Those two signatures (x2239 and x998 per 30-minute window at their peak) are
the largest worker error classes in the Loop S prod-log sensor, and most of
their drains were doomed no-ops: the strict body reads the head, sees a
non-ready state, and commits nothing. The contention storm damper
(`batch-contention-storm-damper.md`) spaces out the re-strikes after an
exhaustion; it does not stop the drain from striking a hot row it provably
does not need to touch.

Failure-Class: FC-blocked-head-merge-drains-join-the-hot-row-abort-set

## Design

`OrderedMerge.commit_next` now probes the head outside any transaction
before opening the strict one:

- `Store.head_pending(owner_key)` — the non-transactional twin of the
  transactional `first_pending` query (same `owner_key`/`merge_pending`
  filters, same capture order, limit 1, no transaction, therefore no query
  lock and no abort-set membership). It joins the store's advisory probe
  family: a hint read whose consumer re-verifies everything it acts on.
- Probe says **nothing is pending** and no recovery release set is in
  flight: the strict candidate would be `None` — commit nothing, write
  nothing. The drain returns immediately; the in-memory held-owner hint is
  dropped exactly as a no-candidate strict drain does.
- Probe says the head is **`result_ready`**, or the head is a catch-up row
  while the projection depth cap is on: the strict transaction may commit
  (and the fresh-first / depth-marker logic lives inside it), so it opens
  exactly as before.
- Probe says the head is **plain blocked** (any non-ready row that fresh-first
  cannot help, e.g. a leased capture): the transaction's only possible write
  is the durable depth-cap hold marker. Probe-side twins of the body's
  `over_cap` test (`owners` + watermark result + `merge_holds` reads) decide
  whether that marker is owed. When it is, the strict transaction still runs
  — it remains the only authority that writes the marker atomically. When it
  is not (under the cap, or the marker is already durable), no transaction
  opens: the drain records the same `blocked`/`held` facts the body would
  have (`held_owners` add/discard included) and falls through to the
  unchanged downstream sections — release wakes, then the head-wait bypass,
  whose own probe-and-reverify contract already keeps transactions off the
  hot row until a commit is actually available.
- Any probe failure abandons the gate and opens the strict transaction:
  Google API errors (including missing-index `FailedPrecondition`) and any
  other probe failure alike. The probe is a hint; the transaction remains
  the authority, and the gate may only skip a transaction it has positively
  proven unnecessary, so the merge degrades to pre-gate behavior, never to
  a wrong decision.

The strict commit body, the fresh-first probe, the recovered-release path
and the head-wait bypass are byte-for-byte unchanged. The gate only decides
whether the first, strictest transaction opens at all.

## Contracts that do not change

- Ordering: strict capture order, the bounded head wait, fresh-first and
  recovered release all commit through the same body; a commit still
  re-reads its fences inside its transaction.
- Durability of the depth-cap marker: still written transactionally, only
  by the strict body. The probe twins can be briefly stale (non-transactional
  reads); an undershoot delays that marker by one drain cycle, and any
  later drain — publication, serving or maintenance re-offer — re-derives it.
- Kill switches: `BATCH_PIPELINE_CONTENTION_RETRY_ENABLED=false` still runs
  one unladdered attempt per transaction; the gate is orthogonal (it runs
  before any transaction is requested).
- Log taxonomy: the skip path adds no log lines; exhaustion, backoff and
  bypass lines keep their exact shapes and operation labels.

## Operational notes

- Expected prod effect: drains that run while an owner's earliest capture is
  in flight — the majority under live load — stop taking the five-attempt
  contention ladder against the heartbeat-hot head document. Both
  signatures above should decay to the residue that comes from genuine
  commits (ready heads racing other writers, release and bypass paths).
- Rollback: revert the gate in `utils/batch_pipeline/merge.py`; the
  `Store.head_pending` probe surface is additive and unused elsewhere.
- Suite: `backend/tests/unit/test_merge_blocked_head_probe_gate.py`
  (gate decisions, probe-failure parity, depth-marker guard, head-wait and
  release flows through the gate, hot-row abort elimination on the real
  store class, fake-store parity for the new probe).
