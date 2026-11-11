#!/usr/bin/env python3
"""
Live Deepgram Voice Agent with DevKit 2 mic as input.
- Mic: DevKit BLE audioDataStream (opus/pcm16/etc.) -> decoded to linear16 16kHz mono -> Deepgram Agent
- Brain: Deepgram Voice Agent (live websocket)
- Speaker: laptop (default, real-time) or DevKit BLE (--output devkit|both)

Usage:
  cd /home/palontologist/Downloads/dev/omi-app
  LD_LIBRARY_PATH=/nix/store/a7r1yfbkqfb8bb1ad6sny5cs3sr3nk4n-libopus-1.5.2/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH} \
  backend/venv/bin/python /home/palontologist/.tmp/opencode/devkit_mic_dg_agent.py

  # DevKit speaker output too:
  ... devkit_mic_dg_agent.py --output devkit
"""
import argparse
import asyncio
import inspect
import json
import os
import struct
import wave
import subprocess
import sys
import time
from pathlib import Path

import websockets
from bleak import BleakClient

DG_AGENT_URL = "wss://agent.deepgram.com/v1/agent/converse"

# DevKit BLE
DEVICE_ID = "C3:43:D7:97:11:10"
SERVICE = "19b10000-e8f2-537e-4f6c-d104768a1214"
AUDIO_DATA = "19b10001-e8f2-537e-4f6c-d104768a1214"
AUDIO_CODEC = "19b10002-e8f2-537e-4f6c-d104768a1214"
AUDIO_SPEAKER = "19b10003-e8f2-537e-4f6c-d104768a1214"
PACKET_SIZE = 400
MAX_MONO_BYTES_PER_TRANSMISSION = 35000

CODEC_BY_ID = {1: "pcm8", 2: "pcm16", 20: "opus", 21: "opusFS320"}


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
                "prompt": "You are Omi, a helpful concise voice assistant running on a DevKit. Reply in 1-2 short spoken sentences.",
            },
            "speak": {"provider": {"type": "deepgram", "model": "aura-2-thalia-en"}},
            "greeting": "Hey, I can hear you from the DevKit. What's up?",
        },
    }


