"""High-level BLE helpers (bleak). Matches multi-lang device SDK surface."""

from __future__ import annotations

import asyncio
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
        if asyncio.iscoroutine(result):
            await result

    async with BleakClient(device_id) as client:
        await client.start_notify(char_uuid, _handler)
        while True:
            await asyncio.sleep(3600)


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
        if asyncio.iscoroutine(result):
            await result

    await listen(device_id, wrapped, char_uuid=char_uuid)


async def read_codec(device_id: str, *, char_uuid: str = AUDIO_CODEC_UUID) -> int:
    async with BleakClient(device_id) as client:
        data = await client.read_gatt_char(char_uuid)
        return int(data[0]) if data else -1
