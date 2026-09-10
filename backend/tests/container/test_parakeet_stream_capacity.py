"""Realtime Parakeet TDT v3 streaming ASR capacity qualification.

This is an end-to-end capacity test for ``/v3/stream``.  It sends a public
LibriSpeech test-clean-derived fixture at wall-clock pace, rather than
replaying bytes as fast as the client can write them.  Each requested
level is run concurrently and then drained with the protocol's ``finalize``
message.  The target level is also sustained for three minutes by repeating
that same speech fixture, so the result measures a live TDT streaming ASR
workload rather than a short burst.

The fixture is English speech audio, so this test treats a non-empty response
as an integration/completeness signal.  It does not claim WER, multilingual
accuracy, or ASR quality; those must be established by separately paired
transcription and diarization checks.

Environment:
  PARAKEET_URL: HTTP base URL (default ``http://127.0.0.1:8080``)
  PARAKEET_STREAM_AUDIO: local WAV path (otherwise downloaded from the public
      Omi test fixture URL)
  PARAKEET_STREAM_AUDIO_URL: override for the public fixture URL
  PARAKEET_STREAM_LEVELS: comma-separated accepted levels (default 1,5,10,20,25)
  PARAKEET_STREAM_EXPECTED_CAPACITY: hard per-pod capacity (default 25)
  PARAKEET_STREAM_RESULTS: JSON output path (default /tmp/parakeet-stream-capacity.json)
  PARAKEET_TEST_IMAGE_REF: immutable image reference recorded in the artifact
  PARAKEET_TEST_SOURCE_SHA: source commit recorded when the test builds source
  PARAKEET_GPU_TYPE: GPU type recorded in the artifact (default nvidia-l4)
  PARAKEET_TARGET_STREAMS: target operating concurrency (default 20)
  PARAKEET_STREAM_CHUNK_MS: pacing chunk size (default 100)
  PARAKEET_STREAM_TIMEOUT_S: per-session timeout (default 180)
  PARAKEET_STREAM_DOWNLOAD_TIMEOUT_S: fixture download timeout (default 60)
  PARAKEET_STREAM_SUSTAIN_S: sustained target duration (default 180)
  PARAKEET_STREAM_MAX_TEXT_LATENCY_S: p95 text latency gate (default 4 seconds)

The stream health response must identify the exact TDT v3 model, NeMo backend,
multilingual decoder family, and pinned Hugging Face revision before any audio
is sent.  This English fixture cannot qualify multilingual accuracy.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
import os
import subprocess
import threading
import time
import urllib.request
import wave
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple
from urllib.parse import urlparse

import websockets
from websockets.exceptions import ConnectionClosed, InvalidStatusCode

PARAKEET_URL = os.getenv("PARAKEET_URL", "http://127.0.0.1:8080").rstrip("/")
DEFAULT_AUDIO_URL = "https://storage.googleapis.com/omi-pr-assets/modulate-repro/test_audio.wav"
DEFAULT_AUDIO_WAV_SHA256 = "8d977c5dcf85ec25c89d8ff81225a9c7b05d14fcea9018a26f56224af5936489"
AUDIO_URL = os.getenv("PARAKEET_STREAM_AUDIO_URL", DEFAULT_AUDIO_URL)
# The default fixture is the public-domain LibriSpeech test-clean-derived
# artifact documented in backend/scripts/stt/modulate_repro/README.md.  An
# override is allowed for a separately reviewed public fixture and is always
# downloaded over HTTPS and validated as speech-level PCM16.
AUDIO_PATH = Path(os.getenv("PARAKEET_STREAM_AUDIO", "/tmp/parakeet-stream-test-audio.wav"))
RESULTS_PATH = Path(os.getenv("PARAKEET_STREAM_RESULTS", "/tmp/parakeet-stream-capacity.json"))
IMAGE_REF = os.getenv("PARAKEET_TEST_IMAGE_REF", "")
SOURCE_SHA = os.getenv("PARAKEET_TEST_SOURCE_SHA", "") or None
GPU_TYPE = os.getenv("PARAKEET_GPU_TYPE", "nvidia-l4")
TARGET_STREAMS = int(os.getenv("PARAKEET_TARGET_STREAMS", "20"))
LEVELS = tuple(int(value.strip()) for value in os.getenv("PARAKEET_STREAM_LEVELS", "1,5,10,20,25").split(","))
EXPECTED_CAPACITY = int(os.getenv("PARAKEET_STREAM_EXPECTED_CAPACITY", "25"))
CHUNK_MS = int(os.getenv("PARAKEET_STREAM_CHUNK_MS", "100"))
SESSION_TIMEOUT_S = float(os.getenv("PARAKEET_STREAM_TIMEOUT_S", "180"))
DOWNLOAD_TIMEOUT_S = float(os.getenv("PARAKEET_STREAM_DOWNLOAD_TIMEOUT_S", "60"))
SUSTAIN_S = float(os.getenv("PARAKEET_STREAM_SUSTAIN_S", "180"))
# The TDT stream uses 2s chunks with 2s right context.  A 2s end-to-text p95
# gate leaves no scheduling/inference margin over that context floor, so it
# would reject healthy streaming output for a structural reason.  Keep the
# bound explicit and record the raw latency distribution for product review.
MAX_TEXT_LATENCY_S = float(os.getenv("PARAKEET_STREAM_MAX_TEXT_LATENCY_S", "4.0"))
LATENCY_GATE_MIN_STREAMS = int(os.getenv("PARAKEET_STREAM_LATENCY_GATE_MIN_STREAMS", "20"))
EXPECTED_STREAM_MODEL = "nvidia/parakeet-tdt-0.6b-v3"
EXPECTED_STREAM_BACKEND = "nemo"
EXPECTED_STREAM_DECODER_FAMILY = "tdt"
EXPECTED_STREAM_LANGUAGE_SUPPORT = "multilingual"
EXPECTED_STREAM_MODEL_REVISION = "541d1f99c6b0c3cd0b11a95167540bb8edefd82b"
SAMPLE_RATE = 16000
BYTES_PER_SAMPLE = 2
SILENCE_FRAME_MS = 10
MAX_PAUSE_MS = 200
SPEECH_RMS_THRESHOLD = 32.0
TEXT_SENTINELS = (
    "he hoped there would be stew",
    "stuff it into you",
    "after early nightfall",
    "hello bertie",
)


def _expected_model_identity() -> Dict[str, str]:
    return {
        "stream_model": EXPECTED_STREAM_MODEL,
        "backend": EXPECTED_STREAM_BACKEND,
        "decoder_family": EXPECTED_STREAM_DECODER_FAMILY,
        "language_support": EXPECTED_STREAM_LANGUAGE_SUPPORT,
        "model_revision": EXPECTED_STREAM_MODEL_REVISION,
    }


def _model_identity_matches(identity: Any) -> bool:
    return (
        isinstance(identity, dict)
        and identity.get("stream_model") == EXPECTED_STREAM_MODEL
        and identity.get("backend") == EXPECTED_STREAM_BACKEND
        and identity.get("decoder_family") == EXPECTED_STREAM_DECODER_FAMILY
        and identity.get("language_support") == EXPECTED_STREAM_LANGUAGE_SUPPORT
        and identity.get("model_revision") == EXPECTED_STREAM_MODEL_REVISION
    )


def _read_runtime_health() -> Dict[str, Any]:
    """Read the bounded stream readiness and model identity contract."""

    with urllib.request.urlopen(f"{PARAKEET_URL}/health", timeout=30) as response:
        payload = json.load(response)
    if not isinstance(payload, dict):
        raise ValueError("Parakeet /health response must be a JSON object")

    identity = payload.get("model_identity")
    components = payload.get("components")
    health = {
        "status": payload.get("status"),
        "ready": payload.get("ready"),
        "mode": payload.get("mode"),
        "components": components,
        "model_identity": identity,
        "admission": payload.get("admission"),
    }
    if payload.get("ready") is not True or payload.get("mode") != "stream":
        raise ValueError(f"stream service is not ready in stream mode: {health}")
    if not isinstance(identity, dict):
        raise ValueError("stream /health omitted model_identity")
    if not _model_identity_matches(identity):
        raise ValueError(
            "stream /health model identity mismatch: " f"expected={_expected_model_identity()} actual={identity}"
        )
    if not isinstance(components, dict):
        raise ValueError("stream /health omitted component readiness")
    required_components = ("rnnt", "vad", "diarizer")
    missing_components = [name for name in required_components if components.get(name) is not True]
    if missing_components:
        raise ValueError(f"stream /health components are not ready: {missing_components}")
    return health


def _download_fixture() -> Path:
    """Download the named public fixture once, using an atomic replacement."""

    parsed = urlparse(AUDIO_URL)
    if parsed.scheme != "https":
        raise ValueError("PARAKEET_STREAM_AUDIO_URL must use https")
    if AUDIO_PATH.exists():
        return AUDIO_PATH
    AUDIO_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = AUDIO_PATH.with_suffix(AUDIO_PATH.suffix + ".download")
    try:
        with urllib.request.urlopen(AUDIO_URL, timeout=DOWNLOAD_TIMEOUT_S) as response:
            temporary_path.write_bytes(response.read())
        temporary_path.replace(AUDIO_PATH)
    finally:
        temporary_path.unlink(missing_ok=True)
    return AUDIO_PATH


def _load_pcm(path: Path) -> Tuple[bytes, float, str, str]:
    """Validate a mono PCM16 16 kHz WAV and return PCM, duration, and digests."""

    wav_sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
    if AUDIO_URL == DEFAULT_AUDIO_URL and wav_sha256 != DEFAULT_AUDIO_WAV_SHA256:
        raise ValueError(
            "default stream fixture changed; expected the pinned public LibriSpeech-derived WAV "
            f"{DEFAULT_AUDIO_WAV_SHA256}, got {wav_sha256}"
        )

    with wave.open(str(path), "rb") as stream:
        channels = stream.getnchannels()
        sample_width = stream.getsampwidth()
        sample_rate = stream.getframerate()
        frame_count = stream.getnframes()
        pcm = stream.readframes(frame_count)

    if channels != 1 or sample_width != BYTES_PER_SAMPLE or sample_rate != SAMPLE_RATE:
        raise ValueError(
            f"stream fixture must be mono PCM16 {SAMPLE_RATE}Hz; "
            f"got channels={channels}, sample_width={sample_width}, sample_rate={sample_rate}"
        )
    if frame_count < SAMPLE_RATE or not pcm:
        raise ValueError("stream fixture must contain at least one second of audio")
    # A zero/silence fixture can prove transport but cannot qualify ASR output.
    peak = max(abs(sample) for sample in memoryview(pcm).cast("h"))
    if peak < 256:
        raise ValueError("stream fixture contains no speech-level signal")
    return pcm, frame_count / SAMPLE_RATE, hashlib.sha256(pcm).hexdigest(), wav_sha256


def _trim_long_silence(pcm: bytes, duration_s: float) -> Tuple[bytes, Dict[str, Any]]:
    """Bound fixture pauses so sustained streams carry speech-level workload.

    The source fixture intentionally has roughly five-second pauses between
    utterances.  Keep at most 200 ms of every silence run, including at the
    fixture boundaries, and record the deterministic recipe and resulting
    digest so the workload remains auditable.
    """

    samples = memoryview(pcm).cast("h")
    frame_samples = SAMPLE_RATE * SILENCE_FRAME_MS // 1000
    max_pause_frames = MAX_PAUSE_MS // SILENCE_FRAME_MS
    frames: List[Tuple[bytes, bool]] = []
    active_samples = 0
    for offset in range(0, len(samples), frame_samples):
        frame = samples[offset : offset + frame_samples]
        if not frame:
            continue
        rms = math.sqrt(sum(sample * sample for sample in frame) / len(frame))
        active = rms >= SPEECH_RMS_THRESHOLD
        if active:
            active_samples += len(frame)
        frames.append(
            (
                pcm[offset * BYTES_PER_SAMPLE : (offset + len(frame)) * BYTES_PER_SAMPLE],
                active,
            )
        )

    kept: List[bytes] = []
    index = 0
    while index < len(frames):
        active = frames[index][1]
        end = index + 1
        while end < len(frames) and frames[end][1] == active:
            end += 1
        run = frames[index:end]
        if active or len(run) <= max_pause_frames:
            kept.extend(frame for frame, _ in run)
        else:
            kept.extend(frame for frame, _ in run[:max_pause_frames])
        index = end

    workload_pcm = b"".join(kept)
    workload_duration_s = len(workload_pcm) / (SAMPLE_RATE * BYTES_PER_SAMPLE)
    metadata = {
        "recipe": "10ms RMS frames; RMS >= 32 is speech; cap each silence run at 200ms",
        "frame_ms": SILENCE_FRAME_MS,
        "max_pause_ms": MAX_PAUSE_MS,
        "speech_rms_threshold": SPEECH_RMS_THRESHOLD,
        "source_duration_s": duration_s,
        "workload_duration_s": workload_duration_s,
        "active_speech_duration_s": active_samples / SAMPLE_RATE,
        "speech_duty_cycle": round(active_samples / len(samples), 6) if samples else 0.0,
        "workload_speech_duty_cycle": (
            round(active_samples / (len(workload_pcm) // BYTES_PER_SAMPLE), 6) if workload_pcm else 0.0
        ),
        "source_pcm_sha256": hashlib.sha256(pcm).hexdigest(),
        "workload_pcm_sha256": hashlib.sha256(workload_pcm).hexdigest(),
    }
    if not workload_pcm or workload_duration_s <= 0:
        raise ValueError("silence trimming produced an empty workload")
    return workload_pcm, metadata


class _GPUMonitor:
    """Best-effort whole-GPU memory samples from the task-owned GPU."""

    def __init__(self) -> None:
        self.samples: List[Dict[str, float]] = []
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        self._stop.clear()
        self._thread = threading.Thread(target=self._poll, name="parakeet-gpu-monitor", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)

    def _poll(self) -> None:
        while not self._stop.is_set():
            try:
                output = subprocess.check_output(
                    [
                        "nvidia-smi",
                        "--query-gpu=memory.used,memory.total",
                        "--format=csv,noheader,nounits",
                    ],
                    stderr=subprocess.DEVNULL,
                    timeout=5,
                    text=True,
                ).strip()
                first_row = output.splitlines()[0]
                used, total = (float(value.strip()) for value in first_row.split(",", 1))
                if total > 0:
                    self.samples.append(
                        {
                            "time_s": time.monotonic(),
                            "used_mib": used,
                            "total_mib": total,
                            "used_pct": used / total * 100,
                        }
                    )
            except (OSError, ValueError, subprocess.SubprocessError, IndexError):
                pass
            self._stop.wait(1.0)

    def summary(self) -> Dict[str, Any]:
        if not self.samples:
            return {"available": False, "sample_count": 0}
        return {
            "available": True,
            "sample_count": len(self.samples),
            "peak_used_mib": max(sample["used_mib"] for sample in self.samples),
            "peak_used_pct": max(sample["used_pct"] for sample in self.samples),
            "total_mib": self.samples[0]["total_mib"],
        }


def _percentile(values: Sequence[float], percentile: float) -> Optional[float]:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, math.ceil(len(ordered) * percentile) - 1)
    return round(ordered[index], 4)


def _valid_speaker_fields(segments: Sequence[Dict[str, Any]]) -> bool:
    """Require the stream contract's diarizer label on every emitted segment."""

    return bool(segments) and all(
        isinstance(segment.get("speaker"), str)
        and str(segment["speaker"]).startswith("SPEAKER_")
        and str(segment["speaker"])[len("SPEAKER_") :].isdigit()
        for segment in segments
    )


