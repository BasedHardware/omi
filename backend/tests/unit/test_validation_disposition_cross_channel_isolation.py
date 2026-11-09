# Failure-Class: FC-terminal-validation-disposition-misbooked-as-worker-fault
"""Cross-channel isolation at the worker boundary, and the demoted handoff's fields.

The demotion families — the terminal worker-validation disposition, the
language guard, the empty ladder and the kept fault channel — never fire each
other's lines: driving a cell of one family through the real worker produces
exactly that family's channel and no sibling's, with the demoted handoff
carrying the complete diagnostic field set the fault line used to carry, and
a healthy unit booking no disposition line at all.
"""

import logging

import numpy as np

from utils.batch_pipeline.audio import StagedAudioInvalid
from utils.batch_pipeline.contracts import FailedWork, WorkResult, ValidationFailureWork
from utils.batch_pipeline.source_audio import RetainedAudioInvalid, RetainedAudioOutsideAdmittedSource
from utils.batch_pipeline.word_validation import BatchValidationError, ValidationReason
from tests.unit.test_batch_pipeline_worker import Samples, item, setup_worker


def _flags(monkeypatch):
    monkeypatch.delenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", raising=False)
    monkeypatch.setenv("BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED", "true")
    monkeypatch.setenv("BATCH_PIPELINE_DIARIZE_SPEECH_ONLY_ENABLED", "false")
    monkeypatch.setenv("BATCH_PIPELINE_SHORT_SPEECH_SINGLE_ENABLED", "false")


def _run(monkeypatch, caplog, **kwargs):
    _flags(monkeypatch)
    caplog.set_level(logging.INFO)
    worker, provider, saved, decoded, diarized, failures = setup_worker(**kwargs)
    results = worker.process_batch([item()])
    handoff = [
        r.getMessage()
        for r in caplog.records
        if "event=batch_validation_disposition outcome=recovery_handoff" in r.getMessage()
    ]
    fault = [r for r in caplog.records if "event=batch_worker_failed" in r.getMessage()]
    ladder = [r for r in caplog.records if "event=batch_empty_ladder" in r.getMessage()]
    guard = [r for r in caplog.records if "event=batch_language_guard" in r.getMessage()]
    return results, handoff, fault, ladder, guard, failures


def _raising(exc):
    def decode(work):
        raise exc

    return decode


def test_staged_audio_invalid_handoff_carries_the_full_field_set(monkeypatch, caplog):
    """The staged-bytes handoff carries error_class, stage, segment, reason and shape fields."""
    results, handoff, fault, ladder, guard, failures = _run(
        monkeypatch, caplog, decode=_raising(StagedAudioInvalid("staged"))
    )
    assert not fault and not ladder and not guard and len(handoff) == 1
    message = handoff[0]
    assert "error_class=StagedAudioInvalid" in message
    assert "stage=fetch_decode segment_id=a reason=staged_audio_invalid" in message
    assert "samples=" in message and "vad_spans=" in message and "windows=" in message
    assert "asr_words=" in message and "owned_words=" in message


def test_vad_order_handoff_keeps_the_batch_validation_error_class(monkeypatch, caplog):
    """The vad_order handoff keeps the BatchValidationError error_class field."""
    results, handoff, fault, ladder, guard, failures = _run(
        monkeypatch,
        caplog,
        vad=lambda samples: (_ for _ in ()).throw(BatchValidationError(ValidationReason.VAD_ORDER)),
    )
    assert not fault and not ladder and not guard and len(handoff) == 1
    assert "error_class=BatchValidationError stage=vad_windows segment_id=a reason=vad_order" in handoff[0]


def test_vad_bounds_handoff_and_durable_result_agree(monkeypatch, caplog):
    """The vad_bounds handoff line and the ValidationFailureWork carry the same diagnosis."""
    speech = np.full(2 * 16000, 400.0, dtype=np.float32)
    results, handoff, fault, ladder, guard, failures = _run(
        monkeypatch,
        caplog,
        decode=lambda work: speech,
        vad=lambda samples: (_ for _ in ()).throw(BatchValidationError(ValidationReason.VAD_BOUNDS)),
    )
    assert not fault and not ladder and not guard and len(handoff) == 1
    assert "reason=vad_bounds" in handoff[0]
    assert results == [ValidationFailureWork("a", "vad_windows", "vad_bounds")]


