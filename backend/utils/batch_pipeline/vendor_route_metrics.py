"""All-vendor batch routing collectors. Names, labels and owners are frozen by slice A.

Every label value is a closed enum member or a fixed route/state name, so these
collectors add no ``reason_label_debt.json`` entries. No child is pre-initialised:
until a slice records, the labelled collectors export no series (the unlabelled
oldest-age gauge reads 0, which is true: nothing is held). Each slice records only its own
collectors through the helpers below, which never raise on a serving path.
"""

from prometheus_client import Counter, Gauge

from utils.batch_pipeline import vendor_route_contracts as contracts
from utils.observability.reasons import (
    ReasonFamily,
    VendorAttemptOutcome,
    VendorHealthReason,
    VendorHoldOutcome,
    VendorHoldReason,
    VendorRouteReason,
    VendorRouteTableOutcome,
    reason_label,
)

ROUTE_DECISIONS = Counter(contracts.METRIC_ROUTE_DECISIONS, 'Batch vendor route selections', ['route', 'reason'])
TABLE_LOADS = Counter(contracts.METRIC_TABLE_LOADS, 'Route table resolutions by ladder rung', ['outcome'])
ATTEMPTS = Counter(contracts.METRIC_ATTEMPTS, 'Settled batch vendor attempts', ['provider', 'outcome'])
ATTEMPT_AUDIO = Counter(
    contracts.METRIC_ATTEMPT_AUDIO, 'Audio seconds sent to a vendor, by settled outcome', ['provider', 'outcome']
)
FAILOVERS = Counter(contracts.METRIC_FAILOVERS, 'Batch units moved to another route', ['from_route', 'to_route'])
LATE_RESULTS = Counter(
    contracts.METRIC_LATE_RESULTS, 'Vendor results found after their attempt settled', ['provider', 'outcome']
)
PAID_INTENT_VIOLATIONS = Counter(
    contracts.METRIC_PAID_INTENT_VIOLATIONS, 'Attempt mints refused by the paid-once bounds; must stay 0', ['provider']
)
HOLD_TRANSITIONS = Counter(contracts.METRIC_HOLD_TRANSITIONS, 'vendor_held transitions', ['outcome'])
HELD_UNITS = Gauge(contracts.METRIC_HELD_UNITS, 'Units parked in vendor_held', ['reason'])
HELD_OLDEST_AGE = Gauge(contracts.METRIC_HELD_OLDEST_AGE, 'Oldest vendor_held unit age; alert above 2h')
HEALTH_DECISIONS = Counter(contracts.METRIC_HEALTH_DECISIONS, 'VendorHealth.allows answers', ['provider', 'reason'])
BREAKER_STATE = Gauge(
    contracts.METRIC_BREAKER_STATE, 'Vendor breaker state, 1 for the current one', ['provider', 'state']
)
AUDIO_HOURS_USED = Gauge(contracts.METRIC_AUDIO_HOURS_USED, 'Vendor audio hours used today, cross-pod', ['provider'])
AUDIO_HOURS_CAP = Gauge(contracts.METRIC_AUDIO_HOURS_CAP, 'Configured vendor daily audio-hour cap', ['provider'])
CAP_HITS = Counter(contracts.METRIC_CAP_HITS, 'Vendor sends refused at a spend cap', ['provider', 'reason'])
COLLECTORS = (
    ROUTE_DECISIONS,
    TABLE_LOADS,
    ATTEMPTS,
    ATTEMPT_AUDIO,
    FAILOVERS,
    LATE_RESULTS,
    PAID_INTENT_VIOLATIONS,
    HOLD_TRANSITIONS,
    HELD_UNITS,
    HELD_OLDEST_AGE,
    HEALTH_DECISIONS,
    BREAKER_STATE,
    AUDIO_HOURS_USED,
    AUDIO_HOURS_CAP,
    CAP_HITS,
)


def _route(value: object) -> str:
    return value if isinstance(value, str) and value in contracts.ROUTES else 'unknown'


