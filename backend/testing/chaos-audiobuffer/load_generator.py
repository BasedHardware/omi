#!/usr/bin/env python3
"""
Load generator for audiobuffer leak chaos test.

Sends continuous header-101 audio chunks and polls /debug/buffers to track
audiobuffer + trigger_audiobuffer lengths over time.
"""

import argparse
import asyncio
import json
import struct
import time
import urllib.request

import websockets


async def send_audio(host, port, duration, chunk_size, interval, stats):
    uri = f"ws://{host}:{port}/v1/trigger/listen?uid=chaos-audio&sample_rate=8000"
    end_time = time.time() + duration
    sent = 0

    async with websockets.connect(uri, close_timeout=2) as ws:
        # Set conversation ID first
        conv_id = "conv-audio-chaos"
        data = struct.pack("<I", 103) + conv_id.encode("utf-8")
        await ws.send(data)

        audio_data = bytes(chunk_size)
        while time.time() < end_time:
            timestamp = time.time()
            payload = struct.pack("<I", 101) + struct.pack("d", timestamp) + audio_data
            await ws.send(payload)
            sent += 1
            stats["sent_chunks"] = sent
            await asyncio.sleep(interval)


async def monitor_buffers(host, port, duration, stats):
    end_time = time.time() + duration
    samples = 0

    while time.time() < end_time:
        await asyncio.sleep(2)
        try:
            url = f"http://{host}:{port}/debug/buffers"
            with urllib.request.urlopen(url, timeout=3) as resp:
                data = json.loads(resp.read().decode())
        except Exception:
            continue

        ts = time.time()
        ab = int(data.get("audiobuffer_len", 0))
        tab = int(data.get("trigger_audiobuffer_len", 0))
        chunks = int(data.get("audio_chunks", 0))

        stats["ts_series"].append(ts)
        stats["ab_series"].append(ab)
        stats["tab_series"].append(tab)
        stats["max_audiobuffer_len"] = max(stats["max_audiobuffer_len"], ab)
        stats["max_trigger_audiobuffer_len"] = max(stats["max_trigger_audiobuffer_len"], tab)
        samples += 1

        elapsed = int(ts - stats["start_ts"])
        print(f"  [{elapsed:3d}s] audiobuffer={ab}  trigger_audiobuffer={tab}  chunks={chunks}")

    stats["samples"] = samples


def slope_bytes_per_sec(ts_series, size_series):
    """Least-squares slope (bytes/sec)."""
    n = len(ts_series)
    if n < 3:
        return 0.0
    t0 = ts_series[0]
    xs = [t - t0 for t in ts_series]
    ys = list(size_series)
    x_mean = sum(xs) / n
    y_mean = sum(ys) / n
    num = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, ys))
    den = sum((x - x_mean) ** 2 for x in xs)
    if den == 0:
        return 0.0
    return num / den


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=18090)
    parser.add_argument("--duration", type=int, default=30)
    parser.add_argument("--chunk-size", type=int, default=16000)
    parser.add_argument("--interval", type=float, default=0.05)
    args = parser.parse_args()

    stats = {
        "start_ts": time.time(),
        "sent_chunks": 0,
        "samples": 0,
        "max_audiobuffer_len": 0,
        "max_trigger_audiobuffer_len": 0,
        "ts_series": [],
        "ab_series": [],
        "tab_series": [],
    }

    await asyncio.gather(
        send_audio(args.host, args.port, args.duration, args.chunk_size, args.interval, stats),
        monitor_buffers(args.host, args.port, args.duration, stats),
    )

    slope_ab = slope_bytes_per_sec(stats["ts_series"], stats["ab_series"])
    slope_tab = slope_bytes_per_sec(stats["ts_series"], stats["tab_series"])

    result = {
        "sent_chunks": stats["sent_chunks"],
        "duration_sec": args.duration,
        "chunk_size": args.chunk_size,
        "interval_sec": args.interval,
        "samples": stats["samples"],
        "max_audiobuffer_len": stats["max_audiobuffer_len"],
        "max_trigger_audiobuffer_len": stats["max_trigger_audiobuffer_len"],
        "slope_audiobuffer_bps": round(slope_ab, 2),
        "slope_trigger_audiobuffer_bps": round(slope_tab, 2),
    }

    print(f"RESULT: {json.dumps(result)}")


if __name__ == "__main__":
    asyncio.run(main())
