"""Spaces HTTP contract against private, disposable Postgres databases."""

import base64
import json
import os
import subprocess
import sys
import time
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from config import spaces_sync_api
from database.cells import CellStore, serving
from database.cells.errors import CellContentionExhausted
from database.cells.feed import DEVICE_STALE_S
from database.cells.mutations import apply_space_mutation
from database.directory import router as directory_router
from database.jobstore.connection import Pool
from routers import spaces
from testing.cells_fixtures import cells_dsn, make_cell_store, make_directory
from utils.other import endpoints as auth
from utils.rate_limit_config import RATE_POLICIES


@pytest.fixture(scope='module')
def stores():
    cell, directory = make_cell_store(), make_directory()
    yield cell, directory
    cell.close()
    directory.close()


@pytest.fixture
def api(stores, monkeypatch):
    cell, directory = stores
    sid = cell.uid('s' + str(time.time_ns()))
    directory.seeded.add(sid)
    monkeypatch.setenv('SPACES_SYNC_API_ENABLED', 'true')
    monkeypatch.setenv('DIRECTORY_ROUTING_MODE', 'new_owners')
    monkeypatch.setenv('DIRECTORY_ROUTING_NEW_OWNER_PERCENT', '0')
    monkeypatch.setattr(serving, 'cell_store', lambda: cell.store)
    monkeypatch.setattr(directory_router, 'directory_store', lambda: directory.store)
    monkeypatch.setattr(directory_router, '_cache', {})
    cache = {}
    monkeypatch.setattr(directory_router.redis_db, 'get_generic_cache', lambda key: cache.get(key))
    monkeypatch.setattr(
        directory_router.redis_db, 'set_generic_cache', lambda key, value, ttl: cache.update({key: value})
    )
    monkeypatch.setattr(directory_router.redis_db, 'delete_generic_cache', lambda key: cache.pop(key, None))
    limiter, events = Mock(), Mock()
    monkeypatch.setattr(auth, '_enforce_rate_limit', limiter)
    monkeypatch.setattr(spaces, 'record_product_event', events)
    app = FastAPI()
    app.include_router(spaces.router)
    identity = {'uid': sid}
    app.dependency_overrides[auth.get_current_user_uid] = lambda: identity['uid']
    with TestClient(app) as client:
        yield SimpleNamespace(
            cell=cell.store,
            directory=directory.store,
            sid=sid,
            client=client,
            app=app,
            identity=identity,
            limiter=limiter,
            events=events,
        )


def enroll(api, *, cell='cell1', head=True):
    api.directory.get_or_create_personal_space(api.sid, cell=cell, now=time.time())
    if head:
        api.cell.enroll_space(api.sid, now=time.time())
        api.cell.run(api.sid, lambda tx: tx.put('notes', 'a', {'text': 'original'}), actor_uid=api.sid, now=time.time())


def mutation(**overrides):
    return dict(
        entity='notes',
        entity_id='a',
        client_mutation_id='edit-1',
        base_revision=1,
        operation={'type': 'patch', 'fields': {'text': 'edited'}},
        **overrides,
    )


def request(api, endpoint, **kwargs):
    path = f'/v1/spaces/{api.sid}/{endpoint}'
    if endpoint == 'mutations':
        return api.client.post(path, json=kwargs.pop('json', mutation()), **kwargs)
    if endpoint == 'cursors':
        return api.client.post(path, json=kwargs.pop('json', {'device_id': 'phone', 'last_seq': 0}), **kwargs)
    return api.client.get(path, **kwargs)


def no_io(*args, **kwargs):
    raise AssertionError('unexpected IO')


