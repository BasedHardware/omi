"""Owners, counters and attempt budgets for the batch and sync backlog paths.

Each class has its own switch in config/policy/kill_switches.py, parsed
literally (``true`` is on, anything else is off, unset is the registered
default). Defaults follow the lead2 rule (64b2fa): ON only where a class just
cuts wasted work or retries, OFF where it changes custody, settle or expiry
semantics. Turning a switch off restores the exact pre-change transition.

- ``CAPTURE_RETRY_CAP_ENFORCED`` (class 1, default OFF): retry caps end work
  (retained quarantine or fenced failure) for every uid, not only the
  CAPTURE_COVERAGE_MODE serve cohort.
- ``SYNC_DISPATCH_ATTEMPT_CARRY_ENABLED`` (class 2, default ON): a running sync
  lease expiry keeps counting ``dispatch_attempt`` (task identity) and counts
  crashes in ``running_expiries`` instead of resetting the attempt budget. The
  legacy dispatching-deadline budget restarts at each new epoch through
  ``dispatch_attempt_base``, as on main.
- ``BATCH_HELD_REDRIVE_COUNTER_ENABLED`` (class 6 counter, default ON): count
  held re-drives (``held_redrives``) and report units whose re-drive budget is
  spent. Counting and an alert only; no state change.

None of these transitions deletes audio, results, custody tokens or privacy
fences. See backend/docs/runbooks/backlog-state-machine.md.
"""

from config.policy.kill_switches import kill_switch

RETRY_CAP_SWITCH = 'CAPTURE_RETRY_CAP_ENFORCED'
SYNC_ATTEMPT_CARRY_SWITCH = 'SYNC_DISPATCH_ATTEMPT_CARRY_ENABLED'
HELD_REDRIVE_COUNTER_SWITCH = 'BATCH_HELD_REDRIVE_COUNTER_ENABLED'

# Automatic held re-drives per unit before the counter reports a spent budget.
MAX_HELD_REDRIVES = 3


def retry_cap_enforced() -> bool:
    return kill_switch(RETRY_CAP_SWITCH)


def sync_attempt_carry_enabled() -> bool:
    return kill_switch(SYNC_ATTEMPT_CARRY_SWITCH)


def held_redrive_counter_enabled() -> bool:
    return kill_switch(HELD_REDRIVE_COUNTER_SWITCH)
