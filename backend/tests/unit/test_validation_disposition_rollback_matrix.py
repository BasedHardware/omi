# Failure-Class: FC-terminal-validation-disposition-misbooked-as-worker-fault
"""Rolling the disposition switch back restores every fault line it demoted.

Under ``BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED=false`` the
flagged verdicts ride the bounded GPU retry ladder again and book ERROR at
both sites — the worker boundary and the terminal quarantine — while the
unconditional trio keeps its designed INFO handoff (its chain end never
depended on the switch). The parse contract of the switch itself is pinned,
the sibling empty-ladder and safety switches never leak into the disposition
decision, and the admitted-source refusal keeps its fault line under every
combination.
"""

import logging
import time

import pytest

from config.batch_pipeline import worker_validation_disposition_enabled
from tests.unit.test_batch_pipeline_scheduler import MemoryStore, item as sched_item
from utils.batch_pipeline.contracts import Priority
from utils.batch_pipeline.scheduler import Scheduler

STAGES = ('fetch_decode', 'vad_windows', 'word_clocks', 'assemble_words', 'asr_recovery')
FLAGGED = ('word_shape', 'word_clock', 'word_sequence', 'vad_nonfinite', 'vad_order', 'vad_bounds')
TRIO = ('staged_audio_invalid', 'retained_audio_invalid', 'decoded_duration_mismatch')


def _queued(monkeypatch, position="false"):
    monkeypatch.setenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", position)
    store = MemoryStore()
    queue = Scheduler(store)
    work = sched_item("a", owner="rollback-disp-owner", duration=30, priority=Priority.FRESH)
    assert queue.enqueue(work, time.time())
    lease = queue.pull(time.time())[0]
    return store, queue, lease


def _fail(queue, lease, **kwargs):
    return queue.fail(lease.item.segment_id, lease.token, time.time() + 100.0, **kwargs)


def _channel(caplog):
    disposition = [r for r in caplog.records if "event=batch_validation_disposition" in r.getMessage()]
    quar = [r for r in caplog.records if "event=batch_quarantined" in r.getMessage()]
    return disposition, quar


def test_rollback_fetch_decode_word_shape_keeps_the_quarantine_error(monkeypatch, caplog):
    """Switch off: a (fetch_decode, word_shape) terminal diagnosis books the ERROR quarantine again."""
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued(monkeypatch)
    assert _fail(queue, lease, worker_failure={"stage": "fetch_decode", "reason": "word_shape"}) is True
    disposition, quar = _channel(caplog)
    assert not disposition and len(quar) == 1
    assert quar[0].levelno == logging.ERROR
    message = quar[0].getMessage()
    assert "reason=worker_failed" in message
    assert "stage=fetch_decode" in message and "worker_reason=word_shape" in message
    job = store.probe("jobs", "a")
    assert job["state"] == "quarantined" and job["worker_failure"] == {"stage": "fetch_decode", "reason": "word_shape"}


def test_rollback_fetch_decode_word_clock_keeps_the_quarantine_error(monkeypatch, caplog):
    """Switch off: a (fetch_decode, word_clock) terminal diagnosis books the ERROR quarantine again."""
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued(monkeypatch)
    assert _fail(queue, lease, worker_failure={"stage": "fetch_decode", "reason": "word_clock"}) is True
    disposition, quar = _channel(caplog)
    assert not disposition and len(quar) == 1
    assert quar[0].levelno == logging.ERROR
    message = quar[0].getMessage()
    assert "reason=worker_failed" in message
    assert "stage=fetch_decode" in message and "worker_reason=word_clock" in message
    job = store.probe("jobs", "a")
    assert job["state"] == "quarantined" and job["worker_failure"] == {"stage": "fetch_decode", "reason": "word_clock"}


def test_rollback_fetch_decode_word_sequence_keeps_the_quarantine_error(monkeypatch, caplog):
    """Switch off: a (fetch_decode, word_sequence) terminal diagnosis books the ERROR quarantine again."""
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued(monkeypatch)
    assert _fail(queue, lease, worker_failure={"stage": "fetch_decode", "reason": "word_sequence"}) is True
    disposition, quar = _channel(caplog)
    assert not disposition and len(quar) == 1
    assert quar[0].levelno == logging.ERROR
    message = quar[0].getMessage()
    assert "reason=worker_failed" in message
    assert "stage=fetch_decode" in message and "worker_reason=word_sequence" in message
    job = store.probe("jobs", "a")
    assert job["state"] == "quarantined" and job["worker_failure"] == {
        "stage": "fetch_decode",
        "reason": "word_sequence",
    }


