"""Real SDK commit encoding, preconditions, result metadata and bulk atomicity."""

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from google.api_core.exceptions import FailedPrecondition
from google.auth.credentials import AnonymousCredentials
from google.cloud import firestore
from google.cloud.firestore_v1 import AsyncClient
from google.cloud.firestore_v1.services.firestore import FirestoreAsyncClient, FirestoreClient
from google.cloud.firestore_v1.types import (
    BatchWriteResponse,
    CommitRequest,
    CommitResponse,
    Document,
    Write,
    WriteResult,
)
from google.rpc.status_pb2 import Status
from google.protobuf.timestamp_pb2 import Timestamp

from database.batch_account_authority_schema import USER_POLICY_FIELDS
from database import (
    _client,
    batch_privacy_write_cache as write_cache,
    batch_privacy_write_fence as fence,
    memory_change_head,
)
from database.batch_pipeline_privacy import privacy_owner_key

ROOT = 'projects/demo/databases/(default)/documents'
TOKEN = f'{ROOT}/batch_pipeline_privacy/{privacy_owner_key("u")}'
AUTHORITIES = [
    'users/u',
    'users/u/conversations/c',
    'users/u/deleted_conversations/c',
    'account_deletions/u',
    'legal_holds/u',
    'legal_hold_deletion_gates/u',
    f'batch_pipeline_privacy/{privacy_owner_key("u")}',
]


@pytest.mark.parametrize('authority', AUTHORITIES)
@pytest.mark.parametrize('operation', ['set', 'merge', 'update', 'delete', 'transform'])
def test_all_authority_shapes_share_one_atomic_commit(authority, operation):
    path = f'{ROOT}/{authority}'
    if operation == 'delete':
        write = Write(delete=path)
    elif operation == 'transform':
        write = Write(
            transform={
                'document': path,
                'field_transforms': [
                    {'field_path': 'dynamic', 'increment': {'integer_value': 1}},
                ],
            }
        )
    else:
        write = Write(update=Document(name=path, fields={'dynamic': {'boolean_value': True}}))
        if authority.startswith('batch_pipeline_privacy/') and operation == 'set':
            write.update.fields.update(
                {
                    'generation': {'integer_value': 7},
                    'blocked': {'boolean_value': False},
                    'purging': {'boolean_value': False},
                }
            )
        if operation in {'merge', 'update'}:
            write.update_mask = {'field_paths': ['dynamic']}
        if operation == 'update':
            write.current_document = {'update_time': {'seconds': 42}}
    request = CommitRequest(database='db', transaction=b'attempt', writes=[write])
    before = CommitRequest.serialize(request)
    if authority.startswith('batch_pipeline_privacy/') and operation == 'delete':
        with pytest.raises(ValueError, match='authority must survive deletion'):
            fence.augment_commit(request)
        assert CommitRequest.serialize(request) == before
        return
    prepared, count = fence.augment_commit(request)
    home_writes = 0
    if authority == 'users/u' and operation in {'set', 'transform'}:
        home_writes = 1  # combined policy/coverage control
    elif authority == 'users/u/conversations/c':
        home_writes = 3 if operation == 'transform' else 2  # source metadata folds into ordinary writes
    elif authority == 'users/u/deleted_conversations/c':
        home_writes = 2
    assert count == 1 and len(prepared.writes) == 2 + home_writes
    original = prepared.writes[0]
    assert original.current_document == write.current_document
    assert original.delete == write.delete and original.transform == write.transform
    assert original.update.name == write.update.name
    assert all(original.update.fields[k] == value for k, value in write.update.fields.items())
    assert original.update_transforms == write.update_transforms
    assert set(write.update_mask.field_paths).issubset(original.update_mask.field_paths)
    assert prepared.transaction == b'attempt'
    assert CommitRequest.serialize(request) == before
    assert prepared.writes[-1].update.name == TOKEN
    assert set(prepared.writes[-1].update_mask.field_paths) == {fence.TOKEN_FIELD, fence.SCHEMA_FIELD}
    assert len(prepared.writes[-1].update.fields[fence.TOKEN_FIELD].string_value) == 32


def test_one_token_per_plane_and_owner_and_random_on_every_retry():
    source = [Write(delete=f'{ROOT}/users/u/conversations/{i}') for i in range(10)]
    source.extend(
        [
            Write(delete=f'{ROOT}/users/v'),
            Write(delete='projects/demo/databases/other/documents/users/u'),
        ]
    )
    first, count = fence.augment_commit({'writes': source})
    second, _ = fence.augment_commit({'writes': source})
    assert count == 12 and len(first.writes) == 26  # ten Home receipts plus one control, three privacy tokens
    assert len({w.update.name for w in first.writes[-3:]}) == 3
    assert first.writes[-1] != second.writes[-1]


