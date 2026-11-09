# Failure-Class: FC-terminal-validation-disposition-misbooked-as-worker-fault
"""The demoted hold's line shape, field-by-field, across the family grid.

For every family (stage, reason) cell the terminal line carries the full
historic field set — ``event``, ``outcome``, ``attempt``, ``recovery``,
``stage``, ``worker_reason`` — at INFO, and the worker handoff carries the
full diagnostic set the fault line carried. Message-prefix parity pins the
exact shape drift cannot silently break.
"""

import logging
import time

from tests.unit.test_batch_pipeline_scheduler import MemoryStore, item as sched_item
from utils.batch_pipeline.contracts import Priority
from utils.batch_pipeline.scheduler import Scheduler

STAGES = ('fetch_decode', 'vad_windows', 'word_clocks', 'assemble_words', 'asr_recovery')
TRIO = ('staged_audio_invalid', 'retained_audio_invalid', 'decoded_duration_mismatch')
FLAGGED = ('word_shape', 'word_clock', 'word_sequence', 'vad_nonfinite', 'vad_order', 'vad_bounds')
FAMILY = TRIO + FLAGGED


def _queued():
    store = MemoryStore()
    queue = Scheduler(store)
    work = sched_item("a", owner="field-grid-owner", duration=30, priority=Priority.FRESH)
    assert queue.enqueue(work, time.time())
    lease = queue.pull(time.time())[0]
    return store, queue, lease


def _fail(queue, lease, **kwargs):
    return queue.fail(lease.item.segment_id, lease.token, time.time() + 100.0, **kwargs)


def _hold(caplog):
    lines = [
        r.getMessage()
        for r in caplog.records
        if "event=batch_validation_disposition outcome=held_for_disposition" in r.getMessage()
    ]
    assert len(lines) == 1
    return lines[0]


def test_hold_shape_fetch_decode_staged_audio_invalid_carries_the_full_field_set(monkeypatch, caplog):
    """The (fetch_decode, staged_audio_invalid) hold line carries every field the fault line carried."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure={"stage": "fetch_decode", "reason": "staged_audio_invalid"}) is True
    message = _hold(caplog)
    assert message.startswith(
        "event=batch_validation_disposition outcome=held_for_disposition attempt=1 recovery=held "
    )
    assert "stage=fetch_decode worker_reason=staged_audio_invalid" in message


def test_hold_shape_fetch_decode_retained_audio_invalid_carries_the_full_field_set(monkeypatch, caplog):
    """The (fetch_decode, retained_audio_invalid) hold line carries every field the fault line carried."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure={"stage": "fetch_decode", "reason": "retained_audio_invalid"}) is True
    message = _hold(caplog)
    assert message.startswith(
        "event=batch_validation_disposition outcome=held_for_disposition attempt=1 recovery=held "
    )
    assert "stage=fetch_decode worker_reason=retained_audio_invalid" in message


def test_hold_shape_fetch_decode_decoded_duration_mismatch_carries_the_full_field_set(monkeypatch, caplog):
    """The (fetch_decode, decoded_duration_mismatch) hold line carries every field the fault line carried."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure={"stage": "fetch_decode", "reason": "decoded_duration_mismatch"}) is True
    message = _hold(caplog)
    assert message.startswith(
        "event=batch_validation_disposition outcome=held_for_disposition attempt=1 recovery=held "
    )
    assert "stage=fetch_decode worker_reason=decoded_duration_mismatch" in message


def test_hold_shape_fetch_decode_word_shape_carries_the_full_field_set(monkeypatch, caplog):
    """The (fetch_decode, word_shape) hold line carries every field the fault line carried."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure={"stage": "fetch_decode", "reason": "word_shape"}) is True
    message = _hold(caplog)
    assert message.startswith(
        "event=batch_validation_disposition outcome=held_for_disposition attempt=1 recovery=held "
    )
    assert "stage=fetch_decode worker_reason=word_shape" in message


def test_hold_shape_fetch_decode_word_clock_carries_the_full_field_set(monkeypatch, caplog):
    """The (fetch_decode, word_clock) hold line carries every field the fault line carried."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure={"stage": "fetch_decode", "reason": "word_clock"}) is True
    message = _hold(caplog)
    assert message.startswith(
        "event=batch_validation_disposition outcome=held_for_disposition attempt=1 recovery=held "
    )
    assert "stage=fetch_decode worker_reason=word_clock" in message


def test_hold_shape_fetch_decode_word_sequence_carries_the_full_field_set(monkeypatch, caplog):
    """The (fetch_decode, word_sequence) hold line carries every field the fault line carried."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure={"stage": "fetch_decode", "reason": "word_sequence"}) is True
    message = _hold(caplog)
    assert message.startswith(
        "event=batch_validation_disposition outcome=held_for_disposition attempt=1 recovery=held "
    )
    assert "stage=fetch_decode worker_reason=word_sequence" in message


