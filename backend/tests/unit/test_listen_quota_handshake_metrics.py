"""Unit tests for listen WS handshake, API 429 rate-limit, and direct LLM 429/quota counters (#21461)."""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from utils import metrics
from utils.llm import byok_errors
from utils.other import endpoints


class _FakeHTTPError(Exception):
    def __init__(self, message: str, status_code: int):
        super().__init__(message)
        self.status_code = status_code


class RateLimitError(Exception):
    pass


def _counter_value(counter, **labels) -> float:
    return counter.labels(**labels)._value.get()


def test_metrics_have_zero_initialized_bounded_children():
    for surface in ('mobile', 'web'):
        assert (
            _counter_value(
                metrics.OMI_LISTEN_WS_HANDSHAKE_FAILURES_TOTAL,
                surface=surface,
                reason='accept_runtime_error',
            )
            >= 0.0
        )

    for scope in ('redis_policy', 'ip_window'):
        for family in ('chat', 'conversations', 'memories', 'stt', 'voice', 'custom'):
            assert (
                _counter_value(
                    metrics.OMI_API_RATE_LIMIT_THROTTLED_TOTAL,
                    scope=scope,
                    policy_family=family,
                )
                >= 0.0
            )

    for provider in ('openai', 'anthropic', 'gemini', 'openrouter', 'groq', 'other'):
        for source in ('platform', 'byok'):
            for reason in ('quota', 'rate_limit'):
                assert (
                    _counter_value(
                        metrics.OMI_DIRECT_LLM_RATE_LIMIT_ERRORS_TOTAL,
                        provider=provider,
                        source=source,
                        reason=reason,
                    )
                    >= 0.0
                )


def test_record_helpers_collapse_unbounded_labels():
    before_ws = _counter_value(
        metrics.OMI_LISTEN_WS_HANDSHAKE_FAILURES_TOTAL,
        surface='other',
        reason='other',
    )
    metrics.record_listen_ws_handshake_failure(surface='unexpected-surface', reason='unexpected-reason')
    assert (
        _counter_value(
            metrics.OMI_LISTEN_WS_HANDSHAKE_FAILURES_TOTAL,
            surface='other',
            reason='other',
        )
        == before_ws + 1.0
    )

    before_rl = _counter_value(
        metrics.OMI_API_RATE_LIMIT_THROTTLED_TOTAL,
        scope='other',
        policy_family='custom',
    )
    metrics.record_api_rate_limit_throttled(scope='unknown_scope', policy='unbounded_user_id:12345')
    assert (
        _counter_value(
            metrics.OMI_API_RATE_LIMIT_THROTTLED_TOTAL,
            scope='other',
            policy_family='custom',
        )
        == before_rl + 1.0
    )

    before_llm = _counter_value(
        metrics.OMI_DIRECT_LLM_RATE_LIMIT_ERRORS_TOTAL,
        provider='other',
        source='other',
        reason='rate_limit',
    )
    metrics.record_direct_llm_rate_limit_error(provider='custom-vendor', source='invalid', reason='invalid')
    assert (
        _counter_value(
            metrics.OMI_DIRECT_LLM_RATE_LIMIT_ERRORS_TOTAL,
            provider='other',
            source='other',
            reason='rate_limit',
        )
        == before_llm + 1.0
    )


def test_listen_and_web_listen_handshake_failures_increment_counter():
    from testing.import_isolation import stub_modules

    runtime_stub = SimpleNamespace(run_listen_session=AsyncMock())
    with stub_modules({'routers.listen.runtime': runtime_stub}):
        from routers import transcribe

        ws = MagicMock()
        ws.accept = AsyncMock(side_effect=RuntimeError('ASGI callable returned without sending handshake'))

        before_mobile = _counter_value(
            metrics.OMI_LISTEN_WS_HANDSHAKE_FAILURES_TOTAL,
            surface='mobile',
            reason='accept_runtime_error',
        )
        asyncio.run(transcribe._listen(ws, 'uid-test'))
        assert (
            _counter_value(
                metrics.OMI_LISTEN_WS_HANDSHAKE_FAILURES_TOTAL,
                surface='mobile',
                reason='accept_runtime_error',
            )
            == before_mobile + 1.0
        )

        before_web = _counter_value(
            metrics.OMI_LISTEN_WS_HANDSHAKE_FAILURES_TOTAL,
            surface='web',
            reason='accept_runtime_error',
        )
        asyncio.run(transcribe.web_listen_handler(ws))
        assert (
            _counter_value(
                metrics.OMI_LISTEN_WS_HANDSHAKE_FAILURES_TOTAL,
                surface='web',
                reason='accept_runtime_error',
            )
            == before_web + 1.0
        )


