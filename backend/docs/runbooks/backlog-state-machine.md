# Backlog state machine (core: classes 1, 3 and the class 6 counter)

Code: `config/backlog_state_machine.py`, `utils/backlog_metrics.py`.
Tests: `tests/unit/test_backlog_state_machine.py`.
Alerts: `charts/monitoring/alerts/backlog-state-machine.json`.

Backlogs recurred because retry state machines lost their counters or never
ended work: a retry cap that only observed, held re-drives that kept the attempt
count at the cap, and held re-drive loops nobody counted. Each class has its own
switch. The sync path (class 2, the running-lease attempt carry and the
budget-deferral chain) is not in core; it ships on the follow-up branch, and
core leaves main's sync behavior unchanged. Nothing here
deletes audio, results, custody tokens or privacy fences.

## Switches

Parsed literally: only the exact value `true` is on (`TRUE`, ` true`, `1` and
`yes` are off), any other set value is off, and unset means the default below. Defaults follow lead2's rule (64b2fa): ON only where a class just
cuts wasted work or retries, OFF where it changes custody, settle or expiry
semantics. Each switch is read per decision; turning it off restores the old
transition with no restart or migration, and fields written while it was on are
inert.

| Switch | Default | Class | Turning it off |
| --- | --- | --- | --- |
| `CAPTURE_RETRY_CAP_ENFORCED` | OFF | 1: the cap only observed outside the serve cohort | The batch lease-expiry cap returns to the `CAPTURE_COVERAGE_MODE` cohort decision |
| `BATCH_HELD_REDRIVE_BUDGET_ENABLED` | OFF | 3: requeue kept `attempt` at the cap | Switching class 3 OFF stops new budget resets. Existing grants persist until their unit runs or finishes. Each grant is capped at `MAX_ATTEMPTS`. |
| `BATCH_HELD_REDRIVE_COUNTER_ENABLED` | ON | 6 (counter): held re-drives were not counted | No `held_redrives` increments and no spent-budget observation |

## Class 1: retry cap enforcement

With the switch on, a batch unit whose lease expires at
`BATCH_PIPELINE_MAX_ATTEMPTS` is quarantined (`quarantine_reason=worker_failed`,
`recovery_state=held`), the transition explicit worker failures already take.
The cap applies only to the batch lease-expiry cap; every other caller of
`retry_cap`, including main's sync dispatch cap, keeps the `CAPTURE_COVERAGE_MODE`
cohort decision, so this switch never changes the sync path. Alert: `omi-backlog-retry-cap-quarantine-rate`.

## Classes 3 and 6 (counter): held re-drives

Every held re-drive (nightly re-drive, operator requeue, operator
`/redrive-dead` or status poll of a `held_expired` dead letter) goes through one
helper:
the counter increments `held_redrives`, and class 3 resets `attempt` to 0 and keeps
the prior value in `held_redrive_last_attempt`. Class 3 takes effect only with
the counter on, only for a unit's first 3 re-drives, and only where the batch
retry cap enforces for the owner (class 1 on, or the owner in the served
`CAPTURE_COVERAGE_MODE` cohort): elsewhere lease expiries only defer, so a fresh
budget would keep the unit runnable without bound and unalerted; after that the unit
keeps main's retained held loop (attempt at the cap) and the spent-budget
signal, so a fresh budget never sustains an unbounded loop. The nightly scan and committed
poll and `/redrive-dead` re-drives record `held_redrive_budget_spent` at or over 3 re-drives.
Alerts: `omi-backlog-held-redrive-unit-looping` (one unit, last 8 days) and
`omi-backlog-held-redrive-budget-spent` (volume). The single-unit alert is a page:
it is unmuted on `Omi - Services Alerting (Telegram)` and on `live-alert-gate.json`,
because one looping unit stays under the volume threshold. There is no terminal stop in core;
it ships in the follow-up branch behind its own default-off switch.

## Metrics

`omi_backlog_state_transitions_total{transition}`: `held_redrive_budget_spent`.
Batch and sync cap decisions are in
`omi_capture_retry_cap_total{check,outcome}`. Counted once per committed
transaction, never inside a retryable callback.

## Known open items (not changed here)

- Projection re-arm gap: a restorable assignment hold with
  `projection_release_attempts >= 3` bypasses expiry (the `if attempts >=
  MAX_RELEASE_ATTEMPTS: return False` after a restorable target in
  `backend/database/batch_pipeline_projection_release.py`). Pre-existing on
  main. Main now has a fix behind the dark switch
  `BATCH_PIPELINE_PROJECTION_RESTORABLE_CAP_EXPIRY_ENABLED` (default off,
  `de0d4d34f627`); until it is on, the gap stands. This branch does not touch
  that file.
