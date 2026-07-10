#!/usr/bin/env python3
"""
Sustained VRAM leak detector for parakeet.

Runs sustained load for a configurable duration and detects monotonic
VRAM accumulation — the failure pattern from the prod OOM incident
(PR #8428 Phase 2: VRAM ratcheted 5.7→22 GiB over 22 min).

Key difference from burst tests (test_parakeet_vram_stress.py):
  - Burst tests catch "too much VRAM for one batch" failures
  - This test catches "VRAM never releases" leak failures

The test PASSES if:
  1. Peak VRAM stays below the headroom threshold (default 85%)
  2. VRAM slope is not monotonically increasing (regression slope < threshold)
  3. Zero OOM events from the metrics endpoint
  4. VRAM returns to within 20% of baseline after load stops

Usage:
    # Against dev pod (port-forwarded):
    PARAKEET_URL=http://127.0.0.1:10120 python parakeet_vram_leak_test.py

    # Quick 5-min smoke test:
    LEAK_TEST_DURATION=300 PARAKEET_URL=http://127.0.0.1:10120 \
        python parakeet_vram_leak_test.py

    # Full 20-min test with high concurrency:
    LEAK_TEST_DURATION=1200 LEAK_TEST_RPM=120 \
        PARAKEET_URL=http://127.0.0.1:10120 python parakeet_vram_leak_test.py

    # With real audio files:
    LEAK_TEST_AUDIO_DIR=/tmp/librispeech_continuous \
        PARAKEET_URL=http://127.0.0.1:10120 python parakeet_vram_leak_test.py

Env vars:
    PARAKEET_URL            Server URL (default http://127.0.0.1:8080)
    LEAK_TEST_DURATION      Test duration in seconds (default 1200 = 20 min)
    LEAK_TEST_RPM           Requests per minute (default 60)
    LEAK_TEST_AUDIO_DIR     Directory with .wav files (optional, uses synthetic if empty)
    LEAK_TEST_AUDIO_DUR     Synthetic audio duration in seconds (default 60)
    LEAK_TEST_VRAM_POLL     VRAM sample interval in seconds (default 10)
    LEAK_TEST_HEADROOM_PCT  Max allowed VRAM % (default 85)
    LEAK_TEST_SLOPE_THRESH  Max VRAM slope MiB/min before FAIL (default 50.0)
    LEAK_TEST_COOLDOWN      Seconds to wait after load for VRAM to settle (default 30)
"""

import http.client
import io
import math
import os
import struct
import subprocess
import sys
import threading
import time
import wave
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

PARAKEET_URL = os.getenv("PARAKEET_URL", "http://127.0.0.1:8080")
TEST_DURATION = int(os.getenv("LEAK_TEST_DURATION", "1200"))
TARGET_RPM = int(os.getenv("LEAK_TEST_RPM", "60"))
AUDIO_DIR = os.getenv("LEAK_TEST_AUDIO_DIR", "")
AUDIO_DUR = float(os.getenv("LEAK_TEST_AUDIO_DUR", "60"))
VRAM_POLL = float(os.getenv("LEAK_TEST_VRAM_POLL", "10"))
HEADROOM_PCT = float(os.getenv("LEAK_TEST_HEADROOM_PCT", "85"))
SLOPE_THRESH = float(os.getenv("LEAK_TEST_SLOPE_THRESH", "50.0"))
COOLDOWN = int(os.getenv("LEAK_TEST_COOLDOWN", "30"))


def _make_conn(timeout: int) -> http.client.HTTPConnection:
    parsed = urlparse(PARAKEET_URL)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port
    if port is None:
        return http.client.HTTPConnection(host, timeout=timeout)
    return http.client.HTTPConnection(host, port, timeout=timeout)


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


def get_process_rss_mib() -> Optional[float]:
    """Query parakeet /metrics for process_resident_memory_bytes as fallback."""
    try:
        conn = _make_conn(5)
        conn.request("GET", "/metrics/")
        resp = conn.getresponse()
        body = resp.read().decode()
        conn.close()
        for line in body.split("\n"):
            if line.startswith("process_resident_memory_bytes "):
                return float(line.split()[1]) / (1024 * 1024)
    except Exception:
        pass
    return None


def get_metrics() -> Dict[str, float]:
    try:
        conn = _make_conn(5)
        conn.request("GET", "/metrics/")
        resp = conn.getresponse()
        body = resp.read().decode()
        conn.close()
        metrics: Dict[str, float] = {}
        for line in body.split("\n"):
            if line.startswith("parakeet_gpu_oom_total "):
                metrics["oom"] = float(line.split()[1])
            elif line.startswith("parakeet_batch_pending_requests "):
                metrics["pending"] = float(line.split()[1])
            elif line.startswith("parakeet_active_batch_requests "):
                metrics["active"] = float(line.split()[1])
        return metrics
    except Exception:
        return {}


