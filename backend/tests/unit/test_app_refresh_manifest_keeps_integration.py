import os

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)
os.environ.setdefault("OPENAI_API_KEY", "test-openai-key-not-real")
os.environ.setdefault("PINECONE_API_KEY", "test-pinecone-key-not-real")

import copy

from google.cloud.firestore_v1 import _helpers

import routers.apps as apps

_DOC_PATH = 'projects/p/databases/(default)/documents/plugins_data/app-1'


def _apply_firestore_update(stored: dict, field_updates: dict) -> dict:
    [write] = _helpers.pbs_for_update(_DOC_PATH, field_updates, None)
    values = _helpers.decode_dict(write.update.fields, None)
    result = copy.deepcopy(stored)
    for path in write.update_mask.field_paths:
        parts = path.split('.')
        value = values
        for part in parts:
            value = value[part]
        target = result
        for part in parts[:-1]:
            target = target.setdefault(part, {})
        target[parts[-1]] = value
    return result


def _stored_app() -> dict:
    return {
        'id': 'app-1',
        'uid': 'owner-1',
        'approved': False,
        'private': True,
        'external_integration': {
            'triggers_on': 'memory_creation',
            'webhook_url': 'https://example.com/webhook',
            'setup_completed_url': 'https://example.com/setup',
            'app_home_url': 'https://example.com',
            'chat_tools_manifest_url': 'https://example.com/.well-known/omi-tools.json',
            'chat_messages_enabled': False,
        },
    }


def _refresh(monkeypatch, manifest: dict) -> dict:
    stored = _stored_app()
    writes = []
    monkeypatch.setattr(apps, 'get_available_app_by_id', lambda app_id, uid: copy.deepcopy(stored))
    monkeypatch.setattr(apps, 'fetch_app_chat_tools_from_manifest', lambda url, **kwargs: manifest)
    monkeypatch.setattr(apps, 'update_app_in_db', writes.append)
    monkeypatch.setattr(apps, 'delete_app_cache_by_id', lambda app_id: None)
    monkeypatch.setattr(apps, 'invalidate_approved_apps_cache', lambda: None)

    apps.refresh_app_manifest('app-1', uid='owner-1')

    assert len(writes) == 1
    return _apply_firestore_update(stored, writes[0])


def test_refresh_manifest_keeps_webhook_and_manifest_url(monkeypatch):
    manifest = {
        'tools': [{'name': 'create_task', 'endpoint': '/tools/create_task'}],
        'chat_messages': {'enabled': True, 'target': 'main', 'notify': True},
    }

    after = _refresh(monkeypatch, manifest)

    integration = after['external_integration']
    assert integration.get('webhook_url') == 'https://example.com/webhook'
    assert integration.get('triggers_on') == 'memory_creation'
    assert integration.get('setup_completed_url') == 'https://example.com/setup'
    assert integration.get('chat_tools_manifest_url') == 'https://example.com/.well-known/omi-tools.json'
    assert integration.get('chat_messages_enabled') is True
    assert integration.get('chat_messages_target') == 'main'
    assert integration.get('chat_messages_notify') is True
    assert after['chat_tools'][0]['endpoint'] == 'https://example.com/tools/create_task'


def test_refresh_manifest_without_chat_messages_still_keeps_webhook(monkeypatch):
    after = _refresh(monkeypatch, {'tools': [{'name': 'lookup', 'endpoint': 'https://api.example.com/lookup'}]})

    integration = after['external_integration']
    assert integration.get('webhook_url') == 'https://example.com/webhook'
    assert integration.get('chat_tools_manifest_url') == 'https://example.com/.well-known/omi-tools.json'
    assert integration.get('chat_messages_enabled') is False
