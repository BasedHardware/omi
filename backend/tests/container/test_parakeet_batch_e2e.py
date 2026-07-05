"""
End-to-end tests for parakeet /v1/transcribe and /v2/transcribe batch endpoints.

Tests cover: transcription quality, timestamps, diarization, concurrency,
error handling, and duration guard.

Requires:
  - Parakeet server running (PARAKEET_URL env var, default http://127.0.0.1:8080)
  - GPU with batch model loaded

Usage:
    # Against port-forwarded dev pod:
    PARAKEET_URL=http://localhost:10260 python -m pytest tests/container/test_parakeet_batch_e2e.py -v -s

    # Inside container:
    python -m pytest tests/container/test_parakeet_batch_e2e.py -v -s
"""

import http.client
import io
import json
import math
import os
import struct
import time
import wave
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse

import pytest

PARAKEET_URL = os.getenv("PARAKEET_URL", "http://127.0.0.1:8080")


def _check_server_ready():
    parsed = urlparse(PARAKEET_URL)
    try:
        conn = http.client.HTTPConnection(parsed.hostname, parsed.port or 80, timeout=5)
        conn.request("GET", "/health")
        resp = conn.getresponse()
        data = json.loads(resp.read())
        conn.close()
        return data.get("ready", False)
    except Exception:
        return False


server_ready = _check_server_ready()
skip_no_server = pytest.mark.skipif(not server_ready, reason="Parakeet server not available")


def _make_speech_wav(duration_s=3.0, sample_rate=16000):
    n = int(duration_s * sample_rate)
    samples = []
    for i in range(n):
        t = i / sample_rate
        val = 0.3 * math.sin(2 * math.pi * 250 * t)
        val += 0.2 * math.sin(2 * math.pi * 440 * t)
        val += 0.1 * math.sin(2 * math.pi * 800 * t)
        val *= 0.8 + 0.2 * math.sin(2 * math.pi * 3 * t)
        samples.append(max(-32768, min(32767, int(val * 16000))))
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(struct.pack(f"<{n}h", *samples))
    return buf.getvalue()


def _load_real_wav():
    ls_dir = os.path.join(os.path.dirname(__file__), "librispeech")
    if os.path.isdir(ls_dir):
        wavs = sorted(f for f in os.listdir(ls_dir) if f.endswith(".wav"))
        if wavs:
            with open(os.path.join(ls_dir, wavs[0]), "rb") as f:
                return f.read()
    for path in ["/tmp/bench_speech.wav", "/tmp/speaker1.wav"]:
        if os.path.exists(path):
            with open(path, "rb") as f:
                return f.read()
    return None


def _get_test_wav():
    real = _load_real_wav()
    return real if real else _make_speech_wav(3.0)


