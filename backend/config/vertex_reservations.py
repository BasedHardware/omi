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


RESERVATIONS = {
    'gemini-2.5-flash': Reservation('flash-5-gsu', 'us-central1', unknown_capacity='dedicated', overflow='ladder'),
    'gemini-3.8-flash': Reservation('flash-5-gsu', 'us', 'OMI_VERTEX_PT_TARGET_LOCATION', thinking_level='low'),
}
STATE_OVERRIDE_ENV = 'OMI_VERTEX_RESERVATION_STATES'
ENFORCEMENT_ENV = 'OMI_VERTEX_LEGACY_TASK_MODE'
PROBE_SECONDS = 600
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
    kind: str  # dedicated, shared, remap, refuse
    model: str = ''


# Lane refinements precede the requested-model default. No platform is cut off
# merely because it sends Flash, a screenshot, or the broad extraction tag.
D = Action('dedicated')
S = Action('shared')
R = Action('refuse')
MODEL_REMAPS = {'gemini-2.5-pro': 'gemini-3.1-flash-lite'}

POLICIES = {
    'macos_legacy_tasks': {State.ACTIVE: D, State.INACTIVE: R, State.UNKNOWN: D},
    'windows_tasks': {State.ACTIVE: D, State.INACTIVE: S, State.UNKNOWN: D},
    'windows_focus': {State.ACTIVE: D, State.INACTIVE: S, State.UNKNOWN: D},
    'macos_dictation': {State.ACTIVE: D, State.INACTIVE: S, State.UNKNOWN: D},
    'macos_suggestions': {State.ACTIVE: D, State.INACTIVE: S, State.UNKNOWN: D},
    'desktop_other': {State.ACTIVE: D, State.INACTIVE: S, State.UNKNOWN: D},
    'backend_other': {State.ACTIVE: D, State.INACTIVE: S, State.UNKNOWN: D},
}

LANE_POLICIES = {'gemini-2.5-flash': POLICIES}


def policy(model: str, state: State, *, lane: str = '') -> Action:
    if model in MODEL_REMAPS:
        return Action('remap', MODEL_REMAPS[model])
    spec = RESERVATIONS.get(model)
    if spec is None:
        return S
    lanes = LANE_POLICIES.get(model, {})
    if lane in lanes:
        return lanes[lane][state]
    return {State.ACTIVE: D, State.INACTIVE: S, State.UNKNOWN: Action(spec.unknown_capacity)}[state]
