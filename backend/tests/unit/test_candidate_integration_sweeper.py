"""Bounded candidate-integration sweep: dead-letter the stale backlog, retry the rest."""

import asyncio
from datetime import datetime, timedelta, timezone

import pytest
import yaml
from fastapi import FastAPI
from fastapi.testclient import TestClient

import database.candidate_integration_outbox as integration_outbox_db
from routers import candidate_integration_sweep
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from utils import cloud_tasks
from utils.metrics import CANDIDATE_INTEGRATION_SWEEP_DISPOSITIONS, OMI_CANDIDATE_INTEGRATION_SWEEP_TOTAL
from utils.task_intelligence import candidate_integration_sweeper as sweeper
from utils.task_intelligence import candidate_service

AUDIENCE = 'https://synthetic-sync.example/v2/sync-jobs/run'
INVOKER = 'synthetic-scheduler@example.iam.gserviceaccount.com'


def _now():
    return datetime.now(timezone.utc)


class _Snapshot:
    def __init__(self, path, data):
        self.reference = type('Ref', (), {'path': '/'.join(path)})()
        self._data = data

    def to_dict(self):
        return dict(self._data)


class _GroupQuery:
    def __init__(self, database, group, selects):
        self.database = database
        self.group = group
        self.selects = selects
        self._filters = []
        self._fields = None
        self._limit = None

    def where(self, *args, filter=None, **kwargs):
        self._filters.append((filter.field_path, filter.value))
        return self

    def select(self, fields):
        chosen = tuple(fields)
        self.selects.append(chosen)
        self._fields = chosen
        return self

    def limit(self, count):
        self._limit = count
        return self

    def stream(self):
        rows = []
        for path, data in sorted(self.database.rows.items()):
            if len(path) < 2 or path[-2] != self.group:
                continue
            if any(data.get(field) != expected for field, expected in self._filters):
                continue
            projected = {field: data[field] for field in self._fields if field in data}
            rows.append(_Snapshot(path, projected))
        if self._limit is not None:
            rows = rows[: self._limit]
        return iter(rows)


class _GroupClient:
    def __init__(self, database):
        self.database = database
        self.selects = []

    def collection_group(self, name):
        return _GroupQuery(self.database, name, self.selects)


@pytest.fixture
def store(monkeypatch):
    database = StrictFirestore()
    database.rows[('users', 'user-1', 'task_intelligence_control', 'state')] = {
        'workflow_mode': 'read',
        'account_generation': 3,
    }

    def transactional(function):
        def run(transaction):
            with transaction.lock:
                return function(transaction)

        return run

    monkeypatch.setattr(integration_outbox_db, 'db', database)
    monkeypatch.setattr(integration_outbox_db.firestore, 'transactional', transactional)
    return database


def _put(store, candidate_id, **fields):
    now = fields.pop('now')
    payload = {
        'outbox_id': candidate_id,
        'candidate_id': candidate_id,
        'task_id': 'task-1',
        'account_generation': 3,
        'status': 'failed',
        'attempt_count': 1,
        'created_at': now - timedelta(hours=1),
        'updated_at': now,
        'available_at': now - timedelta(seconds=1),
    }
    payload.update(fields)
    store.rows[('users', 'user-1', 'candidate_integration_outbox', candidate_id)] = payload
    return ('users', 'user-1', 'candidate_integration_outbox', candidate_id)


def _forbid_provider(monkeypatch):
    async def explode(*args, **kwargs):
        raise AssertionError('provider called')

    monkeypatch.setattr(candidate_service, 'auto_sync_action_item', explode)
    monkeypatch.setattr(
        candidate_service.action_items_db,
        'get_action_item',
        lambda *args, **kwargs: pytest.fail('task loaded'),
    )


def _allow_sync(monkeypatch, result):
    calls = []

    async def sync(uid, task, **kwargs):
        calls.append(task['id'])
        return result

    monkeypatch.setattr(candidate_service.action_items_db, 'get_action_item', lambda uid, task_id: {'id': task_id})
    monkeypatch.setattr(candidate_service, 'auto_sync_action_item', sync)
    return calls


def _sweep(store, **kwargs):
    client = _GroupClient(store)
    counts = asyncio.run(sweeper.sweep_candidate_integrations(firestore_client=client, now=kwargs.pop('now'), **kwargs))
    return counts, client


