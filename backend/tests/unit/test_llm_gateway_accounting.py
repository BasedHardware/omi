from __future__ import annotations

import asyncio
from typing import Any

from google.api_core.exceptions import AlreadyExists
import pytest

from database.llm_gateway_accounting import ATTEMPTS_COLLECTION, record_llm_gateway_attempt
from llm_gateway.gateway import accounting_sink
from llm_gateway.gateway.accounting import (
    AccountingContext,
    AttemptTrace,
    CacheStatus,
    CostStatus,
    ProviderResponseMetadata,
    ProviderUsage,
    anthropic_usage_from_response,
    aggregate_accounting_events,
    build_accounting_event,
    cache_requested_for_openai_request,
    cache_write_ttl_for_anthropic_request,
    image_usage,
    jit_gateway_receipt_for_trace,
    openai_usage_from_response,
    vertex_usage_from_response,
)


def test_openai_cache_request_detection_matches_explicit_contract() -> None:
    breakpoint_messages = [
        {
            'role': 'system',
            'content': [
                {
                    'type': 'text',
                    'text': 'static instructions',
                    'prompt_cache_breakpoint': {'mode': 'explicit'},
                }
            ],
        }
    ]

    assert cache_requested_for_openai_request(
        {
            'prompt_cache_key': 'omi-transcript-structure-v1',
            'prompt_cache_options': {'mode': 'explicit', 'ttl': '30m'},
            'messages': breakpoint_messages,
        }
    )
    assert not cache_requested_for_openai_request(
        {
            # Include the routing key so the check reaches the breakpoint-detection
            # branch instead of short-circuiting on the missing prompt_cache_key guard.
            'prompt_cache_key': 'omi-transcript-structure-v1',
            'prompt_cache_options': {'mode': 'explicit', 'ttl': '30m'},
            'messages': [{'role': 'system', 'content': 'unique transcript'}],
        }
    )
    assert cache_requested_for_openai_request({'prompt_cache_key': 'legacy-key', 'messages': []})


def test_openai_usage_distinguishes_cache_hit_miss_and_unobserved_cache() -> None:
    hit = openai_usage_from_response(
        {
            'id': 'chatcmpl-hit',
            'usage': {
                'prompt_tokens': 100,
                'completion_tokens': 10,
                'prompt_tokens_details': {'cached_tokens': 100},
            },
        }
    ).usage
    partial = openai_usage_from_response(
        {
            'id': 'chatcmpl-partial',
            'usage': {
                'prompt_tokens': 100,
                'completion_tokens': 10,
                'prompt_tokens_details': {'cached_tokens': 40},
            },
        }
    ).usage
    miss = openai_usage_from_response(
        {
            'id': 'chatcmpl-miss',
            'usage': {'prompt_tokens': 100, 'completion_tokens': 10, 'prompt_tokens_details': {'cached_tokens': 0}},
        },
        cache_requested=True,
    ).usage
    no_cache_read = openai_usage_from_response(
        {
            'id': 'chatcmpl-no-read',
            'usage': {'prompt_tokens': 100, 'completion_tokens': 10, 'prompt_tokens_details': {'cached_tokens': 0}},
        }
    ).usage

    assert hit is not None and hit.cache_status == CacheStatus.HIT
    assert partial is not None and partial.cache_status == CacheStatus.PARTIAL_HIT
    assert miss is not None and miss.cache_status == CacheStatus.MISS
    assert no_cache_read is not None and no_cache_read.cache_status == CacheStatus.NO_CACHE_READ_OBSERVED


