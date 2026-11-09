"""Fake-only local soak; owns emulator/listen PIDs and never invokes kubectl."""

from __future__ import annotations

import argparse
import asyncio
import ipaddress
import json
import os
import resource
import secrets
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx
from prometheus_client import REGISTRY
from prometheus_client.core import GaugeMetricFamily, CounterMetricFamily
from prometheus_client.parser import text_string_to_metric_families

from testing.live_stt_soak.manifest import render
from testing.live_stt_soak.run import metric_samples, public_pcm, session, summarize
from testing.live_stt_soak.safety import PROJECT, validate_environment

ROOT = Path(__file__).resolve().parents[2]
PORTS = (6379, 8085, 8080, 9090, 9155)


def local_environment(state: Path, sessions: int, order: str, recovery: bool, fault_after: float) -> dict[str, str]:
    """Allowlist, never copy the parent environment or load dotenv."""
    deployment = next(
        row
        for row in render(
            'gcr.io/based-hardware-dev/backend@sha256:' + '0' * 64, 'fake', sessions, fault_after, order, None
        )
        if row['kind'] == 'Deployment'
    )
    values = {
        row['name']: row['value']
        for row in deployment['spec']['template']['spec']['containers'][0]['env']
        if 'value' in row
    }
    values.update(
        PATH='/usr/bin:/bin',
        HOME=str(state / 'home'),
        CLOUDSDK_CONFIG=str(state / 'cloudsdk'),
        TMPDIR=str(state),
        PYTHONPATH=str(ROOT),
        PYTHONUNBUFFERED='1',
        GCE_METADATA_HOST='127.0.0.1:9',
        GCE_METADATA_IP='127.0.0.1',
        GCE_METADATA_TIMEOUT='1',
        STT_FAILOVER_RECOVERY_ENABLED=str(recovery).lower(),
        ADMIN_KEY=secrets.token_urlsafe(32),
        METRICS_SECRET=secrets.token_urlsafe(32),
    )
    # These are protocol placeholders, never provider credentials. The real
    # adapters require nonempty values; ProviderConnections redirects locally.
    for directory in ('home', 'cloudsdk'):
        (state / directory).mkdir()
    validate_environment(values)
    return values


def loopback_only() -> None:
    """Deny Python socket destinations outside loopback, including metadata."""
    original = socket.getaddrinfo

    def check(host: object) -> None:
        if host in (None, '', 'localhost'):
            return
        if isinstance(host, bytes):
            host = host.decode('ascii')
        if not ipaddress.ip_address(str(host)).is_loopback:
            raise RuntimeError('local soak denied a non-loopback destination')

    def resolve(host, *args, **kwargs):
        check(host)
        return original(host, *args, **kwargs)

    def audit(event, args):
        if event == 'socket.connect' and isinstance(args[1], tuple):
            check(args[1][0])

    socket.getaddrinfo = resolve
    sys.addaudithook(audit)


class MacProcessMetrics:
    """prometheus_client's Linux-only process collector has no macOS samples."""

    def collect(self):
        rss = int(subprocess.check_output(['/bin/ps', '-p', str(os.getpid()), '-o', 'rss=']).strip()) * 1024
        usage = resource.getrusage(resource.RUSAGE_SELF)
        yield GaugeMetricFamily('process_resident_memory_bytes', 'Listen resident memory', value=rss)
        yield CounterMetricFamily(
            'process_cpu_seconds', 'Listen user plus system CPU', value=usage.ru_utime + usage.ru_stime
        )


def listen() -> None:
    validate_environment(os.environ)
    if os.environ['OMI_STT_SOAK_MODE'] != 'fake':
        raise ValueError('local runner only supports fake mode')
    loopback_only()
    if sys.platform == 'darwin':
        REGISTRY.register(MacProcessMetrics())
    import uvicorn

    uvicorn.run(
        'testing.live_stt_soak.app:create_app',
        factory=True,
        host='127.0.0.1',
        port=8080,
        loop='uvloop',
        log_level='error',
        access_log=False,
    )


def ensure_ports_free() -> None:
    for port in PORTS:
        with socket.socket() as probe:
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            probe.bind(('127.0.0.1', port))


async def ready(port: int, process: subprocess.Popen) -> None:
    for _ in range(120):
        if process.poll() is not None:
            raise RuntimeError(f'owned process exited before readiness on port {port}')
        try:
            reader, writer = await asyncio.open_connection('127.0.0.1', port)
            writer.close()
            await writer.wait_closed()
            return
        except OSError:
            await asyncio.sleep(0.5)
    raise TimeoutError(f'local readiness timed out on port {port}')


