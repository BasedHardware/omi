"""Local Calendar API fixture: real Omi routes and Firestore, synthetic Google HTTP.

Run only against an explicitly configured loopback Firestore emulator. No Google
OAuth, Firebase production identity, live calendar or customer record is used.
"""

import argparse
import os
from contextlib import asynccontextmanager
from functools import partial
from unittest.mock import patch

import httpx
from fastapi import FastAPI, HTTPException
from google.auth.credentials import AnonymousCredentials
from google.cloud import firestore

if __name__ == '__main__':
    # A standalone simulator fixture must be as isolated as the pytest lane:
    # no dotenv/ADC/service credentials and no non-loopback network access.
    import atexit
    from contextlib import ExitStack
    from scripts.export_openapi import configure_hermetic_environment
    from testing.hermetic_network import block_local_redis, block_outbound_network

    configure_hermetic_environment()
    _isolation = ExitStack()
    _isolation.enter_context(block_outbound_network())
    _isolation.enter_context(block_local_redis())
    atexit.register(_isolation.close)

from database import google_calendar_preferences as preferences
from routers import google_calendar as routes
from routers import integrations as integration_routes
from utils.retrieval.tools import google_utils


@asynccontextmanager
async def calendar_fixture(uid: str = 'calendar-qa', project: str = 'demo-omi-calendar-20195'):
    host = os.environ.get('FIRESTORE_EMULATOR_HOST', '')
    if not host.startswith(('127.0.0.1:', 'localhost:')) or not project.startswith('demo-'):
        raise RuntimeError('Calendar QA requires an explicit loopback Firestore emulator and demo project')
    db = firestore.Client(project=project, credentials=AnonymousCredentials())
    db.collection('users').document(uid).set({'qa_fixture': True})
    state = {'uid': uid, 'google_account': 'personal@example.test', 'secondary_available': True, 'connected': True}
    calls = []

    def provider(request: httpx.Request) -> httpx.Response:
        calls.append((request.method, str(request.url)))
        path = request.url.path
        if path.endswith('/calendarList'):
            items = [
                {'id': state['google_account'], 'summary': 'Personal', 'primary': True, 'accessRole': 'owner'},
                {'id': 'work@group.calendar.test', 'summary': 'Project team', 'accessRole': 'reader'},
            ]
            if not state['secondary_available']:
                items.pop()
            return httpx.Response(200, json={'items': items})
        primary = '/calendars/primary/' in path
        return httpx.Response(
            200,
            json={
                'items': [
                    {
                        'id': 'shared-event-id',
                        'summary': 'Primary meeting' if primary else 'Team meeting',
                        'start': {'dateTime': '2026-11-10T09:00:00Z'},
                        'end': {'dateTime': '2026-11-10T09:30:00Z'},
                    }
                ]
            },
        )

    app = FastAPI()
    app.include_router(routes.router)

    @app.get('/v1/account/cutover/control')
    def local_account_admission():
        # The native shell requires this bootstrap before allowing UI input.
        # This explicit demo-only legacy account never enters a migration.
        return {
            'schema_version': 1,
            'state': 'legacy',
            'account_generation': 0,
            'ui_generation': 0,
            'api_generation': 0,
            'client_action': 'none',
            'offline_queue_instruction': 'none',
            'stranded_new_data': False,
            'legacy_writes_allowed': True,
            'product_traffic_allowed': True,
            'auth_bootstrap_reachable': True,
        }

    @app.get('/v1/integrations/google_calendar')
    def google_status():
        return integration_routes.get_integration('google_calendar', uid=state['uid'])

    @app.post('/__qa/provider')
    def set_provider_state(values: dict):
        # Fixture-only external-provider faults; this app is never mounted by
        # production and is bound to loopback with a demo Firestore project.
        if any(
            key not in {'connected', 'secondary_available'} or not isinstance(value, bool)
            for key, value in values.items()
        ):
            raise HTTPException(400, 'Unknown fixture setting')
        state.update(values)
        return {'ok': True}

    app.dependency_overrides[routes.auth.get_current_user_uid] = lambda: state['uid']
    get_preferences, save_preferences = preferences.get_selections, preferences.save_selection
    async with httpx.AsyncClient(transport=httpx.MockTransport(provider)) as google:
        with (
            patch.object(
                integration_routes.users_db,
                'get_integration',
                lambda *_: {'connected': state['connected'], 'access_token': 'synthetic-token'},
            ),
            patch.object(google_utils, 'get_auth_client', lambda: google),
            patch.object(preferences, 'get_selections', partial(get_preferences, firestore_client=db)),
            patch.object(preferences, 'save_selection', partial(save_preferences, firestore_client=db)),
        ):
            yield app, state, calls, db
    db.close()


async def main(port: int):
    import uvicorn

    async with calendar_fixture() as (app, _, _, _):
        await uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=port)).serve()


if __name__ == '__main__':
    import asyncio

    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=18196)
    asyncio.run(main(parser.parse_args().port))