def _normalized_text(value: str) -> str:
    return " ".join("".join(character.lower() if character.isalnum() else " " for character in value).split())


def _ws_url() -> str:
    parsed = urlparse(PARAKEET_URL)
    scheme = "wss" if parsed.scheme == "https" else "ws"
    return f"{scheme}://{parsed.netloc}/v3/stream?sample_rate={SAMPLE_RATE}"


def _new_stream_result(stream_id: int) -> Dict[str, Any]:
    return {
        "stream_id": stream_id,
        "accepted": False,
        "ready": False,
        "closed_normally": False,
        "sent_audio_s": 0.0,
        "segments": [],
        "nonempty_text": False,
        "speaker_fields_valid": False,
        "timestamp_valid": True,
        "text_latency_timestamps_valid": True,
        "text_sentinels": {sentinel: False for sentinel in TEXT_SENTINELS},
        "text_sentinels_complete": False,
        "first_text_latency_s": None,
        "text_latencies_s": [],
        "error": None,
        "close_code": None,
        "close_reason": None,
        "finalize_sent": False,
    }


async def _run_stream_inner(stream_id: int, pcm: bytes, duration_s: float) -> Dict[str, Any]:
    """Run one real-time stream and retain protocol/latency evidence."""

    result = _new_stream_result(stream_id)
    ws: Any = None
    receive_task: Optional[asyncio.Task[None]] = None
    audio_start = 0.0
    transcript_parts: List[str] = []

    async def receive_segments() -> None:
        try:
            while True:
                raw = await ws.recv()
                arrival_s = time.monotonic() - audio_start
                if not isinstance(raw, str):
                    continue
                try:
                    message = json.loads(raw)
                except json.JSONDecodeError:
                    result["error"] = "invalid JSON frame"
                    continue
                if not isinstance(message, dict) or not message.get("text"):
                    continue
                text = str(message["text"]).strip()
                if not text:
                    continue
                transcript_parts.append(text)
                segment = {
                    "text_length": len(text),
                    "start": message.get("start"),
                    "end": message.get("end"),
                    "speaker": message.get("speaker"),
                    "arrival_s": round(arrival_s, 4),
                }
                result["segments"].append(segment)
                end_s = message.get("end")
                start_s = message.get("start")
                if (
                    not isinstance(start_s, (int, float))
                    or isinstance(start_s, bool)
                    or not isinstance(end_s, (int, float))
                    or isinstance(end_s, bool)
                    or not math.isfinite(float(start_s))
                    or not math.isfinite(float(end_s))
                ):
                    result["timestamp_valid"] = False
                    continue
                if float(start_s) < 0 or float(end_s) < float(start_s) or float(end_s) > duration_s + 5:
                    result["timestamp_valid"] = False
                latency = arrival_s - float(end_s)
                if latency < 0:
                    result["text_latency_timestamps_valid"] = False
                result["text_latencies_s"].append(round(latency, 4))
        except ConnectionClosed as error:
            result["close_code"] = error.code
            result["close_reason"] = error.reason

    try:
        try:
            ws = await websockets.connect(
                _ws_url(),
                open_timeout=min(30.0, SESSION_TIMEOUT_S),
                close_timeout=10.0,
                max_size=10 * 1024 * 1024,
            )
            ready = await asyncio.wait_for(ws.recv(), timeout=30.0)
            if not isinstance(ready, str) or json.loads(ready).get("type") != "ready":
                raise RuntimeError("Parakeet did not confirm stream admission")
            result["accepted"] = True
            result["ready"] = True
            audio_start = time.monotonic()
            receive_task = asyncio.create_task(receive_segments())
            chunk_bytes = max(2, int(SAMPLE_RATE * BYTES_PER_SAMPLE * CHUNK_MS / 1000))
            for offset in range(0, len(pcm), chunk_bytes):
                target = audio_start + offset / (SAMPLE_RATE * BYTES_PER_SAMPLE)
                wait_s = target - time.monotonic()
                if wait_s > 0:
                    await asyncio.sleep(wait_s)
                await ws.send(pcm[offset : offset + chunk_bytes])
            result["sent_audio_s"] = duration_s
            await ws.send("finalize")
            result["finalize_sent"] = True
            await asyncio.wait_for(receive_task, timeout=max(30.0, duration_s + 30.0))
            result["closed_normally"] = result["close_code"] in (None, 1000, 1001)
            if not result["closed_normally"]:
                result["error"] = f"stream closed before final drain: {result['close_reason']}"
        except (ConnectionClosed, InvalidStatusCode) as error:
            result["close_code"] = getattr(error, "code", None)
            result["close_reason"] = getattr(error, "reason", None) or str(error)
            if result["ready"]:
                result["error"] = f"stream closed before final drain: {result['close_reason']}"
        except Exception as error:  # pragma: no cover - exercised by live service
            result["error"] = f"{type(error).__name__}: {error}"
    finally:
        if receive_task is not None and not receive_task.done():
            receive_task.cancel()
            await asyncio.gather(receive_task, return_exceptions=True)
        if ws is not None:
            await ws.close()

    result["nonempty_text"] = bool(result["segments"])
    result["speaker_fields_valid"] = _valid_speaker_fields(result["segments"])
    if result["text_latencies_s"]:
        result["first_text_latency_s"] = result["text_latencies_s"][0]
    normalized_transcript = _normalized_text(" ".join(transcript_parts))
    result["text_sentinels"] = {
        sentinel: _normalized_text(sentinel) in normalized_transcript for sentinel in TEXT_SENTINELS
    }
    result["text_sentinels_complete"] = all(result["text_sentinels"].values())
    # Avoid carrying raw fixture transcript text into the artifact.
    result["segment_count"] = len(result["segments"])
    return result


