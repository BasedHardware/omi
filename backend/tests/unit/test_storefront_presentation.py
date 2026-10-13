"""Schema v2 copy, hours, policy matrix, and golden plans-sheet fixtures."""

import json
import os
from datetime import datetime, timezone
from decimal import Decimal
from itertools import product
from pathlib import Path

import pytest

import config.plan_catalog_generated as catalog
from models.storefront import StorefrontUsage
from models.users import PlanType, Subscription
from utils.storefront import (
    build_storefront,
    is_legacy_plan,
    load_ladder,
    offered_intervals,
    tier_action,
)
from utils.storefront_copy import (
    cta_label,
    floor_to_nice,
    hours_line,
    money,
    months_free,
    months_free_phrase,
    per_day_phrase,
    present_usage,
    recording_hours,
    recording_hours_left,
    render_price,
    yearly_switch_label,
    yearly_toggle_label,
)

PERIOD_END = int(datetime(2026, 11, 1, tzinfo=timezone.utc).timestamp())
GOLDEN_DIR = Path(__file__).resolve().parents[1] / 'fixtures' / 'storefront_v2'
PLANS = ('basic', 'plus', 'operator', 'architect', 'unlimited', 'unlimited_v2')
LADDER = ('basic', 'plus', 'operator', 'architect')
INTERVALS = ('month', 'year')


def price(identifier, amount, interval='month', **overrides):
    return {
        'id': identifier,
        'currency': 'usd',
        'unit_amount': amount,
        'active': True,
        'recurring': {'interval': interval, 'interval_count': 1},
        **overrides,
    }


def ladder_catalog():
    rows, recognized = {}, []
    for plan, monthly in (('plus', 1999), ('operator', 4999), ('architect', 19900)):
        for interval, amount in (('month', monthly), ('year', monthly * 10)):
            key = f'price_{plan}_{interval}'
            rows[key] = price(key, amount, interval)
            recognized.append(
                {'price_id': key, 'plan_id': plan, 'interval': interval, 'entitlement_version': 'ladder_v1'}
            )
    return rows, recognized


def sheet_for(
    plan,
    *,
    price_id=None,
    rows=None,
    bindings=None,
    recognized=None,
    cancel=False,
    trigger=None,
    source=None,
    locale=None,
    percent=None,
    period_end=None,
):
    usage = StorefrontUsage(
        **present_usage(
            plan_id=plan,
            kind='usage_budget' if percent is not None else 'unavailable',
            percent=percent,
            reset_at=PERIOD_END if percent is not None else None,
            locale=locale,
        )
    )
    return build_storefront(
        catalog_revision=catalog.CATALOG_REVISION,
        ladder=load_ladder(),
        bindings=list(bindings or []),
        recognized=recognized or [],
        subscription=Subscription(
            plan=PlanType(plan),
            current_price_id=price_id,
            cancel_at_period_end=cancel,
            current_period_end=period_end,
        ),
        retrieve_price=lambda key: (rows or {})[key],
        purchasable=lambda key: True,
        usage=usage,
        source=source,
        trigger=trigger,
        locale=locale,
    )


def test_recording_hours_match_the_deck():
    assert not hasattr(catalog, 'USAGE_BUDGET_UNITS')
    assert (
        recording_hours('basic'),
        recording_hours('plus'),
        recording_hours('operator'),
        recording_hours('architect'),
    ) == (
        15,
        100,
        280,
        1200,
    )
    assert hours_line('basic') == 'About 15 hours of recording a month'
    assert hours_line('plus') == 'About 100 hours of recording a month, around 3 hours a day'
    assert hours_line('operator') == 'About 280 hours of recording a month, enough to wear it all day'
    assert hours_line('architect') == 'About 1,200 hours of recording a month, for all-day use on more than one device'


def test_floor_to_nice_and_per_day_phrasing():
    assert floor_to_nice(Decimal('15.6')) == 15
    assert floor_to_nice(Decimal('17.5')) == 20
    assert floor_to_nice(Decimal('30')) == 30
    assert floor_to_nice(Decimal('106.969230769')) == 100
    assert floor_to_nice(Decimal('288.280769230')) == 280
    assert floor_to_nice(Decimal('299.9')) == 290
    assert floor_to_nice(Decimal('300')) == 300
    assert floor_to_nice(Decimal('1238.796153846')) == 1200
    assert per_day_phrase(15) == 'about 1 hours a day'
    assert per_day_phrase(100) == 'about 3 hours a day'
    assert per_day_phrase(179) == 'about 6 hours a day'
    assert per_day_phrase(180) == 'enough to wear it all day'
    assert per_day_phrase(280) == 'enough to wear it all day'
    assert per_day_phrase(480) == 'enough to wear it all day'
    assert per_day_phrase(481) == 'for wearing it all day, every day, on more than one device'
    assert per_day_phrase(1200) == 'for wearing it all day, every day, on more than one device'
    assert recording_hours_left('plus', 80) == 20
    assert recording_hours_left('basic', 80) == 3
    assert months_free(4999, 49990) == 2