@pytest.mark.parametrize('operation', ['create', 'merge_upsert', 'replace'])
def test_metadata_only_conversation_creation_always_rotates(operation):
    write = Write(update=Document(name=f'{ROOT}/users/u/conversations/c', fields={'title': {'string_value': 'new'}}))
    if operation == 'create':
        write.current_document = {'exists': False}
    elif operation == 'merge_upsert':
        write.update_mask = {'field_paths': ['title']}
    prepared, _ = fence.augment_commit({'writes': [write]})
    assert prepared.writes[0].current_document == write.current_document
    assert prepared.writes[0].update.fields['title'] == write.update.fields['title']
    assert prepared.writes[-1].update.name == TOKEN


@pytest.mark.asyncio
@pytest.mark.parametrize('asynchronous', [False, True])
@pytest.mark.parametrize('bulk', [False, True])
async def test_authority_delete_refuses_whole_request_before_transport(asynchronous, bulk):
    called = []

    def transport(*args, **kwargs):
        called.append(True)
        raise AssertionError('destructive authority request reached transport')

    async def async_transport(*args, **kwargs):
        return transport(*args, **kwargs)

    wrap = fence._wrap_bulk if bulk else fence._wrap_commit
    wrapped = wrap(async_transport if asynchronous else transport)
    request = {
        'database': 'db',
        'writes': [Write(delete=f'{ROOT}/users/u/conversations/source'), Write(delete=TOKEN)],
    }
    with pytest.raises(ValueError, match='authority must survive deletion'):
        if asynchronous:
            await wrapped(None, request=request)
        else:
            wrapped(None, request=request)
    assert called == []


@pytest.mark.asyncio
@pytest.mark.parametrize('asynchronous', [False, True])
@pytest.mark.parametrize('bulk', [False, True])
@pytest.mark.parametrize(
    'mutation',
    [
        'masked_delete',
        'quoted_delete',
        'replacement',
        'nested_state',
        'null_state',
        'wrong_generation',
        'negative_generation',
        'state_transform',
        'update_transform',
    ],
)
async def test_authority_state_loss_refuses_whole_request_before_transport(asynchronous, bulk, mutation):
    write = Write(update=Document(name=TOKEN), update_mask={'field_paths': ['generation', 'blocked', 'purging']})
    if mutation == 'quoted_delete':
        write.update_mask.field_paths = ['`generation`', '`blocked`', '`purging`']
    elif mutation == 'replacement':
        write = Write(update=Document(name=TOKEN, fields={'dynamic': {'boolean_value': True}}))
    elif mutation == 'nested_state':
        write.update_mask.field_paths = ['blocked.nested']
    elif mutation == 'null_state':
        write.update_mask.field_paths = ['blocked']
        write.update.fields['blocked'] = {'null_value': 0}
    elif mutation in {'wrong_generation', 'negative_generation'}:
        write.update_mask.field_paths = ['generation']
        write.update.fields['generation'] = (
            {'string_value': '7'} if mutation == 'wrong_generation' else {'integer_value': -1}
        )
    elif mutation in {'state_transform', 'update_transform'}:
        transform = {'field_path': 'generation', 'increment': {'integer_value': 1}}
        if mutation == 'state_transform':
            write = Write(transform={'document': TOKEN, 'field_transforms': [transform]})
        else:
            write.update_mask.field_paths = []
            write.update_transforms = [transform]
    called = []

    def transport(*args, **kwargs):
        called.append(True)
        raise AssertionError('state-loss request reached transport')

    async def async_transport(*args, **kwargs):
        return transport(*args, **kwargs)

    wrapped = (fence._wrap_bulk if bulk else fence._wrap_commit)(async_transport if asynchronous else transport)
    request = {'database': 'db', 'writes': [Write(delete=f'{ROOT}/users/u/conversations/source'), write]}
    with pytest.raises(ValueError, match='batch privacy authority'):
        if asynchronous:
            await wrapped(None, request=request)
        else:
            wrapped(None, request=request)
    assert called == []


