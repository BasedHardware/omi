"""Real SDK write surfaces, Lua fencing, API cache races and owner isolation."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import fakeredis
import pytest
from fastapi import Request, Response
from google.auth.credentials import AnonymousCredentials
from google.cloud import firestore
from google.cloud.firestore_v1.document import DocumentReference
from google.cloud.firestore_v1.async_client import AsyncClient
from google.cloud.firestore_v1.bulk_batch import BulkWriteBatch
from google.cloud.firestore_v1.types import CommitResponse, BatchWriteResponse, WriteResult

from database import _client, action_items, action_item_versions as versions
from utils import external_list_reads as cache
from tests.unit.test_external_list_cache import FakeRedis


@pytest.fixture
def redis(monkeypatch):
    client = fakeredis.FakeRedis()
    monkeypatch.setattr(versions, '_redis', lambda: client)
    monkeypatch.setattr(cache, '_client', FakeRedis())
    return client


def sdk_client(*, during=None, fails=False):
    client = firestore.Client(project='synthetic-project', credentials=AnonymousCredentials())

    def commit(request, **kwargs):
        if during:
            during(request)
        if fails:
            raise RuntimeError('ambiguous commit')
        return CommitResponse(write_results=[WriteResult() for _ in request['writes']])

    client._firestore_api_internal = SimpleNamespace(commit=commit, batch_write=commit)
    return client


def lookup(uid='owner', **query):
    request = Request(
        {
            'type': 'http',
            'method': 'GET',
            'path': '/v1/dev/user/action-items',
            'headers': [(b'authorization', b'synthetic-key')],
            'query_string': b'',
        }
    )
    hit = cache.cached_list_response(
        request,
        Response(),
        uid=uid,
        context=SimpleNamespace(app_id='app', key_id='key'),
        query=query or {'limit': 25},
    )
    return request, hit


def fill(request, body=b'[]'):
    request.state.external_list_cache_entry.store(Response(body))


@pytest.mark.parametrize(
    'operation', ['set', 'create', 'update', 'delete', 'transform', 'batch', 'transaction', 'bulk']
)
def test_all_sync_sdk_write_surfaces_fence_and_invalidate(redis, operation):
    # Importing _client installed once, also for subsequently constructed SDK clients.
    assert getattr(firestore.WriteBatch.commit, '_omi_action_item_fence', False)
    request, hit = lookup()
    assert hit is None
    fill(request)
    assert lookup()[1].body == b'[]'
    before = versions.version('owner')
    other = versions.version('other')
    observations = []

    def during(request):
        observations.append(versions.version('owner'))
        assert lookup()[1] is None  # Neither a hit nor a fill during a write.
        assert getattr(lookup()[0].state, 'external_list_cache_entry', None) is None

    client = sdk_client(during=during)
    ref = client.document('users/owner/action_items/task')
    if operation in ('set', 'create', 'update'):
        getattr(ref, operation)({'completed': False})
    elif operation == 'delete':
        ref.delete()
    elif operation == 'transform':
        ref.update({'sort_order': firestore.Increment(1)})
    else:
        batch = (
            client.transaction()
            if operation == 'transaction'
            else BulkWriteBatch(client) if operation == 'bulk' else client.batch()
        )
        batch.set(ref, {'completed': False})
        if operation == 'transaction':
            batch._id = b'synthetic-transaction'
            batch._commit()
        elif operation == 'bulk':
            # BulkWriteBatch consumes the non-atomic BatchWrite response type.
            original = client._firestore_api_internal.batch_write
            client._firestore_api_internal.batch_write = lambda **kw: BatchWriteResponse(
                write_results=original(**kw).write_results
            )
            batch.commit()
        else:
            batch.commit()
    assert observations == [None]
    assert versions.version('owner') not in (None, before)
    assert versions.version('other') == other
    assert lookup()[1] is None


@pytest.mark.asyncio
@pytest.mark.parametrize('transaction', [False, True])
async def test_async_sdk_batch_and_transaction(redis, transaction):
    client = AsyncClient(project='synthetic-project', credentials=AnonymousCredentials())
    before = versions.version('owner')

    async def commit(**kwargs):
        assert versions.version('owner') is None
        return CommitResponse(write_results=[WriteResult()])

    client._firestore_api_internal = SimpleNamespace(commit=AsyncMock(side_effect=commit))
    batch = client.transaction() if transaction else client.batch()
    batch.set(client.document('users/owner/action_items/task'), {'completed': True})
    if transaction:
        batch._id = b'synthetic-transaction'
        await batch._commit()
    else:
        await batch.commit()
    assert versions.version('owner') not in (None, before)


def test_multiple_owners_and_non_task_writes(redis):
    before = {uid: versions.version(uid) for uid in ('a', 'b', 'c')}
    client = sdk_client()
    batch = client.batch()
    batch.set(client.document('users/a/action_items/one'), {})
    batch.delete(client.document('users/b/action_items/two'))
    batch.set(client.document('users/c/conversations/three'), {})
    batch.commit()
    assert versions.version('a') != before['a']
    assert versions.version('b') != before['b']
    assert versions.version('c') == before['c']


def test_overlapping_writes_partial_failure_and_late_fill(redis):
    request, _ = lookup()
    old = versions.version('owner')
    one, two = versions.begin('owner'), versions.begin('owner')
    assert versions.version('owner') is None
    versions.finish('owner', one)
    assert versions.version('owner') is None
    versions.finish('owner', two)
    assert versions.version('owner') not in (old, None)
    fill(request)  # A delayed pre-write origin cannot populate the new version.
    assert not cache._client.entries
    request, _ = lookup()
    fill(request)
    with pytest.raises(RuntimeError, match='ambiguous'):
        sdk_client(fails=True).document('users/owner/action_items/a').delete()
    assert lookup()[1] is None


def test_unknown_begin_poison_and_version_eviction_never_alias(redis):
    old = versions.version('owner')
    versions.finish('owner', ('unknown-ticket', False))
    assert versions.version('owner') is None
    redis.flushall()
    assert versions.version('owner') not in (old, None)


def test_orphan_writer_stays_fail_closed_after_a_later_confirmed_write(redis):
    versions.begin('owner')  # Model a crashed writer whose durable result is uncertain.
    later = versions.begin('owner')
    versions.finish('owner', later)
    key = versions._key('owner')
    assert redis.ttl(key + ':writers') == -1
    assert versions.version('owner') is None
    assert lookup()[1] is None
    assert getattr(lookup()[0].state, 'external_list_cache_entry', None) is None


def test_long_ttl_flag_and_write_when_reader_flag_off(redis, monkeypatch):
    request, _ = lookup()
    entry = request.state.external_list_cache_entry
    assert entry.ttl == 900
    fill(request)
    monkeypatch.setenv('OMI_DEV_ACTION_ITEMS_VERSION_CACHE_ENABLED', 'false')
    assert lookup()[1] is None
    assert lookup()[0].state.external_list_cache_entry.ttl == 10
    sdk_client().document('users/owner/action_items/a').set({})
    monkeypatch.delenv('OMI_DEV_ACTION_ITEMS_VERSION_CACHE_ENABLED')
    assert lookup()[1] is None


def test_unavailable_version_bypasses_without_retrying_origin(redis, monkeypatch):
    def fail():
        raise ConnectionError('offline')

    monkeypatch.setattr(versions, '_redis', fail)
    request, hit = lookup()
    assert hit is None and getattr(request.state, 'external_list_cache_entry', None) is None
    # Optional Redis cannot change the durable SDK result.
    sdk_client().document('users/owner/action_items/a').set({})


def test_60_second_polls_survive_short_ttl_and_expire_at_15_minutes(redis, monkeypatch):
    now = SimpleNamespace(seconds=1000.0)
    monkeypatch.setattr(cache, 'time', SimpleNamespace(time=lambda: now.seconds, monotonic=lambda: now.seconds))
    request, _ = lookup()
    fill(request)
    for elapsed in (60, 120, 300, 899):
        now.seconds = 1000 + elapsed
        assert lookup()[1].body == b'[]'
    now.seconds = 1900
    assert lookup()[1] is None


@pytest.mark.asyncio
async def test_async_document_delete_uses_direct_commit_fence(redis):
    client = AsyncClient(project='synthetic-project', credentials=AnonymousCredentials())
    before = versions.version('owner')

    async def commit(**kwargs):
        assert versions.version('owner') is None
        return CommitResponse()

    client._firestore_api_internal = SimpleNamespace(commit=AsyncMock(side_effect=commit))
    await client.document('users/owner/action_items/task').delete()
    assert versions.version('owner') not in (before, None)


def test_identical_patch_keeps_cached_page_but_real_sdk_write_invalidates(redis, monkeypatch):
    reads = []
    bumps = []
    client = sdk_client()
    monkeypatch.setattr(action_items, 'db', client)
    monkeypatch.setattr(action_items, 'bump_action_items_list_version', lambda uid: bumps.append(uid))

    def get(ref, **kwargs):
        reads.append(ref.path)
        return SimpleNamespace(exists=True, to_dict=lambda: {'description': 'Task'})

    monkeypatch.setattr(DocumentReference, 'get', get)
    request, _ = lookup()
    fill(request)
    before = versions.version('owner')
    assert action_items.update_action_item('owner', 'task', {'description': 'Task'}) is True
    assert reads == ['users/owner/action_items/task']
    assert versions.version('owner') == before and lookup()[1].body == b'[]'
    assert bumps == []
    assert action_items.update_action_item('owner', 'task', {'description': 'Changed'}) is True
    assert len(reads) == 2  # one already-required read per update; no extra lookup
    assert versions.version('owner') != before and lookup()[1] is None
    assert bumps == ['owner']
