"""One dead pusher socket is one fault line, not one per observing task.

Failure-Class: FC-one-socket-close-logged-per-observing-task — instance in
backend/utils/listen_pusher_session.py (2026-10-20 sensor, backend-listen
x55/30m): a session's pusher socket died without a close frame and three
concurrent session tasks — the receive loop, the audio-run flush and the
transcript flush — each re-observed the same death and each logged its own
severity-classified ERROR line ("Pusher audio_bytes Connection closed: no
close frame received or sent" plus its siblings), so one socket death
produced up to three identical faults in the log while the session itself
self-healed through the existing reconnect loop. The earlier severity
boundary had already classified closes by the statement their code carries
(1012 restart = INFO), but the no-frame member — a close that carries no
receiver statement at all — kept per-task ERROR, and the two remaining send
paths (heartbeat, speaker-sample request) had no socket-identity guard at
all: a close raised by a socket a reconnect had already replaced still tore
down the fresh connection from those paths and logged an unowned error.

Contract under test:

- classification buckets every close shape by the statement its code
  carries (restart / no_frame / clean / abnormal) and feeds
  ``pusher_close_events_total{close_class,deduped}``;
- a close whose code is absent keeps ERROR on the first observation but is
  demoted to INFO on every later in-flight observation while the session's
  reconnect is already armed — one socket death, one ERROR;
- the demotion window is per session, closes again when a reconnect
  completes, and never changes recovery: ``_mark_disconnected`` stays
  idempotent and one reconnect loop owns the replacement socket;
- the heartbeat and speaker-sample send paths follow the same identity rule
  as the receive and flush paths: a close from a replaced socket is
  informational and never tears down the freshly installed connection, a
  real close from the installed socket still marks the session
  disconnected, and a non-close transport error keeps its plain ERROR
  without disconnecting;
- a no-frame close changes nothing about data flow: buffered runs and
  segments stay queued for the reconnect replay, v2 envelopes turn
  uncertain, legacy runs keep their failed-socket stamp and the
  discard-on-replacement contract, and the log line keeps the exact
  production message shape.
"""

import asyncio
import logging
import struct

import pytest
from websockets.exceptions import ConnectionClosed, ConnectionClosedError
from websockets.frames import Close

from utils.listen_pusher_session import (
    PUSHER_CLOSE_CLASS_ABNORMAL,
    PUSHER_CLOSE_CLASS_CLEAN,
    PUSHER_CLOSE_CLASS_NO_FRAME,
    PUSHER_CLOSE_CLASS_RESTART,
    PUSHER_EXPECTED_RESTART_CLOSE_CODES,
    classify_pusher_close,
    log_pusher_connection_closed,
)
from tests.unit.utils.test_listen_pusher_session import FakePusherWebSocket, make_session

SESSION_LOGGER = 'utils.listen_pusher_session'


def close_no_frame() -> ConnectionClosed:
    """The production shape for an abruptly ended socket: no close frame at all."""
    return ConnectionClosedError(None, None)


def close_sent_only() -> ConnectionClosed:
    """A close where only our own FIN went out: still no receiver statement."""
    return ConnectionClosedError(None, Close(1000, 'normal closure'))


def close_1012() -> ConnectionClosed:
    """The pusher rolling-update close: received 1012, then sent 1012."""
    return ConnectionClosed(Close(1012, 'service restart'), Close(1012, 'service restart'), True)


def close_1000() -> ConnectionClosed:
    return ConnectionClosedError(Close(1000, 'normal closure'), None)


def close_1006() -> ConnectionClosed:
    return ConnectionClosedError(Close(1006, 'abnormal closure'), None)


def close_1011() -> ConnectionClosed:
    return ConnectionClosedError(Close(1011, 'internal error'), None)


def close_1015() -> ConnectionClosed:
    return ConnectionClosedError(Close(1015, 'tls handshake failed'), None)


def close_3000() -> ConnectionClosed:
    return ConnectionClosedError(Close(3000, 'custom'), None)


def close_4000() -> ConnectionClosed:
    return ConnectionClosedError(Close(4000, 'private'), None)


@pytest.fixture
def anyio_backend():
    return "asyncio"


def close_records(caplog, needle='connection closed'):
    return [r for r in caplog.records if r.name == SESSION_LOGGER and needle in r.getMessage().lower()]


def park_reconnect_forever(session):
    """Keep the reconnect loop parked in its backoff wait.

    The default fake ``wait_for_event`` returns immediately, which lets the
    reconnect loop reconnect within the test and flip the session back to
    CONNECTED — that would un-arm the dedupe window mid-test. Parking the
    loop makes "reconnect armed" a stable state the assertions can rely on.
    Returns the release event so a test can end the park (and the task).
    """
    release = asyncio.Event()

    async def park_in_backoff(event, timeout):
        await release.wait()
        return False

    session.deps.wait_for_event = park_in_backoff
    return release


def flip_active_then_false(session, active_ref):
    """A wait_for_event that ends the caller's loop after one beat."""

    async def flip(event, timeout):
        active_ref['active'] = False
        return False

    session.deps.wait_for_event = flip


def gate_lock_before_send(lock, started_event, proceed_event):
    """Hold ``lock`` until ``proceed_event`` so a second task can observe the
    same dead socket while this one is still in flight."""

    real_acquire = lock.acquire

    async def acquire_then_wait():
        await real_acquire()
        started_event.set()
        await proceed_event.wait()

    lock.acquire = acquire_then_wait  # type: ignore[method-assign]


