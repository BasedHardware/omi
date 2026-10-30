"""Exercise real feature factory and usage writer signatures after rebases, without IO."""

import asyncio
from unittest.mock import MagicMock

import pytest
from langchain_core.messages import AIMessageChunk
from langchain_core.outputs import Generation, LLMResult

from database import llm_usage
from utils.llm import clients, providers, usage_tracker
from utils.llm.gateway_client import GatewayContextChatOpenAI


@pytest.fixture
def gateway(monkeypatch):
    # Retain the real get_llm and gateway constructor. Only configuration/IO boundaries
    # are synthetic; a nonexistent get_llm keyword must fail this fixture's consumer.
    monkeypatch.setattr(clients, '_get_model_config', lambda feature: ('gpt-5.6', 'openai'))
    monkeypatch.setattr(clients, 'get_byok_profile', lambda: None)
    monkeypatch.setattr(clients, 'get_byok_key', lambda provider: None)
    monkeypatch.setattr(clients, 'should_route_company_paid_features_through_gateway', lambda: True)
    monkeypatch.setattr(providers, 'get_llm_gateway_base_url', lambda: 'http://127.0.0.1:1')
    monkeypatch.setattr(providers, 'get_llm_gateway_service_token', lambda: '')
    monkeypatch.setattr(providers, '_llm_cache', {})
    # Construct the SDK fixture during setup; no network operation is performed.
    model = clients.get_llm('chat_agent', streaming=True)
    assert isinstance(model, GatewayContextChatOpenAI)
    assert model.model_kwargs['stream_options'] == {'include_usage': True}
    from utils.retrieval import agentic, shaped_chat

    return model, agentic, shaped_chat


def test_real_feature_factory_runs_shaped_chat_and_requests_stream_usage(monkeypatch, gateway):
    _, agentic, shaped_chat = gateway

    assert agentic.get_llm is clients.get_llm
    seen = []

    async def stream(model, messages, config=None, **kwargs):
        assert model.streaming is True
        assert model.model_kwargs['stream_options'] == {'include_usage': True}
        seen.append(messages)
        yield AIMessageChunk(content='Actual factory answer')

    monkeypatch.setattr(GatewayContextChatOpenAI, 'astream', stream)

    async def run():
        output = []
        await shaped_chat.run_shaped_chat_stream(
            '',
            [{'role': 'user', 'content': 'Question'}],
            [],
            {},
            agentic.AsyncStreamingCallback(),
            output,
            agentic.AgentSafetyGuard(),
            {'user_id': 'synthetic-user'},
        )
        assert output == ['Actual factory answer'] and len(seen) == 1

    asyncio.run(run())


def test_singleton_callback_calls_actual_usage_writer_with_cache_keywords(monkeypatch):
    client = MagicMock()
    client.collection.return_value.document.return_value.get.return_value.to_dict.return_value = {
        'subscription': {'plan': 'operator'}
    }
    monkeypatch.setattr(llm_usage, 'db', client)
    monkeypatch.setattr(usage_tracker, '_callback_instance', None)
    callback = usage_tracker.get_usage_callback()
    assert callback._flush_fn is llm_usage.record_llm_usage
    token = usage_tracker.set_usage_context('synthetic-user', 'chat_agent', surface='telegram', turn_id='turn')
    try:
        callback.on_llm_end(
            LLMResult(
                generations=[[Generation(text='Answer')]],
                llm_output={
                    'token_usage': {
                        'model_name': 'gpt-5.6',
                        'prompt_tokens': 1200,
                        'completion_tokens': 40,
                        'prompt_tokens_details': {'cached_tokens': 800, 'cache_write_tokens': 100},
                    }
                },
            )
        )
    finally:
        usage_tracker.reset_usage_context(token)
    # A keyword TypeError or swallowed DB error cannot satisfy the real atomic write.
    client.batch.return_value.commit.assert_called_once()
    writes = client.batch.return_value.set.call_args_list
    assert len(writes) == 2
    daily, turn = (call.args[1] for call in writes)
    assert {'input_tokens', 'cache_read_tokens', 'cache_write_tokens'} <= daily['chat_agent']['gpt-5_6'].keys()
    assert daily['chat_agent_surfaces']['telegram']['gpt-5_6']['cache_read_tokens'] is not None
    assert turn['surface'] == 'telegram' and 'cache_write_tokens' in turn['models']['gpt-5_6']
