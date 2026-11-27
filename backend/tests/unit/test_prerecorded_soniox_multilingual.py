"""Legacy sync's multilingual audio runs Soniox first; Velma is the fallback (SCA-4917)."""

from io import BytesIO
from types import SimpleNamespace
from unittest.mock import Mock
import wave

import pytest

from utils.stt import pre_recorded as stt
from utils.stt import soniox_multilingual
from utils.stt.parakeet_request_metrics import parakeet_caller
from utils.stt.prerecorded_deadline import verification_deadline
from utils.stt.soniox_batch import SonioxBatchError
from utils.stt.vendor_guard import reset_vendor_guard_for_tests

SONIOX_WORDS = [{'timestamp': [0.0, 1.0], 'speaker': 'SPEAKER_00', 'text': '你好'}]
VELMA_WORDS = [{'timestamp': [0.0, 1.0], 'speaker': 'SPEAKER_00', 'text': 'knee how'}]


def wav_bytes(seconds=2, sample_rate=16000):
    output = BytesIO()
    with wave.open(output, 'wb') as writer:
        writer.setparams((1, 2, sample_rate, 0, 'NONE', 'not compressed'))
        writer.writeframes(b'\x01\x00' * int(seconds * sample_rate))
    return output.getvalue()


@pytest.fixture(autouse=True)
def defaults(monkeypatch):
    monkeypatch.delenv('STT_PRERECORDED_SONIOX_MULTILINGUAL_ENABLED', raising=False)
    monkeypatch.delenv('PRERECORDED_SONIOX_FAILOVER_ENABLED', raising=False)
    monkeypatch.setenv('SONIOX_API_KEY', 'synthetic-test-key')
    reset_vendor_guard_for_tests()
    yield
    reset_vendor_guard_for_tests()


@pytest.fixture
def vendors(monkeypatch):
    velma = Mock(return_value=(VELMA_WORDS, 'en'))
    soniox = Mock(return_value=(SONIOX_WORDS, 'zh'))
    fallback = Mock()
    burn = Mock()
    monkeypatch.setattr(stt, 'modulate_prerecorded_from_bytes', velma)
    # The Modulate-credit failover hop keeps its own Soniox handle; it must never fire here.
    monkeypatch.setattr(stt, 'soniox_transcribe', Mock(side_effect=AssertionError('failover hop')))
    monkeypatch.setattr(soniox_multilingual, 'soniox_transcribe', soniox)
    monkeypatch.setattr(soniox_multilingual, 'record_fallback', fallback)
    monkeypatch.setattr(soniox_multilingual, 'record_vendor_burn', burn)
    return SimpleNamespace(velma=velma, soniox=soniox, fallback=fallback, burn=burn)


def sync_call(language='multi', *, caller='sync_fresh', seconds=2, **kwargs):
    provider = stt.ModulatePrerecordedProvider()
    with parakeet_caller(caller):
        result = provider.transcribe_bytes(
            wav_bytes(seconds), diarize=True, return_language=True, language=language, **kwargs
        )
    return provider, result


def test_sync_multilingual_audio_is_served_by_soniox(vendors):
    provider, result = sync_call('multi')

    assert result == (SONIOX_WORDS, 'zh')
    assert provider.served_provider == 'soniox'
    vendors.velma.assert_not_called()
    assert vendors.soniox.call_args.args[1] == 2.0
    assert vendors.soniox.call_args.kwargs == {
        'language': 'multi',
        'failover': True,
        'diarize': True,
        'retry_rate_limits': False,
    }
    vendors.burn.assert_called_once_with('stt', 'ok', 2.0, provider='soniox')
    vendors.fallback.assert_not_called()


@pytest.mark.parametrize('caller', ['sync_backfill', 'sync_unknown'])
def test_every_sync_lane_counts(vendors, caller):
    provider, _ = sync_call('multi', caller=caller)

    assert provider.served_provider == 'soniox'


@pytest.mark.parametrize('language', ['zh', 'ja', 'ko', 'hi', 'zh-CN'])
def test_languages_velma_is_weak_on_go_to_soniox(vendors, language):
    provider, _ = sync_call(language)

    assert provider.served_provider == 'soniox'


@pytest.mark.parametrize('language', ['en', 'es', 'fr', 'de', 'it', 'pt', 'nl', 'en-US'])
def test_velma_first_languages_keep_velma(vendors, language):
    provider, result = sync_call(language)

    assert result == (VELMA_WORDS, 'en')
    assert provider.served_provider == 'modulate'
    vendors.soniox.assert_not_called()


