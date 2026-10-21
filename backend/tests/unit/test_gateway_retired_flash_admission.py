"""Exercise desktop admission through real reservation reads and provider HTTP.

A cache receipt for Gemini can describe a local policy rejection without any
Vertex inference. Keep that distinction explicit when diagnosing retired Flash.
"""

import json
import logging
import time
from dataclasses import asdict
from pathlib import Path
from unittest.mock import AsyncMock

import fakeredis.aioredis
import httpx
import pytest
import yaml

from config import vertex_reservations as vr
from llm_gateway.gateway.accounting import AttemptTrace
from llm_gateway.gateway.auth import ServiceCaller
from llm_gateway.gateway.config_loader import load_gateway_config
from llm_gateway.gateway.credentials import build_omi_managed_credential_context
from llm_gateway.gateway.executor import ProviderRegistry, execute_chat_completion
from llm_gateway.gateway.providers import OpenAICompatibleChatCompletionProvider, VertexGeminiProvider
from llm_gateway.gateway.resolver import resolve_chat_completion_route
from llm_gateway.gateway.schemas import FailureClass
from llm_gateway.routers.openai_compatible import _prepared_streaming_iterator, _stream_with_terminal_metrics
from utils.llm import vertex_pt_routing as ptr
from utils.llm.vertex_reservation_state import ReservationState, discovery_models, effective_states


def test_prod_gateway_retirement_pin_preserves_dream_target_discovery():
    backend = Path(__file__).resolve().parents[2]
    chart = yaml.load(
        (backend / 'charts/llm-gateway/prod_omi_llm_gateway_values.yaml').read_text(), Loader=yaml.CSafeLoader
    )
    manifest = yaml.load((backend / 'deploy/runtime_env.yaml').read_text(), Loader=yaml.CSafeLoader)
    override = next(entry['value'] for entry in chart['env'] if entry['name'] == vr.STATE_OVERRIDE_ENV)
    assert manifest['environments']['prod']['llm_gateway']['env'][vr.STATE_OVERRIDE_ENV]['value'] == override
    assert json.loads(override) == {ptr.PT_MODEL_CURRENT: 'inactive'}
    env = {vr.STATE_OVERRIDE_ENV: override}
    observed = {ptr.PT_MODEL_CURRENT: vr.State.ACTIVE, ptr.PT_MODEL_TARGET: vr.State.ACTIVE}
    assert effective_states(observed, env) == {
        ptr.PT_MODEL_CURRENT: vr.State.INACTIVE,
        ptr.PT_MODEL_TARGET: vr.State.ACTIVE,
    }
    assert discovery_models(env) == frozenset({ptr.PT_MODEL_TARGET})


