from dataclasses import replace

import pytest

from llm_gateway.gateway import accounting as a
from llm_gateway.gateway.cache_metrics import CACHE_ATTEMPTS, CACHE_ELIGIBLE
from llm_gateway.gateway.dream_usage import with_dream_usage
from llm_gateway.gateway.provider_types import _openai_usage_payload


def test_per_attempt_receipts_preserve_unknown_and_reported_zero():
    trace = a.AttemptTrace()
    for raw in [
        {'promptTokenCount': 7000, 'candidatesTokenCount': 3},
        {'promptTokenCount': 7000, 'cachedContentTokenCount': 0, 'candidatesTokenCount': 4},
    ]:
        trace.record(
            provider='gemini',
            configured_model='gemini-3.8-flash',
            lane_id='omi:auto:dream-reasoning',
            route_artifact_id='synthetic-route',
            fallback_reason=None,
            retry_ordinal=1,
            outcome='success',
            error_class='none',
            metadata=replace(
                a.vertex_usage_from_response({'usageMetadata': raw}),
                cache_mode='implicit',
                cacheable_prefix_tokens=6500,
            ),
        )
    trace.record(
        provider='openai',
        configured_model='gpt-6-luna',
        lane_id='omi:auto:dream-reasoning',
        route_artifact_id='synthetic-route',
        fallback_reason=None,
        retry_ordinal=1,
        outcome='error',
        error_class='timeout_before_output',
    )
    summary = with_dream_usage({}, 'omi:auto:dream-reasoning', trace)['dream_usage']
    assert summary['prompt_tokens'] == 14000 and summary['completion_tokens'] == 7
    assert [x['cache_field_reported'] for x in summary['attempt_usage']] == [False, True, False]
    assert summary['attempt_usage'][2]['model'] == 'gpt-6-luna'
    assert summary['unknown_attempts'] >= 1
    assert 'cached_tokens' not in _openai_usage_payload(trace.attempts[0].usage)['prompt_tokens_details']
    for reported in ('true', 'false'):
        assert (
            CACHE_ELIGIBLE.labels(
                lane='omi:auto:dream-reasoning', model='gemini-3.8-flash', mode='implicit', reported=reported
            )._value.get()
            >= 1
        )


def test_storage_and_creation_costs_are_not_silently_zero(monkeypatch):
    card = a.RateCard(
        rate_card_id='synthetic-rate',
        provider='gemini',
        model='gemini-3.8-flash',
        input_micro_usd_per_million=1000000,
        cached_input_micro_usd_per_million=100000,
        output_micro_usd_per_million=2000000,
        cache_write_micro_usd_per_million=1000000,
        cache_storage_micro_usd_per_million_token_hours=1000000,
    )
    monkeypatch.setattr(a, 'rate_card_for', lambda *_: card)
    usage = a.ProviderUsage(
        prompt_tokens=10000,
        cached_input_tokens=8000,
        uncached_input_tokens=2000,
        output_tokens=100,
        cache_write_tokens=10000,
        cache_storage_token_seconds=10000 * 1800,
    )
    status, cost, *_ = a._estimate_cost(
        payer='omi',
        provider='gemini',
        model='gemini-3.8-flash',
        usage=usage,
        usage_status=a.UsageStatus.CONFIRMED,
        traffic_type='PROVISIONED_THROUGHPUT',
    )
    assert status == a.CostStatus.ESTIMATED and cost == 18000
    for missing in ('cache_storage_micro_usd_per_million_token_hours', 'cache_write_micro_usd_per_million'):
        monkeypatch.setattr(a, 'rate_card_for', lambda *_, missing=missing: replace(card, **{missing: None}))
        assert a._estimate_cost(
            payer='omi',
            provider='gemini',
            model='gemini-3.8-flash',
            usage=usage,
            usage_status=a.UsageStatus.CONFIRMED,
            traffic_type='ON_DEMAND',
        )[:2] == (a.CostStatus.UNPRICED, None)


def test_stream_receipt_metadata_preserves_missing_cache_field():
    metadata = a.openai_usage_from_sse_payload(
        {
            'usage': {'prompt_tokens': 7000, 'completion_tokens': 4, 'prompt_tokens_details': {}},
            '_gateway_cache_receipt': {
                'lane': 'omi:auto:dream-reasoning',
                'mode': 'explicit',
                'prefix_tokens': 6000,
                'write_tokens': 6100,
                'storage_token_seconds': 10980000,
            },
        },
        cache_requested=True,
    )
    assert metadata.usage.cache_status == a.CacheStatus.NOT_REPORTED
    assert metadata.cache_mode == 'explicit' and metadata.cache_write_tokens == 6100
    assert metadata.cache_storage_token_seconds == 10980000


def test_initial_stream_receipt_does_not_invent_usage():
    metadata = a.openai_usage_from_sse_payload(
        {
            'choices': [{'delta': {'content': 'invented'}}],
            '_gateway_cache_receipt': {
                'lane': 'omi:auto:dream-reasoning',
                'mode': 'explicit',
                'prefix_tokens': 6000,
                'write_tokens': 6100,
                'storage_token_seconds': 10980000,
            },
        }
    )
    assert metadata.usage is None
    assert metadata.cache_write_tokens == 6100


def test_resolved_model_drives_attempt_price_and_receipt(monkeypatch):
    models = []
    card = a.RateCard(
        rate_card_id='synthetic-rate',
        provider='gemini',
        model='gemini-3.8-flash',
        input_micro_usd_per_million=1000000,
        cached_input_micro_usd_per_million=100000,
        output_micro_usd_per_million=2000000,
    )

    def card_for(provider, model):
        models.append(model)
        return card

    monkeypatch.setattr(a, 'rate_card_for', card_for)
    trace = a.AttemptTrace()
    attempt = trace.record(
        provider='gemini',
        configured_model='synthetic-anchor',
        route_artifact_id='synthetic-route',
        fallback_reason=None,
        retry_ordinal=1,
        outcome='success',
        error_class='none',
        metadata=a.ProviderResponseMetadata(
            usage=a.ProviderUsage(prompt_tokens=10, uncached_input_tokens=10), resolved_model='gemini-3.8-flash'
        ),
    )
    context = a.AccountingContext.create(
        request_id='synthetic-request',
        caller='backend',
        user_uid=None,
        feature=None,
        api_surface='openai_chat_completions',
        payer='omi',
    )
    event = a.build_accounting_event(context, attempt)
    assert models == ['gemini-3.8-flash']
    assert event.as_dict()['resolved_model'] == 'gemini-3.8-flash'
    assert (
        with_dream_usage({}, 'omi:auto:dream-reasoning', trace)['dream_usage']['attempt_usage'][0]['model']
        == 'gemini-3.8-flash'
    )