async def _run_stream(stream_id: int, pcm: bytes, duration_s: float) -> Dict[str, Any]:
    """Run a stream under one deadline covering connect, send, and final drain."""

    deadline_s = max(SESSION_TIMEOUT_S, duration_s + 30.0)
    try:
        return await asyncio.wait_for(_run_stream_inner(stream_id, pcm, duration_s), timeout=deadline_s)
    except asyncio.TimeoutError:
        result = _new_stream_result(stream_id)
        result["error"] = f"stream exceeded {deadline_s:.1f}s end-to-end deadline"
        return result


async def _run_level(level: int, pcm: bytes, duration_s: float) -> Dict[str, Any]:
    monitor = _GPUMonitor()
    monitor.start()
    started = time.monotonic()
    try:
        streams = await asyncio.gather(*(_run_stream(i, pcm, duration_s) for i in range(level)))
    finally:
        monitor.stop()

    accepted = [stream for stream in streams if stream["accepted"]]
    completed = [stream for stream in accepted if stream["closed_normally"]]
    nonempty = [stream for stream in accepted if stream["nonempty_text"]]
    speaker_valid = [stream for stream in accepted if stream["speaker_fields_valid"]]
    latencies = [latency for stream in accepted for latency in stream["text_latencies_s"]]
    text_latency_p95 = _percentile(latencies, 0.95)
    return {
        "requested_streams": level,
        "audio_duration_s": duration_s,
        "accepted_streams": len(accepted),
        "rejected_streams": level - len(accepted),
        "error_streams": sum(1 for stream in streams if stream["error"]),
        "ready_rate": sum(1 for stream in accepted if stream["ready"]) / len(accepted) if accepted else 0.0,
        "final_drain_complete": len(completed) == len(accepted),
        "nonempty_rate": len(nonempty) / len(accepted) if accepted else 0.0,
        "speaker_fields_rate": len(speaker_valid) / len(accepted) if accepted else 0.0,
        "timestamp_valid_rate": (
            sum(1 for stream in accepted if stream["timestamp_valid"]) / len(accepted) if accepted else 0.0
        ),
        "text_latency_timestamps_valid_rate": (
            sum(1 for stream in accepted if stream["text_latency_timestamps_valid"]) / len(accepted)
            if accepted
            else 0.0
        ),
        "text_sentinel_rate": (
            sum(1 for stream in accepted if stream["text_sentinels_complete"]) / len(accepted) if accepted else 0.0
        ),
        "first_text_latency_p50_s": _percentile(
            [stream["first_text_latency_s"] for stream in accepted if stream["first_text_latency_s"] is not None],
            0.50,
        ),
        "first_text_latency_p95_s": _percentile(
            [stream["first_text_latency_s"] for stream in accepted if stream["first_text_latency_s"] is not None],
            0.95,
        ),
        "text_latency_p95_s": text_latency_p95,
        "text_latency_gate": (text_latency_p95 is not None and text_latency_p95 <= MAX_TEXT_LATENCY_S),
        "elapsed_s": round(time.monotonic() - started, 4),
        "gpu_memory": monitor.summary(),
        "streams": streams,
    }


