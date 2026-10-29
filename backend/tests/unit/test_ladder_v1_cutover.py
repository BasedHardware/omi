"""Cutover policy contracts: dark path, retained legacy entitlements, and cap boundaries."""

from datetime import datetime, timedelta, timezone
from tests.unit.fixtures.cap_rollout import full_cap_dispatch_rollout  # noqa: F401

import inspect
import json
from pathlib import Path

import fakeredis
import pytest
from fastapi import HTTPException

from config import ladder_v1 as policy, plan_catalog as catalog
from utils import ladder_v1 as ladder
import utils.mcp_server.transport as mcp_transport


@pytest.fixture
def bindings(monkeypatch):
    for key, row in catalog.LADDER_V1_PRICE_BINDINGS.items():
        monkeypatch.setenv(row['env_var'], 'price_' + key)
    return catalog.configured_ladder_prices()


def subscription(plan='plus', price='price_ladder_v1_plus_month'):
    return {'plan': plan, 'current_price_id': price, 'status': 'active', 'current_period_end': 4102444800}


def test_binding_resolves_all_lookup_keys_without_stripe_writes(bindings):
    assert len(bindings) == 6
    for price, row in bindings.items():
        entitlement = catalog.resolve_price_entitlements(price)
        assert entitlement['entitlement_version'] == 'ladder_v1'
        assert entitlement['plan_id'] == row['plan_id']
        assert catalog.resolve_stripe_price_plan(price).value == row['plan_id']
        assert catalog.configured_billing_price_plans()[price].value == row['plan_id']


def test_binding_rejects_legacy_reclassification_and_duplicates(monkeypatch, bindings):
    monkeypatch.setenv('LADDER_V1_PLUS_MONTH_PRICE_ID', next(iter(catalog.RECOGNIZED_STRIPE_PRICE_PLAN_TYPES)))
    with pytest.raises(ValueError, match='legacy'):
        catalog.configured_ladder_prices()
    monkeypatch.setenv('LADDER_V1_PLUS_MONTH_PRICE_ID', 'price_shared')
    monkeypatch.setenv('LADDER_V1_PRO_MONTH_PRICE_ID', 'price_shared')
    with pytest.raises(ValueError, match='distinct'):
        catalog.configured_ladder_prices()


def test_flag_off_does_not_read_account_or_ledger(monkeypatch):
    monkeypatch.delenv('LADDER_V1_BUDGET_ENFORCEMENT_ENABLED', raising=False)
    monkeypatch.delenv('LADDER_V1_PRO_GATES_ENABLED', raising=False)
    monkeypatch.delenv('LADDER_V1_MCP_DAILY_CAPS_ENABLED', raising=False)

    def forbidden(*args, **kwargs):
        pytest.fail('flag off performed a read')

    monkeypatch.setattr(ladder, 'account', forbidden)
    assert ladder.enforce_budget('u') is False
    assert ladder.feature_allowed('u', 'screen_frame_judge') is None
    assert ladder.enforce_daily_cap('u') is None


@pytest.mark.parametrize('percent,blocked', [(79.9, False), (80, False), (99.99, False), (100, True), (130, True)])
def test_budget_hold_boundary(monkeypatch, percent, blocked):
    snapshot = {'budget_percent': percent, 'plan_id': 'plus', 'period_id': '2026-10', 'reset_at': 1793491200}
    monkeypatch.setattr(ladder, 'budget_snapshot', lambda *a, **k: snapshot)
    if blocked:
        with pytest.raises(HTTPException) as error:
            ladder.enforce_budget('u')
        assert error.value.status_code == 402
        assert error.value.detail['state'] == 'held_pending_choice'
        assert error.value.detail['choices'] == ['on_device', 'upgrade']
    else:
        assert ladder.enforce_budget('u') is True


