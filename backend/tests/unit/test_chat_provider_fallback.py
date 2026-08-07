import os
from types import SimpleNamespace

import pytest

os.environ.setdefault('ENCRYPTION_SECRET', '0123456789abcdef0123456789abcdef')
os.environ.setdefault('OPENAI_API_KEY', 'sk-test-fake-for-unit-tests')
os.environ.setdefault('TYPESENSE_API_KEY', 'test-typesense-key')
os.environ.setdefault('TYPESENSE_HOST', 'localhost')
os.environ.setdefault('TYPESENSE_HOST_PORT', '8108')
os.environ.setdefault('TYPESENSE_PROTOCOL', 'http')

import utils.retrieval.agentic as agentic  # noqa: E402


def test_configured_chat_provider_reads_current_environment(monkeypatch):
    monkeypatch.setenv(agentic.CHAT_PROVIDER_ENV_VAR, ' OPENAI ')
    assert agentic._configured_chat_provider() == 'openai'

    monkeypatch.setenv(agentic.CHAT_PROVIDER_ENV_VAR, 'unsupported')
    assert agentic._configured_chat_provider() == 'anthropic'


@pytest.mark.parametrize(
    ('provider', 'gateway_enabled', 'expected_model_feature'),
    [('openai', False, 'chat_graph'), ('anthropic', True, 'chat_agent')],
)
async def test_openai_compatible_modes_use_current_supervised_runner(
    monkeypatch, provider, gateway_enabled, expected_model_feature
):
    invoked = {}
    messages = [SimpleNamespace(sender='human', text='hello')]

    async def fake_run_blocking(_executor, function, *_args, **_kwargs):
        if function is agentic.get_user_timezone:
            return 'UTC'
        if function is agentic._get_agentic_qa_prompt:
            return 'SYSTEM'
        if function is agentic.load_app_tools:
            return []
        raise AssertionError(f'unexpected blocking function: {function}')

    async def fake_mobile_city(_uid, _platform):
        return None

    async def fake_openai_stream(
        system_prompt,
        provider_messages,
        tool_schemas,
        tool_registry,
        callback,
        full_response,
        safety_guard,
        configurable,
        *,
        model_feature='chat_agent',
    ):
        invoked.update(
            system_prompt=system_prompt,
            messages=provider_messages,
            tool_schemas=tool_schemas,
            tool_registry=tool_registry,
            model_feature=model_feature,
            configurable=configurable,
        )
        await callback.end()

    fake_tool = SimpleNamespace(name='core_tool')
    monkeypatch.setattr(agentic, 'CORE_TOOLS', (fake_tool,))
    monkeypatch.setattr(agentic, 'fit_within_budget', lambda value, *_args: (value, False))
    monkeypatch.setattr(agentic, '_configured_chat_provider', lambda: provider)
    monkeypatch.setattr(agentic, 'should_route_features_through_gateway', lambda: gateway_enabled)
    monkeypatch.setattr(agentic, 'get_byok_key', lambda _provider: None)
    monkeypatch.setattr(agentic, 'run_blocking', fake_run_blocking)
    monkeypatch.setattr(agentic, 'get_mobile_city', fake_mobile_city)
    monkeypatch.setattr(agentic, 'get_current_datetime_block', lambda *_args, **_kwargs: 'NOW')
    monkeypatch.setattr(agentic, '_convert_tools', lambda *_args: ([{'name': 'core_tool'}], {'core_tool': fake_tool}))
    monkeypatch.setattr(agentic, '_convert_anthropic_tools_to_openai', lambda schemas: schemas)
    monkeypatch.setattr(agentic, '_langchain_tool_to_anthropic', lambda *_args, **_kwargs: {'name': 'web_search'})
    monkeypatch.setattr(agentic, '_run_openai_agent_stream', fake_openai_stream)

    callback_data = {}
    chunks = [
        chunk
        async for chunk in agentic.execute_agentic_chat_stream(
            'uid-123', messages, callback_data=callback_data, current_datetime_block='NOW'
        )
    ]

    assert chunks == [None]
    assert invoked['model_feature'] == expected_model_feature
    assert invoked['system_prompt'].startswith('SYSTEM')
    assert invoked['messages'][-1]['content'].startswith('NOW\n\n')
    assert invoked['configurable']['tools'] == [fake_tool]
    assert invoked['tool_schemas'][-1] == {'name': 'web_search'}
