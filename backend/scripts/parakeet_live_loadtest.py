#!/usr/bin/env python3
"""Paced, content-free load receipts for a port-forwarded dev Parakeet pod.

Uses only checked-in licensed/synthetic release fixtures. This is an HTTP/GPU
capacity probe, not a listen, Firestore, VAD, or transcript-quality test.
"""

from __future__ import annotations

import argparse
import asyncio
from collections import Counter
import hashlib
import io
import json
import math
import os
from pathlib import Path
import time
from urllib.parse import urlparse
import wave

import httpx
from prometheus_client.parser import text_string_to_metric_families

FIXTURES = Path(__file__).resolve().parents[1] / 'testing/release_fixtures'


def validate_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme != 'http' or parsed.hostname != '127.0.0.1' or parsed.username or parsed.password:
        raise ValueError('Use an explicit http://127.0.0.1:<port> dev pod port-forward')
    if parsed.path not in ('', '/') or parsed.query or parsed.fragment or not parsed.port:
        raise ValueError('Expected only the loopback origin and explicit port')
    return url.rstrip('/')


def fixture_pcm() -> bytes:
    parts = []
    for name in ('transcription-release-probe.json', 'parakeet-canary-pt.json'):
        manifest = json.loads((FIXTURES / name).read_text())
        data = (FIXTURES / manifest['fixture_filename']).read_bytes()
        if hashlib.sha256(data).hexdigest() != manifest['sha256']:
            raise ValueError('Fixture hash mismatch')
        with wave.open(io.BytesIO(data)) as wav:
            if (wav.getnchannels(), wav.getsampwidth(), wav.getframerate()) != (1, 2, 16000):
                raise ValueError('Fixture must be mono 16 kHz PCM16')
            parts.append(wav.readframes(wav.getnframes()))
    return b''.join(parts)


def audio(pcm: bytes, seconds: int) -> bytes:
    size = seconds * 32000
    stream = io.BytesIO()
    with wave.open(stream, 'wb') as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes((pcm * math.ceil(size / len(pcm)))[:size])
    return stream.getvalue()


def quantile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    values = sorted(values)
    return values[max(0, math.ceil(q * len(values)) - 1)]


def metrics(text: str) -> dict:
    return {
        (sample.name, tuple(sorted(sample.labels.items()))): sample.value
        for family in text_string_to_metric_families(text)
        for sample in family.samples
    }


def histogram(before: dict, after: dict, name: str, labels: dict | None = None) -> dict:
    labels = labels or {}
    buckets = []
    total = 0.0
    count = 0.0
    for key, value in after.items():
        metric, pairs = key
        sample_labels = dict(pairs)
        if any(sample_labels.get(k) != v for k, v in labels.items()):
            continue
        delta = value - before.get(key, 0)
        if metric == name + '_bucket':
            buckets.append((float(sample_labels['le']), delta))
        elif metric == name + '_sum':
            total += delta
        elif metric == name + '_count':
            count += delta
    buckets.sort()
    result = {'count': count, 'mean': total / count if count else None}
    for q in (0.5, 0.95, 0.99):
        prev_bound = prev_count = 0.0
        result[f'p{int(q * 100)}'] = None
        for bound, bucket_count in buckets:
            if count and bucket_count >= count * q:
                # Match Prometheus interpolation; +Inf resolves to the last finite bound.
                result[f'p{int(q * 100)}'] = (
                    prev_bound
                    if math.isinf(bound)
                    else prev_bound + (bound - prev_bound) * (count * q - prev_count) / (bucket_count - prev_count)
                )
                break
            prev_bound, prev_count = bound, bucket_count
    return result