def _vendor(value: object) -> str:
    return value if isinstance(value, str) and value in contracts.VENDOR_SERVICES else 'unknown'


def _late_outcome(value: object) -> str:
    return value if isinstance(value, str) and value in contracts.LATE_RESULT_OUTCOMES else 'unknown'


def route_decision(route: str, reason: VendorRouteReason | str) -> None:
    try:
        ROUTE_DECISIONS.labels(
            route=_route(route), reason=reason_label(ReasonFamily.VENDOR_ROUTE, reason, VendorRouteReason)
        ).inc()
    except Exception:
        pass


def table_load(outcome: VendorRouteTableOutcome | str) -> None:
    try:
        TABLE_LOADS.labels(outcome=reason_label(ReasonFamily.VENDOR_ROUTE, outcome, VendorRouteTableOutcome)).inc()
    except Exception:
        pass


def attempt(provider: str, outcome: VendorAttemptOutcome | str, audio_seconds: float) -> None:
    try:
        ATTEMPTS.labels(
            provider=_vendor(provider), outcome=reason_label(ReasonFamily.VENDOR_ROUTE, outcome, VendorAttemptOutcome)
        ).inc()
        if audio_seconds > 0:
            ATTEMPT_AUDIO.labels(
                provider=_vendor(provider),
                outcome=reason_label(ReasonFamily.VENDOR_ROUTE, outcome, VendorAttemptOutcome),
            ).inc(audio_seconds)
    except Exception:
        pass


def failover(from_route: str, to_route: str) -> None:
    try:
        FAILOVERS.labels(from_route=_route(from_route), to_route=_route(to_route)).inc()
    except Exception:
        pass


def late_result(provider: str, outcome: str) -> None:
    try:
        LATE_RESULTS.labels(provider=_vendor(provider), outcome=_late_outcome(outcome)).inc()
    except Exception:
        pass


def paid_intent_violation(provider: str) -> None:
    try:
        PAID_INTENT_VIOLATIONS.labels(provider=_vendor(provider)).inc()
    except Exception:
        pass


def hold_transition(outcome: VendorHoldOutcome | str) -> None:
    try:
        HOLD_TRANSITIONS.labels(outcome=reason_label(ReasonFamily.VENDOR_ROUTE, outcome, VendorHoldOutcome)).inc()
    except Exception:
        pass


def held_units(counts: dict, oldest_age_seconds: float) -> None:
    """Leader/sweep snapshot: every hold reason is set, so a drained reason reads 0, not stale."""
    try:
        for reason in VendorHoldReason:
            HELD_UNITS.labels(reason=reason_label(ReasonFamily.VENDOR_ROUTE, reason, VendorHoldReason)).set(
                counts.get(reason, 0)
            )
        HELD_OLDEST_AGE.set(max(0.0, oldest_age_seconds))
    except Exception:
        pass


def health_decision(provider: str, reason: VendorHealthReason | str) -> None:
    try:
        HEALTH_DECISIONS.labels(
            provider=_vendor(provider), reason=reason_label(ReasonFamily.VENDOR_ROUTE, reason, VendorHealthReason)
        ).inc()
    except Exception:
        pass


def breaker_state(provider: str, state: str) -> None:
    try:
        for candidate in contracts.BREAKER_STATES:
            BREAKER_STATE.labels(provider=_vendor(provider), state=candidate).set(1 if candidate == state else 0)
    except Exception:
        pass


def audio_hours(provider: str, used: float, cap: float | None) -> None:
    try:
        AUDIO_HOURS_USED.labels(provider=_vendor(provider)).set(used)
        if cap is not None:
            AUDIO_HOURS_CAP.labels(provider=_vendor(provider)).set(cap)
    except Exception:
        pass


def cap_hit(provider: str, reason: VendorHealthReason | str) -> None:
    try:
        CAP_HITS.labels(
            provider=_vendor(provider), reason=reason_label(ReasonFamily.VENDOR_ROUTE, reason, VendorHealthReason)
        ).inc()
    except Exception:
        pass
