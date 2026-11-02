"""Provider-STT Firestore outbox: contract (b) invariants on an in-memory CAS fake (synthetic only)."""

import hashlib
from types import SimpleNamespace

import pytest
from google.api_core.exceptions import AlreadyExists, FailedPrecondition

from google.cloud import firestore  # noqa: F401  # warm the CAS path's lazy import outside the call budget

from database import outbox_firestore
from database.outbox import Claim, OutboxKind, Outcome
from utils import cloud_tasks, provider_stt_tasks
from database.outbox_provider_stt import REWAKE_AFTER_SECONDS, FirestoreProviderSttOutbox, collection_name, task_name

ROW = hashlib.sha256(b'content:0').hexdigest()
OWNER = 'synthetic-owner'


class Doc:
    def __init__(self, store, key):
        self.store, self.key, self.id = store, key, key[1]

    def get(self, transaction=None):
        data = self.store.rows.get(self.key)
        return SimpleNamespace(
            exists=data is not None,
            to_dict=lambda: dict(data) if data is not None else None,
            update_time=self.store.versions.get(self.key),
            id=self.key[1],
        )

    def create(self, data):
        if self.key in self.store.rows:
            raise AlreadyExists('exists')
        self.store.write(self.key, data)

    def update(self, data, option=None):
        if option is not None and getattr(option, '_last_update_time') != self.store.versions.get(self.key):
            raise FailedPrecondition('stale')
        self.store.write(self.key, {**self.store.rows[self.key], **data})


class Query:
    def __init__(self, store, name, filters=(), limit=None):
        self.store, self.name, self.filters, self._limit = store, name, filters, limit

    def where(self, *, filter):
        return Query(self.store, self.name, (*self.filters, filter), self._limit)

    def limit(self, n):
        return Query(self.store, self.name, self.filters, n)

    def stream(self):
        out = []
        for (name, key), row in sorted(self.store.rows.items()):
            if name == self.name and all(row.get(f.field_path) == f.value for f in self.filters):
                out.append(SimpleNamespace(id=key, to_dict=lambda row=row: dict(row)))
        return out[: self._limit]


class Collection:
    def __init__(self, store, name):
        self.store, self.name = store, name

    def document(self, key):
        return Doc(self.store, (self.name, key))

    def where(self, *, filter):
        return Query(self.store, self.name).where(filter=filter)


class Fake:
    def __init__(self):
        self.rows, self.versions, self.clock = {}, {}, 0

    def write(self, key, data):
        self.clock += 1
        self.rows[key], self.versions[key] = dict(data), self.clock

    def collection(self, name):
        return Collection(self, name)


@pytest.fixture
def box():
    client, woken, blocked = Fake(), [], set()
    outbox = FirestoreProviderSttOutbox(
        client,
        privacy_blocked=lambda owner_id, payload: payload['segment_id'] in blocked,
        create_wake=lambda row_id, token, available_at: woken.append(token),
        collection='batch_pipeline_test_provider_stt_outbox',
    )
    return SimpleNamespace(outbox=outbox, client=client, woken=woken, blocked=blocked)


def row(box):
    return box.client.rows[('batch_pipeline_test_provider_stt_outbox', ROW)]


def enqueue(box, now=100.0, available_at=100.0, **kwargs):
    return box.outbox.enqueue(ROW, OWNER, {'segment_id': ROW}, available_at, now=now, **kwargs)


def test_collection_is_stage_scoped_and_task_names_are_bounded():
    assert collection_name('prod') != collection_name('dev')
    name = task_name(ROW, 'a' * 32)
    assert name.startswith('pst-') and len(name) <= 100


def test_enqueue_is_durable_before_wake_and_coalesces(box):
    first = enqueue(box)
    assert not first.coalesced and box.woken == [first.wake_token] == [row(box)['task_token']]
    again = enqueue(box, now=101.0)
    assert again.coalesced and again.wake_token is None and len(box.woken) == 1
    with pytest.raises(ValueError):
        box.outbox.enqueue('not-a-segment', OWNER, {'segment_id': 'not-a-segment'}, 100.0, now=100.0)


def test_transactional_enqueue_writes_in_the_callers_transaction_and_does_not_wake(box):
    staged = {}
    transaction = SimpleNamespace(set=lambda ref, data: staged.update({ref.key: data}))
    tx = SimpleNamespace(transaction=transaction, client=box.client)
    result = enqueue(box, tx=tx)
    assert result.wake_token and box.woken == [] and not box.client.rows
    (((_, key), data),) = staged.items()
    assert key == ROW and data['task_token'] == result.wake_token and data['state'] == 'open'
    box.client.write(('batch_pipeline_test_provider_stt_outbox', ROW), data)  # commit
    box.outbox.wake(ROW, result.wake_token)
    box.outbox.wake(ROW, 'f' * 32)  # superseded token: no task
    assert box.woken == [result.wake_token]


