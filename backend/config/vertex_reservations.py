"""Declared orders and pure, conservative reservation evidence reduction.

An error is never proof of absence. Automatic inactivity additionally requires
fresh positive service on another model of the SAME, exclusive order. If an
operator buys a second order, give it a different order key before enabling it.
"""

from dataclasses import dataclass, replace
from enum import Enum
from collections.abc import Mapping


class State(str, Enum):
    ACTIVE = 'active'
    INACTIVE = 'inactive'
    UNKNOWN = 'unknown'


@dataclass(frozen=True)
class Reservation:
    order: str
    location: str
    location_env: str = ''
    unknown_capacity: str = 'shared'
    overflow: str = 'shared'
    thinking_level: str = ''
    saturation_seconds: int = 120


RESERVATIONS = {
    'gemini-2.5-flash': Reservation('flash-5-gsu', 'us-central1', unknown_capacity='dedicated', overflow='ladder'),
    'gemini-3.8-flash': Reservation(
        'flash-5-gsu', 'us', 'OMI_VERTEX_PT_TARGET_LOCATION', thinking_level='low', saturation_seconds=10
    ),
}
STATE_OVERRIDE_ENV = 'OMI_VERTEX_RESERVATION_STATES'
ENFORCEMENT_ENV = 'OMI_VERTEX_LEGACY_TASK_MODE'
PROBE_SECONDS = 600
PROBE_TIMEOUT_SECONDS = 30
INACTIVE_WINDOW_SECONDS = 1800
EVIDENCE_FRESH_SECONDS = 900
ACTIVE_FRESH_SECONDS = 86400
MIN_FAILURES = 4


@dataclass(frozen=True)
class Evidence:
    success_at: float = 0
    failure_start: float = 0
    failure_at: float = 0
    failure_count: int = 0


def observe(previous: Evidence, *, now: float, outcome: str) -> Evidence:
    """Only strict PT success and capacity-signature errors teach state.

    Non-capacity failures break continuity. Count at most one failure per probe
    interval, so a burst cannot masquerade as sustained evidence.
    """
    if outcome == 'dedicated_success':
        return Evidence(success_at=now)
    if outcome != 'capacity_error':
        return replace(previous, failure_start=0, failure_at=0, failure_count=0)
    if not previous.failure_at or now - previous.failure_at > EVIDENCE_FRESH_SECONDS:
        return Evidence(previous.success_at, now, now, 1)
    if now - previous.failure_at < PROBE_SECONDS / 2:
        return previous
    return replace(previous, failure_at=now, failure_count=min(previous.failure_count + 1, 64))


def observed_state(model: str, evidence: Mapping[str, Evidence], *, now: float) -> tuple[State, str]:
    own = evidence.get(model, Evidence())
    declaration = RESERVATIONS.get(model)
    if declaration is None:
        return State.UNKNOWN, 'undeclared'
    sustained = (
        own.failure_count >= MIN_FAILURES
        and own.failure_start > own.success_at
        and own.failure_at - own.failure_start >= INACTIVE_WINDOW_SECONDS
        and 0 <= now - own.failure_at <= EVIDENCE_FRESH_SECONDS
    )
    # A saturated order alone can NEVER satisfy this positive-evidence clause.
    # Concurrent orders MUST have distinct order keys; this is an operator contract.
    moved = any(
        other != model
        and spec.order == declaration.order
        and evidence.get(other, Evidence()).success_at > own.failure_start
        and 0 <= now - evidence.get(other, Evidence()).success_at <= EVIDENCE_FRESH_SECONDS
        for other, spec in RESERVATIONS.items()
    )
    if sustained and moved:
        return State.INACTIVE, 'exclusive_order_moved'
    if own.success_at and 0 <= now - own.success_at <= ACTIVE_FRESH_SECONDS:
        return State.ACTIVE, 'dedicated_success'
    return State.UNKNOWN, 'insufficient_evidence'


@dataclass(frozen=True)
class Action:
    kind: str  # dedicated, shared (non-managed compatibility), remap, refuse, luna
    model: str = ''


# INACTIVE destinations are reviewed product policy, not an overflow ladder.
# After the exclusive-order move, only Dream may consume Gemini capacity.
# Legacy tool loops retain their explicit terminal-refusal contract.
D = Action('dedicated')
S = Action('shared')
R = Action('refuse')
REMAP = Action('remap', 'gemini-3.8-flash')
LUNA = Action('luna', 'gpt-6-luna')
MODEL_REMAPS = {'gemini-2.5-pro': 'gemini-3.1-flash-lite'}

INACTIVE_DESTINATIONS = {
    'macos_legacy_tasks': R,
    'macos_tasks': LUNA,
    'windows_tasks': LUNA,
    'windows_focus': LUNA,
    'windows_dictation': LUNA,
    'windows_suggestions': LUNA,
    'windows_live_notes': LUNA,
    'windows_screen_synthesis': LUNA,
    'windows_memory': LUNA,
    'windows_insight': LUNA,
    'windows_goals': LUNA,
    'windows_task_dedup': LUNA,
    'windows_task_prioritization': LUNA,
    'windows_home_suggestions': LUNA,
    'macos_focus': LUNA,
    'macos_dictation': LUNA,
    'macos_suggestions': LUNA,
    'macos_live_notes': LUNA,
    'macos_screen_synthesis': LUNA,
    'macos_memory': LUNA,
    'macos_insight': LUNA,
    'macos_goals': LUNA,
    'macos_task_dedup': LUNA,
    'macos_task_prioritization': LUNA,
    'macos_home_suggestions': LUNA,
    'proactive_nudges': LUNA,
    'desktop_other': LUNA,
    'backend_other': LUNA,
}

# These are the bounded product tags in desktop_gemini_attribution.json.
PRODUCT_POLICY_TAGS = {
    'task_extraction': 'tasks',
    'focus': 'focus',
    'dictation': 'dictation',
    'suggestions': 'suggestions',
    'live_notes': 'live_notes',
    'screen_synthesis': 'screen_synthesis',
    'memory': 'memory',
    'insight': 'insight',
    'goals': 'goals',
    'task_dedup': 'task_dedup',
    'task_prioritization': 'task_prioritization',
    'home_suggestions': 'home_suggestions',
}


def product_policy_lane(platform: str, tag: str, *, default: str = 'desktop_other') -> str:
    platform, tag = platform.strip().lower(), tag.strip().lower()
    if tag in {'proactive_notification', 'proactive-notification', 'proactive_nudges', 'notifications'}:
        return 'proactive_nudges'
    row = f'{platform}_{PRODUCT_POLICY_TAGS.get(tag, "other")}'
    return row if row in INACTIVE_DESTINATIONS else default


def policy(model: str, state: State, *, lane: str = '') -> Action:
    if model in MODEL_REMAPS:
        return Action('remap', MODEL_REMAPS[model])
    spec = RESERVATIONS.get(model)
    if spec is None:
        return S
    if model == 'gemini-2.5-flash':
        return INACTIVE_DESTINATIONS.get(lane, INACTIVE_DESTINATIONS['desktop_other']) if state == State.INACTIVE else D
    return {State.ACTIVE: D, State.INACTIVE: S, State.UNKNOWN: Action(spec.unknown_capacity)}[state]
