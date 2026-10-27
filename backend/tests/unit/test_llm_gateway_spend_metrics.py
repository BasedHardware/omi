"""Content-free spend attribution uses priced ledger events, never response size."""

from dataclasses import replace

import pytest
from prometheus_client import CollectorRegistry, Counter

from llm_gateway.gateway import accounting as a, metrics
from utils.llm.model_config import LUNA_MODEL


@pytest.fixture
def registry(monkeypatch):
    registry = CollectorRegistry()
    for name in (
        'ACCOUNTING_EVENTS_TOTAL',
        'ACCOUNTED_ATTEMPTS_TOTAL',
        'ACCOUNTED_TOKENS_TOTAL',
        'ESTIMATED_COST_MICRO_USD_TOTAL',
    ):
        original = getattr(metrics, name)
        monkeypatch.setattr(
            metrics, name, Counter(original._name, original._documentation, original._labelnames, registry=registry)
        )
    return registry


def event(*, payer='omi', provider='openai', traffic_type='default', **usage_overrides):
    usage = a.ProviderUsage(
        **{
            'prompt_tokens': 100,
            'uncached_input_tokens': 60,
            'cached_input_tokens': 40,
            'output_tokens': 20,
            'reasoning_tokens': 5,
            'output_tokens_include_reasoning': True,
            **usage_overrides,
        }
    )
    attempt = a.ProviderAttempt(
        ordinal=1,
        provider=provider,
        configured_model=LUNA_MODEL,
        route_artifact_id='route.synthetic',
        fallback_reason=None,
        retry_ordinal=0,
        outcome='success',
        error_class='none',
        billable_usage_complete=True,
        lane_id='omi:auto:chat-agent',
        usage=usage,
        usage_status=a.UsageStatus.CONFIRMED,
        traffic_type=traffic_type,
    )
    context = a.AccountingContext.create(
        request_id='invented-request',
        caller='synthetic-test',
        user_uid='invented-owner',
        feature='chat_agent',
        api_surface='openai_chat_completions',
        payer=payer,
    )
    return a.build_accounting_event(context, attempt)


def samples(registry, name):
    return [s for family in registry.collect() for s in family.samples if s.name == name]


def tokens(registry):
    return {s.labels['token_type']: s.value for s in samples(registry, 'llm_gateway_accounted_tokens_total')}


def test_written_receipt_counts_full_usage_even_below_cache_minimum(registry):
    value = event()
    assert value.cache_mode == 'none' and value.cacheable_prefix_tokens == 0
    metrics.observe_accounting_event(value, delivery='written')
    assert tokens(registry) == {
        'prompt': 100,
        'uncached_input': 60,
        'cached_input': 40,
        'cache_write': 0,
        'tool_use_prompt': 0,
        'output': 20,
        'reasoning': 5,
    }
    cost = samples(registry, 'llm_gateway_estimated_cost_micro_usd_total')
    assert len(cost) == 1 and cost[0].value == value.estimated_cost_micro_usd
    for family in registry.collect():
        for sample in family.samples:
            assert not {'uid', 'user_uid', 'request_id', 'feature', 'caller', 'attempt_id'} & sample.labels.keys()
            assert 'invented-owner' not in str(sample.labels)
            assert 'invented-request' not in str(sample.labels)


@pytest.mark.parametrize('delivery', ['duplicate', 'failed', 'dropped', 'unknown'])
def test_nonwritten_delivery_never_inflates_tokens_or_dollars(registry, delivery):
    value = event()
    metrics.observe_accounting_event(value, delivery='written')
    metrics.observe_accounting_event(value, delivery=delivery)
    assert tokens(registry)['output'] == 20
    assert samples(registry, 'llm_gateway_estimated_cost_micro_usd_total')[0].value == value.estimated_cost_micro_usd
    assert sum(s.value for s in samples(registry, 'llm_gateway_accounted_attempts_total')) == 1
    assert sum(s.value for s in samples(registry, 'llm_gateway_accounting_events_total')) == 2


