"""Executable presentation policy, live-price arithmetic, and dark-route contract."""

import json
from pathlib import Path
from unittest.mock import Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from models.users import PlanType, Subscription
from models.storefront import StorefrontUsage
from routers import storefront as route
from utils.rate_limit_config import get_effective_limit
from utils.storefront import _valid_price_rows, build_single_plan_storefront, build_storefront, load_ladder
from utils.storefront_copy import months_free


@pytest.fixture(autouse=True)
def offline_usage_projection(monkeypatch):
    # The new facade exists in cutover; presentation tests must not reach the ledger.
    monkeypatch.setattr(route.subscription_utils, 'get_usage_units', lambda uid: {})


def price(identifier, amount, interval='month', **overrides):
    return {
        'id': identifier,
        'currency': 'usd',
        'unit_amount': amount,
        'active': True,
        'recurring': {'interval': interval, 'interval_count': 1},
        **overrides,
    }


SINGLE_PLAN_PRICES = {
    'price_omi_pro_month': price('price_omi_pro_month', 2999, 'month'),
    'price_omi_pro_year': price('price_omi_pro_year', 26991, 'year'),
}


def build(plan='basic', current_price=None, rows=None, bindings=None, recognized=None, source=None, trigger=None):
    return build_storefront(
        catalog_revision=6,
        ladder=load_ladder(),
        bindings=bindings or [],
        recognized=recognized or [],
        subscription=Subscription(plan=PlanType(plan), current_price_id=current_price),
        retrieve_price=lambda key: (rows or {})[key],
        purchasable=lambda key: True,
        usage=StorefrontUsage(),
        source=source,
        trigger=trigger,
    )


def test_empty_bindings_hide_unpurchasable_tiers_but_keep_architect_contact():
    sheet = build()
    assert [(tier.plan_id, tier.action) for tier in sheet.tiers] == [('basic', 'current'), ('architect', 'none')]
    assert sheet.current.legacy is False


@pytest.mark.parametrize('plan', ['plus', 'operator', 'architect', 'unlimited', 'unlimited_v2'])
def test_legacy_subscriber_has_exactly_one_current_row_even_without_stripe(plan):
    sheet = build(plan, 'price_old')
    current = [tier for tier in sheet.tiers if tier.action == 'current']
    assert len(current) == 1
    assert current[0].plan_id == plan and sheet.current.legacy
    assert current[0].prices == []
    assert sheet.current.price_id == 'price_old' and sheet.current.legacy
    assert not any(tier.action == 'checkout' for tier in sheet.tiers)


def test_registered_purchasable_ladder_is_ordered_and_computes_live_prices():
    rows, recognized = {}, []
    for plan, monthly in [('plus', 1999), ('operator', 4999), ('architect', 19900)]:
        for interval, amount in [('month', monthly), ('year', monthly * 10)]:
            key = f'price_{plan}_{interval}'
            rows[key] = price(key, amount, interval)
            recognized.append(
                {'price_id': key, 'plan_id': plan, 'interval': interval, 'entitlement_version': 'ladder_v1'}
            )
    sheet = build(rows=rows, bindings=list(rows), recognized=recognized)
    assert [tier.plan_id for tier in sheet.tiers] == ['plus', 'basic', 'operator', 'architect']
    assert [tier.action for tier in sheet.tiers] == ['checkout', 'current', 'checkout', 'checkout']
    plus = next(tier for tier in sheet.tiers if tier.plan_id == 'plus')
    assert plus.recommended and plus.cta_label == 'Get Plus'
    yearly = next(item for item in plus.prices if item.interval == 'year')
    assert yearly.headline == '$16.66/month'
    assert yearly.subline == '$199.90 billed yearly · 2 months free'
    assert yearly.months_free == 2
    pro = next(tier for tier in sheet.tiers if tier.plan_id == 'operator')
    assert pro.cta_label == 'Get Pro'
    assert pro.bullets[0] == "Omi reminds you of things you said you'd do"
    paid = build('operator', 'price_operator_month', rows, list(rows), recognized)
    assert [tier.plan_id for tier in paid.tiers] == ['plus', 'operator']
    assert [tier.action for tier in paid.tiers] == ['none', 'checkout']
    assert all(tier.plan_id != 'basic' for tier in paid.tiers)
    assert all(tier.plan_id != 'architect' for tier in paid.tiers)
    operator = next(tier for tier in paid.tiers if tier.plan_id == 'operator')
    assert operator.cta_label is None and operator.bullets == []
    assert [item.interval for item in operator.prices] == ['year']
    assert operator.prices[0].headline == '$49.99/month'
    assert operator.prices[0].subline == '$499.90 billed yearly · 2 months free'
    assert operator.prices[0].cta_label == 'Switch to yearly · save $99.98'
    assert not any(tier.recommended for tier in paid.tiers)