def test_a_language_soniox_cannot_take_as_a_hint_keeps_velma(vendors):
    provider, _ = sync_call('tlh')

    assert provider.served_provider == 'modulate'
    vendors.soniox.assert_not_called()


@pytest.mark.parametrize('caller', ['voice_message', 'batch_recovery', 'shadow', 'other'])
def test_callers_outside_legacy_sync_keep_velma(vendors, caller):
    provider, _ = sync_call('multi', caller=caller)

    assert provider.served_provider == 'modulate'
    vendors.soniox.assert_not_called()


def test_no_caller_context_keeps_velma(vendors):
    provider = stt.ModulatePrerecordedProvider()
    provider.transcribe_bytes(wav_bytes(), language='multi')

    assert provider.served_provider == 'modulate'
    vendors.soniox.assert_not_called()


@pytest.mark.parametrize('kind', ['timeout', 'error_5xx', 'rate_limited', 'credit_refusal', 'invalid_response'])
def test_a_soniox_failure_falls_back_to_velma_on_the_same_audio(vendors, kind):
    vendors.soniox.side_effect = SonioxBatchError(kind, submitted=True)

    provider, result = sync_call('multi')

    assert result == (VELMA_WORDS, 'en')
    assert provider.served_provider == 'modulate'
    assert vendors.velma.call_count == 1
    vendors.burn.assert_called_once_with('stt', 'error', 2.0, provider='soniox')
    event = vendors.fallback.call_args.kwargs
    assert (event['from_mode'], event['to_mode'], event['outcome']) == ('soniox', 'modulate', 'degraded')
    assert event['reason'] == {
        'timeout': 'timeout',
        'rate_limited': 'provider_rate_limited',
        'credit_refusal': 'provider_budget_exhausted',
    }.get(kind, 'other')


def test_a_local_refusal_falls_back_without_counting_soniox_audio(vendors):
    vendors.soniox.side_effect = SonioxBatchError('refused')

    provider, _ = sync_call('multi')

    assert provider.served_provider == 'modulate'
    vendors.burn.assert_not_called()


def test_an_unexpected_soniox_error_falls_back(vendors):
    vendors.soniox.side_effect = RuntimeError('boom')

    provider, _ = sync_call('multi')

    assert provider.served_provider == 'modulate'


def test_an_empty_soniox_transcript_is_the_answer(vendors):
    vendors.soniox.return_value = ([], 'multi')

    provider, result = sync_call('multi')

    assert result == ([], 'multi')
    assert provider.served_provider == 'soniox'
    vendors.velma.assert_not_called()


def test_kill_switch_restores_velma_first(vendors, monkeypatch):
    monkeypatch.setenv('STT_PRERECORDED_SONIOX_MULTILINGUAL_ENABLED', 'false')

    provider, _ = sync_call('multi')

    assert provider.served_provider == 'modulate'
    vendors.soniox.assert_not_called()


def test_missing_soniox_key_keeps_velma(vendors, monkeypatch):
    monkeypatch.delenv('SONIOX_API_KEY')

    provider, _ = sync_call('multi')

    assert provider.served_provider == 'modulate'
    vendors.soniox.assert_not_called()


def test_audio_longer_than_the_soniox_deadline_bound_keeps_velma(vendors):
    provider, _ = sync_call('multi', seconds=soniox_multilingual.MAX_SECONDS + 1)

    assert provider.served_provider == 'modulate'
    vendors.soniox.assert_not_called()


def test_a_retry_attempt_does_not_try_soniox_again(vendors):
    provider, _ = sync_call('multi', attempts=1)

    assert provider.served_provider == 'modulate'
    vendors.soniox.assert_not_called()


def test_held_single_attempt_keeps_velma(vendors):
    with stt.held_single_attempt():
        provider, _ = sync_call('multi')

    assert provider.served_provider == 'modulate'
    vendors.soniox.assert_not_called()


def test_speaker_verification_keeps_velma(vendors):
    token = verification_deadline.set(10**12)
    try:
        provider, _ = sync_call('multi')
    finally:
        verification_deadline.reset(token)

    assert provider.served_provider == 'modulate'
    vendors.soniox.assert_not_called()


def test_without_return_language_only_words_are_returned(vendors):
    with parakeet_caller('sync_fresh'):
        result = stt.modulate_prerecorded_from_bytes_with_soniox(wav_bytes(), language='multi')

    assert result == SONIOX_WORDS
