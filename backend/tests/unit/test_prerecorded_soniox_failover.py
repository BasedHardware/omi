"""Modulate credit/breaker refusal has exactly one bounded Soniox replacement."""

from io import BytesIO
from types import SimpleNamespace
from unittest.mock import Mock
import wave

import httpx
import pytest

from config.prerecorded_stt import PrerecordedSTTConfigurationError, TranscriptionOutcome
from config.prerecorded_vendor import soniox_failover_enabled
from utils import chat
from utils.stt import pre_recorded as stt
from utils.stt.outcomes import TranscriptionFailure
from utils.stt.soniox_batch import SonioxBatchError
from utils.stt.vendor_guard import (
    BREAKER_FAILURE_THRESHOLD,
    ModulateQuotaError,
    record_breaker_quota_error,
    reset_vendor_guard_for_tests,
)

WORDS = [{'timestamp': [0.0, 1.0], 'speaker': 'SPEAKER_00', 'text': 'recovered'}]


def wav_bytes(seconds=2, sample_rate=16000):
    output = BytesIO()
    with wave.open(output, 'wb') as writer:
        writer.setparams((1, 2, sample_rate, 0, 'NONE', 'not compressed'))
        writer.writeframes(b'\x01\x00' * int(seconds * sample_rate))
    return output.getvalue()


@pytest.fixture(autouse=True)
def failover_defaults(monkeypatch):
    monkeypatch.delenv('PRERECORDED_SONIOX_FAILOVER_ENABLED', raising=False)
    monkeypatch.setenv('SONIOX_API_KEY', 'synthetic-test-key')
    reset_vendor_guard_for_tests()
    yield
    reset_vendor_guard_for_tests()


@pytest.fixture
def vendors(monkeypatch):
    modulate = Mock()
    soniox = Mock(return_value=(WORDS, 'en'))
    fallback = Mock()
    burn = Mock()
    monkeypatch.setattr(stt, 'modulate_prerecorded_from_bytes', modulate)
    monkeypatch.setattr(stt, 'soniox_transcribe', soniox)
    monkeypatch.setattr(stt, 'record_fallback', fallback)
    monkeypatch.setattr(stt, 'record_vendor_burn', burn)
    return SimpleNamespace(modulate=modulate, soniox=soniox, fallback=fallback, burn=burn)


def budget_failure():
    return TranscriptionFailure(
        TranscriptionOutcome.PROVIDER_BUDGET_EXHAUSTED,
        provider='modulate',
        retryable=False,
    )


def expect_fallback(event, *, reason, outcome):
    assert event.kwargs == {
        'component': 'stt_prerecorded',
        'from_mode': 'modulate',
        'to_mode': 'soniox',
        'reason': reason,
        'outcome': outcome,
        'log': stt.logger,
    }


def test_credit_refusal_recovers_on_soniox_and_reports_serving_provider(vendors):
    audio = wav_bytes(2)
    vendors.modulate.side_effect = budget_failure()

    provider = stt.ModulatePrerecordedProvider()
    result = provider.transcribe_bytes(audio, diarize=False, return_language=True, language='en')

    assert result == (WORDS, 'en')
    assert provider.served_provider == 'soniox'
    assert provider.served_model == 'stt-async-v5'
    assert vendors.modulate.call_count == 1
    assert vendors.soniox.call_count == 1
    assert vendors.soniox.call_args.args == (audio, 2.0)
    assert vendors.soniox.call_args.kwargs == {
        'language': 'en',
        'failover': True,
        'diarize': False,
        'retry_rate_limits': False,
    }
    expect_fallback(vendors.fallback.call_args, reason='provider_budget_exhausted', outcome='recovered')
    vendors.burn.assert_called_once_with('stt', 'ok', 2.0, provider='soniox')


