# Failure-Class: FC-terminal-validation-disposition-misbooked-as-worker-fault
"""The scheduler terminal hold rechannels the validation disposition, live, cell-by-cell.

Every diagnosis the store validators admit is driven through a real
``Scheduler.fail`` over ``MemoryStore`` with INFO captured. The fetch_decode
trio and — under the disposition switch — the vad/word verdicts report
``event=batch_validation_disposition outcome=held_for_disposition``; the
sibling empty-ladder and language-guard families keep their own demoted
lines; the admitted-source refusal and the anonymous bucket keep the ERROR
``batch_quarantined`` line. Durable state, attempt retention, evidence
booking, the ``recovery_held`` metric and the awaiting-fenced-recovery
warning are pinned unchanged next to the new channel. The evidence-only
ladder names its preserved diagnosis through the same channel when the
ladder exhausts, under both switch positions.
"""

import logging
import time
from unittest.mock import Mock

import utils.batch_pipeline.scheduler as scheduler_module
from tests.unit.test_batch_pipeline_scheduler import MemoryStore, item as sched_item
from utils.batch_pipeline.contracts import Priority
from utils.batch_pipeline.scheduler import Scheduler

STAGES = ('fetch_decode', 'vad_windows', 'word_clocks', 'assemble_words', 'asr_recovery')
TERMINAL_REASONS = (
    'staged_audio_invalid',
    'retained_audio_invalid',
    'decoded_duration_mismatch',
    'word_shape',
    'word_clock',
    'word_sequence',
    'vad_nonfinite',
    'vad_order',
    'vad_bounds',
    'empty_asr',
    'no_owned_words',
    'unsupported_language',
    'outside_admitted_source',
)
EVIDENCE_REASONS = (
    'staged_audio_invalid',
    'retained_audio_invalid',
    'decoded_duration_mismatch',
    'word_shape',
    'word_clock',
    'word_sequence',
    'vad_nonfinite',
    'vad_order',
    'vad_bounds',
    'empty_asr',
    'no_owned_words',
    'unsupported_language',
    'outside_admitted_source',
    'unknown',
)
TRIO = ('staged_audio_invalid', 'retained_audio_invalid', 'decoded_duration_mismatch')
FLAGGED = ('word_shape', 'word_clock', 'word_sequence', 'vad_nonfinite', 'vad_order', 'vad_bounds')
EMPTY = ('empty_asr', 'no_owned_words')


def _queued(key="a", owner="disp-owner", duration=30, metrics=None):
    store = MemoryStore()
    queue = Scheduler(store, metrics=metrics)
    work = sched_item(key, owner=owner, duration=duration, priority=Priority.FRESH)
    assert queue.enqueue(work, time.time())
    lease = queue.pull(time.time())[0]
    return store, queue, lease


def _queued_for_walk(key="a", owner="disp-owner", duration=30):
    """Enqueue without pulling: the walk owns every pull, so the ladder counts 5 real fails."""
    store = MemoryStore()
    queue = Scheduler(store)
    work = sched_item(key, owner=owner, duration=duration, priority=Priority.FRESH)
    assert queue.enqueue(work, time.time())
    return store, queue


def _fail(queue, lease, **kwargs):
    return queue.fail(lease.item.segment_id, lease.token, time.time() + 100.0, **kwargs)


def _walk(queue, store, evidence_plan=None):
    """Pull->fail until quarantined; evidence_plan maps attempt number -> evidence."""
    now = time.time()
    attempt = 0
    for _ in range(14):
        leases = queue.pull(now)
        if not leases:
            now += 30.0
            queue.recover(now)
            continue
        attempt += 1
        now += 10.0
        queue.fail("a", leases[0].token, now, worker_failure_evidence=(evidence_plan or {}).get(attempt))
        if store.rows["jobs", "a"]["state"] == "quarantined":
            return attempt
    raise AssertionError("ladder never quarantined the unit")


def _channel(caplog):
    source = caplog.text
    disposition = [r for r in caplog.records if "event=batch_validation_disposition" in r.getMessage()]
    quar = [r for r in caplog.records if "event=batch_quarantined" in r.getMessage()]
    ladder = [r for r in caplog.records if "event=batch_empty_ladder" in r.getMessage()]
    guard = [r for r in caplog.records if "event=batch_language_guard" in r.getMessage()]
    warn = [r for r in caplog.records if "awaiting_fenced_recovery" in r.getMessage()]
    return disposition, quar, ladder, guard, warn


def _message(caplog, event):
    return [r.getMessage() for r in caplog.records if event in r.getMessage()][0]


def test_terminal_fetch_decode_staged_audio_invalid_books_the_disposition_channel(monkeypatch, caplog):
    """worker_failure=(fetch_decode, staged_audio_invalid) books the disposition channel."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure={"stage": "fetch_decode", "reason": "staged_audio_invalid"}) is True
    disposition, quar, ladder, guard, warn = _channel(caplog)
    assert not quar and not ladder and not guard and len(disposition) == 1
    assert disposition[0].levelno == logging.INFO
    assert "outcome=held_for_disposition" in disposition[0].getMessage()
    assert "stage=fetch_decode" in disposition[0].getMessage()
    assert "worker_reason=staged_audio_invalid" in disposition[0].getMessage()
    assert len(warn) == 1
    job = store.probe("jobs", "a")
    assert job["state"] == "quarantined"
    assert job["worker_failure"] == {"stage": "fetch_decode", "reason": "staged_audio_invalid"}


def test_terminal_fetch_decode_retained_audio_invalid_books_the_disposition_channel(monkeypatch, caplog):
    """worker_failure=(fetch_decode, retained_audio_invalid) books the disposition channel."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure={"stage": "fetch_decode", "reason": "retained_audio_invalid"}) is True
    disposition, quar, ladder, guard, warn = _channel(caplog)
    assert not quar and not ladder and not guard and len(disposition) == 1
    assert disposition[0].levelno == logging.INFO
    assert "outcome=held_for_disposition" in disposition[0].getMessage()
    assert "stage=fetch_decode" in disposition[0].getMessage()
    assert "worker_reason=retained_audio_invalid" in disposition[0].getMessage()
    assert len(warn) == 1
    job = store.probe("jobs", "a")
    assert job["state"] == "quarantined"
    assert job["worker_failure"] == {"stage": "fetch_decode", "reason": "retained_audio_invalid"}


def test_terminal_fetch_decode_decoded_duration_mismatch_books_the_disposition_channel(monkeypatch, caplog):
    """worker_failure=(fetch_decode, decoded_duration_mismatch) books the disposition channel."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure={"stage": "fetch_decode", "reason": "decoded_duration_mismatch"}) is True
    disposition, quar, ladder, guard, warn = _channel(caplog)
    assert not quar and not ladder and not guard and len(disposition) == 1
    assert disposition[0].levelno == logging.INFO
    assert "outcome=held_for_disposition" in disposition[0].getMessage()
    assert "stage=fetch_decode" in disposition[0].getMessage()
    assert "worker_reason=decoded_duration_mismatch" in disposition[0].getMessage()
    assert len(warn) == 1
    job = store.probe("jobs", "a")
    assert job["state"] == "quarantined"
    assert job["worker_failure"] == {"stage": "fetch_decode", "reason": "decoded_duration_mismatch"}


def test_terminal_fetch_decode_word_shape_books_the_disposition_channel(monkeypatch, caplog):
    """worker_failure=(fetch_decode, word_shape) books the disposition channel."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure={"stage": "fetch_decode", "reason": "word_shape"}) is True
    disposition, quar, ladder, guard, warn = _channel(caplog)
    assert not quar and not ladder and not guard and len(disposition) == 1
    assert disposition[0].levelno == logging.INFO
    assert "outcome=held_for_disposition" in disposition[0].getMessage()
    assert "stage=fetch_decode" in disposition[0].getMessage()
    assert "worker_reason=word_shape" in disposition[0].getMessage()
    assert len(warn) == 1
    job = store.probe("jobs", "a")
    assert job["state"] == "quarantined"
    assert job["worker_failure"] == {"stage": "fetch_decode", "reason": "word_shape"}


def test_terminal_fetch_decode_word_clock_books_the_disposition_channel(monkeypatch, caplog):
    """worker_failure=(fetch_decode, word_clock) books the disposition channel."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure={"stage": "fetch_decode", "reason": "word_clock"}) is True
    disposition, quar, ladder, guard, warn = _channel(caplog)
    assert not quar and not ladder and not guard and len(disposition) == 1
    assert disposition[0].levelno == logging.INFO
    assert "outcome=held_for_disposition" in disposition[0].getMessage()
    assert "stage=fetch_decode" in disposition[0].getMessage()
    assert "worker_reason=word_clock" in disposition[0].getMessage()
    assert len(warn) == 1
    job = store.probe("jobs", "a")
    assert job["state"] == "quarantined"
    assert job["worker_failure"] == {"stage": "fetch_decode", "reason": "word_clock"}


def test_terminal_fetch_decode_word_sequence_books_the_disposition_channel(monkeypatch, caplog):
    """worker_failure=(fetch_decode, word_sequence) books the disposition channel."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure={"stage": "fetch_decode", "reason": "word_sequence"}) is True
    disposition, quar, ladder, guard, warn = _channel(caplog)
    assert not quar and not ladder and not guard and len(disposition) == 1
    assert disposition[0].levelno == logging.INFO
    assert "outcome=held_for_disposition" in disposition[0].getMessage()
    assert "stage=fetch_decode" in disposition[0].getMessage()
    assert "worker_reason=word_sequence" in disposition[0].getMessage()
    assert len(warn) == 1
    job = store.probe("jobs", "a")
    assert job["state"] == "quarantined"
    assert job["worker_failure"] == {"stage": "fetch_decode", "reason": "word_sequence"}


def test_terminal_fetch_decode_vad_nonfinite_books_the_disposition_channel(monkeypatch, caplog):
    """worker_failure=(fetch_decode, vad_nonfinite) books the disposition channel."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure={"stage": "fetch_decode", "reason": "vad_nonfinite"}) is True
    disposition, quar, ladder, guard, warn = _channel(caplog)
    assert not quar and not ladder and not guard and len(disposition) == 1
    assert disposition[0].levelno == logging.INFO
    assert "outcome=held_for_disposition" in disposition[0].getMessage()
    assert "stage=fetch_decode" in disposition[0].getMessage()
    assert "worker_reason=vad_nonfinite" in disposition[0].getMessage()
    assert len(warn) == 1
    job = store.probe("jobs", "a")
    assert job["state"] == "quarantined"
    assert job["worker_failure"] == {"stage": "fetch_decode", "reason": "vad_nonfinite"}


def test_terminal_fetch_decode_vad_order_books_the_disposition_channel(monkeypatch, caplog):
    """worker_failure=(fetch_decode, vad_order) books the disposition channel."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure={"stage": "fetch_decode", "reason": "vad_order"}) is True
    disposition, quar, ladder, guard, warn = _channel(caplog)
    assert not quar and not ladder and not guard and len(disposition) == 1
    assert disposition[0].levelno == logging.INFO
    assert "outcome=held_for_disposition" in disposition[0].getMessage()
    assert "stage=fetch_decode" in disposition[0].getMessage()
    assert "worker_reason=vad_order" in disposition[0].getMessage()
    assert len(warn) == 1
    job = store.probe("jobs", "a")
    assert job["state"] == "quarantined"
    assert job["worker_failure"] == {"stage": "fetch_decode", "reason": "vad_order"}


def test_terminal_fetch_decode_vad_bounds_books_the_disposition_channel(monkeypatch, caplog):
    """worker_failure=(fetch_decode, vad_bounds) books the disposition channel."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure={"stage": "fetch_decode", "reason": "vad_bounds"}) is True
    disposition, quar, ladder, guard, warn = _channel(caplog)
    assert not quar and not ladder and not guard and len(disposition) == 1
    assert disposition[0].levelno == logging.INFO
    assert "outcome=held_for_disposition" in disposition[0].getMessage()
    assert "stage=fetch_decode" in disposition[0].getMessage()
    assert "worker_reason=vad_bounds" in disposition[0].getMessage()
    assert len(warn) == 1
    job = store.probe("jobs", "a")
    assert job["state"] == "quarantined"
    assert job["worker_failure"] == {"stage": "fetch_decode", "reason": "vad_bounds"}


def test_terminal_fetch_decode_empty_asr_books_the_quarantined_channel(monkeypatch, caplog):
    """worker_failure=(fetch_decode, empty_asr) books the quarantined channel."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure={"stage": "fetch_decode", "reason": "empty_asr"}) is True
    disposition, quar, ladder, guard, warn = _channel(caplog)
    assert not disposition and not ladder and not guard and len(quar) == 1
    assert quar[0].levelno == logging.ERROR
    assert "reason=worker_failed" in quar[0].getMessage()
    assert "stage=fetch_decode" in quar[0].getMessage()
    assert "worker_reason=empty_asr" in quar[0].getMessage()
    assert len(warn) == 1
    job = store.probe("jobs", "a")
    assert job["state"] == "quarantined"
    assert job["worker_failure"] == {"stage": "fetch_decode", "reason": "empty_asr"}


def test_terminal_fetch_decode_no_owned_words_books_the_quarantined_channel(monkeypatch, caplog):
    """worker_failure=(fetch_decode, no_owned_words) books the quarantined channel."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure={"stage": "fetch_decode", "reason": "no_owned_words"}) is True
    disposition, quar, ladder, guard, warn = _channel(caplog)
    assert not disposition and not ladder and not guard and len(quar) == 1
    assert quar[0].levelno == logging.ERROR
    assert "reason=worker_failed" in quar[0].getMessage()
    assert "stage=fetch_decode" in quar[0].getMessage()
    assert "worker_reason=no_owned_words" in quar[0].getMessage()
    assert len(warn) == 1
    job = store.probe("jobs", "a")
    assert job["state"] == "quarantined"
    assert job["worker_failure"] == {"stage": "fetch_decode", "reason": "no_owned_words"}


def test_terminal_fetch_decode_unsupported_language_books_the_guard_channel(monkeypatch, caplog):
    """worker_failure=(fetch_decode, unsupported_language) books the guard channel."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure={"stage": "fetch_decode", "reason": "unsupported_language"}) is True
    disposition, quar, ladder, guard, warn = _channel(caplog)
    assert not disposition and not quar and not ladder and len(guard) == 1
    assert guard[0].levelno == logging.INFO
    assert "outcome=held_for_redrive" in guard[0].getMessage()
    assert len(warn) == 1
    job = store.probe("jobs", "a")
    assert job["state"] == "quarantined"
    assert job["worker_failure"] == {"stage": "fetch_decode", "reason": "unsupported_language"}


def test_terminal_fetch_decode_outside_admitted_source_books_the_quarantined_channel(monkeypatch, caplog):
    """worker_failure=(fetch_decode, outside_admitted_source) books the quarantined channel."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure={"stage": "fetch_decode", "reason": "outside_admitted_source"}) is True
    disposition, quar, ladder, guard, warn = _channel(caplog)
    assert not disposition and not ladder and not guard and len(quar) == 1
    assert quar[0].levelno == logging.ERROR
    assert "reason=worker_failed" in quar[0].getMessage()
    assert "stage=fetch_decode" in quar[0].getMessage()
    assert "worker_reason=outside_admitted_source" in quar[0].getMessage()
    assert len(warn) == 1
    job = store.probe("jobs", "a")
    assert job["state"] == "quarantined"
    assert job["worker_failure"] == {"stage": "fetch_decode", "reason": "outside_admitted_source"}


def test_terminal_vad_windows_staged_audio_invalid_books_the_quarantined_channel(monkeypatch, caplog):
    """worker_failure=(vad_windows, staged_audio_invalid) books the quarantined channel."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure={"stage": "vad_windows", "reason": "staged_audio_invalid"}) is True
    disposition, quar, ladder, guard, warn = _channel(caplog)
    assert not disposition and not ladder and not guard and len(quar) == 1
    assert quar[0].levelno == logging.ERROR
    assert "reason=worker_failed" in quar[0].getMessage()
    assert "stage=vad_windows" in quar[0].getMessage()
    assert "worker_reason=staged_audio_invalid" in quar[0].getMessage()
    assert len(warn) == 1
    job = store.probe("jobs", "a")
    assert job["state"] == "quarantined"
    assert job["worker_failure"] == {"stage": "vad_windows", "reason": "staged_audio_invalid"}


def test_terminal_vad_windows_retained_audio_invalid_books_the_quarantined_channel(monkeypatch, caplog):
    """worker_failure=(vad_windows, retained_audio_invalid) books the quarantined channel."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure={"stage": "vad_windows", "reason": "retained_audio_invalid"}) is True
    disposition, quar, ladder, guard, warn = _channel(caplog)
    assert not disposition and not ladder and not guard and len(quar) == 1
    assert quar[0].levelno == logging.ERROR
    assert "reason=worker_failed" in quar[0].getMessage()
    assert "stage=vad_windows" in quar[0].getMessage()
    assert "worker_reason=retained_audio_invalid" in quar[0].getMessage()
    assert len(warn) == 1
    job = store.probe("jobs", "a")
    assert job["state"] == "quarantined"
    assert job["worker_failure"] == {"stage": "vad_windows", "reason": "retained_audio_invalid"}


def test_terminal_vad_windows_decoded_duration_mismatch_books_the_quarantined_channel(monkeypatch, caplog):
    """worker_failure=(vad_windows, decoded_duration_mismatch) books the quarantined channel."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure={"stage": "vad_windows", "reason": "decoded_duration_mismatch"}) is True
    disposition, quar, ladder, guard, warn = _channel(caplog)
    assert not disposition and not ladder and not guard and len(quar) == 1
    assert quar[0].levelno == logging.ERROR
    assert "reason=worker_failed" in quar[0].getMessage()
    assert "stage=vad_windows" in quar[0].getMessage()
    assert "worker_reason=decoded_duration_mismatch" in quar[0].getMessage()
    assert len(warn) == 1
    job = store.probe("jobs", "a")
    assert job["state"] == "quarantined"
    assert job["worker_failure"] == {"stage": "vad_windows", "reason": "decoded_duration_mismatch"}


def test_terminal_vad_windows_word_shape_books_the_disposition_channel(monkeypatch, caplog):
    """worker_failure=(vad_windows, word_shape) books the disposition channel."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure={"stage": "vad_windows", "reason": "word_shape"}) is True
    disposition, quar, ladder, guard, warn = _channel(caplog)
    assert not quar and not ladder and not guard and len(disposition) == 1
    assert disposition[0].levelno == logging.INFO
    assert "outcome=held_for_disposition" in disposition[0].getMessage()
    assert "stage=vad_windows" in disposition[0].getMessage()
    assert "worker_reason=word_shape" in disposition[0].getMessage()
    assert len(warn) == 1
    job = store.probe("jobs", "a")
    assert job["state"] == "quarantined"
    assert job["worker_failure"] == {"stage": "vad_windows", "reason": "word_shape"}


def test_terminal_vad_windows_word_clock_books_the_disposition_channel(monkeypatch, caplog):
    """worker_failure=(vad_windows, word_clock) books the disposition channel."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure={"stage": "vad_windows", "reason": "word_clock"}) is True
    disposition, quar, ladder, guard, warn = _channel(caplog)
    assert not quar and not ladder and not guard and len(disposition) == 1
    assert disposition[0].levelno == logging.INFO
    assert "outcome=held_for_disposition" in disposition[0].getMessage()
    assert "stage=vad_windows" in disposition[0].getMessage()
    assert "worker_reason=word_clock" in disposition[0].getMessage()
    assert len(warn) == 1
    job = store.probe("jobs", "a")
    assert job["state"] == "quarantined"
    assert job["worker_failure"] == {"stage": "vad_windows", "reason": "word_clock"}


def test_terminal_vad_windows_word_sequence_books_the_disposition_channel(monkeypatch, caplog):
    """worker_failure=(vad_windows, word_sequence) books the disposition channel."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure={"stage": "vad_windows", "reason": "word_sequence"}) is True
    disposition, quar, ladder, guard, warn = _channel(caplog)
    assert not quar and not ladder and not guard and len(disposition) == 1
    assert disposition[0].levelno == logging.INFO
    assert "outcome=held_for_disposition" in disposition[0].getMessage()
    assert "stage=vad_windows" in disposition[0].getMessage()
    assert "worker_reason=word_sequence" in disposition[0].getMessage()
    assert len(warn) == 1
    job = store.probe("jobs", "a")
    assert job["state"] == "quarantined"
    assert job["worker_failure"] == {"stage": "vad_windows", "reason": "word_sequence"}


def test_terminal_vad_windows_vad_nonfinite_books_the_disposition_channel(monkeypatch, caplog):
    """worker_failure=(vad_windows, vad_nonfinite) books the disposition channel."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure={"stage": "vad_windows", "reason": "vad_nonfinite"}) is True
    disposition, quar, ladder, guard, warn = _channel(caplog)
    assert not quar and not ladder and not guard and len(disposition) == 1
    assert disposition[0].levelno == logging.INFO
    assert "outcome=held_for_disposition" in disposition[0].getMessage()
    assert "stage=vad_windows" in disposition[0].getMessage()
    assert "worker_reason=vad_nonfinite" in disposition[0].getMessage()
    assert len(warn) == 1
    job = store.probe("jobs", "a")
    assert job["state"] == "quarantined"
    assert job["worker_failure"] == {"stage": "vad_windows", "reason": "vad_nonfinite"}


