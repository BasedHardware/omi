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

Values are trimmed and case-insensitive: `true`, `TRUE` and ` true ` are on.
Every other set value (including `1`, `yes` and an empty string) fails closed
to off; unset means the default below. Defaults follow lead2's rule (64b2fa): ON only where a class just
cuts wasted work or retries, OFF where it changes custody, settle or expiry
semantics. Each switch is read per decision without restart or migration. Class 1 and 3
rollback stops new enforcement or resets; durable held accounting continues
when the telemetry switch is off.

| Switch | Default | Class | Turning it off |
| --- | --- | --- | --- |
| `CAPTURE_RETRY_CAP_ENFORCED` | OFF | 1: the cap only observed outside the serve cohort | Switching class 1 OFF stops new cap enforcement. Existing grants persist until they finish; no clawback. Each grant is capped at `MAX_ATTEMPTS` only while the retry cap enforces for the owner (class 1 on, or the owner in the served cohort). With class 1 off, lease expiries defer, as on main. |
| `BATCH_HELD_REDRIVE_BUDGET_ENABLED` | OFF | 3: requeue kept `attempt` at the cap | Switching class 3 OFF stops new budget resets. Existing grants persist until their unit runs or finishes; no clawback. Each grant is capped at `MAX_ATTEMPTS` only while the retry cap enforces for the owner (class 1 on, or the owner in the served cohort). With class 1 off, lease expiries defer, as on main. |
| `BATCH_HELD_REDRIVE_COUNTER_ENABLED` | ON | 6 (counter): held re-drives were not counted | Silences spent-budget telemetry only; durable budget accounting and class 3 custody behavior continue |

## Class 1: retry cap enforcement

With the switch on, a batch unit whose lease expires at
`BATCH_PIPELINE_MAX_ATTEMPTS` is quarantined (`quarantine_reason=worker_failed`,
`recovery_state=held`), the transition explicit worker failures already take.
The cap applies only to the batch lease-expiry cap; every other caller of
`retry_cap`, including main's sync dispatch cap, keeps the `CAPTURE_COVERAGE_MODE`
cohort decision, so this switch never changes the sync path. Alert: `omi-backlog-retry-cap-quarantine-rate`.

## Classes 3 and 6 (counter): held re-drives

Every held re-drive (nightly, operator `/requeue-quarantined`, operator
`/redrive-dead`, or status poll of a `held_expired` dead letter) uses the same
content-owner/privacy CAS and eligibility checks before accounting. Durable
`held_redrives` always increments, independent of the telemetry switch. Class 3
resets `attempt` to 0 and keeps the prior value in `held_redrive_last_attempt`
only for the first 3 re-drives, and only where the batch retry cap enforces for
the owner (class 1 on, or the served `CAPTURE_COVERAGE_MODE` cohort). The counter
switch only silences the metric; it never changes custody or replenishes grants.
`input_expiring` operator requeues and staging-input repair CAS calls consume no
held grant and grant no attempt reset. Status polls still leave `input_expiring`
terminal.

After three grants the unit keeps the retained held loop with its existing
attempt count; core has no terminal stop. On the first subsequent **committed**
re-drive, `held_redrive_budget_spent_at` is written atomically with the queue
mutation. Only that new transition emits `held_redrive_budget_spent`, after
commit and only with telemetry enabled. Today-expired rows, privacy/content
refusals, staging repairs, CAS losers and transaction retries emit nothing.
The marker is retained through later cycles and is written even while telemetry
is off, so re-enabling telemetry never replays old pages. Do not clear it as a
silencing procedure.

Malformed `held_redrives` values log the content-free
`event=batch_held_redrives_malformed` signal and restart accounting from zero on
the next verified commit. Nonnegative integral floats (for example `3.0`) are
valid and normalized to integers. Operators should investigate the writer and
repair metadata using verified history; malformed metadata alone never makes a
unit permanently spent. A pre-existing spent marker is retained.

Alerts: `omi-backlog-held-redrive-unit-looping` pages for a **new** spent
transition in the last hour; `omi-backlog-held-redrive-budget-spent` covers
volume. The page retains the live Telegram route and gate. Once the hour elapses,
later nightly cycles of that unit cannot re-fire it. Investigate the recorded
failure and retained audio before another re-drive. To silence telemetry set
`BATCH_HELD_REDRIVE_COUNTER_ENABLED=false`; to stop new budget resets separately
set `BATCH_HELD_REDRIVE_BUDGET_ENABLED=false`. Neither switch claws back grants.

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
