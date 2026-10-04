"""Review regressions: telemetry-only identity and attributable attempt cost."""

import asyncio
import json
from uuid import UUID

import httpx
import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from starlette.requests import Request

from database import users
from llm_gateway.gateway.accounting import (
    AccountingContext,
    AttemptTrace,
    ProviderResponseMetadata,
    ProviderUsage,
    build_accounting_event,
)
from llm_gateway.gateway.auth import ServiceCaller
from llm_gateway.gateway.executor import ProviderRegistry
from llm_gateway.gateway.providers import FakeChatCompletionProvider, ProviderResponse
from llm_gateway.main import app as gateway_app
from llm_gateway.routers import dependencies, embeddings, openai_compatible
from utils.llm import desktop_gemini_gateway as dgg, desktop_gemini_telemetry as telemetry_module
from utils.llm.managed_spend_ledger import build_managed_attempt_event
from utils.other import endpoints

REQUEST_ID = 'b87d6cf8-c82d-48d3-90d3-c0350a7c9d19'


def telemetry(headers=None):
    return telemetry_module.ProxyTelemetry(
        Request({'type': 'http', 'headers': [(k.encode(), v.encode()) for k, v in (headers or {}).items()]}),
        streaming=False,
    )


@pytest.mark.parametrize('header', ['x-omi-request-id', 'x-request-id'])
@pytest.mark.parametrize(
    'supplied',
    [
        REQUEST_ID,
        REQUEST_ID.upper(),
        'PrivateUserUid12345',
        REQUEST_ID.replace('-', ''),
        '{' + REQUEST_ID + '}',
        'bad',
        '',
    ],
)
def test_request_ids_are_canonical_uuids_only(header, supplied, capsys):
    state = telemetry({header: supplied})
    assert str(UUID(state.request_id)) == state.request_id
    if supplied.lower() == REQUEST_ID:
        assert state.request_id == REQUEST_ID
    else:
        assert state.request_id != supplied
    state.complete(outcome='success', status_code=200, retryable=False)
    event = json.loads(capsys.readouterr().out)
    assert event['request_id'] == state.request_id
    if supplied == 'PrivateUserUid12345':
        assert supplied not in json.dumps(event)


@pytest.mark.parametrize(
    ('supplied', 'expected'),
    [
        ('macos', 'macos'),
        (' WINDOWS ', 'windows'),
        ('linux', 'other'),
        ('bogus-user-value', 'unknown'),
        ('', 'unknown'),
    ],
)
def test_telemetry_platform_is_bounded_and_precedes_legacy_identity(supplied, expected):
    state = telemetry({'x-omi-client-platform': supplied, 'x-app-platform': 'windows'})
    assert state.client_platform == expected


def test_telemetry_platform_does_not_activate_auth_platform_io(monkeypatch):
    monkeypatch.setattr(endpoints, 'verify_token', lambda token: 'synthetic-user')
    monkeypatch.setattr(endpoints, 'enforce_account_deletion_http_access', lambda uid: None)
    monkeypatch.setattr(endpoints, '_enforce_cutover_http_if_request', lambda *args: None)
    monkeypatch.setattr(endpoints, 'validate_byok_request', lambda uid: None)
    monkeypatch.setattr(users, 'try_acquire_user_platform_write_lock', lambda *args: pytest.fail('platform Redis IO'))
    monkeypatch.setattr(users, 'db', object())  # Any Firestore access would also fail.
    app = FastAPI()

    @app.get('/auth')
    def protected(request: Request, uid: str = Depends(endpoints.get_current_user_uid)):
        return {'platform': telemetry_module.ProxyTelemetry(request, streaming=False).client_platform}

    response = TestClient(app).get(
        '/auth', headers={'Authorization': 'Bearer synthetic-token', 'X-Omi-Client-Platform': 'macos'}
    )
    assert response.status_code == 200
    assert response.json() == {'platform': 'macos'}


class AttributionProvider(FakeChatCompletionProvider):
    async def stream_chat_completion(self, request, **kwargs):
        yield b'data: {"choices":[{"delta":{"content":"ok"}}]}\n\n'
        yield b'data: {"choices":[{"delta":{},"finish_reason":"stop"}],"usage":{"prompt_tokens":12,"completion_tokens":2,"total_tokens":14}}\n\n'
        yield b'data: [DONE]\n\n'

    async def create_embedding(self, request, **kwargs):
        return ProviderResponse(
            response={'data': [{'index': 0, 'object': 'embedding', 'embedding': [0.1, 0.2]}], 'object': 'list'},
            accounting=ProviderResponseMetadata(usage=ProviderUsage(prompt_tokens=12, uncached_input_tokens=12)),
        )


@pytest.fixture
def gateway_transport(monkeypatch):
    monkeypatch.setenv('OMI_LLM_GATEWAY_SERVICE_TOKEN', 'synthetic-service-token')
    monkeypatch.setenv('OMI_LLM_GATEWAY_URL', 'http://gateway.test')
    provider = AttributionProvider(
        [
            {
                'choices': [{'message': {'content': 'ok'}, 'finish_reason': 'stop'}],
                'usage': {'prompt_tokens': 12, 'completion_tokens': 2, 'total_tokens': 14},
            }
        ]
    )
    monkeypatch.setitem(
        gateway_app.dependency_overrides,
        dependencies.get_provider_registry,
        lambda: ProviderRegistry({'gemini': provider}),
    )
    rows = []

    def capture(context, trace):
        rows.extend(build_accounting_event(context, attempt).as_dict() for attempt in trace.attempts)

    monkeypatch.setattr(openai_compatible, 'schedule_attempt_trace', capture)
    monkeypatch.setattr(embeddings, 'schedule_attempt_trace', capture)
    monkeypatch.setattr(dgg, 'get_llm_gateway_semaphore', lambda: asyncio.Semaphore(1))
    return rows


