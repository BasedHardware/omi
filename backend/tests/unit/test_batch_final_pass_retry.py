"""Dedicated retry custody: bounded model work, identity-only writes, duplicate wakes."""

import threading
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from types import SimpleNamespace

import pytest

from database.batch_final_pass_retry import MAX_ATTEMPTS, LEASE_SECONDS, backoff
from tests.unit.fixtures.speaker_final_pass_retry import retry_state  # noqa: F401
from tests.unit.test_batch_final_pass import prod_shaped, run_prod, UID, batch_outcome_counts  # noqa: F401
from utils.conversations import final_pass_batch as batch, final_pass_retry as retry


@pytest.fixture
def ready(prod_shaped, retry_state, monkeypatch):
    from database import conversations, speaker_resolution_updates
    from utils.conversations import speaker_resolution, process_conversation
    from utils.enrichment import callback

    raw = prod_shaped.conversation.model_dump()
    raw.update(status='completed', _recovery_transcript_decoded=True, updated_at=raw['created_at'])
    writes = []
    monkeypatch.setattr(conversations, 'get_conversation', lambda *a, **kw: deepcopy(raw))
    monkeypatch.setattr(conversations, 'get_manual_speaker_receipt', lambda *a: {})
    monkeypatch.setattr(speaker_resolution, 'load_voiceprints_for_resolution', lambda *a, **kw: {'user': [1.0, 0.0]})
    monkeypatch.setattr(
        speaker_resolution_updates,
        'persist_speaker_resolution_if_current',
        lambda uid, data, **kw: writes.append((uid, data, kw)) or True,
    )
    monkeypatch.setattr(callback, 'enrich_conversation', lambda *a, **kw: pytest.fail('full enrichment replayed'))
    monkeypatch.setattr(
        process_conversation, 'process_conversation', lambda *a, **kw: pytest.fail('notes pipeline replayed')
    )
    return SimpleNamespace(lane=prod_shaped, state=retry_state, writes=writes, raw=raw)


def next_wake(state):
    key, row = next(iter(state.rows.items()))
    state.clock[0] = row['due_at'] + 1
    return key, row['token']


def test_slot_retry_cap_counts_exhaustion_once_and_duplicate_wakes_are_stale(ready, monkeypatch):
    slot = threading.BoundedSemaphore(1)
    assert slot.acquire()
    monkeypatch.setattr(batch, '_SLOTS', slot)
    before = batch_outcome_counts()
    try:
        assert run_prod(ready.lane)['outcome'] == 'deferred_slot_busy'
        for attempt in range(1, MAX_ATTEMPTS + 1):
            key, token = next_wake(ready.state)
            result = retry.consume(key, token)
            assert ready.state.rows[key]['attempts'] == attempt
            assert result['outcome'] == ('skipped_slot_exhausted' if attempt == MAX_ATTEMPTS else 'deferred_slot_busy')
        assert retry.consume(key, token)['outcome'] == 'stale'
        assert retry.enqueue(UID, ready.lane.conversation)['outcome'] == 'skipped_slot_exhausted'
    finally:
        slot.release()
    # Even after capacity returns, the terminal receipt cannot reopen this obligation.
    assert retry.consume(key, token)['outcome'] == 'stale'
    assert not ready.lane.gpu and not ready.writes
    after = batch_outcome_counts()
    assert sum(after.values()) - sum(before.values()) == 1
    assert (
        sum(
            value - before.get(labels, 0)
            for labels, value in after.items()
            if dict(labels)['outcome'] == 'skipped_slot_exhausted'
        )
        == 1
    )


def test_retry_runs_only_final_pass_and_commits_identity_through_revision_fence(ready):
    before = batch_outcome_counts()
    retry.enqueue(UID, ready.lane.conversation)
    key, token = next_wake(ready.state)
    assert retry.consume(key, token)['outcome'] == 'success'
    assert len(ready.lane.gpu) == 1 and len(ready.writes) == 1
    uid, data, kwargs = ready.writes[0]
    assert uid == UID and kwargs == {'expected_updated_at': ready.raw.get('updated_at')}
    assert data['structured'] == ready.raw['structured']  # no notes regeneration
    assert retry.consume(key, token)['outcome'] == 'stale'
    assert sum(batch_outcome_counts().values()) - sum(before.values()) == 1