def test_one_month_free_is_singular_and_yearly_switch_uses_the_price_currency():
    assert months_free(1000, 11000) == 1
    assert months_free_phrase(1) == '1 month free'
    assert months_free_phrase(2) == '2 months free'
    rendered = render_price(
        price_id='price_year',
        interval='year',
        amount_minor=11000,
        currency='usd',
        monthly_minor=1000,
    )
    assert rendered['subline'] == '$110.00 billed yearly · 1 month free'
    assert rendered['months_free'] == 1
    assert yearly_toggle_label(1) == 'Yearly · 1 month free'
    assert yearly_toggle_label(2) == 'Yearly · 2 months free'
    assert yearly_switch_label(monthly_minor=1999, annual_minor=19990, currency='usd') == (
        'Switch to yearly · save $39.98'
    )
    assert yearly_switch_label(monthly_minor=1999, annual_minor=1999 * 12, currency='usd') is None
    euro = yearly_switch_label(monthly_minor=1999, annual_minor=19990, currency='eur')
    assert euro == 'Switch to yearly · save 39.98 EUR'


def expected_action(current, tier, legacy, cancel):
    rank = {'basic': 0, 'plus': 1, 'operator': 2, 'architect': 3}
    if tier == current:
        if legacy or current == 'basic' or not cancel:
            return 'current'
        return 'checkout'
    if legacy or (cancel and current in rank and current != 'basic'):
        return 'none'
    if current not in rank or tier not in rank or rank[tier] <= rank[current]:
        return 'none'
    return 'checkout'


def expected_intervals(current, tier, interval, available):
    ordered = [item for item in ('month', 'year') if item in available]
    if tier == current and interval == 'year':
        return [item for item in ordered if item != 'month']
    return ordered


def expected_cta(current, tier, action):
    if action != 'checkout':
        return None
    if tier == current:
        return 'Resubscribe'
    if tier == 'plus':
        return 'Get Plus'
    if tier == 'operator':
        return 'Get Pro' if current == 'basic' else 'Upgrade to Pro'
    if tier == 'architect':
        return 'Get Architect' if current == 'basic' else 'Upgrade to Architect'
    return None


@pytest.mark.parametrize('current', PLANS)
@pytest.mark.parametrize('interval', INTERVALS)
@pytest.mark.parametrize('cancel', (False, True))
@pytest.mark.parametrize('legacy', (False, True))
@pytest.mark.parametrize('tier', PLANS)
def test_policy_matrix(current, interval, cancel, legacy, tier):
    action = tier_action(current_plan=current, tier_plan=tier, legacy=legacy, cancel=cancel)
    assert action == expected_action(current, tier, legacy, cancel)
    if tier == 'basic':
        available = ['month']
    elif tier in {'plus', 'operator', 'architect'}:
        available = ['month', 'year']
    else:
        available = [interval]
    assert offered_intervals(
        current_plan=current, tier_plan=tier, current_interval=interval, available=available
    ) == expected_intervals(current, tier, interval, available)
    assert cta_label(action=action, tier_plan=tier, current_plan=current) == expected_cta(current, tier, action)
    if legacy:
        assert action != 'checkout'


