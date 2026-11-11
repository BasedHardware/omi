# Storm-alignment family parity: every contention re-offer lands after the measured window

## What broke

The batch pipeline's production ERROR family —

- `ERROR:database.firestore_transaction_retry:firestore_transaction_contention operation=batch_pipeline_store attempt=5/5 outcome=exhausted`
- `ERROR:utils.batch_pipeline.pump:event=batch_merge outcome=retry exception_type=FirestoreContentionExhausted`
- `ERROR:utils.batch_pipeline.pump:event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted`

— is one failure class: a lane re-offers work after a contention loss while
the store's storm damper has just armed a window for that exact label. The
damper spaces the five in-chain attempts; but the LANE-level re-offer ran
on its own bare ladder (`0.5s` deferred re-offers, `0.25/0.5/1.0s`
publication re-strikes), which lands INSIDE the armed window: the entry
consult parks the lane's db-executor thread on the residual sleep, and a
chain that still loses re-arms the very storm the lane just re-entered.
Each collision burns a full five-attempt chain and books an
`outcome=retry` ERROR line, once per lane attempt until the budget dies.

The publication re-strike lane (`Pump._restrike_publication`) was the last
sub-second lane that still discarded the stamped window
(`error.retry_after`, set by `FirestoreStore.run`). The deferred-drain lane
already aligned through `contention_retry_after`; the re-strike did not.

## The fix

- `utils/batch_pipeline/pump.py`: the re-strike lane now waits
  `max(ladder step, min(measured window, storm cap))` at every attempt.
  The shared `_contention_storm_after` helper reads the stamped window
  once; `publication_restrike_storm_after` clamps it to the store damper's
  window cap (4.0s). A storm shifts WHEN the replay lands, never the
  attempt budget; a mid-lane re-exhaustion re-aims the next wait at the
  freshly armed window; every hostile payload keeps the documented ladder.
- `database/jobstore/postgres_store.py`: the postgres jobstore raised
  `JobStoreContentionExhausted` (a `FirestoreContentionExhausted`
  subclass the same pump lanes catch) with the default `retry_after=0.0` —
  the jitter window its chain applied died with the chain, so the next
  lane-level re-offer fired blind into the same conflicting row. It now
  stamps the inter-attempt window it actually applied, the same contract
  `FirestoreStore.run` follows.
- `scripts/scan_storm_alignment.py` (new): an AST parity scanner over the
  whole contention family (every `utils/batch_pipeline` module, the store,
  the retry engine, the postgres jobstore). A finding is a function that
  catches/classifies/raises a contention exhaustion AND waits without
  consuming the measured window (alignment helper call, `retry_after`
  reference, or the retry engine's `inter_attempt_gate`). Cadence-aligned
  sweeps — catch, log, continue with no in-function wait — stay clean by
  construction. `--ablate` rewrites the alignment helper names to dead
  `__dealigned` forms and rescans; the landed tree must flag exactly the
  publication re-strike lane, proving the gate sees the collision class.
- `tests/support/storm_alignment_fixture.py` +
  `tests/unit/test_storm_alignment_family_grid.py`: every family function
  (1120 across 98 modules) is pinned cell-by-cell against the scanner's
  real verdicts on this checkout — fixed posture must be family-wide
  clean; the ablated blackout must be exactly the re-strike lane. A new
  bare contention ladder anywhere in the family flips a cell red.
- `tests/unit/test_publication_restrike_storm_alignment_{contract,grid}.py`:
  the re-strike lane's wait lattice pinned as literals on the real
  `Pump._publish` path with recorded sleeps.
- `tests/unit/test_postgres_jobstore_storm_stamp.py`: the postgres stamp
  contract, including the downstream consumers
  (`contention_retry_after`, `publication_restrike_storm_after`) acting on
  the stamped window.

## Rollout and rollback

No new env, flags, migrations or clients. The pump change only shifts WHEN
an already-budgeted re-strike attempt fires (budget and ceiling unchanged);
the postgres change only populates a field consumers already read. Rollback
is reverting the two source files; the scanner and grids then report the
historical (pre-fix) posture and stay green as pure tests.

## Failure-Class

FC-publication-restrike-collides-inside-the-armed-storm-window
