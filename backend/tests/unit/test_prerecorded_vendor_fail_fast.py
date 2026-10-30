"""Prerecorded vendor fail-fast: quota never retries, breaker, burn accounting.

Synthetic httpx replies only — no network, no sys.modules mutation. httpx objects
are real (Response/exceptions) so quota classification exercises production code.
"""

from io import BytesIO
from unittest.mock import MagicMock
import wave

import httpx
import pytest
from prometheus_client import REGISTRY

from utils.stt import batch_language as lid
from utils.stt import pre_recorded as stt
from utils.stt import vendor_guard
from utils.stt.vendor_guard import ModulateQuotaError, reset_vendor_guard_for_tests

PROBE_OUTCOMES = (
    'accepted',
    'invalid_response',
    'quota',
    'http_5xx',
    'http_4xx',
    'timeout',
    'transport',
    'unsupported_format',
    'no_key',
    'skipped',
    'breaker_open',
    'error',
)
UNAVAILABLE = dict(language='und', confidence=0.0, evidence='unavailable')


def wav_bytes(seconds=2, sample_rate=16000):
    output = BytesIO()
    with wave.open(output, 'wb') as writer:
        writer.setparams((1, 2, sample_rate, 0, 'NONE', 'not compressed'))
        writer.writeframes(b'\x01\x00' * int(seconds * sample_rate))
    return output.getvalue()


def stt_reply(status=200, payload=None, text='error'):
    request = httpx.Request('POST', 'https://modulate.test/stt')
    if status == 200:
        return httpx.Response(200, json=payload or {'text': '', 'duration_ms': 120, 'utterances': []}, request=request)
    return httpx.Response(status, text=text, request=request)


def lid_reply(status=200, payload=None, text='error'):
    request = httpx.Request('POST', 'https://modulate.test/lid')
    if status == 200:
        return httpx.Response(
            200, json=payload or {'predicted_language_code': 'en', 'confidence': 0.9}, request=request
        )
    return httpx.Response(status, text=text, request=request)


def download_ok(content=None):
    return httpx.Response(200, content=content or wav_bytes(), request=httpx.Request('GET', 'https://storage.test'))


def install_http(monkeypatch, module, post=None, get=None):
    client = MagicMock()
    client.__enter__.return_value = client
    client.__exit__.return_value = False

    # mock treats a non-callable, non-exception side_effect as an iterator; a bare
    # httpx.Response must be wrapped so every call returns it instead of TypeError.
    def normalize(value):
        if callable(value) or isinstance(value, BaseException) or isinstance(value, list):
            return value
        return lambda *args, **kwargs: value

    if post is not None:
        client.post.side_effect = normalize(post)
    if get is not None:
        client.get.side_effect = normalize(get)
    monkeypatch.setattr(module.httpx, 'Client', MagicMock(return_value=client))
    return client


def metric(name, **labels):
    return REGISTRY.get_sample_value(name, labels) or 0


def breaker_gauge(endpoint):
    return metric('omi_prerecorded_vendor_breaker_open', provider='modulate', endpoint=endpoint)


def burn(endpoint, outcome):
    return metric('omi_prerecorded_vendor_audio_seconds_total', provider='modulate', endpoint=endpoint, outcome=outcome)


def probe_total():
    return sum(metric('omi_batch_pipeline_language_probe_total', outcome=o) for o in PROBE_OUTCOMES)


def probe_outcome(o):
    return metric('omi_batch_pipeline_language_probe_total', outcome=o)


@pytest.fixture(autouse=True)
def fail_fast_defaults(monkeypatch):
    monkeypatch.delenv('STT_PRERECORDED_VENDOR_FAIL_FAST', raising=False)
    monkeypatch.setenv('MODULATE_API_KEY', 'synthetic-test-key')
    reset_vendor_guard_for_tests()
    yield
    reset_vendor_guard_for_tests()


def no_retry_sleep(monkeypatch):
    calls = []
    monkeypatch.setattr(stt, '_fail_fast_retry_sleep', lambda: calls.append(1))
    return calls


# ---------------------------------------------------------------------------
# STT bytes path
# ---------------------------------------------------------------------------