class AudioDecoder:
    """Decode DevKit BLE audio packets to PCM16 mono 16kHz for DG Agent input."""
    def __init__(self, codec: str):
        self.codec = codec
        self.rate = 16000
        # Try to be flexible: opus may be mono or stereo depending on firmware; prefer mono
        self.channels = 1 if codec in ("opus", "opusFS320") else 1
        self.opus_dec = None
        self.opus_dec_alt = None  # alternative channel config
        self.opus_dec_ch = self.channels
        # prefer common speech frame sizes at 16kHz: 20ms, 10ms, 40ms, 60ms...
        self.opus_frame_sizes = [320, 160, 640, 960, 480, 1280, 1920, 2880]
        self._ok = 0
        self._fail = 0
        if codec in ("opus", "opusFS320"):
            self._init_opus()

    def _load_libopus(self):
        import ctypes, ctypes.util, glob as _glob
        opus_path = None
        found = ctypes.util.find_library('opus')
        if found and (isinstance(found, str) and found.startswith('/')):
            opus_path = found
        if not opus_path:
            candidates = []
            candidates += _glob.glob('/nix/store/*libopus*/lib/libopus.so.0')
            candidates += _glob.glob('/nix/store/*libopus*/lib/libopus.so')
            candidates += _glob.glob('/nix/store/*libopus*/lib/libopus.so*')
            candidates += _glob.glob('/usr/lib*/libopus.so.0')
            candidates += _glob.glob('/usr/lib*/libopus.so')
            candidates += _glob.glob('/usr/local/lib*/libopus.so*')
            def score(x):
                if x.endswith('.so.0'): return (0, len(x))
                if x.endswith('.so'): return (1, len(x))
                return (2, len(x))
            candidates.sort(key=score)
            for c in candidates:
                try:
                    ctypes.CDLL(c)
                    opus_path = c
                    print(f"[dec] loaded libopus: {c}")
                    break
                except Exception:
                    continue
        else:
            try:
                ctypes.CDLL(opus_path)
            except Exception:
                pass
        if opus_path:
            orig_find = ctypes.util.find_library
            def _find(name):
                if name == 'opus':
                    return opus_path
                return orig_find(name)
            ctypes.util.find_library = _find
        return opus_path

    def _init_opus(self):
        try:
            self._load_libopus()
            import opuslib
            import opuslib.api.decoder as dec_api
            self._opus_api = dec_api
            # Keep decoders for both channel counts; pick per-packet based on TOC/header
            self.opus_dec_mono = opuslib.Decoder(self.rate, 1)
            self.opus_dec_stereo = opuslib.Decoder(self.rate, 2)
            self.opus_dec = self.opus_dec_mono  # compat
            self.opus_dec_ch = 1
            print(f"[dec] opus decoder ready (rate={self.rate}, mono+stereo)")
        except Exception as e:
            self._opus_api = None
            print(f"[dec] opus decoder unavailable: {e}")

    def _decode_opus_payload(self, payload: bytes):
        api = self._opus_api
        if api is None or not payload:
            return b""
        # Try TOC-based decode first
        try:
            nb_frames = api.packet_get_nb_frames(payload)
            spf = api.packet_get_samples_per_frame(payload, self.rate)
            ch = api.packet_get_nb_channels(payload)
            frame_size = int(nb_frames) * int(spf)
            if 0 < frame_size <= 2880 * 48:
                for dec, dec_ch in ((self.opus_dec_stereo, 2), (self.opus_dec_mono, 1)) if int(ch)==2 else ((self.opus_dec_mono, 1), (self.opus_dec_stereo, 2)):
                    try:
                        pcm = dec.decode(payload, frame_size, decode_fec=False)
                        if dec_ch == 2:
                            pcm = stereo_to_mono_s16(pcm)
                        return pcm
                    except Exception:
                        continue
        except Exception:
            pass
        # Fallback: try common frame sizes/channels
        for dec, dec_ch in ((self.opus_dec_mono, 1), (self.opus_dec_stereo, 2)):
            for fs in self.opus_frame_sizes:
                try:
                    pcm = dec.decode(payload, fs, decode_fec=False)
                    if dec_ch == 2:
                        pcm = stereo_to_mono_s16(pcm)
                    return pcm
                except Exception:
                    continue
        return b""

    def decode(self, packet: bytes) -> bytes:
        if not packet:
            return b""
        if self.codec == "pcm16":
            return packet
        if self.codec == "pcm8":
            try:
                import audioop
                return audioop.lin2lin(packet, 1, 2)
            except Exception:
                return b""
        if self.codec in ("opus", "opusFS320"):
            total = self._ok + self._fail
            if total < 5:
                hx = packet[:16].hex()
                print(f"\n[dec] pkt#{total} len={len(packet)} head={hx}")
            # Determine stable payload offset. Many Omi BLE audio packets carry a 3-byte
            # header/prefix before opus data; per-packet "first decode wins" can pick wrong
            # offsets and corrupt the stream (decoder state + garbled PCM). Prefer locked offset.
            if not hasattr(self, "_opus_off"):
                self._opus_off = None
            offsets = [self._opus_off] if self._opus_off is not None else [3, 0, 2, 1, 4]
            for off in offsets:
                if off is None or off >= len(packet):
                    continue
                payload = packet[off:] if off else packet
                pcm = self._decode_opus_payload(payload)
                if pcm:
                    self._ok += 1
                    # lock offset after first successful decode to keep stream consistent
                    if self._opus_off is None:
                        self._opus_off = off
                        print(f"\n[dec] locked opus payload offset={off}")
                    if self._ok in (1, 2, 10) or (self._ok + self._fail) % 500 == 0:
                        print(f"\n[dec] ok={self._ok} fail={self._fail} off={off} pkt={len(packet)} out={len(pcm)}")
                    return pcm
            # if locked offset failed, try to recover by probing others (but keep state risk)
            if self._opus_off is not None:
                for off in (0, 1, 2, 3, 4):
                    if off == self._opus_off or off >= len(packet):
                        continue
                    payload = packet[off:]
                    pcm = self._decode_opus_payload(payload)
                    if pcm:
                        self._ok += 1
                        if (self._ok + self._fail) % 200 == 0:
                            print(f"\n[dec] ok={self._ok} fail={self._fail} off={off} (recovered, locked={self._opus_off})")
                        return pcm
            self._fail += 1
            if (self._ok + self._fail) in (100, 500) or (self._ok + self._fail) % 1000 == 0:
                print(f"\n[dec] ok={self._ok} fail={self._fail} (locked={getattr(self,'_opus_off',None)})")
            return b""
        return b""


