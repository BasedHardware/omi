"""Bounded lane/workload/client_platform attribution for the desktop Gemini proxy."""

import asyncio
import json
import os
import re
import sys
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from starlette.requests import Request

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

os.environ.setdefault("ENCRYPTION_SECRET", "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv")

from config.desktop_gemini_attribution_generated import (
    GEMINI_CLIENT_PLATFORMS,
    GEMINI_LANES,
    GEMINI_LANE_WIRE_VALUES,
    GEMINI_WORKLOADS,
)
from config.plan_catalog import PlanType
from routers import desktop_proxy
from scripts import generate_desktop_gemini_attribution as generator
from utils.llm import desktop_gemini_gateway
from utils.llm import desktop_gemini_telemetry
from utils.llm import vertex_pt_routing as ptr
from utils.managed_compute import Decision
from utils.other.endpoints import get_current_user_uid

CANONICAL_PATH = BACKEND_DIR / 'config' / 'desktop_gemini_attribution.json'
REPO_ROOT = BACKEND_DIR.parent
MACOS_SOURCES = REPO_ROOT / 'desktop' / 'macos' / 'Desktop' / 'Sources'
WINDOWS_SRC = REPO_ROOT / 'desktop' / 'windows' / 'src'

CANONICAL = json.loads(CANONICAL_PATH.read_text())


def _walk(root: Path, suffixes: tuple[str, ...]) -> list[Path]:
    if not root.exists():
        return []
    return sorted(p for p in root.rglob('*') if p.suffix in suffixes and 'Tests' not in p.parts)


def test_canonical_json_shape():
    assert len(CANONICAL['lanes']) == 13
    assert CANONICAL['workloads'] == ['interactive', 'extraction', 'maintenance']
    assert CANONICAL['platforms'] == ['macos', 'windows', 'other', 'unknown']


def test_canonical_lane_wires_are_bounded_and_unique():
    for key, wire in CANONICAL['lanes'].items():
        assert re.fullmatch(r'[a-z][a-zA-Z0-9]*', key)
        assert re.fullmatch(r'[a-z][a-z0-9_]*', wire)
    assert len(set(CANONICAL['lanes'].values())) == len(CANONICAL['lanes'])


def test_generator_validation_rejects_bad_wire_values():
    good = {'lanes': {'a': 'a_lane'}, 'workloads': ['interactive'], 'platforms': ['unknown']}
    assert generator.validate_attribution(dict(good))['lanes']['a'] == 'a_lane'
    with pytest.raises(AssertionError):
        generator.validate_attribution({'lanes': {'a': 'Has-Caps'}, 'workloads': ['x'], 'platforms': ['unknown']})
    with pytest.raises(AssertionError):
        generator.validate_attribution(
            {'lanes': {'a': 'same', 'b': 'same'}, 'workloads': ['x'], 'platforms': ['unknown']}
        )


def test_generator_render_functions_match_checked_in_artifacts():
    assert generator.render_python(CANONICAL) == generator.PYTHON_PATH.read_text()
    if generator.SWIFT_PATH.exists():
        assert generator.render_swift(CANONICAL) == generator.SWIFT_PATH.read_text()
    if generator.TYPESCRIPT_PATH.exists():
        assert generator.render_typescript(CANONICAL) == generator.TYPESCRIPT_PATH.read_text()


def test_generated_python_matches_canonical_json():
    assert GEMINI_LANE_WIRE_VALUES == CANONICAL['lanes']
    assert set(GEMINI_LANES) == set(CANONICAL['lanes'].values())
    assert sorted(GEMINI_WORKLOADS) == sorted(CANONICAL['workloads'])
    assert sorted(GEMINI_CLIENT_PLATFORMS) == sorted(CANONICAL['platforms'])


def test_generated_swift_matches_canonical_json():
    swift_path = MACOS_SOURCES / 'ProactiveAssistants' / 'Core' / 'GeminiLane.swift'
    if not swift_path.exists():
        pytest.skip('desktop sources are not present in this checkout')
    text = swift_path.read_text()
    lane_block = re.search(r'enum GeminiLane[^\n]*\{(.*?)\}', text, re.DOTALL)
    workload_block = re.search(r'enum GeminiWorkloadClass[^\n]*\{(.*?)\}', text, re.DOTALL)
    assert lane_block and workload_block
    assert dict(re.findall(r'case (\w+) = "([a-z_]+)"', lane_block.group(1))) == CANONICAL['lanes']
    assert sorted(re.findall(r'case (\w+) = "[a-z_]+"', workload_block.group(1))) == sorted(CANONICAL['workloads'])


