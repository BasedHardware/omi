"""Schema v2 copy, hours, policy matrix, and golden plans-sheet fixtures."""

import json
import os
import re
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
    include_architect_card,
    is_budget_cap_surface,
    is_legacy_plan,
    load_ladder,
    offered_intervals,
    tier_action,
)
from utils.storefront_copy import (
    _count_template,
    _deep_merge,
    _meter_hours_line,
    copy_for,
    cta_label,
    current_line,
    load_copy,
    floor_to_nice,
    format_date,
    format_money,
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
APP_FIXTURE_DIR = Path(__file__).resolve().parents[3] / 'app' / 'test' / 'fixtures' / 'storefront_v2'
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
    assert per_day_phrase(15) == 'about 1 hour a day'
    assert per_day_phrase(60) == 'about 2 hours a day'
    assert per_day_phrase(100) == 'about 3 hours a day'
    assert per_day_phrase(179) == 'about 6 hours a day'
    assert per_day_phrase(180) == 'enough to wear it all day'
    assert per_day_phrase(280) == 'enough to wear it all day'
    assert per_day_phrase(480) == 'enough to wear it all day'
    assert per_day_phrase(481) == 'for wearing it all day, every day, on more than one device'
    assert per_day_phrase(1200) == 'for wearing it all day, every day, on more than one device'
    assert recording_hours_left('plus', 80) == 20
    assert recording_hours_left('plus', 100) == 0
    assert recording_hours_left('plus', 150) == 0
    assert recording_hours_left('basic', 80) == 3
    assert recording_hours_left('basic', 120) == 0
    assert months_free(4999, 49990) == 2


def test_meter_line_includes_hours_only_from_80_until_100():
    def usage(percent: float, plan_id: str = 'basic') -> StorefrontUsage:
        return StorefrontUsage(
            **present_usage(plan_id=plan_id, kind='usage_budget', percent=percent, reset_at=PERIOD_END)
        )

    def line(percent: float, plan_id: str = 'basic') -> str:
        return usage(percent, plan_id).meter_line

    assert line(40) == '40% used · resets Nov 1'
    assert usage(40).hours_left is None
    assert 'hours_left' not in usage(40).model_dump(mode='json')
    assert line(79) == '79% used · resets Nov 1'
    assert usage(79).hours_left is None
    assert line(80) == '80% used · about 3 hours of recording left · resets Nov 1'
    assert usage(80).hours_left == 3
    assert line(99, 'operator') == '99% used · about 5 hours of recording left · resets Nov 1'
    assert usage(99, 'operator').hours_left == 5
    # A shown percent still in the hours band can round to no hours. Omit the estimate.
    assert line(99) == '99% used · resets Nov 1'
    assert usage(99).hours_left is None
    assert 'about 0 hours' not in line(99)
    assert 'hours_left' not in usage(99).model_dump(mode='json')
    assert line(100) == '100% used · resets Nov 1'
    assert usage(100).hours_left is None
    assert 'hours_left' not in usage(100).model_dump(mode='json')
    assert 'about 0 hours' not in line(100)
    assert 'about 0 hours' not in line(140)
    legacy = StorefrontUsage(
        **present_usage(plan_id='unlimited', kind='transcription', percent=80, reset_at=PERIOD_END)
    )
    assert legacy.hours_left is None
    assert 'hours_left' not in legacy.model_dump(mode='json')
    for code, text in load_copy()['locales'].items():
        assert '{hours}' in text['meter']['line'], code
        assert '{hours}' not in text['meter']['line_short'], code


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
    assert rendered['subline'] == '$110 billed yearly · 1 month free'
    assert rendered['months_free'] == 1
    assert yearly_toggle_label(1) == 'Yearly · 1 month free'
    assert yearly_toggle_label(2) == 'Yearly · 2 months free'
    assert yearly_switch_label(monthly_minor=1999, annual_minor=19990, currency='usd') == (
        'Switch to yearly · save $39.98'
    )
    assert yearly_switch_label(monthly_minor=1999, annual_minor=1999 * 12, currency='usd') is None
    euro = yearly_switch_label(monthly_minor=1999, annual_minor=19990, currency='eur')
    assert euro == 'Switch to yearly · save 39.98 EUR'


def test_format_money_groups_whole_dollars_and_respects_zero_decimal_currencies():
    assert format_money(19900, 'usd') == '$199'
    assert format_money(39800, 'usd') == '$398'
    assert format_money(1999, 'usd') == '$19.99'
    assert format_money(1666, 'usd') == '$16.66'
    assert format_money(3998, 'usd') == '$39.98'
    assert format_money(49990, 'usd') == '$499.90'
    assert format_money(199050, 'usd') == '$1,990.50'
    assert format_money(199000, 'usd') == '$1,990'
    assert format_money(0, 'usd') == '$0'
    assert money(199000) == '$1,990'
    # JPY unit_amount is whole yen. 4800 is ¥4,800, not $48 and not 48.00 JPY.
    assert format_money(4800, 'jpy') == '4,800 JPY'
    assert format_money(199000, 'jpy') == '199,000 JPY'
    assert format_money(39800, 'eur') == '398 EUR'
    assert format_money(5120, 'kwd') == '5.120 KWD'
    # Stripe sends UGX as two-decimal even though it displays without decimals.
    assert format_money(500, 'ugx') == '5 UGX'
    rendered = render_price(
        price_id='price_jpy_year',
        interval='year',
        amount_minor=199000,
        currency='jpy',
        monthly_minor=19900,
    )
    assert rendered['headline'] == '16,583 JPY/month'
    assert rendered['subline'] == '199,000 JPY billed yearly · 2 months free'
    line, note = current_line(
        plan_id='architect',
        plan_name_text='Architect',
        amount_minor=19900,
        interval='month',
        period_end=PERIOD_END,
        cancel=False,
        legacy=False,
        currency='jpy',
    )
    assert note is None
    assert line == "You're on Architect · 19,900 JPY/mo · renews Nov 1"


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


def expected_intervals(current, tier, interval, available, *, resubscribe_only=False, legacy=False):
    ordered = [item for item in ('month', 'year') if item in available]
    if tier != current or current == 'basic':
        return ordered
    if interval is None:
        return []
    if resubscribe_only:
        return [interval] if interval in ordered else []
    if interval == 'year':
        return [item for item in ordered if item != 'month']
    if not legacy and 'year' in ordered:
        return ['year']
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
    resubscribe_only = cancel and not legacy and current in LADDER and current != 'basic'
    assert offered_intervals(
        current_plan=current,
        tier_plan=tier,
        current_interval=interval,
        available=available,
        resubscribe_only=resubscribe_only,
        legacy=legacy,
    ) == expected_intervals(current, tier, interval, available, resubscribe_only=resubscribe_only, legacy=legacy)
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
        resubscribe_only = cancel and not legacy and plan in LADDER and plan != 'basic'
        if plan != 'basic' and not resubscribe_only:
            assert all(tier.plan_id != 'basic' for tier in built.tiers)
        if plan == 'operator' and not resubscribe_only:
            assert all(tier.plan_id != 'architect' for tier in built.tiers)
        if resubscribe_only:
            ids = [tier.plan_id for tier in built.tiers]
            assert ids[0] == plan
            assert set(ids) == set(LADDER)
            rank = {'basic': 0, 'plus': 1, 'operator': 2, 'architect': 3}
            assert ids[1:] == sorted(ids[1:], key=lambda item: (rank[item], item))
            free = next(tier for tier in built.tiers if tier.plan_id == 'basic')
            assert free.action == 'none' and free.cta_label is None and free.compact is True
            assert free.bullets == [] and free.blocked_line == 'Resubscribe first to change plans'
            assert free.prices[0].headline == '$0'
        switching = not legacy and not cancel and interval == 'month' and plan in LADDER and plan != 'basic'
        for tier in built.tiers:
            expected = expected_action(plan, tier.plan_id, legacy, cancel)
            if switching and tier.is_current:
                expected = 'checkout'
            assert tier.action == expected
            if tier.is_current:
                assert tier.bullets == []
            if not tier.is_current:
                continue
            if plan == 'basic':
                available = ['month']
            elif legacy:
                available = [interval]
            else:
                available = ['month', 'year']
            assert [item.interval for item in tier.prices] == expected_intervals(
                plan, plan, interval, available, resubscribe_only=resubscribe_only, legacy=legacy
            )
        if resubscribe_only:
            assert built.yearly_toggle_label is None
            assert built.header == f"Your {built.current.name} plan ends Nov 1"
            current_amount = next(item.amount_minor for item in built.tiers[0].prices if item.interval == interval)
            period = 'mo' if interval == 'month' else 'yr'
            assert built.current.line == f"You're on {built.current.name} · {money(current_amount)}/{period}"
            assert built.tiers[0].is_current
            assert not any(tier.recommended for tier in built.tiers)
            for tier in built.tiers:
                if tier.is_current:
                    assert tier.action == 'checkout' and tier.cta_label == 'Resubscribe'
                    assert [item.price_id for item in tier.prices] == [price_id]
                    assert [item.interval for item in tier.prices] == [interval]
                    assert tier.blocked_line is None and tier.compact is False
                    assert all(item.cta_label is None for item in tier.prices)
                else:
                    assert tier.action == 'none' and tier.cta_label is None
                    assert tier.blocked_line == 'Resubscribe first to change plans'
                    assert tier.compact is (tier.plan_id == 'basic')
                    if tier.plan_id == 'basic':
                        assert tier.bullets == []
        elif not legacy and plan in {'plus', 'operator', 'architect'}:
            current_tier = next(tier for tier in built.tiers if tier.is_current)
            if interval == 'month':
                assert [item.interval for item in current_tier.prices] == ['year']
                yearly = current_tier.prices[0]
                assert yearly.headline == f'{money(yearly.amount_minor // 10)}/month'
                assert yearly.subline is not None and 'billed yearly' in yearly.subline
                assert yearly.cta_label is not None and yearly.cta_label.startswith('Switch to yearly · save $')
                assert current_tier.action == 'checkout'
                assert current_tier.compact is False and current_tier.cta_label is None
            else:
                assert [item.interval for item in current_tier.prices] == ['year']
                assert current_tier.action == 'current'
                assert current_tier.compact is True
                assert all(item.cta_label is None for item in current_tier.prices)
        if plan == 'basic':
            assert next(tier for tier in built.tiers if tier.is_current).compact is True


@pytest.mark.parametrize('plan', ('plus', 'operator', 'architect'))
@pytest.mark.parametrize('interval', INTERVALS)
def test_cancel_scheduled_sheet_lists_every_ladder_tier(plan, interval):
    rows, recognized = ladder_catalog()
    built = sheet_for(
        plan,
        price_id=f'price_{plan}_{interval}',
        rows=rows,
        bindings=list(rows),
        recognized=recognized,
        cancel=True,
        period_end=PERIOD_END,
    )
    ids = [tier.plan_id for tier in built.tiers]
    rank = {'basic': 0, 'plus': 1, 'operator': 2, 'architect': 3}
    assert ids[0] == plan
    assert set(ids) == set(LADDER)
    assert ids[1:] == sorted(ids[1:], key=lambda item: (rank[item], item))
    assert built.yearly_toggle_label is None
    assert not any(tier.recommended for tier in built.tiers)
    for tier in built.tiers:
        if tier.is_current:
            assert tier.action == 'checkout' and tier.cta_label == 'Resubscribe'
            assert [item.price_id for item in tier.prices] == [f'price_{plan}_{interval}']
            assert tier.blocked_line is None
            continue
        assert tier.action == 'none' and tier.cta_label is None
        assert tier.blocked_line == 'Resubscribe first to change plans'
        if tier.plan_id == 'basic':
            assert tier.compact is True and tier.bullets == []
            assert tier.prices[0].headline == '$0'
        else:
            assert tier.compact is False and tier.bullets


@pytest.mark.parametrize(
    'trigger,percent,source',
    [
        (None, None, 'settings'),
        ('usage_budget', 80, None),
        ('usage_budget', 99, None),
        ('usage_budget', None, None),
        ('proactive_agent', 100, None),
        ('screen_context', 100, None),
        ('mcp_daily_cap', 100, None),
        (None, 100, 'settings'),
    ],
)
def test_pro_omits_architect_off_the_cap_surface(trigger, percent, source):
    rows, recognized = ladder_catalog()
    assert is_budget_cap_surface(trigger=trigger, percent=percent) is False
    assert (
        include_architect_card(current_plan='operator', resubscribe_only=False, trigger=trigger, percent=percent)
        is False
    )
    built = sheet_for(
        'operator',
        price_id='price_operator_month',
        rows=rows,
        bindings=list(rows),
        recognized=recognized,
        trigger=trigger,
        source=source,
        percent=percent,
        period_end=PERIOD_END,
    )
    assert all(tier.plan_id != 'architect' for tier in built.tiers)
    assert all(tier.plan_id != 'basic' for tier in built.tiers)
    assert not any(tier.recommended for tier in built.tiers)


@pytest.mark.parametrize('percent', (100, 140))
def test_pro_budget_cap_recommends_architect_checkout(percent):
    rows, recognized = ladder_catalog()
    assert is_budget_cap_surface(trigger='usage_budget', percent=percent) is True
    built = sheet_for(
        'operator',
        price_id='price_operator_month',
        rows=rows,
        bindings=list(rows),
        recognized=recognized,
        trigger='usage_budget',
        percent=percent,
        period_end=PERIOD_END,
    )
    architect = next(tier for tier in built.tiers if tier.plan_id == 'architect')
    assert built.tiers[0].plan_id == 'architect'
    assert architect.recommended and architect.action == 'checkout'
    assert architect.cta_label == 'Upgrade to Architect'
    assert [tier.plan_id for tier in built.tiers if tier.recommended] == ['architect']
    assert all(tier.plan_id != 'basic' for tier in built.tiers)


@pytest.mark.parametrize('percent', (100, 140))
def test_legacy_price_pro_at_cap_lists_architect_without_checkout(percent):
    """A price outside the ladder still includes Architect at the cap, never as checkout."""
    rows, recognized = ladder_catalog()
    price_id = 'price_legacy_operator'
    priced = dict(rows)
    priced[price_id] = price(price_id, 4999)
    assert price_id not in rows
    assert is_legacy_plan('operator', price_id, set(rows)) is True
    assert (
        include_architect_card(current_plan='operator', resubscribe_only=False, trigger='usage_budget', percent=percent)
        is True
    )
    built = sheet_for(
        'operator',
        price_id=price_id,
        rows=priced,
        bindings=list(rows),
        recognized=recognized,
        trigger='usage_budget',
        percent=percent,
        period_end=PERIOD_END,
    )
    assert built.current.legacy is True
    architect = next(tier for tier in built.tiers if tier.plan_id == 'architect')
    assert architect.action == 'none'
    assert architect.recommended is False
    assert architect.cta_label is None
    assert not any(tier.action == 'checkout' for tier in built.tiers)
    assert not any(tier.recommended for tier in built.tiers)


@pytest.mark.parametrize('percent', (100, 140))
def test_pro_at_cap_without_purchasable_architect_price_is_not_recommended(percent):
    """No ladder-v1 Architect price demotes checkout, so the card is not recommended."""
    rows, recognized = ladder_catalog()
    built = build_storefront(
        catalog_revision=catalog.CATALOG_REVISION,
        ladder=load_ladder(),
        bindings=list(rows),
        recognized=recognized,
        subscription=Subscription(
            plan=PlanType.operator,
            current_price_id='price_operator_month',
            current_period_end=PERIOD_END,
        ),
        retrieve_price=lambda key: rows[key],
        purchasable=lambda key: not str(key).startswith('price_architect_'),
        usage=StorefrontUsage(
            **present_usage(
                plan_id='operator',
                kind='usage_budget',
                percent=percent,
                reset_at=PERIOD_END,
            )
        ),
        trigger='usage_budget',
    )
    architect = next(tier for tier in built.tiers if tier.plan_id == 'architect')
    assert architect.prices == []
    assert architect.action == 'none'
    assert architect.recommended is False
    assert architect.cta_label is None
    assert not any(tier.recommended for tier in built.tiers)


def test_cancel_scheduled_pro_at_cap_blocks_architect_instead_of_checkout():
    rows, recognized = ladder_catalog()
    built = sheet_for(
        'operator',
        price_id='price_operator_month',
        rows=rows,
        bindings=list(rows),
        recognized=recognized,
        trigger='usage_budget',
        percent=100,
        cancel=True,
        period_end=PERIOD_END,
    )
    assert [tier.plan_id for tier in built.tiers] == ['operator', 'basic', 'plus', 'architect']
    architect = next(tier for tier in built.tiers if tier.plan_id == 'architect')
    assert architect.action == 'none' and architect.recommended is False
    assert architect.blocked_line == 'Resubscribe first to change plans'
    assert next(tier for tier in built.tiers if tier.is_current).cta_label == 'Resubscribe'


def test_legacy_plans_still_list_architect_without_checkout():
    rows, recognized = ladder_catalog()
    for plan, amount in (('unlimited', 1999), ('unlimited_v2', 2999)):
        price_id = f'price_legacy_{plan}'
        priced = dict(rows)
        priced[price_id] = price(price_id, amount)
        built = sheet_for(
            plan,
            price_id=price_id,
            rows=priced,
            bindings=list(rows),
            recognized=recognized,
            period_end=PERIOD_END,
        )
        architect = next(tier for tier in built.tiers if tier.plan_id == 'architect')
        assert architect.action == 'none' and architect.recommended is False
        assert 'basic' not in {tier.plan_id for tier in built.tiers}
        assert not any(tier.action == 'checkout' for tier in built.tiers)


@pytest.mark.parametrize('trigger', [None, 'proactive_agent', 'screen_context', 'usage_budget', 'mcp_daily_cap'])
@pytest.mark.parametrize('percent', [None, 80, 100])
def test_plus_keeps_pro_recommended_and_lists_architect(trigger, percent):
    rows, recognized = ladder_catalog()
    built = sheet_for(
        'plus',
        price_id='price_plus_month',
        rows=rows,
        bindings=list(rows),
        recognized=recognized,
        trigger=trigger,
        percent=percent,
        period_end=PERIOD_END,
    )
    assert [tier.plan_id for tier in built.tiers if tier.recommended] == ['operator']
    architect = next(tier for tier in built.tiers if tier.plan_id == 'architect')
    assert architect.action == 'checkout' and architect.recommended is False
    assert all(tier.plan_id != 'basic' for tier in built.tiers)


@pytest.mark.parametrize(
    'plan,price_id',
    [('plus', 'price_plus_month'), ('operator', 'price_operator_month'), ('architect', 'price_architect_month')],
)
def test_cancel_scheduled_failed_price_retrieve_is_current_without_checkout(plan, price_id):
    """#21397: a cancel-scheduled card with no prices must not offer checkout."""
    rows, recognized = ladder_catalog()

    def retrieve(key):
        if key == price_id:
            raise RuntimeError('stripe down')
        return rows[key]

    built = build_storefront(
        catalog_revision=catalog.CATALOG_REVISION,
        ladder=load_ladder(),
        bindings=list(rows),
        recognized=recognized,
        subscription=Subscription(
            plan=PlanType(plan),
            current_price_id=price_id,
            cancel_at_period_end=True,
            current_period_end=PERIOD_END,
        ),
        retrieve_price=retrieve,
        purchasable=lambda key: True,
        usage=StorefrontUsage(),
    )
    current = next(tier for tier in built.tiers if tier.is_current)
    assert current.plan_id == plan
    assert current.action == 'current'
    assert current.cta_label is None
    assert current.prices == []
    free = next(tier for tier in built.tiers if tier.plan_id == 'basic')
    assert free.action == 'none' and free.compact is True and free.bullets == []
    assert free.blocked_line == 'Resubscribe first to change plans'
    assert not any(tier.action == 'checkout' and not tier.prices for tier in built.tiers)
    assert not any(tier.action == 'checkout' for tier in built.tiers)


def test_yearly_subscriber_with_failed_price_retrieve_offers_no_prices():
    rows, recognized = ladder_catalog()

    def retrieve(key):
        if key == 'price_plus_year':
            raise RuntimeError('stripe down')
        return rows[key]

    built = build_storefront(
        catalog_revision=catalog.CATALOG_REVISION,
        ladder=load_ladder(),
        bindings=list(rows),
        recognized=recognized,
        subscription=Subscription(
            plan=PlanType.plus,
            current_price_id='price_plus_year',
            cancel_at_period_end=False,
            current_period_end=PERIOD_END,
        ),
        retrieve_price=retrieve,
        purchasable=lambda key: True,
        usage=StorefrontUsage(),
    )
    current = next(tier for tier in built.tiers if tier.is_current)
    assert built.current.interval is None
    assert current.plan_id == 'plus'
    assert current.action == 'current'
    assert current.cta_label is None
    assert current.prices == []
    assert current.bullets == []


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
    if name == 'pro_budget80':
        return sheet_for('operator', price_id='price_operator_month', trigger='usage_budget', percent=80, **common)
    if name == 'pro_budget_cap':
        return sheet_for('operator', price_id='price_operator_month', trigger='usage_budget', percent=100, **common)
    if name == 'architect_settings':
        return sheet_for('architect', price_id='price_architect_month', source='settings', **common)
    if name == 'legacy_unlimited':
        rows = dict(rows)
        rows['price_legacy_unlimited_v2'] = price('price_legacy_unlimited_v2', 2999)
        return sheet_for(
            'unlimited_v2',
            price_id='price_legacy_unlimited_v2',
            rows=rows,
            bindings=list(recognized and common['bindings']),
            recognized=recognized,
            source='settings',
            period_end=PERIOD_END,
        )
    if name == 'legacy_neo':
        rows = dict(rows)
        rows['price_legacy_neo'] = price('price_legacy_neo', 1999)
        return sheet_for(
            'unlimited',
            price_id='price_legacy_neo',
            rows=rows,
            bindings=list(recognized and common['bindings']),
            recognized=recognized,
            source='settings',
            period_end=PERIOD_END,
        )
    if name == 'cancel_scheduled_plus':
        return sheet_for('plus', price_id='price_plus_month', cancel=True, source='settings', **common)
    if name == 'cancel_scheduled_pro':
        return sheet_for('operator', price_id='price_operator_month', cancel=True, source='settings', **common)
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
    'pro_budget80',
    'pro_budget_cap',
    'architect_settings',
    'legacy_unlimited',
    'legacy_neo',
    'cancel_scheduled_plus',
    'cancel_scheduled_pro',
)