@pytest.mark.parametrize('status,body', [(403, 'forbidden'), (401, 'unauthorized'), (400, 'Insufficient Credits')])
def test_quota_error_fails_fast_with_a_single_post(monkeypatch, status, body):
    client = install_http(monkeypatch, stt, post=stt_reply(status, text=body))
    seconds_before = burn('stt', 'error')
    with pytest.raises(ModulateQuotaError, match=r'^Modulate transcription failed') as exc_info:
        stt.modulate_prerecorded_from_bytes(wav_bytes(2))
    assert isinstance(exc_info.value, RuntimeError)
    # The marker body never reaches the exception message.
    assert 'insufficient credits' not in str(exc_info.value).lower()
    assert client.post.call_count == 1
    assert burn('stt', 'error') - seconds_before == 2.0


@pytest.mark.parametrize('status,body', [(402, 'payment required'), (429, '{"error": "Insufficient Credits."}')])
def test_budget_refusal_is_typed_terminal_and_feeds_the_breaker(monkeypatch, status, body):
    from utils.stt.outcomes import TranscriptionFailure, TranscriptionOutcome

    client = install_http(monkeypatch, stt, post=stt_reply(status, text=body))
    before = burn('stt', 'error')
    for _ in range(vendor_guard.BREAKER_FAILURE_THRESHOLD):
        with pytest.raises(TranscriptionFailure) as exc_info:
            stt.modulate_prerecorded_from_bytes(wav_bytes(2))
        assert exc_info.value.outcome == TranscriptionOutcome.PROVIDER_BUDGET_EXHAUSTED
        assert exc_info.value.retryable is False
    assert client.post.call_count == vendor_guard.BREAKER_FAILURE_THRESHOLD
    assert burn('stt', 'error') - before == 2.0 * vendor_guard.BREAKER_FAILURE_THRESHOLD
    assert breaker_gauge('stt') == 1
    # The open breaker reports the same typed budget outcome without another POST.
    with pytest.raises(TranscriptionFailure) as exc_info:
        stt.modulate_prerecorded_from_bytes(wav_bytes(2))
    assert exc_info.value.outcome == TranscriptionOutcome.PROVIDER_BUDGET_EXHAUSTED
    assert client.post.call_count == vendor_guard.BREAKER_FAILURE_THRESHOLD


def test_plain_429_rate_limit_is_transient_and_bounded_to_two_posts(monkeypatch):
    from utils.stt.outcomes import TranscriptionFailure

    client = install_http(monkeypatch, stt, post=stt_reply(429, text='{"error": "Too many requests"}'))
    no_retry_sleep(monkeypatch)
    with pytest.raises(RuntimeError) as exc_info:
        stt.modulate_prerecorded_from_bytes(wav_bytes(2))
    assert not isinstance(exc_info.value, (TranscriptionFailure, ModulateQuotaError))
    assert client.post.call_count == 2
    assert breaker_gauge('stt') == 0


def test_5xx_retries_once_then_raises_runtime_error(monkeypatch):
    client = install_http(monkeypatch, stt, post=[stt_reply(503), stt_reply(503)])
    sleeps = no_retry_sleep(monkeypatch)
    with pytest.raises(RuntimeError, match='Modulate transcription failed after 2 attempts') as exc_info:
        stt.modulate_prerecorded_from_bytes(wav_bytes())
    assert not isinstance(exc_info.value, ModulateQuotaError)
    assert client.post.call_count == 2
    assert sleeps == [1]


def test_timeout_retries_once_then_raises(monkeypatch):
    client = install_http(monkeypatch, stt, post=httpx.ConnectTimeout('synthetic timeout'))
    no_retry_sleep(monkeypatch)
    with pytest.raises(RuntimeError, match='after 2 attempts'):
        stt.modulate_prerecorded_from_bytes(wav_bytes())
    assert client.post.call_count == 2


def test_transient_retry_then_success_is_bounded_to_two_posts(monkeypatch):
    client = install_http(monkeypatch, stt, post=[stt_reply(503), stt_reply(200)])
    no_retry_sleep(monkeypatch)
    ok_before = burn('stt', 'ok')
    error_before = burn('stt', 'error')
    assert stt.modulate_prerecorded_from_bytes(wav_bytes(3)) == []
    assert client.post.call_count == 2
    assert burn('stt', 'ok') - ok_before == 3.0
    assert burn('stt', 'error') - error_before == 3.0


def test_non_wav_audio_burns_zero_seconds_without_raising(monkeypatch):
    client = install_http(monkeypatch, stt, post=stt_reply(403))
    before = burn('stt', 'error')
    with pytest.raises(ModulateQuotaError):
        stt.modulate_prerecorded_from_bytes(b'not-a-wav')
    assert burn('stt', 'error') - before == 0.0