@pytest.mark.parametrize('plan,allowed', [('basic', False), ('plus', False), ('operator', True), ('architect', True)])
def test_pro_gates_preserve_on_request_features(monkeypatch, bindings, plan, allowed):
    monkeypatch.setenv('LADDER_V1_PRO_GATES_ENABLED', 'true')
    price = next((key for key, row in bindings.items() if row['plan_id'] == plan), None)
    sub = subscription(plan, price)
    assert ladder.feature_allowed('u', 'screen_frame_judge', sub) is allowed
    assert ladder.feature_allowed('u', 'desktop_proactivity', sub) is allowed
    assert ladder.feature_allowed('u', 'chat_agent', sub) is True


def test_legacy_price_bypasses_new_mechanics(monkeypatch):
    for flag in ['LADDER_V1_PRO_GATES_ENABLED', 'LADDER_V1_BUDGET_ENFORCEMENT_ENABLED']:
        monkeypatch.setenv(flag, 'true')
    price = next(p for p, plan in catalog.RECOGNIZED_STRIPE_PRICE_PLAN_TYPES.items() if plan.value == 'plus')
    sub = subscription('plus', price)
    assert ladder.budget_snapshot('u', sub) is None
    assert ladder.feature_allowed('u', 'proactive_agent', sub) is None
    assert catalog.resolve_price_entitlements(price) == catalog.get_entitlement_version('plus', 'legacy')


@pytest.fixture
def daily_module():
    from database import ladder_v1 as daily_db

    return daily_db


@pytest.mark.parametrize('plan,cap', [('basic', 100), ('plus', 500), ('operator', 5000), ('architect', 5000)])
def test_daily_cap_policy_and_error(monkeypatch, plan, cap, daily_module):
    monkeypatch.setenv('LADDER_V1_MCP_DAILY_CAPS_ENABLED', 'true')
    monkeypatch.setattr(ladder, 'account', lambda *a: {'plan_id': plan})

    def reserve(uid, actual_cap):
        assert actual_cap == cap
        return {'allowed': False, 'used': cap, 'limit': cap, 'reset_at': 4102444800, 'state': 'cap'}

    monkeypatch.setattr(daily_module, 'reserve_daily_request', reserve)
    with pytest.raises(HTTPException) as error:
        ladder.enforce_daily_cap('u')
    assert error.value.detail['trigger'] == 'mcp_daily_cap'
    assert error.value.detail['limit'] == cap


def test_price_binding_attestation(monkeypatch, bindings):
    price, row = next(iter(bindings.items()))
    good = {
        'product': next(
            p for p, plan in catalog.RECOGNIZED_STRIPE_PRODUCT_PLAN_TYPES.items() if plan.value == row['plan_id']
        ),
        'id': price,
        'lookup_key': row['lookup_key'],
        'active': True,
        'currency': 'usd',
        'unit_amount': 1999,
        'recurring': {'interval': row['interval'], 'interval_count': 1},
    }
    catalog.validate_ladder_price(price, good)
    for field, value in [('lookup_key', 'legacy_plus_month'), ('active', False), ('currency', 'jpy')]:
        with pytest.raises(ValueError):
            catalog.validate_ladder_price(price, dict(good, **{field: value}))


def test_alias_retirement_is_dark(monkeypatch):
    monkeypatch.delenv('LADDER_V1_RETIRE_PRO_ALIAS_ENABLED', raising=False)
    assert catalog.PlanType('pro') == catalog.PlanType.architect
    monkeypatch.setenv('LADDER_V1_RETIRE_PRO_ALIAS_ENABLED', 'true')
    with pytest.raises(ValueError):
        catalog.PlanType('pro')


def test_live_batch_and_on_device_are_disjoint(monkeypatch):
    monkeypatch.setenv('LADDER_V1_LANE_METERING_ENABLED', 'true')
    from database.usage_units import hourly_shadow
    from tests.unit.fixtures.shadow_usage_firestore import merge

    for source, funding, lane in [
        ('listen', 'omi', 'live'),
        ('sync_v2', 'omi', 'batch'),
        ('sync_v2', 'on_device', 'on_device'),
    ]:
        row = {}
        merge(
            row,
            hourly_shadow(
                {'transcription_seconds': 100},
                {'source': source, 'funding': funding, 'provider': 'parakeet', 'accepted_speech_seconds': 10},
            ),
        )
        lanes = row['shadow_v1']['lanes']
        assert set(lanes) == {lane}
        if lane == 'on_device':
            assert lanes[lane]['micro_units'] == 0
        else:
            assert lanes[lane]['speech_seconds'] == 10


