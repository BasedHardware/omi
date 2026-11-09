# Failure-Class: FC-empty-ladder-recovery-handoff-misclassified-as-worker-fault
"""Live worker grid for the demoted channel: durations, servable languages, sub-second.

Every cell drives a real empty-recognition unit through ``process_batch`` and
pins the channel decision, the ``RecoveryWork`` evidence fields, the fault
counters, the persistence absence and the failure callback, per duration and
servable language — including a sub-second unit (the 2026-11-04
measured-speech-gate boundary) and a wholly-ghost-words ``no_owned_words``
unit.
"""

import logging
from dataclasses import replace
from unittest.mock import Mock

import numpy as np
import pytest

from utils.batch_pipeline.contracts import FailedWork, RecoveryWork, ValidationFailureWork, WorkResult
from utils.batch_pipeline.word_validation import BatchValidationError, ValidationReason
from tests.unit.test_batch_pipeline_worker import Samples, item, setup_worker

SERVABLE = ['en', 'es', 'fr']
DURATIONS = (1, 2, 4, 30)


def _flags(monkeypatch, safety="true", recovery="false", disposition="false", validation="true", silence="false"):
    monkeypatch.setenv("BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED", safety)
    monkeypatch.setenv("BATCH_PIPELINE_EMPTY_ASR_RECOVERY_ENABLED", recovery)
    monkeypatch.setenv("BATCH_PIPELINE_EMPTY_ASR_DISPOSITION_ENABLED", disposition)
    monkeypatch.setenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", validation)
    monkeypatch.setenv("BATCH_PIPELINE_WORKER_SILENCE_DISPOSITION_ENABLED", silence)


def _split(caplog):
    ladder = [r for r in caplog.records if "event=batch_empty_ladder" in r.getMessage()]
    fault = [r for r in caplog.records if "event=batch_worker_failed" in r.getMessage()]
    guard = [r for r in caplog.records if "event=batch_language_guard" in r.getMessage()]
    return ladder, fault, guard


def _run_empty(
    monkeypatch, caplog, *, duration=2, language="en", shadow=False, recover=Mock(return_value=[]), on_failure_seen=None
):
    _flags(monkeypatch)
    caplog.set_level(logging.INFO)
    provider = Mock()
    provider.transcribe_batch.side_effect = lambda samples: [[] for _ in samples]
    vad_cb = (lambda _: [(0.0, 0.45)]) if duration < 0.8 else (lambda _: [(0.2, 0.8)])
    worker, _, saved, _, _, failures = setup_worker(
        language_of=lambda _item, _lang=language: _lang,
        decode=lambda work: np.full(int(work.duration_seconds * 16000), 0.5, dtype=np.float32),
        vad=vad_cb,
        words_providers={"parakeet": provider},
        recover_words=recover,
        on_failure=(
            (lambda i, e, sink=on_failure_seen: sink.append((i.segment_id, e))) if on_failure_seen is not None else None
        ),
    )
    unit = item(duration=duration)
    if shadow:
        unit = replace(unit, shadow=True)
    results = worker.process_batch([unit])
    return worker, results, saved, failures


def test_grid_duration_1_samples_token(monkeypatch, caplog):
    _worker, results, saved, failures = _run_empty(monkeypatch, caplog, duration=1)
    ladder, fault, guard = _split(caplog)
    assert not fault and not guard and len(ladder) == 1
    assert ladder[0].levelno == logging.INFO
    assert "samples=16000 vad_spans=1 windows=1 asr_words=0 owned_words=0" in ladder[0].getMessage()
    assert results == [RecoveryWork("a", padded_retry="empty", padded_retry_empty=True)]
    assert not saved
    assert _worker.counts["failed"] == 1


def test_grid_duration_2_samples_token(monkeypatch, caplog):
    _worker, results, saved, failures = _run_empty(monkeypatch, caplog, duration=2)
    ladder, fault, guard = _split(caplog)
    assert not fault and not guard and len(ladder) == 1
    assert ladder[0].levelno == logging.INFO
    assert "samples=32000 vad_spans=1 windows=1 asr_words=0 owned_words=0" in ladder[0].getMessage()
    assert results == [RecoveryWork("a", padded_retry="empty", padded_retry_empty=True)]
    assert not saved
    assert _worker.counts["failed"] == 1


