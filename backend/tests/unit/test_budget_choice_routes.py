"""HTTP contract with no real identity, database, subscription, or provider access."""

import os
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from testing.import_isolation import load_module_fresh, stub_modules
from utils.other import endpoints as real_auth
from database import budget_choice as real_choices
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore

_get_choice = real_choices.get_choice
_set_choice = real_choices.set_choice


@pytest.fixture(scope='module')
def route_module():
    subscription = ModuleType('utils.subscription')
    subscription.resolve_transcription_allowance = lambda uid, source=None: SimpleNamespace(
        managed=False, reason='plan_allowance_exhausted'
    )
    auth = ModuleType('utils.other.endpoints')
    auth.get_current_user_uid_no_byok_validation = lambda: 'synthetic-test-user'
    auth.with_rate_limit = real_auth.with_rate_limit
    with stub_modules({'utils.subscription': subscription, 'utils.other.endpoints': auth}):
        yield load_module_fresh(
            'routers.budget_choice', str(Path(__file__).resolve().parents[2] / 'routers/budget_choice.py')
        )


@pytest.fixture
def api(monkeypatch, route_module):
    route = route_module

    async def inline(pool, function, *args, **kwargs):
        return function(*args, **kwargs)

    monkeypatch.setattr(route, 'run_blocking', inline)
    monkeypatch.setattr(real_auth, 'run_blocking', inline)
    monkeypatch.setattr(real_auth, '_enforce_rate_limit', lambda *args, **kwargs: None)
    monkeypatch.setattr(route, 'budget_period', lambda: '2026-10')

    def cohort_tokens():
        if os.getenv('HELD_CONTENT_ENABLED', 'false').lower() != 'true':
            return ''
        return os.getenv('HELD_CONTENT_COHORT', 'all')

    monkeypatch.setattr(route.held_content_cohort.runtime_cohort, 'tokens', cohort_tokens)
    monkeypatch.setattr(route.choices_db, 'get_choice', lambda uid, period: None)
    monkeypatch.setattr(
        route.choices_db,
        'set_choice',
        lambda uid, period, choice, dont_ask: {
            'period': period,
            'choice': choice,
            'dont_ask_again': dont_ask,
        },
    )
    app = FastAPI()
    app.include_router(route.router)
    return TestClient(app), route


@pytest.mark.parametrize('flag,header', [('false', '1'), ('true', None), ('true', '2')])
def test_dark_or_legacy_does_no_reads(api, monkeypatch, flag, header):
    client, route = api
    monkeypatch.setenv('HELD_CONTENT_ENABLED', flag)
    monkeypatch.setattr(route, 'resolve_transcription_allowance', lambda uid, source=None: pytest.fail('must not read'))
    assert (
        client.get('/v1/users/budget-choice', headers={'X-Omi-Held-Content': header} if header else {}).status_code
        == 404
    )


def test_get_prompts_once_and_upgrade_stays_held(api, monkeypatch):
    client, route = api
    monkeypatch.setenv('HELD_CONTENT_ENABLED', 'true')
    headers = {'X-Omi-Held-Content': '1'}
    response = client.get('/v1/users/budget-choice', headers=headers).json()
    assert response['state'] == 'held_pending_choice' and response['ask'] is True
    monkeypatch.setattr(
        route.choices_db,
        'get_choice',
        lambda uid, period: {'period': period, 'choice': 'upgrade', 'dont_ask_again': False},
    )
    response = client.get('/v1/users/budget-choice', headers=headers).json()
    assert response['state'] == 'held_pending_choice' and response['ask'] is False


def test_put_validates_period_and_never_grants_entitlement(api, monkeypatch):
    client, route = api
    monkeypatch.setenv('HELD_CONTENT_ENABLED', 'true')
    headers = {'X-Omi-Held-Content': '1'}
    body = {'period': '2026-09', 'choice': 'on_device'}
    assert client.put('/v1/users/budget-choice', headers=headers, json=body).status_code == 409
    body['period'] = '2026-10'
    assert client.put('/v1/users/budget-choice', headers=headers, json=body).json()['ask'] is False
    monkeypatch.setattr(
        route,
        'resolve_transcription_allowance',
        lambda uid, source=None: SimpleNamespace(managed=True, reason='plan_within_allowance'),
    )
    assert client.put('/v1/users/budget-choice', headers=headers, json=body).status_code == 409
    assert client.get('/v1/users/budget-choice', headers=headers).json()['state'] == 'managed'


def test_put_conflict_and_strict_input(api, monkeypatch):
    client, route = api
    monkeypatch.setenv('HELD_CONTENT_ENABLED', 'true')
    headers = {'X-Omi-Held-Content': '1'}

    def conflict(*args):
        raise route.choices_db.BudgetChoiceConflict('choice_already_recorded')

    monkeypatch.setattr(route.choices_db, 'set_choice', conflict)
    body = {'period': '2026-10', 'choice': 'upgrade'}
    assert client.put('/v1/users/budget-choice', headers=headers, json=body).status_code == 409
    body['dont_ask_again'] = 'true'
    assert client.put('/v1/users/budget-choice', headers=headers, json=body).status_code == 422


