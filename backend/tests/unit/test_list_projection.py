"""Actual SDK surfaces: atomic projection writes and unchanged-poll read counts."""

import copy
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI, Depends, Request, Response, HTTPException
from fastapi.testclient import TestClient
from google.auth.credentials import AnonymousCredentials
from google.cloud import firestore
from google.cloud.firestore_v1 import _helpers
from google.cloud.firestore_v1.async_client import AsyncClient
from google.cloud.firestore_v1.types import CommitResponse, WriteResult, Write

from database import list_projection as projection, action_item_versions
from utils import list_version_check as checks
from routers import conversations as conversation_routes


@pytest.fixture
def store(monkeypatch):
    # Record SDK transport writes without relaxing source transaction semantics.
    state = SimpleNamespace(rows={}, reads=0, queries=0, commits=[], fail=False)
    client = firestore.Client(project='synthetic-project', credentials=AnonymousCredentials())

    def commit(request, **kwargs):
        state.commits.append(copy.deepcopy(request['writes']))
        if state.fail:
            raise RuntimeError('commit rejected atomically')
        after = copy.deepcopy(state.rows)
        for write in request['writes']:
            path = write.delete or write.update.name
            if write.delete:
                after.pop(path, None)
                continue
            if write.current_document.exists and path not in after:
                raise RuntimeError('source update requires existence')
            data = _helpers.decode_dict(write.update.fields, client)
            if Write.pb(write).HasField('update_mask'):
                row = after.setdefault(path, {})
                for field in write.update_mask.field_paths:
                    if field in data:
                        row[field] = data[field]
                    else:
                        row.pop(field, None)
            else:
                after[path] = data
            for transform in write.update_transforms:
                assert transform.field_path == 'sort_order'
                after[path]['sort_order'] = after[path].get('sort_order', 0) + transform.increment.integer_value
        state.rows = after
        return CommitResponse(write_results=[WriteResult() for _ in request['writes']])

    client._firestore_api_internal = SimpleNamespace(commit=commit)
    projection.install_list_projection_writer()
    # Avoid installing unrelated Redis fences while testing this writer; SDK
    # classes already wrapped by _client keep their normal public contract.
    monkeypatch.setattr(action_item_versions, 'begin', lambda uid: ('ticket', True))
    monkeypatch.setattr(action_item_versions, 'finish', lambda uid, ticket: None)

    def read_version(uid, family):
        state.reads += 1
        path = client.document(f'users/{uid}/{projection.STATE_COLLECTION}/{family}')._document_path
        return state.rows.get(path, {}).get('version')

    monkeypatch.setattr(checks, '_version', read_version)
    monkeypatch.setenv('OMI_LIST_VERSION_EPOCH', 'synthetic-complete-writer-rollout')
    monkeypatch.setenv('OMI_BACKEND_RELEASE_SHA', 'a' * 40)
    monkeypatch.delenv('OMI_LIST_PROJECTION_WRITER_ENABLED', raising=False)
    state.client = client
    return state


@pytest.mark.parametrize('family', ['conversations', 'action_items'])
@pytest.mark.parametrize('operation', ['set', 'create', 'update', 'delete', 'batch', 'transaction'])
def test_sdk_source_and_projection_are_atomic_and_results_unchanged(store, family, operation):
    source = store.client.document(f'users/owner/{family}/one')
    source.set({'status': 'active', 'sort_order': 1, 'transcript_segments': 'sensitive', 'description': 'private'})
    before = checks._version('owner', family)
    row = store.client.document(f'users/owner/{projection.ROW_COLLECTIONS[family]}/one')._document_path
    assert store.rows[row] == {'status': 'active', 'sort_order': 1}
    if operation in {'set', 'create'}:
        ref = store.client.document(f'users/owner/{family}/two')
        getattr(ref, operation)({'status': 'completed'})
    elif operation == 'update':
        source.update({'sort_order': firestore.Increment(2), 'status': firestore.DELETE_FIELD})
        assert store.rows[row] == {'sort_order': 3}
    elif operation == 'delete':
        source.delete()
        assert row not in store.rows
    else:
        batch = store.client.transaction() if operation == 'transaction' else store.client.batch()
        batch.update(source, {'status': 'completed'})
        if operation == 'transaction':
            batch._id = b'synthetic-tx'
            results = batch._commit()
        else:
            results = batch.commit()
        assert len(results) == len(batch.write_results) == 1
        assert store.rows[row]['status'] == 'completed'
    assert checks._version('owner', family) != before
    # No row contents or source preconditions are read to maintain the projection.
    assert store.reads == 2


