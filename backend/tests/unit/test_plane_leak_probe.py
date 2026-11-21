"""Hermetic real SDK probe paths: no credentials, emulator, or network."""

import asyncio
import sys
from types import SimpleNamespace

import pytest
from google.auth.credentials import AnonymousCredentials
from google.cloud import firestore
from google.cloud.firestore_v1.document import DocumentReference
from google.cloud.firestore_v1.services.firestore import FirestoreClient
from google.cloud.firestore_v1.types import BatchWriteResponse, CommitResponse
from google.rpc.status_pb2 import Status

from database import firestore_document_probe as reads
from database import firestore_write_probe as writes
from database import plane_leak_probe as probe
from database.directory import router as directory_router
from database.firestore_read_origin import read_origin
from utils.log_sanitizer import hash_log_identifier
from utils.other import plane_routing as routing

CELL_UID = 'private-cell-owner'
ORIGIN = 'job:plane_leak_test'


@pytest.fixture(autouse=True)
def cell_owner(monkeypatch):
    monkeypatch.setenv('OMI_ENV_STAGE', 'offline')
    monkeypatch.setenv('PLANE_LEAK_TEST_CELL_UIDS', f' {CELL_UID}, ,{CELL_UID} ')
    monkeypatch.setattr(routing, '_TEST_CELL_UIDS', routing._load_test_cell_uids())
    with read_origin(ORIGIN):
        yield


def count(op, collection):
    return probe.PLANE_LEAK.labels(op=op, collection=collection, origin=ORIGIN)._value.get()


@pytest.mark.parametrize('stage', ['prod', 'production', 'dev', ''])
def test_override_refused_outside_harness(monkeypatch, stage):
    monkeypatch.setenv('OMI_ENV_STAGE', stage)
    with pytest.raises(RuntimeError, match='requires a local, offline, or test stage'):
        routing._load_test_cell_uids()


@pytest.mark.parametrize('stage', ['local', 'offline', 'test'])
def test_override_allowed_only_in_explicit_harness(monkeypatch, stage):
    monkeypatch.setenv('OMI_ENV_STAGE', stage)
    assert routing._load_test_cell_uids() == frozenset({CELL_UID})


def test_default_and_nested_request_planes_restore_on_error(monkeypatch):
    monkeypatch.setattr(routing, '_TEST_CELL_UIDS', frozenset())
    assert routing.plane_for(CELL_UID) == 'firestore'
    with routing.plane_context(CELL_UID, 'cell'):
        assert routing.plane_for(CELL_UID) == 'cell'
        assert routing.plane_for('other') == 'firestore'
        with pytest.raises(ValueError), routing.plane_context(CELL_UID, 'firestore'):
            assert routing.plane_for(CELL_UID) == 'firestore'
            raise ValueError('abort request')
        assert routing.plane_for(CELL_UID) == 'cell'
    assert not routing.has_cell_plane()


def test_concurrent_request_planes_are_isolated():
    async def request(plane):
        with routing.plane_context('request-owner', plane):
            await asyncio.sleep(0)
            return routing.plane_for('request-owner')

    async def run():
        return await asyncio.gather(request('cell'), request('firestore'))

    assert asyncio.run(run()) == ['cell', 'firestore']


def test_request_binding_detects_leaks_without_test_override(monkeypatch):
    monkeypatch.setattr(routing, '_TEST_CELL_UIDS', frozenset())
    before = count('read', 'memories')
    with routing.plane_context(CELL_UID, 'cell'):
        reads._record(('users', CELL_UID, 'memories', 'm'), True)
    reads._record(('users', CELL_UID, 'memories', 'm'), True)
    assert count('read', 'memories') == before + 1


def test_disabled_gate_does_not_parse_path_or_resolve_owner(monkeypatch):
    monkeypatch.setattr(routing, '_TEST_CELL_UIDS', frozenset())

    def unexpected(*args):
        pytest.fail('disabled probe performed work')

    monkeypatch.setattr(routing, 'plane_for', unexpected)
    monkeypatch.setattr(probe, 'hash_log_identifier', unexpected)

    class UnreadablePath:
        def __iter__(self):
            unexpected()

    probe.record_plane_leak(UnreadablePath(), 'read')


@pytest.mark.parametrize(
    'uid,collection,delta',
    [
        (CELL_UID, 'conversations', 1),
        (CELL_UID, 'memory_items', 1),
        (CELL_UID, 'goals', 1),
        (CELL_UID, 'workstreams', 1),
        (CELL_UID, 'messages', 1),
        (CELL_UID, 'chat_sessions', 1),
        ('firestore-owner', 'conversations', 0),
        (CELL_UID, 'fcm_tokens', 0),
    ],
)
def test_sdk_lookup_counts_only_routed_cell_data(monkeypatch, caplog, uid, collection, delta):
    snapshot = SimpleNamespace(exists=True)
    monkeypatch.setattr(DocumentReference, 'get', reads._wrap_lookup_get(lambda *a, **k: snapshot))
    db = firestore.Client(project='plane-probe-test', credentials=AnonymousCredentials())
    before = count('read', collection)
    assert db.document(f'users/{uid}/{collection}/private-document').get() is snapshot
    assert count('read', collection) == before + delta
    assert uid not in caplog.text
    assert 'private-document' not in caplog.text
    if delta:
        assert len(caplog.records) == 1
        assert hash_log_identifier(uid) in caplog.text