@pytest.fixture
def cap_presentation():
    from tests.unit.test_storefront_presentation import sheet_for, ladder_catalog

    return sheet_for, ladder_catalog


def test_at_cap_backend_owned_copy_golden(monkeypatch, cap_presentation):
    sheet_for, ladder_catalog = cap_presentation

    monkeypatch.setenv('LADDER_V1_BUDGET_ENFORCEMENT_ENABLED', 'true')
    rows, recognized = ladder_catalog()
    response = sheet_for(
        'plus',
        price_id='price_plus_month',
        rows=rows,
        recognized=recognized,
        bindings=list(rows),
        percent=100,
        trigger='usage_budget',
    )
    at_cap = response.model_dump(mode='json')['at_cap']
    expected = json.loads((Path(__file__).parents[1] / 'fixtures/ladder_v1_at_cap.json').read_text())
    assert at_cap == expected
    assert at_cap['on_device_upgrade_line'] == 'Upgrade to Pro for speaker separation and higher accuracy'


def test_at_cap_body_preserves_recordings_without_automatic_reset_promise(monkeypatch, cap_presentation):
    sheet_for, ladder_catalog = cap_presentation

    monkeypatch.setenv('LADDER_V1_BUDGET_ENFORCEMENT_ENABLED', 'true')
    rows, recognized = ladder_catalog()

    def body(locale):
        response = sheet_for(
            'plus',
            price_id='price_plus_month',
            rows=rows,
            recognized=recognized,
            bindings=list(rows),
            percent=100,
            trigger='usage_budget',
            locale=locale,
        )
        return response.at_cap.body

    assert (
        body(None)
        == 'Your recordings and transcripts are saved. Waiting recordings stay waiting until you choose to process them.'
    )
    assert (
        body('es')
        == 'Tus grabaciones y transcripciones están guardadas. Las grabaciones pendientes esperarán hasta que decidas procesarlas.'
    )
    assert body('ja') == '録音と文字起こしは保存されています。処理を選択するまで、待機中の録音はそのまま保持されます。'
    assert body('ar') == 'تم حفظ تسجيلاتك ونصوصك. ستبقى التسجيلات قيد الانتظار حتى تختار معالجتها.'


def test_atomic_daily_reservations_boundary_and_reset():
    from database.ladder_v1 import daily_cap_reached, reserve_daily_request

    redis = fakeredis.FakeRedis()
    # EXPIREAT is a wall-clock timestamp, so the sample has to be the current UTC day.
    now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    first = reserve_daily_request('u', 5, now=now, redis_client=redis)
    reset_at = int((now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0).timestamp())
    assert first == {'allowed': True, 'used': 1, 'limit': 5, 'reset_at': reset_at, 'state': 'within'}
    assert daily_cap_reached('u', 5, now=now, redis_client=redis) is False
    for used in (2, 3):
        step = reserve_daily_request('u', 5, now=now, redis_client=redis)
        assert step['used'] == used and step['state'] == 'within'
    nudge = reserve_daily_request('u', 5, now=now, redis_client=redis)
    assert nudge['used'] == 4 and nudge['allowed'] and nudge['state'] == 'nudge'
    last = reserve_daily_request('u', 5, now=now, redis_client=redis)
    assert last['used'] == 5 and last['allowed'] and last['state'] == 'nudge'
    assert daily_cap_reached('u', 5, now=now, redis_client=redis) is True
    key = f"ladder_v1:api_daily:u:{now.date().isoformat()}"
    before = redis.get(key)
    blocked = reserve_daily_request('u', 5, now=now, redis_client=redis)
    assert not blocked['allowed'] and blocked['used'] == 5 and blocked['state'] == 'cap'
    assert redis.get(key) == before
    other = reserve_daily_request('other', 5, now=now, redis_client=redis)
    assert other['allowed'] and other['used'] == 1
    tomorrow = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    reset = reserve_daily_request('u', 5, now=tomorrow, redis_client=redis)
    assert reset['allowed'] and reset['used'] == 1 and reset['state'] == 'within'
    ttl = redis.ttl(key)
    expected = reset_at - int(datetime.now(timezone.utc).timestamp())
    assert abs(ttl - expected) <= 2