def test_hold_shape_fetch_decode_vad_nonfinite_carries_the_full_field_set(monkeypatch, caplog):
    """The (fetch_decode, vad_nonfinite) hold line carries every field the fault line carried."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure={"stage": "fetch_decode", "reason": "vad_nonfinite"}) is True
    message = _hold(caplog)
    assert message.startswith(
        "event=batch_validation_disposition outcome=held_for_disposition attempt=1 recovery=held "
    )
    assert "stage=fetch_decode worker_reason=vad_nonfinite" in message


def test_hold_shape_fetch_decode_vad_order_carries_the_full_field_set(monkeypatch, caplog):
    """The (fetch_decode, vad_order) hold line carries every field the fault line carried."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure={"stage": "fetch_decode", "reason": "vad_order"}) is True
    message = _hold(caplog)
    assert message.startswith(
        "event=batch_validation_disposition outcome=held_for_disposition attempt=1 recovery=held "
    )
    assert "stage=fetch_decode worker_reason=vad_order" in message


def test_hold_shape_fetch_decode_vad_bounds_carries_the_full_field_set(monkeypatch, caplog):
    """The (fetch_decode, vad_bounds) hold line carries every field the fault line carried."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure={"stage": "fetch_decode", "reason": "vad_bounds"}) is True
    message = _hold(caplog)
    assert message.startswith(
        "event=batch_validation_disposition outcome=held_for_disposition attempt=1 recovery=held "
    )
    assert "stage=fetch_decode worker_reason=vad_bounds" in message


def test_quarantine_shape_vad_windows_staged_audio_invalid_carries_the_full_field_set(monkeypatch, caplog):
    """The (vad_windows, staged_audio_invalid) kept fault keeps the full ERROR field set."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure={"stage": "vad_windows", "reason": "staged_audio_invalid"}) is True
    quar = [r for r in caplog.records if "event=batch_quarantined" in r.getMessage()]
    assert len(quar) == 1 and quar[0].levelno == logging.ERROR
    message = quar[0].getMessage()
    assert message.startswith("event=batch_quarantined reason=worker_failed attempt=1 recovery=held ")
    assert "stage=vad_windows worker_reason=staged_audio_invalid" in message


def test_quarantine_shape_vad_windows_retained_audio_invalid_carries_the_full_field_set(monkeypatch, caplog):
    """The (vad_windows, retained_audio_invalid) kept fault keeps the full ERROR field set."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure={"stage": "vad_windows", "reason": "retained_audio_invalid"}) is True
    quar = [r for r in caplog.records if "event=batch_quarantined" in r.getMessage()]
    assert len(quar) == 1 and quar[0].levelno == logging.ERROR
    message = quar[0].getMessage()
    assert message.startswith("event=batch_quarantined reason=worker_failed attempt=1 recovery=held ")
    assert "stage=vad_windows worker_reason=retained_audio_invalid" in message


def test_quarantine_shape_vad_windows_decoded_duration_mismatch_carries_the_full_field_set(monkeypatch, caplog):
    """The (vad_windows, decoded_duration_mismatch) kept fault keeps the full ERROR field set."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure={"stage": "vad_windows", "reason": "decoded_duration_mismatch"}) is True
    quar = [r for r in caplog.records if "event=batch_quarantined" in r.getMessage()]
    assert len(quar) == 1 and quar[0].levelno == logging.ERROR
    message = quar[0].getMessage()
    assert message.startswith("event=batch_quarantined reason=worker_failed attempt=1 recovery=held ")
    assert "stage=vad_windows worker_reason=decoded_duration_mismatch" in message


