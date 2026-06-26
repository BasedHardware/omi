import importlib.abc
import importlib.machinery
import json
import sys
import types
from datetime import datetime, timezone
from unittest.mock import MagicMock


class _AutoMockModule(types.ModuleType):
    __path__ = []

    def __getattr__(self, name):
        if name.startswith('__') and name.endswith('__'):
            raise AttributeError(name)
        mock = MagicMock()
        setattr(self, name, mock)
        return mock


_STUB_PREFIXES = (
    'database',
    'firebase_admin',
    'google.cloud',
    'google.api_core',
    'pinecone',
    'typesense',
    'utils',
)


def _should_stub(name: str) -> bool:
    return any(name == prefix or name.startswith(prefix + '.') for prefix in _STUB_PREFIXES)


class _StubFinder(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    def find_spec(self, name, path=None, target=None):
        if _should_stub(name):
            return importlib.machinery.ModuleSpec(name, self, is_package=True)
        return None

    def create_module(self, spec):
        return _AutoMockModule(spec.name)

    def exec_module(self, module):
        pass


sys.meta_path.insert(0, _StubFinder())

from services.users import data_export  # noqa: E402


def test_iter_user_data_export_streams_all_top_level_sections(monkeypatch):
    now = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
    monkeypatch.setattr(data_export, 'get_user_profile', MagicMock(return_value={'created_at': now}))
    monkeypatch.setattr(data_export.memories_db, 'get_memories', MagicMock(return_value=[{'id': 'mem1'}]))
    monkeypatch.setattr(data_export, 'get_people', MagicMock(return_value=[{'id': 'person1'}]))
    monkeypatch.setattr(data_export, 'get_standalone_action_items', MagicMock(return_value=[{'id': 'task1'}]))
    monkeypatch.setattr(
        data_export.conversations_db,
        'iter_all_conversations',
        MagicMock(return_value=iter([{'id': 'conv1', 'is_locked': True}, {'id': 'conv2'}])),
    )
    monkeypatch.setattr(
        data_export.chat_db, 'iter_all_messages', MagicMock(return_value=iter([{'id': 'msg1', 'created_at': now}]))
    )

    body = ''.join(data_export.iter_user_data_export('uid1'))
    payload = json.loads(body)

    assert payload == {
        'profile': {'created_at': '2026-01-02T03:04:05+00:00'},
        'conversations': [{'id': 'conv1', 'is_locked': True}, {'id': 'conv2'}],
        'memories': [{'id': 'mem1'}],
        'people': [{'id': 'person1'}],
        'action_items': [{'id': 'task1'}],
        'chat_messages': [{'id': 'msg1', 'created_at': '2026-01-02T03:04:05+00:00'}],
    }
    data_export.memories_db.get_memories.assert_called_once_with('uid1', limit=10000, offset=0)
    data_export.get_standalone_action_items.assert_called_once_with('uid1', limit=10000, offset=0)
    data_export.conversations_db.iter_all_conversations.assert_called_once_with('uid1', include_discarded=True)
    data_export.chat_db.iter_all_messages.assert_called_once_with('uid1')


def test_iter_user_data_export_uses_empty_profile_object(monkeypatch):
    monkeypatch.setattr(data_export, 'get_user_profile', MagicMock(return_value=None))
    monkeypatch.setattr(data_export.memories_db, 'get_memories', MagicMock(return_value=[]))
    monkeypatch.setattr(data_export, 'get_people', MagicMock(return_value=[]))
    monkeypatch.setattr(data_export, 'get_standalone_action_items', MagicMock(return_value=[]))
    monkeypatch.setattr(data_export.conversations_db, 'iter_all_conversations', MagicMock(return_value=iter([])))
    monkeypatch.setattr(data_export.chat_db, 'iter_all_messages', MagicMock(return_value=iter([])))

    payload = json.loads(''.join(data_export.iter_user_data_export('uid1')))

    assert payload['profile'] == {}