def test_rollback_fetch_decode_vad_nonfinite_keeps_the_quarantine_error(monkeypatch, caplog):
    """Switch off: a (fetch_decode, vad_nonfinite) terminal diagnosis books the ERROR quarantine again."""
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued(monkeypatch)
    assert _fail(queue, lease, worker_failure={"stage": "fetch_decode", "reason": "vad_nonfinite"}) is True
    disposition, quar = _channel(caplog)
    assert not disposition and len(quar) == 1
    assert quar[0].levelno == logging.ERROR
    message = quar[0].getMessage()
    assert "reason=worker_failed" in message
    assert "stage=fetch_decode" in message and "worker_reason=vad_nonfinite" in message
    job = store.probe("jobs", "a")
    assert job["state"] == "quarantined" and job["worker_failure"] == {
        "stage": "fetch_decode",
        "reason": "vad_nonfinite",
    }


def test_rollback_fetch_decode_vad_order_keeps_the_quarantine_error(monkeypatch, caplog):
    """Switch off: a (fetch_decode, vad_order) terminal diagnosis books the ERROR quarantine again."""
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued(monkeypatch)
    assert _fail(queue, lease, worker_failure={"stage": "fetch_decode", "reason": "vad_order"}) is True
    disposition, quar = _channel(caplog)
    assert not disposition and len(quar) == 1
    assert quar[0].levelno == logging.ERROR
    message = quar[0].getMessage()
    assert "reason=worker_failed" in message
    assert "stage=fetch_decode" in message and "worker_reason=vad_order" in message
    job = store.probe("jobs", "a")
    assert job["state"] == "quarantined" and job["worker_failure"] == {"stage": "fetch_decode", "reason": "vad_order"}


def test_rollback_fetch_decode_vad_bounds_keeps_the_quarantine_error(monkeypatch, caplog):
    """Switch off: a (fetch_decode, vad_bounds) terminal diagnosis books the ERROR quarantine again."""
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued(monkeypatch)
    assert _fail(queue, lease, worker_failure={"stage": "fetch_decode", "reason": "vad_bounds"}) is True
    disposition, quar = _channel(caplog)
    assert not disposition and len(quar) == 1
    assert quar[0].levelno == logging.ERROR
    message = quar[0].getMessage()
    assert "reason=worker_failed" in message
    assert "stage=fetch_decode" in message and "worker_reason=vad_bounds" in message
    job = store.probe("jobs", "a")
    assert job["state"] == "quarantined" and job["worker_failure"] == {"stage": "fetch_decode", "reason": "vad_bounds"}


def test_rollback_vad_windows_word_shape_keeps_the_quarantine_error(monkeypatch, caplog):
    """Switch off: a (vad_windows, word_shape) terminal diagnosis books the ERROR quarantine again."""
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued(monkeypatch)
    assert _fail(queue, lease, worker_failure={"stage": "vad_windows", "reason": "word_shape"}) is True
    disposition, quar = _channel(caplog)
    assert not disposition and len(quar) == 1
    assert quar[0].levelno == logging.ERROR
    message = quar[0].getMessage()
    assert "reason=worker_failed" in message
    assert "stage=vad_windows" in message and "worker_reason=word_shape" in message
    job = store.probe("jobs", "a")
    assert job["state"] == "quarantined" and job["worker_failure"] == {"stage": "vad_windows", "reason": "word_shape"}


def test_rollback_vad_windows_word_clock_keeps_the_quarantine_error(monkeypatch, caplog):
    """Switch off: a (vad_windows, word_clock) terminal diagnosis books the ERROR quarantine again."""
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued(monkeypatch)
    assert _fail(queue, lease, worker_failure={"stage": "vad_windows", "reason": "word_clock"}) is True
    disposition, quar = _channel(caplog)
    assert not disposition and len(quar) == 1
    assert quar[0].levelno == logging.ERROR
    message = quar[0].getMessage()
    assert "reason=worker_failed" in message
    assert "stage=vad_windows" in message and "worker_reason=word_clock" in message
    job = store.probe("jobs", "a")
    assert job["state"] == "quarantined" and job["worker_failure"] == {"stage": "vad_windows", "reason": "word_clock"}