@pytest.mark.parametrize('endpoint', ['mutations', 'cursors'])
@pytest.mark.parametrize('body', [b'{', b'{"padding":"' + b'x' * (1024 * 1024) + b'"}'], ids=['malformed', 'oversized'])
async def test_disabled_gate_never_reads_request_body(monkeypatch, endpoint, body):
    monkeypatch.delenv('SPACES_SYNC_API_ENABLED', raising=False)
    monkeypatch.setattr(serving, 'cell_store', no_io)
    monkeypatch.setattr(directory_router, 'directory_store', no_io)
    limiter = Mock(side_effect=no_io)
    monkeypatch.setattr(auth, '_enforce_rate_limit', limiter)
    app = FastAPI()
    app.include_router(spaces.router)
    authenticate = Mock(side_effect=no_io)
    app.dependency_overrides[auth.get_current_user_uid] = authenticate
    receive = AsyncMock(return_value={'type': 'http.request', 'body': body, 'more_body': False})
    send = AsyncMock()
    await app(
        {
            'type': 'http',
            'http_version': '1.1',
            'method': 'POST',
            'path': f'/v1/spaces/synthetic-space/{endpoint}',
            'root_path': '',
            'query_string': b'',
            'scheme': 'http',
            'headers': [(b'content-type', b'application/json'), (b'content-length', str(len(body)).encode())],
        },
        receive,
        send,
    )
    messages = [call.args[0] for call in send.await_args_list]
    assert messages[0]['status'] == 503
    assert json.loads(messages[1]['body']) == {'detail': {'code': 'spaces_sync_api_disabled', 'retryable': False}}
    receive.assert_not_awaited()
    authenticate.assert_not_called()
    limiter.assert_not_called()


@pytest.mark.parametrize('endpoint', ['changes', 'snapshot', 'mutations', 'cursors'])
@pytest.mark.parametrize(
    'gate,status,code',
    [
        ('off', 503, 'spaces_sync_api_disabled'),
        ('routing_off', 503, 'directory_routing_unavailable'),
        ('directory_outage', 503, 'directory_routing_unavailable'),
        ('missing_space', 404, None),
        ('non_member', 404, None),
        ('revoked', 404, None),
        ('firestore', 503, 'space_not_cell_served'),
        ('disabled', 503, 'directory_routing_unavailable'),
        ('cell_outage', 503, 'cell_space_unavailable'),
        ('unenrolled', 503, 'cell_space_unavailable'),
        ('tombstoned', 503, 'cell_space_unavailable'),
        ('enrolled', 200, None),
    ],
)
def test_gate_matrix(api, monkeypatch, endpoint, gate, status, code):
    if gate == 'off':
        monkeypatch.delenv('SPACES_SYNC_API_ENABLED')
        # Even authentication and rate limiting must not run with the flag off.
        api.app.dependency_overrides.clear()
        monkeypatch.setattr(serving, 'cell_store', no_io)
        monkeypatch.setattr(directory_router, 'directory_store', no_io)
        api.limiter.side_effect = no_io
    elif gate in {'routing_off', 'directory_outage'}:
        if gate == 'routing_off':
            monkeypatch.setenv('DIRECTORY_ROUTING_MODE', 'off')
        else:
            monkeypatch.setattr(directory_router, 'directory_store', no_io)
        monkeypatch.setattr(serving, 'cell_store', no_io)
    elif gate != 'missing_space':
        enroll(api, cell=gate if gate in {'firestore', 'disabled'} else 'cell1', head=gate != 'unenrolled')
        if gate == 'non_member':
            api.identity['uid'] = 'someone-else'
        elif gate == 'revoked':
            api.directory.revoke_member(api.sid, api.sid, now=time.time())
        elif gate == 'tombstoned':
            api.cell.purge_space(api.sid)
        elif gate == 'cell_outage':
            monkeypatch.setattr(serving, 'cell_store', Mock(side_effect=ConnectionError('synthetic cell outage')))
    response = request(api, endpoint)
    assert response.status_code == status, response.text
    if code:
        assert response.json()['detail'] == dict(
            code=code, retryable=code not in {'spaces_sync_api_disabled', 'space_not_cell_served'}
        )
    elif status == 404:
        assert response.json()['detail'] == 'Space not found'
    if gate == 'off':
        api.limiter.assert_not_called()


@pytest.mark.parametrize('role', ['member', 'owner'])
def test_other_uid_gets_no_personal_sync_access_even_with_owner_role(api, role):
    enroll(api)
    member = api.sid + '-member'
    api.directory.add_member(api.sid, member, role=role, now=time.time())
    api.identity['uid'] = member
    for endpoint in ['changes', 'snapshot', 'mutations', 'cursors']:
        response = request(api, endpoint)
        assert response.status_code == 404, endpoint
        assert response.json()['detail'] == 'Space not found'
    assert api.cell.read_doc(api.sid, 'notes', 'a') == {'text': 'original'}


def test_personal_uid_still_requires_owner_role(api):
    enroll(api)
    api.directory.add_member(api.sid, api.sid, role='member', now=time.time())
    for endpoint in ['changes', 'snapshot', 'mutations', 'cursors']:
        response = request(api, endpoint)
        assert response.status_code == 404, endpoint
        assert response.json()['detail'] == 'Space not found'