def test_open_breaker_recovers_with_bounded_circuit_reason(vendors):
    for _ in range(BREAKER_FAILURE_THRESHOLD):
        record_breaker_quota_error('stt', budget=False)
    vendors.modulate.side_effect = ModulateQuotaError(
        'Modulate transcription failed: vendor circuit breaker open', breaker_open=True
    )

    assert stt.modulate_prerecorded_from_bytes_with_soniox(wav_bytes(), language='en') == WORDS

    expect_fallback(vendors.fallback.call_args, reason='circuit_open', outcome='recovered')
    assert vendors.soniox.call_count == 1


def test_modulate_empty_does_not_fail_over(vendors):
    vendors.modulate.return_value = []

    assert stt.modulate_prerecorded_from_bytes_with_soniox(wav_bytes(), language='en') == []

    vendors.soniox.assert_not_called()
    vendors.fallback.assert_not_called()
    vendors.burn.assert_not_called()


def test_soniox_429_returns_original_modulate_failure_without_loop(vendors):
    original = budget_failure()
    vendors.modulate.side_effect = original
    vendors.soniox.side_effect = SonioxBatchError('rate_limited', status_code=429)

    with pytest.raises(TranscriptionFailure) as raised:
        stt.modulate_prerecorded_from_bytes_with_soniox(wav_bytes(), language='en')

    assert raised.value is original
    assert raised.value.outcome is TranscriptionOutcome.PROVIDER_BUDGET_EXHAUSTED
    assert vendors.soniox.call_count == 1
    expect_fallback(vendors.fallback.call_args, reason='provider_budget_exhausted', outcome='exhausted')
    vendors.burn.assert_called_once_with('stt', 'error', 2.0, provider='soniox')


def test_local_soniox_refusal_returns_original_without_burn(vendors):
    original = budget_failure()
    vendors.modulate.side_effect = original
    vendors.soniox.side_effect = SonioxBatchError('refused')

    with pytest.raises(TranscriptionFailure) as raised:
        stt.modulate_prerecorded_from_bytes_with_soniox(wav_bytes(), language='en')

    assert raised.value is original
    vendors.burn.assert_not_called()
    expect_fallback(vendors.fallback.call_args, reason='provider_budget_exhausted', outcome='exhausted')


def test_missing_soniox_credentials_keep_original_modulate_failure(vendors):
    original = budget_failure()
    vendors.modulate.side_effect = original
    vendors.soniox.side_effect = PrerecordedSTTConfigurationError('soniox', 'SONIOX_API_KEY')

    with pytest.raises(TranscriptionFailure) as raised:
        stt.modulate_prerecorded_from_bytes_with_soniox(wav_bytes(), language='en')

    assert raised.value is original
    vendors.burn.assert_not_called()


def test_kill_switch_off_keeps_original_modulate_failure(vendors, monkeypatch):
    monkeypatch.setenv('PRERECORDED_SONIOX_FAILOVER_ENABLED', 'false')
    original = budget_failure()
    vendors.modulate.side_effect = original

    with pytest.raises(TranscriptionFailure) as raised:
        stt.modulate_prerecorded_from_bytes_with_soniox(wav_bytes(), language='en')

    assert raised.value is original
    vendors.soniox.assert_not_called()
    vendors.fallback.assert_not_called()


def test_unsupported_language_keeps_original_modulate_failure(vendors):
    original = ModulateQuotaError('Modulate transcription failed: vendor quota error')
    vendors.modulate.side_effect = original

    with pytest.raises(ModulateQuotaError) as raised:
        stt.modulate_prerecorded_from_bytes_with_soniox(wav_bytes(), language='xx-unsupported')

    assert raised.value is original
    vendors.soniox.assert_not_called()
    vendors.fallback.assert_not_called()


@pytest.mark.parametrize('error', [RuntimeError('transient'), TimeoutError('unknown posted billing state')])
def test_transient_and_uncertain_timeout_do_not_fail_over(vendors, error):
    vendors.modulate.side_effect = error

    with pytest.raises(type(error)):
        stt.modulate_prerecorded_from_bytes_with_soniox(wav_bytes(), language='en')

    vendors.soniox.assert_not_called()
    vendors.fallback.assert_not_called()


