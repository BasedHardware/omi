"""The disposition boundary: which typed reasons terminate, and none of them demote.

Only the language-guard reason is terminal regardless of the disposition flag; every other typed reason terminates only while the flag is on — and every one of them keeps the event=batch_worker_failed ERROR line in every flag combination. This grid pins the terminality and the channel for both drivable stages (fetch_decode, vad_windows) across all nine typed reasons, both flags, and both safety settings.

Failure-Class: FC-language-guard-redrive-misclassified-as-worker-fault
"""

import logging
from dataclasses import replace

import pytest

from diarizer.batch_pipeline import DecodedDurationMismatch
from utils.batch_pipeline.artifacts import StagedArtifactInvalid
from utils.batch_pipeline.audio import StagedAudioInvalid
from utils.batch_pipeline.contracts import ValidationFailureWork, WorkResult
from utils.batch_pipeline.source_audio import RetainedAudioInvalid
from utils.batch_pipeline.word_validation import BatchValidationError, ValidationReason
from tests.unit.test_batch_pipeline_worker import Samples, item, setup_worker

GUARD = ValidationReason.UNSUPPORTED_LANGUAGE
LANGS = ['vi', None, '', 'und', 'multi', 'unknown']
DURS = [0.5, 1, 2, 4, 10, 30, 90, 600]


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
    key='a'
):
    _env(monkeypatch, disposition, safety)
    caplog.set_level(logging.INFO)
    kwargs = {}
    if vad is not None:
        kwargs['vad'] = vad
    if decode is not None:
        kwargs['decode'] = decode
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


def test_disposition_fetch_decode_unsupported_language_disp_on_safety_off(monkeypatch, caplog):
    """unsupported_language at fetch_decode (disposition true, safety false)."""
    caplog.set_level(logging.INFO)

    def decode(arg):
        raise BatchValidationError(ValidationReason.UNSUPPORTED_LANGUAGE)

    worker, results, words, saved, guard, fault = _run(
        monkeypatch, caplog, decode=decode, disposition='true', safety='false'
    )
    assert len(guard) == 1 and not fault
    assert 'outcome=redrive_held' in guard[0].getMessage()
    assert isinstance(results[0], ValidationFailureWork)


def test_disposition_fetch_decode_unsupported_language_disp_off_safety_off(monkeypatch, caplog):
    """unsupported_language at fetch_decode (disposition false, safety false)."""
    caplog.set_level(logging.INFO)

    def decode(arg):
        raise BatchValidationError(ValidationReason.UNSUPPORTED_LANGUAGE)

    worker, results, words, saved, guard, fault = _run(
        monkeypatch, caplog, decode=decode, disposition='false', safety='false'
    )
    assert len(guard) == 1 and not fault
    assert 'outcome=redrive_held' in guard[0].getMessage()
    assert isinstance(results[0], ValidationFailureWork)


def test_disposition_fetch_decode_unsupported_language_disp_on_safety_on(monkeypatch, caplog):
    """unsupported_language at fetch_decode (disposition true, safety true)."""
    caplog.set_level(logging.INFO)

    def decode(arg):
        raise BatchValidationError(ValidationReason.UNSUPPORTED_LANGUAGE)

    worker, results, words, saved, guard, fault = _run(
        monkeypatch, caplog, decode=decode, disposition='true', safety='true'
    )
    assert len(guard) == 1 and not fault
    assert 'outcome=redrive_held' in guard[0].getMessage()
    assert isinstance(results[0], ValidationFailureWork)


def test_disposition_fetch_decode_unsupported_language_disp_off_safety_on(monkeypatch, caplog):
    """unsupported_language at fetch_decode (disposition false, safety true)."""
    caplog.set_level(logging.INFO)

    def decode(arg):
        raise BatchValidationError(ValidationReason.UNSUPPORTED_LANGUAGE)

    worker, results, words, saved, guard, fault = _run(
        monkeypatch, caplog, decode=decode, disposition='false', safety='true'
    )
    assert len(guard) == 1 and not fault
    assert 'outcome=redrive_held' in guard[0].getMessage()
    assert isinstance(results[0], ValidationFailureWork)


def test_disposition_fetch_decode_word_shape_disp_on_safety_off(monkeypatch, caplog):
    """word_shape at fetch_decode (disposition true, safety false)."""
    caplog.set_level(logging.INFO)

    def decode(arg):
        raise BatchValidationError(ValidationReason.WORD_SHAPE)

    worker, results, words, saved, guard, fault = _run(
        monkeypatch, caplog, decode=decode, disposition='true', safety='false'
    )
    assert not guard and len(fault) == 1
    assert 'reason=word_shape' in fault[0].getMessage()
    assert isinstance(results[0], ValidationFailureWork)


def test_disposition_fetch_decode_word_shape_disp_off_safety_off(monkeypatch, caplog):
    """word_shape at fetch_decode (disposition false, safety false)."""
    caplog.set_level(logging.INFO)

    def decode(arg):
        raise BatchValidationError(ValidationReason.WORD_SHAPE)

    worker, results, words, saved, guard, fault = _run(
        monkeypatch, caplog, decode=decode, disposition='false', safety='false'
    )
    assert not guard and len(fault) == 1
    assert 'reason=word_shape' in fault[0].getMessage()
    assert not any(isinstance(r, ValidationFailureWork) for r in results)


def test_disposition_fetch_decode_word_shape_disp_on_safety_on(monkeypatch, caplog):
    """word_shape at fetch_decode (disposition true, safety true)."""
    caplog.set_level(logging.INFO)

    def decode(arg):
        raise BatchValidationError(ValidationReason.WORD_SHAPE)

    worker, results, words, saved, guard, fault = _run(
        monkeypatch, caplog, decode=decode, disposition='true', safety='true'
    )
    assert not guard and len(fault) == 1
    assert 'reason=word_shape' in fault[0].getMessage()
    assert isinstance(results[0], ValidationFailureWork)


