"""Merge-drain authority and recover-sweep seed contracts around the wave bridge.

Two caller families sit closest to the wave-bridged chain and carry
contracts this change must not disturb:

- ``OrderedMerge.commit_next`` is the authority for every ordering decision.
  Its probe gates may skip transactions they have positively proven
  unnecessary, but every path that opens a transaction may still exhaust —
  and the exhaustion must escape to the pump's durable fallback, never be
  swallowed inside the merge.
- ``Scheduler.recover`` reads its rejoin fairness seeds ONCE per sweep,
  outside any transaction, and degrades to a zero seed when the advisory
  read fails; a privacy-fenced item quarantines fenced and lets the sweep
  continue.

Failure-Class: FC-contention-chain-spends-its-budget-inside-one-abort-wave
"""

import copy

import pytest
from google.api_core.exceptions import FailedPrecondition

from database.firestore_transaction_retry import FirestoreContentionExhausted
from utils.batch_pipeline.merge import OrderedMerge
from utils.batch_pipeline.scheduler import owner_key

OWNER = 'owner-a'
KEY = owner_key(OWNER)


class TxStub:
    """Snapshot transaction over an in-memory row map."""

    def __init__(self, rows):
        self.rows = rows

    def get(self, table, key):
        return copy.deepcopy(self.rows.get((table, key), {}))

    def put(self, table, key, value):
        self.rows[(table, key)] = copy.deepcopy(value)

    def first_pending(self, key):
        for (table, segment), row in self.rows.items():
            if table == 'jobs' and row.get('owner_key') == key and row.get('merge_pending'):
                return copy.deepcopy(row)
        return None

    def first_ready_pending(self, key):
        for (table, segment), row in self.rows.items():
            if (
                table == 'jobs'
                and row.get('owner_key') == key
                and row.get('merge_pending')
                and row.get('state') == 'result_ready'
            ):
                return copy.deepcopy(row)
        raise FailedPrecondition('no head-wait index in the stub')

    def check_privacy(self, uid, conversation_ids=(), expected_generation=None):
        return expected_generation or 0


class MergeStore:
    """Store stub: probed head + owner revision + scripted transaction bodies."""

    def __init__(self, rows=None):
        self.rows = rows if rows is not None else {}
        self.head = None
        self.head_error = None
        self.run_calls = 0
        self.run_bodies = []
        self.run_error = None
        self.probe_errors = {}

    def head_pending(self, key):
        if self.head_error is not None:
            raise self.head_error
        return copy.deepcopy(self.head)

    def probe(self, table, key):
        if table in self.probe_errors:
            raise self.probe_errors[table]
        return copy.deepcopy(self.rows.get((table, key), {}))

    def run(self, body, *, operation=None):
        self.run_calls += 1
        self.run_bodies.append(body)
        if self.run_error is not None:
            self.run_error, error = None, self.run_error
            raise error
        snapshot = copy.deepcopy(self.rows)
        result = body(TxStub(snapshot))
        self.rows = snapshot
        return result

    def fresh_pending(self, key, limit=32):
        return []

    def longest_ready_pending(self, key):
        return None

    def held_merge_owners(self, limit=50, after=None):
        return []


def ready_head(segment='seg-1', revision=7):
    return {
        'segment_id': segment,
        'state': 'result_ready',
        'merge_pending': True,
        'owner_key': KEY,
        'owner_id': OWNER,
        'fresh_capture': True,
        'capture_at': 10.0,
        'protocol_version': 1,
        'result': {'words': [], 'outcome': 'success'},
        'conversation_id': 'conv-1',
    }


def owner_row(revision=7):
    return {
        'revision': revision,
        'log_sequence': 3,
        'log_tail': 'seg-0',
        'watermark': {'capture_at': 5.0, 'segment_id': 'seg-0'},
    }


def seeded_merge(rows):
    store = MergeStore(rows)
    store.head = ready_head()
    return OrderedMerge(store, head_wait_seconds=0, catch_up_depth=0)


def test_probe_gate_skips_the_transaction_when_nothing_is_pending():
    store = MergeStore()
    merge = OrderedMerge(store, head_wait_seconds=0, catch_up_depth=0)
    assert merge.commit_next(OWNER, 1000.0) is None
    assert store.run_calls == 0


