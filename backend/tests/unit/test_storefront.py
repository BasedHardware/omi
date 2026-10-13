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
from utils.storefront import build_storefront, load_ladder, present_prices


def price(identifier, amount, interval='month', **overrides):
    return {
        'id': identifier,
        'currency': 'usd',
        'unit_amount': amount,
        'active': True,
        'recurring': {'interval': interval, 'interval_count': 1},
        **overrides,
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
    assert [(tier.plan_id, tier.action) for tier in sheet.tiers] == [('basic', 'current'), ('architect', 'contact')]
    assert sheet.current.legacy is False


@pytest.mark.parametrize('plan', ['plus', 'operator', 'architect', 'unlimited', 'unlimited_v2'])
def test_legacy_subscriber_has_exactly_one_current_row_even_without_stripe(plan):
    sheet = build(plan, 'price_old')
    current = [tier for tier in sheet.tiers if tier.action == 'current']
    assert len(current) == 1
    assert current[0].plan_id == plan and current[0].legacy
    assert current[0].prices == []
    assert sheet.current.price_id == 'price_old' and sheet.current.legacy
    assert not any(tier.action == 'upgrade' for tier in sheet.tiers)


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
    assert [tier.plan_id for tier in sheet.tiers] == ['basic', 'plus', 'operator', 'architect']
    assert [tier.action for tier in sheet.tiers] == ['current', 'upgrade', 'upgrade', 'upgrade']
    plus = sheet.tiers[1]
    assert sheet.next_offer_tier_id == 'plus:ladder_v1'
    assert plus.recommended
    assert plus.prices[1].monthly_equivalent == '$16.66/mo'
    assert plus.prices[1].annual_savings.amount_minor == 3998
    assert plus.prices[1].annual_savings.percent == 16.67
    assert {f.key: f.included for f in plus.features}['screen_context'] is False
    pro = sheet.tiers[2]
    assert {f.key: f.included for f in pro.features}['proactive_agent'] is True
    paid = build('operator', 'price_operator_month', rows, list(rows), recognized)
    assert paid.next_offer_tier_id == 'architect:ladder_v1'
    assert [tier.action for tier in paid.tiers] == [
        'downgrade_not_offered',
        'downgrade_not_offered',
        'current',
        'upgrade',
    ]


def test_price_currency_interval_and_negative_savings_validation():
    assert not present_prices([price('bad', 1999, currency='jpy')])
    assert not present_prices([price('bad', 1999, active=False)])
    assert not present_prices([price('bad', 1999, recurring={'interval': 'month', 'interval_count': 3})])
    rows = present_prices([price('month', 2100), price('year', 25000, 'year')])
    assert rows[1].annual_savings.amount_minor == 200
    assert rows[1].annual_savings.percent == 0.79
    assert present_prices([price('month', 1000), price('year', 13000, 'year')])[1].annual_savings is None
    assert present_prices([price('old', 1999, active=False)], current=True)


@pytest.fixture
def client(monkeypatch):
    app = FastAPI()
    app.include_router(route.router)
    app.dependency_overrides[route.auth.get_current_user_uid_no_byok_validation] = lambda: 'fixture-user'
    monkeypatch.setattr(route.auth, 'check_rate_limit', lambda *args: (True, 12, 0))
    monkeypatch.setattr(route.auth, 'RATE_LIMIT_SHADOW', False)
    monkeypatch.setenv('STOREFRONT_LADDER_V1_ENABLED', 'true')
    monkeypatch.setattr(route, 'should_hide_subscription_ui', lambda *args: False)
    monkeypatch.setattr(route.users_db, 'get_user_valid_subscription', lambda uid, **kwargs: Subscription())
    monkeypatch.setattr(route, '_usage', lambda *args: StorefrontUsage())
    return TestClient(app)


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
    assert [tier['display_name'] for tier in json.loads(bodies[0])['tiers']] == ['Free', 'Plus', 'Pro', 'Architect']
    assert all(call.kwargs == {'provision': False} for call in read.call_args_list)


def test_new_current_row_survives_missing_purchasable_prices():
    sheet = build('plus', 'price_new', bindings=['price_new'])
    current = [tier for tier in sheet.tiers if tier.action == 'current']
    assert len(current) == 1 and current[0].plan_id == 'plus'
    assert not current[0].legacy


def test_legacy_current_price_is_preserved_even_when_archived():
    sheet = build('plus', 'price_old', rows={'price_old': price('price_old', 1799, active=False)})
    current = next(tier for tier in sheet.tiers if tier.action == 'current')
    assert current.prices[0].amount_minor == 1799


def test_usage_absence_and_bad_projection_never_invent_budget(monkeypatch):
    monkeypatch.setattr(route.subscription_utils, 'transcription_allowance_seconds', lambda plan: 100)
    monkeypatch.setattr(
        route.subscription_utils, 'get_monthly_usage_for_subscription', lambda uid: {'transcription_seconds': 62}
    )
    assert route._usage('fixture', Subscription()).model_dump()['budget_percent'] == 62
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
    assert schema['components']['schemas']['StorefrontTier']['properties']['action']['enum'] == [
        'current',
        'upgrade',
        'downgrade_not_offered',
        'contact',
    ]


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
    rows, recognized = {}, []
    for plan, monthly in [('plus', 1999), ('operator', 4999), ('architect', 19900)]:
        for interval, amount in [('month', monthly), ('year', monthly * 10)]:
            key = f'price_fixture_{plan}_{interval}'
            rows[key] = price(key, amount, interval)
            recognized.append(
                {'price_id': key, 'plan_id': plan, 'interval': interval, 'entitlement_version': 'ladder_v1'}
            )
    expected = json.loads((Path(__file__).parent / 'fixtures/storefront/ladder_v1_free.json').read_text())
    assert build(rows=rows, bindings=list(rows), recognized=recognized).model_dump() == expected


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
    # Non-basic includes legacy plans; their recommendation must not authorize migration.
    sheet = build(
        plan,
        None if plan == 'basic' else 'price_legacy',
        rows,
        list(rows),
        recognized,
        source='macos_usage_limit',
        trigger=trigger,
    )
    expected = (
        []
        if plan in {'operator', 'architect'}
        else ['operator'] if plan != 'basic' or trigger in {'proactive_agent', 'screen_context'} else ['plus']
    )
    assert [tier.plan_id for tier in sheet.tiers if tier.recommended] == expected
    if plan != 'basic':
        assert not any(tier.action == 'upgrade' for tier in sheet.tiers)


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
    assert by_plan['basic'].action == 'downgrade_not_offered'
    if offers:
        assert by_plan['plus'].action == 'downgrade_not_offered'
        assert not by_plan['plus'].recommended
        assert by_plan['operator'].action == by_plan['architect'].action == 'contact'
        assert by_plan['operator'].recommended
    assert len([tier for tier in sheet.tiers if tier.action == 'current']) == 1
    assert by_plan[plan].action == 'current' and by_plan[plan].legacy
    assert by_plan[plan].prices[0].amount_minor == 2999
    assert [feature.key for feature in by_plan[plan].features] == ['legacy_entitlements']
    assert sheet.next_offer_tier_id is None


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
    assert cards[0].action == 'current' and cards[0].legacy
    assert [feature.key for feature in cards[0].features] == ['legacy_entitlements']
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
    assert result.kind == 'transcription' and result.budget_percent == 62
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
    assert result.kind == 'unavailable' and result.budget_percent is None


@pytest.mark.parametrize('plan', ['basic', 'plus'])
def test_shared_budget_projection_is_only_for_free_or_ladder_subscribers(monkeypatch, plan):
    monkeypatch.setattr(route.catalog, 'LADDER_V1_STRIPE_PRICES', ['price_new'], raising=False)
    projection = Mock(return_value={'budget_percent': 80, 'reset_at': 1800000000})
    monkeypatch.setattr(route.subscription_utils, 'get_usage_units', projection, raising=False)
    result = route._usage('fixture', Subscription(plan=PlanType(plan), current_price_id='price_new'))
    assert result.kind == 'usage_budget' and result.budget_percent == 80
    projection.assert_called_once_with('fixture')
