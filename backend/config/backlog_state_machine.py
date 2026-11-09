"""Owners, counters and attempt budgets for the batch and sync backlog paths.

Each class has its own switch in config/policy/kill_switches.py, parsed
literally: only the exact raw value ``true`` is on (no case folding or
trimming), any other set value is off, unset is the registered default. Defaults follow the lead2 rule (64b2fa): ON only where a class just
cuts wasted work or retries, OFF where it changes custody, settle or expiry
semantics. Turning a switch off restores the exact pre-change transition.

- ``CAPTURE_RETRY_CAP_ENFORCED`` (class 1, default OFF): the batch lease-expiry
  retry cap ends work (retained quarantine) for every uid, not only the
  CAPTURE_COVERAGE_MODE serve cohort. The sync path is main's, unchanged.
- ``BATCH_HELD_REDRIVE_COUNTER_ENABLED`` (class 6 counter, default ON): count
  held re-drives (``held_redrives``) and report units whose re-drive budget is
  spent. Counting and an alert only; no state change.
- ``BATCH_HELD_REDRIVE_BUDGET_ENABLED`` (class 3, default OFF): a
  held/dead-letter requeue resets ``attempt`` to 0 (history in
  ``held_redrive_last_attempt``), so one re-drive gets a real attempt. Moving
  held rows back into processing with a fresh budget is a custody change. It
  takes effect only with the class 6 counter on and only while the unit has
  fewer than MAX_HELD_REDRIVES re-drives, so fresh budgets are bounded and a
  spent unit is alerted; the terminal stop is not in core. It also takes effect
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
    return kill_switch(HELD_REDRIVE_COUNTER_SWITCH, log=False)


def held_redrive_budget_enabled() -> bool:
    return kill_switch(HELD_REDRIVE_BUDGET_SWITCH)
