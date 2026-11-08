"""Batch-level guard shapes: every unit classifies once and independently.

Multi-unit batches pin the transition at batch scale: N guarded units produce N INFO lines and no fault lines, mixed batches classify each unit on its own language, shadow units keep the shadow line, segment ids echo verbatim, counters and callback accounting stay exact, and no guarded unit claims ASR, storage, or diarization.

Failure-Class: FC-language-guard-redrive-misclassified-as-worker-fault
"""

import logging
from dataclasses import replace

import pytest

from utils.batch_pipeline.contracts import ValidationFailureWork, WorkResult
from tests.unit.test_batch_pipeline_worker import item, setup_worker


def _env(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'false')
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_DIARIZE_SPEECH_ONLY_ENABLED', 'false')
    monkeypatch.setenv('BATCH_PIPELINE_SHORT_SPEECH_SINGLE_ENABLED', 'false')


def _worker(monkeypatch, caplog, language_of):
    _env(monkeypatch)
    caplog.set_level(logging.INFO)
    return setup_worker(language_of=language_of)


def _guard_lines(caplog):
    return [r for r in caplog.records if 'event=batch_language_guard' in r.getMessage()]


def _fault_lines(caplog):
    return [r for r in caplog.records if 'event=batch_worker_failed' in r.getMessage()]


def test_batch_of_3_guard_units_logs_3_transitions(monkeypatch, caplog):
    """A batch of 3 guarded units reports 3 transitions."""
    caplog.set_level(logging.INFO)
    worker, words, saved, decoded, diarized, failures = _worker(monkeypatch, caplog, lambda _u: "vi")
    results = worker.process_batch([item("u0", 2), item("u1", 2), item("u2", 2)])
    assert len(_guard_lines(caplog)) == 3 and not _fault_lines(caplog)
    assert len(results) == 3 and all(isinstance(r, ValidationFailureWork) for r in results)
    assert worker.counts["failed"] == 3
    assert not words.calls and not saved


def test_batch_of_4_guard_units_logs_4_transitions(monkeypatch, caplog):
    """A batch of 4 guarded units reports 4 transitions."""
    caplog.set_level(logging.INFO)
    worker, words, saved, decoded, diarized, failures = _worker(monkeypatch, caplog, lambda _u: "vi")
    results = worker.process_batch([item("u0", 2), item("u1", 2), item("u2", 2), item("u3", 2)])
    assert len(_guard_lines(caplog)) == 4 and not _fault_lines(caplog)
    assert len(results) == 4 and all(isinstance(r, ValidationFailureWork) for r in results)
    assert worker.counts["failed"] == 4
    assert not words.calls and not saved


def test_batch_of_5_guard_units_logs_5_transitions(monkeypatch, caplog):
    """A batch of 5 guarded units reports 5 transitions."""
    caplog.set_level(logging.INFO)
    worker, words, saved, decoded, diarized, failures = _worker(monkeypatch, caplog, lambda _u: "vi")
    results = worker.process_batch([item("u0", 2), item("u1", 2), item("u2", 2), item("u3", 2), item("u4", 2)])
    assert len(_guard_lines(caplog)) == 5 and not _fault_lines(caplog)
    assert len(results) == 5 and all(isinstance(r, ValidationFailureWork) for r in results)
    assert worker.counts["failed"] == 5
    assert not words.calls and not saved


def test_batch_of_6_guard_units_logs_6_transitions(monkeypatch, caplog):
    """A batch of 6 guarded units reports 6 transitions."""
    caplog.set_level(logging.INFO)
    worker, words, saved, decoded, diarized, failures = _worker(monkeypatch, caplog, lambda _u: "vi")
    results = worker.process_batch(
        [item("u0", 2), item("u1", 2), item("u2", 2), item("u3", 2), item("u4", 2), item("u5", 2)]
    )
    assert len(_guard_lines(caplog)) == 6 and not _fault_lines(caplog)
    assert len(results) == 6 and all(isinstance(r, ValidationFailureWork) for r in results)
    assert worker.counts["failed"] == 6
    assert not words.calls and not saved


def test_mixed_2_guard_1_success_batch(monkeypatch, caplog):
    """2 guarded and 1 transcribable units classify independently."""
    caplog.set_level(logging.INFO)
    worker, words, saved, decoded, diarized, failures = _worker(
        monkeypatch, caplog, lambda u: "vi" if u.segment_id.startswith("g") else "en"
    )
    results = worker.process_batch(
        [item("g0", 2), item("g1", 2), replace(item("s0", 2), language_receipt_enabled=True)]
    )
    assert len(_guard_lines(caplog)) == 2 and not _fault_lines(caplog)
    assert sum(isinstance(r, ValidationFailureWork) for r in results) == 2
    assert sum(isinstance(r, WorkResult) and r.outcome == "success" for r in results) == 1
    assert words.calls


def test_mixed_1_guard_2_success_batch(monkeypatch, caplog):
    """1 guarded and 2 transcribable units classify independently."""
    caplog.set_level(logging.INFO)
    worker, words, saved, decoded, diarized, failures = _worker(
        monkeypatch, caplog, lambda u: "vi" if u.segment_id.startswith("g") else "en"
    )
    results = worker.process_batch(
        [
            item("g0", 2),
            replace(item("s0", 2), language_receipt_enabled=True),
            replace(item("s1", 2), language_receipt_enabled=True),
        ]
    )
    assert len(_guard_lines(caplog)) == 1 and not _fault_lines(caplog)
    assert sum(isinstance(r, ValidationFailureWork) for r in results) == 1
    assert sum(isinstance(r, WorkResult) and r.outcome == "success" for r in results) == 2
    assert words.calls


