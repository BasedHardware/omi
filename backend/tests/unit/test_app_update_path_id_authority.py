"""PATCH /v1/apps/{app_id} must write only the app whose ownership it checked.

Ownership is verified on the path id. The multipart body carries its own `id` and
used to carry `uid`; neither may redirect the write to another app or move ownership.
"""

import json
import os

os.environ.setdefault("ENCRYPTION_SECRET", "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv")
os.environ.setdefault("OPENAI_API_KEY", "test-openai-key-not-real")
os.environ.setdefault("PINECONE_API_KEY", "test-pinecone-key-not-real")

from models.app import AppUpdate
from routers import apps

STORED = {
    'attacker-app': {
        'id': 'attacker-app',
        'uid': 'attacker',
        'name': 'Attacker App',
        'category': 'productivity',
        'author': 'Attacker',
        'description': 'd',
        'image': 'https://example.com/a.png',
        'capabilities': ['chat'],
        'approved': False,
        'private': True,
    },
    'victim-app': {
        'id': 'victim-app',
        'uid': 'victim',
        'name': 'Victim App',
        'category': 'productivity',
        'author': 'Victim',
        'description': 'd',
        'image': 'https://example.com/v.png',
        'capabilities': ['chat'],
        'approved': True,
        'private': False,
    },
}


def _patch(monkeypatch, path_id, uid, payload):
    writes = []
    payment_calls = []
    monkeypatch.setattr(apps, 'get_available_app_by_id', lambda app_id, _uid: dict(STORED[app_id]))
    monkeypatch.setattr(apps, 'update_app_in_db', lambda data: writes.append(dict(data)))
    monkeypatch.setattr(apps, 'upsert_app_payment_link', lambda *a, **k: payment_calls.append((a, k)))
    monkeypatch.setattr(apps, 'delete_app_cache_by_id', lambda *a, **k: None)
    monkeypatch.setattr(apps, 'invalidate_approved_apps_cache', lambda *a, **k: None)
    apps.update_app(path_id, app_data=json.dumps(payload), file=None, uid=uid)
    return writes, payment_calls


def test_body_id_cannot_redirect_write_to_another_app(monkeypatch):
    payload = {
        'id': 'victim-app',
        'name': 'Hijacked',
        'external_integration': {
            'triggers_on': 'transcript_processed',
            'webhook_url': 'https://attacker.example/collect',
        },
    }
    writes, _ = _patch(monkeypatch, 'attacker-app', 'attacker', payload)

    assert len(writes) == 1
    assert writes[0]['id'] == 'attacker-app'
    assert writes[0]['external_integration']['webhook_url'] == 'https://attacker.example/collect'


def test_body_without_id_targets_path_app(monkeypatch):
    writes, _ = _patch(monkeypatch, 'attacker-app', 'attacker', {'name': 'Renamed'})

    assert writes[0]['id'] == 'attacker-app'


def test_body_uid_cannot_change_ownership(monkeypatch):
    payload = {'id': 'attacker-app', 'uid': 'someone-else', 'name': 'Renamed'}
    writes, _ = _patch(monkeypatch, 'attacker-app', 'attacker', payload)

    assert 'uid' not in writes[0]


def test_payment_link_uses_path_id_and_authenticated_uid(monkeypatch):
    payload = {
        'id': 'victim-app',
        'uid': 'victim',
        'is_paid': True,
        'price': 5.0,
        'payment_plan': 'monthly_recurring',
    }
    _, payment_calls = _patch(monkeypatch, 'attacker-app', 'attacker', payload)

    assert len(payment_calls) == 1
    args, _ = payment_calls[0]
    assert args[0] == 'attacker-app'
    assert args[4] == 'attacker'


def test_app_update_model_has_no_uid_field():
    assert 'uid' not in AppUpdate.model_fields
    dumped = AppUpdate.model_validate({'id': 'a', 'uid': 'other'}).model_dump(exclude_unset=True)
    assert 'uid' not in dumped
