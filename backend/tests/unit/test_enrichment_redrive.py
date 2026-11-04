"""Scoped re-wakes preserve accepted debt and cannot bypass live work or privacy."""

from copy import deepcopy
from types import SimpleNamespace

import pytest

from database import batch_pipeline_privacy
from utils.enrichment import outbox, redrive

KEY = outbox.key('synthetic-owner', 'synthetic-conversation')
NOW = 10000.0


@pytest.fixture
def store(monkeypatch):
    row = {
        'uid': 'synthetic-owner',
        'conversation_id': 'synthetic-conversation',
        'version': 7,
        'task_token': 'a' * 32,
        'first_pending_at': 100,
        'summary_deadline_at': 220,
        'due_at': 700,
        'task_due_at': 700,
        'lease_until': 0,
        'sync_hold': True,
        'dispatch': {
            'queue': 'enrichment',
            'handler': 'https://worker.invalid/v2/enrichment/run',
            'audience': 'https://worker.invalid/v2/enrichment/run',
            'invoker_sa': 'synthetic@example.invalid',
        },
    }
    conversation = {'status': 'completed', 'sync_processing_hold': {'held': True, 'pending_since': 100}}
    docs = {
        'sync_reprocess_outbox/' + KEY: row,
        'users/synthetic-owner/conversations/synthetic-conversation': conversation,
    }
    jobs = [{'owner_id': 'synthetic-owner', 'state': 'committed'}]
    writes, wakes = [], []

    class Ref:
        def __init__(self, path):
            self.path = path

        def document(self, key):
            return Ref(self.path + '/' + key)

        def collection(self, name):
            return Ref(self.path + '/' + name)

        def get(self, transaction, **_):
            assert not transaction.written, 'read after write'
            return SimpleNamespace(to_dict=lambda: deepcopy(docs.get(self.path)))

        def where(self, **_):
            return self

        def select(self, *_):
            return self

        def limit(self, *_):
            return self

        def stream(self, transaction):
            assert not transaction.written, 'query after write'
            return [SimpleNamespace(id=str(i), to_dict=lambda j=j: deepcopy(j)) for i, j in enumerate(jobs)]

    class Transaction:
        written = False

        def set(self, ref, value):
            self.written = True
            docs[ref.path] = deepcopy(value)
            writes.append(deepcopy(value))

    client = SimpleNamespace(collection=lambda name: Ref(name), transaction=Transaction)
    monkeypatch.setattr(redrive.firestore, 'transactional', lambda fn: fn)
    privacy = []

    def allowed(_client, transaction, uid, **kwargs):
        assert not transaction.written
        privacy.append((uid, kwargs['conversation_ids']))

    monkeypatch.setattr(batch_pipeline_privacy, 'assert_batch_write_allowed', allowed)
    monkeypatch.setattr(outbox, 'wake_row', lambda row: wakes.append(deepcopy(row)))
    return client, docs, jobs, writes, wakes, privacy


def test_dry_run_reads_eligibility_without_mutation_or_wake(store):
    client, _, _, writes, wakes, privacy = store
    assert redrive.redrive(client, KEY, 'same-run', now=NOW) == 'eligible'
    assert not writes and not wakes and privacy


def test_apply_changes_only_repair_metadata_and_retries_same_name_after_lost_ack(store, monkeypatch):
    client, docs, _, writes, wakes, _ = store
    before = deepcopy(docs['sync_reprocess_outbox/' + KEY])
    wake = outbox.wake_row

    def lost(row):
        wake(row)
        raise RuntimeError('synthetic lost enqueue acknowledgement')

    monkeypatch.setattr(outbox, 'wake_row', lost)
    with pytest.raises(RuntimeError):
        redrive.redrive(client, KEY, 'same-run', now=NOW, apply=True)
    first_name = outbox._task_name(wakes[0])
    monkeypatch.setattr(outbox, 'wake_row', wake)
    assert redrive.redrive(client, KEY, 'same-run', now=NOW + 1, apply=True) == 'rewoken'
    assert len(writes) == 1 and outbox._task_name(wakes[1]) == first_name
    assert first_name.endswith('-repair-1')
    changed = docs['sync_reprocess_outbox/' + KEY]
    assert {k: changed[k] for k in before if k != 'task_due_at'} == {
        k: v for k, v in before.items() if k != 'task_due_at'
    }


@pytest.mark.parametrize('cause', ['leased', 'titled', 'deleted', 'recent', 'pending', 'owner', 'blocked'])
def test_current_state_can_refuse_a_prepared_plan(store, cause):
    client, docs, jobs, writes, wakes, _ = store
    row = docs['sync_reprocess_outbox/' + KEY]
    conversation = docs['users/synthetic-owner/conversations/synthetic-conversation']
    if cause == 'leased':
        row['lease_until'] = NOW + 1
    if cause == 'titled':
        conversation['structured'] = {'title': 'Synthetic persisted title'}
    if cause == 'deleted':
        conversation['deleted'] = True
    if cause == 'recent':
        conversation['sync_processing_hold']['pending_since'] = NOW - 100
    if cause == 'pending':
        jobs[0]['state'] = 'record_pending'
    if cause == 'owner':
        jobs[0]['owner_id'] = 'other-synthetic-owner'
    if cause == 'blocked':
        row['summary_blocked_reason'] = 'empty_output_exhausted'
    assert redrive.redrive(client, KEY, 'same-run', now=NOW, apply=True) != 'rewoken'
    assert not writes and not wakes


def test_privacy_refusal_preserves_outbox(store, monkeypatch):
    client, _, _, writes, wakes, _ = store

    def denied(*_, **__):
        raise batch_pipeline_privacy.BatchPrivacyBlocked('account_deleted')

    monkeypatch.setattr(batch_pipeline_privacy, 'assert_batch_write_allowed', denied)
    assert redrive.redrive(client, KEY, 'same-run', now=NOW, apply=True) == 'privacy'
    assert not writes and not wakes


def test_new_run_id_cannot_mint_another_repair_name(store):
    client, _, _, writes, wakes, _ = store
    assert redrive.redrive(client, KEY, 'same-run', now=NOW, apply=True) == 'rewoken'
    with pytest.raises(ValueError, match='already pinned'):
        redrive.redrive(client, KEY, 'different-run', now=NOW + 1, apply=True)
    assert len(writes) == 1 and len(wakes) == 1