def test_built_sheets_match_the_policy_matrix():
    base_rows, recognized = ladder_catalog()
    cases = []
    for cancel in (False, True):
        cases.append(('basic', 'month', cancel, False, None))
    for plan in ('unlimited', 'unlimited_v2'):
        for interval, cancel in product(INTERVALS, (False, True)):
            cases.append((plan, interval, cancel, True, f'price_legacy_{plan}_{interval}'))
    for plan in ('plus', 'operator', 'architect'):
        for interval, cancel, legacy in product(INTERVALS, (False, True), (False, True)):
            price_id = f'price_old_{plan}_{interval}' if legacy else f'price_{plan}_{interval}'
            cases.append((plan, interval, cancel, legacy, price_id))
    for plan, interval, cancel, legacy, price_id in cases:
        rows = dict(base_rows)
        if price_id and price_id not in rows:
            rows[price_id] = price(price_id, 2999, interval)
        built = sheet_for(
            plan,
            price_id=price_id,
            rows=rows,
            bindings=list(base_rows),
            recognized=recognized,
            cancel=cancel,
            period_end=None if plan == 'basic' else PERIOD_END,
        )
        assert is_legacy_plan(plan, price_id, set(base_rows)) is legacy
        assert built.current.legacy is legacy
        assert not (legacy and any(tier.action == 'checkout' for tier in built.tiers))
        for tier in built.tiers:
            assert tier.action == expected_action(plan, tier.plan_id, legacy, cancel)
            if not tier.is_current:
                continue
            if plan == 'basic':
                available = ['month']
            elif legacy:
                available = [interval]
            else:
                available = ['month', 'year']
            assert [item.interval for item in tier.prices] == expected_intervals(plan, plan, interval, available)
        resubscribe_only = cancel and not legacy and plan in LADDER and plan != 'basic'
        if resubscribe_only:
            assert built.header == f"Your {built.current.name} plan ends Nov 1"
            current_amount = next(item.amount_minor for item in built.tiers[0].prices if item.interval == interval)
            period = 'mo' if interval == 'month' else 'yr'
            assert built.current.line == f"You're on {built.current.name} · {money(current_amount)}/{period}"
            assert built.tiers[0].is_current
            assert not any(tier.recommended for tier in built.tiers)
            for tier in built.tiers:
                if tier.is_current:
                    assert tier.action == 'checkout' and tier.cta_label == 'Resubscribe'
                    assert tier.blocked_line is None and tier.compact is False
                    assert all(item.cta_label is None for item in tier.prices)
                else:
                    assert tier.action == 'none' and tier.cta_label is None
                    assert tier.blocked_line == 'Resubscribe first to change plans'
                    assert tier.compact is False
        elif not legacy and plan in {'plus', 'operator', 'architect'}:
            current_tier = next(tier for tier in built.tiers if tier.is_current)
            if interval == 'month':
                yearly = next(item for item in current_tier.prices if item.interval == 'year')
                assert yearly.cta_label is not None and yearly.cta_label.startswith('Switch to yearly · save $')
                assert current_tier.compact is False and current_tier.cta_label is None
            else:
                assert current_tier.compact is True
                assert all(item.cta_label is None for item in current_tier.prices)
        if plan == 'basic':
            assert next(tier for tier in built.tiers if tier.is_current).compact is True


def _scenario(name):
    rows, recognized = ladder_catalog()
    common = {'rows': rows, 'bindings': list(rows), 'recognized': recognized, 'period_end': PERIOD_END}
    if name == 'free_settings':
        return sheet_for(
            'basic', source='settings', period_end=None, rows=rows, bindings=list(rows), recognized=recognized
        )
    if name == 'free_budget80':
        return sheet_for(
            'basic',
            trigger='usage_budget',
            percent=80,
            period_end=None,
            **{k: common[k] for k in ('rows', 'bindings', 'recognized')},
        )
    if name == 'free_pro_gate_proactive':
        return sheet_for(
            'basic',
            trigger='proactive_agent',
            period_end=None,
            **{k: common[k] for k in ('rows', 'bindings', 'recognized')},
        )
    if name == 'free_pro_gate_screen':
        return sheet_for(
            'basic',
            trigger='screen_context',
            period_end=None,
            **{k: common[k] for k in ('rows', 'bindings', 'recognized')},
        )
    if name == 'free_mcp_cap':
        return sheet_for(
            'basic',
            trigger='mcp_daily_cap',
            period_end=None,
            **{k: common[k] for k in ('rows', 'bindings', 'recognized')},
        )
    if name == 'plus_budget80':
        return sheet_for('plus', price_id='price_plus_month', trigger='usage_budget', percent=80, **common)
    if name == 'plus_monthly_yearly_toggle':
        return sheet_for('plus', price_id='price_plus_month', source='settings', **common)
    if name == 'plus_annual_current':
        return sheet_for('plus', price_id='price_plus_year', source='settings', **common)
    if name == 'pro_settings':
        return sheet_for('operator', price_id='price_operator_month', source='settings', **common)
    if name == 'architect_settings':
        return sheet_for('architect', price_id='price_architect_month', source='settings', **common)
    if name == 'legacy_unlimited':
        rows = dict(rows)
        rows['price_legacy_unlimited'] = price('price_legacy_unlimited', 2999)
        return sheet_for(
            'unlimited',
            price_id='price_legacy_unlimited',
            rows=rows,
            bindings=list(recognized and common['bindings']),
            recognized=recognized,
            source='settings',
            period_end=PERIOD_END,
        )
    if name == 'cancel_scheduled_plus':
        return sheet_for('plus', price_id='price_plus_month', cancel=True, source='settings', **common)
    raise AssertionError(name)


SCENARIOS = (
    'free_settings',
    'free_budget80',
    'free_pro_gate_proactive',
    'free_pro_gate_screen',
    'free_mcp_cap',
    'plus_budget80',
    'plus_monthly_yearly_toggle',
    'plus_annual_current',
    'pro_settings',
    'architect_settings',
    'legacy_unlimited',
    'cancel_scheduled_plus',
)


def _dump(sheet) -> str:
    return json.dumps(sheet.model_dump(mode='json'), indent=2, ensure_ascii=False) + '\n'