def test_admitted_source_refusal_cannot_fire_the_handoff_line(monkeypatch, caplog):
    """The kept admitted-source refusal never books a handoff line."""
    results, handoff, fault, ladder, guard, failures = _run(
        monkeypatch, caplog, decode=_raising(RetainedAudioOutsideAdmittedSource("source"))
    )
    assert not handoff and len(fault) == 1
    assert fault[0].levelno == logging.ERROR
    assert isinstance(results[0], FailedWork)


def test_unclassified_decode_fault_cannot_fire_the_handoff_line(monkeypatch, caplog):
    """A raw decode ValueError keeps the fault channel under the disposition switch."""
    results, handoff, fault, ladder, guard, failures = _run(
        monkeypatch, caplog, decode=_raising(ValueError("synthetic"))
    )
    assert not handoff and len(fault) == 1


def test_trio_handoff_isolated_from_the_sibling_channels(monkeypatch, caplog):
    """The trio's handoff fires no empty-ladder or language-guard line."""
    results, handoff, fault, ladder, guard, failures = _run(
        monkeypatch, caplog, decode=_raising(StagedAudioInvalid("staged"))
    )
    assert len(handoff) == 1 and not ladder and not guard and not fault


def test_vad_nonfinite_handoff_isolated_from_the_sibling_channels(monkeypatch, caplog):
    """vad_nonfinite's handoff fires no sibling line."""
    results, handoff, fault, ladder, guard, failures = _run(
        monkeypatch,
        caplog,
        vad=lambda samples: (_ for _ in ()).throw(BatchValidationError(ValidationReason.VAD_NONFINITE)),
    )
    assert len(handoff) == 1 and not fault and not ladder and not guard


def test_word_clock_handoff_reports_the_closed_verdict(monkeypatch, caplog):
    """A mid-window inverted clock demotes as word_clock at word_clocks."""
    results, handoff, fault, ladder, guard, failures = _run(
        monkeypatch,
        caplog,
        words_providers={
            "parakeet": type(
                "BrokenWords",
                (),
                {
                    "transcribe_batch": lambda self, samples: [
                        [{"word": "hi", "timestamp": [1.0, 0.5]}] for _ in samples
                    ]
                },
            )()
        },
    )
    assert not fault and not ladder and not guard and len(handoff) == 1
    assert "stage=word_clocks segment_id=a reason=word_clock" in handoff[0]


def test_retained_handoff_keeps_the_fault_line_message_shape(monkeypatch, caplog):
    """The retained-bytes handoff keeps the fault line's exact message prefix shape."""
    results, handoff, fault, ladder, guard, failures = _run(
        monkeypatch, caplog, decode=_raising(RetainedAudioInvalid("retained"))
    )
    assert not fault and not ladder and not guard and len(handoff) == 1
    message = handoff[0]
    assert message.startswith(
        "event=batch_validation_disposition outcome=recovery_handoff error_class=RetainedAudioInvalid "
    )
    assert "samples=-1" in message and "vad_spans=-1" in message


def test_duration_mismatch_handoff_names_measured_samples(monkeypatch, caplog):
    """The decoded-extent handoff reports the decoded sample count, not the admitted one."""
    results, handoff, fault, ladder, guard, failures = _run(monkeypatch, caplog, decode=lambda work: Samples(99))
    assert not fault and not ladder and not guard and len(handoff) == 1
    assert "samples=1584000" in handoff[0]


def test_healthy_unit_books_no_disposition_line(monkeypatch, caplog):
    """A healthy unit books no disposition line at all."""
    results, handoff, fault, ladder, guard, failures = _run(monkeypatch, caplog)
    assert not handoff and not fault
    assert isinstance(results[0], WorkResult)
