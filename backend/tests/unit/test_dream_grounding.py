"""Invented spelling hallucinations, independent support and Review demotion."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from config.dream_agent import Caps
from database import dream_store
from models.dream_agent import Edit, Plan, Cluster, Triage
from utils import dream_agent, dream_grounding, dream_tools, review
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


def test_all_canonical_conversation_sources_prevent_false_independence():
    rows = {
        **records(),
        'memory_items/multi': {
            'content': 'Zuvrah',
            'conversation_id': 'later',
            'evidence': [
                {'source_type': 'conversation', 'source_id': 'film'},
                {'source_type': 'conversation', 'source_id': 'later'},
            ],
        },
    }
    assert dream_grounding.spelling_grounding_rejection(correction(evidence=list(rows)), rows) == 'ungrounded_spelling'


@pytest.mark.parametrize('before,after', [('Zuvra', 'Zuvra'), (' ', 'Zuvrah'), ('Zuvra', ' '), (' Zuvra', 'Zuvra ')])
def test_invalid_spelling_never_reaches_review(before, after):
    from utils.dream_guards import filter_plan

    edit = correction().model_copy(update={'before': before, 'after': after})
    sink = {}
    assert not filter_plan(Plan(edits=[edit]), records(), usage_sink=sink).edits
    assert sink['rejected'] == {'invalid_spelling': 1}


def test_spelling_question_retains_fenced_actionable_source(monkeypatch):
    seen = []
    monkeypatch.setattr(dream_tools, 'proposal_fences', lambda *a: {'conversations/film': {'raw': 'original'}})
    monkeypatch.setattr(dream_tools, 'revalidate_proposal', lambda *a: records())
    monkeypatch.setattr(dream_tools, 'validate_canonical_proposal', lambda *a: None)
    monkeypatch.setattr(
        dream_tools.review_store,
        'enqueue_review_proposal',
        lambda uid, item, **kwargs: seen.append(kwargs) or 'suggested',
    )
    assert dream_tools.suggest_spelling('synthetic', correction(), records(), 'fixture-run') == 'suggested'
    source = seen[0]['source']
    applied = []
    monkeypatch.setattr(
        dream_tools, 'apply_edit', lambda uid, edit, rows, **kwargs: applied.append((edit, kwargs)) or 'applied'
    )
    assert dream_tools.answer_spelling('synthetic', source, 'Custom synthetic name')
    assert applied[0][0].target == 'conversations/film'
    assert applied[0][0].after == 'Custom synthetic name'
    assert applied[0][1]['expected_records'] == source['fences']
    assert not dream_tools.answer_spelling('synthetic', source, 'Zuvra')
    monkeypatch.setattr(
        dream_tools,
        'revalidate_proposal',
        lambda *a: (_ for _ in ()).throw(dream_tools.review_store.ReviewConflict('changed')),
    )
    with pytest.raises(dream_tools.review_store.ReviewConflict, match='changed'):
        dream_tools.answer_spelling('synthetic', source, 'Zuvrah')


def test_review_answer_dispatches_dream_spelling_source(monkeypatch):
    from models.review import ReviewAnswer, SpellingAnswer

    item = dream_grounding.spelling_question(correction())
    source = {'spelling_edit': correction().model_dump(mode='python')}
    monkeypatch.setattr(
        review.store,
        'begin_answer',
        lambda *a: {'retry': False, 'item': item.model_dump(mode='python'), 'source': source, 'version': 'fixture'},
    )
    monkeypatch.setattr(review.store, 'finish_answer', lambda uid, item_id, **kwargs: kwargs)
    seen = []
    monkeypatch.setattr(
        dream_tools, 'answer_spelling', lambda uid, snapshot, value: seen.append((snapshot, value)) or True
    )
    result = review.answer_item('synthetic', item.item_id, ReviewAnswer(spelling=SpellingAnswer(value='Zuvrah')))
    assert result['applied']
    assert seen == [(source, 'Zuvrah')]


def test_spelling_enqueue_counts_only_new_cards_atomically(monkeypatch):
    from database import review_store
    from tests.support.dream_firestore import DreamFirestore
    from datetime import datetime, timezone

    db = DreamFirestore()
    uid, run_id = 'synthetic', 'fixture-run'
    state_path = ('dream_users', uid)
    db.rows[state_path] = {'lease': {'run_id': run_id}}
    monkeypatch.setenv('REVIEW_SURFACE_MODE', 'on')
    monkeypatch.setattr(review_store, 'get_firestore_client', lambda: db)
    monkeypatch.setattr(review_store, 'encode_doc', lambda uid, doc: doc)
    monkeypatch.setattr(review_store, 'decode_doc', lambda uid, doc: doc)
    monkeypatch.setattr(review_store.firestore, 'transactional', lambda fn: fn)
    item = dream_grounding.spelling_question(correction())
    kwargs = {'evidence_version': 'fixture', 'dream_run_id': run_id}
    assert review_store.enqueue_review_proposal(uid, item, **kwargs) == 'suggested'
    assert db.rows[state_path]['questions'] == 1
    assert review_store.enqueue_review_proposal(uid, item, **kwargs) == 'already_suggested'
    proposal = ('users', uid, 'review_proposals', review_store.safe_id(item.item_id))
    db.rows[proposal]['status'] = 'resolved'
    assert (
        review_store.enqueue_review_proposal(uid, item, evidence_version='new', dream_run_id=run_id)
        == 'already_suggested'
    )
    assert db.rows[state_path]['questions'] == 1
    day = datetime.now(timezone.utc).date().isoformat()
    db.rows[('users', uid, 'review_attention', day)] = {'dream_suggestions': 2}
    new_item = item.model_copy(update={'item_id': 'spelling:new-fixture'})
    assert review_store.enqueue_review_proposal(uid, new_item, **kwargs) == 'suggestion_cap'
    assert db.rows[state_path]['questions'] == 1


def test_capped_spelling_preserves_capacity_for_next_edit(monkeypatch):
    rows = {**records(), 'conversations/empty': {'transcript_segments': [{'text': 'solar boat ' * 20}]}}
    lease = {'run_id': 'fixture-run', 'mode': 'on'}
    monkeypatch.setenv('DREAM_AGENT_MODE', 'on')
    monkeypatch.setattr(dream_store, 'acquire', lambda *a, **k: lease)
    monkeypatch.setattr(dream_store, 'vocabulary', lambda *a: [])
    monkeypatch.setattr(dream_store, 'demoted_types', lambda *a: set())
    monkeypatch.setattr(dream_store, 'assert_lease', lambda *a: None)
    monkeypatch.setattr(dream_store, 'finish', lambda *a, **k: None)
    monkeypatch.setattr(dream_agent.dream_reads, 'read_changes', lambda *a: (rows, []))
    summary = Edit(
        kind='title',
        target='conversations/empty',
        after='Solar boat discussion',
        reason='Synthetic',
        evidence=['conversations/empty'],
    )
    monkeypatch.setattr(dream_agent, 'plan_pass', AsyncMock(return_value=(Plan(edits=[correction(), summary]), 100)))
    monkeypatch.setattr(dream_agent.review_changes, 'agent_change_allowed', lambda *a: True)
    monkeypatch.setattr(dream_agent.review_store, 'remaining_today', lambda *a: 3)
    monkeypatch.setattr(dream_tools, 'suggest_spelling', lambda *a: 'suggestion_cap')
    applied = []
    monkeypatch.setattr(dream_tools, 'apply_edit', lambda uid, edit, records: applied.append(edit.target) or 'applied')
    result = asyncio.run(dream_agent.run_pass('synthetic', caps=Caps(edits=1)))
    assert result['status'] == 'complete'
    assert applied == ['conversations/empty']


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
        lambda uid, edit, records, run_id: (
            (questions.append(dream_grounding.spelling_question(edit)) or 'suggested') if budget else 'suggestion_cap'
        ),
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