def test_separate_reasoning_is_added_once_and_cache_writes_are_exposed(registry):
    value = event(output_tokens_include_reasoning=False, cache_write_tokens=12, tool_use_prompt_tokens=7)
    metrics.observe_accounting_event(value, delivery='written')
    assert tokens(registry)['output'] == 25
    assert tokens(registry)['reasoning'] == 5  # a subset of billable output, not another charge
    assert tokens(registry)['cache_write'] == 12
    assert tokens(registry)['tool_use_prompt'] == 7


@pytest.mark.parametrize('status', [a.UsageStatus.NOT_REPORTED, a.UsageStatus.INDETERMINATE])
def test_unknown_usage_is_coverage_not_zero_tokens_or_free_work(registry, status):
    value = replace(event(), usage_status=status, cost_status=a.CostStatus.INDETERMINATE, estimated_cost_micro_usd=None)
    metrics.observe_accounting_event(value, delivery='written')
    assert tokens(registry) == {}
    assert samples(registry, 'llm_gateway_estimated_cost_micro_usd_total') == []
    assert samples(registry, 'llm_gateway_accounted_attempts_total')[0].labels['usage_status'] == status.value


@pytest.mark.parametrize('kind', ['byok', 'unpriced', 'indeterminate'])
def test_unpriced_or_customer_paid_work_never_becomes_omi_dollars(registry, kind):
    value = event(payer='byok' if kind == 'byok' else 'omi')
    if kind != 'byok':
        value = replace(value, cost_status=a.CostStatus(kind), estimated_cost_micro_usd=None)
    metrics.observe_accounting_event(value, delivery='written')
    assert tokens(registry)['prompt'] == 100
    assert samples(registry, 'llm_gateway_estimated_cost_micro_usd_total') == []
    assert samples(registry, 'llm_gateway_accounted_attempts_total')[0].labels['cost_status'] == value.cost_status.value


def test_flex_uses_existing_estimator_without_a_second_discount(registry):
    value = event(traffic_type='flex')
    metrics.observe_accounting_event(value, delivery='written')
    sample = samples(registry, 'llm_gateway_estimated_cost_micro_usd_total')[0]
    assert sample.labels['traffic_type'] == 'flex'
    assert sample.value == value.estimated_cost_micro_usd
    assert sample.value < event().estimated_cost_micro_usd


def test_non_token_units_and_arbitrary_tier_are_not_fabricated(registry):
    value = replace(event(traffic_type='invented-private-value'), unit_type='images')
    metrics.observe_accounting_event(value, delivery='written')
    assert tokens(registry) == {}
    assert samples(registry, 'llm_gateway_accounted_attempts_total')[0].labels['traffic_type'] == 'unknown'


def normalized_event(metadata, *, provider='openai'):
    trace = a.AttemptTrace()
    attempt = trace.record(
        provider=provider,
        configured_model=LUNA_MODEL,
        route_artifact_id='route.synthetic',
        fallback_reason=None,
        retry_ordinal=0,
        outcome='success',
        error_class='none',
        metadata=metadata,
        lane_id='omi:auto:chat-agent',
    )
    context = a.AccountingContext.create(
        request_id='invented-normalized-request',
        caller='synthetic-test',
        user_uid=None,
        feature='chat_agent',
        api_surface='openai_chat_completions',
        payer='omi',
    )
    return a.build_accounting_event(context, attempt)


