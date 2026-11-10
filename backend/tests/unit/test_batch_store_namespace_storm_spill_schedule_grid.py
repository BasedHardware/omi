"""Namespace storm spill schedule grid

Pins the spill lane across the exhaustion ladder and the scheduler shard matrix: the arm
ladder x jitter x prior-spill-depth matrices, the applied cap, the exhaustion retry_after
stamps, consult-then-arm sequences, the full directed shard-pair matrix (own label waits
uncapped; sibling labels adopt share-capped), store-level exhaust and shard sweeps,
lockstep broadcast volume, mid-ladder peek immunity, the mirror bound, dormancy under
every kill switch, TTL re-reads, equal-depth skips and merge-preserving stamps.

Failure-Class: FC-sibling-label-rederives-a-storm-the-fleet-already-measured

Generated point pins: every test drives the real database.batch_pipeline_store spill lane
on deterministic injected clocks and asserts one point of an input surface. The harness is
restated from tests/unit/test_batch_store_namespace_storm_spill_contract.py so this file
runs isolated.
"""

import logging
import math
from unittest.mock import Mock

import pytest

from database import batch_pipeline_store as storage

BASE_SECONDS = storage.FirestoreStore.STORM_DAMPER_BASE_SECONDS  # 0.25
CAP_SECONDS = storage.FirestoreStore.STORM_DAMPER_CAP_SECONDS  # 4.0


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


from google.api_core.exceptions import Aborted  # noqa: E402  (after the tx stand-in)


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
    """Dict-backed storm-window collection recording both lanes' call budgets."""

    def __init__(self, abort_times=0):
        self.abort_times = abort_times
        self._aborts_left = abort_times
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
            return AbortThenCommitTx(1)
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


def spill_doc_id():
    return storage._FleetStormWindow.SPILL_DOC_ID


def spill_collection(namespace):
    return f'{namespace}_storm_dampers'


def seed_spill(client, namespace, until_wall, label='batch_pull_shard_scheduler_03'):
    client.docs[(spill_collection(namespace), spill_doc_id())] = {
        'armed_until': until_wall,
        'label': label,
    }


def fresh_window(namespace, *, wall_now=1_000_000.0):
    wall = FakeWall(now=wall_now)
    window = storage._FleetStormWindow(namespace)
    window._wall_now = wall.time
    return window, wall


def fresh_damper(namespace, *, window=None, now=100.0, jitter=0.0):
    clock = FakeClock(now=now, jitter=jitter)
    damper = storage._ContentionStormDamper(fleet_window=window)
    damper._monotonic = clock.monotonic
    damper._sleeper = clock.sleep
    damper._random_value = clock.random_value
    return damper, clock


WALL0 = 1000000.0
NOW0 = 100.0

SPILL_DOC = storage._FleetStormWindow.SPILL_DOC_ID


def seed_window_doc(client, namespace, label, until_wall):
    doc_id = storage.fleet_storm_window_doc_id(label)
    client.docs[(f'{namespace}_storm_dampers', doc_id)] = {'armed_until': until_wall}


def default_store(monkeypatch, namespace='batch_pipeline_dev', client=None):
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


@pytest.fixture(autouse=True)
def _fresh_storm_registry():
    """The generated grids run against the real registry; reset it per test."""
    storage.reset_fleet_storm_windows()
    yield
    storage.reset_fleet_storm_windows()


def test_ladder_n1_j0_pabsent():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    applied = 0.0
    for _ in range(1):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(0.125)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000000.125)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 0.125)


def test_ladder_n1_j0_p0p05():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.05)
    applied = 0.0
    for _ in range(1):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(0.125)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000000.125)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 0.125)


def test_ladder_n1_j0_p4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    applied = 0.0
    for _ in range(1):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(0.125)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000004.0)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 0.125)


def test_ladder_n1_j0p25_pabsent():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    applied = 0.0
    for _ in range(1):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(0.15625)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000000.15625)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 0.15625)


def test_ladder_n1_j0p25_p0p05():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.05)
    applied = 0.0
    for _ in range(1):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(0.15625)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000000.15625)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 0.15625)


def test_ladder_n1_j0p25_p4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    applied = 0.0
    for _ in range(1):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(0.15625)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000004.0)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 0.15625)


def test_ladder_n1_j0p5_pabsent():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    applied = 0.0
    for _ in range(1):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(0.1875)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000000.1875)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 0.1875)


def test_ladder_n1_j0p5_p0p05():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.05)
    applied = 0.0
    for _ in range(1):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(0.1875)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000000.1875)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 0.1875)


def test_ladder_n1_j0p5_p4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    applied = 0.0
    for _ in range(1):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(0.1875)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000004.0)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 0.1875)


def test_ladder_n1_j0p75_pabsent():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    applied = 0.0
    for _ in range(1):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(0.21875)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000000.21875)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 0.21875)


def test_ladder_n1_j0p75_p0p05():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.05)
    applied = 0.0
    for _ in range(1):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(0.21875)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000000.21875)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 0.21875)


def test_ladder_n1_j0p75_p4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    applied = 0.0
    for _ in range(1):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(0.21875)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000004.0)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 0.21875)


def test_ladder_n1_j1_pabsent():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    applied = 0.0
    for _ in range(1):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(0.25)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000000.25)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 0.25)


def test_ladder_n1_j1_p0p05():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.05)
    applied = 0.0
    for _ in range(1):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(0.25)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000000.25)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 0.25)


def test_ladder_n1_j1_p4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    applied = 0.0
    for _ in range(1):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(0.25)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000004.0)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 0.25)


def test_ladder_n2_j0_pabsent():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    applied = 0.0
    for _ in range(2):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(0.25)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000000.25)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 0.25)


def test_ladder_n2_j0_p0p05():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.05)
    applied = 0.0
    for _ in range(2):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(0.25)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000000.25)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 0.25)


def test_ladder_n2_j0_p4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    applied = 0.0
    for _ in range(2):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(0.25)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000004.0)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 0.25)


def test_ladder_n2_j0p25_pabsent():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    applied = 0.0
    for _ in range(2):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(0.3125)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000000.3125)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 0.3125)


def test_ladder_n2_j0p25_p0p05():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.05)
    applied = 0.0
    for _ in range(2):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(0.3125)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000000.3125)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 0.3125)


def test_ladder_n2_j0p25_p4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    applied = 0.0
    for _ in range(2):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(0.3125)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000004.0)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 0.3125)


def test_ladder_n2_j0p5_pabsent():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    applied = 0.0
    for _ in range(2):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(0.375)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000000.375)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 0.375)


def test_ladder_n2_j0p5_p0p05():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.05)
    applied = 0.0
    for _ in range(2):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(0.375)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000000.375)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 0.375)


def test_ladder_n2_j0p5_p4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    applied = 0.0
    for _ in range(2):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(0.375)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000004.0)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 0.375)


def test_ladder_n2_j0p75_pabsent():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    applied = 0.0
    for _ in range(2):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(0.4375)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000000.4375)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 0.4375)


def test_ladder_n2_j0p75_p0p05():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.05)
    applied = 0.0
    for _ in range(2):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(0.4375)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000000.4375)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 0.4375)


def test_ladder_n2_j0p75_p4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    applied = 0.0
    for _ in range(2):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(0.4375)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000004.0)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 0.4375)


def test_ladder_n2_j1_pabsent():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    applied = 0.0
    for _ in range(2):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(0.5)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000000.5)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 0.5)


def test_ladder_n2_j1_p0p05():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.05)
    applied = 0.0
    for _ in range(2):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(0.5)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000000.5)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 0.5)


def test_ladder_n2_j1_p4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    applied = 0.0
    for _ in range(2):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(0.5)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000004.0)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 0.5)


def test_ladder_n3_j0_pabsent():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    applied = 0.0
    for _ in range(3):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(0.5)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000000.5)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 0.5)


def test_ladder_n3_j0_p0p05():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.05)
    applied = 0.0
    for _ in range(3):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(0.5)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000000.5)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 0.5)


def test_ladder_n3_j0_p4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    applied = 0.0
    for _ in range(3):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(0.5)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000004.0)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 0.5)


def test_ladder_n3_j0p25_pabsent():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    applied = 0.0
    for _ in range(3):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(0.625)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000000.625)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 0.625)


def test_ladder_n3_j0p25_p0p05():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.05)
    applied = 0.0
    for _ in range(3):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(0.625)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000000.625)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 0.625)


def test_ladder_n3_j0p25_p4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    applied = 0.0
    for _ in range(3):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(0.625)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000004.0)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 0.625)


def test_ladder_n3_j0p5_pabsent():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    applied = 0.0
    for _ in range(3):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(0.75)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000000.75)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 0.75)


def test_ladder_n3_j0p5_p0p05():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.05)
    applied = 0.0
    for _ in range(3):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(0.75)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000000.75)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 0.75)


def test_ladder_n3_j0p5_p4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    applied = 0.0
    for _ in range(3):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(0.75)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000004.0)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 0.75)


def test_ladder_n3_j0p75_pabsent():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    applied = 0.0
    for _ in range(3):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(0.875)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000000.875)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 0.875)


def test_ladder_n3_j0p75_p0p05():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.05)
    applied = 0.0
    for _ in range(3):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(0.875)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000000.875)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 0.875)


def test_ladder_n3_j0p75_p4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    applied = 0.0
    for _ in range(3):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(0.875)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000004.0)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 0.875)


def test_ladder_n3_j1_pabsent():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    applied = 0.0
    for _ in range(3):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(1.0)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000001.0)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 1.0)


def test_ladder_n3_j1_p0p05():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.05)
    applied = 0.0
    for _ in range(3):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(1.0)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000001.0)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 1.0)


def test_ladder_n3_j1_p4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    applied = 0.0
    for _ in range(3):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(1.0)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000004.0)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 1.0)


def test_ladder_n4_j0_pabsent():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    applied = 0.0
    for _ in range(4):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(1.0)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000001.0)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 1.0)


def test_ladder_n4_j0_p0p05():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.05)
    applied = 0.0
    for _ in range(4):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(1.0)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000001.0)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 1.0)


def test_ladder_n4_j0_p4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    applied = 0.0
    for _ in range(4):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(1.0)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000004.0)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 1.0)


def test_ladder_n4_j0p25_pabsent():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    applied = 0.0
    for _ in range(4):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(1.25)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000001.25)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 1.25)


def test_ladder_n4_j0p25_p0p05():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.05)
    applied = 0.0
    for _ in range(4):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(1.25)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000001.25)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 1.25)


def test_ladder_n4_j0p25_p4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    applied = 0.0
    for _ in range(4):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(1.25)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000004.0)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 1.25)


def test_ladder_n4_j0p5_pabsent():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    applied = 0.0
    for _ in range(4):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(1.5)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000001.5)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 1.5)


def test_ladder_n4_j0p5_p0p05():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.05)
    applied = 0.0
    for _ in range(4):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(1.5)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000001.5)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 1.5)


def test_ladder_n4_j0p5_p4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    applied = 0.0
    for _ in range(4):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(1.5)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000004.0)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 1.5)


def test_ladder_n4_j0p75_pabsent():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    applied = 0.0
    for _ in range(4):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(1.75)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000001.75)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 1.75)


def test_ladder_n4_j0p75_p0p05():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.05)
    applied = 0.0
    for _ in range(4):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(1.75)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000001.75)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 1.75)


def test_ladder_n4_j0p75_p4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    applied = 0.0
    for _ in range(4):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(1.75)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000004.0)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 1.75)


def test_ladder_n4_j1_pabsent():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    applied = 0.0
    for _ in range(4):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(2.0)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000002.0)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 2.0)


def test_ladder_n4_j1_p0p05():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.05)
    applied = 0.0
    for _ in range(4):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(2.0)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000002.0)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 2.0)


def test_ladder_n4_j1_p4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    applied = 0.0
    for _ in range(4):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(2.0)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000004.0)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 2.0)


def test_ladder_n5_j0_pabsent():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    applied = 0.0
    for _ in range(5):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(2.0)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000002.0)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 2.0)


def test_ladder_n5_j0_p0p05():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.05)
    applied = 0.0
    for _ in range(5):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(2.0)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000002.0)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 2.0)


def test_ladder_n5_j0_p4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    applied = 0.0
    for _ in range(5):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(2.0)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000004.0)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 2.0)


def test_ladder_n5_j0p25_pabsent():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    applied = 0.0
    for _ in range(5):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(2.5)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000002.5)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 2.5)


def test_ladder_n5_j0p25_p0p05():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.05)
    applied = 0.0
    for _ in range(5):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(2.5)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000002.5)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 2.5)


def test_ladder_n5_j0p25_p4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    applied = 0.0
    for _ in range(5):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(2.5)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000004.0)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 2.5)


def test_ladder_n5_j0p5_pabsent():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    applied = 0.0
    for _ in range(5):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(3.0)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000003.0)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 3.0)


def test_ladder_n5_j0p5_p0p05():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.05)
    applied = 0.0
    for _ in range(5):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(3.0)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000003.0)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 3.0)


def test_ladder_n5_j0p5_p4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    applied = 0.0
    for _ in range(5):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(3.0)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000004.0)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 3.0)


def test_ladder_n5_j0p75_pabsent():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    applied = 0.0
    for _ in range(5):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(3.5)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000003.5)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 3.5)


def test_ladder_n5_j0p75_p0p05():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.05)
    applied = 0.0
    for _ in range(5):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(3.5)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000003.5)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 3.5)


def test_ladder_n5_j0p75_p4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    applied = 0.0
    for _ in range(5):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(3.5)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000004.0)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 3.5)


def test_ladder_n5_j1_pabsent():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    applied = 0.0
    for _ in range(5):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(4.0)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000004.0)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 4.0)


def test_ladder_n5_j1_p0p05():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.05)
    applied = 0.0
    for _ in range(5):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(4.0)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000004.0)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 4.0)


def test_ladder_n5_j1_p4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    applied = 0.0
    for _ in range(5):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(4.0)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000004.0)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 4.0)


def test_ladder_n6_j0_pabsent():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    applied = 0.0
    for _ in range(6):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(2.0)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000002.0)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 2.0)


def test_ladder_n6_j0_p0p05():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.05)
    applied = 0.0
    for _ in range(6):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(2.0)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000002.0)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 2.0)


def test_ladder_n6_j0_p4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    applied = 0.0
    for _ in range(6):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(2.0)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000004.0)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 2.0)


def test_ladder_n6_j0p25_pabsent():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    applied = 0.0
    for _ in range(6):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(2.5)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000002.5)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 2.5)


def test_ladder_n6_j0p25_p0p05():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.05)
    applied = 0.0
    for _ in range(6):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(2.5)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000002.5)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 2.5)


def test_ladder_n6_j0p25_p4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    applied = 0.0
    for _ in range(6):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(2.5)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000004.0)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 2.5)


def test_ladder_n6_j0p5_pabsent():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    applied = 0.0
    for _ in range(6):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(3.0)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000003.0)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 3.0)


def test_ladder_n6_j0p5_p0p05():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.05)
    applied = 0.0
    for _ in range(6):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(3.0)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000003.0)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 3.0)


def test_ladder_n6_j0p5_p4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    applied = 0.0
    for _ in range(6):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(3.0)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000004.0)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 3.0)


def test_ladder_n6_j0p75_pabsent():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    applied = 0.0
    for _ in range(6):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(3.5)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000003.5)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 3.5)


def test_ladder_n6_j0p75_p0p05():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.05)
    applied = 0.0
    for _ in range(6):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(3.5)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000003.5)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 3.5)


def test_ladder_n6_j0p75_p4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    applied = 0.0
    for _ in range(6):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(3.5)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000004.0)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 3.5)


def test_ladder_n6_j1_pabsent():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    applied = 0.0
    for _ in range(6):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(4.0)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000004.0)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 4.0)


def test_ladder_n6_j1_p0p05():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.05)
    applied = 0.0
    for _ in range(6):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(4.0)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000004.0)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 4.0)


def test_ladder_n6_j1_p4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    applied = 0.0
    for _ in range(6):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(4.0)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000004.0)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 4.0)


def test_ladder_n7_j0_pabsent():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    applied = 0.0
    for _ in range(7):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(2.0)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000002.0)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 2.0)


def test_ladder_n7_j0_p0p05():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.05)
    applied = 0.0
    for _ in range(7):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(2.0)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000002.0)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 2.0)


def test_ladder_n7_j0_p4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    applied = 0.0
    for _ in range(7):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(2.0)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000004.0)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 2.0)


def test_ladder_n7_j0p25_pabsent():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    applied = 0.0
    for _ in range(7):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(2.5)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000002.5)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 2.5)


def test_ladder_n7_j0p25_p0p05():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.05)
    applied = 0.0
    for _ in range(7):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(2.5)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000002.5)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 2.5)


def test_ladder_n7_j0p25_p4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    applied = 0.0
    for _ in range(7):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(2.5)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000004.0)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 2.5)


def test_ladder_n7_j0p5_pabsent():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    applied = 0.0
    for _ in range(7):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(3.0)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000003.0)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 3.0)


def test_ladder_n7_j0p5_p0p05():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.05)
    applied = 0.0
    for _ in range(7):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(3.0)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000003.0)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 3.0)


def test_ladder_n7_j0p5_p4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    applied = 0.0
    for _ in range(7):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(3.0)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000004.0)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 3.0)


def test_ladder_n7_j0p75_pabsent():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    applied = 0.0
    for _ in range(7):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(3.5)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000003.5)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 3.5)


def test_ladder_n7_j0p75_p0p05():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.05)
    applied = 0.0
    for _ in range(7):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(3.5)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000003.5)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 3.5)


def test_ladder_n7_j0p75_p4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    applied = 0.0
    for _ in range(7):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(3.5)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000004.0)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 3.5)


def test_ladder_n7_j1_pabsent():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    applied = 0.0
    for _ in range(7):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(4.0)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000004.0)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 4.0)


def test_ladder_n7_j1_p0p05():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.05)
    applied = 0.0
    for _ in range(7):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(4.0)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000004.0)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 4.0)


def test_ladder_n7_j1_p4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    applied = 0.0
    for _ in range(7):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(4.0)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000004.0)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 4.0)


def test_ladder_n8_j0_pabsent():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    applied = 0.0
    for _ in range(8):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(2.0)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000002.0)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 2.0)


def test_ladder_n8_j0_p0p05():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.05)
    applied = 0.0
    for _ in range(8):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(2.0)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000002.0)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 2.0)


def test_ladder_n8_j0_p4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    applied = 0.0
    for _ in range(8):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(2.0)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000004.0)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 2.0)


def test_ladder_n8_j0p25_pabsent():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    applied = 0.0
    for _ in range(8):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(2.5)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000002.5)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 2.5)


def test_ladder_n8_j0p25_p0p05():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.05)
    applied = 0.0
    for _ in range(8):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(2.5)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000002.5)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 2.5)


def test_ladder_n8_j0p25_p4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    applied = 0.0
    for _ in range(8):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(2.5)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000004.0)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 2.5)


def test_ladder_n8_j0p5_pabsent():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    applied = 0.0
    for _ in range(8):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(3.0)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000003.0)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 3.0)


def test_ladder_n8_j0p5_p0p05():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.05)
    applied = 0.0
    for _ in range(8):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(3.0)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000003.0)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 3.0)


def test_ladder_n8_j0p5_p4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    applied = 0.0
    for _ in range(8):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(3.0)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000004.0)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 3.0)


def test_ladder_n8_j0p75_pabsent():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    applied = 0.0
    for _ in range(8):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(3.5)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000003.5)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 3.5)


def test_ladder_n8_j0p75_p0p05():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.05)
    applied = 0.0
    for _ in range(8):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(3.5)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000003.5)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 3.5)


def test_ladder_n8_j0p75_p4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    applied = 0.0
    for _ in range(8):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(3.5)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000004.0)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 3.5)


def test_ladder_n8_j1_pabsent():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    applied = 0.0
    for _ in range(8):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(4.0)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000004.0)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 4.0)


def test_ladder_n8_j1_p0p05():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.05)
    applied = 0.0
    for _ in range(8):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(4.0)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000004.0)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 4.0)


def test_ladder_n8_j1_p4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    applied = 0.0
    for _ in range(8):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(4.0)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000004.0)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 4.0)


def test_ladder_n9_j0_pabsent():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    applied = 0.0
    for _ in range(9):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(2.0)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000002.0)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 2.0)


def test_ladder_n9_j0_p0p05():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.05)
    applied = 0.0
    for _ in range(9):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(2.0)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000002.0)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 2.0)


def test_ladder_n9_j0_p4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    applied = 0.0
    for _ in range(9):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(2.0)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000004.0)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 2.0)


def test_ladder_n9_j0p25_pabsent():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    applied = 0.0
    for _ in range(9):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(2.5)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000002.5)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 2.5)


def test_ladder_n9_j0p25_p0p05():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.05)
    applied = 0.0
    for _ in range(9):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(2.5)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000002.5)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 2.5)


def test_ladder_n9_j0p25_p4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    applied = 0.0
    for _ in range(9):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(2.5)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000004.0)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 2.5)


def test_ladder_n9_j0p5_pabsent():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    applied = 0.0
    for _ in range(9):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(3.0)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000003.0)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 3.0)


def test_ladder_n9_j0p5_p0p05():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.05)
    applied = 0.0
    for _ in range(9):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(3.0)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000003.0)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 3.0)


def test_ladder_n9_j0p5_p4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    applied = 0.0
    for _ in range(9):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(3.0)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000004.0)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 3.0)


def test_ladder_n9_j0p75_pabsent():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    applied = 0.0
    for _ in range(9):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(3.5)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000003.5)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 3.5)


def test_ladder_n9_j0p75_p0p05():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.05)
    applied = 0.0
    for _ in range(9):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(3.5)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000003.5)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 3.5)


def test_ladder_n9_j0p75_p4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    applied = 0.0
    for _ in range(9):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(3.5)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000004.0)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 3.5)


def test_ladder_n9_j1_pabsent():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    applied = 0.0
    for _ in range(9):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(4.0)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000004.0)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 4.0)


def test_ladder_n9_j1_p0p05():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.05)
    applied = 0.0
    for _ in range(9):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(4.0)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000004.0)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 4.0)


def test_ladder_n9_j1_p4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    applied = 0.0
    for _ in range(9):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(4.0)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000004.0)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 4.0)


def test_ladder_n10_j0_pabsent():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    applied = 0.0
    for _ in range(10):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(2.0)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000002.0)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 2.0)


def test_ladder_n10_j0_p0p05():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.05)
    applied = 0.0
    for _ in range(10):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(2.0)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000002.0)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 2.0)


def test_ladder_n10_j0_p4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    applied = 0.0
    for _ in range(10):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(2.0)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000004.0)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 2.0)


def test_ladder_n10_j0p25_pabsent():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    applied = 0.0
    for _ in range(10):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(2.5)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000002.5)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 2.5)


def test_ladder_n10_j0p25_p0p05():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.05)
    applied = 0.0
    for _ in range(10):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(2.5)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000002.5)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 2.5)


def test_ladder_n10_j0p25_p4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    applied = 0.0
    for _ in range(10):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(2.5)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000004.0)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 2.5)


def test_ladder_n10_j0p5_pabsent():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    applied = 0.0
    for _ in range(10):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(3.0)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000003.0)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 3.0)


def test_ladder_n10_j0p5_p0p05():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.05)
    applied = 0.0
    for _ in range(10):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(3.0)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000003.0)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 3.0)


def test_ladder_n10_j0p5_p4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    applied = 0.0
    for _ in range(10):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(3.0)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000004.0)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 3.0)


def test_ladder_n10_j0p75_pabsent():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    applied = 0.0
    for _ in range(10):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(3.5)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000003.5)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 3.5)


def test_ladder_n10_j0p75_p0p05():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.05)
    applied = 0.0
    for _ in range(10):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(3.5)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000003.5)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 3.5)


def test_ladder_n10_j0p75_p4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    applied = 0.0
    for _ in range(10):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(3.5)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000004.0)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 3.5)


def test_ladder_n10_j1_pabsent():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    applied = 0.0
    for _ in range(10):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(4.0)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000004.0)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 4.0)


def test_ladder_n10_j1_p0p05():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.05)
    applied = 0.0
    for _ in range(10):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(4.0)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000004.0)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 4.0)


def test_ladder_n10_j1_p4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    applied = 0.0
    for _ in range(10):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(4.0)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000004.0)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 4.0)


def test_ladder_n11_j0_pabsent():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    applied = 0.0
    for _ in range(11):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(2.0)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000002.0)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 2.0)


def test_ladder_n11_j0_p0p05():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.05)
    applied = 0.0
    for _ in range(11):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(2.0)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000002.0)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 2.0)


def test_ladder_n11_j0_p4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    applied = 0.0
    for _ in range(11):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(2.0)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000004.0)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 2.0)


def test_ladder_n11_j0p25_pabsent():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    applied = 0.0
    for _ in range(11):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(2.5)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000002.5)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 2.5)


def test_ladder_n11_j0p25_p0p05():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.05)
    applied = 0.0
    for _ in range(11):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(2.5)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000002.5)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 2.5)


def test_ladder_n11_j0p25_p4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    applied = 0.0
    for _ in range(11):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(2.5)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000004.0)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 2.5)


def test_ladder_n11_j0p5_pabsent():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    applied = 0.0
    for _ in range(11):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(3.0)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000003.0)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 3.0)


def test_ladder_n11_j0p5_p0p05():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.05)
    applied = 0.0
    for _ in range(11):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(3.0)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000003.0)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 3.0)


def test_ladder_n11_j0p5_p4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    applied = 0.0
    for _ in range(11):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(3.0)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000004.0)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 3.0)


def test_ladder_n11_j0p75_pabsent():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    applied = 0.0
    for _ in range(11):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(3.5)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000003.5)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 3.5)


def test_ladder_n11_j0p75_p0p05():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.05)
    applied = 0.0
    for _ in range(11):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(3.5)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000003.5)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 3.5)


def test_ladder_n11_j0p75_p4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    applied = 0.0
    for _ in range(11):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(3.5)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000004.0)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 3.5)


def test_ladder_n11_j1_pabsent():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    applied = 0.0
    for _ in range(11):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(4.0)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000004.0)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 4.0)


def test_ladder_n11_j1_p0p05():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.05)
    applied = 0.0
    for _ in range(11):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(4.0)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000004.0)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 4.0)


def test_ladder_n11_j1_p4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    applied = 0.0
    for _ in range(11):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(4.0)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000004.0)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 4.0)


def test_ladder_n12_j0_pabsent():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    applied = 0.0
    for _ in range(12):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(2.0)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000002.0)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 2.0)


def test_ladder_n12_j0_p0p05():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.05)
    applied = 0.0
    for _ in range(12):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(2.0)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000002.0)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 2.0)