def test_stale_and_missing_created_at_dead_letter_with_zero_provider_calls(store, monkeypatch):
    now = _now()
    _forbid_provider(monkeypatch)
    stale = _put(store, 'stale', now=now, created_at=now - timedelta(days=8), status='failed')
    abandoned = _put(
        store,
        'abandoned-lease',
        now=now,
        status='processing',
        created_at=now - timedelta(days=58),
        claimed_at=now - timedelta(days=58),
        lease_token='old-lease',
    )
    missing = _put(store, 'missing-created', now=now, status='failed')
    del store.rows[missing]['created_at']

    counts, client = _sweep(store, now=now)

    assert counts['dead_letter_stale_abandoned'] == 2
    assert counts['dead_letter_missing_created_at'] == 1
    assert counts['retried'] == 0
    assert store.rows[stale]['status'] == 'dead_letter'
    assert store.rows[stale]['dead_letter_reason'] == 'stale_abandoned'
    assert store.rows[stale]['attempt_count'] == 1
    assert store.rows[abandoned]['status'] == 'dead_letter'
    assert store.rows[abandoned]['dead_letter_reason'] == 'stale_abandoned'
    assert store.rows[abandoned]['lease_token'] is None
    assert store.rows[missing]['status'] == 'dead_letter'
    assert store.rows[missing]['dead_letter_reason'] == 'missing_created_at'
    assert client.selects
    assert all('description' not in fields and 'last_error_text' not in fields for fields in client.selects)
    assert set(client.selects) == {integration_outbox_db.SWEEP_METADATA_FIELDS}


def test_generation_mismatch_dead_letters_without_a_provider_call(store, monkeypatch):
    now = _now()
    _forbid_provider(monkeypatch)
    path = _put(store, 'old-generation', now=now, account_generation=1, status='failed')

    counts, _client = _sweep(store, now=now)

    assert counts['dead_letter_generation_mismatch'] == 1
    assert counts['retried'] == 0
    assert store.rows[path]['status'] == 'dead_letter'
    assert store.rows[path]['dead_letter_reason'] == 'generation_mismatch'


def test_young_failed_due_row_is_claimed_and_completed_before_return(store, monkeypatch):
    now = _now()
    calls = _allow_sync(monkeypatch, {'synced': True})
    path = _put(store, 'due', now=now, status='failed', attempt_count=1)

    counts, _client = _sweep(store, now=now)

    assert counts['retried'] == 1
    assert calls == ['task-1']
    assert store.rows[path]['status'] == 'completed'
    assert store.rows[path]['attempt_count'] == 2


def test_disconnected_integration_completes_without_raising_the_attempt_budget(store, monkeypatch):
    now = _now()
    calls = _allow_sync(monkeypatch, {'synced': False, 'reason': 'integration_not_connected'})
    path = _put(store, 'disconnected', now=now, status='failed', attempt_count=1)

    counts, _client = _sweep(store, now=now)

    assert counts['retried'] == 1
    assert calls == ['task-1']
    assert store.rows[path]['status'] == 'completed'


def test_future_available_at_and_young_pending_are_skipped(store, monkeypatch):
    now = _now()
    _forbid_provider(monkeypatch)
    future = _put(store, 'future', now=now, status='failed', available_at=now + timedelta(hours=1))
    pending = _put(
        store,
        'fresh-pending',
        now=now,
        status='pending',
        attempt_count=0,
        created_at=now - timedelta(minutes=1),
        available_at=None,
    )

    counts, _client = _sweep(store, now=now)

    assert counts['skipped_not_due'] == 1
    assert counts['skipped_pending_young'] == 1
    assert counts['retried'] == 0
    assert store.rows[future]['status'] == 'failed'
    assert store.rows[pending]['status'] == 'pending'


def test_live_lease_is_skipped_and_expired_lease_is_reclaimed(store, monkeypatch):
    now = _now()
    calls = _allow_sync(monkeypatch, {'synced': True})
    live = _put(
        store,
        'live',
        now=now,
        status='processing',
        claimed_at=now - timedelta(seconds=30),
        lease_token='live-lease',
        attempt_count=1,
    )
    expired = _put(
        store,
        'expired',
        now=now,
        status='processing',
        claimed_at=now - timedelta(seconds=301),
        lease_token='expired-lease',
        attempt_count=1,
    )

    counts, _client = _sweep(store, now=now)

    assert counts['skipped_live_lease'] == 1
    assert counts['retried'] == 1
    assert calls == ['task-1']
    assert store.rows[live]['status'] == 'processing'
    assert store.rows[live]['lease_token'] == 'live-lease'
    assert store.rows[expired]['status'] == 'completed'
    assert store.rows[expired]['attempt_count'] == 2


