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

    def turn(model, response, *, sink=None):
        client.post.return_value = httpx.Response(
            200,
            request=httpx.Request('POST', 'https://synthetic.invalid'),
            json={
                'usage': {'prompt_tokens': 30, 'completion_tokens': 20},
                'choices': [{'message': {'content': json.dumps(response)}}],
            },
        )
        sink = {'tokens': 0} if sink is None else sink
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


@pytest.mark.parametrize('response', [None, [], 'invalid', {'edits': {}}, {'questions': None}, {'unexpected': True}])
def test_top_level_shape_failures_remain_errors(transport, response):
    with pytest.raises(ValidationError):
        transport(Plan, response)


def test_invalid_cluster_does_not_discard_valid_cluster(transport):
    sink = {'tokens': 0}
    valid = {'refs': ['conversations/synthetic'], 'problem': 'spelling'}
    value = transport(Triage, {'clusters': [{'refs': [], 'problem': 'spelling'}, valid]}, sink=sink)
    assert value == Triage(clusters=[valid])
    assert sink['dropped_invalid'] == {'clusters': 1}
    assert sink['validation_errors'] == {'clusters.refs:too_short': 1}


def test_mixed_plan_retains_valid_items_in_every_list(transport):
    ref = 'conversations/synthetic'
    question = {
        'item_id': 'invented',
        'kind': 'spelling',
        'title': 'Invented spelling',
        'created_at': '2026-10-09T00:00:00Z',
        'spelling': {'term_id': 'invented', 'options': ['a', 'b'], 'allow_custom': True},
    }
    valid = {
        'edits': {'kind': 'spelling', 'target': ref, 'reason': 'Invented typo', 'evidence': [ref]},
        'questions': question,
        'vocabulary': {'kind': 'jargon', 'spelling': 'Invented', 'evidence': [ref]},
        'frames': {'screen_ref': ref, 'question': 'Invented question'},
        'feedback': {
            'component': 'dream',
            'failure_class': 'success',
            'severity': 'info',
            'count': 1,
            'latency_ms': 0,
            'error_rate': 0,
            'reproduction': 'Invented robot fixture',
        },
        'slow_tasks': {'description': 'Invented followup', 'evidence': [ref]},
    }
    invalid = deepcopy(valid)
    invalid['edits']['evidence'] = []
    invalid['questions']['spelling']['options'] = ['a']
    invalid['vocabulary']['spelling'] = ''
    invalid['frames']['question'] = ''
    invalid['feedback']['count'] = 0
    invalid['slow_tasks']['description'] = ''
    response = {key: [invalid[key], item] for key, item in valid.items()}
    response['edits'].insert(1, {**valid['edits'], 'reason': ''})
    sink = {'tokens': 0}
    value = transport(Plan, response, sink=sink)
    assert value == Plan.model_validate({key: [item] for key, item in valid.items()})
    assert sink['dropped_invalid'] == {key: 2 if key == 'edits' else 1 for key in valid}
    assert sink['validation_errors'] == {
        'edits.evidence:too_short': 1,
        'edits.reason:string_too_short': 1,
        'questions.spelling.options:too_short': 1,
        'vocabulary.spelling:string_too_short': 1,
        'frames.question:string_too_short': 1,
        'feedback.count:greater_than_equal': 1,
        'slow_tasks.description:string_too_short': 1,
    }


def test_matching_payload_validator_still_drops_question(transport):
    question = {
        'item_id': 'invented',
        'kind': 'task',
        'title': 'Invented',
        'created_at': '2026-10-09T00:00:00Z',
        'spelling': {'term_id': 'invented', 'options': ['a', 'b'], 'allow_custom': True},
    }
    sink = {'tokens': 0}
    assert transport(Plan, {'questions': [question]}, sink=sink) == Plan()
    assert sink['validation_errors'] == {'questions:value_error': 1}


def test_validation_diagnostics_never_include_unknown_keys_or_values(transport, caplog):
    from utils.dream_metrics import record_pass

    sink = {'tokens': 0}
    secret = 'invented PRIVATE text including spaces'
    edit = {'kind': 'spelling', 'target': secret, 'reason': '', 'evidence': [secret], secret: secret}
    assert transport(Plan, {'edits': [edit]}, sink=sink) == Plan()
    assert sink['validation_errors'] == {'edits.reason:string_too_short': 1, 'edits.unknown_field:extra_forbidden': 1}
    with caplog.at_level('INFO', logger='utils.dream_metrics'):
        record_pass({'status': 'complete', **sink})
    assert secret not in str(sink) and secret not in caplog.text
    assert 'dropped_invalid=' in caplog.text and 'edits.reason:string_too_short' in caplog.text
