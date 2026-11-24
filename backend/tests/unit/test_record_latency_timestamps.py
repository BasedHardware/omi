"""Stage clocks travel on existing writes; Home observation has no persistence."""

from datetime import datetime, timezone
from dataclasses import replace
from unittest.mock import Mock

import pytest

from database import record_audio
from database import batch_pipeline_intake
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from tests.unit.test_batch_pipeline_scheduler import MemoryStore, item
from utils.batch_pipeline.contracts import ProjectionBinding
from utils.batch_pipeline.scheduler import Scheduler
from utils.batch_pipeline import scheduler as scheduler_module
from utils.conversations import home_latency, home_step


def test_seal_stamps_actual_close_once_and_reseal_replaces_clock(monkeypatch):
    client = StrictFirestore()
    ref = client.collection('users').document('synthetic-owner').collection('conversations').document('capture')
    ref.create({'record_lane_owner': 'batch_sync_v1', 'record_audio_closed': False})
    monkeypatch.setattr(record_audio.time, 'time', lambda: 1000)
    assert record_audio.seal_record_audio('synthetic-owner', 'capture', firestore_client=client) is None
    assert ref.get().to_dict()['record_sealed_at'] == 1000
    assert ref.get().to_dict()['record_admitted_at'] == 1000
    assert record_audio.seal_record_audio('synthetic-owner', 'capture', firestore_client=client) is None
    assert not client.transactions[-1].sets and not client.transactions[-1].updates
    client.rows[ref.path]['record_audio_closed'] = False
    monkeypatch.setattr(record_audio.time, 'time', lambda: 1010)
    assert record_audio.seal_record_audio('synthetic-owner', 'capture', firestore_client=client) is None
    assert ref.get().to_dict()['record_sealed_at'] == 1010
    assert ref.get().to_dict()['record_admitted_at'] == 1000


def test_admission_copies_claim_and_seal_and_first_gpu_lease(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_UID_ALLOWLIST', 'synthetic-owner')
    monkeypatch.setenv('BATCH_PIPELINE_RECORD_PROTOCOL_READY', 'true')
    monkeypatch.setattr(batch_pipeline_intake.time, 'time', lambda: 1020)
    store = MemoryStore()
    binding = ProjectionBinding(
        'synthetic-owner',
        'job',
        'content',
        ('first',),
        native_record=True,
        record_origin=True,
        target_conversation_id='capture',
    )
    store.rows['jobs', 'first'] = {
        'state': 'record_pending',
        'owner_id': 'synthetic-owner',
        'privacy_generation': 0,
        'record_intake_claimed_at': 1010,
    }
    store.rows['conversations', 'synthetic-owner/capture'] = {
        'status': 'completed',
        'record_audio_closed': True,
        'record_lane_owner': 'batch_sync_v1',
        'finished_at': datetime.fromtimestamp(990, timezone.utc),
        'record_sealed_at': 1000,
    }
    batch_pipeline_intake.admit(
        store,
        [replace(item('first', owner='synthetic-owner', capture=900), privacy_generation=0)],
        binding,
        1010,
        namespace='test',
    )
    job = store.rows['jobs', 'first']
    assert (job['record_sealed_at'], job['record_intake_claimed_at'], job['record_ready_at']) == (1000, 1010, 1020)
    scheduler = Scheduler(store)
    monkeypatch.setattr(scheduler_module, 'wall_time', lambda: 1030)
    assert scheduler.pull(1015)  # A long pull began before staging finished.
    assert store.rows['jobs', 'first']['record_first_leased_at'] == 1030


@pytest.mark.parametrize('attempt,refusals', [(1, 0), (0, 1)])
def test_first_lease_clock_is_not_invented_for_historical_retries(attempt, refusals):
    store = MemoryStore()
    scheduler = Scheduler(store)
    scheduler.enqueue(item('retry'), 0)
    store.rows['jobs', 'retry'].update(
        projection_binding={'native_record': True},
        attempt=attempt,
        admission_refusals=refusals,
    )
    assert scheduler.pull(1)
    assert 'record_first_leased_at' not in store.rows['jobs', 'retry']


@pytest.mark.parametrize('stamp', [1000, datetime.fromtimestamp(1000, timezone.utc)])
def test_home_ready_metric_observes_once_per_process_revision_without_mutation(monkeypatch, stamp):
    metric = Mock()
    monkeypatch.setattr(home_latency, 'NOTES_TO_HOME', metric)
    monkeypatch.setattr(home_latency, '_SEEN', home_latency.OrderedDict())
    row = {
        'id': 'synthetic-capture',
        'record_lane_owner': 'batch_sync_v1',
        'notes_written_at': stamp,
        'finished_at': 990,
    }
    before = dict(row)
    home_latency.observe(row, now=1005)
    home_latency.observe(row, now=1010)
    metric.observe.assert_called_once_with(5)
    assert row == before


@pytest.mark.parametrize('finished,written', [(-1000, 1000), (1030, 1000), (None, 1000), (990, 980)])
def test_home_metric_excludes_old_or_untrusted_captures_and_pre_end_notes(monkeypatch, finished, written):
    metric = Mock()
    monkeypatch.setattr(home_latency, 'NOTES_TO_HOME', metric)
    home_latency.observe(
        {
            'id': 'synthetic-capture',
            'record_lane_owner': 'batch_sync_v1',
            'finished_at': finished,
            'notes_written_at': written,
        },
        now=1005,
    )
    metric.observe.assert_not_called()


def test_home_pending_row_does_not_count_as_readable(monkeypatch):
    observe = Mock()
    monkeypatch.setattr(home_latency, 'observe', observe)
    monkeypatch.setattr(home_step, 'classify', lambda _: home_step.WRITING_NOTES)
    home_step.project({'id': 'synthetic-capture'})
    observe.assert_not_called()
    monkeypatch.setattr(home_step, 'classify', lambda _: home_step.READY)
    home_step.project({'id': 'synthetic-capture'})
    observe.assert_called_once()
