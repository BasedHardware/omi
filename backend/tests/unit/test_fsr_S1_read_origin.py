"""S1: origin attribution adds telemetry without changing reads or responses."""

import asyncio
import json
import logging
import sys
import time
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest

from database import firestore_document_probe as probe
from database import firestore_read_origin as origin
from database.firestore_tier_context import FirestoreTierMiddleware


@pytest.fixture(autouse=True)
def isolated_origins(monkeypatch):
    monkeypatch.setattr(origin, '_known_origins', set())
    token = origin._read_origin.set(None)
    yield
    origin._read_origin.reset(token)


@pytest.mark.parametrize('protocol,prefix', [('http', 'http'), ('websocket', 'ws')])
def test_middleware_resolves_live_route_template_and_resets(protocol, prefix):
    async def downstream(scope, receive, send):
        assert origin.current_read_origin() == f'{prefix}:unmatched'
        scope['route'] = SimpleNamespace(path='/v1/users/{uid}')
        assert origin.current_read_origin() == f'{prefix}:/v1/users/{{uid}}'
        probe._record(('users', 'secret-user'), True)
        raise RuntimeError('application error')

    async def run():
        with origin.read_origin('job:parent'):
            with pytest.raises(RuntimeError):
                await FirestoreTierMiddleware(downstream)(
                    {'type': protocol, 'path': '/v1/users/secret-user'}, None, None
                )
            assert origin.current_read_origin() == 'job:parent'

    asyncio.run(run())
    assert origin.current_read_origin() == 'unset'
    labels = probe.FIRESTORE_BILLED_READS_BY_ORIGIN.labels(
        origin=f'{prefix}:/v1/users/{{uid}}', collection='users', kind='lookup'
    )
    assert labels._value.get() >= 1
    assert all('secret' not in name for name in origin._known_origins)


@pytest.mark.parametrize('protocol,prefix', [('http', 'http'), ('websocket', 'ws')])
def test_origin_string_is_built_once_per_scope_and_refreshes_after_routing(protocol, prefix):
    builds = []

    class RoutePath(str):
        def __format__(self, spec):
            builds.append(str(self))
            return super().__format__(spec)

    scope = {'type': protocol, 'path': '/private-id'}
    token = origin.bind_read_scope(scope)
    try:
        assert origin.current_read_origin() == f'{prefix}:unmatched'
        scope['route'] = SimpleNamespace(path=RoutePath('/items/{item_id}'))
        for _ in range(100):
            assert origin.current_read_origin() == f'{prefix}:/items/{{item_id}}'
        assert builds == ['/items/{item_id}']
        scope['route'] = SimpleNamespace(path=RoutePath('/other/{item_id}'))
        assert origin.current_read_origin() == f'{prefix}:/other/{{item_id}}'
        assert builds == ['/items/{item_id}', '/other/{item_id}']
        scope.pop('route')
        assert origin.current_read_origin() == f'{prefix}:unmatched'
    finally:
        origin.reset_read_scope(token)
    other_scope = {'type': protocol, 'route': SimpleNamespace(path=RoutePath('/items/{item_id}'))}
    token = origin.bind_read_scope(other_scope)
    try:
        assert origin.current_read_origin() == f'{prefix}:/items/{{item_id}}'
        assert len(builds) == 3
    finally:
        origin.reset_read_scope(token)


def test_cached_scope_preserves_overflow_observation_count(monkeypatch):
    monkeypatch.setattr(origin, 'MAX_ORIGINS', 0)
    before = origin.FIRESTORE_ORIGIN_LABEL_OVERFLOW._value.get()
    token = origin.bind_read_scope({'type': 'http', 'route': SimpleNamespace(path='/items/{item_id}')})
    try:
        for _ in range(3):
            assert origin.current_read_origin() == 'overflow'
    finally:
        origin.reset_read_scope(token)
    assert origin.FIRESTORE_ORIGIN_LABEL_OVERFLOW._value.get() == before + 3


@pytest.fixture
def fastapi_types():
    from fastapi import FastAPI, WebSocket
    from fastapi.testclient import TestClient

    return FastAPI, WebSocket, TestClient


