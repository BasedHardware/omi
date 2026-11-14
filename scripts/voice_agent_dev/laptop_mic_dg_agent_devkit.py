#!/usr/bin/env python3
"""
Live Deepgram Voice Agent: laptop mic input -> DevKit 2 speaker output.
- Mic: laptop (arecord, streaming linear16 to Deepgram Agent)
- Brain: Deepgram Voice Agent (live websocket: STT+LLM+TTS)
- Speaker: Omi DevKit 2 over BLE (agent audio buffered per response, resampled to 8kHz, sent as transmissions)

Note: DevKit BLE speaker has protocol latency (~slower than realtime). Audio is played per agent response
(buffered until AgentAudioDone/flush points) for reliable playback.
"""
import argparse
import asyncio
import inspect
import json
import os
import struct
import subprocess
import sys
import time
from pathlib import Path

import websockets
from bleak import BleakClient

DG_AGENT_URL = "wss://agent.deepgram.com/v1/agent/converse"

# DevKit BLE
DEVICE_ID = "C3:43:D7:97:11:10"
AUDIO_SPEAKER = "19b10003-e8f2-537e-4f6c-d104768a1214"
PACKET_SIZE = 400
MAX_MONO_BYTES_PER_TRANSMISSION = 35000


def load_env(env_path: str):
    p = Path(env_path)
    if not p.exists():
        return
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip().removeprefix("export").strip()
        v = v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v


def build_settings(mic_rate: int, out_rate: int, settings_file: str | None = None) -> dict:
    if settings_file:
        s = json.loads(Path(settings_file).read_text())
        if isinstance(s, dict):
            s.setdefault("type", "Settings")
        return s
    return {
        "type": "Settings",
        "audio": {
            "input": {"encoding": "linear16", "sample_rate": mic_rate},
            "output": {"encoding": "linear16", "sample_rate": out_rate, "container": "none"},
        },
        "agent": {
            "listen": {"provider": {"type": "deepgram", "model": "nova-3"}},
            "think": {
                "provider": {"type": "open_ai", "model": "gpt-4o-mini"},
                "prompt": "You are Omi, a helpful concise voice assistant. Reply in 1-2 short spoken sentences.",
            },
            "speak": {"provider": {"type": "deepgram", "model": "aura-2-thalia-en"}},
            "greeting": "Hey, I'm ready. Talk to me.",
        },
    }


