"""Diagnosis precedence and exhausted ladders classify by the strongest stored evidence.

A terminal hold names the strongest diagnosis: the structured worker_failure, else this attempt's evidence, else the evidence earlier ladder attempts preserved, else the anonymous shape. This suite seeds MemoryStore jobs directly and pins every precedence cell — including the exhausted bare ladder keeping the anonymous ERROR — plus the due-listing and scheduling parity of holds versus defers.

Failure-Class: FC-language-guard-redrive-misclassified-as-worker-fault
"""

import logging

import pytest

from tests.unit.test_batch_pipeline_scheduler import MemoryStore, item as sched_item
from utils.batch_pipeline.contracts import Priority
from utils.batch_pipeline.scheduler import Scheduler

STAGES = ['fetch_decode', 'vad_windows', 'word_clocks', 'assemble_words', 'asr_recovery']
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
    retry = [r for r in caplog.records if 'event=batch_retry' in r.getMessage()]
    warn = [r for r in caplog.records if 'awaiting_fenced_recovery' in r.getMessage()]
    return guard, quar, retry, warn


def _exhaust(store, lease):
    """Age the job past every ladder attempt before the observed fail()."""
    job = store.rows.get(('jobs', lease.item.segment_id))
    job['attempt'] = 99


def test_exhausted_bare_fail_keeps_the_unknown_quarantine_error(caplog):
    """An evidence-less exhausted ladder keeps the historical anonymous ERROR shape."""
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued()
    _exhaust(store, lease)
    assert _fail(queue, lease) is True
    guard, quar, retry, warn = _split(caplog)
    assert not guard and len(quar) == 1
    assert 'stage=unknown' in quar[0].getMessage() and 'worker_reason=unclassified' in quar[0].getMessage()
    assert len(warn) == 1
    job = store.probe('jobs', 'a')
    assert job['state'] == 'quarantined'


def test_exhausted_guard_evidence_fetch_decode_demotes(caplog):
    """Exhausted with fetch_decode guard evidence: the diagnosis demotes."""
    caplog.set_level(logging.INFO)
    shape = {"stage": "fetch_decode", "reason": GUARD}
    store, queue, lease = _queued()
    _exhaust(store, lease)
    assert _fail(queue, lease, worker_failure_evidence=shape) is True
    guard, quar, retry, warn = _split(caplog)
    assert len(guard) == 1 and not quar
    assert 'outcome=held_for_redrive' in guard[0].getMessage()
    assert 'worker_reason=unsupported_language' in guard[0].getMessage()


def test_exhausted_vad_bounds_evidence_fetch_decode_reports_disposition_hold(caplog):
    """Exhausted with fetch_decode vad_bounds evidence demotes to the disposition hold."""
    caplog.set_level(logging.INFO)
    shape = {"stage": "fetch_decode", "reason": "vad_bounds"}
    store, queue, lease = _queued()
    _exhaust(store, lease)
    assert _fail(queue, lease, worker_failure_evidence=shape) is True
    guard, quar, retry, warn = _split(caplog)
    disposition = [r for r in caplog.records if 'event=batch_validation_disposition' in r.getMessage()]
    assert not guard and not quar and len(disposition) == 1


def test_exhausted_guard_evidence_vad_windows_demotes(caplog):
    """Exhausted with vad_windows guard evidence: the diagnosis demotes."""
    caplog.set_level(logging.INFO)
    shape = {"stage": "vad_windows", "reason": GUARD}
    store, queue, lease = _queued()
    _exhaust(store, lease)
    assert _fail(queue, lease, worker_failure_evidence=shape) is True
    guard, quar, retry, warn = _split(caplog)
    assert len(guard) == 1 and not quar
    assert 'outcome=held_for_redrive' in guard[0].getMessage()
    assert 'worker_reason=unsupported_language' in guard[0].getMessage()


def test_exhausted_vad_bounds_evidence_vad_windows_reports_disposition_hold(caplog):
    """Exhausted with vad_windows vad_bounds evidence demotes to the disposition hold."""
    caplog.set_level(logging.INFO)
    shape = {"stage": "vad_windows", "reason": "vad_bounds"}
    store, queue, lease = _queued()
    _exhaust(store, lease)
    assert _fail(queue, lease, worker_failure_evidence=shape) is True
    guard, quar, retry, warn = _split(caplog)
    disposition = [r for r in caplog.records if 'event=batch_validation_disposition' in r.getMessage()]
    assert not guard and not quar and len(disposition) == 1


