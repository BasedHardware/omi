"""The keepalive's own close is churn, not an application fault.

Failure-Class: FC-keepalive-close-logged-as-application-error — instance in
backend/utils/listen_pusher_session.py (backend-listen 2026-11-01: ``Pusher
audio_bytes Connection closed: received 1011 (internal error) keepalive ping
timeout`` alone ran 380-1227 lines per hour across the fleet, spread evenly
over pods with no deploy correlation; the receive and transcript siblings
added their own per-task copies of the same deaths). When one end of the
internal listen <-> pusher lane misses its own keepalive deadline, the
websockets library fails the connection with ``1011 "keepalive ping
timeout"`` — a sentence that names the mechanism — and every session task
touching the socket observed the death as its own ERROR-severity fault line,
drowning the abnormal closes that share the generic ``1011`` code while the
session itself reconnected and replayed buffered work without operator
action. The peer on the other end of these deaths is a sibling pod or a
dozing phone: a CPU throttle, a radio doze, one GC pause. The companion root
cause lived in the pusher container command: uvicorn ran
``--ws-ping-interval 20 --ws-ping-timeout 20`` while the backend-listen
client declared ``ping_interval=30, ping_timeout=60``, so the server's
stricter clock killed peers a healthy client was still willing to wait for —
a pong arriving between 20s and 60s was a live pod answering late.

Contract under test:

- the keepalive close shape is recognized by the reason sentence the peer's
  RECEIVED close frame carries — never by the bare ``1011`` code, which every
  other internal failure also uses — and classified as its own
  ``keepalive_timeout`` class, ahead of every code-based bucket;
- the severity ladder demotes exactly that class: WARNING on a session's
  first observation, INFO on later in-flight observations under the existing
  per-session dedupe window; restart keeps INFO, no-frame and every generic
  abnormal code (1006/1011/1015/custom) keep first-observation ERROR;
- one socket death still produces one first-severity line across all five
  observing paths (audio flush, transcript flush, receive loop, heartbeat,
  speaker-sample request) — the keepalive class rides the same demotion
  window and the same recovery contracts as the no-frame class;
- recovery is identical under every class: buffers stay queued for the
  reconnect replay, ``_mark_disconnected`` stays idempotent, and the
  reconnect loop remains the single owner of the replacement socket;
- the keepalive budget is declared once in
  ``config/listen_pusher_keepalive.py``: the client connect passes those
  constants to ``websockets.connect``, the pusher Dockerfile CMD is rendered
  from them by ``scripts/generate_pusher_keepalive_flags.py``, and the
  rendered server clock is never stricter than the client's — the inversion
  that produced this failure class cannot re-enter through either end;
- the pusher side of the same cut classifies with the same sentence: the
  receive loop's ``WebSocketDisconnect`` carries the peer's close reason
  (uvicorn forwards it on the ASGI ``websocket.disconnect`` event) and the
  terminal session outcome demotes exactly the keepalive-verdict disconnect
  to ``cancelled`` while a generic ``1011`` and every real application
  failure stay ``failure``; starlette's ``WebSocket is not connected``
  lifecycle RuntimeError — the loop or the final flushes touching a
  transport whose disconnect already arrived — classifies as the peer-gone
  event it is (close 1006, one INFO line) instead of the
  ``Could not process audio`` application fault the catch-all booked for it;
- every observation still increments
  ``pusher_close_events_total{close_class,deduped}``, so the burst shape
  stays measurable after the log severity stops counting each task's copy.
"""

from __future__ import annotations

import asyncio
import logging
import subprocess
import sys
from pathlib import Path
from unittest import mock
from unittest.mock import MagicMock

import pytest
from starlette.websockets import WebSocketDisconnect
from websockets.exceptions import ConnectionClosed, ConnectionClosedError
from websockets.frames import Close

from config.listen_pusher_keepalive import (
    LISTEN_PUSHER_PING_INTERVAL_SECONDS,
    LISTEN_PUSHER_PING_TIMEOUT_SECONDS,
    LISTEN_PUSHER_PING_INTERVAL_UVICORN,
    LISTEN_PUSHER_PING_TIMEOUT_UVICORN,
    uvicorn_keepalive_args,
)
from utils.listen_pusher_session import (
    PUSHER_CLOSE_CLASS_ABNORMAL,
    PUSHER_CLOSE_CLASS_CLEAN,
    PUSHER_CLOSE_CLASS_KEEPALIVE,
    PUSHER_CLOSE_CLASS_NO_FRAME,
    PUSHER_CLOSE_CLASS_RESTART,
    PUSHER_KEEPALIVE_TIMEOUT_REASON,
    classify_pusher_close,
    is_keepalive_ping_timeout_close,
    log_pusher_connection_closed,
)
from utils.pusher_protocol import pusher_session_outcome

# Module-level router import on purpose: the fast-unit CPU guard measures the
# call phase only, and `routers.pusher` pulls the whole serving stack
# (database, Firestore, storage clients). Importing it inside a test charged
# its full 1.3s to that one test and failed the 1.0s budget; at module level
# it is file setup, exactly like the teardown-cancel boundary suite does.
import routers.pusher as pusher  # noqa: E402
from tests.unit.utils.test_listen_pusher_session import FakePusherWebSocket, make_session

SESSION_LOGGER = 'utils.listen_pusher_session'
REPO_ROOT = Path(__file__).resolve().parents[3]
GENERATOR = REPO_ROOT / 'backend' / 'scripts' / 'generate_pusher_keepalive_flags.py'
DOCKERFILE = REPO_ROOT / 'backend' / 'pusher' / 'Dockerfile'


# ---------------------------------------------------------------------------
# Production close shapes
# ---------------------------------------------------------------------------


def close_keepalive_received() -> ConnectionClosed:
    """The production shape: the peer's keepalive failed and it told us why.

    websockets sends ``1011 "keepalive ping timeout"`` from the side whose
    pong wait expired; the observing side receives that frame before the
    transport dies (backend-listen log line: ``received 1011 (internal
    error) keepalive ping timeout; then sent 1000 (OK)``).
    """
    return ConnectionClosedError(Close(1011, 'keepalive ping timeout'), Close(1000, 'OK'), True)