def test_terminal_vad_windows_vad_order_books_the_disposition_channel(monkeypatch, caplog):
    """worker_failure=(vad_windows, vad_order) books the disposition channel."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure={"stage": "vad_windows", "reason": "vad_order"}) is True
    disposition, quar, ladder, guard, warn = _channel(caplog)
    assert not quar and not ladder and not guard and len(disposition) == 1
    assert disposition[0].levelno == logging.INFO
    assert "outcome=held_for_disposition" in disposition[0].getMessage()
    assert "stage=vad_windows" in disposition[0].getMessage()
    assert "worker_reason=vad_order" in disposition[0].getMessage()
    assert len(warn) == 1
    job = store.probe("jobs", "a")
    assert job["state"] == "quarantined"
    assert job["worker_failure"] == {"stage": "vad_windows", "reason": "vad_order"}


def test_terminal_vad_windows_vad_bounds_books_the_disposition_channel(monkeypatch, caplog):
    """worker_failure=(vad_windows, vad_bounds) books the disposition channel."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure={"stage": "vad_windows", "reason": "vad_bounds"}) is True
    disposition, quar, ladder, guard, warn = _channel(caplog)
    assert not quar and not ladder and not guard and len(disposition) == 1
    assert disposition[0].levelno == logging.INFO
    assert "outcome=held_for_disposition" in disposition[0].getMessage()
    assert "stage=vad_windows" in disposition[0].getMessage()
    assert "worker_reason=vad_bounds" in disposition[0].getMessage()
    assert len(warn) == 1
    job = store.probe("jobs", "a")
    assert job["state"] == "quarantined"
    assert job["worker_failure"] == {"stage": "vad_windows", "reason": "vad_bounds"}


def test_terminal_vad_windows_empty_asr_books_the_quarantined_channel(monkeypatch, caplog):
    """worker_failure=(vad_windows, empty_asr) books the quarantined channel."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure={"stage": "vad_windows", "reason": "empty_asr"}) is True
    disposition, quar, ladder, guard, warn = _channel(caplog)
    assert not disposition and not ladder and not guard and len(quar) == 1
    assert quar[0].levelno == logging.ERROR
    assert "reason=worker_failed" in quar[0].getMessage()
    assert "stage=vad_windows" in quar[0].getMessage()
    assert "worker_reason=empty_asr" in quar[0].getMessage()
    assert len(warn) == 1
    job = store.probe("jobs", "a")
    assert job["state"] == "quarantined"
    assert job["worker_failure"] == {"stage": "vad_windows", "reason": "empty_asr"}


def test_terminal_vad_windows_no_owned_words_books_the_quarantined_channel(monkeypatch, caplog):
    """worker_failure=(vad_windows, no_owned_words) books the quarantined channel."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure={"stage": "vad_windows", "reason": "no_owned_words"}) is True
    disposition, quar, ladder, guard, warn = _channel(caplog)
    assert not disposition and not ladder and not guard and len(quar) == 1
    assert quar[0].levelno == logging.ERROR
    assert "reason=worker_failed" in quar[0].getMessage()
    assert "stage=vad_windows" in quar[0].getMessage()
    assert "worker_reason=no_owned_words" in quar[0].getMessage()
    assert len(warn) == 1
    job = store.probe("jobs", "a")
    assert job["state"] == "quarantined"
    assert job["worker_failure"] == {"stage": "vad_windows", "reason": "no_owned_words"}


def test_terminal_vad_windows_unsupported_language_books_the_guard_channel(monkeypatch, caplog):
    """worker_failure=(vad_windows, unsupported_language) books the guard channel."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure={"stage": "vad_windows", "reason": "unsupported_language"}) is True
    disposition, quar, ladder, guard, warn = _channel(caplog)
    assert not disposition and not quar and not ladder and len(guard) == 1
    assert guard[0].levelno == logging.INFO
    assert "outcome=held_for_redrive" in guard[0].getMessage()
    assert len(warn) == 1
    job = store.probe("jobs", "a")
    assert job["state"] == "quarantined"
    assert job["worker_failure"] == {"stage": "vad_windows", "reason": "unsupported_language"}


def test_terminal_vad_windows_outside_admitted_source_books_the_quarantined_channel(monkeypatch, caplog):
    """worker_failure=(vad_windows, outside_admitted_source) books the quarantined channel."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure={"stage": "vad_windows", "reason": "outside_admitted_source"}) is True
    disposition, quar, ladder, guard, warn = _channel(caplog)
    assert not disposition and not ladder and not guard and len(quar) == 1
    assert quar[0].levelno == logging.ERROR
    assert "reason=worker_failed" in quar[0].getMessage()
    assert "stage=vad_windows" in quar[0].getMessage()
    assert "worker_reason=outside_admitted_source" in quar[0].getMessage()
    assert len(warn) == 1
    job = store.probe("jobs", "a")
    assert job["state"] == "quarantined"
    assert job["worker_failure"] == {"stage": "vad_windows", "reason": "outside_admitted_source"}


def test_terminal_word_clocks_staged_audio_invalid_books_the_quarantined_channel(monkeypatch, caplog):
    """worker_failure=(word_clocks, staged_audio_invalid) books the quarantined channel."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure={"stage": "word_clocks", "reason": "staged_audio_invalid"}) is True
    disposition, quar, ladder, guard, warn = _channel(caplog)
    assert not disposition and not ladder and not guard and len(quar) == 1
    assert quar[0].levelno == logging.ERROR
    assert "reason=worker_failed" in quar[0].getMessage()
    assert "stage=word_clocks" in quar[0].getMessage()
    assert "worker_reason=staged_audio_invalid" in quar[0].getMessage()
    assert len(warn) == 1
    job = store.probe("jobs", "a")
    assert job["state"] == "quarantined"
    assert job["worker_failure"] == {"stage": "word_clocks", "reason": "staged_audio_invalid"}


def test_terminal_word_clocks_retained_audio_invalid_books_the_quarantined_channel(monkeypatch, caplog):
    """worker_failure=(word_clocks, retained_audio_invalid) books the quarantined channel."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure={"stage": "word_clocks", "reason": "retained_audio_invalid"}) is True
    disposition, quar, ladder, guard, warn = _channel(caplog)
    assert not disposition and not ladder and not guard and len(quar) == 1
    assert quar[0].levelno == logging.ERROR
    assert "reason=worker_failed" in quar[0].getMessage()
    assert "stage=word_clocks" in quar[0].getMessage()
    assert "worker_reason=retained_audio_invalid" in quar[0].getMessage()
    assert len(warn) == 1
    job = store.probe("jobs", "a")
    assert job["state"] == "quarantined"
    assert job["worker_failure"] == {"stage": "word_clocks", "reason": "retained_audio_invalid"}


def test_terminal_word_clocks_decoded_duration_mismatch_books_the_quarantined_channel(monkeypatch, caplog):
    """worker_failure=(word_clocks, decoded_duration_mismatch) books the quarantined channel."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure={"stage": "word_clocks", "reason": "decoded_duration_mismatch"}) is True
    disposition, quar, ladder, guard, warn = _channel(caplog)
    assert not disposition and not ladder and not guard and len(quar) == 1
    assert quar[0].levelno == logging.ERROR
    assert "reason=worker_failed" in quar[0].getMessage()
    assert "stage=word_clocks" in quar[0].getMessage()
    assert "worker_reason=decoded_duration_mismatch" in quar[0].getMessage()
    assert len(warn) == 1
    job = store.probe("jobs", "a")
    assert job["state"] == "quarantined"
    assert job["worker_failure"] == {"stage": "word_clocks", "reason": "decoded_duration_mismatch"}


def test_terminal_word_clocks_word_shape_books_the_disposition_channel(monkeypatch, caplog):
    """worker_failure=(word_clocks, word_shape) books the disposition channel."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure={"stage": "word_clocks", "reason": "word_shape"}) is True
    disposition, quar, ladder, guard, warn = _channel(caplog)
    assert not quar and not ladder and not guard and len(disposition) == 1
    assert disposition[0].levelno == logging.INFO
    assert "outcome=held_for_disposition" in disposition[0].getMessage()
    assert "stage=word_clocks" in disposition[0].getMessage()
    assert "worker_reason=word_shape" in disposition[0].getMessage()
    assert len(warn) == 1
    job = store.probe("jobs", "a")
    assert job["state"] == "quarantined"
    assert job["worker_failure"] == {"stage": "word_clocks", "reason": "word_shape"}


def test_terminal_word_clocks_word_clock_books_the_disposition_channel(monkeypatch, caplog):
    """worker_failure=(word_clocks, word_clock) books the disposition channel."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure={"stage": "word_clocks", "reason": "word_clock"}) is True
    disposition, quar, ladder, guard, warn = _channel(caplog)
    assert not quar and not ladder and not guard and len(disposition) == 1
    assert disposition[0].levelno == logging.INFO
    assert "outcome=held_for_disposition" in disposition[0].getMessage()
    assert "stage=word_clocks" in disposition[0].getMessage()
    assert "worker_reason=word_clock" in disposition[0].getMessage()
    assert len(warn) == 1
    job = store.probe("jobs", "a")
    assert job["state"] == "quarantined"
    assert job["worker_failure"] == {"stage": "word_clocks", "reason": "word_clock"}


def test_terminal_word_clocks_word_sequence_books_the_disposition_channel(monkeypatch, caplog):
    """worker_failure=(word_clocks, word_sequence) books the disposition channel."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure={"stage": "word_clocks", "reason": "word_sequence"}) is True
    disposition, quar, ladder, guard, warn = _channel(caplog)
    assert not quar and not ladder and not guard and len(disposition) == 1
    assert disposition[0].levelno == logging.INFO
    assert "outcome=held_for_disposition" in disposition[0].getMessage()
    assert "stage=word_clocks" in disposition[0].getMessage()
    assert "worker_reason=word_sequence" in disposition[0].getMessage()
    assert len(warn) == 1
    job = store.probe("jobs", "a")
    assert job["state"] == "quarantined"
    assert job["worker_failure"] == {"stage": "word_clocks", "reason": "word_sequence"}


def test_terminal_word_clocks_vad_nonfinite_books_the_disposition_channel(monkeypatch, caplog):
    """worker_failure=(word_clocks, vad_nonfinite) books the disposition channel."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure={"stage": "word_clocks", "reason": "vad_nonfinite"}) is True
    disposition, quar, ladder, guard, warn = _channel(caplog)
    assert not quar and not ladder and not guard and len(disposition) == 1
    assert disposition[0].levelno == logging.INFO
    assert "outcome=held_for_disposition" in disposition[0].getMessage()
    assert "stage=word_clocks" in disposition[0].getMessage()
    assert "worker_reason=vad_nonfinite" in disposition[0].getMessage()
    assert len(warn) == 1
    job = store.probe("jobs", "a")
    assert job["state"] == "quarantined"
    assert job["worker_failure"] == {"stage": "word_clocks", "reason": "vad_nonfinite"}


def test_terminal_word_clocks_vad_order_books_the_disposition_channel(monkeypatch, caplog):
    """worker_failure=(word_clocks, vad_order) books the disposition channel."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure={"stage": "word_clocks", "reason": "vad_order"}) is True
    disposition, quar, ladder, guard, warn = _channel(caplog)
    assert not quar and not ladder and not guard and len(disposition) == 1
    assert disposition[0].levelno == logging.INFO
    assert "outcome=held_for_disposition" in disposition[0].getMessage()
    assert "stage=word_clocks" in disposition[0].getMessage()
    assert "worker_reason=vad_order" in disposition[0].getMessage()
    assert len(warn) == 1
    job = store.probe("jobs", "a")
    assert job["state"] == "quarantined"
    assert job["worker_failure"] == {"stage": "word_clocks", "reason": "vad_order"}


def test_terminal_word_clocks_vad_bounds_books_the_disposition_channel(monkeypatch, caplog):
    """worker_failure=(word_clocks, vad_bounds) books the disposition channel."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure={"stage": "word_clocks", "reason": "vad_bounds"}) is True
    disposition, quar, ladder, guard, warn = _channel(caplog)
    assert not quar and not ladder and not guard and len(disposition) == 1
    assert disposition[0].levelno == logging.INFO
    assert "outcome=held_for_disposition" in disposition[0].getMessage()
    assert "stage=word_clocks" in disposition[0].getMessage()
    assert "worker_reason=vad_bounds" in disposition[0].getMessage()
    assert len(warn) == 1
    job = store.probe("jobs", "a")
    assert job["state"] == "quarantined"
    assert job["worker_failure"] == {"stage": "word_clocks", "reason": "vad_bounds"}


def test_terminal_word_clocks_empty_asr_books_the_quarantined_channel(monkeypatch, caplog):
    """worker_failure=(word_clocks, empty_asr) books the quarantined channel."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure={"stage": "word_clocks", "reason": "empty_asr"}) is True
    disposition, quar, ladder, guard, warn = _channel(caplog)
    assert not disposition and not ladder and not guard and len(quar) == 1
    assert quar[0].levelno == logging.ERROR
    assert "reason=worker_failed" in quar[0].getMessage()
    assert "stage=word_clocks" in quar[0].getMessage()
    assert "worker_reason=empty_asr" in quar[0].getMessage()
    assert len(warn) == 1
    job = store.probe("jobs", "a")
    assert job["state"] == "quarantined"
    assert job["worker_failure"] == {"stage": "word_clocks", "reason": "empty_asr"}


def test_terminal_word_clocks_no_owned_words_books_the_quarantined_channel(monkeypatch, caplog):
    """worker_failure=(word_clocks, no_owned_words) books the quarantined channel."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure={"stage": "word_clocks", "reason": "no_owned_words"}) is True
    disposition, quar, ladder, guard, warn = _channel(caplog)
    assert not disposition and not ladder and not guard and len(quar) == 1
    assert quar[0].levelno == logging.ERROR
    assert "reason=worker_failed" in quar[0].getMessage()
    assert "stage=word_clocks" in quar[0].getMessage()
    assert "worker_reason=no_owned_words" in quar[0].getMessage()
    assert len(warn) == 1
    job = store.probe("jobs", "a")
    assert job["state"] == "quarantined"
    assert job["worker_failure"] == {"stage": "word_clocks", "reason": "no_owned_words"}


def test_terminal_word_clocks_unsupported_language_books_the_guard_channel(monkeypatch, caplog):
    """worker_failure=(word_clocks, unsupported_language) books the guard channel."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure={"stage": "word_clocks", "reason": "unsupported_language"}) is True
    disposition, quar, ladder, guard, warn = _channel(caplog)
    assert not disposition and not quar and not ladder and len(guard) == 1
    assert guard[0].levelno == logging.INFO
    assert "outcome=held_for_redrive" in guard[0].getMessage()
    assert len(warn) == 1
    job = store.probe("jobs", "a")
    assert job["state"] == "quarantined"
    assert job["worker_failure"] == {"stage": "word_clocks", "reason": "unsupported_language"}


def test_terminal_word_clocks_outside_admitted_source_books_the_quarantined_channel(monkeypatch, caplog):
    """worker_failure=(word_clocks, outside_admitted_source) books the quarantined channel."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure={"stage": "word_clocks", "reason": "outside_admitted_source"}) is True
    disposition, quar, ladder, guard, warn = _channel(caplog)
    assert not disposition and not ladder and not guard and len(quar) == 1
    assert quar[0].levelno == logging.ERROR
    assert "reason=worker_failed" in quar[0].getMessage()
    assert "stage=word_clocks" in quar[0].getMessage()
    assert "worker_reason=outside_admitted_source" in quar[0].getMessage()
    assert len(warn) == 1
    job = store.probe("jobs", "a")
    assert job["state"] == "quarantined"
    assert job["worker_failure"] == {"stage": "word_clocks", "reason": "outside_admitted_source"}


def test_terminal_assemble_words_staged_audio_invalid_books_the_quarantined_channel(monkeypatch, caplog):
    """worker_failure=(assemble_words, staged_audio_invalid) books the quarantined channel."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure={"stage": "assemble_words", "reason": "staged_audio_invalid"}) is True
    disposition, quar, ladder, guard, warn = _channel(caplog)
    assert not disposition and not ladder and not guard and len(quar) == 1
    assert quar[0].levelno == logging.ERROR
    assert "reason=worker_failed" in quar[0].getMessage()
    assert "stage=assemble_words" in quar[0].getMessage()
    assert "worker_reason=staged_audio_invalid" in quar[0].getMessage()
    assert len(warn) == 1
    job = store.probe("jobs", "a")
    assert job["state"] == "quarantined"
    assert job["worker_failure"] == {"stage": "assemble_words", "reason": "staged_audio_invalid"}


def test_terminal_assemble_words_retained_audio_invalid_books_the_quarantined_channel(monkeypatch, caplog):
    """worker_failure=(assemble_words, retained_audio_invalid) books the quarantined channel."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure={"stage": "assemble_words", "reason": "retained_audio_invalid"}) is True
    disposition, quar, ladder, guard, warn = _channel(caplog)
    assert not disposition and not ladder and not guard and len(quar) == 1
    assert quar[0].levelno == logging.ERROR
    assert "reason=worker_failed" in quar[0].getMessage()
    assert "stage=assemble_words" in quar[0].getMessage()
    assert "worker_reason=retained_audio_invalid" in quar[0].getMessage()
    assert len(warn) == 1
    job = store.probe("jobs", "a")
    assert job["state"] == "quarantined"
    assert job["worker_failure"] == {"stage": "assemble_words", "reason": "retained_audio_invalid"}


def test_terminal_assemble_words_decoded_duration_mismatch_books_the_quarantined_channel(monkeypatch, caplog):
    """worker_failure=(assemble_words, decoded_duration_mismatch) books the quarantined channel."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued()
    assert (
        _fail(queue, lease, worker_failure={"stage": "assemble_words", "reason": "decoded_duration_mismatch"}) is True
    )
    disposition, quar, ladder, guard, warn = _channel(caplog)
    assert not disposition and not ladder and not guard and len(quar) == 1
    assert quar[0].levelno == logging.ERROR
    assert "reason=worker_failed" in quar[0].getMessage()
    assert "stage=assemble_words" in quar[0].getMessage()
    assert "worker_reason=decoded_duration_mismatch" in quar[0].getMessage()
    assert len(warn) == 1
    job = store.probe("jobs", "a")
    assert job["state"] == "quarantined"
    assert job["worker_failure"] == {"stage": "assemble_words", "reason": "decoded_duration_mismatch"}


def test_terminal_assemble_words_word_shape_books_the_disposition_channel(monkeypatch, caplog):
    """worker_failure=(assemble_words, word_shape) books the disposition channel."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure={"stage": "assemble_words", "reason": "word_shape"}) is True
    disposition, quar, ladder, guard, warn = _channel(caplog)
    assert not quar and not ladder and not guard and len(disposition) == 1
    assert disposition[0].levelno == logging.INFO
    assert "outcome=held_for_disposition" in disposition[0].getMessage()
    assert "stage=assemble_words" in disposition[0].getMessage()
    assert "worker_reason=word_shape" in disposition[0].getMessage()
    assert len(warn) == 1
    job = store.probe("jobs", "a")
    assert job["state"] == "quarantined"
    assert job["worker_failure"] == {"stage": "assemble_words", "reason": "word_shape"}


def test_terminal_assemble_words_word_clock_books_the_disposition_channel(monkeypatch, caplog):
    """worker_failure=(assemble_words, word_clock) books the disposition channel."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure={"stage": "assemble_words", "reason": "word_clock"}) is True
    disposition, quar, ladder, guard, warn = _channel(caplog)
    assert not quar and not ladder and not guard and len(disposition) == 1
    assert disposition[0].levelno == logging.INFO
    assert "outcome=held_for_disposition" in disposition[0].getMessage()
    assert "stage=assemble_words" in disposition[0].getMessage()
    assert "worker_reason=word_clock" in disposition[0].getMessage()
    assert len(warn) == 1
    job = store.probe("jobs", "a")
    assert job["state"] == "quarantined"
    assert job["worker_failure"] == {"stage": "assemble_words", "reason": "word_clock"}