def test_multi_uses_soniox_automatic_language_identification(vendors):
    vendors.modulate.side_effect = budget_failure()

    assert stt.modulate_prerecorded_from_bytes_with_soniox(wav_bytes(), language='multi') == WORDS

    assert vendors.soniox.call_args.kwargs['language'] == 'multi'


def test_soniox_valid_empty_is_a_recovered_result_and_keeps_return_shape(vendors):
    vendors.modulate.side_effect = budget_failure()
    vendors.soniox.return_value = ([], 'multi')

    result = stt.modulate_prerecorded_from_bytes_with_soniox(wav_bytes(), language='multi', return_language=True)

    assert result == ([], 'multi')
    expect_fallback(vendors.fallback.call_args, reason='provider_budget_exhausted', outcome='recovered')


def test_prerecorded_dispatch_returns_soniox_metadata_without_changing_words_shape(vendors, monkeypatch):
    vendors.modulate.side_effect = budget_failure()
    monkeypatch.setenv('STT_PRERECORDED_MODEL', 'modulate-velma-2')
    pcm = b'\x01\x00' * 16000

    result, provider, model = stt.prerecorded_from_bytes(
        pcm,
        encoding='linear16',
        language='en',
        diarize=False,
        return_provider=True,
    )

    assert result == WORDS
    assert (provider, model) == ('soniox', 'stt-async-v5')
    assert vendors.soniox.call_args.args[1] == 1.0


def test_voice_helper_propagates_serving_provider_and_model(monkeypatch):
    monkeypatch.setattr(chat, 'get_prerecorded_service', lambda _language: ('modulate', 'en', 'velma-2'))
    monkeypatch.setattr(chat, 'linear16_pcm_is_silent', lambda *args, **kwargs: False)
    monkeypatch.setattr(chat, 'postprocess_words', lambda words, offset: [SimpleNamespace(text='recovered')])
    dispatch = Mock(return_value=(WORDS, 'soniox', 'stt-async-v5'))
    monkeypatch.setattr(chat, 'prerecorded_from_bytes', dispatch)

    result = chat.transcribe_pcm_bytes(b'\x01\x00' * 16000, 'uid', language='en', return_provider=True)

    assert result == ('recovered', 'en', 'soniox', 'stt-async-v5')
    assert dispatch.call_args.kwargs['return_provider'] is True


@pytest.mark.parametrize('duration', [0, 7201])
def test_sync_soniox_client_respects_failover_duration_bounds(duration):
    client_factory = Mock()

    with pytest.raises(SonioxBatchError) as raised:
        stt.soniox_transcribe(wav_bytes(), duration, language='en', failover=True, client_factory=client_factory)

    assert raised.value.kind == 'refused'
    client_factory.assert_not_called()


def test_failover_flag_defaults_on_and_only_explicit_false_disables(monkeypatch):
    assert soniox_failover_enabled() is True
    for value in ('false', ' False ', 'FALSE'):
        monkeypatch.setenv('PRERECORDED_SONIOX_FAILOVER_ENABLED', value)
        assert soniox_failover_enabled() is False
    for value in ('true', '0', 'off', 'malformed', ''):
        monkeypatch.setenv('PRERECORDED_SONIOX_FAILOVER_ENABLED', value)
        assert soniox_failover_enabled() is True


@pytest.mark.parametrize('scope', [stt.held_single_attempt, lambda: stt.verification_stt_deadline(100)])
def test_coordinator_owned_attempts_do_not_add_a_hidden_vendor(vendors, scope):
    original = budget_failure()
    vendors.modulate.side_effect = original
    with scope(), pytest.raises(TranscriptionFailure) as raised:
        stt.modulate_prerecorded_from_bytes_with_soniox(wav_bytes(), language='en')
    assert raised.value is original
    vendors.soniox.assert_not_called()