def test_openai_flex_tier_is_recorded_and_priced_at_batch_rates() -> None:
    metadata = openai_usage_from_response(
        {
            'id': 'chatcmpl-flex',
            'model': 'gpt-5.6-luna',
            'service_tier': 'flex',
            'usage': {'prompt_tokens': 1_000_000, 'completion_tokens': 1_000_000},
        }
    )
    trace = AttemptTrace()
    attempt = trace.record(
        provider='openai',
        configured_model='gpt-5.6-luna',
        route_artifact_id='route.memory_conflict_flex.model_config.001',
        fallback_reason=None,
        retry_ordinal=0,
        outcome='success',
        error_class='none',
        metadata=metadata,
    )
    context = AccountingContext.create(
        request_id='request-flex',
        caller='memory-maintenance-job',
        user_uid=None,
        feature='memory_conflict',
        api_surface='openai.chat_completions',
        payer='omi',
    )

    event = build_accounting_event(context, attempt)

    assert event.traffic_type == 'flex'
    # 1M input + 1M output puts this over the 272K long-context boundary:
    # (1M * $0.40 + 1M * $1.80) halved for Flex = $1.10.
    assert event.estimated_cost_micro_usd == 1_100_000
    assert event.cost_basis == 'flex_batch_token_rates_excludes_cache_storage'


def test_openai_usage_parses_cache_writes_and_prices_luna_write_tokens() -> None:
    usage = openai_usage_from_response(
        {
            'id': 'chatcmpl-write',
            'usage': {
                'prompt_tokens': 1_000_000,
                'completion_tokens': 1_000_000,
                'prompt_tokens_details': {'cached_tokens': 200_000, 'cache_write_tokens': 400_000},
            },
        },
        cache_requested=True,
    ).usage
    assert usage is not None
    assert usage.cache_write_tokens == 400_000
    assert usage.cache_write_ttl == '30m'
    assert usage.uncached_input_tokens == 400_000

    trace = AttemptTrace()
    attempt = trace.record(
        provider='openai',
        configured_model='gpt-5.6-luna',
        route_artifact_id='route.conv_action_items.model_config.001',
        fallback_reason=None,
        retry_ordinal=1,
        outcome='success',
        error_class='none',
        metadata=ProviderResponseMetadata(usage=usage),
    )
    event = build_accounting_event(_context(), attempt)

    assert event.cache_write_tokens == 400_000
    # Long-context tier: 400K * $0.40 + 200K * $0.04 + 1M * $1.80
    # + 400K * $0.50 = $2.168.
    assert event.estimated_cost_micro_usd == 2_168_000
    assert event.rate_card_id == 'openai.gpt-5.6-luna.2026-07-30'


def test_openai_receipt_normalizes_cached_and_cache_write_tokens_once() -> None:
    """OpenAI prompt_tokens already includes both cached and write units."""
    metadata = openai_usage_from_response(
        {
            'id': 'chatcmpl-jit-receipt',
            'model': 'gpt-5.4-nano',
            'usage': {
                'prompt_tokens': 100,
                'completion_tokens': 12,
                'prompt_tokens_details': {'cached_tokens': 40, 'cache_write_tokens': 10},
            },
        },
        cache_requested=True,
    )

    usage = metadata.usage
    assert usage is not None
    assert usage.prompt_tokens == 100
    assert usage.cached_input_tokens == 40
    assert usage.cache_write_tokens == 10
    assert usage.uncached_input_tokens == 50


def test_jit_aggregate_includes_retries_and_stops_on_unknown_cost() -> None:
    context = AccountingContext.create(
        request_id='request-jit-run',
        caller='jit-proactivity',
        user_uid='user-123',
        feature='jit_proactivity',
        api_surface='openai_chat_completions',
        payer='omi',
        jit_run_id='jit-run-opaque-1',
        jit_contract_version='jit-cloud-qa-v1',
    )
    trace = AttemptTrace()
    priced_attempt = trace.record(
        provider='openai',
        configured_model='gpt-5.4-nano',
        route_artifact_id='route.jit.nano.001',
        fallback_reason=None,
        retry_ordinal=0,
        outcome='success',
        error_class='none',
        metadata=ProviderResponseMetadata(
            usage=ProviderUsage(prompt_tokens=100, uncached_input_tokens=80, cached_input_tokens=20, output_tokens=8)
        ),
    )
    retry_without_receipt = trace.record(
        provider='openai',
        configured_model='gpt-5.4-nano',
        route_artifact_id='route.jit.nano.001',
        fallback_reason='provider_timeout',
        retry_ordinal=1,
        outcome='error',
        error_class='timeout',
    )

    aggregate = aggregate_accounting_events(
        [build_accounting_event(context, priced_attempt), build_accounting_event(context, retry_without_receipt)]
    )

    assert aggregate is not None
    assert aggregate.attempt_count == 2
    assert aggregate.normalized_uncached_input_tokens == 80
    assert aggregate.cached_input_tokens == 20
    assert aggregate.cost_status == CostStatus.INDETERMINATE
    assert aggregate.estimated_cost_micro_usd is None
    assert not aggregate.cost_is_known


