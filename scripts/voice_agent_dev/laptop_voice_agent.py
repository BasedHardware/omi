#!/usr/bin/env python3
"""
Laptop mic -> Deepgram STT -> (OpenAI/simple) agent -> Deepgram TTS -> Omi DevKit 2 speaker.
Turn-based: press Enter to record, agent replies out loud from the DevKit.

Adds latency instrumentation and chunked (sentence/clause) TTS+playback for smoother responses.

Requirements:
  - Local dev server running at http://127.0.0.1:8000 (tts_dev_server.py) with DEEPGRAM_API_KEY
  - DevKit advertising and not connected elsewhere (BLE MAX_CONN=1)
  - backend/.env.local-dev loaded for API keys (DEEPGRAM_API_KEY, OPENAI_API_KEY optional)
  - arecord available for mic capture
"""
import argparse
import asyncio
import os
import re
import struct
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx
from bleak import BleakClient

# BLE / DevKit speaker
DEVICE_ID = "C3:43:D7:97:11:10"
AUDIO_WRITE_UUID = "19B10003-E8F2-537E-4F6C-D104768A1214"
PACKET_SIZE = 400
MAX_MONO_BYTES_PER_TRANSMISSION = 35000

# Services
TTS_URL = "http://127.0.0.1:8000/v2/tts/synthesize"
AUTH_TOKEN = "local-dev-admin-key-devuser"
DG_LISTEN_URL = "https://api.deepgram.com/v1/listen"


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


def pad_for_firmware(pcm: bytes) -> bytes:
    r = len(pcm) % PACKET_SIZE
    add = 8 if r == 0 else (2 if r == 4 else 0)
    return pcm + (b"\x00" * add) if add else pcm


def plan_transmissions(pcm: bytes):
    return [
        pad_for_firmware(pcm[o:o + MAX_MONO_BYTES_PER_TRANSMISSION])
        for o in range(0, len(pcm), MAX_MONO_BYTES_PER_TRANSMISSION)
    ]


# Reuse HTTP client for lower TTS latency (connection reuse)
_http: httpx.Client | None = None
_tts_cache: dict[str, bytes] = {}

def get_http() -> httpx.Client:
    global _http
    if _http is None:
        _http = httpx.Client(timeout=60.0)
    return _http


def fetch_pcm16_8k(text: str) -> bytes:
    key = (text or "").strip()
    if key in _tts_cache:
        return _tts_cache[key]
    r = get_http().post(
        TTS_URL,
        headers={"Authorization": f"Bearer {AUTH_TOKEN}", "Content-Type": "application/json"},
        json={"text": text, "output_format": "pcm_8000"},
    )
    r.raise_for_status()
    data = r.content
    if data[:3] == b"ID3" or (len(data) > 1 and data[0] == 0xFF and (data[1] & 0xE0) == 0xE0):
        raise RuntimeError("TTS returned MP3, not pcm_8000")
    # cache short/common phrases to avoid repeat latency
    if len(key) <= 160:
        _tts_cache[key] = data
    return data