def _dump(sheet) -> str:
    return json.dumps(sheet.model_dump(mode='json'), indent=2, ensure_ascii=False) + '\n'


def test_golden_storefront_scenarios():
    rendered = {name: _scenario(name) for name in SCENARIOS}
    free = rendered['free_settings']
    assert free.header == 'Choose your plan'
    assert free.current.line == "You're on Free"
    assert [tier.plan_id for tier in free.tiers] == ['plus', 'basic', 'operator', 'architect']
    free_card = next(tier for tier in free.tiers if tier.is_current)
    assert free_card.compact is True and free_card.bullets == []
    assert free_card.prices[0].headline == '$0'
    assert rendered['free_budget80'].header == "You've used 80% of this month's usage"
    assert rendered['free_budget80'].usage.meter_line == ('80% used · about 3 hours of recording left · resets Nov 1')
    assert rendered['free_budget80'].usage.more_label == 'Get more usage'
    assert rendered['free_budget80'].usage.nudge_line == ("You've used 80% of this month's usage · resets Nov 1")
    assert rendered['free_pro_gate_proactive'].header == 'Reminders and follow-ups come with Pro'
    proactive = next(tier for tier in rendered['free_pro_gate_proactive'].tiers if tier.plan_id == 'operator')
    assert proactive.bullets[0] == "Omi reminds you of things you said you'd do"
    assert rendered['free_pro_gate_screen'].header == 'Screen help comes with Pro'
    screen = next(tier for tier in rendered['free_pro_gate_screen'].tiers if tier.plan_id == 'operator')
    assert screen.bullets[0] == "On your Mac, Omi can see what you're working on and help with it"
    assert rendered['free_mcp_cap'].header == "You've used today's 100 MCP requests"
    assert all('MCP requests' in tier.bullets[0] for tier in rendered['free_mcp_cap'].tiers if not tier.is_current)
    plus80 = rendered['plus_budget80']
    assert plus80.current.line == "You're on Plus · $19.99/mo · renews Nov 1"
    assert plus80.usage.meter_line == '80% used · about 20 hours of recording left · resets Nov 1'
    annual = rendered['plus_annual_current']
    assert annual.current.line == "You're on Plus · $199.90/yr · renews Nov 1"
    plus_card = next(tier for tier in annual.tiers if tier.plan_id == 'plus')
    assert [item.interval for item in plus_card.prices] == ['year']
    assert plus_card.compact is True and plus_card.cta_label is None and plus_card.bullets == []
    assert all(item.cta_label is None for item in plus_card.prices)
    switched = rendered['plus_monthly_yearly_toggle']
    assert switched.header == 'Choose your plan'
    plus_month = next(tier for tier in switched.tiers if tier.plan_id == 'plus')
    assert plus_month.action == 'checkout' and plus_month.cta_label is None and plus_month.compact is False
    assert plus_month.bullets == []
    assert [item.interval for item in plus_month.prices] == ['year']
    assert plus_month.prices[0].headline == '$19.99/month'
    assert plus_month.prices[0].subline == '$199.90 billed yearly · 2 months free'
    assert plus_month.prices[0].cta_label == 'Switch to yearly · save $39.98'
    assert all(tier.plan_id != 'basic' for tier in switched.tiers)
    pro_settings = rendered['pro_settings']
    assert pro_settings.current.line == "You're on Pro · $49.99/mo · renews Nov 1"
    assert [tier.plan_id for tier in pro_settings.tiers] == ['plus', 'operator']
    assert all(tier.plan_id != 'architect' for tier in pro_settings.tiers)
    assert all(tier.plan_id != 'architect' for tier in rendered['pro_budget80'].tiers)
    assert plus_month.prices[0].confirm_lines == [
        'Your monthly plan continues until Nov 1',
        'Your payment method will be charged $199.90 when your yearly plan starts',
        'Your yearly plan starts on Nov 1',
    ]
    capped = rendered['pro_budget_cap']
    assert capped.header == "You've used all of this month's usage"
    assert capped.usage.percent == 100
    assert capped.usage.meter_line == '100% used · resets Nov 1'
    assert 'about 0 hours' not in capped.usage.meter_line
    assert [tier.plan_id for tier in capped.tiers] == ['architect', 'plus', 'operator']
    architect = next(tier for tier in capped.tiers if tier.plan_id == 'architect')
    assert architect.recommended and architect.action == 'checkout'
    assert architect.cta_label == 'Upgrade to Architect' and architect.blocked_line is None
    assert not any(tier.recommended for tier in capped.tiers if tier.plan_id != 'architect')
    assert rendered['architect_settings'].current.line == "You're on Architect · $199/mo · renews Nov 1"
    legacy = rendered['legacy_unlimited']
    assert legacy.header == 'Your plan'
    assert legacy.current.plan_id == 'unlimited_v2'
    assert legacy.current.name == 'Unlimited'
    assert legacy.current.line == "You're on Unlimited · $29.99/mo · renews Nov 1"
    assert legacy.current.legacy_note == "We don't sell this plan anymore, but yours stays exactly as it is."
    assert legacy.usage.more_label is None
    assert 'more_label' not in legacy.model_dump(mode='json')['usage']
    assert not any(tier.action == 'checkout' for tier in legacy.tiers)
    assert 'basic' not in {tier.plan_id for tier in legacy.tiers}
    assert {tier.plan_id for tier in legacy.tiers if tier.action == 'none'} >= {
        'operator',
        'architect',
        'plus',
    }
    neo = rendered['legacy_neo']
    assert neo.header == 'Your plan'
    assert neo.current.plan_id == 'unlimited'
    assert neo.current.name == 'Neo'
    assert neo.current.line == "You're on Neo · $19.99/mo · renews Nov 1"
    assert neo.current.legacy_note == legacy.current.legacy_note
    assert not any(tier.action == 'checkout' for tier in neo.tiers)
    cancelled = rendered['cancel_scheduled_plus']
    assert cancelled.header == 'Your Plus plan ends Nov 1'
    assert cancelled.current.line == "You're on Plus · $19.99/mo"
    assert [tier.plan_id for tier in cancelled.tiers] == ['plus', 'basic', 'operator', 'architect']
    assert not any(tier.recommended for tier in cancelled.tiers)
    cancelled_free = next(tier for tier in cancelled.tiers if tier.plan_id == 'basic')
    assert cancelled_free.compact is True and cancelled_free.bullets == [] and cancelled_free.action == 'none'
    assert cancelled_free.blocked_line == 'Resubscribe first to change plans'
    cancelled_pro = rendered['cancel_scheduled_pro']
    assert cancelled_pro.header == 'Your Pro plan ends Nov 1'
    assert [tier.plan_id for tier in cancelled_pro.tiers] == ['operator', 'basic', 'plus', 'architect']
    assert not any(tier.recommended for tier in cancelled_pro.tiers)
    assert next(tier for tier in cancelled_pro.tiers if tier.is_current).cta_label == 'Resubscribe'
    assert all(
        tier.action == 'none' and tier.cta_label is None and tier.blocked_line == 'Resubscribe first to change plans'
        for tier in cancelled_pro.tiers
        if tier.plan_id in {'basic', 'plus', 'architect'}
    )
    current_plus = next(tier for tier in cancelled.tiers if tier.is_current)
    assert current_plus.action == 'checkout' and current_plus.cta_label == 'Resubscribe'
    assert current_plus.blocked_line is None and current_plus.compact is False and current_plus.bullets == []
    assert [item.price_id for item in current_plus.prices] == ['price_plus_month']
    assert all(item.cta_label is None for item in current_plus.prices)
    assert cancelled.yearly_toggle_label is None
    assert all(
        tier.action == 'none' and tier.cta_label is None and tier.blocked_line == 'Resubscribe first to change plans'
        for tier in cancelled.tiers
        if not tier.is_current
    )
    assert all(tier.bullets == [] for sheet in rendered.values() for tier in sheet.tiers if tier.is_current)
    assert all(
        rendered[name].yearly_toggle_label == 'Yearly · 2 months free'
        for name in SCENARIOS
        if name not in {'cancel_scheduled_plus', 'cancel_scheduled_pro'}
    )
    french = sheet_for('basic', locale='fr-FR', rows={}, bindings=[], recognized=[])
    assert french.header == copy_for('fr')['headers']['default']
    assert french.header != 'Choose your plan'
    unknown = sheet_for('basic', locale='zz-ZZ', rows={}, bindings=[], recognized=[])
    assert unknown.header == 'Choose your plan'

    GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
    for name in SCENARIOS:
        path = GOLDEN_DIR / f'{name}.json'
        payload = _dump(rendered[name])
        if os.environ.get('UPDATE_STOREFRONT_GOLDENS') == '1':
            path.write_text(payload, encoding='utf-8')
            APP_FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
            (APP_FIXTURE_DIR / f'{name}.json').write_text(payload, encoding='utf-8')
        assert path.read_text(encoding='utf-8') == payload
    for name in SCENARIOS:
        path = GOLDEN_DIR / f'{name}.json'
        app_path = APP_FIXTURE_DIR / f'{name}.json'
        assert app_path.read_bytes() == path.read_bytes()


