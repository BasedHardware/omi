"""Tests for the chat agent's recovery from a failed provider stream.

Regression: the Anthropic call died mid-stream (``error_type=ReadTimeout``), the loop treated
it as fatal, and the turn ended with an empty answer the router could only render as a canned
error.

The loop tests reuse the agentic-module harness from ``test_prompt_cache_integration`` rather
than re-stubbing the LLM import stack, so both files share one ``sys.modules`` view.
"""

import types
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from utils.retrieval.safety import (
    SafetyGuardError,
    is_transient_provider_error,
    provider_fallback_reason,
    should_retry_provider_error,
)

from tests.unit.test_prompt_cache_integration import _get_agentic_module

# Provider exception stand-ins. Classification is by class name, so these carry the real names.


class ReadTimeout(Exception):
    pass


class RemoteProtocolError(Exception):
    pass


class _StatusError(Exception):
    def __init__(self, status_code):
        super().__init__(f'status {status_code}')
        self.status_code = status_code


class InternalServerError(_StatusError):
    def __init__(self):
        super().__init__(500)


class BadRequestError(_StatusError):
    def __init__(self):
        super().__init__(400)


class RateLimitError(_StatusError):
    def __init__(self):
        super().__init__(429)


class TestIsTransientProviderError:
    def test_transport_errors_are_transient(self):
        assert is_transient_provider_error(ReadTimeout())
        assert is_transient_provider_error(RemoteProtocolError())

    def test_provider_5xx_is_transient(self):
        assert is_transient_provider_error(InternalServerError())
        assert is_transient_provider_error(_StatusError(503))
        assert is_transient_provider_error(_StatusError(529))

    def test_client_errors_are_not_transient(self):
        assert not is_transient_provider_error(BadRequestError())
        assert not is_transient_provider_error(_StatusError(401))

    def test_rate_limit_is_not_retried_within_the_turn(self):
        assert not is_transient_provider_error(RateLimitError())

    def test_unknown_exception_is_not_transient(self):
        assert not is_transient_provider_error(ValueError('boom'))

    def test_status_wins_over_a_transport_sounding_name(self):
        class ReadTimeout(_StatusError):  # noqa: F811 — deliberately shadows, status must win
            def __init__(self):
                super().__init__(400)

        assert not is_transient_provider_error(ReadTimeout())

    def test_status_read_from_a_response_attribute(self):
        error = Exception('wrapped')
        error.response = types.SimpleNamespace(status_code=503)
        assert is_transient_provider_error(error)


class TestProviderFallbackReason:
    def test_timeout(self):
        assert provider_fallback_reason(ReadTimeout()) == 'timeout'

    def test_provider_5xx(self):
        assert provider_fallback_reason(InternalServerError()) == 'provider_5xx'

    def test_provider_429(self):
        assert provider_fallback_reason(RateLimitError()) == 'provider_429'

    def test_unclassified(self):
        assert provider_fallback_reason(RemoteProtocolError()) == 'other'
        assert provider_fallback_reason(BadRequestError()) == 'other'

    def test_reasons_are_in_the_shared_bounded_set(self):
        from utils.observability.fallback import ALLOWED_REASONS

        for error in (ReadTimeout(), InternalServerError(), RateLimitError(), BadRequestError()):
            assert provider_fallback_reason(error) in ALLOWED_REASONS


class TestShouldRetryProviderError:
    def _decide(self, error=None, **overrides):
        kwargs = {
            'attempts_made': 1,
            'max_attempts': 3,
            'text_already_streamed': False,
            'seconds_remaining': 150.0,
            'min_headroom_seconds': 45.0,
        }
        kwargs.update(overrides)
        return should_retry_provider_error(error or ReadTimeout(), **kwargs)

    def test_transient_failure_before_any_output_is_retried(self):
        assert self._decide() is True

    def test_streamed_text_blocks_a_retry(self):
        assert self._decide(text_already_streamed=True) is False

    def test_attempt_budget_is_respected(self):
        assert self._decide(attempts_made=2, max_attempts=3) is True
        assert self._decide(attempts_made=3, max_attempts=3) is False

    def test_no_retry_that_cannot_finish_in_the_remaining_time(self):
        assert self._decide(seconds_remaining=44.0, min_headroom_seconds=45.0) is False
        assert self._decide(seconds_remaining=45.0, min_headroom_seconds=45.0) is True

    def test_non_transient_failure_is_not_retried(self):
        assert self._decide(error=BadRequestError()) is False


