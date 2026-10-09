"""Tests for utils.log_sanitizer — masks sensitive tokens while preserving searchability."""

import asyncio
import importlib.util
import io
import json
import logging
import wave
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from utils.log_sanitizer import sanitize, sanitize_pii, sanitize_provider_error
from utils.stt import parakeet_window, pre_recorded, provider_resilience, soniox, speaker_embedding, streaming, vad
from utils.stt.safe_socket import SafeDeepgramSocket
from utils.stt.streaming import MODULATE_DEATH_SERVE_ERROR, ParakeetConnectionError, SafeModulateSocket
from utils.stt.stream_close import PROVIDER_BUDGET_EXHAUSTED


class TestSanitizeShortStrings:
    """Strings shorter than 8 chars are left as-is."""

    def test_short_word(self):
        assert sanitize("hello") == "hello"

    def test_7_char_string(self):
        assert sanitize("abcdefg") == "abcdefg"

    def test_none(self):
        assert sanitize(None) == "None"

    def test_empty(self):
        assert sanitize("") == ""


class TestSanitizeMediumStrings:
    """Strings 8-12 chars with digits: first 3 + *** + last 3."""

    def test_8_char_with_digit(self):
        result = sanitize("abcdef1h")
        assert result == "abc***f1h"

    def test_12_char_with_digit(self):
        result = sanitize("abcdef1hijkl")
        assert result == "abc***jkl"

    def test_8_char_pure_alpha_not_masked(self):
        """Pure alphabetic strings are NOT masked (they're words, not tokens)."""
        assert sanitize("abcdefgh") == "abcdefgh"


class TestSanitizeLongStrings:
    """Strings 13+ chars with digits: first 4 + *** + last 4."""

    def test_13_char_with_digit(self):
        result = sanitize("abcdefgh1jklm")
        assert result == "abcd***jklm"

    def test_13_char_pure_alpha_not_masked(self):
        """Pure alphabetic strings are NOT masked."""
        assert sanitize("abcdefghijklm") == "abcdefghijklm"

    def test_jwt_like_token(self):
        token = "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9"
        result = sanitize(token)
        assert result.startswith("eyJh")
        assert result.endswith("VCJ9")
        assert "***" in result

    def test_base64_blob(self):
        blob = "dGhpcyBpcyBhIGxvbmcgYmFzZTY0IHN0cmluZw=="
        result = sanitize(blob)
        assert result.startswith("dGhp")
        assert "***" in result


class TestSanitizePreservesStructure:
    """JSON keys, punctuation, and short values stay intact."""

    def test_json_with_token(self):
        text = '{"access_token": "ya29xABCDEFGHIJKLMNOP1234567890"}'
        result = sanitize(text)
        assert '"access_token": "' in result  # key preserved (no digits)
        assert "***" in result  # token value is masked

    def test_error_message_with_token(self):
        text = "Apple token exchange failed: {\"error\":\"invalid_grant\",\"token\":\"abc123def456ghij\"}"
        result = sanitize(text)
        assert "Apple token exchange failed:" in result  # message preserved
        assert "invalid_grant" in result  # no digits, not masked
        assert "***" in result  # token is masked

    def test_ip_address_not_masked(self):
        """IPs have dots separating segments, so segments < 8 chars stay visible."""
        result = sanitize("connecting to 10.128.0.5:8080")
        assert "10.128.0.5" in result

    def test_uid_partially_masked(self):
        """UIDs contain digits, so they get masked."""
        result = sanitize("uid=abc123def456ghij")
        assert "uid=" in result
        assert "***" in result

    def test_status_code_preserved(self):
        result = sanitize("HTTP 403: some_long_error_message_here")
        assert "HTTP 403:" in result
        assert "some_long_error_message_here" in result  # pure alpha + underscores, not masked

    def test_pure_words_not_masked(self):
        """Regular English words and snake_case identifiers are not masked."""
        text = "access_token client_secret invalid_grant exchange"
        assert sanitize(text) == text


class TestSanitizeTruncation:
    """Very long strings are truncated to prevent log bloat."""

    def test_long_string_truncated(self):
        # Use digits so the truncation marker isn't confused by masking
        long_text = "x" * 3000
        result = sanitize(long_text)
        assert len(result) < 3000
        # Pure alpha, so not masked — truncation marker should be intact
        assert "...[truncated]" in result

    def test_under_limit_not_truncated(self):
        text = "a" * 1999
        result = sanitize(text)
        assert "...[truncated]" not in result