async def step(client: httpx.AsyncClient, args: argparse.Namespace, n: int, payloads: dict) -> dict:
    before = metrics((await client.get(args.url + '/metrics/')).raise_for_status().text)
    rows: list[dict] = []
    pressure: list[dict] = []
    telemetry_errors: Counter = Counter()
    batch_rate = max(args.batch_floor_rps, n / args.pace * 16 / 84)
    start = time.monotonic()
    start_epoch = time.time()
    stop = start + args.seconds
    outstanding: set[asyncio.Task] = set()

    async def post(lane: str, duration: int) -> None:
        began = time.monotonic()
        status: int | str = 'transport_error'
        has_text = False
        try:
            headers = {'X-Omi-STT-Surface': 'live-window', 'X-Omi-STT-Timeout-Seconds': '8'} if lane == 'live' else {}
            endpoint = '/v1/transcribe' if lane == 'live' else '/v2/transcribe'
            response = await client.post(
                args.url + endpoint,
                files={'file': ('fixture.wav', payloads[duration], 'audio/wav')},
                data={'diarize': str(args.diarize_backfill).lower()} if lane == 'backfill' else None,
                headers=headers,
                timeout=8 if lane == 'live' else 120,
            )
            status = response.status_code
            if status == 200:
                has_text = bool(response.json().get('text', '').strip())
        except (httpx.HTTPError, ValueError):
            pass
        rows.append(
            {
                'lane': lane,
                'duration': duration,
                'latency': time.monotonic() - began,
                'status': status,
                'has_text': has_text,
            }
        )

    async def live(session: int) -> None:
        due = start + (0 if args.synchronized else session * args.pace / n)
        i = 0
        while due < stop:
            await asyncio.sleep(max(0, due - time.monotonic()))
            began = time.monotonic()
            await post('live', args.live_context_seconds or (6, 12, 18, 24)[i % 4])
            i += 1
            # One POST in flight per session, minimum interval between starts.
            due = max(due + args.pace, began + args.pace, time.monotonic())

    async def backfill() -> None:
        due = start
        i = 0
        # Approximate prerecorded duration bands inferred from fleet aggregates:
        # 30% <=30s, 20% 30-60s, 40% 60-120s, 10% 120-300s.
        mix = (30, 60, 120, 30, 120, 60, 120, 30, 120, 240)
        while due < stop:
            await asyncio.sleep(max(0, due - time.monotonic()))
            if len(outstanding) >= 32:
                raise RuntimeError('Batch backlog exceeded 32; stop instead of hiding overload')
            task = asyncio.create_task(post('backfill', mix[i % len(mix)]))
            outstanding.add(task)
            task.add_done_callback(outstanding.discard)
            i += 1
            due += 1 / batch_rate
        if outstanding:
            await asyncio.gather(*list(outstanding))

    async def sample() -> None:
        while time.monotonic() < stop:
            try:
                snapshot = (await client.get(args.url + '/batch/metrics', timeout=5)).raise_for_status().json()
                pressure.append(snapshot)
            except (httpx.HTTPError, ValueError) as error:
                telemetry_errors[type(error).__name__] += 1
            await asyncio.sleep(0.5)

    await asyncio.gather(*(live(i) for i in range(n)), backfill(), sample())
    after = metrics((await client.get(args.url + '/metrics/')).raise_for_status().text)
    result = {
        'sessions': n,
        'seconds': args.seconds,
        'pace': args.pace,
        'live_context_seconds': args.live_context_seconds,
        'batch_rps': batch_rate,
        'synchronized': args.synchronized,
        'diarize_backfill': args.diarize_backfill,
        'keepalive_connections': args.keepalive_connections,
        'start_epoch': start_epoch,
        'end_epoch': time.time(),
    }
    for lane in ('live', 'backfill'):
        selected = [row for row in rows if row['lane'] == lane]
        latencies = [row['latency'] for row in selected]
        result[lane] = {
            'count': len(selected),
            'p50': quantile(latencies, 0.5),
            'p95': quantile(latencies, 0.95),
            'p99': quantile(latencies, 0.99),
            'statuses': dict(Counter(str(row['status']) for row in selected)),
            'nonempty': sum(row['has_text'] for row in selected),
            'completed_rps': sum(row['status'] == 200 for row in selected) / (time.monotonic() - start),
            'audio_seconds': sum(row['duration'] for row in selected if row['status'] == 200),
            'queue_wait': histogram(before, after, 'parakeet_batch_lane_queue_wait_seconds', {'lane': lane}),
            'server_post': histogram(
                before,
                after,
                'parakeet_request_duration_seconds',
                {'endpoint': 'v1_transcribe' if lane == 'live' else 'v2_transcribe'},
            ),
        }
    result['inference'] = histogram(before, after, 'parakeet_inference_duration_seconds')
    result['batch_size'] = histogram(before, after, 'parakeet_batch_size')
    result['oom'] = after.get(('parakeet_gpu_oom_total', ()), 0) - before.get(('parakeet_gpu_oom_total', ()), 0)
    result['fatal_cuda'] = after.get(('parakeet_gpu_fatal_errors_total', ()), 0) - before.get(
        ('parakeet_gpu_fatal_errors_total', ()), 0
    )
    result['pressure_samples'] = len(pressure)
    result['telemetry_errors'] = dict(telemetry_errors)
    result['old_gate_busy_share'] = (
        (
            sum(row['live_pending_requests'] >= 4 or row['live_oldest_pending_seconds'] >= 0.75 for row in pressure)
            / len(pressure)
        )
        if pressure
        else None
    )
    result['max_live_pending'] = max((row['live_pending_requests'] for row in pressure), default=None)
    result['max_live_oldest'] = max((row['live_oldest_pending_seconds'] for row in pressure), default=None)
    result['rows'] = rows
    return result


