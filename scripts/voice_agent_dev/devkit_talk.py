#!/usr/bin/env python3
"""Send TTS audio to Omi DevKit 2 speaker over BLE from the laptop.
Uses local dev server (/v2/tts/synthesize, pcm_8000) with ADMIN_KEY auth.
DevKit must be advertising (not connected to another device, MAX_CONN=1).
"""
import argparse
import asyncio
import struct
import sys
import httpx
from bleak import BleakClient

DEVICE_ID = "C3:43:D7:97:11:10"
AUDIO_WRITE_UUID = "19B10003-E8F2-537E-4F6C-D104768A1214"
PACKET_SIZE = 400
MAX_MONO_BYTES_PER_TRANSMISSION = 35000
TTS_URL = "http://127.0.0.1:8000/v2/tts/synthesize"
AUTH_TOKEN = "local-dev-admin-key-devuser"


def pad_for_firmware(pcm: bytes) -> bytes:
    r = len(pcm) % PACKET_SIZE
    add = 8 if r == 0 else (2 if r == 4 else 0)
    return pcm + (b"\x00" * add) if add else pcm


def plan_transmissions(pcm: bytes):
    return [
        pad_for_firmware(pcm[o:o + MAX_MONO_BYTES_PER_TRANSMISSION])
        for o in range(0, len(pcm), MAX_MONO_BYTES_PER_TRANSMISSION)
    ]


def fetch_pcm16_8k(text: str) -> bytes:
    """Get raw 16-bit little-endian mono PCM @ 8kHz from local dev server."""
    with httpx.Client(timeout=60.0) as c:
        r = c.post(
            TTS_URL,
            headers={"Authorization": f"Bearer {AUTH_TOKEN}", "Content-Type": "application/json"},
            json={"text": text, "output_format": "pcm_8000"},
        )
        r.raise_for_status()
        data = r.content
        ct = r.headers.get("content-type", "")
        print(f"  [tts] {len(data)} bytes, content-type={ct}")
        if data[:3] == b"ID3" or (len(data) > 1 and data[0] == 0xFF and (data[1] & 0xE0) == 0xE0):
            raise RuntimeError("TTS returned MP3, not pcm_8000")
        return data


async def play_pcm(client: BleakClient, pcm: bytes):
    transmissions = plan_transmissions(pcm)
    print(f"  [ble] {len(pcm)} mono bytes -> {len(transmissions)} transmission(s)")
    pump = asyncio.Event()

    async def on_notify(sender, data: bytearray):
        pump.set()

    await client.start_notify(AUDIO_WRITE_UUID, on_notify)
    await asyncio.sleep(0.3)
    try:
        for i, mono in enumerate(transmissions, 1):
            header = struct.pack("<I", len(mono))
            pump.clear()
            await client.write_gatt_char(AUDIO_WRITE_UUID, header, response=True)
            await asyncio.wait_for(pump.wait(), timeout=10)
            print(f"  [ble] tx {i}/{len(transmissions)}: {len(mono)} bytes")
            for off in range(0, len(mono), PACKET_SIZE):
                chunk = mono[off:off + PACKET_SIZE]
                pump.clear()
                await client.write_gatt_char(AUDIO_WRITE_UUID, chunk, response=True)
                if len(chunk) < PACKET_SIZE:
                    break
                await asyncio.wait_for(pump.wait(), timeout=10)
            await asyncio.sleep(0.4)
    finally:
        try:
            await client.stop_notify(AUDIO_WRITE_UUID)
        except Exception:
            pass


async def speak_text(client: BleakClient, text: str):
    text = (text or "").strip()
    if not text:
        return
    print(f"[say] {text}")
    pcm = fetch_pcm16_8k(text)
    await play_pcm(client, pcm)
    print("[done]")


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--device", default=DEVICE_ID, help="BLE address of DevKit (default OMI-VOICE)")
    ap.add_argument("--text", help="Text to speak once")
    ap.add_argument("--chat", action="store_true", help="Interactive loop: type text, DevKit speaks it")
    args = ap.parse_args()

    if not args.text and not args.chat:
        args.text = "Hello, I am your Omi DevKit voice agent. I can talk to you from this device."

    print(f"[ble] connecting to {args.device} (ensure DevKit is not connected to phone, MAX_CONN=1)...")
    try:
        async with BleakClient(args.device, timeout=20.0) as client:
            print(f"[ble] connected: {client.is_connected}, mtu={getattr(client,'mtu_size','?')}")
            if args.text:
                await speak_text(client, args.text)
            if args.chat:
                print("[chat] Type a message and press Enter (empty line to quit).")
                while True:
                    try:
                        line = await asyncio.get_event_loop().run_in_executor(None, sys.stdin.readline)
                    except (EOFError, KeyboardInterrupt):
                        break
                    if not line:
                        break
                    line = line.strip()
                    if not line:
                        break
                    try:
                        await speak_text(client, line)
                    except Exception as e:
                        print(f"[error] {e}")
    except Exception as e:
        print(f"[ble] failed: {e}")
        print("Hints: DevKit must be advertising & not connected elsewhere (BLE MAX_CONN=1). "
              "Power-cycle DevKit or disconnect it from the phone, then retry.")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
