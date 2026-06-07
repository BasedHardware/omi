"""Unit tests for the speaker-sample (type-105) reconnect buffer (#6060).

Speaker sample extraction requests were silently dropped when the backend->pusher WebSocket was
mid-reconnect: send_speaker_sample_request() returned on a disconnected socket with no log, queue,
or retry, so the speaker profile was never built. The fix buffers the request and replays it on
reconnect, mirroring the existing pending_conversation_requests (type-104) pattern.

The real logic lives inside the create_pusher_task_handler closure in routers/transcribe.py and
cannot be imported in isolation, so (as with test_pusher_conversation_retry.py) these tests mirror
the buffer/send/replay helpers faithfully, and a source-inspection test guards the real file against
a regression that removes the behavior.
"""

import asyncio
import json
import re
import struct
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

# ---------------------------------------------------------------------------
# Mirror of the real helpers in create_pusher_task_handler (transcribe.py)
# ---------------------------------------------------------------------------
MAX_PENDING_REQUESTS = 100


def _buffer_speaker_sample_request(pending: dict, person_id: str, conv_id: str, segment_ids):
    """Mirrors _buffer_speaker_sample_request(): key by person:conv, merge on dup, cap+drop oldest."""
    key = f"{person_id}:{conv_id}"
    existing = pending.get(key)
    if existing:
        existing['segment_ids'] = list(dict.fromkeys([*existing['segment_ids'], *segment_ids]))
        existing['sent_at'] = time.time()
        return
    if len(pending) >= MAX_PENDING_REQUESTS:
        oldest = min(pending, key=lambda k: pending[k]['sent_at'])
        del pending[oldest]
    pending[key] = {
        'person_id': person_id,
        'conv_id': conv_id,
        'segment_ids': list(segment_ids),
        'sent_at': time.time(),
    }


class _ConnectionClosed(Exception):
    """Stand-in for websockets.exceptions.ConnectionClosed, to exercise that distinct branch."""


async def _send_speaker_sample_request(
    pending, person_id, conv_id, segment_ids, pusher_ws, pusher_connected, mark_disconnected=None
):
    """Mirrors send_speaker_sample_request(): buffer when disconnected/failed, True only on send.

    Models the two distinct failure branches: ConnectionClosed re-buffers AND signals disconnect
    (mark_disconnected, which in the real code starts the reconnect loop), while a generic
    exception only re-buffers.
    """
    if not pusher_connected or not pusher_ws:
        _buffer_speaker_sample_request(pending, person_id, conv_id, segment_ids)
        return False
    try:
        data = bytearray()
        data.extend(struct.pack("I", 105))
        data.extend(
            bytes(json.dumps({"person_id": person_id, "conversation_id": conv_id, "segment_ids": segment_ids}), "utf-8")
        )
        await pusher_ws.send(data)
        return True
    except _ConnectionClosed:
        _buffer_speaker_sample_request(pending, person_id, conv_id, segment_ids)
        if mark_disconnected is not None:
            mark_disconnected()
        return False
    except Exception:
        _buffer_speaker_sample_request(pending, person_id, conv_id, segment_ids)
        return False


async def _replay_speaker_samples(pending, pusher_ws, pusher_connected, mark_disconnected=None):
    """Mirrors the _connect() replay: remove an entry only after a confirmed send."""
    for key in list(pending.keys()):
        req = pending.get(key)
        if not req:
            continue
        if await _send_speaker_sample_request(
            pending,
            req['person_id'],
            req['conv_id'],
            req['segment_ids'],
            pusher_ws,
            pusher_connected,
            mark_disconnected,
        ):
            pending.pop(key, None)


# ---------------------------------------------------------------------------
# Behavioral tests
# ---------------------------------------------------------------------------
def test_buffers_when_disconnected():
    pending = {}
    sent = asyncio.run(_send_speaker_sample_request(pending, "p1", "c1", ["s1", "s2"], None, False))
    assert sent is False
    assert list(pending.keys()) == ["p1:c1"]
    assert pending["p1:c1"]["segment_ids"] == ["s1", "s2"]


def test_sends_immediately_when_connected():
    pending = {}
    ws = AsyncMock()
    sent = asyncio.run(_send_speaker_sample_request(pending, "p1", "c1", ["s1"], ws, True))
    assert sent is True
    ws.send.assert_awaited_once()
    assert pending == {}  # nothing buffered on a successful send