def test_daily_cap_redis_outage_stays_retryable(monkeypatch):
    import database.ladder_v1 as daily

    monkeypatch.setenv('LADDER_V1_MCP_DAILY_CAPS_ENABLED', 'true')
    monkeypatch.setattr(ladder, 'account', lambda *a, **k: {'plan_id': 'plus'})

    def unavailable(*args, **kwargs):
        raise ConnectionError('redis down')

    monkeypatch.setattr(daily, 'reserve_daily_request', unavailable)
    with pytest.raises(HTTPException) as error:
        ladder.enforce_daily_cap('u')
    assert error.value.status_code == 503
    assert error.value.detail == 'usage_unavailable'
    assert error.value.headers['Retry-After'] == '30'


def test_api_enforcement_keeps_the_daily_cap_and_skips_the_budget(monkeypatch):
    import asyncio

    from fastapi import Response

    import dependencies

    monkeypatch.setenv('LADDER_V1_BUDGET_ENFORCEMENT_ENABLED', 'true')
    monkeypatch.setenv('LADDER_V1_MCP_DAILY_CAPS_ENABLED', 'true')
    calls = []
    assert 'enforce_budget' not in inspect.getsource(dependencies._enforce_ladder_api)
    assert 'enforce_budget' not in inspect.getsource(mcp_transport._handle_tool_call)
    monkeypatch.setattr(
        dependencies,
        'enforce_daily_cap',
        lambda uid: calls.append('daily') or {'state': 'nudge', 'reset_at': 4102444800},
    )
    response = Response()
    asyncio.run(dependencies._enforce_ladder_api('u', response))
    assert calls == ['daily']
    assert response.headers['X-Omi-Usage-State'] == 'nudge'
    assert response.headers['X-Omi-Usage-Reset-At'] == '4102444800'
    assert response.headers['X-Omi-Storefront-Trigger'] == 'mcp_daily_cap'

    calls.clear()
    monkeypatch.delenv('LADDER_V1_BUDGET_ENFORCEMENT_ENABLED', raising=False)
    monkeypatch.delenv('LADDER_V1_MCP_DAILY_CAPS_ENABLED', raising=False)
    quiet = Response()
    asyncio.run(dependencies._enforce_ladder_api('u', quiet))
    assert calls == []
    assert 'X-Omi-Usage-State' not in quiet.headers


@pytest.mark.parametrize(
    'plan,limit',
    [('basic', 2000), ('plus', 5000), ('operator', 25000), ('architect', 25000)],
)
def test_api_read_limit_follows_the_ladder_plan(bindings, plan, limit):
    if plan == 'basic':
        subscription_row = {'plan': 'basic'}
    else:
        price = next(key for key, row in bindings.items() if row['plan_id'] == plan)
        subscription_row = subscription(plan, price)
    assert ladder.api_max_reads_per_request('u', subscription_row) == limit


def test_legacy_prices_resolve_api_read_limit_to_none():
    price = next(item for item, plan in catalog.RECOGNIZED_STRIPE_PRICE_PLAN_TYPES.items() if plan.value == 'plus')
    assert ladder.api_max_reads_per_request('u', subscription('plus', price)) is None


