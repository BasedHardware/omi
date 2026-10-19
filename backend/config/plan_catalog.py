"""Stable backend API for the generated subscription plan catalog.

Plan identity and static policy live in ``plan_catalog.json``. Runtime code
imports this module (or the generated constants it re-exports) instead of
parsing JSON or rebuilding plan sets. Unresolved product decisions are never
silently presented as canonical values: callers must opt into the preserved
legacy behavior while a decision remains open.
"""

from __future__ import annotations

import os
import logging
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal, ROUND_FLOOR
from typing import Any, Mapping, Optional

from config.rate_card import budget_units as entitlement_budget_units

from config.plan_catalog_generated import (  # noqa: F401 - this module is the public facade
    ENTITLEMENT_VERSIONS,
    LADDER_V1_PRICE_BINDINGS,
    LADDER_V1_STRIPE_PRICES,
    RECOGNIZED_STRIPE_ENTITLEMENT_VERSIONS,
    BILLING_ENV_VAR_PLAN_TYPES,
    CATALOG_AUTHORITY,
    CATALOG_REVISION,
    CATALOG_SHA256,
    DESKTOP_ENTITLED_PLAN_TYPES,
    DESKTOP_PROFILE_DEFAULTS,
    FAIR_USE_PROFILE_LIMITS,
    LEGACY_WIRE_PLAN_VALUES,
    MEASUREMENT_CONTRACTS,
    MOBILE_PLAN_TYPES,
    OPEN_PLAN_DECISIONS,
    PAID_PLAN_IDS,
    PAID_PLAN_TYPES,
    PHONE_CALL_PROFILE_DEFAULTS,
    PLAN_CATALOG_DATA,
    PLAN_DISPLAY_NAMES,
    PLAN_STOREFRONTS,
    PLAN_TYPE_VALUES,
    PRIMARY_BILLING_ENV_VARS,
    RECOGNIZED_STRIPE_PRICE_INTERVALS,
    RECOGNIZED_STRIPE_PRICE_PLAN_TYPES,
    RECOGNIZED_STRIPE_PRODUCT_PLAN_TYPES,
    UNLIMITED_TRANSCRIPTION_PLAN_TYPES,
    WIRE_FALLBACK_PLAN_TYPES,
    WIRE_PLAN_ALIASES,
    PlanType,
)


class UnresolvedPlanDecision(ValueError):
    """A consumer requested a value whose product policy is still open."""


def get_plan_definition(plan: PlanType | str) -> Mapping[str, Any]:
    return PLAN_CATALOG_DATA[PlanType(plan).value]


def get_plan_allocation(plan: PlanType | str, allocation: str) -> Mapping[str, Any]:
    allocations = get_plan_definition(plan)['allocations']
    try:
        return allocations[allocation]
    except KeyError as error:
        raise KeyError(f'{PlanType(plan).value} has no {allocation!r} allocation') from error


def get_measurement_contract(allocation: str) -> Mapping[str, Any]:
    try:
        return MEASUREMENT_CONTRACTS[allocation]
    except KeyError as error:
        raise KeyError(f'no measurement contract exists for {allocation!r}') from error


def get_plan_contract(plan: PlanType | str) -> Mapping[str, Any]:
    """Return one joined view of a plan's policy and measurement coverage."""

    definition = get_plan_definition(plan)
    return {
        'catalog_revision': CATALOG_REVISION,
        'catalog_sha256': CATALOG_SHA256,
        'plan': definition,
        'features': {
            allocation: {
                'policy': policy,
                'measurement': get_measurement_contract(allocation),
            }
            for allocation, policy in definition['allocations'].items()
        },
    }


def allocation_limit(
    plan: PlanType | str,
    allocation: str,
    *,
    use_legacy_value_for_open_decision: bool = False,
) -> Optional[int]:
    """Return an exact integer allocation limit, or ``None`` for unlimited.

    The catalog uses explicit typed units, including ``usd_cent`` for the
    Architect chat budget. A pending product decision raises unless the caller
    explicitly asks for the documented legacy runtime value.
    """

    limit = get_plan_allocation(plan, allocation)['limit']
    kind = limit['kind']
    if kind == 'unlimited':
        return None
    if kind == 'finite':
        return int(limit['value'])
    if use_legacy_value_for_open_decision:
        return int(limit['legacy_runtime_value'])
    decision_id = limit['decision_id']
    raise UnresolvedPlanDecision(f'{PlanType(plan).value}.{allocation} requires product decision {decision_id}')


