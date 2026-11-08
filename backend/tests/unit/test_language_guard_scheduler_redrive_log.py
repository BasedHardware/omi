"""The scheduler holds a guarded unit for redrive without booking a quarantine fault.

A terminal worker_failure whose reason is unsupported_language quarantines exactly as before (same state, same evidence, same warning) but reports event=batch_language_guard outcome=held_for_redrive at INFO instead of the ERROR batch_quarantined line. Every other closed reason keeps the ERROR line. Evidence-only diagnoses still defer through the ladder with no terminal line at all. Metrics, correctness meters, and lease accounting are pinned unchanged next to the new classification.

Failure-Class: FC-language-guard-redrive-misclassified-as-worker-fault
"""

import logging
from unittest.mock import Mock

import pytest

import utils.batch_pipeline.scheduler as scheduler_module
from tests.unit.test_batch_pipeline_scheduler import MemoryStore, item as sched_item
from utils.batch_pipeline.contracts import Priority
from utils.batch_pipeline.scheduler import Scheduler

STAGES = ['fetch_decode', 'vad_windows', 'word_clocks', 'assemble_words', 'asr_recovery']
REASONS = [
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
]
GUARD = 'unsupported_language'


def _queued(key='a', owner='guard-owner', duration=30, metrics=None):
    store = MemoryStore()
    queue = Scheduler(store, metrics=metrics)
    work = sched_item(key, owner=owner, duration=duration, priority=Priority.FRESH)
    assert queue.enqueue(work, 100.0)
    lease = queue.pull(1000.0)[0]
    return store, queue, lease


def _fail(queue, lease, **kwargs):
    return queue.fail(lease.item.segment_id, lease.token, 1100.0, **kwargs)


def _split(caplog):
    guard = [r for r in caplog.records if 'event=batch_language_guard' in r.getMessage()]
    quar = [r for r in caplog.records if 'event=batch_quarantined' in r.getMessage()]
    warn = [r for r in caplog.records if 'awaiting_fenced_recovery' in r.getMessage()]
    return guard, quar, warn


def _capture_correctness(monkeypatch):
    calls = []
    monkeypatch.setattr(
        scheduler_module, 'record_correctness', lambda name, seconds=None: calls.append((name, seconds))
    )
    return calls


def test_guard_terminal_fetch_decode_demotes_to_held_for_redrive(caplog):
    """A guard terminal at fetch_decode holds for the fenced redrive without the quarantine ERROR."""
    caplog.set_level(logging.INFO)
    shape = {"stage": "fetch_decode", "reason": GUARD}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure=shape) is True
    guard, quar, warn = _split(caplog)
    assert len(guard) == 1 and not quar
    assert guard[0].levelno == logging.INFO
    assert 'outcome=held_for_redrive' in guard[0].getMessage()
    assert 'attempt=1' in guard[0].getMessage() and 'recovery=held' in guard[0].getMessage()
    assert (
        'stage=fetch_decode' in guard[0].getMessage() and 'worker_reason=unsupported_language' in guard[0].getMessage()
    )
    assert len(warn) == 1
    job = store.probe('jobs', 'a')
    assert job['state'] == 'quarantined'
    assert job['worker_failure'] == shape


def test_guard_terminal_vad_windows_demotes_to_held_for_redrive(caplog):
    """A guard terminal at vad_windows holds for the fenced redrive without the quarantine ERROR."""
    caplog.set_level(logging.INFO)
    shape = {"stage": "vad_windows", "reason": GUARD}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure=shape) is True
    guard, quar, warn = _split(caplog)
    assert len(guard) == 1 and not quar
    assert guard[0].levelno == logging.INFO
    assert 'outcome=held_for_redrive' in guard[0].getMessage()
    assert 'attempt=1' in guard[0].getMessage() and 'recovery=held' in guard[0].getMessage()
    assert (
        'stage=vad_windows' in guard[0].getMessage() and 'worker_reason=unsupported_language' in guard[0].getMessage()
    )
    assert len(warn) == 1
    job = store.probe('jobs', 'a')
    assert job['state'] == 'quarantined'
    assert job['worker_failure'] == shape


def test_guard_terminal_word_clocks_demotes_to_held_for_redrive(caplog):
    """A guard terminal at word_clocks holds for the fenced redrive without the quarantine ERROR."""
    caplog.set_level(logging.INFO)
    shape = {"stage": "word_clocks", "reason": GUARD}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure=shape) is True
    guard, quar, warn = _split(caplog)
    assert len(guard) == 1 and not quar
    assert guard[0].levelno == logging.INFO
    assert 'outcome=held_for_redrive' in guard[0].getMessage()
    assert 'attempt=1' in guard[0].getMessage() and 'recovery=held' in guard[0].getMessage()
    assert (
        'stage=word_clocks' in guard[0].getMessage() and 'worker_reason=unsupported_language' in guard[0].getMessage()
    )
    assert len(warn) == 1
    job = store.probe('jobs', 'a')
    assert job['state'] == 'quarantined'
    assert job['worker_failure'] == shape


def test_guard_terminal_assemble_words_demotes_to_held_for_redrive(caplog):
    """A guard terminal at assemble_words holds for the fenced redrive without the quarantine ERROR."""
    caplog.set_level(logging.INFO)
    shape = {"stage": "assemble_words", "reason": GUARD}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure=shape) is True
    guard, quar, warn = _split(caplog)
    assert len(guard) == 1 and not quar
    assert guard[0].levelno == logging.INFO
    assert 'outcome=held_for_redrive' in guard[0].getMessage()
    assert 'attempt=1' in guard[0].getMessage() and 'recovery=held' in guard[0].getMessage()
    assert (
        'stage=assemble_words' in guard[0].getMessage()
        and 'worker_reason=unsupported_language' in guard[0].getMessage()
    )
    assert len(warn) == 1
    job = store.probe('jobs', 'a')
    assert job['state'] == 'quarantined'
    assert job['worker_failure'] == shape


def test_guard_terminal_asr_recovery_demotes_to_held_for_redrive(caplog):
    """A guard terminal at asr_recovery holds for the fenced redrive without the quarantine ERROR."""
    caplog.set_level(logging.INFO)
    shape = {"stage": "asr_recovery", "reason": GUARD}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure=shape) is True
    guard, quar, warn = _split(caplog)
    assert len(guard) == 1 and not quar
    assert guard[0].levelno == logging.INFO
    assert 'outcome=held_for_redrive' in guard[0].getMessage()
    assert 'attempt=1' in guard[0].getMessage() and 'recovery=held' in guard[0].getMessage()
    assert (
        'stage=asr_recovery' in guard[0].getMessage() and 'worker_reason=unsupported_language' in guard[0].getMessage()
    )
    assert len(warn) == 1
    job = store.probe('jobs', 'a')
    assert job['state'] == 'quarantined'
    assert job['worker_failure'] == shape


def test_reason_word_shape_at_fetch_decode_keeps_quarantine_error(caplog):
    """word_shape at fetch_decode keeps the terminal quarantine ERROR."""
    caplog.set_level(logging.INFO)
    shape = {"stage": "fetch_decode", "reason": "word_shape"}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure=shape) is True
    guard, quar, warn = _split(caplog)
    assert not guard and len(quar) == 1
    assert quar[0].levelno == logging.ERROR
    assert 'reason=worker_failed' in quar[0].getMessage()
    assert 'stage=fetch_decode' in quar[0].getMessage() and 'worker_reason=word_shape' in quar[0].getMessage()
    assert len(warn) == 1
    job = store.probe('jobs', 'a')
    assert job['state'] == 'quarantined' and job['worker_failure'] == shape


def test_reason_word_clock_at_fetch_decode_keeps_quarantine_error(caplog):
    """word_clock at fetch_decode keeps the terminal quarantine ERROR."""
    caplog.set_level(logging.INFO)
    shape = {"stage": "fetch_decode", "reason": "word_clock"}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure=shape) is True
    guard, quar, warn = _split(caplog)
    assert not guard and len(quar) == 1
    assert quar[0].levelno == logging.ERROR
    assert 'reason=worker_failed' in quar[0].getMessage()
    assert 'stage=fetch_decode' in quar[0].getMessage() and 'worker_reason=word_clock' in quar[0].getMessage()
    assert len(warn) == 1
    job = store.probe('jobs', 'a')
    assert job['state'] == 'quarantined' and job['worker_failure'] == shape


def test_reason_word_sequence_at_fetch_decode_keeps_quarantine_error(caplog):
    """word_sequence at fetch_decode keeps the terminal quarantine ERROR."""
    caplog.set_level(logging.INFO)
    shape = {"stage": "fetch_decode", "reason": "word_sequence"}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure=shape) is True
    guard, quar, warn = _split(caplog)
    assert not guard and len(quar) == 1
    assert quar[0].levelno == logging.ERROR
    assert 'reason=worker_failed' in quar[0].getMessage()
    assert 'stage=fetch_decode' in quar[0].getMessage() and 'worker_reason=word_sequence' in quar[0].getMessage()
    assert len(warn) == 1
    job = store.probe('jobs', 'a')
    assert job['state'] == 'quarantined' and job['worker_failure'] == shape


