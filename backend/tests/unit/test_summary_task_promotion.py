"""Real prepare/accept routers over strict transaction ordering; no network IO."""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from database import _client, candidates
from database.summary_task_links import read_summary_task_row
from models.candidate import SummaryTaskReference
from routers import candidates as router
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from tests.unit.universal_memory_test_helpers import configure_universal_memory
from utils.task_intelligence import candidate_service

UID = 'summary-reader'
GENERATION = 3
CONVERSATION_PATH = ('users', UID, 'conversations', 'conversation-1')
SELECTED = {'conversation_id': 'conversation-1', 'action_item_index': 0, 'expected_description': 'Send the budget'}
HEADERS = {'X-Account-Generation': '3', 'Idempotency-Key': 'summary-gesture-1'}
DUE = datetime(2026, 10, 1, 9, tzinfo=timezone.utc)


@pytest.fixture
def harness(monkeypatch):
    db = StrictFirestore()
    db.rows[('users', UID, 'task_intelligence_control', 'state')] = {'account_generation': GENERATION}
    db.rows[CONVERSATION_PATH] = {
        'structured': {
            'title': 'Budget meeting',
            'action_items': [
                {
                    'description': 'Send the budget',
                    'capture_owner': 'user',
                    'capture_confidence': 0.9,
                    'ownership_confidence': 1.0,
                    'due_at': DUE,
                    'source_segment_ids': ['segment-1'],
                },
                {'description': 'Ask the accountant', 'capture_owner': 'other'},
            ],
        },
        'transcript_segments': b'opaque encrypted transcript remains untouched',
        'data_protection_level': 'enhanced',
    }
    monkeypatch.setattr(_client, '_firestore_client', db)
    monkeypatch.setattr(candidates, 'db', db)
    configure_universal_memory(monkeypatch, UID)
    monkeypatch.setattr(candidate_service, '_dispatch_task_integration', Mock())
    monkeypatch.setattr(candidate_service, '_sync_task_reminder', Mock())
    app = FastAPI()
    app.include_router(router.router)
    app.dependency_overrides[router.auth.get_current_user_uid] = lambda: UID
    with TestClient(app) as client:
        yield client, db


def tasks(db):
    return [row for path, row in db.rows.items() if len(path) == 4 and path[2] == 'action_items']


def pending(db):
    return [
        row
        for path, row in db.rows.items()
        if len(path) == 4 and path[2] == 'candidates' and row['status'] == 'pending'
    ]


def prepare(client, **overrides):
    return client.post('/v1/candidates/from-conversation', headers=HEADERS, json={**SELECTED, **overrides})


def accept(client, candidate_id, *, summary=True):
    kwargs = {'json': {'summary_item': SELECTED}} if summary else {}
    return client.post(f'/v1/candidates/{candidate_id}/accept', headers=HEADERS, **kwargs)


def test_summary_prepares_only_then_accepts_the_extractions_semantic_candidate(harness):
    client, db = harness
    before = deepcopy(db.rows[CONVERSATION_PATH])
    extracted = candidates.create_candidate(
        UID,
        read_summary_task_row(UID, SummaryTaskReference(**SELECTED)).proposal(),
        idempotency_key='automatic-extraction',
        account_generation=GENERATION,
    )
    response = prepare(client)
    assert response.status_code == 200, response.text
    assert response.json()['candidate_id'] == extracted.candidate_id
    assert len(pending(db)) == 1
    assert tasks(db) == []
    assert db.rows[CONVERSATION_PATH] == before

    accepted = accept(client, extracted.candidate_id)
    assert accepted.status_code == 200, accepted.text
    task_id = accepted.json()['task_id']
    assert pending(db) == []
    assert len(tasks(db)) == 1
    task = tasks(db)[0]
    assert task['id'] == task_id
    assert task['conversation_id'] == 'conversation-1'
    assert task['due_at'] == DUE
    assert task['owner'] == 'user'
    assert task['provenance'][0]['transcript_segment_ids'] == ['segment-1']
    after = db.rows[CONVERSATION_PATH]
    assert after['structured']['action_items'][0]['target_task_id'] == task_id
    assert after['structured']['action_items'][1] == before['structured']['action_items'][1]
    assert after['transcript_segments'] == before['transcript_segments']

    # The Suggested card and summary are one resolution, not two task writers.
    replay = accept(client, extracted.candidate_id, summary=False)
    assert replay.status_code == 200
    assert replay.json()['newly_resolved'] is False
    assert replay.json()['task_id'] == task_id
    assert len(tasks(db)) == 1


def test_reopened_summary_and_lost_response_preserve_completed_edited_task(harness):
    client, db = harness
    candidate_id = prepare(client).json()['candidate_id']
    first = accept(client, candidate_id).json()
    task = tasks(db)[0]
    task.update(description='User revised title', status='completed', completed=True)
    response = prepare(client)
    assert response.status_code == 200, response.text
    assert response.json()['candidate_id'] == candidate_id
    replay = accept(client, candidate_id)
    assert replay.status_code == 200, replay.text
    assert replay.json()['task_id'] == first['task_id']
    assert replay.json()['newly_resolved'] is False
    assert len(tasks(db)) == 1
    assert task['description'] == 'User revised title'
    assert task['completed'] is True


