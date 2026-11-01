"""Silent PCM, invalid evidence, quiet positive spans and paid-call boundaries."""

import io
import wave
from unittest.mock import Mock

import pytest

from utils.sync import empty_recovery as recovery
from utils.stt.outcomes import TranscriptionFailure


def wav_bytes(rate=16000, width=2):
    out = io.BytesIO()
    with wave.open(out, 'wb') as wav:
        wav.setparams((1, width, rate, 0, 'NONE', 'not compressed'))
        wav.writeframes(bytes(rate * width))
    return out.getvalue()


def setup_audio(tmp_path, monkeypatch, spans, **kw):
    path = tmp_path / 'synthetic.wav'
    path.write_bytes(wav_bytes(**kw))
    # Exercise the real shared canonical WAV and strict-span validation.
    original = recovery.inspect_audio
    monkeypatch.setattr(recovery, 'inspect_audio', lambda item, audio: original(item, audio, vad=lambda pcm: spans))
    return path


@pytest.mark.parametrize('rate,width', [(16000, 2), (8000, 1), (48000, 2)])
def test_zero_strict_spans_is_the_only_silence_without_paid_call(tmp_path, monkeypatch, rate, width):
    path = setup_audio(tmp_path, monkeypatch, [], rate=rate, width=width)
    dispatch, authorize = Mock(), Mock()
    words, language, duration, spans = recovery.recover(path, transcribe=dispatch, authorize=authorize)
    assert words == [] and spans == [] and abs(duration - 1) <= 0.001
    dispatch.assert_not_called()
    authorize.assert_not_called()


def test_quiet_positive_span_uses_independent_multilingual_once(tmp_path, monkeypatch):
    path = setup_audio(tmp_path, monkeypatch, [{'start': 0.1, 'end': 0.8}])
    dispatch = Mock(return_value=([{'text': 'Synthetic words', 'timestamp': [0.1, 0.8]}], 'vi'))
    authorize = Mock()
    words, language, duration, spans = recovery.recover(path, transcribe=dispatch, authorize=authorize)
    assert words[0]['text'] == 'Synthetic words' and language == 'vi'
    dispatch.assert_called_once()
    authorize.assert_called_once()
    assert dispatch.call_args.kwargs == {'return_language': True, 'language': 'multi', 'attempts': 2}
    with wave.open(io.BytesIO(dispatch.call_args.args[0]), 'rb') as wav:
        assert (wav.getnchannels(), wav.getsampwidth(), wav.getframerate()) == (1, 2, 16000)


@pytest.mark.parametrize('spans', [None, {}, [{'start': 0, 'end': 5}], [{'start': float('nan'), 'end': 0.8}]])
def test_uncertain_vad_never_becomes_silence_or_paid_work(tmp_path, monkeypatch, spans):
    path = setup_audio(tmp_path, monkeypatch, spans)
    dispatch = Mock()
    with pytest.raises(RuntimeError, match='inspection failed'):
        recovery.recover(path, transcribe=dispatch, authorize=Mock())
    dispatch.assert_not_called()


@pytest.mark.parametrize(
    'response',
    [
        ([], 'multi'),
        None,
        ({}, 'en'),
        ([{'text': '', 'timestamp': [0, 0.5]}], 'en'),
        ([{'text': 'Synthetic', 'timestamp': [0, 20]}], 'en'),
    ],
)
def test_positive_vad_empty_or_malformed_provider_never_becomes_silence(tmp_path, monkeypatch, response):
    path = setup_audio(tmp_path, monkeypatch, [{'start': 0.1, 'end': 0.8}])
    dispatch = Mock(return_value=response)
    with pytest.raises((TranscriptionFailure, RuntimeError)):
        recovery.recover(path, transcribe=dispatch, authorize=Mock())
    dispatch.assert_called_once()


def test_funded_admission_denial_prevents_paid_call(tmp_path, monkeypatch):
    path = setup_audio(tmp_path, monkeypatch, [{'start': 0.1, 'end': 0.8}])
    dispatch = Mock()
    with pytest.raises(RuntimeError, match='denied'):
        recovery.recover(path, transcribe=dispatch, authorize=Mock(side_effect=RuntimeError('denied')))
    dispatch.assert_not_called()


def test_truncated_audio_is_not_silence(tmp_path):
    path = tmp_path / 'synthetic.wav'
    path.write_bytes(wav_bytes()[:-10])
    dispatch = Mock()
    with pytest.raises(RuntimeError, match='inspection failed'):
        recovery.recover(path, transcribe=dispatch, authorize=Mock())
    dispatch.assert_not_called()


def test_flag_reads_current_environment_and_defaults_dark(monkeypatch):
    monkeypatch.delenv('SYNC_EMPTY_MULTILINGUAL_RECOVERY_ENABLED', raising=False)
    assert recovery.enabled() is False
    monkeypatch.setenv('SYNC_EMPTY_MULTILINGUAL_RECOVERY_ENABLED', 'true')
    assert recovery.enabled() is True


@pytest.mark.parametrize('result', ['silence', 'speech', 'provider_error', 'denied', 'inspection_error'])
def test_strict_observation_precedes_dispatch_and_includes_failed_recovery(tmp_path, monkeypatch, result):
    spans = [] if result == 'silence' else [{'start': 0.1, 'end': 0.8}]
    path = setup_audio(tmp_path, monkeypatch, None if result == 'inspection_error' else spans)
    observed = []

    def observe(duration, verdict):
        observed.append((duration, verdict))

    def authorize():
        assert observed == [(1.0, spans)]
        if result == 'denied':
            raise RuntimeError('denied')

    def dispatch(*args, **kwargs):
        assert observed == [(1.0, spans)]
        if result == 'provider_error':
            return [], 'multi'
        return [{'text': 'Synthetic', 'timestamp': [0.1, 0.8]}], 'vi'

    if result in ('provider_error', 'denied', 'inspection_error'):
        with pytest.raises((RuntimeError, TranscriptionFailure)):
            recovery.recover(path, transcribe=dispatch, authorize=authorize, observe=observe)
    else:
        recovery.recover(path, transcribe=dispatch, authorize=authorize, observe=observe)
    assert observed == ([(None, None)] if result == 'inspection_error' else [(1.0, spans)])
