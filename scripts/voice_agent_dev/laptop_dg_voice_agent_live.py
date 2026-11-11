#!/usr/bin/env python3
"""
Live Deepgram Voice Agent on laptop:
  laptop mic (streaming linear16) -> Deepgram Agent API -> laptop speaker (streaming audio)

This is the "live/interactive" agent (STT+LLM+TTS handled by Deepgram in one websocket).
Press Ctrl+C to quit.

Usage:
  cd /home/palontologist/Downloads/dev/omi-app
  backend/venv/bin/python /home/palontologist/.tmp/opencode/laptop_dg_voice_agent_live.py

Options:
  --mic hw:0,7        arecord device (try hw:0,7 DMIC 16kHz or hw:0,6 if default fails)
  --mic-rate 16000    mic/input sample rate (agent input configured to match)
  --out-rate 24000    agent output sample rate (played on laptop at this rate)
  --env PATH          env file with DEEPGRAM_API_KEY (default: backend/.env.local-dev)
"""
import argparse
import inspect
import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path

import websockets

DG_AGENT_URL = "wss://agent.deepgram.com/v1/agent/converse"


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
    """Settings for Deepgram Voice Agent. Loads from --settings-file if provided (JSON),
    otherwise uses a simple laptop-friendly default. Audio rates in file are respected for playback."""
    if settings_file:
        p = Path(settings_file)
        settings = json.loads(p.read_text())
        if isinstance(settings, dict):
            settings.setdefault("type", "Settings")
        return settings
    return {
        "type": "Settings",
        "audio": {
            "input": {"encoding": "linear16", "sample_rate": mic_rate},
            "output": {"encoding": "linear16", "sample_rate": out_rate, "container": "none"},
        },
        "agent": {
            "listen": {
                "provider": {
                    "type": "deepgram",
                    "model": "nova-3",
                }
            },
            "think": {
                "provider": {
                    "type": "open_ai",
                    "model": "gpt-4o-mini",
                },
                "prompt": (
                    "You are Omi, a helpful concise voice assistant. "
                    "This is a live voice conversation on a laptop. "
                    "Reply in 1-3 short spoken sentences. Be conversational, clear, and responsive."
                ),
            },
            "speak": {
                "provider": {
                    "type": "deepgram",
                    "model": "aura-2-thalia-en",
                }
            },
            "greeting": "Hey, I'm ready. What would you like to talk about?",
        },
    }


async def mic_sender(proc: subprocess.Popen, dg_ws, chunk_bytes: int, stop: asyncio.Event, stats: dict):
    loop = asyncio.get_event_loop()
    try:
        while not stop.is_set() and proc.stdout:
            data = await loop.run_in_executor(None, proc.stdout.read, chunk_bytes)
            if not data:
                break
            stats["mic_chunks"] = stats.get("mic_chunks", 0) + 1
            stats["mic_bytes"] = stats.get("mic_bytes", 0) + len(data)
            if stats["mic_chunks"] == 1 or stats["mic_chunks"] % 200 == 0:
                print(f"\n[dbg] mic -> agent chunks={stats['mic_chunks']} bytes={stats['mic_bytes']}", flush=True)
            try:
                await dg_ws.send(data)
            except Exception:
                break
    except Exception as e:
        print(f"\n[mic] sender ended: {e}", flush=True)


def start_player(out_rate: int):
    """Start streaming audio player reading raw s16le mono PCM from stdin."""
    cmds = [
        ["aplay", "-q", "-f", "S16_LE", "-r", str(out_rate), "-c", "1", "-t", "raw"],
        ["ffplay", "-nodisp", "-autoexit", "-loglevel", "error", "-f", "s16le", "-ar", str(out_rate), "-ac", "1", "-i", "pipe:0"],
        ["play", "-q", "-t", "raw", "-r", str(out_rate), "-e", "signed", "-b", "16", "-c", "1", "-"],
    ]
    for cmd in cmds:
        try:
            return subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except FileNotFoundError:
            continue
        except Exception:
            continue
    raise RuntimeError("No audio player found (need aplay, ffplay, or sox play)")


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