@pytest.mark.parametrize('endpoint', ['changes', 'snapshot', 'mutations', 'cursors'])
def test_sync_routes_enforce_auth_byok_validation(api, monkeypatch, endpoint):
    enroll(api)
    api.app.dependency_overrides.clear()
    monkeypatch.setattr(auth, 'verify_token', lambda token: api.sid)
    for name in [
        'enforce_account_deletion_http_access',
        '_enforce_cutover_http_if_request',
        '_resolve_request_plane_or_503',
        'record_user_platform',
        'record_client_device',
    ]:
        monkeypatch.setattr(auth, name, Mock())
    validate = Mock(side_effect=HTTPException(403, detail='Synthetic BYOK validation rejection'))
    monkeypatch.setattr(auth, 'validate_byok_request', validate)
    monkeypatch.setattr(auth, '_recover_locked_content_if_request', no_io)
    response = request(api, endpoint, headers={'Authorization': 'Bearer synthetic-token'})
    assert response.status_code == 403
    validate.assert_called_once_with(api.sid)
    api.limiter.assert_not_called()


def test_invalid_sid_and_membership_refresh(api):
    enroll(api)
    assert api.client.get('/v1/spaces/invalid%20sid/changes').status_code == 404
    assert request(api, 'changes').status_code == 200
    api.directory.revoke_member(api.sid, api.sid, now=time.time())
    assert request(api, 'changes').status_code == 404


@pytest.mark.parametrize('cell', [None, '', 123, 'cell2'])
def test_malformed_directory_route_fails_closed(api, monkeypatch, cell):
    enroll(api)
    monkeypatch.setattr(api.directory, 'get_space', lambda sid: SimpleNamespace(cell=cell))
    monkeypatch.setattr(serving, 'cell_store', no_io)
    for endpoint in ['changes', 'snapshot', 'mutations', 'cursors']:
        response = request(api, endpoint)
        assert response.status_code == 503
        assert response.json()['detail'] == {'code': 'directory_routing_unavailable', 'retryable': True}


def test_unexpected_cell_error_logs_only_exception_type(api, monkeypatch, caplog):
    enroll(api)
    monkeypatch.setattr(serving, 'cell_store', Mock(side_effect=RuntimeError('synthetic-private-content')))
    with caplog.at_level('ERROR', logger=spaces.__name__):
        response = request(api, 'changes')
    assert response.status_code == 503
    assert response.json()['detail'] == {'code': 'cell_space_unavailable', 'retryable': True}
    assert len(caplog.records) == 1
    record = caplog.records[0]
    assert record.getMessage() == 'Space sync cell operation failed: exception_type=RuntimeError'
    assert record.exc_info is None
    assert 'synthetic-private-content' not in caplog.text


def test_changes_content_free_coalesced_current_state_and_tail(api):
    enroll(api)

    def body(tx):
        tx.put('notes', 'a', {'text': 'first'})
        tx.put('notes', 'a', {'text': 'final'})
        tx.put('notes', 'b', {'text': 'other'})

    api.cell.run(api.sid, body, actor_uid=api.sid, now=time.time())
    api.cell.run(api.sid, lambda tx: tx.delete('notes', 'b'), actor_uid=api.sid, now=time.time())
    api.cell.run(
        api.sid,
        lambda tx: tx.put('notes', 'hidden', {'pipeline': True}, feed=False),
        actor_uid=api.sid,
        now=time.time(),
    )
    page = request(api, 'changes').json()
    assert [(e['entity_id'], e['op']) for e in page['entries']] == [('a', 'upsert'), ('b', 'delete')]
    assert all('doc' not in e for e in page['entries'])
    assert [(row['entity_id'], row['doc']) for row in page['rows']] == [('a', {'text': 'final'})]
    assert page['next_cursor'] == page['head'] == 5
    truncated = request(api, 'changes', params={'limit': 1}).json()
    assert truncated['next_cursor'] == 1 < truncated['head']
    assert request(api, 'changes', params={'cursor': 4}).json()['next_cursor'] == 5


