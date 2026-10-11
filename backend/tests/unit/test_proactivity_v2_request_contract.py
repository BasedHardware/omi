"""Producer requests cross the real gateway HTTP, validation and money boundaries."""

import json
from datetime import timedelta
from types import SimpleNamespace
from uuid import NAMESPACE_URL, uuid5

import httpx
import pytest

from config.proactivity_v2 import ProactivityDenied, producer_for
from database import proactivity as ledger
from database import proactivity_budget as money
from database.llm_gateway_accounting import ATTEMPTS_COLLECTION, record_llm_gateway_attempt
from llm_gateway.gateway import accounting_sink
from llm_gateway.gateway import proactivity_budget as budget
from llm_gateway.gateway.executor import ProviderRegistry
from llm_gateway.gateway.providers import OpenAICompatibleChatCompletionProvider
from llm_gateway.main import app
from llm_gateway.routers import dependencies
from tests.unit.test_proactivity_v2_budget import NOW, Redis, store
from tests.unit.test_proactivity_v2_producers import lane, mentor
from utils.llm import gateway_client
from utils import proactivity
from utils import proactivity_producers as producers
from utils.proactivity import claim_item, ensure_admitted, publish_item, run_proactivity_model


@pytest.fixture
async def wire(lane, store, monkeypatch):
    store.rows[('users', 'u', 'conversations', 'c')] = {'id': 'c'}
    monkeypatch.setattr(ledger, 'client_or_default', lambda client=None: client if client is not None else store)
    monkeypatch.setattr(ledger, 'utc_now', lambda: NOW)
    monkeypatch.setattr(proactivity, 'utc_now', lambda: NOW)
    monkeypatch.setattr(proactivity.proactivity_flags, 'enabled', lambda uid: True)
    monkeypatch.setenv('MENTOR_PIPELINE', 'cohort')
    monkeypatch.setattr(proactivity, 'ensure_admitted', ensure_admitted)
    monkeypatch.setattr(proactivity, 'claim_item', claim_item)
    monkeypatch.setattr(proactivity, 'publish_item', publish_item)
    monkeypatch.setattr(proactivity, 'run_proactivity_model', run_proactivity_model)
    authority = money.BudgetAuthority(firestore_client=store, redis_client=Redis(), clock=lambda: NOW)
    monkeypatch.setattr(money, 'BudgetAuthority', lambda: authority)
    events = []

    def persist(event, **kwargs):
        # StrictFirestore's narrow create fake raises RuntimeError for duplicates;
        # model the create-once store seam for the normal sink's repeated write.
        if (ATTEMPTS_COLLECTION, event['attempt_id']) in store.rows:
            return False
        created = record_llm_gateway_attempt(event, firestore_client=store)
        events.append(event)
        return created

    monkeypatch.setattr(money, 'record_llm_gateway_attempt', persist)
    monkeypatch.setattr(accounting_sink, 'record_llm_gateway_attempt', persist)
    monkeypatch.setenv('LLM_GATEWAY_ACCOUNTING_ENABLED', 'true')
    monkeypatch.setenv('OMI_LLM_GATEWAY_SERVICE_TOKEN', 'synthetic-service-token')
    monkeypatch.setenv('OPENROUTER_API_KEY', 'synthetic-provider-token')
    monkeypatch.setenv('OMI_LLM_GATEWAY_URL', 'http://gateway.test')
    calls = []
    fail_provider = []
    responses = []

    async def capture(response):
        await response.aread()
        responses.append((response.status_code, response.json()))

    async def transport(request):
        ctx = budget.current_attempt()
        row = store.rows[('users', 'u', ledger.ITEMS, ctx.item_id)]
        assert row['attempts'][ctx.call_id]['state'] == 'reserved'
        payload = json.loads(request.content)
        calls.append((ctx, payload))
        if fail_provider:
            return httpx.Response(503, json={'error': 'synthetic failure'})
        response = await lane.respond(item=row, step=ctx.step, request=payload)
        if request.url.path.endswith('chat/completions'):
            response.update(id='synthetic', object='chat.completion', model=payload['model'])
            response['choices'][0]['message']['role'] = 'assistant'
        response['usage'] = {'prompt_tokens': 10, 'completion_tokens': 0, 'total_tokens': 10}
        return httpx.Response(200, json=response)

    async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as upstream:
        provider = OpenAICompatibleChatCompletionProvider(base_url='http://provider.test/v1', http_client=upstream)
        app.dependency_overrides[dependencies.get_provider_registry] = lambda: ProviderRegistry(
            {'openai': provider, 'openrouter': provider}
        )
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), event_hooks={'response': [capture]}
        ) as client:
            monkeypatch.setattr(gateway_client, 'get_llm_gateway_client', lambda: client)
            try:
                yield SimpleNamespace(
                    lane=lane,
                    client=client,
                    calls=calls,
                    store=store,
                    responses=responses,
                    events=events,
                    fail_provider=fail_provider,
                )
            finally:
                await accounting_sink.drain_accounting_persistence_tasks()
                app.dependency_overrides.pop(dependencies.get_provider_registry, None)