def test_ladder_n12_j0_p4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    applied = 0.0
    for _ in range(12):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(2.0)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000004.0)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 2.0)


def test_ladder_n12_j0p25_pabsent():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    applied = 0.0
    for _ in range(12):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(2.5)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000002.5)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 2.5)


def test_ladder_n12_j0p25_p0p05():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.05)
    applied = 0.0
    for _ in range(12):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(2.5)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000002.5)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 2.5)


def test_ladder_n12_j0p25_p4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    applied = 0.0
    for _ in range(12):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(2.5)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000004.0)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 2.5)


def test_ladder_n12_j0p5_pabsent():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    applied = 0.0
    for _ in range(12):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(3.0)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000003.0)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 3.0)


def test_ladder_n12_j0p5_p0p05():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.05)
    applied = 0.0
    for _ in range(12):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(3.0)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000003.0)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 3.0)


def test_ladder_n12_j0p5_p4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    applied = 0.0
    for _ in range(12):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(3.0)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000004.0)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 3.0)


def test_ladder_n12_j0p75_pabsent():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    applied = 0.0
    for _ in range(12):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(3.5)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000003.5)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 3.5)


def test_ladder_n12_j0p75_p0p05():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.05)
    applied = 0.0
    for _ in range(12):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(3.5)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000003.5)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 3.5)


def test_ladder_n12_j0p75_p4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    applied = 0.0
    for _ in range(12):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(3.5)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000004.0)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 3.5)


def test_ladder_n12_j1_pabsent():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    applied = 0.0
    for _ in range(12):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(4.0)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000004.0)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 4.0)


def test_ladder_n12_j1_p0p05():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.05)
    applied = 0.0
    for _ in range(12):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(4.0)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000004.0)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 4.0)


def test_ladder_n12_j1_p4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    applied = 0.0
    for _ in range(12):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(4.0)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000004.0)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 4.0)


def test_ladder_n13_j0_pabsent():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    applied = 0.0
    for _ in range(13):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(2.0)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000002.0)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 2.0)


def test_ladder_n13_j0_p0p05():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.05)
    applied = 0.0
    for _ in range(13):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(2.0)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000002.0)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 2.0)


def test_ladder_n13_j0_p4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    applied = 0.0
    for _ in range(13):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(2.0)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000004.0)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 2.0)


def test_ladder_n13_j0p25_pabsent():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    applied = 0.0
    for _ in range(13):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(2.5)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000002.5)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 2.5)


def test_ladder_n13_j0p25_p0p05():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.05)
    applied = 0.0
    for _ in range(13):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(2.5)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000002.5)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 2.5)


def test_ladder_n13_j0p25_p4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    applied = 0.0
    for _ in range(13):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(2.5)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000004.0)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 2.5)


def test_ladder_n13_j0p5_pabsent():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    applied = 0.0
    for _ in range(13):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(3.0)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000003.0)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 3.0)


def test_ladder_n13_j0p5_p0p05():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.05)
    applied = 0.0
    for _ in range(13):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(3.0)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000003.0)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 3.0)


def test_ladder_n13_j0p5_p4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    applied = 0.0
    for _ in range(13):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(3.0)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000004.0)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 3.0)


def test_ladder_n13_j0p75_pabsent():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    applied = 0.0
    for _ in range(13):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(3.5)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000003.5)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 3.5)


def test_ladder_n13_j0p75_p0p05():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.05)
    applied = 0.0
    for _ in range(13):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(3.5)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000003.5)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 3.5)


def test_ladder_n13_j0p75_p4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    applied = 0.0
    for _ in range(13):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(3.5)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000004.0)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 3.5)


def test_ladder_n13_j1_pabsent():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    applied = 0.0
    for _ in range(13):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(4.0)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000004.0)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 4.0)


def test_ladder_n13_j1_p0p05():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.05)
    applied = 0.0
    for _ in range(13):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(4.0)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000004.0)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 4.0)


def test_ladder_n13_j1_p4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    applied = 0.0
    for _ in range(13):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(4.0)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000004.0)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 4.0)


def test_ladder_n14_j0_pabsent():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    applied = 0.0
    for _ in range(14):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(2.0)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000002.0)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 2.0)


def test_ladder_n14_j0_p0p05():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.05)
    applied = 0.0
    for _ in range(14):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(2.0)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000002.0)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 2.0)


def test_ladder_n14_j0_p4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    applied = 0.0
    for _ in range(14):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(2.0)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000004.0)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 2.0)


def test_ladder_n14_j0p25_pabsent():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    applied = 0.0
    for _ in range(14):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(2.5)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000002.5)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 2.5)


def test_ladder_n14_j0p25_p0p05():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.05)
    applied = 0.0
    for _ in range(14):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(2.5)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000002.5)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 2.5)


def test_ladder_n14_j0p25_p4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    applied = 0.0
    for _ in range(14):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(2.5)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000004.0)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 2.5)


def test_ladder_n14_j0p5_pabsent():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    applied = 0.0
    for _ in range(14):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(3.0)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000003.0)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 3.0)


def test_ladder_n14_j0p5_p0p05():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.05)
    applied = 0.0
    for _ in range(14):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(3.0)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000003.0)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 3.0)


def test_ladder_n14_j0p5_p4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    applied = 0.0
    for _ in range(14):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(3.0)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000004.0)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 3.0)


def test_ladder_n14_j0p75_pabsent():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    applied = 0.0
    for _ in range(14):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(3.5)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000003.5)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 3.5)


def test_ladder_n14_j0p75_p0p05():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.05)
    applied = 0.0
    for _ in range(14):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(3.5)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000003.5)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 3.5)


def test_ladder_n14_j0p75_p4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    applied = 0.0
    for _ in range(14):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(3.5)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000004.0)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 3.5)


def test_ladder_n14_j1_pabsent():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    applied = 0.0
    for _ in range(14):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(4.0)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000004.0)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 4.0)


def test_ladder_n14_j1_p0p05():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.05)
    applied = 0.0
    for _ in range(14):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(4.0)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000004.0)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 4.0)


def test_ladder_n14_j1_p4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    applied = 0.0
    for _ in range(14):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(4.0)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000004.0)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 4.0)


def test_ladder_n15_j0_pabsent():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    applied = 0.0
    for _ in range(15):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(2.0)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000002.0)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 2.0)


def test_ladder_n15_j0_p0p05():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.05)
    applied = 0.0
    for _ in range(15):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(2.0)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000002.0)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 2.0)


def test_ladder_n15_j0_p4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    applied = 0.0
    for _ in range(15):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(2.0)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000004.0)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 2.0)


def test_ladder_n15_j0p25_pabsent():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    applied = 0.0
    for _ in range(15):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(2.5)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000002.5)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 2.5)


def test_ladder_n15_j0p25_p0p05():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.05)
    applied = 0.0
    for _ in range(15):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(2.5)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000002.5)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 2.5)


def test_ladder_n15_j0p25_p4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    applied = 0.0
    for _ in range(15):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(2.5)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000004.0)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 2.5)


def test_ladder_n15_j0p5_pabsent():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    applied = 0.0
    for _ in range(15):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(3.0)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000003.0)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 3.0)


def test_ladder_n15_j0p5_p0p05():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.05)
    applied = 0.0
    for _ in range(15):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(3.0)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000003.0)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 3.0)


def test_ladder_n15_j0p5_p4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    applied = 0.0
    for _ in range(15):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(3.0)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000004.0)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 3.0)


def test_ladder_n15_j0p75_pabsent():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    applied = 0.0
    for _ in range(15):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(3.5)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000003.5)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 3.5)


def test_ladder_n15_j0p75_p0p05():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.05)
    applied = 0.0
    for _ in range(15):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(3.5)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000003.5)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 3.5)


def test_ladder_n15_j0p75_p4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    applied = 0.0
    for _ in range(15):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(3.5)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000004.0)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 3.5)


def test_ladder_n15_j1_pabsent():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    applied = 0.0
    for _ in range(15):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(4.0)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000004.0)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 4.0)


def test_ladder_n15_j1_p0p05():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.05)
    applied = 0.0
    for _ in range(15):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(4.0)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000004.0)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 4.0)


def test_ladder_n15_j1_p4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    applied = 0.0
    for _ in range(15):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(4.0)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000004.0)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 4.0)


def test_ladder_n16_j0_pabsent():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    applied = 0.0
    for _ in range(16):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(2.0)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000002.0)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 2.0)


def test_ladder_n16_j0_p0p05():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.05)
    applied = 0.0
    for _ in range(16):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(2.0)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000002.0)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 2.0)


def test_ladder_n16_j0_p4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    applied = 0.0
    for _ in range(16):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(2.0)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000004.0)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 2.0)


def test_ladder_n16_j0p25_pabsent():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    applied = 0.0
    for _ in range(16):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(2.5)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000002.5)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 2.5)


def test_ladder_n16_j0p25_p0p05():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.05)
    applied = 0.0
    for _ in range(16):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(2.5)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000002.5)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 2.5)


def test_ladder_n16_j0p25_p4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    applied = 0.0
    for _ in range(16):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(2.5)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000004.0)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 2.5)


def test_ladder_n16_j0p5_pabsent():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    applied = 0.0
    for _ in range(16):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(3.0)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000003.0)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 3.0)


def test_ladder_n16_j0p5_p0p05():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.05)
    applied = 0.0
    for _ in range(16):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(3.0)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000003.0)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 3.0)


def test_ladder_n16_j0p5_p4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    applied = 0.0
    for _ in range(16):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(3.0)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000004.0)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 3.0)


def test_ladder_n16_j0p75_pabsent():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    applied = 0.0
    for _ in range(16):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(3.5)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000003.5)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 3.5)


def test_ladder_n16_j0p75_p0p05():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.05)
    applied = 0.0
    for _ in range(16):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(3.5)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000003.5)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 3.5)


def test_ladder_n16_j0p75_p4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    applied = 0.0
    for _ in range(16):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(3.5)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000004.0)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 3.5)


def test_ladder_n16_j1_pabsent():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    applied = 0.0
    for _ in range(16):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(4.0)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000004.0)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 4.0)


def test_ladder_n16_j1_p0p05():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.05)
    applied = 0.0
    for _ in range(16):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(4.0)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000004.0)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 4.0)


def test_ladder_n16_j1_p4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    applied = 0.0
    for _ in range(16):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(4.0)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000004.0)
    label_row = [row for row in client.set_calls if row[1] == 'batch_admit'][-1]
    assert label_row[2]['armed_until'] == pytest.approx(WALL0 + 4.0)


def test_cap_n1_j0():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    applied = 0.0
    for _ in range(1):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(0.125)
    assert applied <= CAP_SECONDS


def test_cap_n1_j0p25():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    applied = 0.0
    for _ in range(1):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(0.15625)
    assert applied <= CAP_SECONDS


def test_cap_n1_j0p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    applied = 0.0
    for _ in range(1):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(0.1875)
    assert applied <= CAP_SECONDS


def test_cap_n1_j0p75():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    applied = 0.0
    for _ in range(1):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(0.21875)
    assert applied <= CAP_SECONDS


def test_cap_n1_j1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    applied = 0.0
    for _ in range(1):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(0.25)
    assert applied <= CAP_SECONDS


def test_cap_n2_j0():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    applied = 0.0
    for _ in range(2):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(0.25)
    assert applied <= CAP_SECONDS


def test_cap_n2_j0p25():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    applied = 0.0
    for _ in range(2):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(0.3125)
    assert applied <= CAP_SECONDS


def test_cap_n2_j0p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    applied = 0.0
    for _ in range(2):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(0.375)
    assert applied <= CAP_SECONDS


def test_cap_n2_j0p75():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    applied = 0.0
    for _ in range(2):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(0.4375)
    assert applied <= CAP_SECONDS


def test_cap_n2_j1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    applied = 0.0
    for _ in range(2):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(0.5)
    assert applied <= CAP_SECONDS


def test_cap_n3_j0():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    applied = 0.0
    for _ in range(3):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(0.5)
    assert applied <= CAP_SECONDS


def test_cap_n3_j0p25():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    applied = 0.0
    for _ in range(3):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(0.625)
    assert applied <= CAP_SECONDS


def test_cap_n3_j0p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    applied = 0.0
    for _ in range(3):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(0.75)
    assert applied <= CAP_SECONDS


def test_cap_n3_j0p75():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    applied = 0.0
    for _ in range(3):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(0.875)
    assert applied <= CAP_SECONDS


def test_cap_n3_j1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    applied = 0.0
    for _ in range(3):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(1.0)
    assert applied <= CAP_SECONDS


def test_cap_n4_j0():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    applied = 0.0
    for _ in range(4):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(1.0)
    assert applied <= CAP_SECONDS


def test_cap_n4_j0p25():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    applied = 0.0
    for _ in range(4):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(1.25)
    assert applied <= CAP_SECONDS


def test_cap_n4_j0p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    applied = 0.0
    for _ in range(4):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(1.5)
    assert applied <= CAP_SECONDS


def test_cap_n4_j0p75():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    applied = 0.0
    for _ in range(4):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(1.75)
    assert applied <= CAP_SECONDS


def test_cap_n4_j1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    applied = 0.0
    for _ in range(4):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(2.0)
    assert applied <= CAP_SECONDS


def test_cap_n5_j0():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    applied = 0.0
    for _ in range(5):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(2.0)
    assert applied <= CAP_SECONDS


def test_cap_n5_j0p25():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    applied = 0.0
    for _ in range(5):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(2.5)
    assert applied <= CAP_SECONDS


def test_cap_n5_j0p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    applied = 0.0
    for _ in range(5):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(3.0)
    assert applied <= CAP_SECONDS


def test_cap_n5_j0p75():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    applied = 0.0
    for _ in range(5):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(3.5)
    assert applied <= CAP_SECONDS


def test_cap_n5_j1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    applied = 0.0
    for _ in range(5):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(4.0)
    assert applied <= CAP_SECONDS


def test_cap_n6_j0():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    applied = 0.0
    for _ in range(6):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(2.0)
    assert applied <= CAP_SECONDS


def test_cap_n6_j0p25():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    applied = 0.0
    for _ in range(6):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(2.5)
    assert applied <= CAP_SECONDS


def test_cap_n6_j0p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    applied = 0.0
    for _ in range(6):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(3.0)
    assert applied <= CAP_SECONDS


def test_cap_n6_j0p75():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    applied = 0.0
    for _ in range(6):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(3.5)
    assert applied <= CAP_SECONDS


def test_cap_n6_j1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    applied = 0.0
    for _ in range(6):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(4.0)
    assert applied <= CAP_SECONDS


def test_cap_n7_j0():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    applied = 0.0
    for _ in range(7):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(2.0)
    assert applied <= CAP_SECONDS


def test_cap_n7_j0p25():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    applied = 0.0
    for _ in range(7):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(2.5)
    assert applied <= CAP_SECONDS


def test_cap_n7_j0p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    applied = 0.0
    for _ in range(7):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(3.0)
    assert applied <= CAP_SECONDS


def test_cap_n7_j0p75():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    applied = 0.0
    for _ in range(7):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(3.5)
    assert applied <= CAP_SECONDS


def test_cap_n7_j1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    applied = 0.0
    for _ in range(7):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(4.0)
    assert applied <= CAP_SECONDS


def test_cap_n8_j0():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    applied = 0.0
    for _ in range(8):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(2.0)
    assert applied <= CAP_SECONDS


def test_cap_n8_j0p25():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    applied = 0.0
    for _ in range(8):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(2.5)
    assert applied <= CAP_SECONDS


def test_cap_n8_j0p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    applied = 0.0
    for _ in range(8):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(3.0)
    assert applied <= CAP_SECONDS


def test_cap_n8_j0p75():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    applied = 0.0
    for _ in range(8):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(3.5)
    assert applied <= CAP_SECONDS


def test_cap_n8_j1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    applied = 0.0
    for _ in range(8):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(4.0)
    assert applied <= CAP_SECONDS


def test_cap_n9_j0():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    applied = 0.0
    for _ in range(9):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(2.0)
    assert applied <= CAP_SECONDS


def test_cap_n9_j0p25():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    applied = 0.0
    for _ in range(9):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(2.5)
    assert applied <= CAP_SECONDS


def test_cap_n9_j0p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    applied = 0.0
    for _ in range(9):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(3.0)
    assert applied <= CAP_SECONDS


def test_cap_n9_j0p75():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    applied = 0.0
    for _ in range(9):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(3.5)
    assert applied <= CAP_SECONDS


def test_cap_n9_j1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    applied = 0.0
    for _ in range(9):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(4.0)
    assert applied <= CAP_SECONDS


def test_cap_n10_j0():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    applied = 0.0
    for _ in range(10):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(2.0)
    assert applied <= CAP_SECONDS


def test_cap_n10_j0p25():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    applied = 0.0
    for _ in range(10):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(2.5)
    assert applied <= CAP_SECONDS


def test_cap_n10_j0p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    applied = 0.0
    for _ in range(10):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(3.0)
    assert applied <= CAP_SECONDS


def test_cap_n10_j0p75():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    applied = 0.0
    for _ in range(10):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(3.5)
    assert applied <= CAP_SECONDS


def test_cap_n10_j1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    applied = 0.0
    for _ in range(10):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(4.0)
    assert applied <= CAP_SECONDS


def test_cap_n11_j0():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    applied = 0.0
    for _ in range(11):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(2.0)
    assert applied <= CAP_SECONDS


def test_cap_n11_j0p25():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    applied = 0.0
    for _ in range(11):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(2.5)
    assert applied <= CAP_SECONDS


def test_cap_n11_j0p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    applied = 0.0
    for _ in range(11):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(3.0)
    assert applied <= CAP_SECONDS


def test_cap_n11_j0p75():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    applied = 0.0
    for _ in range(11):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(3.5)
    assert applied <= CAP_SECONDS


def test_cap_n11_j1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    applied = 0.0
    for _ in range(11):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(4.0)
    assert applied <= CAP_SECONDS


def test_cap_n12_j0():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    applied = 0.0
    for _ in range(12):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(2.0)
    assert applied <= CAP_SECONDS


def test_cap_n12_j0p25():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    applied = 0.0
    for _ in range(12):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(2.5)
    assert applied <= CAP_SECONDS


def test_cap_n12_j0p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    applied = 0.0
    for _ in range(12):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(3.0)
    assert applied <= CAP_SECONDS


def test_cap_n12_j0p75():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    applied = 0.0
    for _ in range(12):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(3.5)
    assert applied <= CAP_SECONDS


def test_cap_n12_j1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    applied = 0.0
    for _ in range(12):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(4.0)
    assert applied <= CAP_SECONDS


def test_cap_n13_j0():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    applied = 0.0
    for _ in range(13):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(2.0)
    assert applied <= CAP_SECONDS


def test_cap_n13_j0p25():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    applied = 0.0
    for _ in range(13):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(2.5)
    assert applied <= CAP_SECONDS


def test_cap_n13_j0p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    applied = 0.0
    for _ in range(13):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(3.0)
    assert applied <= CAP_SECONDS


def test_cap_n13_j0p75():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    applied = 0.0
    for _ in range(13):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(3.5)
    assert applied <= CAP_SECONDS


def test_cap_n13_j1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    applied = 0.0
    for _ in range(13):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(4.0)
    assert applied <= CAP_SECONDS


def test_cap_n14_j0():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    applied = 0.0
    for _ in range(14):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(2.0)
    assert applied <= CAP_SECONDS


def test_cap_n14_j0p25():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    applied = 0.0
    for _ in range(14):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(2.5)
    assert applied <= CAP_SECONDS


def test_cap_n14_j0p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    applied = 0.0
    for _ in range(14):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(3.0)
    assert applied <= CAP_SECONDS


def test_cap_n14_j0p75():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    applied = 0.0
    for _ in range(14):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(3.5)
    assert applied <= CAP_SECONDS


def test_cap_n14_j1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    applied = 0.0
    for _ in range(14):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(4.0)
    assert applied <= CAP_SECONDS


def test_cap_n15_j0():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    applied = 0.0
    for _ in range(15):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(2.0)
    assert applied <= CAP_SECONDS


def test_cap_n15_j0p25():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    applied = 0.0
    for _ in range(15):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(2.5)
    assert applied <= CAP_SECONDS


def test_cap_n15_j0p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    applied = 0.0
    for _ in range(15):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(3.0)
    assert applied <= CAP_SECONDS


def test_cap_n15_j0p75():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    applied = 0.0
    for _ in range(15):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(3.5)
    assert applied <= CAP_SECONDS


def test_cap_n15_j1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    applied = 0.0
    for _ in range(15):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(4.0)
    assert applied <= CAP_SECONDS


def test_cap_n16_j0():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    applied = 0.0
    for _ in range(16):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(2.0)
    assert applied <= CAP_SECONDS


def test_cap_n16_j0p25():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    applied = 0.0
    for _ in range(16):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(2.5)
    assert applied <= CAP_SECONDS


def test_cap_n16_j0p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    applied = 0.0
    for _ in range(16):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(3.0)
    assert applied <= CAP_SECONDS


def test_cap_n16_j0p75():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    applied = 0.0
    for _ in range(16):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(3.5)
    assert applied <= CAP_SECONDS


def test_cap_n16_j1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    applied = 0.0
    for _ in range(16):
        applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(4.0)
    assert applied <= CAP_SECONDS


def test_retry_n1_j0(monkeypatch):
    silence_chain_sleep(monkeypatch)
    client = StormDocsClient(abort_times=10**6)
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    store = default_store(monkeypatch, client=client)
    store._storm_damper = damper
    error = exhaust_run(store, 'batch_admit', times=1)
    assert error.retry_after == pytest.approx(0.125)


def test_retry_n1_j0p25(monkeypatch):
    silence_chain_sleep(monkeypatch)
    client = StormDocsClient(abort_times=10**6)
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    store = default_store(monkeypatch, client=client)
    store._storm_damper = damper
    error = exhaust_run(store, 'batch_admit', times=1)
    assert error.retry_after == pytest.approx(0.15625)


def test_retry_n1_j0p5(monkeypatch):
    silence_chain_sleep(monkeypatch)
    client = StormDocsClient(abort_times=10**6)
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    store = default_store(monkeypatch, client=client)
    store._storm_damper = damper
    error = exhaust_run(store, 'batch_admit', times=1)
    assert error.retry_after == pytest.approx(0.1875)


def test_retry_n1_j0p75(monkeypatch):
    silence_chain_sleep(monkeypatch)
    client = StormDocsClient(abort_times=10**6)
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    store = default_store(monkeypatch, client=client)
    store._storm_damper = damper
    error = exhaust_run(store, 'batch_admit', times=1)
    assert error.retry_after == pytest.approx(0.21875)


def test_retry_n1_j1(monkeypatch):
    silence_chain_sleep(monkeypatch)
    client = StormDocsClient(abort_times=10**6)
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    store = default_store(monkeypatch, client=client)
    store._storm_damper = damper
    error = exhaust_run(store, 'batch_admit', times=1)
    assert error.retry_after == pytest.approx(0.25)


def test_retry_n2_j0(monkeypatch):
    silence_chain_sleep(monkeypatch)
    client = StormDocsClient(abort_times=10**6)
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    store = default_store(monkeypatch, client=client)
    store._storm_damper = damper
    error = exhaust_run(store, 'batch_admit', times=2)
    assert error.retry_after == pytest.approx(0.25)


def test_retry_n2_j0p25(monkeypatch):
    silence_chain_sleep(monkeypatch)
    client = StormDocsClient(abort_times=10**6)
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    store = default_store(monkeypatch, client=client)
    store._storm_damper = damper
    error = exhaust_run(store, 'batch_admit', times=2)
    assert error.retry_after == pytest.approx(0.3125)


def test_retry_n2_j0p5(monkeypatch):
    silence_chain_sleep(monkeypatch)
    client = StormDocsClient(abort_times=10**6)
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    store = default_store(monkeypatch, client=client)
    store._storm_damper = damper
    error = exhaust_run(store, 'batch_admit', times=2)
    assert error.retry_after == pytest.approx(0.375)


def test_retry_n2_j0p75(monkeypatch):
    silence_chain_sleep(monkeypatch)
    client = StormDocsClient(abort_times=10**6)
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    store = default_store(monkeypatch, client=client)
    store._storm_damper = damper
    error = exhaust_run(store, 'batch_admit', times=2)
    assert error.retry_after == pytest.approx(0.4375)


def test_retry_n2_j1(monkeypatch):
    silence_chain_sleep(monkeypatch)
    client = StormDocsClient(abort_times=10**6)
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    store = default_store(monkeypatch, client=client)
    store._storm_damper = damper
    error = exhaust_run(store, 'batch_admit', times=2)
    assert error.retry_after == pytest.approx(0.5)


def test_retry_n3_j0(monkeypatch):
    silence_chain_sleep(monkeypatch)
    client = StormDocsClient(abort_times=10**6)
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    store = default_store(monkeypatch, client=client)
    store._storm_damper = damper
    error = exhaust_run(store, 'batch_admit', times=3)
    assert error.retry_after == pytest.approx(0.5)


def test_retry_n3_j0p25(monkeypatch):
    silence_chain_sleep(monkeypatch)
    client = StormDocsClient(abort_times=10**6)
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    store = default_store(monkeypatch, client=client)
    store._storm_damper = damper
    error = exhaust_run(store, 'batch_admit', times=3)
    assert error.retry_after == pytest.approx(0.625)


def test_retry_n3_j0p5(monkeypatch):
    silence_chain_sleep(monkeypatch)
    client = StormDocsClient(abort_times=10**6)
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    store = default_store(monkeypatch, client=client)
    store._storm_damper = damper
    error = exhaust_run(store, 'batch_admit', times=3)
    assert error.retry_after == pytest.approx(0.75)


def test_retry_n3_j0p75(monkeypatch):
    silence_chain_sleep(monkeypatch)
    client = StormDocsClient(abort_times=10**6)
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    store = default_store(monkeypatch, client=client)
    store._storm_damper = damper
    error = exhaust_run(store, 'batch_admit', times=3)
    assert error.retry_after == pytest.approx(0.875)


def test_retry_n3_j1(monkeypatch):
    silence_chain_sleep(monkeypatch)
    client = StormDocsClient(abort_times=10**6)
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    store = default_store(monkeypatch, client=client)
    store._storm_damper = damper
    error = exhaust_run(store, 'batch_admit', times=3)
    assert error.retry_after == pytest.approx(1.0)


def test_retry_n4_j0(monkeypatch):
    silence_chain_sleep(monkeypatch)
    client = StormDocsClient(abort_times=10**6)
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    store = default_store(monkeypatch, client=client)
    store._storm_damper = damper
    error = exhaust_run(store, 'batch_admit', times=4)
    assert error.retry_after == pytest.approx(1.0)