def test_flag_off_put_valid_body_is_dark_and_malformed_json_does_no_reads(api, monkeypatch):
    client, route = api
    monkeypatch.setenv('HELD_CONTENT_ENABLED', 'false')

    def forbidden():
        pytest.fail('dark request must not authenticate')

    client.app.dependency_overrides[route.auth.get_current_user_uid_no_byok_validation] = forbidden
    monkeypatch.setattr(route, 'resolve_transcription_allowance', lambda *args: pytest.fail('must not read'))
    monkeypatch.setattr(route.choices_db, 'set_choice', lambda *args: pytest.fail('must not write'))
    headers = {'X-Omi-Held-Content': '1'}
    assert (
        client.put(
            '/v1/users/budget-choice', headers=headers, json={'period': '2026-10', 'choice': 'upgrade'}
        ).status_code
        == 404
    )
    assert (
        client.put(
            '/v1/users/budget-choice', headers={**headers, 'Content-Type': 'application/json'}, content='{'
        ).status_code
        == 422
    )


@pytest.mark.parametrize('platform', ['macos', 'windows', 'desktop'])
def test_platform_trial_paywall_is_unavailable_and_cannot_store_choice(api, monkeypatch, platform):
    client, route = api
    monkeypatch.setenv('HELD_CONTENT_ENABLED', 'true')

    def allowance(uid, source=None):
        assert source == platform
        return SimpleNamespace(managed=False, reason='trial_paywalled')

    monkeypatch.setattr(route, 'resolve_transcription_allowance', allowance)
    monkeypatch.setattr(route.choices_db, 'set_choice', lambda *args: pytest.fail('must not write'))
    headers = {'X-Omi-Held-Content': '1', 'X-App-Platform': platform}
    response = client.get('/v1/users/budget-choice', headers=headers)
    assert response.json()['state'] == 'unavailable' and response.json()['ask'] is False
    assert 'upgrade_available' not in response.json()
    assert (
        client.put('/v1/users/budget-choice', headers=headers, json={'period': '2026-10', 'choice': 'upgrade'}).json()[
            'detail'
        ]
        == 'budget_not_exhausted'
    )


def test_excluded_cohort_does_not_read_usage_or_choice(api, monkeypatch):
    client, route = api
    monkeypatch.setenv('HELD_CONTENT_ENABLED', 'true')
    monkeypatch.setenv('HELD_CONTENT_COHORT', 'uid:other-synthetic-user')
    monkeypatch.setattr(route, 'resolve_transcription_allowance', lambda *args: pytest.fail('must not read'))
    monkeypatch.setattr(route.choices_db, 'get_choice', lambda *args: pytest.fail('must not read'))
    monkeypatch.setattr(route.choices_db, 'set_choice', lambda *args: pytest.fail('must not write'))
    headers = {'X-Omi-Held-Content': '1'}
    assert client.get('/v1/users/budget-choice', headers=headers).status_code == 404
    assert (
        client.put(
            '/v1/users/budget-choice', headers=headers, json={'period': '2026-10', 'choice': 'on_device'}
        ).status_code
        == 404
    )


def test_clock_step_back_conflict_retains_period_changed_reason(api, monkeypatch):
    client, route = api
    monkeypatch.setenv('HELD_CONTENT_ENABLED', 'true')

    def conflict(*args):
        raise route.choices_db.BudgetChoiceConflict('budget_period_changed')

    monkeypatch.setattr(route.choices_db, 'set_choice', conflict)
    response = client.put(
        '/v1/users/budget-choice', headers={'X-Omi-Held-Content': '1'}, json={'period': '2026-10', 'choice': 'upgrade'}
    )
    assert response.status_code == 409 and response.json()['detail'] == 'budget_period_changed'


@pytest.mark.parametrize('method', ['get', 'put'])
@pytest.mark.parametrize('status', [429, 503])
def test_rate_limit_denial_precedes_usage_and_choice_reads(api, monkeypatch, method, status):
    client, route = api
    monkeypatch.setenv('HELD_CONTENT_ENABLED', 'true')

    def denied(uid, policy, *, fail_closed):
        assert policy == 'users:budget_choice' and fail_closed
        raise HTTPException(status_code=status, detail='limited')

    monkeypatch.setattr(real_auth, '_enforce_rate_limit', denied)
    monkeypatch.setattr(route, 'resolve_transcription_allowance', lambda *args: pytest.fail('must not read'))
    monkeypatch.setattr(route.choices_db, 'get_choice', lambda *args: pytest.fail('must not read'))
    monkeypatch.setattr(route.choices_db, 'set_choice', lambda *args: pytest.fail('must not write'))
    kwargs = {'headers': {'X-Omi-Held-Content': '1'}}
    if method == 'put':
        kwargs['json'] = {'period': '2026-10', 'choice': 'on_device'}
    assert getattr(client, method)('/v1/users/budget-choice', **kwargs).status_code == status


