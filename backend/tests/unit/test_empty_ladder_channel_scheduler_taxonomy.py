# Failure-Class: FC-empty-ladder-recovery-handoff-misclassified-as-worker-fault
"""The scheduler terminal hold rechannels the empty ladder, cell-by-cell, live.

Every (stage, reason) diagnosis the store validators admit is driven through a
real ``Scheduler.fail`` over ``MemoryStore`` with the INFO capture level set:
only the assemble_words empty family reports
``event=batch_empty_ladder outcome=held_for_recovery``; the guard keeps its
``held_for_redrive`` line; every kept fault keeps the ERROR
``batch_quarantined`` line. Evidence-only calls defer with no terminal line at
all, the preserved-diagnosis naming keeps its precedence, and metrics,
correctness meters, evidence booking and lease fences are pinned unchanged
next to the new classification.
"""

import logging
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

import utils.batch_pipeline.scheduler as scheduler_module
from tests.unit.test_batch_pipeline_scheduler import MemoryStore, item as sched_item
from utils.batch_pipeline.contracts import Priority
from utils.batch_pipeline.scheduler import Scheduler

FAMILY_STAGE = "assemble_words"
FAMILY = ("empty_asr", "no_owned_words")
GUARD = "unsupported_language"
STAGES = ('fetch_decode', 'vad_windows', 'word_clocks', 'assemble_words', 'asr_recovery')
# Reasons that keep the terminal quarantine ERROR under the disposition
# switch: the deliberately-retryable admitted-source refusal and the
# anonymous fault bucket. The vad/word verdicts and the fetch_decode trio
# report ``event=batch_validation_disposition`` instead (cells below).
KEPT = (
    'outside_admitted_source',
    'unknown',
)


def _queued(key="a", owner="empty-owner", duration=30, metrics=None):
    store = MemoryStore()
    queue = Scheduler(store, metrics=metrics)
    work = sched_item(key, owner=owner, duration=duration, priority=Priority.FRESH)
    assert queue.enqueue(work, 100.0)
    lease = queue.pull(1000.0)[0]
    return store, queue, lease


def _fail(queue, lease, **kwargs):
    return queue.fail(lease.item.segment_id, lease.token, 1100.0, **kwargs)


def _split(caplog):
    guard = [r for r in caplog.records if "event=batch_language_guard" in r.getMessage()]
    quar = [r for r in caplog.records if "event=batch_quarantined" in r.getMessage()]
    ladder = [r for r in caplog.records if "event=batch_empty_ladder" in r.getMessage()]
    warn = [r for r in caplog.records if "awaiting_fenced_recovery" in r.getMessage()]
    return guard, quar, ladder, warn


def test_disposition_fetch_decode_staged_audio_invalid_reports_held_for_disposition(caplog):
    """staged_audio_invalid at fetch_decode reports the terminal disposition hold at INFO."""
    caplog.set_level(logging.INFO)
    shape = {"stage": "fetch_decode", "reason": "staged_audio_invalid"}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure=shape) is True
    guard, quar, ladder, warn = _split(caplog)
    disposition = [r for r in caplog.records if "event=batch_validation_disposition" in r.getMessage()]
    assert not guard and not ladder and not quar and len(disposition) == 1
    assert disposition[0].levelno == logging.INFO
    message = disposition[0].getMessage()
    assert "outcome=held_for_disposition" in message
    assert "recovery=held" in message
    assert "stage=fetch_decode" in message and "worker_reason=staged_audio_invalid" in message
    assert len(warn) == 1
    job = store.probe("jobs", "a")
    assert job["state"] == "quarantined" and job["worker_failure"] == shape


def test_disposition_fetch_decode_retained_audio_invalid_reports_held_for_disposition(caplog):
    """retained_audio_invalid at fetch_decode reports the terminal disposition hold at INFO."""
    caplog.set_level(logging.INFO)
    shape = {"stage": "fetch_decode", "reason": "retained_audio_invalid"}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure=shape) is True
    guard, quar, ladder, warn = _split(caplog)
    disposition = [r for r in caplog.records if "event=batch_validation_disposition" in r.getMessage()]
    assert not guard and not ladder and not quar and len(disposition) == 1
    assert disposition[0].levelno == logging.INFO
    message = disposition[0].getMessage()
    assert "outcome=held_for_disposition" in message
    assert "recovery=held" in message
    assert "stage=fetch_decode" in message and "worker_reason=retained_audio_invalid" in message
    assert len(warn) == 1
    job = store.probe("jobs", "a")
    assert job["state"] == "quarantined" and job["worker_failure"] == shape


def test_disposition_fetch_decode_decoded_duration_mismatch_reports_held_for_disposition(caplog):
    """decoded_duration_mismatch at fetch_decode reports the terminal disposition hold at INFO."""
    caplog.set_level(logging.INFO)
    shape = {"stage": "fetch_decode", "reason": "decoded_duration_mismatch"}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure=shape) is True
    guard, quar, ladder, warn = _split(caplog)
    disposition = [r for r in caplog.records if "event=batch_validation_disposition" in r.getMessage()]
    assert not guard and not ladder and not quar and len(disposition) == 1
    assert disposition[0].levelno == logging.INFO
    message = disposition[0].getMessage()
    assert "outcome=held_for_disposition" in message
    assert "recovery=held" in message
    assert "stage=fetch_decode" in message and "worker_reason=decoded_duration_mismatch" in message
    assert len(warn) == 1
    job = store.probe("jobs", "a")
    assert job["state"] == "quarantined" and job["worker_failure"] == shape


def test_disposition_fetch_decode_word_shape_reports_held_for_disposition(caplog):
    """word_shape at fetch_decode reports the terminal disposition hold at INFO."""
    caplog.set_level(logging.INFO)
    shape = {"stage": "fetch_decode", "reason": "word_shape"}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure=shape) is True
    guard, quar, ladder, warn = _split(caplog)
    disposition = [r for r in caplog.records if "event=batch_validation_disposition" in r.getMessage()]
    assert not guard and not ladder and not quar and len(disposition) == 1
    assert disposition[0].levelno == logging.INFO
    message = disposition[0].getMessage()
    assert "outcome=held_for_disposition" in message
    assert "recovery=held" in message
    assert "stage=fetch_decode" in message and "worker_reason=word_shape" in message
    assert len(warn) == 1
    job = store.probe("jobs", "a")
    assert job["state"] == "quarantined" and job["worker_failure"] == shape


def test_disposition_fetch_decode_word_clock_reports_held_for_disposition(caplog):
    """word_clock at fetch_decode reports the terminal disposition hold at INFO."""
    caplog.set_level(logging.INFO)
    shape = {"stage": "fetch_decode", "reason": "word_clock"}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure=shape) is True
    guard, quar, ladder, warn = _split(caplog)
    disposition = [r for r in caplog.records if "event=batch_validation_disposition" in r.getMessage()]
    assert not guard and not ladder and not quar and len(disposition) == 1
    assert disposition[0].levelno == logging.INFO
    message = disposition[0].getMessage()
    assert "outcome=held_for_disposition" in message
    assert "recovery=held" in message
    assert "stage=fetch_decode" in message and "worker_reason=word_clock" in message
    assert len(warn) == 1
    job = store.probe("jobs", "a")
    assert job["state"] == "quarantined" and job["worker_failure"] == shape


def test_disposition_fetch_decode_word_sequence_reports_held_for_disposition(caplog):
    """word_sequence at fetch_decode reports the terminal disposition hold at INFO."""
    caplog.set_level(logging.INFO)
    shape = {"stage": "fetch_decode", "reason": "word_sequence"}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure=shape) is True
    guard, quar, ladder, warn = _split(caplog)
    disposition = [r for r in caplog.records if "event=batch_validation_disposition" in r.getMessage()]
    assert not guard and not ladder and not quar and len(disposition) == 1
    assert disposition[0].levelno == logging.INFO
    message = disposition[0].getMessage()
    assert "outcome=held_for_disposition" in message
    assert "recovery=held" in message
    assert "stage=fetch_decode" in message and "worker_reason=word_sequence" in message
    assert len(warn) == 1
    job = store.probe("jobs", "a")
    assert job["state"] == "quarantined" and job["worker_failure"] == shape


def test_disposition_fetch_decode_vad_nonfinite_reports_held_for_disposition(caplog):
    """vad_nonfinite at fetch_decode reports the terminal disposition hold at INFO."""
    caplog.set_level(logging.INFO)
    shape = {"stage": "fetch_decode", "reason": "vad_nonfinite"}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure=shape) is True
    guard, quar, ladder, warn = _split(caplog)
    disposition = [r for r in caplog.records if "event=batch_validation_disposition" in r.getMessage()]
    assert not guard and not ladder and not quar and len(disposition) == 1
    assert disposition[0].levelno == logging.INFO
    message = disposition[0].getMessage()
    assert "outcome=held_for_disposition" in message
    assert "recovery=held" in message
    assert "stage=fetch_decode" in message and "worker_reason=vad_nonfinite" in message
    assert len(warn) == 1
    job = store.probe("jobs", "a")
    assert job["state"] == "quarantined" and job["worker_failure"] == shape


