"""Fleet window boundary grid

Pins every fail-open boundary: the malformed-payload corpus, valid payloads with extra fields, the fault matrix, the operation-label grammar (including composite serving-pull shard classes), dormancy under each kill switch, namespace isolation, the mirror bound and eviction, the bounded call budget, the reset seam, and the publish skip/overwrite matrix.

Failure-Class: FC-storm-window-never-leaves-the-process

Generated point pins: every test below drives the real
``database.batch_pipeline_store`` fleet window on deterministic injected
clocks and asserts one point of an input surface. The harness is shared with
``tests/unit/test_batch_store_fleet_storm_window_contract.py`` and is restated
here so each grid file runs isolated.
"""

import logging
from unittest.mock import Mock

import pytest
from google.api_core.exceptions import Aborted

from database import batch_pipeline_store as storage

BASE_SECONDS = storage.FirestoreStore.STORM_DAMPER_BASE_SECONDS  # 0.25
CAP_SECONDS = storage.FirestoreStore.STORM_DAMPER_CAP_SECONDS  # 4.0
LADDER_STEPS = storage.FirestoreStore.STORM_DAMPER_LADDER_STEPS  # 4


class AbortThenCommitTx:
    """Minimal firestore_v1.Transaction: the first ``abort_times`` commits abort."""

    _max_attempts = 1
    _read_only = False
    _id = None

    def __init__(self, abort_times=0):
        self.abort_times = abort_times
        self.commits = 0

    def _clean_up(self):
        self._id = None

    def _begin(self, retry_id=None):
        self._id = b'synthetic'

    def _commit(self):
        self.commits += 1
        if self.abort_times > 0:
            self.abort_times -= 1
            raise Aborted('synthetic commit contention')
        self._id = None

    def _rollback(self):
        self._id = None


class FakeClock:
    """Deterministic monotonic clock, sleeper recorder and jitter source."""

    def __init__(self, now=100.0, jitter=0.0):
        self.now = now
        self.jitter = jitter
        self.sleeps = []

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        assert seconds >= 0, 'damper must never sleep a negative residual'
        self.sleeps.append(seconds)
        self.now += seconds

    def random_value(self):
        return self.jitter


