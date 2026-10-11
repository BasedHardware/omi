from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import yaml

from utils import byok
from utils.llm import chat, gateway_client, gateway_observability
from utils.llm import conversation_processing
from models.conversation_enums import CategoryEnum
from models.structured import Structured
from models.structured_extraction import ActionItemsExtraction, ConversationStructureExtraction

GATEWAY_FEATURE_MODELS = {
    'chat_extraction.requires_context': chat.RequiresContext,
    'conversation_structure.extract.shadow': ConversationStructureExtraction,
    'conversation_action_items.extract.shadow': ActionItemsExtraction,
}


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


class ErrorGatewayResponse:
    def __init__(self, status_code):
        self.status_code = status_code

    def raise_for_status(self):
        request = gateway_client.httpx.Request('POST', 'http://gateway.test/v1/chat/completions')
        response = gateway_client.httpx.Response(self.status_code, request=request)
        raise gateway_client.httpx.HTTPStatusError('gateway request failed', request=request, response=response)


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
_UNEXPECTED_STRUCTURE_RESPONSE = FakeGatewayResponse({'choices': [{'message': {'content': '{"answer": "ok"}'}}]})


def test_requires_context_uses_legacy_llm_provider(monkeypatch):
    existing_calls = []
    monkeypatch.setattr(chat, 'get_llm', lambda feature: FakeLLM(chat.RequiresContext(value=True), existing_calls))

    assert chat.requires_context('what did I discuss yesterday?') is True
    assert existing_calls == [chat.RequiresContext]


def test_requires_context_byok_context_uses_same_legacy_llm_provider(monkeypatch):
    byok.set_byok_keys({'openai': 'secret'})
    existing_calls = []
    monkeypatch.setattr(chat, 'get_llm', lambda feature: FakeLLM(chat.RequiresContext(value=True), existing_calls))

    assert chat.requires_context('what did I discuss yesterday?') is True
    assert existing_calls == [chat.RequiresContext]


def test_gateway_validation_rejects_conversation_structure_defaults_masking_missing_fields(monkeypatch):
    counter = FakeCounter()
    monkeypatch.setattr(gateway_observability, 'LLM_GATEWAY_CHAT_EXTRACTION_REQUESTS', counter)
    _mock_gateway_client(monkeypatch, lambda *args, **kwargs: _UNEXPECTED_STRUCTURE_RESPONSE)

    result = gateway_client.invoke_chat_structured_gateway(
        'extract structure',
        ConversationStructureExtraction,
        feature='conversation_structure.extract.shadow',
    )

    assert result is None
    assert counter.calls == [
        (
            {
                'feature': 'conversation_structure.extract.shadow',
                'mode': 'fallback',
                'outcome': 'fallback',
                'reason': 'schema_validation',
            },
            1,
        )
    ]


def test_chat_structured_gateway_request_uses_auto_lane_and_service_auth(monkeypatch):
    monkeypatch.setenv('OMI_LLM_GATEWAY_URL', 'http://gateway.test/')
    monkeypatch.setenv('OMI_LLM_GATEWAY_SERVICE_TOKEN', 'service-token')
    captured = {'client_kwargs': None}

    def fake_client(*args, **kwargs):
        captured['client_kwargs'] = kwargs
        return FakeGatewayClient(fake_post)

    def fake_post(url, *, headers=None, json=None, **kwargs):
        captured.update({'url': url, 'headers': headers, 'json': json})
        return _VALUE_TRUE_RESPONSE

    monkeypatch.setattr(gateway_client.httpx, 'Client', fake_client)

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
    timeout = captured['client_kwargs']['timeout']
    assert timeout.connect == 3.0
    assert timeout.pool == 3.0
    assert timeout.read == gateway_client.CHAT_EXTRACTION_TIMEOUT_SECONDS
    assert timeout.write == gateway_client.CHAT_EXTRACTION_TIMEOUT_SECONDS