def test_price_currency_interval_and_months_free_validation():
    assert not _valid_price_rows([price('bad', 1999, currency='jpy')])
    assert not _valid_price_rows([price('bad', 1999, active=False)])
    assert not _valid_price_rows([price('bad', 1999, recurring={'interval': 'month', 'interval_count': 3})])
    assert _valid_price_rows([price('old', 1999, active=False)], current=True)
    # 12 - 25000/2100 is under one month, so the free-months line stays off.
    assert months_free(2100, 25000) is None
    assert months_free(1000, 13000) is None
    assert months_free(1999, 19990) == 2
    assert months_free(1000, 11000) == 1


def test_single_plan_storefront_builder_pins_golden(monkeypatch):
    """The new-buyer Omi Pro sheet: one checkout tier over a Free current row.
    Pinned byte-exact to the golden the web plans panel renders in its tests —
    no dead 'Couldn't load plans' state for a new buyer."""
    monkeypatch.setenv('STRIPE_UNLIMITED_V2_MONTHLY_PRICE_ID', 'price_omi_pro_month')
    monkeypatch.setenv('STRIPE_UNLIMITED_V2_ANNUAL_PRICE_ID', 'price_omi_pro_year')
    sheet = build_single_plan_storefront(
        catalog_revision=6,
        subscription=Subscription(),
        usage=StorefrontUsage(),
        retrieve_price=lambda key: SINGLE_PLAN_PRICES[key],
    )
    assert [tier.tier_id for tier in sheet.tiers] == ['unlimited_v2:single_plan', 'basic:single_plan']
    tier = sheet.tiers[0]
    assert tier.name == 'Unlimited' and tier.recommended and tier.is_current is False
    assert tier.action == 'checkout' and tier.cta_label == 'Get Unlimited'
    assert [item.price_id for item in tier.prices] == ['price_omi_pro_month', 'price_omi_pro_year']
    assert tier.prices[0].headline == '$29.99/month'
    assert tier.prices[1].months_free == 3 and tier.prices[1].subline == '$269.91 billed yearly · 3 months free'
    assert sheet.current.plan_id == 'basic' and sheet.current.line == "You're on Free"
    free_card = sheet.tiers[1]
    assert free_card.is_current and free_card.action == 'current' and free_card.bullets == []
    assert sheet.current.legacy is False and sheet.current.price_id is None
    assert sheet.yearly_toggle_label == 'Yearly · 3 months free'
    payload = json.dumps(sheet.model_dump(mode='json'), indent=2, ensure_ascii=False) + '\n'
    golden = Path(__file__).resolve().parents[1] / 'fixtures' / 'storefront_v2' / 'single_plan_omi_pro.json'
    assert golden.read_text(encoding='utf-8') == payload


def test_single_plan_storefront_without_live_prices_keeps_sheet_not_dead(monkeypatch):
    """Price retrieval failure degrades the tier to action=none — still a v2
    sheet (no 404), so the client shows the card rather than an error panel."""
    monkeypatch.setenv('STRIPE_UNLIMITED_V2_MONTHLY_PRICE_ID', 'price_omi_pro_month')
    monkeypatch.delenv('STRIPE_UNLIMITED_V2_ANNUAL_PRICE_ID', raising=False)

    def _explode(price_id):
        raise RuntimeError('stripe unavailable')

    sheet = build_single_plan_storefront(
        catalog_revision=6,
        subscription=Subscription(),
        usage=StorefrontUsage(),
        retrieve_price=_explode,
    )
    assert sheet.tiers and sheet.tiers[0].plan_id == 'unlimited_v2'
    assert sheet.tiers[0].action == 'none' and sheet.tiers[0].prices == []
    assert sheet.current.plan_id == 'basic'