class TestSanitizeNonStringInput:
    """sanitize() accepts any type and converts to str."""

    def test_dict_input(self):
        data = {"client_id": "abc123", "client_secret": "superSecret1ValueHere1234"}
        result = sanitize(data)
        assert "client_id" in result  # key preserved (no digits in key)
        assert "client_secret" in result  # key preserved
        assert "***" in result  # value with digits is masked

    def test_int_input(self):
        assert sanitize(42) == "42"

    def test_list_input(self):
        result = sanitize([True, False, True])
        assert "True" in result


class TestSanitizeEmails:
    """Email addresses get local part masked, domain preserved."""

    def test_simple_email(self):
        result = sanitize("john@example.com")
        assert "example.com" in result
        assert "john" not in result
        assert "***" in result

    def test_email_in_log_message(self):
        result = sanitize("Found contact: John Doe -> john.doe@gmail.com")
        assert "gmail.com" in result
        assert "john.doe" not in result

    def test_short_local_part(self):
        result = sanitize("ab@example.com")
        assert "***@example.com" == result

    def test_email_with_digits(self):
        result = sanitize("user123@company.org")
        assert "company.org" in result
        assert "***" in result

    def test_multiple_emails(self):
        result = sanitize("from alice@a.com to bob@b.com")
        assert "a.com" in result
        assert "b.com" in result
        assert "alice" not in result
        assert "bob" not in result


class TestSanitizeKeyValuePreserved:
    """key=value style text should not be falsely masked."""

    def test_simple_key_value(self):
        """key=value where value is a regular word should be preserved."""
        result = sanitize("attendee=charlie")
        assert "attendee" in result
        assert "charlie" in result

    def test_key_value_with_token(self):
        """key=value where value looks like a token should be masked."""
        result = sanitize("token=abc123def456ghij")
        assert "token=" in result
        assert "***" in result


class TestSanitizePii:
    """sanitize_pii() always masks PII values, including pure-alpha names."""

    def test_short_name(self):
        assert sanitize_pii("Bob") == "***"

    def test_medium_name(self):
        result = sanitize_pii("Alice")
        assert result == "A***e"

    def test_long_name(self):
        result = sanitize_pii("Alexander")
        assert result == "Al***er"

    def test_full_name(self):
        """Each word is masked independently."""
        result = sanitize_pii("John Doe")
        assert "John" not in result
        assert "Doe" not in result
        assert "***" in result

    def test_email_via_pii(self):
        result = sanitize_pii("john.doe@gmail.com")
        assert "gmail.com" in result
        assert "john.doe" not in result

    def test_none(self):
        assert sanitize_pii(None) == "None"

    def test_user_text(self):
        """User-generated text should be masked."""
        result = sanitize_pii("Hello this is a private message")
        assert "Hello" not in result
        assert "private" not in result

    def test_4_char_name(self):
        """4 chars -> ***"""
        assert sanitize_pii("Jane") == "***"

    def test_8_char_name(self):
        """8 chars -> first 1 + *** + last 1"""
        result = sanitize_pii("Jonathan")
        assert result == "J***n"

    def test_mixed_name_and_email(self):
        """String with name and email — both get masked."""
        result = sanitize_pii("John Doe john@example.com")
        assert "John" not in result
        assert "Doe" not in result
        assert "john" not in result
        assert "example.com" in result  # domain preserved

    def test_single_char_email(self):
        """Single char local part -> ***@domain."""
        result = sanitize_pii("a@example.com")
        assert result == "***@example.com"


class TestSanitizeBoundaryEdgeCases:
    """Exact boundary tests for masking thresholds and truncation limits."""

    def test_token_with_plus_no_digits(self):
        """+ triggers masking even without digits."""
        result = sanitize("abcdefg+hijklmnop")
        assert "***" in result

    def test_token_with_slash_no_digits(self):
        """/ triggers masking even without digits."""
        result = sanitize("abcdefg/hijklmnop")
        assert "***" in result

    def test_truncation_at_exact_2000(self):
        """Exactly 2000 chars — should NOT be truncated."""
        text = "x" * 2000
        result = sanitize(text)
        assert "...[truncated]" not in result

    def test_truncation_at_2001(self):
        """2001 chars — should be truncated."""
        text = "x" * 2001
        result = sanitize(text)
        assert "...[truncated]" in result

    def test_pii_truncation_at_200(self):
        """sanitize_pii truncates at 200 chars."""
        text = "a" * 201
        result = sanitize_pii(text)
        assert "..." in result

    def test_pii_no_truncation_at_200(self):
        """Exactly 200 chars — should NOT be truncated."""
        text = "a" * 200
        result = sanitize_pii(text)
        assert "..." not in result