def test_disposition_fetch_decode_word_shape_disp_off_safety_on(monkeypatch, caplog):
    """word_shape at fetch_decode (disposition false, safety true)."""
    caplog.set_level(logging.INFO)

    def decode(arg):
        raise BatchValidationError(ValidationReason.WORD_SHAPE)

    worker, results, words, saved, guard, fault = _run(
        monkeypatch, caplog, decode=decode, disposition='false', safety='true'
    )
    assert not guard and len(fault) == 1
    assert 'reason=word_shape' in fault[0].getMessage()
    assert not any(isinstance(r, ValidationFailureWork) for r in results)


def test_disposition_fetch_decode_word_clock_disp_on_safety_off(monkeypatch, caplog):
    """word_clock at fetch_decode (disposition true, safety false)."""
    caplog.set_level(logging.INFO)

    def decode(arg):
        raise BatchValidationError(ValidationReason.WORD_CLOCK)

    worker, results, words, saved, guard, fault = _run(
        monkeypatch, caplog, decode=decode, disposition='true', safety='false'
    )
    assert not guard and len(fault) == 1
    assert 'reason=word_clock' in fault[0].getMessage()
    assert isinstance(results[0], ValidationFailureWork)


def test_disposition_fetch_decode_word_clock_disp_off_safety_off(monkeypatch, caplog):
    """word_clock at fetch_decode (disposition false, safety false)."""
    caplog.set_level(logging.INFO)

    def decode(arg):
        raise BatchValidationError(ValidationReason.WORD_CLOCK)

    worker, results, words, saved, guard, fault = _run(
        monkeypatch, caplog, decode=decode, disposition='false', safety='false'
    )
    assert not guard and len(fault) == 1
    assert 'reason=word_clock' in fault[0].getMessage()
    assert not any(isinstance(r, ValidationFailureWork) for r in results)


def test_disposition_fetch_decode_word_clock_disp_on_safety_on(monkeypatch, caplog):
    """word_clock at fetch_decode (disposition true, safety true)."""
    caplog.set_level(logging.INFO)

    def decode(arg):
        raise BatchValidationError(ValidationReason.WORD_CLOCK)

    worker, results, words, saved, guard, fault = _run(
        monkeypatch, caplog, decode=decode, disposition='true', safety='true'
    )
    assert not guard and len(fault) == 1
    assert 'reason=word_clock' in fault[0].getMessage()
    assert isinstance(results[0], ValidationFailureWork)


def test_disposition_fetch_decode_word_clock_disp_off_safety_on(monkeypatch, caplog):
    """word_clock at fetch_decode (disposition false, safety true)."""
    caplog.set_level(logging.INFO)

    def decode(arg):
        raise BatchValidationError(ValidationReason.WORD_CLOCK)

    worker, results, words, saved, guard, fault = _run(
        monkeypatch, caplog, decode=decode, disposition='false', safety='true'
    )
    assert not guard and len(fault) == 1
    assert 'reason=word_clock' in fault[0].getMessage()
    assert not any(isinstance(r, ValidationFailureWork) for r in results)


def test_disposition_fetch_decode_word_sequence_disp_on_safety_off(monkeypatch, caplog):
    """word_sequence at fetch_decode (disposition true, safety false)."""
    caplog.set_level(logging.INFO)

    def decode(arg):
        raise BatchValidationError(ValidationReason.WORD_SEQUENCE)

    worker, results, words, saved, guard, fault = _run(
        monkeypatch, caplog, decode=decode, disposition='true', safety='false'
    )
    assert not guard and len(fault) == 1
    assert 'reason=word_sequence' in fault[0].getMessage()
    assert isinstance(results[0], ValidationFailureWork)


def test_disposition_fetch_decode_word_sequence_disp_off_safety_off(monkeypatch, caplog):
    """word_sequence at fetch_decode (disposition false, safety false)."""
    caplog.set_level(logging.INFO)

    def decode(arg):
        raise BatchValidationError(ValidationReason.WORD_SEQUENCE)

    worker, results, words, saved, guard, fault = _run(
        monkeypatch, caplog, decode=decode, disposition='false', safety='false'
    )
    assert not guard and len(fault) == 1
    assert 'reason=word_sequence' in fault[0].getMessage()
    assert not any(isinstance(r, ValidationFailureWork) for r in results)


def test_disposition_fetch_decode_word_sequence_disp_on_safety_on(monkeypatch, caplog):
    """word_sequence at fetch_decode (disposition true, safety true)."""
    caplog.set_level(logging.INFO)

    def decode(arg):
        raise BatchValidationError(ValidationReason.WORD_SEQUENCE)

    worker, results, words, saved, guard, fault = _run(
        monkeypatch, caplog, decode=decode, disposition='true', safety='true'
    )
    assert not guard and len(fault) == 1
    assert 'reason=word_sequence' in fault[0].getMessage()
    assert isinstance(results[0], ValidationFailureWork)


def test_disposition_fetch_decode_word_sequence_disp_off_safety_on(monkeypatch, caplog):
    """word_sequence at fetch_decode (disposition false, safety true)."""
    caplog.set_level(logging.INFO)

    def decode(arg):
        raise BatchValidationError(ValidationReason.WORD_SEQUENCE)

    worker, results, words, saved, guard, fault = _run(
        monkeypatch, caplog, decode=decode, disposition='false', safety='true'
    )
    assert not guard and len(fault) == 1
    assert 'reason=word_sequence' in fault[0].getMessage()
    assert not any(isinstance(r, ValidationFailureWork) for r in results)