@pytest.fixture
def client(monkeypatch):
    app = FastAPI()
    app.include_router(route.router)
    app.dependency_overrides[route.auth.get_current_user_uid_no_byok_validation] = lambda: 'fixture-user'
    monkeypatch.setattr(route.auth, 'check_rate_limit', lambda *args: (True, 12, 0))
    monkeypatch.setattr(route.auth, 'RATE_LIMIT_SHADOW', False)
    monkeypatch.setenv('STOREFRONT_LADDER_V1_ENABLED', 'true')
    # These tests pin ladder presentation policy for a default (basic) caller.
    # The 2026-10-24 new-buyer single-plan rule serves that caller the Omi Pro
    # sheet on explicit non-desktop platforms (see
    # test_new_buyer_single_plan_rule_serves_omi_pro_sheet), so restore the
    # pre-ruling ladder here; the rule itself has its own tests.
    monkeypatch.setenv('NEW_BUYER_SINGLE_PLAN_ENABLED', 'false')
    monkeypatch.setattr(route, 'should_hide_subscription_ui', lambda *args: False)
    monkeypatch.setattr(route.users_db, 'get_user_valid_subscription', lambda uid, **kwargs: Subscription())
    monkeypatch.setattr(route, '_usage', lambda *args: StorefrontUsage())
    return TestClient(app)


def _omi_pro_env(monkeypatch):
    monkeypatch.setenv('STRIPE_UNLIMITED_V2_MONTHLY_PRICE_ID', 'price_omi_pro_month')
    monkeypatch.setenv('STRIPE_UNLIMITED_V2_ANNUAL_PRICE_ID', 'price_omi_pro_year')
    monkeypatch.setattr(route, '_retrieve_price', lambda price_id: SINGLE_PLAN_PRICES[price_id])


def test_new_buyer_single_plan_rule_serves_omi_pro_sheet(client, monkeypatch):
    """2026-10-24 ruling at the v2 route: a basic buyer on an explicit
    non-desktop platform (mobile/web) gets a single-tier Omi Pro sheet — never
    a 404, which the web plans panel renders as a dead "Couldn't load plans"
    state. Missing/unknown platform headers, desktop platforms, existing
    subscribers, and the kill switch keep the ladder sheet."""
    monkeypatch.delenv('NEW_BUYER_SINGLE_PLAN_ENABLED', raising=False)
    _omi_pro_env(monkeypatch)

    for platform in ('ios', 'android', 'web'):
        response = client.get('/v2/payments/plans', headers={'X-App-Platform': platform})
        assert response.status_code == 200, platform
        payload = response.json()
        assert [tier['plan_id'] for tier in payload['tiers']] == ['unlimited_v2', 'basic'], platform
        assert [item['price_id'] for item in payload['tiers'][0]['prices']] == [
            'price_omi_pro_month',
            'price_omi_pro_year',
        ], platform
        assert payload['tiers'][0]['action'] == 'checkout'
        assert payload['current']['plan_id'] == 'basic'

    # Desktop, missing header, unknown value, and current subscribers keep the
    # ladder sheet (this fixture's ladder has no Omi Pro card).
    ladder_callers = [
        {'X-App-Platform': 'macos'},
        {'X-App-Platform': 'windows'},
        {},
        {'X-App-Platform': 'not-a-platform'},
    ]
    for headers in ladder_callers:
        response = client.get('/v2/payments/plans', headers=headers)
        assert response.status_code == 200, headers
        assert all(tier['plan_id'] != 'unlimited_v2' for tier in response.json()['tiers']), headers

    monkeypatch.setattr(
        route.users_db, 'get_user_valid_subscription', lambda uid, **kwargs: Subscription(plan=PlanType.plus)
    )
    assert all(
        tier['plan_id'] != 'unlimited_v2'
        for tier in client.get('/v2/payments/plans', headers={'X-App-Platform': 'ios'}).json()['tiers']
    )

    monkeypatch.setattr(route.users_db, 'get_user_valid_subscription', lambda uid, **kwargs: Subscription())
    monkeypatch.setenv('NEW_BUYER_SINGLE_PLAN_ENABLED', 'false')
    for platform in ('ios', 'web'):
        response = client.get('/v2/payments/plans', headers={'X-App-Platform': platform})
        assert response.status_code == 200, platform
        assert all(tier['plan_id'] != 'unlimited_v2' for tier in response.json()['tiers']), platform