def test_modulate_auth_refusal_does_not_fail_over_even_if_breaker_opens(vendors):
    for _ in range(BREAKER_FAILURE_THRESHOLD):
        record_breaker_quota_error('stt', budget=False)
    vendors.modulate.side_effect = ModulateQuotaError('Modulate transcription failed: vendor quota error')
    with pytest.raises(ModulateQuotaError):
        stt.modulate_prerecorded_from_bytes_with_soniox(wav_bytes(), language='en')
    vendors.soniox.assert_not_called()


@pytest.mark.parametrize(
    'status,body,eligible',
    [
        (402, '', True),
        (429, 'insufficient credits', True),
        (401, '', False),
        (403, '', False),
        (400, '', False),
        (429, 'rate limited', False),
    ],
)
@pytest.mark.parametrize('use_url', [False, True])
def test_real_modulate_http_classification(monkeypatch, status, body, eligible, use_url):
    monkeypatch.setenv('MODULATE_API_KEY', 'synthetic')
    monkeypatch.setattr(stt, '_fail_fast_retry_sleep', lambda: None)
    audio = wav_bytes()
    posts = []

    def handler(request):
        if request.method == 'GET':
            return httpx.Response(200, content=audio)
        posts.append(request)
        return httpx.Response(status, text=body)

    real_client = httpx.Client
    monkeypatch.setattr(
        stt.httpx, 'Client', lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs)
    )
    soniox = Mock(return_value=(WORDS, 'en'))
    monkeypatch.setattr(stt, 'soniox_transcribe', soniox)
    provider = stt.ModulatePrerecordedProvider()
    dispatch = provider.transcribe_url if use_url else provider.transcribe_bytes
    if eligible:
        assert dispatch('https://synthetic.invalid/audio' if use_url else audio, language='en') == WORDS
        assert provider.served_provider == 'soniox'
        assert len(posts) == 1
        soniox.assert_called_once()
    else:
        with pytest.raises(RuntimeError):
            dispatch('https://synthetic.invalid/audio' if use_url else audio, language='en')
        soniox.assert_not_called()


def test_posted_timeout_then_credit_refusal_never_adds_soniox(monkeypatch):
    monkeypatch.setenv('MODULATE_API_KEY', 'synthetic')
    monkeypatch.setattr(stt, '_fail_fast_retry_sleep', lambda: None)
    posts = []

    def handler(request):
        posts.append(request)
        if len(posts) == 1:
            raise httpx.ReadTimeout('synthetic uncertain POST')
        return httpx.Response(402)

    real_client = httpx.Client
    monkeypatch.setattr(
        stt.httpx, 'Client', lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs)
    )
    soniox = Mock()
    monkeypatch.setattr(stt, 'soniox_transcribe', soniox)
    with pytest.raises(TranscriptionFailure):
        stt.modulate_prerecorded_from_bytes_with_soniox(wav_bytes(), language='en')
    assert len(posts) == 2
    soniox.assert_not_called()


def test_fenced_batch_attempt_budget_does_not_add_a_hidden_vendor(vendors):
    original = budget_failure()
    vendors.modulate.side_effect = original
    with pytest.raises(TranscriptionFailure) as raised:
        stt.modulate_prerecorded_from_bytes_with_soniox(wav_bytes(), language='en', attempts=2)
    assert raised.value is original
    vendors.soniox.assert_not_called()


def test_url_dispatch_reports_served_provider_to_sync_without_changing_tuple_shape(vendors, monkeypatch):
    vendors.modulate.side_effect = budget_failure()
    monkeypatch.setenv('STT_PRERECORDED_MODEL', 'modulate-velma-2')
    response = Mock(content=wav_bytes())
    client = Mock()
    client.__enter__ = Mock(return_value=client)
    client.__exit__ = Mock(return_value=False)
    client.get.return_value = response
    monkeypatch.setattr(stt.httpx, 'Client', lambda **kwargs: client)
    served = Mock()
    assert stt.prerecorded(
        'https://synthetic.invalid/audio',
        language='en',
        return_language=True,
        on_provider_served=served,
    ) == (WORDS, 'en')
    served.assert_called_once_with('soniox', 'stt-async-v5')