def allocation_exhaustion_policy(
    plan: PlanType | str,
    allocation: str,
    *,
    use_legacy_policy_for_open_decision: bool = False,
) -> str:
    exhaustion = get_plan_allocation(plan, allocation).get('exhaustion')
    if not isinstance(exhaustion, dict):
        raise ValueError(f'{PlanType(plan).value}.{allocation} has no exhaustion policy')
    if exhaustion['kind'] != 'decision_required':
        return str(exhaustion['kind'])
    if use_legacy_policy_for_open_decision:
        return str(exhaustion['runtime_until_decided'])
    decision_id = exhaustion['decision_id']
    raise UnresolvedPlanDecision(f'{PlanType(plan).value}.{allocation} requires product decision {decision_id}')


def plan_uses_overage(plan: PlanType | str, allocation: str = 'chat') -> bool:
    """Single reporting/enforcement predicate, preserving unresolved behavior."""

    return (
        allocation_exhaustion_policy(
            plan,
            allocation,
            use_legacy_policy_for_open_decision=True,
        )
        == 'overage'
    )


def configured_ladder_prices(environ: Mapping[str, str] | None = None) -> dict[str, dict[str, Any]]:
    """Explicit lookup-key bindings; no Stripe I/O and no legacy price reclassification."""
    values = os.environ if environ is None else environ
    rows: dict[str, dict[str, Any]] = {}
    for lookup_key, binding in LADDER_V1_PRICE_BINDINGS.items():
        price_id = values.get(binding['env_var'], '').strip()
        if not price_id:
            continue
        if not price_id.startswith('price_'):
            raise ValueError(f'{binding["env_var"]}: expected Stripe price ID')
        if price_id in RECOGNIZED_STRIPE_PRICE_PLAN_TYPES:
            if RECOGNIZED_STRIPE_ENTITLEMENT_VERSIONS.get(price_id) != 'ladder_v1':
                raise ValueError('Cannot reclassify a legacy price as ladder_v1')
            if (
                RECOGNIZED_STRIPE_PRICE_PLAN_TYPES[price_id].value != binding['plan_id']
                or RECOGNIZED_STRIPE_PRICE_INTERVALS[price_id] != binding['interval']
            ):
                raise ValueError('Retained ladder binding conflicts with configuration')
        if price_id in rows:
            raise ValueError('Each ladder lookup key requires a distinct price')
        # A legacy billing env must never resolve to new entitlements.
        if any(values.get(env) == price_id for env in BILLING_ENV_VAR_PLAN_TYPES):
            raise ValueError('Ladder prices cannot replace legacy billing env bindings')
        rows[price_id] = dict(binding, price_id=price_id, lookup_key=lookup_key, entitlement_version='ladder_v1')
    return rows


def validate_ladder_price(price_id: str, row: Mapping[str, Any], *, allow_archived: bool = False) -> None:
    binding = configured_ladder_prices().get(price_id)
    if not binding:
        return
    recurring = row.get('recurring') or {}
    product = row.get('product')
    product_id = product.get('id') if isinstance(product, Mapping) else product
    if not isinstance(product_id, str) or RECOGNIZED_STRIPE_PRODUCT_PLAN_TYPES.get(product_id) != PlanType(
        binding['plan_id']
    ):
        raise ValueError('Ladder price product does not match plan')
    if (
        row.get('id') != price_id
        or row.get('lookup_key') != binding['lookup_key']
        or (not allow_archived and row.get('active') is not True)
        or row.get('currency') != 'usd'
        or recurring.get('interval') != binding['interval']
        or recurring.get('interval_count') != 1
        or type(row.get('unit_amount')) is not int
        or row['unit_amount'] <= 0
    ):
        raise ValueError('Ladder Stripe price does not match lookup-key contract')


