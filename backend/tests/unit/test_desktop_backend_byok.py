"""Regression test for the desktop backend's BYOK header plumbing (issue #20602).

desktop_backend.py builds a separate FastAPI app from main.py and must install
BYOKMiddleware itself for the contextvar BYOK readers (get_byok_key, etc.) to
see the X-BYOK-* headers desktop chat sends. Without it, validated BYOK keys
are silently ignored on every desktop chat request.
"""

import hashlib
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from cachetools import TTLCache
from fastapi.testclient import TestClient

import desktop_backend
from database import users as users_db
from models.users import PlanType
from routers import desktop_chat
from tests.unit.test_desktop_backend_cors import _test_client
from utils import byok, subscription
from utils.byok import get_byok_key
from utils.other import endpoints


def test_desktop_backend_installs_byok_middleware(monkeypatch):
    monkeypatch.delenv('CORS_ALLOWED_ORIGINS', raising=False)
    app = desktop_backend._build_app()

    captured = {}

    @app.get('/__test_byok_probe')
    def _probe():
        captured['openai'] = get_byok_key('openai')
        return {'ok': True}

    client = _test_client(monkeypatch, app)
    with client:
        with_header = client.get('/__test_byok_probe', headers={'X-BYOK-OpenAI': 'probe-key'})
        captured_with_header = dict(captured)
        without_header = client.get('/__test_byok_probe')
        captured_without_header = dict(captured)

    assert with_header.status_code == 200
    assert captured_with_header['openai'] == 'probe-key'
    assert without_header.status_code == 200
    assert captured_without_header['openai'] is None


@pytest.fixture
def authenticated_anthropic_chat(monkeypatch):
    """Run the real desktop app, HTTP auth, enrollment, quota, and route selection.

    Only external boundaries use fakes: Firebase token verification via the
    supported local ADMIN_KEY contract, persisted enrollment/quota state, and
    the Anthropic SDK transport. No provider or customer account is contacted.
    """
    uid = 'desktop-anthropic-byok-fixture'
    api_key = 'sk-ant-synthetic-enrolled-key-not-real'
    admin_key = 'synthetic-admin-key-for-byok-test'
    state = {
        'active': True,
        'last_seen_at': datetime.now(timezone.utc),
        'fingerprints': {'anthropic': hashlib.sha256(api_key.encode()).hexdigest()},
    }
    calls = {'clients': [], 'messages': [], 'quota_reads': [], 'cost_exclusions': [], 'quota_questions': []}
    monkeypatch.setenv('ADMIN_KEY', admin_key)
    monkeypatch.setenv('ADMIN_KEY_AUTH_ENABLED', 'true')
    monkeypatch.setattr(byok, '_byok_state_cache', TTLCache(maxsize=1, ttl=30))
    monkeypatch.setattr(users_db, 'get_byok_state', lambda *_args, **_kwargs: state)
    monkeypatch.setattr(users_db, 'is_byok_active', lambda *_args, **_kwargs: True)
    monkeypatch.setattr(endpoints, 'enforce_account_deletion_http_access', lambda _uid: None)
    monkeypatch.setattr(endpoints, '_enforce_cutover_http_if_request', lambda *_args: None)
    monkeypatch.setattr(endpoints, 'record_user_platform', lambda *_args: None)
    monkeypatch.setattr(endpoints, 'record_client_device', lambda *_args, **_kwargs: None)
    monkeypatch.setattr(subscription, 'is_trial_paywalled', lambda *_args, **_kwargs: False)
    monkeypatch.setattr(subscription, 'get_customer_firestore_client', lambda: None)

    def exhausted_managed_quota(*_args, **_kwargs):
        calls['quota_reads'].append(get_byok_key('anthropic'))
        return {
            'allowed': False,
            'plan': PlanType.basic,
            'unit': 'questions',
            'used': 30,
            'limit': 30,
            'reset_at': '2030-01-01T00:00:00Z',
        }

    monkeypatch.setattr(subscription, 'get_chat_quota_snapshot', exhausted_managed_quota)
    monkeypatch.setattr(desktop_chat, 'llm_stub_enabled', lambda: False)
    monkeypatch.setattr(desktop_chat, 'should_route_chat_agent_through_gateway', lambda: True)
    monkeypatch.setattr(desktop_chat, 'get_customer_firestore_client', lambda: None)
    monkeypatch.setattr(
        desktop_chat.llm_usage_db,
        'record_llm_cost_exclusion',
        lambda *_args, **kwargs: calls['cost_exclusions'].append(kwargs),
    )
    monkeypatch.setattr(
        desktop_chat.llm_usage_db,
        'record_chat_quota_question',
        lambda *_args, **_kwargs: calls['quota_questions'].append(uid),
    )
    message = SimpleNamespace(
        id='msg_synthetic_byok',
        content=[SimpleNamespace(type='text', text='Synthetic BYOK response')],
        stop_reason='end_turn',
        usage=SimpleNamespace(
            input_tokens=1, output_tokens=1, cache_read_input_tokens=0, cache_creation_input_tokens=0
        ),
    )

    class MessageStream:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def __aiter__(self):
            yield SimpleNamespace(type='message_start', message=message)
            yield SimpleNamespace(
                type='content_block_delta', delta=SimpleNamespace(type='text_delta', text='Synthetic BYOK response')
            )

        async def get_final_message(self):
            return message

    class Messages:
        async def create(self, **payload):
            calls['messages'].append(payload)
            return message

        def stream(self, **payload):
            calls['messages'].append(payload)
            return MessageStream()

    def customer_client(*, byok_api_key):
        calls['clients'].append(byok_api_key)
        return SimpleNamespace(messages=Messages())

    def managed_transport_must_not_run(*_args, **_kwargs):
        raise AssertionError('Enrolled Anthropic BYOK must not call managed transport or rate metering')

    monkeypatch.setattr(desktop_chat, 'get_direct_anthropic_client', customer_client)
    monkeypatch.setattr(desktop_chat, 'get_llm_gateway_client', managed_transport_must_not_run)
    monkeypatch.setattr(desktop_chat.redis_db, 'check_rate_limit', managed_transport_must_not_run)
    app = desktop_backend._build_app()
    headers = {
        'Authorization': f'Bearer {admin_key}{uid}',
        'X-BYOK-Anthropic': api_key,
        'X-App-Platform': 'desktop',
        'X-App-Version': '0.12.447+12447',
        'X-Omi-Chat-Contract-Version': '1',
    }
    return app, headers, calls