def close_counter_totals():
    from utils.metrics import PUSHER_CLOSE_EVENTS_TOTAL

    totals = {}
    for metric in PUSHER_CLOSE_EVENTS_TOTAL.collect():
        for sample in metric.samples:
            if sample.name.endswith('_total'):
                key = (sample.labels.get('close_class'), sample.labels.get('deduped'))
                totals[key] = totals.get(key, 0.0) + sample.value
    return totals


# ---------------------------------------------------------------------------
# Close classification
# ---------------------------------------------------------------------------


def test_classify_restart_1012():
    assert classify_pusher_close(close_1012()) == PUSHER_CLOSE_CLASS_RESTART


def test_classify_no_frame_when_no_frame_received():
    assert classify_pusher_close(close_no_frame()) == PUSHER_CLOSE_CLASS_NO_FRAME


def test_classify_no_frame_when_only_sent_frame_exists():
    assert classify_pusher_close(close_sent_only()) == PUSHER_CLOSE_CLASS_NO_FRAME


def test_classify_clean_1000():
    assert classify_pusher_close(close_1000()) == PUSHER_CLOSE_CLASS_CLEAN


def test_classify_abnormal_1006():
    assert classify_pusher_close(close_1006()) == PUSHER_CLOSE_CLASS_ABNORMAL


def test_classify_abnormal_1011():
    assert classify_pusher_close(close_1011()) == PUSHER_CLOSE_CLASS_ABNORMAL


def test_classify_abnormal_1015():
    assert classify_pusher_close(close_1015()) == PUSHER_CLOSE_CLASS_ABNORMAL


def test_classify_abnormal_3000():
    assert classify_pusher_close(close_3000()) == PUSHER_CLOSE_CLASS_ABNORMAL


def test_classify_abnormal_4000():
    assert classify_pusher_close(close_4000()) == PUSHER_CLOSE_CLASS_ABNORMAL


def test_expected_restart_codes_stay_the_service_restart_singleton():
    assert PUSHER_EXPECTED_RESTART_CLOSE_CODES == frozenset({1012})


def test_close_class_constants_match_counter_label_vocabulary():
    assert PUSHER_CLOSE_CLASS_RESTART == 'restart'
    assert PUSHER_CLOSE_CLASS_NO_FRAME == 'no_frame'
    assert PUSHER_CLOSE_CLASS_CLEAN == 'clean'
    assert PUSHER_CLOSE_CLASS_ABNORMAL == 'abnormal'


def test_close_counter_registers_class_and_dedup_labels():
    from utils.metrics import PUSHER_CLOSE_EVENTS_TOTAL

    # Prometheus children only exist after first use; bump once so the
    # label keys are observable through collect().
    PUSHER_CLOSE_EVENTS_TOTAL.labels(close_class='restart', deduped='false').inc()
    labels = set()
    for metric in PUSHER_CLOSE_EVENTS_TOTAL.collect():
        for sample in metric.samples:
            labels.update(sample.labels.keys())
    assert {'close_class', 'deduped'} <= labels


def test_close_counter_help_lists_all_four_classes():
    from utils.metrics import PUSHER_CLOSE_EVENTS_TOTAL

    documentation = PUSHER_CLOSE_EVENTS_TOTAL._documentation
    for class_name in ('restart', 'no_frame', 'abnormal', 'clean'):
        assert class_name in documentation


def test_close_severity_log_keeps_the_exception_text_verbatim(caplog):
    e = close_no_frame()
    with caplog.at_level(logging.INFO, logger=SESSION_LOGGER):
        log_pusher_connection_closed(
            logging.getLogger(SESSION_LOGGER),
            e,
            'Pusher audio_bytes Connection closed',
            uid='uid-1',
            session_id='session-1',
        )
    records = close_records(caplog)
    assert len(records) == 1
    assert str(e) in records[0].getMessage()


def test_log_function_without_session_keeps_code_only_classification(caplog):
    """The documented call shape (no session kwarg) keeps the earlier
    severity contract exactly: severity follows the close code alone,
    nothing is deduped."""
    logger = logging.getLogger(SESSION_LOGGER)
    with caplog.at_level(logging.INFO, logger=SESSION_LOGGER):
        log_pusher_connection_closed(
            logger, close_no_frame(), 'Pusher audio_bytes Connection closed', uid='u', session_id='s'
        )
        log_pusher_connection_closed(
            logger, close_1012(), 'Pusher audio_bytes Connection closed', uid='u', session_id='s'
        )
    records = close_records(caplog)
    assert [r.levelno for r in records] == [logging.ERROR, logging.INFO]


def test_log_function_with_connected_session_logs_first_observation_error(caplog):
    """A session reference with a CONNECTED state is a first observation even
    though the caller supplied the session — dedupe is state-driven, not
    call-driven."""
    ws = FakePusherWebSocket()
    session = make_session(ws=ws)
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


@pytest.mark.anyio
async def test_has_armed_reconnect_lifecycle_across_close_and_recovery():
    ws = FakePusherWebSocket(send_errors=[close_no_frame()])
    session = make_session(ws=ws)
    await session.connect()
    assert not session.has_armed_reconnect()

    session.audio_bytes_send(b'abcd', received_at=100.0)
    await session._audio_bytes_flush()
    assert session.has_armed_reconnect(), 'the close observation arms the window'

    deadline = asyncio.get_event_loop().time() + 5
    while not (session.pusher_connected and not session.has_armed_reconnect()):
        assert asyncio.get_event_loop().time() < deadline, 'reconnect never recovered'
        await asyncio.sleep(0.02)
    assert not session.has_armed_reconnect(), 'a completed reconnect closes the window'