def test_efficiency_hours_bands(monkeypatch):
    import config.rate_card as rates
    from copy import deepcopy

    card = rates.recording_rate_card()
    assert rates.recording_units_per_hour() == Decimal('130')
    assert rates.recording_units_per_hour('on_device') == 0
    for plan, hours in [('plus', 100), ('operator', 280), ('architect', 1200)]:
        assert recording_hours(plan) == hours
        assert '24/7' not in hours_line(plan)
        assert 'Enough for casual daily use' not in hours_line(plan)
    measured = deepcopy(card)
    measured['recording']['units_per_recorded_hour']['batch'] = '30'
    monkeypatch.setattr(rates, 'recording_rate_card', lambda: measured)
    assert rates.recording_units_per_hour() == Decimal('32')
    assert 'Enough for casual daily use' in hours_line('plus')
    assert 'Enough to wear it 24/7' in hours_line('operator')
    assert '24/7 on more than one device' in hours_line('architect')
    assert rates.recording_units_per_hour('live') == 130


def test_capacity_rounding_preserves_supported_band_and_meter(monkeypatch):
    import config.rate_card as rates

    card = rates.recording_rate_card()
    card['recording']['units_per_recorded_hour']['batch'] = '50'
    monkeypatch.setattr(rates, 'recording_rate_card', lambda: card)
    assert recording_hours('operator') == 720
    assert recording_hours_left('operator', 0) == 720
    assert 'About 720 hours' in hours_line('operator')
    assert 'Enough to wear it 24/7' in hours_line('operator')
    card['recording']['units_per_recorded_hour']['batch'] = '110'
    assert recording_hours('architect') == 1440
    assert recording_hours_left('architect', 0) == 1440
    assert '24/7 on more than one device' in hours_line('architect')


