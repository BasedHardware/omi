from dataclasses import replace
from types import SimpleNamespace
from uuid import uuid4

import pytest

from config.proactivity_v2 import ProactivityDenied
from database import proactivity_budget as money
from llm_gateway.gateway import proactivity_budget as gate
from llm_gateway.gateway.accounting import AccountingContext, AttemptTrace, ProviderResponseMetadata, ProviderUsage
from llm_gateway.gateway.auth import ServiceCaller
from llm_gateway.gateway.config_loader import load_gateway_config
from llm_gateway.gateway.credentials import build_omi_managed_credential_context
from llm_gateway.gateway.errors import GatewayInvalidRequestError
from llm_gateway.gateway.executor import ProviderRegistry, execute_chat_completion, execute_systemone
from llm_gateway.gateway.providers import ProviderResponse
from llm_gateway.gateway.resolver import resolve_chat_completion_route, resolve_systemone_route
from tests.unit.test_proactivity_v2_budget import NOW, Redis, claim, store


def context(item, step='phrase'):
    call_id = str(uuid4())
    accounting = AccountingContext.create(
        request_id=call_id,
        caller='backend',
        user_uid='u',
        feature=f"proactivity_v2_{item['producer']}",
        api_surface='openai_chat_completions',
        payer='omi',
    )
    return gate.ProactivityAttemptContext('u', item['item_id'], item['producer'], call_id, step, accounting)


class Provider:
    def __init__(self, fail=False):
        self.calls = 0
        self.fail = fail

    async def create_chat_completion(self, request, **kwargs):
        self.calls += 1
        if self.fail:
            raise RuntimeError('ambiguous')
        return ProviderResponse(
            response={'choices': [{'message': {'content': 'synthetic'}, 'finish_reason': 'stop'}]},
            accounting=ProviderResponseMetadata(
                usage=ProviderUsage(prompt_tokens=10, uncached_input_tokens=10, output_tokens=3)
            ),
        )

    async def create_systemone(self, request, **kwargs):
        return await self.create_chat_completion(request, **kwargs)


@pytest.fixture
def gated(store, monkeypatch):
    authority = money.BudgetAuthority(firestore_client=store, redis_client=Redis(), clock=lambda: NOW)

    async def admit(*args):
        return None

    monkeypatch.setattr(gate, 'ensure_admitted', admit)
    monkeypatch.setattr(gate, 'BudgetAuthority', lambda: authority)
    monkeypatch.setenv('LLM_GATEWAY_ACCOUNTING_ENABLED', 'true')
    return authority


@pytest.mark.asyncio
async def test_real_executor_reserves_settles_and_tags_same_event(store, gated, monkeypatch):
    events = []
    monkeypatch.setattr(money, 'record_llm_gateway_attempt', lambda event, **kwargs: events.append(event))
    item = claim(store)
    ctx = context(item)
    route = resolve_chat_completion_route(
        load_gateway_config(),
        {
            'model': 'omi:auto:proactive-notification',
            'messages': [{'role': 'user', 'content': 'synthetic'}],
            'max_completion_tokens': 512,
        },
    )
    provider = Provider()
    trace = AttemptTrace()
    credentials = build_omi_managed_credential_context(ServiceCaller(name='backend', user_uid='u'))
    with gate.attempt_scope(ctx):
        await execute_chat_completion(route, credentials, ProviderRegistry({'openai': provider}), attempt_trace=trace)
    assert provider.calls == 1
    assert len(events) == len(trace.attempts) == 1
    assert events[0]['feature'] == 'proactivity_v2_commitment_followup'
    assert events[0]['request_id'] == ctx.call_id
    row = store.rows[('users', 'u', 'proactivity_items', item['item_id'])]
    assert row['cost_status'] == 'estimated'
    assert row['estimated_cost_micro_usd'] == events[0]['estimated_cost_micro_usd']


