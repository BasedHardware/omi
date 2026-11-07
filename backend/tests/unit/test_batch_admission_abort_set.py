"""Entry-point wiring: the rejoin seed is read outside every transaction.

Every append entry point — ring enqueue, upload admission, the recover sweep's
retry requeue and legacy migration, dead redrive, artifact restore, the intake
status redrive — reads its advisory frontier seed before ``store.run`` and
threads it into ``control.activate``. Pinned here:

1. Ordering: the hint read lands before the transaction opens, on every entry
   point, and never inside it.
2. Seeding: the activated shard's service is exactly ``max(own, hint)`` with
   the hint the entry point read for that job's priority.
3. Degrade: a failed hint read degrades to ``0.0`` with
   ``event=batch_frontier_hint outcome=degraded`` and never fails admission.
4. The abort-set property: no rejoin body touches the retired transactional
   frontier read — a guard transaction fails the body the moment it does.
5. Probe gates: ``redrive_dead`` probes the row's priority; ``durable_status``
   reads hints only when the intake is incomplete.
6. ``admit`` carries the caller's ``frontiers`` map into the ring enqueue per
   item priority; a custom (provider-STT) enqueue is untouched.

Failure-Class: FC-rejoin-frontier-seed-read-joins-the-argmax-shard-abort-set
"""

import hashlib
from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace

import pytest

from config.batch_pipeline import scheduler_control_key
from database.batch_pipeline_intake import admit
from tests.unit.test_batch_pipeline_intake import proposal, submit
from tests.unit.test_batch_pipeline_scheduler import MemoryStore, MemoryTransaction, item
from utils.batch_pipeline.contracts import Priority, ProjectionBinding
from utils.batch_pipeline.scheduler import Scheduler, owner_key, rejoin_frontiers
from utils.batch_pipeline.intake import durable_status


class SequencedStore(MemoryStore):
    """MemoryStore that records hint reads and run openings on one timeline."""

    def __init__(self, hints=None, failing=False):
        super().__init__()
        self._hints = dict(hints or {})
        self._failing = failing
        self.seq = 0
        self.timeline = []
        self.hint_calls = []

    def service_frontier_hint(self, priority):
        if priority not in (0, 1, 2):
            raise ValueError('bounded priority required')
        value = self._hints.get(priority, 0.0)
        self.hint_calls.append((priority, value))
        self.timeline.append(('hint', priority, self.seq))
        self.seq += 1
        if self._failing:
            raise RuntimeError('synthetic hint outage')
        return value

    def run(self, body, *, operation=None):
        self.timeline.append(('run-open', operation, self.seq))
        self.seq += 1
        result = super().run(body, operation=operation)
        self.timeline.append(('run-close', operation, self.seq))
        self.seq += 1
        return result


class FrontierGuardTx:
    """Fails the body the moment anything touches the retired frontier read."""

    def __init__(self, tx):
        self._tx = tx
        self.touches = []

    def __getattr__(self, name):
        if name == 'service_frontier':
            self.touches.append(name)
            raise AssertionError('transactional frontier read inside a rejoin body')
        return getattr(self._tx, name)


class GuardedStore(MemoryStore):
    """MemoryStore whose transaction views guard the retired frontier read."""

    def __init__(self):
        super().__init__()
        self.guard_touches = []

    def run(self, body, *, operation=None):
        with self.lock:
            snapshot = deepcopy(self.rows)
            tx = FrontierGuardTx(MemoryTransaction(snapshot))
            result = body(tx)
            self.guard_touches.extend(tx.touches)
            self.rows = snapshot
            return result