def test_chat_structured_gateway_allows_background_timeout_override(monkeypatch):
    captured = {}

    def fake_client(*args, **kwargs):
        captured['client_kwargs'] = kwargs
        return FakeGatewayClient(lambda *args, **kwargs: _VALUE_TRUE_RESPONSE)

    monkeypatch.setattr(gateway_client.httpx, 'Client', fake_client)

    result = gateway_client.invoke_chat_structured_gateway(
        'classified prompt',
        chat.RequiresContext,
        feature='chat_extraction.requires_context',
        timeout_seconds=gateway_client.BACKGROUND_CHAT_EXTRACTION_TIMEOUT_SECONDS,
    )

    assert result == chat.RequiresContext(value=True)
    timeout = captured['client_kwargs']['timeout']
    assert timeout.connect == 3.0
    assert timeout.pool == 3.0
    assert timeout.read == 15.0
    assert timeout.write == 15.0


def test_strict_schema_normalizes_action_item_extraction_for_openai():
    schema = gateway_client._strict_model_json_schema(ActionItemsExtraction)

    assert schema['additionalProperties'] is False
    assert schema['required'] == ['action_items']

    action_item_schema = schema['$defs']['ExtractedActionItem']
    assert action_item_schema['additionalProperties'] is False
    assert action_item_schema['required'] == [
        'description',
        'due_at',
        'capture_kind',
        'capture_confidence',
        'ownership_confidence',
        'capture_owner',
        'owner_name',
        'context',
        'due_certainty',
        'concrete_deliverable',
        'candidate_action',
        'target_task_id',
        'source_segment_ids',
    ]
    assert 'default' not in action_item_schema['properties']['due_at']
    assert {'type': 'null'} in action_item_schema['properties']['due_at']['anyOf']


def test_strict_schema_keeps_conversation_structure_shadow_contract_narrow():
    schema = gateway_client._strict_model_json_schema(ConversationStructureExtraction)

    assert schema['additionalProperties'] is False
    assert schema['required'] == ['title', 'overview', 'emoji', 'category']
    assert set(schema['properties']) == {'title', 'overview', 'emoji', 'category'}
    assert 'action_items' not in schema['properties']
    assert 'events' not in schema['properties']
    assert '$ref' not in schema['properties']['category']
    assert schema['properties']['category']['type'] == 'string'
    assert 'enum' in schema['properties']['category']


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


@pytest.mark.parametrize(('feature', 'output_model'), sorted(GATEWAY_FEATURE_MODELS.items()))
def test_gateway_feature_payloads_use_openai_strict_schema_subset(feature, output_model):
    payload = gateway_client._chat_structured_payload('fixture prompt', output_model, feature=feature)
    schema = payload['response_format']['json_schema']['schema']

    assert payload['model'] == 'omi:auto:chat-structured'
    assert payload['response_format']['json_schema']['strict'] is True
    assert payload['metadata']['omi_feature'] == feature
    _assert_openai_strict_schema_subset(schema)


def test_feature_bundles_have_gateway_payload_contract_coverage():
    config_path = Path(__file__).resolve().parents[2] / 'llm_gateway' / 'config' / 'feature_bundles.yaml'
    configured = {bundle['feature'] for bundle in yaml.safe_load(config_path.read_text())['feature_bundles']}

    assert configured <= set(GATEWAY_FEATURE_MODELS) | {'public_shared_conversation_chat'}
    assert configured - set(GATEWAY_FEATURE_MODELS) == {'public_shared_conversation_chat'}


def _assert_openai_strict_schema_subset(schema):
    unsupported_keys = {
        'allOf',
        'oneOf',
        'not',
        'if',
        'then',
        'else',
        'dependentRequired',
        'dependentSchemas',
        'patternProperties',
    }

    def walk(node, path='$'):
        if isinstance(node, dict):
            for key in unsupported_keys:
                assert key not in node, f'{path} contains unsupported strict schema key: {key}'
            if '$ref' in node:
                siblings = set(node) - {'$ref'}
                assert not siblings, f'{path} has $ref sibling keys: {sorted(siblings)}'
            if node.get('type') == 'object':
                assert node.get('additionalProperties') is False, f'{path} must set additionalProperties=false'
                properties = node.get('properties')
                if isinstance(properties, dict):
                    assert node.get('required') == list(properties.keys()), f'{path} must require every property'
            assert 'default' not in node, f'{path} must not contain default'
            for key, value in node.items():
                walk(value, f'{path}.{key}')
        elif isinstance(node, list):
            for index, value in enumerate(node):
                walk(value, f'{path}[{index}]')

    walk(schema)


