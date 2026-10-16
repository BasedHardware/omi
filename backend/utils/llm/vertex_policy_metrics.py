"""Bounded, content-free telemetry for automatic managed 2.5 retirement."""

from prometheus_client import Counter
from config.vertex_reservations import INACTIVE_DESTINATIONS

MANAGED_25_ATTEMPTS = Counter(
    'omi_vertex_managed_25_attempts_total', 'Managed 2.5 Flash generation dispatches', ['lane', 'traffic_type']
)
UNEXPECTED_25_PAYGO = Counter(
    'omi_vertex_managed_25_on_demand_responses_total',
    'Managed 2.5 responses unexpectedly reporting ON_DEMAND',
    ['lane'],
)
POLICY_DECISIONS = Counter(
    'omi_vertex_routing_decisions_total', 'Managed reservation routing decisions', ['lane', 'action']
)
NON_DREAM_FLASH_AFTER_CUTOVER = Counter(
    'omi_vertex_non_dream_flash_after_cutover_attempts_total',
    'Forbidden non-Dream Flash generation attempts after the exclusive order moved, including blocked attempts',
    ['lane', 'model', 'traffic_type'],
)

for _lane in INACTIVE_DESTINATIONS:
    UNEXPECTED_25_PAYGO.labels(lane=_lane)
    for _capacity in ('dedicated', 'shared'):
        MANAGED_25_ATTEMPTS.labels(lane=_lane, traffic_type=_capacity)
        for _model in ('gemini-2.5-flash', 'gemini-3.8-flash', 'other_flash'):
            NON_DREAM_FLASH_AFTER_CUTOVER.labels(lane=_lane, model=_model, traffic_type=_capacity)


def observe_forbidden_flash(model: str, capacity: str, lane: str) -> None:
    NON_DREAM_FLASH_AFTER_CUTOVER.labels(
        lane=lane if lane in INACTIVE_DESTINATIONS else 'desktop_other',
        model=model if model in {'gemini-2.5-flash', 'gemini-3.8-flash'} else 'other_flash',
        traffic_type=capacity if capacity in {'dedicated', 'shared'} else 'unknown',
    ).inc()


def observe_decision(lane: str, action: str) -> None:
    POLICY_DECISIONS.labels(
        lane=lane if lane in INACTIVE_DESTINATIONS else 'desktop_other',
        action=action if action in {'dedicated', 'remap', 'refuse', 'luna'} else 'unknown',
    ).inc()


def observe_dispatch(model: str, capacity: str, lane: str) -> None:
    if model == 'gemini-2.5-flash':
        MANAGED_25_ATTEMPTS.labels(
            lane=lane if lane in INACTIVE_DESTINATIONS else 'desktop_other',
            traffic_type=capacity if capacity in {'dedicated', 'shared'} else 'unknown',
        ).inc()


def observe_reported_traffic(model: str, traffic_type: str | None, lane: str) -> None:
    if model == 'gemini-2.5-flash' and traffic_type == 'ON_DEMAND':
        UNEXPECTED_25_PAYGO.labels(lane=lane if lane in INACTIVE_DESTINATIONS else 'desktop_other').inc()
