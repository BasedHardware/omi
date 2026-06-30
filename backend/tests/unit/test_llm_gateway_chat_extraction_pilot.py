from __future__ import annotations

import sys
import types
import logging
from contextlib import contextmanager
from datetime import datetime, timezone

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
clients_stub.parser = object()
sys.modules.setdefault('utils.llm.clients', clients_stub)

from utils import byok
from utils.llm import chat, gateway_client
from utils.llm import conversation_processing
from models.conversation_enums import CategoryEnum
from models.structured import Structured
from models.structured_extraction import ActionItemsExtraction, ConversationStructureExtraction


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


class FakeGatewayClient:
    """Fake ``httpx.Client`` for tests. Returns a canned response from post()."""

    def __init__(self, fake_post):
        self._fake_post = fake_post

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def post(self, url, *, headers=None, json=None, **kwargs):
        return self._fake_post(url, headers=headers, json=json, **kwargs)


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


def _mock_gateway_client(monkeypatch, fake_post):
    """Patch ``httpx.Client`` so the gateway_client uses a fake HTTP client."""

    def fake_client(*args, **kwargs):
        return FakeGatewayClient(fake_post)

    monkeypatch.setattr(gateway_client.httpx, 'Client', fake_client)


_VALUE_TRUE_RESPONSE = FakeGatewayResponse({'choices': [{'message': {'content': '{"value": true}'}}]})
_UNEXPECTED_RESPONSE = FakeGatewayResponse({'choices': [{'message': {'content': '{"unexpected": true}'}}]})


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
    _mock_gateway_client(monkeypatch, lambda *args, **kwargs: _UNEXPECTED_RESPONSE)

    assert chat.requires_context('what did I discuss yesterday?') is False
    assert existing_calls == [chat.RequiresContext]


def test_chat_structured_gateway_request_uses_auto_lane_and_service_auth(monkeypatch):
    monkeypatch.setenv('OMI_LLM_GATEWAY_URL', 'http://gateway.test/')
    monkeypatch.setenv('OMI_LLM_GATEWAY_SERVICE_TOKEN', 'service-token')
    captured = {}

    def fake_post(url, *, headers=None, json=None, **kwargs):
        captured.update({'url': url, 'headers': headers, 'json': json})
        return _VALUE_TRUE_RESPONSE

    _mock_gateway_client(monkeypatch, fake_post)

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


def test_strict_schema_normalizes_action_item_extraction_for_openai():
    schema = gateway_client._strict_model_json_schema(ActionItemsExtraction)

    assert schema['additionalProperties'] is False
    assert schema['required'] == ['action_items']

    action_item_schema = schema['$defs']['ExtractedActionItem']
    assert action_item_schema['additionalProperties'] is False
    assert action_item_schema['required'] == ['description', 'due_at']
    assert 'default' not in action_item_schema['properties']['due_at']
    assert {'type': 'null'} in action_item_schema['properties']['due_at']['anyOf']


def test_strict_schema_keeps_conversation_structure_shadow_contract_narrow():
    schema = gateway_client._strict_model_json_schema(ConversationStructureExtraction)

    assert schema['additionalProperties'] is False
    assert schema['required'] == ['title', 'overview', 'emoji', 'category']
    assert set(schema['properties']) == {'title', 'overview', 'emoji', 'category'}
    assert 'action_items' not in schema['properties']
    assert 'events' not in schema['properties']


def test_strict_schema_removes_defaults_recursively():
    schema = gateway_client._strict_model_json_schema(ActionItemsExtraction)

    def walk(node):
        if isinstance(node, dict):
            assert 'default' not in node
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(schema)


def test_chat_structured_gateway_records_success_metric(monkeypatch):
    counter = FakeCounter()
    monkeypatch.setattr(gateway_client, 'LLM_GATEWAY_CHAT_EXTRACTION_REQUESTS', counter)
    _mock_gateway_client(monkeypatch, lambda *args, **kwargs: _VALUE_TRUE_RESPONSE)

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
    _mock_gateway_client(monkeypatch, lambda *args, **kwargs: _UNEXPECTED_RESPONSE)

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

    _mock_gateway_client(monkeypatch, fake_post)

    with caplog.at_level(logging.DEBUG):
        result = gateway_client.invoke_chat_structured_gateway(
            'raw user question should not be logged',
            chat.RequiresContext,
            feature='chat_extraction.requires_context',
        )

    assert result is None
    assert 'raw user question should not be logged' not in caplog.text
    assert 'raw provider body should not be logged' not in caplog.text


def test_conversation_discard_gateway_success_returns_without_legacy_llm(monkeypatch):
    captured = {}

    def fake_gateway(prompt, output_model, *, feature):
        captured.update({'prompt': prompt, 'output_model': output_model, 'feature': feature})
        return output_model(discard=True)

    monkeypatch.setattr(conversation_processing, 'invoke_chat_structured_gateway', fake_gateway)
    monkeypatch.setattr(
        conversation_processing,
        'get_llm',
        lambda feature, **kwargs: pytest.fail('legacy discard path should not be called after gateway success'),
    )

    assert conversation_processing.should_discard_conversation('hello there', duration_seconds=15) is True
    assert captured['output_model'] is conversation_processing.DiscardConversation
    assert captured['feature'] == 'conversation_discard.should_discard'
    assert 'hello there' in captured['prompt']