def test_claim_fencing_busy_stale_and_expired_lease(box):
    token = enqueue(box).wake_token
    assert box.outbox.claim_key(ROW, 'f' * 32, 1800, now=200.0) is Outcome.STALE
    claim = box.outbox.claim_key(ROW, token, 1800, now=200.0)
    assert isinstance(claim, Claim) and claim.kind is OutboxKind.PROVIDER_STT and claim.attempt == 1
    assert claim.payload == {'segment_id': ROW} and claim.owner_id == OWNER
    assert box.outbox.claim_key(ROW, token, 1800, now=300.0) is Outcome.BUSY
    assert box.outbox.heartbeat(claim, 1800, now=300.0)
    later = box.outbox.claim_key(ROW, token, 1800, now=200.0 + 1800 + 301)
    assert isinstance(later, Claim) and later.lease_token != claim.lease_token and later.attempt == 2
    assert box.outbox.ack(claim, 'processed', now=2400.0) is False  # the old holder is fenced out
    assert box.outbox.ack(later, 'processed', now=2400.0) is True
    assert row(box)['state'] == 'closed' and row(box)['closed_reason'] == 'processed'
    assert box.outbox.claim_key(ROW, token, 1800, now=2500.0) is Outcome.STALE


def test_not_due_and_defer_mint_new_wakes(box):
    token = enqueue(box, available_at=500.0).wake_token
    assert box.outbox.claim_key(ROW, token, 1800, now=200.0) is Outcome.DEFERRED
    fresh = row(box)['task_token']
    assert fresh != token and box.woken[-1] == fresh
    assert box.outbox.claim_key(ROW, token, 1800, now=600.0) is Outcome.STALE
    claim = box.outbox.claim_key(ROW, fresh, 1800, now=600.0)
    new = box.outbox.defer(claim, 700.0, 'not_due', now=600.0)
    assert new and new != fresh and box.woken[-1] == new and row(box)['lease_token'] is None
    assert box.outbox.defer(claim, 800.0, 'not_due', now=600.0) is None  # stale lease


def test_release_keeps_the_wake_for_the_queue_retry(box):
    token = enqueue(box).wake_token
    claim = box.outbox.claim_key(ROW, token, 1800, now=200.0)
    assert box.outbox.release(claim, 'dependency_warming', now=201.0)
    assert row(box)['task_token'] == token and row(box)['lease_until'] == 0.0
    assert isinstance(box.outbox.claim_key(ROW, token, 1800, now=202.0), Claim)


def test_privacy_fenced_rows_are_discarded_at_claim_and_sweep(box):
    token = enqueue(box).wake_token
    box.blocked.add(ROW)
    assert box.outbox.claim_key(ROW, token, 1800, now=200.0) is Outcome.DISCARDED
    assert row(box)['state'] == 'closed' and row(box)['closed_reason'] == 'privacy_blocked'
    box.client.rows.clear()
    enqueue(box)
    assert box.outbox.sweep(now=200.0).discarded == 1


def test_sweep_rewakes_only_lost_wakes(box):
    enqueue(box)
    assert box.outbox.sweep(now=200.0).rewoken == 0  # the first wake may still be queued
    counts = box.outbox.sweep(now=100.0 + REWAKE_AFTER_SECONDS + 1)
    assert counts.rewoken == 1 and box.woken[-1] == row(box)['task_token']
    claim = box.outbox.claim_key(ROW, row(box)['task_token'], 60, now=1000.0)
    assert box.outbox.sweep(now=1030.0).rewoken == 0  # live lease
    counts = box.outbox.sweep(now=1000.0 + 60 + REWAKE_AFTER_SECONDS)
    assert counts.expired_leases == 1 and counts.rewoken == 1
    assert box.outbox.ack(claim, 'processed', now=2000.0) is False


def test_pull_claims_due_unleased_rows(box):
    enqueue(box, available_at=500.0)
    assert box.outbox.claim(4, 1800, now=200.0) == []
    (claim,) = box.outbox.claim(4, 1800, now=600.0)
    assert claim.row_id == ROW


def test_selector_and_factory_return_the_provider_outbox():
    assert isinstance(outbox_firestore.firestore_outbox(OutboxKind.PROVIDER_STT), FirestoreProviderSttOutbox)
    built = outbox_firestore.FirestoreOutbox(OutboxKind.PROVIDER_STT, client=Fake())
    assert isinstance(built, FirestoreProviderSttOutbox)


def test_wake_task_shape(monkeypatch):
    sent = []
    monkeypatch.setattr(cloud_tasks, 'enqueue_named_task', lambda *a, **k: sent.append((a, k)))
    monkeypatch.setenv('PROVIDER_STT_TASKS_HANDLER_URL', 'https://workers.example/')
    monkeypatch.setenv('PROVIDER_STT_TASKS_QUEUE', 'provider-stt')
    monkeypatch.delenv('PROVIDER_STT_TASKS_OIDC_AUDIENCE', raising=False)
    provider_stt_tasks.create_wake(ROW, 'a' * 32, due_at=1234.2)
    ((args, kwargs),) = sent
    assert args == (
        'provider-stt',
        'https://workers.example/v2/batch-pipeline/provider-stt/run',
        task_name(ROW, 'a' * 32),
        {'kind': 'provider_stt', 'row_id': ROW, 'wake_token': 'a' * 32},
    )
    assert kwargs['audience'] == 'https://workers.example' and kwargs['schedule_at'] == 1235
    monkeypatch.delenv('PROVIDER_STT_TASKS_QUEUE')
    with pytest.raises(RuntimeError):
        provider_stt_tasks.create_wake(ROW, 'a' * 32, due_at=0)