def test_percent_rounding_never_offers_architect_before_cap():
    rows, recognized = ladder_catalog()
    sheet = sheet_for(
        'operator',
        price_id='price_operator_month',
        trigger='usage_budget',
        percent=99.9,
        rows=rows,
        recognized=recognized,
        bindings=list(rows),
    )
    assert sheet.usage.percent == 99
    assert all(tier.plan_id != 'architect' for tier in sheet.tiers)
    assert sheet.header != "You've used all of this month's usage"


_PLACEHOLDERS = re.compile(r'\{[a-z_]+\}')
_PLUS_DAILY_UNIT = {
    'ar': '3 ساعات',
    'be': '3 гадзін',
    'bn': '3 ঘণ্টা',
    'bs': '3 sati',
    'ca': '3 hores',
    'cs': '3 hodin',
    'da': '3 timer',
    'lt': '3 valandų',
    'lv': '3 stundas',
    'mk': '3 часа',
    'mr': '3 तास',
    'ms': '3 jam',
    'nl': '3 uur',
    'no': '3 timer',
    'pl': '3 godzin',
    'te': '3 గంటలు',
    'th': '3 ชั่วโมง',
    'tl': '3 oras',
    'tr': '3 saat',
    'uk': '3 годин',
    'ur': '3 گھنٹے',
    'vi': '3 giờ',
    'zh': '3 小时',
}
L10N_LOCALES = ('es', 'ja', 'ar', 'zh', 'de')
L10N_SCENARIOS = ('free_settings', 'plus_budget80', 'pro_budget_cap', 'cancel_scheduled_plus')
L10N_DIR = Path(__file__).resolve().parents[1] / 'fixtures' / 'storefront_v2_l10n'


