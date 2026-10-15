"""Pusher close severity follows the close code, not the transport phase.

Failure-Class: FC-lifecycle-close-classified-by-transport-phase — instance in
backend/utils/listen_pusher_session.py (2026-10-09 1012 wave): an expected
lifecycle teardown (pusher rolling update, close code 1012) was dispatched on
the transport phase that surfaced it (any ConnectionClosed on any socket)
instead of the typed close-code signal the transport already carries, logging
a routine restart per live session at ERROR; the adjacent genuine failures
(1006/1011/1015, no close frame) keep ERROR, and a close raised by a socket a
reconnect already replaced is informational on every path it can arrive on.

Production evidence (2026-10-09, backend-listen): every pusher GKE rolling
update closes each live session with 1012 (service restart), and the session
logged three ERROR lines per close —

- ``Pusher audio_bytes Connection closed: received 1012 (service restart);
  then sent 1012 (service restart)`` — x342/30m in the wave, plus the
  sibling ``Pusher transcripts Connection closed`` line at x17/30m.

1012 is the pusher pod's own rolling-update signal, sent to every live
session at once. The session already treats it as routine transport churn:
audio runs and pending conversations stay buffered and the reconnect loop
installs a replacement socket, replaying everything. Logging it at ERROR
paged the log sentinel per session per restart and buried the genuine
abnormal closes (1006, 1011, 1015, no close frame) that share the message
shape. The boundary mirrors the session-side severity reclassifications in
#12822/#12827: expected, self-healing lifecycle events log below ERROR; the
genuine fault signal keeps ERROR.

Second, independent defect in the same close path: the audio and transcript
flush handlers treated ANY socket's ConnectionClosed as this session's
disconnect — including a stale socket that a concurrent reconnect had
already replaced — tearing down the freshly installed connection
(``pusher_receive`` already guarded this with a socket-identity check; the
flush paths did not). A stale close is informational and must never drop
the new connection.
"""

import asyncio
import logging
import struct

import pytest
from websockets.exceptions import ConnectionClosed, ConnectionClosedError
from websockets.frames import Close

from utils.listen_pusher_session import (
    PUSHER_EXPECTED_RESTART_CLOSE_CODES,
    log_pusher_connection_closed,
)
from tests.unit.utils.test_listen_pusher_session import FakePusherWebSocket, make_session


def close_1012() -> ConnectionClosed:
    """The exact production shape: received 1012, then sent 1012."""
    return ConnectionClosed(Close(1012, 'service restart'), Close(1012, 'service restart'), True)


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.parametrize(
    'exception,expected_level',
    [
        (close_1012(), logging.INFO),
        # Genuine abnormal closes keep the fault meaning of the line.
        (ConnectionClosedError(None, None), logging.ERROR),
        (ConnectionClosedError(Close(1011, 'internal error'), None), logging.ERROR),
        (ConnectionClosedError(Close(1006, 'no close frame received'), None), logging.ERROR),
        (ConnectionClosedError(Close(1015, 'tls handshake failed'), None), logging.ERROR),
    ],
)
@pytest.mark.anyio
async def test_close_classifier_severity_follows_close_code(exception, expected_level, caplog):
    with caplog.at_level(logging.INFO, logger='utils.listen_pusher_session'):
        log_pusher_connection_closed(
            logging.getLogger('utils.listen_pusher_session'),
            exception,
            'Pusher audio_bytes Connection closed',
            uid='uid-1',
            session_id='session-1',
        )
    records = [r for r in caplog.records if r.name == 'utils.listen_pusher_session']
    assert len(records) == 1
    assert records[0].levelno == expected_level
    # The close text itself is preserved verbatim for the log sentinel.
    assert str(exception) in records[0].getMessage()


@pytest.mark.anyio
async def test_restart_close_codes_are_only_the_service_restart_family():
    assert PUSHER_EXPECTED_RESTART_CLOSE_CODES == frozenset({1012})


