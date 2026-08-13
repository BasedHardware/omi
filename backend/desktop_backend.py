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
    desktop_proactivity,
    desktop_realtime,
    desktop_screen_crisp,
    desktop_tts_updates,
)
from utils.env_loader import firebase_admin_options, load_backend_env
from utils.http_client import close_all_clients


def _initialize_firebase_admin() -> None:
    """Initialize token verification without selecting the Google data project.

    Development serves production Firebase identities but runs its Cloud Run
    workload (Firestore and Agent VM control) in the development GCP project.
    ``firebase_admin_options`` therefore pins only Firebase Admin's token
    audience; ADC continues to use ``GOOGLE_CLOUD_PROJECT`` independently.
    """
    auth_emulator_host = os.environ.get("FIREBASE_AUTH_EMULATOR_HOST", "").strip()
    if auth_emulator_host:
        for adc_key in ("GOOGLE_APPLICATION_CREDENTIALS", "SERVICE_ACCOUNT_JSON", "FIREBASE_AUTH_CREDENTIALS_PATH"):
            os.environ.pop(adc_key, None)
        firebase_project_id = (
            os.environ.get("FIREBASE_AUTH_PROJECT_ID") or os.environ.get("FIREBASE_PROJECT_ID") or "demo-omi-local"
        )
        firebase_admin.initialize_app(options={"projectId": firebase_project_id})
    elif firebase_auth_credentials_path := os.environ.get("FIREBASE_AUTH_CREDENTIALS_PATH", "").strip():
        credentials = firebase_admin.credentials.Certificate(firebase_auth_credentials_path)
        firebase_admin.initialize_app(credentials, options=firebase_admin_options())
    elif service_account_json := os.environ.get("SERVICE_ACCOUNT_JSON"):
        service_account_info = json.loads(service_account_json)
        credentials = firebase_admin.credentials.Certificate(service_account_info)
        firebase_admin.initialize_app(credentials, options=firebase_admin_options())
    else:
        firebase_admin.initialize_app(options=firebase_admin_options())


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    load_backend_env()
    prepare_google_credentials()
    _initialize_firebase_admin()
    try:
        yield
    finally:
        await close_all_clients()


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
app.include_router(desktop_proactivity.router)
app.include_router(desktop_realtime.router)
app.include_router(desktop_screen_crisp.router)
app.include_router(desktop_tts_updates.router)
app.include_router(desktop_deprecated.router)
