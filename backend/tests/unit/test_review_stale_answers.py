"""Stale Review questions settle durably; transactional races stay retryable."""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from database import review_store as store, review_changes, task_intelligence_control
from models.agent_tools import HarnessQuestion
from models.review import EntitySummary, ReviewItem, SamePersonItem
from routers import review as router
from tests.support.dream_firestore import DreamFirestore
from utils import dream_review_policy, entity_pages, review
from utils.agent_capabilities import staging, tools
from utils.task_intelligence import chat_first_eligibility

UID = 'synthetic-stale-owner'
NOW = datetime.now(timezone.utc)


def question(item_id='same_person:toy'):
    return ReviewItem(
        item_id=item_id,
        kind='same_person',
        title='Same person?',
        created_at=NOW,
        same_person=SamePersonItem(
            left=EntitySummary(entity_id='person:a', type='person', name='Sam'),
            right=EntitySummary(entity_id='person:b', type='person', name='Samuel'),
            reason='Same voice',
        ),
    )


@pytest.fixture
def harness(monkeypatch):
    db = DreamFirestore()
    monkeypatch.setattr(store, 'client', lambda: db)
    monkeypatch.setattr(store.firestore, 'transactional', lambda fn: fn)
    monkeypatch.setenv('REVIEW_SURFACE_MODE', 'on')
    monkeypatch.setattr(review, 'dream_visible', lambda uid: True)
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
    # Substitute only the pending query; transactions, encryption, offers,
    # reservation, settlement, entity redirects and HTTP handlers are real.
    monkeypatch.setattr(
        store,
        'list_proposals',
        lambda uid: [
            store.require_doc(uid, row)
            for path, row in db.rows.items()
            if path[:-1] == ('users', uid, 'review_proposals') and row.get('status') == 'pending'
        ],
    )
    monkeypatch.setattr(
        entity_pages.knowledge_graph,
        'get_knowledge_node',
        lambda uid, key: store.user(uid).collection('knowledge_nodes').document(key).get().to_dict(),
    )
    monkeypatch.setattr(
        entity_pages.users,
        'get_person',
        lambda uid, key: store.user(uid).collection('people').document(key).get().to_dict(),
    )
    for key in ('a', 'b'):
        store.user(UID).collection('people').document(key).set({'name': key})
        store.user(UID).collection('knowledge_nodes').document('person:' + key).set(
            {'id': 'person:' + key, 'label': key, 'node_type': 'person', 'aliases': []}
        )
    app = FastAPI()
    app.include_router(router.router)
    app.dependency_overrides[router.auth.get_current_user_uid] = lambda: UID
    with TestClient(app) as client:
        yield client, db


def offer(client, item=None):
    item = item or question()
    store.enqueue_review_proposal(UID, item, evidence_version='v1')
    assert client.get('/v2/review/items').json()['items'][0]['item_id'] == item.item_id
    return item.item_id


def answer(client, item_id, decision='yes'):
    return client.post(f'/v2/review/items/{item_id}/answer', json={'same_person': {'decision': decision}})


def proposal(item_id):
    return store.user(UID).collection('review_proposals').document(store.safe_id(item_id))


def test_yes_after_redirects_converge_resolves_without_second_merge(harness):
    client, _ = harness
    item_id = offer(client)
    store.user(UID).collection('knowledge_nodes').document('person:b').set({'redirect_entity_id': 'person:a'})
    response = answer(client, item_id)
    assert response.status_code == 200, response.text
    assert response.json()['applied'] is False
    assert answer(client, item_id).json() == response.json()
    assert proposal(item_id).get().to_dict()['status'] == 'resolved'
    assert client.get('/v2/review/items').json()['items'] == []
    assert (
        store.user(UID)
        .collection('review_changes')
        .document(store.safe_id('review:' + store.safe_id(item_id)))
        .get()
        .exists
        is False
    )


@pytest.mark.parametrize('failure', ['same_node_no', 'missing', 'types', 'kind', 'redirect_cycle', 'suppressed'])
def test_deterministic_conflicts_retire_and_refund_attention(harness, failure):
    client, db = harness
    item_id = offer(client)
    if failure in {'same_node_no', 'redirect_cycle'}:
        store.user(UID).collection('knowledge_nodes').document('person:b').set({'redirect_entity_id': 'person:a'})
        if failure == 'redirect_cycle':
            store.user(UID).collection('knowledge_nodes').document('person:a').set({'redirect_entity_id': 'person:b'})
    elif failure == 'missing':
        store.user(UID).collection('people').document('b').delete()
    elif failure == 'types':
        store.user(UID).collection('knowledge_nodes').document('person:b').set({'redirect_entity_id': 'org'})
        store.user(UID).collection('knowledge_nodes').document('org').set({'node_type': 'organization', 'label': 'Org'})
    elif failure == 'suppressed':
        store.user(UID).collection('review_do_not_redo').document(store.safe_id('merge:person:a:person:b')).set(
            {'blocked': True}
        )
    elif failure == 'kind':
        # A legacy persisted shape bypassing today's enqueue prefix validator.
        offered = store.user(UID).collection('review_answers').document(store.safe_id(item_id))
        data = store.require_doc(UID, offered.get().to_dict())
        item_id = 'agent:question:legacy'
        data['item']['item_id'] = item_id
        store.user(UID).collection('review_answers').document(store.safe_id(item_id)).set(store.encode_doc(UID, data))
        proposal(item_id).set(proposal('same_person:toy').get().to_dict())
        proposal('same_person:toy').delete()
    response = answer(client, item_id, 'no' if failure == 'same_node_no' else 'yes')
    assert response.status_code == 409, response.text
    assert proposal(item_id).get().to_dict()['status'] == 'resolved'
    assert proposal(item_id).get().to_dict()['resolution'] == 'stale'
    assert store.remaining_today(UID) == 3
    assert client.get('/v2/review/items').json()['items'] == []