@pytest.mark.parametrize('endpoint', ['changes', 'snapshot', 'mutations'])
def test_byte_documents_round_trip_through_every_row_response(api, endpoint):
    enroll(api)
    doc = {
        'binary': b'\x00\xff\x80',
        'nested': [{'binary': b'\xfe\x00'}, b'', b'plain UTF-8'],
        'json': {'$bytes': 'ordinary field', 'other': [None, 42, True]},
    }
    wire_doc = {
        'binary': {'$bytes': 'AP+A'},
        'nested': [{'binary': {'$bytes': '/gA='}}, {'$bytes': ''}, {'$bytes': 'cGxhaW4gVVRGLTg='}],
        'json': doc['json'],
    }
    api.cell.run(api.sid, lambda tx: tx.put('notes', 'a', doc), actor_uid=api.sid, now=time.time())
    response = request(api, endpoint)
    assert response.status_code == (409 if endpoint == 'mutations' else 200), response.text
    row = response.json()['row'] if endpoint == 'mutations' else response.json()['rows'][0]
    assert row['doc'] == wire_doc

    # Send exactly the document a sync client received, with its authoritative revision.
    payload = mutation()
    payload.update(base_revision=row['rev'], client_mutation_id='bytes-round-trip')
    payload['operation']['fields'] = row['doc']
    applied = request(api, 'mutations', json=payload)
    assert applied.status_code == 200, applied.text
    assert api.cell.read_doc(api.sid, 'notes', 'a') == doc
    replay = request(api, 'mutations', json=payload)
    assert replay.status_code == 200, replay.text
    assert replay.json() == {**applied.json(), 'replayed': True}
    # A different byte value must retain exactly-once fingerprint protection.
    payload['operation']['fields']['binary'] = {'$bytes': '/w=='}
    reused = request(api, 'mutations', json=payload)
    assert reused.status_code == 409, reused.text
    assert reused.json()['code'] == 'mutation_id_reused'
    assert reused.json()['row']['doc'] == wire_doc


@pytest.mark.parametrize('value', [None, 42, [], {}, '!', 'a', '/w', '/w==\n', 'é'])
def test_malformed_byte_tags_are_rejected_before_cell_io(api, monkeypatch, value):
    enroll(api)
    monkeypatch.setattr(serving, 'cell_store', no_io)
    payload = mutation()
    payload['operation']['fields'] = {'nested': [{'binary': {'$bytes': value}}]}
    response = request(api, 'mutations', json=payload)
    assert response.status_code == 422, response.text


def test_byte_mutations_retain_wire_size_limit(api, monkeypatch):
    enroll(api)
    monkeypatch.setattr(serving, 'cell_store', no_io)
    payload = mutation()
    payload['operation']['fields'] = {'binary': {'$bytes': base64.b64encode(b'\xff' * (100 * 1024)).decode()}}
    response = request(api, 'mutations', json=payload)
    assert response.status_code == 422, response.text
    assert 'operation exceeds 128 KiB' in response.text


def test_cursor_floor_ahead_and_monotonic_ack(api):
    enroll(api)
    for seq in [1, 0]:
        response = request(api, 'cursors', json={'device_id': 'phone', 'last_seq': seq})
        assert response.status_code == 200
        assert response.json() == {'status': 'ok', 'last_seq': 1, 'head': 1, 'epoch': 1}
    ahead = request(api, 'changes', params={'cursor': 2})
    assert ahead.status_code == 425
    assert ahead.json()['detail'] == dict(code='resync_required', reason='cursor_ahead_of_head', head=1, epoch=1)
    assert request(api, 'cursors', json={'device_id': 'other', 'last_seq': 2}).status_code == 425
    with api.cell.pool.connection() as conn:
        conn.execute(
            'UPDATE sync_cursors SET last_seen_at=%s WHERE space_id=%s', (time.time() - DEVICE_STALE_S - 1, api.sid)
        )
        conn.execute('UPDATE change_log SET ts=0 WHERE space_id=%s', (api.sid,))
    for endpoint in ['changes', 'cursors']:
        old = request(api, endpoint)
        assert old.status_code == 425
        assert old.json()['detail'] == dict(code='resync_required', reason='cursor_below_floor', floor=1, epoch=1)
    assert request(api, 'cursors', json={'device_id': 'bad id', 'last_seq': 1}).status_code == 422


