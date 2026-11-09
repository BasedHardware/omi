# Failure-Class: FC-terminal-validation-disposition-misbooked-as-worker-fault
"""The exhausting ladder names its preserved diagnosis on the right channel, cell-by-cell.

Every diagnosis the evidence validator admits is seeded on the job, the
bounded ladder runs bare until it quarantines, and the terminal line names the
preserved diagnosis on the channel the demotion (or its sibling demotions, or
the kept faults) dictate — with the switch on. The exhausting attempt arrives
evidence-less in every cell, so the naming always comes from the preserved
record, and the latest evidence beats earlier evidence when several attempts
carried one.
"""

import logging
import time

from tests.unit.test_batch_pipeline_scheduler import MemoryStore, item as sched_item
from utils.batch_pipeline.contracts import Priority
from utils.batch_pipeline.scheduler import Scheduler

STAGES = ('fetch_decode', 'vad_windows', 'word_clocks', 'assemble_words', 'asr_recovery')
ALL_REASONS = (
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
TRIO = ("staged_audio_invalid", "retained_audio_invalid", "decoded_duration_mismatch")
FLAGGED = ("word_shape", "word_clock", "word_sequence", "vad_nonfinite", "vad_order", "vad_bounds")


def _queued_for_walk():
    store = MemoryStore()
    queue = Scheduler(store)
    work = sched_item("a", owner="walk-grid-owner", duration=30, priority=Priority.FRESH)
    assert queue.enqueue(work, time.time())
    return store, queue


def _walk(queue, store, evidence_plan=None):
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


def _event(caplog, event):
    lines = [r.getMessage() for r in caplog.records if event in r.getMessage()]
    assert len(lines) == 1
    return lines[0]


def test_walk_fetch_decode_staged_audio_invalid_preserved_diagnosis_names_the_disposition_channel(monkeypatch, caplog):
    """A bare-exhausting ladder over seeded (fetch_decode, staged_audio_invalid) evidence reports disposition."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue = _queued_for_walk()
    store.rows["jobs", "a"]["worker_failure_evidence"] = {"stage": "fetch_decode", "reason": "staged_audio_invalid"}
    assert _walk(queue, store) == 5
    message = _event(caplog, "event=batch_validation_disposition outcome=held_for_disposition")
    assert "stage=fetch_decode" in message
    assert "worker_reason=staged_audio_invalid" in message
    assert "recovery=held" in message


def test_walk_fetch_decode_retained_audio_invalid_preserved_diagnosis_names_the_disposition_channel(
    monkeypatch, caplog
):
    """A bare-exhausting ladder over seeded (fetch_decode, retained_audio_invalid) evidence reports disposition."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue = _queued_for_walk()
    store.rows["jobs", "a"]["worker_failure_evidence"] = {"stage": "fetch_decode", "reason": "retained_audio_invalid"}
    assert _walk(queue, store) == 5
    message = _event(caplog, "event=batch_validation_disposition outcome=held_for_disposition")
    assert "stage=fetch_decode" in message
    assert "worker_reason=retained_audio_invalid" in message
    assert "recovery=held" in message


def test_walk_fetch_decode_decoded_duration_mismatch_preserved_diagnosis_names_the_disposition_channel(
    monkeypatch, caplog
):
    """A bare-exhausting ladder over seeded (fetch_decode, decoded_duration_mismatch) evidence reports disposition."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue = _queued_for_walk()
    store.rows["jobs", "a"]["worker_failure_evidence"] = {
        "stage": "fetch_decode",
        "reason": "decoded_duration_mismatch",
    }
    assert _walk(queue, store) == 5
    message = _event(caplog, "event=batch_validation_disposition outcome=held_for_disposition")
    assert "stage=fetch_decode" in message
    assert "worker_reason=decoded_duration_mismatch" in message
    assert "recovery=held" in message


def test_walk_fetch_decode_word_shape_preserved_diagnosis_names_the_disposition_channel(monkeypatch, caplog):
    """A bare-exhausting ladder over seeded (fetch_decode, word_shape) evidence reports disposition."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue = _queued_for_walk()
    store.rows["jobs", "a"]["worker_failure_evidence"] = {"stage": "fetch_decode", "reason": "word_shape"}
    assert _walk(queue, store) == 5
    message = _event(caplog, "event=batch_validation_disposition outcome=held_for_disposition")
    assert "stage=fetch_decode" in message
    assert "worker_reason=word_shape" in message
    assert "recovery=held" in message


def test_walk_fetch_decode_word_clock_preserved_diagnosis_names_the_disposition_channel(monkeypatch, caplog):
    """A bare-exhausting ladder over seeded (fetch_decode, word_clock) evidence reports disposition."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue = _queued_for_walk()
    store.rows["jobs", "a"]["worker_failure_evidence"] = {"stage": "fetch_decode", "reason": "word_clock"}
    assert _walk(queue, store) == 5
    message = _event(caplog, "event=batch_validation_disposition outcome=held_for_disposition")
    assert "stage=fetch_decode" in message
    assert "worker_reason=word_clock" in message
    assert "recovery=held" in message


def test_walk_fetch_decode_word_sequence_preserved_diagnosis_names_the_disposition_channel(monkeypatch, caplog):
    """A bare-exhausting ladder over seeded (fetch_decode, word_sequence) evidence reports disposition."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue = _queued_for_walk()
    store.rows["jobs", "a"]["worker_failure_evidence"] = {"stage": "fetch_decode", "reason": "word_sequence"}
    assert _walk(queue, store) == 5
    message = _event(caplog, "event=batch_validation_disposition outcome=held_for_disposition")
    assert "stage=fetch_decode" in message
    assert "worker_reason=word_sequence" in message
    assert "recovery=held" in message


def test_walk_fetch_decode_vad_nonfinite_preserved_diagnosis_names_the_disposition_channel(monkeypatch, caplog):
    """A bare-exhausting ladder over seeded (fetch_decode, vad_nonfinite) evidence reports disposition."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue = _queued_for_walk()
    store.rows["jobs", "a"]["worker_failure_evidence"] = {"stage": "fetch_decode", "reason": "vad_nonfinite"}
    assert _walk(queue, store) == 5
    message = _event(caplog, "event=batch_validation_disposition outcome=held_for_disposition")
    assert "stage=fetch_decode" in message
    assert "worker_reason=vad_nonfinite" in message
    assert "recovery=held" in message


def test_walk_fetch_decode_vad_order_preserved_diagnosis_names_the_disposition_channel(monkeypatch, caplog):
    """A bare-exhausting ladder over seeded (fetch_decode, vad_order) evidence reports disposition."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue = _queued_for_walk()
    store.rows["jobs", "a"]["worker_failure_evidence"] = {"stage": "fetch_decode", "reason": "vad_order"}
    assert _walk(queue, store) == 5
    message = _event(caplog, "event=batch_validation_disposition outcome=held_for_disposition")
    assert "stage=fetch_decode" in message
    assert "worker_reason=vad_order" in message
    assert "recovery=held" in message


def test_walk_fetch_decode_vad_bounds_preserved_diagnosis_names_the_disposition_channel(monkeypatch, caplog):
    """A bare-exhausting ladder over seeded (fetch_decode, vad_bounds) evidence reports disposition."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue = _queued_for_walk()
    store.rows["jobs", "a"]["worker_failure_evidence"] = {"stage": "fetch_decode", "reason": "vad_bounds"}
    assert _walk(queue, store) == 5
    message = _event(caplog, "event=batch_validation_disposition outcome=held_for_disposition")
    assert "stage=fetch_decode" in message
    assert "worker_reason=vad_bounds" in message
    assert "recovery=held" in message


def test_walk_fetch_decode_empty_asr_preserved_diagnosis_names_the_quarantined_channel(monkeypatch, caplog):
    """A bare-exhausting ladder over seeded (fetch_decode, empty_asr) evidence reports quarantined."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue = _queued_for_walk()
    store.rows["jobs", "a"]["worker_failure_evidence"] = {"stage": "fetch_decode", "reason": "empty_asr"}
    assert _walk(queue, store) == 5
    message = _event(caplog, "event=batch_quarantined reason=worker_failed")
    assert "stage=fetch_decode" in message
    assert "worker_reason=empty_asr" in message
    assert "recovery=held" in message


def test_walk_fetch_decode_no_owned_words_preserved_diagnosis_names_the_quarantined_channel(monkeypatch, caplog):
    """A bare-exhausting ladder over seeded (fetch_decode, no_owned_words) evidence reports quarantined."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue = _queued_for_walk()
    store.rows["jobs", "a"]["worker_failure_evidence"] = {"stage": "fetch_decode", "reason": "no_owned_words"}
    assert _walk(queue, store) == 5
    message = _event(caplog, "event=batch_quarantined reason=worker_failed")
    assert "stage=fetch_decode" in message
    assert "worker_reason=no_owned_words" in message
    assert "recovery=held" in message


def test_walk_fetch_decode_unsupported_language_preserved_diagnosis_names_the_guard_channel(monkeypatch, caplog):
    """A bare-exhausting ladder over seeded (fetch_decode, unsupported_language) evidence reports guard."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue = _queued_for_walk()
    store.rows["jobs", "a"]["worker_failure_evidence"] = {"stage": "fetch_decode", "reason": "unsupported_language"}
    assert _walk(queue, store) == 5
    message = _event(caplog, "event=batch_language_guard outcome=held_for_redrive")
    assert "stage=fetch_decode" in message
    assert "worker_reason=unsupported_language" in message
    assert "recovery=held" in message


def test_walk_fetch_decode_outside_admitted_source_preserved_diagnosis_names_the_quarantined_channel(
    monkeypatch, caplog
):
    """A bare-exhausting ladder over seeded (fetch_decode, outside_admitted_source) evidence reports quarantined."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue = _queued_for_walk()
    store.rows["jobs", "a"]["worker_failure_evidence"] = {"stage": "fetch_decode", "reason": "outside_admitted_source"}
    assert _walk(queue, store) == 5
    message = _event(caplog, "event=batch_quarantined reason=worker_failed")
    assert "stage=fetch_decode" in message
    assert "worker_reason=outside_admitted_source" in message
    assert "recovery=held" in message


def test_walk_vad_windows_staged_audio_invalid_preserved_diagnosis_names_the_quarantined_channel(monkeypatch, caplog):
    """A bare-exhausting ladder over seeded (vad_windows, staged_audio_invalid) evidence reports quarantined."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue = _queued_for_walk()
    store.rows["jobs", "a"]["worker_failure_evidence"] = {"stage": "vad_windows", "reason": "staged_audio_invalid"}
    assert _walk(queue, store) == 5
    message = _event(caplog, "event=batch_quarantined reason=worker_failed")
    assert "stage=vad_windows" in message
    assert "worker_reason=staged_audio_invalid" in message
    assert "recovery=held" in message


def test_walk_vad_windows_retained_audio_invalid_preserved_diagnosis_names_the_quarantined_channel(monkeypatch, caplog):
    """A bare-exhausting ladder over seeded (vad_windows, retained_audio_invalid) evidence reports quarantined."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue = _queued_for_walk()
    store.rows["jobs", "a"]["worker_failure_evidence"] = {"stage": "vad_windows", "reason": "retained_audio_invalid"}
    assert _walk(queue, store) == 5
    message = _event(caplog, "event=batch_quarantined reason=worker_failed")
    assert "stage=vad_windows" in message
    assert "worker_reason=retained_audio_invalid" in message
    assert "recovery=held" in message


def test_walk_vad_windows_decoded_duration_mismatch_preserved_diagnosis_names_the_quarantined_channel(
    monkeypatch, caplog
):
    """A bare-exhausting ladder over seeded (vad_windows, decoded_duration_mismatch) evidence reports quarantined."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue = _queued_for_walk()
    store.rows["jobs", "a"]["worker_failure_evidence"] = {"stage": "vad_windows", "reason": "decoded_duration_mismatch"}
    assert _walk(queue, store) == 5
    message = _event(caplog, "event=batch_quarantined reason=worker_failed")
    assert "stage=vad_windows" in message
    assert "worker_reason=decoded_duration_mismatch" in message
    assert "recovery=held" in message


def test_walk_vad_windows_word_shape_preserved_diagnosis_names_the_disposition_channel(monkeypatch, caplog):
    """A bare-exhausting ladder over seeded (vad_windows, word_shape) evidence reports disposition."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue = _queued_for_walk()
    store.rows["jobs", "a"]["worker_failure_evidence"] = {"stage": "vad_windows", "reason": "word_shape"}
    assert _walk(queue, store) == 5
    message = _event(caplog, "event=batch_validation_disposition outcome=held_for_disposition")
    assert "stage=vad_windows" in message
    assert "worker_reason=word_shape" in message
    assert "recovery=held" in message


def test_walk_vad_windows_word_clock_preserved_diagnosis_names_the_disposition_channel(monkeypatch, caplog):
    """A bare-exhausting ladder over seeded (vad_windows, word_clock) evidence reports disposition."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue = _queued_for_walk()
    store.rows["jobs", "a"]["worker_failure_evidence"] = {"stage": "vad_windows", "reason": "word_clock"}
    assert _walk(queue, store) == 5
    message = _event(caplog, "event=batch_validation_disposition outcome=held_for_disposition")
    assert "stage=vad_windows" in message
    assert "worker_reason=word_clock" in message
    assert "recovery=held" in message


def test_walk_vad_windows_word_sequence_preserved_diagnosis_names_the_disposition_channel(monkeypatch, caplog):
    """A bare-exhausting ladder over seeded (vad_windows, word_sequence) evidence reports disposition."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue = _queued_for_walk()
    store.rows["jobs", "a"]["worker_failure_evidence"] = {"stage": "vad_windows", "reason": "word_sequence"}
    assert _walk(queue, store) == 5
    message = _event(caplog, "event=batch_validation_disposition outcome=held_for_disposition")
    assert "stage=vad_windows" in message
    assert "worker_reason=word_sequence" in message
    assert "recovery=held" in message


def test_walk_vad_windows_vad_nonfinite_preserved_diagnosis_names_the_disposition_channel(monkeypatch, caplog):
    """A bare-exhausting ladder over seeded (vad_windows, vad_nonfinite) evidence reports disposition."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue = _queued_for_walk()
    store.rows["jobs", "a"]["worker_failure_evidence"] = {"stage": "vad_windows", "reason": "vad_nonfinite"}
    assert _walk(queue, store) == 5
    message = _event(caplog, "event=batch_validation_disposition outcome=held_for_disposition")
    assert "stage=vad_windows" in message
    assert "worker_reason=vad_nonfinite" in message
    assert "recovery=held" in message


def test_walk_vad_windows_vad_order_preserved_diagnosis_names_the_disposition_channel(monkeypatch, caplog):
    """A bare-exhausting ladder over seeded (vad_windows, vad_order) evidence reports disposition."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue = _queued_for_walk()
    store.rows["jobs", "a"]["worker_failure_evidence"] = {"stage": "vad_windows", "reason": "vad_order"}
    assert _walk(queue, store) == 5
    message = _event(caplog, "event=batch_validation_disposition outcome=held_for_disposition")
    assert "stage=vad_windows" in message
    assert "worker_reason=vad_order" in message
    assert "recovery=held" in message


def test_walk_vad_windows_vad_bounds_preserved_diagnosis_names_the_disposition_channel(monkeypatch, caplog):
    """A bare-exhausting ladder over seeded (vad_windows, vad_bounds) evidence reports disposition."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue = _queued_for_walk()
    store.rows["jobs", "a"]["worker_failure_evidence"] = {"stage": "vad_windows", "reason": "vad_bounds"}
    assert _walk(queue, store) == 5
    message = _event(caplog, "event=batch_validation_disposition outcome=held_for_disposition")
    assert "stage=vad_windows" in message
    assert "worker_reason=vad_bounds" in message
    assert "recovery=held" in message


def test_walk_vad_windows_empty_asr_preserved_diagnosis_names_the_quarantined_channel(monkeypatch, caplog):
    """A bare-exhausting ladder over seeded (vad_windows, empty_asr) evidence reports quarantined."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue = _queued_for_walk()
    store.rows["jobs", "a"]["worker_failure_evidence"] = {"stage": "vad_windows", "reason": "empty_asr"}
    assert _walk(queue, store) == 5
    message = _event(caplog, "event=batch_quarantined reason=worker_failed")
    assert "stage=vad_windows" in message
    assert "worker_reason=empty_asr" in message
    assert "recovery=held" in message


def test_walk_vad_windows_no_owned_words_preserved_diagnosis_names_the_quarantined_channel(monkeypatch, caplog):
    """A bare-exhausting ladder over seeded (vad_windows, no_owned_words) evidence reports quarantined."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue = _queued_for_walk()
    store.rows["jobs", "a"]["worker_failure_evidence"] = {"stage": "vad_windows", "reason": "no_owned_words"}
    assert _walk(queue, store) == 5
    message = _event(caplog, "event=batch_quarantined reason=worker_failed")
    assert "stage=vad_windows" in message
    assert "worker_reason=no_owned_words" in message
    assert "recovery=held" in message


def test_walk_vad_windows_unsupported_language_preserved_diagnosis_names_the_guard_channel(monkeypatch, caplog):
    """A bare-exhausting ladder over seeded (vad_windows, unsupported_language) evidence reports guard."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue = _queued_for_walk()
    store.rows["jobs", "a"]["worker_failure_evidence"] = {"stage": "vad_windows", "reason": "unsupported_language"}
    assert _walk(queue, store) == 5
    message = _event(caplog, "event=batch_language_guard outcome=held_for_redrive")
    assert "stage=vad_windows" in message
    assert "worker_reason=unsupported_language" in message
    assert "recovery=held" in message


def test_walk_vad_windows_outside_admitted_source_preserved_diagnosis_names_the_quarantined_channel(
    monkeypatch, caplog
):
    """A bare-exhausting ladder over seeded (vad_windows, outside_admitted_source) evidence reports quarantined."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue = _queued_for_walk()
    store.rows["jobs", "a"]["worker_failure_evidence"] = {"stage": "vad_windows", "reason": "outside_admitted_source"}
    assert _walk(queue, store) == 5
    message = _event(caplog, "event=batch_quarantined reason=worker_failed")
    assert "stage=vad_windows" in message
    assert "worker_reason=outside_admitted_source" in message
    assert "recovery=held" in message


def test_walk_word_clocks_staged_audio_invalid_preserved_diagnosis_names_the_quarantined_channel(monkeypatch, caplog):
    """A bare-exhausting ladder over seeded (word_clocks, staged_audio_invalid) evidence reports quarantined."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue = _queued_for_walk()
    store.rows["jobs", "a"]["worker_failure_evidence"] = {"stage": "word_clocks", "reason": "staged_audio_invalid"}
    assert _walk(queue, store) == 5
    message = _event(caplog, "event=batch_quarantined reason=worker_failed")
    assert "stage=word_clocks" in message
    assert "worker_reason=staged_audio_invalid" in message
    assert "recovery=held" in message


def test_walk_word_clocks_retained_audio_invalid_preserved_diagnosis_names_the_quarantined_channel(monkeypatch, caplog):
    """A bare-exhausting ladder over seeded (word_clocks, retained_audio_invalid) evidence reports quarantined."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue = _queued_for_walk()
    store.rows["jobs", "a"]["worker_failure_evidence"] = {"stage": "word_clocks", "reason": "retained_audio_invalid"}
    assert _walk(queue, store) == 5
    message = _event(caplog, "event=batch_quarantined reason=worker_failed")
    assert "stage=word_clocks" in message
    assert "worker_reason=retained_audio_invalid" in message
    assert "recovery=held" in message


def test_walk_word_clocks_decoded_duration_mismatch_preserved_diagnosis_names_the_quarantined_channel(
    monkeypatch, caplog
):
    """A bare-exhausting ladder over seeded (word_clocks, decoded_duration_mismatch) evidence reports quarantined."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue = _queued_for_walk()
    store.rows["jobs", "a"]["worker_failure_evidence"] = {"stage": "word_clocks", "reason": "decoded_duration_mismatch"}
    assert _walk(queue, store) == 5
    message = _event(caplog, "event=batch_quarantined reason=worker_failed")
    assert "stage=word_clocks" in message
    assert "worker_reason=decoded_duration_mismatch" in message
    assert "recovery=held" in message


def test_walk_word_clocks_word_shape_preserved_diagnosis_names_the_disposition_channel(monkeypatch, caplog):
    """A bare-exhausting ladder over seeded (word_clocks, word_shape) evidence reports disposition."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue = _queued_for_walk()
    store.rows["jobs", "a"]["worker_failure_evidence"] = {"stage": "word_clocks", "reason": "word_shape"}
    assert _walk(queue, store) == 5
    message = _event(caplog, "event=batch_validation_disposition outcome=held_for_disposition")
    assert "stage=word_clocks" in message
    assert "worker_reason=word_shape" in message
    assert "recovery=held" in message


def test_walk_word_clocks_word_clock_preserved_diagnosis_names_the_disposition_channel(monkeypatch, caplog):
    """A bare-exhausting ladder over seeded (word_clocks, word_clock) evidence reports disposition."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue = _queued_for_walk()
    store.rows["jobs", "a"]["worker_failure_evidence"] = {"stage": "word_clocks", "reason": "word_clock"}
    assert _walk(queue, store) == 5
    message = _event(caplog, "event=batch_validation_disposition outcome=held_for_disposition")
    assert "stage=word_clocks" in message
    assert "worker_reason=word_clock" in message
    assert "recovery=held" in message


def test_walk_word_clocks_word_sequence_preserved_diagnosis_names_the_disposition_channel(monkeypatch, caplog):
    """A bare-exhausting ladder over seeded (word_clocks, word_sequence) evidence reports disposition."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue = _queued_for_walk()
    store.rows["jobs", "a"]["worker_failure_evidence"] = {"stage": "word_clocks", "reason": "word_sequence"}
    assert _walk(queue, store) == 5
    message = _event(caplog, "event=batch_validation_disposition outcome=held_for_disposition")
    assert "stage=word_clocks" in message
    assert "worker_reason=word_sequence" in message
    assert "recovery=held" in message


def test_walk_word_clocks_vad_nonfinite_preserved_diagnosis_names_the_disposition_channel(monkeypatch, caplog):
    """A bare-exhausting ladder over seeded (word_clocks, vad_nonfinite) evidence reports disposition."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue = _queued_for_walk()
    store.rows["jobs", "a"]["worker_failure_evidence"] = {"stage": "word_clocks", "reason": "vad_nonfinite"}
    assert _walk(queue, store) == 5
    message = _event(caplog, "event=batch_validation_disposition outcome=held_for_disposition")
    assert "stage=word_clocks" in message
    assert "worker_reason=vad_nonfinite" in message
    assert "recovery=held" in message


def test_walk_word_clocks_vad_order_preserved_diagnosis_names_the_disposition_channel(monkeypatch, caplog):
    """A bare-exhausting ladder over seeded (word_clocks, vad_order) evidence reports disposition."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue = _queued_for_walk()
    store.rows["jobs", "a"]["worker_failure_evidence"] = {"stage": "word_clocks", "reason": "vad_order"}
    assert _walk(queue, store) == 5
    message = _event(caplog, "event=batch_validation_disposition outcome=held_for_disposition")
    assert "stage=word_clocks" in message
    assert "worker_reason=vad_order" in message
    assert "recovery=held" in message


def test_walk_word_clocks_vad_bounds_preserved_diagnosis_names_the_disposition_channel(monkeypatch, caplog):
    """A bare-exhausting ladder over seeded (word_clocks, vad_bounds) evidence reports disposition."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue = _queued_for_walk()
    store.rows["jobs", "a"]["worker_failure_evidence"] = {"stage": "word_clocks", "reason": "vad_bounds"}
    assert _walk(queue, store) == 5
    message = _event(caplog, "event=batch_validation_disposition outcome=held_for_disposition")
    assert "stage=word_clocks" in message
    assert "worker_reason=vad_bounds" in message
    assert "recovery=held" in message


def test_walk_word_clocks_empty_asr_preserved_diagnosis_names_the_quarantined_channel(monkeypatch, caplog):
    """A bare-exhausting ladder over seeded (word_clocks, empty_asr) evidence reports quarantined."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue = _queued_for_walk()
    store.rows["jobs", "a"]["worker_failure_evidence"] = {"stage": "word_clocks", "reason": "empty_asr"}
    assert _walk(queue, store) == 5
    message = _event(caplog, "event=batch_quarantined reason=worker_failed")
    assert "stage=word_clocks" in message
    assert "worker_reason=empty_asr" in message
    assert "recovery=held" in message


def test_walk_word_clocks_no_owned_words_preserved_diagnosis_names_the_quarantined_channel(monkeypatch, caplog):
    """A bare-exhausting ladder over seeded (word_clocks, no_owned_words) evidence reports quarantined."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue = _queued_for_walk()
    store.rows["jobs", "a"]["worker_failure_evidence"] = {"stage": "word_clocks", "reason": "no_owned_words"}
    assert _walk(queue, store) == 5
    message = _event(caplog, "event=batch_quarantined reason=worker_failed")
    assert "stage=word_clocks" in message
    assert "worker_reason=no_owned_words" in message
    assert "recovery=held" in message


def test_walk_word_clocks_unsupported_language_preserved_diagnosis_names_the_guard_channel(monkeypatch, caplog):
    """A bare-exhausting ladder over seeded (word_clocks, unsupported_language) evidence reports guard."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue = _queued_for_walk()
    store.rows["jobs", "a"]["worker_failure_evidence"] = {"stage": "word_clocks", "reason": "unsupported_language"}
    assert _walk(queue, store) == 5
    message = _event(caplog, "event=batch_language_guard outcome=held_for_redrive")
    assert "stage=word_clocks" in message
    assert "worker_reason=unsupported_language" in message
    assert "recovery=held" in message


def test_walk_word_clocks_outside_admitted_source_preserved_diagnosis_names_the_quarantined_channel(
    monkeypatch, caplog
):
    """A bare-exhausting ladder over seeded (word_clocks, outside_admitted_source) evidence reports quarantined."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue = _queued_for_walk()
    store.rows["jobs", "a"]["worker_failure_evidence"] = {"stage": "word_clocks", "reason": "outside_admitted_source"}
    assert _walk(queue, store) == 5
    message = _event(caplog, "event=batch_quarantined reason=worker_failed")
    assert "stage=word_clocks" in message
    assert "worker_reason=outside_admitted_source" in message
    assert "recovery=held" in message


def test_walk_assemble_words_staged_audio_invalid_preserved_diagnosis_names_the_quarantined_channel(
    monkeypatch, caplog
):
    """A bare-exhausting ladder over seeded (assemble_words, staged_audio_invalid) evidence reports quarantined."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue = _queued_for_walk()
    store.rows["jobs", "a"]["worker_failure_evidence"] = {"stage": "assemble_words", "reason": "staged_audio_invalid"}
    assert _walk(queue, store) == 5
    message = _event(caplog, "event=batch_quarantined reason=worker_failed")
    assert "stage=assemble_words" in message
    assert "worker_reason=staged_audio_invalid" in message
    assert "recovery=held" in message


def test_walk_assemble_words_retained_audio_invalid_preserved_diagnosis_names_the_quarantined_channel(
    monkeypatch, caplog
):
    """A bare-exhausting ladder over seeded (assemble_words, retained_audio_invalid) evidence reports quarantined."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue = _queued_for_walk()
    store.rows["jobs", "a"]["worker_failure_evidence"] = {"stage": "assemble_words", "reason": "retained_audio_invalid"}
    assert _walk(queue, store) == 5
    message = _event(caplog, "event=batch_quarantined reason=worker_failed")
    assert "stage=assemble_words" in message
    assert "worker_reason=retained_audio_invalid" in message
    assert "recovery=held" in message


def test_walk_assemble_words_decoded_duration_mismatch_preserved_diagnosis_names_the_quarantined_channel(
    monkeypatch, caplog
):
    """A bare-exhausting ladder over seeded (assemble_words, decoded_duration_mismatch) evidence reports quarantined."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue = _queued_for_walk()
    store.rows["jobs", "a"]["worker_failure_evidence"] = {
        "stage": "assemble_words",
        "reason": "decoded_duration_mismatch",
    }
    assert _walk(queue, store) == 5
    message = _event(caplog, "event=batch_quarantined reason=worker_failed")
    assert "stage=assemble_words" in message
    assert "worker_reason=decoded_duration_mismatch" in message
    assert "recovery=held" in message


def test_walk_assemble_words_word_shape_preserved_diagnosis_names_the_disposition_channel(monkeypatch, caplog):
    """A bare-exhausting ladder over seeded (assemble_words, word_shape) evidence reports disposition."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue = _queued_for_walk()
    store.rows["jobs", "a"]["worker_failure_evidence"] = {"stage": "assemble_words", "reason": "word_shape"}
    assert _walk(queue, store) == 5
    message = _event(caplog, "event=batch_validation_disposition outcome=held_for_disposition")
    assert "stage=assemble_words" in message
    assert "worker_reason=word_shape" in message
    assert "recovery=held" in message


def test_walk_assemble_words_word_clock_preserved_diagnosis_names_the_disposition_channel(monkeypatch, caplog):
    """A bare-exhausting ladder over seeded (assemble_words, word_clock) evidence reports disposition."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue = _queued_for_walk()
    store.rows["jobs", "a"]["worker_failure_evidence"] = {"stage": "assemble_words", "reason": "word_clock"}
    assert _walk(queue, store) == 5
    message = _event(caplog, "event=batch_validation_disposition outcome=held_for_disposition")
    assert "stage=assemble_words" in message
    assert "worker_reason=word_clock" in message
    assert "recovery=held" in message


def test_walk_assemble_words_word_sequence_preserved_diagnosis_names_the_disposition_channel(monkeypatch, caplog):
    """A bare-exhausting ladder over seeded (assemble_words, word_sequence) evidence reports disposition."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue = _queued_for_walk()
    store.rows["jobs", "a"]["worker_failure_evidence"] = {"stage": "assemble_words", "reason": "word_sequence"}
    assert _walk(queue, store) == 5
    message = _event(caplog, "event=batch_validation_disposition outcome=held_for_disposition")
    assert "stage=assemble_words" in message
    assert "worker_reason=word_sequence" in message
    assert "recovery=held" in message


def test_walk_assemble_words_vad_nonfinite_preserved_diagnosis_names_the_disposition_channel(monkeypatch, caplog):
    """A bare-exhausting ladder over seeded (assemble_words, vad_nonfinite) evidence reports disposition."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue = _queued_for_walk()
    store.rows["jobs", "a"]["worker_failure_evidence"] = {"stage": "assemble_words", "reason": "vad_nonfinite"}
    assert _walk(queue, store) == 5
    message = _event(caplog, "event=batch_validation_disposition outcome=held_for_disposition")
    assert "stage=assemble_words" in message
    assert "worker_reason=vad_nonfinite" in message
    assert "recovery=held" in message


def test_walk_assemble_words_vad_order_preserved_diagnosis_names_the_disposition_channel(monkeypatch, caplog):
    """A bare-exhausting ladder over seeded (assemble_words, vad_order) evidence reports disposition."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue = _queued_for_walk()
    store.rows["jobs", "a"]["worker_failure_evidence"] = {"stage": "assemble_words", "reason": "vad_order"}
    assert _walk(queue, store) == 5
    message = _event(caplog, "event=batch_validation_disposition outcome=held_for_disposition")
    assert "stage=assemble_words" in message
    assert "worker_reason=vad_order" in message
    assert "recovery=held" in message


def test_walk_assemble_words_vad_bounds_preserved_diagnosis_names_the_disposition_channel(monkeypatch, caplog):
    """A bare-exhausting ladder over seeded (assemble_words, vad_bounds) evidence reports disposition."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue = _queued_for_walk()
    store.rows["jobs", "a"]["worker_failure_evidence"] = {"stage": "assemble_words", "reason": "vad_bounds"}
    assert _walk(queue, store) == 5
    message = _event(caplog, "event=batch_validation_disposition outcome=held_for_disposition")
    assert "stage=assemble_words" in message
    assert "worker_reason=vad_bounds" in message
    assert "recovery=held" in message


def test_walk_assemble_words_empty_asr_preserved_diagnosis_names_the_ladder_channel(monkeypatch, caplog):
    """A bare-exhausting ladder over seeded (assemble_words, empty_asr) evidence reports ladder."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue = _queued_for_walk()
    store.rows["jobs", "a"]["worker_failure_evidence"] = {"stage": "assemble_words", "reason": "empty_asr"}
    assert _walk(queue, store) == 5
    message = _event(caplog, "event=batch_empty_ladder outcome=held_for_recovery")
    assert "stage=assemble_words" in message
    assert "worker_reason=empty_asr" in message
    assert "recovery=held" in message


def test_walk_assemble_words_no_owned_words_preserved_diagnosis_names_the_ladder_channel(monkeypatch, caplog):
    """A bare-exhausting ladder over seeded (assemble_words, no_owned_words) evidence reports ladder."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue = _queued_for_walk()
    store.rows["jobs", "a"]["worker_failure_evidence"] = {"stage": "assemble_words", "reason": "no_owned_words"}
    assert _walk(queue, store) == 5
    message = _event(caplog, "event=batch_empty_ladder outcome=held_for_recovery")
    assert "stage=assemble_words" in message
    assert "worker_reason=no_owned_words" in message
    assert "recovery=held" in message


def test_walk_assemble_words_unsupported_language_preserved_diagnosis_names_the_guard_channel(monkeypatch, caplog):
    """A bare-exhausting ladder over seeded (assemble_words, unsupported_language) evidence reports guard."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue = _queued_for_walk()
    store.rows["jobs", "a"]["worker_failure_evidence"] = {"stage": "assemble_words", "reason": "unsupported_language"}
    assert _walk(queue, store) == 5
    message = _event(caplog, "event=batch_language_guard outcome=held_for_redrive")
    assert "stage=assemble_words" in message
    assert "worker_reason=unsupported_language" in message
    assert "recovery=held" in message


def test_walk_assemble_words_outside_admitted_source_preserved_diagnosis_names_the_quarantined_channel(
    monkeypatch, caplog
):
    """A bare-exhausting ladder over seeded (assemble_words, outside_admitted_source) evidence reports quarantined."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue = _queued_for_walk()
    store.rows["jobs", "a"]["worker_failure_evidence"] = {
        "stage": "assemble_words",
        "reason": "outside_admitted_source",
    }
    assert _walk(queue, store) == 5
    message = _event(caplog, "event=batch_quarantined reason=worker_failed")
    assert "stage=assemble_words" in message
    assert "worker_reason=outside_admitted_source" in message
    assert "recovery=held" in message


def test_walk_asr_recovery_staged_audio_invalid_preserved_diagnosis_names_the_quarantined_channel(monkeypatch, caplog):
    """A bare-exhausting ladder over seeded (asr_recovery, staged_audio_invalid) evidence reports quarantined."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue = _queued_for_walk()
    store.rows["jobs", "a"]["worker_failure_evidence"] = {"stage": "asr_recovery", "reason": "staged_audio_invalid"}
    assert _walk(queue, store) == 5
    message = _event(caplog, "event=batch_quarantined reason=worker_failed")
    assert "stage=asr_recovery" in message
    assert "worker_reason=staged_audio_invalid" in message
    assert "recovery=held" in message


def test_walk_asr_recovery_retained_audio_invalid_preserved_diagnosis_names_the_quarantined_channel(
    monkeypatch, caplog
):
    """A bare-exhausting ladder over seeded (asr_recovery, retained_audio_invalid) evidence reports quarantined."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue = _queued_for_walk()
    store.rows["jobs", "a"]["worker_failure_evidence"] = {"stage": "asr_recovery", "reason": "retained_audio_invalid"}
    assert _walk(queue, store) == 5
    message = _event(caplog, "event=batch_quarantined reason=worker_failed")
    assert "stage=asr_recovery" in message
    assert "worker_reason=retained_audio_invalid" in message
    assert "recovery=held" in message


def test_walk_asr_recovery_decoded_duration_mismatch_preserved_diagnosis_names_the_quarantined_channel(
    monkeypatch, caplog
):
    """A bare-exhausting ladder over seeded (asr_recovery, decoded_duration_mismatch) evidence reports quarantined."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue = _queued_for_walk()
    store.rows["jobs", "a"]["worker_failure_evidence"] = {
        "stage": "asr_recovery",
        "reason": "decoded_duration_mismatch",
    }
    assert _walk(queue, store) == 5
    message = _event(caplog, "event=batch_quarantined reason=worker_failed")
    assert "stage=asr_recovery" in message
    assert "worker_reason=decoded_duration_mismatch" in message
    assert "recovery=held" in message


def test_walk_asr_recovery_word_shape_preserved_diagnosis_names_the_disposition_channel(monkeypatch, caplog):
    """A bare-exhausting ladder over seeded (asr_recovery, word_shape) evidence reports disposition."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue = _queued_for_walk()
    store.rows["jobs", "a"]["worker_failure_evidence"] = {"stage": "asr_recovery", "reason": "word_shape"}
    assert _walk(queue, store) == 5
    message = _event(caplog, "event=batch_validation_disposition outcome=held_for_disposition")
    assert "stage=asr_recovery" in message
    assert "worker_reason=word_shape" in message
    assert "recovery=held" in message


def test_walk_asr_recovery_word_clock_preserved_diagnosis_names_the_disposition_channel(monkeypatch, caplog):
    """A bare-exhausting ladder over seeded (asr_recovery, word_clock) evidence reports disposition."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue = _queued_for_walk()
    store.rows["jobs", "a"]["worker_failure_evidence"] = {"stage": "asr_recovery", "reason": "word_clock"}
    assert _walk(queue, store) == 5
    message = _event(caplog, "event=batch_validation_disposition outcome=held_for_disposition")
    assert "stage=asr_recovery" in message
    assert "worker_reason=word_clock" in message
    assert "recovery=held" in message


def test_walk_asr_recovery_word_sequence_preserved_diagnosis_names_the_disposition_channel(monkeypatch, caplog):
    """A bare-exhausting ladder over seeded (asr_recovery, word_sequence) evidence reports disposition."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue = _queued_for_walk()
    store.rows["jobs", "a"]["worker_failure_evidence"] = {"stage": "asr_recovery", "reason": "word_sequence"}
    assert _walk(queue, store) == 5
    message = _event(caplog, "event=batch_validation_disposition outcome=held_for_disposition")
    assert "stage=asr_recovery" in message
    assert "worker_reason=word_sequence" in message
    assert "recovery=held" in message


def test_walk_asr_recovery_vad_nonfinite_preserved_diagnosis_names_the_disposition_channel(monkeypatch, caplog):
    """A bare-exhausting ladder over seeded (asr_recovery, vad_nonfinite) evidence reports disposition."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue = _queued_for_walk()
    store.rows["jobs", "a"]["worker_failure_evidence"] = {"stage": "asr_recovery", "reason": "vad_nonfinite"}
    assert _walk(queue, store) == 5
    message = _event(caplog, "event=batch_validation_disposition outcome=held_for_disposition")
    assert "stage=asr_recovery" in message
    assert "worker_reason=vad_nonfinite" in message
    assert "recovery=held" in message


def test_walk_asr_recovery_vad_order_preserved_diagnosis_names_the_disposition_channel(monkeypatch, caplog):
    """A bare-exhausting ladder over seeded (asr_recovery, vad_order) evidence reports disposition."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue = _queued_for_walk()
    store.rows["jobs", "a"]["worker_failure_evidence"] = {"stage": "asr_recovery", "reason": "vad_order"}
    assert _walk(queue, store) == 5
    message = _event(caplog, "event=batch_validation_disposition outcome=held_for_disposition")
    assert "stage=asr_recovery" in message
    assert "worker_reason=vad_order" in message
    assert "recovery=held" in message


def test_walk_asr_recovery_vad_bounds_preserved_diagnosis_names_the_disposition_channel(monkeypatch, caplog):
    """A bare-exhausting ladder over seeded (asr_recovery, vad_bounds) evidence reports disposition."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue = _queued_for_walk()
    store.rows["jobs", "a"]["worker_failure_evidence"] = {"stage": "asr_recovery", "reason": "vad_bounds"}
    assert _walk(queue, store) == 5
    message = _event(caplog, "event=batch_validation_disposition outcome=held_for_disposition")
    assert "stage=asr_recovery" in message
    assert "worker_reason=vad_bounds" in message
    assert "recovery=held" in message


def test_walk_asr_recovery_empty_asr_preserved_diagnosis_names_the_quarantined_channel(monkeypatch, caplog):
    """A bare-exhausting ladder over seeded (asr_recovery, empty_asr) evidence reports quarantined."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue = _queued_for_walk()
    store.rows["jobs", "a"]["worker_failure_evidence"] = {"stage": "asr_recovery", "reason": "empty_asr"}
    assert _walk(queue, store) == 5
    message = _event(caplog, "event=batch_quarantined reason=worker_failed")
    assert "stage=asr_recovery" in message
    assert "worker_reason=empty_asr" in message
    assert "recovery=held" in message


def test_walk_asr_recovery_no_owned_words_preserved_diagnosis_names_the_quarantined_channel(monkeypatch, caplog):
    """A bare-exhausting ladder over seeded (asr_recovery, no_owned_words) evidence reports quarantined."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue = _queued_for_walk()
    store.rows["jobs", "a"]["worker_failure_evidence"] = {"stage": "asr_recovery", "reason": "no_owned_words"}
    assert _walk(queue, store) == 5
    message = _event(caplog, "event=batch_quarantined reason=worker_failed")
    assert "stage=asr_recovery" in message
    assert "worker_reason=no_owned_words" in message
    assert "recovery=held" in message


def test_walk_asr_recovery_unsupported_language_preserved_diagnosis_names_the_guard_channel(monkeypatch, caplog):
    """A bare-exhausting ladder over seeded (asr_recovery, unsupported_language) evidence reports guard."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue = _queued_for_walk()
    store.rows["jobs", "a"]["worker_failure_evidence"] = {"stage": "asr_recovery", "reason": "unsupported_language"}
    assert _walk(queue, store) == 5
    message = _event(caplog, "event=batch_language_guard outcome=held_for_redrive")
    assert "stage=asr_recovery" in message
    assert "worker_reason=unsupported_language" in message
    assert "recovery=held" in message


def test_walk_asr_recovery_outside_admitted_source_preserved_diagnosis_names_the_quarantined_channel(
    monkeypatch, caplog
):
    """A bare-exhausting ladder over seeded (asr_recovery, outside_admitted_source) evidence reports quarantined."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue = _queued_for_walk()
    store.rows["jobs", "a"]["worker_failure_evidence"] = {"stage": "asr_recovery", "reason": "outside_admitted_source"}
    assert _walk(queue, store) == 5
    message = _event(caplog, "event=batch_quarantined reason=worker_failed")
    assert "stage=asr_recovery" in message
    assert "worker_reason=outside_admitted_source" in message
    assert "recovery=held" in message


def test_walk_latest_evidence_staged_audio_invalid_then_outside_admitted_source_names_outside_admitted_source(caplog):
    """Evidence on attempts 1 and 4: the terminal record names attempt 4's outside_admitted_source."""
    caplog.set_level(logging.INFO)
    store, queue = _queued_for_walk()
    plan = {
        1: {"stage": "fetch_decode", "reason": "staged_audio_invalid"},
        4: {"stage": "vad_windows", "reason": "outside_admitted_source"},
    }
    assert _walk(queue, store, evidence_plan=plan) == 5
    message = _event(
        caplog,
        (
            "event=batch_validation_disposition outcome=held_for_disposition"
            if ("outside_admitted_source" in TRIO or "outside_admitted_source" in FLAGGED)
            else "event=batch_quarantined reason=worker_failed"
        ),
    )
    assert "worker_reason=outside_admitted_source" in message


def test_walk_latest_evidence_outside_admitted_source_then_vad_bounds_names_vad_bounds(caplog):
    """Evidence on attempts 1 and 4: the terminal record names attempt 4's vad_bounds."""
    caplog.set_level(logging.INFO)
    store, queue = _queued_for_walk()
    plan = {
        1: {"stage": "fetch_decode", "reason": "outside_admitted_source"},
        4: {"stage": "vad_windows", "reason": "vad_bounds"},
    }
    assert _walk(queue, store, evidence_plan=plan) == 5
    message = _event(
        caplog,
        (
            "event=batch_validation_disposition outcome=held_for_disposition"
            if ("vad_bounds" in TRIO or "vad_bounds" in FLAGGED)
            else "event=batch_quarantined reason=worker_failed"
        ),
    )
    assert "worker_reason=vad_bounds" in message


def test_walk_latest_evidence_word_clock_then_unknown_names_unknown(caplog):
    """Evidence on attempts 1 and 4: the terminal record names attempt 4's unknown."""
    caplog.set_level(logging.INFO)
    store, queue = _queued_for_walk()
    plan = {
        1: {"stage": "fetch_decode", "reason": "word_clock"},
        4: {"stage": "vad_windows", "reason": "unknown"},
    }
    assert _walk(queue, store, evidence_plan=plan) == 5
    message = _event(
        caplog,
        (
            "event=batch_validation_disposition outcome=held_for_disposition"
            if ("unknown" in TRIO or "unknown" in FLAGGED)
            else "event=batch_quarantined reason=worker_failed"
        ),
    )
    assert "worker_reason=unknown" in message


def test_walk_latest_evidence_unknown_then_word_clock_names_word_clock(caplog):
    """Evidence on attempts 1 and 4: the terminal record names attempt 4's word_clock."""
    caplog.set_level(logging.INFO)
    store, queue = _queued_for_walk()
    plan = {
        1: {"stage": "fetch_decode", "reason": "unknown"},
        4: {"stage": "vad_windows", "reason": "word_clock"},
    }
    assert _walk(queue, store, evidence_plan=plan) == 5
    message = _event(
        caplog,
        (
            "event=batch_validation_disposition outcome=held_for_disposition"
            if ("word_clock" in TRIO or "word_clock" in FLAGGED)
            else "event=batch_quarantined reason=worker_failed"
        ),
    )
    assert "worker_reason=word_clock" in message


def test_walk_latest_evidence_vad_bounds_then_outside_admitted_source_names_outside_admitted_source(caplog):
    """Evidence on attempts 1 and 4: the terminal record names attempt 4's outside_admitted_source."""
    caplog.set_level(logging.INFO)
    store, queue = _queued_for_walk()
    plan = {
        1: {"stage": "fetch_decode", "reason": "vad_bounds"},
        4: {"stage": "vad_windows", "reason": "outside_admitted_source"},
    }
    assert _walk(queue, store, evidence_plan=plan) == 5
    message = _event(
        caplog,
        (
            "event=batch_validation_disposition outcome=held_for_disposition"
            if ("outside_admitted_source" in TRIO or "outside_admitted_source" in FLAGGED)
            else "event=batch_quarantined reason=worker_failed"
        ),
    )
    assert "worker_reason=outside_admitted_source" in message


def test_walk_attempt_token_staged_audio_invalid_names_the_exhausting_attempt(monkeypatch, caplog):
    """The disposition hold retains the ladder's attempt count for staged_audio_invalid."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue = _queued_for_walk()
    store.rows["jobs", "a"]["worker_failure_evidence"] = {
        "stage": "fetch_decode" if "staged_audio_invalid" in TRIO else "vad_windows",
        "reason": "staged_audio_invalid",
    }
    assert _walk(queue, store) == 5
    message = _event(caplog, "event=batch_validation_disposition outcome=held_for_disposition")
    assert "attempt=5 recovery=held" in message


def test_walk_attempt_token_vad_bounds_names_the_exhausting_attempt(monkeypatch, caplog):
    """The disposition hold retains the ladder's attempt count for vad_bounds."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue = _queued_for_walk()
    store.rows["jobs", "a"]["worker_failure_evidence"] = {
        "stage": "fetch_decode" if "vad_bounds" in TRIO else "vad_windows",
        "reason": "vad_bounds",
    }
    assert _walk(queue, store) == 5
    message = _event(caplog, "event=batch_validation_disposition outcome=held_for_disposition")
    assert "attempt=5 recovery=held" in message


def test_walk_attempt_token_word_clock_names_the_exhausting_attempt(monkeypatch, caplog):
    """The disposition hold retains the ladder's attempt count for word_clock."""
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    caplog.set_level(logging.INFO)
    store, queue = _queued_for_walk()
    store.rows["jobs", "a"]["worker_failure_evidence"] = {
        "stage": "fetch_decode" if "word_clock" in TRIO else "vad_windows",
        "reason": "word_clock",
    }
    assert _walk(queue, store) == 5
    message = _event(caplog, "event=batch_validation_disposition outcome=held_for_disposition")
    assert "attempt=5 recovery=held" in message
