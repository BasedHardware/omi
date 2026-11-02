"""Stale Review questions settle durably; transactional races stay retryable."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from database import review_store as store, review_changes, task_intelligence_control
from models.agent_tools import HarnessQuestion
from models.review import AgentProposalItem, EntitySummary, ReviewItem, ReviewItemV2, SamePersonItem
from models.dream_edit import Term
from models.memories import MemoryDB
from models.product_memory import MemoryItem
from utils.memory import canonical_memory_adapter
from routers import review as router
from tests.support.dream_firestore import DreamFirestore
from utils import dream_review_policy, entity_pages, review
from utils.agent_capabilities import reads, staging, tools
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


@pytest.mark.parametrize('failure', ['same_node_no', 'types', 'kind', 'redirect_cycle'])
def test_deterministic_conflicts_retire_and_refund_attention(harness, failure):
    client, db = harness
    item_id = offer(client)
    if failure in {'same_node_no', 'redirect_cycle'}:
        store.user(UID).collection('knowledge_nodes').document('person:b').set({'redirect_entity_id': 'person:a'})
        if failure == 'redirect_cycle':
            store.user(UID).collection('knowledge_nodes').document('person:a').set({'redirect_entity_id': 'person:b'})
    elif failure == 'types':
        store.user(UID).collection('knowledge_nodes').document('person:b').set({'redirect_entity_id': 'org'})
        store.user(UID).collection('knowledge_nodes').document('org').set({'node_type': 'organization', 'label': 'Org'})
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


def test_dream_evidence_change_and_read_conflict_release_by_default(monkeypatch):
    monkeypatch.setattr(tools, 'proposal_record', lambda *a: {'text': 'new'})
    with pytest.raises(store.ReviewConflict, match='evidence changed') as changed:
        tools.revalidate_proposal(UID, {'records': {'conversations/toy': {'text': 'old'}}})
    assert not isinstance(changed.value, store.ReviewStale)
    conflict = store.ReviewConflict('dream_lease_lost')
    monkeypatch.setattr(tools, 'proposal_record', Mock(side_effect=conflict))
    with pytest.raises(store.ReviewConflict) as caught:
        tools.revalidate_proposal(UID, {'records': {'conversations/toy': {}}})
    assert caught.value is conflict


@pytest.mark.parametrize('status', [402, 404, 423, 503])
def test_dream_temporary_access_denial_is_retryable_but_missing_evidence_is_stale(monkeypatch, status):
    monkeypatch.setattr(tools, 'proposal_record', Mock(side_effect=HTTPException(status_code=status)))
    with pytest.raises(store.ReviewConflict) as caught:
        tools.revalidate_proposal(UID, {'records': {'conversations/toy': {}}})
    assert isinstance(caught.value, store.ReviewStale) is (status == 404)


def offer_vocabulary(client, records, *, auxiliary=None):
    item = ReviewItemV2(
        item_id='agent_proposal:availability',
        kind='agent_proposal',
        title='Add vocabulary?',
        created_at=NOW,
        agent_proposal=AgentProposalItem(
            vocabulary=Term(kind='person', spelling='Zarathion', evidence=list(records)),
        ),
    )
    store.enqueue_review_proposal(
        UID,
        item,
        evidence_version='v1',
        edit_key='agent:availability',
        source={'records': records, 'edit_key': 'agent:availability', 'auxiliary': auxiliary or {}},
    )
    assert client.get('/v2/review/items').json()['items'][0]['item_id'] == item.item_id
    return item.item_id


def accept_vocabulary(client, item_id):
    return client.post(f'/v2/review/items/{item_id}/answer', json={'agent_proposal': {'decision': 'accept'}})


def assert_released(client, item_id):
    state = store.user(UID).collection('review_answers').document(store.safe_id(item_id)).get().to_dict()
    assert state['state'] == 'offered'
    assert proposal(item_id).get().to_dict()['status'] == 'pending'
    assert store.remaining_today(UID) == 3
    assert client.get('/v2/review/items').json()['items'][0]['item_id'] == item_id


@pytest.mark.parametrize('lock', ['paywall', 'locked_row'])
def test_memory_lock_releases_through_real_reader_and_upgrade_allows_same_answer(harness, monkeypatch, lock):
    client, _ = harness
    memory = MemoryDB(
        id='toy',
        uid=UID,
        content='Zarathion is a person',
        category='core',
        created_at=NOW,
        updated_at=NOW,
        visibility='private',
        user_review=True,
    )
    locked = False
    monkeypatch.setattr(reads, 'read_canonical_memory_item', lambda *a, **kw: None)

    def fetch(self, uid, key):
        assert (uid, key) == (UID, 'toy')
        if locked and lock == 'paywall':
            raise HTTPException(402, 'Paid plan required')
        return memory.model_copy(update={'is_locked': locked})

    monkeypatch.setattr(reads.MemoryService, 'fetch', fetch)
    # Both snapshot and revalidation use read_record -> _read_memory_record.
    item_id = offer_vocabulary(client, {'memory_items/toy': reads.read_record(UID, 'memory_items/toy')})
    locked = True
    response = accept_vocabulary(client, item_id)
    assert response.status_code == 409, response.text
    assert_released(client, item_id)
    locked = False  # Same evidence is accessible again after the upgrade.
    response = accept_vocabulary(client, item_id)
    assert response.status_code == 200, response.text
    assert response.json()['applied'] is True
    assert proposal(item_id).get().to_dict()['status'] == 'resolved'
    assert client.get('/v2/review/items').json()['items'] == []


@pytest.mark.parametrize('condition', ['discarded', 'is_locked', 'deleted', 'missing', 'decode_failed'])
def test_conversation_availability_uses_real_reader_and_refunds_reservation(harness, monkeypatch, condition):
    client, _ = harness
    row = {'id': 'toy', 'transcript_segments': [], 'structured': {'title': 'Zarathion'}}
    monkeypatch.setattr(reads.conversations, 'get_conversation_raw_snapshot', lambda *a: row.copy())

    def decode(*args):
        if row.get('decode_failed'):
            raise ValueError('Synthetic transcript decode failure')
        return []

    monkeypatch.setattr(reads.conversations, 'decode_transcript_segments_verified', decode)
    monkeypatch.setattr(reads.conversations, 'prepare_conversation_for_read', lambda raw, uid: raw)
    item_id = offer_vocabulary(client, {'conversations/toy': reads.read_record(UID, 'conversations/toy')})
    if condition == 'missing':
        row.clear()
    else:
        row[condition] = True
    if condition == 'is_locked':
        with pytest.raises(HTTPException) as caught:
            reads.read_record(UID, 'conversations/toy')
        assert caught.value.status_code == 423
    response = accept_vocabulary(client, item_id)
    assert response.status_code == 409, response.text
    if condition in {'deleted', 'missing'}:
        assert proposal(item_id).get().to_dict()['resolution'] == 'stale'
        assert client.get('/v2/review/items').json()['items'] == []
        assert store.remaining_today(UID) == 3
    else:
        assert_released(client, item_id)
        row.pop(condition)
        response = accept_vocabulary(client, item_id)
        assert response.status_code == 200, response.text
        assert response.json()['applied'] is True


def test_vocabulary_capacity_releases_and_same_answer_succeeds_after_removing_a_term(harness):
    client, _ = harness
    item_id = offer_vocabulary(client, {'people/a': reads.read_record(UID, 'people/a')})
    vocabulary = store.user(UID).collection('dream_vocabulary').document('current')
    rows = [{'spelling': f'Synthetic-{i}'} for i in range(500)]
    vocabulary.set(store.encode_doc(UID, {'source': rows}))
    response = accept_vocabulary(client, item_id)
    assert response.status_code == 409, response.text
    assert response.json()['detail'] == 'agent_vocabulary_cap'
    assert_released(client, item_id)
    vocabulary.set(store.encode_doc(UID, {'source': rows[:-1]}))
    response = accept_vocabulary(client, item_id)
    assert response.status_code == 200, response.text
    assert response.json()['applied'] is True
    assert proposal(item_id).get().to_dict()['status'] == 'resolved'


@pytest.mark.parametrize(
    'condition',
    [
        'deleted',
        'tombstoned',
        'hidden',
        'source_tombstoned',
        'source_purged',
        'archive',
        'user_rejected',
        'chat_deleted',
        'restricted',
        'public',
        'shared',
        'valid_to',
        'processing_pending',
        'processing_blocked',
        'locked',
        'superseded',
        'content_changed',
    ],
)
def test_canonical_memory_unavailability_settles_only_terminal_reasons(harness, monkeypatch, condition):
    client, db = harness
    monkeypatch.setattr(canonical_memory_adapter, 'default_db_client', db)
    memory = MemoryItem(
        memory_id='toy',
        uid=UID,
        version=1,
        tier='short_term',
        status='active',
        processing_state='processed',
        content='Zarathion is a person',
        source_state='active',
        sensitivity_labels=[],
        visibility='private',
        user_asserted=True,
        captured_at=NOW,
        updated_at=NOW,
        expires_at=NOW + timedelta(days=2),
    )
    ref = store.user(UID).collection('memory_items').document('toy')
    ref.set(memory.model_dump(mode='python'))
    # Real canonical read, default visibility filter, adapter and Review HTTP lifecycle.
    snapshot = reads.read_record(UID, 'memory_items/toy')
    assert snapshot is not None
    item_id = offer_vocabulary(client, {'memory_items/toy': snapshot})
    changed = {
        'deleted': {},
        'tombstoned': {'status': 'tombstoned'},
        'hidden': {'status': 'hidden'},
        'source_tombstoned': {'source_state': 'tombstoned'},
        'source_purged': {'source_state': 'purged'},
        'chat_deleted': {'promotion': {'chat_deleted': True}},
        'restricted': {'sensitivity_labels': ['health']},
        'public': {'visibility': 'public'},
        'shared': {'visibility': 'shared'},
        'valid_to': {'valid_to': NOW + timedelta(days=1)},
        'processing_blocked': {'processing_state': 'blocked'},
        'superseded': {'status': 'superseded'},
        'content_changed': {'content': 'New evidence about Zarathion'},
        'archive': {'tier': 'archive'},
        'user_rejected': {'promotion': {'user_review': False}},
        'locked': {'promotion': {'is_locked': True}},
        'processing_pending': {'processing_state': 'pending'},
    }[condition]
    # The only legacy fallback is a genuinely absent canonical item; its owner
    # fetch reports missing. The canonical reader/filter/adapter stay real.
    legacy_fetch = Mock(side_effect=HTTPException(404, 'Memory not found'))
    monkeypatch.setattr(reads.MemoryService, 'fetch', legacy_fetch)
    if condition == 'deleted':
        ref.delete()
    else:
        ref.set({**memory.model_dump(mode='python'), **changed})
    if condition in {'tombstoned', 'hidden', 'superseded'}:
        assert canonical_memory_adapter.read_canonical_memory_item(UID, 'toy') is None
    response = accept_vocabulary(client, item_id)
    assert response.status_code == 409, response.text
    assert legacy_fetch.call_count == (1 if condition == 'deleted' else 0)
    if condition in {
        'deleted',
        'tombstoned',
        'hidden',
        'source_tombstoned',
        'source_purged',
        'archive',
        'user_rejected',
    }:
        assert proposal(item_id).get().to_dict()['status'] == 'resolved'
        assert proposal(item_id).get().to_dict()['resolution'] == 'stale'
        assert store.remaining_today(UID) == 3
        assert client.get('/v2/review/items').json()['items'] == []
    else:
        assert_released(client, item_id)
        ref.set(memory.model_dump(mode='python'))
        response = accept_vocabulary(client, item_id)
        assert response.status_code == 200, response.text
        assert response.json()['applied'] is True


@pytest.mark.parametrize('condition', ['user_rejected', 'public', 'shared', 'valid_to'])
def test_legacy_memory_row_gate_releases_unless_user_rejected(harness, monkeypatch, condition):
    client, _ = harness
    memory = MemoryDB(
        id='toy',
        uid=UID,
        content='Zarathion is a person',
        category='core',
        created_at=NOW,
        updated_at=NOW,
        visibility='private',
        user_review=True,
    )
    current = memory
    monkeypatch.setattr(reads, 'read_canonical_memory_item', lambda *a, **kw: None)
    monkeypatch.setattr(reads.MemoryService, 'fetch', lambda *a: current)
    item_id = offer_vocabulary(client, {'memories/toy': reads.read_record(UID, 'memories/toy')})
    changes = {
        'user_rejected': {'user_review': False},
        'public': {'visibility': 'public'},
        'shared': {'visibility': 'shared'},
        'valid_to': {'invalid_at': NOW + timedelta(days=1)},
    }[condition]
    current = memory.model_copy(update=changes)
    response = accept_vocabulary(client, item_id)
    assert response.status_code == 409, response.text
    if condition == 'user_rejected':
        assert proposal(item_id).get().to_dict()['resolution'] == 'stale'
        assert client.get('/v2/review/items').json()['items'] == []
        assert store.remaining_today(UID) == 3
    else:
        assert_released(client, item_id)
        current = memory
        response = accept_vocabulary(client, item_id)
        assert response.status_code == 200, response.text
        assert response.json()['applied'] is True


def test_suppression_conflict_is_not_on_the_terminal_allowlist(harness):
    client, _ = harness
    item_id = offer(client)
    store.user(UID).collection('review_do_not_redo').document(store.safe_id('merge:person:a:person:b')).set(
        {'blocked': True}
    )
    response = answer(client, item_id)
    assert response.status_code == 409, response.text
    assert_released(client, item_id)


def test_auxiliary_snapshot_change_releases_instead_of_retiring(harness):
    client, _ = harness
    item_id = offer_vocabulary(
        client,
        {'people/a': reads.read_record(UID, 'people/a')},
        auxiliary={'dream_vocabulary/current': None},
    )
    target = store.user(UID).collection('dream_vocabulary').document('current')
    target.set(store.encode_doc(UID, {'source': []}))
    response = accept_vocabulary(client, item_id)
    assert response.status_code == 409, response.text
    assert_released(client, item_id)
    target.delete()
    response = accept_vocabulary(client, item_id)
    assert response.status_code == 200, response.text
    assert response.json()['applied'] is True


def test_missing_entity_is_not_on_the_terminal_allowlist(harness):
    client, _ = harness
    item_id = offer(client)
    store.user(UID).collection('people').document('b').delete()
    response = answer(client, item_id)
    assert response.status_code == 409, response.text
    assert_released(client, item_id)
