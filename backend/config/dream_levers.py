"""Dream efficiency levers: off, shadow (measure only) or serve, per owner cohort.

Each lever reads one ``config.refactor_modes`` mode env. ``shadow`` (the
default) keeps today's behavior and records what the lever would have done;
``<MODE>_SERVE_PERCENT`` enforces it for a salted owner bucket so the rest stay
a same-day control; ``serve`` enforces it for everyone; ``off`` skips even the
measurement. Every reader fails open: a parse or cohort error is ``off``.
"""

import logging
from typing import Literal

from config import refactor_modes

logger = logging.getLogger(__name__)

Arm = Literal['off', 'shadow', 'serve']

# Skip a scheduled pass when the owner has no new material (David 2026-10-28: no slow-rotation floor).
IDLE_SKIP_MODE_ENV = 'DREAM_IDLE_SKIP_MODE'
IDLE_SKIP_SERVE_PERCENT_ENV = 'DREAM_IDLE_SKIP_MODE_SERVE_PERCENT'
# Order each sweep's due owners by expected payoff, with an aging bound. Global: off/shadow/serve only.
PAYOFF_ORDER_MODE_ENV = 'DREAM_PAYOFF_ORDER_MODE'
# Back off an owner's hunt cadence after dry hunts (David 2026-10-30: replaces the idle-skip hunt floor).
HUNT_BACKOFF_MODE_ENV = 'DREAM_HUNT_BACKOFF_MODE'
HUNT_BACKOFF_SERVE_PERCENT_ENV = 'DREAM_HUNT_BACKOFF_MODE_SERVE_PERCENT'

# Hold the two verifier calls' token reserve out of the main loop so staged work is
# verified (10-30/31: 171 of 252 daily verifier_unverified items had zero verifier calls).
VERIFY_HOLD_MODE_ENV = 'DREAM_VERIFY_HOLD_MODE'
VERIFY_HOLD_SERVE_PERCENT_ENV = 'DREAM_VERIFY_HOLD_MODE_SERVE_PERCENT'
# Apply trivially reversible auto kinds left unverified by budget or transport, never
# when a verifier disagreed or the evidence was oversized or answered with invalid ids.
LIBERAL_VERIFIER_MODE_ENV = 'DREAM_LIBERAL_VERIFIER_MODE'
LIBERAL_VERIFIER_SERVE_PERCENT_ENV = 'DREAM_LIBERAL_VERIFIER_MODE_SERVE_PERCENT'
LIBERAL_VERIFIER_KINDS = frozenset({'dismiss_person', 'spelling', 'title', 'overview', 'set_language', 'vocabulary'})
LIBERAL_VERIFIER_REASONS = frozenset({'call_failed', 'single_vote', 'budget_tokens', 'budget_deadline'})

# Idle skip stays off; payoff ordering and the verifier hold serve by default.
DEFAULT_MODES: dict[str, Arm] = {
    IDLE_SKIP_MODE_ENV: 'off',
    PAYOFF_ORDER_MODE_ENV: 'serve',
    VERIFY_HOLD_MODE_ENV: 'serve',
}

PER_OWNER = (
    IDLE_SKIP_MODE_ENV,
    HUNT_BACKOFF_MODE_ENV,
    VERIFY_HOLD_MODE_ENV,
    LIBERAL_VERIFIER_MODE_ENV,
)
SHORT_NAMES = {
    IDLE_SKIP_MODE_ENV: 'idle_skip',
    PAYOFF_ORDER_MODE_ENV: 'payoff_order',
    HUNT_BACKOFF_MODE_ENV: 'hunt_backoff',
    VERIFY_HOLD_MODE_ENV: 'verify_hold',
    LIBERAL_VERIFIER_MODE_ENV: 'liberal_verifier',
}


def arm(name: str, uid: str | None) -> Arm:
    """This owner's arm for one lever; any configuration error fails open to ``off``."""
    try:
        default: Arm = DEFAULT_MODES.get(name, 'shadow')
        current = refactor_modes.mode(name, default)
        if current == 'off':
            return 'off'
        if name == PAYOFF_ORDER_MODE_ENV:
            return current
        return 'serve' if refactor_modes.serving_for(name, uid, default) else 'shadow'
    except Exception as error:
        logger.warning(
            'event=dream_lever_error lever=%s exc=%s', SHORT_NAMES.get(name, 'unknown'), type(error).__name__
        )
        return 'off'


def arms(uid: str | None) -> dict[str, Arm]:
    return {SHORT_NAMES[name]: arm(name, uid) for name in PER_OWNER}


def telemetry_enabled() -> bool:
    return refactor_modes.default_on('DREAM_TELEMETRY_V2_ENABLED')


def defect_reports_enabled() -> bool:
    return refactor_modes.default_on('DREAM_DEFECT_REPORTS_ENABLED')
