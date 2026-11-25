"""SCA-4178: an undecodable stored transcript parks in ONE delivery on real transactions.

The 2026-11-24 Go replay oracle (SCA-3551, case ``unreadable-ciphertext-dead-letters``) measured Python
answering 409 ``callback_pending`` 868 times into the 72 h age gate: 13,890 Firestore operations for one
conversation, versus 22 for the Go dead-letter. This proof drives the real enrichment push route against a
loopback emulator: the first delivery must reach the counted terminal park, keep the ciphertext
byte-for-byte, make no provider call, and leave a redelivery with nothing to do.
"""

from copy import deepcopy
import os
import time
import uuid

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from google.auth.credentials import AnonymousCredentials
from google.cloud import firestore

pytestmark = pytest.mark.integration

# The oracle's per-conversation budget for a terminal disposition; the Python shape it replaces cost 13,890.
OPERATION_BUDGET = 100


@pytest.fixture(autouse=True)
def loopback_only_network():
    from testing.hermetic_network import block_outbound_network

    with block_outbound_network():
        yield


@pytest.fixture
def store(monkeypatch):
    host = os.getenv('FIRESTORE_EMULATOR_HOST', '')
    if not host.startswith(('127.0.0.1:', 'localhost:')):
        pytest.skip('requires a loopback Firestore emulator')
    import google.auth

    monkeypatch.setattr(google.auth, 'default', lambda **_: (AnonymousCredentials(), 'demo-omi-unreadable'))
    monkeypatch.setenv('PROVIDER_MODE', 'offline')
    monkeypatch.setenv('OMI_ENV_STAGE', 'prod')
    client = firestore.Client(project='demo-omi-unreadable', credentials=AnonymousCredentials())

    from database import _client
    from utils.enrichment import outbox

    monkeypatch.setattr(outbox, 'get_firestore_client', lambda: client)
    monkeypatch.setattr(_client, 'get_firestore_client', lambda: client)
    monkeypatch.setenv('SYNC_REPROCESS_SETTLE_SECONDS', '0')
    monkeypatch.setenv('SYNC_TASKS_QUEUE', 'sync-jobs')
    monkeypatch.setenv('SYNC_TASKS_HANDLER_URL', 'https://fresh.invalid/v2/sync-jobs/run')
    monkeypatch.setenv('SYNC_TASKS_INVOKER_SA', 'invoker@example.invalid')
    monkeypatch.delenv('SYNC_TASKS_OIDC_AUDIENCE', raising=False)
    tasks: list[dict] = []
    monkeypatch.setattr(outbox, '_enqueue', lambda row: tasks.append(dict(row)))
    uid = 'test-' + uuid.uuid4().hex
    client.collection('users').document(uid).set({'data_protection_level': 'enhanced'})
    yield client, uid, tasks
    for row in client.collection(outbox.COLLECTION).where('uid', '==', uid).stream():
        row.reference.delete()
    client.collection('users').document(uid).delete()


@pytest.fixture
def wrong_key(store):
    """A stored transcript encrypted for another owner: no key this worker holds can read it."""
    from database import conversations as conversations_db

    client, uid, tasks = store
    cid = 'unreadable'
    document = conversations_db.encode_conversation_for_write(
        'different-encryption-user',
        {
            'id': cid,
            'status': 'completed',
            'discarded': False,
            'sync_relevance': 'review',
            'has_photos': False,
            'language': 'en',
            'transcript_segments': [{'text': 'synthetic transcript'}],
        },
        'enhanced',
    )
    client.document(f'users/{uid}/conversations/{cid}').set(document)
    yield document
    client.document(f'users/{uid}/conversations/{cid}').delete()


@pytest.fixture
def app(store):
    from routers import enrichment

    application = FastAPI()
    application.include_router(enrichment.router)
    application.dependency_overrides[enrichment.verify_enrichment_task] = lambda: 0
    return TestClient(application)


