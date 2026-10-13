"""Synthetic rung 1.1 output contracts, including the actual gateway/Vertex wire."""

import asyncio
import json
from unittest.mock import AsyncMock

import httpx
import pytest
from pydantic import ValidationError

from config.dream_agent import Caps, FULL_CONTEXT_WINDOW
from models.dream_agent import DreamReviewItem, Edit, Plan
from utils import dream_agent, dream_guards, dream_metrics, dream_prompt, dream_transport, dream_tools
from utils.dream_context import EvidenceRecords

UID = 'synthetic-full-output-owner'
REF = 'memory_items/synthetic'


@pytest.fixture
def full(monkeypatch):
    monkeypatch.setenv('DREAM_AGENT_CONTEXT_MODE', 'full')
    monkeypatch.setenv('DREAM_AGENT_FULL_CONTEXT_UIDS', UID)
    return Caps().for_uid(UID)


def spelling(before='Borza', after='Borzah', **kwargs):
    return Edit(
        kind='spelling', target=REF, before=before, after=after, reason='Synthetic correction', evidence=[REF], **kwargs
    )


def question(**kwargs):
    return DreamReviewItem.model_validate(
        {
            'item_id': 'spelling:synthetic',
            'kind': 'spelling',
            'title': 'Which project name?',
            'created_at': '2026-10-13T00:00:00Z',
            'source_ref': REF,
            'quote': 'Borza',
            'spelling': {'term_id': 'synthetic', 'options': ['Borza', 'Borzah'], 'allow_custom': True},
            **kwargs,
        }
    )


def test_self_describing_schema_reaches_the_request():
    schema = Plan.model_json_schema()
    fields = schema['$defs']['Edit']['properties']
    assert 'Exact wrong text' in fields['before']['description']
    assert 'corrected text' in fields['after']['description']
    assert 'Only the second' in fields['other']['description']
    assert 'every occurrence' in fields['target']['description']
    q = schema['$defs']['DreamReviewItem']
    assert {'source_ref', 'quote'} <= set(q['required'])
    assert 'attention' in q['properties']['quote']['description']


@pytest.mark.parametrize('kind', ['spelling', 'title', 'overview'])
def test_empty_replacement_is_schema_failure_with_its_own_guard_count(kind):
    payload = {
        'kind': kind,
        'target': 'conversations/synthetic',
        'before': 'Borza',
        'after': '',
        'reason': 'Synthetic',
        'evidence': ['conversations/synthetic'],
    }
    with pytest.raises(ValidationError):
        Edit.model_validate(payload)
    sink = {}
    assert dream_transport.parse_response(Plan, {'edits': [payload]}, usage_sink=sink) == Plan()
    assert sink['rejected'] == {'invalid_edit': 1}
    assert sink['dropped_invalid']['edits'] == 1


def test_non_merge_other_is_schema_failure_and_merges_remain_allowed():
    with pytest.raises(ValidationError):
        spelling(other='memory_items/second')
    assert Edit(
        kind='merge_memories',
        target=REF,
        other='memory_items/second',
        after='Merged fact',
        reason='Duplicate',
        evidence=[REF],
    ).other


def test_deduplicate_noop_and_reciprocal_spelling_before_caps():
    records = EvidenceRecords({REF: {'content': 'Borza Borza NAME name word toy'}}, targets=[REF])
    records.context_mode = 'full'
    edits = [spelling() for _ in range(8)] + [
        spelling('word', 'word'),
        spelling('NAME', 'name'),
        spelling('name', 'NAME'),
        spelling('toy', 'Toy'),
    ]
    sink = {}
    result = dream_guards.filter_plan(Plan(edits=edits), records, usage_sink=sink)
    assert [(e.before, e.after) for e in result.edits] == [('Borza', 'Borzah'), ('toy', 'Toy')]
    assert sink['rejected'] == {'duplicate_edit': 7, 'noop': 1, 'contradictory_spelling': 2}
    assert len(edits) == 12
    dream_guards.filter_plan(result, records, usage_sink=sink)
    assert sink['rejected'] == {'duplicate_edit': 7, 'noop': 1, 'contradictory_spelling': 2}


@pytest.mark.parametrize(
    'updates',
    [
        {'source_ref': 'memory_items/unknown'},
        {'quote': 'borza'},
        {'quote': 'Borza\nBorzah'},
        {'quote': 'Invented question'},
    ],
)
def test_questions_require_verbatim_quote_in_one_supplied_field(updates):
    sink = {}
    records = {REF: {'content': 'Borza', 'nested': {'name': 'Borzah'}}}
    assert not dream_guards.filter_plan(Plan(questions=[question(**updates)]), records, usage_sink=sink).questions
    assert sink['rejected'] == {'invalid_question_evidence': 1}
    assert dream_guards.filter_plan(Plan(questions=[question()]), records).questions


@pytest.mark.parametrize('field', ['source_ref', 'quote'])
def test_missing_question_evidence_is_rejected_at_schema_boundary(field):
    payload = question().model_dump(mode='json')
    payload.pop(field)
    sink = {}
    assert dream_transport.parse_response(Plan, {'questions': [payload]}, usage_sink=sink) == Plan()
    assert sink['rejected'] == {'invalid_question_evidence': 1}


