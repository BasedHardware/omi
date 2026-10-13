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
        self._after = None

    def where(self, *args, filter=None, **kwargs):
        self._filters.append((filter.field_path, filter.value))
        return self

    def order_by(self, field, direction=None):
        return self

    def select(self, fields):
        chosen = tuple(fields)
        self.selects.append(chosen)
        self._fields = chosen
        return self

    def limit(self, count):
        self._limit = count
        return self

    def start_after(self, snapshot):
        reference = getattr(snapshot, 'reference', None)
        path = getattr(reference, 'path', None)
        if isinstance(path, tuple):
            path = '/'.join(path)
        self._after = str(path) if path else None
        return self

    def stream(self):
        rows = []
        for path, data in self.database.rows.items():
            if len(path) < 2 or path[-2] != self.group:
                continue
            if any(data.get(field) != expected for field, expected in self._filters):
                continue
            projected = {field: data[field] for field in self._fields if field in data}
            rows.append(_Snapshot(path, projected))
        rows.sort(key=lambda snapshot: snapshot.reference.path)
        if self._after:
            rows = [snapshot for snapshot in rows if snapshot.reference.path > self._after]
        if self._limit is not None:
            rows = rows[: self._limit]
        return iter(rows)


class _GroupClient:
    def __init__(self, database):
        self.database = database
        self.selects = []

    def collection_group(self, name):
        return _GroupQuery(self.database, name, self.selects)

    def collection(self, name):
        return self.database.collection(name)

    def document(self, path):
        return self.database.document(path)

    def transaction(self):
        return self.database.transaction()


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
    monkeypatch.setattr(integration_outbox_db, 'get_firestore_client', lambda: database)
    monkeypatch.setattr(integration_outbox_db.firestore, 'transactional', transactional)
    monkeypatch.setattr(candidate_service, 'get_user_deletion_wipe_status', lambda uid: None)
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
        'provider_attempt_outcome': 'definite_error',
    }
    payload.update(fields)
    store.rows[('users', 'user-1', 'candidate_integration_outbox', candidate_id)] = payload
    return ('users', 'user-1', 'candidate_integration_outbox', candidate_id)


def _dispatch(result):
    """Adapt a public sync dict to the internal (result, outcome, external id) channel."""
    public = dict(result)
    outcome = public.pop('provider_attempt_outcome', None)
    if outcome not in {'not_sent', 'definite_error', 'in_doubt', 'accepted'}:
        outcome = 'accepted' if public.get('synced') else 'in_doubt'
    external = public.get('external_task_id')
    if not isinstance(external, str) or not external:
        external = None
    return public, outcome, external


def _forbid_provider(monkeypatch):
    async def explode(*args, **kwargs):
        raise AssertionError('provider called')

    monkeypatch.setattr(candidate_service, 'auto_sync_action_item_with_outcome', explode)
    monkeypatch.setattr(
        candidate_service.action_items_db,
        'get_action_item',
        lambda *args, **kwargs: pytest.fail('task loaded'),
    )


def _allow_sync(monkeypatch, result):
    calls = []

    async def sync(uid, task, **kwargs):
        calls.append(task['id'])
        return _dispatch(result)

    monkeypatch.setattr(candidate_service.action_items_db, 'get_action_item', lambda uid, task_id: {'id': task_id})
    monkeypatch.setattr(candidate_service, 'auto_sync_action_item_with_outcome', sync)
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


def test_sweeper_skips_a_ten_minute_processing_row_and_reclaims_a_two_hour_one(store, monkeypatch):
    now = _now()
    calls = _allow_sync(monkeypatch, {'synced': True})
    recent = _put(
        store,
        'ten-minutes',
        now=now,
        status='processing',
        task_id='task-recent',
        claimed_at=now - timedelta(minutes=10),
        lease_token='recent-lease',
        attempt_count=1,
    )
    abandoned = _put(
        store,
        'two-hours',
        now=now,
        status='processing',
        task_id='task-abandoned',
        claimed_at=now - timedelta(hours=2),
        lease_token='abandoned-lease',
        attempt_count=1,
    )

    counts, _client = _sweep(store, now=now)

    assert sweeper.SWEEP_RECLAIM_AFTER == timedelta(hours=1)
    assert integration_outbox_db.CANDIDATE_INTEGRATION_LEASE_SECONDS == 300
    assert counts['skipped_live_lease'] == 1
    assert counts['retried'] == 1
    assert calls == ['task-abandoned']
    assert store.rows[recent]['status'] == 'processing'
    assert store.rows[recent]['lease_token'] == 'recent-lease'
    assert store.rows[recent]['attempt_count'] == 1
    assert store.rows[abandoned]['status'] == 'completed'
    assert store.rows[abandoned]['attempt_count'] == 2
    assert store.rows[abandoned]['claimed_at'] >= now


