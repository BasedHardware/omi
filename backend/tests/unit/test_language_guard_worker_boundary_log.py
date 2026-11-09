"""The worker boundary reports the language-guard redrive instead of a worker fault.

A BatchValidationError with the unsupported_language reason is the designed redrive handoff: typed refusal, terminal chain end, fenced recovery lane waiting. The finish() logging loop reports it as event=batch_language_guard outcome=redrive_held at INFO and books nothing on the fault channel. Every other typed reason, every typed terminal class, and every generic exception keeps event=batch_worker_failed at ERROR. Durable worker outcomes, counters, and the failure callback are pinned unchanged next to the new line.

Failure-Class: FC-language-guard-redrive-misclassified-as-worker-fault
"""

import logging
from dataclasses import replace
from unittest.mock import Mock

import pytest

from diarizer.batch_pipeline import DecodedDurationMismatch
from utils.batch_pipeline.artifacts import StagedArtifactInvalid
from utils.batch_pipeline.audio import StagedAudioInvalid
from utils.batch_pipeline.contracts import ValidationFailureWork
from utils.batch_pipeline.source_audio import RetainedAudioInvalid
from utils.batch_pipeline.word_validation import BatchValidationError, ValidationReason
from tests.unit.test_batch_pipeline_worker import Samples, item, setup_worker

GUARD = ValidationReason.UNSUPPORTED_LANGUAGE


def _env(monkeypatch, disposition='true', safety='false'):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', safety)
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', disposition)
    monkeypatch.setenv('BATCH_PIPELINE_DIARIZE_SPEECH_ONLY_ENABLED', 'false')
    monkeypatch.setenv('BATCH_PIPELINE_SHORT_SPEECH_SINGLE_ENABLED', 'false')


def _run(
    monkeypatch,
    caplog,
    *,
    language='vi',
    vad=None,
    decode=None,
    shadow=False,
    disposition='true',
    safety='false',
    duration=2,
    key='a',
    on_failure=None,
):
    _env(monkeypatch, disposition, safety)
    caplog.set_level(logging.INFO)
    kwargs = {}
    if vad is not None:
        kwargs['vad'] = vad
    if decode is not None:
        kwargs['decode'] = decode
    if on_failure is not None:
        kwargs['on_failure'] = on_failure
    worker, words, saved, decoded, diarized, failures = setup_worker(language_of=lambda _: language, **kwargs)
    unit = item(key, duration)
    if shadow:
        unit = replace(unit, shadow=True)
    results = worker.process_batch([unit])
    guard = [r for r in caplog.records if 'event=batch_language_guard' in r.getMessage()]
    fault = [r for r in caplog.records if 'event=batch_worker_failed' in r.getMessage()]
    return worker, results, words, saved, guard, fault


class NoisyGuard(BatchValidationError):
    def __str__(self):
        return 'SECRET-AUDIO-BYTES ' + super().__str__()


def test_guard_vad_windows_vi_lang_1s_demotes_to_transition(monkeypatch, caplog):
    """The serial language barrier at vad_windows (vi language, 1s) reports the redrive."""
    caplog.set_level(logging.INFO)
    worker, results, words, saved, guard, fault = _run(monkeypatch, caplog, language='vi', duration=1)
    assert len(guard) == 1 and not fault
    assert guard[0].levelno == logging.INFO
    assert 'outcome=redrive_held' in guard[0].getMessage()
    assert 'stage=vad_windows' in guard[0].getMessage() and 'reason=unsupported_language' in guard[0].getMessage()
    assert 'error_class=BatchValidationError' in guard[0].getMessage()
    assert 'samples=16000' in guard[0].getMessage() and 'vad_spans=1' in guard[0].getMessage()
    assert 'asr_words=0' in guard[0].getMessage() and 'owned_words=0' in guard[0].getMessage()
    assert len(results) == 1 and isinstance(results[0], ValidationFailureWork)
    assert (results[0].stage, results[0].reason) == ('vad_windows', 'unsupported_language')
    assert not words.calls and not saved
    assert worker.counts["failed"] == 1


def test_guard_vad_windows_vi_lang_2s_demotes_to_transition(monkeypatch, caplog):
    """The serial language barrier at vad_windows (vi language, 2s) reports the redrive."""
    caplog.set_level(logging.INFO)
    worker, results, words, saved, guard, fault = _run(monkeypatch, caplog, language='vi', duration=2)
    assert len(guard) == 1 and not fault
    assert guard[0].levelno == logging.INFO
    assert 'outcome=redrive_held' in guard[0].getMessage()
    assert 'stage=vad_windows' in guard[0].getMessage() and 'reason=unsupported_language' in guard[0].getMessage()
    assert 'error_class=BatchValidationError' in guard[0].getMessage()
    assert 'samples=32000' in guard[0].getMessage() and 'vad_spans=1' in guard[0].getMessage()
    assert 'asr_words=0' in guard[0].getMessage() and 'owned_words=0' in guard[0].getMessage()
    assert len(results) == 1 and isinstance(results[0], ValidationFailureWork)
    assert (results[0].stage, results[0].reason) == ('vad_windows', 'unsupported_language')
    assert not words.calls and not saved
    assert worker.counts["failed"] == 1


def test_guard_vad_windows_vi_lang_4s_demotes_to_transition(monkeypatch, caplog):
    """The serial language barrier at vad_windows (vi language, 4s) reports the redrive."""
    caplog.set_level(logging.INFO)
    worker, results, words, saved, guard, fault = _run(monkeypatch, caplog, language='vi', duration=4)
    assert len(guard) == 1 and not fault
    assert guard[0].levelno == logging.INFO
    assert 'outcome=redrive_held' in guard[0].getMessage()
    assert 'stage=vad_windows' in guard[0].getMessage() and 'reason=unsupported_language' in guard[0].getMessage()
    assert 'error_class=BatchValidationError' in guard[0].getMessage()
    assert 'samples=64000' in guard[0].getMessage() and 'vad_spans=1' in guard[0].getMessage()
    assert 'asr_words=0' in guard[0].getMessage() and 'owned_words=0' in guard[0].getMessage()
    assert len(results) == 1 and isinstance(results[0], ValidationFailureWork)
    assert (results[0].stage, results[0].reason) == ('vad_windows', 'unsupported_language')
    assert not words.calls and not saved
    assert worker.counts["failed"] == 1


