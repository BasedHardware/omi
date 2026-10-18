"""Transport diagnostics retain useful close evidence without provider text."""

import asyncio
import logging
from types import SimpleNamespace

import pytest
import websockets
from websockets.exceptions import ConnectionClosedError
from websockets.frames import Close
from websockets.legacy.protocol import CloseCode, State, WebSocketCommonProtocol

from utils.stt import soniox
from utils.stt.failure_diagnostics import transport_failure_fields


def test_websockets_12_keepalive_timeout_preserves_local_sent_close_code():
    class PingTimeoutProtocol(WebSocketCommonProtocol):
        async def ping(self):
            return asyncio.get_running_loop().create_future()

    async def run():
        protocol = object.__new__(PingTimeoutProtocol)
        protocol.ping_interval = 0
        protocol.ping_timeout = 0.001
        protocol.debug = False
        protocol.logger = logging.getLogger(__name__)
        protocol.state = State.OPEN
        protocol.close_rcvd = None
        protocol.loop = asyncio.get_running_loop()
        protocol.close_connection_task = None
        protocol.write_frame_sync = lambda *_args: None

        await protocol.keepalive_ping()
        error = ConnectionClosedError(None, protocol.close_sent)
        assert error.sent.code is CloseCode.INTERNAL_ERROR
        fields = transport_failure_fields(error, 120)

        assert fields == ('ConnectionClosedError', -1, 1011, 'keepalive_ping_timeout', 'lt_5m')
        assert type(fields.sent_close_code) is int

    asyncio.run(run())


@pytest.mark.parametrize(
    'payload,expected_code',
    [(b'\x03\xf3peer close', 1011), (b'', 1005)],
)
def test_websockets_12_parsed_received_close_frame_preserves_code(payload, expected_code):
    received = Close.parse(payload)
    error = ConnectionClosedError(received, None)

    fields = transport_failure_fields(error, 120)

    assert fields.received_close_code == expected_code
    assert type(fields.received_close_code) is int
    assert fields.sent_close_code == -1


class _IntSubclass(int):
    pass


@pytest.mark.parametrize(
    'code,expected',
    [
        (_IntSubclass(1011), 1011),
        (1000, 1000),
        (4999, 4999),
        (True, -1),
        (False, -1),
        (999, -1),
        (5000, -1),
        ('1011', -1),
    ],
)
def test_close_codes_are_plain_bounded_non_bool_integers(code, expected):
    error = SimpleNamespace(rcvd=SimpleNamespace(code=code), sent=None)

    fields = transport_failure_fields(error, 120)

    assert fields.received_close_code == expected
    assert type(fields.received_close_code) is int


@pytest.mark.parametrize(
    'seconds,bucket',
    [(0, 'lt_30s'), (30, 'lt_5m'), (300, 'lt_30m'), (1800, 'lt_60m'), (3600, 'lt_300m'), (18000, 'ge_300m')],
)
def test_session_age_buckets(seconds, bucket):
    assert transport_failure_fields(TimeoutError('private'), seconds).session_age_bucket == bucket


def test_arbitrary_class_names_messages_and_invalid_codes_do_not_escape():
    custom = type('private_uid_and_secret', (Exception,), {})
    error = custom('private transcript')
    error.rcvd = SimpleNamespace(code='private', reason='private')
    error.sent = SimpleNamespace(code=9000, reason='private')
    assert transport_failure_fields(error, 1) == ('other', -1, -1, 'other', 'lt_30s')


def test_real_provider_websocket_close_is_logged_once_without_private_reason(caplog, monkeypatch):
    monkeypatch.setattr(soniox, 'resilient_reconnect_enabled', lambda: True)
    caplog.set_level(logging.WARNING, logger=soniox.__name__)

    async def run():
        async def provider(ws):
            await ws.close(code=1011, reason='private_provider_body')

        async with websockets.serve(provider, '127.0.0.1', 0) as server:
            port = server.sockets[0].getsockname()[1]
            async with websockets.connect(f'ws://127.0.0.1:{port}') as ws:
                socket = soniox.SafeSonioxSocket(ws, lambda _: None, asyncio.get_running_loop())
                try:
                    await asyncio.wait_for(socket._recv_task, timeout=3)
                    assert socket.is_connection_dead
                    assert socket.typed_death_reason == 'connection_lost'
                    # A send-loop race must not produce another close diagnostic.
                    socket._mark_dead('second death', transport_error=TimeoutError('private'), operation='send')
                finally:
                    socket._send_task.cancel()
                    await asyncio.gather(socket._send_task, return_exceptions=True)

    asyncio.run(run())
    records = [r.getMessage() for r in caplog.records if 'STT provider transport failure' in r.getMessage()]
    assert len(records) == 1
    assert 'exception_class=ConnectionClosedError' in records[0]
    assert 'received_close_code=1011' in records[0]
    assert 'operation=recv' in records[0]
    assert 'private' not in caplog.text


@pytest.mark.parametrize('operation', ['send', 'recv'])
def test_generic_transport_exception_uses_same_bounded_diagnostic(operation, caplog):
    caplog.set_level(logging.WARNING, logger=soniox.__name__)

    async def run():
        class Provider:
            async def send(self, data):
                raise ConnectionResetError('private_provider_body')

            def __aiter__(self):
                async def receive():
                    if operation == 'recv':
                        raise ConnectionResetError('private_provider_body')
                    await asyncio.Event().wait()
                    yield ''

                return receive()

        socket = soniox.SafeSonioxSocket(Provider(), lambda _: None, asyncio.get_running_loop())
        try:
            if operation == 'send':
                assert socket.send(b'\x00\x00')
            task = socket._send_task if operation == 'send' else socket._recv_task
            await asyncio.wait_for(task, timeout=3)
            assert socket.is_connection_dead
        finally:
            socket._send_task.cancel()
            socket._recv_task.cancel()
            await asyncio.gather(socket._send_task, socket._recv_task, return_exceptions=True)

    asyncio.run(run())
    assert f'operation={operation}' in caplog.text
    assert 'exception_class=ConnectionResetError' in caplog.text
    assert 'received_close_code=-1 sent_close_code=-1' in caplog.text
    assert 'private' not in caplog.text