def test_terminal_assemble_words_word_sequence_books_the_disposition_channel(monkeypatch, caplog):
    """worker_failure=(assemble_words, word_sequence) books the disposition channel."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure={"stage": "assemble_words", "reason": "word_sequence"}) is True
    disposition, quar, ladder, guard, warn = _channel(caplog)
    assert not quar and not ladder and not guard and len(disposition) == 1
    assert disposition[0].levelno == logging.INFO
    assert "outcome=held_for_disposition" in disposition[0].getMessage()
    assert "stage=assemble_words" in disposition[0].getMessage()
    assert "worker_reason=word_sequence" in disposition[0].getMessage()
    assert len(warn) == 1
    job = store.probe("jobs", "a")
    assert job["state"] == "quarantined"
    assert job["worker_failure"] == {"stage": "assemble_words", "reason": "word_sequence"}


def test_terminal_assemble_words_vad_nonfinite_books_the_disposition_channel(monkeypatch, caplog):
    """worker_failure=(assemble_words, vad_nonfinite) books the disposition channel."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure={"stage": "assemble_words", "reason": "vad_nonfinite"}) is True
    disposition, quar, ladder, guard, warn = _channel(caplog)
    assert not quar and not ladder and not guard and len(disposition) == 1
    assert disposition[0].levelno == logging.INFO
    assert "outcome=held_for_disposition" in disposition[0].getMessage()
    assert "stage=assemble_words" in disposition[0].getMessage()
    assert "worker_reason=vad_nonfinite" in disposition[0].getMessage()
    assert len(warn) == 1
    job = store.probe("jobs", "a")
    assert job["state"] == "quarantined"
    assert job["worker_failure"] == {"stage": "assemble_words", "reason": "vad_nonfinite"}


def test_terminal_assemble_words_vad_order_books_the_disposition_channel(monkeypatch, caplog):
    """worker_failure=(assemble_words, vad_order) books the disposition channel."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure={"stage": "assemble_words", "reason": "vad_order"}) is True
    disposition, quar, ladder, guard, warn = _channel(caplog)
    assert not quar and not ladder and not guard and len(disposition) == 1
    assert disposition[0].levelno == logging.INFO
    assert "outcome=held_for_disposition" in disposition[0].getMessage()
    assert "stage=assemble_words" in disposition[0].getMessage()
    assert "worker_reason=vad_order" in disposition[0].getMessage()
    assert len(warn) == 1
    job = store.probe("jobs", "a")
    assert job["state"] == "quarantined"
    assert job["worker_failure"] == {"stage": "assemble_words", "reason": "vad_order"}


def test_terminal_assemble_words_vad_bounds_books_the_disposition_channel(monkeypatch, caplog):
    """worker_failure=(assemble_words, vad_bounds) books the disposition channel."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure={"stage": "assemble_words", "reason": "vad_bounds"}) is True
    disposition, quar, ladder, guard, warn = _channel(caplog)
    assert not quar and not ladder and not guard and len(disposition) == 1
    assert disposition[0].levelno == logging.INFO
    assert "outcome=held_for_disposition" in disposition[0].getMessage()
    assert "stage=assemble_words" in disposition[0].getMessage()
    assert "worker_reason=vad_bounds" in disposition[0].getMessage()
    assert len(warn) == 1
    job = store.probe("jobs", "a")
    assert job["state"] == "quarantined"
    assert job["worker_failure"] == {"stage": "assemble_words", "reason": "vad_bounds"}


def test_terminal_assemble_words_empty_asr_books_the_ladder_channel(monkeypatch, caplog):
    """worker_failure=(assemble_words, empty_asr) books the ladder channel."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure={"stage": "assemble_words", "reason": "empty_asr"}) is True
    disposition, quar, ladder, guard, warn = _channel(caplog)
    assert not disposition and not quar and not guard and len(ladder) == 1
    assert ladder[0].levelno == logging.INFO
    assert "outcome=held_for_recovery" in ladder[0].getMessage()
    assert len(warn) == 1
    job = store.probe("jobs", "a")
    assert job["state"] == "quarantined"
    assert job["worker_failure"] == {"stage": "assemble_words", "reason": "empty_asr"}


def test_terminal_assemble_words_no_owned_words_books_the_ladder_channel(monkeypatch, caplog):
    """worker_failure=(assemble_words, no_owned_words) books the ladder channel."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure={"stage": "assemble_words", "reason": "no_owned_words"}) is True
    disposition, quar, ladder, guard, warn = _channel(caplog)
    assert not disposition and not quar and not guard and len(ladder) == 1
    assert ladder[0].levelno == logging.INFO
    assert "outcome=held_for_recovery" in ladder[0].getMessage()
    assert len(warn) == 1
    job = store.probe("jobs", "a")
    assert job["state"] == "quarantined"
    assert job["worker_failure"] == {"stage": "assemble_words", "reason": "no_owned_words"}


def test_terminal_assemble_words_unsupported_language_books_the_guard_channel(monkeypatch, caplog):
    """worker_failure=(assemble_words, unsupported_language) books the guard channel."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure={"stage": "assemble_words", "reason": "unsupported_language"}) is True
    disposition, quar, ladder, guard, warn = _channel(caplog)
    assert not disposition and not quar and not ladder and len(guard) == 1
    assert guard[0].levelno == logging.INFO
    assert "outcome=held_for_redrive" in guard[0].getMessage()
    assert len(warn) == 1
    job = store.probe("jobs", "a")
    assert job["state"] == "quarantined"
    assert job["worker_failure"] == {"stage": "assemble_words", "reason": "unsupported_language"}


def test_terminal_assemble_words_outside_admitted_source_books_the_quarantined_channel(monkeypatch, caplog):
    """worker_failure=(assemble_words, outside_admitted_source) books the quarantined channel."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure={"stage": "assemble_words", "reason": "outside_admitted_source"}) is True
    disposition, quar, ladder, guard, warn = _channel(caplog)
    assert not disposition and not ladder and not guard and len(quar) == 1
    assert quar[0].levelno == logging.ERROR
    assert "reason=worker_failed" in quar[0].getMessage()
    assert "stage=assemble_words" in quar[0].getMessage()
    assert "worker_reason=outside_admitted_source" in quar[0].getMessage()
    assert len(warn) == 1
    job = store.probe("jobs", "a")
    assert job["state"] == "quarantined"
    assert job["worker_failure"] == {"stage": "assemble_words", "reason": "outside_admitted_source"}


def test_terminal_asr_recovery_staged_audio_invalid_books_the_quarantined_channel(monkeypatch, caplog):
    """worker_failure=(asr_recovery, staged_audio_invalid) books the quarantined channel."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure={"stage": "asr_recovery", "reason": "staged_audio_invalid"}) is True
    disposition, quar, ladder, guard, warn = _channel(caplog)
    assert not disposition and not ladder and not guard and len(quar) == 1
    assert quar[0].levelno == logging.ERROR
    assert "reason=worker_failed" in quar[0].getMessage()
    assert "stage=asr_recovery" in quar[0].getMessage()
    assert "worker_reason=staged_audio_invalid" in quar[0].getMessage()
    assert len(warn) == 1
    job = store.probe("jobs", "a")
    assert job["state"] == "quarantined"
    assert job["worker_failure"] == {"stage": "asr_recovery", "reason": "staged_audio_invalid"}


def test_terminal_asr_recovery_retained_audio_invalid_books_the_quarantined_channel(monkeypatch, caplog):
    """worker_failure=(asr_recovery, retained_audio_invalid) books the quarantined channel."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure={"stage": "asr_recovery", "reason": "retained_audio_invalid"}) is True
    disposition, quar, ladder, guard, warn = _channel(caplog)
    assert not disposition and not ladder and not guard and len(quar) == 1
    assert quar[0].levelno == logging.ERROR
    assert "reason=worker_failed" in quar[0].getMessage()
    assert "stage=asr_recovery" in quar[0].getMessage()
    assert "worker_reason=retained_audio_invalid" in quar[0].getMessage()
    assert len(warn) == 1
    job = store.probe("jobs", "a")
    assert job["state"] == "quarantined"
    assert job["worker_failure"] == {"stage": "asr_recovery", "reason": "retained_audio_invalid"}


def test_terminal_asr_recovery_decoded_duration_mismatch_books_the_quarantined_channel(monkeypatch, caplog):
    """worker_failure=(asr_recovery, decoded_duration_mismatch) books the quarantined channel."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure={"stage": "asr_recovery", "reason": "decoded_duration_mismatch"}) is True
    disposition, quar, ladder, guard, warn = _channel(caplog)
    assert not disposition and not ladder and not guard and len(quar) == 1
    assert quar[0].levelno == logging.ERROR
    assert "reason=worker_failed" in quar[0].getMessage()
    assert "stage=asr_recovery" in quar[0].getMessage()
    assert "worker_reason=decoded_duration_mismatch" in quar[0].getMessage()
    assert len(warn) == 1
    job = store.probe("jobs", "a")
    assert job["state"] == "quarantined"
    assert job["worker_failure"] == {"stage": "asr_recovery", "reason": "decoded_duration_mismatch"}


def test_terminal_asr_recovery_word_shape_books_the_disposition_channel(monkeypatch, caplog):
    """worker_failure=(asr_recovery, word_shape) books the disposition channel."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure={"stage": "asr_recovery", "reason": "word_shape"}) is True
    disposition, quar, ladder, guard, warn = _channel(caplog)
    assert not quar and not ladder and not guard and len(disposition) == 1
    assert disposition[0].levelno == logging.INFO
    assert "outcome=held_for_disposition" in disposition[0].getMessage()
    assert "stage=asr_recovery" in disposition[0].getMessage()
    assert "worker_reason=word_shape" in disposition[0].getMessage()
    assert len(warn) == 1
    job = store.probe("jobs", "a")
    assert job["state"] == "quarantined"
    assert job["worker_failure"] == {"stage": "asr_recovery", "reason": "word_shape"}


def test_terminal_asr_recovery_word_clock_books_the_disposition_channel(monkeypatch, caplog):
    """worker_failure=(asr_recovery, word_clock) books the disposition channel."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure={"stage": "asr_recovery", "reason": "word_clock"}) is True
    disposition, quar, ladder, guard, warn = _channel(caplog)
    assert not quar and not ladder and not guard and len(disposition) == 1
    assert disposition[0].levelno == logging.INFO
    assert "outcome=held_for_disposition" in disposition[0].getMessage()
    assert "stage=asr_recovery" in disposition[0].getMessage()
    assert "worker_reason=word_clock" in disposition[0].getMessage()
    assert len(warn) == 1
    job = store.probe("jobs", "a")
    assert job["state"] == "quarantined"
    assert job["worker_failure"] == {"stage": "asr_recovery", "reason": "word_clock"}


def test_terminal_asr_recovery_word_sequence_books_the_disposition_channel(monkeypatch, caplog):
    """worker_failure=(asr_recovery, word_sequence) books the disposition channel."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure={"stage": "asr_recovery", "reason": "word_sequence"}) is True
    disposition, quar, ladder, guard, warn = _channel(caplog)
    assert not quar and not ladder and not guard and len(disposition) == 1
    assert disposition[0].levelno == logging.INFO
    assert "outcome=held_for_disposition" in disposition[0].getMessage()
    assert "stage=asr_recovery" in disposition[0].getMessage()
    assert "worker_reason=word_sequence" in disposition[0].getMessage()
    assert len(warn) == 1
    job = store.probe("jobs", "a")
    assert job["state"] == "quarantined"
    assert job["worker_failure"] == {"stage": "asr_recovery", "reason": "word_sequence"}


def test_terminal_asr_recovery_vad_nonfinite_books_the_disposition_channel(monkeypatch, caplog):
    """worker_failure=(asr_recovery, vad_nonfinite) books the disposition channel."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure={"stage": "asr_recovery", "reason": "vad_nonfinite"}) is True
    disposition, quar, ladder, guard, warn = _channel(caplog)
    assert not quar and not ladder and not guard and len(disposition) == 1
    assert disposition[0].levelno == logging.INFO
    assert "outcome=held_for_disposition" in disposition[0].getMessage()
    assert "stage=asr_recovery" in disposition[0].getMessage()
    assert "worker_reason=vad_nonfinite" in disposition[0].getMessage()
    assert len(warn) == 1
    job = store.probe("jobs", "a")
    assert job["state"] == "quarantined"
    assert job["worker_failure"] == {"stage": "asr_recovery", "reason": "vad_nonfinite"}


def test_terminal_asr_recovery_vad_order_books_the_disposition_channel(monkeypatch, caplog):
    """worker_failure=(asr_recovery, vad_order) books the disposition channel."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure={"stage": "asr_recovery", "reason": "vad_order"}) is True
    disposition, quar, ladder, guard, warn = _channel(caplog)
    assert not quar and not ladder and not guard and len(disposition) == 1
    assert disposition[0].levelno == logging.INFO
    assert "outcome=held_for_disposition" in disposition[0].getMessage()
    assert "stage=asr_recovery" in disposition[0].getMessage()
    assert "worker_reason=vad_order" in disposition[0].getMessage()
    assert len(warn) == 1
    job = store.probe("jobs", "a")
    assert job["state"] == "quarantined"
    assert job["worker_failure"] == {"stage": "asr_recovery", "reason": "vad_order"}


def test_terminal_asr_recovery_vad_bounds_books_the_disposition_channel(monkeypatch, caplog):
    """worker_failure=(asr_recovery, vad_bounds) books the disposition channel."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure={"stage": "asr_recovery", "reason": "vad_bounds"}) is True
    disposition, quar, ladder, guard, warn = _channel(caplog)
    assert not quar and not ladder and not guard and len(disposition) == 1
    assert disposition[0].levelno == logging.INFO
    assert "outcome=held_for_disposition" in disposition[0].getMessage()
    assert "stage=asr_recovery" in disposition[0].getMessage()
    assert "worker_reason=vad_bounds" in disposition[0].getMessage()
    assert len(warn) == 1
    job = store.probe("jobs", "a")
    assert job["state"] == "quarantined"
    assert job["worker_failure"] == {"stage": "asr_recovery", "reason": "vad_bounds"}


def test_terminal_asr_recovery_empty_asr_books_the_quarantined_channel(monkeypatch, caplog):
    """worker_failure=(asr_recovery, empty_asr) books the quarantined channel."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure={"stage": "asr_recovery", "reason": "empty_asr"}) is True
    disposition, quar, ladder, guard, warn = _channel(caplog)
    assert not disposition and not ladder and not guard and len(quar) == 1
    assert quar[0].levelno == logging.ERROR
    assert "reason=worker_failed" in quar[0].getMessage()
    assert "stage=asr_recovery" in quar[0].getMessage()
    assert "worker_reason=empty_asr" in quar[0].getMessage()
    assert len(warn) == 1
    job = store.probe("jobs", "a")
    assert job["state"] == "quarantined"
    assert job["worker_failure"] == {"stage": "asr_recovery", "reason": "empty_asr"}


def test_terminal_asr_recovery_no_owned_words_books_the_quarantined_channel(monkeypatch, caplog):
    """worker_failure=(asr_recovery, no_owned_words) books the quarantined channel."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure={"stage": "asr_recovery", "reason": "no_owned_words"}) is True
    disposition, quar, ladder, guard, warn = _channel(caplog)
    assert not disposition and not ladder and not guard and len(quar) == 1
    assert quar[0].levelno == logging.ERROR
    assert "reason=worker_failed" in quar[0].getMessage()
    assert "stage=asr_recovery" in quar[0].getMessage()
    assert "worker_reason=no_owned_words" in quar[0].getMessage()
    assert len(warn) == 1
    job = store.probe("jobs", "a")
    assert job["state"] == "quarantined"
    assert job["worker_failure"] == {"stage": "asr_recovery", "reason": "no_owned_words"}


def test_terminal_asr_recovery_unsupported_language_books_the_guard_channel(monkeypatch, caplog):
    """worker_failure=(asr_recovery, unsupported_language) books the guard channel."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure={"stage": "asr_recovery", "reason": "unsupported_language"}) is True
    disposition, quar, ladder, guard, warn = _channel(caplog)
    assert not disposition and not quar and not ladder and len(guard) == 1
    assert guard[0].levelno == logging.INFO
    assert "outcome=held_for_redrive" in guard[0].getMessage()
    assert len(warn) == 1
    job = store.probe("jobs", "a")
    assert job["state"] == "quarantined"
    assert job["worker_failure"] == {"stage": "asr_recovery", "reason": "unsupported_language"}


def test_terminal_asr_recovery_outside_admitted_source_books_the_quarantined_channel(monkeypatch, caplog):
    """worker_failure=(asr_recovery, outside_admitted_source) books the quarantined channel."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure={"stage": "asr_recovery", "reason": "outside_admitted_source"}) is True
    disposition, quar, ladder, guard, warn = _channel(caplog)
    assert not disposition and not ladder and not guard and len(quar) == 1
    assert quar[0].levelno == logging.ERROR
    assert "reason=worker_failed" in quar[0].getMessage()
    assert "stage=asr_recovery" in quar[0].getMessage()
    assert "worker_reason=outside_admitted_source" in quar[0].getMessage()
    assert len(warn) == 1
    job = store.probe("jobs", "a")
    assert job["state"] == "quarantined"
    assert job["worker_failure"] == {"stage": "asr_recovery", "reason": "outside_admitted_source"}


def test_terminal_fetch_decode_staged_audio_invalid_durable_state_and_metrics_parity(monkeypatch):
    """worker_failure=(fetch_decode, staged_audio_invalid): quarantine state, evidence booking and metrics are unchanged."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    metrics = Mock()
    store, queue, lease = _queued(metrics=metrics)
    assert _fail(queue, lease, worker_failure={"stage": "fetch_decode", "reason": "staged_audio_invalid"}) is True
    job = store.rows["jobs", "a"]
    assert job["state"] == "quarantined" and job["attempt"] == 1
    assert job["recovery_state"] == "held" and not job["merge_pending"]
    assert job["worker_failure"] == {"stage": "fetch_decode", "reason": "staged_audio_invalid"}
    recorded = [call.args[0] for call in metrics.record.call_args_list]
    assert "quarantined" in recorded and "recovery_held" in recorded


def test_terminal_fetch_decode_retained_audio_invalid_durable_state_and_metrics_parity(monkeypatch):
    """worker_failure=(fetch_decode, retained_audio_invalid): quarantine state, evidence booking and metrics are unchanged."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    metrics = Mock()
    store, queue, lease = _queued(metrics=metrics)
    assert _fail(queue, lease, worker_failure={"stage": "fetch_decode", "reason": "retained_audio_invalid"}) is True
    job = store.rows["jobs", "a"]
    assert job["state"] == "quarantined" and job["attempt"] == 1
    assert job["recovery_state"] == "held" and not job["merge_pending"]
    assert job["worker_failure"] == {"stage": "fetch_decode", "reason": "retained_audio_invalid"}
    recorded = [call.args[0] for call in metrics.record.call_args_list]
    assert "quarantined" in recorded and "recovery_held" in recorded


def test_terminal_fetch_decode_decoded_duration_mismatch_durable_state_and_metrics_parity(monkeypatch):
    """worker_failure=(fetch_decode, decoded_duration_mismatch): quarantine state, evidence booking and metrics are unchanged."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    metrics = Mock()
    store, queue, lease = _queued(metrics=metrics)
    assert _fail(queue, lease, worker_failure={"stage": "fetch_decode", "reason": "decoded_duration_mismatch"}) is True
    job = store.rows["jobs", "a"]
    assert job["state"] == "quarantined" and job["attempt"] == 1
    assert job["recovery_state"] == "held" and not job["merge_pending"]
    assert job["worker_failure"] == {"stage": "fetch_decode", "reason": "decoded_duration_mismatch"}
    recorded = [call.args[0] for call in metrics.record.call_args_list]
    assert "quarantined" in recorded and "recovery_held" in recorded


def test_terminal_fetch_decode_word_shape_durable_state_and_metrics_parity(monkeypatch):
    """worker_failure=(fetch_decode, word_shape): quarantine state, evidence booking and metrics are unchanged."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    metrics = Mock()
    store, queue, lease = _queued(metrics=metrics)
    assert _fail(queue, lease, worker_failure={"stage": "fetch_decode", "reason": "word_shape"}) is True
    job = store.rows["jobs", "a"]
    assert job["state"] == "quarantined" and job["attempt"] == 1
    assert job["recovery_state"] == "held" and not job["merge_pending"]
    assert job["worker_failure"] == {"stage": "fetch_decode", "reason": "word_shape"}
    recorded = [call.args[0] for call in metrics.record.call_args_list]
    assert "quarantined" in recorded and "recovery_held" in recorded


def test_terminal_fetch_decode_word_clock_durable_state_and_metrics_parity(monkeypatch):
    """worker_failure=(fetch_decode, word_clock): quarantine state, evidence booking and metrics are unchanged."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    metrics = Mock()
    store, queue, lease = _queued(metrics=metrics)
    assert _fail(queue, lease, worker_failure={"stage": "fetch_decode", "reason": "word_clock"}) is True
    job = store.rows["jobs", "a"]
    assert job["state"] == "quarantined" and job["attempt"] == 1
    assert job["recovery_state"] == "held" and not job["merge_pending"]
    assert job["worker_failure"] == {"stage": "fetch_decode", "reason": "word_clock"}
    recorded = [call.args[0] for call in metrics.record.call_args_list]
    assert "quarantined" in recorded and "recovery_held" in recorded


