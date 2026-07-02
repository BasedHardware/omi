from __future__ import annotations

from utils.llm import providers
from utils.llm.gateway_client import DEFAULT_LLM_GATEWAY_URL, get_llm_gateway_base_url
from utils.llm.clients import get_llm_gateway_chat_structured


def test_llm_gateway_base_url_defaults_to_local_service(monkeypatch):
    monkeypatch.delenv('OMI_LLM_GATEWAY_URL', raising=False)

    assert get_llm_gateway_base_url() == DEFAULT_LLM_GATEWAY_URL


def test_llm_gateway_base_url_uses_repo_local_env_config(monkeypatch):
    monkeypatch.setenv('OMI_LLM_GATEWAY_URL', ' http://llm-gateway.internal:8080/ ')

    assert get_llm_gateway_base_url() == 'http://llm-gateway.internal:8080'


def test_gateway_langchain_client_uses_internal_gateway_base_url_and_auth(monkeypatch):
    captured = {}

    class FakeChatOpenAI:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setenv('OMI_LLM_GATEWAY_URL', 'http://gateway.internal:8080/')
    monkeypatch.setenv('OMI_LLM_GATEWAY_SERVICE_TOKEN', 'service-token')
    monkeypatch.setattr(providers, 'ChatOpenAI', FakeChatOpenAI)
    providers._llm_cache.clear()

    result = get_llm_gateway_chat_structured()

    assert isinstance(result, FakeChatOpenAI)
    assert captured['model'] == 'omi:auto:chat-structured'
    assert captured['base_url'] == 'http://gateway.internal:8080/v1'
    assert captured['default_headers']['X-Omi-Service-Caller'] == 'backend'
    assert captured['default_headers']['Authorization'] == 'Bearer service-token'
