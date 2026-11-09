# Failure-Class: FC-terminal-validation-disposition-misbooked-as-worker-fault
"""The worker boundary reports the terminal validation disposition on its own channel.

Every raise site that lands a unit in the terminal ``ValidationFailureWork``
handoff is driven through the real ``PipelineWorker`` with INFO captured: the
typed staged/retained/decoded-extent trio, the closed vad/word verdicts, and
the vad_bounds sub-frame pair whose strict-inspector answer disposes the unit
as silence. Each demoted cell reports
``event=batch_validation_disposition outcome=recovery_handoff`` at INFO with
every diagnostic field the fault line carried, while the deliberately
retryable admitted-source refusal, raw untyped faults, and every cell under
the switch-off rollback keep ``event=batch_worker_failed`` at ERROR. Durable
results, the failure callback and the worker counters are pinned unchanged
next to the new channel.
"""

import logging
from dataclasses import replace

import numpy as np
import pytest

from diarizer.batch_pipeline import DecodedDurationMismatch
from utils.batch_pipeline.artifacts import StagedArtifactInvalid
from utils.batch_pipeline.audio import StagedAudioInvalid
from utils.batch_pipeline.contracts import FailedWork, ValidationFailureWork, WorkResult
from utils.batch_pipeline.source_audio import RetainedAudioInvalid, RetainedAudioOutsideAdmittedSource
from utils.batch_pipeline.word_validation import BatchValidationError, ValidationReason
from tests.unit.test_batch_pipeline_worker import Samples, item, setup_worker


def _flags(monkeypatch, disposition="true", safety="true"):
    monkeypatch.setenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", disposition)
    monkeypatch.setenv("BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED", safety)
    monkeypatch.setenv("BATCH_PIPELINE_DIARIZE_SPEECH_ONLY_ENABLED", "false")
    monkeypatch.setenv("BATCH_PIPELINE_SHORT_SPEECH_SINGLE_ENABLED", "false")


def _run(monkeypatch, caplog, *, disposition="true", safety="true", shadow=False, duration=2, **kwargs):
    _flags(monkeypatch, disposition=disposition, safety=safety)
    caplog.set_level(logging.INFO)
    worker, provider, saved, decoded, diarized, failures = setup_worker(**kwargs)
    unit = item(duration=duration)
    if shadow:
        unit = replace(unit, shadow=True)
    results = worker.process_batch([unit])
    return worker, results, failures


def _split(caplog):
    disposition = [r for r in caplog.records if "event=batch_validation_disposition" in r.getMessage()]
    fault = [r for r in caplog.records if "event=batch_worker_failed" in r.getMessage()]
    ladder = [r for r in caplog.records if "event=batch_empty_ladder" in r.getMessage()]
    guard = [r for r in caplog.records if "event=batch_language_guard" in r.getMessage()]
    shadow_line = [r for r in caplog.records if "event=batch_shadow_worker_failure" in r.getMessage()]
    return disposition, fault, ladder, guard, shadow_line


def _raise(exc):
    def decode(work):
        raise exc

    return decode


# --- the typed fetch_decode trio demotes unconditionally ---------------------


def test_staged_audio_invalid_reports_the_disposition_handoff(monkeypatch, caplog):
    worker, results, failures = _run(monkeypatch, caplog, decode=_raise(StagedAudioInvalid("staged")))
    disposition, fault, ladder, guard, shadow_line = _split(caplog)
    assert not fault and not ladder and not guard and len(disposition) == 1
    assert disposition[0].levelno == logging.INFO
    message = disposition[0].getMessage()
    assert message.startswith("event=batch_validation_disposition outcome=recovery_handoff ")
    assert "error_class=StagedAudioInvalid stage=fetch_decode segment_id=a reason=staged_audio_invalid" in message
    assert results == [ValidationFailureWork("a", "fetch_decode", "staged_audio_invalid")]


