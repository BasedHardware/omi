"""Review spelling excerpts remain verbatim, owner-scoped, bounded and encrypted."""

from copy import deepcopy
from datetime import datetime, timezone
from unittest.mock import Mock
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from database import review_store as store
from models.review import (
    EntitySummary,
    ReviewAnswer,
    ReviewAnswerReceipt,
    ReviewItem,
    SamePersonItem,
    SpellingAnswer,
    SpellingItem,
)
from models.review_context import build_context, enrich_spelling, question_source
from routers import review as router
from tests.support.dream_firestore import DreamFirestore
from utils import review

NOW = datetime(2026, 10, 14, 12, tzinfo=timezone.utc)
UID = 'synthetic-context-owner'
REF = 'conversations/toy'
ROW = {
    'structured': {'title': 'Toy launch planning'},
    'started_at': NOW,
    'transcript_segments': [
        {'id': 'a', 'text': 'Where should we send the link?', 'person_id': 'alex'},
        {'id': 'b', 'start': 10, 'text': 'Please send the UL to the design group.', 'is_user': True},
        {'id': 'c', 'text': 'I will share it after lunch.', 'person_id': 'alex'},
    ],
}


def item(ref=REF + '#b', quote='UL'):
    return ReviewItem(
        item_id='spelling:toy',
        kind='spelling',
        title='Which spelling?',
        quote=quote,
        source_ref=ref,
        created_at=NOW,
        spelling=SpellingItem(term_id='toy', options=['UL', 'URL'], allow_custom=True),
    )


def source(row=None):
    return {'records': {REF: deepcopy(ROW if row is None else row)}, 'speaker_names': {'alex': 'Alex'}}


@pytest.mark.parametrize('ref', [REF, REF + '#b', REF + '#10', REF + '#00:00:10'])
def test_quote_with_neighbours_names_date_and_offsets(ref):
    context = build_context(item(ref), source())
    assert context.conversation_title == 'Toy launch planning' and context.conversation_date == NOW
    assert context.main_index == 1
    assert [s.text for s in context.segments] == [s['text'] for s in ROW['transcript_segments']]
    assert [s.speaker_label for s in context.segments] == ['Alex', 'You', 'Alex']
    assert context.segments[1].is_user
    assert context.segments[1].text[context.quote_start : context.quote_end] == 'UL'


def test_fragment_does_not_highlight_an_identical_quote_in_another_segment():
    context = build_context(item(REF + '#a'), source())
    assert context.main_index == 0
    assert context.quote_start is None and context.quote_end is None
    assert context.segments[0].text == ROW['transcript_segments'][0]['text']
    assert len(context.segments) == 2
    assert build_context(item(REF + '#unknown'), source()) is None


@pytest.mark.parametrize('fragment', ['#a', '#b', '#c'])
def test_whole_excerpt_is_bounded_and_cropping_keeps_exact_offsets(fragment):
    row = deepcopy(ROW)
    for segment in row['transcript_segments']:
        segment['text'] = 'before ' * 200 + 'UL' + ' after' * 200
    context = build_context(item(REF + fragment), source(row))
    assert sum(len(s.text) for s in context.segments) <= 400
    main = context.segments[context.main_index].text
    assert main[context.quote_start : context.quote_end] == 'UL'
    assert len(context.segments) == (3 if fragment == '#b' else 2)


def test_unicode_offsets_match_dart_utf16_code_units():
    row = deepcopy(ROW)
    row['transcript_segments'][1]['text'] = '🙂 请发 UL 给我'
    context = build_context(item(), source(row))
    encoded = context.segments[1].text.encode('utf-16-le')
    assert encoded[context.quote_start * 2 : context.quote_end * 2].decode('utf-16-le') == 'UL'
    assert context.quote_start == 6


def test_unknown_speaker_is_not_given_a_fabricated_name():
    data = source()
    data.pop('speaker_names')
    assert build_context(item(), data).segments[0].speaker_label is None


def test_source_snapshot_is_authoritative_without_product_reads_and_old_items_read_once():
    loader = Mock(return_value=ROW)
    assert build_context(item(), source(), load_conversation=loader)
    loader.assert_not_called()
    assert build_context(item(), {}, load_conversation=loader)
    loader.assert_called_once_with('toy')
    loader.reset_mock()
    assert build_context(item('conversations/other/invalid#b'), {}, load_conversation=loader) is None
    loader.assert_not_called()


def test_question_source_keeps_only_cited_record_and_existing_names():
    records = {REF: ROW, 'people/alex': {'name': 'Alex'}, 'conversations/unrelated': {'secret': 'not stored'}}
    assert question_source(item(), records) == source(ROW)