def test_retry_n4_j0p25(monkeypatch):
    silence_chain_sleep(monkeypatch)
    client = StormDocsClient(abort_times=10**6)
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    store = default_store(monkeypatch, client=client)
    store._storm_damper = damper
    error = exhaust_run(store, 'batch_admit', times=4)
    assert error.retry_after == pytest.approx(1.25)


def test_retry_n4_j0p5(monkeypatch):
    silence_chain_sleep(monkeypatch)
    client = StormDocsClient(abort_times=10**6)
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    store = default_store(monkeypatch, client=client)
    store._storm_damper = damper
    error = exhaust_run(store, 'batch_admit', times=4)
    assert error.retry_after == pytest.approx(1.5)


def test_retry_n4_j0p75(monkeypatch):
    silence_chain_sleep(monkeypatch)
    client = StormDocsClient(abort_times=10**6)
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    store = default_store(monkeypatch, client=client)
    store._storm_damper = damper
    error = exhaust_run(store, 'batch_admit', times=4)
    assert error.retry_after == pytest.approx(1.75)


def test_retry_n4_j1(monkeypatch):
    silence_chain_sleep(monkeypatch)
    client = StormDocsClient(abort_times=10**6)
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    store = default_store(monkeypatch, client=client)
    store._storm_damper = damper
    error = exhaust_run(store, 'batch_admit', times=4)
    assert error.retry_after == pytest.approx(2.0)


def test_retry_n5_j0(monkeypatch):
    silence_chain_sleep(monkeypatch)
    client = StormDocsClient(abort_times=10**6)
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    store = default_store(monkeypatch, client=client)
    store._storm_damper = damper
    error = exhaust_run(store, 'batch_admit', times=5)
    assert error.retry_after == pytest.approx(2.0)


def test_retry_n5_j0p25(monkeypatch):
    silence_chain_sleep(monkeypatch)
    client = StormDocsClient(abort_times=10**6)
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    store = default_store(monkeypatch, client=client)
    store._storm_damper = damper
    error = exhaust_run(store, 'batch_admit', times=5)
    assert error.retry_after == pytest.approx(2.5)


def test_retry_n5_j0p5(monkeypatch):
    silence_chain_sleep(monkeypatch)
    client = StormDocsClient(abort_times=10**6)
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    store = default_store(monkeypatch, client=client)
    store._storm_damper = damper
    error = exhaust_run(store, 'batch_admit', times=5)
    assert error.retry_after == pytest.approx(3.0)


def test_retry_n5_j0p75(monkeypatch):
    silence_chain_sleep(monkeypatch)
    client = StormDocsClient(abort_times=10**6)
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    store = default_store(monkeypatch, client=client)
    store._storm_damper = damper
    error = exhaust_run(store, 'batch_admit', times=5)
    assert error.retry_after == pytest.approx(3.5)


def test_retry_n5_j1(monkeypatch):
    silence_chain_sleep(monkeypatch)
    client = StormDocsClient(abort_times=10**6)
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    store = default_store(monkeypatch, client=client)
    store._storm_damper = damper
    error = exhaust_run(store, 'batch_admit', times=5)
    assert error.retry_after == pytest.approx(4.0)


def test_retry_n6_j0(monkeypatch):
    silence_chain_sleep(monkeypatch)
    client = StormDocsClient(abort_times=10**6)
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    store = default_store(monkeypatch, client=client)
    store._storm_damper = damper
    error = exhaust_run(store, 'batch_admit', times=6)
    assert error.retry_after == pytest.approx(2.0)


def test_retry_n6_j0p25(monkeypatch):
    silence_chain_sleep(monkeypatch)
    client = StormDocsClient(abort_times=10**6)
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    store = default_store(monkeypatch, client=client)
    store._storm_damper = damper
    error = exhaust_run(store, 'batch_admit', times=6)
    assert error.retry_after == pytest.approx(2.5)


def test_retry_n6_j0p5(monkeypatch):
    silence_chain_sleep(monkeypatch)
    client = StormDocsClient(abort_times=10**6)
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    store = default_store(monkeypatch, client=client)
    store._storm_damper = damper
    error = exhaust_run(store, 'batch_admit', times=6)
    assert error.retry_after == pytest.approx(3.0)


def test_retry_n6_j0p75(monkeypatch):
    silence_chain_sleep(monkeypatch)
    client = StormDocsClient(abort_times=10**6)
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    store = default_store(monkeypatch, client=client)
    store._storm_damper = damper
    error = exhaust_run(store, 'batch_admit', times=6)
    assert error.retry_after == pytest.approx(3.5)


def test_retry_n6_j1(monkeypatch):
    silence_chain_sleep(monkeypatch)
    client = StormDocsClient(abort_times=10**6)
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    store = default_store(monkeypatch, client=client)
    store._storm_damper = damper
    error = exhaust_run(store, 'batch_admit', times=6)
    assert error.retry_after == pytest.approx(4.0)


def test_retry_n7_j0(monkeypatch):
    silence_chain_sleep(monkeypatch)
    client = StormDocsClient(abort_times=10**6)
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    store = default_store(monkeypatch, client=client)
    store._storm_damper = damper
    error = exhaust_run(store, 'batch_admit', times=7)
    assert error.retry_after == pytest.approx(2.0)


def test_retry_n7_j0p25(monkeypatch):
    silence_chain_sleep(monkeypatch)
    client = StormDocsClient(abort_times=10**6)
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    store = default_store(monkeypatch, client=client)
    store._storm_damper = damper
    error = exhaust_run(store, 'batch_admit', times=7)
    assert error.retry_after == pytest.approx(2.5)


def test_retry_n7_j0p5(monkeypatch):
    silence_chain_sleep(monkeypatch)
    client = StormDocsClient(abort_times=10**6)
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    store = default_store(monkeypatch, client=client)
    store._storm_damper = damper
    error = exhaust_run(store, 'batch_admit', times=7)
    assert error.retry_after == pytest.approx(3.0)


def test_retry_n7_j0p75(monkeypatch):
    silence_chain_sleep(monkeypatch)
    client = StormDocsClient(abort_times=10**6)
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    store = default_store(monkeypatch, client=client)
    store._storm_damper = damper
    error = exhaust_run(store, 'batch_admit', times=7)
    assert error.retry_after == pytest.approx(3.5)


def test_retry_n7_j1(monkeypatch):
    silence_chain_sleep(monkeypatch)
    client = StormDocsClient(abort_times=10**6)
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    store = default_store(monkeypatch, client=client)
    store._storm_damper = damper
    error = exhaust_run(store, 'batch_admit', times=7)
    assert error.retry_after == pytest.approx(4.0)


def test_retry_n8_j0(monkeypatch):
    silence_chain_sleep(monkeypatch)
    client = StormDocsClient(abort_times=10**6)
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    store = default_store(monkeypatch, client=client)
    store._storm_damper = damper
    error = exhaust_run(store, 'batch_admit', times=8)
    assert error.retry_after == pytest.approx(2.0)


def test_retry_n8_j0p25(monkeypatch):
    silence_chain_sleep(monkeypatch)
    client = StormDocsClient(abort_times=10**6)
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    store = default_store(monkeypatch, client=client)
    store._storm_damper = damper
    error = exhaust_run(store, 'batch_admit', times=8)
    assert error.retry_after == pytest.approx(2.5)


def test_retry_n8_j0p5(monkeypatch):
    silence_chain_sleep(monkeypatch)
    client = StormDocsClient(abort_times=10**6)
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    store = default_store(monkeypatch, client=client)
    store._storm_damper = damper
    error = exhaust_run(store, 'batch_admit', times=8)
    assert error.retry_after == pytest.approx(3.0)


def test_retry_n8_j0p75(monkeypatch):
    silence_chain_sleep(monkeypatch)
    client = StormDocsClient(abort_times=10**6)
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    store = default_store(monkeypatch, client=client)
    store._storm_damper = damper
    error = exhaust_run(store, 'batch_admit', times=8)
    assert error.retry_after == pytest.approx(3.5)


def test_retry_n8_j1(monkeypatch):
    silence_chain_sleep(monkeypatch)
    client = StormDocsClient(abort_times=10**6)
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    store = default_store(monkeypatch, client=client)
    store._storm_damper = damper
    error = exhaust_run(store, 'batch_admit', times=8)
    assert error.retry_after == pytest.approx(4.0)


def test_retry_n9_j0(monkeypatch):
    silence_chain_sleep(monkeypatch)
    client = StormDocsClient(abort_times=10**6)
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    store = default_store(monkeypatch, client=client)
    store._storm_damper = damper
    error = exhaust_run(store, 'batch_admit', times=9)
    assert error.retry_after == pytest.approx(2.0)


def test_retry_n9_j0p25(monkeypatch):
    silence_chain_sleep(monkeypatch)
    client = StormDocsClient(abort_times=10**6)
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    store = default_store(monkeypatch, client=client)
    store._storm_damper = damper
    error = exhaust_run(store, 'batch_admit', times=9)
    assert error.retry_after == pytest.approx(2.5)


def test_retry_n9_j0p5(monkeypatch):
    silence_chain_sleep(monkeypatch)
    client = StormDocsClient(abort_times=10**6)
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    store = default_store(monkeypatch, client=client)
    store._storm_damper = damper
    error = exhaust_run(store, 'batch_admit', times=9)
    assert error.retry_after == pytest.approx(3.0)


def test_retry_n9_j0p75(monkeypatch):
    silence_chain_sleep(monkeypatch)
    client = StormDocsClient(abort_times=10**6)
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    store = default_store(monkeypatch, client=client)
    store._storm_damper = damper
    error = exhaust_run(store, 'batch_admit', times=9)
    assert error.retry_after == pytest.approx(3.5)


def test_retry_n9_j1(monkeypatch):
    silence_chain_sleep(monkeypatch)
    client = StormDocsClient(abort_times=10**6)
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    store = default_store(monkeypatch, client=client)
    store._storm_damper = damper
    error = exhaust_run(store, 'batch_admit', times=9)
    assert error.retry_after == pytest.approx(4.0)


def test_retry_n10_j0(monkeypatch):
    silence_chain_sleep(monkeypatch)
    client = StormDocsClient(abort_times=10**6)
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    store = default_store(monkeypatch, client=client)
    store._storm_damper = damper
    error = exhaust_run(store, 'batch_admit', times=10)
    assert error.retry_after == pytest.approx(2.0)


def test_retry_n10_j0p25(monkeypatch):
    silence_chain_sleep(monkeypatch)
    client = StormDocsClient(abort_times=10**6)
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    store = default_store(monkeypatch, client=client)
    store._storm_damper = damper
    error = exhaust_run(store, 'batch_admit', times=10)
    assert error.retry_after == pytest.approx(2.5)


def test_retry_n10_j0p5(monkeypatch):
    silence_chain_sleep(monkeypatch)
    client = StormDocsClient(abort_times=10**6)
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    store = default_store(monkeypatch, client=client)
    store._storm_damper = damper
    error = exhaust_run(store, 'batch_admit', times=10)
    assert error.retry_after == pytest.approx(3.0)


def test_retry_n10_j0p75(monkeypatch):
    silence_chain_sleep(monkeypatch)
    client = StormDocsClient(abort_times=10**6)
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    store = default_store(monkeypatch, client=client)
    store._storm_damper = damper
    error = exhaust_run(store, 'batch_admit', times=10)
    assert error.retry_after == pytest.approx(3.5)


def test_retry_n10_j1(monkeypatch):
    silence_chain_sleep(monkeypatch)
    client = StormDocsClient(abort_times=10**6)
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    store = default_store(monkeypatch, client=client)
    store._storm_damper = damper
    error = exhaust_run(store, 'batch_admit', times=10)
    assert error.retry_after == pytest.approx(4.0)


def test_retry_n11_j0(monkeypatch):
    silence_chain_sleep(monkeypatch)
    client = StormDocsClient(abort_times=10**6)
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    store = default_store(monkeypatch, client=client)
    store._storm_damper = damper
    error = exhaust_run(store, 'batch_admit', times=11)
    assert error.retry_after == pytest.approx(2.0)


def test_retry_n11_j0p25(monkeypatch):
    silence_chain_sleep(monkeypatch)
    client = StormDocsClient(abort_times=10**6)
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    store = default_store(monkeypatch, client=client)
    store._storm_damper = damper
    error = exhaust_run(store, 'batch_admit', times=11)
    assert error.retry_after == pytest.approx(2.5)


def test_retry_n11_j0p5(monkeypatch):
    silence_chain_sleep(monkeypatch)
    client = StormDocsClient(abort_times=10**6)
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    store = default_store(monkeypatch, client=client)
    store._storm_damper = damper
    error = exhaust_run(store, 'batch_admit', times=11)
    assert error.retry_after == pytest.approx(3.0)


def test_retry_n11_j0p75(monkeypatch):
    silence_chain_sleep(monkeypatch)
    client = StormDocsClient(abort_times=10**6)
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    store = default_store(monkeypatch, client=client)
    store._storm_damper = damper
    error = exhaust_run(store, 'batch_admit', times=11)
    assert error.retry_after == pytest.approx(3.5)


def test_retry_n11_j1(monkeypatch):
    silence_chain_sleep(monkeypatch)
    client = StormDocsClient(abort_times=10**6)
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    store = default_store(monkeypatch, client=client)
    store._storm_damper = damper
    error = exhaust_run(store, 'batch_admit', times=11)
    assert error.retry_after == pytest.approx(4.0)


def test_retry_n12_j0(monkeypatch):
    silence_chain_sleep(monkeypatch)
    client = StormDocsClient(abort_times=10**6)
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    store = default_store(monkeypatch, client=client)
    store._storm_damper = damper
    error = exhaust_run(store, 'batch_admit', times=12)
    assert error.retry_after == pytest.approx(2.0)


def test_retry_n12_j0p25(monkeypatch):
    silence_chain_sleep(monkeypatch)
    client = StormDocsClient(abort_times=10**6)
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    store = default_store(monkeypatch, client=client)
    store._storm_damper = damper
    error = exhaust_run(store, 'batch_admit', times=12)
    assert error.retry_after == pytest.approx(2.5)


def test_retry_n12_j0p5(monkeypatch):
    silence_chain_sleep(monkeypatch)
    client = StormDocsClient(abort_times=10**6)
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    store = default_store(monkeypatch, client=client)
    store._storm_damper = damper
    error = exhaust_run(store, 'batch_admit', times=12)
    assert error.retry_after == pytest.approx(3.0)


def test_retry_n12_j0p75(monkeypatch):
    silence_chain_sleep(monkeypatch)
    client = StormDocsClient(abort_times=10**6)
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    store = default_store(monkeypatch, client=client)
    store._storm_damper = damper
    error = exhaust_run(store, 'batch_admit', times=12)
    assert error.retry_after == pytest.approx(3.5)


def test_retry_n12_j1(monkeypatch):
    silence_chain_sleep(monkeypatch)
    client = StormDocsClient(abort_times=10**6)
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    store = default_store(monkeypatch, client=client)
    store._storm_damper = damper
    error = exhaust_run(store, 'batch_admit', times=12)
    assert error.retry_after == pytest.approx(4.0)


def test_consultarm_r0p05():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.05)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    waited, generation = damper.consult('batch_admit', client=client)
    assert waited == pytest.approx(min(0.05, 1.0))
    assert clock.sleeps == [pytest.approx(min(0.05, 1.0))]
    applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(0.125)  # the spill adoption never arms the label
    assert clock.sleeps == [pytest.approx(min(0.05, 1.0))]


def test_consultarm_r0p0625():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.0625)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    waited, generation = damper.consult('batch_admit', client=client)
    assert waited == pytest.approx(min(0.0625, 1.0))
    assert clock.sleeps == [pytest.approx(min(0.0625, 1.0))]
    applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(0.125)  # the spill adoption never arms the label
    assert clock.sleeps == [pytest.approx(min(0.0625, 1.0))]


def test_consultarm_r0p125():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.125)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    waited, generation = damper.consult('batch_admit', client=client)
    assert waited == pytest.approx(min(0.125, 1.0))
    assert clock.sleeps == [pytest.approx(min(0.125, 1.0))]
    applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(0.125)  # the spill adoption never arms the label
    assert clock.sleeps == [pytest.approx(min(0.125, 1.0))]


def test_consultarm_r0p1875():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.1875)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    waited, generation = damper.consult('batch_admit', client=client)
    assert waited == pytest.approx(min(0.1875, 1.0))
    assert clock.sleeps == [pytest.approx(min(0.1875, 1.0))]
    applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(0.125)  # the spill adoption never arms the label
    assert clock.sleeps == [pytest.approx(min(0.1875, 1.0))]


def test_consultarm_r0p25():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.25)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    waited, generation = damper.consult('batch_admit', client=client)
    assert waited == pytest.approx(min(0.25, 1.0))
    assert clock.sleeps == [pytest.approx(min(0.25, 1.0))]
    applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(0.125)  # the spill adoption never arms the label
    assert clock.sleeps == [pytest.approx(min(0.25, 1.0))]


def test_consultarm_r0p3125():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.3125)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    waited, generation = damper.consult('batch_admit', client=client)
    assert waited == pytest.approx(min(0.3125, 1.0))
    assert clock.sleeps == [pytest.approx(min(0.3125, 1.0))]
    applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(0.125)  # the spill adoption never arms the label
    assert clock.sleeps == [pytest.approx(min(0.3125, 1.0))]


def test_consultarm_r0p375():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.375)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    waited, generation = damper.consult('batch_admit', client=client)
    assert waited == pytest.approx(min(0.375, 1.0))
    assert clock.sleeps == [pytest.approx(min(0.375, 1.0))]
    applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(0.125)  # the spill adoption never arms the label
    assert clock.sleeps == [pytest.approx(min(0.375, 1.0))]


def test_consultarm_r0p4375():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.4375)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    waited, generation = damper.consult('batch_admit', client=client)
    assert waited == pytest.approx(min(0.4375, 1.0))
    assert clock.sleeps == [pytest.approx(min(0.4375, 1.0))]
    applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(0.125)  # the spill adoption never arms the label
    assert clock.sleeps == [pytest.approx(min(0.4375, 1.0))]


def test_consultarm_r0p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.5)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    waited, generation = damper.consult('batch_admit', client=client)
    assert waited == pytest.approx(min(0.5, 1.0))
    assert clock.sleeps == [pytest.approx(min(0.5, 1.0))]
    applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(0.125)  # the spill adoption never arms the label
    assert clock.sleeps == [pytest.approx(min(0.5, 1.0))]


def test_consultarm_r0p625():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.625)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    waited, generation = damper.consult('batch_admit', client=client)
    assert waited == pytest.approx(min(0.625, 1.0))
    assert clock.sleeps == [pytest.approx(min(0.625, 1.0))]
    applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(0.125)  # the spill adoption never arms the label
    assert clock.sleeps == [pytest.approx(min(0.625, 1.0))]


def test_consultarm_r0p75():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.75)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    waited, generation = damper.consult('batch_admit', client=client)
    assert waited == pytest.approx(min(0.75, 1.0))
    assert clock.sleeps == [pytest.approx(min(0.75, 1.0))]
    applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(0.125)  # the spill adoption never arms the label
    assert clock.sleeps == [pytest.approx(min(0.75, 1.0))]


def test_consultarm_r0p875():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.875)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    waited, generation = damper.consult('batch_admit', client=client)
    assert waited == pytest.approx(min(0.875, 1.0))
    assert clock.sleeps == [pytest.approx(min(0.875, 1.0))]
    applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(0.125)  # the spill adoption never arms the label
    assert clock.sleeps == [pytest.approx(min(0.875, 1.0))]


def test_consultarm_r1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 1.0)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    waited, generation = damper.consult('batch_admit', client=client)
    assert waited == pytest.approx(min(1.0, 1.0))
    assert clock.sleeps == [pytest.approx(min(1.0, 1.0))]
    applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(0.125)  # the spill adoption never arms the label
    assert clock.sleeps == [pytest.approx(min(1.0, 1.0))]


def test_consultarm_r1p25():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 1.25)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    waited, generation = damper.consult('batch_admit', client=client)
    assert waited == pytest.approx(min(1.25, 1.0))
    assert clock.sleeps == [pytest.approx(min(1.25, 1.0))]
    applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(0.125)  # the spill adoption never arms the label
    assert clock.sleeps == [pytest.approx(min(1.25, 1.0))]


def test_consultarm_r1p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 1.5)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    waited, generation = damper.consult('batch_admit', client=client)
    assert waited == pytest.approx(min(1.5, 1.0))
    assert clock.sleeps == [pytest.approx(min(1.5, 1.0))]
    applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(0.125)  # the spill adoption never arms the label
    assert clock.sleeps == [pytest.approx(min(1.5, 1.0))]


def test_consultarm_r1p75():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 1.75)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    waited, generation = damper.consult('batch_admit', client=client)
    assert waited == pytest.approx(min(1.75, 1.0))
    assert clock.sleeps == [pytest.approx(min(1.75, 1.0))]
    applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(0.125)  # the spill adoption never arms the label
    assert clock.sleeps == [pytest.approx(min(1.75, 1.0))]


def test_consultarm_r2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 2.0)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    waited, generation = damper.consult('batch_admit', client=client)
    assert waited == pytest.approx(min(2.0, 1.0))
    assert clock.sleeps == [pytest.approx(min(2.0, 1.0))]
    applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(0.125)  # the spill adoption never arms the label
    assert clock.sleeps == [pytest.approx(min(2.0, 1.0))]


def test_consultarm_r2p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 2.5)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    waited, generation = damper.consult('batch_admit', client=client)
    assert waited == pytest.approx(min(2.5, 1.0))
    assert clock.sleeps == [pytest.approx(min(2.5, 1.0))]
    applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(0.125)  # the spill adoption never arms the label
    assert clock.sleeps == [pytest.approx(min(2.5, 1.0))]


def test_consultarm_r3():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 3.0)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    waited, generation = damper.consult('batch_admit', client=client)
    assert waited == pytest.approx(min(3.0, 1.0))
    assert clock.sleeps == [pytest.approx(min(3.0, 1.0))]
    applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(0.125)  # the spill adoption never arms the label
    assert clock.sleeps == [pytest.approx(min(3.0, 1.0))]


def test_consultarm_r3p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 3.5)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    waited, generation = damper.consult('batch_admit', client=client)
    assert waited == pytest.approx(min(3.5, 1.0))
    assert clock.sleeps == [pytest.approx(min(3.5, 1.0))]
    applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(0.125)  # the spill adoption never arms the label
    assert clock.sleeps == [pytest.approx(min(3.5, 1.0))]


def test_consultarm_r4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    waited, generation = damper.consult('batch_admit', client=client)
    assert waited == pytest.approx(min(4.0, 1.0))
    assert clock.sleeps == [pytest.approx(min(4.0, 1.0))]
    applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(0.125)  # the spill adoption never arms the label
    assert clock.sleeps == [pytest.approx(min(4.0, 1.0))]


def test_consultarm_r4p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.5)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    waited, generation = damper.consult('batch_admit', client=client)
    assert waited == pytest.approx(min(4.5, 1.0))
    assert clock.sleeps == [pytest.approx(min(4.5, 1.0))]
    applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(0.125)  # the spill adoption never arms the label
    assert clock.sleeps == [pytest.approx(min(4.5, 1.0))]


def test_shard_a00_b00_j0_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_00', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_00', client=client)
    assert waited == pytest.approx(0.125)  # the label's own window is waited in full
    assert clock.sleeps == [pytest.approx(0.125)]


def test_shard_a00_b00_j0_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_00', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_00', client=client)
    assert waited == pytest.approx(0.25)  # the label's own window is waited in full
    assert clock.sleeps == [pytest.approx(0.25)]


def test_shard_a00_b00_j0p25_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_00', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_00', client=client)
    assert waited == pytest.approx(0.15625)  # the label's own window is waited in full
    assert clock.sleeps == [pytest.approx(0.15625)]


def test_shard_a00_b00_j0p25_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_00', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_00', client=client)
    assert waited == pytest.approx(0.3125)  # the label's own window is waited in full
    assert clock.sleeps == [pytest.approx(0.3125)]


def test_shard_a00_b00_j0p5_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_00', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_00', client=client)
    assert waited == pytest.approx(0.1875)  # the label's own window is waited in full
    assert clock.sleeps == [pytest.approx(0.1875)]


def test_shard_a00_b00_j0p5_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_00', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_00', client=client)
    assert waited == pytest.approx(0.375)  # the label's own window is waited in full
    assert clock.sleeps == [pytest.approx(0.375)]


def test_shard_a00_b00_j0p75_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_00', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_00', client=client)
    assert waited == pytest.approx(0.21875)  # the label's own window is waited in full
    assert clock.sleeps == [pytest.approx(0.21875)]


def test_shard_a00_b00_j0p75_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_00', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_00', client=client)
    assert waited == pytest.approx(0.4375)  # the label's own window is waited in full
    assert clock.sleeps == [pytest.approx(0.4375)]


def test_shard_a00_b00_j1_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_00', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_00', client=client)
    assert waited == pytest.approx(0.25)  # the label's own window is waited in full
    assert clock.sleeps == [pytest.approx(0.25)]


def test_shard_a00_b00_j1_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_00', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_00', client=client)
    assert waited == pytest.approx(0.5)  # the label's own window is waited in full
    assert clock.sleeps == [pytest.approx(0.5)]


def test_shard_a00_b01_j0_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_00', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_01', client=client)
    assert waited == pytest.approx(0.125)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.125)]


def test_shard_a00_b01_j0_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_00', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_01', client=client)
    assert waited == pytest.approx(0.25)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.25)]


def test_shard_a00_b01_j0p25_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_00', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_01', client=client)
    assert waited == pytest.approx(0.15625)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.15625)]


def test_shard_a00_b01_j0p25_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_00', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_01', client=client)
    assert waited == pytest.approx(0.3125)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.3125)]


def test_shard_a00_b01_j0p5_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_00', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_01', client=client)
    assert waited == pytest.approx(0.1875)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.1875)]


def test_shard_a00_b01_j0p5_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_00', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_01', client=client)
    assert waited == pytest.approx(0.375)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.375)]


def test_shard_a00_b01_j0p75_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_00', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_01', client=client)
    assert waited == pytest.approx(0.21875)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.21875)]


def test_shard_a00_b01_j0p75_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_00', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_01', client=client)
    assert waited == pytest.approx(0.4375)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.4375)]


def test_shard_a00_b01_j1_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_00', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_01', client=client)
    assert waited == pytest.approx(0.25)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.25)]


