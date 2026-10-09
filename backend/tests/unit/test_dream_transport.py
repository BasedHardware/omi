"""Dream responses keep their bounded prefix before Pydantic validation."""

import asyncio
from copy import deepcopy
import json
from unittest.mock import AsyncMock

import httpx
import pytest
from pydantic import ValidationError

from models.dream_agent import Plan, Triage
from utils import dream_transport
from utils.llm.shaped_agent import Budget, Mount


@pytest.fixture
def transport(monkeypatch):
    client = type('Client', (), {'post': AsyncMock()})()
    monkeypatch.setattr(dream_transport, 'get_llm_gateway_client', lambda: client)
    monkeypatch.setattr(dream_transport, 'get_llm_gateway_base_url', lambda: 'https://synthetic.invalid')
    monkeypatch.setattr(dream_transport, 'llm_gateway_headers', lambda **k: {})
    monkeypatch.setattr(dream_transport, 'get_llm_gateway_semaphore', lambda: asyncio.Semaphore(1))

    def turn(model, response):
        client.post.return_value = httpx.Response(
            200,
            request=httpx.Request('POST', 'https://synthetic.invalid'),
            json={
                'usage': {'prompt_tokens': 30, 'completion_tokens': 20},
                'choices': [{'message': {'content': json.dumps(response)}}],
            },
        )
        sink = {'tokens': 0}
        result = asyncio.run(
            dream_transport.model_turn(
                'synthetic',
                dream_transport.MAIN_LANE,
                Mount(schema=model, budget=Budget(tokens=20000)),
                [],
                usage_sink=sink,
            )
        )
        assert result.tokens == sink['tokens'] == 50
        assert sink['usage_unknown'] is False
        assert (
            client.post.call_args.kwargs['json']['response_format']['json_schema']['schema']
            == model.model_json_schema()
        )
        return result.value

    return turn


def test_triage_caps_clusters_and_nested_refs_in_order(transport):
    clusters = [{'refs': [str(i) for i in range(21)], 'problem': 'spelling'} for _ in range(12)]
    value = transport(Triage, {'clusters': [*clusters, {'invalid': 'discarded tail'}]})
    assert len(value.clusters) == 12
    assert value.clusters[0].refs == [str(i) for i in range(20)]


def test_plan_caps_all_arrays_including_optional_referenced_models(transport):
    ref = 'conversations/synthetic'
    question = {
        'item_id': 'synthetic',
        'kind': 'speaker',
        'title': 'synthetic',
        'created_at': '2026-10-09T00:00:00Z',
        'speaker': {
            'prompt_id': 'synthetic',
            'conversation_id': 'synthetic',
            'conversation_title': 'synthetic',
            'start': 0,
            'end': 1,
            'affected_conversation_count': 1,
            'candidates': [{'person_id': str(i), 'name': str(i)} for i in range(4)],
            'context': [{'speaker_label': str(i), 'text': str(i), 'is_target': True} for i in range(4)],
        },
    }
    spelling = {
        'item_id': 'synthetic-spelling',
        'kind': 'spelling',
        'title': 'synthetic',
        'created_at': '2026-10-09T00:00:00Z',
        'spelling': {'term_id': 'synthetic', 'options': ['a', 'b', 'c', 'd'], 'allow_custom': True},
    }
    items = {
        'edits': {'kind': 'spelling', 'target': ref, 'reason': 'synthetic', 'evidence': [ref] * 11},
        'questions': question,
        'vocabulary': {'kind': 'jargon', 'spelling': 'synthetic', 'aliases': ['a'] * 6, 'evidence': [ref] * 11},
        'frames': {'screen_ref': ref, 'question': 'synthetic'},
        'feedback': {
            'component': 'dream',
            'failure_class': 'success',
            'severity': 'info',
            'count': 1,
            'latency_ms': 0,
            'error_rate': 0,
            'reproduction': 'synthetic',
        },
        'slow_tasks': {'description': 'synthetic', 'evidence': [ref] * 11},
    }
    bounds = {'edits': 50, 'questions': 3, 'vocabulary': 100, 'frames': 3, 'feedback': 10, 'slow_tasks': 3}
    response = {key: [deepcopy(item) for _ in range(bounds[key])] + [None] for key, item in items.items()}
    response['questions'][1] = spelling
    value = transport(Plan, response)
    assert {key: len(getattr(value, key)) for key in bounds} == bounds
    assert len(value.edits[0].evidence) == len(value.vocabulary[0].evidence) == len(value.slow_tasks[0].evidence) == 10
    assert len(value.vocabulary[0].aliases) == 5
    assert [item.person_id for item in value.questions[0].speaker.candidates] == ['0', '1', '2']
    assert len(value.questions[0].speaker.context) == 3
    assert value.questions[1].spelling.options == ['a', 'b', 'c']


@pytest.mark.parametrize(
    'model,response',
    [
        (Triage, {'clusters': [{'refs': [], 'problem': 'spelling'}]}),
        (Triage, {'clusters': 'invalid'}),
        (Plan, {'edits': [{'kind': 'spelling', 'target': 'synthetic', 'reason': '', 'evidence': ['synthetic']}]}),
        (Plan, {'unexpected': True}),
        (
            Plan,
            {
                'questions': [
                    {
                        'item_id': 'synthetic',
                        'kind': 'task',
                        'title': 'synthetic',
                        'created_at': '2026-10-09T00:00:00Z',
                        'spelling': {'term_id': 'synthetic', 'options': ['a', 'b'], 'allow_custom': True},
                    }
                ]
            },
        ),
    ],
)
def test_other_validation_failures_remain_errors(transport, model, response):
    with pytest.raises(ValidationError):
        transport(model, response)