@pytest.fixture
def storage(monkeypatch):
    db = DreamFirestore()
    monkeypatch.setattr(store, 'client', lambda: db)
    monkeypatch.setattr(store.firestore, 'transactional', lambda fn: fn)
    monkeypatch.setenv('REVIEW_SURFACE_MODE', 'on')
    return db


def test_enqueue_computes_context_and_encrypts_it_with_source(storage):
    offered = item()
    offered.spelling.context = build_context(item(REF + '#a'), source())
    store.enqueue_review_proposal(UID, offered, source=source(), evidence_version='v1')
    raw = storage.rows[('users', UID, 'review_proposals', store.safe_id(offered.item_id))]
    assert 'Toy launch' not in str(raw) and 'design group' not in str(raw) and 'Alex' not in str(raw)
    decoded = store.require_doc(UID, raw)
    assert decoded['item']['spelling']['context']['main_index'] == 1  # Replace supplied display data.
    assert decoded['source'] == source()


@pytest.mark.parametrize('snapshot', [True, False])
@pytest.mark.parametrize('api', ['v1', 'v2'])
def test_local_http_list_enriches_queued_items_and_offers_encrypted_context(storage, monkeypatch, snapshot, api):
    legacy = item()
    src = source() if snapshot else {}
    raw = store.encode_doc(UID, {'item': legacy.model_dump(), 'source': src, 'evidence_version': 'v1'})
    monkeypatch.setattr(store, 'remaining_today', lambda *args: 3)
    from database import task_intelligence_control
    from utils.task_intelligence import chat_first_eligibility

    monkeypatch.setattr(review.speakers, 'get_prompts', lambda uid: SimpleNamespace(prompts=[]))
    monkeypatch.setattr(
        task_intelligence_control,
        'get_task_workflow_control',
        lambda uid: SimpleNamespace(workflow_mode='off', account_generation=0),
    )
    monkeypatch.setattr(
        chat_first_eligibility,
        'resolve_task_intelligence_for_user',
        lambda **kwargs: SimpleNamespace(intelligence_product_enabled=False),
    )
    monkeypatch.setattr(store, 'list_proposals', lambda uid: [store.require_doc(uid, raw)])
    loader = Mock(return_value=ROW)
    monkeypatch.setattr(review.conversations, 'get_conversation', loader)
    app = FastAPI()
    app.include_router(router.router)
    app.dependency_overrides[router.auth.get_current_user_uid] = lambda: UID
    with TestClient(app) as client:
        response = client.get(f'/{api}/review/items')
    assert response.status_code == 200, response.text
    context = response.json()['items'][0]['spelling']['context']
    assert context['conversation_title'] == 'Toy launch planning'
    assert context['segments'][context['main_index']]['is_user']
    if snapshot:
        loader.assert_not_called()
    else:
        loader.assert_called_once_with(UID, 'toy')
    offered = storage.rows[('users', UID, 'review_answers', store.safe_id(legacy.item_id))]
    assert 'design group' not in str(offered)
    assert store.require_doc(UID, offered)['item']['spelling']['context']['quote_start'] == context['quote_start']


def test_already_computed_context_needs_no_read_and_missing_conversation_is_optional():
    enriched = enrich_spelling(item(), source())
    loader = Mock(side_effect=AssertionError('unexpected read'))
    assert enrich_spelling(enriched, {}, load_conversation=loader) is enriched
    assert enrich_spelling(item(), {}, load_conversation=lambda _: None).spelling.context is None


def test_server_context_does_not_enter_the_model_output_schema():
    from models.agent_tools import Ask

    schema = Ask.model_json_schema()
    assert 'SpellingContext' not in schema.get('$defs', {})
    assert 'context' not in schema['$defs']['SpellingQuestionPayload']['properties']


class _User:
    def get(self):
        return self

    def to_dict(self):
        return {}


def _quiet_review(monkeypatch):
    monkeypatch.setenv('DREAM_AGENT_ELIGIBILITY', 'allowlist')
    monkeypatch.setenv('DREAM_AGENT_UID_ALLOWLIST', UID)
    monkeypatch.setattr(review.store, 'user', lambda uid: _User())
    monkeypatch.setattr(review.store, 'remaining_today', lambda uid: 3)
    monkeypatch.setattr(review.store, 'offer_item', lambda *args: True)
    monkeypatch.setattr(review.speakers, 'get_prompts', lambda uid: SimpleNamespace(prompts=[]))
    monkeypatch.setattr(
        'database.task_intelligence_control.get_task_workflow_control',
        lambda uid: SimpleNamespace(workflow_mode='off', account_generation=0),
    )
    monkeypatch.setattr(
        'utils.task_intelligence.chat_first_eligibility.resolve_task_intelligence_for_user',
        lambda **kwargs: SimpleNamespace(intelligence_product_enabled=False),
    )


