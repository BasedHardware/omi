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
    """Connect and notify on audio characteristic until cancelled, disconnected, or
    a packet callback raises.

    Bleak's own ``start_notify`` detects that ``_handler`` is a coroutine function
    and dispatches each notification via a detached ``asyncio.create_task`` (see
    ``BleakClient.start_notify``), not by awaiting it inline. A callback exception
    raised there never reaches this coroutine's caller on its own -- it has to be
    caught inside ``_handler`` and forwarded through the shared ``stopped`` signal.
    """

    stopped = asyncio.Event()
    callback_error: list[BaseException] = []

    async def _handler(_sender, data: bytearray) -> None:
        if stopped.is_set():
            return
        try:
            raw = bytes(data)
            result = on_packet(raw)
            if inspect.isawaitable(result):
                await result
        except Exception as error:  # noqa: BLE001 - forwarded to listen()'s caller below
            callback_error.append(error)
            stopped.set()

    def _on_disconnect(_client: BleakClient) -> None:
        stopped.set()

    async with BleakClient(device_id, disconnected_callback=_on_disconnect) as client:
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
        while not stopped.is_set():
            await asyncio.sleep(1)

    if callback_error:
        raise callback_error[0]
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
