"""Main's settle paths (#24884, 920bb5be) run unchanged with the backlog switches off.

Merge contract for the backlog state machine: with every new switch off,
main's record barrier dead letter (record_barrier_aged) and assignment-hold
expiry (_expire_assignment) produce exactly main's writes. Each new path runs
only when its own switch is on.
"""

from copy import deepcopy
from unittest.mock import Mock

import pytest

from config import backlog_state_machine as sm
from config.batch_pipeline import RECORD_DEAD_LETTER_SECONDS
from database.batch_pipeline_projection_release import MAX_RELEASE_ATTEMPTS, ProjectionReleaseStore
from tests.unit.test_batch_pipeline_projection_release import rows, store_for
from tests.unit.test_batch_pipeline_scheduler import MemoryStore
from utils.batch_pipeline import live

NEW_SWITCHES = (
    sm.RETRY_CAP_SWITCH,
    sm.SYNC_ATTEMPT_CARRY_SWITCH,
    sm.HELD_REDRIVE_BUDGET_SWITCH,
    sm.HELD_REDRIVE_COUNTER_SWITCH,
    sm.HELD_REDRIVE_STOP_SWITCH,
    sm.RECORD_BARRIER_DEAD_LETTER_SWITCH,
    sm.ASSIGNMENT_HOLD_ESCALATION_SWITCH,
)
NOW = 2_000_000.0
RESULT = ('batch_pipeline_prod_results', 'held')
JOB = ('batch_pipeline_prod_jobs', 'held')


@pytest.fixture
def switches_off(monkeypatch):
    for name in NEW_SWITCHES:
        monkeypatch.setenv(name, 'false')
    monkeypatch.setenv('OMI_ENV_STAGE', 'prod')
    monkeypatch.setenv('BATCH_HELD_DEAD_LETTER_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_PROJECTION_HOLD_RECOVERY_ENABLED', 'true')
    return monkeypatch


# Record barrier dead letter (main: record_barrier_aged) ----------------------------


def record_store(enqueued_ago):
    store = MemoryStore()
    store.rows['jobs', 'record'] = {
        'segment_id': 'record',
        'owner_id': 'owner',
        'conversation_id': 'capture',
        'privacy_generation': 3,
        'state': 'record_pending',
        'available_at': 0,
        'enqueued_at': NOW - enqueued_ago,
        'merge_pending': False,
        'audio_uri': 'gs://synthetic/immutable',
    }
    return store


def drain_with(monkeypatch, store, error):
    import asyncio

    async def refuse(*args, **kwargs):
        raise error

    monkeypatch.setattr(live, 'admit_recording', refuse)
    counter = Mock()
    asyncio.run(live.drain_recordings(store, metrics=Mock(record_dead_letter=counter)))
    return store.rows['jobs', 'record'], counter


def present_unfinished():
    # The real admission pre-check's barrier refusal for a present, unfinished conversation.
    return live.RecordBarrierOpen(live.BARRIER_NOT_CLOSED, conversation_present=True, conversation_status='in_progress')


@pytest.mark.parametrize('class4', ['false', None])
def test_main_record_dead_letter_runs_unchanged_with_class_4_off(switches_off, class4):
    monkeypatch = switches_off
    if class4 is None:
        monkeypatch.delenv(sm.RECORD_BARRIER_DEAD_LETTER_SWITCH)
    clock = [NOW]
    monkeypatch.setattr(live.time, 'time', lambda: clock[0])
    store = record_store(30 * 86400)
    row, counter = drain_with(monkeypatch, store, present_unfinished())
    # Main: the first barrier failure stamps the full window.
    assert row['record_dead_letter_deadline_at'] == NOW + RECORD_DEAD_LETTER_SECONDS
    assert row['state'] == 'record_pending' and 'barrier_redrives' not in row
    clock[0] = row['record_dead_letter_deadline_at'] + 1
    row['available_at'] = 0
    row, counter = drain_with(monkeypatch, store, present_unfinished())
    # Main: after the deadline the row settles as retained dead/record_barrier_aged.
    assert row['state'] == 'dead' and row['dead_letter_reason'] == 'record_barrier_aged'
    assert counter.inc.call_count == 1
    assert row['audio_uri'] == 'gs://synthetic/immutable'
    assert 'barrier_dead_letter' not in row and 'barrier_redrives' not in row


def test_class_4_on_owns_present_unfinished_rows_and_skips_main_dead_letter(switches_off):
    monkeypatch = switches_off
    monkeypatch.setenv(sm.RECORD_BARRIER_DEAD_LETTER_SWITCH, 'true')
    monkeypatch.setattr(live.time, 'time', lambda: NOW)
    store = record_store(30 * 86400)
    row, counter = drain_with(monkeypatch, store, present_unfinished())
    assert 'record_dead_letter_deadline_at' not in row
    assert row['state'] == 'record_pending' and row['barrier_redrives'] == 1
    assert counter.inc.call_count == 0


