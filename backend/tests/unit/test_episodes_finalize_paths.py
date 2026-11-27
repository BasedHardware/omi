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
from google.api_core.exceptions import Aborted

os.environ.setdefault(
    'ENCRYPTION_SECRET',
    'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv',
)
os.environ.setdefault('OPENAI_API_KEY', 'test-openai-key-not-real')

from database.account_deletion_marker import account_deletion_document
from database.sync_ledger import sync_content_ledger_ref
from config import episodes as config
from config.record_audio import record_identity
from models.conversation import Conversation
from models.conversation_enums import ConversationSource, ConversationStatus
from models.structured import Structured
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore, StrictFirestoreDocument
from utils.batch_pipeline.live_projection import replace_record
from utils.conversations.v3 import finish as v3_finish, live as v3_live, triggers
from utils.conversations.v3.live import FINISH_FIELDS, FINISH_RECORDING_FIELD, FINISH_STAMP_FIELD, FINISH_WINDOW_FIELD
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
            assert field_paths in (FINISH_FIELDS, store.NAMED_FINISH_FIELDS)
        if field_paths in (
            store.LIVE_FIELDS,
            FINISH_FIELDS,
            v3_live.FINISH_SOURCE_FIELDS,
            store.NAMED_FINISH_FIELDS,
            store.RECENT_FINISH_FIELDS,
        ):
            snapshot = read_document(ref, *args, **kwargs)
            data, masked = snapshot.to_dict() or {}, {}
            for path in field_paths:  # Firestore field masks, including one dotted map path.
                head, _, rest = path.partition('.')
                if head in data and not rest:
                    masked[head] = data[head]
                elif isinstance(data.get(head), dict) and rest in data[head]:
                    masked.setdefault(head, {})[rest] = data[head][rest]
            return type(snapshot)(masked)
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

    def recent_windows(collection, now, max_idle):
        query = Mock()
        snapshots = []
        for path, row in db.rows.items():
            if (
                path[:-1] == owner_path
                and row.get('v3_derived')
                and row['finished_at'] >= now - max_idle
                and row['started_at'] <= now + store.START_SKEW
            ):
                snapshots.append(collection.document(path[-1]))

        def stream(*, transaction):
            return [ref.get(transaction=transaction, field_paths=FINISH_FIELDS) for ref in snapshots[: store.READ_CAP]]

        query.order_by.return_value.select.return_value.limit.return_value.stream.side_effect = stream
        return query

    monkeypatch.setattr(store, '_recent_finish_sources', recent_sources)
    monkeypatch.setattr(store, '_recent_window_query', recent_windows)
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
    assert all(not tx.updates for tx in db.transactions)
    assert all(path[1] == 'other-owner' for path in db.rows if path[0] == 'users')


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
        assert response.json()['conversation']['discarded'] is False
        assert enqueued == [(_UID, {'manual_end_id': 'latest'})]
    else:
        assert latest['v3_manual_end_requested'] is False and 'v3_manual_end' not in latest
        assert response.json()['conversation']['status'] == 'completed'
        assert response.json()['conversation']['tile_state'] == 'done'
        assert response.json()['conversation']['discarded'] is True
        assert not enqueued