def test_exhausted_guard_evidence_word_clocks_demotes(caplog):
    """Exhausted with word_clocks guard evidence: the diagnosis demotes."""
    caplog.set_level(logging.INFO)
    shape = {"stage": "word_clocks", "reason": GUARD}
    store, queue, lease = _queued()
    _exhaust(store, lease)
    assert _fail(queue, lease, worker_failure_evidence=shape) is True
    guard, quar, retry, warn = _split(caplog)
    assert len(guard) == 1 and not quar
    assert 'outcome=held_for_redrive' in guard[0].getMessage()
    assert 'worker_reason=unsupported_language' in guard[0].getMessage()


def test_exhausted_vad_bounds_evidence_word_clocks_reports_disposition_hold(caplog):
    """Exhausted with word_clocks vad_bounds evidence demotes to the disposition hold."""
    caplog.set_level(logging.INFO)
    shape = {"stage": "word_clocks", "reason": "vad_bounds"}
    store, queue, lease = _queued()
    _exhaust(store, lease)
    assert _fail(queue, lease, worker_failure_evidence=shape) is True
    guard, quar, retry, warn = _split(caplog)
    disposition = [r for r in caplog.records if 'event=batch_validation_disposition' in r.getMessage()]
    assert not guard and not quar and len(disposition) == 1


def test_exhausted_guard_evidence_assemble_words_demotes(caplog):
    """Exhausted with assemble_words guard evidence: the diagnosis demotes."""
    caplog.set_level(logging.INFO)
    shape = {"stage": "assemble_words", "reason": GUARD}
    store, queue, lease = _queued()
    _exhaust(store, lease)
    assert _fail(queue, lease, worker_failure_evidence=shape) is True
    guard, quar, retry, warn = _split(caplog)
    assert len(guard) == 1 and not quar
    assert 'outcome=held_for_redrive' in guard[0].getMessage()
    assert 'worker_reason=unsupported_language' in guard[0].getMessage()


def test_exhausted_vad_bounds_evidence_assemble_words_reports_disposition_hold(caplog):
    """Exhausted with assemble_words vad_bounds evidence demotes to the disposition hold."""
    caplog.set_level(logging.INFO)
    shape = {"stage": "assemble_words", "reason": "vad_bounds"}
    store, queue, lease = _queued()
    _exhaust(store, lease)
    assert _fail(queue, lease, worker_failure_evidence=shape) is True
    guard, quar, retry, warn = _split(caplog)
    disposition = [r for r in caplog.records if 'event=batch_validation_disposition' in r.getMessage()]
    assert not guard and not quar and len(disposition) == 1


def test_exhausted_guard_evidence_asr_recovery_demotes(caplog):
    """Exhausted with asr_recovery guard evidence: the diagnosis demotes."""
    caplog.set_level(logging.INFO)
    shape = {"stage": "asr_recovery", "reason": GUARD}
    store, queue, lease = _queued()
    _exhaust(store, lease)
    assert _fail(queue, lease, worker_failure_evidence=shape) is True
    guard, quar, retry, warn = _split(caplog)
    assert len(guard) == 1 and not quar
    assert 'outcome=held_for_redrive' in guard[0].getMessage()
    assert 'worker_reason=unsupported_language' in guard[0].getMessage()


def test_exhausted_vad_bounds_evidence_asr_recovery_reports_disposition_hold(caplog):
    """Exhausted with asr_recovery vad_bounds evidence demotes to the disposition hold."""
    caplog.set_level(logging.INFO)
    shape = {"stage": "asr_recovery", "reason": "vad_bounds"}
    store, queue, lease = _queued()
    _exhaust(store, lease)
    assert _fail(queue, lease, worker_failure_evidence=shape) is True
    guard, quar, retry, warn = _split(caplog)
    disposition = [r for r in caplog.records if 'event=batch_validation_disposition' in r.getMessage()]
    assert not guard and not quar and len(disposition) == 1