def test_kill_switch_restores_the_legacy_three_post_retry(monkeypatch):
    monkeypatch.setenv('STT_PRERECORDED_VENDOR_FAIL_FAST', 'false')
    client = install_http(monkeypatch, stt, post=httpx.ConnectTimeout('synthetic timeout'))
    with pytest.raises(RuntimeError, match='after 3 attempts'):
        stt.modulate_prerecorded_from_bytes(wav_bytes())
    assert client.post.call_count == 3


def test_kill_switch_is_read_at_call_time(monkeypatch):
    from config.prerecorded_vendor import vendor_fail_fast_enabled

    monkeypatch.delenv('STT_PRERECORDED_VENDOR_FAIL_FAST', raising=False)
    assert vendor_fail_fast_enabled() is True
    for value in ('false', ' False ', 'FALSE'):
        monkeypatch.setenv('STT_PRERECORDED_VENDOR_FAIL_FAST', value)
        assert vendor_fail_fast_enabled() is False
    for value in ('true', '0', 'no', 'off', ''):
        monkeypatch.setenv('STT_PRERECORDED_VENDOR_FAIL_FAST', value)
        assert vendor_fail_fast_enabled() is True


# ---------------------------------------------------------------------------
# STT URL wrapper
# ---------------------------------------------------------------------------


def test_url_wrapper_quota_is_one_download_and_one_post(monkeypatch):
    client = install_http(monkeypatch, stt, post=stt_reply(403), get=download_ok())
    with pytest.raises(ModulateQuotaError, match=r'^Modulate transcription failed'):
        stt.modulate_prerecorded('https://storage.test/wave')
    assert client.get.call_count == 1
    assert client.post.call_count == 1


def test_url_wrapper_retries_only_the_download(monkeypatch):
    client = install_http(monkeypatch, stt, post=stt_reply(200), get=[Exception('synthetic reset'), download_ok()])
    assert stt.modulate_prerecorded('https://storage.test/wave') == []
    assert client.get.call_count == 2
    assert client.post.call_count == 1


def test_url_wrapper_download_exhaustion_never_posts(monkeypatch):
    client = install_http(monkeypatch, stt, post=stt_reply(200), get=Exception('synthetic reset'))
    with pytest.raises(RuntimeError, match=r'Modulate transcription \(url\) failed'):
        stt.modulate_prerecorded('https://storage.test/wave')
    assert client.get.call_count == 2
    assert client.post.call_count == 0


def test_kill_switch_restores_the_legacy_five_post_url_retry(monkeypatch):
    monkeypatch.setenv('STT_PRERECORDED_VENDOR_FAIL_FAST', 'false')
    client = install_http(monkeypatch, stt, post=httpx.ConnectTimeout('synthetic timeout'), get=download_ok())
    with pytest.raises(RuntimeError, match=r'\(url\) failed after 2 attempts'):
        stt.modulate_prerecorded('https://storage.test/wave')
    assert client.post.call_count == 5
    assert client.get.call_count == 2


# ---------------------------------------------------------------------------
# Circuit breaker
# ---------------------------------------------------------------------------


def prime_stt_breaker(monkeypatch, failures=5):
    client = install_http(monkeypatch, stt, post=stt_reply(403))
    for _ in range(failures):
        with pytest.raises(ModulateQuotaError):
            stt.modulate_prerecorded_from_bytes(wav_bytes())
    return client


def test_breaker_opens_after_five_quota_errors_and_blocks_http(monkeypatch):
    client = prime_stt_breaker(monkeypatch)
    assert client.post.call_count == 5
    assert breaker_gauge('stt') == 1
    with pytest.raises(ModulateQuotaError, match='circuit breaker open'):
        stt.modulate_prerecorded_from_bytes(wav_bytes())
    assert client.post.call_count == 5
    assert breaker_gauge('stt') == 1


def test_four_quota_errors_leave_the_breaker_closed(monkeypatch):
    client = prime_stt_breaker(monkeypatch, failures=4)
    assert breaker_gauge('stt') == 0
    with pytest.raises(ModulateQuotaError):
        stt.modulate_prerecorded_from_bytes(wav_bytes())
    assert client.post.call_count == 5


def test_non_quota_errors_do_not_open_the_breaker(monkeypatch):
    client = install_http(monkeypatch, stt, post=httpx.ConnectTimeout('synthetic timeout'))
    no_retry_sleep(monkeypatch)
    for _ in range(3):
        with pytest.raises(RuntimeError):
            stt.modulate_prerecorded_from_bytes(wav_bytes())
    assert client.post.call_count == 6
    assert breaker_gauge('stt') == 0


