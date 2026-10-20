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