def test_accepting_suggested_first_then_summary_reuses_task_and_saves_link(harness):
    client, db = harness
    candidate_id = prepare(client).json()['candidate_id']
    first = accept(client, candidate_id, summary=False).json()
    replay = accept(client, candidate_id)
    assert replay.status_code == 200, replay.text
    assert replay.json()['task_id'] == first['task_id']
    assert db.rows[CONVERSATION_PATH]['structured']['action_items'][0]['target_task_id'] == first['task_id']
    assert tasks(db)[0]['conversation_id'] == 'conversation-1'
    assert len(tasks(db)) == 1


def test_same_commitment_in_two_conversations_keeps_both_provenance_links(harness):
    client, db = harness
    first_candidate = prepare(client).json()['candidate_id']
    first_task = accept(client, first_candidate).json()['task_id']
    second_path = ('users', UID, 'conversations', 'conversation-2')
    db.rows[second_path] = {
        'structured': {
            'title': 'Budget follow-up',
            'action_items': [
                {
                    'description': 'Send the budget',
                    'capture_owner': 'user',
                    'capture_confidence': 0.9,
                    'ownership_confidence': 1.0,
                    'due_at': DUE,
                    'source_segment_ids': ['segment-2'],
                }
            ],
        }
    }
    second = {
        'conversation_id': 'conversation-2',
        'action_item_index': 0,
        'expected_description': 'Send the budget',
    }

    prepared = client.post(
        '/v1/candidates/from-conversation',
        headers={**HEADERS, 'Idempotency-Key': 'summary-gesture-2'},
        json=second,
    )
    assert prepared.status_code == 200, prepared.text
    assert prepared.json()['candidate_id'] == first_candidate
    accepted = client.post(
        f'/v1/candidates/{first_candidate}/accept',
        headers={**HEADERS, 'Idempotency-Key': 'summary-gesture-2'},
        json={'summary_item': second},
    )
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()['task_id'] == first_task
    assert db.rows[second_path]['structured']['action_items'][0]['target_task_id'] == first_task
    task = tasks(db)[0]
    assert task['conversation_id'] == 'conversation-1'
    assert [ref['id'] for ref in task['provenance']] == ['conversation-1', 'conversation-2']


@pytest.mark.parametrize(
    'mutation', ['description', 'due_at', 'capture_owner', 'deleted', 'is_locked', 'different_link']
)
def test_changed_summary_rejects_before_task_or_resolution_write(harness, mutation):
    client, db = harness
    candidate_id = prepare(client).json()['candidate_id']
    row = db.rows[CONVERSATION_PATH]
    item = row['structured']['action_items'][0]
    if mutation in {'deleted', 'is_locked'}:
        row[mutation] = True
    elif mutation == 'different_link':
        item['target_task_id'] = 'another-task'
    else:
        item[mutation] = {
            'description': 'Different item',
            'due_at': DUE + timedelta(hours=1),
            'capture_owner': 'other',
        }[mutation]
    before = deepcopy(db.rows)
    response = accept(client, candidate_id)
    assert response.status_code in {404, 409}, response.text
    assert db.rows == before
    assert tasks(db) == []


@pytest.mark.parametrize(
    'patch', [{'action_item_index': 1}, {'conversation_id': 'other-conversation'}, {'action_item_index': -1}]
)
def test_stale_index_cross_owner_or_bad_index_cannot_promote(harness, patch):
    client, db = harness
    response = prepare(client, **patch)
    assert response.status_code in {404, 409, 422}
    assert tasks(db) == []
    assert pending(db) == []


def test_account_generation_fence_preserves_legacy_bodyless_accept(harness):
    client, db = harness
    candidate_id = prepare(client).json()['candidate_id']
    rejected = client.post(
        f'/v1/candidates/{candidate_id}/accept',
        headers={'X-Account-Generation': '2'},
        json={'summary_item': SELECTED},
    )
    assert rejected.status_code == 409
    assert tasks(db) == []
    accepted = accept(client, candidate_id, summary=False)
    assert accepted.status_code == 200, accepted.text
    assert len(tasks(db)) == 1


@pytest.mark.parametrize(
    'field,value', [('target_task_id', 'bad/path'), ('source_segment_ids', ['bad/path']), ('capture_confidence', 2)]
)
def test_malformed_stored_link_or_evidence_is_a_conflict_not_a_server_error(harness, field, value):
    client, db = harness
    db.rows[CONVERSATION_PATH]['structured']['action_items'][0][field] = value
    before = deepcopy(db.rows)
    response = prepare(client)
    assert response.status_code == 409, response.text
    assert db.rows == before


def test_legacy_summary_preserves_unknown_owner_and_zero_confidence(harness):
    client, db = harness
    item = db.rows[CONVERSATION_PATH]['structured']['action_items'][0]
    item.pop('capture_owner')
    item.update(capture_confidence=0, ownership_confidence=0)
    prepared = prepare(client)
    assert prepared.status_code == 200, prepared.text
    assert prepared.json()['capture_confidence'] == 0
    accepted = accept(client, prepared.json()['candidate_id'])
    assert accepted.status_code == 200, accepted.text
    assert tasks(db)[0]['owner'] == 'unknown'


def test_missing_linked_task_cannot_recreate_or_retarget_summary(harness):
    client, db = harness
    candidate_id = prepare(client).json()['candidate_id']
    task_id = accept(client, candidate_id).json()['task_id']
    del db.rows[('users', UID, 'action_items', task_id)]
    before = deepcopy(db.rows)
    response = prepare(client)
    assert response.status_code == 409, response.text
    assert db.rows == before
