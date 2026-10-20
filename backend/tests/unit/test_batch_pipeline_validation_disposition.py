"""Production failure shapes through worker, lease fencing and ordered merge."""

from dataclasses import replace
import time
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pytest

from config.batch_pipeline import worker_validation_disposition_enabled
from diarizer import batch_pipeline, batch_pipeline_models
from diarizer.batch_pipeline import BatchValidationError, ValidationReason
from diarizer.batch_pipeline_models import PyannoteVAD
from tests.unit.test_batch_pipeline_scheduler import MemoryStore
from tests.unit.test_batch_pipeline_worker import item, setup_worker
from utils.batch_pipeline.contracts import ValidationFailureWork, WorkResult
from utils.batch_pipeline.pump import Pump
from utils.batch_pipeline.scheduler import Scheduler
from utils.stt import local_vad
from utils.batch_pipeline.worker_silence import inspect_worker_silence


def test_validation_disposition_ships_on_and_has_a_kill_switch(monkeypatch):
    monkeypatch.delenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', raising=False)
    assert worker_validation_disposition_enabled()
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'false')
    assert not worker_validation_disposition_enabled()


def test_real_strict_vad_checks_the_20ms_partial_window():
    payload = inspect_worker_silence(item('short', 0.02), np.zeros(320, dtype=np.float32))
    assert payload['outcome'] == 'silence' and payload['speech_spans'] == []


@pytest.mark.asyncio
@pytest.mark.parametrize('speech', [False, True, 'unavailable'])
async def test_20ms_frame_beyond_eof_needs_independent_silence_evidence(monkeypatch, speech):
    monkeypatch.delenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', raising=False)
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_SILENCE_DISPOSITION_ENABLED', 'false')
    # Exercise the actual Pyannote adapter with a synthetic frame whose start
    # lies beyond this 320-sample buffer. No model/GPU/private audio needed.
    monkeypatch.setattr(
        batch_pipeline_models,
        'torch',
        SimpleNamespace(
            inference_mode=batch_pipeline_models.nullcontext,
            from_numpy=lambda _: SimpleNamespace(unsqueeze=lambda _: None),
        ),
    )
    output = SimpleNamespace(
        get_timeline=lambda: SimpleNamespace(support=lambda: [SimpleNamespace(start=0.03, end=0.05)])
    )
    strict = Mock(
        **(
            {'side_effect': RuntimeError('synthetic-private-error')}
            if speech == 'unavailable'
            else {'return_value': [{'start': 0, 'end': 0.02}] if speech else []}
        )
    )
    monkeypatch.setattr(local_vad, 'offline_pcm_speech_segments', strict)
    worker, provider, saved, _, diarized, _ = setup_worker(
        decode=lambda work: np.zeros(round(work.duration_seconds * 16000), dtype=np.float32),
        vad=PyannoteVAD(lambda _: output),
    )
    store = MemoryStore()
    scheduler = Scheduler(store)
    scheduler.enqueue(item('short', 0.02), time.time())
    await Pump(scheduler, worker).run_once()
    strict.assert_called_once()
    assert provider.calls == [] and not diarized
    job = store.rows['jobs', 'short']
    assert job['attempt'] == 1
    if speech is False:
        assert job['state'] == 'committed'
        assert job['result']['outcome'] == 'silence'
        assert saved['short']['words_provider'] == 'strict_local_vad'
        assert saved['short']['speech_spans'] == []
        assert 'quarantine_reason' not in job
    else:
        assert job['state'] == 'quarantined' and job['recovery_state'] == 'held'
        assert job['worker_failure'] == {'stage': 'vad_windows', 'reason': 'vad_bounds'}
        assert not saved and ('results', 'short') not in store.rows
        assert scheduler.pull(time.time() + 1000) == []


@pytest.mark.asyncio
@pytest.mark.parametrize('reason', list(ValidationReason))
async def test_deterministic_failure_first_attempt_keeps_custody_and_drains_sibling(monkeypatch, reason):
    monkeypatch.delenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', raising=False)
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_RECOVERY_ENABLED', 'false')
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_DISPOSITION_ENABLED', 'false')
    stage = 'vad_windows' if reason.value.startswith('vad_') else 'word_clocks'
    store = MemoryStore()
    scheduler = Scheduler(store)
    before = item('poison')
    after = replace(before, segment_id='after', capture_at=101)
    for work in [before, after]:
        scheduler.enqueue(work, time.time())

    # Use the real fail classifier, with no provider call needed for this matrix.
    def broken(_):
        raise BatchValidationError(reason)

    worker, *_ = setup_worker(vad=broken)
    assert worker.process_batch([before]) == [ValidationFailureWork('poison', 'vad_windows', reason.value)]
    worker = Mock()
    worker.process_batch.return_value = [
        ValidationFailureWork('poison', stage, reason.value),
        WorkResult('after', 'encrypted://after'),
    ]
    await Pump(scheduler, worker).run_once()
    job = store.rows['jobs', 'poison']
    assert job['attempt'] == 1 and job['state'] == 'quarantined'
    assert job['worker_failure'] == {'stage': stage, 'reason': reason.value}
    assert not job['merge_pending'] and not job['token'] and job['lease_until'] == 0
    assert job['recovery_state'] == 'held'
    assert store.rows['jobs', 'after']['state'] == 'committed'
    assert ('results', 'poison') not in store.rows
    assert not scheduler.complete(WorkResult('poison', 'encrypted://late'), 'stale', time.time())


def test_invalid_failure_codes_cannot_persist_private_error_messages():
    store = MemoryStore()
    scheduler = Scheduler(store)
    scheduler.enqueue(item(), 0)
    lease = scheduler.pull(0)[0]
    for failure in [
        {'stage': 'vad_windows', 'reason': 'synthetic-private-message'},
        {'stage': 'synthetic-private-message', 'reason': 'vad_bounds'},
        {'stage': 'vad_windows', 'reason': 'vad_bounds', 'message': 'private'},
    ]:
        with pytest.raises(ValueError, match='closed worker validation'):
            scheduler.fail('a', lease.token, 1, worker_failure=failure)
    assert store.rows['jobs', 'a']['state'] == 'leased'
    assert not scheduler.fail('a', 'stale', 1, worker_failure={'stage': 'vad_windows', 'reason': 'vad_bounds'})


@pytest.mark.asyncio
async def test_kill_switch_restores_retry_with_backoff(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'false')

    def broken(_):
        raise BatchValidationError(ValidationReason.VAD_BOUNDS)

    strict = Mock(side_effect=AssertionError('kill switch must bypass new disposition'))
    monkeypatch.setattr(batch_pipeline, 'inspect_worker_silence', strict)
    worker, *_ = setup_worker(vad=broken)
    store = MemoryStore()
    scheduler = Scheduler(store)
    scheduler.enqueue(item(), time.time())
    await Pump(scheduler, worker).run_once()
    job = store.rows['jobs', 'a']
    assert job['state'] == 'retry' and job['attempt'] == 1
    assert job['available_at'] > time.time()
    strict.assert_not_called()


@pytest.mark.asyncio
async def test_unknown_transient_fault_still_retries_with_backoff():
    def unavailable(_):
        raise TimeoutError('synthetic-private-message')

    worker, *_ = setup_worker(vad=unavailable)
    store = MemoryStore()
    scheduler = Scheduler(store)
    scheduler.enqueue(item(), time.time())
    await Pump(scheduler, worker).run_once()
    job = store.rows['jobs', 'a']
    assert job['state'] == 'retry' and job['attempt'] == 1
    assert job['available_at'] > time.time()
    assert 'worker_failure' not in job
