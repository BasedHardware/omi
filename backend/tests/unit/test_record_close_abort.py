"""Abort needs the same exact durable tail as commit and wins atomically."""

import asyncio
import json
import struct
from unittest.mock import AsyncMock

import pytest

from tests.unit.utils.test_listen_pusher_session import FakePusherWebSocket, make_session
from utils.pusher_record_close import PusherCloseState, PendingClose


@pytest.mark.parametrize('first', ['abort', 'commit'])
async def test_abort_and_commit_race_has_one_terminal_winner(first):
    state = PusherCloseState(True)
    state.audio('record', 4)
    state.prepare('record', 'request', set())
    gate = asyncio.Event()

    async def resolve(phase):
        await gate.wait()
        return getattr(state, phase)('record', 'request', 4)

    tasks = [asyncio.create_task(resolve(phase)) for phase in [first, 'commit' if first == 'abort' else 'abort']]
    gate.set()
    replies = await asyncio.gather(*tasks)
    assert replies == (['aborted', 'unknown'] if first == 'abort' else ['accepted', 'committed'])
    assert not state.blocks('record', True)
    assert state.abort('record', 'request', 5) == 'invalid_watermark'
    assert state.abort('record', 'other', 4) == 'unknown'
    assert state.abort('unknown', 'request', 4) == 'unknown'
    state.retire('record')
    assert state.abort('record', 'request', 4) == ('aborted' if first == 'abort' else 'committed')
    assert state.abort('record', 'request', 5) == ('unknown' if first == 'abort' else 'invalid_watermark')


@pytest.mark.parametrize('durable,capable', [(False, True), (True, True), (True, False)])
async def test_deadline_abort_requires_durable_source_and_peer_capability(monkeypatch, durable, capable):
    monkeypatch.setenv('PUSHER_RECORD_CLOSE_NOTIFY_ENABLED', 'true')
    monkeypatch.setenv('PUSHER_RECORD_CLOSE_NOTIFY_ENABLED_SERVE_PERCENT', '100')
    clock = [100.0]
    socket = FakePusherWebSocket()
    hook = AsyncMock(return_value=durable)
    session = make_session(ws=socket, deps_overrides={'finish_recording_audio': hook, 'monotonic': lambda: clock[0]})
    await session.connect()
    session.record_close_supported = True
    session.record_close_abort_supported = capable
    close = PendingClose(socket=socket, prepared=True, deadline=99, base=4)
    session.pending_record_closes['record'] = close
    await session.request_recording_close('record')
    controls = [json.loads(frame[4:]) for frame in socket.sent if struct.unpack('<I', frame[:4])[0] == 104]
    assert [frame['phase'] for frame in controls] == (['abort'] if durable and capable else [])
    assert close.frozen is (durable and capable)
    if capable:
        assert 'record' in session.pending_record_closes  # Wait for ACK or bounded abort exit.
        clock[0] += 31
        await session.request_recording_close('record')
    assert 'record' not in session.pending_record_closes
    assert not socket.closed_codes


@pytest.mark.parametrize('capability', [None, False, True])
async def test_v3_abort_extension_is_negotiated_per_socket(monkeypatch, capability):
    monkeypatch.setenv('PUSHER_RECORD_CLOSE_NOTIFY_ENABLED', 'true')
    monkeypatch.setenv('PUSHER_RECORD_CLOSE_NOTIFY_ENABLED_SERVE_PERCENT', '100')
    ack = {'type': 'record_close_ack', 'version': 3}
    if capability is not None:
        ack['abort_to_legacy'] = capability
    active = {'active': True}
    socket = FakePusherWebSocket(incoming=[struct.pack('<I', 204) + json.dumps(ack).encode(), b''])
    socket.on_recv = lambda: active.update(active=len(socket.incoming) > 1)
    session = make_session(
        ws=socket, active_ref=active, deps_overrides={'finish_recording_audio': AsyncMock(return_value=True)}
    )
    await session.connect()
    session.pending_request_event.set()
    session.pending_conversation_requests['unrelated'] = {'sent_at': 1000, 'retries': 0}
    await session.pusher_receive()
    assert session.record_close_supported
    assert session.record_close_abort_supported is (capability is True)


async def test_abort_watermark_and_late_request_cannot_release_fence():
    state = PusherCloseState(True)
    state.audio('record', 4)
    state.prepare('record', 'request', set())
    assert state.abort('record', 'request', 3) == 'invalid_watermark'
    assert state.abort('record', 'request', 8) == 'watermark_pending'
    assert state.blocks('record', True)
    state.audio('record', 4)
    assert state.abort('record', 'request', 8) == 'aborted'
    assert state.abort('record', 'request', 8) == 'aborted'
    assert state.abort('record', 'request', 4) == 'invalid_watermark'
    with pytest.raises(ValueError):
        state.audio('record', 4)


async def test_abort_waits_for_archive_before_ordered_relay_and_ack(monkeypatch):
    monkeypatch.setenv('PUSHER_RECORD_CLOSE_NOTIFY_ENABLED', 'true')
    monkeypatch.setenv('PUSHER_RECORD_CLOSE_NOTIFY_ENABLED_SERVE_PERCENT', '100')
    entered, release = asyncio.Event(), asyncio.Event()
    order = []

    async def archive(cid):
        entered.set()
        await release.wait()
        order.append('archive')
        return True

    active = {'active': True}
    socket = FakePusherWebSocket()
    session = make_session(ws=socket, active_ref=active, deps_overrides={'finish_recording_audio': archive})
    await session.connect()
    session.record_close_supported = session.record_close_abort_supported = True
    close = PendingClose(socket=socket, prepared=True, deadline=0, base=4)
    session.pending_record_closes['conv-1'] = close
    flush = session._audio_bytes_flush

    async def ordered_flush(**kwargs):
        order.append('relay')
        await flush(**kwargs)

    monkeypatch.setattr(session, '_audio_bytes_flush', ordered_flush)
    attempt = asyncio.create_task(session.request_recording_close('conv-1'))
    try:
        await asyncio.wait_for(entered.wait(), 2)
        assert not socket.sent and not close.frozen
        release.set()
        await asyncio.wait_for(attempt, 2)
        assert order == ['archive', 'relay']
        assert json.loads(socket.sent[-1][4:])['phase'] == 'abort'
        assert 'conv-1' in session.pending_record_closes
        ack = dict(
            type='record_close_result',
            version=3,
            conversation_id='conv-1',
            request_id=close.request_id,
            phase='abort',
            status='aborted',
            watermark=4,
        )
        socket.incoming.extend([struct.pack('<I', 206) + json.dumps(ack).encode(), b''])
        socket.on_recv = lambda: active.update(active=len(socket.incoming) > 1)
        session.pending_conversation_requests['unrelated'] = {'sent_at': 1000, 'retries': 0}
        await asyncio.wait_for(session.pusher_receive(), 2)
        assert 'conv-1' not in session.pending_record_closes
        assert session.record_close_boundaries['conv-1'] is False
    finally:
        release.set()
        await attempt