def test_disposition_fetch_decode_vad_order_reports_held_for_disposition(caplog):
    """vad_order at fetch_decode reports the terminal disposition hold at INFO."""
    caplog.set_level(logging.INFO)
    shape = {"stage": "fetch_decode", "reason": "vad_order"}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure=shape) is True
    guard, quar, ladder, warn = _split(caplog)
    disposition = [r for r in caplog.records if "event=batch_validation_disposition" in r.getMessage()]
    assert not guard and not ladder and not quar and len(disposition) == 1
    assert disposition[0].levelno == logging.INFO
    message = disposition[0].getMessage()
    assert "outcome=held_for_disposition" in message
    assert "recovery=held" in message
    assert "stage=fetch_decode" in message and "worker_reason=vad_order" in message
    assert len(warn) == 1
    job = store.probe("jobs", "a")
    assert job["state"] == "quarantined" and job["worker_failure"] == shape


def test_disposition_fetch_decode_vad_bounds_reports_held_for_disposition(caplog):
    """vad_bounds at fetch_decode reports the terminal disposition hold at INFO."""
    caplog.set_level(logging.INFO)
    shape = {"stage": "fetch_decode", "reason": "vad_bounds"}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure=shape) is True
    guard, quar, ladder, warn = _split(caplog)
    disposition = [r for r in caplog.records if "event=batch_validation_disposition" in r.getMessage()]
    assert not guard and not ladder and not quar and len(disposition) == 1
    assert disposition[0].levelno == logging.INFO
    message = disposition[0].getMessage()
    assert "outcome=held_for_disposition" in message
    assert "recovery=held" in message
    assert "stage=fetch_decode" in message and "worker_reason=vad_bounds" in message
    assert len(warn) == 1
    job = store.probe("jobs", "a")
    assert job["state"] == "quarantined" and job["worker_failure"] == shape


def test_kept_fetch_decode_outside_admitted_source_keeps_quarantine_error(caplog):
    """outside_admitted_source at fetch_decode keeps the terminal quarantine ERROR."""
    caplog.set_level(logging.INFO)
    shape = {"stage": "fetch_decode", "reason": "outside_admitted_source"}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure=shape) is True
    guard, quar, ladder, warn = _split(caplog)
    assert not guard and not ladder and len(quar) == 1
    assert quar[0].levelno == logging.ERROR
    message = quar[0].getMessage()
    assert "reason=worker_failed" in message
    assert "stage=fetch_decode" in message and "worker_reason=outside_admitted_source" in message
    assert len(warn) == 1
    job = store.probe("jobs", "a")
    assert job["state"] == "quarantined" and job["worker_failure"] == shape


def test_kept_vad_windows_staged_audio_invalid_keeps_quarantine_error(caplog):
    """staged_audio_invalid at vad_windows keeps the terminal quarantine ERROR."""
    caplog.set_level(logging.INFO)
    shape = {"stage": "vad_windows", "reason": "staged_audio_invalid"}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure=shape) is True
    guard, quar, ladder, warn = _split(caplog)
    assert not guard and not ladder and len(quar) == 1
    assert quar[0].levelno == logging.ERROR
    message = quar[0].getMessage()
    assert "reason=worker_failed" in message
    assert "stage=vad_windows" in message and "worker_reason=staged_audio_invalid" in message
    assert len(warn) == 1
    job = store.probe("jobs", "a")
    assert job["state"] == "quarantined" and job["worker_failure"] == shape


def test_kept_vad_windows_retained_audio_invalid_keeps_quarantine_error(caplog):
    """retained_audio_invalid at vad_windows keeps the terminal quarantine ERROR."""
    caplog.set_level(logging.INFO)
    shape = {"stage": "vad_windows", "reason": "retained_audio_invalid"}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure=shape) is True
    guard, quar, ladder, warn = _split(caplog)
    assert not guard and not ladder and len(quar) == 1
    assert quar[0].levelno == logging.ERROR
    message = quar[0].getMessage()
    assert "reason=worker_failed" in message
    assert "stage=vad_windows" in message and "worker_reason=retained_audio_invalid" in message
    assert len(warn) == 1
    job = store.probe("jobs", "a")
    assert job["state"] == "quarantined" and job["worker_failure"] == shape


def test_kept_vad_windows_decoded_duration_mismatch_keeps_quarantine_error(caplog):
    """decoded_duration_mismatch at vad_windows keeps the terminal quarantine ERROR."""
    caplog.set_level(logging.INFO)
    shape = {"stage": "vad_windows", "reason": "decoded_duration_mismatch"}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure=shape) is True
    guard, quar, ladder, warn = _split(caplog)
    assert not guard and not ladder and len(quar) == 1
    assert quar[0].levelno == logging.ERROR
    message = quar[0].getMessage()
    assert "reason=worker_failed" in message
    assert "stage=vad_windows" in message and "worker_reason=decoded_duration_mismatch" in message
    assert len(warn) == 1
    job = store.probe("jobs", "a")
    assert job["state"] == "quarantined" and job["worker_failure"] == shape


def test_disposition_vad_windows_word_shape_reports_held_for_disposition(caplog):
    """word_shape at vad_windows reports the terminal disposition hold at INFO."""
    caplog.set_level(logging.INFO)
    shape = {"stage": "vad_windows", "reason": "word_shape"}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure=shape) is True
    guard, quar, ladder, warn = _split(caplog)
    disposition = [r for r in caplog.records if "event=batch_validation_disposition" in r.getMessage()]
    assert not guard and not ladder and not quar and len(disposition) == 1
    assert disposition[0].levelno == logging.INFO
    message = disposition[0].getMessage()
    assert "outcome=held_for_disposition" in message
    assert "recovery=held" in message
    assert "stage=vad_windows" in message and "worker_reason=word_shape" in message
    assert len(warn) == 1
    job = store.probe("jobs", "a")
    assert job["state"] == "quarantined" and job["worker_failure"] == shape


def test_disposition_vad_windows_word_clock_reports_held_for_disposition(caplog):
    """word_clock at vad_windows reports the terminal disposition hold at INFO."""
    caplog.set_level(logging.INFO)
    shape = {"stage": "vad_windows", "reason": "word_clock"}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure=shape) is True
    guard, quar, ladder, warn = _split(caplog)
    disposition = [r for r in caplog.records if "event=batch_validation_disposition" in r.getMessage()]
    assert not guard and not ladder and not quar and len(disposition) == 1
    assert disposition[0].levelno == logging.INFO
    message = disposition[0].getMessage()
    assert "outcome=held_for_disposition" in message
    assert "recovery=held" in message
    assert "stage=vad_windows" in message and "worker_reason=word_clock" in message
    assert len(warn) == 1
    job = store.probe("jobs", "a")
    assert job["state"] == "quarantined" and job["worker_failure"] == shape


def test_disposition_vad_windows_word_sequence_reports_held_for_disposition(caplog):
    """word_sequence at vad_windows reports the terminal disposition hold at INFO."""
    caplog.set_level(logging.INFO)
    shape = {"stage": "vad_windows", "reason": "word_sequence"}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure=shape) is True
    guard, quar, ladder, warn = _split(caplog)
    disposition = [r for r in caplog.records if "event=batch_validation_disposition" in r.getMessage()]
    assert not guard and not ladder and not quar and len(disposition) == 1
    assert disposition[0].levelno == logging.INFO
    message = disposition[0].getMessage()
    assert "outcome=held_for_disposition" in message
    assert "recovery=held" in message
    assert "stage=vad_windows" in message and "worker_reason=word_sequence" in message
    assert len(warn) == 1
    job = store.probe("jobs", "a")
    assert job["state"] == "quarantined" and job["worker_failure"] == shape


def test_disposition_vad_windows_vad_nonfinite_reports_held_for_disposition(caplog):
    """vad_nonfinite at vad_windows reports the terminal disposition hold at INFO."""
    caplog.set_level(logging.INFO)
    shape = {"stage": "vad_windows", "reason": "vad_nonfinite"}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure=shape) is True
    guard, quar, ladder, warn = _split(caplog)
    disposition = [r for r in caplog.records if "event=batch_validation_disposition" in r.getMessage()]
    assert not guard and not ladder and not quar and len(disposition) == 1
    assert disposition[0].levelno == logging.INFO
    message = disposition[0].getMessage()
    assert "outcome=held_for_disposition" in message
    assert "recovery=held" in message
    assert "stage=vad_windows" in message and "worker_reason=vad_nonfinite" in message
    assert len(warn) == 1
    job = store.probe("jobs", "a")
    assert job["state"] == "quarantined" and job["worker_failure"] == shape


def test_disposition_vad_windows_vad_order_reports_held_for_disposition(caplog):
    """vad_order at vad_windows reports the terminal disposition hold at INFO."""
    caplog.set_level(logging.INFO)
    shape = {"stage": "vad_windows", "reason": "vad_order"}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure=shape) is True
    guard, quar, ladder, warn = _split(caplog)
    disposition = [r for r in caplog.records if "event=batch_validation_disposition" in r.getMessage()]
    assert not guard and not ladder and not quar and len(disposition) == 1
    assert disposition[0].levelno == logging.INFO
    message = disposition[0].getMessage()
    assert "outcome=held_for_disposition" in message
    assert "recovery=held" in message
    assert "stage=vad_windows" in message and "worker_reason=vad_order" in message
    assert len(warn) == 1
    job = store.probe("jobs", "a")
    assert job["state"] == "quarantined" and job["worker_failure"] == shape


