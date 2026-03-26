"""Tests for conversation deferred processing via Redis queue (#6061).

Verifies that backend-listen never runs heavy processing locally — instead,
conversations are enqueued to Redis for the pusher deferred queue worker.
"""

import asyncio
import json
import threading
import time
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Source-level regression tests — ensure architecture constraints hold
# ---------------------------------------------------------------------------


def _read_transcribe_source():
    """Read routers/transcribe.py source code."""
    import pathlib

    src = pathlib.Path(__file__).resolve().parents[2] / 'routers' / 'transcribe.py'
    return src.read_text()


def _read_pusher_source():
    """Read routers/pusher.py source code."""
    import pathlib

    src = pathlib.Path(__file__).resolve().parents[2] / 'routers' / 'pusher.py'
    return src.read_text()


def _read_pusher_main_source():
    """Read pusher/main.py source code."""
    import pathlib

    src = pathlib.Path(__file__).resolve().parents[2] / 'pusher' / 'main.py'
    return src.read_text()


def test_no_process_conversation_import_in_transcribe():
    """transcribe.py must NOT import process_conversation (all processing is in pusher)."""
    source = _read_transcribe_source()
    # It should only import retrieve_in_progress_conversation, NOT process_conversation
    assert 'import process_conversation' not in source or 'retrieve_in_progress_conversation' in source
    # The direct function call must never appear (except in string literals / comments)
    # Check that process_conversation( is not called as a function
    lines = source.split('\n')
    for line in lines:
        stripped = line.strip()
        if stripped.startswith('#') or stripped.startswith('"') or stripped.startswith("'"):
            continue
        assert (
            'process_conversation(uid' not in stripped
        ), f"transcribe.py must not call process_conversation() directly: {stripped}"


def test_no_trigger_external_integrations_in_transcribe():
    """transcribe.py must NOT import or call trigger_external_integrations."""
    source = _read_transcribe_source()
    assert (
        'trigger_external_integrations' not in source
    ), "transcribe.py must not import or call trigger_external_integrations — this belongs in pusher"


def test_no_create_conversation_fallback():
    """_create_conversation_fallback must not exist — replaced by Redis enqueue."""
    source = _read_transcribe_source()
    assert (
        '_create_conversation_fallback' not in source
    ), "_create_conversation_fallback must be removed — use _enqueue_conversation_for_deferred_processing"


def test_no_process_fallback_sync():
    """_process_fallback_sync must not exist — no heavy processing on listen."""
    source = _read_transcribe_source()
    assert (
        '_process_fallback_sync' not in source
    ), "_process_fallback_sync must be removed — no heavy processing on the listen event loop"


def test_no_fallback_semaphore():
    """FALLBACK_PROCESS_SEMAPHORE must not exist — not needed with Redis queue."""
    source = _read_transcribe_source()
    assert 'FALLBACK_PROCESS_SEMAPHORE' not in source
    assert 'FALLBACK_PROCESS_MAX_CONCURRENCY' not in source


def test_enqueue_function_exists_in_transcribe():
    """_enqueue_conversation_for_deferred_processing must exist in transcribe.py."""
    source = _read_transcribe_source()
    assert '_enqueue_conversation_for_deferred_processing' in source


def test_enqueue_calls_redis_enqueue():
    """_enqueue_conversation_for_deferred_processing must call redis_db.enqueue_deferred_conversation."""
    source = _read_transcribe_source()
    # Find the function body
    pos = source.find('_enqueue_conversation_for_deferred_processing')
    assert pos > 0
    func_body = source[pos : pos + 500]
    assert 'enqueue_deferred_conversation' in func_body


# ---------------------------------------------------------------------------
# Redis queue function tests
# ---------------------------------------------------------------------------


def test_redis_enqueue_deferred_conversation():
    """enqueue_deferred_conversation must push to Redis list with dedup."""
    from database import redis_db

    assert hasattr(redis_db, 'enqueue_deferred_conversation')
    assert hasattr(redis_db, 'dequeue_deferred_conversation')
    assert hasattr(redis_db, 'get_deferred_queue_length')


def test_redis_ack_nack_recover_exist():
    """ack, nack, and recover functions must exist for crash-safe processing."""
    from database import redis_db

    assert hasattr(redis_db, 'ack_deferred_conversation')
    assert hasattr(redis_db, 'nack_deferred_conversation')
    assert hasattr(redis_db, 'recover_deferred_processing')


def test_redis_queue_key_defined():
    """DEFERRED_CONVERSATION_QUEUE_KEY and PROCESSING_KEY must be defined in redis_db."""
    from database import redis_db

    assert hasattr(redis_db, 'DEFERRED_CONVERSATION_QUEUE_KEY')
    assert redis_db.DEFERRED_CONVERSATION_QUEUE_KEY == 'deferred_conversations'
    assert hasattr(redis_db, 'DEFERRED_CONVERSATION_PROCESSING_KEY')
    assert redis_db.DEFERRED_CONVERSATION_PROCESSING_KEY == 'deferred_conversations_processing'


