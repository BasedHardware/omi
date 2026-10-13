"""Backend-only presentation policy. Does not grant entitlements or mutate billing."""

from functools import lru_cache
from pathlib import Path
import json
from typing import Any, Callable

from models.storefront import (
    StorefrontCurrent,
    StorefrontPrice,
    StorefrontResponse,
    StorefrontTier,
    StorefrontUsage,
)
from models.users import Subscription
from utils.storefront_copy import (
    bullets,
    cta_label,
    current_line,
    header,
    hours_line,
    plan_name,
    render_price,
    yearly_toggle_label,
)

RANK = {'basic': 0, 'plus': 1, 'operator': 2, 'architect': 3}
UNRANKED_HIGHER = {'operator', 'architect'}


@lru_cache(maxsize=1)
def load_ladder() -> dict[str, Any]:
    return json.loads((Path(__file__).resolve().parents[1] / 'config/storefront_ladder.json').read_text())


def is_legacy_plan(plan: str, price_id: str | None, bindings: set[str]) -> bool:
    if plan == 'basic':
        return False
    if plan not in RANK:
        return True
    return price_id not in bindings


def tier_action(*, current_plan: str, tier_plan: str, legacy: bool, cancel: bool) -> str:
    """checkout, current, or none. Legacy never checks out. Cancel offers Resubscribe on the current tier."""
    if tier_plan == current_plan:
        if legacy or current_plan == 'basic' or not cancel:
            return 'current'
        return 'checkout'
    if legacy:
        return 'none'
    current_rank = RANK.get(current_plan)
    tier_rank = RANK.get(tier_plan)
    if current_rank is None or tier_rank is None:
        return 'none'
    if tier_rank <= current_rank:
        return 'none'
    return 'checkout'


def is_higher_offer(current_plan: str, tier_plan: str) -> bool:
    if tier_plan == current_plan:
        return False
    if current_plan not in RANK:
        return tier_plan in UNRANKED_HIGHER
    current_rank = RANK.get(current_plan)
    tier_rank = RANK.get(tier_plan)
    if current_rank is None or tier_rank is None:
        return False
    return tier_rank > current_rank


def recommended_plan_id(current_plan: str, trigger: str | None) -> str | None:
    """Badge only. Pro and Architect are never badged; a badge is not a selection."""
    if current_plan in {'operator', 'architect'}:
        return None
    if trigger in {'proactive_agent', 'screen_context'} or current_plan != 'basic':
        return 'operator'
    return 'plus'


def offered_intervals(
    *, current_plan: str, tier_plan: str, current_interval: str | None, available: list[str]
) -> list[str]:
    """Same tier: annual → monthly is not offered; monthly → annual stays available."""
    ordered = [interval for interval in ('month', 'year') if interval in available]
    if tier_plan == current_plan and current_interval == 'year':
        return [interval for interval in ordered if interval != 'month']
    return ordered


def _valid_price_rows(rows: list[dict[str, Any]], *, current: bool = False) -> list[dict[str, Any]]:
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
    return valid


def _prices_for(
    rows: list[dict[str, Any]],
    *,
    offered: list[str],
    locale: str | None,
    current: bool = False,
) -> list[StorefrontPrice]:
    valid = _valid_price_rows(rows, current=current)
    monthly = next((row for row in valid if row['recurring']['interval'] == 'month'), None)
    monthly_minor = monthly['unit_amount'] if monthly else None
    rendered = []
    for interval in offered:
        row = next((item for item in valid if item['recurring']['interval'] == interval), None)
        if row is None:
            continue
        rendered.append(
            StorefrontPrice(
                **render_price(
                    price_id=row['id'],
                    interval=interval,
                    amount_minor=row['unit_amount'],
                    currency=row['currency'],
                    monthly_minor=monthly_minor,
                    locale=locale,
                )
            )
        )
    return rendered


def _free_price(currency: str, locale: str | None) -> StorefrontPrice:
    rendered = render_price(
        price_id=None, interval='month', amount_minor=0, currency=currency, monthly_minor=None, locale=locale
    )
    # The paid renewal sentence does not apply to the zero price.
    rendered['renewal_line'] = None
    return StorefrontPrice(**rendered)


def _retrieve(retrieve_price: Callable[[str], dict[str, Any]], price_id: str | None) -> dict[str, Any] | None:
    if not price_id:
        return None
    try:
        row = retrieve_price(price_id)
    except Exception:
        return None
    if isinstance(row, dict) and row.get('id') == price_id:
        return row
    return None


def _mcp_cap(ladder: dict[str, Any], plan_id: str) -> int | None:
    for tier in ladder.get('tiers', []):
        if tier.get('plan_id') == plan_id and type(tier.get('mcp_daily_cap')) is int:
            return tier['mcp_daily_cap']
    return None