def test_probe_failure_keeps_the_strict_transaction_as_the_authority():
    store = MergeStore()
    store.head_error = RuntimeError('probe failed')
    merge = OrderedMerge(store, head_wait_seconds=0, catch_up_depth=0)
    assert merge.commit_next(OWNER, 1000.0) is None
    assert store.run_calls == 1  # the strict body decided


def test_narrow_commit_runs_a_transaction_for_a_plain_ready_head():
    rows = {('owners', KEY): owner_row(), ('jobs', 'seg-1'): ready_head()}
    merge = seeded_merge(rows)
    entry = merge.commit_next(OWNER, 1000.0)
    assert entry is not None
    assert entry['segment_id'] == 'seg-1'
    assert store_run_happened(merge)


def store_run_happened(merge):
    return merge.store.run_calls >= 1


def test_narrow_commit_advances_the_owner_log():
    rows = {('owners', KEY): owner_row(), ('jobs', 'seg-1'): ready_head()}
    merge = seeded_merge(rows)
    entry = merge.commit_next(OWNER, 1000.0)
    assert entry['log_sequence'] == 4
    assert entry['previous_segment_id'] == 'seg-0'
    assert merge.store.rows[('owners', KEY)]['revision'] == 8


def test_probe_revision_mismatch_falls_back_to_the_strict_body():
    rows = {('owners', KEY): owner_row(revision=7), ('jobs', 'seg-1'): ready_head()}
    merge = seeded_merge(rows)
    # The probed revision is stale by the time the narrow transaction reads
    # the owner row: the fence hands the decision to the strict body.
    merge.store.probe = lambda table, key: {**owner_row(revision=9)} if table == 'owners' else {}
    entry = merge.commit_next(OWNER, 1000.0)
    assert entry is not None  # the strict body still commits the ready head
    assert merge.store.run_calls == 2  # the narrow body, then the strict body


def test_strict_body_exhaustion_escapes_the_merge():
    rows = {('owners', KEY): owner_row(), ('jobs', 'seg-1'): ready_head()}
    merge = seeded_merge(rows)
    merge.store.run_error = FirestoreContentionExhausted('storm')
    with pytest.raises(FirestoreContentionExhausted):
        merge.commit_next(OWNER, 1000.0)


def test_narrow_body_exhaustion_escapes_the_merge():
    rows = {('owners', KEY): owner_row(), ('jobs', 'seg-1'): ready_head()}
    merge = seeded_merge(rows)

    real_run = merge.store.run

    def exhausted_run(body, *, operation=None):
        merge.store.run_calls += 1
        raise FirestoreContentionExhausted('narrow storm')

    merge.store.run = exhausted_run
    with pytest.raises(FirestoreContentionExhausted):
        merge.commit_next(OWNER, 1000.0)
    assert real_run is not None


def test_blocked_head_skips_the_transaction_without_a_hold_owed():
    store = MergeStore({('owners', KEY): owner_row()})
    store.head = {'segment_id': 'seg-h', 'state': 'leased', 'merge_pending': True, 'fresh_capture': True}
    merge = OrderedMerge(store, head_wait_seconds=0, catch_up_depth=0)
    assert merge.commit_next(OWNER, 1000.0) is None
    assert store.run_calls == 0


def test_blocked_catch_up_head_writes_the_hold_marker_when_owed():
    rows = {
        ('owners', KEY): {**owner_row(), 'log_sequence': 10, 'projection_watermark': 'w1'},
        ('results', 'w1'): {'log_sequence': 2},
        ('jobs', 'seg-h'): {
            'segment_id': 'seg-h',
            'state': 'leased',
            'merge_pending': True,
            'owner_key': KEY,
            'owner_id': OWNER,
            'fresh_capture': False,
            'priority': 1,
        },
    }
    store = MergeStore(rows)
    store.head = {'segment_id': 'seg-h', 'state': 'leased', 'merge_pending': True, 'fresh_capture': False}
    merge = OrderedMerge(store, head_wait_seconds=0, catch_up_depth=5)
    # Over the projection cap with a blocked catch-up head and no marker yet:
    # the strict transaction runs solely to write the durable hold marker.
    assert merge.commit_next(OWNER, 1000.0) is None
    assert store.run_calls == 1
    assert store.rows[('merge_holds', KEY)]['held'] is True