def test_guard_vad_windows_vi_lang_30s_demotes_to_transition(monkeypatch, caplog):
    """The serial language barrier at vad_windows (vi language, 30s) reports the redrive."""
    caplog.set_level(logging.INFO)
    worker, results, words, saved, guard, fault = _run(monkeypatch, caplog, language='vi', duration=30)
    assert len(guard) == 1 and not fault
    assert guard[0].levelno == logging.INFO
    assert 'outcome=redrive_held' in guard[0].getMessage()
    assert 'stage=vad_windows' in guard[0].getMessage() and 'reason=unsupported_language' in guard[0].getMessage()
    assert 'error_class=BatchValidationError' in guard[0].getMessage()
    assert 'samples=480000' in guard[0].getMessage() and 'vad_spans=1' in guard[0].getMessage()
    assert 'asr_words=0' in guard[0].getMessage() and 'owned_words=0' in guard[0].getMessage()
    assert len(results) == 1 and isinstance(results[0], ValidationFailureWork)
    assert (results[0].stage, results[0].reason) == ('vad_windows', 'unsupported_language')
    assert not words.calls and not saved
    assert worker.counts["failed"] == 1


def test_guard_vad_windows_none_lang_1s_demotes_to_transition(monkeypatch, caplog):
    """The serial language barrier at vad_windows (unknown language, 1s) reports the redrive."""
    caplog.set_level(logging.INFO)
    worker, results, words, saved, guard, fault = _run(monkeypatch, caplog, language=None, duration=1)
    assert len(guard) == 1 and not fault
    assert guard[0].levelno == logging.INFO
    assert 'outcome=redrive_held' in guard[0].getMessage()
    assert 'stage=vad_windows' in guard[0].getMessage() and 'reason=unsupported_language' in guard[0].getMessage()
    assert 'error_class=BatchValidationError' in guard[0].getMessage()
    assert 'samples=16000' in guard[0].getMessage() and 'vad_spans=1' in guard[0].getMessage()
    assert 'asr_words=0' in guard[0].getMessage() and 'owned_words=0' in guard[0].getMessage()
    assert len(results) == 1 and isinstance(results[0], ValidationFailureWork)
    assert (results[0].stage, results[0].reason) == ('vad_windows', 'unsupported_language')
    assert not words.calls and not saved
    assert worker.counts["failed"] == 1


def test_guard_vad_windows_none_lang_2s_demotes_to_transition(monkeypatch, caplog):
    """The serial language barrier at vad_windows (unknown language, 2s) reports the redrive."""
    caplog.set_level(logging.INFO)
    worker, results, words, saved, guard, fault = _run(monkeypatch, caplog, language=None, duration=2)
    assert len(guard) == 1 and not fault
    assert guard[0].levelno == logging.INFO
    assert 'outcome=redrive_held' in guard[0].getMessage()
    assert 'stage=vad_windows' in guard[0].getMessage() and 'reason=unsupported_language' in guard[0].getMessage()
    assert 'error_class=BatchValidationError' in guard[0].getMessage()
    assert 'samples=32000' in guard[0].getMessage() and 'vad_spans=1' in guard[0].getMessage()
    assert 'asr_words=0' in guard[0].getMessage() and 'owned_words=0' in guard[0].getMessage()
    assert len(results) == 1 and isinstance(results[0], ValidationFailureWork)
    assert (results[0].stage, results[0].reason) == ('vad_windows', 'unsupported_language')
    assert not words.calls and not saved
    assert worker.counts["failed"] == 1


def test_guard_vad_windows_none_lang_4s_demotes_to_transition(monkeypatch, caplog):
    """The serial language barrier at vad_windows (unknown language, 4s) reports the redrive."""
    caplog.set_level(logging.INFO)
    worker, results, words, saved, guard, fault = _run(monkeypatch, caplog, language=None, duration=4)
    assert len(guard) == 1 and not fault
    assert guard[0].levelno == logging.INFO
    assert 'outcome=redrive_held' in guard[0].getMessage()
    assert 'stage=vad_windows' in guard[0].getMessage() and 'reason=unsupported_language' in guard[0].getMessage()
    assert 'error_class=BatchValidationError' in guard[0].getMessage()
    assert 'samples=64000' in guard[0].getMessage() and 'vad_spans=1' in guard[0].getMessage()
    assert 'asr_words=0' in guard[0].getMessage() and 'owned_words=0' in guard[0].getMessage()
    assert len(results) == 1 and isinstance(results[0], ValidationFailureWork)
    assert (results[0].stage, results[0].reason) == ('vad_windows', 'unsupported_language')
    assert not words.calls and not saved
    assert worker.counts["failed"] == 1


def test_guard_vad_windows_none_lang_30s_demotes_to_transition(monkeypatch, caplog):
    """The serial language barrier at vad_windows (unknown language, 30s) reports the redrive."""
    caplog.set_level(logging.INFO)
    worker, results, words, saved, guard, fault = _run(monkeypatch, caplog, language=None, duration=30)
    assert len(guard) == 1 and not fault
    assert guard[0].levelno == logging.INFO
    assert 'outcome=redrive_held' in guard[0].getMessage()
    assert 'stage=vad_windows' in guard[0].getMessage() and 'reason=unsupported_language' in guard[0].getMessage()
    assert 'error_class=BatchValidationError' in guard[0].getMessage()
    assert 'samples=480000' in guard[0].getMessage() and 'vad_spans=1' in guard[0].getMessage()
    assert 'asr_words=0' in guard[0].getMessage() and 'owned_words=0' in guard[0].getMessage()
    assert len(results) == 1 and isinstance(results[0], ValidationFailureWork)
    assert (results[0].stage, results[0].reason) == ('vad_windows', 'unsupported_language')
    assert not words.calls and not saved
    assert worker.counts["failed"] == 1