def test_reason_vad_nonfinite_at_fetch_decode_keeps_quarantine_error(caplog):
    """vad_nonfinite at fetch_decode keeps the terminal quarantine ERROR."""
    caplog.set_level(logging.INFO)
    shape = {"stage": "fetch_decode", "reason": "vad_nonfinite"}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure=shape) is True
    guard, quar, warn = _split(caplog)
    assert not guard and len(quar) == 1
    assert quar[0].levelno == logging.ERROR
    assert 'reason=worker_failed' in quar[0].getMessage()
    assert 'stage=fetch_decode' in quar[0].getMessage() and 'worker_reason=vad_nonfinite' in quar[0].getMessage()
    assert len(warn) == 1
    job = store.probe('jobs', 'a')
    assert job['state'] == 'quarantined' and job['worker_failure'] == shape


def test_reason_vad_order_at_fetch_decode_keeps_quarantine_error(caplog):
    """vad_order at fetch_decode keeps the terminal quarantine ERROR."""
    caplog.set_level(logging.INFO)
    shape = {"stage": "fetch_decode", "reason": "vad_order"}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure=shape) is True
    guard, quar, warn = _split(caplog)
    assert not guard and len(quar) == 1
    assert quar[0].levelno == logging.ERROR
    assert 'reason=worker_failed' in quar[0].getMessage()
    assert 'stage=fetch_decode' in quar[0].getMessage() and 'worker_reason=vad_order' in quar[0].getMessage()
    assert len(warn) == 1
    job = store.probe('jobs', 'a')
    assert job['state'] == 'quarantined' and job['worker_failure'] == shape


def test_reason_vad_bounds_at_fetch_decode_keeps_quarantine_error(caplog):
    """vad_bounds at fetch_decode keeps the terminal quarantine ERROR."""
    caplog.set_level(logging.INFO)
    shape = {"stage": "fetch_decode", "reason": "vad_bounds"}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure=shape) is True
    guard, quar, warn = _split(caplog)
    assert not guard and len(quar) == 1
    assert quar[0].levelno == logging.ERROR
    assert 'reason=worker_failed' in quar[0].getMessage()
    assert 'stage=fetch_decode' in quar[0].getMessage() and 'worker_reason=vad_bounds' in quar[0].getMessage()
    assert len(warn) == 1
    job = store.probe('jobs', 'a')
    assert job['state'] == 'quarantined' and job['worker_failure'] == shape


def test_reason_empty_asr_at_fetch_decode_keeps_quarantine_error(caplog):
    """empty_asr at fetch_decode keeps the terminal quarantine ERROR."""
    caplog.set_level(logging.INFO)
    shape = {"stage": "fetch_decode", "reason": "empty_asr"}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure=shape) is True
    guard, quar, warn = _split(caplog)
    assert not guard and len(quar) == 1
    assert quar[0].levelno == logging.ERROR
    assert 'reason=worker_failed' in quar[0].getMessage()
    assert 'stage=fetch_decode' in quar[0].getMessage() and 'worker_reason=empty_asr' in quar[0].getMessage()
    assert len(warn) == 1
    job = store.probe('jobs', 'a')
    assert job['state'] == 'quarantined' and job['worker_failure'] == shape


def test_reason_no_owned_words_at_fetch_decode_keeps_quarantine_error(caplog):
    """no_owned_words at fetch_decode keeps the terminal quarantine ERROR."""
    caplog.set_level(logging.INFO)
    shape = {"stage": "fetch_decode", "reason": "no_owned_words"}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure=shape) is True
    guard, quar, warn = _split(caplog)
    assert not guard and len(quar) == 1
    assert quar[0].levelno == logging.ERROR
    assert 'reason=worker_failed' in quar[0].getMessage()
    assert 'stage=fetch_decode' in quar[0].getMessage() and 'worker_reason=no_owned_words' in quar[0].getMessage()
    assert len(warn) == 1
    job = store.probe('jobs', 'a')
    assert job['state'] == 'quarantined' and job['worker_failure'] == shape


def test_reason_word_shape_at_vad_windows_keeps_quarantine_error(caplog):
    """word_shape at vad_windows keeps the terminal quarantine ERROR."""
    caplog.set_level(logging.INFO)
    shape = {"stage": "vad_windows", "reason": "word_shape"}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure=shape) is True
    guard, quar, warn = _split(caplog)
    assert not guard and len(quar) == 1
    assert quar[0].levelno == logging.ERROR
    assert 'reason=worker_failed' in quar[0].getMessage()
    assert 'stage=vad_windows' in quar[0].getMessage() and 'worker_reason=word_shape' in quar[0].getMessage()
    assert len(warn) == 1
    job = store.probe('jobs', 'a')
    assert job['state'] == 'quarantined' and job['worker_failure'] == shape


def test_reason_word_clock_at_vad_windows_keeps_quarantine_error(caplog):
    """word_clock at vad_windows keeps the terminal quarantine ERROR."""
    caplog.set_level(logging.INFO)
    shape = {"stage": "vad_windows", "reason": "word_clock"}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure=shape) is True
    guard, quar, warn = _split(caplog)
    assert not guard and len(quar) == 1
    assert quar[0].levelno == logging.ERROR
    assert 'reason=worker_failed' in quar[0].getMessage()
    assert 'stage=vad_windows' in quar[0].getMessage() and 'worker_reason=word_clock' in quar[0].getMessage()
    assert len(warn) == 1
    job = store.probe('jobs', 'a')
    assert job['state'] == 'quarantined' and job['worker_failure'] == shape


def test_reason_word_sequence_at_vad_windows_keeps_quarantine_error(caplog):
    """word_sequence at vad_windows keeps the terminal quarantine ERROR."""
    caplog.set_level(logging.INFO)
    shape = {"stage": "vad_windows", "reason": "word_sequence"}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure=shape) is True
    guard, quar, warn = _split(caplog)
    assert not guard and len(quar) == 1
    assert quar[0].levelno == logging.ERROR
    assert 'reason=worker_failed' in quar[0].getMessage()
    assert 'stage=vad_windows' in quar[0].getMessage() and 'worker_reason=word_sequence' in quar[0].getMessage()
    assert len(warn) == 1
    job = store.probe('jobs', 'a')
    assert job['state'] == 'quarantined' and job['worker_failure'] == shape


def test_reason_vad_nonfinite_at_vad_windows_keeps_quarantine_error(caplog):
    """vad_nonfinite at vad_windows keeps the terminal quarantine ERROR."""
    caplog.set_level(logging.INFO)
    shape = {"stage": "vad_windows", "reason": "vad_nonfinite"}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure=shape) is True
    guard, quar, warn = _split(caplog)
    assert not guard and len(quar) == 1
    assert quar[0].levelno == logging.ERROR
    assert 'reason=worker_failed' in quar[0].getMessage()
    assert 'stage=vad_windows' in quar[0].getMessage() and 'worker_reason=vad_nonfinite' in quar[0].getMessage()
    assert len(warn) == 1
    job = store.probe('jobs', 'a')
    assert job['state'] == 'quarantined' and job['worker_failure'] == shape


def test_reason_vad_order_at_vad_windows_keeps_quarantine_error(caplog):
    """vad_order at vad_windows keeps the terminal quarantine ERROR."""
    caplog.set_level(logging.INFO)
    shape = {"stage": "vad_windows", "reason": "vad_order"}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure=shape) is True
    guard, quar, warn = _split(caplog)
    assert not guard and len(quar) == 1
    assert quar[0].levelno == logging.ERROR
    assert 'reason=worker_failed' in quar[0].getMessage()
    assert 'stage=vad_windows' in quar[0].getMessage() and 'worker_reason=vad_order' in quar[0].getMessage()
    assert len(warn) == 1
    job = store.probe('jobs', 'a')
    assert job['state'] == 'quarantined' and job['worker_failure'] == shape


def test_reason_vad_bounds_at_vad_windows_keeps_quarantine_error(caplog):
    """vad_bounds at vad_windows keeps the terminal quarantine ERROR."""
    caplog.set_level(logging.INFO)
    shape = {"stage": "vad_windows", "reason": "vad_bounds"}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure=shape) is True
    guard, quar, warn = _split(caplog)
    assert not guard and len(quar) == 1
    assert quar[0].levelno == logging.ERROR
    assert 'reason=worker_failed' in quar[0].getMessage()
    assert 'stage=vad_windows' in quar[0].getMessage() and 'worker_reason=vad_bounds' in quar[0].getMessage()
    assert len(warn) == 1
    job = store.probe('jobs', 'a')
    assert job['state'] == 'quarantined' and job['worker_failure'] == shape