def test_shard_a00_b01_j1_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_00', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_01', client=client)
    assert waited == pytest.approx(0.5)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.5)]


def test_shard_a00_b02_j0_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_00', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_02', client=client)
    assert waited == pytest.approx(0.125)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.125)]


def test_shard_a00_b02_j0_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_00', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_02', client=client)
    assert waited == pytest.approx(0.25)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.25)]


def test_shard_a00_b02_j0p25_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_00', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_02', client=client)
    assert waited == pytest.approx(0.15625)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.15625)]


def test_shard_a00_b02_j0p25_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_00', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_02', client=client)
    assert waited == pytest.approx(0.3125)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.3125)]


def test_shard_a00_b02_j0p5_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_00', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_02', client=client)
    assert waited == pytest.approx(0.1875)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.1875)]


def test_shard_a00_b02_j0p5_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_00', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_02', client=client)
    assert waited == pytest.approx(0.375)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.375)]


def test_shard_a00_b02_j0p75_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_00', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_02', client=client)
    assert waited == pytest.approx(0.21875)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.21875)]


def test_shard_a00_b02_j0p75_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_00', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_02', client=client)
    assert waited == pytest.approx(0.4375)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.4375)]


def test_shard_a00_b02_j1_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_00', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_02', client=client)
    assert waited == pytest.approx(0.25)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.25)]


def test_shard_a00_b02_j1_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_00', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_02', client=client)
    assert waited == pytest.approx(0.5)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.5)]


def test_shard_a00_b03_j0_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_00', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_03', client=client)
    assert waited == pytest.approx(0.125)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.125)]


def test_shard_a00_b03_j0_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_00', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_03', client=client)
    assert waited == pytest.approx(0.25)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.25)]


def test_shard_a00_b03_j0p25_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_00', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_03', client=client)
    assert waited == pytest.approx(0.15625)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.15625)]


def test_shard_a00_b03_j0p25_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_00', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_03', client=client)
    assert waited == pytest.approx(0.3125)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.3125)]


def test_shard_a00_b03_j0p5_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_00', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_03', client=client)
    assert waited == pytest.approx(0.1875)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.1875)]


def test_shard_a00_b03_j0p5_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_00', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_03', client=client)
    assert waited == pytest.approx(0.375)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.375)]


def test_shard_a00_b03_j0p75_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_00', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_03', client=client)
    assert waited == pytest.approx(0.21875)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.21875)]


def test_shard_a00_b03_j0p75_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_00', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_03', client=client)
    assert waited == pytest.approx(0.4375)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.4375)]


def test_shard_a00_b03_j1_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_00', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_03', client=client)
    assert waited == pytest.approx(0.25)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.25)]


def test_shard_a00_b03_j1_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_00', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_03', client=client)
    assert waited == pytest.approx(0.5)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.5)]


def test_shard_a00_b04_j0_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_00', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_04', client=client)
    assert waited == pytest.approx(0.125)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.125)]


def test_shard_a00_b04_j0_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_00', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_04', client=client)
    assert waited == pytest.approx(0.25)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.25)]


def test_shard_a00_b04_j0p25_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_00', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_04', client=client)
    assert waited == pytest.approx(0.15625)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.15625)]


def test_shard_a00_b04_j0p25_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_00', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_04', client=client)
    assert waited == pytest.approx(0.3125)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.3125)]


def test_shard_a00_b04_j0p5_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_00', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_04', client=client)
    assert waited == pytest.approx(0.1875)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.1875)]


def test_shard_a00_b04_j0p5_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_00', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_04', client=client)
    assert waited == pytest.approx(0.375)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.375)]


def test_shard_a00_b04_j0p75_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_00', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_04', client=client)
    assert waited == pytest.approx(0.21875)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.21875)]


def test_shard_a00_b04_j0p75_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_00', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_04', client=client)
    assert waited == pytest.approx(0.4375)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.4375)]


def test_shard_a00_b04_j1_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_00', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_04', client=client)
    assert waited == pytest.approx(0.25)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.25)]


def test_shard_a00_b04_j1_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_00', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_04', client=client)
    assert waited == pytest.approx(0.5)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.5)]


def test_shard_a00_b05_j0_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_00', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_05', client=client)
    assert waited == pytest.approx(0.125)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.125)]


def test_shard_a00_b05_j0_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_00', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_05', client=client)
    assert waited == pytest.approx(0.25)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.25)]


def test_shard_a00_b05_j0p25_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_00', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_05', client=client)
    assert waited == pytest.approx(0.15625)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.15625)]


def test_shard_a00_b05_j0p25_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_00', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_05', client=client)
    assert waited == pytest.approx(0.3125)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.3125)]


def test_shard_a00_b05_j0p5_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_00', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_05', client=client)
    assert waited == pytest.approx(0.1875)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.1875)]


def test_shard_a00_b05_j0p5_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_00', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_05', client=client)
    assert waited == pytest.approx(0.375)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.375)]


def test_shard_a00_b05_j0p75_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_00', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_05', client=client)
    assert waited == pytest.approx(0.21875)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.21875)]


def test_shard_a00_b05_j0p75_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_00', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_05', client=client)
    assert waited == pytest.approx(0.4375)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.4375)]


def test_shard_a00_b05_j1_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_00', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_05', client=client)
    assert waited == pytest.approx(0.25)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.25)]


def test_shard_a00_b05_j1_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_00', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_05', client=client)
    assert waited == pytest.approx(0.5)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.5)]


def test_shard_a00_b06_j0_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_00', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_06', client=client)
    assert waited == pytest.approx(0.125)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.125)]


def test_shard_a00_b06_j0_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_00', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_06', client=client)
    assert waited == pytest.approx(0.25)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.25)]


def test_shard_a00_b06_j0p25_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_00', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_06', client=client)
    assert waited == pytest.approx(0.15625)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.15625)]


def test_shard_a00_b06_j0p25_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_00', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_06', client=client)
    assert waited == pytest.approx(0.3125)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.3125)]


def test_shard_a00_b06_j0p5_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_00', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_06', client=client)
    assert waited == pytest.approx(0.1875)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.1875)]


def test_shard_a00_b06_j0p5_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_00', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_06', client=client)
    assert waited == pytest.approx(0.375)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.375)]


def test_shard_a00_b06_j0p75_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_00', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_06', client=client)
    assert waited == pytest.approx(0.21875)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.21875)]


def test_shard_a00_b06_j0p75_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_00', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_06', client=client)
    assert waited == pytest.approx(0.4375)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.4375)]


def test_shard_a00_b06_j1_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_00', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_06', client=client)
    assert waited == pytest.approx(0.25)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.25)]


def test_shard_a00_b06_j1_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_00', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_06', client=client)
    assert waited == pytest.approx(0.5)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.5)]


def test_shard_a00_b07_j0_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_00', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_07', client=client)
    assert waited == pytest.approx(0.125)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.125)]


def test_shard_a00_b07_j0_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_00', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_07', client=client)
    assert waited == pytest.approx(0.25)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.25)]


def test_shard_a00_b07_j0p25_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_00', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_07', client=client)
    assert waited == pytest.approx(0.15625)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.15625)]


def test_shard_a00_b07_j0p25_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_00', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_07', client=client)
    assert waited == pytest.approx(0.3125)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.3125)]


def test_shard_a00_b07_j0p5_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_00', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_07', client=client)
    assert waited == pytest.approx(0.1875)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.1875)]


def test_shard_a00_b07_j0p5_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_00', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_07', client=client)
    assert waited == pytest.approx(0.375)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.375)]


def test_shard_a00_b07_j0p75_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_00', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_07', client=client)
    assert waited == pytest.approx(0.21875)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.21875)]


def test_shard_a00_b07_j0p75_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_00', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_07', client=client)
    assert waited == pytest.approx(0.4375)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.4375)]


def test_shard_a00_b07_j1_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_00', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_07', client=client)
    assert waited == pytest.approx(0.25)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.25)]


def test_shard_a00_b07_j1_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_00', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_07', client=client)
    assert waited == pytest.approx(0.5)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.5)]


def test_shard_a01_b00_j0_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_01', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_00', client=client)
    assert waited == pytest.approx(0.125)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.125)]


def test_shard_a01_b00_j0_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_01', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_00', client=client)
    assert waited == pytest.approx(0.25)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.25)]


def test_shard_a01_b00_j0p25_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_01', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_00', client=client)
    assert waited == pytest.approx(0.15625)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.15625)]


def test_shard_a01_b00_j0p25_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_01', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_00', client=client)
    assert waited == pytest.approx(0.3125)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.3125)]


def test_shard_a01_b00_j0p5_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_01', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_00', client=client)
    assert waited == pytest.approx(0.1875)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.1875)]


def test_shard_a01_b00_j0p5_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_01', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_00', client=client)
    assert waited == pytest.approx(0.375)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.375)]


def test_shard_a01_b00_j0p75_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_01', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_00', client=client)
    assert waited == pytest.approx(0.21875)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.21875)]


def test_shard_a01_b00_j0p75_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_01', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_00', client=client)
    assert waited == pytest.approx(0.4375)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.4375)]


def test_shard_a01_b00_j1_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_01', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_00', client=client)
    assert waited == pytest.approx(0.25)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.25)]


def test_shard_a01_b00_j1_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_01', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_00', client=client)
    assert waited == pytest.approx(0.5)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.5)]


def test_shard_a01_b01_j0_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_01', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_01', client=client)
    assert waited == pytest.approx(0.125)  # the label's own window is waited in full
    assert clock.sleeps == [pytest.approx(0.125)]


def test_shard_a01_b01_j0_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_01', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_01', client=client)
    assert waited == pytest.approx(0.25)  # the label's own window is waited in full
    assert clock.sleeps == [pytest.approx(0.25)]


def test_shard_a01_b01_j0p25_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_01', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_01', client=client)
    assert waited == pytest.approx(0.15625)  # the label's own window is waited in full
    assert clock.sleeps == [pytest.approx(0.15625)]


def test_shard_a01_b01_j0p25_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_01', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_01', client=client)
    assert waited == pytest.approx(0.3125)  # the label's own window is waited in full
    assert clock.sleeps == [pytest.approx(0.3125)]


def test_shard_a01_b01_j0p5_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_01', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_01', client=client)
    assert waited == pytest.approx(0.1875)  # the label's own window is waited in full
    assert clock.sleeps == [pytest.approx(0.1875)]


def test_shard_a01_b01_j0p5_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_01', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_01', client=client)
    assert waited == pytest.approx(0.375)  # the label's own window is waited in full
    assert clock.sleeps == [pytest.approx(0.375)]


def test_shard_a01_b01_j0p75_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_01', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_01', client=client)
    assert waited == pytest.approx(0.21875)  # the label's own window is waited in full
    assert clock.sleeps == [pytest.approx(0.21875)]


def test_shard_a01_b01_j0p75_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_01', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_01', client=client)
    assert waited == pytest.approx(0.4375)  # the label's own window is waited in full
    assert clock.sleeps == [pytest.approx(0.4375)]


def test_shard_a01_b01_j1_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_01', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_01', client=client)
    assert waited == pytest.approx(0.25)  # the label's own window is waited in full
    assert clock.sleeps == [pytest.approx(0.25)]


def test_shard_a01_b01_j1_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_01', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_01', client=client)
    assert waited == pytest.approx(0.5)  # the label's own window is waited in full
    assert clock.sleeps == [pytest.approx(0.5)]


def test_shard_a01_b02_j0_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_01', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_02', client=client)
    assert waited == pytest.approx(0.125)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.125)]


def test_shard_a01_b02_j0_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_01', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_02', client=client)
    assert waited == pytest.approx(0.25)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.25)]


def test_shard_a01_b02_j0p25_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_01', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_02', client=client)
    assert waited == pytest.approx(0.15625)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.15625)]


def test_shard_a01_b02_j0p25_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_01', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_02', client=client)
    assert waited == pytest.approx(0.3125)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.3125)]


def test_shard_a01_b02_j0p5_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_01', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_02', client=client)
    assert waited == pytest.approx(0.1875)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.1875)]


def test_shard_a01_b02_j0p5_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_01', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_02', client=client)
    assert waited == pytest.approx(0.375)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.375)]


def test_shard_a01_b02_j0p75_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_01', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_02', client=client)
    assert waited == pytest.approx(0.21875)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.21875)]


def test_shard_a01_b02_j0p75_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_01', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_02', client=client)
    assert waited == pytest.approx(0.4375)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.4375)]


def test_shard_a01_b02_j1_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_01', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_02', client=client)
    assert waited == pytest.approx(0.25)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.25)]


def test_shard_a01_b02_j1_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_01', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_02', client=client)
    assert waited == pytest.approx(0.5)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.5)]


def test_shard_a01_b03_j0_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_01', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_03', client=client)
    assert waited == pytest.approx(0.125)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.125)]


def test_shard_a01_b03_j0_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_01', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_03', client=client)
    assert waited == pytest.approx(0.25)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.25)]


def test_shard_a01_b03_j0p25_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_01', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_03', client=client)
    assert waited == pytest.approx(0.15625)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.15625)]


def test_shard_a01_b03_j0p25_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_01', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_03', client=client)
    assert waited == pytest.approx(0.3125)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.3125)]


def test_shard_a01_b03_j0p5_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_01', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_03', client=client)
    assert waited == pytest.approx(0.1875)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.1875)]


def test_shard_a01_b03_j0p5_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_01', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_03', client=client)
    assert waited == pytest.approx(0.375)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.375)]


def test_shard_a01_b03_j0p75_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_01', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_03', client=client)
    assert waited == pytest.approx(0.21875)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.21875)]


def test_shard_a01_b03_j0p75_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_01', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_03', client=client)
    assert waited == pytest.approx(0.4375)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.4375)]


def test_shard_a01_b03_j1_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_01', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_03', client=client)
    assert waited == pytest.approx(0.25)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.25)]


def test_shard_a01_b03_j1_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_01', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_03', client=client)
    assert waited == pytest.approx(0.5)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.5)]


def test_shard_a01_b04_j0_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_01', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_04', client=client)
    assert waited == pytest.approx(0.125)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.125)]


def test_shard_a01_b04_j0_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_01', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_04', client=client)
    assert waited == pytest.approx(0.25)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.25)]


def test_shard_a01_b04_j0p25_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_01', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_04', client=client)
    assert waited == pytest.approx(0.15625)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.15625)]


def test_shard_a01_b04_j0p25_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_01', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_04', client=client)
    assert waited == pytest.approx(0.3125)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.3125)]


def test_shard_a01_b04_j0p5_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_01', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_04', client=client)
    assert waited == pytest.approx(0.1875)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.1875)]


def test_shard_a01_b04_j0p5_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_01', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_04', client=client)
    assert waited == pytest.approx(0.375)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.375)]


def test_shard_a01_b04_j0p75_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_01', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_04', client=client)
    assert waited == pytest.approx(0.21875)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.21875)]


def test_shard_a01_b04_j0p75_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_01', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_04', client=client)
    assert waited == pytest.approx(0.4375)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.4375)]


def test_shard_a01_b04_j1_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_01', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_04', client=client)
    assert waited == pytest.approx(0.25)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.25)]


def test_shard_a01_b04_j1_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_01', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_04', client=client)
    assert waited == pytest.approx(0.5)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.5)]


def test_shard_a01_b05_j0_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_01', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_05', client=client)
    assert waited == pytest.approx(0.125)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.125)]


def test_shard_a01_b05_j0_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_01', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_05', client=client)
    assert waited == pytest.approx(0.25)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.25)]


def test_shard_a01_b05_j0p25_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_01', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_05', client=client)
    assert waited == pytest.approx(0.15625)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.15625)]


def test_shard_a01_b05_j0p25_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_01', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_05', client=client)
    assert waited == pytest.approx(0.3125)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.3125)]


def test_shard_a01_b05_j0p5_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_01', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_05', client=client)
    assert waited == pytest.approx(0.1875)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.1875)]


def test_shard_a01_b05_j0p5_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_01', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_05', client=client)
    assert waited == pytest.approx(0.375)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.375)]


def test_shard_a01_b05_j0p75_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_01', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_05', client=client)
    assert waited == pytest.approx(0.21875)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.21875)]


def test_shard_a01_b05_j0p75_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_01', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_05', client=client)
    assert waited == pytest.approx(0.4375)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.4375)]


def test_shard_a01_b05_j1_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_01', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_05', client=client)
    assert waited == pytest.approx(0.25)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.25)]


def test_shard_a01_b05_j1_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_01', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_05', client=client)
    assert waited == pytest.approx(0.5)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.5)]


def test_shard_a01_b06_j0_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_01', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_06', client=client)
    assert waited == pytest.approx(0.125)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.125)]


def test_shard_a01_b06_j0_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_01', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_06', client=client)
    assert waited == pytest.approx(0.25)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.25)]


def test_shard_a01_b06_j0p25_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_01', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_06', client=client)
    assert waited == pytest.approx(0.15625)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.15625)]


def test_shard_a01_b06_j0p25_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_01', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_06', client=client)
    assert waited == pytest.approx(0.3125)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.3125)]


def test_shard_a01_b06_j0p5_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_01', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_06', client=client)
    assert waited == pytest.approx(0.1875)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.1875)]


def test_shard_a01_b06_j0p5_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_01', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_06', client=client)
    assert waited == pytest.approx(0.375)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.375)]


def test_shard_a01_b06_j0p75_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_01', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_06', client=client)
    assert waited == pytest.approx(0.21875)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.21875)]


def test_shard_a01_b06_j0p75_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_01', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_06', client=client)
    assert waited == pytest.approx(0.4375)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.4375)]


def test_shard_a01_b06_j1_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_01', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_06', client=client)
    assert waited == pytest.approx(0.25)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.25)]


def test_shard_a01_b06_j1_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_01', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_06', client=client)
    assert waited == pytest.approx(0.5)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.5)]


def test_shard_a01_b07_j0_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_01', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_07', client=client)
    assert waited == pytest.approx(0.125)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.125)]


def test_shard_a01_b07_j0_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_01', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_07', client=client)
    assert waited == pytest.approx(0.25)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.25)]


def test_shard_a01_b07_j0p25_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_01', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_07', client=client)
    assert waited == pytest.approx(0.15625)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.15625)]


def test_shard_a01_b07_j0p25_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_01', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_07', client=client)
    assert waited == pytest.approx(0.3125)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.3125)]


def test_shard_a01_b07_j0p5_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_01', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_07', client=client)
    assert waited == pytest.approx(0.1875)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.1875)]


def test_shard_a01_b07_j0p5_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_01', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_07', client=client)
    assert waited == pytest.approx(0.375)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.375)]


def test_shard_a01_b07_j0p75_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_01', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_07', client=client)
    assert waited == pytest.approx(0.21875)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.21875)]


def test_shard_a01_b07_j0p75_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_01', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_07', client=client)
    assert waited == pytest.approx(0.4375)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.4375)]


def test_shard_a01_b07_j1_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_01', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_07', client=client)
    assert waited == pytest.approx(0.25)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.25)]


def test_shard_a01_b07_j1_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_01', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_07', client=client)
    assert waited == pytest.approx(0.5)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.5)]


def test_shard_a02_b00_j0_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_02', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_00', client=client)
    assert waited == pytest.approx(0.125)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.125)]


def test_shard_a02_b00_j0_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_02', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_00', client=client)
    assert waited == pytest.approx(0.25)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.25)]


def test_shard_a02_b00_j0p25_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_02', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_00', client=client)
    assert waited == pytest.approx(0.15625)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.15625)]


def test_shard_a02_b00_j0p25_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_02', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_00', client=client)
    assert waited == pytest.approx(0.3125)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.3125)]


def test_shard_a02_b00_j0p5_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_02', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_00', client=client)
    assert waited == pytest.approx(0.1875)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.1875)]


def test_shard_a02_b00_j0p5_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_02', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_00', client=client)
    assert waited == pytest.approx(0.375)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.375)]


def test_shard_a02_b00_j0p75_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_02', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_00', client=client)
    assert waited == pytest.approx(0.21875)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.21875)]


def test_shard_a02_b00_j0p75_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_02', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_00', client=client)
    assert waited == pytest.approx(0.4375)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.4375)]


def test_shard_a02_b00_j1_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_02', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_00', client=client)
    assert waited == pytest.approx(0.25)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.25)]


def test_shard_a02_b00_j1_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_02', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_00', client=client)
    assert waited == pytest.approx(0.5)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.5)]


def test_shard_a02_b01_j0_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_02', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_01', client=client)
    assert waited == pytest.approx(0.125)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.125)]


def test_shard_a02_b01_j0_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_02', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_01', client=client)
    assert waited == pytest.approx(0.25)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.25)]


def test_shard_a02_b01_j0p25_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_02', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_01', client=client)
    assert waited == pytest.approx(0.15625)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.15625)]


def test_shard_a02_b01_j0p25_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_02', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_01', client=client)
    assert waited == pytest.approx(0.3125)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.3125)]


def test_shard_a02_b01_j0p5_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_02', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_01', client=client)
    assert waited == pytest.approx(0.1875)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.1875)]


def test_shard_a02_b01_j0p5_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_02', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_01', client=client)
    assert waited == pytest.approx(0.375)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.375)]


def test_shard_a02_b01_j0p75_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_02', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_01', client=client)
    assert waited == pytest.approx(0.21875)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.21875)]


def test_shard_a02_b01_j0p75_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_02', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_01', client=client)
    assert waited == pytest.approx(0.4375)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.4375)]


def test_shard_a02_b01_j1_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_02', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_01', client=client)
    assert waited == pytest.approx(0.25)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.25)]


def test_shard_a02_b01_j1_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_02', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_01', client=client)
    assert waited == pytest.approx(0.5)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.5)]


def test_shard_a02_b02_j0_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_02', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_02', client=client)
    assert waited == pytest.approx(0.125)  # the label's own window is waited in full
    assert clock.sleeps == [pytest.approx(0.125)]


def test_shard_a02_b02_j0_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_02', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_02', client=client)
    assert waited == pytest.approx(0.25)  # the label's own window is waited in full
    assert clock.sleeps == [pytest.approx(0.25)]


def test_shard_a02_b02_j0p25_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_02', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_02', client=client)
    assert waited == pytest.approx(0.15625)  # the label's own window is waited in full
    assert clock.sleeps == [pytest.approx(0.15625)]


def test_shard_a02_b02_j0p25_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_02', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_02', client=client)
    assert waited == pytest.approx(0.3125)  # the label's own window is waited in full
    assert clock.sleeps == [pytest.approx(0.3125)]


def test_shard_a02_b02_j0p5_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_02', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_02', client=client)
    assert waited == pytest.approx(0.1875)  # the label's own window is waited in full
    assert clock.sleeps == [pytest.approx(0.1875)]


def test_shard_a02_b02_j0p5_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_02', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_02', client=client)
    assert waited == pytest.approx(0.375)  # the label's own window is waited in full
    assert clock.sleeps == [pytest.approx(0.375)]


def test_shard_a02_b02_j0p75_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_02', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_02', client=client)
    assert waited == pytest.approx(0.21875)  # the label's own window is waited in full
    assert clock.sleeps == [pytest.approx(0.21875)]


def test_shard_a02_b02_j0p75_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_02', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_02', client=client)
    assert waited == pytest.approx(0.4375)  # the label's own window is waited in full
    assert clock.sleeps == [pytest.approx(0.4375)]


def test_shard_a02_b02_j1_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_02', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_02', client=client)
    assert waited == pytest.approx(0.25)  # the label's own window is waited in full
    assert clock.sleeps == [pytest.approx(0.25)]


def test_shard_a02_b02_j1_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_02', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_02', client=client)
    assert waited == pytest.approx(0.5)  # the label's own window is waited in full
    assert clock.sleeps == [pytest.approx(0.5)]


def test_shard_a02_b03_j0_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_02', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_03', client=client)
    assert waited == pytest.approx(0.125)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.125)]


def test_shard_a02_b03_j0_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_02', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_03', client=client)
    assert waited == pytest.approx(0.25)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.25)]


def test_shard_a02_b03_j0p25_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_02', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_03', client=client)
    assert waited == pytest.approx(0.15625)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.15625)]


def test_shard_a02_b03_j0p25_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_02', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_03', client=client)
    assert waited == pytest.approx(0.3125)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.3125)]


def test_shard_a02_b03_j0p5_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_02', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_03', client=client)
    assert waited == pytest.approx(0.1875)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.1875)]


def test_shard_a02_b03_j0p5_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_02', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_03', client=client)
    assert waited == pytest.approx(0.375)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.375)]


def test_shard_a02_b03_j0p75_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_02', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_03', client=client)
    assert waited == pytest.approx(0.21875)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.21875)]


def test_shard_a02_b03_j0p75_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_02', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_03', client=client)
    assert waited == pytest.approx(0.4375)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.4375)]


def test_shard_a02_b03_j1_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_02', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_03', client=client)
    assert waited == pytest.approx(0.25)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.25)]


def test_shard_a02_b03_j1_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_02', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_03', client=client)
    assert waited == pytest.approx(0.5)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.5)]


def test_shard_a02_b04_j0_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_02', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_04', client=client)
    assert waited == pytest.approx(0.125)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.125)]


def test_shard_a02_b04_j0_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_02', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_04', client=client)
    assert waited == pytest.approx(0.25)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.25)]


def test_shard_a02_b04_j0p25_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_02', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_04', client=client)
    assert waited == pytest.approx(0.15625)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.15625)]


def test_shard_a02_b04_j0p25_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_02', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_04', client=client)
    assert waited == pytest.approx(0.3125)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.3125)]


def test_shard_a02_b04_j0p5_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_02', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_04', client=client)
    assert waited == pytest.approx(0.1875)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.1875)]


def test_shard_a02_b04_j0p5_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_02', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_04', client=client)
    assert waited == pytest.approx(0.375)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.375)]


def test_shard_a02_b04_j0p75_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_02', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_04', client=client)
    assert waited == pytest.approx(0.21875)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.21875)]


def test_shard_a02_b04_j0p75_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_02', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_04', client=client)
    assert waited == pytest.approx(0.4375)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.4375)]


def test_shard_a02_b04_j1_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_02', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_04', client=client)
    assert waited == pytest.approx(0.25)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.25)]


def test_shard_a02_b04_j1_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_02', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_04', client=client)
    assert waited == pytest.approx(0.5)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.5)]


def test_shard_a02_b05_j0_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_02', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_05', client=client)
    assert waited == pytest.approx(0.125)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.125)]


def test_shard_a02_b05_j0_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_02', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_05', client=client)
    assert waited == pytest.approx(0.25)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.25)]


def test_shard_a02_b05_j0p25_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_02', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_05', client=client)
    assert waited == pytest.approx(0.15625)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.15625)]


