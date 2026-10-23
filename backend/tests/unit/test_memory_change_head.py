"""Actual SDK protobufs cover every mutation surface without fake transaction semantics."""

from types import SimpleNamespace

import pytest
from google.cloud.firestore_v1.types import CommitRequest, CommitResponse, Document, Write, WriteResult

from database import memory_change_head as head

ROOT = 'projects/demo/databases/(default)/documents'


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
