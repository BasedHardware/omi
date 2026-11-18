"""HTTP contract of DELETE /v2/sync-local-files/{job_id} over the real fence on a snapshot store."""

from contextlib import contextmanager

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

import routers.sync as sync_router
import utils.sync.owner_cancel_endpoint as router
from database.legal_holds import LegalHoldActive
from tests.unit.test_batch_pipeline_scheduler import MemoryStore
from tests.unit.test_sync_owner_cancel import FakeEraser, JOB, OWNER, OTHER, admit
from utils.other import endpoints as auth


@pytest.fixture
def api(monkeypatch):
    store = MemoryStore()
    eraser = FakeEraser(store)
    gates = []

    @contextmanager
    def gate(uid, *, kind, wait_seconds):
        gates.append((uid, kind))
        yield 'token'

    monkeypatch.setenv('OMI_ENV_STAGE', 'prod')
    monkeypatch.delenv('SYNC_JOB_OWNER_CANCEL_ENABLED', raising=False)
    monkeypatch.setattr(router, 'admit_sync_job_poll', lambda uid: True)
    monkeypatch.setattr(sync_router, 'admit_sync_job_poll', lambda uid: True)
    monkeypatch.setattr(router, 'destructive_operation_gate', gate)
    monkeypatch.setattr(router, 'FirestoreStore', lambda namespace: store)
    monkeypatch.setattr(router, 'shadow_from_env', lambda primary: primary)
    monkeypatch.setattr(router, 'FirestoreEraser', lambda namespace: eraser)
    monkeypatch.setattr(router, 'FirestoreLegacyStore', lambda: None)
    app = FastAPI()
    app.include_router(sync_router.router)  # mounts the cancel route beside the status poll
    caller = {'uid': OWNER}
    app.dependency_overrides[auth.get_current_user_uid] = lambda: caller['uid']
    with TestClient(app) as client:
        yield client, store, eraser, caller, gates


def test_owner_cancel_erases_and_is_idempotent(api):
    client, store, eraser, _, gates = api
    admit(store, ['a'])
    response = client.delete(f'/v2/sync-local-files/{JOB}')
    assert response.status_code == 200
    assert response.json() == {'job_id': JOB, 'outcome': 'cancelled', 'erasure': 'complete', 'conversation_ids': []}
    assert gates == [(OWNER, 'audio_conversation_deletion')]
    assert ('jobs', 'a') not in store.rows
    again = client.delete(f'/v2/sync-local-files/{JOB}')
    assert again.status_code == 200 and again.json()['outcome'] == 'cancelled'


def test_wrong_owner_and_unknown_handles_are_indistinguishable(api):
    client, store, _, caller, _ = api
    admit(store, ['a'])
    caller['uid'] = OTHER
    foreign = client.delete(f'/v2/sync-local-files/{JOB}')
    unknown = client.delete('/v2/sync-local-files/bp_unknown')
    legacy = client.delete('/v2/sync-local-files/6f1c0e5a-legacy')
    assert [r.status_code for r in (foreign, unknown, legacy)] == [200, 200, 200]
    assert {r.json()['outcome'] for r in (foreign, unknown, legacy)} == {'not_found'}
    assert store.rows['jobs', 'a']['state'] == 'ready'


def test_in_flight_work_is_a_retryable_conflict(api):
    client, store, _, _, _ = api
    admit(store, ['a'])
    store.rows['jobs', 'a'].update(state='leased', token='worker')
    response = client.delete(f'/v2/sync-local-files/{JOB}')
    assert response.status_code == 409
    assert response.json()['code'] == 'sync_job_processing'
    assert response.headers['Retry-After'] == '300'


def test_processed_upload_names_its_conversations(api):
    client, store, _, _, _ = api
    admit(
        store,
        ['a'],
        ledger={
            'status': 'completed',
            'job_id': JOB,
            'result': {
                'new_memories': ['conv-1'],
                'updated_memories': [],
                'failed_segments': 0,
                'total_segments': 1,
                'errors': [],
            },
        },
    )
    response = client.delete(f'/v2/sync-local-files/{JOB}')
    assert response.status_code == 200
    assert response.json() == {'job_id': JOB, 'outcome': 'already_processed', 'conversation_ids': ['conv-1']}


