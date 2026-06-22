"""
Concurrency stress test for parakeet batch transcription + diarization.

Reproduces the prod incident from PR #8108: concurrent /v2/transcribe
requests with diarize=true caused CUDA stream conflicts between the
NeMo batch transcription (GPU worker thread) and wespeaker embedding
inference (diarize_pool threads).

This test fires N concurrent requests and verifies zero CUDA errors.

Requires:
  - Parakeet server running on localhost:8080 (or PARAKEET_URL env var)
  - GPU (for ASR + diarization inference)

Usage (inside container with server running):
    python -m pytest tests/container/test_parakeet_concurrency.py -v -s
"""

import http.client
import io
import json
import os
import struct
import time
import wave
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse

import pytest

PARAKEET_URL = os.getenv("PARAKEET_URL", "http://127.0.0.1:8080")
CONCURRENCY = int(os.getenv("CONCURRENCY_LEVEL", "8"))
ROUNDS = int(os.getenv("CONCURRENCY_ROUNDS", "3"))


def _make_wav_bytes(duration_s=2.0, sample_rate=16000):
    """Generate speech-like audio (multi-tone) to ensure ASR produces segments.

    Silent audio would bypass the diarization embedding path entirely,
    giving false confidence that the CUDA fix works.
    """
    import math

    n_samples = int(duration_s * sample_rate)
    samples = []
    for i in range(n_samples):
        t = i / sample_rate
        val = 0.3 * math.sin(2 * math.pi * 250 * t)
        val += 0.2 * math.sin(2 * math.pi * 440 * t)
        val += 0.1 * math.sin(2 * math.pi * 800 * t)
        val *= 0.8 + 0.2 * math.sin(2 * math.pi * 3 * t)
        samples.append(int(val * 16000))
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(struct.pack("<" + "h" * n_samples, *samples))
    return buf.getvalue()


def _send_transcribe_request(wav_bytes, diarize=True, request_id=0):
    parsed = urlparse(PARAKEET_URL)
    boundary = f"----ConcurrencyTest{request_id}"

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

    conn = http.client.HTTPConnection(parsed.hostname, parsed.port, timeout=120)
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
            "body": data[:1000],
            "error": None,
        }
    except Exception as e:
        return {
            "request_id": request_id,
            "status": 0,
            "body": b"",
            "error": str(e),
        }


