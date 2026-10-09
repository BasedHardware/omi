"""Tests for OpenAI prompt caching support in conversation processing (issue #4654).

Verifies prompt-cache retention and static system-message behavior on live routes.
"""

import inspect
import re

from utils.llm.model_config import LUNA_MODEL
from utils.llm.conversation_processing import (
    _gpt56_cacheable_system_message,
)


class TestPromptCacheRetention:
    """Tests for 24h prompt cache retention and routing keys (PR #4674)."""

    @staticmethod
    def _read_clients_source():
        from pathlib import Path

        clients_path = Path(__file__).resolve().parent.parent.parent / "utils" / "llm" / "clients.py"
        return clients_path.read_text(encoding="utf-8")

    @staticmethod
    def _import_model_config():
        """Import model_config.py in isolation (it has only stdlib deps)."""
        import importlib.util
        from pathlib import Path

        path = Path(__file__).resolve().parent.parent.parent / "utils" / "llm" / "model_config.py"
        spec = importlib.util.spec_from_file_location("_omi_model_config_test", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_qos_openai_llm_gates_retention_by_capability(self):
        """_get_or_create_openai_llm must gate prompt_cache_retention=24h via a capability check."""
        source = self._read_clients_source()
        match = re.search(
            r"_get_or_create_openai_llm.*?supports_cache_retention\(.*?prompt_cache_retention.*?24h",
            source,
            re.DOTALL,
        )
        assert match, "_get_or_create_openai_llm should gate prompt_cache_retention='24h' by supports_cache_retention()"

    def test_capability_gating_matrix(self):
        """Capability gating (not exact names): renamed gpt-5 still cached, non-capable models untouched."""
        mc = self._import_model_config()
        # A renamed/future gpt-5 family model must still get routing + retention.
        assert mc.supports_prompt_cache("gpt-5.9-turbo"), "renamed gpt-5 should support prompt_cache_key"
        assert mc.supports_cache_retention("gpt-5.9-turbo"), "renamed gpt-5 should support 24h retention"
        assert mc.supports_prompt_cache(LUNA_MODEL)
        assert not mc.supports_cache_retention(LUNA_MODEL), "gpt-x-luna uses explicit cache options"
        assert mc.supports_prompt_cache("gpt-5.6-sol")
        assert not mc.supports_cache_retention("gpt-5.6-sol"), "GPT-5.6 uses explicit 30m cache options"
        # Retired product models are no longer treated as active cache targets.
        assert not mc.supports_prompt_cache("gpt-4.1-mini")
        assert not mc.supports_cache_retention("gpt-4.1-mini")
        # Non-OpenAI models get neither.
        assert not mc.supports_prompt_cache("gemini-2.5-flash-lite")
        assert not mc.supports_cache_retention("gemini-2.5-flash-lite")

    def test_explicit_cache_and_chat_sanitizer_predicate(self):
        """One helper covers the GPT-5.6 wire contract and the canonical Luna id."""
        mc = self._import_model_config()
        assert mc.uses_explicit_cache_and_chat_sanitizer(mc.LUNA_MODEL)
        assert mc.uses_explicit_cache_and_chat_sanitizer("gpt-5.6-sol")
        assert mc.uses_explicit_cache_and_chat_sanitizer("gpt-5.6-terra")
        assert not mc.uses_explicit_cache_and_chat_sanitizer("gpt-5-nano")
        assert not mc.uses_explicit_cache_and_chat_sanitizer("gpt-4o")
        assert not mc.uses_explicit_cache_and_chat_sanitizer("")
        assert not mc.supports_cache_retention(mc.LUNA_MODEL)
        assert not mc.supports_cache_retention("gpt-5.6-terra")

        from pathlib import Path

        backend = Path(__file__).resolve().parent.parent.parent
        sites = {
            "utils/llm/clients.py": 1,
            "utils/llm/model_config.py": 2,
            "utils/llm/conversation_prompt_prefix.py": 1,
            "utils/llm/proactive_notification.py": 1,
            "llm_gateway/gateway/executor.py": 2,
        }
        for rel, minimum in sites.items():
            text = (backend / rel).read_text(encoding="utf-8")
            assert text.count("uses_explicit_cache_and_chat_sanitizer") >= minimum, rel

    def test_cache_retention_not_in_model_kwargs(self):
        """prompt_cache_retention must NOT be in model_kwargs (SDK rejects it there)."""
        source = self._read_clients_source()
        mk_blocks = re.findall(r'model_kwargs\s*=\s*\{[^}]*\}', source)
        for block in mk_blocks:
            assert 'prompt_cache_retention' not in block, f"prompt_cache_retention must not be in model_kwargs: {block}"


def test_explicit_cache_system_message_preserves_parser_schema_braces():
    """A cached system message must bypass ChatPromptTemplate variable parsing."""
    from langchain_core.prompts import ChatPromptTemplate

    system_message = _gpt56_cacheable_system_message('{"title": "string"}', cache_enabled=True, formatted=True)
    prompt = ChatPromptTemplate.from_messages([system_message, ('system', 'Content: {conversation_context}')])

    messages = prompt.format_messages(conversation_context='Transcript: hello')

    assert messages[0].content == [
        {
            'type': 'text',
            'text': '{"title": "string"}',
            'prompt_cache_breakpoint': {'mode': 'explicit'},
        }
    ]


def test_gateway_formatted_instructions_without_explicit_cache_stay_a_concrete_message():
    """The explicit-cache kill switch must not degrade pre-formatted instructions to a tuple template.

    Gateway mode pre-formats the parser schema (with literal JSON braces) into
    instructions_text. If that text were passed as a ('system', ...) template
    tuple, ChatPromptTemplate would parse the braces as variables and fail
    before the LLM call — the cache-off rollback path would be broken.
    """
    from langchain_core.prompts import ChatPromptTemplate

    message = _gpt56_cacheable_system_message('Schema: {"title": "string"}', cache_enabled=False, formatted=True)

    assert not isinstance(message, tuple), 'formatted instructions must be a concrete message'
    assert message.content == [
        {'type': 'text', 'text': 'Schema: {"title": "string"}'}
    ], 'no breakpoint: explicit-cache disabled must not request a cache write'

    prompt = ChatPromptTemplate.from_messages([message, ('system', 'Content: {conversation_context}')])
    rendered = prompt.format_messages(conversation_context='Transcript: hello')
    assert rendered[0].content[0]['text'] == 'Schema: {"title": "string"}'
