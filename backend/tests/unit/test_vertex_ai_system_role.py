"""
Regression test: LLM call sites must use LangChain message objects, not raw dicts.

Vertex AI rejects "system" role in contents array. LangChain SystemMessage/HumanMessage
auto-convert to the correct Gemini format (systemInstruction field). Raw dicts bypass
this conversion and cause HTTP 400 errors.

See: issue #7085, PR #7084
"""

import os
import sys
from unittest.mock import MagicMock, patch

import pytest
from langchain_core.messages import SystemMessage, HumanMessage

# ---------------------------------------------------------------------------
# Pre-mock heavy deps before any imports touch them (same pattern as test_omi_qos_tiers.py)
# ---------------------------------------------------------------------------
_HEAVY_MOCKS = {
    'firebase_admin': MagicMock(),
    'firebase_admin.auth': MagicMock(),
    'firebase_admin.firestore': MagicMock(),
    'firebase_admin.messaging': MagicMock(),
    'firebase_admin.storage': MagicMock(),
    'google.cloud.firestore': MagicMock(),
    'google.cloud.firestore_v1': MagicMock(),
    'google.cloud.firestore_v1.base_query': MagicMock(),
    'google.cloud.storage': MagicMock(),
    'database': MagicMock(),
    'database._client': MagicMock(),
    'database.llm_usage': MagicMock(),
    'database.redis_db': MagicMock(),
    'database.vector_db': MagicMock(),
}

for _mod, _mock in _HEAVY_MOCKS.items():
    sys.modules.setdefault(_mod, _mock)

os.environ.setdefault('OPENAI_API_KEY', 'sk-test-fake-key-for-unit-tests')
os.environ.setdefault('ANTHROPIC_API_KEY', 'sk-ant-test-fake-key')


class _CaptureInvoke:
    """Mock LLM that captures the messages passed to invoke/ainvoke."""

    def __init__(self, content='[]'):
        self.captured_messages = None
        self.content = content

    def invoke(self, messages, *args, **kwargs):
        self.captured_messages = messages
        resp = MagicMock()
        resp.content = self.content
        return resp

    async def ainvoke(self, messages, *args, **kwargs):
        self.captured_messages = messages
        resp = MagicMock()
        resp.content = self.content
        return resp


def _assert_langchain_messages(messages):
    """Assert messages are LangChain objects, not raw dicts."""
    assert isinstance(messages, list), f"Expected list, got {type(messages)}"
    assert len(messages) >= 2, f"Expected at least 2 messages, got {len(messages)}"
    for msg in messages:
        assert not isinstance(msg, dict), (
            f"Raw dict message found: {msg}. " "Must use SystemMessage/HumanMessage for Vertex AI compatibility."
        )
    assert isinstance(messages[0], SystemMessage), f"First message should be SystemMessage, got {type(messages[0])}"
    assert isinstance(messages[1], HumanMessage), f"Second message should be HumanMessage, got {type(messages[1])}"


@pytest.mark.asyncio
async def test_generate_app_from_prompt_uses_langchain_messages():
    """app_generator.generate_app_from_prompt must pass SystemMessage/HumanMessage."""
    from utils.llm.app_generator import generate_app_from_prompt

    capture = _CaptureInvoke(
        '{"name": "Test", "description": "A test app", "category": "other", '
        '"capabilities": ["chat"], "chat_prompt": "Be helpful"}'
    )

    with patch('utils.llm.app_generator.get_llm', return_value=capture):
        await generate_app_from_prompt("Make a test app")

    _assert_langchain_messages(capture.captured_messages)


def test_generate_description_and_emoji_uses_langchain_messages():
    """app_generator.generate_description_and_emoji must pass SystemMessage/HumanMessage."""
    from utils.llm.app_generator import generate_description_and_emoji

    capture = _CaptureInvoke('{"description": "A great app", "emoji": "🎯"}')

    with patch('utils.llm.app_generator.get_llm', return_value=capture):
        generate_description_and_emoji("TestApp", "do something cool")

    _assert_langchain_messages(capture.captured_messages)


def test_apps_router_uses_langchain_messages_not_raw_dicts():
    """apps.py generate_sample_prompts_endpoint must use SystemMessage/HumanMessage, not raw dicts.

    Since routers/apps.py has heavy import dependencies that can't be easily mocked,
    we verify the source code directly — the ainvoke call must use SystemMessage/HumanMessage
    and must NOT contain raw dict patterns like {"role": "system"}.
    """
    import ast
    import pathlib

    apps_path = pathlib.Path(__file__).resolve().parents[2] / 'routers' / 'apps.py'
    source = apps_path.read_text()

    # Find the generate_sample_prompts_endpoint function
    tree = ast.parse(source)
    found_endpoint = False
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == 'generate_sample_prompts_endpoint':
            found_endpoint = True
            # Get the source lines for this function
            func_source = ast.get_source_segment(source, node)
            assert func_source is not None, "Could not extract function source"

            # Must NOT contain raw dict message patterns
            assert '{"role": "system"' not in func_source, (
                "generate_sample_prompts_endpoint still uses raw dict {'role': 'system'}. "
                "Must use SystemMessage() for Vertex AI compatibility."
            )
            assert "{'role': 'system'" not in func_source, (
                "generate_sample_prompts_endpoint still uses raw dict {'role': 'system'}. "
                "Must use SystemMessage() for Vertex AI compatibility."
            )

            # Must contain LangChain message objects
            assert (
                'SystemMessage(' in func_source
            ), "generate_sample_prompts_endpoint must use SystemMessage() from langchain_core.messages"
            assert (
                'HumanMessage(' in func_source
            ), "generate_sample_prompts_endpoint must use HumanMessage() from langchain_core.messages"
            break

    assert found_endpoint, "generate_sample_prompts_endpoint not found in routers/apps.py"