# ---------------------------------------------------------------------------
# Agent loop behaviour
# ---------------------------------------------------------------------------


class FakeStream:
    """Stand-in for ``anthropic_client.messages.stream(...)``: yields ``events``, then raises."""

    def __init__(self, response=None, events=(), error=None):
        self.response = response
        self.events = list(events)
        self.error = error

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    def __aiter__(self):
        async def _events():
            for event in self.events:
                yield event
            if self.error is not None:
                raise self.error

        return _events()

    async def get_final_message(self):
        return self.response


def _text_delta(text):
    return types.SimpleNamespace(
        type='content_block_delta',
        delta=types.SimpleNamespace(type='text_delta', text=text),
    )


def _final(stop_reason='end_turn', content=()):
    return types.SimpleNamespace(stop_reason=stop_reason, content=list(content))


def _tool_use_final(tool_name='lookup'):
    return _final(
        stop_reason='tool_use',
        content=[types.SimpleNamespace(type='tool_use', id='tool-1', name=tool_name, input={'query': 'omi'})],
    )


@pytest.fixture
def agentic_mod(monkeypatch):
    mod = _get_agentic_module()
    monkeypatch.setattr(mod, 'AGENT_STREAM_PROVIDER_RETRY_BACKOFF_SECONDS', 0)
    return mod


def _run(agentic_mod, streams, safety_guard=None, tool_result='tool result'):
    """Drive the production loop over a scripted sequence of provider streams."""
    calls = []

    def stream(**kwargs):
        calls.append(kwargs)
        return streams[len(calls) - 1]

    if safety_guard is None:
        safety_guard = MagicMock()
        safety_guard.should_warn_user.return_value = None
        safety_guard.get_stats.return_value = {}

    callback = agentic_mod.AsyncStreamingCallback()
    full_response = []

    async def go():
        with patch.object(agentic_mod.anthropic_client.messages, 'stream', side_effect=stream), patch.object(
            agentic_mod, '_execute_tool', new=AsyncMock(return_value=tool_result)
        ), patch.object(agentic_mod, 'handle_llm_error_async', new=AsyncMock()), patch.object(
            agentic_mod, 'record_fallback'
        ) as recorded:
            result = await agentic_mod._run_anthropic_agent_stream(
                'SYSTEM',
                [{'role': 'user', 'content': 'question'}],
                [],
                {'lookup': MagicMock()},
                callback,
                full_response,
                safety_guard,
                {},
            )
        return result, recorded

    return go, calls, full_response


async def test_transient_provider_failure_is_retried_and_the_turn_survives(agentic_mod):
    """A stalled stream with nothing yet delivered must not cost the turn."""
    streams = [
        FakeStream(error=ReadTimeout()),
        FakeStream(response=_final(), events=[_text_delta('Here is your answer.')]),
    ]
    go, calls, full_response = _run(agentic_mod, streams)

    result, recorded = await go()

    assert result is None, 'a recovered turn must not report a failure'
    assert ''.join(full_response) == 'Here is your answer.'
    assert len(calls) == 2, 'the failed attempt should have been re-issued'
    # The retry sends the identical request — a failed stream commits nothing.
    assert calls[0]['messages'] == calls[1]['messages']
    assert calls[0]['system'] == calls[1]['system']
    recorded.assert_called_once()
    assert recorded.call_args.kwargs['outcome'] == 'recovered'
    assert recorded.call_args.kwargs['reason'] == 'timeout'