def test_rollback_vad_windows_word_sequence_keeps_the_quarantine_error(monkeypatch, caplog):
    """Switch off: a (vad_windows, word_sequence) terminal diagnosis books the ERROR quarantine again."""
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued(monkeypatch)
    assert _fail(queue, lease, worker_failure={"stage": "vad_windows", "reason": "word_sequence"}) is True
    disposition, quar = _channel(caplog)
    assert not disposition and len(quar) == 1
    assert quar[0].levelno == logging.ERROR
    message = quar[0].getMessage()
    assert "reason=worker_failed" in message
    assert "stage=vad_windows" in message and "worker_reason=word_sequence" in message
    job = store.probe("jobs", "a")
    assert job["state"] == "quarantined" and job["worker_failure"] == {
        "stage": "vad_windows",
        "reason": "word_sequence",
    }


def test_rollback_vad_windows_vad_nonfinite_keeps_the_quarantine_error(monkeypatch, caplog):
    """Switch off: a (vad_windows, vad_nonfinite) terminal diagnosis books the ERROR quarantine again."""
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued(monkeypatch)
    assert _fail(queue, lease, worker_failure={"stage": "vad_windows", "reason": "vad_nonfinite"}) is True
    disposition, quar = _channel(caplog)
    assert not disposition and len(quar) == 1
    assert quar[0].levelno == logging.ERROR
    message = quar[0].getMessage()
    assert "reason=worker_failed" in message
    assert "stage=vad_windows" in message and "worker_reason=vad_nonfinite" in message
    job = store.probe("jobs", "a")
    assert job["state"] == "quarantined" and job["worker_failure"] == {
        "stage": "vad_windows",
        "reason": "vad_nonfinite",
    }


def test_rollback_vad_windows_vad_order_keeps_the_quarantine_error(monkeypatch, caplog):
    """Switch off: a (vad_windows, vad_order) terminal diagnosis books the ERROR quarantine again."""
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued(monkeypatch)
    assert _fail(queue, lease, worker_failure={"stage": "vad_windows", "reason": "vad_order"}) is True
    disposition, quar = _channel(caplog)
    assert not disposition and len(quar) == 1
    assert quar[0].levelno == logging.ERROR
    message = quar[0].getMessage()
    assert "reason=worker_failed" in message
    assert "stage=vad_windows" in message and "worker_reason=vad_order" in message
    job = store.probe("jobs", "a")
    assert job["state"] == "quarantined" and job["worker_failure"] == {"stage": "vad_windows", "reason": "vad_order"}


def test_rollback_vad_windows_vad_bounds_keeps_the_quarantine_error(monkeypatch, caplog):
    """Switch off: a (vad_windows, vad_bounds) terminal diagnosis books the ERROR quarantine again."""
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued(monkeypatch)
    assert _fail(queue, lease, worker_failure={"stage": "vad_windows", "reason": "vad_bounds"}) is True
    disposition, quar = _channel(caplog)
    assert not disposition and len(quar) == 1
    assert quar[0].levelno == logging.ERROR
    message = quar[0].getMessage()
    assert "reason=worker_failed" in message
    assert "stage=vad_windows" in message and "worker_reason=vad_bounds" in message
    job = store.probe("jobs", "a")
    assert job["state"] == "quarantined" and job["worker_failure"] == {"stage": "vad_windows", "reason": "vad_bounds"}


def test_rollback_word_clocks_word_shape_keeps_the_quarantine_error(monkeypatch, caplog):
    """Switch off: a (word_clocks, word_shape) terminal diagnosis books the ERROR quarantine again."""
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued(monkeypatch)
    assert _fail(queue, lease, worker_failure={"stage": "word_clocks", "reason": "word_shape"}) is True
    disposition, quar = _channel(caplog)
    assert not disposition and len(quar) == 1
    assert quar[0].levelno == logging.ERROR
    message = quar[0].getMessage()
    assert "reason=worker_failed" in message
    assert "stage=word_clocks" in message and "worker_reason=word_shape" in message
    job = store.probe("jobs", "a")
    assert job["state"] == "quarantined" and job["worker_failure"] == {"stage": "word_clocks", "reason": "word_shape"}


def test_rollback_word_clocks_word_clock_keeps_the_quarantine_error(monkeypatch, caplog):
    """Switch off: a (word_clocks, word_clock) terminal diagnosis books the ERROR quarantine again."""
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued(monkeypatch)
    assert _fail(queue, lease, worker_failure={"stage": "word_clocks", "reason": "word_clock"}) is True
    disposition, quar = _channel(caplog)
    assert not disposition and len(quar) == 1
    assert quar[0].levelno == logging.ERROR
    message = quar[0].getMessage()
    assert "reason=worker_failed" in message
    assert "stage=word_clocks" in message and "worker_reason=word_clock" in message
    job = store.probe("jobs", "a")
    assert job["state"] == "quarantined" and job["worker_failure"] == {"stage": "word_clocks", "reason": "word_clock"}