def test_failed_commit_preserves_version_source_and_retry_payload(store):
    source = store.client.document('users/owner/conversations/one')
    source.set({'status': 'processing'})
    before = copy.deepcopy(store.rows)
    batch = store.client.batch()
    batch.update(source, {'status': 'completed'})
    original = copy.deepcopy(batch._write_pbs)
    store.fail = True
    with pytest.raises(RuntimeError, match='atomically'):
        batch.commit()
    assert store.rows == before
    assert batch._write_pbs == original
    first_version = store.commits[-1][-1].update.fields['version'].string_value
    store.fail = False
    assert len(batch.commit()) == 1
    assert store.commits[-1][-1].update.fields['version'].string_value != first_version


def test_partial_legacy_update_never_claims_complete_coverage_and_ignores_content(store):
    source = store.client.document('users/owner/conversations/legacy')
    store.rows[source._document_path] = {'status': 'processing', 'created_at': 'old', 'transcript_segments': 'bytes'}
    source.update({'status': 'completed'})
    row = store.client.document('users/owner/conversation_list_rows/legacy')._document_path
    assert store.rows[row] == {'status': 'completed'}
    assert 'created_at' not in store.rows[row]
    source.update({'transcript_segments': 'new bytes'})
    assert store.rows[row] == {'status': 'completed'}
    assert len(store.commits[-1]) == 2  # source + owner version; no transcript row copy


def test_owner_family_nested_corrections_and_account_invalidation(store):
    a = store.client.document('users/a/conversations/one')
    a.set({'status': 'completed'})
    a_version = checks._version('a', 'conversations')
    b = store.client.document('users/b/action_items/one')
    b.set({'completed': False})
    b_version = checks._version('b', 'action_items')
    a.collection('corrections').document('one').set({'text': 'private'})
    assert checks._version('a', 'conversations') != a_version
    assert checks._version('b', 'action_items') == b_version
    before = checks._version('b', 'conversations')
    store.client.document('users/b').set({'subscription': 'changed'})
    assert checks._version('b', 'conversations') != before
    assert checks._version('b', 'action_items') != b_version


@pytest.mark.asyncio
@pytest.mark.parametrize('transaction', [False, True])
async def test_async_sdk_contract(store, transaction):
    client = AsyncClient(project='synthetic-project', credentials=AnonymousCredentials())

    async def commit(request, **kwargs):
        assert len(request['writes']) == 3
        return CommitResponse(write_results=[WriteResult() for _ in request['writes']])

    client._firestore_api_internal = SimpleNamespace(commit=AsyncMock(side_effect=commit))
    batch = client.transaction() if transaction else client.batch()
    batch.set(client.document('users/owner/conversations/one'), {'status': 'completed'})
    if transaction:
        batch._id = b'synthetic-tx'
        result = await batch._commit()
    else:
        result = await batch.commit()
    assert len(result) == len(batch.write_results) == 1


def make_app(store, *, truncated=False, mutate=False):
    app = FastAPI()

    def auth(request: Request):
        if request.headers.get('authorization') != 'synthetic-key':
            raise HTTPException(401)
        return request.headers.get('x-owner', 'owner')

    @app.get('/v1/conversations')
    def listing(request: Request, response: Response, uid: str = Depends(auth)):
        check = checks.ListVersionCheck.start(request, uid, 'conversations')
        if check.not_modified is not None:
            return check.not_modified
        store.queries += 1
        store.reads += 100  # real source list equivalent, including legacy rows
        if mutate:
            store.client.document(f'users/{uid}/conversations/racing').set({'status': 'processing'})
        check.finish(response, truncated=truncated)
        return [{'id': 'legacy', 'status': 'completed'}]

    return TestClient(app)


