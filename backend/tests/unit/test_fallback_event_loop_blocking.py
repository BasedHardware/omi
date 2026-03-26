"""Tests for conversation fallback event loop blocking fix (#6061).

Verifies that _create_conversation_fallback offloads heavy processing to a thread
via asyncio.to_thread() and that the pod-level semaphore caps concurrency.
"""

import asyncio
import threading
import time
from unittest.mock import MagicMock

import pytest

# ---------------------------------------------------------------------------
# Source-level regression tests
# ---------------------------------------------------------------------------


def _read_transcribe_source():
    """Read routers/transcribe.py source code."""
    import pathlib

    src = pathlib.Path(__file__).resolve().parents[2] / 'routers' / 'transcribe.py'
    return src.read_text()


def test_fallback_uses_asyncio_to_thread():
    """_create_conversation_fallback must use asyncio.to_thread to offload blocking work."""
    source = _read_transcribe_source()
    fallback_pos = source.find('async def _create_conversation_fallback')
    assert fallback_pos > 0, "Cannot find _create_conversation_fallback"
    fallback_body = source[fallback_pos : fallback_pos + 800]
    assert (
        'asyncio.to_thread' in fallback_body
    ), "_create_conversation_fallback must use asyncio.to_thread to avoid blocking the event loop"


def test_fallback_uses_semaphore():
    """_create_conversation_fallback must use FALLBACK_PROCESS_SEMAPHORE to cap concurrency."""
    source = _read_transcribe_source()
    fallback_pos = source.find('async def _create_conversation_fallback')
    assert fallback_pos > 0
    fallback_body = source[fallback_pos : fallback_pos + 800]
    assert (
        'FALLBACK_PROCESS_SEMAPHORE' in fallback_body
    ), "_create_conversation_fallback must use FALLBACK_PROCESS_SEMAPHORE"


def test_process_fallback_sync_exists_at_module_level():
    """_process_fallback_sync must be a module-level function (not nested in closure)."""
    source = _read_transcribe_source()
    pos = source.find('def _process_fallback_sync(')
    assert pos > 0, "Missing _process_fallback_sync function"
    # Must be at module level (no leading whitespace beyond 0)
    line_start = source.rfind('\n', 0, pos) + 1
    leading = source[line_start:pos]
    assert leading.strip() == '', "_process_fallback_sync must be at module level (no indentation)"


def test_process_fallback_sync_calls_process_conversation():
    """_process_fallback_sync must call process_conversation."""
    source = _read_transcribe_source()
    pos = source.find('def _process_fallback_sync(')
    assert pos > 0
    # Find the end of the function (next def at same or lower indent)
    next_def = source.find('\ndef ', pos + 1)
    func_body = source[pos:next_def] if next_def > 0 else source[pos : pos + 800]
    assert 'process_conversation(' in func_body, "_process_fallback_sync must call process_conversation"
    assert (
        'trigger_external_integrations(' in func_body
    ), "_process_fallback_sync must call trigger_external_integrations"


def test_no_direct_process_conversation_in_fallback():
    """_create_conversation_fallback must NOT call process_conversation directly (must use thread)."""
    source = _read_transcribe_source()
    fallback_pos = source.find('async def _create_conversation_fallback')
    assert fallback_pos > 0
    # Find next function definition to bound the search
    next_func = source.find('\n    async def ', fallback_pos + 1)
    if next_func < 0:
        next_func = fallback_pos + 800
    fallback_body = source[fallback_pos:next_func]
    assert (
        'process_conversation(uid' not in fallback_body
    ), "_create_conversation_fallback must not call process_conversation directly — use asyncio.to_thread"


def test_semaphore_constant_exists():
    """FALLBACK_PROCESS_SEMAPHORE and FALLBACK_PROCESS_MAX_CONCURRENCY must be defined."""
    source = _read_transcribe_source()
    assert 'FALLBACK_PROCESS_MAX_CONCURRENCY' in source
    assert 'FALLBACK_PROCESS_SEMAPHORE' in source


def test_fallback_sync_handles_geolocation():
    """_process_fallback_sync must handle geolocation before processing."""
    source = _read_transcribe_source()
    pos = source.find('def _process_fallback_sync(')
    assert pos > 0
    next_def = source.find('\ndef ', pos + 1)
    func_body = source[pos:next_def] if next_def > 0 else source[pos : pos + 800]
    assert 'get_cached_user_geolocation' in func_body, "_process_fallback_sync must call get_cached_user_geolocation"
    assert 'get_google_maps_location' in func_body, "_process_fallback_sync must call get_google_maps_location"


