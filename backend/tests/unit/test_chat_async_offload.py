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
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

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
import utils.other.chat_file as chat_file  # noqa: E402
from models.users import (  # noqa: E402
    LOCATION_CONTEXT_DISCLOSED_PROVIDERS,
    LOCATION_CONTEXT_PURPOSE,
    LocationContextConsent,
    LocationContextConsentStatus,
)


async def _collect_agentic_chunks(producer, callback_data=None):
    """Drive the real public stream with deterministic setup dependencies."""
    if callback_data is None:
        callback_data = {}
    with ExitStack() as stack:
        stack.enter_context(patch.object(agentic, 'get_user_timezone', lambda _uid: 'UTC'))
        stack.enter_context(patch.object(agentic, '_get_agentic_qa_prompt', lambda *_args, **_kwargs: 'SYSTEM'))
        stack.enter_context(patch.object(agentic, 'load_app_tools', lambda _uid: []))
        stack.enter_context(
            patch.object(agentic, 'get_current_datetime_block', lambda _uid, tz=None, location=None: '')
        )
        stack.enter_context(patch.object(agentic, '_convert_tools', lambda _core, _app: ([], {})))
        stack.enter_context(patch.object(agentic, '_messages_to_anthropic', lambda _messages: []))
        stack.enter_context(patch.object(agentic, '_inject_current_datetime', lambda messages, _block: messages))
        stack.enter_context(patch.object(agentic, '_run_anthropic_agent_stream', producer))
        return [
            chunk
            async for chunk in agentic.execute_agentic_chat_stream(
                'uid1', [], app=None, callback_data=callback_data, chat_session=None
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


def _location_context_consent(*, status=LocationContextConsentStatus.granted, expires_at=None):
    now = datetime.now(timezone.utc)
    return LocationContextConsent(
        status=status,
        purpose=LOCATION_CONTEXT_PURPOSE,
        disclosed_providers=LOCATION_CONTEXT_DISCLOSED_PROVIDERS,
        granted_at=now,
        expires_at=expires_at or now + timedelta(days=1),
        revoked_at=now if status is LocationContextConsentStatus.revoked else None,
    )


async def test_mobile_header_alone_never_reads_coordinates_or_discloses_location():
    """A caller-controlled mobile header is not consent for location disclosure."""
    cached_coordinates = AsyncMock()
    maps_city = AsyncMock()

    async def fake_run_blocking(_executor, function, _uid):
        assert function is agentic.get_user_location_context_consent
        return None

    with patch.object(agentic, 'run_blocking', fake_run_blocking), patch.object(
        agentic, 'get_cached_user_geolocation', cached_coordinates
    ), patch.object(agentic, 'async_get_google_maps_city', maps_city):
        assert await agentic.get_mobile_city('uid1', 'ios') is None

    cached_coordinates.assert_not_awaited()
    maps_city.assert_not_awaited()


async def test_valid_location_context_opt_in_allows_city_only_prompt_metadata():
    """A valid server-owned disclosure permits a city label, never precise coordinates."""
    consent = _location_context_consent()

    async def fake_run_blocking(_executor, function, _uid):
        if function is agentic.get_user_location_context_consent:
            return consent
        if function is agentic.get_cached_user_geolocation:
            return {'latitude': 40.7128, 'longitude': -74.006}
        raise AssertionError(f'unexpected blocking call: {function}')

    maps_city = AsyncMock(return_value='New York, New York, United States')
    with patch.object(agentic, 'run_blocking', fake_run_blocking), patch.object(
        agentic, 'async_get_google_maps_city', maps_city
    ):
        city = await agentic.get_mobile_city('uid1', 'android')

    assert city == 'New York, New York, United States'
    maps_city.assert_awaited_once_with(40.7128, -74.006)
    provider_messages = agentic._inject_current_datetime(
        [{'role': 'user', 'content': 'What should I do nearby?'}],
        agentic.get_current_datetime_block('uid1', tz='UTC', location=city),
    )
    provider_payload = str(provider_messages)
    assert 'New York, New York, United States' in provider_payload
    assert '40.7128' not in provider_payload
    assert '-74.006' not in provider_payload


async def test_revoked_or_expired_location_context_never_reads_coordinates_or_calls_maps():
    for consent in (
        _location_context_consent(status=LocationContextConsentStatus.revoked),
        _location_context_consent(expires_at=datetime.now(timezone.utc) - timedelta(seconds=1)),
    ):
        cached_coordinates = AsyncMock()
        maps_city = AsyncMock()

        async def fake_run_blocking(_executor, function, _uid):
            assert function is agentic.get_user_location_context_consent
            return consent

        with patch.object(agentic, 'run_blocking', fake_run_blocking), patch.object(
            agentic, 'get_cached_user_geolocation', cached_coordinates
        ), patch.object(agentic, 'async_get_google_maps_city', maps_city):
            assert await agentic.get_mobile_city('uid1', 'ios') is None

        cached_coordinates.assert_not_awaited()
        maps_city.assert_not_awaited()


async def test_invalid_cached_coordinates_never_reach_maps_after_opt_in():
    consent = _location_context_consent()
    maps_city = AsyncMock()

    async def fake_run_blocking(_executor, function, _uid):
        if function is agentic.get_user_location_context_consent:
            return consent
        if function is agentic.get_cached_user_geolocation:
            return {'latitude': 90.1, 'longitude': 0}
        raise AssertionError(f'unexpected blocking call: {function}')

    with patch.object(agentic, 'run_blocking', fake_run_blocking), patch.object(
        agentic, 'async_get_google_maps_city', maps_city
    ):
        assert await agentic.get_mobile_city('uid1', 'ios') is None

    maps_city.assert_not_awaited()


async def test_mobile_city_context_rejects_non_mobile_platform_before_cache_read():
    cached_coordinates = AsyncMock()
    with patch.object(agentic, 'get_cached_user_geolocation', cached_coordinates):
        assert await agentic.get_mobile_city('uid1', 'macos') is None

    cached_coordinates.assert_not_awaited()


async def test_chat_router_passes_metadata_to_every_interactive_path():
    message = SimpleNamespace(sender='human', text='What should I do?', files_id=['file1'])
    session = SimpleNamespace(id='session1', file_ids=['file1'])
    metadata = '<current_datetime>now</current_datetime>'
    seen = []

    async def stream(*_args, **kwargs):
        seen.append(kwargs['current_datetime_block'])
        yield None

    with patch.object(graph, '_current_prompt_metadata', AsyncMock(return_value=(metadata, 'UTC'))):
        persona = SimpleNamespace(id='persona1', is_a_persona=lambda: True)
        with patch.object(graph, 'execute_persona_chat_stream', stream):
            assert [chunk async for chunk in graph.execute_chat_stream('uid1', [message], app=persona)] == [None]
        with patch.object(graph, '_has_file_context', AsyncMock(return_value=True)), patch.object(
            graph, '_execute_file_chat_stream', stream
        ):
            assert [chunk async for chunk in graph.execute_chat_stream('uid1', [message], chat_session=session)] == [
                None
            ]
        with patch.object(graph, 'execute_agentic_chat_stream', stream):
            assert [chunk async for chunk in graph.execute_chat_stream('uid1', [message])] == [None]

    assert seen == [metadata, metadata, metadata]


async def test_chat_router_and_agentic_share_one_setup_deadline():
    """Router metadata must not stack a second full setup budget onto agentic setup."""
    message = SimpleNamespace(sender='human', text='hello', files_id=[])
    seen = {}

    async def capture_agentic(*_args, **kwargs):
        seen['setup_deadline_at'] = kwargs.get('setup_deadline_at')
        yield None

    before = asyncio.get_running_loop().time()
    with patch.object(graph, '_current_prompt_metadata', AsyncMock(return_value=('<dt/>', 'UTC'))), patch.object(
        graph, 'execute_agentic_chat_stream', capture_agentic
    ), patch.object(graph, 'AGENT_STREAM_SETUP_TIMEOUT_SECONDS', 25.0), patch.object(
        agentic, 'AGENT_STREAM_SETUP_TIMEOUT_SECONDS', 25.0
    ):
        assert [chunk async for chunk in graph.execute_chat_stream('uid1', [message])] == [None]
    after = asyncio.get_running_loop().time()

    deadline = seen.get('setup_deadline_at')
    assert isinstance(deadline, float)
    # Absolute deadline is ~25s from router start, not ~50s (two stacked budgets).
    assert before + 20.0 <= deadline <= after + 25.0


async def test_file_route_classification_shares_router_setup_deadline():
    """Existing session file IDs must classify under the remaining shared setup budget."""
    message = SimpleNamespace(sender='human', text='what is in the file?', files_id=[])
    session = SimpleNamespace(id='s1', file_ids=['f1'])
    agentic_calls = []

    async def slow_file_context(*_args, **_kwargs):
        await asyncio.sleep(0.05)
        return False

    async def capture_agentic(*_args, **_kwargs):
        agentic_calls.append(1)
        yield None

    with patch.object(graph, '_current_prompt_metadata', AsyncMock(return_value=('<dt/>', 'UTC'))), patch.object(
        graph, '_has_file_context', slow_file_context
    ), patch.object(graph, 'execute_agentic_chat_stream', capture_agentic), patch.object(
        graph, 'AGENT_STREAM_SETUP_TIMEOUT_SECONDS', 0.01
    ):
        chunks = [chunk async for chunk in graph.execute_chat_stream('uid1', [message], chat_session=session)]

    assert not agentic_calls, 'stalled file classification must not fall through to agentic after setup budget'
    assert chunks[0].startswith('error: ')
    assert chunks[-1] is None


def test_prompt_metadata_is_prepended_to_the_live_user_turn():
    assert graph._with_prompt_metadata('question', '<current_datetime>now</current_datetime>') == (
        '<current_datetime>now</current_datetime>\n\nquestion'
    )


async def test_prompt_metadata_falls_back_to_utc_when_context_lookup_fails():
    with patch.object(graph, 'run_blocking', AsyncMock(side_effect=RuntimeError('offline'))):
        metadata, tz = await graph._current_prompt_metadata('uid1', 'ios')

    assert tz == 'UTC'
    assert 'Current date time in UTC:' in metadata


def _file_chat_tool_for_stream_test():
    """Create a FileChatTool without its production Firestore constructor for a hermetic stream test."""
    tool = object.__new__(chat_file.FileChatTool)
    tool.uid = 'uid1'
    tool.chat_session_id = 'session1'
    tool.thread_id = None
    tool.assistant_id = None
    return tool


async def test_file_assistants_stream_runs_setup_and_sync_callbacks_off_loop():
    """The real non-vision file stream keeps the loop responsive and bridges worker callbacks."""
    loop = asyncio.get_running_loop()
    loop_thread = threading.current_thread()
    ask_started = asyncio.Event()
    worker_finished = asyncio.Event()
    release_worker = threading.Event()
    worker_threads = {}
    tool = _file_chat_tool_for_stream_test()
    callback = agentic.AsyncStreamingCallback()

    def fake_ensure(self):
        worker_threads['ensure'] = threading.current_thread()
        self.thread_id = 'thread1'
        self.assistant_id = 'assistant1'

    def blocking_ask(self, _uid, _question, _file_ids, _thread_id, _assistant_id, stream_callback):
        worker_threads['ask'] = threading.current_thread()
        loop.call_soon_threadsafe(ask_started.set)
        try:
            assert release_worker.wait(timeout=0.5), 'test did not release the blocking Assistants stream'
            stream_callback.put_data_nowait('file answer')
            return 'file answer'
        finally:
            stream_callback.end_nowait()
            loop.call_soon_threadsafe(worker_finished.set)

    with patch.object(chat_file.chat_db, 'get_chat_files_desc', lambda *_args, **_kwargs: []), patch.object(
        chat_file.FileChatTool, '_ensure_thread_and_assistant', fake_ensure
    ), patch.object(chat_file.FileChatTool, 'ask_stream', blocking_ask):
        task = asyncio.create_task(tool.process_chat_with_file_stream('summarize', ['file1'], callback))
        await asyncio.wait_for(ask_started.wait(), timeout=0.5)

        health_check_ran = asyncio.Event()
        loop.call_soon(health_check_ran.set)
        await asyncio.wait_for(health_check_ran.wait(), timeout=0.1)
        assert not task.done(), 'the worker-side stream should still be pending while the loop serves other work'

        release_worker.set()
        assert await task == 'file answer'
        await asyncio.wait_for(worker_finished.wait(), timeout=0.5)

    assert worker_threads['ensure'] is not loop_thread
    assert worker_threads['ask'] is not loop_thread
    assert await callback.queue.get() == 'data: file answer'
    assert await callback.queue.get() is None


async def test_file_stream_deadline_fires_while_sync_assistants_stream_is_off_loop():
    """A blocked Assistants iterator yields the terminal SSE error instead of freezing its deadline."""
    loop = asyncio.get_running_loop()
    ask_started = asyncio.Event()
    worker_finished = asyncio.Event()
    release_worker = threading.Event()
    tool = _file_chat_tool_for_stream_test()

    def fake_ensure(self):
        self.thread_id = 'thread1'
        self.assistant_id = 'assistant1'

    def blocking_ask(self, _uid, _question, _file_ids, _thread_id, _assistant_id, stream_callback):
        loop.call_soon_threadsafe(ask_started.set)
        try:
            assert release_worker.wait(timeout=0.5), 'test did not release the blocking Assistants stream'
            return ''
        finally:
            stream_callback.end_nowait()
            loop.call_soon_threadsafe(worker_finished.set)

    message = SimpleNamespace(files_id=['file1'], text='summarize')
    session = SimpleNamespace(id='session1', file_ids=['file1'])
    callback_data = {}

    async def collect_file_stream():
        return [
            chunk
            async for chunk in graph._execute_file_chat_stream('uid1', [message], session, callback_data=callback_data)
        ]

    with patch.object(graph, 'FileChatTool', lambda *_args: tool), patch.object(
        chat_file.chat_db, 'get_chat_files_desc', lambda *_args, **_kwargs: []
    ), patch.object(chat_file.FileChatTool, '_ensure_thread_and_assistant', fake_ensure), patch.object(
        chat_file.FileChatTool, 'ask_stream', blocking_ask
    ), patch.object(
        graph, 'AGENT_STREAM_FIRST_EVENT_TIMEOUT_SECONDS', 0.01
    ), patch.object(
        agentic, 'AGENT_STREAM_CANCEL_GRACE_SECONDS', 0.05
    ):
        stream_task = asyncio.create_task(collect_file_stream())
        await asyncio.wait_for(ask_started.wait(), timeout=0.5)
        chunks = await asyncio.wait_for(stream_task, timeout=0.5)
        release_worker.set()
        await asyncio.wait_for(worker_finished.wait(), timeout=0.5)

    assert chunks == [f'error: {agentic.AGENT_STREAM_TIMEOUT_MESSAGE}', None]
    assert callback_data['error'] == 'stream_failure'
    assert callback_data['answer'] == agentic.AGENT_STREAM_TIMEOUT_MESSAGE


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
        agentic, 'get_current_datetime_block', lambda uid, tz=None, location=None: ''
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

    assert chunks[0] == f'think: {agentic.AGENT_STREAM_SETUP_PROGRESS}'
    assert f'error: {agentic.AGENT_STREAM_TIMEOUT_MESSAGE}' in chunks
    assert chunks[-1] is None
    assert cancelled.is_set()


async def test_agentic_stream_keeps_an_answer_streamed_before_the_deadline():
    """A bounded stop must persist what the user already watched arrive, not discard it."""
    callback_data = {}

    async def stalls_after_answering(*args, **_kwargs):
        callback, full_response = args[4], args[5]
        await callback.put_data('the answer so far')
        full_response.append('the answer so far')
        await asyncio.Event().wait()

    with patch.object(agentic, 'AGENT_STREAM_PROGRESS_HEARTBEAT_SECONDS', 0.01), patch.object(
        agentic, 'AGENT_STREAM_MAX_DURATION_SECONDS', 0.05
    ), patch.object(agentic, 'AGENT_STREAM_CANCEL_GRACE_SECONDS', 0.05):
        chunks = await _collect_agentic_chunks(stalls_after_answering, callback_data)

    # The terminal None is what makes the router persist instead of writing a
    # canned error over the streamed answer.
    assert chunks[0] == f'think: {agentic.AGENT_STREAM_SETUP_PROGRESS}'
    assert chunks[-1] is None
    assert f'error: {agentic.AGENT_STREAM_TIMEOUT_MESSAGE}' not in chunks
    assert callback_data['answer'] == 'the answer so far'
    assert callback_data['error'] == 'idle_timeout'


async def test_agentic_stream_still_errors_when_nothing_was_streamed():
    """With no partial answer there is nothing to keep, so the terminal error stands."""
    callback_data = {}

    async def stalled_producer(*_args, **_kwargs):
        await asyncio.Event().wait()

    with patch.object(agentic, 'AGENT_STREAM_FIRST_EVENT_TIMEOUT_SECONDS', 0.01), patch.object(
        agentic, 'AGENT_STREAM_CANCEL_GRACE_SECONDS', 0.05
    ):
        chunks = await _collect_agentic_chunks(stalled_producer, callback_data)

    assert chunks[0] == f'think: {agentic.AGENT_STREAM_SETUP_PROGRESS}'
    assert f'error: {agentic.AGENT_STREAM_TIMEOUT_MESSAGE}' in chunks
    assert chunks[-1] is None
    # Typed timeout is persisted through the normal done: contract so the router
    # does not append the generic canned sorry bubble.
    assert callback_data['answer'] == agentic.AGENT_STREAM_TIMEOUT_MESSAGE
    assert callback_data['error'] == 'idle_timeout'


async def test_agentic_stream_keeps_an_answer_streamed_before_a_producer_crash():
    """A provider failure mid-answer must not discard the tokens already delivered."""
    callback_data = {}

    async def crashes_after_answering(*args, **_kwargs):
        callback, full_response = args[4], args[5]
        await callback.put_data('partial before crash')
        full_response.append('partial before crash')
        raise RuntimeError('simulated provider failure')

    chunks = await _collect_agentic_chunks(crashes_after_answering, callback_data)

    assert chunks[0] == f'think: {agentic.AGENT_STREAM_SETUP_PROGRESS}'
    assert chunks[-1] is None
    assert f'error: {agentic.AGENT_STREAM_FAILURE_MESSAGE}' not in chunks
    assert callback_data['answer'] == 'partial before crash'
    assert callback_data['error'] == 'RuntimeError'


async def test_agentic_stream_surfaces_a_producer_crash_without_waiting_for_idle_timeout():
    """A producer exception before callback.end() immediately terminates the SSE stream."""

    async def crashing_producer(*_args, **_kwargs):
        raise RuntimeError('simulated provider failure')

    chunks = await _collect_agentic_chunks(crashing_producer)

    assert chunks[0] == f'think: {agentic.AGENT_STREAM_SETUP_PROGRESS}'
    assert f'error: {agentic.AGENT_STREAM_FAILURE_MESSAGE}' in chunks
    assert chunks[-1] is None


async def test_agentic_stream_treats_a_cancelled_producer_as_a_failure():
    """Only a client cancellation is silent; a producer cancellation is a terminal SSE error."""

    async def cancelled_producer(*_args, **_kwargs):
        raise asyncio.CancelledError

    chunks = await _collect_agentic_chunks(cancelled_producer)

    assert chunks[0] == f'think: {agentic.AGENT_STREAM_SETUP_PROGRESS}'
    assert f'error: {agentic.AGENT_STREAM_FAILURE_MESSAGE}' in chunks
    assert chunks[-1] is None


async def test_agentic_setup_budget_does_not_consume_first_event_deadline():
    """Multi-second setup must not silently exhaust the post-setup TTFT window."""
    callback_data = {}
    # setup_delay must exceed FIRST_EVENT_TIMEOUT so a shared clock would
    # exhaust the producer's budget.  The first-event window is widened well
    # beyond the 30ms that can flake under CI scheduling contention: the
    # producer does almost no work, but it still needs to be scheduled, emit,
    # and end within the budget.
    setup_delay = 0.2

    def slow_tz(_uid):
        import time

        time.sleep(setup_delay)
        return 'UTC'

    async def quick_producer(*args, **_kwargs):
        callback = args[4]
        await callback.put_data('hello')
        args[5].append('hello')
        await callback.end()

    with patch.object(agentic, 'get_user_timezone', slow_tz), patch.object(
        agentic, '_get_agentic_qa_prompt', lambda *_args, **_kwargs: 'SYSTEM'
    ), patch.object(agentic, 'load_app_tools', lambda _uid: []), patch.object(
        agentic, 'get_current_datetime_block', lambda _uid, tz=None, location=None: ''
    ), patch.object(
        agentic, '_convert_tools', lambda _core, _app: ([], {})
    ), patch.object(
        agentic, '_messages_to_anthropic', lambda _messages: []
    ), patch.object(
        agentic, '_inject_current_datetime', lambda messages, _block: messages
    ), patch.object(
        agentic, '_run_anthropic_agent_stream', quick_producer
    ), patch.object(
        agentic, 'AGENT_STREAM_SETUP_TIMEOUT_SECONDS', 2.0
    ), patch.object(
        agentic, 'AGENT_STREAM_FIRST_EVENT_TIMEOUT_SECONDS', 0.1
    ):
        # If setup shared the first-event clock, the 200ms setup would leave no
        # budget for the producer (100ms window) and this would idle-timeout before 'hello'.
        chunks = [
            chunk
            async for chunk in agentic.execute_agentic_chat_stream(
                'uid1', [], app=None, callback_data=callback_data, chat_session=None
            )
        ]

    assert chunks[0] == f'think: {agentic.AGENT_STREAM_SETUP_PROGRESS}'
    assert 'data: hello' in chunks
    assert callback_data.get('answer') == 'hello'
    assert 'error' not in callback_data


async def test_file_chat_gateway_block_is_typed_not_generic_canned():
    """Under gateway feature mode, file chat must fail with a typed user-safe message."""
    from utils.llm.gateway_client import GatewayDirectModelSurfaceBlocked

    message = SimpleNamespace(files_id=['file1'], text='summarize')
    session = SimpleNamespace(id='session1', file_ids=['file1'])
    callback_data = {}

    def blocked_tool(_uid, _session_id):
        raise GatewayDirectModelSurfaceBlocked('file_chat.openai_files_assistants_vision')

    with patch.object(graph, 'FileChatTool', blocked_tool):
        chunks = [
            chunk
            async for chunk in graph._execute_file_chat_stream(
                'uid-gateway', [message], session, callback_data=callback_data
            )
        ]

    assert chunks == [f'error: {agentic.FILE_CHAT_GATEWAY_BLOCKED_MESSAGE}', None]
    assert callback_data['error'] == 'file_chat_gateway_blocked'
    assert callback_data['answer'] == agentic.FILE_CHAT_GATEWAY_BLOCKED_MESSAGE
    assert callback_data['route'] == 'file'
    assert agentic.AGENT_STREAM_FAILURE_MESSAGE not in (chunks[0] or '')