def close_keepalive_received_no_sent() -> ConnectionClosed:
    """The sibling shape seen when our own close never made it out."""
    return ConnectionClosedError(Close(1011, 'keepalive ping timeout'), None)


def close_keepalive_sent_only() -> ConnectionClosed:
    """Our keepalive failed; the peer never got to answer.

    This side knows its OWN clock expired, but the close carries no received
    statement about the peer — it must NOT take the keepalive class.
    """
    return ConnectionClosedError(None, Close(1011, 'keepalive ping timeout'))


def close_generic_1011() -> ConnectionClosed:
    """An internal error WITHOUT the keepalive sentence: a real fault."""
    return ConnectionClosedError(Close(1011, 'internal error'), None)


def close_no_frame() -> ConnectionClosed:
    return ConnectionClosedError(None, None)


def close_1012() -> ConnectionClosed:
    return ConnectionClosed(Close(1012, 'service restart'), Close(1012, 'service restart'), True)


def close_1000() -> ConnectionClosed:
    return ConnectionClosedError(Close(1000, 'normal closure'), None)


def close_1006() -> ConnectionClosed:
    return ConnectionClosedError(Close(1006, 'abnormal closure'), None)


def close_1015() -> ConnectionClosed:
    return ConnectionClosedError(Close(1015, 'tls handshake failed'), None)


def close_3000() -> ConnectionClosed:
    return ConnectionClosedError(Close(3000, 'custom'), None)


def close_records(caplog, needle='connection closed'):
    return [r for r in caplog.records if r.name == SESSION_LOGGER and needle in r.getMessage().lower()]


def park_reconnect_forever(session):
    """Keep the reconnect loop parked in its backoff wait (dedupe window stays open)."""
    release = asyncio.Event()

    async def park_in_backoff(event, timeout):
        await release.wait()
        return False

    session.deps.wait_for_event = park_in_backoff
    return release


def close_counter_totals():
    from utils.metrics import PUSHER_CLOSE_EVENTS_TOTAL

    totals = {}
    for metric in PUSHER_CLOSE_EVENTS_TOTAL.collect():
        for sample in metric.samples:
            if sample.name.endswith('_total'):
                key = (sample.labels.get('close_class'), sample.labels.get('deduped'))
                totals[key] = totals.get(key, 0.0) + sample.value
    return totals


@pytest.fixture
def anyio_backend():
    return "asyncio"


# ---------------------------------------------------------------------------
# Classification parity: the whole close-shape family
# ---------------------------------------------------------------------------


def test_classify_keepalive_received_frame():
    assert classify_pusher_close(close_keepalive_received()) == PUSHER_CLOSE_CLASS_KEEPALIVE


def test_classify_keepalive_received_frame_without_sent_frame():
    assert classify_pusher_close(close_keepalive_received_no_sent()) == PUSHER_CLOSE_CLASS_KEEPALIVE


def test_classify_generic_1011_stays_abnormal():
    """The bare 1011 — an internal error with no keepalive sentence — is a
    real fault and must not inherit the churn class."""
    assert classify_pusher_close(close_generic_1011()) == PUSHER_CLOSE_CLASS_ABNORMAL


def test_classify_keepalive_sent_only_is_not_keepalive():
    """A close where only OUR keepalive sentence went out carries no
    statement about the peer's keepalive."""
    assert classify_pusher_close(close_keepalive_sent_only()) == PUSHER_CLOSE_CLASS_NO_FRAME


def test_classify_no_frame_unchanged():
    assert classify_pusher_close(close_no_frame()) == PUSHER_CLOSE_CLASS_NO_FRAME


def test_classify_restart_1012_unchanged():
    assert classify_pusher_close(close_1012()) == PUSHER_CLOSE_CLASS_RESTART


def test_classify_clean_1000_unchanged():
    assert classify_pusher_close(close_1000()) == PUSHER_CLOSE_CLASS_CLEAN


def test_classify_abnormal_1006_unchanged():
    assert classify_pusher_close(close_1006()) == PUSHER_CLOSE_CLASS_ABNORMAL


def test_classify_abnormal_1015_unchanged():
    assert classify_pusher_close(close_1015()) == PUSHER_CLOSE_CLASS_ABNORMAL


def test_classify_custom_3000_unchanged():
    assert classify_pusher_close(close_3000()) == PUSHER_CLOSE_CLASS_ABNORMAL


def test_keepalive_class_takes_precedence_over_every_code_bucket():
    """The keepalive sentence wins even though its code collides with the
    abnormal bucket's 1011 — recognition is by the peer's reason, not the
    code."""
    assert classify_pusher_close(close_keepalive_received()) is not PUSHER_CLOSE_CLASS_ABNORMAL
    assert classify_pusher_close(close_keepalive_received()) == PUSHER_CLOSE_CLASS_KEEPALIVE


def test_is_keepalive_predicate_matches_received_reason_substring():
    assert is_keepalive_ping_timeout_close(close_keepalive_received())
    assert not is_keepalive_ping_timeout_close(close_generic_1011())
    assert not is_keepalive_ping_timeout_close(close_keepalive_sent_only())
    assert not is_keepalive_ping_timeout_close(close_no_frame())


def test_is_keepalive_predicate_requires_received_frame():
    """``rcvd is None`` can never be a keepalive close, whatever we sent."""
    e = ConnectionClosedError(None, Close(1011, PUSHER_KEEPALIVE_TIMEOUT_REASON))
    assert e.rcvd is None
    assert not is_keepalive_ping_timeout_close(e)


def test_keepalive_reason_constant_is_the_wire_sentence():
    """The matched sentence is exactly what the library sends
    (websockets ``fail_connection(CloseCode.INTERNAL_ERROR, ...)``)."""
    assert PUSHER_KEEPALIVE_TIMEOUT_REASON == 'keepalive ping timeout'