def test_disposition_vad_windows_vad_bounds_reports_held_for_disposition(caplog):
    """vad_bounds at vad_windows reports the terminal disposition hold at INFO."""
    caplog.set_level(logging.INFO)
    shape = {"stage": "vad_windows", "reason": "vad_bounds"}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure=shape) is True
    guard, quar, ladder, warn = _split(caplog)
    disposition = [r for r in caplog.records if "event=batch_validation_disposition" in r.getMessage()]
    assert not guard and not ladder and not quar and len(disposition) == 1
    assert disposition[0].levelno == logging.INFO
    message = disposition[0].getMessage()
    assert "outcome=held_for_disposition" in message
    assert "recovery=held" in message
    assert "stage=vad_windows" in message and "worker_reason=vad_bounds" in message
    assert len(warn) == 1
    job = store.probe("jobs", "a")
    assert job["state"] == "quarantined" and job["worker_failure"] == shape


def test_kept_vad_windows_outside_admitted_source_keeps_quarantine_error(caplog):
    """outside_admitted_source at vad_windows keeps the terminal quarantine ERROR."""
    caplog.set_level(logging.INFO)
    shape = {"stage": "vad_windows", "reason": "outside_admitted_source"}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure=shape) is True
    guard, quar, ladder, warn = _split(caplog)
    assert not guard and not ladder and len(quar) == 1
    assert quar[0].levelno == logging.ERROR
    message = quar[0].getMessage()
    assert "reason=worker_failed" in message
    assert "stage=vad_windows" in message and "worker_reason=outside_admitted_source" in message
    assert len(warn) == 1
    job = store.probe("jobs", "a")
    assert job["state"] == "quarantined" and job["worker_failure"] == shape


def test_kept_word_clocks_staged_audio_invalid_keeps_quarantine_error(caplog):
    """staged_audio_invalid at word_clocks keeps the terminal quarantine ERROR."""
    caplog.set_level(logging.INFO)
    shape = {"stage": "word_clocks", "reason": "staged_audio_invalid"}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure=shape) is True
    guard, quar, ladder, warn = _split(caplog)
    assert not guard and not ladder and len(quar) == 1
    assert quar[0].levelno == logging.ERROR
    message = quar[0].getMessage()
    assert "reason=worker_failed" in message
    assert "stage=word_clocks" in message and "worker_reason=staged_audio_invalid" in message
    assert len(warn) == 1
    job = store.probe("jobs", "a")
    assert job["state"] == "quarantined" and job["worker_failure"] == shape


def test_kept_word_clocks_retained_audio_invalid_keeps_quarantine_error(caplog):
    """retained_audio_invalid at word_clocks keeps the terminal quarantine ERROR."""
    caplog.set_level(logging.INFO)
    shape = {"stage": "word_clocks", "reason": "retained_audio_invalid"}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure=shape) is True
    guard, quar, ladder, warn = _split(caplog)
    assert not guard and not ladder and len(quar) == 1
    assert quar[0].levelno == logging.ERROR
    message = quar[0].getMessage()
    assert "reason=worker_failed" in message
    assert "stage=word_clocks" in message and "worker_reason=retained_audio_invalid" in message
    assert len(warn) == 1
    job = store.probe("jobs", "a")
    assert job["state"] == "quarantined" and job["worker_failure"] == shape


def test_kept_word_clocks_decoded_duration_mismatch_keeps_quarantine_error(caplog):
    """decoded_duration_mismatch at word_clocks keeps the terminal quarantine ERROR."""
    caplog.set_level(logging.INFO)
    shape = {"stage": "word_clocks", "reason": "decoded_duration_mismatch"}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure=shape) is True
    guard, quar, ladder, warn = _split(caplog)
    assert not guard and not ladder and len(quar) == 1
    assert quar[0].levelno == logging.ERROR
    message = quar[0].getMessage()
    assert "reason=worker_failed" in message
    assert "stage=word_clocks" in message and "worker_reason=decoded_duration_mismatch" in message
    assert len(warn) == 1
    job = store.probe("jobs", "a")
    assert job["state"] == "quarantined" and job["worker_failure"] == shape


def test_disposition_word_clocks_word_shape_reports_held_for_disposition(caplog):
    """word_shape at word_clocks reports the terminal disposition hold at INFO."""
    caplog.set_level(logging.INFO)
    shape = {"stage": "word_clocks", "reason": "word_shape"}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure=shape) is True
    guard, quar, ladder, warn = _split(caplog)
    disposition = [r for r in caplog.records if "event=batch_validation_disposition" in r.getMessage()]
    assert not guard and not ladder and not quar and len(disposition) == 1
    assert disposition[0].levelno == logging.INFO
    message = disposition[0].getMessage()
    assert "outcome=held_for_disposition" in message
    assert "recovery=held" in message
    assert "stage=word_clocks" in message and "worker_reason=word_shape" in message
    assert len(warn) == 1
    job = store.probe("jobs", "a")
    assert job["state"] == "quarantined" and job["worker_failure"] == shape


def test_disposition_word_clocks_word_clock_reports_held_for_disposition(caplog):
    """word_clock at word_clocks reports the terminal disposition hold at INFO."""
    caplog.set_level(logging.INFO)
    shape = {"stage": "word_clocks", "reason": "word_clock"}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure=shape) is True
    guard, quar, ladder, warn = _split(caplog)
    disposition = [r for r in caplog.records if "event=batch_validation_disposition" in r.getMessage()]
    assert not guard and not ladder and not quar and len(disposition) == 1
    assert disposition[0].levelno == logging.INFO
    message = disposition[0].getMessage()
    assert "outcome=held_for_disposition" in message
    assert "recovery=held" in message
    assert "stage=word_clocks" in message and "worker_reason=word_clock" in message
    assert len(warn) == 1
    job = store.probe("jobs", "a")
    assert job["state"] == "quarantined" and job["worker_failure"] == shape


def test_disposition_word_clocks_word_sequence_reports_held_for_disposition(caplog):
    """word_sequence at word_clocks reports the terminal disposition hold at INFO."""
    caplog.set_level(logging.INFO)
    shape = {"stage": "word_clocks", "reason": "word_sequence"}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure=shape) is True
    guard, quar, ladder, warn = _split(caplog)
    disposition = [r for r in caplog.records if "event=batch_validation_disposition" in r.getMessage()]
    assert not guard and not ladder and not quar and len(disposition) == 1
    assert disposition[0].levelno == logging.INFO
    message = disposition[0].getMessage()
    assert "outcome=held_for_disposition" in message
    assert "recovery=held" in message
    assert "stage=word_clocks" in message and "worker_reason=word_sequence" in message
    assert len(warn) == 1
    job = store.probe("jobs", "a")
    assert job["state"] == "quarantined" and job["worker_failure"] == shape


def test_disposition_word_clocks_vad_nonfinite_reports_held_for_disposition(caplog):
    """vad_nonfinite at word_clocks reports the terminal disposition hold at INFO."""
    caplog.set_level(logging.INFO)
    shape = {"stage": "word_clocks", "reason": "vad_nonfinite"}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure=shape) is True
    guard, quar, ladder, warn = _split(caplog)
    disposition = [r for r in caplog.records if "event=batch_validation_disposition" in r.getMessage()]
    assert not guard and not ladder and not quar and len(disposition) == 1
    assert disposition[0].levelno == logging.INFO
    message = disposition[0].getMessage()
    assert "outcome=held_for_disposition" in message
    assert "recovery=held" in message
    assert "stage=word_clocks" in message and "worker_reason=vad_nonfinite" in message
    assert len(warn) == 1
    job = store.probe("jobs", "a")
    assert job["state"] == "quarantined" and job["worker_failure"] == shape


def test_disposition_word_clocks_vad_order_reports_held_for_disposition(caplog):
    """vad_order at word_clocks reports the terminal disposition hold at INFO."""
    caplog.set_level(logging.INFO)
    shape = {"stage": "word_clocks", "reason": "vad_order"}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure=shape) is True
    guard, quar, ladder, warn = _split(caplog)
    disposition = [r for r in caplog.records if "event=batch_validation_disposition" in r.getMessage()]
    assert not guard and not ladder and not quar and len(disposition) == 1
    assert disposition[0].levelno == logging.INFO
    message = disposition[0].getMessage()
    assert "outcome=held_for_disposition" in message
    assert "recovery=held" in message
    assert "stage=word_clocks" in message and "worker_reason=vad_order" in message
    assert len(warn) == 1
    job = store.probe("jobs", "a")
    assert job["state"] == "quarantined" and job["worker_failure"] == shape


def test_disposition_word_clocks_vad_bounds_reports_held_for_disposition(caplog):
    """vad_bounds at word_clocks reports the terminal disposition hold at INFO."""
    caplog.set_level(logging.INFO)
    shape = {"stage": "word_clocks", "reason": "vad_bounds"}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure=shape) is True
    guard, quar, ladder, warn = _split(caplog)
    disposition = [r for r in caplog.records if "event=batch_validation_disposition" in r.getMessage()]
    assert not guard and not ladder and not quar and len(disposition) == 1
    assert disposition[0].levelno == logging.INFO
    message = disposition[0].getMessage()
    assert "outcome=held_for_disposition" in message
    assert "recovery=held" in message
    assert "stage=word_clocks" in message and "worker_reason=vad_bounds" in message
    assert len(warn) == 1
    job = store.probe("jobs", "a")
    assert job["state"] == "quarantined" and job["worker_failure"] == shape


