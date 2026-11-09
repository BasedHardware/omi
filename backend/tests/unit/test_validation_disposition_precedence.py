# Failure-Class: FC-terminal-validation-disposition-misbooked-as-worker-fault
"""Diagnosis precedence through the disposition channel.

The terminal record keeps the scheduler's precedence — the current attempt's
structured worker_failure, then its evidence, then the preserved diagnosis —
and the demotion rides the same winner: a family winner reports the
disposition hold, a non-family winner keeps the quarantine ERROR, and the
sibling guard and empty-ladder families still outrank nothing they didn't
before. Every combination below is driven through a real ``Scheduler.fail``
over ``MemoryStore``.
"""

import logging
import time

from tests.unit.test_batch_pipeline_scheduler import MemoryStore, item as sched_item
from utils.batch_pipeline.contracts import Priority
from utils.batch_pipeline.scheduler import Scheduler

FAMILY_SHAPE = {'stage': 'vad_windows', 'reason': 'vad_bounds'}
OTHER_FAMILY_SHAPE = {'stage': 'word_clocks', 'reason': 'word_clock'}
FAULT_SHAPE = {'stage': 'fetch_decode', 'reason': 'outside_admitted_source'}
GUARD_SHAPE = {'stage': 'vad_windows', 'reason': 'unsupported_language'}
EMPTY_SHAPE = {'stage': 'assemble_words', 'reason': 'empty_asr'}


def _queued():
    store = MemoryStore()
    queue = Scheduler(store)
    work = sched_item("a", owner="prec-disp-owner", duration=30, priority=Priority.FRESH)
    assert queue.enqueue(work, time.time())
    lease = queue.pull(time.time())[0]
    return store, queue, lease


def _fail(queue, lease, **kwargs):
    return queue.fail(lease.item.segment_id, lease.token, time.time() + 100.0, **kwargs)


def _disposition(caplog):
    return [r for r in caplog.records if "event=batch_validation_disposition" in r.getMessage()]


def _quar(caplog):
    return [r for r in caplog.records if "event=batch_quarantined" in r.getMessage()]


def test_precedence_worker_failure_vad_bounds_beats_worker_failure_evidence_outside_admitted_source(caplog):
    """worker_failure (vad_bounds) decides the channel over worker_failure_evidence (outside_admitted_source)."""
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued()
    assert (
        _fail(
            queue,
            lease,
            **{
                "worker_failure": {'stage': 'vad_windows', 'reason': 'vad_bounds'},
                "worker_failure_evidence": {'stage': 'fetch_decode', 'reason': 'outside_admitted_source'},
            }
        )
        is True
    )
    disposition, quar = _disposition(caplog), _quar(caplog)
    guard = [r for r in caplog.records if "event=batch_language_guard" in r.getMessage()]
    ladder = [r for r in caplog.records if "event=batch_empty_ladder" in r.getMessage()]
    if "disposition" == "disposition":
        assert not quar and not guard and not ladder and len(disposition) == 1
        assert "worker_reason=vad_bounds" in disposition[0].getMessage()
    elif "disposition" == "quar":
        assert not disposition and len(quar) == 1
        assert "worker_reason=vad_bounds" in quar[0].getMessage()
    elif "disposition" == "guard":
        assert not quar and not disposition and len(guard) == 1
    else:
        assert not quar and not disposition and len(ladder) == 1


def test_precedence_worker_failure_outside_admitted_source_beats_worker_failure_evidence_vad_bounds(caplog):
    """worker_failure (outside_admitted_source) decides the channel over worker_failure_evidence (vad_bounds)."""
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued()
    assert (
        _fail(
            queue,
            lease,
            **{
                "worker_failure": {'stage': 'fetch_decode', 'reason': 'outside_admitted_source'},
                "worker_failure_evidence": {'stage': 'vad_windows', 'reason': 'vad_bounds'},
            }
        )
        is True
    )
    disposition, quar = _disposition(caplog), _quar(caplog)
    guard = [r for r in caplog.records if "event=batch_language_guard" in r.getMessage()]
    ladder = [r for r in caplog.records if "event=batch_empty_ladder" in r.getMessage()]
    if "quar" == "disposition":
        assert not quar and not guard and not ladder and len(disposition) == 1
        assert "worker_reason=outside_admitted_source" in disposition[0].getMessage()
    elif "quar" == "quar":
        assert not disposition and len(quar) == 1
        assert "worker_reason=outside_admitted_source" in quar[0].getMessage()
    elif "quar" == "guard":
        assert not quar and not disposition and len(guard) == 1
    else:
        assert not quar and not disposition and len(ladder) == 1