def test_breaker_half_open_trial_success_closes(monkeypatch):
    now = {'t': 1000.0}
    monkeypatch.setattr(vendor_guard, '_clock', lambda: now['t'])
    client = prime_stt_breaker(monkeypatch)
    with pytest.raises(ModulateQuotaError, match='circuit breaker open'):
        stt.modulate_prerecorded_from_bytes(wav_bytes())
    assert client.post.call_count == 5

    now['t'] += vendor_guard.BREAKER_OPEN_SECONDS + 1
    client.post.side_effect = lambda *args, **kwargs: stt_reply(200)
    assert stt.modulate_prerecorded_from_bytes(wav_bytes()) == []
    assert client.post.call_count == 6
    assert breaker_gauge('stt') == 0
    # Closed again: subsequent calls are ordinary requests.
    assert stt.modulate_prerecorded_from_bytes(wav_bytes()) == []
    assert client.post.call_count == 7


def test_breaker_half_open_trial_quota_reopens_for_another_window(monkeypatch):
    now = {'t': 1000.0}
    monkeypatch.setattr(vendor_guard, '_clock', lambda: now['t'])
    client = prime_stt_breaker(monkeypatch)
    now['t'] += vendor_guard.BREAKER_OPEN_SECONDS + 1
    with pytest.raises(ModulateQuotaError):
        stt.modulate_prerecorded_from_bytes(wav_bytes())
    assert client.post.call_count == 6
    now['t'] += 1
    with pytest.raises(ModulateQuotaError, match='circuit breaker open'):
        stt.modulate_prerecorded_from_bytes(wav_bytes())
    assert client.post.call_count == 6
    assert breaker_gauge('stt') == 1


def test_breaker_allows_exactly_one_half_open_trial(monkeypatch):
    now = {'t': 1000.0}
    monkeypatch.setattr(vendor_guard, '_clock', lambda: now['t'])
    for _ in range(vendor_guard.BREAKER_FAILURE_THRESHOLD):
        vendor_guard.record_breaker_quota_error('stt')
    assert vendor_guard.breaker_allows('stt') is False
    now['t'] += vendor_guard.BREAKER_OPEN_SECONDS + 1
    assert vendor_guard.breaker_allows('stt') is True
    assert vendor_guard.breaker_allows('stt') is False
    vendor_guard.record_breaker_success('stt')
    assert vendor_guard.breaker_allows('stt') is True


def test_breaker_trial_with_a_5xx_does_not_wedge_the_breaker(monkeypatch):
    """A non-quota trial failure must release the trial; otherwise the breaker stays open until restart."""
    now = {'t': 1000.0}
    monkeypatch.setattr(vendor_guard, '_clock', lambda: now['t'])
    no_retry_sleep(monkeypatch)
    client = prime_stt_breaker(monkeypatch)
    now['t'] += vendor_guard.BREAKER_OPEN_SECONDS + 1
    client.post.side_effect = lambda *args, **kwargs: stt_reply(503)
    with pytest.raises(RuntimeError):
        stt.modulate_prerecorded_from_bytes(wav_bytes())
    assert client.post.call_count == 6  # the trial; its retry meets the re-opened breaker
    now['t'] += vendor_guard.BREAKER_OPEN_SECONDS + 1
    client.post.side_effect = lambda *args, **kwargs: stt_reply(200)
    assert stt.modulate_prerecorded_from_bytes(wav_bytes()) == []
    assert breaker_gauge('stt') == 0


def test_abandoned_trial_expires(monkeypatch):
    now = {'t': 1000.0}
    monkeypatch.setattr(vendor_guard, '_clock', lambda: now['t'])
    for _ in range(vendor_guard.BREAKER_FAILURE_THRESHOLD):
        vendor_guard.record_breaker_quota_error('lid')
    now['t'] += vendor_guard.BREAKER_OPEN_SECONDS + 1
    assert vendor_guard.breaker_allows('lid') is True
    assert vendor_guard.breaker_allows('lid') is False
    now['t'] += vendor_guard.BREAKER_TRIAL_TIMEOUT_SECONDS + 1
    assert vendor_guard.breaker_allows('lid') is True


