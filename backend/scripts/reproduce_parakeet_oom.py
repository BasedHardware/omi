#!/usr/bin/env python3
"""
Reproduce the parakeet Phase 2 OOM (PR #8428).

Root cause: ATTENTION_MODE=auto disables torch.compile, which eliminates
operator fusion and buffer reuse.  Under concurrent batch load, VRAM
for attention tensors increases ~3x, causing OOM on L4 (22GB).

This script:
1. Queries the server's current config (attention mode, torch.compile)
2. Sends concurrent requests with increasing audio durations
3. Monitors VRAM via nvidia-smi at each step
4. Reports the exact VRAM profile and identifies OOM thresholds

Usage:
    # Against a server with torch.compile enabled (baseline):
    PARAKEET_URL=http://localhost:8080 python reproduce_parakeet_oom.py

    # Against a server with ATTENTION_MODE=auto (reproduces OOM):
    PARAKEET_ATTENTION_MODE=auto PARAKEET_URL=http://localhost:8080 \
        python reproduce_parakeet_oom.py

    # On dev cluster:
    kubectl port-forward -n dev-omi-backend svc/dev-omi-parakeet 8080:8080 &
    PARAKEET_URL=http://localhost:8080 python reproduce_parakeet_oom.py
"""

import http.client
import io
import math
import os
import struct
import subprocess
import sys
import time
import wave
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from typing import List, Optional, Tuple, TypedDict
from urllib.parse import urlparse

PARAKEET_URL = os.getenv("PARAKEET_URL", "http://127.0.0.1:8080")
CONCURRENCY = int(os.getenv("REPRO_CONCURRENCY", "4"))
DURATIONS = [10, 30, 60, 120, 300, 600]


def get_gpu_memory() -> Tuple[Optional[float], Optional[float]]:
    try:
        out = (
            subprocess.check_output(
                ["nvidia-smi", "--query-gpu=memory.used,memory.total", "--format=csv,noheader,nounits"],
                timeout=5,
            )
            .decode()
            .strip()
        )
        used, total = out.split(",")
        return float(used.strip()), float(total.strip())
    except Exception:
        return None, None


def get_server_config() -> str:
    try:
        parsed = urlparse(PARAKEET_URL)
        conn = http.client.HTTPConnection(parsed.hostname or "127.0.0.1", parsed.port, timeout=5)
        conn.request("GET", "/health")
        resp = conn.getresponse()
        body = resp.read().decode()
        conn.close()
        if resp.status == 200:
            return body
    except Exception as e:
        return f"error: {e}"
    return "unknown"


def get_oom_count() -> float:
    try:
        parsed = urlparse(PARAKEET_URL)
        conn = http.client.HTTPConnection(parsed.hostname or "127.0.0.1", parsed.port, timeout=5)
        conn.request("GET", "/metrics/")
        resp = conn.getresponse()
        body = resp.read().decode()
        conn.close()
        for line in body.split("\n"):
            if line.startswith("parakeet_gpu_oom_total "):
                return float(line.split()[1])
    except Exception:
        pass
    return 0


def make_wav(duration_s: int, sample_rate: int = 16000) -> bytes:
    n_samples = int(duration_s * sample_rate)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        samples: List[int] = []
        for i in range(n_samples):
            t = i / sample_rate
            val = 0.3 * math.sin(2 * math.pi * 250 * t)
            val += 0.2 * math.sin(2 * math.pi * 440 * t)
            samples.append(int(val * 16000))
        w.writeframes(struct.pack("<" + "h" * n_samples, *samples))
    return buf.getvalue()


class TranscriptionResult(TypedDict):
    id: int
    status: int
    error: Optional[str]
    body: bytes


def send_request(wav_bytes: bytes, request_id: int = 0, timeout: int = 600) -> TranscriptionResult:
    parsed = urlparse(PARAKEET_URL)
    boundary = f"----Repro{request_id}"
    body = b"".join(
        [
            f"--{boundary}\r\n".encode(),
            b'Content-Disposition: form-data; name="file"; filename="test.wav"\r\n',
            b"Content-Type: audio/wav\r\n\r\n",
            wav_bytes,
            f"\r\n--{boundary}\r\n".encode(),
            b'Content-Disposition: form-data; name="diarize"\r\n\r\n',
            b"true",
            f"\r\n--{boundary}--\r\n".encode(),
        ]
    )
    conn = http.client.HTTPConnection(parsed.hostname or "127.0.0.1", parsed.port, timeout=timeout)
    try:
        conn.request(
            "POST",
            "/v2/transcribe",
            body=body,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        )
        resp = conn.getresponse()
        status = resp.status
        data = resp.read()[:500]
        conn.close()
        return {"id": request_id, "status": status, "error": None, "body": data}
    except Exception as e:
        return {"id": request_id, "status": 0, "error": str(e), "body": b""}