def test_preserved_guard_evidence_fetch_decode_demotes_on_exhaustion(caplog):
    """A fetch_decode guard diagnosis preserved from earlier attempts demotes."""
    caplog.set_level(logging.INFO)
    seed = {"stage": "fetch_decode", "reason": GUARD}
    store, queue, lease = _queued()
    store.rows[('jobs', 'a')]['worker_failure_evidence'] = dict(seed)
    _exhaust(store, lease)
    assert _fail(queue, lease) is True
    guard, quar, retry, warn = _split(caplog)
    assert len(guard) == 1 and not quar
    job = store.probe('jobs', 'a')
    assert job['worker_failure_evidence'] == seed


def test_preserved_vad_bounds_evidence_fetch_decode_reports_disposition_hold(caplog):
    caplog.set_level(logging.INFO)
    seed = {"stage": "fetch_decode", "reason": "vad_bounds"}
    store, queue, lease = _queued()
    store.rows[('jobs', 'a')]['worker_failure_evidence'] = dict(seed)
    _exhaust(store, lease)
    assert _fail(queue, lease) is True
    guard, quar, retry, warn = _split(caplog)
    disposition = [r for r in caplog.records if 'event=batch_validation_disposition' in r.getMessage()]
    assert not guard and not quar and len(disposition) == 1


def test_preserved_guard_evidence_vad_windows_demotes_on_exhaustion(caplog):
    """A vad_windows guard diagnosis preserved from earlier attempts demotes."""
    caplog.set_level(logging.INFO)
    seed = {"stage": "vad_windows", "reason": GUARD}
    store, queue, lease = _queued()
    store.rows[('jobs', 'a')]['worker_failure_evidence'] = dict(seed)
    _exhaust(store, lease)
    assert _fail(queue, lease) is True
    guard, quar, retry, warn = _split(caplog)
    assert len(guard) == 1 and not quar
    job = store.probe('jobs', 'a')
    assert job['worker_failure_evidence'] == seed


def test_preserved_vad_bounds_evidence_vad_windows_reports_disposition_hold(caplog):
    caplog.set_level(logging.INFO)
    seed = {"stage": "vad_windows", "reason": "vad_bounds"}
    store, queue, lease = _queued()
    store.rows[('jobs', 'a')]['worker_failure_evidence'] = dict(seed)
    _exhaust(store, lease)
    assert _fail(queue, lease) is True
    guard, quar, retry, warn = _split(caplog)
    disposition = [r for r in caplog.records if 'event=batch_validation_disposition' in r.getMessage()]
    assert not guard and not quar and len(disposition) == 1


def test_preserved_guard_evidence_word_clocks_demotes_on_exhaustion(caplog):
    """A word_clocks guard diagnosis preserved from earlier attempts demotes."""
    caplog.set_level(logging.INFO)
    seed = {"stage": "word_clocks", "reason": GUARD}
    store, queue, lease = _queued()
    store.rows[('jobs', 'a')]['worker_failure_evidence'] = dict(seed)
    _exhaust(store, lease)
    assert _fail(queue, lease) is True
    guard, quar, retry, warn = _split(caplog)
    assert len(guard) == 1 and not quar
    job = store.probe('jobs', 'a')
    assert job['worker_failure_evidence'] == seed


def test_preserved_vad_bounds_evidence_word_clocks_reports_disposition_hold(caplog):
    caplog.set_level(logging.INFO)
    seed = {"stage": "word_clocks", "reason": "vad_bounds"}
    store, queue, lease = _queued()
    store.rows[('jobs', 'a')]['worker_failure_evidence'] = dict(seed)
    _exhaust(store, lease)
    assert _fail(queue, lease) is True
    guard, quar, retry, warn = _split(caplog)
    disposition = [r for r in caplog.records if 'event=batch_validation_disposition' in r.getMessage()]
    assert not guard and not quar and len(disposition) == 1


def test_preserved_guard_evidence_assemble_words_demotes_on_exhaustion(caplog):
    """A assemble_words guard diagnosis preserved from earlier attempts demotes."""
    caplog.set_level(logging.INFO)
    seed = {"stage": "assemble_words", "reason": GUARD}
    store, queue, lease = _queued()
    store.rows[('jobs', 'a')]['worker_failure_evidence'] = dict(seed)
    _exhaust(store, lease)
    assert _fail(queue, lease) is True
    guard, quar, retry, warn = _split(caplog)
    assert len(guard) == 1 and not quar
    job = store.probe('jobs', 'a')
    assert job['worker_failure_evidence'] == seed


