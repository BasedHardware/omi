"""Unit tests for the process_conversation retry mechanism.

Tests the timeout-based retry and reconnect-retry logic that prevents
conversations from getting stuck as in_progress when pusher WebSocket
messages are silently lost (#5391).
"""

import asyncio
import json
import struct
import time
from unittest.mock import AsyncMock, MagicMock

import pytest
from websockets.exceptions import ConnectionClosed

# ---------------------------------------------------------------------------
# Helpers: mirror the real pending request tracking from transcribe.py
# ---------------------------------------------------------------------------

PENDING_REQUEST_TIMEOUT = 120  # seconds
MAX_RETRIES_PER_REQUEST = 3
MAX_PENDING_REQUESTS = 100


async def _request_conversation_processing(
    conversation_id: str,
    pending_requests: dict,
    pending_event: asyncio.Event,
    pusher_ws,
    pusher_connected: bool,
    language: str = "en",
):
    """Mirrors request_conversation_processing() from create_pusher_task_handler."""
    if not pusher_connected or not pusher_ws:
        if conversation_id not in pending_requests:
            pending_requests[conversation_id] = {'sent_at': time.time(), 'retries': 0}
            pending_event.set()
        return False
    if len(pending_requests) >= MAX_PENDING_REQUESTS:
        oldest_id = min(pending_requests, key=lambda k: pending_requests[k]['sent_at'])
        del pending_requests[oldest_id]
    try:
        pending_requests[conversation_id] = {
            'sent_at': time.time(),
            'retries': pending_requests.get(conversation_id, {}).get('retries', 0),
        }
        pending_event.set()
        data = bytearray()
        data.extend(struct.pack("I", 104))
        data.extend(bytes(json.dumps({"conversation_id": conversation_id, "language": language}), "utf-8"))
        await pusher_ws.send(data)
        return True
    except Exception:
        return False


def _check_timed_out_requests(pending_requests: dict, now: float):
    """Mirrors the timeout check in pusher_receive()."""
    timed_out = [cid for cid, info in list(pending_requests.items()) if now - info['sent_at'] > PENDING_REQUEST_TIMEOUT]
    actions = []
    for cid in timed_out:
        info = pending_requests.get(cid)
        if not info:
            continue
        if info['retries'] >= MAX_RETRIES_PER_REQUEST:
            pending_requests.pop(cid, None)
            actions.append(('give_up', cid))
            continue
        info['retries'] += 1
        info['sent_at'] = now  # Reset timer on retry
        actions.append(('retry', cid, info['retries']))
    return actions


def _handle_type_201_response(pending_requests: dict, conversation_id: str):
    """Mirrors type 201 handling in pusher_receive()."""
    pending_requests.pop(conversation_id, None)


# ---------------------------------------------------------------------------
# Tests: request tracking
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_request_tracks_pending_on_success():
    """Successful send adds conversation to pending with timestamp."""
    pending = {}
    event = asyncio.Event()
    mock_ws = AsyncMock()

    result = await _request_conversation_processing("conv-1", pending, event, mock_ws, True)

    assert result is True
    assert "conv-1" in pending
    assert pending["conv-1"]["retries"] == 0
    assert pending["conv-1"]["sent_at"] > 0


@pytest.mark.asyncio
async def test_request_tracks_pending_when_disconnected():
    """When pusher is disconnected, conversation is tracked for retry on reconnect."""
    pending = {}
    event = asyncio.Event()

    result = await _request_conversation_processing("conv-1", pending, event, None, False)

    assert result is False
    assert "conv-1" in pending
    assert pending["conv-1"]["retries"] == 0
    assert event.is_set(), "Should signal the receiver"


@pytest.mark.asyncio
async def test_request_does_not_overwrite_retry_count_when_disconnected():
    """Re-requesting a conversation that's already pending doesn't reset retry count."""
    pending = {"conv-1": {"sent_at": time.time() - 100, "retries": 2}}
    event = asyncio.Event()

    result = await _request_conversation_processing("conv-1", pending, event, None, False)

    assert result is False
    assert pending["conv-1"]["retries"] == 2, "Should not reset retry count"


@pytest.mark.asyncio
async def test_request_preserves_retry_count_on_resend():
    """Re-sending a pending request preserves its retry count."""
    pending = {"conv-1": {"sent_at": time.time() - 200, "retries": 2}}
    event = asyncio.Event()
    mock_ws = AsyncMock()

    result = await _request_conversation_processing("conv-1", pending, event, mock_ws, True)

    assert result is True
    assert pending["conv-1"]["retries"] == 2, "Retry count should be preserved"


@pytest.mark.asyncio
async def test_request_drops_oldest_on_overflow():
    """When pending requests hit MAX, drops the oldest."""
    pending = {}
    event = asyncio.Event()
    mock_ws = AsyncMock()

    # Fill to MAX
    for i in range(MAX_PENDING_REQUESTS):
        pending[f"conv-{i}"] = {"sent_at": time.time() - (MAX_PENDING_REQUESTS - i), "retries": 0}

    # conv-0 is the oldest
    result = await _request_conversation_processing("conv-new", pending, event, mock_ws, True)

    assert result is True
    assert "conv-0" not in pending, "Oldest request should be dropped"
    assert "conv-new" in pending
    assert len(pending) == MAX_PENDING_REQUESTS