def test_http_equivalence_unchanged_poll_one_read_no_query_and_auth_preserved(store):
    store.client.document('users/owner/conversations/one').set({'status': 'completed'})
    client = make_app(store)
    headers = {'authorization': 'synthetic-key'}
    first = client.get('/v1/conversations', headers=headers)
    assert first.status_code == 200
    assert first.json() == [{'id': 'legacy', 'status': 'completed'}]
    assert store.reads == 102 and store.queries == 1
    headers['if-none-match'] = first.headers['etag']
    second = client.get('/v1/conversations', headers=headers)
    assert second.status_code == 304 and second.content == b''
    assert store.reads == 103 and store.queries == 1  # 100 -> 1, auth still runs
    assert client.get('/v1/conversations', headers={'if-none-match': headers['if-none-match']}).status_code == 401
    store.client.document('users/owner/conversations/one').update({'deleted': True})
    assert client.get('/v1/conversations', headers=headers).status_code == 200
    assert store.queries == 2
    assert client.get('/v1/conversations?offset=1', headers=headers).status_code == 200
    assert client.get('/v1/conversations', headers={**headers, 'x-owner': 'other'}).status_code == 200


@pytest.mark.parametrize('truncated,mutate', [(True, False), (False, True)])
def test_partial_or_racing_source_response_never_gets_validator(store, truncated, mutate):
    store.client.document('users/owner/conversations/one').set({'status': 'completed'})
    result = make_app(store, truncated=truncated, mutate=mutate).get(
        '/v1/conversations', headers={'authorization': 'synthetic-key'}
    )
    assert result.status_code == 200 and 'etag' not in result.headers


@pytest.mark.parametrize(
    'setting,value',
    [
        ('OMI_LIST_VERSION_EPOCH', ''),
        ('OMI_BACKEND_RELEASE_SHA', ''),
        ('OMI_LIST_PROJECTION_WRITER_ENABLED', 'false'),
    ],
)
def test_reader_rollback_default_behavior_and_no_extra_reads(store, monkeypatch, setting, value):
    store.client.document('users/owner/conversations/one').set({'status': 'completed'})
    monkeypatch.setenv(setting, value)
    result = make_app(store).get('/v1/conversations', headers={'authorization': 'synthetic-key', 'if-none-match': '*'})
    assert result.status_code == 200 and store.reads == 100
    assert 'etag' not in result.headers


def test_writer_kill_switch_and_idempotent_installation(store, monkeypatch):
    wrapped = firestore.WriteBatch.commit
    projection.install_list_projection_writer()
    assert firestore.WriteBatch.commit is wrapped
    monkeypatch.setenv('OMI_LIST_PROJECTION_WRITER_ENABLED', 'false')
    store.client.document('users/owner/conversations/one').set({'status': 'completed'})
    assert len(store.commits[-1]) == 1 and len(store.rows) == 1


def test_production_version_lookup_bounds_io_and_falls_back(monkeypatch):
    calls = []

    class Reference:
        def collection(self, name):
            calls.append(name)
            return self

        def document(self, name):
            calls.append(name)
            return self

        def get(self, **kwargs):
            assert kwargs == {'timeout': 1.0, 'retry': None}
            return SimpleNamespace(exists=True, to_dict=lambda: {'version': 'a' * 32})

    monkeypatch.setattr(checks, 'get_firestore_client', Reference)
    assert checks._version('synthetic-owner', 'conversations') == 'a' * 32
    assert calls == ['users', 'synthetic-owner', projection.STATE_COLLECTION, 'conversations']
    monkeypatch.setattr(Reference, 'get', lambda *a, **k: (_ for _ in ()).throw(RuntimeError('offline')))
    assert checks._version('synthetic-owner', 'conversations') is None


