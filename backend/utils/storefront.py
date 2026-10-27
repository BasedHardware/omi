"""Backend-only presentation policy. Does not grant entitlements or mutate billing."""

from functools import lru_cache
from pathlib import Path
import json
import os
from typing import Any, Callable, Literal

from config import ladder_v1 as ladder_policy
from models.storefront import (
    StorefrontCapChoice,
    ChatAtCap,
    StorefrontCurrent,
    StorefrontPrice,
    StorefrontResponse,
    StorefrontTier,
    StorefrontUsage,
)
from models.users import Subscription
from utils.storefront_copy import (
    copy_for,
    chat_at_cap,
    format_date,
    format_money,
    blocked_line,
    bullets,
    cta_label,
    current_line,
    header,
    hours_line,
    monthly_headline,
    plan_name,
    render_price,
    yearly_switch_label,
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


def cancel_resubscribe_only(*, current_plan: str, legacy: bool, cancel: bool) -> bool:
    """Paid non-legacy cancellation: the payment API rejects every price except resubscribe."""
    return cancel and not legacy and current_plan in RANK and current_plan != 'basic'


def tier_action(
    *, current_plan: str, tier_plan: str, legacy: bool, cancel: bool
) -> Literal['checkout', 'current', 'none']:
    """checkout, current, or none. Legacy never checks out. Cancel offers Resubscribe on the current tier only."""
    if tier_plan == current_plan:
        if legacy or current_plan == 'basic' or not cancel:
            return 'current'
        return 'checkout'
    if legacy or cancel_resubscribe_only(current_plan=current_plan, legacy=legacy, cancel=cancel):
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


def is_budget_cap_surface(*, trigger: str | None, percent: float | int | None) -> bool:
    """Exhausted monthly budget. ``usage_budget`` below 100 is the 80% surface.

    Header copy already splits that one trigger: percent >= 100 is
    ``budget_100``, otherwise ``budget_80``. There is no second trigger.
    Other triggers, including settings (no trigger), are not budget surfaces.
    """
    if trigger != 'usage_budget' or isinstance(percent, bool) or not isinstance(percent, (int, float)):
        return False
    return percent >= 100


def include_architect_card(
    *,
    current_plan: str,
    resubscribe_only: bool,
    trigger: str | None,
    percent: float | int | None,
) -> bool:
    """Pro omits Architect except when the monthly budget is exhausted.

    Cancel-scheduled Pro still lists Architect, blocked, because that sheet
    shows every ladder tier and the only purchase is Resubscribe.
    """
    if current_plan != 'operator' or resubscribe_only:
        return True
    return is_budget_cap_surface(trigger=trigger, percent=percent)


def recommended_plan_id(
    current_plan: str,
    trigger: str | None,
    *,
    budget_cap: bool = False,
    legacy: bool = False,
) -> str | None:
    """Badge only. A badge is not a selection.

    Pro is badged Architect only on the exhausted surface, and only when that
    card can check out. Legacy Pro never checks out, so it is not badged.
    """
    if current_plan == 'architect':
        return None
    if current_plan == 'operator':
        if legacy or not budget_cap:
            return None
        return 'architect'
    if trigger in {'proactive_agent', 'screen_context'} or current_plan != 'basic':
        return 'operator'
    return 'plus'


def offered_intervals(
    *,
    current_plan: str,
    tier_plan: str,
    current_interval: str | None,
    available: list[str],
    resubscribe_only: bool = False,
    legacy: bool = False,
) -> list[str]:
    """Same tier: annual → monthly is never offered.

    Monthly → annual is allowed, and that yearly price is the only one on the
    switch card. Resubscribe offers only the current interval. When the current
    price cannot be retrieved, the paid current card offers no interval, so a
    yearly subscriber is not shown the monthly price.
    """
    ordered = [interval for interval in ('month', 'year') if interval in available]
    if tier_plan != current_plan or current_plan == 'basic':
        return ordered
    if current_interval is None:
        return []
    if resubscribe_only:
        return [current_interval] if current_interval in ordered else []
    if current_interval == 'year':
        return [interval for interval in ordered if interval != 'month']
    if not legacy and 'year' in ordered:
        return ['year']
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
    switch_yearly: bool = False,
) -> list[StorefrontPrice]:
    valid = _valid_price_rows(rows, current=current)
    monthly = next((row for row in valid if row['recurring']['interval'] == 'month'), None)
    monthly_minor = monthly['unit_amount'] if monthly else None
    rendered = []
    for interval in offered:
        row = next((item for item in valid if item['recurring']['interval'] == interval), None)
        if row is None:
            continue
        payload = render_price(
            price_id=row['id'],
            interval=interval,
            amount_minor=row['unit_amount'],
            currency=row['currency'],
            monthly_minor=monthly_minor,
            locale=locale,
        )
        if switch_yearly and interval == 'year' and monthly_minor is not None:
            # The toggle can still read Monthly. Keep the headline on the price
            # the user pays; the subline and CTA carry the yearly offer.
            payload['headline'] = monthly_headline(monthly_minor, locale, currency=row['currency'])
            payload['cta_label'] = yearly_switch_label(
                monthly_minor=monthly_minor,
                annual_minor=row['unit_amount'],
                currency=row['currency'],
                locale=locale,
            )
        rendered.append(StorefrontPrice(**payload))
    return rendered