def test_cache_write_only_miss_reports_negative_net_cache_savings() -> None:
    trace = AttemptTrace()
    attempt = trace.record(
        provider='openai',
        configured_model='gpt-5.6-luna',
        route_artifact_id='route.test.001',
        fallback_reason=None,
        retry_ordinal=0,
        outcome='success',
        error_class='none',
        metadata=ProviderResponseMetadata(
            usage=ProviderUsage(
                prompt_tokens=1_000_000,
                cache_write_tokens=1_000_000,
                cache_write_ttl='30m',
            )
        ),
    )

    event = build_accounting_event(_context(), attempt)

    # 1M of write tokens is past the 272K boundary, so the long-context rates
    # apply: a write costs $0.50/M while the ordinary input counterfactual
    # costs $0.40/M, a $0.10/M net loss until this entry is reused.
    assert event.estimated_cost_micro_usd == 500_000
    assert event.estimated_cache_savings_micro_usd == -100_000


def test_cache_write_and_read_report_net_cache_savings() -> None:
    trace = AttemptTrace()
    attempt = trace.record(
        provider='openai',
        configured_model='gpt-5.6-luna',
        route_artifact_id='route.test.001',
        fallback_reason=None,
        retry_ordinal=0,
        outcome='success',
        error_class='none',
        metadata=ProviderResponseMetadata(
            usage=ProviderUsage(
                prompt_tokens=2_000_000,
                cached_input_tokens=1_000_000,
                uncached_input_tokens=0,
                cache_write_tokens=1_000_000,
                cache_write_ttl='30m',
                output_tokens=1_000_000,
            )
        ),
    )

    event = build_accounting_event(_context(), attempt)

    # 2M of input context is past the 272K boundary, so this prices at the
    # long-context tier throughout. Counterfactual input bill: 2M * $0.40 =
    # $0.80. Actual input bill is 1M * $0.04 + 1M * $0.50 = $0.54, for $0.26
    # net savings. Output adds 1M * $1.80.
    assert event.estimated_cost_micro_usd == 2_340_000
    assert event.estimated_cache_savings_micro_usd == 260_000


def test_flex_halves_complete_net_cache_savings_and_total_cost() -> None:
    trace = AttemptTrace()
    attempt = trace.record(
        provider='openai',
        configured_model='gpt-5.6-luna',
        route_artifact_id='route.test.001',
        fallback_reason=None,
        retry_ordinal=0,
        outcome='success',
        error_class='none',
        metadata=ProviderResponseMetadata(
            usage=ProviderUsage(
                prompt_tokens=2_000_000,
                cached_input_tokens=1_000_000,
                cache_write_tokens=1_000_000,
                cache_write_ttl='30m',
                output_tokens=1_000_000,
            ),
            traffic_type='flex',
        ),
    )

    event = build_accounting_event(_context(), attempt)

    # Exactly half of the long-context figures in the test above.
    assert event.estimated_cost_micro_usd == 1_170_000
    assert event.estimated_cache_savings_micro_usd == 130_000