def test_kept_word_clocks_outside_admitted_source_keeps_quarantine_error(caplog):
    """outside_admitted_source at word_clocks keeps the terminal quarantine ERROR."""
    caplog.set_level(logging.INFO)
    shape = {"stage": "word_clocks", "reason": "outside_admitted_source"}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure=shape) is True
    guard, quar, ladder, warn = _split(caplog)
    assert not guard and not ladder and len(quar) == 1
    assert quar[0].levelno == logging.ERROR
    message = quar[0].getMessage()
    assert "reason=worker_failed" in message
    assert "stage=word_clocks" in message and "worker_reason=outside_admitted_source" in message
    assert len(warn) == 1
    job = store.probe("jobs", "a")
    assert job["state"] == "quarantined" and job["worker_failure"] == shape


def test_kept_assemble_words_staged_audio_invalid_keeps_quarantine_error(caplog):
    """staged_audio_invalid at assemble_words keeps the terminal quarantine ERROR."""
    caplog.set_level(logging.INFO)
    shape = {"stage": "assemble_words", "reason": "staged_audio_invalid"}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure=shape) is True
    guard, quar, ladder, warn = _split(caplog)
    assert not guard and not ladder and len(quar) == 1
    assert quar[0].levelno == logging.ERROR
    message = quar[0].getMessage()
    assert "reason=worker_failed" in message
    assert "stage=assemble_words" in message and "worker_reason=staged_audio_invalid" in message
    assert len(warn) == 1
    job = store.probe("jobs", "a")
    assert job["state"] == "quarantined" and job["worker_failure"] == shape


def test_kept_assemble_words_retained_audio_invalid_keeps_quarantine_error(caplog):
    """retained_audio_invalid at assemble_words keeps the terminal quarantine ERROR."""
    caplog.set_level(logging.INFO)
    shape = {"stage": "assemble_words", "reason": "retained_audio_invalid"}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure=shape) is True
    guard, quar, ladder, warn = _split(caplog)
    assert not guard and not ladder and len(quar) == 1
    assert quar[0].levelno == logging.ERROR
    message = quar[0].getMessage()
    assert "reason=worker_failed" in message
    assert "stage=assemble_words" in message and "worker_reason=retained_audio_invalid" in message
    assert len(warn) == 1
    job = store.probe("jobs", "a")
    assert job["state"] == "quarantined" and job["worker_failure"] == shape


def test_kept_assemble_words_decoded_duration_mismatch_keeps_quarantine_error(caplog):
    """decoded_duration_mismatch at assemble_words keeps the terminal quarantine ERROR."""
    caplog.set_level(logging.INFO)
    shape = {"stage": "assemble_words", "reason": "decoded_duration_mismatch"}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure=shape) is True
    guard, quar, ladder, warn = _split(caplog)
    assert not guard and not ladder and len(quar) == 1
    assert quar[0].levelno == logging.ERROR
    message = quar[0].getMessage()
    assert "reason=worker_failed" in message
    assert "stage=assemble_words" in message and "worker_reason=decoded_duration_mismatch" in message
    assert len(warn) == 1
    job = store.probe("jobs", "a")
    assert job["state"] == "quarantined" and job["worker_failure"] == shape


def test_disposition_assemble_words_word_shape_reports_held_for_disposition(caplog):
    """word_shape at assemble_words reports the terminal disposition hold at INFO."""
    caplog.set_level(logging.INFO)
    shape = {"stage": "assemble_words", "reason": "word_shape"}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure=shape) is True
    guard, quar, ladder, warn = _split(caplog)
    disposition = [r for r in caplog.records if "event=batch_validation_disposition" in r.getMessage()]
    assert not guard and not ladder and not quar and len(disposition) == 1
    assert disposition[0].levelno == logging.INFO
    message = disposition[0].getMessage()
    assert "outcome=held_for_disposition" in message
    assert "recovery=held" in message
    assert "stage=assemble_words" in message and "worker_reason=word_shape" in message
    assert len(warn) == 1
    job = store.probe("jobs", "a")
    assert job["state"] == "quarantined" and job["worker_failure"] == shape


def test_disposition_assemble_words_word_clock_reports_held_for_disposition(caplog):
    """word_clock at assemble_words reports the terminal disposition hold at INFO."""
    caplog.set_level(logging.INFO)
    shape = {"stage": "assemble_words", "reason": "word_clock"}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure=shape) is True
    guard, quar, ladder, warn = _split(caplog)
    disposition = [r for r in caplog.records if "event=batch_validation_disposition" in r.getMessage()]
    assert not guard and not ladder and not quar and len(disposition) == 1
    assert disposition[0].levelno == logging.INFO
    message = disposition[0].getMessage()
    assert "outcome=held_for_disposition" in message
    assert "recovery=held" in message
    assert "stage=assemble_words" in message and "worker_reason=word_clock" in message
    assert len(warn) == 1
    job = store.probe("jobs", "a")
    assert job["state"] == "quarantined" and job["worker_failure"] == shape


def test_disposition_assemble_words_word_sequence_reports_held_for_disposition(caplog):
    """word_sequence at assemble_words reports the terminal disposition hold at INFO."""
    caplog.set_level(logging.INFO)
    shape = {"stage": "assemble_words", "reason": "word_sequence"}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure=shape) is True
    guard, quar, ladder, warn = _split(caplog)
    disposition = [r for r in caplog.records if "event=batch_validation_disposition" in r.getMessage()]
    assert not guard and not ladder and not quar and len(disposition) == 1
    assert disposition[0].levelno == logging.INFO
    message = disposition[0].getMessage()
    assert "outcome=held_for_disposition" in message
    assert "recovery=held" in message
    assert "stage=assemble_words" in message and "worker_reason=word_sequence" in message
    assert len(warn) == 1
    job = store.probe("jobs", "a")
    assert job["state"] == "quarantined" and job["worker_failure"] == shape


def test_disposition_assemble_words_vad_nonfinite_reports_held_for_disposition(caplog):
    """vad_nonfinite at assemble_words reports the terminal disposition hold at INFO."""
    caplog.set_level(logging.INFO)
    shape = {"stage": "assemble_words", "reason": "vad_nonfinite"}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure=shape) is True
    guard, quar, ladder, warn = _split(caplog)
    disposition = [r for r in caplog.records if "event=batch_validation_disposition" in r.getMessage()]
    assert not guard and not ladder and not quar and len(disposition) == 1
    assert disposition[0].levelno == logging.INFO
    message = disposition[0].getMessage()
    assert "outcome=held_for_disposition" in message
    assert "recovery=held" in message
    assert "stage=assemble_words" in message and "worker_reason=vad_nonfinite" in message
    assert len(warn) == 1
    job = store.probe("jobs", "a")
    assert job["state"] == "quarantined" and job["worker_failure"] == shape


def test_disposition_assemble_words_vad_order_reports_held_for_disposition(caplog):
    """vad_order at assemble_words reports the terminal disposition hold at INFO."""
    caplog.set_level(logging.INFO)
    shape = {"stage": "assemble_words", "reason": "vad_order"}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure=shape) is True
    guard, quar, ladder, warn = _split(caplog)
    disposition = [r for r in caplog.records if "event=batch_validation_disposition" in r.getMessage()]
    assert not guard and not ladder and not quar and len(disposition) == 1
    assert disposition[0].levelno == logging.INFO
    message = disposition[0].getMessage()
    assert "outcome=held_for_disposition" in message
    assert "recovery=held" in message
    assert "stage=assemble_words" in message and "worker_reason=vad_order" in message
    assert len(warn) == 1
    job = store.probe("jobs", "a")
    assert job["state"] == "quarantined" and job["worker_failure"] == shape


def test_disposition_assemble_words_vad_bounds_reports_held_for_disposition(caplog):
    """vad_bounds at assemble_words reports the terminal disposition hold at INFO."""
    caplog.set_level(logging.INFO)
    shape = {"stage": "assemble_words", "reason": "vad_bounds"}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure=shape) is True
    guard, quar, ladder, warn = _split(caplog)
    disposition = [r for r in caplog.records if "event=batch_validation_disposition" in r.getMessage()]
    assert not guard and not ladder and not quar and len(disposition) == 1
    assert disposition[0].levelno == logging.INFO
    message = disposition[0].getMessage()
    assert "outcome=held_for_disposition" in message
    assert "recovery=held" in message
    assert "stage=assemble_words" in message and "worker_reason=vad_bounds" in message
    assert len(warn) == 1
    job = store.probe("jobs", "a")
    assert job["state"] == "quarantined" and job["worker_failure"] == shape


def test_kept_assemble_words_outside_admitted_source_keeps_quarantine_error(caplog):
    """outside_admitted_source at assemble_words keeps the terminal quarantine ERROR."""
    caplog.set_level(logging.INFO)
    shape = {"stage": "assemble_words", "reason": "outside_admitted_source"}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure=shape) is True
    guard, quar, ladder, warn = _split(caplog)
    assert not guard and not ladder and len(quar) == 1
    assert quar[0].levelno == logging.ERROR
    message = quar[0].getMessage()
    assert "reason=worker_failed" in message
    assert "stage=assemble_words" in message and "worker_reason=outside_admitted_source" in message
    assert len(warn) == 1
    job = store.probe("jobs", "a")
    assert job["state"] == "quarantined" and job["worker_failure"] == shape


