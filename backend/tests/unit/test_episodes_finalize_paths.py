"""Every finalize path closes the live episode when it starts and runs the episode hook after processing.

The pendant double-tap and the app's Wrap up reach ``POST /v1/conversations`` (synchronous);
desktop reaches ``POST /v1/conversations/{id}/finalize``; listen and quiet recovery reach the
durable finalizer. ``test_episodes_service`` covers what the close and the hook do.
"""

from __future__ import annotations

import asyncio
import inspect
import os
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

os.environ.setdefault(
    'ENCRYPTION_SECRET',
    'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv',
)
os.environ.setdefault('OPENAI_API_KEY', 'test-openai-key-not-real')

from config import episodes as config
from models.conversation import Conversation
from models.conversation_enums import ConversationSource, ConversationStatus
from models.structured import Structured
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore, StrictFirestoreDocument
from utils.conversations.v3 import finish as v3_finish
from utils.conversations.v3.live import FINISH_FIELDS, FINISH_RECORDING_FIELD, FINISH_WINDOW_FIELD
from tests.unit.test_batch_pipeline_projection import native_finish_completion
from utils.conversations import finalizer
from utils.conversations.processing_trigger import ProcessingTrigger
from utils.episodes import finalize as episode_finalize

_UID = 'finalize-paths-uid'
_STARTED = datetime(2026, 10, 23, 9, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def _enabled(monkeypatch):
    monkeypatch.delenv(config.EPISODES_ENABLED_ENV, raising=False)


@pytest.fixture(scope='module')
def conv():
    import routers.conversations as conversations_router

    return conversations_router


def _conversation(status: ConversationStatus) -> Conversation:
    return Conversation(
        id='conv-finalize',
        created_at=_STARTED,
        started_at=_STARTED,
        finished_at=_STARTED,
        language='en',
        structured=Structured(title=''),
        transcript_segments=[],
        status=status,
        source=ConversationSource.omi,
    )


@contextmanager
def _noop_guard(*_args: Any, **_kwargs: Any):
    yield


def _episode_spies(monkeypatch, module, timeline):
    monkeypatch.setattr(
        module.episode_finalize,
        'close_now',
        lambda uid, cid, trigger, source=None: timeline.append(('close', cid, trigger)) or 'closed',
    )
    monkeypatch.setattr(
        module.episode_finalize,
        'schedule_after_finalization',
        lambda uid, cid, trigger: timeline.append(('after', cid, trigger)),
    )


def _drive_sync_route(conv, monkeypatch, *, persisted=True):
    timeline: list[tuple] = []
    in_progress = _conversation(ConversationStatus.in_progress)
    processed = _conversation(ConversationStatus.completed)

    def process(_uid, _language, conversation, **kwargs):
        timeline.append(('process', conversation.id, kwargs.get('trigger')))
        kwargs['persistence_observer'](persisted)
        return processed

    monkeypatch.setattr(conv, 'retrieve_in_progress_conversation', lambda uid: {'id': in_progress.id})
    monkeypatch.setattr(conv, 'deserialize_conversation', lambda data: in_progress)
    monkeypatch.setattr(conv, '_get_valid_conversation_by_id', lambda uid, cid, **_kw: {'id': cid})
    monkeypatch.setattr(conv.lifecycle_service, 'admit_processing', lambda uid, cid: True)
    monkeypatch.setattr(conv.lifecycle_service, 'processing_admission_guard', _noop_guard)
    monkeypatch.setattr(conv.redis_db, 'get_cached_user_geolocation', lambda uid: None)
    monkeypatch.setattr(conv.redis_db, 'get_in_progress_conversation_id', lambda uid: in_progress.id)
    monkeypatch.setattr(conv.redis_db, 'remove_in_progress_conversation_id', lambda uid: None)
    monkeypatch.setattr(conv, 'process_conversation', process)
    monkeypatch.setattr(conv, 'trigger_external_integrations', AsyncMock(return_value=[]))
    _episode_spies(monkeypatch, conv, timeline)
    conv.process_in_progress_conversation(uid=_UID)
    return timeline


def test_sync_finalize_closes_the_episode_before_processing_and_runs_the_hook_after(conv, monkeypatch):
    timeline = _drive_sync_route(conv, monkeypatch)
    final = ProcessingTrigger.CLIENT_FINALIZE
    assert timeline == [
        ('close', 'conv-finalize', final),
        ('process', 'conv-finalize', final),
        ('after', 'conv-finalize', final),
    ]


def test_sync_finalize_that_lost_ownership_runs_no_hook(conv, monkeypatch):
    timeline = _drive_sync_route(conv, monkeypatch, persisted=False)
    assert [step for step, *_ in timeline] == ['close', 'process']


def test_sync_finalize_that_lost_admission_leaves_the_episode_alone(conv, monkeypatch):
    timeline: list[tuple] = []
    in_progress = _conversation(ConversationStatus.in_progress)
    monkeypatch.setattr(conv, 'retrieve_in_progress_conversation', lambda uid: {'id': in_progress.id})
    monkeypatch.setattr(conv, 'deserialize_conversation', lambda data: in_progress)
    monkeypatch.setattr(conv, '_get_valid_conversation_by_id', lambda uid, cid, **_kw: {'id': cid})
    monkeypatch.setattr(conv.lifecycle_service, 'admit_processing', lambda uid, cid: False)
    monkeypatch.setattr(conv.redis_db, 'get_cached_user_geolocation', lambda uid: None)
    _episode_spies(monkeypatch, conv, timeline)
    # A second double-tap on the same conversation: the first request owns it, this one is a no-op.
    conv.process_in_progress_conversation(uid=_UID)
    assert timeline == []


def test_durable_client_finalize_closes_the_episode_with_the_request(conv, monkeypatch):
    timeline: list[tuple] = []
    in_progress = _conversation(ConversationStatus.in_progress)
    monkeypatch.setattr(conv, '_get_valid_conversation_by_id', lambda uid, cid, **_kw: {'id': cid})
    monkeypatch.setattr(conv, 'deserialize_conversation', lambda data: in_progress)
    monkeypatch.setattr(conv.byok, 'has_byok_keys', lambda: False)
    monkeypatch.setattr(
        conv.lifecycle_service,
        'request_finalization',
        lambda *a, **k: timeline.append(('enqueue',)) or {'route': 'cloud_tasks', 'job_id': 'job-1'},
    )
    monkeypatch.setattr(conv.redis_db, 'get_in_progress_conversation_id', lambda uid: None)
    _episode_spies(monkeypatch, conv, timeline)
    response = conv.finalize_conversation('conv-finalize', request=None, uid=_UID)
    assert response.conversation.status == ConversationStatus.processing
    # The worker runs the post-processing hook; the route only closes.
    assert timeline == [('enqueue',), ('close', 'conv-finalize', ProcessingTrigger.CLIENT_FINALIZE)]


# --------------------------------------------------------------------------- durable finalizer


class _Stop(Exception):
    pass


def test_durable_finalizer_closes_the_episode_before_processing(monkeypatch):
    seen: list[tuple] = []
    row = {'id': 'c1', 'source': 'omi'}
    conversation = _conversation(ConversationStatus.processing)

    async def admitted(*_args, **_kwargs):
        return None, row, conversation

    async def evidence(*_args, **_kwargs):
        seen.append(('processing',))
        raise _Stop

    async def run_inline(_executor, function, *args, **kwargs):
        return function(*args, **kwargs)

    monkeypatch.setattr(finalizer, '_load_admitted_conversation', admitted)
    monkeypatch.setattr(finalizer, 'await_meeting_evidence', evidence)
    monkeypatch.setattr(finalizer, 'run_blocking', run_inline)
    monkeypatch.setattr(
        finalizer, 'close_episode_now', lambda uid, cid, trigger, source: seen.append(('close', cid, trigger, source))
    )
    with pytest.raises(_Stop):
        asyncio.run(
            finalizer.finalize_persisted_conversation(
                _UID,
                'c1',
                finalization_job_id='job-1',
                dispatch_generation=1,
                lease_epoch=1,
                trigger=ProcessingTrigger.SERVER_RECOVERY,
            )
        )
    assert seen == [('close', 'c1', ProcessingTrigger.SERVER_RECOVERY, 'omi'), ('processing',)]


def test_durable_finalizer_close_is_bounded_and_fail_open(monkeypatch):
    budgets = []

    async def expired(awaitable, timeout):
        budgets.append(timeout)
        awaitable.close()
        raise asyncio.TimeoutError

    monkeypatch.setattr(finalizer.asyncio, 'wait_for', expired)
    asyncio.run(finalizer._episode_at_finalization_start(_UID, 'c1', {'id': 'c1'}, ProcessingTrigger.CAPTURE_END))
    assert budgets == [finalizer.EPISODE_CLOSE_TIMEOUT_SECONDS]
    # Nothing to close without a row, and nothing at all with episodes off.
    asyncio.run(finalizer._episode_at_finalization_start(_UID, 'c1', None, ProcessingTrigger.CAPTURE_END))
    monkeypatch.setenv(config.EPISODES_ENABLED_ENV, 'off')
    asyncio.run(finalizer._episode_at_finalization_start(_UID, 'c1', {'id': 'c1'}, ProcessingTrigger.CAPTURE_END))
    assert budgets == [finalizer.EPISODE_CLOSE_TIMEOUT_SECONDS]


# --------------------------------------------------------------------------- shared hooks


def test_close_now_passes_the_trigger_and_never_raises(monkeypatch):
    from utils.episodes import service

    calls = []
    monkeypatch.setattr(episode_finalize.client_gate, 'client_seen_cached', lambda uid: True)
    monkeypatch.setattr(service, 'close_on_finalize', lambda uid, cid, **kw: calls.append((cid, kw)) or 'closed')
    assert episode_finalize.close_now(_UID, 'c1', ProcessingTrigger.CLIENT_FINALIZE) == 'closed'
    assert calls == [('c1', {'trigger': 'client_finalize', 'source': None})]

    def boom(*_args, **_kwargs):
        raise RuntimeError('episode store down')

    monkeypatch.setattr(service, 'close_on_finalize', boom)
    assert episode_finalize.close_now(_UID, 'c1', ProcessingTrigger.CLIENT_FINALIZE) == 'error'
    monkeypatch.setattr(episode_finalize.client_gate, 'client_seen_cached', lambda uid: False)
    assert episode_finalize.close_now(_UID, 'c1', ProcessingTrigger.CLIENT_FINALIZE) == 'skipped_no_client'
    monkeypatch.setenv(config.EPISODES_ENABLED_ENV, 'off')
    assert episode_finalize.close_now(_UID, 'c1', ProcessingTrigger.CLIENT_FINALIZE) == 'disabled'


def test_schedule_after_finalization_runs_the_finalizer_hook_off_the_request(monkeypatch):
    from database import conversations as conversations_db
    from utils.episodes import service

    submitted = []
    hooked = []
    monkeypatch.setattr(
        episode_finalize, 'submit_with_context', lambda executor, fn, *args: submitted.append((fn, args))
    )
    episode_finalize.schedule_after_finalization(_UID, 'c1', ProcessingTrigger.CLIENT_FINALIZE)
    assert len(submitted) == 1
    row = {'id': 'c1', 'source': 'omi'}
    monkeypatch.setattr(conversations_db, 'get_conversation', lambda uid, cid: row if cid == 'c1' else None)
    monkeypatch.setattr(service, 'on_conversation_finalized', lambda *a, **k: hooked.append((a, k)))
    fn, args = submitted[0]
    fn(*args)
    assert hooked == [((_UID, 'c1', row), {'trigger': 'client_finalize'})]


def test_schedule_after_finalization_survives_a_saturated_pool(monkeypatch):
    def saturated(*_args, **_kwargs):
        raise RuntimeError('episode pool saturated')

    monkeypatch.setattr(episode_finalize, 'submit_with_context', saturated)
    episode_finalize.schedule_after_finalization(_UID, 'c1', ProcessingTrigger.CLIENT_FINALIZE)


@pytest.mark.parametrize('intake', [False, True])
def test_saturated_episode_hook_is_queued_until_capacity_returns_without_another_append(monkeypatch, intake):
    import threading
    from utils.executors import MonitoredThreadPoolExecutor

    pool = MonitoredThreadPoolExecutor('episode-retry-test', max_workers=1, max_queue_size=0, wait_on_saturation=True)
    release, executed = threading.Event(), threading.Event()
    occupied = pool.submit(release.wait, 5)
    monkeypatch.setattr(episode_finalize, 'lifecycle_executor', lambda *a, **kw: pool)
    hook = 'attach_synced_at_intake' if intake else '_after_finalization'
    monkeypatch.setattr(episode_finalize, hook, lambda *a: executed.set())
    try:
        if intake:
            episode_finalize.schedule_synced_intake_attach(_UID, 'c1', {'id': 'c1'})
        else:
            episode_finalize.schedule_after_finalization(_UID, 'c1', ProcessingTrigger.CLIENT_FINALIZE)
        assert not executed.is_set()
        release.set()
        occupied.result(timeout=5)
        assert executed.wait(5), 'the final hook was dropped on saturation'
    finally:
        release.set()
        pool.shutdown(wait=True)


def test_attach_synced_at_intake_joins_through_the_service_and_normalizes_the_row(monkeypatch):
    from utils.episodes import service

    seen = []
    monkeypatch.setattr(episode_finalize.client_gate, 'client_seen_cached', lambda uid: True)
    monkeypatch.setattr(
        service,
        'attach_synced_intake',
        lambda uid, cid, row, collaborators=None: seen.append((uid, cid, row['source'])) or 'joined',
    )
    row = {'id': 'c-wal', 'source': ConversationSource.omi}
    assert episode_finalize.attach_synced_at_intake(_UID, 'c-wal', row) == 'joined'
    # The boundary rules compare wire values; the pydantic enum member never reaches them.
    assert seen == [(_UID, 'c-wal', 'omi')]


def test_attach_synced_at_intake_is_gated_and_fail_open(monkeypatch):
    monkeypatch.setattr(episode_finalize.client_gate, 'client_seen_cached', lambda uid: False)
    assert episode_finalize.attach_synced_at_intake(_UID, 'c-wal', {'id': 'c-wal'}) == 'skipped_no_client'
    monkeypatch.setattr(episode_finalize.client_gate, 'client_seen_cached', lambda uid: True)
    monkeypatch.setenv(config.EPISODES_ENABLED_ENV, 'off')
    assert episode_finalize.attach_synced_at_intake(_UID, 'c-wal', {'id': 'c-wal'}) == 'disabled'
    monkeypatch.delenv(config.EPISODES_ENABLED_ENV)
    assert episode_finalize.attach_synced_at_intake(_UID, '', {'id': 'c-wal'}) == 'disabled'

    def boom(*_args, **_kwargs):
        raise RuntimeError('episode store unavailable')

    from utils.episodes import service

    monkeypatch.setattr(service, 'attach_synced_intake', boom)
    assert episode_finalize.attach_synced_at_intake(_UID, 'c-wal', {'id': 'c-wal'}) == 'error'


@pytest.mark.parametrize('route', ['cloud_tasks', 'queued'])
def test_mobile_process_now_uses_exact_id_durable_handoff(conv, monkeypatch, route):
    """Mobile must acknowledge durable intent before expensive work, even if enqueue ACK is lost."""
    timeline = []
    in_progress = _conversation(ConversationStatus.in_progress)
    monkeypatch.setattr(conv, 'is_listen_finalization_dispatch_enabled', lambda: True)
    monkeypatch.setattr(conv.byok, 'has_byok_keys', lambda: False)
    monkeypatch.setattr(conv, 'retrieve_in_progress_conversation', lambda uid: {'id': 'conv-finalize'})
    monkeypatch.setattr(conv, '_get_valid_conversation_by_id', lambda uid, cid, **_kw: {'id': cid})
    monkeypatch.setattr(conv, 'deserialize_conversation', lambda data: in_progress)

    def admit(uid, cid, **kwargs):
        assert cid == 'conv-finalize'
        assert kwargs['trigger'] is ProcessingTrigger.CLIENT_FINALIZE
        assert kwargs['require_cloud_tasks'] is True
        timeline.append(('enqueue',))
        return {'route': route, 'job_id': 'durable-job'}

    monkeypatch.setattr(conv.lifecycle_service, 'request_finalization', admit)
    monkeypatch.setattr(conv, 'process_conversation', lambda *a, **k: pytest.fail('request ran expensive work'))
    # Redis moved to the next capture after the initial lookup. Never remove it.
    monkeypatch.setattr(conv.redis_db, 'get_in_progress_conversation_id', lambda uid: 'next-capture')
    monkeypatch.setattr(
        conv.redis_db, 'remove_in_progress_conversation_id', lambda uid: pytest.fail('removed next capture')
    )
    _episode_spies(monkeypatch, conv, timeline)
    app = FastAPI()
    app.add_api_route('/v1/conversations', conv.process_in_progress_conversation, methods=['POST'])
    uid_dependency = inspect.signature(conv.process_in_progress_conversation).parameters['uid'].default.dependency
    app.dependency_overrides[uid_dependency] = lambda: _UID
    with TestClient(app) as client:
        result = client.post('/v1/conversations', json={})
    assert result.status_code == 200
    assert result.json()['conversation']['id'] == 'conv-finalize'
    assert result.json()['conversation']['status'] == 'processing'
    assert result.json()['messages'] == []
    assert timeline == [('enqueue',), ('close', 'conv-finalize', ProcessingTrigger.CLIENT_FINALIZE)]


def test_mobile_durable_admission_unavailable_leaves_recording_recoverable(conv, monkeypatch):
    in_progress = _conversation(ConversationStatus.in_progress)
    monkeypatch.setattr(conv, 'is_listen_finalization_dispatch_enabled', lambda: True)
    monkeypatch.setattr(conv.byok, 'has_byok_keys', lambda: False)
    monkeypatch.setattr(conv, 'retrieve_in_progress_conversation', lambda uid: {'id': 'conv-finalize'})
    monkeypatch.setattr(conv, '_get_valid_conversation_by_id', lambda uid, cid, **_kw: {'id': cid})
    monkeypatch.setattr(conv, 'deserialize_conversation', lambda data: in_progress)

    def refuse(*args, **kwargs):
        raise conv.lifecycle_service.FinalizationDispatchUnavailable('unconfigured queue')

    monkeypatch.setattr(conv.lifecycle_service, 'request_finalization', refuse)
    monkeypatch.setattr(conv, 'record_product_event', lambda *a, **k: None)
    monkeypatch.setattr(conv, 'process_conversation', lambda *a, **k: pytest.fail('inline fallback'))
    with pytest.raises(HTTPException) as error:
        conv.process_in_progress_conversation(uid=_UID)
    assert error.value.status_code == 503
    assert in_progress.status is ConversationStatus.in_progress


def test_mobile_byok_keeps_request_scoped_processing(conv, monkeypatch):
    monkeypatch.setattr(conv, 'is_listen_finalization_dispatch_enabled', lambda: True)
    monkeypatch.setattr(conv.byok, 'has_byok_keys', lambda: True)
    monkeypatch.setattr(conv.lifecycle_service, 'request_finalization', lambda *a, **k: pytest.fail('queued BYOK'))
    timeline = _drive_sync_route(conv, monkeypatch)
    assert [step for step, *_ in timeline] == ['close', 'process', 'after']


def test_group_join_schedules_one_group_recovery(monkeypatch):
    from database import conversations

    calls = []
    monkeypatch.setattr(episode_finalize.client_gate, 'client_seen_cached', lambda uid: True)
    monkeypatch.setattr(
        conversations, 'get_conversation_raw_snapshot', lambda *a, **kw: {'capture_group': {'primary_id': 'pendant'}}
    )
    monkeypatch.setattr(
        episode_finalize, 'schedule_after_finalization', lambda uid, cid, trigger: calls.append((uid, cid, trigger))
    )
    episode_finalize.schedule_group_attachments(_UID, ['desktop', 'pendant', 'desktop'])
    assert calls == [(_UID, 'pendant', ProcessingTrigger.CAPTURE_GROUP)]


def test_serving_intake_notifies_workerd_only_for_current_bound_revision(monkeypatch):
    from datetime import datetime, timedelta, timezone
    from unittest.mock import Mock

    import httpx
    from database import _client
    from utils.episodes import service
    from utils.sync import worker_client

    monkeypatch.delenv('SYNC_EPISODE_INTAKE_ORIGIN', raising=False)
    monkeypatch.delenv('WORKER_EPISODE_INTAKE_AUDIENCE', raising=False)
    monkeypatch.setattr(episode_finalize.client_gate, 'client_seen_cached', lambda _uid: True)
    canonical = Mock(return_value='joined')
    monkeypatch.setattr(service, 'attach_synced_intake', canonical)
    client = Mock()
    snapshot_get = (
        client.collection.return_value.document.return_value.collection.return_value.document.return_value.get
    )
    snapshot = snapshot_get.return_value
    snapshot.update_time = datetime(2026, 1, 1, tzinfo=timezone.utc)
    snapshot.to_dict.return_value = {'sync_content_revision': 3}
    firestore_client = Mock(return_value=client)
    monkeypatch.setattr(_client, 'get_firestore_client', firestore_client)
    token = Mock(return_value='fixture-token')
    monkeypatch.setattr(worker_client, 'identity_token', token)
    request = Mock(return_value=Mock(status_code=200))
    monkeypatch.setattr(httpx, 'post', request)

    assert episode_finalize.attach_synced_at_intake(_UID, 'clip', {'sync_content_revision': 3}) == 'joined'
    canonical.assert_called_once_with(_UID, 'clip', {'source': None, 'sync_content_revision': 3})
    firestore_client.assert_not_called()
    token.assert_not_called()
    request.assert_not_called()

    monkeypatch.setenv('SYNC_EPISODE_INTAKE_ORIGIN', 'https://workerd.fixture.test')
    monkeypatch.setenv('WORKER_EPISODE_INTAKE_AUDIENCE', 'fixture-audience')
    assert episode_finalize.attach_synced_at_intake(_UID, 'clip', {'sync_content_revision': 2}) == 'joined'
    request.assert_not_called()
    assert episode_finalize.attach_synced_at_intake(_UID, 'clip', {'sync_content_revision': 3}) == 'joined'
    request.assert_called_once_with(
        'https://workerd.fixture.test/internal/finalization/episode-intake',
        json={'owner': _UID, 'conversation': 'clip', 'written': snapshot.update_time.isoformat()},
        headers={'Authorization': 'Bearer fixture-token'},
        follow_redirects=False,
        timeout=5.0,
    )
    canonical.return_value = 'skipped_discarded'
    assert episode_finalize.attach_synced_at_intake(_UID, 'clip', {'sync_content_revision': 3}) == 'skipped_discarded'
    token.assert_called_once_with('fixture-audience')


@pytest.fixture
def v3_finish_route(conv, monkeypatch):
    monkeypatch.setenv('OMI_ENV_STAGE', 'offline')
    store = v3_finish.conversations_v3_live
    now = datetime.now(timezone.utc)
    window = {
        'id': 'window',
        'created_at': now,
        'started_at': now,
        'finished_at': now,
        'structured': {'title': 'Live window'},
        'status': 'in_progress',
        'tile_state': 'live',
        'v3_derived': True,
        'v3_recording_ids': ['older', 'latest'],
    }
    owner_path = ('users', _UID, 'conversations')
    paths = {name: (*owner_path, name) for name in ('window', 'older', 'latest')}
    recording = {'recording': True, 'status': 'completed', 'finished_at': now}
    db = StrictFirestore({paths['window']: window, paths['older']: dict(recording), paths['latest']: recording})
    monkeypatch.setattr(store, 'get_firestore_client', lambda: db)
    read_document = StrictFirestoreDocument.get

    def read_finish_fields(ref, *args, field_paths=None, **kwargs):
        if ref.path == paths['window'] and kwargs.get('transaction') is not None:
            assert field_paths == FINISH_FIELDS
        if field_paths in (store.LIVE_FIELDS, FINISH_FIELDS):
            snapshot = read_document(ref, *args, **kwargs)
            return type(snapshot)(
                {key: value for key, value in (snapshot.to_dict() or {}).items() if key in field_paths}
            )
        return read_document(ref, *args, field_paths=field_paths, **kwargs)

    monkeypatch.setattr(StrictFirestoreDocument, 'get', read_finish_fields)
    monkeypatch.setattr(store.firestore, 'transactional', lambda body: body)
    monkeypatch.setattr(conv, 'retrieve_in_progress_conversation', lambda uid: None)
    monkeypatch.setattr(v3_finish, 'conversations_v3_enabled', lambda uid: True)
    monkeypatch.delenv('CONVERSATIONS_V3_FINISH_NO_POINTER', raising=False)
    monkeypatch.delenv('CONVERSATIONS_V3_BATCH_MANUAL_END', raising=False)

    def discover(uid, *, now, max_idle, pick):
        assert uid == _UID
        row = db.rows.get(paths['window'])
        return pick([row] if row else [], now)

    def recent_sources(collection, tx, now):
        snapshots = []
        for path, row in db.rows.items():
            if path[:-1] == owner_path and row['finished_at'] >= now - store.RECENT_FINISH_AGE:
                snapshot = read_document(collection.document(path[-1]), transaction=tx)
                snapshot.id = path[-1]
                snapshots.append(snapshot)
        return snapshots[: store.RECENT_FINISH_LIMIT]

    monkeypatch.setattr(store, '_recent_finish_sources', recent_sources)
    monkeypatch.setattr(store, 'live_window', discover)
    enqueued = []
    monkeypatch.setattr(v3_finish.triggers, 'enqueue', lambda uid, **kwargs: enqueued.append((uid, kwargs)))
    app = FastAPI()
    app.include_router(conv.router)
    uid_dependency = inspect.signature(conv.process_in_progress_conversation).parameters['uid'].default.dependency
    app.dependency_overrides[uid_dependency] = lambda: _UID
    with TestClient(app) as client:
        yield client, db, paths, enqueued


@pytest.mark.parametrize('audio_only', [False, True])
def test_finish_without_recording_pointer_ends_latest_source_once(v3_finish_route, audio_only):
    client, db, paths, enqueued = v3_finish_route
    latest = db.rows[paths['latest']]
    if audio_only:
        latest.update(record_lane_owner='batch_live_v1', server_batch_only=True)
    for result in (client.post('/v1/conversations', json={}), client.post('/v1/conversations')):
        assert result.status_code == 200
        assert result.json()['conversation']['id'] == 'window'
        assert result.json()['conversation']['status'] == 'processing'
        assert result.json()['messages'] == []
    latest = db.rows[paths['latest']]
    assert db.rows[paths['window']]['status'] == 'in_progress'
    assert 'v3_manual_end' not in db.rows[paths['older']]
    assert len(db.transactions) == 2
    assert len(db.transactions[0].updates) == 1
    assert not db.transactions[1].updates
    if audio_only:
        assert latest['v3_manual_end_requested'] is True
        assert 'v3_manual_end' not in latest
        assert 'v3_pending' not in latest
        assert enqueued == []
    else:
        assert latest['v3_manual_end'] is True
        assert latest['v3_pending'] is True
        assert latest['v3_pending_since'] is not None
        assert enqueued == [(_UID, {'manual_end_id': 'latest'})]


def test_finish_without_pointer_keeps_404_for_non_v3_owner(v3_finish_route, monkeypatch):
    client, db, _, _ = v3_finish_route
    monkeypatch.setattr(v3_finish, 'conversations_v3_enabled', lambda uid: False)
    assert client.post('/v1/conversations', json={}).status_code == 404
    assert db.transactions == []


def test_finish_without_pointer_kill_switch_restores_404(v3_finish_route, monkeypatch):
    client, db, _, _ = v3_finish_route
    monkeypatch.setenv('CONVERSATIONS_V3_FINISH_NO_POINTER', 'off')
    assert client.post('/v1/conversations', json={}).status_code == 404
    assert db.transactions == []


def test_finish_without_pointer_ignores_other_owners_window_id(v3_finish_route):
    client, db, paths, _ = v3_finish_route
    for name, path in paths.items():
        db.rows['users', 'other-owner', 'conversations', name] = db.rows.pop(path)
    assert client.post('/v1/conversations', json={'live_conversation_id': 'window'}).status_code == 404
    assert db.transactions == []


def test_finish_without_pointer_rechecks_window_is_live_before_writing(v3_finish_route, monkeypatch):
    client, db, paths, enqueued = v3_finish_route
    store = v3_finish.conversations_v3_live
    discover = store.live_window

    def close_after_lookup(*args, **kwargs):
        open_snapshot = dict(discover(*args, **kwargs))
        db.rows[paths['window']].update(status='processing', tile_state='writing')
        return open_snapshot

    monkeypatch.setattr(store, 'live_window', close_after_lookup)
    assert client.post('/v1/conversations', json={}).status_code == 404
    assert 'v3_manual_end' not in db.rows[paths['latest']]
    assert not enqueued


def test_finish_without_pointer_keeps_404_without_a_live_window(v3_finish_route):
    client, db, paths, _ = v3_finish_route
    db.rows[paths['window']].update(status='completed', tile_state='done')
    assert client.post('/v1/conversations', json={}).status_code == 404
    assert len(db.transactions) == 1
    assert not db.transactions[0].updates


@pytest.mark.parametrize('unit_count', [1, 2])
def test_first_finish_after_whole_batch_uses_real_completion_ledger(v3_finish_route, monkeypatch, unit_count):
    client, db, paths, enqueued = v3_finish_route
    latest = db.rows[paths['latest']]
    latest.update(record_lane_owner='batch_live_v1', server_batch_only=True, record_projection_revision=1)
    complete, ledger_path, _ = native_finish_completion(monkeypatch, db, _UID, 'latest', unit_count)
    assert complete(datetime.now(timezone.utc).timestamp())['outcome'] == 'success'
    assert 'processed_segment_ids' not in db.rows[ledger_path]

    assert client.post('/v1/conversations', json={}).status_code == 200
    assert latest['v3_manual_end'] and latest['v3_pending']
    assert client.post('/v1/conversations', json={}).status_code == 200
    assert not db.transactions[-1].updates
    assert enqueued == [(_UID, {'manual_end_id': 'latest'})]


def test_repeat_finish_after_whole_single_unit_projection_cuts(v3_finish_route, monkeypatch):
    client, db, paths, enqueued = v3_finish_route
    latest = db.rows[paths['latest']]
    latest.update(record_lane_owner='batch_live_v1', server_batch_only=True)
    complete, _, _ = native_finish_completion(monkeypatch, db, _UID, 'latest', 1)
    assert client.post('/v1/conversations', json={}).status_code == 200
    assert latest['v3_manual_end_requested']
    latest['record_projection_revision'] = 1
    assert client.post('/v1/conversations', json={}).status_code == 200
    assert not db.transactions[-1].updates and not enqueued

    assert complete(datetime.now(timezone.utc).timestamp())['outcome'] == 'success'
    assert client.post('/v1/conversations', json={}).status_code == 200
    assert latest['v3_manual_end'] and latest['v3_pending']
    assert enqueued == [(_UID, {'manual_end_id': 'latest'})]


@pytest.mark.parametrize(
    'unit_count,empty_outcome,other_content',
    [
        (1, 'silence', False),
        (1, 'no_recoverable_speech', True),
        (2, 'silence', True),
    ],
)
def test_silent_whole_batch_resolves_deferred_finish(
    v3_finish_route, monkeypatch, unit_count, empty_outcome, other_content
):
    client, db, paths, enqueued = v3_finish_route
    latest = db.rows[paths['latest']]
    latest.update(record_lane_owner='batch_live_v1', server_batch_only=True, has_content=False)
    if not other_content:
        db.rows[paths['window']]['v3_recording_ids'] = ['latest']
    complete, ledger, _ = native_finish_completion(
        monkeypatch, db, _UID, 'latest', unit_count, empty_outcome=empty_outcome
    )
    request = {'live_conversation_id': 'window'}
    assert client.post('/v1/conversations', json=request).json()['conversation']['tile_state'] == 'transcribing'
    assert latest['v3_manual_end_requested']
    assert complete(datetime.now(timezone.utc).timestamp()) is not None
    assert 'processed_segment_ids' not in db.rows[ledger]
    assert 'record_projection_revision' not in latest
    response = client.post('/v1/conversations', json=request)
    assert response.status_code == 200
    assert not db.transactions[-1].updates
    if other_content:
        assert latest['v3_manual_end'] and latest['v3_pending']
        assert response.json()['conversation']['tile_state'] == 'writing'
        assert enqueued == [(_UID, {'manual_end_id': 'latest'})]
    else:
        assert latest['v3_manual_end_requested'] is False and 'v3_manual_end' not in latest
        assert response.json()['conversation']['status'] == 'completed'
        assert response.json()['conversation']['tile_state'] == 'done'
        assert not enqueued


@pytest.mark.parametrize('marked_window', ['window', 'previous'])
def test_finish_rearms_resolved_marker_for_pending_batch(v3_finish_route, monkeypatch, marked_window):
    client, db, paths, enqueued = v3_finish_route
    latest = db.rows[paths['latest']]
    latest.update(
        record_lane_owner='batch_live_v1',
        server_batch_only=True,
        v3_manual_end_requested=False,
        **{FINISH_WINDOW_FIELD: marked_window},
    )
    counter = Mock()
    monkeypatch.setattr(v3_finish.metrics, 'FINISH_NO_POINTER', counter)

    result = client.post('/v1/conversations', json={})
    assert result.status_code == 200 and result.json()['conversation']['tile_state'] == 'transcribing'
    assert db.transactions[-1].updates == [
        (paths['latest'], {'v3_manual_end_requested': True, FINISH_WINDOW_FIELD: 'window'})
    ]
    counter.labels.assert_called_once_with('requested')
    assert not enqueued


@pytest.mark.parametrize('marked_window', ['window', 'previous'])
def test_finish_counts_new_cut_after_empty_marker(v3_finish_route, monkeypatch, marked_window):
    client, db, paths, enqueued = v3_finish_route
    latest = db.rows[paths['latest']]
    latest.update(
        record_lane_owner='batch_live_v1',
        server_batch_only=True,
        record_projection_revision=1,
        has_content=True,
        v3_manual_end_requested=False,
        **{FINISH_WINDOW_FIELD: marked_window},
    )
    complete, _, _ = native_finish_completion(monkeypatch, db, _UID, 'latest', 1)
    assert complete(datetime.now(timezone.utc).timestamp())['outcome'] == 'success'
    counter = Mock()
    monkeypatch.setattr(v3_finish.metrics, 'FINISH_NO_POINTER', counter)

    result = client.post('/v1/conversations', json={})
    assert result.status_code == 200 and result.json()['conversation']['tile_state'] == 'writing'
    assert latest['v3_manual_end'] and latest[FINISH_WINDOW_FIELD] == 'window'
    counter.labels.assert_called_once_with('cut')
    assert client.post('/v1/conversations', json={}).json()['conversation']['tile_state'] == 'writing'
    assert not db.transactions[-1].updates
    assert enqueued == [(_UID, {'manual_end_id': 'latest'})]


@pytest.mark.parametrize('whole_record_complete', [False, True])
@pytest.mark.parametrize('previous_end_offset', [-1, 0, 1, None])
def test_finish_only_retargets_pending_request_to_proven_later_tail(
    v3_finish_route, monkeypatch, whole_record_complete, previous_end_offset
):
    client, db, paths, enqueued = v3_finish_route
    latest = db.rows[paths['latest']]
    end = latest['finished_at']
    claims = [{'conversation_id': 'window', 'end': end}]
    if previous_end_offset is not None:
        claims.append({'conversation_id': 'previous', 'end': end + timedelta(seconds=previous_end_offset)})
    latest.update(
        record_lane_owner='batch_live_v1',
        server_batch_only=True,
        claims=claims,
        v3_manual_end_requested=True,
        **{FINISH_WINDOW_FIELD: 'previous'},
    )
    if whole_record_complete:
        latest.update(record_projection_revision=1, has_content=True)
        complete, _, _ = native_finish_completion(monkeypatch, db, _UID, 'latest', 1)
        assert complete(datetime.now(timezone.utc).timestamp())['outcome'] == 'success'
    counter = Mock()
    monkeypatch.setattr(v3_finish.metrics, 'FINISH_NO_POINTER', counter)

    result = client.post('/v1/conversations', json={})
    if previous_end_offset == -1:
        assert result.status_code == 200 and latest[FINISH_WINDOW_FIELD] == 'window'
        if whole_record_complete:
            assert latest['v3_manual_end'] and enqueued == [(_UID, {'manual_end_id': 'latest'})]
            counter.labels.assert_called_once_with('cut')
        else:
            assert latest['v3_manual_end_requested'] and not enqueued
            counter.labels.assert_called_once_with('requested')
    else:
        assert result.status_code == 404
        assert not db.transactions[-1].updates and not enqueued
        assert latest[FINISH_WINDOW_FIELD] == 'previous'
        counter.labels.assert_called_once_with('request_conflict')


def test_batch_manual_end_switch_disables_deferred_finish(v3_finish_route, monkeypatch):
    client, db, paths, enqueued = v3_finish_route
    db.rows[paths['latest']].update(record_lane_owner='batch_live_v1', server_batch_only=True)
    monkeypatch.setenv('CONVERSATIONS_V3_BATCH_MANUAL_END', 'off')
    assert client.post('/v1/conversations', json={}).status_code == 404
    assert not db.transactions[-1].updates and not enqueued


def test_finish_uses_explicit_owned_live_window(v3_finish_route, monkeypatch):
    client, db, paths, enqueued = v3_finish_route
    alternate = ('users', _UID, 'conversations', 'second')
    db.rows[alternate] = {**db.rows[paths['window']], 'id': 'second', 'v3_recording_ids': ['older']}
    monkeypatch.setattr(
        v3_finish.conversations_v3_live, 'live_window', lambda *a, **kw: pytest.fail('valid hint used fallback')
    )
    result = client.post('/v1/conversations', json={'live_conversation_id': 'second'})
    assert result.status_code == 200 and result.json()['conversation']['id'] == 'second'
    assert not db.rows[paths['latest']].get('v3_manual_end')
    assert db.rows[paths['older']]['v3_manual_end']
    assert enqueued == [(_UID, {'manual_end_id': 'older'})]


@pytest.mark.parametrize('owner,status', [('other-owner', 'in_progress'), (_UID, 'completed')])
def test_finish_falls_back_when_hint_is_foreign_or_stale(v3_finish_route, owner, status):
    client, db, paths, _ = v3_finish_route
    db.rows['users', owner, 'conversations', 'hint'] = {**db.rows[paths['window']], 'status': status}
    result = client.post('/v1/conversations', json={'live_conversation_id': 'hint'})
    assert result.status_code == 200 and result.json()['conversation']['id'] == 'window'


def test_finish_refuses_known_partial_audio_archive(v3_finish_route):
    client, db, paths, enqueued = v3_finish_route
    latest = db.rows[paths['latest']]
    latest.update(record_lane_owner='batch_live_v1', server_batch_only=True, record_audio_partial=True)
    assert client.post('/v1/conversations', json={}).status_code == 404
    assert not db.transactions[-1].updates and not enqueued


@pytest.fixture
def pre_window_finish_route(v3_finish_route):
    _, db, paths, _ = v3_finish_route
    now = db.rows.pop(paths['window'])['finished_at']
    db.rows[paths['latest']].update(
        created_at=now - timedelta(seconds=30),
        started_at=now - timedelta(seconds=30),
        source='omi',
        external_data={'recording_session_id': 'fixture-session'},
        v3_pending=True,
        has_content=True,
        v3_speech_landed_at=now,
    )
    return v3_finish_route


def test_empty_body_finish_before_first_window_cuts_recent_listen_recording(pre_window_finish_route):
    client, db, paths, enqueued = pre_window_finish_route
    for result in (client.post('/v1/conversations', json={}), client.post('/v1/conversations')):
        assert result.status_code == 200
        assert result.json()['conversation']['id'] == 'latest'
        assert result.json()['conversation']['tile_state'] == 'writing'
    latest = db.rows[paths['latest']]
    assert latest[FINISH_RECORDING_FIELD] and latest['v3_manual_end'] and latest['v3_pending']
    assert not db.transactions[-1].updates
    assert enqueued == [(_UID, {'manual_end_id': 'latest'})]


@pytest.mark.parametrize('empty_outcome', [None, 'silence'])
def test_empty_body_finish_before_first_batch_transcript_is_consumed(
    pre_window_finish_route, monkeypatch, empty_outcome
):
    client, db, paths, enqueued = pre_window_finish_route
    latest = db.rows[paths['latest']]
    latest.pop('v3_speech_landed_at')
    latest.update(
        record_lane_owner='batch_live_v1',
        server_batch_only=True,
        server_batch_audio_start=1,
        server_batch_audio_end=2,
    )
    complete, _, _ = native_finish_completion(monkeypatch, db, _UID, 'latest', 2, empty_outcome=empty_outcome)
    first = client.post('/v1/conversations', json={})
    assert first.status_code == 200 and first.json()['conversation']['tile_state'] == 'transcribing'
    assert latest[FINISH_RECORDING_FIELD] and latest['v3_manual_end_requested']
    assert not enqueued
    if empty_outcome is None:
        latest['record_projection_revision'] = 2
    else:
        latest['has_content'] = False
    assert complete(datetime.now(timezone.utc).timestamp()) is not None
    second = client.post('/v1/conversations', json={})
    assert second.status_code == 200 and not db.transactions[-1].updates
    if empty_outcome is None:
        assert latest['v3_manual_end'] and latest['v3_pending']
        assert second.json()['conversation']['tile_state'] == 'writing'
        assert enqueued == [(_UID, {'manual_end_id': 'latest'})]
    else:
        assert latest['v3_manual_end_requested'] is False and 'v3_manual_end' not in latest
        assert second.json()['conversation']['tile_state'] == 'done'
        assert not enqueued


@pytest.mark.parametrize('case', ['ambiguous', 'claimed', 'hinted', 'saturated', 'deleting'])
def test_finish_before_first_window_refuses_unproven_recording(pre_window_finish_route, monkeypatch, case):
    client, db, paths, enqueued = pre_window_finish_route
    latest = db.rows[paths['latest']]
    request = {}
    if case == 'ambiguous':
        db.rows[paths['older']] = {**latest, 'external_data': {'recording_session_id': 'other-session'}}
    elif case == 'claimed':
        latest['claims'] = [{'conversation_id': 'prior-window'}]
    elif case == 'saturated':
        for i in range(8):
            db.rows['users', _UID, 'conversations', f'window-{i}'] = {'finished_at': latest['finished_at']}
    elif case == 'deleting':
        from database.account_deletion_marker import account_deletion_document

        db.rows[account_deletion_document(_UID, firestore_client=db).path] = {'wipe_status': 'pending'}
    else:
        request['live_conversation_id'] = 'missing'

    assert client.post('/v1/conversations', json=request).status_code == 404
    assert not enqueued
    assert all(not tx.updates for tx in db.transactions)


def test_finish_before_first_window_refuses_recording_if_live_window_appears(pre_window_finish_route, monkeypatch):
    client, db, paths, enqueued = pre_window_finish_route
    store = v3_finish.conversations_v3_live
    monkeypatch.setattr(store, 'live_window', lambda *a, **kw: None)
    end = db.rows[paths['latest']]['finished_at']
    db.rows[paths['window']] = {
        'id': 'window',
        'started_at': end,
        'finished_at': end,
        'v3_derived': True,
        'status': 'in_progress',
        'tile_state': 'live',
    }
    assert client.post('/v1/conversations', json={}).status_code == 404
    assert not db.transactions[-1].updates and not enqueued
