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
    soniox_multilingual._TRIED.clear()
    reset_vendor_guard_for_tests()
    yield
    soniox_multilingual._TRIED.clear()
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


@pytest.mark.parametrize('language', ['zh', 'ja', 'ko', 'hi', 'zh-CN', 'es', 'fr', 'de', 'sv'])
def test_languages_velma_is_weak_on_go_to_soniox(vendors, language):
    provider, _ = sync_call(language)

    assert provider.served_provider == 'soniox'


@pytest.mark.parametrize('language', ['en', 'en-US', 'en-GB'])
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


@pytest.mark.parametrize('kind', ['refused', 'timeout', 'error_5xx'])
def test_an_unsubmitted_failure_falls_back_without_counting_soniox_audio(vendors, kind):
    vendors.soniox.side_effect = SonioxBatchError(kind, submitted=False)

    provider, _ = sync_call('multi')

    assert provider.served_provider == 'modulate'
    vendors.burn.assert_not_called()


def test_an_unexpected_soniox_error_falls_back(vendors):
    vendors.soniox.side_effect = RuntimeError('boom')

    provider, _ = sync_call('multi')

    assert provider.served_provider == 'modulate'


def test_an_empty_soniox_transcript_is_the_answer_and_the_empty_retry_runs_velma(vendors):
    vendors.soniox.return_value = ([], 'multi')

    provider, result = sync_call('multi')

    assert result == ([], 'multi')
    assert provider.served_provider == 'soniox'
    vendors.velma.assert_not_called()
    # Legacy sync's bounded empty retry calls again with attempts=0: the same audio now goes to Velma.
    provider, result = sync_call('multi')

    assert result == (VELMA_WORDS, 'en')
    assert provider.served_provider == 'modulate'
    assert vendors.soniox.call_count == 1


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


def test_a_failed_soniox_first_attempt_is_never_followed_by_a_second_soniox_submission(vendors):
    from config.prerecorded_stt import TranscriptionOutcome
    from utils.stt.outcomes import TranscriptionFailure

    vendors.soniox.side_effect = SonioxBatchError('timeout', submitted=True)
    vendors.velma.side_effect = TranscriptionFailure(
        TranscriptionOutcome.PROVIDER_BUDGET_EXHAUSTED, provider='modulate', retryable=False
    )

    with parakeet_caller('sync_fresh'), pytest.raises(TranscriptionFailure):
        stt.modulate_prerecorded_from_bytes_with_soniox(wav_bytes(), language='multi')

    assert vendors.soniox.call_count == 1
    assert vendors.velma.call_count == 1
    stt.soniox_transcribe.assert_not_called()  # the credit-refusal hop never re-sent the audio to Soniox


def test_a_full_process_sends_the_file_to_velma_without_waiting(vendors, monkeypatch):
    import threading

    monkeypatch.setattr(soniox_multilingual, '_IN_FLIGHT', threading.BoundedSemaphore(1))
    soniox_multilingual._IN_FLIGHT.acquire()
    try:
        provider, _ = sync_call('multi')
    finally:
        soniox_multilingual._IN_FLIGHT.release()

    assert provider.served_provider == 'modulate'
    vendors.soniox.assert_not_called()


def test_the_in_flight_slot_is_released_after_success_and_failure(vendors, monkeypatch):
    import threading

    monkeypatch.setattr(soniox_multilingual, '_IN_FLIGHT', threading.BoundedSemaphore(1))
    sync_call('multi', seconds=2)
    vendors.soniox.side_effect = SonioxBatchError('timeout', submitted=True)
    sync_call('multi', seconds=3)
    vendors.soniox.side_effect = None
    provider, _ = sync_call('multi', seconds=4)

    assert provider.served_provider == 'soniox'
    assert vendors.soniox.call_count == 3


