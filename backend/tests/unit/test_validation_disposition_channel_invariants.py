# Failure-Class: FC-terminal-validation-disposition-misbooked-as-worker-fault
"""The demotion rechannels the report and nothing else.

For every family arm the durable accounting is pinned unchanged next to the
new channel: quarantine state, attempt retention, evidence booking, the
recovery_held metric, the awaiting-fenced-recovery warning, the correctness
meter, lease fences and the recovery lane's retry-due answers. Severity is
exclusive — the demoted path emits no ERROR and the fault path no INFO —
shadow units keep the shadow line ahead of classification, and the pump's
``ValidationFailureWork`` wiring lands the same worker_failure dict that the
scheduler rechannels, end to end, for every family reason.
"""

import logging
import time
from unittest.mock import Mock

import pytest

from tests.unit.test_batch_pipeline_scheduler import MemoryStore, item as sched_item
from tests.unit.test_batch_pipeline_worker import item as worker_item, setup_worker
from utils.batch_pipeline.artifacts import StagedArtifactInvalid
from utils.batch_pipeline.audio import StagedAudioInvalid
from utils.batch_pipeline.contracts import (
    FailedWork,
    Priority,
    ValidationFailureWork,
    WorkResult,
)
from utils.batch_pipeline.pump import Pump
from utils.batch_pipeline.scheduler import Scheduler
from utils.batch_pipeline.source_audio import RetainedAudioInvalid
from utils.batch_pipeline.word_validation import BatchValidationError, ValidationReason
from diarizer.batch_pipeline import DecodedDurationMismatch

TRIO = ('staged_audio_invalid', 'retained_audio_invalid', 'decoded_duration_mismatch')
FLAGGED = ('word_shape', 'word_clock', 'word_sequence', 'vad_nonfinite', 'vad_order', 'vad_bounds')


def _queued(metrics=None):
    store = MemoryStore()
    queue = Scheduler(store, metrics=metrics)
    work = sched_item("a", owner="inv-disp-owner", duration=30, priority=Priority.FRESH)
    assert queue.enqueue(work, time.time())
    lease = queue.pull(time.time())[0]
    return store, queue, lease


def _fail(queue, lease, **kwargs):
    return queue.fail(lease.item.segment_id, lease.token, time.time() + 100.0, **kwargs)


def _disposition(caplog):
    return [r for r in caplog.records if "event=batch_validation_disposition" in r.getMessage()]


def _worker_handoff(caplog):
    return [
        r for r in caplog.records if "event=batch_validation_disposition outcome=recovery_handoff" in r.getMessage()
    ]


def _scheduler_hold(caplog):
    return [
        r for r in caplog.records if "event=batch_validation_disposition outcome=held_for_disposition" in r.getMessage()
    ]


def _quar(caplog):
    return [r for r in caplog.records if "event=batch_quarantined" in r.getMessage()]


@pytest.mark.asyncio
async def test_pump_wiring_staged_audio_invalid_lands_the_rechanneled_hold(monkeypatch, caplog):
    """Pump -> scheduler: the staged_audio_invalid ValidationFailureWork books the disposition hold end to end."""
    monkeypatch.setenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", "true")
    monkeypatch.setenv("BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED", "true")
    monkeypatch.setenv("BATCH_PIPELINE_DIARIZE_SPEECH_ONLY_ENABLED", "false")
    monkeypatch.setenv("BATCH_PIPELINE_SHORT_SPEECH_SINGLE_ENABLED", "false")
    caplog.set_level(logging.INFO)

    def decode(work):
        raise StagedAudioInvalid('staged')

    worker, *_ = setup_worker(decode=decode)
    results = worker.process_batch([worker_item()])
    assert isinstance(results[0], ValidationFailureWork)
    store, queue, lease = _queued()
    assert await Pump(queue, worker)._publish(lease, {"a": results[0]}, set()) is True
    job = store.rows["jobs", "a"]
    assert job["state"] == "quarantined" and job["attempt"] == 1
    assert job["worker_failure"] == {"stage": "fetch_decode", "reason": "staged_audio_invalid"}
    assert not _quar(caplog)
    assert len(_worker_handoff(caplog)) == 1
    assert len(_scheduler_hold(caplog)) == 1