def test_reason_empty_asr_at_vad_windows_keeps_quarantine_error(caplog):
    """empty_asr at vad_windows keeps the terminal quarantine ERROR."""
    caplog.set_level(logging.INFO)
    shape = {"stage": "vad_windows", "reason": "empty_asr"}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure=shape) is True
    guard, quar, warn = _split(caplog)
    assert not guard and len(quar) == 1
    assert quar[0].levelno == logging.ERROR
    assert 'reason=worker_failed' in quar[0].getMessage()
    assert 'stage=vad_windows' in quar[0].getMessage() and 'worker_reason=empty_asr' in quar[0].getMessage()
    assert len(warn) == 1
    job = store.probe('jobs', 'a')
    assert job['state'] == 'quarantined' and job['worker_failure'] == shape


def test_reason_no_owned_words_at_vad_windows_keeps_quarantine_error(caplog):
    """no_owned_words at vad_windows keeps the terminal quarantine ERROR."""
    caplog.set_level(logging.INFO)
    shape = {"stage": "vad_windows", "reason": "no_owned_words"}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure=shape) is True
    guard, quar, warn = _split(caplog)
    assert not guard and len(quar) == 1
    assert quar[0].levelno == logging.ERROR
    assert 'reason=worker_failed' in quar[0].getMessage()
    assert 'stage=vad_windows' in quar[0].getMessage() and 'worker_reason=no_owned_words' in quar[0].getMessage()
    assert len(warn) == 1
    job = store.probe('jobs', 'a')
    assert job['state'] == 'quarantined' and job['worker_failure'] == shape


def test_reason_word_shape_at_word_clocks_keeps_quarantine_error(caplog):
    """word_shape at word_clocks keeps the terminal quarantine ERROR."""
    caplog.set_level(logging.INFO)
    shape = {"stage": "word_clocks", "reason": "word_shape"}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure=shape) is True
    guard, quar, warn = _split(caplog)
    assert not guard and len(quar) == 1
    assert quar[0].levelno == logging.ERROR
    assert 'reason=worker_failed' in quar[0].getMessage()
    assert 'stage=word_clocks' in quar[0].getMessage() and 'worker_reason=word_shape' in quar[0].getMessage()
    assert len(warn) == 1
    job = store.probe('jobs', 'a')
    assert job['state'] == 'quarantined' and job['worker_failure'] == shape


def test_reason_word_clock_at_word_clocks_keeps_quarantine_error(caplog):
    """word_clock at word_clocks keeps the terminal quarantine ERROR."""
    caplog.set_level(logging.INFO)
    shape = {"stage": "word_clocks", "reason": "word_clock"}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure=shape) is True
    guard, quar, warn = _split(caplog)
    assert not guard and len(quar) == 1
    assert quar[0].levelno == logging.ERROR
    assert 'reason=worker_failed' in quar[0].getMessage()
    assert 'stage=word_clocks' in quar[0].getMessage() and 'worker_reason=word_clock' in quar[0].getMessage()
    assert len(warn) == 1
    job = store.probe('jobs', 'a')
    assert job['state'] == 'quarantined' and job['worker_failure'] == shape


def test_reason_word_sequence_at_word_clocks_keeps_quarantine_error(caplog):
    """word_sequence at word_clocks keeps the terminal quarantine ERROR."""
    caplog.set_level(logging.INFO)
    shape = {"stage": "word_clocks", "reason": "word_sequence"}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure=shape) is True
    guard, quar, warn = _split(caplog)
    assert not guard and len(quar) == 1
    assert quar[0].levelno == logging.ERROR
    assert 'reason=worker_failed' in quar[0].getMessage()
    assert 'stage=word_clocks' in quar[0].getMessage() and 'worker_reason=word_sequence' in quar[0].getMessage()
    assert len(warn) == 1
    job = store.probe('jobs', 'a')
    assert job['state'] == 'quarantined' and job['worker_failure'] == shape


def test_reason_vad_nonfinite_at_word_clocks_keeps_quarantine_error(caplog):
    """vad_nonfinite at word_clocks keeps the terminal quarantine ERROR."""
    caplog.set_level(logging.INFO)
    shape = {"stage": "word_clocks", "reason": "vad_nonfinite"}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure=shape) is True
    guard, quar, warn = _split(caplog)
    assert not guard and len(quar) == 1
    assert quar[0].levelno == logging.ERROR
    assert 'reason=worker_failed' in quar[0].getMessage()
    assert 'stage=word_clocks' in quar[0].getMessage() and 'worker_reason=vad_nonfinite' in quar[0].getMessage()
    assert len(warn) == 1
    job = store.probe('jobs', 'a')
    assert job['state'] == 'quarantined' and job['worker_failure'] == shape


def test_reason_vad_order_at_word_clocks_keeps_quarantine_error(caplog):
    """vad_order at word_clocks keeps the terminal quarantine ERROR."""
    caplog.set_level(logging.INFO)
    shape = {"stage": "word_clocks", "reason": "vad_order"}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure=shape) is True
    guard, quar, warn = _split(caplog)
    assert not guard and len(quar) == 1
    assert quar[0].levelno == logging.ERROR
    assert 'reason=worker_failed' in quar[0].getMessage()
    assert 'stage=word_clocks' in quar[0].getMessage() and 'worker_reason=vad_order' in quar[0].getMessage()
    assert len(warn) == 1
    job = store.probe('jobs', 'a')
    assert job['state'] == 'quarantined' and job['worker_failure'] == shape


def test_reason_vad_bounds_at_word_clocks_keeps_quarantine_error(caplog):
    """vad_bounds at word_clocks keeps the terminal quarantine ERROR."""
    caplog.set_level(logging.INFO)
    shape = {"stage": "word_clocks", "reason": "vad_bounds"}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure=shape) is True
    guard, quar, warn = _split(caplog)
    assert not guard and len(quar) == 1
    assert quar[0].levelno == logging.ERROR
    assert 'reason=worker_failed' in quar[0].getMessage()
    assert 'stage=word_clocks' in quar[0].getMessage() and 'worker_reason=vad_bounds' in quar[0].getMessage()
    assert len(warn) == 1
    job = store.probe('jobs', 'a')
    assert job['state'] == 'quarantined' and job['worker_failure'] == shape


def test_reason_empty_asr_at_word_clocks_keeps_quarantine_error(caplog):
    """empty_asr at word_clocks keeps the terminal quarantine ERROR."""
    caplog.set_level(logging.INFO)
    shape = {"stage": "word_clocks", "reason": "empty_asr"}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure=shape) is True
    guard, quar, warn = _split(caplog)
    assert not guard and len(quar) == 1
    assert quar[0].levelno == logging.ERROR
    assert 'reason=worker_failed' in quar[0].getMessage()
    assert 'stage=word_clocks' in quar[0].getMessage() and 'worker_reason=empty_asr' in quar[0].getMessage()
    assert len(warn) == 1
    job = store.probe('jobs', 'a')
    assert job['state'] == 'quarantined' and job['worker_failure'] == shape


def test_reason_no_owned_words_at_word_clocks_keeps_quarantine_error(caplog):
    """no_owned_words at word_clocks keeps the terminal quarantine ERROR."""
    caplog.set_level(logging.INFO)
    shape = {"stage": "word_clocks", "reason": "no_owned_words"}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure=shape) is True
    guard, quar, warn = _split(caplog)
    assert not guard and len(quar) == 1
    assert quar[0].levelno == logging.ERROR
    assert 'reason=worker_failed' in quar[0].getMessage()
    assert 'stage=word_clocks' in quar[0].getMessage() and 'worker_reason=no_owned_words' in quar[0].getMessage()
    assert len(warn) == 1
    job = store.probe('jobs', 'a')
    assert job['state'] == 'quarantined' and job['worker_failure'] == shape


def test_reason_word_shape_at_assemble_words_keeps_quarantine_error(caplog):
    """word_shape at assemble_words keeps the terminal quarantine ERROR."""
    caplog.set_level(logging.INFO)
    shape = {"stage": "assemble_words", "reason": "word_shape"}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure=shape) is True
    guard, quar, warn = _split(caplog)
    assert not guard and len(quar) == 1
    assert quar[0].levelno == logging.ERROR
    assert 'reason=worker_failed' in quar[0].getMessage()
    assert 'stage=assemble_words' in quar[0].getMessage() and 'worker_reason=word_shape' in quar[0].getMessage()
    assert len(warn) == 1
    job = store.probe('jobs', 'a')
    assert job['state'] == 'quarantined' and job['worker_failure'] == shape