def test_keepalive_reason_substring_tolerates_suffixes():
    """A peer that appends detail to the sentence still classifies as
    keepalive churn."""
    e = ConnectionClosedError(Close(1011, 'keepalive ping timeout (60s)'), None)
    assert classify_pusher_close(e) == PUSHER_CLOSE_CLASS_KEEPALIVE


def test_every_legacy_shape_keeps_its_documented_bucket():
    """Full-family parity snapshot: the buckets the existing suites pin are
    untouched by the keepalive member's addition."""
    assert classify_pusher_close(close_1012()) == 'restart'
    assert classify_pusher_close(close_no_frame()) == 'no_frame'
    assert classify_pusher_close(close_1000()) == 'clean'
    assert classify_pusher_close(close_1006()) == 'abnormal'
    assert classify_pusher_close(close_generic_1011()) == 'abnormal'
    assert classify_pusher_close(close_1015()) == 'abnormal'
    assert classify_pusher_close(close_3000()) == 'abnormal'
    assert classify_pusher_close(close_keepalive_received()) == 'keepalive_timeout'


# ---------------------------------------------------------------------------
# Severity ladder: function level
# ---------------------------------------------------------------------------


def test_first_keepalive_close_logs_warning(caplog):
    session = make_session()
    with caplog.at_level(logging.INFO, logger=SESSION_LOGGER):
        log_pusher_connection_closed(
            logging.getLogger(SESSION_LOGGER),
            close_keepalive_received(),
            'Pusher audio_bytes Connection closed',
            uid='uid-1',
            session_id='session-1',
            session=session,
        )
    records = close_records(caplog)
    assert [r.levelno for r in records] == [logging.WARNING]


def test_first_keepalive_close_without_session_logs_warning(caplog):
    with caplog.at_level(logging.INFO, logger=SESSION_LOGGER):
        log_pusher_connection_closed(
            logging.getLogger(SESSION_LOGGER),
            close_keepalive_received(),
            'Pusher audio_bytes Connection closed',
            uid='uid-1',
            session_id='session-1',
        )
    records = close_records(caplog)
    assert [r.levelno for r in records] == [logging.WARNING]


def test_generic_1011_still_logs_error(caplog):
    session = make_session()
    with caplog.at_level(logging.INFO, logger=SESSION_LOGGER):
        log_pusher_connection_closed(
            logging.getLogger(SESSION_LOGGER),
            close_generic_1011(),
            'Pusher audio_bytes Connection closed',
            uid='uid-1',
            session_id='session-1',
            session=session,
        )
    records = close_records(caplog)
    assert [r.levelno for r in records] == [logging.ERROR]


def test_no_frame_still_logs_error(caplog):
    session = make_session()
    with caplog.at_level(logging.INFO, logger=SESSION_LOGGER):
        log_pusher_connection_closed(
            logging.getLogger(SESSION_LOGGER),
            close_no_frame(),
            'Pusher audio_bytes Connection closed',
            uid='uid-1',
            session_id='session-1',
            session=session,
        )
    records = close_records(caplog)
    assert [r.levelno for r in records] == [logging.ERROR]


def test_restart_still_logs_info(caplog):
    session = make_session()
    with caplog.at_level(logging.INFO, logger=SESSION_LOGGER):
        log_pusher_connection_closed(
            logging.getLogger(SESSION_LOGGER),
            close_1012(),
            'Pusher audio_bytes Connection closed',
            uid='uid-1',
            session_id='session-1',
            session=session,
        )
    records = close_records(caplog)
    assert [r.levelno for r in records] == [logging.INFO]


def test_custom_3000_still_logs_error(caplog):
    session = make_session()
    with caplog.at_level(logging.INFO, logger=SESSION_LOGGER):
        log_pusher_connection_closed(
            logging.getLogger(SESSION_LOGGER),
            close_3000(),
            'Pusher audio_bytes Connection closed',
            uid='uid-1',
            session_id='session-1',
            session=session,
        )
    records = close_records(caplog)
    assert [r.levelno for r in records] == [logging.ERROR]


def test_warning_line_keeps_exact_message_shape(caplog):
    """The demotion must not editorialize the message: operators grep the
    production sentence, and the parity of the line shape is what lets a
    severity-only change stay observable."""
    session = make_session()
    with caplog.at_level(logging.INFO, logger=SESSION_LOGGER):
        log_pusher_connection_closed(
            logging.getLogger(SESSION_LOGGER),
            close_keepalive_received(),
            'Pusher audio_bytes Connection closed',
            uid='uid-1',
            session_id='session-1',
            session=session,
        )
    message = close_records(caplog)[0].getMessage()
    assert message.startswith(
        'Pusher audio_bytes Connection closed: received 1011 (internal error) keepalive ping timeout'
    )
    assert message.endswith('uid-1 session-1')


# ---------------------------------------------------------------------------
# One socket death, one first-severity line (session parity, keepalive shape)
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_first_keepalive_close_in_flush_logs_warning_and_arms_reconnect(caplog):
    ws = FakePusherWebSocket(send_errors=[close_keepalive_received()])
    session = make_session(ws=ws)
    release = park_reconnect_forever(session)
    await session.connect()
    session.audio_bytes_send(b'abcd', received_at=100.0)

    with caplog.at_level(logging.INFO, logger=SESSION_LOGGER):
        await session._audio_bytes_flush()

    records = close_records(caplog)
    assert [r.levelno for r in records] == [logging.WARNING]
    assert 'keepalive ping timeout' in records[0].getMessage()
    assert session.has_armed_reconnect()
    assert session.audio_total_size == len(b'abcd'), 'buffer stays queued for the replay'
    release.set()
    session.reconnect_task.cancel()