@pytest.mark.anyio
async def test_recovery_reset_applies_across_send_paths(caplog):
    """A heartbeat-observed close after a flush death and a completed
    recovery is ERROR again — the window reset is global to the session, not
    per send path."""
    ws = FakePusherWebSocket(send_errors=[close_no_frame(), close_no_frame()])
    active_ref = {"active": True}
    session = make_session(ws=ws, active_ref=active_ref)
    await session.connect()
    session.last_synced_conversation_id = 'conv-1'
    session.audio_bytes_send(b'abcd', received_at=100.0)

    await session._audio_bytes_flush()
    deadline = asyncio.get_event_loop().time() + 5
    while not (session.pusher_connected and not session.has_armed_reconnect()):
        assert asyncio.get_event_loop().time() < deadline, 'reconnect never recovered'
        await asyncio.sleep(0.02)

    flip_active_then_false(session, active_ref)
    caplog.clear()
    with caplog.at_level(logging.INFO, logger=SESSION_LOGGER):
        await asyncio.wait_for(session.pusher_heartbeat(), timeout=10)

    records = close_records(caplog, 'pusher heartbeat connection closed')
    assert [r.levelno for r in records] == [logging.ERROR]


# ---------------------------------------------------------------------------
# One socket death, one ERROR (the demotion boundary)
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_first_no_frame_close_logs_error_and_arms_reconnect(caplog):
    ws = FakePusherWebSocket(send_errors=[close_no_frame()])
    session = make_session(ws=ws)
    release = park_reconnect_forever(session)
    await session.connect()
    session.audio_bytes_send(b'abcd', received_at=100.0)

    with caplog.at_level(logging.INFO, logger=SESSION_LOGGER):
        await session._audio_bytes_flush()

    records = close_records(caplog)
    assert [r.levelno for r in records] == [logging.ERROR]
    assert 'no close frame received or sent' in records[0].getMessage()
    assert session.has_armed_reconnect()
    assert session.audio_total_size == len(b'abcd')
    release.set()
    session.reconnect_task.cancel()


@pytest.mark.anyio
async def test_in_flight_sibling_flush_of_the_same_death_is_demoted_to_info(caplog):
    """The audio flush's close arms the reconnect; a transcript flush already
    past its guard observes the same dead socket and must log INFO."""
    ws = FakePusherWebSocket(send_errors=[close_no_frame(), close_no_frame()])
    session = make_session(ws=ws)
    release = park_reconnect_forever(session)
    await session.connect()
    session.audio_bytes_send(b'abcd', received_at=100.0)
    session.transcript_send([{'id': 'seg-1', 'text': 'hello'}])
    audio_started = asyncio.Event()
    sibling_started = asyncio.Event()
    gate_lock_before_send(session.audio_flush_lock, audio_started, sibling_started)

    async def sibling_flush():
        sibling_started.set()
        await audio_started.wait()
        await session._transcript_flush()

    with caplog.at_level(logging.INFO, logger=SESSION_LOGGER):
        await asyncio.gather(session._audio_bytes_flush(), sibling_flush())

    records = close_records(caplog)
    assert len([r for r in records if r.levelno == logging.ERROR]) == 1
    assert len([r for r in records if r.levelno == logging.INFO]) == 1
    assert 'no close frame received or sent' in records[1].getMessage()
    assert not session.pusher_connected
    release.set()
    session.reconnect_task.cancel()


@pytest.mark.anyio
async def test_concurrent_flushes_produce_exactly_one_error(caplog):
    """The regression: two flush tasks racing on the same dead socket in one
    drain window must produce exactly one ERROR line between them."""
    ws = FakePusherWebSocket(send_errors=[close_no_frame(), close_no_frame()])
    session = make_session(ws=ws)
    release = park_reconnect_forever(session)
    await session.connect()
    session.audio_bytes_send(b'abcd', received_at=100.0)
    session.transcript_send([{'id': 'seg-1', 'text': 'hello'}])

    with caplog.at_level(logging.INFO, logger=SESSION_LOGGER):
        await asyncio.gather(session._audio_bytes_flush(), session._transcript_flush())

    records = close_records(caplog)
    assert len([r for r in records if r.levelno == logging.ERROR]) == 1
    # Data contracts unchanged: both payloads re-buffered for the replay.
    assert session.audio_total_size == len(b'abcd')
    assert len(session.segment_buffers) == 1
    release.set()
    session.reconnect_task.cancel()


