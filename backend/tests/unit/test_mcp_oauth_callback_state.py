"""The MCP OAuth callback must trust only a state this server issued.

`mcp_oauth_callback` is unauthenticated and used to parse `app_id:uid:nonce` straight
out of the client-supplied `state` — no signature, no server-side record — and then
called `enable_app(uid, app_id)` with whatever uid that string named. A caller could
therefore forge a state for another account and silently install their own MCP app on
it. The app-key routes in `routers/integration.py` authorize reads with
`app_id in get_enabled_apps(uid)`, so the forged enablement hands the attacker's app
key the victim's conversations, memories and tasks.

The fix stores the app_id/uid pair server-side under an opaque single-use token
(GETDEL on consume, like the integration OAuth flow) and re-checks the app owner at
the callback, mirroring `refresh_mcp_tools` directly below it. These tests cover the
state helpers and the callback's rejection paths; no live services.
"""

import asyncio
import json
import os

os.environ.setdefault('OPENAI_API_KEY', 'sk-test-not-real')
os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')

from routers import apps as apps_router  # noqa: E402
from utils import mcp_client  # noqa: E402


class _FakeRedis:
    """Minimal stand-in for redis_db.r covering the state helpers' two calls."""

    def __init__(self):
        self.store = {}
        self.setex_calls = []

    def setex(self, key, ttl, value):
        self.setex_calls.append((key, ttl, value))
        self.store[key] = value

    def getdel(self, key):
        return self.store.pop(key, None)


class _ExchangeReached(Exception):
    """Sentinel raised from the exchange stub to prove validation passed."""


def _patch_redis(monkeypatch):
    fake = _FakeRedis()
    monkeypatch.setattr(mcp_client.redis_db, 'r', fake)
    return fake


def _patch_route(monkeypatch, app_data):
    async def _passthrough(_executor, fn, *args, **kwargs):
        return fn(*args, **kwargs)

    reached = []

    async def _exchange(*_args, **_kwargs):
        reached.append(True)
        raise _ExchangeReached()

    monkeypatch.setattr(apps_router, 'run_blocking', _passthrough)
    monkeypatch.setattr(apps_router, 'get_app_by_id_db', lambda _app_id: app_data)
    monkeypatch.setattr(apps_router, 'exchange_oauth_code', _exchange)
    return reached


def test_state_round_trip_is_single_use(monkeypatch):
    fake = _patch_redis(monkeypatch)
    state = mcp_client.create_mcp_oauth_state('app-1', 'uid-1')

    assert fake.setex_calls == [
        (
            f'mcp_oauth_state:{state}',
            mcp_client.MCP_OAUTH_STATE_EXPIRY_SECONDS,
            json.dumps({'app_id': 'app-1', 'uid': 'uid-1'}),
        )
    ]
    assert mcp_client.consume_mcp_oauth_state(state) == ('app-1', 'uid-1')
    # Single-use: a replayed callback finds the token already consumed.
    assert mcp_client.consume_mcp_oauth_state(state) is None


def test_forged_legacy_state_is_rejected(monkeypatch):
    _patch_redis(monkeypatch)
    # The old format a caller fully controls; it was previously parsed and trusted.
    assert mcp_client.consume_mcp_oauth_state('attacker-app:victim-uid:nonce') is None


def test_empty_and_malformed_states_are_rejected(monkeypatch):
    fake = _patch_redis(monkeypatch)
    assert mcp_client.consume_mcp_oauth_state('') is None

    fake.store['mcp_oauth_state:not-json'] = b'not json'
    fake.store['mcp_oauth_state:not-a-dict'] = json.dumps(['app-1', 'uid-1'])
    fake.store['mcp_oauth_state:missing-uid'] = json.dumps({'app_id': 'app-1'})
    fake.store['mcp_oauth_state:empty-uid'] = json.dumps({'app_id': 'app-1', 'uid': ''})
    fake.store['mcp_oauth_state:non-string'] = json.dumps({'app_id': 'app-1', 'uid': 7})
    for state in ('not-json', 'not-a-dict', 'missing-uid', 'empty-uid', 'non-string'):
        assert mcp_client.consume_mcp_oauth_state(state) is None


def test_callback_rejects_forged_state_before_any_side_effect(monkeypatch):
    _patch_redis(monkeypatch)
    reached = _patch_route(monkeypatch, app_data={'uid': 'victim-uid'})

    response = asyncio.run(apps_router.mcp_oauth_callback(code='attacker-code', state='attacker-app:victim-uid:nonce'))

    assert response.status_code == 400
    assert reached == []


def test_callback_rejects_state_whose_owner_does_not_match(monkeypatch):
    fake = _patch_redis(monkeypatch)
    state = mcp_client.create_mcp_oauth_state('app-1', 'uid-1')
    reached = _patch_route(monkeypatch, app_data={'uid': 'someone-else'})

    response = asyncio.run(apps_router.mcp_oauth_callback(code='code-1', state=state))

    assert response.status_code == 403
    assert reached == []
    # Consumption happens before the owner check, so a mismatch burns the state:
    # single-use means any callback attempt, valid or not, spends the token.
    assert f'mcp_oauth_state:{state}' not in fake.store


def test_callback_reaches_exchange_when_state_and_owner_match(monkeypatch):
    _patch_redis(monkeypatch)
    state = mcp_client.create_mcp_oauth_state('app-1', 'uid-1')
    app_data = {
        'uid': 'uid-1',
        'external_integration': {
            'mcp_server_url': 'https://mcp.example.com',
            'mcp_oauth_tokens': {
                'token_endpoint': 'https://mcp.example.com/token',
                'client_id': 'client-1',
            },
        },
    }
    reached = _patch_route(monkeypatch, app_data=app_data)

    response = asyncio.run(apps_router.mcp_oauth_callback(code='code-1', state=state))

    # The stub raises, so the route reports the exchange failure: proof the state and
    # owner checks passed and the flow proceeded to the provider call.
    assert reached == [True]
    assert response.status_code == 502
