"""Execute deletion entrypoints against a content-free Firestore fake.

The router graph is import-heavy; compile its actual function body with isolated
collaborators rather than importing network clients or asserting source strings.
"""

import ast
import asyncio
from contextlib import ExitStack, nullcontext
from pathlib import Path
from types import SimpleNamespace, MethodType
from unittest.mock import MagicMock, AsyncMock

from fastapi import HTTPException, Response
import pytest

from database import conversation_tombstones as tombstones
from database import user_data_deletion
from database.account_deletion_operational_holds import StoragePrefixPurgeBlocked, StoragePrefixPurgeError
from google.api_core.exceptions import AlreadyExists
from testing.import_isolation import stub_modules, AutoMockModule
from utils.log_sanitizer import sanitize

ROOT = Path(__file__).resolve().parents[2]


class Store:
    def __init__(self):
        self.rows = {}

    def collection(self, name):
        return Ref(self, name)

    def batch(self):
        return Batch()


class Batch:
    def __init__(self):
        self.refs = []

    def delete(self, ref):
        self.refs.append(ref)

    def commit(self):
        for ref in self.refs:
            ref.delete()


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
    if path == 'routers/conversations.py' and name == 'delete_conversation':
        namespace['Response'] = Response
        namespace['nullcontext'] = nullcontext
        namespace['ExitStack'] = ExitStack
        namespace.setdefault('accepts_conversation_deletes', lambda: False)
        namespace.setdefault('destructive_operation_gate', lambda *args, **kwargs: nullcontext())
        namespace.setdefault('CONVERSATION_DELETE_GATE_WAIT_SECONDS', 0.0)
        namespace.setdefault('deferred_batch_purges', lambda uid: nullcontext())
        namespace.setdefault('_legal_hold_defers_delete', lambda uid: False)
        namespace.setdefault('durable_audio_erasure', lambda: False)
        namespace.setdefault('arm_audio_erasure', MagicMock())
        function(path, '_delete_privacy_audio_after_response', namespace)
        function(path, '_delete_conversation_under_gate', namespace)
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
    monkeypatch.setattr('database.batch_pipeline_purge.purge_batch_owner', MagicMock())
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


def test_non_cascade_delete_purges_prompt_evidence_and_primary_audio_after_intent(store):
    calls = []

    def purge(uid, cid):
        calls.append(('prompt', tombstones.is_deleted(uid, cid)))

    def hard_delete(uid, cid):
        calls.append(('parent', tombstones.is_deleted(uid, cid)))
        store.rows.pop(f'users/{uid}/conversations/{cid}')

    snapshots = MagicMock()
    snapshots.get_conversation_raw_snapshot.return_value = {'sync_merged_from': ['donor']}
    namespace = {
        'logger': MagicMock(),
        'conversation_tombstones': tombstones,
        'conversations_db': snapshots,
        'delete_owner_prompt_embedding_cache': purge,
        'delete_conversation_screen_frames': MagicMock(),
        'delete_conversation_and_frame_evidence': hard_delete,
        'delete_conversation_audio_under_gate': MagicMock(),
        'delete_vector': MagicMock(),
        'delete_transcript_chunk_vectors': MagicMock(),
        'record_product_event': MagicMock(),
    }
    delete = function('routers/conversations.py', 'delete_conversation', namespace)
    background = MagicMock()
    # The handler returns no body: the route is 204 No Content, the contract the
    # released mobile client gates on (test_conversation_delete_wire_contract.py).
    assert delete('c', background, False, None, 'u').status_code == 204
    assert calls == [('prompt', True), ('parent', True)]
    # Audio is primary content: a non-cascade delete erases it after the response, donors included.
    background.add_task.assert_called_once_with(
        namespace['_delete_privacy_audio_after_response'], 'u', 'c', source_ids=['donor']
    )