async def test_no_retry_once_text_has_reached_the_user(agentic_mod):
    """Streamed tokens cannot be un-sent, so the partial answer is kept instead of duplicated.

    The persisted answer is the whole of what the user watched arrive: the partial answer and
    then the apology. Both are streamed either way — asserting that only the partial one is
    persisted would pin the router to overwrite the pair with its canned error.
    """
    streams = [FakeStream(events=[_text_delta('Half an ans')], error=ReadTimeout())]
    go, calls, full_response = _run(agentic_mod, streams)

    result, recorded = await go()

    assert len(calls) == 1
    answer = ''.join(full_response)
    assert answer.startswith('Half an ans'), 'the delivered text must survive verbatim'
    assert answer.count('Half an ans') == 1, 'the partial answer must not be replayed'
    assert answer.endswith('Sorry, I encountered an error. Please try again.')
    assert result == 'provider_ReadTimeout'
    recorded.assert_not_called()


async def test_non_transient_failure_is_not_retried(agentic_mod):
    streams = [FakeStream(error=BadRequestError())]
    go, calls, _full_response = _run(agentic_mod, streams)

    result, _recorded = await go()

    assert len(calls) == 1, 'a bad request must not be sent again'
    assert result == 'provider_BadRequestError'


async def test_retries_are_bounded_by_the_attempt_budget(agentic_mod, monkeypatch):
    monkeypatch.setattr(agentic_mod, 'AGENT_STREAM_PROVIDER_MAX_ATTEMPTS', 3)
    streams = [FakeStream(error=ReadTimeout()) for _ in range(5)]
    go, calls, _full_response = _run(agentic_mod, streams)

    result, recorded = await go()

    assert len(calls) == 3
    assert result == 'provider_ReadTimeout'
    assert recorded.call_count == 0, 'nothing was recovered'


async def test_the_transport_silent_interval_bound_is_not_overridden(agentic_mod):
    """In prod these calls go through the gateway client, whose httpx.Timeout(read=15s) is the
    silent-interval policy the gateway's own observability is built around. A per-request
    timeout= would silently replace it for this one caller."""
    streams = [FakeStream(response=_final(), events=[_text_delta('hi')])]
    go, calls, _full_response = _run(agentic_mod, streams)

    await go()

    assert 'timeout' not in calls[0]


async def test_gateway_agent_loop_uses_openai_compatible_lane(agentic_mod, monkeypatch):
    calls = []

    class Model:
        def bind(self, **kwargs):
            calls.append(('bind', kwargs))
            return self

        def astream(self, messages):
            calls.append(('stream', messages))

            async def chunks():
                yield types.SimpleNamespace(content='Luna answer', tool_call_chunks=[])

            return chunks()

    guard = MagicMock()
    guard.get_stats.return_value = {}
    callback = agentic_mod.AsyncStreamingCallback()
    full_response = []
    monkeypatch.setattr(agentic_mod, 'get_llm', MagicMock(return_value=Model()))

    result = await agentic_mod._run_openai_agent_stream(
        'SYSTEM',
        [{'role': 'user', 'content': 'question'}],
        [],
        {},
        callback,
        full_response,
        guard,
        {},
    )

    assert result is None
    assert ''.join(full_response) == 'Luna answer'
    assert calls[0] == ('bind', {'tools': [], 'tool_choice': 'auto', 'max_completion_tokens': 8192})
    assert calls[1][1][0] == {'role': 'system', 'content': 'SYSTEM'}


async def test_tool_loop_still_reaches_a_second_iteration(agentic_mod):
    """The retry loop must not swallow the ordinary tool-use iteration."""
    streams = [
        FakeStream(response=_tool_use_final()),
        FakeStream(response=_final(), events=[_text_delta('done')]),
    ]
    go, calls, full_response = _run(agentic_mod, streams)

    result, _recorded = await go()

    assert result is None
    assert len(calls) == 2
    assert calls[1]['messages'][-1]['content'][0]['type'] == 'tool_result'
    assert ''.join(full_response) == 'done'