def test_route_dark_by_default_and_bad_flag_cannot_read_data(client, monkeypatch):
    read = Mock(side_effect=AssertionError('dark route must not read'))
    monkeypatch.setattr(route.users_db, 'get_user_valid_subscription', read)
    for flag in [None, 'false', 'TRUE', '1', 'typo']:
        if flag is None:
            monkeypatch.delenv('STOREFRONT_LADDER_V1_ENABLED')
        else:
            monkeypatch.setenv('STOREFRONT_LADDER_V1_ENABLED', flag)
        assert client.get('/v2/payments/plans').status_code == 404
    read.assert_not_called()


def test_review_hidden_response_reads_no_subscription_price_or_usage(client, monkeypatch):
    monkeypatch.setattr(route, 'should_hide_subscription_ui', lambda *args: True)
    read = Mock(side_effect=AssertionError('hidden route must not read'))
    monkeypatch.setattr(route.users_db, 'get_user_valid_subscription', read)
    monkeypatch.setattr(route, '_retrieve_price', read)
    monkeypatch.setattr(route, '_usage', read)
    response = client.get('/v2/payments/plans', headers={'X-App-Platform': 'ios', 'X-App-Version': '1.0.1'})
    assert response.status_code == 200
    assert response.json()['show_subscription_ui'] is False
    assert response.json()['tiers'] == [] and response.json()['current'] is None
    read.assert_not_called()


def test_every_surface_has_identical_presentation_and_read_only_subscription(client, monkeypatch):
    read = Mock(return_value=Subscription())
    monkeypatch.setattr(route.users_db, 'get_user_valid_subscription', read)
    rows = {
        f'price_{plan}_month': price(f'price_{plan}_month', amount)
        for plan, amount in [('plus', 1999), ('operator', 4999), ('architect', 19900)]
    }
    monkeypatch.setattr(route.catalog, 'LADDER_V1_STRIPE_PRICES', list(rows), raising=False)
    monkeypatch.setattr(
        route.catalog, 'RECOGNIZED_STRIPE_ENTITLEMENT_VERSIONS', {key: 'ladder_v1' for key in rows}, raising=False
    )
    monkeypatch.setattr(
        route.catalog, 'RECOGNIZED_STRIPE_PRICE_PLAN_TYPES', {key: PlanType(key.split('_')[1]) for key in rows}
    )
    monkeypatch.setattr(route.catalog, 'RECOGNIZED_STRIPE_PRICE_INTERVALS', {key: 'month' for key in rows})
    monkeypatch.setattr(route.subscription_utils, 'is_purchasable_price_id', lambda key: True)
    monkeypatch.setattr(route, '_retrieve_price', lambda key: rows[key])
    bodies = [
        client.get('/v2/payments/plans', headers={'X-App-Platform': platform}).content
        for platform in ['ios', 'android', 'macos', 'windows', 'web']
    ]
    assert all(body == bodies[0] for body in bodies)
    body = json.loads(bodies[0])
    assert body['schema_version'] == 2
    assert [tier['name'] for tier in body['tiers']] == ['Plus', 'Free', 'Pro', 'Architect']
    assert all(call.kwargs == {'provision': False} for call in read.call_args_list)