def test_cell_owner_lookup_miss_counts(monkeypatch):
    # A correctly routed owner mostly misses in Firestore; a miss is still a leak.
    monkeypatch.setattr(DocumentReference, 'get', reads._wrap_lookup_get(lambda *a, **k: SimpleNamespace(exists=False)))
    db = firestore.Client(project='plane-probe-test', credentials=AnonymousCredentials())
    before = count('read', 'conversations')
    db.document(f'users/{CELL_UID}/conversations/missing').get()
    assert count('read', 'conversations') == before + 1


def test_empty_collection_query_and_nested_data_are_detected():
    before = count('read', 'conversations')
    reads._finish_query(('users', CELL_UID, 'conversations'), 'test', 0, 0)
    reads._record(('users', CELL_UID, 'conversations', 'c', 'photos', 'p'), True)
    assert count('read', 'conversations') == before + 2


@pytest.mark.parametrize('method', ['commit', 'batch_write'])
def test_real_sdk_writes_count_only_successes(monkeypatch, method):
    def transport(*args, **kwargs):
        return CommitResponse() if method == 'commit' else BatchWriteResponse(status=[Status(), Status(code=7)])

    monkeypatch.setattr(FirestoreClient, method, writes._wrap(transport, partial=method == 'batch_write'))
    db = firestore.Client(project='plane-probe-test', credentials=AnonymousCredentials())
    db._firestore_api_internal = FirestoreClient(credentials=AnonymousCredentials())
    first = f'users/{CELL_UID}/action_items/task'
    second = f'users/{CELL_UID}/memories/memory'
    batch = db.batch()
    batch.set(db.document(first), {'content': 'never logged'})
    batch.set(db.document(second), {'content': 'never logged'})
    before = count('write', 'action_items'), count('write', 'memories')
    if method == 'commit':
        batch.commit()
    else:
        db._firestore_api.batch_write(request={'writes': batch._write_pbs})
    assert count('write', 'action_items') == before[0] + 1
    assert count('write', 'memories') == before[1] + (method == 'commit')

    def fail(*args, **kwargs):
        raise RuntimeError('rejected')

    monkeypatch.setattr(FirestoreClient, method, writes._wrap(fail, partial=method == 'batch_write'))
    after = count('write', 'action_items')
    with pytest.raises(RuntimeError, match='rejected'):
        getattr(db._firestore_api, method)(request={'writes': batch._write_pbs})
    assert count('write', 'action_items') == after


@pytest.mark.parametrize('op', ['read', 'write'])
@pytest.mark.parametrize(
    'path',
    [
        ('users', 'firestore-owner', 'memories', 'm'),
        ('users', CELL_UID, 'fcm_tokens', 't'),
        ('users', CELL_UID),
        ('memories', 'm'),
    ],
)
def test_unrouted_access_never_creates_leak_series(monkeypatch, op, path):
    def unexpected(*args, **kwargs):
        pytest.fail('unrouted access reached metrics')

    monkeypatch.setattr(probe, 'PLANE_LEAK', SimpleNamespace(labels=unexpected))
    probe.record_plane_leak(path, op)


def test_telemetry_fault_does_not_break_access(monkeypatch):
    def fail(**kwargs):
        raise RuntimeError('telemetry unavailable')

    monkeypatch.setattr(probe, 'PLANE_LEAK', SimpleNamespace(labels=fail))
    reads._record(('users', CELL_UID, 'memories', 'm'), True)
    writes._record([{'delete': f'projects/p/databases/(default)/documents/users/{CELL_UID}/memories/m'}], 'test')


def test_directory_cache_supplies_plane_without_request_context(monkeypatch):
    monkeypatch.setenv('DIRECTORY_ROUTING_MODE', 'new_owners')
    monkeypatch.setattr(routing, '_TEST_CELL_UIDS', frozenset())
    monkeypatch.setattr(directory_router, '_cache', {})
    directory_router._remember(CELL_UID, 'cell')
    assert routing.plane_for(CELL_UID) == 'cell'
    before = count('read', 'memories')
    reads._record(('users', CELL_UID, 'memories', 'm'), True)
    assert count('read', 'memories') == before + 1
    with routing.plane_context(CELL_UID, 'firestore'):
        assert routing.plane_for(CELL_UID) == 'firestore'
    monkeypatch.setenv('DIRECTORY_ROUTING_MODE', 'off')
    assert routing.plane_for(CELL_UID) == 'firestore'
    assert not routing.has_cell_plane()


def test_probe_lookup_never_initializes_a_missing_or_partial_router(monkeypatch):
    monkeypatch.setenv('DIRECTORY_ROUTING_MODE', 'new_owners')
    monkeypatch.setattr(routing, '_TEST_CELL_UIDS', frozenset())
    monkeypatch.delitem(sys.modules, 'database.directory.router', raising=False)
    assert routing.plane_for(CELL_UID) == 'firestore'
    assert 'database.directory.router' not in sys.modules
    monkeypatch.setitem(sys.modules, 'database.directory.router', SimpleNamespace())
    assert routing.plane_for(CELL_UID) == 'firestore'