async def test_gateway_agent_uses_openai_tools_and_continues_after_tool_call(agentic_mod, monkeypatch):
    """Managed chat must use chat-completions tool history, not Anthropic content blocks."""

    class GatewayChatModel:
        def __init__(self):
            self.bind_kwargs = None
            self.calls = []
            self.streams = [
                [
                    types.SimpleNamespace(
                        content='',
                        tool_call_chunks=[
                            {'index': 0, 'id': 'call_1', 'name': 'lookup', 'args': '{"query":'},
                        ],
                    ),
                    types.SimpleNamespace(
                        content='',
                        tool_call_chunks=[{'index': 0, 'args': '"omi"}'}],
                    ),
                ],
                [types.SimpleNamespace(content='done', tool_call_chunks=[])],
            ]

        def bind(self, **kwargs):
            self.bind_kwargs = kwargs
            return self

        async def astream(self, messages):
            self.calls.append(messages)
            for chunk in self.streams.pop(0):
                yield chunk

    gateway_model = GatewayChatModel()
    monkeypatch.setattr(agentic_mod, 'get_llm', lambda *args, **kwargs: gateway_model)

    safety_guard = MagicMock()
    safety_guard.should_warn_user.return_value = None
    safety_guard.get_stats.return_value = {}
    callback = agentic_mod.AsyncStreamingCallback()
    full_response = []
    tool_schemas = agentic_mod._convert_anthropic_tools_to_openai(
        [
            agentic_mod.WEB_SEARCH_TOOL,
            agentic_mod.TOOL_SEARCH_TOOL,
            {
                'name': 'lookup',
                'description': 'Look something up',
                'input_schema': {
                    'type': 'object',
                    'properties': {'query': {'type': 'string'}},
                    'required': ['query'],
                },
            },
        ]
    )

    with patch.object(agentic_mod, '_execute_tool', new=AsyncMock(return_value='tool result')):
        result = await agentic_mod._run_openai_agent_stream(
            'SYSTEM',
            [{'role': 'user', 'content': 'question'}],
            tool_schemas,
            {'lookup': MagicMock()},
            callback,
            full_response,
            safety_guard,
            {'user_id': 'user-1'},
        )

    assert result is None
    assert ''.join(full_response) == 'done'
    assert len(gateway_model.calls) == 2
    assert gateway_model.calls[0][0] == {'role': 'system', 'content': 'SYSTEM'}
    assert gateway_model.calls[1][-2]['role'] == 'assistant'
    assert gateway_model.calls[1][-2]['tool_calls'][0]['function']['name'] == 'lookup'
    assert gateway_model.calls[1][-1] == {
        'role': 'tool',
        'tool_call_id': 'call_1',
        'content': 'tool result',
    }
    assert [tool['function']['name'] for tool in gateway_model.bind_kwargs['tools']] == ['lookup']


def test_gateway_tool_conversion_drops_anthropic_server_tools(agentic_mod):
    converted = agentic_mod._convert_anthropic_tools_to_openai(
        [
            agentic_mod.WEB_SEARCH_TOOL,
            agentic_mod.TOOL_SEARCH_TOOL,
            {'name': 'lookup', 'input_schema': {'type': 'object'}},
        ]
    )

    assert converted == [
        {
            'type': 'function',
            'function': {
                'name': 'lookup',
                'description': '',
                'parameters': {'type': 'object'},
            },
        }
    ]


async def test_gateway_mode_selects_openai_agent_runner(agentic_mod):
    callback_data = {}
    seen = {}

    async def fake_run_blocking(_executor, function, *_args, **_kwargs):
        if function is agentic_mod.get_user_timezone:
            return 'UTC'
        if function is agentic_mod._get_agentic_qa_prompt:
            return 'SYSTEM'
        if function is agentic_mod.load_app_tools:
            return []
        raise AssertionError(f'unexpected blocking setup call: {function}')

    async def openai_runner(system, messages, schemas, _registry, callback, full_response, _guard, _configurable):
        seen.update({'system': system, 'messages': messages, 'schemas': schemas})
        full_response.append('managed answer')
        await callback.put_data('managed answer')
        await callback.end()
        return None

    async def anthropic_runner(*_args):
        raise AssertionError('gateway mode selected the Anthropic runner')

    with patch.object(agentic_mod, 'should_route_chat_agent_through_gateway', return_value=True), patch.object(
        agentic_mod, 'run_blocking', new=fake_run_blocking
    ), patch.object(agentic_mod, '_convert_tools', return_value=([], {})), patch.object(
        agentic_mod, '_messages_to_anthropic', return_value=[{'role': 'user', 'content': 'hello'}]
    ), patch.object(
        agentic_mod, '_inject_current_datetime', side_effect=lambda messages, _block: messages
    ), patch.object(
        agentic_mod, '_run_openai_agent_stream', new=openai_runner
    ), patch.object(
        agentic_mod, '_run_anthropic_agent_stream', new=anthropic_runner
    ):
        chunks = [
            chunk
            async for chunk in agentic_mod.execute_agentic_chat_stream(
                'uid_test',
                [_chat_message('hello')],
                callback_data=callback_data,
                current_datetime_block='<current_datetime/>',
            )
        ]

    assert chunks == [f'think: {agentic_mod.AGENT_STREAM_SETUP_PROGRESS}', 'data: managed answer', None]
    assert callback_data['answer'] == 'managed answer'
    assert seen['system'].startswith('SYSTEM')
    assert '<url_fetching_instructions>' in seen['system']
    assert seen['messages'] == [{'role': 'user', 'content': 'hello'}]
    assert [schema['function']['name'] for schema in seen['schemas']] == ['perplexity_web_search_tool']