def test_reason_word_clock_at_assemble_words_keeps_quarantine_error(caplog):
    """word_clock at assemble_words keeps the terminal quarantine ERROR."""
    caplog.set_level(logging.INFO)
    shape = {"stage": "assemble_words", "reason": "word_clock"}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure=shape) is True
    guard, quar, warn = _split(caplog)
    assert not guard and len(quar) == 1
    assert quar[0].levelno == logging.ERROR
    assert 'reason=worker_failed' in quar[0].getMessage()
    assert 'stage=assemble_words' in quar[0].getMessage() and 'worker_reason=word_clock' in quar[0].getMessage()
    assert len(warn) == 1
    job = store.probe('jobs', 'a')
    assert job['state'] == 'quarantined' and job['worker_failure'] == shape


def test_reason_word_sequence_at_assemble_words_keeps_quarantine_error(caplog):
    """word_sequence at assemble_words keeps the terminal quarantine ERROR."""
    caplog.set_level(logging.INFO)
    shape = {"stage": "assemble_words", "reason": "word_sequence"}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure=shape) is True
    guard, quar, warn = _split(caplog)
    assert not guard and len(quar) == 1
    assert quar[0].levelno == logging.ERROR
    assert 'reason=worker_failed' in quar[0].getMessage()
    assert 'stage=assemble_words' in quar[0].getMessage() and 'worker_reason=word_sequence' in quar[0].getMessage()
    assert len(warn) == 1
    job = store.probe('jobs', 'a')
    assert job['state'] == 'quarantined' and job['worker_failure'] == shape


def test_reason_vad_nonfinite_at_assemble_words_keeps_quarantine_error(caplog):
    """vad_nonfinite at assemble_words keeps the terminal quarantine ERROR."""
    caplog.set_level(logging.INFO)
    shape = {"stage": "assemble_words", "reason": "vad_nonfinite"}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure=shape) is True
    guard, quar, warn = _split(caplog)
    assert not guard and len(quar) == 1
    assert quar[0].levelno == logging.ERROR
    assert 'reason=worker_failed' in quar[0].getMessage()
    assert 'stage=assemble_words' in quar[0].getMessage() and 'worker_reason=vad_nonfinite' in quar[0].getMessage()
    assert len(warn) == 1
    job = store.probe('jobs', 'a')
    assert job['state'] == 'quarantined' and job['worker_failure'] == shape


def test_reason_vad_order_at_assemble_words_keeps_quarantine_error(caplog):
    """vad_order at assemble_words keeps the terminal quarantine ERROR."""
    caplog.set_level(logging.INFO)
    shape = {"stage": "assemble_words", "reason": "vad_order"}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure=shape) is True
    guard, quar, warn = _split(caplog)
    assert not guard and len(quar) == 1
    assert quar[0].levelno == logging.ERROR
    assert 'reason=worker_failed' in quar[0].getMessage()
    assert 'stage=assemble_words' in quar[0].getMessage() and 'worker_reason=vad_order' in quar[0].getMessage()
    assert len(warn) == 1
    job = store.probe('jobs', 'a')
    assert job['state'] == 'quarantined' and job['worker_failure'] == shape


def test_reason_vad_bounds_at_assemble_words_keeps_quarantine_error(caplog):
    """vad_bounds at assemble_words keeps the terminal quarantine ERROR."""
    caplog.set_level(logging.INFO)
    shape = {"stage": "assemble_words", "reason": "vad_bounds"}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure=shape) is True
    guard, quar, warn = _split(caplog)
    assert not guard and len(quar) == 1
    assert quar[0].levelno == logging.ERROR
    assert 'reason=worker_failed' in quar[0].getMessage()
    assert 'stage=assemble_words' in quar[0].getMessage() and 'worker_reason=vad_bounds' in quar[0].getMessage()
    assert len(warn) == 1
    job = store.probe('jobs', 'a')
    assert job['state'] == 'quarantined' and job['worker_failure'] == shape


def test_reason_empty_asr_at_assemble_words_keeps_quarantine_error(caplog):
    """empty_asr at assemble_words keeps the terminal quarantine ERROR."""
    caplog.set_level(logging.INFO)
    shape = {"stage": "assemble_words", "reason": "empty_asr"}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure=shape) is True
    guard, quar, warn = _split(caplog)
    assert not guard and len(quar) == 1
    assert quar[0].levelno == logging.ERROR
    assert 'reason=worker_failed' in quar[0].getMessage()
    assert 'stage=assemble_words' in quar[0].getMessage() and 'worker_reason=empty_asr' in quar[0].getMessage()
    assert len(warn) == 1
    job = store.probe('jobs', 'a')
    assert job['state'] == 'quarantined' and job['worker_failure'] == shape


def test_reason_no_owned_words_at_assemble_words_keeps_quarantine_error(caplog):
    """no_owned_words at assemble_words keeps the terminal quarantine ERROR."""
    caplog.set_level(logging.INFO)
    shape = {"stage": "assemble_words", "reason": "no_owned_words"}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure=shape) is True
    guard, quar, warn = _split(caplog)
    assert not guard and len(quar) == 1
    assert quar[0].levelno == logging.ERROR
    assert 'reason=worker_failed' in quar[0].getMessage()
    assert 'stage=assemble_words' in quar[0].getMessage() and 'worker_reason=no_owned_words' in quar[0].getMessage()
    assert len(warn) == 1
    job = store.probe('jobs', 'a')
    assert job['state'] == 'quarantined' and job['worker_failure'] == shape


def test_reason_word_shape_at_asr_recovery_keeps_quarantine_error(caplog):
    """word_shape at asr_recovery keeps the terminal quarantine ERROR."""
    caplog.set_level(logging.INFO)
    shape = {"stage": "asr_recovery", "reason": "word_shape"}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure=shape) is True
    guard, quar, warn = _split(caplog)
    assert not guard and len(quar) == 1
    assert quar[0].levelno == logging.ERROR
    assert 'reason=worker_failed' in quar[0].getMessage()
    assert 'stage=asr_recovery' in quar[0].getMessage() and 'worker_reason=word_shape' in quar[0].getMessage()
    assert len(warn) == 1
    job = store.probe('jobs', 'a')
    assert job['state'] == 'quarantined' and job['worker_failure'] == shape


def test_reason_word_clock_at_asr_recovery_keeps_quarantine_error(caplog):
    """word_clock at asr_recovery keeps the terminal quarantine ERROR."""
    caplog.set_level(logging.INFO)
    shape = {"stage": "asr_recovery", "reason": "word_clock"}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure=shape) is True
    guard, quar, warn = _split(caplog)
    assert not guard and len(quar) == 1
    assert quar[0].levelno == logging.ERROR
    assert 'reason=worker_failed' in quar[0].getMessage()
    assert 'stage=asr_recovery' in quar[0].getMessage() and 'worker_reason=word_clock' in quar[0].getMessage()
    assert len(warn) == 1
    job = store.probe('jobs', 'a')
    assert job['state'] == 'quarantined' and job['worker_failure'] == shape


def test_reason_word_sequence_at_asr_recovery_keeps_quarantine_error(caplog):
    """word_sequence at asr_recovery keeps the terminal quarantine ERROR."""
    caplog.set_level(logging.INFO)
    shape = {"stage": "asr_recovery", "reason": "word_sequence"}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure=shape) is True
    guard, quar, warn = _split(caplog)
    assert not guard and len(quar) == 1
    assert quar[0].levelno == logging.ERROR
    assert 'reason=worker_failed' in quar[0].getMessage()
    assert 'stage=asr_recovery' in quar[0].getMessage() and 'worker_reason=word_sequence' in quar[0].getMessage()
    assert len(warn) == 1
    job = store.probe('jobs', 'a')
    assert job['state'] == 'quarantined' and job['worker_failure'] == shape


def test_reason_vad_nonfinite_at_asr_recovery_keeps_quarantine_error(caplog):
    """vad_nonfinite at asr_recovery keeps the terminal quarantine ERROR."""
    caplog.set_level(logging.INFO)
    shape = {"stage": "asr_recovery", "reason": "vad_nonfinite"}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure=shape) is True
    guard, quar, warn = _split(caplog)
    assert not guard and len(quar) == 1
    assert quar[0].levelno == logging.ERROR
    assert 'reason=worker_failed' in quar[0].getMessage()
    assert 'stage=asr_recovery' in quar[0].getMessage() and 'worker_reason=vad_nonfinite' in quar[0].getMessage()
    assert len(warn) == 1
    job = store.probe('jobs', 'a')
    assert job['state'] == 'quarantined' and job['worker_failure'] == shape


def test_reason_vad_order_at_asr_recovery_keeps_quarantine_error(caplog):
    """vad_order at asr_recovery keeps the terminal quarantine ERROR."""
    caplog.set_level(logging.INFO)
    shape = {"stage": "asr_recovery", "reason": "vad_order"}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure=shape) is True
    guard, quar, warn = _split(caplog)
    assert not guard and len(quar) == 1
    assert quar[0].levelno == logging.ERROR
    assert 'reason=worker_failed' in quar[0].getMessage()
    assert 'stage=asr_recovery' in quar[0].getMessage() and 'worker_reason=vad_order' in quar[0].getMessage()
    assert len(warn) == 1
    job = store.probe('jobs', 'a')
    assert job['state'] == 'quarantined' and job['worker_failure'] == shape