def test_new_current_row_survives_missing_purchasable_prices():
    sheet = build('plus', 'price_new', bindings=['price_new'])
    current = [tier for tier in sheet.tiers if tier.action == 'current']
    assert len(current) == 1 and current[0].plan_id == 'plus'
    assert sheet.current.legacy is False


def test_legacy_current_price_is_preserved_even_when_archived():
    sheet = build('plus', 'price_old', rows={'price_old': price('price_old', 1799, active=False)})
    current = next(tier for tier in sheet.tiers if tier.action == 'current')
    assert current.prices[0].amount_minor == 1799


def test_usage_absence_and_bad_projection_never_invent_budget(monkeypatch):
    monkeypatch.setattr(route.subscription_utils, 'transcription_allowance_seconds', lambda plan: 100)
    monkeypatch.setattr(
        route.subscription_utils, 'get_monthly_usage_for_subscription', lambda uid: {'transcription_seconds': 62}
    )
    assert route._usage('fixture', Subscription()).model_dump()['percent'] == 62
    monkeypatch.setattr(
        route.subscription_utils,
        'get_usage_units',
        lambda uid: {'budget_percent': 80, 'reset_at': 1800000000},
        raising=False,
    )
    assert route._usage('fixture', Subscription()).kind == 'usage_budget'
    monkeypatch.setattr(
        route.subscription_utils, 'get_usage_units', lambda uid: {'budget_percent': float('nan'), 'reset_at': 1}
    )
    assert route._usage('fixture', Subscription()).kind == 'transcription'
    monkeypatch.setattr(route.catalog, 'LADDER_V1_STRIPE_PRICES', ['price_new'], raising=False)
    assert route._usage('fixture', Subscription(current_price_id='price_new')).kind == 'unavailable'


def test_api_openapi_names_the_versioned_presentation_contract(client):
    schema = client.get('/openapi.json').json()
    operation = schema['paths']['/v2/payments/plans']['get']
    assert operation['responses']['200']['content']['application/json']['schema']['$ref'].endswith(
        '/StorefrontResponse'
    )
    version = schema['components']['schemas']['StorefrontResponse']['properties']['schema_version']
    assert version.get('const', version.get('enum')) in (2, [2])
    assert schema['components']['schemas']['StorefrontTier']['properties']['action']['enum'] == [
        'checkout',
        'current',
        'none',
    ]
    assert 'tagline' not in schema['components']['schemas']['StorefrontTier']['properties']
    assert 'hours_line' in schema['components']['schemas']['StorefrontTier']['properties']
    assert 'blocked_line' in schema['components']['schemas']['StorefrontTier']['properties']
    assert 'compact' in schema['components']['schemas']['StorefrontTier']['properties']
    assert 'cta_label' in schema['components']['schemas']['StorefrontPrice']['properties']
    parameters = {item['name'] for item in operation['parameters']}
    assert {'source', 'trigger', 'locale'} <= parameters


def test_registration_does_not_bypass_existing_checkout_guard():
    read = Mock(side_effect=AssertionError('non-purchasable price must not be retrieved'))
    sheet = build_storefront(
        catalog_revision=6,
        ladder=load_ladder(),
        bindings=['price_new'],
        recognized=[
            {'price_id': 'price_new', 'plan_id': 'plus', 'interval': 'month', 'entitlement_version': 'ladder_v1'}
        ],
        subscription=Subscription(),
        retrieve_price=read,
        purchasable=lambda key: False,
        usage=StorefrontUsage(),
    )
    assert [tier.plan_id for tier in sheet.tiers] == ['basic', 'architect']
    read.assert_not_called()


def test_shared_client_fixture_matches_production_presentation():
    # Schema v2 goldens live in test_storefront_presentation.py.
    assert load_ladder()['tiers'][1]['plan_id'] == 'plus'
    assert 'tagline' not in load_ladder()['tiers'][1]
    assert 'recommended' not in load_ladder()['tiers'][1]


