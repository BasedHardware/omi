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