def test_empty_usage_object_is_unreported_not_a_zero_cost_completion() -> None:
    metadata = openai_usage_from_response({'id': 'chatcmpl-empty', 'model': 'gpt-5.4-nano', 'usage': {}})
    trace = AttemptTrace()
    attempt = trace.record(
        provider='openai',
        configured_model='gpt-5.4-nano',
        route_artifact_id='route.test.001',
        fallback_reason=None,
        retry_ordinal=1,
        outcome='success',
        error_class='none',
        metadata=metadata,
    )

    event = build_accounting_event(_context(), attempt)

    assert event.usage_status.value == 'not_reported'
    assert event.cost_status == CostStatus.UNPRICED
    assert event.estimated_cost_micro_usd is None


def test_openai_reasoning_tokens_are_an_output_subset_not_double_charged() -> None:
    usage = openai_usage_from_response(
        {
            'id': 'chatcmpl-reasoning',
            'usage': {
                'prompt_tokens': 10,
                'completion_tokens': 100,
                'completion_tokens_details': {'reasoning_tokens': 40},
            },
        }
    ).usage

    assert usage is not None
    assert usage.reasoning_tokens == 40
    assert usage.output_tokens_include_reasoning is True
    assert usage.billable_output_tokens == 100
    assert usage.total_tokens == 110


def test_jit_aggregate_and_receipt_preserve_reasoning_tokens() -> None:
    context = AccountingContext.create(
        request_id='request-reasoning-jit',
        caller='jit-proactivity',
        user_uid='user-123',
        feature='jit_proactivity',
        api_surface='openai_chat_completions',
        payer='omi',
        jit_run_id='jit-reasoning-run',
        jit_contract_version='jit-cloud-qa-v1',
    )
    trace = AttemptTrace()
    trace.record(
        provider='openai',
        configured_model='gpt-5.6-luna',
        route_artifact_id='route.jit.001',
        fallback_reason=None,
        retry_ordinal=1,
        outcome='success',
        error_class='none',
        metadata=ProviderResponseMetadata(
            usage=ProviderUsage(
                prompt_tokens=10,
                uncached_input_tokens=10,
                output_tokens=100,
                reasoning_tokens=40,
                output_tokens_include_reasoning=True,
            )
        ),
    )

    receipt = jit_gateway_receipt_for_trace(context, trace)

    assert receipt is not None
    assert receipt.aggregate.output_tokens == 100
    assert receipt.aggregate.reasoning_tokens == 40
    assert receipt.as_dict()['aggregate']['reasoning_tokens'] == 40
    assert receipt.as_dict()['attempts'][0]['reasoning_tokens'] == 40


def test_vertex_and_anthropic_usage_preserve_provider_cache_fields() -> None:
    vertex = vertex_usage_from_response(
        {
            'responseId': 'vertex-response',
            'modelVersion': 'gemini-2.5-flash-001',
            'trafficType': 'ON_DEMAND',
            'usageMetadata': {
                'promptTokenCount': 1_000,
                'cachedContentTokenCount': 250,
                'candidatesTokenCount': 100,
                'thoughtsTokenCount': 50,
                'toolUsePromptTokenCount': 20,
                'totalTokenCount': 1_150,
            },
        }
    )
    anthropic = anthropic_usage_from_response(
        {
            'id': 'msg_123',
            'model': 'claude-sonnet-5',
            'usage': {
                'input_tokens': 700,
                'cache_read_input_tokens': 300,
                'cache_creation_input_tokens': 50,
                'output_tokens': 125,
            },
        },
        cache_requested=True,
        cache_write_ttl='1h',
    )

    assert vertex.usage is not None
    assert vertex.usage.cached_input_tokens == 250
    assert vertex.usage.uncached_input_tokens == 750
    assert vertex.usage.reasoning_tokens == 50
    assert vertex.usage.cache_status == CacheStatus.PARTIAL_HIT
    assert vertex.actual_model_version == 'gemini-2.5-flash-001'
    assert vertex.traffic_type == 'ON_DEMAND'

    assert anthropic.usage is not None
    assert anthropic.usage.cached_input_tokens == 300
    assert anthropic.usage.cache_write_tokens == 50
    assert anthropic.usage.cache_write_ttl == '1h'
    assert anthropic.usage.cache_status == CacheStatus.PARTIAL_HIT