@pytest.mark.parametrize('plan', ['basic', 'plus', 'operator', 'architect', 'unlimited', 'unlimited_v2'])
@pytest.mark.parametrize('trigger', [None, 'proactive_agent', 'screen_context', 'usage_budget', 'mcp_daily_cap'])
def test_contextual_recommendation_per_subscription_and_gate(plan, trigger):
    rows = {f'price_{p}': price(f'price_{p}', amount) for p, amount in [('plus', 1999), ('operator', 4999)]}
    recognized = [
        {
            'price_id': key,
            'plan_id': key.removeprefix('price_'),
            'interval': 'month',
            'entitlement_version': 'ladder_v1',
        }
        for key in rows
    ]
    # A badge requires checkout. Legacy prices never check out, so they are not badged.
    sheet = build(
        plan,
        None if plan == 'basic' else 'price_legacy',
        rows,
        list(rows),
        recognized,
        source='macos_usage_limit',
        trigger=trigger,
    )
    expected = [] if plan != 'basic' else ['operator'] if trigger in {'proactive_agent', 'screen_context'} else ['plus']
    assert [tier.plan_id for tier in sheet.tiers if tier.recommended] == expected
    if plan != 'basic':
        assert not any(tier.action == 'checkout' for tier in sheet.tiers)


@pytest.mark.parametrize(
    'trigger,expected',
    [
        (None, 'plus'),
        ('proactive_agent', 'operator'),
        ('screen_context', 'operator'),
        ('usage_budget', 'plus'),
        ('mcp_daily_cap', 'plus'),
    ],
)
def test_endpoint_forwards_opening_context(client, monkeypatch, trigger, expected):
    rows = {f'price_{p}': price(f'price_{p}', amount) for p, amount in [('plus', 1999), ('operator', 4999)]}
    monkeypatch.setattr(route.catalog, 'LADDER_V1_STRIPE_PRICES', list(rows), raising=False)
    monkeypatch.setattr(
        route.catalog, 'RECOGNIZED_STRIPE_ENTITLEMENT_VERSIONS', {key: 'ladder_v1' for key in rows}, raising=False
    )
    monkeypatch.setattr(
        route.catalog, 'RECOGNIZED_STRIPE_PRICE_PLAN_TYPES', {key: PlanType(key.removeprefix('price_')) for key in rows}
    )
    monkeypatch.setattr(route.catalog, 'RECOGNIZED_STRIPE_PRICE_INTERVALS', {key: 'month' for key in rows})
    monkeypatch.setattr(route.subscription_utils, 'is_purchasable_price_id', lambda key: True)
    monkeypatch.setattr(route, '_retrieve_price', lambda key: rows[key])
    real_build = route.build_storefront
    seen = {}

    def capture(**kwargs):
        seen.update(kwargs)
        return real_build(**kwargs)

    monkeypatch.setattr(route, 'build_storefront', capture)
    params = {'source': 'macos_usage_limit'}
    if trigger:
        params['trigger'] = trigger
    response = client.get('/v2/payments/plans', params=params)
    assert response.status_code == 200
    assert seen['source'] == 'macos_usage_limit' and seen['trigger'] == trigger
    assert [tier['plan_id'] for tier in response.json()['tiers'] if tier['recommended']] == [expected]


def test_invalid_gate_is_rejected(client):
    assert client.get('/v2/payments/plans?trigger=typo').status_code == 422


@pytest.mark.parametrize('plan', ['unlimited', 'unlimited_v2'])
@pytest.mark.parametrize('registered_current', [False, True])
@pytest.mark.parametrize('offers', [False, True])
def test_non_ladder_paid_plans_only_offer_explicit_higher_tiers(plan, registered_current, offers):
    rows = {'price_current': price('price_current', 2999)}
    bindings = ['price_current'] if registered_current else []
    recognized = []
    if offers:
        for offer, amount in [('plus', 1999), ('operator', 4999), ('architect', 19900)]:
            key = f'price_{offer}'
            rows[key] = price(key, amount)
            bindings.append(key)
            recognized.append(
                {'price_id': key, 'plan_id': offer, 'interval': 'month', 'entitlement_version': 'ladder_v1'}
            )
    sheet = build(plan, 'price_current', rows, bindings, recognized)
    by_plan = {tier.plan_id: tier for tier in sheet.tiers}
    assert 'basic' not in by_plan
    if offers:
        assert by_plan['plus'].action == 'none'
        assert not by_plan['plus'].recommended
        assert by_plan['operator'].action == by_plan['architect'].action == 'none'
        assert not by_plan['operator'].recommended
        assert not by_plan['architect'].recommended
    assert len([tier for tier in sheet.tiers if tier.action == 'current']) == 1
    assert by_plan[plan].action == 'current' and sheet.current.legacy
    assert by_plan[plan].prices[0].amount_minor == 2999
    assert by_plan[plan].bullets == []
    assert not any(tier.action == 'checkout' for tier in sheet.tiers)


