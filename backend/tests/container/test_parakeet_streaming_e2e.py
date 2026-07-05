"""
End-to-end tests for parakeet /v4/stream WebSocket streaming endpoint.

Tests cover: connection, transcription quality, error handling, concurrency,
session lifecycle, and close-code correctness.

Requires:
  - Parakeet server running (PARAKEET_URL env var, default http://127.0.0.1:8080)
  - GPU with streaming model loaded (PARAKEET_STREAM_MODEL set)

Usage:
    # Against port-forwarded dev pod:
    PARAKEET_URL=http://localhost:10260 python -m pytest tests/container/test_parakeet_streaming_e2e.py -v -s

    # Inside container:
    python -m pytest tests/container/test_parakeet_streaming_e2e.py -v -s
"""

import asyncio
import io
import json
import math
import os
import struct
import time
import wave

import pytest

PARAKEET_URL = os.getenv("PARAKEET_URL", "http://127.0.0.1:8080")
WS_URL = PARAKEET_URL.replace("http://", "ws://").replace("https://", "wss://")
STREAM_ENDPOINT = f"{WS_URL}/v4/stream"
SAMPLE_RATE = 16000
CHUNK_MS = 160
CHUNK_SAMPLES = SAMPLE_RATE * CHUNK_MS // 1000


def _check_streaming_available():
    import http.client
    from urllib.parse import urlparse

    parsed = urlparse(PARAKEET_URL)
    conn = http.client.HTTPConnection(parsed.hostname, parsed.port or 80, timeout=5)
    try:
        conn.request("GET", "/health")
        resp = conn.getresponse()
        data = json.loads(resp.read())
        return data.get("streaming", False) and data.get("ready", False)
    except Exception:
        return False
    finally:
        conn.close()


def _make_speech_pcm(duration_s=3.0, sample_rate=16000):
    n = int(duration_s * sample_rate)
    samples = []
    for i in range(n):
        t = i / sample_rate
        val = 0.3 * math.sin(2 * math.pi * 250 * t)
        val += 0.2 * math.sin(2 * math.pi * 440 * t)
        val += 0.1 * math.sin(2 * math.pi * 800 * t)
        val *= 0.8 + 0.2 * math.sin(2 * math.pi * 3 * t)
        samples.append(int(val * 16000))
    return struct.pack(f"<{n}h", *samples)


def _load_librispeech_sample():
    ls_dir = os.path.join(os.path.dirname(__file__), "librispeech")
    wavs = [f for f in os.listdir(ls_dir) if f.endswith(".wav")] if os.path.isdir(ls_dir) else []
    if wavs:
        path = os.path.join(ls_dir, sorted(wavs)[0])
        with wave.open(path, "rb") as wf:
            sr = wf.getframerate()
            frames = wf.readframes(wf.getnframes())
        if sr == 16000:
            return frames
    return None


def _get_test_audio():
    real = _load_librispeech_sample()
    if real:
        return real
    for path in ["/tmp/bench_speech.wav", "/tmp/speaker1.wav"]:
        if os.path.exists(path):
            with wave.open(path, "rb") as wf:
                if wf.getframerate() == 16000:
                    return wf.readframes(wf.getnframes())
    return _make_speech_pcm(3.0)


streaming_available = _check_streaming_available()
skip_no_streaming = pytest.mark.skipif(not streaming_available, reason="Streaming not available on server")

try:
    import websockets

    HAS_WEBSOCKETS = True
except ImportError:
    HAS_WEBSOCKETS = False

skip_no_ws = pytest.mark.skipif(not HAS_WEBSOCKETS, reason="websockets package not installed")


async def _drain_until_closed(ws, timeout=5.0):
    """Drain responses after finalize until we get a terminal status."""
    responses = []
    for _ in range(20):
        try:
            msg = await asyncio.wait_for(ws.recv(), timeout=timeout)
            data = json.loads(msg)
            responses.append(data)
            if data.get("status") in ("closed", "close_failed", "not_found"):
                break
        except asyncio.TimeoutError:
            break
    return responses