def test_unrelated_writes_are_byte_identical_and_expanded_batches_never_drop_fence():
    request = {'writes': [{'delete': f'{ROOT}/users/u/screen_frames/x'}]}
    assert fence.augment_commit(request)[0] is request
    source = [Write(delete=f'{ROOT}/users/u/conversations/{i}') for i in range(500)]
    prepared, count = fence.augment_commit({'writes': source})
    assert count == 500 and len(prepared.writes) == 1002  # source + 500 dirty receipts + control + token
    assert prepared.writes[-1].update.name == TOKEN
    assert len(source) == 500


@pytest.mark.asyncio
@pytest.mark.parametrize('asynchronous', [False, True])
@pytest.mark.parametrize('operation', ['set', 'create', 'update', 'delete', 'batch', 'transaction'])
async def test_actual_sdk_surfaces_and_composed_hooks_preserve_results(monkeypatch, asynchronous, operation):
    captured = []

    # Production list projection hook wraps SDK surfaces; memory and privacy
    # hooks wrap GAPIC. Capture below both GAPIC hooks, at the network boundary.
    def capture(client, request=None, **kwargs):
        request = CommitRequest(request)
        captured.append(request)
        return CommitResponse(
            write_results=[WriteResult(update_time={'seconds': i + 100}) for i, _ in enumerate(request.writes)],
            commit_time={'seconds': 999},
        )

    if asynchronous:

        async def async_capture(client, request=None, **kwargs):
            return capture(client, request, **kwargs)

        monkeypatch.setattr(
            FirestoreAsyncClient, 'commit', fence._wrap_commit(memory_change_head._wrap_commit(async_capture))
        )
        client = AsyncClient(project='demo', credentials=AnonymousCredentials())
        client._firestore_api_internal = FirestoreAsyncClient(credentials=AnonymousCredentials())
    else:
        monkeypatch.setattr(FirestoreClient, 'commit', fence._wrap_commit(memory_change_head._wrap_commit(capture)))
        client = firestore.Client(project='demo', credentials=AnonymousCredentials())
        client._firestore_api_internal = FirestoreClient(credentials=AnonymousCredentials())
    ref = client.document('users/u/conversations/c')
    if operation in {'batch', 'transaction'}:
        batch = client.batch() if operation == 'batch' else client.transaction()
        batch.update(ref, {'record_lane_owner': 'batch_live_v1'})
        batch.set(client.document('users/u/memories/m'), {'fact': 'synthetic'})
        if operation == 'transaction':
            batch._id = b'attempt'
        call = batch.commit() if operation == 'batch' else batch._commit()
    elif operation == 'update':
        call = ref.update({'deleted': True}, option=client.write_option(last_update_time={'seconds': 42}))
    else:
        call = getattr(ref, operation)(*([] if operation == 'delete' else [{'dynamic': True}]))
    result = await call if asynchronous else call
    assert len(captured) == 1
    writes = captured[0].writes
    assert writes[-2].update.name == TOKEN if operation in {'batch', 'transaction'} else writes[-1].update.name == TOKEN
    assert (
        writes[0].delete == ref._document_path if operation == 'delete' else writes[0].update.name == ref._document_path
    )
    if operation == 'update':
        assert writes[0].current_document.update_time.timestamp() == 42
    if operation in {'batch', 'transaction'}:
        assert len(result) == len(batch.write_results) == 2
        assert result[0].update_time.timestamp() == 100
    elif operation != 'delete':
        assert result.update_time.timestamp() == 100
    else:
        assert result.timestamp() == 999


@pytest.mark.asyncio
@pytest.mark.parametrize('asynchronous', [False, True])
async def test_bulk_uses_atomic_source_token_pairs_and_preserves_partial_status(monkeypatch, asynchronous):
    calls = []

    def commit(client, request=None, **kwargs):
        assert len(request.writes) == 4  # source, Home receipt/control, privacy token
        assert request.writes[-1].update.name == TOKEN
        calls.append(('atomic', request))
        if request.writes[0].delete.endswith('/bad'):
            raise FailedPrecondition('synthetic CAS conflict')
        return CommitResponse(
            write_results=[WriteResult(update_time={'seconds': 101}), WriteResult(), WriteResult(), WriteResult()]
        )

    def bulk(client, request=None, **kwargs):
        calls.append(('bulk', request))
        assert len(request.writes) == 1
        return BatchWriteResponse(write_results=[WriteResult(update_time={'seconds': 202})], status=[Status()])

    request = {
        'database': 'db',
        'writes': [
            Write(delete=f'{ROOT}/users/u/conversations/good'),
            Write(delete=f'{ROOT}/unrelated/a'),
            Write(delete=f'{ROOT}/users/u/conversations/bad'),
        ],
    }
    if asynchronous:

        async def acommit(client, request=None, **kwargs):
            return commit(client, request, **kwargs)

        async def abulk(client, request=None, **kwargs):
            return bulk(client, request, **kwargs)

        client = SimpleNamespace()
        client.commit = lambda **kwargs: fence._wrap_commit(acommit)(client, **kwargs)
        result = await fence._wrap_bulk(abulk)(client, request=request)
    else:
        client = SimpleNamespace()
        client.commit = lambda **kwargs: fence._wrap_commit(commit)(client, **kwargs)
        result = fence._wrap_bulk(bulk)(client, request=request)
    assert [c[0] for c in calls] == ['atomic', 'atomic', 'bulk']
    assert [s.code for s in result.status] == [0, 0, 9]
    assert [r.update_time.timestamp() if r.update_time else 0 for r in result.write_results] == [101, 202, 0]


