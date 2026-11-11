"""Validation for additive, shadow-only entitlement-version metadata."""

from typing import Any, Mapping


def validate_entitlement_versions(catalog: Mapping[str, Any]) -> list[str]:
    errors = []
    versions = catalog.get('entitlement_versions')
    if not isinstance(versions, dict) or set(versions) != {'legacy', 'ladder_v1'}:
        return ['entitlement_versions: expected legacy and ladder_v1']
    if (
        not isinstance(versions['legacy'], dict)
        or set(versions['legacy']) != {'budget', 'capabilities'}
        or versions['legacy'].get('budget') is not None
    ):
        errors.append('entitlement_versions.legacy: legacy has no usage-unit budget')
    ladder = versions['ladder_v1']
    if not isinstance(ladder, dict) or set(ladder) != {
        'rate_card_version',
        'unit_usd_micros',
        'monthly_budgets',
        'mcp_daily_caps',
        'api_max_reads_per_request',
        'capabilities',
    }:
        return errors + ['entitlement_versions.ladder_v1: invalid keys']
    if ladder['rate_card_version'] != 'v1' or ladder['unit_usd_micros'] != 1000:
        errors.append('entitlement_versions.ladder_v1: expected v1 at $0.001/unit')
    if ladder.get('mcp_daily_caps') != {'basic': 100, 'plus': 500, 'operator': 5000, 'architect': 5000}:
        errors.append('ladder_v1.mcp_daily_caps: expected ratified caps')
    if ladder.get('api_max_reads_per_request') != {'basic': 2000, 'plus': 5000, 'operator': 25000, 'architect': 25000}:
        errors.append('ladder_v1.api_max_reads_per_request: expected per-plan read limits')
    for version, plans in {
        'legacy': {
            'basic': False,
            'plus': True,
            'unlimited': True,
            'unlimited_v2': True,
            'operator': True,
            'architect': True,
        },
        'ladder_v1': {'basic': False, 'plus': False, 'operator': True, 'architect': True},
    }.items():
        expected_capabilities = {plan: {'cloud_screen_vectors': allowed} for plan, allowed in plans.items()}
        if versions[version].get('capabilities') != expected_capabilities:
            errors.append(f'entitlement_versions.{version}.capabilities: expected cloud screen vector parity')
    bindings_config = catalog.get('ladder_v1_price_bindings')
    expected = {
        f'ladder_v1_{tier}_{interval}': {
            'plan_id': plan,
            'interval': interval,
            'env_var': f'LADDER_V1_{tier.upper()}_{interval.upper()}_PRICE_ID',
        }
        for tier, plan in [('plus', 'plus'), ('pro', 'operator'), ('architect', 'architect')]
        for interval in ('month', 'year')
    }
    if bindings_config != expected:
        errors.append('ladder_v1_price_bindings: expected six lookup-key bindings')
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


_DESKTOP_PROFILE_RANK = ('desktop_free', 'desktop_full', 'desktop_architect')


def _desktop_rank(profile: Any) -> int:
    return _DESKTOP_PROFILE_RANK.index(profile) if profile in _DESKTOP_PROFILE_RANK else -1


def validate_entitlement_compatibility(previous: Mapping[str, Any], current: Mapping[str, Any]) -> list[str]:
    errors = []

    def price_map(catalog: Mapping[str, Any]) -> dict[str, Any]:
        prices = {}
        for price in catalog.get('recognized_stripe_prices', []):
            if not isinstance(price, dict) or not isinstance(price.get('price_id'), str) or not price['price_id']:
                errors.append('compatibility: recognized price requires a nonempty price_id')
                continue
            prices[price['price_id']] = price
        return prices

    current_prices = price_map(current)
    for price_id, price in price_map(previous).items():
        replacement = current_prices.get(price_id)
        if replacement and replacement.get('entitlement_version', 'legacy') != price.get(
            'entitlement_version', 'legacy'
        ):
            errors.append(f"compatibility: {price['price_id']} cannot change entitlement version")
    # Default runtime APIs still consume these rows, so existing legacy policy cannot drift.
    policy_keys = (
        'allocations',
        'desktop_profile',
        'conditional_desktop_profiles',
        'fair_use_profile',
        'phone_calls_profile',
    )

    def indexed_plans(catalog: Mapping[str, Any]) -> dict[str, Any]:
        plans = {}
        for plan in catalog.get('plans', []):
            plan_id = plan.get('id') if isinstance(plan, dict) else None
            if not isinstance(plan_id, str) or not plan_id:
                errors.append('compatibility: plan requires an id')
                continue
            plans[plan_id] = plan
        return plans

    current_plans = indexed_plans(current)
    for plan in previous.get('plans', []):
        plan_id = plan.get('id') if isinstance(plan, dict) else None
        if not isinstance(plan_id, str) or not plan_id:
            errors.append('compatibility: plan requires an id')
            continue
        replacement = current_plans.get(plan_id)
        if not replacement:
            continue
        missing = [key for key in policy_keys if key not in plan or key not in replacement]
        if missing:
            errors.append(f"compatibility: {plan_id} missing legacy entitlement key {missing[0]}")
            continue
        changed = [key for key in policy_keys if plan[key] != replacement[key]]
        # Desktop access may widen (a retired catalog folds into the remaining plan) but never narrow.
        if changed == ['desktop_profile'] and _desktop_rank(replacement['desktop_profile']) > _desktop_rank(
            plan['desktop_profile']
        ):
            continue
        if changed:
            errors.append(f"compatibility: {plan_id} legacy entitlements cannot change")
    if previous.get('allocation_profiles') != current.get('allocation_profiles'):
        errors.append('compatibility: legacy allocation profiles cannot change')
    return errors
