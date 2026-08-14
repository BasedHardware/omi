import json
from pathlib import Path
from types import ModuleType

import pytest

from testing.import_isolation import load_module_fresh, stub_modules

_SCRIPT = Path(__file__).resolve().parents[2] / 'scripts' / 'web.py'


class _Document:
    def __init__(self, data):
        self._data = data

    def to_dict(self):
        return self._data


class _Collection:
    def __init__(self, documents):
        self._documents = documents

    def stream(self):
        if isinstance(self._documents, BaseException):
            raise self._documents
        return iter(_Document(document) for document in self._documents)


class _UserDocument:
    def __init__(self, messages):
        self._messages = messages

    def collection(self, name):
        assert name == 'messages'
        return _Collection(self._messages)


class _UsersCollection:
    def __init__(self, messages_by_uid):
        self._messages_by_uid = messages_by_uid

    def document(self, uid):
        return _UserDocument(self._messages_by_uid.get(uid, []))


class _Database:
    def __init__(self, plugin_documents=(), messages_by_uid=None):
        self._plugin_documents = plugin_documents
        self._messages_by_uid = messages_by_uid or {}

    def collection(self, name):
        if name == 'plugins_data':
            return _Collection(self._plugin_documents)
        assert name == 'users'
        return _UsersCollection(self._messages_by_uid)


def _load_web_module(plugin_documents=(), messages_by_uid=None) -> ModuleType:
    client = ModuleType('database._client')
    client.get_users_uid = lambda: []
    client.get_firestore_client = lambda: _Database(plugin_documents, messages_by_uid)
    client.db = _Database(plugin_documents, messages_by_uid)
    with stub_modules({'database._client': client}):
        return load_module_fresh('web_persona_export', str(_SCRIPT))


def test_map_plugin_data_by_persona_name_groups_plugin_documents_and_injects_user_uid(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / 'user_messages_with_bot_name.json').write_text(
        json.dumps(
            {
                'uid-1': [{'botName': 'Coach', 'pluginId': 'plugin-coach', 'text': 'first'}],
                'uid-2': [
                    {'botName': 'Coach', 'pluginId': 'plugin-coach', 'text': 'second'},
                    {'text': 'ignored'},
                ],
            }
        ),
        encoding='utf-8',
    )

    _load_web_module(
        plugin_documents=[
            {'id': 'plugin-coach', 'name': 'Coach', 'uid': 'owner-1', 'description': 'A coach'},
            {'id': 'plugin-other', 'name': 'Other', 'description': 'Not referenced'},
        ]
    ).map_plugin_data_by_persona_name()

    assert json.loads((tmp_path / 'plugin_data_by_persona_name.json').read_text(encoding='utf-8')) == {
        'plugin-coach': [
            {'id': 'plugin-coach', 'name': 'Coach', 'uid': 'owner-1', 'description': 'A coach', 'user_uid': 'uid-1'},
            {'id': 'plugin-coach', 'name': 'Coach', 'uid': 'owner-1', 'description': 'A coach', 'user_uid': 'uid-2'},
        ]
    }


def test_map_plugin_data_by_persona_name_redacts_oauth_tokens(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / 'user_messages_with_bot_name.json').write_text(
        json.dumps({'uid-1': [{'botName': 'Coach', 'pluginId': 'plugin-coach', 'text': 'first'}]}),
        encoding='utf-8',
    )

    _load_web_module(
        plugin_documents=[
            {
                'id': 'plugin-coach',
                'name': 'Coach',
                'uid': 'owner-1',
                'external_integration': {
                    'mcp_server_url': 'https://mcp.example.com',
                    'mcp_oauth_tokens': {
                        'client_id': 'cid',
                        'client_secret': 'secret',
                        'access_token': 'token',
                        'refresh_token': 'refresh',
                    },
                },
            }
        ]
    ).map_plugin_data_by_persona_name()

    output = json.loads((tmp_path / 'plugin_data_by_persona_name.json').read_text(encoding='utf-8'))
    assert output['plugin-coach'][0]['external_integration'] == {'mcp_server_url': 'https://mcp.example.com'}


def test_map_plugin_data_by_persona_name_removes_stale_output_when_input_missing(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / 'plugin_data_by_persona_name.json').write_text('{"stale": true}', encoding='utf-8')

    _load_web_module().map_plugin_data_by_persona_name()

    assert not (tmp_path / 'plugin_data_by_persona_name.json').exists()


def test_map_plugin_data_by_persona_name_preserves_bot_name_only_messages(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / 'user_messages_with_bot_name.json').write_text(
        json.dumps(
            {
                'uid-1': [{'botName': 'Coach', 'pluginId': 'plugin-coach', 'text': 'first'}],
                'uid-2': [{'botName': 'Legacy', 'text': 'old'}],
            }
        ),
        encoding='utf-8',
    )

    _load_web_module(
        plugin_documents=[
            {'id': 'plugin-coach', 'name': 'Coach', 'uid': 'owner-1', 'description': 'A coach'},
        ]
    ).map_plugin_data_by_persona_name()

    output = json.loads((tmp_path / 'plugin_data_by_persona_name.json').read_text(encoding='utf-8'))
    assert output['plugin-coach'][0]['user_uid'] == 'uid-1'
    assert output['_bot_name_only'] == [
        {'uid': 'uid-2', 'bot_name': 'Legacy', 'message': {'botName': 'Legacy', 'text': 'old'}}
    ]


def test_get_user_messages_scans_all_users_and_writes_results(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    module = _load_web_module(
        messages_by_uid={
            'uid-1': [{'botName': 'Coach', 'text': 'first'}],
            'uid-2': [{'text': 'ignored'}],
            'uid-3': [{'botName': 'Coach', 'text': 'third'}],
        }
    )
    module.get_users_uid = lambda: ['uid-1', 'uid-2', 'uid-3']

    assert module.get_user_messages_with_bot_name() == ['uid-1', 'uid-2', 'uid-3']
    assert json.loads((tmp_path / 'user_messages_with_bot_name.json').read_text(encoding='utf-8')) == {
        'uid-1': [{'botName': 'Coach', 'text': 'first'}],
        'uid-3': [{'botName': 'Coach', 'text': 'third'}],
    }


def test_get_user_messages_propagates_worker_failures(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    module = _load_web_module(messages_by_uid={'uid-1': RuntimeError('stream failed')})
    module.get_users_uid = lambda: ['uid-1']

    with pytest.raises(RuntimeError, match='stream failed'):
        module.get_user_messages_with_bot_name()

    assert not (tmp_path / 'user_messages_with_bot_name.json').exists()
