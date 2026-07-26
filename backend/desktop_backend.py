import json
import os

import firebase_admin
from fastapi import FastAPI

from database.google_credentials import prepare_google_credentials
from routers import (
    desktop_agent_vm,
    desktop_chat,
    desktop_core,
    desktop_proxy,
    desktop_realtime,
    desktop_screen_crisp,
    desktop_tts_updates,
)
from utils.env_loader import load_backend_env

load_backend_env()
prepare_google_credentials()

_auth_emulator_host = os.environ.get("FIREBASE_AUTH_EMULATOR_HOST", "").strip()
if _auth_emulator_host:
    for _adc_key in ("GOOGLE_APPLICATION_CREDENTIALS", "SERVICE_ACCOUNT_JSON"):
        os.environ.pop(_adc_key, None)
    _firebase_project_id = (
        os.environ.get("FIREBASE_AUTH_PROJECT_ID") or os.environ.get("FIREBASE_PROJECT_ID") or "demo-omi-local"
    )
    firebase_admin.initialize_app(options={"projectId": _firebase_project_id})
elif os.environ.get("SERVICE_ACCOUNT_JSON"):
    _service_account_info = json.loads(os.environ["SERVICE_ACCOUNT_JSON"])
    _credentials = firebase_admin.credentials.Certificate(_service_account_info)
    firebase_admin.initialize_app(_credentials)
else:
    firebase_admin.initialize_app()

app = FastAPI()
app.include_router(desktop_core.router)
app.include_router(desktop_agent_vm.router)
app.include_router(desktop_chat.router)
app.include_router(desktop_proxy.router)
app.include_router(desktop_realtime.router)
app.include_router(desktop_screen_crisp.router)
app.include_router(desktop_tts_updates.router)