@pytest.mark.anyio
async def test_receive_loop_close_then_in_flight_flush_is_one_fault(caplog):
    """The flush must already be inside the send when the receive loop's close
    arms the reconnect — a flush that starts after the death short-circuits
    on its ``pusher_connected`` guard and logs nothing (correctly)."""
    active_ref = {"active": True}
    ws = FakePusherWebSocket()
    session = make_session(ws=ws, active_ref=active_ref)
    release = park_reconnect_forever(session)
    await session.connect()
    await session.request_conversation_processing('conv-1')
    session.audio_bytes_send(b'abcd', received_at=100.0)

    recv_close_raised = asyncio.Event()
    flush_in_send = asyncio.Event()

    async def send_then_die_with_socket(data):
        # The socket dies underneath the in-flight send: the receive loop's
        # close arms the reconnect while this send is still parked, then the
        # send observes the same death.
        flush_in_send.set()
        await recv_close_raised.wait()
        raise close_no_frame()

    ws.send = send_then_die_with_socket

    calls = {'n': 0}

    async def recv():
        calls['n'] += 1
        if calls['n'] == 1:
            active_ref['active'] = False
            recv_close_raised.set()
            raise close_no_frame()
        await asyncio.sleep(30)

    ws.recv = recv

    async def run_receive():
        await asyncio.wait_for(session.pusher_receive(), timeout=10)

    with caplog.at_level(logging.INFO, logger=SESSION_LOGGER):
        receive_task = asyncio.create_task(run_receive())
        flush_task = asyncio.create_task(session._audio_bytes_flush())
        # The flush enters its send and parks; the receive loop's close then
        # arms the reconnect while the flush is still in flight.
        await asyncio.wait_for(flush_in_send.wait(), timeout=5)
        await asyncio.wait_for(receive_task, timeout=10)
        await asyncio.wait_for(flush_task, timeout=10)

    records = close_records(caplog)
    assert len([r for r in records if r.levelno == logging.ERROR]) == 1
    assert len([r for r in records if r.levelno == logging.INFO]) == 1
    assert session.audio_total_size == len(b'abcd')
    release.set()
    session.reconnect_task.cancel()


@pytest.mark.anyio
async def test_receive_loop_alone_logs_single_error_and_arms(caplog):
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
            raise close_no_frame()
        await asyncio.sleep(30)

    ws.recv = recv
    with caplog.at_level(logging.INFO, logger=SESSION_LOGGER):
        await asyncio.wait_for(session.pusher_receive(), timeout=10)

    records = close_records(caplog)
    assert [r.levelno for r in records] == [logging.ERROR]
    assert not session.pusher_connected
    assert session.has_armed_reconnect()
    session.reconnect_task.cancel()


@pytest.mark.anyio
async def test_restart_close_logs_info_and_arms_recovery_once(caplog):
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
            raise close_1012()
        await asyncio.sleep(30)

    ws.recv = recv
    with caplog.at_level(logging.INFO, logger=SESSION_LOGGER):
        await asyncio.wait_for(session.pusher_receive(), timeout=10)

    records = close_records(caplog)
    assert [r.levelno for r in records] == [logging.INFO]
    assert not session.pusher_connected
    session.reconnect_task.cancel()


@pytest.mark.anyio
async def test_abnormal_1011_first_error_then_in_flight_sibling_info(caplog):
    ws = FakePusherWebSocket(send_errors=[close_1011(), close_1011()])
    session = make_session(ws=ws)
    release = park_reconnect_forever(session)
    await session.connect()
    session.audio_bytes_send(b'abcd', received_at=100.0)
    session.transcript_send([{'id': 'seg-1', 'text': 'hello'}])
    audio_started = asyncio.Event()
    sibling_started = asyncio.Event()
    gate_lock_before_send(session.audio_flush_lock, audio_started, sibling_started)

    async def sibling_flush():
        sibling_started.set()
        await audio_started.wait()
        await session._transcript_flush()

    with caplog.at_level(logging.INFO, logger=SESSION_LOGGER):
        await asyncio.gather(session._audio_bytes_flush(), sibling_flush())

    records = close_records(caplog)
    assert len([r for r in records if r.levelno == logging.ERROR]) == 1
    assert len([r for r in records if r.levelno == logging.INFO]) == 1
    release.set()
    session.reconnect_task.cancel()


@pytest.mark.anyio
async def test_clean_1000_first_error_then_in_flight_sibling_info(caplog):
    ws = FakePusherWebSocket(send_errors=[close_1000(), close_1000()])
    session = make_session(ws=ws)
    release = park_reconnect_forever(session)
    await session.connect()
    session.audio_bytes_send(b'abcd', received_at=100.0)
    session.transcript_send([{'id': 'seg-1', 'text': 'hello'}])
    audio_started = asyncio.Event()
    sibling_started = asyncio.Event()
    gate_lock_before_send(session.audio_flush_lock, audio_started, sibling_started)

    async def sibling_flush():
        sibling_started.set()
        await audio_started.wait()
        await session._transcript_flush()

    with caplog.at_level(logging.INFO, logger=SESSION_LOGGER):
        await asyncio.gather(session._audio_bytes_flush(), sibling_flush())

    records = close_records(caplog)
    assert len([r for r in records if r.levelno == logging.ERROR]) == 1
    assert len([r for r in records if r.levelno == logging.INFO]) == 1
    release.set()
    session.reconnect_task.cancel()


@pytest.mark.anyio
async def test_dedupe_window_is_per_session(caplog):
    """Two live sessions each observing their own first no-frame close both
    log ERROR — the demotion never crosses a session boundary."""
    ws_a = FakePusherWebSocket(send_errors=[close_no_frame()])
    ws_b = FakePusherWebSocket(send_errors=[close_no_frame()])
    session_a = make_session(ws=ws_a)
    session_b = make_session(ws=ws_b)
    release_a = park_reconnect_forever(session_a)
    release_b = park_reconnect_forever(session_b)
    await session_a.connect()
    await session_b.connect()
    session_a.audio_bytes_send(b'aaaa', received_at=100.0)
    session_b.audio_bytes_send(b'bbbb', received_at=100.0)

    with caplog.at_level(logging.INFO, logger=SESSION_LOGGER):
        await session_a._audio_bytes_flush()
        await session_b._audio_bytes_flush()

    records = close_records(caplog)
    assert [r.levelno for r in records] == [logging.ERROR, logging.ERROR]
    release_a.set()
    release_b.set()
    session_a.reconnect_task.cancel()
    session_b.reconnect_task.cancel()


