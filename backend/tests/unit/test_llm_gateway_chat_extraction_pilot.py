from __future__ import annotations

import sys
import types
import logging
from contextlib import contextmanager

import pytest

for module_name in (
    'database.auth',
    'database.goals',
    'database.notifications',
    'database.redis_db',
    'database.users',
):
    sys.modules.setdefault(module_name, types.ModuleType(module_name))

sys.modules['database.auth'].get_user_name = lambda uid: 'Test User'
sys.modules['database.redis_db'].add_filter_category_item = lambda *args, **kwargs: None


@contextmanager
def _track_usage(*args, **kwargs):
    yield


usage_tracker_stub = types.ModuleType('utils.llm.usage_tracker')
usage_tracker_stub.track_usage = _track_usage
usage_tracker_stub.Features = types.SimpleNamespace(CHAT='chat')
sys.modules.setdefault('utils.llm.usage_tracker', usage_tracker_stub)

memory_stub = types.ModuleType('utils.llms.memory')
memory_stub.get_prompt_memories = lambda uid: ('Test User', '')
sys.modules.setdefault('utils.llms.memory', memory_stub)

clients_stub = types.ModuleType('utils.llm.clients')
clients_stub.get_llm = lambda feature: None
sys.modules.setdefault('utils.llm.clients', clients_stub)

from utils import byok
from utils.llm import chat, gateway_client


class FakeParser:
    def __init__(self, response):
        self.response = response

    def invoke(self, prompt):
        return self.response


class FakeLLM:
    def __init__(self, response, calls):
        self.response = response
        self.calls = calls

    def with_structured_output(self, output_model):
        self.calls.append(output_model)
        return FakeParser(self.response)


class FakeGatewayResponse:
    def __init__(self, body):
        self.body = body

    def raise_for_status(self):
        return None

    def json(self):
        return self.body


@pytest.fixture(autouse=True)
def clear_byok_context():
    byok.set_byok_keys({})
    yield
    byok.set_byok_keys({})


class FakeCounterChild:
    def __init__(self, parent, labels):
        self.parent = parent
        self.labels = labels

    def inc(self, amount=1):
        self.parent.calls.append((self.labels, amount))


class FakeCounter:
    def __init__(self):
        self.calls = []

    def labels(self, **labels):
        return FakeCounterChild(self, labels)


def test_requires_context_non_byok_tries_gateway_by_default(monkeypatch):
    monkeypatch.setattr(
        chat,
        'invoke_chat_structured_gateway',
        lambda prompt, output_model, *, feature: output_model(value=True),
    )
    monkeypatch.setattr(
        chat,
        'get_llm',
        lambda feature: pytest.fail('existing path should not be called after gateway success'),
    )

    assert chat.requires_context('hello?') is True


def test_requires_context_gateway_success_returns_parsed_result(monkeypatch):
    monkeypatch.setattr(
        chat,
        'get_llm',
        lambda feature: pytest.fail('existing path should not be called after gateway success'),
    )
    monkeypatch.setattr(
        chat,
        'invoke_chat_structured_gateway',
        lambda prompt, output_model, *, feature: output_model(value=True),
    )

    assert chat.requires_context('what did I discuss yesterday?') is True


def test_requires_context_gateway_failure_falls_back(monkeypatch):
    existing_calls = []
    monkeypatch.setattr(chat, 'get_llm', lambda feature: FakeLLM(chat.RequiresContext(value=False), existing_calls))
    monkeypatch.setattr(chat, 'invoke_chat_structured_gateway', lambda *args, **kwargs: None)

    assert chat.requires_context('what did I discuss yesterday?') is False
    assert existing_calls == [chat.RequiresContext]


def test_requires_context_byok_context_skips_gateway(monkeypatch):
    byok.set_byok_keys({'openai': 'secret'})
    existing_calls = []
    counter = FakeCounter()
    monkeypatch.setattr(
        chat, 'record_chat_extraction_gateway_result', gateway_client.record_chat_extraction_gateway_result
    )
    monkeypatch.setattr(gateway_client, 'LLM_GATEWAY_CHAT_EXTRACTION_REQUESTS', counter)
    monkeypatch.setattr(chat, 'get_llm', lambda feature: FakeLLM(chat.RequiresContext(value=True), existing_calls))
    monkeypatch.setattr(
        chat,
        'invoke_chat_structured_gateway',
        lambda *args, **kwargs: pytest.fail('gateway should not be called for BYOK requests'),
    )

    assert chat.requires_context('what did I discuss yesterday?') is True
    assert existing_calls == [chat.RequiresContext]
    assert counter.calls == [
        (
            {
                'feature': 'chat_extraction.requires_context',
                'outcome': 'skipped',
                'reason': 'byok',
            },
            1,
        )
    ]