def test_dream_enqueue_marks_origin_and_plain_enqueue_does_not(storage):
    plain = item()
    store.enqueue_review_proposal(UID, plain, source=source(), evidence_version='v1')
    plain_row = storage.rows[('users', UID, 'review_proposals', store.safe_id(plain.item_id))]
    assert store.require_doc(UID, plain_row).get('dream_origin') is not True
    assert store.proposal_is_dream_origin(UID, plain.item_id) is False

    storage.rows[('dream_users', UID)] = {'lease': {'run_id': 'run-1'}}
    dreamed = item()
    dreamed.item_id = 'spelling:dream'
    assert (
        store.enqueue_review_proposal(UID, dreamed, source=source(), evidence_version='v2', dream_run_id='run-1')
        == 'suggested'
    )
    marked = store.require_doc(UID, storage.rows[('users', UID, 'review_proposals', store.safe_id(dreamed.item_id))])
    assert marked['dream_origin'] is True
    assert store.proposal_is_dream_origin(UID, dreamed.item_id) is True


def test_ineligible_owners_lose_dream_questions_and_keep_ordinary_ones(monkeypatch):
    _quiet_review(monkeypatch)
    dreamed = item()
    dreamed.item_id = 'spelling:dream'
    plain = item()
    person = ReviewItem(
        item_id='same_person:dream',
        kind='same_person',
        title='Same person?',
        created_at=NOW,
        same_person=SamePersonItem(
            left=EntitySummary(entity_id='a', type='person', name='Ada'),
            right=EntitySummary(entity_id='b', type='person', name='Ada B'),
            reason='Shared name',
        ),
    )
    ordinary = ReviewItem(
        item_id='same_person:user',
        kind='same_person',
        title='Same person?',
        created_at=NOW,
        same_person=person.same_person,
    )

    def show(rows):
        monkeypatch.setattr(review.store, 'list_proposals', lambda uid: rows)
        return review.get_items('other-owner'), review.get_items(UID)

    hidden, shown = show(
        [
            {'item': dreamed.model_dump(), 'source': source(), 'evidence_version': 'd', 'dream_origin': True},
            {'item': plain.model_dump(), 'source': source(), 'evidence_version': 'p'},
        ]
    )
    assert {row.item_id for row in hidden.items} == {'spelling:toy'}
    assert {row.item_id for row in shown.items} == {'spelling:dream', 'spelling:toy'}
    hidden, shown = show(
        [
            {'item': person.model_dump(), 'source': {}, 'evidence_version': 's', 'dream_origin': True},
            {'item': ordinary.model_dump(), 'source': {}, 'evidence_version': 'u'},
        ]
    )
    assert {row.item_id for row in hidden.items} == {'same_person:user'}
    assert {row.item_id for row in shown.items} == {'same_person:dream', 'same_person:user'}


def _answer(monkeypatch, *, dream):
    _quiet_review(monkeypatch)
    monkeypatch.setattr(
        review.store,
        'begin_answer',
        lambda *args, **kwargs: {'item': item().model_dump(), 'source': {}, 'version': 'v', 'retry': False},
    )
    monkeypatch.setattr(review.store, 'proposal_is_dream_origin', lambda uid, item_id: dream)
    saved = []
    monkeypatch.setattr('utils.entity_pages.save_user_fact', lambda *args, **kwargs: saved.append(args))
    monkeypatch.setattr(
        review.store,
        'finish_answer',
        lambda *args, **kwargs: ReviewAnswerReceipt(item_id='spelling:toy', applied=True, remaining_today=2),
    )
    released = []
    monkeypatch.setattr(review.store, 'release_failed_answer', lambda *args, **kwargs: released.append(args))
    return saved, released


def test_ineligible_owner_cannot_answer_a_dream_question_and_eligible_owner_can(monkeypatch):
    saved, released = _answer(monkeypatch, dream=True)
    with pytest.raises(store.ReviewConflict, match='Dream proposals'):
        review.answer_item('other-owner', 'spelling:toy', ReviewAnswer(spelling=SpellingAnswer(value='URL')))
    assert saved == [] and released

    saved, released = _answer(monkeypatch, dream=True)
    receipt = review.answer_item(UID, 'spelling:toy', ReviewAnswer(spelling=SpellingAnswer(value='URL')))
    assert receipt.applied is True and saved and released == []

    saved, released = _answer(monkeypatch, dream=False)
    receipt = review.answer_item('other-owner', 'spelling:toy', ReviewAnswer(spelling=SpellingAnswer(value='URL')))
    assert receipt.applied is True and saved and released == []