def test_chat_structured_gateway_records_success_metric(monkeypatch, caplog):
    counter = FakeCounter()
    monkeypatch.setattr(gateway_observability, 'LLM_GATEWAY_CHAT_EXTRACTION_REQUESTS', counter)
    _mock_gateway_client(monkeypatch, lambda *args, **kwargs: _VALUE_TRUE_RESPONSE)

    with caplog.at_level(logging.INFO, logger='utils.llm.gateway_observability'):
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
                'mode': 'serving',
                'outcome': 'success',
                'reason': 'ok',
            },
            1,
        )
    ]
    assert 'llm_gateway_backend_event kind=request_result' in caplog.text
    assert 'feature=chat_extraction.requires_context' in caplog.text
    assert 'outcome=success' in caplog.text
    assert 'reason=ok' in caplog.text
    assert 'classified prompt' not in caplog.text


def test_chat_structured_gateway_records_fallback_reason_metric(monkeypatch):
    counter = FakeCounter()
    monkeypatch.setattr(gateway_observability, 'LLM_GATEWAY_CHAT_EXTRACTION_REQUESTS', counter)
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
                'mode': 'fallback',
                'outcome': 'fallback',
                'reason': 'schema_validation',
            },
            1,
        )
    ]


def test_chat_structured_gateway_propagates_configuration_http_errors(monkeypatch):
    counter = FakeCounter()
    monkeypatch.setattr(gateway_observability, 'LLM_GATEWAY_CHAT_EXTRACTION_REQUESTS', counter)
    _mock_gateway_client(monkeypatch, lambda *args, **kwargs: ErrorGatewayResponse(503))

    with pytest.raises(gateway_client.httpx.HTTPStatusError):
        gateway_client.invoke_chat_structured_gateway(
            'classified prompt',
            chat.RequiresContext,
            feature='chat_extraction.requires_context',
        )

    assert counter.calls == [
        (
            {
                'feature': 'chat_extraction.requires_context',
                'mode': 'error',
                'outcome': 'error',
                'reason': 'http_503',
            },
            1,
        )
    ]


def test_chat_structured_gateway_falls_back_on_hard_proxy_http_errors(monkeypatch):
    _mock_gateway_client(monkeypatch, lambda *args, **kwargs: ErrorGatewayResponse(502))

    result = gateway_client.invoke_chat_structured_gateway(
        'classified prompt',
        chat.RequiresContext,
        feature='chat_extraction.requires_context',
    )

    assert result is None


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


def test_conversation_discard_uses_legacy_llm_provider(monkeypatch):
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
            return conversation_processing.DiscardConversation(discard=True)

    legacy_features = []
    monkeypatch.setattr(conversation_processing, 'PydanticOutputParser', FakeParser)
    monkeypatch.setattr(conversation_processing.ChatPromptTemplate, 'from_messages', lambda messages: FakePrompt())
    monkeypatch.setattr(
        conversation_processing, 'get_llm', lambda feature, **kwargs: legacy_features.append(feature) or object()
    )

    assert conversation_processing.should_discard_conversation('hello there', duration_seconds=15) is True
    assert legacy_features == ['conv_discard']


def test_conversation_discard_byok_uses_same_legacy_llm_provider(monkeypatch):
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
    monkeypatch.setattr(conversation_processing, 'PydanticOutputParser', FakeParser)
    monkeypatch.setattr(conversation_processing.ChatPromptTemplate, 'from_messages', lambda messages: FakePrompt())
    monkeypatch.setattr(conversation_processing, 'get_llm', lambda feature, **kwargs: object())

    assert conversation_processing.should_discard_conversation('hello there', duration_seconds=15) is False
