"""Synthetic record ownership, raw-reference and annotation contracts."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import hashlib
import io
import json
import wave
from unittest.mock import Mock, call

import pytest

from config.batch_pipeline import live_record_enabled_for
from database.batch_pipeline_intake import AdmissionDisabled, admit
from database.batch_pipeline_store import due
from tests.unit.test_batch_pipeline_scheduler import MemoryStore
from utils.batch_pipeline.contracts import Priority, ProjectionBinding, WorkItem
from utils.batch_pipeline.live import record_identity, register_recording
from utils.batch_pipeline.live_projection import replace_record
from utils.batch_pipeline.source_audio import MAGIC, materialize, validate_reference
from utils.conversations import summary_delivery
from utils.enrichment.age_gate import expired
from utils.sync.assignment_errors import SyncAssignmentConflict
from tests.unit.test_batch_provider_stt import Outbox, Artifacts, Vendor, stage as provider_stage
from utils.batch_pipeline import record_provider


@pytest.mark.asyncio
async def test_drain_bounds_concurrency_and_passes_slow_partial(monkeypatch, caplog):
    from utils.batch_pipeline import live

    monkeypatch.setenv('RECORD_DRAIN_CONCURRENCY', '4')
    # This fixture deliberately starts the blocking partial in the first group.
    monkeypatch.setattr(live.random, 'shuffle', lambda segments: None)
    store = MemoryStore()
    for i in range(10):
        store.rows['jobs', str(i)] = {
            'owner_id': f'synthetic-{i}',
            'state': 'record_pending',
            'available_at': 0,
            'partial_coordinator': i == 0,
        }
    slow, full, release = asyncio.Event(), asyncio.Event(), asyncio.Event()
    active, peak, completed = 0, 0, []

    async def admit(store, pending):
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        try:
            if pending.get('partial_coordinator'):
                slow.set()
                await release.wait()
            else:
                if active == 4:
                    full.set()
                await slow.wait()
                await full.wait()
                completed.append(1)
        finally:
            active -= 1

    monkeypatch.setattr(live, 'admit_recording', admit)
    with caplog.at_level('INFO', logger=live.__name__):
        task = asyncio.create_task(live.drain_recordings(store))
        try:
            await asyncio.wait_for(full.wait(), timeout=1)
            for _ in range(50):
                if len(completed) == 9:
                    break
                await asyncio.sleep(0.001)
            assert len(completed) == 9
            assert not task.done()
            assert peak == 4
        finally:
            slow.set()
            full.set()
            release.set()
            await asyncio.wait_for(task, timeout=1)
    events = [r.getMessage() for r in caplog.records if 'event=batch_drain_pass' in r.getMessage()]
    assert len(events) == 1
    assert 'row_count=10 partial_count=1 seconds=' in events[0]
    assert all(row['state'] == 'record_pending' and 'expires_at' not in row for row in store.rows.values())


@pytest.mark.asyncio
async def test_drain_shuffles_selected_page_before_admission(monkeypatch):
    from utils.batch_pipeline import live

    monkeypatch.setenv('RECORD_DRAIN_BATCH', '3')
    monkeypatch.setenv('RECORD_DRAIN_CONCURRENCY', '1')
    monkeypatch.setattr(live.random, 'shuffle', lambda segments: segments.reverse())
    # Paging/shuffle test: no-op admissions; pacing is covered in test_record_drain_pacing.
    monkeypatch.setenv('RECORD_DRAIN_IDLE_WITHOUT_PROGRESS', 'off')
    store = MemoryStore()
    for segment in ('first', 'second', 'third'):
        store.rows['jobs', segment] = {
            'owner_id': f'synthetic-{segment}',
            'segment_id': segment,
            'state': 'record_pending',
            'available_at': 0,
        }
    admitted = []

    async def admit(store, pending):
        admitted.append(pending['segment_id'])

    monkeypatch.setattr(live, 'admit_recording', admit)
    assert await live.drain_recordings(store)
    assert admitted == ['third', 'second', 'first']


@pytest.mark.asyncio
@pytest.mark.parametrize('reverse', [False, True])
async def test_drain_joins_workers_before_propagating_store_failure(monkeypatch, reverse):
    from utils.batch_pipeline import live

    monkeypatch.setenv('RECORD_DRAIN_CONCURRENCY', '2')
    monkeypatch.setattr(live.random, 'shuffle', lambda segments: segments.reverse() if reverse else None)
    store = MemoryStore()
    store.rows['jobs', 'bad'] = {'owner_id': 'synthetic-bad', 'state': 'record_pending', 'available_at': 0}
    store.rows['jobs', 'slow'] = {'owner_id': 'synthetic-slow', 'state': 'record_pending', 'available_at': 0}
    original_run = store.run
    slow, release, failed = asyncio.Event(), asyncio.Event(), asyncio.Event()
    slow_workers = []

    async def run_blocking(executor, fn, *args, **kwargs):
        # Resolve fake DB calls without yielding to executor scheduling. The real
        # drain workers still run concurrently and admission blocks on release.
        return fn(*args, **kwargs)

    monkeypatch.setattr(live, 'run_blocking', run_blocking)

    def run(body):
        result = original_run(body)
        if isinstance(result, dict) and result.get('broken'):
            failed.set()
            raise RuntimeError('synthetic store failure')
        return result

    store.rows['jobs', 'bad']['broken'] = True
    monkeypatch.setattr(store, 'run', run)

    async def admit(store, pending):
        slow_workers.append(asyncio.current_task())
        slow.set()
        await release.wait()

    monkeypatch.setattr(live, 'admit_recording', admit)
    task = asyncio.create_task(live.drain_recordings(store))
    try:
        await asyncio.wait_for(slow.wait(), timeout=1)
        assert failed.is_set()
        assert not task.done()
    finally:
        release.set()
        with pytest.raises(RuntimeError, match='synthetic store failure'):
            await asyncio.wait_for(task, timeout=1)
    assert len(slow_workers) == 1
    assert slow_workers[0].done() and not slow_workers[0].cancelled()
    assert store.rows['jobs', 'slow']['available_at'] > 0


@pytest.mark.asyncio
async def test_drain_emits_one_identifier_free_pass_on_query_failure(monkeypatch, caplog):
    from utils.batch_pipeline import live

    def unavailable(*args):
        raise RuntimeError('synthetic-private-message')

    store = MemoryStore()
    monkeypatch.setattr(store, 'due', unavailable)
    with caplog.at_level('INFO', logger=live.__name__), pytest.raises(RuntimeError):
        await live.drain_recordings(store)
    assert len(caplog.records) == 1
    assert 'row_count=0 partial_count=0 seconds=' in caplog.text
    assert 'synthetic-private-message' not in caplog.text


@pytest.mark.parametrize(
    'raw,batch,concurrency',
    [(None, 100, 16), ('bad', 100, 16), ('0', 1, 1), ('-3', 1, 1), ('999', 500, 64), ('7', 7, 7)],
)
def test_record_drain_settings_are_bounded(monkeypatch, raw, batch, concurrency):
    from utils.batch_pipeline import live

    for name in ('RECORD_DRAIN_BATCH', 'RECORD_DRAIN_CONCURRENCY'):
        if raw is None:
            monkeypatch.delenv(name, raising=False)
        else:
            monkeypatch.setenv(name, raw)
    assert live.record_drain_batch() == batch
    assert live.record_drain_concurrency() == concurrency


@pytest.mark.parametrize(
    'state,limit,expected',
    [
        ('record_pending', 500, 500),
        ('record_pending', 999, 500),
        ('retry', 500, 100),
        ('record_recovery_waiting', 500, 100),
    ],
)
def test_due_record_page_keeps_available_at_order_and_accepts_larger_batch(state, limit, expected):
    query = Mock()
    query.collection.return_value = query
    query.where.return_value = query
    query.order_by.return_value = query
    query.limit.return_value = query
    query.stream.return_value = []
    assert due(query, 'batch_pipeline_test_live', state, 1000, limit) == []
    states = ['record_recovery_waiting', state] if state == 'record_pending' else [state]
    limits = [100, expected] if state == 'record_pending' else [expected]
    assert query.where.call_args_list == [
        request
        for candidate in states
        for request in (call('state', '==', candidate), call('available_at', '<=', 1000))
    ]
    assert query.order_by.call_args_list == [call('available_at')] * len(states)
    assert query.limit.call_args_list == [call(size) for size in limits]
    assert query.stream.call_count == len(states)


@pytest.mark.asyncio
@pytest.mark.parametrize('count,full', [(2, True), (1, False), (0, False)])
async def test_record_drain_uses_configured_page_and_reports_full(monkeypatch, count, full):
    from utils.batch_pipeline import live

    monkeypatch.setenv('RECORD_DRAIN_BATCH', '2')
    # Page-size test: no-op admissions; pacing is covered in test_record_drain_pacing.
    monkeypatch.setenv('RECORD_DRAIN_IDLE_WITHOUT_PROGRESS', 'off')
    store = MemoryStore()
    for i in range(count):
        store.rows['jobs', str(i)] = {'owner_id': f'synthetic-{i}', 'state': 'record_pending', 'available_at': 0}
    calls = []
    original_due = store.due

    def due(state, now, limit):
        calls.append((state, limit))
        return original_due(state, now, limit)

    async def no_admission(*args):
        return None

    monkeypatch.setattr(store, 'due', due)
    monkeypatch.setattr(live, 'admit_recording', no_admission)
    assert await live.drain_recordings(store) is full
    assert calls == [('record_pending', 2)]
    assert store.due('record_pending', live.time.time(), 100) == []


@pytest.mark.asyncio
@pytest.mark.parametrize('outcome', ['value_error', 'no_admission', 'admitted', 'already_deferred'])
@pytest.mark.parametrize('partial_complete', [False, True])
async def test_record_drain_defers_only_still_pending_rows(monkeypatch, outcome, partial_complete):
    from utils.batch_pipeline import live

    store = MemoryStore()
    store.rows['jobs', 'synthetic'] = {
        'owner_id': 'synthetic',
        'state': 'record_pending',
        'available_at': 0,
        'partial_coordinator': partial_complete,
        'partial_run': {'complete': partial_complete},
    }
    monkeypatch.setattr(live.time, 'time', lambda: 1000)

    async def admission(store, pending):
        if outcome == 'value_error':
            raise ValueError('retained capture not durable yet')
        if outcome == 'admitted':
            store.rows['jobs', 'synthetic']['state'] = 'ready'
        if outcome == 'already_deferred':
            store.rows['jobs', 'synthetic']['available_at'] = 2000
        return None

    monkeypatch.setattr(live, 'admit_recording', admission)
    await live.drain_recordings(store)
    row = store.rows['jobs', 'synthetic']
    assert row['state'] == ('ready' if outcome == 'admitted' else 'record_pending')
    delay = live.INVENTORY_POLL_SECONDS if partial_complete and outcome != 'value_error' else 60
    # An admitted row keeps only the selection lease; admission owns it from here.
    lease = 1000 + live.record_drain_lease_seconds()
    expected = lease if outcome == 'admitted' else max(2000 if outcome == 'already_deferred' else 0, 1000 + delay)
    assert row['available_at'] == expected


@pytest.mark.asyncio
@pytest.mark.parametrize('blocked_rows', [1, 2])
async def test_full_privacy_fenced_page_keeps_idle_wait_without_writing_fenced_rows(monkeypatch, blocked_rows):
    from utils.batch_pipeline import live
    from database.batch_pipeline_privacy import BatchPrivacyBlocked

    monkeypatch.setenv('RECORD_DRAIN_BATCH', '2')
    store = MemoryStore()
    for i in range(2):
        store.rows['jobs', str(i)] = {
            'owner_id': f'synthetic-{i}',
            'segment_id': str(i),
            'state': 'record_pending',
            'available_at': 0,
            'fenced': i < blocked_rows,
        }

    async def admission(store, pending):
        if pending['fenced']:
            raise BatchPrivacyBlocked('synthetic privacy fence')
        store.rows['jobs', pending['segment_id']]['state'] = 'ready'

    monkeypatch.setattr(live, 'admit_recording', admission)
    monkeypatch.setattr(live.time, 'time', lambda: 1000)
    assert await live.drain_recordings(store) is False
    for row in store.rows.values():
        # The selection lease is the only write; a fenced row is not deferred again.
        assert row['available_at'] == 1000 + live.record_drain_lease_seconds()
        assert row['state'] == ('record_pending' if row['fenced'] else 'ready')


@pytest.mark.asyncio
async def test_concurrent_replicas_admit_each_selected_row_once(monkeypatch):
    from utils.batch_pipeline import live

    monkeypatch.setenv('RECORD_DRAIN_CONCURRENCY', '4')
    store = MemoryStore()
    for i in range(8):
        store.rows['jobs', str(i)] = {
            'owner_id': f'synthetic-{i}',
            'segment_id': str(i),
            'state': 'record_pending',
            'available_at': 0,
        }
    admitted = []

    async def admission(store, pending):
        admitted.append(pending['segment_id'])
        await asyncio.sleep(0.01)
        raise ValueError('retained capture tail not durable yet')

    monkeypatch.setattr(live, 'admit_recording', admission)
    # Three replicas select the same page before any admission finishes.
    await asyncio.gather(*(live.drain_recordings(store) for _ in range(3)))
    assert sorted(admitted) == [str(i) for i in range(8)]
    now = live.time.time()
    for row in store.rows.values():
        # A failed admission releases its own lease to the ordinary 60 s retry.
        assert now < row['available_at'] <= now + 61


@pytest.mark.asyncio
async def test_drain_skips_a_row_leased_by_another_replica(monkeypatch):
    from utils.batch_pipeline import live

    store = MemoryStore()
    store.rows['jobs', 'synthetic'] = {'owner_id': 'synthetic', 'state': 'record_pending', 'available_at': 0}
    original_run = store.run
    calls = 0

    def run(body):
        nonlocal calls
        calls += 1
        if calls == 2:
            # Another replica's claim commits between selection and our claim.
            store.rows['jobs', 'synthetic']['available_at'] = live.time.time() + 900
        return original_run(body)

    async def admission(store, pending):
        raise AssertionError('leased row must not be admitted twice')

    monkeypatch.setattr(store, 'run', run)
    monkeypatch.setattr(live, 'admit_recording', admission)
    await live.drain_recordings(store)
    assert store.rows['jobs', 'synthetic']['state'] == 'record_pending'


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'error,reason',
    [
        (ValueError('retained capture tail not durable yet'), 'reason=retained_capture_tail_not_durable_yet'),
        (ValueError("invalid literal for int() with base 10: 'synthetic-private'"), 'reason=other'),
        (ValueError('synthetic private account name'), 'reason=other'),
        (RuntimeError('synthetic-private'), 'reason=-'),
    ],
)
async def test_retry_log_names_only_static_value_error_reasons(monkeypatch, caplog, error, reason):
    from utils.batch_pipeline import live

    store = MemoryStore()
    store.rows['jobs', 'synthetic'] = {'owner_id': 'synthetic', 'state': 'record_pending', 'available_at': 0}

    async def admission(store, pending):
        raise error

    monkeypatch.setattr(live, 'admit_recording', admission)
    with caplog.at_level('WARNING', logger=live.__name__):
        await live.drain_recordings(store)
    assert reason in caplog.text
    assert 'synthetic-private' not in caplog.text and 'account_name' not in caplog.text


@pytest.fixture(autouse=True)
def protocol_ready(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_RECORD_PROTOCOL_READY', 'true')
    # Paging/privacy fixtures share an owner; drain those rows serially.
    # Parallel-admission tests explicitly choose their own worker count.
    monkeypatch.setenv('RECORD_DRAIN_CONCURRENCY', '1')


def recording(**changes):
    return {
        'id': 'record',
        'record_lane_owner': 'batch_live_v1',
        'source': 'desktop',
        'language': 'en',
        'private_cloud_sync_enabled': True,
        'status': 'completed',
        'data_protection_level': 'standard',
        'started_at': datetime.fromtimestamp(100, timezone.utc),
        'finished_at': datetime.fromtimestamp(102, timezone.utc),
        'transcript_segments': [
            {'id': 'old', 'text': 'Synthetic speech.', 'start': 0, 'end': 2, 'speaker_id': 0, 'is_user': False}
        ],
        **changes,
    }


def incoming():
    return {
        'started_at': datetime.fromtimestamp(100, timezone.utc),
        'transcript_segments': [
            {
                'id': 'new',
                'text': 'Synthetic speech.',
                'start': 0,
                'end': 2,
                'speaker_id': 0,
                'speaker': 'SPEAKER_00',
                'speaker_id_scope': 'final:batch:unit',
                'is_user': False,
                'speaker_match_source': 'batch_pyannote',
            }
        ],
    }


def _ledger_documents(monkeypatch, documents):
    """Route ledger writes through the real transition planner over an in-memory store."""
    from database import pipeline_ledger

    def advance(uid, capture_id, stage, *, now=None, firestore_client=None, **fields):
        plan = pipeline_ledger.plan_advance(documents.get((uid, capture_id)), stage, now=now, **fields)
        if plan.doc is None:
            return False
        plan.doc['owner_key'] = pipeline_ledger.owner_key(uid)
        documents[(uid, capture_id)] = plan.doc
        return True

    monkeypatch.setattr(pipeline_ledger, 'advance', advance)


def _admission_policy(monkeypatch, live, *, claim):
    from types import SimpleNamespace

    monkeypatch.setattr(live, 'resolve_batch_policy', lambda uid: object())
    monkeypatch.setattr(live, 'record_capture_eligible', lambda uid, conversation, policy=None: True)
    monkeypatch.setattr(live, 'ramp_admission_policy', lambda uid, policy: SimpleNamespace(live_record_enabled=True))
    monkeypatch.setattr(live, 'claim_record_lane_owner', lambda *args, **kwargs: claim())


def test_admission_writes_capturing_once_and_never_reopens_a_later_stage(monkeypatch):
    from utils.batch_pipeline import live

    documents = {}
    _ledger_documents(monkeypatch, documents)
    _admission_policy(monkeypatch, live, claim=lambda: datetime.fromtimestamp(120, timezone.utc))
    conversation = recording(
        status='processing', record_lane_owner=None, updated_at=datetime.fromtimestamp(100, timezone.utc)
    )
    assert live.reserve_recording('synthetic', conversation) == 'batch_live_v1'
    assert documents[('synthetic', 'record')]['stage'] == 'capturing'
    # A finalizer replay finds the claimed owner and must not count a second admission.
    assert live.reserve_recording('synthetic', dict(conversation)) == 'batch_live_v1'
    assert [entry['stage'] for entry in documents[('synthetic', 'record')]['transitions']] == ['capturing']
    # A capture that already sealed keeps its forward stage; admission never rewinds it.
    documents[('synthetic', 'record')] = {
        **documents[('synthetic', 'record')],
        'stage': 'sealed',
        'revision': documents[('synthetic', 'record')]['revision'],
    }
    assert live.reserve_recording('synthetic', dict(conversation)) == 'batch_live_v1'
    assert documents[('synthetic', 'record')]['stage'] == 'sealed'


def test_admission_ledger_failure_never_blocks_the_real_admission(monkeypatch, caplog):
    from database import pipeline_ledger
    from utils.batch_pipeline import live

    def broken(*args, **kwargs):
        raise RuntimeError('synthetic ledger outage')

    monkeypatch.setattr(pipeline_ledger, 'advance', broken)
    _admission_policy(monkeypatch, live, claim=lambda: datetime.fromtimestamp(120, timezone.utc))
    conversation = recording(
        status='processing', record_lane_owner=None, updated_at=datetime.fromtimestamp(100, timezone.utc)
    )
    assert live.reserve_recording('synthetic', conversation) == 'batch_live_v1'
    assert 'event=batch_live_ledger outcome=error stage=capturing' in caplog.text


def test_admission_writer_ignores_an_identityless_or_deleted_capture(monkeypatch):
    from database import pipeline_ledger
    from utils.batch_pipeline import live

    writes = []
    monkeypatch.setattr(pipeline_ledger, 'advance', lambda *args, **kwargs: writes.append(args) or True)
    assert not live.observe_admitted('synthetic', {'id': None})
    assert not live.observe_admitted('synthetic', {'id': 'record', 'deleted': True})
    assert not writes


def test_cohort_requires_both_flags_and_uses_the_sync_hash(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_PERCENT', '100')
    assert not live_record_enabled_for('synthetic')
    monkeypatch.setenv('BATCH_PIPELINE_LIVE_ADMISSION_ENABLED', 'true')
    assert live_record_enabled_for('synthetic')
    monkeypatch.setenv('BATCH_PIPELINE_ENABLED', 'false')
    assert not live_record_enabled_for('synthetic')


def test_record_owner_stays_server_internal_without_expanding_the_client_contract():
    from models.conversation import Conversation

    row = recording()
    model = Conversation(**{**row, 'created_at': row['started_at'], 'structured': {}})
    assert model.record_lane_owner == 'batch_live_v1'
    assert 'record_lane_owner' not in model.model_dump()
    assert 'record_lane_owner' not in Conversation.model_json_schema()['properties']


@pytest.mark.parametrize(
    'change',
    [
        {'private_cloud_sync_enabled': False},
        {'uses_custom_stt': True},
        {'discarded': True},
        {'deleted': True},
        {'record_lane_owner': None},
    ],
)
def test_privacy_refusals_never_create_obligations(change):
    store = MemoryStore()
    assert not register_recording('synthetic', recording(**change), store=store, now=0)
    assert not store.rows


def test_concurrent_finalize_registration_and_replay_create_one_pending_obligation():
    store = MemoryStore()
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert all(pool.map(lambda _: register_recording('synthetic', recording(), store=store, now=0), range(2)))
    assert len(store.rows) == 1
    assert next(iter(store.rows.values()))['state'] == 'record_pending'


@pytest.mark.parametrize('recorded_enabled', [True, False])
@pytest.mark.parametrize('automatic_discard', [False, True])
def test_reserved_record_drains_after_rollback_and_cannot_rebind_to_wal(
    monkeypatch, recorded_enabled, automatic_discard
):
    store = MemoryStore()
    register_recording('synthetic', recording(), store=store, now=0)
    content, segment = record_identity('synthetic', 'record')
    store.rows['conversations', 'synthetic/record'] = recording(
        record_audio_closed=True,
        **({'discarded': True, 'relevance_decision': dict(RULE_DISCARD)} if automatic_discard else {}),
    )
    item = WorkItem(
        segment,
        'synthetic',
        100,
        'gs://synthetic/audio#1',
        2,
        Priority.FRESH,
        conversation_id='record',
        privacy_generation=0,
    )
    binding = ProjectionBinding(
        'synthetic',
        'bp_' + content,
        content,
        (segment,),
        target_conversation_id='record',
        record_origin=True,
        native_record=True,
    )
    store.rows['jobs', segment]['policy'].update(
        batch_enabled=recorded_enabled, source_role='reserve-role', final_pass_enabled=True
    )
    monkeypatch.setenv('BATCH_PIPELINE_ENABLED', 'false')
    if not recorded_enabled:
        with pytest.raises(AdmissionDisabled):
            admit(store, [item], binding, 1, namespace='batch_pipeline_test_live')
        assert store.rows['jobs', segment]['state'] == 'record_pending'
        return
    result = admit(store, [item], binding, 1, namespace='batch_pipeline_test_live')
    assert result == {'outcome': 'batch', 'job_id': binding.job_id}
    assert admit(store, [item], binding, 2, namespace='batch_pipeline_test_live') == result
    assert store.rows['jobs', segment]['state'] == 'ready'
    assert len([v for (t, _), v in store.rows.items() if t == 'jobs']) == 1


@pytest.mark.parametrize('visible_restore', [False, True])
def test_projection_replaces_provisional_instead_of_appending_and_keeps_id(visible_restore):
    provisional = recording()
    if visible_restore:
        provisional['external_data'] = {'server_batch_only': True}
        provisional['transcript_segments'][0].update(text='Synthetic Modulate preview.', stt_provider='modulate')
    result, survivors = replace_record(provisional, incoming(), {'start': 100, 'end': 102})
    assert result['id'] == 'record'
    assert len(result['transcript_segments']) == 1
    assert result['transcript_segments'][0]['id'] == 'new'
    assert result['sync_content_revision'] == result['record_projection_revision'] == 1
    assert survivors[0]['speaker_id_scope'] == 'final:batch:unit'
    assert result['record_lane_owner'] == 'batch_live_v1'
    if visible_restore:
        assert result['external_data']['server_batch_only'] is True
        assert result['transcript_segments'][0]['text'] == 'Synthetic speech.'


def test_final_batch_projection_fences_a_delayed_modulate_preview_flush():
    from database import conversations
    from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore

    provisional = recording(external_data={'server_batch_only': True})
    final, _ = replace_record(provisional, incoming(), {'start': 100, 'end': 102})
    key = ('users', 'synthetic', 'conversations', 'record')
    db = StrictFirestore({key: final})
    assert (
        conversations.update_conversation_segments(
            'synthetic',
            'record',
            provisional['transcript_segments'],
            live_segments=provisional['transcript_segments'],
            firestore_client=db,
        )
        is False
    )
    assert db.rows[key] == final


RULE_DISCARD = {'verdict': 'discard', 'decided_by': 'rule', 'reason': 'empty_transcript', 'trigger': 'sync_update'}


def test_projection_later_speech_clears_an_ordinary_automatic_discard():
    original = recording(transcript_segments=[], discarded=True, relevance_decision=dict(RULE_DISCARD))
    result, _ = replace_record(original, incoming(), {'start': 100, 'end': 102})
    assert result['discarded'] is False and result['relevance_decision'] is None
    assert [s['id'] for s in result['transcript_segments']] == ['new']
    assert original['discarded'] is True


def test_projection_without_new_text_keeps_the_automatic_discard():
    original = recording(discarded=True, relevance_decision=dict(RULE_DISCARD))
    result, new = replace_record(original, incoming(), {'start': 100, 'end': 102, 'preserve_existing': True})
    assert not new
    assert result['discarded'] is True and result['relevance_decision'] == RULE_DISCARD


STAMP_NOW = 1_000_000_000.0


def stamp_row(**changes):
    row = recording(**changes)
    row.setdefault('created_at', datetime.fromtimestamp(STAMP_NOW - 3600, timezone.utc))
    return row


def test_projection_stamps_first_summary_debt_on_an_untitled_completed_row():
    from config.summary_guarantee import deadline_seconds
    from utils.conversations import home_step

    result, new = replace_record(recording(), incoming(), {'start': 100, 'end': 102})
    assert new
    assert result['summary_title_provenance'] == 'server_minimum'
    # The stamp must not write structured.title_provenance: is_server_minimum
    # gates derived effects, and a projection stamp must not suppress them.
    assert 'title_provenance' not in result.get('structured', {})
    assert isinstance(result['summary_first_pending_at'], float)
    assert result['summary_due_at'] == result['summary_first_pending_at'] + deadline_seconds()
    # The repair must accept every row this stamp creates.
    assert summary_delivery.refusal(result) is None
    assert not expired(
        {'first_pending_at': result['summary_first_pending_at']},
        result.get('created_at'),
        now=result['summary_due_at'],
    )
    # The list read omits transcript_segments; debt plus provenance is what Home reads.
    listed = {key: value for key, value in result.items() if key != 'transcript_segments'}
    assert home_step.classify(listed) == home_step.WRITING_NOTES


def test_projection_does_not_stamp_debt_past_the_repair_age_gate():
    from utils.conversations import home_step

    old = recording(created_at=datetime.fromtimestamp(STAMP_NOW - 4 * 86400, timezone.utc))
    result, new = replace_record(old, incoming(), {'start': 100, 'end': 102})
    assert new
    # Provenance is honest, but no debt means the repair never parks the row
    # one-way and Home never presents it as Writing notes forever.
    assert result['summary_title_provenance'] == 'server_minimum'
    assert 'summary_due_at' not in result
    assert 'summary_first_pending_at' not in result
    assert summary_delivery.refusal(result) is None
    listed = {key: value for key, value in result.items() if key != 'transcript_segments'}
    assert home_step.classify(listed) == home_step.NOISE


def test_projection_does_not_double_stamp_existing_debt():
    original = recording(
        summary_first_pending_at=50.0,
        summary_due_at=170.0,
        summary_title_provenance='server_minimum',
        structured={'title_provenance': 'server_minimum'},
    )
    result, _ = replace_record(original, incoming(), {'start': 100, 'end': 102})
    assert result['summary_first_pending_at'] == 50.0
    assert result['summary_due_at'] == 170.0
    assert result['summary_title_provenance'] == 'server_minimum'
    assert summary_delivery.refusal(result) is None


def test_projection_does_not_move_debt_on_a_second_projection():
    first, _ = replace_record(recording(), incoming(), {'start': 100, 'end': 102})
    due, pending = first['summary_due_at'], first['summary_first_pending_at']
    second, new = replace_record(first, incoming(), {'start': 100, 'end': 102})
    assert new
    assert second['summary_due_at'] == due
    assert second['summary_first_pending_at'] == pending
    assert second['summary_title_provenance'] == 'server_minimum'


def test_projection_leaves_titled_rows_untouched():
    original = recording(structured={'title': 'Synthetic title'})
    result, _ = replace_record(original, incoming(), {'start': 100, 'end': 102})
    assert 'summary_due_at' not in result
    assert 'summary_first_pending_at' not in result
    assert result['structured'] == {'title': 'Synthetic title'}


def test_projection_leaves_an_existing_summary_untouched():
    original = recording(summary_completed_at=90.0, summary_output_present=True)
    result, _ = replace_record(original, incoming(), {'start': 100, 'end': 102})
    assert 'summary_due_at' not in result
    assert 'summary_first_pending_at' not in result


def test_projection_debt_kill_switch_off_restores_todays_behavior(monkeypatch):
    monkeypatch.setenv('SUMMARY_PROJECTION_DEBT_ENABLED', 'false')
    original = recording()
    result, _ = replace_record(original, incoming(), {'start': 100, 'end': 102})
    assert 'summary_due_at' not in result
    assert 'summary_first_pending_at' not in result
    assert 'summary_title_provenance' not in result
    assert result.get('structured') == original.get('structured')


@pytest.mark.parametrize(
    'changes,reason',
    [
        ({'is_locked': True}, 'local_only'),
        ({'client_processing': True}, 'local_only'),
        ({'finalization_job_id': 'synthetic-job'}, 'generation_owned'),
        ({'finalization_status': 'blocked_byok'}, 'generation_owned'),
        (
            {'relevance_decision': {'verdict': 'keep', 'decided_by': 'rule', 'reason': 'content_below_floor'}},
            'content_below_floor',
        ),
    ],
)
def test_projection_debt_stamp_skips_rows_the_repair_would_refuse(changes, reason):
    row = stamp_row(**changes)
    before = deepcopy(row)
    assert not summary_delivery.stamp_projection_debt(row, now=STAMP_NOW)
    assert row == before
    # The stamp evaluates the row with the provenance it would add, so the
    # refusal reason is the one the repair would see after a stamp.
    candidate = {
        **row,
        'structured': {**row.get('structured', {}), 'title_provenance': 'server_minimum'},
        'summary_title_provenance': 'server_minimum',
    }
    assert summary_delivery.refusal(candidate) == reason


@pytest.mark.parametrize('reason', ['content_below_floor', 'local_only', 'blocked_byok', 'empty_output_exhausted'])
def test_projection_debt_stamp_skips_every_non_empty_summary_block(reason):
    row = stamp_row(summary_blocked_reason=reason)
    before = deepcopy(row)
    assert not summary_delivery.stamp_projection_debt(row, now=STAMP_NOW)
    assert row == before


@pytest.mark.parametrize(
    'changes',
    [
        {'terminal_no_derived_effects': True},
        {'deferred': True},
        {'processing_state': 'local_pending'},
        {'data_protection_level': 'e2ee'},
        {'user_title': 'Synthetic title'},
        {'user_overview': 'Synthetic overview'},
        {'summary_completed_at': 90.0},
        {'summary_output_present': True},
        {'summary_due_at': 170.0},
        {'summary_first_pending_at': 50.0},
        {'structured': {'title': 'Synthetic title'}},
        {'structured': {'overview': 'Synthetic overview'}},
        {'structured': {'sections': [{'body_markdown': 'Synthetic body'}]}},
    ],
)
def test_projection_debt_stamp_skips_every_guard_branch(changes):
    row = stamp_row(**changes)
    before = deepcopy(row)
    assert not summary_delivery.stamp_projection_debt(row, now=STAMP_NOW)
    assert row == before


@pytest.mark.parametrize('structured', [['synthetic'], 'synthetic', 7])
def test_projection_debt_stamp_preserves_non_dict_structured(structured):
    row = stamp_row(structured=structured)
    before = deepcopy(row)
    assert not summary_delivery.stamp_projection_debt(row, now=STAMP_NOW)
    assert row == before
    assert row['structured'] == structured


@pytest.mark.parametrize(
    'changes',
    [
        {'discarded': True},
        {'discarded': True, 'relevance_decision': dict(RULE_DISCARD), 'sync_relevance_user_kept': False},
        {'discarded': True, 'relevance_decision': {**RULE_DISCARD, 'verdict': 'keep'}},
    ],
)
def test_projection_never_overrides_a_user_discard(changes):
    with pytest.raises(SyncAssignmentConflict, match='discarded'):
        replace_record(recording(**changes), incoming(), {'start': 100, 'end': 102})


def test_projection_waits_for_finalize_without_mutating_provisional():
    original = recording(status='processing')
    with pytest.raises(SyncAssignmentConflict, match='finalize'):
        replace_record(original, incoming(), {'start': 100, 'end': 102})
    assert original['transcript_segments'][0]['id'] == 'old'


def test_translation_and_manual_edit_anchors_survive_projection():
    old = recording(has_transcript_corrections=True)
    old['transcript_segments'][0]['translations'] = [{'language': 'es', 'text': 'Synthetic translation.'}]
    old['manual_speaker_assignments'] = {'segments': {'old': {'is_user': True, 'person_id': None, 'generation': 1}}}
    result, _ = replace_record(old, incoming(), {'start': 100, 'end': 102})
    segment = result['transcript_segments'][0]
    assert segment['id'] == 'old' and segment['text'] == old['transcript_segments'][0]['text']
    assert segment['translations'] == old['transcript_segments'][0]['translations']
    assert segment['is_user']
    assert segment['speaker_id_scope'] == 'final:batch:unit'


def test_reference_manifest_joins_sample_slices_without_copying_source_audio():
    pcm = b'\x01\x00' * 32000
    item = WorkItem('unit', 'synthetic', 100, 'manifest', 1, Priority.FRESH, conversation_id='record')
    body = (
        MAGIC
        + json.dumps(
            {
                'owner_id': 'synthetic',
                'conversation_id': 'record',
                'capture_at': 100,
                'context': {'synthetic': True},
                'references': [
                    {
                        'start_frame': 0,
                        'offset_frame': 16000,
                        'frames': 16000,
                        'pcm_sha256': hashlib.sha256(pcm).hexdigest(),
                    }
                ],
            }
        ).encode()
    )
    wav = materialize(body, item, lambda ref: pcm)
    with wave.open(io.BytesIO(wav), 'rb') as stream:
        assert stream.readframes(stream.getnframes()) == pcm[32000:]
    with pytest.raises(ValueError, match='digest changed'):
        materialize(body, item, lambda ref: b'\0' * 64000)


@pytest.mark.parametrize(
    'change',
    [
        {'bucket': 'foreign'},
        {'path': 'chunks/other/record/a'},
        {'generation': 0},
        {'path': 'chunks/synthetic/record/../a'},
    ],
)
def test_reference_scope_and_generation_are_fail_closed(change):
    with pytest.raises(ValueError):
        validate_reference(
            {'bucket': 'retained', 'path': 'chunks/synthetic/record/a', 'generation': 1, **change},
            'synthetic',
            'record',
            {'retained'},
        )


@pytest.mark.parametrize('server_only', [False, True])
@pytest.mark.parametrize('barrier_change', [None, 'before_read', 'pending', 'failed', 'resealed', 'protocol_closed'])
@pytest.mark.parametrize('language', ['en', 'multi', 'ca'])
async def test_native_admission_stages_references_and_drains_after_rollback(
    monkeypatch, server_only, barrier_change, language
):
    from types import SimpleNamespace
    from utils.batch_pipeline import live
    from database.batch_pipeline_staging import artifact_id

    unit_reads = []
    original_run_blocking = live.run_blocking

    async def run_blocking(executor, fn, *args, **kwargs):
        if fn is next:
            assert executor is live.storage_executor
            unit_reads.append(1)
        return await original_run_blocking(executor, fn, *args, **kwargs)

    monkeypatch.setattr(live, 'run_blocking', run_blocking)
    store = MemoryStore()
    store.namespace = 'batch_pipeline_test_live'
    current = recording(record_audio_closed=True, finished_at=datetime.fromtimestamp(101, timezone.utc))
    current['language'] = language
    proofs = []
    from unittest.mock import Mock

    outbox = Outbox()
    outbox.wake = Mock(side_effect=OSError('synthetic wake unavailable'))
    # Durable captures drain even after the experimental allowlist is cleared.
    monkeypatch.setenv('SERVER_BATCH_UNSUPPORTED_LANGUAGES', '')

    async def prove(store, artifacts, item, manifest):
        proofs.append(manifest)
        if language == 'ca':
            from utils.batch_pipeline.record_language import prove_manifest

            return await prove_manifest(store, artifacts, item, manifest)
        return {
            **manifest,
            'context': {
                **manifest['context'],
                'stt_language': 'en',
                'stt_language_evidence': 'audio_lid',
                'stt_language_confidence': 0.99,
            },
        }

    monkeypatch.setattr(live, 'prove_manifest', prove)
    if server_only:
        current['client_platform'] = 'ios'
        current['external_data'] = {**(current.get('external_data') or {}), 'server_batch_only': True}
        current.update(
            has_content=True, server_batch_audio_start=100, server_batch_audio_end=101, transcript_segments=[]
        )
    register_recording('synthetic', current, store=store, now=0)
    content, segment = record_identity('synthetic', 'record')
    pending = store.rows['jobs', segment]
    store.rows['conversations', 'synthetic/record'] = current
    if barrier_change == 'before_read':
        # The reservation predates the append. No input was captured yet, so
        # admission must capture the newer revision, never its old snapshot.
        current['record_upload_revision'] = 9
        monkeypatch.setenv('RECORD_TOKEN_LEASE_MODE', 'serve')
        barrier_change = None

    class Reference:
        def collection(self, *args):
            return self

        document = collection

        def get(self):
            return SimpleNamespace(to_dict=lambda: current)

    store.client = Reference()

    class Client:
        def bucket(self, name):
            return self

        def blob(self, path, generation=None):
            return SimpleNamespace(reload=lambda **kwargs: None, metadata={})

    monkeypatch.setattr(live, 'create_storage_client', Client)
    listings = []
    monkeypatch.setattr(
        live,
        'list_audio_chunks',
        lambda *args, **kwargs: listings.append(kwargs)
        or [
            {
                'path': 'chunks/synthetic/record/audio.batch.bin',
                'generation': 1,
                'timestamp': 100,
                'span': {'sample_rate': 16000},
            }
        ],
    )
    monkeypatch.setattr(live, 'read_reference', lambda *args, **kwargs: b'\x01\x00' * 16000)
    manifests = []

    def stage(item, body):
        manifests.append(json.loads(body[len(MAGIC) :]))
        assert body.startswith(MAGIC) and len(body) < 2000
        uri = 'gs://synthetic-manifest/audio#1'
        store.rows['artifacts', artifact_id(item.segment_id, uri)] = {
            'owner_id': item.owner_id,
            'privacy_generation': 0,
        }
        if barrier_change == 'pending':
            current.update(record_upload_sessions={'new': True}, record_audio_closed=False)
        elif barrier_change == 'failed':
            current.update(record_upload_failed=True, record_audio_closed=False)
        elif barrier_change == 'resealed':
            # A producer can upload and seal again during staging. A closed
            # boolean alone cannot prove that these manifests include it.
            current.update(record_upload_revision=1, record_audio_closed=True)
        elif barrier_change == 'protocol_closed':
            monkeypatch.setenv('BATCH_PIPELINE_RECORD_PROTOCOL_READY', 'false')
        if barrier_change:
            store.rows['conversations', 'synthetic/record'].update(current)
        return uri

    monkeypatch.setattr(
        live,
        'create_artifact_store',
        lambda *args: SimpleNamespace(
            key_for_owner=lambda uid: b'a' * 32,
            stage_audio=stage,
            authorize=lambda item: SimpleNamespace(level='standard'),
        ),
    )
    monkeypatch.setenv('BATCH_PIPELINE_ENABLED', 'false')
    if barrier_change:
        with pytest.raises(ValueError, match='barrier'):
            await live.admit_recording(store, pending, now=1, provider_outbox_factory=lambda: outbox)
        assert store.rows['jobs', segment]['state'] == 'record_pending'
        assert ('content', 'synthetic/' + content) not in store.rows
        return
    result = await live.admit_recording(store, pending, now=1, provider_outbox_factory=lambda: outbox)
    assert unit_reads
    assert result == {'outcome': 'batch', 'job_id': 'bp_' + content}
    job = store.rows['jobs', segment]
    if current.get('record_upload_revision') == 9:
        assert job['record_input_upload_revision'] == 9
    else:
        assert 'record_input_upload_revision' not in job
    assert job['state'] == ('provider_pending' if language == 'ca' else 'ready')
    if language == 'ca':
        assert job['stt_route']['provider_service'] == 'modulate'
        assert job['policy']['stt_route'] == 'provider'
        assert job['policy']['provider_reason'] == 'unsupported_language'
        assert not job['requires_compute_admission']
        assert len(outbox.enqueued) == 1
        outbox.wake.assert_called_once()
        assert not any(key[0] in {'queues', 'control'} for key in store.rows)
        vendor = Vendor()
        # A 1 s unit cannot carry the 2 s speech minimum; this test is about admission, not the skip.
        monkeypatch.setenv('BATCH_VENDOR_MIN_SPEECH_SECONDS', '0')
        provider = provider_stage(
            store,
            Artifacts(),
            vendor,
            now=2,
            inspect=lambda *_: (b'\0\0' * 16000, 1.0, [{'start': 0.5, 'end': 1.0}]),
        )
        outcome = provider.run(segment)
        assert outcome.outcome == 'done' and vendor.calls == 1
        assert store.rows['jobs', segment]['state'] == 'result_ready'
        assert store.rows['jobs', segment]['provider_intent']['service'] == 'modulate'
        assert provider.run(segment).outcome == 'done'
        assert vendor.calls == 1
    assert manifests[0]['references'][0]['generation'] == 1
    assert bool(proofs) is server_only
    assert manifests[0]['context']['stt_language'] == ('en' if server_only and language != 'ca' else language)
    assert store.rows['jobs', segment]['projection_binding']['native_record']
    intake = store.rows['intakes', 'bp_' + content]
    assert (intake.get('server_batch_only') is True) is server_only
    assert store.rows['jobs', segment]['timing_store'] == 'batch'
    receipt_enabled = server_only and language == 'multi'
    assert ('language_receipts' in intake) is receipt_enabled
    assert (store.rows['jobs', intake['segment_ids'][0]].get('language_receipt_enabled') is True) is receipt_enabled
    if receipt_enabled:
        assert intake['language_receipts'][intake['segment_ids'][0]] == {
            'version': 1,
            'language': 'en',
            'evidence': 'audio_lid',
        }
    # A slow raw-archive listing must raise and retry, never admit a short capture.
    assert listings == [{'max_count': 4096, 'require_archive': True}]


@pytest.mark.parametrize('setting', [None, 'false', 'typo'])
async def test_protocol_cutover_defers_without_reading_archive_or_expiring_obligation(monkeypatch, setting):
    from utils.batch_pipeline import live

    if setting is None:
        monkeypatch.delenv('BATCH_PIPELINE_RECORD_PROTOCOL_READY')
    else:
        monkeypatch.setenv('BATCH_PIPELINE_RECORD_PROTOCOL_READY', setting)
    store = MemoryStore()
    register_recording('synthetic', recording(), store=store, now=0)
    _, segment = record_identity('synthetic', 'record')
    pending = dict(store.rows['jobs', segment])
    with pytest.raises(ValueError, match='cutover barrier closed'):
        await live.admit_recording(store, pending, now=10**10)
    assert store.rows['jobs', segment] == pending
    assert pending['state'] == 'record_pending'


@pytest.mark.parametrize('language,admitted', [('en', True), ('vi', False), ('multi', False)])
def test_capture_reservation_preserves_supported_language_route(monkeypatch, language, admitted):
    from utils.conversations import lifecycle

    monkeypatch.setenv('BATCH_PIPELINE_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_PERCENT', '100')
    monkeypatch.setenv('BATCH_PIPELINE_LIVE_ADMISSION_ENABLED', 'true')
    captured = []
    monkeypatch.setattr(
        lifecycle.conversations_db,
        'create_conversation_if_absent_with_lifecycle',
        lambda uid, row: captured.append(dict(row)) or True,
    )
    row = recording(status='in_progress', language=language, record_lane_owner=None)
    assert lifecycle.create_in_progress_conversation('synthetic', row, idempotent=True)
    assert (captured[0].get('record_lane_owner') == 'batch_live_v1') == admitted


def test_ambiguous_annotated_sentence_preserves_text_and_abstains_instead_of_guessing():
    old = recording()
    old['transcript_segments'][0]['translations'] = [{'language': 'es', 'text': 'Synthetic translation.'}]
    new = incoming()
    new['transcript_segments'][0]['text'] = 'Unrelated synthetic recognition.'
    result, _ = replace_record(old, new, {'start': 100, 'end': 102})
    segment = result['transcript_segments'][0]
    assert segment['id'] == 'old' and segment['text'] == 'Synthetic speech.'
    assert segment['speaker_match_source'] == 'batch_abstention' and not segment['is_user']
    assert segment['translations'] == old['transcript_segments'][0]['translations']


@pytest.mark.asyncio
async def test_privacy_fenced_claim_does_not_stop_the_worker(monkeypatch):
    from utils.batch_pipeline import live
    from database.batch_pipeline_privacy import BatchPrivacyBlocked

    monkeypatch.setenv('RECORD_DRAIN_CONCURRENCY', '1')
    monkeypatch.setenv('RECORD_DRAIN_BATCH', '2')
    monkeypatch.setattr(live.random, 'shuffle', lambda segments: segments.sort())
    store = MemoryStore()
    for segment in ('a-fenced', 'b-ok'):
        store.rows['jobs', segment] = {
            'owner_id': f'synthetic-{segment}',
            'segment_id': segment,
            'state': 'record_pending',
            'available_at': 0,
        }
    original_run = store.run
    calls = []

    def run(body):
        calls.append(1)
        if len(calls) == 2:  # the fenced row's claim transaction
            raise BatchPrivacyBlocked('synthetic privacy fence')
        return original_run(body)

    admitted = []

    async def admission(store, pending):
        admitted.append(pending['segment_id'])
        store.rows['jobs', pending['segment_id']]['state'] = 'ready'

    monkeypatch.setattr(store, 'run', run)
    monkeypatch.setattr(live, 'admit_recording', admission)
    assert await live.drain_recordings(store) is False
    assert admitted == ['b-ok']
    assert store.rows['jobs', 'a-fenced']['available_at'] == 0


def test_record_replacement_preserves_discard_until_restore_metadata_commits():
    start = datetime.fromtimestamp(100, timezone.utc)
    current = {
        'id': 'capture',
        'record_lane_owner': 'batch_live_v1',
        'status': 'completed',
        'discarded': True,
        'relevance_decision': {'verdict': 'discard', 'decided_by': 'rule', 'reason': 'empty_transcript'},
        'started_at': start,
        'transcript_segments': [],
    }
    incoming = {
        'id': 'record-pass',
        'started_at': start,
        'transcript_segments': [{'id': 'speech', 'start': 0, 'end': 1, 'text': 'Synthetic speech'}],
    }
    replaced, _ = replace_record(
        current, incoming, {'start': 100, 'end': 110}, obligations=({'registration_origin': 'restore'},)
    )
    assert replaced['discarded'] is True, 'record replacement cleared discard without a restore metadata commit'