class TierResult(TypedDict):
    duration: int
    peak_mib: float
    delta_mib: float
    successes: int
    failures: int
    ooms: int
    elapsed: float


def main() -> int:
    print("=" * 70)
    print("Parakeet OOM Reproduction Script")
    print("=" * 70)

    health = get_server_config()
    print(f"\nServer: {PARAKEET_URL}")
    print(f"Health: {health}")

    used, total = get_gpu_memory()
    if used is not None and total is not None:
        print(f"GPU: {used:.0f}/{total:.0f} MiB ({used / total * 100:.1f}%)")
    else:
        print("GPU: nvidia-smi not available (running without VRAM monitoring)")

    initial_ooms = get_oom_count()
    print(f"OOM counter: {initial_ooms:.0f}")
    print(f"Concurrency: {CONCURRENCY}")
    print(f"Durations to test: {DURATIONS}s")

    print(
        f"\n{'Duration':>8s}  {'CC':>3s}  {'VRAM Before':>12s}  {'VRAM Peak':>10s}  "
        f"{'Delta':>8s}  {'OK':>3s}  {'Fail':>4s}  {'OOM':>4s}  {'Status':>8s}"
    )
    print("-" * 85)

    all_results: List[TierResult] = []
    oom_threshold_found: Optional[int] = None

    for dur in DURATIONS:
        wav_data = make_wav(dur)
        before_used, before_total = get_gpu_memory()
        oom_before = get_oom_count()

        peak_used = before_used or 0
        t0 = time.time()

        with ThreadPoolExecutor(max_workers=CONCURRENCY) as pool:
            futures: List[Future[TranscriptionResult]] = [
                pool.submit(send_request, wav_data, i) for i in range(CONCURRENCY)
            ]

            done_count = 0
            for _ in as_completed(futures):
                done_count += 1
                cur_used, _ = get_gpu_memory()
                if cur_used and cur_used > peak_used:
                    peak_used = cur_used

            results = [f.result() for f in futures]

        elapsed = time.time() - t0
        oom_after = get_oom_count()
        new_ooms = int(oom_after - oom_before)

        successes = sum(1 for r in results if r["status"] == 200)
        failures = sum(1 for r in results if r["status"] != 200)

        delta = peak_used - (before_used or 0)
        pct = (peak_used / before_total * 100) if before_total else 0

        status = "OK" if failures == 0 and new_ooms == 0 else "FAIL"
        if new_ooms > 0:
            status = "OOM"
            if oom_threshold_found is None:
                oom_threshold_found = dur

        before_str = f"{before_used:.0f}" if before_used else "N/A"
        peak_str = f"{peak_used:.0f} ({pct:.0f}%)" if before_total else "N/A"
        delta_str = f"+{delta:.0f}" if before_used else "N/A"

        print(
            f"  {dur:>6.0f}s  {CONCURRENCY:>3d}  {before_str:>11s}  {peak_str:>10s}  "
            f"{delta_str:>8s}  {successes:>3d}  {failures:>4d}  {new_ooms:>4d}  {status:>8s}"
        )

        all_results.append(
            {
                "duration": dur,
                "peak_mib": peak_used,
                "delta_mib": delta,
                "successes": successes,
                "failures": failures,
                "ooms": new_ooms,
                "elapsed": elapsed,
            }
        )

        if new_ooms > 0:
            print(f"\n  !!! OOM at {dur}s with cc={CONCURRENCY}. " f"Errors from failed requests:")
            for r in results:
                if r["status"] != 200:
                    print(f"      req {r['id']}: status={r['status']} " f"err={r['error']} body={r['body'][:200]}")

    total_ooms = int(get_oom_count() - initial_ooms)
    print("\n" + "=" * 70)
    print("Summary")
    print("=" * 70)
    print(f"Total OOMs: {total_ooms}")
    if oom_threshold_found:
        print(f"OOM threshold: {oom_threshold_found}s audio @ cc={CONCURRENCY}")
        print(f"\nREPRODUCED: OOM occurs with {CONCURRENCY}x {oom_threshold_found}s " f"concurrent requests.")
        print("Root cause: torch.compile disabled (ATTENTION_MODE=auto) eliminates")
        print("operator fusion, tripling VRAM for attention tensors (B,8,T,T).")
    else:
        print("No OOM observed at any duration tier.")
        print("This config is safe for the tested audio lengths and concurrency.")

    return 1 if total_ooms > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
