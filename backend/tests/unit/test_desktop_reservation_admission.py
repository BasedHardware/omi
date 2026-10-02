"""Exercise the BFF admission boundary with ASGI, preserving BYOK and other lanes."""

import json

import httpx
import pytest
from fastapi import FastAPI, Request

from config.vertex_reservations import State
from routers import desktop_proxy as proxy
from utils.llm.desktop_reservation_policy import TASK_TOOLS


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setattr(proxy, 'get_byok_key', lambda _: None)
    monkeypatch.setattr(proxy, 'llm_stub_enabled', lambda: False)

    async def states():
        return {'gemini-2.5-flash': State.INACTIVE}

    monkeypatch.setattr(proxy, '_refresh_reservations', states)
    app = FastAPI()

    @app.post('/proxy/{model}/{action}')
    async def endpoint(model: str, action: str, request: Request):
        return await proxy._proxy(request, f'models/{model}:{action}', action == 'streamGenerateContent', 'synthetic')

    return app


@pytest.mark.asyncio
@pytest.mark.parametrize('stream', [False, True])
async def test_refusal_stops_before_metering_or_dispatch_and_is_quiet(app, monkeypatch, stream):
    async def forbidden(*args, **kwargs):
        pytest.fail('refused requests must not be metered or dispatched')

    monkeypatch.setattr(proxy, '_meter_server_request', forbidden)
    monkeypatch.setattr(proxy, '_proxy_via_gateway', forbidden)
    body = {
        'contents': [{'role': 'user', 'parts': [{'text': 'synthetic'}]}],
        'tools': [{'function_declarations': [{'name': n, 'parameters': {'type': 'object'}} for n in TASK_TOOLS]}],
    }
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://synthetic') as client:
        action = 'streamGenerateContent' if stream else 'generateContent'
        response = await client.post(
            f'/proxy/gemini-2.5-flash/{action}', json=body, headers={'X-Omi-Workload': 'extraction'}
        )
    assert response.status_code == 200
    assert response.headers['x-omi-retryable'] == 'false'
    assert response.headers['x-omi-error-class'] == 'legacy_task_reservation_inactive'
    assert response.headers['x-omi-reservation-state'] == 'inactive'
    payload = json.loads(response.text.removeprefix('data: ').strip())
    assert payload['candidates'][0]['content']['parts'][0]['functionCall']['name'] == 'no_task_found'


@pytest.mark.asyncio
@pytest.mark.parametrize('case', ['windows', 'dictation', 'lite', 'pro', 'byok', 'observe', 'unknown'])
async def test_other_lanes_and_rollback_reach_existing_dispatch(app, monkeypatch, case):
    # Meter sentinel proves admission was allowed without touching a provider.
    reached = []

    async def meter(*args):
        reached.append(True)
        raise proxy.HTTPException(status_code=418, detail='synthetic admission sentinel')

    monkeypatch.setattr(proxy, '_meter_server_request', meter)
    model = 'gemini-2.5-flash'
    headers = {'X-Omi-Workload': 'extraction'}
    body = {
        'contents': [{'parts': [{'text': 'synthetic'}]}],
        'tools': [{'function_declarations': [{'name': n, 'parameters': {'type': 'object'}} for n in TASK_TOOLS]}],
    }
    if case == 'windows':
        headers = {}
    elif case == 'dictation':
        body.pop('tools')
        headers = {'X-Omi-Workload': 'interactive'}
    elif case in {'lite', 'pro'}:
        model = 'gemini-2.5-flash-lite' if case == 'lite' else 'gemini-2.5-pro'
    elif case == 'byok':
        monkeypatch.setattr(proxy, 'get_byok_key', lambda _: 'synthetic-byok')

        async def forbidden():
            pytest.fail('BYOK must not read reservation state')

        monkeypatch.setattr(proxy, '_refresh_reservations', forbidden)
    elif case == 'observe':
        monkeypatch.setenv('OMI_VERTEX_LEGACY_TASK_MODE', 'observe')
    else:

        async def unknown():
            return {}

        monkeypatch.setattr(proxy, '_refresh_reservations', unknown)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://synthetic') as client:
        response = await client.post(f'/proxy/{model}/generateContent', json=body, headers=headers)
    assert response.status_code == 418 and reached == [True]
