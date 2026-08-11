import importlib.abc
import importlib.machinery
import json
import sys
import types
from datetime import datetime, timezone
from unittest.mock import MagicMock, call

import pytest


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
    def __init__(self):
        self._created: set[str] = set()

    def find_spec(self, name, path=None, target=None):
        if _should_stub(name):
            return importlib.machinery.ModuleSpec(name, self, is_package=True)
        return None

    def create_module(self, spec):
        self._created.add(spec.name)
        return _AutoMockModule(spec.name)

    def exec_module(self, module):
        pass


_finder = _StubFinder()
sys.meta_path.insert(0, _finder)
try:
    from services.users import data_export  # noqa: E402
finally:
    # Remove the meta-path finder and clear *only* the modules that the
    # stub finder actually created. Broadly deleting every module matching
    # _STUB_PREFIXES (database, utils, …) would also evict real project
    # modules imported by other tests collected in the same pytest process.
    sys.meta_path.remove(_finder)
    for _name in list(_finder._created):
        sys.modules.pop(_name, None)
    # The imported service module itself was loaded against the MagicMock
    # stubs (its globals hold MagicMock objects for database, utils, etc.).
    # Pop it — along with its parent packages — so a later test that imports
    # the real service reloads it with production dependencies instead of
    # reusing this mock-backed copy.
    for _svc_name in ('services.users.data_export', 'services.users', 'services'):
        sys.modules.pop(_svc_name, None)


def test_iter_user_data_export_streams_all_top_level_sections(monkeypatch):
    now = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
    monkeypatch.setattr(data_export, 'get_user_profile', MagicMock(return_value={'created_at': now}))
    memory_service = MagicMock()
    memory_service.export_memories.return_value = [MagicMock(model_dump=MagicMock(return_value={'id': 'mem1'}))]
    monkeypatch.setattr(data_export, 'MemoryService', MagicMock(return_value=memory_service))
    monkeypatch.setattr(data_export, 'get_people', MagicMock(return_value=[{'id': 'person1'}]))
    monkeypatch.setattr(data_export, 'get_standalone_action_items', MagicMock(return_value=[{'id': 'task1'}]))
    monkeypatch.setattr(
        data_export,
        '_iter_user_subcollection',
        MagicMock(side_effect=lambda _uid, name: iter([{'id': f'{name}-1'}])),
    )
    monkeypatch.setattr(
        data_export,
        '_iter_user_nested_subcollection',
        MagicMock(
            side_effect=lambda _uid, parent, child: iter([{'id': f'{parent}-{child}-1', 'parent_id': f'{parent}-1'}])
        ),
    )
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
        'task_data': {
            **{name: [{'id': f'{name}-1'}] for name in data_export.TASK_EXPORT_COLLECTIONS},
            **{
                export_name: [{'id': f'{parent}-{child}-1', 'parent_id': f'{parent}-1'}]
                for export_name, parent, child in data_export.TASK_NESTED_EXPORT_COLLECTIONS
            },
        },
        'chat_messages': [{'id': 'msg1', 'created_at': '2026-01-02T03:04:05+00:00'}],
    }
    memory_service.export_memories.assert_called_once_with('uid1', include_archive=True)
    data_export.get_standalone_action_items.assert_called_once_with('uid1', limit=1000, offset=0)
    data_export.conversations_db.iter_all_conversations.assert_called_once_with('uid1', include_discarded=True)
    data_export.chat_db.iter_all_messages.assert_called_once_with('uid1')


def test_iter_user_data_export_uses_empty_profile_object(monkeypatch):
    monkeypatch.setattr(data_export, 'get_user_profile', MagicMock(return_value=None))
    monkeypatch.setattr(
        data_export, 'MemoryService', MagicMock(return_value=MagicMock(export_memories=MagicMock(return_value=[])))
    )
    monkeypatch.setattr(data_export, 'get_people', MagicMock(return_value=[]))
    monkeypatch.setattr(data_export, 'get_standalone_action_items', MagicMock(return_value=[]))
    monkeypatch.setattr(data_export, '_iter_user_subcollection', MagicMock(return_value=iter([])))
    monkeypatch.setattr(data_export.conversations_db, 'iter_all_conversations', MagicMock(return_value=iter([])))
    monkeypatch.setattr(data_export.chat_db, 'iter_all_messages', MagicMock(return_value=iter([])))

    payload = json.loads(''.join(data_export.iter_user_data_export('uid1')))

    assert payload['profile'] == {}


