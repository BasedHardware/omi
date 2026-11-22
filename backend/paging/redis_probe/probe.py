"""Serve the result of the last independent authenticated Redis PING."""

from concurrent.futures import Future, ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import os
from pathlib import Path
import subprocess
import sys
from threading import Thread
import time

ATTEMPT_INTERVAL = 30
ATTEMPT_TIMEOUT = 2
SAMPLER_LIVENESS_SECONDS = 65
TARGET = 'prod-serving-redis'
SUCCESS_METRIC = 'omi_redis_authenticated_ping_success'
ATTEMPT_METRIC = 'omi_redis_authenticated_ping_last_attempt_seconds'


def ping(deadline: float) -> bool:
    # Import only in the one-attempt child. No serving clients or application
    # modules are initialized by the probe.
    import redis
    from redis.backoff import NoBackoff
    from redis.retry import Retry

    try:
        with redis.Redis(
            host=os.environ['REDIS_DB_HOST'],
            port=int(os.environ['REDIS_DB_PORT']),
            username=os.environ['REDIS_PROBE_USERNAME'],
            password=Path(os.environ['REDIS_PROBE_PASSWORD_FILE']).read_text(),
            socket_connect_timeout=ATTEMPT_TIMEOUT,
            socket_timeout=ATTEMPT_TIMEOUT,
            retry=Retry(NoBackoff(), 0),
            health_check_interval=0,
            lib_name=None,
            lib_version=None,
            ssl=False,
        ) as client:
            return time.monotonic() < deadline and client.ping() is True
    except (OSError, ValueError, redis.RedisError):
        return False


def run_ping(deadline: float) -> bool:
    if time.monotonic() >= deadline:
        return False
    try:
        with subprocess.Popen(
            [sys.executable, __file__, '--ping', str(deadline)],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        ) as child:
            try:
                remaining = max(0, deadline - time.monotonic())
                return child.wait(timeout=remaining) == 0 and time.monotonic() <= deadline
            except subprocess.TimeoutExpired:
                child.kill()
                return False
    except OSError:
        return False


class Probe:
    def __init__(self) -> None:
        self.sample: tuple[int, int, float] | None = None
        self.in_flight: Future[bool] | None = None

    def sample_once(self, pool: ThreadPoolExecutor, deadline: float) -> None:
        attempted_at = int(time.time())
        success = False
        # A stuck launch or reap must not delay the recorded result, queue a
        # second attempt, or permit a child that starts after its deadline to
        # contact Redis. DNS and all socket operations run in the child.
        if self.in_flight is not None and not self.in_flight.done():
            return
        self.in_flight = pool.submit(run_ping, deadline)
        try:
            success = self.in_flight.result(timeout=max(0, deadline - time.monotonic()))
        except TimeoutError:
            pass
        self.sample = (int(success), attempted_at, deadline - ATTEMPT_TIMEOUT)

    def sample_forever(self) -> None:
        with ThreadPoolExecutor(max_workers=1) as pool:
            # Prestart the single worker before measuring the first attempt.
            # Subsequent submissions never need to create a thread.
            pool.submit(lambda: None).result()
            while True:
                started = time.monotonic()
                self.sample_once(pool, started + ATTEMPT_TIMEOUT)
                time.sleep(max(0, ATTEMPT_INTERVAL - (time.monotonic() - started)))

    def live(self) -> bool:
        sample = self.sample
        return sample is not None and time.monotonic() - sample[2] < SAMPLER_LIVENESS_SECONDS

    def metrics(self) -> bytes:
        # Publish status and attempt time in one snapshot. Prior to the first
        # result there is no evidence of success or failure.
        sample = self.sample
        if sample is None:
            return b''
        success, attempted_at, _ = sample
        return (
            f'# TYPE {SUCCESS_METRIC} gauge\n'
            f'{SUCCESS_METRIC}{{target="{TARGET}"}} {success}\n'
            f'# TYPE {ATTEMPT_METRIC} gauge\n'
            f'{ATTEMPT_METRIC}{{target="{TARGET}"}} {attempted_at}\n'
        ).encode()


def serve() -> None:
    probe = Probe()

    class MetricsHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.path == '/healthz/live':
                body = b''
                status = 200 if probe.live() else 503
            elif self.path == '/metrics':
                body = probe.metrics()
                status = 200
            else:
                self.send_error(404)
                return
            self.send_response(status)
            self.send_header('Content-Type', 'text/plain; version=0.0.4; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, _format: str, *_args: object) -> None:
            pass

    with ThreadingHTTPServer(('0.0.0.0', 9090), MetricsHandler) as server:
        Thread(target=probe.sample_forever, daemon=True).start()
        server.serve_forever()


if __name__ == '__main__':
    if len(sys.argv) == 3 and sys.argv[1] == '--ping':
        sys.exit(0 if ping(float(sys.argv[2])) else 1)
    serve()