@pytest.mark.anyio
async def test_demoted_observations_never_spawn_a_second_reconnect_loop(caplog):
    ws = FakePusherWebSocket(send_errors=[close_no_frame(), close_no_frame()])
    session = make_session(ws=ws)
    release = park_reconnect_forever(session)
    await session.connect()
    session.audio_bytes_send(b'abcd', received_at=100.0)
    session.transcript_send([{'id': 'seg-1', 'text': 'hello'}])

    with caplog.at_level(logging.INFO, logger=SESSION_LOGGER):
        await asyncio.gather(session._audio_bytes_flush(), session._transcript_flush())

    assert session.reconnect_task is not None and not session.reconnect_task.done()
    assert session.reconnect_state.value != 'connected'
    release.set()
    session.reconnect_task.cancel()


@pytest.mark.anyio
async def test_disconnect_marking_stays_idempotent_through_deduped_observations(caplog):
    ws = FakePusherWebSocket(send_errors=[close_no_frame(), close_no_frame()])
    session = make_session(ws=ws)
    release = park_reconnect_forever(session)
    await session.connect()

    with caplog.at_level(logging.INFO, logger=SESSION_LOGGER):
        await asyncio.gather(session._audio_bytes_flush(), session._transcript_flush())

    assert not session.pusher_connected
    assert session.reconnect_state.value == 'reconnect_backoff'
    release.set()
    session.reconnect_task.cancel()


@pytest.mark.anyio
async def test_buffers_survive_both_observations_of_one_death(caplog):
    ws = FakePusherWebSocket(send_errors=[close_no_frame(), close_no_frame()])
    session = make_session(ws=ws)
    release = park_reconnect_forever(session)
    await session.connect()
    session.audio_bytes_send(b'abcd', received_at=100.0)
    session.transcript_send([{'id': 'seg-1', 'text': 'hello'}])

    with caplog.at_level(logging.INFO, logger=SESSION_LOGGER):
        await asyncio.gather(session._audio_bytes_flush(), session._transcript_flush())

    assert session.audio_total_size == len(b'abcd')
    assert len(session.segment_buffers) == 1
    release.set()
    session.reconnect_task.cancel()


@pytest.mark.anyio
async def test_counter_counts_first_and_deduped_observations_of_no_frame_death():
    ws = FakePusherWebSocket(send_errors=[close_no_frame(), close_no_frame()])
    session = make_session(ws=ws)
    release = park_reconnect_forever(session)
    await session.connect()
    session.audio_bytes_send(b'abcd', received_at=100.0)
    session.transcript_send([{'id': 'seg-1', 'text': 'hello'}])

    await session._audio_bytes_flush()
    await session._transcript_flush()

    totals = close_counter_totals()
    assert totals.get(('no_frame', 'false'), 0.0) >= 1.0
    assert totals.get(('no_frame', 'true'), 0.0) >= 1.0
    release.set()
    session.reconnect_task.cancel()


@pytest.mark.anyio
async def test_counter_counts_typed_close_class_with_dedup(caplog):
    ws = FakePusherWebSocket(send_errors=[close_1011(), close_1011()])
    session = make_session(ws=ws)
    release = park_reconnect_forever(session)
    await session.connect()
    session.audio_bytes_send(b'abcd', received_at=100.0)
    session.transcript_send([{'id': 'seg-1', 'text': 'hello'}])

    with caplog.at_level(logging.INFO, logger=SESSION_LOGGER):
        await asyncio.gather(session._audio_bytes_flush(), session._transcript_flush())

    totals = close_counter_totals()
    assert totals.get(('abnormal', 'false'), 0.0) >= 1.0
    assert totals.get(('abnormal', 'true'), 0.0) >= 1.0
    release.set()
    session.reconnect_task.cancel()


@pytest.mark.anyio
async def test_demoted_line_keeps_the_full_close_text(caplog):
    ws = FakePusherWebSocket(send_errors=[close_no_frame(), close_no_frame()])
    session = make_session(ws=ws)
    release = park_reconnect_forever(session)
    await session.connect()
    session.audio_bytes_send(b'abcd', received_at=100.0)
    session.transcript_send([{'id': 'seg-1', 'text': 'hello'}])

    with caplog.at_level(logging.INFO, logger=SESSION_LOGGER):
        await asyncio.gather(session._audio_bytes_flush(), session._transcript_flush())

    infos = [r for r in close_records(caplog) if r.levelno == logging.INFO]
    assert len(infos) == 1
    assert 'no close frame received or sent' in infos[0].getMessage()
    assert 'uid-1' in infos[0].getMessage() and 'session-1' in infos[0].getMessage()
    release.set()
    session.reconnect_task.cancel()


# ---------------------------------------------------------------------------
# Heartbeat path identity rule
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_heartbeat_close_on_replaced_socket_is_info_and_keeps_fresh_connection(caplog):
    stale = FakePusherWebSocket(send_errors=[close_no_frame()])
    fresh = FakePusherWebSocket()
    active_ref = {"active": True}
    session = make_session(ws=stale, active_ref=active_ref)
    await session.connect()

    async def install_fresh_during_send(data):
        session.pusher_ws = fresh
        session.pusher_connected = True
        raise close_no_frame()

    stale.send = install_fresh_during_send
    flip_active_then_false(session, active_ref)
    with caplog.at_level(logging.INFO, logger=SESSION_LOGGER):
        await asyncio.wait_for(session.pusher_heartbeat(), timeout=10)

    assert session.pusher_ws is fresh
    assert session.pusher_connected
    assert session.reconnect_task is None
    records = close_records(caplog, 'replaced socket')
    assert [r.levelno for r in records] == [logging.INFO]


