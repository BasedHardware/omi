"""Real dirty hook, encrypted storage, transport lanes and canary failure attribution offline."""

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock

import httpx
import pytest
import yaml
from fastapi import FastAPI
from fastapi.testclient import TestClient

from llm_gateway.gateway.config_loader import load_gateway_config
from llm_gateway.gateway.executor import ProviderRegistry, provider_request_for
from llm_gateway.gateway.providers import VertexGeminiProvider, OpenAICompatibleChatCompletionProvider
from llm_gateway.gateway.resolver import resolve_chat_completion_route
from llm_gateway.gateway.vertex_wire import _vertex_request
from llm_gateway.main import app as gateway_app
from llm_gateway.routers import dependencies
from config.vertex_reservations import State
from utils.llm import vertex_pt_routing as ptr

from config.dream_agent import eligible
from database import dream_canary as storage, dream_store, conversations
from routers import dream_sweep
from tests.support.dream_firestore import DreamFirestore
from tests.support.vertex_contract import assert_vertex_subset, assert_local_references
from utils import dream_canary, dream_reads, dream_transport, dream_agent

UID = 'dream-canary-synthetic'


@pytest.fixture
def store(monkeypatch):
    db = DreamFirestore()
    monkeypatch.setenv('DREAM_AGENT_MODE', 'on')
    monkeypatch.setenv('DREAM_AGENT_CANARY_UID', UID)
    monkeypatch.setenv('DREAM_AGENT_UID_ALLOWLIST', UID)
    monkeypatch.setenv('REVIEW_SURFACE_MODE', 'off')
    monkeypatch.setattr(dream_store, 'get_firestore_client', lambda: db)
    monkeypatch.setattr(storage, 'get_firestore_client', lambda: db)
    monkeypatch.setattr(conversations, 'db', db)
    monkeypatch.setattr(conversations, 'invalidate_people_stats_cache', lambda *a: None)
    monkeypatch.setattr(conversations, '_sync_conversation_search_index', lambda *a: None)
    monkeypatch.setattr(dream_store.firestore, 'transactional', lambda fn: fn)
    monkeypatch.setattr(dream_store, 'vocabulary', lambda *a: [])
    monkeypatch.setattr(dream_store, 'demoted_types', lambda *a: set())
    monkeypatch.setattr(dream_agent.review_store, 'remaining_today', lambda *a: 3)
    monkeypatch.setattr(dream_reads.screen_activity, 'get_screen_activity', lambda *a, **k: [])

    async def post(url, **kwargs):
        body = kwargs['json']
        assert body['max_completion_tokens'] <= 256
        model = body['model']
        evidence = json.loads(body['messages'][-1]['content'])['records']
        projected = evidence['conversations/' + storage.RECORD_ID]
        assert 'SPEAKER_00: Robot Qorbi' in projected
        assert 'Qorby is a misspelling of Qorbi' in projected
        assert 'transcript_segments' not in projected
        value = (
            {'clusters': [{'refs': ['conversations/' + storage.RECORD_ID], 'problem': 'spelling'}]}
            if model == dream_transport.TRIAGE_LANE
            else {}
        )
        return httpx.Response(
            200,
            request=httpx.Request('POST', url),
            json={
                'usage': {'prompt_tokens': 30, 'completion_tokens': 20},
                'choices': [{'message': {'content': json.dumps(value)}}],
            },
        )

    client = type('Client', (), {'post': AsyncMock(side_effect=post)})()
    monkeypatch.setattr(dream_transport, 'get_llm_gateway_client', lambda: client)
    monkeypatch.setattr(dream_transport, 'get_llm_gateway_base_url', lambda: 'https://synthetic.invalid')
    monkeypatch.setattr(dream_transport, 'llm_gateway_headers', lambda **k: {})
    monkeypatch.setattr(dream_transport, 'get_llm_gateway_semaphore', lambda: asyncio.Semaphore(1))
    return db, client


