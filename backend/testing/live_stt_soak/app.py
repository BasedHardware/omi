"""Isolated test entrypoint exposing the real listen route, not production main.

Pod-local Firestore/Redis own all persistence and router observations. No
production startup jobs, pusher, storage, LLM, or Firebase mutations run here.
"""

from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from typing import Any

from testing.live_stt_soak.safety import validate_environment, session_uid, PROJECT
from testing.live_stt_soak.transport import ProviderConnections, start_fake_server


def create_app() -> Any:
    validate_environment(os.environ)
    # Guard before importing any runtime clients. No dotenv hydration.
    from utils.firebase_admin_runtime import (
        firebase_verify_only_credential,
        install_google_adc_guard,
        install_firebase_auth_mutation_guard,
    )

    install_google_adc_guard()
    install_firebase_auth_mutation_guard()
    import firebase_admin

    try:
        firebase_admin.get_app()
    except ValueError:
        firebase_admin.initialize_app(firebase_verify_only_credential(), options={'projectId': PROJECT})

    from database._client import get_firestore_client
    from fastapi import FastAPI, Response
    from routers import transcribe, metrics
    from utils.stt import soniox, streaming
    from utils.http_client import close_all_clients
    from utils.executors import shutdown_executors
    from utils.stt.parakeet_window import batch_pressure

    mode = os.environ['OMI_STT_SOAK_MODE']
    faults = ProviderConnections(
        mode, float(os.environ.get('OMI_STT_SOAK_FAULT_AFTER', '12')), int(os.environ.get('OMI_STT_SOAK_FAULTS', '4'))
    )
    # Replace only these two adapters' module references; never globally patch
    # the websocket package, serving selection, recovery, send queues or metrics.
    soniox.websockets = faults
    streaming.websockets = faults

    @asynccontextmanager
    async def lifespan(_app: Any):
        server = await start_fake_server() if mode == 'fake' else None
        db = get_firestore_client()
        for index in range(int(os.environ.get('OMI_STT_SOAK_SESSIONS', '4'))):
            await asyncio.to_thread(
                db.collection('users').document(session_uid(index)).set,
                {
                    'id': session_uid(index),
                    'language': 'en',
                    'private_cloud_sync_enabled': False,
                    'transcription_preferences': {'uses_custom_stt': False, 'single_language_mode': True},
                },
            )
        batch_pressure.start_from_env()
        try:
            yield
        finally:
            await faults.shutdown()
            await batch_pressure.stop()
            if server is not None:
                server.close()
                await server.wait_closed()
            await close_all_clients()
            shutdown_executors()

    app = FastAPI(lifespan=lifespan)
    app.include_router(transcribe.router)
    app.include_router(metrics.router)

    @app.get('/v1/health')
    def health() -> dict[str, str]:
        return {'status': 'ok'}

    @app.get('/soak-safety')
    def safety() -> dict[str, Any]:
        return {
            'isolated': True,
            'project': PROJECT,
            'mode': mode,
            'faults_injected': faults.injected,
            'sessions': int(os.environ.get('OMI_STT_SOAK_SESSIONS', '4')),
        }

    @app.get('/batch/metrics')
    def window_pressure() -> dict[str, float]:
        return {'live_pending_requests': 0, 'live_oldest_pending_seconds': 0}

    @app.post('/v1/transcribe')
    def fail_window() -> Response:
        # Local synthetic window-provider outage; the production window socket,
        # VAD, capture ring and paid successor/replay adapters remain real.
        # No PCM is inspected or persisted by this endpoint.
        faults.injected += 1
        return Response(status_code=503)

    return app
