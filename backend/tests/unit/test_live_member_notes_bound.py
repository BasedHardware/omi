"""A deferred finished member has a finite live-owner wait and one paid escape."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from database import conversation_finalization_jobs as jobs
from database import episodes
from database import live_member_notes as permits
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from utils.conversations.processing_trigger import ProcessingTrigger
from utils.episodes import member_notes, service

NOW = datetime(2026, 11, 15, tzinfo=timezone.utc)


@pytest.fixture
def deferred(monkeypatch):
    monkeypatch.setenv('OMI_ENV_STAGE', 'prod')
    monkeypatch.delenv('HOME_PROCESSING_OWNERSHIP_UIDS', raising=False)
    monkeypatch.setenv('HOME_LIVE_MEMBER_NOTES_DEFERRED_ENABLED', 'true')
    monkeypatch.delenv('HOME_LIVE_MEMBER_NOTES_BOUNDED_ENABLED', raising=False)
    monkeypatch.setattr(member_notes.time, 'time', lambda: NOW.timestamp())
    monkeypatch.setattr(member_notes.demand_processing, 'client', lambda: SimpleNamespace(get=lambda key: None))
    owner = {
        'id': 'episode',
        'status': 'live',
        'conversation_ids': ['first', 'last'],
        'started_at': NOW - timedelta(hours=1),
        'last_activity_at': NOW,
    }
    job = {'uid': 'synthetic', 'conversation_id': 'first', 'created_at': NOW, 'finalization_revision': 1}
    monkeypatch.setattr(episodes, 'get_episode_owner_snapshot', lambda *a: dict(owner))
    monkeypatch.setattr(episodes, 'get_episode', lambda *a, **kw: dict(owner))
    monkeypatch.setattr(jobs, 'get_finalization_job', lambda *a: dict(job))
    return owner, job, {'id': 'first', 'status': 'processing', 'source': 'omi', 'finalization_job_id': 'job'}


def test_idle_non_last_member_retry_uses_home_idle_close(deferred, monkeypatch):
    owner, _, row = deferred
    owner['last_activity_at'] = NOW - timedelta(minutes=31)
    close = Mock(side_effect=lambda uid, episode, c: dict(episode, status='closed'))
    monkeypatch.setattr(service, 'settle_episode_for_read', close)
    assert not member_notes.waits('synthetic', row, ProcessingTrigger.CAPTURE_END)
    close.assert_called_once()
    assert owner['conversation_ids'] == ['first', 'last']


def test_live_owner_member_past_age_bound_proceeds(deferred):
    owner, job, row = deferred
    job['created_at'] = NOW - timedelta(seconds=181)
    assert not member_notes.waits('synthetic', row, ProcessingTrigger.CAPTURE_END)
    assert owner['status'] == 'live'
    assert owner['conversation_ids'] == ['first', 'last']


@pytest.mark.parametrize('age,waiting', [(0, True), (179.999, True), (180, False), (181, False)])
def test_active_owner_exact_age_boundary(deferred, monkeypatch, age, waiting):
    owner, job, row = deferred
    job['created_at'] = NOW - timedelta(seconds=age)
    close = Mock(side_effect=AssertionError('active owner must stay live'))
    monkeypatch.setattr(service, 'settle_episode_for_read', close)
    assert member_notes.waits('synthetic', row) is waiting
    close.assert_not_called()
    assert owner['status'] == 'live'


@pytest.mark.parametrize('value', ['off', 'false', '0', 'no'])
def test_kill_switch_off_is_inert_even_for_old_idle_members(deferred, monkeypatch, value):
    owner, job, row = deferred
    owner['last_activity_at'] = NOW - timedelta(hours=1)
    job['created_at'] = NOW - timedelta(hours=1)
    monkeypatch.setenv('HOME_LIVE_MEMBER_NOTES_BOUNDED_ENABLED', value)
    read = Mock(side_effect=AssertionError('kill switch must not enter recovery'))
    monkeypatch.setattr(episodes, 'get_episode', read)
    monkeypatch.setattr(jobs, 'get_finalization_job', read)
    monkeypatch.setattr(permits, 'claim', read)
    assert member_notes.waits('synthetic', row)
    member_notes.before_model(
        'synthetic', SimpleNamespace(id='first'), ProcessingTrigger.CAPTURE_END, finalization_fence=('job', 1, 1)
    )
    read.assert_not_called()


def test_second_gate_keeps_the_durable_job_clock(deferred):
    _, job, _ = deferred
    job['created_at'] = NOW - timedelta(seconds=181)
    conversation = SimpleNamespace(id='first', source='omi', status='processing', transcript_segments=[object()])
    member_notes.before_notes(
        'synthetic', conversation, ProcessingTrigger.CAPTURE_END, finalization_fence=('job', 1, 1)
    )


def test_failed_idle_read_does_not_disable_timeout(deferred, monkeypatch):
    _, job, row = deferred
    job['created_at'] = NOW - timedelta(seconds=181)
    monkeypatch.setattr(episodes, 'get_episode', Mock(side_effect=TimeoutError('synthetic')))
    assert not member_notes.waits('synthetic', row)


@pytest.mark.parametrize('field,value', [('source', 'desktop'), ('record_lane_owner', 'batch_live_v1')])
def test_bounded_recovery_stays_inside_the_measured_live_scope(deferred, monkeypatch, field, value):
    owner, job, row = deferred
    job['created_at'] = NOW - timedelta(hours=1)
    owner['last_activity_at'] = NOW - timedelta(hours=1)
    row[field] = value
    read = Mock(side_effect=AssertionError('outside bounded live scope'))
    monkeypatch.setattr(episodes, 'get_episode', read)
    assert member_notes.waits('synthetic', row)
    read.assert_not_called()


def test_old_job_recording_detail_keeps_its_independent_escalation(deferred, monkeypatch):
    _, job, row = deferred
    job['created_at'] = NOW - timedelta(hours=1)
    row['transcript_segments'] = [object()]
    redis = Mock()
    redis.get.return_value = None
    monkeypatch.setattr(member_notes.demand_processing, 'client', lambda: redis)
    enqueue = Mock()
    monkeypatch.setattr(member_notes.ENRICHMENT_OUTBOX, 'enqueue', enqueue)
    member_notes.open_recording('synthetic', row)
    enqueue.assert_called_once()
    redis.set.assert_called_once()


def test_aged_finalizer_defers_to_detail_lease_without_paying(deferred, monkeypatch):
    _, job, _ = deferred
    job['created_at'] = NOW - timedelta(seconds=181)
    monkeypatch.setattr(member_notes.demand_processing, 'client', lambda: SimpleNamespace(get=lambda key: '1'))
    permit = Mock()
    monkeypatch.setattr(permits, 'claim', permit)
    model = Mock()
    with pytest.raises(member_notes.LiveMemberNotesDeferred):
        member_notes.before_model(
            'synthetic',
            SimpleNamespace(id='first', source='omi'),
            ProcessingTrigger.CAPTURE_END,
            finalization_fence=('job', 1, 2),
        )
        model()
    model.assert_not_called()
    permit.assert_not_called()


def test_aged_finalizer_proceeds_unfenced_when_owner_read_fails(deferred, monkeypatch):
    """An unreadable owner never stalls finalization and never consumes the aged permit."""
    _, job, _ = deferred
    job['created_at'] = NOW - timedelta(seconds=181)
    monkeypatch.setattr(episodes, 'get_episode_owner_snapshot', Mock(side_effect=TimeoutError('synthetic')))
    permit = Mock()
    monkeypatch.setattr(permits, 'claim', permit)
    unavailable = Mock()
    monkeypatch.setattr(member_notes, '_unavailable', unavailable)
    member_notes.before_model(
        'synthetic',
        SimpleNamespace(id='first', source='omi'),
        ProcessingTrigger.CAPTURE_END,
        finalization_fence=('job', 1, 2),
    )
    permit.assert_not_called()
    unavailable.assert_called_once()
    assert unavailable.call_args.args[0] == 'owner_unavailable'


@pytest.mark.parametrize('state', ['closed', 'in_progress', 'no_job'])
def test_no_recomposition_or_work_for_ineligible_rows(deferred, monkeypatch, state):
    owner, _, row = deferred
    if state == 'closed':
        owner['status'] = 'closed'
    elif state == 'in_progress':
        row['status'] = 'in_progress'
    else:
        row.pop('finalization_job_id')
    read = Mock(side_effect=AssertionError('not eligible for recovery'))
    monkeypatch.setattr(episodes, 'get_episode', read)
    monkeypatch.setattr(jobs, 'get_finalization_job', read)
    assert member_notes.waits('synthetic', row) is (state != 'closed')
    read.assert_not_called()


def _permit_store():
    return StrictFirestore(
        {
            ('conversation_finalization_jobs', 'job'): {
                'uid': 'synthetic',
                'conversation_id': 'first',
                'status': 'leased',
                'dispatch_generation': 1,
                'lease_epoch': 2,
                'lease_expires_at': NOW + timedelta(minutes=10),
                'finalization_revision': 1,
            },
            ('users', 'synthetic', 'conversations', 'first'): {
                'status': 'processing',
                'finalization_job_id': 'job',
                'finalization_revision': 1,
                'sync_content_revision': 3,
            },
        }
    )


def _claim(store, fence=('job', 1, 2), revision=3):
    return permits._claim(
        store.transaction(),
        store.collection('conversation_finalization_jobs').document('job'),
        store.document('users/synthetic/conversations/first'),
        fence,
        revision,
        NOW,
    )


def test_one_paid_permit_per_revision_survives_worker_retries():
    store = _permit_store()
    assert _claim(store)
    assert not _claim(store)
    store.rows[('conversation_finalization_jobs', 'job')]['lease_epoch'] = 3
    assert not _claim(store, ('job', 1, 3))
    store.rows[('users', 'synthetic', 'conversations', 'first')]['sync_content_revision'] = 4
    assert _claim(store, ('job', 1, 3), revision=4)
    assert not _claim(store, ('job', 1, 3), revision=4)


@pytest.mark.parametrize('change', ['epoch', 'generation', 'expired', 'deleted', 'revision', 'account', 'completed'])
def test_paid_permit_fences_stale_or_terminal_work(change):
    store = _permit_store()
    job = store.rows[('conversation_finalization_jobs', 'job')]
    row = store.rows[('users', 'synthetic', 'conversations', 'first')]
    if change == 'epoch':
        job['lease_epoch'] += 1
    elif change == 'generation':
        job['dispatch_generation'] += 1
    elif change == 'expired':
        job['lease_expires_at'] = NOW
    elif change == 'deleted':
        row['deleted'] = True
    elif change == 'revision':
        row['sync_content_revision'] = 4
    elif change == 'account':
        job['uid'] = 'different-synthetic'
    else:
        row['status'] = 'completed'
    assert not _claim(store)
    assert 'live_member_notes_fallback_revision' not in row


def test_consumed_paid_permit_waits_until_close_or_explicit_request(deferred, monkeypatch):
    owner, job, _ = deferred
    job['created_at'] = NOW - timedelta(seconds=181)
    monkeypatch.setattr(permits, 'claim', Mock(return_value=False))
    conversation = SimpleNamespace(id='first', source='omi', sync_content_revision=3)
    with pytest.raises(member_notes.LiveMemberNotesDeferred):
        member_notes.before_model(
            'synthetic', conversation, ProcessingTrigger.CAPTURE_END, finalization_fence=('job', 1, 2)
        )
    member_notes.before_model(
        'synthetic', conversation, ProcessingTrigger.USER_REPROCESS, finalization_fence=('job', 1, 2)
    )
    owner['status'] = 'closed'
    member_notes.before_model(
        'synthetic', conversation, ProcessingTrigger.CAPTURE_END, finalization_fence=('job', 1, 2)
    )
    permits.claim.assert_called_once()


@pytest.mark.parametrize('new_speech', [False, True])
def test_idle_retry_reuses_real_transaction_and_speech_wins(monkeypatch, new_speech):
    monkeypatch.setenv('OMI_ENV_STAGE', 'prod')
    monkeypatch.setenv('EPISODE_RECORDED_TIME_ENABLED', 'false')
    monkeypatch.setenv('HOME_LIVE_MEMBER_NOTES_DEFERRED_ENABLED', 'true')
    monkeypatch.delenv('HOME_PROCESSING_OWNERSHIP_UIDS', raising=False)
    monkeypatch.setattr(member_notes.time, 'time', lambda: NOW.timestamp())
    monkeypatch.setattr(service, '_now', lambda c: NOW)
    monkeypatch.setattr(member_notes.demand_processing, 'client', lambda: SimpleNamespace(get=lambda key: None))
    episode_path = ('users', 'synthetic', 'episodes', 'episode')
    store = StrictFirestore(
        {
            episode_path: {
                'id': 'episode',
                'status': 'live',
                'conversation_ids': ['first', 'last'],
                'started_at': NOW - timedelta(hours=1),
                'last_activity_at': NOW - timedelta(minutes=31),
            },
            ('users', 'synthetic', 'episode_links', 'first'): {'episode_id': 'episode'},
        }
    )
    monkeypatch.setattr(episodes, '_client', lambda c=None: store)
    monkeypatch.setattr(
        jobs, 'get_finalization_job', lambda j: {'uid': 'synthetic', 'conversation_id': 'first', 'created_at': NOW}
    )
    schedule = Mock()
    monkeypatch.setattr(service.composer, 'schedule_after_close', schedule)
    close = episodes.close_episode

    def racing_close(*args, **kwargs):
        if new_speech:
            store.rows[episode_path]['last_activity_at'] = NOW
        return close(*args, **kwargs)

    monkeypatch.setattr(episodes, 'close_episode', racing_close)
    row = {'id': 'first', 'status': 'processing', 'source': 'omi', 'finalization_job_id': 'job'}
    assert member_notes.waits('synthetic', row) is new_speech
    stored = store.rows[episode_path]
    assert stored['status'] == ('live' if new_speech else 'closed')
    assert stored['conversation_ids'] == ['first', 'last']
    assert schedule.call_count == int(not new_speech)