@pytest.mark.anyio
async def test_heartbeat_no_frame_close_on_installed_socket_marks_disconnected(caplog):
    ws = FakePusherWebSocket(send_errors=[close_no_frame()])
    active_ref = {"active": True}
    session = make_session(ws=ws, active_ref=active_ref)
    await session.connect()

    flip_active_then_false(session, active_ref)
    with caplog.at_level(logging.INFO, logger=SESSION_LOGGER):
        await asyncio.wait_for(session.pusher_heartbeat(), timeout=10)

    records = close_records(caplog)
    assert [r.levelno for r in records] == [logging.ERROR]
    assert 'Pusher heartbeat connection closed' in records[0].getMessage()
    assert not session.pusher_connected
    assert session.has_armed_reconnect()


@pytest.mark.anyio
async def test_heartbeat_abnormal_1011_close_marks_disconnected_with_error(caplog):
    ws = FakePusherWebSocket(send_errors=[close_1011()])
    active_ref = {"active": True}
    session = make_session(ws=ws, active_ref=active_ref)
    await session.connect()

    flip_active_then_false(session, active_ref)
    with caplog.at_level(logging.INFO, logger=SESSION_LOGGER):
        await asyncio.wait_for(session.pusher_heartbeat(), timeout=10)

    records = close_records(caplog)
    assert [r.levelno for r in records] == [logging.ERROR]
    assert not session.pusher_connected


@pytest.mark.anyio
async def test_heartbeat_restart_1012_close_stays_info(caplog):
    ws = FakePusherWebSocket(send_errors=[close_1012()])
    active_ref = {"active": True}
    session = make_session(ws=ws, active_ref=active_ref)
    await session.connect()

    flip_active_then_false(session, active_ref)
    with caplog.at_level(logging.INFO, logger=SESSION_LOGGER):
        await asyncio.wait_for(session.pusher_heartbeat(), timeout=10)

    records = close_records(caplog)
    assert [r.levelno for r in records] == [logging.INFO]
    assert not session.pusher_connected


@pytest.mark.anyio
async def test_heartbeat_replaced_socket_close_does_not_spawn_reconnect(caplog):
    stale = FakePusherWebSocket(send_errors=[close_no_frame()])
    fresh = FakePusherWebSocket()
    active_ref = {"active": True}
    session = make_session(ws=stale, active_ref=active_ref)
    await session.connect()

    async def install_fresh_during_send(data):
        session.pusher_ws = fresh
        session.pusher_connected = True
        raise close_no_frame()

    stale.send = install_fresh_during_send
    flip_active_then_false(session, active_ref)
    await asyncio.wait_for(session.pusher_heartbeat(), timeout=10)

    assert session.reconnect_task is None


@pytest.mark.anyio
async def test_heartbeat_non_close_transport_failure_stays_error_without_disconnect(caplog):
    ws = FakePusherWebSocket()
    active_ref = {"active": True}
    session = make_session(ws=ws, active_ref=active_ref)
    await session.connect()

    async def failing_send(data):
        raise RuntimeError('transport wedged')

    ws.send = failing_send
    flip_active_then_false(session, active_ref)
    with caplog.at_level(logging.INFO, logger=SESSION_LOGGER):
        await asyncio.wait_for(session.pusher_heartbeat(), timeout=10)

    assert session.pusher_connected
    assert session.reconnect_task is None
    errors = [r for r in caplog.records if r.name == SESSION_LOGGER and 'heartbeat send failed' in r.getMessage()]
    assert len(errors) == 1


# ---------------------------------------------------------------------------
# Speaker-sample request path identity rule
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_speaker_close_on_replaced_socket_is_info_and_request_stays_buffered(caplog):
    stale = FakePusherWebSocket(send_errors=[close_no_frame()])
    fresh = FakePusherWebSocket()
    session = make_session(ws=stale)
    await session.connect()

    async def install_fresh_during_send(data):
        session.pusher_ws = fresh
        session.pusher_connected = True
        raise close_no_frame()

    stale.send = install_fresh_during_send
    with caplog.at_level(logging.INFO, logger=SESSION_LOGGER):
        result = await session.send_speaker_sample_request('person-1', 'conv-1', ['seg-1'])

    assert result is False
    assert session.pusher_ws is fresh
    assert session.pusher_connected
    assert session.reconnect_task is None
    assert len(session.pending_speaker_sample_requests) == 1
    records = close_records(caplog, 'replaced socket')
    assert [r.levelno for r in records] == [logging.INFO]


@pytest.mark.anyio
async def test_speaker_no_frame_close_on_installed_socket_marks_disconnected(caplog):
    ws = FakePusherWebSocket(send_errors=[close_no_frame()])
    session = make_session(ws=ws)
    release = park_reconnect_forever(session)
    await session.connect()

    with caplog.at_level(logging.INFO, logger=SESSION_LOGGER):
        result = await session.send_speaker_sample_request('person-1', 'conv-1', ['seg-1'])

    assert result is False
    records = close_records(caplog)
    assert [r.levelno for r in records] == [logging.ERROR]
    assert 'Speaker sample request connection closed' in records[0].getMessage()
    assert not session.pusher_connected
    assert len(session.pending_speaker_sample_requests) == 1
    release.set()
    session.reconnect_task.cancel()