def test_rollback_word_clocks_word_sequence_keeps_the_quarantine_error(monkeypatch, caplog):
    """Switch off: a (word_clocks, word_sequence) terminal diagnosis books the ERROR quarantine again."""
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued(monkeypatch)
    assert _fail(queue, lease, worker_failure={"stage": "word_clocks", "reason": "word_sequence"}) is True
    disposition, quar = _channel(caplog)
    assert not disposition and len(quar) == 1
    assert quar[0].levelno == logging.ERROR
    message = quar[0].getMessage()
    assert "reason=worker_failed" in message
    assert "stage=word_clocks" in message and "worker_reason=word_sequence" in message
    job = store.probe("jobs", "a")
    assert job["state"] == "quarantined" and job["worker_failure"] == {
        "stage": "word_clocks",
        "reason": "word_sequence",
    }


def test_rollback_word_clocks_vad_nonfinite_keeps_the_quarantine_error(monkeypatch, caplog):
    """Switch off: a (word_clocks, vad_nonfinite) terminal diagnosis books the ERROR quarantine again."""
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued(monkeypatch)
    assert _fail(queue, lease, worker_failure={"stage": "word_clocks", "reason": "vad_nonfinite"}) is True
    disposition, quar = _channel(caplog)
    assert not disposition and len(quar) == 1
    assert quar[0].levelno == logging.ERROR
    message = quar[0].getMessage()
    assert "reason=worker_failed" in message
    assert "stage=word_clocks" in message and "worker_reason=vad_nonfinite" in message
    job = store.probe("jobs", "a")
    assert job["state"] == "quarantined" and job["worker_failure"] == {
        "stage": "word_clocks",
        "reason": "vad_nonfinite",
    }


def test_rollback_word_clocks_vad_order_keeps_the_quarantine_error(monkeypatch, caplog):
    """Switch off: a (word_clocks, vad_order) terminal diagnosis books the ERROR quarantine again."""
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued(monkeypatch)
    assert _fail(queue, lease, worker_failure={"stage": "word_clocks", "reason": "vad_order"}) is True
    disposition, quar = _channel(caplog)
    assert not disposition and len(quar) == 1
    assert quar[0].levelno == logging.ERROR
    message = quar[0].getMessage()
    assert "reason=worker_failed" in message
    assert "stage=word_clocks" in message and "worker_reason=vad_order" in message
    job = store.probe("jobs", "a")
    assert job["state"] == "quarantined" and job["worker_failure"] == {"stage": "word_clocks", "reason": "vad_order"}


def test_rollback_word_clocks_vad_bounds_keeps_the_quarantine_error(monkeypatch, caplog):
    """Switch off: a (word_clocks, vad_bounds) terminal diagnosis books the ERROR quarantine again."""
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued(monkeypatch)
    assert _fail(queue, lease, worker_failure={"stage": "word_clocks", "reason": "vad_bounds"}) is True
    disposition, quar = _channel(caplog)
    assert not disposition and len(quar) == 1
    assert quar[0].levelno == logging.ERROR
    message = quar[0].getMessage()
    assert "reason=worker_failed" in message
    assert "stage=word_clocks" in message and "worker_reason=vad_bounds" in message
    job = store.probe("jobs", "a")
    assert job["state"] == "quarantined" and job["worker_failure"] == {"stage": "word_clocks", "reason": "vad_bounds"}


def test_rollback_assemble_words_word_shape_keeps_the_quarantine_error(monkeypatch, caplog):
    """Switch off: a (assemble_words, word_shape) terminal diagnosis books the ERROR quarantine again."""
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued(monkeypatch)
    assert _fail(queue, lease, worker_failure={"stage": "assemble_words", "reason": "word_shape"}) is True
    disposition, quar = _channel(caplog)
    assert not disposition and len(quar) == 1
    assert quar[0].levelno == logging.ERROR
    message = quar[0].getMessage()
    assert "reason=worker_failed" in message
    assert "stage=assemble_words" in message and "worker_reason=word_shape" in message
    job = store.probe("jobs", "a")
    assert job["state"] == "quarantined" and job["worker_failure"] == {
        "stage": "assemble_words",
        "reason": "word_shape",
    }