async def test_anthropic_byok_stays_on_openai_agent_runner(agentic_mod):
    """Chat-agent BYOK Anthropic is dropped: one Luna/OpenAI path, no second Messages lane."""
    callback_data = {}
    seen = {'openai': False}

    async def fake_run_blocking(_executor, function, *_args, **_kwargs):
        if function is agentic_mod.get_user_timezone:
            return 'UTC'
        if function is agentic_mod._get_agentic_qa_prompt:
            return 'SYSTEM'
        if function is agentic_mod.load_app_tools:
            return []
        raise AssertionError(f'unexpected blocking setup call: {function}')

    async def openai_runner(_system, _messages, _schemas, _registry, callback, full_response, _guard, _configurable):
        seen['openai'] = True
        full_response.append('managed answer')
        await callback.put_data('managed answer')
        await callback.end()
        return None

    async def anthropic_runner(*_args):
        raise AssertionError('Anthropic BYOK must not select the leftover Messages runner')

    with patch.object(agentic_mod, 'should_route_chat_agent_through_gateway', return_value=True), patch.object(
        agentic_mod, 'run_blocking', new=fake_run_blocking
    ), patch.object(agentic_mod, '_convert_tools', return_value=([], {})), patch.object(
        agentic_mod, '_messages_to_anthropic', return_value=[{'role': 'user', 'content': 'hello'}]
    ), patch.object(
        agentic_mod, '_inject_current_datetime', side_effect=lambda messages, _block: messages
    ), patch.object(
        agentic_mod, '_run_openai_agent_stream', new=openai_runner
    ), patch.object(
        agentic_mod, '_run_anthropic_agent_stream', new=anthropic_runner
    ):
        chunks = [
            chunk
            async for chunk in agentic_mod.execute_agentic_chat_stream(
                'uid_test',
                [_chat_message('hello')],
                callback_data=callback_data,
                current_datetime_block='<current_datetime/>',
            )
        ]

    assert chunks == [f'think: {agentic_mod.AGENT_STREAM_SETUP_PROGRESS}', 'data: managed answer', None]
    assert seen['openai'] is True


async def test_safety_guard_message_becomes_the_answer(agentic_mod):
    """Guard text reached the client but not the answer, so the canned error overwrote it."""
    guard = MagicMock()
    guard.validate_tool_call.side_effect = SafetyGuardError(
        'I seem to be stuck trying to answer your question. Could you rephrase it in a different way?'
    )
    guard.should_warn_user.return_value = None
    guard.get_stats.return_value = {}

    streams = [FakeStream(response=_tool_use_final())]
    go, _calls, full_response = _run(agentic_mod, streams, safety_guard=guard)

    result, _recorded = await go()

    assert result is None, 'a guard stop is a deliberate reply, not a provider failure'
    assert 'I seem to be stuck' in ''.join(full_response)


async def _drain(stream):
    return [chunk async for chunk in stream]


def _chat_message(text, sender='human'):
    """Duck-typed stand-in for models.chat.Message as the agent stream consumes it."""
    return types.SimpleNamespace(
        sender=sender,
        text=text,
        created_at=datetime(2026, 7, 28, 8, 53, tzinfo=timezone.utc),
        files_id=[],
    )


