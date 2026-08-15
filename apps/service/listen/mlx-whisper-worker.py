#!/usr/bin/env python3
"""Long-lived on-device Whisper worker.

JSON-lines protocol on stdin/stdout. Exits when stdin hits EOF or a shutdown
op arrives, so a dead parent cannot leave an orphan. Stderr is for diagnostics
only; stdout is the protocol and must stay parseable.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
from typing import Any

WHISPER_RATE = 16_000


def log(message: str) -> None:
    sys.stderr.write(f"mlx-whisper-worker: {message}\n")
    sys.stderr.flush()


def write(payload: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(payload) + "\n")
    sys.stdout.flush()


def resample(audio: Any, source_rate: int, target_rate: int) -> Any:
    import numpy as np

    if source_rate == target_rate or audio.size == 0:
        return audio
    target_length = int(round(audio.size * target_rate / source_rate))
    if target_length <= 1:
        return audio.astype(np.float32)
    old_x = np.linspace(0.0, 1.0, num=audio.size, endpoint=False)
    new_x = np.linspace(0.0, 1.0, num=target_length, endpoint=False)
    return np.interp(new_x, old_x, audio).astype(np.float32)


def pcm16_to_float(pcm_b64: str, sample_rate: int, channels: int) -> Any:
    import numpy as np

    raw = base64.b64decode(pcm_b64)
    samples = np.frombuffer(raw, dtype="<i2")
    if samples.size == 0:
        return np.zeros(0, dtype=np.float32)
    if channels < 1:
        raise ValueError("channels must be >= 1")
    if channels > 1:
        usable = samples.size - (samples.size % channels)
        samples = samples[:usable].reshape(-1, channels).mean(axis=1)
    audio = samples.astype(np.float32) / 32768.0
    return resample(audio, sample_rate, WHISPER_RATE)


def load_model(model: str) -> None:
    from mlx_whisper.load_models import load_model as load_whisper_model

    load_whisper_model(model)


def transcribe_window(model: str, audio: Any) -> str:
    import mlx_whisper

    result = mlx_whisper.transcribe(
        audio,
        path_or_hf_repo=model,
        verbose=False,
        temperature=0.0,
        condition_on_previous_text=False,
    )
    text = result.get("text") if isinstance(result, dict) else ""
    return text.strip() if isinstance(text, str) else ""


def main() -> int:
    parser = argparse.ArgumentParser(prog="mlx-whisper-worker")
    parser.add_argument("--model", required=True)
    args = parser.parse_args()

    try:
        load_model(args.model)
    except Exception as error:
        log(f"model load failed: {error}")
        return 1

    write({"op": "ready", "pid": os.getpid()})

    for raw in sys.stdin:
        line = raw.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            write({"op": "error", "id": "", "message": "invalid json"})
            continue
        op = message.get("op")
        request_id = message.get("id", "")
        if op == "shutdown":
            break
        if op != "transcribe":
            write({"op": "error", "id": request_id, "message": "unsupported op"})
            continue
        try:
            sample_rate = int(message.get("sample_rate", WHISPER_RATE))
            channels = int(message.get("channels", 1))
            audio = pcm16_to_float(message.get("pcm_b64", ""), sample_rate, channels)
            text = "" if audio.size == 0 else transcribe_window(args.model, audio)
            write({"op": "result", "id": request_id, "text": text})
        except Exception as error:
            write({"op": "error", "id": request_id, "message": "transcribe failed"})
            log(f"transcribe failed: {error}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