def test_generated_typescript_matches_canonical_json():
    ts_path = WINDOWS_SRC / 'shared' / 'geminiAttribution.ts'
    if not ts_path.exists():
        pytest.skip('desktop sources are not present in this checkout')
    text = ts_path.read_text()
    lane_block = re.search(r'export const GeminiLane = \{(.*?)\} as const', text, re.DOTALL)
    assert lane_block
    assert dict(re.findall(r"(\w+): '([a-z_]+)'", lane_block.group(1))) == CANONICAL['lanes']
    workload_block = re.search(r'export const GEMINI_WORKLOADS = \[(.*?)\] as const', text, re.DOTALL)
    assert workload_block
    assert sorted(re.findall(r"'([a-z_]+)'", workload_block.group(1))) == sorted(CANONICAL['workloads'])


# Source-inspection ratchet: a GeminiClient init that drops the required `lane`
# fails compilation in app builds, but this ratchet runs in backend CI where no
# Swift compiler exists.
def test_macos_every_gemini_client_init_declares_a_lane():
    offenders = []
    for path in _walk(MACOS_SOURCES, ('.swift',)):
        src = path.read_text()
        for match in re.finditer(r'\bGeminiClient\(', src):
            window = src[match.start() : match.start() + 600]
            if 'lane:' not in window.split(')')[0]:
                offenders.append(f'{path}:{src[: match.start()].count(chr(10)) + 1}')
    assert offenders == []


# Source-inspection ratchet: the URLRequest transports are private to the actor,
# so the shared-header wiring cannot be observed without a live session.
def test_macos_gemini_transports_route_through_the_shared_header_helper():
    core = MACOS_SOURCES / 'ProactiveAssistants' / 'Core' / 'GeminiClient.swift'
    embed = MACOS_SOURCES / 'ProactiveAssistants' / 'Services' / 'EmbeddingService.swift'
    if not core.exists() or not embed.exists():
        pytest.skip('desktop sources are not present in this checkout')
    assert core.read_text().count('applyGeminiProxyHeaders') == 4
    embedding = embed.read_text()
    assert embedding.count('applyGeminiProxyHeaders') == 2
    assert 'lane: .embedding' in embedding
    assert 'workload: .maintenance' in embedding


# Source-inspection ratchet: only the centralized transports may construct the
# proxy path or set the X-Omi-* attribution headers.
def test_no_raw_proxy_url_or_attribution_headers_outside_transport_owners():
    macos_owner = 'ProactiveAssistants/Core/GeminiProxyRequestHeaders.swift'
    windows_owner = 'src/shared/geminiProxy.ts'
    offenders = []
    for path in _walk(MACOS_SOURCES, ('.swift',)):
        rel = path.relative_to(MACOS_SOURCES).as_posix()
        src = path.read_text()
        if rel in {macos_owner, 'ProactiveAssistants/Core/GeminiLane.swift'}:
            pass
        # The DEBUG E2E bridge reads back the headers the shared helper set; it
        # never sets them itself.
        elif rel == 'DesktopAutomationOpenOmiShortcutQA.swift':
            pass
        elif 'X-Omi-Lane' in src or 'X-Omi-Workload' in src:
            offenders.append(str(rel))
        if 'proxy/gemini' in src and rel not in {
            macos_owner,
            'ProactiveAssistants/Core/GeminiClient.swift',
            'ProactiveAssistants/Services/EmbeddingService.swift',
        }:
            offenders.append(str(rel))
    for path in _walk(WINDOWS_SRC, ('.ts', '.tsx')):
        rel = path.relative_to(WINDOWS_SRC.parent).as_posix()
        src = path.read_text()
        if rel.endswith('.test.ts') or rel in {windows_owner, 'src/shared/geminiAttribution.ts'}:
            continue
        if 'proxy/gemini' in src or 'X-Omi-Lane' in src or 'X-Omi-Workload' in src:
            offenders.append(str(rel))
    assert offenders == []