def test_not_cancellable_upload_is_a_terminal_conflict(api):
    client, store, _, _, _ = api
    admit(store, ['a'])
    store.rows['intakes', JOB]['coalesce_group'] = 'group'
    response = client.delete(f'/v2/sync-local-files/{JOB}')
    assert response.status_code == 409 and response.json()['code'] == 'sync_job_not_cancellable'


def test_kill_switch_off_pauses_without_touching_the_gate_or_store(api, monkeypatch):
    client, store, _, _, gates = api
    admit(store, ['a'])
    monkeypatch.setenv('SYNC_JOB_OWNER_CANCEL_ENABLED', 'off')
    response = client.delete(f'/v2/sync-local-files/{JOB}')
    assert response.status_code == 503 and response.json()['code'] == 'sync_job_cancel_disabled'
    assert gates == [] and store.rows['jobs', 'a']['state'] == 'ready'


def test_legal_hold_or_busy_gate_is_a_retryable_conflict(api, monkeypatch):
    client, store, _, _, _ = api
    admit(store, ['a'])

    @contextmanager
    def held(uid, *, kind, wait_seconds):
        raise LegalHoldActive('hold')
        yield

    monkeypatch.setattr(router, 'destructive_operation_gate', held)
    response = client.delete(f'/v2/sync-local-files/{JOB}')
    assert response.status_code == 409
    assert store.rows['jobs', 'a']['state'] == 'ready'


def test_throttled_owner_gets_429(api, monkeypatch):
    client, _, _, _, _ = api
    monkeypatch.setattr(router, 'admit_sync_job_poll', lambda uid: False)
    assert client.delete(f'/v2/sync-local-files/{JOB}').status_code == 429


def test_status_poll_after_cancel_returns_custody(api, monkeypatch):
    client, store, _, _, _ = api
    admit(store, ['a'])
    client.delete(f'/v2/sync-local-files/{JOB}')
    from utils.batch_pipeline import intake as batch_intake

    monkeypatch.setattr(batch_intake, 'shadow_from_env', lambda primary: primary)
    monkeypatch.setattr(batch_intake, 'FirestoreStore', lambda namespace: store)
    response = client.get(f'/v2/sync-local-files/{JOB}')
    assert response.status_code == 200
    body = response.json()
    assert body['status'] == 'failed' and body['reason_code'] == 'owner_cancelled'


def test_legacy_handle_cancels_its_cap_holds_under_the_gate(api, monkeypatch):
    from tests.unit.test_sync_owner_cancel_legacy import FakeLegacyEraser, MemoryLegacyStore, held_upload

    client, _, _, _, gates = api
    legacy = MemoryLegacyStore()
    held_upload(legacy)
    eraser = FakeLegacyEraser(legacy)
    monkeypatch.setattr(router, 'FirestoreLegacyStore', lambda: legacy)
    monkeypatch.setattr(router, 'FirestoreEraser', lambda namespace: eraser)
    response = client.delete('/v2/sync-local-files/legacy-upload-1')
    assert response.status_code == 200
    assert response.json() == {
        'job_id': 'legacy-upload-1',
        'outcome': 'cancelled',
        'erasure': 'complete',
        'conversation_ids': [],
    }
    assert gates and len(eraser.erased) == 2


def test_legacy_hold_mid_recovery_is_a_retryable_conflict(api, monkeypatch):
    from tests.unit.test_sync_owner_cancel_legacy import FakeLegacyEraser, MemoryLegacyStore, held_upload, hold

    client, _, _, _, _ = api
    legacy = MemoryLegacyStore()
    held_upload(legacy, {'h1': hold(30, lease_until=4_000_000_000, lease_token='worker')})
    monkeypatch.setattr(router, 'FirestoreLegacyStore', lambda: legacy)
    monkeypatch.setattr(router, 'FirestoreEraser', lambda namespace: FakeLegacyEraser(legacy))
    response = client.delete('/v2/sync-local-files/legacy-upload-1')
    assert response.status_code == 409 and response.json()['detail'] == 'sync_job_processing'
    assert legacy.rows[('hold', 'owner-synthetic', 'h1')]['state'] == 'held'
