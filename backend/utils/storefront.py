"""Backend-only presentation policy. Does not grant entitlements or mutate billing."""

from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
import json
from typing import Any, Callable

from models.storefront import (
    AnnualSavings,
    PlanFeature,
    StorefrontCurrentPlan,
    StorefrontPrice,
    StorefrontResponse,
    StorefrontTier,
    StorefrontUsage,
)
from models.users import Subscription


def load_ladder() -> dict[str, Any]:
    return json.loads((Path(__file__).resolve().parents[1] / 'config/storefront_ladder.json').read_text())


def _money(amount_minor: Decimal | int) -> str:
    dollars = (Decimal(amount_minor) / 100).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    return f'${dollars:.2f}'


def present_prices(rows: list[dict[str, Any]], *, current: bool = False) -> list[StorefrontPrice]:
    """USD recurring monthly/yearly prices only; omit unsupported billing shapes."""
    valid = [
        row
        for row in rows
        if isinstance(row.get('id'), str)
        and row.get('currency') == 'usd'
        and type(row.get('unit_amount')) is int
        and row['unit_amount'] > 0
        and (current or row.get('active') is True)
        and (row.get('recurring') or {}).get('interval') in {'month', 'year'}
        and row['recurring'].get('interval_count', 1) == 1
    ]
    valid.sort(key=lambda row: (row['recurring']['interval'] != 'month', row['id']))
    monthly = next((row for row in valid if row['recurring']['interval'] == 'month'), None)
    result = []
    for row in valid:
        interval = row['recurring']['interval']
        amount = row['unit_amount']
        savings = None
        if interval == 'year' and monthly:
            saved = monthly['unit_amount'] * 12 - amount
            if saved > 0:
                percent = round(saved * 100 / (monthly['unit_amount'] * 12), 2)
                savings = AnnualSavings(
                    amount_minor=saved, percent=percent, formatted=f'Save {_money(saved)} ({percent:.2f}%) per year'
                )
        result.append(
            StorefrontPrice(
                price_id=row['id'],
                interval=interval,
                currency=row['currency'],
                amount_minor=amount,
                formatted_amount=f'{_money(amount)}/{"mo" if interval == "month" else "yr"}',
                monthly_equivalent=f'{_money(Decimal(amount) / (12 if interval == "year" else 1))}/mo',
                annual_savings=savings,
            )
        )
    return result


def _features(tier: dict[str, Any]) -> list[PlanFeature]:
    pro = tier['plan_id'] in {'operator', 'architect'}
    return [
        PlanFeature(key='core_desktop', label='Capture, conversations, chat, memories and search'),
        PlanFeature(key='managed_usage_budget', label='Managed AI uses your shared monthly budget'),
        PlanFeature(
            key='mcp_daily_cap',
            label=f'MCP + developer API: {"at least " if tier["plan_id"] == "architect" else ""}{tier["mcp_daily_cap"]:,} requests/day',
        ),
        PlanFeature(key='proactive_agent', label='Proactive agent', included=pro),
        PlanFeature(key='screen_context', label='Screen context', included=pro),
    ]


def build_storefront(
    *,
    catalog_revision: int,
    ladder: dict[str, Any],
    bindings: list[str],
    recognized: list[dict[str, Any]],
    subscription: Subscription,
    retrieve_price: Callable[[str], dict[str, Any]],
    purchasable: Callable[[str], bool],
    usage: StorefrontUsage,
    source: str | None = None,
    trigger: str | None = None,
) -> StorefrontResponse:
    current_plan = subscription.plan.value
    # Sources use the Paywall Opened vocabulary (#21337). A separate trigger
    # carries gate semantics because a surface (e.g. settings) is not a gate.
    recommended_plan = (
        'operator' if trigger in {'proactive_agent', 'screen_context'} or current_plan != 'basic' else 'plus'
    )
    current_price = subscription.current_price_id
    # Missing historical price never implies the new entitlement version.
    legacy = current_plan != 'basic' and current_price not in bindings
    ranks = {tier['plan_id']: rank for rank, tier in enumerate(ladder['tiers'])}
    current_rank = ranks.get(current_plan)
    tiers: list[StorefrontTier] = []
    for tier in ladder['tiers']:
        plan = tier['plan_id']
        rows: list[dict[str, Any]] = []
        for registration in recognized:
            price_id = registration['price_id']
            if (
                price_id in bindings
                and registration['plan_id'] == plan
                and registration.get('entitlement_version') == 'ladder_v1'
                and purchasable(price_id)
            ):
                try:
                    row = retrieve_price(price_id)
                    if (
                        row.get('id') == price_id
                        and (row.get('recurring') or {}).get('interval') == registration['interval']
                    ):
                        rows.append(row)
                except Exception:
                    # Caller owns provider-error telemetry; omit unusable prices.
                    continue
        prices = present_prices(rows)
        if plan == 'basic':
            prices = [
                StorefrontPrice(
                    interval='month',
                    currency='usd',
                    amount_minor=0,
                    formatted_amount='$0.00/mo',
                    monthly_equivalent='$0.00/mo',
                )
            ]
        # Do not sell legacy prices with ladder-v1 feature claims. Architect remains
        # a visible contact tier until its new prices and live amount are approved.
        if plan != 'basic' and not prices and plan != 'architect':
            continue
        if plan == current_plan and not legacy:
            action = 'current'
        elif legacy and plan == current_plan:
            action = 'contact'
        elif current_rank is not None and ranks[plan] <= current_rank:
            action = 'downgrade_not_offered'
        elif legacy or not prices:
            action = 'contact'
        else:
            action = 'upgrade'
        tiers.append(
            StorefrontTier(
                tier_id=f'{plan}:ladder_v1',
                plan_id=plan,
                entitlement_version='ladder_v1',
                display_name=tier['display_name'],
                tagline=tier['tagline'],
                features=_features(tier),
                prices=prices,
                action=action,
                recommended=plan == recommended_plan,
            )
        )
    if legacy or (current_plan != 'basic' and not any(tier.action == 'current' for tier in tiers)):
        rows = []
        if current_price:
            try:
                row = retrieve_price(current_price)
                if row.get('id') == current_price:
                    rows.append(row)
            except Exception:
                pass
        name = next(
            (tier['display_name'] for tier in ladder['tiers'] if tier['plan_id'] == current_plan),
            {'unlimited': 'Neo', 'unlimited_v2': 'Unlimited'}.get(current_plan, current_plan),
        )
        tiers.append(
            StorefrontTier(
                tier_id=f'{current_plan}:{"legacy" if legacy else "ladder_v1"}',
                plan_id=current_plan,
                entitlement_version='legacy' if legacy else 'ladder_v1',
                display_name=name,
                tagline='Your current plan',
                legacy=legacy,
                action='current',
                features=(
                    [PlanFeature(key='legacy_entitlements', label='Your existing benefits stay the same')]
                    if legacy
                    else _features(next(tier for tier in ladder['tiers'] if tier['plan_id'] == current_plan))
                ),
                prices=present_prices(rows, current=True),
            )
        )
    tiers.sort(key=lambda tier: (ranks.get(tier.plan_id, len(ranks)), not tier.legacy))
    next_offer = next((tier.tier_id for tier in tiers if tier.action == 'upgrade'), None)
    return StorefrontResponse(
        catalog_revision=catalog_revision,
        tiers=tiers,
        next_offer_tier_id=next_offer,
        current=StorefrontCurrentPlan(plan_id=current_plan, price_id=current_price, legacy=legacy),
        usage=usage,
    )
