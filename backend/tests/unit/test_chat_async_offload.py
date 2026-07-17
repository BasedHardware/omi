"""
Regression tests: chat setup helpers that do blocking Firestore / LLM I/O must run
OFF the event-loop thread.

``execute_chat_stream`` / ``execute_agentic_chat_stream`` are async generators driven on
the event loop by ``StreamingResponse``. Before this fix several synchronous setup helpers
were called directly on the loop, blocking every concurrent request during chat setup:

- ``execute_agentic_chat_stream`` (the default chat path) ran ``get_user_timezone``,
  ``_get_agentic_qa_prompt`` (Firestore reads + a LangSmith prompt fetch), and
  ``load_app_tools`` inline before its first ``await``.
- ``_has_file_context`` ran ``retrieve_is_file_question`` — a ~1-2s synchronous LLM
  inference — inline on the file-chat path.

They now run via ``run_blocking(...)``. These tests drive the production async functions
through the executor seam and assert each helper executes on a non-loop thread, so a
regression that reintroduces an inline call fails. (Not a source grep: the offload is
observed via the thread each helper actually runs on.)
"""

import asyncio
import os
import threading
from contextlib import ExitStack, nullcontext
from types import SimpleNamespace
from unittest.mock import patch

# Hermetic config so importing the chat modules (which construct Typesense / OpenAI clients
# and require the encryption key) succeeds without network. Matches conftest defaults.
os.environ.setdefault('ENCRYPTION_SECRET', '0123456789abcdef0123456789abcdef')
os.environ.setdefault('OPENAI_API_KEY', 'sk-test')
os.environ.setdefault('TYPESENSE_API_KEY', 'test-typesense-key')
os.environ.setdefault('TYPESENSE_HOST', 'localhost')
os.environ.setdefault('TYPESENSE_HOST_PORT', '8108')
os.environ.setdefault('TYPESENSE_PROTOCOL', 'http')

# Imported at module scope so the heavy import cost lands in collection, keeping each
# per-test call within the fast-unit duration guard.
import utils.retrieval.graph as graph  # noqa: E402
import utils.retrieval.agentic as agentic  # noqa: E402


async def _collect_agentic_chunks(producer):
    """Drive the real public stream with deterministic setup dependencies."""
    with ExitStack() as stack:
        stack.enter_context(patch.object(agentic, 'get_user_timezone', lambda _uid: 'UTC'))
        stack.enter_context(patch.object(agentic, '_get_agentic_qa_prompt', lambda *_args, **_kwargs: 'SYSTEM'))
        stack.enter_context(patch.object(agentic, 'load_app_tools', lambda _uid: []))
        stack.enter_context(patch.object(agentic, 'get_current_datetime_block', lambda _uid, tz=None: ''))
        stack.enter_context(patch.object(agentic, '_convert_tools', lambda _core, _app: ([], {})))
        stack.enter_context(patch.object(agentic, '_messages_to_anthropic', lambda _messages: []))
        stack.enter_context(patch.object(agentic, '_inject_current_datetime', lambda messages, _block: messages))
        stack.enter_context(patch.object(agentic, '_run_anthropic_agent_stream', producer))
        return [
            chunk
            async for chunk in agentic.execute_agentic_chat_stream(
                'uid1', [], app=None, callback_data={}, chat_session=None
            )
        ]


async def test_has_file_context_offloads_llm_call_off_loop():
    """_has_file_context must run the synchronous retrieve_is_file_question in an executor,
    not inline on the event loop."""
    loop_thread = threading.current_thread()
    ran_on = {}

    def fake_is_file_question(question):
        ran_on['thread'] = threading.current_thread()
        return True

    # File attached earlier in the session + a text-only follow-up → the retrieve path.
    session = SimpleNamespace(id="s1", file_ids=["f1"])
    last = SimpleNamespace(files_id=None, text="what's in the document I shared?")

    with patch.object(graph, 'retrieve_is_file_question', fake_is_file_question):
        result = await graph._has_file_context(last, session)

    assert result is True
    assert 'thread' in ran_on, "retrieve_is_file_question was not called"
    assert ran_on['thread'] is not loop_thread, "retrieve_is_file_question must run off the event-loop thread"


