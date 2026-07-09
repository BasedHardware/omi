from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from utils.llm import gateway_observability


class _CounterStub:
    def __init__(self) -> None:
        self.calls: list[dict[str, str]] = []

    def labels(self, **kwargs: str):
        self.calls.append(kwargs)
        return MagicMock(inc=MagicMock())


def test_record_gateway_request_result_maps_success_to_serving_mode(monkeypatch):
    counter = _CounterStub()
    monkeypatch.setattr(gateway_observability, 'LLM_GATEWAY_CHAT_EXTRACTION_REQUESTS', counter)
    monkeypatch.setattr(gateway_observability, '_observability_logs_enabled', lambda: False)

    gateway_observability.record_gateway_request_result(
        feature='conv_discard',
        outcome='success',
        reason='ok',
        route='omi:auto:conv-discard',
    )

    assert counter.calls == [
        {
            'feature': 'conv_discard',
            'mode': 'serving',
            'outcome': 'success',
            'reason': 'ok',
        }
    ]


def test_record_gateway_request_result_maps_fallback_mode(monkeypatch):
    counter = _CounterStub()
    monkeypatch.setattr(gateway_observability, 'LLM_GATEWAY_CHAT_EXTRACTION_REQUESTS', counter)
    monkeypatch.setattr(gateway_observability, '_observability_logs_enabled', lambda: False)

    gateway_observability.record_gateway_request_result(
        feature='knowledge_graph',
        outcome='fallback',
        reason='timeout',
        route='omi:auto:knowledge-graph',
    )

    assert counter.calls[0]['mode'] == 'fallback'


def test_record_direct_exception_surface_increments_counter(monkeypatch):
    counter = _CounterStub()
    monkeypatch.setattr(gateway_observability, 'LLM_GATEWAY_DIRECT_EXCEPTION_REQUESTS', counter)
    monkeypatch.setattr(gateway_observability, '_observability_logs_enabled', lambda: False)

    gateway_observability.record_direct_exception_surface(
        surface='chat_agent.anthropic_stream',
        reason='acknowledged',
    )

    assert counter.calls == [{'surface': 'chat_agent.anthropic_stream', 'reason': 'acknowledged'}]


def test_raise_if_gateway_feature_mode_records_direct_exception_when_allowed(monkeypatch):
    from utils.llm import gateway_client
    from utils.llm.gateway_client import (
        LLM_GATEWAY_ALLOW_DIRECT_EXCEPTION_ENV_VAR,
        LLM_GATEWAY_FEATURE_MODE_ENV_VAR,
        raise_if_gateway_feature_mode_blocks_direct_model_surface,
    )

    recorded: list[dict[str, str]] = []
    monkeypatch.setenv(LLM_GATEWAY_FEATURE_MODE_ENV_VAR, 'gateway')
    monkeypatch.setenv(LLM_GATEWAY_ALLOW_DIRECT_EXCEPTION_ENV_VAR, 'true')
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    monkeypatch.setattr(
        gateway_client,
        'record_direct_exception_surface',
        lambda **kwargs: recorded.append(kwargs),
    )

    raise_if_gateway_feature_mode_blocks_direct_model_surface('file_chat.openai_files')

    assert recorded == [{'surface': 'file_chat.openai_files', 'reason': 'acknowledged'}]
