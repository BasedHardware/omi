import json

import pytest

from testing.episode_notes.eval import (
    CANDIDATE_PROMPT,
    JUDGE_PROMPT,
    REFERENCE_PROMPT,
    CompatibleEndpoint,
    evaluate,
    load_fixtures,
)
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
            return {'title': 'Quick chat', 'overview': 'A brief exchange'}
        if prompt == REFERENCE_PROMPT:
            assert 'expected' not in payload
            return {'narrative': 'All available evidence was considered', 'claims': []}
        assert prompt == JUDGE_PROMPT
        assert {'evidence', 'reference', 'candidate', 'expected'} == set(payload)
        return {
            'informativeness_gap': 0.8,
            'unsupported_claims': 1,
            'wrong_provenance_claims': 2,
            'sensitive_tagging_misses': 3,
            'vacuous': True,
            'property_failures': ['missing detail'],
            'reasons': ['synthetic fake score'],
        }

    report = evaluate(load_fixtures(), fake)
    assert len(calls) == 33
    assert len(report['cases']) == 11
    assert all(row['deterministic_vacuity'] and not row['faithfulness_pass'] for row in report['cases'])
    assert all(group['wrong_provenance_claims'] == 2 for group in report['strata'].values())
    assert json.loads(json.dumps(report)) == report
    assert len(report['prompt_sha256']) == 64


def test_endpoint_requires_explicit_opt_in_and_rejects_production():
    with pytest.raises(ValueError, match='explicit'):
        CompatibleEndpoint(key='', base_url='https://openrouter.ai/api/v1', model='fake')
    with pytest.raises(ValueError, match='disallowed'):
        CompatibleEndpoint(key='fake', base_url='https://api.omi.me', model='fake')


@pytest.mark.parametrize(
    'note,expected',
    [
        ({'title': 'Quick chat', 'overview': 'No clear topic'}, True),
        ({'title': 'Empty capture', 'overview': 'Audio captured only you; no other speaker was recorded.'}, False),
        ({'title': 'Budget', 'overview': 'The budget was approved at 5 percent.'}, False),
        ({'title': 'Title without content'}, True),
        ({'title': 'Capture', 'overview': 'Details', 'sections': [{'body_markdown': '- Nothing was captured'}]}, True),
    ],
)
def test_deterministic_vacuity(note, expected):
    assert is_vacuous_note(note) is expected
