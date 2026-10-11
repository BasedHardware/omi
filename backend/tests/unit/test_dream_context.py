"""Synthetic contract regressions; no provider or customer reads."""

import json

import pytest

from models.dream_agent import Triage
from utils import dream_guards, dream_prompt


@pytest.mark.parametrize(
    'row,expected',
    [
        ({'structured': {'title': 'Existing title'}}, {'title': 'nonempty_field', 'overview': 'insufficient_speech'}),
        ({'user_title': 'My title'}, {'title': 'nonempty_field', 'overview': 'insufficient_speech'}),
        ({'structured': {'sections': [{}]}}, {'title': 'insufficient_speech', 'overview': 'nonempty_field'}),
        ({}, {'title': 'insufficient_speech', 'overview': 'insufficient_speech'}),
        ({'transcript_segments': [{'text': 'solar boat ' * 20}]}, {'title': 'editable', 'overview': 'editable'}),
    ],
)
def test_eligibility_survives_projection_and_uses_guard_primitive(row, expected):
    records = {'conversations/synthetic': row}
    payload = json.loads(dream_prompt.evidence_message(records, Triage, 12000)[0]['content'])
    assert payload['summary_eligibility']['conversations/synthetic'] == expected
    assert dream_guards.summary_eligibility(row) == expected


def test_full_speech_eligibility_is_computed_before_excerpt_truncation():
    row = {'transcript_segments': [{'text': 'solar boat ' * 2000}]}
    payload = json.loads(dream_prompt.evidence_message({'conversations/c': row}, Triage, 5000)[0]['content'])
    assert payload['summary_eligibility']['conversations/c']['title'] == 'editable'


def test_eligibility_eval_removes_wasted_offers():
    cases = [
        {'structured': {'title': 'Confirmed invented movie'}, 'transcript_segments': [{'text': 'solar boat ' * 20}]},
        {'transcript_segments': [{'text': 'This invented snippet has only eleven words about our toy boat.'}]},
    ]
    before = sum(2 for _ in cases)
    after = sum(value == 'editable' for row in cases for value in dream_guards.summary_eligibility(row).values())
    assert (before, after) == (4, 1)
