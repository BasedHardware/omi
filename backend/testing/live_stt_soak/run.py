"""Paced public-audio sockets plus per-process metrics. Only isolated dev pods."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import stat
import subprocess
import time
import wave
from pathlib import Path
from typing import Any

import httpx
import websockets
from prometheus_client.parser import text_string_to_metric_families

from testing.live_stt_soak.safety import (
    DEV_CONTEXT,
    NAMESPACE,
    PROJECT,
    session_uid,
    validate_target,
    validate_environment,
    FORBIDDEN,
)

FIXTURE = Path(__file__).resolve().parents[1] / 'release_fixtures/transcription-release-probe.wav'
METRICS = (
    'omi_live_stt_terminal_failures_total',
    'omi_stt_recovery_attempts_total',
    'omi_stt_replay_wall_seconds_count',
    'omi_stt_replay_wall_seconds_sum',
    'omi_stt_replay_wall_seconds_bucket',
    'omi_stt_replay_audio_seconds_total',
    'omi_stt_replay_skipped_seconds_total',
    'omi_stt_replay_successor_closed_total',
    'omi_live_session_terminal_after_text_total',
    'omi_fallback_total',
    'omi_live_session_transcript_outcome_total',
)


def validate_pod(pod: dict) -> None:
    if pod['metadata']['namespace'] != NAMESPACE or pod['metadata']['labels'].get('app') != 'live-stt-soak':
        raise ValueError('pod must be the dedicated isolated soak workload')
    spec = pod['spec']
    if spec.get('automountServiceAccountToken') is not False or spec.get('hostNetwork'):
        raise ValueError('pod must have no mounted runtime identity or host network')
    container = next(c for c in spec['containers'] if c['name'] == 'listen')
    if container.get('envFrom'):
        raise ValueError('shared envFrom is forbidden')
    if any(entry['name'] in FORBIDDEN for entry in container['env']):
        raise ValueError('customer credential and shared state references are forbidden')
    validate_environment({entry['name']: entry.get('value', '') for entry in container['env']})


def pod_generation(pod: dict) -> tuple:
    return (
        pod['metadata']['uid'],
        tuple(
            sorted(
                (row['name'], row.get('restartCount', 0), row.get('containerID', ''))
                for row in pod.get('status', {}).get('containerStatuses', [])
            )
        ),
    )


def private_file(path: Path) -> str:
    info = path.stat()
    if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077 or info.st_uid != os.getuid():
        raise ValueError('auth files must be owned, regular mode-0600 files')
    value = path.read_text().strip()
    if len(value) < 16:
        raise ValueError('local auth key must have at least 16 characters')
    return value


def public_pcm() -> bytes:
    manifest = json.loads(FIXTURE.with_suffix('.json').read_text())
    if hashlib.sha256(FIXTURE.read_bytes()).hexdigest() != manifest['sha256']:
        raise ValueError('public fixture hash mismatch')
    with wave.open(str(FIXTURE), 'rb') as audio:
        if (audio.getframerate(), audio.getnchannels(), audio.getsampwidth()) != (16000, 1, 2):
            raise ValueError('fixture must be mono PCM16 at 16kHz')
        return audio.readframes(audio.getnframes())


class MetricSamples(dict):
    declared: set[str]


def metric_samples(text: str) -> MetricSamples:
    families = list(text_string_to_metric_families(text))
    samples = MetricSamples(
        {
            (sample.name, tuple(sorted(sample.labels.items()))): float(sample.value)
            for family in families
            for sample in family.samples
            if sample.name in METRICS or sample.name == 'process_resident_memory_bytes'
        }
    )
    # Labeled counters have no samples before their first event. An exported
    # TYPE declaration proves registration; absence of that family does not.
    declared = set()
    for family in families:
        if family.type == 'counter':
            declared.add(family.name + '_total')
        elif family.type == 'histogram':
            declared.update(family.name + suffix for suffix in ('_count', '_sum', '_bucket'))
        else:
            declared.add(family.name)
    samples.declared = declared.intersection(METRICS)
    return samples


def summarize(before: dict, after: dict) -> dict:
    declared = getattr(after, 'declared', set())
    missing = [name for name in METRICS if name not in declared and not any(key[0] == name for key in after)]
    deltas, resets = [], []
    for key, value in sorted(after.items()):
        name, labels = key
        if name == 'process_resident_memory_bytes':
            continue
        delta = value - before.get(key, 0)
        if delta < 0:
            resets.append(name)
        deltas.append({'metric': name, 'labels': dict(labels), 'increase': delta})
    totals = {name: 0 for name in declared if name != 'omi_stt_replay_wall_seconds_bucket'}
    for row in deltas:
        name = row['metric']
        if name != 'omi_stt_replay_wall_seconds_bucket':
            totals[name] = totals.get(name, 0) + row['increase']
    fallback = {
        outcome: sum(
            row['increase']
            for row in deltas
            if row['metric'] == 'omi_fallback_total'
            and row['labels'].get('component') == 'stt_live_session'
            and row['labels'].get('outcome') == outcome
        )
        for outcome in ('recovered', 'exhausted')
    }
    positive = totals.get('omi_stt_replay_wall_seconds_count', 0) - sum(
        row['increase']
        for row in deltas
        if row['metric'] == 'omi_stt_replay_wall_seconds_bucket' and row['labels'].get('le') == '0.1'
    )
    buckets: dict[float, float] = {}
    for row in deltas:
        if row['metric'] == 'omi_stt_replay_wall_seconds_bucket':
            bound = float(row['labels']['le'])
            buckets[bound] = buckets.get(bound, 0) + row['increase']
    count = totals.get('omi_stt_replay_wall_seconds_count', 0)
    p95 = next((bound for bound, value in sorted(buckets.items()) if count > 0 and value >= count * 0.95), None)
    return {
        'metric_deltas': deltas,
        'totals': totals,
        'live_fallback_outcomes': fallback,
        'missing_metrics': missing,
        'counter_resets': sorted(set(resets)),
        'positive_replays_over_100ms_lower_bound': positive,
        'replay_wall_p95_upper_bound_seconds': p95 if p95 is not None and p95 != float('inf') else None,
        'gate': 'HOLD' if missing or resets else 'REVIEW_REQUIRED',
    }


async def session(base: str, index: int, seconds: float, key: str, pcm: bytes) -> dict:
    result = {
        'index': index,
        'started': False,
        'ready': False,
        'client_terminated_failure': False,
        'transcript_batches': 0,
        'terminal_status': False,
        'close_code': None,
    }
    url = (
        base.replace('http://', 'ws://')
        + '/v4/web/listen?sample_rate=16000&codec=pcm16&source=desktop&include_speech_profile=false'
    )
    try:
        async with websockets.connect(url, open_timeout=10, close_timeout=5) as ws:
            result['started'] = True
            await ws.send(json.dumps({'type': 'auth', 'token': key + session_uid(index)}))

            async def receive() -> None:
                async for message in ws:
                    if not isinstance(message, str) or message == 'ping':
                        continue
                    event = json.loads(message)
                    if isinstance(event, list) and event:
                        result['transcript_batches'] += 1
                    if isinstance(event, dict) and event.get('type') == 'service_status':
                        result['ready'] |= event.get('status') == 'ready'
                        result['terminal_status'] |= event.get('status') == 'stt_failed'

            receiver = asyncio.create_task(receive(), name=f'soak-receive-{index}')
            started = time.monotonic()
            offset, frame = 0, 640  # 20ms PCM16, 1x; never a catch-up burst.
            try:
                while time.monotonic() - started < seconds:
                    if receiver.done():
                        await receiver
                        result['client_terminated_failure'] = True
                        break
                    await ws.send(pcm[offset : offset + frame])
                    offset += frame
                    if offset >= len(pcm):
                        offset = 0
                    await asyncio.sleep(0.02)
                await ws.close(code=1000)
            finally:
                receiver.cancel()
                await asyncio.gather(receiver, return_exceptions=True)
            result['close_code'] = ws.close_code
    except Exception as error:
        result['client_terminated_failure'] = True
        result['error_class'] = type(error).__name__  # never exception strings/tokens
        result['close_code'] = getattr(error, 'code', None)
    result['client_terminated_failure'] |= result['terminal_status'] or not result['ready']
    return result


async def run(args: Any) -> dict:
    validate_target(args.url)
    if args.context != DEV_CONTEXT or not 1 <= args.sessions <= 40 or not 0 < args.minutes <= 60:
        raise ValueError('explicit dev context, 1..40 sessions and 0..60 minutes required')
    pod = json.loads(
        subprocess.run(
            ['kubectl', '--context', args.context, '-n', NAMESPACE, 'get', 'pod', args.pod, '-o', 'json'],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
    )
    validate_pod(pod)
    key, metrics_key = private_file(args.auth_file), private_file(args.metrics_file)
    pcm = public_pcm()
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output / 'pod-before.json').write_text(json.dumps(pod, indent=2))
    async with httpx.AsyncClient(base_url=args.url, timeout=10, trust_env=False) as client:
        safety = (await client.get('/soak-safety')).json()
        if not safety.get('isolated') or safety.get('project') != PROJECT or safety.get('sessions', 0) < args.sessions:
            raise ValueError('port-forward is not the configured isolated soak app')

        async def scrape() -> tuple[str, dict]:
            response = await client.get('/metrics', headers={'Authorization': f'Bearer {metrics_key}'})
            response.raise_for_status()
            return response.text, metric_samples(response.text)

        raw_before, before = await scrape()
        (args.output / 'before.prom').write_text(raw_before)
        stop = asyncio.Event()
        rss = []
        sampling_errors = []

        async def sample_rss() -> None:
            while not stop.is_set():
                try:
                    _, samples = await scrape()
                    rss.append({'at': time.time(), 'bytes': samples.get(('process_resident_memory_bytes', ()))})
                except httpx.HTTPError as error:
                    sampling_errors.append(type(error).__name__)
                try:
                    await asyncio.wait_for(stop.wait(), timeout=15)
                except asyncio.TimeoutError:
                    pass

        sampler = asyncio.create_task(sample_rss(), name='soak-rss')
        try:
            results = await asyncio.gather(
                *(session(args.url, n, args.minutes * 60, key, pcm) for n in range(args.sessions))
            )
            await asyncio.sleep(5)  # Allow ordinary session settlement after close.
            raw_after, after = await scrape()
            final_safety = (await client.get('/soak-safety')).json()
        finally:
            stop.set()
            await sampler
    (args.output / 'after.prom').write_text(raw_after)
    report = {
        **summarize(before, after),
        'pod': args.pod,
        'pod_uid': pod['metadata']['uid'],
        'image': next(c['image'] for c in pod['spec']['containers'] if c['name'] == 'listen'),
        'mode': safety['mode'],
        'minutes': args.minutes,
        'sessions': results,
        'sessions_started': sum(r['started'] for r in results),
        'client_terminated_failures': sum(r['client_terminated_failure'] for r in results),
        'faults_injected': final_safety['faults_injected'] - safety['faults_injected'],
        'rss_samples': rss,
        'rss_peak_bytes': max((r['bytes'] for r in rss if r['bytes'] is not None), default=None),
        'sampling_errors': sampling_errors,
    }
    final_pod = json.loads(
        subprocess.run(
            ['kubectl', '--context', args.context, '-n', NAMESPACE, 'get', 'pod', args.pod, '-o', 'json'],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
    )
    (args.output / 'pod-after.json').write_text(json.dumps(final_pod, indent=2))
    report['pod_restarted'] = pod_generation(final_pod) != pod_generation(pod)
    if (
        sampling_errors
        or report['rss_peak_bytes'] is None
        or not report['faults_injected']
        or not report['positive_replays_over_100ms_lower_bound']
        or report['client_terminated_failures']
        or report['pod_restarted']
    ):
        report['gate'] = 'HOLD'
    (args.output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--context', required=True)
    parser.add_argument('--pod', required=True)
    parser.add_argument('--url', required=True)
    parser.add_argument('--sessions', type=int, default=4)
    parser.add_argument('--minutes', type=float, default=10)
    parser.add_argument('--auth-file', type=Path, required=True)
    parser.add_argument('--metrics-file', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = asyncio.run(run(args))
    print(
        json.dumps(
            {k: report[k] for k in ('sessions_started', 'client_terminated_failures', 'faults_injected', 'gate')}
        )
    )
    if report['gate'] == 'HOLD':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