def _schedule_inline_job(store, monkeypatch):
    now = _now()
    path = _put(store, 'inline', now=now, status='pending', attempt_count=0, task_id='task-inline')
    calls = []
    scheduled = []

    async def sync(uid, task, **kwargs):
        calls.append(
            {
                'task_id': task['id'],
                'claimed_at': store.rows[path]['claimed_at'],
                'lease_token': store.rows[path]['lease_token'],
            }
        )
        return _dispatch({'synced': True})

    monkeypatch.setattr(candidate_service.action_items_db, 'get_action_item', lambda uid, task_id: {'id': task_id})
    monkeypatch.setattr(candidate_service, 'auto_sync_action_item_with_outcome', sync)

    def capture(executor, function):
        scheduled.append(function)

    monkeypatch.setattr(candidate_service, 'submit_with_context', capture)
    assert candidate_service._dispatch_task_integration('user-1', 'inline', 'task-inline', account_generation=3)
    assert len(scheduled) == 1
    assert calls == []
    return path, calls, scheduled[0]


def test_inline_job_delayed_past_the_claim_lease_is_the_only_provider_call(store, monkeypatch):
    path, calls, run_sync = _schedule_inline_job(store, monkeypatch)
    sweep_now = _now()
    original_token = store.rows[path]['lease_token']
    store.rows[path]['claimed_at'] = sweep_now - timedelta(seconds=301)

    counts, _client = _sweep(store, now=sweep_now)
    assert counts['skipped_live_lease'] == 1
    assert counts['retried'] == 0
    assert calls == []

    run_sync()

    assert [call['task_id'] for call in calls] == ['task-inline']
    assert calls[0]['lease_token'] == original_token
    assert calls[0]['claimed_at'] >= sweep_now
    assert store.rows[path]['status'] == 'completed'
    assert store.rows[path]['attempt_count'] == 1


def test_inline_job_that_lost_its_lease_makes_no_provider_call(store, monkeypatch):
    path, calls, run_sync = _schedule_inline_job(store, monkeypatch)
    claimed_at = store.rows[path]['claimed_at']
    store.rows[path]['lease_token'] = 'taken-over'

    run_sync()

    assert calls == []
    assert store.rows[path]['status'] == 'processing'
    assert store.rows[path]['lease_token'] == 'taken-over'
    assert store.rows[path]['claimed_at'] == claimed_at
    assert store.rows[path]['attempt_count'] == 1


def test_blocking_dispatch_skips_the_provider_when_the_lease_is_lost_before_the_call(store, monkeypatch):
    now = _now()
    path = _put(store, 'due', now=now, status='failed', attempt_count=1)
    calls = []

    def steal_before_provider(uid, task_id):
        store.rows[path]['lease_token'] = 'stolen'
        return {'id': task_id}

    async def sync(uid, task, **kwargs):
        calls.append(task['id'])
        return _dispatch({'synced': True})

    monkeypatch.setattr(candidate_service.action_items_db, 'get_action_item', steal_before_provider)
    monkeypatch.setattr(candidate_service, 'auto_sync_action_item_with_outcome', sync)

    recorded = candidate_service.dispatch_task_integration_blocking('user-1', 'due', 'task-1', account_generation=3)

    assert recorded is False
    assert calls == []
    assert store.rows[path]['status'] == 'processing'
    assert store.rows[path]['lease_token'] == 'stolen'


def test_blocking_dispatch_uses_the_injected_client_for_claim_and_completion(store, monkeypatch):
    now = _now()
    path = _put(store, 'due', now=now, status='failed', provider_attempt_outcome='definite_error')
    empty = StrictFirestore()
    empty.rows[('users', 'user-1', 'task_intelligence_control', 'state')] = {
        'workflow_mode': 'read',
        'account_generation': 9,
    }
    monkeypatch.setattr(integration_outbox_db, 'db', empty)
    monkeypatch.setattr(integration_outbox_db, 'get_firestore_client', lambda: empty)
    calls = _allow_sync(monkeypatch, {'synced': True, 'provider_attempt_outcome': 'accepted'})

    recorded = candidate_service.dispatch_task_integration_blocking(
        'user-1',
        'due',
        'task-1',
        account_generation=3,
        firestore_client=_GroupClient(store),
    )

    assert recorded is True
    assert calls == ['task-1']
    assert store.rows[path]['status'] == 'completed'
    assert ('users', 'user-1', 'candidate_integration_outbox', 'due') not in empty.rows


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