def test_grid_duration_4_samples_token(monkeypatch, caplog):
    _worker, results, saved, failures = _run_empty(monkeypatch, caplog, duration=4)
    ladder, fault, guard = _split(caplog)
    assert not fault and not guard and len(ladder) == 1
    assert ladder[0].levelno == logging.INFO
    assert "samples=64000 vad_spans=1 windows=1 asr_words=0 owned_words=0" in ladder[0].getMessage()
    assert results == [RecoveryWork("a", padded_retry="empty", padded_retry_empty=True)]
    assert not saved
    assert _worker.counts["failed"] == 1


def test_grid_duration_30_samples_token(monkeypatch, caplog):
    _worker, results, saved, failures = _run_empty(monkeypatch, caplog, duration=30)
    ladder, fault, guard = _split(caplog)
    assert not fault and not guard and len(ladder) == 1
    assert ladder[0].levelno == logging.INFO
    assert "samples=480000 vad_spans=1 windows=1 asr_words=0 owned_words=0" in ladder[0].getMessage()
    assert results == [RecoveryWork("a", padded_retry="empty", padded_retry_empty=True)]
    assert not saved
    assert _worker.counts["failed"] == 1


def test_grid_duration_1_measured_vad_evidence(monkeypatch, caplog):
    _worker, results, saved, failures = _run_empty(monkeypatch, caplog, duration=1)
    ladder, fault, guard = _split(caplog)
    assert not fault and not guard and len(ladder) == 1
    held = results[0].measured_held_vad_speech_seconds
    assert held is not None and abs(held - 0.6) < 1e-6
    assert isinstance(results[0].worker_vad_receipt, dict)


def test_grid_duration_2_measured_vad_evidence(monkeypatch, caplog):
    _worker, results, saved, failures = _run_empty(monkeypatch, caplog, duration=2)
    ladder, fault, guard = _split(caplog)
    assert not fault and not guard and len(ladder) == 1
    held = results[0].measured_held_vad_speech_seconds
    assert held is not None and abs(held - 0.6) < 1e-6
    assert isinstance(results[0].worker_vad_receipt, dict)


def test_grid_duration_4_measured_vad_evidence(monkeypatch, caplog):
    _worker, results, saved, failures = _run_empty(monkeypatch, caplog, duration=4)
    ladder, fault, guard = _split(caplog)
    assert not fault and not guard and len(ladder) == 1
    held = results[0].measured_held_vad_speech_seconds
    assert held is not None and abs(held - 0.6) < 1e-6
    assert isinstance(results[0].worker_vad_receipt, dict)


def test_grid_duration_30_measured_vad_evidence(monkeypatch, caplog):
    _worker, results, saved, failures = _run_empty(monkeypatch, caplog, duration=30)
    ladder, fault, guard = _split(caplog)
    assert not fault and not guard and len(ladder) == 1
    held = results[0].measured_held_vad_speech_seconds
    assert held is not None and abs(held - 0.6) < 1e-6
    assert isinstance(results[0].worker_vad_receipt, dict)


def test_grid_duration_1_failure_callback_receives_the_class_name(monkeypatch, caplog):
    seen = []
    _worker, results, saved, failures = _run_empty(monkeypatch, caplog, duration=1, on_failure_seen=seen)
    assert seen == [("a", "BatchValidationError")]


def test_grid_duration_2_failure_callback_receives_the_class_name(monkeypatch, caplog):
    seen = []
    _worker, results, saved, failures = _run_empty(monkeypatch, caplog, duration=2, on_failure_seen=seen)
    assert seen == [("a", "BatchValidationError")]


def test_grid_duration_4_failure_callback_receives_the_class_name(monkeypatch, caplog):
    seen = []
    _worker, results, saved, failures = _run_empty(monkeypatch, caplog, duration=4, on_failure_seen=seen)
    assert seen == [("a", "BatchValidationError")]