def _decision(*, allowed: bool, reason: str, plan: PlanType | None = PlanType.basic) -> Decision:
    return Decision(
        allowed=allowed,
        reason=reason,
        feature=desktop_proxy._PLAN_GATED_PROXY_FEATURE,
        funding_owner='omi',
        plan=plan,
        plan_resolved=plan is not None,
    )


async def _passthrough_run_blocking(_, function, *args, **kwargs):
    return function(*args, **kwargs)


class _FakeProviderClient:
    def __init__(self, response: httpx.Response) -> None:
        self.response = response

    async def post(self, *args, **kwargs) -> httpx.Response:
        return self.response


def _upstream_ok(path, model, action, query, **kwargs):
    async def inner():
        return desktop_proxy.UpstreamRoute(
            url='https://provider.invalid/v1/models',
            headers={},
            params={},
            provider='vertex_ai',
            credential_source='server',
            region='us-central1',
        )

    return inner()


def _fail_if_invoked(*_args, **_kwargs):
    raise AssertionError('provider dispatch must not run on this path')


async def _return(value):
    return value


@pytest.fixture
def client_app(monkeypatch):
    app = FastAPI()
    app.include_router(desktop_proxy.router)
    app.dependency_overrides[get_current_user_uid] = lambda: 'uid-test'
    monkeypatch.setattr(desktop_proxy, 'run_blocking', _passthrough_run_blocking)
    monkeypatch.setattr(desktop_proxy, 'is_desktop_trial_paywalled', lambda *a, **k: False)
    monkeypatch.setattr(
        desktop_proxy,
        'authorize_managed_compute',
        lambda *a, **k: _decision(allowed=True, reason='plan_paid', plan=PlanType.plus),
    )
    monkeypatch.setattr(desktop_proxy, 'get_byok_key', lambda *a, **k: None)
    monkeypatch.setattr(desktop_proxy, 'llm_stub_enabled', lambda: False)
    monkeypatch.setattr(desktop_proxy, '_meter_server_request', lambda uid, path, m, a: _return(path))
    monkeypatch.setattr(desktop_proxy, '_upstream', _upstream_ok)
    monkeypatch.setattr(desktop_proxy, '_cancel_on_disconnect', lambda req, aw: aw)
    monkeypatch.setattr(desktop_proxy, 'get_desktop_gemini_semaphore', lambda: asyncio.Semaphore(4))
    monkeypatch.setattr(
        desktop_proxy,
        'get_desktop_gemini_client',
        lambda: _FakeProviderClient(
            httpx.Response(200, content=b'{"candidates":[{"content":{"parts":[{"text":"hi"}]}}]}')
        ),
    )
    monkeypatch.setattr(desktop_gemini_telemetry, 'schedule_managed_attempt', lambda *a, **k: True)
    return app


@pytest.fixture
def no_dispatch(client_app, monkeypatch):
    monkeypatch.setattr(desktop_proxy, '_upstream', _fail_if_invoked)
    monkeypatch.setattr(desktop_proxy, 'get_desktop_gemini_client', _fail_if_invoked)
    monkeypatch.setattr(desktop_proxy, 'get_desktop_gemini_stream_client', _fail_if_invoked)
    monkeypatch.setattr(desktop_proxy, '_stream_provider', _fail_if_invoked)
    monkeypatch.setattr(desktop_gemini_gateway, 'proxy_company_paid_via_gateway', _fail_if_invoked)
    monkeypatch.setattr(desktop_gemini_gateway, 'gateway_desktop_chat', _fail_if_invoked)
    monkeypatch.setattr(desktop_gemini_gateway, 'gateway_desktop_chat_stream', _fail_if_invoked)
    monkeypatch.setattr(desktop_gemini_gateway, 'gateway_desktop_embed_content', _fail_if_invoked)
    return client_app


def _events(capsys) -> list[dict]:
    out = capsys.readouterr().out
    return [json.loads(line) for line in out.splitlines() if '"desktop_gemini_proxy_terminal"' in line]


def _body() -> bytes:
    return b'{"contents":[{"parts":[{"text":"hello"}]}]}'


def _success_headers(**extra):
    return {
        'x-app-platform': 'macos',
        'x-omi-lane': 'focus',
        'x-omi-workload': 'extraction',
        'content-length': str(len(_body())),
        **extra,
    }