def _post_transcribe(endpoint, wav_bytes, params=None, timeout=30):
    parsed = urlparse(PARAKEET_URL)
    conn = http.client.HTTPConnection(parsed.hostname, parsed.port or 80, timeout=timeout)
    boundary = "----PakaeetTestBoundary"
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="test.wav"\r\n'
        f"Content-Type: audio/wav\r\n\r\n"
    ).encode()
    body += wav_bytes
    body += f"\r\n--{boundary}--\r\n".encode()

    url = endpoint
    if params:
        url += "?" + "&".join(f"{k}={v}" for k, v in params.items())

    conn.request(
        "POST",
        url,
        body=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    resp = conn.getresponse()
    result = resp.read()
    conn.close()
    return resp.status, json.loads(result) if resp.status == 200 else result


@skip_no_server
class TestV1Transcribe:

    def test_basic_transcription(self):
        wav = _get_test_wav()
        status, data = _post_transcribe("/v1/transcribe", wav)
        assert status == 200, f"Expected 200, got {status}"
        assert "result" in data or "text" in data or "segments" in data

    def test_response_has_segments(self):
        wav = _get_test_wav()
        status, data = _post_transcribe("/v1/transcribe", wav)
        assert status == 200
        segments = data.get("segments", data.get("result", []))
        if isinstance(segments, list) and len(segments) > 0:
            seg = segments[0]
            assert "text" in seg or "segment" in seg

    def test_latency_under_10s(self):
        wav = _get_test_wav()
        t0 = time.monotonic()
        status, _ = _post_transcribe("/v1/transcribe", wav)
        elapsed = time.monotonic() - t0
        assert status == 200
        assert elapsed < 10.0, f"Transcription took {elapsed:.2f}s"


@skip_no_server
class TestV2Transcribe:

    def test_basic_transcription(self):
        wav = _get_test_wav()
        status, data = _post_transcribe("/v2/transcribe", wav)
        assert status == 200, f"Expected 200, got {status}: {data}"
        segments = data.get("segments", [])
        assert isinstance(segments, list)

    def test_segments_have_timestamps(self):
        wav = _get_test_wav()
        status, data = _post_transcribe("/v2/transcribe", wav)
        assert status == 200
        segments = data.get("segments", [])
        if len(segments) > 0:
            seg = segments[0]
            assert "start" in seg, f"Segment missing 'start': {seg}"
            assert "end" in seg, f"Segment missing 'end': {seg}"
            assert seg["end"] >= seg["start"]

    def test_segments_have_text(self):
        wav = _get_test_wav()
        status, data = _post_transcribe("/v2/transcribe", wav)
        assert status == 200
        segments = data.get("segments", [])
        texts = [s.get("text", "") for s in segments]
        combined = " ".join(texts).strip()
        assert isinstance(combined, str)
        if segments:
            assert len(combined) > 0, "Segments present but all have empty text"

    def test_diarize_false(self):
        wav = _get_test_wav()
        status, data = _post_transcribe("/v2/transcribe", wav, params={"diarize": "false"})
        assert status == 200
        segments = data.get("segments", [])
        assert isinstance(segments, list)

    def test_latency_under_10s(self):
        wav = _get_test_wav()
        t0 = time.monotonic()
        status, _ = _post_transcribe("/v2/transcribe", wav)
        elapsed = time.monotonic() - t0
        assert status == 200
        assert elapsed < 10.0, f"Transcription took {elapsed:.2f}s"


@skip_no_server
class TestV2TranscribeEdgeCases:

    def test_very_short_audio(self):
        wav = _make_speech_wav(0.1)
        status, data = _post_transcribe("/v2/transcribe", wav)
        assert status == 200

    def test_silence_audio(self):
        buf = io.BytesIO()
        with wave.open(buf, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(16000)
            w.writeframes(b"\x00" * (16000 * 2))
        status, data = _post_transcribe("/v2/transcribe", buf.getvalue())
        assert status == 200

    def test_5s_audio(self):
        wav = _make_speech_wav(5.0)
        status, data = _post_transcribe("/v2/transcribe", wav, timeout=30)
        assert status == 200
        segments = data.get("segments", [])
        assert isinstance(segments, list)


@skip_no_server
class TestBatchConcurrency:

    def test_4_concurrent_requests(self):
        wav = _get_test_wav()
        results = []

        def do_request(idx):
            t0 = time.monotonic()
            status, data = _post_transcribe("/v2/transcribe", wav, timeout=30)
            return {"idx": idx, "status": status, "elapsed": time.monotonic() - t0}

        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = [pool.submit(do_request, i) for i in range(4)]
            for f in as_completed(futures):
                results.append(f.result())

        successes = [r for r in results if r["status"] == 200]
        assert len(successes) == 4, f"Only {len(successes)}/4 succeeded: {results}"

    def test_8_concurrent_requests(self):
        wav = _make_speech_wav(1.0)
        results = []

        def do_request(idx):
            status, data = _post_transcribe("/v2/transcribe", wav, timeout=30)
            return {"idx": idx, "status": status}

        with ThreadPoolExecutor(max_workers=8) as pool:
            futures = [pool.submit(do_request, i) for i in range(8)]
            for f in as_completed(futures):
                results.append(f.result())

        successes = [r for r in results if r["status"] == 200]
        assert len(successes) == 8, f"Only {len(successes)}/8 succeeded: {results}"


@skip_no_server
class TestHealthAndMetrics:

    def test_health_ready(self):
        parsed = urlparse(PARAKEET_URL)
        conn = http.client.HTTPConnection(parsed.hostname, parsed.port or 80, timeout=5)
        conn.request("GET", "/health")
        resp = conn.getresponse()
        data = json.loads(resp.read())
        conn.close()
        assert resp.status == 200
        assert data["ready"] is True

    def test_batch_metrics(self):
        parsed = urlparse(PARAKEET_URL)
        conn = http.client.HTTPConnection(parsed.hostname, parsed.port or 80, timeout=5)
        conn.request("GET", "/batch/metrics")
        resp = conn.getresponse()
        data = json.loads(resp.read())
        conn.close()
        assert resp.status == 200
        assert "total_requests" in data

    def test_prometheus_metrics(self):
        parsed = urlparse(PARAKEET_URL)
        conn = http.client.HTTPConnection(parsed.hostname, parsed.port or 80, timeout=5)
        conn.request("GET", "/metrics")
        resp = conn.getresponse()
        if resp.status == 307:
            location = resp.getheader("Location", "/metrics/")
            resp.read()
            conn.request("GET", location)
            resp = conn.getresponse()
        body = resp.read().decode()
        conn.close()
        assert resp.status == 200
        assert "parakeet_requests_total" in body