def test_requires_context_invalid_gateway_content_falls_back(monkeypatch):
    existing_calls = []
    monkeypatch.setattr(chat, 'get_llm', lambda feature: FakeLLM(chat.RequiresContext(value=False), existing_calls))
    monkeypatch.setattr(
        gateway_client.httpx,
        'post',
        lambda *args, **kwargs: FakeGatewayResponse({'choices': [{'message': {'content': '{"unexpected": true}'}}]}),
    )

    assert chat.requires_context('what did I discuss yesterday?') is False
    assert existing_calls == [chat.RequiresContext]


def test_chat_structured_gateway_request_uses_auto_lane_and_service_auth(monkeypatch):
    monkeypatch.setenv('OMI_LLM_GATEWAY_URL', 'http://gateway.test/')
    monkeypatch.setenv('OMI_LLM_GATEWAY_SERVICE_TOKEN', 'service-token')
    captured = {}

    def fake_post(url, *, headers, json, timeout):
        captured.update({'url': url, 'headers': headers, 'json': json, 'timeout': timeout})
        return FakeGatewayResponse({'choices': [{'message': {'content': '{"value": true}'}}]})

    monkeypatch.setattr(gateway_client.httpx, 'post', fake_post)

    result = gateway_client.invoke_chat_structured_gateway(
        'classified prompt',
        chat.RequiresContext,
        feature='chat_extraction.requires_context',
    )

    assert result == chat.RequiresContext(value=True)
    assert captured['url'] == 'http://gateway.test/v1/chat/completions'
    assert captured['headers']['Authorization'] == 'Bearer service-token'
    assert captured['headers']['X-Omi-Service-Caller'] == 'backend'
    assert captured['json']['model'] == 'omi:auto:chat-structured'
    assert captured['json']['messages'] == [{'role': 'user', 'content': 'classified prompt'}]
    assert captured['json']['response_format']['type'] == 'json_schema'
    assert captured['json']['response_format']['json_schema']['schema']['properties']['value']['type'] == 'boolean'


def test_chat_structured_gateway_records_success_metric(monkeypatch):
    counter = FakeCounter()
    monkeypatch.setattr(gateway_client, 'LLM_GATEWAY_CHAT_EXTRACTION_REQUESTS', counter)
    monkeypatch.setattr(
        gateway_client.httpx,
        'post',
        lambda *args, **kwargs: FakeGatewayResponse({'choices': [{'message': {'content': '{"value": true}'}}]}),
    )

    result = gateway_client.invoke_chat_structured_gateway(
        'classified prompt',
        chat.RequiresContext,
        feature='chat_extraction.requires_context',
    )

    assert result == chat.RequiresContext(value=True)
    assert counter.calls == [
        (
            {
                'feature': 'chat_extraction.requires_context',
                'outcome': 'success',
                'reason': 'ok',
            },
            1,
        )
    ]


def test_chat_structured_gateway_records_fallback_reason_metric(monkeypatch):
    counter = FakeCounter()
    monkeypatch.setattr(gateway_client, 'LLM_GATEWAY_CHAT_EXTRACTION_REQUESTS', counter)
    monkeypatch.setattr(
        gateway_client.httpx,
        'post',
        lambda *args, **kwargs: FakeGatewayResponse({'choices': [{'message': {'content': '{"unexpected": true}'}}]}),
    )

    result = gateway_client.invoke_chat_structured_gateway(
        'classified prompt',
        chat.RequiresContext,
        feature='chat_extraction.requires_context',
    )

    assert result is None
    assert counter.calls == [
        (
            {
                'feature': 'chat_extraction.requires_context',
                'outcome': 'fallback',
                'reason': 'schema_validation',
            },
            1,
        )
    ]


def test_chat_structured_gateway_failure_does_not_log_raw_prompt_or_response(monkeypatch, caplog):
    def fake_post(*args, **kwargs):
        raise RuntimeError('raw provider body should not be logged')

    monkeypatch.setattr(gateway_client.httpx, 'post', fake_post)

    with caplog.at_level(logging.DEBUG):
        result = gateway_client.invoke_chat_structured_gateway(
            'raw user question should not be logged',
            chat.RequiresContext,
            feature='chat_extraction.requires_context',
        )

    assert result is None
    assert 'raw user question should not be logged' not in caplog.text
    assert 'raw provider body should not be logged' not in caplog.text