@pytest.mark.asyncio
async def test_pump_wiring_retained_audio_invalid_lands_the_rechanneled_hold(monkeypatch, caplog):
    """Pump -> scheduler: the retained_audio_invalid ValidationFailureWork books the disposition hold end to end."""
    monkeypatch.setenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", "true")
    monkeypatch.setenv("BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED", "true")
    monkeypatch.setenv("BATCH_PIPELINE_DIARIZE_SPEECH_ONLY_ENABLED", "false")
    monkeypatch.setenv("BATCH_PIPELINE_SHORT_SPEECH_SINGLE_ENABLED", "false")
    caplog.set_level(logging.INFO)

    def decode(work):
        raise RetainedAudioInvalid('retained')

    worker, *_ = setup_worker(decode=decode)
    results = worker.process_batch([worker_item()])
    assert isinstance(results[0], ValidationFailureWork)
    store, queue, lease = _queued()
    assert await Pump(queue, worker)._publish(lease, {"a": results[0]}, set()) is True
    job = store.rows["jobs", "a"]
    assert job["state"] == "quarantined" and job["attempt"] == 1
    assert job["worker_failure"] == {"stage": "fetch_decode", "reason": "retained_audio_invalid"}
    assert not _quar(caplog)
    assert len(_worker_handoff(caplog)) == 1
    assert len(_scheduler_hold(caplog)) == 1


@pytest.mark.asyncio
async def test_pump_wiring_decoded_duration_mismatch_lands_the_rechanneled_hold(monkeypatch, caplog):
    """Pump -> scheduler: the decoded_duration_mismatch ValidationFailureWork books the disposition hold end to end."""
    monkeypatch.setenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", "true")
    monkeypatch.setenv("BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED", "true")
    monkeypatch.setenv("BATCH_PIPELINE_DIARIZE_SPEECH_ONLY_ENABLED", "false")
    monkeypatch.setenv("BATCH_PIPELINE_SHORT_SPEECH_SINGLE_ENABLED", "false")
    caplog.set_level(logging.INFO)

    def decode(work):
        raise DecodedDurationMismatch('extent')

    worker, *_ = setup_worker(decode=decode)
    results = worker.process_batch([worker_item()])
    assert isinstance(results[0], ValidationFailureWork)
    store, queue, lease = _queued()
    assert await Pump(queue, worker)._publish(lease, {"a": results[0]}, set()) is True
    job = store.rows["jobs", "a"]
    assert job["state"] == "quarantined" and job["attempt"] == 1
    assert job["worker_failure"] == {"stage": "fetch_decode", "reason": "decoded_duration_mismatch"}
    assert not _quar(caplog)
    assert len(_worker_handoff(caplog)) == 1
    assert len(_scheduler_hold(caplog)) == 1


@pytest.mark.asyncio
async def test_pump_wiring_word_shape_lands_the_rechanneled_hold(monkeypatch, caplog):
    """Pump -> scheduler: the word_shape ValidationFailureWork books the disposition hold end to end."""
    monkeypatch.setenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", "true")
    monkeypatch.setenv("BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED", "true")
    monkeypatch.setenv("BATCH_PIPELINE_DIARIZE_SPEECH_ONLY_ENABLED", "false")
    monkeypatch.setenv("BATCH_PIPELINE_SHORT_SPEECH_SINGLE_ENABLED", "false")
    caplog.set_level(logging.INFO)

    def decode(work):
        raise BatchValidationError(ValidationReason.WORD_SHAPE)

    worker, *_ = setup_worker(decode=decode)
    results = worker.process_batch([worker_item()])
    assert isinstance(results[0], ValidationFailureWork)
    store, queue, lease = _queued()
    assert await Pump(queue, worker)._publish(lease, {"a": results[0]}, set()) is True
    job = store.rows["jobs", "a"]
    assert job["state"] == "quarantined" and job["attempt"] == 1
    assert job["worker_failure"] == {"stage": "fetch_decode", "reason": "word_shape"}
    assert not _quar(caplog)
    assert len(_worker_handoff(caplog)) == 1
    assert len(_scheduler_hold(caplog)) == 1


