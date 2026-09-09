from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest
from bleak.exc import BleakError

from omi.ble import listen, listen_payload
from omi.constants import AUDIO_DATA_UUID, OMI_SERVICE_UUID


class FakeCharacteristic:
    def __init__(self, uuid: str, handle: int):
        self.uuid = uuid
        self.handle = handle


class FakeService:
    def __init__(self, uuid: str):
        self.uuid = uuid
        self.characteristics: dict[str, FakeCharacteristic] = {}

    def add_char(self, char: FakeCharacteristic):
        self.characteristics[char.uuid] = char

    def get_characteristic(self, uuid: str) -> FakeCharacteristic | None:
        return self.characteristics.get(uuid)


class FakeServiceCollection:
    def __init__(self):
        self.services: dict[str, FakeService] = {}

    def add_service(self, service: FakeService):
        self.services[service.uuid] = service

    def get_service(self, uuid: str) -> FakeService | None:
        return self.services.get(uuid)


class MockBleakClientWithServices:
    def __init__(self, device_id: str, services: FakeServiceCollection | None = None):
        self.device_id = device_id
        self.services = services
        self.notified_target = None
        self.notify_handler = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass

    async def start_notify(self, char_or_uuid, handler):
        self.notified_target = char_or_uuid
        self.notify_handler = handler


def test_listen_resolves_characteristic_from_selected_service(monkeypatch):
    async def _test():
        collection = FakeServiceCollection()
        srv1 = FakeService(OMI_SERVICE_UUID)
        c1 = FakeCharacteristic(AUDIO_DATA_UUID, 101)
        srv1.add_char(c1)
        collection.add_service(srv1)

        client = MockBleakClientWithServices("dev-1", collection)

        async def fake_sleep(sec):
            raise asyncio.CancelledError()

        monkeypatch.setattr(asyncio, "sleep", fake_sleep)

        with patch("omi.ble.BleakClient", return_value=client):
            with pytest.raises(asyncio.CancelledError):
                await listen("dev-1", lambda data: None, service_uuid=OMI_SERVICE_UUID, char_uuid=AUDIO_DATA_UUID)

        assert client.notified_target is c1

    asyncio.run(_test())


def test_listen_disambiguates_between_multiple_services(monkeypatch):
    async def _test():
        custom_service = "29b10000-e8f2-537e-4f6c-d104768a1214"
        collection = FakeServiceCollection()

        srv1 = FakeService(OMI_SERVICE_UUID)
        c1 = FakeCharacteristic(AUDIO_DATA_UUID, 101)
        srv1.add_char(c1)
        collection.add_service(srv1)

        srv2 = FakeService(custom_service)
        c2 = FakeCharacteristic(AUDIO_DATA_UUID, 202)
        srv2.add_char(c2)
        collection.add_service(srv2)

        client = MockBleakClientWithServices("dev-1", collection)

        async def fake_sleep(sec):
            raise asyncio.CancelledError()

        monkeypatch.setattr(asyncio, "sleep", fake_sleep)

        with patch("omi.ble.BleakClient", return_value=client):
            with pytest.raises(asyncio.CancelledError):
                await listen("dev-1", lambda data: None, service_uuid=custom_service, char_uuid=AUDIO_DATA_UUID)

        assert client.notified_target is c2

    asyncio.run(_test())


def test_listen_raises_bleak_error_when_service_missing():
    async def _test():
        collection = FakeServiceCollection()
        client = MockBleakClientWithServices("dev-1", collection)

        with patch("omi.ble.BleakClient", return_value=client):
            with pytest.raises(BleakError, match="Service .* was not found"):
                await listen("dev-1", lambda data: None, service_uuid="missing-uuid")

    asyncio.run(_test())


def test_listen_raises_bleak_error_when_characteristic_missing():
    async def _test():
        collection = FakeServiceCollection()
        srv = FakeService(OMI_SERVICE_UUID)
        collection.add_service(srv)
        client = MockBleakClientWithServices("dev-1", collection)

        with patch("omi.ble.BleakClient", return_value=client):
            with pytest.raises(BleakError, match="Characteristic .* was not found in service"):
                await listen("dev-1", lambda data: None, service_uuid=OMI_SERVICE_UUID, char_uuid="missing-char")

    asyncio.run(_test())


def test_listen_payload_forwards_service_uuid(monkeypatch):
    async def _test():
        collection = FakeServiceCollection()
        custom_service = "custom-srv"
        srv = FakeService(custom_service)
        c = FakeCharacteristic(AUDIO_DATA_UUID, 999)
        srv.add_char(c)
        collection.add_service(srv)
        client = MockBleakClientWithServices("dev-1", collection)

        async def fake_sleep(sec):
            raise asyncio.CancelledError()

        monkeypatch.setattr(asyncio, "sleep", fake_sleep)

        with patch("omi.ble.BleakClient", return_value=client):
            with pytest.raises(asyncio.CancelledError):
                await listen_payload("dev-1", lambda data: None, service_uuid=custom_service, char_uuid=AUDIO_DATA_UUID)

        assert client.notified_target is c

    asyncio.run(_test())