def test_nonstream_success_emits_one_attributed_terminal(client_app, capsys):
    response = TestClient(client_app).post(
        '/v1/proxy/gemini/models/gemini-2.5-flash:generateContent',
        content=_body(),
        headers=_success_headers(),
    )
    assert response.status_code == 200
    events = _events(capsys)
    assert len(events) == 1
    event = events[0]
    assert event['outcome'] == 'success'
    assert event['model'] == 'gemini-2.5-flash'
    assert event['action'] == 'generateContent'
    assert event['lane'] == 'focus'
    assert event['workload_class'] == 'extraction'
    assert event['client_platform'] == 'macos'


def test_stub_success_emits_one_terminal(client_app, capsys, monkeypatch):
    monkeypatch.setattr(desktop_proxy, 'llm_stub_enabled', lambda: True)
    response = TestClient(client_app).post(
        '/v1/proxy/gemini/models/gemini-2.5-flash:generateContent',
        content=_body(),
        headers=_success_headers(),
    )
    assert response.status_code == 200
    events = _events(capsys)
    assert len(events) == 1
    assert events[0]['outcome'] == 'success'
    assert events[0]['provider_route'] == 'offline_stub'
    assert events[0]['lane'] == 'focus'
    assert events[0]['client_platform'] == 'macos'


def test_auth_rejection_emits_one_terminal(monkeypatch, capsys):
    app = FastAPI()
    app.include_router(desktop_proxy.router)

    def reject():
        raise HTTPException(status_code=401, detail='invalid token')

    app.dependency_overrides[get_current_user_uid] = reject
    response = TestClient(app).post(
        '/v1/proxy/gemini/models/gemini-2.5-flash:generateContent',
        content=_body(),
        headers=_success_headers(),
    )
    assert response.status_code == 401
    assert response.json()['detail'] == 'invalid token'
    events = _events(capsys)
    assert len(events) == 1
    assert events[0]['outcome'] == 'authorization_rejected'
    assert events[0]['phase'] == 'authorization'
    assert events[0]['model'] == 'gemini-2.5-flash'
    assert events[0]['lane'] == 'focus'
    assert events[0]['client_platform'] == 'macos'


def _metering_failure(retryable: bool):
    async def metered(*_args, **_kwargs):
        raise desktop_proxy._GeminiRateLimitExceeded(
            'Gemini request rate limit exceeded', retryable=retryable, retry_after=7
        )

    return metered


# Every rejection phase, on BOTH proxy routes, must emit exactly one terminal
# event with the full bounded attribution — and never reach provider dispatch.
@pytest.mark.parametrize('route', ['/v1/proxy/gemini', '/v1/proxy/gemini-stream'])
@pytest.mark.parametrize(
    'scenario',
    [
        'plan_gated',
        'trial_expired',
        'authorization_unavailable',
        'rate_limited_retryable',
        'rate_limited_terminal',
        'oversized_body',
        'invalid_action',
        'invalid_model',
    ],
)
def test_rejection_emits_one_fully_attributed_terminal(no_dispatch, capsys, monkeypatch, route, scenario):
    action = 'generateContent' if route.endswith('gemini') else 'streamGenerateContent'
    path = f'models/gemini-2.5-flash:{action}'
    headers = _success_headers()
    expected_status = 403
    expected_outcome = 'validation_rejected'
    expected_retryable = False
    expected_model = 'gemini-2.5-flash'
    expected_action = action

    if scenario == 'plan_gated':
        monkeypatch.setattr(
            desktop_proxy,
            'authorize_managed_compute',
            lambda *a, **k: _decision(allowed=False, reason='basic_not_entitled'),
        )
        expected_status = 402
        expected_outcome = 'plan_gated'
    elif scenario == 'trial_expired':
        monkeypatch.setattr(desktop_proxy, 'is_desktop_trial_paywalled', lambda *a, **k: True)
        expected_status = 402
        expected_outcome = 'trial_expired'
    elif scenario == 'authorization_unavailable':
        monkeypatch.setattr(
            desktop_proxy,
            'authorize_managed_compute',
            lambda *a, **k: _decision(allowed=False, reason='authorization_unavailable', plan=None),
        )
        expected_status = 503
        expected_outcome = 'authorization_unavailable'
    elif scenario.startswith('rate_limited'):
        retryable = scenario == 'rate_limited_retryable'
        monkeypatch.setattr(desktop_proxy, '_meter_server_request', _metering_failure(retryable))
        expected_status = 429
        expected_outcome = 'rate_limited'
        expected_retryable = retryable
    elif scenario == 'oversized_body':
        headers = {**headers, 'content-length': '99999999'}
        expected_status = 413
    elif scenario == 'invalid_action':
        path = 'models/gemini-2.5-flash:deleteModel'
        expected_action = 'unknown'
    elif scenario == 'invalid_model':
        path = f'models/gemini-9-bogus:{action}'
        expected_model = 'unknown'

    response = TestClient(no_dispatch).post(f'{route}/{path}', content=_body(), headers=headers)
    assert response.status_code == expected_status
    if scenario == 'plan_gated':
        assert response.json()['detail']['error'] == 'plan_gated'
    elif scenario == 'trial_expired':
        assert response.json()['detail'] == 'trial_expired'

    events = _events(capsys)
    assert len(events) == 1
    event = events[0]
    assert event['outcome'] == expected_outcome
    assert event['status_code'] == expected_status
    assert event['retryable'] is expected_retryable
    assert event['model'] == expected_model
    assert event['action'] == expected_action
    assert event['lane'] == 'focus'
    assert event['workload_class'] == 'extraction'
    assert event['client_platform'] == 'macos'