@pytest.mark.asyncio
async def test_pump_wiring_word_clock_lands_the_rechanneled_hold(monkeypatch, caplog):
    """Pump -> scheduler: the word_clock ValidationFailureWork books the disposition hold end to end."""
    monkeypatch.setenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", "true")
    monkeypatch.setenv("BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED", "true")
    monkeypatch.setenv("BATCH_PIPELINE_DIARIZE_SPEECH_ONLY_ENABLED", "false")
    monkeypatch.setenv("BATCH_PIPELINE_SHORT_SPEECH_SINGLE_ENABLED", "false")
    caplog.set_level(logging.INFO)

    def decode(work):
        raise BatchValidationError(ValidationReason.WORD_CLOCK)

    worker, *_ = setup_worker(decode=decode)
    results = worker.process_batch([worker_item()])
    assert isinstance(results[0], ValidationFailureWork)
    store, queue, lease = _queued()
    assert await Pump(queue, worker)._publish(lease, {"a": results[0]}, set()) is True
    job = store.rows["jobs", "a"]
    assert job["state"] == "quarantined" and job["attempt"] == 1
    assert job["worker_failure"] == {"stage": "fetch_decode", "reason": "word_clock"}
    assert not _quar(caplog)
    assert len(_worker_handoff(caplog)) == 1
    assert len(_scheduler_hold(caplog)) == 1


@pytest.mark.asyncio
async def test_pump_wiring_word_sequence_lands_the_rechanneled_hold(monkeypatch, caplog):
    """Pump -> scheduler: the word_sequence ValidationFailureWork books the disposition hold end to end."""
    monkeypatch.setenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", "true")
    monkeypatch.setenv("BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED", "true")
    monkeypatch.setenv("BATCH_PIPELINE_DIARIZE_SPEECH_ONLY_ENABLED", "false")
    monkeypatch.setenv("BATCH_PIPELINE_SHORT_SPEECH_SINGLE_ENABLED", "false")
    caplog.set_level(logging.INFO)

    def decode(work):
        raise BatchValidationError(ValidationReason.WORD_SEQUENCE)

    worker, *_ = setup_worker(decode=decode)
    results = worker.process_batch([worker_item()])
    assert isinstance(results[0], ValidationFailureWork)
    store, queue, lease = _queued()
    assert await Pump(queue, worker)._publish(lease, {"a": results[0]}, set()) is True
    job = store.rows["jobs", "a"]
    assert job["state"] == "quarantined" and job["attempt"] == 1
    assert job["worker_failure"] == {"stage": "fetch_decode", "reason": "word_sequence"}
    assert not _quar(caplog)
    assert len(_worker_handoff(caplog)) == 1
    assert len(_scheduler_hold(caplog)) == 1


@pytest.mark.asyncio
async def test_pump_wiring_vad_nonfinite_lands_the_rechanneled_hold(monkeypatch, caplog):
    """Pump -> scheduler: the vad_nonfinite ValidationFailureWork books the disposition hold end to end."""
    monkeypatch.setenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", "true")
    monkeypatch.setenv("BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED", "true")
    monkeypatch.setenv("BATCH_PIPELINE_DIARIZE_SPEECH_ONLY_ENABLED", "false")
    monkeypatch.setenv("BATCH_PIPELINE_SHORT_SPEECH_SINGLE_ENABLED", "false")
    caplog.set_level(logging.INFO)

    def decode(work):
        raise BatchValidationError(ValidationReason.VAD_NONFINITE)

    worker, *_ = setup_worker(decode=decode)
    results = worker.process_batch([worker_item()])
    assert isinstance(results[0], ValidationFailureWork)
    store, queue, lease = _queued()
    assert await Pump(queue, worker)._publish(lease, {"a": results[0]}, set()) is True
    job = store.rows["jobs", "a"]
    assert job["state"] == "quarantined" and job["attempt"] == 1
    assert job["worker_failure"] == {"stage": "fetch_decode", "reason": "vad_nonfinite"}
    assert not _quar(caplog)
    assert len(_worker_handoff(caplog)) == 1
    assert len(_scheduler_hold(caplog)) == 1