def test_grid_duration_30_failure_callback_receives_the_class_name(monkeypatch, caplog):
    seen = []
    _worker, results, saved, failures = _run_empty(monkeypatch, caplog, duration=30, on_failure_seen=seen)
    assert seen == [("a", "BatchValidationError")]


def test_grid_language_en_duration_2_reports_the_handoff(monkeypatch, caplog):
    _worker, results, saved, failures = _run_empty(monkeypatch, caplog, duration=2, language="en")
    ladder, fault, guard = _split(caplog)
    assert not fault and not guard and len(ladder) == 1
    assert ladder[0].levelno == logging.INFO
    message = ladder[0].getMessage()
    assert "error_class=BatchValidationError stage=assemble_words segment_id=a reason=empty_asr" in message
    assert "samples=32000" in message
    assert results == [RecoveryWork("a", padded_retry="empty", padded_retry_empty=True)]


def test_grid_language_en_duration_7_9_reports_the_handoff(monkeypatch, caplog):
    _worker, results, saved, failures = _run_empty(monkeypatch, caplog, duration=7.9, language="en")
    ladder, fault, guard = _split(caplog)
    assert not fault and not guard and len(ladder) == 1
    assert ladder[0].levelno == logging.INFO
    message = ladder[0].getMessage()
    assert "error_class=BatchValidationError stage=assemble_words segment_id=a reason=empty_asr" in message
    assert "samples=126400" in message
    assert results == [RecoveryWork("a", padded_retry="empty", padded_retry_empty=True)]


def test_grid_language_es_duration_2_reports_the_handoff(monkeypatch, caplog):
    _worker, results, saved, failures = _run_empty(monkeypatch, caplog, duration=2, language="es")
    ladder, fault, guard = _split(caplog)
    assert not fault and not guard and len(ladder) == 1
    assert ladder[0].levelno == logging.INFO
    message = ladder[0].getMessage()
    assert "error_class=BatchValidationError stage=assemble_words segment_id=a reason=empty_asr" in message
    assert "samples=32000" in message
    assert results == [RecoveryWork("a", padded_retry="empty", padded_retry_empty=True)]


def test_grid_language_es_duration_7_9_reports_the_handoff(monkeypatch, caplog):
    _worker, results, saved, failures = _run_empty(monkeypatch, caplog, duration=7.9, language="es")
    ladder, fault, guard = _split(caplog)
    assert not fault and not guard and len(ladder) == 1
    assert ladder[0].levelno == logging.INFO
    message = ladder[0].getMessage()
    assert "error_class=BatchValidationError stage=assemble_words segment_id=a reason=empty_asr" in message
    assert "samples=126400" in message
    assert results == [RecoveryWork("a", padded_retry="empty", padded_retry_empty=True)]


def test_grid_language_fr_duration_2_reports_the_handoff(monkeypatch, caplog):
    _worker, results, saved, failures = _run_empty(monkeypatch, caplog, duration=2, language="fr")
    ladder, fault, guard = _split(caplog)
    assert not fault and not guard and len(ladder) == 1
    assert ladder[0].levelno == logging.INFO
    message = ladder[0].getMessage()
    assert "error_class=BatchValidationError stage=assemble_words segment_id=a reason=empty_asr" in message
    assert "samples=32000" in message
    assert results == [RecoveryWork("a", padded_retry="empty", padded_retry_empty=True)]


def test_grid_language_fr_duration_7_9_reports_the_handoff(monkeypatch, caplog):
    _worker, results, saved, failures = _run_empty(monkeypatch, caplog, duration=7.9, language="fr")
    ladder, fault, guard = _split(caplog)
    assert not fault and not guard and len(ladder) == 1
    assert ladder[0].levelno == logging.INFO
    message = ladder[0].getMessage()
    assert "error_class=BatchValidationError stage=assemble_words segment_id=a reason=empty_asr" in message
    assert "samples=126400" in message
    assert results == [RecoveryWork("a", padded_retry="empty", padded_retry_empty=True)]