@pytest.mark.asyncio
async def test_mentor_requests_reserve_and_settle(wire):
    assert await mentor(wire.lane), wire.responses
    assert [ctx.step for ctx, _ in wire.calls] == ['gate', 'generate', 'critic', 'usefulness', 'dedupe']
    row = wire.store.rows[('users', 'u', ledger.ITEMS, wire.calls[0][0].item_id)]
    assert len(row['attempts']) == 5
    assert all(attempt['state'] == 'settled' for attempt in row['attempts'].values())
    assert row['state'] == 'ready' and row['charged_micro_usd'] == sum(
        event['estimated_cost_micro_usd'] for event in wire.events
    )
    for ctx, payload in wire.calls:
        assert ctx.call_id == str(uuid5(NAMESPACE_URL, f'proactivity:{ctx.item_id}:{ctx.step}'))
        assert row['attempts'][ctx.call_id]['step'] == ctx.step
        attempt_id = row['attempts'][ctx.call_id]['attempt_id']
        receipt = wire.store.rows[(ATTEMPTS_COLLECTION, attempt_id)]
        assert receipt['request_id'] == ctx.call_id and receipt['feature'] == ctx.accounting.feature
        if 'messages' in payload:
            assert payload['stream'] is False
            assert payload['max_completion_tokens'] == 2048
            assert payload['response_format']['type'] == 'json_schema'
    assert all(
        event['route_artifact_id'] == 'route.proactive_notification.model_config.001'
        for event in wire.events
        if event['provider'] == 'openai'
    )


@pytest.mark.asyncio
@pytest.mark.parametrize('field', ['user_facts', 'past_conversations', 'conversation', 'goals', 'notifications'])
async def test_mentor_large_context_requests_reserve_and_settle(wire, field, monkeypatch):
    text = 'Synthetic 日本語 "quoted" \\ context.\n' * 2000
    messages = [{'text': 'Recent Call Alex', 'is_user': True, 'timestamp': 1}]
    if field == 'conversation':
        messages.insert(0, {'text': text, 'is_user': False, 'timestamp': 0})
    elif field == 'goals':
        wire.lane.context['goals'] = [{'title': text}]
    elif field == 'notifications':
        wire.lane.context['recent_notifications'] = [{'text': text}]
    else:
        wire.lane.context[field] = text
    monkeypatch.setattr(
        producers,
        'mentor_config',
        lambda: (wire.lane.config.model_copy(update={'prefilter_threshold': 0.5}), wire.lane.prompts),
    )
    monkeypatch.setattr(producers, 'mentor_delivery_history', lambda uid: [text, 'Recent advice'])
    assert await producers.produce_mentor('u', 'c', messages, wire.lane.context), wire.responses
    assert [ctx.step for ctx, _ in wire.calls] == ['prefilter', 'gate', 'generate', 'critic', 'usefulness', 'dedupe']
    for ctx, payload in wire.calls:
        assert (
            len(json.dumps(payload, separators=(',', ':'), ensure_ascii=False).encode())
            <= producer_for(ctx.producer).max_request_bytes
        )
        row = wire.store.rows[('users', 'u', ledger.ITEMS, ctx.item_id)]
        assert row['attempts'][ctx.call_id]['state'] == 'settled'
    assert len(wire.events) == 6
    if field == 'conversation':
        assert all('Recent Call Alex' in p['messages'][0]['content'] for _, p in wire.calls if 'messages' in p)


@pytest.mark.asyncio
async def test_followup_unicode_description_reserves_and_settles(wire, monkeypatch):
    due = NOW - timedelta(minutes=1)
    task = {'conversation_id': 'c', 'due_at': due, 'completed': False, 'description': '日本語😀' * 600}
    wire.store.rows[('users', 'u', 'action_items', 'a')] = task
    monkeypatch.setattr(producers.tasks, 'get_action_item', lambda *args: task)
    await producers.produce_followup('u', 'a', due.isoformat())
    assert len(wire.calls) == 1, wire.responses
    ctx, payload = wire.calls[0]
    assert ctx.step == 'phrase' and payload['stream'] is False and payload['max_completion_tokens'] == 512
    assert (
        len(json.dumps(payload, separators=(',', ':'), ensure_ascii=False).encode())
        <= producer_for(ctx.producer).max_request_bytes
    )
    row = wire.store.rows[('users', 'u', ledger.ITEMS, ctx.item_id)]
    assert row['state'] == 'ready' and row['attempts'][ctx.call_id]['state'] == 'settled'