def _leaves(value, prefix=''):
    if isinstance(value, dict):
        for key, child in value.items():
            yield from _leaves(child, f'{prefix}.{key}' if prefix else key)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _leaves(child, f'{prefix}[{index}]')
    else:
        yield prefix, value


def _l10n_sheet(name, locale):
    rows, recognized = ladder_catalog()
    common = {
        'rows': rows,
        'bindings': list(rows),
        'recognized': recognized,
        'period_end': PERIOD_END,
        'locale': locale,
    }
    if name == 'free_settings':
        return sheet_for(
            'basic',
            source='settings',
            period_end=None,
            rows=rows,
            bindings=list(rows),
            recognized=recognized,
            locale=locale,
        )
    if name == 'plus_budget80':
        return sheet_for('plus', price_id='price_plus_month', trigger='usage_budget', percent=80, **common)
    if name == 'pro_budget_cap':
        return sheet_for('operator', price_id='price_operator_month', trigger='usage_budget', percent=100, **common)
    if name == 'cancel_scheduled_plus':
        return sheet_for('plus', price_id='price_plus_month', cancel=True, source='settings', **common)
    raise AssertionError(name)


def test_every_locale_has_every_english_key_and_the_same_placeholders():
    locales = load_copy()['locales']
    english = dict(_leaves(locales['en']))
    assert set(locales) >= set(L10N_LOCALES) | {'en'}
    for code, text in locales.items():
        got = dict(_leaves(text))
        missing = set(english) - set(got)
        assert not missing, (code, sorted(missing))
        for key, value in english.items():
            if isinstance(value, str):
                assert set(_PLACEHOLDERS.findall(got[key])) == set(_PLACEHOLDERS.findall(value)), (code, key)
        assert text['pro_gates'] == locales['en']['pro_gates']
        focus = text['bullet_focus']
        bullets = text['bullets']
        for plan, items in bullets.items():
            assert any(focus['mcp_marker'] in item for item in items), (code, plan)
        for trigger in ('proactive_agent', 'screen_context'):
            assert focus[trigger] in bullets['operator'], (code, trigger)
        plus = text['hours_lines']['plus'].format(hours='100', per_day='3')
        assert '3' in plus, code
        if code in _PLUS_DAILY_UNIT:
            assert _PLUS_DAILY_UNIT[code] in plus, (code, plus)