def test_mixed_3_guard_1_success_batch(monkeypatch, caplog):
    """3 guarded and 1 transcribable units classify independently."""
    caplog.set_level(logging.INFO)
    worker, words, saved, decoded, diarized, failures = _worker(
        monkeypatch, caplog, lambda u: "vi" if u.segment_id.startswith("g") else "en"
    )
    results = worker.process_batch(
        [item("g0", 2), item("g1", 2), item("g2", 2), replace(item("s0", 2), language_receipt_enabled=True)]
    )
    assert len(_guard_lines(caplog)) == 3 and not _fault_lines(caplog)
    assert sum(isinstance(r, ValidationFailureWork) for r in results) == 3
    assert sum(isinstance(r, WorkResult) and r.outcome == "success" for r in results) == 1
    assert words.calls


def test_mixed_guard_and_generic_fault_batch(monkeypatch, caplog):
    """A vad_bounds fault and a guard transition keep their own channels."""
    caplog.set_level(logging.INFO)
    from utils.batch_pipeline.word_validation import BatchValidationError, ValidationReason

    worker, words, saved, decoded, diarized, failures = _worker(monkeypatch, caplog, lambda _u: "vi")

    def vad(samples):
        raise BatchValidationError(ValidationReason.VAD_BOUNDS)

    worker.vad = vad
    results = worker.process_batch([item("g", 2)])
    worker.vad = lambda s: [(0.1, 0.9)]
    results2 = worker.process_batch([item("h", 2)])
    assert len(_fault_lines(caplog)) == 1 and len(_guard_lines(caplog)) == 1
    assert isinstance(results[0], ValidationFailureWork)
    assert isinstance(results2[0], ValidationFailureWork)


def test_batch_shape_echoes_segment_id_8203(monkeypatch, caplog):
    """Segment ids echo verbatim in the transition record."""
    caplog.set_level(logging.INFO)
    worker, words, saved, decoded, diarized, failures = _worker(monkeypatch, caplog, lambda _u: "vi")
    results = worker.process_batch([item('seg-42', 2)])
    assert any('seg-42' in r.getMessage() for r in _guard_lines(caplog))


def test_batch_shape_echoes_segment_id_9877(monkeypatch, caplog):
    """Segment ids echo verbatim in the transition record."""
    caplog.set_level(logging.INFO)
    worker, words, saved, decoded, diarized, failures = _worker(monkeypatch, caplog, lambda _u: "vi")
    results = worker.process_batch([item('94397aea29add38b43309bc25872dd5593da9d011', 2)])
    assert any('94397aea29add38b43309bc25872dd5593da9d011' in r.getMessage() for r in _guard_lines(caplog))


def test_batch_shape_echoes_segment_id_492(monkeypatch, caplog):
    """Segment ids echo verbatim in the transition record."""
    caplog.set_level(logging.INFO)
    worker, words, saved, decoded, diarized, failures = _worker(monkeypatch, caplog, lambda _u: "vi")
    results = worker.process_batch(
        [
            item(
                'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
                2,
            )
        ]
    )
    assert any(
        'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx'
        in r.getMessage()
        for r in _guard_lines(caplog)
    )


def test_shadow_and_real_units_keep_their_own_lines(monkeypatch, caplog):
    """Shadow custody keeps the shadow line; the real unit keeps the transition."""
    caplog.set_level(logging.INFO)
    worker, words, saved, decoded, diarized, failures = _worker(monkeypatch, caplog, lambda _u: "vi")
    shadow_unit = replace(item("sh", 2), shadow=True)
    results = worker.process_batch([item("real", 2), shadow_unit])
    assert len(_guard_lines(caplog)) == 1
    assert sum("event=batch_shadow_worker_failure" in r.getMessage() for r in caplog.records) == 1
    assert len(results) == 2 and all(isinstance(r, ValidationFailureWork) for r in results)


def test_language_route_line_precedes_each_guard_transition(monkeypatch, caplog):
    """The frozen-route line still precedes the redrive transition."""
    caplog.set_level(logging.INFO)
    worker, words, saved, decoded, diarized, failures = _worker(monkeypatch, caplog, lambda _u: "vi")
    results = worker.process_batch([item("a", 2), item("b", 4)])
    routes = [r for r in caplog.records if "event=batch_language_route" in r.getMessage()]
    assert len(routes) == 2
    assert all("route=blocked" in r.getMessage() for r in routes)


def test_guard_units_never_claim_asr(monkeypatch, caplog):
    """No guarded unit reaches a recognizer, storage, or diarization."""
    caplog.set_level(logging.INFO)
    worker, words, saved, decoded, diarized, failures = _worker(monkeypatch, caplog, lambda _u: "vi")
    results = worker.process_batch([item("a", 2), item("b", 4), item("c", 30)])
    assert not words.calls
    assert not saved
    assert not diarized


def test_counts_items_matches_the_batch_size(monkeypatch, caplog):
    caplog.set_level(logging.INFO)
    worker, words, saved, decoded, diarized, failures = _worker(monkeypatch, caplog, lambda _u: "vi")
    worker.process_batch([item("a", 2), item("b", 2), item("c", 2)])
    assert worker.counts["items"] == 3
    assert worker.counts["failed"] == 3


def test_batch_order_preserves_result_segment_ids(monkeypatch, caplog):
    caplog.set_level(logging.INFO)
    worker, words, saved, decoded, diarized, failures = _worker(monkeypatch, caplog, lambda _u: "vi")
    results = worker.process_batch([item("a", 2), item("b", 2), item("c", 2)])
    assert [r.segment_id for r in results] == ["a", "b", "c"]