class TestSanitizeProviderError:
    """Provider diagnostics emit only a validated code and canonical phrase."""

    def test_none(self):
        assert sanitize_provider_error(None) == 'code=unknown diagnostic=[redacted]'

    def test_pure_alpha_secret_redacted(self):
        result = sanitize_provider_error('quixotictranscriptzebra')
        assert 'quixotictranscriptzebra' not in result
        assert '[redacted]' in result

    def test_canonical_phrase_from_string(self):
        assert sanitize_provider_error('429 limit_exceeded retry later') == 'code=unknown diagnostic=limit_exceeded'

    def test_explicit_valid_codes_preserved(self):
        assert sanitize_provider_error('anything', code=429).startswith('code=429 ')
        assert sanitize_provider_error('anything', code='500').startswith('code=500 ')
        assert sanitize_provider_error('anything', code=1005).startswith('code=1005 ')

    def test_invalid_codes_become_unknown(self):
        for bad in (True, 'nope', '12345', 99, 700, 1016, 3.5, {'code': 500}):
            assert sanitize_provider_error('anything', code=bad).startswith('code=unknown '), bad

    def test_mapping_extracts_code_and_message(self):
        result = sanitize_provider_error(
            {'error_code': 402, 'error_type': 'x', 'error_message': 'Organization balance exhausted, uid user-secret'}
        )
        assert result.startswith('code=402 ')
        assert 'user-secret' not in result

    def test_mapping_non_string_values_not_stringified(self):
        result = sanitize_provider_error({'error': {'nested': 'payload-secret'}, 'code': 500})
        assert result.startswith('code=500 ')
        assert 'payload-secret' not in result
        assert '[redacted]' in result

    def test_exception_uses_str_for_matching_only(self):
        result = sanitize_provider_error(RuntimeError('connection timed out: victim@example.com'))
        assert result == 'code=unknown diagnostic=timed out exception_type=RuntimeError'

    def test_exception_status_code_attribute(self):
        class ProviderError(Exception):
            status_code = 503

        assert sanitize_provider_error(ProviderError('opaque')) == 'code=503 diagnostic=[redacted] exception_type=other'

    def test_exception_response_status_code_attribute(self):
        class Response:
            status_code = 502

        class HttpError(Exception):
            response = Response()

        assert sanitize_provider_error(HttpError('opaque')).startswith('code=502 ')

    def test_mapping_code_walk_skips_unusable_fields(self):
        result = sanitize_provider_error(
            {'error_code': 'bad-private', 'status_code': 503, 'code': 429, 'message': 'opaque'}
        )
        assert result == 'code=503 diagnostic=[redacted]'

    def test_mapping_code_walk_skips_bool_and_empty(self):
        result = sanitize_provider_error({'error_code': True, 'status_code': '', 'code': '404', 'message': 'opaque'})
        assert result == 'code=404 diagnostic=[redacted]'

    def test_object_code_and_description_fields(self):
        class Frame:
            code = 502
            description = 'Internal server error for victim@sentinel-domain.example'

        result = sanitize_provider_error(Frame())
        assert result == 'code=502 diagnostic=internal server error'
        assert 'victim@sentinel-domain.example' not in result

    def test_object_blank_message_falls_through_to_description(self):
        class Frame:
            code = 502
            message = ''
            description = 'Internal server error for victim@sentinel-domain.example'

        result = sanitize_provider_error(Frame())
        assert result == 'code=502 diagnostic=internal server error'
        assert 'victim@sentinel-domain.example' not in result

    def test_mapping_blank_message_falls_through_to_error(self):
        result = sanitize_provider_error(
            {'code': 503, 'message': '   ', 'error': 'Unable to complete the request victim@sentinel-domain.example'}
        )
        assert result == 'code=503 diagnostic=unable to complete the request'
        assert 'victim@sentinel-domain.example' not in result

    def test_object_response_fallback_code(self):
        class Response:
            status_code = 429

        class Reply:
            response = Response()

        assert sanitize_provider_error(Reply()).startswith('code=429 ')

    def test_raising_property_is_ignored(self):
        class Frame:
            @property
            def status_code(self):
                raise RuntimeError('getter exploded')

            code = 503

        result = sanitize_provider_error(Frame())
        assert result == 'code=503 diagnostic=[redacted]'

    def test_explicit_invalid_code_stays_unknown(self):
        result = sanitize_provider_error({'status_code': 503, 'message': 'opaque'}, code='nope')
        assert result == 'code=unknown diagnostic=[redacted]'

    def test_object_str_and_repr_never_used(self):
        class Hostile:
            def __str__(self):
                raise RuntimeError('no')

            def __repr__(self):
                raise RuntimeError('no')

        assert sanitize_provider_error(Hostile()) == 'code=unknown diagnostic=[redacted]'

    @pytest.mark.parametrize(
        'text',
        [
            'rate_limit_exceeded',
            'Rate Limit Exceeded',
            'rate   limit\nexceeded',
        ],
    )
    def test_canonical_phrase_variants_match_same_constant(self, text):
        assert sanitize_provider_error(text) == 'code=unknown diagnostic=rate_limit_exceeded'

    def test_bounded_connect_retry_window_phrase(self):
        result = sanitize_provider_error('429 responses continued through the bounded connect retry window', code=429)
        assert result == 'code=429 diagnostic=bounded connect retry window'

    def test_phrase_beyond_scan_window_stays_redacted(self):
        result = sanitize_provider_error('x' * 2001 + ' timeout', code=503)
        assert result == 'code=503 diagnostic=[redacted]'

    def test_distinct_closed_exception_types(self):
        assert (
            sanitize_provider_error(TimeoutError(''))
            == 'code=unknown diagnostic=[redacted] exception_type=TimeoutError'
        )
        assert (
            sanitize_provider_error(OSError('private')) == 'code=unknown diagnostic=[redacted] exception_type=OSError'
        )

    def test_unknown_exception_type_maps_other(self):
        VictimError = type('VictimPrivateError', (Exception,), {})
        result = sanitize_provider_error(VictimError('internal server error victim@sentinel-domain.example'))
        assert result == 'code=unknown diagnostic=internal server error exception_type=other'
        assert 'VictimPrivateError' not in result
        assert 'victim@sentinel-domain.example' not in result

    def test_canonical_phrase_never_carries_surrounding_text(self):
        result = sanitize_provider_error(
            'Internal server error for account victim@sentinel.example key abcdef1234567890'
        )
        assert result == 'code=unknown diagnostic=internal server error'

    def test_long_payload_stays_under_cap(self):
        result = sanitize_provider_error('x' * 12000, code=429)
        assert len(result) <= 160
        assert 'xxx' not in result

    @pytest.mark.parametrize(
        'payload',
        [
            'victim@sentinel-domain.example',
            'https://signed.example.invalid/audio?sig=abcdef123456',
            '/home/user/private/audio.wav',
            'line one\nline two secret',
            'uid 12345 name zebra',
        ],
    )
    def test_sensitive_shapes_redacted(self, payload):
        result = sanitize_provider_error(payload)
        assert result == 'code=unknown diagnostic=[redacted]'
        assert '\n' not in result
        for fragment in payload.split():
            assert fragment not in result

    @pytest.mark.parametrize(
        'phrase',
        [
            'organization_balance_exhausted',
            'organization_monthly_budget_exhausted',
            'project_monthly_budget_exhausted',
            'invalid_api_key',
            'invalid language hint',
            'no audio received',
            'max_duration_reached',
            'request_timeout',
            'rate_limit_exceeded',
            'limit_exceeded',
            'internal server error',
            'unable to complete the request',
            'invalid input audio',
            'timeout',
            'timed out',
            'connection closed',
        ],
    )
    def test_each_canonical_phrase_emits_exact_constant(self, phrase):
        result = sanitize_provider_error(f'vendor said "{phrase}" uid 12345 victim@sentinel-domain.example')
        assert result == f'code=unknown diagnostic={phrase}'


