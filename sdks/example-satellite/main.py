#!/usr/bin/env python3
"""Omi-Bluetooth Wyoming satellite."""

import argparse
import asyncio
import contextlib
import logging
import socket
from pathlib import Path
from typing import Optional

from bleak.exc import BleakDeviceNotFoundError
from omi.bluetooth import listen_to_omi
from omi.decoder import OmiOpusDecoder
from wyoming.audio import AudioChunk
from wyoming.event import Event
from wyoming.info import Attribution, Describe, Info, Satellite
from wyoming.server import AsyncEventHandler, AsyncTcpServer
from wyoming_satellite.satellite import (
    AlwaysStreamingSatellite,
    SatelliteBase,
    WakeStreamingSatellite,
)
from wyoming_satellite.settings import (
    MicSettings,
    SatelliteSettings,
    SndSettings,
    WakeSettings,
    WakeWordAndPipeline,
)
from zeroconf import ServiceInfo, Zeroconf

_LOGGER = logging.getLogger(__name__)
_LOGGER.setLevel(logging.INFO)

###############################################################################
# Constants (PCM format and Bluetooth identifiers)
###############################################################################
RATE, WIDTH, CHANNELS = 16_000, 2, 1  # 16-kHz/16-bit/mono
# CHUNK_MS = 32
# CHUNK_LEN = int(RATE * CHUNK_MS / 1000) * WIDTH

DEFAULT_OMI_MAC = "C67EDFB1-56C8-7A6F-0776-7303E8F697AF"
DEFAULT_OMI_CHAR_UUID = "19B10001-E8F2-537E-4F6C-D104768A1214"

###############################################################################
# BLE → PCM helper
###############################################################################
class _OmiMic:
    """Background task that feeds decoded PCM into an asyncio.Queue."""

    def __init__(self, mac: str, char_uuid: str):
        self._mac = mac
        self._char_uuid = char_uuid
        self._decoder = OmiOpusDecoder()
        self._q: asyncio.Queue[bytes] = asyncio.Queue(maxsize=50)
        self._task: Optional[asyncio.Task] = None

    # public -----------------------------------------------------------------
    async def start(self):
        if self._task is None:
            self._task = asyncio.create_task(self._ble_loop(), name="ble-omi")

    async def stop(self):
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None

    async def pcm_iter(self):
        # buf = bytearray()
        while True:
            pcm = await self._q.get()
            yield pcm
            # buf.extend(pcm)
            # while len(buf) >= CHUNK_LEN:
            #     yield bytes(buf[:CHUNK_LEN])
            #     del buf[:CHUNK_LEN]

    # internal ---------------------------------------------------------------
    async def _ble_loop(self):
        def _cb(_: int, data: bytes):
            pcm = self._decoder.decode_packet(data)
            if pcm is not None:
                try:
                    self._q.put_nowait(pcm)
                except asyncio.QueueFull:
                    _LOGGER.warning("PCM queue full - dropping packet")
        await listen_to_omi(self._mac, self._char_uuid, _cb)

###############################################################################
# Satellite mix-in: consume _OmiMic instead of built-in mic service
###############################################################################
class _BluetoothMixin(SatelliteBase):
    def __init__(self, settings: SatelliteSettings, mic_src: _OmiMic):
        super().__init__(settings)
        self._mic_src = mic_src
        self._pump_task: Optional[asyncio.Task] = None

    async def started(self):
        await super().started()
        if self._pump_task is None:
            self._pump_task = asyncio.create_task(self._pump(), name="pcm-pump")

    async def stopped(self):
        if self._pump_task:
            self._pump_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._pump_task
            self._pump_task = None
        await super().stopped()

    async def _pump(self):
        async for pcm in self._mic_src.pcm_iter():
            evt = AudioChunk(rate=RATE, width=WIDTH, channels=CHANNELS, audio=pcm).event()
            await self.event_from_mic(evt, audio_bytes=pcm)

###############################################################################
# Handler bridging TCP client ↔ satellite
###############################################################################
class _SatHandler(AsyncEventHandler):
    def __init__(self, *args, satellite: SatelliteBase, **kwargs):
        _LOGGER.info(f"SatHandler __init__: {args}, {kwargs}")
        super().__init__(*args, **kwargs)
        self._sat = satellite
        self._peer = str(self.writer.get_extra_info("peername"))
        _LOGGER.info(f"Setting server for {self._peer}")

    async def handle_event(self, event: Event) -> bool:  # noqa: D401
        _LOGGER.info(f"Received event {event} from client {self._peer}")
        await self._sat.event_from_server(event)
        if Describe.is_type(event.type):
            if self._sat._writer is None:
                await self._sat.set_server(self._peer, self.writer)
            _LOGGER.info(f"Received describe event from client {self._peer}")
            info = Info(
                satellite=Satellite(
                    name="Omi Bluetooth Satellite",
                    attribution=Attribution(
                        name="Omi",
                        url="https://omi.com"
                    ),
                    installed=True,
                    description="Omi Bluetooth Satellite",
                    version="0.1.0"
                )
            )
            await self.write_event(info.event())
        return True

    async def disconnect(self) -> None:
        """Called when client disconnects."""
        _LOGGER.info(f"Client {self._peer} disconnected")
        await self._sat.clear_server()
        await super().disconnect()

