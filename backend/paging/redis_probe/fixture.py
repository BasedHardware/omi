"""Run the candidate image against a private Redis and Prometheus Docker network.

From the repository root, pass the local image tag as argv[1].
"""

from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
import json
from pathlib import Path
from secrets import token_hex
import subprocess
import sys
from tempfile import TemporaryDirectory
from threading import Event
import time
from urllib.parse import urlencode
from unittest.mock import patch
from uuid import uuid4

from . import probe as probe_module
from .probe import ATTEMPT_METRIC, SUCCESS_METRIC, TARGET

USER = 'omi-redis-serving-probe'
PROBE_CREDENTIAL = '/run/probe-auth/password'


def docker(*args: str, check: bool = True, stdin: str | None = None) -> str:
    return subprocess.run(
        ['docker', *args], check=check, input=stdin, stdout=subprocess.PIPE, text=True, timeout=30
    ).stdout.strip()


def sample(prometheus: str, expression: str) -> float | None:
    url = 'http://127.0.0.1:9090/api/v1/query?' + urlencode({'query': expression})
    results = json.loads(docker('exec', prometheus, 'wget', '-q', '-O', '-', url))['data']['result']
    if not results:
        return None
    if len(results) != 1:
        raise AssertionError(f'expected one series for {expression!r}, got {len(results)}')
    return float(results[0]['value'][1])


def await_state(prometheus: str, expression: str, success: int, previous: int) -> int:
    selector = f'{{job="omi-redis-serving-probe",target="{TARGET}"}}'
    deadline = time.monotonic() + 55
    while time.monotonic() < deadline:
        try:
            attempted_at = sample(prometheus, ATTEMPT_METRIC + selector)
            if (
                attempted_at is not None
                and attempted_at > previous
                and sample(prometheus, SUCCESS_METRIC + selector) == success
                and sample(prometheus, expression) == 1 - success
            ):
                return int(attempted_at)
        except subprocess.CalledProcessError:
            pass
        time.sleep(0.5)
    raise AssertionError(f'expected fresh success={success} and combined alert condition={1 - success}')


def check_attempt_deadlines(root: Path) -> None:
    stalled_child = root / 'stall.py'
    stalled_child.write_text('import time\ntime.sleep(30)\n')
    sampler = probe_module.Probe()
    assert not sampler.live()
    with ThreadPoolExecutor(max_workers=1) as worker:
        with patch.object(probe_module, '__file__', str(stalled_child)):
            started = time.monotonic()
            sampler.sample_once(worker, started + 2)
            elapsed = time.monotonic() - started
            assert sampler.sample is not None and sampler.sample[0] == 0
            assert 1.9 <= elapsed < 2.5, elapsed
            assert sampler.in_flight is not None
            assert sampler.in_flight.result(timeout=1) is False

        start_attempt = Event()
        release_attempt = Event()

        def delayed_launch(_deadline: float) -> bool:
            start_attempt.set()
            return release_attempt.wait(timeout=5)

        with patch.object(probe_module, 'run_ping', side_effect=delayed_launch) as launch:
            try:
                started = time.monotonic()
                sampler.sample_once(worker, started + 2)
                elapsed = time.monotonic() - started
                assert start_attempt.is_set()
                assert sampler.sample is not None and sampler.sample[0] == 0
                assert 1.9 <= elapsed < 2.5, elapsed
                timed_out_sample = sampler.sample
                sampler.sample_once(worker, time.monotonic() + 2)
                assert sampler.sample is timed_out_sample and launch.call_count == 1
                assert sampler.live()
                expired = timed_out_sample[2] + probe_module.SAMPLER_LIVENESS_SECONDS
                with patch.object(probe_module.time, 'monotonic', return_value=expired):
                    assert not sampler.live()
            finally:
                release_attempt.set()

    print('Probe enforced the 2s publication deadline during a stalled child and a delayed launch.')


