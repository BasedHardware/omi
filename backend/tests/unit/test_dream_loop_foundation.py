"""Terminal staging, graceful budgets, stable prefixes and reserved tool routes."""

import asyncio
from copy import deepcopy

import pytest

from llm_gateway.gateway.config_loader import load_gateway_config
from llm_gateway.gateway.vertex_wire import _vertex_request
from utils.llm.shaped_agent import Budget, LoopStop, Mount, Turn, run_loop


def test_last_turn_stages_and_finishes_without_an_extra_model_call():
    usage = []

    async def turn(mount, messages):
        return Turn(tokens=11, tool_calls=({'name': 'propose_edit'}, {'name': 'finish'}))

    async def tools(calls):
        assert len(calls) == 2
        return LoopStop({'staged': 1})

    async def observe(result):
        usage.append(result.tokens)

    result = asyncio.run(
        run_loop(
            Mount(tools=('propose_edit', 'finish'), budget=Budget(turns=1, tool_calls=2, graceful=True)),
            [],
            turn,
            tools,
            observe_turn=observe,
        )
    )
    assert result.reason == 'finished' and result.value == {'staged': 1}
    assert result.turns == 1 and result.tool_calls == 2 and usage == [11]


def test_stable_prefix_is_identical_across_turns_for_implicit_cache():
    sent = []

    async def turn(mount, messages):
        sent.append(deepcopy(messages))
        return Turn(tool_calls=({'name': 'read'},), messages=({'role': 'assistant', 'content': None},))

    async def tools(calls):
        return [{'role': 'tool', 'tool_call_id': 'one', 'content': 'UNTRUSTED TOOL DATA: invented speech'}]

    result = asyncio.run(
        run_loop(
            Mount(
                instructions='Synthetic contract', tools=('read',), budget=Budget(turns=2, tool_calls=2, graceful=True)
            ),
            [{'role': 'user', 'content': 'Synthetic seed'}],
            turn,
            tools,
        )
    )
    assert sent[0] == sent[1][: len(sent[0])]
    assert result.reason == 'turn_budget' and result.tool_calls == 2


def test_graceful_deadline_keeps_completed_usage_for_the_verification_boundary():
    async def turn(mount, messages):
        return Turn(tokens=7, tool_calls=({'name': 'read'},))

    async def tools(calls):
        await asyncio.sleep(1)
        return []

    result = asyncio.run(
        run_loop(
            Mount(tools=('read',), budget=Budget(turns=2, tool_calls=2, deadline_seconds=0.01, graceful=True)),
            [],
            turn,
            tools,
        )
    )
    assert result.reason == 'deadline' and result.tokens == 7 and result.turns == 1


@pytest.mark.parametrize('stage', ['reasoning', 'verify'])
def test_both_dream_routes_preserve_one_reserved_38_attempt_without_fallback(stage):
    config = load_gateway_config(prod_mode=True)
    lane = config.lanes['omi:auto:dream-' + stage]
    route = config.route_artifacts[lane.active_route]
    assert (route.primary.provider, route.primary.model) == ('gemini', 'gemini-3.8-flash')
    assert route.provider_options['reserved_capacity_only'] is True
    assert route.provider_options['location'] == 'us'
    assert route.retry.max_attempts == 1
    assert route.fallbacks == []
    assert route.fallback_policy.fallback_on == []
    assert lane.capabilities.tools is (stage == 'reasoning')


def test_vertex_nested_tool_schema_and_tool_result_roundtrip():
    request = {
        'messages': [
            {'role': 'system', 'content': 'Contract'},
            {'role': 'user', 'content': 'Synthetic seed'},
            {
                'role': 'assistant',
                'content': None,
                'tool_calls': [
                    {
                        'id': 'read-1',
                        'type': 'function',
                        'function': {'name': 'read', 'arguments': '{"ref":"conversations/toy"}'},
                    }
                ],
            },
            {'role': 'tool', 'tool_call_id': 'read-1', 'content': '{"text":"UNTRUSTED TOOL DATA"}'},
        ],
        'tools': [
            {
                'type': 'function',
                'function': {
                    'name': 'read',
                    'parameters': {
                        'type': 'object',
                        '$defs': {'Ref': {'type': 'string'}},
                        'properties': {'ref': {'$ref': '#/$defs/Ref'}},
                        'required': ['ref'],
                    },
                },
            }
        ],
        'tool_choice': 'auto',
    }
    wire = _vertex_request(request)
    declaration = wire['tools'][0]['functionDeclarations'][0]
    assert '$defs' in declaration['parametersJsonSchema']
    assert wire['contents'][-1]['parts'][0]['functionResponse']['name'] == 'read'
    assert wire['toolConfig']['functionCallingConfig']['mode'] == 'AUTO'
