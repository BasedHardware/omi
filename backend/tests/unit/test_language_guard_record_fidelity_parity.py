"""Record fidelity, storage accounting, and the remaining parity cells.

Closes the suite: token ordering on both transition records, vad-span counts at long durations, the retry metric across stages, empty-ladder padded receipts beside the fault channel, owner parity, hostile bytes tokens, fractional-duration sample echoes, and the last doc/recovery predicates.

Failure-Class: FC-language-guard-redrive-misclassified-as-worker-fault
"""

import logging
from unittest.mock import Mock

import pytest

from tests.unit.test_batch_pipeline_scheduler import MemoryStore, item as sched_item
from utils.batch_pipeline.contracts import Priority
from utils.batch_pipeline.scheduler import Scheduler
from tests.unit.test_batch_pipeline_worker import item as worker_item, setup_worker

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


def test_worker_guard_record_leads_with_the_event_token(monkeypatch, caplog):
    """The transition line opens with its event and outcome tokens."""
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'false')
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_DIARIZE_SPEECH_ONLY_ENABLED', 'false')
    monkeypatch.setenv('BATCH_PIPELINE_SHORT_SPEECH_SINGLE_ENABLED', 'false')
    caplog.set_level(logging.INFO)
    worker, words, saved, decoded, diarized, failures = setup_worker(language_of=lambda _u: "vi")
    worker.process_batch([worker_item("a", 2)])
    record = next(r for r in caplog.records if "event=batch_language_guard" in r.getMessage())
    assert record.getMessage().startswith("event=batch_language_guard outcome=redrive_held")


def test_scheduler_hold_record_leads_with_the_event_token(caplog):
    """The hold line opens with its event and outcome tokens."""
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued()
    shape = {"stage": "vad_windows", "reason": GUARD}
    assert _fail(queue, lease, worker_failure=shape) is True
    record = next(r for r in caplog.records if "event=batch_language_guard" in r.getMessage())
    assert record.getMessage().startswith("event=batch_language_guard outcome=held_for_redrive")


def test_worker_guard_2_spans_at_10s(monkeypatch, caplog):
    """2 speech spans ride the transition at 10s."""
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'false')
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_DIARIZE_SPEECH_ONLY_ENABLED', 'false')
    monkeypatch.setenv('BATCH_PIPELINE_SHORT_SPEECH_SINGLE_ENABLED', 'false')
    caplog.set_level(logging.INFO)
    worker, words, saved, decoded, diarized, failures = setup_worker(
        language_of=lambda _u: "vi",
        vad=lambda _s: [(0.1, 0.5), (0.6, 0.9)],
    )
    worker.process_batch([worker_item("a", 10)])
    record = next(r for r in caplog.records if "event=batch_language_guard" in r.getMessage())
    assert 'vad_spans=2' in record.getMessage()


def test_worker_guard_3_spans_at_30s(monkeypatch, caplog):
    """3 speech spans ride the transition at 30s."""
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'false')
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_DIARIZE_SPEECH_ONLY_ENABLED', 'false')
    monkeypatch.setenv('BATCH_PIPELINE_SHORT_SPEECH_SINGLE_ENABLED', 'false')
    caplog.set_level(logging.INFO)
    worker, words, saved, decoded, diarized, failures = setup_worker(
        language_of=lambda _u: "vi",
        vad=lambda _s: [(0.05, 10.0), (11.0, 20.0), (21.0, 29.0)],
    )
    worker.process_batch([worker_item("a", 30)])
    record = next(r for r in caplog.records if "event=batch_language_guard" in r.getMessage())
    assert 'vad_spans=3' in record.getMessage()


def test_metrics_retry_token_for_guard_defer_fetch_decode():
    """A fetch_decode guarded defer counts as a retry."""
    metrics = Mock()
    shape = {"stage": "fetch_decode", "reason": GUARD}
    store, queue, lease = _queued(metrics=metrics)
    assert _fail(queue, lease, worker_failure_evidence=shape) is True
    metrics.record.assert_any_call("retry")


def test_metrics_retry_token_for_guard_defer_vad_windows():
    """A vad_windows guarded defer counts as a retry."""
    metrics = Mock()
    shape = {"stage": "vad_windows", "reason": GUARD}
    store, queue, lease = _queued(metrics=metrics)
    assert _fail(queue, lease, worker_failure_evidence=shape) is True
    metrics.record.assert_any_call("retry")


def test_metrics_retry_token_for_guard_defer_word_clocks():
    """A word_clocks guarded defer counts as a retry."""
    metrics = Mock()
    shape = {"stage": "word_clocks", "reason": GUARD}
    store, queue, lease = _queued(metrics=metrics)
    assert _fail(queue, lease, worker_failure_evidence=shape) is True
    metrics.record.assert_any_call("retry")