def test_snapshot_pagination_since_epoch_and_page_one_head(api):
    enroll(api)
    for key in ['b', 'c']:
        api.cell.run(api.sid, lambda tx: tx.put('notes', key, {'v': key}), actor_uid=api.sid, now=time.time())
    first = request(api, 'snapshot', params={'limit': 1}).json()
    assert first['rows'][0]['entity_id'] == 'a'
    first_head = first['head']
    api.cell.run(api.sid, lambda tx: tx.put('notes', 'a', {'text': 'concurrent'}), actor_uid=api.sid, now=time.time())
    pages = [first]
    while pages[-1]['next_page_token']:
        pages.append(request(api, 'snapshot', params={'limit': 1, 'page_token': pages[-1]['next_page_token']}).json())
    assert [r['entity_id'] for p in pages for r in p['rows']] == ['a', 'b', 'c']
    assert pages[-1]['head'] > first_head
    changes = request(api, 'changes', params={'cursor': first_head}).json()
    assert changes['rows'][0]['doc'] == {'text': 'concurrent'}
    assert [r['entity_id'] for r in request(api, 'snapshot', params={'since': first_head}).json()['rows']] == ['a']
    api.cell.bump_epoch(api.sid, now=time.time())
    assert request(api, 'snapshot', params={'page_token': first['next_page_token']}).json()['epoch'] != first['epoch']


def test_snapshot_since_includes_feed_shaped_delete(api):
    enroll(api)
    since = api.cell.head(api.sid)[0]
    payload = mutation()
    payload['operation'] = {'type': 'delete'}
    assert request(api, 'mutations', json=payload).status_code == 200
    snapshot = request(api, 'snapshot', params={'since': since}).json()
    changes = request(api, 'changes', params={'cursor': since}).json()
    assert snapshot['rows'] == []
    assert snapshot['entries'] == changes['entries']
    assert [(entry['entity_id'], entry['op'], entry['seq']) for entry in snapshot['entries']] == [('a', 'delete', 2)]
    assert snapshot['next_page_token'] is None


@pytest.mark.parametrize(
    'token',
    [
        '',
        '!',
        'e30=',
        'WzFd',
        'WzEsMl0=',
        'W1sibm90ZXMiXSwiYSJd',
        base64.b64encode(json.dumps(['notes', 'bad\x00']).encode()).decode(),
    ],
)
def test_malformed_snapshot_tokens(api, token):
    enroll(api)
    assert request(api, 'snapshot', params={'page_token': token}).status_code == 422
    api.limiter.assert_called_once_with(api.sid, 'spaces:snapshot')
    api.limiter.side_effect = HTTPException(429, detail='Rate limit exceeded')
    assert request(api, 'snapshot', params={'page_token': token}).status_code == 429


def test_large_snapshot_pages_survive_exhausted_start_budget_and_epoch_restart(api):
    enroll(api)
    start_max = RATE_POLICIES['spaces:snapshot'][0]
    # More pages than the hourly start allowance, with real keyset tokens from PostgreSQL.
    api.cell.run(
        api.sid,
        lambda tx: [tx.put('notes', f'b{i:03}', {'v': i}) for i in range(start_max + 1)],
        actor_uid=api.sid,
        now=time.time(),
    )
    counts = {}

    def enforce(uid, policy, **kwargs):
        assert uid == api.sid
        counts[policy] = counts.get(policy, 0) + 1
        if counts[policy] > RATE_POLICIES[policy][0]:
            raise HTTPException(429, detail='Rate limit exceeded')

    api.limiter.side_effect = enforce
    for _ in range(start_max):
        first = request(api, 'snapshot', params={'limit': 1})
        assert first.status_code == 200
    page = first.json()
    token = page['next_page_token']
    rows = list(page['rows'])
    while page['next_page_token']:
        response = request(api, 'snapshot', params={'limit': 1, 'page_token': page['next_page_token']})
        assert response.status_code == 200, response.text
        page = response.json()
        rows.extend(page['rows'])
    assert len(rows) == start_max + 2
    assert counts['spaces:snapshot'] == start_max
    assert counts['spaces:snapshot_page'] > start_max
    api.cell.bump_epoch(api.sid, now=time.time())
    changed = request(api, 'snapshot', params={'limit': 1, 'page_token': token})
    assert changed.status_code == 200
    assert changed.json()['epoch'] != first.json()['epoch']
    # Client discards the old pages and restarts without a token, charging a new start.
    assert request(api, 'snapshot', params={'limit': 1}).status_code == 429
    assert counts['spaces:snapshot'] == start_max + 1