def test_replay_drains_buffer_on_reconnect():
    pending = {}
    # two requests arrive while disconnected
    asyncio.run(_send_speaker_sample_request(pending, "p1", "c1", ["s1"], None, False))
    asyncio.run(_send_speaker_sample_request(pending, "p2", "c2", ["s2"], None, False))
    assert len(pending) == 2
    ws = AsyncMock()
    asyncio.run(_replay_speaker_samples(pending, ws, True))
    assert pending == {}  # all replayed and removed
    assert ws.send.await_count == 2


def test_replay_retains_entry_on_generic_failure_without_marking_disconnected():
    pending = {}
    asyncio.run(_send_speaker_sample_request(pending, "p1", "c1", ["s1"], None, False))
    ws = AsyncMock()
    ws.send.side_effect = RuntimeError("boom")
    mark = MagicMock()
    asyncio.run(_replay_speaker_samples(pending, ws, True, mark))
    assert "p1:c1" in pending  # not dropped — preserved for the next reconnect
    mark.assert_not_called()  # a generic send error does not flag the connection as down


def test_connection_closed_rebuffers_and_marks_disconnected():
    pending = {}
    asyncio.run(_send_speaker_sample_request(pending, "p1", "c1", ["s1"], None, False))
    ws = AsyncMock()
    ws.send.side_effect = _ConnectionClosed()
    mark = MagicMock()
    asyncio.run(_replay_speaker_samples(pending, ws, True, mark))
    assert "p1:c1" in pending  # retained for the next reconnect
    mark.assert_called_once()  # ConnectionClosed flags disconnect so the reconnect loop drains it


def test_cap_drops_oldest():
    pending = {
        f"p{i}:c{i}": {'person_id': f"p{i}", 'conv_id': f"c{i}", 'segment_ids': ["s"], 'sent_at': float(i)}
        for i in range(MAX_PENDING_REQUESTS)
    }
    assert len(pending) == MAX_PENDING_REQUESTS
    _buffer_speaker_sample_request(pending, "pnew", "cnew", ["s"])
    assert len(pending) == MAX_PENDING_REQUESTS  # capped
    assert "p0:c0" not in pending  # oldest (sent_at=0.0) evicted
    assert "pnew:cnew" in pending


def test_merges_segment_ids_on_duplicate_key():
    pending = {}
    _buffer_speaker_sample_request(pending, "p1", "c1", ["s1", "s2"])
    _buffer_speaker_sample_request(pending, "p1", "c1", ["s2", "s3"])
    assert list(pending.keys()) == ["p1:c1"]
    assert pending["p1:c1"]["segment_ids"] == ["s1", "s2", "s3"]  # merged, de-duplicated, ordered


# ---------------------------------------------------------------------------
# Source-inspection regression guard on the real file
# ---------------------------------------------------------------------------
def _transcribe_source():
    return (Path(__file__).resolve().parent.parent.parent / "routers" / "transcribe.py").read_text(encoding="utf-8")


def _send_function_source():
    """Slice just send_speaker_sample_request() out of transcribe.py (up to the next sibling def)."""
    src = _transcribe_source()
    start = src.index("async def send_speaker_sample_request")
    rest = src[start + 1 :]
    m = re.search(r"\n        (?:async def|def) ", rest)
    return rest[: m.start()] if m else rest


def test_real_code_buffers_and_replays_speaker_samples():
    src = _transcribe_source()
    assert "pending_speaker_sample_requests" in src
    assert "_buffer_speaker_sample_request" in src
    # buffered on the disconnected path (no longer a bare return)
    assert "buffering speaker sample request" in src
    # replayed on reconnect, removed only after a confirmed send
    assert "pending speaker sample requests" in src
    assert "pending_speaker_sample_requests.pop(" in src


def test_real_code_has_distinct_connection_closed_branch():
    # Greptile #6060: the ConnectionClosed branch must stay distinct from the generic handler so it
    # keeps calling _mark_disconnected(); merging them would silently drop the reconnect trigger.
    body = _send_function_source()
    assert "except ConnectionClosed:" in body
    assert "_mark_disconnected()" in body  # only present in the ConnectionClosed branch
    assert "except Exception" in body  # the generic branch still exists and is separate
    assert body.count("_buffer_speaker_sample_request(") >= 2  # both failure branches re-buffer