def test_actual_fastapi_http_and_websocket_templates(fastapi_types):
    FastAPI, WebSocket, TestClient = fastapi_types
    app = FastAPI()
    app.add_middleware(FirestoreTierMiddleware)

    @app.get('/items/{item_id}')
    def get_item(item_id: str):
        return origin.current_read_origin()

    @app.websocket('/listen/{socket_id}')
    async def listen(websocket: WebSocket, socket_id: str):
        await websocket.accept()
        await websocket.send_text(origin.current_read_origin())
        await websocket.close()

    with TestClient(app) as client:
        assert client.get('/items/private-id').json() == 'http:/items/{item_id}'
        with client.websocket_connect('/listen/private-id') as socket:
            assert socket.receive_text() == 'ws:/listen/{socket_id}'


def test_jobs_sync_async_decorators_and_task_executor_propagation():
    from utils.executors import db_executor, run_blocking, start_background_task

    @origin.read_origin('job:sync')
    def sync_job():
        return origin.current_read_origin()

    @origin.read_origin('job:async')
    async def async_job():
        await asyncio.sleep(0)
        return origin.current_read_origin()

    async def task_body():
        await asyncio.sleep(0)
        assert origin.current_read_origin() == 'task:worker'
        return await run_blocking(db_executor, origin.current_read_origin)

    async def run():
        with origin.read_origin('job:parent'):
            task = start_background_task(task_body(), name='worker')
            assert origin.current_read_origin() == 'job:parent'
            assert await async_job() == 'job:async'
            assert await task == 'task:worker'
        assert origin.current_read_origin() == 'unset'

    assert sync_job() == 'job:sync'
    asyncio.run(run())


def test_task_created_before_parent_reset_keeps_its_origin():
    from utils.executors import start_background_task

    async def run():
        async def body():
            await asyncio.sleep(0)
            return origin.current_read_origin()

        with origin.read_origin('job:parent'):
            task = start_background_task(body(), name='detached')
        assert await task == 'task:detached'

    asyncio.run(run())


def test_overflow_and_invalid_names_are_bounded_and_recording_never_raises(monkeypatch):
    monkeypatch.setattr(origin, 'MAX_ORIGINS', 2)
    before = origin.FIRESTORE_ORIGIN_LABEL_OVERFLOW._value.get()
    for name, expected in [('job:a', 'job:a'), ('job:b', 'job:b'), ('job:c', 'overflow'), ('job:a', 'job:a')]:
        with origin.read_origin(name):
            assert origin.current_read_origin() == expected
    assert origin.FIRESTORE_ORIGIN_LABEL_OVERFLOW._value.get() == before + 1
    with origin.read_origin('job:contains/user-id'):
        assert origin.current_read_origin() == 'unset'
    monkeypatch.setattr(origin, '_bounded_origin', lambda value: 1 / 0)
    assert origin.current_read_origin() == 'unset'


def test_billing_math_is_identical_for_origin_and_existing_counter(monkeypatch):
    # Exercise wrapped SDK boundary functions without any network/client.
    path = ('users', 'secret', 'conversations')
    query = SimpleNamespace(_parent=SimpleNamespace(_path=path), _offset=7)
    snapshots = [SimpleNamespace(exists=True, reference=SimpleNamespace(_path=path + ('one',)))]
    stream = probe._wrap_query_stream(lambda self: iter(snapshots))
    empty_stream = probe._wrap_query_stream(lambda self: iter(()))
    lookup = probe._wrap_lookup_get(lambda self: SimpleNamespace(exists=False))
    aggregation = probe._wrap_aggregation_stream(lambda self: iter([[SimpleNamespace(value=2001)]]))
    count_query = SimpleNamespace(_nested_query=SimpleNamespace(_parent=SimpleNamespace(_path=path)), _aggregations=[])
    existing = probe.FIRESTORE_BILLED_READS.labels(collection='users/conversations', kind='query', tier='unattributed')
    attributed = probe.FIRESTORE_BILLED_READS_BY_ORIGIN.labels(
        collection='users/conversations', kind='query', origin='job:math'
    )
    before, origin_before = existing._value.get(), attributed._value.get()
    with origin.read_origin('job:math'):
        assert list(stream(query)) == snapshots  # 1 doc + 7 skipped
        query._offset = 0
        assert list(empty_stream(query)) == []  # floor 1
        assert list(aggregation(count_query))  # ceil(2001 / 1000) = 3
        lookup(SimpleNamespace(_path=path + ('missing',)))
    assert existing._value.get() - before == attributed._value.get() - origin_before == 12
    assert (
        probe.FIRESTORE_BILLED_READS_BY_ORIGIN.labels(
            collection='users/conversations', kind='not_found', origin='job:math'
        )._value.get()
        == 1
    )