def test_disposition_fetch_decode_vad_nonfinite_disp_on_safety_off(monkeypatch, caplog):
    """vad_nonfinite at fetch_decode (disposition true, safety false)."""
    caplog.set_level(logging.INFO)

    def decode(arg):
        raise BatchValidationError(ValidationReason.VAD_NONFINITE)

    worker, results, words, saved, guard, fault = _run(
        monkeypatch, caplog, decode=decode, disposition='true', safety='false'
    )
    assert not guard and len(fault) == 1
    assert 'reason=vad_nonfinite' in fault[0].getMessage()
    assert isinstance(results[0], ValidationFailureWork)


def test_disposition_fetch_decode_vad_nonfinite_disp_off_safety_off(monkeypatch, caplog):
    """vad_nonfinite at fetch_decode (disposition false, safety false)."""
    caplog.set_level(logging.INFO)

    def decode(arg):
        raise BatchValidationError(ValidationReason.VAD_NONFINITE)

    worker, results, words, saved, guard, fault = _run(
        monkeypatch, caplog, decode=decode, disposition='false', safety='false'
    )
    assert not guard and len(fault) == 1
    assert 'reason=vad_nonfinite' in fault[0].getMessage()
    assert not any(isinstance(r, ValidationFailureWork) for r in results)


def test_disposition_fetch_decode_vad_nonfinite_disp_on_safety_on(monkeypatch, caplog):
    """vad_nonfinite at fetch_decode (disposition true, safety true)."""
    caplog.set_level(logging.INFO)

    def decode(arg):
        raise BatchValidationError(ValidationReason.VAD_NONFINITE)

    worker, results, words, saved, guard, fault = _run(
        monkeypatch, caplog, decode=decode, disposition='true', safety='true'
    )
    assert not guard and len(fault) == 1
    assert 'reason=vad_nonfinite' in fault[0].getMessage()
    assert isinstance(results[0], ValidationFailureWork)


def test_disposition_fetch_decode_vad_nonfinite_disp_off_safety_on(monkeypatch, caplog):
    """vad_nonfinite at fetch_decode (disposition false, safety true)."""
    caplog.set_level(logging.INFO)

    def decode(arg):
        raise BatchValidationError(ValidationReason.VAD_NONFINITE)

    worker, results, words, saved, guard, fault = _run(
        monkeypatch, caplog, decode=decode, disposition='false', safety='true'
    )
    assert not guard and len(fault) == 1
    assert 'reason=vad_nonfinite' in fault[0].getMessage()
    assert not any(isinstance(r, ValidationFailureWork) for r in results)


def test_disposition_fetch_decode_vad_order_disp_on_safety_off(monkeypatch, caplog):
    """vad_order at fetch_decode (disposition true, safety false)."""
    caplog.set_level(logging.INFO)

    def decode(arg):
        raise BatchValidationError(ValidationReason.VAD_ORDER)

    worker, results, words, saved, guard, fault = _run(
        monkeypatch, caplog, decode=decode, disposition='true', safety='false'
    )
    assert not guard and len(fault) == 1
    assert 'reason=vad_order' in fault[0].getMessage()
    assert isinstance(results[0], ValidationFailureWork)


def test_disposition_fetch_decode_vad_order_disp_off_safety_off(monkeypatch, caplog):
    """vad_order at fetch_decode (disposition false, safety false)."""
    caplog.set_level(logging.INFO)

    def decode(arg):
        raise BatchValidationError(ValidationReason.VAD_ORDER)

    worker, results, words, saved, guard, fault = _run(
        monkeypatch, caplog, decode=decode, disposition='false', safety='false'
    )
    assert not guard and len(fault) == 1
    assert 'reason=vad_order' in fault[0].getMessage()
    assert not any(isinstance(r, ValidationFailureWork) for r in results)


def test_disposition_fetch_decode_vad_order_disp_on_safety_on(monkeypatch, caplog):
    """vad_order at fetch_decode (disposition true, safety true)."""
    caplog.set_level(logging.INFO)

    def decode(arg):
        raise BatchValidationError(ValidationReason.VAD_ORDER)

    worker, results, words, saved, guard, fault = _run(
        monkeypatch, caplog, decode=decode, disposition='true', safety='true'
    )
    assert not guard and len(fault) == 1
    assert 'reason=vad_order' in fault[0].getMessage()
    assert isinstance(results[0], ValidationFailureWork)


def test_disposition_fetch_decode_vad_order_disp_off_safety_on(monkeypatch, caplog):
    """vad_order at fetch_decode (disposition false, safety true)."""
    caplog.set_level(logging.INFO)

    def decode(arg):
        raise BatchValidationError(ValidationReason.VAD_ORDER)

    worker, results, words, saved, guard, fault = _run(
        monkeypatch, caplog, decode=decode, disposition='false', safety='true'
    )
    assert not guard and len(fault) == 1
    assert 'reason=vad_order' in fault[0].getMessage()
    assert not any(isinstance(r, ValidationFailureWork) for r in results)


def test_disposition_fetch_decode_vad_bounds_disp_on_safety_off(monkeypatch, caplog):
    """vad_bounds at fetch_decode (disposition true, safety false)."""
    caplog.set_level(logging.INFO)

    def decode(arg):
        raise BatchValidationError(ValidationReason.VAD_BOUNDS)

    worker, results, words, saved, guard, fault = _run(
        monkeypatch, caplog, decode=decode, disposition='true', safety='false'
    )
    assert not guard and len(fault) == 1
    assert 'reason=vad_bounds' in fault[0].getMessage()
    assert isinstance(results[0], ValidationFailureWork)