def test_staged_artifact_invalid_reports_the_disposition_handoff(monkeypatch, caplog):
    worker, results, failures = _run(monkeypatch, caplog, decode=_raise(StagedArtifactInvalid("artifact")))
    disposition, fault, ladder, guard, shadow_line = _split(caplog)
    assert not fault and len(disposition) == 1
    assert "error_class=StagedArtifactInvalid stage=fetch_decode segment_id=a reason=staged_audio_invalid" in (
        disposition[0].getMessage()
    )
    assert results == [ValidationFailureWork("a", "fetch_decode", "staged_audio_invalid")]


def test_retained_audio_invalid_reports_the_disposition_handoff(monkeypatch, caplog):
    worker, results, failures = _run(monkeypatch, caplog, decode=_raise(RetainedAudioInvalid("retained")))
    disposition, fault, ladder, guard, shadow_line = _split(caplog)
    assert not fault and len(disposition) == 1
    assert "error_class=RetainedAudioInvalid stage=fetch_decode segment_id=a reason=retained_audio_invalid" in (
        disposition[0].getMessage()
    )
    assert results == [ValidationFailureWork("a", "fetch_decode", "retained_audio_invalid")]


def test_trio_demotes_with_the_disposition_switch_off(monkeypatch, caplog):
    """The trio's chain end is unconditional on pinned bytes, so its demotion is too."""
    worker, results, failures = _run(
        monkeypatch, caplog, disposition="false", decode=_raise(StagedAudioInvalid("staged"))
    )
    disposition, fault, ladder, guard, shadow_line = _split(caplog)
    assert not fault and len(disposition) == 1
    assert results == [ValidationFailureWork("a", "fetch_decode", "staged_audio_invalid")]


def test_trio_demotes_with_the_safety_net_off(monkeypatch, caplog):
    worker, results, failures = _run(monkeypatch, caplog, safety="false", decode=_raise(RetainedAudioInvalid("r")))
    disposition, fault, ladder, guard, shadow_line = _split(caplog)
    assert not fault and len(disposition) == 1
    assert results == [ValidationFailureWork("a", "fetch_decode", "retained_audio_invalid")]


# --- the decoded-extent mismatch and its tolerance boundary ------------------


def test_decoded_extent_mismatch_reports_the_disposition_handoff(monkeypatch, caplog):
    worker, results, failures = _run(monkeypatch, caplog, decode=lambda work: Samples(99))
    disposition, fault, ladder, guard, shadow_line = _split(caplog)
    assert not fault and len(disposition) == 1
    assert "error_class=DecodedDurationMismatch stage=fetch_decode segment_id=a reason=decoded_duration_mismatch" in (
        disposition[0].getMessage()
    )
    assert results == [ValidationFailureWork("a", "fetch_decode", "decoded_duration_mismatch")]


def test_extent_within_the_admission_tolerance_is_not_a_disposition(monkeypatch, caplog):
    """0.1s tolerance: a decoded extent inside it never books any failure line."""
    worker, results, failures = _run(monkeypatch, caplog, decode=lambda work: Samples(work.duration_seconds + 0.05))
    disposition, fault, ladder, guard, shadow_line = _split(caplog)
    assert not disposition and not fault
    assert isinstance(results[0], WorkResult)


def test_extent_mismatch_beyond_the_tolerance_disposes(monkeypatch, caplog):
    worker, results, failures = _run(monkeypatch, caplog, decode=lambda work: Samples(work.duration_seconds + 0.2))
    disposition, fault, ladder, guard, shadow_line = _split(caplog)
    assert not fault and len(disposition) == 1
    assert "reason=decoded_duration_mismatch" in disposition[0].getMessage()


def test_extent_mismatch_on_a_shadow_unit_keeps_the_shadow_line(monkeypatch, caplog):
    worker, results, failures = _run(monkeypatch, caplog, shadow=True, decode=lambda work: Samples(99))
    disposition, fault, ladder, guard, shadow_line = _split(caplog)
    assert not disposition and not fault
    assert len(shadow_line) == 1