@pytest.fixture
def choice_http(monkeypatch):
    import os

    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from routers import budget_choice
    from utils.transcription_allowance import TranscriptionAllowance
    from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
    from database import budget_choice as choice_db

    store = StrictFirestore()
    monkeypatch.setenv('HELD_CONTENT_ENABLED', 'true')

    def cohort_tokens():
        if os.getenv('HELD_CONTENT_ENABLED', 'false').lower() != 'true':
            return ''
        return os.getenv('HELD_CONTENT_COHORT', 'all')

    monkeypatch.setattr(budget_choice.held_content_cohort.runtime_cohort, 'tokens', cohort_tokens)
    monkeypatch.setattr(
        budget_choice,
        'resolve_transcription_allowance',
        lambda *a: TranscriptionAllowance('on_device', 0, 'usage_budget_exhausted'),
    )
    monkeypatch.setattr(
        budget_choice.choices_db,
        'get_choice',
        lambda uid, period: choice_db.current_choice(
            store.rows.get(('users', uid, 'budget_choice', 'current')), period
        ),
    )
    original = choice_db.set_choice
    monkeypatch.setattr(
        budget_choice.choices_db,
        'set_choice',
        lambda uid, period, choice, dont_ask: original(uid, period, choice, dont_ask, firestore_client=store),
    )
    app = FastAPI()
    app.include_router(budget_choice.router)
    app.dependency_overrides[budget_choice.choice_uid] = lambda: 'u'
    with TestClient(app) as client:
        yield client, budget_choice.budget_period()


def test_actual_choice_http_holds_then_persists_once(choice_http):
    client, period = choice_http
    headers = {'X-Omi-Held-Content': '1'}
    initial = client.get('/v1/users/budget-choice', headers=headers)
    assert initial.status_code == 200
    assert initial.json()['state'] == 'held_pending_choice' and initial.json()['ask'] is True
    chosen = client.put(
        '/v1/users/budget-choice',
        headers=headers,
        json={'period': period, 'choice': 'on_device', 'dont_ask_again': True},
    )
    assert chosen.status_code == 200 and chosen.json()['ask'] is False
    replay = client.get('/v1/users/budget-choice', headers=headers)
    assert replay.json()['state'] == 'on_device' and replay.json()['ask'] is False
    assert client.get('/v1/users/budget-choice').status_code == 404


def test_ladder_quotas_do_not_use_legacy_chat_cap_or_overage(monkeypatch):
    from utils import subscription as sub, overage
    from models.users import Subscription, PlanType

    monkeypatch.setattr(sub, 'is_trial_paywalled', lambda *a, **k: False)
    monkeypatch.setattr(
        sub.users_db, 'get_user_valid_subscription', lambda *a, **k: Subscription(plan=PlanType.operator)
    )
    monkeypatch.setattr(
        sub.user_usage_db,
        'get_monthly_chat_usage',
        lambda *a, **k: {'questions': 100000, 'cost_usd': 1000, 'reset_at': 4102444800},
    )
    monkeypatch.setattr(
        sub.ladder_v1, 'budget_snapshot', lambda *a, **k: {'budget_percent': 80, 'reset_at': 4102444800}
    )
    snapshot = sub.get_chat_quota_snapshot('u')
    assert snapshot['allowed'] is True and snapshot['is_overage_plan'] is False
    monkeypatch.setattr(overage, 'budget_enforcement_enabled', lambda: True)
    monkeypatch.setattr(overage, 'account', lambda uid: {'plan_id': 'operator'})
    assert overage.get_user_overage('u', PlanType.operator)['overage_usd'] == 0


@pytest.fixture
def checkout_boundary():
    from routers import payment
    from utils.subscription import is_purchasable_price_id

    return payment, is_purchasable_price_id


