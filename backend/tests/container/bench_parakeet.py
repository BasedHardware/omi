#!/usr/bin/env python3
"""
Reusable benchmark suite for parakeet batch and streaming endpoints.

Produces structured JSON results and human-readable markdown tables.
Uses real speech audio (LibriSpeech or local WAV files) for representative
GPU scheduling behavior — RNNT processes silence 7x faster than speech.

Usage:
    # Batch only:
    python bench_parakeet.py --url http://localhost:10260 --mode batch

    # Streaming only:
    python bench_parakeet.py --url http://localhost:10260 --mode stream

    # Combined (batch + stream simultaneously):
    python bench_parakeet.py --url http://localhost:10260 --mode combined

    # Full suite:
    python bench_parakeet.py --url http://localhost:10260 --mode all

    # With custom concurrency levels:
    python bench_parakeet.py --url http://localhost:10260 --mode batch --concurrency 1,4,8,16,32

    # Save JSON report:
    python bench_parakeet.py --url http://localhost:10260 --mode all --output /tmp/bench_report.json

Environment:
    PARAKEET_URL    Override --url default (http://127.0.0.1:8080)
"""

import argparse
import asyncio
import http.client
import io
import json
import math
import os
import struct
import sys
import time
import wave
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from statistics import mean, median
from urllib.parse import urlparse

SAMPLE_RATE = 16000
CHUNK_MS = 160
CHUNK_SAMPLES = SAMPLE_RATE * CHUNK_MS // 1000
CHUNK_BYTES = CHUNK_SAMPLES * 2


def make_speech_wav(duration_s=3.0, sample_rate=16000):
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


def load_audio_files(audio_dir=None, max_files=200):
    files = []
    search_dirs = []
    if audio_dir:
        search_dirs.append(Path(audio_dir))
    search_dirs.extend(
        [
            Path(__file__).parent / "librispeech",
            Path("/tmp/stt_benchmark_audio_02"),
            Path("/tmp/LibriSpeech/test-clean"),
        ]
    )

    for d in search_dirs:
        if d.is_dir():
            wavs = sorted(d.glob("*.wav"))[:max_files]
            if wavs:
                for w in wavs:
                    with open(w, "rb") as f:
                        files.append({"path": str(w), "bytes": f.read()})
                break

    if not files:
        for path in ["/tmp/bench_speech.wav", "/tmp/speaker1.wav"]:
            if os.path.exists(path):
                with open(path, "rb") as f:
                    files.append({"path": path, "bytes": f.read()})
                break

    if not files:
        files.append({"path": "synthetic_3s", "bytes": make_speech_wav(3.0)})

    return files


def get_audio_duration(wav_bytes):
    try:
        with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
            return wf.getnframes() / wf.getframerate()
    except Exception:
        return 0.0


def wav_to_pcm16(wav_bytes):
    with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
        return wf.readframes(wf.getnframes())


# --- Batch benchmark ---