def test_rollback_assemble_words_word_clock_keeps_the_quarantine_error(monkeypatch, caplog):
    """Switch off: a (assemble_words, word_clock) terminal diagnosis books the ERROR quarantine again."""
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued(monkeypatch)
    assert _fail(queue, lease, worker_failure={"stage": "assemble_words", "reason": "word_clock"}) is True
    disposition, quar = _channel(caplog)
    assert not disposition and len(quar) == 1
    assert quar[0].levelno == logging.ERROR
    message = quar[0].getMessage()
    assert "reason=worker_failed" in message
    assert "stage=assemble_words" in message and "worker_reason=word_clock" in message
    job = store.probe("jobs", "a")
    assert job["state"] == "quarantined" and job["worker_failure"] == {
        "stage": "assemble_words",
        "reason": "word_clock",
    }


def test_rollback_assemble_words_word_sequence_keeps_the_quarantine_error(monkeypatch, caplog):
    """Switch off: a (assemble_words, word_sequence) terminal diagnosis books the ERROR quarantine again."""
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued(monkeypatch)
    assert _fail(queue, lease, worker_failure={"stage": "assemble_words", "reason": "word_sequence"}) is True
    disposition, quar = _channel(caplog)
    assert not disposition and len(quar) == 1
    assert quar[0].levelno == logging.ERROR
    message = quar[0].getMessage()
    assert "reason=worker_failed" in message
    assert "stage=assemble_words" in message and "worker_reason=word_sequence" in message
    job = store.probe("jobs", "a")
    assert job["state"] == "quarantined" and job["worker_failure"] == {
        "stage": "assemble_words",
        "reason": "word_sequence",
    }


def test_rollback_assemble_words_vad_nonfinite_keeps_the_quarantine_error(monkeypatch, caplog):
    """Switch off: a (assemble_words, vad_nonfinite) terminal diagnosis books the ERROR quarantine again."""
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued(monkeypatch)
    assert _fail(queue, lease, worker_failure={"stage": "assemble_words", "reason": "vad_nonfinite"}) is True
    disposition, quar = _channel(caplog)
    assert not disposition and len(quar) == 1
    assert quar[0].levelno == logging.ERROR
    message = quar[0].getMessage()
    assert "reason=worker_failed" in message
    assert "stage=assemble_words" in message and "worker_reason=vad_nonfinite" in message
    job = store.probe("jobs", "a")
    assert job["state"] == "quarantined" and job["worker_failure"] == {
        "stage": "assemble_words",
        "reason": "vad_nonfinite",
    }


def test_rollback_assemble_words_vad_order_keeps_the_quarantine_error(monkeypatch, caplog):
    """Switch off: a (assemble_words, vad_order) terminal diagnosis books the ERROR quarantine again."""
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued(monkeypatch)
    assert _fail(queue, lease, worker_failure={"stage": "assemble_words", "reason": "vad_order"}) is True
    disposition, quar = _channel(caplog)
    assert not disposition and len(quar) == 1
    assert quar[0].levelno == logging.ERROR
    message = quar[0].getMessage()
    assert "reason=worker_failed" in message
    assert "stage=assemble_words" in message and "worker_reason=vad_order" in message
    job = store.probe("jobs", "a")
    assert job["state"] == "quarantined" and job["worker_failure"] == {"stage": "assemble_words", "reason": "vad_order"}


def test_rollback_assemble_words_vad_bounds_keeps_the_quarantine_error(monkeypatch, caplog):
    """Switch off: a (assemble_words, vad_bounds) terminal diagnosis books the ERROR quarantine again."""
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued(monkeypatch)
    assert _fail(queue, lease, worker_failure={"stage": "assemble_words", "reason": "vad_bounds"}) is True
    disposition, quar = _channel(caplog)
    assert not disposition and len(quar) == 1
    assert quar[0].levelno == logging.ERROR
    message = quar[0].getMessage()
    assert "reason=worker_failed" in message
    assert "stage=assemble_words" in message and "worker_reason=vad_bounds" in message
    job = store.probe("jobs", "a")
    assert job["state"] == "quarantined" and job["worker_failure"] == {
        "stage": "assemble_words",
        "reason": "vad_bounds",
    }