###############################################################################
# SatelliteSettings factory (matches frozen dataclass definition)
###############################################################################

def build_settings(*, wake_uri: str | None, wake_names: list[str] | None) -> SatelliteSettings:
    mic = MicSettings(
        uri=None,
        command=None,
    )

    # vad = VadSettings(enabled=False)
    snd = SndSettings(
        awake_wav="./sounds/awake_sound.wav",
        done_wav="./sounds/done_sound.wav",
        command=["sox", "-t", "raw", "-r", "22050", "-c", "1", "-e", "signed-integer", "-b", "16", "-", "-t", "coreaudio"]
        )
    # event = EventSettings()
    # timer = TimerSettings()

    if wake_uri:
        wake = WakeSettings(
            uri=wake_uri,
            command=None,
            reconnect_seconds=1.0,
            names=[WakeWordAndPipeline(name=n, pipeline="Omi BT Wakeword Pipeline") for n in (wake_names or [])],
            rate=RATE,
            width=WIDTH,
            channels=CHANNELS,
            refractory_seconds=None,
        )
    else:
        wake = WakeSettings(uri=None)

    return SatelliteSettings(
        mic=mic,
        wake=wake,
        snd=snd,
        debug_recording_dir=Path("./debug"),
    )


def register_service(ip: str, port: int):
    desc = {'uri': f'tcp://{ip}:{port}'}
    info = ServiceInfo(
        "_wyoming._tcp.local.",
        "OmiSatellite._wyoming._tcp.local.",
        addresses=[socket.inet_aton(ip)],
        port=port,
        properties=desc,
        server="omi-satellite.local.",
    )

    zeroconf = Zeroconf()
    zeroconf.register_service(info)
    return zeroconf

###############################################################################
# Entry-point
###############################################################################
async def _run_satellite(sat: SatelliteBase, host: str, port: int):
    _LOGGER.info(f"Satellite server starting at {host}:{port}")
    server = AsyncTcpServer(host, port)
    try:
        await server.run(lambda r, w: _SatHandler(r, w, satellite=sat))
        _LOGGER.info("Satellite server started")
    except Exception as e:
        _LOGGER.error(f"Failed to start satellite server: {e}")
        raise

async def main():
    p = argparse.ArgumentParser()
    p.add_argument("--host", default="0.0.0.0")
    p.add_argument("--port", type=int, default=10700)
    p.add_argument("--omi-mac", default=DEFAULT_OMI_MAC)
    p.add_argument("--omi-char-uuid", default=DEFAULT_OMI_CHAR_UUID)
    p.add_argument("--wake-uri")
    p.add_argument("--wake-word-name", action="append")
    p.add_argument("--debug", action="store_true")
    args = p.parse_args()

    logging_level = logging.DEBUG if args.debug else logging.INFO
    print(f"Logging level: {logging_level}")
    logging.basicConfig(level=logging_level, format="%(asctime)s %(levelname)s: %(message)s")

    try:
        mic_src = _OmiMic(args.omi_mac, args.omi_char_uuid)
        await mic_src.start()

        settings = build_settings(wake_uri=args.wake_uri, wake_names=args.wake_word_name)

        sat_cls = type(
            "OmiBluetoothSatellite",
            (_BluetoothMixin, WakeStreamingSatellite if args.wake_uri else AlwaysStreamingSatellite),
            {},
        )
        _LOGGER.info(f"Creating satellite with class: {sat_cls.__name__}")
        satellite: SatelliteBase = sat_cls(settings, mic_src)  # type: ignore[arg-type]


                
        # Initialize satellite
        await satellite.started()
        
        try:
            
            await asyncio.gather(
                asyncio.create_task(_run_satellite(satellite, args.host, args.port), name="tcp"),
                asyncio.create_task(satellite.run(), name="sat-loop"),
            )
        finally:
            await satellite.stopped()
            await mic_src.stop()
    except Exception as e:
        _LOGGER.error(f"Error in main: {e}", exc_info=True)
        raise

def get_lan_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # doesn't have to be reachable
        s.connect(("10.255.255.255", 1))
        ip = s.getsockname()[0]
    except Exception:
        ip = "127.0.0.1"
    finally:
        s.close()
    return ip

if __name__ == "__main__":
    try:
        zeroconf = register_service(get_lan_ip(), 10700)
        asyncio.run(main())
    except BleakDeviceNotFoundError:
        _LOGGER.error("OMI device not found – check MAC address")
        exit(1)
    except KeyboardInterrupt:
        pass
    finally:
        zeroconf.unregister_all_services()
        zeroconf.close()