@pytest.mark.asyncio
async def test_provider_failure_keeps_one_reservation_without_retry(wire):
    wire.fail_provider.append(True)
    assert await mentor(wire.lane) is None
    assert len(wire.calls) == len(wire.events) == 1
    ctx, _ = wire.calls[0]
    row = wire.store.rows[('users', 'u', ledger.ITEMS, ctx.item_id)]
    assert row['cost_status'] == 'indeterminate'
    assert row['charged_micro_usd'] == row['reserved_micro_usd'] > 0
    assert row['attempts'][ctx.call_id]['state'] == 'unknown'


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'fault,reason', [('context', 'input_bound'), ('output', 'invalid_output_bound'), ('stream', None)]
)
async def test_invalid_wire_fails_closed_before_reservation(wire, fault, reason, caplog):
    item = await claim_item(
        uid='u',
        producer='conversation_mentor_v2',
        source={'source_kind': 'conversation', 'source_id': 'c', 'source_revision': '1', 'source_event_id': 'eligible'},
    )
    # The previous producer sent the full rendered gate without a byte bound.
    fields = dict(wire.lane.context, goals_text='No goals', current_conversation='Call Alex', recent_notifications='')
    if fault == 'context':
        fields['user_facts'] = 'Synthetic remembered detail. ' * 2000
    request = {
        'messages': [{'role': 'user', 'content': wire.lane.prompts['gate'].format(**fields)}],
        'reasoning_effort': 'low',
        'max_completion_tokens': 2048,
        'response_format': {
            'type': 'json_schema',
            'json_schema': {'name': 'RelevanceResult', 'schema': producers.legacy.RelevanceResult.model_json_schema()},
        },
    }
    if fault == 'output':
        request.pop('max_completion_tokens')
    elif fault == 'stream':
        request['stream'] = True
    with pytest.raises((ProactivityDenied, httpx.HTTPStatusError)):
        await run_proactivity_model(item=item, step='gate', request=request)
    assert wire.responses[-1][0] == 400
    if reason:
        assert wire.responses[-1][1]['error']['message'] == f'proactivity admission denied: {reason}'
    else:
        assert wire.responses[-1][1]['error']['message'] == 'proactivity requires a nonstreaming exclusive budget'
    row = wire.store.rows[('users', 'u', ledger.ITEMS, item['item_id'])]
    assert row['attempts'] == {} and row['reserved_micro_usd'] == row['charged_micro_usd'] == 0
    assert not wire.calls and not wire.events
    code = f'proactivity_admission.{reason}' if reason else 'proactivity_streaming'
    assert f'rejection_reason={code}' in caplog.text


