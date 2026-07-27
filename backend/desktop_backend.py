import json
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import firebase_admin
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from database.google_credentials import prepare_google_credentials
from routers import (
    auth,
    desktop_agent_vm,
    desktop_chat,
    desktop_core,
    desktop_deprecated,
    desktop_proxy,
    desktop_realtime,
    desktop_screen_crisp,
    desktop_tts_updates,
)
from utils.env_loader import load_backend_env


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    load_backend_env()
    prepare_google_credentials()
    auth_emulator_host = os.environ.get("FIREBASE_AUTH_EMULATOR_HOST", "").strip()
    if auth_emulator_host:
        for adc_key in ("GOOGLE_APPLICATION_CREDENTIALS", "SERVICE_ACCOUNT_JSON"):
            os.environ.pop(adc_key, None)
        firebase_project_id = (
            os.environ.get("FIREBASE_AUTH_PROJECT_ID") or os.environ.get("FIREBASE_PROJECT_ID") or "demo-omi-local"
        )
        firebase_admin.initialize_app(options={"projectId": firebase_project_id})
    elif service_account_json := os.environ.get("SERVICE_ACCOUNT_JSON"):
        service_account_info = json.loads(service_account_json)
        credentials = firebase_admin.credentials.Certificate(service_account_info)
        firebase_admin.initialize_app(credentials)
    else:
        firebase_admin.initialize_app()
    yield


app = FastAPI(lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(desktop_core.router)
app.include_router(auth.router)
app.include_router(desktop_agent_vm.router)
app.include_router(desktop_chat.router)
app.include_router(desktop_proxy.router)
app.include_router(desktop_realtime.router)
app.include_router(desktop_screen_crisp.router)
app.include_router(desktop_tts_updates.router)
app.include_router(desktop_deprecated.router)