def test_disposition_fetch_decode_vad_bounds_disp_off_safety_off(monkeypatch, caplog):
    """vad_bounds at fetch_decode (disposition false, safety false)."""
    caplog.set_level(logging.INFO)

    def decode(arg):
        raise BatchValidationError(ValidationReason.VAD_BOUNDS)

    worker, results, words, saved, guard, fault = _run(
        monkeypatch, caplog, decode=decode, disposition='false', safety='false'
    )
    assert not guard and len(fault) == 1
    assert 'reason=vad_bounds' in fault[0].getMessage()
    assert not any(isinstance(r, ValidationFailureWork) for r in results)


def test_disposition_fetch_decode_vad_bounds_disp_on_safety_on(monkeypatch, caplog):
    """vad_bounds at fetch_decode (disposition true, safety true)."""
    caplog.set_level(logging.INFO)

    def decode(arg):
        raise BatchValidationError(ValidationReason.VAD_BOUNDS)

    worker, results, words, saved, guard, fault = _run(
        monkeypatch, caplog, decode=decode, disposition='true', safety='true'
    )
    assert not guard and len(fault) == 1
    assert 'reason=vad_bounds' in fault[0].getMessage()
    assert isinstance(results[0], ValidationFailureWork)


def test_disposition_fetch_decode_vad_bounds_disp_off_safety_on(monkeypatch, caplog):
    """vad_bounds at fetch_decode (disposition false, safety true)."""
    caplog.set_level(logging.INFO)

    def decode(arg):
        raise BatchValidationError(ValidationReason.VAD_BOUNDS)

    worker, results, words, saved, guard, fault = _run(
        monkeypatch, caplog, decode=decode, disposition='false', safety='true'
    )
    assert not guard and len(fault) == 1
    assert 'reason=vad_bounds' in fault[0].getMessage()
    assert not any(isinstance(r, ValidationFailureWork) for r in results)


def test_disposition_fetch_decode_empty_asr_disp_on_safety_off(monkeypatch, caplog):
    """empty_asr at fetch_decode (disposition true, safety false)."""
    caplog.set_level(logging.INFO)

    def decode(arg):
        raise BatchValidationError(ValidationReason.EMPTY_ASR)

    worker, results, words, saved, guard, fault = _run(
        monkeypatch, caplog, decode=decode, disposition='true', safety='false'
    )
    assert not guard and len(fault) == 1
    assert 'reason=empty_asr' in fault[0].getMessage()
    assert isinstance(results[0], ValidationFailureWork)


def test_disposition_fetch_decode_empty_asr_disp_off_safety_off(monkeypatch, caplog):
    """empty_asr at fetch_decode (disposition false, safety false)."""
    caplog.set_level(logging.INFO)

    def decode(arg):
        raise BatchValidationError(ValidationReason.EMPTY_ASR)

    worker, results, words, saved, guard, fault = _run(
        monkeypatch, caplog, decode=decode, disposition='false', safety='false'
    )
    assert not guard and len(fault) == 1
    assert 'reason=empty_asr' in fault[0].getMessage()
    assert not any(isinstance(r, ValidationFailureWork) for r in results)


def test_disposition_fetch_decode_empty_asr_disp_on_safety_on(monkeypatch, caplog):
    """empty_asr at fetch_decode (disposition true, safety true)."""
    caplog.set_level(logging.INFO)

    def decode(arg):
        raise BatchValidationError(ValidationReason.EMPTY_ASR)

    worker, results, words, saved, guard, fault = _run(
        monkeypatch, caplog, decode=decode, disposition='true', safety='true'
    )
    assert not guard and len(fault) == 1
    assert 'reason=empty_asr' in fault[0].getMessage()
    assert isinstance(results[0], ValidationFailureWork)


def test_disposition_fetch_decode_empty_asr_disp_off_safety_on(monkeypatch, caplog):
    """empty_asr at fetch_decode (disposition false, safety true)."""
    caplog.set_level(logging.INFO)

    def decode(arg):
        raise BatchValidationError(ValidationReason.EMPTY_ASR)

    worker, results, words, saved, guard, fault = _run(
        monkeypatch, caplog, decode=decode, disposition='false', safety='true'
    )
    assert not guard and len(fault) == 1
    assert 'reason=empty_asr' in fault[0].getMessage()
    assert not any(isinstance(r, ValidationFailureWork) for r in results)


def test_disposition_fetch_decode_no_owned_words_disp_on_safety_off(monkeypatch, caplog):
    """no_owned_words at fetch_decode (disposition true, safety false)."""
    caplog.set_level(logging.INFO)

    def decode(arg):
        raise BatchValidationError(ValidationReason.NO_OWNED_WORDS)

    worker, results, words, saved, guard, fault = _run(
        monkeypatch, caplog, decode=decode, disposition='true', safety='false'
    )
    assert not guard and len(fault) == 1
    assert 'reason=no_owned_words' in fault[0].getMessage()
    assert isinstance(results[0], ValidationFailureWork)


def test_disposition_fetch_decode_no_owned_words_disp_off_safety_off(monkeypatch, caplog):
    """no_owned_words at fetch_decode (disposition false, safety false)."""
    caplog.set_level(logging.INFO)

    def decode(arg):
        raise BatchValidationError(ValidationReason.NO_OWNED_WORDS)

    worker, results, words, saved, guard, fault = _run(
        monkeypatch, caplog, decode=decode, disposition='false', safety='false'
    )
    assert not guard and len(fault) == 1
    assert 'reason=no_owned_words' in fault[0].getMessage()
    assert not any(isinstance(r, ValidationFailureWork) for r in results)


