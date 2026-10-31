"""Regression test for the real Bleak notification dispatch path.

``bleak.BleakClient.start_notify`` detects that a callback is a coroutine function and
wraps it so each notification runs in a *detached* ``asyncio.create_task`` (see
``bleak/__init__.py::BleakClient.start_notify``), not something the caller of
``start_notify`` ever awaits. ``tests/test_ble_callbacks.py`` only ever called the
captured handler directly and awaited that call, which exercises a path bleak itself
never takes and made a callback exception look like it would propagate when it would
not. This test swaps in a duck-typed backend (via ``BleakClient(backend=...)``) so the
real ``BleakClient.start_notify`` wrapping -- and its ``asyncio.create_task`` dispatch --
runs, then asserts the exception still reaches the ``listen()``/``listen_payload()``
caller instead of vanishing into that detached task.
"""

from __future__ import annotations

import asyncio
from functools import partial
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from bleak import BleakClient

from omi.ble import listen, listen_payload
from omi.constants import PACKET_HEADER_BYTES

_real_sleep = asyncio.sleep


async def _fast_sleep(_sec):
    # Keep listen()'s 1-second poll loop from blocking real test time.
    await _real_sleep(0)


class _FakeBackend:
    """Duck-typed stand-in for a Bleak backend; only what BleakClient touches."""

    def __init__(self, address, *, disconnected_callback=None, ready=None, **_kwargs):
        self.address = address
        self.disconnected_callback = disconnected_callback
        self._ready = ready
        self.is_connected = False
        self.notification = None
        self.services = SimpleNamespace(get_characteristic=lambda _uuid: SimpleNamespace())

    async def connect(self, **_kwargs):
        self.is_connected = True
        return True

    async def disconnect(self):
        self.is_connected = False
        return True

    async def start_notify(self, _characteristic, callback, **_kwargs):
        # BleakClient.start_notify already wrapped our coroutine handler so that
        # this stored `callback` dispatches via a detached asyncio.create_task.
        self.notification = callback
        if self._ready is not None and not self._ready.done():
            self._ready.set_result(self)

    def emit(self, payload: bytes = b"\x01\x02\x03\x04") -> None:
        self.notification(bytearray(payload))


@pytest.mark.parametrize("listen_fn", [listen, listen_payload])
def test_notification_callback_error_reaches_listener(listen_fn):
    async def _test():
        loop = asyncio.get_running_loop()
        ready = loop.create_future()
        failure = ValueError("audio consumer failed")

        def on_packet(_packet: bytes):
            raise failure

        backend_factory = partial(BleakClient, backend=_FakeBackend, ready=ready)
        with (
            patch("omi.ble.BleakClient", backend_factory),
            patch("asyncio.sleep", side_effect=_fast_sleep),
        ):
            listener = asyncio.ensure_future(listen_fn("fake-device", on_packet))
            try:
                backend = await asyncio.wait_for(ready, timeout=2)
                packet = (
                    b"\x00" * PACKET_HEADER_BYTES + b"audio"
                    if listen_fn is listen_payload
                    else b"audio"
                )
                # The real dispatcher runs `on_packet` inside a detached task created
                # by bleak itself, never awaited here -- unlike the handler-level tests.
                backend.emit(packet)
                with pytest.raises(ValueError, match="audio consumer failed"):
                    await asyncio.wait_for(listener, timeout=2)
            finally:
                listener.cancel()
                await asyncio.gather(listener, return_exceptions=True)

    asyncio.run(_test())


def test_notification_without_error_still_raises_on_disconnect():
    async def _test():
        loop = asyncio.get_running_loop()
        ready = loop.create_future()

        async def on_packet(_packet: bytes):
            return None

        backend_factory = partial(BleakClient, backend=_FakeBackend, ready=ready)
        with (
            patch("omi.ble.BleakClient", backend_factory),
            patch("asyncio.sleep", side_effect=_fast_sleep),
        ):
            listener = asyncio.ensure_future(listen("fake-device", on_packet))
            backend = await asyncio.wait_for(ready, timeout=2)
            backend.emit(b"\x01\x02\x03\x04")
            await _real_sleep(0)
            assert not listener.done(), "a successful callback must not end the listener"

            backend.disconnected_callback()
            with pytest.raises(ConnectionError, match="fake-device"):
                await asyncio.wait_for(listener, timeout=2)

    asyncio.run(_test())