def test_kept_asr_recovery_staged_audio_invalid_keeps_quarantine_error(caplog):
    """staged_audio_invalid at asr_recovery keeps the terminal quarantine ERROR."""
    caplog.set_level(logging.INFO)
    shape = {"stage": "asr_recovery", "reason": "staged_audio_invalid"}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure=shape) is True
    guard, quar, ladder, warn = _split(caplog)
    assert not guard and not ladder and len(quar) == 1
    assert quar[0].levelno == logging.ERROR
    message = quar[0].getMessage()
    assert "reason=worker_failed" in message
    assert "stage=asr_recovery" in message and "worker_reason=staged_audio_invalid" in message
    assert len(warn) == 1
    job = store.probe("jobs", "a")
    assert job["state"] == "quarantined" and job["worker_failure"] == shape


def test_kept_asr_recovery_retained_audio_invalid_keeps_quarantine_error(caplog):
    """retained_audio_invalid at asr_recovery keeps the terminal quarantine ERROR."""
    caplog.set_level(logging.INFO)
    shape = {"stage": "asr_recovery", "reason": "retained_audio_invalid"}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure=shape) is True
    guard, quar, ladder, warn = _split(caplog)
    assert not guard and not ladder and len(quar) == 1
    assert quar[0].levelno == logging.ERROR
    message = quar[0].getMessage()
    assert "reason=worker_failed" in message
    assert "stage=asr_recovery" in message and "worker_reason=retained_audio_invalid" in message
    assert len(warn) == 1
    job = store.probe("jobs", "a")
    assert job["state"] == "quarantined" and job["worker_failure"] == shape


def test_kept_asr_recovery_decoded_duration_mismatch_keeps_quarantine_error(caplog):
    """decoded_duration_mismatch at asr_recovery keeps the terminal quarantine ERROR."""
    caplog.set_level(logging.INFO)
    shape = {"stage": "asr_recovery", "reason": "decoded_duration_mismatch"}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure=shape) is True
    guard, quar, ladder, warn = _split(caplog)
    assert not guard and not ladder and len(quar) == 1
    assert quar[0].levelno == logging.ERROR
    message = quar[0].getMessage()
    assert "reason=worker_failed" in message
    assert "stage=asr_recovery" in message and "worker_reason=decoded_duration_mismatch" in message
    assert len(warn) == 1
    job = store.probe("jobs", "a")
    assert job["state"] == "quarantined" and job["worker_failure"] == shape


def test_disposition_asr_recovery_word_shape_reports_held_for_disposition(caplog):
    """word_shape at asr_recovery reports the terminal disposition hold at INFO."""
    caplog.set_level(logging.INFO)
    shape = {"stage": "asr_recovery", "reason": "word_shape"}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure=shape) is True
    guard, quar, ladder, warn = _split(caplog)
    disposition = [r for r in caplog.records if "event=batch_validation_disposition" in r.getMessage()]
    assert not guard and not ladder and not quar and len(disposition) == 1
    assert disposition[0].levelno == logging.INFO
    message = disposition[0].getMessage()
    assert "outcome=held_for_disposition" in message
    assert "recovery=held" in message
    assert "stage=asr_recovery" in message and "worker_reason=word_shape" in message
    assert len(warn) == 1
    job = store.probe("jobs", "a")
    assert job["state"] == "quarantined" and job["worker_failure"] == shape


def test_disposition_asr_recovery_word_clock_reports_held_for_disposition(caplog):
    """word_clock at asr_recovery reports the terminal disposition hold at INFO."""
    caplog.set_level(logging.INFO)
    shape = {"stage": "asr_recovery", "reason": "word_clock"}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure=shape) is True
    guard, quar, ladder, warn = _split(caplog)
    disposition = [r for r in caplog.records if "event=batch_validation_disposition" in r.getMessage()]
    assert not guard and not ladder and not quar and len(disposition) == 1
    assert disposition[0].levelno == logging.INFO
    message = disposition[0].getMessage()
    assert "outcome=held_for_disposition" in message
    assert "recovery=held" in message
    assert "stage=asr_recovery" in message and "worker_reason=word_clock" in message
    assert len(warn) == 1
    job = store.probe("jobs", "a")
    assert job["state"] == "quarantined" and job["worker_failure"] == shape


def test_disposition_asr_recovery_word_sequence_reports_held_for_disposition(caplog):
    """word_sequence at asr_recovery reports the terminal disposition hold at INFO."""
    caplog.set_level(logging.INFO)
    shape = {"stage": "asr_recovery", "reason": "word_sequence"}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure=shape) is True
    guard, quar, ladder, warn = _split(caplog)
    disposition = [r for r in caplog.records if "event=batch_validation_disposition" in r.getMessage()]
    assert not guard and not ladder and not quar and len(disposition) == 1
    assert disposition[0].levelno == logging.INFO
    message = disposition[0].getMessage()
    assert "outcome=held_for_disposition" in message
    assert "recovery=held" in message
    assert "stage=asr_recovery" in message and "worker_reason=word_sequence" in message
    assert len(warn) == 1
    job = store.probe("jobs", "a")
    assert job["state"] == "quarantined" and job["worker_failure"] == shape


def test_disposition_asr_recovery_vad_nonfinite_reports_held_for_disposition(caplog):
    """vad_nonfinite at asr_recovery reports the terminal disposition hold at INFO."""
    caplog.set_level(logging.INFO)
    shape = {"stage": "asr_recovery", "reason": "vad_nonfinite"}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure=shape) is True
    guard, quar, ladder, warn = _split(caplog)
    disposition = [r for r in caplog.records if "event=batch_validation_disposition" in r.getMessage()]
    assert not guard and not ladder and not quar and len(disposition) == 1
    assert disposition[0].levelno == logging.INFO
    message = disposition[0].getMessage()
    assert "outcome=held_for_disposition" in message
    assert "recovery=held" in message
    assert "stage=asr_recovery" in message and "worker_reason=vad_nonfinite" in message
    assert len(warn) == 1
    job = store.probe("jobs", "a")
    assert job["state"] == "quarantined" and job["worker_failure"] == shape


def test_disposition_asr_recovery_vad_order_reports_held_for_disposition(caplog):
    """vad_order at asr_recovery reports the terminal disposition hold at INFO."""
    caplog.set_level(logging.INFO)
    shape = {"stage": "asr_recovery", "reason": "vad_order"}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure=shape) is True
    guard, quar, ladder, warn = _split(caplog)
    disposition = [r for r in caplog.records if "event=batch_validation_disposition" in r.getMessage()]
    assert not guard and not ladder and not quar and len(disposition) == 1
    assert disposition[0].levelno == logging.INFO
    message = disposition[0].getMessage()
    assert "outcome=held_for_disposition" in message
    assert "recovery=held" in message
    assert "stage=asr_recovery" in message and "worker_reason=vad_order" in message
    assert len(warn) == 1
    job = store.probe("jobs", "a")
    assert job["state"] == "quarantined" and job["worker_failure"] == shape


def test_disposition_asr_recovery_vad_bounds_reports_held_for_disposition(caplog):
    """vad_bounds at asr_recovery reports the terminal disposition hold at INFO."""
    caplog.set_level(logging.INFO)
    shape = {"stage": "asr_recovery", "reason": "vad_bounds"}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure=shape) is True
    guard, quar, ladder, warn = _split(caplog)
    disposition = [r for r in caplog.records if "event=batch_validation_disposition" in r.getMessage()]
    assert not guard and not ladder and not quar and len(disposition) == 1
    assert disposition[0].levelno == logging.INFO
    message = disposition[0].getMessage()
    assert "outcome=held_for_disposition" in message
    assert "recovery=held" in message
    assert "stage=asr_recovery" in message and "worker_reason=vad_bounds" in message
    assert len(warn) == 1
    job = store.probe("jobs", "a")
    assert job["state"] == "quarantined" and job["worker_failure"] == shape


def test_kept_asr_recovery_outside_admitted_source_keeps_quarantine_error(caplog):
    """outside_admitted_source at asr_recovery keeps the terminal quarantine ERROR."""
    caplog.set_level(logging.INFO)
    shape = {"stage": "asr_recovery", "reason": "outside_admitted_source"}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure=shape) is True
    guard, quar, ladder, warn = _split(caplog)
    assert not guard and not ladder and len(quar) == 1
    assert quar[0].levelno == logging.ERROR
    message = quar[0].getMessage()
    assert "reason=worker_failed" in message
    assert "stage=asr_recovery" in message and "worker_reason=outside_admitted_source" in message
    assert len(warn) == 1
    job = store.probe("jobs", "a")
    assert job["state"] == "quarantined" and job["worker_failure"] == shape


def test_family_empty_asr_at_fetch_decode_synthetic_cell_keeps_quarantine_error(caplog):
    """A synthetic empty_asr diagnosis at fetch_decode keeps the fault channel."""
    caplog.set_level(logging.INFO)
    shape = {"stage": "fetch_decode", "reason": "empty_asr"}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure=shape) is True
    guard, quar, ladder, warn = _split(caplog)
    assert not guard and not ladder and len(quar) == 1
    assert quar[0].levelno == logging.ERROR
    message = quar[0].getMessage()
    assert "stage=fetch_decode" in message and "worker_reason=empty_asr" in message
    assert len(warn) == 1
    job = store.probe("jobs", "a")
    assert job["state"] == "quarantined" and job["worker_failure"] == shape