def resample_pcm16(data: bytes, in_rate: int, out_rate: int) -> bytes:
    if in_rate == out_rate or not data:
        return data
    for cmd in (
        ["sox", "-t", "raw", "-r", str(in_rate), "-e", "signed", "-b", "16", "-c", "1", "-",
         "-t", "raw", "-r", str(out_rate), "-e", "signed", "-b", "16", "-c", "1", "-"],
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "s16le", "-ar", str(in_rate), "-ac", "1", "-i", "pipe:0",
         "-f", "s16le", "-ar", str(out_rate), "-ac", "1", "pipe:1"],
    ):
        try:
            p = subprocess.run(cmd, input=data, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if p.returncode == 0 and p.stdout:
                return p.stdout
        except Exception:
            pass
    # naive fallback
    ratio = in_rate // out_rate if out_rate and in_rate % out_rate == 0 else None
    if ratio and ratio > 1:
        return b"".join(data[i:i+2] for i in range(0, len(data), 2 * ratio))
    return data


def pad_for_firmware(pcm: bytes) -> bytes:
    r = len(pcm) % PACKET_SIZE
    add = 8 if r == 0 else (2 if r == 4 else 0)
    return pcm + (b"\x00" * add) if add else pcm


def plan_transmissions(pcm: bytes):
    return [pad_for_firmware(pcm[o:o + MAX_MONO_BYTES_PER_TRANSMISSION]) for o in range(0, len(pcm), MAX_MONO_BYTES_PER_TRANSMISSION)]


async def play_pcm_devkit(client: BleakClient, pcm: bytes):
    if not pcm or len(pcm) < 2:
        return
    transmissions = plan_transmissions(pcm)
    audio_dur = len(pcm) / (8000 * 2)
    print(f"[spk-devkit] playing {len(pcm)} bytes ({audio_dur:.2f}s audio, {len(transmissions)} tx)...")
    t0 = time.perf_counter()
    pump = asyncio.Event()

    async def on_notify(sender, data: bytearray):
        pump.set()

    await client.start_notify(AUDIO_SPEAKER, on_notify)
    await asyncio.sleep(0.05)
    try:
        for mono in transmissions:
            header = struct.pack("<I", len(mono))
            pump.clear()
            await client.write_gatt_char(AUDIO_SPEAKER, header, response=True)
            await asyncio.wait_for(pump.wait(), timeout=10)
            for off in range(0, len(mono), PACKET_SIZE):
                chunk = mono[off:off + PACKET_SIZE]
                pump.clear()
                await client.write_gatt_char(AUDIO_SPEAKER, chunk, response=True)
                if len(chunk) < PACKET_SIZE:
                    break
                await asyncio.wait_for(pump.wait(), timeout=10)
            await asyncio.sleep(0.05)
    finally:
        try:
            await client.stop_notify(AUDIO_SPEAKER)
        except Exception:
            pass
    print(f"[spk-devkit] done in {time.perf_counter()-t0:.2f}s")


async def mic_sender(proc: subprocess.Popen, dg_ws, chunk_bytes: int, stop: asyncio.Event):
    loop = asyncio.get_event_loop()
    sent = 0
    try:
        while not stop.is_set() and proc.stdout:
            data = await loop.run_in_executor(None, proc.stdout.read, chunk_bytes)
            if not data:
                break
            sent += len(data)
            try:
                await dg_ws.send(data)
            except Exception:
                break
    except Exception:
        pass
    print(f"[mic] sent {sent} bytes total")


async def keepalive(dg_ws, stop: asyncio.Event):
    try:
        while not stop.is_set():
            await asyncio.sleep(8)
            if stop.is_set():
                break
            try:
                await dg_ws.send(json.dumps({"type": "KeepAlive"}))
            except Exception:
                break
    except Exception:
        pass


async def run(api_key: str, mic_device: str | None, mic_rate: int, out_rate: int, device_id: str, settings_file: str | None):
    settings = build_settings(mic_rate, out_rate, settings_file=settings_file)
    try:
        ain = (((settings.get("audio") or {}).get("input") or {}).get("sample_rate"))
        aout = (((settings.get("audio") or {}).get("output") or {}).get("sample_rate"))
        if isinstance(ain, int) and ain > 0:
            mic_rate = ain
        if isinstance(aout, int) and aout > 0:
            out_rate = aout
    except Exception:
        pass
    devkit_rate = 8000
    headers = {"Authorization": f"Token {api_key}"}

    print(f"[ble] connecting to DevKit {device_id} (must not be connected to phone, MAX_CONN=1)...")
    async with BleakClient(device_id, timeout=25.0) as client:
        try:
            if hasattr(client, "_backend") and hasattr(client._backend, "_acquire_mtu"):
                await client._backend._acquire_mtu()
        except Exception as e:
            print(f"[ble] mtu negotiate skipped: {e}")
        print(f"[ble] connected: {client.is_connected}, mtu={getattr(client,'mtu_size',None)}")

        connect_kw = dict(ping_interval=20, ping_timeout=20, close_timeout=5, max_size=16 * 1024 * 1024)
        params = inspect.signature(websockets.connect).parameters
        if "extra_headers" in params:
            ws_cm = websockets.connect(DG_AGENT_URL, extra_headers=headers, **connect_kw)
        elif "additional_headers" in params:
            ws_cm = websockets.connect(DG_AGENT_URL, additional_headers=headers, **connect_kw)
        else:
            ws_cm = websockets.connect(DG_AGENT_URL, extra_headers=headers, **connect_kw)

        print(f"[dg] connecting {DG_AGENT_URL} ... (mic {mic_rate}Hz -> agent -> {out_rate}Hz -> devkit {devkit_rate}Hz)")
        async with ws_cm as dg_ws:
            await dg_ws.send(json.dumps(settings))
            print("[dg] Settings sent. Speak into laptop mic; agent replies on DevKit speaker. Ctrl+C to quit.")

            arecord_cmd = ["arecord", "-q", "-f", "S16_LE", "-r", str(mic_rate), "-c", "1", "-t", "raw"]
            if mic_device:
                arecord_cmd[1:1] = ["-D", mic_device]
            mic_proc = subprocess.Popen(arecord_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            stop = asyncio.Event()
            mic_task = asyncio.create_task(mic_sender(mic_proc, dg_ws, max(320, int(mic_rate * 2 * 0.1)), stop))
            ka_task = asyncio.create_task(keepalive(dg_ws, stop))

            audio_buf = bytearray()
            play_q: asyncio.Queue[bytes | None] = asyncio.Queue()
            speaking = asyncio.Event()  # devkit playing

            async def player():
                while True:
                    pcm8 = await play_q.get()
                    if pcm8 is None:
                        break
                    speaking.set()
                    try:
                        await play_pcm_devkit(client, pcm8)
                    except Exception as e:
                        print(f"[spk-devkit] error: {e}")
                    finally:
                        speaking.clear()
                    play_q.task_done()

            player_task = asyncio.create_task(player())

            async def flush_audio(reason: str):
                nonlocal audio_buf
                if not audio_buf:
                    return
                raw = bytes(audio_buf)
                audio_buf.clear()
                print(f"[dg] flushing {len(raw)} bytes ({reason}) -> resample {out_rate}->{devkit_rate}")
                pcm8 = await asyncio.get_event_loop().run_in_executor(None, resample_pcm16, raw, out_rate, devkit_rate)
                if pcm8:
                    await play_q.put(pcm8)

            try:
                async for msg in dg_ws:
                    if isinstance(msg, (bytes, bytearray)):
                        audio_buf.extend(msg)
                        continue
                    try:
                        evt = json.loads(msg)
                    except Exception:
                        continue
                    et = evt.get("type") or ""
                    if et == "ConversationText":
                        role = evt.get("role", "?")
                        content = evt.get("content", "")
                        if content:
                            print(f"[{'You' if role=='user' else 'Agent'}] {content}")
                    elif et == "UserStartedSpeaking":
                        print("[event] UserStartedSpeaking")
                        # barge-in: drop buffered agent audio not yet played
                        if audio_buf and not speaking.is_set():
                            print(f"[dg] dropping {len(audio_buf)} buffered bytes (barge-in)")
                            audio_buf.clear()
                    elif et == "AgentStartedSpeaking":
                        print("[event] AgentStartedSpeaking")
                    elif et == "AgentAudioDone":
                        print("[event] AgentAudioDone")
                        await flush_audio("AgentAudioDone")
                    elif et == "Welcome":
                        print(f"[dg] Welcome: {evt.get('request_id')}")
                    elif et == "SettingsApplied":
                        print("[dg] SettingsApplied")
                    elif et in ("Error", "Warning"):
                        print(f"[dg] {et}: {evt}")
                    else:
                        if et:
                            pass
            except websockets.exceptions.ConnectionClosed as e:
                print(f"[dg] connection closed: {e}")
            finally:
                stop.set()
                await flush_audio("shutdown")
                await play_q.put(None)
                for t in (mic_task, ka_task):
                    t.cancel()
                try:
                    mic_proc.terminate()
                except Exception:
                    pass
                try:
                    mic_proc.wait(timeout=2)
                except Exception:
                    try:
                        mic_proc.kill()
                    except Exception:
                        pass
                await player_task


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mic", default=None, help="arecord device, e.g. hw:0,7 or hw:0,6")
    ap.add_argument("--device", default=DEVICE_ID, help="DevKit BLE address")
    ap.add_argument("--mic-rate", type=int, default=16000)
    ap.add_argument("--out-rate", type=int, default=24000)
    ap.add_argument("--settings-file", default=None)
    ap.add_argument("--env", default="/home/palontologist/Downloads/dev/omi-app/backend/.env.local-dev")
    args = ap.parse_args()

    load_env(args.env)
    api_key = os.getenv("DEEPGRAM_API_KEY", "")
    if not api_key:
        print("DEEPGRAM_API_KEY not found in env or backend/.env.local-dev")
        sys.exit(1)
    print("[ok] DEEPGRAM_API_KEY loaded")
    try:
        await run(api_key, args.mic, args.mic_rate, args.out_rate, args.device, args.settings_file)
    except KeyboardInterrupt:
        print("\n[bye]")


if __name__ == "__main__":
    asyncio.run(main())
