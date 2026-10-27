"""Real SDK commit encoding, preconditions, result metadata and bulk atomicity."""

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

from database import _client, batch_privacy_write_fence as fence, memory_change_head
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
        if operation in {'merge', 'update'}:
            write.update_mask = {'field_paths': ['dynamic']}
        if operation == 'update':
            write.current_document = {'update_time': {'seconds': 42}}
    request = CommitRequest(database='db', transaction=b'attempt', writes=[write])
    before = CommitRequest.serialize(request)
    prepared, count = fence.augment_commit(request)
    assert count == 1 and len(prepared.writes) == 2
    assert prepared.writes[0] == write
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
    assert count == 12 and len(first.writes) == 15
    assert len({w.update.name for w in first.writes[-3:]}) == 3
    assert first.writes[-1] != second.writes[-1]


def test_unrelated_writes_are_byte_identical_and_expanded_batches_never_drop_fence():
    request = {'writes': [{'delete': f'{ROOT}/users/u/screen_frames/x'}]}
    assert fence.augment_commit(request)[0] is request
    source = [Write(delete=f'{ROOT}/users/u/conversations/{i}') for i in range(500)]
    prepared, count = fence.augment_commit({'writes': source})
    assert count == 500 and len(prepared.writes) == 501
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
        assert len(request.writes) == 2
        assert request.writes[-1].update.name == TOKEN
        calls.append(('atomic', request))
        if request.writes[0].delete.endswith('/bad'):
            raise FailedPrecondition('synthetic CAS conflict')
        return CommitResponse(write_results=[WriteResult(update_time={'seconds': 101}), WriteResult()])

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


@pytest.mark.parametrize(
    'family,fields',
    [
        ('users/u', fence._USER_FIELDS),
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