@pytest.mark.parametrize(
    'field', ['current_conversation', 'goals_text', 'user_facts', 'past_conversations', 'recent_notifications']
)
def test_context_trims_whole_items_in_priority_order(field):
    item = {'producer': 'conversation_mentor_v2'}
    limit = producer_for(item['producer']).max_request_bytes
    entries = [f'BEGIN_{i} ' + 'x' * (limit // 3) + f' END_{i}' for i in range(4)]
    fields = {field: producers.ContextItems(entries, lambda items: '\n'.join(items))}

    def request(data):
        return {'messages': [{'role': 'user', 'content': producers._render_fields(data)[field]}]}

    first = producers._fit_context(item, request, fields, (field,))
    assert first == producers._fit_context(item, request, fields, (field,))
    text = first['messages'][0]['content']
    expected = entries[-2:] if field == 'current_conversation' else entries[:2]
    assert text == '\n'.join(expected)
    assert fields[field].values == entries  # No caller mutation across steps.


@pytest.mark.parametrize('field', ['current_conversation', 'goals_text', 'recent_conversation', 'user_goals'])
def test_single_oversized_item_retains_text_with_marker(field):
    item = {'producer': 'conversation_mentor_v2'}
    limit = producer_for(item['producer']).max_request_bytes
    oversized = {'text': 'START ' + '日本語😀"\\\n' * limit + ' NEWEST END', 'is_user': True}
    values = [oversized]
    fields = {
        field: values if field in {'recent_conversation', 'user_goals'} else producers.ContextItems(values, json.dumps)
    }

    def request(data):
        return {'state': json.dumps(producers._render_fields(data), ensure_ascii=False), 'questions': {}}

    fitted = producers._fit_context(item, request, fields, (field,), jev=True)
    assert (
        len(json.dumps(dict(fitted, model=producers.JEV_MODEL), separators=(',', ':'), ensure_ascii=False).encode())
        <= limit
    )
    assert '[Context truncated]' in fitted['state']
    assert ('NEWEST END' if field in {'current_conversation', 'recent_conversation'} else 'START') in fitted['state']
    assert oversized['text'].startswith('START') and '[Context truncated]' not in oversized['text']


def test_multiline_facts_keep_continuations_with_whole_fact():
    text = 'Known facts:\n- Highest priority\nwith a continuation\n- Lower priority\n'
    entries = producers._fact_items(text)
    assert entries.render(entries.values) == text
    assert entries.values[0] == 'Known facts:\n- Highest priority\nwith a continuation\n'


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'header,value,code',
    [
        ('x-omi-proactivity-call', None, 'proactivity_identity'),
        ('x-omi-proactivity-call', 'PRIVATE_SECRET_CALL', 'proactivity_identity'),
        ('x-omi-proactivity-item', 'PRIVATE_USER_CONTENT', 'proactivity_item'),
        ('x-omi-llm-feature', 'proactivity_v2_wrong', 'proactivity_attribution'),
        ('x-omi-proactivity-step', 'PRIVATE_SECRET_STEP', 'proactivity_attribution'),
    ],
)
async def test_producer_identity_rejection_terminal_has_safe_reason_and_no_spend(wire, header, value, code, caplog):
    async def corrupt(request):
        if value is None:
            request.headers.pop(header)
        else:
            request.headers[header] = value

    wire.client.event_hooks['request'].append(corrupt)
    assert await mentor(wire.lane) is None
    assert wire.responses[-1][0] == 400
    assert not wire.calls and not wire.events
    assert f'rejection_reason={code}' in caplog.text
    assert 'PRIVATE' not in caplog.text
    rows = [row for key, row in wire.store.rows.items() if len(key) == 4 and key[2] == ledger.ITEMS]
    assert len(rows) == 1
    assert rows[0]['attempts'] == {} and rows[0]['reserved_micro_usd'] == 0


@pytest.mark.asyncio
async def test_validator_rejection_has_safe_parameter_without_reservation(wire, caplog):
    item = await claim_item(
        uid='u',
        producer='conversation_mentor_v2',
        source={'source_kind': 'conversation', 'source_id': 'c', 'source_revision': '1', 'source_event_id': 'eligible'},
    )
    with pytest.raises(httpx.HTTPStatusError):
        await run_proactivity_model(
            item=item,
            step='gate',
            request={'messages': [{'role': 'user'}], 'max_completion_tokens': 2048},
        )
    assert wire.responses[-1][0] == 400
    assert 'rejection_reason=parameter_messages' in caplog.text
    assert not wire.calls and not wire.events
    assert wire.store.rows[('users', 'u', ledger.ITEMS, item['item_id'])]['attempts'] == {}


@pytest.mark.asyncio
@pytest.mark.parametrize('field', ['conversation', 'goals', 'user_facts', 'past_conversations', 'notifications'])
async def test_real_producer_preserves_whole_context_items_through_gateway(wire, field):
    limit = producer_for('conversation_mentor_v2').max_request_bytes
    entries = [f'BEGIN_{i} ' + 'x' * (limit // 4) + f' END_{i}' for i in range(4)]
    messages = [{'text': 'Recent decision', 'is_user': True}]
    if field == 'conversation':
        messages = [{'text': text, 'is_user': True} for text in entries]
    elif field == 'goals':
        wire.lane.context['goals'] = [{'title': text} for text in entries]
    elif field == 'notifications':
        wire.lane.context['recent_notifications'] = [{'text': text} for text in entries]
    elif field == 'user_facts':
        wire.lane.context[field] = '\n'.join('- ' + text for text in entries)
    else:
        wire.lane.context[field] = entries
    assert await producers.produce_mentor('u', 'c', messages, wire.lane.context), wire.responses
    for ctx, payload in wire.calls:
        prompt = payload['messages'][0]['content'] if 'messages' in payload else payload['state']
        for i, text in enumerate(entries):
            if f'BEGIN_{i}' in prompt or f'END_{i}' in prompt:
                assert text in prompt  # A retained entry is complete, never a fragment.
        prompt_field = {
            'conversation': 'current_conversation',
            'goals': 'goals_text',
            'notifications': 'recent_notifications',
        }.get(field, field)
        if 'messages' in payload and '{' + prompt_field + '}' in wire.lane.prompts[ctx.step]:
            if field == 'conversation':
                assert entries[-1] in prompt and entries[0] not in prompt
            else:
                assert entries[0] in prompt and entries[-1] not in prompt
            assert '[Context truncated]' not in prompt
        assert wire.store.rows[('users', 'u', ledger.ITEMS, ctx.item_id)]['attempts'][ctx.call_id]['state'] == 'settled'
