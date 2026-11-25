"""Worker emulator checks for publication authorities and the sync assignment writer."""

import os
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse
from uuid import uuid4

from google.api_core.exceptions import Aborted
from google.auth.credentials import AnonymousCredentials
from google.cloud import firestore
import pytest

from database.batch_pipeline_projection_protocol import ProjectionBlocked
from database.batch_pipeline_publication_authority import (
    ActivationOperations,
    record_oversized_row_custody,
    routing_ref,
    run_activation_transaction,
)
from utils.sync.assignment import assign_in_transaction


@pytest.fixture
def client():
    host = os.environ.get('FIRESTORE_EMULATOR_HOST')
    if not host:
        pytest.skip('requires the Firestore emulator')
    assert urlparse(f'//{host}').hostname in {'127.0.0.1', 'localhost', '::1'}
    with_client = firestore.Client(project=f'demo-pub-{uuid4().hex[:12]}', credentials=AnonymousCredentials())
    yield with_client
    with_client.close()


def test_assignment_fences_absent_id_and_index(client, monkeypatch):
    uid = uuid4().hex
    monkeypatch.setenv('BATCH_PUBLICATION_PILOT_OWNER', uid)
    owner = client.collection('users').document(uid)
    route = routing_ref(client, uid)
    start = datetime(2026, 11, 20, 12, tzinfo=timezone.utc)
    incoming = {
        'id': 'new',
        'started_at': start,
        'finished_at': start + timedelta(seconds=20),
        'status': 'processing',
        'source': 'omi',
        'transcript_segments': [{'id': 'audio', 'start': 0, 'end': 20, 'text': 'Synthetic speech.'}],
    }

    @firestore.transactional
    def assign(tx):
        return assign_in_transaction(tx, owner, incoming, decode=deepcopy, encode=deepcopy, invalidate=lambda _: None)

    route.set({'active_publication': 'fixture'})
    with pytest.raises(ProjectionBlocked, match='must drain'):
        assign(client.transaction())
    assert not owner.collection('conversations').document('new').get().exists
    assert not list(owner.collection('sync_assignment').stream())

    # An incompatible writer can still successfully change a guarded owner.
    owner.collection('conversations').document('unguarded').set({'id': 'unguarded'})
    assert owner.collection('conversations').document('unguarded').get().exists

    route.delete()
    assigned, created, _ = assign(client.transaction())
    assert created
    assert owner.collection('conversations').document(assigned['id']).get().exists
    assert set(doc.id for doc in owner.collection('sync_assignment').stream()) == {'recent', '2026-11-20'}


def test_budget_counts_absence_retries_and_exact_receipt(client, monkeypatch):
    table = client.collection('publication_test')
    receipt = table.document('receipt')
    original_commit = firestore.Transaction._commit
    commits = []

    def abort_once(transaction):
        commits.append(None)
        if len(commits) == 1:
            transaction._rollback()
            raise Aborted('synthetic retry at commit boundary')
        return original_commit(transaction)

    monkeypatch.setattr(firestore.Transaction, '_commit', abort_once)

    def activate(attempt):
        if attempt.read(receipt).exists:
            return
        for i in range(275):
            ref = table.document(str(i))
            assert not attempt.read(ref).exists
            assert not attempt.read(ref).exists
        for i in range(11):
            attempt.transaction.set(table.document(str(i)), {'fixture': True})
        attempt.transaction.create(receipt, {'publication': 'fixture'})

    attempts = []
    run_activation_transaction(client, activate, attempts)
    assert attempts == [ActivationOperations(276, 12), ActivationOperations(276, 12, committed=True)]

    # Discard the successful outcome and retry by the exact receipt.
    replay = []
    run_activation_transaction(client, activate, replay)
    assert replay == [ActivationOperations(1, 0, committed=True)]


def test_oversized_refusal_retains_the_exact_staged_artifact(client):
    job = client.collection('publication_test').document('job')
    artifact = {'object': 'result.json', 'generation': '1234'}
    job.set({'owner_id': 'owner', 'state': 'result_ready', 'result': artifact})
    with pytest.raises(ProjectionBlocked, match='lost its staged result binding'):
        record_oversized_row_custody(client, job, owner_id='owner', artifact={'generation': '5678'})
    assert 'publication_custody' not in job.get().to_dict()
    record_oversized_row_custody(client, job, owner_id='owner', artifact=artifact)
    recorded = job.get().to_dict()
    assert recorded['state'] == 'result_ready'
    assert recorded['result'] == recorded['publication_custody']['artifact'] == artifact
    assert recorded['publication_custody']['reason'] == 'canonical_row_too_large'
    record_oversized_row_custody(client, job, owner_id='owner', artifact=artifact)
    assert job.get().to_dict() == recorded


def test_activation_rejects_a_commit_whose_hooks_exceed_the_write_cap(client):
    conversations = client.collection('users').document('owner').collection('conversations')
    table = client.collection('publication_test')
    attempts = []

    def candidate(attempt):
        attempt.transaction.create(conversations.document('new'), {'id': 'new'})
        for i in range(11):
            attempt.transaction.create(table.document(str(i)), {'fixture': True})

    with pytest.raises(ProjectionBlocked, match='native commit budget'):
        run_activation_transaction(client, candidate, attempts)
    assert len(attempts) == 1
    assert attempts[0].buffered_writes > 12
    assert not attempts[0].committed
    assert not conversations.document('new').get().exists
    assert not list(table.stream())
