"""Owners, counters and attempt budgets for the batch and sync backlog paths.

Each class has its own switch in config/policy/kill_switches.py, parsed
literally (``true`` is on, anything else is off, unset is the registered
default). Defaults follow the lead2 rule (64b2fa): ON only where a class just
cuts wasted work or retries, OFF where it changes custody, settle or expiry
semantics. Turning a switch off restores the exact pre-change transition.

- ``CAPTURE_RETRY_CAP_ENFORCED`` (class 1, default OFF): retry caps end work
  (retained quarantine or fenced failure) for every uid, not only the
  CAPTURE_COVERAGE_MODE serve cohort.

None of these transitions deletes audio, results, custody tokens or privacy
fences. See backend/docs/runbooks/backlog-state-machine.md.
"""

from config.policy.kill_switches import kill_switch

RETRY_CAP_SWITCH = 'CAPTURE_RETRY_CAP_ENFORCED'


def retry_cap_enforced() -> bool:
    return kill_switch(RETRY_CAP_SWITCH)