class TestConcurrentTranscription:
    """Stress test: concurrent /v2/transcribe with diarize=true."""

    @pytest.fixture(scope="class")
    def wav_data(self):
        return _make_wav_bytes(duration_s=3.0, sample_rate=16000)

    def test_concurrent_diarize_requests_no_cuda_errors(self, wav_data):
        """Fire N concurrent /v2/transcribe?diarize=true and verify zero 500s.

        This is the exact scenario that caused the PR #8108 prod incident:
        multiple requests hitting batch transcription + diarization
        simultaneously, triggering CUDA stream conflicts.
        """
        all_results = []

        for round_num in range(ROUNDS):
            print(f"\n  Round {round_num + 1}/{ROUNDS}: " f"firing {CONCURRENCY} concurrent requests...")
            t0 = time.time()

            with ThreadPoolExecutor(max_workers=CONCURRENCY) as pool:
                futures = {
                    pool.submit(
                        _send_transcribe_request,
                        wav_data,
                        diarize=True,
                        request_id=round_num * CONCURRENCY + i,
                    ): i
                    for i in range(CONCURRENCY)
                }
                round_results = []
                for future in as_completed(futures):
                    round_results.append(future.result())

            elapsed = time.time() - t0
            successes = sum(1 for r in round_results if r["status"] == 200)
            failures = [r for r in round_results if r["status"] != 200]

            print(f"  {successes}/{CONCURRENCY} succeeded in {elapsed:.1f}s")
            if failures:
                for f in failures:
                    print(
                        f"  FAIL request {f['request_id']}: "
                        f"status={f['status']} error={f['error']} "
                        f"body={f['body'][:200]}"
                    )

            all_results.extend(round_results)

        total = len(all_results)
        total_success = sum(1 for r in all_results if r["status"] == 200)
        total_500 = sum(1 for r in all_results if r["status"] == 500)
        total_503 = sum(1 for r in all_results if r["status"] == 503)
        total_err = sum(1 for r in all_results if r["error"] is not None)

        print(
            f"\n  TOTAL: {total_success}/{total} succeeded, "
            f"{total_500} x 500, {total_503} x 503, {total_err} connection errors"
        )

        cuda_errors = [r for r in all_results if r["status"] == 500 and b"CUDA" in r["body"]]
        if cuda_errors:
            details = "\n".join(f"  req {r['request_id']}: {r['body'][:300]}" for r in cuda_errors)
            assert False, f"{len(cuda_errors)} CUDA errors detected in concurrent requests:\n{details}"

        assert total_500 == 0, (
            f"{total_500}/{total} requests returned 500. "
            f"This suggests a concurrency bug (CUDA stream conflict, race condition, etc.)"
        )

        diarized_count = 0
        for r in all_results:
            if r["status"] == 200:
                data = json.loads(r["body"])
                for seg in data.get("segments", []):
                    if seg.get("speaker", "").startswith("SPEAKER_"):
                        diarized_count += 1
                        break
        print(f"  Diarized responses (with speaker labels): {diarized_count}/{total_success}")
        assert diarized_count > 0, (
            "No responses contained speaker labels — embedding path was never exercised. "
            "The test audio may be too short or silent for ASR to produce segments."
        )

    def test_concurrent_mixed_diarize_and_nodiarize(self, wav_data):
        """Mixed concurrent requests: some with diarize, some without.

        Verifies that non-diarize requests don't get blocked or crash
        when diarize requests are consuming the GPU worker for embeddings.
        """
        results = []

        with ThreadPoolExecutor(max_workers=CONCURRENCY) as pool:
            futures = {}
            for i in range(CONCURRENCY):
                diarize = i % 2 == 0
                f = pool.submit(
                    _send_transcribe_request,
                    wav_data,
                    diarize=diarize,
                    request_id=i,
                )
                futures[f] = (i, diarize)

            for future in as_completed(futures):
                idx, diarize = futures[future]
                r = future.result()
                r["diarize"] = diarize
                results.append(r)

        successes = sum(1 for r in results if r["status"] == 200)
        failures_500 = [r for r in results if r["status"] == 500]

        print(f"\n  Mixed mode: {successes}/{CONCURRENCY} succeeded, " f"{len(failures_500)} x 500")

        assert len(failures_500) == 0, f"{len(failures_500)} requests failed with 500 in mixed diarize mode"

    def test_sustained_sequential_after_concurrent_burst(self, wav_data):
        """After a concurrent burst, verify sequential requests still work.

        Catches state corruption from concurrent access (e.g. GPU worker
        stuck, embedding model in bad state, CUDA context corrupted).
        """
        print("\n  Burst: firing concurrent requests...")
        with ThreadPoolExecutor(max_workers=CONCURRENCY) as pool:
            futures = [pool.submit(_send_transcribe_request, wav_data, True, i) for i in range(CONCURRENCY)]
            burst_results = [f.result() for f in as_completed(futures)]

        burst_500s = sum(1 for r in burst_results if r["status"] == 500)
        assert burst_500s == 0, f"Burst had {burst_500s} x 500 errors"

        print("  Sequential: verifying 5 follow-up requests...")
        for i in range(5):
            result = _send_transcribe_request(wav_data, True, 1000 + i)
            assert result["status"] == 200, (
                f"Sequential request {i} failed after burst: " f"status={result['status']} body={result['body'][:200]}"
            )
            if result["status"] == 200:
                data = json.loads(result["body"])
                assert "segments" in data
                for seg in data["segments"]:
                    assert "speaker" in seg, "Missing speaker label after burst"
        print("  All sequential requests succeeded")