def play_pcm_local(pcm: bytes) -> float:
    """Play raw s16le mono 8kHz on laptop speaker (real-time). Returns wall time."""
    t0 = time.perf_counter()
    cmds = [
        ["aplay", "-q", "-f", "S16_LE", "-r", "8000", "-c", "1", "-t", "raw"],
        ["ffplay", "-nodisp", "-autoexit", "-loglevel", "error", "-f", "s16le", "-ar", "8000", "-ac", "1", "-i", "pipe:0"],
        ["play", "-q", "-t", "raw", "-r", "8000", "-e", "signed", "-b", "16", "-c", "1", "-"],
    ]
    last_err = None
    for cmd in cmds:
        try:
            p = subprocess.run(cmd, input=pcm, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if p.returncode == 0:
                return time.perf_counter() - t0
            last_err = (p.stderr or b"").decode("utf-8", "replace").strip().splitlines()[-1] if p.stderr else f"rc={p.returncode}"
        except FileNotFoundError:
            continue
        except Exception as e:
            last_err = str(e)
    print(f"[spk-local] error: {last_err}")
    return time.perf_counter() - t0

async def _play_pcm_pumped(client: BleakClient, pcm: bytes, pump: asyncio.Event) -> float:
    t0 = time.perf_counter()
    transmissions = plan_transmissions(pcm)
    for i, mono in enumerate(transmissions, 1):
        header = struct.pack("<I", len(mono))
        pump.clear()
        await client.write_gatt_char(AUDIO_WRITE_UUID, header, response=True)
        await asyncio.wait_for(pump.wait(), timeout=10)
        for off in range(0, len(mono), PACKET_SIZE):
            chunk = mono[off:off + PACKET_SIZE]
            pump.clear()
            await client.write_gatt_char(AUDIO_WRITE_UUID, chunk, response=True)
            if len(chunk) < PACKET_SIZE:
                break
            await asyncio.wait_for(pump.wait(), timeout=10)
        # minimal inter-transmission gap; avoid extra pause after last
        if i < len(transmissions):
            await asyncio.sleep(0.05)
    return time.perf_counter() - t0


async def play_pcm(client: BleakClient, pcm: bytes) -> float:
    """Single-shot playback (manages notify lifecycle)."""
    pump = asyncio.Event()

    async def on_notify(sender, data: bytearray):
        pump.set()

    await client.start_notify(AUDIO_WRITE_UUID, on_notify)
    await asyncio.sleep(0.05)
    try:
        return await _play_pcm_pumped(client, pcm, pump)
    finally:
        try:
            await client.stop_notify(AUDIO_WRITE_UUID)
        except Exception:
            pass


def split_reply(text: str) -> list[str]:
    """Split into speakable chunks for smoother playback.
    Prefer sentence boundaries; also break long clauses on commas/colons/semicolons/questions.
    """
    text = re.sub(r"\s+", " ", (text or "").strip())
    if not text:
        return []
    # Split into sentence-like units, keeping punctuation
    parts = re.split(r"(?<=[.!?])\s+", text)
    chunks: list[str] = []
    for p in parts:
        p = p.strip()
        if not p:
            continue
        # If a sentence is long, break on clause punctuation for earlier audio start
        if len(p) > 90:
            sub = re.split(r"(?<=[,;:]|\?)\s+", p)
            buf = ""
            for s in sub:
                s = s.strip()
                if not s:
                    continue
                if not buf:
                    buf = s
                elif len(buf) + 1 + len(s) <= 90:
                    buf = buf + " " + s
                else:
                    chunks.append(buf)
                    buf = s
            if buf:
                chunks.append(buf)
        else:
            chunks.append(p)
    # Merge tiny trailing fragments
    merged: list[str] = []
    for c in chunks:
        if merged and len(c) < 18 and len(merged[-1]) < 90:
            merged[-1] = merged[-1] + " " + c
        else:
            merged.append(c)
    return merged or [text]


async def speak(client: BleakClient | None, text: str, label: str = "agent", output: str = "devkit") -> dict:
    """output: 'devkit' | 'laptop' | 'both'"""
    text = (text or "").strip()
    if not text:
        return {"chunks": 0, "tts_s": 0.0, "play_s": 0.0, "ttfa_s": None, "total_s": 0.0}
    chunks = split_reply(text)
    out_label = {"devkit": "agent->devkit", "laptop": "agent->laptop", "both": "agent->devkit+laptop"}.get(output, label)
    print(f"[{out_label}] {text}")
    if len(chunks) > 1:
        mode = "pipelined" if output != "devkit" else "pipelined (synthesize next while playing)"
        print(f"[tts] speaking in {len(chunks)} chunks ({mode}, output={output})")
    t_start = time.perf_counter()
    tts_total = 0.0
    play_total = 0.0
    ttfa = None
    loop = asyncio.get_event_loop()

    async def fetch_one(idx: int, chunk: str):
        t0 = time.perf_counter()
        pcm = await loop.run_in_executor(None, fetch_pcm16_8k, chunk)
        return idx, chunk, pcm, time.perf_counter() - t0

    pump = asyncio.Event()
    notify_on = False

    async def on_notify(sender, data: bytearray):
        pump.set()

    if output in ("devkit", "both") and client is not None:
        await client.start_notify(AUDIO_WRITE_UUID, on_notify)
        await asyncio.sleep(0.05)
        notify_on = True
    try:
        next_task: asyncio.Task | None = asyncio.create_task(fetch_one(1, chunks[0]))
        for i, chunk in enumerate(chunks, 1):
            try:
                assert next_task is not None
                idx, ch_text, pcm, tts_s = await next_task
                next_task = None
            except Exception as e:
                print(f"[tts] error (chunk {i}/{len(chunks)}): {e}")
                next_task = None
                if i < len(chunks):
                    next_task = asyncio.create_task(fetch_one(i + 1, chunks[i]))
                continue

            tts_total += tts_s
            audio_dur = len(pcm) / (8000 * 2)
            if len(chunks) > 1:
                preview = ch_text if len(ch_text) <= 60 else ch_text[:57] + "..."
                print(f"[tts] chunk {i}/{len(chunks)} ready: tts={tts_s:.2f}s audio={audio_dur:.2f}s | {preview!r}")
            else:
                print(f"[tts] tts={tts_s:.2f}s audio={audio_dur:.2f}s bytes={len(pcm)}")

            # prefetch next while playing (esp. helpful for laptop/real-time playback)
            if i < len(chunks):
                next_task = asyncio.create_task(fetch_one(i + 1, chunks[i]))

            if ttfa is None:
                ttfa = time.perf_counter() - t_start
                print(f"[latency] time-to-first-audio: {ttfa:.2f}s")

            try:
                if output == "laptop":
                    play_s = await loop.run_in_executor(None, play_pcm_local, pcm)
                elif output == "both" and client is not None:
                    # play on laptop for immediacy; devkit stream will lag (BLE ~4x realtime)
                    play_s = await loop.run_in_executor(None, play_pcm_local, pcm)
                    try:
                        await _play_pcm_pumped(client, pcm, pump)
                    except Exception as e:
                        print(f"[spk-devkit] error: {e}")
                else:
                    assert client is not None
                    play_s = await _play_pcm_pumped(client, pcm, pump)
            except Exception as e:
                print(f"[spk] error (chunk {i}/{len(chunks)}): {e}")
                continue
            play_total += play_s
            if len(chunks) > 1:
                pending = " (next tts in-flight)" if (next_task and not next_task.done()) else ""
                print(f"[spk] chunk {i}/{len(chunks)} played in {play_s:.2f}s{pending}")
        if next_task and not next_task.done():
            next_task.cancel()
    finally:
        if notify_on and client is not None:
            try:
                await client.stop_notify(AUDIO_WRITE_UUID)
            except Exception:
                pass
    total = time.perf_counter() - t_start
    return {"chunks": len(chunks), "tts_s": tts_total, "play_s": play_total, "ttfa_s": ttfa, "total_s": total}


def record_wav(path: str, seconds: float, device: str | None, rate: int = 16000) -> tuple[bool, float]:
    """Record mic audio. Runs until Enter is pressed or `seconds` max timeout.
    Returns (ok, duration_seconds).
    """
    max_s = max(1.0, float(seconds))
    cmd = ["arecord", "-f", "S16_LE", "-r", str(rate), "-c", "1", "-t", "wav", path]
    if device:
        cmd[1:1] = ["-D", device]
    print(f"[mic] recording... speak now, press Enter to stop (max {max_s:.0f}s)")
    t0 = time.perf_counter()
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except Exception as e:
        print(f"[mic] error: {e}")
        return False, 0.0

    try:
        import select
        deadline = t0 + max_s
        stopped_by_user = False
        # Wait for Enter (stdin ready) or timeout without leaving a blocking readline behind
        while True:
            remaining = deadline - time.perf_counter()
            if remaining <= 0:
                break
            try:
                rlist, _, _ = select.select([sys.stdin], [], [], min(0.2, remaining))
            except Exception:
                time.sleep(min(0.2, max(0, remaining)))
                continue
            if rlist:
                try:
                    sys.stdin.readline()  # consume the Enter
                except Exception:
                    pass
                stopped_by_user = True
                break
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=1.5)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
    except Exception:
        try:
            if proc.poll() is None:
                proc.kill()
        except Exception:
            pass
    dur = time.perf_counter() - t0
    try:
        # drain stderr for diagnostics on failure
        _, stderr = proc.communicate(timeout=0.5)
    except Exception:
        stderr = b""
    if not os.path.exists(path) or os.path.getsize(path) <= 44:
        if stderr:
            err = stderr.decode("utf-8", "replace").strip().splitlines()[-1]
            if err:
                print(f"[mic] error: {err}")
        return False, dur
    print(f"[mic] captured {dur:.2f}s")
    return True, dur