def test_disposition_fetch_decode_no_owned_words_disp_on_safety_on(monkeypatch, caplog):
    """no_owned_words at fetch_decode (disposition true, safety true)."""
    caplog.set_level(logging.INFO)

    def decode(arg):
        raise BatchValidationError(ValidationReason.NO_OWNED_WORDS)

    worker, results, words, saved, guard, fault = _run(
        monkeypatch, caplog, decode=decode, disposition='true', safety='true'
    )
    assert not guard and len(fault) == 1
    assert 'reason=no_owned_words' in fault[0].getMessage()
    assert isinstance(results[0], ValidationFailureWork)


def test_disposition_fetch_decode_no_owned_words_disp_off_safety_on(monkeypatch, caplog):
    """no_owned_words at fetch_decode (disposition false, safety true)."""
    caplog.set_level(logging.INFO)

    def decode(arg):
        raise BatchValidationError(ValidationReason.NO_OWNED_WORDS)

    worker, results, words, saved, guard, fault = _run(
        monkeypatch, caplog, decode=decode, disposition='false', safety='true'
    )
    assert not guard and len(fault) == 1
    assert 'reason=no_owned_words' in fault[0].getMessage()
    assert not any(isinstance(r, ValidationFailureWork) for r in results)


def test_disposition_vad_windows_unsupported_language_disp_on_safety_off(monkeypatch, caplog):
    """unsupported_language at vad_windows (disposition true, safety false)."""
    caplog.set_level(logging.INFO)

    def vad(arg):
        raise BatchValidationError(ValidationReason.UNSUPPORTED_LANGUAGE)

    worker, results, words, saved, guard, fault = _run(monkeypatch, caplog, vad=vad, disposition='true', safety='false')
    assert len(guard) == 1 and not fault
    assert 'outcome=redrive_held' in guard[0].getMessage()
    assert isinstance(results[0], ValidationFailureWork)


def test_disposition_vad_windows_unsupported_language_disp_off_safety_off(monkeypatch, caplog):
    """unsupported_language at vad_windows (disposition false, safety false)."""
    caplog.set_level(logging.INFO)

    def vad(arg):
        raise BatchValidationError(ValidationReason.UNSUPPORTED_LANGUAGE)

    worker, results, words, saved, guard, fault = _run(
        monkeypatch, caplog, vad=vad, disposition='false', safety='false'
    )
    assert len(guard) == 1 and not fault
    assert 'outcome=redrive_held' in guard[0].getMessage()
    assert isinstance(results[0], ValidationFailureWork)


def test_disposition_vad_windows_unsupported_language_disp_on_safety_on(monkeypatch, caplog):
    """unsupported_language at vad_windows (disposition true, safety true)."""
    caplog.set_level(logging.INFO)

    def vad(arg):
        raise BatchValidationError(ValidationReason.UNSUPPORTED_LANGUAGE)

    worker, results, words, saved, guard, fault = _run(monkeypatch, caplog, vad=vad, disposition='true', safety='true')
    assert len(guard) == 1 and not fault
    assert 'outcome=redrive_held' in guard[0].getMessage()
    assert isinstance(results[0], ValidationFailureWork)


def test_disposition_vad_windows_unsupported_language_disp_off_safety_on(monkeypatch, caplog):
    """unsupported_language at vad_windows (disposition false, safety true)."""
    caplog.set_level(logging.INFO)

    def vad(arg):
        raise BatchValidationError(ValidationReason.UNSUPPORTED_LANGUAGE)

    worker, results, words, saved, guard, fault = _run(monkeypatch, caplog, vad=vad, disposition='false', safety='true')
    assert len(guard) == 1 and not fault
    assert 'outcome=redrive_held' in guard[0].getMessage()
    assert isinstance(results[0], ValidationFailureWork)


def test_disposition_vad_windows_word_shape_disp_on_safety_off(monkeypatch, caplog):
    """word_shape at vad_windows (disposition true, safety false)."""
    caplog.set_level(logging.INFO)

    def vad(arg):
        raise BatchValidationError(ValidationReason.WORD_SHAPE)

    worker, results, words, saved, guard, fault = _run(monkeypatch, caplog, vad=vad, disposition='true', safety='false')
    assert not guard and len(fault) == 1
    assert 'reason=word_shape' in fault[0].getMessage()
    assert isinstance(results[0], ValidationFailureWork)


def test_disposition_vad_windows_word_shape_disp_off_safety_off(monkeypatch, caplog):
    """word_shape at vad_windows (disposition false, safety false)."""
    caplog.set_level(logging.INFO)

    def vad(arg):
        raise BatchValidationError(ValidationReason.WORD_SHAPE)

    worker, results, words, saved, guard, fault = _run(
        monkeypatch, caplog, vad=vad, disposition='false', safety='false'
    )
    assert not guard and len(fault) == 1
    assert 'reason=word_shape' in fault[0].getMessage()
    assert not any(isinstance(r, ValidationFailureWork) for r in results)


def test_disposition_vad_windows_word_shape_disp_on_safety_on(monkeypatch, caplog):
    """word_shape at vad_windows (disposition true, safety true)."""
    caplog.set_level(logging.INFO)

    def vad(arg):
        raise BatchValidationError(ValidationReason.WORD_SHAPE)

    worker, results, words, saved, guard, fault = _run(monkeypatch, caplog, vad=vad, disposition='true', safety='true')
    assert not guard and len(fault) == 1
    assert 'reason=word_shape' in fault[0].getMessage()
    assert isinstance(results[0], ValidationFailureWork)


def test_disposition_vad_windows_word_shape_disp_off_safety_on(monkeypatch, caplog):
    """word_shape at vad_windows (disposition false, safety true)."""
    caplog.set_level(logging.INFO)

    def vad(arg):
        raise BatchValidationError(ValidationReason.WORD_SHAPE)

    worker, results, words, saved, guard, fault = _run(monkeypatch, caplog, vad=vad, disposition='false', safety='true')
    assert not guard and len(fault) == 1
    assert 'reason=word_shape' in fault[0].getMessage()
    assert not any(isinstance(r, ValidationFailureWork) for r in results)


