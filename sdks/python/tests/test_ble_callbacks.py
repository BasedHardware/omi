from __future__ import annotations

import asyncio
from unittest.mock import patch, MagicMock

import pytest

from omi.ble import listen, listen_payload
from omi.constants import PACKET_HEADER_BYTES


class CustomAwaitable:
    def __init__(self, trace: list[str], tag: str):
        self.trace = trace
        self.tag = tag

    def __await__(self):
        async def _run():
            self.trace.append(f"custom:{self.tag}")
        return _run().__await__()


class MockBleakClient:
    def __init__(self, device_id: str):
        self.device_id = device_id
        self.notify_handler = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass

    async def start_notify(self, char_uuid, handler):
        self.notify_handler = handler


def test_listen_awaits_futures_and_custom_awaitables():
    async def _test():
        trace = []
        client_instance = MockBleakClient("fake-device")

        # 1. Test future
        async def future_handler(data: bytes):
            fut = asyncio.get_running_loop().create_future()
            fut.set_result(None)
            trace.append("future")
            return fut

        # 2. Test custom awaitable
        def custom_handler(data: bytes):
            return CustomAwaitable(trace, "packet")

        # 3. Test coroutine
        async def coro_handler(data: bytes):
            trace.append("coro")

        # 4. Test sync
        def sync_handler(data: bytes):
            trace.append("sync")

        with patch("omi.ble.BleakClient", return_value=client_instance):
            for handler in (future_handler, custom_handler, coro_handler, sync_handler):
                notify_captured = []

                async def fake_sleep(_sec):
                    # Trigger handler and stop
                    await client_instance.notify_handler("sender", bytearray(b"\x00\x01\x02\x03\x04"))
                    raise asyncio.CancelledError()

                with patch("asyncio.sleep", side_effect=fake_sleep):
                    try:
                        await listen("fake-device", handler)
                    except asyncio.CancelledError:
                        pass

        assert trace == ["future", "custom:packet", "coro", "sync"]

    asyncio.run(_test())


def test_listen_payload_awaits_futures_and_custom_awaitables():
    async def _test():
        trace = []
        client_instance = MockBleakClient("fake-device")

        # Custom awaitable for payload
        def custom_payload_handler(payload: bytes):
            assert payload == b"\x03\x04"  # Header bytes stripped
            return CustomAwaitable(trace, "payload")

        # Future for payload
        def future_payload_handler(payload: bytes):
            assert payload == b"\x03\x04"
            fut = asyncio.get_running_loop().create_future()
            fut.set_result(None)
            trace.append("future_payload")
            return fut

        with patch("omi.ble.BleakClient", return_value=client_instance):
            for handler in (custom_payload_handler, future_payload_handler):
                async def fake_sleep(_sec):
                    # 3 header bytes + 2 payload bytes
                    packet = b"\x00" * PACKET_HEADER_BYTES + b"\x03\x04"
                    await client_instance.notify_handler("sender", bytearray(packet))
                    raise asyncio.CancelledError()

                with patch("asyncio.sleep", side_effect=fake_sleep):
                    try:
                        await listen_payload("fake-device", handler)
                    except asyncio.CancelledError:
                        pass

        assert trace == ["custom:payload", "future_payload"]

    asyncio.run(_test())