SENTINEL = 'quixotictranscriptzebra'
SENTINEL_EMAIL = 'victim@sentinel-domain.example'
SENTINEL_URL = 'https://signed.example.invalid/audio.wav?sig=abcdef123456'


def _caplog_text(caplog) -> str:
    return '\n'.join(record.getMessage() for record in caplog.records)


class FakeWebSocket:
    def __init__(self, inbound):
        self._inbound = list(inbound)
        self.sent = []

    async def send(self, data):
        self.sent.append(data)

    async def close(self):
        pass

    def __aiter__(self):
        async def gen():
            for msg in self._inbound:
                yield json.dumps(msg)

        return gen()


async def _drive(sock_cls, frames):
    ws = FakeWebSocket(frames)
    sock = sock_cls(ws, lambda _segs: None, asyncio.get_running_loop())
    await asyncio.wait_for(sock._done_event.wait(), timeout=1)
    await sock.drain_and_close()
    return sock


def _wav_bytes(seconds: float, sample_rate: int = 16000) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, 'wb') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(b'\x00\x00' * int(sample_rate * seconds))
    return buf.getvalue()


@pytest.mark.asyncio
async def test_soniox_budget_error_logs_severity_and_code_without_payload(caplog):
    frame = {'error_code': 402, 'error_type': 'organization_balance_exhausted', 'error_message': SENTINEL}
    with caplog.at_level(logging.WARNING, logger='utils.stt.soniox'):
        sock = await _drive(soniox.SafeSonioxSocket, [frame])
    assert sock.is_connection_dead
    assert sock.typed_death_reason == PROVIDER_BUDGET_EXHAUSTED
    errors = [r for r in caplog.records if r.levelno == logging.ERROR and 'Soniox streaming error:' in r.getMessage()]
    assert errors
    assert 'code=402' in errors[0].getMessage()
    assert 'organization_balance_exhausted' in errors[0].getMessage()
    assert SENTINEL not in _caplog_text(caplog)