@pytest.mark.asyncio
@pytest.mark.parametrize('surface', ['chat', 'stream', 'embed'])
async def test_gateway_attempts_keep_lane_platform_and_proxy_request_id(monkeypatch, gateway_transport, surface):
    state = telemetry({'x-omi-request-id': REQUEST_ID, 'x-omi-lane': 'focus', 'x-omi-client-platform': 'windows'})
    attribution = dict(
        uid='synthetic-user',
        request_id=state.request_id,
        product_lane=state.lane,
        client_platform=state.client_platform,
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=gateway_app), base_url='http://gateway.test'
    ) as client:
        monkeypatch.setattr(dgg, 'get_llm_gateway_client', lambda: client)
        if surface == 'embed':
            result = await dgg.gateway_desktop_embed_content(
                b'{"content":{"parts":[{"text":"synthetic"}]}}', **attribution
            )
            assert result.values == [0.1, 0.2]
        elif surface == 'stream':
            chunks = [
                chunk
                async for chunk in dgg.gateway_desktop_chat_stream(
                    b'{"contents":[{"parts":[{"text":"synthetic"}]}]}', model='gemini-2.5-flash', **attribution
                )
            ]
            assert b'ok' in b''.join(chunks)
        else:
            result = await dgg.gateway_desktop_chat(
                b'{"contents":[{"parts":[{"text":"synthetic"}]}]}',
                model='gemini-2.5-flash',
                action='generateContent',
                **attribution
            )
            assert result.gemini_payload['candidates'][0]['content']['parts'][0]['text'] == 'ok'
    assert len(gateway_transport) == 1
    row = gateway_transport[0]
    assert row['request_id'] == state.request_id
    assert row['feature'] == 'desktop_proactivity'
    assert row['app_platform'] == 'desktop'
    assert row['product_lane'] == 'focus'
    assert row['client_platform'] == 'windows'
    assert row['prompt_tokens'] == 12
    if surface == 'embed':
        # Existing rate cards do not price gemini-embedding-001. Preserve its
        # unpriced status while retaining usage and attribution.
        assert row['cost_status'] == 'unpriced'
    else:
        assert row['estimated_cost_micro_usd'] is not None


@pytest.mark.parametrize(
    ('lane', 'platform', 'expected_lane', 'expected_platform'),
    [
        (' focus ', ' WINDOWS ', 'focus', 'windows'),
        ('PrivateUserUid12345', 'secret', 'unknown', 'unknown'),
        ('', '', 'unknown', 'unknown'),
        (None, None, None, None),
    ],
)
def test_gateway_accounting_bounds_tags_without_changing_feature(lane, platform, expected_lane, expected_platform):
    caller = ServiceCaller(
        name='backend',
        usage_feature='desktop_proactivity',
        app_platform='desktop',
        product_lane=lane,
        client_platform=platform,
    )
    context = openai_compatible._accounting_context(
        request_id=REQUEST_ID,
        caller=caller,
        api_surface='openai_chat_completions',
        payer='omi',
        fallback_feature='unused',
    )
    trace = AttemptTrace()
    attempt = trace.record(
        provider='gemini',
        configured_model='gemini-2.5-flash',
        route_artifact_id=None,
        fallback_reason=None,
        retry_ordinal=1,
        outcome='success',
        error_class='none',
    )
    row = build_accounting_event(context, attempt).as_dict()
    assert row['product_lane'] == expected_lane
    assert row['client_platform'] == expected_platform
    assert row['feature'] == 'desktop_proactivity'
    # The event boundary also bounds tags from non-HTTP callers.
    raw_context = AccountingContext.create(
        request_id=REQUEST_ID,
        caller='backend',
        user_uid=None,
        feature='desktop_proactivity',
        api_surface='test',
        payer='omi',
        product_lane=lane,
        client_platform=platform,
    )
    raw_row = build_accounting_event(raw_context, attempt).as_dict()
    assert raw_row['product_lane'] == expected_lane
    assert raw_row['client_platform'] == expected_platform


def test_direct_attempt_rows_keep_the_same_bounded_tags(monkeypatch):
    attempts = []
    monkeypatch.setattr(telemetry_module, 'schedule_managed_attempt', attempts.append)
    state = telemetry({'x-omi-lane': 'memory', 'x-omi-client-platform': 'macos'})
    state.uid = 'synthetic-user'
    state.identify('models/gemini-2.5-flash:generateContent')
    state.note_dispatch(telemetry_module.UpstreamRoute('http://provider.test', {}, {}, 'vertex_ai', 'server', 'us'))
    state.record_attempt('success', 'none')
    row = build_managed_attempt_event(attempts[0]).as_dict()
    assert row['request_id'] == state.request_id
    assert row['feature'] == 'desktop_proactivity'
    assert row['product_lane'] == 'memory'
    assert row['client_platform'] == 'macos'