@skip_no_ws
@skip_no_streaming
class TestStreamConnection:

    @pytest.mark.asyncio
    async def test_connect_and_accept(self):
        async with websockets.connect(f"{STREAM_ENDPOINT}?sample_rate=16000", ping_interval=None) as ws:
            await ws.send(b"\x00\x00")
            assert True

    @pytest.mark.asyncio
    async def test_connect_latency_under_2s(self):
        t0 = time.monotonic()
        async with websockets.connect(f"{STREAM_ENDPOINT}?sample_rate=16000", ping_interval=None) as ws:
            latency = time.monotonic() - t0
            assert latency < 2.0, f"Connect took {latency:.2f}s"


@skip_no_ws
@skip_no_streaming
class TestStreamTranscription:

    @pytest.mark.asyncio
    async def test_single_stream_produces_output(self):
        audio = _get_test_audio()
        async with websockets.connect(
            f"{STREAM_ENDPOINT}?sample_rate=16000", max_size=10 * 1024 * 1024, ping_interval=None
        ) as ws:
            responses = []
            for i in range(0, len(audio), CHUNK_SAMPLES * 2):
                chunk = audio[i : i + CHUNK_SAMPLES * 2]
                await ws.send(chunk)
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=2.0)
                    responses.append(json.loads(msg))
                except asyncio.TimeoutError:
                    pass

            await ws.send("finalize")
            for _ in range(10):
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=5.0)
                    data = json.loads(msg)
                    responses.append(data)
                    if data.get("status") in ("closed", "close_failed", "not_found"):
                        break
                except asyncio.TimeoutError:
                    break

            assert len(responses) > 0, "No responses received"
            has_transcript = any(
                r.get("partial_transcript") or r.get("final_transcript") or r.get("final_text") for r in responses
            )
            has_close = any(r.get("status") == "closed" for r in responses)
            assert has_transcript or has_close, f"No transcript or close in responses: {responses[:3]}"

    @pytest.mark.asyncio
    async def test_first_response_latency(self):
        audio = _get_test_audio()
        t0 = time.monotonic()
        async with websockets.connect(
            f"{STREAM_ENDPOINT}?sample_rate=16000", max_size=10 * 1024 * 1024, ping_interval=None
        ) as ws:
            for i in range(0, min(len(audio), CHUNK_SAMPLES * 2 * 20), CHUNK_SAMPLES * 2):
                await ws.send(audio[i : i + CHUNK_SAMPLES * 2])
                try:
                    await asyncio.wait_for(ws.recv(), timeout=2.0)
                    first_latency = time.monotonic() - t0
                    assert first_latency < 5.0, f"First response took {first_latency:.2f}s"
                    return
                except asyncio.TimeoutError:
                    continue
            pytest.fail("No response within 20 chunks")


@skip_no_ws
@skip_no_streaming
class TestStreamErrorHandling:

    @pytest.mark.asyncio
    async def test_bad_sample_rate_returns_1003(self):
        try:
            async with websockets.connect(f"{STREAM_ENDPOINT}?sample_rate=8000", ping_interval=None) as ws:
                await asyncio.wait_for(ws.recv(), timeout=3.0)
                pytest.fail("Should have received close frame")
        except websockets.ConnectionClosed as e:
            assert e.code == 1003, f"Expected 1003, got {e.code}"
            assert "16kHz" in (e.reason or "")

    @pytest.mark.asyncio
    async def test_finalize_without_audio(self):
        async with websockets.connect(
            f"{STREAM_ENDPOINT}?sample_rate=16000", max_size=10 * 1024 * 1024, ping_interval=None
        ) as ws:
            await ws.send("finalize")
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=5.0)
                data = json.loads(msg)
                assert data.get("status") == "closed"
            except asyncio.TimeoutError:
                pytest.fail("No close response after finalize")