def test_precedence_worker_failure_vad_bounds_beats_worker_failure_evidence_word_clock(caplog):
    """worker_failure (vad_bounds) decides the channel over worker_failure_evidence (word_clock)."""
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued()
    assert (
        _fail(
            queue,
            lease,
            **{
                "worker_failure": {'stage': 'vad_windows', 'reason': 'vad_bounds'},
                "worker_failure_evidence": {'stage': 'word_clocks', 'reason': 'word_clock'},
            }
        )
        is True
    )
    disposition, quar = _disposition(caplog), _quar(caplog)
    guard = [r for r in caplog.records if "event=batch_language_guard" in r.getMessage()]
    ladder = [r for r in caplog.records if "event=batch_empty_ladder" in r.getMessage()]
    if "disposition" == "disposition":
        assert not quar and not guard and not ladder and len(disposition) == 1
        assert "worker_reason=vad_bounds" in disposition[0].getMessage()
    elif "disposition" == "quar":
        assert not disposition and len(quar) == 1
        assert "worker_reason=vad_bounds" in quar[0].getMessage()
    elif "disposition" == "guard":
        assert not quar and not disposition and len(guard) == 1
    else:
        assert not quar and not disposition and len(ladder) == 1


def test_precedence_worker_failure_word_clock_beats_worker_failure_evidence_vad_bounds(caplog):
    """worker_failure (word_clock) decides the channel over worker_failure_evidence (vad_bounds)."""
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued()
    assert (
        _fail(
            queue,
            lease,
            **{
                "worker_failure": {'stage': 'word_clocks', 'reason': 'word_clock'},
                "worker_failure_evidence": {'stage': 'vad_windows', 'reason': 'vad_bounds'},
            }
        )
        is True
    )
    disposition, quar = _disposition(caplog), _quar(caplog)
    guard = [r for r in caplog.records if "event=batch_language_guard" in r.getMessage()]
    ladder = [r for r in caplog.records if "event=batch_empty_ladder" in r.getMessage()]
    if "disposition" == "disposition":
        assert not quar and not guard and not ladder and len(disposition) == 1
        assert "worker_reason=word_clock" in disposition[0].getMessage()
    elif "disposition" == "quar":
        assert not disposition and len(quar) == 1
        assert "worker_reason=word_clock" in quar[0].getMessage()
    elif "disposition" == "guard":
        assert not quar and not disposition and len(guard) == 1
    else:
        assert not quar and not disposition and len(ladder) == 1


def test_precedence_worker_failure_unsupported_language_beats_worker_failure_evidence_vad_bounds_guards(caplog):
    """worker_failure (unsupported_language) decides the channel over worker_failure_evidence (vad_bounds)."""
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued()
    assert (
        _fail(
            queue,
            lease,
            **{
                "worker_failure": {'stage': 'vad_windows', 'reason': 'unsupported_language'},
                "worker_failure_evidence": {'stage': 'vad_windows', 'reason': 'vad_bounds'},
            }
        )
        is True
    )
    disposition, quar = _disposition(caplog), _quar(caplog)
    guard = [r for r in caplog.records if "event=batch_language_guard" in r.getMessage()]
    ladder = [r for r in caplog.records if "event=batch_empty_ladder" in r.getMessage()]
    if "guard" == "disposition":
        assert not quar and not guard and not ladder and len(disposition) == 1
        assert "worker_reason=unsupported_language" in disposition[0].getMessage()
    elif "guard" == "quar":
        assert not disposition and len(quar) == 1
        assert "worker_reason=unsupported_language" in quar[0].getMessage()
    elif "guard" == "guard":
        assert not quar and not disposition and len(guard) == 1
    else:
        assert not quar and not disposition and len(ladder) == 1