def test_hold_shape_vad_windows_word_shape_carries_the_full_field_set(monkeypatch, caplog):
    """The (vad_windows, word_shape) hold line carries every field the fault line carried."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure={"stage": "vad_windows", "reason": "word_shape"}) is True
    message = _hold(caplog)
    assert message.startswith(
        "event=batch_validation_disposition outcome=held_for_disposition attempt=1 recovery=held "
    )
    assert "stage=vad_windows worker_reason=word_shape" in message


def test_hold_shape_vad_windows_word_clock_carries_the_full_field_set(monkeypatch, caplog):
    """The (vad_windows, word_clock) hold line carries every field the fault line carried."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure={"stage": "vad_windows", "reason": "word_clock"}) is True
    message = _hold(caplog)
    assert message.startswith(
        "event=batch_validation_disposition outcome=held_for_disposition attempt=1 recovery=held "
    )
    assert "stage=vad_windows worker_reason=word_clock" in message


def test_hold_shape_vad_windows_word_sequence_carries_the_full_field_set(monkeypatch, caplog):
    """The (vad_windows, word_sequence) hold line carries every field the fault line carried."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure={"stage": "vad_windows", "reason": "word_sequence"}) is True
    message = _hold(caplog)
    assert message.startswith(
        "event=batch_validation_disposition outcome=held_for_disposition attempt=1 recovery=held "
    )
    assert "stage=vad_windows worker_reason=word_sequence" in message


def test_hold_shape_vad_windows_vad_nonfinite_carries_the_full_field_set(monkeypatch, caplog):
    """The (vad_windows, vad_nonfinite) hold line carries every field the fault line carried."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure={"stage": "vad_windows", "reason": "vad_nonfinite"}) is True
    message = _hold(caplog)
    assert message.startswith(
        "event=batch_validation_disposition outcome=held_for_disposition attempt=1 recovery=held "
    )
    assert "stage=vad_windows worker_reason=vad_nonfinite" in message


def test_hold_shape_vad_windows_vad_order_carries_the_full_field_set(monkeypatch, caplog):
    """The (vad_windows, vad_order) hold line carries every field the fault line carried."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure={"stage": "vad_windows", "reason": "vad_order"}) is True
    message = _hold(caplog)
    assert message.startswith(
        "event=batch_validation_disposition outcome=held_for_disposition attempt=1 recovery=held "
    )
    assert "stage=vad_windows worker_reason=vad_order" in message


def test_hold_shape_vad_windows_vad_bounds_carries_the_full_field_set(monkeypatch, caplog):
    """The (vad_windows, vad_bounds) hold line carries every field the fault line carried."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure={"stage": "vad_windows", "reason": "vad_bounds"}) is True
    message = _hold(caplog)
    assert message.startswith(
        "event=batch_validation_disposition outcome=held_for_disposition attempt=1 recovery=held "
    )
    assert "stage=vad_windows worker_reason=vad_bounds" in message


def test_quarantine_shape_word_clocks_staged_audio_invalid_carries_the_full_field_set(monkeypatch, caplog):
    """The (word_clocks, staged_audio_invalid) kept fault keeps the full ERROR field set."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure={"stage": "word_clocks", "reason": "staged_audio_invalid"}) is True
    quar = [r for r in caplog.records if "event=batch_quarantined" in r.getMessage()]
    assert len(quar) == 1 and quar[0].levelno == logging.ERROR
    message = quar[0].getMessage()
    assert message.startswith("event=batch_quarantined reason=worker_failed attempt=1 recovery=held ")
    assert "stage=word_clocks worker_reason=staged_audio_invalid" in message


def test_quarantine_shape_word_clocks_retained_audio_invalid_carries_the_full_field_set(monkeypatch, caplog):
    """The (word_clocks, retained_audio_invalid) kept fault keeps the full ERROR field set."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure={"stage": "word_clocks", "reason": "retained_audio_invalid"}) is True
    quar = [r for r in caplog.records if "event=batch_quarantined" in r.getMessage()]
    assert len(quar) == 1 and quar[0].levelno == logging.ERROR
    message = quar[0].getMessage()
    assert message.startswith("event=batch_quarantined reason=worker_failed attempt=1 recovery=held ")
    assert "stage=word_clocks worker_reason=retained_audio_invalid" in message


