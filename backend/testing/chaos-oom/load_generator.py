#!/usr/bin/env python3
"""
Load generator for chaos OOM test.

Drives both leak patterns against the pusher WebSocket endpoint:
  Leak 1: header-104 (process_conversation) — fire-and-forget tasks hold ws refs
  Leak 2: header-101 (audio bytes) — unbounded queue growth under backpressure

Improvements:
  #6: RSS time series + slope analysis (linear regression)
  #7: Disconnect/reconnect simulation (--disconnect-interval flag)
"""

import argparse
import asyncio
import json
import struct
import sys
import time

import websockets


async def leak1_client(host, port, client_id, duration, stats, disconnect_interval=0):
    """
    Leak 1: Send header-104 (process_conversation) requests rapidly.
    Each triggers safe_create_task(_process_conversation_task(...)) which sleeps 5s
    holding a websocket reference. Tasks accumulate because they're never cancelled.
    """
    uri = f"ws://{host}:{port}/v1/trigger/listen?uid=chaos-user-{client_id}&sample_rate=8000"
    end_time = time.time() + duration
    sent = 0

    while time.time() < end_time:
        try:
            async with websockets.connect(uri, close_timeout=2) as ws:
                # First send a conversation ID (header 103)
                conv_id = f"conv-leak1-{client_id}"
                data = struct.pack('<I', 103) + conv_id.encode('utf-8')
                await ws.send(data)

                conn_start = time.time()

                while time.time() < end_time:
                    # Improvement #7: Disconnect/reconnect after interval
                    if disconnect_interval and (time.time() - conn_start) >= disconnect_interval:
                        break  # close connection, outer loop reconnects

                    # Send process_conversation request (header 104)
                    payload = json.dumps(
                        {
                            'conversation_id': f"conv-{client_id}-{sent}",
                            'language': 'en',
                        }
                    ).encode('utf-8')
                    data = struct.pack('<I', 104) + payload
                    await ws.send(data)
                    sent += 1
                    stats['leak1_sent'] += 1

                    # 10 requests/sec per client
                    await asyncio.sleep(0.1)

        except Exception as e:
            stats['errors'] += 1
            if 'connect' not in str(e).lower():
                print(f"  leak1 client {client_id}: {e}", file=sys.stderr)

        # If not using disconnect_interval, don't reconnect
        if not disconnect_interval:
            break


async def leak2_client(host, port, client_id, duration, stats, disconnect_interval=0):
    """
    Leak 2: Send header-101 (audio bytes) at high rate.
    The slow mock consumers can't keep up, so the List[dict] queues grow without bound.
    With deque(maxlen=N) in the fix, old items are silently dropped.
    """
    uri = f"ws://{host}:{port}/v1/trigger/listen?uid=chaos-audio-{client_id}&sample_rate=8000"
    end_time = time.time() + duration
    sent = 0

    while time.time() < end_time:
        try:
            async with websockets.connect(uri, close_timeout=2) as ws:
                # Set conversation ID first (needed for private cloud sync path)
                conv_id = f"conv-audio-{client_id}"
                data = struct.pack('<I', 103) + conv_id.encode('utf-8')
                await ws.send(data)

                conn_start = time.time()
                chunk_size = 16000
                audio_data = bytes(chunk_size)

                while time.time() < end_time:
                    # Improvement #7: Disconnect/reconnect after interval
                    if disconnect_interval and (time.time() - conn_start) >= disconnect_interval:
                        break

                    timestamp = time.time()
                    data = struct.pack('<I', 101) + struct.pack('d', timestamp) + audio_data
                    await ws.send(data)
                    sent += 1
                    stats['leak2_sent'] += 1

                    # 20 chunks/sec per client
                    await asyncio.sleep(0.05)

        except Exception as e:
            stats['errors'] += 1
            if 'connect' not in str(e).lower():
                print(f"  leak2 client {client_id}: {e}", file=sys.stderr)

        if not disconnect_interval:
            break


def slope_mb_per_min(ts_series, rss_series):
    """
    Improvement #6: Compute RSS growth slope via least-squares linear regression.
    Returns slope in MB/min. Positive = growing, near-zero = stable.
    """
    n = len(ts_series)
    if n < 3:
        return 0.0

    # Use last portion of data (skip initial ramp-up)
    t0 = ts_series[0]
    xs = [t - t0 for t in ts_series]
    ys = list(rss_series)

    x_mean = sum(xs) / n
    y_mean = sum(ys) / n

    num = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, ys))
    den = sum((x - x_mean) ** 2 for x in xs)

    if den == 0:
        return 0.0

    slope_mb_per_sec = num / den
    return round(slope_mb_per_sec * 60.0, 2)  # Convert to MB/min