def test_delete_owes_audio_durably_before_the_primary_row_goes(store):
    """Both cascade modes arm the audio obligation after intent and before primary deletion."""
    calls = []

    def hard_delete(uid, cid):
        calls.append(('parent', tombstones.is_deleted(uid, cid)))
        store.rows.pop(f'users/{uid}/conversations/{cid}')

    def arm(uid, cid, source_ids):
        calls.append(('arm', tombstones.is_deleted(uid, cid), list(source_ids)))

    snapshots = MagicMock()
    snapshots.get_conversation_raw_snapshot.return_value = {'sync_merged_from': ['donor']}
    namespace = {
        'logger': MagicMock(),
        'conversation_tombstones': tombstones,
        'conversations_db': snapshots,
        'delete_owner_prompt_embedding_cache': MagicMock(),
        'delete_conversation_screen_frames': MagicMock(),
        'delete_conversation_and_frame_evidence': hard_delete,
        'delete_conversation_audio_under_gate': MagicMock(),
        'delete_vector': MagicMock(),
        'delete_transcript_chunk_vectors': MagicMock(),
        'record_product_event': MagicMock(),
        'durable_audio_erasure': lambda: True,
        'arm_audio_erasure': arm,
    }
    delete = function('routers/conversations.py', 'delete_conversation', namespace)
    background = MagicMock()
    assert delete('c', background, False, None, 'u').status_code == 204
    assert calls == [('arm', True, ['donor']), ('parent', True)]
    # The durable runner erases it; no unretried after-response attempt remains.
    background.add_task.assert_not_called()


def test_unarmed_audio_obligation_fails_the_delete_before_the_primary_row_goes(store):
    hard_delete = MagicMock()

    def arm(*args):
        raise RuntimeError('firestore unavailable')

    namespace = {
        'logger': MagicMock(),
        'conversation_tombstones': tombstones,
        'conversations_db': MagicMock(get_conversation_raw_snapshot=MagicMock(return_value={})),
        'delete_owner_prompt_embedding_cache': MagicMock(),
        'delete_conversation_screen_frames': MagicMock(),
        'delete_conversation_and_frame_evidence': hard_delete,
        'delete_conversation_audio_under_gate': MagicMock(),
        'delete_vector': MagicMock(),
        'delete_transcript_chunk_vectors': MagicMock(),
        'record_product_event': MagicMock(),
        'durable_audio_erasure': lambda: True,
        'arm_audio_erasure': arm,
        'HTTPException': HTTPException,
    }
    delete = function('routers/conversations.py', 'delete_conversation', namespace)
    with pytest.raises(HTTPException) as error:
        delete('c', MagicMock(), False, None, 'u')
    assert error.value.status_code == 503
    # The row survives, so a retry is not answered ``already_deleted`` and re-arms it.
    hard_delete.assert_not_called()
    assert tombstones.is_deleted('u', 'c')


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
        'conversations_db': SimpleNamespace(
            get_conversation_raw_snapshot=lambda *args, **kwargs: {'sync_merged_from': ['donor']}
        ),
        'object_lake': SimpleNamespace(LakeFetchError=type('LakeFetchError', (Exception,), {})),
        'os': SimpleNamespace(getenv=lambda *args: 'canonical'),
        'MemoryService': lambda **kw: SimpleNamespace(retract_conversation_memories=retract),
        'retraction_can_be_skipped': lambda *a, **kw: False,
        'ConversationReplacementConflictError': Conflict,
        'HTTPException': HTTPException,
        'delete_conversation_screen_frames': cleanup,
        'delete_conversation_and_frame_evidence': hard_delete,
        'action_items_db': MagicMock(get_action_items_by_conversation=MagicMock(return_value=[])),
        'delete_conversation_audio_under_gate': MagicMock(),
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
        tasks = MagicMock()
        assert delete('c', tasks, True, None, 'u').status_code == 204
        tasks.add_task.assert_called_once_with(
            namespace['_delete_privacy_audio_after_response'], 'u', 'c', source_ids=['donor']
        )
        assert 'users/u/conversations/c' not in store.rows
    assert tombstones.is_deleted('u', 'c')