class _Forbidden:
    """A step that must not run for an unreadable transcript."""

    def __init__(self, action: str) -> None:
        self.action = action
        self.called = False

    def __call__(self, *_args, **_kwargs):
        self.called = True
        raise AssertionError(f'artifact-safety: {self.action} must not run for an unreadable transcript')


class _Operations:
    """Minimal replay-meter state: counts the Firestore RPCs the case costs."""

    cost_measured = False

    def __init__(self) -> None:
        self.counts: dict[str, int] = {}

    def add_firestore_operations(self, **counts) -> None:
        for name, value in counts.items():
            if value:
                self.counts[name] = self.counts.get(name, 0) + int(value)

    @property
    def total(self) -> int:
        return sum(self.counts.values())


def test_unreadable_transcript_parks_in_one_delivery_with_ciphertext_kept(app, store, wrong_key, monkeypatch):
    from testing.finalization_replay import metrics
    from utils.enrichment import callback
    from utils.enrichment.admission import TRANSCRIPT_DECODE_FAILURES
    from utils.enrichment import outbox

    client, uid, tasks = store
    cid = 'unreadable'
    conversation_ref = client.document(f'users/{uid}/conversations/{cid}')
    ciphertext = wrong_key['transcript_segments']
    assert isinstance(ciphertext, str) and ciphertext
    before = deepcopy(conversation_ref.get().to_dict())

    provider = _Forbidden('a provider step')
    claim = _Forbidden('a summary claim')
    monkeypatch.setattr(callback, 'process_conversation', provider)
    monkeypatch.setattr(callback, 'claim_from_snapshot', claim)
    monkeypatch.setattr(callback, 'occasion_relevance_enabled', lambda: False)

    tasks.clear()
    outbox.mark(uid, cid, 'en', snapshot_summary=True)
    assert len(tasks) == 1  # the one accepted wake
    key, token = outbox.key(uid, cid), tasks[-1]['task_token']
    payload = {'kind': 'enrichment', 'key': key, 'task_token': token}
    # Cloud Tasks dispatches at the row's due time, and the outbox rejects an early claim.
    delay = float(client.collection(outbox.COLLECTION).document(key).get().to_dict()['due_at']) - time.time()
    if delay > 0:
        time.sleep(delay + 0.05)

    decode_failures_before = TRANSCRIPT_DECODE_FAILURES._value.get()
    metrics.install_firestore_meter()
    operations = _Operations()
    with metrics.measure(operations):
        first = app.post('/v2/enrichment/run', json=payload)
        assert first.status_code == 200
        assert first.json() == {'status': 'discarded', 'reason': 'transcript_unreadable'}
        redelivery = app.post('/v2/enrichment/run', json=payload)
        assert redelivery.status_code == 200
        assert redelivery.json()['status'] == 'stale'

    row = client.collection(outbox.COLLECTION).document(key).get().to_dict()
    assert row['dormant'] and row['due_at'] is None and row['task_due_at'] is None
    assert row['lease_until'] == 0 and row['owner'] is None
    assert row['held_reason'] == 'transcript_unreadable' and row['held_at'] is not None
    assert (row['uid'], row['conversation_id']) == (uid, cid)  # kept findable for a later revision
    assert len(tasks) == 1  # the park created no successor wake

    assert before['transcript_segments'] == ciphertext
    assert conversation_ref.get().to_dict() == before  # ciphertext and every other field untouched
    assert TRANSCRIPT_DECODE_FAILURES._value.get() == decode_failures_before + 1
    assert not provider.called and not claim.called
    # Measured here: 40 operations (21 RPC calls, 17 document reads, 2 writes) for the park plus its
    # stale redelivery, against 13,890 for the 868-delivery age-gate loop this replaces.
    assert operations.total < OPERATION_BUDGET, operations.counts

    # A later content revision reopens the same obligation: the guard still never discards.
    outbox.mark(uid, cid, 'en')
    reopened = client.collection(outbox.COLLECTION).document(key).get().to_dict()
    assert not reopened['dormant'] and reopened.get('held_reason') is None and reopened['due_at'] is not None
    assert len(tasks) == 2
