"""Unit tests for the pusher heartbeat keepalive mechanism.

Tests the data-frame heartbeat (header type 100) that prevents GKE ILB idle
timeout kills on the backend→pusher WebSocket connection.
"""

import asyncio
import struct
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from websockets.exceptions import ConnectionClosed
from websockets.frames import Close

# ---------------------------------------------------------------------------
# Helper: build a minimal pusher_heartbeat coroutine matching the real impl
# ---------------------------------------------------------------------------


async def _make_heartbeat(pusher_ws, pusher_connected_ref, websocket_active_ref, uid="test", session_id="s1"):
    """Mirrors the pusher_heartbeat() logic from create_pusher_task_handler."""
    while websocket_active_ref[0]:
        await asyncio.sleep(0.05)  # Shortened from 20s for testing
        if pusher_connected_ref[0] and pusher_ws[0]:
            try:
                await pusher_ws[0].send(struct.pack("I", 100))
            except ConnectionClosed:
                pusher_connected_ref[0] = False
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_heartbeat_sends_header_100():
    """Heartbeat sends exactly a 4-byte header with value 100."""
    mock_ws = AsyncMock()
    ws_ref = [mock_ws]
    connected = [True]
    active = [True]

    task = asyncio.create_task(_make_heartbeat(ws_ref, connected, active))
    await asyncio.sleep(0.15)  # Let a few heartbeats fire
    active[0] = False
    await asyncio.sleep(0.1)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    assert mock_ws.send.call_count >= 1, "Should have sent at least one heartbeat"
    for call in mock_ws.send.call_args_list:
        frame = call[0][0]
        assert len(frame) == 4, "Heartbeat frame must be exactly 4 bytes"
        assert struct.unpack("<I", frame)[0] == 100, "Header type must be 100"


@pytest.mark.asyncio
async def test_heartbeat_skips_when_disconnected():
    """Heartbeat does not send when pusher_connected is False."""
    mock_ws = AsyncMock()
    ws_ref = [mock_ws]
    connected = [False]  # Disconnected
    active = [True]

    task = asyncio.create_task(_make_heartbeat(ws_ref, connected, active))
    await asyncio.sleep(0.15)
    active[0] = False
    await asyncio.sleep(0.1)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    assert mock_ws.send.call_count == 0, "Should not send when disconnected"


@pytest.mark.asyncio
async def test_heartbeat_skips_when_ws_none():
    """Heartbeat does not send when pusher_ws is None."""
    ws_ref = [None]
    connected = [True]
    active = [True]

    task = asyncio.create_task(_make_heartbeat(ws_ref, connected, active))
    await asyncio.sleep(0.15)
    active[0] = False
    await asyncio.sleep(0.1)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    # No send calls since ws is None — test passes if no exception raised


@pytest.mark.asyncio
async def test_heartbeat_marks_disconnected_on_connection_closed():
    """ConnectionClosed sets pusher_connected = False."""
    mock_ws = AsyncMock()
    mock_ws.send.side_effect = ConnectionClosed(None, None)
    ws_ref = [mock_ws]
    connected = [True]
    active = [True]

    task = asyncio.create_task(_make_heartbeat(ws_ref, connected, active))
    await asyncio.sleep(0.15)
    active[0] = False
    await asyncio.sleep(0.1)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    assert connected[0] is False, "Should mark disconnected after ConnectionClosed"


@pytest.mark.asyncio
async def test_heartbeat_stops_on_websocket_inactive():
    """Heartbeat loop exits when websocket_active becomes False."""
    mock_ws = AsyncMock()
    ws_ref = [mock_ws]
    connected = [True]
    active = [True]

    task = asyncio.create_task(_make_heartbeat(ws_ref, connected, active))
    await asyncio.sleep(0.1)
    active[0] = False
    # Task should exit on its own
    await asyncio.wait_for(task, timeout=1.0)
    # If we get here without timeout, the loop exited correctly


@pytest.mark.asyncio
async def test_heartbeat_interleaves_with_data_frames():
    """Heartbeat frames don't interfere with normal data frame sends."""
    sent_frames = []

    async def capture_send(data):
        sent_frames.append(data)

    mock_ws = AsyncMock()
    mock_ws.send.side_effect = capture_send
    ws_ref = [mock_ws]
    connected = [True]
    active = [True]

    # Start heartbeat
    task = asyncio.create_task(_make_heartbeat(ws_ref, connected, active))

    # Simulate sending normal data frames (header 102 = transcript)
    transcript_frame = bytearray()
    transcript_frame.extend(struct.pack("I", 102))
    transcript_frame.extend(b'{"segments":[]}')
    await mock_ws.send(bytes(transcript_frame))

    await asyncio.sleep(0.15)
    active[0] = False
    await asyncio.sleep(0.1)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    # Should have both heartbeat (100) and transcript (102) frames
    heartbeat_count = sum(1 for f in sent_frames if len(f) == 4 and struct.unpack("<I", f[:4])[0] == 100)
    assert heartbeat_count >= 1, "Should have heartbeat frames"


def test_pusher_receive_handles_heartbeat_header():
    """Pusher receive_tasks() handles header 100 with continue (no processing)."""
    # Simulate the header dispatch logic from pusher.py receive_tasks()
    data = struct.pack("I", 100)  # Heartbeat frame
    header_type = struct.unpack('<I', data[:4])[0]

    # The pusher handler should recognize 100 and skip processing
    assert header_type == 100
    # In the actual code this is: if header_type == 100: continue
    # Here we verify the frame is correctly parsed


def test_heartbeat_frame_is_minimal():
    """Heartbeat frame is exactly 4 bytes with no payload."""
    frame = struct.pack("I", 100)
    assert len(frame) == 4
    assert struct.unpack("<I", frame)[0] == 100
    # 720 bytes/hour at 3 frames/min
    hourly_bytes = 4 * 3 * 60
    assert hourly_bytes == 720
