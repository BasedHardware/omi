"""Actual SDK protobufs cover every mutation surface without fake transaction semantics."""

from types import SimpleNamespace

import pytest
from google.auth.credentials import AnonymousCredentials
from google.cloud import firestore
from google.cloud.firestore_v1.async_client import AsyncClient
from google.cloud.firestore_v1.services.firestore import FirestoreClient, FirestoreAsyncClient
from google.cloud.firestore_v1.types import CommitRequest, CommitResponse, Document, Write, WriteResult

from database import _client, memory_change_head as head

ROOT = 'projects/demo/databases/(default)/documents'


@pytest.mark.asyncio
@pytest.mark.parametrize('asynchronous', [False, True])
@pytest.mark.parametrize('operation', ['set', 'delete'])
async def test_list_and_memory_writers_share_one_commit_and_keep_source_results(monkeypatch, asynchronous, operation):
    # Exercise both installers from the production entrypoint, through real SDK
    # batches and GAPIC request preparation, stopping only at the network edge.
    _client._install_memory_change_heads()
    _client._install_list_projection_writer()
    monkeypatch.delenv('OMI_LIST_PROJECTION_WRITER_ENABLED', raising=False)
    calls = []

    def capture(client, request=None, **kwargs):
        prepared = CommitRequest(request)
        calls.append(prepared)
        return CommitResponse(write_results=[WriteResult() for _ in prepared.writes])

    if asynchronous:

        async def capture_async(client, request=None, **kwargs):
            return capture(client, request=request, **kwargs)

        monkeypatch.setattr(FirestoreAsyncClient, 'commit', head._wrap_commit(capture_async))
        client = AsyncClient(project='demo', credentials=AnonymousCredentials())
        client._firestore_api_internal = FirestoreAsyncClient(credentials=AnonymousCredentials())
    else:
        monkeypatch.setattr(FirestoreClient, 'commit', head._wrap_commit(capture))
        client = firestore.Client(project='demo', credentials=AnonymousCredentials())
        client._firestore_api_internal = FirestoreClient(credentials=AnonymousCredentials())

    batch = client.batch()
    for collection in ('memory_items', 'conversations'):
        ref = client.document(f'users/u/{collection}/one')
        if operation == 'delete':
            batch.delete(ref)
        else:
            batch.set(ref, {'status': 'completed'})
    result = await batch.commit() if asynchronous else batch.commit()
    assert len(result) == len(batch.write_results) == 2
    assert len(calls) == 1
    writes = calls[0].writes
    paths = [write.delete or write.update.name for write in writes]
    assert len(paths) == len(set(paths)) == 5
    assert paths[:2] == [f'{ROOT}/users/u/{family}/one' for family in ('memory_items', 'conversations')]
    assert set(paths[2:]) == {
        f'{ROOT}/users/u/conversation_list_rows/one',
        f'{ROOT}/users/u/list_serving_versions/conversations',
        f'{ROOT}/users/u/memory_state/{head.HEAD_DOCUMENT}',
    }
    assert bool(writes[2].delete) == (operation == 'delete')
    assert writes[-1].update.fields['token'].string_value


@pytest.mark.parametrize('collection', sorted(head.SOURCE_COLLECTIONS))
@pytest.mark.parametrize('operation', ['set', 'delete', 'transform'])
def test_atomic_head_is_in_the_same_commit_as_every_source_change(collection, operation):
    path = f'{ROOT}/users/u/{collection}/a'
    write = Write(delete=path) if operation == 'delete' else Write(update=Document(name=path))
    if operation == 'transform':
        write = Write(
            transform={'document': path, 'field_transforms': [{'field_path': 'n', 'increment': {'integer_value': 1}}]}
        )
    request = CommitRequest(database='projects/demo/databases/(default)', writes=[write], transaction=b'attempt')
    prepared, count = head.augment_commit(request)
    assert count == 1
    assert len(prepared.writes) == 2
    assert prepared.writes[0] == write
    assert prepared.transaction == b'attempt'
    assert len(request.writes) == 1  # Never mutate caller buffers/retry state.
    change = prepared.writes[-1]
    assert change.update.name == f'{ROOT}/users/u/memory_state/{head.HEAD_DOCUMENT}'
    assert set(change.update_mask.field_paths) == {'token', 'schema'}
    assert change.update.fields['token'].string_value


