from __future__ import annotations

import httpx

from utils.llm import gateway_serving


def test_network_and_timeout_errors_are_transport_failures():
    assert gateway_serving.is_gateway_transport_failure(httpx.ConnectError('connection refused'))
    assert gateway_serving.is_gateway_transport_failure(httpx.ReadTimeout('timed out'))


def test_only_hard_gateway_statuses_are_transport_failures():
    for status_code, expected in ((502, True), (503, False), (504, True)):
        request = httpx.Request('POST', 'http://gateway/v1/chat/completions')
        error = httpx.HTTPStatusError(
            'gateway error',
            request=request,
            response=httpx.Response(status_code, request=request),
        )
        assert gateway_serving.is_gateway_transport_failure(error) is expected


def test_nontransport_application_error_is_not_classified_as_transport():
    assert gateway_serving.is_gateway_transport_failure(ValueError('schema invalid')) is False


def test_retired_legacy_fallback_shim_is_not_reintroduced():
    """The retired compatibility layer must not return (AGENTS.md: no in-repo
    compatibility layers). A stale caller passing a ``legacy_model`` should be a
    hard failure at import time, not silently discarded."""
    assert not hasattr(gateway_serving, 'wrap_gateway_with_legacy_fallback')