def test_guard_fetch_decode_2s_demotes_to_transition(monkeypatch, caplog):
    """A guard refusal at the decode boundary reports the transition with the decode stage."""
    caplog.set_level(logging.INFO)

    def decode(work):
        raise BatchValidationError(GUARD)

    worker, results, words, saved, guard, fault = _run(monkeypatch, caplog, decode=decode, duration=2)
    assert len(guard) == 1 and not fault
    assert guard[0].levelno == logging.INFO
    assert 'stage=fetch_decode' in guard[0].getMessage()
    assert 'samples=-1' in guard[0].getMessage() and 'vad_spans=-1' in guard[0].getMessage()
    assert isinstance(results[0], ValidationFailureWork)
    assert (results[0].stage, results[0].reason) == ('fetch_decode', 'unsupported_language')
    assert worker.counts["failed"] == 1


def test_guard_fetch_decode_30s_demotes_to_transition(monkeypatch, caplog):
    """A guard refusal at the decode boundary reports the transition with the decode stage."""
    caplog.set_level(logging.INFO)

    def decode(work):
        raise BatchValidationError(GUARD)

    worker, results, words, saved, guard, fault = _run(monkeypatch, caplog, decode=decode, duration=30)
    assert len(guard) == 1 and not fault
    assert guard[0].levelno == logging.INFO
    assert 'stage=fetch_decode' in guard[0].getMessage()
    assert 'samples=-1' in guard[0].getMessage() and 'vad_spans=-1' in guard[0].getMessage()
    assert isinstance(results[0], ValidationFailureWork)
    assert (results[0].stage, results[0].reason) == ('fetch_decode', 'unsupported_language')
    assert worker.counts["failed"] == 1


def test_guard_terminal_regardless_of_disposition_flag_true(monkeypatch, caplog):
    """The guard reason terminates the chain with the disposition flag off or on."""
    caplog.set_level(logging.INFO)
    worker, results, words, saved, guard, fault = _run(monkeypatch, caplog, disposition='true')
    assert len(guard) == 1 and not fault
    assert isinstance(results[0], ValidationFailureWork)


def test_guard_terminal_regardless_of_disposition_flag_false(monkeypatch, caplog):
    """The guard reason terminates the chain with the disposition flag off or on."""
    caplog.set_level(logging.INFO)
    worker, results, words, saved, guard, fault = _run(monkeypatch, caplog, disposition='false')
    assert len(guard) == 1 and not fault
    assert isinstance(results[0], ValidationFailureWork)


def test_reason_word_shape_at_vad_flag_off_stays_error(monkeypatch, caplog):
    """word_shape keeps the worker-fault channel and the ladder (disposition off)."""
    caplog.set_level(logging.INFO)

    def vad(_samples):
        raise BatchValidationError(ValidationReason.WORD_SHAPE)

    worker, results, words, saved, guard, fault = _run(monkeypatch, caplog, vad=vad, disposition='false')
    assert not guard and len(fault) == 1
    assert fault[0].levelno == logging.ERROR
    assert 'reason=word_shape' in fault[0].getMessage()
    assert results == []


def test_reason_word_shape_at_vad_flag_on_terminal_and_demotes(monkeypatch, caplog):
    """word_shape under the disposition flag terminates and demotes to the disposition channel."""
    caplog.set_level(logging.INFO)

    def vad(_samples):
        raise BatchValidationError(ValidationReason.WORD_SHAPE)

    worker, results, words, saved, guard, fault = _run(monkeypatch, caplog, vad=vad, disposition='true')
    disposition = [r for r in caplog.records if 'event=batch_validation_disposition' in r.getMessage()]
    assert not guard and not fault and len(disposition) == 1
    assert 'reason=word_shape' in disposition[0].getMessage()
    assert isinstance(results[0], ValidationFailureWork)


def test_reason_word_clock_at_vad_flag_off_stays_error(monkeypatch, caplog):
    """word_clock keeps the worker-fault channel and the ladder (disposition off)."""
    caplog.set_level(logging.INFO)

    def vad(_samples):
        raise BatchValidationError(ValidationReason.WORD_CLOCK)

    worker, results, words, saved, guard, fault = _run(monkeypatch, caplog, vad=vad, disposition='false')
    assert not guard and len(fault) == 1
    assert fault[0].levelno == logging.ERROR
    assert 'reason=word_clock' in fault[0].getMessage()
    assert results == []


def test_reason_word_clock_at_vad_flag_on_terminal_and_demotes(monkeypatch, caplog):
    """word_clock under the disposition flag terminates and demotes to the disposition channel."""
    caplog.set_level(logging.INFO)

    def vad(_samples):
        raise BatchValidationError(ValidationReason.WORD_CLOCK)

    worker, results, words, saved, guard, fault = _run(monkeypatch, caplog, vad=vad, disposition='true')
    disposition = [r for r in caplog.records if 'event=batch_validation_disposition' in r.getMessage()]
    assert not guard and not fault and len(disposition) == 1
    assert 'reason=word_clock' in disposition[0].getMessage()
    assert isinstance(results[0], ValidationFailureWork)