def test_gateway_success_reuses_one_telemetry(client_app, capsys, monkeypatch):
    monkeypatch.setattr(desktop_gemini_gateway, 'should_route_features_through_gateway', lambda: True)

    async def fake_chat(body, *, model, action, uid):
        return desktop_gemini_gateway.GatewayChatResult(
            gemini_payload={'candidates': [{'content': {'parts': [{'text': 'hi'}]}}]}
        )

    monkeypatch.setattr(desktop_gemini_gateway, 'gateway_desktop_chat', fake_chat)
    response = TestClient(client_app).post(
        '/v1/proxy/gemini/models/gemini-2.5-flash:generateContent',
        content=_body(),
        headers=_success_headers(),
    )
    assert response.status_code == 200
    events = _events(capsys)
    assert len(events) == 1
    assert events[0]['outcome'] == 'success'
    assert events[0]['provider_route'] == 'llm_gateway'
    assert events[0]['phase'] == 'gateway'
    assert events[0]['lane'] == 'focus'
    assert events[0]['client_platform'] == 'macos'


def test_gateway_failure_reuses_one_telemetry(client_app, capsys, monkeypatch):
    monkeypatch.setattr(desktop_gemini_gateway, 'should_route_features_through_gateway', lambda: True)

    async def fake_chat(body, *, model, action, uid):
        raise desktop_gemini_gateway.DesktopGeminiGatewayError(
            status_code=500, code='gateway_unavailable', message='gateway is down'
        )

    monkeypatch.setattr(desktop_gemini_gateway, 'gateway_desktop_chat', fake_chat)
    response = TestClient(client_app).post(
        '/v1/proxy/gemini/models/gemini-2.5-flash:generateContent',
        content=_body(),
        headers=_success_headers(),
    )
    assert response.status_code == 503
    events = _events(capsys)
    assert len(events) == 1
    assert events[0]['outcome'] == 'gateway_unavailable'
    assert events[0]['phase'] == 'gateway'
    assert events[0]['lane'] == 'focus'
    assert events[0]['client_platform'] == 'macos'


def test_legacy_preview_model_resolves_for_telemetry(client_app, capsys):
    response = TestClient(client_app).post(
        '/v1/proxy/gemini/models/gemini-3-flash-preview:generateContent',
        content=_body(),
        headers=_success_headers(),
    )
    assert response.status_code == 200
    events = _events(capsys)
    assert len(events) == 1
    assert events[0]['model'] == ptr.PT_MODEL_CURRENT


def test_missing_lane_with_known_platform(client_app, capsys):
    headers = {k: v for k, v in _success_headers().items() if k != 'x-omi-lane'}
    response = TestClient(client_app).post(
        '/v1/proxy/gemini/models/gemini-2.5-flash:generateContent',
        content=_body(),
        headers=headers,
    )
    assert response.status_code == 200
    events = _events(capsys)
    assert len(events) == 1
    assert events[0]['lane'] == 'unknown'
    assert events[0]['client_platform'] == 'macos'