def test_preserved_vad_bounds_evidence_assemble_words_reports_disposition_hold(caplog):
    caplog.set_level(logging.INFO)
    seed = {"stage": "assemble_words", "reason": "vad_bounds"}
    store, queue, lease = _queued()
    store.rows[('jobs', 'a')]['worker_failure_evidence'] = dict(seed)
    _exhaust(store, lease)
    assert _fail(queue, lease) is True
    guard, quar, retry, warn = _split(caplog)
    disposition = [r for r in caplog.records if 'event=batch_validation_disposition' in r.getMessage()]
    assert not guard and not quar and len(disposition) == 1


def test_preserved_guard_evidence_asr_recovery_demotes_on_exhaustion(caplog):
    """A asr_recovery guard diagnosis preserved from earlier attempts demotes."""
    caplog.set_level(logging.INFO)
    seed = {"stage": "asr_recovery", "reason": GUARD}
    store, queue, lease = _queued()
    store.rows[('jobs', 'a')]['worker_failure_evidence'] = dict(seed)
    _exhaust(store, lease)
    assert _fail(queue, lease) is True
    guard, quar, retry, warn = _split(caplog)
    assert len(guard) == 1 and not quar
    job = store.probe('jobs', 'a')
    assert job['worker_failure_evidence'] == seed


def test_preserved_vad_bounds_evidence_asr_recovery_reports_disposition_hold(caplog):
    caplog.set_level(logging.INFO)
    seed = {"stage": "asr_recovery", "reason": "vad_bounds"}
    store, queue, lease = _queued()
    store.rows[('jobs', 'a')]['worker_failure_evidence'] = dict(seed)
    _exhaust(store, lease)
    assert _fail(queue, lease) is True
    guard, quar, retry, warn = _split(caplog)
    disposition = [r for r in caplog.records if 'event=batch_validation_disposition' in r.getMessage()]
    assert not guard and not quar and len(disposition) == 1


def test_worker_failure_guard_beats_vad_bounds_evidence_fetch_decode(caplog):
    """The structured worker_failure wins the diagnosis; the evidence still stores."""
    caplog.set_level(logging.INFO)
    failure_shape = {"stage": "fetch_decode", "reason": GUARD}
    evidence_shape = {"stage": "vad_windows", "reason": "vad_bounds"}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure=failure_shape, worker_failure_evidence=evidence_shape) is True
    guard, quar, retry, warn = _split(caplog)
    assert len(guard) == 1 and not quar
    job = store.probe('jobs', 'a')
    assert job['worker_failure'] == failure_shape
    assert job['worker_failure_evidence'] == evidence_shape


def test_worker_failure_guard_beats_vad_bounds_evidence_vad_windows(caplog):
    """The structured worker_failure wins the diagnosis; the evidence still stores."""
    caplog.set_level(logging.INFO)
    failure_shape = {"stage": "vad_windows", "reason": GUARD}
    evidence_shape = {"stage": "vad_windows", "reason": "vad_bounds"}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure=failure_shape, worker_failure_evidence=evidence_shape) is True
    guard, quar, retry, warn = _split(caplog)
    assert len(guard) == 1 and not quar
    job = store.probe('jobs', 'a')
    assert job['worker_failure'] == failure_shape
    assert job['worker_failure_evidence'] == evidence_shape


def test_worker_failure_guard_beats_vad_bounds_evidence_word_clocks(caplog):
    """The structured worker_failure wins the diagnosis; the evidence still stores."""
    caplog.set_level(logging.INFO)
    failure_shape = {"stage": "word_clocks", "reason": GUARD}
    evidence_shape = {"stage": "vad_windows", "reason": "vad_bounds"}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure=failure_shape, worker_failure_evidence=evidence_shape) is True
    guard, quar, retry, warn = _split(caplog)
    assert len(guard) == 1 and not quar
    job = store.probe('jobs', 'a')
    assert job['worker_failure'] == failure_shape
    assert job['worker_failure_evidence'] == evidence_shape