def test_shard_a02_b05_j0p25_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_02', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_05', client=client)
    assert waited == pytest.approx(0.3125)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.3125)]


def test_shard_a02_b05_j0p5_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_02', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_05', client=client)
    assert waited == pytest.approx(0.1875)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.1875)]


def test_shard_a02_b05_j0p5_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_02', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_05', client=client)
    assert waited == pytest.approx(0.375)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.375)]


def test_shard_a02_b05_j0p75_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_02', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_05', client=client)
    assert waited == pytest.approx(0.21875)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.21875)]


def test_shard_a02_b05_j0p75_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_02', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_05', client=client)
    assert waited == pytest.approx(0.4375)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.4375)]


def test_shard_a02_b05_j1_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_02', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_05', client=client)
    assert waited == pytest.approx(0.25)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.25)]


def test_shard_a02_b05_j1_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_02', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_05', client=client)
    assert waited == pytest.approx(0.5)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.5)]


def test_shard_a02_b06_j0_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_02', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_06', client=client)
    assert waited == pytest.approx(0.125)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.125)]


def test_shard_a02_b06_j0_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_02', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_06', client=client)
    assert waited == pytest.approx(0.25)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.25)]


def test_shard_a02_b06_j0p25_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_02', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_06', client=client)
    assert waited == pytest.approx(0.15625)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.15625)]


def test_shard_a02_b06_j0p25_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_02', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_06', client=client)
    assert waited == pytest.approx(0.3125)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.3125)]


def test_shard_a02_b06_j0p5_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_02', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_06', client=client)
    assert waited == pytest.approx(0.1875)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.1875)]


def test_shard_a02_b06_j0p5_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_02', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_06', client=client)
    assert waited == pytest.approx(0.375)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.375)]


def test_shard_a02_b06_j0p75_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_02', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_06', client=client)
    assert waited == pytest.approx(0.21875)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.21875)]


def test_shard_a02_b06_j0p75_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_02', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_06', client=client)
    assert waited == pytest.approx(0.4375)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.4375)]


def test_shard_a02_b06_j1_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_02', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_06', client=client)
    assert waited == pytest.approx(0.25)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.25)]


def test_shard_a02_b06_j1_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_02', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_06', client=client)
    assert waited == pytest.approx(0.5)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.5)]


def test_shard_a02_b07_j0_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_02', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_07', client=client)
    assert waited == pytest.approx(0.125)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.125)]


def test_shard_a02_b07_j0_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_02', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_07', client=client)
    assert waited == pytest.approx(0.25)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.25)]


def test_shard_a02_b07_j0p25_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_02', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_07', client=client)
    assert waited == pytest.approx(0.15625)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.15625)]


def test_shard_a02_b07_j0p25_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_02', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_07', client=client)
    assert waited == pytest.approx(0.3125)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.3125)]


def test_shard_a02_b07_j0p5_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_02', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_07', client=client)
    assert waited == pytest.approx(0.1875)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.1875)]


def test_shard_a02_b07_j0p5_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_02', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_07', client=client)
    assert waited == pytest.approx(0.375)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.375)]


def test_shard_a02_b07_j0p75_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_02', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_07', client=client)
    assert waited == pytest.approx(0.21875)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.21875)]


def test_shard_a02_b07_j0p75_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_02', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_07', client=client)
    assert waited == pytest.approx(0.4375)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.4375)]


def test_shard_a02_b07_j1_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_02', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_07', client=client)
    assert waited == pytest.approx(0.25)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.25)]


def test_shard_a02_b07_j1_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_02', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_07', client=client)
    assert waited == pytest.approx(0.5)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.5)]


def test_shard_a03_b00_j0_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_03', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_00', client=client)
    assert waited == pytest.approx(0.125)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.125)]


def test_shard_a03_b00_j0_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_03', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_00', client=client)
    assert waited == pytest.approx(0.25)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.25)]


def test_shard_a03_b00_j0p25_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_03', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_00', client=client)
    assert waited == pytest.approx(0.15625)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.15625)]


def test_shard_a03_b00_j0p25_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_03', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_00', client=client)
    assert waited == pytest.approx(0.3125)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.3125)]


def test_shard_a03_b00_j0p5_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_03', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_00', client=client)
    assert waited == pytest.approx(0.1875)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.1875)]


def test_shard_a03_b00_j0p5_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_03', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_00', client=client)
    assert waited == pytest.approx(0.375)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.375)]


def test_shard_a03_b00_j0p75_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_03', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_00', client=client)
    assert waited == pytest.approx(0.21875)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.21875)]


def test_shard_a03_b00_j0p75_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_03', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_00', client=client)
    assert waited == pytest.approx(0.4375)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.4375)]


def test_shard_a03_b00_j1_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_03', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_00', client=client)
    assert waited == pytest.approx(0.25)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.25)]


def test_shard_a03_b00_j1_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_03', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_00', client=client)
    assert waited == pytest.approx(0.5)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.5)]


def test_shard_a03_b01_j0_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_03', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_01', client=client)
    assert waited == pytest.approx(0.125)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.125)]


def test_shard_a03_b01_j0_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_03', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_01', client=client)
    assert waited == pytest.approx(0.25)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.25)]


def test_shard_a03_b01_j0p25_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_03', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_01', client=client)
    assert waited == pytest.approx(0.15625)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.15625)]


def test_shard_a03_b01_j0p25_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_03', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_01', client=client)
    assert waited == pytest.approx(0.3125)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.3125)]


def test_shard_a03_b01_j0p5_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_03', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_01', client=client)
    assert waited == pytest.approx(0.1875)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.1875)]


def test_shard_a03_b01_j0p5_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_03', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_01', client=client)
    assert waited == pytest.approx(0.375)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.375)]


def test_shard_a03_b01_j0p75_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_03', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_01', client=client)
    assert waited == pytest.approx(0.21875)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.21875)]


def test_shard_a03_b01_j0p75_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_03', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_01', client=client)
    assert waited == pytest.approx(0.4375)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.4375)]


def test_shard_a03_b01_j1_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_03', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_01', client=client)
    assert waited == pytest.approx(0.25)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.25)]


def test_shard_a03_b01_j1_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_03', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_01', client=client)
    assert waited == pytest.approx(0.5)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.5)]


def test_shard_a03_b02_j0_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_03', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_02', client=client)
    assert waited == pytest.approx(0.125)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.125)]


def test_shard_a03_b02_j0_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_03', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_02', client=client)
    assert waited == pytest.approx(0.25)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.25)]


def test_shard_a03_b02_j0p25_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_03', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_02', client=client)
    assert waited == pytest.approx(0.15625)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.15625)]


def test_shard_a03_b02_j0p25_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_03', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_02', client=client)
    assert waited == pytest.approx(0.3125)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.3125)]


def test_shard_a03_b02_j0p5_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_03', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_02', client=client)
    assert waited == pytest.approx(0.1875)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.1875)]


def test_shard_a03_b02_j0p5_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_03', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_02', client=client)
    assert waited == pytest.approx(0.375)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.375)]


def test_shard_a03_b02_j0p75_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_03', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_02', client=client)
    assert waited == pytest.approx(0.21875)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.21875)]


def test_shard_a03_b02_j0p75_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_03', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_02', client=client)
    assert waited == pytest.approx(0.4375)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.4375)]


def test_shard_a03_b02_j1_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_03', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_02', client=client)
    assert waited == pytest.approx(0.25)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.25)]


def test_shard_a03_b02_j1_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_03', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_02', client=client)
    assert waited == pytest.approx(0.5)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.5)]


def test_shard_a03_b03_j0_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_03', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_03', client=client)
    assert waited == pytest.approx(0.125)  # the label's own window is waited in full
    assert clock.sleeps == [pytest.approx(0.125)]


def test_shard_a03_b03_j0_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_03', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_03', client=client)
    assert waited == pytest.approx(0.25)  # the label's own window is waited in full
    assert clock.sleeps == [pytest.approx(0.25)]


def test_shard_a03_b03_j0p25_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_03', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_03', client=client)
    assert waited == pytest.approx(0.15625)  # the label's own window is waited in full
    assert clock.sleeps == [pytest.approx(0.15625)]


def test_shard_a03_b03_j0p25_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_03', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_03', client=client)
    assert waited == pytest.approx(0.3125)  # the label's own window is waited in full
    assert clock.sleeps == [pytest.approx(0.3125)]


def test_shard_a03_b03_j0p5_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_03', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_03', client=client)
    assert waited == pytest.approx(0.1875)  # the label's own window is waited in full
    assert clock.sleeps == [pytest.approx(0.1875)]


def test_shard_a03_b03_j0p5_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_03', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_03', client=client)
    assert waited == pytest.approx(0.375)  # the label's own window is waited in full
    assert clock.sleeps == [pytest.approx(0.375)]


def test_shard_a03_b03_j0p75_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_03', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_03', client=client)
    assert waited == pytest.approx(0.21875)  # the label's own window is waited in full
    assert clock.sleeps == [pytest.approx(0.21875)]


def test_shard_a03_b03_j0p75_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_03', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_03', client=client)
    assert waited == pytest.approx(0.4375)  # the label's own window is waited in full
    assert clock.sleeps == [pytest.approx(0.4375)]


def test_shard_a03_b03_j1_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_03', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_03', client=client)
    assert waited == pytest.approx(0.25)  # the label's own window is waited in full
    assert clock.sleeps == [pytest.approx(0.25)]


def test_shard_a03_b03_j1_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_03', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_03', client=client)
    assert waited == pytest.approx(0.5)  # the label's own window is waited in full
    assert clock.sleeps == [pytest.approx(0.5)]


def test_shard_a03_b04_j0_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_03', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_04', client=client)
    assert waited == pytest.approx(0.125)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.125)]


def test_shard_a03_b04_j0_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_03', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_04', client=client)
    assert waited == pytest.approx(0.25)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.25)]


def test_shard_a03_b04_j0p25_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_03', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_04', client=client)
    assert waited == pytest.approx(0.15625)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.15625)]


def test_shard_a03_b04_j0p25_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_03', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_04', client=client)
    assert waited == pytest.approx(0.3125)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.3125)]


def test_shard_a03_b04_j0p5_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_03', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_04', client=client)
    assert waited == pytest.approx(0.1875)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.1875)]


def test_shard_a03_b04_j0p5_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_03', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_04', client=client)
    assert waited == pytest.approx(0.375)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.375)]


def test_shard_a03_b04_j0p75_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_03', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_04', client=client)
    assert waited == pytest.approx(0.21875)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.21875)]


def test_shard_a03_b04_j0p75_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_03', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_04', client=client)
    assert waited == pytest.approx(0.4375)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.4375)]


def test_shard_a03_b04_j1_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_03', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_04', client=client)
    assert waited == pytest.approx(0.25)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.25)]


def test_shard_a03_b04_j1_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_03', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_04', client=client)
    assert waited == pytest.approx(0.5)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.5)]


def test_shard_a03_b05_j0_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_03', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_05', client=client)
    assert waited == pytest.approx(0.125)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.125)]


def test_shard_a03_b05_j0_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_03', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_05', client=client)
    assert waited == pytest.approx(0.25)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.25)]


def test_shard_a03_b05_j0p25_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_03', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_05', client=client)
    assert waited == pytest.approx(0.15625)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.15625)]


def test_shard_a03_b05_j0p25_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_03', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_05', client=client)
    assert waited == pytest.approx(0.3125)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.3125)]


def test_shard_a03_b05_j0p5_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_03', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_05', client=client)
    assert waited == pytest.approx(0.1875)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.1875)]


def test_shard_a03_b05_j0p5_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_03', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_05', client=client)
    assert waited == pytest.approx(0.375)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.375)]


def test_shard_a03_b05_j0p75_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_03', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_05', client=client)
    assert waited == pytest.approx(0.21875)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.21875)]


def test_shard_a03_b05_j0p75_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_03', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_05', client=client)
    assert waited == pytest.approx(0.4375)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.4375)]


def test_shard_a03_b05_j1_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_03', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_05', client=client)
    assert waited == pytest.approx(0.25)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.25)]


def test_shard_a03_b05_j1_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_03', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_05', client=client)
    assert waited == pytest.approx(0.5)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.5)]


def test_shard_a03_b06_j0_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_03', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_06', client=client)
    assert waited == pytest.approx(0.125)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.125)]


def test_shard_a03_b06_j0_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_03', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_06', client=client)
    assert waited == pytest.approx(0.25)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.25)]


def test_shard_a03_b06_j0p25_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_03', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_06', client=client)
    assert waited == pytest.approx(0.15625)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.15625)]


def test_shard_a03_b06_j0p25_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_03', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_06', client=client)
    assert waited == pytest.approx(0.3125)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.3125)]


def test_shard_a03_b06_j0p5_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_03', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_06', client=client)
    assert waited == pytest.approx(0.1875)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.1875)]


def test_shard_a03_b06_j0p5_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_03', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_06', client=client)
    assert waited == pytest.approx(0.375)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.375)]


def test_shard_a03_b06_j0p75_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_03', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_06', client=client)
    assert waited == pytest.approx(0.21875)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.21875)]


def test_shard_a03_b06_j0p75_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_03', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_06', client=client)
    assert waited == pytest.approx(0.4375)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.4375)]


def test_shard_a03_b06_j1_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_03', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_06', client=client)
    assert waited == pytest.approx(0.25)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.25)]


def test_shard_a03_b06_j1_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_03', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_06', client=client)
    assert waited == pytest.approx(0.5)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.5)]


def test_shard_a03_b07_j0_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_03', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_07', client=client)
    assert waited == pytest.approx(0.125)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.125)]


def test_shard_a03_b07_j0_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_03', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_07', client=client)
    assert waited == pytest.approx(0.25)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.25)]


def test_shard_a03_b07_j0p25_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_03', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_07', client=client)
    assert waited == pytest.approx(0.15625)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.15625)]


def test_shard_a03_b07_j0p25_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_03', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_07', client=client)
    assert waited == pytest.approx(0.3125)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.3125)]


def test_shard_a03_b07_j0p5_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_03', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_07', client=client)
    assert waited == pytest.approx(0.1875)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.1875)]


def test_shard_a03_b07_j0p5_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_03', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_07', client=client)
    assert waited == pytest.approx(0.375)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.375)]


def test_shard_a03_b07_j0p75_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_03', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_07', client=client)
    assert waited == pytest.approx(0.21875)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.21875)]


def test_shard_a03_b07_j0p75_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_03', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_07', client=client)
    assert waited == pytest.approx(0.4375)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.4375)]


def test_shard_a03_b07_j1_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_03', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_07', client=client)
    assert waited == pytest.approx(0.25)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.25)]


def test_shard_a03_b07_j1_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_03', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_07', client=client)
    assert waited == pytest.approx(0.5)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.5)]


def test_shard_a04_b00_j0_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_04', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_00', client=client)
    assert waited == pytest.approx(0.125)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.125)]


def test_shard_a04_b00_j0_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_04', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_00', client=client)
    assert waited == pytest.approx(0.25)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.25)]


def test_shard_a04_b00_j0p25_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_04', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_00', client=client)
    assert waited == pytest.approx(0.15625)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.15625)]


def test_shard_a04_b00_j0p25_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_04', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_00', client=client)
    assert waited == pytest.approx(0.3125)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.3125)]


def test_shard_a04_b00_j0p5_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_04', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_00', client=client)
    assert waited == pytest.approx(0.1875)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.1875)]


def test_shard_a04_b00_j0p5_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_04', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_00', client=client)
    assert waited == pytest.approx(0.375)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.375)]


def test_shard_a04_b00_j0p75_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_04', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_00', client=client)
    assert waited == pytest.approx(0.21875)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.21875)]


def test_shard_a04_b00_j0p75_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_04', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_00', client=client)
    assert waited == pytest.approx(0.4375)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.4375)]


def test_shard_a04_b00_j1_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_04', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_00', client=client)
    assert waited == pytest.approx(0.25)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.25)]


def test_shard_a04_b00_j1_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_04', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_00', client=client)
    assert waited == pytest.approx(0.5)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.5)]


def test_shard_a04_b01_j0_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_04', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_01', client=client)
    assert waited == pytest.approx(0.125)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.125)]


def test_shard_a04_b01_j0_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_04', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_01', client=client)
    assert waited == pytest.approx(0.25)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.25)]


def test_shard_a04_b01_j0p25_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_04', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_01', client=client)
    assert waited == pytest.approx(0.15625)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.15625)]


def test_shard_a04_b01_j0p25_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_04', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_01', client=client)
    assert waited == pytest.approx(0.3125)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.3125)]


def test_shard_a04_b01_j0p5_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_04', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_01', client=client)
    assert waited == pytest.approx(0.1875)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.1875)]


def test_shard_a04_b01_j0p5_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_04', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_01', client=client)
    assert waited == pytest.approx(0.375)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.375)]


def test_shard_a04_b01_j0p75_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_04', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_01', client=client)
    assert waited == pytest.approx(0.21875)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.21875)]


def test_shard_a04_b01_j0p75_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_04', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_01', client=client)
    assert waited == pytest.approx(0.4375)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.4375)]


def test_shard_a04_b01_j1_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_04', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_01', client=client)
    assert waited == pytest.approx(0.25)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.25)]


def test_shard_a04_b01_j1_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_04', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_01', client=client)
    assert waited == pytest.approx(0.5)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.5)]


def test_shard_a04_b02_j0_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_04', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_02', client=client)
    assert waited == pytest.approx(0.125)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.125)]


def test_shard_a04_b02_j0_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_04', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_02', client=client)
    assert waited == pytest.approx(0.25)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.25)]


def test_shard_a04_b02_j0p25_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_04', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_02', client=client)
    assert waited == pytest.approx(0.15625)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.15625)]


def test_shard_a04_b02_j0p25_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_04', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_02', client=client)
    assert waited == pytest.approx(0.3125)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.3125)]


def test_shard_a04_b02_j0p5_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_04', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_02', client=client)
    assert waited == pytest.approx(0.1875)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.1875)]


def test_shard_a04_b02_j0p5_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_04', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_02', client=client)
    assert waited == pytest.approx(0.375)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.375)]


def test_shard_a04_b02_j0p75_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_04', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_02', client=client)
    assert waited == pytest.approx(0.21875)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.21875)]


def test_shard_a04_b02_j0p75_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_04', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_02', client=client)
    assert waited == pytest.approx(0.4375)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.4375)]


def test_shard_a04_b02_j1_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_04', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_02', client=client)
    assert waited == pytest.approx(0.25)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.25)]


def test_shard_a04_b02_j1_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_04', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_02', client=client)
    assert waited == pytest.approx(0.5)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.5)]


def test_shard_a04_b03_j0_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_04', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_03', client=client)
    assert waited == pytest.approx(0.125)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.125)]


def test_shard_a04_b03_j0_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_04', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_03', client=client)
    assert waited == pytest.approx(0.25)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.25)]


def test_shard_a04_b03_j0p25_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_04', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_03', client=client)
    assert waited == pytest.approx(0.15625)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.15625)]


def test_shard_a04_b03_j0p25_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_04', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_03', client=client)
    assert waited == pytest.approx(0.3125)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.3125)]


def test_shard_a04_b03_j0p5_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_04', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_03', client=client)
    assert waited == pytest.approx(0.1875)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.1875)]


def test_shard_a04_b03_j0p5_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_04', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_03', client=client)
    assert waited == pytest.approx(0.375)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.375)]


def test_shard_a04_b03_j0p75_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_04', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_03', client=client)
    assert waited == pytest.approx(0.21875)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.21875)]


def test_shard_a04_b03_j0p75_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_04', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_03', client=client)
    assert waited == pytest.approx(0.4375)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.4375)]


def test_shard_a04_b03_j1_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_04', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_03', client=client)
    assert waited == pytest.approx(0.25)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.25)]


def test_shard_a04_b03_j1_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_04', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_03', client=client)
    assert waited == pytest.approx(0.5)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.5)]


def test_shard_a04_b04_j0_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_04', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_04', client=client)
    assert waited == pytest.approx(0.125)  # the label's own window is waited in full
    assert clock.sleeps == [pytest.approx(0.125)]


def test_shard_a04_b04_j0_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_04', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_04', client=client)
    assert waited == pytest.approx(0.25)  # the label's own window is waited in full
    assert clock.sleeps == [pytest.approx(0.25)]


def test_shard_a04_b04_j0p25_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_04', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_04', client=client)
    assert waited == pytest.approx(0.15625)  # the label's own window is waited in full
    assert clock.sleeps == [pytest.approx(0.15625)]


def test_shard_a04_b04_j0p25_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_04', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_04', client=client)
    assert waited == pytest.approx(0.3125)  # the label's own window is waited in full
    assert clock.sleeps == [pytest.approx(0.3125)]


def test_shard_a04_b04_j0p5_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_04', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_04', client=client)
    assert waited == pytest.approx(0.1875)  # the label's own window is waited in full
    assert clock.sleeps == [pytest.approx(0.1875)]


def test_shard_a04_b04_j0p5_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_04', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_04', client=client)
    assert waited == pytest.approx(0.375)  # the label's own window is waited in full
    assert clock.sleeps == [pytest.approx(0.375)]


def test_shard_a04_b04_j0p75_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_04', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_04', client=client)
    assert waited == pytest.approx(0.21875)  # the label's own window is waited in full
    assert clock.sleeps == [pytest.approx(0.21875)]


def test_shard_a04_b04_j0p75_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_04', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_04', client=client)
    assert waited == pytest.approx(0.4375)  # the label's own window is waited in full
    assert clock.sleeps == [pytest.approx(0.4375)]


def test_shard_a04_b04_j1_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_04', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_04', client=client)
    assert waited == pytest.approx(0.25)  # the label's own window is waited in full
    assert clock.sleeps == [pytest.approx(0.25)]


def test_shard_a04_b04_j1_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_04', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_04', client=client)
    assert waited == pytest.approx(0.5)  # the label's own window is waited in full
    assert clock.sleeps == [pytest.approx(0.5)]


def test_shard_a04_b05_j0_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_04', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_05', client=client)
    assert waited == pytest.approx(0.125)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.125)]


def test_shard_a04_b05_j0_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_04', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_05', client=client)
    assert waited == pytest.approx(0.25)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.25)]


def test_shard_a04_b05_j0p25_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_04', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_05', client=client)
    assert waited == pytest.approx(0.15625)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.15625)]


def test_shard_a04_b05_j0p25_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_04', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_05', client=client)
    assert waited == pytest.approx(0.3125)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.3125)]


def test_shard_a04_b05_j0p5_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_04', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_05', client=client)
    assert waited == pytest.approx(0.1875)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.1875)]


def test_shard_a04_b05_j0p5_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_04', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_05', client=client)
    assert waited == pytest.approx(0.375)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.375)]


def test_shard_a04_b05_j0p75_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_04', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_05', client=client)
    assert waited == pytest.approx(0.21875)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.21875)]


def test_shard_a04_b05_j0p75_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_04', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_05', client=client)
    assert waited == pytest.approx(0.4375)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.4375)]


def test_shard_a04_b05_j1_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_04', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_05', client=client)
    assert waited == pytest.approx(0.25)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.25)]


def test_shard_a04_b05_j1_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_04', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_05', client=client)
    assert waited == pytest.approx(0.5)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.5)]


def test_shard_a04_b06_j0_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_04', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_06', client=client)
    assert waited == pytest.approx(0.125)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.125)]


def test_shard_a04_b06_j0_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_04', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_06', client=client)
    assert waited == pytest.approx(0.25)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.25)]


def test_shard_a04_b06_j0p25_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_04', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_06', client=client)
    assert waited == pytest.approx(0.15625)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.15625)]


def test_shard_a04_b06_j0p25_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_04', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_06', client=client)
    assert waited == pytest.approx(0.3125)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.3125)]


def test_shard_a04_b06_j0p5_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_04', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_06', client=client)
    assert waited == pytest.approx(0.1875)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.1875)]


def test_shard_a04_b06_j0p5_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_04', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_06', client=client)
    assert waited == pytest.approx(0.375)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.375)]


def test_shard_a04_b06_j0p75_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_04', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_06', client=client)
    assert waited == pytest.approx(0.21875)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.21875)]


def test_shard_a04_b06_j0p75_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_04', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_06', client=client)
    assert waited == pytest.approx(0.4375)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.4375)]


def test_shard_a04_b06_j1_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_04', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_06', client=client)
    assert waited == pytest.approx(0.25)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.25)]


def test_shard_a04_b06_j1_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_04', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_06', client=client)
    assert waited == pytest.approx(0.5)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.5)]


def test_shard_a04_b07_j0_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_04', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_07', client=client)
    assert waited == pytest.approx(0.125)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.125)]


def test_shard_a04_b07_j0_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_04', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_07', client=client)
    assert waited == pytest.approx(0.25)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.25)]


def test_shard_a04_b07_j0p25_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_04', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_07', client=client)
    assert waited == pytest.approx(0.15625)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.15625)]


def test_shard_a04_b07_j0p25_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_04', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_07', client=client)
    assert waited == pytest.approx(0.3125)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.3125)]


def test_shard_a04_b07_j0p5_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_04', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_07', client=client)
    assert waited == pytest.approx(0.1875)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.1875)]


def test_shard_a04_b07_j0p5_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_04', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_07', client=client)
    assert waited == pytest.approx(0.375)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.375)]


def test_shard_a04_b07_j0p75_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_04', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_07', client=client)
    assert waited == pytest.approx(0.21875)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.21875)]


def test_shard_a04_b07_j0p75_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_04', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_07', client=client)
    assert waited == pytest.approx(0.4375)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.4375)]


def test_shard_a04_b07_j1_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_04', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_07', client=client)
    assert waited == pytest.approx(0.25)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.25)]


def test_shard_a04_b07_j1_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_04', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_07', client=client)
    assert waited == pytest.approx(0.5)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.5)]


def test_shard_a05_b00_j0_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_05', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_00', client=client)
    assert waited == pytest.approx(0.125)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.125)]


def test_shard_a05_b00_j0_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_05', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_00', client=client)
    assert waited == pytest.approx(0.25)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.25)]


def test_shard_a05_b00_j0p25_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_05', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_00', client=client)
    assert waited == pytest.approx(0.15625)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.15625)]


def test_shard_a05_b00_j0p25_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_05', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_00', client=client)
    assert waited == pytest.approx(0.3125)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.3125)]


def test_shard_a05_b00_j0p5_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_05', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_00', client=client)
    assert waited == pytest.approx(0.1875)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.1875)]


def test_shard_a05_b00_j0p5_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_05', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_00', client=client)
    assert waited == pytest.approx(0.375)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.375)]


def test_shard_a05_b00_j0p75_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_05', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_00', client=client)
    assert waited == pytest.approx(0.21875)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.21875)]


