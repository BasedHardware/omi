"""Execute deletion entrypoints against a content-free Firestore fake.

The router graph is import-heavy; compile its actual function body with isolated
collaborators rather than importing network clients or asserting source strings.
"""

import ast
import asyncio
from pathlib import Path
from types import SimpleNamespace, MethodType
from unittest.mock import MagicMock, AsyncMock

from fastapi import HTTPException
import pytest

from database import conversation_tombstones as tombstones
from google.api_core.exceptions import AlreadyExists
from testing.import_isolation import stub_modules, AutoMockModule

ROOT = Path(__file__).resolve().parents[2]


class Store:
    def __init__(self):
        self.rows = {}

    def collection(self, name):
        return Ref(self, name)


class Ref:
    def __init__(self, store, path):
        self.store, self.path = store, path
        self.id = path.rsplit('/', 1)[-1]

    def collection(self, name):
        return Ref(self.store, f'{self.path}/{name}')

    document = collection

    def get(self):
        data = self.store.rows.get(self.path)
        return SimpleNamespace(exists=data is not None, to_dict=lambda: data)

    def create(self, data):
        if self.path in self.store.rows:
            raise AlreadyExists('exists')
        self.store.rows[self.path] = data

    def delete(self):
        self.store.rows.pop(self.path, None)

    def collections(self):
        prefix = self.path + '/'
        names = {p[len(prefix) :].split('/')[0] for p in self.store.rows if p.startswith(prefix)}
        return [self.collection(n) for n in names]


def function(path, name, namespace):
    node = next(
        n
        for n in ast.walk(ast.parse((ROOT / path).read_text()))
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name
    )
    node.decorator_list = []
    node.returns = None
    node.args.defaults = []
    for arg in node.args.args + node.args.kwonlyargs:
        arg.annotation = None
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(path), 'exec'), namespace)
    return namespace[name]


@pytest.fixture
def store(monkeypatch):
    store = Store()
    monkeypatch.setattr(tombstones, 'db', store)
    store.rows['users/u/conversations/c'] = {
        'created_at': 'original-time',
        'external_data': {'from_segments_client_session_id': 'session', 'calendar_event': 'private'},
        'transcript_segments': [{'text': 'private'}],
        'structured': {'title': 'private'},
    }
    # The route's notification collaborator is outside this storage/delete contract.
    with stub_modules({'utils.notifications': AutoMockModule('utils.notifications')}):
        yield store


def test_tombstone_contains_only_identity_and_point_lookup_is_owner_scoped(store):
    tombstones.record_deletion('u', 'c')
    row = store.rows['users/u/deleted_conversations/c']
    assert set(row) == {'conversation_id', 'deleted_at', 'client_session_id', 'created_at'}
    assert row['client_session_id'] == 'session'
    assert tombstones.is_deleted('u', 'c')
    assert not tombstones.is_deleted('other-user', 'c')


def test_non_cascade_delete_purges_prompt_evidence_after_intent_without_purging_primary_audio(store):
    calls = []

    def purge(uid, cid):
        calls.append(('prompt', tombstones.is_deleted(uid, cid)))

    def hard_delete(uid, cid):
        calls.append(('parent', tombstones.is_deleted(uid, cid)))
        store.rows.pop(f'users/{uid}/conversations/{cid}')

    audio = MagicMock()
    namespace = {
        'logger': MagicMock(),
        'conversation_tombstones': tombstones,
        'delete_owner_prompt_embedding_cache': purge,
        'delete_conversation_screen_frames': MagicMock(),
        'delete_conversation_and_frame_evidence': hard_delete,
        'delete_conversation_audio_files': audio,
        'delete_vector': MagicMock(),
        'delete_transcript_chunk_vectors': MagicMock(),
        'record_product_event': MagicMock(),
    }
    delete = function('routers/conversations.py', 'delete_conversation', namespace)
    assert delete('c', MagicMock(), False, None, 'u') == {'status': 'Ok'}
    assert calls == [('prompt', True), ('parent', True)]
    audio.assert_not_called()