@pytest.mark.asyncio
async def test_soniox_warning_path_redacts_payload(caplog):
    frame = {'error_code': 400, 'error_type': 'invalid_request', 'error_message': f'No audio received {SENTINEL}'}
    with caplog.at_level(logging.WARNING, logger='utils.stt.soniox'):
        await _drive(soniox.SafeSonioxSocket, [frame])
    warnings = [r for r in caplog.records if 'Soniox stream closed:' in r.getMessage()]
    assert warnings
    assert 'code=400' in warnings[0].getMessage()
    assert 'no audio received' in warnings[0].getMessage()
    assert SENTINEL not in _caplog_text(caplog)


@pytest.mark.asyncio
@pytest.mark.parametrize('resilient,expected_reason', [('false', 'connection_lost'), ('true', 'provider_5xx')])
async def test_soniox_arbitrary_error_type_stays_typed_and_bounded(monkeypatch, caplog, resilient, expected_reason):
    monkeypatch.setenv('STT_RESILIENT_RECONNECT', resilient)
    frame = {
        'error_code': 500,
        'error_type': f'unexpected_vendor_shape {SENTINEL}',
        'error_message': f'{SENTINEL_EMAIL} {SENTINEL_URL}',
    }
    with caplog.at_level(logging.WARNING, logger='utils.stt.soniox'):
        sock = await _drive(soniox.SafeSonioxSocket, [frame])
    assert sock.typed_death_reason == expected_reason
    warnings = [r for r in caplog.records if 'Soniox stream closed:' in r.getMessage()]
    assert warnings
    assert 'code=500' in warnings[0].getMessage()
    assert '[redacted]' in warnings[0].getMessage()
    assert SENTINEL not in _caplog_text(caplog)
    assert SENTINEL_EMAIL not in _caplog_text(caplog)
    assert SENTINEL_URL not in _caplog_text(caplog)


def test_soniox_persistent_rate_limit_log_redacts_payload(monkeypatch, caplog):
    monkeypatch.setattr(soniox, '_last_rate_limit_error_log', float('-inf'))
    monkeypatch.setattr(soniox, '_rate_limit_events', [])
    with caplog.at_level(logging.WARNING, logger='utils.stt.soniox'):
        soniox._rate_limit_persistent_error(f'429 limit_exceeded {SENTINEL} {SENTINEL_URL}', force=True)
    errors = [r for r in caplog.records if 'rate limiting persists' in r.getMessage()]
    assert errors
    assert 'code=429' in errors[0].getMessage()
    assert 'limit_exceeded' in errors[0].getMessage()
    assert SENTINEL not in _caplog_text(caplog)
    assert SENTINEL_URL not in _caplog_text(caplog)


def test_soniox_first_rate_limit_escalation_logs_on_a_freshly_booted_host(monkeypatch, caplog):
    # A pristine module copy exercises the real initial throttle state, which other
    # tests overwrite; the monotonic clock is two minutes past boot, inside the window.
    spec = importlib.util.find_spec('utils.stt.soniox')
    fresh = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fresh)
    monkeypatch.setattr(fresh.time, 'monotonic', lambda: 120.0)
    with caplog.at_level(logging.WARNING, logger='utils.stt.soniox'):
        fresh._rate_limit_persistent_error('429 limit_exceeded', force=True)
    assert [r for r in caplog.records if 'rate limiting persists' in r.getMessage()]


@pytest.mark.asyncio
async def test_modulate_serve_error_logs_severity_and_code_without_payload(caplog):
    frame = {'type': 'error', 'error': f'Internal server error {SENTINEL} {SENTINEL_EMAIL}'}
    with caplog.at_level(logging.WARNING, logger='utils.stt.streaming'):
        sock = await _drive(SafeModulateSocket, [frame])
    assert sock.is_connection_dead
    assert sock.typed_death_reason == MODULATE_DEATH_SERVE_ERROR
    errors = [r for r in caplog.records if r.levelno == logging.ERROR and 'Modulate streaming error:' in r.getMessage()]
    assert errors
    assert 'internal server error' in errors[0].getMessage()
    assert SENTINEL not in _caplog_text(caplog)
    assert SENTINEL_EMAIL not in _caplog_text(caplog)


