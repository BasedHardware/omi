# Batch merge: held owners with a ready catch-up head stop re-opening the wide hold query

The blocked-head probe gate and the revision-fenced narrow commit removed the
two loudest contention burns from the ordered-merge drain, but one
unconditional strict drain was left: an owner parked at the projection depth
cap. The pump re-drains such an owner from three directions every cycle —
after each of its unit completions, through the global `result_ready` page,
and through the marked-owner re-offer — and every one of those drains opened
the strict `batch_merge_commit` transaction whose first act is the owner's
pending query. A query-in-transaction read set is every matched row: the
documents each sibling lease heartbeat (every 20 seconds per in-flight unit)
keeps rewriting. The transaction re-concluded `held` and wrote nothing, and
under load burned its whole five-attempt ladder against the storm:

    event=batch_merge outcome=retry exception_type=FirestoreContentionExhausted
    firestore_transaction_contention operation=batch_merge_commit
    attempt=5/5 outcome=exhausted

## What changed

`OrderedMerge.commit_next` now probes before it transacts. When three
outside-transaction probes positively prove the strict body can only
re-conclude `held` — the probed head is the owner's pending catch-up row in
`result_ready`, the probed owner still sits at the projection depth cap, and
the probed durable hold marker is already set — the drain skips the
transaction and records the same held facts the body would have:
`held['over_cap']` drives the `held_owners` hint and `held['catch_up']` drives
the fresh-first probe below, so the drain's observable outcome is identical
minus the transaction.

Nothing else moves:

- A ready **fresh** head still commits past the cap through the strict body,
  and a ready fresh sibling still commits in the same skipped drain through
  the unchanged fresh-first re-verify (one transaction fewer than before).
- **Blocked** catch-up heads keep the strict re-decide: the strict body alone
  records the `blocked`/`catch_up` facts the fresh-first machinery consumes.
- Shadow heads, unmarked owners, below-cap probes, probe failures and release
  wakes keep the strict transaction as the authority. The new marker probe is
  guarded: a transient failure logs
  `event=batch_merge outcome=held_marker_probe_retry` and the strict body
  decides.
- Once projection advances below the cap, the next drain commits the head
  through the narrow body, `release_hold` clears the marker, and the
  marked-owner re-offer restores the normal drain — the skip changes no
  liveness property, only removes a transaction that could only write
  nothing.

## Rollout

`BATCH_PIPELINE_MERGE_HELD_HEAD_GATE_ENABLED` (default on, registered in
`config/flag_budget.json`). `false` is the kill switch and restores the
strict re-decide for every held-owner drain.

Failure-Class: FC-held-owner-ready-catch-up-drains-reopen-the-wide-hold-query
