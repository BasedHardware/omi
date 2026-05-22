#!/usr/bin/env python3
"""Desktop-adjacent AssemblyAI E2E: uses Omi Dev auth + local Python backend.

By default this script exercises the same backend path as mobile offline sync
(POST /v2/sync-local-files -> STTWorkload.sync). With --background-chunk it
exercises desktop batch listen (POST /v2/desktop/background-transcribe ->
STTWorkload.background) using raw PCM bytes. With --background-batch it
simulates desktop background chunking without launching the desktop app.

Usage:
  cd backend && DYLD_FALLBACK_LIBRARY_PATH="/opt/homebrew/lib" ./run-local.sh
  # backend/.env:
  #   LOCAL_DEVELOPMENT=true
  #   ASSEMBLYAI_PRERECORDED_STT_ENABLED=true
  #   ASSEMBLYAI_PRERECORDED_STT_WORKLOADS=sync,background,postprocess
  #   ASSEMBLYAI_API_KEY=...
  python3 scripts/desktop_assemblyai_e2e.py [--api http://127.0.0.1:8080]
  python3 scripts/desktop_assemblyai_e2e.py --background-chunk [--api http://127.0.0.1:8080]
  python3 scripts/desktop_assemblyai_e2e.py --background-batch [--api http://127.0.0.1:8080] [--language en] [--token TOKEN]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import struct
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import wave
from pathlib import Path

DEFAULTS_DOMAIN = "com.omi.desktop-dev"
SAMPLE_MP3_URL = "https://storage.googleapis.com/aai-docs-samples/nbc.mp3"
SAMPLE_RATE = 16000
CHANNELS = 1
BYTES_PER_SAMPLE = 2
BACKGROUND_CHUNK_SECONDS = 15
BACKGROUND_OVERLAP_SECONDS = 1


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


def read_backend_admin_key() -> str | None:
    admin_key = os.getenv("ADMIN_KEY")
    if admin_key:
        return admin_key

    env_path = Path(__file__).resolve().parents[1] / "backend" / ".env"
    if not env_path.exists():
        return None

    for line in env_path.read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or not stripped.startswith("ADMIN_KEY="):
            continue
        return stripped.split("=", 1)[1].strip().strip('"').strip("'") or None
    return None


def resolve_auth_token(args: argparse.Namespace) -> str:
    if args.token:
        return args.token

    if args.background_chunk or args.background_batch:
        if args.use_desktop_auth:
            print("Using Omi Dev desktop auth; this will persist sample transcripts to the signed-in local account.")
            return read_desktop_auth_token()

        admin_key = read_backend_admin_key()
        if not admin_key:
            raise SystemExit(
                "Background e2e persists transcript segments. Set ADMIN_KEY in backend/.env, pass --token, "
                "or pass --use-desktop-auth to explicitly use the signed-in Omi Dev account."
            )
        print(f"Using isolated local e2e uid={args.e2e_uid}.")
        return f"{admin_key}{args.e2e_uid}"

    return read_desktop_auth_token()


def require_backend_reachable(api_base: str) -> None:
    url = f"{api_base.rstrip('/')}/docs"
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status >= 500:
                raise RuntimeError(f"Backend returned HTTP {resp.status}")
    except (urllib.error.URLError, TimeoutError, RuntimeError) as exc:
        raise SystemExit(
            f"Backend is not reachable at {api_base}. Start the local backend first, for example:\n"
            '  cd backend && DYLD_FALLBACK_LIBRARY_PATH="/opt/homebrew/lib" ./run-local.sh\n'
            "Required backend env includes LOCAL_DEVELOPMENT=true, "
            "ASSEMBLYAI_PRERECORDED_STT_ENABLED=true, and ASSEMBLYAI_API_KEY.\n"
            f"Reachability error: {exc}"
        )


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


def split_background_pcm_chunks(pcm: bytes) -> list[tuple[int, bytes]]:
    """Mirror desktop's 15s chunks with 1s retained overlap.

    Returns (chunk_start_ms, pcm_bytes). Hard cuts are intentional here; the
    Swift chunker may cut earlier at silence, but hard-cut parity is enough to
    prove multi-chunk backend persistence and offset handling.
    """
    bytes_per_second = SAMPLE_RATE * CHANNELS * BYTES_PER_SAMPLE
    chunk_bytes = BACKGROUND_CHUNK_SECONDS * bytes_per_second
    overlap_bytes = BACKGROUND_OVERLAP_SECONDS * bytes_per_second
    stride_bytes = chunk_bytes - overlap_bytes
    if stride_bytes <= 0:
        raise ValueError("background chunk stride must be positive")

    chunks: list[tuple[int, bytes]] = []
    offset = 0
    while offset < len(pcm):
        chunk = pcm[offset : offset + chunk_bytes]
        if not chunk:
            break
        start_ms = int(offset / bytes_per_second * 1000)
        chunks.append((start_ms, chunk))
        if offset + chunk_bytes >= len(pcm):
            break
        offset += stride_bytes
    return chunks


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


def get_json_request(url: str, token: str, *, timeout: int = 60) -> dict:
    req = urllib.request.Request(
        url,
        method="GET",
        headers={"Authorization": f"Bearer {token}"},
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


def background_transcribe_chunk(
    api_base: str,
    token: str,
    conversation_id: str,
    chunk_start_ms: int,
    chunk: bytes,
    language: str,
) -> dict:
    chunk_hash = hashlib.sha256(chunk).hexdigest()
    chunk_id = f"{conversation_id}-{chunk_start_ms}-{len(chunk)}-{chunk_hash[:16]}"
    transcribe_url = (
        f"{api_base.rstrip('/')}/v2/desktop/background-transcribe"
        f"?conversation_id={conversation_id}"
        f"&chunk_id={urllib.parse.quote(chunk_id)}"
        f"&chunk_start_ms={chunk_start_ms}"
        f"&sample_rate={SAMPLE_RATE}"
        f"&channels={CHANNELS}"
        f"&language={urllib.parse.quote(language)}"
    )
    req = urllib.request.Request(
        transcribe_url,
        data=chunk,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/octet-stream",
        },
    )
    with urllib.request.urlopen(req, timeout=180) as resp:
        return json.loads(resp.read().decode())


def background_batch_upload(api_base: str, token: str, pcm_path: Path, language: str) -> dict:
    require_backend_reachable(api_base)
    api_base = api_base.rstrip("/")

    start_url = f"{api_base}/v2/desktop/background-conversation/start"
    started = json_request(start_url, token, payload={"language": language, "source": "desktop"})
    conversation_id = started.get("conversation_id")
    if not conversation_id:
        raise RuntimeError(f"Unexpected background-conversation response: {started}")

    chunks = split_background_pcm_chunks(pcm_path.read_bytes())
    if len(chunks) < 2:
        raise RuntimeError(f"Expected sample to produce at least 2 chunks, got {len(chunks)}")

    total_segments = 0
    non_empty_chunks = 0
    previous_first_segment_start = None
    snippet_parts: list[str] = []
    chunk_summaries: list[dict] = []

    for index, (chunk_start_ms, chunk) in enumerate(chunks, start=1):
        duration_ms = int(len(chunk) / (SAMPLE_RATE * CHANNELS * BYTES_PER_SAMPLE) * 1000)
        print(
            f"Posting chunk {index}/{len(chunks)} "
            f"start_ms={chunk_start_ms} duration_ms={duration_ms} bytes={len(chunk)} ..."
        )
        result = background_transcribe_chunk(api_base, token, conversation_id, chunk_start_ms, chunk, language)
        provider = result.get("provider")
        if provider != "assemblyai":
            raise RuntimeError(f"Chunk {index} expected provider=assemblyai, got {provider!r}: {result}")

        segments = result.get("segments") or []
        for segment in segments:
            if segment.get("start") is None or segment.get("end") is None:
                raise RuntimeError(f"Chunk {index} returned segment without start/end: {segment}")
            if segment["start"] + 0.001 < chunk_start_ms / 1000.0:
                raise RuntimeError(
                    f"Chunk {index} segment start {segment['start']} regressed before offset {chunk_start_ms / 1000.0}"
                )

        first_segment_start = next((segment["start"] for segment in segments if segment.get("start") is not None), None)
        if first_segment_start is not None:
            if previous_first_segment_start is not None and first_segment_start + 0.001 < previous_first_segment_start:
                raise RuntimeError(
                    f"Chunk {index} first segment start regressed: "
                    f"{first_segment_start} < {previous_first_segment_start}"
                )
            previous_first_segment_start = first_segment_start

        if segments:
            non_empty_chunks += 1
            snippet_parts.extend(segment.get("text", "") for segment in segments[:2])
        total_segments += len(segments)
        chunk_summaries.append(
            {
                "index": index,
                "chunk_start_ms": chunk_start_ms,
                "chunk_duration_ms": result.get("chunk_duration_ms"),
                "segments": len(segments),
                "run_id": result.get("run_id"),
            }
        )

    if non_empty_chunks == 0 or total_segments == 0:
        raise RuntimeError("Expected non-empty AssemblyAI segments from at least one chunk.")

    before_finalize = get_json_request(f"{api_base}/v1/conversations/{conversation_id}", token)
    persisted_before = before_finalize.get("transcript_segments") or []
    if not persisted_before:
        raise RuntimeError(f"Expected persisted transcript_segments before finalize: {before_finalize}")

    finalize_status = None
    finalize_body: dict | str | None = None
    try:
        finalize_body = json_request(f"{api_base}/v1/conversations", token, payload={}, timeout=240)
        finalize_status = 200
    except urllib.error.HTTPError as exc:
        finalize_status = exc.code
        body = exc.read().decode(errors="replace")
        try:
            finalize_body = json.loads(body)
        except json.JSONDecodeError:
            finalize_body = body
        if exc.code != 404:
            raise RuntimeError(f"Finalize failed: HTTP {exc.code}\n{body}") from exc

    after_finalize = get_json_request(f"{api_base}/v1/conversations/{conversation_id}", token)
    persisted_after = after_finalize.get("transcript_segments") or []
    if not persisted_after:
        raise RuntimeError(f"Expected transcript_segments on conversation after finalize: {after_finalize}")

    return {
        "conversation_id": conversation_id,
        "chunks": chunk_summaries,
        "total_segments_returned": total_segments,
        "persisted_segments_before_finalize": len(persisted_before),
        "persisted_segments_after_finalize": len(persisted_after),
        "finalize_status": finalize_status,
        "finalize_body": finalize_body,
        "snippet": " ".join(part.strip() for part in snippet_parts if part.strip())[:300],
    }


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
    parser.add_argument("--language", default="en", help="Language passed to background transcription")
    parser.add_argument(
        "--token",
        help=(
            "Firebase ID token or ADMIN_KEY-prefixed uid. Background modes default to an isolated local e2e uid; "
            "sync mode defaults to Omi Dev auth_idToken from macOS defaults."
        ),
    )
    parser.add_argument(
        "--e2e-uid",
        default="desktop-assemblyai-e2e",
        help="Isolated local uid used by background modes when ADMIN_KEY is available and --token is omitted.",
    )
    parser.add_argument(
        "--use-desktop-auth",
        action="store_true",
        help="For background modes, explicitly persist sample transcripts to the signed-in Omi Dev account.",
    )
    parser.add_argument(
        "--background-chunk",
        action="store_true",
        help="Exercise /v2/desktop/background-transcribe with raw PCM instead of sync-local-files",
    )
    parser.add_argument(
        "--background-batch",
        action="store_true",
        help="Exercise desktop background batch lifecycle with 15s/1s-overlap raw PCM chunks",
    )
    args = parser.parse_args()

    if args.background_chunk and args.background_batch:
        print("Choose only one of --background-chunk or --background-batch.", file=sys.stderr)
        return 2

    token = resolve_auth_token(args)

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

    if args.background_batch:
        pcm_path = ensure_sample_pcm(Path(args.workdir))
        print(f"Posting simulated background batch from {pcm_path.name} to {args.api.rstrip('/')} ...")
        try:
            summary = background_batch_upload(args.api, token, pcm_path, args.language)
        except urllib.error.HTTPError as exc:
            body = exc.read().decode(errors="replace")
            print(f"Background batch failed: HTTP {exc.code}\n{body}", file=sys.stderr)
            return 1
        except (RuntimeError, SystemExit) as exc:
            print(str(exc), file=sys.stderr)
            return 1

        print("\nBackground batch succeeded with provider=assemblyai.")
        print(f"Conversation: {summary['conversation_id']}")
        print(f"Chunks uploaded: {len(summary['chunks'])}")
        print(f"Segments returned by chunks: {summary['total_segments_returned']}")
        print(f"Segments persisted before finalize: {summary['persisted_segments_before_finalize']}")
        print(f"Segments persisted after finalize: {summary['persisted_segments_after_finalize']}")
        print(f"Finalize status: HTTP {summary['finalize_status']}")
        if summary["snippet"]:
            print(f"Transcript snippet: {summary['snippet']}")
        print("\nChunk summary:")
        print(json.dumps(summary["chunks"], indent=2))
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
