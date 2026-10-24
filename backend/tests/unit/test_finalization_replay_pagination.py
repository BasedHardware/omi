"""Cursor contract qualified by backend/scripts/quiet_finalization_replay_emulator_test.py."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock

from database import conversation_finalization_jobs as jobs
from services import conversation_finalization as service
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore

NOW = datetime(2026, 10, 24, tzinfo=timezone.utc)


class DueQuery:
    """Narrow query seam: real-store ordering is qualified by the emulator test."""

    def __init__(self, store):
        self.store = store
        self.after = None
        self.bound = 100
        self.orders = []

    def where(self, field, op, cutoff):
        assert (field, op) == ('reconcile_after_at', '<=')
        self.cutoff = cutoff
        return self

    def order_by(self, field):
        assert field in {'reconcile_after_at', '__name__'}
        self.orders.append(field)
        return self

    def start_after(self, cursor):
        assert self.orders == ['reconcile_after_at', '__name__']
        self.after = (cursor['reconcile_after_at'], cursor['__name__'].id)
        return self

    def limit(self, bound):
        self.bound = bound
        return self

    def stream(self):
        ordered = sorted(
            (row['reconcile_after_at'], path[-1], row)
            for path, row in self.store.rows.items()
            if path[0] == jobs.FINALIZATION_JOBS_COLLECTION
            and isinstance(row.get('reconcile_after_at'), datetime)
            and row['reconcile_after_at'] <= self.cutoff
        )
        rows = [entry for entry in ordered if self.after is None or entry[:2] > self.after]
        return iter(SimpleNamespace(id=key, to_dict=lambda row=dict(row): row) for _, key, row in rows[: self.bound])


class ReplayStore(StrictFirestore):
    def collection(self, name):
        col = super().collection(name)
        if name != jobs.FINALIZATION_JOBS_COLLECTION:
            return col
        return SimpleNamespace(document=col.document, where=lambda *args: DueQuery(self).where(*args))


def seed():
    return ReplayStore(
        {
            (jobs.FINALIZATION_JOBS_COLLECTION, f'quiet-{i:03}'): {
                'kind': 'listen_quiet_check',
                'status': 'waiting_quiet',
                'dispatch_generation': 1,
                'reconcile_after_at': NOW - timedelta(hours=1),
                'due_at': NOW - timedelta(hours=1),
            }
            for i in range(101)
        }
    )


def test_hundred_nonadvancing_rows_cannot_starve_valid_check(monkeypatch):
    store = seed()
    monkeypatch.setattr(jobs, '_now', lambda: NOW)
    monkeypatch.setattr(jobs, 'recover_stranded_byok_jobs', Mock(return_value={'blocked': 0, 'errors': 0}))
    monkeypatch.setattr(service, 'is_listen_finalization_dispatch_enabled', lambda: True)
    monkeypatch.setattr(service, '_publish_job_metrics', Mock())
    # Even a broken worker AND broken backoff cannot pin the replay cursor.
    monkeypatch.setattr(jobs, 'defer_finalization_replay', Mock(return_value=False))
    processed = []

    def run(job_id, generation, **kwargs):
        if job_id == 'quiet-100':
            processed.append(job_id)
            store.rows[(jobs.FINALIZATION_JOBS_COLLECTION, job_id)]['status'] = 'quiet_done'
            return 'done'
        return 'stale'

    monkeypatch.setattr(service.quiet_finalization, 'run', run)
    first = service.reconcile_listen_finalization_jobs(limit=100, firestore_client=store)
    second = service.reconcile_listen_finalization_jobs(limit=100, firestore_client=store)
    assert first['stale'] == 100 and first['requeued'] == 0
    assert second['retired'] == 1 and processed == ['quiet-100']


def test_deleted_cursor_boundary_wrap_and_elevated_limit(monkeypatch):
    store = seed()
    monkeypatch.setattr(jobs, '_now', lambda: NOW)
    first = jobs.get_finalization_replay_candidates(firestore_client=store)
    del store.rows[(jobs.FINALIZATION_JOBS_COLLECTION, first[-1]['job_id'])]
    assert [j['job_id'] for j in jobs.get_finalization_replay_candidates(firestore_client=store)] == ['quiet-100']
    assert len(jobs.get_finalization_replay_candidates(limit=1000, firestore_client=store)) == 100
    assert jobs.get_finalization_replay_oldest_overdue_age_seconds(firestore_client=store) == 3600


def test_cursor_cas_rejects_delayed_writer():
    store = seed()
    ref = store.collection('conversation_recovery_state').document('finalization_replay')
    # Use SDK's transactional wrapper, which enforces ordering via StrictFirestore.
    advance = jobs.firestore.transactional(jobs._advance_finalization_replay_cursor_txn)
    assert advance(store.transaction(), ref, 0, {'job_id': 'new'})
    assert not advance(store.transaction(), ref, 0, {'job_id': 'old'})
    assert ref.get().to_dict()['cursor'] == {'job_id': 'new'}


def test_crash_reserved_page_is_revisited_despite_recurring_successors(monkeypatch):
    store = seed()
    for path in list(store.rows):
        if path[-1] not in {'quiet-000', 'quiet-001', 'quiet-002', 'quiet-003'}:
            del store.rows[path]
    clock = [NOW]
    monkeypatch.setattr(jobs, '_now', lambda: clock[0])
    # Crash after reservation: A/B remain untouched behind the cursor.
    assert [j['job_id'] for j in jobs.get_finalization_replay_candidates(limit=2, firestore_client=store)] == [
        'quiet-000',
        'quiet-001',
    ]
    page = jobs.get_finalization_replay_candidates(limit=2, firestore_client=store)
    assert [j['job_id'] for j in page] == ['quiet-002', 'quiet-003']
    for row in page:
        store.rows[(jobs.FINALIZATION_JOBS_COLLECTION, row['job_id'])]['reconcile_after_at'] = NOW + timedelta(
            seconds=60
        )
    clock[0] += timedelta(seconds=60)
    # Even though C/D are due again, this sweep excludes their successors,
    # reaches exhaustion, and wraps to the unprocessed A/B on the next pass.
    assert jobs.get_finalization_replay_candidates(limit=2, firestore_client=store) == []
    assert [j['job_id'] for j in jobs.get_finalization_replay_candidates(limit=2, firestore_client=store)] == [
        'quiet-000',
        'quiet-001',
    ]
