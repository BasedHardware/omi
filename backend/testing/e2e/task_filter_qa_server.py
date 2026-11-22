"""Loopback-only native UI fixture using production routes + real local Firestore.

Run from backend with FIRESTORE_EMULATOR_HOST=127.0.0.1:8798
and GCLOUD_PROJECT=demo-fs-p1. Authentication, Redis and external provider I/O
are synthetic; task/filter codecs, queries, budgets and HTTP responses are real.
"""

import os
from pathlib import Path
from urllib.parse import urlsplit

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from google.auth.credentials import AnonymousCredentials
from google.cloud.firestore_v1.client import Client

from scripts import export_openapi as bootstrap


def main():
    host = os.environ.get('FIRESTORE_EMULATOR_HOST', '')
    if urlsplit('http://' + host).hostname not in {'127.0.0.1', 'localhost', '::1'}:
        raise RuntimeError('A loopback Firestore emulator is required')
    if os.environ.get('GCLOUD_PROJECT') != 'demo-fs-p1':
        raise RuntimeError('Only the synthetic demo-fs-p1 project is permitted')
    # Capture the real emulator client before the import harness substitutes
    # process-wide Client construction for unrelated service singletons.
    client = Client(project='demo-fs-p1', credentials=AnonymousCredentials())
    bootstrap.configure_hermetic_environment()
    bootstrap._install_import_paths()
    bootstrap.install_hermetic_dependency_patches()
    os.environ.update(FIRESTORE_EMULATOR_HOST=host, GCLOUD_PROJECT='demo-fs-p1')
    with bootstrap.record_and_block_outbound_network():
        from database import conversation_task_links as links
        from routers.conversation_tasks import router
        from tests.integration.test_conversation_tasks_emulator import seed

        uid = 'task-filter-native-qa'
        links.get_firestore_client = lambda: client
        links.get_action_items_list_version = lambda uid: None
        app = FastAPI()
        app.include_router(router)
        for route in app.routes:
            if hasattr(route, 'dependant'):
                for dependency in route.dependant.dependencies:
                    app.dependency_overrides[dependency.call] = lambda: uid
        failing = False
        failure_status = 503

        @app.middleware('http')
        async def fault(request, call_next):
            if failing and request.url.path.startswith('/v1/conversations/'):
                return JSONResponse({'detail': 'synthetic read failure'}, status_code=failure_status)
            return await call_next(request)

        @app.post('/fixture/reset')
        def reset():
            nonlocal failing, failure_status
            failing = False
            failure_status = 503
            seed(client, uid)
            return {'ok': True}

        @app.post('/fixture/failure')
        async def failure(request: Request):
            nonlocal failing, failure_status
            control = await request.json()
            failing = control.get('fail') is True
            failure_status = 403 if control.get('status') == 403 else 503
            return {'ok': True}

        @app.post('/fixture/delete-first-task')
        def delete_task():
            client.collection('users').document(uid).collection('action_items').document('t0').update({'deleted': True})
            return {'ok': True}

        @app.post('/fixture/screenshot/{name}')
        async def screenshot(name: str, request: Request):
            if name not in {'home-task-badge', 'conversations-with-tasks'}:
                return JSONResponse({'detail': 'unknown capture'}, status_code=400)
            image = await request.body()
            if not image.startswith(b'\x89PNG\r\n\x1a\n') or len(image) > 5 * 1024 * 1024:
                return JSONResponse({'detail': 'invalid capture'}, status_code=400)
            Path(f'/tmp/omi-20620-{name}.png').write_bytes(image)
            return {'ok': True}

        seed(client, uid)
        uvicorn.run(app, host='127.0.0.1', port=18966, log_level='warning')


if __name__ == '__main__':
    main()