def test_release_and_epoch_rotation_invalidate_existing_validator(store, monkeypatch):
    store.client.document('users/owner/conversations/one').set({'status': 'completed'})
    client = make_app(store)
    headers = {'authorization': 'synthetic-key'}
    first = client.get('/v1/conversations', headers=headers)
    headers['if-none-match'] = first.headers['etag']
    monkeypatch.setenv('OMI_LIST_VERSION_EPOCH', 'new-rollout-after-writer-gap')
    assert client.get('/v1/conversations', headers=headers).status_code == 200
    monkeypatch.setenv('OMI_LIST_VERSION_EPOCH', 'synthetic-complete-writer-rollout')
    monkeypatch.setenv('OMI_BACKEND_RELEASE_SHA', 'b' * 40)
    assert client.get('/v1/conversations', headers=headers).status_code == 200


def test_no_header_action_polls_keep_old_cache_path_without_marker_reads(store):
    request = Request({'type': 'http', 'path': '/v1/action-items', 'headers': [], 'query_string': b''})
    assert not checks.ListVersionCheck.start(request, 'owner', 'action_items').active
    assert store.reads == 0


def test_per_request_proxy_trace_does_not_break_unchanged_poll(store):
    store.client.document('users/owner/conversations/one').set({'status': 'completed'})
    client = make_app(store)
    headers = {'authorization': 'synthetic-key', 'x-cloud-trace-context': 'trace-one'}
    first = client.get('/v1/conversations', headers=headers)
    headers.update({'if-none-match': first.headers['etag'], 'x-cloud-trace-context': 'trace-two'})
    assert client.get('/v1/conversations', headers=headers).status_code == 304


def test_real_conversation_route_preserves_locked_allowance_recovery(store, monkeypatch):
    store.client.document('users/owner/conversations/locked').set({'is_locked': True, 'status': 'completed'})
    rows = [{'id': 'locked', 'is_locked': True, 'status': 'completed'}]
    calls = []

    def source(*args, **kwargs):
        store.reads += 100
        calls.append('source')
        return copy.deepcopy(rows)

    def heal(uid, page):
        calls.append('heal')

    monkeypatch.setattr(conversation_routes.conversations_db, 'get_conversations_without_photos', source)
    monkeypatch.setattr(conversation_routes, '_heal_locked_conversations_if_eligible', heal)
    monkeypatch.setattr(conversation_routes, 'redact_conversations_for_list', lambda page: None)
    monkeypatch.setattr(
        conversation_routes,
        'list_read_budget_for_request',
        lambda *a, **k: SimpleNamespace(
            truncated=False,
            observe=lambda outcome: None,
        ),
    )
    request = Request({'type': 'http', 'path': '/v1/conversations', 'headers': [], 'query_string': b''})
    params = dict(
        request=request,
        uid='owner',
        limit=100,
        offset=0,
        statuses='completed',
        sources=None,
        start_date=None,
        end_date=None,
        folder_id=None,
        starred=None,
    )
    first = Response()
    assert conversation_routes.get_conversations(response=first, **params) == rows
    assert 'etag' not in first.headers  # monthly rollover must still reach heal
    assert conversation_routes.get_conversations(response=Response(), **params) == rows
    assert calls == ['source', 'heal', 'source', 'heal']
    rows[0]['is_locked'] = False
    fresh = Response()
    assert conversation_routes.get_conversations(response=fresh, **params) == rows
    assert 'etag' in fresh.headers
    conditional = Request(
        {
            'type': 'http',
            'path': '/v1/conversations',
            'query_string': b'',
            'headers': [(b'if-none-match', fresh.headers['etag'].encode())],
        }
    )
    params['request'] = conditional
    assert conversation_routes.get_conversations(response=Response(), **params).status_code == 304
    assert calls == ['source', 'heal', 'source', 'heal', 'source', 'heal']
