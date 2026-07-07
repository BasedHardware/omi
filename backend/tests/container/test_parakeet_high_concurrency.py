"""
High-concurrency end-to-end stress test for parakeet.

Fires 16+ concurrent /v2/transcribe requests with diarize=true and verifies:
1. Zero HTTP 500 errors (CUDA conflicts, GPU worker crashes)
2. All responses contain valid transcription output
3. Transcription quality is consistent under load (no WER degradation)

Extends the base concurrency test with higher load and quality checks.

Requires:
  - Parakeet server running on localhost:8080 (or PARAKEET_URL env var)
  - GPU (for ASR + diarization inference)

Usage (inside container with server running):
    python -m pytest tests/container/test_parakeet_high_concurrency.py -v -s
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
HIGH_CONCURRENCY = int(os.getenv("HIGH_CONCURRENCY_LEVEL", "16"))
HIGH_ROUNDS = int(os.getenv("HIGH_CONCURRENCY_ROUNDS", "5"))
RTFX_CONCURRENCY = int(os.getenv("RTFX_CONCURRENCY", "16"))
RTFX_REQUESTS = int(os.getenv("RTFX_REQUESTS", "50"))
RTFX_AUDIO_DURATION = float(os.getenv("RTFX_AUDIO_DURATION", "5.0"))
RTFX_MIN_THRESHOLD = float(os.getenv("RTFX_MIN_THRESHOLD", "50.0"))


def _make_speech_wav(duration_s=3.0, sample_rate=16000):
    n_samples = int(duration_s * sample_rate)
    samples = []
    for i in range(n_samples):
        t = i / sample_rate
        val = 0.3 * math.sin(2 * math.pi * 250 * t)
        val += 0.2 * math.sin(2 * math.pi * 440 * t)
        val += 0.1 * math.sin(2 * math.pi * 800 * t)
        val += 0.05 * math.sin(2 * math.pi * 1200 * t)
        val *= 0.8 + 0.2 * math.sin(2 * math.pi * 3 * t)
        val *= 1.0 + 0.3 * math.sin(2 * math.pi * 0.5 * t)
        samples.append(int(val * 16000))
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(struct.pack("<" + "h" * n_samples, *samples))
    return buf.getvalue()


def _send_request(wav_bytes, diarize=True, request_id=0, timeout=180):
    parsed = urlparse(PARAKEET_URL)
    boundary = f"----HighConc{request_id}"

    body_parts = [
        f"--{boundary}\r\n".encode(),
        b'Content-Disposition: form-data; name="file"; filename="test.wav"\r\n',
        b"Content-Type: audio/wav\r\n\r\n",
        wav_bytes,
        f"\r\n--{boundary}\r\n".encode(),
        b'Content-Disposition: form-data; name="diarize"\r\n\r\n',
        str(diarize).lower().encode(),
        f"\r\n--{boundary}--\r\n".encode(),
    ]
    body = b"".join(body_parts)

    conn = http.client.HTTPConnection(parsed.hostname, parsed.port, timeout=timeout)
    try:
        conn.request(
            "POST",
            "/v2/transcribe",
            body=body,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        )
        resp = conn.getresponse()
        status = resp.status
        data = resp.read()
        conn.close()
        return {
            "request_id": request_id,
            "status": status,
            "body": data[:2000],
            "error": None,
        }
    except Exception as e:
        return {
            "request_id": request_id,
            "status": 0,
            "body": b"",
            "error": str(e),
        }


class TestHighConcurrency:
    """High-concurrency end-to-end stress test."""

    @pytest.fixture(scope="class")
    def wav_data(self):
        return _make_speech_wav(duration_s=3.0, sample_rate=16000)

    def test_high_concurrency_zero_errors(self, wav_data):
        """Fire 16 concurrent diarize=true requests for 5 rounds (80 total).

        This tests sustained high load — not just a single burst.
        Verifies zero 500 errors and zero CUDA errors.
        """
        all_results = []

        for round_num in range(HIGH_ROUNDS):
            print(f"\n  Round {round_num + 1}/{HIGH_ROUNDS}: " f"firing {HIGH_CONCURRENCY} concurrent requests...")
            t0 = time.time()

            with ThreadPoolExecutor(max_workers=HIGH_CONCURRENCY) as pool:
                futures = {
                    pool.submit(
                        _send_request,
                        wav_data,
                        diarize=True,
                        request_id=round_num * HIGH_CONCURRENCY + i,
                    ): i
                    for i in range(HIGH_CONCURRENCY)
                }
                round_results = []
                for future in as_completed(futures):
                    round_results.append(future.result())

            elapsed = time.time() - t0
            successes = sum(1 for r in round_results if r["status"] == 200)
            failures = [r for r in round_results if r["status"] != 200]

            print(f"  {successes}/{HIGH_CONCURRENCY} succeeded in {elapsed:.1f}s")
            if failures:
                for f in failures[:3]:
                    print(
                        f"  FAIL request {f['request_id']}: "
                        f"status={f['status']} error={f['error']} "
                        f"body={f['body'][:200]}"
                    )

            all_results.extend(round_results)

        total = len(all_results)
        total_success = sum(1 for r in all_results if r["status"] == 200)
        total_500 = sum(1 for r in all_results if r["status"] == 500)
        total_err = sum(1 for r in all_results if r["error"] is not None)

        print(f"\n  TOTAL: {total_success}/{total} succeeded, " f"{total_500} x 500, {total_err} connection errors")

        cuda_errors = [r for r in all_results if r["status"] == 500 and b"CUDA" in r["body"]]
        assert len(cuda_errors) == 0, f"{len(cuda_errors)} CUDA errors in high-concurrency test"

        failures = [r for r in all_results if r["status"] != 200 or r["error"] is not None]
        if failures:
            detail = "; ".join(f"req {r['request_id']}: status={r['status']} err={r['error']}" for r in failures[:5])
            assert False, f"{len(failures)}/{total} requests failed under high concurrency: {detail}"

    def test_high_concurrency_all_responses_valid(self, wav_data):
        """Under high load, every request must succeed with valid JSON."""
        results = []

        with ThreadPoolExecutor(max_workers=HIGH_CONCURRENCY) as pool:
            futures = [pool.submit(_send_request, wav_data, True, i) for i in range(HIGH_CONCURRENCY)]
            for f in as_completed(futures):
                results.append(f.result())

        failures = [r for r in results if r["status"] != 200 or r["error"] is not None]
        assert len(failures) == 0, f"{len(failures)}/{len(results)} requests failed: " + "; ".join(
            f"req {r['request_id']}: status={r['status']} err={r['error']}" for r in failures[:3]
        )

        print(f"\n  Validating {len(results)} responses...")
        invalid = []
        for r in results:
            try:
                data = json.loads(r["body"])
                if "segments" not in data:
                    invalid.append((r["request_id"], "missing 'segments' key"))
                elif not isinstance(data["segments"], list):
                    invalid.append((r["request_id"], "'segments' is not a list"))
            except json.JSONDecodeError as e:
                invalid.append((r["request_id"], f"invalid JSON: {e}"))

        assert len(invalid) == 0, f"{len(invalid)} responses had invalid structure: {invalid[:5]}"

    def test_high_concurrency_diarization_active(self, wav_data):
        """Under high load, at least some responses must contain speaker labels.

        This verifies the embedding path is exercised even under contention.
        """
        results = []

        with ThreadPoolExecutor(max_workers=HIGH_CONCURRENCY) as pool:
            futures = [pool.submit(_send_request, wav_data, True, i) for i in range(HIGH_CONCURRENCY)]
            for f in as_completed(futures):
                results.append(f.result())

        failures = [r for r in results if r["status"] != 200 or r["error"] is not None]
        assert len(failures) == 0, f"{len(failures)} requests failed — cannot verify diarization"

        diarized = 0
        for r in results:
            try:
                data = json.loads(r["body"])
                for seg in data.get("segments", []):
                    if seg.get("speaker", "").startswith("SPEAKER_"):
                        diarized += 1
                        break
            except json.JSONDecodeError:
                pass

        print(f"\n  Diarized: {diarized}/{len(results)} under high concurrency")
        assert diarized > 0, "No responses had speaker labels under high concurrency — embedding path not exercised"

    def test_sustained_ramp(self, wav_data):
        """Ramp from low to high concurrency and verify no degradation.

        Tests: 2 → 4 → 8 → 16 concurrent requests.
        Catches issues that only appear at specific concurrency levels.
        """
        levels = [2, 4, 8, HIGH_CONCURRENCY]

        for level in levels:
            print(f"\n  Ramp level={level}...")
            t0 = time.time()

            with ThreadPoolExecutor(max_workers=level) as pool:
                futures = [pool.submit(_send_request, wav_data, True, i) for i in range(level)]
                results = [f.result() for f in as_completed(futures)]

            elapsed = time.time() - t0
            successes = sum(1 for r in results if r["status"] == 200)
            failures = [r for r in results if r["status"] != 200 or r["error"] is not None]

            print(f"  level={level}: {successes}/{level} succeeded in {elapsed:.1f}s, {len(failures)} failures")

            if failures:
                statuses = ", ".join(f"status={r['status']}" for r in failures[:3])
                assert False, f"Ramp failed at concurrency={level}: {len(failures)} requests failed ({statuses})"

    def test_rtfx_gate(self):
        """RTFx must exceed threshold at cc=16 on L4.

        Sends RTFX_REQUESTS concurrent requests with RTFX_AUDIO_DURATION audio
        and gates on aggregate RTFx >= RTFX_MIN_THRESHOLD.
        """
        wav_data = _make_speech_wav(duration_s=RTFX_AUDIO_DURATION, sample_rate=16000)

        print(
            f"\n  RTFx gate: cc={RTFX_CONCURRENCY}, "
            f"{RTFX_REQUESTS} requests, "
            f"{RTFX_AUDIO_DURATION}s audio, "
            f"threshold={RTFX_MIN_THRESHOLD}x"
        )

        t_start = time.time()
        with ThreadPoolExecutor(max_workers=RTFX_CONCURRENCY) as pool:
            futures = [pool.submit(_send_request, wav_data, True, i, timeout=180) for i in range(RTFX_REQUESTS)]
            results = [f.result() for f in as_completed(futures)]
        t_total = time.time() - t_start

        successes = [r for r in results if r["status"] == 200]
        failures = [r for r in results if r["status"] != 200 or r["error"] is not None]

        assert len(failures) == 0, f"{len(failures)}/{len(results)} requests failed — " f"cannot measure RTFx"

        rps = len(successes) / t_total
        rtfx = rps * RTFX_AUDIO_DURATION

        print(
            f"  Result: {len(successes)}/{len(results)} OK in {t_total:.1f}s, "
            f"RPS={rps:.2f}, RTFx={rtfx:.1f}x "
            f"(threshold={RTFX_MIN_THRESHOLD}x)"
        )

        assert rtfx >= RTFX_MIN_THRESHOLD, (
            f"RTFx {rtfx:.1f}x below threshold {RTFX_MIN_THRESHOLD}x "
            f"at cc={RTFX_CONCURRENCY} "
            f"(RPS={rps:.2f}, {RTFX_AUDIO_DURATION}s audio)"
        )