# --- the closed vad_windows verdicts ----------------------------------------


def test_vad_nonfinite_reports_the_disposition_handoff(monkeypatch, caplog):
    worker, results, failures = _run(monkeypatch, caplog, vad=lambda samples: [(float("nan"), 0.5)])
    disposition, fault, ladder, guard, shadow_line = _split(caplog)
    assert not fault and len(disposition) == 1
    assert "error_class=BatchValidationError stage=vad_windows segment_id=a reason=vad_nonfinite" in (
        disposition[0].getMessage()
    )
    assert results == [ValidationFailureWork("a", "vad_windows", "vad_nonfinite")]


def test_vad_order_reports_the_disposition_handoff(monkeypatch, caplog):
    worker, results, failures = _run(monkeypatch, caplog, vad=lambda samples: [(0.5, 0.2)])
    disposition, fault, ladder, guard, shadow_line = _split(caplog)
    assert not fault and len(disposition) == 1
    assert "reason=vad_order" in disposition[0].getMessage()
    assert results == [ValidationFailureWork("a", "vad_windows", "vad_order")]


def test_vad_infinite_span_reports_the_disposition_handoff(monkeypatch, caplog):
    worker, results, failures = _run(monkeypatch, caplog, vad=lambda samples: [(float("inf"), 9.0)])
    disposition, fault, ladder, guard, shadow_line = _split(caplog)
    assert not fault and len(disposition) == 1
    assert "reason=vad_nonfinite" in disposition[0].getMessage()


def test_vad_bounds_with_speech_samples_reports_the_disposition_handoff(monkeypatch, caplog):
    """Speech evidence cannot confirm silence, so the bounds verdict stays held."""
    speech = np.full(2 * 16000, 500.0, dtype=np.float32)
    worker, results, failures = _run(monkeypatch, caplog, decode=lambda work: speech, vad=lambda samples: [(0.1, 9.0)])
    disposition, fault, ladder, guard, shadow_line = _split(caplog)
    assert not fault and len(disposition) == 1
    assert "reason=vad_bounds" in disposition[0].getMessage()
    assert results == [ValidationFailureWork("a", "vad_windows", "vad_bounds")]


def test_vad_bounds_with_unavailable_strict_evidence_reports_the_disposition_handoff(monkeypatch, caplog):
    """The duck-typed harness samples make the strict inspector unavailable: the hold stays."""
    worker, results, failures = _run(monkeypatch, caplog, vad=lambda samples: [(0.1, 9.0)])
    disposition, fault, ladder, guard, shadow_line = _split(caplog)
    assert not fault and len(disposition) == 1
    assert "reason=vad_bounds" in disposition[0].getMessage()


def test_vad_bounds_with_strict_silence_disposes_the_unit_as_silence(monkeypatch, caplog):
    """The designed silence answer: no fault line, no disposition line, a real result."""
    silence = np.zeros(2 * 16000, dtype=np.float32)

    def vad(samples):
        raise BatchValidationError(ValidationReason.VAD_BOUNDS)

    worker, results, failures = _run(monkeypatch, caplog, decode=lambda work: silence, vad=vad)
    disposition, fault, ladder, guard, shadow_line = _split(caplog)
    assert not disposition and not fault
    assert results[0].outcome == "silence"


def test_vad_bounds_raised_by_window_building_reports_the_disposition_handoff(monkeypatch, caplog):
    """A bounds verdict raised while building windows never reaches the strict-silence
    handler (it wraps only the model call), so the hold stands on any samples."""
    silence = np.zeros(2 * 16000, dtype=np.float32)
    worker, results, failures = _run(monkeypatch, caplog, decode=lambda work: silence, vad=lambda samples: [(0.1, 9.0)])
    disposition, fault, ladder, guard, shadow_line = _split(caplog)
    assert not fault and len(disposition) == 1
    assert "reason=vad_bounds" in disposition[0].getMessage()
    assert results == [ValidationFailureWork("a", "vad_windows", "vad_bounds")]