@pytest.mark.asyncio
async def test_pump_wiring_vad_order_lands_the_rechanneled_hold(monkeypatch, caplog):
    """Pump -> scheduler: the vad_order ValidationFailureWork books the disposition hold end to end."""
    monkeypatch.setenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", "true")
    monkeypatch.setenv("BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED", "true")
    monkeypatch.setenv("BATCH_PIPELINE_DIARIZE_SPEECH_ONLY_ENABLED", "false")
    monkeypatch.setenv("BATCH_PIPELINE_SHORT_SPEECH_SINGLE_ENABLED", "false")
    caplog.set_level(logging.INFO)

    def decode(work):
        raise BatchValidationError(ValidationReason.VAD_ORDER)

    worker, *_ = setup_worker(decode=decode)
    results = worker.process_batch([worker_item()])
    assert isinstance(results[0], ValidationFailureWork)
    store, queue, lease = _queued()
    assert await Pump(queue, worker)._publish(lease, {"a": results[0]}, set()) is True
    job = store.rows["jobs", "a"]
    assert job["state"] == "quarantined" and job["attempt"] == 1
    assert job["worker_failure"] == {"stage": "fetch_decode", "reason": "vad_order"}
    assert not _quar(caplog)
    assert len(_worker_handoff(caplog)) == 1
    assert len(_scheduler_hold(caplog)) == 1


@pytest.mark.asyncio
async def test_pump_wiring_vad_bounds_lands_the_rechanneled_hold(monkeypatch, caplog):
    """Pump -> scheduler: the vad_bounds ValidationFailureWork books the disposition hold end to end."""
    monkeypatch.setenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", "true")
    monkeypatch.setenv("BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED", "true")
    monkeypatch.setenv("BATCH_PIPELINE_DIARIZE_SPEECH_ONLY_ENABLED", "false")
    monkeypatch.setenv("BATCH_PIPELINE_SHORT_SPEECH_SINGLE_ENABLED", "false")
    caplog.set_level(logging.INFO)

    def decode(work):
        raise BatchValidationError(ValidationReason.VAD_BOUNDS)

    worker, *_ = setup_worker(decode=decode)
    results = worker.process_batch([worker_item()])
    assert isinstance(results[0], ValidationFailureWork)
    store, queue, lease = _queued()
    assert await Pump(queue, worker)._publish(lease, {"a": results[0]}, set()) is True
    job = store.rows["jobs", "a"]
    assert job["state"] == "quarantined" and job["attempt"] == 1
    assert job["worker_failure"] == {"stage": "fetch_decode", "reason": "vad_bounds"}
    assert not _quar(caplog)
    assert len(_worker_handoff(caplog)) == 1
    assert len(_scheduler_hold(caplog)) == 1


def test_durable_parity_vad_bounds_state_attempt_evidence_and_warning(monkeypatch, caplog):
    """vad_bounds: durable state, attempt, evidence booking and the warning are unchanged."""
    caplog.set_level(logging.INFO)
    metrics = Mock()
    store, queue, lease = _queued(metrics=metrics)
    shape = {"stage": "fetch_decode" if "vad_bounds" in TRIO else "vad_windows", "reason": "vad_bounds"}
    assert _fail(queue, lease, worker_failure=shape) is True
    job = store.rows["jobs", "a"]
    assert job["state"] == "quarantined" and job["attempt"] == 1
    assert job["recovery_state"] == "held" and not job["merge_pending"]
    assert job["worker_failure"] == shape
    recorded = [call.args[0] for call in metrics.record.call_args_list]
    assert "quarantined" in recorded and "recovery_held" in recorded
    warning = [r for r in caplog.records if "awaiting_fenced_recovery" in r.getMessage()]
    assert len(warning) == 1


