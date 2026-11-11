from utils import dream_review_policy

"""Review endpoints through FastAPI and real loopback Firestore transactions."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import os
from unittest.mock import Mock
from urllib.parse import urlparse
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
from google.auth.credentials import AnonymousCredentials
from google.cloud import firestore
import pytest

from database import _client, review_changes as journal, review_store as store
from models.review import (
    EntitySummary,
    ReviewAnswer,
    ReviewChange,
    ReviewItem,
    ReviewItemV2,
    SamePersonItem,
    SpellingItem,
)
from routers import review as router
from utils import entity_pages, review

pytestmark = pytest.mark.integration
NOW = datetime.now(timezone.utc)


def spelling(index=1):
    return ReviewItem(
        item_id=f'spelling:{index}',
        kind='spelling',
        title='Which spelling?',
        created_at=NOW,
        spelling=SpellingItem(term_id=str(index), options=['Pairform', 'Paraform'], allow_custom=True),
    )


@pytest.fixture
def harness(monkeypatch):
    host = os.environ.get('FIRESTORE_EMULATOR_HOST', '')
    if urlparse(f'//{host}').hostname not in {'127.0.0.1', 'localhost', '::1'}:
        pytest.fail('Loopback Firestore emulator is required')
    db = firestore.Client(project='demo-review', credentials=AnonymousCredentials())
    monkeypatch.setattr(_client, '_firestore_client', db)
    monkeypatch.setenv('REVIEW_SURFACE_MODE', 'on')
    uid = uuid4().hex
    user = db.collection('users').document(uid)
    user.set({'data_protection_level': 'standard'})
    user.collection('task_intelligence_control').document('state').set({'account_generation': 3})
    monkeypatch.setattr(review.speakers, 'get_prompts', lambda uid: type('Prompts', (), {'prompts': []})())
    monkeypatch.setattr(review.candidates, 'list_candidates', lambda *a, **k: [])
    app = FastAPI()
    app.include_router(router.router)
    app.dependency_overrides[router.auth.get_current_user_uid] = lambda: uid
    with TestClient(app) as client:
        yield client, uid, user, db
    db.close()


def enqueue(uid, item=None, version='v1'):
    store.enqueue_review_proposal(uid, item or spelling(), evidence_version=version)


def test_default_off_gate_blocks_every_route(harness, monkeypatch):
    client, uid, user, db = harness
    monkeypatch.delenv('REVIEW_SURFACE_MODE')
    for method, path, body in [
        ('get', '/v1/review/items', None),
        ('get', '/v2/review/items', None),
        ('post', '/v2/review/items/item/answer', {'not_sure': True}),
        ('get', '/v1/review/changes', None),
        ('post', '/v1/review/items/spelling:1/answer', {'not_sure': True}),
        ('post', '/v1/review/changes/x/undo', None),
        ('post', '/v1/review/changes/x/redo', None),
        ('get', '/v1/entities?type=project', None),
        ('get', '/v1/entities/org/page', None),
        ('post', '/v1/entities/org/corrections', {'text': 'Changed'}),
        ('get', '/v1/conversations/c/entities', None),
    ]:
        response = client.request(method, path, json=body)
        assert response.status_code == 404, response.text
        assert response.json()['detail'] == 'review_surface_disabled'


def test_proposals_not_sure_retry_and_new_evidence(harness):
    client, uid, user, db = harness
    assert client.get('/v1/review/items').json() == {'items': [], 'remaining_today': 3}
    enqueue(uid)
    response = client.get('/v1/review/items')
    assert response.status_code == 200, response.text
    assert response.json()['items'][0]['item_id'] == 'spelling:1'
    answer = client.post('/v1/review/items/spelling:1/answer', json={'not_sure': True})
    assert answer.json() == {'item_id': 'spelling:1', 'applied': False, 'remaining_today': 2}
    assert client.post('/v1/review/items/spelling:1/answer', json={'not_sure': True}).json() == answer.json()
    assert client.get('/v1/review/items').json()['items'] == []
    enqueue(uid)  # unchanged producer replay cannot re-ask
    assert client.get('/v1/review/items').json()['items'] == []
    enqueue(uid, version='v2')
    assert len(client.get('/v1/review/items').json()['items']) == 1
    assert client.post('/v1/review/items/spelling:1/answer', json={'not_sure': True}).json()['remaining_today'] == 1


def test_new_evidence_enqueued_during_answer_stays_pending(harness):
    client, uid, user, db = harness
    enqueue(uid, version='v1')
    assert client.get('/v1/review/items').json()['items'][0]['item_id'] == 'spelling:1'
    state = store.begin_answer(uid, 'spelling:1', 'answer-v1', now=NOW)

    refreshed = spelling()
    refreshed.title = 'Confirm the updated spelling?'
    enqueue(uid, item=refreshed, version='v2')
    store.finish_answer(uid, 'spelling:1', applied=True, uncertain=False, offered_version=state['version'])

    proposal = store.require_doc(
        uid, user.collection('review_proposals').document(store.safe_id('spelling:1')).get().to_dict()
    )
    assert proposal['evidence_version'] == 'v2'
    assert proposal['status'] == 'pending'
    items = client.get('/v1/review/items').json()['items']
    assert [(item['item_id'], item['title']) for item in items] == [('spelling:1', 'Confirm the updated spelling?')]


def test_attention_budget_concurrency_and_day_rollover(harness):
    _, uid, _, _ = harness
    for i in range(5):
        store.offer_item(uid, spelling(i), {}, 'v1')

    def answer(i):
        try:
            store.begin_answer(uid, f'spelling:{i}', 'hash', now=NOW)
            return True
        except store.ReviewConflict:
            return False

    with ThreadPoolExecutor(max_workers=5) as pool:
        results = list(pool.map(answer, range(5)))
    assert sum(results) == 3
    assert store.remaining_today(uid, NOW) == 0
    assert store.remaining_today(uid, NOW + timedelta(days=1)) == 3


def test_owner_scope_and_encryption(harness):
    client, uid, user, db = harness
    enqueue('other-user')
    assert client.get('/v1/review/items').json()['items'] == []
    assert client.post('/v1/review/items/spelling:1/answer', json={'not_sure': True}).status_code == 404
    enqueue(uid)
    raw = user.collection('review_proposals').document(store.safe_id('spelling:1')).get().to_dict()
    assert 'Pairform' not in str(raw)
    assert store.decode_doc(uid, raw)['item']['spelling']['options'] == ['Pairform', 'Paraform']
    with pytest.raises(Exception):
        store.decode_doc('wrong-user', raw)


@pytest.mark.parametrize(
    'kind,collection,before,after',
    [
        ('rename', 'knowledge_nodes', {'label': 'Pairform'}, {'label': 'Paraform'}),
        ('update_person', 'people', {'name': 'Sam'}, {'name': 'Samuel'}),
        ('title_conversation', 'conversations', {'user_title': 'Before'}, {'user_title': 'After'}),
        (
            'label_speaker',
            'conversations',
            {'transcript_segments': [{'id': 's', 'person_id': None}]},
            {'transcript_segments': [{'id': 's', 'person_id': 'p'}]},
        ),
        (
            'close_task',
            'action_items',
            {'completed': False, 'status': 'active'},
            {'completed': True, 'status': 'completed'},
        ),
    ],
)
def test_journal_reverses_underlying_edit_and_suppresses_agent(harness, kind, collection, before, after):
    client, uid, user, db = harness
    target = user.collection(collection).document('target')
    target.set(before | {'unrelated': 'preserve'})
    change = ReviewChange(change_id='change', kind=kind, title='An edit', created_at=NOW)
    edits = [journal.AgentEdit(collection=collection, document_id='target', patch=after)]
    journal.record_agent_change(uid, change, edits, edit_key='stable-operation')
    assert target.get().to_dict() == after | {'unrelated': 'preserve'}
    assert client.get('/v1/review/changes').json()['changes'][0]['undone'] is False
    undo = client.post('/v1/review/changes/change/undo')
    assert undo.status_code == 200, undo.text
    assert target.get().to_dict() == before | {'unrelated': 'preserve'}
    assert not journal.agent_change_allowed(uid, 'stable-operation')
    assert client.post('/v1/review/changes/change/undo').status_code == 200
    assert client.post('/v1/review/changes/change/redo').json()['undone'] is False
    assert target.get().to_dict() == after | {'unrelated': 'preserve'}
    assert not journal.agent_change_allowed(uid, 'stable-operation')  # explicit redo does not lift the marker
    other = change.model_copy(update={'change_id': 'another'})
    with pytest.raises(store.ReviewConflict):
        journal.record_agent_change(uid, other, edits, edit_key='stable-operation')
    assert len(list(user.collection('memory_commits').stream())) >= 3


def test_undo_conflict_expiry_and_pagination(harness):
    client, uid, user, db = harness
    target = user.collection('people').document('p')
    target.set({'name': 'Before'})
    change = ReviewChange(change_id='change', kind='update_person', title='Rename', created_at=NOW)
    journal.record_agent_change(
        uid,
        change,
        [journal.AgentEdit(collection='people', document_id='p', patch={'name': 'After'})],
        edit_key='rename-p',
    )
    target.update({'name': 'User edit'})
    assert client.post('/v1/review/changes/change/undo').status_code == 409
    assert target.get().to_dict()['name'] == 'User edit'
    with pytest.raises(store.ReviewNotFound):
        journal.set_undone(uid, 'change', True, now=NOW + timedelta(days=31))
    for i in range(31):
        row = ReviewChange(change_id=f'row-{i}', kind='other', title='Change', created_at=NOW + timedelta(seconds=i))
        user.collection('review_changes').document(store.safe_id(row.change_id)).set(
            store.encode_doc(uid, {'change': row.model_dump(mode='python'), 'created_at': row.created_at})
        )
    first = client.get('/v1/review/changes').json()
    assert len(first['changes']) == 30 and first['next_cursor']
    second = client.get('/v1/review/changes', params={'cursor': first['next_cursor']}).json()
    assert len(second['changes']) == 2
    assert not {c['change_id'] for c in first['changes']}.intersection(c['change_id'] for c in second['changes'])


def test_merge_answer_and_undo_redo(harness, monkeypatch):
    client, uid, user, db = harness
    for person, label in [('a', 'Sam'), ('b', 'Samuel')]:
        user.collection('knowledge_nodes').document(f'person:{person}').set(
            {'id': f'person:{person}', 'label': label, 'node_type': 'person', 'aliases': []}
        )
    monkeypatch.setattr(entity_pages.users, 'get_person', lambda uid, pid: {'name': {'a': 'Sam', 'b': 'Samuel'}[pid]})
    left = EntitySummary(entity_id='person:a', type='person', name='Sam')
    right = EntitySummary(entity_id='person:b', type='person', name='Samuel')
    item = ReviewItem(
        item_id='same_person:ab',
        kind='same_person',
        title='Same person?',
        created_at=NOW,
        same_person=SamePersonItem(left=left, right=right, reason='Same voice'),
    )
    enqueue(uid, item)
    client.get('/v1/review/items')
    answer = client.post('/v1/review/items/same_person:ab/answer', json={'same_person': {'decision': 'yes'}})
    assert answer.status_code == 200, answer.text
    assert answer.json()['applied'] is True
    assert entity_pages.resolve_entity(uid, 'person:b')['entity_id'] == 'person:a'
    change = client.get('/v1/review/changes').json()['changes'][0]
    assert client.post(f'/v1/review/changes/{change["change_id"]}/undo').status_code == 200
    assert entity_pages.resolve_entity(uid, 'person:b')['entity_id'] == 'person:b'
    assert client.post(f'/v1/review/changes/{change["change_id"]}/redo').status_code == 200
    assert entity_pages.resolve_entity(uid, 'person:b')['entity_id'] == 'person:a'


def test_spelling_delegates_canonical_fact_once(harness, monkeypatch):
    client, uid, user, db = harness
    writer = Mock(return_value='fact')
    monkeypatch.setattr(entity_pages, 'save_user_fact', writer)
    enqueue(uid)
    client.get('/v1/review/items')
    body = {'spelling': {'value': 'Paraform'}}
    assert client.post('/v1/review/items/spelling:1/answer', json=body).json()['applied'] is True
    assert client.post('/v1/review/items/spelling:1/answer', json=body).status_code == 200
    writer.assert_called_once()
    assert writer.call_args.args == (uid, 'vocabulary:1', 'Paraform')
    assert client.get('/v1/review/items').json()['items'] == []


def test_entity_pages_projects_chips_and_cache(harness, monkeypatch):
    client, uid, user, db = harness
    user.collection('knowledge_nodes').document('org').set(
        {'id': 'org', 'node_type': 'organization', 'label': 'Paraform'}
    )
    user.collection('knowledge_nodes').document('person:p').set(
        {'id': 'person:p', 'node_type': 'person', 'label': 'Sam'}
    )
    user.collection('workstreams').document('project').set({'title': 'Partner launch', 'account_generation': 3})
    user.collection('knowledge_edges').document('edge').set(
        {'source_id': 'org', 'target_id': 'person:p', 'label': 'member'}
    )
    user.collection('knowledge_edges').document('project-edge').set(
        {'source_id': 'org', 'target_id': 'project', 'label': 'project'}
    )
    monkeypatch.setattr(entity_pages.users, 'get_person', lambda uid, pid: {'name': 'Sam', 'role': 'Partnerships'})
    conversation = {
        'id': 'c',
        'created_at': NOW,
        'started_at': NOW,
        'finished_at': NOW + timedelta(seconds=60),
        'structured': {'title': 'Launch planning'},
        'transcript_segments': [{'person_id': 'p'}],
        'entity_ids': ['org', 'project'],
    }
    monkeypatch.setattr(entity_pages.conversations, 'get_conversation', lambda uid, cid: conversation)
    monkeypatch.setattr(entity_pages.conversations, 'get_conversations', lambda uid, **k: [conversation])
    from database import memories

    monkeypatch.setattr(memories, 'get_memory_ids_for_conversation', lambda *a: [])
    page = client.get('/v1/entities/org/page')
    assert page.status_code == 200, page.text
    assert page.json()['summary'] is None
    assert page.json()['people'] == [{'entity_id': 'person:p', 'type': 'person', 'name': 'Sam'}]
    assert page.json()['projects'] == [{'entity_id': 'project', 'type': 'project', 'name': 'Partner launch'}]
    entity_pages.write_entity_summary(uid, 'org', 'A hiring partner', updated_at=NOW)
    page = client.get('/v1/entities/org/page').json()
    assert page['summary'] == 'A hiring partner' and page['summary_updated_at']
    assert 'A hiring partner' not in str(user.collection('entity_pages').document('org').get().to_dict())
    assert client.get('/v1/entities?type=project').json()['entities'][0]['entity_id'] == 'project'
    chips = client.get('/v1/conversations/c/entities').json()['entities']
    assert [ref['type'] for ref in chips] == ['organization', 'project', 'person']
    assert client.get('/v1/entities/missing/page').status_code == 404


def _billed_read_total():
    from database.firestore_document_probe import FIRESTORE_BILLED_READS

    return sum(sample.value for metric in FIRESTORE_BILLED_READS.collect() for sample in metric.samples)


def test_entity_page_large_project_and_conversation_pages_stay_within_read_budget(harness):
    client, uid, user, db = harness
    # Document-read budget: each of these entity-page requests must stay at or
    # below 250 billed-equivalent Firestore reads with 100 related source rows.
    # This leaves headroom for auth-independent page metadata while catching
    # duplicate per-task/per-conversation point reads.
    read_bound = 250
    user.collection('workstreams').document('project').set(
        {'title': 'Launch', 'objective': 'Ship launch', 'status': 'open', 'account_generation': 3}
    )
    user.collection('knowledge_nodes').document('org').set(
        {'id': 'org', 'node_type': 'organization', 'label': 'Partner'}
    )
    for index in range(100):
        created_at = NOW - timedelta(seconds=index)
        user.collection('action_items').document(f'task-{index:03}').set(
            {
                'description': f'Task {index}',
                'status': 'active',
                'completed': False,
                'created_at': created_at,
                'account_generation': 3,
                'workstream_id': 'project',
            }
        )
        user.collection('conversations').document(f'conversation-{index:03}').set(
            {
                'created_at': created_at,
                'started_at': created_at,
                'finished_at': created_at + timedelta(minutes=1),
                'status': 'completed',
                'discarded': False,
                'data_protection_level': 'standard',
                'structured': {'title': f'Meeting {index}'},
                'entity_ids': ['project', 'org'],
                'workstream_id': 'project',
                'transcript_segments': [],
            }
        )

    before = _billed_read_total()
    project_page = client.get('/v1/entities/project/page')
    project_reads = _billed_read_total() - before
    assert project_page.status_code == 200, project_page.text
    assert len(project_page.json()['open_tasks']) == 30
    assert project_reads <= read_bound, f'project page used {project_reads} reads (budget {read_bound})'

    before = _billed_read_total()
    org_page = client.get('/v1/entities/org/page')
    conversation_reads = _billed_read_total() - before
    assert org_page.status_code == 200, org_page.text
    assert len(org_page.json()['recent_conversations']) == 10
    assert (
        conversation_reads <= read_bound
    ), f'entity page with 100 conversations used {conversation_reads} reads (budget {read_bound})'


def test_entity_page_keeps_pending_canonical_facts_hidden(harness):
    client, uid, user, db = harness
    from models.memory_evidence import ArtifactPreservationState, MemoryEvidence, SourceState
    from models.product_memory import MemoryItem, MemoryItemStatus, MemorySubjectScope, MemoryTier, ProcessingState

    _canonical_control(user, uid)
    user.collection('knowledge_nodes').document('org').set(
        {'id': 'org', 'node_type': 'organization', 'label': 'Partner'}
    )
    pending = MemoryItem(
        memory_id='pending-fact',
        uid=uid,
        version=1,
        tier=MemoryTier.short_term,
        status=MemoryItemStatus.active,
        processing_state=ProcessingState.pending,
        content='Still being processed',
        source_state=SourceState.active,
        evidence=[
            MemoryEvidence(
                evidence_id='pending-source',
                source_type='explicit_user',
                source_id='pending-source',
                source_version='1',
                artifact_preservation=ArtifactPreservationState.not_applicable,
            )
        ],
        sensitivity_labels=[],
        visibility='private',
        user_asserted=False,
        captured_at=NOW,
        updated_at=NOW,
        expires_at=NOW + timedelta(days=30),
        subject_entity_id='org',
        subject_scope=MemorySubjectScope.third_party,
    )
    user.collection('memory_items').document(pending.memory_id).set(pending.model_dump(mode='json'))

    page = client.get('/v1/entities/org/page')
    assert page.status_code == 200, page.text
    assert page.json()['facts'] == []


def _canonical_control(user, uid):
    from models.memory_apply import MemoryControlState, WriterMode

    control = MemoryControlState(
        uid=uid,
        account_generation=3,
        source_generation=1,
        head_commit_id='review-seed-head',
        writer_mode=WriterMode.ledger,
        writer_epoch=1,
        commit_sequence=0,
        updated_at=NOW,
    )
    user.collection('memory_state').document('apply_control').set(control.model_dump(mode='json'))


def test_correction_uses_real_ledger_authority_and_page_fact(harness, monkeypatch):
    client, uid, user, db = harness
    _canonical_control(user, uid)
    user.collection('knowledge_nodes').document('org').set(
        {'id': 'org', 'node_type': 'organization', 'label': 'Paraform'}
    )
    monkeypatch.setattr(entity_pages.conversations, 'get_conversations', lambda *a, **k: [])
    response = client.post('/v1/entities/org/corrections', json={'text': 'Paraform is our hiring partner.'})
    assert response.status_code == 204, response.text
    rows = list(user.collection('memory_items').stream())
    assert len(rows) == 1
    item = rows[0].to_dict()
    assert item['subject_entity_id'] == 'org'
    from models.knowledge_ledger_policy import ledger_authority_rank

    assert item['write_reason'] == 'direct_user_statement' and ledger_authority_rank(item['write_reason']) == 600
    assert list(user.collection('memory_commits').stream())
    page = client.get('/v1/entities/org/page')
    assert page.status_code == 200, page.text
    assert page.json()['facts'][0]['text'] == 'Paraform is our hiring partner.'
    assert page.json()['facts'][0]['source']['kind'] == 'user'
    assert client.post('/v1/entities/org/corrections', json={'text': ' '}).status_code == 422


@pytest.mark.parametrize('intervening_correction', [False, True])
def test_canonical_memory_journal_reverses_real_fact(harness, monkeypatch, intervening_correction):
    client, uid, user, db = harness
    _canonical_control(user, uid)
    from database.review_memory_changes import MemoryEdit
    from models.product_memory import LedgerWriteReason, MemorySubjectScope
    from utils.memory.knowledge_ledger import LedgerProvenance, save_fact

    source = save_fact(
        uid,
        'Partner name is Pairform',
        provenance=LedgerProvenance(source_id='agent-test', source_type='agent_conclusion', action_id='seed'),
        write_reason=LedgerWriteReason.agent_reusable_conclusion,
        subject_scope=MemorySubjectScope.third_party,
        subject_entity_id='org',
        db_client=db,
    )
    # Local ancillary cache invalidation only; no external providers.
    from utils.memory.memory_service import MemoryService

    monkeypatch.setattr(MemoryService, '_invalidate_prompt_cache', lambda *a: None)
    change = ReviewChange(
        change_id='memory-change', kind='merge_memories', title='Correct partner spelling', created_at=NOW
    )
    journal.record_agent_change(
        uid,
        change,
        edit_key='partner-spelling',
        memory_edit=MemoryEdit(memory_id=source, content='Partner name is Paraform'),
    )

    def active_content():
        return [
            doc.to_dict()['content']
            for doc in user.collection('memory_items').stream()
            if doc.to_dict()['status'] == 'active'
        ]

    assert active_content() == ['Partner name is Paraform']
    if intervening_correction:
        from utils.memory import knowledge_ledger

        original = knowledge_ledger.amend_user_fact

        def correct_before_undo(owner, memory_id, content, **kwargs):
            original(
                owner,
                memory_id,
                'A newer user correction',
                **dict(
                    kwargs,
                    provenance=LedgerProvenance(
                        source_id=memory_id, source_type='explicit_user_correction', action_id='intervening'
                    ),
                ),
            )
            return original(owner, memory_id, content, **kwargs)

        monkeypatch.setattr(knowledge_ledger, 'amend_user_fact', correct_before_undo)
        response = client.post('/v1/review/changes/memory-change/undo')
        assert response.status_code == 409, response.text
        assert active_content() == ['A newer user correction']
        return
    response = client.post('/v1/review/changes/memory-change/undo')
    assert response.status_code == 200, response.text
    assert active_content() == ['Partner name is Pairform']
    row_count = len(list(user.collection('memory_items').stream()))
    assert client.post('/v1/review/changes/memory-change/undo').status_code == 200
    assert len(list(user.collection('memory_items').stream())) == row_count
    assert client.post('/v1/review/changes/memory-change/redo').status_code == 200
    assert active_content() == ['Partner name is Paraform']
    assert not journal.agent_change_allowed(uid, 'partner-spelling')


@pytest.mark.parametrize('decision', ['accept', 'dismiss'])
def test_task_answer_uses_real_candidate_resolution_with_edits(harness, monkeypatch, decision):
    client, uid, user, db = harness
    from database import candidates
    from models.candidate import CandidateCreate
    from utils.task_intelligence import candidate_service

    for name in ('_dispatch_task_integration', '_sync_task_reminder'):
        monkeypatch.setattr(candidate_service, name, Mock())
    proposal = CandidateCreate.model_validate(
        {
            'subject_kind': 'task',
            'proposed_action': 'create',
            'task_change': {'description': 'Send deck'},
            'capture_confidence': 0.9,
            'ownership_confidence': 0.9,
            'evidence_refs': [{'kind': 'conversation', 'id': 'c', 'scope': 'canonical'}],
            'source_surface': 'conversation',
        }
    )
    record = candidates.create_candidate(uid, proposal, idempotency_key='task-review', account_generation=3)
    item = review._task_item(uid, record)
    store.offer_item(uid, item, record.model_dump(mode='python'), 'v1')
    user.collection('workstreams').document('project').set(
        {
            'workstream_id': 'project',
            'title': 'Launch',
            'objective': 'Ship launch',
            'status': 'open',
            'account_generation': 3,
            'goal_id': None,
            'created_at': NOW,
            'updated_at': NOW,
        }
    )
    body = {
        'task': (
            {'decision': decision, 'dismiss_reason': 'not_mine'}
            if decision == 'dismiss'
            else {
                'decision': 'accept',
                'edited_description': 'Send launch deck',
                'due_at': None,
                'workstream_id': 'project',
            }
        )
    }
    response = client.post(f'/v1/review/items/{item.item_id}/answer', json=body)
    assert response.status_code == 200, response.text
    assert response.json()['applied'] is True
    final = candidates.get_candidate(uid, record.candidate_id)
    assert final.status.value == ('accepted' if decision == 'accept' else 'rejected')
    tasks = list(user.collection('action_items').stream())
    if decision == 'accept':
        assert len(tasks) == 1
        assert tasks[0].to_dict()['description'] == 'Send launch deck'
        assert tasks[0].to_dict()['workstream_id'] == 'project'
        assert tasks[0].to_dict().get('due_at') is None
    else:
        assert tasks == []
        assert final.resolution_reason == 'not_mine'
    assert client.post(f'/v1/review/items/{item.item_id}/answer', json=body).status_code == 200
    assert len(list(user.collection('action_items').stream())) == len(tasks)


def test_speaker_answer_delegates_existing_teaching(harness, monkeypatch):
    client, uid, user, db = harness
    from models.speaker_tag_prompts import SpeakerTagPrompt

    prompt = SpeakerTagPrompt(
        id='prompt',
        kind='identify',
        origin='unnamed',
        conversation_id='c',
        speaker_id=0,
        segment_ids=['s'],
        clip_start=1,
        clip_end=5,
        excerpt='A useful quote',
    )
    conversation = {
        'id': 'c',
        'created_at': NOW,
        'started_at': NOW,
        'structured': {'title': 'Meeting'},
        'transcript_segments': [{'id': 's', 'text': 'A useful quote', 'speaker_id': 0, 'start': 1}],
    }
    monkeypatch.setattr(review.conversations, 'get_conversation', lambda *a: conversation)
    teaching = Mock()
    monkeypatch.setattr(review.speakers, 'apply_answer', teaching)
    item = review._speaker_item(uid, prompt)
    store.offer_item(uid, item, prompt.model_dump(mode='python'), 'v1')
    response = client.post('/v1/review/items/speaker:prompt/answer', json={'speaker': {'is_me': True}})
    assert response.status_code == 200, response.text
    assert teaching.call_args.args[0] == uid
    request = teaching.call_args.args[1]
    assert request.answer.value == 'me' and request.segment_ids == ['s'] and request.conversation_id == 'c'
    assert callable(teaching.call_args.kwargs['schedule'])
    assert client.post('/v1/review/items/speaker:prompt/answer', json={'speaker': {'is_me': True}}).status_code == 200
    teaching.assert_called_once()


def test_real_spelling_fact_has_authority_600(harness):
    client, uid, user, db = harness
    _canonical_control(user, uid)
    enqueue(uid)
    client.get('/v1/review/items')
    response = client.post('/v1/review/items/spelling:1/answer', json={'spelling': {'value': 'Paraform'}})
    assert response.status_code == 200, response.text
    item = list(user.collection('memory_items').stream())[0].to_dict()
    assert item['subject_entity_id'] == 'vocabulary:1' and item['content'] == 'Paraform'
    assert item['write_reason'] == 'direct_user_statement'
    assert item['predicate'] == 'vocabulary'


@pytest.mark.parametrize('kind', ['title', 'overview'])
def test_agent_summary_edits_apply_undo_redo_and_suppress(harness, kind):
    from models.dream_edit import Edit
    from utils.agent_capabilities import tools as dream_tools

    client, uid, user, db = harness
    before = {
        'id': 'synthetic-summary',
        'structured': {
            'title': '',
            'overview': '',
            'sections': [{'heading': 'Old section'}] if kind == 'title' else [],
            'note_claims': [{'text': 'Old claim'}],
        },
        'transcript_segments': [{'text': 'We will build a toy boat. ' * 7}],
    }
    target = user.collection('conversations').document(before['id'])
    target.set(before)
    ref = 'conversations/' + before['id']
    edit = Edit(
        kind=kind,
        target=ref,
        before='',
        after=(
            'Building a toy boat' if kind == 'title' else '## Toy boat\n\n- We will build and test a toy boat tomorrow.'
        ),
        reason='Missing summary field',
        evidence=[ref],
    )
    assert dream_tools.apply_edit(uid, edit, {ref: before}) == 'applied'
    after = target.get().to_dict()
    assert after['structured'][kind] == edit.after
    if kind == 'overview':
        assert after['structured']['sections'] == after['structured']['note_claims'] == []
    change = client.get('/v1/review/changes').json()['changes'][0]
    assert change['snippet'] == edit.after
    assert change['refs'][0]['id'] == before['id']
    assert client.post(f'/v1/review/changes/{change["change_id"]}/undo').status_code == 200
    assert target.get().to_dict() == before
    assert dream_tools.apply_edit(uid, edit, {ref: before}) == 'suppressed'
    assert client.post(f'/v1/review/changes/{change["change_id"]}/redo').status_code == 200
    assert target.get().to_dict() == after
    target.update({'structured.' + kind: 'Direct user correction'})
    assert client.post(f'/v1/review/changes/{change["change_id"]}/undo').status_code == 409


def test_dream_title_and_overview_in_same_pass_share_evidence(harness):
    from models.dream_edit import Edit
    from utils.agent_capabilities import tools as dream_tools

    client, uid, user, db = harness
    before = {
        'id': 'synthetic-pair',
        'structured': {'title': '', 'overview': ''},
        'transcript_segments': [{'text': 'We will build a toy boat. ' * 7}],
    }
    target = user.collection('conversations').document(before['id'])
    target.set(before)
    ref = 'conversations/' + before['id']
    for kind in ['title', 'overview']:
        edit = Edit(
            kind=kind,
            target=ref,
            before='',
            after=(
                'Building a toy boat'
                if kind == 'title'
                else '## Toy boat\n\n- We will build and test a toy boat tomorrow.'
            ),
            reason='Missing summary field',
            evidence=[ref],
        )
        assert dream_tools.apply_edit(uid, edit, {ref: before}) == 'applied'
    assert target.get().to_dict()['structured']['title'] == 'Building a toy boat'
    assert (
        target.get().to_dict()['structured']['overview']
        == '## Toy boat\n\n- We will build and test a toy boat tomorrow.'
    )


def dream_task_proposal(harness, *, kind='retire_task', index=1):
    from models.dream_edit import Edit
    from utils.agent_capabilities import reads as dream_reads
    from utils.agent_capabilities import tools as dream_tools

    client, uid, user, db = harness
    task_id = f'dream-task-{index}'
    conversation_id = f'dream-evidence-{index}'
    user.collection('action_items').document(task_id).set(
        {
            'description': 'Build a toy boat',
            'status': 'active',
            'completed': False,
            'created_at': NOW - timedelta(days=10),
            'updated_at': NOW - timedelta(days=9),
            'account_generation': 3,
        }
    )
    user.collection('conversations').document(conversation_id).set(
        {
            'id': conversation_id,
            'created_at': NOW,
            'status': 'completed',
            'discarded': False,
            'structured': {'title': 'Toy boat'},
            'transcript_segments': [{'text': 'The toy boat is no longer needed.'}],
        }
    )
    refs = [f'action_items/{task_id}', f'conversations/{conversation_id}']
    records = {ref: dream_reads.read_record(uid, ref) for ref in refs}
    edit = Edit(kind=kind, target=refs[0], reason='Toy boat work is done', evidence=[refs[1]])
    status = dream_review_policy.suggest_edit(uid, edit, records)
    item_id = 'agent_proposal:' + store.safe_id(dream_tools.edit_key(edit, records))
    return edit, records, status, item_id


@pytest.mark.parametrize('kind', ['close_task', 'retire_task'])
def test_dream_suggestion_accept_journals_undo_and_exact_retry(harness, kind):
    from utils.agent_capabilities import tools as dream_tools

    client, uid, user, db = harness
    edit, records, status, item_id = dream_task_proposal(harness, kind=kind)
    assert status == 'suggested'
    target = user.collection('action_items').document(edit.target.split('/')[1])
    before = target.get().to_dict()
    assert before['status'] == 'active'
    items = client.get('/v2/review/items').json()['items']
    assert items[0]['kind'] == 'agent_proposal'
    assert items[0]['agent_proposal']['edit']['evidence'] == edit.evidence
    raw = user.collection('review_proposals').document(store.safe_id(item_id)).get().to_dict()
    assert 'Toy boat' not in str(raw) and 'review_encrypted_v1' in raw['source']
    body = {'agent_proposal': {'decision': 'accept'}}
    response = client.post(f'/v2/review/items/{item_id}/answer', json=body)
    assert response.status_code == 200, response.text
    assert response.json()['applied']
    assert target.get().to_dict()['status'] == ('completed' if kind == 'close_task' else 'cancelled')
    assert client.post(f'/v2/review/items/{item_id}/answer', json=body).status_code == 200
    changes = client.get('/v1/review/changes').json()['changes']
    assert len(changes) == 1
    assert client.post(f'/v1/review/changes/{changes[0]["change_id"]}/undo').status_code == 200
    assert target.get().to_dict() == before
    assert dream_review_policy.suggest_edit(uid, edit, records) == 'suppressed'
    assert client.get('/v2/review/items').json()['items'] == []


def test_dream_dismiss_is_durable_across_versions(harness):
    from utils.agent_capabilities import tools as dream_tools

    client, uid, user, db = harness
    edit, records, status, item_id = dream_task_proposal(harness)
    client.get('/v2/review/items')
    response = client.post(f'/v2/review/items/{item_id}/answer', json={'agent_proposal': {'decision': 'dismiss'}})
    assert response.status_code == 200, response.text
    assert not response.json()['applied']
    assert list(user.collection('review_changes').stream()) == []
    records[edit.evidence[0]]['structured']['title'] = 'New evidence version'
    assert (
        dream_review_policy.suggest_edit(uid, edit.model_copy(update={'reason': 'Different wording'}), records)
        == 'suppressed'
    )
    assert user.collection('action_items').document(edit.target.split('/')[1]).get().to_dict()['status'] == 'active'
    assert client.get('/v2/review/items').json()['items'] == []


@pytest.mark.parametrize('changed', ['target', 'evidence', 'generation'])
def test_dream_stale_accept_conflicts_and_refunds_attention(harness, changed):
    client, uid, user, db = harness
    edit, records, status, item_id = dream_task_proposal(harness)
    client.get('/v2/review/items')
    if changed == 'generation':
        user.collection('task_intelligence_control').document('state').set({'account_generation': 4})
    else:
        ref = edit.target if changed == 'target' else edit.evidence[0]
        collection, key = ref.split('/')
        user.collection(collection).document(key).update(
            {'description' if changed == 'target' else 'structured.title': 'User correction'}
        )
    response = client.post(f'/v2/review/items/{item_id}/answer', json={'agent_proposal': {'decision': 'accept'}})
    assert response.status_code == 409, response.text
    assert store.remaining_today(uid) == 3
    assert list(user.collection('review_changes').stream()) == []
    assert user.collection('action_items').document(edit.target.split('/')[1]).get().to_dict()['status'] == 'active'
    day = datetime.now(timezone.utc).date().isoformat()
    assert user.collection('review_attention').document(day).get().to_dict()['dream_suggestions'] == 1


def test_dream_attention_cap_is_atomic_and_idempotent(harness):
    client, uid, user, db = harness
    with ThreadPoolExecutor(max_workers=6) as pool:
        proposals = list(pool.map(lambda index: dream_task_proposal(harness, index=index), range(6)))
    assert sorted(row[2] for row in proposals) == ['suggested'] * 3 + ['suggestion_cap'] * 3
    from utils.agent_capabilities import tools as dream_tools

    for edit, records, status, item_id in proposals:
        assert dream_review_policy.suggest_edit(uid, edit, records) == (
            'already_suggested' if status == 'suggested' else 'suggestion_cap'
        )
    assert len(list(user.collection('review_proposals').stream())) == 3
    assert len(client.get('/v2/review/items').json()['items']) == 3


def test_dream_entity_summary_and_vocabulary_journal_roundtrip(harness):
    from models.dream_edit import Edit, Term
    from utils.agent_capabilities import tools as dream_tools

    client, uid, user, db = harness
    user.collection('knowledge_nodes').document('org').set(
        {'id': 'org', 'node_type': 'organization', 'label': 'Toy Works'}
    )
    row = entity_pages.resolve_entity(uid, 'org')
    edit = Edit(
        kind='entity_summary',
        target='knowledge_nodes/org',
        before='',
        after='Makes toy boats',
        reason='Summarize toy company',
        evidence=['knowledge_nodes/org'],
    )
    assert dream_review_policy.suggest_edit(uid, edit, {edit.target: row}) == 'suggested'
    item_id = client.get('/v2/review/items').json()['items'][0]['item_id']
    response = client.post(f'/v2/review/items/{item_id}/answer', json={'agent_proposal': {'decision': 'accept'}})
    assert response.status_code == 200, response.text
    cache = user.collection('entity_pages').document('org')
    assert store.decode_doc(uid, cache.get().to_dict())['summary'] == edit.after
    assert edit.after not in str(cache.get().to_dict())
    term = Term(kind='project', spelling='ToyBoat', evidence=[edit.target])
    with pytest.raises(ValueError, match='agent_vocabulary_requires_acceptance'):
        dream_tools.apply_vocabulary(uid, [term])
    assert dream_tools.apply_vocabulary(uid, [term], user_accepted=True) == 'applied'
    vocabulary = user.collection('dream_vocabulary').document('current')
    assert 'ToyBoat' not in str(vocabulary.get().to_dict())
    changes = client.get('/v1/review/changes').json()['changes']
    assert len(changes) == 2
    for change in changes:
        assert client.post(f'/v1/review/changes/{change["change_id"]}/undo').status_code == 200
    assert cache.get().to_dict() == {}
    assert vocabulary.get().to_dict() == {}
    assert dream_review_policy.suggest_edit(uid, edit, {edit.target: row}) == 'suppressed'
    for change in changes:
        assert client.post(f'/v1/review/changes/{change["change_id"]}/redo').status_code == 200
    assert store.decode_doc(uid, cache.get().to_dict())['summary'] == edit.after
    assert store.decode_doc(uid, vocabulary.get().to_dict())['source'][0]['spelling'] == 'ToyBoat'


def test_dream_accept_fences_evidence_in_actual_journal_transaction(harness, monkeypatch):
    client, uid, user, db = harness
    edit, records, status, item_id = dream_task_proposal(harness)
    client.get('/v2/review/items')
    original = journal.record_agent_change

    def racing_write(*args, **kwargs):
        user.collection('conversations').document(edit.evidence[0].split('/')[1]).update(
            {'structured.title': 'Intervening correction'}
        )
        return original(*args, **kwargs)

    monkeypatch.setattr(journal, 'record_agent_change', racing_write)
    response = client.post(f'/v2/review/items/{item_id}/answer', json={'agent_proposal': {'decision': 'accept'}})
    assert response.status_code == 409, response.text
    assert list(user.collection('review_changes').stream()) == []
    assert store.remaining_today(uid) == 3
    assert user.collection('action_items').document(edit.target.split('/')[1]).get().to_dict()['status'] == 'active'


@pytest.mark.parametrize('kind', ['memory', 'merge_memories'])
def test_dream_canonical_memory_suggestion_accept_and_undo(harness, monkeypatch, kind):
    from models.dream_edit import Edit
    from models.product_memory import LedgerWriteReason, MemorySubjectScope
    from utils.agent_capabilities import reads as dream_reads
    from utils.agent_capabilities import tools as dream_tools
    from utils.memory.knowledge_ledger import LedgerProvenance, save_fact
    from utils.memory.memory_service import MemoryService

    client, uid, user, db = harness
    _canonical_control(user, uid)
    monkeypatch.setattr(MemoryService, '_invalidate_prompt_cache', lambda *a: None)
    ids = [
        save_fact(
            uid,
            content,
            provenance=LedgerProvenance(
                source_id='toy-source', source_type='agent_conclusion', action_id=f'toy-seed-{index}'
            ),
            write_reason=LedgerWriteReason.agent_reusable_conclusion,
            subject_scope=MemorySubjectScope.third_party,
            subject_entity_id='toy-org',
            db_client=db,
        )
        for index, content in enumerate(['Toy company makes boats', 'Toy company builds boats'])
    ]
    refs = [f'memory_items/{key}' for key in ids]
    records = {ref: dream_reads.read_record(uid, ref) for ref in refs}
    edit = Edit(
        kind=kind,
        target=refs[0],
        other=refs[1] if kind == 'merge_memories' else '',
        before=records[refs[0]]['content'],
        after='Toy company makes wooden boats',
        reason='Update synthetic fact',
        evidence=refs,
    )
    assert dream_review_policy.suggest_edit(uid, edit, records) == 'suggested'
    item_id = client.get('/v2/review/items').json()['items'][0]['item_id']
    response = client.post(f'/v2/review/items/{item_id}/answer', json={'agent_proposal': {'decision': 'accept'}})
    assert response.status_code == 200, response.text

    def contents():
        return sorted(
            doc.to_dict()['content']
            for doc in user.collection('memory_items').stream()
            if doc.to_dict()['status'] == 'active'
        )

    assert edit.after in contents()
    changes = client.get('/v1/review/changes').json()['changes']
    assert len(changes) == 1
    response = client.post(f'/v1/review/changes/{changes[0]["change_id"]}/undo')
    assert response.status_code == 200, response.text
    assert contents() == ['Toy company builds boats', 'Toy company makes boats']
    assert not journal.agent_change_allowed(uid, dream_tools.edit_key(edit, records))


def test_dream_people_merge_suggestion_accept_and_undo(harness):
    from models.dream_edit import Edit
    from utils.agent_capabilities import tools as dream_tools

    client, uid, user, db = harness
    for key, name in [('a', 'Toy Mira'), ('b', 'Toy Meera')]:
        user.collection('people').document(key).set({'name': name})
        user.collection('knowledge_nodes').document('person:' + key).set(
            {'id': 'person:' + key, 'node_type': 'person', 'label': name, 'aliases': []}
        )
    refs = ['entity/person:a', 'entity/person:b']
    records = {ref: entity_pages.resolve_entity(uid, ref.split('/')[1]) for ref in refs}
    edit = Edit(
        kind='merge_people', target=refs[0], other=refs[1], reason='Synthetic duplicate identity', evidence=refs
    )
    assert dream_review_policy.suggest_edit(uid, edit, records) == 'suggested'
    item_id = client.get('/v2/review/items').json()['items'][0]['item_id']
    response = client.post(f'/v2/review/items/{item_id}/answer', json={'agent_proposal': {'decision': 'accept'}})
    assert response.status_code == 200, response.text
    other = user.collection('knowledge_nodes').document('person:b')
    assert other.get().to_dict()['redirect_entity_id'] == 'person:a'
    change = client.get('/v1/review/changes').json()['changes'][0]
    assert client.post(f'/v1/review/changes/{change["change_id"]}/undo').status_code == 200
    assert 'redirect_entity_id' not in other.get().to_dict()
    assert dream_review_policy.suggest_edit(uid, edit, records) == 'suppressed'


def test_dream_suggestions_share_question_budget_and_reset_next_day(harness, monkeypatch):
    from database import dream_store

    client, uid, user, db = harness
    day = datetime.now(timezone.utc).date().isoformat()
    db.collection('dream_users').document(uid).set({'lease': {'run_id': 'toy-run'}})
    assert dream_task_proposal(harness)[2] == 'suggested'
    assert dream_store.reserve_questions(uid, 'toy-run', 3) == 2
    assert dream_task_proposal(harness, index=2)[2] == 'suggestion_cap'

    original = store.enqueue_review_proposal
    monkeypatch.setattr(
        store, 'enqueue_review_proposal', lambda *args, **kwargs: original(*args, **kwargs, now=NOW + timedelta(days=1))
    )
    assert dream_task_proposal(harness, index=3)[2] == 'suggested'
    assert user.collection('review_attention').document(day).get().to_dict()['dream_suggestions'] == 1


def test_dismiss_hides_an_in_flight_refresh_of_same_operation(harness, monkeypatch):
    client, uid, user, db = harness
    edit, records, status, item_id = dream_task_proposal(harness)
    client.get('/v2/review/items')
    proposal_ref = user.collection('review_proposals').document(store.safe_id(item_id))
    proposal = store.require_doc(uid, proposal_ref.get().to_dict())
    item = ReviewItemV2.model_validate(proposal['item'])
    original = journal.suppress_agent_change

    def refresh_then_dismiss(owner, key):
        assert (
            store.enqueue_review_proposal(
                owner, item, evidence_version='refreshed-version', source=proposal['source'], edit_key=key
            )
            == 'suggested'
        )
        original(owner, key)

    monkeypatch.setattr(journal, 'suppress_agent_change', refresh_then_dismiss)
    response = client.post(f'/v2/review/items/{item_id}/answer', json={'agent_proposal': {'decision': 'dismiss'}})
    assert response.status_code == 200, response.text
    assert store.require_doc(uid, proposal_ref.get().to_dict())['status'] == 'pending'
    assert client.get('/v2/review/items').json()['items'] == []


def test_review_v1_hides_v2_proposals_and_cannot_answer_them(harness):
    client, uid, user, db = harness
    edit, records, status, item_id = dream_task_proposal(harness)
    enqueue(uid)
    legacy = client.get('/v1/review/items').json()['items']
    assert [item['kind'] for item in legacy] == ['spelling']
    modern = client.get('/v2/review/items').json()['items']
    assert {item['kind'] for item in modern} == {'spelling', 'agent_proposal'}
    response = client.post(f'/v1/review/items/{item_id}/answer', json={'not_sure': True})
    assert response.status_code == 409
    assert store.remaining_today(uid) == 3
    assert user.collection('action_items').document(edit.target.split('/')[1]).get().to_dict()['status'] == 'active'
    user.collection('knowledge_nodes').document('toy-org').set(
        {'id': 'toy-org', 'node_type': 'organization', 'label': 'Toy Works'}
    )
    page = client.get('/v1/entities/toy-org/page')
    assert page.status_code == 200, page.text
    assert page.json()['pending_question'] is None
    first = client.post('/v1/review/items/spelling:1/answer', json={'not_sure': True})
    retry = client.post('/v2/review/items/spelling:1/answer', json={'not_sure': True})
    assert first.status_code == retry.status_code == 200
    assert first.json() == retry.json()


@pytest.mark.parametrize('decision', ['yes', 'no'])
def test_same_person_redirects_converge_and_do_not_reappear(harness, monkeypatch, decision):
    client, uid, user, db = harness
    monkeypatch.setattr(entity_pages.users, 'get_person', lambda uid, pid: {'name': 'Synthetic Sam'})
    item = ReviewItem(
        item_id='same_person:stale-redirect',
        kind='same_person',
        title='Same person?',
        created_at=NOW,
        same_person=SamePersonItem(
            left=EntitySummary(entity_id='person:a', type='person', name='Sam'),
            right=EntitySummary(entity_id='person:b', type='person', name='Samuel'),
            reason='Same voice',
        ),
    )
    user.collection('knowledge_nodes').document('person:a').set({'node_type': 'person', 'label': 'Sam'})
    user.collection('knowledge_nodes').document('person:b').set({'node_type': 'person', 'label': 'Samuel'})
    enqueue(uid, item)
    assert client.get('/v2/review/items').json()['items'][0]['item_id'] == item.item_id
    # Another question or manual merge completed after this offer was made.
    user.collection('knowledge_nodes').document('person:b').update({'redirect_entity_id': 'person:a'})
    response = client.post(f'/v2/review/items/{item.item_id}/answer', json={'same_person': {'decision': decision}})
    assert response.status_code == (200 if decision == 'yes' else 409), response.text
    if decision == 'yes':
        assert response.json()['applied'] is False
    row = user.collection('review_proposals').document(store.safe_id(item.item_id)).get().to_dict()
    assert row['status'] == 'resolved'
    assert client.get('/v2/review/items').json()['items'] == []
    assert list(user.collection('review_changes').stream()) == []
