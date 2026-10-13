"""Validation for additive, shadow-only entitlement-version metadata."""

from typing import Any, Mapping


def validate_entitlement_versions(catalog: Mapping[str, Any]) -> list[str]:
    errors = []
    versions = catalog.get('entitlement_versions')
    if not isinstance(versions, dict) or set(versions) != {'legacy', 'ladder_v1'}:
        return ['entitlement_versions: expected legacy and ladder_v1']
    if versions['legacy'] != {'budget': None}:
        errors.append('entitlement_versions.legacy: legacy has no usage-unit budget')
    ladder = versions['ladder_v1']
    if not isinstance(ladder, dict) or set(ladder) != {'rate_card_version', 'unit_usd_micros', 'monthly_budgets'}:
        return errors + ['entitlement_versions.ladder_v1: invalid keys']
    if ladder['rate_card_version'] != 'v1' or ladder['unit_usd_micros'] != 1000:
        errors.append('entitlement_versions.ladder_v1: expected v1 at $0.001/unit')
    budgets = ladder['monthly_budgets']
    if not isinstance(budgets, dict) or set(budgets) != {'basic', 'plus', 'operator', 'architect'}:
        return errors + ['entitlement_versions.ladder_v1.monthly_budgets: invalid plans']
    free = {'kind': 'rate_card_mix', 'speech_seconds': 18000, 'chat_messages': 30, 'chat_tier': 'standard'}
    if budgets['basic'] != free:
        errors.append('entitlement_versions: Free must derive from 5 speech hours + 30 standard chats')
    for plan in ('plus', 'operator', 'architect'):
        budget = budgets[plan]
        if (
            not isinstance(budget, dict)
            or set(budget) != {'kind', 'value'}
            or budget.get('kind') != 'units'
            or type(budget.get('value')) is not int
            or budget['value'] <= 0
        ):
            errors.append(f'entitlement_versions: {plan} budget must be positive integer units')
    bindings = catalog.get('ladder_v1_stripe_prices')
    if not isinstance(bindings, list) or any(not isinstance(p, str) for p in bindings):
        return errors + ['ladder_v1_stripe_prices: expected a list of price IDs']
    if len(set(bindings)) != len(bindings):
        errors.append('ladder_v1_stripe_prices: duplicate price IDs')
    ladder_prices = set()
    prices = catalog.get('recognized_stripe_prices', [])
    for price in prices if isinstance(prices, list) else []:
        if not isinstance(price, dict):
            continue
        version = price.get('entitlement_version')
        if version not in versions:
            errors.append(f'entitlement_versions: unknown version {version!r}')
        if version == 'ladder_v1':
            price_id = price.get('price_id')
            if not isinstance(price_id, str) or not price_id:
                errors.append('entitlement_versions: ladder_v1 price requires a nonempty price_id')
            else:
                ladder_prices.add(price_id)
            if price.get('plan_id') not in budgets or price.get('plan_id') == 'basic':
                errors.append('entitlement_versions: ladder price must map to a paid ladder plan')
    if set(bindings) != ladder_prices:
        errors.append('ladder_v1_stripe_prices: must match recognized ladder_v1 prices exactly')
    return errors


def validate_entitlement_compatibility(previous: Mapping[str, Any], current: Mapping[str, Any]) -> list[str]:
    errors = []
    current_prices = {p['price_id']: p for p in current.get('recognized_stripe_prices', [])}
    for price in previous.get('recognized_stripe_prices', []):
        replacement = current_prices.get(price['price_id'])
        if replacement and replacement.get('entitlement_version', 'legacy') != price.get(
            'entitlement_version', 'legacy'
        ):
            errors.append(f"compatibility: {price['price_id']} cannot change entitlement version")
    # Default runtime APIs still consume these rows, so existing legacy policy cannot drift.
    current_plans = {p['id']: p for p in current.get('plans', [])}
    policy_keys = (
        'allocations',
        'desktop_profile',
        'conditional_desktop_profiles',
        'fair_use_profile',
        'phone_calls_profile',
    )
    for plan in previous.get('plans', []):
        replacement = current_plans.get(plan['id'])
        if replacement and any(plan[k] != replacement[k] for k in policy_keys):
            errors.append(f"compatibility: {plan['id']} legacy entitlements cannot change")
    if previous.get('allocation_profiles') != current.get('allocation_profiles'):
        errors.append('compatibility: legacy allocation profiles cannot change')
    return errors
