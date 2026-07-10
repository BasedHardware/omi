"""
VRAM stress test for parakeet under concurrent batch load.

Catches OOM regressions by monitoring GPU memory during concurrent
requests with varying audio durations.  The Phase 2 OOM (PR #8428)
happened because torch.compile was disabled, tripling VRAM under
batch load.  This test gates on peak VRAM staying below a safe
threshold for the GPU.

Requires:
  - Parakeet server running on localhost:8080 (or PARAKEET_URL)
  - GPU with nvidia-smi available
  - VRAM_HEADROOM_PCT: max allowed VRAM usage as % of total (default 85)

Usage:
    python -m pytest tests/container/test_parakeet_vram_stress.py -v -s

Env vars:
    PARAKEET_URL           Server URL (default http://127.0.0.1:8080)
    VRAM_HEADROOM_PCT      Max VRAM usage percent (default 85)
    VRAM_STRESS_CONCURRENCY  Concurrent requests per round (default 4)
    VRAM_STRESS_DURATIONS  Comma-separated audio durations in seconds
                           (default "30,60,120,300")
    VRAM_POLL_INTERVAL     Seconds between VRAM samples (default 0.5)
"""

import http.client
import io
import json
import math
import os
import struct
import subprocess
import threading
import time
import wave
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse

import pytest

PARAKEET_URL = os.getenv("PARAKEET_URL", "http://127.0.0.1:8080")
VRAM_HEADROOM_PCT = float(os.getenv("VRAM_HEADROOM_PCT", "85"))
VRAM_STRESS_CONCURRENCY = int(os.getenv("VRAM_STRESS_CONCURRENCY", "4"))
VRAM_STRESS_DURATIONS = [float(d.strip()) for d in os.getenv("VRAM_STRESS_DURATIONS", "30,60,120,300").split(",")]
VRAM_POLL_INTERVAL = float(os.getenv("VRAM_POLL_INTERVAL", "0.5"))


def _get_gpu_memory():
    """Query nvidia-smi for GPU memory usage.

    Returns (used_mib, total_mib) or (None, None) if unavailable.
    """
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


def _get_vram_from_metrics():
    """Query parakeet /metrics for process_resident_memory_bytes as fallback."""
    try:
        parsed = urlparse(PARAKEET_URL)
        conn = http.client.HTTPConnection(parsed.hostname, parsed.port, timeout=5)
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


class VRAMMonitor:
    """Background thread that samples GPU VRAM at regular intervals."""

    def __init__(self, interval=0.5):
        self._interval = interval
        self._samples = []
        self._stop = threading.Event()
        self._thread = None

    def start(self):
        self._samples = []
        self._stop.clear()
        self._thread = threading.Thread(target=self._poll, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)

    def _poll(self):
        while not self._stop.is_set():
            used, total = _get_gpu_memory()
            if used is not None:
                self._samples.append(
                    {
                        "time": time.monotonic(),
                        "used_mib": used,
                        "total_mib": total,
                        "pct": (used / total * 100) if total > 0 else 0,
                    }
                )
            self._stop.wait(self._interval)

    @property
    def peak_used_mib(self):
        return max((s["used_mib"] for s in self._samples), default=0)

    @property
    def peak_pct(self):
        return max((s["pct"] for s in self._samples), default=0)

    @property
    def total_mib(self):
        if self._samples:
            return self._samples[0]["total_mib"]
        return 0

    @property
    def sample_count(self):
        return len(self._samples)


def _make_speech_wav(duration_s, sample_rate=16000):
    """Generate a WAV with speech-like harmonics."""
    n_samples = int(duration_s * sample_rate)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        samples = []
        for i in range(n_samples):
            t = i / sample_rate
            val = 0.3 * math.sin(2 * math.pi * 250 * t)
            val += 0.2 * math.sin(2 * math.pi * 440 * t)
            val += 0.1 * math.sin(2 * math.pi * 800 * t)
            val *= 0.8 + 0.2 * math.sin(2 * math.pi * 3 * t)
            samples.append(int(val * 16000))
        w.writeframes(struct.pack("<" + "h" * n_samples, *samples))
    return buf.getvalue()


