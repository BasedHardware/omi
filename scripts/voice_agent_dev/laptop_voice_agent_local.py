#!/usr/bin/env python3
"""Laptop mic -> Deepgram STT -> agent -> Deepgram TTS (local server) -> laptop speaker.
Turn-based: press Enter to record, agent replies out loud from laptop speakers.
"""
import argparse
import asyncio
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import httpx

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


def fetch_pcm16_8k(text: str) -> bytes:
    with httpx.Client(timeout=60.0) as c:
        r = c.post(
            TTS_URL,
            headers={"Authorization": f"Bearer {AUTH_TOKEN}", "Content-Type": "application/json"},
            json={"text": text, "output_format": "pcm_8000"},
        )
        r.raise_for_status()
        data = r.content
        if not data or data[:3] == b"ID3":
            raise RuntimeError(f"TTS bad response ({len(data)} bytes)")
        return data


def play_pcm_local(pcm: bytes):
    """Play raw s16le mono 8kHz on laptop speaker."""
    # Try aplay, then ffplay, then sox play
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
                return
            last_err = (p.stderr or b"").decode("utf-8", "replace").strip().splitlines()[-1] if p.stderr else f"rc={p.returncode}"
        except FileNotFoundError:
            continue
        except Exception as e:
            last_err = str(e)
    raise RuntimeError(f"no audio player worked: {last_err}")


def speak_local(text: str):
    text = (text or "").strip()
    if not text:
        return
    print(f"[agent] {text}")
    pcm = fetch_pcm16_8k(text)
    print(f"[tts] {len(pcm)} bytes pcm_8000, playing on laptop speaker...")
    play_pcm_local(pcm)


def record_wav(path: str, seconds: float, device: str | None, rate: int = 16000) -> bool:
    cmd = ["arecord", "-f", "S16_LE", "-r", str(rate), "-c", "1", "-t", "wav", "-d", str(max(1, int(seconds))), path]
    if device:
        cmd[1:1] = ["-D", device]
    print(f"[mic] recording {seconds}s... (speak now)")
    try:
        r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if r.returncode != 0:
            err = r.stderr.decode("utf-8", "replace").strip().splitlines()[-1] if r.stderr else "arecord failed"
            print(f"[mic] error: {err}")
            return False
        return os.path.exists(path) and os.path.getsize(path) > 44
    except Exception as e:
        print(f"[mic] error: {e}")
        return False


def transcribe_deepgram(wav_path: str) -> str:
    key = os.getenv("DEEPGRAM_API_KEY", "")
    if not key:
        print("[stt] DEEPGRAM_API_KEY missing")
        return ""
    params = {"model": "nova-2", "language": "en", "smart_format": "true", "punctuate": "true"}
    url = DG_LISTEN_URL + "?" + "&".join(f"{k}={v}" for k, v in params.items())
    headers = {"Authorization": f"Token {key}", "Content-Type": "audio/wav"}
    with open(wav_path, "rb") as f:
        audio = f.read()
    print(f"[stt] sending {len(audio)} bytes to Deepgram...")
    try:
        with httpx.Client(timeout=60.0) as c:
            r = c.post(url, headers=headers, content=audio)
            if r.status_code >= 400:
                print(f"[stt] Deepgram error {r.status_code}: {r.text[:200]}")
                return ""
            data = r.json()
        alts = (((data.get("results") or {}).get("channels") or [{}])[0].get("alternatives") or [{}])
        transcript = (alts[0].get("transcript") or "").strip() if alts else ""
        conf = alts[0].get("confidence") if alts else None
        print(f"[stt] transcript={transcript!r} confidence={conf}")
        return transcript
    except Exception as e:
        print(f"[stt] error: {e}")
        return ""


def agent_reply(user_text: str, history: list[dict]) -> str:
    user_text = user_text.strip()
    if not user_text:
        return "I didn't catch that. Could you say it again?"
    openai_key = os.getenv("OPENAI_API_KEY", "")
    if openai_key:
        try:
            messages = [
                {"role": "system", "content": "You are Omi, a helpful concise voice assistant. Reply in 1-3 short spoken sentences."},
                *history[-8:], {"role": "user", "content": user_text},
            ]
            with httpx.Client(timeout=30.0) as c:
                r = c.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={"Authorization": f"Bearer {openai_key}", "Content-Type": "application/json"},
                    json={"model": "gpt-4o-mini", "messages": messages, "max_tokens": 120, "temperature": 0.6},
                )
                r.raise_for_status()
                txt = (((r.json().get("choices") or [{}])[0].get("message") or {}).get("content") or "").strip()
                if txt:
                    return txt
                print(f"[agent] empty openai response: {r.text[:120]}")
        except Exception as e:
            print(f"[agent] openai fallback: {e}")
    low = user_text.lower()
    if "hello" in low or "hi" in low:
        return "Hi! I'm your voice agent. How can I help?"
    if "time" in low:
        import datetime
        return f"It's {datetime.datetime.now().strftime('%I:%M %p').lstrip('0')}."
    return f"You said: {user_text}."


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mic", default=None, help="arecord device, e.g. hw:0,7 (DMIC 16k) or hw:0,6")
    ap.add_argument("--seconds", type=float, default=5.0)
    ap.add_argument("--rate", type=int, default=16000)
    ap.add_argument("--env", default="/home/palontologist/Downloads/dev/omi-app/backend/.env.local-dev")
    args = ap.parse_args()

    load_env(args.env)
    print(f"[env] DEEPGRAM_API_KEY={'set' if os.getenv('DEEPGRAM_API_KEY') else 'MISSING'} OPENAI_API_KEY={'set' if os.getenv('OPENAI_API_KEY') else 'missing'}")
    # quick TTS health check
    try:
        with httpx.Client(timeout=5.0) as c:
            print(f"[health] tts server: {c.get('http://127.0.0.1:8000/health').status_code}")
    except Exception as e:
        print(f"[health] tts server unreachable: {e}")

    history = []
    print("\nLaptop voice agent ready (mic -> STT -> agent -> TTS -> laptop speaker).")
    while True:
        try:
            cmd = input("\n[you] Press Enter to speak, or type q to quit: ")
        except (EOFError, KeyboardInterrupt):
            break
        if (cmd or "").strip().lower() in ("q", "quit", "exit"):
            break
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tf:
            wav_path = tf.name
        try:
            ok = record_wav(wav_path, args.seconds, args.mic, args.rate)
            if not ok:
                print("[warn] mic capture failed; try --mic hw:0,7 or --mic hw:0,6")
                continue
            transcript = transcribe_deepgram(wav_path)
            if not transcript:
                print("[warn] no speech recognized; try speaking louder/closer or different --mic")
                continue
            history.append({"role": "user", "content": transcript})
            reply = agent_reply(transcript, history)
            history.append({"role": "assistant", "content": reply})
            try:
                speak_local(reply)
            except Exception as e:
                print(f"[tts/play] error: {e}")
        finally:
            try:
                os.unlink(wav_path)
            except Exception:
                pass
    print("[bye]")


if __name__ == "__main__":
    main()