@skip_no_ws
@skip_no_streaming
class TestStreamConcurrency:

    @pytest.mark.asyncio
    async def test_4_concurrent_streams(self):
        audio = _get_test_audio()

        async def run_stream():
            async with websockets.connect(
                f"{STREAM_ENDPOINT}?sample_rate=16000", max_size=10 * 1024 * 1024, ping_interval=None
            ) as ws:
                for i in range(0, min(len(audio), CHUNK_SAMPLES * 2 * 10), CHUNK_SAMPLES * 2):
                    await ws.send(audio[i : i + CHUNK_SAMPLES * 2])
                    try:
                        await asyncio.wait_for(ws.recv(), timeout=2.0)
                    except asyncio.TimeoutError:
                        pass
                await ws.send("finalize")
                responses = await _drain_until_closed(ws)
                closed = [r for r in responses if r.get("status") == "closed"]
                return closed[0] if closed else None

        results = await asyncio.gather(*[run_stream() for _ in range(4)], return_exceptions=True)
        successes = [r for r in results if isinstance(r, dict) and r.get("status") == "closed"]
        assert len(successes) == 4, f"Only {len(successes)}/4 streams completed: {results}"

    @pytest.mark.asyncio
    async def test_8_concurrent_streams(self):
        audio = _get_test_audio()[: CHUNK_SAMPLES * 2 * 5]

        async def run_stream():
            async with websockets.connect(
                f"{STREAM_ENDPOINT}?sample_rate=16000", max_size=10 * 1024 * 1024, ping_interval=None
            ) as ws:
                for i in range(0, len(audio), CHUNK_SAMPLES * 2):
                    await ws.send(audio[i : i + CHUNK_SAMPLES * 2])
                    try:
                        await asyncio.wait_for(ws.recv(), timeout=2.0)
                    except asyncio.TimeoutError:
                        pass
                await ws.send("finalize")
                responses = await _drain_until_closed(ws)
                closed = [r for r in responses if r.get("status") == "closed"]
                return closed[0] if closed else None

        results = await asyncio.gather(*[run_stream() for _ in range(8)], return_exceptions=True)
        successes = [r for r in results if isinstance(r, dict) and r.get("status") == "closed"]
        assert len(successes) == 8, f"Only {len(successes)}/8 streams completed"


@skip_no_ws
@skip_no_streaming
class TestStreamLifecycle:

    @pytest.mark.asyncio
    async def test_clean_close_after_finalize(self):
        audio = _get_test_audio()[: CHUNK_SAMPLES * 2 * 3]
        async with websockets.connect(
            f"{STREAM_ENDPOINT}?sample_rate=16000", max_size=10 * 1024 * 1024, ping_interval=None
        ) as ws:
            for i in range(0, len(audio), CHUNK_SAMPLES * 2):
                await ws.send(audio[i : i + CHUNK_SAMPLES * 2])
                try:
                    await asyncio.wait_for(ws.recv(), timeout=2.0)
                except asyncio.TimeoutError:
                    pass

            await ws.send("finalize")
            responses = await _drain_until_closed(ws)
            closed = [r for r in responses if r.get("status") == "closed"]
            assert len(closed) == 1, f"Expected closed response, got: {responses}"
            data = closed[0]
            assert "stream_id" in data
            assert "final_text" in data

    @pytest.mark.asyncio
    async def test_metrics_after_stream(self):
        import http.client
        from urllib.parse import urlparse

        parsed = urlparse(PARAKEET_URL)
        conn = http.client.HTTPConnection(parsed.hostname, parsed.port or 80, timeout=5)
        conn.request("GET", "/stream/metrics")
        resp = conn.getresponse()
        data = json.loads(resp.read())
        conn.close()

        assert "total_streams_opened" in data
        assert "total_streams_closed" in data
        assert "active_streams" in data
        assert data["total_streams_opened"] >= 0