class FakeWall:
    """Deterministic wall clock for the fleet mirror."""

    def __init__(self, now=1_000_000.0):
        self.now = now

    def time(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


class StormDocsClient:
    """Transactions for the store plus a dict-backed storm-window collection.

    ``get_calls`` rows are ``(collection, doc_id, timeout)``; ``set_calls``
    rows are ``(collection, doc_id, payload, merge, timeout)`` — both lanes
    record the bounded call budget the production code passes.
    """

    def __init__(self, abort_times=0):
        self.abort_times = abort_times
        self._aborts_left = abort_times  # the abort budget is the CLIENT's, shared by every chain
        self.docs = {}
        self.get_calls = []
        self.set_calls = []
        self.fail_gets = 0
        self.fail_sets = 0

    class Snapshot:
        def __init__(self, data):
            self._data = data

        @property
        def exists(self):
            return self._data is not None

        def to_dict(self):
            return self._data

    def transaction(self, max_attempts=5):
        if self._aborts_left > 0:
            self._aborts_left -= 1
            return AbortThenCommitTx(1)  # this chain aborts once
        return AbortThenCommitTx(0)

    def collection(self, name):
        return _StormDocsCollection(self, name)


class _StormDocsCollection:
    def __init__(self, client, name):
        self._client = client
        self._name = name

    def document(self, doc_id):
        return _StormDocsDoc(self._client, self._name, doc_id)


class _StormDocsDoc:
    def __init__(self, client, name, doc_id):
        self._client = client
        self._name = name
        self._doc_id = doc_id

    def get(self, timeout=None):
        client = self._client
        client.get_calls.append((self._name, self._doc_id, timeout))
        if client.fail_gets > 0:
            client.fail_gets -= 1
            raise IOError('synthetic storm-window read fault')
        return StormDocsClient.Snapshot(client.docs.get((self._name, self._doc_id)))

    def set(self, data, merge=False, timeout=None):
        client = self._client
        client.set_calls.append((self._name, self._doc_id, dict(data), merge, timeout))
        if client.fail_sets > 0:
            client.fail_sets -= 1
            raise IOError('synthetic storm-window write fault')
        key = (self._name, self._doc_id)
        if merge:
            client.docs.setdefault(key, {}).update(dict(data))
        else:
            client.docs[key] = dict(data)


def adopt_clocks(namespace, jitter=0.0, now=100.0, wall_now=1_000_000.0):
    """The registry damper and fleet mirror of ``namespace`` on one clock set."""
    clock = FakeClock(now=now, jitter=jitter)
    wall = FakeWall(now=wall_now)
    damper = storage.shared_storm_damper(namespace)
    damper._monotonic = clock.monotonic
    damper._sleeper = clock.sleep
    damper._random_value = clock.random_value
    storage.fleet_storm_window(namespace)._wall_now = wall.time
    return damper, storage.fleet_storm_window(namespace), clock, wall


def default_store(monkeypatch, namespace='batch_pipeline_dev', client=None):
    """A store on the process-shared damper (no ``storm_damper=`` injection)."""
    stage = 'prod' if namespace == 'batch_pipeline_prod' else 'dev'
    monkeypatch.setenv('OMI_ENV_STAGE', stage)
    return storage.FirestoreStore(namespace, firestore_client=client if client is not None else Mock())


def silence_chain_sleep(monkeypatch):
    """Drop the retry chain's own sleeps; the damper's sleeps stay recorded."""
    actual = storage.run_with_transaction_contention_retry

    def factory(*args, **kwargs):
        kwargs.setdefault('sleep', lambda _seconds: None)
        kwargs.setdefault('random_value', lambda: 0.0)
        return actual(*args, **kwargs)

    monkeypatch.setattr(storage, 'run_with_transaction_contention_retry', factory)


def exhaust_run(store, label, times=1):
    """Drive ``label`` to exhaustion ``times`` times; return the last error."""
    error = None
    for _ in range(times):
        try:
            store.run(lambda tx: True, operation=label)
        except storage.FirestoreContentionExhausted as caught:
            error = caught
        else:
            raise AssertionError('expected exhaustion')
    return error


def fresh_window(namespace='batch_pipeline_dev', wall=None):
    """A standalone fleet window on its own (or a shared) wall clock."""
    return storage._FleetStormWindow(namespace, wall_now=(wall or FakeWall()).time)


def arm_maximum(failures):
    """The ladder high bound the damper arms for the ``failures``-th exhaustion."""
    return min(CAP_SECONDS, BASE_SECONDS * (2 ** min(failures - 1, LADDER_STEPS)))


def arm_applied(failures, jitter):
    """The applied window: the high bound under the equal jitter."""
    return arm_maximum(failures) * (0.5 + 0.5 * jitter)


# --------------------------------------------------------------------------
# Malformed payload corpus x wall offsets
# --------------------------------------------------------------------------


def test_malformed_bool_true_wall0p0():
    wall = FakeWall(now=50.0)
    window = fresh_window(wall=wall)
    client = StormDocsClient()
    client.docs[('batch_pipeline_dev_storm_dampers', 'batch_merge')] = {'armed_until': True}
    wall.advance(0.0)
    assert window.peek('batch_merge', client=client) == 0.0
    assert window.malformed_reads == 1
    assert window.failed_reads == 0


def test_malformed_bool_true_wall0p5():
    wall = FakeWall(now=50.0)
    window = fresh_window(wall=wall)
    client = StormDocsClient()
    client.docs[('batch_pipeline_dev_storm_dampers', 'batch_merge')] = {'armed_until': True}
    wall.advance(0.5)
    assert window.peek('batch_merge', client=client) == 0.0
    assert window.malformed_reads == 1
    assert window.failed_reads == 0


def test_malformed_bool_true_wall2p0():
    wall = FakeWall(now=50.0)
    window = fresh_window(wall=wall)
    client = StormDocsClient()
    client.docs[('batch_pipeline_dev_storm_dampers', 'batch_merge')] = {'armed_until': True}
    wall.advance(2.0)
    assert window.peek('batch_merge', client=client) == 0.0
    assert window.malformed_reads == 1
    assert window.failed_reads == 0


def test_malformed_bool_false_wall0p0():
    wall = FakeWall(now=50.0)
    window = fresh_window(wall=wall)
    client = StormDocsClient()
    client.docs[('batch_pipeline_dev_storm_dampers', 'batch_merge')] = {'armed_until': False}
    wall.advance(0.0)
    assert window.peek('batch_merge', client=client) == 0.0
    assert window.malformed_reads == 1
    assert window.failed_reads == 0


def test_malformed_bool_false_wall0p5():
    wall = FakeWall(now=50.0)
    window = fresh_window(wall=wall)
    client = StormDocsClient()
    client.docs[('batch_pipeline_dev_storm_dampers', 'batch_merge')] = {'armed_until': False}
    wall.advance(0.5)
    assert window.peek('batch_merge', client=client) == 0.0
    assert window.malformed_reads == 1
    assert window.failed_reads == 0


def test_malformed_bool_false_wall2p0():
    wall = FakeWall(now=50.0)
    window = fresh_window(wall=wall)
    client = StormDocsClient()
    client.docs[('batch_pipeline_dev_storm_dampers', 'batch_merge')] = {'armed_until': False}
    wall.advance(2.0)
    assert window.peek('batch_merge', client=client) == 0.0
    assert window.malformed_reads == 1
    assert window.failed_reads == 0


def test_malformed_string_wall0p0():
    wall = FakeWall(now=50.0)
    window = fresh_window(wall=wall)
    client = StormDocsClient()
    client.docs[('batch_pipeline_dev_storm_dampers', 'batch_merge')] = {'armed_until': '51.0'}
    wall.advance(0.0)
    assert window.peek('batch_merge', client=client) == 0.0
    assert window.malformed_reads == 1
    assert window.failed_reads == 0


def test_malformed_string_wall0p5():
    wall = FakeWall(now=50.0)
    window = fresh_window(wall=wall)
    client = StormDocsClient()
    client.docs[('batch_pipeline_dev_storm_dampers', 'batch_merge')] = {'armed_until': '51.0'}
    wall.advance(0.5)
    assert window.peek('batch_merge', client=client) == 0.0
    assert window.malformed_reads == 1
    assert window.failed_reads == 0


def test_malformed_string_wall2p0():
    wall = FakeWall(now=50.0)
    window = fresh_window(wall=wall)
    client = StormDocsClient()
    client.docs[('batch_pipeline_dev_storm_dampers', 'batch_merge')] = {'armed_until': '51.0'}
    wall.advance(2.0)
    assert window.peek('batch_merge', client=client) == 0.0
    assert window.malformed_reads == 1
    assert window.failed_reads == 0


def test_malformed_none_wall0p0():
    wall = FakeWall(now=50.0)
    window = fresh_window(wall=wall)
    client = StormDocsClient()
    client.docs[('batch_pipeline_dev_storm_dampers', 'batch_merge')] = {'armed_until': None}
    wall.advance(0.0)
    assert window.peek('batch_merge', client=client) == 0.0
    assert window.malformed_reads == 1
    assert window.failed_reads == 0


def test_malformed_none_wall0p5():
    wall = FakeWall(now=50.0)
    window = fresh_window(wall=wall)
    client = StormDocsClient()
    client.docs[('batch_pipeline_dev_storm_dampers', 'batch_merge')] = {'armed_until': None}
    wall.advance(0.5)
    assert window.peek('batch_merge', client=client) == 0.0
    assert window.malformed_reads == 1
    assert window.failed_reads == 0


def test_malformed_none_wall2p0():
    wall = FakeWall(now=50.0)
    window = fresh_window(wall=wall)
    client = StormDocsClient()
    client.docs[('batch_pipeline_dev_storm_dampers', 'batch_merge')] = {'armed_until': None}
    wall.advance(2.0)
    assert window.peek('batch_merge', client=client) == 0.0
    assert window.malformed_reads == 1
    assert window.failed_reads == 0


def test_malformed_missing_field_wall0p0():
    wall = FakeWall(now=50.0)
    window = fresh_window(wall=wall)
    client = StormDocsClient()
    client.docs[('batch_pipeline_dev_storm_dampers', 'batch_merge')] = {'window_seconds': 1.0}
    wall.advance(0.0)
    assert window.peek('batch_merge', client=client) == 0.0
    assert window.malformed_reads == 1
    assert window.failed_reads == 0


def test_malformed_missing_field_wall0p5():
    wall = FakeWall(now=50.0)
    window = fresh_window(wall=wall)
    client = StormDocsClient()
    client.docs[('batch_pipeline_dev_storm_dampers', 'batch_merge')] = {'window_seconds': 1.0}
    wall.advance(0.5)
    assert window.peek('batch_merge', client=client) == 0.0
    assert window.malformed_reads == 1
    assert window.failed_reads == 0


def test_malformed_missing_field_wall2p0():
    wall = FakeWall(now=50.0)
    window = fresh_window(wall=wall)
    client = StormDocsClient()
    client.docs[('batch_pipeline_dev_storm_dampers', 'batch_merge')] = {'window_seconds': 1.0}
    wall.advance(2.0)
    assert window.peek('batch_merge', client=client) == 0.0
    assert window.malformed_reads == 1
    assert window.failed_reads == 0


def test_malformed_nan_wall0p0():
    wall = FakeWall(now=50.0)
    window = fresh_window(wall=wall)
    client = StormDocsClient()
    client.docs[('batch_pipeline_dev_storm_dampers', 'batch_merge')] = "{'armed_until': float('nan')}"
    wall.advance(0.0)
    assert window.peek('batch_merge', client=client) == 0.0
    assert window.malformed_reads == 1
    assert window.failed_reads == 0


def test_malformed_nan_wall0p5():
    wall = FakeWall(now=50.0)
    window = fresh_window(wall=wall)
    client = StormDocsClient()
    client.docs[('batch_pipeline_dev_storm_dampers', 'batch_merge')] = "{'armed_until': float('nan')}"
    wall.advance(0.5)
    assert window.peek('batch_merge', client=client) == 0.0
    assert window.malformed_reads == 1
    assert window.failed_reads == 0


def test_malformed_nan_wall2p0():
    wall = FakeWall(now=50.0)
    window = fresh_window(wall=wall)
    client = StormDocsClient()
    client.docs[('batch_pipeline_dev_storm_dampers', 'batch_merge')] = "{'armed_until': float('nan')}"
    wall.advance(2.0)
    assert window.peek('batch_merge', client=client) == 0.0
    assert window.malformed_reads == 1
    assert window.failed_reads == 0


def test_malformed_inf_wall0p0():
    wall = FakeWall(now=50.0)
    window = fresh_window(wall=wall)
    client = StormDocsClient()
    client.docs[('batch_pipeline_dev_storm_dampers', 'batch_merge')] = "{'armed_until': float('inf')}"
    wall.advance(0.0)
    assert window.peek('batch_merge', client=client) == 0.0
    assert window.malformed_reads == 1
    assert window.failed_reads == 0


def test_malformed_inf_wall0p5():
    wall = FakeWall(now=50.0)
    window = fresh_window(wall=wall)
    client = StormDocsClient()
    client.docs[('batch_pipeline_dev_storm_dampers', 'batch_merge')] = "{'armed_until': float('inf')}"
    wall.advance(0.5)
    assert window.peek('batch_merge', client=client) == 0.0
    assert window.malformed_reads == 1
    assert window.failed_reads == 0


def test_malformed_inf_wall2p0():
    wall = FakeWall(now=50.0)
    window = fresh_window(wall=wall)
    client = StormDocsClient()
    client.docs[('batch_pipeline_dev_storm_dampers', 'batch_merge')] = "{'armed_until': float('inf')}"
    wall.advance(2.0)
    assert window.peek('batch_merge', client=client) == 0.0
    assert window.malformed_reads == 1
    assert window.failed_reads == 0


def test_malformed_neg_inf_wall0p0():
    wall = FakeWall(now=50.0)
    window = fresh_window(wall=wall)
    client = StormDocsClient()
    client.docs[('batch_pipeline_dev_storm_dampers', 'batch_merge')] = "{'armed_until': float('-inf')}"
    wall.advance(0.0)
    assert window.peek('batch_merge', client=client) == 0.0
    assert window.malformed_reads == 1
    assert window.failed_reads == 0


def test_malformed_neg_inf_wall0p5():
    wall = FakeWall(now=50.0)
    window = fresh_window(wall=wall)
    client = StormDocsClient()
    client.docs[('batch_pipeline_dev_storm_dampers', 'batch_merge')] = "{'armed_until': float('-inf')}"
    wall.advance(0.5)
    assert window.peek('batch_merge', client=client) == 0.0
    assert window.malformed_reads == 1
    assert window.failed_reads == 0


def test_malformed_neg_inf_wall2p0():
    wall = FakeWall(now=50.0)
    window = fresh_window(wall=wall)
    client = StormDocsClient()
    client.docs[('batch_pipeline_dev_storm_dampers', 'batch_merge')] = "{'armed_until': float('-inf')}"
    wall.advance(2.0)
    assert window.peek('batch_merge', client=client) == 0.0
    assert window.malformed_reads == 1
    assert window.failed_reads == 0


def test_malformed_not_a_dict_wall0p0():
    wall = FakeWall(now=50.0)
    window = fresh_window(wall=wall)
    client = StormDocsClient()
    client.docs[('batch_pipeline_dev_storm_dampers', 'batch_merge')] = 'not-a-dict'
    wall.advance(0.0)
    assert window.peek('batch_merge', client=client) == 0.0
    assert window.malformed_reads == 1
    assert window.failed_reads == 0


def test_malformed_not_a_dict_wall0p5():
    wall = FakeWall(now=50.0)
    window = fresh_window(wall=wall)
    client = StormDocsClient()
    client.docs[('batch_pipeline_dev_storm_dampers', 'batch_merge')] = 'not-a-dict'
    wall.advance(0.5)
    assert window.peek('batch_merge', client=client) == 0.0
    assert window.malformed_reads == 1
    assert window.failed_reads == 0


def test_malformed_not_a_dict_wall2p0():
    wall = FakeWall(now=50.0)
    window = fresh_window(wall=wall)
    client = StormDocsClient()
    client.docs[('batch_pipeline_dev_storm_dampers', 'batch_merge')] = 'not-a-dict'
    wall.advance(2.0)
    assert window.peek('batch_merge', client=client) == 0.0
    assert window.malformed_reads == 1
    assert window.failed_reads == 0


# --------------------------------------------------------------------------
# Valid payloads with extra fields and integer deadlines
# --------------------------------------------------------------------------


def test_valid_payload_extra_fields_0():
    wall = FakeWall(now=50.0)
    window = fresh_window(wall=wall)
    client = StormDocsClient()
    client.docs[('batch_pipeline_dev_storm_dampers', 'batch_merge')] = {'armed_until': 51, 'extra': 'field'}
    assert window.peek('batch_merge', client=client) == pytest.approx(1.0)
    assert window.malformed_reads == 0  # finite deadlines are windows, extras are ignored


def test_valid_payload_extra_fields_1():
    wall = FakeWall(now=50.0)
    window = fresh_window(wall=wall)
    client = StormDocsClient()
    client.docs[('batch_pipeline_dev_storm_dampers', 'batch_merge')] = {'armed_until': 51.0, 'window_seconds': 2}
    assert window.peek('batch_merge', client=client) == pytest.approx(1.0)
    assert window.malformed_reads == 0  # finite deadlines are windows, extras are ignored


def test_valid_payload_extra_fields_2():
    wall = FakeWall(now=50.0)
    window = fresh_window(wall=wall)
    client = StormDocsClient()
    client.docs[('batch_pipeline_dev_storm_dampers', 'batch_merge')] = {
        'armed_until': 51,
        'window_seconds': 2,
        'writer': 'pod-7',
    }
    assert window.peek('batch_merge', client=client) == pytest.approx(1.0)
    assert window.malformed_reads == 0  # finite deadlines are windows, extras are ignored


def test_valid_payload_extra_fields_3():
    wall = FakeWall(now=50.0)
    window = fresh_window(wall=wall)
    client = StormDocsClient()
    client.docs[('batch_pipeline_dev_storm_dampers', 'batch_merge')] = {'armed_until': 50.5}
    assert window.peek('batch_merge', client=client) == pytest.approx(0.5)
    assert window.malformed_reads == 0  # finite deadlines are windows, extras are ignored


# --------------------------------------------------------------------------
# Publish skip/overwrite matrix
# --------------------------------------------------------------------------


def test_publish_matrix_mirror0p05_window0p05():
    wall = FakeWall(now=50.0)
    window = fresh_window(wall=wall)
    client = StormDocsClient()
    window.publish('batch_merge', 0.05, client=client)
    window.publish('batch_merge', 0.05, client=client)
    assert len(client.set_calls) == 2  # the lane writes a covered window
    assert window.publishes == 2
    assert window.publish_skips == 0


def test_publish_matrix_mirror0p05_window0p125():
    wall = FakeWall(now=50.0)
    window = fresh_window(wall=wall)
    client = StormDocsClient()
    window.publish('batch_merge', 0.05, client=client)
    window.publish('batch_merge', 0.125, client=client)
    assert len(client.set_calls) == 2  # the lane writes a covered window
    assert window.publishes == 2
    assert window.publish_skips == 0


def test_publish_matrix_mirror0p05_window0p25():
    wall = FakeWall(now=50.0)
    window = fresh_window(wall=wall)
    client = StormDocsClient()
    window.publish('batch_merge', 0.05, client=client)
    window.publish('batch_merge', 0.25, client=client)
    assert len(client.set_calls) == 2  # the lane writes a covered window
    assert window.publishes == 2
    assert window.publish_skips == 0


def test_publish_matrix_mirror0p05_window0p5():
    wall = FakeWall(now=50.0)
    window = fresh_window(wall=wall)
    client = StormDocsClient()
    window.publish('batch_merge', 0.05, client=client)
    window.publish('batch_merge', 0.5, client=client)
    assert len(client.set_calls) == 2  # the lane writes a covered window
    assert window.publishes == 2
    assert window.publish_skips == 0


def test_publish_matrix_mirror0p05_window1p0():
    wall = FakeWall(now=50.0)
    window = fresh_window(wall=wall)
    client = StormDocsClient()
    window.publish('batch_merge', 0.05, client=client)
    window.publish('batch_merge', 1.0, client=client)
    assert len(client.set_calls) == 2  # the lane writes a covered window
    assert window.publishes == 2
    assert window.publish_skips == 0


def test_publish_matrix_mirror0p05_window2p0():
    wall = FakeWall(now=50.0)
    window = fresh_window(wall=wall)
    client = StormDocsClient()
    window.publish('batch_merge', 0.05, client=client)
    window.publish('batch_merge', 2.0, client=client)
    assert len(client.set_calls) == 2  # the lane writes a covered window
    assert window.publishes == 2
    assert window.publish_skips == 0


def test_publish_matrix_mirror0p05_window4p0():
    wall = FakeWall(now=50.0)
    window = fresh_window(wall=wall)
    client = StormDocsClient()
    window.publish('batch_merge', 0.05, client=client)
    window.publish('batch_merge', 4.0, client=client)
    assert len(client.set_calls) == 2  # the lane writes a covered window
    assert window.publishes == 2
    assert window.publish_skips == 0


def test_publish_matrix_mirror0p125_window0p05():
    wall = FakeWall(now=50.0)
    window = fresh_window(wall=wall)
    client = StormDocsClient()
    window.publish('batch_merge', 0.125, client=client)
    window.publish('batch_merge', 0.05, client=client)
    assert len(client.set_calls) == 1  # the lane skips a covered window
    assert window.publishes == 1
    assert window.publish_skips == 1


def test_publish_matrix_mirror0p125_window0p125():
    wall = FakeWall(now=50.0)
    window = fresh_window(wall=wall)
    client = StormDocsClient()
    window.publish('batch_merge', 0.125, client=client)
    window.publish('batch_merge', 0.125, client=client)
    assert len(client.set_calls) == 1  # the lane skips a covered window
    assert window.publishes == 1
    assert window.publish_skips == 1


def test_publish_matrix_mirror0p125_window0p25():
    wall = FakeWall(now=50.0)
    window = fresh_window(wall=wall)
    client = StormDocsClient()
    window.publish('batch_merge', 0.125, client=client)
    window.publish('batch_merge', 0.25, client=client)
    assert len(client.set_calls) == 2  # the lane writes a covered window
    assert window.publishes == 2
    assert window.publish_skips == 0


def test_publish_matrix_mirror0p125_window0p5():
    wall = FakeWall(now=50.0)
    window = fresh_window(wall=wall)
    client = StormDocsClient()
    window.publish('batch_merge', 0.125, client=client)
    window.publish('batch_merge', 0.5, client=client)
    assert len(client.set_calls) == 2  # the lane writes a covered window
    assert window.publishes == 2
    assert window.publish_skips == 0


def test_publish_matrix_mirror0p125_window1p0():
    wall = FakeWall(now=50.0)
    window = fresh_window(wall=wall)
    client = StormDocsClient()
    window.publish('batch_merge', 0.125, client=client)
    window.publish('batch_merge', 1.0, client=client)
    assert len(client.set_calls) == 2  # the lane writes a covered window
    assert window.publishes == 2
    assert window.publish_skips == 0


def test_publish_matrix_mirror0p125_window2p0():
    wall = FakeWall(now=50.0)
    window = fresh_window(wall=wall)
    client = StormDocsClient()
    window.publish('batch_merge', 0.125, client=client)
    window.publish('batch_merge', 2.0, client=client)
    assert len(client.set_calls) == 2  # the lane writes a covered window
    assert window.publishes == 2
    assert window.publish_skips == 0


def test_publish_matrix_mirror0p125_window4p0():
    wall = FakeWall(now=50.0)
    window = fresh_window(wall=wall)
    client = StormDocsClient()
    window.publish('batch_merge', 0.125, client=client)
    window.publish('batch_merge', 4.0, client=client)
    assert len(client.set_calls) == 2  # the lane writes a covered window
    assert window.publishes == 2
    assert window.publish_skips == 0


def test_publish_matrix_mirror0p25_window0p05():
    wall = FakeWall(now=50.0)
    window = fresh_window(wall=wall)
    client = StormDocsClient()
    window.publish('batch_merge', 0.25, client=client)
    window.publish('batch_merge', 0.05, client=client)
    assert len(client.set_calls) == 1  # the lane skips a covered window
    assert window.publishes == 1
    assert window.publish_skips == 1


def test_publish_matrix_mirror0p25_window0p125():
    wall = FakeWall(now=50.0)
    window = fresh_window(wall=wall)
    client = StormDocsClient()
    window.publish('batch_merge', 0.25, client=client)
    window.publish('batch_merge', 0.125, client=client)
    assert len(client.set_calls) == 1  # the lane skips a covered window
    assert window.publishes == 1
    assert window.publish_skips == 1


def test_publish_matrix_mirror0p25_window0p25():
    wall = FakeWall(now=50.0)
    window = fresh_window(wall=wall)
    client = StormDocsClient()
    window.publish('batch_merge', 0.25, client=client)
    window.publish('batch_merge', 0.25, client=client)
    assert len(client.set_calls) == 1  # the lane skips a covered window
    assert window.publishes == 1
    assert window.publish_skips == 1


def test_publish_matrix_mirror0p25_window0p5():
    wall = FakeWall(now=50.0)
    window = fresh_window(wall=wall)
    client = StormDocsClient()
    window.publish('batch_merge', 0.25, client=client)
    window.publish('batch_merge', 0.5, client=client)
    assert len(client.set_calls) == 2  # the lane writes a covered window
    assert window.publishes == 2
    assert window.publish_skips == 0


def test_publish_matrix_mirror0p25_window1p0():
    wall = FakeWall(now=50.0)
    window = fresh_window(wall=wall)
    client = StormDocsClient()
    window.publish('batch_merge', 0.25, client=client)
    window.publish('batch_merge', 1.0, client=client)
    assert len(client.set_calls) == 2  # the lane writes a covered window
    assert window.publishes == 2
    assert window.publish_skips == 0


def test_publish_matrix_mirror0p25_window2p0():
    wall = FakeWall(now=50.0)
    window = fresh_window(wall=wall)
    client = StormDocsClient()
    window.publish('batch_merge', 0.25, client=client)
    window.publish('batch_merge', 2.0, client=client)
    assert len(client.set_calls) == 2  # the lane writes a covered window
    assert window.publishes == 2
    assert window.publish_skips == 0


def test_publish_matrix_mirror0p25_window4p0():
    wall = FakeWall(now=50.0)
    window = fresh_window(wall=wall)
    client = StormDocsClient()
    window.publish('batch_merge', 0.25, client=client)
    window.publish('batch_merge', 4.0, client=client)
    assert len(client.set_calls) == 2  # the lane writes a covered window
    assert window.publishes == 2
    assert window.publish_skips == 0


def test_publish_matrix_mirror0p5_window0p05():
    wall = FakeWall(now=50.0)
    window = fresh_window(wall=wall)
    client = StormDocsClient()
    window.publish('batch_merge', 0.5, client=client)
    window.publish('batch_merge', 0.05, client=client)
    assert len(client.set_calls) == 1  # the lane skips a covered window
    assert window.publishes == 1
    assert window.publish_skips == 1


def test_publish_matrix_mirror0p5_window0p125():
    wall = FakeWall(now=50.0)
    window = fresh_window(wall=wall)
    client = StormDocsClient()
    window.publish('batch_merge', 0.5, client=client)
    window.publish('batch_merge', 0.125, client=client)
    assert len(client.set_calls) == 1  # the lane skips a covered window
    assert window.publishes == 1
    assert window.publish_skips == 1


def test_publish_matrix_mirror0p5_window0p25():
    wall = FakeWall(now=50.0)
    window = fresh_window(wall=wall)
    client = StormDocsClient()
    window.publish('batch_merge', 0.5, client=client)
    window.publish('batch_merge', 0.25, client=client)
    assert len(client.set_calls) == 1  # the lane skips a covered window
    assert window.publishes == 1
    assert window.publish_skips == 1


def test_publish_matrix_mirror0p5_window0p5():
    wall = FakeWall(now=50.0)
    window = fresh_window(wall=wall)
    client = StormDocsClient()
    window.publish('batch_merge', 0.5, client=client)
    window.publish('batch_merge', 0.5, client=client)
    assert len(client.set_calls) == 1  # the lane skips a covered window
    assert window.publishes == 1
    assert window.publish_skips == 1


def test_publish_matrix_mirror0p5_window1p0():
    wall = FakeWall(now=50.0)
    window = fresh_window(wall=wall)
    client = StormDocsClient()
    window.publish('batch_merge', 0.5, client=client)
    window.publish('batch_merge', 1.0, client=client)
    assert len(client.set_calls) == 2  # the lane writes a covered window
    assert window.publishes == 2
    assert window.publish_skips == 0


def test_publish_matrix_mirror0p5_window2p0():
    wall = FakeWall(now=50.0)
    window = fresh_window(wall=wall)
    client = StormDocsClient()
    window.publish('batch_merge', 0.5, client=client)
    window.publish('batch_merge', 2.0, client=client)
    assert len(client.set_calls) == 2  # the lane writes a covered window
    assert window.publishes == 2
    assert window.publish_skips == 0


def test_publish_matrix_mirror0p5_window4p0():
    wall = FakeWall(now=50.0)
    window = fresh_window(wall=wall)
    client = StormDocsClient()
    window.publish('batch_merge', 0.5, client=client)
    window.publish('batch_merge', 4.0, client=client)
    assert len(client.set_calls) == 2  # the lane writes a covered window
    assert window.publishes == 2
    assert window.publish_skips == 0


def test_publish_matrix_mirror1p0_window0p05():
    wall = FakeWall(now=50.0)
    window = fresh_window(wall=wall)
    client = StormDocsClient()
    window.publish('batch_merge', 1.0, client=client)
    window.publish('batch_merge', 0.05, client=client)
    assert len(client.set_calls) == 1  # the lane skips a covered window
    assert window.publishes == 1
    assert window.publish_skips == 1


def test_publish_matrix_mirror1p0_window0p125():
    wall = FakeWall(now=50.0)
    window = fresh_window(wall=wall)
    client = StormDocsClient()
    window.publish('batch_merge', 1.0, client=client)
    window.publish('batch_merge', 0.125, client=client)
    assert len(client.set_calls) == 1  # the lane skips a covered window
    assert window.publishes == 1
    assert window.publish_skips == 1


def test_publish_matrix_mirror1p0_window0p25():
    wall = FakeWall(now=50.0)
    window = fresh_window(wall=wall)
    client = StormDocsClient()
    window.publish('batch_merge', 1.0, client=client)
    window.publish('batch_merge', 0.25, client=client)
    assert len(client.set_calls) == 1  # the lane skips a covered window
    assert window.publishes == 1
    assert window.publish_skips == 1


def test_publish_matrix_mirror1p0_window0p5():
    wall = FakeWall(now=50.0)
    window = fresh_window(wall=wall)
    client = StormDocsClient()
    window.publish('batch_merge', 1.0, client=client)
    window.publish('batch_merge', 0.5, client=client)
    assert len(client.set_calls) == 1  # the lane skips a covered window
    assert window.publishes == 1
    assert window.publish_skips == 1


def test_publish_matrix_mirror1p0_window1p0():
    wall = FakeWall(now=50.0)
    window = fresh_window(wall=wall)
    client = StormDocsClient()
    window.publish('batch_merge', 1.0, client=client)
    window.publish('batch_merge', 1.0, client=client)
    assert len(client.set_calls) == 1  # the lane skips a covered window
    assert window.publishes == 1
    assert window.publish_skips == 1


def test_publish_matrix_mirror1p0_window2p0():
    wall = FakeWall(now=50.0)
    window = fresh_window(wall=wall)
    client = StormDocsClient()
    window.publish('batch_merge', 1.0, client=client)
    window.publish('batch_merge', 2.0, client=client)
    assert len(client.set_calls) == 2  # the lane writes a covered window
    assert window.publishes == 2
    assert window.publish_skips == 0


def test_publish_matrix_mirror1p0_window4p0():
    wall = FakeWall(now=50.0)
    window = fresh_window(wall=wall)
    client = StormDocsClient()
    window.publish('batch_merge', 1.0, client=client)
    window.publish('batch_merge', 4.0, client=client)
    assert len(client.set_calls) == 2  # the lane writes a covered window
    assert window.publishes == 2
    assert window.publish_skips == 0


def test_publish_matrix_mirror2p0_window0p05():
    wall = FakeWall(now=50.0)
    window = fresh_window(wall=wall)
    client = StormDocsClient()
    window.publish('batch_merge', 2.0, client=client)
    window.publish('batch_merge', 0.05, client=client)
    assert len(client.set_calls) == 1  # the lane skips a covered window
    assert window.publishes == 1
    assert window.publish_skips == 1


def test_publish_matrix_mirror2p0_window0p125():
    wall = FakeWall(now=50.0)
    window = fresh_window(wall=wall)
    client = StormDocsClient()
    window.publish('batch_merge', 2.0, client=client)
    window.publish('batch_merge', 0.125, client=client)
    assert len(client.set_calls) == 1  # the lane skips a covered window
    assert window.publishes == 1
    assert window.publish_skips == 1


def test_publish_matrix_mirror2p0_window0p25():
    wall = FakeWall(now=50.0)
    window = fresh_window(wall=wall)
    client = StormDocsClient()
    window.publish('batch_merge', 2.0, client=client)
    window.publish('batch_merge', 0.25, client=client)
    assert len(client.set_calls) == 1  # the lane skips a covered window
    assert window.publishes == 1
    assert window.publish_skips == 1


def test_publish_matrix_mirror2p0_window0p5():
    wall = FakeWall(now=50.0)
    window = fresh_window(wall=wall)
    client = StormDocsClient()
    window.publish('batch_merge', 2.0, client=client)
    window.publish('batch_merge', 0.5, client=client)
    assert len(client.set_calls) == 1  # the lane skips a covered window
    assert window.publishes == 1
    assert window.publish_skips == 1


def test_publish_matrix_mirror2p0_window1p0():
    wall = FakeWall(now=50.0)
    window = fresh_window(wall=wall)
    client = StormDocsClient()
    window.publish('batch_merge', 2.0, client=client)
    window.publish('batch_merge', 1.0, client=client)
    assert len(client.set_calls) == 1  # the lane skips a covered window
    assert window.publishes == 1
    assert window.publish_skips == 1


def test_publish_matrix_mirror2p0_window2p0():
    wall = FakeWall(now=50.0)
    window = fresh_window(wall=wall)
    client = StormDocsClient()
    window.publish('batch_merge', 2.0, client=client)
    window.publish('batch_merge', 2.0, client=client)
    assert len(client.set_calls) == 1  # the lane skips a covered window
    assert window.publishes == 1
    assert window.publish_skips == 1


def test_publish_matrix_mirror2p0_window4p0():
    wall = FakeWall(now=50.0)
    window = fresh_window(wall=wall)
    client = StormDocsClient()
    window.publish('batch_merge', 2.0, client=client)
    window.publish('batch_merge', 4.0, client=client)
    assert len(client.set_calls) == 2  # the lane writes a covered window
    assert window.publishes == 2
    assert window.publish_skips == 0


def test_publish_matrix_mirror4p0_window0p05():
    wall = FakeWall(now=50.0)
    window = fresh_window(wall=wall)
    client = StormDocsClient()
    window.publish('batch_merge', 4.0, client=client)
    window.publish('batch_merge', 0.05, client=client)
    assert len(client.set_calls) == 1  # the lane skips a covered window
    assert window.publishes == 1
    assert window.publish_skips == 1


def test_publish_matrix_mirror4p0_window0p125():
    wall = FakeWall(now=50.0)
    window = fresh_window(wall=wall)
    client = StormDocsClient()
    window.publish('batch_merge', 4.0, client=client)
    window.publish('batch_merge', 0.125, client=client)
    assert len(client.set_calls) == 1  # the lane skips a covered window
    assert window.publishes == 1
    assert window.publish_skips == 1


def test_publish_matrix_mirror4p0_window0p25():
    wall = FakeWall(now=50.0)
    window = fresh_window(wall=wall)
    client = StormDocsClient()
    window.publish('batch_merge', 4.0, client=client)
    window.publish('batch_merge', 0.25, client=client)
    assert len(client.set_calls) == 1  # the lane skips a covered window
    assert window.publishes == 1
    assert window.publish_skips == 1


def test_publish_matrix_mirror4p0_window0p5():
    wall = FakeWall(now=50.0)
    window = fresh_window(wall=wall)
    client = StormDocsClient()
    window.publish('batch_merge', 4.0, client=client)
    window.publish('batch_merge', 0.5, client=client)
    assert len(client.set_calls) == 1  # the lane skips a covered window
    assert window.publishes == 1
    assert window.publish_skips == 1


def test_publish_matrix_mirror4p0_window1p0():
    wall = FakeWall(now=50.0)
    window = fresh_window(wall=wall)
    client = StormDocsClient()
    window.publish('batch_merge', 4.0, client=client)
    window.publish('batch_merge', 1.0, client=client)
    assert len(client.set_calls) == 1  # the lane skips a covered window
    assert window.publishes == 1
    assert window.publish_skips == 1


def test_publish_matrix_mirror4p0_window2p0():
    wall = FakeWall(now=50.0)
    window = fresh_window(wall=wall)
    client = StormDocsClient()
    window.publish('batch_merge', 4.0, client=client)
    window.publish('batch_merge', 2.0, client=client)
    assert len(client.set_calls) == 1  # the lane skips a covered window
    assert window.publishes == 1
    assert window.publish_skips == 1


def test_publish_matrix_mirror4p0_window4p0():
    wall = FakeWall(now=50.0)
    window = fresh_window(wall=wall)
    client = StormDocsClient()
    window.publish('batch_merge', 4.0, client=client)
    window.publish('batch_merge', 4.0, client=client)
    assert len(client.set_calls) == 1  # the lane skips a covered window
    assert window.publishes == 1
    assert window.publish_skips == 1


# --------------------------------------------------------------------------
# Publish skip never outlives the wall
# --------------------------------------------------------------------------


def test_publish_after_mirror_expiry_mirror0p5_advance0p5():
    wall = FakeWall(now=50.0)
    window = fresh_window(wall=wall)
    client = StormDocsClient()
    window.publish('batch_merge', 0.5, client=client)
    wall.advance(0.5)
    window.publish('batch_merge', 0.5, client=client)
    assert len(client.set_calls) == 2  # the covered-window skip never outlives the wall


def test_publish_after_mirror_expiry_mirror0p5_advance2p0():
    wall = FakeWall(now=50.0)
    window = fresh_window(wall=wall)
    client = StormDocsClient()
    window.publish('batch_merge', 0.5, client=client)
    wall.advance(2.0)
    window.publish('batch_merge', 0.5, client=client)
    assert len(client.set_calls) == 2  # the covered-window skip never outlives the wall


def test_publish_after_mirror_expiry_mirror0p5_advance5p0():
    wall = FakeWall(now=50.0)
    window = fresh_window(wall=wall)
    client = StormDocsClient()
    window.publish('batch_merge', 0.5, client=client)
    wall.advance(5.0)
    window.publish('batch_merge', 0.5, client=client)
    assert len(client.set_calls) == 2  # the covered-window skip never outlives the wall


def test_publish_after_mirror_expiry_mirror1p0_advance0p5():
    wall = FakeWall(now=50.0)
    window = fresh_window(wall=wall)
    client = StormDocsClient()
    window.publish('batch_merge', 1.0, client=client)
    wall.advance(0.5)
    window.publish('batch_merge', 1.0, client=client)
    assert len(client.set_calls) == 2  # the covered-window skip never outlives the wall


def test_publish_after_mirror_expiry_mirror1p0_advance2p0():
    wall = FakeWall(now=50.0)
    window = fresh_window(wall=wall)
    client = StormDocsClient()
    window.publish('batch_merge', 1.0, client=client)
    wall.advance(2.0)
    window.publish('batch_merge', 1.0, client=client)
    assert len(client.set_calls) == 2  # the covered-window skip never outlives the wall


def test_publish_after_mirror_expiry_mirror1p0_advance5p0():
    wall = FakeWall(now=50.0)
    window = fresh_window(wall=wall)
    client = StormDocsClient()
    window.publish('batch_merge', 1.0, client=client)
    wall.advance(5.0)
    window.publish('batch_merge', 1.0, client=client)
    assert len(client.set_calls) == 2  # the covered-window skip never outlives the wall


def test_publish_after_mirror_expiry_mirror2p0_advance0p5():
    wall = FakeWall(now=50.0)
    window = fresh_window(wall=wall)
    client = StormDocsClient()
    window.publish('batch_merge', 2.0, client=client)
    wall.advance(0.5)
    window.publish('batch_merge', 2.0, client=client)
    assert len(client.set_calls) == 2  # the covered-window skip never outlives the wall


def test_publish_after_mirror_expiry_mirror2p0_advance2p0():
    wall = FakeWall(now=50.0)
    window = fresh_window(wall=wall)
    client = StormDocsClient()
    window.publish('batch_merge', 2.0, client=client)
    wall.advance(2.0)
    window.publish('batch_merge', 2.0, client=client)
    assert len(client.set_calls) == 2  # the covered-window skip never outlives the wall


def test_publish_after_mirror_expiry_mirror2p0_advance5p0():
    wall = FakeWall(now=50.0)
    window = fresh_window(wall=wall)
    client = StormDocsClient()
    window.publish('batch_merge', 2.0, client=client)
    wall.advance(5.0)
    window.publish('batch_merge', 2.0, client=client)
    assert len(client.set_calls) == 2  # the covered-window skip never outlives the wall


def test_publish_after_mirror_expiry_mirror4p0_advance0p5():
    wall = FakeWall(now=50.0)
    window = fresh_window(wall=wall)
    client = StormDocsClient()
    window.publish('batch_merge', 4.0, client=client)
    wall.advance(0.5)
    window.publish('batch_merge', 4.0, client=client)
    assert len(client.set_calls) == 2  # the covered-window skip never outlives the wall


def test_publish_after_mirror_expiry_mirror4p0_advance2p0():
    wall = FakeWall(now=50.0)
    window = fresh_window(wall=wall)
    client = StormDocsClient()
    window.publish('batch_merge', 4.0, client=client)
    wall.advance(2.0)
    window.publish('batch_merge', 4.0, client=client)
    assert len(client.set_calls) == 2  # the covered-window skip never outlives the wall


def test_publish_after_mirror_expiry_mirror4p0_advance5p0():
    wall = FakeWall(now=50.0)
    window = fresh_window(wall=wall)
    client = StormDocsClient()
    window.publish('batch_merge', 4.0, client=client)
    wall.advance(5.0)
    window.publish('batch_merge', 4.0, client=client)
    assert len(client.set_calls) == 2  # the covered-window skip never outlives the wall


# --------------------------------------------------------------------------
# Fault matrix (read and write faults per label)
# --------------------------------------------------------------------------


def test_read_faults_fail_open_n1_batch_merge():
    wall = FakeWall(now=50.0)
    window = fresh_window(wall=wall)
    client = StormDocsClient()
    client.fail_gets = 1
    assert window.peek('batch_merge', client=client) == 0.0
    assert window.failed_reads == 1
    wall.advance(0.5)
    assert window.peek('batch_merge', client=client) == 0.0  # cached as no window
    assert len(client.get_calls) == 1


def test_write_faults_fail_open_n1_batch_merge():
    wall = FakeWall(now=50.0)
    window = fresh_window(wall=wall)
    client = StormDocsClient()
    client.fail_sets = 1
    window.publish('batch_merge', 1.0, client=client)  # must not raise
    assert window.publish_failures == 1
    assert window.publishes == 0
    assert len(client.set_calls) == 1  # the attempt was recorded before the fault


def test_read_faults_fail_open_n1_batch_recover():
    wall = FakeWall(now=50.0)
    window = fresh_window(wall=wall)
    client = StormDocsClient()
    client.fail_gets = 1
    assert window.peek('batch_recover', client=client) == 0.0
    assert window.failed_reads == 1
    wall.advance(0.5)
    assert window.peek('batch_recover', client=client) == 0.0  # cached as no window
    assert len(client.get_calls) == 1


def test_write_faults_fail_open_n1_batch_recover():
    wall = FakeWall(now=50.0)
    window = fresh_window(wall=wall)
    client = StormDocsClient()
    client.fail_sets = 1
    window.publish('batch_recover', 1.0, client=client)  # must not raise
    assert window.publish_failures == 1
    assert window.publishes == 0
    assert len(client.set_calls) == 1  # the attempt was recorded before the fault


def test_read_faults_fail_open_n1_batch_pull_shard_scheduler_05():
    wall = FakeWall(now=50.0)
    window = fresh_window(wall=wall)
    client = StormDocsClient()
    client.fail_gets = 1
    assert window.peek('batch_pull shard=scheduler_05', client=client) == 0.0
    assert window.failed_reads == 1
    wall.advance(0.5)
    assert window.peek('batch_pull shard=scheduler_05', client=client) == 0.0  # cached as no window
    assert len(client.get_calls) == 1


def test_write_faults_fail_open_n1_batch_pull_shard_scheduler_05():
    wall = FakeWall(now=50.0)
    window = fresh_window(wall=wall)
    client = StormDocsClient()
    client.fail_sets = 1
    window.publish('batch_pull shard=scheduler_05', 1.0, client=client)  # must not raise
    assert window.publish_failures == 1
    assert window.publishes == 0
    assert len(client.set_calls) == 1  # the attempt was recorded before the fault


def test_read_faults_fail_open_n2_batch_merge():
    wall = FakeWall(now=50.0)
    window = fresh_window(wall=wall)
    client = StormDocsClient()
    client.fail_gets = 2
    assert window.peek('batch_merge', client=client) == 0.0
    assert window.failed_reads == 1
    wall.advance(0.5)
    assert window.peek('batch_merge', client=client) == 0.0  # cached as no window
    assert len(client.get_calls) == 1


def test_write_faults_fail_open_n2_batch_merge():
    wall = FakeWall(now=50.0)
    window = fresh_window(wall=wall)
    client = StormDocsClient()
    client.fail_sets = 2
    window.publish('batch_merge', 1.0, client=client)  # must not raise
    assert window.publish_failures == 1
    assert window.publishes == 0
    assert len(client.set_calls) == 1  # the attempt was recorded before the fault


def test_read_faults_fail_open_n2_batch_recover():
    wall = FakeWall(now=50.0)
    window = fresh_window(wall=wall)
    client = StormDocsClient()
    client.fail_gets = 2
    assert window.peek('batch_recover', client=client) == 0.0
    assert window.failed_reads == 1
    wall.advance(0.5)
    assert window.peek('batch_recover', client=client) == 0.0  # cached as no window
    assert len(client.get_calls) == 1


def test_write_faults_fail_open_n2_batch_recover():
    wall = FakeWall(now=50.0)
    window = fresh_window(wall=wall)
    client = StormDocsClient()
    client.fail_sets = 2
    window.publish('batch_recover', 1.0, client=client)  # must not raise
    assert window.publish_failures == 1
    assert window.publishes == 0
    assert len(client.set_calls) == 1  # the attempt was recorded before the fault


def test_read_faults_fail_open_n2_batch_pull_shard_scheduler_05():
    wall = FakeWall(now=50.0)
    window = fresh_window(wall=wall)
    client = StormDocsClient()
    client.fail_gets = 2
    assert window.peek('batch_pull shard=scheduler_05', client=client) == 0.0
    assert window.failed_reads == 1
    wall.advance(0.5)
    assert window.peek('batch_pull shard=scheduler_05', client=client) == 0.0  # cached as no window
    assert len(client.get_calls) == 1


def test_write_faults_fail_open_n2_batch_pull_shard_scheduler_05():
    wall = FakeWall(now=50.0)
    window = fresh_window(wall=wall)
    client = StormDocsClient()
    client.fail_sets = 2
    window.publish('batch_pull shard=scheduler_05', 1.0, client=client)  # must not raise
    assert window.publish_failures == 1
    assert window.publishes == 0
    assert len(client.set_calls) == 1  # the attempt was recorded before the fault


# --------------------------------------------------------------------------
# Label grammar: fit and unfit corpora
# --------------------------------------------------------------------------


def test_label_grammar_fit_batch_merge():
    assert storage.fleet_storm_window_doc_id('batch_merge') == 'batch_merge'
    wall = FakeWall(now=50.0)
    window = fresh_window(wall=wall)
    client = StormDocsClient()
    window.publish('batch_merge', 0.5, client=client)
    assert client.set_calls[0][1] == 'batch_merge'
    assert window.peek('batch_merge', client=client) == pytest.approx(0.5)
    assert len(client.get_calls) == 1  # the publish's floor read warmed the mirror


def test_label_grammar_fit_batch_defer():
    assert storage.fleet_storm_window_doc_id('batch_defer') == 'batch_defer'
    wall = FakeWall(now=50.0)
    window = fresh_window(wall=wall)
    client = StormDocsClient()
    window.publish('batch_defer', 0.5, client=client)
    assert client.set_calls[0][1] == 'batch_defer'
    assert window.peek('batch_defer', client=client) == pytest.approx(0.5)
    assert len(client.get_calls) == 1  # the publish's floor read warmed the mirror


def test_label_grammar_fit_batch_recover():
    assert storage.fleet_storm_window_doc_id('batch_recover') == 'batch_recover'
    wall = FakeWall(now=50.0)
    window = fresh_window(wall=wall)
    client = StormDocsClient()
    window.publish('batch_recover', 0.5, client=client)
    assert client.set_calls[0][1] == 'batch_recover'
    assert window.peek('batch_recover', client=client) == pytest.approx(0.5)
    assert len(client.get_calls) == 1  # the publish's floor read warmed the mirror


def test_label_grammar_fit_batch_release():
    assert storage.fleet_storm_window_doc_id('batch_release') == 'batch_release'
    wall = FakeWall(now=50.0)
    window = fresh_window(wall=wall)
    client = StormDocsClient()
    window.publish('batch_release', 0.5, client=client)
    assert client.set_calls[0][1] == 'batch_release'
    assert window.peek('batch_release', client=client) == pytest.approx(0.5)
    assert len(client.get_calls) == 1  # the publish's floor read warmed the mirror


def test_label_grammar_fit_batch_offer():
    assert storage.fleet_storm_window_doc_id('batch_offer') == 'batch_offer'
    wall = FakeWall(now=50.0)
    window = fresh_window(wall=wall)
    client = StormDocsClient()
    window.publish('batch_offer', 0.5, client=client)
    assert client.set_calls[0][1] == 'batch_offer'
    assert window.peek('batch_offer', client=client) == pytest.approx(0.5)
    assert len(client.get_calls) == 1  # the publish's floor read warmed the mirror


def test_label_grammar_fit_batch_finish():
    assert storage.fleet_storm_window_doc_id('batch_finish') == 'batch_finish'
    wall = FakeWall(now=50.0)
    window = fresh_window(wall=wall)
    client = StormDocsClient()
    window.publish('batch_finish', 0.5, client=client)
    assert client.set_calls[0][1] == 'batch_finish'
    assert window.peek('batch_finish', client=client) == pytest.approx(0.5)
    assert len(client.get_calls) == 1  # the publish's floor read warmed the mirror


def test_label_grammar_fit_batch_reserve():
    assert storage.fleet_storm_window_doc_id('batch_reserve') == 'batch_reserve'
    wall = FakeWall(now=50.0)
    window = fresh_window(wall=wall)
    client = StormDocsClient()
    window.publish('batch_reserve', 0.5, client=client)
    assert client.set_calls[0][1] == 'batch_reserve'
    assert window.peek('batch_reserve', client=client) == pytest.approx(0.5)
    assert len(client.get_calls) == 1  # the publish's floor read warmed the mirror


def test_label_grammar_fit_batch_ready():
    assert storage.fleet_storm_window_doc_id('batch_ready') == 'batch_ready'
    wall = FakeWall(now=50.0)
    window = fresh_window(wall=wall)
    client = StormDocsClient()
    window.publish('batch_ready', 0.5, client=client)
    assert client.set_calls[0][1] == 'batch_ready'
    assert window.peek('batch_ready', client=client) == pytest.approx(0.5)
    assert len(client.get_calls) == 1  # the publish's floor read warmed the mirror


def test_label_grammar_fit_batch_take():
    assert storage.fleet_storm_window_doc_id('batch_take') == 'batch_take'
    wall = FakeWall(now=50.0)
    window = fresh_window(wall=wall)
    client = StormDocsClient()
    window.publish('batch_take', 0.5, client=client)
    assert client.set_calls[0][1] == 'batch_take'
    assert window.peek('batch_take', client=client) == pytest.approx(0.5)
    assert len(client.get_calls) == 1  # the publish's floor read warmed the mirror


def test_label_grammar_fit_batch_paid():
    assert storage.fleet_storm_window_doc_id('batch_paid') == 'batch_paid'
    wall = FakeWall(now=50.0)
    window = fresh_window(wall=wall)
    client = StormDocsClient()
    window.publish('batch_paid', 0.5, client=client)
    assert client.set_calls[0][1] == 'batch_paid'
    assert window.peek('batch_paid', client=client) == pytest.approx(0.5)
    assert len(client.get_calls) == 1  # the publish's floor read warmed the mirror


def test_label_grammar_fit_batch_handoff():
    assert storage.fleet_storm_window_doc_id('batch_handoff') == 'batch_handoff'
    wall = FakeWall(now=50.0)
    window = fresh_window(wall=wall)
    client = StormDocsClient()
    window.publish('batch_handoff', 0.5, client=client)
    assert client.set_calls[0][1] == 'batch_handoff'
    assert window.peek('batch_handoff', client=client) == pytest.approx(0.5)
    assert len(client.get_calls) == 1  # the publish's floor read warmed the mirror


def test_label_grammar_fit_batch_reap():
    assert storage.fleet_storm_window_doc_id('batch_reap') == 'batch_reap'
    wall = FakeWall(now=50.0)
    window = fresh_window(wall=wall)
    client = StormDocsClient()
    window.publish('batch_reap', 0.5, client=client)
    assert client.set_calls[0][1] == 'batch_reap'
    assert window.peek('batch_reap', client=client) == pytest.approx(0.5)
    assert len(client.get_calls) == 1  # the publish's floor read warmed the mirror


def test_label_grammar_fit_batch_start_recovery():
    assert storage.fleet_storm_window_doc_id('batch_start_recovery') == 'batch_start_recovery'
    wall = FakeWall(now=50.0)
    window = fresh_window(wall=wall)
    client = StormDocsClient()
    window.publish('batch_start_recovery', 0.5, client=client)
    assert client.set_calls[0][1] == 'batch_start_recovery'
    assert window.peek('batch_start_recovery', client=client) == pytest.approx(0.5)
    assert len(client.get_calls) == 1  # the publish's floor read warmed the mirror


def test_label_grammar_fit_batch_recovery_transport_failed():
    assert storage.fleet_storm_window_doc_id('batch_recovery_transport_failed') == 'batch_recovery_transport_failed'
    wall = FakeWall(now=50.0)
    window = fresh_window(wall=wall)
    client = StormDocsClient()
    window.publish('batch_recovery_transport_failed', 0.5, client=client)
    assert client.set_calls[0][1] == 'batch_recovery_transport_failed'
    assert window.peek('batch_recovery_transport_failed', client=client) == pytest.approx(0.5)
    assert len(client.get_calls) == 1  # the publish's floor read warmed the mirror


def test_label_grammar_fit_batch_projection_input():
    assert storage.fleet_storm_window_doc_id('batch_projection_input') == 'batch_projection_input'
    wall = FakeWall(now=50.0)
    window = fresh_window(wall=wall)
    client = StormDocsClient()
    window.publish('batch_projection_input', 0.5, client=client)
    assert client.set_calls[0][1] == 'batch_projection_input'
    assert window.peek('batch_projection_input', client=client) == pytest.approx(0.5)
    assert len(client.get_calls) == 1  # the publish's floor read warmed the mirror


def test_label_grammar_fit_a():
    assert storage.fleet_storm_window_doc_id('a') == 'a'
    wall = FakeWall(now=50.0)
    window = fresh_window(wall=wall)
    client = StormDocsClient()
    window.publish('a', 0.5, client=client)
    assert client.set_calls[0][1] == 'a'
    assert window.peek('a', client=client) == pytest.approx(0.5)
    assert len(client.get_calls) == 1  # the publish's floor read warmed the mirror


def test_label_grammar_fit_z9_():
    assert storage.fleet_storm_window_doc_id('z9_') == 'z9_'
    wall = FakeWall(now=50.0)
    window = fresh_window(wall=wall)
    client = StormDocsClient()
    window.publish('z9_', 0.5, client=client)
    assert client.set_calls[0][1] == 'z9_'
    assert window.peek('z9_', client=client) == pytest.approx(0.5)
    assert len(client.get_calls) == 1  # the publish's floor read warmed the mirror


def test_label_grammar_fit_batch_store_backoff_probe():
    assert storage.fleet_storm_window_doc_id('batch_store_backoff_probe') == 'batch_store_backoff_probe'
    wall = FakeWall(now=50.0)
    window = fresh_window(wall=wall)
    client = StormDocsClient()
    window.publish('batch_store_backoff_probe', 0.5, client=client)
    assert client.set_calls[0][1] == 'batch_store_backoff_probe'
    assert window.peek('batch_store_backoff_probe', client=client) == pytest.approx(0.5)
    assert len(client.get_calls) == 1  # the publish's floor read warmed the mirror


def test_label_grammar_fit_shadow_offer_stage():
    assert storage.fleet_storm_window_doc_id('shadow_offer_stage') == 'shadow_offer_stage'
    wall = FakeWall(now=50.0)
    window = fresh_window(wall=wall)
    client = StormDocsClient()
    window.publish('shadow_offer_stage', 0.5, client=client)
    assert client.set_calls[0][1] == 'shadow_offer_stage'
    assert window.peek('shadow_offer_stage', client=client) == pytest.approx(0.5)
    assert len(client.get_calls) == 1  # the publish's floor read warmed the mirror


def test_label_grammar_fit_record_seal_claim():
    assert storage.fleet_storm_window_doc_id('record_seal_claim') == 'record_seal_claim'
    wall = FakeWall(now=50.0)
    window = fresh_window(wall=wall)
    client = StormDocsClient()
    window.publish('record_seal_claim', 0.5, client=client)
    assert client.set_calls[0][1] == 'record_seal_claim'
    assert window.peek('record_seal_claim', client=client) == pytest.approx(0.5)
    assert len(client.get_calls) == 1  # the publish's floor read warmed the mirror


def test_label_grammar_unfit_00():
    assert storage.fleet_storm_window_doc_id('Bad Label') is None
    window = fresh_window()
    client = StormDocsClient()
    assert window.peek('Bad Label', client=client) == 0.0
    window.publish('Bad Label', 1.0, client=client)
    assert client.get_calls == [] and client.set_calls == []


def test_label_grammar_unfit_01():
    assert storage.fleet_storm_window_doc_id('UPPER') is None
    window = fresh_window()
    client = StormDocsClient()
    assert window.peek('UPPER', client=client) == 0.0
    window.publish('UPPER', 1.0, client=client)
    assert client.get_calls == [] and client.set_calls == []


def test_label_grammar_unfit_02():
    assert storage.fleet_storm_window_doc_id('leading-dash') is None
    window = fresh_window()
    client = StormDocsClient()
    assert window.peek('leading-dash', client=client) == 0.0
    window.publish('leading-dash', 1.0, client=client)
    assert client.get_calls == [] and client.set_calls == []


def test_label_grammar_unfit_03():
    assert storage.fleet_storm_window_doc_id('dot.dot') is None
    window = fresh_window()
    client = StormDocsClient()
    assert window.peek('dot.dot', client=client) == 0.0
    window.publish('dot.dot', 1.0, client=client)
    assert client.get_calls == [] and client.set_calls == []


def test_label_grammar_unfit_04():
    assert storage.fleet_storm_window_doc_id('slash/slash') is None
    window = fresh_window()
    client = StormDocsClient()
    assert window.peek('slash/slash', client=client) == 0.0
    window.publish('slash/slash', 1.0, client=client)
    assert client.get_calls == [] and client.set_calls == []


def test_label_grammar_unfit_05():
    assert storage.fleet_storm_window_doc_id('') is None
    window = fresh_window()
    client = StormDocsClient()
    assert window.peek('', client=client) == 0.0
    window.publish('', 1.0, client=client)
    assert client.get_calls == [] and client.set_calls == []


def test_label_grammar_unfit_06():
    assert storage.fleet_storm_window_doc_id('tab\tinside') is None
    window = fresh_window()
    client = StormDocsClient()
    assert window.peek('tab\tinside', client=client) == 0.0
    window.publish('tab\tinside', 1.0, client=client)
    assert client.get_calls == [] and client.set_calls == []


def test_label_grammar_unfit_07():
    assert storage.fleet_storm_window_doc_id('new\nline') is None
    window = fresh_window()
    client = StormDocsClient()
    assert window.peek('new\nline', client=client) == 0.0
    window.publish('new\nline', 1.0, client=client)
    assert client.get_calls == [] and client.set_calls == []


def test_label_grammar_sanitized_fit_00():
    assert storage.fleet_storm_window_doc_id('space inside') == 'space_inside'  # the deterministic mapping


def test_label_grammar_sanitized_fit_01():
    assert storage.fleet_storm_window_doc_id('1starts_digit') == '1starts_digit'  # the deterministic mapping


def test_label_grammar_sanitized_fit_02():
    assert storage.fleet_storm_window_doc_id('has=equals') == 'has_equals'  # the deterministic mapping


def test_label_grammar_sanitized_fit_03():
    assert (
        storage.fleet_storm_window_doc_id('has spaces and=equals') == 'has_spaces_and_equals'
    )  # the deterministic mapping


def test_label_grammar_sanitized_fit_04():
    assert (
        storage.fleet_storm_window_doc_id('batch_pull shard=scheduler_99') == 'batch_pull_shard_scheduler_99'
    )  # the deterministic mapping


def test_label_grammar_sanitized_fit_05():
    assert (
        storage.fleet_storm_window_doc_id('batch_pull shard=scheduler_1a') == 'batch_pull_shard_scheduler_1a'
    )  # the deterministic mapping


def test_doc_id_length_boundary_ok():
    label = 'a' * 64  # the operation-grammar maximum
    assert storage.fleet_storm_window_doc_id(label) == label


def test_doc_id_length_boundary_refused():
    assert storage.fleet_storm_window_doc_id('a' * 129) is None  # past the bounded id alphabet


# --------------------------------------------------------------------------
# Composite serving-pull labels across the shard space
# --------------------------------------------------------------------------


def test_composite_label_pull_shard_00():
    assert storage.fleet_storm_window_doc_id('batch_pull shard=scheduler_00') == 'batch_pull_shard_scheduler_00'
    wall = FakeWall(now=50.0)
    window = fresh_window(wall=wall)
    client = StormDocsClient()
    window.publish('batch_pull shard=scheduler_00', 0.75, client=client)
    assert client.set_calls[0][:2] == ('batch_pipeline_dev_storm_dampers', 'batch_pull_shard_scheduler_00')
    assert client.set_calls[0][2] == {'armed_until': 50.75, 'window_seconds': 0.75}


def test_composite_label_claim_shard_00():
    assert storage.fleet_storm_window_doc_id('batch_claim shard=scheduler_00') == 'batch_claim_shard_scheduler_00'
    wall = FakeWall(now=50.0)
    window = fresh_window(wall=wall)
    client = StormDocsClient()
    window.publish('batch_claim shard=scheduler_00', 0.75, client=client)
    assert client.set_calls[0][:2] == ('batch_pipeline_dev_storm_dampers', 'batch_claim_shard_scheduler_00')
    assert client.set_calls[0][2] == {'armed_until': 50.75, 'window_seconds': 0.75}


def test_composite_label_pull_shard_07():
    assert storage.fleet_storm_window_doc_id('batch_pull shard=scheduler_07') == 'batch_pull_shard_scheduler_07'
    wall = FakeWall(now=50.0)
    window = fresh_window(wall=wall)
    client = StormDocsClient()
    window.publish('batch_pull shard=scheduler_07', 0.75, client=client)
    assert client.set_calls[0][:2] == ('batch_pipeline_dev_storm_dampers', 'batch_pull_shard_scheduler_07')
    assert client.set_calls[0][2] == {'armed_until': 50.75, 'window_seconds': 0.75}


def test_composite_label_claim_shard_07():
    assert storage.fleet_storm_window_doc_id('batch_claim shard=scheduler_07') == 'batch_claim_shard_scheduler_07'
    wall = FakeWall(now=50.0)
    window = fresh_window(wall=wall)
    client = StormDocsClient()
    window.publish('batch_claim shard=scheduler_07', 0.75, client=client)
    assert client.set_calls[0][:2] == ('batch_pipeline_dev_storm_dampers', 'batch_claim_shard_scheduler_07')
    assert client.set_calls[0][2] == {'armed_until': 50.75, 'window_seconds': 0.75}


def test_composite_label_pull_shard_15():
    assert storage.fleet_storm_window_doc_id('batch_pull shard=scheduler_15') == 'batch_pull_shard_scheduler_15'
    wall = FakeWall(now=50.0)
    window = fresh_window(wall=wall)
    client = StormDocsClient()
    window.publish('batch_pull shard=scheduler_15', 0.75, client=client)
    assert client.set_calls[0][:2] == ('batch_pipeline_dev_storm_dampers', 'batch_pull_shard_scheduler_15')
    assert client.set_calls[0][2] == {'armed_until': 50.75, 'window_seconds': 0.75}


def test_composite_label_claim_shard_15():
    assert storage.fleet_storm_window_doc_id('batch_claim shard=scheduler_15') == 'batch_claim_shard_scheduler_15'
    wall = FakeWall(now=50.0)
    window = fresh_window(wall=wall)
    client = StormDocsClient()
    window.publish('batch_claim shard=scheduler_15', 0.75, client=client)
    assert client.set_calls[0][:2] == ('batch_pipeline_dev_storm_dampers', 'batch_claim_shard_scheduler_15')
    assert client.set_calls[0][2] == {'armed_until': 50.75, 'window_seconds': 0.75}


def test_composite_label_pull_shard_31():
    assert storage.fleet_storm_window_doc_id('batch_pull shard=scheduler_31') == 'batch_pull_shard_scheduler_31'
    wall = FakeWall(now=50.0)
    window = fresh_window(wall=wall)
    client = StormDocsClient()
    window.publish('batch_pull shard=scheduler_31', 0.75, client=client)
    assert client.set_calls[0][:2] == ('batch_pipeline_dev_storm_dampers', 'batch_pull_shard_scheduler_31')
    assert client.set_calls[0][2] == {'armed_until': 50.75, 'window_seconds': 0.75}


def test_composite_label_claim_shard_31():
    assert storage.fleet_storm_window_doc_id('batch_claim shard=scheduler_31') == 'batch_claim_shard_scheduler_31'
    wall = FakeWall(now=50.0)
    window = fresh_window(wall=wall)
    client = StormDocsClient()
    window.publish('batch_claim shard=scheduler_31', 0.75, client=client)
    assert client.set_calls[0][:2] == ('batch_pipeline_dev_storm_dampers', 'batch_claim_shard_scheduler_31')
    assert client.set_calls[0][2] == {'armed_until': 50.75, 'window_seconds': 0.75}


def test_composite_label_pull_shard_47():
    assert storage.fleet_storm_window_doc_id('batch_pull shard=scheduler_47') == 'batch_pull_shard_scheduler_47'
    wall = FakeWall(now=50.0)
    window = fresh_window(wall=wall)
    client = StormDocsClient()
    window.publish('batch_pull shard=scheduler_47', 0.75, client=client)
    assert client.set_calls[0][:2] == ('batch_pipeline_dev_storm_dampers', 'batch_pull_shard_scheduler_47')
    assert client.set_calls[0][2] == {'armed_until': 50.75, 'window_seconds': 0.75}


def test_composite_label_claim_shard_47():
    assert storage.fleet_storm_window_doc_id('batch_claim shard=scheduler_47') == 'batch_claim_shard_scheduler_47'
    wall = FakeWall(now=50.0)
    window = fresh_window(wall=wall)
    client = StormDocsClient()
    window.publish('batch_claim shard=scheduler_47', 0.75, client=client)
    assert client.set_calls[0][:2] == ('batch_pipeline_dev_storm_dampers', 'batch_claim_shard_scheduler_47')
    assert client.set_calls[0][2] == {'armed_until': 50.75, 'window_seconds': 0.75}


def test_composite_label_pull_shard_63():
    assert storage.fleet_storm_window_doc_id('batch_pull shard=scheduler_63') == 'batch_pull_shard_scheduler_63'
    wall = FakeWall(now=50.0)
    window = fresh_window(wall=wall)
    client = StormDocsClient()
    window.publish('batch_pull shard=scheduler_63', 0.75, client=client)
    assert client.set_calls[0][:2] == ('batch_pipeline_dev_storm_dampers', 'batch_pull_shard_scheduler_63')
    assert client.set_calls[0][2] == {'armed_until': 50.75, 'window_seconds': 0.75}


def test_composite_label_claim_shard_63():
    assert storage.fleet_storm_window_doc_id('batch_claim shard=scheduler_63') == 'batch_claim_shard_scheduler_63'
    wall = FakeWall(now=50.0)
    window = fresh_window(wall=wall)
    client = StormDocsClient()
    window.publish('batch_claim shard=scheduler_63', 0.75, client=client)
    assert client.set_calls[0][:2] == ('batch_pipeline_dev_storm_dampers', 'batch_claim_shard_scheduler_63')
    assert client.set_calls[0][2] == {'armed_until': 50.75, 'window_seconds': 0.75}


# --------------------------------------------------------------------------
# Dormancy under each kill switch
# --------------------------------------------------------------------------


def test_dormant_contention_retry_enabled_healthy_run(monkeypatch):
    monkeypatch.setattr(storage, 'contention_retry_enabled', lambda: False)
    damper, window, clock, wall = adopt_clocks('batch_pipeline_dev', jitter=0.0, now=10.0)
    client = StormDocsClient()
    window.publish('batch_merge_commit', 2.0, client=client)  # a sibling armed the fleet
    damper._armed_until['batch_merge_commit'] = clock.now + 2.0  # and the process itself armed
    writes_before, reads_before = len(client.set_calls), len(client.get_calls)
    store = default_store(monkeypatch, client=client)
    assert store.run(lambda tx: 'ok', operation='batch_merge_commit') == 'ok'
    assert clock.sleeps == []  # no consult sleep at all
    assert len(client.get_calls) == reads_before  # the dormant entry never adopts
    assert len(client.set_calls) == writes_before  # and never broadcasts


def test_dormant_contention_storm_damper_enabled_healthy_run(monkeypatch):
    monkeypatch.setattr(storage, 'contention_storm_damper_enabled', lambda: False)
    damper, window, clock, wall = adopt_clocks('batch_pipeline_dev', jitter=0.0, now=10.0)
    client = StormDocsClient()
    window.publish('batch_merge_commit', 2.0, client=client)  # a sibling armed the fleet
    damper._armed_until['batch_merge_commit'] = clock.now + 2.0  # and the process itself armed
    writes_before, reads_before = len(client.set_calls), len(client.get_calls)
    store = default_store(monkeypatch, client=client)
    assert store.run(lambda tx: 'ok', operation='batch_merge_commit') == 'ok'
    assert clock.sleeps == []  # no consult sleep at all
    assert len(client.get_calls) == reads_before  # the dormant entry never adopts
    assert len(client.set_calls) == writes_before  # and never broadcasts


def test_dormant_storm_damper_exhaustion_never_broadcasts(monkeypatch):
    monkeypatch.setattr(storage, 'contention_storm_damper_enabled', lambda: False)
    damper, window, clock, wall = adopt_clocks('batch_pipeline_dev', jitter=0.0, now=10.0)
    client = StormDocsClient(abort_times=10**6)
    store = default_store(monkeypatch, client=client)
    error = exhaust_run(store, 'batch_merge_commit')
    assert error.retry_after == 0.0  # no damper, no stamp
    assert window.publishes == 0
    assert client.set_calls == []  # and no fleet write


def test_dormant_contention_retry_exhaustion_raises_raw_abort(monkeypatch):
    monkeypatch.setattr(storage, 'contention_retry_enabled', lambda: False)
    damper, window, clock, wall = adopt_clocks('batch_pipeline_dev', jitter=0.0, now=10.0)
    client = StormDocsClient(abort_times=10**6)
    store = default_store(monkeypatch, client=client)
    with pytest.raises(ValueError):  # the SDK transactional wrapper wraps the raw Aborted
        store.run(lambda tx: True, operation='batch_merge_commit')
    assert client.set_calls == []  # the raw abort propagates, no broadcast lane


# --------------------------------------------------------------------------
# Namespace isolation matrix
# --------------------------------------------------------------------------


def test_namespace_isolation_dev_to_dev():
    writer = fresh_window('batch_pipeline_dev', wall=FakeWall(now=50.0))
    reader = fresh_window('batch_pipeline_dev', wall=FakeWall(now=50.0))
    client = StormDocsClient()
    writer.publish('batch_merge', 1.5, client=client)
    assert reader.peek('batch_merge', client=client) == pytest.approx(1.5)


def test_namespace_isolation_dev_to_prod():
    writer = fresh_window('batch_pipeline_dev', wall=FakeWall(now=50.0))
    reader = fresh_window('batch_pipeline_prod', wall=FakeWall(now=50.0))
    client = StormDocsClient()
    writer.publish('batch_merge', 1.5, client=client)
    assert reader.peek('batch_merge', client=client) == pytest.approx(0.0)


def test_namespace_isolation_prod_to_dev():
    writer = fresh_window('batch_pipeline_prod', wall=FakeWall(now=50.0))
    reader = fresh_window('batch_pipeline_dev', wall=FakeWall(now=50.0))
    client = StormDocsClient()
    writer.publish('batch_merge', 1.5, client=client)
    assert reader.peek('batch_merge', client=client) == pytest.approx(0.0)


def test_namespace_isolation_prod_to_prod():
    writer = fresh_window('batch_pipeline_prod', wall=FakeWall(now=50.0))
    reader = fresh_window('batch_pipeline_prod', wall=FakeWall(now=50.0))
    client = StormDocsClient()
    writer.publish('batch_merge', 1.5, client=client)
    assert reader.peek('batch_merge', client=client) == pytest.approx(1.5)


# --------------------------------------------------------------------------
# Arm label cap boundary
# --------------------------------------------------------------------------


def test_label_cap_boundary_below():
    damper, window, clock, wall = adopt_clocks('batch_pipeline_dev')
    client = StormDocsClient()
    cap = storage.FirestoreStore.STORM_DAMPER_MAX_TRACKED_LABELS
    for index in range(cap - 1):
        damper.arm(f'batch_label_{index:03d}', client=client)
    assert damper.arm('batch_still_tracked', client=client) > 0.0
    assert window.publishes == cap


def test_label_cap_boundary_at():
    damper, window, clock, wall = adopt_clocks('batch_pipeline_dev')
    client = StormDocsClient()
    cap = storage.FirestoreStore.STORM_DAMPER_MAX_TRACKED_LABELS
    for index in range(cap):
        damper.arm(f'batch_label_{index:03d}', client=client)
    assert damper.arm('batch_untracked_overflow', client=client) == 0.0
    assert window.publishes == cap  # the fail-open label never broadcast


# --------------------------------------------------------------------------
# Success clears the process ladder, never the document
# --------------------------------------------------------------------------


def test_success_clears_process_not_document_j0p0(monkeypatch):
    silence_chain_sleep(monkeypatch)
    damper, window, clock, wall = adopt_clocks('batch_pipeline_dev', jitter=0, now=10.0)
    stormy = StormDocsClient(abort_times=10**6)
    exhaust_run(default_store(monkeypatch, client=stormy), 'batch_merge_commit')
    assert ('batch_pipeline_dev_storm_dampers', 'batch_merge_commit') in stormy.docs
    healthy = StormDocsClient()
    default_store(monkeypatch, client=healthy).run(lambda tx: 'ok', operation='batch_merge_commit')
    assert ('batch_pipeline_dev_storm_dampers', 'batch_merge_commit') in stormy.docs  # decays, never deleted
    assert damper._generations == {}  # process ladder cleared on the clean success


def test_success_clears_process_not_document_j0p5(monkeypatch):
    silence_chain_sleep(monkeypatch)
    damper, window, clock, wall = adopt_clocks('batch_pipeline_dev', jitter=0.5, now=10.0)
    stormy = StormDocsClient(abort_times=10**6)
    exhaust_run(default_store(monkeypatch, client=stormy), 'batch_merge_commit')
    assert ('batch_pipeline_dev_storm_dampers', 'batch_merge_commit') in stormy.docs
    healthy = StormDocsClient()
    default_store(monkeypatch, client=healthy).run(lambda tx: 'ok', operation='batch_merge_commit')
    assert ('batch_pipeline_dev_storm_dampers', 'batch_merge_commit') in stormy.docs  # decays, never deleted
    assert damper._generations == {}  # process ladder cleared on the clean success


# --------------------------------------------------------------------------
# Non-transactional paths stay off the lane
# --------------------------------------------------------------------------


def test_probe_never_touches_the_lane(monkeypatch):
    damper, window, clock, wall = adopt_clocks('batch_pipeline_dev')
    client = StormDocsClient()
    window.publish('jobs_hot_doc', 2.0, client=client)
    probe_client = StormDocsClient()
    store = default_store(monkeypatch, client=probe_client)
    assert store.probe('jobs', 'segment-1') == {}
    storm_reads = [call for call in probe_client.get_calls if call[0] == 'batch_pipeline_dev_storm_dampers']
    assert storm_reads == []  # advisory reads stay off the storm lane


# --------------------------------------------------------------------------
# Absent documents: negative cache and TTL
# --------------------------------------------------------------------------


def test_absent_doc_negative_cache_batch_merge_age0p0():
    wall = FakeWall(now=50.0)
    window = fresh_window(wall=wall)
    client = StormDocsClient()
    assert window.peek('batch_merge', client=client) == 0.0
    wall.advance(0.0)
    assert window.peek('batch_merge', client=client) == 0.0
    assert len(client.get_calls) == 1
    assert window.absent_reads == 1


def test_absent_doc_negative_cache_batch_merge_age0p25():
    wall = FakeWall(now=50.0)
    window = fresh_window(wall=wall)
    client = StormDocsClient()
    assert window.peek('batch_merge', client=client) == 0.0
    wall.advance(0.25)
    assert window.peek('batch_merge', client=client) == 0.0
    assert len(client.get_calls) == 1
    assert window.absent_reads == 1


def test_absent_doc_negative_cache_batch_merge_age0p5():
    wall = FakeWall(now=50.0)
    window = fresh_window(wall=wall)
    client = StormDocsClient()
    assert window.peek('batch_merge', client=client) == 0.0
    wall.advance(0.5)
    assert window.peek('batch_merge', client=client) == 0.0
    assert len(client.get_calls) == 1
    assert window.absent_reads == 1


def test_absent_doc_negative_cache_batch_merge_age0p99():
    wall = FakeWall(now=50.0)
    window = fresh_window(wall=wall)
    client = StormDocsClient()
    assert window.peek('batch_merge', client=client) == 0.0
    wall.advance(0.99)
    assert window.peek('batch_merge', client=client) == 0.0
    assert len(client.get_calls) == 1
    assert window.absent_reads == 1


def test_absent_doc_negative_cache_batch_merge_age1p0():
    wall = FakeWall(now=50.0)
    window = fresh_window(wall=wall)
    client = StormDocsClient()
    assert window.peek('batch_merge', client=client) == 0.0
    wall.advance(1.0)
    assert window.peek('batch_merge', client=client) == 0.0
    assert len(client.get_calls) == 2
    assert window.absent_reads == 2


def test_absent_doc_negative_cache_batch_merge_age2p0():
    wall = FakeWall(now=50.0)
    window = fresh_window(wall=wall)
    client = StormDocsClient()
    assert window.peek('batch_merge', client=client) == 0.0
    wall.advance(2.0)
    assert window.peek('batch_merge', client=client) == 0.0
    assert len(client.get_calls) == 2
    assert window.absent_reads == 2


def test_absent_doc_negative_cache_batch_pull_shard_scheduler_31_age0p0():
    wall = FakeWall(now=50.0)
    window = fresh_window(wall=wall)
    client = StormDocsClient()
    assert window.peek('batch_pull shard=scheduler_31', client=client) == 0.0
    wall.advance(0.0)
    assert window.peek('batch_pull shard=scheduler_31', client=client) == 0.0
    assert len(client.get_calls) == 1
    assert window.absent_reads == 1


def test_absent_doc_negative_cache_batch_pull_shard_scheduler_31_age0p25():
    wall = FakeWall(now=50.0)
    window = fresh_window(wall=wall)
    client = StormDocsClient()
    assert window.peek('batch_pull shard=scheduler_31', client=client) == 0.0
    wall.advance(0.25)
    assert window.peek('batch_pull shard=scheduler_31', client=client) == 0.0
    assert len(client.get_calls) == 1
    assert window.absent_reads == 1


def test_absent_doc_negative_cache_batch_pull_shard_scheduler_31_age0p5():
    wall = FakeWall(now=50.0)
    window = fresh_window(wall=wall)
    client = StormDocsClient()
    assert window.peek('batch_pull shard=scheduler_31', client=client) == 0.0
    wall.advance(0.5)
    assert window.peek('batch_pull shard=scheduler_31', client=client) == 0.0
    assert len(client.get_calls) == 1
    assert window.absent_reads == 1


def test_absent_doc_negative_cache_batch_pull_shard_scheduler_31_age0p99():
    wall = FakeWall(now=50.0)
    window = fresh_window(wall=wall)
    client = StormDocsClient()
    assert window.peek('batch_pull shard=scheduler_31', client=client) == 0.0
    wall.advance(0.99)
    assert window.peek('batch_pull shard=scheduler_31', client=client) == 0.0
    assert len(client.get_calls) == 1
    assert window.absent_reads == 1


def test_absent_doc_negative_cache_batch_pull_shard_scheduler_31_age1p0():
    wall = FakeWall(now=50.0)
    window = fresh_window(wall=wall)
    client = StormDocsClient()
    assert window.peek('batch_pull shard=scheduler_31', client=client) == 0.0
    wall.advance(1.0)
    assert window.peek('batch_pull shard=scheduler_31', client=client) == 0.0
    assert len(client.get_calls) == 2
    assert window.absent_reads == 2


def test_absent_doc_negative_cache_batch_pull_shard_scheduler_31_age2p0():
    wall = FakeWall(now=50.0)
    window = fresh_window(wall=wall)
    client = StormDocsClient()
    assert window.peek('batch_pull shard=scheduler_31', client=client) == 0.0
    wall.advance(2.0)
    assert window.peek('batch_pull shard=scheduler_31', client=client) == 0.0
    assert len(client.get_calls) == 2
    assert window.absent_reads == 2


# --------------------------------------------------------------------------
# Mirror eviction determinism at the cap
# --------------------------------------------------------------------------


def test_mirror_eviction_overflow_1():
    wall = FakeWall(now=50.0)
    window = fresh_window(wall=wall)
    client = StormDocsClient()
    cap = storage._FleetStormWindow.MAX_CACHED_LABELS
    for index in range(cap + 1):
        window.publish(f'batch_label_{index:04d}', 1.0, client=client)
    assert window.cached_labels() == cap


def test_mirror_eviction_overflow_5():
    wall = FakeWall(now=50.0)
    window = fresh_window(wall=wall)
    client = StormDocsClient()
    cap = storage._FleetStormWindow.MAX_CACHED_LABELS
    for index in range(cap + 5):
        window.publish(f'batch_label_{index:04d}', 1.0, client=client)
    assert window.cached_labels() == cap


def test_mirror_eviction_overflow_10():
    wall = FakeWall(now=50.0)
    window = fresh_window(wall=wall)
    client = StormDocsClient()
    cap = storage._FleetStormWindow.MAX_CACHED_LABELS
    for index in range(cap + 10):
        window.publish(f'batch_label_{index:04d}', 1.0, client=client)
    assert window.cached_labels() == cap


def test_mirror_evicted_label_publishes_through_the_floor_read():
    wall = FakeWall(now=50.0)
    window = fresh_window(wall=wall)
    client = StormDocsClient()
    cap = storage._FleetStormWindow.MAX_CACHED_LABELS
    for index in range(cap):
        window.publish(f'batch_label_{index:04d}', 1.0, client=client)
    reads_before = len(client.get_calls)
    sets_before = len(client.set_calls)
    wall.advance(0.5)
    window.publish('batch_label_0000', 2.0, client=client)  # evicted: floor read, then write
    assert len(client.get_calls) == reads_before + 1  # the evicted label's mirror is cold
    assert len(client.set_calls) == sets_before + 1  # and the window still publishes


# --------------------------------------------------------------------------
# Bounded call budget and merge semantics
# --------------------------------------------------------------------------


def test_read_carries_the_call_budget():
    wall = FakeWall(now=50.0)
    window = fresh_window(wall=wall)
    client = StormDocsClient()
    window.peek('batch_merge', client=client)
    assert client.get_calls[0][2] == storage._FleetStormWindow.CALL_TIMEOUT_SECONDS


def test_write_carries_the_call_budget():
    wall = FakeWall(now=50.0)
    window = fresh_window(wall=wall)
    client = StormDocsClient()
    window.publish('batch_merge', 1.0, client=client)
    assert client.set_calls[0][4] == storage._FleetStormWindow.CALL_TIMEOUT_SECONDS


def test_merge_flag_is_always_set():
    wall = FakeWall(now=50.0)
    window = fresh_window(wall=wall)
    client = StormDocsClient()
    window.publish('batch_merge', 1.0, client=client)
    assert client.set_calls[0][3] is True  # merge semantics: extend, never replace


# --------------------------------------------------------------------------
# Reset seam and client-less calls
# --------------------------------------------------------------------------


def test_reset_drops_registry_and_state():
    wall = FakeWall(now=50.0)
    window = fresh_window(wall=wall)
    client = StormDocsClient()
    window.publish('batch_merge', 1.0, client=client)
    storage.reset_fleet_storm_windows()
    revived = storage.fleet_storm_window('batch_pipeline_dev')
    assert revived is not window
    assert revived.cached_labels() == 0


def test_reset_then_adopt_re_reads_the_document():
    wall = FakeWall(now=50.0)
    window = fresh_window(wall=wall)
    client = StormDocsClient()
    client.docs[('batch_pipeline_dev_storm_dampers', 'batch_merge')] = {'armed_until': 51.0}
    storage.reset_fleet_storm_windows()
    revived = storage.fleet_storm_window('batch_pipeline_dev')
    revived._wall_now = wall.time
    assert revived.peek('batch_merge', client=client) == pytest.approx(1.0)
    assert len(client.get_calls) == 1  # a fresh pod reads; nothing was carried over


def test_clientless_calls_change_no_counter():
    window = fresh_window(wall=FakeWall(now=50.0))
    assert window.peek('batch_merge', client=None) == 0.0
    assert window.reads == 0 and window.absent_reads == 0
    window.publish('batch_merge', 1.0, client=None)
    assert window.publishes == 0 and window.publish_failures == 0


# --------------------------------------------------------------------------
# Fleet-scope log emission matrix
# --------------------------------------------------------------------------


def test_fleet_log_matrix_v0p01(caplog):
    damper, window, clock, wall = adopt_clocks('batch_pipeline_dev', jitter=0.0, now=10.0)
    client = StormDocsClient()
    damper.arm('batch_merge', client=None)  # process window 0.125s
    window.publish('batch_merge', 0.01, client=client)
    with caplog.at_level(logging.INFO, logger='database.batch_pipeline_store'):
        damper.consult('batch_merge', client=client)
    emitted = [record for record in caplog.records if 'scope=fleet' in record.getMessage()]
    assert len(emitted) == 0


def test_fleet_log_matrix_v4p0(caplog):
    damper, window, clock, wall = adopt_clocks('batch_pipeline_dev', jitter=0.0, now=10.0)
    client = StormDocsClient()
    damper.arm('batch_merge', client=None)  # process window 0.125s
    window.publish('batch_merge', 4.0, client=client)
    with caplog.at_level(logging.INFO, logger='database.batch_pipeline_store'):
        damper.consult('batch_merge', client=client)
    emitted = [record for record in caplog.records if 'scope=fleet' in record.getMessage()]
    assert len(emitted) == 1


# --------------------------------------------------------------------------
# Injected dampers carry no fleet window
# --------------------------------------------------------------------------


def test_injected_damper_arm_never_publishes():
    clock = FakeClock(now=10.0)
    private = storage._ContentionStormDamper(
        monotonic=clock.monotonic, sleeper=lambda seconds: None, random_value=lambda: 0.0
    )
    window = fresh_window()
    client = StormDocsClient()
    assert private.arm('batch_merge', client=client) > 0.0
    assert window.publishes == 0 and client.set_calls == []


def test_injected_damper_consult_never_reads():
    clock = FakeClock(now=10.0)
    private = storage._ContentionStormDamper(
        monotonic=clock.monotonic, sleeper=lambda seconds: None, random_value=lambda: 0.0
    )
    window = fresh_window()
    client = StormDocsClient()
    assert private.consult('batch_merge', client=client) == (0.0, 0)
    assert client.get_calls == []


# --------------------------------------------------------------------------
# Production namespace end to end
# --------------------------------------------------------------------------


def test_prod_namespace_end_to_end_j0p0(monkeypatch):
    silence_chain_sleep(monkeypatch)
    damper, window, clock, wall = adopt_clocks('batch_pipeline_prod', jitter=0, now=10.0)
    stormy = StormDocsClient(abort_times=10**6)
    error = exhaust_run(default_store(monkeypatch, namespace='batch_pipeline_prod', client=stormy), 'batch_offer')
    assert error.retry_after == pytest.approx(0.125)
    assert stormy.set_calls[0][:2] == ('batch_pipeline_prod_storm_dampers', 'batch_offer')
    cold = StormDocsClient()
    cold.docs = dict(stormy.docs)
    store = default_store(monkeypatch, namespace='batch_pipeline_prod', client=cold)
    store.run(lambda tx: 'ok', operation='batch_offer')
    assert clock.sleeps[-1] == pytest.approx(0.125)  # the cold sibling waited the broadcast


def test_prod_namespace_end_to_end_j0p5(monkeypatch):
    silence_chain_sleep(monkeypatch)
    damper, window, clock, wall = adopt_clocks('batch_pipeline_prod', jitter=0.5, now=10.0)
    stormy = StormDocsClient(abort_times=10**6)
    error = exhaust_run(default_store(monkeypatch, namespace='batch_pipeline_prod', client=stormy), 'batch_offer')
    assert error.retry_after == pytest.approx(0.1875)
    assert stormy.set_calls[0][:2] == ('batch_pipeline_prod_storm_dampers', 'batch_offer')
    cold = StormDocsClient()
    cold.docs = dict(stormy.docs)
    store = default_store(monkeypatch, namespace='batch_pipeline_prod', client=cold)
    store.run(lambda tx: 'ok', operation='batch_offer')
    assert clock.sleeps[-1] == pytest.approx(0.1875)  # the cold sibling waited the broadcast
