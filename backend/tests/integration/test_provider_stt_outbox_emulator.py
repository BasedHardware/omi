"""Provider-STT outbox default privacy fence on the Firestore emulator (M1 review, lane 8).

The unit suite injects ``privacy_blocked``; only a real client shows that the default fence reads through
``assert_batch_write_allowed`` without an unstarted transaction (which raises 'Transaction not in progress').
Skipped without a loopback emulator unless ``OMI_REQUIRE_STORE_BACKENDS`` names it.
"""

from __future__ import annotations

import hashlib
import uuid

import pytest

from database.outbox import Claim, Outcome
from testing.store_fixtures import BackendUnavailable, ClientCustomerData, make_emulator, required_backends

pytestmark = pytest.mark.integration


@pytest.fixture
def emulator():
    try:
        harness = make_emulator()
    except BackendUnavailable as exc:
        if 'emulator' in required_backends():
            pytest.fail(f'required store backend emulator unavailable: {exc}')
        pytest.skip(f'emulator unavailable: {exc}')
    client = harness.customer.client
    collection = f'{harness.namespace}_provider_stt_outbox'
    try:
        yield client, collection
    finally:
        for doc in client.collection(collection).stream():
            doc.reference.delete()
        harness.close()


def _outbox(client, collection, wakes):
    from database.outbox_provider_stt import FirestoreProviderSttOutbox

    return FirestoreProviderSttOutbox(
        client, create_wake=lambda row_id, token, at: wakes.append((row_id, token, at)), collection=collection
    )


def _segment(label: str) -> str:
    return hashlib.sha256(f'{label}-{uuid.uuid4().hex}'.encode()).hexdigest()


def test_default_privacy_fence_claims_an_allowed_owner_and_discards_a_deleted_one(emulator):
    client, collection = emulator
    customer = ClientCustomerData(client)
    allowed, deleted = f'allowed-{uuid.uuid4().hex[:8]}', f'deleted-{uuid.uuid4().hex[:8]}'
    customer.add_user(allowed)
    customer.add_user(deleted)
    wakes: list = []
    outbox = _outbox(client, collection, wakes)

    live = _segment('live')
    queued = outbox.enqueue(live, allowed, {'segment_id': live}, 100.0, now=100.0)
    assert queued.wake_token
    claim = outbox.claim_key(live, queued.wake_token, 1800.0, now=101.0)
    assert isinstance(claim, Claim) and claim.owner_id == allowed

    gone = _segment('gone')
    fenced = outbox.enqueue(gone, deleted, {'segment_id': gone}, 100.0, now=100.0)
    assert fenced.wake_token
    customer.delete_account(deleted)
    assert outbox.claim_key(gone, fenced.wake_token, 1800.0, now=101.0) is Outcome.DISCARDED
    row = client.collection(collection).document(gone).get().to_dict()
    assert row['state'] == 'closed' and row['closed_reason'] == 'privacy_blocked'


def test_default_privacy_fence_runs_inside_the_sweep(emulator):
    client, collection = emulator
    customer = ClientCustomerData(client)
    deleted = f'deleted-{uuid.uuid4().hex[:8]}'
    customer.add_user(deleted)
    outbox = _outbox(client, collection, [])
    gone = _segment('sweep')
    outbox.enqueue(gone, deleted, {'segment_id': gone}, 100.0, now=100.0)
    customer.delete_account(deleted)
    counts = outbox.sweep(now=5000.0)
    assert (counts.discarded, counts.errors) == (1, 0)


def test_provider_running_intent_may_register_its_one_result(emulator):
    """M1 re-review L08-3: register_batch_artifact accepted results only for leased GPU jobs and quarantine
    writes, so a paid provider result raised result_lease_lost and stranded the unit in provider_running."""
    from database.batch_pipeline_privacy import BatchPrivacyBlocked
    from database.batch_pipeline_store import FirestoreStore
    from utils.batch_pipeline.retention import register_batch_artifact

    client, collection = emulator
    namespace = collection.removesuffix('_provider_stt_outbox')
    store = FirestoreStore(namespace, firestore_client=client)
    customer = ClientCustomerData(client)
    owner = f'provider-{uuid.uuid4().hex[:8]}'
    customer.add_user(owner)
    customer.add_conversation(owner, 'conv-1')
    segment, token = _segment('result'), uuid.uuid4().hex
    jobs = client.collection(f'{namespace}_jobs')
    jobs.document(segment).set(
        {
            'owner_id': owner,
            'conversation_id': 'conv-1',
            'state': 'provider_running',
            'provider_intent': {'token': token, 'service': 'modulate', 'privacy_generation': 0},
        }
    )
    try:
        prefix = f'gs://synthetic/{owner}/results/{segment}'
        assert register_batch_artifact(store, owner, segment, f'{prefix}/{token}.enc', 'results', 0)
        with pytest.raises(BatchPrivacyBlocked):
            register_batch_artifact(store, owner, segment, f'{prefix}/{uuid.uuid4().hex}.enc', 'results', 0)
        jobs.document(segment).update({'state': 'provider_pending'})
        with pytest.raises(BatchPrivacyBlocked):
            register_batch_artifact(store, owner, segment, f'{prefix}/{token}.enc', 'results', 0)
    finally:
        jobs.document(segment).delete()
        for doc in client.collection(f'{namespace}_artifacts').stream():
            doc.reference.delete()
