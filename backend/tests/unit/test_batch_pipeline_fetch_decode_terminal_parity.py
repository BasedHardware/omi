"""Fetch_decode terminal dispositions route through storage, pump, shadow and recovery lanes.

The GPU worker's typed terminal evidence (ValidationFailureWork with a closed reason)
must survive every downstream lane unchanged: the pump publishes it as worker_failure,
the scheduler quarantines on the first attempt, the shadow CAS pins the same evidence,
and the fenced recovery lane holds the identical bytes once instead of re-reading them
on every sweep. This suite pins the routing parity for the retained-audio and decoded-
duration families alongside the pre-existing staged-audio contract.

Failure-Class: FC-permanent-retained-decode-failure-burns-retry-ladder
"""

import logging
import time
from unittest.mock import Mock

import pytest

from database.batch_pipeline_shadow import ShadowStore
from utils.batch_pipeline.contracts import (
    FailedWork,
    HeldWork,
    RecoveryWork,
    ValidationFailureWork,
    WorkResult,
)
from utils.batch_pipeline.errors import WORKER_VALIDATION_STAGES, validate_worker_failure
from utils.batch_pipeline.pump import Pump
from utils.batch_pipeline.scheduler import Scheduler
from utils.batch_pipeline.source_audio import RetainedAudioInvalid
from utils.observability.reasons import WorkerValidationReason
from tests.unit.test_batch_pipeline_quarantine_recovery import row, setup  # noqa: F401
from tests.unit.test_batch_pipeline_invalid_manifest_hold import serve
from tests.unit.test_batch_pipeline_scheduler import MemoryStore
from tests.unit.test_batch_pipeline_worker import item, setup_worker

RETAINED = WorkerValidationReason.RETAINED_AUDIO_INVALID.value
DURATION = WorkerValidationReason.DECODED_DURATION_MISMATCH.value


# --- Closed-set registry ------------------------------------------------------


def test_new_reasons_are_closed_vocabulary_members():
    from utils.batch_pipeline.errors import WORKER_VALIDATION_REASONS

    assert RETAINED in WORKER_VALIDATION_REASONS
    assert DURATION in WORKER_VALIDATION_REASONS
    assert WorkerValidationReason.RETAINED_AUDIO_INVALID.value == 'retained_audio_invalid'
    assert WorkerValidationReason.DECODED_DURATION_MISMATCH.value == 'decoded_duration_mismatch'


def test_validate_worker_failure_accepts_retained_audio_invalid():
    validate_worker_failure({'stage': 'fetch_decode', 'reason': RETAINED})


def test_validate_worker_failure_accepts_decoded_duration_mismatch():
    validate_worker_failure({'stage': 'fetch_decode', 'reason': DURATION})


def test_validate_worker_failure_still_rejects_an_unknown_reason():
    with pytest.raises(ValueError, match='closed worker validation failure required'):
        validate_worker_failure({'stage': 'fetch_decode', 'reason': 'mystery'})


def test_validation_failure_work_accepts_the_typed_reason():
    work = ValidationFailureWork('a', 'fetch_decode', RETAINED)
    assert (work.stage, work.reason) == ('fetch_decode', RETAINED)


def test_validation_failure_work_accepts_the_duration_reason():
    work = ValidationFailureWork('a', 'fetch_decode', DURATION)
    assert (work.stage, work.reason) == ('fetch_decode', DURATION)


def test_validation_failure_work_still_rejects_unknown_reason():
    with pytest.raises(ValueError):
        ValidationFailureWork('a', 'fetch_decode', 'mystery')


def test_fetch_decode_stage_token_is_unchanged():
    assert 'fetch_decode' in WORKER_VALIDATION_STAGES


# --- Pump routing ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_pump_routes_typed_failure_as_worker_failure(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'false')
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    lease = queue.pull(time.time())[0]
    fail = Mock(wraps=queue.fail)
    monkeypatch.setattr(queue, 'fail', fail)
    worker, *_ = setup_worker()
    assert await Pump(queue, worker)._publish(lease, {'a': ValidationFailureWork('a', 'fetch_decode', RETAINED)}, set())
    assert fail.call_args.kwargs['worker_failure'] == {'stage': 'fetch_decode', 'reason': RETAINED}
    assert 'quarantine' not in fail.call_args.kwargs


@pytest.mark.asyncio
async def test_pump_routes_duration_mismatch_as_worker_failure(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'false')
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    lease = queue.pull(time.time())[0]
    fail = Mock(wraps=queue.fail)
    monkeypatch.setattr(queue, 'fail', fail)
    worker, *_ = setup_worker()
    assert await Pump(queue, worker)._publish(lease, {'a': ValidationFailureWork('a', 'fetch_decode', DURATION)}, set())
    assert fail.call_args.kwargs['worker_failure'] == {'stage': 'fetch_decode', 'reason': DURATION}


