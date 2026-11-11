# Pull storm alignment: the shard backoff lands after the measured window

Family: the batch contention storm-alignment discipline
([storm-alignment-family-parity](storm-alignment-family-parity.md),
[deferred-drain convergence](batch-merge-deferred-drain-convergence.md),
[mid-ladder storm gate](batch-store-mid-ladder-storm-gate.md)).
Failure-Class: FC-pull-backoff-collides-inside-the-armed-storm-window

## The production error family this closes

The Loop S sensor's top signature burns on the batch store's contention
ladder:

```
ERROR:database.firestore_transaction_retry:firestore_transaction_contention operation=batch_pipeline_store attempt=5/5 outcome=exhausted
```

Every store transaction runs under a bounded five-attempt contention
ladder. When a chain exhausts, the store's storm damper arms a bounded,
jittered re-strike window for the operation's label and stamps the window
it actually armed onto the raised `FirestoreContentionExhausted.retry_after`.
The mid-ladder gate, the deferred drain, and the publication re-strike lane
all consume that measured signal. One lane did not: the scheduler's shard
pull loop — the highest-frequency transaction driver in the system, the
lane that feeds every batch worker its work.

## What the pull lane used to do

After a pull or claim chain exhausted, `Scheduler.pull` armed its
`_contention_backoff_until` deadline from a blind ladder
(`min(30.0, 2.0 ** min(failures - 1, 5))` scaled by a `[0.5, 1.0]` jitter)
and discarded the stamped window:

- When the blind delay landed **inside** the damper's armed window, the
  shard's next pull re-entered the window's interior. The store's entry
  consult parked the caller on the residual sleep, the chain burned its
  five attempts against a collision the damper had already measured, and
  losing again re-armed the very storm the shard had just paid to leave —
  the lockstep burn the damper exists to prevent, repeated per ladder rung
  until the shard's budget died.
- When the blind delay overshot, the shard idled longer than the measured
  storm actually lasted, and shards that exhausted around the same time
  re-entered in near lockstep (the jitter band is narrow relative to the
  ladder rungs).

Either way the shard fed the production exhaustion family — the anonymous
`operation=batch_pipeline_store` label of the pre-labeling deployments
aggregated every unlabeled worker-hot transaction into one storm identity,
which is exactly the signature the sensor carries.

## What changed

`utils/batch_pipeline/scheduler.py` grew two pure helpers and the handler
composes them:

- `pull_contention_storm_after(error)` reads the stamped window off the
  exhausted chain. Only a positive finite number counts; a foreign
  exception, an exhaustion with no stamp (the damper disabled), and hostile
  input all return `0.0`. The clamp is the lane's own documented horizon
  (`CONTENTION_BACKOFF_CAP_SECONDS`, 30.0s) — the store's damper caps armed
  windows at 4.0s, so every real window fits and the clamp only fences a
  hostile stamp.
- `pull_backoff_delay(failures, storm_seconds, jitter)` computes the
  documented ladder rung exactly as before and raises its floor to
  `min(storm_seconds, CONTENTION_BACKOFF_CAP_SECONDS)`. A storm shifts WHEN
  the next pull lands, never the attempt budget or its ceiling. With no
  stamped window the returned delay is byte-for-byte the old draw.

The contention ERROR line is unchanged
(`event=batch_pull outcome=backoff failures=... retry_after_ms=...`); only
the delay the line reports reflects the aligned schedule now.

## The scanner owns the arm

`scripts/scan_storm_alignment.py` (the family's parity scanner) now treats
a state-armed backoff as a wait: any assignment to a `*_backoff_until`
name that holds a non-zero value counts exactly like a `sleep` call.
Before this change the pull lane escaped the scanner because its wait is
state, not a call — the arm sat in one function and the sleep at the entry
gate of another. `pull_contention_storm_after` joined the alignment helper
set, so ablation (dealigning the helper names) flips `Scheduler.pull` to
the bare-ladder finding alongside the publication re-strike lane, and any
future arm that drops the measured window fails the family contract.

## Verification

- `tests/unit/test_pull_storm_alignment.py` pins the two helpers' exact
  semantics and the scheduler's armed state: a stamped 3.5s window with the
  jitter draw pinned to 0.0 arms `monotonic() + 3.5` where the bare ladder
  armed `+ 0.5` (the assertions fail on a tree that still draws the bare
  ladder), and the no-stamp posture is byte-identical to the old schedule.
- `tests/unit/test_pull_storm_alignment_grid.py` pins the compose matrix:
  32 ladder rungs x 27 stamp shapes x 5 jitter draws, every expected value
  a literal transcribed from the documented contract off-tree.
- `tests/unit/test_pull_storm_stamp_grid.py` pins the reader across 40
  stamp shapes x 5 error carriers.
- `tests/unit/test_pull_storm_state_grid.py` drives the real scheduler
  through 1-3 chained exhaustion losses per cell (12 stamps x 4 jitter
  draws x 3 chain depths) and pins the exact armed deadlines plus the
  in-window suppression.
- `tests/unit/test_storm_alignment_family_grid.py` pins the scanner's
  verdicts family-wide in both postures; the ablated blackout set is now
  exactly `{Pump._restrike_publication, Scheduler.pull}`.
