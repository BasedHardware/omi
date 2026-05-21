#!/usr/bin/env python3
"""Desktop-adjacent AssemblyAI E2E: uses Omi Dev auth + local Python backend.

By default this script exercises the same backend path as mobile offline sync
(POST /v2/sync-local-files -> STTWorkload.sync). With --background-chunk it
exercises desktop batch listen (POST /v2/desktop/background-transcribe ->
STTWorkload.background) using raw PCM bytes.

Usage:
  python3 scripts/desktop_assemblyai_e2e.py [--api http://127.0.0.1:8080]
  python3 scripts/desktop_assemblyai_e2e.py --background-chunk [--api http://127.0.0.1:8080]
"""
from __future__ import annotations

import argparse
import json
import struct
import subprocess
import sys
import time
import urllib.error
import urllib.request
import wave
from pathlib import Path

DEFAULTS_DOMAIN = "com.omi.desktop-dev"
SAMPLE_MP3_URL = "https://storage.googleapis.com/aai-docs-samples/nbc.mp3"


def read_desktop_auth_token() -> str:
    result = subprocess.run(
        ["defaults", "read", DEFAULTS_DOMAIN, "auth_idToken"],
        capture_output=True,
        text=True,
        check=False,
    )
    token = (result.stdout or "").strip()
    if result.returncode != 0 or not token:
        raise SystemExit(
            "No Omi Dev auth token found. Sign in via ./run.sh --yolo first, "
            f"then retry (defaults domain: {DEFAULTS_DOMAIN})."
        )
    return token


def mp3_to_pcm_bytes(mp3_path: Path, wav_path: Path, sample_rate: int = 16000) -> bytes:
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(mp3_path),
            "-ar",
            str(sample_rate),
            "-ac",
            "1",
            "-f",
            "wav",
            str(wav_path),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    with wave.open(str(wav_path), "rb") as wav_file:
        return wav_file.readframes(wav_file.getnframes())


def write_length_prefixed_pcm_bin(pcm: bytes, bin_path: Path, sample_rate: int = 16000) -> None:
    # Length-prefixed PCM frames (~100ms) for sync-local-files decoder
    frame_samples = sample_rate // 10
    frame_bytes = frame_samples * 2
    with bin_path.open("wb") as out:
        for offset in range(0, len(pcm), frame_bytes):
            chunk = pcm[offset : offset + frame_bytes]
            if not chunk:
                continue
            out.write(struct.pack("<I", len(chunk)))
            out.write(chunk)


def mp3_to_pcm_bin(mp3_path: Path, bin_path: Path, sample_rate: int = 16000) -> None:
    wav_path = bin_path.with_suffix(".wav")
    pcm = mp3_to_pcm_bytes(mp3_path, wav_path, sample_rate)
    write_length_prefixed_pcm_bin(pcm, bin_path, sample_rate)
    wav_path.unlink(missing_ok=True)


def ensure_sample_mp3(workdir: Path) -> Path:
    workdir.mkdir(parents=True, exist_ok=True)
    mp3_path = workdir / "sample.mp3"
    if not mp3_path.exists():
        print("Downloading sample audio...")
        urllib.request.urlretrieve(SAMPLE_MP3_URL, mp3_path)
    return mp3_path


def ensure_sample_bin(workdir: Path) -> Path:
    mp3_path = ensure_sample_mp3(workdir)
    bin_path = workdir / "desktop_e2e_sample.bin"
    if not bin_path.exists():
        print("Converting sample to sync .bin format...")
        mp3_to_pcm_bin(mp3_path, bin_path)
    return bin_path


def ensure_sample_pcm(workdir: Path) -> Path:
    mp3_path = ensure_sample_mp3(workdir)
    pcm_path = workdir / "desktop_e2e_sample.raw.pcm"
    if not pcm_path.exists():
        print("Converting sample to raw PCM format...")
        wav_path = workdir / "desktop_e2e_sample.raw.wav"
        pcm_path.write_bytes(mp3_to_pcm_bytes(mp3_path, wav_path))
        wav_path.unlink(missing_ok=True)
    return pcm_path


def json_request(
    url: str,
    token: str,
    *,
    method: str = "POST",
    payload: dict | None = None,
    timeout: int = 120,
) -> dict:
    data = json.dumps(payload or {}).encode()
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def multipart_upload(url: str, token: str, bin_path: Path, filename: str) -> dict:
    boundary = "----omiAssemblyAIe2e"
    body = bytearray()
    body.extend(f"--{boundary}\r\n".encode())
    body.extend(f'Content-Disposition: form-data; name="files"; filename="{filename}"\r\n'.encode())
    body.extend(b"Content-Type: application/octet-stream\r\n\r\n")
    body.extend(bin_path.read_bytes())
    body.extend(f"\r\n--{boundary}--\r\n".encode())

    req = urllib.request.Request(
        url,
        data=bytes(body),
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read().decode())


