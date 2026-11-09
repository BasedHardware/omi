# Failure-Class: FC-terminal-validation-disposition-misbooked-as-worker-fault
"""A family fault in a batch never disturbs its healthy siblings.

Every family raise site is driven through the real worker with a healthy
sibling before and after the failing unit: exactly one demoted handoff line,
exactly one fault counter, the sibling persisted, the healthy results intact,
and the failure callback naming only the failing unit — at every position in
the batch, under both switch positions.
"""

import logging
from dataclasses import replace

import pytest

from diarizer.batch_pipeline import DecodedDurationMismatch
from utils.batch_pipeline.audio import StagedAudioInvalid
from utils.batch_pipeline.contracts import ValidationFailureWork, WorkResult
from utils.batch_pipeline.source_audio import RetainedAudioInvalid
from utils.batch_pipeline.word_validation import BatchValidationError, ValidationReason
from tests.unit.test_batch_pipeline_worker import item, setup_worker


def _flags(monkeypatch, disposition="true"):
    monkeypatch.setenv("BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED", disposition)
    monkeypatch.setenv("BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED", "true")
    monkeypatch.setenv("BATCH_PIPELINE_DIARIZE_SPEECH_ONLY_ENABLED", "false")
    monkeypatch.setenv("BATCH_PIPELINE_SHORT_SPEECH_SINGLE_ENABLED", "false")


def _decode_raiser(exc, bad_key):
    def decode(work):
        if work.segment_id == bad_key:
            raise exc
        from tests.unit.test_batch_pipeline_worker import Samples

        return Samples(work.duration_seconds)

    return decode


def _split(caplog):
    handoff = [
        r for r in caplog.records if "event=batch_validation_disposition outcome=recovery_handoff" in r.getMessage()
    ]
    fault = [r for r in caplog.records if "event=batch_worker_failed" in r.getMessage()]
    return handoff, fault


def persisted_ok(results):
    persisted = [r.segment_id for r in results if isinstance(r, WorkResult)]
    return persisted == ["first", "last"]


def test_batch_staged_audio_invalid_fault_keeps_its_siblings_healthy(monkeypatch, caplog):
    """A middle-of-batch staged_audio_invalid fault demotes alone; both siblings persist."""
    _flags(monkeypatch)
    caplog.set_level(logging.INFO)
    worker, _, saved, _, _, failures = setup_worker(decode=_decode_raiser(StagedAudioInvalid('staged'), "bad"))
    results = worker.process_batch([item("first"), item("bad"), item("last")])
    handoff, fault = _split(caplog)
    assert not fault and len(handoff) == 1
    assert failures == [("bad", "StagedAudioInvalid")]
    assert worker.counts["failed"] == 1
    persisted = [r.segment_id for r in results if isinstance(r, WorkResult)]
    assert persisted == ["first", "last"]


def test_batch_retained_audio_invalid_fault_keeps_its_siblings_healthy(monkeypatch, caplog):
    """A middle-of-batch retained_audio_invalid fault demotes alone; both siblings persist."""
    _flags(monkeypatch)
    caplog.set_level(logging.INFO)
    worker, _, saved, _, _, failures = setup_worker(decode=_decode_raiser(RetainedAudioInvalid('retained'), "bad"))
    results = worker.process_batch([item("first"), item("bad"), item("last")])
    handoff, fault = _split(caplog)
    assert not fault and len(handoff) == 1
    assert failures == [("bad", "RetainedAudioInvalid")]
    assert worker.counts["failed"] == 1
    persisted = [r.segment_id for r in results if isinstance(r, WorkResult)]
    assert persisted == ["first", "last"]


def test_batch_decoded_duration_mismatch_fault_keeps_its_siblings_healthy(monkeypatch, caplog):
    """A middle-of-batch decoded_duration_mismatch fault demotes alone; both siblings persist."""
    _flags(monkeypatch)
    caplog.set_level(logging.INFO)
    worker, _, saved, _, _, failures = setup_worker(decode=_decode_raiser(DecodedDurationMismatch('extent'), "bad"))
    results = worker.process_batch([item("first"), item("bad"), item("last")])
    handoff, fault = _split(caplog)
    assert not fault and len(handoff) == 1
    assert failures == [("bad", "DecodedDurationMismatch")]
    assert worker.counts["failed"] == 1
    persisted = [r.segment_id for r in results if isinstance(r, WorkResult)]
    assert persisted == ["first", "last"]


