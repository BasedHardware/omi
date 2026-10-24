"""Actual SDK surfaces: atomic projection writes and unchanged-poll read counts."""

import copy
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI, Depends, Request, Response, HTTPException
from fastapi.testclient import TestClient
from google.auth.credentials import AnonymousCredentials
from google.cloud import firestore
from google.cloud.firestore_v1 import _helpers
from google.cloud.firestore_v1.async_client import AsyncClient
from google.cloud.firestore_v1.types import CommitResponse, DocumentTransform, WriteResult, Write

from database import _client, list_projection as projection, action_item_versions
from database import list_projection_head, legal_holds, user_data_deletion, batch_pipeline_purge, users
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
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
                if transform.field_path == 'platforms_used':
                    values = [
                        _helpers.decode_value(value, client) for value in transform.append_missing_elements.values
                    ]
                    existing = after[path].setdefault('platforms_used', [])
                    existing.extend(value for value in values if value not in existing)
                else:
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


@pytest.mark.parametrize('operation', ['merge', 'update', 'transform'])
def test_telemetry_only_root_masks_and_transforms_add_no_projection_writes(store, operation):
    root = store.client.document('users/owner')
    batch = store.client.batch()
    data = {'last_active_at': firestore.SERVER_TIMESTAMP, 'platforms_used': firestore.ArrayUnion(['mobile'])}
    if operation == 'merge':
        batch.set(root, data, merge=True)
    elif operation == 'update':
        batch.update(root, data)
    else:
        batch._write_pbs.append(
            Write(
                transform=DocumentTransform(
                    document=root._document_path,
                    field_transforms=[
                        DocumentTransform.FieldTransform(field_path='last_active_at', set_to_server_value=1)
                    ],
                )
            )
        )
    source = copy.deepcopy(batch._write_pbs)
    assert projection.project_writes(batch._write_pbs) is batch._write_pbs
    assert batch._write_pbs == source


@pytest.mark.parametrize('operation', ['replace', 'create', 'mixed', 'unknown', 'nested', 'delete', 'transform'])
def test_root_fences_unknown_fields_and_replacements_still_invalidate_both_families(store, operation):
    root = store.client.document('users/owner')
    batch = store.client.batch()
    if operation == 'delete':
        batch.delete(root)
    elif operation == 'replace':
        batch.set(root, {'last_active_platform': 'mobile'})
    elif operation == 'create':
        batch.create(root, {'last_active_platform': 'mobile'})
    elif operation == 'transform':
        batch.set(root, {'last_active_platform': 'mobile', 'subscription': firestore.SERVER_TIMESTAMP}, merge=True)
    else:
        payload = {
            'mixed': {'last_active_platform': 'mobile', 'subscription': {'plan': 'free'}},
            'unknown': {'future_list_policy': True},
            'nested': {'last_active_platform.policy': False},
        }[operation]
        batch.update(root, payload)
    source = copy.deepcopy(batch._write_pbs)
    expanded = projection.project_writes(batch._write_pbs)
    assert expanded[: len(source)] == source
    assert len(expanded) == len(source) + 2
    for family in ['conversations', 'action_items']:
        head = f'{root._document_path}/{projection.STATE_COLLECTION}/{family}'
        assert any((write.delete if operation == 'delete' else write.update.name) == head for write in expanded)


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


class CountedQuery:
    """Count documents actually consumed by the production list collector."""

    def __init__(self, store, *, count=100, offset=0):
        self.store, self.count, self.skip = store, count, offset

    def limit(self, count):
        return CountedQuery(self.store, count=min(self.count, count), offset=self.skip)

    def offset(self, offset):
        return CountedQuery(self.store, count=self.count, offset=offset)

    def stream(self, **kwargs):
        for index in range(self.skip, min(100, self.skip + self.count)):
            self.store.reads += 1
            key = 'legacy' if index == 99 else f'row-{index}'
            row = {'id': key, 'status': 'completed', 'discarded': False}
            yield SimpleNamespace(id=key, to_dict=lambda row=row: copy.deepcopy(row))


def make_app(store, *, truncated=False, mutate=False, platform_telemetry=False):
    app = FastAPI()

    def auth(request: Request):
        if request.headers.get('authorization') != 'synthetic-key':
            raise HTTPException(401)
        uid = request.headers.get('x-owner', 'owner')
        if platform_telemetry:
            users.record_user_platform(uid, request.headers.get('x-app-platform'))
        return uid

    @app.get('/v1/conversations')
    def listing(request: Request, response: Response, uid: str = Depends(auth)):
        check = checks.ListVersionCheck.start(request, uid, 'conversations')
        if check.not_modified is not None:
            return check.not_modified
        store.queries += 1
        rows = conversation_routes.conversations_db._collect_visible_conversation_page(
            CountedQuery(store),
            limit=100,
            offset=0,
            include_discarded=False,
            uid=uid,
        )
        if mutate:
            store.client.document(f'users/{uid}/conversations/racing').set({'status': 'processing'})
        check.finish(response, truncated=truncated)
        return rows

    return TestClient(app)