def test_locale_matching_merges_over_english():
    assert copy_for('pt-BR')['headers']['default'] == copy_for('pt')['headers']['default']
    assert copy_for('zh-Hans')['headers']['default'] == copy_for('zh')['headers']['default']
    assert copy_for('nb')['headers']['default'] == copy_for('no')['headers']['default']
    assert copy_for('zz')['headers']['default'] == 'Choose your plan'
    assert copy_for(None)['dates']['resets'] == 'resets {date}'
    assert _deep_merge({'a': {'b': 1, 'c': 2}, 'd': [1]}, {'a': {'c': 9}}) == {'a': {'b': 1, 'c': 9}, 'd': [1]}
    spanish = copy_for('es')
    assert spanish['dates']['period_month'] == 'mes'
    assert 'Choose your plan' not in spanish['headers']['default']


def test_counted_lines_follow_cldr_plural_categories():
    assert per_day_phrase(30, 'ar') == 'حوالي 1 ساعة يومياً'
    assert per_day_phrase(60, 'ar') == 'حوالي ساعتين يومياً'
    assert per_day_phrase(90, 'ar') == 'حوالي 3 ساعات يومياً'
    assert per_day_phrase(150, 'ar') == 'حوالي 5 ساعات يومياً'
    assert per_day_phrase(30, 'cs') == 'asi 1 hodinu denně'
    assert per_day_phrase(60, 'cs') == 'asi 2 hodiny denně'
    assert per_day_phrase(90, 'cs') == 'asi 3 hodiny denně'
    assert per_day_phrase(150, 'cs') == 'asi 5 hodin denně'
    assert per_day_phrase(30, 'be') == 'каля 1 гадзіна ў дзень'
    assert per_day_phrase(60, 'bs') == 'oko 2 sata dnevno'
    assert per_day_phrase(150, 'bs') == 'oko 5 sati dnevno'
    assert months_free_phrase(1) == '1 month free'
    assert months_free_phrase(2) == '2 months free'
    assert months_free_phrase(2, 'ar') == 'شهران مجاناً'
    assert months_free_phrase(5, 'ar') == '5 أشهر مجانية'
    assert months_free_phrase(21, 'ar') == '21 شهراً مجاناً'
    assert months_free_phrase(2, 'cs') == '2 měsíce zdarma'
    assert months_free_phrase(5, 'cs') == '5 měsíců zdarma'
    assert months_free_phrase(21, 'be') == '21 месяц бясплатна'
    assert months_free_phrase(5, 'pl') == '5 miesięcy gratis'
    for count, word in ((1, 'hodina'), (2, 'hodiny'), (3, 'hodiny'), (5, 'hodin'), (21, 'hodin')):
        line = _meter_hours_line(copy_for('cs'), shown=80, left=count, reset='x', locale='cs')
        assert f'{count} {word}' in line
    for count, word in ((1, 'ساعة'), (2, 'ساعتين'), (3, 'ساعات'), (5, 'ساعات'), (21, 'ساعة')):
        line = _meter_hours_line(copy_for('ar'), shown=80, left=count, reset='x', locale='ar')
        assert word in line
        if count != 2:
            assert str(count) in line
    assert (
        _count_template(
            copy_for('en')['per_day'], 5, 'en', plural_key='under_6_plural', one_key='under_6_one', many_key='under_6'
        )
        == 'about {n} hours a day'
    )


