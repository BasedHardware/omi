"""Regression tests for the server-side ``web_search`` egress gate on the agentic path.

Anthropic executes ``web_search`` on its own infrastructure, so the query string
never reaches ``_execute_tool`` and leaves the trust boundary without passing any
in-process control. Once a tool result is in the transcript, an injected
instruction can place that data into the query.

These cases drive the real Anthropic tool loop through the provider seam and
assert on the ``tools`` list of every request the loop actually composes — the
taint appears *during* the loop, so a single up-front decision cannot see it.
"""

import asyncio
from types import SimpleNamespace

import pytest

from utils.llm.private_context import anthropic_messages_carry_private_tool_output
from utils.retrieval import agentic
from utils.retrieval import web_search_gate
from utils.retrieval.safety import AgentSafetyGuard

WEB_SEARCH_NAME = 'web_search'


def _text_delta(text):
    return SimpleNamespace(type='content_block_delta', delta=SimpleNamespace(type='text_delta', text=text))


def _tool_use(block_id, name, tool_input=None):
    return SimpleNamespace(type='tool_use', id=block_id, name=name, input=tool_input or {})


def _answer(text):
    return SimpleNamespace(type='text', text=text)


def _response(stop_reason, content):
    return SimpleNamespace(stop_reason=stop_reason, content=content, stop_details=None)


class _FakeStream:
    def __init__(self, response, events):
        self._response = response
        self._events = list(events)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return False

    def __aiter__(self):
        async def iterator():
            for event in self._events:
                yield event

        return iterator()

    async def get_final_message(self):
        return self._response


class _FakeMessages:
    """Records the kwargs of every provider request the loop composes."""

    def __init__(self, turns):
        self._turns = list(turns)
        self.requests = []

    def stream(self, **kwargs):
        self.requests.append(kwargs)
        response, events = self._turns.pop(0)
        return _FakeStream(response, events)


class _FakeTool:
    def __init__(self, name, result):
        self.name = name
        self._result = result

    async def ainvoke(self, tool_input, config=None):
        return self._result


def _tool_names(request):
    return [tool.get('name') for tool in request['tools']]


def _drive_loop(monkeypatch, *, turns, registry):
    """Run the direct Anthropic agent loop and return the composed requests."""
    fake_messages = _FakeMessages(turns)
    monkeypatch.setattr(agentic, 'anthropic_client', SimpleNamespace(messages=fake_messages))

    fallbacks = []

    def _capture_fallback(**fields):
        fallbacks.append(fields)

    monkeypatch.setattr(agentic, 'record_fallback', _capture_fallback)
    monkeypatch.setattr(web_search_gate, 'record_fallback', _capture_fallback)

    async def main():
        callback = agentic.AsyncStreamingCallback()
        return await agentic._run_anthropic_agent_stream(
            system_prompt='you are a helpful assistant',
            messages=[{'role': 'user', 'content': 'hello'}],
            tool_schemas=[agentic.WEB_SEARCH_TOOL, *(_schema(name) for name in registry)],
            tool_registry=registry,
            callback=callback,
            full_response=[],
            safety_guard=AgentSafetyGuard(max_tool_calls=25, max_context_tokens=500000),
            configurable={'user_id': 'test-uid'},
        )

    asyncio.run(main())
    return fake_messages.requests, fallbacks


def _schema(name):
    return {'name': name, 'description': name, 'input_schema': {'type': 'object', 'properties': {}}}


def _two_turn(tool_name, tool_result):
    """Model calls *tool_name*, gets *tool_result*, then answers."""
    return [
        (_response('tool_use', [_tool_use('use_1', tool_name)]), []),
        (_response('end_turn', [_answer('done')]), [_text_delta('done')]),
    ]


def test_web_search_is_withheld_after_a_private_tool_result(monkeypatch):
    """A memory read taints the loop: the next request must not offer web_search."""
    registry = {'get_memories_tool': _FakeTool('get_memories_tool', 'secret: board deck passphrase')}
    requests, fallbacks = _drive_loop(
        monkeypatch,
        turns=_two_turn('get_memories_tool', 'secret: board deck passphrase'),
        registry=registry,
    )

    assert len(requests) == 2
    assert WEB_SEARCH_NAME in _tool_names(requests[0]), 'clean opening request should still offer web_search'
    assert WEB_SEARCH_NAME not in _tool_names(
        requests[1]
    ), 'web_search must be withheld once private data is in context'
    assert [fallback['reason'] for fallback in fallbacks] == ['private_tool_output_in_context']
    assert fallbacks[0]['from_mode'] == 'anthropic_web_search'
    assert fallbacks[0]['to_mode'] == 'model_knowledge'
    assert fallbacks[0]['outcome'] == 'degraded'


