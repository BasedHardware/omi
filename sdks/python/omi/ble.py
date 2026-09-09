"""High-level BLE helpers (bleak). Matches multi-lang device SDK surface."""

from __future__ import annotations

import asyncio
import inspect
from dataclasses import dataclass
from typing import Awaitable, Callable, List, Optional, Union

from bleak import BleakClient, BleakScanner

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
    service_uuid: str = OMI_SERVICE_UUID,
) -> None:
    """Connect and notify on audio characteristic until cancelled."""

    async def _handler(_sender, data: bytearray) -> None:
        raw = bytes(data)
        result = on_packet(raw)
        if inspect.isawaitable(result):
            await result

    disconnected_event = asyncio.Event()

    def _on_disconnect(_client: BleakClient) -> None:
        disconnected_event.set()

    try:
        client = BleakClient(device_id, disconnected_callback=_on_disconnect)
    except TypeError:
        client = BleakClient(device_id)
        if hasattr(client, "set_disconnected_callback"):
            client.set_disconnected_callback(_on_disconnect)

    async with client:
        await client.start_notify(char_uuid, _handler)
        while not disconnected_event.is_set():
            disconnect_task = asyncio.create_task(disconnected_event.wait())
            sleep_task = asyncio.create_task(asyncio.sleep(3600))
            try:
                done, pending = await asyncio.wait(
                    [disconnect_task, sleep_task],
                    return_when=asyncio.FIRST_COMPLETED,
                )
            finally:
                for task in (disconnect_task, sleep_task):
                    if not task.done():
                        task.cancel()
                await asyncio.gather(
                    disconnect_task, sleep_task, return_exceptions=True
                )
            for d in done:
                if d is sleep_task and d.exception():
                    raise d.exception()
        raise ConnectionError(f"Device {device_id} disconnected")


async def listen_payload(
    device_id: str,
    on_payload: AsyncPacketHandler,
    *,
    char_uuid: str = AUDIO_DATA_UUID,
) -> None:
    async def wrapped(packet: bytes) -> None:
        if len(packet) <= PACKET_HEADER_BYTES:
            return
        result = on_payload(packet[PACKET_HEADER_BYTES:])
        if inspect.isawaitable(result):
            await result

    await listen(device_id, wrapped, char_uuid=char_uuid)


async def read_codec(device_id: str, *, char_uuid: str = AUDIO_CODEC_UUID) -> int:
    async with BleakClient(device_id) as client:
        data = await client.read_gatt_char(char_uuid)
        return int(data[0]) if data else -1