async def test_unrecovered_provider_failure_is_reported_to_the_caller(agentic_mod):
    """The router reads ``callback_data['error']``; a gave-up provider failure must land there."""

    async def producer(_system, _messages, _schemas, _registry, callback, _full_response, _guard, _configurable):
        await callback.put_thought('Searching your conversations')
        await callback.end()
        return 'provider_ReadTimeout'

    callback_data = {}
    with patch.object(agentic_mod, '_run_openai_agent_stream', new=producer):
        await _drain(
            agentic_mod.execute_agentic_chat_stream(
                'uid_test',
                [_chat_message('what did I do yesterday?')],
                callback_data=callback_data,
                current_datetime_block='<current_datetime/>',
            )
        )

    assert callback_data['answer'] == '', 'no answer was produced'
    assert callback_data['error'] == 'provider_ReadTimeout'


async def test_successful_turn_reports_no_error(agentic_mod):
    async def producer(_system, _messages, _schemas, _registry, callback, full_response, _guard, _configurable):
        full_response.append('an answer')
        await callback.put_data('an answer')
        await callback.end()
        return None

    callback_data = {}
    with patch.object(agentic_mod, '_run_openai_agent_stream', new=producer):
        await _drain(
            agentic_mod.execute_agentic_chat_stream(
                'uid_test',
                [_chat_message('hello')],
                callback_data=callback_data,
                current_datetime_block='<current_datetime/>',
            )
        )

    assert callback_data['answer'] == 'an answer'
    assert 'error' not in callback_data


async def test_context_size_guard_message_becomes_the_answer(agentic_mod):
    guard = MagicMock()
    guard.should_warn_user.return_value = None
    guard.get_stats.return_value = {}
    guard.check_context_size.side_effect = SafetyGuardError("That's a lot of information to process at once!")

    streams = [FakeStream(response=_tool_use_final())]
    go, _calls, full_response = _run(agentic_mod, streams, safety_guard=guard)

    result, _recorded = await go()

    assert result is None
    assert "That's a lot of information to process at once!" in ''.join(full_response)


# ---------------------------------------------------------------------------
# Terminal-exit contract
#
# FC-recoverable-provider-failure-terminal has now recurred once per exit path out of the agent
# loop: the safety-guard reply, the bounded-stop partial, the oversized-input reply, the stalled
# stream, and the provider refusal were each fixed at their own call site. They share one cause —
# a terminal path that ends the turn without leaving the router something to render, or without
# reporting that it failed, is indistinguishable from a model that legitimately said nothing.
#
# This table is the guard surface for that contract rather than another per-path regression test:
# a new exit added to the loop is expected to appear here, and any exit that ends the turn silent
# fails it.
# ---------------------------------------------------------------------------


def _refusal_final(category=None):
    """A declined turn: HTTP success, terminal stop reason, no content blocks."""
    stop_details = types.SimpleNamespace(type='refusal', category=category) if category else None
    return types.SimpleNamespace(stop_reason='refusal', content=[], stop_details=stop_details)


def _blocking_guard(method, message):
    guard = MagicMock()
    guard.should_warn_user.return_value = None
    guard.get_stats.return_value = {}
    getattr(guard, method).side_effect = SafetyGuardError(message)
    return guard


TERMINAL_EXITS = {
    'model_answered': (
        [FakeStream(response=_final(), events=[_text_delta('Here is your answer.')])],
        None,
        False,
    ),
    'provider_refused': ([FakeStream(response=_refusal_final())], None, True),
    'provider_refused_with_category': ([FakeStream(response=_refusal_final(category='cyber'))], None, True),
    # Whitespace makes ``full_response`` non-empty while the persisted reply is still blank.
    'provider_refused_after_whitespace': (
        [FakeStream(response=_refusal_final(), events=[_text_delta('\n\n')])],
        None,
        True,
    ),
    'provider_failed_unrecoverably': ([FakeStream(error=BadRequestError())], None, True),
    'retry_budget_exhausted': ([FakeStream(error=ReadTimeout()) for _ in range(5)], None, True),
    'safety_guard_blocked_a_tool': (
        [FakeStream(response=_tool_use_final())],
        ('validate_tool_call', 'I seem to be stuck trying to answer your question.'),
        False,
    ),
    'safety_guard_blocked_on_context_size': (
        [FakeStream(response=_tool_use_final())],
        ('check_context_size', "That's a lot of information to process at once!"),
        False,
    ),
}