def run(image: str) -> None:
    name = f'local-redis-pilot-{uuid4().hex[:10]}'
    redis, probe, prometheus = (f'{name}-{suffix}' for suffix in ('redis', 'probe', 'prometheus'))
    backend = Path(__file__).resolve().parents[2]
    rules = json.loads((backend / 'charts/monitoring/alerts/resilience.json').read_text())
    expression = next(rule['data'][0]['model']['expr'] for rule in rules if rule['uid'] == 'omi-redis-cache-conn-page')

    with TemporaryDirectory() as path, ExitStack() as cleanup:
        root = Path(path)
        check_attempt_deadlines(root)

        password = token_hex(32)
        prometheus_config = root / 'prometheus.yml'
        prometheus_config.write_text(
            f'scrape_configs:\n  - job_name: {USER}\n    scrape_interval: 2s\n'
            f'    static_configs:\n      - targets: ["{probe}:9090"]\n'
        )
        prometheus_config.chmod(0o444)

        docker('network', 'create', '--internal', name)
        cleanup.callback(docker, 'network', 'rm', name, check=False)

        def start(container: str, *args: str) -> None:
            docker('run', '--detach', '--rm', '--network', name, '--name', container, *args)
            cleanup.callback(docker, 'rm', '-f', container, check=False)

        # Redis reads and applies the native ACL before opening its listener.
        # The FIFO carries startup configuration without retaining it.
        start(
            redis,
            '--user',
            'redis',
            '--log-driver',
            'none',
            '--tmpfs',
            '/run/redis-auth:rw,noexec,nosuid,nodev,size=64k,mode=0700,uid=999,gid=1000',
            '--entrypoint',
            'sh',
            'redis:7.4-alpine',
            '-c',
            'mkfifo -m 0600 /run/redis-auth/config && exec redis-server - < /run/redis-auth/config',
        )
        docker(
            'exec',
            '-i',
            redis,
            'sh',
            '-c',
            'while [ ! -p /run/redis-auth/config ]; do sleep 0.1; done; cat > /run/redis-auth/config',
            stdin=f'bind 0.0.0.0\nsave ""\nappendonly no\nuser default off\nuser {USER} on >{password} +ping\n',
        )
        start(
            probe,
            '--read-only',
            '--tmpfs',
            '/run/probe-auth:rw,noexec,nosuid,nodev,size=64k,mode=0700,uid=65532,gid=65532',
            '-e',
            f'REDIS_DB_HOST={redis}',
            '-e',
            'REDIS_DB_PORT=6379',
            '-e',
            f'REDIS_PROBE_USERNAME={USER}',
            '-e',
            f'REDIS_PROBE_PASSWORD_FILE={PROBE_CREDENTIAL}',
            '--entrypoint',
            'sh',
            image,
            '-c',
            'while [ ! -f "$REDIS_PROBE_PASSWORD_FILE" ]; do sleep 0.1; done; exec python probe.py',
        )
        # Publish the credential only after stdin has closed and the file is complete.
        docker(
            'exec',
            '-i',
            probe,
            'sh',
            '-c',
            'umask 077; cat > "$REDIS_PROBE_PASSWORD_FILE.tmp" && mv "$REDIS_PROBE_PASSWORD_FILE.tmp" "$REDIS_PROBE_PASSWORD_FILE"',
            stdin=password,
        )
        start(
            prometheus,
            '-v',
            f'{prometheus_config}:/etc/prometheus/prometheus.yml:ro',
            'prom/prometheus:v3.5.0',
        )
        healthy = await_state(prometheus, expression, 1, 0)
        assert 'NOAUTH' in docker('exec', redis, 'redis-cli', 'PING')
        acl_check = docker('exec', '-i', redis, 'redis-cli', '--raw', stdin=f'AUTH {USER} {password}\nGET fixture\n')
        auth_status, _, get_status = acl_check.partition('\n')
        assert auth_status == 'OK' and get_status.startswith('NOPERM')

        docker('pause', redis)
        try:
            failed = await_state(prometheus, expression, 0, healthy)
            # Redis failure still advances the sampler and should not restart it.
            docker('exec', prometheus, 'wget', '-q', '-O', '-', f'http://{probe}:9090/healthz/live')
        finally:
            docker('unpause', redis)
        recovered = await_state(prometheus, expression, 1, failed)
        cadence = (failed - healthy, recovered - failed)
        assert all(29 <= delta <= 31 for delta in cadence), cadence
        print(f'Isolated Redis/Prometheus passed: PING-only identity, 1 → 0 → 1, attempt intervals {cadence}s.')


if __name__ == '__main__':
    run(sys.argv[1])