def test_grid_subsecond_es_holds_without_booking_fault_lines(monkeypatch, caplog):
    """The 2026-11-04 measured-speech gate: a sub-second unit rides the same handoff."""
    _worker, results, saved, failures = _run_empty(monkeypatch, caplog, duration=0.5, language="es")
    ladder, fault, guard = _split(caplog)
    assert not fault and not guard and len(ladder) == 1
    assert ladder[0].levelno == logging.INFO
    assert "outcome=recovery_handoff" in ladder[0].getMessage()
    assert "stage=assemble_words segment_id=a reason=empty_asr" in ladder[0].getMessage()
    assert results == [RecoveryWork("a", padded_retry="empty", padded_retry_empty=True)]
    assert not saved


def test_grid_subsecond_fr_holds_without_booking_fault_lines(monkeypatch, caplog):
    """The 2026-11-04 measured-speech gate: a sub-second unit rides the same handoff."""
    _worker, results, saved, failures = _run_empty(monkeypatch, caplog, duration=0.5, language="fr")
    ladder, fault, guard = _split(caplog)
    assert not fault and not guard and len(ladder) == 1
    assert ladder[0].levelno == logging.INFO
    assert "outcome=recovery_handoff" in ladder[0].getMessage()
    assert "stage=assemble_words segment_id=a reason=empty_asr" in ladder[0].getMessage()
    assert results == [RecoveryWork("a", padded_retry="empty", padded_retry_empty=True)]
    assert not saved


def test_grid_shadow_es_stays_on_the_shadow_line(monkeypatch, caplog):
    _worker, results, saved, failures = _run_empty(monkeypatch, caplog, shadow=True, language="es")
    ladder, fault, guard = _split(caplog)
    assert not ladder and not fault and not guard
    assert results == [RecoveryWork("a", padded_retry="empty", padded_retry_empty=True)]


def test_grid_shadow_fr_stays_on_the_shadow_line(monkeypatch, caplog):
    _worker, results, saved, failures = _run_empty(monkeypatch, caplog, shadow=True, language="fr")
    ladder, fault, guard = _split(caplog)
    assert not ladder and not fault and not guard
    assert results == [RecoveryWork("a", padded_retry="empty", padded_retry_empty=True)]


def test_grid_subsecond_half_second_holds_without_booking_fault_lines(monkeypatch, caplog):
    """The 2026-11-04 measured-speech gate: a sub-second unit rides the same handoff."""
    _worker, results, saved, failures = _run_empty(monkeypatch, caplog, duration=0.5)
    ladder, fault, guard = _split(caplog)
    assert not fault and not guard and len(ladder) == 1
    assert ladder[0].levelno == logging.INFO
    assert "outcome=recovery_handoff" in ladder[0].getMessage()
    assert "stage=assemble_words segment_id=a reason=empty_asr" in ladder[0].getMessage()
    assert results == [RecoveryWork("a", padded_retry="empty", padded_retry_empty=True)]
    assert not saved


def test_grid_dual_empty_units_each_report_one_handoff(monkeypatch, caplog):
    _flags(monkeypatch)
    caplog.set_level(logging.INFO)
    provider = Mock()
    provider.transcribe_batch.side_effect = lambda samples: [[] for _ in samples]
    worker, _, saved, _, _, failures = setup_worker(
        decode=lambda work: np.full(int(work.duration_seconds * 16000), 0.5, dtype=np.float32),
        vad=lambda _: [(0.2, 0.8)],
        words_providers={"parakeet": provider},
        recover_words=Mock(return_value=[]),
    )
    results = worker.process_batch([item(duration=2), item("b", 3)])
    ladder, fault, guard = _split(caplog)
    assert not fault and not guard and len(ladder) == 2
    assert {r.getMessage().split("segment_id=")[1].split()[0] for r in ladder} == {"a", "b"}
    assert all(r.levelno == logging.INFO for r in ladder)
    assert worker.counts["failed"] == 2
    assert not saved


def test_grid_record_args_are_scalar_and_exc_info_is_none(monkeypatch, caplog):
    _worker, results, saved, failures = _run_empty(monkeypatch, caplog)
    ladder, fault, guard = _split(caplog)
    assert len(ladder) == 1
    assert all(isinstance(value, (str, int)) for value in ladder[0].args)
    assert ladder[0].exc_info is None


