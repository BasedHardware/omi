"""Owners, counters and attempt budgets for the batch and sync backlog paths.

Each class has its own switch in config/policy/kill_switches.py, parsed
with trimming and case folding: only ``true`` is on; other set values fail
closed, and unset is the registered default. Defaults follow the lead2 rule (64b2fa): ON only where a class just
cuts wasted work or retries, OFF where it changes custody, settle or expiry
semantics. Class 1/3 rollback stops new enforcement/resets; telemetry rollback preserves custody.

- ``CAPTURE_RETRY_CAP_ENFORCED`` (class 1, default OFF): the batch lease-expiry
  retry cap ends work (retained quarantine) for every uid, not only the
  CAPTURE_COVERAGE_MODE serve cohort. The sync path is main's, unchanged.
- ``BATCH_HELD_REDRIVE_COUNTER_ENABLED`` (class 6 counter, default ON): report the first committed re-drive after a unit spends its budget. Durable
  ``held_redrives`` accounting is always active, independent of this switch.
- ``BATCH_HELD_REDRIVE_BUDGET_ENABLED`` (class 3, default OFF): a
  held/dead-letter requeue resets ``attempt`` to 0 (history in
  ``held_redrive_last_attempt``), so one re-drive gets a real attempt. Moving
  held rows back into processing with a fresh budget is a custody change. It
  takes effect only while the unit has
  fewer than MAX_HELD_REDRIVES re-drives, so fresh budgets are bounded and a
  newly spent unit is alerted when telemetry is on; the terminal stop is not in core. It also takes effect
  only where the batch retry cap enforces for the owner (class 1 on, or the
  owner in the served CAPTURE_COVERAGE_MODE cohort): elsewhere a lease expiry
  only defers, so a fresh budget would loop unalerted, and main's behavior is kept.

None of these transitions deletes audio, results, custody tokens or privacy
fences. See backend/docs/runbooks/backlog-state-machine.md.
"""

from config.policy.kill_switches import kill_switch

RETRY_CAP_SWITCH = 'CAPTURE_RETRY_CAP_ENFORCED'
HELD_REDRIVE_COUNTER_SWITCH = 'BATCH_HELD_REDRIVE_COUNTER_ENABLED'
HELD_REDRIVE_BUDGET_SWITCH = 'BATCH_HELD_REDRIVE_BUDGET_ENABLED'

# Automatic held re-drives per unit before the counter reports a spent budget.
MAX_HELD_REDRIVES = 3


def retry_cap_enforced() -> bool:
    return kill_switch(RETRY_CAP_SWITCH)


def held_redrive_counter_enabled() -> bool:
    return kill_switch(HELD_REDRIVE_COUNTER_SWITCH)


def held_redrive_budget_enabled() -> bool:
    return kill_switch(HELD_REDRIVE_BUDGET_SWITCH)