def _sheet_months_free(tiers: list[StorefrontTier]) -> int | None:
    found: list[int] = []
    for tier in tiers:
        yearly = next((price for price in tier.prices if price.interval == 'year'), None)
        if yearly is None or yearly.months_free is None:
            continue
        if yearly.months_free >= 1:
            found.append(yearly.months_free)
    if not found:
        return None
    return min(found)


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
    locale: str | None = None,
) -> StorefrontResponse:
    del source  # Opening surface is accepted; header selection uses trigger, legacy, and usage.
    current_plan = subscription.plan.value
    current_price_id = subscription.current_price_id
    binding_set = set(bindings)
    legacy = is_legacy_plan(current_plan, current_price_id, binding_set)
    current_row = _retrieve(retrieve_price, current_price_id)
    current_interval = None
    current_amount = None
    if current_row and (current_row.get('recurring') or {}).get('interval') in {'month', 'year'}:
        current_interval = current_row['recurring']['interval']
        if type(current_row.get('unit_amount')) is int:
            current_amount = current_row['unit_amount']
    badge = recommended_plan_id(current_plan, trigger)
    currency = ladder.get('currency') if isinstance(ladder.get('currency'), str) else 'usd'
    tiers: list[StorefrontTier] = []
    for tier in ladder['tiers']:
        plan = tier['plan_id']
        if legacy and plan == current_plan:
            continue
        rows: list[dict[str, Any]] = []
        for registration in recognized:
            price_id = registration['price_id']
            if (
                price_id in binding_set
                and registration['plan_id'] == plan
                and registration.get('entitlement_version') == 'ladder_v1'
                and purchasable(price_id)
            ):
                row = _retrieve(retrieve_price, price_id)
                if row and (row.get('recurring') or {}).get('interval') == registration['interval']:
                    rows.append(row)
        available = [row['recurring']['interval'] for row in _valid_price_rows(rows)]
        if plan == 'basic':
            available = ['month']
        offered = offered_intervals(
            current_plan=current_plan, tier_plan=plan, current_interval=current_interval, available=available
        )
        if plan == 'basic':
            prices = [_free_price(currency, locale)]
        else:
            prices = _prices_for(rows, offered=offered, locale=locale)
        if plan != 'basic' and not prices and plan != 'architect':
            continue
        action = tier_action(
            current_plan=current_plan,
            tier_plan=plan,
            legacy=legacy,
            cancel=subscription.cancel_at_period_end,
        )
        if action == 'checkout' and not prices and plan != current_plan:
            action = 'none'
        is_current = plan == current_plan and not legacy
        tiers.append(
            StorefrontTier(
                tier_id=f'{plan}:ladder_v1',
                plan_id=plan,
                name=plan_name(plan, ladder),
                recommended=plan == badge and is_higher_offer(current_plan, plan),
                is_current=is_current,
                hours_line=hours_line(plan, locale),
                bullets=bullets(plan, trigger, locale),
                action=action,
                cta_label=cta_label(action=action, tier_plan=plan, current_plan=current_plan, locale=locale),
                prices=prices,
            )
        )
    if legacy or (current_plan != 'basic' and not any(tier.is_current for tier in tiers)):
        action = tier_action(
            current_plan=current_plan,
            tier_plan=current_plan,
            legacy=legacy,
            cancel=subscription.cancel_at_period_end,
        )
        current_prices: list[StorefrontPrice] = []
        if current_row:
            available = [current_interval] if current_interval else []
            offered = offered_intervals(
                current_plan=current_plan,
                tier_plan=current_plan,
                current_interval=current_interval,
                available=available,
            )
            current_prices = _prices_for([current_row], offered=offered, locale=locale, current=True)
        tiers.append(
            StorefrontTier(
                tier_id=f'{current_plan}:{"legacy" if legacy else "ladder_v1"}',
                plan_id=current_plan,
                name=plan_name(current_plan, ladder),
                recommended=False,
                is_current=True,
                hours_line='' if legacy or current_plan not in RANK else hours_line(current_plan, locale),
                bullets=[] if legacy or current_plan not in RANK else bullets(current_plan, trigger, locale),
                action=action,
                cta_label=cta_label(action=action, tier_plan=current_plan, current_plan=current_plan, locale=locale),
                prices=current_prices,
            )
        )
    tiers.sort(key=lambda tier: (not tier.recommended, RANK.get(tier.plan_id, len(RANK)), tier.plan_id))
    line, note = current_line(
        plan_id=current_plan,
        plan_name_text=plan_name(current_plan, ladder),
        amount_minor=current_amount,
        interval=current_interval,
        period_end=subscription.current_period_end,
        cancel=subscription.cancel_at_period_end,
        legacy=legacy,
        locale=locale,
    )
    return StorefrontResponse(
        catalog_revision=catalog_revision,
        header=header(
            legacy=legacy,
            trigger=trigger,
            percent=usage.percent,
            mcp_daily_cap=_mcp_cap(ladder, current_plan),
            locale=locale,
        ),
        tiers=tiers,
        current=StorefrontCurrent(
            plan_id=current_plan,
            name=plan_name(current_plan, ladder),
            price_id=current_price_id,
            interval=current_interval,
            legacy=legacy,
            cancel_at_period_end=subscription.cancel_at_period_end,
            line=line,
            legacy_note=note,
        ),
        usage=usage,
        yearly_toggle_label=yearly_toggle_label(_sheet_months_free(tiers), locale),
    )