def test_terminal_fetch_decode_word_sequence_durable_state_and_metrics_parity(monkeypatch):
    """worker_failure=(fetch_decode, word_sequence): quarantine state, evidence booking and metrics are unchanged."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    metrics = Mock()
    store, queue, lease = _queued(metrics=metrics)
    assert _fail(queue, lease, worker_failure={"stage": "fetch_decode", "reason": "word_sequence"}) is True
    job = store.rows["jobs", "a"]
    assert job["state"] == "quarantined" and job["attempt"] == 1
    assert job["recovery_state"] == "held" and not job["merge_pending"]
    assert job["worker_failure"] == {"stage": "fetch_decode", "reason": "word_sequence"}
    recorded = [call.args[0] for call in metrics.record.call_args_list]
    assert "quarantined" in recorded and "recovery_held" in recorded


def test_terminal_fetch_decode_vad_nonfinite_durable_state_and_metrics_parity(monkeypatch):
    """worker_failure=(fetch_decode, vad_nonfinite): quarantine state, evidence booking and metrics are unchanged."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    metrics = Mock()
    store, queue, lease = _queued(metrics=metrics)
    assert _fail(queue, lease, worker_failure={"stage": "fetch_decode", "reason": "vad_nonfinite"}) is True
    job = store.rows["jobs", "a"]
    assert job["state"] == "quarantined" and job["attempt"] == 1
    assert job["recovery_state"] == "held" and not job["merge_pending"]
    assert job["worker_failure"] == {"stage": "fetch_decode", "reason": "vad_nonfinite"}
    recorded = [call.args[0] for call in metrics.record.call_args_list]
    assert "quarantined" in recorded and "recovery_held" in recorded


def test_terminal_fetch_decode_vad_order_durable_state_and_metrics_parity(monkeypatch):
    """worker_failure=(fetch_decode, vad_order): quarantine state, evidence booking and metrics are unchanged."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    metrics = Mock()
    store, queue, lease = _queued(metrics=metrics)
    assert _fail(queue, lease, worker_failure={"stage": "fetch_decode", "reason": "vad_order"}) is True
    job = store.rows["jobs", "a"]
    assert job["state"] == "quarantined" and job["attempt"] == 1
    assert job["recovery_state"] == "held" and not job["merge_pending"]
    assert job["worker_failure"] == {"stage": "fetch_decode", "reason": "vad_order"}
    recorded = [call.args[0] for call in metrics.record.call_args_list]
    assert "quarantined" in recorded and "recovery_held" in recorded


def test_terminal_fetch_decode_vad_bounds_durable_state_and_metrics_parity(monkeypatch):
    """worker_failure=(fetch_decode, vad_bounds): quarantine state, evidence booking and metrics are unchanged."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    metrics = Mock()
    store, queue, lease = _queued(metrics=metrics)
    assert _fail(queue, lease, worker_failure={"stage": "fetch_decode", "reason": "vad_bounds"}) is True
    job = store.rows["jobs", "a"]
    assert job["state"] == "quarantined" and job["attempt"] == 1
    assert job["recovery_state"] == "held" and not job["merge_pending"]
    assert job["worker_failure"] == {"stage": "fetch_decode", "reason": "vad_bounds"}
    recorded = [call.args[0] for call in metrics.record.call_args_list]
    assert "quarantined" in recorded and "recovery_held" in recorded


def test_terminal_fetch_decode_empty_asr_durable_state_and_metrics_parity(monkeypatch):
    """worker_failure=(fetch_decode, empty_asr): quarantine state, evidence booking and metrics are unchanged."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    metrics = Mock()
    store, queue, lease = _queued(metrics=metrics)
    assert _fail(queue, lease, worker_failure={"stage": "fetch_decode", "reason": "empty_asr"}) is True
    job = store.rows["jobs", "a"]
    assert job["state"] == "quarantined" and job["attempt"] == 1
    assert job["recovery_state"] == "held" and not job["merge_pending"]
    assert job["worker_failure"] == {"stage": "fetch_decode", "reason": "empty_asr"}
    recorded = [call.args[0] for call in metrics.record.call_args_list]
    assert "quarantined" in recorded and "recovery_held" in recorded


def test_terminal_fetch_decode_no_owned_words_durable_state_and_metrics_parity(monkeypatch):
    """worker_failure=(fetch_decode, no_owned_words): quarantine state, evidence booking and metrics are unchanged."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    metrics = Mock()
    store, queue, lease = _queued(metrics=metrics)
    assert _fail(queue, lease, worker_failure={"stage": "fetch_decode", "reason": "no_owned_words"}) is True
    job = store.rows["jobs", "a"]
    assert job["state"] == "quarantined" and job["attempt"] == 1
    assert job["recovery_state"] == "held" and not job["merge_pending"]
    assert job["worker_failure"] == {"stage": "fetch_decode", "reason": "no_owned_words"}
    recorded = [call.args[0] for call in metrics.record.call_args_list]
    assert "quarantined" in recorded and "recovery_held" in recorded


def test_terminal_fetch_decode_unsupported_language_durable_state_and_metrics_parity(monkeypatch):
    """worker_failure=(fetch_decode, unsupported_language): quarantine state, evidence booking and metrics are unchanged."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    metrics = Mock()
    store, queue, lease = _queued(metrics=metrics)
    assert _fail(queue, lease, worker_failure={"stage": "fetch_decode", "reason": "unsupported_language"}) is True
    job = store.rows["jobs", "a"]
    assert job["state"] == "quarantined" and job["attempt"] == 1
    assert job["recovery_state"] == "held" and not job["merge_pending"]
    assert job["worker_failure"] == {"stage": "fetch_decode", "reason": "unsupported_language"}
    recorded = [call.args[0] for call in metrics.record.call_args_list]
    assert "quarantined" in recorded and "recovery_held" in recorded


def test_terminal_fetch_decode_outside_admitted_source_durable_state_and_metrics_parity(monkeypatch):
    """worker_failure=(fetch_decode, outside_admitted_source): quarantine state, evidence booking and metrics are unchanged."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    metrics = Mock()
    store, queue, lease = _queued(metrics=metrics)
    assert _fail(queue, lease, worker_failure={"stage": "fetch_decode", "reason": "outside_admitted_source"}) is True
    job = store.rows["jobs", "a"]
    assert job["state"] == "quarantined" and job["attempt"] == 1
    assert job["recovery_state"] == "held" and not job["merge_pending"]
    assert job["worker_failure"] == {"stage": "fetch_decode", "reason": "outside_admitted_source"}
    recorded = [call.args[0] for call in metrics.record.call_args_list]
    assert "quarantined" in recorded and "recovery_held" in recorded


def test_terminal_vad_windows_staged_audio_invalid_durable_state_and_metrics_parity(monkeypatch):
    """worker_failure=(vad_windows, staged_audio_invalid): quarantine state, evidence booking and metrics are unchanged."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    metrics = Mock()
    store, queue, lease = _queued(metrics=metrics)
    assert _fail(queue, lease, worker_failure={"stage": "vad_windows", "reason": "staged_audio_invalid"}) is True
    job = store.rows["jobs", "a"]
    assert job["state"] == "quarantined" and job["attempt"] == 1
    assert job["recovery_state"] == "held" and not job["merge_pending"]
    assert job["worker_failure"] == {"stage": "vad_windows", "reason": "staged_audio_invalid"}
    recorded = [call.args[0] for call in metrics.record.call_args_list]
    assert "quarantined" in recorded and "recovery_held" in recorded


def test_terminal_vad_windows_retained_audio_invalid_durable_state_and_metrics_parity(monkeypatch):
    """worker_failure=(vad_windows, retained_audio_invalid): quarantine state, evidence booking and metrics are unchanged."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    metrics = Mock()
    store, queue, lease = _queued(metrics=metrics)
    assert _fail(queue, lease, worker_failure={"stage": "vad_windows", "reason": "retained_audio_invalid"}) is True
    job = store.rows["jobs", "a"]
    assert job["state"] == "quarantined" and job["attempt"] == 1
    assert job["recovery_state"] == "held" and not job["merge_pending"]
    assert job["worker_failure"] == {"stage": "vad_windows", "reason": "retained_audio_invalid"}
    recorded = [call.args[0] for call in metrics.record.call_args_list]
    assert "quarantined" in recorded and "recovery_held" in recorded


def test_terminal_vad_windows_decoded_duration_mismatch_durable_state_and_metrics_parity(monkeypatch):
    """worker_failure=(vad_windows, decoded_duration_mismatch): quarantine state, evidence booking and metrics are unchanged."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    metrics = Mock()
    store, queue, lease = _queued(metrics=metrics)
    assert _fail(queue, lease, worker_failure={"stage": "vad_windows", "reason": "decoded_duration_mismatch"}) is True
    job = store.rows["jobs", "a"]
    assert job["state"] == "quarantined" and job["attempt"] == 1
    assert job["recovery_state"] == "held" and not job["merge_pending"]
    assert job["worker_failure"] == {"stage": "vad_windows", "reason": "decoded_duration_mismatch"}
    recorded = [call.args[0] for call in metrics.record.call_args_list]
    assert "quarantined" in recorded and "recovery_held" in recorded


def test_terminal_vad_windows_word_shape_durable_state_and_metrics_parity(monkeypatch):
    """worker_failure=(vad_windows, word_shape): quarantine state, evidence booking and metrics are unchanged."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    metrics = Mock()
    store, queue, lease = _queued(metrics=metrics)
    assert _fail(queue, lease, worker_failure={"stage": "vad_windows", "reason": "word_shape"}) is True
    job = store.rows["jobs", "a"]
    assert job["state"] == "quarantined" and job["attempt"] == 1
    assert job["recovery_state"] == "held" and not job["merge_pending"]
    assert job["worker_failure"] == {"stage": "vad_windows", "reason": "word_shape"}
    recorded = [call.args[0] for call in metrics.record.call_args_list]
    assert "quarantined" in recorded and "recovery_held" in recorded


def test_terminal_vad_windows_word_clock_durable_state_and_metrics_parity(monkeypatch):
    """worker_failure=(vad_windows, word_clock): quarantine state, evidence booking and metrics are unchanged."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    metrics = Mock()
    store, queue, lease = _queued(metrics=metrics)
    assert _fail(queue, lease, worker_failure={"stage": "vad_windows", "reason": "word_clock"}) is True
    job = store.rows["jobs", "a"]
    assert job["state"] == "quarantined" and job["attempt"] == 1
    assert job["recovery_state"] == "held" and not job["merge_pending"]
    assert job["worker_failure"] == {"stage": "vad_windows", "reason": "word_clock"}
    recorded = [call.args[0] for call in metrics.record.call_args_list]
    assert "quarantined" in recorded and "recovery_held" in recorded


def test_terminal_vad_windows_word_sequence_durable_state_and_metrics_parity(monkeypatch):
    """worker_failure=(vad_windows, word_sequence): quarantine state, evidence booking and metrics are unchanged."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    metrics = Mock()
    store, queue, lease = _queued(metrics=metrics)
    assert _fail(queue, lease, worker_failure={"stage": "vad_windows", "reason": "word_sequence"}) is True
    job = store.rows["jobs", "a"]
    assert job["state"] == "quarantined" and job["attempt"] == 1
    assert job["recovery_state"] == "held" and not job["merge_pending"]
    assert job["worker_failure"] == {"stage": "vad_windows", "reason": "word_sequence"}
    recorded = [call.args[0] for call in metrics.record.call_args_list]
    assert "quarantined" in recorded and "recovery_held" in recorded


def test_terminal_vad_windows_vad_nonfinite_durable_state_and_metrics_parity(monkeypatch):
    """worker_failure=(vad_windows, vad_nonfinite): quarantine state, evidence booking and metrics are unchanged."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    metrics = Mock()
    store, queue, lease = _queued(metrics=metrics)
    assert _fail(queue, lease, worker_failure={"stage": "vad_windows", "reason": "vad_nonfinite"}) is True
    job = store.rows["jobs", "a"]
    assert job["state"] == "quarantined" and job["attempt"] == 1
    assert job["recovery_state"] == "held" and not job["merge_pending"]
    assert job["worker_failure"] == {"stage": "vad_windows", "reason": "vad_nonfinite"}
    recorded = [call.args[0] for call in metrics.record.call_args_list]
    assert "quarantined" in recorded and "recovery_held" in recorded


def test_terminal_vad_windows_vad_order_durable_state_and_metrics_parity(monkeypatch):
    """worker_failure=(vad_windows, vad_order): quarantine state, evidence booking and metrics are unchanged."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    metrics = Mock()
    store, queue, lease = _queued(metrics=metrics)
    assert _fail(queue, lease, worker_failure={"stage": "vad_windows", "reason": "vad_order"}) is True
    job = store.rows["jobs", "a"]
    assert job["state"] == "quarantined" and job["attempt"] == 1
    assert job["recovery_state"] == "held" and not job["merge_pending"]
    assert job["worker_failure"] == {"stage": "vad_windows", "reason": "vad_order"}
    recorded = [call.args[0] for call in metrics.record.call_args_list]
    assert "quarantined" in recorded and "recovery_held" in recorded


def test_terminal_vad_windows_vad_bounds_durable_state_and_metrics_parity(monkeypatch):
    """worker_failure=(vad_windows, vad_bounds): quarantine state, evidence booking and metrics are unchanged."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    metrics = Mock()
    store, queue, lease = _queued(metrics=metrics)
    assert _fail(queue, lease, worker_failure={"stage": "vad_windows", "reason": "vad_bounds"}) is True
    job = store.rows["jobs", "a"]
    assert job["state"] == "quarantined" and job["attempt"] == 1
    assert job["recovery_state"] == "held" and not job["merge_pending"]
    assert job["worker_failure"] == {"stage": "vad_windows", "reason": "vad_bounds"}
    recorded = [call.args[0] for call in metrics.record.call_args_list]
    assert "quarantined" in recorded and "recovery_held" in recorded


def test_terminal_vad_windows_empty_asr_durable_state_and_metrics_parity(monkeypatch):
    """worker_failure=(vad_windows, empty_asr): quarantine state, evidence booking and metrics are unchanged."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    metrics = Mock()
    store, queue, lease = _queued(metrics=metrics)
    assert _fail(queue, lease, worker_failure={"stage": "vad_windows", "reason": "empty_asr"}) is True
    job = store.rows["jobs", "a"]
    assert job["state"] == "quarantined" and job["attempt"] == 1
    assert job["recovery_state"] == "held" and not job["merge_pending"]
    assert job["worker_failure"] == {"stage": "vad_windows", "reason": "empty_asr"}
    recorded = [call.args[0] for call in metrics.record.call_args_list]
    assert "quarantined" in recorded and "recovery_held" in recorded


def test_terminal_vad_windows_no_owned_words_durable_state_and_metrics_parity(monkeypatch):
    """worker_failure=(vad_windows, no_owned_words): quarantine state, evidence booking and metrics are unchanged."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    metrics = Mock()
    store, queue, lease = _queued(metrics=metrics)
    assert _fail(queue, lease, worker_failure={"stage": "vad_windows", "reason": "no_owned_words"}) is True
    job = store.rows["jobs", "a"]
    assert job["state"] == "quarantined" and job["attempt"] == 1
    assert job["recovery_state"] == "held" and not job["merge_pending"]
    assert job["worker_failure"] == {"stage": "vad_windows", "reason": "no_owned_words"}
    recorded = [call.args[0] for call in metrics.record.call_args_list]
    assert "quarantined" in recorded and "recovery_held" in recorded


def test_terminal_vad_windows_unsupported_language_durable_state_and_metrics_parity(monkeypatch):
    """worker_failure=(vad_windows, unsupported_language): quarantine state, evidence booking and metrics are unchanged."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    metrics = Mock()
    store, queue, lease = _queued(metrics=metrics)
    assert _fail(queue, lease, worker_failure={"stage": "vad_windows", "reason": "unsupported_language"}) is True
    job = store.rows["jobs", "a"]
    assert job["state"] == "quarantined" and job["attempt"] == 1
    assert job["recovery_state"] == "held" and not job["merge_pending"]
    assert job["worker_failure"] == {"stage": "vad_windows", "reason": "unsupported_language"}
    recorded = [call.args[0] for call in metrics.record.call_args_list]
    assert "quarantined" in recorded and "recovery_held" in recorded


def test_terminal_vad_windows_outside_admitted_source_durable_state_and_metrics_parity(monkeypatch):
    """worker_failure=(vad_windows, outside_admitted_source): quarantine state, evidence booking and metrics are unchanged."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    metrics = Mock()
    store, queue, lease = _queued(metrics=metrics)
    assert _fail(queue, lease, worker_failure={"stage": "vad_windows", "reason": "outside_admitted_source"}) is True
    job = store.rows["jobs", "a"]
    assert job["state"] == "quarantined" and job["attempt"] == 1
    assert job["recovery_state"] == "held" and not job["merge_pending"]
    assert job["worker_failure"] == {"stage": "vad_windows", "reason": "outside_admitted_source"}
    recorded = [call.args[0] for call in metrics.record.call_args_list]
    assert "quarantined" in recorded and "recovery_held" in recorded


def test_terminal_word_clocks_staged_audio_invalid_durable_state_and_metrics_parity(monkeypatch):
    """worker_failure=(word_clocks, staged_audio_invalid): quarantine state, evidence booking and metrics are unchanged."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    metrics = Mock()
    store, queue, lease = _queued(metrics=metrics)
    assert _fail(queue, lease, worker_failure={"stage": "word_clocks", "reason": "staged_audio_invalid"}) is True
    job = store.rows["jobs", "a"]
    assert job["state"] == "quarantined" and job["attempt"] == 1
    assert job["recovery_state"] == "held" and not job["merge_pending"]
    assert job["worker_failure"] == {"stage": "word_clocks", "reason": "staged_audio_invalid"}
    recorded = [call.args[0] for call in metrics.record.call_args_list]
    assert "quarantined" in recorded and "recovery_held" in recorded


def test_terminal_word_clocks_retained_audio_invalid_durable_state_and_metrics_parity(monkeypatch):
    """worker_failure=(word_clocks, retained_audio_invalid): quarantine state, evidence booking and metrics are unchanged."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    metrics = Mock()
    store, queue, lease = _queued(metrics=metrics)
    assert _fail(queue, lease, worker_failure={"stage": "word_clocks", "reason": "retained_audio_invalid"}) is True
    job = store.rows["jobs", "a"]
    assert job["state"] == "quarantined" and job["attempt"] == 1
    assert job["recovery_state"] == "held" and not job["merge_pending"]
    assert job["worker_failure"] == {"stage": "word_clocks", "reason": "retained_audio_invalid"}
    recorded = [call.args[0] for call in metrics.record.call_args_list]
    assert "quarantined" in recorded and "recovery_held" in recorded


def test_terminal_word_clocks_decoded_duration_mismatch_durable_state_and_metrics_parity(monkeypatch):
    """worker_failure=(word_clocks, decoded_duration_mismatch): quarantine state, evidence booking and metrics are unchanged."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    metrics = Mock()
    store, queue, lease = _queued(metrics=metrics)
    assert _fail(queue, lease, worker_failure={"stage": "word_clocks", "reason": "decoded_duration_mismatch"}) is True
    job = store.rows["jobs", "a"]
    assert job["state"] == "quarantined" and job["attempt"] == 1
    assert job["recovery_state"] == "held" and not job["merge_pending"]
    assert job["worker_failure"] == {"stage": "word_clocks", "reason": "decoded_duration_mismatch"}
    recorded = [call.args[0] for call in metrics.record.call_args_list]
    assert "quarantined" in recorded and "recovery_held" in recorded


def test_terminal_word_clocks_word_shape_durable_state_and_metrics_parity(monkeypatch):
    """worker_failure=(word_clocks, word_shape): quarantine state, evidence booking and metrics are unchanged."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    metrics = Mock()
    store, queue, lease = _queued(metrics=metrics)
    assert _fail(queue, lease, worker_failure={"stage": "word_clocks", "reason": "word_shape"}) is True
    job = store.rows["jobs", "a"]
    assert job["state"] == "quarantined" and job["attempt"] == 1
    assert job["recovery_state"] == "held" and not job["merge_pending"]
    assert job["worker_failure"] == {"stage": "word_clocks", "reason": "word_shape"}
    recorded = [call.args[0] for call in metrics.record.call_args_list]
    assert "quarantined" in recorded and "recovery_held" in recorded


def test_terminal_word_clocks_word_clock_durable_state_and_metrics_parity(monkeypatch):
    """worker_failure=(word_clocks, word_clock): quarantine state, evidence booking and metrics are unchanged."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    metrics = Mock()
    store, queue, lease = _queued(metrics=metrics)
    assert _fail(queue, lease, worker_failure={"stage": "word_clocks", "reason": "word_clock"}) is True
    job = store.rows["jobs", "a"]
    assert job["state"] == "quarantined" and job["attempt"] == 1
    assert job["recovery_state"] == "held" and not job["merge_pending"]
    assert job["worker_failure"] == {"stage": "word_clocks", "reason": "word_clock"}
    recorded = [call.args[0] for call in metrics.record.call_args_list]
    assert "quarantined" in recorded and "recovery_held" in recorded