def test_http_equivalence_unchanged_poll_one_read_no_query_and_auth_preserved(store):
    store.client.document('users/owner/conversations/one').set({'status': 'completed'})
    client = make_app(store)
    headers = {'authorization': 'synthetic-key', 'if-none-match': 'legacy-validator'}
    first = client.get('/v1/conversations', headers=headers)
    assert first.status_code == 200
    assert len(first.json()) == 100
    assert first.json()[-1] == {'id': 'legacy', 'status': 'completed', 'discarded': False}
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


@pytest.mark.parametrize('platform', ['ios', 'macos', 'web'])
def test_auth_platform_telemetry_keeps_both_versions_and_warm_poll_bypass(store, monkeypatch, platform):
    root = store.client.document('users/owner')
    root.set({'subscription': {'plan': 'free'}})
    store.client.document('users/owner/conversations/one').set({'status': 'completed'})
    heads = {path: copy.deepcopy(row) for path, row in store.rows.items() if projection.STATE_COLLECTION in path}
    monkeypatch.setattr(users, 'db', store.client)
    # Model Redis being unavailable: every auth request writes telemetry.
    monkeypatch.setattr(users, 'try_acquire_user_platform_write_lock', lambda *args: True)

    def snapshot(reference, *args, **kwargs):
        store.reads += 1
        return SimpleNamespace(exists=True, to_dict=lambda: copy.deepcopy(store.rows[reference._document_path]))

    monkeypatch.setattr(type(root), 'get', snapshot)
    client = make_app(store, platform_telemetry=True)
    headers = {'authorization': 'synthetic-key', 'if-none-match': 'legacy', 'x-app-platform': platform}
    first = client.get('/v1/conversations', headers=headers)
    assert first.status_code == 200 and len(first.json()) == 100
    assert len(store.commits[-1]) == 1  # Only the original auth telemetry write.
    assert 'signup_platform' in store.rows[root._document_path]
    before = store.reads
    headers['if-none-match'] = first.headers['etag']
    second = client.get('/v1/conversations', headers=headers)
    assert second.status_code == 304 and store.queries == 1
    assert store.reads == before + 2  # Existing auth read + one marker; zero list reads.
    assert len(store.commits[-1]) == 1
    assert {path: store.rows[path] for path in heads} == heads
    root.update({'subscription': {'plan': 'changed'}})
    assert client.get('/v1/conversations', headers=headers).status_code == 200
    assert store.queries == 2