def test_reason_word_sequence_at_vad_flag_off_stays_error(monkeypatch, caplog):
    """word_sequence keeps the worker-fault channel and the ladder (disposition off)."""
    caplog.set_level(logging.INFO)

    def vad(_samples):
        raise BatchValidationError(ValidationReason.WORD_SEQUENCE)

    worker, results, words, saved, guard, fault = _run(monkeypatch, caplog, vad=vad, disposition='false')
    assert not guard and len(fault) == 1
    assert fault[0].levelno == logging.ERROR
    assert 'reason=word_sequence' in fault[0].getMessage()
    assert results == []


def test_reason_word_sequence_at_vad_flag_on_terminal_and_demotes(monkeypatch, caplog):
    """word_sequence under the disposition flag terminates and demotes to the disposition channel."""
    caplog.set_level(logging.INFO)

    def vad(_samples):
        raise BatchValidationError(ValidationReason.WORD_SEQUENCE)

    worker, results, words, saved, guard, fault = _run(monkeypatch, caplog, vad=vad, disposition='true')
    disposition = [r for r in caplog.records if 'event=batch_validation_disposition' in r.getMessage()]
    assert not guard and not fault and len(disposition) == 1
    assert 'reason=word_sequence' in disposition[0].getMessage()
    assert isinstance(results[0], ValidationFailureWork)


def test_reason_vad_nonfinite_at_vad_flag_off_stays_error(monkeypatch, caplog):
    """vad_nonfinite keeps the worker-fault channel and the ladder (disposition off)."""
    caplog.set_level(logging.INFO)

    def vad(_samples):
        raise BatchValidationError(ValidationReason.VAD_NONFINITE)

    worker, results, words, saved, guard, fault = _run(monkeypatch, caplog, vad=vad, disposition='false')
    assert not guard and len(fault) == 1
    assert fault[0].levelno == logging.ERROR
    assert 'reason=vad_nonfinite' in fault[0].getMessage()
    assert results == []


def test_reason_vad_nonfinite_at_vad_flag_on_terminal_and_demotes(monkeypatch, caplog):
    """vad_nonfinite under the disposition flag terminates and demotes to the disposition channel."""
    caplog.set_level(logging.INFO)

    def vad(_samples):
        raise BatchValidationError(ValidationReason.VAD_NONFINITE)

    worker, results, words, saved, guard, fault = _run(monkeypatch, caplog, vad=vad, disposition='true')
    disposition = [r for r in caplog.records if 'event=batch_validation_disposition' in r.getMessage()]
    assert not guard and not fault and len(disposition) == 1
    assert 'reason=vad_nonfinite' in disposition[0].getMessage()
    assert isinstance(results[0], ValidationFailureWork)


def test_reason_vad_order_at_vad_flag_off_stays_error(monkeypatch, caplog):
    """vad_order keeps the worker-fault channel and the ladder (disposition off)."""
    caplog.set_level(logging.INFO)

    def vad(_samples):
        raise BatchValidationError(ValidationReason.VAD_ORDER)

    worker, results, words, saved, guard, fault = _run(monkeypatch, caplog, vad=vad, disposition='false')
    assert not guard and len(fault) == 1
    assert fault[0].levelno == logging.ERROR
    assert 'reason=vad_order' in fault[0].getMessage()
    assert results == []


def test_reason_vad_order_at_vad_flag_on_terminal_and_demotes(monkeypatch, caplog):
    """vad_order under the disposition flag terminates and demotes to the disposition channel."""
    caplog.set_level(logging.INFO)

    def vad(_samples):
        raise BatchValidationError(ValidationReason.VAD_ORDER)

    worker, results, words, saved, guard, fault = _run(monkeypatch, caplog, vad=vad, disposition='true')
    disposition = [r for r in caplog.records if 'event=batch_validation_disposition' in r.getMessage()]
    assert not guard and not fault and len(disposition) == 1
    assert 'reason=vad_order' in disposition[0].getMessage()
    assert isinstance(results[0], ValidationFailureWork)


def test_reason_vad_bounds_at_vad_flag_off_stays_error(monkeypatch, caplog):
    """vad_bounds keeps the worker-fault channel and the ladder (disposition off)."""
    caplog.set_level(logging.INFO)

    def vad(_samples):
        raise BatchValidationError(ValidationReason.VAD_BOUNDS)

    worker, results, words, saved, guard, fault = _run(monkeypatch, caplog, vad=vad, disposition='false')
    assert not guard and len(fault) == 1
    assert fault[0].levelno == logging.ERROR
    assert 'reason=vad_bounds' in fault[0].getMessage()
    assert results == []


def test_reason_empty_asr_at_vad_flag_off_stays_error(monkeypatch, caplog):
    """empty_asr keeps the worker-fault channel and the ladder (disposition off)."""
    caplog.set_level(logging.INFO)

    def vad(_samples):
        raise BatchValidationError(ValidationReason.EMPTY_ASR)

    worker, results, words, saved, guard, fault = _run(monkeypatch, caplog, vad=vad, disposition='false')
    assert not guard and len(fault) == 1
    assert fault[0].levelno == logging.ERROR
    assert 'reason=empty_asr' in fault[0].getMessage()
    assert results == []


def test_reason_empty_asr_at_vad_flag_on_terminal_but_error(monkeypatch, caplog):
    """empty_asr under the disposition flag terminates — and still faults, never demotes."""
    caplog.set_level(logging.INFO)

    def vad(_samples):
        raise BatchValidationError(ValidationReason.EMPTY_ASR)

    worker, results, words, saved, guard, fault = _run(monkeypatch, caplog, vad=vad, disposition='true')
    assert not guard and len(fault) == 1
    assert 'reason=empty_asr' in fault[0].getMessage()
    assert isinstance(results[0], ValidationFailureWork)


