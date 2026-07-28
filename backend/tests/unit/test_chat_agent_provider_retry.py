"""Tests for the chat agent's recovery from a failed provider stream.

Production symptom this covers: the agent's Anthropic call died mid-stream with a transport
error (``error_type=ReadTimeout``), the loop treated it as fatal, and the turn ended with an
empty answer — which the router can only render as "Sorry, something went wrong while generating
a response." A momentary provider stall cost the user their whole reply.

Two behaviours are pinned here:

1. A transport-class failure is re-issued while nothing has reached the user yet, and is *not*
   re-issued once text has streamed (a second attempt would duplicate it on screen).
2. A provider failure the loop could not recover from is reported to the caller instead of
   looking like a model that legitimately produced nothing.

The pure decision logic is exercised directly against ``utils.retrieval.safety`` (import-light).
The loop tests reuse the agentic-module harness from ``test_prompt_cache_integration`` rather
than re-stubbing the LLM import stack, so both files share one ``sys.modules`` view.
"""

import types
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from utils.retrieval.safety import (
    is_transient_provider_error,
    provider_fallback_reason,
    should_retry_provider_error,
)

from tests.unit.test_prompt_cache_integration import _get_agentic_module

# ---------------------------------------------------------------------------
# Stand-ins for the provider exceptions. Classification is by class name because the raw
# httpx exceptions escape the SDK once the response body is already streaming — the exact
# shape seen in production — so these carry the real names rather than the real packages.
# ---------------------------------------------------------------------------


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
        # The request itself is the problem; sending it again cannot help.
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
            'seconds_per_attempt': 45.0,
        }
        kwargs.update(overrides)
        return should_retry_provider_error(error or ReadTimeout(), **kwargs)

    def test_transient_failure_before_any_output_is_retried(self):
        assert self._decide() is True

    def test_streamed_text_blocks_a_retry(self):
        # The tokens are already on the user's screen; a second attempt would duplicate them.
        assert self._decide(text_already_streamed=True) is False

    def test_attempt_budget_is_respected(self):
        assert self._decide(attempts_made=2, max_attempts=3) is True
        assert self._decide(attempts_made=3, max_attempts=3) is False

    def test_no_retry_that_cannot_finish_in_the_remaining_time(self):
        assert self._decide(seconds_remaining=44.0, seconds_per_attempt=45.0) is False
        assert self._decide(seconds_remaining=45.0, seconds_per_attempt=45.0) is True

    def test_non_transient_failure_is_not_retried(self):
        assert self._decide(error=BadRequestError()) is False


# ---------------------------------------------------------------------------
# Agent loop behaviour
# ---------------------------------------------------------------------------


class FakeStream:
    """Minimal stand-in for ``anthropic_client.messages.stream(...)``.

    ``events`` are yielded before ``error`` (if any) is raised, which is what distinguishes a
    stall before the first token from one that interrupts text already on the user's screen.
    """

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
    # The production backoff is a real wait; unit tests must not sleep through it.
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
    """The regression: a stalled stream with nothing yet delivered must not cost the turn."""
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
    """Streamed tokens cannot be un-sent, so the partial answer is kept instead of duplicated."""
    streams = [FakeStream(events=[_text_delta('Half an ans')], error=ReadTimeout())]
    go, calls, full_response = _run(agentic_mod, streams)

    result, recorded = await go()

    assert len(calls) == 1
    assert ''.join(full_response) == 'Half an ans', 'the delivered text must survive verbatim'
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


async def test_each_attempt_carries_an_idle_timeout_that_leaves_room_to_retry(agentic_mod):
    """The client default (120s) exceeded the whole turn budget, so a stall left no second chance."""
    streams = [FakeStream(response=_final(), events=[_text_delta('hi')])]
    go, calls, _full_response = _run(agentic_mod, streams)

    await go()

    assert calls[0]['timeout'] == agentic_mod.AGENT_STREAM_PROVIDER_IDLE_TIMEOUT_SECONDS
    assert (
        agentic_mod.AGENT_STREAM_PROVIDER_IDLE_TIMEOUT_SECONDS * 2 <= agentic_mod.AGENT_STREAM_MAX_DURATION_SECONDS
    ), 'one attempt must fit the turn budget at least twice or a retry can never run'


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
    """``error=False`` on a failed turn is what made this indistinguishable from an empty model.

    The router logs and the fallback metric read ``callback_data['error']``; a provider failure
    the loop gave up on must land there even though the stream itself ended cleanly.
    """

    async def producer(_system, _messages, _schemas, _registry, callback, _full_response, _guard, _configurable):
        await callback.put_thought('Searching your conversations')
        await callback.end()
        return 'provider_ReadTimeout'

    callback_data = {}
    with patch.object(agentic_mod, '_run_anthropic_agent_stream', new=producer):
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
    with patch.object(agentic_mod, '_run_anthropic_agent_stream', new=producer):
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
