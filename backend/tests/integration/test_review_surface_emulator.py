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
from models.review import EntitySummary, ReviewAnswer, ReviewChange, ReviewItem, SamePersonItem, SpellingItem
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
def test_dream_summary_edits_apply_undo_redo_and_suppress(harness, kind):
    from models.dream_agent import Edit
    from utils import dream_tools

    client, uid, user, db = harness
    before = {
        'id': 'synthetic-summary',
        'structured': {
            'title': '',
            'overview': '',
            'sections': [{'heading': 'Old section'}],
            'note_claims': [{'text': 'Old claim'}],
        },
        'transcript_segments': [{'text': 'We will build a toy boat.'}],
    }
    target = user.collection('conversations').document(before['id'])
    target.set(before)
    ref = 'conversations/' + before['id']
    edit = Edit(
        kind=kind, target=ref, before='', after='Building a toy boat', reason='Missing summary field', evidence=[ref]
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
    from models.dream_agent import Edit
    from utils import dream_tools

    client, uid, user, db = harness
    before = {
        'id': 'synthetic-pair',
        'structured': {'title': '', 'overview': ''},
        'transcript_segments': [{'text': 'We will build a toy boat.'}],
    }
    target = user.collection('conversations').document(before['id'])
    target.set(before)
    ref = 'conversations/' + before['id']
    for kind in ['title', 'overview']:
        edit = Edit(
            kind=kind,
            target=ref,
            before='',
            after='Building a toy boat',
            reason='Missing summary field',
            evidence=[ref],
        )
        assert dream_tools.apply_edit(uid, edit, {ref: before}) == 'applied'
    assert target.get().to_dict()['structured']['title'] == 'Building a toy boat'
    assert target.get().to_dict()['structured']['overview'] == 'Building a toy boat'
