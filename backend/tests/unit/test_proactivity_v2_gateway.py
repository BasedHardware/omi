from dataclasses import replace
from types import SimpleNamespace
from uuid import uuid4

import pytest

from config.proactivity_v2 import ProactivityDenied, producer_for
from database import proactivity_budget as money
from llm_gateway.gateway import proactivity_budget as gate
from llm_gateway.gateway.accounting import (
    AccountingContext,
    AttemptTrace,
    ProviderResponseMetadata,
    ProviderUsage,
    openai_usage_from_response,
)
from llm_gateway.gateway.auth import ServiceCaller
from llm_gateway.gateway.config_loader import load_gateway_config
from llm_gateway.gateway.credentials import build_omi_managed_credential_context
from llm_gateway.gateway.errors import GatewayInvalidRequestError
from llm_gateway.gateway.executor import ProviderRegistry, execute_chat_completion, execute_systemone
from llm_gateway.gateway.providers import ProviderResponse
from llm_gateway.gateway.resolver import resolve_chat_completion_route, resolve_systemone_route
from tests.unit.test_proactivity_v2_budget import NOW, Redis, claim, store
from utils import proactivity


@pytest.mark.asyncio
async def test_admission_flag_unavailable_logs_sdk_type_and_status(monkeypatch, caplog):
    from collections import OrderedDict
    from unittest.mock import Mock

    from posthog.request import APIError

    flags = proactivity.proactivity_flags
    monkeypatch.setattr(flags, '_flag_cache', OrderedDict())
    monkeypatch.setattr(flags, '_next_warning_at', 0.0)
    client = Mock()
    client.get_feature_variants.side_effect = APIError(503, 'PRIVATE_RESPONSE_AND_KEY')
    monkeypatch.setattr(flags, 'flag_client', lambda: client)
    with caplog.at_level('INFO'):
        for _ in range(2):
            with pytest.raises(ProactivityDenied, match='flag_unavailable'):
                await proactivity.ensure_admitted('PRIVATE_UID', 'conversation_mentor_v2')
    client.get_feature_variants.assert_called_once_with('PRIVATE_UID')
    assert 'error_type=APIError http_status=503' in caplog.text
    assert 'result=denied reason=flag_unavailable' in caplog.text
    assert 'PRIVATE' not in caplog.text


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
                usage=ProviderUsage(prompt_tokens=10, uncached_input_tokens=10, output_tokens=3),
                billable_usage_complete=True,
            ),
        )

    async def create_systemone(self, request, **kwargs):
        return await self.create_chat_completion(request, **kwargs)


@pytest.fixture
def gated(store, monkeypatch):
    authority = money.BudgetAuthority(firestore_client=store, redis_client=Redis(), clock=lambda: NOW)

    async def admit(*args):
        return None

    monkeypatch.setattr(proactivity, 'ensure_admitted', admit)
    monkeypatch.setattr(money, 'BudgetAuthority', lambda: authority)
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


def test_usefulness_authenticated_attribution_and_lane_fence(store):
    ctx = context(claim(store, producer='conversation_mentor_v2'), 'usefulness')
    request = SimpleNamespace(
        headers={
            'x-omi-proactivity-item': ctx.item_id,
            'x-omi-proactivity-producer': ctx.producer,
            'x-omi-proactivity-call': ctx.call_id,
            'x-omi-proactivity-step': ctx.step,
        }
    )
    caller = SimpleNamespace(name='backend', user_uid='u', usage_feature=ctx.accounting.feature)
    assert gate.context_from_request(request, caller, ctx.accounting).step == 'usefulness'
    with pytest.raises(ProactivityDenied, match='invalid_lane'):
        gate.envelope_for(
            ctx,
            'openai',
            'gpt-6-luna',
            {
                'messages': [{'role': 'user', 'content': 'judge'}],
                'max_completion_tokens': 512,
            },
        )
    caller.name = 'desktop'
    with pytest.raises(GatewayInvalidRequestError):
        gate.context_from_request(request, caller, ctx.accounting)


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
    with gate.attempt_scope(context(item)), pytest.raises(GatewayInvalidRequestError) as error:
        await execute_chat_completion(
            route, credentials, ProviderRegistry({'openai': provider}), attempt_trace=AttemptTrace()
        )
    assert error.value.rejection_reason == 'proactivity_provider_failed'
    assert provider.calls == 1
    row = store.rows[('users', 'u', 'proactivity_items', item['item_id'])]
    assert row['charged_micro_usd'] > 0 and row['cost_status'] == 'indeterminate'