def test_breaker_is_inert_while_fail_fast_is_off(monkeypatch):
    for _ in range(vendor_guard.BREAKER_FAILURE_THRESHOLD + 2):
        vendor_guard.record_breaker_quota_error('stt')
    monkeypatch.setenv('STT_PRERECORDED_VENDOR_FAIL_FAST', 'false')
    assert vendor_guard.breaker_allows('stt') is True
    client = install_http(monkeypatch, stt, post=httpx.ConnectTimeout('synthetic timeout'))
    with pytest.raises(RuntimeError):
        stt.modulate_prerecorded_from_bytes(wav_bytes())
    assert client.post.call_count == 3


# ---------------------------------------------------------------------------
# LID probe outcomes
# ---------------------------------------------------------------------------


def assert_unavailable(decision):
    assert (decision.language, decision.confidence, decision.evidence) == (
        UNAVAILABLE['language'],
        UNAVAILABLE['confidence'],
        UNAVAILABLE['evidence'],
    )


def test_detect_outcome_accepted(monkeypatch):
    client = install_http(monkeypatch, lid, post=lid_reply(200))
    before, accepted_before, burn_before = probe_total(), probe_outcome('accepted'), burn('lid', 'ok')
    decision = lid.detect(wav_bytes(6))
    assert decision == lid.LanguageDecision('en', 0.9, 'audio_lid', 6.0)
    assert client.post.call_count == 1
    assert probe_total() - before == 1
    assert probe_outcome('accepted') - accepted_before == 1
    assert burn('lid', 'ok') - burn_before == 6.0


@pytest.mark.parametrize(
    'post,expected_outcome',
    [
        (lid_reply(429, text='Insufficient credits'), 'quota'),
        (lid_reply(503), 'http_5xx'),
        (lid_reply(404), 'http_4xx'),
        (httpx.ConnectTimeout('synthetic timeout'), 'timeout'),
        (httpx.ConnectError('synthetic transport'), 'transport'),
        (lid_reply(200, payload={'predicted_language_code': 'english', 'confidence': 0.9}), 'invalid_response'),
        (Exception('synthetic unexpected'), 'error'),
    ],
)
def test_detect_failure_outcomes(monkeypatch, post, expected_outcome):
    client = install_http(monkeypatch, lid, post=post)
    before, outcome_before = probe_total(), probe_outcome(expected_outcome)
    assert_unavailable(lid.detect(wav_bytes(6)))
    assert probe_total() - before == 1
    assert probe_outcome(expected_outcome) - outcome_before == 1


def test_detect_outcome_no_key(monkeypatch):
    monkeypatch.delenv('MODULATE_API_KEY', raising=False)
    client = install_http(monkeypatch, lid, post=lid_reply(200))
    before, outcome_before = probe_total(), probe_outcome('no_key')
    assert_unavailable(lid.detect(wav_bytes(6)))
    assert client.post.call_count == 0
    assert probe_total() - before == 1
    assert probe_outcome('no_key') - outcome_before == 1


def test_detect_outcome_skipped(monkeypatch):
    client = install_http(monkeypatch, lid, post=lid_reply(200))
    before, outcome_before = probe_total(), probe_outcome('skipped')
    assert_unavailable(lid.detect(wav_bytes(6), before_probe=lambda: False))
    assert client.post.call_count == 0
    assert probe_total() - before == 1
    assert probe_outcome('skipped') - outcome_before == 1


def test_detect_outcome_unsupported_format(monkeypatch):
    client = install_http(monkeypatch, lid, post=lid_reply(200))
    before, outcome_before = probe_total(), probe_outcome('unsupported_format')
    assert_unavailable(lid.detect(wav_bytes(1), encoding='opus'))
    assert client.post.call_count == 0
    assert probe_total() - before == 1
    assert probe_outcome('unsupported_format') - outcome_before == 1


def test_detect_outcome_breaker_open(monkeypatch):
    client = install_http(monkeypatch, lid, post=lid_reply(403))
    for _ in range(5):
        assert_unavailable(lid.detect(wav_bytes(6)))
    assert client.post.call_count == 5
    assert breaker_gauge('lid') == 1
    before, outcome_before = probe_total(), probe_outcome('breaker_open')
    assert_unavailable(lid.detect(wav_bytes(6)))
    assert client.post.call_count == 5
    assert probe_total() - before == 1
    assert probe_outcome('breaker_open') - outcome_before == 1


def test_detect_quota_failure_burns_probe_seconds_as_error(monkeypatch):
    install_http(monkeypatch, lid, post=lid_reply(403))
    before = burn('lid', 'error')
    assert_unavailable(lid.detect(wav_bytes(6)))
    assert burn('lid', 'error') - before == 6.0
