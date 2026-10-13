"""Stable backend API for the generated subscription plan catalog.

Plan identity and static policy live in ``plan_catalog.json``. Runtime code
imports this module (or the generated constants it re-exports) instead of
parsing JSON or rebuilding plan sets. Unresolved product decisions are never
silently presented as canonical values: callers must opt into the preserved
legacy behavior while a decision remains open.
"""

from __future__ import annotations

import os
from copy import deepcopy
from typing import Any, Mapping, Optional

from config.plan_catalog_generated import (  # noqa: F401 - this module is the public facade
    ENTITLEMENT_VERSIONS,
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
    return resolved


def resolve_stripe_price_plan(
    price_id: str,
    environ: Mapping[str, str] | None = None,
) -> PlanType:
    """Resolve every retained or currently configured subscription price ID."""

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
    }


def resolve_price_entitlements(price_id: str, environ: Mapping[str, str] | None = None) -> dict[str, Any]:
    plan = resolve_stripe_price_plan(price_id, environ)
    # Unretained env-configured prices preserve legacy semantics; env cannot activate ladder v1.
    version = RECOGNIZED_STRIPE_ENTITLEMENT_VERSIONS.get(price_id, 'legacy')
    return get_entitlement_version(plan, version)


def resolve_subscription_entitlements(subscription: Any, environ: Mapping[str, str] | None = None) -> dict[str, Any]:
    """Resolve stored Subscription objects or mappings without remote reads."""

    def field(name: str, default: Any = None) -> Any:
        return (
            subscription.get(name, default)
            if isinstance(subscription, Mapping)
            else getattr(subscription, name, default)
        )

    plan = PlanType(field('plan', 'basic'))
    if field('status', 'active') != 'active':
        return get_entitlement_version(PlanType.basic)
    price = field('current_price_id')
    if price:
        return resolve_price_entitlements(price, environ)
    # Old persisted paid records can predate current_price_id.
    return get_entitlement_version(plan)


__all__ = [
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
