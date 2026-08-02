import os
from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault('ENCRYPTION_SECRET', '0123456789abcdef0123456789abcdef')
os.environ.setdefault('OPENAI_API_KEY', 'sk-test-fake-for-unit-tests')
os.environ.setdefault('TYPESENSE_API_KEY', 'test-typesense-key')
os.environ.setdefault('TYPESENSE_HOST', 'localhost')
os.environ.setdefault('TYPESENSE_HOST_PORT', '8108')
os.environ.setdefault('TYPESENSE_PROTOCOL', 'http')

import utils.retrieval.agentic as agentic  # noqa: E402


async def test_openai_provider_builds_and_runs_openai_agent():
    invoked = {}
    fake_agent = object()
    fake_model = object()

    def fake_create_react_agent(*, model, tools):
        invoked['model'] = model
        invoked['tools'] = tools
        return fake_agent

    async def fake_openai_stream(agent, messages, callback, full_response, safety_guard, configurable):
        invoked['agent'] = agent
        invoked['messages'] = messages
        await callback.end()

    with ExitStack() as stack:
        stack.enter_context(patch.object(agentic, 'CHAT_PROVIDER', 'openai'))
        stack.enter_context(patch.object(agentic, 'create_react_agent', fake_create_react_agent))
        stack.enter_context(patch.object(agentic, 'get_llm', return_value=fake_model))
        stack.enter_context(patch.object(agentic, 'get_user_timezone', lambda _uid: 'UTC'))
        stack.enter_context(patch.object(agentic, '_get_agentic_qa_prompt', lambda *_args, **_kwargs: 'SYSTEM'))
        stack.enter_context(patch.object(agentic, 'load_app_tools', lambda _uid: []))
        stack.enter_context(
            patch.object(agentic, 'get_current_datetime_block', lambda _uid, tz=None, location=None: 'NOW')
        )
        stack.enter_context(patch.object(agentic, '_run_openai_agent_stream', fake_openai_stream))

        chunks = [
            chunk
            async for chunk in agentic.execute_agentic_chat_stream(
                'uid-123', [SimpleNamespace(sender='human', text='hello')], callback_data={}
            )
        ]

    assert chunks == [None]
    assert invoked['agent'] is fake_agent
    assert invoked['model'] is fake_model
    assert invoked['tools'] == list(agentic.CORE_TOOLS)
    assert invoked['messages'][0].content == 'SYSTEM\n\nNOW'
    assert invoked['messages'][1].content == 'hello'


def test_chunk_text_handles_string_and_content_parts():
    assert agentic._chunk_text('hello') == 'hello'
    assert agentic._chunk_text(None) == ''
    assert agentic._chunk_text(['a', 'b']) == 'ab'
    assert agentic._chunk_text([{'type': 'text', 'text': 'hi '}, {'type': 'tool_use'}]) == 'hi '


def test_tool_input_coercion_preserves_non_dict_payload():
    assert agentic._coerce_tool_input_to_params(None) == {}
    assert agentic._coerce_tool_input_to_params({'query': 'x'}) == {'query': 'x'}
    assert agentic._coerce_tool_input_to_params('raw') == {'input': 'raw'}