def test_terminal_word_clocks_word_sequence_durable_state_and_metrics_parity(monkeypatch):
    """worker_failure=(word_clocks, word_sequence): quarantine state, evidence booking and metrics are unchanged."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    metrics = Mock()
    store, queue, lease = _queued(metrics=metrics)
    assert _fail(queue, lease, worker_failure={"stage": "word_clocks", "reason": "word_sequence"}) is True
    job = store.rows["jobs", "a"]
    assert job["state"] == "quarantined" and job["attempt"] == 1
    assert job["recovery_state"] == "held" and not job["merge_pending"]
    assert job["worker_failure"] == {"stage": "word_clocks", "reason": "word_sequence"}
    recorded = [call.args[0] for call in metrics.record.call_args_list]
    assert "quarantined" in recorded and "recovery_held" in recorded


def test_terminal_word_clocks_vad_nonfinite_durable_state_and_metrics_parity(monkeypatch):
    """worker_failure=(word_clocks, vad_nonfinite): quarantine state, evidence booking and metrics are unchanged."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    metrics = Mock()
    store, queue, lease = _queued(metrics=metrics)
    assert _fail(queue, lease, worker_failure={"stage": "word_clocks", "reason": "vad_nonfinite"}) is True
    job = store.rows["jobs", "a"]
    assert job["state"] == "quarantined" and job["attempt"] == 1
    assert job["recovery_state"] == "held" and not job["merge_pending"]
    assert job["worker_failure"] == {"stage": "word_clocks", "reason": "vad_nonfinite"}
    recorded = [call.args[0] for call in metrics.record.call_args_list]
    assert "quarantined" in recorded and "recovery_held" in recorded


def test_terminal_word_clocks_vad_order_durable_state_and_metrics_parity(monkeypatch):
    """worker_failure=(word_clocks, vad_order): quarantine state, evidence booking and metrics are unchanged."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    metrics = Mock()
    store, queue, lease = _queued(metrics=metrics)
    assert _fail(queue, lease, worker_failure={"stage": "word_clocks", "reason": "vad_order"}) is True
    job = store.rows["jobs", "a"]
    assert job["state"] == "quarantined" and job["attempt"] == 1
    assert job["recovery_state"] == "held" and not job["merge_pending"]
    assert job["worker_failure"] == {"stage": "word_clocks", "reason": "vad_order"}
    recorded = [call.args[0] for call in metrics.record.call_args_list]
    assert "quarantined" in recorded and "recovery_held" in recorded


def test_terminal_word_clocks_vad_bounds_durable_state_and_metrics_parity(monkeypatch):
    """worker_failure=(word_clocks, vad_bounds): quarantine state, evidence booking and metrics are unchanged."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    metrics = Mock()
    store, queue, lease = _queued(metrics=metrics)
    assert _fail(queue, lease, worker_failure={"stage": "word_clocks", "reason": "vad_bounds"}) is True
    job = store.rows["jobs", "a"]
    assert job["state"] == "quarantined" and job["attempt"] == 1
    assert job["recovery_state"] == "held" and not job["merge_pending"]
    assert job["worker_failure"] == {"stage": "word_clocks", "reason": "vad_bounds"}
    recorded = [call.args[0] for call in metrics.record.call_args_list]
    assert "quarantined" in recorded and "recovery_held" in recorded


def test_terminal_word_clocks_empty_asr_durable_state_and_metrics_parity(monkeypatch):
    """worker_failure=(word_clocks, empty_asr): quarantine state, evidence booking and metrics are unchanged."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    metrics = Mock()
    store, queue, lease = _queued(metrics=metrics)
    assert _fail(queue, lease, worker_failure={"stage": "word_clocks", "reason": "empty_asr"}) is True
    job = store.rows["jobs", "a"]
    assert job["state"] == "quarantined" and job["attempt"] == 1
    assert job["recovery_state"] == "held" and not job["merge_pending"]
    assert job["worker_failure"] == {"stage": "word_clocks", "reason": "empty_asr"}
    recorded = [call.args[0] for call in metrics.record.call_args_list]
    assert "quarantined" in recorded and "recovery_held" in recorded


def test_terminal_word_clocks_no_owned_words_durable_state_and_metrics_parity(monkeypatch):
    """worker_failure=(word_clocks, no_owned_words): quarantine state, evidence booking and metrics are unchanged."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    metrics = Mock()
    store, queue, lease = _queued(metrics=metrics)
    assert _fail(queue, lease, worker_failure={"stage": "word_clocks", "reason": "no_owned_words"}) is True
    job = store.rows["jobs", "a"]
    assert job["state"] == "quarantined" and job["attempt"] == 1
    assert job["recovery_state"] == "held" and not job["merge_pending"]
    assert job["worker_failure"] == {"stage": "word_clocks", "reason": "no_owned_words"}
    recorded = [call.args[0] for call in metrics.record.call_args_list]
    assert "quarantined" in recorded and "recovery_held" in recorded


def test_terminal_word_clocks_unsupported_language_durable_state_and_metrics_parity(monkeypatch):
    """worker_failure=(word_clocks, unsupported_language): quarantine state, evidence booking and metrics are unchanged."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    metrics = Mock()
    store, queue, lease = _queued(metrics=metrics)
    assert _fail(queue, lease, worker_failure={"stage": "word_clocks", "reason": "unsupported_language"}) is True
    job = store.rows["jobs", "a"]
    assert job["state"] == "quarantined" and job["attempt"] == 1
    assert job["recovery_state"] == "held" and not job["merge_pending"]
    assert job["worker_failure"] == {"stage": "word_clocks", "reason": "unsupported_language"}
    recorded = [call.args[0] for call in metrics.record.call_args_list]
    assert "quarantined" in recorded and "recovery_held" in recorded


def test_terminal_word_clocks_outside_admitted_source_durable_state_and_metrics_parity(monkeypatch):
    """worker_failure=(word_clocks, outside_admitted_source): quarantine state, evidence booking and metrics are unchanged."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    metrics = Mock()
    store, queue, lease = _queued(metrics=metrics)
    assert _fail(queue, lease, worker_failure={"stage": "word_clocks", "reason": "outside_admitted_source"}) is True
    job = store.rows["jobs", "a"]
    assert job["state"] == "quarantined" and job["attempt"] == 1
    assert job["recovery_state"] == "held" and not job["merge_pending"]
    assert job["worker_failure"] == {"stage": "word_clocks", "reason": "outside_admitted_source"}
    recorded = [call.args[0] for call in metrics.record.call_args_list]
    assert "quarantined" in recorded and "recovery_held" in recorded


def test_terminal_assemble_words_staged_audio_invalid_durable_state_and_metrics_parity(monkeypatch):
    """worker_failure=(assemble_words, staged_audio_invalid): quarantine state, evidence booking and metrics are unchanged."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    metrics = Mock()
    store, queue, lease = _queued(metrics=metrics)
    assert _fail(queue, lease, worker_failure={"stage": "assemble_words", "reason": "staged_audio_invalid"}) is True
    job = store.rows["jobs", "a"]
    assert job["state"] == "quarantined" and job["attempt"] == 1
    assert job["recovery_state"] == "held" and not job["merge_pending"]
    assert job["worker_failure"] == {"stage": "assemble_words", "reason": "staged_audio_invalid"}
    recorded = [call.args[0] for call in metrics.record.call_args_list]
    assert "quarantined" in recorded and "recovery_held" in recorded


def test_terminal_assemble_words_retained_audio_invalid_durable_state_and_metrics_parity(monkeypatch):
    """worker_failure=(assemble_words, retained_audio_invalid): quarantine state, evidence booking and metrics are unchanged."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    metrics = Mock()
    store, queue, lease = _queued(metrics=metrics)
    assert _fail(queue, lease, worker_failure={"stage": "assemble_words", "reason": "retained_audio_invalid"}) is True
    job = store.rows["jobs", "a"]
    assert job["state"] == "quarantined" and job["attempt"] == 1
    assert job["recovery_state"] == "held" and not job["merge_pending"]
    assert job["worker_failure"] == {"stage": "assemble_words", "reason": "retained_audio_invalid"}
    recorded = [call.args[0] for call in metrics.record.call_args_list]
    assert "quarantined" in recorded and "recovery_held" in recorded


def test_terminal_assemble_words_decoded_duration_mismatch_durable_state_and_metrics_parity(monkeypatch):
    """worker_failure=(assemble_words, decoded_duration_mismatch): quarantine state, evidence booking and metrics are unchanged."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    metrics = Mock()
    store, queue, lease = _queued(metrics=metrics)
    assert (
        _fail(queue, lease, worker_failure={"stage": "assemble_words", "reason": "decoded_duration_mismatch"}) is True
    )
    job = store.rows["jobs", "a"]
    assert job["state"] == "quarantined" and job["attempt"] == 1
    assert job["recovery_state"] == "held" and not job["merge_pending"]
    assert job["worker_failure"] == {"stage": "assemble_words", "reason": "decoded_duration_mismatch"}
    recorded = [call.args[0] for call in metrics.record.call_args_list]
    assert "quarantined" in recorded and "recovery_held" in recorded


def test_terminal_assemble_words_word_shape_durable_state_and_metrics_parity(monkeypatch):
    """worker_failure=(assemble_words, word_shape): quarantine state, evidence booking and metrics are unchanged."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    metrics = Mock()
    store, queue, lease = _queued(metrics=metrics)
    assert _fail(queue, lease, worker_failure={"stage": "assemble_words", "reason": "word_shape"}) is True
    job = store.rows["jobs", "a"]
    assert job["state"] == "quarantined" and job["attempt"] == 1
    assert job["recovery_state"] == "held" and not job["merge_pending"]
    assert job["worker_failure"] == {"stage": "assemble_words", "reason": "word_shape"}
    recorded = [call.args[0] for call in metrics.record.call_args_list]
    assert "quarantined" in recorded and "recovery_held" in recorded


def test_terminal_assemble_words_word_clock_durable_state_and_metrics_parity(monkeypatch):
    """worker_failure=(assemble_words, word_clock): quarantine state, evidence booking and metrics are unchanged."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    metrics = Mock()
    store, queue, lease = _queued(metrics=metrics)
    assert _fail(queue, lease, worker_failure={"stage": "assemble_words", "reason": "word_clock"}) is True
    job = store.rows["jobs", "a"]
    assert job["state"] == "quarantined" and job["attempt"] == 1
    assert job["recovery_state"] == "held" and not job["merge_pending"]
    assert job["worker_failure"] == {"stage": "assemble_words", "reason": "word_clock"}
    recorded = [call.args[0] for call in metrics.record.call_args_list]
    assert "quarantined" in recorded and "recovery_held" in recorded


def test_terminal_assemble_words_word_sequence_durable_state_and_metrics_parity(monkeypatch):
    """worker_failure=(assemble_words, word_sequence): quarantine state, evidence booking and metrics are unchanged."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    metrics = Mock()
    store, queue, lease = _queued(metrics=metrics)
    assert _fail(queue, lease, worker_failure={"stage": "assemble_words", "reason": "word_sequence"}) is True
    job = store.rows["jobs", "a"]
    assert job["state"] == "quarantined" and job["attempt"] == 1
    assert job["recovery_state"] == "held" and not job["merge_pending"]
    assert job["worker_failure"] == {"stage": "assemble_words", "reason": "word_sequence"}
    recorded = [call.args[0] for call in metrics.record.call_args_list]
    assert "quarantined" in recorded and "recovery_held" in recorded


def test_terminal_assemble_words_vad_nonfinite_durable_state_and_metrics_parity(monkeypatch):
    """worker_failure=(assemble_words, vad_nonfinite): quarantine state, evidence booking and metrics are unchanged."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    metrics = Mock()
    store, queue, lease = _queued(metrics=metrics)
    assert _fail(queue, lease, worker_failure={"stage": "assemble_words", "reason": "vad_nonfinite"}) is True
    job = store.rows["jobs", "a"]
    assert job["state"] == "quarantined" and job["attempt"] == 1
    assert job["recovery_state"] == "held" and not job["merge_pending"]
    assert job["worker_failure"] == {"stage": "assemble_words", "reason": "vad_nonfinite"}
    recorded = [call.args[0] for call in metrics.record.call_args_list]
    assert "quarantined" in recorded and "recovery_held" in recorded


def test_terminal_assemble_words_vad_order_durable_state_and_metrics_parity(monkeypatch):
    """worker_failure=(assemble_words, vad_order): quarantine state, evidence booking and metrics are unchanged."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    metrics = Mock()
    store, queue, lease = _queued(metrics=metrics)
    assert _fail(queue, lease, worker_failure={"stage": "assemble_words", "reason": "vad_order"}) is True
    job = store.rows["jobs", "a"]
    assert job["state"] == "quarantined" and job["attempt"] == 1
    assert job["recovery_state"] == "held" and not job["merge_pending"]
    assert job["worker_failure"] == {"stage": "assemble_words", "reason": "vad_order"}
    recorded = [call.args[0] for call in metrics.record.call_args_list]
    assert "quarantined" in recorded and "recovery_held" in recorded


def test_terminal_assemble_words_vad_bounds_durable_state_and_metrics_parity(monkeypatch):
    """worker_failure=(assemble_words, vad_bounds): quarantine state, evidence booking and metrics are unchanged."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    metrics = Mock()
    store, queue, lease = _queued(metrics=metrics)
    assert _fail(queue, lease, worker_failure={"stage": "assemble_words", "reason": "vad_bounds"}) is True
    job = store.rows["jobs", "a"]
    assert job["state"] == "quarantined" and job["attempt"] == 1
    assert job["recovery_state"] == "held" and not job["merge_pending"]
    assert job["worker_failure"] == {"stage": "assemble_words", "reason": "vad_bounds"}
    recorded = [call.args[0] for call in metrics.record.call_args_list]
    assert "quarantined" in recorded and "recovery_held" in recorded


def test_terminal_assemble_words_empty_asr_durable_state_and_metrics_parity(monkeypatch):
    """worker_failure=(assemble_words, empty_asr): quarantine state, evidence booking and metrics are unchanged."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    metrics = Mock()
    store, queue, lease = _queued(metrics=metrics)
    assert _fail(queue, lease, worker_failure={"stage": "assemble_words", "reason": "empty_asr"}) is True
    job = store.rows["jobs", "a"]
    assert job["state"] == "quarantined" and job["attempt"] == 1
    assert job["recovery_state"] == "held" and not job["merge_pending"]
    assert job["worker_failure"] == {"stage": "assemble_words", "reason": "empty_asr"}
    recorded = [call.args[0] for call in metrics.record.call_args_list]
    assert "quarantined" in recorded and "recovery_held" in recorded


def test_terminal_assemble_words_no_owned_words_durable_state_and_metrics_parity(monkeypatch):
    """worker_failure=(assemble_words, no_owned_words): quarantine state, evidence booking and metrics are unchanged."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    metrics = Mock()
    store, queue, lease = _queued(metrics=metrics)
    assert _fail(queue, lease, worker_failure={"stage": "assemble_words", "reason": "no_owned_words"}) is True
    job = store.rows["jobs", "a"]
    assert job["state"] == "quarantined" and job["attempt"] == 1
    assert job["recovery_state"] == "held" and not job["merge_pending"]
    assert job["worker_failure"] == {"stage": "assemble_words", "reason": "no_owned_words"}
    recorded = [call.args[0] for call in metrics.record.call_args_list]
    assert "quarantined" in recorded and "recovery_held" in recorded


def test_terminal_assemble_words_unsupported_language_durable_state_and_metrics_parity(monkeypatch):
    """worker_failure=(assemble_words, unsupported_language): quarantine state, evidence booking and metrics are unchanged."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    metrics = Mock()
    store, queue, lease = _queued(metrics=metrics)
    assert _fail(queue, lease, worker_failure={"stage": "assemble_words", "reason": "unsupported_language"}) is True
    job = store.rows["jobs", "a"]
    assert job["state"] == "quarantined" and job["attempt"] == 1
    assert job["recovery_state"] == "held" and not job["merge_pending"]
    assert job["worker_failure"] == {"stage": "assemble_words", "reason": "unsupported_language"}
    recorded = [call.args[0] for call in metrics.record.call_args_list]
    assert "quarantined" in recorded and "recovery_held" in recorded


def test_terminal_assemble_words_outside_admitted_source_durable_state_and_metrics_parity(monkeypatch):
    """worker_failure=(assemble_words, outside_admitted_source): quarantine state, evidence booking and metrics are unchanged."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    metrics = Mock()
    store, queue, lease = _queued(metrics=metrics)
    assert _fail(queue, lease, worker_failure={"stage": "assemble_words", "reason": "outside_admitted_source"}) is True
    job = store.rows["jobs", "a"]
    assert job["state"] == "quarantined" and job["attempt"] == 1
    assert job["recovery_state"] == "held" and not job["merge_pending"]
    assert job["worker_failure"] == {"stage": "assemble_words", "reason": "outside_admitted_source"}
    recorded = [call.args[0] for call in metrics.record.call_args_list]
    assert "quarantined" in recorded and "recovery_held" in recorded


def test_terminal_asr_recovery_staged_audio_invalid_durable_state_and_metrics_parity(monkeypatch):
    """worker_failure=(asr_recovery, staged_audio_invalid): quarantine state, evidence booking and metrics are unchanged."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    metrics = Mock()
    store, queue, lease = _queued(metrics=metrics)
    assert _fail(queue, lease, worker_failure={"stage": "asr_recovery", "reason": "staged_audio_invalid"}) is True
    job = store.rows["jobs", "a"]
    assert job["state"] == "quarantined" and job["attempt"] == 1
    assert job["recovery_state"] == "held" and not job["merge_pending"]
    assert job["worker_failure"] == {"stage": "asr_recovery", "reason": "staged_audio_invalid"}
    recorded = [call.args[0] for call in metrics.record.call_args_list]
    assert "quarantined" in recorded and "recovery_held" in recorded


def test_terminal_asr_recovery_retained_audio_invalid_durable_state_and_metrics_parity(monkeypatch):
    """worker_failure=(asr_recovery, retained_audio_invalid): quarantine state, evidence booking and metrics are unchanged."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    metrics = Mock()
    store, queue, lease = _queued(metrics=metrics)
    assert _fail(queue, lease, worker_failure={"stage": "asr_recovery", "reason": "retained_audio_invalid"}) is True
    job = store.rows["jobs", "a"]
    assert job["state"] == "quarantined" and job["attempt"] == 1
    assert job["recovery_state"] == "held" and not job["merge_pending"]
    assert job["worker_failure"] == {"stage": "asr_recovery", "reason": "retained_audio_invalid"}
    recorded = [call.args[0] for call in metrics.record.call_args_list]
    assert "quarantined" in recorded and "recovery_held" in recorded


def test_terminal_asr_recovery_decoded_duration_mismatch_durable_state_and_metrics_parity(monkeypatch):
    """worker_failure=(asr_recovery, decoded_duration_mismatch): quarantine state, evidence booking and metrics are unchanged."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    metrics = Mock()
    store, queue, lease = _queued(metrics=metrics)
    assert _fail(queue, lease, worker_failure={"stage": "asr_recovery", "reason": "decoded_duration_mismatch"}) is True
    job = store.rows["jobs", "a"]
    assert job["state"] == "quarantined" and job["attempt"] == 1
    assert job["recovery_state"] == "held" and not job["merge_pending"]
    assert job["worker_failure"] == {"stage": "asr_recovery", "reason": "decoded_duration_mismatch"}
    recorded = [call.args[0] for call in metrics.record.call_args_list]
    assert "quarantined" in recorded and "recovery_held" in recorded


def test_terminal_asr_recovery_word_shape_durable_state_and_metrics_parity(monkeypatch):
    """worker_failure=(asr_recovery, word_shape): quarantine state, evidence booking and metrics are unchanged."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    metrics = Mock()
    store, queue, lease = _queued(metrics=metrics)
    assert _fail(queue, lease, worker_failure={"stage": "asr_recovery", "reason": "word_shape"}) is True
    job = store.rows["jobs", "a"]
    assert job["state"] == "quarantined" and job["attempt"] == 1
    assert job["recovery_state"] == "held" and not job["merge_pending"]
    assert job["worker_failure"] == {"stage": "asr_recovery", "reason": "word_shape"}
    recorded = [call.args[0] for call in metrics.record.call_args_list]
    assert "quarantined" in recorded and "recovery_held" in recorded


def test_terminal_asr_recovery_word_clock_durable_state_and_metrics_parity(monkeypatch):
    """worker_failure=(asr_recovery, word_clock): quarantine state, evidence booking and metrics are unchanged."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    metrics = Mock()
    store, queue, lease = _queued(metrics=metrics)
    assert _fail(queue, lease, worker_failure={"stage": "asr_recovery", "reason": "word_clock"}) is True
    job = store.rows["jobs", "a"]
    assert job["state"] == "quarantined" and job["attempt"] == 1
    assert job["recovery_state"] == "held" and not job["merge_pending"]
    assert job["worker_failure"] == {"stage": "asr_recovery", "reason": "word_clock"}
    recorded = [call.args[0] for call in metrics.record.call_args_list]
    assert "quarantined" in recorded and "recovery_held" in recorded