def test_localized_storefront_goldens():
    L10N_DIR.mkdir(parents=True, exist_ok=True)
    for locale in L10N_LOCALES:
        text = copy_for(locale)
        for name in L10N_SCENARIOS:
            sheet = _l10n_sheet(name, locale)
            path = L10N_DIR / f'{locale}_{name}.json'
            payload = _dump(sheet)
            if os.environ.get('UPDATE_STOREFRONT_GOLDENS') == '1':
                path.write_text(payload, encoding='utf-8')
            assert path.read_text(encoding='utf-8') == payload
            assert sheet.header != 'Choose your plan'
            if name == 'free_settings':
                assert sheet.header == text['headers']['default']
                assert sheet.current.line == text['current']['free']
            if name == 'plus_budget80':
                assert sheet.usage.hours_left is not None and sheet.usage.hours_left > 0
                assert sheet.usage.meter_line
                assert sheet.usage.reset_label == text['dates']['resets'].format(date=format_date(PERIOD_END, locale))
                assert 'resets Nov' not in sheet.usage.meter_line
            if name == 'pro_budget_cap':
                assert sheet.usage.hours_left is None
                assert sheet.header == text['headers']['budget_100']
                assert 'about 0' not in (sheet.usage.meter_line or '')
            if name == 'cancel_scheduled_plus':
                assert sheet.header == text['headers']['cancel_scheduled'].format(
                    plan='Plus', date=format_date(PERIOD_END, locale)
                )
    german = _l10n_sheet('plus_budget80', 'de')
    assert german.usage.reset_label == 'setzt sich am 1. Nov. zurück'
    japanese = _l10n_sheet('cancel_scheduled_plus', 'ja')
    assert '11月1日' in japanese.header
    arabic = _l10n_sheet('free_settings', 'ar')
    assert arabic.header == copy_for('ar')['headers']['default']