async def run(args: argparse.Namespace) -> None:
    pcm = fixture_pcm()
    payloads = {seconds: audio(pcm, seconds) for seconds in (6, 12, 18, 24, 30, 60, 120, 240)}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.owned_pids.open('a') as file:
        file.write(f'{os.getpid()} parakeet-live-loadtest\n')
    # Close mode measures conservative tunnel overhead. Reuse mode mirrors the
    # serving client, with expiry below Uvicorn's timer to avoid idle races.
    # No POST is retried in either mode.
    async with httpx.AsyncClient(
        limits=httpx.Limits(
            max_connections=128, max_keepalive_connections=args.keepalive_connections, keepalive_expiry=2
        ),
        headers={} if args.keepalive_connections else {'Connection': 'close'},
        trust_env=False,
    ) as client:
        health = (await client.get(args.url + '/health')).raise_for_status().json()
        snapshot = (await client.get(args.url + '/batch/metrics')).raise_for_status().json()
        if health.get('ready') is not True or 'live_pending_requests' not in snapshot:
            raise ValueError('Require a healthy dev pod with the current live/backfill scheduler')
        for n in args.sessions:
            receipt = await step(client, args, n, payloads)
            with args.output.open('a') as file:
                file.write(json.dumps(receipt) + '\n')
            print(json.dumps({k: v for k, v in receipt.items() if k != 'rows'}), flush=True)
            if receipt['oom'] or receipt['fatal_cuda']:
                raise RuntimeError('Stop after GPU error')
            if (
                not receipt['pressure_samples']
                or sum(receipt['telemetry_errors'].values()) > receipt['pressure_samples'] / 10
            ):
                raise RuntimeError('Stop on inadequate queue telemetry coverage')


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', type=validate_url, default='http://127.0.0.1:28180')
    parser.add_argument('--sessions', type=int, nargs='+', default=[2, 4, 6, 8, 12, 16, 24])
    parser.add_argument('--seconds', type=float, default=180)
    parser.add_argument('--pace', type=float, default=6)
    parser.add_argument('--batch-floor-rps', type=float, default=177000 / 86400 / 3)
    parser.add_argument('--synchronized', action='store_true')
    parser.add_argument('--live-context-seconds', type=int, choices=[6, 12, 18, 24], default=None)
    parser.add_argument('--diarize-backfill', action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument('--keepalive-connections', type=int, default=0)
    parser.add_argument('--output', type=Path, default=Path('.local/parakeet-load.jsonl'))
    parser.add_argument('--owned-pids', type=Path, default=Path('.local/owned-pids.txt'))
    args = parser.parse_args()
    if (
        min(args.sessions) < 1
        or args.seconds < 6
        or args.pace < 1
        or args.batch_floor_rps <= 0
        or args.keepalive_connections < 0
    ):
        parser.error('Require positive bounded sessions, duration, pace and batch traffic')
    asyncio.run(run(args))


if __name__ == '__main__':
    main()