def test_reason_no_owned_words_at_vad_flag_off_stays_error(monkeypatch, caplog):
    """no_owned_words keeps the worker-fault channel and the ladder (disposition off)."""
    caplog.set_level(logging.INFO)

    def vad(_samples):
        raise BatchValidationError(ValidationReason.NO_OWNED_WORDS)

    worker, results, words, saved, guard, fault = _run(monkeypatch, caplog, vad=vad, disposition='false')
    assert not guard and len(fault) == 1
    assert fault[0].levelno == logging.ERROR
    assert 'reason=no_owned_words' in fault[0].getMessage()
    assert results == []


def test_reason_no_owned_words_at_vad_flag_on_terminal_but_error(monkeypatch, caplog):
    """no_owned_words under the disposition flag terminates — and still faults, never demotes."""
    caplog.set_level(logging.INFO)

    def vad(_samples):
        raise BatchValidationError(ValidationReason.NO_OWNED_WORDS)

    worker, results, words, saved, guard, fault = _run(monkeypatch, caplog, vad=vad, disposition='true')
    assert not guard and len(fault) == 1
    assert 'reason=no_owned_words' in fault[0].getMessage()
    assert isinstance(results[0], ValidationFailureWork)


def test_reason_word_shape_at_decode_reports_disposition_handoff(monkeypatch, caplog):
    """word_shape at the decode boundary reports the disposition handoff at INFO."""
    caplog.set_level(logging.INFO)

    def decode(work):
        raise BatchValidationError(ValidationReason.WORD_SHAPE)

    worker, results, words, saved, guard, fault = _run(monkeypatch, caplog, decode=decode)
    disposition = [r for r in caplog.records if 'event=batch_validation_disposition' in r.getMessage()]
    assert not guard and not fault and len(disposition) == 1
    assert 'stage=fetch_decode' in disposition[0].getMessage()
    assert 'reason=word_shape' in disposition[0].getMessage()


def test_reason_word_clock_at_decode_reports_disposition_handoff(monkeypatch, caplog):
    """word_clock at the decode boundary reports the disposition handoff at INFO."""
    caplog.set_level(logging.INFO)

    def decode(work):
        raise BatchValidationError(ValidationReason.WORD_CLOCK)

    worker, results, words, saved, guard, fault = _run(monkeypatch, caplog, decode=decode)
    disposition = [r for r in caplog.records if 'event=batch_validation_disposition' in r.getMessage()]
    assert not guard and not fault and len(disposition) == 1
    assert 'stage=fetch_decode' in disposition[0].getMessage()
    assert 'reason=word_clock' in disposition[0].getMessage()


def test_reason_word_sequence_at_decode_reports_disposition_handoff(monkeypatch, caplog):
    """word_sequence at the decode boundary reports the disposition handoff at INFO."""
    caplog.set_level(logging.INFO)

    def decode(work):
        raise BatchValidationError(ValidationReason.WORD_SEQUENCE)

    worker, results, words, saved, guard, fault = _run(monkeypatch, caplog, decode=decode)
    disposition = [r for r in caplog.records if 'event=batch_validation_disposition' in r.getMessage()]
    assert not guard and not fault and len(disposition) == 1
    assert 'stage=fetch_decode' in disposition[0].getMessage()
    assert 'reason=word_sequence' in disposition[0].getMessage()


def test_reason_vad_nonfinite_at_decode_reports_disposition_handoff(monkeypatch, caplog):
    """vad_nonfinite at the decode boundary reports the disposition handoff at INFO."""
    caplog.set_level(logging.INFO)

    def decode(work):
        raise BatchValidationError(ValidationReason.VAD_NONFINITE)

    worker, results, words, saved, guard, fault = _run(monkeypatch, caplog, decode=decode)
    disposition = [r for r in caplog.records if 'event=batch_validation_disposition' in r.getMessage()]
    assert not guard and not fault and len(disposition) == 1
    assert 'stage=fetch_decode' in disposition[0].getMessage()
    assert 'reason=vad_nonfinite' in disposition[0].getMessage()


def test_reason_vad_order_at_decode_reports_disposition_handoff(monkeypatch, caplog):
    """vad_order at the decode boundary reports the disposition handoff at INFO."""
    caplog.set_level(logging.INFO)

    def decode(work):
        raise BatchValidationError(ValidationReason.VAD_ORDER)

    worker, results, words, saved, guard, fault = _run(monkeypatch, caplog, decode=decode)
    disposition = [r for r in caplog.records if 'event=batch_validation_disposition' in r.getMessage()]
    assert not guard and not fault and len(disposition) == 1
    assert 'stage=fetch_decode' in disposition[0].getMessage()
    assert 'reason=vad_order' in disposition[0].getMessage()


def test_reason_vad_bounds_at_decode_reports_disposition_handoff(monkeypatch, caplog):
    """vad_bounds at the decode boundary reports the disposition handoff at INFO."""
    caplog.set_level(logging.INFO)

    def decode(work):
        raise BatchValidationError(ValidationReason.VAD_BOUNDS)

    worker, results, words, saved, guard, fault = _run(monkeypatch, caplog, decode=decode)
    disposition = [r for r in caplog.records if 'event=batch_validation_disposition' in r.getMessage()]
    assert not guard and not fault and len(disposition) == 1
    assert 'stage=fetch_decode' in disposition[0].getMessage()
    assert 'reason=vad_bounds' in disposition[0].getMessage()


def test_reason_empty_asr_at_decode_stays_error(monkeypatch, caplog):
    """empty_asr at the decode boundary keeps the fault channel."""
    caplog.set_level(logging.INFO)

    def decode(work):
        raise BatchValidationError(ValidationReason.EMPTY_ASR)

    worker, results, words, saved, guard, fault = _run(monkeypatch, caplog, decode=decode)
    assert not guard and len(fault) == 1
    assert 'stage=fetch_decode' in fault[0].getMessage()
    assert 'reason=empty_asr' in fault[0].getMessage()