def test_anthropic_tool_cache_control_marks_an_explicit_cache_attempt() -> None:
    from llm_gateway.gateway.accounting import cache_requested_for_anthropic_request

    request = {'tools': [{'name': 'search', 'cache_control': {'type': 'ephemeral', 'ttl': '1h'}}]}
    assert cache_requested_for_anthropic_request(request)
    assert cache_write_ttl_for_anthropic_request(request) == '1h'


def test_anthropic_automatic_cache_control_is_accounted() -> None:
    from llm_gateway.gateway.accounting import cache_requested_for_anthropic_request

    request = {'cache_control': {'type': 'ephemeral', 'ttl': '1h'}, 'messages': []}
    assert cache_requested_for_anthropic_request(request)
    assert cache_write_ttl_for_anthropic_request(request) == '1h'


def test_rate_card_estimate_uses_cached_input_price_and_never_priceless_unknowns() -> None:
    context = _context()
    trace = AttemptTrace()
    priced_attempt = trace.record(
        provider='openai',
        configured_model='gpt-5.4-nano',
        route_artifact_id='route.test.001',
        fallback_reason=None,
        retry_ordinal=1,
        outcome='success',
        error_class='none',
        metadata=ProviderResponseMetadata(
            usage=ProviderUsage(
                prompt_tokens=1_000_000,
                cached_input_tokens=200_000,
                uncached_input_tokens=800_000,
                output_tokens=1_000_000,
                total_tokens=2_000_000,
                cache_status=CacheStatus.PARTIAL_HIT,
            )
        ),
    )
    unknown_attempt = trace.record(
        provider='anthropic',
        configured_model='unknown-model',
        route_artifact_id='route.test.001',
        fallback_reason=None,
        retry_ordinal=1,
        outcome='success',
        error_class='none',
        metadata=ProviderResponseMetadata(usage=ProviderUsage(prompt_tokens=10, uncached_input_tokens=10)),
    )
    byok_context = AccountingContext(
        invocation_id='invocation-byok',
        request_id='request-byok',
        caller='backend',
        user_uid='user-123',
        feature='chat',
        api_surface='openai_chat_completions',
        payer='byok',
    )

    priced = build_accounting_event(context, priced_attempt)
    unknown = build_accounting_event(context, unknown_attempt)
    byok = build_accounting_event(byok_context, priced_attempt)

    assert priced.cost_status == CostStatus.ESTIMATED
    assert priced.estimated_cost_micro_usd == 1_414_000
    assert priced.estimated_cache_savings_micro_usd == 36_000
    assert priced.rate_card_id == 'openai.gpt-5.4-nano.2026-07-17'
    assert unknown.cost_status == CostStatus.UNPRICED
    assert unknown.estimated_cost_micro_usd is None
    assert byok.cost_status == CostStatus.NOT_OMI_COST
    assert byok.estimated_cost_micro_usd == 0


def test_anthropic_cache_write_uses_the_requested_ttl_rate() -> None:
    trace = AttemptTrace()
    attempt = trace.record(
        provider='anthropic',
        configured_model='claude-sonnet-5',
        route_artifact_id='route.test.001',
        fallback_reason=None,
        retry_ordinal=1,
        outcome='success',
        error_class='none',
        metadata=ProviderResponseMetadata(
            usage=ProviderUsage(
                prompt_tokens=2_000_000,
                cached_input_tokens=1_000_000,
                uncached_input_tokens=1_000_000,
                output_tokens=1_000_000,
                cache_write_tokens=1_000_000,
                cache_write_ttl='1h',
            )
        ),
    )

    event = build_accounting_event(_context(), attempt)

    assert event.cost_status == CostStatus.ESTIMATED
    assert event.estimated_cost_micro_usd == 16_200_000
    assert event.rate_card_id == 'anthropic.claude-sonnet-5.intro.2026-07-17'