@pytest.mark.anyio
async def test_speaker_abnormal_1011_close_marks_disconnected_with_error(caplog):
    ws = FakePusherWebSocket(send_errors=[close_1011()])
    session = make_session(ws=ws)
    release = park_reconnect_forever(session)
    await session.connect()

    with caplog.at_level(logging.INFO, logger=SESSION_LOGGER):
        result = await session.send_speaker_sample_request('person-1', 'conv-1', ['seg-1'])

    assert result is False
    records = close_records(caplog)
    assert [r.levelno for r in records] == [logging.ERROR]
    assert not session.pusher_connected
    release.set()
    session.reconnect_task.cancel()


@pytest.mark.anyio
async def test_speaker_close_on_replaced_socket_keeps_request_for_fresh_replay(caplog):
    stale = FakePusherWebSocket(send_errors=[close_no_frame()])
    fresh = FakePusherWebSocket()
    session = make_session(ws=stale)
    await session.connect()

    async def install_fresh_during_send(data):
        session.pusher_ws = fresh
        session.pusher_connected = True
        raise close_no_frame()

    stale.send = install_fresh_during_send
    await session.send_speaker_sample_request('person-1', 'conv-1', ['seg-1'])

    assert list(session.pending_speaker_sample_requests) == [('person-1', 'conv-1', ['seg-1'])]


@pytest.mark.anyio
async def test_speaker_non_close_transport_failure_stays_error_without_disconnect(caplog):
    ws = FakePusherWebSocket()
    session = make_session(ws=ws)
    await session.connect()

    async def failing_send(data):
        raise RuntimeError('transport wedged')

    ws.send = failing_send
    with caplog.at_level(logging.INFO, logger=SESSION_LOGGER):
        result = await session.send_speaker_sample_request('person-1', 'conv-1', ['seg-1'])

    assert result is False
    assert session.pusher_connected
    assert session.reconnect_task is None
    assert len(session.pending_speaker_sample_requests) == 1
    errors = [
        r
        for r in caplog.records
        if r.name == SESSION_LOGGER and 'Failed to send speaker sample request' in r.getMessage()
    ]
    assert len(errors) == 1


@pytest.mark.anyio
async def test_speaker_happy_path_still_sends_and_returns_true(caplog):
    ws = FakePusherWebSocket()
    session = make_session(ws=ws)
    await session.connect()

    with caplog.at_level(logging.INFO, logger=SESSION_LOGGER):
        result = await session.send_speaker_sample_request('person-1', 'conv-1', ['seg-1'])

    assert result is True
    assert session.pusher_connected
    assert not session.pending_speaker_sample_requests
    assert close_records(caplog) == []


# ---------------------------------------------------------------------------
# Recovery cycles and preserved data contracts
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_recovery_cycle_resets_the_dedupe_window(caplog):
    """A later socket death after a completed reconnect is a first observation
    again: it logs ERROR, not a demoted line."""
    ws = FakePusherWebSocket(send_errors=[close_no_frame(), close_no_frame()])
    session = make_session(ws=ws)
    await session.connect()
    session.audio_bytes_send(b'abcd', received_at=100.0)

    await session._audio_bytes_flush()
    assert not session.pusher_connected
    deadline = asyncio.get_event_loop().time() + 5
    while not (session.pusher_connected and not session.has_armed_reconnect()):
        assert asyncio.get_event_loop().time() < deadline, 'reconnect never recovered'
        await asyncio.sleep(0.02)

    caplog.clear()
    with caplog.at_level(logging.INFO, logger=SESSION_LOGGER):
        await session._audio_bytes_flush()

    records = close_records(caplog)
    assert [r.levelno for r in records] == [logging.ERROR]


@pytest.mark.anyio
async def test_two_recovery_cycles_log_two_first_observations(caplog):
    ws = FakePusherWebSocket(send_errors=[close_no_frame(), close_no_frame(), close_no_frame()])
    session = make_session(ws=ws)
    await session.connect()

    session.audio_bytes_send(b'aa', received_at=100.0)
    await session._audio_bytes_flush()
    deadline = asyncio.get_event_loop().time() + 5
    while not (session.pusher_connected and not session.has_armed_reconnect()):
        assert asyncio.get_event_loop().time() < deadline, 'first reconnect never recovered'
        await asyncio.sleep(0.02)

    session.audio_bytes_send(b'bb', received_at=200.0)
    caplog.clear()
    with caplog.at_level(logging.INFO, logger=SESSION_LOGGER):
        await session._audio_bytes_flush()
    records = close_records(caplog)
    assert [r.levelno for r in records] == [logging.ERROR]

    while not (session.pusher_connected and not session.has_armed_reconnect()):
        assert asyncio.get_event_loop().time() < deadline + 5, 'second reconnect never recovered'
        await asyncio.sleep(0.02)

    session.audio_bytes_send(b'cc', received_at=300.0)
    caplog.clear()
    with caplog.at_level(logging.INFO, logger=SESSION_LOGGER):
        await session._audio_bytes_flush()
    records = close_records(caplog)
    assert [r.levelno for r in records] == [logging.ERROR]