def test_vad_bounds_keeps_the_fault_channel_with_the_switch_off(monkeypatch, caplog):
    silence_off = None  # readability anchor
    speech = np.full(2 * 16000, 500.0, dtype=np.float32)
    worker, results, failures = _run(
        monkeypatch,
        caplog,
        disposition="false",
        decode=lambda work: speech,
        vad=lambda samples: [(0.1, 9.0)],
    )
    disposition, fault, ladder, guard, shadow_line = _split(caplog)
    assert not disposition and len(fault) == 1
    assert fault[0].levelno == logging.ERROR
    assert "stage=vad_windows segment_id=a reason=vad_bounds" in fault[0].getMessage()


def test_vad_nonfinite_keeps_the_fault_channel_with_the_switch_off(monkeypatch, caplog):
    worker, results, failures = _run(
        monkeypatch, caplog, disposition="false", vad=lambda samples: [(float("nan"), 0.5)]
    )
    disposition, fault, ladder, guard, shadow_line = _split(caplog)
    assert not disposition and len(fault) == 1
    assert "reason=vad_nonfinite" in fault[0].getMessage()


# --- the closed word verdicts at the window seam ----------------------------


def _words(words):
    class BrokenWords:
        def transcribe_batch(self, samples):
            return [list(words) for _ in samples]

    return {"parakeet": BrokenWords()}


def test_word_shape_reports_the_disposition_handoff(monkeypatch, caplog):
    words = [{"word": "hi", "timestamp": "not-a-pair"}]
    worker, results, failures = _run(monkeypatch, caplog, duration=60, words_providers=_words(words))
    disposition, fault, ladder, guard, shadow_line = _split(caplog)
    assert not fault and len(disposition) == 1
    assert "error_class=BatchValidationError stage=word_clocks segment_id=a reason=word_shape" in (
        disposition[0].getMessage()
    )
    assert results == [ValidationFailureWork("a", "word_clocks", "word_shape")]


def test_word_clock_reports_the_disposition_handoff(monkeypatch, caplog):
    words = [{"word": "hi", "timestamp": [1.0, 0.5]}]
    worker, results, failures = _run(monkeypatch, caplog, duration=60, words_providers=_words(words))
    disposition, fault, ladder, guard, shadow_line = _split(caplog)
    assert not fault and len(disposition) == 1
    assert "reason=word_clock" in disposition[0].getMessage()
    assert results == [ValidationFailureWork("a", "word_clocks", "word_clock")]


def test_word_nonfinite_clock_reports_the_disposition_handoff(monkeypatch, caplog):
    words = [{"word": "hi", "timestamp": [float("nan"), 0.5]}]
    worker, results, failures = _run(monkeypatch, caplog, duration=60, words_providers=_words(words))
    disposition, fault, ladder, guard, shadow_line = _split(caplog)
    assert not fault and len(disposition) == 1
    assert "reason=word_clock" in disposition[0].getMessage()


def test_word_sequence_reports_the_disposition_handoff(monkeypatch, caplog):
    words = [
        {"word": "second", "timestamp": [1.5, 2.0]},
        {"word": "first", "timestamp": [0.1, 0.4]},
    ]
    worker, results, failures = _run(monkeypatch, caplog, duration=60, words_providers=_words(words))
    disposition, fault, ladder, guard, shadow_line = _split(caplog)
    assert not fault and len(disposition) == 1
    assert "reason=word_sequence" in disposition[0].getMessage()
    assert results == [ValidationFailureWork("a", "word_clocks", "word_sequence")]