def test_image_generation_uses_a_size_and_quality_rate_card() -> None:
    trace = AttemptTrace()
    attempt = trace.record(
        provider='openai',
        configured_model='gpt-image-1',
        route_artifact_id=None,
        fallback_reason=None,
        retry_ordinal=1,
        outcome='success',
        error_class='none',
        metadata=ProviderResponseMetadata(usage=image_usage(count=2, size='1024x1024', quality='high')),
    )

    event = build_accounting_event(_context(), attempt)

    assert event.cost_status == CostStatus.ESTIMATED
    assert event.estimated_cost_micro_usd == 334_000
    assert event.cost_basis == 'per_image_generation_rate_excludes_prompt_input_tokens'


def test_firestore_ledger_write_is_immutable_idempotent_and_snapshots_subscription_tier() -> None:
    client = _FakeFirestoreClient(subscription_plan='pro')
    event = {'attempt_id': 'invocation-1:1', 'provider': 'openai', 'user_uid': 'user-123'}

    assert record_llm_gateway_attempt(event, firestore_client=client)
    assert not record_llm_gateway_attempt(event, firestore_client=client)
    stored = client.collections[ATTEMPTS_COLLECTION]['invocation-1:1']
    assert stored['subscription_tier'] == 'pro'
    assert stored['plan_id'] == 'architect'
    assert stored['plan_attribution_status'] == 'complete'
    assert stored['cost_attribution_status'] == 'missing'


def test_firestore_ledger_marks_priced_omi_cost_complete_for_the_canonical_plan() -> None:
    client = _FakeFirestoreClient(subscription_plan='operator')
    event = {
        'attempt_id': 'invocation-1:2',
        'provider': 'openai',
        'user_uid': 'user-123',
        'payer': 'omi',
        'cost_status': 'estimated',
        'estimated_cost_micro_usd': 2500,
    }

    assert record_llm_gateway_attempt(event, firestore_client=client)
    stored = client.collections[ATTEMPTS_COLLECTION]['invocation-1:2']
    assert stored['plan_id'] == 'operator'
    assert stored['cost_attribution_status'] == 'complete'


@pytest.mark.asyncio
async def test_accounting_sink_records_delivery_failure_without_failing_the_request(monkeypatch) -> None:
    monkeypatch.setenv(accounting_sink.ACCOUNTING_ENABLED_ENV_VAR, 'true')
    deliveries: list[str] = []
    trace = AttemptTrace()
    trace.record(
        provider='openai',
        configured_model='gpt-5.4-nano',
        route_artifact_id='route.test.001',
        fallback_reason=None,
        retry_ordinal=1,
        outcome='success',
        error_class='none',
        metadata=ProviderResponseMetadata(usage=ProviderUsage(prompt_tokens=10, uncached_input_tokens=10)),
    )

    async def unavailable_writer(*_args: Any, **_kwargs: Any) -> bool:
        raise RuntimeError('firestore unavailable')

    monkeypatch.setattr(accounting_sink, 'run_blocking', unavailable_writer)
    monkeypatch.setattr(
        accounting_sink, 'observe_accounting_event', lambda _event, *, delivery: deliveries.append(delivery)
    )

    await accounting_sink.persist_attempt_trace(_context(), trace)

    assert deliveries == ['failed']


@pytest.mark.asyncio
async def test_accounting_sink_schedules_writes_without_waiting_for_firestore(monkeypatch) -> None:
    monkeypatch.setenv(accounting_sink.ACCOUNTING_ENABLED_ENV_VAR, 'true')
    started = asyncio.Event()
    release = asyncio.Event()

    async def blocked_persist(*_args: Any, **_kwargs: Any) -> None:
        started.set()
        await release.wait()

    monkeypatch.setattr(accounting_sink, 'persist_attempt_trace', blocked_persist)
    trace = AttemptTrace()
    trace.record(
        provider='openai',
        configured_model='gpt-5.4-nano',
        route_artifact_id='route.test.001',
        fallback_reason=None,
        retry_ordinal=1,
        outcome='success',
        error_class='none',
    )

    accounting_sink.schedule_attempt_trace(_context(), trace)

    assert not started.is_set()
    await started.wait()
    release.set()
    await accounting_sink.drain_accounting_persistence_tasks()


