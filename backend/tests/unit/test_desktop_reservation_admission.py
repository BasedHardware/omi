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
            f'/proxy/gemini-2.5-flash/{action}',
            json=body,
            headers={'X-Omi-Workload': 'extraction', 'User-Agent': 'Omi/12434 CFNetwork/1.0 Darwin/1.0'},
        )
    assert response.status_code == 200
    assert response.headers['x-omi-retryable'] == 'false'
    assert response.headers['x-omi-error-class'] == 'legacy_task_reservation_inactive'
    assert response.headers['x-omi-reservation-state'] == 'inactive'
    payload = json.loads(response.text.removeprefix('data: ').strip())
    assert payload['candidates'][0]['content']['parts'][0]['functionCall']['name'] == 'no_task_found'


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'case',
    [
        'windows',
        'untagged',
        'dictation',
        'lite',
        'pro',
        'byok',
        'observe',
        'unknown',
        'lite_pin',
        'unidentified',
        'current_macos',
        'platform_only',
    ],
)
async def test_other_lanes_and_rollback_reach_existing_dispatch(app, monkeypatch, case):
    # Meter sentinel proves admission was allowed without touching a provider.
    reached = []

    async def meter(*args):
        reached.append(True)
        raise proxy.HTTPException(status_code=418, detail='synthetic admission sentinel')

    monkeypatch.setattr(proxy, '_meter_server_request', meter)
    model = 'gemini-2.5-flash'
    headers = {'X-Omi-Workload': 'extraction', 'User-Agent': 'Omi/12434 CFNetwork/1.0 Darwin/1.0'}
    body = {
        'contents': [{'parts': [{'text': 'synthetic'}]}],
        'tools': [{'function_declarations': [{'name': n, 'parameters': {'type': 'object'}} for n in TASK_TOOLS]}],
    }
    if case == 'windows':
        headers['X-App-Platform'] = 'windows'
    elif case == 'unidentified':
        headers.pop('User-Agent')
    elif case == 'current_macos':
        headers['User-Agent'] = 'Omi/12435 CFNetwork/1.0 Darwin/1.0'
    elif case == 'platform_only':
        headers.pop('User-Agent')
        headers['X-App-Platform'] = 'macos'
    elif case == 'untagged':
        headers = {}
    elif case == 'lite_pin':
        monkeypatch.setenv('OMI_VERTEX_PT_MODEL', 'gemini-3.1-flash-lite')

        async def no_evidence():
            return {}

        monkeypatch.setattr(proxy, '_refresh_reservations', no_evidence)
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


@pytest.mark.parametrize(
    'headers,expected',
    [
        ({'user-agent': 'Omi/12434 CFNetwork/3896.100.1.1.1 Darwin/27.0.0'}, True),
        ({'user-agent': 'Omi%20Beta/12425 CFNetwork/1.0 Darwin/1.0'}, True),
        ({'user-agent': 'Omi/12435 CFNetwork/1.0 Darwin/1.0'}, False),
        ({'user-agent': 'Omi/99999 CFNetwork/1.0 Darwin/1.0'}, False),
        ({'user-agent': 'Omi/12400 CFNetwork/1.0 Darwin/1.0'}, False),
        ({'user-agent': 'SomethingElse/12434 CFNetwork/1.0 Darwin/1.0'}, False),
        ({'user-agent': 'Omi/12434 CFNetwork/1.0'}, False),
        ({'x-app-platform': 'macos'}, False),
        ({'x-app-platform': 'macos', 'x-app-build': '12434', 'x-app-version': '0.12.434'}, True),
        ({'x-app-build': '12434', 'x-app-version': '0.12.434'}, False),
        ({'x-app-platform': 'macos', 'x-app-build': '12435', 'x-app-version': '0.12.435'}, False),
        ({'user-agent': 'Omi/12434 CFNetwork/1.0 Darwin/1.0', 'x-app-platform': 'windows'}, False),
        ({'user-agent': 'Omi/12434 CFNetwork/1.0 Darwin/1.0', 'x-app-version': '0.12.435'}, False),
        (
            {
                'user-agent': 'Omi/12435 CFNetwork/1.0 Darwin/1.0',
                'x-app-platform': 'macos',
                'x-app-build': '12434',
                'x-app-version': '0.12.434',
            },
            False,
        ),
    ],
)
def test_refusal_requires_positive_audited_legacy_macos_identity(headers, expected):
    from utils.llm.desktop_reservation_policy import desktop_lane

    body = {'tools': [{'functionDeclarations': [{'name': name} for name in TASK_TOOLS]}]}
    headers = {**headers, 'x-omi-workload': 'extraction'}
    assert (desktop_lane(headers, body) == 'macos_legacy_tasks') == expected
