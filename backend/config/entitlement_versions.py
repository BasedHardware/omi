"""Price-keyed subscription version metadata; admission remains on legacy APIs.

No live ladder price is configured. W4/W5 own enforcement and activation.
The Free budget expression is evaluated only once rate-card v1 is available.
"""

from copy import deepcopy
from typing import Any, Mapping

from config.plan_catalog import PlanType, get_plan_definition, resolve_stripe_price_plan
from config.plan_catalog_generated import ENTITLEMENT_VERSIONS, RECOGNIZED_STRIPE_ENTITLEMENT_VERSIONS


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