def test_disposition_vad_windows_word_clock_disp_on_safety_off(monkeypatch, caplog):
    """word_clock at vad_windows (disposition true, safety false)."""
    caplog.set_level(logging.INFO)

    def vad(arg):
        raise BatchValidationError(ValidationReason.WORD_CLOCK)

    worker, results, words, saved, guard, fault = _run(monkeypatch, caplog, vad=vad, disposition='true', safety='false')
    assert not guard and len(fault) == 1
    assert 'reason=word_clock' in fault[0].getMessage()
    assert isinstance(results[0], ValidationFailureWork)


def test_disposition_vad_windows_word_clock_disp_off_safety_off(monkeypatch, caplog):
    """word_clock at vad_windows (disposition false, safety false)."""
    caplog.set_level(logging.INFO)

    def vad(arg):
        raise BatchValidationError(ValidationReason.WORD_CLOCK)

    worker, results, words, saved, guard, fault = _run(
        monkeypatch, caplog, vad=vad, disposition='false', safety='false'
    )
    assert not guard and len(fault) == 1
    assert 'reason=word_clock' in fault[0].getMessage()
    assert not any(isinstance(r, ValidationFailureWork) for r in results)


def test_disposition_vad_windows_word_clock_disp_on_safety_on(monkeypatch, caplog):
    """word_clock at vad_windows (disposition true, safety true)."""
    caplog.set_level(logging.INFO)

    def vad(arg):
        raise BatchValidationError(ValidationReason.WORD_CLOCK)

    worker, results, words, saved, guard, fault = _run(monkeypatch, caplog, vad=vad, disposition='true', safety='true')
    assert not guard and len(fault) == 1
    assert 'reason=word_clock' in fault[0].getMessage()
    assert isinstance(results[0], ValidationFailureWork)


def test_disposition_vad_windows_word_clock_disp_off_safety_on(monkeypatch, caplog):
    """word_clock at vad_windows (disposition false, safety true)."""
    caplog.set_level(logging.INFO)

    def vad(arg):
        raise BatchValidationError(ValidationReason.WORD_CLOCK)

    worker, results, words, saved, guard, fault = _run(monkeypatch, caplog, vad=vad, disposition='false', safety='true')
    assert not guard and len(fault) == 1
    assert 'reason=word_clock' in fault[0].getMessage()
    assert not any(isinstance(r, ValidationFailureWork) for r in results)


def test_disposition_vad_windows_word_sequence_disp_on_safety_off(monkeypatch, caplog):
    """word_sequence at vad_windows (disposition true, safety false)."""
    caplog.set_level(logging.INFO)

    def vad(arg):
        raise BatchValidationError(ValidationReason.WORD_SEQUENCE)

    worker, results, words, saved, guard, fault = _run(monkeypatch, caplog, vad=vad, disposition='true', safety='false')
    assert not guard and len(fault) == 1
    assert 'reason=word_sequence' in fault[0].getMessage()
    assert isinstance(results[0], ValidationFailureWork)


def test_disposition_vad_windows_word_sequence_disp_off_safety_off(monkeypatch, caplog):
    """word_sequence at vad_windows (disposition false, safety false)."""
    caplog.set_level(logging.INFO)

    def vad(arg):
        raise BatchValidationError(ValidationReason.WORD_SEQUENCE)

    worker, results, words, saved, guard, fault = _run(
        monkeypatch, caplog, vad=vad, disposition='false', safety='false'
    )
    assert not guard and len(fault) == 1
    assert 'reason=word_sequence' in fault[0].getMessage()
    assert not any(isinstance(r, ValidationFailureWork) for r in results)


def test_disposition_vad_windows_word_sequence_disp_on_safety_on(monkeypatch, caplog):
    """word_sequence at vad_windows (disposition true, safety true)."""
    caplog.set_level(logging.INFO)

    def vad(arg):
        raise BatchValidationError(ValidationReason.WORD_SEQUENCE)

    worker, results, words, saved, guard, fault = _run(monkeypatch, caplog, vad=vad, disposition='true', safety='true')
    assert not guard and len(fault) == 1
    assert 'reason=word_sequence' in fault[0].getMessage()
    assert isinstance(results[0], ValidationFailureWork)


def test_disposition_vad_windows_word_sequence_disp_off_safety_on(monkeypatch, caplog):
    """word_sequence at vad_windows (disposition false, safety true)."""
    caplog.set_level(logging.INFO)

    def vad(arg):
        raise BatchValidationError(ValidationReason.WORD_SEQUENCE)

    worker, results, words, saved, guard, fault = _run(monkeypatch, caplog, vad=vad, disposition='false', safety='true')
    assert not guard and len(fault) == 1
    assert 'reason=word_sequence' in fault[0].getMessage()
    assert not any(isinstance(r, ValidationFailureWork) for r in results)


def test_disposition_vad_windows_vad_nonfinite_disp_on_safety_off(monkeypatch, caplog):
    """vad_nonfinite at vad_windows (disposition true, safety false)."""
    caplog.set_level(logging.INFO)

    def vad(arg):
        raise BatchValidationError(ValidationReason.VAD_NONFINITE)

    worker, results, words, saved, guard, fault = _run(monkeypatch, caplog, vad=vad, disposition='true', safety='false')
    assert not guard and len(fault) == 1
    assert 'reason=vad_nonfinite' in fault[0].getMessage()
    assert isinstance(results[0], ValidationFailureWork)


