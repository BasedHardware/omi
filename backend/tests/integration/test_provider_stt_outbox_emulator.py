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


def test_job_side_sweep_reaches_ancient_open_missing_and_closed_wakes(emulator):
    from config.batch_pipeline_retention import LIFECYCLE_SECONDS

    client, collection = emulator
    owner = f'provider-repair-{uuid.uuid4().hex[:8]}'
    ClientCustomerData(client).add_user(owner)
    wakes: list = []
    outbox = _outbox(client, collection, wakes)
    jobs = client.collection(f"{collection.removesuffix('_provider_stt_outbox')}_jobs")
    now = LIFECYCLE_SECONDS + 10_000
    segments = {label: _segment(label) for label in ('ancient', 'missing', 'closed', 'live', 'recent', 'settled')}
    for label, segment in segments.items():
        jobs.document(segment).set(
            {
                'state': 'result_ready' if label == 'settled' else 'provider_running',
                'enqueued_at': now - 1 if label == 'recent' else 100.0,
                'owner_id': owner,
            }
        )

    ancient = segments['ancient']
    initial = outbox.enqueue(ancient, owner, {'segment_id': ancient}, 100.0, now=100.0)
    assert outbox.sweep(now=now).rewoken == 0

    closed = segments['closed']
    initial_closed = outbox.enqueue(closed, owner, {'segment_id': closed}, 100.0, now=100.0)
    claim = outbox.claim_key(closed, initial_closed.wake_token, 1800, now=101.0)
    assert isinstance(claim, Claim) and outbox.ack(claim, 'processed', now=110.0)

    live = segments['live']
    active = outbox.enqueue(live, owner, {'segment_id': live}, now - 1, now=now - 1)
    assert isinstance(outbox.claim_key(live, active.wake_token, 1800, now=now - 1), Claim)
    wakes.clear()

    # Four matching jobs share the same timestamp. A two-row page must reach both pages,
    # including past the live lease, and a subsequent pass must respect the new tokens.
    assert sum(outbox.sweep_running(now=now, limit=2)[0] for _ in range(3)) == 3
    assert {segment for segment, _, _ in wakes} == {segments[key] for key in ('ancient', 'missing', 'closed')}
    assert outbox.claim_key(ancient, initial.wake_token, 1800, now=now) is Outcome.STALE
    assert all(outbox.sweep_running(now=now, limit=2) == (0, 0) for _ in range(3))
    assert outbox.claim_key(live, active.wake_token, 1800, now=now) is Outcome.BUSY


def test_held_sweep_rewakes_only_overdue_holds_whose_wake_was_lost(emulator):
    from config.batch_pipeline_retention import LIFECYCLE_SECONDS
    from database.outbox_provider_stt import REWAKE_AFTER_SECONDS

    client, collection = emulator
    owner = f'provider-held-{uuid.uuid4().hex[:8]}'
    ClientCustomerData(client).add_user(owner)
    wakes: list = []
    outbox = _outbox(client, collection, wakes)
    jobs = client.collection(f"{collection.removesuffix('_provider_stt_outbox')}_jobs")
    now = LIFECYCLE_SECONDS + 1_000_000.0
    overdue = now - 10 * REWAKE_AFTER_SECONDS
    labels = ('lost', 'missing', 'closed', 'future', 'fresh_wake', 'ancient', 'pending')
    segments = {label: _segment(label) for label in labels}
    for label, segment in segments.items():
        redrive_at = now + 300 if label == 'future' else overdue
        jobs.document(segment).set(
            {
                'state': 'provider_pending' if label == 'pending' else 'vendor_held',
                'enqueued_at': now - LIFECYCLE_SECONDS - 1 if label == 'ancient' else now - 86400,
                'owner_id': owner,
                'vendor_hold': {'reason': 'rate_limited', 'redrive_at': redrive_at},
            }
        )
        if label != 'missing':
            queued = outbox.enqueue(segment, owner, {'segment_id': segment}, redrive_at, now=now - 86400)
            if label == 'closed':
                claim = outbox.claim_key(segment, queued.wake_token, 1800, now=overdue)
                assert isinstance(claim, Claim) and outbox.ack(claim, 'processed', now=overdue)
    outbox._mutate(segments['fresh_wake'], lambda old: ({**old, 'woken_at': now - 1}, None))
    wakes.clear()

    # Two-row pages reach every held job; only overdue holds inside the audio lifecycle whose wake is
    # not fresh are re-armed. An open row keeps its due time; a missing or closed row is recreated due now.
    assert sum(outbox.sweep_held(now=now, limit=2)[0] for _ in range(4)) == 3
    due = {segment: at for segment, _, at in wakes}
    assert due == {segments['lost']: overdue, segments['missing']: now, segments['closed']: now}
    assert all(outbox.sweep_held(now=now, limit=2) == (0, 0) for _ in range(4))