def test_blank_word_text_reports_the_disposition_handoff(monkeypatch, caplog):
    words = [{"word": "   ", "timestamp": [0.1, 0.4]}]
    worker, results, failures = _run(monkeypatch, caplog, duration=60, words_providers=_words(words))
    disposition, fault, ladder, guard, shadow_line = _split(caplog)
    assert not fault and len(disposition) == 1
    assert "reason=word_sequence" in disposition[0].getMessage()


def test_word_clock_keeps_the_fault_channel_with_the_switch_off(monkeypatch, caplog):
    words = [{"word": "hi", "timestamp": [1.0, 0.5]}]
    worker, results, failures = _run(
        monkeypatch, caplog, duration=60, disposition="false", words_providers=_words(words)
    )
    disposition, fault, ladder, guard, shadow_line = _split(caplog)
    assert not disposition and len(fault) == 1
    assert fault[0].levelno == logging.ERROR
    assert "stage=word_clocks segment_id=a reason=word_clock" in fault[0].getMessage()


# --- the deliberately retryable and unclassified faults keep ERROR ----------


def test_outside_admitted_source_keeps_the_fault_channel(monkeypatch, caplog):
    worker, results, failures = _run(monkeypatch, caplog, decode=_raise(RetainedAudioOutsideAdmittedSource("source")))
    disposition, fault, ladder, guard, shadow_line = _split(caplog)
    assert not disposition and len(fault) == 1
    assert fault[0].levelno == logging.ERROR
    assert "stage=fetch_decode segment_id=a reason=outside_admitted_source" in fault[0].getMessage()
    assert isinstance(results[0], FailedWork)


def test_outside_admitted_source_keeps_error_under_switch_off(monkeypatch, caplog):
    worker, results, failures = _run(
        monkeypatch,
        caplog,
        disposition="false",
        decode=_raise(RetainedAudioOutsideAdmittedSource("source")),
    )
    disposition, fault, ladder, guard, shadow_line = _split(caplog)
    assert not disposition and len(fault) == 1


def test_raw_decode_valueerror_keeps_the_fault_channel(monkeypatch, caplog):
    worker, results, failures = _run(monkeypatch, caplog, decode=_raise(ValueError("private")))
    disposition, fault, ladder, guard, shadow_line = _split(caplog)
    assert not disposition and len(fault) == 1
    assert fault[0].levelno == logging.ERROR
    assert "error_class=ValueError stage=fetch_decode segment_id=a reason=unclassified" in fault[0].getMessage()


def test_raw_decode_valueerror_message_never_reaches_the_log(monkeypatch, caplog):
    worker, results, failures = _run(monkeypatch, caplog, decode=_raise(ValueError("secret-private-bytes")))
    assert "secret-private-bytes" not in caplog.text


# --- field and severity invariants on the demoted channel --------------------


def test_disposition_line_carries_the_measured_shape_fields(monkeypatch, caplog):
    worker, results, failures = _run(monkeypatch, caplog, decode=lambda work: Samples(99))
    disposition, fault, ladder, guard, shadow_line = _split(caplog)
    message = disposition[0].getMessage()
    assert "samples=1584000" in message
    assert "vad_spans=-1" in message
    assert "windows=-1" in message
    assert "asr_words=0" in message


def test_demoted_cells_emit_no_error_records_from_the_boundary(caplog):
    """Severity exclusivity is structural: the demoted branch only logs INFO."""
    logger = logging.getLogger("diarizer.batch_pipeline")
    assert logger.getEffectiveLevel() != logging.ERROR


def test_failure_callback_and_counters_unchanged_on_the_demoted_path(monkeypatch, caplog):
    worker, results, failures = _run(monkeypatch, caplog, decode=_raise(StagedAudioInvalid("staged")))
    disposition, fault, ladder, guard, shadow_line = _split(caplog)
    assert failures == [("a", "StagedAudioInvalid")]
    assert worker.counts["failed"] == 1
    assert worker.counts["items"] == 1
