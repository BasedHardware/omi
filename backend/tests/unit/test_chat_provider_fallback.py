import ast
import asyncio
import os
import sys
import types
import typing
from pathlib import Path
from unittest.mock import patch
from unittest.mock import MagicMock

os.environ.setdefault('OPENAI_API_KEY', 'sk-test-fake-for-unit-tests')
os.environ.setdefault('ANTHROPIC_API_KEY', 'ant-test-fake-for-unit-tests')
os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')

sys.modules.setdefault('database._client', MagicMock())
llm_usage_stub = types.ModuleType('database.llm_usage')
llm_usage_stub.record_llm_usage = MagicMock()
sys.modules.setdefault('database.llm_usage', llm_usage_stub)


def test_anthropic_proxy_constructs_default_client_lazily():
    from utils.llm.clients import _AnthropicClientProxy

    created = []

    def _fake_client(**kwargs):
        created.append(kwargs)
        return object()

    proxy = _AnthropicClientProxy()

    with patch('utils.llm.clients.get_byok_key', return_value=None), patch(
        'utils.llm.clients.anthropic.AsyncAnthropic', side_effect=_fake_client
    ):
        assert created == []
        proxy._resolve()

    assert created == [{'timeout': 120.0, 'max_retries': 1}]


def _load_chat_dispatcher(chat_provider, fake_openai_stream):
    """Load the real ``execute_agentic_chat_stream`` dispatcher in isolation.

    Importing ``utils.retrieval.agentic`` pulls in heavy LLM/agent dependencies,
    so instead we extract just the dispatcher function from the source and exec
    it in a controlled namespace. This still exercises the real provider-routing
    code path (unlike a source-substring assertion, it is immune to comments and
    fails if the dispatch is actually broken).
    """
    source = (Path(__file__).resolve().parents[2] / 'utils/retrieval/agentic.py').read_text()
    tree = ast.parse(source)
    func_node = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.AsyncFunctionDef) and node.name == 'execute_agentic_chat_stream'
    )
    namespace = {
        'CHAT_PROVIDER': chat_provider,
        '_execute_agentic_chat_stream_openai': fake_openai_stream,
        'List': typing.List,
        'Optional': typing.Optional,
        'AsyncGenerator': typing.AsyncGenerator,
        'Message': object,
        'App': object,
        'ChatSession': object,
        'PageContext': object,
    }
    exec(ast.get_source_segment(source, func_node), namespace)
    return namespace['execute_agentic_chat_stream']


def test_openai_provider_dispatches_to_openai_path():
    """Behavioral: with CHAT_PROVIDER='openai', execute_agentic_chat_stream must
    delegate to _execute_agentic_chat_stream_openai and stream its chunks."""
    invoked = {}

    async def fake_openai_stream(uid, messages, app=None, callback_data=None, chat_session=None, context=None):
        invoked['uid'] = uid
        yield 'data: openai-chunk'

    dispatcher = _load_chat_dispatcher('openai', fake_openai_stream)

    async def _collect():
        return [chunk async for chunk in dispatcher('uid-123', [], None)]

    chunks = asyncio.run(_collect())

    assert invoked.get('uid') == 'uid-123', 'OpenAI dispatch path was not invoked'
    assert chunks == ['data: openai-chunk']


def test_anthropic_provider_does_not_dispatch_to_openai_path():
    """The OpenAI entry point must be gated behind CHAT_PROVIDER: with the
    default 'anthropic' provider it must not be invoked."""
    invoked = {}

    async def fake_openai_stream(uid, messages, app=None, callback_data=None, chat_session=None, context=None):
        invoked['uid'] = uid
        yield 'data: openai-chunk'

    dispatcher = _load_chat_dispatcher('anthropic', fake_openai_stream)

    async def _collect():
        # The anthropic branch references module-level dependencies that are not
        # provided in this isolated namespace, so entering it (instead of the
        # openai branch) is expected to raise. We only assert the openai path
        # was never taken.
        try:
            async for _ in dispatcher('uid-456', [], None):
                pass
        except Exception:
            pass

    asyncio.run(_collect())

    assert 'uid' not in invoked, 'OpenAI path must not run for the anthropic provider'


def _load_agentic_function(name):
    """Extract a single pure function from agentic.py and exec it in isolation
    (avoids importing the module's heavy LLM/agent dependencies)."""
    source = (Path(__file__).resolve().parents[2] / 'utils/retrieval/agentic.py').read_text()
    tree = ast.parse(source)
    func_node = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == name
    )
    namespace = {'Any': typing.Any}
    exec(ast.get_source_segment(source, func_node), namespace)
    return namespace[name]


def test_chunk_text_handles_string_and_list_content():
    """The stream handler must not silently drop non-string chunk content
    (some providers emit content as a list of parts)."""
    chunk_text = _load_agentic_function('_chunk_text')

    assert chunk_text('hello') == 'hello'
    assert chunk_text(None) == ''
    assert chunk_text(42) == ''
    assert chunk_text(['a', 'b']) == 'ab'
    # List of content-part dicts: emit text parts, skip non-text blocks.
    assert chunk_text([{'type': 'text', 'text': 'hi '}, {'type': 'tool_use', 'name': 'x'}]) == 'hi '
    assert chunk_text([{'text': 'defaults-to-text'}]) == 'defaults-to-text'