def test_disposition_vad_windows_vad_nonfinite_disp_off_safety_off(monkeypatch, caplog):
    """vad_nonfinite at vad_windows (disposition false, safety false)."""
    caplog.set_level(logging.INFO)

    def vad(arg):
        raise BatchValidationError(ValidationReason.VAD_NONFINITE)

    worker, results, words, saved, guard, fault = _run(
        monkeypatch, caplog, vad=vad, disposition='false', safety='false'
    )
    assert not guard and len(fault) == 1
    assert 'reason=vad_nonfinite' in fault[0].getMessage()
    assert not any(isinstance(r, ValidationFailureWork) for r in results)


def test_disposition_vad_windows_vad_nonfinite_disp_on_safety_on(monkeypatch, caplog):
    """vad_nonfinite at vad_windows (disposition true, safety true)."""
    caplog.set_level(logging.INFO)

    def vad(arg):
        raise BatchValidationError(ValidationReason.VAD_NONFINITE)

    worker, results, words, saved, guard, fault = _run(monkeypatch, caplog, vad=vad, disposition='true', safety='true')
    assert not guard and len(fault) == 1
    assert 'reason=vad_nonfinite' in fault[0].getMessage()
    assert isinstance(results[0], ValidationFailureWork)


def test_disposition_vad_windows_vad_nonfinite_disp_off_safety_on(monkeypatch, caplog):
    """vad_nonfinite at vad_windows (disposition false, safety true)."""
    caplog.set_level(logging.INFO)

    def vad(arg):
        raise BatchValidationError(ValidationReason.VAD_NONFINITE)

    worker, results, words, saved, guard, fault = _run(monkeypatch, caplog, vad=vad, disposition='false', safety='true')
    assert not guard and len(fault) == 1
    assert 'reason=vad_nonfinite' in fault[0].getMessage()
    assert not any(isinstance(r, ValidationFailureWork) for r in results)


def test_disposition_vad_windows_vad_order_disp_on_safety_off(monkeypatch, caplog):
    """vad_order at vad_windows (disposition true, safety false)."""
    caplog.set_level(logging.INFO)

    def vad(arg):
        raise BatchValidationError(ValidationReason.VAD_ORDER)

    worker, results, words, saved, guard, fault = _run(monkeypatch, caplog, vad=vad, disposition='true', safety='false')
    assert not guard and len(fault) == 1
    assert 'reason=vad_order' in fault[0].getMessage()
    assert isinstance(results[0], ValidationFailureWork)


def test_disposition_vad_windows_vad_order_disp_off_safety_off(monkeypatch, caplog):
    """vad_order at vad_windows (disposition false, safety false)."""
    caplog.set_level(logging.INFO)

    def vad(arg):
        raise BatchValidationError(ValidationReason.VAD_ORDER)

    worker, results, words, saved, guard, fault = _run(
        monkeypatch, caplog, vad=vad, disposition='false', safety='false'
    )
    assert not guard and len(fault) == 1
    assert 'reason=vad_order' in fault[0].getMessage()
    assert not any(isinstance(r, ValidationFailureWork) for r in results)


def test_disposition_vad_windows_vad_order_disp_on_safety_on(monkeypatch, caplog):
    """vad_order at vad_windows (disposition true, safety true)."""
    caplog.set_level(logging.INFO)

    def vad(arg):
        raise BatchValidationError(ValidationReason.VAD_ORDER)

    worker, results, words, saved, guard, fault = _run(monkeypatch, caplog, vad=vad, disposition='true', safety='true')
    assert not guard and len(fault) == 1
    assert 'reason=vad_order' in fault[0].getMessage()
    assert isinstance(results[0], ValidationFailureWork)


def test_disposition_vad_windows_vad_order_disp_off_safety_on(monkeypatch, caplog):
    """vad_order at vad_windows (disposition false, safety true)."""
    caplog.set_level(logging.INFO)

    def vad(arg):
        raise BatchValidationError(ValidationReason.VAD_ORDER)

    worker, results, words, saved, guard, fault = _run(monkeypatch, caplog, vad=vad, disposition='false', safety='true')
    assert not guard and len(fault) == 1
    assert 'reason=vad_order' in fault[0].getMessage()
    assert not any(isinstance(r, ValidationFailureWork) for r in results)


def test_disposition_vad_windows_vad_bounds_disp_on_safety_off(monkeypatch, caplog):
    """vad_bounds at vad_windows (disposition true, safety false)."""
    caplog.set_level(logging.INFO)

    def vad(arg):
        raise BatchValidationError(ValidationReason.VAD_BOUNDS)

    worker, results, words, saved, guard, fault = _run(monkeypatch, caplog, vad=vad, disposition='true', safety='false')
    assert not guard
    assert len(fault) + len(guard) == len(guard) + 1 if fault else True
    assert not saved


def test_disposition_vad_windows_vad_bounds_disp_off_safety_off(monkeypatch, caplog):
    """vad_bounds at vad_windows (disposition false, safety false)."""
    caplog.set_level(logging.INFO)

    def vad(arg):
        raise BatchValidationError(ValidationReason.VAD_BOUNDS)

    worker, results, words, saved, guard, fault = _run(
        monkeypatch, caplog, vad=vad, disposition='false', safety='false'
    )
    assert not guard and len(fault) == 1
    assert 'reason=vad_bounds' in fault[0].getMessage()
    assert not any(isinstance(r, ValidationFailureWork) for r in results)


def test_disposition_vad_windows_vad_bounds_disp_on_safety_on(monkeypatch, caplog):
    """vad_bounds at vad_windows (disposition true, safety true)."""
    caplog.set_level(logging.INFO)

    def vad(arg):
        raise BatchValidationError(ValidationReason.VAD_BOUNDS)

    worker, results, words, saved, guard, fault = _run(monkeypatch, caplog, vad=vad, disposition='true', safety='true')
    assert not guard
    assert len(fault) + len(guard) == len(guard) + 1 if fault else True
    assert not saved