def test_rollback_asr_recovery_word_shape_keeps_the_quarantine_error(monkeypatch, caplog):
    """Switch off: a (asr_recovery, word_shape) terminal diagnosis books the ERROR quarantine again."""
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued(monkeypatch)
    assert _fail(queue, lease, worker_failure={"stage": "asr_recovery", "reason": "word_shape"}) is True
    disposition, quar = _channel(caplog)
    assert not disposition and len(quar) == 1
    assert quar[0].levelno == logging.ERROR
    message = quar[0].getMessage()
    assert "reason=worker_failed" in message
    assert "stage=asr_recovery" in message and "worker_reason=word_shape" in message
    job = store.probe("jobs", "a")
    assert job["state"] == "quarantined" and job["worker_failure"] == {"stage": "asr_recovery", "reason": "word_shape"}


def test_rollback_asr_recovery_word_clock_keeps_the_quarantine_error(monkeypatch, caplog):
    """Switch off: a (asr_recovery, word_clock) terminal diagnosis books the ERROR quarantine again."""
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued(monkeypatch)
    assert _fail(queue, lease, worker_failure={"stage": "asr_recovery", "reason": "word_clock"}) is True
    disposition, quar = _channel(caplog)
    assert not disposition and len(quar) == 1
    assert quar[0].levelno == logging.ERROR
    message = quar[0].getMessage()
    assert "reason=worker_failed" in message
    assert "stage=asr_recovery" in message and "worker_reason=word_clock" in message
    job = store.probe("jobs", "a")
    assert job["state"] == "quarantined" and job["worker_failure"] == {"stage": "asr_recovery", "reason": "word_clock"}


def test_rollback_asr_recovery_word_sequence_keeps_the_quarantine_error(monkeypatch, caplog):
    """Switch off: a (asr_recovery, word_sequence) terminal diagnosis books the ERROR quarantine again."""
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued(monkeypatch)
    assert _fail(queue, lease, worker_failure={"stage": "asr_recovery", "reason": "word_sequence"}) is True
    disposition, quar = _channel(caplog)
    assert not disposition and len(quar) == 1
    assert quar[0].levelno == logging.ERROR
    message = quar[0].getMessage()
    assert "reason=worker_failed" in message
    assert "stage=asr_recovery" in message and "worker_reason=word_sequence" in message
    job = store.probe("jobs", "a")
    assert job["state"] == "quarantined" and job["worker_failure"] == {
        "stage": "asr_recovery",
        "reason": "word_sequence",
    }


def test_rollback_asr_recovery_vad_nonfinite_keeps_the_quarantine_error(monkeypatch, caplog):
    """Switch off: a (asr_recovery, vad_nonfinite) terminal diagnosis books the ERROR quarantine again."""
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued(monkeypatch)
    assert _fail(queue, lease, worker_failure={"stage": "asr_recovery", "reason": "vad_nonfinite"}) is True
    disposition, quar = _channel(caplog)
    assert not disposition and len(quar) == 1
    assert quar[0].levelno == logging.ERROR
    message = quar[0].getMessage()
    assert "reason=worker_failed" in message
    assert "stage=asr_recovery" in message and "worker_reason=vad_nonfinite" in message
    job = store.probe("jobs", "a")
    assert job["state"] == "quarantined" and job["worker_failure"] == {
        "stage": "asr_recovery",
        "reason": "vad_nonfinite",
    }


def test_rollback_asr_recovery_vad_order_keeps_the_quarantine_error(monkeypatch, caplog):
    """Switch off: a (asr_recovery, vad_order) terminal diagnosis books the ERROR quarantine again."""
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued(monkeypatch)
    assert _fail(queue, lease, worker_failure={"stage": "asr_recovery", "reason": "vad_order"}) is True
    disposition, quar = _channel(caplog)
    assert not disposition and len(quar) == 1
    assert quar[0].levelno == logging.ERROR
    message = quar[0].getMessage()
    assert "reason=worker_failed" in message
    assert "stage=asr_recovery" in message and "worker_reason=vad_order" in message
    job = store.probe("jobs", "a")
    assert job["state"] == "quarantined" and job["worker_failure"] == {"stage": "asr_recovery", "reason": "vad_order"}


def test_rollback_asr_recovery_vad_bounds_keeps_the_quarantine_error(monkeypatch, caplog):
    """Switch off: a (asr_recovery, vad_bounds) terminal diagnosis books the ERROR quarantine again."""
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued(monkeypatch)
    assert _fail(queue, lease, worker_failure={"stage": "asr_recovery", "reason": "vad_bounds"}) is True
    disposition, quar = _channel(caplog)
    assert not disposition and len(quar) == 1
    assert quar[0].levelno == logging.ERROR
    message = quar[0].getMessage()
    assert "reason=worker_failed" in message
    assert "stage=asr_recovery" in message and "worker_reason=vad_bounds" in message
    job = store.probe("jobs", "a")
    assert job["state"] == "quarantined" and job["worker_failure"] == {"stage": "asr_recovery", "reason": "vad_bounds"}