def stereo_to_mono_s16(pcm: bytes) -> bytes:
    if len(pcm) < 4:
        return pcm
    # average L/R samples
    import array
    samples = array.array('h')
    samples.frombytes(pcm[: (len(pcm)//4)*4])
    mono = array.array('h', [0] * (len(samples)//2))
    for i in range(0, len(samples), 2):
        mono[i//2] = int((int(samples[i]) + int(samples[i+1])) / 2)
    return mono.tobytes()


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


def play_pcm_local(pcm: bytes, rate: int = 24000):
    cmds = [
        ["aplay", "-q", "-f", "S16_LE", "-r", str(rate), "-c", "1", "-t", "raw"],
        ["ffplay", "-nodisp", "-autoexit", "-loglevel", "error", "-f", "s16le", "-ar", str(rate), "-ac", "1", "-i", "pipe:0"],
        ["play", "-q", "-t", "raw", "-r", str(rate), "-e", "signed", "-b", "16", "-c", "1", "-"],
    ]
    for cmd in cmds:
        try:
            p = subprocess.run(cmd, input=pcm, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if p.returncode == 0:
                return
        except Exception:
            continue


async def play_pcm_devkit(client: BleakClient, pcm: bytes):
    if not pcm or len(pcm) < 2:
        return
    transmissions = plan_transmissions(pcm)
    audio_dur = len(pcm) / (8000 * 2)
    print(f"[spk-devkit] playing {len(pcm)} bytes ({audio_dur:.2f}s audio)...")
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


async def run(api_key: str, device_id: str, mic_rate: int, out_rate: int, output: str, settings_file: str | None):
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
    headers = {"Authorization": f"Token {api_key}"}

    print(f"[ble] connecting to DevKit {device_id} (must not be connected to phone, MAX_CONN=1)...")
    async with BleakClient(device_id, timeout=25.0) as client:
        try:
            if hasattr(client, "_backend") and hasattr(client._backend, "_acquire_mtu"):
                await client._backend._acquire_mtu()
        except Exception as e:
            print(f"[ble] mtu negotiate skipped: {e}")
        # read codec
        codec = "opus"
        try:
            raw = await client.read_gatt_char(AUDIO_CODEC)
            if raw:
                codec = CODEC_BY_ID.get(raw[0], "opus")
        except Exception as e:
            print(f"[ble] codec read failed ({e}), assuming opus")
        print(f"[ble] connected: {client.is_connected}, mtu={getattr(client,'mtu_size',None)} codec={codec}")

        decoder = AudioDecoder(codec)
        if codec in ("opus", "opusFS320") and decoder.opus_dec is None:
            print("[warn] No opus decoder available. On NixOS try: LD_LIBRARY_PATH=/nix/store/a7r1yfbkqfb8bb1ad6sny5cs3sr3nk4n-libopus-1.5.2/lib ...")
            print("[warn] Without decoding, DevKit opus mic audio cannot be sent as linear16 to DG Agent.")

        connect_kw = dict(ping_interval=20, ping_timeout=20, close_timeout=5, max_size=16 * 1024 * 1024)
        params = inspect.signature(websockets.connect).parameters
        if "extra_headers" in params:
            ws_cm = websockets.connect(DG_AGENT_URL, extra_headers=headers, **connect_kw)
        elif "additional_headers" in params:
            ws_cm = websockets.connect(DG_AGENT_URL, additional_headers=headers, **connect_kw)
        else:
            ws_cm = websockets.connect(DG_AGENT_URL, extra_headers=headers, **connect_kw)

        print(f"[dg] connecting (devkit mic {codec}@16k -> linear16 {mic_rate}Hz agent in, out {out_rate}Hz -> {output})")
        async with ws_cm as dg_ws:
            await dg_ws.send(json.dumps(settings))
            print("[dg] Settings sent. Speak into the DevKit mic. Ctrl+C to quit.")

            stop = asyncio.Event()
            ka_task = asyncio.create_task(keepalive(dg_ws, stop))
            audio_q: asyncio.Queue[bytes | None] = asyncio.Queue(maxsize=500)
            play_q: asyncio.Queue[bytes | None] = asyncio.Queue()
            speaking = asyncio.Event()
            stats = {"mic_pkts": 0, "mic_bytes": 0, "pcm_sent": 0, "pcm_bytes_sent": 0, "decode_fail": 0}
            diag = {"samples": 0, "sumsq": 0.0, "peak": 0, "dump_bytes": 0}
            dump_path = "/home/palontologist/.tmp/opencode/devkit_mic_decoded.wav"
            dump_wav = None
            try:
                dump_wav = wave.open(dump_path, "wb")
                dump_wav.setnchannels(1)
                dump_wav.setsampwidth(2)
                dump_wav.setframerate(mic_rate)
                print(f"[diag] saving decoded mic audio to {dump_path}")
            except Exception as e:
                print(f"[diag] could not open dump wav: {e}")
                dump_wav = None

            async def on_mic(_sender, data: bytearray):
                if stop.is_set():
                    return
                pkt = bytes(data)
                stats["mic_pkts"] += 1
                stats["mic_bytes"] += len(pkt)
                # drop mic while agent speaking to reduce echo/feedback
                if speaking.is_set():
                    return
                pcm = decoder.decode(pkt)
                if not pcm:
                    stats["decode_fail"] += 1
                    return
                # diagnostics: RMS/peak and dump first ~15s
                try:
                    import array, math
                    a = array.array('h'); a.frombytes(pcm[: (len(pcm)//2)*2])
                    if a:
                        peak = max(abs(x) for x in a)
                        diag["peak"] = max(diag["peak"], peak)
                        diag["samples"] += len(a)
                        diag["sumsq"] += sum(x*x for x in a)
                    if dump_wav is not None and diag["dump_bytes"] < mic_rate * 2 * 15:
                        dump_wav.writeframes(pcm)
                        diag["dump_bytes"] += len(pcm)
                except Exception:
                    pass
                if stats["mic_pkts"] == 1 or stats["mic_pkts"] % 300 == 0:
                    rms = 0
                    if diag["samples"]:
                        rms = int((diag["sumsq"]/diag["samples"]) ** 0.5)
                    print(f"\n[dbg] devkit mic pkts={stats['mic_pkts']} bytes={stats['mic_bytes']} decoded_sent={stats['pcm_bytes_sent']} decode_fail={stats['decode_fail']} rms={rms} peak={diag['peak']}")
                try:
                    audio_q.put_nowait(pcm)
                except asyncio.QueueFull:
                    try:
                        audio_q.get_nowait()
                        audio_q.put_nowait(pcm)
                    except Exception:
                        pass

            await client.start_notify(AUDIO_DATA, on_mic)

            async def sender():
                try:
                    while True:
                        pcm = await audio_q.get()
                        if pcm is None:
                            break
                        await dg_ws.send(pcm)
                        stats["pcm_sent"] += 1
                        stats["pcm_bytes_sent"] += len(pcm)
                except Exception as e:
                    print(f"[dg] sender ended: {e}")

            async def player():
                loop = asyncio.get_event_loop()
                while True:
                    item = await play_q.get()
                    if item is None:
                        break
                    pcm_out, rate_out = item
                    speaking.set()
                    try:
                        if output == "laptop":
                            await loop.run_in_executor(None, play_pcm_local, pcm_out, rate_out)
                        elif output == "devkit":
                            pcm8 = await loop.run_in_executor(None, resample_pcm16, pcm_out, rate_out, 8000)
                            await play_pcm_devkit(client, pcm8)
                        elif output == "both":
                            # laptop real-time; devkit may lag
                            pcm8 = await loop.run_in_executor(None, resample_pcm16, pcm_out, rate_out, 8000)
                            await loop.run_in_executor(None, play_pcm_local, pcm_out, rate_out)
                            try:
                                await play_pcm_devkit(client, pcm8)
                            except Exception as e:
                                print(f"[spk-devkit] error: {e}")
                    except Exception as e:
                        print(f"[spk] error: {e}")
                    finally:
                        speaking.clear()
                    play_q.task_done()

            sender_task = asyncio.create_task(sender())
            player_task = asyncio.create_task(player())
            agent_buf = bytearray()

            async def flush_agent(reason: str):
                nonlocal agent_buf
                if not agent_buf:
                    return
                raw = bytes(agent_buf)
                agent_buf.clear()
                print(f"[dg] agent audio {len(raw)} bytes ({reason})")
                await play_q.put((raw, out_rate))

            try:
                async for msg in dg_ws:
                    if isinstance(msg, (bytes, bytearray)):
                        agent_buf.extend(msg)
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
                    elif et == "AgentAudioDone":
                        print("[event] AgentAudioDone")
                        await flush_agent("AgentAudioDone")
                    elif et == "Welcome":
                        print(f"[dg] Welcome: {evt.get('request_id')}")
                    elif et == "SettingsApplied":
                        print("[dg] SettingsApplied")
                    elif et in ("Error", "Warning"):
                        print(f"[dg] {et}: {evt}")
            except websockets.exceptions.ConnectionClosed as e:
                print(f"[dg] connection closed: {e}")
            finally:
                stop.set()
                await flush_agent("shutdown")
                await play_q.put(None)
                try:
                    await audio_q.put(None)
                except Exception:
                    pass
                try:
                    await client.stop_notify(AUDIO_DATA)
                except Exception:
                    pass
                for t in (ka_task, sender_task):
                    t.cancel()
                await player_task
                try:
                    if dump_wav is not None:
                        dump_wav.close()
                        print(f"[diag] saved decoded mic audio: {dump_path} ({diag['dump_bytes']} bytes)")
                except Exception:
                    pass
                rms = int((diag['sumsq']/diag['samples'])**0.5) if diag['samples'] else 0
                print(f"[stats] mic_pkts={stats['mic_pkts']} mic_bytes={stats['mic_bytes']} pcm_frames_sent={stats['pcm_sent']} pcm_bytes_sent={stats['pcm_bytes_sent']} decode_fail={stats['decode_fail']} rms={rms} peak={diag['peak']}")


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--device", default=DEVICE_ID)
    ap.add_argument("--output", choices=["laptop", "devkit", "both"], default="laptop", help="where to play agent responses")
    ap.add_argument("--mic-rate", type=int, default=16000, help="agent input sample rate (decoded PCM sent as linear16)")
    ap.add_argument("--out-rate", type=int, default=24000, help="agent output sample rate")
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
        await run(api_key, args.device, args.mic_rate, args.out_rate, args.output, args.settings_file)
    except KeyboardInterrupt:
        print("\n[bye]")


if __name__ == "__main__":
    asyncio.run(main())