def batch_request(url, wav_bytes, endpoint="/v2/transcribe", timeout=30):
    parsed = urlparse(url)
    conn = http.client.HTTPConnection(parsed.hostname, parsed.port or 80, timeout=timeout)
    boundary = "----BenchBoundary"
    body = (
        (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="bench.wav"\r\n'
            f"Content-Type: audio/wav\r\n\r\n"
        ).encode()
        + wav_bytes
        + f"\r\n--{boundary}--\r\n".encode()
    )

    t0 = time.monotonic()
    conn.request("POST", endpoint, body=body, headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    resp = conn.getresponse()
    elapsed = time.monotonic() - t0
    status = resp.status
    resp.read()
    conn.close()
    return {"status": status, "elapsed": elapsed}


def run_batch_bench(url, audio_files, concurrency_levels, rounds=1):
    print("\n## Batch Benchmark\n")
    results = {"concurrency_sweep": [], "sustained": None}
    total_audio_dur = sum(get_audio_duration(f["bytes"]) for f in audio_files)
    avg_dur = total_audio_dur / len(audio_files) if audio_files else 0

    for c in concurrency_levels:
        latencies = []
        failures = 0

        for _ in range(rounds):
            round_results = []
            with ThreadPoolExecutor(max_workers=c) as pool:
                futures = []
                for i in range(len(audio_files)):
                    f = audio_files[i % len(audio_files)]
                    futures.append(pool.submit(batch_request, url, f["bytes"]))
                for fut in as_completed(futures):
                    r = fut.result()
                    if r["status"] == 200:
                        latencies.append(r["elapsed"])
                    else:
                        failures += 1

        if latencies:
            rps = len(latencies) / sum(latencies) * c
            rtfx = avg_dur * rps if avg_dur > 0 else 0
            p50 = sorted(latencies)[len(latencies) // 2]
            p99 = sorted(latencies)[int(len(latencies) * 0.99)]
        else:
            rps = rtfx = p50 = p99 = 0

        entry = {
            "concurrency": c,
            "rps": round(rps, 2),
            "rtfx": round(rtfx, 1),
            "p50": round(p50, 3),
            "p99": round(p99, 3),
            "failures": failures,
            "total": len(latencies) + failures,
        }
        results["concurrency_sweep"].append(entry)
        print(f"  c={c:3d}: {rps:6.2f} RPS, RTFx={rtfx:6.1f}x, p50={p50:.3f}s, p99={p99:.3f}s, fail={failures}")

    # Sustained load at highest concurrency
    c = concurrency_levels[-1]
    sustained_rounds = 4
    all_latencies = []
    sustained_failures = 0

    for _ in range(sustained_rounds):
        with ThreadPoolExecutor(max_workers=c) as pool:
            futures = [
                pool.submit(batch_request, url, audio_files[i % len(audio_files)]["bytes"])
                for i in range(len(audio_files))
            ]
            for fut in as_completed(futures):
                r = fut.result()
                if r["status"] == 200:
                    all_latencies.append(r["elapsed"])
                else:
                    sustained_failures += 1

    if all_latencies:
        sustained_rps = len(all_latencies) / sum(all_latencies) * c
        sustained_rtfx = avg_dur * sustained_rps if avg_dur > 0 else 0
    else:
        sustained_rps = sustained_rtfx = 0

    results["sustained"] = {
        "concurrency": c,
        "rounds": sustained_rounds,
        "total_files": len(all_latencies) + sustained_failures,
        "rps": round(sustained_rps, 2),
        "rtfx": round(sustained_rtfx, 1),
        "failures": sustained_failures,
    }
    print(f"\n  Sustained (c={c}, {sustained_rounds} rounds): {sustained_rps:.2f} RPS, {sustained_failures} failures")
    return results


# --- Streaming benchmark ---


async def stream_one(ws_url, pcm_bytes, label=""):
    import websockets

    t0 = time.monotonic()
    responses = []
    first_resp_t = None
    try:
        async with websockets.connect(ws_url, max_size=10 * 1024 * 1024, ping_interval=None) as ws:
            for i in range(0, len(pcm_bytes), CHUNK_BYTES):
                chunk = pcm_bytes[i : i + CHUNK_BYTES]
                await ws.send(chunk)
                await asyncio.sleep(CHUNK_MS / 1000.0 * 0.5)
                try:
                    while True:
                        msg = await asyncio.wait_for(ws.recv(), timeout=0.01)
                        resp = json.loads(msg)
                        if first_resp_t is None:
                            first_resp_t = time.monotonic() - t0
                        responses.append(resp)
                except asyncio.TimeoutError:
                    pass

            await ws.send("finalize")
            try:
                while True:
                    msg = await asyncio.wait_for(ws.recv(), timeout=5)
                    resp = json.loads(msg)
                    responses.append(resp)
                    if resp.get("status") in ("closed", "close_failed", "not_found"):
                        break
            except (asyncio.TimeoutError, Exception):
                pass

        return {
            "label": label,
            "status": "ok",
            "total_s": round(time.monotonic() - t0, 3),
            "first_resp_s": round(first_resp_t, 3) if first_resp_t else None,
            "responses": len(responses),
            "audio_s": len(pcm_bytes) / 2 / SAMPLE_RATE,
            "closed": any(r.get("status") == "closed" for r in responses),
        }
    except Exception as e:
        return {"label": label, "status": "error", "error": str(e), "total_s": round(time.monotonic() - t0, 3)}


async def run_stream_bench(url, audio_files, concurrency_levels):
    import websockets

    ws_url = url.replace("http://", "ws://").replace("https://", "wss://") + "/v4/stream?sample_rate=16000"
    print("\n## Streaming Benchmark\n")
    results = {"concurrency_sweep": []}

    pcm_data = [wav_to_pcm16(f["bytes"]) for f in audio_files[:20]]

    for c in concurrency_levels:
        tasks = []
        for i in range(c):
            pcm = pcm_data[i % len(pcm_data)]
            tasks.append(stream_one(ws_url, pcm, label=f"s{i}"))

        t0 = time.monotonic()
        stream_results = await asyncio.gather(*tasks, return_exceptions=True)
        wall_time = time.monotonic() - t0

        ok = [r for r in stream_results if isinstance(r, dict) and r.get("status") == "ok"]
        closed = [r for r in ok if r.get("closed")]
        failures = c - len(ok)
        total_audio = sum(r.get("audio_s", 0) for r in ok)
        rtfx = total_audio / wall_time if wall_time > 0 else 0
        first_latencies = [r["first_resp_s"] for r in ok if r.get("first_resp_s")]
        avg_first = mean(first_latencies) if first_latencies else 0

        entry = {
            "concurrency": c,
            "streams": len(ok),
            "closed": len(closed),
            "rtfx": round(rtfx, 1),
            "wall_s": round(wall_time, 1),
            "avg_first_resp_ms": round(avg_first * 1000),
            "failures": failures,
        }
        results["concurrency_sweep"].append(entry)
        print(
            f"  c={c:3d}: {len(ok)}/{c} ok, {len(closed)} closed, RTFx={rtfx:.1f}x, "
            f"first_resp={avg_first*1000:.0f}ms, fail={failures}"
        )

    return results


# --- Combined benchmark ---


async def run_combined_bench(url, audio_files, batch_c=16, stream_c=8):
    import websockets

    ws_url = url.replace("http://", "ws://").replace("https://", "wss://") + "/v4/stream?sample_rate=16000"
    print("\n## Combined Benchmark\n")
    print(f"  Batch: c={batch_c}, {len(audio_files)} files")
    print(f"  Stream: c={stream_c} concurrent")

    pcm_data = [wav_to_pcm16(f["bytes"]) for f in audio_files[:stream_c]]

    batch_results = []
    batch_done = asyncio.Event()

    def run_batch():
        with ThreadPoolExecutor(max_workers=batch_c) as pool:
            futures = [
                pool.submit(batch_request, url, audio_files[i % len(audio_files)]["bytes"])
                for i in range(len(audio_files))
            ]
            for fut in as_completed(futures):
                batch_results.append(fut.result())
        batch_done.set()

    stream_tasks = [stream_one(ws_url, pcm_data[i % len(pcm_data)], f"s{i}") for i in range(stream_c)]

    t0 = time.monotonic()
    import threading

    batch_thread = threading.Thread(target=run_batch, daemon=True)
    batch_thread.start()
    stream_results = await asyncio.gather(*stream_tasks, return_exceptions=True)
    batch_thread.join(timeout=120)
    wall_time = time.monotonic() - t0

    batch_ok = sum(1 for r in batch_results if r["status"] == 200)
    batch_fail = len(batch_results) - batch_ok
    batch_latencies = [r["elapsed"] for r in batch_results if r["status"] == 200]
    batch_rps = len(batch_latencies) / sum(batch_latencies) * batch_c if batch_latencies else 0

    stream_ok = [r for r in stream_results if isinstance(r, dict) and r.get("status") == "ok"]
    stream_fail = stream_c - len(stream_ok)

    results = {
        "batch": {"ok": batch_ok, "failures": batch_fail, "rps": round(batch_rps, 2)},
        "stream": {"ok": len(stream_ok), "failures": stream_fail},
        "wall_s": round(wall_time, 1),
    }

    print(f"  Batch:  {batch_ok}/{len(batch_results)} ok, RPS={batch_rps:.2f}, {batch_fail} failures")
    print(f"  Stream: {len(stream_ok)}/{stream_c} ok, {stream_fail} failures")
    print(f"  Wall:   {wall_time:.1f}s")
    return results


# --- Main ---


def main():
    parser = argparse.ArgumentParser(description="Parakeet ASR Benchmark Suite")
    parser.add_argument("--url", default=os.getenv("PARAKEET_URL", "http://127.0.0.1:8080"))
    parser.add_argument("--mode", choices=["batch", "stream", "combined", "all"], default="all")
    parser.add_argument("--concurrency", default="1,4,8,16,32", help="Comma-separated concurrency levels")
    parser.add_argument("--audio-dir", default=None, help="Directory with WAV files")
    parser.add_argument("--max-files", type=int, default=200)
    parser.add_argument("--output", default=None, help="Save JSON report to file")
    args = parser.parse_args()

    concurrency = [int(x) for x in args.concurrency.split(",")]
    audio_files = load_audio_files(args.audio_dir, args.max_files)

    print(f"=== Parakeet Benchmark Suite ===")
    print(f"Server: {args.url}")
    print(f"Mode: {args.mode}")
    print(f"Audio files: {len(audio_files)}")
    print(f"Concurrency levels: {concurrency}")

    report = {
        "url": args.url,
        "mode": args.mode,
        "audio_files": len(audio_files),
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }

    if args.mode in ("batch", "all"):
        report["batch"] = run_batch_bench(args.url, audio_files, concurrency)

    if args.mode in ("stream", "all"):
        report["stream"] = asyncio.run(run_stream_bench(args.url, audio_files, concurrency))

    if args.mode in ("combined", "all"):
        report["combined"] = asyncio.run(run_combined_bench(args.url, audio_files))

    if args.output:
        with open(args.output, "w") as f:
            json.dump(report, f, indent=2)
        print(f"\nReport saved to {args.output}")

    print("\n=== Done ===")


if __name__ == "__main__":
    main()