@pytest.mark.asyncio
@pytest.mark.parametrize('step', ['prefilter', 'dedupe', 'usefulness'])
async def test_jev_executor_uses_same_authority(store, gated, step):
    question = (
        {'type': 'score', 'instructions': 'Repeat?', 'criteria': ['a', 'b', 'c', 'd', 'e']}
        if step == 'dedupe'
        else {'type': 'noul', 'instructions': 'Keep?', 'criteria': {'true': 'yes', 'false': 'no'}}
    )
    item = claim(store, producer='conversation_mentor_v2')
    route = resolve_systemone_route(
        load_gateway_config(),
        {
            'model': 'omi:auto:jev-decisions',
            'state': 'synthetic',
            'questions': {'worth': question},
        },
    )
    provider = Provider()
    credentials = build_omi_managed_credential_context(ServiceCaller(name='backend', user_uid='u'))
    with gate.attempt_scope(context(item, step)):
        await execute_systemone(
            route, credentials, ProviderRegistry({'openrouter': provider}), attempt_trace=AttemptTrace()
        )
    assert provider.calls == 1
    row = store.rows[('users', 'u', 'proactivity_items', item['item_id'])]
    assert row['cost_status'] == 'estimated'
    assert next(iter(row['attempts'].values()))['step'] == step


def test_envelope_prices_jev_bytes_with_framing_and_rejects_unbounded_content(store):
    ctx = context(claim(store, producer='conversation_mentor_v2'), 'prefilter')
    envelope = gate.envelope_for(ctx, 'openrouter', 'typesafe/jev-1.13', {'state': 'synthetic', 'questions': {}})
    assert envelope.worst_case_micro_usd >= 173
    with pytest.raises(ProactivityDenied, match='input_bound'):
        gate.envelope_for(
            ctx,
            'openrouter',
            'typesafe/jev-1.13',
            {'state': 'x' * (producer_for(ctx.producer).max_request_bytes + 1), 'questions': {}},
        )
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

        monkeypatch.setattr(proactivity, 'ensure_admitted', denied)
    elif fault == 'unpriced':
        monkeypatch.setattr(gate, 'rate_card_for', lambda *args: None)
    else:
        monkeypatch.delenv('LLM_GATEWAY_ACCOUNTING_ENABLED')
    provider = Provider()
    with gate.attempt_scope(context(item)), pytest.raises(GatewayInvalidRequestError) as error:
        await execute_chat_completion(
            route,
            build_omi_managed_credential_context(ServiceCaller(name='backend', user_uid='u')),
            ProviderRegistry({'openai': provider}),
            attempt_trace=AttemptTrace(),
        )
    assert provider.calls == 0
    reason = {'store': 'unavailable', 'flag': 'disabled', 'unpriced': 'unpriced', 'accounting': 'accounting_disabled'}[
        fault
    ]
    assert error.value.rejection_reason == f'proactivity_admission.{reason}'


def test_legacy_output_limit_cannot_bypass_reasoning_bound(store):
    ctx = context(claim(store))
    with pytest.raises(ProactivityDenied, match='invalid_request'):
        gate.envelope_for(
            ctx, 'openai', 'gpt-6-luna', {'messages': [{'role': 'user', 'content': 'synthetic'}], 'max_tokens': 512}
        )