@pytest.mark.parametrize(
    ('error', 'outcome', 'reason'),
    [
        (
            StoragePrefixPurgeError('owner storage list failed in sync: insufficientPermissions'),
            'failed',
            'insufficientPermissions',
        ),
        (
            StoragePrefixPurgeBlocked({('sync', 'chunks/u/c/clip', 1): 'objectUnderActiveHold'}),
            'blocked',
            'objectUnderActiveHold',
        ),
    ],
)
def test_background_audio_purge_reports_provider_outcome_once(error, outcome, reason):
    purge = MagicMock(side_effect=error)
    logger = MagicMock()
    namespace = {
        'delete_conversation_audio_under_gate': purge,
        'logger': logger,
        'sanitize': sanitize,
    }
    background_purge = function('routers/conversations.py', '_delete_privacy_audio_after_response', namespace)

    background_purge('u', 'c', source_ids=['donor'])

    purge.assert_called_once_with('u', 'c', source_ids=['donor'])
    logger.error.assert_called_once()
    assert logger.error.call_args.args[3] == outcome
    assert reason in logger.error.call_args.args[4]
    logger.warning.assert_not_called()
    logger.exception.assert_not_called()


@pytest.mark.parametrize('name', ['LegalHoldActive', 'LegalHoldAuthorityUnavailable', 'DestructiveOperationInProgress'])
def test_background_audio_sweep_stopped_by_a_hold_retains_and_reports(name):
    stop = type(name, (RuntimeError,), {})
    purge = MagicMock(side_effect=stop('held'))
    logger = MagicMock()
    namespace = {'delete_conversation_audio_under_gate': purge, 'logger': logger, 'sanitize': sanitize}
    background_purge = function('routers/conversations.py', '_delete_privacy_audio_after_response', namespace)
    background_purge('u', 'c', source_ids=['donor'])
    purge.assert_called_once_with('u', 'c', source_ids=['donor'])
    logger.warning.assert_called_once()
    assert logger.warning.call_args.args[1:] == ('c', name)
    logger.error.assert_not_called()


def test_background_audio_sweep_surfaces_unexpected_errors():
    purge = MagicMock(side_effect=RuntimeError('boom'))
    namespace = {'delete_conversation_audio_under_gate': purge, 'logger': MagicMock(), 'sanitize': sanitize}
    background_purge = function('routers/conversations.py', '_delete_privacy_audio_after_response', namespace)
    with pytest.raises(RuntimeError, match='boom'):
        background_purge('u', 'c', source_ids=[])


def test_account_wipe_enumerates_tombstones_even_without_root(store, monkeypatch):
    tombstones.record_deletion('u', 'c')
    data_plane = Store()
    data_plane.rows['rollout_cohorts/u'] = {'cohorts': {'dev': {'batch-pipeline': True}}}
    monkeypatch.setattr(user_data_deletion, 'search_apps_db', lambda _uid, my_apps: [])
    monkeypatch.setattr(user_data_deletion, 'get_data_plane_firestore_client', lambda: data_plane)
    # Global quiet-job pagination is covered by the real Firestore emulator.
    quiet_cleanup = MagicMock()
    monkeypatch.setattr(user_data_deletion, 'stop_quiet_checks_for_account', quiet_cleanup)

    def purge(ref, **kwargs):
        for path in list(store.rows):
            if path.startswith(ref.path + '/'):
                store.rows.pop(path)

    wipe = function(
        'database/users.py',
        'delete_user_data',
        {
            'db': store,
            'account_authority_writer_enabled': lambda: True,
            'get_data_plane_firestore_client': lambda: store,
            'logger': MagicMock(),
            'delete_collection_recursive': purge,
        },
    )
    wipe('u')
    quiet_cleanup.assert_called_once_with('u', firestore_client=store)
    assert data_plane.rows == {}
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