@pytest.mark.anyio
async def test_audio_flush_restart_close_logs_info_and_recovers(monkeypatch, caplog):
    ws = FakePusherWebSocket(send_errors=[close_1012()])
    session = make_session(ws=ws)
    await session.connect()

    with caplog.at_level(logging.INFO, logger='utils.listen_pusher_session'):
        session.audio_bytes_send(b'abcd', received_at=100.0)
        await session._audio_bytes_flush()

    records = [r for r in caplog.records if 'Pusher audio_bytes Connection closed' in r.getMessage()]
    assert len(records) == 1
    assert records[0].levelno == logging.INFO
    assert '1012' in records[0].getMessage()
    # The run stays buffered for the reconnect replay, exactly as before.
    assert session.audio_total_size == len(b'abcd')
    assert not session.pusher_connected
    # One reconnect loop owns the recovery.
    assert session.reconnect_task is not None and not session.reconnect_task.done()
    session.reconnect_task.cancel()


@pytest.mark.anyio
async def test_transcript_flush_abnormal_close_stays_error(monkeypatch, caplog):
    ws = FakePusherWebSocket(send_errors=[ConnectionClosedError(None, None)])
    session = make_session(ws=ws)
    await session.connect()
    session.transcript_send([{'id': 'seg-1', 'text': 'hello'}])

    with caplog.at_level(logging.INFO, logger='utils.listen_pusher_session'):
        await session._transcript_flush()

    records = [r for r in caplog.records if 'Pusher transcripts Connection closed' in r.getMessage()]
    assert len(records) == 1
    assert records[0].levelno == logging.ERROR
    assert not session.pusher_connected


@pytest.mark.anyio
async def test_receive_restart_close_logs_info_and_reconnects():
    active_ref = {"active": True}
    ws = FakePusherWebSocket()
    session = make_session(ws=ws, active_ref=active_ref)
    await session.connect()
    # A pending conversation request moves the receive loop past its
    # pending-request event wait and into sock.recv, where the close lands.
    await session.request_conversation_processing('conv-1')

    async def close_with_restart():
        # The close arrives while the session is live; deactivate afterwards
        # so the receive loop terminates like a real session teardown.
        active_ref.update(active=False)
        raise close_1012()

    ws.recv = close_with_restart

    # Park the reconnect loop inside its backoff wait so the spawned task is
    # observably alive; the default fake wait_for_event returns immediately
    # and would race the assertion below.
    release = asyncio.Event()

    async def park_in_backoff(event, timeout):
        await release.wait()
        return False

    session.deps.wait_for_event = park_in_backoff
    await asyncio.wait_for(session.pusher_receive(), timeout=10)

    assert not session.pusher_connected
    # The disconnect handoff spawned the reconnect loop; the loop body itself
    # exits immediately because this fake session is already inactive.
    assert session.reconnect_task is not None


@pytest.mark.anyio
async def test_stale_socket_close_does_not_teardown_fresh_audio_socket():
    """A close raised by a socket a reconnect already replaced must not drop
    the freshly installed connection (audio flush path)."""
    stale = FakePusherWebSocket(send_errors=[ConnectionClosedError(None, None)])
    fresh = FakePusherWebSocket()
    session = make_session(ws=stale)
    await session.connect()
    session.audio_bytes_send(b'abcd', received_at=100.0)

    # A reconnect installs a replacement socket while the stale flush is in
    # flight; the pending conversation plumbing mirrors the production swap.
    async def install_fresh_during_send(data):
        session.pusher_ws = fresh
        session.pusher_connected = True
        raise ConnectionClosedError(None, None)

    stale.send = install_fresh_during_send
    await session._audio_bytes_flush()

    assert session.pusher_ws is fresh
    assert session.pusher_connected
    assert session.reconnect_task is None
    # The audio stays buffered for the fresh socket rather than being
    # re-buffered as uncertain (it was never framed for the fresh socket).
    assert session.audio_total_size == len(b'abcd')