@pytest.mark.anyio
async def test_keepalive_sibling_observation_during_same_death_is_info(caplog):
    """The transcript flush observing the same keepalive death while the
    audio flush already armed the reconnect logs INFO — one death, one
    first-severity line, same rule as the no-frame class."""
    ws = FakePusherWebSocket(send_errors=[close_keepalive_received(), close_keepalive_received()])
    session = make_session(ws=ws)
    release = park_reconnect_forever(session)
    await session.connect()
    session.audio_bytes_send(b'abcd', received_at=100.0)
    session.transcript_send([{'id': 'seg-1', 'text': 'hello'}])

    with caplog.at_level(logging.INFO, logger=SESSION_LOGGER):
        await asyncio.gather(session._audio_bytes_flush(), session._transcript_flush())

    records = close_records(caplog)
    assert len([r for r in records if r.levelno == logging.WARNING]) == 1
    assert len([r for r in records if r.levelno == logging.INFO]) == 1
    assert session.audio_total_size == len(b'abcd')
    assert len(session.segment_buffers) == 1
    release.set()
    session.reconnect_task.cancel()


@pytest.mark.anyio
async def test_concurrent_flushes_of_keepalive_death_produce_exactly_one_warning(caplog):
    ws = FakePusherWebSocket(send_errors=[close_keepalive_received(), close_keepalive_received()])
    session = make_session(ws=ws)
    release = park_reconnect_forever(session)
    await session.connect()
    session.audio_bytes_send(b'abcd', received_at=100.0)
    session.transcript_send([{'id': 'seg-1', 'text': 'hello'}])

    with caplog.at_level(logging.INFO, logger=SESSION_LOGGER):
        await asyncio.gather(session._audio_bytes_flush(), session._transcript_flush())

    records = close_records(caplog)
    assert len([r for r in records if r.levelno == logging.WARNING]) == 1
    assert not any(r.levelno == logging.ERROR for r in records)
    release.set()
    session.reconnect_task.cancel()


@pytest.mark.anyio
async def test_keepalive_death_after_recovery_is_warning_again(caplog):
    """A NEW keepalive death after a completed recovery is warned again —
    the demotion window closes when the reconnect completes, not forever."""
    ws = FakePusherWebSocket(send_errors=[close_keepalive_received(), close_keepalive_received()])
    session = make_session(ws=ws)
    await session.connect()
    session.audio_bytes_send(b'abcd', received_at=100.0)

    with caplog.at_level(logging.INFO, logger=SESSION_LOGGER):
        await session._audio_bytes_flush()
        deadline = asyncio.get_event_loop().time() + 5
        while not (session.pusher_connected and not session.has_armed_reconnect()):
            assert asyncio.get_event_loop().time() < deadline, 'reconnect never recovered'
            await asyncio.sleep(0.02)
        caplog.clear()
        session.audio_bytes_send(b'efgh', received_at=200.0)
        await session._audio_bytes_flush()

    records = close_records(caplog)
    assert [r.levelno for r in records] == [logging.WARNING]
    assert session.audio_total_size == len(b'abcd') + len(b'efgh'), 'both payloads stay queued for the replay'


@pytest.mark.anyio
async def test_keepalive_and_no_frame_share_identical_recovery_contract(caplog):
    """The class changes the severity, never the data flow: run the same
    death through both shapes and require identical session state."""
    states = []
    for close_shape in (close_keepalive_received(), close_no_frame()):
        ws = FakePusherWebSocket(send_errors=[close_shape, close_shape])
        session = make_session(ws=ws)
        release = park_reconnect_forever(session)
        await session.connect()
        session.audio_bytes_send(b'abcd', received_at=100.0)
        session.transcript_send([{'id': 'seg-1', 'text': 'hello'}])
        with caplog.at_level(logging.INFO, logger=SESSION_LOGGER):
            await asyncio.gather(session._audio_bytes_flush(), session._transcript_flush())
        states.append(
            (
                session.audio_total_size,
                len(session.segment_buffers),
                session.pusher_connected,
                session.has_armed_reconnect(),
            )
        )
        release.set()
        session.reconnect_task.cancel()
    assert states[0] == states[1]
    assert states[0] == (len(b'abcd'), 1, False, True)


@pytest.mark.anyio
async def test_keepalive_close_on_replaced_socket_never_touches_new_connection(caplog):
    """The identity rule is class-independent: a keepalive close raised by a
    socket a reconnect already replaced is informational and leaves the
    fresh connection connected."""
    ws = FakePusherWebSocket()
    session = make_session(ws=ws)
    park_reconnect_forever(session)
    await session.connect()
    stale = FakePusherWebSocket(send_errors=[close_keepalive_received()])

    original_send = session.pusher_ws.send

    async def send_then_swap(data):
        # The reconnect installs the replacement while this send is parked
        # inside the flush; the parked send then observes a stale death.
        await original_send(data)
        session.pusher_ws = stale
        session.pusher_connected = True
        raise close_keepalive_received()

    session.pusher_ws.send = send_then_swap

    session.audio_bytes_send(b'abcd', received_at=100.0)
    with caplog.at_level(logging.INFO, logger=SESSION_LOGGER):
        await session._audio_bytes_flush()

    assert session.pusher_ws is stale, 'the flush must not replace the installed socket'
    assert session.pusher_connected, 'a stale close must not disconnect the fresh connection'
    records = close_records(caplog, 'closed')
    assert any('replaced socket' in r.getMessage() for r in records)
    assert not any(r.levelno == logging.ERROR for r in records)
    assert session.reconnect_task is None, 'a stale close must never arm a reconnect'


@pytest.mark.anyio
async def test_receive_loop_keepalive_close_is_one_warning(caplog):
    """The receive loop is the third observer of the same death shape: one
    WARNING, recovery armed, no ERROR."""
    active_ref = {"active": True}
    ws = FakePusherWebSocket()
    session = make_session(ws=ws, active_ref=active_ref)
    park_reconnect_forever(session)
    await session.connect()
    await session.request_conversation_processing('conv-1')

    calls = {'n': 0}

    async def recv():
        calls['n'] += 1
        if calls['n'] == 1:
            active_ref['active'] = False
            raise close_keepalive_received()
        await asyncio.sleep(30)

    ws.recv = recv
    with caplog.at_level(logging.INFO, logger=SESSION_LOGGER):
        await asyncio.wait_for(session.pusher_receive(), timeout=10)

    records = close_records(caplog, 'pusher receive connection closed')
    assert [r.levelno for r in records] == [logging.WARNING]
    assert not session.pusher_connected
    assert session.has_armed_reconnect()
    session.reconnect_task.cancel()