def configured_billing_price_plans(environ: Mapping[str, str] | None = None) -> dict[str, PlanType]:
    """Return effective env-configured price bindings and reject ambiguity.

    Environment references are a migration input, not a second plan mapping:
    their plan ownership is generated from the catalog. Reusing one price for
    aliases of the same plan is valid (for example Architect/Pro); assigning a
    price to two plans fails immediately.
    """

    values = os.environ if environ is None else environ
    resolved: dict[str, PlanType] = {}
    for env_var, plan in BILLING_ENV_VAR_PLAN_TYPES.items():
        price_id = values.get(env_var)
        if not price_id:
            continue
        prior = resolved.get(price_id)
        if prior is not None and prior != plan:
            raise ValueError(f'Stripe price {price_id} is configured for both {prior.value} and {plan.value}')
        resolved[price_id] = plan
    for price_id, binding in configured_ladder_prices(values).items():
        resolved[price_id] = PlanType(binding['plan_id'])
    return resolved


def resolve_stripe_price_plan(
    price_id: str,
    environ: Mapping[str, str] | None = None,
) -> PlanType:
    """Resolve every retained or currently configured subscription price ID."""

    ladder = configured_ladder_prices(environ).get(price_id)
    if ladder:
        return PlanType(ladder['plan_id'])
    retained = RECOGNIZED_STRIPE_PRICE_PLAN_TYPES.get(price_id)
    configured = configured_billing_price_plans(environ).get(price_id)
    if retained is not None and configured is not None and retained != configured:
        raise ValueError(
            f'Stripe price {price_id} is retained as {retained.value} but configured as {configured.value}'
        )
    if retained is not None:
        return retained
    if configured is not None:
        return configured
    raise ValueError(f'Price ID {price_id} does not correspond to a known plan.')


def get_entitlement_version(plan: PlanType | str, version: str = 'legacy') -> dict[str, Any]:
    plan = PlanType(plan)
    if version == 'legacy':
        return {
            'plan_id': plan.value,
            'entitlement_version': version,
            'policy': deepcopy(get_plan_definition(plan)),
            'budget': None,
            'capabilities': deepcopy(ENTITLEMENT_VERSIONS[version]['capabilities'][plan.value]),
        }
    if version != 'ladder_v1':
        raise ValueError(f'Unknown entitlement version: {version}')
    ladder = ENTITLEMENT_VERSIONS[version]
    if plan.value not in ladder['monthly_budgets']:
        raise ValueError(f'{plan.value} has no ladder_v1 entitlements')
    return {
        'plan_id': plan.value,
        'entitlement_version': version,
        'budget': deepcopy(ladder['monthly_budgets'][plan.value]),
        'rate_card_version': ladder['rate_card_version'],
        'unit_usd_micros': ladder['unit_usd_micros'],
        'capabilities': deepcopy(ladder['capabilities'][plan.value]),
    }


# Spec §4 / evidence §6 (W0 §5). Break-even variable budget is
# price − (Stripe 2.9% + $0.30) − fixed per-user cost. Architect's fixed cost
# is the 2026-09-22..2026-10-09 mean of SUM(shared_headcount)*30/18 over the
# 21 cost-active architect users ($3.465491536615313). One unit is $0.001.
# Floor so the dormant cap never rounds above break-even. Plus ($16.36 →
# 16360) and Pro ($44.09 → 44090) are ratified inputs; this is the same rule
# at the $199 Architect price.
_ARCHITECT_MONTHLY_PRICE_USD = Decimal('199')
_ARCHITECT_FIXED_COST_USD = Decimal('3.465491536615313')
_STRIPE_FEE_RATE = Decimal('0.029')
_STRIPE_FEE_FIXED_USD = Decimal('0.30')
_LADDER_UNIT_USD = Decimal('0.001')


def architect_ladder_v1_budget_units() -> int:
    """Units for the dormant Architect ladder at the §4 break-even rule."""
    price = _ARCHITECT_MONTHLY_PRICE_USD
    stripe_fee = price * _STRIPE_FEE_RATE + _STRIPE_FEE_FIXED_USD
    variable_usd = price - stripe_fee - _ARCHITECT_FIXED_COST_USD
    return int((variable_usd / _LADDER_UNIT_USD).to_integral_value(rounding=ROUND_FLOOR))


def resolve_price_entitlements(price_id: str, environ: Mapping[str, str] | None = None) -> dict[str, Any]:
    plan = resolve_stripe_price_plan(price_id, environ)
    # Legacy billing envs preserve legacy semantics; only explicit ladder bindings select ladder v1.
    version = (
        'ladder_v1'
        if price_id in configured_ladder_prices(environ)
        else RECOGNIZED_STRIPE_ENTITLEMENT_VERSIONS.get(price_id, 'legacy')
    )
    return get_entitlement_version(plan, version)