@pytest.mark.asyncio
async def test_missing_provider_usage_retains_reservation_and_denies_publication(store, gated):
    class MissingUsage(Provider):
        async def create_chat_completion(self, request, **kwargs):
            self.calls += 1
            return ProviderResponse(response={'choices': []}, accounting=ProviderResponseMetadata())

    item = claim(store)
    route = resolve_chat_completion_route(
        load_gateway_config(),
        {
            'model': 'omi:auto:proactive-notification',
            'messages': [{'role': 'user', 'content': 'synthetic'}],
            'max_completion_tokens': 512,
        },
    )
    provider = MissingUsage()
    with gate.attempt_scope(context(item)), pytest.raises(GatewayInvalidRequestError) as error:
        await execute_chat_completion(
            route,
            build_omi_managed_credential_context(ServiceCaller(name='backend', user_uid='u')),
            ProviderRegistry({'openai': provider}),
            attempt_trace=AttemptTrace(),
        )
    row = store.rows[('users', 'u', 'proactivity_items', item['item_id'])]
    assert provider.calls == 1 and row['cost_status'] == 'indeterminate'
    assert error.value.rejection_reason == 'proactivity_settlement_rejected'
    assert row['charged_micro_usd'] == row['reserved_micro_usd'] > 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'usage,valid',
    [
        ({'total_tokens': 2000}, False),
        ({'prompt_tokens': 10}, False),
        ({'completion_tokens': 3}, False),
        *[({'prompt_tokens': value, 'completion_tokens': 3}, False) for value in [-1, 1.5, '10', True, None]],
        *[({'prompt_tokens': 10, 'completion_tokens': value}, False) for value in [-1, 1.5, '3', False, None]],
        ({'prompt_tokens': 10, 'completion_tokens': 3, 'total_tokens': 12}, False),
        ({'prompt_tokens': 10, 'completion_tokens': 3, 'total_tokens': -1}, False),
        ({'prompt_tokens': 10, 'completion_tokens': 3, 'total_tokens': 13.0}, False),
        ({'prompt_tokens': 10, 'completion_tokens': 3, 'prompt_tokens_details': {'cached_tokens': 11}}, False),
        ({'prompt_tokens': 10, 'completion_tokens': 3, 'prompt_tokens_details': {'cached_tokens': -1}}, False),
        ({'prompt_tokens': 10, 'completion_tokens': 3, 'completion_tokens_details': {'reasoning_tokens': 4}}, False),
        ({'prompt_tokens': 0, 'completion_tokens': 0, 'total_tokens': 0}, True),
        ({'input_tokens': 0, 'output_tokens': 0}, True),
        ({'prompt_tokens': 10, 'completion_tokens': 3, 'total_tokens': 13}, True),
    ],
)
async def test_raw_usage_receipt_real_executor_retains_full_hold_unless_complete(store, gated, usage, valid):
    class RawReceipt(Provider):
        async def create_chat_completion(self, request, **kwargs):
            self.calls += 1
            return ProviderResponse(response={'choices': []}, accounting=openai_usage_from_response({'usage': usage}))

    item = claim(store)
    route = resolve_chat_completion_route(
        load_gateway_config(),
        {
            'model': 'omi:auto:proactive-notification',
            'messages': [{'role': 'user', 'content': 'synthetic'}],
            'max_completion_tokens': 512,
        },
    )
    provider = RawReceipt()
    trace = AttemptTrace()
    with gate.attempt_scope(context(item)):
        if valid:
            await execute_chat_completion(
                route,
                build_omi_managed_credential_context(ServiceCaller(name='backend', user_uid='u')),
                ProviderRegistry({'openai': provider}),
                attempt_trace=trace,
            )
        else:
            with pytest.raises(GatewayInvalidRequestError, match='settlement rejected'):
                await execute_chat_completion(
                    route,
                    build_omi_managed_credential_context(ServiceCaller(name='backend', user_uid='u')),
                    ProviderRegistry({'openai': provider}),
                    attempt_trace=trace,
                )
    row = store.rows[('users', 'u', 'proactivity_items', item['item_id'])]
    attempt = next(iter(row['attempts'].values()))
    assert provider.calls == 1
    if valid:
        assert attempt['state'] == 'settled' and row['cost_status'] == 'estimated'
    else:
        assert attempt['state'] == 'unknown' and row['cost_status'] == 'indeterminate'
        assert row['charged_micro_usd'] == row['reserved_micro_usd'] > 0
        assert trace.attempts[0].usage_status.value == 'indeterminate'


@pytest.mark.asyncio
@pytest.mark.parametrize('flag,admitted', [(True, True), (False, False), (None, False), ('error', False)])
async def test_gateway_cohort_admission_uses_same_user_resolver(store, monkeypatch, flag, admitted):
    from utils import proactivity as service

    monkeypatch.setenv('MENTOR_PIPELINE', 'cohort')

    def resolve(uid):
        if flag == 'error':
            raise ConnectionError('flag service unavailable')
        return flag is True

    monkeypatch.setattr(service.proactivity_flags, 'enabled', resolve)
    monkeypatch.setattr(service.ledger, 'client_or_default', lambda client=None: store)
    monkeypatch.setattr(service.ledger, 'utc_now', lambda: NOW)
    monkeypatch.setattr(service.ledger, 'refresh_health', lambda *args, **kwargs: None)
    monkeypatch.setattr(service, 'utc_now', lambda: NOW)
    monkeypatch.setenv('LLM_GATEWAY_ACCOUNTING_ENABLED', 'true')
    authority = money.BudgetAuthority(firestore_client=store, redis_client=Redis(), clock=lambda: NOW)
    monkeypatch.setattr(money, 'BudgetAuthority', lambda: authority)
    item = claim(store, producer='conversation_mentor_v2')
    route = resolve_chat_completion_route(
        load_gateway_config(),
        {
            'model': 'omi:auto:proactive-notification',
            'messages': [{'role': 'user', 'content': 'synthetic'}],
            'max_completion_tokens': 512,
        },
    )
    provider = Provider()
    with gate.attempt_scope(context(item, 'generate')):
        if admitted:
            await execute_chat_completion(
                route,
                build_omi_managed_credential_context(ServiceCaller(name='backend', user_uid='u')),
                ProviderRegistry({'openai': provider}),
                attempt_trace=AttemptTrace(),
            )
        else:
            with pytest.raises(GatewayInvalidRequestError, match='admission denied'):
                await execute_chat_completion(
                    route,
                    build_omi_managed_credential_context(ServiceCaller(name='backend', user_uid='u')),
                    ProviderRegistry({'openai': provider}),
                    attempt_trace=AttemptTrace(),
                )
    assert provider.calls == int(admitted)
    row = store.rows[('users', 'u', 'proactivity_items', item['item_id'])]
    assert len(row['attempts']) == int(admitted)