def test_checkout_uses_bound_price_only_with_storefront_flag(monkeypatch, bindings, checkout_boundary):
    from types import SimpleNamespace

    payment, purchasable = checkout_boundary
    price, row = next(iter(bindings.items()))
    monkeypatch.delenv('STOREFRONT_LADDER_V1_ENABLED', raising=False)
    assert purchasable(price) is False
    with pytest.raises(HTTPException) as error:
        payment._validate_price_id(price)
    assert error.value.status_code == 400
    monkeypatch.setenv('STOREFRONT_LADDER_V1_ENABLED', 'true')
    good = {
        'id': price,
        'lookup_key': row['lookup_key'],
        'active': True,
        'currency': 'usd',
        'unit_amount': 1999,
        'recurring': {'interval': row['interval'], 'interval_count': 1},
        'product': next(
            p for p, plan in catalog.RECOGNIZED_STRIPE_PRODUCT_PLAN_TYPES.items() if plan.value == row['plan_id']
        ),
    }
    monkeypatch.setattr(
        payment.stripe.Price, 'retrieve', lambda identifier: SimpleNamespace(to_dict_recursive=lambda: good)
    )
    assert purchasable(price) is True
    payment._validate_price_id(price)
    catalog.validate_ladder_price(price, dict(good, active=False), allow_archived=True)
    good['lookup_key'] = 'wrong_key'
    with pytest.raises(HTTPException) as error:
        payment._validate_price_id(price)
    assert error.value.status_code == 503


def test_api_units_join_monthly_budget_once_without_transcription():
    from database.usage_units import get_usage_units
    from tests.unit.fixtures.shadow_usage_firestore import Store

    store = Store({'users/u/ladder_v1_api_days/2026-10-14': {'requests': 2, 'micro_units': 2000000}})
    snapshot = get_usage_units(
        'u',
        datetime(2026, 10, 14, tzinfo=timezone.utc),
        firestore_client=store,
        entitlements=catalog.get_entitlement_version('basic', 'ladder_v1'),
    )
    assert snapshot['used_units'] == 2
    assert snapshot['by_feature'] == {'mcp_api': 2}
    assert snapshot['completeness']['by_feature']['mcp_api'] == {'provisional': 2}


def test_bound_intervals_support_reactivation_and_never_match_month_to_year(bindings):
    from utils.subscription import price_ids_match_plan_and_interval

    for tier in ('plus', 'pro', 'architect'):
        month = f'price_ladder_v1_{tier}_month'
        year = f'price_ladder_v1_{tier}_year'
        assert price_ids_match_plan_and_interval(month, month)
        assert price_ids_match_plan_and_interval(year, year)
        assert not price_ids_match_plan_and_interval(month, year)
        assert not price_ids_match_plan_and_interval(year, month)


def test_flag_off_cold_import_never_resolves_database(monkeypatch):
    from types import ModuleType
    from testing.import_isolation import load_module_fresh, stub_modules

    for key in (
        'LADDER_V1_BUDGET_ENFORCEMENT_ENABLED',
        'LADDER_V1_PRO_GATES_ENABLED',
        'LADDER_V1_MCP_DAILY_CAPS_ENABLED',
    ):
        monkeypatch.delenv(key, raising=False)
    database = ModuleType('database')
    database.__path__ = []

    def forbidden(name):
        raise AssertionError(f'flag-off database resolution: {name}')

    database.__getattr__ = forbidden
    with stub_modules({'database': database}):
        cold = load_module_fresh('utils.ladder_v1', str(Path(__file__).parents[2] / 'utils/ladder_v1.py'))
        assert cold.budget_snapshot('u') is None
        assert cold.feature_allowed('u', 'screen_context') is None
        assert cold.enforce_daily_cap('u') is None


