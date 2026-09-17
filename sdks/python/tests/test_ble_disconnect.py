from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest

from omi.ble import listen
from omi.bluetooth import listen_to_omi

_real_sleep = asyncio.sleep


class MockClient:
    """Bleak-like client that records the disconnected_callback it was given
    so a test can invoke it directly to simulate a real device disconnect."""

    def __init__(self, device_id, disconnected_callback=None):
        self.device_id = device_id
        self.disconnected_callback = disconnected_callback
        self.notify_handler = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass

    async def start_notify(self, char_uuid, handler):
        self.notify_handler = handler


async def _fast_sleep(_sec):
    # Keep the listener's poll loop from actually blocking for real time,
    # while still yielding control back to the event loop each iteration.
    await _real_sleep(0)


async def _drain_loop(iterations: int = 10) -> None:
    for _ in range(iterations):
        await _real_sleep(0)


def test_listen_raises_connection_error_on_disconnect():
    async def _test():
        captured_client = {}

        def _make_client(device_id, disconnected_callback=None):
            client = MockClient(device_id, disconnected_callback)
            captured_client["client"] = client
            return client

        with (
            patch("omi.ble.BleakClient", side_effect=_make_client),
            patch("asyncio.sleep", side_effect=_fast_sleep),
        ):
            task = asyncio.ensure_future(listen("fake-device", lambda data: None))
            await _drain_loop()

            client = captured_client["client"]
            assert (
                client.disconnected_callback is not None
            ), "listen() did not register a disconnected_callback"

            client.disconnected_callback(client)

            with pytest.raises(ConnectionError, match="fake-device"):
                await asyncio.wait_for(task, timeout=2)

    asyncio.run(_test())


def test_listen_to_omi_raises_connection_error_on_disconnect():
    async def _test():
        captured_client = {}

        def _make_client(mac_address, disconnected_callback=None):
            client = MockClient(mac_address, disconnected_callback)
            captured_client["client"] = client
            return client

        with (
            patch("omi.bluetooth.BleakClient", side_effect=_make_client),
            patch("asyncio.sleep", side_effect=_fast_sleep),
        ):
            task = asyncio.ensure_future(
                listen_to_omi(
                    "AA:BB:CC:DD:EE:FF", "char-uuid", lambda sender, data: None
                )
            )
            await _drain_loop()

            client = captured_client["client"]
            assert (
                client.disconnected_callback is not None
            ), "listen_to_omi() did not register a disconnected_callback"

            client.disconnected_callback(client)

            with pytest.raises(ConnectionError, match="AA:BB:CC:DD:EE:FF"):
                await asyncio.wait_for(task, timeout=2)

    asyncio.run(_test())


def test_listen_still_cancellable_while_connected():
    async def _test():
        with (
            patch("omi.ble.BleakClient", side_effect=MockClient),
            patch("asyncio.sleep", side_effect=_fast_sleep),
        ):
            task = asyncio.ensure_future(listen("fake-device", lambda data: None))
            await _drain_loop()

            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task

    asyncio.run(_test())
