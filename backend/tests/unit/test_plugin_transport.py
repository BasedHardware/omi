"""Pure transport and real scoped-audio boundary tests, without cloud services."""

import copy
import json
from types import ModuleType, SimpleNamespace

import jwt
import pytest
from fastapi import HTTPException

from testing.import_isolation import load_module_fresh, stub_modules
from utils.plugin_transport import PluginTransport, authorize_app_setup, plugin_transport, strip_launch_credentials

KEY = 'synthetic-transport-secret-with-32-bytes'
APP = 'synthetic-pcloud'
TRANSPORT = PluginTransport(APP, 'https://backup.example.invalid', KEY)


@pytest.mark.parametrize('raw', ['', '{}'])
def test_unregistered_legacy_app_is_unchanged(monkeypatch, raw):
    monkeypatch.setenv('OMI_PLUGIN_TRANSPORT_JSON', raw)
    app = SimpleNamespace(id='legacy', external_integration=None)
    assert plugin_transport('legacy') is None
    assert authorize_app_setup(app, 'user') is app


@pytest.mark.parametrize(
    'raw',
    [
        '[]',
        '{bad',
        json.dumps({APP: {'base_url': 'http://localhost', 'key': KEY}}),
        json.dumps({APP: {'base_url': 'https://backup.example.invalid', 'key': 'short'}}),
    ],
)
def test_bad_registration_fails_closed(monkeypatch, raw):
    monkeypatch.setenv('OMI_PLUGIN_TRANSPORT_JSON', raw)
    with pytest.raises(ValueError):
        plugin_transport(APP)


def test_setup_urls_are_per_account_deep_copies(monkeypatch):
    monkeypatch.setenv('OMI_PLUGIN_TRANSPORT_JSON', json.dumps({APP: {'base_url': TRANSPORT.base_url, 'key': KEY}}))

    class App:
        id = APP
        external_integration = SimpleNamespace(
            auth_steps=[SimpleNamespace(url=TRANSPORT.base_url + '/setup/pcloud')],
            app_home_url=TRANSPORT.base_url + '/setup/pcloud',
            setup_completed_url=TRANSPORT.base_url + '/setup-completed',
        )

        def model_copy(self, deep):
            return copy.deepcopy(self)

    app = App()
    app.external_integration = copy.deepcopy(App.external_integration)
    a = authorize_app_setup(app, 'user-a')
    b = authorize_app_setup(app, 'user-b')
    assert 'omi_token=' not in app.external_integration.auth_steps[0].url
    assert a.external_integration.auth_steps[0].url != b.external_integration.auth_steps[0].url
    assert 'uid=user-a' in a.external_integration.app_home_url
    assert 'uid=user-b' in b.external_integration.setup_completed_url


@pytest.mark.parametrize(
    'url',
    [
        'https://evil.invalid/setup',
        'http://backup.example.invalid/setup',
        'https://backup.example.invalid.evil.invalid/setup',
        'https://user:secret@backup.example.invalid/setup',
        'https://backup.example.invalid/setup#secret',
    ],
)
def test_signed_setup_and_delivery_never_follow_untrusted_metadata(url):
    with pytest.raises(ValueError):
        TRANSPORT.setup_url(url, 'user')
    with pytest.raises(ValueError):
        TRANSPORT.delivery_headers('user', url, {})


def test_delivery_binds_body_path_and_principal():
    headers = TRANSPORT.delivery_headers(
        'user-a', TRANSPORT.base_url + '/conversation?uid=user-a', {'id': 'conversation'}
    )
    claims = TRANSPORT.decode(headers['X-Omi-Plugin-Authorization'], 'delivery')
    assert claims['sub'] == 'user-a' and claims['path'] == '/conversation'
    assert len(claims['sha256']) == 64
    with pytest.raises(ValueError):
        TRANSPORT.decode(headers['X-Omi-Plugin-Authorization'], 'setup')