def test_concurrent_duplicate_wake_does_not_start_second_pass(ready, monkeypatch):
    entered, release = threading.Event(), threading.Event()
    calls = []

    def run_only(*args):
        calls.append(True)
        entered.set()
        assert release.wait(2)
        return {'outcome': 'success'}

    monkeypatch.setattr(retry, 'run_only', run_only)
    retry.enqueue(UID, ready.lane.conversation)
    key, token = next_wake(ready.state)
    before = batch_outcome_counts()
    with ThreadPoolExecutor(max_workers=1) as pool:
        first = pool.submit(retry.consume, key, token)
        try:
            assert entered.wait(2)
            assert retry.consume(key, token)['outcome'] == 'stale'
        finally:
            release.set()
        assert first.result(timeout=2)['outcome'] == 'success'
    assert len(calls) == 1
    assert sum(batch_outcome_counts().values()) - sum(before.values()) == 1


def test_lost_wake_is_repaired_without_reopening_or_replaying_enrichment(ready, monkeypatch):
    wake = retry._wake
    monkeypatch.setattr(retry, '_wake', lambda *a: (_ for _ in ()).throw(RuntimeError('synthetic queue error')))
    assert retry.enqueue(UID, ready.lane.conversation)['outcome'] == 'deferred_slot_busy'
    key, old_token = next_wake(ready.state)
    ready.state.clock[0] = ready.state.rows[key]['repair_after'] + 1
    monkeypatch.setattr(retry, '_wake', wake)
    assert retry.sweep(now=ready.state.clock[0]) == 1
    assert ready.state.rows[key]['token'] != old_token
    assert retry.consume(key, old_token)['outcome'] == 'stale'
    key, token = next_wake(ready.state)
    assert retry.consume(key, token)['outcome'] == 'success'
    assert retry.sweep(now=ready.state.clock[0] + 10000) == 0


def test_expired_leases_do_not_reset_attempt_cap(ready):
    retry.enqueue(UID, ready.lane.conversation)
    for _ in range(MAX_ATTEMPTS):
        key, token = next_wake(ready.state)
        state, row = ready.state.store.claim(key, token, now=ready.state.clock[0])
        assert state == 'claimed'
        ready.state.clock[0] += LEASE_SECONDS + 1
        assert retry.sweep(now=ready.state.clock[0]) == 1
    before = batch_outcome_counts()
    key, token = next_wake(ready.state)
    assert retry.consume(key, token)['outcome'] == 'skipped_retry_exhausted'
    assert retry.consume(key, token)['outcome'] == 'stale'
    assert sum(batch_outcome_counts().values()) - sum(before.values()) == 1
    assert not ready.lane.gpu


def test_scope_membership_can_create_new_obligation_but_summary_writes_cannot(ready):
    retry.enqueue(UID, ready.lane.conversation)
    original = next(iter(ready.state.rows))
    ready.state.rows[original].update(outcome='skipped_slot_exhausted', attempts=MAX_ATTEMPTS)
    ready.lane.conversation.structured.title = 'Synthetic updated summary'
    assert retry.enqueue(UID, ready.lane.conversation)['outcome'] == 'skipped_slot_exhausted'
    segment = ready.lane.conversation.transcript_segments[0].model_copy(deep=True)
    segment.id, segment.speaker_id_scope = 'new-segment', 'final:batch:unit-b'
    ready.lane.conversation.transcript_segments.append(segment)
    assert retry.enqueue(UID, ready.lane.conversation)['outcome'] == 'deferred_slot_busy'
    assert len(ready.state.rows) == 2 and ready.state.rows[original]['attempts'] == MAX_ATTEMPTS


def test_backoff_is_jittered_and_bounded(monkeypatch):
    seen = []
    monkeypatch.setattr('database.batch_final_pass_retry.random.uniform', lambda lo, hi: seen.append((lo, hi)) or 1)
    assert [backoff(n) for n in range(5)] == [30, 60, 120, 240, 240]
    assert seen == [(0.5, 1.5)] * 5