@pytest.mark.parametrize(
    'plan,key,upgrade',
    [
        ('basic', None, 'unlimited_v2'),
        ('plus', 'ladder_v1_plus_month', 'unlimited_v2'),
        ('operator', 'ladder_v1_pro_month', 'unlimited_v2'),
        ('architect', 'ladder_v1_architect_month', None),
    ],
)
def test_chat_stops_at_shared_budget_and_reset_unblocks(monkeypatch, bindings, plan, key, upgrade):
    monkeypatch.setenv('LADDER_V1_BUDGET_ENFORCEMENT_ENABLED', 'true')
    sub = subscription(plan, 'price_' + key if key else None)
    monkeypatch.setattr(ladder, 'account', lambda *a, **k: policy.entitlements(sub))
    from database import usage_units

    now = datetime(2026, 10, 31, 23, 59, tzinfo=timezone.utc)

    class Clock:
        @staticmethod
        def now(tz):
            return now

        def __new__(cls, *args, **kwargs):
            return datetime(*args, **kwargs)

    monkeypatch.setattr(ladder, 'datetime', Clock)
    monkeypatch.setattr(
        usage_units,
        'get_usage_units',
        lambda uid, date, **kw: {
            'budget_units': 100,
            'used_units': 100 if date.month == 10 else 0,
        },
    )
    with pytest.raises(HTTPException) as error:
        ladder.enforce_chat_budget('u')
    assert error.value.status_code == 402
    pause = error.value.detail['chat_at_cap']
    assert pause['state'] == 'paused'
    assert pause['title'] == 'Chat is paused'
    assert pause['trigger'] == 'usage_budget'
    assert pause['upgrade_plan'] == upgrade
    assert pause['reset_line'] == 'Chat is back on Nov 1.'
    now = datetime(2026, 11, 1, tzinfo=timezone.utc)
    assert ladder.enforce_chat_budget('u') is True


def test_chat_dark_path_and_legacy_do_not_read_ledger(monkeypatch):
    def forbidden(*a, **k):
        pytest.fail('dark or legacy path read ledger')

    monkeypatch.delenv('LADDER_V1_BUDGET_ENFORCEMENT_ENABLED', raising=False)
    monkeypatch.setattr(ladder, 'usage_snapshot', forbidden)
    assert ladder.enforce_chat_budget('u') is False
    monkeypatch.undo()
    monkeypatch.setenv('LADDER_V1_BUDGET_ENFORCEMENT_ENABLED', 'true')
    price = next(p for p, plan in catalog.RECOGNIZED_STRIPE_PRICE_PLAN_TYPES.items() if plan.value == 'plus')
    monkeypatch.setattr(ladder, 'account', lambda *a, **k: policy.entitlements(subscription('plus', price)))
    from database import usage_units

    monkeypatch.setattr(usage_units, 'get_usage_units', forbidden)
    assert ladder.enforce_chat_budget('u') is False


@pytest.mark.parametrize(
    'plan,upgrade',
    [('basic', 'unlimited_v2'), ('plus', 'unlimited_v2'), ('operator', 'unlimited_v2'), ('architect', None)],
)
def test_chat_pause_payload_is_only_flagged_exhausted_ladder(monkeypatch, cap_presentation, plan, upgrade):
    sheet_for, ladder_catalog = cap_presentation
    rows, recognized = ladder_catalog()
    kwargs = dict(
        price_id=None if plan == 'basic' else 'price_' + plan + '_month',
        rows=rows,
        recognized=recognized,
        bindings=list(rows),
        trigger='usage_budget',
    )
    monkeypatch.delenv('LADDER_V1_BUDGET_ENFORCEMENT_ENABLED', raising=False)
    assert 'chat_at_cap' not in sheet_for(plan, percent=100, **kwargs).model_dump(mode='json')
    monkeypatch.setenv('LADDER_V1_BUDGET_ENFORCEMENT_ENABLED', 'true')
    assert sheet_for(plan, percent=99.99, **kwargs).chat_at_cap is None
    payload = sheet_for(plan, percent=100, **kwargs).model_dump(mode='json')
    assert payload['chat_at_cap']['upgrade_plan'] == upgrade
    import os

    if os.environ.get('UPDATE_CHAT_CAP_GOLDENS') == '1':
        Path(__file__).parents[1].joinpath('fixtures', f'chat_at_cap_{plan}.json').write_text(
            json.dumps(payload['chat_at_cap'], ensure_ascii=False, indent=2) + '\n'
        )
    expected = json.loads(Path(__file__).parents[1].joinpath('fixtures', f'chat_at_cap_{plan}.json').read_text())
    assert payload['chat_at_cap'] == expected
    legacy = sheet_for(
        'plus', price_id='price_legacy_plus', percent=100, rows=rows, recognized=recognized, bindings=list(rows)
    )
    assert legacy.chat_at_cap is None