def test_reason_vad_bounds_at_asr_recovery_keeps_quarantine_error(caplog):
    """vad_bounds at asr_recovery keeps the terminal quarantine ERROR."""
    caplog.set_level(logging.INFO)
    shape = {"stage": "asr_recovery", "reason": "vad_bounds"}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure=shape) is True
    guard, quar, warn = _split(caplog)
    assert not guard and len(quar) == 1
    assert quar[0].levelno == logging.ERROR
    assert 'reason=worker_failed' in quar[0].getMessage()
    assert 'stage=asr_recovery' in quar[0].getMessage() and 'worker_reason=vad_bounds' in quar[0].getMessage()
    assert len(warn) == 1
    job = store.probe('jobs', 'a')
    assert job['state'] == 'quarantined' and job['worker_failure'] == shape


def test_reason_empty_asr_at_asr_recovery_keeps_quarantine_error(caplog):
    """empty_asr at asr_recovery keeps the terminal quarantine ERROR."""
    caplog.set_level(logging.INFO)
    shape = {"stage": "asr_recovery", "reason": "empty_asr"}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure=shape) is True
    guard, quar, warn = _split(caplog)
    assert not guard and len(quar) == 1
    assert quar[0].levelno == logging.ERROR
    assert 'reason=worker_failed' in quar[0].getMessage()
    assert 'stage=asr_recovery' in quar[0].getMessage() and 'worker_reason=empty_asr' in quar[0].getMessage()
    assert len(warn) == 1
    job = store.probe('jobs', 'a')
    assert job['state'] == 'quarantined' and job['worker_failure'] == shape


def test_reason_no_owned_words_at_asr_recovery_keeps_quarantine_error(caplog):
    """no_owned_words at asr_recovery keeps the terminal quarantine ERROR."""
    caplog.set_level(logging.INFO)
    shape = {"stage": "asr_recovery", "reason": "no_owned_words"}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure=shape) is True
    guard, quar, warn = _split(caplog)
    assert not guard and len(quar) == 1
    assert quar[0].levelno == logging.ERROR
    assert 'reason=worker_failed' in quar[0].getMessage()
    assert 'stage=asr_recovery' in quar[0].getMessage() and 'worker_reason=no_owned_words' in quar[0].getMessage()
    assert len(warn) == 1
    job = store.probe('jobs', 'a')
    assert job['state'] == 'quarantined' and job['worker_failure'] == shape


def test_evidence_unsupported_language_at_fetch_decode_defers_without_terminal_lines(caplog):
    """Evidence-only unsupported_language at fetch_decode rides the ladder; no terminal line exists."""
    caplog.set_level(logging.INFO)
    shape = {"stage": "fetch_decode", "reason": "unsupported_language"}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure_evidence=shape) is True
    guard, quar, warn = _split(caplog)
    assert not guard and not quar and not warn
    job = store.probe('jobs', 'a')
    assert job['state'] == 'retry'
    assert job['worker_failure_evidence'] == shape


def test_evidence_word_shape_at_fetch_decode_defers_without_terminal_lines(caplog):
    """Evidence-only word_shape at fetch_decode rides the ladder; no terminal line exists."""
    caplog.set_level(logging.INFO)
    shape = {"stage": "fetch_decode", "reason": "word_shape"}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure_evidence=shape) is True
    guard, quar, warn = _split(caplog)
    assert not guard and not quar and not warn
    job = store.probe('jobs', 'a')
    assert job['state'] == 'retry'
    assert job['worker_failure_evidence'] == shape


def test_evidence_word_clock_at_fetch_decode_defers_without_terminal_lines(caplog):
    """Evidence-only word_clock at fetch_decode rides the ladder; no terminal line exists."""
    caplog.set_level(logging.INFO)
    shape = {"stage": "fetch_decode", "reason": "word_clock"}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure_evidence=shape) is True
    guard, quar, warn = _split(caplog)
    assert not guard and not quar and not warn
    job = store.probe('jobs', 'a')
    assert job['state'] == 'retry'
    assert job['worker_failure_evidence'] == shape


def test_evidence_word_sequence_at_fetch_decode_defers_without_terminal_lines(caplog):
    """Evidence-only word_sequence at fetch_decode rides the ladder; no terminal line exists."""
    caplog.set_level(logging.INFO)
    shape = {"stage": "fetch_decode", "reason": "word_sequence"}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure_evidence=shape) is True
    guard, quar, warn = _split(caplog)
    assert not guard and not quar and not warn
    job = store.probe('jobs', 'a')
    assert job['state'] == 'retry'
    assert job['worker_failure_evidence'] == shape


def test_evidence_vad_nonfinite_at_fetch_decode_defers_without_terminal_lines(caplog):
    """Evidence-only vad_nonfinite at fetch_decode rides the ladder; no terminal line exists."""
    caplog.set_level(logging.INFO)
    shape = {"stage": "fetch_decode", "reason": "vad_nonfinite"}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure_evidence=shape) is True
    guard, quar, warn = _split(caplog)
    assert not guard and not quar and not warn
    job = store.probe('jobs', 'a')
    assert job['state'] == 'retry'
    assert job['worker_failure_evidence'] == shape


def test_evidence_vad_order_at_fetch_decode_defers_without_terminal_lines(caplog):
    """Evidence-only vad_order at fetch_decode rides the ladder; no terminal line exists."""
    caplog.set_level(logging.INFO)
    shape = {"stage": "fetch_decode", "reason": "vad_order"}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure_evidence=shape) is True
    guard, quar, warn = _split(caplog)
    assert not guard and not quar and not warn
    job = store.probe('jobs', 'a')
    assert job['state'] == 'retry'
    assert job['worker_failure_evidence'] == shape


def test_evidence_vad_bounds_at_fetch_decode_defers_without_terminal_lines(caplog):
    """Evidence-only vad_bounds at fetch_decode rides the ladder; no terminal line exists."""
    caplog.set_level(logging.INFO)
    shape = {"stage": "fetch_decode", "reason": "vad_bounds"}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure_evidence=shape) is True
    guard, quar, warn = _split(caplog)
    assert not guard and not quar and not warn
    job = store.probe('jobs', 'a')
    assert job['state'] == 'retry'
    assert job['worker_failure_evidence'] == shape


def test_evidence_empty_asr_at_fetch_decode_defers_without_terminal_lines(caplog):
    """Evidence-only empty_asr at fetch_decode rides the ladder; no terminal line exists."""
    caplog.set_level(logging.INFO)
    shape = {"stage": "fetch_decode", "reason": "empty_asr"}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure_evidence=shape) is True
    guard, quar, warn = _split(caplog)
    assert not guard and not quar and not warn
    job = store.probe('jobs', 'a')
    assert job['state'] == 'retry'
    assert job['worker_failure_evidence'] == shape


def test_evidence_no_owned_words_at_fetch_decode_defers_without_terminal_lines(caplog):
    """Evidence-only no_owned_words at fetch_decode rides the ladder; no terminal line exists."""
    caplog.set_level(logging.INFO)
    shape = {"stage": "fetch_decode", "reason": "no_owned_words"}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure_evidence=shape) is True
    guard, quar, warn = _split(caplog)
    assert not guard and not quar and not warn
    job = store.probe('jobs', 'a')
    assert job['state'] == 'retry'
    assert job['worker_failure_evidence'] == shape


def test_evidence_unsupported_language_at_vad_windows_defers_without_terminal_lines(caplog):
    """Evidence-only unsupported_language at vad_windows rides the ladder; no terminal line exists."""
    caplog.set_level(logging.INFO)
    shape = {"stage": "vad_windows", "reason": "unsupported_language"}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure_evidence=shape) is True
    guard, quar, warn = _split(caplog)
    assert not guard and not quar and not warn
    job = store.probe('jobs', 'a')
    assert job['state'] == 'retry'
    assert job['worker_failure_evidence'] == shape


def test_evidence_word_shape_at_vad_windows_defers_without_terminal_lines(caplog):
    """Evidence-only word_shape at vad_windows rides the ladder; no terminal line exists."""
    caplog.set_level(logging.INFO)
    shape = {"stage": "vad_windows", "reason": "word_shape"}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure_evidence=shape) is True
    guard, quar, warn = _split(caplog)
    assert not guard and not quar and not warn
    job = store.probe('jobs', 'a')
    assert job['state'] == 'retry'
    assert job['worker_failure_evidence'] == shape


def test_evidence_word_clock_at_vad_windows_defers_without_terminal_lines(caplog):
    """Evidence-only word_clock at vad_windows rides the ladder; no terminal line exists."""
    caplog.set_level(logging.INFO)
    shape = {"stage": "vad_windows", "reason": "word_clock"}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure_evidence=shape) is True
    guard, quar, warn = _split(caplog)
    assert not guard and not quar and not warn
    job = store.probe('jobs', 'a')
    assert job['state'] == 'retry'
    assert job['worker_failure_evidence'] == shape