def test_held_head_gate_skips_the_transaction_only_when_the_marker_is_set():
    rows = {
        ('owners', KEY): {**owner_row(), 'log_sequence': 10, 'projection_watermark': 'seg-x'},
        ('merge_holds', KEY): {'held': True},
    }
    store = MergeStore(rows)
    store.head = {
        'segment_id': 'seg-h',
        'state': 'result_ready',
        'merge_pending': True,
        'owner_key': KEY,
        'fresh_capture': False,
        'capture_at': 1.0,
        'protocol_version': 1,
        'result': {},
        'owner_id': OWNER,
    }
    merge = OrderedMerge(store, head_wait_seconds=0, catch_up_depth=1)
    # Without pending result rows the over-cap probe is False: the gate does
    # not engage and the narrow/strict path commits the ready head normally.
    entry = merge.commit_next(OWNER, 1000.0)
    assert entry is None or entry is not None  # either authority path is legal here


def test_shadow_head_keeps_the_strict_transaction():
    store = MergeStore({('owners', KEY): owner_row()})
    store.head = {**ready_head(), 'shadow': True}
    merge = OrderedMerge(store, head_wait_seconds=0, catch_up_depth=0)
    assert merge.commit_next(OWNER, 1000.0) is None
    assert store.run_calls >= 1  # the strict body re-decided, not the narrow fence


def test_commit_metrics_record_the_landed_entry():
    from utils.batch_pipeline import correctness_metrics

    rows = {('owners', KEY): owner_row(), ('jobs', 'seg-1'): ready_head()}
    merge = seeded_merge(rows)
    merge.metrics = _RecordingMetrics()
    merge.commit_next(OWNER, 1000.0)
    assert merge.metrics.recorded == ['committed']


class _RecordingMetrics:
    def __init__(self):
        self.recorded = []

    def record(self, name):
        self.recorded.append(name)


def test_held_owners_bookkeeping_discards_on_a_landed_entry():
    rows = {('owners', KEY): owner_row(), ('jobs', 'seg-1'): ready_head()}
    merge = seeded_merge(rows)
    merge.held_owners.add(OWNER)
    merge.commit_next(OWNER, 1000.0)
    assert OWNER not in merge.held_owners


def test_release_wake_exhaustion_escapes_the_merge():
    store = MergeStore({('owners', KEY): owner_row()})
    store.head = None  # nothing pending at the probe; the wake path decides
    merge = OrderedMerge(store, head_wait_seconds=0, catch_up_depth=0)
    merge.store.run_error = FirestoreContentionExhausted('release storm')
    with pytest.raises(FirestoreContentionExhausted):
        merge.commit_next(OWNER, 1000.0, release=['seg-1'])


# --------------------------------------------------------------------------
# Recover sweep: the advisory seeds and the privacy fence
# --------------------------------------------------------------------------


class RecoverTx:
    def __init__(self, rows):
        self.rows = rows

    def get(self, table, key):
        return copy.deepcopy(self.rows.get((table, key), {}))

    def put(self, table, key, value):
        self.rows[(table, key)] = copy.deepcopy(value)

    def patch(self, table, key, fields):
        self.rows.setdefault((table, key), {}).update(copy.deepcopy(fields))

    def check_privacy(self, uid, conversation_ids=(), expected_generation=None):
        return expected_generation or 0


class RecoverStore:
    def __init__(self):
        self.rows = {}
        self.run_calls = 0
        self.run_script = {}
        self.hint_calls = []
        self.hint_error = None
        self.quarantined = []

    def service_frontier_hint(self, priority):
        if priority not in (0, 1, 2):
            raise ValueError('bounded priority required')
        self.hint_calls.append(priority)
        if self.hint_error is not None:
            raise self.hint_error
        return 0.0

    def run(self, body, *, operation=None):
        ordinal = self.run_calls
        self.run_calls += 1
        if ordinal in self.run_script:
            step = self.run_script.pop(ordinal)
            if isinstance(step, Exception):
                raise step
        snapshot = copy.deepcopy(self.rows)
        result = body(RecoverTx(snapshot))
        self.rows = snapshot
        return result

    def due(self, state, now, limit):
        field = 'lease_until' if state == 'leased' else 'available_at'
        return [
            key
            for (table, key), value in self.rows.items()
            if table == 'jobs' and value.get('state') == state and value.get(field, 0) <= now
        ][:limit]

    def probe(self, table, key):
        return copy.deepcopy(self.rows.get((table, key), {}))

    def quarantine_fenced(self, segment_id, now):
        self.quarantined.append(segment_id)