#: Every scripted failure case supplies this many streams. Pinned rather than read from the
#: module default so raising that default turns into a budget-exhaustion assertion failure here,
#: not an IndexError off the end of the script — the latter would pass for the wrong reason.
SCRIPTED_FAILURE_ATTEMPTS = 5


@pytest.mark.parametrize('exit_name', sorted(TERMINAL_EXITS))
async def test_every_terminal_exit_leaves_an_answer_and_reports_whether_it_failed(agentic_mod, exit_name, monkeypatch):
    monkeypatch.setattr(agentic_mod, 'AGENT_STREAM_PROVIDER_MAX_ATTEMPTS', SCRIPTED_FAILURE_ATTEMPTS)
    streams, guard_spec, expects_failure = TERMINAL_EXITS[exit_name]
    guard = _blocking_guard(*guard_spec) if guard_spec else None
    go, _calls, full_response = _run(agentic_mod, streams, safety_guard=guard)

    result, _recorded = await go()

    # The router builds both the persisted reply and the terminal done: frame from
    # ``full_response``. Text that only reached ``put_data`` is overwritten by its canned error.
    assert ''.join(full_response).strip(), f'{exit_name} ended the turn with nothing to render'

    if expects_failure:
        assert result, f'{exit_name} is a failure and must report a reason the router can record'
    else:
        assert result is None, f'{exit_name} is a deliberate reply, not a provider failure'


# ---------------------------------------------------------------------------
# The same contract on the managed (OpenAI chat-completions) loop.
#
# ``_run_openai_agent_stream`` is the runner gateway feature mode selects, so it carries the
# production traffic. It was added with the same defect this class describes at two of its exits:
# an apology pushed through ``put_data`` alone, which the router then overwrote. The contract is
# provider-independent, so the table is duplicated in shape rather than in assertions.
# ---------------------------------------------------------------------------


class _FakeChatModel:
    """Scripted stand-in for the bound chat model ``get_llm`` returns."""

    def __init__(self, scripts):
        self._scripts = list(scripts)
        self._call = 0

    def bind(self, **_kwargs):
        return self

    def astream(self, _messages):
        script = self._scripts[self._call]
        self._call += 1

        async def chunks():
            if isinstance(script, Exception):
                raise script
            for chunk in script:
                yield chunk

        return chunks()


def _openai_chunk(text='', tool_calls=None):
    return types.SimpleNamespace(content=text, tool_call_chunks=tool_calls or [])


def _openai_tool_chunk(name='lookup'):
    return [{'index': 0, 'id': 'call_1', 'name': name, 'args': '{}'}]


def _run_openai(agentic_mod, scripts, safety_guard=None, get_llm_error=None, tool_result='tool result'):
    """Drive the managed loop over a scripted sequence of provider streams."""
    if safety_guard is None:
        safety_guard = MagicMock()
        safety_guard.should_warn_user.return_value = None
        safety_guard.get_stats.return_value = {}

    callback = agentic_mod.AsyncStreamingCallback()
    full_response = []
    get_llm = MagicMock(side_effect=get_llm_error) if get_llm_error else MagicMock(return_value=_FakeChatModel(scripts))

    async def go():
        with patch.object(agentic_mod, 'get_llm', new=get_llm), patch.object(
            agentic_mod, '_execute_tool', new=AsyncMock(return_value=tool_result)
        ), patch.object(agentic_mod, 'handle_llm_error_async', new=AsyncMock()), patch.object(
            agentic_mod, 'record_fallback'
        ):
            return await agentic_mod._run_openai_agent_stream(
                'SYSTEM',
                [{'role': 'user', 'content': 'question'}],
                [],
                {'lookup': MagicMock()},
                callback,
                full_response,
                safety_guard,
                {},
            )

    return go, full_response