def test_rollback_trio_staged_audio_invalid_still_reports_the_disposition_handoff(monkeypatch, caplog):
    """Switch off: (staged_audio_invalid at fetch_decode) keeps its unconditional INFO handoff."""
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued(monkeypatch)
    assert _fail(queue, lease, worker_failure={"stage": "fetch_decode", "reason": "staged_audio_invalid"}) is True
    disposition, quar = _channel(caplog)
    assert not quar and len(disposition) == 1
    assert disposition[0].levelno == logging.INFO
    assert "worker_reason=staged_audio_invalid" in disposition[0].getMessage()


def test_rollback_trio_retained_audio_invalid_still_reports_the_disposition_handoff(monkeypatch, caplog):
    """Switch off: (retained_audio_invalid at fetch_decode) keeps its unconditional INFO handoff."""
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued(monkeypatch)
    assert _fail(queue, lease, worker_failure={"stage": "fetch_decode", "reason": "retained_audio_invalid"}) is True
    disposition, quar = _channel(caplog)
    assert not quar and len(disposition) == 1
    assert disposition[0].levelno == logging.INFO
    assert "worker_reason=retained_audio_invalid" in disposition[0].getMessage()


def test_rollback_trio_decoded_duration_mismatch_still_reports_the_disposition_handoff(monkeypatch, caplog):
    """Switch off: (decoded_duration_mismatch at fetch_decode) keeps its unconditional INFO handoff."""
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued(monkeypatch)
    assert _fail(queue, lease, worker_failure={"stage": "fetch_decode", "reason": "decoded_duration_mismatch"}) is True
    disposition, quar = _channel(caplog)
    assert not quar and len(disposition) == 1
    assert disposition[0].levelno == logging.INFO
    assert "worker_reason=decoded_duration_mismatch" in disposition[0].getMessage()


def test_rollback_exhausted_vad_bounds_evidence_names_the_quarantine_error(monkeypatch, caplog):
    """Switch off: a ladder exhausted bare names its preserved vad_bounds evidence on the ERROR line."""
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued(monkeypatch)
    store.rows["jobs", "a"]["worker_failure_evidence"] = {"stage": "vad_windows", "reason": "vad_bounds"}
    now = time.time()
    attempt = 0
    quarantined = False
    for _ in range(14):
        leases = queue.pull(now)
        if not leases:
            now += 30.0
            queue.recover(now)
            continue
        attempt += 1
        now += 10.0
        queue.fail("a", leases[0].token, now)
        if store.rows["jobs", "a"]["state"] == "quarantined":
            quarantined = True
            break
    assert quarantined
    disposition, quar = _channel(caplog)
    assert not disposition and len(quar) == 1
    assert "worker_reason=vad_bounds" in quar[0].getMessage()


def test_rollback_exhausted_word_clock_evidence_names_the_quarantine_error(monkeypatch, caplog):
    """Switch off: a ladder exhausted bare names its preserved word_clock evidence on the ERROR line."""
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued(monkeypatch)
    store.rows["jobs", "a"]["worker_failure_evidence"] = {"stage": "vad_windows", "reason": "word_clock"}
    now = time.time()
    attempt = 0
    quarantined = False
    for _ in range(14):
        leases = queue.pull(now)
        if not leases:
            now += 30.0
            queue.recover(now)
            continue
        attempt += 1
        now += 10.0
        queue.fail("a", leases[0].token, now)
        if store.rows["jobs", "a"]["state"] == "quarantined":
            quarantined = True
            break
    assert quarantined
    disposition, quar = _channel(caplog)
    assert not disposition and len(quar) == 1
    assert "worker_reason=word_clock" in quar[0].getMessage()


def test_rollback_exhausted_word_shape_evidence_names_the_quarantine_error(monkeypatch, caplog):
    """Switch off: a ladder exhausted bare names its preserved word_shape evidence on the ERROR line."""
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued(monkeypatch)
    store.rows["jobs", "a"]["worker_failure_evidence"] = {"stage": "vad_windows", "reason": "word_shape"}
    now = time.time()
    attempt = 0
    quarantined = False
    for _ in range(14):
        leases = queue.pull(now)
        if not leases:
            now += 30.0
            queue.recover(now)
            continue
        attempt += 1
        now += 10.0
        queue.fail("a", leases[0].token, now)
        if store.rows["jobs", "a"]["state"] == "quarantined":
            quarantined = True
            break
    assert quarantined
    disposition, quar = _channel(caplog)
    assert not disposition and len(quar) == 1
    assert "worker_reason=word_shape" in quar[0].getMessage()


