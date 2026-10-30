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
# Size the pass token budget by new material instead of total history.
MATERIAL_BUDGET_MODE_ENV = 'DREAM_MATERIAL_BUDGET_MODE'
MATERIAL_BUDGET_SERVE_PERCENT_ENV = 'DREAM_MATERIAL_BUDGET_MODE_SERVE_PERCENT'
# End a pass that stops staging anything for several turns.
NO_PROGRESS_STOP_MODE_ENV = 'DREAM_NO_PROGRESS_STOP_MODE'
NO_PROGRESS_STOP_SERVE_PERCENT_ENV = 'DREAM_NO_PROGRESS_STOP_MODE_SERVE_PERCENT'
# Elide old tool results from the re-sent conversation once a pass's prompt grows large.
HISTORY_COMPACT_MODE_ENV = 'DREAM_HISTORY_COMPACT_MODE'
HISTORY_COMPACT_SERVE_PERCENT_ENV = 'DREAM_HISTORY_COMPACT_MODE_SERVE_PERCENT'
# Order each sweep's due owners by expected payoff, with an aging bound. Global: off/shadow/serve only.
PAYOFF_ORDER_MODE_ENV = 'DREAM_PAYOFF_ORDER_MODE'
# Back off an owner's hunt cadence after dry hunts (David 2026-10-30: replaces the idle-skip hunt floor).
HUNT_BACKOFF_MODE_ENV = 'DREAM_HUNT_BACKOFF_MODE'
HUNT_BACKOFF_SERVE_PERCENT_ENV = 'DREAM_HUNT_BACKOFF_MODE_SERVE_PERCENT'
# Deterministic no-LLM pre-scan handing hunts concrete people/task cleanup targets.
PRESCAN_MODE_ENV = 'DREAM_PRESCAN_MODE'
PRESCAN_SERVE_PERCENT_ENV = 'DREAM_PRESCAN_MODE_SERVE_PERCENT'

# Defaults when the mode env is unset. 10-29 shadow day: idle-skip would have cut 79% of
# applied edits and the no-progress stop 31%, so both are retired (off); payoff ordering
# serves (David 2026-10-30: payoff first). Every other lever measures in shadow.
DEFAULT_MODES: dict[str, Arm] = {
    IDLE_SKIP_MODE_ENV: 'off',
    NO_PROGRESS_STOP_MODE_ENV: 'off',
    PAYOFF_ORDER_MODE_ENV: 'serve',
}

PER_OWNER = (
    IDLE_SKIP_MODE_ENV,
    MATERIAL_BUDGET_MODE_ENV,
    NO_PROGRESS_STOP_MODE_ENV,
    HISTORY_COMPACT_MODE_ENV,
    HUNT_BACKOFF_MODE_ENV,
    PRESCAN_MODE_ENV,
)
SHORT_NAMES = {
    IDLE_SKIP_MODE_ENV: 'idle_skip',
    MATERIAL_BUDGET_MODE_ENV: 'material_budget',
    NO_PROGRESS_STOP_MODE_ENV: 'no_progress_stop',
    HISTORY_COMPACT_MODE_ENV: 'history_compact',
    PAYOFF_ORDER_MODE_ENV: 'payoff_order',
    HUNT_BACKOFF_MODE_ENV: 'hunt_backoff',
    PRESCAN_MODE_ENV: 'prescan',
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