def test_quarantine_shape_word_clocks_decoded_duration_mismatch_carries_the_full_field_set(monkeypatch, caplog):
    """The (word_clocks, decoded_duration_mismatch) kept fault keeps the full ERROR field set."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure={"stage": "word_clocks", "reason": "decoded_duration_mismatch"}) is True
    quar = [r for r in caplog.records if "event=batch_quarantined" in r.getMessage()]
    assert len(quar) == 1 and quar[0].levelno == logging.ERROR
    message = quar[0].getMessage()
    assert message.startswith("event=batch_quarantined reason=worker_failed attempt=1 recovery=held ")
    assert "stage=word_clocks worker_reason=decoded_duration_mismatch" in message


def test_hold_shape_word_clocks_word_shape_carries_the_full_field_set(monkeypatch, caplog):
    """The (word_clocks, word_shape) hold line carries every field the fault line carried."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure={"stage": "word_clocks", "reason": "word_shape"}) is True
    message = _hold(caplog)
    assert message.startswith(
        "event=batch_validation_disposition outcome=held_for_disposition attempt=1 recovery=held "
    )
    assert "stage=word_clocks worker_reason=word_shape" in message


def test_hold_shape_word_clocks_word_clock_carries_the_full_field_set(monkeypatch, caplog):
    """The (word_clocks, word_clock) hold line carries every field the fault line carried."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure={"stage": "word_clocks", "reason": "word_clock"}) is True
    message = _hold(caplog)
    assert message.startswith(
        "event=batch_validation_disposition outcome=held_for_disposition attempt=1 recovery=held "
    )
    assert "stage=word_clocks worker_reason=word_clock" in message


def test_hold_shape_word_clocks_word_sequence_carries_the_full_field_set(monkeypatch, caplog):
    """The (word_clocks, word_sequence) hold line carries every field the fault line carried."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure={"stage": "word_clocks", "reason": "word_sequence"}) is True
    message = _hold(caplog)
    assert message.startswith(
        "event=batch_validation_disposition outcome=held_for_disposition attempt=1 recovery=held "
    )
    assert "stage=word_clocks worker_reason=word_sequence" in message


def test_hold_shape_word_clocks_vad_nonfinite_carries_the_full_field_set(monkeypatch, caplog):
    """The (word_clocks, vad_nonfinite) hold line carries every field the fault line carried."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure={"stage": "word_clocks", "reason": "vad_nonfinite"}) is True
    message = _hold(caplog)
    assert message.startswith(
        "event=batch_validation_disposition outcome=held_for_disposition attempt=1 recovery=held "
    )
    assert "stage=word_clocks worker_reason=vad_nonfinite" in message


def test_hold_shape_word_clocks_vad_order_carries_the_full_field_set(monkeypatch, caplog):
    """The (word_clocks, vad_order) hold line carries every field the fault line carried."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure={"stage": "word_clocks", "reason": "vad_order"}) is True
    message = _hold(caplog)
    assert message.startswith(
        "event=batch_validation_disposition outcome=held_for_disposition attempt=1 recovery=held "
    )
    assert "stage=word_clocks worker_reason=vad_order" in message


def test_hold_shape_word_clocks_vad_bounds_carries_the_full_field_set(monkeypatch, caplog):
    """The (word_clocks, vad_bounds) hold line carries every field the fault line carried."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure={"stage": "word_clocks", "reason": "vad_bounds"}) is True
    message = _hold(caplog)
    assert message.startswith(
        "event=batch_validation_disposition outcome=held_for_disposition attempt=1 recovery=held "
    )
    assert "stage=word_clocks worker_reason=vad_bounds" in message


def test_quarantine_shape_assemble_words_staged_audio_invalid_carries_the_full_field_set(monkeypatch, caplog):
    """The (assemble_words, staged_audio_invalid) kept fault keeps the full ERROR field set."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure={"stage": "assemble_words", "reason": "staged_audio_invalid"}) is True
    quar = [r for r in caplog.records if "event=batch_quarantined" in r.getMessage()]
    assert len(quar) == 1 and quar[0].levelno == logging.ERROR
    message = quar[0].getMessage()
    assert message.startswith("event=batch_quarantined reason=worker_failed attempt=1 recovery=held ")
    assert "stage=assemble_words worker_reason=staged_audio_invalid" in message