async def _run_benchmark(
    pcm: bytes,
    duration_s: float,
    wav_sha256: str,
    runtime_health: Dict[str, Any],
    workload_metadata: Dict[str, Any],
) -> Dict[str, Any]:
    levels = list(LEVELS)
    if not levels or any(level < 1 for level in levels):
        raise ValueError("PARAKEET_STREAM_LEVELS must contain positive integers")
    if EXPECTED_CAPACITY < max(levels):
        raise ValueError(
            f"PARAKEET_STREAM_EXPECTED_CAPACITY={EXPECTED_CAPACITY} must cover the highest accepted level {max(levels)}"
        )
    if TARGET_STREAMS not in levels:
        raise ValueError(f"PARAKEET_TARGET_STREAMS={TARGET_STREAMS} must be included in PARAKEET_STREAM_LEVELS")
    if not 180.0 <= SUSTAIN_S <= 300.0:
        raise ValueError("PARAKEET_STREAM_SUSTAIN_S must be between 180 and 300 seconds")

    level_results = []
    for level in levels:
        print(f"\n--- realtime stream level {level} ---", flush=True)
        level_result = await _run_level(level, pcm, duration_s)
        level_results.append(level_result)
        print(
            f"accepted={level_result['accepted_streams']}/{level} "
            f"final_drain={level_result['final_drain_complete']} "
            f"nonempty_rate={level_result['nonempty_rate']:.0%} "
            f"p95_text_latency={level_result['text_latency_p95_s']}s",
            flush=True,
        )

    sustained_result: Optional[Dict[str, Any]] = None
    if SUSTAIN_S > 0:
        sustained_pcm = pcm * max(1, math.ceil(SUSTAIN_S / duration_s))
        sustained_pcm = sustained_pcm[: int(SUSTAIN_S * SAMPLE_RATE * BYTES_PER_SAMPLE)]
        sustained_result = await _run_level(max(levels), sustained_pcm, SUSTAIN_S)
        print(
            f"\n--- sustained realtime stream level {max(levels)} for {SUSTAIN_S:.0f}s ---\n"
            f"accepted={sustained_result['accepted_streams']}/{max(levels)} "
            f"final_drain={sustained_result['final_drain_complete']} "
            f"nonempty_rate={sustained_result['nonempty_rate']:.0%} "
            f"p95_text_latency={sustained_result['text_latency_p95_s']}s",
            flush=True,
        )

    probe_level = EXPECTED_CAPACITY + 1
    print(f"\n--- capacity rejection probe {probe_level} ---", flush=True)
    rejection_probe = await _run_level(probe_level, pcm, duration_s)
    print(
        f"accepted={rejection_probe['accepted_streams']}/{probe_level} "
        f"rejected={rejection_probe['rejected_streams']}",
        flush=True,
    )
    sustained_complete = bool(
        sustained_result
        and sustained_result["accepted_streams"] == max(levels)
        and sustained_result["error_streams"] == 0
        and sustained_result["ready_rate"] == 1.0
        and sustained_result["final_drain_complete"]
        and sustained_result["nonempty_rate"] == 1.0
        and sustained_result["speaker_fields_rate"] == 1.0
        and sustained_result["timestamp_valid_rate"] == 1.0
        and sustained_result["text_latency_timestamps_valid_rate"] == 1.0
        and (max(levels) < LATENCY_GATE_MIN_STREAMS or sustained_result["text_latency_gate"])
    )
    memory_results = [*level_results, rejection_probe]
    if sustained_result is not None:
        memory_results.append(sustained_result)
    return {
        "schema_version": 1,
        "status": "ok",
        "endpoint": "/v3/stream",
        "image_ref": IMAGE_REF or None,
        "source_sha": SOURCE_SHA,
        "runtime_health": runtime_health,
        "model_identity": runtime_health.get("model_identity"),
        "expected_model_identity": _expected_model_identity(),
        "coverage": {
            "fixture_language": "en",
            "multilingual_accuracy": "not_qualified",
            "note": (
                "This English LibriSpeech test-clean-derived capacity fixture qualifies transport, "
                "completeness, and capacity only; it cannot qualify multilingual accuracy."
            ),
        },
        "gpu": {
            "type": GPU_TYPE,
            "target_streams": TARGET_STREAMS,
            "hard_capacity_streams": EXPECTED_CAPACITY,
        },
        "audio": {
            "source_url": AUDIO_URL,
            "path": str(AUDIO_PATH),
            "source_provenance": {
                "dataset": "LibriSpeech test-clean",
                "license": "CC BY 4.0",
                "fixture_manifest": "backend/scripts/stt/modulate_repro/README.md",
                "wav_sha256": wav_sha256,
            },
            "sha256_pcm": workload_metadata["workload_pcm_sha256"],
            "sample_rate": SAMPLE_RATE,
            "duration_s": duration_s,
            "workload": workload_metadata,
        },
        "expected_capacity": EXPECTED_CAPACITY,
        "latency_gate": {
            "min_streams": LATENCY_GATE_MIN_STREAMS,
            "max_p95_seconds": MAX_TEXT_LATENCY_S,
        },
        "levels": level_results,
        "sustained": sustained_result,
        "capacity_rejection_probe": rejection_probe,
        "qualification": {
            "accepted_levels_complete": all(
                result["accepted_streams"] == result["requested_streams"]
                and result["error_streams"] == 0
                and result["ready_rate"] == 1.0
                and result["final_drain_complete"]
                and result["nonempty_rate"] == 1.0
                and result["speaker_fields_rate"] == 1.0
                and result["timestamp_valid_rate"] == 1.0
                and result["text_latency_timestamps_valid_rate"] == 1.0
                and (result["requested_streams"] < LATENCY_GATE_MIN_STREAMS or result["text_latency_gate"])
                for result in level_results
            ),
            "rejection_probe_enforced": (
                rejection_probe["accepted_streams"] == EXPECTED_CAPACITY
                and rejection_probe["rejected_streams"] == 1
                and rejection_probe["error_streams"] == 0
            ),
            "stream_readiness": all(result["ready_rate"] == 1.0 for result in level_results)
            and sustained_result is not None
            and sustained_result["ready_rate"] == 1.0,
            "latency_gate": all(
                result["requested_streams"] < LATENCY_GATE_MIN_STREAMS or result["text_latency_gate"]
                for result in level_results
            )
            and sustained_result is not None
            and (max(levels) < LATENCY_GATE_MIN_STREAMS or sustained_result["text_latency_gate"]),
            "sustained_capacity_complete": sustained_complete,
            "gpu_memory_observed": all(result["gpu_memory"]["available"] for result in memory_results),
            "model_identity": _model_identity_matches(runtime_health.get("model_identity")),
            "quality_claim": "not_scored; this artifact covers transport, completeness, and capacity only",
            "text_sentinel_smoke": all(
                result["text_sentinel_rate"] == 1.0
                for result in level_results
                if result["requested_streams"] in {min(levels), TARGET_STREAMS}
            ),
        },
    }


