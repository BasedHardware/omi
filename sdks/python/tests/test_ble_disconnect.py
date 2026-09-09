import asyncio
from unittest.mock import patch
import pytest

from omi.ble import listen, listen_payload
from omi.bluetooth import listen_to_omi


class DisconnectingBleakClient:
    instances = []

    def __init__(self, address: str, disconnected_callback=None):
        self.address = address
        self.disconnected_callback = disconnected_callback
        self.notify_handler = None
        self.connected = False
        DisconnectingBleakClient.instances.append(self)

    async def __aenter__(self):
        self.connected = True
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self.connected = False

    async def start_notify(self, char_uuid, handler):
        self.notify_handler = handler


class LegacyBleakClient:
    instances = []

    def __init__(self, address: str):
        self.address = address
        self.disconnected_callback = None
        self.notify_handler = None
        self.connected = False
        LegacyBleakClient.instances.append(self)

    def set_disconnected_callback(self, cb):
        self.disconnected_callback = cb

    async def __aenter__(self):
        self.connected = True
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self.connected = False

    async def start_notify(self, char_uuid, handler):
        self.notify_handler = handler


def test_listen_raises_connection_error_on_disconnect():
    async def _test():
        DisconnectingBleakClient.instances.clear()
        packets = []

        def on_packet(data: bytes):
            packets.append(data)

        with patch("omi.ble.BleakClient", new=DisconnectingBleakClient):
            task = asyncio.create_task(listen("device-123", on_packet))
            await asyncio.sleep(0.01)
            client = DisconnectingBleakClient.instances[-1]
            assert client.notify_handler is not None

            await client.notify_handler("sender", bytearray(b"audio-data"))
            assert packets == [b"audio-data"]

            client.disconnected_callback(client)

            with pytest.raises(ConnectionError, match="Device device-123 disconnected"):
                await task

    asyncio.run(_test())


def test_listen_payload_raises_connection_error_on_disconnect():
    async def _test():
        DisconnectingBleakClient.instances.clear()
        payloads = []

        def on_payload(data: bytes):
            payloads.append(data)

        with patch("omi.ble.BleakClient", new=DisconnectingBleakClient):
            task = asyncio.create_task(listen_payload("device-456", on_payload))
            await asyncio.sleep(0.01)
            client = DisconnectingBleakClient.instances[-1]

            client.disconnected_callback(client)

            with pytest.raises(ConnectionError, match="Device device-456 disconnected"):
                await task

    asyncio.run(_test())


def test_listen_to_omi_raises_connection_error_on_disconnect():
    async def _test():
        DisconnectingBleakClient.instances.clear()
        with patch("omi.bluetooth.BleakClient", new=DisconnectingBleakClient):
            task = asyncio.create_task(listen_to_omi("AA:BB:CC:DD:EE:FF", "char-uuid", lambda sender, data: None))
            await asyncio.sleep(0.01)
            client = DisconnectingBleakClient.instances[-1]

            client.disconnected_callback(client)

            with pytest.raises(ConnectionError, match="Device AA:BB:CC:DD:EE:FF disconnected"):
                await task

    asyncio.run(_test())


def test_listen_clean_cancellation():
    async def _test():
        DisconnectingBleakClient.instances.clear()
        with patch("omi.ble.BleakClient", new=DisconnectingBleakClient):
            task = asyncio.create_task(listen("device-789", lambda data: None))
            await asyncio.sleep(0.01)

            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task

    asyncio.run(_test())


def test_listen_legacy_client_fallback():
    async def _test():
        LegacyBleakClient.instances.clear()
        with patch("omi.ble.BleakClient", new=LegacyBleakClient):
            task = asyncio.create_task(listen("legacy-123", lambda data: None))
            await asyncio.sleep(0.01)
            client = LegacyBleakClient.instances[-1]
            assert client.disconnected_callback is not None

            client.disconnected_callback(client)
            with pytest.raises(ConnectionError, match="Device legacy-123 disconnected"):
                await task

    asyncio.run(_test())


def test_listen_to_omi_legacy_client_fallback():
    async def _test():
        LegacyBleakClient.instances.clear()
        with patch("omi.bluetooth.BleakClient", new=LegacyBleakClient):
            task = asyncio.create_task(listen_to_omi("legacy-omi", "char-uuid", lambda sender, data: None))
            await asyncio.sleep(0.01)
            client = LegacyBleakClient.instances[-1]
            assert client.disconnected_callback is not None

            client.disconnected_callback(client)
            with pytest.raises(ConnectionError, match="Device legacy-omi disconnected"):
                await task

    asyncio.run(_test())