@pytest.mark.asyncio
async def test_modulate_session_frame_logs_warning_without_payload(caplog):
    frame = {'type': 'error', 'error': f'Invalid input audio {SENTINEL}'}
    with caplog.at_level(logging.WARNING, logger='utils.stt.streaming'):
        await _drive(SafeModulateSocket, [frame])
    warnings = [r for r in caplog.records if 'Modulate stream closed:' in r.getMessage()]
    assert warnings
    assert 'invalid input audio' in warnings[0].getMessage()
    assert SENTINEL not in _caplog_text(caplog)


def test_safe_deepgram_send_exception_redacts_payload(caplog):
    conn = MagicMock()
    conn.send.side_effect = RuntimeError(f'send failed {SENTINEL} {SENTINEL_URL}')
    sock = SafeDeepgramSocket(conn)
    try:
        with caplog.at_level(logging.WARNING, logger='utils.stt.safe_socket'):
            assert sock.send(b'\x00' * 960) is False
        warnings = [r for r in caplog.records if 'DG send exception' in r.getMessage()]
        assert warnings
        assert 'exception_type=RuntimeError' in warnings[0].getMessage()
        assert warnings[0].exc_info is None
        assert SENTINEL not in _caplog_text(caplog)
        assert SENTINEL_URL not in _caplog_text(caplog)
    finally:
        sock.finish()


def test_safe_deepgram_finalize_exception_redacts_payload(caplog):
    conn = MagicMock()
    conn.finalize.side_effect = RuntimeError(f'finalize failed {SENTINEL}')
    sock = SafeDeepgramSocket(conn)
    try:
        with caplog.at_level(logging.WARNING, logger='utils.stt.safe_socket'):
            with pytest.raises(RuntimeError):
                sock.finalize()
        warnings = [r for r in caplog.records if 'DG finalize exception' in r.getMessage()]
        assert warnings
        assert 'exception_type=RuntimeError' in warnings[0].getMessage()
        assert warnings[0].exc_info is None
        assert SENTINEL not in _caplog_text(caplog)
    finally:
        sock.finish()


@pytest.mark.asyncio
async def test_deepgram_owned_callbacks_log_safely_and_latch_close(caplog):
    mock_dg_conn = MagicMock()
    captured_on_error = {}

    async def fake_connect(on_message, on_error, *args, **kwargs):
        captured_on_error['handler'] = on_error
        return mock_dg_conn

    with (
        patch.object(streaming, 'connect_to_deepgram_with_backoff', new=AsyncMock(side_effect=fake_connect)),
        caplog.at_level(logging.INFO, logger='utils.stt.streaming'),
    ):
        safe = await streaming.process_audio_dg(
            stream_transcript=MagicMock(), language='en', sample_rate=16000, channels=1
        )
        try:
            captured_on_error['handler'](None, f'ErrorResponse {SENTINEL}')
            registered = {call[0][0]: call[0][1] for call in mock_dg_conn.on.call_args_list}
            close_handler = registered[streaming.LiveTranscriptionEvents.Close]
            error_handler = registered[streaming.LiveTranscriptionEvents.Error]
            close_handler(None, f'CloseResponse {SENTINEL} {SENTINEL_URL}')
            assert safe.is_connection_dead
            error_handler(None, f'ErrorResponse {SENTINEL_EMAIL}')
        finally:
            safe.finish()
    errors = [r for r in caplog.records if r.levelno == logging.ERROR and r.getMessage().startswith('Deepgram error:')]
    assert errors
    warnings = [r for r in caplog.records if 'close-reason capture' in r.getMessage()]
    assert warnings
    infos = [r for r in caplog.records if 'Deepgram connection closed:' in r.getMessage()]
    assert infos
    text = _caplog_text(caplog)
    assert SENTINEL not in text
    assert SENTINEL_EMAIL not in text
    assert SENTINEL_URL not in text


def test_deepgram_metadata_callback_emits_no_log(monkeypatch, caplog):
    mock_dg_conn = MagicMock()
    client = MagicMock()
    client.listen.websocket.v.return_value = mock_dg_conn
    monkeypatch.setattr(streaming, '_deepgram_client_for_request', lambda: client)
    monkeypatch.setenv('DEEPGRAM_API_KEY', 'test-key')
    streaming.connect_to_deepgram(MagicMock(), MagicMock(), 'en', 16000, 1, 'nova-3')
    registered = {call[0][0]: call[0][1] for call in mock_dg_conn.on.call_args_list}
    with caplog.at_level(logging.INFO, logger='utils.stt.streaming'):
        registered[streaming.LiveTranscriptionEvents.Metadata](None, f'MetadataResponse {SENTINEL} {SENTINEL_URL}')
    assert not [r for r in caplog.records if 'Metadata' in r.getMessage()]
    assert SENTINEL not in _caplog_text(caplog)
    assert SENTINEL_URL not in _caplog_text(caplog)


