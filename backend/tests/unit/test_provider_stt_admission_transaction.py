"""C8 provider admission on a real-shape Firestore transaction (synthetic only).

The batch admission transaction buffers its own writes until ``flush``, which then reads privacy
state. The provider-STT outbox row joins that transaction from outside the batch tables; written
straight to the raw transaction, it made every later read a read-after-write, which real Firestore
refuses (staging 11-01: every unsupported-language upload answered 503). StrictFirestore enforces
the same rule, so these run the real admit(), FirestoreTransaction view and Firestore outbox.
"""

import hashlib

import pytest

from database import batch_pipeline_intake
from database import sync_ledger  # noqa: F401  # warm legacy_dark's lazy ledger import
from database.batch_pipeline_store import FirestoreStore
from database.outbox_provider_stt import FirestoreProviderSttOutbox
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from utils.batch_pipeline import admission  # noqa: F401  # warm its imports outside the call
from utils.batch_pipeline import provider_stt
from utils.batch_pipeline.contracts import Priority, ProjectionBinding, WorkItem
from utils.batch_pipeline.provider_stt import PENDING, SttRoute

OWNER = 'synthetic-owner'
OUTBOX = 'batch_pipeline_prod_provider_stt_outbox'
P1, P2 = (hashlib.sha256(f'content-p:{n}'.encode()).hexdigest() for n in (0, 1))
JA = SttRoute('provider', 'unsupported_language', 'modulate', 'ja')


@pytest.fixture
def world(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_PERCENT', '100')
    monkeypatch.setenv('OMI_ENV_STAGE', 'prod')
    client = StrictFirestore(
        {
            ('users', OWNER): {'id': OWNER, 'data_protection_level': 'enhanced'},
            ('users', OWNER, 'conversations', 'conv-1'): {'id': 'conv-1', 'status': 'completed'},
        }
    )
    woken = []
    outbox = FirestoreProviderSttOutbox(
        client,
        privacy_blocked=lambda owner_id, payload: False,
        create_wake=lambda row_id, token, available_at: woken.append(row_id),
        collection=OUTBOX,
    )
    return client, FirestoreStore('batch_pipeline_prod', firestore_client=client), outbox, woken


def item(segment_id, capture_at):
    return WorkItem(
        segment_id,
        OWNER,
        capture_at,
        f'gs://synthetic/audio/{segment_id}',
        5.0,
        Priority.FRESH,
        conversation_id='conv-1',
        privacy_generation=0,
        requires_compute_admission=False,
    )


def admit(store, outbox, items, content_id, wakes):
    binding = ProjectionBinding(
        OWNER, 'bp_' + content_id, content_id, tuple(i.segment_id for i in items), language='ja'
    )
    return batch_pipeline_intake.admit(
        store,
        items,
        binding,
        100.0,
        namespace=store.namespace,
        enqueue=provider_stt.provider_enqueue(JA, outbox, wakes),
    )


@pytest.mark.parametrize('segments', [(P1,), (P1, P2)], ids=['one-unit', 'two-units'])
def test_provider_admission_commits_job_and_outbox_row_in_one_transaction(world, segments):
    client, store, outbox, woken = world
    wakes: dict[str, str] = {}
    outcome = admit(store, outbox, [item(sid, 10 + n) for n, sid in enumerate(segments)], 'content-p', wakes)
    assert outcome['outcome'] == 'batch'
    for sid in segments:
        assert client.rows[('batch_pipeline_prod_jobs', sid)]['state'] == PENDING
        assert client.rows[(OUTBOX, sid)]['state'] == 'open'
    # The wake waits for the commit (contract (b), invariant 4): the caller wakes each row after.
    assert set(wakes) == set(segments) and woken == []


def test_readmission_coalesces_the_open_outbox_row(world):
    client, store, outbox, _ = world
    admit(store, outbox, [item(P1, 10)], 'content-p', {})
    first = client.rows[(OUTBOX, P1)]
    again: dict[str, str] = {}
    admit(store, outbox, [item(P1, 10)], 'content-p', again)
    assert client.rows[(OUTBOX, P1)]['task_token'] == first['task_token'] and again == {}