def test_terminal_asr_recovery_word_sequence_durable_state_and_metrics_parity(monkeypatch):
    """worker_failure=(asr_recovery, word_sequence): quarantine state, evidence booking and metrics are unchanged."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    metrics = Mock()
    store, queue, lease = _queued(metrics=metrics)
    assert _fail(queue, lease, worker_failure={"stage": "asr_recovery", "reason": "word_sequence"}) is True
    job = store.rows["jobs", "a"]
    assert job["state"] == "quarantined" and job["attempt"] == 1
    assert job["recovery_state"] == "held" and not job["merge_pending"]
    assert job["worker_failure"] == {"stage": "asr_recovery", "reason": "word_sequence"}
    recorded = [call.args[0] for call in metrics.record.call_args_list]
    assert "quarantined" in recorded and "recovery_held" in recorded


def test_terminal_asr_recovery_vad_nonfinite_durable_state_and_metrics_parity(monkeypatch):
    """worker_failure=(asr_recovery, vad_nonfinite): quarantine state, evidence booking and metrics are unchanged."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    metrics = Mock()
    store, queue, lease = _queued(metrics=metrics)
    assert _fail(queue, lease, worker_failure={"stage": "asr_recovery", "reason": "vad_nonfinite"}) is True
    job = store.rows["jobs", "a"]
    assert job["state"] == "quarantined" and job["attempt"] == 1
    assert job["recovery_state"] == "held" and not job["merge_pending"]
    assert job["worker_failure"] == {"stage": "asr_recovery", "reason": "vad_nonfinite"}
    recorded = [call.args[0] for call in metrics.record.call_args_list]
    assert "quarantined" in recorded and "recovery_held" in recorded


def test_terminal_asr_recovery_vad_order_durable_state_and_metrics_parity(monkeypatch):
    """worker_failure=(asr_recovery, vad_order): quarantine state, evidence booking and metrics are unchanged."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    metrics = Mock()
    store, queue, lease = _queued(metrics=metrics)
    assert _fail(queue, lease, worker_failure={"stage": "asr_recovery", "reason": "vad_order"}) is True
    job = store.rows["jobs", "a"]
    assert job["state"] == "quarantined" and job["attempt"] == 1
    assert job["recovery_state"] == "held" and not job["merge_pending"]
    assert job["worker_failure"] == {"stage": "asr_recovery", "reason": "vad_order"}
    recorded = [call.args[0] for call in metrics.record.call_args_list]
    assert "quarantined" in recorded and "recovery_held" in recorded


def test_terminal_asr_recovery_vad_bounds_durable_state_and_metrics_parity(monkeypatch):
    """worker_failure=(asr_recovery, vad_bounds): quarantine state, evidence booking and metrics are unchanged."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    metrics = Mock()
    store, queue, lease = _queued(metrics=metrics)
    assert _fail(queue, lease, worker_failure={"stage": "asr_recovery", "reason": "vad_bounds"}) is True
    job = store.rows["jobs", "a"]
    assert job["state"] == "quarantined" and job["attempt"] == 1
    assert job["recovery_state"] == "held" and not job["merge_pending"]
    assert job["worker_failure"] == {"stage": "asr_recovery", "reason": "vad_bounds"}
    recorded = [call.args[0] for call in metrics.record.call_args_list]
    assert "quarantined" in recorded and "recovery_held" in recorded


def test_terminal_asr_recovery_empty_asr_durable_state_and_metrics_parity(monkeypatch):
    """worker_failure=(asr_recovery, empty_asr): quarantine state, evidence booking and metrics are unchanged."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    metrics = Mock()
    store, queue, lease = _queued(metrics=metrics)
    assert _fail(queue, lease, worker_failure={"stage": "asr_recovery", "reason": "empty_asr"}) is True
    job = store.rows["jobs", "a"]
    assert job["state"] == "quarantined" and job["attempt"] == 1
    assert job["recovery_state"] == "held" and not job["merge_pending"]
    assert job["worker_failure"] == {"stage": "asr_recovery", "reason": "empty_asr"}
    recorded = [call.args[0] for call in metrics.record.call_args_list]
    assert "quarantined" in recorded and "recovery_held" in recorded


def test_terminal_asr_recovery_no_owned_words_durable_state_and_metrics_parity(monkeypatch):
    """worker_failure=(asr_recovery, no_owned_words): quarantine state, evidence booking and metrics are unchanged."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    metrics = Mock()
    store, queue, lease = _queued(metrics=metrics)
    assert _fail(queue, lease, worker_failure={"stage": "asr_recovery", "reason": "no_owned_words"}) is True
    job = store.rows["jobs", "a"]
    assert job["state"] == "quarantined" and job["attempt"] == 1
    assert job["recovery_state"] == "held" and not job["merge_pending"]
    assert job["worker_failure"] == {"stage": "asr_recovery", "reason": "no_owned_words"}
    recorded = [call.args[0] for call in metrics.record.call_args_list]
    assert "quarantined" in recorded and "recovery_held" in recorded


def test_terminal_asr_recovery_unsupported_language_durable_state_and_metrics_parity(monkeypatch):
    """worker_failure=(asr_recovery, unsupported_language): quarantine state, evidence booking and metrics are unchanged."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    metrics = Mock()
    store, queue, lease = _queued(metrics=metrics)
    assert _fail(queue, lease, worker_failure={"stage": "asr_recovery", "reason": "unsupported_language"}) is True
    job = store.rows["jobs", "a"]
    assert job["state"] == "quarantined" and job["attempt"] == 1
    assert job["recovery_state"] == "held" and not job["merge_pending"]
    assert job["worker_failure"] == {"stage": "asr_recovery", "reason": "unsupported_language"}
    recorded = [call.args[0] for call in metrics.record.call_args_list]
    assert "quarantined" in recorded and "recovery_held" in recorded


def test_terminal_asr_recovery_outside_admitted_source_durable_state_and_metrics_parity(monkeypatch):
    """worker_failure=(asr_recovery, outside_admitted_source): quarantine state, evidence booking and metrics are unchanged."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    metrics = Mock()
    store, queue, lease = _queued(metrics=metrics)
    assert _fail(queue, lease, worker_failure={"stage": "asr_recovery", "reason": "outside_admitted_source"}) is True
    job = store.rows["jobs", "a"]
    assert job["state"] == "quarantined" and job["attempt"] == 1
    assert job["recovery_state"] == "held" and not job["merge_pending"]
    assert job["worker_failure"] == {"stage": "asr_recovery", "reason": "outside_admitted_source"}
    recorded = [call.args[0] for call in metrics.record.call_args_list]
    assert "quarantined" in recorded and "recovery_held" in recorded


def test_exhausted_fetch_decode_vad_bounds_evidence_names_the_disposition_channel(monkeypatch, caplog):
    """A ladder exhausted bare names the preserved (fetch_decode, vad_bounds) evidence on the disposition channel."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue = _queued_for_walk()
    attempts = _walk(queue, store, evidence_plan={1: {"stage": "fetch_decode", "reason": "vad_bounds"}})
    assert attempts == 5
    disposition, quar, ladder, guard, warn = _channel(caplog)
    assert not quar and not ladder and not guard and len(disposition) == 1
    assert "stage=fetch_decode" in disposition[0].getMessage()
    assert "worker_reason=vad_bounds" in disposition[0].getMessage()
    assert len(warn) == 1


def test_exhausted_fetch_decode_word_clock_evidence_names_the_disposition_channel(monkeypatch, caplog):
    """A ladder exhausted bare names the preserved (fetch_decode, word_clock) evidence on the disposition channel."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue = _queued_for_walk()
    attempts = _walk(queue, store, evidence_plan={1: {"stage": "fetch_decode", "reason": "word_clock"}})
    assert attempts == 5
    disposition, quar, ladder, guard, warn = _channel(caplog)
    assert not quar and not ladder and not guard and len(disposition) == 1
    assert "stage=fetch_decode" in disposition[0].getMessage()
    assert "worker_reason=word_clock" in disposition[0].getMessage()
    assert len(warn) == 1


def test_exhausted_fetch_decode_staged_audio_invalid_evidence_names_the_disposition_channel(monkeypatch, caplog):
    """A ladder exhausted bare names the preserved (fetch_decode, staged_audio_invalid) evidence on the disposition channel."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue = _queued_for_walk()
    attempts = _walk(queue, store, evidence_plan={1: {"stage": "fetch_decode", "reason": "staged_audio_invalid"}})
    assert attempts == 5
    disposition, quar, ladder, guard, warn = _channel(caplog)
    assert not quar and not ladder and not guard and len(disposition) == 1
    assert "stage=fetch_decode" in disposition[0].getMessage()
    assert "worker_reason=staged_audio_invalid" in disposition[0].getMessage()
    assert len(warn) == 1


def test_exhausted_fetch_decode_outside_admitted_source_evidence_names_the_quarantined_channel(monkeypatch, caplog):
    """A ladder exhausted bare names the preserved (fetch_decode, outside_admitted_source) evidence on the quarantined channel."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue = _queued_for_walk()
    attempts = _walk(queue, store, evidence_plan={1: {"stage": "fetch_decode", "reason": "outside_admitted_source"}})
    assert attempts == 5
    disposition, quar, ladder, guard, warn = _channel(caplog)
    assert not disposition and not ladder and not guard and len(quar) == 1
    assert "stage=fetch_decode" in quar[0].getMessage()
    assert "worker_reason=outside_admitted_source" in quar[0].getMessage()
    assert len(warn) == 1


def test_exhausted_fetch_decode_unknown_evidence_names_the_quarantined_channel(monkeypatch, caplog):
    """A ladder exhausted bare names the preserved (fetch_decode, unknown) evidence on the quarantined channel."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue = _queued_for_walk()
    attempts = _walk(queue, store, evidence_plan={1: {"stage": "fetch_decode", "reason": "unknown"}})
    assert attempts == 5
    disposition, quar, ladder, guard, warn = _channel(caplog)
    assert not disposition and not ladder and not guard and len(quar) == 1
    assert "stage=fetch_decode" in quar[0].getMessage()
    assert "worker_reason=unknown" in quar[0].getMessage()
    assert len(warn) == 1


def test_exhausted_vad_windows_vad_bounds_evidence_names_the_disposition_channel(monkeypatch, caplog):
    """A ladder exhausted bare names the preserved (vad_windows, vad_bounds) evidence on the disposition channel."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue = _queued_for_walk()
    attempts = _walk(queue, store, evidence_plan={1: {"stage": "vad_windows", "reason": "vad_bounds"}})
    assert attempts == 5
    disposition, quar, ladder, guard, warn = _channel(caplog)
    assert not quar and not ladder and not guard and len(disposition) == 1
    assert "stage=vad_windows" in disposition[0].getMessage()
    assert "worker_reason=vad_bounds" in disposition[0].getMessage()
    assert len(warn) == 1


def test_exhausted_vad_windows_word_clock_evidence_names_the_disposition_channel(monkeypatch, caplog):
    """A ladder exhausted bare names the preserved (vad_windows, word_clock) evidence on the disposition channel."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue = _queued_for_walk()
    attempts = _walk(queue, store, evidence_plan={1: {"stage": "vad_windows", "reason": "word_clock"}})
    assert attempts == 5
    disposition, quar, ladder, guard, warn = _channel(caplog)
    assert not quar and not ladder and not guard and len(disposition) == 1
    assert "stage=vad_windows" in disposition[0].getMessage()
    assert "worker_reason=word_clock" in disposition[0].getMessage()
    assert len(warn) == 1


def test_exhausted_vad_windows_staged_audio_invalid_evidence_names_the_quarantined_channel(monkeypatch, caplog):
    """A ladder exhausted bare names the preserved (vad_windows, staged_audio_invalid) evidence on the quarantined channel."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue = _queued_for_walk()
    attempts = _walk(queue, store, evidence_plan={1: {"stage": "vad_windows", "reason": "staged_audio_invalid"}})
    assert attempts == 5
    disposition, quar, ladder, guard, warn = _channel(caplog)
    assert not disposition and not ladder and not guard and len(quar) == 1
    assert "stage=vad_windows" in quar[0].getMessage()
    assert "worker_reason=staged_audio_invalid" in quar[0].getMessage()
    assert len(warn) == 1


def test_exhausted_vad_windows_outside_admitted_source_evidence_names_the_quarantined_channel(monkeypatch, caplog):
    """A ladder exhausted bare names the preserved (vad_windows, outside_admitted_source) evidence on the quarantined channel."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue = _queued_for_walk()
    attempts = _walk(queue, store, evidence_plan={1: {"stage": "vad_windows", "reason": "outside_admitted_source"}})
    assert attempts == 5
    disposition, quar, ladder, guard, warn = _channel(caplog)
    assert not disposition and not ladder and not guard and len(quar) == 1
    assert "stage=vad_windows" in quar[0].getMessage()
    assert "worker_reason=outside_admitted_source" in quar[0].getMessage()
    assert len(warn) == 1


def test_exhausted_vad_windows_unknown_evidence_names_the_quarantined_channel(monkeypatch, caplog):
    """A ladder exhausted bare names the preserved (vad_windows, unknown) evidence on the quarantined channel."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue = _queued_for_walk()
    attempts = _walk(queue, store, evidence_plan={1: {"stage": "vad_windows", "reason": "unknown"}})
    assert attempts == 5
    disposition, quar, ladder, guard, warn = _channel(caplog)
    assert not disposition and not ladder and not guard and len(quar) == 1
    assert "stage=vad_windows" in quar[0].getMessage()
    assert "worker_reason=unknown" in quar[0].getMessage()
    assert len(warn) == 1


def test_exhausted_word_clocks_vad_bounds_evidence_names_the_disposition_channel(monkeypatch, caplog):
    """A ladder exhausted bare names the preserved (word_clocks, vad_bounds) evidence on the disposition channel."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue = _queued_for_walk()
    attempts = _walk(queue, store, evidence_plan={1: {"stage": "word_clocks", "reason": "vad_bounds"}})
    assert attempts == 5
    disposition, quar, ladder, guard, warn = _channel(caplog)
    assert not quar and not ladder and not guard and len(disposition) == 1
    assert "stage=word_clocks" in disposition[0].getMessage()
    assert "worker_reason=vad_bounds" in disposition[0].getMessage()
    assert len(warn) == 1


def test_exhausted_word_clocks_word_clock_evidence_names_the_disposition_channel(monkeypatch, caplog):
    """A ladder exhausted bare names the preserved (word_clocks, word_clock) evidence on the disposition channel."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue = _queued_for_walk()
    attempts = _walk(queue, store, evidence_plan={1: {"stage": "word_clocks", "reason": "word_clock"}})
    assert attempts == 5
    disposition, quar, ladder, guard, warn = _channel(caplog)
    assert not quar and not ladder and not guard and len(disposition) == 1
    assert "stage=word_clocks" in disposition[0].getMessage()
    assert "worker_reason=word_clock" in disposition[0].getMessage()
    assert len(warn) == 1


def test_exhausted_word_clocks_staged_audio_invalid_evidence_names_the_quarantined_channel(monkeypatch, caplog):
    """A ladder exhausted bare names the preserved (word_clocks, staged_audio_invalid) evidence on the quarantined channel."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue = _queued_for_walk()
    attempts = _walk(queue, store, evidence_plan={1: {"stage": "word_clocks", "reason": "staged_audio_invalid"}})
    assert attempts == 5
    disposition, quar, ladder, guard, warn = _channel(caplog)
    assert not disposition and not ladder and not guard and len(quar) == 1
    assert "stage=word_clocks" in quar[0].getMessage()
    assert "worker_reason=staged_audio_invalid" in quar[0].getMessage()
    assert len(warn) == 1


def test_exhausted_word_clocks_outside_admitted_source_evidence_names_the_quarantined_channel(monkeypatch, caplog):
    """A ladder exhausted bare names the preserved (word_clocks, outside_admitted_source) evidence on the quarantined channel."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue = _queued_for_walk()
    attempts = _walk(queue, store, evidence_plan={1: {"stage": "word_clocks", "reason": "outside_admitted_source"}})
    assert attempts == 5
    disposition, quar, ladder, guard, warn = _channel(caplog)
    assert not disposition and not ladder and not guard and len(quar) == 1
    assert "stage=word_clocks" in quar[0].getMessage()
    assert "worker_reason=outside_admitted_source" in quar[0].getMessage()
    assert len(warn) == 1


def test_exhausted_word_clocks_unknown_evidence_names_the_quarantined_channel(monkeypatch, caplog):
    """A ladder exhausted bare names the preserved (word_clocks, unknown) evidence on the quarantined channel."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue = _queued_for_walk()
    attempts = _walk(queue, store, evidence_plan={1: {"stage": "word_clocks", "reason": "unknown"}})
    assert attempts == 5
    disposition, quar, ladder, guard, warn = _channel(caplog)
    assert not disposition and not ladder and not guard and len(quar) == 1
    assert "stage=word_clocks" in quar[0].getMessage()
    assert "worker_reason=unknown" in quar[0].getMessage()
    assert len(warn) == 1


def test_exhausted_assemble_words_vad_bounds_evidence_names_the_disposition_channel(monkeypatch, caplog):
    """A ladder exhausted bare names the preserved (assemble_words, vad_bounds) evidence on the disposition channel."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue = _queued_for_walk()
    attempts = _walk(queue, store, evidence_plan={1: {"stage": "assemble_words", "reason": "vad_bounds"}})
    assert attempts == 5
    disposition, quar, ladder, guard, warn = _channel(caplog)
    assert not quar and not ladder and not guard and len(disposition) == 1
    assert "stage=assemble_words" in disposition[0].getMessage()
    assert "worker_reason=vad_bounds" in disposition[0].getMessage()
    assert len(warn) == 1


def test_exhausted_assemble_words_word_clock_evidence_names_the_disposition_channel(monkeypatch, caplog):
    """A ladder exhausted bare names the preserved (assemble_words, word_clock) evidence on the disposition channel."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue = _queued_for_walk()
    attempts = _walk(queue, store, evidence_plan={1: {"stage": "assemble_words", "reason": "word_clock"}})
    assert attempts == 5
    disposition, quar, ladder, guard, warn = _channel(caplog)
    assert not quar and not ladder and not guard and len(disposition) == 1
    assert "stage=assemble_words" in disposition[0].getMessage()
    assert "worker_reason=word_clock" in disposition[0].getMessage()
    assert len(warn) == 1


def test_exhausted_assemble_words_staged_audio_invalid_evidence_names_the_quarantined_channel(monkeypatch, caplog):
    """A ladder exhausted bare names the preserved (assemble_words, staged_audio_invalid) evidence on the quarantined channel."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue = _queued_for_walk()
    attempts = _walk(queue, store, evidence_plan={1: {"stage": "assemble_words", "reason": "staged_audio_invalid"}})
    assert attempts == 5
    disposition, quar, ladder, guard, warn = _channel(caplog)
    assert not disposition and not ladder and not guard and len(quar) == 1
    assert "stage=assemble_words" in quar[0].getMessage()
    assert "worker_reason=staged_audio_invalid" in quar[0].getMessage()
    assert len(warn) == 1


def test_exhausted_assemble_words_outside_admitted_source_evidence_names_the_quarantined_channel(monkeypatch, caplog):
    """A ladder exhausted bare names the preserved (assemble_words, outside_admitted_source) evidence on the quarantined channel."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue = _queued_for_walk()
    attempts = _walk(queue, store, evidence_plan={1: {"stage": "assemble_words", "reason": "outside_admitted_source"}})
    assert attempts == 5
    disposition, quar, ladder, guard, warn = _channel(caplog)
    assert not disposition and not ladder and not guard and len(quar) == 1
    assert "stage=assemble_words" in quar[0].getMessage()
    assert "worker_reason=outside_admitted_source" in quar[0].getMessage()
    assert len(warn) == 1


def test_exhausted_assemble_words_unknown_evidence_names_the_quarantined_channel(monkeypatch, caplog):
    """A ladder exhausted bare names the preserved (assemble_words, unknown) evidence on the quarantined channel."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue = _queued_for_walk()
    attempts = _walk(queue, store, evidence_plan={1: {"stage": "assemble_words", "reason": "unknown"}})
    assert attempts == 5
    disposition, quar, ladder, guard, warn = _channel(caplog)
    assert not disposition and not ladder and not guard and len(quar) == 1
    assert "stage=assemble_words" in quar[0].getMessage()
    assert "worker_reason=unknown" in quar[0].getMessage()
    assert len(warn) == 1


def test_exhausted_asr_recovery_vad_bounds_evidence_names_the_disposition_channel(monkeypatch, caplog):
    """A ladder exhausted bare names the preserved (asr_recovery, vad_bounds) evidence on the disposition channel."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue = _queued_for_walk()
    attempts = _walk(queue, store, evidence_plan={1: {"stage": "asr_recovery", "reason": "vad_bounds"}})
    assert attempts == 5
    disposition, quar, ladder, guard, warn = _channel(caplog)
    assert not quar and not ladder and not guard and len(disposition) == 1
    assert "stage=asr_recovery" in disposition[0].getMessage()
    assert "worker_reason=vad_bounds" in disposition[0].getMessage()
    assert len(warn) == 1


def test_exhausted_asr_recovery_word_clock_evidence_names_the_disposition_channel(monkeypatch, caplog):
    """A ladder exhausted bare names the preserved (asr_recovery, word_clock) evidence on the disposition channel."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue = _queued_for_walk()
    attempts = _walk(queue, store, evidence_plan={1: {"stage": "asr_recovery", "reason": "word_clock"}})
    assert attempts == 5
    disposition, quar, ladder, guard, warn = _channel(caplog)
    assert not quar and not ladder and not guard and len(disposition) == 1
    assert "stage=asr_recovery" in disposition[0].getMessage()
    assert "worker_reason=word_clock" in disposition[0].getMessage()
    assert len(warn) == 1