@pytest.mark.parametrize(
    'error',
    [
        # A missing conversation: class 4 never owns it.
        lambda: live.RecordBarrierOpen(live.BARRIER_NOT_CLOSED, conversation_present=False, conversation_status=None),
        # A completed conversation with open upload tokens: seal repair's cohort.
        lambda: live.RecordBarrierOpen(
            live.BARRIER_NOT_CLOSED, conversation_present=True, conversation_status='completed'
        ),
        # The transactional recheck's plain refusal.
        lambda: ValueError(live.BARRIER_NOT_CLOSED),
    ],
)
def test_class_4_on_leaves_main_dead_letter_for_rows_it_does_not_own(switches_off, error):
    monkeypatch = switches_off
    monkeypatch.setenv(sm.RECORD_BARRIER_DEAD_LETTER_SWITCH, 'true')
    monkeypatch.setattr(live.time, 'time', lambda: NOW)
    row, _ = drain_with(monkeypatch, record_store(30 * 86400), error())
    assert row['record_dead_letter_deadline_at'] == NOW + RECORD_DEAD_LETTER_SECONDS
    assert 'barrier_redrives' not in row


# Assignment-hold expiry (main: _expire_assignment) ----------------------------------


def gate_fail_rows(**extra):
    seeded = rows(projection={}, held_deadline_at=100.0, payload={'retained': True}, **extra)
    seeded[JOB]['state'] = 'committed'
    return seeded


@pytest.mark.parametrize('attempts', [None, MAX_RELEASE_ATTEMPTS])
def test_main_assignment_expiry_writes_exactly_mains_markers_with_switches_off(switches_off, attempts):
    extra = {} if attempts is None else {'projection_release_attempts': attempts}
    seeded = gate_fail_rows(**extra)
    before = deepcopy(seeded)
    client, store = store_for(seeded)
    release = ProjectionReleaseStore(store)
    assert release.release('held', 100.0) is False
    assert release.expired and not release.rearm_exhausted
    expected = {**before[RESULT], 'held_expired_reason': 'held_expired', 'held_expired_at': 100.0}
    if attempts is not None:
        # Main's one-time re-arm of an aged hold, with no backlog counters.
        expected.update(held_expired_release_attempts=attempts, projection_release_attempts=0)
    assert client.rows == {**before, RESULT: expected}


def test_counter_on_adds_only_the_rearm_count_to_mains_expiry(switches_off):
    switches_off.setenv(sm.HELD_REDRIVE_COUNTER_SWITCH, 'true')
    seeded = gate_fail_rows(projection_release_attempts=MAX_RELEASE_ATTEMPTS)
    before = deepcopy(seeded)
    client, store = store_for(seeded)
    assert ProjectionReleaseStore(store).release('held', 100.0) is False
    assert client.rows[RESULT] == {
        **before[RESULT],
        'held_expired_reason': 'held_expired',
        'held_expired_at': 100.0,
        'held_expired_release_attempts': MAX_RELEASE_ATTEMPTS,
        'projection_release_attempts': 0,
        'held_expired_rearms': 1,
    }


def test_stop_on_keeps_an_exhausted_receipts_budget_spent_on_mains_path(switches_off):
    switches_off.setenv(sm.HELD_REDRIVE_STOP_SWITCH, 'true')
    switches_off.setenv(sm.HELD_REDRIVE_COUNTER_SWITCH, 'true')
    seeded = gate_fail_rows(
        projection_release_attempts=MAX_RELEASE_ATTEMPTS, held_expired_rearms=sm.MAX_PROJECTION_REARMS
    )
    client, store = store_for(seeded)
    release = ProjectionReleaseStore(store)
    assert release.release('held', 100.0) is False
    assert release.expired and release.rearm_exhausted
    entry = client.rows[RESULT]
    assert entry['projection_release_attempts'] == MAX_RELEASE_ATTEMPTS
    assert entry['held_rearm_exhausted_at'] == 100.0


@pytest.mark.parametrize('escalation,stamped', [('false', False), ('true', True)])
def test_persisted_hold_never_expires_and_escalates_only_with_class_5_on(switches_off, escalation, stamped):
    switches_off.setenv(sm.ASSIGNMENT_HOLD_ESCALATION_SWITCH, escalation)
    seeded = rows(
        projection_state='persisted',
        projection={'state': 'quarantined', 'disposition': 'ambiguous_generation'},
        discarded=True,
        held_deadline_at=100.0,
    )
    seeded[JOB]['state'] = 'committed'
    before = deepcopy(seeded)
    client, store = store_for(seeded)
    release = ProjectionReleaseStore(store)
    assert release.release('held', 100.0) is False
    assert not release.expired
    entry = client.rows[RESULT]
    assert 'held_expired_reason' not in entry
    if stamped:
        assert entry['assignment_hold_deadline_at'] == 100.0 + sm.ASSIGNMENT_HOLD_DEADLINE_SECONDS
    else:
        assert client.rows == before