@pytest.mark.anyio
async def test_counter_counts_one_not_deduped_observation_per_death_cycle():
    ws = FakePusherWebSocket(send_errors=[close_no_frame(), close_no_frame()])
    session = make_session(ws=ws)
    await session.connect()
    before = close_counter_totals().get(('no_frame', 'false'), 0.0)

    session.audio_bytes_send(b'aa', received_at=100.0)
    await session._audio_bytes_flush()
    deadline = asyncio.get_event_loop().time() + 5
    while not (session.pusher_connected and not session.has_armed_reconnect()):
        assert asyncio.get_event_loop().time() < deadline, 'reconnect never recovered'
        await asyncio.sleep(0.02)

    session.audio_bytes_send(b'bb', received_at=200.0)
    await session._audio_bytes_flush()

    after = close_counter_totals().get(('no_frame', 'false'), 0.0)
    assert after - before >= 2.0


@pytest.mark.anyio
async def test_error_line_keeps_the_production_sensor_signature_text(caplog):
    """The sentinel greps ``no close frame received or sent`` on the audio
    line — the first-observation ERROR must keep matching it verbatim."""
    ws = FakePusherWebSocket(send_errors=[close_no_frame()])
    session = make_session(ws=ws)
    release = park_reconnect_forever(session)
    await session.connect()
    session.audio_bytes_send(b'abcd', received_at=100.0)

    with caplog.at_level(logging.INFO, logger=SESSION_LOGGER):
        await session._audio_bytes_flush()

    records = close_records(caplog, 'pusher audio_bytes connection closed')
    assert len(records) == 1
    assert records[0].levelno == logging.ERROR
    assert 'no close frame received or sent' in records[0].getMessage()
    release.set()
    session.reconnect_task.cancel()


@pytest.mark.anyio
async def test_transcript_buffer_is_restored_after_no_frame_close(caplog):
    ws = FakePusherWebSocket(send_errors=[close_no_frame()])
    session = make_session(ws=ws)
    release = park_reconnect_forever(session)
    await session.connect()
    session.transcript_send([{'id': 'seg-1', 'text': 'hello'}])

    with caplog.at_level(logging.INFO, logger=SESSION_LOGGER):
        await session._transcript_flush()

    assert len(session.segment_buffers) == 1
    assert session.segment_buffers[0]['id'] == 'seg-1'
    release.set()
    session.reconnect_task.cancel()


@pytest.mark.anyio
async def test_v2_envelope_turns_uncertain_on_no_frame_close(caplog):
    ws = FakePusherWebSocket(send_errors=[close_no_frame()])
    session = make_session(ws=ws)
    release = park_reconnect_forever(session)
    await session.connect()
    session.audio_timeline_active = True
    session.last_synced_conversation_id = 'conv-1'
    session.audio_bytes_send(b'\x01' * 100, received_at=1000.0)

    with caplog.at_level(logging.INFO, logger=SESSION_LOGGER):
        await session._audio_bytes_flush()

    assert len(session.audio_runs) == 1
    assert session.audio_runs[0].uncertain
    release.set()
    session.reconnect_task.cancel()


@pytest.mark.anyio
async def test_legacy_run_keeps_failed_socket_stamp_on_no_frame_close(caplog):
    ws = FakePusherWebSocket(send_errors=[close_no_frame()])
    session = make_session(ws=ws)
    release = park_reconnect_forever(session)
    await session.connect()
    session.last_synced_conversation_id = 'conv-1'
    session.audio_bytes_send(b'abcd', received_at=100.0)

    with caplog.at_level(logging.INFO, logger=SESSION_LOGGER):
        await session._audio_bytes_flush()

    assert session.audio_runs[0].failed_socket is ws
    assert not session.audio_runs[0].uncertain
    release.set()
    session.reconnect_task.cancel()


@pytest.mark.anyio
async def test_legacy_unproven_run_discarded_once_after_replacement(caplog):
    """The d323ef75ad contract is unchanged by the no-frame classification:
    after a replacement socket is installed, the run stamped with the dead
    socket is discarded once, never replayed."""
    ws = FakePusherWebSocket(send_errors=[close_no_frame()])
    fresh = FakePusherWebSocket()
    connect_count = [0]

    async def reconnect_to_pusher(
        uid, sample_rate, retries=5, is_active=None, client_kind='unknown', audio_timeline=None
    ):
        connect_count[0] += 1
        return ws if connect_count[0] == 1 else fresh

    session = make_session(ws=ws, deps_overrides={'connect_to_pusher': reconnect_to_pusher})
    await session.connect()
    session.last_synced_conversation_id = 'conv-1'
    session.audio_bytes_send(b'abcd', received_at=100.0)

    await session._audio_bytes_flush()
    assert session.audio_runs[0].failed_socket is ws

    await session.connect()
    assert session.pusher_ws is fresh

    await session._audio_bytes_flush()
    assert session.audio_total_size == 0
    assert [struct.unpack('I', frame[:4])[0] for frame in fresh.sent if struct.unpack('I', frame[:4])[0] == 101] == []


@pytest.mark.anyio
async def test_legacy_run_retries_normally_when_same_socket_returns(caplog):
    ws = FakePusherWebSocket(send_errors=[close_no_frame()])
    session = make_session(ws=ws)
    await session.connect()
    session.last_synced_conversation_id = 'conv-1'
    session.audio_bytes_send(b'abcd', received_at=100.0)

    await session._audio_bytes_flush()
    assert session.audio_runs[0].failed_socket is ws

    await session.connect()
    assert session.pusher_ws is ws
    assert session.pusher_connected

    await session._audio_bytes_flush()
    assert session.audio_total_size == 0
    sent_101 = [struct.unpack('I', frame[:4])[0] for frame in ws.sent if struct.unpack('I', frame[:4])[0] == 101]
    assert sent_101 == [101]
    assert ws.sent[-1][12:] == b'abcd'
