# Backlog state machine (core: classes 1, 2, 3 and the class 6 counter)

Code: `config/backlog_state_machine.py`, `utils/backlog_metrics.py`.
Tests: `tests/unit/test_backlog_state_machine.py`.
Alerts: `charts/monitoring/alerts/backlog-state-machine.json`.

Backlogs recurred because retry state machines lost their counters or never
ended work: a retry cap that only observed, a sync attempt budget reset on every
lease expiry, held re-drives that kept the attempt count at the cap, and held
re-drive loops nobody counted. Each class has its own switch. Nothing here
deletes audio, results, custody tokens or privacy fences.

## Switches

Parsed literally: `true` is on, anything else is off, and unset means the
default below. Defaults follow lead2's rule (64b2fa): ON only where a class just
cuts wasted work or retries, OFF where it changes custody, settle or expiry
semantics. Each switch is read per decision; turning it off restores the old
transition with no restart or migration, and fields written while it was on are
inert.

| Switch | Default | Class | Turning it off |
| --- | --- | --- | --- |
| `CAPTURE_RETRY_CAP_ENFORCED` | OFF | 1: the cap only observed outside the serve cohort | Batch lease-expiry and sync running caps return to the `CAPTURE_COVERAGE_MODE` cohort decision |
| `SYNC_DISPATCH_ATTEMPT_CARRY_ENABLED` | ON | 2: running lease expiry reset `dispatch_attempt` | Running expiry resets `dispatch_attempt` to 0 again and stops counting `running_expiries` |
| `BATCH_HELD_REDRIVE_BUDGET_ENABLED` | OFF | 3: requeue kept `attempt` at the cap | Requeue keeps `attempt`, so the first failure after a re-drive re-quarantines |
| `BATCH_HELD_REDRIVE_COUNTER_ENABLED` | ON | 6 (counter): held re-drives were not counted | No `held_redrives` increments and no spent-budget observation |

## Class 1: retry cap enforcement

With the switch on, a batch unit whose lease expires at
`BATCH_PIPELINE_MAX_ATTEMPTS` is quarantined (`quarantine_reason=worker_failed`,
`recovery_state=held`), the transition explicit worker failures already take.
A sync running owner whose `running_expiries + 1` reaches
`SYNC_TASKS_MAX_ATTEMPTS` is finalized by the existing fenced finalizer. That
running cap serves only with this switch on; the `CAPTURE_COVERAGE_MODE` serve
mode or cohort never turns it on. The sync dispatching-state cap keeps the
cohort decision because a passed dispatch retry deadline is queue delay, not
failure. Alert: `omi-backlog-retry-cap-quarantine-rate`.

## Class 2: running-lease attempt carry

A running lease expiry keeps the epoch bump that fences the dead worker, carries
`dispatch_attempt` as the task identity, and counts the crash in
`running_expiries` (reset at claim). An expiry while a budget deferral's
`deferred_until` marker is live is not a crash. `dispatch_attempt_base` restarts
the legacy dispatching-deadline budget at each new epoch, exactly as main's reset
did, so the carry never spends that budget. Alert: `omi-backlog-sync-running-cap-rate`
(fires only with class 1 on). With class 1 off, every running-lease expiry at or
over the cap is still redriven, never terminalized, and records
`sync_running_cap_observed` after the redrive commits. Alert:
`omi-backlog-sync-running-cap-unenforced`.

## Classes 3 and 6 (counter): held re-drives

Every held re-drive (nightly re-drive, operator requeue, operator
`/redrive-dead` or status poll of a `held_expired` dead letter) goes through one
helper:
the counter increments `held_redrives`, and class 3 resets `attempt` to 0 and keeps
the prior value in `held_redrive_last_attempt`. The nightly scan and committed
poll and `/redrive-dead` re-drives record `held_redrive_budget_spent` at or over 3 re-drives.
Alert: `omi-backlog-held-redrive-budget-spent`. There is no terminal stop in core;
it ships in the follow-up branch behind its own default-off switch.

## Metrics

`omi_backlog_state_transitions_total{transition}`: `sync_running_cap_reached`,
`sync_running_cap_observed`, `held_redrive_budget_spent`. Batch and sync cap decisions are in
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
