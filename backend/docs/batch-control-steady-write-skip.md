# Batch control steady-write skip: warm admissions stop writing the control document

`firestore_transaction_contention operation=batch_pipeline_store attempt=5/5
outcome=exhausted` burns because the scheduler's append path still carried the
owner's control document inside every admission transaction's write set. The
landed fixes removed the other members one at a time — the tail unit's
lifecycle-hot document (fifo array link), the sibling anchor staging (anchor
stage pins), the merge commit query range (narrow revision-fenced commit) —
and the storm damper spaces whatever collisions remain. The last standing
member was the append's own control write, and it was content-free: on the
warm path (queue already in the owner's ring, priority already active, both
availability floors at or below the arriving job's `available_at`)
`control.activate` changes no value and the ring membership does not change,
so the `tx.put('control', ...)` that followed wrote byte-identical bytes and
existed only to join the abort set. An owner's sibling admission burst — the
intake of one long recording splits into dozens of units — means N
transactions each holding the hottest per-owner document, N-1 aborts per
round, and the shared five-attempt budget spent before any of them commits.

Failure-Class: FC-control-document-carries-content-free-append-writes

## What changed

- `utils/batch_pipeline/control.py` gains `activation_surface`: a value
  snapshot of exactly the fields the append path can change on the control
  document — the priority's ring membership and length, `active`, the cold
  `service` seed, and the `batch`/`live` availability floors. It is pure over
  its input and injects nothing.
- `utils/batch_pipeline/scheduler.py` (`_append` and `_append_fifo_array`)
  snapshot the surface before their mutations and write the control document
  only when the surface changed. A cold activation (first unit of an owner or
  of a priority: ring membership, `active` flip, frontier seed) writes
  byte-for-byte as before; a lower availability floor or a fresh frontier
  seed writes; a warm admission skips the write entirely. The queue document,
  job document and owner revision writes are untouched.
- `config/batch_pipeline.py` gates the skip behind
  `BATCH_PIPELINE_CONTROL_STEADY_WRITE_SKIP_ENABLED` (default on; `false`
  restores the unconditional write), registered in `config/flag_budget.json`.

## What does not change

- The pull's service advance still writes control per granted lease — that is
  the scheduler's own serialization point and a real change every time.
- Migration (`migrate_legacy`) keeps its existing conditional write.
- Transition paths (defer, release, quarantine, recover, heartbeat, complete)
  never wrote control and still do not.
- When the write happens, the control content is byte-identical to the
  unconditional path — proven by paired-stream equivalence tests
  (`tests/unit/test_control_steady_write_skip_*`).

## How the skip is decided

The append computes `before = activation_surface(control, priority,
queue_key)`, performs its ring/queue mutations, calls `activate`, and writes
only if `not control_steady_write_skip_enabled() or
activation_surface(...) != before`. The kill switch forces the write on every
append. Snapshot fields that never move on the warm path (the floors are
`min`-clamped at their 0.0 seed, service is seeded once at the cold frontier)
are still observed, so a future change that makes activation mutate them
flips the decision with no test changes.

## Verification

- Write-ledger tests pin the exact put ledger per admission shape: warm array
  append `[queues, jobs, owners]`, cold append `[control, queues, jobs,
  owners]`, kill-switch warm `[control, queues, jobs, owners]`.
- Paired-stream equivalence: for N from 1 to 30, a skip stream and a
  kill-switch stream end with identical control, queue, job and owner
  documents while the skip stream carries exactly one control write.
- The value grid pins `activation_surface` cell by cell, including the
  purity, missing-field and other-priority independence contracts.