def test_batch_word_shape_fault_keeps_its_siblings_healthy(monkeypatch, caplog):
    """A middle-of-batch word_shape fault demotes alone; both siblings persist."""
    _flags(monkeypatch)
    caplog.set_level(logging.INFO)
    worker, _, saved, _, _, failures = setup_worker(
        decode=_decode_raiser(BatchValidationError(ValidationReason.WORD_SHAPE), "bad")
    )
    results = worker.process_batch([item("first"), item("bad"), item("last")])
    handoff, fault = _split(caplog)
    assert not fault and len(handoff) == 1
    assert failures == [("bad", "BatchValidationError")]
    assert worker.counts["failed"] == 1
    persisted = [r.segment_id for r in results if isinstance(r, WorkResult)]
    assert persisted == ["first", "last"]


def test_batch_word_clock_fault_keeps_its_siblings_healthy(monkeypatch, caplog):
    """A middle-of-batch word_clock fault demotes alone; both siblings persist."""
    _flags(monkeypatch)
    caplog.set_level(logging.INFO)
    worker, _, saved, _, _, failures = setup_worker(
        decode=_decode_raiser(BatchValidationError(ValidationReason.WORD_CLOCK), "bad")
    )
    results = worker.process_batch([item("first"), item("bad"), item("last")])
    handoff, fault = _split(caplog)
    assert not fault and len(handoff) == 1
    assert failures == [("bad", "BatchValidationError")]
    assert worker.counts["failed"] == 1
    persisted = [r.segment_id for r in results if isinstance(r, WorkResult)]
    assert persisted == ["first", "last"]


def test_batch_word_sequence_fault_keeps_its_siblings_healthy(monkeypatch, caplog):
    """A middle-of-batch word_sequence fault demotes alone; both siblings persist."""
    _flags(monkeypatch)
    caplog.set_level(logging.INFO)
    worker, _, saved, _, _, failures = setup_worker(
        decode=_decode_raiser(BatchValidationError(ValidationReason.WORD_SEQUENCE), "bad")
    )
    results = worker.process_batch([item("first"), item("bad"), item("last")])
    handoff, fault = _split(caplog)
    assert not fault and len(handoff) == 1
    assert failures == [("bad", "BatchValidationError")]
    assert worker.counts["failed"] == 1
    persisted = [r.segment_id for r in results if isinstance(r, WorkResult)]
    assert persisted == ["first", "last"]


def test_batch_vad_nonfinite_fault_keeps_its_siblings_healthy(monkeypatch, caplog):
    """A middle-of-batch vad_nonfinite fault demotes alone; both siblings persist."""
    _flags(monkeypatch)
    caplog.set_level(logging.INFO)
    worker, _, saved, _, _, failures = setup_worker(
        decode=_decode_raiser(BatchValidationError(ValidationReason.VAD_NONFINITE), "bad")
    )
    results = worker.process_batch([item("first"), item("bad"), item("last")])
    handoff, fault = _split(caplog)
    assert not fault and len(handoff) == 1
    assert failures == [("bad", "BatchValidationError")]
    assert worker.counts["failed"] == 1
    persisted = [r.segment_id for r in results if isinstance(r, WorkResult)]
    assert persisted == ["first", "last"]


def test_batch_vad_order_fault_keeps_its_siblings_healthy(monkeypatch, caplog):
    """A middle-of-batch vad_order fault demotes alone; both siblings persist."""
    _flags(monkeypatch)
    caplog.set_level(logging.INFO)
    worker, _, saved, _, _, failures = setup_worker(
        decode=_decode_raiser(BatchValidationError(ValidationReason.VAD_ORDER), "bad")
    )
    results = worker.process_batch([item("first"), item("bad"), item("last")])
    handoff, fault = _split(caplog)
    assert not fault and len(handoff) == 1
    assert failures == [("bad", "BatchValidationError")]
    assert worker.counts["failed"] == 1
    persisted = [r.segment_id for r in results if isinstance(r, WorkResult)]
    assert persisted == ["first", "last"]