async def monitor_memory(host, port, duration, stats):
    """Poll /debug/memory every 2 seconds and report. Collect RSS time series for slope analysis."""
    import urllib.request

    end_time = time.time() + duration

    ts_series = []
    rss_series = []

    while time.time() < end_time:
        await asyncio.sleep(2)
        try:
            url = f"http://{host}:{port}/debug/memory"
            req = urllib.request.urlopen(url, timeout=3)
            data = json.loads(req.read().decode())
            rss = data['rss_mb']
            tasks = data['asyncio_tasks']
            traced = data['traced_current_mb']
            elapsed = int(time.time() - (end_time - duration))

            # Improvement #2: Show task metrics if available
            task_m = data.get('safe_create_task_metrics', {})
            task_info = ""
            if task_m:
                task_info = f"  sct={task_m.get('in_flight', '?')}/{task_m.get('created', '?')}"

            # Improvement #8: Show thread pool metrics if available
            thread_m = data.get('to_thread_metrics', {})
            thread_info = ""
            if thread_m and thread_m.get('submitted', 0) > 0:
                thread_info = f"  threads={thread_m.get('in_flight', '?')}/{thread_m.get('submitted', '?')}"

            # Improvement #4: Show pusher debug metrics if available
            pusher_d = data.get('pusher_debug', {})
            queue_info = ""
            drops = pusher_d.get('queue_drops', {})
            if drops:
                total_drops = sum(drops.values())
                queue_info = f"  drops={total_drops}"
            qmax = pusher_d.get('queue_max_len', {})
            if qmax:
                max_vals = '/'.join(str(v) for v in qmax.values())
                queue_info += f"  qmax={max_vals}"

            print(
                f"  [{elapsed:3d}s] RSS={rss:.1f}MB  traced={traced:.1f}MB  tasks={tasks}"
                f"{task_info}{thread_info}{queue_info}"
                f"  leak1={stats['leak1_sent']}  leak2={stats['leak2_sent']}  err={stats['errors']}"
            )

            stats['last_rss'] = rss
            stats['last_tasks'] = tasks

            # Improvement #6: Collect time series for slope analysis
            ts_series.append(time.time())
            rss_series.append(rss)

        except Exception:
            pass

    # Compute and store slope
    slope = slope_mb_per_min(ts_series, rss_series)
    stats['rss_slope_mb_per_min'] = slope
    stats['rss_series_len'] = len(rss_series)

    # Also store the raw series for the caller
    stats['_ts_series'] = ts_series
    stats['_rss_series'] = rss_series


async def run_load(host, port, duration, mode, num_leak1, num_leak2, disconnect_interval=0):
    """Run load generation against the target."""
    stats = {
        'leak1_sent': 0,
        'leak2_sent': 0,
        'errors': 0,
        'last_rss': 0,
        'last_tasks': 0,
        'rss_slope_mb_per_min': 0,
        'rss_series_len': 0,
    }

    # Wait for server to be ready
    import urllib.request

    for attempt in range(30):
        try:
            urllib.request.urlopen(f"http://{host}:{port}/health", timeout=2)
            break
        except Exception:
            if attempt == 29:
                print("ERROR: Server not ready after 30 attempts", file=sys.stderr)
                return stats
            await asyncio.sleep(1)

    di_info = f", disconnect_interval={disconnect_interval}s" if disconnect_interval else ""
    print(f"  Server ready. Starting load: mode={mode}, duration={duration}s{di_info}")
    print(f"  Leak1 clients: {num_leak1 if mode in ('both', 'leak1') else 0}")
    print(f"  Leak2 clients: {num_leak2 if mode in ('both', 'leak2') else 0}")

    tasks = [asyncio.create_task(monitor_memory(host, port, duration, stats))]

    if mode in ('both', 'leak1'):
        for i in range(num_leak1):
            tasks.append(asyncio.create_task(leak1_client(host, port, i, duration, stats, disconnect_interval)))

    if mode in ('both', 'leak2'):
        for i in range(num_leak2):
            tasks.append(asyncio.create_task(leak2_client(host, port, i, duration, stats, disconnect_interval)))

    await asyncio.gather(*tasks, return_exceptions=True)

    # Final memory snapshot
    try:
        req = urllib.request.urlopen(f"http://{host}:{port}/debug/memory", timeout=3)
        data = json.loads(req.read().decode())
        stats['last_rss'] = data['rss_mb']
        stats['last_tasks'] = data['asyncio_tasks']

        # Capture final debug metrics for assertions
        stats['final_debug'] = data

        slope = stats.get('rss_slope_mb_per_min', 0)
        print(
            f"\n  Final: RSS={data['rss_mb']:.1f}MB  tasks={data['asyncio_tasks']}  "
            f"traced_peak={data['traced_peak_mb']:.1f}MB  slope={slope}MB/min"
        )

        # Print detailed debug info
        task_m = data.get('safe_create_task_metrics', {})
        if task_m:
            print(f"  Task metrics: {task_m}")
        thread_m = data.get('to_thread_metrics', {})
        if thread_m and thread_m.get('submitted', 0) > 0:
            print(f"  Thread metrics: {thread_m}")
        pusher_d = data.get('pusher_debug', {})
        if pusher_d:
            print(f"  Pusher debug: {pusher_d}")
    except Exception:
        pass

    return stats


def main():
    parser = argparse.ArgumentParser(description='Chaos OOM load generator')
    parser.add_argument('--host', default='localhost')
    parser.add_argument('--port', type=int, default=8080)
    parser.add_argument('--duration', type=int, default=90, help='Test duration in seconds')
    parser.add_argument('--mode', choices=['both', 'leak1', 'leak2'], default='both')
    parser.add_argument('--num-leak1', type=int, default=30, help='Number of leak1 (header-104) clients')
    parser.add_argument('--num-leak2', type=int, default=15, help='Number of leak2 (header-101) clients')
    parser.add_argument(
        '--disconnect-interval',
        type=float,
        default=0,
        help='Seconds between disconnect/reconnect cycles (0=no reconnect)',
    )
    args = parser.parse_args()

    stats = asyncio.run(
        run_load(
            args.host, args.port, args.duration, args.mode, args.num_leak1, args.num_leak2, args.disconnect_interval
        )
    )

    slope = stats.get('rss_slope_mb_per_min', 0)
    print(
        f"\nStats: leak1_sent={stats['leak1_sent']} leak2_sent={stats['leak2_sent']} "
        f"errors={stats['errors']} final_rss={stats['last_rss']}MB "
        f"final_tasks={stats['last_tasks']} slope={slope}MB/min"
    )


if __name__ == '__main__':
    main()
