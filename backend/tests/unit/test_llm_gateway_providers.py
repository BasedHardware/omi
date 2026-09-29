import pytest
import os
import httpx
from llm_gateway.gateway.auth import ServiceCaller
from llm_gateway.gateway.providers import (
    fake_success_response,
    FakeProviderCall,
    _default_fake_response,
    parse_retry_after_seconds,
    _raise_for_status,
    _provider_rejection,
    _provider_error_message,
    _expose_provider_error_details,
    _parse_limited_json_response,
    _validate_chat_completion_response_shape,
    _configured_max_response_bytes,
    ProviderFailure,
    FailureClass,
    CredentialMode,
    ProviderRejection,
    FakeChatCompletionProvider,
)
from llm_gateway.gateway.schemas import ProviderRef
from llm_gateway.gateway.credentials import build_omi_managed_credential_context

def test_fake_success_response():
    ref = ProviderRef(provider='fake', model='fake-model')
    resp = fake_success_response(ref)
    assert resp['model'] == 'fake-model'
    assert resp['choices'][0]['message']['content'] == '{"answer":"ok"}'

    resp_custom = fake_success_response(ref, content="custom")
    assert resp_custom['choices'][0]['message']['content'] == "custom"

def test_default_fake_response():
    ref = ProviderRef(provider='fake', model='fake-model')
    resp = _default_fake_response(ref)
    assert resp['model'] == 'fake-model'

def test_parse_retry_after_seconds():
    assert parse_retry_after_seconds(None) is None
    assert parse_retry_after_seconds("abc") is None
    assert parse_retry_after_seconds(" 10 ") == 10.0
    assert parse_retry_after_seconds("1.5") is None

def test_raise_for_status():
    with pytest.raises(ProviderFailure) as exc:
        _raise_for_status(401, b"auth failed", credential_mode=CredentialMode.OMI_PAID)
    assert exc.value.failure_class == FailureClass.INVALID_CONFIG

    with pytest.raises(ProviderFailure) as exc:
        _raise_for_status(401, b"auth failed", credential_mode=CredentialMode.BYOK)
    assert exc.value.failure_class == FailureClass.BYOK_AUTH

    with pytest.raises(ProviderFailure) as exc:
        _raise_for_status(408, b"timeout")
    assert exc.value.failure_class == FailureClass.TIMEOUT_BEFORE_OUTPUT

    with pytest.raises(ProviderFailure) as exc:
        _raise_for_status(429, b"rate limit", credential_mode=CredentialMode.BYOK, retry_after_header="5")
    assert exc.value.failure_class == FailureClass.BYOK_RATE_LIMIT
    assert exc.value.retry_after_seconds == 5.0

    with pytest.raises(ProviderFailure) as exc:
        _raise_for_status(503, b"server error")
    assert exc.value.failure_class == FailureClass.PROVIDER_5XX_OMI_PAID

    # 400 without specific unsupported
    with pytest.raises(ProviderFailure) as exc:
        _raise_for_status(400, b'{"error": {"code": "invalid_request_error"}}')
    assert exc.value.failure_class == FailureClass.PROVIDER_INVALID_REQUEST

    # 400 with capability mismatch
    with pytest.raises(ProviderFailure) as exc:
        _raise_for_status(400, b'{"error": {"code": "unsupported_parameter", "param": "tools"}}')
    assert exc.value.failure_class == FailureClass.CAPABILITY_MISMATCH
    assert exc.value.provider_rejection == ProviderRejection.UNSUPPORTED_TOOLS

def test_provider_rejection():
    # Test valid JSON without mapping
    assert _provider_rejection(b'[]') == ProviderRejection.OTHER_4XX

    # Test invalid JSON
    assert _provider_rejection(b'invalid') == ProviderRejection.OTHER_4XX

    # Test context_length_exceeded
    assert _provider_rejection(b'{"error": {"code": "context_length_exceeded"}}') == ProviderRejection.CONTEXT_LENGTH_EXCEEDED

    # Test model_not_found
    assert _provider_rejection(b'{"error": {"code": "model_not_found"}}') == ProviderRejection.MODEL_NOT_FOUND

    # Test unsupported parameter
    assert _provider_rejection(b'{"error": {"code": "unsupported_parameter", "param": "tools"}}') == ProviderRejection.UNSUPPORTED_TOOLS
    assert _provider_rejection(b'{"error": {"code": "unsupported_parameter", "param": "unknown"}}') == ProviderRejection.UNSUPPORTED_OTHER

    # Test invalid parameter
    assert _provider_rejection(b'{"error": {"code": "invalid_parameter", "param": "temperature"}}') == ProviderRejection.INVALID_TEMPERATURE

    # Test invalid request error type
    assert _provider_rejection(b'{"error": {"type": "invalid_request_error"}}') == ProviderRejection.INVALID_REQUEST