def test_flattened_arguments_idempotent_install_and_failed_transport():
    original = lambda *args, **kwargs: (_ for _ in ()).throw(FailedPrecondition('synthetic'))
    wrapped = fence._wrap_commit(original)
    assert fence._wrap_commit(wrapped) is wrapped
    with pytest.raises(ValueError, match='flattened'):
        wrapped(None, request={'database': 'db'}, writes=[Write(delete=f'{ROOT}/users/u')])
    with pytest.raises(FailedPrecondition):
        wrapped(None, database='db', writes=[Write(delete=f'{ROOT}/users/u')])
    called = []
    bulk = fence._wrap_bulk(lambda *args, **kwargs: called.append(True))
    with pytest.raises(ValueError, match='labeled'):
        bulk(None, request={'labels': {'a': 'b'}, 'writes': [Write(delete=f'{ROOT}/users/u')]})
    assert not called


@pytest.mark.parametrize('asynchronous', [False, True])
async def test_committed_write_returns_its_result_when_cache_invalidation_raises(monkeypatch, caplog, asynchronous):
    monkeypatch.setenv('REDIS_DB_HOST', 'synthetic-redis')
    committed = []
    when = datetime(2026, 11, 26, tzinfo=timezone.utc)

    def commit(client, request, **kwargs):
        committed.append(request)
        return CommitResponse(commit_time=when, write_results=[WriteResult(update_time=when)] * len(request.writes))

    def broken(paths, commit_time):
        assert TOKEN in paths and commit_time == when
        raise RuntimeError('synthetic invalidation failure')

    monkeypatch.setattr(fence, 'invalidate_tokenless', broken)
    metric = write_cache.TOKENLESS.labels('invalidation_error')._value
    before = metric.get()
    request = CommitRequest(writes=[Write(delete=f'{ROOT}/users/u/conversations/c')])
    if asynchronous:

        async def async_commit(client, request, **kwargs):
            return commit(client, request, **kwargs)

        result = await fence._wrap_commit(async_commit)(None, request)
    else:
        result = fence._wrap_commit(commit)(None, request)
    assert len(committed) == len(result.write_results) == 1
    assert result.commit_time == when
    assert metric.get() == before + 1
    assert 'RuntimeError' in caplog.text


@pytest.mark.parametrize(
    'timestamp',
    [
        Timestamp(seconds=123, nanos=456789123),
        CommitResponse(commit_time={'seconds': 123, 'nanos': 456789123}).commit_time,
    ],
)
def test_redis_invalidation_keeps_firestore_timestamp_precision(timestamp):
    assert write_cache._revision(timestamp) == 123_456_789_123


@pytest.mark.parametrize(
    'family,fields',
    [
        ('users/u', USER_POLICY_FIELDS),
        ('users/u/conversations/c', fence._CONVERSATION_FIELDS),
    ],
)
def test_exact_masked_authority_fields_invalidate_but_blind_metadata_updates_do_not(family, fields):
    def update(field):
        return Write(
            update=Document(name=f'{ROOT}/{family}'),
            update_mask={'field_paths': [field]},
            current_document={'exists': True},
        )

    for field in fields:
        assert fence.authority_tokens([update(field)]) == {TOKEN}
        assert fence.authority_tokens([update(f'`{field}`.nested')]) == {TOKEN}
    metadata = update('title')
    assert not fence.authority_tokens([metadata])
    # A merge without an existence precondition can recreate the document.
    metadata.current_document = {}
    assert fence.authority_tokens([metadata]) == {TOKEN}


def test_unrelated_bulk_labels_are_preserved_byte_for_byte():
    seen = []
    request = {'database': 'db', 'labels': {'owner': 'test'}, 'writes': [Write(delete=f'{ROOT}/unrelated/a')]}
    fence._wrap_bulk(lambda client, request=None, **kw: seen.append(request))(None, request=request)
    assert seen == [request] and seen[0] is request