@pytest.mark.parametrize(
    'message',
    ['dream_lease_lost', 'Dream proposal evidence changed during apply', 'Entity changed while preparing merge'],
)
def test_transient_conflict_releases_for_retry(harness, monkeypatch, message):
    client, _ = harness
    item_id = offer(client)
    merge = Mock(side_effect=store.ReviewConflict(message))
    monkeypatch.setattr(review_changes, 'merge_review_entities', merge)
    response = answer(client, item_id)
    assert response.status_code == 409, response.text
    row = store.user(UID).collection('review_answers').document(store.safe_id(item_id)).get().to_dict()
    assert row['state'] == 'offered'
    assert store.remaining_today(UID) == 3
    assert proposal(item_id).get().to_dict()['status'] == 'pending'
    assert client.get('/v2/review/items').json()['items'][0]['item_id'] == item_id


@pytest.mark.parametrize('decision', ['yes', 'no'])
def test_dream_staging_key_becomes_a_matching_review_id_and_answers_work(harness, monkeypatch, decision):
    client, _ = harness
    item = HarnessQuestion(
        kind='same_person',
        title='Same person?',
        quote='Synthetic quote',
        source_ref='conversations/toy#s1',
        same_person=question().same_person,
        value=4,
        why_it_matters='Resolve a duplicated identity',
    )
    assert staging.question_key(item).startswith('agent:question:')
    records = {'conversations/toy': {'transcript_segments': [{'id': 's1', 'text': item.quote}]}}
    dream_review_policy.ask(UID, item, records)
    items = client.get('/v2/review/items').json()['items']
    item_id = items[0]['item_id']
    assert item_id == store.dream_question_item_id(UID, item.kind, item.source_ref, item.quote)
    merge = Mock()
    monkeypatch.setattr(review_changes, 'merge_review_entities', merge)
    response = answer(client, item_id, decision)
    assert response.status_code == 200, response.text
    assert response.json()['applied'] is (decision == 'yes')
    assert merge.call_count == (1 if decision == 'yes' else 0)
    assert proposal(item_id).get().to_dict()['status'] == 'resolved'
    assert client.get('/v2/review/items').json()['items'] == []


def test_wrong_request_kind_does_not_retire_a_valid_question(harness):
    client, _ = harness
    item_id = offer(client)
    response = client.post(f'/v2/review/items/{item_id}/answer', json={'spelling': {'value': 'Sam'}})
    assert response.status_code == 409
    assert proposal(item_id).get().to_dict()['status'] == 'pending'
    assert store.remaining_today(UID) == 3


def test_new_proposal_version_survives_stale_settlement(harness):
    client, _ = harness
    item_id = offer(client)
    state = store.begin_answer(UID, item_id, 'synthetic-hash')
    store.enqueue_review_proposal(UID, question(), evidence_version='v2')
    store.finish_answer(UID, item_id, applied=False, uncertain=False, offered_version=state['version'], stale=True)
    assert proposal(item_id).get().to_dict()['status'] == 'pending'
    assert client.get('/v2/review/items').json()['items'][0]['item_id'] == item_id


@pytest.mark.parametrize('spelling', [False, True])
def test_dream_answer_wrapper_preserves_transient_fences(monkeypatch, spelling):
    source = {
        'spelling_edit': {
            'kind': 'spelling',
            'target': 'conversations/toy#s1',
            'before': 'Sam',
            'after': 'Samuel',
            'reason': 'Name spelling',
            'evidence': ['conversations/toy#s1'],
        }
    }
    monkeypatch.setattr(tools, 'revalidate_proposal', lambda *a: {})
    conflict = store.ReviewConflict('Dream proposal evidence changed during apply')
    monkeypatch.setattr(tools, 'apply_edit', Mock(side_effect=conflict))
    with pytest.raises(store.ReviewConflict) as caught:
        if spelling:
            tools.answer_spelling(UID, source, 'Samuel')
        else:
            tools.answer_proposal(UID, SimpleNamespace(operation=object()), source, 'accept')
    assert caught.value is conflict
    assert not isinstance(caught.value, store.ReviewStale)


def test_dream_evidence_change_is_stale_and_evidence_read_conflict_stays_transient(monkeypatch):
    monkeypatch.setattr(tools, 'proposal_record', lambda *a: {'text': 'new'})
    with pytest.raises(store.ReviewStale, match='evidence changed'):
        tools.revalidate_proposal(UID, {'records': {'conversations/toy': {'text': 'old'}}})
    conflict = store.ReviewConflict('dream_lease_lost')
    monkeypatch.setattr(tools, 'proposal_record', Mock(side_effect=conflict))
    with pytest.raises(store.ReviewConflict) as caught:
        tools.revalidate_proposal(UID, {'records': {'conversations/toy': {}}})
    assert caught.value is conflict


@pytest.mark.parametrize('status', [402, 404])
def test_dream_temporary_access_denial_is_retryable_but_missing_evidence_is_stale(monkeypatch, status):
    monkeypatch.setattr(tools, 'proposal_record', Mock(side_effect=HTTPException(status_code=status)))
    with pytest.raises(store.ReviewConflict) as caught:
        tools.revalidate_proposal(UID, {'records': {'conversations/toy': {}}})
    assert isinstance(caught.value, store.ReviewStale) is (status == 404)