def transcribe_deepgram(wav_path: str) -> tuple[str, float]:
    key = os.getenv("DEEPGRAM_API_KEY", "")
    if not key:
        print("[stt] DEEPGRAM_API_KEY missing")
        return "", 0.0
    params = {"model": "nova-2", "language": "en", "smart_format": "true", "punctuate": "true"}
    url = DG_LISTEN_URL + "?" + "&".join(f"{k}={v}" for k, v in params.items())
    headers = {"Authorization": f"Token {key}", "Content-Type": "audio/wav"}
    with open(wav_path, "rb") as f:
        audio = f.read()
    t0 = time.perf_counter()
    try:
        with httpx.Client(timeout=60.0) as c:
            r = c.post(url, headers=headers, content=audio)
            r.raise_for_status()
            data = r.json()
        alts = (((data.get("results") or {}).get("channels") or [{}])[0].get("alternatives") or [{}])
        transcript = (alts[0].get("transcript") or "").strip() if alts else ""
        conf = alts[0].get("confidence") if alts else None
        dt = time.perf_counter() - t0
        meta = data.get("metadata") or {}
        dg_dur = meta.get("duration")
        extra = f" dg_duration={dg_dur}" if dg_dur is not None else ""
        print(f"[stt] {len(audio)} bytes -> transcript={transcript!r} conf={conf} in {dt:.2f}s{extra}")
        return transcript, dt
    except Exception as e:
        dt = time.perf_counter() - t0
        print(f"[stt] error after {dt:.2f}s: {e}")
        return "", dt


