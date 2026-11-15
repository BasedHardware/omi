"""Public-only shadow replay. Exit zero qualifies replay gates, never the full roll."""

import argparse
import asyncio
from collections import Counter
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import time

import httpx
from prometheus_client.parser import text_string_to_metric_families

if __package__ in (None, ''):
    # Executed from /replay: use the mounted benchmark from this exact checkout.
    import bench_diarizer_batch as bench
else:
    from scripts import bench_diarizer_batch as bench

BASE = 'http://prod-omi-diarizer-batch-canary.prod-omi-backend.svc.cluster.local:8080'
BASELINE = dict(
    measured_until='2026-11-09T07:37:00Z',
    rtf_mean=0.059,
    app_peak_gib=1.62,
    dcgm_peak_gib=3.0,
    failed=0,
    rejected=0,
    # Historical configured-host final-pass population, NOT an API outcome.
    incomplete_coverage_share=0.251,
    coverage_measured_at='2026-11-08T14:09:00Z',
)


def emit(event, **fields):
    print(json.dumps(dict(event=event, at=datetime.now(timezone.utc).isoformat(), **fields)), flush=True)


def metrics(base):
    response = httpx.get(base + '/metrics', timeout=10, follow_redirects=False)
    response.raise_for_status()
    samples = [sample for family in text_string_to_metric_families(response.text) for sample in family.samples]
    counts = {s.labels['outcome']: s.value for s in samples if s.name == 'omi_diarization_v2_total'}
    depth = [s.value for s in samples if s.name == 'omi_diarization_v2_queue_depth']
    memory = [s.value for s in samples if s.name == 'omi_diarization_v2_gpu_memory_bytes']
    if depth != [0] or len(memory) != 1 or not math.isfinite(memory[0]) or memory[0] < 0:
        raise ValueError('missing/invalid metrics or target queue not empty')
    return counts, memory[0] / 2**30


async def observed_wave(pcm, concurrency, timeout):
    """Sample the per-request CUDA gauge during serialized/concurrent waves."""
    stop, peaks = asyncio.Event(), [0.0]

    async def sample():
        async with httpx.AsyncClient(timeout=10, follow_redirects=False) as client:
            while not stop.is_set():
                response = await client.get(BASE + '/metrics')
                response.raise_for_status()
                memory = [
                    s.value
                    for family in text_string_to_metric_families(response.text)
                    for s in family.samples
                    if s.name == 'omi_diarization_v2_gpu_memory_bytes'
                ]
                if len(memory) != 1 or not math.isfinite(memory[0]) or memory[0] < 0:
                    raise ValueError('missing/invalid CUDA memory sample')
                peaks[0] = max(peaks[0], memory[0] / 2**30)
                try:
                    await asyncio.wait_for(stop.wait(), timeout=1)
                except TimeoutError:
                    pass

    sampler = asyncio.create_task(sample())
    try:
        receipt = await bench.wave(pcm, concurrency, timeout, single_attempt=True)
    finally:
        stop.set()
        await sampler
    return dict(**receipt, app_peak_gib_sampled=peaks[0])


def summarize(requests, app_peak):
    counts = Counter(r['outcome'] for r in requests)
    rtfs = [r.get('inference_rtf') for r in requests]
    valid = bool(rtfs) and all(v is not None and math.isfinite(v) and v > 0 for v in rtfs)
    mean = sum(rtfs) / len(rtfs) if valid else None
    gates = dict(
        errors=bool(requests) and counts['ok'] == len(requests),
        rtf=valid and mean <= BASELINE['rtf_mean'] * 1.15,
        app_vram=math.isfinite(app_peak) and app_peak <= 2.0,
    )
    return dict(
        requests=len(requests),
        outcome_counts={outcome: counts[outcome] for outcome in ('ok', 'failed', 'rejected')},
        inference_rtf_mean=mean,
        inference_rtf_limit=BASELINE['rtf_mean'] * 1.15,
        app_peak_gib=app_peak,
        replay_gates=gates,
        replay_passed=all(gates.values()),
        incomplete_coverage=dict(
            measured=False,
            share=None,
            reason='upstream audio-assembly outcome; not exposed by /v2/diarization',
        ),
        full_qualification='PENDING: DCGM, restarts/startup, coverage and operator sign-off',
    )