def background_chunk_upload(api_base: str, token: str, pcm_path: Path) -> dict:
    start_url = f"{api_base.rstrip('/')}/v2/desktop/background-conversation/start"
    started = json_request(start_url, token, payload={"language": "en", "source": "desktop"})
    conversation_id = started.get("conversation_id")
    if not conversation_id:
        raise RuntimeError(f"Unexpected background-conversation response: {started}")

    transcribe_url = (
        f"{api_base.rstrip('/')}/v2/desktop/background-transcribe"
        f"?conversation_id={conversation_id}&chunk_start_ms=0&sample_rate=16000&channels=1"
    )
    req = urllib.request.Request(
        transcribe_url,
        data=pcm_path.read_bytes(),
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/octet-stream",
        },
    )
    with urllib.request.urlopen(req, timeout=180) as resp:
        result = json.loads(resp.read().decode())
    result["_conversation_id"] = conversation_id
    return result


def poll_job(api_base: str, token: str, job_id: str, timeout_s: int = 900) -> dict:
    url = f"{api_base.rstrip('/')}/v2/sync-local-files/{job_id}"
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        req = urllib.request.Request(
            url,
            headers={"Authorization": f"Bearer {token}"},
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            job = json.loads(resp.read().decode())
        status = job.get("status")
        stage = job.get("stage")
        print(f"  job {job_id}: status={status} stage={stage}")
        if status in {"completed", "partial_failure", "failed"}:
            return job
        time.sleep(3)
    raise TimeoutError(f"Timed out waiting for job {job_id}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Desktop AssemblyAI E2E via sync-local-files")
    parser.add_argument("--api", default="http://127.0.0.1:8080", help="Local Python backend base URL")
    parser.add_argument("--workdir", default="/tmp/omi-assemblyai-e2e", help="Temp dir for sample audio")
    parser.add_argument(
        "--background-chunk",
        action="store_true",
        help="Exercise /v2/desktop/background-transcribe with raw PCM instead of sync-local-files",
    )
    args = parser.parse_args()

    token = read_desktop_auth_token()

    if args.background_chunk:
        pcm_path = ensure_sample_pcm(Path(args.workdir))
        print(f"Posting raw PCM chunk {pcm_path.name} to {args.api.rstrip('/')}/v2/desktop/background-transcribe ...")
        try:
            result = background_chunk_upload(args.api, token, pcm_path)
        except urllib.error.HTTPError as exc:
            body = exc.read().decode(errors="replace")
            print(f"Background chunk failed: HTTP {exc.code}\n{body}", file=sys.stderr)
            return 1
        except RuntimeError as exc:
            print(str(exc), file=sys.stderr)
            return 1

        print(json.dumps(result, indent=2))
        if result.get("provider") != "assemblyai":
            print(f"Expected provider=assemblyai, got {result.get('provider')!r}.", file=sys.stderr)
            return 1
        if not result.get("segments"):
            print("Expected non-empty segments from background chunk.", file=sys.stderr)
            return 1

        print("\nBackground chunk succeeded with provider=assemblyai.")
        print(f"Conversation: {result.get('_conversation_id')}")
        return 0

    bin_path = ensure_sample_bin(Path(args.workdir))
    ts = int(time.time())
    # Filename must include _pcm16_{sampleRate}_ so sync decode uses PCM path (not Opus).
    filename = f"audio_desktop_pcm16_16000_1_fs160_{ts}.bin"

    upload_url = f"{args.api.rstrip('/')}/v2/sync-local-files"
    print(f"Uploading {bin_path.name} to {upload_url} ...")
    try:
        queued = multipart_upload(upload_url, token, bin_path, filename)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode(errors="replace")
        print(f"Upload failed: HTTP {exc.code}\n{body}", file=sys.stderr)
        return 1

    job_id = queued.get("job_id")
    if not job_id:
        print(f"Unexpected response: {queued}", file=sys.stderr)
        return 1

    print(f"Queued job_id={job_id}; polling...")
    final = poll_job(args.api, token, job_id)
    print(json.dumps(final, indent=2))

    if final.get("status") not in {"completed", "partial_failure"}:
        print("Job did not complete successfully.", file=sys.stderr)
        return 1

    print("\nCheck backend logs for provider=assemblyai on workload=sync.")
    print("Firestore: transcription_provider_runs collection for your uid.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
