"""Owners, deadlines and attempt budgets for the batch and sync backlog paths.

Every non-terminal backlog state names one owner, one deadline and one counter.
The table lives in ``backend/docs/runbooks/backlog-state-machine.md``.

Each class has its own switch in config/policy/kill_switches.py, parsed
literally (``true`` is on, anything else is off, unset is the registered
default). Defaults follow the lead2 rule (64b2fa): ON only where a class just
cuts wasted work or retries, OFF where it changes custody, settle or expiry
semantics. Turning a switch off restores the exact pre-change transition.

- ``CAPTURE_RETRY_CAP_ENFORCED`` (class 1, default OFF): retry caps end work
  (retained quarantine or fenced failure) for every uid, not only the
  CAPTURE_COVERAGE_MODE serve cohort.
- ``SYNC_DISPATCH_ATTEMPT_CARRY_ENABLED`` (class 2): a running sync lease
  expiry keeps counting ``dispatch_attempt`` instead of resetting it to zero.
- ``BATCH_HELD_REDRIVE_BUDGET_ENABLED`` (classes 3 and 6): a held/dead-letter
  requeue grants a fresh attempt budget, counts the re-drive, and automatic
  re-drive stops after ``MAX_HELD_REDRIVES``.
- ``BATCH_HELD_REDRIVE_COUNTER_ENABLED`` (class 6 counter, default ON): count
  held re-drives (``held_redrives``) and projection re-arms
  (``held_expired_rearms``) and report units whose budget is spent. Counting
  and the alert only; no state change.
- ``BATCH_HELD_REDRIVE_TERMINAL_STOP_ENABLED`` (class 6 terminal stop, default
  OFF): automatic re-drive stops after ``MAX_HELD_REDRIVES`` (retained
  ``held_exhausted``), status polls stop redriving retained held dead letters,
  and projection expiry stops re-arming after ``MAX_PROJECTION_REARMS``. Off
  restores the unbounded loop, including for units already marked exhausted.
- ``RECORD_PENDING_BARRIER_DEAD_LETTER_ENABLED`` (class 4): an aged
  record_pending row whose conversation exists but never completed is
  re-driven weekly with a counter, then parked as a retained dead letter.
- ``BATCH_ASSIGNMENT_HOLD_ESCALATION_ENABLED`` (class 5): an unrestorable
  assignment hold gets a deadline and then a retained escalation marker.

None of these transitions deletes audio, results, custody tokens or privacy
fences.
"""

from config.policy.kill_switches import kill_switch

RETRY_CAP_SWITCH = 'CAPTURE_RETRY_CAP_ENFORCED'
SYNC_ATTEMPT_CARRY_SWITCH = 'SYNC_DISPATCH_ATTEMPT_CARRY_ENABLED'
HELD_REDRIVE_BUDGET_SWITCH = 'BATCH_HELD_REDRIVE_BUDGET_ENABLED'
HELD_REDRIVE_COUNTER_SWITCH = 'BATCH_HELD_REDRIVE_COUNTER_ENABLED'
HELD_REDRIVE_STOP_SWITCH = 'BATCH_HELD_REDRIVE_TERMINAL_STOP_ENABLED'
RECORD_BARRIER_DEAD_LETTER_SWITCH = 'RECORD_PENDING_BARRIER_DEAD_LETTER_ENABLED'
ASSIGNMENT_HOLD_ESCALATION_SWITCH = 'BATCH_ASSIGNMENT_HOLD_ESCALATION_ENABLED'

# Automatic held re-drives per unit. Each grants a full scheduler attempt
# budget, so a unit gets (MAX_HELD_REDRIVES + 1) budgets before it stops.
MAX_HELD_REDRIVES = 3
HELD_EXHAUSTED_REASON = 'held_exhausted'
# Retained dead letters: content kept, no automatic step pending (held_exhausted
# is held_expired after the automatic re-drive budget is spent).
RETAINED_DEAD_REASONS = frozenset({'held_expired', HELD_EXHAUSTED_REASON})

# Projection receipts: how many times expiry may re-arm the release budget.
MAX_PROJECTION_REARMS = 3

# A record_pending row whose conversation exists but is not completed after
# this age leaves the fast barrier retry ladder. 14 days matches the BYOK
# abandonment bound and is far beyond any live capture lifetime.
RECORD_BARRIER_DEAD_LETTER_AGE_SECONDS = 14 * 86400
RECORD_BARRIER_REDRIVE_SECONDS = 7 * 86400
MAX_RECORD_BARRIER_REDRIVES = 4
# Parked rows stay record_pending (merge order, seal repair, erasure and the
# missing-conversation cancel all key on that state). They are not admitted
# again until an operator requeues them or the switch is turned off.
RECORD_BARRIER_DEAD_LETTER_REASON = 'conversation_not_completed'
# A parked row is due again after this long. With the switch on it is only
# re-parked (no admission); with the switch off it returns to the ladder, so
# a rollback never strands parked rows behind a far-future available_at.
RECORD_BARRIER_PARK_RECHECK_SECONDS = 86400

# An assignment hold whose target never becomes restorable escalates (a parking
# marker; the obligation, receipt and audio stay) after this long.
ASSIGNMENT_HOLD_DEADLINE_SECONDS = 7 * 86400
ASSIGNMENT_HOLD_ESCALATION_REASON = 'target_unrestorable'


def retry_cap_enforced() -> bool:
    return kill_switch(RETRY_CAP_SWITCH)


def sync_attempt_carry_enabled() -> bool:
    return kill_switch(SYNC_ATTEMPT_CARRY_SWITCH)


def held_redrive_budget_enabled() -> bool:
    return kill_switch(HELD_REDRIVE_BUDGET_SWITCH)


def record_barrier_dead_letter_enabled() -> bool:
    return kill_switch(RECORD_BARRIER_DEAD_LETTER_SWITCH)


def assignment_hold_escalation_enabled() -> bool:
    return kill_switch(ASSIGNMENT_HOLD_ESCALATION_SWITCH)


def held_redrive_counter_enabled() -> bool:
    return kill_switch(HELD_REDRIVE_COUNTER_SWITCH)


def held_redrive_stop_enabled() -> bool:
    return kill_switch(HELD_REDRIVE_STOP_SWITCH)