@pytest.mark.asyncio
async def test_parakeet_transcribe_failure_redacts_payload(monkeypatch, caplog):
    class FailingClient:
        async def post(self, url, **kwargs):
            raise RuntimeError(f'provider replied {SENTINEL} {SENTINEL_EMAIL}\nstack {SENTINEL_URL}')

    @asynccontextmanager
    async def semaphore():
        yield

    monkeypatch.setattr(streaming, 'get_stt_client', lambda: FailingClient())
    monkeypatch.setattr(streaming, 'get_stt_semaphore', semaphore)
    sock = streaming.ParakeetStreamingSocket(lambda _segs: None, 'http://fake', 16000)
    with caplog.at_level(logging.WARNING, logger='utils.stt.streaming'):
        assert await sock._transcribe_chunk(b'\x00\x00' * 1600, 0.0, 0.1) == []
    errors = [r for r in caplog.records if 'Parakeet transcribe failed' in r.getMessage()]
    assert errors
    assert 'exception_type=RuntimeError' in errors[0].getMessage()
    assert errors[0].exc_info is None
    assert SENTINEL not in _caplog_text(caplog)
    assert SENTINEL_EMAIL not in _caplog_text(caplog)
    assert SENTINEL_URL not in _caplog_text(caplog)


@pytest.mark.asyncio
async def test_parakeet_pump_loop_error_redacts_payload(monkeypatch, caplog):
    real_sleep = asyncio.sleep

    async def fast_sleep(_seconds):
        await real_sleep(0)

    async def boom(force):
        raise TypeError(f'flush exploded {SENTINEL}')

    sock = streaming.ParakeetStreamingSocket(lambda _segs: None, 'http://fake', 16000)
    monkeypatch.setattr(asyncio, 'sleep', fast_sleep)
    monkeypatch.setattr(sock, '_flush', boom)
    with caplog.at_level(logging.WARNING, logger='utils.stt.streaming'):
        await sock._pump()
    errors = [r for r in caplog.records if 'Parakeet pump loop error' in r.getMessage()]
    assert errors
    assert 'exception_type=TypeError' in errors[0].getMessage()
    assert errors[0].exc_info is None
    assert SENTINEL not in _caplog_text(caplog)
    assert sock._dead
    assert SENTINEL in sock._dead_reason


@pytest.mark.asyncio
async def test_parakeet_drain_pump_await_error_redacts_payload(monkeypatch, caplog):
    async def boom():
        raise ValueError(f'pump died {SENTINEL}')

    async def no_flush(force):
        return None

    sock = streaming.ParakeetStreamingSocket(lambda _segs: None, 'http://fake', 16000)
    sock._pump_task = asyncio.create_task(boom())
    monkeypatch.setattr(sock, '_flush', no_flush)
    with caplog.at_level(logging.WARNING, logger='utils.stt.streaming'):
        await sock.drain_and_close()
    errors = [r for r in caplog.records if 'Parakeet pump await error during drain' in r.getMessage()]
    assert errors
    assert 'exception_type=ValueError' in errors[0].getMessage()
    assert errors[0].exc_info is None
    assert SENTINEL not in _caplog_text(caplog)


@pytest.mark.asyncio
async def test_parakeet_ws_start_failure_redacts_dead_reason(monkeypatch, caplog):
    sock = streaming.ParakeetWebSocketSocket(lambda _segs: None, 'ws://fake.invalid', 16000)
    sock._mark_dead(f'parakeet ws failed: {SENTINEL}')

    async def stub_run():
        sock._startup_event.set()

    monkeypatch.setattr(sock, '_run', stub_run)
    with caplog.at_level(logging.WARNING, logger='utils.stt.streaming'):
        with pytest.raises(ParakeetConnectionError):
            await sock.start()
    errors = [r for r in caplog.records if 'Parakeet WS failed before connection' in r.getMessage()]
    assert errors
    assert SENTINEL not in _caplog_text(caplog)
    await asyncio.gather(sock._sender_task, return_exceptions=True)