def test_reason_no_owned_words_at_decode_stays_error(monkeypatch, caplog):
    """no_owned_words at the decode boundary keeps the fault channel."""
    caplog.set_level(logging.INFO)

    def decode(work):
        raise BatchValidationError(ValidationReason.NO_OWNED_WORDS)

    worker, results, words, saved, guard, fault = _run(monkeypatch, caplog, decode=decode)
    assert not guard and len(fault) == 1
    assert 'stage=fetch_decode' in fault[0].getMessage()
    assert 'reason=no_owned_words' in fault[0].getMessage()


def test_typed_staged_audio_invalid_reports_disposition_handoff(monkeypatch, caplog):
    """The typed staged_audio_invalid terminal reports the disposition handoff at INFO."""
    caplog.set_level(logging.INFO)

    def decode(work):
        raise StagedAudioInvalid("staged bytes")

    worker, results, words, saved, guard, fault = _run(monkeypatch, caplog, decode=decode)
    disposition = [r for r in caplog.records if 'event=batch_validation_disposition' in r.getMessage()]
    assert not guard and not fault and len(disposition) == 1
    assert 'reason=staged_audio_invalid' in disposition[0].getMessage()
    assert isinstance(results[0], ValidationFailureWork)


def test_typed_staged_artifact_invalid_reports_disposition_handoff(monkeypatch, caplog):
    """The typed staged_artifact_invalid terminal reports the disposition handoff at INFO."""
    caplog.set_level(logging.INFO)

    def decode(work):
        raise StagedArtifactInvalid("artifact bytes")

    worker, results, words, saved, guard, fault = _run(monkeypatch, caplog, decode=decode)
    disposition = [r for r in caplog.records if 'event=batch_validation_disposition' in r.getMessage()]
    assert not guard and not fault and len(disposition) == 1
    assert 'reason=staged_audio_invalid' in disposition[0].getMessage()
    assert isinstance(results[0], ValidationFailureWork)


def test_typed_retained_audio_invalid_reports_disposition_handoff(monkeypatch, caplog):
    """The typed retained_audio_invalid terminal reports the disposition handoff at INFO."""
    caplog.set_level(logging.INFO)

    def decode(work):
        raise RetainedAudioInvalid("retained bytes")

    worker, results, words, saved, guard, fault = _run(monkeypatch, caplog, decode=decode)
    disposition = [r for r in caplog.records if 'event=batch_validation_disposition' in r.getMessage()]
    assert not guard and not fault and len(disposition) == 1
    assert 'reason=retained_audio_invalid' in disposition[0].getMessage()
    assert isinstance(results[0], ValidationFailureWork)


def test_typed_decoded_duration_mismatch_reports_disposition_handoff(monkeypatch, caplog):
    """The typed decoded_duration_mismatch terminal reports the disposition handoff at INFO."""
    caplog.set_level(logging.INFO)

    def decode(work):
        raise DecodedDurationMismatch("extent")

    worker, results, words, saved, guard, fault = _run(monkeypatch, caplog, decode=decode)
    disposition = [r for r in caplog.records if 'event=batch_validation_disposition' in r.getMessage()]
    assert not guard and not fault and len(disposition) == 1
    assert 'reason=decoded_duration_mismatch' in disposition[0].getMessage()
    assert isinstance(results[0], ValidationFailureWork)


def test_generic_ValueError_at_vad_stays_error(monkeypatch, caplog):
    """A generic ValueError at vad keeps the fault channel."""
    caplog.set_level(logging.INFO)

    def vad(arg):
        raise ValueError("x")

    worker, results, words, saved, guard, fault = _run(monkeypatch, caplog, vad=vad)
    assert not guard and len(fault) == 1
    assert 'error_class=ValueError' in fault[0].getMessage()


def test_generic_ValueError_at_decode_stays_error(monkeypatch, caplog):
    """A generic ValueError at decode keeps the fault channel."""
    caplog.set_level(logging.INFO)

    def decode(arg):
        raise ValueError("x")

    worker, results, words, saved, guard, fault = _run(monkeypatch, caplog, decode=decode)
    assert not guard and len(fault) == 1
    assert 'error_class=ValueError' in fault[0].getMessage()


def test_generic_RuntimeError_at_vad_stays_error(monkeypatch, caplog):
    """A generic RuntimeError at vad keeps the fault channel."""
    caplog.set_level(logging.INFO)

    def vad(arg):
        raise RuntimeError("x")

    worker, results, words, saved, guard, fault = _run(monkeypatch, caplog, vad=vad)
    assert not guard and len(fault) == 1
    assert 'error_class=RuntimeError' in fault[0].getMessage()


def test_generic_RuntimeError_at_decode_stays_error(monkeypatch, caplog):
    """A generic RuntimeError at decode keeps the fault channel."""
    caplog.set_level(logging.INFO)

    def decode(arg):
        raise RuntimeError("x")

    worker, results, words, saved, guard, fault = _run(monkeypatch, caplog, decode=decode)
    assert not guard and len(fault) == 1
    assert 'error_class=RuntimeError' in fault[0].getMessage()


def test_generic_TimeoutError_at_vad_stays_error(monkeypatch, caplog):
    """A generic TimeoutError at vad keeps the fault channel."""
    caplog.set_level(logging.INFO)

    def vad(arg):
        raise TimeoutError("x")

    worker, results, words, saved, guard, fault = _run(monkeypatch, caplog, vad=vad)
    assert not guard and len(fault) == 1
    assert 'error_class=TimeoutError' in fault[0].getMessage()


def test_generic_TimeoutError_at_decode_stays_error(monkeypatch, caplog):
    """A generic TimeoutError at decode keeps the fault channel."""
    caplog.set_level(logging.INFO)

    def decode(arg):
        raise TimeoutError("x")

    worker, results, words, saved, guard, fault = _run(monkeypatch, caplog, decode=decode)
    assert not guard and len(fault) == 1
    assert 'error_class=TimeoutError' in fault[0].getMessage()


