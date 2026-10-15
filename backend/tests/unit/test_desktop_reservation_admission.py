"""Exercise the BFF admission boundary with ASGI, preserving BYOK and other lanes."""

import json

import httpx
import pytest
from fastapi import FastAPI, Request

from config.vertex_reservations import State
from routers import desktop_proxy as proxy
from utils.llm.desktop_reservation_policy import (
    TASK_TOOLS,
    MIN_CAPABLE_BUILD_ENV,
    MIN_TERMINAL_TOOL_BUILD,
    POLICY_ACTIONS,
    should_refuse,
)


@pytest.fixture(autouse=True)
def capable_build(monkeypatch):
    # Hypothetical release threshold, not a product default.
    monkeypatch.setenv(MIN_CAPABLE_BUILD_ENV, '12435')


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
@pytest.mark.parametrize('identity', ['user_agent', 'explicit_headers'])
async def test_refusal_stops_before_metering_or_dispatch_and_is_quiet(app, monkeypatch, stream, identity):
    async def forbidden(*args, **kwargs):
        pytest.fail('refused requests must not be metered or dispatched')

    monkeypatch.setattr(proxy, '_meter_server_request', forbidden)
    monkeypatch.setattr(proxy, '_proxy_via_gateway', forbidden)
    body = {
        'contents': [{'role': 'user', 'parts': [{'text': 'synthetic'}]}],
        'tools': [{'function_declarations': [{'name': n, 'parameters': {'type': 'object'}} for n in TASK_TOOLS]}],
    }
    headers = {'X-Omi-Workload': 'extraction', 'User-Agent': 'Omi/12434 CFNetwork/1.0 Darwin/1.0'}
    if identity == 'explicit_headers':
        # httpx supplies its ordinary transport UA; the explicit identity wins.
        headers = {
            'X-Omi-Workload': 'extraction',
            'X-App-Platform': 'macos',
            'X-App-Version': '0.12.402',
            'X-App-Build': '12402',
        }
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://synthetic') as client:
        action = 'streamGenerateContent' if stream else 'generateContent'
        response = await client.post(
            f'/proxy/gemini-2.5-flash/{action}',
            json=body,
            headers=headers,
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
        'ios_user_agent',
        'browser_user_agent',
        'no_task_tools',
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
        'unset_threshold',
        'invalid_threshold',
        'below_supported',
        'missing_terminal_tool',
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
    elif case == 'ios_user_agent':
        headers['User-Agent'] = 'Omi/1.0.543 (iPhone; iOS 18.0) CFNetwork/1.0 Darwin/1.0'
    elif case == 'browser_user_agent':
        headers['User-Agent'] = (
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 Version/18.0 Safari/605.1.15'
        )
    elif case == 'no_task_tools':
        body.pop('tools')
    elif case == 'unidentified':
        headers.pop('User-Agent')
    elif case == 'current_macos':
        headers['User-Agent'] = 'Omi/12435 CFNetwork/1.0 Darwin/1.0'
    elif case == 'platform_only':
        headers.pop('User-Agent')
        headers['X-App-Platform'] = 'macos'
    elif case == 'unset_threshold':
        monkeypatch.delenv(MIN_CAPABLE_BUILD_ENV)
    elif case == 'invalid_threshold':
        monkeypatch.setenv(MIN_CAPABLE_BUILD_ENV, 'invalid')
    elif case == 'below_supported':
        headers['User-Agent'] = 'Omi/6999 CFNetwork/1.0 Darwin/1.0'
    elif case == 'missing_terminal_tool':
        body['tools'][0]['function_declarations'] = [{'name': n} for n in TASK_TOOLS if n != 'no_task_found']
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
        ({'user-agent': 'Omi/12400 CFNetwork/1.0 Darwin/1.0'}, True),
        ({'user-agent': 'SomethingElse/12434 CFNetwork/1.0 Darwin/1.0'}, False),
        ({'user-agent': 'Omi/12434 CFNetwork/1.0'}, False),
        ({'x-app-platform': 'macos'}, False),
        ({'x-app-platform': 'macos', 'x-app-build': '12402', 'x-app-version': '0.12.402'}, True),
        ({'x-app-platform': 'macos', 'x-app-build': '7000', 'x-app-version': '0.7.0'}, True),
        ({'x-app-platform': 'macos', 'x-app-build': '6999', 'x-app-version': '0.6.999'}, False),
        ({'x-app-platform': 'macos', 'x-app-build': '12402', 'x-app-version': 'invalid'}, False),
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
def test_refusal_requires_positive_macos_identity_below_capable_build(headers, expected):
    from utils.llm.desktop_reservation_policy import desktop_lane

    body = {'tools': [{'functionDeclarations': [{'name': name} for name in TASK_TOOLS]}]}
    headers = {**headers, 'x-omi-workload': 'extraction'}
    assert (desktop_lane(headers, body) == 'macos_legacy_tasks') == expected


@pytest.mark.asyncio
@pytest.mark.parametrize('name', ['Omi', 'Omi%20Beta'])
@pytest.mark.parametrize(
    'build,expected', [(6999, False), (7000, True), (12402, True), (12434, True), (12435, False), (12436, False)]
)
async def test_range_boundaries_and_release_channels(name, build, expected):
    async def inactive():
        return {'gemini-2.5-flash': State.INACTIVE}

    body = json.dumps({'tools': [{'functionDeclarations': [{'name': n} for n in TASK_TOOLS]}]}).encode()
    headers = {'x-omi-workload': 'extraction', 'user-agent': f'{name}/{build} CFNetwork/1.0 Darwin/1.0'}
    assert (
        await should_refuse('gemini-2.5-flash', 'generateContent', body, headers, byok=False, refresh=inactive)
        == expected
    )
    assert MIN_TERMINAL_TOOL_BUILD == 7000


@pytest.mark.asyncio
@pytest.mark.parametrize('control', [None, '', 'garbage', '0', '-1', '12435.0', '1e6', 'true', '2147483648'])
@pytest.mark.parametrize('mode', ['enforce', 'observe'])
async def test_unarmed_control_serves_and_counts_bounded_would_refuse(monkeypatch, control, mode, caplog):
    import logging

    if control is None:
        monkeypatch.delenv(MIN_CAPABLE_BUILD_ENV, raising=False)
    else:
        monkeypatch.setenv(MIN_CAPABLE_BUILD_ENV, control)
    monkeypatch.setenv('OMI_VERTEX_LEGACY_TASK_MODE', mode)

    async def inactive():
        return {'gemini-2.5-flash': State.INACTIVE}

    body = json.dumps({'tools': [{'functionDeclarations': [{'name': n} for n in TASK_TOOLS]}]}).encode()
    headers = {'x-omi-workload': 'extraction', 'user-agent': 'Omi/12402 CFNetwork/1.0 Darwin/1.0'}
    counter = POLICY_ACTIONS.labels('gemini-2.5-flash', 'inactive', 'macos_legacy_tasks', 'would_refuse', '12400_12499')
    before = counter._value.get()
    with caplog.at_level(logging.INFO):
        assert not await should_refuse(
            'gemini-2.5-flash', 'generateContent', body, headers, byok=False, refresh=inactive
        )
    assert counter._value.get() == before + 1
    assert 'build_bucket=12400_12499' in caplog.text
    assert '12402' not in caplog.text and 'CFNetwork' not in caplog.text


@pytest.mark.asyncio
async def test_capable_build_is_read_for_each_request(monkeypatch):
    async def inactive():
        return {'gemini-2.5-flash': State.INACTIVE}

    body = json.dumps({'tools': [{'functionDeclarations': [{'name': n} for n in TASK_TOOLS]}]}).encode()
    headers = {'x-omi-workload': 'extraction', 'user-agent': 'Omi/12402 CFNetwork/1.0 Darwin/1.0'}
    for value, expected in [('12435', True), ('12402', False), ('invalid', False), ('12435', True)]:
        monkeypatch.setenv(MIN_CAPABLE_BUILD_ENV, value)
        assert (
            await should_refuse('gemini-2.5-flash', 'generateContent', body, headers, byok=False, refresh=inactive)
            == expected
        )


@pytest.mark.parametrize(
    'build,bucket',
    [
        (None, 'unidentified'),
        (6999, 'below_supported'),
        (7000, '7000_9999'),
        (10000, '10000_11999'),
        (12000, '12000_12399'),
        (12400, '12400_12499'),
        (12500, '12500_12999'),
        (13000, '13000_plus'),
        (2147483647, '13000_plus'),
    ],
)
def test_build_metric_has_closed_buckets(build, bucket):
    from utils.llm.desktop_reservation_policy import build_bucket

    assert build_bucket(build) == bucket


@pytest.mark.parametrize(
    'agent',
    [
        'Omi/not-a-build CFNetwork/1 Darwin/1',
        'Omi/0 CFNetwork/1 Darwin/1',
        'Omi/2147483648 CFNetwork/1 Darwin/1',
        'Omi/１２４０２ CFNetwork/1 Darwin/1',
        'Omi/12402 CFNetwork/1 Darwin/1 trailing',
    ],
)
def test_unparseable_identity_is_served(agent):
    from utils.llm.desktop_reservation_policy import desktop_lane

    body = {'tools': [{'functionDeclarations': [{'name': n} for n in TASK_TOOLS]}]}
    assert desktop_lane({'x-omi-workload': 'extraction', 'user-agent': agent}, body) == 'desktop_other'


@pytest.mark.parametrize('hint', ['x-app-platform', 'x-app-build', 'x-app-version'])
def test_empty_explicit_identity_hint_is_not_overridden_by_user_agent(hint):
    from utils.llm.desktop_reservation_policy import identified_macos_build

    assert identified_macos_build({'user-agent': 'Omi/12402 CFNetwork/1 Darwin/1', hint: ''}) is None


@pytest.mark.parametrize(
    'agent', ['Omi/not-a-build CFNetwork/1 Darwin/1', 'Omi%20Beta/12403 CFNetwork/1 Darwin/1', 'Omi-windows/12402']
)
def test_explicit_headers_do_not_hide_conflicting_or_malformed_app_identity(agent):
    from utils.llm.desktop_reservation_policy import desktop_lane

    headers = {
        'x-omi-workload': 'extraction',
        'x-app-platform': 'macos',
        'x-app-version': '0.12.402',
        'x-app-build': '12402',
        'user-agent': agent,
    }
    body = {'tools': [{'functionDeclarations': [{'name': n} for n in TASK_TOOLS]}]}
    assert desktop_lane(headers, body) != 'macos_legacy_tasks'