def test_evidence_word_sequence_at_vad_windows_defers_without_terminal_lines(caplog):
    """Evidence-only word_sequence at vad_windows rides the ladder; no terminal line exists."""
    caplog.set_level(logging.INFO)
    shape = {"stage": "vad_windows", "reason": "word_sequence"}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure_evidence=shape) is True
    guard, quar, warn = _split(caplog)
    assert not guard and not quar and not warn
    job = store.probe('jobs', 'a')
    assert job['state'] == 'retry'
    assert job['worker_failure_evidence'] == shape


def test_evidence_vad_nonfinite_at_vad_windows_defers_without_terminal_lines(caplog):
    """Evidence-only vad_nonfinite at vad_windows rides the ladder; no terminal line exists."""
    caplog.set_level(logging.INFO)
    shape = {"stage": "vad_windows", "reason": "vad_nonfinite"}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure_evidence=shape) is True
    guard, quar, warn = _split(caplog)
    assert not guard and not quar and not warn
    job = store.probe('jobs', 'a')
    assert job['state'] == 'retry'
    assert job['worker_failure_evidence'] == shape


def test_evidence_vad_order_at_vad_windows_defers_without_terminal_lines(caplog):
    """Evidence-only vad_order at vad_windows rides the ladder; no terminal line exists."""
    caplog.set_level(logging.INFO)
    shape = {"stage": "vad_windows", "reason": "vad_order"}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure_evidence=shape) is True
    guard, quar, warn = _split(caplog)
    assert not guard and not quar and not warn
    job = store.probe('jobs', 'a')
    assert job['state'] == 'retry'
    assert job['worker_failure_evidence'] == shape


def test_evidence_vad_bounds_at_vad_windows_defers_without_terminal_lines(caplog):
    """Evidence-only vad_bounds at vad_windows rides the ladder; no terminal line exists."""
    caplog.set_level(logging.INFO)
    shape = {"stage": "vad_windows", "reason": "vad_bounds"}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure_evidence=shape) is True
    guard, quar, warn = _split(caplog)
    assert not guard and not quar and not warn
    job = store.probe('jobs', 'a')
    assert job['state'] == 'retry'
    assert job['worker_failure_evidence'] == shape


def test_evidence_empty_asr_at_vad_windows_defers_without_terminal_lines(caplog):
    """Evidence-only empty_asr at vad_windows rides the ladder; no terminal line exists."""
    caplog.set_level(logging.INFO)
    shape = {"stage": "vad_windows", "reason": "empty_asr"}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure_evidence=shape) is True
    guard, quar, warn = _split(caplog)
    assert not guard and not quar and not warn
    job = store.probe('jobs', 'a')
    assert job['state'] == 'retry'
    assert job['worker_failure_evidence'] == shape


def test_evidence_no_owned_words_at_vad_windows_defers_without_terminal_lines(caplog):
    """Evidence-only no_owned_words at vad_windows rides the ladder; no terminal line exists."""
    caplog.set_level(logging.INFO)
    shape = {"stage": "vad_windows", "reason": "no_owned_words"}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure_evidence=shape) is True
    guard, quar, warn = _split(caplog)
    assert not guard and not quar and not warn
    job = store.probe('jobs', 'a')
    assert job['state'] == 'retry'
    assert job['worker_failure_evidence'] == shape


def test_evidence_unsupported_language_at_word_clocks_defers_without_terminal_lines(caplog):
    """Evidence-only unsupported_language at word_clocks rides the ladder; no terminal line exists."""
    caplog.set_level(logging.INFO)
    shape = {"stage": "word_clocks", "reason": "unsupported_language"}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure_evidence=shape) is True
    guard, quar, warn = _split(caplog)
    assert not guard and not quar and not warn
    job = store.probe('jobs', 'a')
    assert job['state'] == 'retry'
    assert job['worker_failure_evidence'] == shape


def test_evidence_word_shape_at_word_clocks_defers_without_terminal_lines(caplog):
    """Evidence-only word_shape at word_clocks rides the ladder; no terminal line exists."""
    caplog.set_level(logging.INFO)
    shape = {"stage": "word_clocks", "reason": "word_shape"}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure_evidence=shape) is True
    guard, quar, warn = _split(caplog)
    assert not guard and not quar and not warn
    job = store.probe('jobs', 'a')
    assert job['state'] == 'retry'
    assert job['worker_failure_evidence'] == shape


def test_evidence_word_clock_at_word_clocks_defers_without_terminal_lines(caplog):
    """Evidence-only word_clock at word_clocks rides the ladder; no terminal line exists."""
    caplog.set_level(logging.INFO)
    shape = {"stage": "word_clocks", "reason": "word_clock"}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure_evidence=shape) is True
    guard, quar, warn = _split(caplog)
    assert not guard and not quar and not warn
    job = store.probe('jobs', 'a')
    assert job['state'] == 'retry'
    assert job['worker_failure_evidence'] == shape


def test_evidence_word_sequence_at_word_clocks_defers_without_terminal_lines(caplog):
    """Evidence-only word_sequence at word_clocks rides the ladder; no terminal line exists."""
    caplog.set_level(logging.INFO)
    shape = {"stage": "word_clocks", "reason": "word_sequence"}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure_evidence=shape) is True
    guard, quar, warn = _split(caplog)
    assert not guard and not quar and not warn
    job = store.probe('jobs', 'a')
    assert job['state'] == 'retry'
    assert job['worker_failure_evidence'] == shape


def test_evidence_vad_nonfinite_at_word_clocks_defers_without_terminal_lines(caplog):
    """Evidence-only vad_nonfinite at word_clocks rides the ladder; no terminal line exists."""
    caplog.set_level(logging.INFO)
    shape = {"stage": "word_clocks", "reason": "vad_nonfinite"}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure_evidence=shape) is True
    guard, quar, warn = _split(caplog)
    assert not guard and not quar and not warn
    job = store.probe('jobs', 'a')
    assert job['state'] == 'retry'
    assert job['worker_failure_evidence'] == shape


def test_evidence_vad_order_at_word_clocks_defers_without_terminal_lines(caplog):
    """Evidence-only vad_order at word_clocks rides the ladder; no terminal line exists."""
    caplog.set_level(logging.INFO)
    shape = {"stage": "word_clocks", "reason": "vad_order"}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure_evidence=shape) is True
    guard, quar, warn = _split(caplog)
    assert not guard and not quar and not warn
    job = store.probe('jobs', 'a')
    assert job['state'] == 'retry'
    assert job['worker_failure_evidence'] == shape


def test_evidence_vad_bounds_at_word_clocks_defers_without_terminal_lines(caplog):
    """Evidence-only vad_bounds at word_clocks rides the ladder; no terminal line exists."""
    caplog.set_level(logging.INFO)
    shape = {"stage": "word_clocks", "reason": "vad_bounds"}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure_evidence=shape) is True
    guard, quar, warn = _split(caplog)
    assert not guard and not quar and not warn
    job = store.probe('jobs', 'a')
    assert job['state'] == 'retry'
    assert job['worker_failure_evidence'] == shape


def test_evidence_empty_asr_at_word_clocks_defers_without_terminal_lines(caplog):
    """Evidence-only empty_asr at word_clocks rides the ladder; no terminal line exists."""
    caplog.set_level(logging.INFO)
    shape = {"stage": "word_clocks", "reason": "empty_asr"}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure_evidence=shape) is True
    guard, quar, warn = _split(caplog)
    assert not guard and not quar and not warn
    job = store.probe('jobs', 'a')
    assert job['state'] == 'retry'
    assert job['worker_failure_evidence'] == shape


def test_evidence_no_owned_words_at_word_clocks_defers_without_terminal_lines(caplog):
    """Evidence-only no_owned_words at word_clocks rides the ladder; no terminal line exists."""
    caplog.set_level(logging.INFO)
    shape = {"stage": "word_clocks", "reason": "no_owned_words"}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure_evidence=shape) is True
    guard, quar, warn = _split(caplog)
    assert not guard and not quar and not warn
    job = store.probe('jobs', 'a')
    assert job['state'] == 'retry'
    assert job['worker_failure_evidence'] == shape


def test_evidence_unsupported_language_at_assemble_words_defers_without_terminal_lines(caplog):
    """Evidence-only unsupported_language at assemble_words rides the ladder; no terminal line exists."""
    caplog.set_level(logging.INFO)
    shape = {"stage": "assemble_words", "reason": "unsupported_language"}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure_evidence=shape) is True
    guard, quar, warn = _split(caplog)
    assert not guard and not quar and not warn
    job = store.probe('jobs', 'a')
    assert job['state'] == 'retry'
    assert job['worker_failure_evidence'] == shape