def _paid_period_still_open(period_end: Any, now: datetime) -> bool:
    """Mirror get_user_valid_subscription: missing, zero, or past is not paid."""
    if not period_end:
        return False
    return datetime.fromtimestamp(period_end, tz=timezone.utc) >= now


def resolve_subscription_entitlements(subscription: Any, environ: Mapping[str, str] | None = None) -> dict[str, Any]:
    """Resolve versioned subscription policy without remote reads.

    Runtime admission consumes ladder budgets only behind default-off cutover switches.
    Paid rows follow get_user_valid_subscription: a missing, zero, or past
    current_period_end resolves to basic even when status is active or trialing.
    """

    def field(name: str, default: Any = None) -> Any:
        return (
            subscription.get(name, default)
            if isinstance(subscription, Mapping)
            else getattr(subscription, name, default)
        )

    raw_plan = field('plan', 'basic')
    plan = PlanType.basic if raw_plan == 'free' else PlanType(raw_plan)
    status = field('status', 'active')
    period_end = field('current_period_end')
    period_open = _paid_period_still_open(period_end, datetime.now(timezone.utc))
    inactive_paid_period = status == 'inactive' and plan in PAID_PLAN_TYPES and period_open
    if plan in PAID_PLAN_TYPES and status in ('active', 'trialing') and not period_open:
        return get_entitlement_version(PlanType.basic)
    if status not in ('active', 'trialing') and not inactive_paid_period:
        return get_entitlement_version(PlanType.basic)
    price = field('current_price_id')
    if price:
        if (
            price in RECOGNIZED_STRIPE_PRICE_PLAN_TYPES
            or price in configured_billing_price_plans(environ)
            or price in configured_ladder_prices(environ)
        ):
            # Recognized/configured conflicts remain errors; only unknown identity falls back.
            return resolve_price_entitlements(price, environ)
        logging.getLogger(__name__).warning(
            'Unknown current Stripe price; retaining stored plan legacy entitlements: plan=%s', plan.value
        )
    # Old persisted paid records can predate current_price_id.
    return get_entitlement_version(plan)


__all__ = [
    "entitlement_budget_units",
    "configured_ladder_prices",
    "validate_ladder_price",
    "LADDER_V1_PRICE_BINDINGS",
    'ENTITLEMENT_VERSIONS',
    'LADDER_V1_STRIPE_PRICES',
    'RECOGNIZED_STRIPE_ENTITLEMENT_VERSIONS',
    "get_entitlement_version",
    "resolve_price_entitlements",
    "resolve_subscription_entitlements",
    'BILLING_ENV_VAR_PLAN_TYPES',
    'CATALOG_AUTHORITY',
    'CATALOG_REVISION',
    'CATALOG_SHA256',
    'DESKTOP_ENTITLED_PLAN_TYPES',
    'DESKTOP_PROFILE_DEFAULTS',
    'FAIR_USE_PROFILE_LIMITS',
    'LEGACY_WIRE_PLAN_VALUES',
    'MEASUREMENT_CONTRACTS',
    'MOBILE_PLAN_TYPES',
    'OPEN_PLAN_DECISIONS',
    'PAID_PLAN_IDS',
    'PAID_PLAN_TYPES',
    'PHONE_CALL_PROFILE_DEFAULTS',
    'PLAN_CATALOG_DATA',
    'PLAN_DISPLAY_NAMES',
    'PLAN_STOREFRONTS',
    'PLAN_TYPE_VALUES',
    'PRIMARY_BILLING_ENV_VARS',
    'PlanType',
    'RECOGNIZED_STRIPE_PRICE_INTERVALS',
    'RECOGNIZED_STRIPE_PRICE_PLAN_TYPES',
    'RECOGNIZED_STRIPE_PRODUCT_PLAN_TYPES',
    'UNLIMITED_TRANSCRIPTION_PLAN_TYPES',
    'UnresolvedPlanDecision',
    'WIRE_FALLBACK_PLAN_TYPES',
    'WIRE_PLAN_ALIASES',
    'allocation_exhaustion_policy',
    'allocation_limit',
    'configured_billing_price_plans',
    'get_plan_allocation',
    'get_plan_definition',
    'get_measurement_contract',
    'get_plan_contract',
    'plan_uses_overage',
    'resolve_stripe_price_plan',
]