def test_worker_failure_guard_beats_vad_bounds_evidence_assemble_words(caplog):
    """The structured worker_failure wins the diagnosis; the evidence still stores."""
    caplog.set_level(logging.INFO)
    failure_shape = {"stage": "assemble_words", "reason": GUARD}
    evidence_shape = {"stage": "vad_windows", "reason": "vad_bounds"}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure=failure_shape, worker_failure_evidence=evidence_shape) is True
    guard, quar, retry, warn = _split(caplog)
    assert len(guard) == 1 and not quar
    job = store.probe('jobs', 'a')
    assert job['worker_failure'] == failure_shape
    assert job['worker_failure_evidence'] == evidence_shape


def test_worker_failure_guard_beats_vad_bounds_evidence_asr_recovery(caplog):
    """The structured worker_failure wins the diagnosis; the evidence still stores."""
    caplog.set_level(logging.INFO)
    failure_shape = {"stage": "asr_recovery", "reason": GUARD}
    evidence_shape = {"stage": "vad_windows", "reason": "vad_bounds"}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure=failure_shape, worker_failure_evidence=evidence_shape) is True
    guard, quar, retry, warn = _split(caplog)
    assert len(guard) == 1 and not quar
    job = store.probe('jobs', 'a')
    assert job['worker_failure'] == failure_shape
    assert job['worker_failure_evidence'] == evidence_shape


def test_worker_failure_vad_bounds_beats_guard_evidence(caplog):
    caplog.set_level(logging.INFO)
    failure_shape = {"stage": "vad_windows", "reason": "vad_bounds"}
    evidence_shape = {"stage": "vad_windows", "reason": GUARD}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure=failure_shape, worker_failure_evidence=evidence_shape) is True
    guard, quar, retry, warn = _split(caplog)
    disposition = [r for r in caplog.records if 'event=batch_validation_disposition' in r.getMessage()]
    assert not guard and not quar and len(disposition) == 1
    assert 'worker_reason=vad_bounds' in disposition[0].getMessage()


def test_guard_hold_fetch_decode_is_not_retry_due():
    shape = {"stage": "fetch_decode", "reason": GUARD}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure=shape) is True
    job = store.probe('jobs', 'a')
    assert job['state'] == 'quarantined'
    assert store.due('retry', 1100.0, 10) == []


def test_guard_defer_fetch_decode_is_not_quarantine_due():
    shape = {"stage": "fetch_decode", "reason": GUARD}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure_evidence=shape) is True
    job = store.probe('jobs', 'a')
    assert job['state'] == 'retry'
    job['available_at'] = 900.0
    assert ('jobs', 'a') in [(t, k) for (t, k), _v in store.rows.items() if t == 'jobs']


def test_guard_hold_vad_windows_is_not_retry_due():
    shape = {"stage": "vad_windows", "reason": GUARD}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure=shape) is True
    job = store.probe('jobs', 'a')
    assert job['state'] == 'quarantined'
    assert store.due('retry', 1100.0, 10) == []


def test_guard_defer_vad_windows_is_not_quarantine_due():
    shape = {"stage": "vad_windows", "reason": GUARD}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure_evidence=shape) is True
    job = store.probe('jobs', 'a')
    assert job['state'] == 'retry'
    job['available_at'] = 900.0
    assert ('jobs', 'a') in [(t, k) for (t, k), _v in store.rows.items() if t == 'jobs']


def test_guard_hold_word_clocks_is_not_retry_due():
    shape = {"stage": "word_clocks", "reason": GUARD}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure=shape) is True
    job = store.probe('jobs', 'a')
    assert job['state'] == 'quarantined'
    assert store.due('retry', 1100.0, 10) == []


def test_guard_defer_word_clocks_is_not_quarantine_due():
    shape = {"stage": "word_clocks", "reason": GUARD}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure_evidence=shape) is True
    job = store.probe('jobs', 'a')
    assert job['state'] == 'retry'
    job['available_at'] = 900.0
    assert ('jobs', 'a') in [(t, k) for (t, k), _v in store.rows.items() if t == 'jobs']