def test_enqueue_uses_lua_for_atomicity():
    """enqueue_deferred_conversation must use a Lua script for atomic dedup+push."""
    import pathlib

    src = pathlib.Path(__file__).resolve().parents[2] / 'database' / 'redis_db.py'
    source = src.read_text()
    pos = source.find('def enqueue_deferred_conversation')
    assert pos > 0
    next_func = source.find('\ndef ', pos + 1)
    func_body = source[pos:next_func] if next_func > 0 else source[pos : pos + 1000]
    assert 'eval' in func_body, "enqueue must use r.eval (Lua script) for atomic dedup+push"


def test_enqueue_lua_script_defined():
    """_ENQUEUE_LUA must be defined with SET NX + RPUSH logic."""
    import pathlib

    src = pathlib.Path(__file__).resolve().parents[2] / 'database' / 'redis_db.py'
    source = src.read_text()
    assert '_ENQUEUE_LUA' in source
    assert 'SET' in source and 'NX' in source and 'RPUSH' in source


def test_dequeue_uses_lua_with_lmove():
    """dequeue_deferred_conversation must use Lua script with LMOVE + SET for atomicity."""
    import pathlib

    src = pathlib.Path(__file__).resolve().parents[2] / 'database' / 'redis_db.py'
    source = src.read_text()
    # Check the Lua script contains LMOVE + SET
    assert '_DEQUEUE_LUA' in source
    assert 'LMOVE' in source
    # Dequeue function must use eval (Lua)
    pos = source.find('def dequeue_deferred_conversation')
    assert pos > 0
    next_func = source.find('\ndef ', pos + 1)
    func_body = source[pos:next_func] if next_func > 0 else source[pos : pos + 500]
    assert 'eval' in func_body, "dequeue must use r.eval (Lua script) for atomic LMOVE + SET lock"


def test_recover_uses_lua_for_atomicity():
    """recover_deferred_processing must use Lua for atomic LPOP+RPUSH."""
    import pathlib

    src = pathlib.Path(__file__).resolve().parents[2] / 'database' / 'redis_db.py'
    source = src.read_text()
    pos = source.find('def recover_deferred_processing')
    assert pos > 0
    next_func = source.find('\ndef ', pos + 1)
    func_body = source[pos:next_func] if next_func > 0 else source[pos : pos + 500]
    assert 'eval' in func_body, "recover must use r.eval (Lua script) for atomic LPOP+RPUSH"


# ---------------------------------------------------------------------------
# Pusher deferred queue worker tests
# ---------------------------------------------------------------------------


def test_deferred_queue_worker_exists_in_pusher():
    """deferred_queue_worker must exist in routers/pusher.py."""
    source = _read_pusher_source()
    assert 'async def deferred_queue_worker' in source


def test_process_deferred_conversation_exists():
    """_process_deferred_conversation must exist in routers/pusher.py."""
    source = _read_pusher_source()
    assert 'async def _process_deferred_conversation' in source


def test_deferred_worker_uses_to_thread():
    """_process_deferred_conversation must use asyncio.to_thread for heavy work."""
    source = _read_pusher_source()
    pos = source.find('async def _process_deferred_conversation')
    assert pos > 0
    # Find end of function
    next_func = source.find('\nasync def ', pos + 1)
    func_body = source[pos:next_func] if next_func > 0 else source[pos : pos + 1500]
    assert (
        'asyncio.to_thread' in func_body
    ), "_process_deferred_conversation must use asyncio.to_thread for blocking operations"


def test_deferred_worker_calls_process_conversation():
    """_process_deferred_conversation must call process_conversation."""
    source = _read_pusher_source()
    pos = source.find('async def _process_deferred_conversation')
    assert pos > 0
    next_func = source.find('\nasync def ', pos + 1)
    func_body = source[pos:next_func] if next_func > 0 else source[pos : pos + 1500]
    assert 'process_conversation' in func_body


def test_deferred_worker_handles_geolocation():
    """_process_deferred_conversation must handle geolocation."""
    source = _read_pusher_source()
    pos = source.find('async def _process_deferred_conversation')
    assert pos > 0
    next_func = source.find('\nasync def ', pos + 1)
    func_body = source[pos:next_func] if next_func > 0 else source[pos : pos + 1500]
    assert 'get_cached_user_geolocation' in func_body
    assert 'get_google_maps_location' in func_body


def test_deferred_worker_discards_on_error():
    """_process_deferred_conversation must discard conversation on error."""
    source = _read_pusher_source()
    pos = source.find('async def _process_deferred_conversation')
    assert pos > 0
    next_func = source.find('\nasync def ', pos + 1)
    func_body = source[pos:next_func] if next_func > 0 else source[pos : pos + 1500]
    assert 'set_conversation_as_discarded' in func_body


