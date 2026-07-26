import json
import logging
import os
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from utils.logging_config import configure_split_stream_logging

# Route INFO/DEBUG to stdout and WARNING+ to stderr so GKE Cloud Logging does not
# classify routine request logs as ERROR severity (issues #9136, #9138, #9135).
configure_split_stream_logging(level=logging.INFO)

import firebase_admin
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from firebase_admin import credentials

from routers import pusher, metrics
from utils.http_client import close_all_clients
from utils.executors import drain_background_tasks, log_executor_health, start_background_task
from utils.readiness import ReadinessGate

if os.environ.get('SERVICE_ACCOUNT_JSON'):
    service_account_info = json.loads(os.environ["SERVICE_ACCOUNT_JSON"])
    firebase_credentials = credentials.Certificate(service_account_info)
    firebase_admin_sdk: Any = firebase_admin
    firebase_admin_sdk.initialize_app(firebase_credentials)
else:
    firebase_admin_sdk = firebase_admin
    firebase_admin_sdk.initialize_app()


async def startup_event() -> None:
    start_background_task(log_executor_health(), name='pusher:executor_health')


async def shutdown_event() -> None:
    # Defense-in-depth: close readiness FIRST so the LB stops sending NEW traffic
    # even if the chart preStop hook did not run. Existing in-flight sessions are
    # then drained by drain_background_tasks within the bounded grace period.
    ReadinessGate.begin_drain()
    await drain_background_tasks(timeout=10.0)
    await close_all_clients()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    del app
    await startup_event()
    try:
        yield
    finally:
        await shutdown_event()


app = FastAPI(lifespan=lifespan)
app.include_router(pusher.router)
app.include_router(metrics.router)

paths = ['_temp', '_samples', '_segments', '_speech_profiles']
for path in paths:
    if not os.path.exists(path):
        os.makedirs(path)


@app.get('/health')
async def health_check() -> dict[str, str]:
    return {"status": "healthy"}


@app.get('/ready')
async def ready() -> Response:
    # Readiness for the LB: 200 while serving new traffic, 503 once drain begins.
    # Distinct from /health (liveness), which stays 200 as long as the process is alive.
    if ReadinessGate.is_serving():
        return JSONResponse(content={"status": "ready"}, status_code=200)
    return JSONResponse(content={"status": "draining"}, status_code=503)


@app.post('/__internal/drain')
async def drain(request: Request) -> Response:
    # Trust boundary: accept ONLY loopback peers (the preStop hook curls this from
    # within the pod). The barrier is request.client.host being 127.0.0.1/::1, NOT
    # network isolation: the Ingress path:/ Prefix does route this path, but an
    # off-pod caller (internal LB) presents a non-loopback peer and is 403'd. This
    # relies on uvicorn NOT running --proxy-headers, so request.client.host is the
    # real TCP peer rather than a spoofable X-Forwarded-For.
    client_host = request.client.host if request.client else None
    if client_host not in {'127.0.0.1', '::1'}:
        return Response(status_code=403)
    # Idempotent: safe to call from both preStop and the lifespan shutdown path.
    ReadinessGate.begin_drain()
    return JSONResponse(content={"status": "draining"}, status_code=200)