def test_shard_a05_b00_j0p75_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_05', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_00', client=client)
    assert waited == pytest.approx(0.4375)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.4375)]


def test_shard_a05_b00_j1_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_05', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_00', client=client)
    assert waited == pytest.approx(0.25)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.25)]


def test_shard_a05_b00_j1_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_05', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_00', client=client)
    assert waited == pytest.approx(0.5)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.5)]


def test_shard_a05_b01_j0_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_05', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_01', client=client)
    assert waited == pytest.approx(0.125)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.125)]


def test_shard_a05_b01_j0_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_05', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_01', client=client)
    assert waited == pytest.approx(0.25)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.25)]


def test_shard_a05_b01_j0p25_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_05', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_01', client=client)
    assert waited == pytest.approx(0.15625)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.15625)]


def test_shard_a05_b01_j0p25_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_05', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_01', client=client)
    assert waited == pytest.approx(0.3125)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.3125)]


def test_shard_a05_b01_j0p5_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_05', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_01', client=client)
    assert waited == pytest.approx(0.1875)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.1875)]


def test_shard_a05_b01_j0p5_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_05', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_01', client=client)
    assert waited == pytest.approx(0.375)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.375)]


def test_shard_a05_b01_j0p75_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_05', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_01', client=client)
    assert waited == pytest.approx(0.21875)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.21875)]


def test_shard_a05_b01_j0p75_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_05', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_01', client=client)
    assert waited == pytest.approx(0.4375)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.4375)]


def test_shard_a05_b01_j1_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_05', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_01', client=client)
    assert waited == pytest.approx(0.25)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.25)]


def test_shard_a05_b01_j1_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_05', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_01', client=client)
    assert waited == pytest.approx(0.5)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.5)]


def test_shard_a05_b02_j0_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_05', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_02', client=client)
    assert waited == pytest.approx(0.125)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.125)]


def test_shard_a05_b02_j0_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_05', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_02', client=client)
    assert waited == pytest.approx(0.25)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.25)]


def test_shard_a05_b02_j0p25_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_05', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_02', client=client)
    assert waited == pytest.approx(0.15625)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.15625)]


def test_shard_a05_b02_j0p25_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_05', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_02', client=client)
    assert waited == pytest.approx(0.3125)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.3125)]


def test_shard_a05_b02_j0p5_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_05', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_02', client=client)
    assert waited == pytest.approx(0.1875)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.1875)]


def test_shard_a05_b02_j0p5_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_05', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_02', client=client)
    assert waited == pytest.approx(0.375)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.375)]


def test_shard_a05_b02_j0p75_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_05', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_02', client=client)
    assert waited == pytest.approx(0.21875)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.21875)]


def test_shard_a05_b02_j0p75_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_05', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_02', client=client)
    assert waited == pytest.approx(0.4375)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.4375)]


def test_shard_a05_b02_j1_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_05', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_02', client=client)
    assert waited == pytest.approx(0.25)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.25)]


def test_shard_a05_b02_j1_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_05', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_02', client=client)
    assert waited == pytest.approx(0.5)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.5)]


def test_shard_a05_b03_j0_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_05', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_03', client=client)
    assert waited == pytest.approx(0.125)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.125)]


def test_shard_a05_b03_j0_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_05', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_03', client=client)
    assert waited == pytest.approx(0.25)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.25)]


def test_shard_a05_b03_j0p25_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_05', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_03', client=client)
    assert waited == pytest.approx(0.15625)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.15625)]


def test_shard_a05_b03_j0p25_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_05', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_03', client=client)
    assert waited == pytest.approx(0.3125)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.3125)]


def test_shard_a05_b03_j0p5_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_05', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_03', client=client)
    assert waited == pytest.approx(0.1875)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.1875)]


def test_shard_a05_b03_j0p5_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_05', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_03', client=client)
    assert waited == pytest.approx(0.375)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.375)]


def test_shard_a05_b03_j0p75_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_05', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_03', client=client)
    assert waited == pytest.approx(0.21875)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.21875)]


def test_shard_a05_b03_j0p75_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_05', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_03', client=client)
    assert waited == pytest.approx(0.4375)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.4375)]


def test_shard_a05_b03_j1_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_05', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_03', client=client)
    assert waited == pytest.approx(0.25)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.25)]


def test_shard_a05_b03_j1_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_05', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_03', client=client)
    assert waited == pytest.approx(0.5)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.5)]


def test_shard_a05_b04_j0_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_05', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_04', client=client)
    assert waited == pytest.approx(0.125)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.125)]


def test_shard_a05_b04_j0_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_05', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_04', client=client)
    assert waited == pytest.approx(0.25)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.25)]


def test_shard_a05_b04_j0p25_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_05', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_04', client=client)
    assert waited == pytest.approx(0.15625)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.15625)]


def test_shard_a05_b04_j0p25_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_05', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_04', client=client)
    assert waited == pytest.approx(0.3125)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.3125)]


def test_shard_a05_b04_j0p5_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_05', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_04', client=client)
    assert waited == pytest.approx(0.1875)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.1875)]


def test_shard_a05_b04_j0p5_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_05', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_04', client=client)
    assert waited == pytest.approx(0.375)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.375)]


def test_shard_a05_b04_j0p75_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_05', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_04', client=client)
    assert waited == pytest.approx(0.21875)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.21875)]


def test_shard_a05_b04_j0p75_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_05', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_04', client=client)
    assert waited == pytest.approx(0.4375)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.4375)]


def test_shard_a05_b04_j1_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_05', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_04', client=client)
    assert waited == pytest.approx(0.25)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.25)]


def test_shard_a05_b04_j1_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_05', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_04', client=client)
    assert waited == pytest.approx(0.5)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.5)]


def test_shard_a05_b05_j0_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_05', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_05', client=client)
    assert waited == pytest.approx(0.125)  # the label's own window is waited in full
    assert clock.sleeps == [pytest.approx(0.125)]


def test_shard_a05_b05_j0_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_05', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_05', client=client)
    assert waited == pytest.approx(0.25)  # the label's own window is waited in full
    assert clock.sleeps == [pytest.approx(0.25)]


def test_shard_a05_b05_j0p25_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_05', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_05', client=client)
    assert waited == pytest.approx(0.15625)  # the label's own window is waited in full
    assert clock.sleeps == [pytest.approx(0.15625)]


def test_shard_a05_b05_j0p25_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_05', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_05', client=client)
    assert waited == pytest.approx(0.3125)  # the label's own window is waited in full
    assert clock.sleeps == [pytest.approx(0.3125)]


def test_shard_a05_b05_j0p5_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_05', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_05', client=client)
    assert waited == pytest.approx(0.1875)  # the label's own window is waited in full
    assert clock.sleeps == [pytest.approx(0.1875)]


def test_shard_a05_b05_j0p5_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_05', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_05', client=client)
    assert waited == pytest.approx(0.375)  # the label's own window is waited in full
    assert clock.sleeps == [pytest.approx(0.375)]


def test_shard_a05_b05_j0p75_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_05', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_05', client=client)
    assert waited == pytest.approx(0.21875)  # the label's own window is waited in full
    assert clock.sleeps == [pytest.approx(0.21875)]


def test_shard_a05_b05_j0p75_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_05', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_05', client=client)
    assert waited == pytest.approx(0.4375)  # the label's own window is waited in full
    assert clock.sleeps == [pytest.approx(0.4375)]


def test_shard_a05_b05_j1_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_05', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_05', client=client)
    assert waited == pytest.approx(0.25)  # the label's own window is waited in full
    assert clock.sleeps == [pytest.approx(0.25)]


def test_shard_a05_b05_j1_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_05', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_05', client=client)
    assert waited == pytest.approx(0.5)  # the label's own window is waited in full
    assert clock.sleeps == [pytest.approx(0.5)]


def test_shard_a05_b06_j0_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_05', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_06', client=client)
    assert waited == pytest.approx(0.125)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.125)]


def test_shard_a05_b06_j0_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_05', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_06', client=client)
    assert waited == pytest.approx(0.25)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.25)]


def test_shard_a05_b06_j0p25_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_05', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_06', client=client)
    assert waited == pytest.approx(0.15625)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.15625)]


def test_shard_a05_b06_j0p25_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_05', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_06', client=client)
    assert waited == pytest.approx(0.3125)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.3125)]


def test_shard_a05_b06_j0p5_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_05', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_06', client=client)
    assert waited == pytest.approx(0.1875)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.1875)]


def test_shard_a05_b06_j0p5_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_05', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_06', client=client)
    assert waited == pytest.approx(0.375)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.375)]


def test_shard_a05_b06_j0p75_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_05', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_06', client=client)
    assert waited == pytest.approx(0.21875)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.21875)]


def test_shard_a05_b06_j0p75_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_05', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_06', client=client)
    assert waited == pytest.approx(0.4375)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.4375)]


def test_shard_a05_b06_j1_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_05', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_06', client=client)
    assert waited == pytest.approx(0.25)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.25)]


def test_shard_a05_b06_j1_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_05', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_06', client=client)
    assert waited == pytest.approx(0.5)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.5)]


def test_shard_a05_b07_j0_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_05', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_07', client=client)
    assert waited == pytest.approx(0.125)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.125)]


def test_shard_a05_b07_j0_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_05', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_07', client=client)
    assert waited == pytest.approx(0.25)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.25)]


def test_shard_a05_b07_j0p25_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_05', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_07', client=client)
    assert waited == pytest.approx(0.15625)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.15625)]


def test_shard_a05_b07_j0p25_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_05', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_07', client=client)
    assert waited == pytest.approx(0.3125)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.3125)]


def test_shard_a05_b07_j0p5_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_05', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_07', client=client)
    assert waited == pytest.approx(0.1875)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.1875)]


def test_shard_a05_b07_j0p5_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_05', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_07', client=client)
    assert waited == pytest.approx(0.375)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.375)]


def test_shard_a05_b07_j0p75_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_05', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_07', client=client)
    assert waited == pytest.approx(0.21875)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.21875)]


def test_shard_a05_b07_j0p75_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_05', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_07', client=client)
    assert waited == pytest.approx(0.4375)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.4375)]


def test_shard_a05_b07_j1_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_05', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_07', client=client)
    assert waited == pytest.approx(0.25)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.25)]


def test_shard_a05_b07_j1_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_05', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_07', client=client)
    assert waited == pytest.approx(0.5)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.5)]


def test_shard_a06_b00_j0_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_06', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_00', client=client)
    assert waited == pytest.approx(0.125)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.125)]


def test_shard_a06_b00_j0_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_06', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_00', client=client)
    assert waited == pytest.approx(0.25)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.25)]


def test_shard_a06_b00_j0p25_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_06', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_00', client=client)
    assert waited == pytest.approx(0.15625)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.15625)]


def test_shard_a06_b00_j0p25_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_06', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_00', client=client)
    assert waited == pytest.approx(0.3125)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.3125)]


def test_shard_a06_b00_j0p5_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_06', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_00', client=client)
    assert waited == pytest.approx(0.1875)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.1875)]


def test_shard_a06_b00_j0p5_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_06', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_00', client=client)
    assert waited == pytest.approx(0.375)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.375)]


def test_shard_a06_b00_j0p75_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_06', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_00', client=client)
    assert waited == pytest.approx(0.21875)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.21875)]


def test_shard_a06_b00_j0p75_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_06', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_00', client=client)
    assert waited == pytest.approx(0.4375)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.4375)]


def test_shard_a06_b00_j1_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_06', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_00', client=client)
    assert waited == pytest.approx(0.25)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.25)]


def test_shard_a06_b00_j1_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_06', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_00', client=client)
    assert waited == pytest.approx(0.5)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.5)]


def test_shard_a06_b01_j0_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_06', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_01', client=client)
    assert waited == pytest.approx(0.125)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.125)]


def test_shard_a06_b01_j0_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_06', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_01', client=client)
    assert waited == pytest.approx(0.25)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.25)]


def test_shard_a06_b01_j0p25_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_06', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_01', client=client)
    assert waited == pytest.approx(0.15625)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.15625)]


def test_shard_a06_b01_j0p25_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_06', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_01', client=client)
    assert waited == pytest.approx(0.3125)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.3125)]


def test_shard_a06_b01_j0p5_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_06', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_01', client=client)
    assert waited == pytest.approx(0.1875)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.1875)]


def test_shard_a06_b01_j0p5_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_06', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_01', client=client)
    assert waited == pytest.approx(0.375)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.375)]


def test_shard_a06_b01_j0p75_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_06', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_01', client=client)
    assert waited == pytest.approx(0.21875)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.21875)]


def test_shard_a06_b01_j0p75_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_06', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_01', client=client)
    assert waited == pytest.approx(0.4375)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.4375)]


def test_shard_a06_b01_j1_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_06', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_01', client=client)
    assert waited == pytest.approx(0.25)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.25)]


def test_shard_a06_b01_j1_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_06', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_01', client=client)
    assert waited == pytest.approx(0.5)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.5)]


def test_shard_a06_b02_j0_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_06', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_02', client=client)
    assert waited == pytest.approx(0.125)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.125)]


def test_shard_a06_b02_j0_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_06', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_02', client=client)
    assert waited == pytest.approx(0.25)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.25)]


def test_shard_a06_b02_j0p25_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_06', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_02', client=client)
    assert waited == pytest.approx(0.15625)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.15625)]


def test_shard_a06_b02_j0p25_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_06', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_02', client=client)
    assert waited == pytest.approx(0.3125)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.3125)]


def test_shard_a06_b02_j0p5_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_06', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_02', client=client)
    assert waited == pytest.approx(0.1875)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.1875)]


def test_shard_a06_b02_j0p5_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_06', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_02', client=client)
    assert waited == pytest.approx(0.375)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.375)]


def test_shard_a06_b02_j0p75_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_06', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_02', client=client)
    assert waited == pytest.approx(0.21875)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.21875)]


def test_shard_a06_b02_j0p75_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_06', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_02', client=client)
    assert waited == pytest.approx(0.4375)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.4375)]


def test_shard_a06_b02_j1_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_06', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_02', client=client)
    assert waited == pytest.approx(0.25)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.25)]


def test_shard_a06_b02_j1_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_06', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_02', client=client)
    assert waited == pytest.approx(0.5)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.5)]


def test_shard_a06_b03_j0_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_06', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_03', client=client)
    assert waited == pytest.approx(0.125)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.125)]


def test_shard_a06_b03_j0_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_06', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_03', client=client)
    assert waited == pytest.approx(0.25)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.25)]


def test_shard_a06_b03_j0p25_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_06', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_03', client=client)
    assert waited == pytest.approx(0.15625)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.15625)]


def test_shard_a06_b03_j0p25_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_06', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_03', client=client)
    assert waited == pytest.approx(0.3125)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.3125)]


def test_shard_a06_b03_j0p5_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_06', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_03', client=client)
    assert waited == pytest.approx(0.1875)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.1875)]


def test_shard_a06_b03_j0p5_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_06', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_03', client=client)
    assert waited == pytest.approx(0.375)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.375)]


def test_shard_a06_b03_j0p75_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_06', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_03', client=client)
    assert waited == pytest.approx(0.21875)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.21875)]


def test_shard_a06_b03_j0p75_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_06', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_03', client=client)
    assert waited == pytest.approx(0.4375)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.4375)]


def test_shard_a06_b03_j1_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_06', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_03', client=client)
    assert waited == pytest.approx(0.25)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.25)]


def test_shard_a06_b03_j1_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_06', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_03', client=client)
    assert waited == pytest.approx(0.5)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.5)]


def test_shard_a06_b04_j0_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_06', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_04', client=client)
    assert waited == pytest.approx(0.125)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.125)]


def test_shard_a06_b04_j0_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_06', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_04', client=client)
    assert waited == pytest.approx(0.25)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.25)]


def test_shard_a06_b04_j0p25_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_06', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_04', client=client)
    assert waited == pytest.approx(0.15625)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.15625)]


def test_shard_a06_b04_j0p25_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_06', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_04', client=client)
    assert waited == pytest.approx(0.3125)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.3125)]


def test_shard_a06_b04_j0p5_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_06', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_04', client=client)
    assert waited == pytest.approx(0.1875)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.1875)]


def test_shard_a06_b04_j0p5_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_06', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_04', client=client)
    assert waited == pytest.approx(0.375)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.375)]


def test_shard_a06_b04_j0p75_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_06', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_04', client=client)
    assert waited == pytest.approx(0.21875)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.21875)]


def test_shard_a06_b04_j0p75_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_06', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_04', client=client)
    assert waited == pytest.approx(0.4375)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.4375)]


def test_shard_a06_b04_j1_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_06', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_04', client=client)
    assert waited == pytest.approx(0.25)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.25)]


def test_shard_a06_b04_j1_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_06', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_04', client=client)
    assert waited == pytest.approx(0.5)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.5)]


def test_shard_a06_b05_j0_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_06', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_05', client=client)
    assert waited == pytest.approx(0.125)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.125)]


def test_shard_a06_b05_j0_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_06', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_05', client=client)
    assert waited == pytest.approx(0.25)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.25)]


def test_shard_a06_b05_j0p25_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_06', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_05', client=client)
    assert waited == pytest.approx(0.15625)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.15625)]


def test_shard_a06_b05_j0p25_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_06', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_05', client=client)
    assert waited == pytest.approx(0.3125)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.3125)]


def test_shard_a06_b05_j0p5_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_06', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_05', client=client)
    assert waited == pytest.approx(0.1875)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.1875)]


def test_shard_a06_b05_j0p5_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_06', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_05', client=client)
    assert waited == pytest.approx(0.375)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.375)]


def test_shard_a06_b05_j0p75_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_06', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_05', client=client)
    assert waited == pytest.approx(0.21875)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.21875)]


def test_shard_a06_b05_j0p75_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_06', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_05', client=client)
    assert waited == pytest.approx(0.4375)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.4375)]


def test_shard_a06_b05_j1_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_06', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_05', client=client)
    assert waited == pytest.approx(0.25)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.25)]


def test_shard_a06_b05_j1_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_06', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_05', client=client)
    assert waited == pytest.approx(0.5)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.5)]


def test_shard_a06_b06_j0_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_06', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_06', client=client)
    assert waited == pytest.approx(0.125)  # the label's own window is waited in full
    assert clock.sleeps == [pytest.approx(0.125)]


def test_shard_a06_b06_j0_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_06', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_06', client=client)
    assert waited == pytest.approx(0.25)  # the label's own window is waited in full
    assert clock.sleeps == [pytest.approx(0.25)]


def test_shard_a06_b06_j0p25_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_06', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_06', client=client)
    assert waited == pytest.approx(0.15625)  # the label's own window is waited in full
    assert clock.sleeps == [pytest.approx(0.15625)]


def test_shard_a06_b06_j0p25_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_06', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_06', client=client)
    assert waited == pytest.approx(0.3125)  # the label's own window is waited in full
    assert clock.sleeps == [pytest.approx(0.3125)]


def test_shard_a06_b06_j0p5_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_06', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_06', client=client)
    assert waited == pytest.approx(0.1875)  # the label's own window is waited in full
    assert clock.sleeps == [pytest.approx(0.1875)]


def test_shard_a06_b06_j0p5_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_06', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_06', client=client)
    assert waited == pytest.approx(0.375)  # the label's own window is waited in full
    assert clock.sleeps == [pytest.approx(0.375)]


def test_shard_a06_b06_j0p75_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_06', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_06', client=client)
    assert waited == pytest.approx(0.21875)  # the label's own window is waited in full
    assert clock.sleeps == [pytest.approx(0.21875)]


def test_shard_a06_b06_j0p75_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_06', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_06', client=client)
    assert waited == pytest.approx(0.4375)  # the label's own window is waited in full
    assert clock.sleeps == [pytest.approx(0.4375)]


def test_shard_a06_b06_j1_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_06', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_06', client=client)
    assert waited == pytest.approx(0.25)  # the label's own window is waited in full
    assert clock.sleeps == [pytest.approx(0.25)]


def test_shard_a06_b06_j1_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_06', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_06', client=client)
    assert waited == pytest.approx(0.5)  # the label's own window is waited in full
    assert clock.sleeps == [pytest.approx(0.5)]


def test_shard_a06_b07_j0_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_06', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_07', client=client)
    assert waited == pytest.approx(0.125)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.125)]


def test_shard_a06_b07_j0_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_06', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_07', client=client)
    assert waited == pytest.approx(0.25)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.25)]


def test_shard_a06_b07_j0p25_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_06', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_07', client=client)
    assert waited == pytest.approx(0.15625)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.15625)]


def test_shard_a06_b07_j0p25_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_06', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_07', client=client)
    assert waited == pytest.approx(0.3125)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.3125)]


def test_shard_a06_b07_j0p5_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_06', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_07', client=client)
    assert waited == pytest.approx(0.1875)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.1875)]


def test_shard_a06_b07_j0p5_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_06', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_07', client=client)
    assert waited == pytest.approx(0.375)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.375)]


def test_shard_a06_b07_j0p75_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_06', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_07', client=client)
    assert waited == pytest.approx(0.21875)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.21875)]


def test_shard_a06_b07_j0p75_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_06', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_07', client=client)
    assert waited == pytest.approx(0.4375)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.4375)]


def test_shard_a06_b07_j1_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_06', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_07', client=client)
    assert waited == pytest.approx(0.25)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.25)]


def test_shard_a06_b07_j1_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_06', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_07', client=client)
    assert waited == pytest.approx(0.5)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.5)]


def test_shard_a07_b00_j0_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_07', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_00', client=client)
    assert waited == pytest.approx(0.125)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.125)]


def test_shard_a07_b00_j0_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_07', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_00', client=client)
    assert waited == pytest.approx(0.25)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.25)]


def test_shard_a07_b00_j0p25_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_07', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_00', client=client)
    assert waited == pytest.approx(0.15625)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.15625)]


def test_shard_a07_b00_j0p25_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_07', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_00', client=client)
    assert waited == pytest.approx(0.3125)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.3125)]


def test_shard_a07_b00_j0p5_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_07', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_00', client=client)
    assert waited == pytest.approx(0.1875)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.1875)]


def test_shard_a07_b00_j0p5_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_07', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_00', client=client)
    assert waited == pytest.approx(0.375)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.375)]


def test_shard_a07_b00_j0p75_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_07', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_00', client=client)
    assert waited == pytest.approx(0.21875)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.21875)]


def test_shard_a07_b00_j0p75_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_07', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_00', client=client)
    assert waited == pytest.approx(0.4375)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.4375)]


def test_shard_a07_b00_j1_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_07', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_00', client=client)
    assert waited == pytest.approx(0.25)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.25)]


def test_shard_a07_b00_j1_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_07', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_00', client=client)
    assert waited == pytest.approx(0.5)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.5)]


def test_shard_a07_b01_j0_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_07', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_01', client=client)
    assert waited == pytest.approx(0.125)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.125)]


def test_shard_a07_b01_j0_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_07', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_01', client=client)
    assert waited == pytest.approx(0.25)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.25)]


def test_shard_a07_b01_j0p25_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_07', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_01', client=client)
    assert waited == pytest.approx(0.15625)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.15625)]


def test_shard_a07_b01_j0p25_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_07', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_01', client=client)
    assert waited == pytest.approx(0.3125)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.3125)]


def test_shard_a07_b01_j0p5_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_07', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_01', client=client)
    assert waited == pytest.approx(0.1875)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.1875)]


def test_shard_a07_b01_j0p5_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_07', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_01', client=client)
    assert waited == pytest.approx(0.375)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.375)]


def test_shard_a07_b01_j0p75_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_07', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_01', client=client)
    assert waited == pytest.approx(0.21875)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.21875)]


def test_shard_a07_b01_j0p75_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_07', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_01', client=client)
    assert waited == pytest.approx(0.4375)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.4375)]


def test_shard_a07_b01_j1_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_07', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_01', client=client)
    assert waited == pytest.approx(0.25)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.25)]


def test_shard_a07_b01_j1_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_07', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_01', client=client)
    assert waited == pytest.approx(0.5)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.5)]


def test_shard_a07_b02_j0_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_07', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_02', client=client)
    assert waited == pytest.approx(0.125)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.125)]


def test_shard_a07_b02_j0_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_07', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_02', client=client)
    assert waited == pytest.approx(0.25)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.25)]


def test_shard_a07_b02_j0p25_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_07', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_02', client=client)
    assert waited == pytest.approx(0.15625)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.15625)]


def test_shard_a07_b02_j0p25_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_07', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_02', client=client)
    assert waited == pytest.approx(0.3125)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.3125)]


def test_shard_a07_b02_j0p5_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_07', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_02', client=client)
    assert waited == pytest.approx(0.1875)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.1875)]


def test_shard_a07_b02_j0p5_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_07', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_02', client=client)
    assert waited == pytest.approx(0.375)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.375)]


def test_shard_a07_b02_j0p75_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_07', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_02', client=client)
    assert waited == pytest.approx(0.21875)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.21875)]


def test_shard_a07_b02_j0p75_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_07', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_02', client=client)
    assert waited == pytest.approx(0.4375)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.4375)]


def test_shard_a07_b02_j1_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_07', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_02', client=client)
    assert waited == pytest.approx(0.25)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.25)]


def test_shard_a07_b02_j1_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_07', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_02', client=client)
    assert waited == pytest.approx(0.5)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.5)]


def test_shard_a07_b03_j0_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_07', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_03', client=client)
    assert waited == pytest.approx(0.125)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.125)]


def test_shard_a07_b03_j0_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_07', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_03', client=client)
    assert waited == pytest.approx(0.25)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.25)]


def test_shard_a07_b03_j0p25_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_07', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_03', client=client)
    assert waited == pytest.approx(0.15625)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.15625)]


def test_shard_a07_b03_j0p25_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_07', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_03', client=client)
    assert waited == pytest.approx(0.3125)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.3125)]


def test_shard_a07_b03_j0p5_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_07', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_03', client=client)
    assert waited == pytest.approx(0.1875)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.1875)]


def test_shard_a07_b03_j0p5_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_07', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_03', client=client)
    assert waited == pytest.approx(0.375)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.375)]


def test_shard_a07_b03_j0p75_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_07', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_03', client=client)
    assert waited == pytest.approx(0.21875)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.21875)]


def test_shard_a07_b03_j0p75_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_07', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_03', client=client)
    assert waited == pytest.approx(0.4375)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.4375)]


def test_shard_a07_b03_j1_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_07', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_03', client=client)
    assert waited == pytest.approx(0.25)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.25)]


def test_shard_a07_b03_j1_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_07', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_03', client=client)
    assert waited == pytest.approx(0.5)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.5)]


def test_shard_a07_b04_j0_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_07', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_04', client=client)
    assert waited == pytest.approx(0.125)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.125)]