def test_golden_storefront_scenarios():
    rendered = {name: _scenario(name) for name in SCENARIOS}
    free = rendered['free_settings']
    assert free.header == 'Choose your plan'
    assert free.current.line == "You're on Free"
    assert [tier.plan_id for tier in free.tiers] == ['plus', 'basic', 'operator', 'architect']
    assert next(tier for tier in free.tiers if tier.is_current).compact is True
    assert rendered['free_budget80'].header == "You've used 80% of this month's usage"
    assert rendered['free_budget80'].usage.meter_line == ('80% used · about 3 hours of recording left · resets Nov 1')
    assert rendered['free_budget80'].usage.nudge_line == ("You've used 80% of this month's usage · resets Nov 1")
    assert rendered['free_pro_gate_proactive'].header == 'Reminders and follow-ups come with Pro'
    proactive = next(tier for tier in rendered['free_pro_gate_proactive'].tiers if tier.plan_id == 'operator')
    assert proactive.bullets[0] == "Omi reminds you of things you said you'd do"
    assert rendered['free_pro_gate_screen'].header == 'Screen help comes with Pro'
    screen = next(tier for tier in rendered['free_pro_gate_screen'].tiers if tier.plan_id == 'operator')
    assert screen.bullets[0] == "On your Mac, Omi can see what you're working on and help with it"
    assert rendered['free_mcp_cap'].header == "You've used today's 100 MCP requests"
    assert all('MCP requests' in tier.bullets[0] for tier in rendered['free_mcp_cap'].tiers)
    plus80 = rendered['plus_budget80']
    assert plus80.current.line == "You're on Plus · $19.99/mo · renews Nov 1"
    assert plus80.usage.meter_line == '80% used · about 20 hours of recording left · resets Nov 1'
    annual = rendered['plus_annual_current']
    assert annual.current.line == "You're on Plus · $199.90/yr · renews Nov 1"
    plus_card = next(tier for tier in annual.tiers if tier.plan_id == 'plus')
    assert [item.interval for item in plus_card.prices] == ['year']
    assert plus_card.compact is True and plus_card.cta_label is None
    assert all(item.cta_label is None for item in plus_card.prices)
    switched = rendered['plus_monthly_yearly_toggle']
    assert switched.header == 'Choose your plan'
    plus_month = next(tier for tier in switched.tiers if tier.plan_id == 'plus')
    assert plus_month.action == 'current' and plus_month.cta_label is None and plus_month.compact is False
    assert next(item for item in plus_month.prices if item.interval == 'month').cta_label is None
    assert next(item for item in plus_month.prices if item.interval == 'year').cta_label == (
        'Switch to yearly · save $39.98'
    )
    assert rendered['pro_settings'].current.line == "You're on Pro · $49.99/mo · renews Nov 1"
    assert rendered['architect_settings'].current.line == "You're on Architect · $199.00/mo · renews Nov 1"
    legacy = rendered['legacy_unlimited']
    assert legacy.header == 'Your plan'
    assert legacy.current.line == "You're on Neo · $29.99/mo · renews Nov 1"
    assert legacy.current.legacy_note == "We don't sell this plan anymore, but yours stays exactly as it is."
    assert not any(tier.action == 'checkout' for tier in legacy.tiers)
    assert {tier.plan_id for tier in legacy.tiers if tier.action == 'none'} >= {
        'operator',
        'architect',
        'basic',
        'plus',
    }
    cancelled = rendered['cancel_scheduled_plus']
    assert cancelled.header == 'Your Plus plan ends Nov 1'
    assert cancelled.current.line == "You're on Plus · $19.99/mo"
    assert [tier.plan_id for tier in cancelled.tiers][0] == 'plus'
    assert not any(tier.recommended for tier in cancelled.tiers)
    current_plus = next(tier for tier in cancelled.tiers if tier.is_current)
    assert current_plus.action == 'checkout' and current_plus.cta_label == 'Resubscribe'
    assert current_plus.blocked_line is None and current_plus.compact is False
    assert all(item.cta_label is None for item in current_plus.prices)
    assert all(
        tier.action == 'none' and tier.cta_label is None and tier.blocked_line == 'Resubscribe first to change plans'
        for tier in cancelled.tiers
        if not tier.is_current
    )
    assert all(rendered[name].yearly_toggle_label == 'Yearly · 2 months free' for name in SCENARIOS)
    french = sheet_for('basic', locale='fr-FR', rows={}, bindings=[], recognized=[])
    assert french.header == 'Choose your plan'

    GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
    for name in SCENARIOS:
        path = GOLDEN_DIR / f'{name}.json'
        payload = _dump(rendered[name])
        if os.environ.get('UPDATE_STOREFRONT_GOLDENS') == '1':
            path.write_text(payload, encoding='utf-8')
        assert path.read_text(encoding='utf-8') == payload
