import asyncio
import json
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import firebase_admin
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import Response

from database.firestore_tier_context import FirestoreTierMiddleware
from utils.byok import BYOKMiddleware
from utils.llm.desktop_proxy_lifetime import DesktopProxyDeadlineMiddleware
from utils.env_loader import firebase_admin_options, load_backend_env
from utils.firebase_admin_runtime import (
    firebase_verify_only_credential,
    install_firebase_auth_mutation_guard,
    install_google_adc_guard,
)

install_google_adc_guard()

from database.google_credentials import prepare_google_credentials
from routers import (
    auth,
    desktop_agent_vm,
    desktop_chat,
    desktop_core,
    desktop_deprecated,
    desktop_proxy,
    desktop_task_gate,
    metrics,
    retired_app_client_contracts,
    retired_desktop_proactivity,
    desktop_realtime,
    desktop_screen_crisp,
    desktop_tts_updates,
)
from utils.http_client import close_all_clients
from utils.llm.vertex_reservation_state import reservation_state
from utils.metrics import start_metrics_sidecar_server, stop_metrics_sidecar_server
from utils.llm.managed_spend_ledger import shutdown_managed_spend_ledger
from utils.executors import log_executor_health, start_background_task
from utils.desktop_loop_watchdog import DesktopLoopWatchdog, InFlightRequestsMiddleware


def _initialize_firebase_admin() -> None:
    """Initialize token verification without selecting the Google data project.

    Development serves production Firebase identities. Compute (GCE / ``agentVm``)
    stays on Cloud Run ADC / ``GOOGLE_CLOUD_PROJECT``. Customer entitlements
    (plan, usage, quota) use the mounted Auth SA file's ``project_id`` via
    ``get_customer_firestore_client()`` and must not retarget ADC.
    ``firebase_admin_options`` therefore pins only Firebase Admin's token
    audience; ADC continues to use ``GOOGLE_CLOUD_PROJECT`` independently.
    """
    auth_emulator_host = os.environ.get("FIREBASE_AUTH_EMULATOR_HOST", "").strip()
    install_firebase_auth_mutation_guard()
    verify_only_credential = firebase_verify_only_credential()
    if verify_only_credential is not None:
        firebase_admin.initialize_app(verify_only_credential, options=firebase_admin_options())
    elif auth_emulator_host:
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
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    prepare_google_credentials()
    _initialize_firebase_admin()
    start_metrics_sidecar_server()
    watchdog: DesktopLoopWatchdog = app.state.loop_watchdog
    watchdog.start()
    health_task = start_background_task(log_executor_health(), name="executor_health")
    heartbeat_task = (
        start_background_task(watchdog.heartbeat(), name="desktop_loop_heartbeat") if watchdog.enabled else None
    )
    try:
        yield
    finally:
        watchdog.stop()
        for task in (health_task, heartbeat_task):
            if task is not None:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        await shutdown_managed_spend_ledger()
        await reservation_state.aclose()
        await close_all_clients()

        stop_metrics_sidecar_server()


def _cors_allowed_origins_from_env() -> list[str]:
    origins = [origin.strip() for origin in os.getenv('CORS_ALLOWED_ORIGINS', '').split(',') if origin.strip()]
    if '*' in origins:
        raise RuntimeError('CORS_ALLOWED_ORIGINS must not contain "*" — list explicit origins instead')
    return origins


def _build_app() -> FastAPI:
    app = FastAPI(lifespan=lifespan)
    app.add_middleware(FirestoreTierMiddleware)
    watchdog = DesktopLoopWatchdog(enabled=os.getenv("DESKTOP_LOOP_WATCHDOG_ENABLED", "true").lower() != "false")
    app.state.loop_watchdog = watchdog
    app.add_middleware(InFlightRequestsMiddleware, watchdog=watchdog)

    @app.get("/healthz/live", include_in_schema=False)
    async def desktop_liveness() -> Response:
        return Response(status_code=200 if watchdog.is_live() else 503)

    # Explicit, default-deny CORS: desktop backend traffic is Bearer-token
    # authenticated, so no cross-origin browser caller needs to be allowed by
    # default. CORS_ALLOWED_ORIGINS lets an operator opt a specific web frontend
    # in (comma-separated exact origins — never "*", and never combined with
    # allow_credentials, which would leak authenticated responses).
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_allowed_origins_from_env(),
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=[
            "X-Omi-Memory-Canonical-Lifecycle-Exposed",
            "X-Omi-Memory-Default-Delete-Supported",
            "X-Omi-Memory-Device-Scope-Supported",
            "X-Omi-Memory-Next-Cursor",
            "X-Omi-List-Truncated",
        ],
    )
    # Desktop sends BYOK keys as X-BYOK-* headers on every chat request; without
    # this middleware they're never read into the contextvar, so get_byok_key()
    # always returns None here and BYOK users silently ride the managed/quota
    # lane instead of their own keys. main.py installs the same middleware.
    app.add_middleware(BYOKMiddleware)
    app.add_middleware(DesktopProxyDeadlineMiddleware)
    app.include_router(desktop_core.router)
    app.include_router(auth.router)
    app.include_router(desktop_agent_vm.router)
    app.include_router(desktop_chat.router)
    app.include_router(desktop_proxy.router)
    app.include_router(desktop_task_gate.router)
    app.include_router(retired_desktop_proactivity.router)
    app.include_router(retired_app_client_contracts.router)
    app.include_router(desktop_realtime.router)
    app.include_router(desktop_screen_crisp.router)
    app.include_router(desktop_tts_updates.router)
    app.include_router(desktop_deprecated.router)
    app.include_router(metrics.router)
    return app


def create_app() -> FastAPI:
    load_backend_env()
    return _build_app()


# Load staged backend env before constructing the app so CORS origins are
# populated before CORSMiddleware is installed. This keeps the module-level `app`
# entrypoint (used by desktop/macos/run.sh, the dev harness, and docs) consistent
# with the factory entrypoint used by Cloud Run/Docker.
load_backend_env()
app = _build_app()