@pytest.mark.parametrize(
    'raw',
    [
        {'prompt_tokens': 100},
        {'completion_tokens': 20},
        {'total_tokens': 120},
        {'prompt_tokens': True, 'completion_tokens': 20},
        {'prompt_tokens': 100, 'completion_tokens': 20, 'total_tokens': 200},
    ],
)
def test_real_partial_openai_normalizer_never_publishes_zero_filled_bill(registry, raw):
    value = normalized_event(a.openai_usage_from_response({'usage': raw}))
    assert value.usage_status == a.UsageStatus.CONFIRMED  # legacy normalization is intentionally unchanged
    assert not value.billable_usage_complete
    assert 'billable_usage_complete' not in value.as_dict()  # no persistence schema/pricing migration
    metrics.observe_accounting_event(value, delivery='written')
    assert tokens(registry) == {}
    assert samples(registry, 'llm_gateway_estimated_cost_micro_usd_total') == []
    coverage = samples(registry, 'llm_gateway_accounted_attempts_total')[0]
    assert coverage.labels['usage_status'] == 'indeterminate'
    assert coverage.labels['cost_status'] == 'indeterminate'


@pytest.mark.parametrize(
    'raw',
    [
        {'promptTokenCount': 100},
        {'candidatesTokenCount': 20},
        {'promptTokenCount': 100, 'candidatesTokenCount': 20, 'thoughtsTokenCount': -1},
    ],
)
def test_real_partial_vertex_normalizer_is_coverage_not_tokens(registry, raw):
    value = normalized_event(a.vertex_usage_from_response({'usageMetadata': raw}), provider='gemini')
    assert not value.billable_usage_complete
    metrics.observe_accounting_event(value, delivery='written')
    assert tokens(registry) == {}
    assert samples(registry, 'llm_gateway_estimated_cost_micro_usd_total') == []
    assert samples(registry, 'llm_gateway_accounted_attempts_total')[0].labels['usage_status'] == 'indeterminate'


@pytest.mark.parametrize('provider', ['openai', 'gemini'])
def test_real_complete_normalizer_retains_billable_output(registry, provider):
    metadata = (
        a.openai_usage_from_response(
            {
                'usage': {
                    'prompt_tokens': 100,
                    'completion_tokens': 20,
                    'completion_tokens_details': {'reasoning_tokens': 5},
                }
            }
        )
        if provider == 'openai'
        else a.vertex_usage_from_response(
            {
                'usageMetadata': {
                    'promptTokenCount': 100,
                    'candidatesTokenCount': 20,
                    'thoughtsTokenCount': 5,
                }
            }
        )
    )
    value = normalized_event(metadata, provider=provider)
    assert value.billable_usage_complete
    metrics.observe_accounting_event(value, delivery='written')
    assert tokens(registry)['prompt'] == 100
    assert tokens(registry)['output'] == (20 if provider == 'openai' else 25)


def test_request_models_and_unknown_surfaces_cannot_create_arbitrary_labels(registry):
    for ordinal in range(40):
        value = replace(
            event(),
            configured_model=f'invented-private-model-{ordinal}',
            resolved_model=None,
            lane_id=f'invented-private-lane-{ordinal}',
            api_surface=f'invented-private-surface-{ordinal}',
            cost_status=a.CostStatus.UNPRICED,
            estimated_cost_micro_usd=None,
        )
        metrics.observe_accounting_event(value, delivery='written')
    coverage = samples(registry, 'llm_gateway_accounted_attempts_total')
    assert len(coverage) == 1 and coverage[0].value == 40
    assert (
        coverage[0].labels['model'] == coverage[0].labels['lane_id'] == coverage[0].labels['api_surface'] == 'unknown'
    )


def test_configured_unpriced_model_is_finite_and_model_whitespace_does_not_fork_series(registry, monkeypatch):
    monkeypatch.setattr(metrics, '_spend_model_ids', frozenset({('openai', 'synthetic-configured-model')}))
    monkeypatch.setattr(metrics, '_spend_lane_ids', frozenset({'omi:auto:chat-agent'}))
    for model in [LUNA_MODEL, ' ' + LUNA_MODEL + ' ', 'synthetic-configured-model']:
        metrics.observe_accounting_event(replace(event(), configured_model=model), delivery='written')
    coverage = samples(registry, 'llm_gateway_accounted_attempts_total')
    assert len(coverage) == 2
    assert {s.labels['model'] for s in coverage} == {LUNA_MODEL, 'synthetic-configured-model'}
    assert {s.labels['lane_id'] for s in coverage} == {'omi:auto:chat-agent'}