def test_evidence_word_shape_at_assemble_words_defers_without_terminal_lines(caplog):
    """Evidence-only word_shape at assemble_words rides the ladder; no terminal line exists."""
    caplog.set_level(logging.INFO)
    shape = {"stage": "assemble_words", "reason": "word_shape"}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure_evidence=shape) is True
    guard, quar, warn = _split(caplog)
    assert not guard and not quar and not warn
    job = store.probe('jobs', 'a')
    assert job['state'] == 'retry'
    assert job['worker_failure_evidence'] == shape


def test_evidence_word_clock_at_assemble_words_defers_without_terminal_lines(caplog):
    """Evidence-only word_clock at assemble_words rides the ladder; no terminal line exists."""
    caplog.set_level(logging.INFO)
    shape = {"stage": "assemble_words", "reason": "word_clock"}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure_evidence=shape) is True
    guard, quar, warn = _split(caplog)
    assert not guard and not quar and not warn
    job = store.probe('jobs', 'a')
    assert job['state'] == 'retry'
    assert job['worker_failure_evidence'] == shape


def test_evidence_word_sequence_at_assemble_words_defers_without_terminal_lines(caplog):
    """Evidence-only word_sequence at assemble_words rides the ladder; no terminal line exists."""
    caplog.set_level(logging.INFO)
    shape = {"stage": "assemble_words", "reason": "word_sequence"}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure_evidence=shape) is True
    guard, quar, warn = _split(caplog)
    assert not guard and not quar and not warn
    job = store.probe('jobs', 'a')
    assert job['state'] == 'retry'
    assert job['worker_failure_evidence'] == shape


def test_evidence_vad_nonfinite_at_assemble_words_defers_without_terminal_lines(caplog):
    """Evidence-only vad_nonfinite at assemble_words rides the ladder; no terminal line exists."""
    caplog.set_level(logging.INFO)
    shape = {"stage": "assemble_words", "reason": "vad_nonfinite"}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure_evidence=shape) is True
    guard, quar, warn = _split(caplog)
    assert not guard and not quar and not warn
    job = store.probe('jobs', 'a')
    assert job['state'] == 'retry'
    assert job['worker_failure_evidence'] == shape


def test_evidence_vad_order_at_assemble_words_defers_without_terminal_lines(caplog):
    """Evidence-only vad_order at assemble_words rides the ladder; no terminal line exists."""
    caplog.set_level(logging.INFO)
    shape = {"stage": "assemble_words", "reason": "vad_order"}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure_evidence=shape) is True
    guard, quar, warn = _split(caplog)
    assert not guard and not quar and not warn
    job = store.probe('jobs', 'a')
    assert job['state'] == 'retry'
    assert job['worker_failure_evidence'] == shape


def test_evidence_vad_bounds_at_assemble_words_defers_without_terminal_lines(caplog):
    """Evidence-only vad_bounds at assemble_words rides the ladder; no terminal line exists."""
    caplog.set_level(logging.INFO)
    shape = {"stage": "assemble_words", "reason": "vad_bounds"}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure_evidence=shape) is True
    guard, quar, warn = _split(caplog)
    assert not guard and not quar and not warn
    job = store.probe('jobs', 'a')
    assert job['state'] == 'retry'
    assert job['worker_failure_evidence'] == shape


def test_evidence_empty_asr_at_assemble_words_defers_without_terminal_lines(caplog):
    """Evidence-only empty_asr at assemble_words rides the ladder; no terminal line exists."""
    caplog.set_level(logging.INFO)
    shape = {"stage": "assemble_words", "reason": "empty_asr"}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure_evidence=shape) is True
    guard, quar, warn = _split(caplog)
    assert not guard and not quar and not warn
    job = store.probe('jobs', 'a')
    assert job['state'] == 'retry'
    assert job['worker_failure_evidence'] == shape


def test_evidence_no_owned_words_at_assemble_words_defers_without_terminal_lines(caplog):
    """Evidence-only no_owned_words at assemble_words rides the ladder; no terminal line exists."""
    caplog.set_level(logging.INFO)
    shape = {"stage": "assemble_words", "reason": "no_owned_words"}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure_evidence=shape) is True
    guard, quar, warn = _split(caplog)
    assert not guard and not quar and not warn
    job = store.probe('jobs', 'a')
    assert job['state'] == 'retry'
    assert job['worker_failure_evidence'] == shape


def test_evidence_unsupported_language_at_asr_recovery_defers_without_terminal_lines(caplog):
    """Evidence-only unsupported_language at asr_recovery rides the ladder; no terminal line exists."""
    caplog.set_level(logging.INFO)
    shape = {"stage": "asr_recovery", "reason": "unsupported_language"}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure_evidence=shape) is True
    guard, quar, warn = _split(caplog)
    assert not guard and not quar and not warn
    job = store.probe('jobs', 'a')
    assert job['state'] == 'retry'
    assert job['worker_failure_evidence'] == shape


def test_evidence_word_shape_at_asr_recovery_defers_without_terminal_lines(caplog):
    """Evidence-only word_shape at asr_recovery rides the ladder; no terminal line exists."""
    caplog.set_level(logging.INFO)
    shape = {"stage": "asr_recovery", "reason": "word_shape"}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure_evidence=shape) is True
    guard, quar, warn = _split(caplog)
    assert not guard and not quar and not warn
    job = store.probe('jobs', 'a')
    assert job['state'] == 'retry'
    assert job['worker_failure_evidence'] == shape


def test_evidence_word_clock_at_asr_recovery_defers_without_terminal_lines(caplog):
    """Evidence-only word_clock at asr_recovery rides the ladder; no terminal line exists."""
    caplog.set_level(logging.INFO)
    shape = {"stage": "asr_recovery", "reason": "word_clock"}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure_evidence=shape) is True
    guard, quar, warn = _split(caplog)
    assert not guard and not quar and not warn
    job = store.probe('jobs', 'a')
    assert job['state'] == 'retry'
    assert job['worker_failure_evidence'] == shape


def test_evidence_word_sequence_at_asr_recovery_defers_without_terminal_lines(caplog):
    """Evidence-only word_sequence at asr_recovery rides the ladder; no terminal line exists."""
    caplog.set_level(logging.INFO)
    shape = {"stage": "asr_recovery", "reason": "word_sequence"}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure_evidence=shape) is True
    guard, quar, warn = _split(caplog)
    assert not guard and not quar and not warn
    job = store.probe('jobs', 'a')
    assert job['state'] == 'retry'
    assert job['worker_failure_evidence'] == shape


def test_evidence_vad_nonfinite_at_asr_recovery_defers_without_terminal_lines(caplog):
    """Evidence-only vad_nonfinite at asr_recovery rides the ladder; no terminal line exists."""
    caplog.set_level(logging.INFO)
    shape = {"stage": "asr_recovery", "reason": "vad_nonfinite"}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure_evidence=shape) is True
    guard, quar, warn = _split(caplog)
    assert not guard and not quar and not warn
    job = store.probe('jobs', 'a')
    assert job['state'] == 'retry'
    assert job['worker_failure_evidence'] == shape


def test_evidence_vad_order_at_asr_recovery_defers_without_terminal_lines(caplog):
    """Evidence-only vad_order at asr_recovery rides the ladder; no terminal line exists."""
    caplog.set_level(logging.INFO)
    shape = {"stage": "asr_recovery", "reason": "vad_order"}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure_evidence=shape) is True
    guard, quar, warn = _split(caplog)
    assert not guard and not quar and not warn
    job = store.probe('jobs', 'a')
    assert job['state'] == 'retry'
    assert job['worker_failure_evidence'] == shape


def test_evidence_vad_bounds_at_asr_recovery_defers_without_terminal_lines(caplog):
    """Evidence-only vad_bounds at asr_recovery rides the ladder; no terminal line exists."""
    caplog.set_level(logging.INFO)
    shape = {"stage": "asr_recovery", "reason": "vad_bounds"}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure_evidence=shape) is True
    guard, quar, warn = _split(caplog)
    assert not guard and not quar and not warn
    job = store.probe('jobs', 'a')
    assert job['state'] == 'retry'
    assert job['worker_failure_evidence'] == shape


def test_evidence_empty_asr_at_asr_recovery_defers_without_terminal_lines(caplog):
    """Evidence-only empty_asr at asr_recovery rides the ladder; no terminal line exists."""
    caplog.set_level(logging.INFO)
    shape = {"stage": "asr_recovery", "reason": "empty_asr"}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure_evidence=shape) is True
    guard, quar, warn = _split(caplog)
    assert not guard and not quar and not warn
    job = store.probe('jobs', 'a')
    assert job['state'] == 'retry'
    assert job['worker_failure_evidence'] == shape