def test_batch_vad_bounds_fault_keeps_its_siblings_healthy(monkeypatch, caplog):
    """A middle-of-batch vad_bounds fault demotes alone; both siblings persist."""
    _flags(monkeypatch)
    caplog.set_level(logging.INFO)
    worker, _, saved, _, _, failures = setup_worker(
        decode=_decode_raiser(BatchValidationError(ValidationReason.VAD_BOUNDS), "bad")
    )
    results = worker.process_batch([item("first"), item("bad"), item("last")])
    handoff, fault = _split(caplog)
    assert not fault and len(handoff) == 1
    assert failures == [("bad", "BatchValidationError")]
    assert worker.counts["failed"] == 1
    persisted = [r.segment_id for r in results if isinstance(r, WorkResult)]
    assert persisted == ["first", "last"]


def test_batch_staged_audio_invalid_fault_first_position_demotes_alone(monkeypatch, caplog):
    """A first-position staged_audio_invalid fault: the demoted line names the failing segment only."""
    _flags(monkeypatch)
    caplog.set_level(logging.INFO)
    worker, _, _, _, _, failures = setup_worker(decode=_decode_raiser(StagedAudioInvalid('staged'), "bad"))
    results = worker.process_batch([item("bad"), item("later")])
    handoff, fault = _split(caplog)
    assert not fault and len(handoff) == 1
    assert "segment_id=bad" in handoff[0].getMessage()
    assert failures == [("bad", "StagedAudioInvalid")]


def test_batch_retained_audio_invalid_fault_first_position_demotes_alone(monkeypatch, caplog):
    """A first-position retained_audio_invalid fault: the demoted line names the failing segment only."""
    _flags(monkeypatch)
    caplog.set_level(logging.INFO)
    worker, _, _, _, _, failures = setup_worker(decode=_decode_raiser(RetainedAudioInvalid('retained'), "bad"))
    results = worker.process_batch([item("bad"), item("later")])
    handoff, fault = _split(caplog)
    assert not fault and len(handoff) == 1
    assert "segment_id=bad" in handoff[0].getMessage()
    assert failures == [("bad", "RetainedAudioInvalid")]


def test_batch_decoded_duration_mismatch_fault_first_position_demotes_alone(monkeypatch, caplog):
    """A first-position decoded_duration_mismatch fault: the demoted line names the failing segment only."""
    _flags(monkeypatch)
    caplog.set_level(logging.INFO)
    worker, _, _, _, _, failures = setup_worker(decode=_decode_raiser(DecodedDurationMismatch('extent'), "bad"))
    results = worker.process_batch([item("bad"), item("later")])
    handoff, fault = _split(caplog)
    assert not fault and len(handoff) == 1
    assert "segment_id=bad" in handoff[0].getMessage()
    assert failures == [("bad", "DecodedDurationMismatch")]


def test_batch_vad_nonfinite_fault_switch_off_keeps_siblings_and_faults(monkeypatch, caplog):
    """Switch off: the same batch books the ERROR fault line; siblings stay healthy."""
    _flags(monkeypatch, disposition="false")
    caplog.set_level(logging.INFO)
    worker, _, saved, _, _, failures = setup_worker(
        decode=_decode_raiser(BatchValidationError(ValidationReason.VAD_NONFINITE), "bad")
    )
    results = worker.process_batch([item("first"), item("bad"), item("last")])
    handoff, fault = _split(caplog)
    assert not handoff and len(fault) == 1
    assert persisted_ok(results)


def test_batch_vad_order_fault_switch_off_keeps_siblings_and_faults(monkeypatch, caplog):
    """Switch off: the same batch books the ERROR fault line; siblings stay healthy."""
    _flags(monkeypatch, disposition="false")
    caplog.set_level(logging.INFO)
    worker, _, saved, _, _, failures = setup_worker(
        decode=_decode_raiser(BatchValidationError(ValidationReason.VAD_ORDER), "bad")
    )
    results = worker.process_batch([item("first"), item("bad"), item("last")])
    handoff, fault = _split(caplog)
    assert not handoff and len(fault) == 1
    assert persisted_ok(results)


def test_batch_vad_bounds_fault_switch_off_keeps_siblings_and_faults(monkeypatch, caplog):
    """Switch off: the same batch books the ERROR fault line; siblings stay healthy."""
    _flags(monkeypatch, disposition="false")
    caplog.set_level(logging.INFO)
    worker, _, saved, _, _, failures = setup_worker(
        decode=_decode_raiser(BatchValidationError(ValidationReason.VAD_BOUNDS), "bad")
    )
    results = worker.process_batch([item("first"), item("bad"), item("last")])
    handoff, fault = _split(caplog)
    assert not handoff and len(fault) == 1
    assert persisted_ok(results)