def test_lane_header_normalization_is_bounded(client_app, capsys):
    response = TestClient(client_app).post(
        '/v1/proxy/gemini/models/gemini-2.5-flash:generateContent',
        content=_body(),
        headers=_success_headers(**{'x-omi-lane': '  Focus  ', 'x-omi-workload': ' Extraction '}),
    )
    assert response.status_code == 200
    events = _events(capsys)
    assert len(events) == 1
    assert events[0]['lane'] == 'focus'
    assert events[0]['workload_class'] == 'extraction'


def test_arbitrary_headers_never_reach_the_event(client_app, capsys):
    response = TestClient(client_app).post(
        '/v1/proxy/gemini/models/gemini-2.5-flash:generateContent',
        content=_body(),
        headers={
            **_success_headers(),
            'x-private-secret': 'hunter2-secret-value',
            'x-customer-note': 'please-do-not-log-me',
        },
    )
    assert response.status_code == 200
    out = capsys.readouterr().out
    assert 'hunter2-secret-value' not in out
    assert 'please-do-not-log-me' not in out
    assert 'x-private-secret' not in out


@pytest.mark.parametrize(
    ('headers', 'expected'),
    [
        ({'x-app-platform': 'macos'}, 'macos'),
        ({'x-app-platform': 'windows'}, 'windows'),
        ({'x-app-platform': 'linux'}, 'other'),
        ({'x-app-platform': 'fuchsia'}, 'unknown'),
        ({'x-app-platform': 'desktop'}, 'unknown'),
        ({'user-agent': 'CFNetwork/1568.100.1 Darwin/24.0.0'}, 'macos'),
        ({'user-agent': 'Electron/33.2.0 (Windows NT 10.0; win32)'}, 'windows'),
        ({'user-agent': 'openai/js 4.0.0'}, 'unknown'),
        ({'user-agent': 'Dart/3.5 (dart:io)'}, 'other'),
        (
            {'x-app-platform': 'bogus-os', 'user-agent': 'CFNetwork/1568.100.1 Darwin/24.0.0'},
            'unknown',
        ),
    ],
)
def test_platform_mapping(client_app, capsys, headers, expected):
    sent = {k: v for k, v in _success_headers().items() if k != 'x-app-platform'}
    sent.update(headers)
    response = TestClient(client_app).post(
        '/v1/proxy/gemini/models/gemini-2.5-flash:generateContent',
        content=_body(),
        headers=sent,
    )
    assert response.status_code == 200
    events = _events(capsys)
    assert len(events) == 1
    assert events[0]['client_platform'] == expected


def test_unknown_lane_value_is_bounded(client_app, capsys):
    response = TestClient(client_app).post(
        '/v1/proxy/gemini/models/gemini-2.5-flash:generateContent',
        content=_body(),
        headers=_success_headers(**{'x-omi-lane': 'totally_made_up_lane'}),
    )
    assert response.status_code == 200
    events = _events(capsys)
    assert events[0]['lane'] == 'unknown'


def test_streaming_success_emits_one_terminal(client_app, capsys, monkeypatch):
    def fake_stream(request, route, body, telemetry, **_kwargs):
        async def gen():
            yield b'data: {"candidates":[]}\n\n'
            telemetry.complete(outcome='success', status_code=200, retryable=False, phase='body')

        return gen()

    monkeypatch.setattr(desktop_proxy, '_stream_provider', fake_stream)
    with TestClient(client_app) as client:
        response = client.post(
            '/v1/proxy/gemini-stream/models/gemini-2.5-flash:streamGenerateContent',
            content=_body(),
            headers=_success_headers(),
        )
        assert response.status_code == 200
    events = _events(capsys)
    assert len(events) == 1
    assert events[0]['outcome'] == 'success'
    assert events[0]['route'] == 'stream'
    assert events[0]['action'] == 'streamGenerateContent'
    assert events[0]['lane'] == 'focus'


def test_streaming_unfinished_iterator_reports_incomplete(client_app, capsys, monkeypatch):
    def fake_stream(*_args, **_kwargs):
        async def gen():
            yield b'data: {"candidates":[]}\n\n'

        return gen()

    monkeypatch.setattr(desktop_proxy, '_stream_provider', fake_stream)
    with TestClient(client_app) as client:
        response = client.post(
            '/v1/proxy/gemini-stream/models/gemini-2.5-flash:streamGenerateContent',
            content=_body(),
            headers=_success_headers(),
        )
        assert response.status_code == 200
    events = _events(capsys)
    assert len(events) == 1
    assert events[0]['outcome'] == 'incomplete_stream'
    assert events[0]['status_code'] == 502