def test_developer_delete_purges_prompt_evidence_screen_frames_and_vectors(store):
    """#22997: the Developer API delete must not leave photos, screen frames,
    and vectors behind the way a raw ``delete_conversation_with_sync_sources``
    call does."""
    storage = AutoMockModule('utils.other.storage')
    screen_frames = AutoMockModule('utils.screen_frames.store')
    frame_evidence = AutoMockModule('services.conversation_frame_evidence')

    storage.delete_owner_prompt_embedding_cache = MagicMock()
    screen_frames.delete_conversation_screen_frames = MagicMock()
    frame_evidence.delete_conversation_and_frame_evidence = MagicMock()
    vector_db = SimpleNamespace(delete_vector=MagicMock(), delete_transcript_chunk_vectors=MagicMock())

    delete = function(
        'routers/developer.py',
        'delete_conversation_endpoint',
        {
            'conversation_tombstones': tombstones,
            'HTTPException': HTTPException,
            'conversations_db': SimpleNamespace(get_conversation=lambda *a: {'id': 'c'}),
            'vector_db': vector_db,
        },
    )
    with stub_modules(
        {
            'utils.other.storage': storage,
            'utils.screen_frames.store': screen_frames,
            'services.conversation_frame_evidence': frame_evidence,
        }
    ):
        result = delete('c', 'u')

    assert result == {"success": True}
    storage.delete_owner_prompt_embedding_cache.assert_called_once_with('u', 'c')
    screen_frames.delete_conversation_screen_frames.assert_called_once_with('u', 'c')
    frame_evidence.delete_conversation_and_frame_evidence.assert_called_once_with('u', 'c')
    vector_db.delete_vector.assert_called_once_with('u', 'c')
    vector_db.delete_transcript_chunk_vectors.assert_called_once_with('u', 'c')


def test_developer_delete_commits_tombstone_before_cleanup_failure(store, monkeypatch):
    storage = AutoMockModule('utils.other.storage')
    screen_frames = AutoMockModule('utils.screen_frames.store')
    frame_evidence = AutoMockModule('services.conversation_frame_evidence')

    def fail(*args):
        assert tombstones.is_deleted('u', 'c')
        raise RuntimeError('cleanup failed')

    storage.delete_owner_prompt_embedding_cache = fail
    delete = function(
        'routers/developer.py',
        'delete_conversation_endpoint',
        {
            'conversation_tombstones': tombstones,
            'HTTPException': HTTPException,
            'conversations_db': SimpleNamespace(get_conversation=lambda *a: {'id': 'c'}),
            'vector_db': SimpleNamespace(delete_vector=MagicMock(), delete_transcript_chunk_vectors=MagicMock()),
        },
    )
    with stub_modules(
        {
            'utils.other.storage': storage,
            'utils.screen_frames.store': screen_frames,
            'services.conversation_frame_evidence': frame_evidence,
        }
    ):
        with pytest.raises(RuntimeError, match='cleanup failed'):
            delete('c', 'u')
    assert tombstones.is_deleted('u', 'c')


def test_repeated_delete_after_hard_cleanup_preserves_original_metadata(store):
    tombstones.record_deletion('u', 'c')
    original = dict(store.rows['users/u/deleted_conversations/c'])
    store.rows.pop('users/u/conversations/c')
    tombstones.record_deletion('u', 'c')
    assert store.rows['users/u/deleted_conversations/c'] == original


@pytest.mark.parametrize('parent_exists', [True, False])
def test_deletion_purges_all_staged_chunks_after_durable_intent_even_without_parent(store, parent_exists):
    if not parent_exists:
        store.rows.pop('users/u/conversations/c')
    for index in (0, 17, 127):
        store.rows[f'users/u/from_segments_chunks/c-{index:03d}'] = {'payload': 'encrypted'}
    store.rows['users/u/from_segments_chunks/another-000'] = {'payload': 'encrypted'}
    tombstones.record_deletion('u', 'c')
    assert tombstones.is_deleted('u', 'c')
    assert not any(path.startswith('users/u/from_segments_chunks/c-') for path in store.rows)
    assert 'users/u/from_segments_chunks/another-000' in store.rows


def test_staging_cleanup_failure_leaves_deletion_intent_durable_and_retryable(store, monkeypatch):
    from database import from_segments_chunks

    calls = []

    def fail(owner, cid, **kwargs):
        calls.append(tombstones.is_deleted(owner, cid))
        raise RuntimeError('synthetic storage failure')

    monkeypatch.setattr(from_segments_chunks, 'purge_chunks', fail)
    with pytest.raises(RuntimeError, match='synthetic storage failure'):
        tombstones.record_deletion('u', 'c')
    assert calls == [True]
    assert tombstones.is_deleted('u', 'c')