def _send_request(wav_bytes, request_id=0, timeout=300):
    """Send a /v2/transcribe request."""
    parsed = urlparse(PARAKEET_URL)
    boundary = f"----VRAMStress{request_id}"

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
        return {"request_id": request_id, "status": status, "body": data[:2000], "error": None}
    except Exception as e:
        return {"request_id": request_id, "status": 0, "body": b"", "error": str(e)}


def _get_oom_count():
    """Get current OOM counter from /metrics."""
    try:
        parsed = urlparse(PARAKEET_URL)
        conn = http.client.HTTPConnection(parsed.hostname, parsed.port, timeout=5)
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


class TestVRAMStress:
    """VRAM stress tests that monitor GPU memory under concurrent load.

    These tests catch OOM regressions that purely functional tests miss
    — like the torch.compile VRAM tripling from PR #8428 Phase 2.
    """

    @pytest.fixture(scope="class")
    def gpu_available(self):
        used, total = _get_gpu_memory()
        if used is None:
            pytest.skip("nvidia-smi not available — cannot monitor VRAM")
        return total

    def test_vram_under_concurrent_short_audio(self, gpu_available):
        """Concurrent requests with short audio (30s) should stay well under VRAM limit.

        This is the baseline — if this fails, the GPU is already overloaded.
        """
        duration = 30.0
        cc = VRAM_STRESS_CONCURRENCY
        wav_data = _make_speech_wav(duration)

        monitor = VRAMMonitor(VRAM_POLL_INTERVAL)
        oom_before = _get_oom_count()
        baseline_used, baseline_total = _get_gpu_memory()

        print(
            f"\n  Baseline VRAM: {baseline_used:.0f}/{baseline_total:.0f} MiB "
            f"({baseline_used/baseline_total*100:.1f}%)"
        )
        print(f"  Sending {cc} concurrent requests with {duration}s audio...")

        monitor.start()
        with ThreadPoolExecutor(max_workers=cc) as pool:
            futures = [pool.submit(_send_request, wav_data, i) for i in range(cc)]
            results = [f.result() for f in as_completed(futures)]
        monitor.stop()

        oom_after = _get_oom_count()
        new_ooms = oom_after - oom_before

        successes = sum(1 for r in results if r["status"] == 200)
        print(f"  Results: {successes}/{cc} succeeded")
        print(
            f"  Peak VRAM: {monitor.peak_used_mib:.0f}/{monitor.total_mib:.0f} MiB "
            f"({monitor.peak_pct:.1f}%) — {monitor.sample_count} samples"
        )
        print(f"  OOMs during test: {new_ooms}")

        assert new_ooms == 0, f"{new_ooms} OOM events during 30s audio stress test"
        assert monitor.peak_pct < VRAM_HEADROOM_PCT, (
            f"Peak VRAM {monitor.peak_pct:.1f}% exceeds {VRAM_HEADROOM_PCT}% " f"threshold with {cc}x {duration}s audio"
        )

    def test_vram_scaling_with_audio_duration(self, gpu_available):
        """VRAM should scale predictably as audio duration increases.

        Sends concurrent requests at each duration tier and records peak
        VRAM.  Full attention uses O(T^2) VRAM so longer audio should
        increase VRAM substantially.  Fails if any tier exceeds the
        headroom threshold.
        """
        cc = VRAM_STRESS_CONCURRENCY
        results_by_duration = {}

        for duration in VRAM_STRESS_DURATIONS:
            wav_data = _make_speech_wav(duration)

            monitor = VRAMMonitor(VRAM_POLL_INTERVAL)
            oom_before = _get_oom_count()

            print(f"\n  Duration tier: {duration}s @ cc={cc}")
            monitor.start()
            with ThreadPoolExecutor(max_workers=cc) as pool:
                futures = [pool.submit(_send_request, wav_data, i, timeout=600) for i in range(cc)]
                results = [f.result() for f in as_completed(futures)]
            monitor.stop()

            oom_after = _get_oom_count()
            new_ooms = oom_after - oom_before
            successes = sum(1 for r in results if r["status"] == 200)
            errors_500 = sum(1 for r in results if r["status"] == 500)

            results_by_duration[duration] = {
                "peak_mib": monitor.peak_used_mib,
                "peak_pct": monitor.peak_pct,
                "successes": successes,
                "errors_500": errors_500,
                "ooms": new_ooms,
                "samples": monitor.sample_count,
            }

            print(f"  {successes}/{cc} succeeded, {errors_500} x 500, {new_ooms} OOMs")
            print(f"  Peak VRAM: {monitor.peak_used_mib:.0f} MiB ({monitor.peak_pct:.1f}%)")

        print("\n  === VRAM Scaling Summary ===")
        print(f"  {'Duration':>8s}  {'Peak MiB':>9s}  {'Peak %':>7s}  {'OK':>3s}  {'OOM':>4s}")
        for dur in VRAM_STRESS_DURATIONS:
            r = results_by_duration[dur]
            print(
                f"  {dur:>7.0f}s  {r['peak_mib']:>8.0f}  {r['peak_pct']:>6.1f}%  "
                f"{r['successes']:>3d}  {r['ooms']:>4.0f}"
            )

        for dur, r in results_by_duration.items():
            assert r["ooms"] == 0, (
                f"OOM at {dur}s audio with cc={cc}: {r['ooms']} OOMs, "
                f"peak VRAM {r['peak_mib']:.0f} MiB ({r['peak_pct']:.1f}%)"
            )
            assert r["peak_pct"] < VRAM_HEADROOM_PCT, (
                f"Peak VRAM {r['peak_pct']:.1f}% exceeds {VRAM_HEADROOM_PCT}% " f"at {dur}s audio with cc={cc}"
            )

    def test_no_oom_at_production_pattern(self, gpu_available):
        """Simulate production audio pattern: mixed durations concurrent.

        Omi's p50=34s, p95=59s.  Sends a mix of short and medium audio
        concurrently to verify no OOM under realistic workload.
        """
        cc = VRAM_STRESS_CONCURRENCY
        durations = [10.0, 30.0, 45.0, 60.0]
        wav_data_list = [_make_speech_wav(d) for d in durations]

        monitor = VRAMMonitor(VRAM_POLL_INTERVAL)
        oom_before = _get_oom_count()

        print(f"\n  Production pattern: {durations} @ cc={cc}")
        monitor.start()
        with ThreadPoolExecutor(max_workers=cc) as pool:
            futures = [pool.submit(_send_request, wav_data_list[i], i) for i in range(len(wav_data_list))]
            results = [f.result() for f in as_completed(futures)]
        monitor.stop()

        oom_after = _get_oom_count()
        new_ooms = oom_after - oom_before
        successes = sum(1 for r in results if r["status"] == 200)

        print(f"  {successes}/{len(results)} succeeded")
        print(f"  Peak VRAM: {monitor.peak_used_mib:.0f} MiB ({monitor.peak_pct:.1f}%)")
        print(f"  OOMs: {new_ooms}")

        assert new_ooms == 0, f"OOM under production-like load: {new_ooms} OOMs"
        assert successes == len(results), f"Only {successes}/{len(results)} succeeded under production pattern"