def _telemetry():
    request = Request(
        {
            'type': 'http',
            'method': 'POST',
            'path': '/v1/proxy/gemini-stream/x',
            'query_string': b'',
            'headers': [(b'x-app-platform', b'macos')],
        }
    )
    return desktop_gemini_telemetry.ProxyTelemetry(request, streaming=True)


@pytest.mark.asyncio
async def test_stream_guard_completes_on_early_termination(capsys):
    telemetry = _telemetry()
    inner_closed = asyncio.Event()

    async def gen():
        try:
            yield b'chunk-1'
            yield b'chunk-2'
        finally:
            inner_closed.set()

    iterator = desktop_gemini_telemetry._terminal_stream_guard(gen(), telemetry)
    assert await iterator.__anext__() == b'chunk-1'
    await iterator.aclose()
    assert inner_closed.is_set()
    events = _events(capsys)
    assert len(events) == 1
    assert events[0]['outcome'] == 'client_cancelled'


@pytest.mark.asyncio
async def test_stream_guard_closes_custom_iterator_on_early_termination(capsys):
    telemetry = _telemetry()

    class CustomIterator:
        def __init__(self):
            self.closed = False
            self.served = False

        def __aiter__(self):
            return self

        async def __anext__(self):
            if self.served:
                raise StopAsyncIteration
            self.served = True
            return b'chunk'

        async def aclose(self):
            self.closed = True

    inner = CustomIterator()
    iterator = desktop_gemini_telemetry._terminal_stream_guard(inner, telemetry)
    assert await iterator.__anext__() == b'chunk'
    await iterator.aclose()
    assert inner.closed
    events = _events(capsys)
    assert len(events) == 1
    assert events[0]['outcome'] == 'client_cancelled'


@pytest.mark.asyncio
async def test_stream_guard_reports_unfinished_iterator_as_incomplete(capsys):
    telemetry = _telemetry()

    async def gen():
        yield b'chunk-1'

    iterator = desktop_gemini_telemetry._terminal_stream_guard(gen(), telemetry)
    assert await iterator.__anext__() == b'chunk-1'
    with pytest.raises(StopAsyncIteration):
        await iterator.__anext__()
    events = _events(capsys)
    assert len(events) == 1
    assert events[0]['outcome'] == 'incomplete_stream'
    assert events[0]['status_code'] == 502


@pytest.mark.asyncio
async def test_stream_guard_completes_on_iterator_error(capsys):
    telemetry = _telemetry()

    async def gen():
        yield b'chunk-1'
        raise RuntimeError('provider dropped mid-stream')

    iterator = desktop_gemini_telemetry._terminal_stream_guard(gen(), telemetry)
    assert await iterator.__anext__() == b'chunk-1'
    with pytest.raises(RuntimeError):
        await iterator.__anext__()
    events = _events(capsys)
    assert len(events) == 1
    assert events[0]['outcome'] == 'stream_iterator_error'


@pytest.mark.asyncio
async def test_stream_guard_completes_on_cancellation(capsys):
    telemetry = _telemetry()
    entered = asyncio.Event()
    release = asyncio.Event()

    async def gen():
        yield b'chunk-1'
        entered.set()
        await release.wait()
        yield b'never'

    async def consume():
        async for _ in desktop_gemini_telemetry._terminal_stream_guard(gen(), telemetry):
            pass

    task = asyncio.create_task(consume())
    await entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    events = _events(capsys)
    assert len(events) == 1
    assert events[0]['outcome'] == 'client_cancelled'


@pytest.mark.asyncio
async def test_stream_guard_no_double_complete(capsys):
    telemetry = _telemetry()
    telemetry.complete(outcome='success', status_code=200, retryable=False, phase='body')

    async def gen():
        yield b'x'
        raise RuntimeError('boom')

    iterator = desktop_gemini_telemetry._terminal_stream_guard(gen(), telemetry)
    await iterator.__anext__()
    with pytest.raises(RuntimeError):
        await iterator.__anext__()
    events = _events(capsys)
    assert len(events) == 1
    assert events[0]['outcome'] == 'success'