def test_shard_a07_b04_j0_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_07', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_04', client=client)
    assert waited == pytest.approx(0.25)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.25)]


def test_shard_a07_b04_j0p25_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_07', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_04', client=client)
    assert waited == pytest.approx(0.15625)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.15625)]


def test_shard_a07_b04_j0p25_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_07', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_04', client=client)
    assert waited == pytest.approx(0.3125)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.3125)]


def test_shard_a07_b04_j0p5_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_07', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_04', client=client)
    assert waited == pytest.approx(0.1875)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.1875)]


def test_shard_a07_b04_j0p5_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_07', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_04', client=client)
    assert waited == pytest.approx(0.375)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.375)]


def test_shard_a07_b04_j0p75_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_07', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_04', client=client)
    assert waited == pytest.approx(0.21875)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.21875)]


def test_shard_a07_b04_j0p75_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_07', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_04', client=client)
    assert waited == pytest.approx(0.4375)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.4375)]


def test_shard_a07_b04_j1_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_07', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_04', client=client)
    assert waited == pytest.approx(0.25)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.25)]


def test_shard_a07_b04_j1_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_07', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_04', client=client)
    assert waited == pytest.approx(0.5)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.5)]


def test_shard_a07_b05_j0_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_07', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_05', client=client)
    assert waited == pytest.approx(0.125)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.125)]


def test_shard_a07_b05_j0_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_07', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_05', client=client)
    assert waited == pytest.approx(0.25)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.25)]


def test_shard_a07_b05_j0p25_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_07', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_05', client=client)
    assert waited == pytest.approx(0.15625)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.15625)]


def test_shard_a07_b05_j0p25_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_07', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_05', client=client)
    assert waited == pytest.approx(0.3125)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.3125)]


def test_shard_a07_b05_j0p5_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_07', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_05', client=client)
    assert waited == pytest.approx(0.1875)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.1875)]


def test_shard_a07_b05_j0p5_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_07', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_05', client=client)
    assert waited == pytest.approx(0.375)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.375)]


def test_shard_a07_b05_j0p75_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_07', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_05', client=client)
    assert waited == pytest.approx(0.21875)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.21875)]


def test_shard_a07_b05_j0p75_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_07', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_05', client=client)
    assert waited == pytest.approx(0.4375)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.4375)]


def test_shard_a07_b05_j1_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_07', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_05', client=client)
    assert waited == pytest.approx(0.25)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.25)]


def test_shard_a07_b05_j1_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_07', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_05', client=client)
    assert waited == pytest.approx(0.5)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.5)]


def test_shard_a07_b06_j0_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_07', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_06', client=client)
    assert waited == pytest.approx(0.125)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.125)]


def test_shard_a07_b06_j0_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_07', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_06', client=client)
    assert waited == pytest.approx(0.25)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.25)]


def test_shard_a07_b06_j0p25_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_07', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_06', client=client)
    assert waited == pytest.approx(0.15625)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.15625)]


def test_shard_a07_b06_j0p25_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_07', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_06', client=client)
    assert waited == pytest.approx(0.3125)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.3125)]


def test_shard_a07_b06_j0p5_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_07', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_06', client=client)
    assert waited == pytest.approx(0.1875)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.1875)]


def test_shard_a07_b06_j0p5_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_07', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_06', client=client)
    assert waited == pytest.approx(0.375)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.375)]


def test_shard_a07_b06_j0p75_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_07', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_06', client=client)
    assert waited == pytest.approx(0.21875)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.21875)]


def test_shard_a07_b06_j0p75_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_07', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_06', client=client)
    assert waited == pytest.approx(0.4375)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.4375)]


def test_shard_a07_b06_j1_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_07', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_06', client=client)
    assert waited == pytest.approx(0.25)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.25)]


def test_shard_a07_b06_j1_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_07', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_06', client=client)
    assert waited == pytest.approx(0.5)  # a sibling label adopts the spill share-capped
    assert clock.sleeps == [pytest.approx(0.5)]


def test_shard_a07_b07_j0_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_07', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_07', client=client)
    assert waited == pytest.approx(0.125)  # the label's own window is waited in full
    assert clock.sleeps == [pytest.approx(0.125)]


def test_shard_a07_b07_j0_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_07', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_07', client=client)
    assert waited == pytest.approx(0.25)  # the label's own window is waited in full
    assert clock.sleeps == [pytest.approx(0.25)]


def test_shard_a07_b07_j0p25_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_07', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_07', client=client)
    assert waited == pytest.approx(0.15625)  # the label's own window is waited in full
    assert clock.sleeps == [pytest.approx(0.15625)]


def test_shard_a07_b07_j0p25_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_07', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_07', client=client)
    assert waited == pytest.approx(0.3125)  # the label's own window is waited in full
    assert clock.sleeps == [pytest.approx(0.3125)]


def test_shard_a07_b07_j0p5_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_07', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_07', client=client)
    assert waited == pytest.approx(0.1875)  # the label's own window is waited in full
    assert clock.sleeps == [pytest.approx(0.1875)]


def test_shard_a07_b07_j0p5_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_07', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_07', client=client)
    assert waited == pytest.approx(0.375)  # the label's own window is waited in full
    assert clock.sleeps == [pytest.approx(0.375)]


def test_shard_a07_b07_j0p75_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_07', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_07', client=client)
    assert waited == pytest.approx(0.21875)  # the label's own window is waited in full
    assert clock.sleeps == [pytest.approx(0.21875)]


def test_shard_a07_b07_j0p75_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_07', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_07', client=client)
    assert waited == pytest.approx(0.4375)  # the label's own window is waited in full
    assert clock.sleeps == [pytest.approx(0.4375)]


def test_shard_a07_b07_j1_n1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    for _ in range(1):
        damper.arm('batch_pull shard=scheduler_07', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_07', client=client)
    assert waited == pytest.approx(0.25)  # the label's own window is waited in full
    assert clock.sleeps == [pytest.approx(0.25)]


def test_shard_a07_b07_j1_n2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    for _ in range(2):
        damper.arm('batch_pull shard=scheduler_07', client=client)
    waited, generation = damper.consult('batch_pull shard=scheduler_07', client=client)
    assert waited == pytest.approx(0.5)  # the label's own window is waited in full
    assert clock.sleeps == [pytest.approx(0.5)]


def test_store_exhaust_j0(monkeypatch):
    silence_chain_sleep(monkeypatch)
    client = StormDocsClient(abort_times=10**6)
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    store = default_store(monkeypatch, client=client)
    store._storm_damper = damper
    error = exhaust_run(store, 'batch_merge_commit')
    assert error.retry_after == pytest.approx(0.125)
    spill_rows = [row for row in client.set_calls if row[1] == SPILL_DOC]
    assert len(spill_rows) == 1
    assert spill_rows[0][2]['armed_until'] == pytest.approx(WALL0 + 0.125)
    assert spill_rows[0][2]['label'] == 'batch_merge_commit'
    assert client.set_calls[-1][1] == 'batch_merge_commit'  # the label doc stays last


def test_store_exhaust_j0p25(monkeypatch):
    silence_chain_sleep(monkeypatch)
    client = StormDocsClient(abort_times=10**6)
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    store = default_store(monkeypatch, client=client)
    store._storm_damper = damper
    error = exhaust_run(store, 'batch_merge_commit')
    assert error.retry_after == pytest.approx(0.15625)
    spill_rows = [row for row in client.set_calls if row[1] == SPILL_DOC]
    assert len(spill_rows) == 1
    assert spill_rows[0][2]['armed_until'] == pytest.approx(WALL0 + 0.15625)
    assert spill_rows[0][2]['label'] == 'batch_merge_commit'
    assert client.set_calls[-1][1] == 'batch_merge_commit'  # the label doc stays last


def test_store_exhaust_j0p5(monkeypatch):
    silence_chain_sleep(monkeypatch)
    client = StormDocsClient(abort_times=10**6)
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    store = default_store(monkeypatch, client=client)
    store._storm_damper = damper
    error = exhaust_run(store, 'batch_merge_commit')
    assert error.retry_after == pytest.approx(0.1875)
    spill_rows = [row for row in client.set_calls if row[1] == SPILL_DOC]
    assert len(spill_rows) == 1
    assert spill_rows[0][2]['armed_until'] == pytest.approx(WALL0 + 0.1875)
    assert spill_rows[0][2]['label'] == 'batch_merge_commit'
    assert client.set_calls[-1][1] == 'batch_merge_commit'  # the label doc stays last


def test_store_exhaust_j0p75(monkeypatch):
    silence_chain_sleep(monkeypatch)
    client = StormDocsClient(abort_times=10**6)
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    store = default_store(monkeypatch, client=client)
    store._storm_damper = damper
    error = exhaust_run(store, 'batch_merge_commit')
    assert error.retry_after == pytest.approx(0.21875)
    spill_rows = [row for row in client.set_calls if row[1] == SPILL_DOC]
    assert len(spill_rows) == 1
    assert spill_rows[0][2]['armed_until'] == pytest.approx(WALL0 + 0.21875)
    assert spill_rows[0][2]['label'] == 'batch_merge_commit'
    assert client.set_calls[-1][1] == 'batch_merge_commit'  # the label doc stays last


def test_store_exhaust_j1(monkeypatch):
    silence_chain_sleep(monkeypatch)
    client = StormDocsClient(abort_times=10**6)
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    store = default_store(monkeypatch, client=client)
    store._storm_damper = damper
    error = exhaust_run(store, 'batch_merge_commit')
    assert error.retry_after == pytest.approx(0.25)
    spill_rows = [row for row in client.set_calls if row[1] == SPILL_DOC]
    assert len(spill_rows) == 1
    assert spill_rows[0][2]['armed_until'] == pytest.approx(WALL0 + 0.25)
    assert spill_rows[0][2]['label'] == 'batch_merge_commit'
    assert client.set_calls[-1][1] == 'batch_merge_commit'  # the label doc stays last


def test_store_shard00_j0(monkeypatch):
    silence_chain_sleep(monkeypatch)
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    client = StormDocsClient(abort_times=10**6)
    store = default_store(monkeypatch, client=client)
    store._storm_damper = damper
    exhaust_run(store, 'batch_pull shard=scheduler_00')
    healthy = StormDocsClient()
    store_b = default_store(monkeypatch, client=healthy)
    store_b._storm_damper = damper
    store_b.run(lambda tx: 'ok', operation='batch_pull shard=scheduler_01')
    assert clock.sleeps == [pytest.approx(min(0.125, 1.0))]


def test_store_shard00_j0p25(monkeypatch):
    silence_chain_sleep(monkeypatch)
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    client = StormDocsClient(abort_times=10**6)
    store = default_store(monkeypatch, client=client)
    store._storm_damper = damper
    exhaust_run(store, 'batch_pull shard=scheduler_00')
    healthy = StormDocsClient()
    store_b = default_store(monkeypatch, client=healthy)
    store_b._storm_damper = damper
    store_b.run(lambda tx: 'ok', operation='batch_pull shard=scheduler_01')
    assert clock.sleeps == [pytest.approx(min(0.15625, 1.0))]


def test_store_shard00_j0p5(monkeypatch):
    silence_chain_sleep(monkeypatch)
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    client = StormDocsClient(abort_times=10**6)
    store = default_store(monkeypatch, client=client)
    store._storm_damper = damper
    exhaust_run(store, 'batch_pull shard=scheduler_00')
    healthy = StormDocsClient()
    store_b = default_store(monkeypatch, client=healthy)
    store_b._storm_damper = damper
    store_b.run(lambda tx: 'ok', operation='batch_pull shard=scheduler_01')
    assert clock.sleeps == [pytest.approx(min(0.1875, 1.0))]


def test_store_shard00_j0p75(monkeypatch):
    silence_chain_sleep(monkeypatch)
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    client = StormDocsClient(abort_times=10**6)
    store = default_store(monkeypatch, client=client)
    store._storm_damper = damper
    exhaust_run(store, 'batch_pull shard=scheduler_00')
    healthy = StormDocsClient()
    store_b = default_store(monkeypatch, client=healthy)
    store_b._storm_damper = damper
    store_b.run(lambda tx: 'ok', operation='batch_pull shard=scheduler_01')
    assert clock.sleeps == [pytest.approx(min(0.21875, 1.0))]


def test_store_shard00_j1(monkeypatch):
    silence_chain_sleep(monkeypatch)
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    client = StormDocsClient(abort_times=10**6)
    store = default_store(monkeypatch, client=client)
    store._storm_damper = damper
    exhaust_run(store, 'batch_pull shard=scheduler_00')
    healthy = StormDocsClient()
    store_b = default_store(monkeypatch, client=healthy)
    store_b._storm_damper = damper
    store_b.run(lambda tx: 'ok', operation='batch_pull shard=scheduler_01')
    assert clock.sleeps == [pytest.approx(min(0.25, 1.0))]


def test_store_shard01_j0(monkeypatch):
    silence_chain_sleep(monkeypatch)
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    client = StormDocsClient(abort_times=10**6)
    store = default_store(monkeypatch, client=client)
    store._storm_damper = damper
    exhaust_run(store, 'batch_pull shard=scheduler_01')
    healthy = StormDocsClient()
    store_b = default_store(monkeypatch, client=healthy)
    store_b._storm_damper = damper
    store_b.run(lambda tx: 'ok', operation='batch_pull shard=scheduler_02')
    assert clock.sleeps == [pytest.approx(min(0.125, 1.0))]


def test_store_shard01_j0p25(monkeypatch):
    silence_chain_sleep(monkeypatch)
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    client = StormDocsClient(abort_times=10**6)
    store = default_store(monkeypatch, client=client)
    store._storm_damper = damper
    exhaust_run(store, 'batch_pull shard=scheduler_01')
    healthy = StormDocsClient()
    store_b = default_store(monkeypatch, client=healthy)
    store_b._storm_damper = damper
    store_b.run(lambda tx: 'ok', operation='batch_pull shard=scheduler_02')
    assert clock.sleeps == [pytest.approx(min(0.15625, 1.0))]


def test_store_shard01_j0p5(monkeypatch):
    silence_chain_sleep(monkeypatch)
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    client = StormDocsClient(abort_times=10**6)
    store = default_store(monkeypatch, client=client)
    store._storm_damper = damper
    exhaust_run(store, 'batch_pull shard=scheduler_01')
    healthy = StormDocsClient()
    store_b = default_store(monkeypatch, client=healthy)
    store_b._storm_damper = damper
    store_b.run(lambda tx: 'ok', operation='batch_pull shard=scheduler_02')
    assert clock.sleeps == [pytest.approx(min(0.1875, 1.0))]


def test_store_shard01_j0p75(monkeypatch):
    silence_chain_sleep(monkeypatch)
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    client = StormDocsClient(abort_times=10**6)
    store = default_store(monkeypatch, client=client)
    store._storm_damper = damper
    exhaust_run(store, 'batch_pull shard=scheduler_01')
    healthy = StormDocsClient()
    store_b = default_store(monkeypatch, client=healthy)
    store_b._storm_damper = damper
    store_b.run(lambda tx: 'ok', operation='batch_pull shard=scheduler_02')
    assert clock.sleeps == [pytest.approx(min(0.21875, 1.0))]


def test_store_shard01_j1(monkeypatch):
    silence_chain_sleep(monkeypatch)
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    client = StormDocsClient(abort_times=10**6)
    store = default_store(monkeypatch, client=client)
    store._storm_damper = damper
    exhaust_run(store, 'batch_pull shard=scheduler_01')
    healthy = StormDocsClient()
    store_b = default_store(monkeypatch, client=healthy)
    store_b._storm_damper = damper
    store_b.run(lambda tx: 'ok', operation='batch_pull shard=scheduler_02')
    assert clock.sleeps == [pytest.approx(min(0.25, 1.0))]


def test_store_shard02_j0(monkeypatch):
    silence_chain_sleep(monkeypatch)
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    client = StormDocsClient(abort_times=10**6)
    store = default_store(monkeypatch, client=client)
    store._storm_damper = damper
    exhaust_run(store, 'batch_pull shard=scheduler_02')
    healthy = StormDocsClient()
    store_b = default_store(monkeypatch, client=healthy)
    store_b._storm_damper = damper
    store_b.run(lambda tx: 'ok', operation='batch_pull shard=scheduler_03')
    assert clock.sleeps == [pytest.approx(min(0.125, 1.0))]


def test_store_shard02_j0p25(monkeypatch):
    silence_chain_sleep(monkeypatch)
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    client = StormDocsClient(abort_times=10**6)
    store = default_store(monkeypatch, client=client)
    store._storm_damper = damper
    exhaust_run(store, 'batch_pull shard=scheduler_02')
    healthy = StormDocsClient()
    store_b = default_store(monkeypatch, client=healthy)
    store_b._storm_damper = damper
    store_b.run(lambda tx: 'ok', operation='batch_pull shard=scheduler_03')
    assert clock.sleeps == [pytest.approx(min(0.15625, 1.0))]


def test_store_shard02_j0p5(monkeypatch):
    silence_chain_sleep(monkeypatch)
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    client = StormDocsClient(abort_times=10**6)
    store = default_store(monkeypatch, client=client)
    store._storm_damper = damper
    exhaust_run(store, 'batch_pull shard=scheduler_02')
    healthy = StormDocsClient()
    store_b = default_store(monkeypatch, client=healthy)
    store_b._storm_damper = damper
    store_b.run(lambda tx: 'ok', operation='batch_pull shard=scheduler_03')
    assert clock.sleeps == [pytest.approx(min(0.1875, 1.0))]


def test_store_shard02_j0p75(monkeypatch):
    silence_chain_sleep(monkeypatch)
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    client = StormDocsClient(abort_times=10**6)
    store = default_store(monkeypatch, client=client)
    store._storm_damper = damper
    exhaust_run(store, 'batch_pull shard=scheduler_02')
    healthy = StormDocsClient()
    store_b = default_store(monkeypatch, client=healthy)
    store_b._storm_damper = damper
    store_b.run(lambda tx: 'ok', operation='batch_pull shard=scheduler_03')
    assert clock.sleeps == [pytest.approx(min(0.21875, 1.0))]


def test_store_shard02_j1(monkeypatch):
    silence_chain_sleep(monkeypatch)
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    client = StormDocsClient(abort_times=10**6)
    store = default_store(monkeypatch, client=client)
    store._storm_damper = damper
    exhaust_run(store, 'batch_pull shard=scheduler_02')
    healthy = StormDocsClient()
    store_b = default_store(monkeypatch, client=healthy)
    store_b._storm_damper = damper
    store_b.run(lambda tx: 'ok', operation='batch_pull shard=scheduler_03')
    assert clock.sleeps == [pytest.approx(min(0.25, 1.0))]


def test_store_shard03_j0(monkeypatch):
    silence_chain_sleep(monkeypatch)
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    client = StormDocsClient(abort_times=10**6)
    store = default_store(monkeypatch, client=client)
    store._storm_damper = damper
    exhaust_run(store, 'batch_pull shard=scheduler_03')
    healthy = StormDocsClient()
    store_b = default_store(monkeypatch, client=healthy)
    store_b._storm_damper = damper
    store_b.run(lambda tx: 'ok', operation='batch_pull shard=scheduler_04')
    assert clock.sleeps == [pytest.approx(min(0.125, 1.0))]


def test_store_shard03_j0p25(monkeypatch):
    silence_chain_sleep(monkeypatch)
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    client = StormDocsClient(abort_times=10**6)
    store = default_store(monkeypatch, client=client)
    store._storm_damper = damper
    exhaust_run(store, 'batch_pull shard=scheduler_03')
    healthy = StormDocsClient()
    store_b = default_store(monkeypatch, client=healthy)
    store_b._storm_damper = damper
    store_b.run(lambda tx: 'ok', operation='batch_pull shard=scheduler_04')
    assert clock.sleeps == [pytest.approx(min(0.15625, 1.0))]


def test_store_shard03_j0p5(monkeypatch):
    silence_chain_sleep(monkeypatch)
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    client = StormDocsClient(abort_times=10**6)
    store = default_store(monkeypatch, client=client)
    store._storm_damper = damper
    exhaust_run(store, 'batch_pull shard=scheduler_03')
    healthy = StormDocsClient()
    store_b = default_store(monkeypatch, client=healthy)
    store_b._storm_damper = damper
    store_b.run(lambda tx: 'ok', operation='batch_pull shard=scheduler_04')
    assert clock.sleeps == [pytest.approx(min(0.1875, 1.0))]


def test_store_shard03_j0p75(monkeypatch):
    silence_chain_sleep(monkeypatch)
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    client = StormDocsClient(abort_times=10**6)
    store = default_store(monkeypatch, client=client)
    store._storm_damper = damper
    exhaust_run(store, 'batch_pull shard=scheduler_03')
    healthy = StormDocsClient()
    store_b = default_store(monkeypatch, client=healthy)
    store_b._storm_damper = damper
    store_b.run(lambda tx: 'ok', operation='batch_pull shard=scheduler_04')
    assert clock.sleeps == [pytest.approx(min(0.21875, 1.0))]


def test_store_shard03_j1(monkeypatch):
    silence_chain_sleep(monkeypatch)
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    client = StormDocsClient(abort_times=10**6)
    store = default_store(monkeypatch, client=client)
    store._storm_damper = damper
    exhaust_run(store, 'batch_pull shard=scheduler_03')
    healthy = StormDocsClient()
    store_b = default_store(monkeypatch, client=healthy)
    store_b._storm_damper = damper
    store_b.run(lambda tx: 'ok', operation='batch_pull shard=scheduler_04')
    assert clock.sleeps == [pytest.approx(min(0.25, 1.0))]


def test_store_shard04_j0(monkeypatch):
    silence_chain_sleep(monkeypatch)
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    client = StormDocsClient(abort_times=10**6)
    store = default_store(monkeypatch, client=client)
    store._storm_damper = damper
    exhaust_run(store, 'batch_pull shard=scheduler_04')
    healthy = StormDocsClient()
    store_b = default_store(monkeypatch, client=healthy)
    store_b._storm_damper = damper
    store_b.run(lambda tx: 'ok', operation='batch_pull shard=scheduler_05')
    assert clock.sleeps == [pytest.approx(min(0.125, 1.0))]


def test_store_shard04_j0p25(monkeypatch):
    silence_chain_sleep(monkeypatch)
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    client = StormDocsClient(abort_times=10**6)
    store = default_store(monkeypatch, client=client)
    store._storm_damper = damper
    exhaust_run(store, 'batch_pull shard=scheduler_04')
    healthy = StormDocsClient()
    store_b = default_store(monkeypatch, client=healthy)
    store_b._storm_damper = damper
    store_b.run(lambda tx: 'ok', operation='batch_pull shard=scheduler_05')
    assert clock.sleeps == [pytest.approx(min(0.15625, 1.0))]


def test_store_shard04_j0p5(monkeypatch):
    silence_chain_sleep(monkeypatch)
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    client = StormDocsClient(abort_times=10**6)
    store = default_store(monkeypatch, client=client)
    store._storm_damper = damper
    exhaust_run(store, 'batch_pull shard=scheduler_04')
    healthy = StormDocsClient()
    store_b = default_store(monkeypatch, client=healthy)
    store_b._storm_damper = damper
    store_b.run(lambda tx: 'ok', operation='batch_pull shard=scheduler_05')
    assert clock.sleeps == [pytest.approx(min(0.1875, 1.0))]


def test_store_shard04_j0p75(monkeypatch):
    silence_chain_sleep(monkeypatch)
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    client = StormDocsClient(abort_times=10**6)
    store = default_store(monkeypatch, client=client)
    store._storm_damper = damper
    exhaust_run(store, 'batch_pull shard=scheduler_04')
    healthy = StormDocsClient()
    store_b = default_store(monkeypatch, client=healthy)
    store_b._storm_damper = damper
    store_b.run(lambda tx: 'ok', operation='batch_pull shard=scheduler_05')
    assert clock.sleeps == [pytest.approx(min(0.21875, 1.0))]


def test_store_shard04_j1(monkeypatch):
    silence_chain_sleep(monkeypatch)
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    client = StormDocsClient(abort_times=10**6)
    store = default_store(monkeypatch, client=client)
    store._storm_damper = damper
    exhaust_run(store, 'batch_pull shard=scheduler_04')
    healthy = StormDocsClient()
    store_b = default_store(monkeypatch, client=healthy)
    store_b._storm_damper = damper
    store_b.run(lambda tx: 'ok', operation='batch_pull shard=scheduler_05')
    assert clock.sleeps == [pytest.approx(min(0.25, 1.0))]


def test_store_shard05_j0(monkeypatch):
    silence_chain_sleep(monkeypatch)
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    client = StormDocsClient(abort_times=10**6)
    store = default_store(monkeypatch, client=client)
    store._storm_damper = damper
    exhaust_run(store, 'batch_pull shard=scheduler_05')
    healthy = StormDocsClient()
    store_b = default_store(monkeypatch, client=healthy)
    store_b._storm_damper = damper
    store_b.run(lambda tx: 'ok', operation='batch_pull shard=scheduler_06')
    assert clock.sleeps == [pytest.approx(min(0.125, 1.0))]


def test_store_shard05_j0p25(monkeypatch):
    silence_chain_sleep(monkeypatch)
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    client = StormDocsClient(abort_times=10**6)
    store = default_store(monkeypatch, client=client)
    store._storm_damper = damper
    exhaust_run(store, 'batch_pull shard=scheduler_05')
    healthy = StormDocsClient()
    store_b = default_store(monkeypatch, client=healthy)
    store_b._storm_damper = damper
    store_b.run(lambda tx: 'ok', operation='batch_pull shard=scheduler_06')
    assert clock.sleeps == [pytest.approx(min(0.15625, 1.0))]


def test_store_shard05_j0p5(monkeypatch):
    silence_chain_sleep(monkeypatch)
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    client = StormDocsClient(abort_times=10**6)
    store = default_store(monkeypatch, client=client)
    store._storm_damper = damper
    exhaust_run(store, 'batch_pull shard=scheduler_05')
    healthy = StormDocsClient()
    store_b = default_store(monkeypatch, client=healthy)
    store_b._storm_damper = damper
    store_b.run(lambda tx: 'ok', operation='batch_pull shard=scheduler_06')
    assert clock.sleeps == [pytest.approx(min(0.1875, 1.0))]


def test_store_shard05_j0p75(monkeypatch):
    silence_chain_sleep(monkeypatch)
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    client = StormDocsClient(abort_times=10**6)
    store = default_store(monkeypatch, client=client)
    store._storm_damper = damper
    exhaust_run(store, 'batch_pull shard=scheduler_05')
    healthy = StormDocsClient()
    store_b = default_store(monkeypatch, client=healthy)
    store_b._storm_damper = damper
    store_b.run(lambda tx: 'ok', operation='batch_pull shard=scheduler_06')
    assert clock.sleeps == [pytest.approx(min(0.21875, 1.0))]


def test_store_shard05_j1(monkeypatch):
    silence_chain_sleep(monkeypatch)
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    client = StormDocsClient(abort_times=10**6)
    store = default_store(monkeypatch, client=client)
    store._storm_damper = damper
    exhaust_run(store, 'batch_pull shard=scheduler_05')
    healthy = StormDocsClient()
    store_b = default_store(monkeypatch, client=healthy)
    store_b._storm_damper = damper
    store_b.run(lambda tx: 'ok', operation='batch_pull shard=scheduler_06')
    assert clock.sleeps == [pytest.approx(min(0.25, 1.0))]


def test_store_shard06_j0(monkeypatch):
    silence_chain_sleep(monkeypatch)
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    client = StormDocsClient(abort_times=10**6)
    store = default_store(monkeypatch, client=client)
    store._storm_damper = damper
    exhaust_run(store, 'batch_pull shard=scheduler_06')
    healthy = StormDocsClient()
    store_b = default_store(monkeypatch, client=healthy)
    store_b._storm_damper = damper
    store_b.run(lambda tx: 'ok', operation='batch_pull shard=scheduler_07')
    assert clock.sleeps == [pytest.approx(min(0.125, 1.0))]


def test_store_shard06_j0p25(monkeypatch):
    silence_chain_sleep(monkeypatch)
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    client = StormDocsClient(abort_times=10**6)
    store = default_store(monkeypatch, client=client)
    store._storm_damper = damper
    exhaust_run(store, 'batch_pull shard=scheduler_06')
    healthy = StormDocsClient()
    store_b = default_store(monkeypatch, client=healthy)
    store_b._storm_damper = damper
    store_b.run(lambda tx: 'ok', operation='batch_pull shard=scheduler_07')
    assert clock.sleeps == [pytest.approx(min(0.15625, 1.0))]


def test_store_shard06_j0p5(monkeypatch):
    silence_chain_sleep(monkeypatch)
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    client = StormDocsClient(abort_times=10**6)
    store = default_store(monkeypatch, client=client)
    store._storm_damper = damper
    exhaust_run(store, 'batch_pull shard=scheduler_06')
    healthy = StormDocsClient()
    store_b = default_store(monkeypatch, client=healthy)
    store_b._storm_damper = damper
    store_b.run(lambda tx: 'ok', operation='batch_pull shard=scheduler_07')
    assert clock.sleeps == [pytest.approx(min(0.1875, 1.0))]


def test_store_shard06_j0p75(monkeypatch):
    silence_chain_sleep(monkeypatch)
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    client = StormDocsClient(abort_times=10**6)
    store = default_store(monkeypatch, client=client)
    store._storm_damper = damper
    exhaust_run(store, 'batch_pull shard=scheduler_06')
    healthy = StormDocsClient()
    store_b = default_store(monkeypatch, client=healthy)
    store_b._storm_damper = damper
    store_b.run(lambda tx: 'ok', operation='batch_pull shard=scheduler_07')
    assert clock.sleeps == [pytest.approx(min(0.21875, 1.0))]


def test_store_shard06_j1(monkeypatch):
    silence_chain_sleep(monkeypatch)
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    client = StormDocsClient(abort_times=10**6)
    store = default_store(monkeypatch, client=client)
    store._storm_damper = damper
    exhaust_run(store, 'batch_pull shard=scheduler_06')
    healthy = StormDocsClient()
    store_b = default_store(monkeypatch, client=healthy)
    store_b._storm_damper = damper
    store_b.run(lambda tx: 'ok', operation='batch_pull shard=scheduler_07')
    assert clock.sleeps == [pytest.approx(min(0.25, 1.0))]


def test_store_shard07_j0(monkeypatch):
    silence_chain_sleep(monkeypatch)
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    client = StormDocsClient(abort_times=10**6)
    store = default_store(monkeypatch, client=client)
    store._storm_damper = damper
    exhaust_run(store, 'batch_pull shard=scheduler_07')
    healthy = StormDocsClient()
    store_b = default_store(monkeypatch, client=healthy)
    store_b._storm_damper = damper
    store_b.run(lambda tx: 'ok', operation='batch_pull shard=scheduler_00')
    assert clock.sleeps == [pytest.approx(min(0.125, 1.0))]


def test_store_shard07_j0p25(monkeypatch):
    silence_chain_sleep(monkeypatch)
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    client = StormDocsClient(abort_times=10**6)
    store = default_store(monkeypatch, client=client)
    store._storm_damper = damper
    exhaust_run(store, 'batch_pull shard=scheduler_07')
    healthy = StormDocsClient()
    store_b = default_store(monkeypatch, client=healthy)
    store_b._storm_damper = damper
    store_b.run(lambda tx: 'ok', operation='batch_pull shard=scheduler_00')
    assert clock.sleeps == [pytest.approx(min(0.15625, 1.0))]


def test_store_shard07_j0p5(monkeypatch):
    silence_chain_sleep(monkeypatch)
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    client = StormDocsClient(abort_times=10**6)
    store = default_store(monkeypatch, client=client)
    store._storm_damper = damper
    exhaust_run(store, 'batch_pull shard=scheduler_07')
    healthy = StormDocsClient()
    store_b = default_store(monkeypatch, client=healthy)
    store_b._storm_damper = damper
    store_b.run(lambda tx: 'ok', operation='batch_pull shard=scheduler_00')
    assert clock.sleeps == [pytest.approx(min(0.1875, 1.0))]


def test_store_shard07_j0p75(monkeypatch):
    silence_chain_sleep(monkeypatch)
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    client = StormDocsClient(abort_times=10**6)
    store = default_store(monkeypatch, client=client)
    store._storm_damper = damper
    exhaust_run(store, 'batch_pull shard=scheduler_07')
    healthy = StormDocsClient()
    store_b = default_store(monkeypatch, client=healthy)
    store_b._storm_damper = damper
    store_b.run(lambda tx: 'ok', operation='batch_pull shard=scheduler_00')
    assert clock.sleeps == [pytest.approx(min(0.21875, 1.0))]


def test_store_shard07_j1(monkeypatch):
    silence_chain_sleep(monkeypatch)
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    client = StormDocsClient(abort_times=10**6)
    store = default_store(monkeypatch, client=client)
    store._storm_damper = damper
    exhaust_run(store, 'batch_pull shard=scheduler_07')
    healthy = StormDocsClient()
    store_b = default_store(monkeypatch, client=healthy)
    store_b._storm_damper = damper
    store_b.run(lambda tx: 'ok', operation='batch_pull shard=scheduler_00')
    assert clock.sleeps == [pytest.approx(min(0.25, 1.0))]


def test_lockstep_n3_j0():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    for label in ['batch_label_00', 'batch_label_01', 'batch_label_02']:
        damper.arm(label, client=client)
    assert window.spill_publishes == 1  # the first arm raises the spill; the lockstep siblings skip
    assert window.spill_publish_skips == 2


def test_lockstep_n3_j0p25():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    for label in ['batch_label_00', 'batch_label_01', 'batch_label_02']:
        damper.arm(label, client=client)
    assert window.spill_publishes == 1  # the first arm raises the spill; the lockstep siblings skip
    assert window.spill_publish_skips == 2


def test_lockstep_n3_j0p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    for label in ['batch_label_00', 'batch_label_01', 'batch_label_02']:
        damper.arm(label, client=client)
    assert window.spill_publishes == 1  # the first arm raises the spill; the lockstep siblings skip
    assert window.spill_publish_skips == 2


def test_lockstep_n3_j0p75():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    for label in ['batch_label_00', 'batch_label_01', 'batch_label_02']:
        damper.arm(label, client=client)
    assert window.spill_publishes == 1  # the first arm raises the spill; the lockstep siblings skip
    assert window.spill_publish_skips == 2


def test_lockstep_n3_j1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    for label in ['batch_label_00', 'batch_label_01', 'batch_label_02']:
        damper.arm(label, client=client)
    assert window.spill_publishes == 1  # the first arm raises the spill; the lockstep siblings skip
    assert window.spill_publish_skips == 2


def test_lockstep_n8_j0():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    for label in [
        'batch_label_00',
        'batch_label_01',
        'batch_label_02',
        'batch_label_03',
        'batch_label_04',
        'batch_label_05',
        'batch_label_06',
        'batch_label_07',
    ]:
        damper.arm(label, client=client)
    assert window.spill_publishes == 1  # the first arm raises the spill; the lockstep siblings skip
    assert window.spill_publish_skips == 7


def test_lockstep_n8_j0p25():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.25)
    for label in [
        'batch_label_00',
        'batch_label_01',
        'batch_label_02',
        'batch_label_03',
        'batch_label_04',
        'batch_label_05',
        'batch_label_06',
        'batch_label_07',
    ]:
        damper.arm(label, client=client)
    assert window.spill_publishes == 1  # the first arm raises the spill; the lockstep siblings skip
    assert window.spill_publish_skips == 7