def test_owner_edit_cannot_persist_a_launch_capability(monkeypatch):
    monkeypatch.setenv('OMI_PLUGIN_TRANSPORT_JSON', json.dumps({APP: {'base_url': TRANSPORT.base_url, 'key': KEY}}))
    metadata = {
        'auth_steps': [{'url': TRANSPORT.setup_url(TRANSPORT.base_url + '/setup/pcloud?theme=light', 'user')}],
        'app_home_url': TRANSPORT.setup_url(TRANSPORT.base_url + '/setup/pcloud', 'user'),
    }
    strip_launch_credentials(APP, metadata)
    assert metadata['auth_steps'][0]['url'] == TRANSPORT.base_url + '/setup/pcloud?theme=light'
    assert metadata['app_home_url'] == TRANSPORT.base_url + '/setup/pcloud'


@pytest.fixture
def audio_boundary():
    calls = []

    def module(name, **attrs):
        value = ModuleType(name)
        value.__dict__.update(attrs)
        return value

    dependencies = {
        'database.conversations': module(
            'database.conversations',
            get_conversation=lambda uid, cid: {'id': cid, 'audio_files': [{'id': 'audio-part'}]},
        ),
        'utils.apps': module(
            'utils.apps',
            is_user_app_enabled=lambda uid, app: True,
            get_available_app_by_id=lambda app, uid: {'id': app},
        ),
        'utils.other.endpoints': module(
            'utils.other.endpoints', enforce_account_deletion_http_access=lambda uid: calls.append(('deletion', uid))
        ),
        'utils.sync.playback': module(
            'utils.sync.playback',
            get_audio_signed_urls=lambda uid, cid, files, conversation: calls.append(('audio', uid, cid))
            or {'audio_files': []},
        ),
    }
    with stub_modules(dependencies):
        boundary = load_module_fresh('utils.plugin_backup_audio', 'utils/plugin_backup_audio.py')
        boundary.plugin_transport = lambda app: TRANSPORT if app == APP else None
        yield boundary, calls


def test_audio_read_is_owner_and_conversation_scoped(audio_boundary):
    boundary, calls = audio_boundary
    token = TRANSPORT.token('user-a', 'audio', conversation_id='conversation-a')
    assert boundary.backup_audio_manifest(APP, 'conversation-a', 'Bearer ' + token) == {'audio_files': []}
    assert calls == [('deletion', 'user-a'), ('audio', 'user-a', 'conversation-a')]
    with pytest.raises(HTTPException) as exc:
        boundary.backup_audio_manifest(APP, 'conversation-b', 'Bearer ' + token)
    assert exc.value.status_code == 401


def test_head_access_probe_does_not_trigger_audio_work(audio_boundary):
    boundary, calls = audio_boundary
    token = TRANSPORT.token('user-a', 'audio', conversation_id='conversation-a')
    assert boundary.backup_audio_manifest(APP, 'conversation-a', 'Bearer ' + token, include_audio=False) == {
        'authorized': True
    }
    assert calls == [('deletion', 'user-a')]


@pytest.mark.parametrize('status', ['disabled', 'discarded', 'locked', 'deleted', 'missing'])
def test_audio_rechecks_current_access_not_only_grant(audio_boundary, status):
    boundary, calls = audio_boundary
    if status == 'disabled':
        boundary.is_user_app_enabled = lambda *args: False
    elif status == 'missing':
        boundary.get_conversation = lambda *args: None
    else:
        key = 'is_locked' if status == 'locked' else status
        boundary.get_conversation = lambda *args: {key: True}
    token = TRANSPORT.token('user', 'audio', conversation_id='conversation')
    with pytest.raises(HTTPException) as exc:
        boundary.backup_audio_manifest(APP, 'conversation', 'Bearer ' + token)
    assert exc.value.status_code in (403, 404)
    assert not any(call[0] == 'audio' for call in calls)