def test_canary_full_loop_real_serialization_and_transport_shadow_in_on(store, caplog):
    db, client = store
    with caplog.at_level('INFO', logger='utils.dream_canary'):
        result = asyncio.run(dream_canary.check())
    assert result == {'status': 'pass', 'stage': 'report', 'error_type': 'none', 'consecutive_failures': 0}
    calls = [call.kwargs['json']['model'] for call in client.post.call_args_list]
    assert calls == [dream_transport.TRIAGE_LANE, dream_transport.MAIN_LANE]
    assert dream_store.dirty_count(UID) == 0
    doc = dream_store.own_runs(UID)[0][1]
    assert doc['mode'] == 'shadow' and doc['tokens'] == 100
    assert doc['records_read'] == 1 and doc['records_queued_after'] == 0
    assert 'review_encrypted_v1' in doc['source']
    assert db.rows[('dream_spend', doc['created_at'].date().isoformat())]['reserved_usd'] == pytest.approx(0.16)
    assert not eligible(UID, db.rows[('users', UID)])
    assert not dream_store.mark_dirty(UID, [('conversations', 'other')])
    assert UID not in caplog.text and 'Qorbi' not in caplog.text
    assert 'Dream canary status=pass stage=report error_type=none' in caplog.text


@pytest.mark.parametrize('stage', ['enqueue', 'admit', 'model', 'report'])
def test_canary_failures_identify_stage_and_reset_streak(store, monkeypatch, stage):
    db, client = store

    def broken(*a, **k):
        raise RuntimeError('private provider body')

    if stage == 'enqueue':
        monkeypatch.setattr(dream_canary.lifecycle, 'create_completed_conversation', broken)
    elif stage == 'admit':
        monkeypatch.setattr(dream_store, 'acquire', lambda *a, **k: None)
    elif stage == 'model':
        client.post.side_effect = httpx.ReadError('private provider body')
    else:
        monkeypatch.setattr(dream_store, 'own_run', lambda *a: None)
    first = asyncio.run(dream_canary.check())
    second = asyncio.run(dream_canary.check())
    assert first['status'] == second['status'] == 'fail'
    assert first['stage'] == second['stage'] == stage
    assert second['consecutive_failures'] == 2
    assert storage.record_result(True) == 0
    assert storage.record_result(False) == 1
    assert 'private' not in json.dumps(first)


def test_existing_owner_is_never_overwritten(store):
    db, client = store
    db.rows[('users', UID)] = {'name': 'existing'}
    result = asyncio.run(dream_canary.check())
    assert result['status'] == 'fail' and result['stage'] == 'enqueue'
    assert db.rows[('users', UID)] == {'name': 'existing'}
    assert not dream_store.own_runs(UID)
    client.post.assert_not_called()


def test_canary_uses_same_oidc_guard_as_sweep(store):
    app = FastAPI()
    app.include_router(dream_sweep.router)
    response = TestClient(app).post('/v2/dream-agent/canary')
    assert response.status_code == 403


def test_scheduler_prod_and_paused_dev_auth_match_sweep():
    root = Path(__file__).resolve().parents[3]
    config = yaml.safe_load((root / 'backend/deploy/scheduler/jobs.yaml').read_text())
    prod = config['environments']['prod']['jobs']
    sweep = next(row for row in prod if row['name'] == 'dream-agent-sweep-hourly')
    canary = next(row for row in prod if row['name'] == 'dream-agent-canary-half-hourly')
    assert canary['schedule'] == '*/30 * * * *' and canary['state'] == 'ENABLED'
    assert canary['target']['oidc'] == sweep['target']['oidc'] and canary['retry'] == sweep['retry']
    assert canary['target']['uri'] == sweep['target']['uri'].replace('/sweep', '/canary')
    dev = next(row for row in config['environments']['dev']['jobs'] if row['name'] == canary['name'])
    assert dev['state'] == 'PAUSED'


