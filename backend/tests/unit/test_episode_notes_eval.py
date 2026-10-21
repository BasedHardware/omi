import json

import pytest

from testing.episode_notes.eval import CompatibleEndpoint
from testing.episode_notes.prompts import CANDIDATE_PROMPT
from testing.episode_notes.runner import JUDGE_PROMPT, REFERENCE_PROMPT, evaluate
from testing.episode_notes.schema import LLMResult, load_fixtures

from utils.conversations.episode_vacuity import is_vacuous_note


def test_fixture_schema_and_sealed_split():
    fixtures = load_fixtures()
    assert len(fixtures.episodes) >= 14
    assert len({case.stratum for case in fixtures.episodes}) == len(fixtures.episodes)
    fraction = sum(case.split == 'held_out' for case in fixtures.episodes) / len(fixtures.episodes)
    assert 0.25 <= fraction <= 0.35
    assert all(case.expected.must_cover for case in fixtures.episodes)


def test_fake_llm_reports_per_stratum_and_does_not_leak_expectations():
    calls = []

    def fake(prompt, payload):
        calls.append((prompt, payload))
        if prompt == CANDIDATE_PROMPT:
            assert 'expected' not in payload
            return LLMResult(
                content={'title': 'Quick chat', 'overview': 'A brief exchange'},
                input_tokens=120,
                output_tokens=45,
                latency_seconds=0.25,
            )
        if prompt == REFERENCE_PROMPT:
            assert 'expected' not in payload
            return {'narrative': 'All available evidence was considered', 'claims': []}
        assert prompt == JUDGE_PROMPT
        assert {'evidence', 'reference', 'candidate', 'expected'} == set(payload)
        return {
            'informativeness_gap': 0.8,
            'unsupported_claims': 1,
            'wrong_provenance_claims': 2,
            'unrelated_content_claims': 3,
            'vacuous': True,
            'property_failures': ['missing detail'],
            'reasons': ['synthetic fake score'],
        }

    report = evaluate(load_fixtures(), fake)
    assert len(calls) == 33
    assert len(report['cases']) == 11
    assert all(row['deterministic_vacuity'] and not row['faithfulness_pass'] for row in report['cases'])
    assert all(group['wrong_provenance_claims'] == 2 for group in report['arms']['episode']['strata'].values())
    assert all(group['unrelated_content_claims'] == 3 for group in report['arms']['episode']['strata'].values())
    assert report['arms']['episode']['overall']['unrelated_content_claims'] == 33
    assert 'sensitive_tagging_misses' not in report['arms']['episode']['overall']
    assert json.loads(json.dumps(report)) == report
    assert len(report['arms']['episode']['prompt_sha256']) == 64
    assert all(
        row['candidate_cost']
        == {
            'input_tokens': 120,
            'output_tokens': 45,
            'latency_seconds': 0.25,
            'cached_tokens': None,
            'claim_tokens': None,
            'reasoning_tokens': None,
            'provider_cost': None,
        }
        for row in report['cases']
    )


def test_endpoint_requires_explicit_opt_in_and_rejects_production():
    with pytest.raises(ValueError, match='explicit'):
        CompatibleEndpoint(key='', base_url='https://openrouter.ai/api/v1', model='fake')
    with pytest.raises(ValueError, match='disallowed'):
        CompatibleEndpoint(key='fake', base_url='https://api.omi.me', model='fake')


@pytest.mark.parametrize(
    'note,expected',
    [
        ({'title': 'Quick chat', 'overview': 'No clear topic'}, True),
        ({'title': 'Capture', 'overview': 'A brief exchange; no clear topic or concrete decision is captured.'}, True),
        ({'title': 'Agenda', 'overview': 'Ari said the meeting had no clear topic and asked for an agenda'}, False),
        ({'title': 'Quick chat with Ana about pricing', 'overview': 'Ana said pricing rose.'}, False),
        ({'title': 'Topic', 'overview': 'The slide was titled "No clear topic".'}, False),
        (
            {'title': 'Capture', 'overview': 'Nothing was captured. Audio stopped after Ari introduced the budget.'},
            False,
        ),
        ({'title': 'Empty capture', 'overview': 'Audio captured only you; no other speaker was recorded.'}, False),
        ({'title': 'Budget', 'overview': 'The budget was approved at 5 percent.'}, False),
        ({'title': 'Title without content'}, True),
        ({'title': 'Capture', 'overview': 'Details', 'sections': [{'body_markdown': '- Nothing was captured'}]}, True),
    ],
)
def test_deterministic_vacuity(note, expected):
    assert is_vacuous_note(note) is expected


def test_endpoint_reports_provider_usage_and_candidate_latency(monkeypatch):
    import io
    from testing.episode_notes import eval as module

    response = {
        'choices': [{'message': {'content': '{"title": "Synthetic"}'}}],
        'usage': {'prompt_tokens': 321, 'completion_tokens': 123},
    }
    requests = []

    def respond(request, **kwargs):
        requests.append(json.loads(request.data))
        return io.StringIO(json.dumps(response))

    monkeypatch.setattr(module, 'urlopen', respond)
    ticks = iter([10.0, 10.75, 20.0, 21.0])
    monkeypatch.setattr(module, 'perf_counter', lambda: next(ticks))
    endpoint = CompatibleEndpoint(key='fake', base_url='https://example.com/v1', model='fake')
    result = endpoint('prompt', {})
    assert result.content == {'title': 'Synthetic'}
    assert result.cost() == {
        'input_tokens': 321,
        'output_tokens': 123,
        'latency_seconds': 0.75,
        'cached_tokens': None,
        'claim_tokens': None,
        'reasoning_tokens': None,
        'provider_cost': None,
    }
    del response['usage']
    assert endpoint('prompt', {}).cost() == {
        'input_tokens': None,
        'output_tokens': None,
        'latency_seconds': 1.0,
        'cached_tokens': None,
        'claim_tokens': None,
        'reasoning_tokens': None,
        'provider_cost': None,
    }

    assert all(
        'reasoning_effort' not in request and 'reasoning' not in request and 'temperature' not in request
        for request in requests
    )


@pytest.fixture
def cost_encoder():
    import tiktoken

    return tiktoken.encoding_for_model('gpt-4o')


def test_endpoint_measures_cache_read_and_compact_claim_share(monkeypatch, cost_encoder):
    import io
    from testing.episode_notes import eval as module

    claims = [{'t': 'Approved price', 'p': '/title', 'e': ['evidence:0'], 'v': 'inferred'}]
    packet = {
        'choices': [{'finish_reason': 'stop', 'message': {'content': json.dumps({'note_claims': claims})}}],
        'usage': {'prompt_tokens': 100, 'completion_tokens': 60, 'prompt_tokens_details': {'cached_tokens': 80}},
    }
    monkeypatch.setattr(module, 'urlopen', lambda *a, **k: io.StringIO(json.dumps(packet)))
    receipt = CompatibleEndpoint(key='fake', base_url='https://example.com/v1', model='fake')('prompt', {})
    assert receipt.cached_tokens == 80
    assert receipt.claim_tokens == len(
        cost_encoder.encode(json.dumps(claims, ensure_ascii=False, separators=(',', ':')))
    )
    assert receipt.output_tokens == 60 and receipt.finish_reason == 'stop'