@pytest.mark.anyio
async def test_heartbeat_keepalive_close_is_one_warning(caplog):
    """The heartbeat is the fourth observer: a first-observation keepalive
    death logs WARNING and arms recovery, same as the flush paths."""
    ws = FakePusherWebSocket(send_errors=[close_keepalive_received()])
    active_ref = {"active": True}
    session = make_session(ws=ws, active_ref=active_ref)
    park_reconnect_forever(session)
    await session.connect()

    async def end_loop_after_beat(event, timeout):
        active_ref['active'] = False
        return False

    session.deps.wait_for_event = end_loop_after_beat
    with caplog.at_level(logging.INFO, logger=SESSION_LOGGER):
        await asyncio.wait_for(session.pusher_heartbeat(), timeout=5)

    records = close_records(caplog, 'pusher heartbeat connection closed')
    assert [r.levelno for r in records] == [logging.WARNING]
    assert session.has_armed_reconnect()
    session.reconnect_task.cancel()


@pytest.mark.anyio
async def test_speaker_sample_keepalive_close_is_one_warning_and_stays_buffered(caplog):
    ws = FakePusherWebSocket(send_errors=[close_keepalive_received()])
    session = make_session(ws=ws)
    release = park_reconnect_forever(session)
    await session.connect()

    with caplog.at_level(logging.INFO, logger=SESSION_LOGGER):
        sent = await session.send_speaker_sample_request('person-1', 'conv-1', ['seg-1'])

    assert sent is False
    assert len(session.pending_speaker_sample_requests) == 1, 'request stays buffered for the replay'
    records = close_records(caplog)
    assert [r.levelno for r in records] == [logging.WARNING]
    release.set()
    session.reconnect_task.cancel()


@pytest.mark.anyio
async def test_mixing_classes_in_one_window_keeps_each_honest(caplog):
    """A keepalive death after a completed recovery is WARNING again even
    though the previous death in the same window was the same severity
    ladder — the window closes on recovery, not on the class."""
    ws = FakePusherWebSocket(send_errors=[close_keepalive_received(), close_keepalive_received()])
    session = make_session(ws=ws)
    await session.connect()
    with caplog.at_level(logging.INFO, logger=SESSION_LOGGER):
        session.audio_bytes_send(b'abcd', received_at=100.0)
        await session._audio_bytes_flush()
        deadline = asyncio.get_event_loop().time() + 5
        while not (session.pusher_connected and not session.has_armed_reconnect()):
            assert asyncio.get_event_loop().time() < deadline
            await asyncio.sleep(0.02)
        caplog.clear()
        session.audio_bytes_send(b'efgh', received_at=200.0)
        await session._audio_bytes_flush()

    records = close_records(caplog)
    assert [r.levelno for r in records] == [logging.WARNING]
    assert 'keepalive ping timeout' in records[0].getMessage()


# ---------------------------------------------------------------------------
# Metrics: the burst shape stays measurable
# ---------------------------------------------------------------------------


def test_first_keepalive_observation_counts_undeduped(caplog):
    session = make_session()
    before = close_counter_totals().get((PUSHER_CLOSE_CLASS_KEEPALIVE, 'false'), 0.0)
    with caplog.at_level(logging.INFO, logger=SESSION_LOGGER):
        log_pusher_connection_closed(
            logging.getLogger(SESSION_LOGGER),
            close_keepalive_received(),
            'Pusher audio_bytes Connection closed',
            uid='uid-1',
            session_id='session-1',
            session=session,
        )
    after = close_counter_totals().get((PUSHER_CLOSE_CLASS_KEEPALIVE, 'false'), 0.0)
    assert after == before + 1.0


@pytest.mark.anyio
async def test_deduped_keepalive_observation_counts_deduped(caplog):
    ws = FakePusherWebSocket(send_errors=[close_keepalive_received(), close_keepalive_received()])
    session = make_session(ws=ws)
    release = park_reconnect_forever(session)
    await session.connect()
    session.audio_bytes_send(b'abcd', received_at=100.0)
    session.transcript_send([{'id': 'seg-1', 'text': 'hello'}])

    before = close_counter_totals()
    with caplog.at_level(logging.INFO, logger=SESSION_LOGGER):
        await asyncio.gather(session._audio_bytes_flush(), session._transcript_flush())

    totals = close_counter_totals()
    assert (
        totals.get((PUSHER_CLOSE_CLASS_KEEPALIVE, 'false'), 0.0)
        == before.get((PUSHER_CLOSE_CLASS_KEEPALIVE, 'false'), 0.0) + 1.0
    )
    assert totals.get((PUSHER_CLOSE_CLASS_KEEPALIVE, 'true'), 0.0) >= 1.0
    release.set()
    session.reconnect_task.cancel()


def test_counter_help_names_the_keepalive_class():
    from utils.metrics import PUSHER_CLOSE_EVENTS_TOTAL

    assert 'keepalive_timeout' in PUSHER_CLOSE_EVENTS_TOTAL._documentation


# ---------------------------------------------------------------------------
# Config alignment: one budget, two ends
# ---------------------------------------------------------------------------


def test_lane_budget_constants_are_the_aligned_pair():
    assert LISTEN_PUSHER_PING_INTERVAL_SECONDS == 30.0
    assert LISTEN_PUSHER_PING_TIMEOUT_SECONDS == 60.0


def test_uvicorn_render_is_integer_seconds():
    assert LISTEN_PUSHER_PING_INTERVAL_UVICORN == 30
    assert LISTEN_PUSHER_PING_TIMEOUT_UVICORN == 60


