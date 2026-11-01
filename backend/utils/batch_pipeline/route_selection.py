"""Admission-time STT route selection across GPU and vendors (all-vendor routing, slice B).

``select_route`` replaces intake's direct ``provider_stt.resolve_route`` call. Outside the
vendor-routing cohort, with the kill switch off, or for an owner whose legacy sync is still
on, it returns ``resolve_route`` itself, so today's routing is unchanged byte for byte. Inside
the cohort it reads the route table (configured -> last valid -> builtin), keeps only the
options code-owned capability admits, applies vendor health and the GPU floor share, then
picks the cheapest (or first, for an ordered table) route that is not failover-only.

Selection only chooses where a unit starts. It never mints a vendor intent: the provider
stage owns paid-once, failover and ``vendor_held``. A vendor that is unhealthy at admission
is skipped; when no capable route is healthy the unit still takes its first capable vendor
route and the stage holds it with its audio, so an outage never stops admission.
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
from threading import Lock
from typing import Any

from config.batch_pipeline_vendor_routing import (
    parse_route_table,
    route_table_raw,
    vendor_routing_allowlisted,
    vendor_routing_enabled,
    vendor_routing_percent,
    vendor_routing_shadow_percent,
)
from config.policy.batch import cohort_bucket
from utils.batch_pipeline import vendor_route_contracts as contracts
from utils.batch_pipeline import vendor_route_metrics as metrics
from utils.batch_pipeline.provider_stt import SttRoute, resolve_route
from utils.observability.reasons import VendorHealthReason, VendorRouteReason, VendorRouteTableOutcome

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RouteDecision:
    """What intake stamps (``route``) plus why, for metrics and the provider stage."""

    route: SttRoute
    selected: str  # a contracts.ROUTES member
    reason: VendorRouteReason
    table_version: str
    # Capable vendor routes after ``selected`` in row order, healthy at admission. The stage
    # re-checks health and the paid-once bounds before any failover; this is a hint only.
    failover: tuple[str, ...] = ()


class _TableCache:
    """Parses each distinct payload once; the ladder keeps last-valid across payloads."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._ladder = contracts.RouteTableLadder()
        self._raw: str | None = None
        self._resolved: tuple[contracts.RouteTable, VendorRouteTableOutcome] | None = None

    def resolve(self, raw: str | None) -> tuple[contracts.RouteTable, VendorRouteTableOutcome]:
        with self._lock:
            if self._resolved is None or raw != self._raw:
                self._resolved = self._ladder.resolve(parse_route_table(raw))
                self._raw = raw
                if self._resolved[1] is not VendorRouteTableOutcome.CONFIGURED and raw is not None:
                    # Fixed text: a rejected payload is never logged.
                    logger.warning('event=batch_vendor_route_table outcome=rejected served=%s', self._resolved[1].value)
            return self._resolved


_tables = _TableCache()
_health: contracts.VendorHealth = contracts.AlwaysHealthy()


def configure_health(health: contracts.VendorHealth) -> None:
    """Slice C binds its cross-pod ``VendorHealth`` here; until then every vendor is healthy."""
    global _health
    _health = health


def current_table() -> tuple[contracts.RouteTable, VendorRouteTableOutcome]:
    if not vendor_routing_enabled():
        return contracts.BUILTIN_TABLE, VendorRouteTableOutcome.BUILTIN
    return _tables.resolve(route_table_raw())


def route_allowed(service: str) -> bool:
    """Health gate for one route; GPU always passes. Never raises."""
    if service == contracts.GPU:
        return True
    try:
        allowed, _reason = _health.allows(service)
    except Exception:
        # The contract says allows() never raises; if it does, fail toward GPU or the hold.
        allowed, _reason = False, VendorHealthReason.STATE_UNAVAILABLE
    return allowed is True


def _builtin(language: str | None, byok: bool, reason: VendorRouteReason) -> RouteDecision:
    route = resolve_route(language, byok=byok)
    selected = contracts.GPU if route.stt_route == 'parakeet' else route.provider_service
    return RouteDecision(route, selected, reason, contracts.BUILTIN_TABLE.table_version)


def _as_stt_route(selected: str, language: str | None, byok: bool) -> SttRoute:
    normalized = contracts.normalized_language(language)
    if selected == contracts.GPU:
        return SttRoute('parakeet', 'byok' if byok else 'none', 'none', normalized)
    # Same reason vocabulary as resolve_route: a vendor serving a language the GPU cannot is
    # 'unsupported_language'; a vendor chosen over a capable GPU records no special reason.
    reason = (
        'byok' if byok else ('none' if contracts.route_capable(contracts.GPU, normalized) else 'unsupported_language')
    )
    return SttRoute('provider', reason, selected, normalized[:16])  # type: ignore[arg-type]


def _price(table: contracts.RouteTable, route: str) -> float:
    price = table.routes[route].price_usd_per_audio_hour
    if price is None:  # RouteTable.from_dict refuses a cheapest table with an unpriced route
        raise contracts.RouteTableInvalid('cheapest selection requires a price on every route')
    return price


