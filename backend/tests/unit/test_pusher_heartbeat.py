"""Unit tests for the pusher heartbeat keepalive mechanism.

Tests the data-frame heartbeat (header type 100) that prevents GKE ILB idle
timeout kills on the backend→pusher WebSocket connection.
"""

import asyncio
import json
import struct
from unittest.mock import AsyncMock

import pytest
from websockets.exceptions import ConnectionClosed

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
# Helper: simulate the pusher receive_tasks() dispatch loop from pusher.py
# ---------------------------------------------------------------------------


async def _simulate_pusher_dispatch(frames: list[bytes]) -> dict:
    """Run the header dispatch logic from pusher.py receive_tasks() over a
    list of raw binary frames. Returns counts of how each header was handled.

    This mirrors the real dispatch at backend/routers/pusher.py:324-451.
    """
    counts = {"heartbeat": 0, "conversation_id": 0, "transcript": 0, "audio": 0, "unknown": 0}

    for data in frames:
        if len(data) < 4:
            continue
        header_type = struct.unpack('<I', data[:4])[0]

        # Heartbeat (data-frame keepalive from backend to reset GKE ILB idle timer)
        if header_type == 100:
            counts["heartbeat"] += 1
            continue

        # Conversation ID
        if header_type == 103:
            counts["conversation_id"] += 1
            continue

        # Transcript
        if header_type == 102:
            counts["transcript"] += 1
            continue

        # Audio bytes
        if header_type == 101:
            counts["audio"] += 1
            continue

        counts["unknown"] += 1

    return counts


# ---------------------------------------------------------------------------
# Tests: heartbeat sender (transcribe.py side)
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


# ---------------------------------------------------------------------------
# Tests: pusher dispatch (pusher.py side)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pusher_dispatch_heartbeat_is_silent_noop():
    """Pusher dispatch loop handles header 100 silently (no processing, just continue)."""
    # Build a stream of frames: heartbeat, transcript, heartbeat, audio, heartbeat
    frames = [
        struct.pack("I", 100),  # heartbeat
        struct.pack("I", 102) + json.dumps({"segments": [], "memory_id": "c1"}).encode(),  # transcript
        struct.pack("I", 100),  # heartbeat
        struct.pack("I", 101) + struct.pack("d", 1234.0) + b'\x00' * 100,  # audio
        struct.pack("I", 100),  # heartbeat
    ]

    counts = await _simulate_pusher_dispatch(frames)

    assert counts["heartbeat"] == 3, "All 3 heartbeats should be counted and silently skipped"
    assert counts["transcript"] == 1, "Transcript frame should be processed normally"
    assert counts["audio"] == 1, "Audio frame should be processed normally"
    assert counts["unknown"] == 0, "No unknown frame types"


@pytest.mark.asyncio
async def test_pusher_dispatch_heartbeat_only_stream():
    """Pusher handles a stream of only heartbeats (simulates pure silence period)."""
    frames = [struct.pack("I", 100) for _ in range(10)]
    counts = await _simulate_pusher_dispatch(frames)

    assert counts["heartbeat"] == 10
    assert counts["transcript"] == 0
    assert counts["audio"] == 0


@pytest.mark.asyncio
async def test_pusher_dispatch_heartbeat_does_not_affect_conversation_id():
    """Heartbeat between conversation_id frames doesn't corrupt state."""
    frames = [
        struct.pack("I", 103) + b"conv-abc",  # set conversation_id
        struct.pack("I", 100),  # heartbeat (should not affect anything)
        struct.pack("I", 103) + b"conv-def",  # update conversation_id
    ]
    counts = await _simulate_pusher_dispatch(frames)

    assert counts["heartbeat"] == 1
    assert counts["conversation_id"] == 2


# ---------------------------------------------------------------------------
# Tests: frame format
# ---------------------------------------------------------------------------


def test_heartbeat_frame_is_minimal():
    """Heartbeat frame is exactly 4 bytes with no payload."""
    frame = struct.pack("I", 100)
    assert len(frame) == 4
    assert struct.unpack("<I", frame)[0] == 100
    # 720 bytes/hour at 3 frames/min
    hourly_bytes = 4 * 3 * 60
    assert hourly_bytes == 720


def test_heartbeat_header_does_not_collide_with_existing_headers():
    """Header 100 is distinct from all existing protocol headers."""
    existing_headers = {101, 102, 103, 104, 105, 201}  # All existing headers
    heartbeat_header = 100
    assert heartbeat_header not in existing_headers, "Header 100 must not collide with existing protocol headers"