def test_finish_retry_preserves_earlier_window_speech_after_silent_tail(v3_finish_route, monkeypatch):
    client, db, paths, enqueued = v3_finish_route
    window = db.rows[paths['window']]
    latest = db.rows[paths['latest']]
    latest.update(record_lane_owner='batch_live_v1', server_batch_only=True, has_content=False)
    db.rows[paths['older']].update(has_content=True, record_projection_revision=1)
    complete, ledger, _ = native_finish_completion(monkeypatch, db, _UID, 'latest', 1, empty_outcome='silence')

    request = {'live_conversation_id': 'window'}
    assert client.post('/v1/conversations', json=request).json()['conversation']['tile_state'] == 'transcribing'
    window.update(status='processing', tile_state='writing')
    assert complete(latest['finished_at'].timestamp())['outcome'] == 'expected_silence'
    assert latest['v3_manual_end_requested'] is False
    db.rows[ledger]['result']['superseded_segments'] = 1
    window.update(status='in_progress', tile_state='live')

    response = client.post('/v1/conversations', json=request)
    assert response.status_code == 200
    conversation = response.json()['conversation']
    assert (conversation['id'], conversation['status'], conversation['tile_state'], conversation['discarded']) == (
        'window',
        'completed',
        'done',
        False,
    )
    assert not db.transactions[-1].updates and not enqueued


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
    stamp = latest[FINISH_STAMP_FIELD]
    assert stamp['path'] == 'tail' and isinstance(stamp['at'], datetime)
    assert db.transactions[-1].updates == [
        (paths['latest'], {'v3_manual_end_requested': True, FINISH_WINDOW_FIELD: 'window', FINISH_STAMP_FIELD: stamp})
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


@pytest.mark.parametrize(
    'unit_count,empty_outcome,replace_before_finish',
    [(1, None, True), (1, None, False), (2, None, False), (2, 'silence', False)],
)
def test_empty_body_finish_before_first_window_resolves_at_whole_record_completion(
    pre_window_finish_route, monkeypatch, unit_count, empty_outcome, replace_before_finish
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
    complete, ledger, _ = native_finish_completion(
        monkeypatch, db, _UID, 'latest', unit_count, empty_outcome=empty_outcome
    )
    counter = Mock()
    monkeypatch.setattr(v3_finish.metrics, 'FINISH_NO_POINTER', counter)

    def commit_single_unit_projection():
        projected, _ = replace_record(
            latest,
            {
                'started_at': latest['started_at'],
                'transcript_segments': [{'id': 'speech', 'start': 0, 'end': 1, 'text': 'Synthetic speech'}],
            },
            {
                'start': latest['started_at'].timestamp(),
                'end': latest['finished_at'].timestamp(),
                'whole_native_record': True,
            },
        )
        db.transaction().update(
            db.collection('users').document(_UID).collection('conversations').document('latest'), projected
        )
        assert latest['record_projection_revision'] == 1
        assert db.rows[ledger]['status'] == 'processing'
        assert 'v3_manual_end' not in latest

    if replace_before_finish:
        commit_single_unit_projection()
    first = client.post('/v1/conversations', json={})
    assert first.status_code == 200 and first.json()['conversation']['tile_state'] == 'transcribing'
    assert latest[FINISH_RECORDING_FIELD] and latest['v3_manual_end_requested']
    assert not enqueued
    counter.labels.assert_called_once_with('recording_requested')
    counter.reset_mock()
    if unit_count == 1:
        if not replace_before_finish:
            commit_single_unit_projection()
    elif empty_outcome is None:
        latest['record_projection_revision'] = 2
    else:
        latest['has_content'] = False

    for _ in range(2):
        assert complete(datetime.now(timezone.utc).timestamp()) is not None
    outcome = 'whole_record_consumed' if empty_outcome is None else 'whole_record_resolved_empty'
    counter.labels.assert_called_once_with(outcome)
    counter.labels.return_value.inc.assert_called_once_with()
    second = client.post('/v1/conversations', json={})
    assert second.status_code == 200 and not db.transactions[-1].updates
    if empty_outcome is None:
        assert latest['v3_manual_end'] and latest['v3_pending']
        assert second.json()['conversation']['tile_state'] == 'writing'
        assert enqueued == [(_UID, {'manual_end_id': 'latest'})]
    else:
        assert latest['v3_manual_end_requested'] is False and 'v3_manual_end' not in latest
        assert second.json()['conversation']['tile_state'] == 'done'
        assert second.json()['conversation']['discarded'] is True
        assert not enqueued


def test_finish_accepts_retained_audio_after_first_native_unit_is_silent(pre_window_finish_route, monkeypatch):
    client, db, paths, enqueued = pre_window_finish_route
    latest = db.rows[paths['latest']]
    latest.pop('v3_speech_landed_at')
    latest.update(
        record_lane_owner='batch_live_v1',
        server_batch_only=True,
        server_batch_audio_start=1,
        server_batch_audio_end=2,
    )
    complete, ledger, receipts = native_finish_completion(monkeypatch, db, _UID, 'latest', 2)
    _, first_unit = record_identity(_UID, 'latest')
    db.rows['synthetic_results', first_unit]['result']['outcome'] = 'silence'
    receipts[0].update(conversation_id=None, speech_seconds=0.0)
    receipts[1]['state'] = 'persisted'
    projected, _ = replace_record(
        latest,
        {'started_at': latest['started_at'], 'transcript_segments': []},
        {
            'start': latest['started_at'].timestamp(),
            'end': latest['finished_at'].timestamp(),
            'terminal_empty_outcome': 'silence',
        },
    )
    latest.update(projected)
    assert latest['has_content'] is False
    assert complete(latest['finished_at'].timestamp()) is None
    assert db.rows[ledger]['status'] == 'processing'

    reply = client.post('/v1/conversations')
    assert reply.status_code == 200 and reply.json()['conversation']['tile_state'] == 'transcribing'
    assert latest[FINISH_RECORDING_FIELD] and latest['v3_manual_end_requested'] is True
    assert 'v3_manual_end' not in latest and not enqueued


@pytest.mark.parametrize('use_window', [False, True])
@pytest.mark.parametrize('empty_outcome', ['silence', 'no_recoverable_speech'])
def test_first_finish_after_empty_batch_returns_discarded_acknowledgement(
    v3_finish_route, monkeypatch, use_window, empty_outcome
):
    client, db, paths, enqueued = v3_finish_route
    latest = db.rows[paths['latest']]
    end = latest['finished_at']
    latest.update(
        created_at=end - timedelta(seconds=30),
        started_at=end - timedelta(seconds=30),
        source='omi',
        external_data={'recording_session_id': 'fixture-session'},
        record_lane_owner='batch_live_v1',
        server_batch_only=True,
        has_content=False,
    )
    if use_window:
        db.rows[paths['window']]['v3_recording_ids'] = ['latest']
    else:
        db.rows.pop(paths['window'])

    complete, _, _ = native_finish_completion(monkeypatch, db, _UID, 'latest', 1, empty_outcome=empty_outcome)
    assert complete(end.timestamp()) is not None
    response = client.post('/v1/conversations', json={'live_conversation_id': 'window'} if use_window else {})
    assert response.status_code == 200
    body = response.json()
    conversation = body['conversation']
    assert body['messages'] == []
    assert (conversation['id'], conversation['status'], conversation['tile_state'], conversation['discarded']) == (
        'window' if use_window else 'latest',
        'completed',
        'done',
        True,
    )
    assert conversation['recording'] is (None if use_window else True)
    assert not latest.get('discarded') and not db.transactions[-1].updates and not enqueued
    if use_window:
        assert not db.rows[paths['window']].get('discarded')


@pytest.mark.parametrize('case', ['ambiguous', 'claimed', 'hinted', 'saturated', 'deleting'])
def test_finish_before_first_window_refuses_unproven_recording(pre_window_finish_route, monkeypatch, case):
    # 'hinted' names a missing window alongside another body field: not the app's Finish body.
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
        db.rows[account_deletion_document(_UID, firestore_client=db).path] = {'wipe_status': 'pending'}
    else:
        request.update(live_conversation_id='missing', unknown_future_client_field=True)

    assert client.post('/v1/conversations', json=request).status_code == 404
    assert not enqueued
    assert all(not tx.updates for tx in db.transactions)


@pytest.mark.parametrize('age', [timedelta(0), timedelta(minutes=30), v3_live.MAX_IDLE + timedelta(minutes=1)])
def test_finish_before_first_window_rechecks_full_live_horizon(pre_window_finish_route, monkeypatch, age):
    client, db, paths, enqueued = pre_window_finish_route
    store = v3_finish.conversations_v3_live
    monkeypatch.setattr(store, 'live_window', lambda *a, **kw: None)
    end = db.rows[paths['latest']]['finished_at'] - age
    db.rows[paths['window']] = {
        'id': 'window',
        'started_at': end,
        'finished_at': end,
        'v3_derived': True,
        'status': 'in_progress',
        'tile_state': 'live',
    }
    response = client.post('/v1/conversations', json={})
    if age > v3_live.MAX_IDLE:
        assert response.status_code == 200 and enqueued
    else:
        assert response.status_code == 404
        assert not db.transactions[-1].updates and not enqueued


@pytest.mark.parametrize(
    'payload',
    [
        {
            'calendar_meeting_context': {
                'calendar_event_id': 'meeting',
                'title': 'Calendar meeting',
                'start_time': '2026-11-25T09:00:00Z',
                'duration_minutes': 30,
            }
        },
        {'client_processing': {'projection': 'synthetic'}},
        {'client_processing': None},
        {'unknown_future_client_field': True},
    ],
)
def test_nonempty_finish_body_can_only_finish_a_window(pre_window_finish_route, payload):
    client, db, paths, enqueued = pre_window_finish_route
    latest = db.rows[paths['latest']]
    assert client.post('/v1/conversations', json=payload).status_code == 404
    assert not db.transactions and not enqueued
    assert FINISH_RECORDING_FIELD not in latest

    db.rows[paths['window']] = {
        'id': 'window',
        'started_at': latest['started_at'],
        'finished_at': latest['finished_at'],
        'created_at': latest['created_at'],
        'structured': {'title': 'Live window'},
        'v3_derived': True,
        'status': 'in_progress',
        'tile_state': 'live',
        'v3_recording_ids': ['latest'],
    }
    response = client.post('/v1/conversations', json=payload)
    assert response.status_code == 200 and response.json()['conversation']['id'] == 'window'
    assert latest[FINISH_WINDOW_FIELD] == 'window'
    assert FINISH_RECORDING_FIELD not in latest


@pytest.fixture
def sealed_named_route(v3_finish_route, monkeypatch):
    """A pendant capture sealed at a speech pause and the window it fed stopped being live."""
    client, db, paths, enqueued = v3_finish_route
    window = db.rows[paths['window']]
    now = window['finished_at']
    window.update(status='processing', tile_state='writing', home_hidden=True)
    db.rows[paths['latest']].update(
        created_at=now - timedelta(seconds=20),
        started_at=now - timedelta(seconds=20),
        source='omi',
        external_data={'recording_session_id': 'pendant-session'},
        claims=[{'conversation_id': 'window', 'start': now - timedelta(seconds=20), 'end': now}],
        has_content=True,
        v3_speech_landed_at=now,
    )
    counter = Mock()
    monkeypatch.setattr(v3_finish.metrics, 'FINISH_NO_POINTER', counter)
    return client, db, paths, enqueued, counter


@pytest.mark.parametrize('ended', ['writing', 'done', 'hidden_live'])
def test_named_finish_cuts_sealed_tail_of_window_that_left_live(sealed_named_route, ended):
    client, db, paths, enqueued, counter = sealed_named_route
    if ended == 'done':
        db.rows[paths['window']].update(status='completed', tile_state='done')
    elif ended == 'hidden_live':
        db.rows[paths['window']].update(status='in_progress', tile_state='live')

    response = client.post('/v1/conversations', json={'live_conversation_id': 'window'})

    assert response.status_code == 200
    conversation = response.json()['conversation']
    assert (conversation['id'], conversation['status'], conversation['tile_state']) == (
        'window',
        'processing',
        'writing',
    )
    latest = db.rows[paths['latest']]
    assert latest['v3_manual_end'] is True and latest['v3_pending'] is True
    assert latest[FINISH_WINDOW_FIELD] == 'window' and FINISH_RECORDING_FIELD not in latest
    assert 'v3_manual_end' not in db.rows[paths['older']]
    assert enqueued == [(_UID, {'manual_end_id': 'latest'})]
    counter.labels.assert_called_once_with('named_recording_cut')

    # A retry answers from the stored cut and writes nothing.
    counter.reset_mock()
    assert client.post('/v1/conversations', json={'live_conversation_id': 'window'}).status_code == 200
    assert not db.transactions[-1].updates and len(enqueued) == 1
    counter.labels.assert_called_once_with('already_cut')


def test_named_finish_cuts_named_raw_capture(pre_window_finish_route, monkeypatch):
    client, db, paths, enqueued = pre_window_finish_route
    counter = Mock()
    monkeypatch.setattr(v3_finish.metrics, 'FINISH_NO_POINTER', counter)

    response = client.post('/v1/conversations', json={'live_conversation_id': 'latest'})

    assert response.status_code == 200
    assert response.json()['conversation']['id'] == 'latest'
    assert response.json()['conversation']['tile_state'] == 'writing'
    latest = db.rows[paths['latest']]
    assert latest[FINISH_RECORDING_FIELD] and latest['v3_manual_end'] and latest['v3_pending']
    assert enqueued == [(_UID, {'manual_end_id': 'latest'})]
    counter.labels.assert_called_once_with('named_recording_cut')


def test_named_finish_picks_named_capture_among_recent_ones(pre_window_finish_route, monkeypatch):
    client, db, paths, enqueued = pre_window_finish_route
    latest = db.rows[paths['latest']]
    db.rows[paths['older']] = {**latest, 'external_data': {'recording_session_id': 'other-session'}}
    # Without a name two recent captures are ambiguous.
    assert client.post('/v1/conversations', json={}).status_code == 404
    assert all(not tx.updates for tx in db.transactions) and not enqueued

    response = client.post('/v1/conversations', json={'live_conversation_id': 'older'})

    assert response.status_code == 200 and response.json()['conversation']['id'] == 'older'
    assert db.rows[paths['older']]['v3_manual_end'] is True
    assert 'v3_manual_end' not in db.rows[paths['latest']]
    assert enqueued == [(_UID, {'manual_end_id': 'older'})]


@pytest.mark.parametrize(
    'case',
    [
        'stale',
        'private',
        'deleted',
        'window_deleted',
        'window_private',
        'window_merged',
        'foreign_claim',
        'unclaimed_tail',
        'live_window',
        'deleting',
    ],
)
def test_named_finish_refuses_unproven_capture(sealed_named_route, monkeypatch, case):
    client, db, paths, enqueued, counter = sealed_named_route
    latest = db.rows[paths['latest']]
    expected = 'named_not_finishable'
    if case == 'stale':
        old = latest['finished_at'] - timedelta(minutes=6)
        latest.update(created_at=old, started_at=old, finished_at=old)
        db.rows[paths['window']].update(started_at=old, finished_at=old)
    elif case == 'private':
        latest['data_protection_level'] = 'private'
    elif case == 'deleted':
        latest['deleted'] = True
    elif case == 'window_deleted':
        db.rows[paths['window']]['deleted'] = True
    elif case == 'window_private':
        db.rows[paths['window']]['data_protection_level'] = 'private'
    elif case == 'window_merged':
        db.rows[paths['window']]['sync_merged_into'] = 'survivor'
    elif case == 'unclaimed_tail':
        latest['claims'] = []
    elif case == 'foreign_claim':
        latest['claims'].append(
            {'conversation_id': 'other-window', 'start': latest['started_at'], 'end': latest['finished_at']}
        )
    elif case == 'live_window':
        # A live window the first lookup missed appears before the cut.
        db.rows['users', _UID, 'conversations', 'second'] = {
            **db.rows[paths['window']],
            'status': 'in_progress',
            'tile_state': 'live',
            'home_hidden': False,
            'v3_recording_ids': ['other'],
        }
        monkeypatch.setattr(v3_finish.conversations_v3_live, 'live_window', lambda *a, **kw: None)
        expected = 'no_live_window'
    else:
        db.rows[account_deletion_document(_UID, firestore_client=db).path] = {'wipe_status': 'pending'}
        expected = 'recording_ineligible'

    assert client.post('/v1/conversations', json={'live_conversation_id': 'window'}).status_code == 404
    assert all(not tx.updates for tx in db.transactions) and not enqueued
    assert 'v3_manual_end' not in latest
    counter.labels.assert_called_once_with(expected)


def test_named_missing_window_falls_back_to_single_capture(pre_window_finish_route, monkeypatch):
    client, db, paths, enqueued = pre_window_finish_route
    counter = Mock()
    monkeypatch.setattr(v3_finish.metrics, 'FINISH_NO_POINTER', counter)

    # The app's Finish body names a window that is gone: the single just-sealed capture is finished.
    response = client.post('/v1/conversations', json={'live_conversation_id': 'missing'})
    assert response.status_code == 200 and response.json()['conversation']['id'] == 'latest'
    counter.labels.assert_called_once_with('recording_cut')
    assert enqueued == [(_UID, {'manual_end_id': 'latest'})]


def test_named_missing_window_with_other_fields_keeps_404(pre_window_finish_route, monkeypatch):
    client, db, paths, enqueued = pre_window_finish_route
    counter = Mock()
    monkeypatch.setattr(v3_finish.metrics, 'FINISH_NO_POINTER', counter)
    body = {'live_conversation_id': 'missing', 'client_processing': None}
    assert client.post('/v1/conversations', json=body).status_code == 404
    assert all(not tx.updates for tx in db.transactions) and not enqueued
    counter.labels.assert_called_once_with('named_not_finishable')


def test_finish_only_body_is_empty_or_names_only_the_live_window():
    from models.conversation import ProcessConversationRequest

    assert ProcessConversationRequest.model_validate({}).finish_only_body
    assert ProcessConversationRequest.model_validate({'live_conversation_id': 'w'}).finish_only_body
    assert ProcessConversationRequest.model_validate({'live_conversation_id': None}).finish_only_body
    for body in ({'live_conversation_id': 'w', 'client_processing': None}, {'live_conversation_id': 'w', 'x': 1}):
        assert not ProcessConversationRequest.model_validate(body).finish_only_body


def test_null_live_conversation_id_finishes_like_an_empty_body(pre_window_finish_route):
    client, db, paths, enqueued = pre_window_finish_route
    response = client.post('/v1/conversations', json={'live_conversation_id': None})
    assert response.status_code == 200 and response.json()['conversation']['id'] == 'latest'
    assert db.rows[paths['latest']][FINISH_RECORDING_FIELD]
    assert enqueued == [(_UID, {'manual_end_id': 'latest'})]


def _later_capture(db, paths, *, owner='window-b', seconds_after=120):
    """Capture B sealed after the named window's tail A and fed window WB, hidden and never live."""
    a = db.rows[paths['latest']]
    end_a = a['finished_at'] - timedelta(seconds=seconds_after)
    a.update(created_at=end_a - timedelta(seconds=20), started_at=end_a - timedelta(seconds=20), finished_at=end_a)
    a['claims'][0].update(start=a['started_at'], end=end_a)
    db.rows[paths['window']].update(started_at=a['started_at'], finished_at=end_a)
    end_b = end_a + timedelta(seconds=seconds_after)
    b_path = ('users', _UID, 'conversations', 'capture-b')
    db.rows[b_path] = {
        **a,
        'created_at': end_b - timedelta(seconds=15),
        'started_at': end_b - timedelta(seconds=15),
        'finished_at': end_b,
        'v3_speech_landed_at': end_b,
        'external_data': {'recording_session_id': 'pendant-session-b'},
        'claims': [{'conversation_id': owner, 'start': end_b - timedelta(seconds=15), 'end': end_b}] if owner else [],
    }
    if owner:
        db.rows['users', _UID, 'conversations', owner] = {
            'id': owner,
            'created_at': end_b - timedelta(seconds=15),
            'started_at': end_b - timedelta(seconds=15),
            'finished_at': end_b,
            'status': 'in_progress',
            'tile_state': 'live',
            'home_hidden': True,
            'v3_derived': True,
            'v3_recording_ids': ['capture-b'],
        }
    return a, db.rows[b_path]


@pytest.mark.parametrize('owner', ['window-b', None])
def test_named_finish_cuts_capture_that_sealed_after_the_named_window(sealed_named_route, owner):
    client, db, paths, enqueued, counter = sealed_named_route
    a, b = _later_capture(db, paths, owner=owner)
    if owner is None:
        b['v3_pending'] = True

    response = client.post('/v1/conversations', json={'live_conversation_id': 'window'})

    assert response.status_code == 200
    assert response.json()['conversation']['id'] == (owner or 'capture-b')
    assert b['v3_manual_end'] is True and b['v3_pending'] is True
    if owner:
        assert b[FINISH_WINDOW_FIELD] == owner
    else:
        assert b[FINISH_RECORDING_FIELD] is True
    assert 'v3_manual_end' not in a and FINISH_WINDOW_FIELD not in a
    assert enqueued == [(_UID, {'manual_end_id': 'capture-b'})]
    counter.labels.assert_called_once_with('named_recording_cut')


@pytest.mark.parametrize('owner', ['window-b', None])
def test_strict_named_finish_never_moves_to_a_later_capture(sealed_named_route, owner):
    # The mixed legacy/v3 Finish (SCA-2918) asks for exactly the named target: no supersession.
    client, db, paths, enqueued, counter = sealed_named_route
    a, b = _later_capture(db, paths, owner=owner)

    assert v3_finish.finish_live_window(_UID, 'window', named_only=True) is None

    assert all(not tx.updates for tx in db.transactions) and not enqueued
    assert 'v3_manual_end' not in a and 'v3_manual_end' not in b
    counter.labels.assert_called_once_with('named_superseded')


@pytest.mark.parametrize('case', ['private', 'two_owners', 'not_window_tail', 'tie'])
def test_named_finish_declines_when_the_later_capture_is_unproven(sealed_named_route, case):
    client, db, paths, enqueued, counter = sealed_named_route
    a, b = _later_capture(db, paths)
    expected = 'named_superseded'
    if case == 'private':
        b['data_protection_level'] = 'private'
    elif case == 'two_owners':
        b['claims'].append({'conversation_id': 'window-c', 'start': b['started_at'], 'end': b['finished_at']})
    elif case == 'not_window_tail':
        db.rows['users', _UID, 'conversations', 'window-b']['v3_recording_ids'] = ['capture-b', 'capture-c']
    else:
        db.rows['users', _UID, 'conversations', 'capture-c'] = {
            **b,
            'external_data': {'recording_session_id': 'pendant-session-c'},
        }
        expected = 'recording_ambiguous'

    assert client.post('/v1/conversations', json={'live_conversation_id': 'window'}).status_code == 404
    assert all(not tx.updates for tx in db.transactions) and not enqueued
    assert 'v3_manual_end' not in a and 'v3_manual_end' not in b
    counter.labels.assert_called_once_with(expected)


def test_named_finish_leaves_a_completed_visible_window_as_it_is(sealed_named_route):
    client, db, paths, enqueued, counter = sealed_named_route
    db.rows[paths['window']].update(
        status='completed',
        tile_state='done',
        home_hidden=False,
        starred=True,
        structured={'title': 'Morning standup', 'overview': 'Planned the release train.', 'emoji': '🗓️'},
    )

    response = client.post('/v1/conversations', json={'live_conversation_id': 'window'})

    assert response.status_code == 200
    conversation = response.json()['conversation']
    assert (conversation['id'], conversation['status'], conversation['tile_state']) == ('window', 'completed', 'done')
    assert not conversation.get('discarded')
    # The app replaces the visible card with this row, so it carries the card's own fields.
    assert conversation['structured']['title'] == 'Morning standup'
    assert conversation['structured']['overview'] == 'Planned the release train.'
    assert conversation['structured']['emoji'] == '🗓️'
    assert conversation['starred'] is True
    assert all(not tx.updates for tx in db.transactions) and not enqueued
    assert 'v3_manual_end' not in db.rows[paths['latest']]
    counter.labels.assert_called_once_with('already_visible')


def _rotated_successor(db, a, *, speech):
    """A speech-pause rotation writes the next capture in progress before it seals A."""
    later = a['finished_at'] + timedelta(seconds=2)
    row = {
        'created_at': later,
        'started_at': later,
        'finished_at': later,
        'status': 'in_progress',
        'source': 'omi',
        'external_data': {'recording_session_id': 'pendant-session-next'},
        'structured': {},
    }
    if speech:
        row.update(recording=True, has_content=True, v3_speech_landed_at=later, v3_pending=True)
    db.rows['users', _UID, 'conversations', 'capture-next'] = row
    return row


@pytest.mark.parametrize('speech', [False, True])
def test_named_finish_ignores_in_progress_successor(sealed_named_route, speech):
    client, db, paths, enqueued, counter = sealed_named_route
    a = db.rows[paths['latest']]
    successor = _rotated_successor(db, a, speech=speech)

    response = client.post('/v1/conversations', json={'live_conversation_id': 'window'})

    assert response.status_code == 200 and response.json()['conversation']['id'] == 'window'
    assert a['v3_manual_end'] is True and a[FINISH_WINDOW_FIELD] == 'window'
    assert 'v3_manual_end' not in successor
    assert enqueued == [(_UID, {'manual_end_id': 'latest'})]
    counter.labels.assert_called_once_with('named_recording_cut')


def test_empty_body_finish_ignores_in_progress_successor(pre_window_finish_route):
    client, db, paths, enqueued = pre_window_finish_route
    a = db.rows[paths['latest']]
    successor = _rotated_successor(db, a, speech=True)

    response = client.post('/v1/conversations', json={})

    assert response.status_code == 200 and response.json()['conversation']['id'] == 'latest'
    assert a[FINISH_RECORDING_FIELD] and a['v3_manual_end']
    assert 'v3_manual_end' not in successor
    assert enqueued == [(_UID, {'manual_end_id': 'latest'})]


@pytest.mark.parametrize('case', ['claimed', 'unclaimed', 'claimed_between'])
def test_named_finish_retry_on_later_capture_cuts_once(sealed_named_route, case):
    client, db, paths, enqueued, counter = sealed_named_route
    a, b = _later_capture(db, paths, owner='window-b' if case == 'claimed' else None)
    if case != 'claimed':
        b['v3_pending'] = True
    first = client.post('/v1/conversations', json={'live_conversation_id': 'window'})
    assert first.status_code == 200 and b['v3_manual_end'] is True
    assert enqueued == [(_UID, {'manual_end_id': 'capture-b'})]
    if case == 'claimed_between':
        # The planner claims B for a hidden window between the two taps.
        b['claims'] = [{'conversation_id': 'window-b', 'start': b['started_at'], 'end': b['finished_at']}]
        db.rows['users', _UID, 'conversations', 'window-b'] = {
            'id': 'window-b',
            'created_at': b['started_at'],
            'started_at': b['started_at'],
            'finished_at': b['finished_at'],
            'status': 'in_progress',
            'tile_state': 'live',
            'home_hidden': True,
            'v3_derived': True,
            'v3_recording_ids': ['capture-b'],
        }
    counter.reset_mock()
    writes = sum(len(tx.updates) for tx in db.transactions)

    second = client.post('/v1/conversations', json={'live_conversation_id': 'window'})

    assert second.status_code == 200
    assert sum(len(tx.updates) for tx in db.transactions) == writes
    assert len(enqueued) == 1 and 'v3_manual_end' not in a
    counter.labels.assert_called_once_with('already_cut')


_B = ('users', _UID, 'conversations', 'capture-b')


@pytest.fixture
def newer_capture_route(v3_finish_route, monkeypatch):
    """A's window is still live, idle two minutes; capture B sealed after it and no window holds B yet."""
    client, db, paths, enqueued = v3_finish_route
    window = db.rows[paths['window']]
    sealed_b = window['finished_at'] - timedelta(seconds=5)
    end_a = sealed_b - timedelta(minutes=2)
    window.update(created_at=end_a - timedelta(minutes=1), started_at=end_a - timedelta(minutes=1), finished_at=end_a)
    db.rows[paths['older']]['finished_at'] = end_a - timedelta(seconds=30)
    db.rows[paths['latest']]['finished_at'] = end_a
    db.rows[_B] = {
        'created_at': sealed_b - timedelta(seconds=80),
        'started_at': sealed_b - timedelta(seconds=80),
        'finished_at': sealed_b,
        'status': 'completed',
        'recording': True,
        'source': 'omi',
        'external_data': {'recording_session_id': 'pendant-session-b'},
        'v3_pending': True,
        'has_content': True,
        'v3_speech_landed_at': sealed_b,
    }
    counter = Mock()
    monkeypatch.setattr(v3_finish.metrics, 'FINISH_NO_POINTER', counter)
    monkeypatch.delenv('CONVERSATIONS_V3_FINISH_NEWER_CAPTURE', raising=False)
    return client, db, paths, enqueued, counter


def _batch_pending(row):
    """B is a server-batch capture whose whole-record transcript is still pending (no ledger yet)."""
    row.pop('v3_speech_landed_at')
    row.update(
        record_lane_owner='batch_live_v1', server_batch_only=True, server_batch_audio_start=1, server_batch_audio_end=2
    )


def _batch_speech_landed(row):
    """B is a server-batch capture whose projection already landed speech; its whole record is still pending."""
    _batch_pending(row)
    row['record_projection_revision'] = 1


def _batch_tail(db, paths):
    """A, the window tail, is a server-batch capture too; its ledger read must also precede every write."""
    db.rows[paths['latest']].update(
        record_lane_owner='batch_live_v1', server_batch_only=True, server_batch_audio_start=1, server_batch_audio_end=2
    )


def _writes(db):
    return sum(len(tx.updates) for tx in db.transactions)


@pytest.mark.parametrize('lane', ['live', 'batch'])
@pytest.mark.parametrize('body', [{}, {'live_conversation_id': 'window'}])
def test_live_window_finish_moves_to_a_newer_capture_whose_speech_landed(newer_capture_route, lane, body):
    client, db, paths, enqueued, counter = newer_capture_route
    b = db.rows[_B]
    if lane == 'batch':
        _batch_speech_landed(b)

    response = client.post('/v1/conversations', json=body)

    assert response.status_code == 200
    conversation = response.json()['conversation']
    assert conversation['id'] == 'capture-b'
    assert conversation['tile_state'] == ('transcribing' if lane == 'batch' else 'writing')
    assert b[FINISH_RECORDING_FIELD] is True and FINISH_WINDOW_FIELD not in b
    if lane == 'batch':
        assert b['v3_manual_end_requested'] is True and 'v3_manual_end' not in b and not enqueued
        counter.labels.assert_called_once_with('newer_recording_requested')
    else:
        assert b['v3_manual_end'] is True and enqueued == [(_UID, {'manual_end_id': 'capture-b'})]
        counter.labels.assert_called_once_with('newer_recording_cut')
    for name in ('older', 'latest'):
        assert 'v3_manual_end' not in db.rows[paths[name]] and 'v3_manual_end_requested' not in db.rows[paths[name]]
    assert db.rows[paths['window']]['status'] == 'in_progress'


@pytest.mark.parametrize('created_stamp', [False, True])
@pytest.mark.parametrize('tail_lane', ['live', 'batch'])
@pytest.mark.parametrize('body', [{}, {'live_conversation_id': 'window'}])
def test_live_window_finish_cuts_the_tail_and_requests_a_pending_batch_capture(
    newer_capture_route, tail_lane, body, created_stamp
):
    """A silent or still-untranscribed B looks the same at Finish: A is cut now and B's request rides along."""
    client, db, paths, enqueued, counter = newer_capture_route
    b, a = db.rows[_B], db.rows[paths['latest']]
    _batch_pending(b)
    if created_stamp:
        # Production's mark_new stamps the landing field when the recording is created, before any speech.
        b['v3_speech_landed_at'] = b['created_at']
    if tail_lane == 'batch':
        _batch_tail(db, paths)

    response = client.post('/v1/conversations', json=body)

    assert response.status_code == 200
    conversation = response.json()['conversation']
    # The cut landed on A's window, so the answer names it.
    assert conversation['id'] == 'window' and conversation['status'] == 'processing'
    assert b['v3_manual_end_requested'] is True and b[FINISH_RECORDING_FIELD] is True and 'v3_manual_end' not in b
    assert a[FINISH_WINDOW_FIELD] == 'window'
    if tail_lane == 'batch':
        assert a['v3_manual_end_requested'] is True and 'v3_manual_end' not in a and not enqueued
        assert conversation['tile_state'] == 'transcribing'
        counter.labels.assert_called_once_with('newer_dual_requested')
    else:
        assert a['v3_manual_end'] is True and enqueued == [(_UID, {'manual_end_id': 'latest'})]
        assert conversation['tile_state'] == 'writing'
        counter.labels.assert_called_once_with('newer_dual_cut')
    # One transaction stored both, every read before either write (StrictFirestore enforces the order).
    assert len(db.transactions) == 1 and len(db.transactions[0].updates) == 2
    assert 'v3_manual_end' not in db.rows[paths['older']]


@pytest.mark.parametrize('between', ['nothing', 'b_resolved_silent', 'b_promoted', 'claimed_by_hidden_window'])
def test_live_window_finish_retry_after_tail_and_request_never_cuts_again(newer_capture_route, between):
    client, db, paths, enqueued, counter = newer_capture_route
    b, a = db.rows[_B], db.rows[paths['latest']]
    _batch_pending(b)
    assert client.post('/v1/conversations', json={}).json()['conversation']['id'] == 'window'
    if between == 'b_resolved_silent':
        # Whole-record completion found B silent and cleared its request (_v3_finish_update).
        b.update(v3_manual_end_requested=False, has_content=False)
    elif between == 'b_promoted':
        # B had speech: its request became the cut, so B shows as its own card.
        b.update(v3_manual_end=True, v3_pending=True, record_projection_revision=1)
    elif between == 'claimed_by_hidden_window':
        b['claims'] = [{'conversation_id': 'window-b', 'start': b['started_at'], 'end': b['finished_at']}]
        db.rows['users', _UID, 'conversations', 'window-b'] = {
            **db.rows[paths['window']],
            'id': 'window-b',
            'started_at': b['started_at'],
            'finished_at': b['finished_at'],
            'home_hidden': True,
            'v3_recording_ids': ['capture-b'],
        }
    counter.reset_mock()
    writes = _writes(db)

    second = client.post('/v1/conversations', json={})

    assert second.status_code == 200 and second.json()['conversation']['id'] == 'window'
    assert _writes(db) == writes and enqueued == [(_UID, {'manual_end_id': 'latest'})]
    assert a['v3_manual_end'] is True
    counter.labels.assert_called_once_with('already_cut')


@pytest.mark.parametrize(
    'case', ['none', 'older_than_window', 'in_progress', 'silent', 'private', 'discarded', 'full_scan']
)
def test_live_window_finish_cuts_the_tail_without_a_newer_finishable_capture(newer_capture_route, case, monkeypatch):
    client, db, paths, enqueued, counter = newer_capture_route
    fallback = Mock()
    monkeypatch.setattr(v3_finish.conversations_v3_live, 'record_fallback', fallback)
    b = db.rows[_B]
    if case == 'full_scan':
        # The bounded scan fills with newer rows, so another newer capture may lie past it.
        for n in range(8):
            db.rows['users', _UID, 'conversations', f'rotated-{n}'] = {
                **b,
                'status': 'in_progress',
                'external_data': {'recording_session_id': f'rotated-{n}'},
            }
    elif case == 'none':
        del db.rows[_B]
    elif case == 'older_than_window':
        # An older overlapping source never moves the cut.
        b['finished_at'] = db.rows[paths['window']]['finished_at'] - timedelta(seconds=1)
    elif case == 'in_progress':
        b.update(status='in_progress')
    elif case == 'silent':
        b.update(has_content=False)
    elif case == 'private':
        b['data_protection_level'] = 'private'
    else:
        b['discarded'] = True

    response = client.post('/v1/conversations', json={})

    assert response.status_code == 200 and response.json()['conversation']['id'] == 'window'
    assert db.rows[paths['latest']]['v3_manual_end'] is True
    assert db.rows[paths['latest']][FINISH_WINDOW_FIELD] == 'window'
    # b is the retained object even when the case removed it from the store: Finish wrote neither field to it.
    assert 'v3_manual_end' not in b and 'v3_manual_end_requested' not in b
    assert case != 'none' or _B not in db.rows  # nor recreated B's document
    assert enqueued == [(_UID, {'manual_end_id': 'latest'})]
    counter.labels.assert_called_once_with('cut')
    if case == 'full_scan':
        fallback.assert_called_once_with(
            component='conversation_finalization',
            from_mode='newer_capture',
            to_mode='window_tail',
            reason='other',
            outcome='degraded',
        )
    else:
        fallback.assert_not_called()


@pytest.mark.parametrize('owner', ['window', 'window-b'])
def test_live_window_finish_leaves_a_claimed_newer_capture_to_its_window(newer_capture_route, owner):
    client, db, paths, enqueued, counter = newer_capture_route
    b = db.rows[_B]
    b['claims'] = [{'conversation_id': owner, 'start': b['started_at'], 'end': b['finished_at']}]

    response = client.post('/v1/conversations', json={})

    assert response.status_code == 200 and response.json()['conversation']['id'] == 'window'
    assert db.rows[paths['latest']]['v3_manual_end'] is True and 'v3_manual_end' not in b
    counter.labels.assert_called_once_with('cut')


@pytest.mark.parametrize('tie', [False, True])
def test_live_window_finish_cuts_the_newest_of_two_newer_captures(newer_capture_route, tie, monkeypatch):
    client, db, paths, enqueued, counter = newer_capture_route
    fallback = Mock()
    monkeypatch.setattr(v3_finish.conversations_v3_live, 'record_fallback', fallback)
    b = db.rows[_B]
    c = db.rows['users', _UID, 'conversations', 'capture-c'] = {
        **b,
        'finished_at': b['finished_at'] - timedelta(seconds=0 if tie else 10),
        'external_data': {'recording_session_id': 'phone-session-c'},
    }

    response = client.post('/v1/conversations', json={})

    # A 404 would read as "already closed" to the app and cut nothing; an exact tie cuts the tail instead.
    assert response.status_code == 200
    assert response.json()['conversation']['id'] == ('window' if tie else 'capture-b')
    assert 'v3_manual_end' not in c
    if tie:
        assert db.rows[paths['latest']]['v3_manual_end'] is True and 'v3_manual_end' not in b
        counter.labels.assert_called_once_with('cut')
        fallback.assert_called_once_with(
            component='conversation_finalization',
            from_mode='newer_capture',
            to_mode='window_tail',
            reason='other',
            outcome='degraded',
        )
    else:
        assert b['v3_manual_end'] is True and 'v3_manual_end' not in db.rows[paths['latest']]
        counter.labels.assert_called_once_with('newer_recording_cut')
        fallback.assert_not_called()


@pytest.mark.parametrize('case', ['tie', 'full_scan'])
def test_live_window_finish_records_degraded_targeting_once_across_transaction_retries(
    newer_capture_route, case, monkeypatch
):
    """The transaction body re-runs on contention; only the attempt that commits publishes the fallback."""
    client, db, paths, enqueued, counter = newer_capture_route
    store = v3_finish.conversations_v3_live
    fallback = Mock()
    monkeypatch.setattr(store, 'record_fallback', fallback)
    b = db.rows[_B]
    if case == 'tie':
        db.rows['users', _UID, 'conversations', 'capture-c'] = {
            **b,
            'external_data': {'recording_session_id': 'phone-session-c'},
        }
    else:
        for n in range(8):
            db.rows['users', _UID, 'conversations', f'rotated-{n}'] = {
                **b,
                'status': 'in_progress',
                'external_data': {'recording_session_id': f'rotated-{n}'},
            }
    # The first attempt loses on contention after the scan and before any write, as Firestore's commit would.
    cut_tail, attempts = store._finish_window_tail, []

    def contended_tail(*args, **kwargs):
        attempts.append(len(attempts) + 1)
        if len(attempts) == 1:
            raise Aborted('contention')
        return cut_tail(*args, **kwargs)

    def retrying(body):
        def run(tx):
            try:
                return body(tx)
            except Aborted:
                return body(tx)

        return run

    monkeypatch.setattr(store, '_finish_window_tail', contended_tail)
    monkeypatch.setattr(store.firestore, 'transactional', retrying)

    response = client.post('/v1/conversations', json={})

    assert response.status_code == 200 and response.json()['conversation']['id'] == 'window'
    assert attempts == [1, 2] and _writes(db) == 1
    assert db.rows[paths['latest']]['v3_manual_end'] is True and 'v3_manual_end' not in b
    counter.labels.assert_called_once_with('cut')
    fallback.assert_called_once_with(
        component='conversation_finalization',
        from_mode='newer_capture',
        to_mode='window_tail',
        reason='other',
        outcome='degraded',
    )


def _ledger(db, cid, **fields):
    content, _ = record_identity(_UID, cid)
    db.rows[sync_content_ledger_ref(db, _UID, content).path] = {
        'dispatch_protocol': 'batch_v1',
        'job_id': 'bp_' + content,
        **fields,
    }


@pytest.mark.parametrize('case', ['pending_without_content', 'landed_empty', 'ledger_empty'])
def test_live_window_finish_cuts_the_tail_when_the_newer_batch_capture_has_no_speech(newer_capture_route, case):
    client, db, paths, enqueued, counter = newer_capture_route
    b = db.rows[_B]
    _batch_pending(b)
    if case == 'pending_without_content':
        b.pop('has_content')  # no committed audio samples yet
    elif case == 'landed_empty':
        b.update(has_content=False, record_projection_revision=1)  # the projection found no speech
    else:
        # Whole record completed as silence before the projection cleared has_content: already_empty.
        _ledger(
            db,
            'capture-b',
            status='completed',
            batch_pipeline={'segment_ids': ['unit']},
            result={'outcome': 'expected_silence'},
        )

    response = client.post('/v1/conversations', json={})

    assert response.status_code == 200 and response.json()['conversation']['id'] == 'window'
    assert db.rows[paths['latest']]['v3_manual_end'] is True
    assert not any(key in b for key in ('v3_manual_end', 'v3_manual_end_requested', FINISH_RECORDING_FIELD))
    assert enqueued == [(_UID, {'manual_end_id': 'latest'})]
    counter.labels.assert_called_once_with('cut')


@pytest.mark.parametrize('lane', ['live', 'batch'])
@pytest.mark.parametrize('between', ['nothing', 'claimed_by_hidden_window', 'joined_live_window'])
def test_live_window_finish_retry_never_cuts_the_tail_as_well(newer_capture_route, lane, between):
    client, db, paths, enqueued, counter = newer_capture_route
    b = db.rows[_B]
    batch = lane == 'batch'
    if batch:
        _batch_speech_landed(b)
    assert client.post('/v1/conversations', json={}).json()['conversation']['id'] == 'capture-b'
    window = db.rows[paths['window']]
    claim = [{'conversation_id': 'window', 'start': b['started_at'], 'end': b['finished_at']}]
    if between == 'claimed_by_hidden_window':
        claim[0]['conversation_id'] = 'window-b'
        db.rows['users', _UID, 'conversations', 'window-b'] = {
            **window,
            'id': 'window-b',
            'started_at': b['started_at'],
            'finished_at': b['finished_at'],
            'home_hidden': True,
            'v3_recording_ids': ['capture-b'],
        }
        b['claims'] = claim
    elif between == 'joined_live_window':
        # B's transcript landed and the planner appended it to A's window.
        window.update(finished_at=b['finished_at'], v3_recording_ids=[*window['v3_recording_ids'], 'capture-b'])
        b['claims'] = claim
    counter.reset_mock()
    writes = _writes(db)

    second = client.post('/v1/conversations', json={})

    assert second.status_code == 200 and second.json()['conversation']['id'] in {'capture-b', 'window'}
    for name in ('older', 'latest'):
        assert 'v3_manual_end' not in db.rows[paths[name]] and 'v3_manual_end_requested' not in db.rows[paths[name]]
    assert len(enqueued) == (0 if batch else 1)
    if between == 'joined_live_window':
        # B is now the window tail, so the tail path answers; for a pending batch B it re-stamps the same
        # request on B itself. It never cuts A.
        counter.labels.assert_called_once_with('requested' if batch else 'already_cut')
        assert batch or _writes(db) == writes
    else:
        assert _writes(db) == writes
        counter.labels.assert_called_once_with('newer_already_requested' if batch else 'newer_already_cut')


@pytest.mark.parametrize(
    'change', ['locked', 'private', 'audio_partial', 'upload_failed', 'deleted', 'ledger_unavailable']
)
def test_live_window_finish_retry_cuts_the_tail_when_the_finished_capture_cannot_answer(newer_capture_route, change):
    """A 404 reads as "already closed" to the app (settleManualFinish), so the window tail is cut instead."""
    client, db, paths, enqueued, counter = newer_capture_route
    b = db.rows[_B]
    if change == 'ledger_unavailable':
        _batch_speech_landed(b)
    assert client.post('/v1/conversations', json={}).json()['conversation']['id'] == 'capture-b'
    if change == 'private':
        b['data_protection_level'] = 'private'
    elif change == 'ledger_unavailable':
        _ledger(db, 'capture-b', status='completed')  # no segment binding: the batch is unavailable
    else:
        b[
            {
                'locked': 'is_locked',
                'audio_partial': 'record_audio_partial',
                'upload_failed': 'record_upload_failed',
            }.get(change, change)
        ] = True
    counter.reset_mock()
    b_before = dict(b)

    response = client.post('/v1/conversations', json={})

    assert response.status_code == 200 and response.json()['conversation']['id'] == 'window'
    assert db.rows[paths['latest']]['v3_manual_end'] is True
    assert db.rows[_B] == b_before
    counter.labels.assert_called_once_with('cut')


def test_live_window_finish_retry_cuts_the_tail_once_the_finished_capture_resolved_empty(newer_capture_route):
    client, db, paths, enqueued, counter = newer_capture_route
    b = db.rows[_B]
    _batch_speech_landed(b)
    assert client.post('/v1/conversations', json={}).json()['conversation']['id'] == 'capture-b'
    # Whole-record completion found B silent and cleared the request (_v3_finish_update).
    b.update(v3_manual_end_requested=False, has_content=False)
    counter.reset_mock()

    response = client.post('/v1/conversations', json={})

    assert response.status_code == 200 and response.json()['conversation']['id'] == 'window'
    assert db.rows[paths['latest']]['v3_manual_end'] is True and 'v3_manual_end' not in b
    counter.labels.assert_called_once_with('cut')


def test_live_window_finish_ignores_an_unmarked_capture_older_than_an_active_finish(newer_capture_route):
    client, db, paths, enqueued, counter = newer_capture_route
    b = db.rows[_B]
    assert client.post('/v1/conversations', json={}).json()['conversation']['id'] == 'capture-b'
    # C sealed after A but before B: the person already finished after C's speech.
    c = db.rows['users', _UID, 'conversations', 'capture-c'] = {
        **{k: v for k, v in b.items() if k not in {FINISH_RECORDING_FIELD, 'v3_manual_end', 'v3_pending_since'}},
        'finished_at': b['finished_at'] - timedelta(seconds=10),
        'external_data': {'recording_session_id': 'phone-session-c'},
    }
    counter.reset_mock()
    writes = _writes(db)

    response = client.post('/v1/conversations', json={})

    assert response.status_code == 200 and response.json()['conversation']['id'] == 'capture-b'
    assert _writes(db) == writes and 'v3_manual_end' not in c
    assert 'v3_manual_end' not in db.rows[paths['latest']]
    counter.labels.assert_called_once_with('newer_already_cut')


def test_live_window_finish_newer_capture_refuses_an_account_being_deleted(newer_capture_route):
    client, db, paths, enqueued, counter = newer_capture_route
    db.rows[account_deletion_document(_UID, firestore_client=db).path] = {'wipe_status': 'pending'}

    assert client.post('/v1/conversations', json={}).status_code == 404

    assert _writes(db) == 0 and not enqueued
    assert all('v3_manual_end' not in row for row in db.rows.values())
    counter.labels.assert_called_once_with('newer_recording_ineligible')


def test_live_window_finish_newer_capture_kill_switch_restores_the_tail_cut(newer_capture_route, monkeypatch):
    client, db, paths, enqueued, counter = newer_capture_route
    monkeypatch.setenv('CONVERSATIONS_V3_FINISH_NEWER_CAPTURE', 'off')
    monkeypatch.setattr(
        v3_finish.conversations_v3_live,
        '_recent_finish_sources',
        lambda *a, **kw: pytest.fail('kill switch off still read recent captures'),
    )

    response = client.post('/v1/conversations', json={})

    assert response.status_code == 200 and response.json()['conversation']['id'] == 'window'
    assert db.rows[paths['latest']]['v3_manual_end'] is True and 'v3_manual_end' not in db.rows[_B]
    assert enqueued == [(_UID, {'manual_end_id': 'latest'})]
    counter.labels.assert_called_once_with('cut')


def _spy_request_finish(monkeypatch):
    calls = []
    real = v3_finish.conversations_v3_live.request_finish

    def spy(*args, **kwargs):
        calls.append(kwargs.get('newer_capture'))
        return real(*args, **kwargs)

    monkeypatch.setattr(v3_finish.conversations_v3_live, 'request_finish', spy)
    return calls


def test_named_only_finish_never_redirects_to_a_newer_capture(newer_capture_route, monkeypatch):
    # The holdout Finish (named_only) answers for the named window alone, even with the newer-capture flag on.
    client, db, paths, enqueued, counter = newer_capture_route
    calls = _spy_request_finish(monkeypatch)

    response = v3_finish.finish_live_window(_UID, 'window', named_only=True)

    assert calls == [False]
    assert response.conversation.id == 'window'
    assert db.rows[paths['latest']]['v3_manual_end'] is True
    assert all(field not in db.rows[_B] for field in ('v3_manual_end', FINISH_RECORDING_FIELD, FINISH_WINDOW_FIELD))
    assert enqueued == [(_UID, {'manual_end_id': 'latest'})]
    counter.labels.assert_called_once_with('cut')


@pytest.mark.parametrize('window_id', [None, 'window'])
def test_finish_outside_named_only_still_offers_the_newer_capture(newer_capture_route, monkeypatch, window_id):
    client, db, paths, enqueued, counter = newer_capture_route
    calls = _spy_request_finish(monkeypatch)

    response = v3_finish.finish_live_window(_UID, window_id)

    assert calls == [True]
    assert response.conversation.id == 'capture-b'
    counter.labels.assert_called_once_with('newer_recording_cut')


@pytest.mark.parametrize('b_lands', ['speech', 'silence'])
def test_one_finish_cuts_a_at_once_and_consumes_b_once_across_resolution_and_retry(
    newer_capture_route, monkeypatch, b_lands
):
    """End to end under StrictFirestore: Finish -> both stored -> B's whole record completes -> the same Finish again.

    One Finish may end two cards: A's window is cut at once; if B lands with speech, B's request becomes its own
    manual end. The response names A's window, and a retry answers the same target without writing.
    """
    client, db, paths, enqueued, counter = newer_capture_route
    a_path, body = paths['latest'], {'live_conversation_id': 'window'}
    # B as production creates it: Listen's in-progress create runs mark_new, which stamps v3_speech_landed_at
    # before any speech, then audio custody marks content and the capture seals. No projection yet.
    sealed = db.rows[_B]['finished_at']
    b = {
        'created_at': sealed - timedelta(seconds=80),
        'started_at': sealed - timedelta(seconds=80),
        'finished_at': sealed,
        'status': 'in_progress',
        'source': 'omi',
        'data_protection_level': 'enhanced',
        'external_data': {'recording_session_id': 'pendant-session-b', 'server_batch_only': True},
        'record_lane_owner': 'batch_live_v1',
    }
    monkeypatch.setattr(triggers, 'conversations_v3_enabled', lambda uid: True)
    triggers.mark_new(_UID, b)
    assert b['v3_speech_landed_at'] and b['recording'] is True
    b.update(status='completed', has_content=True, server_batch_audio_start=1, server_batch_audio_end=2)
    db.rows[_B] = b

    projection_txs = []  # the landing stand-in rewrites the whole row; it is not a Finish or completion write

    def writes_to(target, field):
        return [
            p
            for tx in db.transactions
            if tx not in projection_txs
            for path, p in tx.updates
            if path == target and p.get(field)
        ]

    def a_cuts():
        return writes_to(a_path, 'v3_manual_end')

    def b_requests():
        return writes_to(_B, 'v3_manual_end_requested')

    # 1-2. Finish: one transaction cuts A's tail and stores B's request; the answer names A's window.
    first = client.post('/v1/conversations', json=body)
    assert first.status_code == 200 and first.json()['conversation']['id'] == 'window'
    assert db.rows[a_path]['v3_manual_end'] is True and len(a_cuts()) == 1
    assert b['v3_manual_end_requested'] is True and b[FINISH_RECORDING_FIELD] is True and 'v3_manual_end' not in b
    assert enqueued == [(_UID, {'manual_end_id': 'latest'})]
    counter.labels.assert_called_once_with('newer_dual_cut')
    counter.reset_mock()

    # 3. B's batch projection lands, then the real whole-record completion consumes B's request (twice: once).
    complete, _, _ = native_finish_completion(
        monkeypatch, db, _UID, 'capture-b', 1, empty_outcome=None if b_lands == 'speech' else 'silence'
    )
    segments = [{'id': 'speech', 'start': 0, 'end': 1, 'text': 'Synthetic speech'}] if b_lands == 'speech' else []
    span = {'start': b['started_at'].timestamp(), 'end': b['finished_at'].timestamp()}
    span.update(whole_native_record=True) if segments else span.update(terminal_empty_outcome='silence')
    projected, _ = replace_record(b, {'started_at': b['started_at'], 'transcript_segments': segments}, span)
    projection_txs.append(db.transaction())
    projection_txs[0].update(
        db.collection('users').document(_UID).collection('conversations').document(_B[-1]), projected
    )
    assert 'v3_manual_end' not in b  # a recording-scoped request waits for the whole record
    for _ in range(2):
        complete(datetime.now(timezone.utc).timestamp())
    if b_lands == 'speech':
        assert b['v3_manual_end'] is True and b['v3_pending'] is True
        counter.labels.assert_called_once_with('whole_record_consumed')
    else:
        assert b['v3_manual_end_requested'] is False and 'v3_manual_end' not in b
        counter.labels.assert_called_once_with('whole_record_resolved_empty')
    assert len(b_requests()) == 1
    # Consuming B's request wakes B's own reconcile once; A's stays the single one from the Finish.
    assert enqueued == [(_UID, {'manual_end_id': 'latest'})] + (
        [(_UID, {'manual_end_id': 'capture-b'})] if b_lands == 'speech' else []
    )
    woken = list(enqueued)
    counter.reset_mock()
    writes = _writes(db)

    # 4. The same Finish again: the same target, nothing written, an "already" answer.
    retry = client.post('/v1/conversations', json=body)

    assert retry.status_code == 200 and retry.json()['conversation']['id'] == first.json()['conversation']['id']
    assert _writes(db) == writes
    counter.labels.assert_called_once_with('already_cut')
    assert len(a_cuts()) == 1 and len(b_requests()) == 1
    assert enqueued == woken
    assert db.rows[a_path]['v3_manual_end'] is True
    assert b.get('v3_manual_end') is (True if b_lands == 'speech' else None)


def _tx_reads(monkeypatch):
    """Paths of every transactional document read, in order. The recent-source scan is one query and not listed."""
    reads, get = [], StrictFirestoreDocument.get

    def recording(ref, *args, **kwargs):
        if kwargs.get('transaction') is not None:
            reads.append(ref.path)
        return get(ref, *args, **kwargs)

    monkeypatch.setattr(StrictFirestoreDocument, 'get', recording)
    return reads


def _ledger_path(db, cid):
    return sync_content_ledger_ref(db, _UID, record_identity(_UID, cid)[0]).path


@pytest.mark.parametrize('path', ['tail', 'newer', 'newer_dual'])
def test_live_window_finish_stamps_only_its_response_target(newer_capture_route, path):
    """One Finish-to-visible sample per Finish: the stamp lands on the source of the card the answer names."""
    client, db, paths, enqueued, counter = newer_capture_route
    b, a = db.rows[_B], db.rows[paths['latest']]
    if path == 'tail':
        del db.rows[_B]
    elif path == 'newer_dual':
        _batch_pending(b)
    before = datetime.now(timezone.utc)

    response = client.post('/v1/conversations', json={})

    assert response.status_code == 200
    assert response.json()['conversation']['id'] == ('capture-b' if path == 'newer' else 'window')
    target, other = (b, a) if path == 'newer' else (a, b)
    assert target[FINISH_STAMP_FIELD]['path'] == path
    assert before <= target[FINISH_STAMP_FIELD]['at'] <= datetime.now(timezone.utc)
    assert FINISH_STAMP_FIELD not in other and FINISH_STAMP_FIELD not in db.rows[paths['older']]
    if path == 'newer_dual':
        # B's request rides along unstamped, so B's own card never contributes a sample.
        assert b['v3_manual_end_requested'] is True and b[FINISH_RECORDING_FIELD] is True


@pytest.mark.parametrize('path', ['tail', 'newer', 'newer_dual'])
def test_retried_live_window_finish_keeps_the_first_stamp(newer_capture_route, path):
    client, db, paths, enqueued, counter = newer_capture_route
    b, a = db.rows[_B], db.rows[paths['latest']]
    if path == 'tail':
        del db.rows[_B]
    elif path == 'newer_dual':
        _batch_pending(b)
    first = client.post('/v1/conversations', json={}).json()['conversation']['id']
    target = b if path == 'newer' else a
    stamp, writes = dict(target[FINISH_STAMP_FIELD]), _writes(db)

    assert client.post('/v1/conversations', json={}).json()['conversation']['id'] == first

    assert _writes(db) == writes and target[FINISH_STAMP_FIELD] == stamp
    assert FINISH_STAMP_FIELD not in (a if path == 'newer' else b)


@pytest.mark.parametrize('target', ['tail', 'newer'])
def test_consuming_cut_keeps_the_stamp_of_the_finish_that_stored_the_request(newer_capture_route, target):
    """A batch request then its consuming cut: the second write never re-stamps, so the sample stays the first's."""
    client, db, paths, enqueued, counter = newer_capture_route
    b, a = db.rows[_B], db.rows[paths['latest']]
    if target == 'tail':
        del db.rows[_B]
        _batch_tail(db, paths)
        row, cid, outcomes = a, 'latest', ('requested', 'consumed')
    else:
        _batch_speech_landed(b)
        row, cid, outcomes = b, 'capture-b', ('newer_recording_requested', 'newer_consumed')
    client.post('/v1/conversations', json={})
    counter.labels.assert_called_once_with(outcomes[0])
    stamp = dict(row[FINISH_STAMP_FIELD])
    # The whole record completed with speech before the person tapped again.
    _ledger(
        db,
        cid,
        status='completed',
        batch_pipeline={'segment_ids': ['unit']},
        result={'outcome': 'success', 'new_memories': [cid]},
    )
    row.update(has_content=True, record_projection_revision=1)
    counter.reset_mock()

    client.post('/v1/conversations', json={})

    counter.labels.assert_called_once_with(outcomes[1])
    assert row['v3_manual_end'] is True and row[FINISH_STAMP_FIELD] == stamp


@pytest.mark.parametrize('reason', ['already_empty', 'batch_unavailable', 'batch_disabled', 'recording_ineligible'])
def test_live_window_finish_counts_a_declined_newer_capture_and_still_cuts_the_tail(
    newer_capture_route, monkeypatch, reason
):
    client, db, paths, enqueued, counter = newer_capture_route
    declined = Mock()
    monkeypatch.setattr(v3_finish.conversations_v3_live.v3_metrics, 'FINISH_NEWER_DECLINED', declined)
    b = db.rows[_B]
    if reason == 'already_empty':
        # The whole record completed as silence before the projection cleared has_content.
        _batch_pending(b)
        _ledger(
            db,
            'capture-b',
            status='completed',
            batch_pipeline={'segment_ids': ['unit']},
            result={'outcome': 'expected_silence'},
        )
    elif reason == 'batch_unavailable':
        _batch_speech_landed(b)
        _ledger(db, 'capture-b', status='completed')  # no segment binding
    elif reason == 'batch_disabled':
        _batch_speech_landed(b)
        monkeypatch.setenv('CONVERSATIONS_V3_BATCH_MANUAL_END', 'off')
    else:
        b['v3_pending'] = False  # a live-lane capture with nothing pending to cut
    b_before = dict(b)

    response = client.post('/v1/conversations', json={})

    # The window-tail fallback and its answer are unchanged; the answer is counted as the tail's outcome.
    assert response.status_code == 200 and response.json()['conversation']['id'] == 'window'
    assert db.rows[paths['latest']]['v3_manual_end'] is True
    assert db.rows[paths['latest']][FINISH_STAMP_FIELD]['path'] == 'tail'
    assert db.rows[_B] == b_before
    counter.labels.assert_called_once_with('cut')
    declined.labels.assert_called_once_with(reason)
    declined.labels.return_value.inc.assert_called_once_with()


@pytest.mark.parametrize('case', ['none', 'older_than_window', 'silent'])
def test_live_window_finish_without_a_newer_candidate_counts_no_decline(newer_capture_route, monkeypatch, case):
    client, db, paths, enqueued, counter = newer_capture_route
    declined = Mock()
    monkeypatch.setattr(v3_finish.conversations_v3_live.v3_metrics, 'FINISH_NEWER_DECLINED', declined)
    b = db.rows[_B]
    if case == 'none':
        del db.rows[_B]
    elif case == 'older_than_window':
        b['finished_at'] = db.rows[paths['window']]['finished_at'] - timedelta(seconds=1)
    else:
        b['has_content'] = False

    response = client.post('/v1/conversations', json={})

    assert response.status_code == 200 and response.json()['conversation']['id'] == 'window'
    assert db.rows[paths['latest']]['v3_manual_end'] is True
    counter.labels.assert_called_once_with('cut')
    declined.labels.assert_not_called()


def test_newer_capture_finish_labels_are_reachable_or_absent():
    """Every pre-initialised newer_* outcome is one request_finish can return; declines are counted apart."""
    from utils.conversations.v3 import metrics

    labels = {s.labels['outcome'] for f in metrics.FINISH_NO_POINTER.collect() for s in f.samples}
    assert not labels & {'newer_already_empty', 'newer_batch_unavailable', 'newer_batch_disabled'}
    declined = {s.labels['reason'] for f in metrics.FINISH_NEWER_DECLINED.collect() for s in f.samples}
    assert declined == set(metrics.FINISH_NEWER_DECLINED_REASONS)
    paths = {s.labels['path'] for f in metrics.FINISH_TO_VISIBLE.collect() for s in f.samples}
    assert paths == {'tail', 'newer', 'newer_dual'}


def test_server_batch_redirect_reads_the_capture_ledger_once(newer_capture_route, monkeypatch):
    """F2: speech landed, so the redirect is not the stored-both case and _finish_capture reads B's ledger itself."""
    client, db, paths, enqueued, counter = newer_capture_route
    _batch_speech_landed(db.rows[_B])
    reads = _tx_reads(monkeypatch)

    assert client.post('/v1/conversations', json={}).json()['conversation']['id'] == 'capture-b'

    counter.labels.assert_called_once_with('newer_recording_requested')
    # Window, tail, the deletion marker, then B's native ledger: one read each. A's ledger is never read.
    assert reads == [
        paths['window'],
        paths['latest'],
        account_deletion_document(_UID, firestore_client=db).path,
        _ledger_path(db, 'capture-b'),
    ]


def test_marked_pending_retry_reads_the_capture_ledger_once(newer_capture_route, monkeypatch):
    """F4: a retry on a marked, still-requested batch capture answers from B's ledger, read once by _finish_capture."""
    client, db, paths, enqueued, counter = newer_capture_route
    _batch_speech_landed(db.rows[_B])
    assert client.post('/v1/conversations', json={}).json()['conversation']['id'] == 'capture-b'
    counter.reset_mock()
    reads = _tx_reads(monkeypatch)

    assert client.post('/v1/conversations', json={}).json()['conversation']['id'] == 'capture-b'

    counter.labels.assert_called_once_with('newer_already_requested')
    assert reads == [
        paths['window'],
        paths['latest'],
        account_deletion_document(_UID, firestore_client=db).path,
        _ledger_path(db, 'capture-b'),
    ]


def test_stored_both_reads_each_ledger_once_before_any_write(newer_capture_route, monkeypatch):
    client, db, paths, enqueued, counter = newer_capture_route
    _batch_pending(db.rows[_B])
    _batch_tail(db, paths)
    reads = _tx_reads(monkeypatch)

    assert client.post('/v1/conversations', json={}).json()['conversation']['id'] == 'window'

    counter.labels.assert_called_once_with('newer_dual_requested')
    assert reads == [
        paths['window'],
        paths['latest'],
        account_deletion_document(_UID, firestore_client=db).path,
        _ledger_path(db, 'capture-b'),
        _ledger_path(db, 'latest'),
    ]