@pytest.mark.asyncio
async def test_pump_typed_failure_quarantines_first_attempt(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'false')
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    lease = queue.pull(time.time())[0]
    worker, *_ = setup_worker()
    assert await Pump(queue, worker)._publish(lease, {'a': ValidationFailureWork('a', 'fetch_decode', RETAINED)}, set())
    job = store.rows['jobs', 'a']
    assert job['state'] == 'quarantined' and job['attempt'] == 1
    assert job['worker_failure'] == {'stage': 'fetch_decode', 'reason': RETAINED}
    assert job['recovery_state'] == 'held' and not job['merge_pending']


@pytest.mark.asyncio
async def test_pump_typed_failure_not_repulled_after_publish(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'false')
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    now = time.time()
    lease = queue.pull(now)[0]
    worker, *_ = setup_worker()
    assert await Pump(queue, worker)._publish(lease, {'a': ValidationFailureWork('a', 'fetch_decode', DURATION)}, set())
    now += 3600
    assert queue.recover(now) == 0
    assert queue.pull(now) == []


@pytest.mark.asyncio
async def test_pump_recovery_work_still_sets_quarantine_kwarg(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    lease = queue.pull(time.time())[0]
    fail = Mock(wraps=queue.fail)
    monkeypatch.setattr(queue, 'fail', fail)
    worker, *_ = setup_worker()
    assert await Pump(queue, worker)._publish(lease, {'a': RecoveryWork('a')}, set())
    assert fail.call_args.kwargs['quarantine'] is True
    assert fail.call_args.kwargs['worker_failure'] == {'stage': 'assemble_words', 'reason': 'empty_asr'}


@pytest.mark.asyncio
async def test_pump_failed_work_takes_the_defer_path(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    lease = queue.pull(time.time())[0]
    fail = Mock(wraps=queue.fail)
    monkeypatch.setattr(queue, 'fail', fail)
    worker, *_ = setup_worker()
    assert await Pump(queue, worker)._publish(lease, {'a': FailedWork('a', None, None)}, set())
    assert 'worker_failure' not in fail.call_args.kwargs
    assert store.rows['jobs', 'a']['state'] == 'retry'


@pytest.mark.asyncio
async def test_pump_success_still_completes(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'false')
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    lease = queue.pull(time.time())[0]
    complete = Mock(wraps=queue.complete)
    monkeypatch.setattr(queue, 'complete', complete)
    worker, *_ = setup_worker()
    assert await Pump(queue, worker)._publish(lease, {'a': WorkResult('a', 'encrypted-result://a')}, set())
    assert complete.call_args.args[0].result_uri == 'encrypted-result://a'
    assert store.rows['jobs', 'a']['state'] == 'result_ready'


@pytest.mark.asyncio
async def test_pump_held_work_still_defers_with_admission_refused(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'false')
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    lease = queue.pull(time.time())[0]
    defer = Mock(wraps=queue.defer)
    monkeypatch.setattr(queue, 'defer', defer)
    worker, *_ = setup_worker()
    # HeldWork publishes False by contract: the unit stays parked, not completed.
    assert await Pump(queue, worker)._publish(lease, {'a': HeldWork('a', 60, 'capacity')}, set()) is False
    assert defer.call_args.kwargs['admission_refused'] is True
    assert defer.call_args.kwargs['held_reason'] == 'capacity'
    assert store.rows['jobs', 'a']['state'] == 'retry'


# --- Shadow CAS parity ----------------------------------------------------------


@pytest.fixture
def shadow_store():
    from tests.unit.fixtures.shadow_slot_cas_firestore import ShadowStoreDouble

    return ShadowStoreDouble()


@pytest.fixture
def repository(shadow_store, monkeypatch):
    import database.batch_pipeline_shadow as shadow_module
    from utils.batch_pipeline import quarantine_recovery as recovery

    assert recovery.SECOND_PROVIDER == 'soniox'
    monkeypatch.setenv('BATCH_PIPELINE_SHADOW_PERCENT', '100')
    monkeypatch.setattr(shadow_module, 'shadow_slot_cas_enabled', lambda: True)
    return ShadowStore(shadow_store, clock=shadow_store.clock, busy=lambda: False)


def ready_offer(repository, name='one'):
    from utils.batch_pipeline.contracts import WorkItem as Item

    repository.offer('worker-' + name)
    reservation = repository.reserve('synthetic-owner', 'content', 'deep')
    assert reservation is not None, 'admission expected an idle slot'
    item_work = Item(reservation[0], 'synthetic-owner', 1, 'encrypted:shadow', 2, 0, shadow=True, privacy_generation=0)
    assert repository.ready(reservation, item_work, '') is True
    return item_work


def test_shadow_handoff_pins_typed_failure_evidence(repository):
    shadow_item = ready_offer(repository)
    repository.take('worker-one')
    assert repository.handoff(
        shadow_item.segment_id, ValidationFailureWork(shadow_item.segment_id, 'fetch_decode', RETAINED)
    )
    job = repository.store.job(shadow_item.segment_id)
    assert job['state'] == 'recovery_ready'
    assert job['worker_failure'] == {'stage': 'fetch_decode', 'reason': RETAINED}


def test_shadow_handoff_pins_duration_mismatch_evidence(repository):
    shadow_item = ready_offer(repository)
    repository.take('worker-one')
    assert repository.handoff(
        shadow_item.segment_id, ValidationFailureWork(shadow_item.segment_id, 'fetch_decode', DURATION)
    )
    assert repository.store.job(shadow_item.segment_id)['worker_failure']['reason'] == DURATION


def test_shadow_handoff_still_pins_recovery_evidence(repository):
    shadow_item = ready_offer(repository)
    repository.take('worker-one')
    assert repository.handoff(shadow_item.segment_id, RecoveryWork(shadow_item.segment_id))
    job = repository.store.job(shadow_item.segment_id)
    assert job['state'] == 'recovery_ready'
    # Padded-retry evidence is stored only when the retry actually carried one.
    assert 'worker_empty_evidence' not in job


def test_shadow_handoff_refuses_mismatched_segment(repository):
    shadow_item = ready_offer(repository)
    repository.take('worker-one')
    with pytest.raises(ValueError, match='typed worker recovery evidence required'):
        repository.handoff('sh_other', ValidationFailureWork(shadow_item.segment_id, 'fetch_decode', RETAINED))


def test_shadow_handoff_refuses_untyped_evidence(repository):
    shadow_item = ready_offer(repository)
    repository.take('worker-one')
    with pytest.raises(ValueError, match='typed worker recovery evidence required'):
        repository.handoff(shadow_item.segment_id, {'stage': 'fetch_decode', 'reason': RETAINED})


def test_shadow_take_refuses_after_recovery_ready(repository):
    shadow_item = ready_offer(repository)
    repository.take('worker-one')
    repository.handoff(shadow_item.segment_id, ValidationFailureWork(shadow_item.segment_id, 'fetch_decode', RETAINED))
    assert repository.take('worker-two') is None


# --- Fenced recovery lane ---------------------------------------------------------


def test_recovery_holds_once_for_typed_checksum(setup, monkeypatch, caplog):
    caplog.set_level(logging.INFO)
    client, _, _, artifacts, stt, _ = setup
    artifacts.fetch_audio.side_effect = RetainedAudioInvalid('retained capture checksum mismatch')
    response = serve(setup, monkeypatch).post(
        '/v2/batch-pipeline/recover-quarantine', json={'stage': 'prod', 'segment_id': 'bad'}
    )
    assert response.status_code == 200 and response.json() == {'status': 'failed_held'}
    job = row(client)
    assert job['recovery_state'] == 'failed_held'
    assert job['recovery']['refusal'] == {'reason': RETAINED}
    stt.assert_not_called()


def test_recovery_holds_once_for_typed_invalid_pcm(setup, monkeypatch):
    client, _, _, artifacts, stt, _ = setup
    artifacts.fetch_audio.side_effect = RetainedAudioInvalid('invalid retained PCM')
    response = serve(setup, monkeypatch).post(
        '/v2/batch-pipeline/recover-quarantine', json={'stage': 'prod', 'segment_id': 'bad'}
    )
    assert response.status_code == 200 and response.json() == {'status': 'failed_held'}
    assert row(client)['recovery']['refusal'] == {'reason': RETAINED}
    stt.assert_not_called()


def test_recovery_holds_once_for_typed_authentication(setup, monkeypatch):
    client, _, _, artifacts, stt, _ = setup
    artifacts.fetch_audio.side_effect = RetainedAudioInvalid('retained audio authentication failed')
    response = serve(setup, monkeypatch).post(
        '/v2/batch-pipeline/recover-quarantine', json={'stage': 'prod', 'segment_id': 'bad'}
    )
    assert response.json() == {'status': 'failed_held'}
    assert row(client)['recovery']['refusal'] == {'reason': RETAINED}


def test_recovery_manifest_hold_event_name_is_preserved(setup, monkeypatch, caplog):
    from utils.batch_pipeline.source_audio import InvalidRetainedManifest

    caplog.set_level(logging.INFO)
    client, _, _, artifacts, stt, _ = setup
    artifacts.fetch_audio.side_effect = InvalidRetainedManifest('invalid retained audio slice')
    serve(setup, monkeypatch).post('/v2/batch-pipeline/recover-quarantine', json={'stage': 'prod', 'segment_id': 'bad'})
    assert 'event=batch_quarantine_recovery outcome=failed_held reason=invalid_retained_manifest' in caplog.text
    assert row(client)['recovery']['refusal'] == {'reason': 'invalid_retained_manifest'}


def test_recovery_typed_hold_event_carries_the_new_reason(setup, monkeypatch, caplog):
    caplog.set_level(logging.INFO)
    client, _, _, artifacts, stt, _ = setup
    artifacts.fetch_audio.side_effect = RetainedAudioInvalid('retained capture checksum mismatch')
    serve(setup, monkeypatch).post('/v2/batch-pipeline/recover-quarantine', json={'stage': 'prod', 'segment_id': 'bad'})
    assert 'event=batch_quarantine_recovery outcome=failed_held reason=retained_audio_invalid' in caplog.text


def test_recovery_failed_held_leaves_the_candidate_set(setup, monkeypatch):
    client, _, binding, artifacts, stt, recovery = setup
    artifacts.fetch_audio.side_effect = RetainedAudioInvalid('retained capture checksum mismatch')
    http = serve(setup, monkeypatch)
    payload = {'stage': 'prod', 'segment_id': 'bad'}
    assert http.post('/v2/batch-pipeline/recover-quarantine', json=payload).json() == {'status': 'failed_held'}
    assert recovery.protocol.prepare('bad', binding.owner_id, 200) is None
    assert http.post('/v2/batch-pipeline/recover-quarantine', json=payload).json() == {'status': 'held'}
    artifacts.fetch_audio.assert_called_once()


def test_recovery_hold_keeps_audio_without_persist_or_delete(setup, monkeypatch):
    client, _, _, artifacts, stt, _ = setup
    artifacts.fetch_audio.side_effect = RetainedAudioInvalid('invalid retained PCM')
    http = serve(setup, monkeypatch)
    http.post('/v2/batch-pipeline/recover-quarantine', json={'stage': 'prod', 'segment_id': 'bad'})
    assert not [name for name, *_ in artifacts.mock_calls if 'delete' in name or 'persist' in name]
    stt.assert_not_called()


def test_recovery_transient_error_stays_prepared(setup, monkeypatch):
    client, _, _, artifacts, stt, _ = setup
    artifacts.fetch_audio.side_effect = OSError('storage unavailable')
    response = serve(setup, monkeypatch).post(
        '/v2/batch-pipeline/recover-quarantine', json={'stage': 'prod', 'segment_id': 'bad'}
    )
    assert response.status_code == 500
    assert row(client)['recovery_state'] == 'prepared' and 'refusal' not in row(client)['recovery']


def test_recovery_hold_default_refusal_reason_unchanged(setup):
    client, _, binding, _, _, recovery = setup
    token = recovery.protocol.prepare('bad', binding.owner_id, 100)['recovery']['token']
    assert recovery.protocol.hold_invalid_manifest('bad', token, 100, audio_uri='gs://synthetic/audio')
    assert row(client)['recovery']['refusal'] == {'reason': 'invalid_retained_manifest'}


def test_recovery_hold_accepts_typed_refusal_reason(setup):
    client, _, binding, _, _, recovery = setup
    token = recovery.protocol.prepare('bad', binding.owner_id, 100)['recovery']['token']
    assert recovery.protocol.hold_invalid_manifest(
        'bad', token, 100, audio_uri='gs://synthetic/audio', refusal_reason=RETAINED
    )
    assert row(client)['recovery']['refusal'] == {'reason': RETAINED}


def test_recovery_hold_is_fenced_to_unstarted_intents(setup):
    client, _, binding, _, _, recovery = setup
    token = recovery.protocol.prepare('bad', binding.owner_id, 100)['recovery']['token']
    assert not recovery.protocol.hold_invalid_manifest('bad', 'f' * 32, 100, audio_uri='gs://synthetic/audio')
    assert not recovery.protocol.hold_invalid_manifest('bad', token, 100, audio_uri='gs://synthetic/other')
    assert recovery.protocol.start('bad', token, 100)
    assert not recovery.protocol.hold_invalid_manifest(
        'bad', token, 100, audio_uri='gs://synthetic/audio', refusal_reason=RETAINED
    )


def test_recovery_hold_requires_prepared_quarantined_state(setup):
    client, _, binding, _, _, recovery = setup
    token = recovery.protocol.prepare('bad', binding.owner_id, 100)['recovery']['token']
    row(client)['state'] = 'committed'
    assert not recovery.protocol.hold_invalid_manifest(
        'bad', token, 100, audio_uri='gs://synthetic/audio', refusal_reason=RETAINED
    )