@pytest.mark.asyncio
async def test_accounting_sink_bounds_pending_traces_and_reports_overflow(monkeypatch) -> None:
    monkeypatch.setenv(accounting_sink.ACCOUNTING_ENABLED_ENV_VAR, 'true')
    monkeypatch.setenv(accounting_sink.ACCOUNTING_MAX_PENDING_TRACES_ENV_VAR, '1')
    started = asyncio.Event()
    release = asyncio.Event()
    deliveries: list[str] = []

    async def blocked_persist(*_args: Any, **_kwargs: Any) -> None:
        started.set()
        await release.wait()

    monkeypatch.setattr(accounting_sink, 'persist_attempt_trace', blocked_persist)
    monkeypatch.setattr(
        accounting_sink, 'observe_accounting_event', lambda _event, *, delivery: deliveries.append(delivery)
    )
    trace = AttemptTrace()
    trace.record(
        provider='openai',
        configured_model='gpt-5.4-nano',
        route_artifact_id='route.test.001',
        fallback_reason=None,
        retry_ordinal=1,
        outcome='success',
        error_class='none',
    )

    accounting_sink.schedule_attempt_trace(_context(), trace)
    await started.wait()
    accounting_sink.schedule_attempt_trace(_context(), trace)

    assert deliveries == ['dropped']
    release.set()
    await accounting_sink.drain_accounting_persistence_tasks()


def _context() -> AccountingContext:
    return AccountingContext(
        invocation_id='invocation-1',
        request_id='request-1',
        caller='backend',
        user_uid='user-123',
        feature='chat',
        api_surface='openai_chat_completions',
        payer='omi',
    )


class _FakeSnapshot:
    def __init__(self, data: dict[str, Any] | None) -> None:
        self.exists = data is not None
        self._data = data

    def to_dict(self) -> dict[str, Any] | None:
        return self._data


class _FakeDocument:
    def __init__(self, collection: '_FakeCollection', document_id: str) -> None:
        self._collection = collection
        self._document_id = document_id

    def create(self, data: dict[str, Any]) -> None:
        if self._document_id in self._collection.documents:
            raise AlreadyExists('attempt already exists')
        self._collection.documents[self._document_id] = dict(data)

    def get(self, _fields: list[str]) -> _FakeSnapshot:
        return _FakeSnapshot(self._collection.documents.get(self._document_id))


class _FakeCollection:
    def __init__(self, documents: dict[str, dict[str, Any]]) -> None:
        self.documents = documents

    def document(self, document_id: str) -> _FakeDocument:
        return _FakeDocument(self, document_id)


class _FakeFirestoreClient:
    def __init__(self, *, subscription_plan: str) -> None:
        self.collections: dict[str, dict[str, dict[str, Any]]] = {
            ATTEMPTS_COLLECTION: {},
            'users': {'user-123': {'subscription': {'plan': subscription_plan}}},
        }

    def collection(self, name: str) -> _FakeCollection:
        return _FakeCollection(self.collections.setdefault(name, {}))


def test_long_context_threshold_is_pinned_and_exclusive() -> None:
    # The boundary is "more than 272K input tokens": exactly at 272,000 must
    # still use the short-context rate, and 272,001 must switch to long.
    trace = AttemptTrace()

    def _priced_cost(prompt_tokens: int) -> int | None:
        attempt = trace.record(
            provider='openai',
            configured_model='gpt-5.6-luna',
            route_artifact_id='route.test.001',
            fallback_reason=None,
            retry_ordinal=1,
            outcome='success',
            error_class='none',
            metadata=ProviderResponseMetadata(
                usage=ProviderUsage(
                    prompt_tokens=prompt_tokens,
                    uncached_input_tokens=prompt_tokens,
                    output_tokens=0,
                    output_tokens_include_reasoning=True,
                )
            ),
        )
        return build_accounting_event(_context(), attempt).estimated_cost_micro_usd

    at_boundary = _priced_cost(272_000)
    past_boundary = _priced_cost(272_001)

    # 272,000 * $0.20/M short rate = $54,400 micro-USD.
    assert at_boundary == 54_400
    # 272,001 * $0.40/M long rate, rounded = $108,800 micro-USD (rounds down
    # from 108800.4).
    assert past_boundary == 108_800


