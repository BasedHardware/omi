"""Hermetic disconnect signaling for BLE listeners (issue #13290)."""

from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest

from omi.ble import listen, listen_payload
from omi.bluetooth import listen_to_omi
from omi.constants import PACKET_HEADER_BYTES


class DisconnectingBleakClient:
    instances: list["DisconnectingBleakClient"] = []

    def __init__(self, address: str, disconnected_callback=None, **_kwargs):
        self.address = address
        self.disconnected_callback = disconnected_callback
        self.notify_handler = None
        DisconnectingBleakClient.instances.append(self)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return False

    async def start_notify(self, _char_uuid, handler):
        self.notify_handler = handler


class LegacyBleakClient:
    """Constructor rejects disconnected_callback; only set_disconnected_callback exists."""

    instances: list["LegacyBleakClient"] = []

    def __init__(self, address: str):
        self.address = address
        self.disconnected_callback = None
        self.notify_handler = None
        LegacyBleakClient.instances.append(self)

    def set_disconnected_callback(self, callback):
        self.disconnected_callback = callback

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return False

    async def start_notify(self, _char_uuid, handler):
        self.notify_handler = handler


class BareBleakClient:
    """Rejects the keyword and has no setter — must not hang on idle sleep."""

    def __init__(self, address: str):
        self.address = address

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return False

    async def start_notify(self, _char_uuid, _handler):
        return None


class InnerTypeErrorClient:
    def __init__(self, address: str, disconnected_callback=None):
        raise TypeError("address must be a string")


class FailingNotifyClient(DisconnectingBleakClient):
    async def start_notify(self, _char_uuid, _handler):
        raise RuntimeError("start_notify failed")


def test_listen_raises_connection_error_on_disconnect():
    async def _test():
        DisconnectingBleakClient.instances.clear()
        packets: list[bytes] = []

        with patch("omi.ble.BleakClient", new=DisconnectingBleakClient):
            task = asyncio.create_task(listen("device-123", packets.append))
            await asyncio.sleep(0)
            client = DisconnectingBleakClient.instances[-1]
            assert client.disconnected_callback is not None
            assert client.notify_handler is not None

            await client.notify_handler("sender", bytearray(b"audio-data"))
            assert packets == [b"audio-data"]

            client.disconnected_callback(client)
            with pytest.raises(ConnectionError, match="Device device-123 disconnected"):
                await asyncio.wait_for(task, timeout=2)

    asyncio.run(_test())


def test_listen_payload_raises_connection_error_on_disconnect():
    async def _test():
        DisconnectingBleakClient.instances.clear()
        payloads: list[bytes] = []

        with patch("omi.ble.BleakClient", new=DisconnectingBleakClient):
            task = asyncio.create_task(listen_payload("device-456", payloads.append))
            await asyncio.sleep(0)
            client = DisconnectingBleakClient.instances[-1]
            packet = b"\x00" * PACKET_HEADER_BYTES + b"\x03\x04"
            await client.notify_handler("sender", bytearray(packet))
            assert payloads == [b"\x03\x04"]

            client.disconnected_callback(client)
            with pytest.raises(ConnectionError, match="Device device-456 disconnected"):
                await asyncio.wait_for(task, timeout=2)

    asyncio.run(_test())


def test_listen_to_omi_raises_connection_error_on_disconnect():
    async def _test():
        DisconnectingBleakClient.instances.clear()
        with patch("omi.ble.BleakClient", new=DisconnectingBleakClient):
            task = asyncio.create_task(
                listen_to_omi("AA:BB:CC:DD:EE:FF", "char-uuid", lambda _sender, _data: None)
            )
            await asyncio.sleep(0)
            client = DisconnectingBleakClient.instances[-1]
            client.disconnected_callback(client)
            with pytest.raises(ConnectionError, match="Device AA:BB:CC:DD:EE:FF disconnected"):
                await asyncio.wait_for(task, timeout=2)

    asyncio.run(_test())


def test_listen_clean_cancellation():
    async def _test():
        DisconnectingBleakClient.instances.clear()
        with patch("omi.ble.BleakClient", new=DisconnectingBleakClient):
            task = asyncio.create_task(listen("device-789", lambda _data: None))
            await asyncio.sleep(0)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task

    asyncio.run(_test())


def test_listen_legacy_client_fallback():
    async def _test():
        LegacyBleakClient.instances.clear()
        with patch("omi.ble.BleakClient", new=LegacyBleakClient):
            task = asyncio.create_task(listen("legacy-123", lambda _data: None))
            await asyncio.sleep(0)
            client = LegacyBleakClient.instances[-1]
            assert client.disconnected_callback is not None
            client.disconnected_callback(client)
            with pytest.raises(ConnectionError, match="Device legacy-123 disconnected"):
                await asyncio.wait_for(task, timeout=2)

    asyncio.run(_test())


def test_listen_to_omi_legacy_client_fallback():
    async def _test():
        LegacyBleakClient.instances.clear()
        with patch("omi.ble.BleakClient", new=LegacyBleakClient):
            task = asyncio.create_task(listen_to_omi("legacy-omi", "char-uuid", lambda _s, _d: None))
            await asyncio.sleep(0)
            client = LegacyBleakClient.instances[-1]
            assert client.disconnected_callback is not None
            client.disconnected_callback(client)
            with pytest.raises(ConnectionError, match="Device legacy-omi disconnected"):
                await asyncio.wait_for(task, timeout=2)

    asyncio.run(_test())


def test_listen_raises_when_no_disconnect_api():
    async def _test():
        with patch("omi.ble.BleakClient", new=BareBleakClient):
            with pytest.raises(TypeError, match="no disconnected_callback"):
                await listen("bare-1", lambda _data: None)

    asyncio.run(_test())


def test_listen_to_omi_raises_when_no_disconnect_api():
    async def _test():
        with patch("omi.ble.BleakClient", new=BareBleakClient):
            with pytest.raises(TypeError, match="no disconnected_callback"):
                await listen_to_omi("bare-omi", "char-uuid", lambda _s, _d: None)

    asyncio.run(_test())


def test_listen_reraises_constructor_typeerror_when_signature_accepts_callback():
    async def _test():
        with patch("omi.ble.BleakClient", new=InnerTypeErrorClient):
            with pytest.raises(TypeError, match="address must be a string"):
                await listen("bad-addr", lambda _data: None)

    asyncio.run(_test())


def test_listen_propagates_start_notify_errors():
    async def _test():
        DisconnectingBleakClient.instances.clear()
        with patch("omi.ble.BleakClient", new=FailingNotifyClient):
            with pytest.raises(RuntimeError, match="start_notify failed"):
                await listen("device-fail", lambda _data: None)

    asyncio.run(_test())