def test_lockstep_n8_j0p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.5)
    for label in [
        'batch_label_00',
        'batch_label_01',
        'batch_label_02',
        'batch_label_03',
        'batch_label_04',
        'batch_label_05',
        'batch_label_06',
        'batch_label_07',
    ]:
        damper.arm(label, client=client)
    assert window.spill_publishes == 1  # the first arm raises the spill; the lockstep siblings skip
    assert window.spill_publish_skips == 7


def test_lockstep_n8_j0p75():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.75)
    for label in [
        'batch_label_00',
        'batch_label_01',
        'batch_label_02',
        'batch_label_03',
        'batch_label_04',
        'batch_label_05',
        'batch_label_06',
        'batch_label_07',
    ]:
        damper.arm(label, client=client)
    assert window.spill_publishes == 1  # the first arm raises the spill; the lockstep siblings skip
    assert window.spill_publish_skips == 7


def test_lockstep_n8_j1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=1.0)
    for label in [
        'batch_label_00',
        'batch_label_01',
        'batch_label_02',
        'batch_label_03',
        'batch_label_04',
        'batch_label_05',
        'batch_label_06',
        'batch_label_07',
    ]:
        damper.arm(label, client=client)
    assert window.spill_publishes == 1  # the first arm raises the spill; the lockstep siblings skip
    assert window.spill_publish_skips == 7


def test_peekimmune_l0_slive():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 2.0)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    residual, generation = damper.peek('batch_label_00')
    assert residual == 0.0
    assert generation == 0
    assert window.spill_reads == 0  # the mid-ladder peek never reads the spill
    assert client.get_calls == []


def test_peekimmune_l0_sabsent():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    residual, generation = damper.peek('batch_label_00')
    assert residual == 0.0
    assert generation == 0
    assert window.spill_reads == 0  # the mid-ladder peek never reads the spill
    assert client.get_calls == []


def test_peekimmune_l1_slive():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 2.0)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    residual, generation = damper.peek('batch_label_00')
    assert residual == 0.0
    assert generation == 0
    assert window.spill_reads == 0  # the mid-ladder peek never reads the spill
    assert client.get_calls == []


def test_peekimmune_l1_sabsent():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    residual, generation = damper.peek('batch_label_00')
    assert residual == 0.0
    assert generation == 0
    assert window.spill_reads == 0  # the mid-ladder peek never reads the spill
    assert client.get_calls == []


def test_peekimmune_l2_slive():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 2.0)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    residual, generation = damper.peek('batch_label_00')
    assert residual == 0.0
    assert generation == 0
    assert window.spill_reads == 0  # the mid-ladder peek never reads the spill
    assert client.get_calls == []


def test_peekimmune_l2_sabsent():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    residual, generation = damper.peek('batch_label_00')
    assert residual == 0.0
    assert generation == 0
    assert window.spill_reads == 0  # the mid-ladder peek never reads the spill
    assert client.get_calls == []


def test_peekimmune_l3_slive():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 2.0)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    residual, generation = damper.peek('batch_label_00')
    assert residual == 0.0
    assert generation == 0
    assert window.spill_reads == 0  # the mid-ladder peek never reads the spill
    assert client.get_calls == []


def test_peekimmune_l3_sabsent():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    residual, generation = damper.peek('batch_label_00')
    assert residual == 0.0
    assert generation == 0
    assert window.spill_reads == 0  # the mid-ladder peek never reads the spill
    assert client.get_calls == []


def test_peekimmune_l4_slive():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 2.0)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    residual, generation = damper.peek('batch_label_00')
    assert residual == 0.0
    assert generation == 0
    assert window.spill_reads == 0  # the mid-ladder peek never reads the spill
    assert client.get_calls == []


def test_peekimmune_l4_sabsent():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    residual, generation = damper.peek('batch_label_00')
    assert residual == 0.0
    assert generation == 0
    assert window.spill_reads == 0  # the mid-ladder peek never reads the spill
    assert client.get_calls == []


def test_peekimmune_l5_slive():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 2.0)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    residual, generation = damper.peek('batch_label_00')
    assert residual == 0.0
    assert generation == 0
    assert window.spill_reads == 0  # the mid-ladder peek never reads the spill
    assert client.get_calls == []


def test_peekimmune_l5_sabsent():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    residual, generation = damper.peek('batch_label_00')
    assert residual == 0.0
    assert generation == 0
    assert window.spill_reads == 0  # the mid-ladder peek never reads the spill
    assert client.get_calls == []


def test_peekimmune_l6_slive():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 2.0)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    residual, generation = damper.peek('batch_label_00')
    assert residual == 0.0
    assert generation == 0
    assert window.spill_reads == 0  # the mid-ladder peek never reads the spill
    assert client.get_calls == []


def test_peekimmune_l6_sabsent():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    residual, generation = damper.peek('batch_label_00')
    assert residual == 0.0
    assert generation == 0
    assert window.spill_reads == 0  # the mid-ladder peek never reads the spill
    assert client.get_calls == []


def test_peekimmune_l7_slive():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 2.0)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    residual, generation = damper.peek('batch_label_00')
    assert residual == 0.0
    assert generation == 0
    assert window.spill_reads == 0  # the mid-ladder peek never reads the spill
    assert client.get_calls == []


def test_peekimmune_l7_sabsent():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    residual, generation = damper.peek('batch_label_00')
    assert residual == 0.0
    assert generation == 0
    assert window.spill_reads == 0  # the mid-ladder peek never reads the spill
    assert client.get_calls == []


def test_peekimmune_l8_slive():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 2.0)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    residual, generation = damper.peek('batch_label_00')
    assert residual == 0.0
    assert generation == 0
    assert window.spill_reads == 0  # the mid-ladder peek never reads the spill
    assert client.get_calls == []


def test_peekimmune_l8_sabsent():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    residual, generation = damper.peek('batch_label_00')
    assert residual == 0.0
    assert generation == 0
    assert window.spill_reads == 0  # the mid-ladder peek never reads the spill
    assert client.get_calls == []


def test_peekimmune_l9_slive():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 2.0)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    residual, generation = damper.peek('batch_label_00')
    assert residual == 0.0
    assert generation == 0
    assert window.spill_reads == 0  # the mid-ladder peek never reads the spill
    assert client.get_calls == []


def test_peekimmune_l9_sabsent():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    residual, generation = damper.peek('batch_label_00')
    assert residual == 0.0
    assert generation == 0
    assert window.spill_reads == 0  # the mid-ladder peek never reads the spill
    assert client.get_calls == []


def test_mirrorbound_n126():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    for index in range(126):
        window.publish('batch_fill_%03d' % index, 1.0, client=client)
    reads_before = window.spill_reads
    window.publish_spill('batch_spill_label', 1.0, client=client)
    assert window.spill_reads == reads_before + 1  # one cold fetch, then the warm mirror serves
    assert window.peek_spill(client) == pytest.approx(1.0)
    assert window.spill_reads == reads_before + 1  # the peek never re-reads beside the label mirror
    assert window.cached_labels() == 126


def test_mirrorbound_n127():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    for index in range(127):
        window.publish('batch_fill_%03d' % index, 1.0, client=client)
    reads_before = window.spill_reads
    window.publish_spill('batch_spill_label', 1.0, client=client)
    assert window.spill_reads == reads_before + 1  # one cold fetch, then the warm mirror serves
    assert window.peek_spill(client) == pytest.approx(1.0)
    assert window.spill_reads == reads_before + 1  # the peek never re-reads beside the label mirror
    assert window.cached_labels() == 127


def test_mirrorbound_n128():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    for index in range(128):
        window.publish('batch_fill_%03d' % index, 1.0, client=client)
    reads_before = window.spill_reads
    window.publish_spill('batch_spill_label', 1.0, client=client)
    assert window.spill_reads == reads_before + 1  # one cold fetch, then the warm mirror serves
    assert window.peek_spill(client) == pytest.approx(1.0)
    assert window.spill_reads == reads_before + 1  # the peek never re-reads beside the label mirror
    assert window.cached_labels() == 128


def test_mirrorbound_n129():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    for index in range(129):
        window.publish('batch_fill_%03d' % index, 1.0, client=client)
    reads_before = window.spill_reads
    window.publish_spill('batch_spill_label', 1.0, client=client)
    assert window.spill_reads == reads_before + 1  # one cold fetch, then the warm mirror serves
    assert window.peek_spill(client) == pytest.approx(1.0)
    assert window.spill_reads == reads_before + 1  # the peek never re-reads beside the label mirror
    assert window.cached_labels() == 128


def test_mirrorbound_n130():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    for index in range(130):
        window.publish('batch_fill_%03d' % index, 1.0, client=client)
    reads_before = window.spill_reads
    window.publish_spill('batch_spill_label', 1.0, client=client)
    assert window.spill_reads == reads_before + 1  # one cold fetch, then the warm mirror serves
    assert window.peek_spill(client) == pytest.approx(1.0)
    assert window.spill_reads == reads_before + 1  # the peek never re-reads beside the label mirror
    assert window.cached_labels() == 128


def test_dormant_damper_off_ok(monkeypatch):
    monkeypatch.setattr(storage, 'contention_storm_damper_enabled', lambda: False)
    client = StormDocsClient()
    store = default_store(monkeypatch, client=client)
    assert store.run(lambda tx: 'ok', operation='batch_admit') == 'ok'
    assert client.set_calls == []  # the spill lane never wakes while the damper is dormant
    spill_reads = [row for row in client.get_calls if row[1] == SPILL_DOC]
    assert spill_reads == []


def test_dormant_damper_off_exhaust(monkeypatch):
    monkeypatch.setattr(storage, 'contention_storm_damper_enabled', lambda: False)
    client = StormDocsClient(abort_times=10**6)
    store = default_store(monkeypatch, client=client)
    error = exhaust_run(store, 'batch_admit')
    assert error is not None
    assert client.set_calls == []  # the spill lane never wakes while the damper is dormant
    spill_reads = [row for row in client.get_calls if row[1] == SPILL_DOC]
    assert spill_reads == []


def test_dormant_both_off_ok(monkeypatch):
    monkeypatch.setattr(storage, 'contention_retry_enabled', lambda: False)
    monkeypatch.setattr(storage, 'contention_storm_damper_enabled', lambda: False)
    client = StormDocsClient()
    store = default_store(monkeypatch, client=client)
    assert store.run(lambda tx: 'ok', operation='batch_admit') == 'ok'
    assert client.set_calls == []  # the spill lane never wakes while the damper is dormant
    spill_reads = [row for row in client.get_calls if row[1] == SPILL_DOC]
    assert spill_reads == []


def test_dormant_injected_damper_ok(monkeypatch):
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    client = StormDocsClient()
    private = storage._ContentionStormDamper()
    store = storage.FirestoreStore('batch_pipeline_dev', firestore_client=client, storm_damper=private)
    assert store.run(lambda tx: 'ok', operation='batch_admit') == 'ok'
    assert client.set_calls == []  # the spill lane never wakes while the damper is dormant
    spill_reads = [row for row in client.get_calls if row[1] == SPILL_DOC]
    assert spill_reads == []


def test_dormant_injected_damper_exhaust(monkeypatch):
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    client = StormDocsClient(abort_times=10**6)
    private = storage._ContentionStormDamper()
    store = storage.FirestoreStore('batch_pipeline_dev', firestore_client=client, storm_damper=private)
    error = exhaust_run(store, 'batch_admit')
    assert error is not None
    assert client.set_calls == []  # the spill lane never wakes while the damper is dormant
    spill_reads = [row for row in client.get_calls if row[1] == SPILL_DOC]
    assert spill_reads == []


def test_dormant_retry_off_ok(monkeypatch):
    monkeypatch.setattr(storage, 'contention_retry_enabled', lambda: False)
    client = StormDocsClient()
    store = default_store(monkeypatch, client=client)
    assert store.run(lambda tx: 'ok', operation='batch_admit') == 'ok'
    assert client.set_calls == []  # the spill lane never wakes while the damper is dormant
    spill_reads = [row for row in client.get_calls if row[1] == SPILL_DOC]
    assert spill_reads == []


def test_reread_r0p5_o0p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.5)
    assert window.peek_spill(client) == pytest.approx(0.5)
    wall.advance(0.5)
    assert window.peek_spill(client) == pytest.approx(0.0)
    assert window.spill_reads == 1


def test_reread_r0p5_o1p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.5)
    assert window.peek_spill(client) == pytest.approx(0.5)
    wall.advance(1.5)
    assert window.peek_spill(client) == pytest.approx(0.0)
    assert window.spill_reads == 2


def test_reread_r1_o0p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 1.0)
    assert window.peek_spill(client) == pytest.approx(1.0)
    wall.advance(0.5)
    assert window.peek_spill(client) == pytest.approx(0.5)
    assert window.spill_reads == 1


def test_reread_r1_o1p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 1.0)
    assert window.peek_spill(client) == pytest.approx(1.0)
    wall.advance(1.5)
    assert window.peek_spill(client) == pytest.approx(0.0)
    assert window.spill_reads == 2


def test_reread_r2_o0p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 2.0)
    assert window.peek_spill(client) == pytest.approx(2.0)
    wall.advance(0.5)
    assert window.peek_spill(client) == pytest.approx(1.5)
    assert window.spill_reads == 1


def test_reread_r2_o1p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 2.0)
    assert window.peek_spill(client) == pytest.approx(2.0)
    wall.advance(1.5)
    assert window.peek_spill(client) == pytest.approx(0.5)
    assert window.spill_reads == 2


def test_reread_r4_o0p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    assert window.peek_spill(client) == pytest.approx(4.0)
    wall.advance(0.5)
    assert window.peek_spill(client) == pytest.approx(3.5)
    assert window.spill_reads == 1


def test_reread_r4_o1p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    assert window.peek_spill(client) == pytest.approx(4.0)
    wall.advance(1.5)
    assert window.peek_spill(client) == pytest.approx(2.5)
    assert window.spill_reads == 2


def test_equal_w0p125():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.125)  # a live spill at exactly this depth
    window.publish_spill('batch_admit', 0.125, client=client)
    assert window.spill_publishes == 0  # equal depth never rewrites
    assert window.spill_publish_skips == 1
    assert window.spill_reads == 1


def test_equal_w0p25():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.25)  # a live spill at exactly this depth
    window.publish_spill('batch_admit', 0.25, client=client)
    assert window.spill_publishes == 0  # equal depth never rewrites
    assert window.spill_publish_skips == 1
    assert window.spill_reads == 1


def test_equal_w0p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.5)  # a live spill at exactly this depth
    window.publish_spill('batch_admit', 0.5, client=client)
    assert window.spill_publishes == 0  # equal depth never rewrites
    assert window.spill_publish_skips == 1
    assert window.spill_reads == 1


def test_equal_w1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 1.0)  # a live spill at exactly this depth
    window.publish_spill('batch_admit', 1.0, client=client)
    assert window.spill_publishes == 0  # equal depth never rewrites
    assert window.spill_publish_skips == 1
    assert window.spill_reads == 1


def test_equal_w2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 2.0)  # a live spill at exactly this depth
    window.publish_spill('batch_admit', 2.0, client=client)
    assert window.spill_publishes == 0  # equal depth never rewrites
    assert window.spill_publish_skips == 1
    assert window.spill_reads == 1


def test_equal_w4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)  # a live spill at exactly this depth
    window.publish_spill('batch_admit', 4.0, client=client)
    assert window.spill_publishes == 0  # equal depth never rewrites
    assert window.spill_publish_skips == 1
    assert window.spill_reads == 1


def test_merge_f0_lbatch_admit():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)] = {'operator': 'seed-1'}
    window.publish_spill('batch_admit', 2.0, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(
        1000002.0
    )  # merge-set preserves sibling fields; the deeper spill stands


def test_merge_f0_lbatch_merge():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)] = {'operator': 'seed-1'}
    window.publish_spill('batch_merge', 2.0, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(
        1000002.0
    )  # merge-set preserves sibling fields; the deeper spill stands


def test_merge_f0_lbatch_merge_commit():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)] = {'operator': 'seed-1'}
    window.publish_spill('batch_merge_commit', 2.0, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(
        1000002.0
    )  # merge-set preserves sibling fields; the deeper spill stands


def test_merge_f1_lbatch_admit():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)] = {'note': 'seed-2', 'armed_until': WALL0 + 0.1}
    window.publish_spill('batch_admit', 2.0, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(
        1000002.0
    )  # merge-set preserves sibling fields; the deeper spill stands


def test_merge_f1_lbatch_merge():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)] = {'note': 'seed-2', 'armed_until': WALL0 + 0.1}
    window.publish_spill('batch_merge', 2.0, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(
        1000002.0
    )  # merge-set preserves sibling fields; the deeper spill stands


def test_merge_f1_lbatch_merge_commit():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)] = {'note': 'seed-2', 'armed_until': WALL0 + 0.1}
    window.publish_spill('batch_merge_commit', 2.0, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(
        1000002.0
    )  # merge-set preserves sibling fields; the deeper spill stands


def test_merge_f2_lbatch_admit():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)] = {
        'armed_until': WALL0 + 3.0,
        'label': 'deeper_sibling',
    }
    window.publish_spill('batch_admit', 2.0, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(
        1000003.0
    )  # merge-set preserves sibling fields; the deeper spill stands


def test_merge_f2_lbatch_merge():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)] = {
        'armed_until': WALL0 + 3.0,
        'label': 'deeper_sibling',
    }
    window.publish_spill('batch_merge', 2.0, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(
        1000003.0
    )  # merge-set preserves sibling fields; the deeper spill stands


def test_merge_f2_lbatch_merge_commit():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)] = {
        'armed_until': WALL0 + 3.0,
        'label': 'deeper_sibling',
    }
    window.publish_spill('batch_merge_commit', 2.0, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(
        1000003.0
    )  # merge-set preserves sibling fields; the deeper spill stands