def test_cas_removes_due_field_when_closing_receipt():
    from datetime import datetime, timezone
    from google.cloud import firestore
    from database.outbox_cas import mutate

    changes = []
    snapshot = SimpleNamespace(
        exists=True, update_time=datetime.now(timezone.utc), to_dict=lambda: {'due_at': 1000, 'outcome': None}
    )
    ref = SimpleNamespace(get=lambda: snapshot, update=lambda data, **kw: changes.append(data))
    assert mutate(ref, lambda old: ({'outcome': 'success'}, True))
    assert changes == [{'outcome': 'success', 'due_at': firestore.DELETE_FIELD}]


@pytest.mark.parametrize('edge', ['enrichment', 'sync'])
def test_existing_task_edges_dispatch_speaker_kind_without_enrichment(ready, monkeypatch, edge):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from routers import enrichment, sync

    monkeypatch.setenv('OMI_ENV_STAGE', 'offline')
    monkeypatch.setattr(sync.uid_sequencer, 'production_fence_mode', lambda: sync.SyncLedgerFenceMode.LEGACY)
    monkeypatch.setattr(sync, 'enrichment_response', lambda *a: pytest.fail('full enrichment route called'))
    monkeypatch.setattr(enrichment, 'consume', lambda *a: pytest.fail('full enrichment consumer called'))
    module = enrichment if edge == 'enrichment' else sync
    app = FastAPI()
    app.include_router(module.router)
    dependency = enrichment.verify_enrichment_task if edge == 'enrichment' else sync.verify_cloud_tasks_oidc
    app.dependency_overrides[dependency] = lambda: 0

    retry.enqueue(UID, ready.lane.conversation)
    key, token = next_wake(ready.state)

    path = '/v2/enrichment/run' if edge == 'enrichment' else '/v2/sync-jobs/run'
    with TestClient(app) as client:
        response = client.post(path, json={'kind': 'batch_final_pass', 'key': key, 'task_token': token})
    assert response.status_code == 200 and response.json()['outcome'] == 'success'
    assert len(ready.writes) == 1


def test_queued_wake_survives_sweep_and_does_not_pin_repair_discovery(ready, monkeypatch):
    retry.enqueue(UID, ready.lane.conversation)
    key = next(iter(ready.state.rows))
    original = deepcopy(ready.state.rows[key])
    ready.state.clock[0] = original['repair_after'] + 1
    monkeypatch.setattr(retry, '_exists', lambda *args: True)
    assert retry.sweep(now=ready.state.clock[0]) == 0
    row = ready.state.rows[key]
    assert row['token'] == original['token'] and row['due_at'] == original['due_at']
    assert row['repair_after'] > ready.state.clock[0]
    assert not ready.state.store.due(now=ready.state.clock[0])


def test_identity_only_retry_does_not_invalidate_its_own_revision_by_learning(ready, monkeypatch):
    monkeypatch.setattr(batch.recurring_voices, 'checkpoint', lambda *a, **kw: ('synthetic',))
    monkeypatch.setattr(
        batch.recurring_voices, 'learn', lambda *a, **kw: pytest.fail('learning would invalidate identity CAS')
    )
    retry.enqueue(UID, ready.lane.conversation)
    key, token = next_wake(ready.state)
    assert retry.consume(key, token)['outcome'] == 'success'
    assert len(ready.writes) == 1


def test_changed_revision_retries_within_same_cap_without_counting_success(ready, monkeypatch):
    from database import speaker_resolution_updates

    monkeypatch.setattr(speaker_resolution_updates, 'persist_speaker_resolution_if_current', lambda *a, **kw: False)
    retry.enqueue(UID, ready.lane.conversation)
    before = batch_outcome_counts()
    for _ in range(MAX_ATTEMPTS):
        key, token = next_wake(ready.state)
        result = retry.consume(key, token)
    assert result['outcome'] == 'skipped_retry_exhausted'
    assert sum(batch_outcome_counts().values()) - sum(before.values()) == 1