def test_web_search_survives_a_public_safe_tool_result(monkeypatch):
    """Product-doc lookups carry no user data, so the feature must not regress."""
    registry = {'get_omi_product_info_tool': _FakeTool('get_omi_product_info_tool', 'Omi docs: battery lasts 3 days')}
    requests, fallbacks = _drive_loop(
        monkeypatch,
        turns=_two_turn('get_omi_product_info_tool', 'Omi docs: battery lasts 3 days'),
        registry=registry,
    )

    assert len(requests) == 2
    assert WEB_SEARCH_NAME in _tool_names(requests[0])
    assert WEB_SEARCH_NAME in _tool_names(requests[1]), 'a public-safe producer must not withhold web_search'
    assert fallbacks == []


def test_unknown_producer_is_treated_as_private(monkeypatch):
    """App tools are dynamic; an unrecognised producer must taint the loop."""
    registry = {'app_acme_fetch_orders': _FakeTool('app_acme_fetch_orders', 'order #42 for alice@example.com')}
    requests, fallbacks = _drive_loop(
        monkeypatch,
        turns=_two_turn('app_acme_fetch_orders', 'order #42 for alice@example.com'),
        registry=registry,
    )

    assert WEB_SEARCH_NAME not in _tool_names(requests[1])
    assert [fallback['reason'] for fallback in fallbacks] == ['private_tool_output_in_context']


def test_withheld_path_is_recorded_once_per_loop(monkeypatch):
    """Telemetry marks the transition, not every subsequent request.

    The second memories call must use different params so the shared exact-repeat
    loop guard does not abort the leftover Anthropic runner mid-loop.
    """
    registry = {'get_memories_tool': _FakeTool('get_memories_tool', 'private')}
    turns = [
        (_response('tool_use', [_tool_use('use_1', 'get_memories_tool', {'query': 'deck'})]), []),
        (_response('tool_use', [_tool_use('use_2', 'get_memories_tool', {'query': 'passphrase'})]), []),
        (_response('end_turn', [_answer('done')]), [_text_delta('done')]),
    ]
    requests, fallbacks = _drive_loop(monkeypatch, turns=turns, registry=registry)

    assert len(requests) == 3
    assert WEB_SEARCH_NAME not in _tool_names(requests[1])
    assert WEB_SEARCH_NAME not in _tool_names(requests[2])
    assert len(fallbacks) == 1


def test_convert_tools_does_not_offer_anthropic_server_web_search():
    """Live composition is OpenAI function tools; Anthropic web_search is leftover-only."""
    schemas, _ = agentic._convert_tools([], [])
    top_level_names = [schema.get('name') for schema in schemas]
    function_names = [schema.get('function', {}).get('name') for schema in schemas if isinstance(schema, dict)]
    assert WEB_SEARCH_NAME not in top_level_names
    assert WEB_SEARCH_NAME not in function_names


@pytest.mark.parametrize(
    'messages, expected',
    [
        ([], False),
        ('not-a-list', False),
        ([{'role': 'user', 'content': 'plain text turn'}], False),
        (
            [
                {
                    'role': 'assistant',
                    'content': [{'type': 'tool_use', 'id': 'u1', 'name': 'get_omi_product_info_tool'}],
                },
                {'role': 'user', 'content': [{'type': 'tool_result', 'tool_use_id': 'u1', 'content': 'docs'}]},
            ],
            False,
        ),
        (
            [
                {'role': 'assistant', 'content': [{'type': 'tool_use', 'id': 'u1', 'name': 'get_gmail_messages_tool'}]},
                {'role': 'user', 'content': [{'type': 'tool_result', 'tool_use_id': 'u1', 'content': 'inbox'}]},
            ],
            True,
        ),
        # A result with no matching tool_use has no identifiable producer.
        (
            [{'role': 'user', 'content': [{'type': 'tool_result', 'tool_use_id': 'orphan', 'content': 'x'}]}],
            True,
        ),
    ],
)
def test_anthropic_classifier_reads_wire_shape(messages, expected):
    assert (
        anthropic_messages_carry_private_tool_output(
            messages, public_safe_tools=frozenset({'get_omi_product_info_tool'})
        )
        is expected
    )


def test_managed_lane_never_ships_the_provider_executed_tool():
    """The gate is scoped to the leftover Anthropic lane on purpose.

    Live ``_convert_tools`` emits OpenAI function schemas only. The leftover
    converter still drops Anthropic server tools (no ``input_schema``) so a
    specialist fixture cannot smuggle ``web_search`` onto the managed lane.
    Public web search on the live path is the in-process Perplexity function
    tool, which does pass through ``_execute_tool``.
    """
    schemas, _ = agentic._convert_tools([], [])
    live_names = [
        schema.get('function', {}).get('name') if isinstance(schema.get('function'), dict) else schema.get('name')
        for schema in schemas
    ]
    assert WEB_SEARCH_NAME not in live_names

    converted = agentic._convert_anthropic_tools_to_openai(
        [agentic.WEB_SEARCH_TOOL, agentic.TOOL_SEARCH_TOOL, _schema('lookup')]
    )
    assert WEB_SEARCH_NAME not in [tool['function']['name'] for tool in converted]
    assert [tool['function']['name'] for tool in converted] == ['lookup']