@pytest.mark.asyncio
@pytest.mark.parametrize('anchor', [ptr.PT_MODEL_CURRENT, 'gemini-2.5-flash-lite', ptr.PT_MODEL_TARGET])
@pytest.mark.parametrize('streaming', [False, True])
@pytest.mark.parametrize('state_source', ['moved_order', 'inactive_override', 'unknown', 'read_failure', 'active'])
async def test_desktop_admission_with_real_reservation_reader(monkeypatch, caplog, anchor, streaming, state_source):
    monkeypatch.setenv('GOOGLE_CLOUD_PROJECT', 'synthetic-project')
    monkeypatch.delenv(ptr.PT_MODEL_OVERRIDE_ENV, raising=False)
    monkeypatch.delenv(vr.STATE_OVERRIDE_ENV, raising=False)
    skip_vertex = state_source in {'moved_order', 'inactive_override'}
    if state_source == 'inactive_override':
        # Override must win even over positive old-model evidence.
        monkeypatch.setenv(vr.STATE_OVERRIDE_ENV, json.dumps({ptr.PT_MODEL_CURRENT: 'inactive'}))

    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    store = ReservationState(redis)
    seconds, micros = await redis.time()
    now = seconds + micros / 1_000_000
    evidence = {}
    if state_source == 'moved_order':
        evidence = {
            ptr.PT_MODEL_CURRENT: asdict(
                vr.Evidence(success_at=now - 4000, failure_start=now - 2400, failure_at=now - 600, failure_count=4)
            ),
            ptr.PT_MODEL_TARGET: asdict(vr.Evidence(success_at=now - 100)),
        }
    elif state_source in {'inactive_override', 'active'}:
        evidence = {ptr.PT_MODEL_CURRENT: asdict(vr.Evidence(success_at=now - 100))}
    # Discovery has its own synthetic-probe contract. Hold its leases so only
    # user inference is observed here, without mocking refresh or its reducer.
    await redis.set(
        store.key(), json.dumps({'evidence': evidence, 'leases': {model: now + 600 for model in vr.RESERVATIONS}})
    )
    if state_source == 'read_failure':

        def unavailable(*args, **kwargs):
            raise ConnectionError('synthetic reservation read outage')

        monkeypatch.setattr(redis, 'pipeline', unavailable)

    seen = []

    def handler(request):
        seen.append(request)
        if '/publishers/google/models/' in request.url.path:
            assert not skip_vertex
            assert f'/models/{ptr.PT_MODEL_CURRENT}:' in request.url.path
            assert request.headers[ptr.REQUEST_TYPE_HEADER] == ptr.REQUEST_TYPE_DEDICATED
            return httpx.Response(429, json={'error': {'message': 'Provisioned throughput exhausted'}})
        assert request.url.path == '/v1/chat/completions'
        assert json.loads(request.content)['model'] == 'gpt-6-luna'
        if streaming:
            return httpx.Response(
                200,
                content=b'data: {"choices":[{"delta":{"content":"safe Luna"},"finish_reason":"stop"}]}\n\ndata: [DONE]\n\n',
            )
        return httpx.Response(
            200,
            json={
                'id': 'synthetic-completion',
                'object': 'chat.completion',
                'model': 'gpt-6-luna',
                'choices': [{'message': {'role': 'assistant', 'content': 'safe Luna'}, 'finish_reason': 'stop'}],
            },
        )

    try:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            access_token = AsyncMock(return_value='synthetic-token')
            vertex = VertexGeminiProvider(http_client=client, access_token_supplier=access_token)
            vertex._reservations = store
            registry = ProviderRegistry(
                {'gemini': vertex, 'openai': OpenAICompatibleChatCompletionProvider(http_client=client)}
            )
            resolved = resolve_chat_completion_route(
                load_gateway_config(),
                {'model': ptr.desktop_text_lane_id(anchor), 'messages': [{'role': 'user', 'content': 'synthetic'}]},
            )
            credentials = build_omi_managed_credential_context(ServiceCaller(name='backend'))
            trace = AttemptTrace()
            with caplog.at_level(logging.INFO, logger='llm_gateway.gateway.cache_metrics'):
                if streaming:
                    prepared = await _prepared_streaming_iterator(
                        resolved, credentials, registry, resolved.active_route, attempt_trace=trace
                    )
                    output = b''.join(
                        [
                            chunk
                            async for chunk in _stream_with_terminal_metrics(
                                prepared,
                                resolved_route=resolved,
                                credentials=credentials,
                                route=resolved.active_route,
                                started_at=time.monotonic(),
                                request_id='synthetic',
                                attempt_trace=trace,
                            )
                        ]
                    )
                    assert prepared.provider == 'openai' and prepared.model == 'gpt-6-luna'
                    assert b'safe Luna' in output
                else:
                    result = await execute_chat_completion(resolved, credentials, registry, attempt_trace=trace)
                    assert result.selected_provider == 'openai' and result.selected_model == 'gpt-6-luna'
                    assert result.response['choices'][0]['message']['content'] == 'safe Luna'

            assert len(seen) == (1 if skip_vertex else 2)
            assert not store._probe_tasks
            if skip_vertex:
                access_token.assert_not_awaited()
                assert trace.attempts[0].error_class == FailureClass.RESERVED_CAPACITY_UNAVAILABLE.value
                assert trace.attempts[0].resolved_model is None
                assert trace.attempts[0].usage is None
                # This is the same Gemini-then-Luna log pattern as a real 429,
                # despite zero Vertex HTTP, cache preparation, or ADC calls.
                receipts = [
                    json.loads(record.message.split('llm_gateway_cache_receipt ', 1)[1])
                    for record in caplog.records
                    if record.message.startswith('llm_gateway_cache_receipt ')
                ]
                assert [receipt['provider'] for receipt in receipts] == ['gemini', 'openai']
                assert receipts[0]['model'] == resolved.active_route.primary.model
                assert receipts[0]['traffic_type'] is None
                assert receipts[0]['prompt_tokens'] is None
            else:
                assert trace.attempts[0].resolved_model == ptr.PT_MODEL_CURRENT
    finally:
        await store.aclose()
        await redis.aclose()