def test_response_contracts_are_named_openapi_models(api):
    client, route = api
    paths = client.app.openapi()['paths']['/v1/users/budget-choice']
    assert paths['get']['responses']['200']['content']['application/json']['schema']['$ref'].endswith(
        '/BudgetChoiceResponse'
    )
    assert paths['put']['responses']['200']['content']['application/json']['schema']['$ref'].endswith(
        '/BudgetChoiceWriteResponse'
    )


def test_budget_choice_rate_ceiling_is_boost_exempt(monkeypatch):
    from utils import rate_limit_config

    monkeypatch.setattr(rate_limit_config, 'RATE_LIMIT_BOOST', 100.0)
    assert 'users:budget_choice' in rate_limit_config.BOOST_EXEMPT_POLICIES
    assert rate_limit_config.get_effective_limit('users:budget_choice') == (6, 60)


@pytest.fixture
def stored_api(api, monkeypatch):
    """Exercise HTTP serialization and the production choice transaction together."""
    client, route = api
    db = StrictFirestore()
    clock = SimpleNamespace(period='2026-10')
    monkeypatch.setenv('HELD_CONTENT_ENABLED', 'true')
    monkeypatch.setattr(route, 'budget_period', lambda: clock.period)
    monkeypatch.setattr(real_choices, 'budget_period', lambda: clock.period)
    monkeypatch.setattr(
        route.choices_db, 'get_choice', lambda uid, period: _get_choice(uid, period, firestore_client=db)
    )
    monkeypatch.setattr(
        route.choices_db,
        'set_choice',
        lambda uid, period, choice, dont_ask: _set_choice(uid, period, choice, dont_ask, firestore_client=db),
    )
    return client, route, db, clock


@pytest.mark.parametrize('choice', ['on_device', 'upgrade'])
def test_choice_round_trip_replay_and_funded_resume_with_real_store(stored_api, monkeypatch, choice):
    client, route, db, clock = stored_api
    headers = {'X-Omi-Held-Content': '1'}
    body = {'period': clock.period, 'choice': choice, 'dont_ask_again': True}
    for _ in range(2):
        written = client.put('/v1/users/budget-choice', headers=headers, json=body)
        assert written.status_code == 200 and written.json()['choice'] == body
    response = client.get('/v1/users/budget-choice', headers=headers).json()
    assert response == {
        'period': clock.period,
        'state': 'on_device' if choice == 'on_device' else 'held_pending_choice',
        'choice': body,
        'ask': False,
    }
    # Choice persistence cannot create processing consent, audio, or quota rows.
    assert set(db.rows) == {('users', 'synthetic-test-user', 'budget_choice', 'current')}
    assert [len(tx.sets) for tx in db.transactions] == [1, 0]
    monkeypatch.setattr(
        route,
        'resolve_transcription_allowance',
        lambda *args: SimpleNamespace(managed=True, reason='plan_within_allowance'),
    )
    response = client.get('/v1/users/budget-choice', headers=headers).json()
    assert response['state'] == 'managed' and response['ask'] is False
    assert response['choice'] == body


def test_new_month_expires_dont_ask_and_rejects_stale_replay(stored_api):
    client, route, db, clock = stored_api
    headers = {'X-Omi-Held-Content': '1'}
    body = {'period': clock.period, 'choice': 'on_device', 'dont_ask_again': True}
    assert client.put('/v1/users/budget-choice', headers=headers, json=body).status_code == 200
    clock.period = '2026-11'
    response = client.get('/v1/users/budget-choice', headers=headers).json()
    assert response == {'period': '2026-11', 'state': 'held_pending_choice', 'choice': None, 'ask': True}
    stale = client.put('/v1/users/budget-choice', headers=headers, json=body)
    assert stale.status_code == 409 and stale.json()['detail'] == 'budget_period_changed'
    body.update(period=clock.period, choice='upgrade', dont_ask_again=False)
    assert client.put('/v1/users/budget-choice', headers=headers, json=body).status_code == 200
    assert _get_choice('synthetic-test-user', clock.period, firestore_client=db) == body


@pytest.mark.parametrize('existing', [False, True])
def test_rollover_during_allowance_read_rejects_choice_without_mutation(stored_api, monkeypatch, existing):
    client, route, db, clock = stored_api
    headers = {'X-Omi-Held-Content': '1'}
    body = {'period': clock.period, 'choice': 'on_device'}
    if existing:
        assert client.put('/v1/users/budget-choice', headers=headers, json=body).status_code == 200
    before = dict(db.rows)

    def delayed_allowance(*args):
        clock.period = '2026-11'
        return SimpleNamespace(managed=False, reason='plan_allowance_exhausted')

    monkeypatch.setattr(route, 'resolve_transcription_allowance', delayed_allowance)
    response = client.put('/v1/users/budget-choice', headers=headers, json=body)
    assert response.status_code == 409 and response.json()['detail'] == 'budget_period_changed'
    assert db.rows == before