@pytest.mark.parametrize('forgery', ['unsigned', 'address', 'signature', 'space', 'since'])
def test_forged_snapshot_tokens_consume_start_budget(api, forgery):
    enroll(api)
    first = request(api, 'snapshot', params={'limit': 1}).json()
    parts = json.loads(base64.b64decode(first['next_page_token']))
    params = {'limit': 1}
    if forgery == 'unsigned':
        parts = parts[:2]
    elif forgery == 'address':
        parts[1] = 'forged-address'
    elif forgery == 'signature':
        parts[2] = '0' * 64
    elif forgery == 'space':
        parts[2] = spaces._page_signature(api.sid + '-other', 0, parts[:2])
    else:
        params['since'] = 1
    params['page_token'] = base64.b64encode(json.dumps(parts).encode()).decode()
    api.limiter.reset_mock()
    assert request(api, 'snapshot', params=params).status_code == 422
    api.limiter.assert_called_once_with(api.sid, 'spaces:snapshot')
    api.limiter.side_effect = HTTPException(429, detail='Rate limit exceeded')
    assert request(api, 'snapshot', params=params).status_code == 429


def test_mutation_apply_replay_conflicts_delete_and_events(api):
    enroll(api)
    first = request(api, 'mutations')
    assert first.status_code == 200, first.text
    assert first.json() == dict(
        status='ok', entity='notes', entity_id='a', client_mutation_id='edit-1', seq=2, rev=2, replayed=False
    )
    assert request(api, 'changes').json()['rows'][0]['author_id'] == api.sid
    assert request(api, 'mutations').json()['replayed'] is True
    assert api.cell.head(api.sid) == (2, 1)
    payload = mutation()
    payload['operation']['fields'] = {'text': 'different'}
    conflict = request(api, 'mutations', json=payload)
    assert conflict.status_code == 409
    assert conflict.json()['code'] == 'mutation_id_reused'
    assert conflict.json()['row']['doc'] == {'text': 'edited'}
    payload['client_mutation_id'] = 'stale'
    conflict = request(api, 'mutations', json=payload)
    assert conflict.status_code == 409
    assert conflict.json()['code'] == 'base_revision_mismatch'
    assert conflict.json()['row']['rev'] == 2
    with api.cell.pool.connection() as conn:
        assert conn.execute('SELECT count(*) FROM mutation_receipts WHERE space_id=%s', (api.sid,)).fetchone()[0] == 1
    payload.update(base_revision=2, client_mutation_id='delete', operation={'type': 'delete'})
    assert request(api, 'mutations', json=payload).json()['seq'] == 3
    assert request(api, 'mutations', json=payload).json()['replayed'] is True
    page = request(api, 'changes').json()
    assert page['rows'] == []
    assert page['entries'][0]['op'] == 'delete'
    payload.update(client_mutation_id='missing')
    assert request(api, 'mutations', json=payload).status_code == 404
    assert [c.kwargs['outcome'] for c in api.events.call_args_list] == [
        'applied',
        'replayed',
        'conflict',
        'conflict',
        'applied',
        'replayed',
    ]
    assert all(c.args == ('space_sync_mutation',) for c in api.events.call_args_list)


@pytest.mark.parametrize('operation', [{'type': 'patch', 'fields': {'text': 'first'}}, {'type': 'delete'}])
def test_replay_retains_original_revision_after_concurrent_advance(api, operation):
    enroll(api)
    payload = mutation()
    payload['operation'] = operation
    first = request(api, 'mutations', json=payload)
    assert first.status_code == 200
    with ThreadPoolExecutor(max_workers=1) as executor:
        executor.submit(
            api.cell.run,
            api.sid,
            lambda tx: tx.put('notes', 'a', {'text': 'later'}),
            actor_uid=api.sid,
            now=time.time(),
        ).result(timeout=10)
    replay = request(api, 'mutations', json=payload)
    assert replay.status_code == 200
    assert replay.json() == {**first.json(), 'replayed': True}
    assert replay.json()['rev'] == replay.json()['seq'] == 2
    assert api.cell.head(api.sid)[0] == 3
    assert api.cell.read_doc(api.sid, 'notes', 'a') == {'text': 'later'}