def test_ambiguous_and_legacy_failures_are_not_sent_to_the_provider_again(store, monkeypatch):
    now = _now()
    calls = _allow_sync(monkeypatch, {'synced': True, 'provider_attempt_outcome': 'accepted'})
    legacy = _put(store, 'legacy', now=now, task_id='task-legacy')
    del store.rows[legacy]['provider_attempt_outcome']
    doubt = _put(store, 'doubt', now=now, task_id='task-doubt', provider_attempt_outcome='in_doubt')
    safe = _put(store, 'safe', now=now, task_id='task-safe', provider_attempt_outcome='definite_error')
    recorded = _put(
        store,
        'recorded',
        now=now,
        task_id='task-recorded',
        provider_attempt_outcome='in_doubt',
        external_task_id='ext-recorded',
        export_platform='todoist',
    )
    updates = []

    def update_action_item(uid, task_id, payload):
        updates.append((task_id, payload))
        return True

    monkeypatch.setattr(sweeper.action_items_db, 'update_action_item', update_action_item)

    counts, _client = _sweep(store, now=now)

    assert calls == ['task-safe']
    assert counts['dead_letter_in_doubt'] == 2
    assert counts['recovered_external_id'] == 1
    assert counts['retried'] == 1
    assert store.rows[legacy]['status'] == 'dead_letter'
    assert store.rows[legacy]['dead_letter_reason'] == 'in_doubt'
    assert store.rows[doubt]['status'] == 'dead_letter'
    assert store.rows[doubt]['dead_letter_reason'] == 'in_doubt'
    assert store.rows[safe]['status'] == 'completed'
    assert store.rows[recorded]['status'] == 'completed'
    assert updates == [
        (
            'task-recorded',
            {
                'exported': True,
                'export_date': now,
                'external_task_id': 'ext-recorded',
                'export_platform': 'todoist',
            },
        ),
    ]


@pytest.mark.parametrize('wipe_status', ['pending', 'running', 'done'])
def test_account_deletion_skips_provider_dispatch(store, monkeypatch, wipe_status):
    now = _now()
    calls = _allow_sync(monkeypatch, {'synced': True, 'provider_attempt_outcome': 'accepted'})
    path = _put(store, 'deleting', now=now, provider_attempt_outcome='definite_error')
    monkeypatch.setattr(candidate_service, 'get_user_deletion_wipe_status', lambda uid: wipe_status)

    counts, _client = _sweep(store, now=now)

    assert calls == []
    assert counts['skipped_account_deleting'] == 1
    assert counts['retried'] == 0
    assert store.rows[path]['status'] == 'failed'


def test_deletion_fence_is_fail_closed_when_the_marker_read_fails(store, monkeypatch):
    now = _now()
    calls = _allow_sync(monkeypatch, {'synced': True, 'provider_attempt_outcome': 'accepted'})
    path = _put(store, 'deleting', now=now, provider_attempt_outcome='not_sent')

    def explode(uid):
        raise RuntimeError('marker unavailable')

    monkeypatch.setattr(candidate_service, 'get_user_deletion_wipe_status', explode)

    counts, _client = _sweep(store, now=now)

    assert calls == []
    assert counts['skipped_account_deleting'] == 1
    assert store.rows[path]['status'] == 'failed'


def test_redriven_row_is_not_dead_lettered_by_the_original_created_at(store, monkeypatch):
    now = _now()
    calls = _allow_sync(monkeypatch, {'synced': True, 'provider_attempt_outcome': 'accepted'})
    created_at = now - timedelta(days=8)
    path = _put(
        store,
        'old-redrive',
        now=now,
        status='dead_letter',
        created_at=created_at,
        provider_attempt_outcome='definite_error',
        dead_letter_reason='stale_abandoned',
    )

    assert integration_outbox_db.redrive_candidate_integration_dead_letter(
        'user-1',
        'old-redrive',
        account_generation=3,
        now=now,
    )
    assert store.rows[path]['redriven_at'] == now
    assert store.rows[path]['created_at'] == created_at
    assert store.rows[path]['status'] == 'pending'

    counts, _client = _sweep(store, now=now)

    assert counts['dead_letter_stale_abandoned'] == 0
    assert counts['retried'] == 1
    assert calls == ['task-1']
    assert store.rows[path]['status'] == 'completed'


