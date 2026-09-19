"""Regression: POST /v1/apps/{app_id}/refresh-manifest must not wipe external_integration.

`refresh_app_manifest` used to build a throwaway dict holding only the three chat_messages_* keys
and write it as `update_dict['external_integration']`. `update_app_in_db` calls Firestore
`update()`, where a top-level map value replaces the whole field, so a single tap on "Refresh
Manifest" deleted the app's `webhook_url`, `triggers_on`, `actions`, `app_home_url`,
`setup_completed_url`, `auth_steps` and even `chat_tools_manifest_url`. Webhook delivery skips apps
without a `webhook_url` (utils/app_integrations.py), so the app silently stopped receiving events
for every user who installed it, and the next refresh failed with 400 "App does not have a chat
tools manifest URL".

Fix: merge the refreshed chat_messages_* settings into the stored integration and write the full
merged map.

Seam: `routers.apps.refresh_app_manifest` is called directly with its collaborators monkeypatched,
and the captured write is applied through a local stand-in for the Firestore `update()` semantics
(top-level key replaces the stored value) so the data loss the user reported is reproduced here.
"""

import copy
import os

os.environ.setdefault('OPENAI_API_KEY', 'test-openai-key-not-real')
os.environ.setdefault(
    'ENCRYPTION_SECRET',
    'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv',
)

import routers.apps as apps_mod  # noqa: E402

APP_ID = 'app-1'
UID = 'uid-1'
MANIFEST_URL = 'https://app.example.com/.well-known/omi-tools.json'
WEBHOOK_URL = 'https://app.example.com/webhook'
SETUP_COMPLETED_URL = 'https://app.example.com/setup-completed'

STORED_INTEGRATION = {
    'chat_tools_manifest_url': MANIFEST_URL,
    'app_home_url': 'https://app.example.com',
    'webhook_url': WEBHOOK_URL,
    'triggers_on': 'transcript_processed',
    'setup_completed_url': SETUP_COMPLETED_URL,
    'auth_steps': [{'name': 'connect', 'url': 'https://app.example.com/oauth'}],
    'actions': [{'id': 'do_thing', 'name': 'Do thing'}],
    'chat_messages_enabled': True,
    'chat_messages_target': 'app',
    'chat_messages_notify': True,
}


def _stored_app():
    return {
        'id': APP_ID,
        'uid': UID,
        'approved': False,
        'private': True,
        'external_integration': copy.deepcopy(STORED_INTEGRATION),
    }


def _apply_firestore_update(stored, update_payload):
    """Stand-in for Firestore db.collection(...).document(...).update(payload).

    A top-level key in the payload REPLACES the stored value; a map value therefore replaces the
    whole field. This is what turned a partial external_integration into data loss.
    """
    for key, value in update_payload.items():
        stored[key] = value
    return stored


def _capture_refresh(monkeypatch, manifest_result, stored_app):
    """Run the handler with the manifest stubbed and return (result, stored doc after the write)."""
    stored = dict(stored_app)
    writes = []

    monkeypatch.setattr(apps_mod, 'get_available_app_by_id', lambda app_id, uid: stored_app)
    monkeypatch.setattr(
        apps_mod,
        'fetch_app_chat_tools_from_manifest',
        # kwargs so the call shape (url, force_refresh=True) keeps working.
        lambda url, **kwargs: manifest_result,
    )
    monkeypatch.setattr(apps_mod, 'update_app_in_db', lambda payload: (writes.append(payload), _apply_firestore_update(stored, payload)))
    monkeypatch.setattr(apps_mod, 'invalidate_approved_apps_cache', lambda: None)
    monkeypatch.setattr(apps_mod, 'delete_app_cache_by_id', lambda app_id: None)

    result = apps_mod.refresh_app_manifest(app_id=APP_ID, uid=UID)

    assert len(writes) == 1, 'the refresh must issue exactly one app write'
    return result, writes[0], stored


def test_refresh_manifest_preserves_webhook_and_other_integration_fields(monkeypatch):
    manifest = {
        'tools': [{'name': 'do_thing', 'endpoint': '/api/action'}],
        'chat_messages': {'enabled': False, 'target': 'user', 'notify': False},
    }
    result, payload, stored = _capture_refresh(monkeypatch, manifest, _stored_app())

    integration = stored['external_integration']

    # The webhook survives: this is the field whose loss silently disconnected the app.
    assert integration.get('webhook_url') == WEBHOOK_URL
    assert integration.get('triggers_on') == 'transcript_processed'
    assert integration.get('setup_completed_url') == SETUP_COMPLETED_URL
    assert integration.get('app_home_url') == 'https://app.example.com'
    # chat_tools_manifest_url must survive too, or the next refresh 400s.
    assert integration.get('chat_tools_manifest_url') == MANIFEST_URL
    assert isinstance(integration.get('auth_steps'), list)
    assert isinstance(integration.get('actions'), list)

    # The refreshed chat_messages settings are applied on top.
    assert integration['chat_messages_enabled'] is False
    assert integration['chat_messages_target'] == 'user'
    assert integration['chat_messages_notify'] is False

    # The tools themselves are still refreshed.
    assert stored['chat_tools'] == [{'name': 'do_thing', 'endpoint': 'https://app.example.com/api/action'}]
    assert result == {'status': 'ok', 'tools_count': 1}

    # One write, one external_integration entry, and no key dropped or invented.
    assert list(payload.keys()).count('external_integration') == 1
    assert set(payload['external_integration']) == set(STORED_INTEGRATION)


def test_refresh_manifest_without_chat_messages_keeps_the_rest_of_the_integration(monkeypatch):
    # A manifest with no chat_messages block resets those three fields to their defaults; it must
    # still not touch anything else.
    manifest = {'tools': [{'name': 'do_thing', 'endpoint': 'https://app.example.com/api/action'}]}
    _result, _payload, stored = _capture_refresh(monkeypatch, manifest, _stored_app())

    integration = stored['external_integration']

    assert integration.get('webhook_url') == WEBHOOK_URL
    assert integration.get('chat_tools_manifest_url') == MANIFEST_URL
    assert integration['chat_messages_enabled'] is False
    assert integration['chat_messages_target'] == 'app'
    assert integration['chat_messages_notify'] is False


def test_refresh_manifest_does_not_mutate_the_stored_integration_object(monkeypatch):
    # The merge must be written into a copy: the dict read from the app document (and any caller
    # holding it) must not be altered in place before the write.
    app = _stored_app()
    manifest = {'tools': [], 'chat_messages': {'enabled': False, 'target': 'user', 'notify': False}}

    monkeypatch.setattr(apps_mod, 'get_available_app_by_id', lambda app_id, uid: app)
    monkeypatch.setattr(apps_mod, 'fetch_app_chat_tools_from_manifest', lambda url, **kwargs: manifest)
    monkeypatch.setattr(apps_mod, 'update_app_in_db', lambda payload: None)
    monkeypatch.setattr(apps_mod, 'invalidate_approved_apps_cache', lambda: None)
    monkeypatch.setattr(apps_mod, 'delete_app_cache_by_id', lambda app_id: None)

    apps_mod.refresh_app_manifest(app_id=APP_ID, uid=UID)

    assert app['external_integration'] == STORED_INTEGRATION