@pytest.mark.parametrize('failure', ['retraction', 'cleanup', None])
def test_user_delete_records_intent_before_retraction_and_cleanup(store, failure):
    class Conflict(Exception):
        pass

    def retract(*args):
        assert tombstones.is_deleted('u', 'c')
        if failure == 'retraction':
            raise Conflict()

    def cleanup(*args):
        assert tombstones.is_deleted('u', 'c')
        if failure == 'cleanup':
            raise RuntimeError('cleanup failed')

    def hard_delete(*args):
        assert tombstones.is_deleted('u', 'c')
        store.rows.pop('users/u/conversations/c')

    namespace = {
        'logger': MagicMock(),
        'conversation_tombstones': tombstones,
        'db_client_module': SimpleNamespace(db=store),
        'MemoryService': lambda **kw: SimpleNamespace(retract_conversation_memories=retract),
        'retraction_can_be_skipped': lambda *a, **kw: False,
        'ConversationReplacementConflictError': Conflict,
        'HTTPException': HTTPException,
        'delete_conversation_screen_frames': cleanup,
        'delete_conversation_and_frame_evidence': hard_delete,
        'action_items_db': MagicMock(get_action_items_by_conversation=MagicMock(return_value=[])),
        'delete_conversation_audio_files': MagicMock(),
        'delete_owner_prompt_embedding_cache': MagicMock(),
        'delete_vector': MagicMock(),
        'delete_transcript_chunk_vectors': MagicMock(),
        'record_product_event': MagicMock(),
    }
    delete = function('routers/conversations.py', 'delete_conversation', namespace)
    if failure:
        with pytest.raises(HTTPException if failure == 'retraction' else RuntimeError):
            delete('c', MagicMock(), True, None, 'u')
        assert 'users/u/conversations/c' in store.rows
    else:
        assert delete('c', MagicMock(), True, None, 'u') == {'status': 'Ok'}
        assert 'users/u/conversations/c' not in store.rows
    assert tombstones.is_deleted('u', 'c')


def test_account_wipe_enumerates_tombstones_even_without_root(store):
    tombstones.record_deletion('u', 'c')

    def purge(ref, **kwargs):
        for path in list(store.rows):
            if path.startswith(ref.path + '/'):
                store.rows.pop(path)

    wipe = function(
        'database/users.py',
        'delete_user_data',
        {
            'db': store,
            'logger': MagicMock(),
            'delete_collection_recursive': purge,
        },
    )
    wipe('u')
    assert store.rows == {}
    assert not tombstones.is_deleted('u', 'c')


def test_live_client_chosen_deleted_id_is_closed_before_bootstrap_and_registration(store):
    tombstones.record_deletion('u', 'c')
    calls = []

    async def call(fn, *args):
        calls.append(fn)
        return fn(*args)

    websocket = SimpleNamespace(close=AsyncMock())
    host = SimpleNamespace(
        request=SimpleNamespace(uid='u', websocket=websocket),
        client_conversation_id='c',
        persistence=SimpleNamespace(call=call),
        _bootstrap=AsyncMock(),
    )
    register = MagicMock()
    namespace = {
        'conversation_tombstones': tombstones,
        'register_listen_session': register,
        'listen_reconnect_budget': SimpleNamespace(admit=lambda *args: (True, 0)),
    }
    admit = function('routers/listen/runtime.py', '_admit', namespace)
    host._admit = MethodType(admit, host)
    run = function('routers/listen/runtime.py', '_run', namespace)
    asyncio.run(run(host))
    websocket.close.assert_awaited_once_with(code=1008, reason='Conversation was deleted')
    host._bootstrap.assert_not_awaited()
    register.assert_not_called()
    assert calls == [tombstones.is_deleted]


def test_developer_delete_commits_tombstone_before_cleanup_failure(store, monkeypatch):
    helper = AutoMockModule('utils.conversations.merge_conversations')

    def fail(*args):
        assert tombstones.is_deleted('u', 'c')
        raise RuntimeError('cleanup failed')

    helper.delete_conversation_with_sync_sources = fail
    delete = function(
        'routers/developer.py',
        'delete_conversation_endpoint',
        {
            'conversation_tombstones': tombstones,
            'HTTPException': HTTPException,
            'conversations_db': SimpleNamespace(get_conversation=lambda *a: {'id': 'c'}),
        },
    )
    with stub_modules({'utils.conversations.merge_conversations': helper}):
        with pytest.raises(RuntimeError, match='cleanup failed'):
            delete('c', 'u')
    assert tombstones.is_deleted('u', 'c')


def test_repeated_delete_after_hard_cleanup_preserves_original_metadata(store):
    tombstones.record_deletion('u', 'c')
    original = dict(store.rows['users/u/deleted_conversations/c'])
    store.rows.pop('users/u/conversations/c')
    tombstones.record_deletion('u', 'c')
    assert store.rows['users/u/deleted_conversations/c'] == original