# ---------------------------------------------------------------------------
# Behavioral tests — test the threading/semaphore patterns directly
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_to_thread_offloads_blocking_work():
    """asyncio.to_thread must run the sync function in a different thread than the event loop."""
    event_loop_thread = threading.current_thread().ident
    worker_thread_id = None

    def blocking_work(uid, language, conversation, session_id):
        nonlocal worker_thread_id
        worker_thread_id = threading.current_thread().ident
        time.sleep(0.05)  # Simulate blocking work
        return conversation, []

    mock_conversation = MagicMock()
    await asyncio.to_thread(blocking_work, 'uid', 'en', mock_conversation, 'sess')

    assert worker_thread_id is not None, "Worker thread ID should be set"
    assert worker_thread_id != event_loop_thread, "Blocking work must run in a different thread than the event loop"


@pytest.mark.asyncio
async def test_event_loop_remains_responsive_during_thread_offload():
    """The event loop must remain responsive while blocking work runs in a thread."""
    ticker_count = 0

    async def ticker():
        nonlocal ticker_count
        for _ in range(20):
            await asyncio.sleep(0.01)
            ticker_count += 1

    def slow_sync(uid, language, conversation, session_id):
        time.sleep(0.15)  # Simulate 150ms of blocking work
        return conversation, []

    mock_conversation = MagicMock()

    async def run_fallback():
        return await asyncio.to_thread(slow_sync, 'uid', 'en', mock_conversation, 'sess')

    # Run ticker and fallback concurrently
    await asyncio.gather(ticker(), run_fallback())

    assert ticker_count >= 10, f"Event loop ticker only ran {ticker_count}/20 times — event loop was blocked"


@pytest.mark.asyncio
async def test_semaphore_caps_concurrency():
    """asyncio.Semaphore must limit concurrent thread executions."""
    max_concurrent = 0
    current_concurrent = 0
    lock = threading.Lock()

    def counting_sync(uid, language, conversation, session_id):
        nonlocal max_concurrent, current_concurrent
        with lock:
            current_concurrent += 1
            if current_concurrent > max_concurrent:
                max_concurrent = current_concurrent
        time.sleep(0.1)
        with lock:
            current_concurrent -= 1
        return conversation, []

    # Use a semaphore with max=1 for testing
    test_semaphore = asyncio.Semaphore(1)

    async def run_one():
        async with test_semaphore:
            return await asyncio.to_thread(counting_sync, 'uid', 'en', MagicMock(), 'sess')

    # Launch 4 concurrent fallback tasks
    await asyncio.gather(*[run_one() for _ in range(4)])

    assert max_concurrent == 1, f"Max concurrent was {max_concurrent}, expected 1 with semaphore(1)"


@pytest.mark.asyncio
async def test_semaphore_2_allows_two_concurrent():
    """Semaphore(2) should allow exactly 2 concurrent executions."""
    max_concurrent = 0
    current_concurrent = 0
    lock = threading.Lock()

    def counting_sync(uid, language, conversation, session_id):
        nonlocal max_concurrent, current_concurrent
        with lock:
            current_concurrent += 1
            if current_concurrent > max_concurrent:
                max_concurrent = current_concurrent
        time.sleep(0.1)
        with lock:
            current_concurrent -= 1
        return conversation, []

    test_semaphore = asyncio.Semaphore(2)

    async def run_one():
        async with test_semaphore:
            return await asyncio.to_thread(counting_sync, 'uid', 'en', MagicMock(), 'sess')

    await asyncio.gather(*[run_one() for _ in range(6)])

    assert max_concurrent == 2, f"Max concurrent was {max_concurrent}, expected 2 with semaphore(2)"


@pytest.mark.asyncio
async def test_exception_propagates_from_thread():
    """Exceptions from the thread worker must propagate to the caller for error handling."""

    def failing_sync(uid, language, conversation, session_id):
        raise RuntimeError("OpenAI API unavailable")

    with pytest.raises(RuntimeError, match="OpenAI API unavailable"):
        await asyncio.to_thread(failing_sync, 'uid', 'en', MagicMock(), 'sess')