def test_generic_KeyError_at_vad_stays_error(monkeypatch, caplog):
    """A generic KeyError at vad keeps the fault channel."""
    caplog.set_level(logging.INFO)

    def vad(arg):
        raise KeyError("x")

    worker, results, words, saved, guard, fault = _run(monkeypatch, caplog, vad=vad)
    assert not guard and len(fault) == 1
    assert 'error_class=KeyError' in fault[0].getMessage()


def test_generic_KeyError_at_decode_stays_error(monkeypatch, caplog):
    """A generic KeyError at decode keeps the fault channel."""
    caplog.set_level(logging.INFO)

    def decode(arg):
        raise KeyError("x")

    worker, results, words, saved, guard, fault = _run(monkeypatch, caplog, decode=decode)
    assert not guard and len(fault) == 1
    assert 'error_class=KeyError' in fault[0].getMessage()


def test_shadow_guard_at_vad_windows_stays_shadow_line(monkeypatch, caplog):
    """Shadow units keep the shadow line only (vad_windows)."""
    caplog.set_level(logging.INFO)

    def vad(_samples):
        raise BatchValidationError(GUARD)

    worker, results, words, saved, guard, fault = _run(monkeypatch, caplog, vad=vad, shadow=True)
    assert not guard and not fault
    assert isinstance(results[0], ValidationFailureWork)


def test_shadow_guard_at_fetch_decode_stays_shadow_line(monkeypatch, caplog):
    """Shadow units keep the shadow line only (fetch_decode)."""
    caplog.set_level(logging.INFO)

    def decode(work):
        raise BatchValidationError(GUARD)

    worker, results, words, saved, guard, fault = _run(monkeypatch, caplog, decode=decode, shadow=True)
    assert not guard and not fault
    assert isinstance(results[0], ValidationFailureWork)


def test_blocked_language_with_no_spans_is_silence_2s(monkeypatch, caplog):
    """A blocked language with no speech spans is the silence disposition, not the guard."""
    caplog.set_level(logging.INFO)
    worker, results, words, saved, guard, fault = _run(
        monkeypatch, caplog, language='vi', vad=lambda _s: [], duration=2
    )
    assert not guard and not fault
    assert results[0].outcome == "silence"
    assert saved["a"]["words"] == []


def test_blocked_language_with_no_spans_is_silence_30s(monkeypatch, caplog):
    """A blocked language with no speech spans is the silence disposition, not the guard."""
    caplog.set_level(logging.INFO)
    worker, results, words, saved, guard, fault = _run(
        monkeypatch, caplog, language='vi', vad=lambda _s: [], duration=30
    )
    assert not guard and not fault
    assert results[0].outcome == "silence"
    assert saved["a"]["words"] == []


def test_supported_language_2s_succeeds_without_any_guard_record(monkeypatch, caplog):
    """A supported language transcribes; no guard line exists."""
    caplog.set_level(logging.INFO)
    worker, results, words, saved, guard, fault = _run(monkeypatch, caplog, language='en', duration=2)
    assert not guard and not fault
    assert words.calls and results[0].outcome == "success"


def test_supported_language_30s_succeeds_without_any_guard_record(monkeypatch, caplog):
    """A supported language transcribes; no guard line exists."""
    caplog.set_level(logging.INFO)
    worker, results, words, saved, guard, fault = _run(monkeypatch, caplog, language='en', duration=30)
    assert not guard and not fault
    assert words.calls and results[0].outcome == "success"


def test_on_failure_receives_the_typed_guard_error(monkeypatch, caplog):
    """The failure callback keeps receiving the typed error next to the demoted line."""
    caplog.set_level(logging.INFO)
    seen = []

    def on_failure(unit, exc):
        seen.append((unit.segment_id, exc))

    worker, results, words, saved, guard, fault = _run(monkeypatch, caplog, on_failure=on_failure)
    assert len(seen) == 1 and seen[0][0] == "a"
    assert seen[0][1] == "BatchValidationError"
    assert len(guard) == 1


def test_on_failure_receives_non_guard_error_too(monkeypatch, caplog):
    """Non-guard callbacks are untouched."""
    caplog.set_level(logging.INFO)
    seen = []

    def on_failure(unit, exc):
        seen.append(exc)

    def vad(_samples):
        raise BatchValidationError(ValidationReason.VAD_BOUNDS)

    worker, results, words, saved, guard, fault = _run(
        monkeypatch, caplog, vad=vad, on_failure=on_failure, disposition='false'
    )
    assert seen and seen[0] == "BatchValidationError"
    assert len(fault) == 1 and not guard


def test_two_guard_units_log_two_transitions(monkeypatch, caplog):
    """Every guarded unit in a batch reports its own transition."""
    _env(monkeypatch)
    caplog.set_level(logging.INFO)
    worker, words, saved, decoded, diarized, failures = setup_worker(language_of=lambda _: "vi")
    results = worker.process_batch([item("a", 2), item("b", 4)])
    guard = [r for r in caplog.records if "event=batch_language_guard" in r.getMessage()]
    fault = [r for r in caplog.records if "event=batch_worker_failed" in r.getMessage()]
    assert len(guard) == 2 and not fault
    assert worker.counts["failed"] == 2
    assert {r.segment_id for r in results} == {"a", "b"}


def test_mixed_batch_guard_first_classifies_each_unit_once(monkeypatch, caplog):
    """Mixed batches classify each unit once, in either order."""
    from dataclasses import replace as _replace

    _env(monkeypatch)
    caplog.set_level(logging.INFO)
    worker, words, saved, decoded, diarized, failures = setup_worker(
        language_of=lambda u: "vi" if u.segment_id == "a" else "en"
    )
    results = worker.process_batch([item("a", 2), _replace(item("en", 4), language_receipt_enabled=True)])
    guard = [r for r in caplog.records if "event=batch_language_guard" in r.getMessage()]
    fault = [r for r in caplog.records if "event=batch_worker_failed" in r.getMessage()]
    assert len(guard) == 1 and not fault
    assert words.calls
    kinds = {type(r).__name__ for r in results}
    assert "ValidationFailureWork" in kinds and "WorkResult" in kinds