def test_family_no_owned_words_at_fetch_decode_synthetic_cell_keeps_quarantine_error(caplog):
    """A synthetic no_owned_words diagnosis at fetch_decode keeps the fault channel."""
    caplog.set_level(logging.INFO)
    shape = {"stage": "fetch_decode", "reason": "no_owned_words"}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure=shape) is True
    guard, quar, ladder, warn = _split(caplog)
    assert not guard and not ladder and len(quar) == 1
    assert quar[0].levelno == logging.ERROR
    message = quar[0].getMessage()
    assert "stage=fetch_decode" in message and "worker_reason=no_owned_words" in message
    assert len(warn) == 1
    job = store.probe("jobs", "a")
    assert job["state"] == "quarantined" and job["worker_failure"] == shape


def test_family_empty_asr_at_vad_windows_synthetic_cell_keeps_quarantine_error(caplog):
    """A synthetic empty_asr diagnosis at vad_windows keeps the fault channel."""
    caplog.set_level(logging.INFO)
    shape = {"stage": "vad_windows", "reason": "empty_asr"}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure=shape) is True
    guard, quar, ladder, warn = _split(caplog)
    assert not guard and not ladder and len(quar) == 1
    assert quar[0].levelno == logging.ERROR
    message = quar[0].getMessage()
    assert "stage=vad_windows" in message and "worker_reason=empty_asr" in message
    assert len(warn) == 1
    job = store.probe("jobs", "a")
    assert job["state"] == "quarantined" and job["worker_failure"] == shape


def test_family_no_owned_words_at_vad_windows_synthetic_cell_keeps_quarantine_error(caplog):
    """A synthetic no_owned_words diagnosis at vad_windows keeps the fault channel."""
    caplog.set_level(logging.INFO)
    shape = {"stage": "vad_windows", "reason": "no_owned_words"}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure=shape) is True
    guard, quar, ladder, warn = _split(caplog)
    assert not guard and not ladder and len(quar) == 1
    assert quar[0].levelno == logging.ERROR
    message = quar[0].getMessage()
    assert "stage=vad_windows" in message and "worker_reason=no_owned_words" in message
    assert len(warn) == 1
    job = store.probe("jobs", "a")
    assert job["state"] == "quarantined" and job["worker_failure"] == shape


def test_family_empty_asr_at_word_clocks_synthetic_cell_keeps_quarantine_error(caplog):
    """A synthetic empty_asr diagnosis at word_clocks keeps the fault channel."""
    caplog.set_level(logging.INFO)
    shape = {"stage": "word_clocks", "reason": "empty_asr"}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure=shape) is True
    guard, quar, ladder, warn = _split(caplog)
    assert not guard and not ladder and len(quar) == 1
    assert quar[0].levelno == logging.ERROR
    message = quar[0].getMessage()
    assert "stage=word_clocks" in message and "worker_reason=empty_asr" in message
    assert len(warn) == 1
    job = store.probe("jobs", "a")
    assert job["state"] == "quarantined" and job["worker_failure"] == shape


def test_family_no_owned_words_at_word_clocks_synthetic_cell_keeps_quarantine_error(caplog):
    """A synthetic no_owned_words diagnosis at word_clocks keeps the fault channel."""
    caplog.set_level(logging.INFO)
    shape = {"stage": "word_clocks", "reason": "no_owned_words"}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure=shape) is True
    guard, quar, ladder, warn = _split(caplog)
    assert not guard and not ladder and len(quar) == 1
    assert quar[0].levelno == logging.ERROR
    message = quar[0].getMessage()
    assert "stage=word_clocks" in message and "worker_reason=no_owned_words" in message
    assert len(warn) == 1
    job = store.probe("jobs", "a")
    assert job["state"] == "quarantined" and job["worker_failure"] == shape


def test_family_empty_asr_at_asr_recovery_synthetic_cell_keeps_quarantine_error(caplog):
    """A synthetic empty_asr diagnosis at asr_recovery keeps the fault channel."""
    caplog.set_level(logging.INFO)
    shape = {"stage": "asr_recovery", "reason": "empty_asr"}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure=shape) is True
    guard, quar, ladder, warn = _split(caplog)
    assert not guard and not ladder and len(quar) == 1
    assert quar[0].levelno == logging.ERROR
    message = quar[0].getMessage()
    assert "stage=asr_recovery" in message and "worker_reason=empty_asr" in message
    assert len(warn) == 1
    job = store.probe("jobs", "a")
    assert job["state"] == "quarantined" and job["worker_failure"] == shape


def test_family_no_owned_words_at_asr_recovery_synthetic_cell_keeps_quarantine_error(caplog):
    """A synthetic no_owned_words diagnosis at asr_recovery keeps the fault channel."""
    caplog.set_level(logging.INFO)
    shape = {"stage": "asr_recovery", "reason": "no_owned_words"}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure=shape) is True
    guard, quar, ladder, warn = _split(caplog)
    assert not guard and not ladder and len(quar) == 1
    assert quar[0].levelno == logging.ERROR
    message = quar[0].getMessage()
    assert "stage=asr_recovery" in message and "worker_reason=no_owned_words" in message
    assert len(warn) == 1
    job = store.probe("jobs", "a")
    assert job["state"] == "quarantined" and job["worker_failure"] == shape


def test_family_empty_asr_at_assemble_words_holds_for_recovery(caplog):
    """empty_asr at assemble_words reports the designed recovery hold."""
    caplog.set_level(logging.INFO)
    shape = {"stage": "assemble_words", "reason": "empty_asr"}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure=shape) is True
    guard, quar, ladder, warn = _split(caplog)
    assert not guard and not quar and len(ladder) == 1
    assert ladder[0].levelno == logging.INFO
    message = ladder[0].getMessage()
    assert "outcome=held_for_recovery" in message
    assert "attempt=1 recovery=held" in message
    assert "stage=assemble_words" in message and "worker_reason=empty_asr" in message
    assert len(warn) == 1
    job = store.probe("jobs", "a")
    assert job["state"] == "quarantined" and job["worker_failure"] == shape


def test_family_no_owned_words_at_assemble_words_holds_for_recovery(caplog):
    """no_owned_words at assemble_words reports the designed recovery hold."""
    caplog.set_level(logging.INFO)
    shape = {"stage": "assemble_words", "reason": "no_owned_words"}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure=shape) is True
    guard, quar, ladder, warn = _split(caplog)
    assert not guard and not quar and len(ladder) == 1
    assert ladder[0].levelno == logging.INFO
    message = ladder[0].getMessage()
    assert "outcome=held_for_recovery" in message
    assert "attempt=1 recovery=held" in message
    assert "stage=assemble_words" in message and "worker_reason=no_owned_words" in message
    assert len(warn) == 1
    job = store.probe("jobs", "a")
    assert job["state"] == "quarantined" and job["worker_failure"] == shape


def test_guard_fetch_decode_still_holds_for_redrive(caplog):
    """The guard terminal at fetch_decode keeps its INFO redrive line."""
    caplog.set_level(logging.INFO)
    shape = {"stage": "fetch_decode", "reason": "unsupported_language"}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure=shape) is True
    guard, quar, ladder, warn = _split(caplog)
    assert not quar and not ladder and len(guard) == 1
    assert guard[0].levelno == logging.INFO
    assert "outcome=held_for_redrive" in guard[0].getMessage()
    assert (
        "stage=fetch_decode" in guard[0].getMessage() and "worker_reason=unsupported_language" in guard[0].getMessage()
    )
    assert len(warn) == 1
    job = store.probe("jobs", "a")
    assert job["state"] == "quarantined" and job["worker_failure"] == shape


def test_guard_vad_windows_still_holds_for_redrive(caplog):
    """The guard terminal at vad_windows keeps its INFO redrive line."""
    caplog.set_level(logging.INFO)
    shape = {"stage": "vad_windows", "reason": "unsupported_language"}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure=shape) is True
    guard, quar, ladder, warn = _split(caplog)
    assert not quar and not ladder and len(guard) == 1
    assert guard[0].levelno == logging.INFO
    assert "outcome=held_for_redrive" in guard[0].getMessage()
    assert (
        "stage=vad_windows" in guard[0].getMessage() and "worker_reason=unsupported_language" in guard[0].getMessage()
    )
    assert len(warn) == 1
    job = store.probe("jobs", "a")
    assert job["state"] == "quarantined" and job["worker_failure"] == shape


def test_guard_word_clocks_still_holds_for_redrive(caplog):
    """The guard terminal at word_clocks keeps its INFO redrive line."""
    caplog.set_level(logging.INFO)
    shape = {"stage": "word_clocks", "reason": "unsupported_language"}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure=shape) is True
    guard, quar, ladder, warn = _split(caplog)
    assert not quar and not ladder and len(guard) == 1
    assert guard[0].levelno == logging.INFO
    assert "outcome=held_for_redrive" in guard[0].getMessage()
    assert (
        "stage=word_clocks" in guard[0].getMessage() and "worker_reason=unsupported_language" in guard[0].getMessage()
    )
    assert len(warn) == 1
    job = store.probe("jobs", "a")
    assert job["state"] == "quarantined" and job["worker_failure"] == shape