def decide(table: contracts.RouteTable, language: str | None, *, byok: bool, uid: str) -> RouteDecision | None:
    """Pure selection over one table; ``None`` when the table offers no capable route."""
    options = contracts.capable_options(table, language)
    capable = [option.route for option in options]
    healthy = [route for route in capable if route_allowed(route)]
    primaries = [route for route in healthy if not table.routes[route].failover_only]

    # The floor is a fleet share, not a row preference: it holds wherever deployed Parakeet can
    # serve the language (code-owned capability), even when the row leaves GPU out.
    if (
        contracts.route_capable(contracts.GPU, language)
        and cohort_bucket(uid, contracts.GPU_FLOOR_COHORT_SALT) < table.gpu_floor_percent
    ):
        selected, reason = contracts.GPU, VendorRouteReason.GPU_FLOOR
    elif not capable:
        return None
    elif primaries:
        if len([route for route in capable if not table.routes[route].failover_only]) == 1:
            selected, reason = primaries[0], VendorRouteReason.SOLE_CAPABLE
        elif table.selection == 'cheapest':
            # Stable on ties: row order breaks them. Validation guarantees every price is set.
            selected = min(primaries, key=lambda route: _price(table, route))
            reason = VendorRouteReason.CHEAPEST
        else:
            selected, reason = primaries[0], VendorRouteReason.ORDERED
    elif healthy:
        # Only failover capacity is healthy (e.g. Modulate down for a language the GPU cannot serve).
        selected, reason = healthy[0], VendorRouteReason.FAILOVER
    else:
        # Nothing healthy: GPU is always healthy, so this is a vendor-only row. Start on the first
        # capable vendor that is not failover-only; the stage holds the unit with its audio.
        selected = next((route for route in capable if not table.routes[route].failover_only), capable[0])
        reason = VendorRouteReason.NO_HEALTHY_ROUTE
    failover = tuple(route for route in healthy if route != selected and route in contracts.VENDOR_SERVICES)
    return RouteDecision(_as_stt_route(selected, language, byok), selected, reason, table.table_version, failover)


def failover_vendors(language: str | None, exclude: frozenset[str] | set[str] = frozenset()) -> tuple[str, ...]:
    """Vendor routes the provider stage may fail a unit over to, in table row order.

    Capable and healthy now, from the currently served table (kill switch: builtin), minus
    ``exclude`` (vendors already attempted). The stage still applies ``check_new_attempt``.
    Never raises: on any error there is no failover candidate and the stage holds the unit.
    """
    try:
        table, _outcome = current_table()
        options = contracts.capable_options(table, language)
        return tuple(
            option.route
            for option in options
            if option.route in contracts.VENDOR_SERVICES and option.route not in exclude and route_allowed(option.route)
        )
    except Exception as error:
        logger.warning('event=batch_vendor_failover_candidates outcome=none exception_type=%s', type(error).__name__)
        return ()


def _in_cohort(uid: str, percent: float) -> bool:
    # The batch-pipeline bucket (empty salt): with percent <= batch percent the cohort nests.
    return bool(uid) and (
        cohort_bucket(uid, contracts.VENDOR_ROUTING_COHORT_SALT) < percent or vendor_routing_allowlisted(uid)
    )


def _table_decision(language: str | None, *, byok: bool, uid: str) -> RouteDecision:
    table, outcome = current_table()
    metrics.table_load(outcome)
    decision = None if table is contracts.BUILTIN_TABLE else decide(table, language, byok=byok, uid=uid)
    if decision is None:
        # No configured table, or one with no capable route for this language: today's routing,
        # whose exact implementation is resolve_route (the builtin table has no floor share).
        return _builtin(language, byok, VendorRouteReason.ORDERED)
    return decision


def select_route(
    language: str | None,
    *,
    byok: bool,
    uid: str,
    batch_percent: float,
    vendor_eligible: bool,
) -> RouteDecision:
    """The admission route for one upload. Never raises past today's routing.

    ``vendor_eligible`` is false while the owner's legacy sync is on: the provider route only
    exists once legacy is draining or dark (intake), so those owners keep today's routing.
    """
    try:
        if not vendor_routing_enabled():
            decision = _builtin(language, byok, VendorRouteReason.KILL_SWITCH)
        elif not vendor_eligible or not _in_cohort(uid, vendor_routing_percent(batch_percent)):
            decision = _builtin(language, byok, VendorRouteReason.NOT_IN_COHORT)
            if vendor_eligible and _in_cohort(uid, vendor_routing_shadow_percent()):
                _log_shadow(language, byok=byok, uid=uid, served=decision)
        else:
            decision = _table_decision(language, byok=byok, uid=uid)
    except Exception as error:
        logger.error('event=batch_vendor_route outcome=builtin exception_type=%s', type(error).__name__)
        decision = _builtin(language, byok, VendorRouteReason.UNKNOWN)
    metrics.route_decision(decision.selected, decision.reason)
    return decision


def _log_shadow(language: str | None, *, byok: bool, uid: str, served: RouteDecision) -> None:
    """Decision quality for the shadow step: computed, logged without ids, never served."""
    try:
        shadow = _table_decision(language, byok=byok, uid=uid)
    except Exception as error:
        logger.warning('event=batch_vendor_route_shadow outcome=error exception_type=%s', type(error).__name__)
        return
    logger.info(
        'event=batch_vendor_route_shadow route=%s reason=%s served=%s table=%s',
        shadow.selected,
        shadow.reason.value,
        served.selected,
        shadow.table_version,
    )


def route_decision_fields(decision: RouteDecision) -> dict[str, Any]:
    """Bounded, id-free fields for logs and the job record (slice D may persist them)."""
    return {
        'selected': decision.selected,
        'reason': decision.reason.value,
        'table_version': decision.table_version,
        'failover': list(decision.failover),
    }