@pytest.mark.parametrize('reject_vertex', [False, True])
@pytest.mark.parametrize('oversized', [False, True])
def test_real_canary_requests_through_gateway_vertex_contract(store, monkeypatch, capsys, reject_vertex, oversized):
    """Seed/read/shape/transport/resolve/translate both lanes with no provider IO.

    Reasoning's selected records depend on triage output; force a valid spelling
    cluster rather than claiming to reproduce the lost production response.
    """
    db, original_client = store
    monkeypatch.setenv('GOOGLE_CLOUD_PROJECT', 'synthetic-project')
    monkeypatch.setenv('LLM_GATEWAY_SERVICE_TOKEN', 'synthetic-token')
    monkeypatch.delenv('OMI_VERTEX_PT_MODEL', raising=False)
    monkeypatch.delenv('OMI_VERTEX_RESERVATION_STATES', raising=False)
    monkeypatch.setattr(
        dream_transport,
        'llm_gateway_headers',
        lambda **k: {
            'Authorization': 'Bearer synthetic-token',
            'x-omi-service-caller': 'backend',
            'x-omi-request-id': '00000000-0000-4000-8000-000000000001',
        },
    )
    requests, vertex_bodies = [], []
    config = load_gateway_config()
    triage = {'clusters': [{'refs': ['conversations/' + storage.RECORD_ID], 'problem': 'spelling'}]}
    plan = {}
    if oversized:
        triage = {'clusters': [{'refs': ['conversations/' + storage.RECORD_ID], 'problem': 'spelling'}] * 13}
        plan = {
            'vocabulary': [
                {
                    'kind': 'jargon',
                    'spelling': 'synthetic',
                    'aliases': ['synthetic'] * 6,
                    'evidence': ['conversations/' + storage.RECORD_ID] * 11,
                }
            ]
            * 101
        }

    def upstream(request):
        body = json.loads(request.content)
        if request.url.host == 'us-central1-aiplatform.googleapis.com':
            vertex_bodies.append(body)
            assert request.headers[ptr.REQUEST_TYPE_HEADER] == 'dedicated'
            assert 'gemini-2.5-flash:generateContent' in request.url.path
            if reject_vertex:
                return httpx.Response(
                    400,
                    json={
                        'error': {
                            'status': 'INVALID_ARGUMENT',
                            'message': 'The specified schema produces a constraint that has too many states for serving. '
                            'Typical causes include long array length limits (especially when nested). private-user-content',
                            'details': [
                                {
                                    '@type': 'type.googleapis.com/google.rpc.BadRequest',
                                    'fieldViolations': [
                                        {
                                            'field': 'generation_config.response_json_schema.properties.private-name',
                                            'description': 'private-user-content',
                                        }
                                    ],
                                }
                            ],
                        }
                    },
                )
            return httpx.Response(
                200,
                json={
                    'candidates': [{'content': {'parts': [{'text': json.dumps(plan)}]}, 'finishReason': 'STOP'}],
                    'usageMetadata': {'promptTokenCount': 30, 'candidatesTokenCount': 20, 'totalTokenCount': 50},
                },
            )
        # Both the actual Luna triage and a recovered reasoning call run through
        # the real OpenAI adapter. The main schema stays unchanged on fallback.
        assert body['model'] == 'gpt-6-luna'
        value = triage if body['response_format']['json_schema']['name'] == 'Triage' else plan
        return httpx.Response(
            200,
            json={
                'object': 'chat.completion',
                'id': 'synthetic',
                'model': 'gpt-6-luna',
                'choices': [{'message': {'role': 'assistant', 'content': json.dumps(value)}, 'finish_reason': 'stop'}],
                'usage': {'prompt_tokens': 30, 'completion_tokens': 20, 'total_tokens': 50},
            },
        )

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(upstream)) as provider_client:
            vertex = VertexGeminiProvider(
                http_client=provider_client, access_token_supplier=AsyncMock(return_value='synthetic')
            )
            monkeypatch.setattr(
                vertex._reservations, 'refresh', AsyncMock(return_value={ptr.PT_MODEL_CURRENT: State.ACTIVE})
            )
            registry = ProviderRegistry(
                {'gemini': vertex, 'openai': OpenAICompatibleChatCompletionProvider(http_client=provider_client)}
            )
            gateway_app.dependency_overrides[dependencies.get_provider_registry] = lambda: registry
            gateway_app.dependency_overrides[dependencies.get_gateway_config] = lambda: config
            try:
                async with httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=gateway_app), base_url='http://synthetic'
                ) as local:

                    async def post(url, **kwargs):
                        requests.append(kwargs['json'])
                        return await local.post('/v1/chat/completions', **kwargs)

                    monkeypatch.setattr(
                        dream_transport,
                        'get_llm_gateway_client',
                        lambda: type('Client', (), {'post': staticmethod(post)})(),
                    )
                    return await dream_canary.check()
            finally:
                gateway_app.dependency_overrides.clear()

    result = asyncio.run(run())
    assert result['status'] == 'pass', result
    assert [row['model'] for row in requests] == [dream_transport.TRIAGE_LANE, dream_transport.MAIN_LANE]
    assert len(vertex_bodies) == 1  # Triage is Luna, reasoning is reserved Gemini.
    for request in requests:
        assert set(request) == {'model', 'messages', 'stream', 'max_completion_tokens', 'response_format'}
        assert request['stream'] is False and request['max_completion_tokens'] == 256
        resolved = resolve_chat_completion_route(config, request)
        provider_request = provider_request_for(resolved, resolved.active_route.primary)
        payload = ptr.model_payload(_vertex_request(provider_request), ptr.PT_MODEL_CURRENT)
        assert set(payload) == {'contents', 'systemInstruction', 'generationConfig'}
        assert len(payload['contents']) == 1 and payload['contents'][0]['role'] == 'user'
        assert payload['systemInstruction']['parts'][0]['text']
        assert all(part['text'] for part in payload['contents'][0]['parts'])
        generation = payload['generationConfig']
        assert set(generation) == {'maxOutputTokens', 'responseMimeType', 'responseJsonSchema', 'thinkingConfig'}
        assert generation['maxOutputTokens'] == 256
        assert generation['thinkingConfig'] == {'thinkingBudget': 0}
        assert generation['responseMimeType'] == 'application/json'
        assert generation['responseJsonSchema']['type'] == 'object'
        assert_vertex_subset(generation['responseJsonSchema'])
        assert_local_references(generation['responseJsonSchema'])
        assert 'maxItems' not in json.dumps(generation['responseJsonSchema'])
        assert 'minItems' not in json.dumps(generation['responseJsonSchema'])
        if request['model'] == dream_transport.MAIN_LANE:
            assert payload == vertex_bodies[0]
    logs = [json.loads(line) for line in capsys.readouterr().out.splitlines() if line.startswith('{')]
    rejections = [line for line in logs if line.get('event') == 'vertex_provider_rejection']
    assert len(rejections) == int(reject_vertex)
    if reject_vertex:
        assert rejections[0]['request_id'] == '00000000-0000-4000-8000-000000000001'
        assert rejections[0]['lane'] == dream_transport.MAIN_LANE
        assert rejections[0]['route'] == 'route.dream_reasoning.001'
        assert rejections[0]['failure_class'] == 'provider_invalid_request'
        assert rejections[0]['vertex_status'] == 'INVALID_ARGUMENT'
        assert rejections[0]['vertex_field'] == 'generationConfig.responseJsonSchema'
        assert rejections[0]['reason'] == 'schema_too_many_states'
    assert 'private-user-content' not in json.dumps(logs)
    assert 'private-name' not in json.dumps(logs)