def test_switch_parse_true_is_True(monkeypatch):
    """The switch parses 'true' as True (strip + lower, equality with 'true')."""
    monkeypatch.setenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", 'true')
    assert worker_validation_disposition_enabled() is True


def test_switch_parse_true_is_True(monkeypatch):
    """The switch parses 'TRUE' as True (strip + lower, equality with 'true')."""
    monkeypatch.setenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", 'TRUE')
    assert worker_validation_disposition_enabled() is True


def test_switch_parse_true_is_True(monkeypatch):
    """The switch parses ' true ' as True (strip + lower, equality with 'true')."""
    monkeypatch.setenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", ' true ')
    assert worker_validation_disposition_enabled() is True


def test_switch_parse_false_is_False(monkeypatch):
    """The switch parses 'false' as False (strip + lower, equality with 'true')."""
    monkeypatch.setenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", 'false')
    assert worker_validation_disposition_enabled() is False


def test_switch_parse_empty_is_False(monkeypatch):
    """The switch parses '' as False (strip + lower, equality with 'true')."""
    monkeypatch.setenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", '')
    assert worker_validation_disposition_enabled() is False


def test_switch_parse_yes_is_False(monkeypatch):
    """The switch parses 'yes' as False (strip + lower, equality with 'true')."""
    monkeypatch.setenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", 'yes')
    assert worker_validation_disposition_enabled() is False


def test_switch_parse_1_is_False(monkeypatch):
    """The switch parses '1' as False (strip + lower, equality with 'true')."""
    monkeypatch.setenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", '1')
    assert worker_validation_disposition_enabled() is False


def test_switch_parse_on_is_False(monkeypatch):
    """The switch parses 'on' as False (strip + lower, equality with 'true')."""
    monkeypatch.setenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", 'on')
    assert worker_validation_disposition_enabled() is False


def test_switch_unset_defaults_on(monkeypatch):
    """The switch ships on: an unset environment restores the disposition."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    assert worker_validation_disposition_enabled() is True


def test_safety_switch_off_does_not_demote_the_flagged_verdicts(monkeypatch, caplog):
    """Safety-off plus switch-on: the flagged verdicts still demote (the safety switch never decides this)."""
    monkeypatch.setenv("BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED", "false")
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued(monkeypatch, position="true")
    assert _fail(queue, lease, worker_failure={"stage": "vad_windows", "reason": "vad_bounds"}) is True
    disposition, quar = _channel(caplog)
    assert not quar and len(disposition) == 1


def test_safety_switch_off_does_not_demote_the_trio(monkeypatch, caplog):
    """Safety-off: the trio keeps its unconditional handoff."""
    monkeypatch.setenv("BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED", "false")
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued(monkeypatch, position="true")
    assert _fail(queue, lease, worker_failure={"stage": "fetch_decode", "reason": "retained_audio_invalid"}) is True
    disposition, quar = _channel(caplog)
    assert not quar and len(disposition) == 1


def test_empty_ladder_switch_never_demotes_the_family(monkeypatch, caplog):
    """The empty-ladder flags never rechannel a vad/word verdict."""
    monkeypatch.setenv("BATCH_PIPELINE_EMPTY_ASR_RECOVERY_ENABLED", "false")
    monkeypatch.setenv("BATCH_PIPELINE_EMPTY_ASR_DISPOSITION_ENABLED", "false")
    monkeypatch.setenv("BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED", "false")
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued(monkeypatch, position="true")
    assert _fail(queue, lease, worker_failure={"stage": "vad_windows", "reason": "vad_order"}) is True
    disposition, quar = _channel(caplog)
    assert not quar and len(disposition) == 1


def test_admitted_source_refusal_keeps_error_under_every_switch(monkeypatch, caplog):
    """outside_admitted_source keeps the fault line under both switch positions."""
    for position in ("true", "false"):
        caplog.clear()
        caplog.set_level(logging.INFO)
        store, queue, lease = _queued(monkeypatch, position=position)
        assert (
            _fail(queue, lease, worker_failure={"stage": "fetch_decode", "reason": "outside_admitted_source"}) is True
        )
        disposition, quar = _channel(caplog)
        assert not disposition and len(quar) == 1