def _write_results(report: Dict[str, Any]) -> None:
    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = RESULTS_PATH.with_suffix(RESULTS_PATH.suffix + ".tmp")
    temporary_path.write_text(json.dumps(report, indent=2) + "\n")
    temporary_path.replace(RESULTS_PATH)
    print(f"Stream capacity artifact: {RESULTS_PATH}", flush=True)


def _run_and_record() -> Dict[str, Any]:
    runtime_health: Optional[Dict[str, Any]] = None
    try:
        runtime_health = _read_runtime_health()
        path = _download_fixture()
        pcm, duration_s, digest, wav_sha256 = _load_pcm(path)
        workload_pcm, workload_metadata = _trim_long_silence(pcm, duration_s)
        print(
            f"Using public speech fixture {path} ({duration_s:.1f}s source, "
            f"{workload_metadata['workload_duration_s']:.1f}s workload, "
            f"wav_sha256={wav_sha256}, pcm_sha256={digest})",
            flush=True,
        )
        return asyncio.run(
            _run_benchmark(
                workload_pcm,
                workload_metadata["workload_duration_s"],
                wav_sha256,
                runtime_health,
                workload_metadata,
            )
        )
    except Exception as error:
        report = {
            "schema_version": 1,
            "status": "error",
            "endpoint": "/v3/stream",
            "image_ref": IMAGE_REF or None,
            "source_sha": SOURCE_SHA,
            "runtime_health": runtime_health,
            "model_identity": runtime_health.get("model_identity") if runtime_health else None,
            "expected_model_identity": _expected_model_identity(),
            "coverage": {
                "fixture_language": "en",
                "multilingual_accuracy": "not_qualified",
            },
            "gpu": {"type": GPU_TYPE, "target_streams": TARGET_STREAMS},
            "error": f"{type(error).__name__}: {error}",
            "quality_claim": "not_scored; this artifact covers transport, completeness, and capacity only",
        }
        _write_results(report)
        raise


def test_realtime_tdt_stream_capacity() -> None:
    """Qualify all accepted levels and fail closed on capacity regressions."""

    report = _run_and_record()
    _write_results(report)
    qualification = report["qualification"]
    assert qualification["model_identity"], json.dumps(report.get("runtime_health"), indent=2)
    assert qualification["accepted_levels_complete"], json.dumps(report["levels"], indent=2)
    assert qualification["rejection_probe_enforced"], json.dumps(report["capacity_rejection_probe"], indent=2)
    assert qualification["stream_readiness"], json.dumps(report["levels"], indent=2)
    assert qualification["sustained_capacity_complete"], json.dumps(report["sustained"], indent=2)
    assert qualification["text_sentinel_smoke"], json.dumps(report["levels"], indent=2)
    assert qualification["gpu_memory_observed"], "nvidia-smi produced no GPU memory samples"


if __name__ == "__main__":
    report = _run_and_record()
    _write_results(report)
    if not all(report["qualification"].values()):
        raise SystemExit(1)