def test_rate_limit_429_increments_throttled_counter(monkeypatch):
    before_redis = _counter_value(
        metrics.OMI_API_RATE_LIMIT_THROTTLED_TOTAL,
        scope='redis_policy',
        policy_family='voice',
    )
    monkeypatch.setattr(endpoints, 'RATE_LIMIT_SHADOW', False)
    monkeypatch.setattr(endpoints, 'check_rate_limit', lambda *_args, **_kwargs: (False, 0, 12))

    with pytest.raises(HTTPException) as exc_info:
        endpoints._enforce_rate_limit('uid-1', 'voice:transcribe')
    assert exc_info.value.status_code == 429
    assert (
        _counter_value(
            metrics.OMI_API_RATE_LIMIT_THROTTLED_TOTAL,
            scope='redis_policy',
            policy_family='voice',
        )
        == before_redis + 1.0
    )

    before_ip = _counter_value(
        metrics.OMI_API_RATE_LIMIT_THROTTLED_TOTAL,
        scope='ip_window',
        policy_family='custom',
    )
    fake_request = SimpleNamespace(client=SimpleNamespace(host='127.0.0.1'))
    endpoints.cached['rate_limit:phone_verify:127.0.0.1'] = json.dumps({'timestamp': 9999999999, 'remaining': 0})
    try:
        with pytest.raises(HTTPException) as ip_exc:
            endpoints.rate_limit_custom('phone_verify', fake_request, 5, 60)
        assert ip_exc.value.status_code == 429
    finally:
        endpoints.cached.pop('rate_limit:phone_verify:127.0.0.1', None)

    assert (
        _counter_value(
            metrics.OMI_API_RATE_LIMIT_THROTTLED_TOTAL,
            scope='ip_window',
            policy_family='custom',
        )
        == before_ip + 1.0
    )


@patch('utils.llm.byok_errors.get_byok_uid', return_value='user-1')
@patch('utils.llm.byok_errors._send_byok_llm_error_notification')
def test_handle_llm_error_records_platform_and_byok_429_and_quota_metrics(mock_notify, _mock_uid):
    before_platform_quota = _counter_value(
        metrics.OMI_DIRECT_LLM_RATE_LIMIT_ERRORS_TOTAL,
        provider='openai',
        source='platform',
        reason='quota',
    )
    before_platform_rl = _counter_value(
        metrics.OMI_DIRECT_LLM_RATE_LIMIT_ERRORS_TOTAL,
        provider='openai',
        source='platform',
        reason='rate_limit',
    )
    before_byok_quota = _counter_value(
        metrics.OMI_DIRECT_LLM_RATE_LIMIT_ERRORS_TOTAL,
        provider='openai',
        source='byok',
        reason='quota',
    )

    with patch('utils.llm.byok_errors.get_byok_key', return_value=None):
        byok_errors.handle_llm_error(
            _FakeHTTPError('You exceeded your current quota: insufficient_quota', 429), 'openai'
        )
        byok_errors.handle_llm_error(RateLimitError('Rate limit reached for gpt-4o'), 'openai')
        byok_errors.handle_llm_error(_FakeHTTPError('Internal server error', 500), 'openai')

    with patch('utils.llm.byok_errors.get_byok_key', return_value='sk-byok'):
        byok_errors.handle_llm_error(_FakeHTTPError('insufficient_quota', 429), 'openai')

    assert (
        _counter_value(
            metrics.OMI_DIRECT_LLM_RATE_LIMIT_ERRORS_TOTAL,
            provider='openai',
            source='platform',
            reason='quota',
        )
        == before_platform_quota + 1.0
    )
    assert (
        _counter_value(
            metrics.OMI_DIRECT_LLM_RATE_LIMIT_ERRORS_TOTAL,
            provider='openai',
            source='platform',
            reason='rate_limit',
        )
        == before_platform_rl + 1.0
    )
    assert (
        _counter_value(
            metrics.OMI_DIRECT_LLM_RATE_LIMIT_ERRORS_TOTAL,
            provider='openai',
            source='byok',
            reason='quota',
        )
        == before_byok_quota + 1.0
    )
    mock_notify.assert_called_once_with('user-1', 'openai', 'quota')