def test_conversation_discard_byok_skips_gateway_and_uses_legacy_llm(monkeypatch):
    class FakeParser:
        def __init__(self, pydantic_object):
            self.pydantic_object = pydantic_object

        def get_format_instructions(self):
            return 'return structured output'

    class FakePrompt:
        def __or__(self, other):
            return FakeChain()

    class FakeChain:
        def __or__(self, other):
            return self

        def invoke(self, values):
            assert 'hello there' in values['full_context']
            return conversation_processing.DiscardConversation(discard=False)

    byok.set_byok_keys({'openai': 'secret'})
    counter = FakeCounter()
    monkeypatch.setattr(gateway_client, 'LLM_GATEWAY_CHAT_EXTRACTION_REQUESTS', counter)
    monkeypatch.setattr(
        conversation_processing,
        'invoke_chat_structured_gateway',
        lambda *args, **kwargs: pytest.fail('gateway should not be called for BYOK requests'),
    )
    monkeypatch.setattr(conversation_processing, 'PydanticOutputParser', FakeParser)
    monkeypatch.setattr(conversation_processing.ChatPromptTemplate, 'from_messages', lambda messages: FakePrompt())
    monkeypatch.setattr(conversation_processing, 'get_llm', lambda feature, **kwargs: object())

    assert conversation_processing.should_discard_conversation('hello there', duration_seconds=15) is False
    assert counter.calls == [
        (
            {
                'feature': 'conversation_discard.should_discard',
                'outcome': 'skipped',
                'reason': 'byok',
            },
            1,
        )
    ]


def test_conversation_discard_gateway_failure_falls_back_to_legacy_llm(monkeypatch):
    class FakeParser:
        def __init__(self, pydantic_object):
            self.pydantic_object = pydantic_object

        def get_format_instructions(self):
            return 'return structured output'

    class FakePrompt:
        def __or__(self, other):
            return FakeChain()

    class FakeChain:
        def __or__(self, other):
            return self

        def invoke(self, values):
            assert 'hello there' in values['full_context']
            return conversation_processing.DiscardConversation(discard=False)

    monkeypatch.setattr(conversation_processing, 'invoke_chat_structured_gateway', lambda *args, **kwargs: None)
    monkeypatch.setattr(conversation_processing, 'PydanticOutputParser', FakeParser)
    monkeypatch.setattr(
        conversation_processing.ChatPromptTemplate,
        'from_messages',
        lambda messages: FakePrompt(),
    )
    monkeypatch.setattr(conversation_processing, 'get_llm', lambda feature, **kwargs: object())

    assert conversation_processing.should_discard_conversation('hello there', duration_seconds=15) is False


def test_action_items_gateway_shadow_keeps_legacy_result(monkeypatch):
    captured = {}

    class FakeParser:
        def __init__(self, pydantic_object):
            self.pydantic_object = pydantic_object

        def get_format_instructions(self):
            return 'return structured output'

    class FakePrompt:
        def __or__(self, other):
            return FakeChain()

    class FakeChain:
        def __or__(self, other):
            return self

        def invoke(self, values):
            assert 'submit report by Friday' in values['conversation_context']
            return conversation_processing.ActionItemsExtraction(action_items=[])

    def fake_gateway(prompt, output_model, *, feature):
        captured.update({'prompt': prompt, 'output_model': output_model, 'feature': feature})
        return output_model(action_items=[])

    monkeypatch.setattr(conversation_processing, 'PydanticOutputParser', FakeParser)
    monkeypatch.setattr(conversation_processing.ChatPromptTemplate, 'from_messages', lambda messages: FakePrompt())
    monkeypatch.setattr(conversation_processing, 'get_llm', lambda feature, **kwargs: object())
    monkeypatch.setattr(conversation_processing, 'invoke_chat_structured_gateway', fake_gateway)

    result = conversation_processing.extract_action_items(
        'submit report by Friday',
        datetime(2026, 6, 28, tzinfo=timezone.utc),
        'en',
        'UTC',
    )

    assert result == []
    assert captured['output_model'] is conversation_processing.ActionItemsExtraction
    assert captured['feature'] == 'conversation_action_items.extract.shadow'
    assert 'submit report by Friday' in captured['prompt']