async def run(api_key: str, mic_device: str | None, mic_rate: int, out_rate: int, settings_file: str | None = None):
    settings = build_settings(mic_rate, out_rate, settings_file=settings_file)
    # if settings file specifies audio rates, honor them for capture/playback
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
    stats = {"mic_chunks": 0, "mic_bytes": 0, "agent_audio_bytes": 0, "events": 0}

    print(f"[dg] connecting to {DG_AGENT_URL} ...")
    connect_kw = dict(ping_interval=20, ping_timeout=20, close_timeout=5, max_size=16 * 1024 * 1024)
    try:
        params = inspect.signature(websockets.connect).parameters
        if "extra_headers" in params:
            ws_cm = websockets.connect(DG_AGENT_URL, extra_headers=headers, **connect_kw)
        elif "additional_headers" in params:
            ws_cm = websockets.connect(DG_AGENT_URL, additional_headers=headers, **connect_kw)
        else:
            ws_cm = websockets.connect(DG_AGENT_URL, extra_headers=headers, **connect_kw)
    except Exception:
        ws_cm = websockets.connect(DG_AGENT_URL, extra_headers=headers, **connect_kw)
    async with ws_cm as dg_ws:
        await dg_ws.send(json.dumps(settings))
        print("[dg] Settings sent. Waiting for agent...")
        print(f"[cfg] mic_rate={mic_rate}Hz out_rate={out_rate}Hz mic_device={mic_device or 'default'}")
        print("[info] Speak into your laptop mic. Ctrl+C to quit.\n")

        # Mic capture: raw s16le mono
        arecord_cmd = ["arecord", "-q", "-f", "S16_LE", "-r", str(mic_rate), "-c", "1", "-t", "raw"]
        if mic_device:
            arecord_cmd[1:1] = ["-D", mic_device]
        try:
            mic_proc = subprocess.Popen(arecord_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        except Exception as e:
            print(f"[mic] failed to start arecord: {e}")
            return

        # Streaming playback process
        try:
            player = start_player(out_rate)
        except Exception as e:
            print(f"[spk] failed to start audio player: {e}")
            mic_proc.terminate()
            return

        stop = asyncio.Event()
        # ~100ms chunks
        chunk_bytes = max(320, int(mic_rate * 2 * 0.1))
        mic_task = asyncio.create_task(mic_sender(mic_proc, dg_ws, chunk_bytes, stop, stats))
        ka_task = asyncio.create_task(keepalive(dg_ws, stop))
        loop = asyncio.get_event_loop()

        def write_audio(data: bytes):
            try:
                if player.stdin:
                    player.stdin.write(data)
                    player.stdin.flush()
            except Exception:
                pass

        try:
            async for msg in dg_ws:
                if isinstance(msg, (bytes, bytearray)):
                    b = bytes(msg)
                    stats["agent_audio_bytes"] += len(b)
                    # stream agent audio to speakers
                    await loop.run_in_executor(None, write_audio, b)
                    continue
                # JSON event
                stats["events"] += 1
                try:
                    evt = json.loads(msg)
                except Exception:
                    continue
                et = evt.get("type") or ""
                if et == "ConversationText":
                    role = evt.get("role", "?")
                    content = evt.get("content", "")
                    if content:
                        prefix = "You" if role == "user" else "Agent"
                        print(f"[{prefix}] {content}")
                elif et == "UserStartedSpeaking":
                    print("[event] UserStartedSpeaking (barge-in)")
                elif et == "AgentThinking":
                    print("[event] AgentThinking...")
                elif et == "AgentStartedSpeaking":
                    print("[event] AgentStartedSpeaking")
                elif et == "AgentAudioDone":
                    print("[event] AgentAudioDone")
                elif et == "Welcome":
                    print(f"[dg] Welcome: request_id={evt.get('request_id')}")
                elif et == "SettingsApplied":
                    print("[dg] SettingsApplied")
                elif et in ("Error", "Warning"):
                    print(f"[dg] {et}: {evt}")
                elif et == "FunctionCallRequest":
                    print(f"[dg] FunctionCallRequest: {evt}")
                else:
                    # log unknown but potentially useful events once in a while
                    if stats["events"] <= 10 or et in ("SpeechStarted", "UtteranceEnd", "EndOfThought"):
                        print(f"[dg] event: {et} { {k:v for k,v in evt.items() if k!='type'} }")
        except websockets.exceptions.ConnectionClosed as e:
            print(f"\n[dg] connection closed: code={getattr(e,'code',None)} reason={getattr(e,'reason',None)}")
        finally:
            stop.set()
            for task in (mic_task, ka_task):
                task.cancel()
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
            try:
                if player.stdin:
                    player.stdin.close()
            except Exception:
                pass
            try:
                player.wait(timeout=2)
            except Exception:
                try:
                    player.terminate()
                except Exception:
                    pass
            print(f"\n[stats] mic_chunks={stats['mic_chunks']} mic_bytes={stats['mic_bytes']} agent_audio_bytes={stats['agent_audio_bytes']} events={stats['events']}")


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mic", default=None, help="arecord device, e.g. hw:0,7 or hw:0,6")
    ap.add_argument("--mic-rate", type=int, default=16000, help="mic/input sample rate (default 16000; overridden by --settings-file audio.input.sample_rate)")
    ap.add_argument("--out-rate", type=int, default=24000, help="agent output sample rate (default 24000; overridden by --settings-file audio.output.sample_rate)")
    ap.add_argument("--settings-file", default=None, help="path to a Deepgram Voice Agent Settings JSON file (overrides default settings)")
    ap.add_argument("--env", default="/home/palontologist/Downloads/dev/omi-app/backend/.env.local-dev")
    args = ap.parse_args()

    load_env(args.env)
    api_key = os.getenv("DEEPGRAM_API_KEY", "")
    if not api_key:
        print("DEEPGRAM_API_KEY not found. Set it in env or backend/.env.local-dev")
        sys.exit(1)
    print("[ok] DEEPGRAM_API_KEY loaded")
    if args.settings_file:
        print(f"[cfg] using settings file: {args.settings_file}")

    try:
        await run(api_key, args.mic, args.mic_rate, args.out_rate, settings_file=args.settings_file)
    except KeyboardInterrupt:
        print("\n[bye]")


if __name__ == "__main__":
    asyncio.run(main())