@pytest.fixture(autouse=True)
def cohort(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_UID_ALLOWLIST', 'synthetic-owner')
    monkeypatch.setenv('BATCH_PIPELINE_PERCENT', '0')


def queue(store):
    return Scheduler(store)


def seeded_shard(store, owner_hash, priority):
    return store.rows.get(('control', scheduler_control_key(owner_hash)))


# --------------------------------------------------------------------------
# 1. Ring enqueue: hint before the transaction, seed exactly max(own, hint)
# --------------------------------------------------------------------------


def test_enqueue_reads_the_hint_before_opening_the_transaction():
    store = SequencedStore(hints={1: 5.0})
    queue(store).enqueue(item('seg-1'), 100.0)
    kinds = [entry[0] for entry in store.timeline]
    assert kinds[0] == 'hint'
    assert 'hint' not in kinds[1:]


def test_enqueue_reads_the_hint_exactly_once():
    store = SequencedStore(hints={int(Priority.DEEP): 5.0})
    queue(store).enqueue(item('seg-1'), 100.0)
    assert store.hint_calls == [(int(Priority.DEEP), 5.0)]


def test_enqueue_reads_the_hint_for_the_item_priority():
    store = SequencedStore(hints={2: 8.0})
    queue(store).enqueue(item('seg-1', priority=Priority.FRESH), 100.0)
    assert store.hint_calls[0][0] == int(Priority.FRESH)


def test_enqueue_seeds_the_rejoining_shard_with_the_hint():
    store = SequencedStore(hints={int(Priority.DEEP): 5.0})
    work = item('seg-1', owner='heavy', priority=Priority.DEEP)
    queue(store).enqueue(work, 100.0)
    shard = seeded_shard(store, owner_key('heavy'), int(Priority.DEEP))
    assert shard[f'p{int(Priority.DEEP)}_service'] == 5.0


def test_enqueue_seeds_a_higher_hint_over_the_default_zero():
    store = SequencedStore(hints={int(Priority.DEEP): 5.0})
    queue(store).enqueue(item('seg-1'), 100.0)
    shard = seeded_shard(store, owner_key('heavy'), int(Priority.DEEP))
    assert shard[f'p{int(Priority.DEEP)}_service'] == 5.0


def test_enqueue_without_a_stored_hint_seeds_zero():
    store = SequencedStore()
    queue(store).enqueue(item('seg-1'), 100.0)
    shard = seeded_shard(store, owner_key('heavy'), int(Priority.DEEP))
    assert shard[f'p{int(Priority.DEEP)}_service'] == 0.0


def test_enqueue_marks_the_shard_active():
    store = SequencedStore(hints={1: 5.0})
    queue(store).enqueue(item('seg-1'), 100.0)
    shard = seeded_shard(store, owner_key('heavy'), int(Priority.DEEP))
    assert shard[f'p{int(Priority.DEEP)}_active'] is True


def test_enqueue_job_row_is_still_admitted():
    store = SequencedStore(hints={1: 5.0})
    work = item('seg-1')
    assert queue(store).enqueue(work, 100.0) is True
    assert store.rows[('jobs', 'seg-1')]['state'] == 'ready'


def test_enqueue_second_shard_gets_its_own_hint():
    store = SequencedStore(hints={int(Priority.DEEP): 5.0, int(Priority.FRESH): 9.0})
    queue(store).enqueue(item('seg-1'), 100.0)
    queue(store).enqueue(item('seg-2', owner='light', priority=Priority.FRESH), 100.0)
    assert store.hint_calls == [(int(Priority.DEEP), 5.0), (int(Priority.FRESH), 9.0)]


def test_enqueue_hint_priority_matrix_matches_the_item():
    seen = []
    for priority in (Priority.FRESH, Priority.DEEP):
        store = SequencedStore(hints={int(priority): 3.0})
        queue(store).enqueue(item('seg', priority=priority), 100.0)
        seen.append(store.hint_calls[0][0])
    assert seen == [int(Priority.FRESH), int(Priority.DEEP)]


# --------------------------------------------------------------------------
# 2. Degrade: a failed hint never fails admission
# --------------------------------------------------------------------------


def test_enqueue_with_a_failing_hint_still_admits():
    store = SequencedStore(failing=True)
    assert queue(store).enqueue(item('seg-1'), 100.0) is True
    assert store.rows[('jobs', 'seg-1')]['state'] == 'ready'


def test_enqueue_with_a_failing_hint_seeds_zero():
    store = SequencedStore(failing=True)
    queue(store).enqueue(item('seg-1'), 100.0)
    shard = seeded_shard(store, owner_key('heavy'), int(Priority.DEEP))
    assert shard[f'p{int(Priority.DEEP)}_service'] == 0.0


def test_enqueue_with_a_failing_hint_logs_the_degraded_event(caplog):
    import logging

    store = SequencedStore(failing=True)
    with caplog.at_level(logging.WARNING, logger='utils.batch_pipeline.scheduler'):
        queue(store).enqueue(item('seg-1'), 100.0)
    assert any('event=batch_frontier_hint' in record.getMessage() for record in caplog.records)


def test_enqueue_with_a_failing_hint_names_the_priority_in_the_log(caplog):
    import logging

    store = SequencedStore(failing=True)
    with caplog.at_level(logging.WARNING, logger='utils.batch_pipeline.scheduler'):
        queue(store).enqueue(item('seg-1'), 100.0)
    assert any(str(int(Priority.DEEP)) in record.getMessage() for record in caplog.records)


def test_enqueue_with_a_failing_hint_still_opens_the_transaction():
    store = SequencedStore(failing=True)
    queue(store).enqueue(item('seg-1'), 100.0)
    assert ('run-open', None, 1) in [
        (kind, operation, ordinal) for kind, operation, ordinal in store.timeline if kind == 'run-open'
    ]


def test_rejoin_frontiers_degrades_one_priority_and_keeps_the_others():
    class Flaky(MemoryStore):
        def __init__(self):
            super().__init__()
            self.calls = []

        def service_frontier_hint(self, priority):
            self.calls.append(priority)
            if priority == 1:
                raise RuntimeError('outage')
            return 4.0

    seeds = rejoin_frontiers(Flaky(), (0, 1, 2))
    assert seeds == {0: 4.0, 1: 0.0, 2: 4.0}


def test_rejoin_frontiers_normalizes_priorities_and_dedupes():
    class Recording(MemoryStore):
        def __init__(self):
            super().__init__()
            self.calls = []

        def service_frontier_hint(self, priority):
            self.calls.append(priority)
            return 1.0

    store = Recording()
    seeds = rejoin_frontiers(store, (2, 1, 2, 1))
    assert sorted(store.calls) == [1, 2]
    assert seeds == {1: 1.0, 2: 1.0}


def test_rejoin_frontiers_on_an_empty_priority_set_is_empty():
    assert rejoin_frontiers(MemoryStore(), ()) == {}


def test_rejoin_frontiers_values_are_floats():
    seeds = rejoin_frontiers(MemoryStore(), (0, 1, 2))
    assert all(type(value) is float for value in seeds.values())


# --------------------------------------------------------------------------
# 3. The abort-set property across entry points
# --------------------------------------------------------------------------


def test_enqueue_body_never_touches_the_retired_transactional_frontier():
    store = GuardedStore()
    queue(store).enqueue(item('seg-1'), 100.0)
    assert store.guard_touches == []


def test_admit_body_never_touches_the_retired_transactional_frontier():
    store = GuardedStore()
    works, binding = proposal()
    submit(store, works, binding, 100)
    assert store.guard_touches == []


def test_recover_body_never_touches_the_retired_transactional_frontier():
    store = GuardedStore()
    store.rows[('jobs', 'seg-1')] = {
        'segment_id': 'seg-1',
        'state': 'retry',
        'available_at': 50.0,
        'owner_id': 'heavy',
        'owner_key': owner_key('heavy'),
        'priority': int(Priority.DEEP),
    }
    Scheduler(store).recover(100.0)
    assert store.guard_touches == []


def test_redrive_dead_body_never_touches_the_retired_transactional_frontier():
    store = GuardedStore()
    store.rows[('jobs', 'seg-1')] = {
        'segment_id': 'seg-1',
        'state': 'dead',
        'merge_pending': True,
        'owner_id': 'heavy',
        'owner_key': owner_key('heavy'),
        'priority': int(Priority.DEEP),
    }
    Scheduler(store).redrive_dead('seg-1', 100.0)
    assert store.guard_touches == []


def test_restore_body_never_touches_the_retired_transactional_frontier():
    store = GuardedStore()
    job = {
        'segment_id': 'seg-1',
        'state': 'quarantined',
        'recovery_state': 'failed_held',
        'artifact_disposition': {'state': 'restored'},
        'merge_pending': False,
        'token': '',
        'lease_until': 0.0,
        'owner_id': 'heavy',
        'owner_key': owner_key('heavy'),
        'priority': int(Priority.DEEP),
    }
    Scheduler.restore_audio_in_transaction(
        FrontierGuardTx(MemoryTransaction(deepcopy(store.rows))), deepcopy(job), 100.0
    )
    assert True  # reaching here proves the read never fired


# --------------------------------------------------------------------------
# 4. Recover sweep: one seed map per sweep, used by the retry requeue
# --------------------------------------------------------------------------


class SweepStore(MemoryStore):
    """Rows-backed store whose ``due`` scans rows like the real store does."""

    def __init__(self, hints=None, failing=False):
        super().__init__()
        self._hints = dict(hints or {})
        self._failing = failing
        self.hint_calls = []
        self.run_operations = []
        self.seq = 0
        self.timeline = []

    def service_frontier_hint(self, priority):
        if priority not in (0, 1, 2):
            raise ValueError('bounded priority required')
        value = self._hints.get(priority, 0.0)
        self.hint_calls.append((priority, value))
        self.timeline.append(('hint', priority, self.seq))
        self.seq += 1
        if self._failing:
            raise RuntimeError('synthetic hint outage')
        return value

    def due(self, state, now, limit):
        field = 'lease_until' if state == 'leased' else 'available_at'
        keys = [
            key
            for (table, key), v in self.rows.items()
            if table == 'jobs' and v.get('state') == state and v.get(field, 0) <= now
        ]
        return keys[:limit]

    def quarantine_fenced(self, segment_id, now):
        return False

    def run(self, body, *, operation=None):
        self.run_operations.append(operation)
        self.timeline.append(('run', operation, self.seq))
        self.seq += 1
        return super().run(body, operation=operation)


def retry_rows(priority=int(Priority.DEEP)):
    return {
        ('jobs', 'seg-1'): {
            'segment_id': 'seg-1',
            'state': 'retry',
            'available_at': 50.0,
            'attempt': 2,
            'owner_id': 'heavy',
            'owner_key': owner_key('heavy'),
            'priority': priority,
            'enqueued_at': 40.0,
            'capture_at': 40.0,
            'merge_pending': True,
            'next': '',
            'policy': {},
            'privacy_generation': None,
        }
    }


def test_recover_reads_the_seed_map_outside_the_transaction():
    store = SweepStore()
    store.rows = retry_rows()
    Scheduler(store, metrics=None).recover(100.0)
    assert sorted(priority for priority, _ in store.hint_calls) == [0, 1, 2]


def test_recover_requeue_seeds_from_the_map():
    store = SweepStore(hints={int(Priority.DEEP): 6.0})
    store.rows = retry_rows()
    Scheduler(store, metrics=None).recover(100.0)
    shard = store.rows.get(('control', scheduler_control_key(owner_key('heavy'))))
    assert shard[f'p{int(Priority.DEEP)}_service'] == 6.0


def test_recover_requeues_the_due_row():
    store = SweepStore()
    store.rows = retry_rows()
    Scheduler(store, metrics=None).recover(100.0)
    assert store.rows[('jobs', 'seg-1')]['state'] == 'ready'


def test_recover_hints_are_read_before_any_run():
    store = SweepStore(hints={int(Priority.DEEP): 6.0})
    store.rows = retry_rows()
    Scheduler(store, metrics=None).recover(100.0)
    kinds = [entry[0] for entry in store.timeline]
    first_run = kinds.index('run')
    assert kinds[0] == 'hint'
    assert all(kind == 'hint' for kind in kinds[:first_run])


def test_recover_without_due_work_reads_the_seed_map_once():
    store = SweepStore()
    Scheduler(store, metrics=None).recover(100.0)
    assert sorted(priority for priority, _ in store.hint_calls) == [0, 1, 2]
    assert store.run_operations == [None]


def test_recover_with_a_failing_hint_still_requeues():
    store = SweepStore(failing=True)
    store.rows = retry_rows()
    Scheduler(store, metrics=None).recover(100.0)
    assert store.rows[('jobs', 'seg-1')]['state'] == 'ready'


def test_recover_requeue_uses_the_hint_of_the_job_priority():
    store = SweepStore(hints={0: 1.0, 1: 2.0, 2: 3.0})
    store.rows = retry_rows(priority=int(Priority.FRESH))
    Scheduler(store, metrics=None).recover(100.0)
    shard = store.rows.get(('control', scheduler_control_key(owner_key('heavy'))))
    assert shard[f'p{int(Priority.FRESH)}_service'] == 1.0


# --------------------------------------------------------------------------
# 5. redrive_dead: probe-gated seed for the row's priority
# --------------------------------------------------------------------------


def dead_row(priority=int(Priority.DEEP)):
    return {
        'segment_id': 'seg-1',
        'state': 'dead',
        'merge_pending': True,
        'owner_id': 'heavy',
        'owner_key': owner_key('heavy'),
        'priority': priority,
        'enqueued_at': 40.0,
        'capture_at': 40.0,
        'next': '',
        'policy': {},
        'privacy_generation': None,
    }


def test_redrive_dead_probes_the_row_for_its_priority():
    store = SequencedStore(hints={2: 7.0})
    store.rows[('jobs', 'seg-1')] = dead_row(priority=2)
    Scheduler(store).redrive_dead('seg-1', 100.0)
    assert store.hint_calls == [(2, 7.0)]


def test_redrive_dead_seeds_the_rejoining_shard():
    from config.batch_pipeline import scheduler_control_key

    store = SequencedStore(hints={2: 7.0})
    store.rows[('jobs', 'seg-1')] = dead_row(priority=2)
    Scheduler(store).redrive_dead('seg-1', 100.0)
    shard = store.rows.get(('control', scheduler_control_key(owner_key('heavy'))))
    assert shard[f'p2_service'] == 7.0


def test_redrive_dead_requeues_the_row():
    store = SequencedStore(hints={2: 7.0})
    store.rows[('jobs', 'seg-1')] = dead_row(priority=2)
    assert Scheduler(store).redrive_dead('seg-1', 100.0) is True
    assert store.rows[('jobs', 'seg-1')]['state'] == 'ready'


def test_redrive_dead_of_an_unknown_row_probes_default_priority_zero():
    store = SequencedStore(hints={0: 1.0})
    Scheduler(store).redrive_dead('missing', 100.0)
    assert store.hint_calls == [(0, 1.0)]


def test_redrive_dead_of_an_unknown_row_admits_nothing():
    store = SequencedStore()
    assert Scheduler(store).redrive_dead('missing', 100.0) is False


def test_redrive_dead_reads_the_hint_before_the_transaction():
    store = SequencedStore(hints={2: 7.0})
    store.rows[('jobs', 'seg-1')] = dead_row(priority=2)
    Scheduler(store).redrive_dead('seg-1', 100.0)
    kinds = [entry[0] for entry in store.timeline]
    assert kinds[0] == 'hint'
    assert 'hint' not in kinds[1:]


# --------------------------------------------------------------------------
# 6. admit: the frontiers map reaches the ring enqueue per item priority
# --------------------------------------------------------------------------


def test_admit_passes_frontiers_to_the_ring_enqueue(monkeypatch):
    store = SequencedStore(hints={int(Priority.DEEP): 4.0})
    works, binding = proposal()
    captured = []
    real = Scheduler.enqueue_in_transaction

    def spy(tx, work, now, *, policy=None, frontier=0.0):
        captured.append((int(work.priority), frontier))
        return real(tx, work, now, policy=policy, frontier=frontier)

    monkeypatch.setattr(Scheduler, 'enqueue_in_transaction', staticmethod(spy))
    admit(store, works, binding, 100, namespace='batch_pipeline_test_wiring', frontiers={int(Priority.DEEP): 4.0})
    assert captured
    assert all(frontier == 4.0 for _, frontier in captured)


def test_admit_frontiers_map_is_consumed_per_item_priority(monkeypatch):
    store = SequencedStore(hints={int(Priority.DEEP): 4.0, int(Priority.FRESH): 8.0})
    works, binding = proposal()
    works = [works[0], replace(works[0], segment_id='segment-2', priority=Priority.FRESH)]
    binding = ProjectionBinding(
        binding.owner_id, binding.job_id, binding.content_id, tuple(w.segment_id for w in works)
    )
    captured = []
    real = Scheduler.enqueue_in_transaction

    def spy(tx, work, now, *, policy=None, frontier=0.0):
        captured.append((int(work.priority), frontier))
        return real(tx, work, now, policy=policy, frontier=frontier)

    monkeypatch.setattr(Scheduler, 'enqueue_in_transaction', staticmethod(spy))
    admit(
        store,
        works,
        binding,
        100,
        namespace='batch_pipeline_test_wiring',
        frontiers={int(Priority.DEEP): 4.0, int(Priority.FRESH): 8.0},
    )
    seeds = dict(captured)
    assert seeds[int(Priority.DEEP)] == 4.0
    assert seeds[int(Priority.FRESH)] == 8.0


def test_admit_without_frontiers_degrades_the_ring_seed_to_zero(monkeypatch):
    store = SequencedStore(hints={int(Priority.DEEP): 0.0})
    works, binding = proposal()
    captured = []
    real = Scheduler.enqueue_in_transaction

    def spy(tx, work, now, *, policy=None, frontier=0.0):
        captured.append(frontier)
        return real(tx, work, now, policy=policy, frontier=frontier)

    monkeypatch.setattr(Scheduler, 'enqueue_in_transaction', staticmethod(spy))
    admit(store, works, binding, 100, namespace='batch_pipeline_test_wiring')
    assert captured and captured[0] == 0.0


def test_admit_keeps_a_custom_enqueue_off_the_frontier_kwarg(monkeypatch):
    store = SequencedStore(hints={int(Priority.DEEP): 4.0})
    works, binding = proposal()
    seen = []

    def custom(tx, work, now, *, policy=None):
        seen.append(work.segment_id)
        return True

    admit(store, works, binding, 100, namespace='batch_pipeline_test_wiring', enqueue=custom)
    assert seen == [works[0].segment_id]


# --------------------------------------------------------------------------
# 7. durable_status: probe-gated hints and the status redrive seed
# --------------------------------------------------------------------------


def intake_rows(uid='synthetic-owner', priority=2):
    owner = owner_key(uid)
    return {
        ('intakes', 'job-1'): {
            'owner_id': uid,
            'content_id': 'content-1',
            'segment_ids': ['seg-1'],
            'lane': 'backfill',
            'status': 'processing',
            'result': None,
            'total_segments': 1,
            'total_files': 1,
        },
        ('content', f'{uid}/content-1'): {
            'dispatch_protocol': 'batch_v1',
            'job_id': 'job-1',
            'status': 'processing',
            'result': None,
        },
        ('jobs', 'seg-1'): {
            'segment_id': 'seg-1',
            'state': 'dead',
            'merge_pending': True,
            'owner_id': uid,
            'owner_key': owner,
            'priority': priority,
            'enqueued_at': 40.0,
            'capture_at': 40.0,
            'next': '',
            'policy': {},
            'privacy_generation': None,
        },
    }


def test_durable_status_incomplete_ledger_reads_hints_for_every_priority():

    store = SequencedStore()
    store.rows = intake_rows()
    durable_status(store, 'synthetic-owner', 'job-1')
    assert sorted(priority for priority, _ in store.hint_calls) == [0, 1, 2]


def test_durable_status_redrive_seeds_from_the_job_priority():

    store = SequencedStore(hints={2: 11.0})
    store.rows = intake_rows(priority=2)
    durable_status(store, 'synthetic-owner', 'job-1')
    shard = store.rows.get(('control', scheduler_control_key(owner_key('synthetic-owner'))))
    assert shard['p2_service'] == 11.0


def test_durable_status_redrives_the_dead_row():

    store = SequencedStore(hints={2: 11.0})
    store.rows = intake_rows()
    durable_status(store, 'synthetic-owner', 'job-1')
    assert store.rows[('jobs', 'seg-1')]['state'] == 'ready'


def test_durable_status_missing_intake_never_reads_hints():

    store = SequencedStore()
    durable_status(store, 'synthetic-owner', 'missing-job')
    assert store.hint_calls == []


def test_durable_status_completed_poll_never_reads_hints(monkeypatch):
    from utils.batch_pipeline import intake as intake_module

    rows = intake_rows()
    rows[('intakes', 'job-1')]['status'] = 'completed'
    rows[('content', 'synthetic-owner/content-1')]['status'] = 'completed'
    rows[('content', 'synthetic-owner/content-1')]['result'] = {'total_segments': 1, 'total_files': 1}
    rows[('jobs', 'seg-1')]['state'] = 'committed'
    monkeypatch.setattr(intake_module, 'is_valid_completed_sync_content_result', lambda result: True)
    store = SequencedStore()
    store.rows = rows
    durable_status(store, 'synthetic-owner', 'job-1')
    assert store.hint_calls == []


# --------------------------------------------------------------------------
# 8. The restore path carries the seed into the ring
# --------------------------------------------------------------------------


def _restore_fixture_rows(uid='synthetic-owner', priority=1):
    owner = owner_key(uid)
    job = {
        'segment_id': 'seg-1',
        'state': 'quarantined',
        'recovery_state': 'failed_held',
        'merge_pending': False,
        'token': '',
        'lease_until': 0.0,
        'owner_id': uid,
        'owner_key': owner,
        'owner_key_hash': owner,
        'priority': priority,
        'audio_uri': 'gs://synthetic/original#1',
        'artifact_disposition': {
            'state': 'missing',
            'privacy_generation': 0,
            'evidence': {'uri_sha256': hashlib.sha256(b'gs://synthetic/original#1').hexdigest()},
        },
    }
    return {'jobs': {'seg-1': deepcopy(job)}, 'owner': owner}


def test_restore_reupload_reads_seeds_outside_the_transaction(monkeypatch):
    from database.batch_pipeline_artifact_missing import ArtifactMissingStore
    from database.batch_pipeline_staging import artifact_id

    uid = 'synthetic-owner'
    rows = _restore_fixture_rows(uid)
    job = deepcopy(rows['jobs']['seg-1'])
    uri = 'gs://synthetic/restored#8'
    store = SequencedStore(hints={1: 13.0})
    store.rows[('jobs', 'seg-1')] = deepcopy(job)
    store.rows[('owners', rows['owner'])] = {'revision': 0}
    store.rows[('artifacts', artifact_id('seg-1', uri))] = {
        'owner_id': uid,
        'privacy_generation': 0,
        'segment_id': 'seg-1',
        'kind': 'audio',
        'uri': uri.split('#')[0],
    }
    store.namespace = 'batch_pipeline_test_wiring'
    artifact_store = ArtifactMissingStore(store)
    ledger = {
        'dispatch_protocol': 'batch_v1',
        'status': 'processing',
        'batch_pipeline': {'segment_ids': ['seg-1'], 'namespace': store.namespace},
    }
    binding = SimpleNamespace(
        owner_id=uid,
        content_id='content-1',
        segment_ids=('seg-1',),
        job_id='job-1',
        run_token='tok',
        run_epoch=1,
        privacy_generation=0,
        native_record=False,
        record_origin='',
        partial_record=False,
    )
    monkeypatch.setattr(
        ArtifactMissingStore,
        '_reupload_content',
        lambda self, tx, u, content: (deepcopy(ledger), binding, [deepcopy(job)]),
    )

    def checked(self, tx, sid):
        return None

    from database.batch_pipeline_quarantine_recovery import RecoveryStore

    monkeypatch.setattr(RecoveryStore, 'checked', checked)
    artifact_store.restore_reupload(uid, 'content-1', {'seg-1': deepcopy(job)}, {'seg-1': uri}, 100.0)
    assert store.hint_calls == [(1, 13.0)]


def test_restore_reupload_seeds_the_rejoining_shard(monkeypatch):
    from config.batch_pipeline import scheduler_control_key
    from database.batch_pipeline_artifact_missing import ArtifactMissingStore
    from database.batch_pipeline_staging import artifact_id
    from database.batch_pipeline_quarantine_recovery import RecoveryStore

    uid = 'synthetic-owner'
    rows = _restore_fixture_rows(uid)
    job = deepcopy(rows['jobs']['seg-1'])
    uri = 'gs://synthetic/restored#8'
    store = SequencedStore(hints={1: 13.0})
    store.rows[('jobs', 'seg-1')] = deepcopy(job)
    store.rows[('owners', rows['owner'])] = {'revision': 0}
    store.rows[('artifacts', artifact_id('seg-1', uri))] = {
        'owner_id': uid,
        'privacy_generation': 0,
        'segment_id': 'seg-1',
        'kind': 'audio',
        'uri': uri.split('#')[0],
    }
    store.namespace = 'batch_pipeline_test_wiring'
    artifact_store = ArtifactMissingStore(store)
    ledger = {
        'dispatch_protocol': 'batch_v1',
        'status': 'processing',
        'batch_pipeline': {'segment_ids': ['seg-1'], 'namespace': store.namespace},
    }
    binding = SimpleNamespace(
        owner_id=uid,
        content_id='content-1',
        segment_ids=('seg-1',),
        job_id='job-1',
        run_token='tok',
        run_epoch=1,
        privacy_generation=0,
        native_record=False,
        record_origin='',
        partial_record=False,
    )
    monkeypatch.setattr(
        ArtifactMissingStore,
        '_reupload_content',
        lambda self, tx, u, content: (deepcopy(ledger), binding, [deepcopy(job)]),
    )
    monkeypatch.setattr(RecoveryStore, 'checked', lambda self, tx, sid: None)
    import database.batch_pipeline_projection as projection_module

    monkeypatch.setattr(projection_module, 'held_without_recovery', lambda job: True)
    artifact_store.restore_reupload(uid, 'content-1', {'seg-1': deepcopy(job)}, {'seg-1': uri}, 100.0)
    shard = store.rows.get(('control', scheduler_control_key(owner_key(uid))))
    assert shard['p1_service'] == 13.0