def agent_reply(user_text: str, history: list[dict]) -> tuple[str, float, str]:
    user_text = user_text.strip()
    if not user_text:
        return "I didn't catch that. Could you say it again?", 0.0, "empty"
    openai_key = os.getenv("OPENAI_API_KEY", "")
    if openai_key:
        t0 = time.perf_counter()
        try:
            messages = [
                {"role": "system", "content": "You are Omi, a helpful concise voice assistant running on a DevKit device. Reply in 1-3 short spoken sentences."},
                *history[-8:],
                {"role": "user", "content": user_text},
            ]
            with httpx.Client(timeout=30.0) as c:
                r = c.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={"Authorization": f"Bearer {openai_key}", "Content-Type": "application/json"},
                    json={"model": "gpt-4o-mini", "messages": messages, "max_tokens": 120, "temperature": 0.6},
                )
                r.raise_for_status()
                data = r.json()
                txt = (((data.get("choices") or [{}])[0].get("message") or {}).get("content") or "").strip()
                dt = time.perf_counter() - t0
                if txt:
                    return txt, dt, "openai"
                print(f"[agent] empty openai response in {dt:.2f}s")
        except Exception as e:
            dt = time.perf_counter() - t0
            print(f"[agent] openai fallback after {dt:.2f}s: {e}")
    # Simple deterministic fallback
    t0 = time.perf_counter()
    low = user_text.lower()
    if "hello" in low or "hi" in low:
        reply = "Hi! I'm your Omi DevKit voice agent. How can I help?"
    elif "time" in low:
        import datetime
        reply = f"It's {datetime.datetime.now().strftime('%I:%M %p').lstrip('0')}."
    elif "name" in low:
        reply = "I'm Omi, running locally and speaking from your DevKit."
    elif any(w in low for w in ("task", "remind", "todo")):
        reply = f"Got it. I noted: {user_text}."
    else:
        reply = f"You said: {user_text}. I'm here and listening."
    return reply, time.perf_counter() - t0, "local-fallback"


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--device", default=DEVICE_ID, help="BLE address of DevKit")
    ap.add_argument("--mic", default=None, help="arecord device, e.g. hw:0,7 or hw:0,6")
    ap.add_argument("--seconds", type=float, default=6.0, help="max record seconds per turn (default 6). Press Enter to stop earlier for faster response.")
    ap.add_argument("--rate", type=int, default=16000, help="mic sample rate (default 16000)")
    ap.add_argument("--env", default="/home/palontologist/Downloads/dev/omi-app/backend/.env.local-dev", help="env file with API keys")
    ap.add_argument("--no-chunk", action="store_true", help="disable sentence/clause chunked playback")
    ap.add_argument("--output", choices=["devkit", "laptop", "both"], default="devkit", help="where to play agent audio (laptop is real-time/fast; devkit BLE speaker is ~4x slower than realtime)")
    args = ap.parse_args()

    load_env(args.env)
    has_dg = bool(os.getenv("DEEPGRAM_API_KEY"))
    has_oai = bool(os.getenv("OPENAI_API_KEY"))
    print(f"[env] DEEPGRAM_API_KEY={'set' if has_dg else 'MISSING'} OPENAI_API_KEY={'set' if has_oai else 'missing'}")
    if not has_dg:
        print("[warn] DEEPGRAM_API_KEY not set; STT/TTS may fail. Ensure local server has it.")
    if not has_oai:
        print("[info] OPENAI_API_KEY missing -> using local fallback replies (simpler, but faster/no LLM latency).")

    history: list[dict] = []

    async def run_loop(client: BleakClient | None):
        await speak(client, "Voice agent ready. Press enter to talk, then press enter again to send.", output=args.output)
        while True:
            try:
                cmd = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: input("\n[you] Press Enter to START talking (q to quit): ")
                )
            except (EOFError, KeyboardInterrupt):
                break
            if (cmd or "").strip().lower() in ("q", "quit", "exit"):
                break
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tf:
                wav_path = tf.name
            try:
                t_turn = time.perf_counter()
                ok, record_s = await asyncio.get_event_loop().run_in_executor(
                    None, record_wav, wav_path, args.seconds, args.mic, args.rate
                )
                t_record_end = time.perf_counter()
                if not record_s:
                    record_s = t_record_end - t_turn
                if not ok:
                    await speak(client, "I couldn't record from the microphone.", output=args.output)
                    continue

                transcript, stt_s = transcribe_deepgram(wav_path)
                print(f"[timing] record={record_s:.2f}s stt={stt_s:.2f}s")
                if not transcript:
                    print("[stt] (no speech recognized)")
                    await speak(client, "I didn't catch that. Try again.", output=args.output)
                    continue

                print(f"[you] {transcript}")
                history.append({"role": "user", "content": transcript})

                t_agent0 = time.perf_counter()
                reply, agent_s, agent_src = agent_reply(transcript, history)
                if agent_s == 0.0:
                    agent_s = time.perf_counter() - t_agent0
                print(f"[timing] agent={agent_s:.2f}s ({agent_src})")
                history.append({"role": "assistant", "content": reply})

                if args.no_chunk:
                    print(f"[agent] {reply}")
                    t_tts0 = time.perf_counter()
                    pcm = await asyncio.get_event_loop().run_in_executor(None, fetch_pcm16_8k, reply)
                    tts_s = time.perf_counter() - t_tts0
                    audio_dur = len(pcm) / (8000 * 2)
                    print(f"[tts] tts={tts_s:.2f}s audio={audio_dur:.2f}s bytes={len(pcm)}")
                    ttfa = stt_s + agent_s + tts_s
                    print(f"[latency] approx time-to-first-audio (after record): {ttfa:.2f}s")
                    if args.output == "laptop":
                        play_s = await asyncio.get_event_loop().run_in_executor(None, play_pcm_local, pcm)
                    elif args.output == "both" and client is not None:
                        play_s = await asyncio.get_event_loop().run_in_executor(None, play_pcm_local, pcm)
                        try:
                            await play_pcm(client, pcm)
                        except Exception as e:
                            print(f"[spk-devkit] error: {e}")
                    elif client is not None:
                        play_s = await play_pcm(client, pcm)
                    else:
                        play_s = await asyncio.get_event_loop().run_in_executor(None, play_pcm_local, pcm)
                    spk = {"chunks": 1, "tts_s": tts_s, "play_s": play_s, "ttfa_s": tts_s, "total_s": tts_s + play_s}
                else:
                    spk = await speak(client, reply, output=args.output)

                resp_after_record = stt_s + agent_s + (spk.get("tts_s") or 0.0) + (spk.get("play_s") or 0.0)
                ttfa_after_record = stt_s + agent_s + (spk.get("ttfa_s") or 0.0)
                print(
                    "[latency] after-record: "
                    f"stt={stt_s:.2f}s agent={agent_s:.2f}s tts={spk.get('tts_s',0):.2f}s "
                    f"play={spk.get('play_s',0):.2f}s | ttfa={ttfa_after_record:.2f}s total={resp_after_record:.2f}s "
                    f"(chunks={spk.get('chunks',0)})"
                )
            finally:
                try:
                    os.unlink(wav_path)
                except Exception:
                    pass

    try:
        if args.output == "laptop":
            print("[ble] skipped (output=laptop). Use --output devkit/both to play through DevKit.")
            await run_loop(None)
        else:
            print(f"[ble] connecting to DevKit {args.device} (must not be connected to phone, MAX_CONN=1)...")
            async with BleakClient(args.device, timeout=25.0) as client:
                try:
                    if hasattr(client, "_backend") and hasattr(client._backend, "_acquire_mtu"):
                        await client._backend._acquire_mtu()
                except Exception as e:
                    print(f"[ble] mtu negotiate (backend) skipped: {e}")
                mtu = getattr(client, "mtu_size", None)
                print(f"[ble] connected: {client.is_connected}, mtu={mtu}")
                await run_loop(client)
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"[error] {e}")
        if args.output != "laptop":
            print("Hints: DevKit must be advertising & not connected to phone (MAX_CONN=1). Power-cycle or disconnect from phone, then retry.")
        print("If mic capture fails, try --mic hw:0,7 (DMIC 16k) or --mic hw:0,6.")
        sys.exit(1)

    print("[bye]")


if __name__ == "__main__":
    asyncio.run(main())