def test_uvicorn_args_helper_renders_both_flags():
    args = uvicorn_keepalive_args()
    assert args == ['--ws-ping-interval=30', '--ws-ping-timeout=60']


def test_server_clock_is_never_stricter_than_the_client_clock():
    """The inversion that produced this failure class: a server that kills a
    peer its own client would have kept. Rendered server timeout must be >=
    the client's declared pong budget."""
    assert LISTEN_PUSHER_PING_TIMEOUT_UVICORN >= LISTEN_PUSHER_PING_TIMEOUT_SECONDS


def test_silent_but_alive_peer_survival_bound():
    """The longest a fully silent-but-alive peer can hold the socket is
    interval + timeout on the strictest end; document and pin the bound so a
    future edit re-derives it instead of discovering it in prod."""
    strictest_total = LISTEN_PUSHER_PING_INTERVAL_UVICORN + LISTEN_PUSHER_PING_TIMEOUT_UVICORN
    assert strictest_total == 90


def test_client_connect_uses_the_lane_constants(monkeypatch):
    """The dial path passes the config constants to ``websockets.connect`` —
    drift here would silently reintroduce a client/server mismatch."""
    import utils.pusher as pusher_module

    captured = {}

    async def fake_connect(url, **kwargs):
        captured['url'] = url
        captured.update(kwargs)
        return mock.MagicMock()

    monkeypatch.setattr(pusher_module.websockets, 'connect', fake_connect)
    monkeypatch.setattr(pusher_module, 'PusherAPI', 'https://pusher.example.internal')

    async def run():
        return await pusher_module._connect_to_trigger_pusher('uid-1', 8000)

    socket = asyncio.new_event_loop().run_until_complete(run())
    assert socket is not None
    assert captured['ping_interval'] == LISTEN_PUSHER_PING_INTERVAL_SECONDS
    assert captured['ping_timeout'] == LISTEN_PUSHER_PING_TIMEOUT_SECONDS


