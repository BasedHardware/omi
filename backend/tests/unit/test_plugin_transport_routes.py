"""Real app HTTP metadata and real finalized-webhook composition with fake IO."""

import json
import os
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')

import routers.apps as apps
import utils.app_integrations as integrations
from utils.plugin_transport import PluginTransport

KEY = 'synthetic-transport-secret-at-least-32-bytes'
APP = 'signed-backup'
BASE = 'https://backup.example.invalid'


def app_record():
    return {
        'id': APP,
        'uid': 'author',
        'name': 'Backup',
        'category': 'productivity-and-organization',
        'author': 'Developer',
        'description': 'Conversation backup',
        'image': 'https://example.invalid/icon.png',
        'capabilities': ['external_integration'],
        'approved': True,
        'private': False,
        'external_integration': {
            'triggers_on': 'memory_creation',
            'webhook_url': BASE + '/conversation',
            'auth_steps': [{'name': 'Connect', 'url': BASE + '/setup/pcloud'}],
            'app_home_url': BASE + '/setup/pcloud',
            'setup_completed_url': BASE + '/setup-completed',
        },
    }


@pytest.fixture
def config(monkeypatch):
    monkeypatch.setenv('OMI_PLUGIN_TRANSPORT_JSON', json.dumps({APP: {'base_url': BASE, 'key': KEY}}))
    return PluginTransport(APP, BASE, KEY)


def test_app_http_response_receives_a_fresh_account_bound_launch(config, monkeypatch):
    record = app_record()
    monkeypatch.setattr(apps, 'get_available_app_by_id_with_reviews', lambda app_id, uid: record)
    monkeypatch.setattr(apps, 'get_is_user_paid_app', lambda *args: False)
    api = FastAPI()
    api.include_router(apps.router)
    api.dependency_overrides[apps.auth.get_current_user_uid] = lambda: 'user-a'
    with TestClient(api) as client:
        response = client.get('/v1/apps/' + APP)
    assert response.status_code == 200
    integration = response.json()['external_integration']
    for url, scope in (
        (integration['auth_steps'][0]['url'], 'setup'),
        (integration['app_home_url'], 'setup'),
        (integration['setup_completed_url'], 'status'),
    ):
        params = parse_qs(urlsplit(url).query)
        assert params['uid'] == ['user-a']
        assert config.decode(params['omi_token'][0], scope)['sub'] == 'user-a'
    assert 'omi_token' not in record['external_integration']['auth_steps'][0]['url']


@pytest.mark.asyncio
async def test_actual_finalized_fanout_signs_payload_and_retains_idempotency(config, monkeypatch):
    app = MagicMock()
    app.id, app.uid, app.enabled = APP, 'author', True
    app.external_integration.webhook_url = BASE + '/conversation'
    app.triggers_on_conversation_creation.return_value = True
    conversation = SimpleNamespace(
        id='conversation-a', discarded=False, is_locked=False, source=None, client_platform='ios'
    )
    monkeypatch.setattr(integrations, 'get_available_apps', lambda uid: [app])
    monkeypatch.setattr(integrations, 'is_app_webhook_disabled', lambda app_id: False)
    monkeypatch.setattr(
        integrations, 'conversation_to_dict', lambda value: {'id': value.id, 'structured': {'title': 'Synthetic'}}
    )
    monkeypatch.setattr(
        integrations,
        'safe_request_target',
        lambda url: (url, {'headers': {'Host': 'backup.example.invalid'}, 'extensions': {}}),
    )
    monkeypatch.setattr(integrations, 'get_webhook_circuit_breaker', lambda url: MagicMock())
    monkeypatch.setattr(integrations, 'record_app_webhook_success', lambda *args: None)
    monkeypatch.setattr(integrations, 'record_app_usage', lambda *args, **kwargs: None)
    client = SimpleNamespace(post=AsyncMock(return_value=SimpleNamespace(status_code=202, json=lambda: {})))
    monkeypatch.setattr(integrations, 'get_webhook_client', lambda: client)
    await integrations.trigger_external_integrations(
        'user-a', conversation, idempotency_key='durable-key', require_delivery=True
    )
    sent = client.post.call_args.kwargs
    assert sent['headers']['X-Omi-Idempotency-Key'] == 'durable-key'
    claims = config.decode(sent['headers']['X-Omi-Plugin-Authorization'], 'delivery')
    assert claims['sub'] == 'user-a' and claims['path'] == '/conversation'
    audio = config.decode(sent['json']['_omi_backup_audio_token'], 'audio')
    assert audio['sub'] == 'user-a' and audio['conversation_id'] == 'conversation-a'
