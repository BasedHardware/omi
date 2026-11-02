"""Synthetic task recall and final-selection contract; no user data or paid calls."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from utils.conversations import action_item_validity as validity
from utils.conversations import action_item_extraction as extraction


@pytest.mark.parametrize(
    'case', json.loads((Path(__file__).parent / 'fixtures/unresolved_reference_cases.json').read_text())
)
def test_reference_fixtures(case):
    case = dict(case)
    reason = case.pop('reason')
    assert validity.unresolved_reference(**case) == reason


def test_shadow_is_identity_and_text_free(monkeypatch, caplog):
    monkeypatch.delenv(validity.VALIDITY_MODE_ENV, raising=False)
    monkeypatch.delenv(validity.VALIDITY_SERVE_PERCENT_ENV, raising=False)
    items = [{'description': 'Send it here'}]
    with caplog.at_level('INFO', logger=validity.__name__):
        assert validity.select_valid_items('synthetic', items) == items
    assert 'count=1' in caplog.text
    assert 'Send it here' not in caplog.text
    assert 'synthetic' not in caplog.text


def test_final_guard_runs_after_v2_and_cannot_be_reintroduced(monkeypatch):
    monkeypatch.setattr(extraction, 'get_user_full_name', lambda *_: None)
    monkeypatch.setenv('ACTION_ITEMS_V2_MODE', 'serve')
    monkeypatch.setenv(validity.VALIDITY_MODE_ENV, 'serve')
    bad = {'description': 'Send it here', 'owner_name': 'me'}
    good = {'description': 'Buy milk', 'owner_name': 'me'}
    assert extraction.filter_extracted_items('synthetic', [bad, good]) == [good]


def test_cited_context_keeps_pronouns_without_mutation(monkeypatch):
    monkeypatch.setenv(validity.VALIDITY_MODE_ENV, 'serve')
    item = {'description': 'Send it', 'source_segment_ids': ['s1']}
    segments = [SimpleNamespace(id='s1', text='The Q3 deck goes to Morgan')]
    assert validity.select_valid_items('synthetic', [item], transcript_segments=segments) == [item]
    assert item['description'] == 'Send it'
    # Unrelated source rows cannot resolve the reference.
    assert (
        validity.select_valid_items('synthetic', [item], transcript_segments=[SimpleNamespace(id='s2', text='Budget')])
        == []
    )


def test_off_cohort_and_missing_capture_context(monkeypatch):
    item = {'description': 'Send it', 'source_segment_ids': ['s1']}
    monkeypatch.setenv(validity.VALIDITY_MODE_ENV, 'off')
    assert validity.select_valid_items('synthetic', [item]) == [item]
    monkeypatch.setenv(validity.VALIDITY_MODE_ENV, 'shadow')
    monkeypatch.setenv(validity.VALIDITY_SERVE_PERCENT_ENV, '100')
    assert validity.select_valid_items('synthetic', [{'description': 'Send it'}]) == []
    assert validity.select_valid_items('synthetic', [item]) == [item]


def test_role_map_is_not_a_blanket_object_resolution():
    # Role projection belongs to the extraction/capture prompt. Knowing who
    # speaks does not resolve who a placeholder task is asking to call.
    assert validity.unresolved_reference('Send it')
    assert validity.unresolved_reference('Call Speaker 2')