def process_value(raw: str, name: str) -> float | None:
    return next(
        (
            sample.value
            for family in text_string_to_metric_families(raw)
            for sample in family.samples
            if sample.name == name
        ),
        None,
    )


async def drive(args, env: dict[str, str], process: subprocess.Popen) -> dict:
    async with httpx.AsyncClient(base_url='http://127.0.0.1:8080', trust_env=False, timeout=10) as client:
        for _ in range(120):
            if process.poll() is not None:
                raise RuntimeError('listen exited before health readiness')
            try:
                response = await client.get('/v1/health')
                response.raise_for_status()
                break
            except httpx.HTTPError:
                await asyncio.sleep(0.5)
        else:
            raise TimeoutError('listen health readiness timed out')
        await asyncio.sleep(10)  # Warm the actual window pressure cache.
        safety = (await client.get('/soak-safety')).json()
        if not safety.get('isolated') or safety['mode'] != 'fake' or safety['project'] != PROJECT:
            raise RuntimeError('not the isolated fake app')

        async def scrape():
            response = await client.get('/metrics', headers={'Authorization': 'Bearer ' + env['METRICS_SECRET']})
            response.raise_for_status()
            return response.text

        before_raw = await scrape()
        (args.output / 'before.prom').write_text(before_raw)
        samples, errors = [], []
        stop = asyncio.Event()

        async def sample():
            while not stop.is_set():
                try:
                    raw = await scrape()
                    samples.append(
                        {
                            'at': time.time(),
                            'rss_bytes': process_value(raw, 'process_resident_memory_bytes'),
                            'cpu_seconds': process_value(raw, 'process_cpu_seconds_total'),
                            'load_average': os.getloadavg()[0],
                            'replay_skipped_seconds': sum(
                                value
                                for (name, _), value in metric_samples(raw).items()
                                if name == 'omi_stt_replay_skipped_seconds_total'
                            ),
                        }
                    )
                    (args.output / 'progress.json').write_text(
                        json.dumps({'samples': samples, 'sampling_errors': errors}, indent=2) + '\n'
                    )
                except httpx.HTTPError as error:
                    errors.append(type(error).__name__)
                try:
                    await asyncio.wait_for(stop.wait(), timeout=5)
                except asyncio.TimeoutError:
                    pass

        sampler = asyncio.create_task(sample())
        pcm = public_pcm()
        started = time.monotonic()
        try:
            # Shared-machine protection: smaller sequential batches when busy.
            batch = min(args.sessions, 4) if os.getloadavg()[0] > 30 else args.sessions
            results = []
            for offset in range(0, args.sessions, batch):
                results.extend(
                    await asyncio.gather(
                        *(
                            session(str(client.base_url).rstrip('/'), n, args.minutes * 60, env['ADMIN_KEY'], pcm)
                            for n in range(offset, min(offset + batch, args.sessions))
                        )
                    )
                )
            duration = time.monotonic() - started
            await asyncio.sleep(5)
            after_raw = await scrape()
            final_safety = (await client.get('/soak-safety')).json()
        finally:
            stop.set()
            await sampler
    (args.output / 'after.prom').write_text(after_raw)
    cpu_before = process_value(before_raw, 'process_cpu_seconds_total')
    cpu_after = process_value(after_raw, 'process_cpu_seconds_total')
    cpu = None if cpu_before is None or cpu_after is None else cpu_after - cpu_before
    report = {
        **summarize(metric_samples(before_raw), metric_samples(after_raw)),
        'mode': 'fake-local',
        'order': args.order,
        'recovery_enabled': args.recovery,
        'minutes_per_session': args.minutes,
        'concurrent_batch_size': batch,
        'sessions': results,
        'sessions_started': sum(r['started'] for r in results),
        'client_terminated_failures': sum(r['client_terminated_failure'] for r in results),
        'faults_injected': final_safety['faults_injected'] - safety['faults_injected'],
        'process_samples': samples,
        'sampling_errors': errors,
        'rss_peak_bytes': max((r['rss_bytes'] for r in samples if r['rss_bytes'] is not None), default=None),
        'listen_cpu_seconds': cpu,
        'listen_cpu_seconds_per_session': None if cpu is None else cpu / args.sessions,
        'listen_cpu_percent_per_session': None if cpu is None else cpu / (args.sessions * args.minutes * 60) * 100,
        'wall_seconds': duration,
    }
    recovery_series = [
        row for row in report['metric_deltas'] if row['metric'].startswith(('omi_stt_recovery_', 'omi_stt_replay_'))
    ]
    report['recovery_metric_series'] = len(recovery_series)
    if (
        errors
        or report['rss_peak_bytes'] is None
        or cpu is None
        or report['client_terminated_failures']
        or not report['faults_injected']
        or (args.recovery and not report['positive_replays_over_100ms_lower_bound'])
        or (not args.recovery and recovery_series)
    ):
        report['gate'] = 'HOLD'
    return report