def test_quarantine_shape_assemble_words_retained_audio_invalid_carries_the_full_field_set(monkeypatch, caplog):
    """The (assemble_words, retained_audio_invalid) kept fault keeps the full ERROR field set."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure={"stage": "assemble_words", "reason": "retained_audio_invalid"}) is True
    quar = [r for r in caplog.records if "event=batch_quarantined" in r.getMessage()]
    assert len(quar) == 1 and quar[0].levelno == logging.ERROR
    message = quar[0].getMessage()
    assert message.startswith("event=batch_quarantined reason=worker_failed attempt=1 recovery=held ")
    assert "stage=assemble_words worker_reason=retained_audio_invalid" in message


def test_quarantine_shape_assemble_words_decoded_duration_mismatch_carries_the_full_field_set(monkeypatch, caplog):
    """The (assemble_words, decoded_duration_mismatch) kept fault keeps the full ERROR field set."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued()
    assert (
        _fail(queue, lease, worker_failure={"stage": "assemble_words", "reason": "decoded_duration_mismatch"}) is True
    )
    quar = [r for r in caplog.records if "event=batch_quarantined" in r.getMessage()]
    assert len(quar) == 1 and quar[0].levelno == logging.ERROR
    message = quar[0].getMessage()
    assert message.startswith("event=batch_quarantined reason=worker_failed attempt=1 recovery=held ")
    assert "stage=assemble_words worker_reason=decoded_duration_mismatch" in message


def test_hold_shape_assemble_words_word_shape_carries_the_full_field_set(monkeypatch, caplog):
    """The (assemble_words, word_shape) hold line carries every field the fault line carried."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure={"stage": "assemble_words", "reason": "word_shape"}) is True
    message = _hold(caplog)
    assert message.startswith(
        "event=batch_validation_disposition outcome=held_for_disposition attempt=1 recovery=held "
    )
    assert "stage=assemble_words worker_reason=word_shape" in message


def test_hold_shape_assemble_words_word_clock_carries_the_full_field_set(monkeypatch, caplog):
    """The (assemble_words, word_clock) hold line carries every field the fault line carried."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure={"stage": "assemble_words", "reason": "word_clock"}) is True
    message = _hold(caplog)
    assert message.startswith(
        "event=batch_validation_disposition outcome=held_for_disposition attempt=1 recovery=held "
    )
    assert "stage=assemble_words worker_reason=word_clock" in message


def test_hold_shape_assemble_words_word_sequence_carries_the_full_field_set(monkeypatch, caplog):
    """The (assemble_words, word_sequence) hold line carries every field the fault line carried."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure={"stage": "assemble_words", "reason": "word_sequence"}) is True
    message = _hold(caplog)
    assert message.startswith(
        "event=batch_validation_disposition outcome=held_for_disposition attempt=1 recovery=held "
    )
    assert "stage=assemble_words worker_reason=word_sequence" in message


def test_hold_shape_assemble_words_vad_nonfinite_carries_the_full_field_set(monkeypatch, caplog):
    """The (assemble_words, vad_nonfinite) hold line carries every field the fault line carried."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure={"stage": "assemble_words", "reason": "vad_nonfinite"}) is True
    message = _hold(caplog)
    assert message.startswith(
        "event=batch_validation_disposition outcome=held_for_disposition attempt=1 recovery=held "
    )
    assert "stage=assemble_words worker_reason=vad_nonfinite" in message


def test_hold_shape_assemble_words_vad_order_carries_the_full_field_set(monkeypatch, caplog):
    """The (assemble_words, vad_order) hold line carries every field the fault line carried."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure={"stage": "assemble_words", "reason": "vad_order"}) is True
    message = _hold(caplog)
    assert message.startswith(
        "event=batch_validation_disposition outcome=held_for_disposition attempt=1 recovery=held "
    )
    assert "stage=assemble_words worker_reason=vad_order" in message


def test_hold_shape_assemble_words_vad_bounds_carries_the_full_field_set(monkeypatch, caplog):
    """The (assemble_words, vad_bounds) hold line carries every field the fault line carried."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure={"stage": "assemble_words", "reason": "vad_bounds"}) is True
    message = _hold(caplog)
    assert message.startswith(
        "event=batch_validation_disposition outcome=held_for_disposition attempt=1 recovery=held "
    )
    assert "stage=assemble_words worker_reason=vad_bounds" in message