def test_exhausted_asr_recovery_staged_audio_invalid_evidence_names_the_quarantined_channel(monkeypatch, caplog):
    """A ladder exhausted bare names the preserved (asr_recovery, staged_audio_invalid) evidence on the quarantined channel."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue = _queued_for_walk()
    attempts = _walk(queue, store, evidence_plan={1: {"stage": "asr_recovery", "reason": "staged_audio_invalid"}})
    assert attempts == 5
    disposition, quar, ladder, guard, warn = _channel(caplog)
    assert not disposition and not ladder and not guard and len(quar) == 1
    assert "stage=asr_recovery" in quar[0].getMessage()
    assert "worker_reason=staged_audio_invalid" in quar[0].getMessage()
    assert len(warn) == 1


def test_exhausted_asr_recovery_outside_admitted_source_evidence_names_the_quarantined_channel(monkeypatch, caplog):
    """A ladder exhausted bare names the preserved (asr_recovery, outside_admitted_source) evidence on the quarantined channel."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue = _queued_for_walk()
    attempts = _walk(queue, store, evidence_plan={1: {"stage": "asr_recovery", "reason": "outside_admitted_source"}})
    assert attempts == 5
    disposition, quar, ladder, guard, warn = _channel(caplog)
    assert not disposition and not ladder and not guard and len(quar) == 1
    assert "stage=asr_recovery" in quar[0].getMessage()
    assert "worker_reason=outside_admitted_source" in quar[0].getMessage()
    assert len(warn) == 1


def test_exhausted_asr_recovery_unknown_evidence_names_the_quarantined_channel(monkeypatch, caplog):
    """A ladder exhausted bare names the preserved (asr_recovery, unknown) evidence on the quarantined channel."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue = _queued_for_walk()
    attempts = _walk(queue, store, evidence_plan={1: {"stage": "asr_recovery", "reason": "unknown"}})
    assert attempts == 5
    disposition, quar, ladder, guard, warn = _channel(caplog)
    assert not disposition and not ladder and not guard and len(quar) == 1
    assert "stage=asr_recovery" in quar[0].getMessage()
    assert "worker_reason=unknown" in quar[0].getMessage()
    assert len(warn) == 1


def test_preserved_fetch_decode_staged_audio_invalid_diagnosis_names_the_disposition_channel_on_bare_exhaustion(
    monkeypatch, caplog
):
    """A (fetch_decode, staged_audio_invalid) diagnosis preserved on the job names the disposition channel."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue = _queued_for_walk()
    store.rows["jobs", "a"]["worker_failure_evidence"] = {"stage": "fetch_decode", "reason": "staged_audio_invalid"}
    attempts = _walk(queue, store)
    assert attempts == 5
    disposition, quar, ladder, guard, warn = _channel(caplog)
    assert not quar and not ladder and not guard and len(disposition) == 1
    assert disposition[0].levelno == logging.INFO
    assert "outcome=held_for_disposition" in disposition[0].getMessage()
    assert "stage=fetch_decode" in disposition[0].getMessage()
    assert "worker_reason=staged_audio_invalid" in disposition[0].getMessage()
    assert len(warn) == 1


def test_preserved_fetch_decode_retained_audio_invalid_diagnosis_names_the_disposition_channel_on_bare_exhaustion(
    monkeypatch, caplog
):
    """A (fetch_decode, retained_audio_invalid) diagnosis preserved on the job names the disposition channel."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue = _queued_for_walk()
    store.rows["jobs", "a"]["worker_failure_evidence"] = {"stage": "fetch_decode", "reason": "retained_audio_invalid"}
    attempts = _walk(queue, store)
    assert attempts == 5
    disposition, quar, ladder, guard, warn = _channel(caplog)
    assert not quar and not ladder and not guard and len(disposition) == 1
    assert disposition[0].levelno == logging.INFO
    assert "outcome=held_for_disposition" in disposition[0].getMessage()
    assert "stage=fetch_decode" in disposition[0].getMessage()
    assert "worker_reason=retained_audio_invalid" in disposition[0].getMessage()
    assert len(warn) == 1


def test_preserved_fetch_decode_decoded_duration_mismatch_diagnosis_names_the_disposition_channel_on_bare_exhaustion(
    monkeypatch, caplog
):
    """A (fetch_decode, decoded_duration_mismatch) diagnosis preserved on the job names the disposition channel."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue = _queued_for_walk()
    store.rows["jobs", "a"]["worker_failure_evidence"] = {
        "stage": "fetch_decode",
        "reason": "decoded_duration_mismatch",
    }
    attempts = _walk(queue, store)
    assert attempts == 5
    disposition, quar, ladder, guard, warn = _channel(caplog)
    assert not quar and not ladder and not guard and len(disposition) == 1
    assert disposition[0].levelno == logging.INFO
    assert "outcome=held_for_disposition" in disposition[0].getMessage()
    assert "stage=fetch_decode" in disposition[0].getMessage()
    assert "worker_reason=decoded_duration_mismatch" in disposition[0].getMessage()
    assert len(warn) == 1


def test_preserved_fetch_decode_word_shape_diagnosis_names_the_disposition_channel_on_bare_exhaustion(
    monkeypatch, caplog
):
    """A (fetch_decode, word_shape) diagnosis preserved on the job names the disposition channel."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue = _queued_for_walk()
    store.rows["jobs", "a"]["worker_failure_evidence"] = {"stage": "fetch_decode", "reason": "word_shape"}
    attempts = _walk(queue, store)
    assert attempts == 5
    disposition, quar, ladder, guard, warn = _channel(caplog)
    assert not quar and not ladder and not guard and len(disposition) == 1
    assert disposition[0].levelno == logging.INFO
    assert "outcome=held_for_disposition" in disposition[0].getMessage()
    assert "stage=fetch_decode" in disposition[0].getMessage()
    assert "worker_reason=word_shape" in disposition[0].getMessage()
    assert len(warn) == 1


def test_preserved_fetch_decode_word_clock_diagnosis_names_the_disposition_channel_on_bare_exhaustion(
    monkeypatch, caplog
):
    """A (fetch_decode, word_clock) diagnosis preserved on the job names the disposition channel."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue = _queued_for_walk()
    store.rows["jobs", "a"]["worker_failure_evidence"] = {"stage": "fetch_decode", "reason": "word_clock"}
    attempts = _walk(queue, store)
    assert attempts == 5
    disposition, quar, ladder, guard, warn = _channel(caplog)
    assert not quar and not ladder and not guard and len(disposition) == 1
    assert disposition[0].levelno == logging.INFO
    assert "outcome=held_for_disposition" in disposition[0].getMessage()
    assert "stage=fetch_decode" in disposition[0].getMessage()
    assert "worker_reason=word_clock" in disposition[0].getMessage()
    assert len(warn) == 1


def test_preserved_fetch_decode_word_sequence_diagnosis_names_the_disposition_channel_on_bare_exhaustion(
    monkeypatch, caplog
):
    """A (fetch_decode, word_sequence) diagnosis preserved on the job names the disposition channel."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue = _queued_for_walk()
    store.rows["jobs", "a"]["worker_failure_evidence"] = {"stage": "fetch_decode", "reason": "word_sequence"}
    attempts = _walk(queue, store)
    assert attempts == 5
    disposition, quar, ladder, guard, warn = _channel(caplog)
    assert not quar and not ladder and not guard and len(disposition) == 1
    assert disposition[0].levelno == logging.INFO
    assert "outcome=held_for_disposition" in disposition[0].getMessage()
    assert "stage=fetch_decode" in disposition[0].getMessage()
    assert "worker_reason=word_sequence" in disposition[0].getMessage()
    assert len(warn) == 1


def test_preserved_fetch_decode_vad_nonfinite_diagnosis_names_the_disposition_channel_on_bare_exhaustion(
    monkeypatch, caplog
):
    """A (fetch_decode, vad_nonfinite) diagnosis preserved on the job names the disposition channel."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue = _queued_for_walk()
    store.rows["jobs", "a"]["worker_failure_evidence"] = {"stage": "fetch_decode", "reason": "vad_nonfinite"}
    attempts = _walk(queue, store)
    assert attempts == 5
    disposition, quar, ladder, guard, warn = _channel(caplog)
    assert not quar and not ladder and not guard and len(disposition) == 1
    assert disposition[0].levelno == logging.INFO
    assert "outcome=held_for_disposition" in disposition[0].getMessage()
    assert "stage=fetch_decode" in disposition[0].getMessage()
    assert "worker_reason=vad_nonfinite" in disposition[0].getMessage()
    assert len(warn) == 1


def test_preserved_fetch_decode_vad_order_diagnosis_names_the_disposition_channel_on_bare_exhaustion(
    monkeypatch, caplog
):
    """A (fetch_decode, vad_order) diagnosis preserved on the job names the disposition channel."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue = _queued_for_walk()
    store.rows["jobs", "a"]["worker_failure_evidence"] = {"stage": "fetch_decode", "reason": "vad_order"}
    attempts = _walk(queue, store)
    assert attempts == 5
    disposition, quar, ladder, guard, warn = _channel(caplog)
    assert not quar and not ladder and not guard and len(disposition) == 1
    assert disposition[0].levelno == logging.INFO
    assert "outcome=held_for_disposition" in disposition[0].getMessage()
    assert "stage=fetch_decode" in disposition[0].getMessage()
    assert "worker_reason=vad_order" in disposition[0].getMessage()
    assert len(warn) == 1


def test_preserved_fetch_decode_vad_bounds_diagnosis_names_the_disposition_channel_on_bare_exhaustion(
    monkeypatch, caplog
):
    """A (fetch_decode, vad_bounds) diagnosis preserved on the job names the disposition channel."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue = _queued_for_walk()
    store.rows["jobs", "a"]["worker_failure_evidence"] = {"stage": "fetch_decode", "reason": "vad_bounds"}
    attempts = _walk(queue, store)
    assert attempts == 5
    disposition, quar, ladder, guard, warn = _channel(caplog)
    assert not quar and not ladder and not guard and len(disposition) == 1
    assert disposition[0].levelno == logging.INFO
    assert "outcome=held_for_disposition" in disposition[0].getMessage()
    assert "stage=fetch_decode" in disposition[0].getMessage()
    assert "worker_reason=vad_bounds" in disposition[0].getMessage()
    assert len(warn) == 1


def test_preserved_vad_windows_staged_audio_invalid_diagnosis_names_the_quarantined_channel_on_bare_exhaustion(
    monkeypatch, caplog
):
    """A (vad_windows, staged_audio_invalid) diagnosis preserved on the job names the quarantined channel."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue = _queued_for_walk()
    store.rows["jobs", "a"]["worker_failure_evidence"] = {"stage": "vad_windows", "reason": "staged_audio_invalid"}
    attempts = _walk(queue, store)
    assert attempts == 5
    disposition, quar, ladder, guard, warn = _channel(caplog)
    assert not disposition and not ladder and not guard and len(quar) == 1
    assert quar[0].levelno == logging.ERROR
    assert "reason=worker_failed" in quar[0].getMessage()
    assert "stage=vad_windows" in quar[0].getMessage()
    assert "worker_reason=staged_audio_invalid" in quar[0].getMessage()
    assert len(warn) == 1


def test_preserved_vad_windows_retained_audio_invalid_diagnosis_names_the_quarantined_channel_on_bare_exhaustion(
    monkeypatch, caplog
):
    """A (vad_windows, retained_audio_invalid) diagnosis preserved on the job names the quarantined channel."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue = _queued_for_walk()
    store.rows["jobs", "a"]["worker_failure_evidence"] = {"stage": "vad_windows", "reason": "retained_audio_invalid"}
    attempts = _walk(queue, store)
    assert attempts == 5
    disposition, quar, ladder, guard, warn = _channel(caplog)
    assert not disposition and not ladder and not guard and len(quar) == 1
    assert quar[0].levelno == logging.ERROR
    assert "reason=worker_failed" in quar[0].getMessage()
    assert "stage=vad_windows" in quar[0].getMessage()
    assert "worker_reason=retained_audio_invalid" in quar[0].getMessage()
    assert len(warn) == 1


def test_preserved_vad_windows_decoded_duration_mismatch_diagnosis_names_the_quarantined_channel_on_bare_exhaustion(
    monkeypatch, caplog
):
    """A (vad_windows, decoded_duration_mismatch) diagnosis preserved on the job names the quarantined channel."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue = _queued_for_walk()
    store.rows["jobs", "a"]["worker_failure_evidence"] = {"stage": "vad_windows", "reason": "decoded_duration_mismatch"}
    attempts = _walk(queue, store)
    assert attempts == 5
    disposition, quar, ladder, guard, warn = _channel(caplog)
    assert not disposition and not ladder and not guard and len(quar) == 1
    assert quar[0].levelno == logging.ERROR
    assert "reason=worker_failed" in quar[0].getMessage()
    assert "stage=vad_windows" in quar[0].getMessage()
    assert "worker_reason=decoded_duration_mismatch" in quar[0].getMessage()
    assert len(warn) == 1


def test_preserved_vad_windows_word_shape_diagnosis_names_the_disposition_channel_on_bare_exhaustion(
    monkeypatch, caplog
):
    """A (vad_windows, word_shape) diagnosis preserved on the job names the disposition channel."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue = _queued_for_walk()
    store.rows["jobs", "a"]["worker_failure_evidence"] = {"stage": "vad_windows", "reason": "word_shape"}
    attempts = _walk(queue, store)
    assert attempts == 5
    disposition, quar, ladder, guard, warn = _channel(caplog)
    assert not quar and not ladder and not guard and len(disposition) == 1
    assert disposition[0].levelno == logging.INFO
    assert "outcome=held_for_disposition" in disposition[0].getMessage()
    assert "stage=vad_windows" in disposition[0].getMessage()
    assert "worker_reason=word_shape" in disposition[0].getMessage()
    assert len(warn) == 1


def test_preserved_vad_windows_word_clock_diagnosis_names_the_disposition_channel_on_bare_exhaustion(
    monkeypatch, caplog
):
    """A (vad_windows, word_clock) diagnosis preserved on the job names the disposition channel."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue = _queued_for_walk()
    store.rows["jobs", "a"]["worker_failure_evidence"] = {"stage": "vad_windows", "reason": "word_clock"}
    attempts = _walk(queue, store)
    assert attempts == 5
    disposition, quar, ladder, guard, warn = _channel(caplog)
    assert not quar and not ladder and not guard and len(disposition) == 1
    assert disposition[0].levelno == logging.INFO
    assert "outcome=held_for_disposition" in disposition[0].getMessage()
    assert "stage=vad_windows" in disposition[0].getMessage()
    assert "worker_reason=word_clock" in disposition[0].getMessage()
    assert len(warn) == 1


def test_preserved_vad_windows_word_sequence_diagnosis_names_the_disposition_channel_on_bare_exhaustion(
    monkeypatch, caplog
):
    """A (vad_windows, word_sequence) diagnosis preserved on the job names the disposition channel."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue = _queued_for_walk()
    store.rows["jobs", "a"]["worker_failure_evidence"] = {"stage": "vad_windows", "reason": "word_sequence"}
    attempts = _walk(queue, store)
    assert attempts == 5
    disposition, quar, ladder, guard, warn = _channel(caplog)
    assert not quar and not ladder and not guard and len(disposition) == 1
    assert disposition[0].levelno == logging.INFO
    assert "outcome=held_for_disposition" in disposition[0].getMessage()
    assert "stage=vad_windows" in disposition[0].getMessage()
    assert "worker_reason=word_sequence" in disposition[0].getMessage()
    assert len(warn) == 1


def test_preserved_vad_windows_vad_nonfinite_diagnosis_names_the_disposition_channel_on_bare_exhaustion(
    monkeypatch, caplog
):
    """A (vad_windows, vad_nonfinite) diagnosis preserved on the job names the disposition channel."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue = _queued_for_walk()
    store.rows["jobs", "a"]["worker_failure_evidence"] = {"stage": "vad_windows", "reason": "vad_nonfinite"}
    attempts = _walk(queue, store)
    assert attempts == 5
    disposition, quar, ladder, guard, warn = _channel(caplog)
    assert not quar and not ladder and not guard and len(disposition) == 1
    assert disposition[0].levelno == logging.INFO
    assert "outcome=held_for_disposition" in disposition[0].getMessage()
    assert "stage=vad_windows" in disposition[0].getMessage()
    assert "worker_reason=vad_nonfinite" in disposition[0].getMessage()
    assert len(warn) == 1


def test_preserved_vad_windows_vad_order_diagnosis_names_the_disposition_channel_on_bare_exhaustion(
    monkeypatch, caplog
):
    """A (vad_windows, vad_order) diagnosis preserved on the job names the disposition channel."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue = _queued_for_walk()
    store.rows["jobs", "a"]["worker_failure_evidence"] = {"stage": "vad_windows", "reason": "vad_order"}
    attempts = _walk(queue, store)
    assert attempts == 5
    disposition, quar, ladder, guard, warn = _channel(caplog)
    assert not quar and not ladder and not guard and len(disposition) == 1
    assert disposition[0].levelno == logging.INFO
    assert "outcome=held_for_disposition" in disposition[0].getMessage()
    assert "stage=vad_windows" in disposition[0].getMessage()
    assert "worker_reason=vad_order" in disposition[0].getMessage()
    assert len(warn) == 1


def test_preserved_vad_windows_vad_bounds_diagnosis_names_the_disposition_channel_on_bare_exhaustion(
    monkeypatch, caplog
):
    """A (vad_windows, vad_bounds) diagnosis preserved on the job names the disposition channel."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue = _queued_for_walk()
    store.rows["jobs", "a"]["worker_failure_evidence"] = {"stage": "vad_windows", "reason": "vad_bounds"}
    attempts = _walk(queue, store)
    assert attempts == 5
    disposition, quar, ladder, guard, warn = _channel(caplog)
    assert not quar and not ladder and not guard and len(disposition) == 1
    assert disposition[0].levelno == logging.INFO
    assert "outcome=held_for_disposition" in disposition[0].getMessage()
    assert "stage=vad_windows" in disposition[0].getMessage()
    assert "worker_reason=vad_bounds" in disposition[0].getMessage()
    assert len(warn) == 1


def test_preserved_word_clocks_staged_audio_invalid_diagnosis_names_the_quarantined_channel_on_bare_exhaustion(
    monkeypatch, caplog
):
    """A (word_clocks, staged_audio_invalid) diagnosis preserved on the job names the quarantined channel."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue = _queued_for_walk()
    store.rows["jobs", "a"]["worker_failure_evidence"] = {"stage": "word_clocks", "reason": "staged_audio_invalid"}
    attempts = _walk(queue, store)
    assert attempts == 5
    disposition, quar, ladder, guard, warn = _channel(caplog)
    assert not disposition and not ladder and not guard and len(quar) == 1
    assert quar[0].levelno == logging.ERROR
    assert "reason=worker_failed" in quar[0].getMessage()
    assert "stage=word_clocks" in quar[0].getMessage()
    assert "worker_reason=staged_audio_invalid" in quar[0].getMessage()
    assert len(warn) == 1


def test_preserved_word_clocks_retained_audio_invalid_diagnosis_names_the_quarantined_channel_on_bare_exhaustion(
    monkeypatch, caplog
):
    """A (word_clocks, retained_audio_invalid) diagnosis preserved on the job names the quarantined channel."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue = _queued_for_walk()
    store.rows["jobs", "a"]["worker_failure_evidence"] = {"stage": "word_clocks", "reason": "retained_audio_invalid"}
    attempts = _walk(queue, store)
    assert attempts == 5
    disposition, quar, ladder, guard, warn = _channel(caplog)
    assert not disposition and not ladder and not guard and len(quar) == 1
    assert quar[0].levelno == logging.ERROR
    assert "reason=worker_failed" in quar[0].getMessage()
    assert "stage=word_clocks" in quar[0].getMessage()
    assert "worker_reason=retained_audio_invalid" in quar[0].getMessage()
    assert len(warn) == 1


def test_preserved_word_clocks_decoded_duration_mismatch_diagnosis_names_the_quarantined_channel_on_bare_exhaustion(
    monkeypatch, caplog
):
    """A (word_clocks, decoded_duration_mismatch) diagnosis preserved on the job names the quarantined channel."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue = _queued_for_walk()
    store.rows["jobs", "a"]["worker_failure_evidence"] = {"stage": "word_clocks", "reason": "decoded_duration_mismatch"}
    attempts = _walk(queue, store)
    assert attempts == 5
    disposition, quar, ladder, guard, warn = _channel(caplog)
    assert not disposition and not ladder and not guard and len(quar) == 1
    assert quar[0].levelno == logging.ERROR
    assert "reason=worker_failed" in quar[0].getMessage()
    assert "stage=word_clocks" in quar[0].getMessage()
    assert "worker_reason=decoded_duration_mismatch" in quar[0].getMessage()
    assert len(warn) == 1