def test_total_only_usage_keeps_legacy_accounting_behavior():
    from llm_gateway.gateway.accounting import build_accounting_event

    metadata = openai_usage_from_response({'usage': {'total_tokens': 2000}})
    trace = AttemptTrace()
    attempt = trace.record(
        provider='openai',
        configured_model='gpt-6-luna',
        route_artifact_id=None,
        fallback_reason=None,
        retry_ordinal=1,
        outcome='success',
        error_class='none',
        metadata=metadata,
    )
    event = build_accounting_event(
        AccountingContext.create(
            request_id='legacy',
            caller='backend',
            user_uid='u',
            feature='proactive_notification',
            api_surface='openai_chat_completions',
            payer='omi',
        ),
        attempt,
    )
    assert event.usage_status.value == 'confirmed' and event.estimated_cost_micro_usd == 0
    assert not metadata.billable_usage_complete


def test_followup_step_rejection_has_stable_code(store):
    ctx = context(claim(store), 'gate')
    request = SimpleNamespace(
        headers={
            'x-omi-proactivity-item': ctx.item_id,
            'x-omi-proactivity-producer': ctx.producer,
            'x-omi-proactivity-call': ctx.call_id,
            'x-omi-proactivity-step': ctx.step,
        }
    )
    caller = SimpleNamespace(name='backend', user_uid='u', usage_feature=ctx.accounting.feature)
    with pytest.raises(GatewayInvalidRequestError) as error:
        gate.context_from_request(request, caller, ctx.accounting)
    assert error.value.rejection_reason == 'proactivity_step'


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'fault,code',
    [
        ('authority', 'proactivity_authority_missing'),
        ('deadline', 'proactivity_deadline'),
        ('settlement', 'proactivity_settlement_unavailable'),
        ('denial', 'proactivity_admission.unknown'),
    ],
)
async def test_budget_boundary_errors_have_stable_payload_free_codes(store, gated, monkeypatch, fault, code, caplog):
    item = claim(store)
    provider = Provider()
    if fault == 'settlement':

        def unavailable(**kwargs):
            raise RuntimeError('PRIVATE_STORE_SECRET')

        monkeypatch.setattr(gated, 'settle', unavailable)
    elif fault == 'denial':

        async def denied(*args):
            raise ProactivityDenied('PRIVATE_USER_CONTENT\nforged=true')

        monkeypatch.setattr(proactivity, 'ensure_admitted', denied)
    with caplog.at_level('INFO'), gate.attempt_scope(None if fault == 'authority' else context(item)):
        with pytest.raises(GatewayInvalidRequestError) as error:
            await gate.execute_budgeted_provider(
                request={'messages': [{'role': 'user', 'content': 'synthetic'}], 'max_completion_tokens': 512},
                provider_ref=SimpleNamespace(provider='openai', model='gpt-6-luna'),
                route=SimpleNamespace(route_artifact_id='route.proactive_notification.model_config.001'),
                credentials=None,
                provider_call=provider.create_chat_completion,
                timeout_ms=0 if fault == 'deadline' else 1000,
                attempt_trace=AttemptTrace(),
            )
    assert error.value.rejection_reason == code
    assert 'PRIVATE' not in caplog.text and 'forged' not in caplog.text
    assert provider.calls == int(fault == 'settlement')
    row = store.rows[('users', 'u', 'proactivity_items', item['item_id'])]
    if fault in {'authority', 'denial'}:
        assert row['attempts'] == {} and row['reserved_micro_usd'] == 0
    elif fault == 'deadline':
        assert row['reserved_micro_usd'] == row['charged_micro_usd'] == 0
    else:
        assert row['reserved_micro_usd'] > 0  # Ambiguous settlement retains the hold.