@pytest.mark.asyncio
@pytest.mark.parametrize('asynchronous', [False, True])
async def test_flattened_bulk_authorities_cannot_bypass_atomic_token(monkeypatch, asynchronous):
    captured = []

    def commit(client, request=None, **kwargs):
        captured.append(CommitRequest(request))
        return CommitResponse(write_results=[WriteResult(), WriteResult()])

    def bulk(client, request=None, **kwargs):
        raise AssertionError('authority must use atomic Commit, never raw BatchWrite')

    client = SimpleNamespace()
    if asynchronous:

        async def acommit(client, request=None, **kwargs):
            return commit(client, request, **kwargs)

        async def abulk(client, request=None, **kwargs):
            return bulk(client, request, **kwargs)

        client.commit = lambda **kwargs: fence._wrap_commit(acommit)(client, **kwargs)
        call = fence._wrap_bulk(abulk)(client, database='db', writes=[Write(delete=f'{ROOT}/users/u')])
        result = await call
    else:
        client.commit = lambda **kwargs: fence._wrap_commit(commit)(client, **kwargs)
        result = fence._wrap_bulk(bulk)(client, database='db', writes=[Write(delete=f'{ROOT}/users/u')])
    assert len(captured) == 1 and len(captured[0].writes) == 2
    assert captured[0].writes[-1].update.name == TOKEN
    assert len(result.status) == 1 and result.status[0].code == 0


def test_installer_only_skips_fileless_sdk_stubs_and_propagates_real_import_failure(monkeypatch):
    import builtins

    original = builtins.__import__

    def unavailable(name, *args, **kwargs):
        if name == 'database.batch_privacy_write_fence':
            raise ImportError('synthetic missing mandatory fence')
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, '__import__', unavailable)
    assert _client.firestore.__file__
    with pytest.raises(ImportError, match='mandatory fence'):
        _client._install_batch_privacy_write_fence()
    monkeypatch.setattr(_client.firestore, '__file__', None)
    _client._install_batch_privacy_write_fence()


@pytest.mark.asyncio
@pytest.mark.parametrize('asynchronous', [False, True])
async def test_mixed_account_bulk_erasure_never_recreates_erased_subtree(asynchronous):
    captured = []
    other_plane = ROOT.replace('projects/demo/', 'projects/demo-other/')
    sources = [
        Write(delete=f'{ROOT}/users/u/conversations/erased'),
        Write(delete=f'{ROOT}/users/u'),
        Write(delete=f'{ROOT}/users/v/conversations/retained'),
        Write(delete=f'{other_plane}/users/u/conversations/retained'),
    ]

    def commit(client, request=None, **kwargs):
        captured.append(CommitRequest(request))
        return CommitResponse(
            write_results=[WriteResult(update_time={'seconds': len(captured)}) for _ in request.writes]
        )

    def bulk(client, request=None, **kwargs):
        raise AssertionError('all canonical mutations require atomic Commit')

    client = SimpleNamespace()
    if asynchronous:

        async def acommit(client, request=None, **kwargs):
            return commit(client, request, **kwargs)

        async def abulk(client, request=None, **kwargs):
            return bulk(client, request, **kwargs)

        client.commit = lambda **kwargs: fence._wrap_commit(acommit)(client, **kwargs)
        result = await fence._wrap_bulk(abulk)(client, request={'database': 'db', 'writes': sources})
    else:
        client.commit = lambda **kwargs: fence._wrap_commit(commit)(client, **kwargs)
        result = fence._wrap_bulk(bulk)(client, request={'database': 'db', 'writes': sources})
    assert len(result.status) == len(result.write_results) == len(sources)
    assert [r.update_time.timestamp() for r in result.write_results] == [1, 2, 3, 4]
    assert all(status.code == 0 for status in result.status)
    assert all(not w.update.name.startswith(f'{ROOT}/users/u/') for request in captured for w in request.writes)
    assert any(w.update.name == f'{ROOT}/users/v/episode_links/home_feed_control' for w in captured[2].writes)
    assert any(w.update.name == f'{other_plane}/users/u/episode_links/home_feed_control' for w in captured[3].writes)
    # The ContextVar scope must reset after the batch, even for the same uid.
    restored, _ = fence.augment_commit({'writes': [sources[0]]})
    assert any(w.update.name == f'{ROOT}/users/u/episode_links/home_feed_control' for w in restored.writes)