@pytest.mark.asyncio
async def test_failure_has_one_attempt_no_fallback_and_retains_money(store, gated):
    item = claim(store)
    route = resolve_chat_completion_route(
        load_gateway_config(),
        {
            'model': 'omi:auto:proactive-notification',
            'messages': [{'role': 'user', 'content': 'synthetic'}],
            'max_completion_tokens': 512,
        },
    )
    provider = Provider(fail=True)
    credentials = build_omi_managed_credential_context(ServiceCaller(name='backend', user_uid='u'))
    with gate.attempt_scope(context(item)), pytest.raises(GatewayInvalidRequestError):
        await execute_chat_completion(
            route, credentials, ProviderRegistry({'openai': provider}), attempt_trace=AttemptTrace()
        )
    assert provider.calls == 1
    row = store.rows[('users', 'u', 'proactivity_items', item['item_id'])]
    assert row['charged_micro_usd'] > 0 and row['cost_status'] == 'indeterminate'


@pytest.mark.asyncio
async def test_jev_executor_uses_same_authority(store, gated):
    item = claim(store, producer='conversation_mentor_v2')
    route = resolve_systemone_route(
        load_gateway_config(),
        {
            'model': 'omi:auto:jev-decisions',
            'state': 'synthetic',
            'questions': {
                'worth': {'type': 'noul', 'instructions': 'Keep?', 'criteria': {'true': 'yes', 'false': 'no'}}
            },
        },
    )
    provider = Provider()
    credentials = build_omi_managed_credential_context(ServiceCaller(name='backend', user_uid='u'))
    with gate.attempt_scope(context(item, 'prefilter')):
        await execute_systemone(
            route, credentials, ProviderRegistry({'openrouter': provider}), attempt_trace=AttemptTrace()
        )
    assert provider.calls == 1


def test_envelope_prices_jev_bytes_with_framing_and_rejects_unbounded_content(store):
    ctx = context(claim(store, producer='conversation_mentor_v2'), 'prefilter')
    envelope = gate.envelope_for(ctx, 'openrouter', 'typesafe/jev-1.13', {'state': 'synthetic', 'questions': {}})
    assert envelope.worst_case_micro_usd >= 173
    with pytest.raises(ProactivityDenied, match='input_bound'):
        gate.envelope_for(ctx, 'openrouter', 'typesafe/jev-1.13', {'state': 'x' * 40000, 'questions': {}})
    ctx = replace(ctx, step='generate')
    with pytest.raises(ProactivityDenied, match='invalid_request'):
        gate.envelope_for(
            ctx,
            'openai',
            'gpt-6-luna',
            {'messages': [{'role': 'user', 'content': [{'type': 'image_url'}]}], 'max_completion_tokens': 512},
        )


@pytest.mark.asyncio
@pytest.mark.parametrize('fault', ['store', 'flag', 'unpriced', 'accounting'])
async def test_executor_denials_never_reach_provider(store, gated, monkeypatch, fault):
    item = claim(store)
    route = resolve_chat_completion_route(
        load_gateway_config(),
        {
            'model': 'omi:auto:proactive-notification',
            'messages': [{'role': 'user', 'content': 'synthetic'}],
            'max_completion_tokens': 512,
        },
    )
    if fault == 'store':
        gated.redis.down = True
    elif fault == 'flag':

        async def denied(*args):
            raise ProactivityDenied('disabled')

        monkeypatch.setattr(gate, 'ensure_admitted', denied)
    elif fault == 'unpriced':
        monkeypatch.setattr(gate, 'rate_card_for', lambda *args: None)
    else:
        monkeypatch.delenv('LLM_GATEWAY_ACCOUNTING_ENABLED')
    provider = Provider()
    with gate.attempt_scope(context(item)), pytest.raises(GatewayInvalidRequestError):
        await execute_chat_completion(
            route,
            build_omi_managed_credential_context(ServiceCaller(name='backend', user_uid='u')),
            ProviderRegistry({'openai': provider}),
            attempt_trace=AttemptTrace(),
        )
    assert provider.calls == 0