def test_ledger_adds_origins_without_changing_old_fields(monkeypatch, caplog):
    monkeypatch.setattr(probe, '_LEDGER_ENABLED', True)
    monkeypatch.setattr(probe, '_ledger_day', time.strftime('%Y-%m-%d', time.gmtime()))
    monkeypatch.setattr(probe, '_ledger_counts', {'lookup': 0, 'not_found': 0, 'query': 0})
    monkeypatch.setattr(probe, '_ledger_tier_counts', {})
    monkeypatch.setattr(probe, '_ledger_origin_counts', {})
    monkeypatch.setattr(probe, '_ledger_last_emit', float('inf'))
    with origin.read_origin('job:ledger'), caplog.at_level(logging.INFO, logger=probe.__name__):
        probe._record(('users', 'secret'), True, sdk_object=SimpleNamespace(project='based-hardware'))
        probe._record(('users', 'secret'), False, sdk_object=SimpleNamespace(project='based-hardware'))
        probe._ledger_atexit()
    payload = json.loads(caplog.records[-1].message)
    assert payload['reads_by_origin'] == {'job:ledger': 2}
    assert {
        'event',
        'schema',
        'service',
        'epoch',
        'seq',
        'day',
        'lookup',
        'not_found',
        'query',
        'tier_counts',
        'unscoped',
    } <= payload.keys()
    assert (payload['lookup'], payload['not_found'], payload['query']) == (1, 1, 0)
    assert payload['tier_counts'] == {'unattributed': 2}
    assert payload['schema'] == 2


@pytest.mark.parametrize(
    'pattern',
    [
        'users/client_devices',
        'users/account_cutover',
        'desktop_prompts',
        'users/fair_use_state',
        'users/llm_usage',
        'users/hourly_usage',
        'users/memory_state',
        'users/candidate_integration_outbox',
        'users/task_recurrence_inbox',
        'users/frame_deletion_outbox',
        'account_deletions',
        'conversation_finalization_jobs',
        'users/daily_summaries',
        'users/desktop_daily_usage',
        'dream_users/dirty',
        'users/dream_runs',
        'offline_sync_jobs',
        'sync_backfill_pending',
    ],
)
def test_reviewed_collection_patterns(pattern):
    path = tuple(piece for segment in pattern.split('/') for piece in (segment, 'private-id'))
    assert probe.collection_pattern(path) == pattern


@pytest.mark.parametrize(
    'name,label',
    [
        ('sync_pipeline:private-job', 'sync_pipeline'),
        ('sync:uid-lease:private-job', 'sync:uid-lease'),
        ('fair_use_classifier:private-user:private-session', 'fair_use_classifier'),
        ('migrate_memories:private-user', 'migrate_memories'),
        ('pusher_finalization:private-user:private-conversation', 'pusher_finalization'),
        ('x_initial_sync_private-user', 'x_initial_sync'),
        ('pusher:executor_health', 'pusher:executor_health'),
    ],
)
def test_dynamic_task_names_never_become_origin_ids(name, label):
    from utils.executors import start_background_task

    async def run():
        async def body():
            return origin.current_read_origin()

        task = start_background_task(body(), name=name)
        assert task.get_name() == name
        assert await task == 'task:' + label

    asyncio.run(run())
    assert all('private' not in item for item in origin._known_origins)