@pytest.mark.parametrize('streaming', [False, True])
def test_authenticated_enrolled_anthropic_uses_customer_key_with_exhausted_managed_quota(
    authenticated_anthropic_chat, streaming
):
    app, headers, calls = authenticated_anthropic_chat
    client = TestClient(app)
    body = {'model': 'omi-sonnet', 'messages': [{'role': 'user', 'content': 'hello'}], 'stream': streaming}

    response = client.post('/v2/chat/completions', headers=headers, json=body)

    assert response.status_code == 200
    assert 'Synthetic BYOK response' in response.text
    assert calls['clients'] == [headers['X-BYOK-Anthropic']]
    assert calls['messages'][0]['model'] == 'claude-sonnet-4-6'
    assert calls['quota_reads'] == []
    assert calls['quota_questions'] == ['desktop-anthropic-byok-fixture']
    assert [entry['cost_exclusion'] for entry in calls['cost_exclusions']] == ['byok_provider_cost']

    without_key = {name: value for name, value in headers.items() if name != 'X-BYOK-Anthropic'}
    next_response = client.post('/v2/chat/completions', headers=without_key, json=body)
    assert next_response.status_code == 402
    assert calls['quota_reads'] == [None]
    assert len(calls['clients']) == 1


def test_missing_desktop_byok_middleware_reproduces_managed_quota_failure(authenticated_anthropic_chat):
    app, headers, calls = authenticated_anthropic_chat
    # Reproduce the desktop serving app before #20931 without modifying source.
    app.user_middleware = [item for item in app.user_middleware if item.cls is not byok.BYOKMiddleware]
    response = TestClient(app).post(
        '/v2/chat/completions',
        headers=headers,
        json={'model': 'omi-sonnet', 'messages': [{'role': 'user', 'content': 'hello'}]},
    )

    assert response.status_code == 402
    assert response.json()['detail']['error'] == 'quota_exceeded'
    assert calls['quota_reads'] == [None]
    assert calls['clients'] == []
    assert calls['messages'] == []
    assert calls['cost_exclusions'] == []


def test_authenticated_anthropic_fingerprint_mismatch_never_calls_provider(authenticated_anthropic_chat):
    app, headers, calls = authenticated_anthropic_chat
    headers['X-BYOK-Anthropic'] = 'sk-ant-unenrolled-synthetic-key-not-real'
    response = TestClient(app).post(
        '/v2/chat/completions',
        headers=headers,
        json={'model': 'omi-sonnet', 'messages': [{'role': 'user', 'content': 'hello'}]},
    )

    assert response.status_code == 403
    assert response.json()['detail'] == 'BYOK key fingerprint mismatch for provider: anthropic'
    assert calls['quota_reads'] == []
    assert calls['clients'] == []