def response(content, finish='stop'):
    return httpx.Response(
        200,
        request=httpx.Request('POST', 'https://synthetic.invalid'),
        json={
            'usage': {'prompt_tokens': 30, 'completion_tokens': 20},
            'choices': [{'finish_reason': finish, 'message': {'content': content}}],
        },
    )


@pytest.fixture
def client(monkeypatch):
    client = type('Client', (), {'post': AsyncMock()})()
    monkeypatch.setattr(dream_transport, 'get_llm_gateway_client', lambda: client)
    monkeypatch.setattr(dream_transport, 'get_llm_gateway_base_url', lambda: 'https://synthetic.invalid')
    monkeypatch.setattr(dream_transport, 'llm_gateway_headers', lambda **kwargs: {})
    monkeypatch.setattr(dream_transport, 'get_llm_gateway_semaphore', lambda: asyncio.Semaphore(1))
    monkeypatch.setattr(dream_transport.dream_capacity, 'available_model', AsyncMock(return_value='gemini-2.5-flash'))
    return client


@pytest.mark.asyncio
@pytest.mark.parametrize('first', [response('{"edits":[{"reason":"unterminated'), response('{}', 'length')])
async def test_full_response_retries_once_with_accounted_usage_and_same_context(full, client, first, caplog):
    client.post.side_effect = [first, response('{}')]
    sink = {'tokens': 0}
    plan, tokens = await dream_agent.plan_pass(UID, {REF: {'content': 'Synthetic text'}}, full, usage_sink=sink)
    assert plan == Plan() and tokens == sink['tokens'] == 100
    assert sink['response_retries'] == 1 and sink['usage_unknown'] is False
    assert client.post.await_count == 2
    requests = [call.kwargs['json'] for call in client.post.call_args_list]
    assert requests[0] == requests[1]
    assert requests[0]['max_completion_tokens'] == 32768
    assert requests[0]['google']['thinking_config']['thinking_budget'] == 16384
    assert requests[0]['reasoning_effort'] == 'high'
    assert (
        dream_transport.input_ceiling(requests[0]['messages'], Plan.model_json_schema()) + 32768 <= FULL_CONTEXT_WINDOW
    )
    assert full.reservation_usd == 2 * full.tokens * full.max_usd_per_token
    before = dream_metrics.RESPONSE_RETRIES._value.get()
    with caplog.at_level('INFO', logger='utils.dream_metrics'):
        dream_metrics.record_pass({'status': 'complete', **sink})
    assert dream_metrics.RESPONSE_RETRIES._value.get() == before + 1
    assert 'response_retries=1' in caplog.text and 'unterminated' not in caplog.text


@pytest.mark.asyncio
async def test_second_invalid_response_fails_without_third_attempt(full, client):
    client.post.side_effect = [response('not json'), response('not json')]
    sink = {'tokens': 0}
    with pytest.raises(dream_transport.InvalidModelResponse):
        await dream_agent.plan_pass(UID, {}, full, usage_sink=sink)
    assert client.post.await_count == 2 and sink['tokens'] == 100 and sink['response_retries'] == 1
    assert sink['usage_unknown'] is False


@pytest.mark.asyncio
async def test_bounded_keeps_one_attempt_and_no_thinking_override(client):
    client.post.side_effect = [response('not json'), response('{}')]
    sink = {'tokens': 0}
    with pytest.raises(dream_transport.InvalidModelResponse):
        await dream_transport.model_turn(
            'bounded', dream_transport.MAIN_LANE, dream_prompt.mount(Plan, 24000), [], usage_sink=sink
        )
    assert client.post.await_count == 1 and sink.get('response_retries', 0) == 0
    payload = client.post.call_args.kwargs['json']
    assert payload['max_completion_tokens'] == 4096
    assert 'reasoning_effort' not in payload and 'google' not in payload


def test_two_missing_question_fields_count_one_rejected_question():
    payload = question().model_dump(mode='json')
    payload.pop('source_ref')
    payload.pop('quote')
    sink = {}
    assert dream_transport.parse_response(Plan, {'questions': [payload]}, usage_sink=sink) == Plan()
    assert sink['rejected'] == {'invalid_question_evidence': 1}


@pytest.mark.asyncio
async def test_valid_json_with_invalid_items_is_not_retried(full, client):
    client.post.return_value = response(
        json.dumps(
            {
                'edits': [
                    {
                        'kind': 'spelling',
                        'target': REF,
                        'before': 'Borza',
                        'after': '',
                        'reason': 'Synthetic',
                        'evidence': [REF],
                    }
                ]
            }
        )
    )
    sink = {'tokens': 0}
    plan, tokens = await dream_agent.plan_pass(UID, {REF: {'content': 'Borza'}}, full, usage_sink=sink)
    assert plan == Plan() and tokens == 50 and client.post.await_count == 1
    assert sink.get('response_retries', 0) == 0 and sink['rejected'] == {'invalid_edit': 1}


def test_question_effect_backstop_rejects_invented_quote(monkeypatch):
    monkeypatch.setattr(
        dream_tools.review_store,
        'enqueue_review_proposal',
        lambda *args, **kwargs: pytest.fail('invented evidence reached Review'),
    )
    with pytest.raises(ValueError, match='dream_invalid_question_evidence'):
        dream_tools.ask(UID, question(quote='invented'), {REF: {'content': 'Borza'}})