@pytest.mark.anyio
async def test_stale_socket_close_does_not_teardown_fresh_transcript_socket():
    """Same identity rule on the transcript flush path."""
    stale = FakePusherWebSocket(send_errors=[ConnectionClosedError(None, None)])
    fresh = FakePusherWebSocket()
    session = make_session(ws=stale)
    await session.connect()
    session.transcript_send([{'id': 'seg-1', 'text': 'hello'}])

    async def install_fresh_during_send(data):
        session.pusher_ws = fresh
        session.pusher_connected = True
        raise ConnectionClosedError(None, None)

    stale.send = install_fresh_during_send
    await session._transcript_flush()

    assert session.pusher_ws is fresh
    assert session.pusher_connected
    assert session.reconnect_task is None
    assert len(session.segment_buffers) == 1


@pytest.mark.anyio
async def test_1012_close_then_reconnect_discards_unproven_legacy_runs_once():
    """End-to-end 1012 transport contract on a legacy session: the close
    returns the framed run to the buffer stamped with the dead socket; after
    the reconnect installs a replacement, that run is discarded once (never
    silently replayed against an unannounced replacement) — the d323ef75ad
    contract the severity change must not alter."""
    ws = FakePusherWebSocket(send_errors=[close_1012()])
    fresh = FakePusherWebSocket()
    connect_count = [0]

    async def reconnect_to_pusher(
        uid, sample_rate, retries=5, is_active=None, client_kind='unknown', audio_timeline=None
    ):
        connect_count[0] += 1
        return ws if connect_count[0] == 1 else fresh

    session = make_session(ws=ws, deps_overrides={'connect_to_pusher': reconnect_to_pusher})
    await session.connect()
    # Suppress the opcode-103 conversation announcement so the simulated close
    # lands on the opcode-101 audio send, which is what stamps failed_socket.
    session.last_synced_conversation_id = 'conv-1'
    session.audio_bytes_send(b'abcd', received_at=100.0)

    # First flush hits the 1012 close: the run returns to the buffer,
    # stamped with the socket it died on.
    await session._audio_bytes_flush()
    assert not session.pusher_connected
    assert session.audio_total_size == len(b'abcd')
    assert session.audio_runs[0].failed_socket is ws

    # The reconnect loop's connect() installs the fresh socket.
    await session.connect()
    assert session.pusher_ws is fresh
    assert session.pusher_connected

    # The next flush discards the unproven run once instead of replaying it.
    await session._audio_bytes_flush()
    assert session.audio_total_size == 0
    assert [frame for frame in fresh.sent if frame_type(frame) == 101] == []


@pytest.mark.anyio
async def test_flush_after_1012_retries_normally_when_same_socket_reconnects():
    """A 1012 close against a socket that comes back as the same installed
    socket is a plain retry: the stamped run is kept and re-sent."""
    ws = FakePusherWebSocket(send_errors=[close_1012()])
    session = make_session(ws=ws)
    await session.connect()
    # Suppress the opcode-103 announcement so the close lands on the stamped
    # opcode-101 audio send.
    session.last_synced_conversation_id = 'conv-1'
    session.audio_bytes_send(b'abcd', received_at=100.0)

    await session._audio_bytes_flush()
    assert session.audio_total_size == len(b'abcd')
    assert session.audio_runs[0].failed_socket is ws

    # The run already carries the dead socket's stamp from the failed send;
    # a reconnect that installs the same fake socket keeps the retry.
    await session.connect()
    assert session.pusher_ws is ws
    assert session.pusher_connected

    await session._audio_bytes_flush()
    assert session.audio_total_size == 0
    assert [frame_type(frame) for frame in ws.sent if frame_type(frame) == 101] == [101]
    assert ws.sent[-1][12:] == b'abcd'


def frame_type(frame: bytes) -> int:
    return struct.unpack("I", frame[:4])[0]