def test_guard_assemble_words_still_holds_for_redrive(caplog):
    """The guard terminal at assemble_words keeps its INFO redrive line."""
    caplog.set_level(logging.INFO)
    shape = {"stage": "assemble_words", "reason": "unsupported_language"}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure=shape) is True
    guard, quar, ladder, warn = _split(caplog)
    assert not quar and not ladder and len(guard) == 1
    assert guard[0].levelno == logging.INFO
    assert "outcome=held_for_redrive" in guard[0].getMessage()
    assert (
        "stage=assemble_words" in guard[0].getMessage()
        and "worker_reason=unsupported_language" in guard[0].getMessage()
    )
    assert len(warn) == 1
    job = store.probe("jobs", "a")
    assert job["state"] == "quarantined" and job["worker_failure"] == shape


def test_guard_asr_recovery_still_holds_for_redrive(caplog):
    """The guard terminal at asr_recovery keeps its INFO redrive line."""
    caplog.set_level(logging.INFO)
    shape = {"stage": "asr_recovery", "reason": "unsupported_language"}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure=shape) is True
    guard, quar, ladder, warn = _split(caplog)
    assert not quar and not ladder and len(guard) == 1
    assert guard[0].levelno == logging.INFO
    assert "outcome=held_for_redrive" in guard[0].getMessage()
    assert (
        "stage=asr_recovery" in guard[0].getMessage() and "worker_reason=unsupported_language" in guard[0].getMessage()
    )
    assert len(warn) == 1
    job = store.probe("jobs", "a")
    assert job["state"] == "quarantined" and job["worker_failure"] == shape


def test_evidence_only_family_stage_defers_without_a_terminal_line(caplog):
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure_evidence={"stage": "assemble_words", "reason": "empty_asr"}) is True
    guard, quar, ladder, warn = _split(caplog)
    assert not guard and not quar and not ladder and not warn
    job = store.probe("jobs", "a")
    assert job["state"] == "retry"
    assert job["worker_failure_evidence"] == {"stage": "assemble_words", "reason": "empty_asr"}


def test_evidence_only_fault_stage_defers_without_a_terminal_line(caplog):
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure_evidence={"stage": "vad_windows", "reason": "vad_bounds"}) is True
    guard, quar, ladder, warn = _split(caplog)
    assert not guard and not quar and not ladder and not warn


def test_evidence_only_guard_stage_defers_without_a_terminal_line(caplog):
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued()
    assert (
        _fail(queue, lease, worker_failure_evidence={"stage": "vad_windows", "reason": "unsupported_language"}) is True
    )
    guard, quar, ladder, warn = _split(caplog)
    assert not guard and not quar and not ladder and not warn


def test_preserved_family_evidence_demotes_the_exhausting_bare_call(caplog):
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure_evidence={"stage": "assemble_words", "reason": "empty_asr"}) is True
    store.rows["jobs", "a"].update(state="leased", token="t2", lease_until=100.0, attempt=99)
    assert queue.fail("a", "t2", 60.0) is True
    guard, quar, ladder, warn = _split(caplog)
    assert not guard and not quar and len(ladder) == 1
    assert "stage=assemble_words worker_reason=empty_asr" in ladder[0].getMessage()
    assert store.rows["jobs", "a"]["worker_failure_evidence"] == {"stage": "assemble_words", "reason": "empty_asr"}


def test_preserved_disposition_evidence_demotes_for_the_exhausting_bare_call(caplog):
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure_evidence={"stage": "vad_windows", "reason": "vad_bounds"}) is True
    store.rows["jobs", "a"].update(state="leased", token="t2", lease_until=100.0, attempt=99)
    assert queue.fail("a", "t2", 60.0) is True
    guard, quar, ladder, warn = _split(caplog)
    disposition = [r for r in caplog.records if "event=batch_validation_disposition" in r.getMessage()]
    assert not guard and not ladder and not quar and len(disposition) == 1
    assert "stage=vad_windows worker_reason=vad_bounds" in disposition[0].getMessage()


def test_current_family_call_beats_preserved_fault_evidence(caplog):
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure_evidence={"stage": "vad_windows", "reason": "vad_bounds"}) is True
    store.rows["jobs", "a"].update(state="leased", token="t2", lease_until=100.0, attempt=99)
    assert queue.fail("a", "t2", 60.0, worker_failure={"stage": "assemble_words", "reason": "empty_asr"}) is True
    guard, quar, ladder, warn = _split(caplog)
    assert not guard and not quar and len(ladder) == 1


def test_current_disposition_call_beats_preserved_family_evidence(caplog):
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure_evidence={"stage": "assemble_words", "reason": "empty_asr"}) is True
    store.rows["jobs", "a"].update(state="leased", token="t2", lease_until=100.0, attempt=99)
    assert queue.fail("a", "t2", 60.0, worker_failure={"stage": "vad_windows", "reason": "vad_bounds"}) is True
    guard, quar, ladder, warn = _split(caplog)
    disposition = [r for r in caplog.records if "event=batch_validation_disposition" in r.getMessage()]
    assert not guard and not ladder and not quar and len(disposition) == 1
    assert "stage=vad_windows worker_reason=vad_bounds" in disposition[0].getMessage()


def test_maxed_family_ladder_demotes_with_the_retained_attempt(caplog):
    caplog.set_level(logging.INFO)
    shape = {"stage": "assemble_words", "reason": "empty_asr"}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure_evidence=shape) is True
    store.rows["jobs", "a"].update(state="leased", token="t2", lease_until=100.0, attempt=99)
    assert queue.fail("a", "t2", 60.0) is True
    guard, quar, ladder, warn = _split(caplog)
    assert not guard and not quar and len(ladder) == 1
    assert "attempt=99 recovery=held" in ladder[0].getMessage()


def test_never_diagnosed_exhaustion_keeps_the_anonymous_fault_line(caplog):
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued()
    store.rows["jobs", "a"].update(state="leased", token="t2", lease_until=100.0, attempt=99)
    assert queue.fail("a", "t2", 60.0) is True
    guard, quar, ladder, warn = _split(caplog)
    assert not guard and not ladder and len(quar) == 1
    assert "stage=unknown worker_reason=unclassified" in quar[0].getMessage()
    assert quar[0].levelno == logging.ERROR


def test_demoted_hold_records_quarantined_then_recovery_held_metrics():
    calls = []
    metrics = SimpleNamespace(record=lambda name, reason=None: calls.append(name))
    caplog_enabled = None
    store, queue, lease = _queued(metrics=metrics)
    assert _fail(queue, lease, worker_failure={"stage": "assemble_words", "reason": "empty_asr"}) is True
    assert calls == ["quarantined", "recovery_held"]


def test_fault_hold_records_quarantined_then_recovery_held_metrics():
    calls = []
    metrics = SimpleNamespace(record=lambda name, reason=None: calls.append(name))
    store, queue, lease = _queued(metrics=metrics)
    assert _fail(queue, lease, worker_failure={"stage": "vad_windows", "reason": "vad_bounds"}) is True
    assert calls == ["quarantined", "recovery_held"]


def test_guard_hold_records_quarantined_then_recovery_held_metrics():
    calls = []
    metrics = SimpleNamespace(record=lambda name, reason=None: calls.append(name))
    store, queue, lease = _queued(metrics=metrics)
    assert _fail(queue, lease, worker_failure={"stage": "vad_windows", "reason": "unsupported_language"}) is True
    assert calls == ["quarantined", "recovery_held"]


def test_defer_records_the_retry_metric_only():
    calls = []
    metrics = SimpleNamespace(record=lambda name, reason=None: calls.append(name))
    store, queue, lease = _queued(metrics=metrics)
    assert _fail(queue, lease, worker_failure_evidence={"stage": "assemble_words", "reason": "empty_asr"}) is True
    assert calls == ["retry"]


def test_demoted_hold_records_failed_correctness(monkeypatch):
    calls = []
    monkeypatch.setattr(
        scheduler_module, "record_correctness", lambda name, seconds=None: calls.append((name, seconds))
    )
    store, queue, lease = _queued(duration=45)
    assert _fail(queue, lease, worker_failure={"stage": "assemble_words", "reason": "empty_asr"}) is True
    assert calls == [("failed", 45)]


def test_defer_records_no_failed_correctness(monkeypatch):
    calls = []
    monkeypatch.setattr(
        scheduler_module, "record_correctness", lambda name, seconds=None: calls.append((name, seconds))
    )
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure_evidence={"stage": "assemble_words", "reason": "empty_asr"}) is True
    assert calls == []


def test_family_quarantine_with_the_empty_token_writes_versioned_evidence():
    store, queue, lease = _queued()
    assert _fail(queue, lease, quarantine=True, padded_retry="empty", padded_retry_empty=True) is True
    job = store.probe("jobs", "a")
    assert job["worker_empty_evidence"] == {"padded_retry": "empty", "version": 1}
    assert job["state"] == "quarantined"
    assert "worker_failure" not in job


def test_family_quarantine_with_the_skipped_oversize_token_writes_the_evidence():
    store, queue, lease = _queued()
    assert _fail(queue, lease, quarantine=True, padded_retry="skipped_oversize") is True
    assert store.probe("jobs", "a")["worker_empty_evidence"] == {"padded_retry": "skipped_oversize", "version": 1}