def test_datetime_revision_history_ties_and_compaction(api):
    enroll(api)
    now = time.time()
    payload = mutation()
    payload['base_revision'] = datetime.fromtimestamp(now, timezone.utc).isoformat()
    assert request(api, 'mutations', json=payload).status_code == 200
    payload['client_mutation_id'] = 'datetime-stale'
    old = request(api, 'mutations', json=payload)
    assert old.status_code == 409
    assert old.json()['code'] == 'base_revision_mismatch'
    with api.cell.pool.connection() as conn:
        conn.execute('DELETE FROM change_log WHERE space_id=%s AND seq=1', (api.sid,))
    unavailable = request(api, 'mutations', json=payload)
    assert unavailable.status_code == 409
    assert unavailable.json()['code'] == 'revision_unavailable'
    payload['base_revision'] = '2026-01-01T00:00:00'
    assert request(api, 'mutations', json=payload).status_code == 422


def test_datetime_revision_conflicts_after_contended_out_of_order_caller_times(api):
    enroll(api)
    locked, release_first, entered_second, release_second = [threading.Event() for _ in range(4)]
    caller_now = time.time()

    def first_body(tx):
        tx.get('notes', 'a')
        locked.set()
        assert release_first.wait(timeout=10)
        tx.put('notes', 'a', {'text': 'first'})

    def second_body(tx):
        entered_second.set()
        tx.get('notes', 'a')  # Waits behind the first writer's row lock.
        assert release_second.wait(timeout=10)
        tx.put('notes', 'a', {'text': 'second'})

    observer = Pool(cells_dsn(), size=1)
    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            first = executor.submit(api.cell.run, api.sid, first_body, actor_uid=api.sid, now=caller_now)
            try:
                assert locked.wait(timeout=5)
                second = executor.submit(api.cell.run, api.sid, second_body, actor_uid=api.sid, now=caller_now - 10)
                assert entered_second.wait(timeout=5)
                deadline = time.monotonic() + 5
                with observer.connection() as conn:
                    while not conn.execute(
                        "SELECT 1 FROM pg_stat_activity WHERE datname=current_database() "
                        "AND wait_event_type='Lock' AND query LIKE 'SELECT rev, doc FROM cell_docs%'"
                    ).fetchone():
                        assert time.monotonic() < deadline, 'second writer never contended on the row'
                        time.sleep(0.01)
                        conn.execute('SELECT pg_stat_clear_snapshot()')
                release_first.set()
                first.result(timeout=10)
                stale_token = datetime.now(timezone.utc).isoformat()
            finally:
                release_first.set()
                release_second.set()
            second.result(timeout=10)
    finally:
        observer.close()

    with api.cell.pool.connection() as conn:
        history = conn.execute(
            'SELECT seq, ts, committed_at FROM change_log WHERE space_id=%s ORDER BY seq', (api.sid,)
        ).fetchall()
    assert history[1][1] > history[2][1]  # Caller timestamps run backwards.
    assert history[1][2] < history[2][2]  # Server revision times follow commits.
    payload = mutation()
    payload.update(base_revision=stale_token, client_mutation_id='stale-datetime-contention')
    response = request(api, 'mutations', json=payload)
    assert response.status_code == 409, response.text
    assert response.json()['code'] == 'base_revision_mismatch'
    assert response.json()['row']['rev'] == 3
    assert api.cell.read_doc(api.sid, 'notes', 'a') == {'text': 'second'}


def test_datetime_revision_does_not_trust_pre_migration_timestamps(api):
    enroll(api)
    with api.cell.pool.connection() as conn:
        conn.execute('UPDATE change_log SET committed_at=NULL WHERE space_id=%s', (api.sid,))
    payload = mutation()
    payload['base_revision'] = datetime.now(timezone.utc).isoformat()
    response = request(api, 'mutations', json=payload)
    assert response.status_code == 409
    assert response.json()['code'] == 'revision_unavailable'
    assert request(api, 'mutations').status_code == 200  # Integer revisions remain usable.


def test_datetime_revision_roundtrips_row_timestamp_after_clock_regression(api):
    enroll(api)
    # Force logical clock advances even though the database clock is behind it.
    # Repeated float increments would drift off datetime's microsecond grid.
    with api.cell.pool.connection() as conn:
        conn.execute(
            'UPDATE space_heads SET revision_us=%s WHERE space_id=%s',
            (int(time.time() * 1_000_000) + 60_000_000, api.sid),
        )
    for index in range(16):
        api.cell.run(
            api.sid,
            lambda tx: tx.put('notes', 'a', {'index': index}),
            actor_uid=api.sid,
            now=0,
        )
    row = request(api, 'snapshot').json()['rows'][0]
    payload = mutation()
    payload['base_revision'] = datetime.fromtimestamp(row['updated_at'], timezone.utc).isoformat()
    assert request(api, 'mutations', json=payload).status_code == 200
    with api.cell.pool.connection() as conn:
        stamps = [
            r[0]
            for r in conn.execute(
                'SELECT committed_at FROM change_log WHERE space_id=%s ORDER BY seq', (api.sid,)
            ).fetchall()
        ]
    assert all(first < second for first, second in zip(stamps, stamps[1:]))