def test_one_head_per_owner_per_commit_and_no_heads_for_unrelated_data():
    writes = [
        Write(delete=f'{ROOT}/users/{uid}/{collection}/x')
        for uid, collection in [
            ('u', 'memories'),
            ('u', 'memory_items'),
            ('v', 'memory_historical_overrides'),
            ('w', 'messages'),
        ]
    ]
    prepared, count = head.augment_commit({'writes': writes})
    assert count == 4
    assert len(prepared.writes) == 6


def test_unrelated_commits_are_not_copied_or_rewritten():
    request = {'writes': [{'update': {'name': f'{ROOT}/users/u/conversations/a'}}]}
    prepared, count = head.augment_commit(request)
    assert prepared is request and count == 1


def test_gapic_dictionary_writes_receive_the_same_atomic_head():
    request = {'writes': [{'delete': f'{ROOT}/users/u/memories/a'}]}
    prepared, count = head.augment_commit(request)
    assert count == 1 and len(prepared.writes) == 2
    assert prepared.writes[0].delete == request['writes'][0]['delete']


def test_sync_commit_preserves_source_results_and_transport_options():
    calls = []

    def original(client, request=None, **kwargs):
        calls.append((request, kwargs))
        return CommitResponse(write_results=[WriteResult() for _ in request.writes])

    wrapped = head._wrap_commit(original)
    result = wrapped(None, writes=[Write(delete=f'{ROOT}/users/u/memories/a')], timeout=7, metadata=(('a', 'b'),))
    assert len(result.write_results) == 1
    assert len(calls[0][0].writes) == 2
    assert calls[0][1] == {'timeout': 7, 'metadata': (('a', 'b'),)}
    assert head._wrap_commit(wrapped) is wrapped


@pytest.mark.asyncio
async def test_async_commit_uses_the_same_atomic_head_and_result_contract():
    async def original(client, request=None, **kwargs):
        assert len(request.writes) == 2
        return CommitResponse(write_results=[WriteResult(), WriteResult()])

    result = await head._wrap_commit(original)(
        None, request={'writes': [Write(delete=f'{ROOT}/users/u/memory_items/a')]}
    )
    assert len(result.write_results) == 1


def test_non_atomic_bulk_blocks_reuse_before_source_writes_and_never_clears_block():
    calls = []
    client = SimpleNamespace(commit=lambda **kwargs: calls.append(('block', kwargs)))
    wrapped = head._wrap_bulk(lambda *args, **kwargs: calls.append(('source', kwargs)))
    wrapped(
        client,
        request={'writes': [Write(delete=f'{ROOT}/users/u/memories/a')], 'database': 'db'},
        metadata=(('authorization', 'synthetic'),),
        timeout=7,
    )
    assert [call[0] for call in calls] == ['block', 'source']
    blocked = calls[0][1]['request']['writes'][0]
    assert calls[0][1]['metadata'] == (('authorization', 'synthetic'),)
    assert calls[0][1]['timeout'] == 7
    assert blocked.update.fields['blocked'].boolean_value
    assert 'blocked' in blocked.update_mask.field_paths
    assert 'blocked' not in head.head_write(ROOT, 'u').update_mask.field_paths


def test_failed_bulk_barrier_prevents_source_mutation():
    def fail(**kwargs):
        raise RuntimeError('barrier unavailable')

    client = SimpleNamespace(commit=fail)
    wrapped = head._wrap_bulk(lambda *args, **kwargs: pytest.fail('source must not execute'))
    with pytest.raises(RuntimeError, match='barrier unavailable'):
        wrapped(client, request={'writes': [Write(delete=f'{ROOT}/users/u/memories/a')]})