async def run(args):
    # Deliberately no arbitrary endpoint, GCS prefix or production fallback.
    os.environ['HOSTED_DIARIZATION_API_URL'] = BASE
    bench.prepare(args.corpus)
    manifest = bench.load_corpus(args.corpus)
    emit(
        'manifest',
        corpus_sha256=manifest['sha256'],
        source=manifest['source'],
        target=BASE,
        target_image=args.target_image,
        client_image=args.client_image,
        baseline=BASELINE,
        soak_hours=args.soak_hours,
    )
    initial, app_peak = metrics(BASE)
    if sum(initial.values()) != 0:
        raise ValueError('fresh shadow required: nonzero request counters before replay')
    started = time.monotonic()
    end = started + args.soak_hours * 3600
    requests, previous, cycle = [], initial, 0
    while time.monotonic() < end:
        cycle_start = time.monotonic()
        for minutes in bench.MINUTES:
            with (Path(args.corpus) / 'corpus.pcm').open('rb') as stream:
                pcm = stream.read(minutes * 60 * bench.BYTES_PER_SECOND)
            for concurrency in (1, 2):
                if time.monotonic() >= end:
                    break
                before, memory = metrics(BASE)
                if before != previous:
                    raise ValueError('unexpected traffic/counter reset between waves')
                app_peak = max(app_peak, memory)
                receipt = await observed_wave(pcm, concurrency, args.timeout)
                app_peak = max(app_peak, receipt['app_peak_gib_sampled'])
                for row in receipt['requests']:
                    row.setdefault('error', None)
                    row.setdefault('inference_rtf', None)
                    row.setdefault('wall_rtf', row['wall_seconds'] / row['audio_seconds'])
                requests.extend(receipt['requests'])
                emit('wave', cycle=cycle, minutes=minutes, **receipt)
                if any(r['outcome'] != 'ok' for r in receipt['requests']):
                    emit('summary', **summarize(requests, app_peak))
                    return 1  # No retry: canceled GPU work can still be running.
                after, memory = metrics(BASE)
                expected = dict(before)
                expected['ok'] = expected.get('ok', 0) + concurrency
                if after != expected:
                    raise ValueError('server outcome counts disagree: traffic, reset or rejected/failed request')
                previous = after
                app_peak = max(app_peak, memory)
                # Fail immediately on a measured gate miss; never hide it in later cycles.
                summary = summarize(requests, app_peak)
                if not summary['replay_passed']:
                    emit('summary', **summary)
                    return 1
        cycle += 1
        await asyncio.sleep(max(0, min(end, cycle_start + args.interval) - time.monotonic()))
    final, memory = metrics(BASE)
    if final != previous:
        raise ValueError('unexpected traffic/counter reset during idle soak')
    summary = summarize(requests, max(app_peak, memory))
    emit('summary', elapsed_seconds=time.monotonic() - started, cycles=cycle, **summary)
    return 0 if summary['replay_passed'] else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--corpus', default='/data')
    parser.add_argument('--target-image', required=True)
    parser.add_argument('--client-image', required=True)
    parser.add_argument('--soak-hours', type=float, default=24)
    parser.add_argument('--interval', type=float, default=3600)
    parser.add_argument('--timeout', type=float, default=1200)
    args = parser.parse_args()
    if not (0 < args.soak_hours <= 24 and 1 <= args.interval <= 3600 and 1 <= args.timeout <= 1200):
        parser.error('soak in (0,24], interval in [1,3600], timeout in [1,1200] required')
    try:
        return asyncio.run(run(args))
    except Exception as error:
        # Exception strings may contain response bodies. Only the type is safe.
        emit('abort', error=type(error).__name__, full_qualification='FAIL; inspect numeric receipts')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
