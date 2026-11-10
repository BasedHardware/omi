"""Backlog state-machine transitions, one static-label counter.

Each switch in config/backlog_state_machine.py has a rate the agent-tier alerts
in charts/monitoring/alerts/backlog-state-machine.json can read. Labels are a
closed set; no uid, segment or conversation identity.
"""

import logging

from prometheus_client import Counter

logger = logging.getLogger(__name__)

TRANSITIONS = (
    # First committed re-drive after MAX_HELD_REDRIVES; once per unit.
    'held_redrive_budget_spent',
)
TERMINAL_TRANSITIONS = Counter(
    'omi_backlog_state_transitions_total',
    'Backlog state-machine transitions; content always retained',
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