def test_grid_wholly_ghost_words_drop_to_empty_asr(monkeypatch, caplog):
    _flags(monkeypatch)
    caplog.set_level(logging.INFO)
    provider = Mock()
    provider.transcribe_batch.return_value = [[{"word": "ghost", "timestamp": [99.0, 100.0]}]]
    worker, _, saved, _, _, failures = setup_worker(
        decode=lambda _: np.zeros(160320, dtype=np.float32),
        vad=lambda _: [(1, 2)],
        words_providers={"parakeet": provider},
        recover_words=Mock(return_value=[]),
    )
    results = worker.process_batch([item(duration=10.02)])
    ladder, fault, guard = _split(caplog)
    assert not fault and not guard and len(ladder) == 1
    message = ladder[0].getMessage()
    assert "stage=assemble_words segment_id=a reason=empty_asr" in message
    assert "asr_words=0 owned_words=0" in message
    assert len(results) == 1 and isinstance(results[0], RecoveryWork) and results[0].reason == "empty_asr"
    assert not saved


def test_grid_private_provider_error_stays_unclassified_on_the_fault_channel(monkeypatch, caplog):
    _flags(monkeypatch)
    caplog.set_level(logging.INFO)
    provider = Mock()
    provider.transcribe_batch.side_effect = ValueError("synthetic-private-must-not-be-logged")
    worker, _, saved, _, _, failures = setup_worker(
        decode=lambda work: np.full(int(work.duration_seconds * 16000), 0.5, dtype=np.float32),
        vad=lambda _: [(0.2, 0.8)],
        words_providers={"parakeet": provider},
    )
    results = worker.process_batch([item(duration=2)])
    ladder, fault, guard = _split(caplog)
    assert not ladder and not guard and len(fault) == 1
    assert fault[0].levelno == logging.ERROR
    assert "error_class=ValueError stage=asr segment_id=a reason=unclassified" in fault[0].getMessage()
    assert "synthetic-private-must-not-be-logged" not in caplog.text


def test_grid_language_en_duration_7_9_reports_the_handoff(monkeypatch, caplog):
    _worker, results, saved, failures = _run_empty(monkeypatch, caplog, duration=7.9, language="en")
    ladder, fault, guard = _split(caplog)
    assert not fault and not guard and len(ladder) == 1
    assert ladder[0].levelno == logging.INFO
    message = ladder[0].getMessage()
    assert "error_class=BatchValidationError stage=assemble_words segment_id=a reason=empty_asr" in message
    assert "samples=126400" in message
    assert results == [RecoveryWork("a", padded_retry="empty", padded_retry_empty=True)]


def test_grid_language_en_duration_20_04_reports_the_handoff(monkeypatch, caplog):
    _worker, results, saved, failures = _run_empty(monkeypatch, caplog, duration=20.04, language="en")
    ladder, fault, guard = _split(caplog)
    assert not fault and not guard and len(ladder) == 1
    assert ladder[0].levelno == logging.INFO
    message = ladder[0].getMessage()
    assert "error_class=BatchValidationError stage=assemble_words segment_id=a reason=empty_asr" in message
    assert "samples=320640" in message
    assert results == [RecoveryWork("a", padded_retry="empty", padded_retry_empty=True)]


def test_grid_language_en_duration_60_reports_the_handoff(monkeypatch, caplog):
    _worker, results, saved, failures = _run_empty(monkeypatch, caplog, duration=60, language="en")
    ladder, fault, guard = _split(caplog)
    assert not fault and not guard and len(ladder) == 1
    assert ladder[0].levelno == logging.INFO
    message = ladder[0].getMessage()
    assert "error_class=BatchValidationError stage=assemble_words segment_id=a reason=empty_asr" in message
    assert "samples=960000" in message
    assert results == [RecoveryWork("a", padded_retry="empty", padded_retry_empty=True)]