@pytest.mark.parametrize('plan', ['plus', 'operator', 'architect'])
def test_legacy_ladder_plan_has_one_card_and_only_existing_entitlement_copy(plan):
    key = f'price_{plan}'
    sheet = build(
        plan,
        'price_old',
        {key: price(key, 4999)},
        [key],
        [{'price_id': key, 'plan_id': plan, 'interval': 'month', 'entitlement_version': 'ladder_v1'}],
    )
    cards = [tier for tier in sheet.tiers if tier.plan_id == plan]
    assert len(cards) == 1
    assert cards[0].action == 'current' and sheet.current.legacy
    assert cards[0].bullets == []
    assert cards[0].hours_line == ''
    assert not cards[0].recommended


@pytest.mark.parametrize('plan', ['operator', 'architect'])
@pytest.mark.parametrize('trigger', [None, 'proactive_agent', 'screen_context', 'usage_budget', 'mcp_daily_cap'])
def test_ladder_subscriber_never_recommends_current_or_lower_plan(plan, trigger):
    rows, recognized = {}, []
    for offer, amount in [('plus', 1999), ('operator', 4999), ('architect', 19900)]:
        key = f'price_{offer}'
        rows[key] = price(key, amount)
        recognized.append({'price_id': key, 'plan_id': offer, 'interval': 'month', 'entitlement_version': 'ladder_v1'})
    sheet = build(plan, f'price_{plan}', rows, list(rows), recognized, trigger=trigger)
    assert not any(tier.recommended for tier in sheet.tiers)


def test_price_retrieval_reuses_subscription_cache_and_24_hour_ttl(monkeypatch):
    cache = {}
    writes = []
    monkeypatch.setattr(route.redis_db, 'get_generic_cache', cache.get)

    def save(key, value, ttl):
        cache[key] = value
        writes.append((key, ttl))

    monkeypatch.setattr(route.redis_db, 'set_generic_cache', save)
    retrieved = Mock()
    retrieved.to_dict_recursive.return_value = price('price_fixture', 1999)
    retrieve = Mock(return_value=retrieved)
    monkeypatch.setattr(route.stripe.Price, 'retrieve', retrieve)
    assert route._retrieve_price('price_fixture') == route._retrieve_price('price_fixture')
    retrieve.assert_called_once_with('price_fixture')
    assert writes == [('stripe_price:price_fixture', 86400)]
    cache['stripe_price:price_existing'] = price('price_existing', 2999, active=False)
    assert route._retrieve_price('price_existing')['active'] is False
    retrieve.assert_called_once()


def test_price_provider_failure_is_not_cached_and_emits_fallback(monkeypatch):
    monkeypatch.setattr(route.redis_db, 'get_generic_cache', lambda key: None)
    save = Mock()
    monkeypatch.setattr(route.redis_db, 'set_generic_cache', save)
    monkeypatch.setattr(route.stripe.Price, 'retrieve', Mock(side_effect=RuntimeError('offline fixture')))
    fallback = Mock()
    monkeypatch.setattr(route, '_degraded', fallback)
    with pytest.raises(RuntimeError, match='offline fixture'):
        route._retrieve_price('price_bad')
    save.assert_not_called()
    fallback.assert_called_once_with('storefront_price', 'hidden_price')


