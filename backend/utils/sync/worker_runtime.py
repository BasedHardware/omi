"""Dedicated CPU pull entrypoint; never imports main, routers or serving pumps.

Each lease executes in its own process group so lease loss kills executor
leaves before the Cloud Tasks fallback can run the same job.
"""

import asyncio
import contextlib
from contextlib import asynccontextmanager
import logging
import json
import os
import signal
import sys
import time

from omi_logging import TraceContextMiddleware, configure_logging

configure_logging(service='sync-backfill-worker')

import httpx
from fastapi import FastAPI
from starlette.responses import JSONResponse, Response
from prometheus_client import CONTENT_TYPE_LATEST

from utils.executors import start_background_task
from utils.sync.worker_client import WorkerClient, worker_endpoint
from utils.sync.worker_privacy_metrics import WorkerPrivacyMetrics
from utils.staging_fence import assert_staging_isolation

logger = logging.getLogger(__name__)
POLL_SECONDS = 5
HEARTBEAT_SECONDS = 120
# Wall-clock work bound, enforced outside the job's event loop/executors.
# Includes bootstrap, provider work and normal child flushing. Both silence
# leases remain 1800s; timeout kills the group without releasing Redis early.
WORK_DEADLINE_SECONDS = 1380
EMPTY_POLL_MAX_SECONDS = 60


async def launch_job(env: dict[str, str]):
    return await asyncio.create_subprocess_exec(
        sys.executable,
        '-m',
        'utils.sync.worker_job',
        stdin=asyncio.subprocess.PIPE,
        env=env,
        start_new_session=True,
    )


class Runtime:
    def __init__(self, client: WorkerClient):
        self.client = client
        self.stop = asyncio.Event()
        self.last_tick = time.monotonic()
        self.connected = False
        self.active = False
        self.poll_seconds = POLL_SECONDS
        self.privacy_metrics = WorkerPrivacyMetrics()

    async def tick(self) -> None:
        result = await self.client.call('claim')
        self.connected = True
        lease = result.get('lease')
        if lease:
            self.poll_seconds = POLL_SECONDS
            await self.execute(lease)
        else:
            self.poll_seconds = min(EMPTY_POLL_MAX_SECONDS, self.poll_seconds * 2)

    async def execute(self, lease: dict) -> None:
        payload = lease['payload']
        identity = {
            'uid': payload['uid'],
            'job_id': payload['job_id'],
            'epoch': payload['sequencer_epoch'],
            'token': lease['token'],
        }
        if not (await self.client.call('heartbeat', identity)).get('accepted'):
            return
        self.active = True
        process = None
        waiter = None
        completed = False
        try:
            async with asyncio.timeout(WORK_DEADLINE_SECONDS):
                # Payload and opaque lease token travel through stdin, never argv.
                process = await launch_job(self.privacy_metrics.begin_job())
                assert process.stdin is not None
                process.stdin.write(json.dumps(lease).encode())
                await process.stdin.drain()
                process.stdin.close()
                waiter = start_background_task(process.wait(), name='sync-pull:job-exit')
                next_heartbeat = time.monotonic() + HEARTBEAT_SECONDS
                while process.returncode is None:
                    self.last_tick = time.monotonic()
                    try:
                        await asyncio.wait_for(asyncio.shield(waiter), POLL_SECONDS)
                    except TimeoutError:
                        pass
                    if process.returncode is not None:
                        break
                    if time.monotonic() >= next_heartbeat:
                        if not (await self.client.call('heartbeat', identity)).get('accepted'):
                            raise RuntimeError('sequencer lease lost')
                        next_heartbeat = time.monotonic() + HEARTBEAT_SECONDS
                completed = process.returncode == 0
        except TimeoutError:
            logger.warning('event=sync_pull_worker outcome=work_deadline')
        finally:
            if process is not None:
                # No pattern-based kill: this child owns a fresh process group.
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                await asyncio.wait_for(process.wait(), 10)
            if waiter is not None:
                await asyncio.wait_for(waiter, 10)
            self.privacy_metrics.finish_job()
            self.active = False
        # Child exit is the quiescence proof. A killed child leaves Redis held;
        # fail then refuses early release and the unchanged silence TTL wins.
        response = await self.client.call('complete' if completed else 'fail', identity)
        logger.info(
            'event=sync_pull_worker outcome=%s accepted=%s',
            'completed' if completed else 'fallback',
            bool(response.get('accepted')),
        )

    async def run(self) -> None:
        while not self.stop.is_set():
            try:
                await self.tick()
            except Exception as error:
                self.connected = False
                self.poll_seconds = min(EMPTY_POLL_MAX_SECONDS, self.poll_seconds * 2)
                logger.warning('event=sync_pull_worker outcome=rpc_error exception_type=%s', type(error).__name__)
            self.last_tick = time.monotonic()
            remaining = self.poll_seconds
            while remaining > 0 and not self.stop.is_set():
                # Keep health fresh during backoff without claiming again.
                interval = min(POLL_SECONDS, remaining)
                try:
                    await asyncio.wait_for(self.stop.wait(), interval)
                except TimeoutError:
                    pass
                self.last_tick = time.monotonic()
                remaining -= interval


def create_app() -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        assert_staging_isolation()
        if os.environ.get('OMI_ENV_STAGE') != 'prod':
            raise ValueError('worker registry requires explicit prod stage; staging needs isolated persistence')
        base, audience = worker_endpoint()
        async with httpx.AsyncClient(timeout=httpx.Timeout(20, connect=3), follow_redirects=False) as http:
            runtime = Runtime(WorkerClient(http, base, audience))
            app.state.runtime = runtime
            task = start_background_task(runtime.run(), name='sync-pull:poll')
            try:
                yield
            finally:
                runtime.stop.set()
                try:
                    await asyncio.wait_for(asyncio.shield(task), 1450)
                except TimeoutError:
                    task.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await asyncio.wait_for(task, 30)

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(TraceContextMiddleware)

    async def health():
        runtime = app.state.runtime
        healthy = time.monotonic() - runtime.last_tick < 60
        return JSONResponse({'healthy': healthy}, status_code=200 if healthy else 503)

    async def ready():
        runtime = app.state.runtime
        available = runtime.connected and not runtime.stop.is_set()
        return JSONResponse({'ready': available}, status_code=200 if available else 503)

    async def metrics():
        return Response(app.state.runtime.privacy_metrics.render(), media_type=CONTENT_TYPE_LATEST)

    app.add_api_route('/metrics', metrics, methods=['GET'])
    app.add_api_route('/health', health, methods=['GET'])
    app.add_api_route('/ready', ready, methods=['GET'])
    return app


def main() -> None:
    import uvicorn

    uvicorn.run(create_app(), host='0.0.0.0', port=8080, timeout_graceful_shutdown=1500, log_config=None)


if __name__ == '__main__':
    main()