def test_provider_error_message(monkeypatch):
    monkeypatch.setenv("LLM_GATEWAY_EXPOSE_PROVIDER_ERROR_DETAILS", "true")
    msg = _provider_error_message(400, b'some error')
    assert "status=400" in msg
    assert "some error" in msg

    monkeypatch.setenv("LLM_GATEWAY_EXPOSE_PROVIDER_ERROR_DETAILS", "false")
    msg2 = _provider_error_message(400, b'some error')
    assert msg2 == "provider request failed"

def test_parse_limited_json_response():
    assert _parse_limited_json_response(b'{"key": "value"}') == {"key": "value"}

    with pytest.raises(ProviderFailure) as exc:
        _parse_limited_json_response(b'invalid')
    assert exc.value.failure_class == FailureClass.PROVIDER_5XX_OMI_PAID

    with pytest.raises(ProviderFailure) as exc:
        _parse_limited_json_response(b'[]')
    assert exc.value.failure_class == FailureClass.PROVIDER_5XX_OMI_PAID

def test_validate_chat_completion_response_shape():
    _validate_chat_completion_response_shape({
        'object': 'chat.completion',
        'id': '123',
        'model': 'test-model',
        'choices': [
            {'message': {'role': 'assistant'}}
        ]
    })

    with pytest.raises(ProviderFailure):
        _validate_chat_completion_response_shape({'object': 'other'})

    with pytest.raises(ProviderFailure):
        _validate_chat_completion_response_shape({
            'object': 'chat.completion',
            'id': '',
            'model': 'test',
            'choices': [{'message': {'role': 'assistant'}}]
        })

    with pytest.raises(ProviderFailure):
        _validate_chat_completion_response_shape({
            'object': 'chat.completion',
            'id': '1',
            'model': '',
            'choices': [{'message': {'role': 'assistant'}}]
        })

    with pytest.raises(ProviderFailure):
        _validate_chat_completion_response_shape({
            'object': 'chat.completion',
            'id': '1',
            'model': 'test',
            'choices': []
        })

    with pytest.raises(ProviderFailure):
        _validate_chat_completion_response_shape({
            'object': 'chat.completion',
            'id': '1',
            'model': 'test',
            'choices': [{'message': {'role': 'user'}}]
        })

def test_configured_max_response_bytes(monkeypatch):
    monkeypatch.delenv("OPENAI_MAX_RESPONSE_BYTES", raising=False)
    # Default is 2 * 1024 * 1024
    assert _configured_max_response_bytes() == 2 * 1024 * 1024

    monkeypatch.setenv("OPENAI_MAX_RESPONSE_BYTES", "1000")
    assert _configured_max_response_bytes() == 1000

    monkeypatch.setenv("OPENAI_MAX_RESPONSE_BYTES", "-1")
    assert _configured_max_response_bytes() == 2 * 1024 * 1024

    monkeypatch.setenv("OPENAI_MAX_RESPONSE_BYTES", "invalid")
    with pytest.raises(ProviderFailure):
        _configured_max_response_bytes()

@pytest.mark.asyncio
async def test_fake_chat_completion_provider():
    provider = FakeChatCompletionProvider()
    assert len(provider.calls) == 0

    req = {'messages': []}
    ref = ProviderRef(provider='fake', model='test-model')
    cred = build_omi_managed_credential_context(ServiceCaller(name='test-service'))

    resp = await provider.create_chat_completion(
        req,
        provider_ref=ref,
        credentials=cred,
        timeout_ms=1000,
    )
    assert resp.response['model'] == 'test-model'
    assert len(provider.calls) == 1
    assert provider.calls[0].provider == 'fake'
    assert provider.calls[0].model == 'test-model'
    assert provider.calls[0].request == req
    assert provider.calls[0].timeout_ms == 1000

@pytest.mark.asyncio
async def test_fake_chat_completion_provider_with_outcomes():
    # Test success outcome
    outcomes = [{'id': 'test-1', 'object': 'chat.completion', 'model': 'm', 'choices': [{'message': {'role': 'assistant', 'content': 'hi'}, 'finish_reason': 'stop'}]}]
    provider = FakeChatCompletionProvider(outcomes=outcomes)

    req = {'messages': []}
    ref = ProviderRef(provider='fake', model='m')
    cred = build_omi_managed_credential_context(ServiceCaller(name='test-service'))

    resp = await provider.create_chat_completion(
        req,
        provider_ref=ref,
        credentials=cred,
        timeout_ms=1000,
    )
    assert resp.response['id'] == 'test-1'

    # Test failure outcome
    outcomes = [ProviderFailure(FailureClass.PROVIDER_5XX_OMI_PAID)]
    provider2 = FakeChatCompletionProvider(outcomes=outcomes)
    with pytest.raises(ProviderFailure) as exc:
        await provider2.create_chat_completion(
            req,
            provider_ref=ref,
            credentials=cred,
            timeout_ms=1000,
        )
    assert exc.value.failure_class == FailureClass.PROVIDER_5XX_OMI_PAID