async def worker(args) -> None:
    validate_environment(os.environ)
    loopback_only()
    import google.auth
    from google.auth.exceptions import DefaultCredentialsError

    try:
        google.auth.default()
    except DefaultCredentialsError:
        proof = {
            'adc_lookup': 'DefaultCredentialsError',
            'cloudsdk_config_empty': not any(Path(os.environ['CLOUDSDK_CONFIG']).iterdir()),
            'provider_credentials': False,
            'provider_protocol_placeholders_only': True,
        }
    else:
        raise RuntimeError('ADC unexpectedly available; refusing to start')
    (args.output / 'isolation.json').write_text(json.dumps(proof, indent=2) + '\n')
    print(json.dumps(proof), flush=True)
    ensure_ports_free()

    def terminate(_signum, _frame):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, terminate)
    processes = []
    env = dict(os.environ)
    try:
        commands = [
            [
                args.java,
                '-Xmx512m',
                '-XX:ActiveProcessorCount=2',
                '-jar',
                str(args.firestore_jar),
                '--host=127.0.0.1',
                '--port=8085',
                '--websocket_port=9155',
                '--project_id=' + PROJECT,
                '--single_project_mode=true',
                '--single_project_mode_error=true',
            ],
            [args.redis, '--bind', '127.0.0.1', '--port', '6379', '--save', '', '--appendonly', 'no'],
            [sys.executable, '-m', 'testing.live_stt_soak.local', '--listen'],
        ]
        for command, port in zip(commands, (8085, 6379, 8080)):
            process = subprocess.Popen(
                command, env=env, cwd=env['TMPDIR'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            processes.append(process)
            await ready(port, process)
        report = await drive(args, env, processes[-1])
    finally:
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        for process in reversed(processes):
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=20)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=10)
        cleanup = {
            'owned_pids': [p.pid for p in processes],
            'exit_codes': [p.returncode for p in processes],
            'all_reaped': all(p.returncode is not None for p in processes),
        }
        (args.output / 'cleanup.json').write_text(json.dumps(cleanup, indent=2) + '\n')
    (args.output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(
        json.dumps(
            {key: report[key] for key in ('sessions_started', 'client_terminated_failures', 'faults_injected', 'gate')}
        ),
        flush=True,
    )
    if report['gate'] == 'HOLD':
        raise SystemExit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--listen', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--worker', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--sessions', type=int, default=16)
    parser.add_argument('--minutes', type=float, default=10)
    parser.add_argument('--order', default='parakeet-window,soniox,modulate-velma-2')
    parser.add_argument('--recovery', action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument('--fault-after', type=float, default=12)
    parser.add_argument('--firestore-jar', type=Path)
    parser.add_argument('--java', default=shutil.which('java'))
    parser.add_argument('--redis', default=shutil.which('redis-server'))
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.listen:
        listen()
        return
    if not 1 <= args.sessions <= 40 or not 0 < args.minutes <= 60 or not args.output:
        parser.error('1..40 sessions, 0..60 minutes and output are required')
    if args.worker:
        asyncio.run(worker(args))
        return
    if not args.firestore_jar or not args.firestore_jar.is_file() or not args.java or not args.redis:
        parser.error('existing Firestore emulator jar, java and redis-server are required')
    args.output.mkdir(parents=True, exist_ok=False)
    with tempfile.TemporaryDirectory(prefix='omi-stt-soak-local-') as temporary:
        env = local_environment(Path(temporary), args.sessions, args.order, args.recovery, args.fault_after)
        command = [
            sys.executable,
            '-m',
            'testing.live_stt_soak.local',
            '--worker',
            '--sessions',
            str(args.sessions),
            '--minutes',
            str(args.minutes),
            '--order',
            args.order,
            '--fault-after',
            str(args.fault_after),
            '--firestore-jar',
            str(args.firestore_jar.resolve()),
            '--java',
            str(Path(args.java).resolve()),
            '--redis',
            str(Path(args.redis).resolve()),
            '--output',
            str(args.output.resolve()),
            '--recovery' if args.recovery else '--no-recovery',
        ]
        child = subprocess.Popen(command, env=env, cwd=ROOT)
        try:
            code = child.wait()
        finally:
            if child.poll() is None:
                child.terminate()
                child.wait(timeout=90)
        if code:
            raise SystemExit(code)


if __name__ == '__main__':
    main()
