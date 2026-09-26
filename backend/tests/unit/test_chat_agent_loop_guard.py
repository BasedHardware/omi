"""Loop-guard and parallel-tool contracts for agentic chat.

David's iOS recall (yesterday / friends / bars / jobs) hit the 80% key-overlap
gate because search_conversations shares a date window and defaults; only
``query`` changed. Hits were already in conversations_collected.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from utils.retrieval.safety import AgentSafetyGuard, CollectedContextReady, SafetyGuardError

from tests.unit.test_chat_agent_provider_retry import _FakeChatModel, _openai_chunk
from tests.unit.test_prompt_cache_integration import _get_agentic_module


def _search_params(query: str) -> dict:
    return {
        'query': query,
        'start_date': '2026-08-29',
        'end_date': '2026-08-30',
        'limit': 10,
        'include_transcript': True,
    }


class TestSearchConversationsLoopGuard:
    def test_different_queries_same_window_do_not_trip(self):
        guard = AgentSafetyGuard()
        guard.validate_tool_call('search_conversations', _search_params('yesterday'))
        guard.validate_tool_call('search_conversations', _search_params('friends'))
        guard.validate_tool_call('search_conversations', _search_params('bars'))
        guard.validate_tool_call('search_conversations', _search_params('jobs'))
        assert guard.tool_call_count == 4

    def test_identical_params_twice_still_guard(self):
        guard = AgentSafetyGuard()
        params = _search_params('yesterday')
        guard.validate_tool_call('search_conversations', params)
        with pytest.raises(SafetyGuardError, match='stuck trying to answer'):
            guard.validate_tool_call('search_conversations', dict(params))

    def test_identical_params_with_collected_results_do_not_emit_stuck(self):
        guard = AgentSafetyGuard()
        params = _search_params('yesterday')
        guard.validate_tool_call('search_conversations', params)
        collected = [{'id': 'conv-1', 'title': 'Dinner'}]
        with pytest.raises(CollectedContextReady):
            guard.validate_tool_call('search_conversations', dict(params), collected_results=collected)


@pytest.mark.asyncio
async def test_abort_with_collected_results_is_forbidden():
    """The canned stuck message must not replace an answer once retrieval collected hits."""
    agentic_mod = _get_agentic_module()
    guard = AgentSafetyGuard()
    collected = [{'id': 'conv-1'}]
    tool_calls = [
        {'id': 'call_1', 'name': 'search_conversations', 'input': _search_params('yesterday')},
        {'id': 'call_2', 'name': 'search_conversations', 'input': _search_params('yesterday')},
    ]
    callback = agentic_mod.AsyncStreamingCallback()
    full_response = []

    with patch.object(agentic_mod, '_execute_tool', new=AsyncMock(return_value='found dinner')):
        results = await agentic_mod._execute_independent_tool_calls(
            tool_calls,
            name_of=lambda call: call['name'],
            input_of=lambda call: call['input'],
            id_of=lambda call: call['id'],
            tool_registry={'search_conversations': MagicMock()},
            configurable={'conversations_collected': collected},
            safety_guard=guard,
            callback=callback,
            full_response=full_response,
            result_factory=lambda call, result: {'id': call['id'], 'content': result},
        )

    assert results is not None
    assert 'stuck trying to answer' not in ''.join(full_response)
    assert results[-1]['content'] == agentic_mod._COLLECTED_CONTEXT_TOOL_STUB
    assert guard.tool_call_count == 1


@pytest.mark.asyncio
async def test_parallel_tool_calls_in_one_turn_overlap():
    """Two tool_use blocks in one turn must start concurrently, not wait serially."""
    agentic_mod = _get_agentic_module()
    started: list[str] = []

    async def fake_execute(tool_name, _tool_input, _registry, _configurable):
        started.append(tool_name)
        while len(started) < 2:
            await asyncio.sleep(0)
        return f'result-{tool_name}'

    safety_guard = AgentSafetyGuard()
    callback = agentic_mod.AsyncStreamingCallback()
    full_response = []
    tool_calls = [
        {'id': 'call_1', 'name': 'lookup_a', 'input': {'query': 'a'}},
        {'id': 'call_2', 'name': 'lookup_b', 'input': {'query': 'b'}},
    ]

    async def go():
        return await agentic_mod._execute_independent_tool_calls(
            tool_calls,
            name_of=lambda call: call['name'],
            input_of=lambda call: call['input'],
            id_of=lambda call: call['id'],
            tool_registry={'lookup_a': MagicMock(), 'lookup_b': MagicMock()},
            configurable={'conversations_collected': []},
            safety_guard=safety_guard,
            callback=callback,
            full_response=full_response,
            result_factory=lambda call, result: {'id': call['id'], 'content': result},
        )

    with patch.object(agentic_mod, '_execute_tool', new=fake_execute):
        results = await asyncio.wait_for(go(), timeout=1.0)

    assert [item['content'] for item in results] == ['result-lookup_a', 'result-lookup_b']
    assert set(started) == {'lookup_a', 'lookup_b'}
    assert safety_guard.tool_call_count == 2
    assert 'stuck' not in ''.join(full_response)


@pytest.mark.asyncio
async def test_managed_loop_runs_two_tool_calls_without_serial_wait():
    agentic_mod = _get_agentic_module()
    started: list[str] = []

    async def fake_execute(tool_name, _tool_input, _registry, _configurable):
        started.append(tool_name)
        while len(started) < 2:
            await asyncio.sleep(0)
        return f'result-{tool_name}'

    scripts = [
        [
            type(
                'Chunk',
                (),
                {
                    'content': '',
                    'tool_call_chunks': [
                        {'index': 0, 'id': 'call_1', 'name': 'lookup_a', 'args': '{}'},
                        {'index': 1, 'id': 'call_2', 'name': 'lookup_b', 'args': '{}'},
                    ],
                },
            )()
        ],
        [_openai_chunk('both done')],
    ]
    safety_guard = AgentSafetyGuard()
    callback = agentic_mod.AsyncStreamingCallback()
    full_response: list[str] = []

    async def go():
        with patch.object(agentic_mod, 'get_llm', return_value=_FakeChatModel(scripts)), patch.object(
            agentic_mod, '_execute_tool', new=fake_execute
        ), patch.object(agentic_mod, 'handle_llm_error_async', new=AsyncMock()), patch.object(
            agentic_mod, 'record_fallback'
        ):
            return await agentic_mod._run_openai_agent_stream(
                'SYSTEM',
                [{'role': 'user', 'content': 'question'}],
                [],
                {'lookup_a': MagicMock(), 'lookup_b': MagicMock()},
                callback,
                full_response,
                safety_guard,
                {},
            )

    result = await asyncio.wait_for(go(), timeout=1.0)
    assert result is None
    assert set(started) == {'lookup_a', 'lookup_b'}
    assert safety_guard.tool_call_count == 2
    assert 'both done' in ''.join(full_response)