def test_row_and_wall_clock_budgets_stop_the_pass(store, monkeypatch):
    now = _now()
    _forbid_provider(monkeypatch)
    first = _put(store, 'a-stale', now=now, created_at=now - timedelta(days=8))
    second = _put(store, 'b-stale', now=now, created_at=now - timedelta(days=9))
    third = _put(store, 'c-stale', now=now, created_at=now - timedelta(days=10))

    counts, _client = _sweep(store, now=now, max_rows=2)
    assert counts['inspected'] == 2
    assert counts['dead_letter_stale_abandoned'] == 2
    assert store.rows[first]['status'] == 'dead_letter'
    assert store.rows[second]['status'] == 'dead_letter'
    assert store.rows[third]['status'] == 'failed'

    ticks = {'n': 0}

    def clock():
        ticks['n'] += 1
        return 0.0 if ticks['n'] < 4 else 100.0

    later = _sweep(store, now=now, monotonic=clock, budget_seconds=50)
    assert later[0]['inspected'] == 1
    assert store.rows[third]['status'] == 'dead_letter'

    held = _put(store, 'd-stale', now=now, created_at=now - timedelta(days=11))
    stopped = _sweep(store, now=now, monotonic=lambda: 0.0, budget_seconds=0)
    assert stopped[0]['inspected'] == 0
    assert store.rows[held]['status'] == 'failed'


def test_sweep_counter_zero_inits_the_closed_disposition_set():
    samples = {
        sample.labels['disposition']
        for family in OMI_CANDIDATE_INTEGRATION_SWEEP_TOTAL.collect()
        for sample in family.samples
        if sample.name == 'omi_candidate_integration_sweep_total'
    }
    assert samples == set(CANDIDATE_INTEGRATION_SWEEP_DISPOSITIONS)


def test_scheduler_job_matches_the_sync_oidc_audience_and_cannot_block_a_full_reconcile():
    from pathlib import Path

    manifest = yaml.load(
        (Path(__file__).resolve().parents[2] / 'deploy/scheduler/jobs.yaml').read_text(),
        Loader=yaml.CSafeLoader,
    )
    for environment, host, account in (
        (
            'dev',
            'https://backend-sync-dt5lrfkkoa-uc.a.run.app',
            'sync-tasks-invoker@based-hardware-dev.iam.gserviceaccount.com',
        ),
        (
            'prod',
            'https://backend-sync-hhibjajaja-uc.a.run.app',
            'sync-tasks-invoker@based-hardware.iam.gserviceaccount.com',
        ),
    ):
        jobs = manifest['environments'][environment]['jobs']
        job = next(item for item in jobs if item['name'] == 'candidate-integration-sweep')
        sequencer = next(item for item in jobs if item['name'] == 'sync-backfill-uid-sequencer')
        assert job['lifecycle'] == 'planned'
        assert job['schedule'] == '*/15 * * * *'
        assert job['attempt_deadline'] == '120s'
        assert job['state'] == ('PAUSED' if environment == 'dev' else 'ENABLED')
        assert job['target']['uri'] == host + '/v2/candidate-integrations/sweep'
        assert job['target']['method'] == 'POST'
        assert job['target']['oidc'] == {
            'service_account': account,
            'audience': sequencer['target']['oidc']['audience'],
        }
        assert job['retry'] == sequencer['retry']


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv('SYNC_TASKS_OIDC_AUDIENCE', AUDIENCE)
    monkeypatch.setenv('SYNC_TASKS_INVOKER_SA', INVOKER)
    monkeypatch.setattr(cloud_tasks, '_get_auth_request', lambda: object())
    app = FastAPI()
    app.include_router(candidate_integration_sweep.router)
    return TestClient(app)


@pytest.mark.parametrize('token', [None, 'wrong-audience', 'wrong-identity', 'unverified'])
def test_sweep_route_rejects_unauthenticated_callers(client, monkeypatch, token):
    def verify(value, request, *, audience):
        assert audience == AUDIENCE
        if value == 'wrong-audience':
            raise ValueError('invalid audience')
        return {'email': INVOKER if value != 'wrong-identity' else 'other', 'email_verified': value != 'unverified'}

    monkeypatch.setattr(cloud_tasks.id_token, 'verify_oauth2_token', verify)
    monkeypatch.setattr(
        candidate_integration_sweep,
        'run_candidate_integration_sweep',
        lambda **kwargs: pytest.fail('swept'),
    )
    headers = {} if token is None else {'Authorization': 'Bearer ' + token}
    assert client.post('/v2/candidate-integrations/sweep', headers=headers).status_code == 403