def test_sweep_cursor_moves_past_rows_that_stay_in_the_same_status(store, monkeypatch):
    now = _now()
    calls = _allow_sync(monkeypatch, {'synced': True, 'provider_attempt_outcome': 'accepted'})
    _put(store, 'a-sticky', now=now, available_at=now + timedelta(hours=1))
    _put(store, 'b-sticky', now=now, available_at=now + timedelta(hours=1))
    _put(store, 'c-due', now=now, task_id='task-due', available_at=now - timedelta(seconds=1))

    first, _client = _sweep(store, now=now, max_rows=1)
    second, _client = _sweep(store, now=now, max_rows=1)
    third, _client = _sweep(store, now=now, max_rows=1)

    assert first['skipped_not_due'] == 1 and first['retried'] == 0
    assert second['skipped_not_due'] == 1 and second['retried'] == 0
    assert third['retried'] == 1
    assert calls == ['task-due']


def test_two_sweeps_reach_a_processing_row_behind_a_full_future_failed_page(store, monkeypatch):
    now = _now()
    calls = _allow_sync(monkeypatch, {'synced': True, 'provider_attempt_outcome': 'accepted'})
    for index in range(sweeper.MAX_ROWS):
        _put(
            store,
            f'failed-{index:03d}',
            now=now,
            available_at=now + timedelta(hours=1),
            provider_attempt_outcome='definite_error',
        )
    _put(
        store,
        'reclaim',
        now=now,
        status='processing',
        task_id='task-reclaim',
        claimed_at=now - timedelta(hours=2),
        lease_token='abandoned',
        provider_attempt_outcome='definite_error',
    )

    first, _client = _sweep(store, now=now)

    assert first['inspected'] == sweeper.MAX_ROWS
    assert first['skipped_not_due'] == sweeper.MAX_ROWS
    assert first['retried'] == 0
    assert calls == []

    second, _client = _sweep(store, now=now)

    assert second['inspected'] == 1
    assert second['retried'] == 1
    assert calls == ['task-reclaim']


def test_generation_mismatch_rechecks_the_control_document_in_the_write_transaction(store, monkeypatch):
    now = _now()
    calls = _allow_sync(monkeypatch, {'synced': True, 'provider_attempt_outcome': 'accepted'})
    path = _put(store, 'current-generation', now=now, account_generation=3)
    monkeypatch.setattr(
        integration_outbox_db,
        'current_task_account_generation',
        lambda uid, firestore_client=None: 1,
    )

    counts, _client = _sweep(store, now=now)

    assert counts['dead_letter_generation_mismatch'] == 0
    assert counts['retried'] == 1
    assert calls == ['task-1']
    assert store.rows[path]['status'] == 'completed'


def test_sweep_counter_zero_inits_the_closed_disposition_set():
    samples = {
        sample.labels['disposition']
        for family in OMI_CANDIDATE_INTEGRATION_SWEEP_TOTAL.collect()
        for sample in family.samples
        if sample.name == 'omi_candidate_integration_sweep_total'
    }
    assert samples == set(CANDIDATE_INTEGRATION_SWEEP_DISPOSITIONS)


def test_scheduler_job_exists_only_for_prod():
    from pathlib import Path

    manifest = yaml.load(
        (Path(__file__).resolve().parents[2] / 'deploy/scheduler/jobs.yaml').read_text(),
        Loader=yaml.CSafeLoader,
    )
    dev_names = {item['name'] for item in manifest['environments']['dev']['jobs']}
    assert 'candidate-integration-sweep' not in dev_names
    jobs = manifest['environments']['prod']['jobs']
    job = next(item for item in jobs if item['name'] == 'candidate-integration-sweep')
    sequencer = next(item for item in jobs if item['name'] == 'sync-backfill-uid-sequencer')
    host = 'https://backend-sync-hhibjajaja-uc.a.run.app'
    assert 'lifecycle' not in job  # active: backend-sync serves the route since 7741a1a
    assert job['schedule'] == '*/15 * * * *'
    assert job['attempt_deadline'] == '120s'
    assert job['state'] == 'ENABLED'
    assert job['target']['uri'] == host + '/v2/candidate-integrations/sweep'
    assert job['target']['method'] == 'POST'
    assert job['target']['oidc'] == {
        'service_account': 'sync-tasks-invoker@based-hardware.iam.gserviceaccount.com',
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