def test_conversation_structure_gateway_shadow_keeps_legacy_result_and_records_comparison(monkeypatch):
    captured = {}
    counter = FakeCounter()
    call_order = []

    class LegacyParser:
        @staticmethod
        def get_format_instructions():
            return 'return legacy structure'

    class FakeParser:
        def __init__(self, pydantic_object):
            self.pydantic_object = pydantic_object

        def get_format_instructions(self):
            return 'return shadow structure'

    class FakePrompt:
        def __or__(self, other):
            return FakeChain()

    class FakeChain:
        def __or__(self, other):
            return self

        def invoke(self, values):
            assert values['format_instructions'] == 'return legacy structure'
            call_order.append('legacy')
            return Structured(
                title='Weekly Planning',
                overview='Discussed project launch tasks.',
                emoji='📋',
                category=CategoryEnum.work,
            )

    def fake_gateway(prompt, output_model, *, feature):
        call_order.append('gateway')
        captured.update({'prompt': prompt, 'output_model': output_model, 'feature': feature})
        return output_model(
            title='Weekly Plan',
            overview='Discussed launch tasks for the project.',
            emoji='📋',
            category=CategoryEnum.work,
        )

    class ImmediateFuture:
        def result(self):
            return None

        def add_done_callback(self, callback):
            callback(self)

    def immediate_submit(_executor, fn, *args, **kwargs):
        fn(*args, **kwargs)
        return ImmediateFuture()

    monkeypatch.setenv(conversation_processing.CONVERSATION_STRUCTURE_SHADOW_ENABLED_ENV, 'true')
    monkeypatch.setenv(conversation_processing.CONVERSATION_STRUCTURE_SHADOW_SAMPLE_RATE_ENV, '1.0')
    monkeypatch.setattr(conversation_processing, 'parser', LegacyParser())
    monkeypatch.setattr(conversation_processing, 'PydanticOutputParser', FakeParser)
    monkeypatch.setattr(conversation_processing.ChatPromptTemplate, 'from_messages', lambda messages: FakePrompt())
    monkeypatch.setattr(conversation_processing, 'get_llm', lambda feature, **kwargs: object())
    monkeypatch.setattr(conversation_processing, 'invoke_chat_structured_gateway', fake_gateway)
    monkeypatch.setattr(conversation_processing, 'submit_with_context', immediate_submit)
    monkeypatch.setattr(conversation_processing, 'LLM_GATEWAY_CHAT_EXTRACTION_COMPARISONS', counter)

    result = conversation_processing.get_transcript_structure(
        'we discussed project launch tasks',
        datetime(2026, 6, 28, tzinfo=timezone.utc),
        'en',
        'UTC',
        'uid',
    )

    assert result.title == 'Weekly Planning'
    assert result.overview == 'Discussed project launch tasks.'
    assert call_order == ['legacy', 'gateway']
    assert captured['output_model'] is ConversationStructureExtraction
    assert captured['feature'] == 'conversation_structure.extract.shadow'
    assert 'return shadow structure' in captured['prompt']
    comparison_labels = [labels for labels, _amount in counter.calls]
    assert {
        'feature': 'conversation_structure.extract.shadow',
        'field': 'category',
        'outcome': 'exact_match',
    } in comparison_labels
    assert {
        'feature': 'conversation_structure.extract.shadow',
        'field': 'emoji',
        'outcome': 'exact_match',
    } in comparison_labels
    assert any(labels['field'] == 'title_similarity' for labels in comparison_labels)
    assert any(labels['field'] == 'overview_similarity' for labels in comparison_labels)


def test_conversation_structure_shadow_disabled_skips_gateway(monkeypatch):
    captured = {'gateway_called': False, 'submitted': False}
    counter = FakeCounter()

    class LegacyParser:
        @staticmethod
        def get_format_instructions():
            return 'return legacy structure'

    class FakePrompt:
        def __or__(self, other):
            return FakeChain()

    class FakeChain:
        def __or__(self, other):
            return self

        def invoke(self, values):
            return Structured(title='Legacy Title', overview='Legacy Overview', category=CategoryEnum.work)

    def fake_gateway(*args, **kwargs):
        captured['gateway_called'] = True
        return None

    def fake_submit(*args, **kwargs):
        captured['submitted'] = True

    monkeypatch.delenv(conversation_processing.CONVERSATION_STRUCTURE_SHADOW_ENABLED_ENV, raising=False)
    monkeypatch.setattr(conversation_processing, 'parser', LegacyParser())
    monkeypatch.setattr(conversation_processing.ChatPromptTemplate, 'from_messages', lambda messages: FakePrompt())
    monkeypatch.setattr(conversation_processing, 'get_llm', lambda feature, **kwargs: object())
    monkeypatch.setattr(conversation_processing, 'invoke_chat_structured_gateway', fake_gateway)
    monkeypatch.setattr(conversation_processing, 'submit_with_context', fake_submit)
    monkeypatch.setattr(gateway_client, 'LLM_GATEWAY_CHAT_EXTRACTION_REQUESTS', counter)

    result = conversation_processing.get_transcript_structure(
        'we discussed project launch tasks',
        datetime(2026, 6, 28, tzinfo=timezone.utc),
        'en',
        'UTC',
        'uid',
    )

    assert result.title == 'Legacy Title'
    assert captured == {'gateway_called': False, 'submitted': False}
    assert (
        {
            'feature': 'conversation_structure.extract.shadow',
            'outcome': 'skipped',
            'reason': 'disabled',
        },
        1,
    ) in counter.calls