def test_metrics_retry_token_for_guard_defer_assemble_words():
    """A assemble_words guarded defer counts as a retry."""
    metrics = Mock()
    shape = {"stage": "assemble_words", "reason": GUARD}
    store, queue, lease = _queued(metrics=metrics)
    assert _fail(queue, lease, worker_failure_evidence=shape) is True
    metrics.record.assert_any_call("retry")


def test_metrics_retry_token_for_guard_defer_asr_recovery():
    """A asr_recovery guarded defer counts as a retry."""
    metrics = Mock()
    shape = {"stage": "asr_recovery", "reason": GUARD}
    store, queue, lease = _queued(metrics=metrics)
    assert _fail(queue, lease, worker_failure_evidence=shape) is True
    metrics.record.assert_any_call("retry")


def test_quarantine_lane_keeps_padded_token_skipped_oversize():
    """The empty ladder keeps its skipped_oversize receipt next to the fault channel."""
    store, queue, lease = _queued()
    shape = {"stage": "assemble_words", "reason": "empty_asr"}
    assert _fail(queue, lease, quarantine=True, worker_failure=shape, padded_retry='skipped_oversize') is True
    job = store.probe('jobs', 'a')
    assert job['worker_empty_evidence']['padded_retry'] == 'skipped_oversize'


def test_quarantine_lane_keeps_padded_token_skipped_long_speech():
    """The empty ladder keeps its skipped_long_speech receipt next to the fault channel."""
    store, queue, lease = _queued()
    shape = {"stage": "assemble_words", "reason": "empty_asr"}
    assert _fail(queue, lease, quarantine=True, worker_failure=shape, padded_retry='skipped_long_speech') is True
    job = store.probe('jobs', 'a')
    assert job['worker_empty_evidence']['padded_retry'] == 'skipped_long_speech'


def test_guard_hold_for_another_owner_still_demotes(caplog):
    """Ownership does not change the classification."""
    caplog.set_level(logging.INFO)
    store, queue, lease = _queued(owner="other-owner")
    shape = {"stage": "vad_windows", "reason": GUARD}
    assert _fail(queue, lease, worker_failure=shape) is True
    guard = [r for r in caplog.records if "event=batch_language_guard" in r.getMessage()]
    assert len(guard) == 1


def test_bytes_stage_token_never_demotes():
    """Bytes tokens are not the closed string shapes."""
    assert False is __import__(
        'utils.batch_pipeline.errors', fromlist=['language_guard_redrive_failure']
    ).language_guard_redrive_failure({"stage": b"vad_windows", "reason": "unsupported_language"})


def test_bytes_reason_token_never_demotes():
    assert False is __import__(
        'utils.batch_pipeline.errors', fromlist=['language_guard_redrive_failure']
    ).language_guard_redrive_failure({"stage": "vad_windows", "reason": b"unsupported_language"})


def test_worker_guard_echoes_fractional_duration_samples(monkeypatch, caplog):
    """A 2.5s capture reports 40000 samples."""
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'false')
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_DIARIZE_SPEECH_ONLY_ENABLED', 'false')
    monkeypatch.setenv('BATCH_PIPELINE_SHORT_SPEECH_SINGLE_ENABLED', 'false')
    caplog.set_level(logging.INFO)
    worker, words, saved, decoded, diarized, failures = setup_worker(language_of=lambda _u: "vi")
    worker.process_batch([worker_item("a", 2.5)])
    record = next(r for r in caplog.records if "event=batch_language_guard" in r.getMessage())
    assert 'samples=40000' in record.getMessage()


def test_doc_names_custody_retention():
    from pathlib import Path

    doc = (Path(__file__).resolve().parents[2] / 'docs' / 'batch-language-guard-redrive-classification.md').read_text()
    assert 'custody' in doc


def test_doc_says_transition_at_least_four_times():
    from pathlib import Path

    doc = (Path(__file__).resolve().parents[2] / 'docs' / 'batch-language-guard-redrive-classification.md').read_text()
    assert doc.count('transition') >= 4


def test_independent_attempted_receipt_under_modulate_key_is_not_soniox():
    """Only the Soniox receipt proves the independent lane attempted."""
    job = {'recovery': {'recognizers': {'modulate': {'outcome': 'started'}}}}
    from config.batch_language_recovery import independent_attempted

    assert independent_attempted(job) is False


def test_words_repair_soniox_words_none_count_is_ineligible():
    from config.batch_language_recovery import words_repair_eligible

    job = {
        'worker_failure': {'stage': 'vad_windows', 'reason': 'unsupported_language'},
        'audio_uri': 'gs://bucket/a.enc',
        'duration_seconds': 30.0,
        'worker_vad_receipt': None,
        'recovery': {
            'provider': 'modulate',
            'failure': {'stage': 'payload_validation', 'reason': 'invalid_payload'},
            'recognizers': {
                'modulate': {'outcome': 'words', 'word_count': 3},
                'soniox': {'outcome': 'words', 'word_count': None},
            },
        },
    }
    assert words_repair_eligible(job) is False