def test_preserved_word_clocks_word_shape_diagnosis_names_the_disposition_channel_on_bare_exhaustion(
    monkeypatch, caplog
):
    """A (word_clocks, word_shape) diagnosis preserved on the job names the disposition channel."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue = _queued_for_walk()
    store.rows["jobs", "a"]["worker_failure_evidence"] = {"stage": "word_clocks", "reason": "word_shape"}
    attempts = _walk(queue, store)
    assert attempts == 5
    disposition, quar, ladder, guard, warn = _channel(caplog)
    assert not quar and not ladder and not guard and len(disposition) == 1
    assert disposition[0].levelno == logging.INFO
    assert "outcome=held_for_disposition" in disposition[0].getMessage()
    assert "stage=word_clocks" in disposition[0].getMessage()
    assert "worker_reason=word_shape" in disposition[0].getMessage()
    assert len(warn) == 1


def test_preserved_word_clocks_word_clock_diagnosis_names_the_disposition_channel_on_bare_exhaustion(
    monkeypatch, caplog
):
    """A (word_clocks, word_clock) diagnosis preserved on the job names the disposition channel."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue = _queued_for_walk()
    store.rows["jobs", "a"]["worker_failure_evidence"] = {"stage": "word_clocks", "reason": "word_clock"}
    attempts = _walk(queue, store)
    assert attempts == 5
    disposition, quar, ladder, guard, warn = _channel(caplog)
    assert not quar and not ladder and not guard and len(disposition) == 1
    assert disposition[0].levelno == logging.INFO
    assert "outcome=held_for_disposition" in disposition[0].getMessage()
    assert "stage=word_clocks" in disposition[0].getMessage()
    assert "worker_reason=word_clock" in disposition[0].getMessage()
    assert len(warn) == 1


def test_preserved_word_clocks_word_sequence_diagnosis_names_the_disposition_channel_on_bare_exhaustion(
    monkeypatch, caplog
):
    """A (word_clocks, word_sequence) diagnosis preserved on the job names the disposition channel."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue = _queued_for_walk()
    store.rows["jobs", "a"]["worker_failure_evidence"] = {"stage": "word_clocks", "reason": "word_sequence"}
    attempts = _walk(queue, store)
    assert attempts == 5
    disposition, quar, ladder, guard, warn = _channel(caplog)
    assert not quar and not ladder and not guard and len(disposition) == 1
    assert disposition[0].levelno == logging.INFO
    assert "outcome=held_for_disposition" in disposition[0].getMessage()
    assert "stage=word_clocks" in disposition[0].getMessage()
    assert "worker_reason=word_sequence" in disposition[0].getMessage()
    assert len(warn) == 1


def test_preserved_word_clocks_vad_nonfinite_diagnosis_names_the_disposition_channel_on_bare_exhaustion(
    monkeypatch, caplog
):
    """A (word_clocks, vad_nonfinite) diagnosis preserved on the job names the disposition channel."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue = _queued_for_walk()
    store.rows["jobs", "a"]["worker_failure_evidence"] = {"stage": "word_clocks", "reason": "vad_nonfinite"}
    attempts = _walk(queue, store)
    assert attempts == 5
    disposition, quar, ladder, guard, warn = _channel(caplog)
    assert not quar and not ladder and not guard and len(disposition) == 1
    assert disposition[0].levelno == logging.INFO
    assert "outcome=held_for_disposition" in disposition[0].getMessage()
    assert "stage=word_clocks" in disposition[0].getMessage()
    assert "worker_reason=vad_nonfinite" in disposition[0].getMessage()
    assert len(warn) == 1


def test_preserved_word_clocks_vad_order_diagnosis_names_the_disposition_channel_on_bare_exhaustion(
    monkeypatch, caplog
):
    """A (word_clocks, vad_order) diagnosis preserved on the job names the disposition channel."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue = _queued_for_walk()
    store.rows["jobs", "a"]["worker_failure_evidence"] = {"stage": "word_clocks", "reason": "vad_order"}
    attempts = _walk(queue, store)
    assert attempts == 5
    disposition, quar, ladder, guard, warn = _channel(caplog)
    assert not quar and not ladder and not guard and len(disposition) == 1
    assert disposition[0].levelno == logging.INFO
    assert "outcome=held_for_disposition" in disposition[0].getMessage()
    assert "stage=word_clocks" in disposition[0].getMessage()
    assert "worker_reason=vad_order" in disposition[0].getMessage()
    assert len(warn) == 1


def test_preserved_word_clocks_vad_bounds_diagnosis_names_the_disposition_channel_on_bare_exhaustion(
    monkeypatch, caplog
):
    """A (word_clocks, vad_bounds) diagnosis preserved on the job names the disposition channel."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue = _queued_for_walk()
    store.rows["jobs", "a"]["worker_failure_evidence"] = {"stage": "word_clocks", "reason": "vad_bounds"}
    attempts = _walk(queue, store)
    assert attempts == 5
    disposition, quar, ladder, guard, warn = _channel(caplog)
    assert not quar and not ladder and not guard and len(disposition) == 1
    assert disposition[0].levelno == logging.INFO
    assert "outcome=held_for_disposition" in disposition[0].getMessage()
    assert "stage=word_clocks" in disposition[0].getMessage()
    assert "worker_reason=vad_bounds" in disposition[0].getMessage()
    assert len(warn) == 1


def test_preserved_assemble_words_staged_audio_invalid_diagnosis_names_the_quarantined_channel_on_bare_exhaustion(
    monkeypatch, caplog
):
    """A (assemble_words, staged_audio_invalid) diagnosis preserved on the job names the quarantined channel."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue = _queued_for_walk()
    store.rows["jobs", "a"]["worker_failure_evidence"] = {"stage": "assemble_words", "reason": "staged_audio_invalid"}
    attempts = _walk(queue, store)
    assert attempts == 5
    disposition, quar, ladder, guard, warn = _channel(caplog)
    assert not disposition and not ladder and not guard and len(quar) == 1
    assert quar[0].levelno == logging.ERROR
    assert "reason=worker_failed" in quar[0].getMessage()
    assert "stage=assemble_words" in quar[0].getMessage()
    assert "worker_reason=staged_audio_invalid" in quar[0].getMessage()
    assert len(warn) == 1


def test_preserved_assemble_words_retained_audio_invalid_diagnosis_names_the_quarantined_channel_on_bare_exhaustion(
    monkeypatch, caplog
):
    """A (assemble_words, retained_audio_invalid) diagnosis preserved on the job names the quarantined channel."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue = _queued_for_walk()
    store.rows["jobs", "a"]["worker_failure_evidence"] = {"stage": "assemble_words", "reason": "retained_audio_invalid"}
    attempts = _walk(queue, store)
    assert attempts == 5
    disposition, quar, ladder, guard, warn = _channel(caplog)
    assert not disposition and not ladder and not guard and len(quar) == 1
    assert quar[0].levelno == logging.ERROR
    assert "reason=worker_failed" in quar[0].getMessage()
    assert "stage=assemble_words" in quar[0].getMessage()
    assert "worker_reason=retained_audio_invalid" in quar[0].getMessage()
    assert len(warn) == 1


def test_preserved_assemble_words_decoded_duration_mismatch_diagnosis_names_the_quarantined_channel_on_bare_exhaustion(
    monkeypatch, caplog
):
    """A (assemble_words, decoded_duration_mismatch) diagnosis preserved on the job names the quarantined channel."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue = _queued_for_walk()
    store.rows["jobs", "a"]["worker_failure_evidence"] = {
        "stage": "assemble_words",
        "reason": "decoded_duration_mismatch",
    }
    attempts = _walk(queue, store)
    assert attempts == 5
    disposition, quar, ladder, guard, warn = _channel(caplog)
    assert not disposition and not ladder and not guard and len(quar) == 1
    assert quar[0].levelno == logging.ERROR
    assert "reason=worker_failed" in quar[0].getMessage()
    assert "stage=assemble_words" in quar[0].getMessage()
    assert "worker_reason=decoded_duration_mismatch" in quar[0].getMessage()
    assert len(warn) == 1


def test_preserved_assemble_words_word_shape_diagnosis_names_the_disposition_channel_on_bare_exhaustion(
    monkeypatch, caplog
):
    """A (assemble_words, word_shape) diagnosis preserved on the job names the disposition channel."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue = _queued_for_walk()
    store.rows["jobs", "a"]["worker_failure_evidence"] = {"stage": "assemble_words", "reason": "word_shape"}
    attempts = _walk(queue, store)
    assert attempts == 5
    disposition, quar, ladder, guard, warn = _channel(caplog)
    assert not quar and not ladder and not guard and len(disposition) == 1
    assert disposition[0].levelno == logging.INFO
    assert "outcome=held_for_disposition" in disposition[0].getMessage()
    assert "stage=assemble_words" in disposition[0].getMessage()
    assert "worker_reason=word_shape" in disposition[0].getMessage()
    assert len(warn) == 1


def test_preserved_assemble_words_word_clock_diagnosis_names_the_disposition_channel_on_bare_exhaustion(
    monkeypatch, caplog
):
    """A (assemble_words, word_clock) diagnosis preserved on the job names the disposition channel."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue = _queued_for_walk()
    store.rows["jobs", "a"]["worker_failure_evidence"] = {"stage": "assemble_words", "reason": "word_clock"}
    attempts = _walk(queue, store)
    assert attempts == 5
    disposition, quar, ladder, guard, warn = _channel(caplog)
    assert not quar and not ladder and not guard and len(disposition) == 1
    assert disposition[0].levelno == logging.INFO
    assert "outcome=held_for_disposition" in disposition[0].getMessage()
    assert "stage=assemble_words" in disposition[0].getMessage()
    assert "worker_reason=word_clock" in disposition[0].getMessage()
    assert len(warn) == 1


def test_preserved_assemble_words_word_sequence_diagnosis_names_the_disposition_channel_on_bare_exhaustion(
    monkeypatch, caplog
):
    """A (assemble_words, word_sequence) diagnosis preserved on the job names the disposition channel."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue = _queued_for_walk()
    store.rows["jobs", "a"]["worker_failure_evidence"] = {"stage": "assemble_words", "reason": "word_sequence"}
    attempts = _walk(queue, store)
    assert attempts == 5
    disposition, quar, ladder, guard, warn = _channel(caplog)
    assert not quar and not ladder and not guard and len(disposition) == 1
    assert disposition[0].levelno == logging.INFO
    assert "outcome=held_for_disposition" in disposition[0].getMessage()
    assert "stage=assemble_words" in disposition[0].getMessage()
    assert "worker_reason=word_sequence" in disposition[0].getMessage()
    assert len(warn) == 1


def test_preserved_assemble_words_vad_nonfinite_diagnosis_names_the_disposition_channel_on_bare_exhaustion(
    monkeypatch, caplog
):
    """A (assemble_words, vad_nonfinite) diagnosis preserved on the job names the disposition channel."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue = _queued_for_walk()
    store.rows["jobs", "a"]["worker_failure_evidence"] = {"stage": "assemble_words", "reason": "vad_nonfinite"}
    attempts = _walk(queue, store)
    assert attempts == 5
    disposition, quar, ladder, guard, warn = _channel(caplog)
    assert not quar and not ladder and not guard and len(disposition) == 1
    assert disposition[0].levelno == logging.INFO
    assert "outcome=held_for_disposition" in disposition[0].getMessage()
    assert "stage=assemble_words" in disposition[0].getMessage()
    assert "worker_reason=vad_nonfinite" in disposition[0].getMessage()
    assert len(warn) == 1


def test_preserved_assemble_words_vad_order_diagnosis_names_the_disposition_channel_on_bare_exhaustion(
    monkeypatch, caplog
):
    """A (assemble_words, vad_order) diagnosis preserved on the job names the disposition channel."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue = _queued_for_walk()
    store.rows["jobs", "a"]["worker_failure_evidence"] = {"stage": "assemble_words", "reason": "vad_order"}
    attempts = _walk(queue, store)
    assert attempts == 5
    disposition, quar, ladder, guard, warn = _channel(caplog)
    assert not quar and not ladder and not guard and len(disposition) == 1
    assert disposition[0].levelno == logging.INFO
    assert "outcome=held_for_disposition" in disposition[0].getMessage()
    assert "stage=assemble_words" in disposition[0].getMessage()
    assert "worker_reason=vad_order" in disposition[0].getMessage()
    assert len(warn) == 1


def test_preserved_assemble_words_vad_bounds_diagnosis_names_the_disposition_channel_on_bare_exhaustion(
    monkeypatch, caplog
):
    """A (assemble_words, vad_bounds) diagnosis preserved on the job names the disposition channel."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue = _queued_for_walk()
    store.rows["jobs", "a"]["worker_failure_evidence"] = {"stage": "assemble_words", "reason": "vad_bounds"}
    attempts = _walk(queue, store)
    assert attempts == 5
    disposition, quar, ladder, guard, warn = _channel(caplog)
    assert not quar and not ladder and not guard and len(disposition) == 1
    assert disposition[0].levelno == logging.INFO
    assert "outcome=held_for_disposition" in disposition[0].getMessage()
    assert "stage=assemble_words" in disposition[0].getMessage()
    assert "worker_reason=vad_bounds" in disposition[0].getMessage()
    assert len(warn) == 1


def test_preserved_asr_recovery_staged_audio_invalid_diagnosis_names_the_quarantined_channel_on_bare_exhaustion(
    monkeypatch, caplog
):
    """A (asr_recovery, staged_audio_invalid) diagnosis preserved on the job names the quarantined channel."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue = _queued_for_walk()
    store.rows["jobs", "a"]["worker_failure_evidence"] = {"stage": "asr_recovery", "reason": "staged_audio_invalid"}
    attempts = _walk(queue, store)
    assert attempts == 5
    disposition, quar, ladder, guard, warn = _channel(caplog)
    assert not disposition and not ladder and not guard and len(quar) == 1
    assert quar[0].levelno == logging.ERROR
    assert "reason=worker_failed" in quar[0].getMessage()
    assert "stage=asr_recovery" in quar[0].getMessage()
    assert "worker_reason=staged_audio_invalid" in quar[0].getMessage()
    assert len(warn) == 1


def test_preserved_asr_recovery_retained_audio_invalid_diagnosis_names_the_quarantined_channel_on_bare_exhaustion(
    monkeypatch, caplog
):
    """A (asr_recovery, retained_audio_invalid) diagnosis preserved on the job names the quarantined channel."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue = _queued_for_walk()
    store.rows["jobs", "a"]["worker_failure_evidence"] = {"stage": "asr_recovery", "reason": "retained_audio_invalid"}
    attempts = _walk(queue, store)
    assert attempts == 5
    disposition, quar, ladder, guard, warn = _channel(caplog)
    assert not disposition and not ladder and not guard and len(quar) == 1
    assert quar[0].levelno == logging.ERROR
    assert "reason=worker_failed" in quar[0].getMessage()
    assert "stage=asr_recovery" in quar[0].getMessage()
    assert "worker_reason=retained_audio_invalid" in quar[0].getMessage()
    assert len(warn) == 1


def test_preserved_asr_recovery_decoded_duration_mismatch_diagnosis_names_the_quarantined_channel_on_bare_exhaustion(
    monkeypatch, caplog
):
    """A (asr_recovery, decoded_duration_mismatch) diagnosis preserved on the job names the quarantined channel."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue = _queued_for_walk()
    store.rows["jobs", "a"]["worker_failure_evidence"] = {
        "stage": "asr_recovery",
        "reason": "decoded_duration_mismatch",
    }
    attempts = _walk(queue, store)
    assert attempts == 5
    disposition, quar, ladder, guard, warn = _channel(caplog)
    assert not disposition and not ladder and not guard and len(quar) == 1
    assert quar[0].levelno == logging.ERROR
    assert "reason=worker_failed" in quar[0].getMessage()
    assert "stage=asr_recovery" in quar[0].getMessage()
    assert "worker_reason=decoded_duration_mismatch" in quar[0].getMessage()
    assert len(warn) == 1


def test_preserved_asr_recovery_word_shape_diagnosis_names_the_disposition_channel_on_bare_exhaustion(
    monkeypatch, caplog
):
    """A (asr_recovery, word_shape) diagnosis preserved on the job names the disposition channel."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue = _queued_for_walk()
    store.rows["jobs", "a"]["worker_failure_evidence"] = {"stage": "asr_recovery", "reason": "word_shape"}
    attempts = _walk(queue, store)
    assert attempts == 5
    disposition, quar, ladder, guard, warn = _channel(caplog)
    assert not quar and not ladder and not guard and len(disposition) == 1
    assert disposition[0].levelno == logging.INFO
    assert "outcome=held_for_disposition" in disposition[0].getMessage()
    assert "stage=asr_recovery" in disposition[0].getMessage()
    assert "worker_reason=word_shape" in disposition[0].getMessage()
    assert len(warn) == 1


def test_preserved_asr_recovery_word_clock_diagnosis_names_the_disposition_channel_on_bare_exhaustion(
    monkeypatch, caplog
):
    """A (asr_recovery, word_clock) diagnosis preserved on the job names the disposition channel."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue = _queued_for_walk()
    store.rows["jobs", "a"]["worker_failure_evidence"] = {"stage": "asr_recovery", "reason": "word_clock"}
    attempts = _walk(queue, store)
    assert attempts == 5
    disposition, quar, ladder, guard, warn = _channel(caplog)
    assert not quar and not ladder and not guard and len(disposition) == 1
    assert disposition[0].levelno == logging.INFO
    assert "outcome=held_for_disposition" in disposition[0].getMessage()
    assert "stage=asr_recovery" in disposition[0].getMessage()
    assert "worker_reason=word_clock" in disposition[0].getMessage()
    assert len(warn) == 1


def test_preserved_asr_recovery_word_sequence_diagnosis_names_the_disposition_channel_on_bare_exhaustion(
    monkeypatch, caplog
):
    """A (asr_recovery, word_sequence) diagnosis preserved on the job names the disposition channel."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue = _queued_for_walk()
    store.rows["jobs", "a"]["worker_failure_evidence"] = {"stage": "asr_recovery", "reason": "word_sequence"}
    attempts = _walk(queue, store)
    assert attempts == 5
    disposition, quar, ladder, guard, warn = _channel(caplog)
    assert not quar and not ladder and not guard and len(disposition) == 1
    assert disposition[0].levelno == logging.INFO
    assert "outcome=held_for_disposition" in disposition[0].getMessage()
    assert "stage=asr_recovery" in disposition[0].getMessage()
    assert "worker_reason=word_sequence" in disposition[0].getMessage()
    assert len(warn) == 1


def test_preserved_asr_recovery_vad_nonfinite_diagnosis_names_the_disposition_channel_on_bare_exhaustion(
    monkeypatch, caplog
):
    """A (asr_recovery, vad_nonfinite) diagnosis preserved on the job names the disposition channel."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue = _queued_for_walk()
    store.rows["jobs", "a"]["worker_failure_evidence"] = {"stage": "asr_recovery", "reason": "vad_nonfinite"}
    attempts = _walk(queue, store)
    assert attempts == 5
    disposition, quar, ladder, guard, warn = _channel(caplog)
    assert not quar and not ladder and not guard and len(disposition) == 1
    assert disposition[0].levelno == logging.INFO
    assert "outcome=held_for_disposition" in disposition[0].getMessage()
    assert "stage=asr_recovery" in disposition[0].getMessage()
    assert "worker_reason=vad_nonfinite" in disposition[0].getMessage()
    assert len(warn) == 1


def test_preserved_asr_recovery_vad_order_diagnosis_names_the_disposition_channel_on_bare_exhaustion(
    monkeypatch, caplog
):
    """A (asr_recovery, vad_order) diagnosis preserved on the job names the disposition channel."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue = _queued_for_walk()
    store.rows["jobs", "a"]["worker_failure_evidence"] = {"stage": "asr_recovery", "reason": "vad_order"}
    attempts = _walk(queue, store)
    assert attempts == 5
    disposition, quar, ladder, guard, warn = _channel(caplog)
    assert not quar and not ladder and not guard and len(disposition) == 1
    assert disposition[0].levelno == logging.INFO
    assert "outcome=held_for_disposition" in disposition[0].getMessage()
    assert "stage=asr_recovery" in disposition[0].getMessage()
    assert "worker_reason=vad_order" in disposition[0].getMessage()
    assert len(warn) == 1


def test_preserved_asr_recovery_vad_bounds_diagnosis_names_the_disposition_channel_on_bare_exhaustion(
    monkeypatch, caplog
):
    """A (asr_recovery, vad_bounds) diagnosis preserved on the job names the disposition channel."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue = _queued_for_walk()
    store.rows["jobs", "a"]["worker_failure_evidence"] = {"stage": "asr_recovery", "reason": "vad_bounds"}
    attempts = _walk(queue, store)
    assert attempts == 5
    disposition, quar, ladder, guard, warn = _channel(caplog)
    assert not quar and not ladder and not guard and len(disposition) == 1
    assert disposition[0].levelno == logging.INFO
    assert "outcome=held_for_disposition" in disposition[0].getMessage()
    assert "stage=asr_recovery" in disposition[0].getMessage()
    assert "worker_reason=vad_bounds" in disposition[0].getMessage()
    assert len(warn) == 1