def test_iter_user_data_export_yields_before_heavy_reads(monkeypatch):
    get_profile = MagicMock(return_value={})
    monkeypatch.setattr(data_export, 'get_user_profile', get_profile)
    monkeypatch.setattr(
        data_export, 'MemoryService', MagicMock(return_value=MagicMock(export_memories=MagicMock(return_value=[])))
    )
    monkeypatch.setattr(data_export, 'get_people', MagicMock(return_value=[]))
    monkeypatch.setattr(data_export, 'get_standalone_action_items', MagicMock(return_value=[]))
    monkeypatch.setattr(data_export.conversations_db, 'iter_all_conversations', MagicMock(return_value=iter([])))
    monkeypatch.setattr(data_export.chat_db, 'iter_all_messages', MagicMock(return_value=iter([])))

    chunks = data_export.iter_user_data_export('uid1')

    assert next(chunks) == '{\n'
    get_profile.assert_not_called()


def test_json_default_raises_type_error_for_unsupported_types():
    with pytest.raises(TypeError, match="Type <class 'set'> not serializable"):
        data_export._json_default(set())


def test_nested_task_export_carries_owning_parent_id(monkeypatch):
    child = MagicMock(id='event-1')
    child.to_dict.return_value = {'kind': 'progress'}
    parent = MagicMock(id='workstream-1')
    parent.reference.collection.return_value.stream.return_value = [child]
    parent_collection = MagicMock()
    parent_collection.stream.return_value = [parent]
    user_document = MagicMock()
    user_document.collection.return_value = parent_collection
    users_collection = MagicMock()
    users_collection.document.return_value = user_document
    monkeypatch.setattr(data_export.database_client.db, 'collection', MagicMock(return_value=users_collection))

    records = list(data_export._iter_user_nested_subcollection('uid1', 'workstreams', 'events'))

    assert records == [{'kind': 'progress', 'id': 'event-1', 'parent_id': 'workstream-1'}]
    data_export.database_client.db.collection.assert_called_once_with('users')
    users_collection.document.assert_called_once_with('uid1')
    user_document.collection.assert_called_once_with('workstreams')
    parent.reference.collection.assert_called_once_with('events')


def test_iter_user_data_export_skips_none_conversations_and_formats_arrays(monkeypatch):
    monkeypatch.setattr(data_export, 'get_user_profile', MagicMock(return_value={}))
    monkeypatch.setattr(
        data_export, 'MemoryService', MagicMock(return_value=MagicMock(export_memories=MagicMock(return_value=[])))
    )
    monkeypatch.setattr(data_export, 'get_people', MagicMock(return_value=[]))
    monkeypatch.setattr(data_export, 'get_standalone_action_items', MagicMock(return_value=[]))
    monkeypatch.setattr(
        data_export.conversations_db,
        'iter_all_conversations',
        MagicMock(return_value=iter([{'id': 'conv1'}, None, {'id': 'conv2'}])),
    )
    monkeypatch.setattr(
        data_export.chat_db,
        'iter_all_messages',
        MagicMock(return_value=iter([{'id': 'msg1'}, {'id': 'msg2'}])),
    )

    body = ''.join(data_export.iter_user_data_export('uid1'))
    payload = json.loads(body)

    assert payload['conversations'] == [{'id': 'conv1'}, {'id': 'conv2'}]
    assert payload['chat_messages'] == [{'id': 'msg1'}, {'id': 'msg2'}]


def test_iter_user_data_export_paginates_complete_collections(monkeypatch):
    monkeypatch.setattr(data_export, 'get_user_profile', MagicMock(return_value={}))
    monkeypatch.setattr(data_export, 'get_people', MagicMock(return_value=[]))
    monkeypatch.setattr(data_export.conversations_db, 'iter_all_conversations', MagicMock(return_value=iter([])))
    monkeypatch.setattr(data_export.chat_db, 'iter_all_messages', MagicMock(return_value=iter([])))

    exported_memories = [MagicMock(model_dump=MagicMock(return_value={'id': f'mem-{i}'})) for i in range(1001)]
    action_item_pages = [
        [{'id': f'task-{i}'} for i in range(1000)],
        [{'id': 'task-1000'}],
    ]
    memory_service = MagicMock(export_memories=MagicMock(return_value=exported_memories))
    get_action_items = MagicMock(side_effect=action_item_pages)
    monkeypatch.setattr(data_export, 'MemoryService', MagicMock(return_value=memory_service))
    monkeypatch.setattr(data_export, 'get_standalone_action_items', get_action_items)

    payload = json.loads(''.join(data_export.iter_user_data_export('uid1')))

    assert len(payload['memories']) == 1001
    assert payload['memories'][-1] == {'id': 'mem-1000'}
    assert len(payload['action_items']) == 1001
    assert payload['action_items'][-1] == {'id': 'task-1000'}
    memory_service.export_memories.assert_called_once_with('uid1', include_archive=True)
    assert get_action_items.call_args_list == [
        call('uid1', limit=1000, offset=0),
        call('uid1', limit=1000, offset=1000),
    ]