def test_precedence_worker_failure_empty_asr_beats_worker_failure_evidence_vad_bounds_ladder(caplog):
    """worker_failure (empty_asr) decides the channel over worker_failure_evidence (vad_bounds)."""
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued()
    assert (
        _fail(
            queue,
            lease,
            **{
                "worker_failure": {'stage': 'assemble_words', 'reason': 'empty_asr'},
                "worker_failure_evidence": {'stage': 'vad_windows', 'reason': 'vad_bounds'},
            }
        )
        is True
    )
    disposition, quar = _disposition(caplog), _quar(caplog)
    guard = [r for r in caplog.records if "event=batch_language_guard" in r.getMessage()]
    ladder = [r for r in caplog.records if "event=batch_empty_ladder" in r.getMessage()]
    if "ladder" == "disposition":
        assert not quar and not guard and not ladder and len(disposition) == 1
        assert "worker_reason=empty_asr" in disposition[0].getMessage()
    elif "ladder" == "quar":
        assert not disposition and len(quar) == 1
        assert "worker_reason=empty_asr" in quar[0].getMessage()
    elif "ladder" == "guard":
        assert not quar and not disposition and len(guard) == 1
    else:
        assert not quar and not disposition and len(ladder) == 1


def test_precedence_worker_failure_vad_bounds_beats_worker_failure_evidence_unsupported_language(caplog):
    """worker_failure (vad_bounds) decides the channel over worker_failure_evidence (unsupported_language)."""
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued()
    assert (
        _fail(
            queue,
            lease,
            **{
                "worker_failure": {'stage': 'vad_windows', 'reason': 'vad_bounds'},
                "worker_failure_evidence": {'stage': 'vad_windows', 'reason': 'unsupported_language'},
            }
        )
        is True
    )
    disposition, quar = _disposition(caplog), _quar(caplog)
    guard = [r for r in caplog.records if "event=batch_language_guard" in r.getMessage()]
    ladder = [r for r in caplog.records if "event=batch_empty_ladder" in r.getMessage()]
    if "disposition" == "disposition":
        assert not quar and not guard and not ladder and len(disposition) == 1
        assert "worker_reason=vad_bounds" in disposition[0].getMessage()
    elif "disposition" == "quar":
        assert not disposition and len(quar) == 1
        assert "worker_reason=vad_bounds" in quar[0].getMessage()
    elif "disposition" == "guard":
        assert not quar and not disposition and len(guard) == 1
    else:
        assert not quar and not disposition and len(ladder) == 1


def test_precedence_worker_failure_vad_bounds_beats_worker_failure_evidence_empty_asr(caplog):
    """worker_failure (vad_bounds) decides the channel over worker_failure_evidence (empty_asr)."""
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued()
    assert (
        _fail(
            queue,
            lease,
            **{
                "worker_failure": {'stage': 'vad_windows', 'reason': 'vad_bounds'},
                "worker_failure_evidence": {'stage': 'assemble_words', 'reason': 'empty_asr'},
            }
        )
        is True
    )
    disposition, quar = _disposition(caplog), _quar(caplog)
    guard = [r for r in caplog.records if "event=batch_language_guard" in r.getMessage()]
    ladder = [r for r in caplog.records if "event=batch_empty_ladder" in r.getMessage()]
    if "disposition" == "disposition":
        assert not quar and not guard and not ladder and len(disposition) == 1
        assert "worker_reason=vad_bounds" in disposition[0].getMessage()
    elif "disposition" == "quar":
        assert not disposition and len(quar) == 1
        assert "worker_reason=vad_bounds" in quar[0].getMessage()
    elif "disposition" == "guard":
        assert not quar and not disposition and len(guard) == 1
    else:
        assert not quar and not disposition and len(ladder) == 1
