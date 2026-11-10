"""Namespace storm spill boundary grid

Pins every fail-open boundary of the spill lanes: the adopt share-cap and precedence
matrices, the monotone publish floor over the seeded live-spill depth x window matrices,
the label stamp, the fault and malformed-payload corpora, the TTL and wall-offset
boundaries, hostile answers, unfit labels, namespace isolation, the mirror-freshness
boundary, expired-own-window interplay, and the generation-guard passthrough.

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


def test_adopt_cap0p25_r0p05():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.05)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 0.25
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(0.05)
    assert clock.sleeps == [pytest.approx(0.05)]
    assert generation == 0


def test_adopt_cap0p25_r0p0625():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.0625)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 0.25
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(0.0625)
    assert clock.sleeps == [pytest.approx(0.0625)]
    assert generation == 0


def test_adopt_cap0p25_r0p125():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.125)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 0.25
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(0.125)
    assert clock.sleeps == [pytest.approx(0.125)]
    assert generation == 0


def test_adopt_cap0p25_r0p1875():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.1875)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 0.25
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(0.1875)
    assert clock.sleeps == [pytest.approx(0.1875)]
    assert generation == 0


def test_adopt_cap0p25_r0p25():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.25)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 0.25
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(0.25)
    assert clock.sleeps == [pytest.approx(0.25)]
    assert generation == 0


def test_adopt_cap0p25_r0p3125():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.3125)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 0.25
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(0.25)
    assert clock.sleeps == [pytest.approx(0.25)]
    assert generation == 0


def test_adopt_cap0p25_r0p375():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.375)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 0.25
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(0.25)
    assert clock.sleeps == [pytest.approx(0.25)]
    assert generation == 0


def test_adopt_cap0p25_r0p4375():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.4375)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 0.25
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(0.25)
    assert clock.sleeps == [pytest.approx(0.25)]
    assert generation == 0


def test_adopt_cap0p25_r0p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.5)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 0.25
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(0.25)
    assert clock.sleeps == [pytest.approx(0.25)]
    assert generation == 0


def test_adopt_cap0p25_r0p625():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.625)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 0.25
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(0.25)
    assert clock.sleeps == [pytest.approx(0.25)]
    assert generation == 0


def test_adopt_cap0p25_r0p75():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.75)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 0.25
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(0.25)
    assert clock.sleeps == [pytest.approx(0.25)]
    assert generation == 0


def test_adopt_cap0p25_r0p875():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.875)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 0.25
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(0.25)
    assert clock.sleeps == [pytest.approx(0.25)]
    assert generation == 0


def test_adopt_cap0p25_r1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 1.0)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 0.25
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(0.25)
    assert clock.sleeps == [pytest.approx(0.25)]
    assert generation == 0


def test_adopt_cap0p25_r1p25():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 1.25)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 0.25
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(0.25)
    assert clock.sleeps == [pytest.approx(0.25)]
    assert generation == 0


def test_adopt_cap0p25_r1p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 1.5)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 0.25
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(0.25)
    assert clock.sleeps == [pytest.approx(0.25)]
    assert generation == 0


def test_adopt_cap0p25_r1p75():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 1.75)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 0.25
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(0.25)
    assert clock.sleeps == [pytest.approx(0.25)]
    assert generation == 0


def test_adopt_cap0p25_r2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 2.0)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 0.25
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(0.25)
    assert clock.sleeps == [pytest.approx(0.25)]
    assert generation == 0


def test_adopt_cap0p25_r2p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 2.5)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 0.25
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(0.25)
    assert clock.sleeps == [pytest.approx(0.25)]
    assert generation == 0


def test_adopt_cap0p25_r3():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 3.0)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 0.25
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(0.25)
    assert clock.sleeps == [pytest.approx(0.25)]
    assert generation == 0


def test_adopt_cap0p25_r3p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 3.5)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 0.25
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(0.25)
    assert clock.sleeps == [pytest.approx(0.25)]
    assert generation == 0


def test_adopt_cap0p25_r4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 0.25
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(0.25)
    assert clock.sleeps == [pytest.approx(0.25)]
    assert generation == 0


def test_adopt_cap0p25_r4p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.5)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 0.25
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(0.25)
    assert clock.sleeps == [pytest.approx(0.25)]
    assert generation == 0


def test_adopt_cap0p5_r0p05():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.05)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 0.5
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(0.05)
    assert clock.sleeps == [pytest.approx(0.05)]
    assert generation == 0


def test_adopt_cap0p5_r0p0625():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.0625)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 0.5
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(0.0625)
    assert clock.sleeps == [pytest.approx(0.0625)]
    assert generation == 0


def test_adopt_cap0p5_r0p125():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.125)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 0.5
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(0.125)
    assert clock.sleeps == [pytest.approx(0.125)]
    assert generation == 0


def test_adopt_cap0p5_r0p1875():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.1875)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 0.5
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(0.1875)
    assert clock.sleeps == [pytest.approx(0.1875)]
    assert generation == 0


def test_adopt_cap0p5_r0p25():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.25)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 0.5
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(0.25)
    assert clock.sleeps == [pytest.approx(0.25)]
    assert generation == 0


def test_adopt_cap0p5_r0p3125():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.3125)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 0.5
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(0.3125)
    assert clock.sleeps == [pytest.approx(0.3125)]
    assert generation == 0


def test_adopt_cap0p5_r0p375():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.375)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 0.5
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(0.375)
    assert clock.sleeps == [pytest.approx(0.375)]
    assert generation == 0


def test_adopt_cap0p5_r0p4375():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.4375)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 0.5
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(0.4375)
    assert clock.sleeps == [pytest.approx(0.4375)]
    assert generation == 0


def test_adopt_cap0p5_r0p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.5)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 0.5
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(0.5)
    assert clock.sleeps == [pytest.approx(0.5)]
    assert generation == 0


def test_adopt_cap0p5_r0p625():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.625)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 0.5
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(0.5)
    assert clock.sleeps == [pytest.approx(0.5)]
    assert generation == 0


def test_adopt_cap0p5_r0p75():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.75)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 0.5
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(0.5)
    assert clock.sleeps == [pytest.approx(0.5)]
    assert generation == 0


def test_adopt_cap0p5_r0p875():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.875)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 0.5
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(0.5)
    assert clock.sleeps == [pytest.approx(0.5)]
    assert generation == 0


def test_adopt_cap0p5_r1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 1.0)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 0.5
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(0.5)
    assert clock.sleeps == [pytest.approx(0.5)]
    assert generation == 0


def test_adopt_cap0p5_r1p25():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 1.25)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 0.5
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(0.5)
    assert clock.sleeps == [pytest.approx(0.5)]
    assert generation == 0


def test_adopt_cap0p5_r1p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 1.5)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 0.5
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(0.5)
    assert clock.sleeps == [pytest.approx(0.5)]
    assert generation == 0


def test_adopt_cap0p5_r1p75():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 1.75)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 0.5
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(0.5)
    assert clock.sleeps == [pytest.approx(0.5)]
    assert generation == 0


def test_adopt_cap0p5_r2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 2.0)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 0.5
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(0.5)
    assert clock.sleeps == [pytest.approx(0.5)]
    assert generation == 0


def test_adopt_cap0p5_r2p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 2.5)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 0.5
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(0.5)
    assert clock.sleeps == [pytest.approx(0.5)]
    assert generation == 0


def test_adopt_cap0p5_r3():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 3.0)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 0.5
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(0.5)
    assert clock.sleeps == [pytest.approx(0.5)]
    assert generation == 0


def test_adopt_cap0p5_r3p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 3.5)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 0.5
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(0.5)
    assert clock.sleeps == [pytest.approx(0.5)]
    assert generation == 0


def test_adopt_cap0p5_r4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 0.5
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(0.5)
    assert clock.sleeps == [pytest.approx(0.5)]
    assert generation == 0


def test_adopt_cap0p5_r4p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.5)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 0.5
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(0.5)
    assert clock.sleeps == [pytest.approx(0.5)]
    assert generation == 0


def test_adopt_cap0p75_r0p05():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.05)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 0.75
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(0.05)
    assert clock.sleeps == [pytest.approx(0.05)]
    assert generation == 0


def test_adopt_cap0p75_r0p0625():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.0625)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 0.75
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(0.0625)
    assert clock.sleeps == [pytest.approx(0.0625)]
    assert generation == 0


def test_adopt_cap0p75_r0p125():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.125)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 0.75
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(0.125)
    assert clock.sleeps == [pytest.approx(0.125)]
    assert generation == 0


def test_adopt_cap0p75_r0p1875():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.1875)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 0.75
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(0.1875)
    assert clock.sleeps == [pytest.approx(0.1875)]
    assert generation == 0


def test_adopt_cap0p75_r0p25():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.25)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 0.75
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(0.25)
    assert clock.sleeps == [pytest.approx(0.25)]
    assert generation == 0


def test_adopt_cap0p75_r0p3125():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.3125)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 0.75
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(0.3125)
    assert clock.sleeps == [pytest.approx(0.3125)]
    assert generation == 0


def test_adopt_cap0p75_r0p375():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.375)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 0.75
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(0.375)
    assert clock.sleeps == [pytest.approx(0.375)]
    assert generation == 0


def test_adopt_cap0p75_r0p4375():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.4375)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 0.75
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(0.4375)
    assert clock.sleeps == [pytest.approx(0.4375)]
    assert generation == 0


def test_adopt_cap0p75_r0p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.5)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 0.75
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(0.5)
    assert clock.sleeps == [pytest.approx(0.5)]
    assert generation == 0


def test_adopt_cap0p75_r0p625():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.625)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 0.75
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(0.625)
    assert clock.sleeps == [pytest.approx(0.625)]
    assert generation == 0


def test_adopt_cap0p75_r0p75():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.75)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 0.75
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(0.75)
    assert clock.sleeps == [pytest.approx(0.75)]
    assert generation == 0


def test_adopt_cap0p75_r0p875():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.875)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 0.75
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(0.75)
    assert clock.sleeps == [pytest.approx(0.75)]
    assert generation == 0


def test_adopt_cap0p75_r1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 1.0)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 0.75
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(0.75)
    assert clock.sleeps == [pytest.approx(0.75)]
    assert generation == 0


def test_adopt_cap0p75_r1p25():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 1.25)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 0.75
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(0.75)
    assert clock.sleeps == [pytest.approx(0.75)]
    assert generation == 0


def test_adopt_cap0p75_r1p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 1.5)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 0.75
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(0.75)
    assert clock.sleeps == [pytest.approx(0.75)]
    assert generation == 0


def test_adopt_cap0p75_r1p75():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 1.75)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 0.75
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(0.75)
    assert clock.sleeps == [pytest.approx(0.75)]
    assert generation == 0


def test_adopt_cap0p75_r2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 2.0)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 0.75
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(0.75)
    assert clock.sleeps == [pytest.approx(0.75)]
    assert generation == 0


def test_adopt_cap0p75_r2p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 2.5)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 0.75
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(0.75)
    assert clock.sleeps == [pytest.approx(0.75)]
    assert generation == 0


def test_adopt_cap0p75_r3():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 3.0)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 0.75
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(0.75)
    assert clock.sleeps == [pytest.approx(0.75)]
    assert generation == 0


def test_adopt_cap0p75_r3p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 3.5)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 0.75
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(0.75)
    assert clock.sleeps == [pytest.approx(0.75)]
    assert generation == 0


def test_adopt_cap0p75_r4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 0.75
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(0.75)
    assert clock.sleeps == [pytest.approx(0.75)]
    assert generation == 0


def test_adopt_cap0p75_r4p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.5)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 0.75
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(0.75)
    assert clock.sleeps == [pytest.approx(0.75)]
    assert generation == 0


def test_adopt_cap1_r0p05():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.05)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 1.0
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(0.05)
    assert clock.sleeps == [pytest.approx(0.05)]
    assert generation == 0


def test_adopt_cap1_r0p0625():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.0625)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 1.0
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(0.0625)
    assert clock.sleeps == [pytest.approx(0.0625)]
    assert generation == 0


def test_adopt_cap1_r0p125():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.125)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 1.0
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(0.125)
    assert clock.sleeps == [pytest.approx(0.125)]
    assert generation == 0


def test_adopt_cap1_r0p1875():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.1875)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 1.0
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(0.1875)
    assert clock.sleeps == [pytest.approx(0.1875)]
    assert generation == 0


def test_adopt_cap1_r0p25():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.25)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 1.0
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(0.25)
    assert clock.sleeps == [pytest.approx(0.25)]
    assert generation == 0


def test_adopt_cap1_r0p3125():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.3125)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 1.0
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(0.3125)
    assert clock.sleeps == [pytest.approx(0.3125)]
    assert generation == 0


def test_adopt_cap1_r0p375():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.375)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 1.0
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(0.375)
    assert clock.sleeps == [pytest.approx(0.375)]
    assert generation == 0


def test_adopt_cap1_r0p4375():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.4375)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 1.0
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(0.4375)
    assert clock.sleeps == [pytest.approx(0.4375)]
    assert generation == 0


def test_adopt_cap1_r0p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.5)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 1.0
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(0.5)
    assert clock.sleeps == [pytest.approx(0.5)]
    assert generation == 0


def test_adopt_cap1_r0p625():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.625)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 1.0
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(0.625)
    assert clock.sleeps == [pytest.approx(0.625)]
    assert generation == 0


def test_adopt_cap1_r0p75():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.75)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 1.0
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(0.75)
    assert clock.sleeps == [pytest.approx(0.75)]
    assert generation == 0


def test_adopt_cap1_r0p875():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.875)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 1.0
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(0.875)
    assert clock.sleeps == [pytest.approx(0.875)]
    assert generation == 0


def test_adopt_cap1_r1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 1.0)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 1.0
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(1.0)
    assert clock.sleeps == [pytest.approx(1.0)]
    assert generation == 0


def test_adopt_cap1_r1p25():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 1.25)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 1.0
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(1.0)
    assert clock.sleeps == [pytest.approx(1.0)]
    assert generation == 0


def test_adopt_cap1_r1p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 1.5)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 1.0
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(1.0)
    assert clock.sleeps == [pytest.approx(1.0)]
    assert generation == 0


def test_adopt_cap1_r1p75():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 1.75)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 1.0
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(1.0)
    assert clock.sleeps == [pytest.approx(1.0)]
    assert generation == 0


def test_adopt_cap1_r2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 2.0)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 1.0
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(1.0)
    assert clock.sleeps == [pytest.approx(1.0)]
    assert generation == 0


def test_adopt_cap1_r2p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 2.5)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 1.0
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(1.0)
    assert clock.sleeps == [pytest.approx(1.0)]
    assert generation == 0


def test_adopt_cap1_r3():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 3.0)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 1.0
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(1.0)
    assert clock.sleeps == [pytest.approx(1.0)]
    assert generation == 0


def test_adopt_cap1_r3p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 3.5)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 1.0
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(1.0)
    assert clock.sleeps == [pytest.approx(1.0)]
    assert generation == 0


def test_adopt_cap1_r4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 1.0
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(1.0)
    assert clock.sleeps == [pytest.approx(1.0)]
    assert generation == 0


def test_adopt_cap1_r4p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.5)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 1.0
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(1.0)
    assert clock.sleeps == [pytest.approx(1.0)]
    assert generation == 0


def test_adopt_cap1p25_r0p05():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.05)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 1.25
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(0.05)
    assert clock.sleeps == [pytest.approx(0.05)]
    assert generation == 0


def test_adopt_cap1p25_r0p0625():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.0625)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 1.25
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(0.0625)
    assert clock.sleeps == [pytest.approx(0.0625)]
    assert generation == 0


def test_adopt_cap1p25_r0p125():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.125)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 1.25
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(0.125)
    assert clock.sleeps == [pytest.approx(0.125)]
    assert generation == 0


def test_adopt_cap1p25_r0p1875():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.1875)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 1.25
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(0.1875)
    assert clock.sleeps == [pytest.approx(0.1875)]
    assert generation == 0


def test_adopt_cap1p25_r0p25():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.25)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 1.25
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(0.25)
    assert clock.sleeps == [pytest.approx(0.25)]
    assert generation == 0


def test_adopt_cap1p25_r0p3125():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.3125)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 1.25
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(0.3125)
    assert clock.sleeps == [pytest.approx(0.3125)]
    assert generation == 0


def test_adopt_cap1p25_r0p375():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.375)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 1.25
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(0.375)
    assert clock.sleeps == [pytest.approx(0.375)]
    assert generation == 0


def test_adopt_cap1p25_r0p4375():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.4375)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 1.25
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(0.4375)
    assert clock.sleeps == [pytest.approx(0.4375)]
    assert generation == 0


def test_adopt_cap1p25_r0p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.5)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 1.25
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(0.5)
    assert clock.sleeps == [pytest.approx(0.5)]
    assert generation == 0


def test_adopt_cap1p25_r0p625():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.625)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 1.25
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(0.625)
    assert clock.sleeps == [pytest.approx(0.625)]
    assert generation == 0


def test_adopt_cap1p25_r0p75():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.75)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 1.25
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(0.75)
    assert clock.sleeps == [pytest.approx(0.75)]
    assert generation == 0


def test_adopt_cap1p25_r0p875():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.875)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 1.25
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(0.875)
    assert clock.sleeps == [pytest.approx(0.875)]
    assert generation == 0


def test_adopt_cap1p25_r1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 1.0)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 1.25
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(1.0)
    assert clock.sleeps == [pytest.approx(1.0)]
    assert generation == 0


def test_adopt_cap1p25_r1p25():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 1.25)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 1.25
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(1.25)
    assert clock.sleeps == [pytest.approx(1.25)]
    assert generation == 0


def test_adopt_cap1p25_r1p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 1.5)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 1.25
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(1.25)
    assert clock.sleeps == [pytest.approx(1.25)]
    assert generation == 0


def test_adopt_cap1p25_r1p75():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 1.75)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 1.25
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(1.25)
    assert clock.sleeps == [pytest.approx(1.25)]
    assert generation == 0


def test_adopt_cap1p25_r2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 2.0)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 1.25
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(1.25)
    assert clock.sleeps == [pytest.approx(1.25)]
    assert generation == 0


def test_adopt_cap1p25_r2p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 2.5)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 1.25
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(1.25)
    assert clock.sleeps == [pytest.approx(1.25)]
    assert generation == 0


def test_adopt_cap1p25_r3():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 3.0)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 1.25
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(1.25)
    assert clock.sleeps == [pytest.approx(1.25)]
    assert generation == 0


def test_adopt_cap1p25_r3p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 3.5)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 1.25
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(1.25)
    assert clock.sleeps == [pytest.approx(1.25)]
    assert generation == 0


def test_adopt_cap1p25_r4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 1.25
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(1.25)
    assert clock.sleeps == [pytest.approx(1.25)]
    assert generation == 0


def test_adopt_cap1p25_r4p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.5)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 1.25
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(1.25)
    assert clock.sleeps == [pytest.approx(1.25)]
    assert generation == 0


def test_adopt_cap1p5_r0p05():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.05)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 1.5
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(0.05)
    assert clock.sleeps == [pytest.approx(0.05)]
    assert generation == 0


def test_adopt_cap1p5_r0p0625():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.0625)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 1.5
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(0.0625)
    assert clock.sleeps == [pytest.approx(0.0625)]
    assert generation == 0


def test_adopt_cap1p5_r0p125():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.125)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 1.5
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(0.125)
    assert clock.sleeps == [pytest.approx(0.125)]
    assert generation == 0


def test_adopt_cap1p5_r0p1875():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.1875)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 1.5
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(0.1875)
    assert clock.sleeps == [pytest.approx(0.1875)]
    assert generation == 0


def test_adopt_cap1p5_r0p25():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.25)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 1.5
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(0.25)
    assert clock.sleeps == [pytest.approx(0.25)]
    assert generation == 0


def test_adopt_cap1p5_r0p3125():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.3125)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 1.5
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(0.3125)
    assert clock.sleeps == [pytest.approx(0.3125)]
    assert generation == 0


def test_adopt_cap1p5_r0p375():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.375)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 1.5
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(0.375)
    assert clock.sleeps == [pytest.approx(0.375)]
    assert generation == 0


def test_adopt_cap1p5_r0p4375():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.4375)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 1.5
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(0.4375)
    assert clock.sleeps == [pytest.approx(0.4375)]
    assert generation == 0


def test_adopt_cap1p5_r0p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.5)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 1.5
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(0.5)
    assert clock.sleeps == [pytest.approx(0.5)]
    assert generation == 0


def test_adopt_cap1p5_r0p625():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.625)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 1.5
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(0.625)
    assert clock.sleeps == [pytest.approx(0.625)]
    assert generation == 0


def test_adopt_cap1p5_r0p75():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.75)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 1.5
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(0.75)
    assert clock.sleeps == [pytest.approx(0.75)]
    assert generation == 0


def test_adopt_cap1p5_r0p875():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.875)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 1.5
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(0.875)
    assert clock.sleeps == [pytest.approx(0.875)]
    assert generation == 0


def test_adopt_cap1p5_r1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 1.0)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 1.5
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(1.0)
    assert clock.sleeps == [pytest.approx(1.0)]
    assert generation == 0


def test_adopt_cap1p5_r1p25():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 1.25)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 1.5
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(1.25)
    assert clock.sleeps == [pytest.approx(1.25)]
    assert generation == 0


def test_adopt_cap1p5_r1p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 1.5)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 1.5
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(1.5)
    assert clock.sleeps == [pytest.approx(1.5)]
    assert generation == 0


def test_adopt_cap1p5_r1p75():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 1.75)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 1.5
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(1.5)
    assert clock.sleeps == [pytest.approx(1.5)]
    assert generation == 0


def test_adopt_cap1p5_r2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 2.0)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 1.5
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(1.5)
    assert clock.sleeps == [pytest.approx(1.5)]
    assert generation == 0


def test_adopt_cap1p5_r2p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 2.5)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 1.5
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(1.5)
    assert clock.sleeps == [pytest.approx(1.5)]
    assert generation == 0


def test_adopt_cap1p5_r3():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 3.0)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 1.5
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(1.5)
    assert clock.sleeps == [pytest.approx(1.5)]
    assert generation == 0


def test_adopt_cap1p5_r3p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 3.5)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 1.5
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(1.5)
    assert clock.sleeps == [pytest.approx(1.5)]
    assert generation == 0


def test_adopt_cap1p5_r4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 1.5
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(1.5)
    assert clock.sleeps == [pytest.approx(1.5)]
    assert generation == 0


def test_adopt_cap1p5_r4p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.5)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 1.5
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(1.5)
    assert clock.sleeps == [pytest.approx(1.5)]
    assert generation == 0


def test_adopt_cap1p75_r0p05():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.05)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 1.75
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(0.05)
    assert clock.sleeps == [pytest.approx(0.05)]
    assert generation == 0


def test_adopt_cap1p75_r0p0625():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.0625)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 1.75
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(0.0625)
    assert clock.sleeps == [pytest.approx(0.0625)]
    assert generation == 0


def test_adopt_cap1p75_r0p125():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.125)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 1.75
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(0.125)
    assert clock.sleeps == [pytest.approx(0.125)]
    assert generation == 0


def test_adopt_cap1p75_r0p1875():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.1875)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 1.75
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(0.1875)
    assert clock.sleeps == [pytest.approx(0.1875)]
    assert generation == 0


def test_adopt_cap1p75_r0p25():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.25)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 1.75
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(0.25)
    assert clock.sleeps == [pytest.approx(0.25)]
    assert generation == 0


def test_adopt_cap1p75_r0p3125():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.3125)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 1.75
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(0.3125)
    assert clock.sleeps == [pytest.approx(0.3125)]
    assert generation == 0


def test_adopt_cap1p75_r0p375():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.375)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 1.75
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(0.375)
    assert clock.sleeps == [pytest.approx(0.375)]
    assert generation == 0


def test_adopt_cap1p75_r0p4375():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.4375)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 1.75
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(0.4375)
    assert clock.sleeps == [pytest.approx(0.4375)]
    assert generation == 0


def test_adopt_cap1p75_r0p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.5)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 1.75
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(0.5)
    assert clock.sleeps == [pytest.approx(0.5)]
    assert generation == 0


def test_adopt_cap1p75_r0p625():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.625)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 1.75
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(0.625)
    assert clock.sleeps == [pytest.approx(0.625)]
    assert generation == 0


def test_adopt_cap1p75_r0p75():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.75)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 1.75
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(0.75)
    assert clock.sleeps == [pytest.approx(0.75)]
    assert generation == 0


def test_adopt_cap1p75_r0p875():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.875)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 1.75
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(0.875)
    assert clock.sleeps == [pytest.approx(0.875)]
    assert generation == 0


def test_adopt_cap1p75_r1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 1.0)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 1.75
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(1.0)
    assert clock.sleeps == [pytest.approx(1.0)]
    assert generation == 0


def test_adopt_cap1p75_r1p25():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 1.25)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 1.75
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(1.25)
    assert clock.sleeps == [pytest.approx(1.25)]
    assert generation == 0


def test_adopt_cap1p75_r1p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 1.5)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 1.75
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(1.5)
    assert clock.sleeps == [pytest.approx(1.5)]
    assert generation == 0


def test_adopt_cap1p75_r1p75():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 1.75)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 1.75
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(1.75)
    assert clock.sleeps == [pytest.approx(1.75)]
    assert generation == 0


def test_adopt_cap1p75_r2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 2.0)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 1.75
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(1.75)
    assert clock.sleeps == [pytest.approx(1.75)]
    assert generation == 0


def test_adopt_cap1p75_r2p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 2.5)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 1.75
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(1.75)
    assert clock.sleeps == [pytest.approx(1.75)]
    assert generation == 0


def test_adopt_cap1p75_r3():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 3.0)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 1.75
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(1.75)
    assert clock.sleeps == [pytest.approx(1.75)]
    assert generation == 0


def test_adopt_cap1p75_r3p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 3.5)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 1.75
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(1.75)
    assert clock.sleeps == [pytest.approx(1.75)]
    assert generation == 0


def test_adopt_cap1p75_r4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 1.75
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(1.75)
    assert clock.sleeps == [pytest.approx(1.75)]
    assert generation == 0


def test_adopt_cap1p75_r4p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.5)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 1.75
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(1.75)
    assert clock.sleeps == [pytest.approx(1.75)]
    assert generation == 0


def test_adopt_cap2_r0p05():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.05)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 2.0
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(0.05)
    assert clock.sleeps == [pytest.approx(0.05)]
    assert generation == 0


def test_adopt_cap2_r0p0625():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.0625)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 2.0
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(0.0625)
    assert clock.sleeps == [pytest.approx(0.0625)]
    assert generation == 0


def test_adopt_cap2_r0p125():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.125)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 2.0
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(0.125)
    assert clock.sleeps == [pytest.approx(0.125)]
    assert generation == 0


def test_adopt_cap2_r0p1875():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.1875)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 2.0
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(0.1875)
    assert clock.sleeps == [pytest.approx(0.1875)]
    assert generation == 0


def test_adopt_cap2_r0p25():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.25)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 2.0
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(0.25)
    assert clock.sleeps == [pytest.approx(0.25)]
    assert generation == 0


def test_adopt_cap2_r0p3125():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.3125)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 2.0
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(0.3125)
    assert clock.sleeps == [pytest.approx(0.3125)]
    assert generation == 0


def test_adopt_cap2_r0p375():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.375)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 2.0
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(0.375)
    assert clock.sleeps == [pytest.approx(0.375)]
    assert generation == 0


def test_adopt_cap2_r0p4375():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.4375)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 2.0
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(0.4375)
    assert clock.sleeps == [pytest.approx(0.4375)]
    assert generation == 0


def test_adopt_cap2_r0p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.5)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 2.0
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(0.5)
    assert clock.sleeps == [pytest.approx(0.5)]
    assert generation == 0


def test_adopt_cap2_r0p625():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.625)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 2.0
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(0.625)
    assert clock.sleeps == [pytest.approx(0.625)]
    assert generation == 0


def test_adopt_cap2_r0p75():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.75)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 2.0
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(0.75)
    assert clock.sleeps == [pytest.approx(0.75)]
    assert generation == 0


def test_adopt_cap2_r0p875():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.875)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 2.0
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(0.875)
    assert clock.sleeps == [pytest.approx(0.875)]
    assert generation == 0


def test_adopt_cap2_r1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 1.0)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 2.0
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(1.0)
    assert clock.sleeps == [pytest.approx(1.0)]
    assert generation == 0


def test_adopt_cap2_r1p25():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 1.25)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 2.0
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(1.25)
    assert clock.sleeps == [pytest.approx(1.25)]
    assert generation == 0


def test_adopt_cap2_r1p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 1.5)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 2.0
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(1.5)
    assert clock.sleeps == [pytest.approx(1.5)]
    assert generation == 0


def test_adopt_cap2_r1p75():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 1.75)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 2.0
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(1.75)
    assert clock.sleeps == [pytest.approx(1.75)]
    assert generation == 0


def test_adopt_cap2_r2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 2.0)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 2.0
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(2.0)
    assert clock.sleeps == [pytest.approx(2.0)]
    assert generation == 0


def test_adopt_cap2_r2p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 2.5)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 2.0
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(2.0)
    assert clock.sleeps == [pytest.approx(2.0)]
    assert generation == 0


def test_adopt_cap2_r3():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 3.0)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 2.0
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(2.0)
    assert clock.sleeps == [pytest.approx(2.0)]
    assert generation == 0


def test_adopt_cap2_r3p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 3.5)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 2.0
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(2.0)
    assert clock.sleeps == [pytest.approx(2.0)]
    assert generation == 0


def test_adopt_cap2_r4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 2.0
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(2.0)
    assert clock.sleeps == [pytest.approx(2.0)]
    assert generation == 0


def test_adopt_cap2_r4p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.5)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 2.0
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(2.0)
    assert clock.sleeps == [pytest.approx(2.0)]
    assert generation == 0


def test_prec_o0p125_f0p125_snone():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._armed_until['batch_claim'] = NOW0 + 0.125  # the label's own process window
    damper._generations['batch_claim'] = 1
    seed_window_doc(client, 'batch_pipeline_dev', 'batch_claim', WALL0 + 0.125)
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(0.125)
    assert clock.sleeps == [pytest.approx(0.125)]
    assert window.spill_absent_reads == 0  # no consult reached the spill lane at all


def test_prec_o0p125_f0p125_s0p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._armed_until['batch_claim'] = NOW0 + 0.125  # the label's own process window
    damper._generations['batch_claim'] = 1
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.5)
    seed_window_doc(client, 'batch_pipeline_dev', 'batch_claim', WALL0 + 0.125)
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(0.125)
    assert clock.sleeps == [pytest.approx(0.125)]
    assert window.spill_reads == 0  # the spill is never read when the label windows cover


def test_prec_o0p125_f0p125_s2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._armed_until['batch_claim'] = NOW0 + 0.125  # the label's own process window
    damper._generations['batch_claim'] = 1
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 2.0)
    seed_window_doc(client, 'batch_pipeline_dev', 'batch_claim', WALL0 + 0.125)
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(0.125)
    assert clock.sleeps == [pytest.approx(0.125)]
    assert window.spill_reads == 0  # the spill is never read when the label windows cover


def test_prec_o0p125_f0p125_s4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._armed_until['batch_claim'] = NOW0 + 0.125  # the label's own process window
    damper._generations['batch_claim'] = 1
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    seed_window_doc(client, 'batch_pipeline_dev', 'batch_claim', WALL0 + 0.125)
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(0.125)
    assert clock.sleeps == [pytest.approx(0.125)]
    assert window.spill_reads == 0  # the spill is never read when the label windows cover


def test_prec_o0p125_f0p25_snone():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._armed_until['batch_claim'] = NOW0 + 0.125  # the label's own process window
    damper._generations['batch_claim'] = 1
    seed_window_doc(client, 'batch_pipeline_dev', 'batch_claim', WALL0 + 0.25)
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(0.25)
    assert clock.sleeps == [pytest.approx(0.25)]
    assert window.spill_absent_reads == 0  # no consult reached the spill lane at all


def test_prec_o0p125_f0p25_s0p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._armed_until['batch_claim'] = NOW0 + 0.125  # the label's own process window
    damper._generations['batch_claim'] = 1
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.5)
    seed_window_doc(client, 'batch_pipeline_dev', 'batch_claim', WALL0 + 0.25)
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(0.25)
    assert clock.sleeps == [pytest.approx(0.25)]
    assert window.spill_reads == 0  # the spill is never read when the label windows cover


def test_prec_o0p125_f0p25_s2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._armed_until['batch_claim'] = NOW0 + 0.125  # the label's own process window
    damper._generations['batch_claim'] = 1
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 2.0)
    seed_window_doc(client, 'batch_pipeline_dev', 'batch_claim', WALL0 + 0.25)
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(0.25)
    assert clock.sleeps == [pytest.approx(0.25)]
    assert window.spill_reads == 0  # the spill is never read when the label windows cover


def test_prec_o0p125_f0p25_s4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._armed_until['batch_claim'] = NOW0 + 0.125  # the label's own process window
    damper._generations['batch_claim'] = 1
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    seed_window_doc(client, 'batch_pipeline_dev', 'batch_claim', WALL0 + 0.25)
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(0.25)
    assert clock.sleeps == [pytest.approx(0.25)]
    assert window.spill_reads == 0  # the spill is never read when the label windows cover


def test_prec_o0p125_f0p5_snone():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._armed_until['batch_claim'] = NOW0 + 0.125  # the label's own process window
    damper._generations['batch_claim'] = 1
    seed_window_doc(client, 'batch_pipeline_dev', 'batch_claim', WALL0 + 0.5)
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(0.5)
    assert clock.sleeps == [pytest.approx(0.5)]
    assert window.spill_absent_reads == 0  # no consult reached the spill lane at all


def test_prec_o0p125_f0p5_s0p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._armed_until['batch_claim'] = NOW0 + 0.125  # the label's own process window
    damper._generations['batch_claim'] = 1
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.5)
    seed_window_doc(client, 'batch_pipeline_dev', 'batch_claim', WALL0 + 0.5)
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(0.5)
    assert clock.sleeps == [pytest.approx(0.5)]
    assert window.spill_reads == 0  # the spill is never read when the label windows cover


def test_prec_o0p125_f0p5_s2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._armed_until['batch_claim'] = NOW0 + 0.125  # the label's own process window
    damper._generations['batch_claim'] = 1
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 2.0)
    seed_window_doc(client, 'batch_pipeline_dev', 'batch_claim', WALL0 + 0.5)
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(0.5)
    assert clock.sleeps == [pytest.approx(0.5)]
    assert window.spill_reads == 0  # the spill is never read when the label windows cover


def test_prec_o0p125_f0p5_s4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._armed_until['batch_claim'] = NOW0 + 0.125  # the label's own process window
    damper._generations['batch_claim'] = 1
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    seed_window_doc(client, 'batch_pipeline_dev', 'batch_claim', WALL0 + 0.5)
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(0.5)
    assert clock.sleeps == [pytest.approx(0.5)]
    assert window.spill_reads == 0  # the spill is never read when the label windows cover


def test_prec_o0p125_f1_snone():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._armed_until['batch_claim'] = NOW0 + 0.125  # the label's own process window
    damper._generations['batch_claim'] = 1
    seed_window_doc(client, 'batch_pipeline_dev', 'batch_claim', WALL0 + 1.0)
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(1.0)
    assert clock.sleeps == [pytest.approx(1.0)]
    assert window.spill_absent_reads == 0  # no consult reached the spill lane at all


def test_prec_o0p125_f1_s0p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._armed_until['batch_claim'] = NOW0 + 0.125  # the label's own process window
    damper._generations['batch_claim'] = 1
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.5)
    seed_window_doc(client, 'batch_pipeline_dev', 'batch_claim', WALL0 + 1.0)
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(1.0)
    assert clock.sleeps == [pytest.approx(1.0)]
    assert window.spill_reads == 0  # the spill is never read when the label windows cover


def test_prec_o0p125_f1_s2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._armed_until['batch_claim'] = NOW0 + 0.125  # the label's own process window
    damper._generations['batch_claim'] = 1
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 2.0)
    seed_window_doc(client, 'batch_pipeline_dev', 'batch_claim', WALL0 + 1.0)
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(1.0)
    assert clock.sleeps == [pytest.approx(1.0)]
    assert window.spill_reads == 0  # the spill is never read when the label windows cover


def test_prec_o0p125_f1_s4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._armed_until['batch_claim'] = NOW0 + 0.125  # the label's own process window
    damper._generations['batch_claim'] = 1
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    seed_window_doc(client, 'batch_pipeline_dev', 'batch_claim', WALL0 + 1.0)
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(1.0)
    assert clock.sleeps == [pytest.approx(1.0)]
    assert window.spill_reads == 0  # the spill is never read when the label windows cover


def test_prec_o0p125_f2_snone():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._armed_until['batch_claim'] = NOW0 + 0.125  # the label's own process window
    damper._generations['batch_claim'] = 1
    seed_window_doc(client, 'batch_pipeline_dev', 'batch_claim', WALL0 + 2.0)
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(2.0)
    assert clock.sleeps == [pytest.approx(2.0)]
    assert window.spill_absent_reads == 0  # no consult reached the spill lane at all


def test_prec_o0p125_f2_s0p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._armed_until['batch_claim'] = NOW0 + 0.125  # the label's own process window
    damper._generations['batch_claim'] = 1
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.5)
    seed_window_doc(client, 'batch_pipeline_dev', 'batch_claim', WALL0 + 2.0)
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(2.0)
    assert clock.sleeps == [pytest.approx(2.0)]
    assert window.spill_reads == 0  # the spill is never read when the label windows cover


def test_prec_o0p125_f2_s2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._armed_until['batch_claim'] = NOW0 + 0.125  # the label's own process window
    damper._generations['batch_claim'] = 1
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 2.0)
    seed_window_doc(client, 'batch_pipeline_dev', 'batch_claim', WALL0 + 2.0)
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(2.0)
    assert clock.sleeps == [pytest.approx(2.0)]
    assert window.spill_reads == 0  # the spill is never read when the label windows cover


def test_prec_o0p125_f2_s4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._armed_until['batch_claim'] = NOW0 + 0.125  # the label's own process window
    damper._generations['batch_claim'] = 1
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    seed_window_doc(client, 'batch_pipeline_dev', 'batch_claim', WALL0 + 2.0)
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(2.0)
    assert clock.sleeps == [pytest.approx(2.0)]
    assert window.spill_reads == 0  # the spill is never read when the label windows cover


def test_prec_o0p125_f4_snone():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._armed_until['batch_claim'] = NOW0 + 0.125  # the label's own process window
    damper._generations['batch_claim'] = 1
    seed_window_doc(client, 'batch_pipeline_dev', 'batch_claim', WALL0 + 4.0)
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(4.0)
    assert clock.sleeps == [pytest.approx(4.0)]
    assert window.spill_absent_reads == 0  # no consult reached the spill lane at all


def test_prec_o0p125_f4_s0p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._armed_until['batch_claim'] = NOW0 + 0.125  # the label's own process window
    damper._generations['batch_claim'] = 1
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.5)
    seed_window_doc(client, 'batch_pipeline_dev', 'batch_claim', WALL0 + 4.0)
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(4.0)
    assert clock.sleeps == [pytest.approx(4.0)]
    assert window.spill_reads == 0  # the spill is never read when the label windows cover


def test_prec_o0p125_f4_s2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._armed_until['batch_claim'] = NOW0 + 0.125  # the label's own process window
    damper._generations['batch_claim'] = 1
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 2.0)
    seed_window_doc(client, 'batch_pipeline_dev', 'batch_claim', WALL0 + 4.0)
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(4.0)
    assert clock.sleeps == [pytest.approx(4.0)]
    assert window.spill_reads == 0  # the spill is never read when the label windows cover


def test_prec_o0p125_f4_s4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._armed_until['batch_claim'] = NOW0 + 0.125  # the label's own process window
    damper._generations['batch_claim'] = 1
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    seed_window_doc(client, 'batch_pipeline_dev', 'batch_claim', WALL0 + 4.0)
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(4.0)
    assert clock.sleeps == [pytest.approx(4.0)]
    assert window.spill_reads == 0  # the spill is never read when the label windows cover


def test_prec_o0p25_f0p125_snone():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._armed_until['batch_claim'] = NOW0 + 0.25  # the label's own process window
    damper._generations['batch_claim'] = 1
    seed_window_doc(client, 'batch_pipeline_dev', 'batch_claim', WALL0 + 0.125)
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(0.25)
    assert clock.sleeps == [pytest.approx(0.25)]
    assert window.spill_absent_reads == 0  # no consult reached the spill lane at all


def test_prec_o0p25_f0p125_s0p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._armed_until['batch_claim'] = NOW0 + 0.25  # the label's own process window
    damper._generations['batch_claim'] = 1
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.5)
    seed_window_doc(client, 'batch_pipeline_dev', 'batch_claim', WALL0 + 0.125)
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(0.25)
    assert clock.sleeps == [pytest.approx(0.25)]
    assert window.spill_reads == 0  # the spill is never read when the label windows cover


def test_prec_o0p25_f0p125_s2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._armed_until['batch_claim'] = NOW0 + 0.25  # the label's own process window
    damper._generations['batch_claim'] = 1
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 2.0)
    seed_window_doc(client, 'batch_pipeline_dev', 'batch_claim', WALL0 + 0.125)
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(0.25)
    assert clock.sleeps == [pytest.approx(0.25)]
    assert window.spill_reads == 0  # the spill is never read when the label windows cover


def test_prec_o0p25_f0p125_s4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._armed_until['batch_claim'] = NOW0 + 0.25  # the label's own process window
    damper._generations['batch_claim'] = 1
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    seed_window_doc(client, 'batch_pipeline_dev', 'batch_claim', WALL0 + 0.125)
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(0.25)
    assert clock.sleeps == [pytest.approx(0.25)]
    assert window.spill_reads == 0  # the spill is never read when the label windows cover


def test_prec_o0p25_f0p25_snone():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._armed_until['batch_claim'] = NOW0 + 0.25  # the label's own process window
    damper._generations['batch_claim'] = 1
    seed_window_doc(client, 'batch_pipeline_dev', 'batch_claim', WALL0 + 0.25)
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(0.25)
    assert clock.sleeps == [pytest.approx(0.25)]
    assert window.spill_absent_reads == 0  # no consult reached the spill lane at all


def test_prec_o0p25_f0p25_s0p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._armed_until['batch_claim'] = NOW0 + 0.25  # the label's own process window
    damper._generations['batch_claim'] = 1
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.5)
    seed_window_doc(client, 'batch_pipeline_dev', 'batch_claim', WALL0 + 0.25)
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(0.25)
    assert clock.sleeps == [pytest.approx(0.25)]
    assert window.spill_reads == 0  # the spill is never read when the label windows cover


def test_prec_o0p25_f0p25_s2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._armed_until['batch_claim'] = NOW0 + 0.25  # the label's own process window
    damper._generations['batch_claim'] = 1
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 2.0)
    seed_window_doc(client, 'batch_pipeline_dev', 'batch_claim', WALL0 + 0.25)
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(0.25)
    assert clock.sleeps == [pytest.approx(0.25)]
    assert window.spill_reads == 0  # the spill is never read when the label windows cover


def test_prec_o0p25_f0p25_s4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._armed_until['batch_claim'] = NOW0 + 0.25  # the label's own process window
    damper._generations['batch_claim'] = 1
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    seed_window_doc(client, 'batch_pipeline_dev', 'batch_claim', WALL0 + 0.25)
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(0.25)
    assert clock.sleeps == [pytest.approx(0.25)]
    assert window.spill_reads == 0  # the spill is never read when the label windows cover


def test_prec_o0p25_f0p5_snone():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._armed_until['batch_claim'] = NOW0 + 0.25  # the label's own process window
    damper._generations['batch_claim'] = 1
    seed_window_doc(client, 'batch_pipeline_dev', 'batch_claim', WALL0 + 0.5)
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(0.5)
    assert clock.sleeps == [pytest.approx(0.5)]
    assert window.spill_absent_reads == 0  # no consult reached the spill lane at all


def test_prec_o0p25_f0p5_s0p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._armed_until['batch_claim'] = NOW0 + 0.25  # the label's own process window
    damper._generations['batch_claim'] = 1
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.5)
    seed_window_doc(client, 'batch_pipeline_dev', 'batch_claim', WALL0 + 0.5)
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(0.5)
    assert clock.sleeps == [pytest.approx(0.5)]
    assert window.spill_reads == 0  # the spill is never read when the label windows cover


def test_prec_o0p25_f0p5_s2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._armed_until['batch_claim'] = NOW0 + 0.25  # the label's own process window
    damper._generations['batch_claim'] = 1
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 2.0)
    seed_window_doc(client, 'batch_pipeline_dev', 'batch_claim', WALL0 + 0.5)
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(0.5)
    assert clock.sleeps == [pytest.approx(0.5)]
    assert window.spill_reads == 0  # the spill is never read when the label windows cover


def test_prec_o0p25_f0p5_s4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._armed_until['batch_claim'] = NOW0 + 0.25  # the label's own process window
    damper._generations['batch_claim'] = 1
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    seed_window_doc(client, 'batch_pipeline_dev', 'batch_claim', WALL0 + 0.5)
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(0.5)
    assert clock.sleeps == [pytest.approx(0.5)]
    assert window.spill_reads == 0  # the spill is never read when the label windows cover


def test_prec_o0p25_f1_snone():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._armed_until['batch_claim'] = NOW0 + 0.25  # the label's own process window
    damper._generations['batch_claim'] = 1
    seed_window_doc(client, 'batch_pipeline_dev', 'batch_claim', WALL0 + 1.0)
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(1.0)
    assert clock.sleeps == [pytest.approx(1.0)]
    assert window.spill_absent_reads == 0  # no consult reached the spill lane at all


def test_prec_o0p25_f1_s0p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._armed_until['batch_claim'] = NOW0 + 0.25  # the label's own process window
    damper._generations['batch_claim'] = 1
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.5)
    seed_window_doc(client, 'batch_pipeline_dev', 'batch_claim', WALL0 + 1.0)
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(1.0)
    assert clock.sleeps == [pytest.approx(1.0)]
    assert window.spill_reads == 0  # the spill is never read when the label windows cover


def test_prec_o0p25_f1_s2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._armed_until['batch_claim'] = NOW0 + 0.25  # the label's own process window
    damper._generations['batch_claim'] = 1
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 2.0)
    seed_window_doc(client, 'batch_pipeline_dev', 'batch_claim', WALL0 + 1.0)
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(1.0)
    assert clock.sleeps == [pytest.approx(1.0)]
    assert window.spill_reads == 0  # the spill is never read when the label windows cover


def test_prec_o0p25_f1_s4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._armed_until['batch_claim'] = NOW0 + 0.25  # the label's own process window
    damper._generations['batch_claim'] = 1
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    seed_window_doc(client, 'batch_pipeline_dev', 'batch_claim', WALL0 + 1.0)
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(1.0)
    assert clock.sleeps == [pytest.approx(1.0)]
    assert window.spill_reads == 0  # the spill is never read when the label windows cover


def test_prec_o0p25_f2_snone():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._armed_until['batch_claim'] = NOW0 + 0.25  # the label's own process window
    damper._generations['batch_claim'] = 1
    seed_window_doc(client, 'batch_pipeline_dev', 'batch_claim', WALL0 + 2.0)
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(2.0)
    assert clock.sleeps == [pytest.approx(2.0)]
    assert window.spill_absent_reads == 0  # no consult reached the spill lane at all


def test_prec_o0p25_f2_s0p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._armed_until['batch_claim'] = NOW0 + 0.25  # the label's own process window
    damper._generations['batch_claim'] = 1
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.5)
    seed_window_doc(client, 'batch_pipeline_dev', 'batch_claim', WALL0 + 2.0)
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(2.0)
    assert clock.sleeps == [pytest.approx(2.0)]
    assert window.spill_reads == 0  # the spill is never read when the label windows cover


def test_prec_o0p25_f2_s2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._armed_until['batch_claim'] = NOW0 + 0.25  # the label's own process window
    damper._generations['batch_claim'] = 1
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 2.0)
    seed_window_doc(client, 'batch_pipeline_dev', 'batch_claim', WALL0 + 2.0)
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(2.0)
    assert clock.sleeps == [pytest.approx(2.0)]
    assert window.spill_reads == 0  # the spill is never read when the label windows cover


def test_prec_o0p25_f2_s4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._armed_until['batch_claim'] = NOW0 + 0.25  # the label's own process window
    damper._generations['batch_claim'] = 1
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    seed_window_doc(client, 'batch_pipeline_dev', 'batch_claim', WALL0 + 2.0)
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(2.0)
    assert clock.sleeps == [pytest.approx(2.0)]
    assert window.spill_reads == 0  # the spill is never read when the label windows cover


def test_prec_o0p25_f4_snone():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._armed_until['batch_claim'] = NOW0 + 0.25  # the label's own process window
    damper._generations['batch_claim'] = 1
    seed_window_doc(client, 'batch_pipeline_dev', 'batch_claim', WALL0 + 4.0)
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(4.0)
    assert clock.sleeps == [pytest.approx(4.0)]
    assert window.spill_absent_reads == 0  # no consult reached the spill lane at all


def test_prec_o0p25_f4_s0p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._armed_until['batch_claim'] = NOW0 + 0.25  # the label's own process window
    damper._generations['batch_claim'] = 1
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.5)
    seed_window_doc(client, 'batch_pipeline_dev', 'batch_claim', WALL0 + 4.0)
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(4.0)
    assert clock.sleeps == [pytest.approx(4.0)]
    assert window.spill_reads == 0  # the spill is never read when the label windows cover


def test_prec_o0p25_f4_s2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._armed_until['batch_claim'] = NOW0 + 0.25  # the label's own process window
    damper._generations['batch_claim'] = 1
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 2.0)
    seed_window_doc(client, 'batch_pipeline_dev', 'batch_claim', WALL0 + 4.0)
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(4.0)
    assert clock.sleeps == [pytest.approx(4.0)]
    assert window.spill_reads == 0  # the spill is never read when the label windows cover


def test_prec_o0p25_f4_s4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._armed_until['batch_claim'] = NOW0 + 0.25  # the label's own process window
    damper._generations['batch_claim'] = 1
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    seed_window_doc(client, 'batch_pipeline_dev', 'batch_claim', WALL0 + 4.0)
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(4.0)
    assert clock.sleeps == [pytest.approx(4.0)]
    assert window.spill_reads == 0  # the spill is never read when the label windows cover


def test_prec_o0p5_f0p125_snone():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._armed_until['batch_claim'] = NOW0 + 0.5  # the label's own process window
    damper._generations['batch_claim'] = 1
    seed_window_doc(client, 'batch_pipeline_dev', 'batch_claim', WALL0 + 0.125)
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(0.5)
    assert clock.sleeps == [pytest.approx(0.5)]
    assert window.spill_absent_reads == 0  # no consult reached the spill lane at all


def test_prec_o0p5_f0p125_s0p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._armed_until['batch_claim'] = NOW0 + 0.5  # the label's own process window
    damper._generations['batch_claim'] = 1
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.5)
    seed_window_doc(client, 'batch_pipeline_dev', 'batch_claim', WALL0 + 0.125)
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(0.5)
    assert clock.sleeps == [pytest.approx(0.5)]
    assert window.spill_reads == 0  # the spill is never read when the label windows cover


def test_prec_o0p5_f0p125_s2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._armed_until['batch_claim'] = NOW0 + 0.5  # the label's own process window
    damper._generations['batch_claim'] = 1
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 2.0)
    seed_window_doc(client, 'batch_pipeline_dev', 'batch_claim', WALL0 + 0.125)
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(0.5)
    assert clock.sleeps == [pytest.approx(0.5)]
    assert window.spill_reads == 0  # the spill is never read when the label windows cover


def test_prec_o0p5_f0p125_s4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._armed_until['batch_claim'] = NOW0 + 0.5  # the label's own process window
    damper._generations['batch_claim'] = 1
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    seed_window_doc(client, 'batch_pipeline_dev', 'batch_claim', WALL0 + 0.125)
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(0.5)
    assert clock.sleeps == [pytest.approx(0.5)]
    assert window.spill_reads == 0  # the spill is never read when the label windows cover


def test_prec_o0p5_f0p25_snone():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._armed_until['batch_claim'] = NOW0 + 0.5  # the label's own process window
    damper._generations['batch_claim'] = 1
    seed_window_doc(client, 'batch_pipeline_dev', 'batch_claim', WALL0 + 0.25)
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(0.5)
    assert clock.sleeps == [pytest.approx(0.5)]
    assert window.spill_absent_reads == 0  # no consult reached the spill lane at all


def test_prec_o0p5_f0p25_s0p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._armed_until['batch_claim'] = NOW0 + 0.5  # the label's own process window
    damper._generations['batch_claim'] = 1
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.5)
    seed_window_doc(client, 'batch_pipeline_dev', 'batch_claim', WALL0 + 0.25)
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(0.5)
    assert clock.sleeps == [pytest.approx(0.5)]
    assert window.spill_reads == 0  # the spill is never read when the label windows cover


def test_prec_o0p5_f0p25_s2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._armed_until['batch_claim'] = NOW0 + 0.5  # the label's own process window
    damper._generations['batch_claim'] = 1
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 2.0)
    seed_window_doc(client, 'batch_pipeline_dev', 'batch_claim', WALL0 + 0.25)
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(0.5)
    assert clock.sleeps == [pytest.approx(0.5)]
    assert window.spill_reads == 0  # the spill is never read when the label windows cover


def test_prec_o0p5_f0p25_s4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._armed_until['batch_claim'] = NOW0 + 0.5  # the label's own process window
    damper._generations['batch_claim'] = 1
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    seed_window_doc(client, 'batch_pipeline_dev', 'batch_claim', WALL0 + 0.25)
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(0.5)
    assert clock.sleeps == [pytest.approx(0.5)]
    assert window.spill_reads == 0  # the spill is never read when the label windows cover


def test_prec_o0p5_f0p5_snone():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._armed_until['batch_claim'] = NOW0 + 0.5  # the label's own process window
    damper._generations['batch_claim'] = 1
    seed_window_doc(client, 'batch_pipeline_dev', 'batch_claim', WALL0 + 0.5)
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(0.5)
    assert clock.sleeps == [pytest.approx(0.5)]
    assert window.spill_absent_reads == 0  # no consult reached the spill lane at all


def test_prec_o0p5_f0p5_s0p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._armed_until['batch_claim'] = NOW0 + 0.5  # the label's own process window
    damper._generations['batch_claim'] = 1
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.5)
    seed_window_doc(client, 'batch_pipeline_dev', 'batch_claim', WALL0 + 0.5)
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(0.5)
    assert clock.sleeps == [pytest.approx(0.5)]
    assert window.spill_reads == 0  # the spill is never read when the label windows cover


def test_prec_o0p5_f0p5_s2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._armed_until['batch_claim'] = NOW0 + 0.5  # the label's own process window
    damper._generations['batch_claim'] = 1
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 2.0)
    seed_window_doc(client, 'batch_pipeline_dev', 'batch_claim', WALL0 + 0.5)
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(0.5)
    assert clock.sleeps == [pytest.approx(0.5)]
    assert window.spill_reads == 0  # the spill is never read when the label windows cover


def test_prec_o0p5_f0p5_s4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._armed_until['batch_claim'] = NOW0 + 0.5  # the label's own process window
    damper._generations['batch_claim'] = 1
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    seed_window_doc(client, 'batch_pipeline_dev', 'batch_claim', WALL0 + 0.5)
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(0.5)
    assert clock.sleeps == [pytest.approx(0.5)]
    assert window.spill_reads == 0  # the spill is never read when the label windows cover


def test_prec_o0p5_f1_snone():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._armed_until['batch_claim'] = NOW0 + 0.5  # the label's own process window
    damper._generations['batch_claim'] = 1
    seed_window_doc(client, 'batch_pipeline_dev', 'batch_claim', WALL0 + 1.0)
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(1.0)
    assert clock.sleeps == [pytest.approx(1.0)]
    assert window.spill_absent_reads == 0  # no consult reached the spill lane at all


def test_prec_o0p5_f1_s0p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._armed_until['batch_claim'] = NOW0 + 0.5  # the label's own process window
    damper._generations['batch_claim'] = 1
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.5)
    seed_window_doc(client, 'batch_pipeline_dev', 'batch_claim', WALL0 + 1.0)
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(1.0)
    assert clock.sleeps == [pytest.approx(1.0)]
    assert window.spill_reads == 0  # the spill is never read when the label windows cover


def test_prec_o0p5_f1_s2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._armed_until['batch_claim'] = NOW0 + 0.5  # the label's own process window
    damper._generations['batch_claim'] = 1
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 2.0)
    seed_window_doc(client, 'batch_pipeline_dev', 'batch_claim', WALL0 + 1.0)
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(1.0)
    assert clock.sleeps == [pytest.approx(1.0)]
    assert window.spill_reads == 0  # the spill is never read when the label windows cover


def test_prec_o0p5_f1_s4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._armed_until['batch_claim'] = NOW0 + 0.5  # the label's own process window
    damper._generations['batch_claim'] = 1
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    seed_window_doc(client, 'batch_pipeline_dev', 'batch_claim', WALL0 + 1.0)
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(1.0)
    assert clock.sleeps == [pytest.approx(1.0)]
    assert window.spill_reads == 0  # the spill is never read when the label windows cover


def test_prec_o0p5_f2_snone():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._armed_until['batch_claim'] = NOW0 + 0.5  # the label's own process window
    damper._generations['batch_claim'] = 1
    seed_window_doc(client, 'batch_pipeline_dev', 'batch_claim', WALL0 + 2.0)
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(2.0)
    assert clock.sleeps == [pytest.approx(2.0)]
    assert window.spill_absent_reads == 0  # no consult reached the spill lane at all


def test_prec_o0p5_f2_s0p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._armed_until['batch_claim'] = NOW0 + 0.5  # the label's own process window
    damper._generations['batch_claim'] = 1
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.5)
    seed_window_doc(client, 'batch_pipeline_dev', 'batch_claim', WALL0 + 2.0)
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(2.0)
    assert clock.sleeps == [pytest.approx(2.0)]
    assert window.spill_reads == 0  # the spill is never read when the label windows cover


def test_prec_o0p5_f2_s2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._armed_until['batch_claim'] = NOW0 + 0.5  # the label's own process window
    damper._generations['batch_claim'] = 1
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 2.0)
    seed_window_doc(client, 'batch_pipeline_dev', 'batch_claim', WALL0 + 2.0)
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(2.0)
    assert clock.sleeps == [pytest.approx(2.0)]
    assert window.spill_reads == 0  # the spill is never read when the label windows cover


def test_prec_o0p5_f2_s4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._armed_until['batch_claim'] = NOW0 + 0.5  # the label's own process window
    damper._generations['batch_claim'] = 1
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    seed_window_doc(client, 'batch_pipeline_dev', 'batch_claim', WALL0 + 2.0)
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(2.0)
    assert clock.sleeps == [pytest.approx(2.0)]
    assert window.spill_reads == 0  # the spill is never read when the label windows cover


def test_prec_o0p5_f4_snone():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._armed_until['batch_claim'] = NOW0 + 0.5  # the label's own process window
    damper._generations['batch_claim'] = 1
    seed_window_doc(client, 'batch_pipeline_dev', 'batch_claim', WALL0 + 4.0)
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(4.0)
    assert clock.sleeps == [pytest.approx(4.0)]
    assert window.spill_absent_reads == 0  # no consult reached the spill lane at all


def test_prec_o0p5_f4_s0p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._armed_until['batch_claim'] = NOW0 + 0.5  # the label's own process window
    damper._generations['batch_claim'] = 1
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.5)
    seed_window_doc(client, 'batch_pipeline_dev', 'batch_claim', WALL0 + 4.0)
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(4.0)
    assert clock.sleeps == [pytest.approx(4.0)]
    assert window.spill_reads == 0  # the spill is never read when the label windows cover


def test_prec_o0p5_f4_s2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._armed_until['batch_claim'] = NOW0 + 0.5  # the label's own process window
    damper._generations['batch_claim'] = 1
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 2.0)
    seed_window_doc(client, 'batch_pipeline_dev', 'batch_claim', WALL0 + 4.0)
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(4.0)
    assert clock.sleeps == [pytest.approx(4.0)]
    assert window.spill_reads == 0  # the spill is never read when the label windows cover


def test_prec_o0p5_f4_s4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._armed_until['batch_claim'] = NOW0 + 0.5  # the label's own process window
    damper._generations['batch_claim'] = 1
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    seed_window_doc(client, 'batch_pipeline_dev', 'batch_claim', WALL0 + 4.0)
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(4.0)
    assert clock.sleeps == [pytest.approx(4.0)]
    assert window.spill_reads == 0  # the spill is never read when the label windows cover


def test_prec_o1_f0p125_snone():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._armed_until['batch_claim'] = NOW0 + 1.0  # the label's own process window
    damper._generations['batch_claim'] = 1
    seed_window_doc(client, 'batch_pipeline_dev', 'batch_claim', WALL0 + 0.125)
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(1.0)
    assert clock.sleeps == [pytest.approx(1.0)]
    assert window.spill_absent_reads == 0  # no consult reached the spill lane at all


def test_prec_o1_f0p125_s0p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._armed_until['batch_claim'] = NOW0 + 1.0  # the label's own process window
    damper._generations['batch_claim'] = 1
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.5)
    seed_window_doc(client, 'batch_pipeline_dev', 'batch_claim', WALL0 + 0.125)
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(1.0)
    assert clock.sleeps == [pytest.approx(1.0)]
    assert window.spill_reads == 0  # the spill is never read when the label windows cover


def test_prec_o1_f0p125_s2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._armed_until['batch_claim'] = NOW0 + 1.0  # the label's own process window
    damper._generations['batch_claim'] = 1
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 2.0)
    seed_window_doc(client, 'batch_pipeline_dev', 'batch_claim', WALL0 + 0.125)
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(1.0)
    assert clock.sleeps == [pytest.approx(1.0)]
    assert window.spill_reads == 0  # the spill is never read when the label windows cover


def test_prec_o1_f0p125_s4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._armed_until['batch_claim'] = NOW0 + 1.0  # the label's own process window
    damper._generations['batch_claim'] = 1
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    seed_window_doc(client, 'batch_pipeline_dev', 'batch_claim', WALL0 + 0.125)
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(1.0)
    assert clock.sleeps == [pytest.approx(1.0)]
    assert window.spill_reads == 0  # the spill is never read when the label windows cover


def test_prec_o1_f0p25_snone():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._armed_until['batch_claim'] = NOW0 + 1.0  # the label's own process window
    damper._generations['batch_claim'] = 1
    seed_window_doc(client, 'batch_pipeline_dev', 'batch_claim', WALL0 + 0.25)
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(1.0)
    assert clock.sleeps == [pytest.approx(1.0)]
    assert window.spill_absent_reads == 0  # no consult reached the spill lane at all


def test_prec_o1_f0p25_s0p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._armed_until['batch_claim'] = NOW0 + 1.0  # the label's own process window
    damper._generations['batch_claim'] = 1
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.5)
    seed_window_doc(client, 'batch_pipeline_dev', 'batch_claim', WALL0 + 0.25)
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(1.0)
    assert clock.sleeps == [pytest.approx(1.0)]
    assert window.spill_reads == 0  # the spill is never read when the label windows cover


def test_prec_o1_f0p25_s2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._armed_until['batch_claim'] = NOW0 + 1.0  # the label's own process window
    damper._generations['batch_claim'] = 1
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 2.0)
    seed_window_doc(client, 'batch_pipeline_dev', 'batch_claim', WALL0 + 0.25)
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(1.0)
    assert clock.sleeps == [pytest.approx(1.0)]
    assert window.spill_reads == 0  # the spill is never read when the label windows cover


def test_prec_o1_f0p25_s4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._armed_until['batch_claim'] = NOW0 + 1.0  # the label's own process window
    damper._generations['batch_claim'] = 1
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    seed_window_doc(client, 'batch_pipeline_dev', 'batch_claim', WALL0 + 0.25)
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(1.0)
    assert clock.sleeps == [pytest.approx(1.0)]
    assert window.spill_reads == 0  # the spill is never read when the label windows cover


def test_prec_o1_f0p5_snone():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._armed_until['batch_claim'] = NOW0 + 1.0  # the label's own process window
    damper._generations['batch_claim'] = 1
    seed_window_doc(client, 'batch_pipeline_dev', 'batch_claim', WALL0 + 0.5)
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(1.0)
    assert clock.sleeps == [pytest.approx(1.0)]
    assert window.spill_absent_reads == 0  # no consult reached the spill lane at all


def test_prec_o1_f0p5_s0p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._armed_until['batch_claim'] = NOW0 + 1.0  # the label's own process window
    damper._generations['batch_claim'] = 1
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.5)
    seed_window_doc(client, 'batch_pipeline_dev', 'batch_claim', WALL0 + 0.5)
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(1.0)
    assert clock.sleeps == [pytest.approx(1.0)]
    assert window.spill_reads == 0  # the spill is never read when the label windows cover


def test_prec_o1_f0p5_s2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._armed_until['batch_claim'] = NOW0 + 1.0  # the label's own process window
    damper._generations['batch_claim'] = 1
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 2.0)
    seed_window_doc(client, 'batch_pipeline_dev', 'batch_claim', WALL0 + 0.5)
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(1.0)
    assert clock.sleeps == [pytest.approx(1.0)]
    assert window.spill_reads == 0  # the spill is never read when the label windows cover


def test_prec_o1_f0p5_s4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._armed_until['batch_claim'] = NOW0 + 1.0  # the label's own process window
    damper._generations['batch_claim'] = 1
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    seed_window_doc(client, 'batch_pipeline_dev', 'batch_claim', WALL0 + 0.5)
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(1.0)
    assert clock.sleeps == [pytest.approx(1.0)]
    assert window.spill_reads == 0  # the spill is never read when the label windows cover


def test_prec_o1_f1_snone():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._armed_until['batch_claim'] = NOW0 + 1.0  # the label's own process window
    damper._generations['batch_claim'] = 1
    seed_window_doc(client, 'batch_pipeline_dev', 'batch_claim', WALL0 + 1.0)
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(1.0)
    assert clock.sleeps == [pytest.approx(1.0)]
    assert window.spill_absent_reads == 0  # no consult reached the spill lane at all


def test_prec_o1_f1_s0p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._armed_until['batch_claim'] = NOW0 + 1.0  # the label's own process window
    damper._generations['batch_claim'] = 1
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.5)
    seed_window_doc(client, 'batch_pipeline_dev', 'batch_claim', WALL0 + 1.0)
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(1.0)
    assert clock.sleeps == [pytest.approx(1.0)]
    assert window.spill_reads == 0  # the spill is never read when the label windows cover


def test_prec_o1_f1_s2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._armed_until['batch_claim'] = NOW0 + 1.0  # the label's own process window
    damper._generations['batch_claim'] = 1
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 2.0)
    seed_window_doc(client, 'batch_pipeline_dev', 'batch_claim', WALL0 + 1.0)
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(1.0)
    assert clock.sleeps == [pytest.approx(1.0)]
    assert window.spill_reads == 0  # the spill is never read when the label windows cover


def test_prec_o1_f1_s4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._armed_until['batch_claim'] = NOW0 + 1.0  # the label's own process window
    damper._generations['batch_claim'] = 1
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    seed_window_doc(client, 'batch_pipeline_dev', 'batch_claim', WALL0 + 1.0)
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(1.0)
    assert clock.sleeps == [pytest.approx(1.0)]
    assert window.spill_reads == 0  # the spill is never read when the label windows cover


def test_prec_o1_f2_snone():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._armed_until['batch_claim'] = NOW0 + 1.0  # the label's own process window
    damper._generations['batch_claim'] = 1
    seed_window_doc(client, 'batch_pipeline_dev', 'batch_claim', WALL0 + 2.0)
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(2.0)
    assert clock.sleeps == [pytest.approx(2.0)]
    assert window.spill_absent_reads == 0  # no consult reached the spill lane at all


def test_prec_o1_f2_s0p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._armed_until['batch_claim'] = NOW0 + 1.0  # the label's own process window
    damper._generations['batch_claim'] = 1
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.5)
    seed_window_doc(client, 'batch_pipeline_dev', 'batch_claim', WALL0 + 2.0)
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(2.0)
    assert clock.sleeps == [pytest.approx(2.0)]
    assert window.spill_reads == 0  # the spill is never read when the label windows cover


def test_prec_o1_f2_s2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._armed_until['batch_claim'] = NOW0 + 1.0  # the label's own process window
    damper._generations['batch_claim'] = 1
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 2.0)
    seed_window_doc(client, 'batch_pipeline_dev', 'batch_claim', WALL0 + 2.0)
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(2.0)
    assert clock.sleeps == [pytest.approx(2.0)]
    assert window.spill_reads == 0  # the spill is never read when the label windows cover


def test_prec_o1_f2_s4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._armed_until['batch_claim'] = NOW0 + 1.0  # the label's own process window
    damper._generations['batch_claim'] = 1
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    seed_window_doc(client, 'batch_pipeline_dev', 'batch_claim', WALL0 + 2.0)
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(2.0)
    assert clock.sleeps == [pytest.approx(2.0)]
    assert window.spill_reads == 0  # the spill is never read when the label windows cover


def test_prec_o1_f4_snone():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._armed_until['batch_claim'] = NOW0 + 1.0  # the label's own process window
    damper._generations['batch_claim'] = 1
    seed_window_doc(client, 'batch_pipeline_dev', 'batch_claim', WALL0 + 4.0)
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(4.0)
    assert clock.sleeps == [pytest.approx(4.0)]
    assert window.spill_absent_reads == 0  # no consult reached the spill lane at all


def test_prec_o1_f4_s0p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._armed_until['batch_claim'] = NOW0 + 1.0  # the label's own process window
    damper._generations['batch_claim'] = 1
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.5)
    seed_window_doc(client, 'batch_pipeline_dev', 'batch_claim', WALL0 + 4.0)
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(4.0)
    assert clock.sleeps == [pytest.approx(4.0)]
    assert window.spill_reads == 0  # the spill is never read when the label windows cover


def test_prec_o1_f4_s2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._armed_until['batch_claim'] = NOW0 + 1.0  # the label's own process window
    damper._generations['batch_claim'] = 1
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 2.0)
    seed_window_doc(client, 'batch_pipeline_dev', 'batch_claim', WALL0 + 4.0)
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(4.0)
    assert clock.sleeps == [pytest.approx(4.0)]
    assert window.spill_reads == 0  # the spill is never read when the label windows cover


def test_prec_o1_f4_s4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._armed_until['batch_claim'] = NOW0 + 1.0  # the label's own process window
    damper._generations['batch_claim'] = 1
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    seed_window_doc(client, 'batch_pipeline_dev', 'batch_claim', WALL0 + 4.0)
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(4.0)
    assert clock.sleeps == [pytest.approx(4.0)]
    assert window.spill_reads == 0  # the spill is never read when the label windows cover


def test_prec_o2_f0p125_snone():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._armed_until['batch_claim'] = NOW0 + 2.0  # the label's own process window
    damper._generations['batch_claim'] = 1
    seed_window_doc(client, 'batch_pipeline_dev', 'batch_claim', WALL0 + 0.125)
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(2.0)
    assert clock.sleeps == [pytest.approx(2.0)]
    assert window.spill_absent_reads == 0  # no consult reached the spill lane at all


def test_prec_o2_f0p125_s0p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._armed_until['batch_claim'] = NOW0 + 2.0  # the label's own process window
    damper._generations['batch_claim'] = 1
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.5)
    seed_window_doc(client, 'batch_pipeline_dev', 'batch_claim', WALL0 + 0.125)
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(2.0)
    assert clock.sleeps == [pytest.approx(2.0)]
    assert window.spill_reads == 0  # the spill is never read when the label windows cover


def test_prec_o2_f0p125_s2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._armed_until['batch_claim'] = NOW0 + 2.0  # the label's own process window
    damper._generations['batch_claim'] = 1
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 2.0)
    seed_window_doc(client, 'batch_pipeline_dev', 'batch_claim', WALL0 + 0.125)
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(2.0)
    assert clock.sleeps == [pytest.approx(2.0)]
    assert window.spill_reads == 0  # the spill is never read when the label windows cover


def test_prec_o2_f0p125_s4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._armed_until['batch_claim'] = NOW0 + 2.0  # the label's own process window
    damper._generations['batch_claim'] = 1
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    seed_window_doc(client, 'batch_pipeline_dev', 'batch_claim', WALL0 + 0.125)
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(2.0)
    assert clock.sleeps == [pytest.approx(2.0)]
    assert window.spill_reads == 0  # the spill is never read when the label windows cover


def test_prec_o2_f0p25_snone():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._armed_until['batch_claim'] = NOW0 + 2.0  # the label's own process window
    damper._generations['batch_claim'] = 1
    seed_window_doc(client, 'batch_pipeline_dev', 'batch_claim', WALL0 + 0.25)
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(2.0)
    assert clock.sleeps == [pytest.approx(2.0)]
    assert window.spill_absent_reads == 0  # no consult reached the spill lane at all


def test_prec_o2_f0p25_s0p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._armed_until['batch_claim'] = NOW0 + 2.0  # the label's own process window
    damper._generations['batch_claim'] = 1
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.5)
    seed_window_doc(client, 'batch_pipeline_dev', 'batch_claim', WALL0 + 0.25)
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(2.0)
    assert clock.sleeps == [pytest.approx(2.0)]
    assert window.spill_reads == 0  # the spill is never read when the label windows cover


def test_prec_o2_f0p25_s2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._armed_until['batch_claim'] = NOW0 + 2.0  # the label's own process window
    damper._generations['batch_claim'] = 1
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 2.0)
    seed_window_doc(client, 'batch_pipeline_dev', 'batch_claim', WALL0 + 0.25)
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(2.0)
    assert clock.sleeps == [pytest.approx(2.0)]
    assert window.spill_reads == 0  # the spill is never read when the label windows cover


def test_prec_o2_f0p25_s4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._armed_until['batch_claim'] = NOW0 + 2.0  # the label's own process window
    damper._generations['batch_claim'] = 1
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    seed_window_doc(client, 'batch_pipeline_dev', 'batch_claim', WALL0 + 0.25)
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(2.0)
    assert clock.sleeps == [pytest.approx(2.0)]
    assert window.spill_reads == 0  # the spill is never read when the label windows cover


def test_prec_o2_f0p5_snone():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._armed_until['batch_claim'] = NOW0 + 2.0  # the label's own process window
    damper._generations['batch_claim'] = 1
    seed_window_doc(client, 'batch_pipeline_dev', 'batch_claim', WALL0 + 0.5)
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(2.0)
    assert clock.sleeps == [pytest.approx(2.0)]
    assert window.spill_absent_reads == 0  # no consult reached the spill lane at all


def test_prec_o2_f0p5_s0p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._armed_until['batch_claim'] = NOW0 + 2.0  # the label's own process window
    damper._generations['batch_claim'] = 1
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.5)
    seed_window_doc(client, 'batch_pipeline_dev', 'batch_claim', WALL0 + 0.5)
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(2.0)
    assert clock.sleeps == [pytest.approx(2.0)]
    assert window.spill_reads == 0  # the spill is never read when the label windows cover


def test_prec_o2_f0p5_s2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._armed_until['batch_claim'] = NOW0 + 2.0  # the label's own process window
    damper._generations['batch_claim'] = 1
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 2.0)
    seed_window_doc(client, 'batch_pipeline_dev', 'batch_claim', WALL0 + 0.5)
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(2.0)
    assert clock.sleeps == [pytest.approx(2.0)]
    assert window.spill_reads == 0  # the spill is never read when the label windows cover


def test_prec_o2_f0p5_s4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._armed_until['batch_claim'] = NOW0 + 2.0  # the label's own process window
    damper._generations['batch_claim'] = 1
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    seed_window_doc(client, 'batch_pipeline_dev', 'batch_claim', WALL0 + 0.5)
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(2.0)
    assert clock.sleeps == [pytest.approx(2.0)]
    assert window.spill_reads == 0  # the spill is never read when the label windows cover


def test_prec_o2_f1_snone():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._armed_until['batch_claim'] = NOW0 + 2.0  # the label's own process window
    damper._generations['batch_claim'] = 1
    seed_window_doc(client, 'batch_pipeline_dev', 'batch_claim', WALL0 + 1.0)
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(2.0)
    assert clock.sleeps == [pytest.approx(2.0)]
    assert window.spill_absent_reads == 0  # no consult reached the spill lane at all


def test_prec_o2_f1_s0p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._armed_until['batch_claim'] = NOW0 + 2.0  # the label's own process window
    damper._generations['batch_claim'] = 1
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.5)
    seed_window_doc(client, 'batch_pipeline_dev', 'batch_claim', WALL0 + 1.0)
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(2.0)
    assert clock.sleeps == [pytest.approx(2.0)]
    assert window.spill_reads == 0  # the spill is never read when the label windows cover


def test_prec_o2_f1_s2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._armed_until['batch_claim'] = NOW0 + 2.0  # the label's own process window
    damper._generations['batch_claim'] = 1
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 2.0)
    seed_window_doc(client, 'batch_pipeline_dev', 'batch_claim', WALL0 + 1.0)
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(2.0)
    assert clock.sleeps == [pytest.approx(2.0)]
    assert window.spill_reads == 0  # the spill is never read when the label windows cover


def test_prec_o2_f1_s4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._armed_until['batch_claim'] = NOW0 + 2.0  # the label's own process window
    damper._generations['batch_claim'] = 1
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    seed_window_doc(client, 'batch_pipeline_dev', 'batch_claim', WALL0 + 1.0)
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(2.0)
    assert clock.sleeps == [pytest.approx(2.0)]
    assert window.spill_reads == 0  # the spill is never read when the label windows cover


def test_prec_o2_f2_snone():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._armed_until['batch_claim'] = NOW0 + 2.0  # the label's own process window
    damper._generations['batch_claim'] = 1
    seed_window_doc(client, 'batch_pipeline_dev', 'batch_claim', WALL0 + 2.0)
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(2.0)
    assert clock.sleeps == [pytest.approx(2.0)]
    assert window.spill_absent_reads == 0  # no consult reached the spill lane at all


def test_prec_o2_f2_s0p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._armed_until['batch_claim'] = NOW0 + 2.0  # the label's own process window
    damper._generations['batch_claim'] = 1
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.5)
    seed_window_doc(client, 'batch_pipeline_dev', 'batch_claim', WALL0 + 2.0)
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(2.0)
    assert clock.sleeps == [pytest.approx(2.0)]
    assert window.spill_reads == 0  # the spill is never read when the label windows cover


def test_prec_o2_f2_s2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._armed_until['batch_claim'] = NOW0 + 2.0  # the label's own process window
    damper._generations['batch_claim'] = 1
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 2.0)
    seed_window_doc(client, 'batch_pipeline_dev', 'batch_claim', WALL0 + 2.0)
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(2.0)
    assert clock.sleeps == [pytest.approx(2.0)]
    assert window.spill_reads == 0  # the spill is never read when the label windows cover


def test_prec_o2_f2_s4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._armed_until['batch_claim'] = NOW0 + 2.0  # the label's own process window
    damper._generations['batch_claim'] = 1
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    seed_window_doc(client, 'batch_pipeline_dev', 'batch_claim', WALL0 + 2.0)
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(2.0)
    assert clock.sleeps == [pytest.approx(2.0)]
    assert window.spill_reads == 0  # the spill is never read when the label windows cover


def test_prec_o2_f4_snone():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._armed_until['batch_claim'] = NOW0 + 2.0  # the label's own process window
    damper._generations['batch_claim'] = 1
    seed_window_doc(client, 'batch_pipeline_dev', 'batch_claim', WALL0 + 4.0)
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(4.0)
    assert clock.sleeps == [pytest.approx(4.0)]
    assert window.spill_absent_reads == 0  # no consult reached the spill lane at all


def test_prec_o2_f4_s0p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._armed_until['batch_claim'] = NOW0 + 2.0  # the label's own process window
    damper._generations['batch_claim'] = 1
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.5)
    seed_window_doc(client, 'batch_pipeline_dev', 'batch_claim', WALL0 + 4.0)
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(4.0)
    assert clock.sleeps == [pytest.approx(4.0)]
    assert window.spill_reads == 0  # the spill is never read when the label windows cover


def test_prec_o2_f4_s2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._armed_until['batch_claim'] = NOW0 + 2.0  # the label's own process window
    damper._generations['batch_claim'] = 1
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 2.0)
    seed_window_doc(client, 'batch_pipeline_dev', 'batch_claim', WALL0 + 4.0)
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(4.0)
    assert clock.sleeps == [pytest.approx(4.0)]
    assert window.spill_reads == 0  # the spill is never read when the label windows cover


def test_prec_o2_f4_s4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._armed_until['batch_claim'] = NOW0 + 2.0  # the label's own process window
    damper._generations['batch_claim'] = 1
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    seed_window_doc(client, 'batch_pipeline_dev', 'batch_claim', WALL0 + 4.0)
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(4.0)
    assert clock.sleeps == [pytest.approx(4.0)]
    assert window.spill_reads == 0  # the spill is never read when the label windows cover


def test_prec_o4_f0p125_snone():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._armed_until['batch_claim'] = NOW0 + 4.0  # the label's own process window
    damper._generations['batch_claim'] = 1
    seed_window_doc(client, 'batch_pipeline_dev', 'batch_claim', WALL0 + 0.125)
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(4.0)
    assert clock.sleeps == [pytest.approx(4.0)]
    assert window.spill_absent_reads == 0  # no consult reached the spill lane at all


def test_prec_o4_f0p125_s0p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._armed_until['batch_claim'] = NOW0 + 4.0  # the label's own process window
    damper._generations['batch_claim'] = 1
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.5)
    seed_window_doc(client, 'batch_pipeline_dev', 'batch_claim', WALL0 + 0.125)
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(4.0)
    assert clock.sleeps == [pytest.approx(4.0)]
    assert window.spill_reads == 0  # the spill is never read when the label windows cover


def test_prec_o4_f0p125_s2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._armed_until['batch_claim'] = NOW0 + 4.0  # the label's own process window
    damper._generations['batch_claim'] = 1
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 2.0)
    seed_window_doc(client, 'batch_pipeline_dev', 'batch_claim', WALL0 + 0.125)
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(4.0)
    assert clock.sleeps == [pytest.approx(4.0)]
    assert window.spill_reads == 0  # the spill is never read when the label windows cover


def test_prec_o4_f0p125_s4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._armed_until['batch_claim'] = NOW0 + 4.0  # the label's own process window
    damper._generations['batch_claim'] = 1
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    seed_window_doc(client, 'batch_pipeline_dev', 'batch_claim', WALL0 + 0.125)
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(4.0)
    assert clock.sleeps == [pytest.approx(4.0)]
    assert window.spill_reads == 0  # the spill is never read when the label windows cover


def test_prec_o4_f0p25_snone():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._armed_until['batch_claim'] = NOW0 + 4.0  # the label's own process window
    damper._generations['batch_claim'] = 1
    seed_window_doc(client, 'batch_pipeline_dev', 'batch_claim', WALL0 + 0.25)
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(4.0)
    assert clock.sleeps == [pytest.approx(4.0)]
    assert window.spill_absent_reads == 0  # no consult reached the spill lane at all


def test_prec_o4_f0p25_s0p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._armed_until['batch_claim'] = NOW0 + 4.0  # the label's own process window
    damper._generations['batch_claim'] = 1
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.5)
    seed_window_doc(client, 'batch_pipeline_dev', 'batch_claim', WALL0 + 0.25)
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(4.0)
    assert clock.sleeps == [pytest.approx(4.0)]
    assert window.spill_reads == 0  # the spill is never read when the label windows cover


def test_prec_o4_f0p25_s2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._armed_until['batch_claim'] = NOW0 + 4.0  # the label's own process window
    damper._generations['batch_claim'] = 1
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 2.0)
    seed_window_doc(client, 'batch_pipeline_dev', 'batch_claim', WALL0 + 0.25)
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(4.0)
    assert clock.sleeps == [pytest.approx(4.0)]
    assert window.spill_reads == 0  # the spill is never read when the label windows cover


def test_prec_o4_f0p25_s4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._armed_until['batch_claim'] = NOW0 + 4.0  # the label's own process window
    damper._generations['batch_claim'] = 1
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    seed_window_doc(client, 'batch_pipeline_dev', 'batch_claim', WALL0 + 0.25)
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(4.0)
    assert clock.sleeps == [pytest.approx(4.0)]
    assert window.spill_reads == 0  # the spill is never read when the label windows cover


def test_prec_o4_f0p5_snone():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._armed_until['batch_claim'] = NOW0 + 4.0  # the label's own process window
    damper._generations['batch_claim'] = 1
    seed_window_doc(client, 'batch_pipeline_dev', 'batch_claim', WALL0 + 0.5)
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(4.0)
    assert clock.sleeps == [pytest.approx(4.0)]
    assert window.spill_absent_reads == 0  # no consult reached the spill lane at all


def test_prec_o4_f0p5_s0p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._armed_until['batch_claim'] = NOW0 + 4.0  # the label's own process window
    damper._generations['batch_claim'] = 1
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.5)
    seed_window_doc(client, 'batch_pipeline_dev', 'batch_claim', WALL0 + 0.5)
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(4.0)
    assert clock.sleeps == [pytest.approx(4.0)]
    assert window.spill_reads == 0  # the spill is never read when the label windows cover


def test_prec_o4_f0p5_s2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._armed_until['batch_claim'] = NOW0 + 4.0  # the label's own process window
    damper._generations['batch_claim'] = 1
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 2.0)
    seed_window_doc(client, 'batch_pipeline_dev', 'batch_claim', WALL0 + 0.5)
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(4.0)
    assert clock.sleeps == [pytest.approx(4.0)]
    assert window.spill_reads == 0  # the spill is never read when the label windows cover


def test_prec_o4_f0p5_s4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._armed_until['batch_claim'] = NOW0 + 4.0  # the label's own process window
    damper._generations['batch_claim'] = 1
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    seed_window_doc(client, 'batch_pipeline_dev', 'batch_claim', WALL0 + 0.5)
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(4.0)
    assert clock.sleeps == [pytest.approx(4.0)]
    assert window.spill_reads == 0  # the spill is never read when the label windows cover


def test_prec_o4_f1_snone():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._armed_until['batch_claim'] = NOW0 + 4.0  # the label's own process window
    damper._generations['batch_claim'] = 1
    seed_window_doc(client, 'batch_pipeline_dev', 'batch_claim', WALL0 + 1.0)
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(4.0)
    assert clock.sleeps == [pytest.approx(4.0)]
    assert window.spill_absent_reads == 0  # no consult reached the spill lane at all


def test_prec_o4_f1_s0p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._armed_until['batch_claim'] = NOW0 + 4.0  # the label's own process window
    damper._generations['batch_claim'] = 1
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.5)
    seed_window_doc(client, 'batch_pipeline_dev', 'batch_claim', WALL0 + 1.0)
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(4.0)
    assert clock.sleeps == [pytest.approx(4.0)]
    assert window.spill_reads == 0  # the spill is never read when the label windows cover


def test_prec_o4_f1_s2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._armed_until['batch_claim'] = NOW0 + 4.0  # the label's own process window
    damper._generations['batch_claim'] = 1
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 2.0)
    seed_window_doc(client, 'batch_pipeline_dev', 'batch_claim', WALL0 + 1.0)
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(4.0)
    assert clock.sleeps == [pytest.approx(4.0)]
    assert window.spill_reads == 0  # the spill is never read when the label windows cover


def test_prec_o4_f1_s4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._armed_until['batch_claim'] = NOW0 + 4.0  # the label's own process window
    damper._generations['batch_claim'] = 1
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    seed_window_doc(client, 'batch_pipeline_dev', 'batch_claim', WALL0 + 1.0)
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(4.0)
    assert clock.sleeps == [pytest.approx(4.0)]
    assert window.spill_reads == 0  # the spill is never read when the label windows cover


def test_prec_o4_f2_snone():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._armed_until['batch_claim'] = NOW0 + 4.0  # the label's own process window
    damper._generations['batch_claim'] = 1
    seed_window_doc(client, 'batch_pipeline_dev', 'batch_claim', WALL0 + 2.0)
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(4.0)
    assert clock.sleeps == [pytest.approx(4.0)]
    assert window.spill_absent_reads == 0  # no consult reached the spill lane at all


def test_prec_o4_f2_s0p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._armed_until['batch_claim'] = NOW0 + 4.0  # the label's own process window
    damper._generations['batch_claim'] = 1
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.5)
    seed_window_doc(client, 'batch_pipeline_dev', 'batch_claim', WALL0 + 2.0)
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(4.0)
    assert clock.sleeps == [pytest.approx(4.0)]
    assert window.spill_reads == 0  # the spill is never read when the label windows cover


def test_prec_o4_f2_s2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._armed_until['batch_claim'] = NOW0 + 4.0  # the label's own process window
    damper._generations['batch_claim'] = 1
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 2.0)
    seed_window_doc(client, 'batch_pipeline_dev', 'batch_claim', WALL0 + 2.0)
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(4.0)
    assert clock.sleeps == [pytest.approx(4.0)]
    assert window.spill_reads == 0  # the spill is never read when the label windows cover


def test_prec_o4_f2_s4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._armed_until['batch_claim'] = NOW0 + 4.0  # the label's own process window
    damper._generations['batch_claim'] = 1
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    seed_window_doc(client, 'batch_pipeline_dev', 'batch_claim', WALL0 + 2.0)
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(4.0)
    assert clock.sleeps == [pytest.approx(4.0)]
    assert window.spill_reads == 0  # the spill is never read when the label windows cover


def test_prec_o4_f4_snone():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._armed_until['batch_claim'] = NOW0 + 4.0  # the label's own process window
    damper._generations['batch_claim'] = 1
    seed_window_doc(client, 'batch_pipeline_dev', 'batch_claim', WALL0 + 4.0)
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(4.0)
    assert clock.sleeps == [pytest.approx(4.0)]
    assert window.spill_absent_reads == 0  # no consult reached the spill lane at all


def test_prec_o4_f4_s0p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._armed_until['batch_claim'] = NOW0 + 4.0  # the label's own process window
    damper._generations['batch_claim'] = 1
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.5)
    seed_window_doc(client, 'batch_pipeline_dev', 'batch_claim', WALL0 + 4.0)
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(4.0)
    assert clock.sleeps == [pytest.approx(4.0)]
    assert window.spill_reads == 0  # the spill is never read when the label windows cover


def test_prec_o4_f4_s2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._armed_until['batch_claim'] = NOW0 + 4.0  # the label's own process window
    damper._generations['batch_claim'] = 1
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 2.0)
    seed_window_doc(client, 'batch_pipeline_dev', 'batch_claim', WALL0 + 4.0)
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(4.0)
    assert clock.sleeps == [pytest.approx(4.0)]
    assert window.spill_reads == 0  # the spill is never read when the label windows cover


def test_prec_o4_f4_s4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._armed_until['batch_claim'] = NOW0 + 4.0  # the label's own process window
    damper._generations['batch_claim'] = 1
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    seed_window_doc(client, 'batch_pipeline_dev', 'batch_claim', WALL0 + 4.0)
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(4.0)
    assert clock.sleeps == [pytest.approx(4.0)]
    assert window.spill_reads == 0  # the spill is never read when the label windows cover


def test_floor_d0p05_w0p125():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.05)
    window.publish_spill('batch_admit', 0.125, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000000.125)
    assert stored['window_seconds'] == pytest.approx(0.125)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p05_w0p15625():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.05)
    window.publish_spill('batch_admit', 0.15625, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000000.15625)
    assert stored['window_seconds'] == pytest.approx(0.15625)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p05_w0p1875():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.05)
    window.publish_spill('batch_admit', 0.1875, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000000.1875)
    assert stored['window_seconds'] == pytest.approx(0.1875)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p05_w0p21875():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.05)
    window.publish_spill('batch_admit', 0.21875, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000000.21875)
    assert stored['window_seconds'] == pytest.approx(0.21875)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p05_w0p25():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.05)
    window.publish_spill('batch_admit', 0.25, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000000.25)
    assert stored['window_seconds'] == pytest.approx(0.25)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p05_w0p3125():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.05)
    window.publish_spill('batch_admit', 0.3125, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000000.3125)
    assert stored['window_seconds'] == pytest.approx(0.3125)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p05_w0p375():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.05)
    window.publish_spill('batch_admit', 0.375, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000000.375)
    assert stored['window_seconds'] == pytest.approx(0.375)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p05_w0p4375():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.05)
    window.publish_spill('batch_admit', 0.4375, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000000.4375)
    assert stored['window_seconds'] == pytest.approx(0.4375)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p05_w0p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.05)
    window.publish_spill('batch_admit', 0.5, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000000.5)
    assert stored['window_seconds'] == pytest.approx(0.5)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p05_w0p625():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.05)
    window.publish_spill('batch_admit', 0.625, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000000.625)
    assert stored['window_seconds'] == pytest.approx(0.625)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p05_w0p75():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.05)
    window.publish_spill('batch_admit', 0.75, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000000.75)
    assert stored['window_seconds'] == pytest.approx(0.75)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p05_w0p875():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.05)
    window.publish_spill('batch_admit', 0.875, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000000.875)
    assert stored['window_seconds'] == pytest.approx(0.875)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p05_w1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.05)
    window.publish_spill('batch_admit', 1.0, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000001.0)
    assert stored['window_seconds'] == pytest.approx(1.0)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p05_w1p25():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.05)
    window.publish_spill('batch_admit', 1.25, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000001.25)
    assert stored['window_seconds'] == pytest.approx(1.25)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p05_w1p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.05)
    window.publish_spill('batch_admit', 1.5, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000001.5)
    assert stored['window_seconds'] == pytest.approx(1.5)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p05_w1p75():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.05)
    window.publish_spill('batch_admit', 1.75, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000001.75)
    assert stored['window_seconds'] == pytest.approx(1.75)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p05_w2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.05)
    window.publish_spill('batch_admit', 2.0, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000002.0)
    assert stored['window_seconds'] == pytest.approx(2.0)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p05_w2p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.05)
    window.publish_spill('batch_admit', 2.5, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000002.5)
    assert stored['window_seconds'] == pytest.approx(2.5)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p05_w3():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.05)
    window.publish_spill('batch_admit', 3.0, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000003.0)
    assert stored['window_seconds'] == pytest.approx(3.0)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p05_w3p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.05)
    window.publish_spill('batch_admit', 3.5, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000003.5)
    assert stored['window_seconds'] == pytest.approx(3.5)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p05_w4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.05)
    window.publish_spill('batch_admit', 4.0, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000004.0)
    assert stored['window_seconds'] == pytest.approx(4.0)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p0625_w0p125():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.0625)
    window.publish_spill('batch_admit', 0.125, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000000.125)
    assert stored['window_seconds'] == pytest.approx(0.125)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p0625_w0p15625():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.0625)
    window.publish_spill('batch_admit', 0.15625, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000000.15625)
    assert stored['window_seconds'] == pytest.approx(0.15625)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p0625_w0p1875():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.0625)
    window.publish_spill('batch_admit', 0.1875, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000000.1875)
    assert stored['window_seconds'] == pytest.approx(0.1875)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p0625_w0p21875():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.0625)
    window.publish_spill('batch_admit', 0.21875, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000000.21875)
    assert stored['window_seconds'] == pytest.approx(0.21875)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p0625_w0p25():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.0625)
    window.publish_spill('batch_admit', 0.25, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000000.25)
    assert stored['window_seconds'] == pytest.approx(0.25)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p0625_w0p3125():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.0625)
    window.publish_spill('batch_admit', 0.3125, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000000.3125)
    assert stored['window_seconds'] == pytest.approx(0.3125)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p0625_w0p375():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.0625)
    window.publish_spill('batch_admit', 0.375, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000000.375)
    assert stored['window_seconds'] == pytest.approx(0.375)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p0625_w0p4375():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.0625)
    window.publish_spill('batch_admit', 0.4375, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000000.4375)
    assert stored['window_seconds'] == pytest.approx(0.4375)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p0625_w0p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.0625)
    window.publish_spill('batch_admit', 0.5, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000000.5)
    assert stored['window_seconds'] == pytest.approx(0.5)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p0625_w0p625():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.0625)
    window.publish_spill('batch_admit', 0.625, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000000.625)
    assert stored['window_seconds'] == pytest.approx(0.625)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p0625_w0p75():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.0625)
    window.publish_spill('batch_admit', 0.75, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000000.75)
    assert stored['window_seconds'] == pytest.approx(0.75)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p0625_w0p875():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.0625)
    window.publish_spill('batch_admit', 0.875, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000000.875)
    assert stored['window_seconds'] == pytest.approx(0.875)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p0625_w1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.0625)
    window.publish_spill('batch_admit', 1.0, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000001.0)
    assert stored['window_seconds'] == pytest.approx(1.0)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p0625_w1p25():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.0625)
    window.publish_spill('batch_admit', 1.25, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000001.25)
    assert stored['window_seconds'] == pytest.approx(1.25)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p0625_w1p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.0625)
    window.publish_spill('batch_admit', 1.5, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000001.5)
    assert stored['window_seconds'] == pytest.approx(1.5)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p0625_w1p75():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.0625)
    window.publish_spill('batch_admit', 1.75, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000001.75)
    assert stored['window_seconds'] == pytest.approx(1.75)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p0625_w2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.0625)
    window.publish_spill('batch_admit', 2.0, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000002.0)
    assert stored['window_seconds'] == pytest.approx(2.0)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p0625_w2p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.0625)
    window.publish_spill('batch_admit', 2.5, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000002.5)
    assert stored['window_seconds'] == pytest.approx(2.5)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p0625_w3():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.0625)
    window.publish_spill('batch_admit', 3.0, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000003.0)
    assert stored['window_seconds'] == pytest.approx(3.0)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p0625_w3p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.0625)
    window.publish_spill('batch_admit', 3.5, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000003.5)
    assert stored['window_seconds'] == pytest.approx(3.5)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p0625_w4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.0625)
    window.publish_spill('batch_admit', 4.0, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000004.0)
    assert stored['window_seconds'] == pytest.approx(4.0)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p125_w0p125():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.125)
    window.publish_spill('batch_admit', 0.125, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000000.125)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d0p125_w0p15625():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.125)
    window.publish_spill('batch_admit', 0.15625, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000000.15625)
    assert stored['window_seconds'] == pytest.approx(0.15625)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p125_w0p1875():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.125)
    window.publish_spill('batch_admit', 0.1875, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000000.1875)
    assert stored['window_seconds'] == pytest.approx(0.1875)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p125_w0p21875():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.125)
    window.publish_spill('batch_admit', 0.21875, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000000.21875)
    assert stored['window_seconds'] == pytest.approx(0.21875)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p125_w0p25():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.125)
    window.publish_spill('batch_admit', 0.25, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000000.25)
    assert stored['window_seconds'] == pytest.approx(0.25)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p125_w0p3125():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.125)
    window.publish_spill('batch_admit', 0.3125, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000000.3125)
    assert stored['window_seconds'] == pytest.approx(0.3125)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p125_w0p375():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.125)
    window.publish_spill('batch_admit', 0.375, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000000.375)
    assert stored['window_seconds'] == pytest.approx(0.375)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p125_w0p4375():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.125)
    window.publish_spill('batch_admit', 0.4375, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000000.4375)
    assert stored['window_seconds'] == pytest.approx(0.4375)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p125_w0p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.125)
    window.publish_spill('batch_admit', 0.5, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000000.5)
    assert stored['window_seconds'] == pytest.approx(0.5)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p125_w0p625():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.125)
    window.publish_spill('batch_admit', 0.625, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000000.625)
    assert stored['window_seconds'] == pytest.approx(0.625)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p125_w0p75():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.125)
    window.publish_spill('batch_admit', 0.75, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000000.75)
    assert stored['window_seconds'] == pytest.approx(0.75)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p125_w0p875():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.125)
    window.publish_spill('batch_admit', 0.875, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000000.875)
    assert stored['window_seconds'] == pytest.approx(0.875)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p125_w1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.125)
    window.publish_spill('batch_admit', 1.0, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000001.0)
    assert stored['window_seconds'] == pytest.approx(1.0)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p125_w1p25():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.125)
    window.publish_spill('batch_admit', 1.25, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000001.25)
    assert stored['window_seconds'] == pytest.approx(1.25)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p125_w1p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.125)
    window.publish_spill('batch_admit', 1.5, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000001.5)
    assert stored['window_seconds'] == pytest.approx(1.5)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p125_w1p75():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.125)
    window.publish_spill('batch_admit', 1.75, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000001.75)
    assert stored['window_seconds'] == pytest.approx(1.75)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p125_w2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.125)
    window.publish_spill('batch_admit', 2.0, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000002.0)
    assert stored['window_seconds'] == pytest.approx(2.0)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p125_w2p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.125)
    window.publish_spill('batch_admit', 2.5, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000002.5)
    assert stored['window_seconds'] == pytest.approx(2.5)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p125_w3():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.125)
    window.publish_spill('batch_admit', 3.0, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000003.0)
    assert stored['window_seconds'] == pytest.approx(3.0)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p125_w3p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.125)
    window.publish_spill('batch_admit', 3.5, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000003.5)
    assert stored['window_seconds'] == pytest.approx(3.5)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p125_w4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.125)
    window.publish_spill('batch_admit', 4.0, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000004.0)
    assert stored['window_seconds'] == pytest.approx(4.0)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p1875_w0p125():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.1875)
    window.publish_spill('batch_admit', 0.125, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000000.1875)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d0p1875_w0p15625():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.1875)
    window.publish_spill('batch_admit', 0.15625, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000000.1875)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d0p1875_w0p1875():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.1875)
    window.publish_spill('batch_admit', 0.1875, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000000.1875)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d0p1875_w0p21875():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.1875)
    window.publish_spill('batch_admit', 0.21875, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000000.21875)
    assert stored['window_seconds'] == pytest.approx(0.21875)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p1875_w0p25():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.1875)
    window.publish_spill('batch_admit', 0.25, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000000.25)
    assert stored['window_seconds'] == pytest.approx(0.25)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p1875_w0p3125():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.1875)
    window.publish_spill('batch_admit', 0.3125, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000000.3125)
    assert stored['window_seconds'] == pytest.approx(0.3125)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p1875_w0p375():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.1875)
    window.publish_spill('batch_admit', 0.375, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000000.375)
    assert stored['window_seconds'] == pytest.approx(0.375)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p1875_w0p4375():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.1875)
    window.publish_spill('batch_admit', 0.4375, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000000.4375)
    assert stored['window_seconds'] == pytest.approx(0.4375)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p1875_w0p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.1875)
    window.publish_spill('batch_admit', 0.5, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000000.5)
    assert stored['window_seconds'] == pytest.approx(0.5)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p1875_w0p625():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.1875)
    window.publish_spill('batch_admit', 0.625, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000000.625)
    assert stored['window_seconds'] == pytest.approx(0.625)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p1875_w0p75():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.1875)
    window.publish_spill('batch_admit', 0.75, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000000.75)
    assert stored['window_seconds'] == pytest.approx(0.75)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p1875_w0p875():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.1875)
    window.publish_spill('batch_admit', 0.875, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000000.875)
    assert stored['window_seconds'] == pytest.approx(0.875)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p1875_w1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.1875)
    window.publish_spill('batch_admit', 1.0, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000001.0)
    assert stored['window_seconds'] == pytest.approx(1.0)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p1875_w1p25():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.1875)
    window.publish_spill('batch_admit', 1.25, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000001.25)
    assert stored['window_seconds'] == pytest.approx(1.25)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p1875_w1p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.1875)
    window.publish_spill('batch_admit', 1.5, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000001.5)
    assert stored['window_seconds'] == pytest.approx(1.5)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p1875_w1p75():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.1875)
    window.publish_spill('batch_admit', 1.75, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000001.75)
    assert stored['window_seconds'] == pytest.approx(1.75)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p1875_w2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.1875)
    window.publish_spill('batch_admit', 2.0, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000002.0)
    assert stored['window_seconds'] == pytest.approx(2.0)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p1875_w2p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.1875)
    window.publish_spill('batch_admit', 2.5, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000002.5)
    assert stored['window_seconds'] == pytest.approx(2.5)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p1875_w3():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.1875)
    window.publish_spill('batch_admit', 3.0, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000003.0)
    assert stored['window_seconds'] == pytest.approx(3.0)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p1875_w3p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.1875)
    window.publish_spill('batch_admit', 3.5, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000003.5)
    assert stored['window_seconds'] == pytest.approx(3.5)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p1875_w4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.1875)
    window.publish_spill('batch_admit', 4.0, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000004.0)
    assert stored['window_seconds'] == pytest.approx(4.0)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p25_w0p125():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.25)
    window.publish_spill('batch_admit', 0.125, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000000.25)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d0p25_w0p15625():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.25)
    window.publish_spill('batch_admit', 0.15625, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000000.25)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d0p25_w0p1875():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.25)
    window.publish_spill('batch_admit', 0.1875, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000000.25)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d0p25_w0p21875():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.25)
    window.publish_spill('batch_admit', 0.21875, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000000.25)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d0p25_w0p25():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.25)
    window.publish_spill('batch_admit', 0.25, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000000.25)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d0p25_w0p3125():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.25)
    window.publish_spill('batch_admit', 0.3125, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000000.3125)
    assert stored['window_seconds'] == pytest.approx(0.3125)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p25_w0p375():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.25)
    window.publish_spill('batch_admit', 0.375, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000000.375)
    assert stored['window_seconds'] == pytest.approx(0.375)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p25_w0p4375():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.25)
    window.publish_spill('batch_admit', 0.4375, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000000.4375)
    assert stored['window_seconds'] == pytest.approx(0.4375)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p25_w0p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.25)
    window.publish_spill('batch_admit', 0.5, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000000.5)
    assert stored['window_seconds'] == pytest.approx(0.5)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p25_w0p625():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.25)
    window.publish_spill('batch_admit', 0.625, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000000.625)
    assert stored['window_seconds'] == pytest.approx(0.625)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p25_w0p75():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.25)
    window.publish_spill('batch_admit', 0.75, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000000.75)
    assert stored['window_seconds'] == pytest.approx(0.75)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p25_w0p875():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.25)
    window.publish_spill('batch_admit', 0.875, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000000.875)
    assert stored['window_seconds'] == pytest.approx(0.875)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p25_w1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.25)
    window.publish_spill('batch_admit', 1.0, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000001.0)
    assert stored['window_seconds'] == pytest.approx(1.0)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p25_w1p25():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.25)
    window.publish_spill('batch_admit', 1.25, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000001.25)
    assert stored['window_seconds'] == pytest.approx(1.25)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p25_w1p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.25)
    window.publish_spill('batch_admit', 1.5, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000001.5)
    assert stored['window_seconds'] == pytest.approx(1.5)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p25_w1p75():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.25)
    window.publish_spill('batch_admit', 1.75, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000001.75)
    assert stored['window_seconds'] == pytest.approx(1.75)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p25_w2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.25)
    window.publish_spill('batch_admit', 2.0, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000002.0)
    assert stored['window_seconds'] == pytest.approx(2.0)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p25_w2p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.25)
    window.publish_spill('batch_admit', 2.5, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000002.5)
    assert stored['window_seconds'] == pytest.approx(2.5)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p25_w3():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.25)
    window.publish_spill('batch_admit', 3.0, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000003.0)
    assert stored['window_seconds'] == pytest.approx(3.0)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p25_w3p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.25)
    window.publish_spill('batch_admit', 3.5, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000003.5)
    assert stored['window_seconds'] == pytest.approx(3.5)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p25_w4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.25)
    window.publish_spill('batch_admit', 4.0, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000004.0)
    assert stored['window_seconds'] == pytest.approx(4.0)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p3125_w0p125():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.3125)
    window.publish_spill('batch_admit', 0.125, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000000.3125)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d0p3125_w0p15625():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.3125)
    window.publish_spill('batch_admit', 0.15625, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000000.3125)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d0p3125_w0p1875():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.3125)
    window.publish_spill('batch_admit', 0.1875, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000000.3125)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d0p3125_w0p21875():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.3125)
    window.publish_spill('batch_admit', 0.21875, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000000.3125)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d0p3125_w0p25():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.3125)
    window.publish_spill('batch_admit', 0.25, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000000.3125)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d0p3125_w0p3125():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.3125)
    window.publish_spill('batch_admit', 0.3125, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000000.3125)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d0p3125_w0p375():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.3125)
    window.publish_spill('batch_admit', 0.375, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000000.375)
    assert stored['window_seconds'] == pytest.approx(0.375)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p3125_w0p4375():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.3125)
    window.publish_spill('batch_admit', 0.4375, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000000.4375)
    assert stored['window_seconds'] == pytest.approx(0.4375)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p3125_w0p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.3125)
    window.publish_spill('batch_admit', 0.5, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000000.5)
    assert stored['window_seconds'] == pytest.approx(0.5)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p3125_w0p625():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.3125)
    window.publish_spill('batch_admit', 0.625, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000000.625)
    assert stored['window_seconds'] == pytest.approx(0.625)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p3125_w0p75():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.3125)
    window.publish_spill('batch_admit', 0.75, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000000.75)
    assert stored['window_seconds'] == pytest.approx(0.75)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p3125_w0p875():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.3125)
    window.publish_spill('batch_admit', 0.875, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000000.875)
    assert stored['window_seconds'] == pytest.approx(0.875)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p3125_w1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.3125)
    window.publish_spill('batch_admit', 1.0, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000001.0)
    assert stored['window_seconds'] == pytest.approx(1.0)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p3125_w1p25():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.3125)
    window.publish_spill('batch_admit', 1.25, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000001.25)
    assert stored['window_seconds'] == pytest.approx(1.25)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p3125_w1p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.3125)
    window.publish_spill('batch_admit', 1.5, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000001.5)
    assert stored['window_seconds'] == pytest.approx(1.5)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p3125_w1p75():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.3125)
    window.publish_spill('batch_admit', 1.75, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000001.75)
    assert stored['window_seconds'] == pytest.approx(1.75)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p3125_w2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.3125)
    window.publish_spill('batch_admit', 2.0, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000002.0)
    assert stored['window_seconds'] == pytest.approx(2.0)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p3125_w2p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.3125)
    window.publish_spill('batch_admit', 2.5, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000002.5)
    assert stored['window_seconds'] == pytest.approx(2.5)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p3125_w3():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.3125)
    window.publish_spill('batch_admit', 3.0, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000003.0)
    assert stored['window_seconds'] == pytest.approx(3.0)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p3125_w3p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.3125)
    window.publish_spill('batch_admit', 3.5, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000003.5)
    assert stored['window_seconds'] == pytest.approx(3.5)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p3125_w4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.3125)
    window.publish_spill('batch_admit', 4.0, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000004.0)
    assert stored['window_seconds'] == pytest.approx(4.0)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p375_w0p125():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.375)
    window.publish_spill('batch_admit', 0.125, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000000.375)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d0p375_w0p15625():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.375)
    window.publish_spill('batch_admit', 0.15625, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000000.375)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d0p375_w0p1875():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.375)
    window.publish_spill('batch_admit', 0.1875, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000000.375)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d0p375_w0p21875():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.375)
    window.publish_spill('batch_admit', 0.21875, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000000.375)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d0p375_w0p25():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.375)
    window.publish_spill('batch_admit', 0.25, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000000.375)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d0p375_w0p3125():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.375)
    window.publish_spill('batch_admit', 0.3125, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000000.375)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d0p375_w0p375():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.375)
    window.publish_spill('batch_admit', 0.375, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000000.375)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d0p375_w0p4375():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.375)
    window.publish_spill('batch_admit', 0.4375, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000000.4375)
    assert stored['window_seconds'] == pytest.approx(0.4375)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p375_w0p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.375)
    window.publish_spill('batch_admit', 0.5, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000000.5)
    assert stored['window_seconds'] == pytest.approx(0.5)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p375_w0p625():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.375)
    window.publish_spill('batch_admit', 0.625, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000000.625)
    assert stored['window_seconds'] == pytest.approx(0.625)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p375_w0p75():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.375)
    window.publish_spill('batch_admit', 0.75, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000000.75)
    assert stored['window_seconds'] == pytest.approx(0.75)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p375_w0p875():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.375)
    window.publish_spill('batch_admit', 0.875, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000000.875)
    assert stored['window_seconds'] == pytest.approx(0.875)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p375_w1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.375)
    window.publish_spill('batch_admit', 1.0, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000001.0)
    assert stored['window_seconds'] == pytest.approx(1.0)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p375_w1p25():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.375)
    window.publish_spill('batch_admit', 1.25, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000001.25)
    assert stored['window_seconds'] == pytest.approx(1.25)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p375_w1p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.375)
    window.publish_spill('batch_admit', 1.5, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000001.5)
    assert stored['window_seconds'] == pytest.approx(1.5)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p375_w1p75():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.375)
    window.publish_spill('batch_admit', 1.75, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000001.75)
    assert stored['window_seconds'] == pytest.approx(1.75)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p375_w2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.375)
    window.publish_spill('batch_admit', 2.0, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000002.0)
    assert stored['window_seconds'] == pytest.approx(2.0)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p375_w2p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.375)
    window.publish_spill('batch_admit', 2.5, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000002.5)
    assert stored['window_seconds'] == pytest.approx(2.5)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p375_w3():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.375)
    window.publish_spill('batch_admit', 3.0, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000003.0)
    assert stored['window_seconds'] == pytest.approx(3.0)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p375_w3p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.375)
    window.publish_spill('batch_admit', 3.5, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000003.5)
    assert stored['window_seconds'] == pytest.approx(3.5)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p375_w4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.375)
    window.publish_spill('batch_admit', 4.0, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000004.0)
    assert stored['window_seconds'] == pytest.approx(4.0)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p4375_w0p125():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.4375)
    window.publish_spill('batch_admit', 0.125, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000000.4375)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d0p4375_w0p15625():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.4375)
    window.publish_spill('batch_admit', 0.15625, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000000.4375)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d0p4375_w0p1875():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.4375)
    window.publish_spill('batch_admit', 0.1875, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000000.4375)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d0p4375_w0p21875():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.4375)
    window.publish_spill('batch_admit', 0.21875, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000000.4375)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d0p4375_w0p25():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.4375)
    window.publish_spill('batch_admit', 0.25, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000000.4375)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d0p4375_w0p3125():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.4375)
    window.publish_spill('batch_admit', 0.3125, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000000.4375)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d0p4375_w0p375():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.4375)
    window.publish_spill('batch_admit', 0.375, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000000.4375)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d0p4375_w0p4375():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.4375)
    window.publish_spill('batch_admit', 0.4375, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000000.4375)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d0p4375_w0p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.4375)
    window.publish_spill('batch_admit', 0.5, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000000.5)
    assert stored['window_seconds'] == pytest.approx(0.5)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p4375_w0p625():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.4375)
    window.publish_spill('batch_admit', 0.625, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000000.625)
    assert stored['window_seconds'] == pytest.approx(0.625)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p4375_w0p75():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.4375)
    window.publish_spill('batch_admit', 0.75, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000000.75)
    assert stored['window_seconds'] == pytest.approx(0.75)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p4375_w0p875():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.4375)
    window.publish_spill('batch_admit', 0.875, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000000.875)
    assert stored['window_seconds'] == pytest.approx(0.875)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p4375_w1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.4375)
    window.publish_spill('batch_admit', 1.0, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000001.0)
    assert stored['window_seconds'] == pytest.approx(1.0)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p4375_w1p25():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.4375)
    window.publish_spill('batch_admit', 1.25, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000001.25)
    assert stored['window_seconds'] == pytest.approx(1.25)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p4375_w1p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.4375)
    window.publish_spill('batch_admit', 1.5, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000001.5)
    assert stored['window_seconds'] == pytest.approx(1.5)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p4375_w1p75():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.4375)
    window.publish_spill('batch_admit', 1.75, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000001.75)
    assert stored['window_seconds'] == pytest.approx(1.75)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p4375_w2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.4375)
    window.publish_spill('batch_admit', 2.0, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000002.0)
    assert stored['window_seconds'] == pytest.approx(2.0)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p4375_w2p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.4375)
    window.publish_spill('batch_admit', 2.5, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000002.5)
    assert stored['window_seconds'] == pytest.approx(2.5)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p4375_w3():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.4375)
    window.publish_spill('batch_admit', 3.0, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000003.0)
    assert stored['window_seconds'] == pytest.approx(3.0)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p4375_w3p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.4375)
    window.publish_spill('batch_admit', 3.5, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000003.5)
    assert stored['window_seconds'] == pytest.approx(3.5)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p4375_w4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.4375)
    window.publish_spill('batch_admit', 4.0, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000004.0)
    assert stored['window_seconds'] == pytest.approx(4.0)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p5_w0p125():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.5)
    window.publish_spill('batch_admit', 0.125, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000000.5)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d0p5_w0p15625():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.5)
    window.publish_spill('batch_admit', 0.15625, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000000.5)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d0p5_w0p1875():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.5)
    window.publish_spill('batch_admit', 0.1875, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000000.5)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d0p5_w0p21875():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.5)
    window.publish_spill('batch_admit', 0.21875, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000000.5)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d0p5_w0p25():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.5)
    window.publish_spill('batch_admit', 0.25, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000000.5)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d0p5_w0p3125():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.5)
    window.publish_spill('batch_admit', 0.3125, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000000.5)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d0p5_w0p375():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.5)
    window.publish_spill('batch_admit', 0.375, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000000.5)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d0p5_w0p4375():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.5)
    window.publish_spill('batch_admit', 0.4375, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000000.5)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d0p5_w0p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.5)
    window.publish_spill('batch_admit', 0.5, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000000.5)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d0p5_w0p625():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.5)
    window.publish_spill('batch_admit', 0.625, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000000.625)
    assert stored['window_seconds'] == pytest.approx(0.625)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p5_w0p75():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.5)
    window.publish_spill('batch_admit', 0.75, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000000.75)
    assert stored['window_seconds'] == pytest.approx(0.75)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p5_w0p875():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.5)
    window.publish_spill('batch_admit', 0.875, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000000.875)
    assert stored['window_seconds'] == pytest.approx(0.875)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p5_w1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.5)
    window.publish_spill('batch_admit', 1.0, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000001.0)
    assert stored['window_seconds'] == pytest.approx(1.0)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p5_w1p25():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.5)
    window.publish_spill('batch_admit', 1.25, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000001.25)
    assert stored['window_seconds'] == pytest.approx(1.25)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p5_w1p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.5)
    window.publish_spill('batch_admit', 1.5, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000001.5)
    assert stored['window_seconds'] == pytest.approx(1.5)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p5_w1p75():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.5)
    window.publish_spill('batch_admit', 1.75, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000001.75)
    assert stored['window_seconds'] == pytest.approx(1.75)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p5_w2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.5)
    window.publish_spill('batch_admit', 2.0, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000002.0)
    assert stored['window_seconds'] == pytest.approx(2.0)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p5_w2p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.5)
    window.publish_spill('batch_admit', 2.5, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000002.5)
    assert stored['window_seconds'] == pytest.approx(2.5)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p5_w3():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.5)
    window.publish_spill('batch_admit', 3.0, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000003.0)
    assert stored['window_seconds'] == pytest.approx(3.0)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p5_w3p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.5)
    window.publish_spill('batch_admit', 3.5, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000003.5)
    assert stored['window_seconds'] == pytest.approx(3.5)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p5_w4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.5)
    window.publish_spill('batch_admit', 4.0, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000004.0)
    assert stored['window_seconds'] == pytest.approx(4.0)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p625_w0p125():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.625)
    window.publish_spill('batch_admit', 0.125, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000000.625)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d0p625_w0p15625():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.625)
    window.publish_spill('batch_admit', 0.15625, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000000.625)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d0p625_w0p1875():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.625)
    window.publish_spill('batch_admit', 0.1875, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000000.625)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d0p625_w0p21875():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.625)
    window.publish_spill('batch_admit', 0.21875, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000000.625)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d0p625_w0p25():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.625)
    window.publish_spill('batch_admit', 0.25, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000000.625)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d0p625_w0p3125():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.625)
    window.publish_spill('batch_admit', 0.3125, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000000.625)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d0p625_w0p375():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.625)
    window.publish_spill('batch_admit', 0.375, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000000.625)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d0p625_w0p4375():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.625)
    window.publish_spill('batch_admit', 0.4375, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000000.625)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d0p625_w0p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.625)
    window.publish_spill('batch_admit', 0.5, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000000.625)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d0p625_w0p625():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.625)
    window.publish_spill('batch_admit', 0.625, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000000.625)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d0p625_w0p75():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.625)
    window.publish_spill('batch_admit', 0.75, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000000.75)
    assert stored['window_seconds'] == pytest.approx(0.75)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p625_w0p875():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.625)
    window.publish_spill('batch_admit', 0.875, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000000.875)
    assert stored['window_seconds'] == pytest.approx(0.875)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p625_w1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.625)
    window.publish_spill('batch_admit', 1.0, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000001.0)
    assert stored['window_seconds'] == pytest.approx(1.0)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p625_w1p25():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.625)
    window.publish_spill('batch_admit', 1.25, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000001.25)
    assert stored['window_seconds'] == pytest.approx(1.25)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p625_w1p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.625)
    window.publish_spill('batch_admit', 1.5, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000001.5)
    assert stored['window_seconds'] == pytest.approx(1.5)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p625_w1p75():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.625)
    window.publish_spill('batch_admit', 1.75, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000001.75)
    assert stored['window_seconds'] == pytest.approx(1.75)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p625_w2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.625)
    window.publish_spill('batch_admit', 2.0, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000002.0)
    assert stored['window_seconds'] == pytest.approx(2.0)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p625_w2p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.625)
    window.publish_spill('batch_admit', 2.5, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000002.5)
    assert stored['window_seconds'] == pytest.approx(2.5)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p625_w3():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.625)
    window.publish_spill('batch_admit', 3.0, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000003.0)
    assert stored['window_seconds'] == pytest.approx(3.0)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p625_w3p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.625)
    window.publish_spill('batch_admit', 3.5, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000003.5)
    assert stored['window_seconds'] == pytest.approx(3.5)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p625_w4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.625)
    window.publish_spill('batch_admit', 4.0, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000004.0)
    assert stored['window_seconds'] == pytest.approx(4.0)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p75_w0p125():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.75)
    window.publish_spill('batch_admit', 0.125, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000000.75)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d0p75_w0p15625():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.75)
    window.publish_spill('batch_admit', 0.15625, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000000.75)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d0p75_w0p1875():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.75)
    window.publish_spill('batch_admit', 0.1875, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000000.75)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d0p75_w0p21875():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.75)
    window.publish_spill('batch_admit', 0.21875, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000000.75)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d0p75_w0p25():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.75)
    window.publish_spill('batch_admit', 0.25, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000000.75)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d0p75_w0p3125():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.75)
    window.publish_spill('batch_admit', 0.3125, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000000.75)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d0p75_w0p375():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.75)
    window.publish_spill('batch_admit', 0.375, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000000.75)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d0p75_w0p4375():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.75)
    window.publish_spill('batch_admit', 0.4375, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000000.75)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d0p75_w0p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.75)
    window.publish_spill('batch_admit', 0.5, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000000.75)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d0p75_w0p625():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.75)
    window.publish_spill('batch_admit', 0.625, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000000.75)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d0p75_w0p75():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.75)
    window.publish_spill('batch_admit', 0.75, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000000.75)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d0p75_w0p875():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.75)
    window.publish_spill('batch_admit', 0.875, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000000.875)
    assert stored['window_seconds'] == pytest.approx(0.875)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p75_w1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.75)
    window.publish_spill('batch_admit', 1.0, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000001.0)
    assert stored['window_seconds'] == pytest.approx(1.0)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p75_w1p25():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.75)
    window.publish_spill('batch_admit', 1.25, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000001.25)
    assert stored['window_seconds'] == pytest.approx(1.25)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p75_w1p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.75)
    window.publish_spill('batch_admit', 1.5, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000001.5)
    assert stored['window_seconds'] == pytest.approx(1.5)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p75_w1p75():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.75)
    window.publish_spill('batch_admit', 1.75, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000001.75)
    assert stored['window_seconds'] == pytest.approx(1.75)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p75_w2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.75)
    window.publish_spill('batch_admit', 2.0, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000002.0)
    assert stored['window_seconds'] == pytest.approx(2.0)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p75_w2p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.75)
    window.publish_spill('batch_admit', 2.5, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000002.5)
    assert stored['window_seconds'] == pytest.approx(2.5)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p75_w3():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.75)
    window.publish_spill('batch_admit', 3.0, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000003.0)
    assert stored['window_seconds'] == pytest.approx(3.0)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p75_w3p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.75)
    window.publish_spill('batch_admit', 3.5, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000003.5)
    assert stored['window_seconds'] == pytest.approx(3.5)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p75_w4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.75)
    window.publish_spill('batch_admit', 4.0, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000004.0)
    assert stored['window_seconds'] == pytest.approx(4.0)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p875_w0p125():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.875)
    window.publish_spill('batch_admit', 0.125, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000000.875)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d0p875_w0p15625():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.875)
    window.publish_spill('batch_admit', 0.15625, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000000.875)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d0p875_w0p1875():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.875)
    window.publish_spill('batch_admit', 0.1875, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000000.875)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d0p875_w0p21875():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.875)
    window.publish_spill('batch_admit', 0.21875, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000000.875)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d0p875_w0p25():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.875)
    window.publish_spill('batch_admit', 0.25, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000000.875)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d0p875_w0p3125():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.875)
    window.publish_spill('batch_admit', 0.3125, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000000.875)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d0p875_w0p375():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.875)
    window.publish_spill('batch_admit', 0.375, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000000.875)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d0p875_w0p4375():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.875)
    window.publish_spill('batch_admit', 0.4375, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000000.875)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d0p875_w0p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.875)
    window.publish_spill('batch_admit', 0.5, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000000.875)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d0p875_w0p625():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.875)
    window.publish_spill('batch_admit', 0.625, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000000.875)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d0p875_w0p75():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.875)
    window.publish_spill('batch_admit', 0.75, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000000.875)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d0p875_w0p875():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.875)
    window.publish_spill('batch_admit', 0.875, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000000.875)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d0p875_w1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.875)
    window.publish_spill('batch_admit', 1.0, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000001.0)
    assert stored['window_seconds'] == pytest.approx(1.0)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p875_w1p25():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.875)
    window.publish_spill('batch_admit', 1.25, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000001.25)
    assert stored['window_seconds'] == pytest.approx(1.25)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p875_w1p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.875)
    window.publish_spill('batch_admit', 1.5, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000001.5)
    assert stored['window_seconds'] == pytest.approx(1.5)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p875_w1p75():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.875)
    window.publish_spill('batch_admit', 1.75, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000001.75)
    assert stored['window_seconds'] == pytest.approx(1.75)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p875_w2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.875)
    window.publish_spill('batch_admit', 2.0, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000002.0)
    assert stored['window_seconds'] == pytest.approx(2.0)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p875_w2p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.875)
    window.publish_spill('batch_admit', 2.5, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000002.5)
    assert stored['window_seconds'] == pytest.approx(2.5)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p875_w3():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.875)
    window.publish_spill('batch_admit', 3.0, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000003.0)
    assert stored['window_seconds'] == pytest.approx(3.0)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p875_w3p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.875)
    window.publish_spill('batch_admit', 3.5, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000003.5)
    assert stored['window_seconds'] == pytest.approx(3.5)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d0p875_w4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.875)
    window.publish_spill('batch_admit', 4.0, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000004.0)
    assert stored['window_seconds'] == pytest.approx(4.0)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d1_w0p125():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 1.0)
    window.publish_spill('batch_admit', 0.125, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000001.0)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d1_w0p15625():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 1.0)
    window.publish_spill('batch_admit', 0.15625, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000001.0)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d1_w0p1875():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 1.0)
    window.publish_spill('batch_admit', 0.1875, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000001.0)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d1_w0p21875():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 1.0)
    window.publish_spill('batch_admit', 0.21875, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000001.0)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d1_w0p25():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 1.0)
    window.publish_spill('batch_admit', 0.25, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000001.0)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d1_w0p3125():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 1.0)
    window.publish_spill('batch_admit', 0.3125, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000001.0)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d1_w0p375():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 1.0)
    window.publish_spill('batch_admit', 0.375, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000001.0)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d1_w0p4375():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 1.0)
    window.publish_spill('batch_admit', 0.4375, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000001.0)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d1_w0p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 1.0)
    window.publish_spill('batch_admit', 0.5, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000001.0)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d1_w0p625():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 1.0)
    window.publish_spill('batch_admit', 0.625, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000001.0)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d1_w0p75():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 1.0)
    window.publish_spill('batch_admit', 0.75, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000001.0)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d1_w0p875():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 1.0)
    window.publish_spill('batch_admit', 0.875, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000001.0)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d1_w1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 1.0)
    window.publish_spill('batch_admit', 1.0, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000001.0)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d1_w1p25():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 1.0)
    window.publish_spill('batch_admit', 1.25, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000001.25)
    assert stored['window_seconds'] == pytest.approx(1.25)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d1_w1p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 1.0)
    window.publish_spill('batch_admit', 1.5, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000001.5)
    assert stored['window_seconds'] == pytest.approx(1.5)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d1_w1p75():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 1.0)
    window.publish_spill('batch_admit', 1.75, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000001.75)
    assert stored['window_seconds'] == pytest.approx(1.75)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d1_w2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 1.0)
    window.publish_spill('batch_admit', 2.0, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000002.0)
    assert stored['window_seconds'] == pytest.approx(2.0)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d1_w2p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 1.0)
    window.publish_spill('batch_admit', 2.5, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000002.5)
    assert stored['window_seconds'] == pytest.approx(2.5)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d1_w3():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 1.0)
    window.publish_spill('batch_admit', 3.0, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000003.0)
    assert stored['window_seconds'] == pytest.approx(3.0)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d1_w3p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 1.0)
    window.publish_spill('batch_admit', 3.5, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000003.5)
    assert stored['window_seconds'] == pytest.approx(3.5)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d1_w4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 1.0)
    window.publish_spill('batch_admit', 4.0, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000004.0)
    assert stored['window_seconds'] == pytest.approx(4.0)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d1p25_w0p125():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 1.25)
    window.publish_spill('batch_admit', 0.125, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000001.25)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d1p25_w0p15625():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 1.25)
    window.publish_spill('batch_admit', 0.15625, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000001.25)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d1p25_w0p1875():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 1.25)
    window.publish_spill('batch_admit', 0.1875, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000001.25)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d1p25_w0p21875():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 1.25)
    window.publish_spill('batch_admit', 0.21875, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000001.25)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d1p25_w0p25():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 1.25)
    window.publish_spill('batch_admit', 0.25, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000001.25)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d1p25_w0p3125():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 1.25)
    window.publish_spill('batch_admit', 0.3125, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000001.25)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d1p25_w0p375():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 1.25)
    window.publish_spill('batch_admit', 0.375, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000001.25)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d1p25_w0p4375():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 1.25)
    window.publish_spill('batch_admit', 0.4375, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000001.25)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d1p25_w0p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 1.25)
    window.publish_spill('batch_admit', 0.5, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000001.25)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d1p25_w0p625():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 1.25)
    window.publish_spill('batch_admit', 0.625, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000001.25)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d1p25_w0p75():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 1.25)
    window.publish_spill('batch_admit', 0.75, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000001.25)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d1p25_w0p875():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 1.25)
    window.publish_spill('batch_admit', 0.875, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000001.25)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d1p25_w1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 1.25)
    window.publish_spill('batch_admit', 1.0, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000001.25)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d1p25_w1p25():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 1.25)
    window.publish_spill('batch_admit', 1.25, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000001.25)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d1p25_w1p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 1.25)
    window.publish_spill('batch_admit', 1.5, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000001.5)
    assert stored['window_seconds'] == pytest.approx(1.5)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d1p25_w1p75():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 1.25)
    window.publish_spill('batch_admit', 1.75, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000001.75)
    assert stored['window_seconds'] == pytest.approx(1.75)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d1p25_w2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 1.25)
    window.publish_spill('batch_admit', 2.0, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000002.0)
    assert stored['window_seconds'] == pytest.approx(2.0)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d1p25_w2p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 1.25)
    window.publish_spill('batch_admit', 2.5, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000002.5)
    assert stored['window_seconds'] == pytest.approx(2.5)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d1p25_w3():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 1.25)
    window.publish_spill('batch_admit', 3.0, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000003.0)
    assert stored['window_seconds'] == pytest.approx(3.0)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d1p25_w3p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 1.25)
    window.publish_spill('batch_admit', 3.5, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000003.5)
    assert stored['window_seconds'] == pytest.approx(3.5)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d1p25_w4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 1.25)
    window.publish_spill('batch_admit', 4.0, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000004.0)
    assert stored['window_seconds'] == pytest.approx(4.0)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d1p5_w0p125():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 1.5)
    window.publish_spill('batch_admit', 0.125, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000001.5)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d1p5_w0p15625():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 1.5)
    window.publish_spill('batch_admit', 0.15625, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000001.5)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d1p5_w0p1875():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 1.5)
    window.publish_spill('batch_admit', 0.1875, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000001.5)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d1p5_w0p21875():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 1.5)
    window.publish_spill('batch_admit', 0.21875, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000001.5)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d1p5_w0p25():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 1.5)
    window.publish_spill('batch_admit', 0.25, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000001.5)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d1p5_w0p3125():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 1.5)
    window.publish_spill('batch_admit', 0.3125, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000001.5)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d1p5_w0p375():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 1.5)
    window.publish_spill('batch_admit', 0.375, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000001.5)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d1p5_w0p4375():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 1.5)
    window.publish_spill('batch_admit', 0.4375, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000001.5)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d1p5_w0p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 1.5)
    window.publish_spill('batch_admit', 0.5, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000001.5)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d1p5_w0p625():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 1.5)
    window.publish_spill('batch_admit', 0.625, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000001.5)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d1p5_w0p75():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 1.5)
    window.publish_spill('batch_admit', 0.75, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000001.5)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d1p5_w0p875():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 1.5)
    window.publish_spill('batch_admit', 0.875, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000001.5)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d1p5_w1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 1.5)
    window.publish_spill('batch_admit', 1.0, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000001.5)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d1p5_w1p25():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 1.5)
    window.publish_spill('batch_admit', 1.25, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000001.5)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d1p5_w1p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 1.5)
    window.publish_spill('batch_admit', 1.5, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000001.5)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d1p5_w1p75():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 1.5)
    window.publish_spill('batch_admit', 1.75, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000001.75)
    assert stored['window_seconds'] == pytest.approx(1.75)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d1p5_w2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 1.5)
    window.publish_spill('batch_admit', 2.0, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000002.0)
    assert stored['window_seconds'] == pytest.approx(2.0)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d1p5_w2p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 1.5)
    window.publish_spill('batch_admit', 2.5, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000002.5)
    assert stored['window_seconds'] == pytest.approx(2.5)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d1p5_w3():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 1.5)
    window.publish_spill('batch_admit', 3.0, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000003.0)
    assert stored['window_seconds'] == pytest.approx(3.0)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d1p5_w3p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 1.5)
    window.publish_spill('batch_admit', 3.5, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000003.5)
    assert stored['window_seconds'] == pytest.approx(3.5)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d1p5_w4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 1.5)
    window.publish_spill('batch_admit', 4.0, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000004.0)
    assert stored['window_seconds'] == pytest.approx(4.0)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d1p75_w0p125():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 1.75)
    window.publish_spill('batch_admit', 0.125, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000001.75)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d1p75_w0p15625():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 1.75)
    window.publish_spill('batch_admit', 0.15625, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000001.75)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d1p75_w0p1875():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 1.75)
    window.publish_spill('batch_admit', 0.1875, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000001.75)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d1p75_w0p21875():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 1.75)
    window.publish_spill('batch_admit', 0.21875, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000001.75)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d1p75_w0p25():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 1.75)
    window.publish_spill('batch_admit', 0.25, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000001.75)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d1p75_w0p3125():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 1.75)
    window.publish_spill('batch_admit', 0.3125, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000001.75)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d1p75_w0p375():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 1.75)
    window.publish_spill('batch_admit', 0.375, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000001.75)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d1p75_w0p4375():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 1.75)
    window.publish_spill('batch_admit', 0.4375, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000001.75)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d1p75_w0p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 1.75)
    window.publish_spill('batch_admit', 0.5, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000001.75)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d1p75_w0p625():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 1.75)
    window.publish_spill('batch_admit', 0.625, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000001.75)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d1p75_w0p75():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 1.75)
    window.publish_spill('batch_admit', 0.75, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000001.75)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d1p75_w0p875():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 1.75)
    window.publish_spill('batch_admit', 0.875, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000001.75)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d1p75_w1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 1.75)
    window.publish_spill('batch_admit', 1.0, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000001.75)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d1p75_w1p25():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 1.75)
    window.publish_spill('batch_admit', 1.25, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000001.75)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d1p75_w1p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 1.75)
    window.publish_spill('batch_admit', 1.5, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000001.75)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d1p75_w1p75():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 1.75)
    window.publish_spill('batch_admit', 1.75, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000001.75)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d1p75_w2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 1.75)
    window.publish_spill('batch_admit', 2.0, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000002.0)
    assert stored['window_seconds'] == pytest.approx(2.0)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d1p75_w2p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 1.75)
    window.publish_spill('batch_admit', 2.5, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000002.5)
    assert stored['window_seconds'] == pytest.approx(2.5)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d1p75_w3():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 1.75)
    window.publish_spill('batch_admit', 3.0, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000003.0)
    assert stored['window_seconds'] == pytest.approx(3.0)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d1p75_w3p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 1.75)
    window.publish_spill('batch_admit', 3.5, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000003.5)
    assert stored['window_seconds'] == pytest.approx(3.5)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d1p75_w4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 1.75)
    window.publish_spill('batch_admit', 4.0, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000004.0)
    assert stored['window_seconds'] == pytest.approx(4.0)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d2_w0p125():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 2.0)
    window.publish_spill('batch_admit', 0.125, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000002.0)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d2_w0p15625():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 2.0)
    window.publish_spill('batch_admit', 0.15625, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000002.0)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d2_w0p1875():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 2.0)
    window.publish_spill('batch_admit', 0.1875, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000002.0)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d2_w0p21875():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 2.0)
    window.publish_spill('batch_admit', 0.21875, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000002.0)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d2_w0p25():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 2.0)
    window.publish_spill('batch_admit', 0.25, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000002.0)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d2_w0p3125():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 2.0)
    window.publish_spill('batch_admit', 0.3125, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000002.0)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d2_w0p375():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 2.0)
    window.publish_spill('batch_admit', 0.375, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000002.0)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d2_w0p4375():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 2.0)
    window.publish_spill('batch_admit', 0.4375, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000002.0)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d2_w0p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 2.0)
    window.publish_spill('batch_admit', 0.5, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000002.0)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d2_w0p625():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 2.0)
    window.publish_spill('batch_admit', 0.625, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000002.0)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d2_w0p75():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 2.0)
    window.publish_spill('batch_admit', 0.75, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000002.0)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d2_w0p875():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 2.0)
    window.publish_spill('batch_admit', 0.875, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000002.0)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d2_w1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 2.0)
    window.publish_spill('batch_admit', 1.0, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000002.0)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d2_w1p25():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 2.0)
    window.publish_spill('batch_admit', 1.25, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000002.0)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d2_w1p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 2.0)
    window.publish_spill('batch_admit', 1.5, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000002.0)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d2_w1p75():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 2.0)
    window.publish_spill('batch_admit', 1.75, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000002.0)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d2_w2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 2.0)
    window.publish_spill('batch_admit', 2.0, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000002.0)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d2_w2p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 2.0)
    window.publish_spill('batch_admit', 2.5, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000002.5)
    assert stored['window_seconds'] == pytest.approx(2.5)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d2_w3():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 2.0)
    window.publish_spill('batch_admit', 3.0, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000003.0)
    assert stored['window_seconds'] == pytest.approx(3.0)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d2_w3p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 2.0)
    window.publish_spill('batch_admit', 3.5, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000003.5)
    assert stored['window_seconds'] == pytest.approx(3.5)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d2_w4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 2.0)
    window.publish_spill('batch_admit', 4.0, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000004.0)
    assert stored['window_seconds'] == pytest.approx(4.0)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d2p5_w0p125():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 2.5)
    window.publish_spill('batch_admit', 0.125, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000002.5)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d2p5_w0p15625():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 2.5)
    window.publish_spill('batch_admit', 0.15625, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000002.5)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d2p5_w0p1875():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 2.5)
    window.publish_spill('batch_admit', 0.1875, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000002.5)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d2p5_w0p21875():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 2.5)
    window.publish_spill('batch_admit', 0.21875, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000002.5)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d2p5_w0p25():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 2.5)
    window.publish_spill('batch_admit', 0.25, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000002.5)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d2p5_w0p3125():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 2.5)
    window.publish_spill('batch_admit', 0.3125, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000002.5)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d2p5_w0p375():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 2.5)
    window.publish_spill('batch_admit', 0.375, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000002.5)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d2p5_w0p4375():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 2.5)
    window.publish_spill('batch_admit', 0.4375, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000002.5)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d2p5_w0p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 2.5)
    window.publish_spill('batch_admit', 0.5, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000002.5)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d2p5_w0p625():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 2.5)
    window.publish_spill('batch_admit', 0.625, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000002.5)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d2p5_w0p75():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 2.5)
    window.publish_spill('batch_admit', 0.75, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000002.5)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d2p5_w0p875():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 2.5)
    window.publish_spill('batch_admit', 0.875, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000002.5)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d2p5_w1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 2.5)
    window.publish_spill('batch_admit', 1.0, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000002.5)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d2p5_w1p25():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 2.5)
    window.publish_spill('batch_admit', 1.25, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000002.5)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d2p5_w1p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 2.5)
    window.publish_spill('batch_admit', 1.5, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000002.5)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d2p5_w1p75():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 2.5)
    window.publish_spill('batch_admit', 1.75, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000002.5)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d2p5_w2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 2.5)
    window.publish_spill('batch_admit', 2.0, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000002.5)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d2p5_w2p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 2.5)
    window.publish_spill('batch_admit', 2.5, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000002.5)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d2p5_w3():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 2.5)
    window.publish_spill('batch_admit', 3.0, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000003.0)
    assert stored['window_seconds'] == pytest.approx(3.0)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d2p5_w3p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 2.5)
    window.publish_spill('batch_admit', 3.5, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000003.5)
    assert stored['window_seconds'] == pytest.approx(3.5)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d2p5_w4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 2.5)
    window.publish_spill('batch_admit', 4.0, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000004.0)
    assert stored['window_seconds'] == pytest.approx(4.0)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d3_w0p125():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 3.0)
    window.publish_spill('batch_admit', 0.125, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000003.0)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d3_w0p15625():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 3.0)
    window.publish_spill('batch_admit', 0.15625, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000003.0)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d3_w0p1875():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 3.0)
    window.publish_spill('batch_admit', 0.1875, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000003.0)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d3_w0p21875():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 3.0)
    window.publish_spill('batch_admit', 0.21875, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000003.0)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d3_w0p25():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 3.0)
    window.publish_spill('batch_admit', 0.25, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000003.0)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d3_w0p3125():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 3.0)
    window.publish_spill('batch_admit', 0.3125, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000003.0)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d3_w0p375():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 3.0)
    window.publish_spill('batch_admit', 0.375, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000003.0)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d3_w0p4375():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 3.0)
    window.publish_spill('batch_admit', 0.4375, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000003.0)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d3_w0p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 3.0)
    window.publish_spill('batch_admit', 0.5, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000003.0)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d3_w0p625():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 3.0)
    window.publish_spill('batch_admit', 0.625, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000003.0)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d3_w0p75():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 3.0)
    window.publish_spill('batch_admit', 0.75, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000003.0)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d3_w0p875():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 3.0)
    window.publish_spill('batch_admit', 0.875, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000003.0)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d3_w1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 3.0)
    window.publish_spill('batch_admit', 1.0, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000003.0)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d3_w1p25():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 3.0)
    window.publish_spill('batch_admit', 1.25, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000003.0)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d3_w1p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 3.0)
    window.publish_spill('batch_admit', 1.5, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000003.0)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d3_w1p75():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 3.0)
    window.publish_spill('batch_admit', 1.75, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000003.0)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d3_w2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 3.0)
    window.publish_spill('batch_admit', 2.0, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000003.0)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d3_w2p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 3.0)
    window.publish_spill('batch_admit', 2.5, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000003.0)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d3_w3():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 3.0)
    window.publish_spill('batch_admit', 3.0, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000003.0)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d3_w3p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 3.0)
    window.publish_spill('batch_admit', 3.5, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000003.5)
    assert stored['window_seconds'] == pytest.approx(3.5)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d3_w4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 3.0)
    window.publish_spill('batch_admit', 4.0, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000004.0)
    assert stored['window_seconds'] == pytest.approx(4.0)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d3p5_w0p125():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 3.5)
    window.publish_spill('batch_admit', 0.125, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000003.5)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d3p5_w0p15625():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 3.5)
    window.publish_spill('batch_admit', 0.15625, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000003.5)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d3p5_w0p1875():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 3.5)
    window.publish_spill('batch_admit', 0.1875, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000003.5)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d3p5_w0p21875():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 3.5)
    window.publish_spill('batch_admit', 0.21875, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000003.5)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d3p5_w0p25():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 3.5)
    window.publish_spill('batch_admit', 0.25, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000003.5)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d3p5_w0p3125():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 3.5)
    window.publish_spill('batch_admit', 0.3125, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000003.5)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d3p5_w0p375():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 3.5)
    window.publish_spill('batch_admit', 0.375, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000003.5)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d3p5_w0p4375():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 3.5)
    window.publish_spill('batch_admit', 0.4375, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000003.5)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d3p5_w0p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 3.5)
    window.publish_spill('batch_admit', 0.5, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000003.5)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d3p5_w0p625():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 3.5)
    window.publish_spill('batch_admit', 0.625, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000003.5)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d3p5_w0p75():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 3.5)
    window.publish_spill('batch_admit', 0.75, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000003.5)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d3p5_w0p875():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 3.5)
    window.publish_spill('batch_admit', 0.875, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000003.5)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d3p5_w1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 3.5)
    window.publish_spill('batch_admit', 1.0, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000003.5)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d3p5_w1p25():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 3.5)
    window.publish_spill('batch_admit', 1.25, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000003.5)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d3p5_w1p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 3.5)
    window.publish_spill('batch_admit', 1.5, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000003.5)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d3p5_w1p75():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 3.5)
    window.publish_spill('batch_admit', 1.75, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000003.5)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d3p5_w2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 3.5)
    window.publish_spill('batch_admit', 2.0, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000003.5)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d3p5_w2p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 3.5)
    window.publish_spill('batch_admit', 2.5, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000003.5)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d3p5_w3():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 3.5)
    window.publish_spill('batch_admit', 3.0, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000003.5)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d3p5_w3p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 3.5)
    window.publish_spill('batch_admit', 3.5, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000003.5)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d3p5_w4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 3.5)
    window.publish_spill('batch_admit', 4.0, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000004.0)
    assert stored['window_seconds'] == pytest.approx(4.0)
    assert window.spill_publishes == 1
    assert window.spill_publish_skips == 0


def test_floor_d4_w0p125():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    window.publish_spill('batch_admit', 0.125, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000004.0)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d4_w0p15625():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    window.publish_spill('batch_admit', 0.15625, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000004.0)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d4_w0p1875():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    window.publish_spill('batch_admit', 0.1875, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000004.0)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d4_w0p21875():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    window.publish_spill('batch_admit', 0.21875, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000004.0)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d4_w0p25():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    window.publish_spill('batch_admit', 0.25, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000004.0)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d4_w0p3125():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    window.publish_spill('batch_admit', 0.3125, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000004.0)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d4_w0p375():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    window.publish_spill('batch_admit', 0.375, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000004.0)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d4_w0p4375():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    window.publish_spill('batch_admit', 0.4375, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000004.0)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d4_w0p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    window.publish_spill('batch_admit', 0.5, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000004.0)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d4_w0p625():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    window.publish_spill('batch_admit', 0.625, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000004.0)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d4_w0p75():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    window.publish_spill('batch_admit', 0.75, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000004.0)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d4_w0p875():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    window.publish_spill('batch_admit', 0.875, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000004.0)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d4_w1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    window.publish_spill('batch_admit', 1.0, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000004.0)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d4_w1p25():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    window.publish_spill('batch_admit', 1.25, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000004.0)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d4_w1p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    window.publish_spill('batch_admit', 1.5, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000004.0)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d4_w1p75():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    window.publish_spill('batch_admit', 1.75, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000004.0)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d4_w2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    window.publish_spill('batch_admit', 2.0, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000004.0)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d4_w2p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    window.publish_spill('batch_admit', 2.5, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000004.0)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d4_w3():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    window.publish_spill('batch_admit', 3.0, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000004.0)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d4_w3p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    window.publish_spill('batch_admit', 3.5, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000004.0)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d4_w4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    window.publish_spill('batch_admit', 4.0, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000004.0)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d4p5_w0p125():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.5)
    window.publish_spill('batch_admit', 0.125, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000004.5)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d4p5_w0p15625():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.5)
    window.publish_spill('batch_admit', 0.15625, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000004.5)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d4p5_w0p1875():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.5)
    window.publish_spill('batch_admit', 0.1875, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000004.5)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d4p5_w0p21875():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.5)
    window.publish_spill('batch_admit', 0.21875, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000004.5)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d4p5_w0p25():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.5)
    window.publish_spill('batch_admit', 0.25, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000004.5)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d4p5_w0p3125():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.5)
    window.publish_spill('batch_admit', 0.3125, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000004.5)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d4p5_w0p375():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.5)
    window.publish_spill('batch_admit', 0.375, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000004.5)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d4p5_w0p4375():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.5)
    window.publish_spill('batch_admit', 0.4375, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000004.5)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d4p5_w0p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.5)
    window.publish_spill('batch_admit', 0.5, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000004.5)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d4p5_w0p625():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.5)
    window.publish_spill('batch_admit', 0.625, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000004.5)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d4p5_w0p75():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.5)
    window.publish_spill('batch_admit', 0.75, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000004.5)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d4p5_w0p875():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.5)
    window.publish_spill('batch_admit', 0.875, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000004.5)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d4p5_w1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.5)
    window.publish_spill('batch_admit', 1.0, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000004.5)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d4p5_w1p25():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.5)
    window.publish_spill('batch_admit', 1.25, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000004.5)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d4p5_w1p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.5)
    window.publish_spill('batch_admit', 1.5, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000004.5)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d4p5_w1p75():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.5)
    window.publish_spill('batch_admit', 1.75, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000004.5)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d4p5_w2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.5)
    window.publish_spill('batch_admit', 2.0, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000004.5)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d4p5_w2p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.5)
    window.publish_spill('batch_admit', 2.5, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000004.5)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d4p5_w3():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.5)
    window.publish_spill('batch_admit', 3.0, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000004.5)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d4p5_w3p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.5)
    window.publish_spill('batch_admit', 3.5, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000004.5)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_floor_d4p5_w4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.5)
    window.publish_spill('batch_admit', 4.0, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000004.5)  # the deeper live spill stands
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_stamp_batch_admit_w0p125():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    window.publish_spill('batch_admit', 0.125, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['label'] == 'batch_admit'
    assert stored['armed_until'] == pytest.approx(WALL0 + 0.125)
    assert stored['window_seconds'] == pytest.approx(0.125)


def test_stamp_batch_admit_w1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    window.publish_spill('batch_admit', 1.0, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['label'] == 'batch_admit'
    assert stored['armed_until'] == pytest.approx(WALL0 + 1.0)
    assert stored['window_seconds'] == pytest.approx(1.0)


def test_stamp_batch_admit_w4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    window.publish_spill('batch_admit', 4.0, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['label'] == 'batch_admit'
    assert stored['armed_until'] == pytest.approx(WALL0 + 4.0)
    assert stored['window_seconds'] == pytest.approx(4.0)


def test_stamp_batch_merge_w0p125():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    window.publish_spill('batch_merge', 0.125, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['label'] == 'batch_merge'
    assert stored['armed_until'] == pytest.approx(WALL0 + 0.125)
    assert stored['window_seconds'] == pytest.approx(0.125)


def test_stamp_batch_merge_w1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    window.publish_spill('batch_merge', 1.0, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['label'] == 'batch_merge'
    assert stored['armed_until'] == pytest.approx(WALL0 + 1.0)
    assert stored['window_seconds'] == pytest.approx(1.0)


def test_stamp_batch_merge_w4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    window.publish_spill('batch_merge', 4.0, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['label'] == 'batch_merge'
    assert stored['armed_until'] == pytest.approx(WALL0 + 4.0)
    assert stored['window_seconds'] == pytest.approx(4.0)


def test_stamp_batch_merge_commit_w0p125():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    window.publish_spill('batch_merge_commit', 0.125, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['label'] == 'batch_merge_commit'
    assert stored['armed_until'] == pytest.approx(WALL0 + 0.125)
    assert stored['window_seconds'] == pytest.approx(0.125)


def test_stamp_batch_merge_commit_w1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    window.publish_spill('batch_merge_commit', 1.0, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['label'] == 'batch_merge_commit'
    assert stored['armed_until'] == pytest.approx(WALL0 + 1.0)
    assert stored['window_seconds'] == pytest.approx(1.0)


def test_stamp_batch_merge_commit_w4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    window.publish_spill('batch_merge_commit', 4.0, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['label'] == 'batch_merge_commit'
    assert stored['armed_until'] == pytest.approx(WALL0 + 4.0)
    assert stored['window_seconds'] == pytest.approx(4.0)


def test_stamp_batch_provider_stt_w0p125():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    window.publish_spill('batch_provider_stt', 0.125, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['label'] == 'batch_provider_stt'
    assert stored['armed_until'] == pytest.approx(WALL0 + 0.125)
    assert stored['window_seconds'] == pytest.approx(0.125)


def test_stamp_batch_provider_stt_w1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    window.publish_spill('batch_provider_stt', 1.0, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['label'] == 'batch_provider_stt'
    assert stored['armed_until'] == pytest.approx(WALL0 + 1.0)
    assert stored['window_seconds'] == pytest.approx(1.0)


def test_stamp_batch_provider_stt_w4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    window.publish_spill('batch_provider_stt', 4.0, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['label'] == 'batch_provider_stt'
    assert stored['armed_until'] == pytest.approx(WALL0 + 4.0)
    assert stored['window_seconds'] == pytest.approx(4.0)


def test_stamp_batch_intake_status_w0p125():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    window.publish_spill('batch_intake_status', 0.125, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['label'] == 'batch_intake_status'
    assert stored['armed_until'] == pytest.approx(WALL0 + 0.125)
    assert stored['window_seconds'] == pytest.approx(0.125)


def test_stamp_batch_intake_status_w1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    window.publish_spill('batch_intake_status', 1.0, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['label'] == 'batch_intake_status'
    assert stored['armed_until'] == pytest.approx(WALL0 + 1.0)
    assert stored['window_seconds'] == pytest.approx(1.0)


def test_stamp_batch_intake_status_w4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    window.publish_spill('batch_intake_status', 4.0, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['label'] == 'batch_intake_status'
    assert stored['armed_until'] == pytest.approx(WALL0 + 4.0)
    assert stored['window_seconds'] == pytest.approx(4.0)


def test_stamp_batch_recover_items_w0p125():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    window.publish_spill('batch_recover_items', 0.125, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['label'] == 'batch_recover_items'
    assert stored['armed_until'] == pytest.approx(WALL0 + 0.125)
    assert stored['window_seconds'] == pytest.approx(0.125)


def test_stamp_batch_recover_items_w1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    window.publish_spill('batch_recover_items', 1.0, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['label'] == 'batch_recover_items'
    assert stored['armed_until'] == pytest.approx(WALL0 + 1.0)
    assert stored['window_seconds'] == pytest.approx(1.0)


def test_stamp_batch_recover_items_w4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    window.publish_spill('batch_recover_items', 4.0, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['label'] == 'batch_recover_items'
    assert stored['armed_until'] == pytest.approx(WALL0 + 4.0)
    assert stored['window_seconds'] == pytest.approx(4.0)


def test_stamp_batch_complete_w0p125():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    window.publish_spill('batch_complete', 0.125, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['label'] == 'batch_complete'
    assert stored['armed_until'] == pytest.approx(WALL0 + 0.125)
    assert stored['window_seconds'] == pytest.approx(0.125)


def test_stamp_batch_complete_w1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    window.publish_spill('batch_complete', 1.0, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['label'] == 'batch_complete'
    assert stored['armed_until'] == pytest.approx(WALL0 + 1.0)
    assert stored['window_seconds'] == pytest.approx(1.0)


def test_stamp_batch_complete_w4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    window.publish_spill('batch_complete', 4.0, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['label'] == 'batch_complete'
    assert stored['armed_until'] == pytest.approx(WALL0 + 4.0)
    assert stored['window_seconds'] == pytest.approx(4.0)


def test_stamp_batch_pull_shard_scheduler_00_w0p125():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    window.publish_spill('batch_pull_shard_scheduler_00', 0.125, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['label'] == 'batch_pull_shard_scheduler_00'
    assert stored['armed_until'] == pytest.approx(WALL0 + 0.125)
    assert stored['window_seconds'] == pytest.approx(0.125)


def test_stamp_batch_pull_shard_scheduler_00_w1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    window.publish_spill('batch_pull_shard_scheduler_00', 1.0, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['label'] == 'batch_pull_shard_scheduler_00'
    assert stored['armed_until'] == pytest.approx(WALL0 + 1.0)
    assert stored['window_seconds'] == pytest.approx(1.0)


def test_stamp_batch_pull_shard_scheduler_00_w4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    window.publish_spill('batch_pull_shard_scheduler_00', 4.0, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['label'] == 'batch_pull_shard_scheduler_00'
    assert stored['armed_until'] == pytest.approx(WALL0 + 4.0)
    assert stored['window_seconds'] == pytest.approx(4.0)


def test_stamp_batch_claim_shard_scheduler_03_w0p125():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    window.publish_spill('batch_claim_shard_scheduler_03', 0.125, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['label'] == 'batch_claim_shard_scheduler_03'
    assert stored['armed_until'] == pytest.approx(WALL0 + 0.125)
    assert stored['window_seconds'] == pytest.approx(0.125)


def test_stamp_batch_claim_shard_scheduler_03_w1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    window.publish_spill('batch_claim_shard_scheduler_03', 1.0, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['label'] == 'batch_claim_shard_scheduler_03'
    assert stored['armed_until'] == pytest.approx(WALL0 + 1.0)
    assert stored['window_seconds'] == pytest.approx(1.0)


def test_stamp_batch_claim_shard_scheduler_03_w4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    window.publish_spill('batch_claim_shard_scheduler_03', 4.0, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['label'] == 'batch_claim_shard_scheduler_03'
    assert stored['armed_until'] == pytest.approx(WALL0 + 4.0)
    assert stored['window_seconds'] == pytest.approx(4.0)


def test_readfault_true_peek():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)] = {'armed_until': True}
    assert window.peek_spill(client) == 0.0
    assert window.spill_malformed_reads == 1


def test_readfault_true_publish():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)] = {'armed_until': True}
    window.publish_spill('batch_admit', 1.0, client=client)
    # the fetch failed open as no spill, so the arm writes its window
    assert window.spill_malformed_reads == 1
    stored = client.docs.get((spill_collection('batch_pipeline_dev'), SPILL_DOC))
    assert stored is not None and stored['armed_until'] == pytest.approx(WALL0 + 1.0)


def test_readfault_false_peek():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)] = {'armed_until': False}
    assert window.peek_spill(client) == 0.0
    assert window.spill_malformed_reads == 1


def test_readfault_false_publish():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)] = {'armed_until': False}
    window.publish_spill('batch_admit', 1.0, client=client)
    # the fetch failed open as no spill, so the arm writes its window
    assert window.spill_malformed_reads == 1
    stored = client.docs.get((spill_collection('batch_pipeline_dev'), SPILL_DOC))
    assert stored is not None and stored['armed_until'] == pytest.approx(WALL0 + 1.0)


def test_readfault_soon_peek():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)] = {'armed_until': 'soon'}
    assert window.peek_spill(client) == 0.0
    assert window.spill_malformed_reads == 1


def test_readfault_soon_publish():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)] = {'armed_until': 'soon'}
    window.publish_spill('batch_admit', 1.0, client=client)
    # the fetch failed open as no spill, so the arm writes its window
    assert window.spill_malformed_reads == 1
    stored = client.docs.get((spill_collection('batch_pipeline_dev'), SPILL_DOC))
    assert stored is not None and stored['armed_until'] == pytest.approx(WALL0 + 1.0)


def test_readfault_none_peek():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)] = {'armed_until': None}
    assert window.peek_spill(client) == 0.0
    assert window.spill_malformed_reads == 1


def test_readfault_none_publish():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)] = {'armed_until': None}
    window.publish_spill('batch_admit', 1.0, client=client)
    # the fetch failed open as no spill, so the arm writes its window
    assert window.spill_malformed_reads == 1
    stored = client.docs.get((spill_collection('batch_pipeline_dev'), SPILL_DOC))
    assert stored is not None and stored['armed_until'] == pytest.approx(WALL0 + 1.0)


def test_readfault_1_peek():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)] = {'armed_until': [1]}
    assert window.peek_spill(client) == 0.0
    assert window.spill_malformed_reads == 1


def test_readfault_1_publish():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)] = {'armed_until': [1]}
    window.publish_spill('batch_admit', 1.0, client=client)
    # the fetch failed open as no spill, so the arm writes its window
    assert window.spill_malformed_reads == 1
    stored = client.docs.get((spill_collection('batch_pipeline_dev'), SPILL_DOC))
    assert stored is not None and stored['armed_until'] == pytest.approx(WALL0 + 1.0)


def test_readfault_dict_peek():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)] = {'armed_until': {}}
    assert window.peek_spill(client) == 0.0
    assert window.spill_malformed_reads == 1


def test_readfault_dict_publish():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)] = {'armed_until': {}}
    window.publish_spill('batch_admit', 1.0, client=client)
    # the fetch failed open as no spill, so the arm writes its window
    assert window.spill_malformed_reads == 1
    stored = client.docs.get((spill_collection('batch_pipeline_dev'), SPILL_DOC))
    assert stored is not None and stored['armed_until'] == pytest.approx(WALL0 + 1.0)


def test_readfault_nan_peek():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)] = {'armed_until': float('nan')}
    assert window.peek_spill(client) == 0.0
    assert window.spill_malformed_reads == 1


def test_readfault_nan_publish():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)] = {'armed_until': float('nan')}
    window.publish_spill('batch_admit', 1.0, client=client)
    # the fetch failed open as no spill, so the arm writes its window
    assert window.spill_malformed_reads == 1
    stored = client.docs.get((spill_collection('batch_pipeline_dev'), SPILL_DOC))
    assert stored is not None and stored['armed_until'] == pytest.approx(WALL0 + 1.0)


def test_readfault_inf_peek():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)] = {'armed_until': float('inf')}
    assert window.peek_spill(client) == 0.0
    assert window.spill_malformed_reads == 1


def test_readfault_inf_publish():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)] = {'armed_until': float('inf')}
    window.publish_spill('batch_admit', 1.0, client=client)
    # the fetch failed open as no spill, so the arm writes its window
    assert window.spill_malformed_reads == 1
    stored = client.docs.get((spill_collection('batch_pipeline_dev'), SPILL_DOC))
    assert stored is not None and stored['armed_until'] == pytest.approx(WALL0 + 1.0)


def test_readfault_minf_peek():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)] = {'armed_until': -float('inf')}
    assert window.peek_spill(client) == 0.0
    assert window.spill_malformed_reads == 1


def test_readfault_minf_publish():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)] = {'armed_until': -float('inf')}
    window.publish_spill('batch_admit', 1.0, client=client)
    # the fetch failed open as no spill, so the arm writes its window
    assert window.spill_malformed_reads == 1
    stored = client.docs.get((spill_collection('batch_pipeline_dev'), SPILL_DOC))
    assert stored is not None and stored['armed_until'] == pytest.approx(WALL0 + 1.0)


def test_writefault_f1_dabsent():
    client = StormDocsClient()
    client.fail_sets = 1
    window, wall = fresh_window('batch_pipeline_dev')
    window.publish_spill('batch_admit', 2.0, client=client)
    assert window.spill_publish_failures >= 1
    assert window.spill_publishes == 0


def test_writefault_f1_d0p5():
    client = StormDocsClient()
    client.fail_sets = 1
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.5)
    window.publish_spill('batch_admit', 2.0, client=client)
    assert window.spill_publish_failures >= 1
    assert window.spill_publishes == 0


def test_writefault_f3_dabsent():
    client = StormDocsClient()
    client.fail_sets = 3
    window, wall = fresh_window('batch_pipeline_dev')
    window.publish_spill('batch_admit', 2.0, client=client)
    assert window.spill_publish_failures >= 1
    assert window.spill_publishes == 0


def test_writefault_f3_d0p5():
    client = StormDocsClient()
    client.fail_sets = 3
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.5)
    window.publish_spill('batch_admit', 2.0, client=client)
    assert window.spill_publish_failures >= 1
    assert window.spill_publishes == 0


def test_ttl_o0_r0p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.5)
    assert window.peek_spill(client) == pytest.approx(0.5)
    wall.advance(0.0)
    assert window.peek_spill(client) == pytest.approx(0.5)
    assert window.spill_reads == 1


def test_ttl_o0_r1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 1.0)
    assert window.peek_spill(client) == pytest.approx(1.0)
    wall.advance(0.0)
    assert window.peek_spill(client) == pytest.approx(1.0)
    assert window.spill_reads == 1


def test_ttl_o0_r2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 2.0)
    assert window.peek_spill(client) == pytest.approx(2.0)
    wall.advance(0.0)
    assert window.peek_spill(client) == pytest.approx(2.0)
    assert window.spill_reads == 1


def test_ttl_o0_r4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    assert window.peek_spill(client) == pytest.approx(4.0)
    wall.advance(0.0)
    assert window.peek_spill(client) == pytest.approx(4.0)
    assert window.spill_reads == 1


def test_ttl_o0p25_r0p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.5)
    assert window.peek_spill(client) == pytest.approx(0.5)
    wall.advance(0.25)
    assert window.peek_spill(client) == pytest.approx(0.25)
    assert window.spill_reads == 1


def test_ttl_o0p25_r1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 1.0)
    assert window.peek_spill(client) == pytest.approx(1.0)
    wall.advance(0.25)
    assert window.peek_spill(client) == pytest.approx(0.75)
    assert window.spill_reads == 1


def test_ttl_o0p25_r2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 2.0)
    assert window.peek_spill(client) == pytest.approx(2.0)
    wall.advance(0.25)
    assert window.peek_spill(client) == pytest.approx(1.75)
    assert window.spill_reads == 1


def test_ttl_o0p25_r4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    assert window.peek_spill(client) == pytest.approx(4.0)
    wall.advance(0.25)
    assert window.peek_spill(client) == pytest.approx(3.75)
    assert window.spill_reads == 1


def test_ttl_o0p5_r0p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.5)
    assert window.peek_spill(client) == pytest.approx(0.5)
    wall.advance(0.5)
    assert window.peek_spill(client) == pytest.approx(0.0)
    assert window.spill_reads == 1


def test_ttl_o0p5_r1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 1.0)
    assert window.peek_spill(client) == pytest.approx(1.0)
    wall.advance(0.5)
    assert window.peek_spill(client) == pytest.approx(0.5)
    assert window.spill_reads == 1


def test_ttl_o0p5_r2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 2.0)
    assert window.peek_spill(client) == pytest.approx(2.0)
    wall.advance(0.5)
    assert window.peek_spill(client) == pytest.approx(1.5)
    assert window.spill_reads == 1


def test_ttl_o0p5_r4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    assert window.peek_spill(client) == pytest.approx(4.0)
    wall.advance(0.5)
    assert window.peek_spill(client) == pytest.approx(3.5)
    assert window.spill_reads == 1


def test_ttl_o0p75_r0p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.5)
    assert window.peek_spill(client) == pytest.approx(0.5)
    wall.advance(0.75)
    assert window.peek_spill(client) == pytest.approx(0.0)
    assert window.spill_reads == 1


def test_ttl_o0p75_r1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 1.0)
    assert window.peek_spill(client) == pytest.approx(1.0)
    wall.advance(0.75)
    assert window.peek_spill(client) == pytest.approx(0.25)
    assert window.spill_reads == 1


def test_ttl_o0p75_r2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 2.0)
    assert window.peek_spill(client) == pytest.approx(2.0)
    wall.advance(0.75)
    assert window.peek_spill(client) == pytest.approx(1.25)
    assert window.spill_reads == 1


def test_ttl_o0p75_r4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    assert window.peek_spill(client) == pytest.approx(4.0)
    wall.advance(0.75)
    assert window.peek_spill(client) == pytest.approx(3.25)
    assert window.spill_reads == 1


def test_ttl_o0p99_r0p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.5)
    assert window.peek_spill(client) == pytest.approx(0.5)
    wall.advance(0.99)
    assert window.peek_spill(client) == pytest.approx(0.0)
    assert window.spill_reads == 1


def test_ttl_o0p99_r1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 1.0)
    assert window.peek_spill(client) == pytest.approx(1.0)
    wall.advance(0.99)
    assert window.peek_spill(client) == pytest.approx(0.010000000000000009)
    assert window.spill_reads == 1


def test_ttl_o0p99_r2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 2.0)
    assert window.peek_spill(client) == pytest.approx(2.0)
    wall.advance(0.99)
    assert window.peek_spill(client) == pytest.approx(1.01)
    assert window.spill_reads == 1


def test_ttl_o0p99_r4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    assert window.peek_spill(client) == pytest.approx(4.0)
    wall.advance(0.99)
    assert window.peek_spill(client) == pytest.approx(3.01)
    assert window.spill_reads == 1


def test_ttl_o1_r0p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.5)
    assert window.peek_spill(client) == pytest.approx(0.5)
    wall.advance(1.0)
    assert window.peek_spill(client) == pytest.approx(0.0)
    assert window.spill_reads == 2


def test_ttl_o1_r1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 1.0)
    assert window.peek_spill(client) == pytest.approx(1.0)
    wall.advance(1.0)
    assert window.peek_spill(client) == pytest.approx(0.0)
    assert window.spill_reads == 2


def test_ttl_o1_r2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 2.0)
    assert window.peek_spill(client) == pytest.approx(2.0)
    wall.advance(1.0)
    assert window.peek_spill(client) == pytest.approx(1.0)
    assert window.spill_reads == 2


def test_ttl_o1_r4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    assert window.peek_spill(client) == pytest.approx(4.0)
    wall.advance(1.0)
    assert window.peek_spill(client) == pytest.approx(3.0)
    assert window.spill_reads == 2


def test_ttl_o1p01_r0p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.5)
    assert window.peek_spill(client) == pytest.approx(0.5)
    wall.advance(1.01)
    assert window.peek_spill(client) == pytest.approx(0.0)
    assert window.spill_reads == 2


def test_ttl_o1p01_r1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 1.0)
    assert window.peek_spill(client) == pytest.approx(1.0)
    wall.advance(1.01)
    assert window.peek_spill(client) == pytest.approx(0.0)
    assert window.spill_reads == 2


def test_ttl_o1p01_r2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 2.0)
    assert window.peek_spill(client) == pytest.approx(2.0)
    wall.advance(1.01)
    assert window.peek_spill(client) == pytest.approx(0.99)
    assert window.spill_reads == 2


def test_ttl_o1p01_r4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    assert window.peek_spill(client) == pytest.approx(4.0)
    wall.advance(1.01)
    assert window.peek_spill(client) == pytest.approx(2.99)
    assert window.spill_reads == 2


def test_ttl_o1p5_r0p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.5)
    assert window.peek_spill(client) == pytest.approx(0.5)
    wall.advance(1.5)
    assert window.peek_spill(client) == pytest.approx(0.0)
    assert window.spill_reads == 2


def test_ttl_o1p5_r1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 1.0)
    assert window.peek_spill(client) == pytest.approx(1.0)
    wall.advance(1.5)
    assert window.peek_spill(client) == pytest.approx(0.0)
    assert window.spill_reads == 2


def test_ttl_o1p5_r2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 2.0)
    assert window.peek_spill(client) == pytest.approx(2.0)
    wall.advance(1.5)
    assert window.peek_spill(client) == pytest.approx(0.5)
    assert window.spill_reads == 2


def test_ttl_o1p5_r4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    assert window.peek_spill(client) == pytest.approx(4.0)
    wall.advance(1.5)
    assert window.peek_spill(client) == pytest.approx(2.5)
    assert window.spill_reads == 2


def test_ttl_o2_r0p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.5)
    assert window.peek_spill(client) == pytest.approx(0.5)
    wall.advance(2.0)
    assert window.peek_spill(client) == pytest.approx(0.0)
    assert window.spill_reads == 2


def test_ttl_o2_r1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 1.0)
    assert window.peek_spill(client) == pytest.approx(1.0)
    wall.advance(2.0)
    assert window.peek_spill(client) == pytest.approx(0.0)
    assert window.spill_reads == 2


def test_ttl_o2_r2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 2.0)
    assert window.peek_spill(client) == pytest.approx(2.0)
    wall.advance(2.0)
    assert window.peek_spill(client) == pytest.approx(0.0)
    assert window.spill_reads == 2


def test_ttl_o2_r4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    assert window.peek_spill(client) == pytest.approx(4.0)
    wall.advance(2.0)
    assert window.peek_spill(client) == pytest.approx(2.0)
    assert window.spill_reads == 2


def test_ttl_o3_r0p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.5)
    assert window.peek_spill(client) == pytest.approx(0.5)
    wall.advance(3.0)
    assert window.peek_spill(client) == pytest.approx(0.0)
    assert window.spill_reads == 2


def test_ttl_o3_r1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 1.0)
    assert window.peek_spill(client) == pytest.approx(1.0)
    wall.advance(3.0)
    assert window.peek_spill(client) == pytest.approx(0.0)
    assert window.spill_reads == 2


def test_ttl_o3_r2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 2.0)
    assert window.peek_spill(client) == pytest.approx(2.0)
    wall.advance(3.0)
    assert window.peek_spill(client) == pytest.approx(0.0)
    assert window.spill_reads == 2


def test_ttl_o3_r4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    assert window.peek_spill(client) == pytest.approx(4.0)
    wall.advance(3.0)
    assert window.peek_spill(client) == pytest.approx(1.0)
    assert window.spill_reads == 2


def test_decay_a0p125_r1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 1.0)
    assert window.peek_spill(client) == pytest.approx(1.0)
    wall.advance(0.125)  # the cached until decays against the moved wall
    assert window.peek_spill(client) == pytest.approx(0.875)
    assert window.spill_reads == 1


def test_decay_a0p125_r2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 2.0)
    assert window.peek_spill(client) == pytest.approx(2.0)
    wall.advance(0.125)  # the cached until decays against the moved wall
    assert window.peek_spill(client) == pytest.approx(1.875)
    assert window.spill_reads == 1


def test_decay_a0p125_r4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    assert window.peek_spill(client) == pytest.approx(4.0)
    wall.advance(0.125)  # the cached until decays against the moved wall
    assert window.peek_spill(client) == pytest.approx(3.875)
    assert window.spill_reads == 1


def test_decay_a0p25_r1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 1.0)
    assert window.peek_spill(client) == pytest.approx(1.0)
    wall.advance(0.25)  # the cached until decays against the moved wall
    assert window.peek_spill(client) == pytest.approx(0.75)
    assert window.spill_reads == 1


def test_decay_a0p25_r2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 2.0)
    assert window.peek_spill(client) == pytest.approx(2.0)
    wall.advance(0.25)  # the cached until decays against the moved wall
    assert window.peek_spill(client) == pytest.approx(1.75)
    assert window.spill_reads == 1


def test_decay_a0p25_r4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    assert window.peek_spill(client) == pytest.approx(4.0)
    wall.advance(0.25)  # the cached until decays against the moved wall
    assert window.peek_spill(client) == pytest.approx(3.75)
    assert window.spill_reads == 1


def test_decay_a0p5_r1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 1.0)
    assert window.peek_spill(client) == pytest.approx(1.0)
    wall.advance(0.5)  # the cached until decays against the moved wall
    assert window.peek_spill(client) == pytest.approx(0.5)
    assert window.spill_reads == 1


def test_decay_a0p5_r2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 2.0)
    assert window.peek_spill(client) == pytest.approx(2.0)
    wall.advance(0.5)  # the cached until decays against the moved wall
    assert window.peek_spill(client) == pytest.approx(1.5)
    assert window.spill_reads == 1


def test_decay_a0p5_r4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    assert window.peek_spill(client) == pytest.approx(4.0)
    wall.advance(0.5)  # the cached until decays against the moved wall
    assert window.peek_spill(client) == pytest.approx(3.5)
    assert window.spill_reads == 1


def test_decay_a0p75_r1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 1.0)
    assert window.peek_spill(client) == pytest.approx(1.0)
    wall.advance(0.75)  # the cached until decays against the moved wall
    assert window.peek_spill(client) == pytest.approx(0.25)
    assert window.spill_reads == 1


def test_decay_a0p75_r2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 2.0)
    assert window.peek_spill(client) == pytest.approx(2.0)
    wall.advance(0.75)  # the cached until decays against the moved wall
    assert window.peek_spill(client) == pytest.approx(1.25)
    assert window.spill_reads == 1


def test_decay_a0p75_r4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    assert window.peek_spill(client) == pytest.approx(4.0)
    wall.advance(0.75)  # the cached until decays against the moved wall
    assert window.peek_spill(client) == pytest.approx(3.25)
    assert window.spill_reads == 1


def test_decay_a1p25_r1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 1.0)
    assert window.peek_spill(client) == pytest.approx(1.0)
    wall.advance(1.25)  # the cached until decays against the moved wall
    assert window.peek_spill(client) == pytest.approx(0.0)
    assert window.spill_reads == 2


def test_decay_a1p25_r2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 2.0)
    assert window.peek_spill(client) == pytest.approx(2.0)
    wall.advance(1.25)  # the cached until decays against the moved wall
    assert window.peek_spill(client) == pytest.approx(0.75)
    assert window.spill_reads == 2


def test_decay_a1p25_r4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    assert window.peek_spill(client) == pytest.approx(4.0)
    wall.advance(1.25)  # the cached until decays against the moved wall
    assert window.peek_spill(client) == pytest.approx(2.75)
    assert window.spill_reads == 2


def test_hostile_res_0():
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet = Mock()
    damper._fleet.peek.return_value = 0.0
    damper._fleet.peek_spill.return_value = None
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 1.0
    waited, generation = damper.consult('batch_claim', client=Mock())
    assert waited == 0.0
    assert clock.sleeps == []
    assert generation == 0


def test_hostile_res_1():
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet = Mock()
    damper._fleet.peek.return_value = 0.0
    damper._fleet.peek_spill.return_value = True
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 1.0
    waited, generation = damper.consult('batch_claim', client=Mock())
    assert waited == 0.0
    assert clock.sleeps == []
    assert generation == 0


def test_hostile_res_2():
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet = Mock()
    damper._fleet.peek.return_value = 0.0
    damper._fleet.peek_spill.return_value = 'x'
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 1.0
    waited, generation = damper.consult('batch_claim', client=Mock())
    assert waited == 0.0
    assert clock.sleeps == []
    assert generation == 0


def test_hostile_res_3():
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet = Mock()
    damper._fleet.peek.return_value = 0.0
    damper._fleet.peek_spill.return_value = object()
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 1.0
    waited, generation = damper.consult('batch_claim', client=Mock())
    assert waited == 0.0
    assert clock.sleeps == []
    assert generation == 0


def test_hostile_res_4():
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet = Mock()
    damper._fleet.peek.return_value = 0.0
    damper._fleet.peek_spill.return_value = -1.0
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 1.0
    waited, generation = damper.consult('batch_claim', client=Mock())
    assert waited == 0.0
    assert clock.sleeps == []
    assert generation == 0


def test_hostile_res_5():
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet = Mock()
    damper._fleet.peek.return_value = 0.0
    damper._fleet.peek_spill.return_value = 0.0
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 1.0
    waited, generation = damper.consult('batch_claim', client=Mock())
    assert waited == 0.0
    assert clock.sleeps == []
    assert generation == 0


def test_hostile_res_6():
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet = Mock()
    damper._fleet.peek.return_value = 0.0
    damper._fleet.peek_spill.return_value = float('nan')
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 1.0
    waited, generation = damper.consult('batch_claim', client=Mock())
    assert waited == 0.0
    assert clock.sleeps == []
    assert generation == 0


def test_hostile_res_7():
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet = Mock()
    damper._fleet.peek.return_value = 0.0
    damper._fleet.peek_spill.return_value = float('inf')
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 1.0
    waited, generation = damper.consult('batch_claim', client=Mock())
    assert waited == 0.0
    assert clock.sleeps == []
    assert generation == 0


def test_hostile_res_8():
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet = Mock()
    damper._fleet.peek.return_value = 0.0
    damper._fleet.peek_spill.return_value = -float('inf')
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 1.0
    waited, generation = damper.consult('batch_claim', client=Mock())
    assert waited == 0.0
    assert clock.sleeps == []
    assert generation == 0


def test_hostile_res_9():
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet = Mock()
    damper._fleet.peek.return_value = 0.0
    damper._fleet.peek_spill.return_value = []
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 1.0
    waited, generation = damper.consult('batch_claim', client=Mock())
    assert waited == 0.0
    assert clock.sleeps == []
    assert generation == 0


def test_hostile_cap_0():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 1.0)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet = Mock()
    damper._fleet.peek.return_value = 0.0
    damper._fleet.peek_spill.return_value = 1.0
    damper._fleet.SPILL_SHARE_CAP_SECONDS = None
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == 0.0
    assert clock.sleeps == []


def test_hostile_cap_1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 1.0)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet = Mock()
    damper._fleet.peek.return_value = 0.0
    damper._fleet.peek_spill.return_value = 1.0
    damper._fleet.SPILL_SHARE_CAP_SECONDS = True
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == 0.0
    assert clock.sleeps == []


def test_hostile_cap_2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 1.0)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet = Mock()
    damper._fleet.peek.return_value = 0.0
    damper._fleet.peek_spill.return_value = 1.0
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 'x'
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == 0.0
    assert clock.sleeps == []


def test_hostile_cap_3():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 1.0)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet = Mock()
    damper._fleet.peek.return_value = 0.0
    damper._fleet.peek_spill.return_value = 1.0
    damper._fleet.SPILL_SHARE_CAP_SECONDS = object()
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == 0.0
    assert clock.sleeps == []


def test_hostile_cap_4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 1.0)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet = Mock()
    damper._fleet.peek.return_value = 0.0
    damper._fleet.peek_spill.return_value = 1.0
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 0.0
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == 0.0
    assert clock.sleeps == []


def test_hostile_cap_5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 1.0)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet = Mock()
    damper._fleet.peek.return_value = 0.0
    damper._fleet.peek_spill.return_value = 1.0
    damper._fleet.SPILL_SHARE_CAP_SECONDS = -1.0
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == 0.0
    assert clock.sleeps == []


def test_hostile_cap_6():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 1.0)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet = Mock()
    damper._fleet.peek.return_value = 0.0
    damper._fleet.peek_spill.return_value = 1.0
    damper._fleet.SPILL_SHARE_CAP_SECONDS = float('nan')
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == 0.0
    assert clock.sleeps == []


def test_hostile_cap_7():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 1.0)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet = Mock()
    damper._fleet.peek.return_value = 0.0
    damper._fleet.peek_spill.return_value = 1.0
    damper._fleet.SPILL_SHARE_CAP_SECONDS = float('inf')
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == 0.0
    assert clock.sleeps == []


def test_unfit_publish_label_0():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    window.publish_spill('BAD LABEL!', 1.0, client=client)
    assert window.spill_unfit_labels == 1
    assert client.set_calls == []
    assert window.spill_publishes == 0


def test_unfit_publish_label_1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    window.publish_spill('', 1.0, client=client)
    assert window.spill_unfit_labels == 1
    assert client.set_calls == []
    assert window.spill_publishes == 0


def test_unfit_publish_label_2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    window.publish_spill('UPPER_CASE', 1.0, client=client)
    assert window.spill_unfit_labels == 1
    assert client.set_calls == []
    assert window.spill_publishes == 0


def test_unfit_publish_label_3():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    window.publish_spill('dot.name', 1.0, client=client)
    assert window.spill_unfit_labels == 1
    assert client.set_calls == []
    assert window.spill_publishes == 0


def test_unfit_publish_label_4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    window.publish_spill('dash-name', 1.0, client=client)
    assert window.spill_unfit_labels == 1
    assert client.set_calls == []
    assert window.spill_publishes == 0


def test_unfit_publish_label_5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    window.publish_spill(
        '''aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa''',
        1.0,
        client=client,
    )
    assert window.spill_unfit_labels == 1
    assert client.set_calls == []
    assert window.spill_publishes == 0


def test_ns_isolation_0():
    client = StormDocsClient()
    window_a, _wall_a = fresh_window('batch_pipeline_dev')
    window_b, _wall_b = fresh_window('batch_pipeline_prod')
    window_a.publish_spill('batch_admit', 2.0, client=client)
    assert (spill_collection('batch_pipeline_prod'), SPILL_DOC) not in client.docs
    assert window_b.peek_spill(client) == 0.0
    assert window_b.spill_reads == 1


def test_ns_isolation_1():
    client = StormDocsClient()
    window_a, _wall_a = fresh_window('batch_pipeline_prod')
    window_b, _wall_b = fresh_window('batch_pipeline_dev')
    window_a.publish_spill('batch_admit', 2.0, client=client)
    assert (spill_collection('batch_pipeline_dev'), SPILL_DOC) not in client.docs
    assert window_b.peek_spill(client) == 0.0
    assert window_b.spill_reads == 1


def test_ns_isolation_2():
    client = StormDocsClient()
    window_a, _wall_a = fresh_window('batch_pipeline_dev')
    window_b, _wall_b = fresh_window('batch_pipeline_prod')
    window_a.publish_spill('batch_admit', 2.0, client=client)
    assert (spill_collection('batch_pipeline_prod'), SPILL_DOC) not in client.docs
    assert window_b.peek_spill(client) == 0.0
    assert window_b.spill_reads == 1


def test_ns_isolation_3():
    client = StormDocsClient()
    window_a, _wall_a = fresh_window('batch_pipeline_prod')
    window_b, _wall_b = fresh_window('batch_pipeline_dev')
    window_a.publish_spill('batch_admit', 2.0, client=client)
    assert (spill_collection('batch_pipeline_dev'), SPILL_DOC) not in client.docs
    assert window_b.peek_spill(client) == 0.0
    assert window_b.spill_reads == 1


def test_ns_isolation_4():
    client = StormDocsClient()
    window_a, _wall_a = fresh_window('batch_pipeline_dev')
    window_b, _wall_b = fresh_window('batch_pipeline_prod')
    window_a.publish_spill('batch_admit', 2.0, client=client)
    assert (spill_collection('batch_pipeline_prod'), SPILL_DOC) not in client.docs
    assert window_b.peek_spill(client) == 0.0
    assert window_b.spill_reads == 1


def test_ns_isolation_5():
    client = StormDocsClient()
    window_a, _wall_a = fresh_window('batch_pipeline_prod')
    window_b, _wall_b = fresh_window('batch_pipeline_dev')
    window_a.publish_spill('batch_admit', 2.0, client=client)
    assert (spill_collection('batch_pipeline_dev'), SPILL_DOC) not in client.docs
    assert window_b.peek_spill(client) == 0.0
    assert window_b.spill_reads == 1


def test_ns_isolation_6():
    client = StormDocsClient()
    window_a, _wall_a = fresh_window('batch_pipeline_dev')
    window_b, _wall_b = fresh_window('batch_pipeline_prod')
    window_a.publish_spill('batch_admit', 2.0, client=client)
    assert (spill_collection('batch_pipeline_prod'), SPILL_DOC) not in client.docs
    assert window_b.peek_spill(client) == 0.0
    assert window_b.spill_reads == 1


def test_ns_isolation_7():
    client = StormDocsClient()
    window_a, _wall_a = fresh_window('batch_pipeline_prod')
    window_b, _wall_b = fresh_window('batch_pipeline_dev')
    window_a.publish_spill('batch_admit', 2.0, client=client)
    assert (spill_collection('batch_pipeline_dev'), SPILL_DOC) not in client.docs
    assert window_b.peek_spill(client) == 0.0
    assert window_b.spill_reads == 1


def test_skew_sm2_r0p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev', wall_now=WALL0 + -2.0)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.5)
    assert window.peek_spill(client) == pytest.approx(2.5)


def test_skew_sm2_r1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev', wall_now=WALL0 + -2.0)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 1.0)
    assert window.peek_spill(client) == pytest.approx(3.0)


def test_skew_sm2_r2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev', wall_now=WALL0 + -2.0)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 2.0)
    assert window.peek_spill(client) == pytest.approx(4.0)


def test_skew_sm2_r4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev', wall_now=WALL0 + -2.0)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    assert window.peek_spill(client) == pytest.approx(6.0)


def test_skew_sm1_r0p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev', wall_now=WALL0 + -1.0)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.5)
    assert window.peek_spill(client) == pytest.approx(1.5)


def test_skew_sm1_r1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev', wall_now=WALL0 + -1.0)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 1.0)
    assert window.peek_spill(client) == pytest.approx(2.0)


def test_skew_sm1_r2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev', wall_now=WALL0 + -1.0)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 2.0)
    assert window.peek_spill(client) == pytest.approx(3.0)


def test_skew_sm1_r4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev', wall_now=WALL0 + -1.0)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    assert window.peek_spill(client) == pytest.approx(5.0)


def test_skew_sm0p5_r0p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev', wall_now=WALL0 + -0.5)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.5)
    assert window.peek_spill(client) == pytest.approx(1.0)


def test_skew_sm0p5_r1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev', wall_now=WALL0 + -0.5)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 1.0)
    assert window.peek_spill(client) == pytest.approx(1.5)


def test_skew_sm0p5_r2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev', wall_now=WALL0 + -0.5)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 2.0)
    assert window.peek_spill(client) == pytest.approx(2.5)


def test_skew_sm0p5_r4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev', wall_now=WALL0 + -0.5)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    assert window.peek_spill(client) == pytest.approx(4.5)


def test_skew_s0_r0p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev', wall_now=WALL0 + 0.0)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.5)
    assert window.peek_spill(client) == pytest.approx(0.5)


def test_skew_s0_r1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev', wall_now=WALL0 + 0.0)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 1.0)
    assert window.peek_spill(client) == pytest.approx(1.0)


def test_skew_s0_r2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev', wall_now=WALL0 + 0.0)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 2.0)
    assert window.peek_spill(client) == pytest.approx(2.0)


def test_skew_s0_r4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev', wall_now=WALL0 + 0.0)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    assert window.peek_spill(client) == pytest.approx(4.0)


def test_skew_s0p5_r0p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev', wall_now=WALL0 + 0.5)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.5)
    assert window.peek_spill(client) == pytest.approx(0.0)


def test_skew_s0p5_r1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev', wall_now=WALL0 + 0.5)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 1.0)
    assert window.peek_spill(client) == pytest.approx(0.5)


def test_skew_s0p5_r2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev', wall_now=WALL0 + 0.5)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 2.0)
    assert window.peek_spill(client) == pytest.approx(1.5)


def test_skew_s0p5_r4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev', wall_now=WALL0 + 0.5)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    assert window.peek_spill(client) == pytest.approx(3.5)


def test_skew_s1_r0p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev', wall_now=WALL0 + 1.0)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.5)
    assert window.peek_spill(client) == pytest.approx(0.0)


def test_skew_s1_r1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev', wall_now=WALL0 + 1.0)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 1.0)
    assert window.peek_spill(client) == pytest.approx(0.0)


def test_skew_s1_r2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev', wall_now=WALL0 + 1.0)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 2.0)
    assert window.peek_spill(client) == pytest.approx(1.0)


def test_skew_s1_r4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev', wall_now=WALL0 + 1.0)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    assert window.peek_spill(client) == pytest.approx(3.0)


def test_skew_s2_r0p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev', wall_now=WALL0 + 2.0)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.5)
    assert window.peek_spill(client) == pytest.approx(0.0)


def test_skew_s2_r1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev', wall_now=WALL0 + 2.0)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 1.0)
    assert window.peek_spill(client) == pytest.approx(0.0)


def test_skew_s2_r2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev', wall_now=WALL0 + 2.0)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 2.0)
    assert window.peek_spill(client) == pytest.approx(0.0)


def test_skew_s2_r4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev', wall_now=WALL0 + 2.0)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    assert window.peek_spill(client) == pytest.approx(2.0)


def test_skew_s4_r0p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev', wall_now=WALL0 + 4.0)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.5)
    assert window.peek_spill(client) == pytest.approx(0.0)


def test_skew_s4_r1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev', wall_now=WALL0 + 4.0)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 1.0)
    assert window.peek_spill(client) == pytest.approx(0.0)


def test_skew_s4_r2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev', wall_now=WALL0 + 4.0)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 2.0)
    assert window.peek_spill(client) == pytest.approx(0.0)


def test_skew_s4_r4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev', wall_now=WALL0 + 4.0)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    assert window.peek_spill(client) == pytest.approx(0.0)


def test_skew_sm4_r0p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev', wall_now=WALL0 + -4.0)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.5)
    assert window.peek_spill(client) == pytest.approx(4.5)


def test_skew_sm4_r1():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev', wall_now=WALL0 + -4.0)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 1.0)
    assert window.peek_spill(client) == pytest.approx(5.0)


def test_skew_sm4_r2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev', wall_now=WALL0 + -4.0)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 2.0)
    assert window.peek_spill(client) == pytest.approx(6.0)


def test_skew_sm4_r4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev', wall_now=WALL0 + -4.0)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    assert window.peek_spill(client) == pytest.approx(8.0)


def test_mirrorfresh_d0p5_w0p625_a0():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.5)
    assert window.peek_spill(client) == pytest.approx(0.5)  # warm the spill mirror
    wall.advance(0.0)  # inside the TTL: the publish consults the mirror, not the document
    reads_before = window.spill_reads
    window.publish_spill('batch_admit', 0.625, client=client)
    assert window.spill_reads == reads_before
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000000.625)


def test_mirrorfresh_d0p5_w0p625_a0p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.5)
    assert window.peek_spill(client) == pytest.approx(0.5)  # warm the spill mirror
    wall.advance(0.5)  # inside the TTL: the publish consults the mirror, not the document
    reads_before = window.spill_reads
    window.publish_spill('batch_admit', 0.625, client=client)
    assert window.spill_reads == reads_before
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000001.125)


def test_mirrorfresh_d0p5_w1p5_a0():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.5)
    assert window.peek_spill(client) == pytest.approx(0.5)  # warm the spill mirror
    wall.advance(0.0)  # inside the TTL: the publish consults the mirror, not the document
    reads_before = window.spill_reads
    window.publish_spill('batch_admit', 1.5, client=client)
    assert window.spill_reads == reads_before
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000001.5)


def test_mirrorfresh_d0p5_w1p5_a0p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.5)
    assert window.peek_spill(client) == pytest.approx(0.5)  # warm the spill mirror
    wall.advance(0.5)  # inside the TTL: the publish consults the mirror, not the document
    reads_before = window.spill_reads
    window.publish_spill('batch_admit', 1.5, client=client)
    assert window.spill_reads == reads_before
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000002.0)


def test_mirrorfresh_d1_w0p625_a0():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 1.0)
    assert window.peek_spill(client) == pytest.approx(1.0)  # warm the spill mirror
    wall.advance(0.0)  # inside the TTL: the publish consults the mirror, not the document
    reads_before = window.spill_reads
    window.publish_spill('batch_admit', 0.625, client=client)
    assert window.spill_reads == reads_before
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000001.0)


def test_mirrorfresh_d1_w0p625_a0p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 1.0)
    assert window.peek_spill(client) == pytest.approx(1.0)  # warm the spill mirror
    wall.advance(0.5)  # inside the TTL: the publish consults the mirror, not the document
    reads_before = window.spill_reads
    window.publish_spill('batch_admit', 0.625, client=client)
    assert window.spill_reads == reads_before
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000001.125)


def test_mirrorfresh_d1_w1p5_a0():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 1.0)
    assert window.peek_spill(client) == pytest.approx(1.0)  # warm the spill mirror
    wall.advance(0.0)  # inside the TTL: the publish consults the mirror, not the document
    reads_before = window.spill_reads
    window.publish_spill('batch_admit', 1.5, client=client)
    assert window.spill_reads == reads_before
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000001.5)


def test_mirrorfresh_d1_w1p5_a0p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 1.0)
    assert window.peek_spill(client) == pytest.approx(1.0)  # warm the spill mirror
    wall.advance(0.5)  # inside the TTL: the publish consults the mirror, not the document
    reads_before = window.spill_reads
    window.publish_spill('batch_admit', 1.5, client=client)
    assert window.spill_reads == reads_before
    stored = client.docs[(spill_collection('batch_pipeline_dev'), SPILL_DOC)]
    assert stored['armed_until'] == pytest.approx(1000002.0)


def test_ownexpired_a2_r0p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.5)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper.arm('batch_claim')  # the label's own window, expired by the clock below
    clock.now += 2.0
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(0.5)  # the expired own window no longer covers; the spill does
    assert clock.sleeps == [pytest.approx(0.5)]


def test_ownexpired_a2_r2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 2.0)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper.arm('batch_claim')  # the label's own window, expired by the clock below
    clock.now += 2.0
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(1.0)  # the expired own window no longer covers; the spill does
    assert clock.sleeps == [pytest.approx(1.0)]


def test_ownexpired_a2_r4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper.arm('batch_claim')  # the label's own window, expired by the clock below
    clock.now += 2.0
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(1.0)  # the expired own window no longer covers; the spill does
    assert clock.sleeps == [pytest.approx(1.0)]


def test_ownexpired_a10_r0p5():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.5)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper.arm('batch_claim')  # the label's own window, expired by the clock below
    clock.now += 10.0
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(0.5)  # the expired own window no longer covers; the spill does
    assert clock.sleeps == [pytest.approx(0.5)]


def test_ownexpired_a10_r2():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 2.0)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper.arm('batch_claim')  # the label's own window, expired by the clock below
    clock.now += 10.0
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(1.0)  # the expired own window no longer covers; the spill does
    assert clock.sleeps == [pytest.approx(1.0)]


def test_ownexpired_a10_r4():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 4.0)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper.arm('batch_claim')  # the label's own window, expired by the clock below
    clock.now += 10.0
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(1.0)  # the expired own window no longer covers; the spill does
    assert clock.sleeps == [pytest.approx(1.0)]


def test_gen_k0_slive():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    for _ in range(0):
        damper.arm('batch_claim')
    generation_before = damper._generations.get('batch_claim', 0)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 1.0)
    waited, generation = damper.consult('batch_claim', client=client)
    assert generation == generation_before


def test_gen_k0_sabsent():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    for _ in range(0):
        damper.arm('batch_claim')
    generation_before = damper._generations.get('batch_claim', 0)
    waited, generation = damper.consult('batch_claim', client=client)
    assert generation == generation_before


def test_gen_k1_slive():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    for _ in range(1):
        damper.arm('batch_claim')
    generation_before = damper._generations.get('batch_claim', 0)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 1.0)
    waited, generation = damper.consult('batch_claim', client=client)
    assert generation == generation_before


def test_gen_k1_sabsent():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    for _ in range(1):
        damper.arm('batch_claim')
    generation_before = damper._generations.get('batch_claim', 0)
    waited, generation = damper.consult('batch_claim', client=client)
    assert generation == generation_before


def test_gen_k2_slive():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    for _ in range(2):
        damper.arm('batch_claim')
    generation_before = damper._generations.get('batch_claim', 0)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 1.0)
    waited, generation = damper.consult('batch_claim', client=client)
    assert generation == generation_before


def test_gen_k2_sabsent():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    for _ in range(2):
        damper.arm('batch_claim')
    generation_before = damper._generations.get('batch_claim', 0)
    waited, generation = damper.consult('batch_claim', client=client)
    assert generation == generation_before


def test_gen_k3_slive():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    for _ in range(3):
        damper.arm('batch_claim')
    generation_before = damper._generations.get('batch_claim', 0)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 1.0)
    waited, generation = damper.consult('batch_claim', client=client)
    assert generation == generation_before


def test_gen_k3_sabsent():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    for _ in range(3):
        damper.arm('batch_claim')
    generation_before = damper._generations.get('batch_claim', 0)
    waited, generation = damper.consult('batch_claim', client=client)
    assert generation == generation_before
