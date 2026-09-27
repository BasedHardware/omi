"""A PATCH to an app must not write explicit nulls over fields the App model requires.

`PATCH /v1/apps/{app_id}` validates the payload with `AppUpdate` (all fields optional),
then persists `model_dump(exclude_unset=True)`. `exclude_unset` keeps a key the caller sent
as null — and the released clients serialize an omitted field as null, not absent (the Flutter
editor already sends `source_code_url: null` when empty, and `category` is a nullable local).
`App.name/category/author/description/image/capabilities` are non-nullable, so one such PATCH
made every `App(**doc)` read raise ValidationError (app detail, personas list, OAuth token,
notifications) with no un-poisoning path.

Fix: a null for one of those fields means "not sent" and is dropped before validation, while
genuinely optional fields (e.g. `source_code_url`) still pass a null through unchanged.

Seam: `routers.apps.update_app` is called directly with its collaborators patched — no HTTP
client, no Firestore.
"""

import json
import os

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)
os.environ.setdefault("OPENAI_API_KEY", "test-openai-key-not-real")
os.environ.setdefault("PINECONE_API_KEY", "test-pinecone-key-not-real")

import pytest

import routers.apps as apps_router

EXISTING = {
    'id': 'app-1',
    'uid': 'uid-1',
    'name': 'Existing name',
    'category': 'conversation-analysis',
    'author': 'Ada',
    'description': 'Existing description',
    'image': '',
    'capabilities': [],
    'approved': False,
    'private': False,
}

NULLED_REQUIRED = {
    'name': None,
    'category': None,
    'author': None,
    'description': None,
    'image': None,
    'capabilities': None,
}


@pytest.fixture
def calls(monkeypatch):
    recorded = {'updates': []}

    def _update_app_in_db(update):
        recorded['updates'].append(update)

    monkeypatch.setattr(apps_router, 'get_available_app_by_id', lambda app_id, uid: dict(EXISTING))
    monkeypatch.setattr(apps_router, 'update_app_in_db', _update_app_in_db)
    monkeypatch.setattr(apps_router, 'upsert_app_payment_link', lambda *args, **kwargs: None)
    monkeypatch.setattr(apps_router, 'invalidate_approved_apps_cache', lambda: None)
    monkeypatch.setattr(apps_router, 'delete_app_cache_by_id', lambda app_id: None)
    monkeypatch.setattr(apps_router, 'parse_form_json', lambda t, raw, field: json.loads(raw))
    return recorded


def _patch(payload):
    data = {'id': EXISTING['id'], **payload}
    return apps_router.update_app(EXISTING['id'], json.dumps(data), None, EXISTING['uid'])


def test_explicit_null_required_fields_are_not_written(calls):
    result = _patch({**NULLED_REQUIRED, 'source_code_url': None})

    assert result == {'status': 'ok'}
    written = calls['updates'][0]
    for field in NULLED_REQUIRED:
        assert field not in written
    # Genuinely optional fields keep their explicit null (not part of this fix's scope).
    assert 'source_code_url' in written and written['source_code_url'] is None


def test_real_required_fields_still_update(calls):
    result = _patch({'name': 'New name', 'category': 'conversation-analysis'})

    assert result == {'status': 'ok'}
    written = calls['updates'][0]
    assert written['name'] == 'New name'
    assert written['category'] == 'conversation-analysis'