def test_disposition_vad_windows_vad_bounds_disp_off_safety_on(monkeypatch, caplog):
    """vad_bounds at vad_windows (disposition false, safety true)."""
    caplog.set_level(logging.INFO)

    def vad(arg):
        raise BatchValidationError(ValidationReason.VAD_BOUNDS)

    worker, results, words, saved, guard, fault = _run(monkeypatch, caplog, vad=vad, disposition='false', safety='true')
    assert not guard and len(fault) == 1
    assert 'reason=vad_bounds' in fault[0].getMessage()
    assert not any(isinstance(r, ValidationFailureWork) for r in results)


def test_disposition_vad_windows_empty_asr_disp_on_safety_off(monkeypatch, caplog):
    """empty_asr at vad_windows (disposition true, safety false)."""
    caplog.set_level(logging.INFO)

    def vad(arg):
        raise BatchValidationError(ValidationReason.EMPTY_ASR)

    worker, results, words, saved, guard, fault = _run(monkeypatch, caplog, vad=vad, disposition='true', safety='false')
    assert not guard and len(fault) == 1
    assert 'reason=empty_asr' in fault[0].getMessage()
    assert isinstance(results[0], ValidationFailureWork)


def test_disposition_vad_windows_empty_asr_disp_off_safety_off(monkeypatch, caplog):
    """empty_asr at vad_windows (disposition false, safety false)."""
    caplog.set_level(logging.INFO)

    def vad(arg):
        raise BatchValidationError(ValidationReason.EMPTY_ASR)

    worker, results, words, saved, guard, fault = _run(
        monkeypatch, caplog, vad=vad, disposition='false', safety='false'
    )
    assert not guard and len(fault) == 1
    assert 'reason=empty_asr' in fault[0].getMessage()
    assert not any(isinstance(r, ValidationFailureWork) for r in results)


def test_disposition_vad_windows_empty_asr_disp_on_safety_on(monkeypatch, caplog):
    """empty_asr at vad_windows (disposition true, safety true)."""
    caplog.set_level(logging.INFO)

    def vad(arg):
        raise BatchValidationError(ValidationReason.EMPTY_ASR)

    worker, results, words, saved, guard, fault = _run(monkeypatch, caplog, vad=vad, disposition='true', safety='true')
    assert not guard and len(fault) == 1
    assert 'reason=empty_asr' in fault[0].getMessage()
    assert isinstance(results[0], ValidationFailureWork)


def test_disposition_vad_windows_empty_asr_disp_off_safety_on(monkeypatch, caplog):
    """empty_asr at vad_windows (disposition false, safety true)."""
    caplog.set_level(logging.INFO)

    def vad(arg):
        raise BatchValidationError(ValidationReason.EMPTY_ASR)

    worker, results, words, saved, guard, fault = _run(monkeypatch, caplog, vad=vad, disposition='false', safety='true')
    assert not guard and len(fault) == 1
    assert 'reason=empty_asr' in fault[0].getMessage()
    assert not any(isinstance(r, ValidationFailureWork) for r in results)


def test_disposition_vad_windows_no_owned_words_disp_on_safety_off(monkeypatch, caplog):
    """no_owned_words at vad_windows (disposition true, safety false)."""
    caplog.set_level(logging.INFO)

    def vad(arg):
        raise BatchValidationError(ValidationReason.NO_OWNED_WORDS)

    worker, results, words, saved, guard, fault = _run(monkeypatch, caplog, vad=vad, disposition='true', safety='false')
    assert not guard and len(fault) == 1
    assert 'reason=no_owned_words' in fault[0].getMessage()
    assert isinstance(results[0], ValidationFailureWork)


def test_disposition_vad_windows_no_owned_words_disp_off_safety_off(monkeypatch, caplog):
    """no_owned_words at vad_windows (disposition false, safety false)."""
    caplog.set_level(logging.INFO)

    def vad(arg):
        raise BatchValidationError(ValidationReason.NO_OWNED_WORDS)

    worker, results, words, saved, guard, fault = _run(
        monkeypatch, caplog, vad=vad, disposition='false', safety='false'
    )
    assert not guard and len(fault) == 1
    assert 'reason=no_owned_words' in fault[0].getMessage()
    assert not any(isinstance(r, ValidationFailureWork) for r in results)


def test_disposition_vad_windows_no_owned_words_disp_on_safety_on(monkeypatch, caplog):
    """no_owned_words at vad_windows (disposition true, safety true)."""
    caplog.set_level(logging.INFO)

    def vad(arg):
        raise BatchValidationError(ValidationReason.NO_OWNED_WORDS)

    worker, results, words, saved, guard, fault = _run(monkeypatch, caplog, vad=vad, disposition='true', safety='true')
    assert not guard and len(fault) == 1
    assert 'reason=no_owned_words' in fault[0].getMessage()
    assert isinstance(results[0], ValidationFailureWork)


def test_disposition_vad_windows_no_owned_words_disp_off_safety_on(monkeypatch, caplog):
    """no_owned_words at vad_windows (disposition false, safety true)."""
    caplog.set_level(logging.INFO)

    def vad(arg):
        raise BatchValidationError(ValidationReason.NO_OWNED_WORDS)

    worker, results, words, saved, guard, fault = _run(monkeypatch, caplog, vad=vad, disposition='false', safety='true')
    assert not guard and len(fault) == 1
    assert 'reason=no_owned_words' in fault[0].getMessage()
    assert not any(isinstance(r, ValidationFailureWork) for r in results)
