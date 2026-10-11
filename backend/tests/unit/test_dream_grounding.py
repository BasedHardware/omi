"""Invented spelling hallucinations, independent support and Review demotion."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from config.dream_agent import Caps
from database import dream_store
from models.dream_agent import Edit, Plan, Cluster, Triage
from utils import dream_agent, dream_grounding, dream_tools
from utils.llm.shaped_agent import Turn


def correction(**updates):
    return Edit(
        kind='spelling',
        target='conversations/film',
        before='Zuvra',
        after='Zuvrah',
        reason='Synthetic name uncertainty',
        evidence=updates.pop('evidence', ['conversations/film']),
        **updates
    )


def records():
    return {
        'conversations/film': {
            'id': 'film',
            'transcript_segments': [{'text': 'The invented film is called Zuvra. Yes, Zuvra is its name.'}],
        }
    }


def test_repeated_confirmation_in_target_is_not_independent_support():
    rows = records()
    rows['conversations/film']['structured'] = {'title': 'Zuvrah'}
    assert dream_grounding.spelling_grounding_rejection(correction(), rows) == 'ungrounded_spelling'


@pytest.mark.parametrize(
    'row',
    [
        {'name': 'Zuvrah'},
        {'content': 'Zuvrah is an invented dish.'},
        {'transcript_segments': [{'text': 'We discussed Zuvrah.'}]},
    ],
)
def test_corrected_form_requires_cited_independent_record(row):
    rows = {**records(), 'people/independent': row}
    assert dream_grounding.spelling_grounding_rejection(correction(), rows) == 'ungrounded_spelling'
    assert (
        dream_grounding.spelling_grounding_rejection(
            correction(evidence=['conversations/film', 'people/independent']), rows
        )
        is None
    )


def test_derived_memory_and_alias_of_same_record_are_not_independent():
    rows = {**records(), 'memory_items/derived': {'content': 'Zuvrah', 'conversation_id': 'film'}}
    assert dream_grounding.spelling_grounding_rejection(correction(evidence=list(rows)), rows) == 'ungrounded_spelling'
    rows = {**records(), 'memories/film': {'content': 'Zuvrah'}}
    assert dream_grounding.spelling_grounding_rejection(correction(evidence=list(rows)), rows) == 'ungrounded_spelling'


def test_existing_vocabulary_support_is_exact_and_accent_sensitive():
    assert dream_grounding.spelling_grounding_rejection(correction(), records(), [{'spelling': 'ZUVRAH'}]) is None
    assert (
        dream_grounding.spelling_grounding_rejection(correction(), records(), [{'spelling': 'Zuvrahtown'}])
        == 'ungrounded_spelling'
    )
    assert not dream_grounding.contains_spelling('Zuvráh', 'Zuvrah')


def test_read_only_eval_shows_zero_ungrounded_auto_applies_and_question():
    async def turn(uid, lane, mount, messages):
        value = (
            Triage(clusters=[Cluster(refs=['conversations/film'], problem='spelling')])
            if mount.schema is Triage
            else Plan(edits=[correction()])
        )
        return Turn(value=value, tokens=50)

    result = asyncio.run(dream_agent.dry_run('synthetic', records(), turn=turn))
    assert result['plan']['edits'][0]['policy'] == 'suggest'
    assert result['guard_decisions'] == {'ungrounded_spelling': 1}
    assert result['plan']['questions'][0]['kind'] == 'spelling'
    assert result['plan']['questions'][0]['spelling']['options'] == ['Zuvra', 'Zuvrah']
    assert not any(row['policy'] == 'auto' for row in result['plan']['edits'])


@pytest.mark.parametrize('budget', [0, 1])
def test_real_pass_routes_ungrounded_to_spelling_question_with_shared_cap(monkeypatch, budget):
    rows = records()
    lease = {'run_id': 'synthetic', 'mode': 'on'}
    monkeypatch.setenv('DREAM_AGENT_MODE', 'on')
    monkeypatch.setattr(dream_store, 'acquire', lambda *a, **k: lease)
    monkeypatch.setattr(dream_store, 'vocabulary', lambda *a: [])
    monkeypatch.setattr(dream_store, 'demoted_types', lambda *a: set())
    monkeypatch.setattr(dream_store, 'assert_lease', lambda *a: None)
    monkeypatch.setattr(dream_store, 'reserve_questions', lambda *a: budget)
    monkeypatch.setattr(dream_store, 'finish', lambda *a, **k: None)
    monkeypatch.setattr(dream_agent.dream_reads, 'read_changes', lambda *a: (rows, []))
    monkeypatch.setattr(dream_agent, 'plan_pass', AsyncMock(return_value=(Plan(edits=[correction()]), 100)))
    monkeypatch.setattr(dream_agent.review_changes, 'agent_change_allowed', lambda *a: True)
    monkeypatch.setattr(dream_agent.review_store, 'remaining_today', lambda *a: 3)
    monkeypatch.setattr(dream_tools, 'apply_edit', lambda *a, **k: pytest.fail('ungrounded automatic write'))
    monkeypatch.setattr(dream_tools, 'apply_grounded_edit', lambda *a, **k: pytest.fail('ungrounded automatic write'))
    questions = []
    monkeypatch.setattr(
        dream_tools,
        'suggest_spelling',
        lambda uid, edit, records: questions.append(dream_grounding.spelling_question(edit)) or 'suggested',
    )
    report = asyncio.run(dream_agent.run_pass('synthetic', caps=Caps()))
    assert report['status'] == 'complete'
    assert report['proposed']['edits'][0]['policy'] == 'suggest'
    assert report['outcomes'][0]['status'] == ('suggested' if budget else 'suggestion_cap')
    assert len(questions) == budget
    assert report['rejected']['ungrounded_spelling'] == 1


def test_automatic_boundary_rechecks_current_support_and_fences_before_read(monkeypatch):
    calls = []
    raw = {'source': [{'spelling': 'Zuvrah'}]}
    monkeypatch.setattr(dream_tools, 'validate_edit', lambda *a: None)
    monkeypatch.setattr(
        dream_tools, 'proposal_fences', lambda *a: calls.append('fence') or {'conversations/film': {'raw': 'snapshot'}}
    )
    monkeypatch.setattr(dream_tools, 'revalidate_proposal', lambda *a: calls.append('revalidate'))
    monkeypatch.setattr(
        dream_tools.review_store,
        'user',
        lambda *a: SimpleNamespace(
            collection=lambda *a: SimpleNamespace(
                document=lambda *a: SimpleNamespace(get=lambda: SimpleNamespace(to_dict=lambda: raw))
            )
        ),
    )
    monkeypatch.setattr(dream_tools.review_store, 'decode_doc', lambda uid, doc: doc)
    monkeypatch.setattr(
        dream_tools,
        'apply_edit',
        lambda uid, edit, records, **kwargs: calls.append(kwargs['expected_records']) or 'applied',
    )
    assert dream_tools.apply_grounded_edit('synthetic', correction(), records()) == 'applied'
    assert calls[:2] == ['fence', 'revalidate']
    assert calls[-1]['dream_vocabulary/current'] == raw
    raw['source'] = []
    with pytest.raises(ValueError, match='ungrounded_spelling'):
        dream_tools.apply_grounded_edit('synthetic', correction(), records())