@pytest.mark.parametrize('truncated,mutate', [(True, False), (False, True)])
def test_partial_or_racing_source_response_never_gets_validator(store, truncated, mutate):
    store.client.document('users/owner/conversations/one').set({'status': 'completed'})
    result = make_app(store, truncated=truncated, mutate=mutate).get(
        '/v1/conversations', headers={'authorization': 'synthetic-key', 'if-none-match': 'legacy-validator'}
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

    monkeypatch.setattr(_client, 'get_firestore_client', Reference)
    assert checks._version('synthetic-owner', 'conversations') == 'a' * 32
    assert calls == ['users', 'synthetic-owner', projection.STATE_COLLECTION, 'conversations']
    monkeypatch.setattr(Reference, 'get', lambda *a, **k: (_ for _ in ()).throw(RuntimeError('offline')))
    assert checks._version('synthetic-owner', 'conversations') is None


@pytest.mark.parametrize('race', [False, True])
def test_missing_version_baseline_is_create_only_and_cannot_overwrite_writer(monkeypatch, race):
    path = ('users', 'owner', projection.STATE_COLLECTION, 'conversations')
    database = StrictFirestore({path: {'version': 'a' * 32}} if race else {})
    factory = database.transaction
    monkeypatch.setattr(database, 'transaction', lambda **kw: factory())
    value = list_projection_head.initialize_head('owner', 'conversations', firestore_client=database)
    assert value == database.rows[path]['version']
    transaction = database.transactions[-1]
    assert len(transaction.creates) == (0 if race else 1)
    assert value == 'a' * 32 if race else len(value) == 32


@pytest.mark.parametrize('blocked_by', ['account_deletion', 'destructive_operation'])
def test_baseline_uses_existing_transactional_deletion_authority(monkeypatch, blocked_by):
    rows = (
        {('account_deletions', 'owner'): {'wipe_status': 'in_progress'}}
        if blocked_by == 'account_deletion'
        else {
            ('legal_hold_deletion_gates', 'owner'): {
                'schema_version': 'legal_hold_deletion_gate.v1',
                'uid': 'owner',
                'kind': 'account_deletion',
                'token': 'synthetic',
                'state': 'running',
                'started_at': datetime.now(timezone.utc),
                'finished_at': None,
            }
        }
    )
    database = StrictFirestore(rows)
    factory = database.transaction
    monkeypatch.setattr(database, 'transaction', lambda **kw: factory())
    with pytest.raises(legal_holds.DestructiveOperationInProgress):
        list_projection_head.initialize_head('owner', 'conversations', firestore_client=database)
    assert not database.transactions[-1].creates
    assert database.rows == rows


def test_root_delete_clears_heads_instead_of_recreating_them(store):
    user = store.client.document('users/owner')
    user.set({'language': 'en'})
    assert checks._version('owner', 'conversations')
    user.delete()
    assert checks._version('owner', 'conversations') is None
    assert checks._version('owner', 'action_items') is None
    assert all(write.delete for write in store.commits[-1])


def test_recursive_wipe_closes_head_recreation_when_user_root_already_missing(monkeypatch):
    rows = {
        projection.STATE_COLLECTION: {'conversations': {}, 'action_items': {}},
        'conversations': {'one': {}},
        'action_items': {'one': {}},
    }

    def collection(name):
        return SimpleNamespace(document=lambda key: SimpleNamespace(delete=lambda: rows.get(name, {}).pop(key, None)))

    root = SimpleNamespace(
        get=lambda: SimpleNamespace(exists=False),
        collection=collection,
        collections=lambda: [SimpleNamespace(id=name) for name in rows],
    )
    client = SimpleNamespace(collection=lambda name: SimpleNamespace(document=lambda key: root))
    monkeypatch.setattr(batch_pipeline_purge, 'purge_batch_owner', lambda uid: None)
    monkeypatch.setattr(
        user_data_deletion,
        'get_data_plane_firestore_client',
        lambda: SimpleNamespace(
            collection=lambda name: SimpleNamespace(document=lambda key: SimpleNamespace(delete=lambda: None))
        ),
    )

    def recursive(subcollection, **kwargs):
        rows[subcollection.id].clear()
        if subcollection.id in projection.ROW_COLLECTIONS:
            # Model atomic source-delete hooks running after the heads were
            # walked, the worst collection-enumeration order for an erase.
            rows[projection.STATE_COLLECTION][subcollection.id] = {'version': 'rotated'}

    retirements = []
    monkeypatch.setattr(
        user_data_deletion,
        'stop_quiet_checks_for_account',
        lambda uid, **kwargs: retirements.append((uid, kwargs['firestore_client'])),
    )
    assert user_data_deletion.purge_user_subtree('owner', client, recursive)['status'] == 'ok'
    assert retirements == [('owner', client)]
    assert all(not values for values in rows.values())


def test_release_and_epoch_rotation_invalidate_existing_validator(store, monkeypatch):
    store.client.document('users/owner/conversations/one').set({'status': 'completed'})
    client = make_app(store)
    headers = {'authorization': 'synthetic-key', 'if-none-match': 'legacy-validator'}
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


@pytest.mark.parametrize('mutate', [False, True])
def test_no_header_conversation_polls_add_zero_reads_and_initial_tag_never_shortcuts_source(store, mutate):
    store.client.document('users/owner/conversations/one').set({'status': 'completed'})
    client = make_app(store, mutate=mutate)
    headers = {'authorization': 'synthetic-key'}
    first = client.get('/v1/conversations', headers=headers)
    second = client.get('/v1/conversations', headers=headers)
    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()
    assert first.headers['etag'].startswith('W/"lp0-')
    assert first.headers['etag'] != second.headers['etag']
    assert store.reads == 200 and store.queries == 2  # source only, no marker lookups
    # Even a tag emitted across a source mutation cannot cause a false 304.
    client = make_app(store)
    headers['if-none-match'] = first.headers['etag']
    graduated = client.get('/v1/conversations', headers=headers)
    assert graduated.status_code == 200 and graduated.json() == first.json()
    assert graduated.headers['etag'].startswith('W/"lp1-')
    assert store.reads == 302 and store.queries == 3
    headers['if-none-match'] = graduated.headers['etag']
    assert client.get('/v1/conversations', headers=headers).status_code == 304
    assert store.reads == 303 and store.queries == 3


def test_per_request_proxy_trace_does_not_break_unchanged_poll(store):
    store.client.document('users/owner/conversations/one').set({'status': 'completed'})
    client = make_app(store)
    headers = {
        'authorization': 'synthetic-key',
        'x-cloud-trace-context': 'trace-one',
        'if-none-match': 'legacy-validator',
    }
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
    graduated = Response()
    assert conversation_routes.get_conversations(response=graduated, **params) == rows
    assert graduated.headers['etag'].startswith('W/"lp1-')
    params['request'] = Request(
        {
            'type': 'http',
            'path': '/v1/conversations',
            'query_string': b'',
            'headers': [(b'if-none-match', graduated.headers['etag'].encode())],
        }
    )
    assert conversation_routes.get_conversations(response=Response(), **params).status_code == 304
    assert calls == ['source', 'heal'] * 4