def test_parakeet_batch_diarization_failure_redacts_payload(monkeypatch, caplog):
    def boom(_wav):
        raise RuntimeError(f'embedding service: {SENTINEL}')

    monkeypatch.setattr(pre_recorded, 'extract_embedding_from_bytes', boom)
    with caplog.at_level(logging.WARNING, logger='utils.stt.pre_recorded'):
        assert pre_recorded._parakeet_assign_speaker_sync(_wav_bytes(1.0), 16000, 0.0, 1.0, [], []) == 'SPEAKER_00'
    warnings = [r for r in caplog.records if 'batch diarization failed' in r.getMessage()]
    assert warnings
    assert SENTINEL not in _caplog_text(caplog)


@pytest.mark.asyncio
async def test_embedding_failure_redacts_payload(monkeypatch, caplog):
    class FailingClient:
        async def post(self, url, **kwargs):
            raise RuntimeError(f'embedding endpoint: {SENTINEL} {SENTINEL_URL}')

    monkeypatch.setenv('HOSTED_SPEAKER_EMBEDDING_API_URL', 'http://embedding.invalid')
    monkeypatch.setattr(speaker_embedding, 'get_stt_client', lambda: FailingClient())
    with caplog.at_level(logging.WARNING, logger='utils.stt.speaker_embedding'):
        with pytest.raises(RuntimeError):
            await speaker_embedding.async_extract_embedding_from_bytes(_wav_bytes(0.7))
    errors = [r for r in caplog.records if 'async_extract_embedding_from_bytes failed' in r.getMessage()]
    assert errors
    assert SENTINEL not in _caplog_text(caplog)
    assert SENTINEL_URL not in _caplog_text(caplog)


def test_vad_decode_failure_drops_path_and_payload(monkeypatch, caplog, tmp_path):
    secret_path = tmp_path / f'{SENTINEL}.wav'
    secret_path.write_bytes(b'not-audio')

    def boom(_path):
        raise RuntimeError(f'decode failed {SENTINEL}')

    monkeypatch.setattr(vad.AudioSegment, 'from_file', boom)
    with caplog.at_level(logging.WARNING, logger='utils.stt.vad'):
        assert vad._run_file_vad(str(secret_path)) == []
    errors = [r for r in caplog.records if 'Failed to read audio file' in r.getMessage()]
    assert errors
    assert SENTINEL not in _caplog_text(caplog)


@pytest.mark.asyncio
async def test_parakeet_window_post_failure_stays_bounded_without_body(monkeypatch, caplog):
    monkeypatch.setattr(
        streaming,
        '_parakeet_circuit',
        provider_resilience.ProviderCircuitBreaker(failure_threshold=1, cooldown_seconds=30),
    )

    class BodyClient:
        async def post(self, url, **kwargs):
            return httpx.Response(500, text=f'upstream exploded {SENTINEL}', request=httpx.Request('POST', url))

    @asynccontextmanager
    async def semaphore():
        yield

    monkeypatch.setattr(parakeet_window, 'get_stt_client', lambda: BodyClient())
    monkeypatch.setattr(parakeet_window, 'get_stt_semaphore', semaphore)
    monkeypatch.setenv('HOSTED_PARAKEET_API_URL', 'http://fake')
    sock = parakeet_window.WindowedParakeetSocket(lambda _segs: None, 'http://fake', 16000, lambda: None)
    sock.start()
    with caplog.at_level(logging.WARNING, logger='utils.stt.parakeet_window'):
        with pytest.raises(Exception):
            await sock._post_and_parse(b'\x01\x00' * 16000, 1.0)
    assert sock._dead_reason == 'provider_5xx'
    assert SENTINEL not in _caplog_text(caplog)
    sock.finish()
    await asyncio.gather(sock._pump_task, return_exceptions=True)


@pytest.mark.asyncio
async def test_parakeet_window_invalid_body_logs_no_payload(monkeypatch, caplog):
    class BadJsonClient:
        async def post(self, url, **kwargs):
            return httpx.Response(200, text=SENTINEL, request=httpx.Request('POST', url))

    @asynccontextmanager
    async def semaphore():
        yield

    monkeypatch.setattr(parakeet_window, 'get_stt_client', lambda: BadJsonClient())
    monkeypatch.setattr(parakeet_window, 'get_stt_semaphore', semaphore)
    monkeypatch.setenv('HOSTED_PARAKEET_API_URL', 'http://fake')
    sock = parakeet_window.WindowedParakeetSocket(lambda _segs: None, 'http://fake', 16000, lambda: None)
    sock.start()
    with caplog.at_level(logging.WARNING, logger='utils.stt.parakeet_window'):
        with pytest.raises(Exception):
            await sock._post_and_parse(b'\x01\x00' * 16000, 1.0)
    assert sock._dead_reason == 'provider_5xx'
    assert SENTINEL not in _caplog_text(caplog)
    sock.finish()
    await asyncio.gather(sock._pump_task, return_exceptions=True)