@pytest.mark.parametrize('percent', [0, 80, 99.99])
def test_chat_below_shared_budget_still_allowed(monkeypatch, percent):
    monkeypatch.setattr(
        ladder,
        'budget_snapshot',
        lambda *a, **k: {'budget_percent': percent, 'budget_units': 100, 'used_units': percent},
    )
    assert ladder.enforce_chat_budget('u') is True


def test_unprojected_usage_exhausts_budget_and_emits_coverage(monkeypatch):
    from database import usage_units
    from tests.unit.fixtures.shadow_usage_firestore import Store
    from utils.observability import ladder_v1 as metrics
    from unittest.mock import Mock

    monkeypatch.setenv('LADDER_V1_BUDGET_ENFORCEMENT_ENABLED', 'true')
    monkeypatch.setattr(
        ladder,
        'account',
        lambda *a, **k: {
            'plan_id': 'plus',
            'entitlement_version': 'ladder_v1',
            'budget': {'kind': 'units', 'value': 1},
        },
    )
    now = datetime.now(timezone.utc)
    store = Store(
        {
            'users/u/hourly_usage/current': {
                'year': now.year,
                'month': now.month,
                'transcription_seconds': 3600,
            }
        }
    )
    seconds, attempts = Mock(), Mock()
    monkeypatch.setattr(metrics.UNPROJECTED_SECONDS, 'observe', seconds)
    monkeypatch.setattr(metrics.UNPROJECTED_ATTEMPTS, 'observe', attempts)
    snapshot = ladder.budget_snapshot('u', firestore_client=store)
    assert snapshot['used_units'] > snapshot['budget_units']
    seconds.assert_called_once_with(3600)
    attempts.assert_called_once_with(0)
    with pytest.raises(HTTPException) as error:
        ladder.enforce_budget('u', firestore_client=store)
    assert error.value.status_code == 402
    assert store.writes == 0


def test_coverage_metrics_survive_isolated_auth_reimports():
    from testing.import_isolation import load_module_fresh
    from utils.observability import ladder_v1 as metrics

    path = str(Path(__file__).parents[2] / 'utils/observability/ladder_v1.py')
    for _ in range(3):
        reloaded = load_module_fresh('utils.observability.ladder_v1', path)
        assert reloaded.UNPROJECTED_SECONDS is metrics.UNPROJECTED_SECONDS
        assert reloaded.UNPROJECTED_ATTEMPTS is metrics.UNPROJECTED_ATTEMPTS


@pytest.mark.parametrize('key', ['ambiguous_priced_transcription_seconds', 'ambiguous_priced_gateway_attempts'])
@pytest.mark.parametrize('dispatch', [False, True])
def test_historical_mixed_coverage_admits_on_snapshot(monkeypatch, key, dispatch):
    from types import SimpleNamespace
    from utils import stt_cap_dispatch, subscription

    monkeypatch.setenv('LADDER_V1_BUDGET_ENFORCEMENT_ENABLED', 'true')
    monkeypatch.setenv('STT_CAP_DISPATCH_ENFORCEMENT', str(dispatch).lower())
    snapshot = {'budget_percent': 0, 'used_units': 0, 'budget_units': 100, 'completeness': {key: 1}}
    monkeypatch.setattr(ladder, 'usage_snapshot', lambda *a, **k: snapshot)
    monkeypatch.setattr(subscription, 'is_marketplace_reviewer', lambda _: False)
    monkeypatch.setattr(subscription, 'is_trial_paywalled', lambda *a, **k: False)
    monkeypatch.setattr(
        subscription.users_db, 'get_user_valid_subscription', lambda *a, **k: SimpleNamespace(plan='plus')
    )
    assert ladder.budget_snapshot('u') is snapshot
    assert stt_cap_dispatch.sync_allowed('u')
    assert stt_cap_dispatch.funded_allowance('u').reason == 'usage_budget_available'
