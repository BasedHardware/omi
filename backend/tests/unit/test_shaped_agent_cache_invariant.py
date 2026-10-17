import copy

import pytest

from utils.llm.shaped_agent import Budget, Mount, PREFIX_VIOLATIONS, Turn, run_loop


@pytest.mark.asyncio
@pytest.mark.parametrize('mutate,expected', [(False, 0), (True, 1)])
async def test_prefix_violation_is_measured_without_failing(mutate, expected):
    before = PREFIX_VIOLATIONS.labels(reason='messages')._value.get()
    requests = []

    async def model(mount, messages):
        requests.append(copy.deepcopy(messages))
        if len(requests) == 1:
            if mutate:
                messages[1]['content'][0]['text'] = 'synthetic mutated seed'
            return Turn(tool_calls=('invented',), messages=({'role': 'assistant', 'content': 'invented call'},))
        return Turn(value='finished')

    async def tool(calls):
        return [{'role': 'tool', 'content': 'invented result'}]

    seed = [{'role': 'user', 'content': 'synthetic stable seed'}]
    result = await run_loop(Mount(tools=('invented',), budget=Budget(turns=2, tool_calls=1)), seed, model, tool)
    assert result.value == 'finished'
    assert PREFIX_VIOLATIONS.labels(reason='messages')._value.get() - before == expected
    assert seed == [{'role': 'user', 'content': 'synthetic stable seed'}]
    if not mutate:
        assert requests[1][: len(requests[0])] == requests[0]
    assert requests[0][1]['content'][0]['prompt_cache_breakpoint']['mode'] == 'explicit'


def test_stable_context_precedes_volatile_evidence():
    mount = Mount(stable_context=({'role': 'user', 'content': 'synthetic stable'},))
    messages = mount.messages([{'role': 'user', 'content': 'synthetic volatile'}])
    assert messages[0]['role'] == 'system'
    assert messages[1]['content'][0]['text'] == 'synthetic stable'
    assert messages[2]['content'] == 'synthetic volatile'
