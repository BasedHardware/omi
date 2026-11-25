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

# Order each sweep's due owners by expected payoff, with an aging bound. Global: off/shadow/serve only.
PAYOFF_ORDER_MODE_ENV = 'DREAM_PAYOFF_ORDER_MODE'
# Hold the two verifier calls' token reserve out of the main loop so staged work is
# verified (10-30/31: 171 of 252 daily verifier_unverified items had zero verifier calls).
VERIFY_HOLD_MODE_ENV = 'DREAM_VERIFY_HOLD_MODE'
VERIFY_HOLD_SERVE_PERCENT_ENV = 'DREAM_VERIFY_HOLD_MODE_SERVE_PERCENT'
# Apply trivially reversible auto kinds left unverified by budget or transport, never
# when a verifier disagreed or the evidence was oversized or answered with invalid ids.

# Defaults when the mode env is unset. Payoff ordering
# serves (David 2026-10-30: payoff first). The verify hold serves: it only moves budget
# from searching to verifying what was found.
DEFAULT_MODES: dict[str, Arm] = {
    PAYOFF_ORDER_MODE_ENV: 'serve',
    VERIFY_HOLD_MODE_ENV: 'serve',
}

PER_OWNER = (VERIFY_HOLD_MODE_ENV,)
SHORT_NAMES = {
    PAYOFF_ORDER_MODE_ENV: 'payoff_order',
    VERIFY_HOLD_MODE_ENV: 'verify_hold',
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