def test_generator_check_mode_passes_on_the_committed_dockerfile():
    result = subprocess.run(
        [sys.executable, str(GENERATOR), '--check'],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    assert result.returncode == 0, result.stderr
    assert 'match' in result.stdout


def test_dockerfile_cmd_matches_generator_render():
    """The Dockerfile's CMD is byte-identical to the generator's render —
    the pin that keeps the server's clock derived, not hardcoded."""
    sys.path.insert(0, str(REPO_ROOT / 'backend'))
    from scripts.generate_pusher_keepalive_flags import dockerfile_cmd

    dockerfile = DOCKERFILE.read_text(encoding='utf-8')
    assert dockerfile_cmd() in dockerfile


def test_dockerfile_no_longer_carries_the_stricter_20s_clock():
    dockerfile = DOCKERFILE.read_text(encoding='utf-8')
    assert '--ws-ping-interval 20' not in dockerfile
    assert '--ws-ping-timeout 20' not in dockerfile
    assert '--ws-ping-interval=30' in dockerfile
    assert '--ws-ping-timeout=60' in dockerfile


def test_generator_check_mode_fails_on_drift(tmp_path):
    """A hand-edited CMD (someone bumping one end again) fails the gate."""
    dockerfile = DOCKERFILE.read_text(encoding='utf-8')
    drifted = dockerfile.replace('--ws-ping-timeout=60', '--ws-ping-timeout=20')
    assert drifted != dockerfile
    DOCKERFILE.write_text(drifted, encoding='utf-8')
    try:
        result = subprocess.run(
            [sys.executable, str(GENERATOR), '--check'],
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
        )
        assert result.returncode == 1
        assert '--ws-ping-timeout=60' in result.stdout
    finally:
        DOCKERFILE.write_text(dockerfile, encoding='utf-8')


def test_old_flag_spelling_would_not_satisfy_the_gate():
    """The generator renders ``--flag=value`` argv form; the legacy
    space-separated spelling must not pass --check by accident."""
    dockerfile = DOCKERFILE.read_text(encoding='utf-8')
    legacy_form = dockerfile.replace('--ws-ping-interval=30', '--ws-ping-interval 30')
    assert legacy_form != dockerfile
    DOCKERFILE.write_text(legacy_form, encoding='utf-8')
    try:
        result = subprocess.run(
            [sys.executable, str(GENERATOR), '--check'],
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
        )
        assert result.returncode == 1
    finally:
        DOCKERFILE.write_text(dockerfile, encoding='utf-8')


# ---------------------------------------------------------------------------
# Server side of the cut: the session's terminal classification
# ---------------------------------------------------------------------------
#
# The pusher handler's receive loop is the mirror image of the client tasks
# above: the same keepalive close arrives there as WebSocketDisconnect with
# the peer's reason (uvicorn forwards it on the ASGI websocket.disconnect
# event), and starlette's lifecycle guards raise the not-connected sentence
# when the loop or the final flushes touch a transport whose disconnect
# already arrived. Both shapes used to book the session as an application
# fault (close 1011 + application_failed -> journey 'failure'; the catch-all
# 'Could not process audio' ERROR line). The contract under test: keepalive
# churn and peer transport ends classify as the transport events they are.


def outcome_for(close_code, *, application_failed=False, peer_keepalive_timeout=False):
    return pusher_session_outcome(
        close_code,
        application_failed=application_failed,
        peer_keepalive_timeout=peer_keepalive_timeout,
    )


def test_outcome_generic_1011_still_failure():
    """A generic 1011 — no keepalive sentence — remains an application fault."""
    assert outcome_for(1011) == 'failure'


def test_outcome_generic_1011_with_application_failure_still_failure():
    assert outcome_for(1011, application_failed=True) == 'failure'


def test_outcome_keepalive_1011_is_cancelled():
    """The keepalive verdict is churn: interrupted-session, not a fault."""
    assert outcome_for(1011, peer_keepalive_timeout=True) == 'cancelled'


def test_outcome_keepalive_with_real_application_failure_still_failure():
    """An application failure always wins over the transport verdict."""
    assert outcome_for(1011, application_failed=True, peer_keepalive_timeout=True) == 'failure'


def test_outcome_clean_close_unchanged():
    assert outcome_for(1000) == 'success'
    assert outcome_for(1001) == 'success'


def test_outcome_abnormal_1006_unchanged():
    assert outcome_for(1006) == 'cancelled'


def test_outcome_keepalive_flag_does_not_upgrade_1000():
    """The flag classifies the churn; it never rewrites a clean close's
    success meaning."""
    assert outcome_for(1000, peer_keepalive_timeout=True) == 'success'


def test_outcome_legacy_calls_without_flag_unchanged():
    """Every pre-existing two-argument call keeps its exact mapping."""
    assert outcome_for(1011, application_failed=True) == 'failure'
    assert outcome_for(1001) == 'success'
    assert outcome_for(1006) == 'cancelled'
    assert outcome_for(3000) == 'cancelled'


def test_outcome_drain_restart_1012_stays_cancelled():
    """The rolling-update close (uvicorn's server-closing verdict) was never
    a failure and must stay 'cancelled' through the new plumbing."""
    assert outcome_for(1012) == 'cancelled'


def test_outcome_no_status_1005_stays_cancelled():
    """uvicorn synthesizes disconnect code 1005 when the transport closed
    without a status: interrupted session, not a fault."""
    assert outcome_for(1005) == 'cancelled'


def test_outcome_invalid_frame_1003_stays_cancelled():
    assert outcome_for(1003) == 'cancelled'


def test_outcome_application_failure_beats_clean_close():
    """A session that failed after a clean close attempt keeps 'failure' —
    the flag never launders a real fault into success."""
    assert outcome_for(1000, application_failed=True) == 'failure'


def test_expected_restart_close_codes_do_not_absorb_1011():
    """The restart class is exactly {1012}: 1011 must never join it, or the
    keepalive/generic-1011 distinction below it would be unreachable."""
    from utils.listen_pusher_session import PUSHER_EXPECTED_RESTART_CLOSE_CODES

    assert PUSHER_EXPECTED_RESTART_CLOSE_CODES == frozenset({1012})


def test_keepalive_predicate_is_safe_for_duck_typed_shapes():
    """The predicate is defensive: an object without ``rcvd`` (a wrapped or
    foreign close shape) can never classify as keepalive churn."""

    class _Bare:
        pass

    assert not is_keepalive_ping_timeout_close(_Bare())  # type: ignore[arg-type]


def test_lane_config_module_is_the_single_import_source():
    """Both ends import the same module object — a second copy of the
    constants would reintroduce the drift this class fixes."""
    import config.listen_pusher_keepalive as cfg
    import utils.pusher as pusher_module

    assert pusher_module.LISTEN_PUSHER_PING_INTERVAL_SECONDS is cfg.LISTEN_PUSHER_PING_INTERVAL_SECONDS
    assert pusher_module.LISTEN_PUSHER_PING_TIMEOUT_SECONDS is cfg.LISTEN_PUSHER_PING_TIMEOUT_SECONDS


def test_router_imports_the_keepalive_reason_from_the_classifier():
    """The server side classifies with the same sentence constant the client
    side matches — one wire sentence, one definition."""
    import utils.listen_pusher_session as lps

    assert pusher.PUSHER_KEEPALIVE_TIMEOUT_REASON is lps.PUSHER_KEEPALIVE_TIMEOUT_REASON


class _RouterFakeWebSocket:
    """Minimal starlette-state WebSocket stub for the receive-loop tests."""

    def __init__(self, frames=()):
        import starlette.websockets as sw

        self.frames = list(frames)
        self.client_state = sw.WebSocketState.CONNECTED
        self.application_state = sw.WebSocketState.CONNECTED
        self.close_calls = []

    async def accept(self):
        return None

    async def send_bytes(self, data):
        return None

    async def send_text(self, data):
        return None

    async def receive_bytes(self):
        if self.frames:
            return self.frames.pop(0)
        raise WebSocketDisconnect(code=1011, reason=PUSHER_KEEPALIVE_TIMEOUT_REASON)

    async def close(self, code=1000, reason=None):
        self.close_calls.append(code)


@pytest.mark.anyio
async def test_receive_loop_keepalive_disconnect_books_cancelled_not_failure(monkeypatch, caplog):
    """The production server-side shape: the peer's keepalive sentence rides
    WebSocketDisconnect.reason into the receive loop; the session's terminal
    journey outcome is 'cancelled' and no 'Could not process audio' ERROR is
    logged."""
    from starlette.websockets import WebSocketDisconnect

    gate = _router_gate(monkeypatch)
    ws = _RouterFakeWebSocket()
    _stub_admission_reads(monkeypatch)
    journeys = _capture_journeys(monkeypatch)

    receive_task = asyncio.create_task(pusher._websocket_util_trigger(ws, 'uid-ka', 8000))
    await asyncio.wait_for(receive_task, timeout=10)

    assert journeys, 'journey attempt recorded'
    journeys[0].finish.assert_called_once_with('cancelled')
    assert not any('Could not process audio' in r.getMessage() for r in caplog.records)
    gate.assert_noop()


def _router_gate(monkeypatch):
    """Install a serving-forever gate stub over the handler's ReadinessGate.

    Mirrors the real waiter contract the teardown suite pins
    (``drain_wait_event`` + ``remove_drain_wait_event``), so the supervised
    wind-down watcher sees the same seam shape it sees in production."""

    class _Gate:
        def __init__(self):
            self.serving = True
            self._waiters = []

        def flip(self):
            self.serving = False
            for event in self._waiters:
                event.set()

        def is_serving(self):
            return self.serving

        def drain_age_seconds(self):
            return None

        def drain_wait_event(self):
            event = asyncio.Event()
            if not self.serving:
                event.set()
            else:
                self._waiters.append(event)
            return event

        def remove_drain_wait_event(self, event):
            try:
                self._waiters.remove(event)
            except ValueError:
                pass

        def assert_noop(self):
            assert self.serving, 'a churn-classified session must never flip the gate'

    gate = _Gate()
    monkeypatch.setattr(pusher, 'ReadinessGate', gate)
    return gate


def _stub_admission_reads(monkeypatch):
    monkeypatch.setattr(pusher, 'get_audio_bytes_webhook_seconds', lambda uid: None)
    monkeypatch.setattr(pusher, 'is_audio_bytes_app_enabled', lambda uid: False)
    monkeypatch.setattr(pusher.users_db, 'get_user_private_cloud_sync_enabled', lambda uid: False)
    monkeypatch.setattr(pusher, 'PUSHER_ACTIVE_WS_CONNECTIONS', MagicMock())
    monkeypatch.setattr(pusher, 'JourneyAttempt', _journey_sink.journey_factory)


class _JourneySink:
    def __init__(self):
        self.journeys = []

    def journey_factory(self, name):
        attempt = MagicMock()
        attempt.name = name
        self.journeys.append(attempt)
        return attempt


_journey_sink = _JourneySink()


def _capture_journeys(monkeypatch):
    _journey_sink.journeys.clear()
    return _journey_sink.journeys


@pytest.mark.anyio
async def test_receive_loop_not_connected_runtimeerror_books_cancelled_and_no_error_line(monkeypatch, caplog):
    """The dominant single-line ERROR family: starlette's lifecycle guard
    raises the not-connected sentence when the loop touches a gone transport.
    The catch-all must classify it as the disconnect it is — no
    'Could not process audio' ERROR, no application fault."""
    from starlette.websockets import WebSocketState

    _router_gate(monkeypatch)
    ws = _RouterFakeWebSocket()

    async def receive_bytes_then_not_connected():
        raise RuntimeError(pusher.PUSHER_NOT_CONNECTED_SENTINEL + '. Need to call "accept" first.')

    ws.receive_bytes = receive_bytes_then_not_connected
    _stub_admission_reads(monkeypatch)
    journeys = _capture_journeys(monkeypatch)

    receive_task = asyncio.create_task(pusher._websocket_util_trigger(ws, 'uid-nc', 8000))
    await asyncio.wait_for(receive_task, timeout=10)

    assert journeys, 'journey attempt recorded'
    journeys[0].finish.assert_called_once_with('cancelled')
    assert not any('Could not process audio' in r.getMessage() for r in caplog.records)


@pytest.mark.anyio
async def test_receive_loop_generic_fault_still_books_failure(monkeypatch, caplog):
    """The loud arm stays loud: a genuine application fault keeps the 1011 +
    'failure' booking and its ERROR line."""
    _router_gate(monkeypatch)
    ws = _RouterFakeWebSocket()

    async def receive_bytes_fault():
        raise RuntimeError('storage exploded mid-frame')

    ws.receive_bytes = receive_bytes_fault
    _stub_admission_reads(monkeypatch)
    journeys = _capture_journeys(monkeypatch)

    receive_task = asyncio.create_task(pusher._websocket_util_trigger(ws, 'uid-fault', 8000))
    await asyncio.wait_for(receive_task, timeout=10)

    assert journeys, 'journey attempt recorded'
    journeys[0].finish.assert_called_once_with('failure')
    assert any('Could not process audio' in r.getMessage() for r in caplog.records)


@pytest.mark.anyio
async def test_disconnect_without_keepalive_reason_keeps_failure_booking(monkeypatch, caplog):
    """A peer 1011 WITHOUT the keepalive sentence (any other internal error)
    keeps the failure booking — only the sentence demotes."""
    _router_gate(monkeypatch)
    ws = _RouterFakeWebSocket()

    async def receive_bytes_generic_1011():
        raise WebSocketDisconnect(code=1011, reason='internal error')

    ws.receive_bytes = receive_bytes_generic_1011
    _stub_admission_reads(monkeypatch)
    journeys = _capture_journeys(monkeypatch)

    receive_task = asyncio.create_task(pusher._websocket_util_trigger(ws, 'uid-g1011', 8000))
    await asyncio.wait_for(receive_task, timeout=10)

    assert journeys, 'journey attempt recorded'
    journeys[0].finish.assert_called_once_with('failure')


@pytest.mark.anyio
async def test_disconnect_keepalive_reason_variant_books_cancelled(monkeypatch, caplog):
    """A reason carrying the sentence plus library detail ('... (60s)')
    still demotes — the match is the sentence, not a byte-exact string."""
    _router_gate(monkeypatch)
    ws = _RouterFakeWebSocket()

    async def receive_bytes_variant():
        raise WebSocketDisconnect(code=1011, reason=PUSHER_KEEPALIVE_TIMEOUT_REASON + ' (60s)')

    ws.receive_bytes = receive_bytes_variant
    _stub_admission_reads(monkeypatch)
    journeys = _capture_journeys(monkeypatch)

    receive_task = asyncio.create_task(pusher._websocket_util_trigger(ws, 'uid-var', 8000))
    await asyncio.wait_for(receive_task, timeout=10)

    assert journeys, 'journey attempt recorded'
    journeys[0].finish.assert_called_once_with('cancelled')


@pytest.mark.anyio
async def test_plain_disconnect_without_status_stays_cancelled_not_failure(monkeypatch, caplog):
    """A disconnect carrying no status (uvicorn's 1005/1006 synthesis) keeps
    its interrupted-session meaning through the endpoint plumbing."""
    _router_gate(monkeypatch)
    ws = _RouterFakeWebSocket()

    async def receive_bytes_plain():
        raise WebSocketDisconnect(code=1006)

    ws.receive_bytes = receive_bytes_plain
    _stub_admission_reads(monkeypatch)
    journeys = _capture_journeys(monkeypatch)

    receive_task = asyncio.create_task(pusher._websocket_util_trigger(ws, 'uid-plain', 8000))
    await asyncio.wait_for(receive_task, timeout=10)

    assert journeys, 'journey attempt recorded'
    journeys[0].finish.assert_called_once_with('cancelled')