VRAM_SUSTAINED_DURATION = int(os.getenv("VRAM_SUSTAINED_DURATION", "300"))
VRAM_SUSTAINED_RPM = int(os.getenv("VRAM_SUSTAINED_RPM", "30"))
VRAM_SLOPE_THRESHOLD = float(os.getenv("VRAM_SLOPE_THRESHOLD", "50.0"))


def _linear_regression(times, values):
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


class TestVRAMSustainedLeak:
    """Sustained load test that detects monotonic VRAM accumulation.

    The Phase 2 OOM (PR #8428) showed VRAM ratcheting from 5.7→22 GiB
    over 22 minutes.  Burst tests missed it because VRAM releases
    between batches.  This test runs sustained load and checks the
    VRAM slope — a positive slope above threshold means a leak.

    Default: 5 minutes at 30 req/min (override via env vars for longer runs).
    """

    @pytest.fixture(scope="class")
    def gpu_available(self):
        used, total = _get_gpu_memory()
        if used is None:
            pytest.skip("nvidia-smi not available — cannot monitor VRAM")
        return total

    def test_no_vram_leak_under_sustained_load(self, gpu_available):
        """VRAM must not monotonically increase under sustained load."""
        duration = VRAM_SUSTAINED_DURATION
        rpm = VRAM_SUSTAINED_RPM
        interval = 60.0 / rpm
        cc = min(rpm, 64)

        wav_data = _make_speech_wav(60.0)
        baseline_used, total = _get_gpu_memory()
        oom_before = _get_oom_count()

        print(f"\n  Sustained leak test: {duration}s at {rpm} req/min")
        print(f"  Baseline VRAM: {baseline_used:.0f}/{total:.0f} MiB")

        monitor = VRAMMonitor(2.0)
        monitor.start()
        start = time.monotonic()
        results = []
        results_lock = threading.Lock()

        def fire(req_id):
            r = _send_request(wav_data, req_id, timeout=300)
            with results_lock:
                results.append(r)

        pool = ThreadPoolExecutor(max_workers=cc)
        req_id = 0
        try:
            while time.monotonic() - start < duration:
                req_id += 1
                pool.submit(fire, req_id)
                next_send = start + req_id * interval
                wait = next_send - time.monotonic()
                if wait > 0:
                    time.sleep(wait)
        except KeyboardInterrupt:
            pass

        pool.shutdown(wait=False)
        time.sleep(10)
        monitor.stop()

        oom_after = _get_oom_count()
        new_ooms = oom_after - oom_before
        final_used, _ = _get_gpu_memory()

        with results_lock:
            ok = sum(1 for r in results if r["status"] == 200)
            fail = len(results) - ok

        samples = monitor._samples
        load_samples = [s for s in samples if 30 < (s["time"] - start) < duration]

        if len(load_samples) >= 3:
            times_min = [(s["time"] - start) / 60.0 for s in load_samples]
            values_mib = [s["used_mib"] for s in load_samples]
            slope, _, r_squared = _linear_regression(times_min, values_mib)
        else:
            slope, r_squared = 0.0, 0.0

        print(f"  Sent: {req_id}, OK: {ok}, Failed: {fail}")
        print(f"  Peak VRAM: {monitor.peak_used_mib:.0f} MiB ({monitor.peak_pct:.1f}%)")
        print(f"  Final VRAM: {final_used:.0f} MiB")
        print(f"  VRAM slope: {slope:+.1f} MiB/min (R²={r_squared:.3f})")
        print(f"  OOMs: {new_ooms}")

        recovery_delta = final_used - baseline_used if final_used and baseline_used else 0

        assert new_ooms == 0, f"{new_ooms} OOM events during sustained load"
        assert slope < VRAM_SLOPE_THRESHOLD, (
            f"VRAM slope {slope:+.1f} MiB/min exceeds {VRAM_SLOPE_THRESHOLD} MiB/min — "
            f"monotonic accumulation detected (R²={r_squared:.3f})"
        )
        assert recovery_delta < 2000, (
            f"VRAM did not recover: baseline {baseline_used:.0f} → "
            f"final {final_used:.0f} MiB (+{recovery_delta:.0f})"
        )


