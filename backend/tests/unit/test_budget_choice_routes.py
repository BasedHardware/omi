"""HTTP contract with no real identity, database, subscription, or provider access."""

from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from testing.import_isolation import load_module_fresh, stub_modules


@pytest.fixture(scope='module')
def route_module():
    subscription = ModuleType('utils.subscription')
    subscription.resolve_transcription_allowance = lambda uid: SimpleNamespace(
        managed=False, reason='plan_allowance_exhausted'
    )
    auth = ModuleType('utils.other.endpoints')
    auth.get_current_user_uid_no_byok_validation = lambda: 'synthetic-test-user'
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
    monkeypatch.setattr(route, 'budget_period', lambda: '2026-10')
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
    monkeypatch.setattr(route, 'resolve_transcription_allowance', lambda uid: pytest.fail('must not read'))
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
    monkeypatch.setattr(route.choices_db, 'get_choice', lambda uid, period: {'choice': 'upgrade'})
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
        lambda uid: SimpleNamespace(managed=True, reason='plan_within_allowance'),
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