def test_durable_parity_staged_audio_invalid_state_attempt_evidence_and_warning(monkeypatch, caplog):
    """staged_audio_invalid: durable state, attempt, evidence booking and the warning are unchanged."""
    caplog.set_level(logging.INFO)
    metrics = Mock()
    store, queue, lease = _queued(metrics=metrics)
    shape = {
        "stage": "fetch_decode" if "staged_audio_invalid" in TRIO else "vad_windows",
        "reason": "staged_audio_invalid",
    }
    assert _fail(queue, lease, worker_failure=shape) is True
    job = store.rows["jobs", "a"]
    assert job["state"] == "quarantined" and job["attempt"] == 1
    assert job["recovery_state"] == "held" and not job["merge_pending"]
    assert job["worker_failure"] == shape
    recorded = [call.args[0] for call in metrics.record.call_args_list]
    assert "quarantined" in recorded and "recovery_held" in recorded
    warning = [r for r in caplog.records if "awaiting_fenced_recovery" in r.getMessage()]
    assert len(warning) == 1


def test_demoted_hold_is_not_retry_due():
    """A disposition hold is as terminal to the ladder as a fault hold."""
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure={"stage": "vad_windows", "reason": "vad_bounds"}) is True
    job = store.rows["jobs", "a"]
    assert job["state"] == "quarantined"
    assert store.due("retry", time.time() + 10_000.0, 10) == []


def test_demoted_hold_keeps_the_lease_fenced_state():
    """The hold still books under the owning lease token only."""
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure={"stage": "vad_windows", "reason": "vad_bounds"}) is True
    assert store.rows["jobs", "a"]["state"] == "quarantined"


def test_severity_exclusivity_on_the_demoted_path():
    """The demoted quarantine path emits no ERROR record from the scheduler."""
    import logging as _logging

    handler_records = []
    logger = _logging.getLogger("utils.batch_pipeline.scheduler")
    handler = _logging.Handler()
    handler.emit = lambda record: handler_records.append(record)
    old_level = logger.level
    logger.addHandler(handler)
    logger.setLevel(_logging.INFO)
    try:
        store, queue, lease = _queued()
        _fail(queue, lease, worker_failure={"stage": "vad_windows", "reason": "vad_order"})
    finally:
        logger.removeHandler(handler)
        logger.setLevel(old_level)
    errors = [r for r in handler_records if r.levelno >= _logging.ERROR]
    assert not errors
    infos = [r for r in handler_records if "event=batch_validation_disposition" in r.getMessage()]
    assert len(infos) == 1


def test_severity_exclusivity_on_the_fault_path(caplog):
    """The kept-fault path emits no disposition INFO."""
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure={"stage": "fetch_decode", "reason": "outside_admitted_source"}) is True
    assert not _disposition(caplog) and len(_quar(caplog)) == 1


def test_one_terminal_line_per_fail_on_the_demoted_path(caplog):
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure={"stage": "vad_windows", "reason": "vad_bounds"}) is True
    terminal = _disposition(caplog) + _quar(caplog)
    assert len(terminal) == 1


def test_evidence_only_family_failure_defers_without_a_terminal_line(caplog):
    """Evidence-only calls never decide a transition: no demotion, no quarantine line."""
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure_evidence={"stage": "vad_windows", "reason": "vad_bounds"}) is True
    job = store.rows["jobs", "a"]
    assert job["state"] == "retry"
    assert not _disposition(caplog) and not _quar(caplog)