def test_quarantine_shape_asr_recovery_staged_audio_invalid_carries_the_full_field_set(monkeypatch, caplog):
    """The (asr_recovery, staged_audio_invalid) kept fault keeps the full ERROR field set."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure={"stage": "asr_recovery", "reason": "staged_audio_invalid"}) is True
    quar = [r for r in caplog.records if "event=batch_quarantined" in r.getMessage()]
    assert len(quar) == 1 and quar[0].levelno == logging.ERROR
    message = quar[0].getMessage()
    assert message.startswith("event=batch_quarantined reason=worker_failed attempt=1 recovery=held ")
    assert "stage=asr_recovery worker_reason=staged_audio_invalid" in message


def test_quarantine_shape_asr_recovery_retained_audio_invalid_carries_the_full_field_set(monkeypatch, caplog):
    """The (asr_recovery, retained_audio_invalid) kept fault keeps the full ERROR field set."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure={"stage": "asr_recovery", "reason": "retained_audio_invalid"}) is True
    quar = [r for r in caplog.records if "event=batch_quarantined" in r.getMessage()]
    assert len(quar) == 1 and quar[0].levelno == logging.ERROR
    message = quar[0].getMessage()
    assert message.startswith("event=batch_quarantined reason=worker_failed attempt=1 recovery=held ")
    assert "stage=asr_recovery worker_reason=retained_audio_invalid" in message


def test_quarantine_shape_asr_recovery_decoded_duration_mismatch_carries_the_full_field_set(monkeypatch, caplog):
    """The (asr_recovery, decoded_duration_mismatch) kept fault keeps the full ERROR field set."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure={"stage": "asr_recovery", "reason": "decoded_duration_mismatch"}) is True
    quar = [r for r in caplog.records if "event=batch_quarantined" in r.getMessage()]
    assert len(quar) == 1 and quar[0].levelno == logging.ERROR
    message = quar[0].getMessage()
    assert message.startswith("event=batch_quarantined reason=worker_failed attempt=1 recovery=held ")
    assert "stage=asr_recovery worker_reason=decoded_duration_mismatch" in message


def test_hold_shape_asr_recovery_word_shape_carries_the_full_field_set(monkeypatch, caplog):
    """The (asr_recovery, word_shape) hold line carries every field the fault line carried."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure={"stage": "asr_recovery", "reason": "word_shape"}) is True
    message = _hold(caplog)
    assert message.startswith(
        "event=batch_validation_disposition outcome=held_for_disposition attempt=1 recovery=held "
    )
    assert "stage=asr_recovery worker_reason=word_shape" in message


def test_hold_shape_asr_recovery_word_clock_carries_the_full_field_set(monkeypatch, caplog):
    """The (asr_recovery, word_clock) hold line carries every field the fault line carried."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure={"stage": "asr_recovery", "reason": "word_clock"}) is True
    message = _hold(caplog)
    assert message.startswith(
        "event=batch_validation_disposition outcome=held_for_disposition attempt=1 recovery=held "
    )
    assert "stage=asr_recovery worker_reason=word_clock" in message


def test_hold_shape_asr_recovery_word_sequence_carries_the_full_field_set(monkeypatch, caplog):
    """The (asr_recovery, word_sequence) hold line carries every field the fault line carried."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure={"stage": "asr_recovery", "reason": "word_sequence"}) is True
    message = _hold(caplog)
    assert message.startswith(
        "event=batch_validation_disposition outcome=held_for_disposition attempt=1 recovery=held "
    )
    assert "stage=asr_recovery worker_reason=word_sequence" in message


def test_hold_shape_asr_recovery_vad_nonfinite_carries_the_full_field_set(monkeypatch, caplog):
    """The (asr_recovery, vad_nonfinite) hold line carries every field the fault line carried."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure={"stage": "asr_recovery", "reason": "vad_nonfinite"}) is True
    message = _hold(caplog)
    assert message.startswith(
        "event=batch_validation_disposition outcome=held_for_disposition attempt=1 recovery=held "
    )
    assert "stage=asr_recovery worker_reason=vad_nonfinite" in message


def test_hold_shape_asr_recovery_vad_order_carries_the_full_field_set(monkeypatch, caplog):
    """The (asr_recovery, vad_order) hold line carries every field the fault line carried."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure={"stage": "asr_recovery", "reason": "vad_order"}) is True
    message = _hold(caplog)
    assert message.startswith(
        "event=batch_validation_disposition outcome=held_for_disposition attempt=1 recovery=held "
    )
    assert "stage=asr_recovery worker_reason=vad_order" in message


def test_hold_shape_asr_recovery_vad_bounds_carries_the_full_field_set(monkeypatch, caplog):
    """The (asr_recovery, vad_bounds) hold line carries every field the fault line carried."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure={"stage": "asr_recovery", "reason": "vad_bounds"}) is True
    message = _hold(caplog)
    assert message.startswith(
        "event=batch_validation_disposition outcome=held_for_disposition attempt=1 recovery=held "
    )
    assert "stage=asr_recovery worker_reason=vad_bounds" in message
