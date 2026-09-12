"""High-level BLE helpers (bleak). Matches multi-lang device SDK surface."""

from __future__ import annotations

import asyncio
import inspect
from dataclasses import dataclass
from typing import Awaitable, Callable, List, Optional, Union

from bleak import BleakClient, BleakScanner
from bleak.exc import BleakError

from .constants import AUDIO_CODEC_UUID, AUDIO_DATA_UUID, OMI_SERVICE_UUID, PACKET_HEADER_BYTES


@dataclass
class Device:
    id: str
    name: str
    rssi: int = 0


PacketHandler = Callable[[bytes], None]
AsyncPacketHandler = Callable[[bytes], Union[None, Awaitable[None]]]
DisconnectCallback = Callable[[BleakClient], None]


def _client_with_disconnect(address: str, on_disconnect: DisconnectCallback) -> BleakClient:
    """Prefer BleakClient(disconnected_callback=...); fall back to set_disconnected_callback."""
    try:
        return BleakClient(address, disconnected_callback=on_disconnect)
    except TypeError:
        client = BleakClient(address)
        setter = getattr(client, "set_disconnected_callback", None)
        if setter is not None:
            setter(on_disconnect)
        return client


async def _wait_while_connected(disconnected: asyncio.Event, idle_seconds: float) -> None:
    """Wait until Bleak reports disconnect. Idle sleep is only a wake/cancel hook, not the signal."""
    while not disconnected.is_set():
        disconnect_task = asyncio.create_task(disconnected.wait())
        sleep_task = asyncio.create_task(asyncio.sleep(idle_seconds))
        try:
            done, _pending = await asyncio.wait(
                {disconnect_task, sleep_task},
                return_when=asyncio.FIRST_COMPLETED,
            )
        except asyncio.CancelledError:
            disconnect_task.cancel()
            sleep_task.cancel()
            await asyncio.gather(disconnect_task, sleep_task, return_exceptions=True)
            raise
        for task in (disconnect_task, sleep_task):
            if not task.done():
                task.cancel()
        await asyncio.gather(disconnect_task, sleep_task, return_exceptions=True)
        if sleep_task in done:
            if sleep_task.cancelled():
                raise asyncio.CancelledError()
            exc = sleep_task.exception()
            if exc is not None:
                raise exc


async def scan(timeout: float = 5.0) -> List[Device]:
    found = await BleakScanner.discover(timeout=timeout)
    out: List[Device] = []
    for d in found:
        name = d.name or ""
        rssi = int(getattr(d, "rssi", 0) or 0)
        out.append(Device(id=d.address, name=name, rssi=rssi))
    return out


async def listen(
    device_id: str,
    on_packet: AsyncPacketHandler,
    *,
    char_uuid: str = AUDIO_DATA_UUID,
    service_uuid: Optional[str] = None,
) -> None:
    """Connect and notify on audio characteristic until cancelled or the device disconnects."""

    async def _handler(_sender, data: bytearray) -> None:
        raw = bytes(data)
        result = on_packet(raw)
        if inspect.isawaitable(result):
            await result

    disconnected = asyncio.Event()

    def _on_disconnect(_client: BleakClient) -> None:
        disconnected.set()

    async with _client_with_disconnect(device_id, _on_disconnect) as client:
        services = getattr(client, "services", None)
        if services is not None and service_uuid:
            service = services.get_service(service_uuid)
            if service is None:
                raise BleakError(f"Service {service_uuid} was not found")
            characteristic = service.get_characteristic(char_uuid)
            if characteristic is None:
                raise BleakError(f"Characteristic {char_uuid} was not found in service {service_uuid}")
            await client.start_notify(characteristic, _handler)
        else:
            await client.start_notify(char_uuid, _handler)
        await _wait_while_connected(disconnected, 3600)
        raise ConnectionError(f"Device {device_id} disconnected")


async def listen_payload(
    device_id: str,
    on_payload: AsyncPacketHandler,
    *,
    char_uuid: str = AUDIO_DATA_UUID,
    service_uuid: Optional[str] = None,
) -> None:
    async def wrapped(packet: bytes) -> None:
        if len(packet) <= PACKET_HEADER_BYTES:
            return
        result = on_payload(packet[PACKET_HEADER_BYTES:])
        if inspect.isawaitable(result):
            await result

    await listen(device_id, wrapped, char_uuid=char_uuid, service_uuid=service_uuid)


async def read_codec(device_id: str, *, char_uuid: str = AUDIO_CODEC_UUID) -> int:
    async with BleakClient(device_id) as client:
        data = await client.read_gatt_char(char_uuid)
        return int(data[0]) if data else -1