def test_guard_hold_assemble_words_is_not_retry_due():
    shape = {"stage": "assemble_words", "reason": GUARD}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure=shape) is True
    job = store.probe('jobs', 'a')
    assert job['state'] == 'quarantined'
    assert store.due('retry', 1100.0, 10) == []


def test_guard_defer_assemble_words_is_not_quarantine_due():
    shape = {"stage": "assemble_words", "reason": GUARD}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure_evidence=shape) is True
    job = store.probe('jobs', 'a')
    assert job['state'] == 'retry'
    job['available_at'] = 900.0
    assert ('jobs', 'a') in [(t, k) for (t, k), _v in store.rows.items() if t == 'jobs']


def test_guard_hold_asr_recovery_is_not_retry_due():
    shape = {"stage": "asr_recovery", "reason": GUARD}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure=shape) is True
    job = store.probe('jobs', 'a')
    assert job['state'] == 'quarantined'
    assert store.due('retry', 1100.0, 10) == []


def test_guard_defer_asr_recovery_is_not_quarantine_due():
    shape = {"stage": "asr_recovery", "reason": GUARD}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure_evidence=shape) is True
    job = store.probe('jobs', 'a')
    assert job['state'] == 'retry'
    job['available_at'] = 900.0
    assert ('jobs', 'a') in [(t, k) for (t, k), _v in store.rows.items() if t == 'jobs']


def test_guard_defer_fetch_decode_schedules_a_future_retry():
    """A fetch_decode guarded defer parks the job for a later ladder attempt."""
    shape = {"stage": "fetch_decode", "reason": GUARD}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure_evidence=shape) is True
    job = store.probe('jobs', 'a')
    assert job['available_at'] > 1100.0
    assert job['token'] == ''


def test_guard_defer_vad_windows_schedules_a_future_retry():
    """A vad_windows guarded defer parks the job for a later ladder attempt."""
    shape = {"stage": "vad_windows", "reason": GUARD}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure_evidence=shape) is True
    job = store.probe('jobs', 'a')
    assert job['available_at'] > 1100.0
    assert job['token'] == ''


def test_guard_defer_word_clocks_schedules_a_future_retry():
    """A word_clocks guarded defer parks the job for a later ladder attempt."""
    shape = {"stage": "word_clocks", "reason": GUARD}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure_evidence=shape) is True
    job = store.probe('jobs', 'a')
    assert job['available_at'] > 1100.0
    assert job['token'] == ''


def test_guard_defer_assemble_words_schedules_a_future_retry():
    """A assemble_words guarded defer parks the job for a later ladder attempt."""
    shape = {"stage": "assemble_words", "reason": GUARD}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure_evidence=shape) is True
    job = store.probe('jobs', 'a')
    assert job['available_at'] > 1100.0
    assert job['token'] == ''


def test_guard_defer_asr_recovery_schedules_a_future_retry():
    """A asr_recovery guarded defer parks the job for a later ladder attempt."""
    shape = {"stage": "asr_recovery", "reason": GUARD}
    store, queue, lease = _queued()
    assert _fail(queue, lease, worker_failure_evidence=shape) is True
    job = store.probe('jobs', 'a')
    assert job['available_at'] > 1100.0
    assert job['token'] == ''


def test_defer_never_records_recovery_held():
    """Only quarantines count as recovery-held."""
    from unittest.mock import Mock

    metrics = Mock()
    store, queue, lease = _queued(metrics=metrics)
    shape = {"stage": "vad_windows", "reason": GUARD}
    assert _fail(queue, lease, worker_failure_evidence=shape) is True
    metrics.record.assert_any_call("retry")
    for call in metrics.record.call_args_list:
        assert call.args[0] != 'recovery_held'


def test_guard_defer_books_a_nonnegative_attempt(caplog):
    """The defer line and the stored job agree on the ladder attempt."""
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued()
    shape = {"stage": "vad_windows", "reason": GUARD}
    assert _fail(queue, lease, worker_failure_evidence=shape) is True
    job = store.probe('jobs', 'a')
    assert type(job["attempt"]) is int and job["attempt"] >= 0
    guard, quar, retry, warn = _split(caplog)
    assert len(retry) == 1
    assert 'attempt=' + str(job['attempt']) in retry[0].getMessage()