def test_storefront_rate_limit_runs_before_data_reads(client, monkeypatch):
    assert get_effective_limit('storefront:plans', boost=100) == (12, 60)

    limited = Mock(return_value=(False, 0, 60))
    monkeypatch.setattr(route.auth, 'check_rate_limit', limited)
    read = Mock(side_effect=AssertionError('limited request must not read data'))
    monkeypatch.setattr(route.users_db, 'get_user_valid_subscription', read)
    response = client.get('/v2/payments/plans')
    assert response.status_code == 429 and response.headers['Retry-After'] == '60'
    limited.assert_called_once_with('fixture-user', 'storefront:plans', 12, 60)
    read.assert_not_called()


@pytest.mark.parametrize('plan', ['plus', 'operator', 'architect', 'unlimited', 'unlimited_v2'])
def test_legacy_usage_never_accepts_shared_budget_projection(monkeypatch, plan):
    projection = Mock(return_value={'budget_percent': 80, 'reset_at': 1800000000})
    monkeypatch.setattr(route.subscription_utils, 'get_usage_units', projection, raising=False)
    monkeypatch.setattr(route.subscription_utils, 'transcription_allowance_seconds', lambda plan: 100)
    monkeypatch.setattr(
        route.subscription_utils, 'get_monthly_usage_for_subscription', lambda uid: {'transcription_seconds': 62}
    )
    result = route._usage('fixture', Subscription(plan=PlanType(plan), current_price_id='price_legacy'))
    assert result.kind == 'transcription' and result.percent == 62
    projection.assert_not_called()


def test_legacy_chat_meter_without_speech_allowance_is_explicitly_unavailable(monkeypatch):
    monkeypatch.setattr(
        route.subscription_utils,
        'get_usage_units',
        lambda uid: {'budget_percent': 80, 'reset_at': 1800000000},
        raising=False,
    )
    monkeypatch.setattr(route.subscription_utils, 'transcription_allowance_seconds', lambda plan: None)
    result = route._usage('fixture', Subscription(plan=PlanType.operator, current_price_id='price_legacy'))
    assert result.kind == 'unavailable' and result.percent is None


@pytest.mark.parametrize('plan', ['basic', 'plus'])
def test_shared_budget_projection_is_only_for_free_or_ladder_subscribers(monkeypatch, plan):
    monkeypatch.setattr(route.catalog, 'LADDER_V1_STRIPE_PRICES', ['price_new'], raising=False)
    projection = Mock(return_value={'budget_percent': 80, 'reset_at': 1800000000})
    monkeypatch.setattr(route.subscription_utils, 'get_usage_units', projection, raising=False)
    result = route._usage('fixture', Subscription(plan=PlanType(plan), current_price_id='price_new'))
    assert result.kind == 'usage_budget' and result.percent == 80
    projection.assert_called_once_with('fixture')


@pytest.mark.parametrize('enabled,expected', [(False, []), (True, ['proactive_agent', 'screen_context'])])
def test_endpoint_contextual_gates_require_backend_flag(client, monkeypatch, enabled, expected):
    monkeypatch.setenv('LADDER_V1_PRO_GATES_ENABLED', str(enabled).lower())
    monkeypatch.setattr(route, '_usage', lambda *args: StorefrontUsage(pro_gates=['proactive_agent', 'screen_context']))
    response = client.get('/v2/payments/plans?trigger=proactive_agent')
    assert response.status_code == 200
    assert response.json()['usage']['pro_gates'] == expected


@pytest.mark.parametrize('enabled,reached', [(False, True), (True, False), (True, True)])
def test_endpoint_daily_cap_entry_is_observed_not_inferred(client, monkeypatch, enabled, reached):
    from database import ladder_v1

    monkeypatch.setenv('LADDER_V1_MCP_DAILY_CAPS_ENABLED', str(enabled).lower())
    reads = []
    monkeypatch.setattr(ladder_v1, 'daily_cap_reached', lambda uid, cap: reads.append((uid, cap)) or reached)
    response = client.get('/v2/payments/plans?trigger=mcp_daily_cap')
    assert response.status_code == 200
    assert response.json()['usage'].get('mcp_cap_reached', False) is (enabled and reached)
    assert len(reads) == int(enabled)