def make_wav(duration_s: float, sample_rate: int = 16000) -> bytes:
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
            val += 0.1 * math.sin(2 * math.pi * 800 * t)
            val *= 0.8 + 0.2 * math.sin(2 * math.pi * 3 * t)
            samples.append(int(val * 16000))
        w.writeframes(struct.pack("<" + "h" * n_samples, *samples))
    return buf.getvalue()


def load_audio_files(audio_dir: str) -> List[Dict[str, Any]]:
    files: List[Dict[str, Any]] = []
    if not audio_dir or not os.path.isdir(audio_dir):
        return files
    for name in sorted(os.listdir(audio_dir)):
        if not name.endswith('.wav'):
            continue
        path = os.path.join(audio_dir, name)
        with wave.open(path) as wf:
            dur = wf.getnframes() / wf.getframerate()
        with open(path, 'rb') as f:
            data = f.read()
        files.append({'name': name, 'data': data, 'duration_s': dur})
    return files


def send_request(wav_bytes: bytes, request_id: int, filename: str = "test.wav") -> Dict[str, Any]:
    boundary = f"----LeakTest{request_id}"
    body = b"".join(
        [
            f"--{boundary}\r\n".encode(),
            f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'.encode(),
            b"Content-Type: audio/wav\r\n\r\n",
            wav_bytes,
            f"\r\n--{boundary}--\r\n".encode(),
        ]
    )
    conn = _make_conn(600)
    t0 = time.time()
    try:
        conn.request(
            "POST",
            "/v2/transcribe",
            body=body,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        )
        resp = conn.getresponse()
        status = resp.status
        resp.read()
        conn.close()
        return {"id": request_id, "status": status, "elapsed": time.time() - t0, "error": None}
    except Exception as e:
        return {"id": request_id, "status": 0, "elapsed": time.time() - t0, "error": str(e)}


def linear_regression(times: List[float], values: List[float]) -> Tuple[float, float, float]:
    """Simple least-squares linear regression. Returns (slope, intercept, r_squared)."""
    n = len(times)
    if n < 3:
        return 0.0, 0.0, 0.0
    sum_x = sum(times)
    sum_y = sum(values)
    sum_xy = sum(t * v for t, v in zip(times, values))
    sum_x2 = sum(t * t for t in times)

    denom = n * sum_x2 - sum_x * sum_x
    if denom == 0:
        return 0.0, 0.0, 0.0
    slope = (n * sum_xy - sum_x * sum_y) / denom
    intercept = (sum_y - slope * sum_x) / n

    ss_res = sum((v - (slope * t + intercept)) ** 2 for t, v in zip(times, values))
    ss_tot = sum((v - sum_y / n) ** 2 for v in values)
    r_squared = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0.0

    return slope, intercept, r_squared