def _compact(*, is_current: bool, action: str, prices: list[StorefrontPrice]) -> bool:
    """Current card with no purchase button. Current cards already send no bullets."""
    if not is_current or action == 'checkout':
        return False
    return not any(price.cta_label for price in prices)


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
    if row.get('id') == price_id:
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
    current_currency = 'usd'
    if current_row and (current_row.get('recurring') or {}).get('interval') in {'month', 'year'}:
        current_interval = current_row['recurring']['interval']
        if type(current_row.get('unit_amount')) is int:
            current_amount = current_row['unit_amount']
        price_currency = current_row.get('currency')
        if isinstance(price_currency, str) and price_currency.strip():
            current_currency = price_currency
    resubscribe_only = cancel_resubscribe_only(
        current_plan=current_plan, legacy=legacy, cancel=subscription.cancel_at_period_end
    )
    cap_surface = is_budget_cap_surface(trigger=trigger, percent=usage.percent)
    badge = (
        None if resubscribe_only else recommended_plan_id(current_plan, trigger, budget_cap=cap_surface, legacy=legacy)
    )
    blocked = blocked_line(locale) if resubscribe_only else None
    raw_currency = ladder.get('currency')
    currency = raw_currency if isinstance(raw_currency, str) else 'usd'
    tiers: list[StorefrontTier] = []
    for tier in ladder['tiers']:
        plan = tier['plan_id']
        if legacy and plan == current_plan:
            continue
        # Paid users who are not cancel-scheduled never see Free. A scheduled
        # cancellation lists every ladder tier, lower and higher, plus Free.
        if plan == 'basic' and current_plan != 'basic' and not resubscribe_only:
            continue
        if plan == 'architect' and not include_architect_card(
            current_plan=current_plan,
            resubscribe_only=resubscribe_only,
            trigger=trigger,
            percent=usage.percent,
        ):
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
        is_current = plan == current_plan and not legacy
        switch = False
        if plan == 'basic':
            prices = [_free_price(currency, locale)]
        else:
            resubscribe_this = resubscribe_only and is_current
            offered = offered_intervals(
                current_plan=current_plan,
                tier_plan=plan,
                current_interval=current_interval,
                available=available,
                resubscribe_only=resubscribe_this,
                legacy=legacy,
            )
            want_switch = is_current and current_interval == 'month' and not resubscribe_only and 'year' in offered
            prices = _prices_for(rows, offered=offered, locale=locale, switch_yearly=want_switch)
            if want_switch and subscription.current_period_end:
                for item in prices:
                    if item.interval == 'year' and item.cta_label:
                        item.confirm_lines = [
                            line.format(
                                date=format_date(subscription.current_period_end, locale),
                                amount=format_money(item.amount_minor, item.currency),
                            )
                            for line in copy_for(locale)['prices']['confirm_yearly_lines']
                        ]
            if resubscribe_this and current_price_id:
                prices = [item for item in prices if item.price_id == current_price_id]
            switch = want_switch and any(item.cta_label for item in prices)
            if want_switch and not switch:
                month_offered = ['month'] if 'month' in available else []
                prices = _prices_for(rows, offered=month_offered, locale=locale)
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
        if switch:
            action = 'checkout'
        # A checkout button with no price_id cannot be sent. Failed retrieval
        # on a cancel-scheduled current card stays "current" with no CTA.
        if is_current and action == 'checkout' and not prices:
            action = 'current'
        # Free, while a paid cancellation is scheduled, is a plain card: no
        # bullets and no CTA, with the same blocked line as the other tiers.
        plain_free = resubscribe_only and plan == 'basic'
        tiers.append(
            StorefrontTier(
                tier_id=f'{plan}:ladder_v1',
                plan_id=plan,
                name=plan_name(plan, ladder),
                # An empty price list already demoted checkout to none. Badge only a real checkout.
                recommended=(
                    action == 'checkout' and bool(badge) and plan == badge and is_higher_offer(current_plan, plan)
                ),
                is_current=is_current,
                hours_line=hours_line(plan, locale),
                bullets=[] if is_current or plain_free else bullets(plan, trigger, locale),
                action=action,
                cta_label=(
                    None
                    if switch
                    else cta_label(action=action, tier_plan=plan, current_plan=current_plan, locale=locale)
                ),
                blocked_line=None if is_current or blocked is None else blocked,
                compact=plain_free or _compact(is_current=is_current, action=action, prices=prices),
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
        if current_row and current_interval:
            available = [current_interval]
            offered = offered_intervals(
                current_plan=current_plan,
                tier_plan=current_plan,
                current_interval=current_interval,
                available=available,
                resubscribe_only=resubscribe_only,
                legacy=legacy,
            )
            current_prices = _prices_for([current_row], offered=offered, locale=locale, current=True)
            if resubscribe_only and current_price_id:
                current_prices = [item for item in current_prices if item.price_id == current_price_id]
        if action == 'checkout' and not current_prices:
            action = 'current'
        tiers.append(
            StorefrontTier(
                tier_id=f'{current_plan}:{"legacy" if legacy else "ladder_v1"}',
                plan_id=current_plan,
                name=plan_name(current_plan, ladder),
                recommended=False,
                is_current=True,
                hours_line='' if legacy or current_plan not in RANK else hours_line(current_plan, locale),
                bullets=[],
                action=action,
                cta_label=cta_label(action=action, tier_plan=current_plan, current_plan=current_plan, locale=locale),
                blocked_line=None,
                compact=_compact(is_current=True, action=action, prices=current_prices),
                prices=current_prices,
            )
        )
    if resubscribe_only:
        tiers.sort(key=lambda tier: (not tier.is_current, RANK.get(tier.plan_id, len(RANK)), tier.plan_id))
    else:
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
        currency=current_currency,
    )
    at_cap = None
    chat_pause = None
    if (
        ladder_policy.enabled('LADDER_V1_BUDGET_ENFORCEMENT_ENABLED')
        and not legacy
        and usage.kind == 'usage_budget'
        and usage.percent is not None
        and usage.percent >= 100
        and usage.period_id is not None
    ):
        from datetime import datetime, timezone

        # usage period_id is the charged calendar month; reset is its next month.
        year, month = map(int, usage.period_id.split('-'))
        reset_at = int(datetime(year + (month == 12), month % 12 + 1, 1, tzinfo=timezone.utc).timestamp())
        chat_pause = ChatAtCap(**chat_at_cap(current_plan, reset_at, locale))
        at_cap = dict(copy_for(locale)['at_cap'])
        at_cap['body'] = at_cap['body'].format(date=format_date(reset_at, locale))
    return StorefrontResponse(
        chat_at_cap=chat_pause,
        at_cap=StorefrontCapChoice(**at_cap) if at_cap is not None else None,
        catalog_revision=catalog_revision,
        header=header(
            legacy=legacy,
            trigger=trigger,
            percent=usage.percent,
            mcp_daily_cap=_mcp_cap(ladder, current_plan),
            locale=locale,
            cancel_scheduled=resubscribe_only,
            plan_name_text=plan_name(current_plan, ladder),
            period_end=subscription.current_period_end,
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
        yearly_toggle_label=None if resubscribe_only else yearly_toggle_label(_sheet_months_free(tiers), locale),
    )


def _configured_unlimited_v2_rows(retrieve_price: Callable[[str], dict[str, Any]]) -> list[dict[str, Any]]:
    """Live Stripe rows for the configured Omi Pro (`unlimited_v2`) prices.

    Mirrors `_configured_plan_price_id(PRIMARY_BILLING_ENV_VARS[unlimited_v2])`
    in utils.subscription without importing it (that would cycle). A missing
    env price or a failed retrieval just drops that interval.
    """
    rows = []
    for interval, env in (
        ('month', 'STRIPE_UNLIMITED_V2_MONTHLY_PRICE_ID'),
        ('year', 'STRIPE_UNLIMITED_V2_ANNUAL_PRICE_ID'),
    ):
        price_id = os.getenv(env)
        if not price_id:
            continue
        row = _retrieve(retrieve_price, price_id)
        if row and (row.get('recurring') or {}).get('interval') == interval:
            rows.append(row)
    return rows


def build_single_plan_storefront(
    *,
    catalog_revision: int,
    subscription: Subscription,
    usage: StorefrontUsage,
    retrieve_price: Callable[[str], dict[str, Any]],
    trigger: str | None = None,
    locale: str | None = None,
) -> StorefrontResponse:
    """Omi Pro (`unlimited_v2`) offer sheet for a buyer with no current paid plan.

    Omi Pro is the only plan sold, on every platform. The ladder sheet has no
    Omi Pro card, so this single-tier v2 sheet is served instead; current
    subscribers keep the ladder sheet via `build_storefront`.
    """
    ladder = load_ladder()
    current_plan = subscription.plan.value
    raw_currency = ladder.get('currency')
    currency = raw_currency if isinstance(raw_currency, str) else 'usd'
    prices = _prices_for(_configured_unlimited_v2_rows(retrieve_price), offered=['month', 'year'], locale=locale)
    action: Literal['checkout', 'current', 'none'] = 'checkout' if prices else 'none'
    tier = StorefrontTier(
        tier_id='unlimited_v2:single_plan',
        plan_id='unlimited_v2',
        name=plan_name('unlimited_v2', ladder),
        recommended=bool(prices),
        is_current=False,
        hours_line=hours_line('unlimited_v2', locale),
        bullets=bullets('unlimited_v2', trigger, locale),
        action=action,
        cta_label=cta_label(action=action, tier_plan='unlimited_v2', current_plan=current_plan, locale=locale),
        blocked_line=None,
        compact=False,
        prices=prices,
    )
    # The Free current card keeps the sheet shape every other golden has (a
    # current row: no bullets, no CTA, the $0 price) so clients render the Omi
    # Pro offer next to where the buyer already is.
    free_tier = StorefrontTier(
        tier_id='basic:single_plan',
        plan_id='basic',
        name=plan_name('basic', ladder),
        recommended=False,
        is_current=True,
        hours_line=hours_line('basic', locale),
        bullets=[],
        action='current',
        cta_label=None,
        blocked_line=None,
        compact=True,
        prices=[_free_price(currency, locale)],
    )
    line, _ = current_line(
        plan_id=current_plan,
        plan_name_text=plan_name(current_plan, ladder),
        amount_minor=None,
        interval=None,
        period_end=subscription.current_period_end,
        cancel=subscription.cancel_at_period_end,
        legacy=False,
        locale=locale,
    )
    return StorefrontResponse(
        catalog_revision=catalog_revision,
        header=header(
            legacy=False,
            trigger=trigger,
            percent=usage.percent,
            mcp_daily_cap=_mcp_cap(ladder, current_plan),
            locale=locale,
            cancel_scheduled=False,
            plan_name_text=plan_name(current_plan, ladder),
            period_end=None,
        ),
        tiers=[tier, free_tier],
        current=StorefrontCurrent(
            plan_id=current_plan,
            name=plan_name(current_plan, ladder),
            price_id=subscription.current_price_id,
            interval=None,
            legacy=False,
            cancel_at_period_end=subscription.cancel_at_period_end,
            line=line,
        ),
        usage=usage,
        yearly_toggle_label=yearly_toggle_label(_sheet_months_free([tier]), locale),
    )