@pytest.mark.asyncio
async def test_request_send_failure_keeps_pending():
    """If WS send raises, conversation stays in pending for retry."""
    pending = {}
    event = asyncio.Event()
    mock_ws = AsyncMock()
    mock_ws.send.side_effect = ConnectionClosed(None, None)

    result = await _request_conversation_processing("conv-1", pending, event, mock_ws, True)

    assert result is False
    assert "conv-1" in pending, "Should stay in pending for retry"


# ---------------------------------------------------------------------------
# Tests: timeout-based retry
# ---------------------------------------------------------------------------


def test_timeout_retry_triggers_after_threshold():
    """Pending request older than PENDING_REQUEST_TIMEOUT triggers retry."""
    pending = {"conv-1": {"sent_at": time.time() - PENDING_REQUEST_TIMEOUT - 1, "retries": 0}}
    now = time.time()

    actions = _check_timed_out_requests(pending, now)

    assert len(actions) == 1
    assert actions[0] == ('retry', 'conv-1', 1)
    assert pending["conv-1"]["retries"] == 1


def test_timeout_no_retry_before_threshold():
    """Pending request within timeout window is not retried."""
    pending = {"conv-1": {"sent_at": time.time() - 10, "retries": 0}}
    now = time.time()

    actions = _check_timed_out_requests(pending, now)

    assert len(actions) == 0


def test_timeout_gives_up_after_max_retries():
    """After MAX_RETRIES_PER_REQUEST, request is dropped."""
    pending = {"conv-1": {"sent_at": time.time() - PENDING_REQUEST_TIMEOUT - 1, "retries": MAX_RETRIES_PER_REQUEST}}
    now = time.time()

    actions = _check_timed_out_requests(pending, now)

    assert len(actions) == 1
    assert actions[0] == ('give_up', 'conv-1')
    assert "conv-1" not in pending, "Should be removed from pending"


def test_timeout_retry_increments_count():
    """Each retry increments the retry counter."""
    pending = {"conv-1": {"sent_at": time.time() - PENDING_REQUEST_TIMEOUT - 1, "retries": 1}}
    now = time.time()

    actions = _check_timed_out_requests(pending, now)

    assert actions[0] == ('retry', 'conv-1', 2)
    assert pending["conv-1"]["retries"] == 2


def test_timeout_multiple_requests():
    """Multiple timed-out requests are all retried."""
    now = time.time()
    pending = {
        "conv-1": {"sent_at": now - PENDING_REQUEST_TIMEOUT - 10, "retries": 0},
        "conv-2": {"sent_at": now - PENDING_REQUEST_TIMEOUT - 5, "retries": 1},
        "conv-3": {"sent_at": now - 10, "retries": 0},  # Not timed out
    }

    actions = _check_timed_out_requests(pending, now)

    retried_ids = {a[1] for a in actions if a[0] == 'retry'}
    assert retried_ids == {"conv-1", "conv-2"}
    assert "conv-3" in pending
    assert pending["conv-3"]["retries"] == 0, "Non-timed-out request should not be touched"


# ---------------------------------------------------------------------------
# Tests: type 201 response handling
# ---------------------------------------------------------------------------


def test_type_201_removes_from_pending():
    """Successful type 201 response removes conversation from pending."""
    pending = {"conv-1": {"sent_at": time.time(), "retries": 0}}

    _handle_type_201_response(pending, "conv-1")

    assert "conv-1" not in pending


def test_type_201_unknown_id_is_safe():
    """Type 201 for unknown conversation_id doesn't crash."""
    pending = {"conv-1": {"sent_at": time.time(), "retries": 0}}

    _handle_type_201_response(pending, "conv-unknown")

    assert "conv-1" in pending, "Should not affect other pending requests"


# ---------------------------------------------------------------------------
# Tests: reconnect retry
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reconnect_resends_all_pending():
    """After reconnect, all pending requests are re-sent."""
    mock_ws = AsyncMock()
    pending = {
        "conv-1": {"sent_at": time.time() - 200, "retries": 0},
        "conv-2": {"sent_at": time.time() - 100, "retries": 1},
    }
    event = asyncio.Event()

    # Simulate reconnect: re-send all pending
    for cid in list(pending.keys()):
        pending[cid]['sent_at'] = time.time()
        await _request_conversation_processing(cid, pending, event, mock_ws, True)

    assert mock_ws.send.call_count == 2
    # Verify both sent type 104
    for call in mock_ws.send.call_args_list:
        frame = call[0][0]
        header = struct.unpack('<I', frame[:4])[0]
        assert header == 104


@pytest.mark.asyncio
async def test_reconnect_preserves_retry_counts():
    """Re-sending on reconnect preserves existing retry counts."""
    mock_ws = AsyncMock()
    pending = {
        "conv-1": {"sent_at": time.time() - 200, "retries": 2},
    }
    event = asyncio.Event()

    pending["conv-1"]["sent_at"] = time.time()
    await _request_conversation_processing("conv-1", pending, event, mock_ws, True)

    assert pending["conv-1"]["retries"] == 2, "Retry count should be preserved on reconnect"


# ---------------------------------------------------------------------------
# Tests: binary protocol
# ---------------------------------------------------------------------------


def test_type_104_frame_format():
    """Type 104 frame has correct format: 4-byte header + JSON payload."""
    conversation_id = "test-conv-123"
    language = "en"

    data = bytearray()
    data.extend(struct.pack("I", 104))
    data.extend(bytes(json.dumps({"conversation_id": conversation_id, "language": language}), "utf-8"))

    # Parse it back
    header = struct.unpack('<I', data[:4])[0]
    payload = json.loads(data[4:].decode("utf-8"))

    assert header == 104
    assert payload["conversation_id"] == conversation_id
    assert payload["language"] == language