def test_legacy_sync_url_path_is_served_by_soniox(vendors, monkeypatch):
    audio = wav_bytes(2)

    class Response:
        content = audio

        def raise_for_status(self):
            return None

    class Client:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def get(self, url):
            return Response()

    monkeypatch.setattr(stt.httpx, 'Client', Client)
    provider = stt.ModulatePrerecordedProvider()
    with parakeet_caller('sync_fresh'):
        result = provider.transcribe_url('https://signed.example/audio.wav', return_language=True, language=None)

    assert result == (SONIOX_WORDS, 'zh')
    assert provider.served_provider == 'soniox'
    vendors.velma.assert_not_called()


def test_a_code_switched_transcript_is_named_by_its_majority_language():
    from utils.stt.soniox_batch import transcript_words

    tokens = [
        {'text': '我们今天去公园散步', 'start_ms': 0, 'end_ms': 900, 'speaker': '1', 'language': 'zh'},
        {'text': ' okay', 'start_ms': 1000, 'end_ms': 1200, 'speaker': '1', 'language': 'en'},
    ]
    _, language = transcript_words({'text': '我们今天去公园散步 okay', 'tokens': tokens}, 2.0)

    assert language == 'zh'


def test_after_a_failed_soniox_attempt_the_empty_retry_runs_velma_only(vendors):
    vendors.soniox.side_effect = SonioxBatchError('timeout', submitted=True)
    vendors.velma.return_value = ([], 'multi')

    sync_call('multi')
    provider, _ = sync_call('multi')  # legacy sync's bounded empty retry: attempts=0 again

    assert vendors.soniox.call_count == 1
    assert vendors.velma.call_count == 2
    assert provider.served_provider == 'modulate'


def test_a_skipped_soniox_first_attempt_keeps_the_credit_refusal_hop(vendors, monkeypatch):
    import threading

    from config.prerecorded_stt import TranscriptionOutcome
    from utils.stt.outcomes import TranscriptionFailure

    monkeypatch.setattr(soniox_multilingual, '_IN_FLIGHT', threading.BoundedSemaphore(1))
    soniox_multilingual._IN_FLIGHT.acquire()  # Soniox-first is skipped (full process), never attempted
    hop = Mock(return_value=(SONIOX_WORDS, 'zh'))
    monkeypatch.setattr(stt, 'soniox_transcribe', hop)
    monkeypatch.setattr(stt, 'record_fallback', Mock())
    monkeypatch.setattr(stt, 'record_vendor_burn', Mock())
    vendors.velma.side_effect = TranscriptionFailure(
        TranscriptionOutcome.PROVIDER_BUDGET_EXHAUSTED, provider='modulate', retryable=False
    )
    try:
        with parakeet_caller('sync_fresh'):
            result = stt.modulate_prerecorded_from_bytes_with_soniox(wav_bytes(), language='multi')
    finally:
        soniox_multilingual._IN_FLIGHT.release()

    assert result == SONIOX_WORDS
    vendors.soniox.assert_not_called()
    assert hop.call_count == 1


def test_the_attempt_memo_expires(vendors, monkeypatch):
    monkeypatch.setattr(soniox_multilingual, 'TRIED_SECONDS', -1.0)
    vendors.soniox.side_effect = SonioxBatchError('timeout', submitted=True)

    sync_call('multi')
    vendors.soniox.side_effect = None
    provider, _ = sync_call('multi')

    assert provider.served_provider == 'soniox'
    assert vendors.soniox.call_count == 2


def test_production_sync_context_reaches_the_executor_thread(vendors):
    import asyncio

    from utils.executors import run_blocking, sync_executor
    from utils.observability.sync_phases import sync_attempt

    provider = stt.ModulatePrerecordedProvider()

    @sync_attempt
    async def attempt(sync_lane='fresh'):
        return await run_blocking(sync_executor, provider.transcribe_bytes, wav_bytes(), language='multi')

    result = asyncio.run(attempt())

    assert result == SONIOX_WORDS
    assert provider.served_provider == 'soniox'