OPENAI_TERMINAL_EXITS = {
    'model_answered': ([[_openai_chunk('Here is your answer.')]], None, None, False),
    # A content filter on this contract yields no signal of its own: the completion simply
    # arrives with no text and no tool calls, which the loop would otherwise treat as done.
    'model_returned_nothing': ([[_openai_chunk('')]], None, None, True),
    'client_construction_failed': (None, None, BadRequestError(), True),
    'provider_failed_unrecoverably': ([BadRequestError()], None, None, True),
    'retry_budget_exhausted': ([ReadTimeout() for _ in range(5)], None, None, True),
    'safety_guard_blocked_a_tool': (
        [[_openai_chunk(tool_calls=_openai_tool_chunk())]],
        ('validate_tool_call', 'I seem to be stuck trying to answer your question.'),
        None,
        False,
    ),
    'safety_guard_blocked_on_context_size': (
        [[_openai_chunk(tool_calls=_openai_tool_chunk())]],
        ('check_context_size', "That's a lot of information to process at once!"),
        None,
        False,
    ),
}


@pytest.mark.parametrize('exit_name', sorted(OPENAI_TERMINAL_EXITS))
async def test_every_managed_terminal_exit_leaves_an_answer_and_reports_whether_it_failed(
    agentic_mod, exit_name, monkeypatch
):
    monkeypatch.setattr(agentic_mod, 'AGENT_STREAM_PROVIDER_MAX_ATTEMPTS', SCRIPTED_FAILURE_ATTEMPTS)
    scripts, guard_spec, get_llm_error, expects_failure = OPENAI_TERMINAL_EXITS[exit_name]
    guard = _blocking_guard(*guard_spec) if guard_spec else None
    go, full_response = _run_openai(agentic_mod, scripts, safety_guard=guard, get_llm_error=get_llm_error)

    result = await go()

    assert ''.join(full_response).strip(), f'{exit_name} ended the turn with nothing to render'

    if expects_failure:
        assert result, f'{exit_name} is a failure and must report a reason the router can record'
    else:
        assert result is None, f'{exit_name} is a deliberate reply, not a provider failure'


async def test_a_silent_completion_is_reported_rather_than_persisted_as_a_blank_answer(agentic_mod):
    """The managed contract has no refusal stop reason — a filtered turn is just an empty
    completion, so the only signal the loop gets is that it produced nothing."""
    go, full_response = _run_openai(agentic_mod, [[_openai_chunk('')]])

    result = await go()

    assert result == 'empty_answer'
    assert ''.join(full_response) == agentic_mod.AGENT_EMPTY_ANSWER_MESSAGE


async def test_refusal_is_reported_as_a_failure_rather_than_an_empty_answer(agentic_mod):
    """A declined turn returns HTTP 200 with empty content — the loop must not read that as
    'the model chose to say nothing', which lands the user on the router's generic error."""
    go, calls, full_response = _run(agentic_mod, [FakeStream(response=_refusal_final(category='cyber'))])

    result, recorded = await go()

    assert result == 'provider_refusal'
    assert ''.join(full_response) == agentic_mod.AGENT_REFUSAL_MESSAGE
    assert len(calls) == 1, 'a refusal is deterministic — re-sending the same prompt is wasted spend'
    recorded.assert_not_called()


async def test_refusal_keeps_text_the_user_already_saw(agentic_mod):
    """A classifier can fire mid-turn, after real content streamed. That text is a real answer."""
    stream = FakeStream(response=_refusal_final(), events=[_text_delta('Here is what I found')])
    go, _calls, full_response = _run(agentic_mod, [stream])

    result, _recorded = await go()

    assert result == 'provider_refusal'
    assert ''.join(full_response) == 'Here is what I found', 'delivered text must not be replaced'


def test_refusal_category_is_optional_at_every_level(agentic_mod):
    """``stop_details`` is absent on other stop reasons and on older provider versions."""
    assert agentic_mod._refusal_category(_refusal_final(category='cyber')) == 'cyber'
    assert agentic_mod._refusal_category(_refusal_final()) == 'unspecified'
    assert agentic_mod._refusal_category(types.SimpleNamespace(stop_reason='refusal')) == 'unspecified'
    assert agentic_mod._refusal_category(types.SimpleNamespace(stop_details=None)) == 'unspecified'