@pytest.mark.parametrize(
    'change',
    [
        {'base_revision': True},
        {'base_revision': 1.5},
        {'entity': 'Notes'},
        {'entity_id': 'a\x00'},
        {'client_mutation_id': 'bad id'},
        {'unknown': True},
        {'operation': {'type': 'unknown'}},
        {'operation': {'type': 'delete', 'fields': {}}},
        {'operation': {'type': 'patch', 'fields': {'huge': 'x' * (128 * 1024)}}},
    ],
)
def test_mutation_validation(api, change):
    enroll(api)
    payload = mutation()
    payload.update(change)
    assert request(api, 'mutations', json=payload).status_code == 422
    assert api.cell.head(api.sid)[0] == 1


def test_replay_survives_new_store_and_concurrent_duplicate(api):
    enroll(api)
    kwargs = dict(actor_uid=api.sid, **mutation(), now=time.time())
    barrier = threading.Barrier(2)

    def apply():
        barrier.wait(timeout=5)
        return apply_space_mutation(api.cell, api.sid, **kwargs)

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: apply(), range(2)))
    assert sorted(replayed for _, replayed in results) == [False, True]
    assert api.cell.head(api.sid)[0] == 2
    # Recreate the pool/store, then cross a process boundary to exclude module caches too.
    replacement = CellStore(Pool(cells_dsn(), size=1))
    try:
        assert apply_space_mutation(replacement, api.sid, **kwargs)[1] is True
    finally:
        replacement.pool.close()
    child_env = dict(
        os.environ,
        OMI_B3_REPLAY_DSN=cells_dsn(),
        OMI_B3_REPLAY_SPACE=api.sid,
        OMI_B3_REPLAY_MUTATION=json.dumps(kwargs),
    )
    replay = subprocess.run(
        [
            sys.executable,
            '-c',
            """
import json
import os
from database.cells.store import CellStore
from database.cells.mutations import apply_space_mutation
from database.jobstore.connection import Pool
pool = Pool(os.environ['OMI_B3_REPLAY_DSN'], size=1)
try:
    response, replayed = apply_space_mutation(
        CellStore(pool), os.environ['OMI_B3_REPLAY_SPACE'],
        **json.loads(os.environ['OMI_B3_REPLAY_MUTATION'])
    )
    assert replayed
    print(json.dumps(response))
finally:
    pool.close()
""",
        ],
        cwd=Path(__file__).resolve().parents[2],
        env=child_env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert replay.returncode == 0, replay.stderr
    assert json.loads(replay.stdout)['seq'] == 2
    assert json.loads(replay.stdout)['replayed'] is True
    assert api.cell.head(api.sid)[0] == 2


def test_rate_limits_and_contention_mapping(api, monkeypatch):
    enroll(api)
    for endpoint in ['changes', 'snapshot', 'mutations', 'cursors']:
        assert request(api, endpoint).status_code == 200
    assert [c.args[1] for c in api.limiter.call_args_list] == [
        'spaces:changes',
        'spaces:snapshot',
        'spaces:mutations',
        'spaces:cursors',
    ]
    api.limiter.side_effect = HTTPException(429, detail='Rate limit exceeded')
    assert request(api, 'changes').status_code == 429
    api.limiter.side_effect = None
    monkeypatch.setattr(api.cell, 'pull', Mock(side_effect=CellContentionExhausted(api.sid)))
    response = request(api, 'changes')
    assert response.status_code == 503
    assert response.json()['detail'] == dict(code='cell_contention', retryable=True)


def test_flag_is_call_time(monkeypatch):
    monkeypatch.delenv('SPACES_SYNC_API_ENABLED', raising=False)
    assert not spaces_sync_api.enabled()
    monkeypatch.setenv('SPACES_SYNC_API_ENABLED', 'TRUE')
    assert spaces_sync_api.enabled()
    monkeypatch.setenv('SPACES_SYNC_API_ENABLED', '1')
    assert not spaces_sync_api.enabled()