def test_family_quarantine_with_the_skipped_long_speech_token_writes_the_evidence():
    store, queue, lease = _queued()
    assert _fail(queue, lease, quarantine=True, padded_retry="skipped_long_speech") is True
    assert store.probe("jobs", "a")["worker_empty_evidence"] == {"padded_retry": "skipped_long_speech", "version": 1}


def test_family_quarantine_without_a_padded_token_writes_no_evidence():
    store, queue, lease = _queued()
    assert (
        _fail(queue, lease, quarantine=True, worker_failure={"stage": "assemble_words", "reason": "empty_asr"}) is True
    )
    assert "worker_empty_evidence" not in store.probe("jobs", "a")


def test_family_quarantine_with_an_invalid_token_is_refused_before_any_write():
    store, queue, lease = _queued()
    with pytest.raises(ValueError, match="invalid padded retry evidence"):
        _fail(queue, lease, quarantine=True, padded_retry="identical")
    assert store.probe("jobs", "a")["state"] == "leased"


def test_wrong_token_cannot_move_a_family_unit():
    store, queue, lease = _queued()
    assert (
        queue.fail(
            "a",
            "wrong-token",
            1100.0,
            quarantine=True,
            worker_failure={"stage": "assemble_words", "reason": "empty_asr"},
        )
        is False
    )
    assert store.probe("jobs", "a")["state"] == "leased"


def test_expired_lease_cannot_move_a_family_unit():
    store, queue, lease = _queued()
    assert (
        queue.fail(
            "a",
            lease.token,
            99999.0,
            quarantine=True,
            worker_failure={"stage": "assemble_words", "reason": "empty_asr"},
        )
        is False
    )
    assert store.probe("jobs", "a")["state"] == "leased"


def test_quarantined_family_unit_is_not_due_again():
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure={"stage": "assemble_words", "reason": "empty_asr"}) is True
    assert store.due("retry", 99999.0, 100) == []
    assert store.probe("jobs", "a")["state"] == "quarantined"


def test_family_attempt_2_demotes_with_the_retained_attempt(caplog):
    caplog.set_level(logging.INFO)
    shape = {"stage": "assemble_words", "reason": "empty_asr"}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure_evidence=shape) is True
    store.rows["jobs", "a"].update(state="leased", token="t2", lease_until=100.0, attempt=20)
    assert queue.fail("a", "t2", 60.0) is True
    guard, quar, ladder, warn = _split(caplog)
    assert not guard and not quar and len(ladder) == 1
    assert "attempt=20 recovery=held" in ladder[0].getMessage()


def test_family_attempt_5_demotes_with_the_retained_attempt(caplog):
    caplog.set_level(logging.INFO)
    shape = {"stage": "assemble_words", "reason": "empty_asr"}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure_evidence=shape) is True
    store.rows["jobs", "a"].update(state="leased", token="t2", lease_until=100.0, attempt=40)
    assert queue.fail("a", "t2", 60.0) is True
    guard, quar, ladder, warn = _split(caplog)
    assert not guard and not quar and len(ladder) == 1
    assert "attempt=40 recovery=held" in ladder[0].getMessage()


def test_family_attempt_7_demotes_with_the_retained_attempt(caplog):
    caplog.set_level(logging.INFO)
    shape = {"stage": "assemble_words", "reason": "empty_asr"}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure_evidence=shape) is True
    store.rows["jobs", "a"].update(state="leased", token="t2", lease_until=100.0, attempt=60)
    assert queue.fail("a", "t2", 60.0) is True
    guard, quar, ladder, warn = _split(caplog)
    assert not guard and not quar and len(ladder) == 1
    assert "attempt=60 recovery=held" in ladder[0].getMessage()


def test_family_attempt_50_demotes_with_the_retained_attempt(caplog):
    caplog.set_level(logging.INFO)
    shape = {"stage": "assemble_words", "reason": "empty_asr"}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure_evidence=shape) is True
    store.rows["jobs", "a"].update(state="leased", token="t2", lease_until=100.0, attempt=80)
    assert queue.fail("a", "t2", 60.0) is True
    guard, quar, ladder, warn = _split(caplog)
    assert not guard and not quar and len(ladder) == 1
    assert "attempt=80 recovery=held" in ladder[0].getMessage()


def test_disposition_vad_bounds_maxed_ladder_demotes_with_the_retained_attempt(caplog):
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure_evidence={"stage": "vad_windows", "reason": "vad_bounds"}) is True
    store.rows["jobs", "a"].update(state="leased", token="t2", lease_until=100.0, attempt=80)
    assert queue.fail("a", "t2", 60.0) is True
    guard, quar, ladder, warn = _split(caplog)
    disposition = [r for r in caplog.records if "event=batch_validation_disposition" in r.getMessage()]
    assert not guard and not ladder and not quar and len(disposition) == 1
    assert "attempt=80 recovery=held" in disposition[0].getMessage()


def test_evidence_only_no_owned_stage_defers_without_a_terminal_line(caplog):
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure_evidence={"stage": "assemble_words", "reason": "no_owned_words"}) is True
    guard, quar, ladder, warn = _split(caplog)
    assert not guard and not quar and not ladder and not warn
    job = store.probe("jobs", "a")
    assert job["state"] == "retry"
    assert job["worker_failure_evidence"] == {"stage": "assemble_words", "reason": "no_owned_words"}


def test_evidence_only_guard_family_defers_without_a_terminal_line(caplog):
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued()
    assert (
        _fail(queue, lease, worker_failure_evidence={"stage": "asr_recovery", "reason": "unsupported_language"}) is True
    )
    guard, quar, ladder, warn = _split(caplog)
    assert not guard and not quar and not ladder and not warn


def test_guard_attempt_20_still_holds_for_redrive(caplog):
    caplog.set_level(logging.INFO)
    shape = {"stage": "vad_windows", "reason": "unsupported_language"}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure_evidence=shape) is True
    store.rows["jobs", "a"].update(state="leased", token="t2", lease_until=100.0, attempt=20)
    assert queue.fail("a", "t2", 60.0) is True
    guard, quar, ladder, warn = _split(caplog)
    assert not quar and not ladder and len(guard) == 1
    assert "attempt=20 recovery=held" in guard[0].getMessage()


def test_guard_attempt_40_still_holds_for_redrive(caplog):
    caplog.set_level(logging.INFO)
    shape = {"stage": "vad_windows", "reason": "unsupported_language"}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure_evidence=shape) is True
    store.rows["jobs", "a"].update(state="leased", token="t2", lease_until=100.0, attempt=40)
    assert queue.fail("a", "t2", 60.0) is True
    guard, quar, ladder, warn = _split(caplog)
    assert not quar and not ladder and len(guard) == 1
    assert "attempt=40 recovery=held" in guard[0].getMessage()


def test_guard_attempt_60_still_holds_for_redrive(caplog):
    caplog.set_level(logging.INFO)
    shape = {"stage": "vad_windows", "reason": "unsupported_language"}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure_evidence=shape) is True
    store.rows["jobs", "a"].update(state="leased", token="t2", lease_until=100.0, attempt=60)
    assert queue.fail("a", "t2", 60.0) is True
    guard, quar, ladder, warn = _split(caplog)
    assert not quar and not ladder and len(guard) == 1
    assert "attempt=60 recovery=held" in guard[0].getMessage()


def test_guard_attempt_80_still_holds_for_redrive(caplog):
    caplog.set_level(logging.INFO)
    shape = {"stage": "vad_windows", "reason": "unsupported_language"}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure_evidence=shape) is True
    store.rows["jobs", "a"].update(state="leased", token="t2", lease_until=100.0, attempt=80)
    assert queue.fail("a", "t2", 60.0) is True
    guard, quar, ladder, warn = _split(caplog)
    assert not quar and not ladder and len(guard) == 1
    assert "attempt=80 recovery=held" in guard[0].getMessage()


def test_guard_attempt_99_still_holds_for_redrive(caplog):
    caplog.set_level(logging.INFO)
    shape = {"stage": "vad_windows", "reason": "unsupported_language"}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure_evidence=shape) is True
    store.rows["jobs", "a"].update(state="leased", token="t2", lease_until=100.0, attempt=99)
    assert queue.fail("a", "t2", 60.0) is True
    guard, quar, ladder, warn = _split(caplog)
    assert not quar and not ladder and len(guard) == 1
    assert "attempt=99 recovery=held" in guard[0].getMessage()


def test_family_hold_without_metrics_object_is_safe(caplog):
    caplog.set_level(logging.INFO)
    shape = {"stage": "assemble_words", "reason": "empty_asr"}
    store, queue, lease = _queued()
    queue.metrics = None
    assert _fail(queue, lease, worker_failure=shape) is True
    guard, quar, ladder, warn = _split(caplog)
    assert not guard and not quar and len(ladder) == 1


def test_disposition_hold_without_metrics_object_is_safe(caplog):
    caplog.set_level(logging.INFO)
    shape = {"stage": "vad_windows", "reason": "vad_bounds"}
    store, queue, lease = _queued()
    queue.metrics = None
    assert _fail(queue, lease, worker_failure=shape) is True
    guard, quar, ladder, warn = _split(caplog)
    disposition = [r for r in caplog.records if "event=batch_validation_disposition" in r.getMessage()]
    assert not guard and not ladder and not quar and len(disposition) == 1