@pytest.mark.asyncio
async def test_semaphore_releases_on_exception():
    """Semaphore must be released even when the thread worker raises."""
    test_semaphore = asyncio.Semaphore(1)
    call_count = 0

    def failing_sync(uid, language, conversation, session_id):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise RuntimeError("fail first time")
        return conversation, []

    # First call fails
    with pytest.raises(RuntimeError):
        async with test_semaphore:
            await asyncio.to_thread(failing_sync, 'uid', 'en', MagicMock(), 'sess')

    # Second call should succeed (semaphore released despite exception)
    async with test_semaphore:
        result = await asyncio.to_thread(failing_sync, 'uid', 'en', MagicMock(), 'sess')

    assert result is not None, "Semaphore must be released after exception for retry"
    assert call_count == 2


# ---------------------------------------------------------------------------
# Status transition and cancellation tests
# ---------------------------------------------------------------------------


def test_status_transition_skipped_when_already_processing():
    """_create_conversation_fallback must NOT send memory_processing_started if already processing.

    Source-level: the `if conversation.status != ConversationStatus.processing` guard
    must exist in the fallback function.
    """
    source = _read_transcribe_source()
    fallback_pos = source.find('async def _create_conversation_fallback')
    assert fallback_pos > 0
    next_func = source.find('\n    async def ', fallback_pos + 1)
    fallback_body = source[fallback_pos:next_func] if next_func > 0 else source[fallback_pos : fallback_pos + 800]
    assert (
        'ConversationStatus.processing' in fallback_body
    ), "Fallback must check conversation.status before sending processing event"


def test_discard_path_on_exception():
    """On exception, conversation must be discarded and memory_created still sent.

    Source-level: set_conversation_as_discarded must appear in the except block.
    """
    source = _read_transcribe_source()
    fallback_pos = source.find('async def _create_conversation_fallback')
    assert fallback_pos > 0
    next_func = source.find('\n    async def ', fallback_pos + 1)
    fallback_body = source[fallback_pos:next_func] if next_func > 0 else source[fallback_pos : fallback_pos + 800]
    assert 'set_conversation_as_discarded' in fallback_body, "Exception path must discard the conversation"
    assert 'memory_created' in fallback_body, "memory_created event must be sent even on error (with empty messages)"


@pytest.mark.asyncio
async def test_cancellation_during_semaphore_wait():
    """Task cancelled while waiting on semaphore must raise CancelledError."""
    semaphore = asyncio.Semaphore(1)
    # Hold the semaphore so the second task has to wait
    await semaphore.acquire()

    async def wait_for_semaphore():
        async with semaphore:
            return "acquired"

    task = asyncio.create_task(wait_for_semaphore())
    await asyncio.sleep(0.01)  # Let it start waiting
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task

    # Release the semaphore — it should still be usable
    semaphore.release()
    async with semaphore:
        pass  # Semaphore still functional after cancellation


@pytest.mark.asyncio
async def test_cancellation_during_to_thread():
    """Task cancelled during to_thread — CancelledError propagates but thread keeps running.

    This documents the known behavior: asyncio.to_thread work is not truly
    cancellable, but CancelledError is raised to the awaiter.
    """
    started = threading.Event()
    finished = threading.Event()

    def long_work(uid, language, conversation, session_id):
        started.set()
        time.sleep(0.5)
        finished.set()
        return conversation, []

    task = asyncio.create_task(asyncio.to_thread(long_work, 'uid', 'en', MagicMock(), 'sess'))
    await asyncio.sleep(0.05)  # Let the thread start
    assert started.is_set(), "Thread should have started"

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    # Thread continues running (expected behavior — to_thread is not cancellable)
    finished.wait(timeout=2.0)
    assert finished.is_set(), "Thread continues even after task cancel (expected)"


@pytest.mark.asyncio
async def test_fallback_return_value_shape():
    """_process_fallback_sync must return (conversation, messages) tuple."""

    def sync_impl(uid, language, conversation, session_id):
        return conversation, ['msg1', 'msg2']

    mock_conversation = MagicMock()
    result = await asyncio.to_thread(sync_impl, 'uid', 'en', mock_conversation, 'sess')

    assert isinstance(result, tuple), "Return value must be a tuple"
    assert len(result) == 2, "Return value must be (conversation, messages)"
    conversation, messages = result
    assert conversation is mock_conversation
    assert messages == ['msg1', 'msg2']
