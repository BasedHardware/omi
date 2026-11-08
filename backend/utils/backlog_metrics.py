"""Terminal and re-drive transitions of the backlog state machine.

One static-label counter, so each kill switch in config/backlog_state_machine.py
has a rate the agent-tier alerts in charts/monitoring/alerts/backlog-state-machine.json
can read. Labels are a closed set; no uid, segment or conversation identity.
"""

import logging

from prometheus_client import Counter

logger = logging.getLogger(__name__)

TRANSITIONS = (
    # A held unit whose automatic re-drive budget is spent (dead/held_exhausted).
    'held_exhausted',
    # A projection receipt whose expiry may no longer re-arm its release budget.
    'projection_rearm_exhausted',
    # An aged record_pending row with an unfinished conversation re-driven weekly.
    'record_barrier_redrive',
    # The same row parked as a retained dead letter after its last re-drive.
    'record_barrier_dead_letter',
    # A running sync job whose carried dispatch attempts reached the cap.
    'sync_running_cap_reached',
    # An unrestorable assignment hold past its deadline (retained parking marker).
    'assignment_hold_escalated',
)
TERMINAL_TRANSITIONS = Counter(
    'omi_backlog_state_transitions_total',
    'Backlog state-machine terminal and re-drive transitions; content always retained',
    ['transition'],
)
for _transition in TRANSITIONS:
    TERMINAL_TRANSITIONS.labels(_transition)


def record_transition(transition: str, count: int = 1) -> None:
    if transition not in TRANSITIONS:
        raise ValueError('backlog transition must be a static label')
    try:
        TERMINAL_TRANSITIONS.labels(transition).inc(count)
    except Exception:
        logger.warning('event=backlog_state_transition outcome=metric_error transition=%s', transition)