def test_mixed_batch_success_first_classifies_each_unit_once(monkeypatch, caplog):
    """Mixed batches classify each unit once, in either order."""
    from dataclasses import replace as _replace

    _env(monkeypatch)
    caplog.set_level(logging.INFO)
    worker, words, saved, decoded, diarized, failures = setup_worker(
        language_of=lambda u: "vi" if u.segment_id == "a" else "en"
    )
    results = worker.process_batch([_replace(item("en", 4), language_receipt_enabled=True), item("a", 2)])
    guard = [r for r in caplog.records if "event=batch_language_guard" in r.getMessage()]
    fault = [r for r in caplog.records if "event=batch_worker_failed" in r.getMessage()]
    assert len(guard) == 1 and not fault
    assert words.calls
    kinds = {type(r).__name__ for r in results}
    assert "ValidationFailureWork" in kinds and "WorkResult" in kinds


def test_guard_line_never_carries_exception_payload_text(monkeypatch, caplog):
    """A subclass with a noisy __str__ still demotes — and never leaks the payload text."""
    caplog.set_level(logging.INFO)

    def vad(_samples):
        raise NoisyGuard(GUARD)

    worker, results, words, saved, guard, fault = _run(monkeypatch, caplog, vad=vad)
    assert len(guard) == 1 and not fault
    assert "SECRET-AUDIO-BYTES" not in guard[0].getMessage()
    assert isinstance(results[0], ValidationFailureWork)


def test_guard_record_rides_the_worker_logger(monkeypatch, caplog):
    caplog.set_level(logging.INFO)
    worker, results, words, saved, guard, fault = _run(monkeypatch, caplog)
    assert guard[0].name == "diarizer.batch_pipeline"


def test_fault_record_rides_the_worker_logger(monkeypatch, caplog):
    caplog.set_level(logging.INFO)

    def vad(_samples):
        raise BatchValidationError(ValidationReason.VAD_BOUNDS)

    worker, results, words, saved, guard, fault = _run(monkeypatch, caplog, vad=vad, disposition='false')
    assert fault[0].name == "diarizer.batch_pipeline"


def test_duplicate_segment_admission_is_refused(monkeypatch, caplog):
    """A batch carries distinct conversations only; the duplicate never reaches the barrier."""
    _env(monkeypatch)
    caplog.set_level(logging.INFO)
    worker, words, saved, decoded, diarized, failures = setup_worker(language_of=lambda _: "vi")
    with pytest.raises(ValueError):
        worker.process_batch([item("a", 2), item("a", 2)])
    guard = [r for r in caplog.records if "event=batch_language_guard" in r.getMessage()]
    assert not guard


def test_guard_record_carries_the_windows_token(monkeypatch, caplog):
    caplog.set_level(logging.INFO)
    worker, results, words, saved, guard, fault = _run(monkeypatch, caplog)
    assert "windows=" in guard[0].getMessage()


def test_guard_record_counts_1_vad_spans(monkeypatch, caplog):
    """1 speech spans land in the transition record."""
    caplog.set_level(logging.INFO)
    worker, results, words, saved, guard, fault = _run(monkeypatch, caplog, vad=lambda _s: [(0.1, 0.9)])
    assert "vad_spans=1" in guard[0].getMessage()
    assert isinstance(results[0], ValidationFailureWork)


def test_guard_record_counts_2_vad_spans(monkeypatch, caplog):
    """2 speech spans land in the transition record."""
    caplog.set_level(logging.INFO)
    worker, results, words, saved, guard, fault = _run(monkeypatch, caplog, vad=lambda _s: [(0.1, 0.5), (0.6, 0.9)])
    assert "vad_spans=2" in guard[0].getMessage()
    assert isinstance(results[0], ValidationFailureWork)


def test_guard_record_counts_3_vad_spans(monkeypatch, caplog):
    """3 speech spans land in the transition record."""
    caplog.set_level(logging.INFO)
    worker, results, words, saved, guard, fault = _run(
        monkeypatch, caplog, vad=lambda _s: [(0.05, 0.3), (0.4, 0.6), (0.7, 0.95)]
    )
    assert "vad_spans=3" in guard[0].getMessage()
    assert isinstance(results[0], ValidationFailureWork)


def test_guard_record_echoes_segment_id_seg_42(monkeypatch, caplog):
    """The transition record echoes the segment id verbatim."""
    caplog.set_level(logging.INFO)
    worker, results, words, saved, guard, fault = _run(monkeypatch, caplog, key="seg-42")
    assert "segment_id=seg-42" in guard[0].getMessage()


def test_guard_record_echoes_segment_id_94397aea29ad(monkeypatch, caplog):
    """The transition record echoes the segment id verbatim."""
    caplog.set_level(logging.INFO)
    worker, results, words, saved, guard, fault = _run(
        monkeypatch, caplog, key="94397aea29add38b43309bc25872dd5593da9d011"
    )
    assert "segment_id=94397aea29add38b43309bc25872dd5593da9d011" in guard[0].getMessage()


def test_fault_record_echoes_segment_id_too(monkeypatch, caplog):
    caplog.set_level(logging.INFO)

    def vad(_samples):
        raise BatchValidationError(ValidationReason.VAD_BOUNDS)

    worker, results, words, saved, guard, fault = _run(monkeypatch, caplog, vad=vad, disposition='false', key="seg-42")
    assert "segment_id=seg-42" in fault[0].getMessage()