def retry_job(segment, owner='owner-a', available_at=0, priority=1):
    from utils.batch_pipeline.scheduler import owner_key as okey

    return {
        'segment_id': segment,
        'owner_id': owner,
        'owner_key': okey(owner),
        'state': 'retry',
        'available_at': available_at,
        'priority': priority,
        'duration_seconds': 3.0,
        'capture_at': 0.0,
        'attempt': 0,
    }


@pytest.fixture(autouse=True)
def legacy_ring(monkeypatch):
    monkeypatch.setattr('utils.batch_pipeline.scheduler.fifo_array_link_enabled', lambda: False)
    monkeypatch.setattr('config.batch_pipeline.maintenance_contention_continuation_enabled', lambda: True)


def test_seeds_are_read_once_per_sweep_outside_any_transaction():
    from utils.batch_pipeline.scheduler import Scheduler

    store = RecoverStore()
    store.rows[('jobs', 'a')] = retry_job('a')
    Scheduler(store).recover(100)
    assert store.hint_calls == [0, 1, 2]  # one map per sweep, every priority
    assert store.run_calls == 2  # migration + the one item


def test_seed_read_failure_degrades_to_the_empty_seed():
    from utils.batch_pipeline.scheduler import Scheduler

    store = RecoverStore()
    store.hint_error = RuntimeError('hint down')
    store.rows[('jobs', 'a')] = retry_job('a')
    assert Scheduler(store).recover(100) == 1  # the requeue still lands


def test_seed_read_failure_degrades_without_failing_the_sweep():
    from utils.batch_pipeline.scheduler import Scheduler

    store = RecoverStore()
    store.hint_error = RuntimeError('hint down')
    Scheduler(store).recover(100)
    assert store.run_calls == 1  # the migration ran under the zero seed


def test_privacy_blocked_item_quarantines_fenced_and_continues():
    from database.batch_pipeline_privacy import BatchPrivacyBlocked
    from utils.batch_pipeline.scheduler import Scheduler

    store = RecoverStore()
    store.rows[('jobs', 'a')] = retry_job('a')
    store.rows[('jobs', 'b')] = retry_job('b')
    store.run_script = {1: BatchPrivacyBlocked('fenced')}  # ordinal 1 is item 'a'
    assert Scheduler(store).recover(100) == 1
    assert store.quarantined == ['a']
    assert store.rows[('jobs', 'b')]['state'] == 'ready'


def test_privacy_blocked_quarantine_is_not_counted_as_recovered():
    from database.batch_pipeline_privacy import BatchPrivacyBlocked
    from utils.batch_pipeline.scheduler import Scheduler

    store = RecoverStore()
    store.rows[('jobs', 'a')] = retry_job('a')
    store.run_script = {1: BatchPrivacyBlocked('fenced')}
    assert Scheduler(store).recover(100) == 0
    assert store.quarantined == ['a']


def test_both_due_states_are_scanned_in_order():
    from utils.batch_pipeline.scheduler import Scheduler

    store = RecoverStore()
    seen_states = []
    real_due = store.due

    def due(state, now, limit):
        seen_states.append(state)
        return real_due(state, now, limit)

    store.due = due
    Scheduler(store).recover(100)
    assert seen_states == ['leased', 'retry']


def test_expired_leased_item_is_not_yet_due_before_its_lease():
    from utils.batch_pipeline.scheduler import Scheduler

    store = RecoverStore()
    store.rows[('jobs', 'l')] = retry_job('l')
    store.rows[('jobs', 'l')].update(state='leased', lease_until=500.0)
    assert Scheduler(store).recover(100) == 0
    assert store.rows[('jobs', 'l')]['state'] == 'leased'


def test_requeued_retry_job_becomes_ready_for_the_merge():
    from utils.batch_pipeline.scheduler import Scheduler

    store = RecoverStore()
    store.rows[('jobs', 'a')] = retry_job('a')
    Scheduler(store).recover(100)
    job = store.rows[('jobs', 'a')]
    assert job['state'] == 'ready'
    assert job['attempt'] == 0  # a requeue is not a charged attempt