class TestVRAMBaseline:
    """Record VRAM baseline for future comparison.

    These tests don't fail — they capture VRAM characteristics that
    can be compared across builds to detect regressions.
    """

    @pytest.fixture(scope="class")
    def gpu_available(self):
        used, total = _get_gpu_memory()
        if used is None:
            pytest.skip("nvidia-smi not available")
        return total

    def test_idle_vram_baseline(self, gpu_available):
        """Record VRAM at idle (model loaded, no inference)."""
        used, total = _get_gpu_memory()
        pct = used / total * 100

        print(f"\n  Idle VRAM: {used:.0f}/{total:.0f} MiB ({pct:.1f}%)")
        print(f"  Free for inference: {total - used:.0f} MiB")

        assert pct < 50, (
            f"Idle VRAM {pct:.1f}% is too high — model weights alone shouldn't " f"use more than 50% of {total:.0f} MiB"
        )

    def test_single_request_vram_delta(self, gpu_available):
        """Measure VRAM increase from a single 60s request."""
        baseline_used, total = _get_gpu_memory()
        wav_data = _make_speech_wav(60.0)

        monitor = VRAMMonitor(0.2)
        monitor.start()
        result = _send_request(wav_data, 0, timeout=120)
        monitor.stop()

        delta = monitor.peak_used_mib - baseline_used
        print(f"\n  Single 60s request VRAM delta: +{delta:.0f} MiB")
        print(f"  Baseline: {baseline_used:.0f} MiB → Peak: {monitor.peak_used_mib:.0f} MiB")
        print(f"  Status: {result['status']}")

        assert result["status"] == 200, f"Single request failed: {result['error']}"
