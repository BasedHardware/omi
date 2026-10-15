"""Execute chat search through hybrid success, failure, empty and JIT result paths."""

import contextvars
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import MagicMock

import pytest
from prometheus_client import REGISTRY

from testing.import_isolation import AutoMockModule, load_module_fresh, stub_modules
from utils.conversations.search import ConversationSearchUnavailableError
from utils.metrics import OMI_CHAT_SEARCH_TOOL_OUTCOMES_TOTAL as outcomes


@pytest.fixture
def tools():
    fakes = {
        name: AutoMockModule(name)
        for name in (
            'database.conversations',
            'database.notifications',
            'database.users',
            'database.vector_db',
            'utils.conversations.factory',
            'utils.conversations.render',
            'utils.retrieval.tools.conversation_jit',
        )
    }
    agentic = ModuleType('utils.retrieval.agentic')
    agentic.agent_config_context = contextvars.ContextVar('test-config', default=None)
    fakes['utils.retrieval.agentic'] = agentic
    decorator = ModuleType('langchain_core.tools')
    decorator.tool = lambda function: function
    fakes['langchain_core.tools'] = decorator
    with stub_modules(fakes):
        module = load_module_fresh(
            'utils.retrieval.tools.conversation_tools',
            Path(__file__).resolve().parents[2] / 'utils/retrieval/tools/conversation_tools.py',
        )
        module.is_jit_conversation_retrieval_enabled = MagicMock(return_value=False)
        module.keyword_search_conversation_ids = MagicMock(return_value=['keyword'])
        module.vector_db.index = object()
        module.vector_db.embeddings.embed_query.return_value = [0.1]
        module.vector_db.query_vectors.return_value = ['semantic']
        module.vector_db.search_transcript_chunks.return_value = []
        rows = [
            {'id': 'keyword', 'created_at': datetime(2026, 9, 1, tzinfo=timezone.utc)},
            {'id': 'semantic', 'created_at': datetime(2026, 8, 1, tzinfo=timezone.utc)},
        ]
        module.conversations_db.get_conversations_by_id.return_value = rows
        module.deserialize_conversation = lambda data: SimpleNamespace(id=data['id'], transcript_segments=[])
        module.conversations_to_string.return_value = 'conversation results'
        module.notification_db.get_user_time_zone.return_value = 'UTC'
        yield module


def invoke(tools):
    return tools.search_conversations_tool(
        'topic', include_transcript=False, config={'configurable': {'user_id': 'uid', 'conversations_collected': []}}
    )


def value(path, outcome):
    return outcomes.labels(path=path, outcome=outcome)._value.get()


def test_happy_path_unchanged_and_keyword_semantic_both_used(tools):
    before = value('keyword', 'ok')
    result = invoke(tools)
    assert result.startswith("Found 2 conversations semantically matching 'topic':\n\nconversation results")
    assert 'Keyword index temporarily unavailable' not in result
    tools.conversations_db.get_conversations_by_id.assert_called_once_with('uid', ['keyword', 'semantic'])
    assert value('keyword', 'ok') == before + 1


@pytest.mark.parametrize('error_type', [ConversationSearchUnavailableError, RuntimeError])
@pytest.mark.parametrize('empty,jit', [(False, False), (True, False), (False, True)])
def test_keyword_failure_is_visible_in_all_result_modes(tools, empty, jit, error_type):
    tools.keyword_search_conversation_ids.side_effect = error_type('offline')
    tools.is_jit_conversation_retrieval_enabled.return_value = jit
    tools.format_active_jit_conversations.return_value = 'jit results'
    if jit:
        tools._consume_jit_summary_search_budget = lambda config: None
    if empty:
        tools.vector_db.query_vectors.return_value = []
    before = value('keyword', 'degraded')
    result = invoke(tools)
    assert result.endswith('[Keyword index temporarily unavailable; results are semantic-only]')
    assert value('keyword', 'degraded') == before + 1
    if jit:
        assert result.startswith('jit results')
    elif empty:
        assert result.startswith('No conversations found')


def test_successful_empty_keyword_is_not_degraded(tools):
    tools.keyword_search_conversation_ids.return_value = []
    before = value('keyword', 'empty')
    assert 'Keyword index temporarily unavailable' not in invoke(tools)
    assert value('keyword', 'empty') == before + 1


def test_exact_lookup_skips_keyword_and_records_firestore(tools):
    before = value('firestore', 'ok')
    tools.search_conversations_tool(
        'e8c05000-52f0-4a95-951c-ccd715523429', include_transcript=False, config={'configurable': {'user_id': 'uid'}}
    )
    tools.keyword_search_conversation_ids.assert_not_called()
    assert value('firestore', 'ok') == before + 1


def test_vector_failure_counts_degraded(tools):
    tools.vector_db.query_vectors.side_effect = TimeoutError('offline')
    before = value('vector', 'degraded')
    invoke(tools)
    assert value('vector', 'degraded') == before + 1


def test_metrics_export_every_idle_bounded_child():
    for outcome in ('success', 'skipped_discarded', 'skipped_no_structured', 'error'):
        assert (
            REGISTRY.get_sample_value('omi_conversation_summary_vector_upserts_total', {'outcome': outcome}) is not None
        )
    for path in ('keyword', 'vector', 'transcript', 'firestore'):
        for outcome in ('ok', 'degraded', 'empty'):
            assert (
                REGISTRY.get_sample_value('omi_chat_search_tool_outcomes_total', {'path': path, 'outcome': outcome})
                is not None
            )


def test_recency_contract_in_inline_and_langsmith_fallback_prompts():
    backend = Path(__file__).resolve().parents[2]
    for path in ('utils/llm/chat.py', 'utils/observability/langsmith_prompts.py'):
        prompt = (backend / path).read_text()
        assert 'with a small limit and NO dates (newest-first)' in prompt
        assert 'Never claim recency from **search_conversations_tool** alone.' in prompt
        assert 'describe them as similarity matches, not a complete recent history.' in prompt