def test_real_image_route_has_surface_attribution_and_bounded_failed_models(registry, monkeypatch):
    import httpx
    from fastapi.testclient import TestClient
    from llm_gateway.main import app
    from llm_gateway.routers import openai_compatible

    class ImageClient:
        async def post(self, *_args, **kwargs):
            return httpx.Response(200, json={'created': 1, 'data': []})

    def observe(context, trace):
        for attempt in trace.attempts:
            metrics.observe_accounting_event(a.build_accounting_event(context, attempt), delivery='written')

    monkeypatch.setenv('LLM_GATEWAY_SERVICE_TOKEN', 'synthetic-service-token')
    monkeypatch.setenv('OPENAI_API_KEY', 'synthetic-provider-key')
    monkeypatch.setattr(openai_compatible, '_get_image_generation_client', lambda: ImageClient())
    monkeypatch.setattr(openai_compatible, 'schedule_attempt_trace', observe)
    client = TestClient(app)
    headers = {'Authorization': 'Bearer synthetic-service-token', 'x-omi-service-caller': 'backend'}
    response = client.post(
        '/v1/images/generations',
        headers=headers,
        json={
            'model': 'gpt-image-1',
            'prompt': 'invented square',
            'size': '1024x1024',
            'quality': 'low',
        },
    )
    assert response.status_code == 200
    costs = samples(registry, 'llm_gateway_estimated_cost_micro_usd_total')
    assert len(costs) == 1 and costs[0].value > 0
    assert costs[0].labels['api_surface'] == 'openai_images_generations'
    assert costs[0].labels['lane_id'] == 'unknown'  # no invented routed lane on this legacy surface
    monkeypatch.delenv('OPENAI_API_KEY')
    for ordinal in range(4):
        assert (
            client.post(
                '/v1/images/generations',
                headers=headers,
                json={
                    'model': f'invented-private-model-{ordinal}',
                    'prompt': 'invented square',
                },
            ).status_code
            == 503
        )
    attempts = samples(registry, 'llm_gateway_accounted_attempts_total')
    failures = [s for s in attempts if s.labels['cost_status'] == 'indeterminate']
    assert len(failures) == 1 and failures[0].value == 4
    assert failures[0].labels['model'] == 'unknown'


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'raw,complete',
    [
        ({'prompt_tokens': 12, 'total_tokens': 12}, True),
        ({'prompt_tokens': 12}, True),
        ({'total_tokens': 12}, False),
        ({'prompt_tokens': True}, False),
        ({'prompt_tokens': 12, 'total_tokens': 20}, False),
    ],
)
async def test_real_embedding_adapter_reports_raw_input_validity(registry, monkeypatch, raw, complete):
    import httpx
    from llm_gateway.gateway.auth import ServiceCaller
    from llm_gateway.gateway.credentials import build_omi_managed_credential_context
    from llm_gateway.gateway.providers import OpenAICompatibleChatCompletionProvider
    from llm_gateway.gateway.schemas import ProviderRef

    monkeypatch.setenv('OPENAI_API_KEY', 'synthetic-provider-key')
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                json={
                    'object': 'list',
                    'data': [{'index': 0, 'embedding': [0.1, 0.2]}],
                    'usage': raw,
                },
            )
        )
    ) as client:
        provider = OpenAICompatibleChatCompletionProvider(http_client=client)
        result = await provider.create_embedding(
            {'input': ['invented input']},
            provider_ref=ProviderRef(provider='openai', model='text-embedding-3-large'),
            credentials=build_omi_managed_credential_context(ServiceCaller(name='backend')),
            timeout_ms=1000,
        )
    value = normalized_event(result.accounting)
    assert value.billable_usage_complete is complete
    metrics.observe_accounting_event(value, delivery='written')
    assert tokens(registry).get('prompt') == (12 if complete else None)
    assert result.response['usage'] == raw  # actual response and legacy units are unchanged