def test_grid_language_es_duration_7_9_reports_the_handoff(monkeypatch, caplog):
    _worker, results, saved, failures = _run_empty(monkeypatch, caplog, duration=7.9, language="es")
    ladder, fault, guard = _split(caplog)
    assert not fault and not guard and len(ladder) == 1
    assert "samples=126400" in ladder[0].getMessage()
    assert results == [RecoveryWork("a", padded_retry="empty", padded_retry_empty=True)]


def test_grid_language_fr_duration_20_04_reports_the_handoff(monkeypatch, caplog):
    _worker, results, saved, failures = _run_empty(monkeypatch, caplog, duration=20.04, language="fr")
    ladder, fault, guard = _split(caplog)
    assert not fault and not guard and len(ladder) == 1
    assert "samples=320640" in ladder[0].getMessage()
    assert results == [RecoveryWork("a", padded_retry="empty", padded_retry_empty=True)]


def test_grid_language_fr_duration_60_counts_one_failed_unit(monkeypatch, caplog):
    _worker, results, saved, failures = _run_empty(monkeypatch, caplog, duration=60, language="fr")
    ladder, fault, guard = _split(caplog)
    assert not fault and not guard and len(ladder) == 1
    assert _worker.counts["failed"] == 1
    assert not saved


def test_grid_duration_7_9_measured_vad_evidence(monkeypatch, caplog):
    _worker, results, saved, failures = _run_empty(monkeypatch, caplog, duration=7.9)
    ladder, fault, guard = _split(caplog)
    assert not fault and not guard and len(ladder) == 1
    held = results[0].measured_held_vad_speech_seconds
    assert held is not None and abs(held - 0.6) < 1e-6
    assert isinstance(results[0].worker_vad_receipt, dict)


def test_grid_duration_20_04_measured_vad_evidence(monkeypatch, caplog):
    _worker, results, saved, failures = _run_empty(monkeypatch, caplog, duration=20.04)
    ladder, fault, guard = _split(caplog)
    assert not fault and not guard and len(ladder) == 1
    held = results[0].measured_held_vad_speech_seconds
    assert held is not None and abs(held - 0.6) < 1e-6
    assert isinstance(results[0].worker_vad_receipt, dict)


def test_grid_duration_7_9_failure_callback_receives_the_class_name(monkeypatch, caplog):
    seen = []
    _worker, results, saved, failures = _run_empty(monkeypatch, caplog, duration=7.9, on_failure_seen=seen)
    assert seen == [("a", "BatchValidationError")]


def test_grid_duration_20_04_failure_callback_receives_the_class_name(monkeypatch, caplog):
    seen = []
    _worker, results, saved, failures = _run_empty(monkeypatch, caplog, duration=20.04, on_failure_seen=seen)
    assert seen == [("a", "BatchValidationError")]


def test_grid_language_es_duration_2_counts_one_failed_unit(monkeypatch, caplog):
    _worker, results, saved, failures = _run_empty(monkeypatch, caplog, duration=2, language="es")
    ladder, fault, guard = _split(caplog)
    assert not fault and not guard and len(ladder) == 1
    assert _worker.counts["failed"] == 1
    assert not saved


def test_grid_language_fr_duration_2_counts_one_failed_unit(monkeypatch, caplog):
    _worker, results, saved, failures = _run_empty(monkeypatch, caplog, duration=2, language="fr")
    ladder, fault, guard = _split(caplog)
    assert not fault and not guard and len(ladder) == 1
    assert _worker.counts["failed"] == 1
    assert not saved


def test_grid_language_es_duration_2_failure_callback_receives_the_class_name(monkeypatch, caplog):
    seen = []
    _worker, results, saved, failures = _run_empty(monkeypatch, caplog, duration=2, language="es", on_failure_seen=seen)
    assert seen == [("a", "BatchValidationError")]


def test_grid_language_fr_duration_2_failure_callback_receives_the_class_name(monkeypatch, caplog):
    seen = []
    _worker, results, saved, failures = _run_empty(monkeypatch, caplog, duration=2, language="fr", on_failure_seen=seen)
    assert seen == [("a", "BatchValidationError")]