def test_unmarked_preexisting_dream_question_is_hidden_when_the_owner_becomes_ineligible(storage, monkeypatch):
    source_ref = REF + '#b'
    quote = 'UL'
    legacy = item(source_ref, quote)
    legacy.item_id = store.dream_question_item_id(UID, 'spelling', source_ref, quote)
    store.enqueue_review_proposal(UID, legacy, source=source(), evidence_version='legacy')
    decoded = store.require_doc(UID, storage.rows[('users', UID, 'review_proposals', store.safe_id(legacy.item_id))])
    assert decoded.get('dream_origin') is not True
    assert store.proposal_is_dream_origin(UID, legacy.item_id) is True

    person_ref = 'entity/person:a'
    person_quote = 'Ada met Ada'
    person = ReviewItem(
        item_id=store.dream_question_item_id(UID, 'same_person', person_ref, person_quote),
        kind='same_person',
        title='Same person?',
        quote=person_quote,
        source_ref=person_ref,
        created_at=NOW,
        same_person=SamePersonItem(
            left=EntitySummary(entity_id='a', type='person', name='Ada'),
            right=EntitySummary(entity_id='b', type='person', name='Ada B'),
            reason='Shared name',
        ),
    )
    store.enqueue_review_proposal(UID, person, evidence_version='legacy-person')
    person_row = store.require_doc(UID, storage.rows[('users', UID, 'review_proposals', store.safe_id(person.item_id))])
    assert person_row.get('dream_origin') is not True
    plain = item()
    monkeypatch.setenv('DREAM_AGENT_ELIGIBILITY', 'allowlist')
    monkeypatch.setenv('DREAM_AGENT_UID_ALLOWLIST', UID)
    monkeypatch.setattr(review.store, 'remaining_today', lambda uid: 3)
    monkeypatch.setattr(review.store, 'offer_item', lambda *args: True)
    monkeypatch.setattr(review.speakers, 'get_prompts', lambda uid: SimpleNamespace(prompts=[]))
    monkeypatch.setattr(
        'database.task_intelligence_control.get_task_workflow_control',
        lambda uid: SimpleNamespace(workflow_mode='off', account_generation=0),
    )
    monkeypatch.setattr(
        'utils.task_intelligence.chat_first_eligibility.resolve_task_intelligence_for_user',
        lambda **kwargs: SimpleNamespace(intelligence_product_enabled=False),
    )
    monkeypatch.setattr(
        review.store,
        'list_proposals',
        lambda uid: [decoded, person_row, {'item': plain.model_dump(), 'source': source(), 'evidence_version': 'p'}],
    )
    shown = review.get_items(UID)
    assert {row.item_id for row in shown.items} == {legacy.item_id, person.item_id, 'spelling:toy'}
    monkeypatch.setenv('DREAM_AGENT_UID_ALLOWLIST', 'synthetic-other-owner')
    hidden = review.get_items(UID)
    assert {row.item_id for row in hidden.items} == {'spelling:toy'}

    monkeypatch.setattr(
        review.store,
        'begin_answer',
        lambda *args, **kwargs: {'item': legacy.model_dump(), 'source': {}, 'version': 'v', 'retry': False},
    )
    saved = []
    monkeypatch.setattr('utils.entity_pages.save_user_fact', lambda *args, **kwargs: saved.append(args))
    released = []
    monkeypatch.setattr(review.store, 'release_failed_answer', lambda *args, **kwargs: released.append(args))
    monkeypatch.setattr(
        review.store,
        'finish_answer',
        lambda *args, **kwargs: ReviewAnswerReceipt(item_id=legacy.item_id, applied=True, remaining_today=2),
    )
    with pytest.raises(store.ReviewConflict, match='Dream proposals'):
        review.answer_item(UID, legacy.item_id, ReviewAnswer(spelling=SpellingAnswer(value='URL')))
    assert saved == [] and released
    saved.clear()
    released.clear()
    monkeypatch.setenv('DREAM_AGENT_UID_ALLOWLIST', UID)
    receipt = review.answer_item(UID, legacy.item_id, ReviewAnswer(spelling=SpellingAnswer(value='URL')))
    assert receipt.applied is True and saved and released == []


def test_a_long_verbatim_quote_that_fits_the_budget_stays_whole_and_highlighted():
    quote = 'UL' * 175
    row = deepcopy(ROW)
    row['transcript_segments'][1]['text'] = 'before ' * 100 + quote + ' after' * 100
    context = build_context(item(quote=quote), source(row))
    main = context.segments[context.main_index].text
    assert main == quote
    assert main[context.quote_start : context.quote_end] == quote
    assert sum(len(segment.text) for segment in context.segments) <= 400
    assert len(context.segments) == 3
