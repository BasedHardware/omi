"""Dedicated CPU pull entrypoint; never imports main, routers or serving pumps.

S2 is an idle fleet: unexpected leases are handed back without executing audio.
"""

import asyncio
from contextlib import asynccontextmanager
import logging
import os
import time

from omi_logging import TraceContextMiddleware, configure_logging

configure_logging(service='sync-backfill-worker')

import httpx
from fastapi import FastAPI
from starlette.responses import JSONResponse

from utils.executors import start_background_task
from utils.sync.worker_client import WorkerClient, worker_endpoint

logger = logging.getLogger(__name__)
POLL_SECONDS = 5


class Runtime:
    def __init__(self, client: WorkerClient):
        self.client = client
        self.stop = asyncio.Event()
        self.last_tick = time.monotonic()
        self.connected = False

    async def tick(self) -> None:
        result = await self.client.call('claim')
        self.connected = True
        lease = result.get('lease')
        if lease:
            payload = lease['payload']
            await self.client.call(
                'fail',
                {
                    'uid': payload['uid'],
                    'job_id': payload['job_id'],
                    'epoch': payload['sequencer_epoch'],
                    'token': lease['token'],
                },
            )
            logger.warning('event=sync_pull_worker outcome=idle_image_refused_lease')

    async def run(self) -> None:
        while not self.stop.is_set():
            try:
                await self.tick()
            except Exception as error:
                self.connected = False
                logger.warning('event=sync_pull_worker outcome=rpc_error exception_type=%s', type(error).__name__)
            self.last_tick = time.monotonic()
            try:
                await asyncio.wait_for(self.stop.wait(), POLL_SECONDS)
            except TimeoutError:
                pass


def create_app() -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
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
                await asyncio.wait_for(task, 30)

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(TraceContextMiddleware)

    @app.get('/health')
    async def health():
        runtime = app.state.runtime
        healthy = time.monotonic() - runtime.last_tick < 60
        return JSONResponse({'healthy': healthy}, status_code=200 if healthy else 503)

    @app.get('/ready')
    async def ready():
        runtime = app.state.runtime
        available = runtime.connected and not runtime.stop.is_set()
        return JSONResponse({'ready': available}, status_code=200 if available else 503)

    return app


def main() -> None:
    import uvicorn

    uvicorn.run(create_app(), host='0.0.0.0', port=8080, timeout_graceful_shutdown=1500, log_config=None)


if __name__ == '__main__':
    main()
