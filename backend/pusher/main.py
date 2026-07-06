import json
import logging
import os
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

logging.basicConfig(level=logging.INFO)

import firebase_admin
from fastapi import FastAPI
from firebase_admin import credentials

from routers import pusher, metrics
from utils.http_client import close_all_clients
from utils.executors import drain_background_tasks, log_executor_health, start_background_task

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