def test_pusher_main_starts_deferred_worker():
    """pusher/main.py must start the deferred queue worker on startup."""
    source = _read_pusher_main_source()
    assert 'deferred_queue_worker' in source
    assert 'startup' in source


def test_deferred_worker_uses_ack_nack():
    """deferred_queue_worker must use ack on success and nack on failure."""
    source = _read_pusher_source()
    pos = source.find('async def deferred_queue_worker')
    assert pos > 0
    next_func = source.find('\n@router', pos + 1)
    func_body = source[pos:next_func] if next_func > 0 else source[pos : pos + 2000]
    assert 'ack_deferred_conversation' in func_body, "Worker must ack on success"
    assert 'nack_deferred_conversation' in func_body, "Worker must nack on failure for retry"


def test_deferred_worker_recovers_on_startup():
    """deferred_queue_worker must call recover_deferred_processing on startup."""
    source = _read_pusher_source()
    pos = source.find('async def deferred_queue_worker')
    assert pos > 0
    next_func = source.find('\n@router', pos + 1)
    func_body = source[pos:next_func] if next_func > 0 else source[pos : pos + 2000]
    assert 'recover_deferred_processing' in func_body, "Worker must recover stuck items on startup"


# ---------------------------------------------------------------------------
# Behavioral tests — Redis queue patterns
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_to_thread_offloads_blocking_work():
    """asyncio.to_thread must run the sync function in a different thread than the event loop."""
    event_loop_thread = threading.current_thread().ident
    worker_thread_id = None

    def blocking_work(uid, language, conversation):
        nonlocal worker_thread_id
        worker_thread_id = threading.current_thread().ident
        time.sleep(0.05)
        return conversation

    mock_conversation = MagicMock()
    await asyncio.to_thread(blocking_work, 'uid', 'en', mock_conversation)

    assert worker_thread_id is not None
    assert worker_thread_id != event_loop_thread


@pytest.mark.asyncio
async def test_event_loop_remains_responsive_during_thread_offload():
    """The event loop must remain responsive while blocking work runs in a thread."""
    ticker_count = 0

    async def ticker():
        nonlocal ticker_count
        for _ in range(20):
            await asyncio.sleep(0.01)
            ticker_count += 1

    def slow_sync(uid, language, conversation):
        time.sleep(0.15)
        return conversation

    mock_conversation = MagicMock()

    async def run_in_thread():
        return await asyncio.to_thread(slow_sync, 'uid', 'en', mock_conversation)

    await asyncio.gather(ticker(), run_in_thread())
    assert ticker_count >= 10, f"Event loop ticker only ran {ticker_count}/20 — event loop was blocked"


@pytest.mark.asyncio
async def test_exception_propagates_from_thread():
    """Exceptions from the thread worker must propagate to the caller."""

    def failing_sync(uid, language, conversation):
        raise RuntimeError("OpenAI API unavailable")

    with pytest.raises(RuntimeError, match="OpenAI API unavailable"):
        await asyncio.to_thread(failing_sync, 'uid', 'en', MagicMock())


# ---------------------------------------------------------------------------
# Degraded mode routing tests
# ---------------------------------------------------------------------------


def test_degraded_mode_routes_to_enqueue():
    """When pusher is degraded, _process_conversation must enqueue, not process locally."""
    source = _read_transcribe_source()
    # Find the _process_conversation function (the inner one, indented)
    pos = source.find('async def _process_conversation(conversation_id')
    assert pos > 0, "Cannot find _process_conversation"
    next_func = source.find('\n    async def ', pos + 1)
    func_body = source[pos:next_func] if next_func > 0 else source[pos : pos + 1000]
    assert (
        '_enqueue_conversation_for_deferred_processing' in func_body
    ), "Degraded mode must route to _enqueue_conversation_for_deferred_processing"
    assert (
        '_create_conversation_fallback' not in func_body
    ), "_create_conversation_fallback must not be called — use Redis enqueue"


def test_cleanup_processing_routes_to_enqueue():
    """cleanup_processing_conversations must enqueue when degraded, not process locally."""
    source = _read_transcribe_source()
    pos = source.find('async def cleanup_processing_conversations')
    assert pos > 0
    next_func = source.find('\n    async def ', pos + 1)
    func_body = source[pos:next_func] if next_func > 0 else source[pos : pos + 800]
    assert '_enqueue_conversation_for_deferred_processing' in func_body
    assert '_create_conversation_fallback' not in func_body


def test_reconnect_loop_routes_to_enqueue():
    """_pusher_reconnect_loop must enqueue when exhausted/CB open, not process locally."""
    source = _read_transcribe_source()
    pos = source.find('async def _pusher_reconnect_loop')
    assert pos > 0
    next_func = source.find('\n        async def ', pos + 1)
    func_body = source[pos:next_func] if next_func > 0 else source[pos : pos + 3000]
    assert '_fallback_enqueue_conversation' in func_body
    assert '_fallback_process_conversation' not in func_body or '_fallback_enqueue_conversation' in func_body