async def test_agentic_setup_reads_run_off_loop():
    """execute_agentic_chat_stream must offload its blocking Firestore setup reads
    (get_user_timezone, _get_agentic_qa_prompt, load_app_tools) so they don't block the
    event loop before the first await."""
    loop_thread = threading.current_thread()
    threads = {}

    def rec(name, retval):
        def _fn(*args, **kwargs):
            threads[name] = threading.current_thread()
            return retval

        return _fn

    async def fake_agent_stream(
        system_prompt,
        anthropic_messages,
        tool_schemas,
        tool_registry,
        callback,
        full_response,
        safety_guard,
        configurable,
    ):
        # End the stream immediately so the generator's queue loop breaks.
        await callback.queue.put(None)

    with patch.object(agentic, 'get_user_timezone', rec('tz', 'UTC')), patch.object(
        agentic, '_get_agentic_qa_prompt', rec('prompt', 'SYSTEM')
    ), patch.object(agentic, 'load_app_tools', rec('app_tools', [])), patch.object(
        agentic, 'get_current_datetime_block', lambda uid, tz=None: ''
    ), patch.object(
        agentic, '_convert_tools', lambda core, app: ([], {})
    ), patch.object(
        agentic, '_messages_to_anthropic', lambda messages: []
    ), patch.object(
        agentic, '_inject_current_datetime', lambda anthropic_messages, block: []
    ), patch.object(
        agentic, '_run_anthropic_agent_stream', fake_agent_stream
    ):
        chunks = []
        async for chunk in agentic.execute_agentic_chat_stream(
            'uid1', [], app=None, callback_data={}, chat_session=None
        ):
            chunks.append(chunk)

    for name in ('tz', 'prompt', 'app_tools'):
        assert name in threads, f"{name} setup helper was not called"
        assert threads[name] is not loop_thread, f"{name} setup read must run off the event-loop thread"


async def test_callback_preserves_langchain_persona_stream_contract():
    """The shared callback must still bridge LangChain token/end events for persona chat."""
    callback = agentic.AsyncStreamingCallback()

    await callback.on_llm_new_token('hello')
    await callback.on_llm_end(None)

    assert await callback.queue.get() == 'data: hello'
    assert await callback.queue.get() is None


async def test_persona_stream_forwards_langchain_callbacks_and_terminates():
    """Persona chat must yield tokens and its terminal sentinel through the real stream path."""

    class FakeLLM:
        async def agenerate(self, *, callbacks, **_kwargs):
            await callbacks[0].on_llm_new_token('hello')
            await callbacks[0].on_llm_end(None)

    callback_data = {}
    app = SimpleNamespace(id='persona-1', name='Persona', persona_prompt='SYSTEM')
    with patch.object(graph, 'get_llm', lambda *_args, **_kwargs: FakeLLM()), patch.object(
        graph, 'get_chat_tracer_callbacks', lambda **_kwargs: []
    ), patch.object(graph, 'track_usage', lambda *_args, **_kwargs: nullcontext()):
        chunks = [
            chunk
            async for chunk in graph.execute_persona_chat_stream(
                'uid1', [], app, callback_data=callback_data, chat_session=None
            )
        ]

    assert chunks == ['data: hello', None]
    assert callback_data['answer'] == 'hello'


async def test_persona_callback_drain_cancels_a_silent_producer():
    """Persona/file queue consumers use the same bounded lifecycle as default chat."""
    callback = agentic.AsyncStreamingCallback()
    cancelled = asyncio.Event()

    async def stalled_producer():
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cancelled.set()
            raise

    task = asyncio.create_task(stalled_producer())
    with patch.object(graph, 'AGENT_STREAM_FIRST_EVENT_TIMEOUT_SECONDS', 0.01), patch.object(
        agentic, 'AGENT_STREAM_CANCEL_GRACE_SECONDS', 0.05
    ):
        chunks = [chunk async for chunk in graph._drain_chat_callback(callback, task, route='persona')]

    assert chunks == [f'error: {agentic.AGENT_STREAM_TIMEOUT_MESSAGE}']
    assert cancelled.is_set()


async def test_agentic_stream_cancels_a_silent_producer_before_the_proxy_deadline():
    """A stalled provider/tool produces a terminal SSE error instead of an unbounded queue wait."""
    cancelled = asyncio.Event()

    async def stalled_producer(*_args, **_kwargs):
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cancelled.set()
            raise

    with patch.object(agentic, 'AGENT_STREAM_FIRST_EVENT_TIMEOUT_SECONDS', 0.01), patch.object(
        agentic, 'AGENT_STREAM_CANCEL_GRACE_SECONDS', 0.05
    ):
        chunks = await _collect_agentic_chunks(stalled_producer)

    assert chunks == [f'error: {agentic.AGENT_STREAM_TIMEOUT_MESSAGE}']
    assert cancelled.is_set()


async def test_agentic_stream_surfaces_a_producer_crash_without_waiting_for_idle_timeout():
    """A producer exception before callback.end() immediately terminates the SSE stream."""

    async def crashing_producer(*_args, **_kwargs):
        raise RuntimeError('simulated provider failure')

    chunks = await _collect_agentic_chunks(crashing_producer)

    assert chunks == [f'error: {agentic.AGENT_STREAM_FAILURE_MESSAGE}']


async def test_agentic_stream_treats_a_cancelled_producer_as_a_failure():
    """Only a client cancellation is silent; a producer cancellation is a terminal SSE error."""

    async def cancelled_producer(*_args, **_kwargs):
        raise asyncio.CancelledError

    chunks = await _collect_agentic_chunks(cancelled_producer)

    assert chunks == [f'error: {agentic.AGENT_STREAM_FAILURE_MESSAGE}']