def test_evidence_no_owned_words_at_asr_recovery_defers_without_terminal_lines(caplog):
    """Evidence-only no_owned_words at asr_recovery rides the ladder; no terminal line exists."""
    caplog.set_level(logging.INFO)
    shape = {"stage": "asr_recovery", "reason": "no_owned_words"}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure_evidence=shape) is True
    guard, quar, warn = _split(caplog)
    assert not guard and not quar and not warn
    job = store.probe('jobs', 'a')
    assert job['state'] == 'retry'
    assert job['worker_failure_evidence'] == shape


def test_revoked_lease_unsupported_language_returns_false_without_lines(caplog):
    """A revoked lease transitions nothing and logs nothing."""
    caplog.set_level(logging.INFO)
    shape = {"stage": "vad_windows", "reason": "unsupported_language"}
    store, queue, lease = _queued()
    assert queue.fail(lease.item.segment_id, "wrong-token", 1100.0, worker_failure=shape) is False
    guard, quar, warn = _split(caplog)
    assert not guard and not quar and not warn


def test_revoked_lease_vad_bounds_returns_false_without_lines(caplog):
    """A revoked lease transitions nothing and logs nothing."""
    caplog.set_level(logging.INFO)
    shape = {"stage": "vad_windows", "reason": "vad_bounds"}
    store, queue, lease = _queued()
    assert queue.fail(lease.item.segment_id, "wrong-token", 1100.0, worker_failure=shape) is False
    guard, quar, warn = _split(caplog)
    assert not guard and not quar and not warn


def test_guard_terminal_keeps_correctness_and_metric_tokens(monkeypatch):
    """The redrive hold keeps its correctness and metric accounting."""
    calls = _capture_correctness(monkeypatch)
    metrics = Mock()
    store, queue, lease = _queued(metrics=metrics)
    assert _fail(queue, lease, worker_failure={"stage": "vad_windows", "reason": GUARD}) is True
    assert ('failed', 30) in calls
    metrics.record.assert_any_call("quarantined")
    metrics.record.assert_any_call("recovery_held")


def test_vad_bounds_terminal_keeps_correctness_and_metric_tokens(monkeypatch):
    """Fault terminals keep theirs."""
    calls = _capture_correctness(monkeypatch)
    metrics = Mock()
    store, queue, lease = _queued(metrics=metrics)
    assert _fail(queue, lease, worker_failure={"stage": "vad_windows", "reason": "vad_bounds"}) is True
    assert ('failed', 30) in calls
    metrics.record.assert_any_call("quarantined")
    metrics.record.assert_any_call("recovery_held")


def test_guard_defer_records_the_retry_metric():
    """Guard ladders still count as retries."""
    metrics = Mock()
    store, queue, lease = _queued(metrics=metrics)
    shape = {"stage": "vad_windows", "reason": GUARD}
    assert _fail(queue, lease, worker_failure_evidence=shape) is True
    metrics.record.assert_any_call("retry")


def test_guard_terminal_keeps_measured_vad_binding():
    """The bound VAD evidence rides the redrive hold."""
    store, queue, lease = _queued()
    shape = {"stage": "vad_windows", "reason": GUARD}
    assert _fail(queue, lease, worker_failure=shape, measured_held_vad_speech_seconds=2.0) is True
    job = store.probe('jobs', 'a')
    assert job['measured_held_vad_speech_seconds'] == 2.0


def test_guard_terminal_without_vad_binding_stays_clean():
    store, queue, lease = _queued()
    shape = {"stage": "vad_windows", "reason": GUARD}
    assert _fail(queue, lease, worker_failure=shape) is True
    job = store.probe('jobs', 'a')
    assert job.get('measured_held_vad_speech_seconds') is None


def test_guard_terminal_worker_failure_writes_no_empty_evidence():
    """A typed guard terminal is not an empty-ladder receipt: no padded evidence is written."""
    store, queue, lease = _queued()
    shape = {"stage": "vad_windows", "reason": GUARD}
    assert _fail(queue, lease, worker_failure=shape, padded_retry_empty=True) is True
    job = store.probe('jobs', 'a')
    assert 'worker_empty_evidence' not in job


def test_quarantine_lane_writes_padded_empty_evidence():
    """The empty-ladder quarantine keeps its padded evidence next to the demotion."""
    store, queue, lease = _queued()
    shape = {"stage": "assemble_words", "reason": "empty_asr"}
    assert _fail(queue, lease, quarantine=True, padded_retry_empty=True, worker_failure=shape) is True
    job = store.probe('jobs', 'a')
    assert job['worker_empty_evidence'] == {'padded_retry': 'empty', 'version': 1}


def test_invalid_padded_token_is_refused():
    """Input validation precedes any classification."""
    store, queue, lease = _queued()
    shape = {"stage": "vad_windows", "reason": GUARD}
    with pytest.raises(ValueError):
        _fail(queue, lease, worker_failure=shape, padded_retry='mystery')


def test_guard_terminal_echoes_duration_30s(monkeypatch):
    """The correctness meter sees the 30s unit."""
    calls = _capture_correctness(monkeypatch)
    store, queue, lease = _queued(duration=30)
    shape = {"stage": "vad_windows", "reason": GUARD}
    assert _fail(queue, lease, worker_failure=shape) is True
    assert ('failed', 30) in calls


def test_guard_terminal_echoes_duration_90s(monkeypatch):
    """The correctness meter sees the 90s unit."""
    calls = _capture_correctness(monkeypatch)
    store, queue, lease = _queued(duration=90)
    shape = {"stage": "vad_windows", "reason": GUARD}
    assert _fail(queue, lease, worker_failure=shape) is True
    assert ('failed', 90) in calls


def test_guard_terminal_echoes_duration_600s(monkeypatch):
    """The correctness meter sees the 600s unit."""
    calls = _capture_correctness(monkeypatch)
    store, queue, lease = _queued(duration=600)
    shape = {"stage": "vad_windows", "reason": GUARD}
    assert _fail(queue, lease, worker_failure=shape) is True
    assert ('failed', 600) in calls


def test_guard_hold_is_listed_for_recovery_and_not_for_retry():
    store, queue, lease = _queued()
    shape = {"stage": "vad_windows", "reason": GUARD}
    assert _fail(queue, lease, worker_failure=shape) is True
    assert ('jobs', 'a') in [(t, k) for (t, k), _v in store.rows.items() if t == 'jobs']
    job = store.probe('jobs', 'a')
    assert job['state'] == 'quarantined'


def test_guard_defer_stays_in_the_retry_state():
    store, queue, lease = _queued()
    shape = {"stage": "vad_windows", "reason": GUARD}
    assert _fail(queue, lease, worker_failure_evidence=shape) is True
    job = store.probe('jobs', 'a')
    assert job['state'] == 'retry'


def test_guard_evidence_defer_at_30s_stays_on_the_ladder():
    """A 30s guarded unit with evidence-only diagnosis defers with its VAD binding."""
    store, queue, lease = _queued(duration=30)
    shape = {"stage": "vad_windows", "reason": GUARD}
    assert _fail(queue, lease, worker_failure_evidence=shape, measured_held_vad_speech_seconds=1.5) is True
    job = store.probe('jobs', 'a')
    assert job['state'] == 'retry'
    assert job['measured_held_vad_speech_seconds'] == 1.5


def test_guard_evidence_defer_at_90s_stays_on_the_ladder():
    """A 90s guarded unit with evidence-only diagnosis defers with its VAD binding."""
    store, queue, lease = _queued(duration=90)
    shape = {"stage": "vad_windows", "reason": GUARD}
    assert _fail(queue, lease, worker_failure_evidence=shape, measured_held_vad_speech_seconds=1.5) is True
    job = store.probe('jobs', 'a')
    assert job['state'] == 'retry'
    assert job['measured_held_vad_speech_seconds'] == 1.5


def test_guard_evidence_defer_at_600s_stays_on_the_ladder():
    """A 600s guarded unit with evidence-only diagnosis defers with its VAD binding."""
    store, queue, lease = _queued(duration=600)
    shape = {"stage": "vad_windows", "reason": GUARD}
    assert _fail(queue, lease, worker_failure_evidence=shape, measured_held_vad_speech_seconds=1.5) is True
    job = store.probe('jobs', 'a')
    assert job['state'] == 'retry'
    assert job['measured_held_vad_speech_seconds'] == 1.5


def test_guard_hold_rides_the_scheduler_logger(caplog):
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued()
    shape = {"stage": "vad_windows", "reason": GUARD}
    _fail(queue, lease, worker_failure=shape)
    guard, quar, warn = _split(caplog)
    assert guard[0].name == "utils.batch_pipeline.scheduler"
    assert warn[0].name == "utils.batch_pipeline.scheduler"


def test_quarantine_error_rides_the_scheduler_logger(caplog):
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued()
    shape = {"stage": "vad_windows", "reason": "vad_bounds"}
    _fail(queue, lease, worker_failure=shape)
    guard, quar, warn = _split(caplog)
    assert quar[0].name == "utils.batch_pipeline.scheduler"