def test_model_with_no_long_context_tier_ignores_token_count() -> None:
    # gpt-5.4-nano has no long_context_* fields in cost_rate_cards.yaml, so
    # even a huge prompt must keep pricing at its single (short) rate.
    trace = AttemptTrace()
    attempt = trace.record(
        provider='openai',
        configured_model='gpt-5.4-nano',
        route_artifact_id='route.test.001',
        fallback_reason=None,
        retry_ordinal=1,
        outcome='success',
        error_class='none',
        metadata=ProviderResponseMetadata(
            usage=ProviderUsage(
                prompt_tokens=5_000_000,
                uncached_input_tokens=5_000_000,
                output_tokens=0,
                output_tokens_include_reasoning=True,
            )
        ),
    )
    event = build_accounting_event(_context(), attempt)

    # 5,000,000 * $0.20/M (the only rate this card has) = $1,000,000.
    assert event.estimated_cost_micro_usd == 1_000_000
    assert event.rate_card_id == 'openai.gpt-5.4-nano.2026-07-17'


def test_short_context_luna_request_uses_short_context_rates() -> None:
    # Same shape as the long-context test above, scaled down so total input
    # context (150K) stays under the 272K-token boundary.
    usage = openai_usage_from_response(
        {
            'id': 'chatcmpl-short',
            'usage': {
                'prompt_tokens': 150_000,
                'completion_tokens': 100_000,
                'prompt_tokens_details': {'cached_tokens': 30_000, 'cache_write_tokens': 60_000},
            },
        },
        cache_requested=True,
    ).usage
    assert usage is not None
    assert usage.uncached_input_tokens == 60_000

    trace = AttemptTrace()
    attempt = trace.record(
        provider='openai',
        configured_model='gpt-5.6-luna',
        route_artifact_id='route.conv_action_items.model_config.001',
        fallback_reason=None,
        retry_ordinal=1,
        outcome='success',
        error_class='none',
        metadata=ProviderResponseMetadata(usage=usage),
    )
    event = build_accounting_event(_context(), attempt)

    # Short-context rates: 60K uncached @ $0.20/M + 30K cached @ $0.02/M +
    # 100K output @ $1.20/M + 60K cache-write @ $0.25/M = $147,600 micro-USD.
    assert event.estimated_cost_micro_usd == 147_600
    assert event.rate_card_id == 'openai.gpt-5.6-luna.2026-07-30'


def _platform_attempt() -> Any:
    trace = AttemptTrace()
    return trace.record(
        provider='anthropic',
        configured_model='claude-sonnet-4-5',
        route_artifact_id='route.chat_agent.model_config.001',
        fallback_reason=None,
        retry_ordinal=0,
        outcome='success',
        error_class='none',
        metadata=ProviderResponseMetadata(usage=ProviderUsage(prompt_tokens=10, uncached_input_tokens=10)),
    )


def test_app_platform_is_recorded_on_the_accounting_event() -> None:
    """chat_agent spend must be splittable desktop vs mobile in the ledger."""
    context = AccountingContext.create(
        request_id='request-platform',
        caller='backend',
        user_uid='user-123',
        feature='chat_agent',
        api_surface='openai_chat_completions',
        payer='omi',
        app_platform='desktop',
    )

    event = build_accounting_event(context, _platform_attempt())

    assert event.app_platform == 'desktop'
    assert event.as_dict()['app_platform'] == 'desktop'


def test_unknown_app_platform_is_persisted_as_unattributed() -> None:
    event = build_accounting_event(_context(), _platform_attempt())

    assert event.app_platform is None
    assert event.as_dict()['app_platform'] is None