def main() -> int:
    print("=" * 74)
    print("Parakeet Sustained VRAM Leak Test")
    print("=" * 74)

    # Health check
    try:
        conn = _make_conn(5)
        conn.request("GET", "/health")
        resp = conn.getresponse()
        health = resp.read().decode()
        conn.close()
        print(f"Server: {PARAKEET_URL}")
        print(f"Health: {health}")
    except Exception as e:
        print(f"Health check failed: {e}")
        return 2

    # GPU baseline
    use_nvidia_smi = True
    baseline_used, gpu_total = get_gpu_memory()
    if baseline_used is not None and gpu_total is not None:
        print(f"GPU: {baseline_used:.0f}/{gpu_total:.0f} MiB ({baseline_used / gpu_total * 100:.1f}%)")
    else:
        use_nvidia_smi = False
        baseline_used = get_process_rss_mib()
        gpu_total = 0.0
        if baseline_used is not None:
            print(f"GPU: nvidia-smi not available — using process RSS as proxy")
            print(f"  Baseline RSS: {baseline_used:.0f} MiB")
        else:
            print("GPU: no memory monitoring available (neither nvidia-smi nor /metrics)")

    # Load audio
    audio_files = load_audio_files(AUDIO_DIR)
    if audio_files:
        total_dur = sum(a['duration_s'] for a in audio_files)
        print(
            f"Audio: {len(audio_files)} files from {AUDIO_DIR} "
            f"({total_dur:.0f}s total, avg {total_dur / len(audio_files):.0f}s)"
        )
    else:
        wav_data = make_wav(AUDIO_DUR)
        synth: Dict[str, Any] = {'name': f'synthetic_{AUDIO_DUR:.0f}s.wav', 'data': wav_data, 'duration_s': AUDIO_DUR}
        audio_files = [synth]
        print(f"Audio: synthetic {AUDIO_DUR:.0f}s WAV (set LEAK_TEST_AUDIO_DIR for real audio)")

    interval = 60.0 / TARGET_RPM
    initial_metrics = get_metrics()
    initial_oom = initial_metrics.get("oom", 0)

    print(f"\nConfig:")
    print(f"  Duration: {TEST_DURATION}s ({TEST_DURATION // 60} min)")
    print(f"  Rate: {TARGET_RPM} req/min (interval {interval:.2f}s)")
    print(f"  VRAM poll: every {VRAM_POLL:.0f}s")
    print(f"  Headroom gate: peak < {HEADROOM_PCT}%")
    print(f"  Slope gate: < {SLOPE_THRESH:.0f} MiB/min")
    print(f"  Cooldown: {COOLDOWN}s")
    print(f"  Initial OOM counter: {initial_oom:.0f}")

    # VRAM sampling
    vram_samples: List[Dict[str, Any]] = []
    vram_lock = threading.Lock()
    stop_vram = threading.Event()

    def vram_poller() -> None:
        while not stop_vram.is_set():
            if use_nvidia_smi:
                used, total = get_gpu_memory()
            else:
                used = get_process_rss_mib()
                total = 0.0
            if used is not None and total is not None:
                with vram_lock:
                    vram_samples.append(
                        {
                            "time": time.monotonic(),
                            "elapsed_s": 0.0,
                            "used_mib": used,
                            "total_mib": float(total),
                            "pct": (used / total * 100) if total > 0 else 0.0,
                        }
                    )
            stop_vram.wait(VRAM_POLL)

    # Results tracking
    results_lock = threading.Lock()
    results: List[Dict[str, Any]] = []

    def fire_request(req_id: int) -> None:
        import random

        audio = random.choice(audio_files)
        result = send_request(audio['data'], req_id, audio['name'])
        with results_lock:
            results.append(result)

    # Start memory monitoring
    vram_thread = threading.Thread(target=vram_poller, daemon=True)
    vram_thread.start()

    mem_col = "VRAM" if use_nvidia_smi else "RSS"
    print(
        f"\n{'Time':>6s}  {'Sent':>5s}  {'Done':>5s}  {'OK':>4s}  {'Fail':>4s}  "
        f"{mem_col:>8s}  {mem_col + 'pk':>8s}  {'OOMs':>5s}"
    )
    print("-" * 65)

    start_mono = time.monotonic()
    pool = ThreadPoolExecutor(max_workers=256)
    request_id = 0
    last_report = -1

    try:
        while time.monotonic() - start_mono < TEST_DURATION:
            request_id += 1
            pool.submit(fire_request, request_id)

            elapsed = time.monotonic() - start_mono
            report_idx = int(elapsed) // int(VRAM_POLL)

            if report_idx > last_report:
                last_report = report_idx
                metrics = get_metrics()
                current_oom = metrics.get("oom", 0) - initial_oom
                if use_nvidia_smi:
                    cur_used, _ = get_gpu_memory()
                else:
                    cur_used = get_process_rss_mib()

                with vram_lock:
                    peak_vram = max((s["used_mib"] for s in vram_samples), default=0)
                with results_lock:
                    done = len(results)
                    ok = sum(1 for r in results if r["status"] == 200)
                    fail = done - ok

                vram_str = f"{cur_used:.0f}" if cur_used else "N/A"
                peak_str = f"{peak_vram:.0f}" if peak_vram else "N/A"

                print(
                    f"  {elapsed:5.0f}s  {request_id:>5d}  {done:>5d}  {ok:>4d}  "
                    f"{fail:>4d}  {vram_str:>7s}  {peak_str:>7s}  {int(current_oom):>5d}",
                    flush=True,
                )

                if current_oom >= 5:
                    print(f"\n  OOM CASCADE: {int(current_oom)} OOMs. Stopping early.", flush=True)
                    break

            next_send = start_mono + request_id * interval
            wait = next_send - time.monotonic()
            if wait > 0:
                time.sleep(wait)

    except KeyboardInterrupt:
        print("\nInterrupted.", flush=True)

    load_elapsed = time.monotonic() - start_mono
    submitted = request_id
    print(
        f"\nLoad phase complete: {submitted} sent in {load_elapsed:.0f}s. " f"Cooling down {COOLDOWN}s...", flush=True
    )

    # Cooldown: let memory settle
    time.sleep(COOLDOWN)
    stop_vram.set()
    vram_thread.join(timeout=5)

    pool.shutdown(wait=False)

    # Final measurements
    if use_nvidia_smi:
        final_used, _ = get_gpu_memory()
    else:
        final_used = get_process_rss_mib()
    final_metrics = get_metrics()
    final_oom = final_metrics.get("oom", 0) - initial_oom

    with results_lock:
        done = len(results)
        ok = sum(1 for r in results if r["status"] == 200)
        fail = done - ok
        latencies = [r["elapsed"] for r in results if r["status"] == 200]

    # Analyze VRAM samples
    with vram_lock:
        for s in vram_samples:
            s["elapsed_s"] = s["time"] - start_mono

    # Filter to samples during the load phase only (ignore warmup/cooldown)
    load_samples = [s for s in vram_samples if 30 < s["elapsed_s"] < load_elapsed]

    if load_samples:
        times_min = [s["elapsed_s"] / 60.0 for s in load_samples]
        values_mib = [s["used_mib"] for s in load_samples]
        slope, intercept, r_squared = linear_regression(times_min, values_mib)
        peak_pct = max(s["pct"] for s in vram_samples)
        peak_mib = max(s["used_mib"] for s in vram_samples)
    else:
        slope, intercept, r_squared = 0.0, 0.0, 0.0
        peak_pct = 0.0
        peak_mib = 0.0

    # Verdicts
    oom_pass = final_oom == 0
    headroom_pass = peak_pct < HEADROOM_PCT if peak_pct > 0 else True
    slope_pass = slope < SLOPE_THRESH
    cooldown_pass = True
    recovery_pct = 0.0
    if baseline_used and final_used:
        recovery_pct = (final_used - baseline_used) / baseline_used * 100
        cooldown_pass = recovery_pct < 20

    all_pass = oom_pass and headroom_pass and slope_pass and cooldown_pass

    # Report
    print("\n" + "=" * 74)
    print("VRAM LEAK TEST RESULTS")
    print("=" * 74)

    print(
        f"\nLoad: {submitted} requests in {load_elapsed:.0f}s "
        f"({submitted / (load_elapsed / 60):.0f} req/min effective)"
    )
    print(f"Completed: {done} ({ok} OK, {fail} failed)")
    if latencies:
        sl = sorted(latencies)
        print(
            f"Latency: avg={sum(sl) / len(sl):.1f}s, p50={sl[len(sl) // 2]:.1f}s, "
            f"p95={sl[int(len(sl) * 0.95)]:.1f}s, max={max(sl):.1f}s"
        )

    mem_label = "VRAM" if use_nvidia_smi else "RSS (proxy)"
    print(f"\n{mem_label} Analysis ({len(load_samples)} samples during load):")
    if baseline_used:
        print(f"  Baseline: {baseline_used:.0f} MiB")
    print(f"  Peak: {peak_mib:.0f} MiB ({peak_pct:.1f}%)")
    if final_used:
        print(f"  After cooldown: {final_used:.0f} MiB")
    print(f"  Slope: {slope:+.1f} MiB/min (R²={r_squared:.3f})")
    if slope > 0 and load_elapsed > 60:
        projected_20m = intercept + slope * 20
        print(f"  Projected at 20 min: {projected_20m:.0f} MiB")

    print(f"\nGates:")
    print(f"  OOMs:     {int(final_oom):>3d}     {'PASS' if oom_pass else 'FAIL'} (gate: 0)")
    print(f"  Peak:     {peak_pct:>5.1f}%   {'PASS' if headroom_pass else 'FAIL'} " f"(gate: <{HEADROOM_PCT:.0f}%)")
    print(f"  Slope:    {slope:>+6.1f}   {'PASS' if slope_pass else 'FAIL'} " f"(gate: <{SLOPE_THRESH:.0f} MiB/min)")
    if baseline_used and final_used:
        print(
            f"  Recovery: {recovery_pct:>+5.1f}%  {'PASS' if cooldown_pass else 'FAIL'} " f"(gate: <20% above baseline)"
        )

    print(f"\n{'*** PASS ***' if all_pass else '*** FAIL ***'}")

    if not all_pass:
        print("\nFailed gates indicate a VRAM leak or excessive memory use.")
        if not slope_pass:
            print(f"  VRAM grew at {slope:+.1f} MiB/min — monotonic accumulation detected.")
            print("  This matches the prod OOM pattern (5.7→22 GiB in 22 min).")
        if not headroom_pass:
            print(f"  Peak VRAM {peak_pct:.1f}% exceeds {HEADROOM_PCT:.0f}% headroom.")
        if not cooldown_pass:
            print(f"  VRAM did not return to baseline after {COOLDOWN}s cooldown.")
        if not oom_pass:
            print(f"  {int(final_oom)} OOM events detected.")

    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
