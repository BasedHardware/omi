"""Gate fleet adoption chain schedule grid (the x679/30m exhausted family)

Full retry chains through the real store run path on injected clocks: each
cell pins the exact sleep sequence the chain pays (entry consult on the
damper clock, then per-rung equal-jitter plus the fleet-aware gate wait,
with the wave-rung maximum from the third rung), the outcome, and the
exhaustion retry_after stamp the gate must not touch.


Every test below drives the real ``database.batch_pipeline_store`` damper,
fleet window and (for the schedule grid) the real store run path on
deterministic injected clocks; one emitted test pins one input combination's
exact outcome as literals. The harness is restated from
``tests/unit/test_batch_store_gate_fleet_adoption_contract.py`` so this file
runs isolated.

Failure-Class: FC-mid-ladder-retry-collides-inside-the-concurrently-armed-storm-window
"""

import logging
from unittest.mock import Mock

import pytest
from google.api_core.exceptions import Aborted

from database import batch_pipeline_store as storage
from database.firestore_transaction_retry import transaction_retry_deadline_scope as retry_deadline_scope

FC_TOKEN = 'FC-mid-ladder-retry-collides-inside-the-concurrently-armed-storm-window'
SPILL_CAP = storage._FleetStormWindow.SPILL_SHARE_CAP_SECONDS  # 1.0
BASE_SECONDS = storage.FirestoreStore.STORM_DAMPER_BASE_SECONDS  # 0.25
CAP_SECONDS = storage.FirestoreStore.STORM_DAMPER_CAP_SECONDS  # 4.0
WALL0 = 1_000_000.0


# --------------------------------------------------------------------------
# Harnesses
# --------------------------------------------------------------------------


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


class DepletingAbortTx(AbortThenCommitTx):
    """One abort per transaction, draining the CLIENT-side budget.

    ``abort_times=N`` on the client aborts the first N chain attempts once
    each and commits from attempt N+1 on — the retry helper mints a fresh
    transaction per attempt, so a per-transaction budget would never deplete.
    """

    def __init__(self, client):
        super().__init__(0)
        self._client = client
        self.abort_times = 1 if client.abort_times > 0 else 0

    def _commit(self):
        if self.abort_times > 0:
            self.abort_times -= 1
            self._client.abort_times -= 1
            raise Aborted('synthetic commit contention')
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

    def __init__(self, now=WALL0):
        self.now = now

    def time(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


class StormDocsClient:
    """Transactions for the store plus a dict-backed storm-window collection."""

    def __init__(self, abort_times=0):
        self.abort_times = abort_times
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
        return DepletingAbortTx(self)

    def collection(self, name):
        return _StormDocsCollection(self, name)


class _StormDocsCollection:
    def __init__(self, client, name):
        self._client = client
        self._name = name

    def document(self, doc_id):
        return _StormDocsDocument(self._client, self._name, doc_id)


class _StormDocsDocument:
    def __init__(self, client, name, doc_id):
        self._client = client
        self._name = name
        self._doc_id = doc_id

    def get(self, timeout=None):
        self._client.get_calls.append((self._name, self._doc_id, timeout))
        if self._client.fail_gets > 0:
            self._client.fail_gets -= 1
            raise RuntimeError('synthetic storm-window read fault')
        return StormDocsClient.Snapshot(self._client.docs.get((self._name, self._doc_id)))

    def set(self, payload, merge=False, timeout=None):
        self._client.set_calls.append((self._name, self._doc_id, payload, timeout))
        if self._client.fail_sets > 0:
            self._client.fail_sets -= 1
            raise RuntimeError('synthetic storm-window write fault')
        key = (self._name, self._doc_id)
        if merge and key in self._client.docs and isinstance(self._client.docs[key], dict):
            merged = dict(self._client.docs[key])
            merged.update(payload)
            self._client.docs[key] = merged
        else:
            self._client.docs[key] = dict(payload)


def fresh_window(namespace='batch_pipeline_dev', wall_now=WALL0):
    wall = FakeWall(now=wall_now)
    window = storage._FleetStormWindow(namespace)
    window._wall_now = wall.time
    return window, wall


def fresh_damper(namespace='batch_pipeline_dev', *, window=None, now=100.0, jitter=0.0):
    clock = FakeClock(now=now, jitter=jitter)
    damper = storage._ContentionStormDamper(fleet_window=window)
    damper._monotonic = clock.monotonic
    damper._sleeper = clock.sleep
    damper._random_value = clock.random_value
    return damper, clock


def seed_label_doc(client, namespace, label, until_wall):
    doc_id = storage.fleet_storm_window_doc_id(label)
    client.docs[(f'{namespace}_storm_dampers', doc_id)] = {'armed_until': until_wall}


def seed_spill(client, namespace, until_wall, label='batch_merge'):
    client.docs[(f'{namespace}_storm_dampers', storage._FleetStormWindow.SPILL_DOC_ID)] = {
        'armed_until': until_wall,
        'label': label,
    }


def reset_registries():
    storage.reset_shared_storm_dampers()
    storage.reset_fleet_storm_windows()


def equal_jitter_high(attempt):
    return min(0.2 * (2 ** (attempt - 1)), 4.0)


def wave_rung_high(failed_attempt):
    return min(
        CAP_SECONDS,
        BASE_SECONDS * (2 ** min(failed_attempt - 1, storage.FirestoreStore.STORM_DAMPER_LADDER_STEPS)),
    )


import time


@pytest.fixture(autouse=True)
def _reset_storm_registries():
    storage.reset_shared_storm_dampers()
    storage.reset_fleet_storm_windows()
    yield
    storage.reset_shared_storm_dampers()
    storage.reset_fleet_storm_windows()


LABEL = 'batch_merge_commit'
NS_STORMS = 'batch_pipeline_dev_storm_dampers'
LABEL_DOC = (NS_STORMS, 'batch_merge_commit')


def seed_label_doc_here(client, until_wall):
    client.docs[(NS_STORMS, LABEL)] = {'armed_until': until_wall}


def seed_spill_here(client, until_wall, label='batch_other'):
    client.docs[(NS_STORMS, storage._FleetStormWindow.SPILL_DOC_ID)] = {
        'armed_until': until_wall,
        'label': label,
    }


def adopt_registry_clocks(namespace='batch_pipeline_dev', *, damper_jitter=0.0, now=100.0, wall_now=WALL0):
    """Inject deterministic clocks into the SHARED registry damper and mirror."""
    clock = FakeClock(now=now, jitter=damper_jitter)
    damper = storage.shared_storm_damper(namespace)
    damper._monotonic = clock.monotonic
    damper._sleeper = clock.sleep
    damper._random_value = clock.random_value
    wall = FakeWall(now=wall_now)
    window = storage.fleet_storm_window(namespace)
    window._wall_now = wall.time
    return damper, window, clock, wall


class SleepRecordingRetry:
    """Wrap the real retry helper so the chain's sleeps and jitters are pinned."""

    def __init__(self):
        self.sleeps = []
        self.jitter = 0.0

    def __call__(self, monkeypatch):
        actual = storage.run_with_transaction_contention_retry
        recorder = self

        def factory(*args, **kwargs):
            kwargs.setdefault('sleep', recorder.sleeps.append)
            kwargs.setdefault('random_value', lambda: recorder.jitter)
            return actual(*args, **kwargs)

        monkeypatch.setattr(storage, 'run_with_transaction_contention_retry', factory)
        return self


def default_store(monkeypatch, namespace='batch_pipeline_dev', client=None):
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    return storage.FirestoreStore(namespace, firestore_client=client if client is not None else Mock())


def test_chain_abort0_none_rj0_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=0)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.0
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == []
        assert clock.sleeps == []
    finally:
        reset_registries()


def test_chain_abort0_none_rj0_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=0)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.0
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == []
        assert clock.sleeps == []
    finally:
        reset_registries()


def test_chain_abort0_none_rj0p25_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=0)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.25
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == []
        assert clock.sleeps == []
    finally:
        reset_registries()


def test_chain_abort0_none_rj0p25_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=0)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.25
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == []
        assert clock.sleeps == []
    finally:
        reset_registries()


def test_chain_abort0_none_rj0p5_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=0)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.5
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == []
        assert clock.sleeps == []
    finally:
        reset_registries()


def test_chain_abort0_none_rj0p5_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=0)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.5
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == []
        assert clock.sleeps == []
    finally:
        reset_registries()


def test_chain_abort0_none_rj0p75_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=0)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.75
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == []
        assert clock.sleeps == []
    finally:
        reset_registries()


def test_chain_abort0_none_rj0p75_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=0)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.75
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == []
        assert clock.sleeps == []
    finally:
        reset_registries()


def test_chain_abort0_none_rj1_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=0)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 1.0
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == []
        assert clock.sleeps == []
    finally:
        reset_registries()


def test_chain_abort0_none_rj1_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=0)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 1.0
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == []
        assert clock.sleeps == []
    finally:
        reset_registries()


def test_chain_abort0_own0_5_rj0_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=0)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.0
        damper._armed_until[LABEL] = clock.now + 0.5
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == []
        assert clock.sleeps == [pytest.approx(0.5, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort0_own0_5_rj0_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=0)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.0
        damper._armed_until[LABEL] = clock.now + 0.5
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == []
        assert clock.sleeps == [pytest.approx(0.5, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort0_own0_5_rj0p25_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=0)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.25
        damper._armed_until[LABEL] = clock.now + 0.5
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == []
        assert clock.sleeps == [pytest.approx(0.5, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort0_own0_5_rj0p25_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=0)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.25
        damper._armed_until[LABEL] = clock.now + 0.5
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == []
        assert clock.sleeps == [pytest.approx(0.5, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort0_own0_5_rj0p5_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=0)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.5
        damper._armed_until[LABEL] = clock.now + 0.5
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == []
        assert clock.sleeps == [pytest.approx(0.5, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort0_own0_5_rj0p5_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=0)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.5
        damper._armed_until[LABEL] = clock.now + 0.5
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == []
        assert clock.sleeps == [pytest.approx(0.5, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort0_own0_5_rj0p75_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=0)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.75
        damper._armed_until[LABEL] = clock.now + 0.5
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == []
        assert clock.sleeps == [pytest.approx(0.5, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort0_own0_5_rj0p75_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=0)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.75
        damper._armed_until[LABEL] = clock.now + 0.5
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == []
        assert clock.sleeps == [pytest.approx(0.5, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort0_own0_5_rj1_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=0)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 1.0
        damper._armed_until[LABEL] = clock.now + 0.5
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == []
        assert clock.sleeps == [pytest.approx(0.5, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort0_own0_5_rj1_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=0)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 1.0
        damper._armed_until[LABEL] = clock.now + 0.5
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == []
        assert clock.sleeps == [pytest.approx(0.5, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort0_own1_5_rj0_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=0)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.0
        damper._armed_until[LABEL] = clock.now + 1.5
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == []
        assert clock.sleeps == [pytest.approx(1.5, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort0_own1_5_rj0_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=0)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.0
        damper._armed_until[LABEL] = clock.now + 1.5
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == []
        assert clock.sleeps == [pytest.approx(1.5, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort0_own1_5_rj0p25_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=0)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.25
        damper._armed_until[LABEL] = clock.now + 1.5
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == []
        assert clock.sleeps == [pytest.approx(1.5, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort0_own1_5_rj0p25_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=0)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.25
        damper._armed_until[LABEL] = clock.now + 1.5
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == []
        assert clock.sleeps == [pytest.approx(1.5, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort0_own1_5_rj0p5_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=0)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.5
        damper._armed_until[LABEL] = clock.now + 1.5
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == []
        assert clock.sleeps == [pytest.approx(1.5, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort0_own1_5_rj0p5_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=0)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.5
        damper._armed_until[LABEL] = clock.now + 1.5
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == []
        assert clock.sleeps == [pytest.approx(1.5, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort0_own1_5_rj0p75_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=0)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.75
        damper._armed_until[LABEL] = clock.now + 1.5
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == []
        assert clock.sleeps == [pytest.approx(1.5, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort0_own1_5_rj0p75_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=0)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.75
        damper._armed_until[LABEL] = clock.now + 1.5
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == []
        assert clock.sleeps == [pytest.approx(1.5, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort0_own1_5_rj1_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=0)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 1.0
        damper._armed_until[LABEL] = clock.now + 1.5
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == []
        assert clock.sleeps == [pytest.approx(1.5, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort0_own1_5_rj1_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=0)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 1.0
        damper._armed_until[LABEL] = clock.now + 1.5
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == []
        assert clock.sleeps == [pytest.approx(1.5, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort0_fleet0_3_rj0_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=0)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.0
        seed_label_doc_here(client, WALL0 + 0.3)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == []
        assert clock.sleeps == [pytest.approx(0.30000000004656613, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort0_fleet0_3_rj0_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=0)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.0
        seed_label_doc_here(client, WALL0 + 0.3)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == []
        assert clock.sleeps == [pytest.approx(0.30000000004656613, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort0_fleet0_3_rj0p25_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=0)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.25
        seed_label_doc_here(client, WALL0 + 0.3)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == []
        assert clock.sleeps == [pytest.approx(0.30000000004656613, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort0_fleet0_3_rj0p25_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=0)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.25
        seed_label_doc_here(client, WALL0 + 0.3)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == []
        assert clock.sleeps == [pytest.approx(0.30000000004656613, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort0_fleet0_3_rj0p5_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=0)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.5
        seed_label_doc_here(client, WALL0 + 0.3)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == []
        assert clock.sleeps == [pytest.approx(0.30000000004656613, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort0_fleet0_3_rj0p5_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=0)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.5
        seed_label_doc_here(client, WALL0 + 0.3)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == []
        assert clock.sleeps == [pytest.approx(0.30000000004656613, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort0_fleet0_3_rj0p75_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=0)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.75
        seed_label_doc_here(client, WALL0 + 0.3)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == []
        assert clock.sleeps == [pytest.approx(0.30000000004656613, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort0_fleet0_3_rj0p75_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=0)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.75
        seed_label_doc_here(client, WALL0 + 0.3)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == []
        assert clock.sleeps == [pytest.approx(0.30000000004656613, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort0_fleet0_3_rj1_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=0)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 1.0
        seed_label_doc_here(client, WALL0 + 0.3)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == []
        assert clock.sleeps == [pytest.approx(0.30000000004656613, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort0_fleet0_3_rj1_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=0)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 1.0
        seed_label_doc_here(client, WALL0 + 0.3)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == []
        assert clock.sleeps == [pytest.approx(0.30000000004656613, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort0_fleet2_0_rj0_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=0)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.0
        seed_label_doc_here(client, WALL0 + 2.0)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == []
        assert clock.sleeps == [pytest.approx(2.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort0_fleet2_0_rj0_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=0)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.0
        seed_label_doc_here(client, WALL0 + 2.0)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == []
        assert clock.sleeps == [pytest.approx(2.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort0_fleet2_0_rj0p25_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=0)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.25
        seed_label_doc_here(client, WALL0 + 2.0)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == []
        assert clock.sleeps == [pytest.approx(2.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort0_fleet2_0_rj0p25_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=0)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.25
        seed_label_doc_here(client, WALL0 + 2.0)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == []
        assert clock.sleeps == [pytest.approx(2.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort0_fleet2_0_rj0p5_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=0)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.5
        seed_label_doc_here(client, WALL0 + 2.0)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == []
        assert clock.sleeps == [pytest.approx(2.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort0_fleet2_0_rj0p5_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=0)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.5
        seed_label_doc_here(client, WALL0 + 2.0)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == []
        assert clock.sleeps == [pytest.approx(2.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort0_fleet2_0_rj0p75_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=0)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.75
        seed_label_doc_here(client, WALL0 + 2.0)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == []
        assert clock.sleeps == [pytest.approx(2.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort0_fleet2_0_rj0p75_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=0)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.75
        seed_label_doc_here(client, WALL0 + 2.0)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == []
        assert clock.sleeps == [pytest.approx(2.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort0_fleet2_0_rj1_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=0)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 1.0
        seed_label_doc_here(client, WALL0 + 2.0)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == []
        assert clock.sleeps == [pytest.approx(2.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort0_fleet2_0_rj1_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=0)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 1.0
        seed_label_doc_here(client, WALL0 + 2.0)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == []
        assert clock.sleeps == [pytest.approx(2.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort0_fleet3_9_rj0_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=0)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.0
        seed_label_doc_here(client, WALL0 + 3.9)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == []
        assert clock.sleeps == [pytest.approx(3.900000000023283, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort0_fleet3_9_rj0_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=0)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.0
        seed_label_doc_here(client, WALL0 + 3.9)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == []
        assert clock.sleeps == [pytest.approx(3.900000000023283, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort0_fleet3_9_rj0p25_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=0)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.25
        seed_label_doc_here(client, WALL0 + 3.9)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == []
        assert clock.sleeps == [pytest.approx(3.900000000023283, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort0_fleet3_9_rj0p25_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=0)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.25
        seed_label_doc_here(client, WALL0 + 3.9)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == []
        assert clock.sleeps == [pytest.approx(3.900000000023283, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort0_fleet3_9_rj0p5_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=0)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.5
        seed_label_doc_here(client, WALL0 + 3.9)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == []
        assert clock.sleeps == [pytest.approx(3.900000000023283, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort0_fleet3_9_rj0p5_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=0)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.5
        seed_label_doc_here(client, WALL0 + 3.9)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == []
        assert clock.sleeps == [pytest.approx(3.900000000023283, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort0_fleet3_9_rj0p75_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=0)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.75
        seed_label_doc_here(client, WALL0 + 3.9)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == []
        assert clock.sleeps == [pytest.approx(3.900000000023283, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort0_fleet3_9_rj0p75_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=0)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.75
        seed_label_doc_here(client, WALL0 + 3.9)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == []
        assert clock.sleeps == [pytest.approx(3.900000000023283, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort0_fleet3_9_rj1_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=0)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 1.0
        seed_label_doc_here(client, WALL0 + 3.9)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == []
        assert clock.sleeps == [pytest.approx(3.900000000023283, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort0_fleet3_9_rj1_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=0)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 1.0
        seed_label_doc_here(client, WALL0 + 3.9)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == []
        assert clock.sleeps == [pytest.approx(3.900000000023283, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort0_spill0_6_rj0_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=0)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.0
        seed_spill_here(client, WALL0 + 0.6)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == []
        assert clock.sleeps == [pytest.approx(0.5999999999767169, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort0_spill0_6_rj0_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=0)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.0
        seed_spill_here(client, WALL0 + 0.6)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == []
        assert clock.sleeps == [pytest.approx(0.5999999999767169, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort0_spill0_6_rj0p25_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=0)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.25
        seed_spill_here(client, WALL0 + 0.6)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == []
        assert clock.sleeps == [pytest.approx(0.5999999999767169, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort0_spill0_6_rj0p25_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=0)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.25
        seed_spill_here(client, WALL0 + 0.6)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == []
        assert clock.sleeps == [pytest.approx(0.5999999999767169, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort0_spill0_6_rj0p5_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=0)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.5
        seed_spill_here(client, WALL0 + 0.6)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == []
        assert clock.sleeps == [pytest.approx(0.5999999999767169, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort0_spill0_6_rj0p5_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=0)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.5
        seed_spill_here(client, WALL0 + 0.6)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == []
        assert clock.sleeps == [pytest.approx(0.5999999999767169, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort0_spill0_6_rj0p75_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=0)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.75
        seed_spill_here(client, WALL0 + 0.6)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == []
        assert clock.sleeps == [pytest.approx(0.5999999999767169, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort0_spill0_6_rj0p75_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=0)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.75
        seed_spill_here(client, WALL0 + 0.6)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == []
        assert clock.sleeps == [pytest.approx(0.5999999999767169, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort0_spill0_6_rj1_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=0)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 1.0
        seed_spill_here(client, WALL0 + 0.6)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == []
        assert clock.sleeps == [pytest.approx(0.5999999999767169, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort0_spill0_6_rj1_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=0)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 1.0
        seed_spill_here(client, WALL0 + 0.6)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == []
        assert clock.sleeps == [pytest.approx(0.5999999999767169, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort0_spill2_6_rj0_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=0)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.0
        seed_spill_here(client, WALL0 + 2.6)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == []
        assert clock.sleeps == [pytest.approx(1.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort0_spill2_6_rj0_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=0)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.0
        seed_spill_here(client, WALL0 + 2.6)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == []
        assert clock.sleeps == [pytest.approx(1.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort0_spill2_6_rj0p25_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=0)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.25
        seed_spill_here(client, WALL0 + 2.6)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == []
        assert clock.sleeps == [pytest.approx(1.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort0_spill2_6_rj0p25_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=0)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.25
        seed_spill_here(client, WALL0 + 2.6)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == []
        assert clock.sleeps == [pytest.approx(1.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort0_spill2_6_rj0p5_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=0)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.5
        seed_spill_here(client, WALL0 + 2.6)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == []
        assert clock.sleeps == [pytest.approx(1.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort0_spill2_6_rj0p5_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=0)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.5
        seed_spill_here(client, WALL0 + 2.6)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == []
        assert clock.sleeps == [pytest.approx(1.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort0_spill2_6_rj0p75_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=0)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.75
        seed_spill_here(client, WALL0 + 2.6)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == []
        assert clock.sleeps == [pytest.approx(1.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort0_spill2_6_rj0p75_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=0)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.75
        seed_spill_here(client, WALL0 + 2.6)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == []
        assert clock.sleeps == [pytest.approx(1.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort0_spill2_6_rj1_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=0)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 1.0
        seed_spill_here(client, WALL0 + 2.6)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == []
        assert clock.sleeps == [pytest.approx(1.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort0_spill2_6_rj1_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=0)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 1.0
        seed_spill_here(client, WALL0 + 2.6)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == []
        assert clock.sleeps == [pytest.approx(1.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort0_spill3_9_rj0_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=0)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.0
        seed_spill_here(client, WALL0 + 3.9)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == []
        assert clock.sleeps == [pytest.approx(1.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort0_spill3_9_rj0_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=0)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.0
        seed_spill_here(client, WALL0 + 3.9)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == []
        assert clock.sleeps == [pytest.approx(1.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort0_spill3_9_rj0p25_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=0)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.25
        seed_spill_here(client, WALL0 + 3.9)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == []
        assert clock.sleeps == [pytest.approx(1.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort0_spill3_9_rj0p25_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=0)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.25
        seed_spill_here(client, WALL0 + 3.9)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == []
        assert clock.sleeps == [pytest.approx(1.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort0_spill3_9_rj0p5_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=0)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.5
        seed_spill_here(client, WALL0 + 3.9)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == []
        assert clock.sleeps == [pytest.approx(1.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort0_spill3_9_rj0p5_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=0)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.5
        seed_spill_here(client, WALL0 + 3.9)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == []
        assert clock.sleeps == [pytest.approx(1.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort0_spill3_9_rj0p75_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=0)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.75
        seed_spill_here(client, WALL0 + 3.9)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == []
        assert clock.sleeps == [pytest.approx(1.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort0_spill3_9_rj0p75_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=0)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.75
        seed_spill_here(client, WALL0 + 3.9)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == []
        assert clock.sleeps == [pytest.approx(1.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort0_spill3_9_rj1_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=0)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 1.0
        seed_spill_here(client, WALL0 + 3.9)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == []
        assert clock.sleeps == [pytest.approx(1.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort0_spill3_9_rj1_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=0)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 1.0
        seed_spill_here(client, WALL0 + 3.9)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == []
        assert clock.sleeps == [pytest.approx(1.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort1_none_rj0_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=1)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.0
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [pytest.approx(0.1, abs=1e-09)]
        assert clock.sleeps == []
    finally:
        reset_registries()


def test_chain_abort1_none_rj0_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=1)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.0
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [pytest.approx(0.1, abs=1e-09)]
        assert clock.sleeps == []
    finally:
        reset_registries()


def test_chain_abort1_none_rj0p25_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=1)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.25
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [pytest.approx(0.125, abs=1e-09)]
        assert clock.sleeps == []
    finally:
        reset_registries()


def test_chain_abort1_none_rj0p25_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=1)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.25
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [pytest.approx(0.125, abs=1e-09)]
        assert clock.sleeps == []
    finally:
        reset_registries()


def test_chain_abort1_none_rj0p5_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=1)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.5
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [pytest.approx(0.15000000000000002, abs=1e-09)]
        assert clock.sleeps == []
    finally:
        reset_registries()


def test_chain_abort1_none_rj0p5_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=1)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.5
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [pytest.approx(0.15000000000000002, abs=1e-09)]
        assert clock.sleeps == []
    finally:
        reset_registries()


def test_chain_abort1_none_rj0p75_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=1)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.75
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [pytest.approx(0.17500000000000002, abs=1e-09)]
        assert clock.sleeps == []
    finally:
        reset_registries()


def test_chain_abort1_none_rj0p75_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=1)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.75
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [pytest.approx(0.17500000000000002, abs=1e-09)]
        assert clock.sleeps == []
    finally:
        reset_registries()


def test_chain_abort1_none_rj1_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=1)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 1.0
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [pytest.approx(0.2, abs=1e-09)]
        assert clock.sleeps == []
    finally:
        reset_registries()


def test_chain_abort1_none_rj1_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=1)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 1.0
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [pytest.approx(0.2, abs=1e-09)]
        assert clock.sleeps == []
    finally:
        reset_registries()


def test_chain_abort1_own0_5_rj0_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=1)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.0
        damper._armed_until[LABEL] = clock.now + 0.5
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [pytest.approx(0.1, abs=1e-09)]
        assert clock.sleeps == [pytest.approx(0.5, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort1_own0_5_rj0_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=1)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.0
        damper._armed_until[LABEL] = clock.now + 0.5
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [pytest.approx(0.1, abs=1e-09)]
        assert clock.sleeps == [pytest.approx(0.5, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort1_own0_5_rj0p25_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=1)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.25
        damper._armed_until[LABEL] = clock.now + 0.5
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [pytest.approx(0.125, abs=1e-09)]
        assert clock.sleeps == [pytest.approx(0.5, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort1_own0_5_rj0p25_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=1)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.25
        damper._armed_until[LABEL] = clock.now + 0.5
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [pytest.approx(0.125, abs=1e-09)]
        assert clock.sleeps == [pytest.approx(0.5, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort1_own0_5_rj0p5_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=1)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.5
        damper._armed_until[LABEL] = clock.now + 0.5
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [pytest.approx(0.15000000000000002, abs=1e-09)]
        assert clock.sleeps == [pytest.approx(0.5, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort1_own0_5_rj0p5_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=1)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.5
        damper._armed_until[LABEL] = clock.now + 0.5
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [pytest.approx(0.15000000000000002, abs=1e-09)]
        assert clock.sleeps == [pytest.approx(0.5, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort1_own0_5_rj0p75_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=1)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.75
        damper._armed_until[LABEL] = clock.now + 0.5
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [pytest.approx(0.17500000000000002, abs=1e-09)]
        assert clock.sleeps == [pytest.approx(0.5, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort1_own0_5_rj0p75_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=1)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.75
        damper._armed_until[LABEL] = clock.now + 0.5
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [pytest.approx(0.17500000000000002, abs=1e-09)]
        assert clock.sleeps == [pytest.approx(0.5, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort1_own0_5_rj1_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=1)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 1.0
        damper._armed_until[LABEL] = clock.now + 0.5
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [pytest.approx(0.2, abs=1e-09)]
        assert clock.sleeps == [pytest.approx(0.5, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort1_own0_5_rj1_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=1)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 1.0
        damper._armed_until[LABEL] = clock.now + 0.5
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [pytest.approx(0.2, abs=1e-09)]
        assert clock.sleeps == [pytest.approx(0.5, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort1_own1_5_rj0_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=1)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.0
        damper._armed_until[LABEL] = clock.now + 1.5
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [pytest.approx(0.1, abs=1e-09)]
        assert clock.sleeps == [pytest.approx(1.5, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort1_own1_5_rj0_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=1)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.0
        damper._armed_until[LABEL] = clock.now + 1.5
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [pytest.approx(0.1, abs=1e-09)]
        assert clock.sleeps == [pytest.approx(1.5, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort1_own1_5_rj0p25_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=1)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.25
        damper._armed_until[LABEL] = clock.now + 1.5
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [pytest.approx(0.125, abs=1e-09)]
        assert clock.sleeps == [pytest.approx(1.5, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort1_own1_5_rj0p25_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=1)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.25
        damper._armed_until[LABEL] = clock.now + 1.5
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [pytest.approx(0.125, abs=1e-09)]
        assert clock.sleeps == [pytest.approx(1.5, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort1_own1_5_rj0p5_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=1)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.5
        damper._armed_until[LABEL] = clock.now + 1.5
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [pytest.approx(0.15000000000000002, abs=1e-09)]
        assert clock.sleeps == [pytest.approx(1.5, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort1_own1_5_rj0p5_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=1)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.5
        damper._armed_until[LABEL] = clock.now + 1.5
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [pytest.approx(0.15000000000000002, abs=1e-09)]
        assert clock.sleeps == [pytest.approx(1.5, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort1_own1_5_rj0p75_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=1)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.75
        damper._armed_until[LABEL] = clock.now + 1.5
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [pytest.approx(0.17500000000000002, abs=1e-09)]
        assert clock.sleeps == [pytest.approx(1.5, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort1_own1_5_rj0p75_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=1)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.75
        damper._armed_until[LABEL] = clock.now + 1.5
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [pytest.approx(0.17500000000000002, abs=1e-09)]
        assert clock.sleeps == [pytest.approx(1.5, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort1_own1_5_rj1_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=1)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 1.0
        damper._armed_until[LABEL] = clock.now + 1.5
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [pytest.approx(0.2, abs=1e-09)]
        assert clock.sleeps == [pytest.approx(1.5, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort1_own1_5_rj1_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=1)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 1.0
        damper._armed_until[LABEL] = clock.now + 1.5
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [pytest.approx(0.2, abs=1e-09)]
        assert clock.sleeps == [pytest.approx(1.5, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort1_fleet0_3_rj0_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=1)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.0
        seed_label_doc_here(client, WALL0 + 0.3)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [pytest.approx(0.4000000000465661, abs=1e-09)]
        assert clock.sleeps == [pytest.approx(0.30000000004656613, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort1_fleet0_3_rj0_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=1)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.0
        seed_label_doc_here(client, WALL0 + 0.3)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [pytest.approx(0.4000000000465661, abs=1e-09)]
        assert clock.sleeps == [pytest.approx(0.30000000004656613, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort1_fleet0_3_rj0p25_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=1)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.25
        seed_label_doc_here(client, WALL0 + 0.3)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [pytest.approx(0.42500000004656613, abs=1e-09)]
        assert clock.sleeps == [pytest.approx(0.30000000004656613, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort1_fleet0_3_rj0p25_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=1)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.25
        seed_label_doc_here(client, WALL0 + 0.3)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [pytest.approx(0.42500000004656613, abs=1e-09)]
        assert clock.sleeps == [pytest.approx(0.30000000004656613, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort1_fleet0_3_rj0p5_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=1)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.5
        seed_label_doc_here(client, WALL0 + 0.3)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [pytest.approx(0.45000000004656615, abs=1e-09)]
        assert clock.sleeps == [pytest.approx(0.30000000004656613, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort1_fleet0_3_rj0p5_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=1)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.5
        seed_label_doc_here(client, WALL0 + 0.3)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [pytest.approx(0.45000000004656615, abs=1e-09)]
        assert clock.sleeps == [pytest.approx(0.30000000004656613, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort1_fleet0_3_rj0p75_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=1)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.75
        seed_label_doc_here(client, WALL0 + 0.3)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [pytest.approx(0.4750000000465662, abs=1e-09)]
        assert clock.sleeps == [pytest.approx(0.30000000004656613, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort1_fleet0_3_rj0p75_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=1)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.75
        seed_label_doc_here(client, WALL0 + 0.3)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [pytest.approx(0.4750000000465662, abs=1e-09)]
        assert clock.sleeps == [pytest.approx(0.30000000004656613, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort1_fleet0_3_rj1_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=1)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 1.0
        seed_label_doc_here(client, WALL0 + 0.3)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [pytest.approx(0.5000000000465661, abs=1e-09)]
        assert clock.sleeps == [pytest.approx(0.30000000004656613, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort1_fleet0_3_rj1_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=1)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 1.0
        seed_label_doc_here(client, WALL0 + 0.3)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [pytest.approx(0.5000000000465661, abs=1e-09)]
        assert clock.sleeps == [pytest.approx(0.30000000004656613, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort1_fleet2_0_rj0_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=1)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.0
        seed_label_doc_here(client, WALL0 + 2.0)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [pytest.approx(2.1, abs=1e-09)]
        assert clock.sleeps == [pytest.approx(2.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort1_fleet2_0_rj0_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=1)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.0
        seed_label_doc_here(client, WALL0 + 2.0)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [pytest.approx(2.1, abs=1e-09)]
        assert clock.sleeps == [pytest.approx(2.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort1_fleet2_0_rj0p25_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=1)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.25
        seed_label_doc_here(client, WALL0 + 2.0)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [pytest.approx(2.125, abs=1e-09)]
        assert clock.sleeps == [pytest.approx(2.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort1_fleet2_0_rj0p25_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=1)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.25
        seed_label_doc_here(client, WALL0 + 2.0)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [pytest.approx(2.125, abs=1e-09)]
        assert clock.sleeps == [pytest.approx(2.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort1_fleet2_0_rj0p5_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=1)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.5
        seed_label_doc_here(client, WALL0 + 2.0)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [pytest.approx(2.15, abs=1e-09)]
        assert clock.sleeps == [pytest.approx(2.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort1_fleet2_0_rj0p5_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=1)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.5
        seed_label_doc_here(client, WALL0 + 2.0)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [pytest.approx(2.15, abs=1e-09)]
        assert clock.sleeps == [pytest.approx(2.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort1_fleet2_0_rj0p75_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=1)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.75
        seed_label_doc_here(client, WALL0 + 2.0)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [pytest.approx(2.175, abs=1e-09)]
        assert clock.sleeps == [pytest.approx(2.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort1_fleet2_0_rj0p75_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=1)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.75
        seed_label_doc_here(client, WALL0 + 2.0)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [pytest.approx(2.175, abs=1e-09)]
        assert clock.sleeps == [pytest.approx(2.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort1_fleet2_0_rj1_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=1)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 1.0
        seed_label_doc_here(client, WALL0 + 2.0)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [pytest.approx(2.2, abs=1e-09)]
        assert clock.sleeps == [pytest.approx(2.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort1_fleet2_0_rj1_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=1)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 1.0
        seed_label_doc_here(client, WALL0 + 2.0)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [pytest.approx(2.2, abs=1e-09)]
        assert clock.sleeps == [pytest.approx(2.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort1_fleet3_9_rj0_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=1)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.0
        seed_label_doc_here(client, WALL0 + 3.9)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [pytest.approx(4.000000000023283, abs=1e-09)]
        assert clock.sleeps == [pytest.approx(3.900000000023283, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort1_fleet3_9_rj0_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=1)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.0
        seed_label_doc_here(client, WALL0 + 3.9)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [pytest.approx(4.000000000023283, abs=1e-09)]
        assert clock.sleeps == [pytest.approx(3.900000000023283, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort1_fleet3_9_rj0p25_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=1)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.25
        seed_label_doc_here(client, WALL0 + 3.9)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [pytest.approx(4.025000000023283, abs=1e-09)]
        assert clock.sleeps == [pytest.approx(3.900000000023283, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort1_fleet3_9_rj0p25_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=1)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.25
        seed_label_doc_here(client, WALL0 + 3.9)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [pytest.approx(4.025000000023283, abs=1e-09)]
        assert clock.sleeps == [pytest.approx(3.900000000023283, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort1_fleet3_9_rj0p5_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=1)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.5
        seed_label_doc_here(client, WALL0 + 3.9)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [pytest.approx(4.050000000023283, abs=1e-09)]
        assert clock.sleeps == [pytest.approx(3.900000000023283, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort1_fleet3_9_rj0p5_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=1)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.5
        seed_label_doc_here(client, WALL0 + 3.9)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [pytest.approx(4.050000000023283, abs=1e-09)]
        assert clock.sleeps == [pytest.approx(3.900000000023283, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort1_fleet3_9_rj0p75_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=1)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.75
        seed_label_doc_here(client, WALL0 + 3.9)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [pytest.approx(4.075000000023283, abs=1e-09)]
        assert clock.sleeps == [pytest.approx(3.900000000023283, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort1_fleet3_9_rj0p75_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=1)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.75
        seed_label_doc_here(client, WALL0 + 3.9)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [pytest.approx(4.075000000023283, abs=1e-09)]
        assert clock.sleeps == [pytest.approx(3.900000000023283, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort1_fleet3_9_rj1_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=1)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 1.0
        seed_label_doc_here(client, WALL0 + 3.9)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [pytest.approx(4.100000000023283, abs=1e-09)]
        assert clock.sleeps == [pytest.approx(3.900000000023283, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort1_fleet3_9_rj1_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=1)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 1.0
        seed_label_doc_here(client, WALL0 + 3.9)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [pytest.approx(4.100000000023283, abs=1e-09)]
        assert clock.sleeps == [pytest.approx(3.900000000023283, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort1_spill0_6_rj0_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=1)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.0
        seed_spill_here(client, WALL0 + 0.6)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [pytest.approx(0.6999999999767169, abs=1e-09)]
        assert clock.sleeps == [pytest.approx(0.5999999999767169, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort1_spill0_6_rj0_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=1)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.0
        seed_spill_here(client, WALL0 + 0.6)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [pytest.approx(0.6999999999767169, abs=1e-09)]
        assert clock.sleeps == [pytest.approx(0.5999999999767169, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort1_spill0_6_rj0p25_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=1)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.25
        seed_spill_here(client, WALL0 + 0.6)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [pytest.approx(0.7249999999767169, abs=1e-09)]
        assert clock.sleeps == [pytest.approx(0.5999999999767169, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort1_spill0_6_rj0p25_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=1)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.25
        seed_spill_here(client, WALL0 + 0.6)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [pytest.approx(0.7249999999767169, abs=1e-09)]
        assert clock.sleeps == [pytest.approx(0.5999999999767169, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort1_spill0_6_rj0p5_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=1)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.5
        seed_spill_here(client, WALL0 + 0.6)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [pytest.approx(0.749999999976717, abs=1e-09)]
        assert clock.sleeps == [pytest.approx(0.5999999999767169, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort1_spill0_6_rj0p5_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=1)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.5
        seed_spill_here(client, WALL0 + 0.6)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [pytest.approx(0.749999999976717, abs=1e-09)]
        assert clock.sleeps == [pytest.approx(0.5999999999767169, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort1_spill0_6_rj0p75_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=1)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.75
        seed_spill_here(client, WALL0 + 0.6)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [pytest.approx(0.774999999976717, abs=1e-09)]
        assert clock.sleeps == [pytest.approx(0.5999999999767169, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort1_spill0_6_rj0p75_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=1)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.75
        seed_spill_here(client, WALL0 + 0.6)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [pytest.approx(0.774999999976717, abs=1e-09)]
        assert clock.sleeps == [pytest.approx(0.5999999999767169, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort1_spill0_6_rj1_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=1)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 1.0
        seed_spill_here(client, WALL0 + 0.6)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [pytest.approx(0.7999999999767169, abs=1e-09)]
        assert clock.sleeps == [pytest.approx(0.5999999999767169, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort1_spill0_6_rj1_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=1)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 1.0
        seed_spill_here(client, WALL0 + 0.6)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [pytest.approx(0.7999999999767169, abs=1e-09)]
        assert clock.sleeps == [pytest.approx(0.5999999999767169, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort1_spill2_6_rj0_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=1)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.0
        seed_spill_here(client, WALL0 + 2.6)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [pytest.approx(1.1, abs=1e-09)]
        assert clock.sleeps == [pytest.approx(1.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort1_spill2_6_rj0_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=1)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.0
        seed_spill_here(client, WALL0 + 2.6)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [pytest.approx(1.1, abs=1e-09)]
        assert clock.sleeps == [pytest.approx(1.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort1_spill2_6_rj0p25_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=1)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.25
        seed_spill_here(client, WALL0 + 2.6)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [pytest.approx(1.125, abs=1e-09)]
        assert clock.sleeps == [pytest.approx(1.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort1_spill2_6_rj0p25_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=1)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.25
        seed_spill_here(client, WALL0 + 2.6)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [pytest.approx(1.125, abs=1e-09)]
        assert clock.sleeps == [pytest.approx(1.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort1_spill2_6_rj0p5_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=1)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.5
        seed_spill_here(client, WALL0 + 2.6)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [pytest.approx(1.15, abs=1e-09)]
        assert clock.sleeps == [pytest.approx(1.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort1_spill2_6_rj0p5_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=1)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.5
        seed_spill_here(client, WALL0 + 2.6)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [pytest.approx(1.15, abs=1e-09)]
        assert clock.sleeps == [pytest.approx(1.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort1_spill2_6_rj0p75_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=1)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.75
        seed_spill_here(client, WALL0 + 2.6)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [pytest.approx(1.175, abs=1e-09)]
        assert clock.sleeps == [pytest.approx(1.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort1_spill2_6_rj0p75_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=1)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.75
        seed_spill_here(client, WALL0 + 2.6)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [pytest.approx(1.175, abs=1e-09)]
        assert clock.sleeps == [pytest.approx(1.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort1_spill2_6_rj1_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=1)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 1.0
        seed_spill_here(client, WALL0 + 2.6)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [pytest.approx(1.2, abs=1e-09)]
        assert clock.sleeps == [pytest.approx(1.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort1_spill2_6_rj1_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=1)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 1.0
        seed_spill_here(client, WALL0 + 2.6)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [pytest.approx(1.2, abs=1e-09)]
        assert clock.sleeps == [pytest.approx(1.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort1_spill3_9_rj0_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=1)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.0
        seed_spill_here(client, WALL0 + 3.9)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [pytest.approx(1.1, abs=1e-09)]
        assert clock.sleeps == [pytest.approx(1.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort1_spill3_9_rj0_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=1)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.0
        seed_spill_here(client, WALL0 + 3.9)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [pytest.approx(1.1, abs=1e-09)]
        assert clock.sleeps == [pytest.approx(1.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort1_spill3_9_rj0p25_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=1)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.25
        seed_spill_here(client, WALL0 + 3.9)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [pytest.approx(1.125, abs=1e-09)]
        assert clock.sleeps == [pytest.approx(1.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort1_spill3_9_rj0p25_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=1)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.25
        seed_spill_here(client, WALL0 + 3.9)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [pytest.approx(1.125, abs=1e-09)]
        assert clock.sleeps == [pytest.approx(1.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort1_spill3_9_rj0p5_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=1)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.5
        seed_spill_here(client, WALL0 + 3.9)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [pytest.approx(1.15, abs=1e-09)]
        assert clock.sleeps == [pytest.approx(1.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort1_spill3_9_rj0p5_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=1)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.5
        seed_spill_here(client, WALL0 + 3.9)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [pytest.approx(1.15, abs=1e-09)]
        assert clock.sleeps == [pytest.approx(1.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort1_spill3_9_rj0p75_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=1)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.75
        seed_spill_here(client, WALL0 + 3.9)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [pytest.approx(1.175, abs=1e-09)]
        assert clock.sleeps == [pytest.approx(1.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort1_spill3_9_rj0p75_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=1)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.75
        seed_spill_here(client, WALL0 + 3.9)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [pytest.approx(1.175, abs=1e-09)]
        assert clock.sleeps == [pytest.approx(1.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort1_spill3_9_rj1_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=1)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 1.0
        seed_spill_here(client, WALL0 + 3.9)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [pytest.approx(1.2, abs=1e-09)]
        assert clock.sleeps == [pytest.approx(1.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort1_spill3_9_rj1_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=1)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 1.0
        seed_spill_here(client, WALL0 + 3.9)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [pytest.approx(1.2, abs=1e-09)]
        assert clock.sleeps == [pytest.approx(1.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort2_none_rj0_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=2)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.0
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [pytest.approx(0.1, abs=1e-09), pytest.approx(0.2, abs=1e-09)]
        assert clock.sleeps == []
    finally:
        reset_registries()


def test_chain_abort2_none_rj0_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=2)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.0
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [pytest.approx(0.1, abs=1e-09), pytest.approx(0.2, abs=1e-09)]
        assert clock.sleeps == []
    finally:
        reset_registries()


def test_chain_abort2_none_rj0p25_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=2)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.25
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [pytest.approx(0.125, abs=1e-09), pytest.approx(0.25, abs=1e-09)]
        assert clock.sleeps == []
    finally:
        reset_registries()


def test_chain_abort2_none_rj0p25_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=2)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.25
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [pytest.approx(0.125, abs=1e-09), pytest.approx(0.25, abs=1e-09)]
        assert clock.sleeps == []
    finally:
        reset_registries()


def test_chain_abort2_none_rj0p5_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=2)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.5
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(0.15000000000000002, abs=1e-09),
            pytest.approx(0.30000000000000004, abs=1e-09),
        ]
        assert clock.sleeps == []
    finally:
        reset_registries()


def test_chain_abort2_none_rj0p5_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=2)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.5
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(0.15000000000000002, abs=1e-09),
            pytest.approx(0.30000000000000004, abs=1e-09),
        ]
        assert clock.sleeps == []
    finally:
        reset_registries()


def test_chain_abort2_none_rj0p75_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=2)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.75
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(0.17500000000000002, abs=1e-09),
            pytest.approx(0.35000000000000003, abs=1e-09),
        ]
        assert clock.sleeps == []
    finally:
        reset_registries()


def test_chain_abort2_none_rj0p75_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=2)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.75
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(0.17500000000000002, abs=1e-09),
            pytest.approx(0.35000000000000003, abs=1e-09),
        ]
        assert clock.sleeps == []
    finally:
        reset_registries()


def test_chain_abort2_none_rj1_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=2)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 1.0
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [pytest.approx(0.2, abs=1e-09), pytest.approx(0.4, abs=1e-09)]
        assert clock.sleeps == []
    finally:
        reset_registries()


def test_chain_abort2_none_rj1_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=2)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 1.0
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [pytest.approx(0.2, abs=1e-09), pytest.approx(0.4, abs=1e-09)]
        assert clock.sleeps == []
    finally:
        reset_registries()


def test_chain_abort2_own0_5_rj0_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=2)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.0
        damper._armed_until[LABEL] = clock.now + 0.5
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [pytest.approx(0.1, abs=1e-09), pytest.approx(0.2, abs=1e-09)]
        assert clock.sleeps == [pytest.approx(0.5, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort2_own0_5_rj0_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=2)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.0
        damper._armed_until[LABEL] = clock.now + 0.5
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [pytest.approx(0.1, abs=1e-09), pytest.approx(0.2, abs=1e-09)]
        assert clock.sleeps == [pytest.approx(0.5, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort2_own0_5_rj0p25_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=2)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.25
        damper._armed_until[LABEL] = clock.now + 0.5
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [pytest.approx(0.125, abs=1e-09), pytest.approx(0.25, abs=1e-09)]
        assert clock.sleeps == [pytest.approx(0.5, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort2_own0_5_rj0p25_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=2)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.25
        damper._armed_until[LABEL] = clock.now + 0.5
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [pytest.approx(0.125, abs=1e-09), pytest.approx(0.25, abs=1e-09)]
        assert clock.sleeps == [pytest.approx(0.5, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort2_own0_5_rj0p5_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=2)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.5
        damper._armed_until[LABEL] = clock.now + 0.5
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(0.15000000000000002, abs=1e-09),
            pytest.approx(0.30000000000000004, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(0.5, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort2_own0_5_rj0p5_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=2)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.5
        damper._armed_until[LABEL] = clock.now + 0.5
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(0.15000000000000002, abs=1e-09),
            pytest.approx(0.30000000000000004, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(0.5, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort2_own0_5_rj0p75_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=2)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.75
        damper._armed_until[LABEL] = clock.now + 0.5
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(0.17500000000000002, abs=1e-09),
            pytest.approx(0.35000000000000003, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(0.5, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort2_own0_5_rj0p75_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=2)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.75
        damper._armed_until[LABEL] = clock.now + 0.5
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(0.17500000000000002, abs=1e-09),
            pytest.approx(0.35000000000000003, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(0.5, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort2_own0_5_rj1_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=2)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 1.0
        damper._armed_until[LABEL] = clock.now + 0.5
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [pytest.approx(0.2, abs=1e-09), pytest.approx(0.4, abs=1e-09)]
        assert clock.sleeps == [pytest.approx(0.5, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort2_own0_5_rj1_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=2)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 1.0
        damper._armed_until[LABEL] = clock.now + 0.5
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [pytest.approx(0.2, abs=1e-09), pytest.approx(0.4, abs=1e-09)]
        assert clock.sleeps == [pytest.approx(0.5, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort2_own1_5_rj0_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=2)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.0
        damper._armed_until[LABEL] = clock.now + 1.5
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [pytest.approx(0.1, abs=1e-09), pytest.approx(0.2, abs=1e-09)]
        assert clock.sleeps == [pytest.approx(1.5, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort2_own1_5_rj0_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=2)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.0
        damper._armed_until[LABEL] = clock.now + 1.5
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [pytest.approx(0.1, abs=1e-09), pytest.approx(0.2, abs=1e-09)]
        assert clock.sleeps == [pytest.approx(1.5, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort2_own1_5_rj0p25_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=2)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.25
        damper._armed_until[LABEL] = clock.now + 1.5
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [pytest.approx(0.125, abs=1e-09), pytest.approx(0.25, abs=1e-09)]
        assert clock.sleeps == [pytest.approx(1.5, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort2_own1_5_rj0p25_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=2)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.25
        damper._armed_until[LABEL] = clock.now + 1.5
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [pytest.approx(0.125, abs=1e-09), pytest.approx(0.25, abs=1e-09)]
        assert clock.sleeps == [pytest.approx(1.5, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort2_own1_5_rj0p5_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=2)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.5
        damper._armed_until[LABEL] = clock.now + 1.5
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(0.15000000000000002, abs=1e-09),
            pytest.approx(0.30000000000000004, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(1.5, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort2_own1_5_rj0p5_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=2)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.5
        damper._armed_until[LABEL] = clock.now + 1.5
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(0.15000000000000002, abs=1e-09),
            pytest.approx(0.30000000000000004, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(1.5, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort2_own1_5_rj0p75_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=2)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.75
        damper._armed_until[LABEL] = clock.now + 1.5
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(0.17500000000000002, abs=1e-09),
            pytest.approx(0.35000000000000003, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(1.5, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort2_own1_5_rj0p75_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=2)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.75
        damper._armed_until[LABEL] = clock.now + 1.5
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(0.17500000000000002, abs=1e-09),
            pytest.approx(0.35000000000000003, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(1.5, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort2_own1_5_rj1_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=2)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 1.0
        damper._armed_until[LABEL] = clock.now + 1.5
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [pytest.approx(0.2, abs=1e-09), pytest.approx(0.4, abs=1e-09)]
        assert clock.sleeps == [pytest.approx(1.5, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort2_own1_5_rj1_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=2)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 1.0
        damper._armed_until[LABEL] = clock.now + 1.5
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [pytest.approx(0.2, abs=1e-09), pytest.approx(0.4, abs=1e-09)]
        assert clock.sleeps == [pytest.approx(1.5, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort2_fleet0_3_rj0_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=2)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.0
        seed_label_doc_here(client, WALL0 + 0.3)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(0.4000000000465661, abs=1e-09),
            pytest.approx(0.5000000000465661, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(0.30000000004656613, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort2_fleet0_3_rj0_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=2)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.0
        seed_label_doc_here(client, WALL0 + 0.3)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(0.4000000000465661, abs=1e-09),
            pytest.approx(0.5000000000465661, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(0.30000000004656613, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort2_fleet0_3_rj0p25_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=2)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.25
        seed_label_doc_here(client, WALL0 + 0.3)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(0.42500000004656613, abs=1e-09),
            pytest.approx(0.5500000000465661, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(0.30000000004656613, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort2_fleet0_3_rj0p25_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=2)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.25
        seed_label_doc_here(client, WALL0 + 0.3)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(0.42500000004656613, abs=1e-09),
            pytest.approx(0.5500000000465661, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(0.30000000004656613, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort2_fleet0_3_rj0p5_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=2)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.5
        seed_label_doc_here(client, WALL0 + 0.3)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(0.45000000004656615, abs=1e-09),
            pytest.approx(0.6000000000465662, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(0.30000000004656613, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort2_fleet0_3_rj0p5_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=2)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.5
        seed_label_doc_here(client, WALL0 + 0.3)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(0.45000000004656615, abs=1e-09),
            pytest.approx(0.6000000000465662, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(0.30000000004656613, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort2_fleet0_3_rj0p75_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=2)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.75
        seed_label_doc_here(client, WALL0 + 0.3)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(0.4750000000465662, abs=1e-09),
            pytest.approx(0.6500000000465662, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(0.30000000004656613, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort2_fleet0_3_rj0p75_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=2)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.75
        seed_label_doc_here(client, WALL0 + 0.3)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(0.4750000000465662, abs=1e-09),
            pytest.approx(0.6500000000465662, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(0.30000000004656613, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort2_fleet0_3_rj1_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=2)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 1.0
        seed_label_doc_here(client, WALL0 + 0.3)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(0.5000000000465661, abs=1e-09),
            pytest.approx(0.7000000000465662, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(0.30000000004656613, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort2_fleet0_3_rj1_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=2)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 1.0
        seed_label_doc_here(client, WALL0 + 0.3)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(0.5000000000465661, abs=1e-09),
            pytest.approx(0.7000000000465662, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(0.30000000004656613, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort2_fleet2_0_rj0_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=2)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.0
        seed_label_doc_here(client, WALL0 + 2.0)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [pytest.approx(2.1, abs=1e-09), pytest.approx(2.2, abs=1e-09)]
        assert clock.sleeps == [pytest.approx(2.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort2_fleet2_0_rj0_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=2)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.0
        seed_label_doc_here(client, WALL0 + 2.0)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [pytest.approx(2.1, abs=1e-09), pytest.approx(2.2, abs=1e-09)]
        assert clock.sleeps == [pytest.approx(2.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort2_fleet2_0_rj0p25_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=2)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.25
        seed_label_doc_here(client, WALL0 + 2.0)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [pytest.approx(2.125, abs=1e-09), pytest.approx(2.25, abs=1e-09)]
        assert clock.sleeps == [pytest.approx(2.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort2_fleet2_0_rj0p25_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=2)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.25
        seed_label_doc_here(client, WALL0 + 2.0)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [pytest.approx(2.125, abs=1e-09), pytest.approx(2.25, abs=1e-09)]
        assert clock.sleeps == [pytest.approx(2.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort2_fleet2_0_rj0p5_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=2)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.5
        seed_label_doc_here(client, WALL0 + 2.0)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [pytest.approx(2.15, abs=1e-09), pytest.approx(2.3, abs=1e-09)]
        assert clock.sleeps == [pytest.approx(2.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort2_fleet2_0_rj0p5_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=2)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.5
        seed_label_doc_here(client, WALL0 + 2.0)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [pytest.approx(2.15, abs=1e-09), pytest.approx(2.3, abs=1e-09)]
        assert clock.sleeps == [pytest.approx(2.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort2_fleet2_0_rj0p75_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=2)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.75
        seed_label_doc_here(client, WALL0 + 2.0)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [pytest.approx(2.175, abs=1e-09), pytest.approx(2.35, abs=1e-09)]
        assert clock.sleeps == [pytest.approx(2.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort2_fleet2_0_rj0p75_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=2)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.75
        seed_label_doc_here(client, WALL0 + 2.0)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [pytest.approx(2.175, abs=1e-09), pytest.approx(2.35, abs=1e-09)]
        assert clock.sleeps == [pytest.approx(2.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort2_fleet2_0_rj1_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=2)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 1.0
        seed_label_doc_here(client, WALL0 + 2.0)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [pytest.approx(2.2, abs=1e-09), pytest.approx(2.4, abs=1e-09)]
        assert clock.sleeps == [pytest.approx(2.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort2_fleet2_0_rj1_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=2)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 1.0
        seed_label_doc_here(client, WALL0 + 2.0)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [pytest.approx(2.2, abs=1e-09), pytest.approx(2.4, abs=1e-09)]
        assert clock.sleeps == [pytest.approx(2.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort2_fleet3_9_rj0_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=2)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.0
        seed_label_doc_here(client, WALL0 + 3.9)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(4.000000000023283, abs=1e-09),
            pytest.approx(4.100000000023283, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(3.900000000023283, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort2_fleet3_9_rj0_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=2)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.0
        seed_label_doc_here(client, WALL0 + 3.9)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(4.000000000023283, abs=1e-09),
            pytest.approx(4.100000000023283, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(3.900000000023283, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort2_fleet3_9_rj0p25_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=2)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.25
        seed_label_doc_here(client, WALL0 + 3.9)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(4.025000000023283, abs=1e-09),
            pytest.approx(4.150000000023283, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(3.900000000023283, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort2_fleet3_9_rj0p25_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=2)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.25
        seed_label_doc_here(client, WALL0 + 3.9)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(4.025000000023283, abs=1e-09),
            pytest.approx(4.150000000023283, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(3.900000000023283, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort2_fleet3_9_rj0p5_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=2)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.5
        seed_label_doc_here(client, WALL0 + 3.9)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(4.050000000023283, abs=1e-09),
            pytest.approx(4.200000000023283, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(3.900000000023283, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort2_fleet3_9_rj0p5_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=2)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.5
        seed_label_doc_here(client, WALL0 + 3.9)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(4.050000000023283, abs=1e-09),
            pytest.approx(4.200000000023283, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(3.900000000023283, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort2_fleet3_9_rj0p75_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=2)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.75
        seed_label_doc_here(client, WALL0 + 3.9)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(4.075000000023283, abs=1e-09),
            pytest.approx(4.250000000023283, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(3.900000000023283, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort2_fleet3_9_rj0p75_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=2)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.75
        seed_label_doc_here(client, WALL0 + 3.9)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(4.075000000023283, abs=1e-09),
            pytest.approx(4.250000000023283, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(3.900000000023283, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort2_fleet3_9_rj1_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=2)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 1.0
        seed_label_doc_here(client, WALL0 + 3.9)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(4.100000000023283, abs=1e-09),
            pytest.approx(4.300000000023283, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(3.900000000023283, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort2_fleet3_9_rj1_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=2)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 1.0
        seed_label_doc_here(client, WALL0 + 3.9)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(4.100000000023283, abs=1e-09),
            pytest.approx(4.300000000023283, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(3.900000000023283, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort2_spill0_6_rj0_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=2)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.0
        seed_spill_here(client, WALL0 + 0.6)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(0.6999999999767169, abs=1e-09),
            pytest.approx(0.7999999999767169, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(0.5999999999767169, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort2_spill0_6_rj0_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=2)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.0
        seed_spill_here(client, WALL0 + 0.6)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(0.6999999999767169, abs=1e-09),
            pytest.approx(0.7999999999767169, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(0.5999999999767169, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort2_spill0_6_rj0p25_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=2)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.25
        seed_spill_here(client, WALL0 + 0.6)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(0.7249999999767169, abs=1e-09),
            pytest.approx(0.8499999999767169, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(0.5999999999767169, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort2_spill0_6_rj0p25_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=2)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.25
        seed_spill_here(client, WALL0 + 0.6)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(0.7249999999767169, abs=1e-09),
            pytest.approx(0.8499999999767169, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(0.5999999999767169, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort2_spill0_6_rj0p5_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=2)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.5
        seed_spill_here(client, WALL0 + 0.6)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(0.749999999976717, abs=1e-09),
            pytest.approx(0.899999999976717, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(0.5999999999767169, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort2_spill0_6_rj0p5_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=2)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.5
        seed_spill_here(client, WALL0 + 0.6)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(0.749999999976717, abs=1e-09),
            pytest.approx(0.899999999976717, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(0.5999999999767169, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort2_spill0_6_rj0p75_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=2)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.75
        seed_spill_here(client, WALL0 + 0.6)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(0.774999999976717, abs=1e-09),
            pytest.approx(0.949999999976717, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(0.5999999999767169, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort2_spill0_6_rj0p75_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=2)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.75
        seed_spill_here(client, WALL0 + 0.6)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(0.774999999976717, abs=1e-09),
            pytest.approx(0.949999999976717, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(0.5999999999767169, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort2_spill0_6_rj1_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=2)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 1.0
        seed_spill_here(client, WALL0 + 0.6)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(0.7999999999767169, abs=1e-09),
            pytest.approx(0.999999999976717, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(0.5999999999767169, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort2_spill0_6_rj1_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=2)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 1.0
        seed_spill_here(client, WALL0 + 0.6)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(0.7999999999767169, abs=1e-09),
            pytest.approx(0.999999999976717, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(0.5999999999767169, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort2_spill2_6_rj0_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=2)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.0
        seed_spill_here(client, WALL0 + 2.6)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [pytest.approx(1.1, abs=1e-09), pytest.approx(1.2, abs=1e-09)]
        assert clock.sleeps == [pytest.approx(1.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort2_spill2_6_rj0_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=2)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.0
        seed_spill_here(client, WALL0 + 2.6)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [pytest.approx(1.1, abs=1e-09), pytest.approx(1.2, abs=1e-09)]
        assert clock.sleeps == [pytest.approx(1.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort2_spill2_6_rj0p25_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=2)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.25
        seed_spill_here(client, WALL0 + 2.6)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [pytest.approx(1.125, abs=1e-09), pytest.approx(1.25, abs=1e-09)]
        assert clock.sleeps == [pytest.approx(1.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort2_spill2_6_rj0p25_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=2)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.25
        seed_spill_here(client, WALL0 + 2.6)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [pytest.approx(1.125, abs=1e-09), pytest.approx(1.25, abs=1e-09)]
        assert clock.sleeps == [pytest.approx(1.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort2_spill2_6_rj0p5_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=2)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.5
        seed_spill_here(client, WALL0 + 2.6)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [pytest.approx(1.15, abs=1e-09), pytest.approx(1.3, abs=1e-09)]
        assert clock.sleeps == [pytest.approx(1.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort2_spill2_6_rj0p5_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=2)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.5
        seed_spill_here(client, WALL0 + 2.6)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [pytest.approx(1.15, abs=1e-09), pytest.approx(1.3, abs=1e-09)]
        assert clock.sleeps == [pytest.approx(1.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort2_spill2_6_rj0p75_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=2)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.75
        seed_spill_here(client, WALL0 + 2.6)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [pytest.approx(1.175, abs=1e-09), pytest.approx(1.35, abs=1e-09)]
        assert clock.sleeps == [pytest.approx(1.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort2_spill2_6_rj0p75_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=2)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.75
        seed_spill_here(client, WALL0 + 2.6)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [pytest.approx(1.175, abs=1e-09), pytest.approx(1.35, abs=1e-09)]
        assert clock.sleeps == [pytest.approx(1.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort2_spill2_6_rj1_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=2)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 1.0
        seed_spill_here(client, WALL0 + 2.6)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [pytest.approx(1.2, abs=1e-09), pytest.approx(1.4, abs=1e-09)]
        assert clock.sleeps == [pytest.approx(1.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort2_spill2_6_rj1_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=2)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 1.0
        seed_spill_here(client, WALL0 + 2.6)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [pytest.approx(1.2, abs=1e-09), pytest.approx(1.4, abs=1e-09)]
        assert clock.sleeps == [pytest.approx(1.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort2_spill3_9_rj0_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=2)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.0
        seed_spill_here(client, WALL0 + 3.9)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [pytest.approx(1.1, abs=1e-09), pytest.approx(1.2, abs=1e-09)]
        assert clock.sleeps == [pytest.approx(1.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort2_spill3_9_rj0_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=2)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.0
        seed_spill_here(client, WALL0 + 3.9)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [pytest.approx(1.1, abs=1e-09), pytest.approx(1.2, abs=1e-09)]
        assert clock.sleeps == [pytest.approx(1.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort2_spill3_9_rj0p25_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=2)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.25
        seed_spill_here(client, WALL0 + 3.9)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [pytest.approx(1.125, abs=1e-09), pytest.approx(1.25, abs=1e-09)]
        assert clock.sleeps == [pytest.approx(1.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort2_spill3_9_rj0p25_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=2)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.25
        seed_spill_here(client, WALL0 + 3.9)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [pytest.approx(1.125, abs=1e-09), pytest.approx(1.25, abs=1e-09)]
        assert clock.sleeps == [pytest.approx(1.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort2_spill3_9_rj0p5_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=2)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.5
        seed_spill_here(client, WALL0 + 3.9)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [pytest.approx(1.15, abs=1e-09), pytest.approx(1.3, abs=1e-09)]
        assert clock.sleeps == [pytest.approx(1.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort2_spill3_9_rj0p5_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=2)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.5
        seed_spill_here(client, WALL0 + 3.9)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [pytest.approx(1.15, abs=1e-09), pytest.approx(1.3, abs=1e-09)]
        assert clock.sleeps == [pytest.approx(1.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort2_spill3_9_rj0p75_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=2)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.75
        seed_spill_here(client, WALL0 + 3.9)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [pytest.approx(1.175, abs=1e-09), pytest.approx(1.35, abs=1e-09)]
        assert clock.sleeps == [pytest.approx(1.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort2_spill3_9_rj0p75_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=2)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.75
        seed_spill_here(client, WALL0 + 3.9)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [pytest.approx(1.175, abs=1e-09), pytest.approx(1.35, abs=1e-09)]
        assert clock.sleeps == [pytest.approx(1.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort2_spill3_9_rj1_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=2)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 1.0
        seed_spill_here(client, WALL0 + 3.9)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [pytest.approx(1.2, abs=1e-09), pytest.approx(1.4, abs=1e-09)]
        assert clock.sleeps == [pytest.approx(1.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort2_spill3_9_rj1_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=2)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 1.0
        seed_spill_here(client, WALL0 + 3.9)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [pytest.approx(1.2, abs=1e-09), pytest.approx(1.4, abs=1e-09)]
        assert clock.sleeps == [pytest.approx(1.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort3_none_rj0_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=3)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.0
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(0.1, abs=1e-09),
            pytest.approx(0.2, abs=1e-09),
            pytest.approx(0.9, abs=1e-09),
        ]
        assert clock.sleeps == []
    finally:
        reset_registries()


def test_chain_abort3_none_rj0_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=3)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.0
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(0.1, abs=1e-09),
            pytest.approx(0.2, abs=1e-09),
            pytest.approx(1.275, abs=1e-09),
        ]
        assert clock.sleeps == []
    finally:
        reset_registries()


def test_chain_abort3_none_rj0p25_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=3)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.25
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(0.125, abs=1e-09),
            pytest.approx(0.25, abs=1e-09),
            pytest.approx(1.0, abs=1e-09),
        ]
        assert clock.sleeps == []
    finally:
        reset_registries()


def test_chain_abort3_none_rj0p25_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=3)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.25
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(0.125, abs=1e-09),
            pytest.approx(0.25, abs=1e-09),
            pytest.approx(1.375, abs=1e-09),
        ]
        assert clock.sleeps == []
    finally:
        reset_registries()


def test_chain_abort3_none_rj0p5_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=3)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.5
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(0.15000000000000002, abs=1e-09),
            pytest.approx(0.30000000000000004, abs=1e-09),
            pytest.approx(1.1, abs=1e-09),
        ]
        assert clock.sleeps == []
    finally:
        reset_registries()


def test_chain_abort3_none_rj0p5_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=3)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.5
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(0.15000000000000002, abs=1e-09),
            pytest.approx(0.30000000000000004, abs=1e-09),
            pytest.approx(1.475, abs=1e-09),
        ]
        assert clock.sleeps == []
    finally:
        reset_registries()


def test_chain_abort3_none_rj0p75_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=3)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.75
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(0.17500000000000002, abs=1e-09),
            pytest.approx(0.35000000000000003, abs=1e-09),
            pytest.approx(1.2000000000000002, abs=1e-09),
        ]
        assert clock.sleeps == []
    finally:
        reset_registries()


def test_chain_abort3_none_rj0p75_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=3)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.75
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(0.17500000000000002, abs=1e-09),
            pytest.approx(0.35000000000000003, abs=1e-09),
            pytest.approx(1.5750000000000002, abs=1e-09),
        ]
        assert clock.sleeps == []
    finally:
        reset_registries()


def test_chain_abort3_none_rj1_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=3)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 1.0
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(0.2, abs=1e-09),
            pytest.approx(0.4, abs=1e-09),
            pytest.approx(1.3, abs=1e-09),
        ]
        assert clock.sleeps == []
    finally:
        reset_registries()


def test_chain_abort3_none_rj1_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=3)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 1.0
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(0.2, abs=1e-09),
            pytest.approx(0.4, abs=1e-09),
            pytest.approx(1.675, abs=1e-09),
        ]
        assert clock.sleeps == []
    finally:
        reset_registries()


def test_chain_abort3_own0_5_rj0_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=3)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.0
        damper._armed_until[LABEL] = clock.now + 0.5
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(0.1, abs=1e-09),
            pytest.approx(0.2, abs=1e-09),
            pytest.approx(0.9, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(0.5, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort3_own0_5_rj0_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=3)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.0
        damper._armed_until[LABEL] = clock.now + 0.5
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(0.1, abs=1e-09),
            pytest.approx(0.2, abs=1e-09),
            pytest.approx(1.275, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(0.5, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort3_own0_5_rj0p25_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=3)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.25
        damper._armed_until[LABEL] = clock.now + 0.5
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(0.125, abs=1e-09),
            pytest.approx(0.25, abs=1e-09),
            pytest.approx(1.0, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(0.5, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort3_own0_5_rj0p25_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=3)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.25
        damper._armed_until[LABEL] = clock.now + 0.5
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(0.125, abs=1e-09),
            pytest.approx(0.25, abs=1e-09),
            pytest.approx(1.375, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(0.5, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort3_own0_5_rj0p5_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=3)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.5
        damper._armed_until[LABEL] = clock.now + 0.5
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(0.15000000000000002, abs=1e-09),
            pytest.approx(0.30000000000000004, abs=1e-09),
            pytest.approx(1.1, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(0.5, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort3_own0_5_rj0p5_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=3)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.5
        damper._armed_until[LABEL] = clock.now + 0.5
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(0.15000000000000002, abs=1e-09),
            pytest.approx(0.30000000000000004, abs=1e-09),
            pytest.approx(1.475, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(0.5, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort3_own0_5_rj0p75_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=3)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.75
        damper._armed_until[LABEL] = clock.now + 0.5
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(0.17500000000000002, abs=1e-09),
            pytest.approx(0.35000000000000003, abs=1e-09),
            pytest.approx(1.2000000000000002, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(0.5, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort3_own0_5_rj0p75_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=3)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.75
        damper._armed_until[LABEL] = clock.now + 0.5
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(0.17500000000000002, abs=1e-09),
            pytest.approx(0.35000000000000003, abs=1e-09),
            pytest.approx(1.5750000000000002, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(0.5, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort3_own0_5_rj1_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=3)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 1.0
        damper._armed_until[LABEL] = clock.now + 0.5
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(0.2, abs=1e-09),
            pytest.approx(0.4, abs=1e-09),
            pytest.approx(1.3, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(0.5, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort3_own0_5_rj1_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=3)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 1.0
        damper._armed_until[LABEL] = clock.now + 0.5
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(0.2, abs=1e-09),
            pytest.approx(0.4, abs=1e-09),
            pytest.approx(1.675, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(0.5, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort3_own1_5_rj0_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=3)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.0
        damper._armed_until[LABEL] = clock.now + 1.5
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(0.1, abs=1e-09),
            pytest.approx(0.2, abs=1e-09),
            pytest.approx(0.9, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(1.5, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort3_own1_5_rj0_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=3)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.0
        damper._armed_until[LABEL] = clock.now + 1.5
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(0.1, abs=1e-09),
            pytest.approx(0.2, abs=1e-09),
            pytest.approx(1.275, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(1.5, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort3_own1_5_rj0p25_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=3)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.25
        damper._armed_until[LABEL] = clock.now + 1.5
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(0.125, abs=1e-09),
            pytest.approx(0.25, abs=1e-09),
            pytest.approx(1.0, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(1.5, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort3_own1_5_rj0p25_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=3)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.25
        damper._armed_until[LABEL] = clock.now + 1.5
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(0.125, abs=1e-09),
            pytest.approx(0.25, abs=1e-09),
            pytest.approx(1.375, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(1.5, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort3_own1_5_rj0p5_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=3)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.5
        damper._armed_until[LABEL] = clock.now + 1.5
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(0.15000000000000002, abs=1e-09),
            pytest.approx(0.30000000000000004, abs=1e-09),
            pytest.approx(1.1, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(1.5, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort3_own1_5_rj0p5_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=3)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.5
        damper._armed_until[LABEL] = clock.now + 1.5
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(0.15000000000000002, abs=1e-09),
            pytest.approx(0.30000000000000004, abs=1e-09),
            pytest.approx(1.475, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(1.5, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort3_own1_5_rj0p75_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=3)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.75
        damper._armed_until[LABEL] = clock.now + 1.5
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(0.17500000000000002, abs=1e-09),
            pytest.approx(0.35000000000000003, abs=1e-09),
            pytest.approx(1.2000000000000002, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(1.5, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort3_own1_5_rj0p75_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=3)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.75
        damper._armed_until[LABEL] = clock.now + 1.5
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(0.17500000000000002, abs=1e-09),
            pytest.approx(0.35000000000000003, abs=1e-09),
            pytest.approx(1.5750000000000002, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(1.5, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort3_own1_5_rj1_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=3)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 1.0
        damper._armed_until[LABEL] = clock.now + 1.5
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(0.2, abs=1e-09),
            pytest.approx(0.4, abs=1e-09),
            pytest.approx(1.3, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(1.5, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort3_own1_5_rj1_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=3)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 1.0
        damper._armed_until[LABEL] = clock.now + 1.5
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(0.2, abs=1e-09),
            pytest.approx(0.4, abs=1e-09),
            pytest.approx(1.675, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(1.5, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort3_fleet0_3_rj0_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=3)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.0
        seed_label_doc_here(client, WALL0 + 0.3)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(0.4000000000465661, abs=1e-09),
            pytest.approx(0.5000000000465661, abs=1e-09),
            pytest.approx(0.9, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(0.30000000004656613, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort3_fleet0_3_rj0_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=3)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.0
        seed_label_doc_here(client, WALL0 + 0.3)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(0.4000000000465661, abs=1e-09),
            pytest.approx(0.5000000000465661, abs=1e-09),
            pytest.approx(1.275, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(0.30000000004656613, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort3_fleet0_3_rj0p25_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=3)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.25
        seed_label_doc_here(client, WALL0 + 0.3)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(0.42500000004656613, abs=1e-09),
            pytest.approx(0.5500000000465661, abs=1e-09),
            pytest.approx(1.0, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(0.30000000004656613, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort3_fleet0_3_rj0p25_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=3)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.25
        seed_label_doc_here(client, WALL0 + 0.3)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(0.42500000004656613, abs=1e-09),
            pytest.approx(0.5500000000465661, abs=1e-09),
            pytest.approx(1.375, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(0.30000000004656613, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort3_fleet0_3_rj0p5_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=3)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.5
        seed_label_doc_here(client, WALL0 + 0.3)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(0.45000000004656615, abs=1e-09),
            pytest.approx(0.6000000000465662, abs=1e-09),
            pytest.approx(1.1, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(0.30000000004656613, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort3_fleet0_3_rj0p5_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=3)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.5
        seed_label_doc_here(client, WALL0 + 0.3)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(0.45000000004656615, abs=1e-09),
            pytest.approx(0.6000000000465662, abs=1e-09),
            pytest.approx(1.475, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(0.30000000004656613, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort3_fleet0_3_rj0p75_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=3)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.75
        seed_label_doc_here(client, WALL0 + 0.3)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(0.4750000000465662, abs=1e-09),
            pytest.approx(0.6500000000465662, abs=1e-09),
            pytest.approx(1.2000000000000002, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(0.30000000004656613, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort3_fleet0_3_rj0p75_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=3)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.75
        seed_label_doc_here(client, WALL0 + 0.3)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(0.4750000000465662, abs=1e-09),
            pytest.approx(0.6500000000465662, abs=1e-09),
            pytest.approx(1.5750000000000002, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(0.30000000004656613, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort3_fleet0_3_rj1_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=3)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 1.0
        seed_label_doc_here(client, WALL0 + 0.3)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(0.5000000000465661, abs=1e-09),
            pytest.approx(0.7000000000465662, abs=1e-09),
            pytest.approx(1.3, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(0.30000000004656613, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort3_fleet0_3_rj1_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=3)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 1.0
        seed_label_doc_here(client, WALL0 + 0.3)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(0.5000000000465661, abs=1e-09),
            pytest.approx(0.7000000000465662, abs=1e-09),
            pytest.approx(1.675, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(0.30000000004656613, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort3_fleet2_0_rj0_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=3)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.0
        seed_label_doc_here(client, WALL0 + 2.0)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(2.1, abs=1e-09),
            pytest.approx(2.2, abs=1e-09),
            pytest.approx(2.4, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(2.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort3_fleet2_0_rj0_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=3)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.0
        seed_label_doc_here(client, WALL0 + 2.0)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(2.1, abs=1e-09),
            pytest.approx(2.2, abs=1e-09),
            pytest.approx(2.4, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(2.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort3_fleet2_0_rj0p25_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=3)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.25
        seed_label_doc_here(client, WALL0 + 2.0)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(2.125, abs=1e-09),
            pytest.approx(2.25, abs=1e-09),
            pytest.approx(2.5, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(2.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort3_fleet2_0_rj0p25_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=3)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.25
        seed_label_doc_here(client, WALL0 + 2.0)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(2.125, abs=1e-09),
            pytest.approx(2.25, abs=1e-09),
            pytest.approx(2.5, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(2.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort3_fleet2_0_rj0p5_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=3)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.5
        seed_label_doc_here(client, WALL0 + 2.0)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(2.15, abs=1e-09),
            pytest.approx(2.3, abs=1e-09),
            pytest.approx(2.6, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(2.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort3_fleet2_0_rj0p5_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=3)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.5
        seed_label_doc_here(client, WALL0 + 2.0)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(2.15, abs=1e-09),
            pytest.approx(2.3, abs=1e-09),
            pytest.approx(2.6, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(2.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort3_fleet2_0_rj0p75_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=3)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.75
        seed_label_doc_here(client, WALL0 + 2.0)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(2.175, abs=1e-09),
            pytest.approx(2.35, abs=1e-09),
            pytest.approx(2.7, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(2.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort3_fleet2_0_rj0p75_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=3)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.75
        seed_label_doc_here(client, WALL0 + 2.0)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(2.175, abs=1e-09),
            pytest.approx(2.35, abs=1e-09),
            pytest.approx(2.7, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(2.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort3_fleet2_0_rj1_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=3)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 1.0
        seed_label_doc_here(client, WALL0 + 2.0)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(2.2, abs=1e-09),
            pytest.approx(2.4, abs=1e-09),
            pytest.approx(2.8, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(2.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort3_fleet2_0_rj1_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=3)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 1.0
        seed_label_doc_here(client, WALL0 + 2.0)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(2.2, abs=1e-09),
            pytest.approx(2.4, abs=1e-09),
            pytest.approx(2.8, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(2.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort3_fleet3_9_rj0_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=3)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.0
        seed_label_doc_here(client, WALL0 + 3.9)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(4.000000000023283, abs=1e-09),
            pytest.approx(4.100000000023283, abs=1e-09),
            pytest.approx(4.300000000023283, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(3.900000000023283, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort3_fleet3_9_rj0_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=3)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.0
        seed_label_doc_here(client, WALL0 + 3.9)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(4.000000000023283, abs=1e-09),
            pytest.approx(4.100000000023283, abs=1e-09),
            pytest.approx(4.300000000023283, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(3.900000000023283, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort3_fleet3_9_rj0p25_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=3)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.25
        seed_label_doc_here(client, WALL0 + 3.9)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(4.025000000023283, abs=1e-09),
            pytest.approx(4.150000000023283, abs=1e-09),
            pytest.approx(4.400000000023283, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(3.900000000023283, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort3_fleet3_9_rj0p25_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=3)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.25
        seed_label_doc_here(client, WALL0 + 3.9)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(4.025000000023283, abs=1e-09),
            pytest.approx(4.150000000023283, abs=1e-09),
            pytest.approx(4.400000000023283, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(3.900000000023283, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort3_fleet3_9_rj0p5_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=3)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.5
        seed_label_doc_here(client, WALL0 + 3.9)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(4.050000000023283, abs=1e-09),
            pytest.approx(4.200000000023283, abs=1e-09),
            pytest.approx(4.500000000023283, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(3.900000000023283, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort3_fleet3_9_rj0p5_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=3)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.5
        seed_label_doc_here(client, WALL0 + 3.9)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(4.050000000023283, abs=1e-09),
            pytest.approx(4.200000000023283, abs=1e-09),
            pytest.approx(4.500000000023283, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(3.900000000023283, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort3_fleet3_9_rj0p75_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=3)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.75
        seed_label_doc_here(client, WALL0 + 3.9)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(4.075000000023283, abs=1e-09),
            pytest.approx(4.250000000023283, abs=1e-09),
            pytest.approx(4.600000000023283, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(3.900000000023283, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort3_fleet3_9_rj0p75_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=3)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.75
        seed_label_doc_here(client, WALL0 + 3.9)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(4.075000000023283, abs=1e-09),
            pytest.approx(4.250000000023283, abs=1e-09),
            pytest.approx(4.600000000023283, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(3.900000000023283, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort3_fleet3_9_rj1_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=3)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 1.0
        seed_label_doc_here(client, WALL0 + 3.9)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(4.100000000023283, abs=1e-09),
            pytest.approx(4.300000000023283, abs=1e-09),
            pytest.approx(4.700000000023283, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(3.900000000023283, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort3_fleet3_9_rj1_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=3)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 1.0
        seed_label_doc_here(client, WALL0 + 3.9)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(4.100000000023283, abs=1e-09),
            pytest.approx(4.300000000023283, abs=1e-09),
            pytest.approx(4.700000000023283, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(3.900000000023283, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort3_spill0_6_rj0_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=3)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.0
        seed_spill_here(client, WALL0 + 0.6)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(0.6999999999767169, abs=1e-09),
            pytest.approx(0.7999999999767169, abs=1e-09),
            pytest.approx(0.999999999976717, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(0.5999999999767169, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort3_spill0_6_rj0_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=3)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.0
        seed_spill_here(client, WALL0 + 0.6)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(0.6999999999767169, abs=1e-09),
            pytest.approx(0.7999999999767169, abs=1e-09),
            pytest.approx(1.275, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(0.5999999999767169, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort3_spill0_6_rj0p25_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=3)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.25
        seed_spill_here(client, WALL0 + 0.6)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(0.7249999999767169, abs=1e-09),
            pytest.approx(0.8499999999767169, abs=1e-09),
            pytest.approx(1.099999999976717, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(0.5999999999767169, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort3_spill0_6_rj0p25_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=3)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.25
        seed_spill_here(client, WALL0 + 0.6)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(0.7249999999767169, abs=1e-09),
            pytest.approx(0.8499999999767169, abs=1e-09),
            pytest.approx(1.375, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(0.5999999999767169, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort3_spill0_6_rj0p5_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=3)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.5
        seed_spill_here(client, WALL0 + 0.6)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(0.749999999976717, abs=1e-09),
            pytest.approx(0.899999999976717, abs=1e-09),
            pytest.approx(1.199999999976717, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(0.5999999999767169, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort3_spill0_6_rj0p5_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=3)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.5
        seed_spill_here(client, WALL0 + 0.6)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(0.749999999976717, abs=1e-09),
            pytest.approx(0.899999999976717, abs=1e-09),
            pytest.approx(1.475, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(0.5999999999767169, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort3_spill0_6_rj0p75_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=3)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.75
        seed_spill_here(client, WALL0 + 0.6)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(0.774999999976717, abs=1e-09),
            pytest.approx(0.949999999976717, abs=1e-09),
            pytest.approx(1.2999999999767171, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(0.5999999999767169, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort3_spill0_6_rj0p75_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=3)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.75
        seed_spill_here(client, WALL0 + 0.6)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(0.774999999976717, abs=1e-09),
            pytest.approx(0.949999999976717, abs=1e-09),
            pytest.approx(1.5750000000000002, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(0.5999999999767169, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort3_spill0_6_rj1_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=3)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 1.0
        seed_spill_here(client, WALL0 + 0.6)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(0.7999999999767169, abs=1e-09),
            pytest.approx(0.999999999976717, abs=1e-09),
            pytest.approx(1.399999999976717, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(0.5999999999767169, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort3_spill0_6_rj1_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=3)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 1.0
        seed_spill_here(client, WALL0 + 0.6)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(0.7999999999767169, abs=1e-09),
            pytest.approx(0.999999999976717, abs=1e-09),
            pytest.approx(1.675, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(0.5999999999767169, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort3_spill2_6_rj0_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=3)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.0
        seed_spill_here(client, WALL0 + 2.6)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(1.1, abs=1e-09),
            pytest.approx(1.2, abs=1e-09),
            pytest.approx(1.4, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(1.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort3_spill2_6_rj0_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=3)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.0
        seed_spill_here(client, WALL0 + 2.6)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(1.1, abs=1e-09),
            pytest.approx(1.2, abs=1e-09),
            pytest.approx(1.4, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(1.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort3_spill2_6_rj0p25_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=3)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.25
        seed_spill_here(client, WALL0 + 2.6)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(1.125, abs=1e-09),
            pytest.approx(1.25, abs=1e-09),
            pytest.approx(1.5, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(1.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort3_spill2_6_rj0p25_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=3)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.25
        seed_spill_here(client, WALL0 + 2.6)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(1.125, abs=1e-09),
            pytest.approx(1.25, abs=1e-09),
            pytest.approx(1.5, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(1.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort3_spill2_6_rj0p5_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=3)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.5
        seed_spill_here(client, WALL0 + 2.6)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(1.15, abs=1e-09),
            pytest.approx(1.3, abs=1e-09),
            pytest.approx(1.6, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(1.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort3_spill2_6_rj0p5_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=3)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.5
        seed_spill_here(client, WALL0 + 2.6)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(1.15, abs=1e-09),
            pytest.approx(1.3, abs=1e-09),
            pytest.approx(1.6, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(1.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort3_spill2_6_rj0p75_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=3)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.75
        seed_spill_here(client, WALL0 + 2.6)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(1.175, abs=1e-09),
            pytest.approx(1.35, abs=1e-09),
            pytest.approx(1.7000000000000002, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(1.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort3_spill2_6_rj0p75_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=3)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.75
        seed_spill_here(client, WALL0 + 2.6)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(1.175, abs=1e-09),
            pytest.approx(1.35, abs=1e-09),
            pytest.approx(1.7000000000000002, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(1.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort3_spill2_6_rj1_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=3)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 1.0
        seed_spill_here(client, WALL0 + 2.6)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(1.2, abs=1e-09),
            pytest.approx(1.4, abs=1e-09),
            pytest.approx(1.8, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(1.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort3_spill2_6_rj1_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=3)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 1.0
        seed_spill_here(client, WALL0 + 2.6)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(1.2, abs=1e-09),
            pytest.approx(1.4, abs=1e-09),
            pytest.approx(1.8, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(1.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort3_spill3_9_rj0_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=3)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.0
        seed_spill_here(client, WALL0 + 3.9)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(1.1, abs=1e-09),
            pytest.approx(1.2, abs=1e-09),
            pytest.approx(1.4, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(1.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort3_spill3_9_rj0_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=3)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.0
        seed_spill_here(client, WALL0 + 3.9)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(1.1, abs=1e-09),
            pytest.approx(1.2, abs=1e-09),
            pytest.approx(1.4, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(1.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort3_spill3_9_rj0p25_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=3)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.25
        seed_spill_here(client, WALL0 + 3.9)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(1.125, abs=1e-09),
            pytest.approx(1.25, abs=1e-09),
            pytest.approx(1.5, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(1.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort3_spill3_9_rj0p25_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=3)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.25
        seed_spill_here(client, WALL0 + 3.9)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(1.125, abs=1e-09),
            pytest.approx(1.25, abs=1e-09),
            pytest.approx(1.5, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(1.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort3_spill3_9_rj0p5_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=3)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.5
        seed_spill_here(client, WALL0 + 3.9)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(1.15, abs=1e-09),
            pytest.approx(1.3, abs=1e-09),
            pytest.approx(1.6, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(1.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort3_spill3_9_rj0p5_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=3)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.5
        seed_spill_here(client, WALL0 + 3.9)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(1.15, abs=1e-09),
            pytest.approx(1.3, abs=1e-09),
            pytest.approx(1.6, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(1.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort3_spill3_9_rj0p75_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=3)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.75
        seed_spill_here(client, WALL0 + 3.9)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(1.175, abs=1e-09),
            pytest.approx(1.35, abs=1e-09),
            pytest.approx(1.7000000000000002, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(1.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort3_spill3_9_rj0p75_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=3)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.75
        seed_spill_here(client, WALL0 + 3.9)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(1.175, abs=1e-09),
            pytest.approx(1.35, abs=1e-09),
            pytest.approx(1.7000000000000002, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(1.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort3_spill3_9_rj1_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=3)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 1.0
        seed_spill_here(client, WALL0 + 3.9)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(1.2, abs=1e-09),
            pytest.approx(1.4, abs=1e-09),
            pytest.approx(1.8, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(1.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort3_spill3_9_rj1_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=3)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 1.0
        seed_spill_here(client, WALL0 + 3.9)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(1.2, abs=1e-09),
            pytest.approx(1.4, abs=1e-09),
            pytest.approx(1.8, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(1.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort4_none_rj0_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=4)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.0
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(0.1, abs=1e-09),
            pytest.approx(0.2, abs=1e-09),
            pytest.approx(0.9, abs=1e-09),
            pytest.approx(1.8, abs=1e-09),
        ]
        assert clock.sleeps == []
    finally:
        reset_registries()


def test_chain_abort4_none_rj0_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=4)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.0
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(0.1, abs=1e-09),
            pytest.approx(0.2, abs=1e-09),
            pytest.approx(1.275, abs=1e-09),
            pytest.approx(2.55, abs=1e-09),
        ]
        assert clock.sleeps == []
    finally:
        reset_registries()


def test_chain_abort4_none_rj0p25_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=4)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.25
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(0.125, abs=1e-09),
            pytest.approx(0.25, abs=1e-09),
            pytest.approx(1.0, abs=1e-09),
            pytest.approx(2.0, abs=1e-09),
        ]
        assert clock.sleeps == []
    finally:
        reset_registries()


def test_chain_abort4_none_rj0p25_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=4)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.25
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(0.125, abs=1e-09),
            pytest.approx(0.25, abs=1e-09),
            pytest.approx(1.375, abs=1e-09),
            pytest.approx(2.75, abs=1e-09),
        ]
        assert clock.sleeps == []
    finally:
        reset_registries()


def test_chain_abort4_none_rj0p5_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=4)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.5
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(0.15000000000000002, abs=1e-09),
            pytest.approx(0.30000000000000004, abs=1e-09),
            pytest.approx(1.1, abs=1e-09),
            pytest.approx(2.2, abs=1e-09),
        ]
        assert clock.sleeps == []
    finally:
        reset_registries()


def test_chain_abort4_none_rj0p5_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=4)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.5
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(0.15000000000000002, abs=1e-09),
            pytest.approx(0.30000000000000004, abs=1e-09),
            pytest.approx(1.475, abs=1e-09),
            pytest.approx(2.95, abs=1e-09),
        ]
        assert clock.sleeps == []
    finally:
        reset_registries()


def test_chain_abort4_none_rj0p75_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=4)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.75
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(0.17500000000000002, abs=1e-09),
            pytest.approx(0.35000000000000003, abs=1e-09),
            pytest.approx(1.2000000000000002, abs=1e-09),
            pytest.approx(2.4000000000000004, abs=1e-09),
        ]
        assert clock.sleeps == []
    finally:
        reset_registries()


def test_chain_abort4_none_rj0p75_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=4)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.75
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(0.17500000000000002, abs=1e-09),
            pytest.approx(0.35000000000000003, abs=1e-09),
            pytest.approx(1.5750000000000002, abs=1e-09),
            pytest.approx(3.1500000000000004, abs=1e-09),
        ]
        assert clock.sleeps == []
    finally:
        reset_registries()


def test_chain_abort4_none_rj1_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=4)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 1.0
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(0.2, abs=1e-09),
            pytest.approx(0.4, abs=1e-09),
            pytest.approx(1.3, abs=1e-09),
            pytest.approx(2.6, abs=1e-09),
        ]
        assert clock.sleeps == []
    finally:
        reset_registries()


def test_chain_abort4_none_rj1_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=4)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 1.0
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(0.2, abs=1e-09),
            pytest.approx(0.4, abs=1e-09),
            pytest.approx(1.675, abs=1e-09),
            pytest.approx(3.35, abs=1e-09),
        ]
        assert clock.sleeps == []
    finally:
        reset_registries()


def test_chain_abort4_own0_5_rj0_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=4)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.0
        damper._armed_until[LABEL] = clock.now + 0.5
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(0.1, abs=1e-09),
            pytest.approx(0.2, abs=1e-09),
            pytest.approx(0.9, abs=1e-09),
            pytest.approx(1.8, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(0.5, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort4_own0_5_rj0_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=4)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.0
        damper._armed_until[LABEL] = clock.now + 0.5
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(0.1, abs=1e-09),
            pytest.approx(0.2, abs=1e-09),
            pytest.approx(1.275, abs=1e-09),
            pytest.approx(2.55, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(0.5, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort4_own0_5_rj0p25_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=4)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.25
        damper._armed_until[LABEL] = clock.now + 0.5
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(0.125, abs=1e-09),
            pytest.approx(0.25, abs=1e-09),
            pytest.approx(1.0, abs=1e-09),
            pytest.approx(2.0, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(0.5, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort4_own0_5_rj0p25_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=4)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.25
        damper._armed_until[LABEL] = clock.now + 0.5
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(0.125, abs=1e-09),
            pytest.approx(0.25, abs=1e-09),
            pytest.approx(1.375, abs=1e-09),
            pytest.approx(2.75, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(0.5, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort4_own0_5_rj0p5_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=4)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.5
        damper._armed_until[LABEL] = clock.now + 0.5
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(0.15000000000000002, abs=1e-09),
            pytest.approx(0.30000000000000004, abs=1e-09),
            pytest.approx(1.1, abs=1e-09),
            pytest.approx(2.2, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(0.5, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort4_own0_5_rj0p5_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=4)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.5
        damper._armed_until[LABEL] = clock.now + 0.5
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(0.15000000000000002, abs=1e-09),
            pytest.approx(0.30000000000000004, abs=1e-09),
            pytest.approx(1.475, abs=1e-09),
            pytest.approx(2.95, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(0.5, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort4_own0_5_rj0p75_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=4)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.75
        damper._armed_until[LABEL] = clock.now + 0.5
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(0.17500000000000002, abs=1e-09),
            pytest.approx(0.35000000000000003, abs=1e-09),
            pytest.approx(1.2000000000000002, abs=1e-09),
            pytest.approx(2.4000000000000004, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(0.5, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort4_own0_5_rj0p75_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=4)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.75
        damper._armed_until[LABEL] = clock.now + 0.5
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(0.17500000000000002, abs=1e-09),
            pytest.approx(0.35000000000000003, abs=1e-09),
            pytest.approx(1.5750000000000002, abs=1e-09),
            pytest.approx(3.1500000000000004, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(0.5, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort4_own0_5_rj1_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=4)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 1.0
        damper._armed_until[LABEL] = clock.now + 0.5
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(0.2, abs=1e-09),
            pytest.approx(0.4, abs=1e-09),
            pytest.approx(1.3, abs=1e-09),
            pytest.approx(2.6, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(0.5, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort4_own0_5_rj1_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=4)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 1.0
        damper._armed_until[LABEL] = clock.now + 0.5
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(0.2, abs=1e-09),
            pytest.approx(0.4, abs=1e-09),
            pytest.approx(1.675, abs=1e-09),
            pytest.approx(3.35, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(0.5, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort4_own1_5_rj0_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=4)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.0
        damper._armed_until[LABEL] = clock.now + 1.5
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(0.1, abs=1e-09),
            pytest.approx(0.2, abs=1e-09),
            pytest.approx(0.9, abs=1e-09),
            pytest.approx(1.8, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(1.5, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort4_own1_5_rj0_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=4)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.0
        damper._armed_until[LABEL] = clock.now + 1.5
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(0.1, abs=1e-09),
            pytest.approx(0.2, abs=1e-09),
            pytest.approx(1.275, abs=1e-09),
            pytest.approx(2.55, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(1.5, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort4_own1_5_rj0p25_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=4)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.25
        damper._armed_until[LABEL] = clock.now + 1.5
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(0.125, abs=1e-09),
            pytest.approx(0.25, abs=1e-09),
            pytest.approx(1.0, abs=1e-09),
            pytest.approx(2.0, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(1.5, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort4_own1_5_rj0p25_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=4)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.25
        damper._armed_until[LABEL] = clock.now + 1.5
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(0.125, abs=1e-09),
            pytest.approx(0.25, abs=1e-09),
            pytest.approx(1.375, abs=1e-09),
            pytest.approx(2.75, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(1.5, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort4_own1_5_rj0p5_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=4)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.5
        damper._armed_until[LABEL] = clock.now + 1.5
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(0.15000000000000002, abs=1e-09),
            pytest.approx(0.30000000000000004, abs=1e-09),
            pytest.approx(1.1, abs=1e-09),
            pytest.approx(2.2, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(1.5, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort4_own1_5_rj0p5_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=4)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.5
        damper._armed_until[LABEL] = clock.now + 1.5
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(0.15000000000000002, abs=1e-09),
            pytest.approx(0.30000000000000004, abs=1e-09),
            pytest.approx(1.475, abs=1e-09),
            pytest.approx(2.95, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(1.5, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort4_own1_5_rj0p75_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=4)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.75
        damper._armed_until[LABEL] = clock.now + 1.5
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(0.17500000000000002, abs=1e-09),
            pytest.approx(0.35000000000000003, abs=1e-09),
            pytest.approx(1.2000000000000002, abs=1e-09),
            pytest.approx(2.4000000000000004, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(1.5, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort4_own1_5_rj0p75_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=4)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.75
        damper._armed_until[LABEL] = clock.now + 1.5
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(0.17500000000000002, abs=1e-09),
            pytest.approx(0.35000000000000003, abs=1e-09),
            pytest.approx(1.5750000000000002, abs=1e-09),
            pytest.approx(3.1500000000000004, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(1.5, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort4_own1_5_rj1_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=4)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 1.0
        damper._armed_until[LABEL] = clock.now + 1.5
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(0.2, abs=1e-09),
            pytest.approx(0.4, abs=1e-09),
            pytest.approx(1.3, abs=1e-09),
            pytest.approx(2.6, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(1.5, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort4_own1_5_rj1_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=4)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 1.0
        damper._armed_until[LABEL] = clock.now + 1.5
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(0.2, abs=1e-09),
            pytest.approx(0.4, abs=1e-09),
            pytest.approx(1.675, abs=1e-09),
            pytest.approx(3.35, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(1.5, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort4_fleet0_3_rj0_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=4)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.0
        seed_label_doc_here(client, WALL0 + 0.3)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(0.4000000000465661, abs=1e-09),
            pytest.approx(0.5000000000465661, abs=1e-09),
            pytest.approx(0.9, abs=1e-09),
            pytest.approx(1.8, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(0.30000000004656613, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort4_fleet0_3_rj0_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=4)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.0
        seed_label_doc_here(client, WALL0 + 0.3)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(0.4000000000465661, abs=1e-09),
            pytest.approx(0.5000000000465661, abs=1e-09),
            pytest.approx(1.275, abs=1e-09),
            pytest.approx(2.55, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(0.30000000004656613, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort4_fleet0_3_rj0p25_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=4)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.25
        seed_label_doc_here(client, WALL0 + 0.3)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(0.42500000004656613, abs=1e-09),
            pytest.approx(0.5500000000465661, abs=1e-09),
            pytest.approx(1.0, abs=1e-09),
            pytest.approx(2.0, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(0.30000000004656613, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort4_fleet0_3_rj0p25_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=4)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.25
        seed_label_doc_here(client, WALL0 + 0.3)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(0.42500000004656613, abs=1e-09),
            pytest.approx(0.5500000000465661, abs=1e-09),
            pytest.approx(1.375, abs=1e-09),
            pytest.approx(2.75, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(0.30000000004656613, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort4_fleet0_3_rj0p5_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=4)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.5
        seed_label_doc_here(client, WALL0 + 0.3)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(0.45000000004656615, abs=1e-09),
            pytest.approx(0.6000000000465662, abs=1e-09),
            pytest.approx(1.1, abs=1e-09),
            pytest.approx(2.2, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(0.30000000004656613, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort4_fleet0_3_rj0p5_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=4)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.5
        seed_label_doc_here(client, WALL0 + 0.3)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(0.45000000004656615, abs=1e-09),
            pytest.approx(0.6000000000465662, abs=1e-09),
            pytest.approx(1.475, abs=1e-09),
            pytest.approx(2.95, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(0.30000000004656613, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort4_fleet0_3_rj0p75_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=4)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.75
        seed_label_doc_here(client, WALL0 + 0.3)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(0.4750000000465662, abs=1e-09),
            pytest.approx(0.6500000000465662, abs=1e-09),
            pytest.approx(1.2000000000000002, abs=1e-09),
            pytest.approx(2.4000000000000004, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(0.30000000004656613, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort4_fleet0_3_rj0p75_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=4)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.75
        seed_label_doc_here(client, WALL0 + 0.3)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(0.4750000000465662, abs=1e-09),
            pytest.approx(0.6500000000465662, abs=1e-09),
            pytest.approx(1.5750000000000002, abs=1e-09),
            pytest.approx(3.1500000000000004, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(0.30000000004656613, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort4_fleet0_3_rj1_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=4)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 1.0
        seed_label_doc_here(client, WALL0 + 0.3)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(0.5000000000465661, abs=1e-09),
            pytest.approx(0.7000000000465662, abs=1e-09),
            pytest.approx(1.3, abs=1e-09),
            pytest.approx(2.6, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(0.30000000004656613, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort4_fleet0_3_rj1_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=4)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 1.0
        seed_label_doc_here(client, WALL0 + 0.3)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(0.5000000000465661, abs=1e-09),
            pytest.approx(0.7000000000465662, abs=1e-09),
            pytest.approx(1.675, abs=1e-09),
            pytest.approx(3.35, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(0.30000000004656613, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort4_fleet2_0_rj0_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=4)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.0
        seed_label_doc_here(client, WALL0 + 2.0)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(2.1, abs=1e-09),
            pytest.approx(2.2, abs=1e-09),
            pytest.approx(2.4, abs=1e-09),
            pytest.approx(2.8, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(2.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort4_fleet2_0_rj0_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=4)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.0
        seed_label_doc_here(client, WALL0 + 2.0)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(2.1, abs=1e-09),
            pytest.approx(2.2, abs=1e-09),
            pytest.approx(2.4, abs=1e-09),
            pytest.approx(2.8, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(2.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort4_fleet2_0_rj0p25_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=4)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.25
        seed_label_doc_here(client, WALL0 + 2.0)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(2.125, abs=1e-09),
            pytest.approx(2.25, abs=1e-09),
            pytest.approx(2.5, abs=1e-09),
            pytest.approx(3.0, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(2.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort4_fleet2_0_rj0p25_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=4)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.25
        seed_label_doc_here(client, WALL0 + 2.0)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(2.125, abs=1e-09),
            pytest.approx(2.25, abs=1e-09),
            pytest.approx(2.5, abs=1e-09),
            pytest.approx(3.0, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(2.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort4_fleet2_0_rj0p5_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=4)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.5
        seed_label_doc_here(client, WALL0 + 2.0)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(2.15, abs=1e-09),
            pytest.approx(2.3, abs=1e-09),
            pytest.approx(2.6, abs=1e-09),
            pytest.approx(3.2, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(2.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort4_fleet2_0_rj0p5_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=4)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.5
        seed_label_doc_here(client, WALL0 + 2.0)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(2.15, abs=1e-09),
            pytest.approx(2.3, abs=1e-09),
            pytest.approx(2.6, abs=1e-09),
            pytest.approx(3.2, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(2.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort4_fleet2_0_rj0p75_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=4)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.75
        seed_label_doc_here(client, WALL0 + 2.0)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(2.175, abs=1e-09),
            pytest.approx(2.35, abs=1e-09),
            pytest.approx(2.7, abs=1e-09),
            pytest.approx(3.4000000000000004, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(2.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort4_fleet2_0_rj0p75_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=4)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.75
        seed_label_doc_here(client, WALL0 + 2.0)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(2.175, abs=1e-09),
            pytest.approx(2.35, abs=1e-09),
            pytest.approx(2.7, abs=1e-09),
            pytest.approx(3.4000000000000004, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(2.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort4_fleet2_0_rj1_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=4)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 1.0
        seed_label_doc_here(client, WALL0 + 2.0)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(2.2, abs=1e-09),
            pytest.approx(2.4, abs=1e-09),
            pytest.approx(2.8, abs=1e-09),
            pytest.approx(3.6, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(2.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort4_fleet2_0_rj1_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=4)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 1.0
        seed_label_doc_here(client, WALL0 + 2.0)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(2.2, abs=1e-09),
            pytest.approx(2.4, abs=1e-09),
            pytest.approx(2.8, abs=1e-09),
            pytest.approx(3.6, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(2.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort4_fleet3_9_rj0_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=4)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.0
        seed_label_doc_here(client, WALL0 + 3.9)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(4.000000000023283, abs=1e-09),
            pytest.approx(4.100000000023283, abs=1e-09),
            pytest.approx(4.300000000023283, abs=1e-09),
            pytest.approx(4.700000000023283, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(3.900000000023283, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort4_fleet3_9_rj0_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=4)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.0
        seed_label_doc_here(client, WALL0 + 3.9)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(4.000000000023283, abs=1e-09),
            pytest.approx(4.100000000023283, abs=1e-09),
            pytest.approx(4.300000000023283, abs=1e-09),
            pytest.approx(4.700000000023283, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(3.900000000023283, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort4_fleet3_9_rj0p25_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=4)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.25
        seed_label_doc_here(client, WALL0 + 3.9)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(4.025000000023283, abs=1e-09),
            pytest.approx(4.150000000023283, abs=1e-09),
            pytest.approx(4.400000000023283, abs=1e-09),
            pytest.approx(4.900000000023283, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(3.900000000023283, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort4_fleet3_9_rj0p25_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=4)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.25
        seed_label_doc_here(client, WALL0 + 3.9)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(4.025000000023283, abs=1e-09),
            pytest.approx(4.150000000023283, abs=1e-09),
            pytest.approx(4.400000000023283, abs=1e-09),
            pytest.approx(4.900000000023283, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(3.900000000023283, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort4_fleet3_9_rj0p5_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=4)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.5
        seed_label_doc_here(client, WALL0 + 3.9)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(4.050000000023283, abs=1e-09),
            pytest.approx(4.200000000023283, abs=1e-09),
            pytest.approx(4.500000000023283, abs=1e-09),
            pytest.approx(5.100000000023283, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(3.900000000023283, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort4_fleet3_9_rj0p5_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=4)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.5
        seed_label_doc_here(client, WALL0 + 3.9)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(4.050000000023283, abs=1e-09),
            pytest.approx(4.200000000023283, abs=1e-09),
            pytest.approx(4.500000000023283, abs=1e-09),
            pytest.approx(5.100000000023283, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(3.900000000023283, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort4_fleet3_9_rj0p75_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=4)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.75
        seed_label_doc_here(client, WALL0 + 3.9)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(4.075000000023283, abs=1e-09),
            pytest.approx(4.250000000023283, abs=1e-09),
            pytest.approx(4.600000000023283, abs=1e-09),
            pytest.approx(5.300000000023283, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(3.900000000023283, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort4_fleet3_9_rj0p75_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=4)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.75
        seed_label_doc_here(client, WALL0 + 3.9)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(4.075000000023283, abs=1e-09),
            pytest.approx(4.250000000023283, abs=1e-09),
            pytest.approx(4.600000000023283, abs=1e-09),
            pytest.approx(5.300000000023283, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(3.900000000023283, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort4_fleet3_9_rj1_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=4)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 1.0
        seed_label_doc_here(client, WALL0 + 3.9)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(4.100000000023283, abs=1e-09),
            pytest.approx(4.300000000023283, abs=1e-09),
            pytest.approx(4.700000000023283, abs=1e-09),
            pytest.approx(5.500000000023283, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(3.900000000023283, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort4_fleet3_9_rj1_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=4)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 1.0
        seed_label_doc_here(client, WALL0 + 3.9)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(4.100000000023283, abs=1e-09),
            pytest.approx(4.300000000023283, abs=1e-09),
            pytest.approx(4.700000000023283, abs=1e-09),
            pytest.approx(5.500000000023283, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(3.900000000023283, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort4_spill0_6_rj0_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=4)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.0
        seed_spill_here(client, WALL0 + 0.6)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(0.6999999999767169, abs=1e-09),
            pytest.approx(0.7999999999767169, abs=1e-09),
            pytest.approx(0.999999999976717, abs=1e-09),
            pytest.approx(1.8, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(0.5999999999767169, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort4_spill0_6_rj0_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=4)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.0
        seed_spill_here(client, WALL0 + 0.6)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(0.6999999999767169, abs=1e-09),
            pytest.approx(0.7999999999767169, abs=1e-09),
            pytest.approx(1.275, abs=1e-09),
            pytest.approx(2.55, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(0.5999999999767169, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort4_spill0_6_rj0p25_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=4)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.25
        seed_spill_here(client, WALL0 + 0.6)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(0.7249999999767169, abs=1e-09),
            pytest.approx(0.8499999999767169, abs=1e-09),
            pytest.approx(1.099999999976717, abs=1e-09),
            pytest.approx(2.0, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(0.5999999999767169, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort4_spill0_6_rj0p25_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=4)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.25
        seed_spill_here(client, WALL0 + 0.6)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(0.7249999999767169, abs=1e-09),
            pytest.approx(0.8499999999767169, abs=1e-09),
            pytest.approx(1.375, abs=1e-09),
            pytest.approx(2.75, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(0.5999999999767169, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort4_spill0_6_rj0p5_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=4)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.5
        seed_spill_here(client, WALL0 + 0.6)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(0.749999999976717, abs=1e-09),
            pytest.approx(0.899999999976717, abs=1e-09),
            pytest.approx(1.199999999976717, abs=1e-09),
            pytest.approx(2.2, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(0.5999999999767169, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort4_spill0_6_rj0p5_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=4)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.5
        seed_spill_here(client, WALL0 + 0.6)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(0.749999999976717, abs=1e-09),
            pytest.approx(0.899999999976717, abs=1e-09),
            pytest.approx(1.475, abs=1e-09),
            pytest.approx(2.95, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(0.5999999999767169, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort4_spill0_6_rj0p75_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=4)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.75
        seed_spill_here(client, WALL0 + 0.6)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(0.774999999976717, abs=1e-09),
            pytest.approx(0.949999999976717, abs=1e-09),
            pytest.approx(1.2999999999767171, abs=1e-09),
            pytest.approx(2.4000000000000004, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(0.5999999999767169, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort4_spill0_6_rj0p75_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=4)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.75
        seed_spill_here(client, WALL0 + 0.6)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(0.774999999976717, abs=1e-09),
            pytest.approx(0.949999999976717, abs=1e-09),
            pytest.approx(1.5750000000000002, abs=1e-09),
            pytest.approx(3.1500000000000004, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(0.5999999999767169, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort4_spill0_6_rj1_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=4)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 1.0
        seed_spill_here(client, WALL0 + 0.6)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(0.7999999999767169, abs=1e-09),
            pytest.approx(0.999999999976717, abs=1e-09),
            pytest.approx(1.399999999976717, abs=1e-09),
            pytest.approx(2.6, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(0.5999999999767169, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort4_spill0_6_rj1_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=4)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 1.0
        seed_spill_here(client, WALL0 + 0.6)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(0.7999999999767169, abs=1e-09),
            pytest.approx(0.999999999976717, abs=1e-09),
            pytest.approx(1.675, abs=1e-09),
            pytest.approx(3.35, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(0.5999999999767169, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort4_spill2_6_rj0_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=4)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.0
        seed_spill_here(client, WALL0 + 2.6)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(1.1, abs=1e-09),
            pytest.approx(1.2, abs=1e-09),
            pytest.approx(1.4, abs=1e-09),
            pytest.approx(1.8, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(1.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort4_spill2_6_rj0_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=4)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.0
        seed_spill_here(client, WALL0 + 2.6)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(1.1, abs=1e-09),
            pytest.approx(1.2, abs=1e-09),
            pytest.approx(1.4, abs=1e-09),
            pytest.approx(2.55, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(1.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort4_spill2_6_rj0p25_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=4)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.25
        seed_spill_here(client, WALL0 + 2.6)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(1.125, abs=1e-09),
            pytest.approx(1.25, abs=1e-09),
            pytest.approx(1.5, abs=1e-09),
            pytest.approx(2.0, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(1.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort4_spill2_6_rj0p25_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=4)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.25
        seed_spill_here(client, WALL0 + 2.6)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(1.125, abs=1e-09),
            pytest.approx(1.25, abs=1e-09),
            pytest.approx(1.5, abs=1e-09),
            pytest.approx(2.75, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(1.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort4_spill2_6_rj0p5_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=4)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.5
        seed_spill_here(client, WALL0 + 2.6)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(1.15, abs=1e-09),
            pytest.approx(1.3, abs=1e-09),
            pytest.approx(1.6, abs=1e-09),
            pytest.approx(2.2, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(1.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort4_spill2_6_rj0p5_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=4)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.5
        seed_spill_here(client, WALL0 + 2.6)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(1.15, abs=1e-09),
            pytest.approx(1.3, abs=1e-09),
            pytest.approx(1.6, abs=1e-09),
            pytest.approx(2.95, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(1.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort4_spill2_6_rj0p75_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=4)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.75
        seed_spill_here(client, WALL0 + 2.6)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(1.175, abs=1e-09),
            pytest.approx(1.35, abs=1e-09),
            pytest.approx(1.7000000000000002, abs=1e-09),
            pytest.approx(2.4000000000000004, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(1.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort4_spill2_6_rj0p75_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=4)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.75
        seed_spill_here(client, WALL0 + 2.6)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(1.175, abs=1e-09),
            pytest.approx(1.35, abs=1e-09),
            pytest.approx(1.7000000000000002, abs=1e-09),
            pytest.approx(3.1500000000000004, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(1.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort4_spill2_6_rj1_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=4)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 1.0
        seed_spill_here(client, WALL0 + 2.6)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(1.2, abs=1e-09),
            pytest.approx(1.4, abs=1e-09),
            pytest.approx(1.8, abs=1e-09),
            pytest.approx(2.6, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(1.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort4_spill2_6_rj1_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=4)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 1.0
        seed_spill_here(client, WALL0 + 2.6)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(1.2, abs=1e-09),
            pytest.approx(1.4, abs=1e-09),
            pytest.approx(1.8, abs=1e-09),
            pytest.approx(3.35, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(1.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort4_spill3_9_rj0_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=4)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.0
        seed_spill_here(client, WALL0 + 3.9)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(1.1, abs=1e-09),
            pytest.approx(1.2, abs=1e-09),
            pytest.approx(1.4, abs=1e-09),
            pytest.approx(1.8, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(1.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort4_spill3_9_rj0_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=4)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.0
        seed_spill_here(client, WALL0 + 3.9)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(1.1, abs=1e-09),
            pytest.approx(1.2, abs=1e-09),
            pytest.approx(1.4, abs=1e-09),
            pytest.approx(2.55, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(1.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort4_spill3_9_rj0p25_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=4)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.25
        seed_spill_here(client, WALL0 + 3.9)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(1.125, abs=1e-09),
            pytest.approx(1.25, abs=1e-09),
            pytest.approx(1.5, abs=1e-09),
            pytest.approx(2.0, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(1.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort4_spill3_9_rj0p25_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=4)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.25
        seed_spill_here(client, WALL0 + 3.9)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(1.125, abs=1e-09),
            pytest.approx(1.25, abs=1e-09),
            pytest.approx(1.5, abs=1e-09),
            pytest.approx(2.75, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(1.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort4_spill3_9_rj0p5_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=4)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.5
        seed_spill_here(client, WALL0 + 3.9)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(1.15, abs=1e-09),
            pytest.approx(1.3, abs=1e-09),
            pytest.approx(1.6, abs=1e-09),
            pytest.approx(2.2, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(1.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort4_spill3_9_rj0p5_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=4)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.5
        seed_spill_here(client, WALL0 + 3.9)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(1.15, abs=1e-09),
            pytest.approx(1.3, abs=1e-09),
            pytest.approx(1.6, abs=1e-09),
            pytest.approx(2.95, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(1.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort4_spill3_9_rj0p75_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=4)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.75
        seed_spill_here(client, WALL0 + 3.9)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(1.175, abs=1e-09),
            pytest.approx(1.35, abs=1e-09),
            pytest.approx(1.7000000000000002, abs=1e-09),
            pytest.approx(2.4000000000000004, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(1.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort4_spill3_9_rj0p75_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=4)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.75
        seed_spill_here(client, WALL0 + 3.9)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(1.175, abs=1e-09),
            pytest.approx(1.35, abs=1e-09),
            pytest.approx(1.7000000000000002, abs=1e-09),
            pytest.approx(3.1500000000000004, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(1.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort4_spill3_9_rj1_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=4)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 1.0
        seed_spill_here(client, WALL0 + 3.9)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(1.2, abs=1e-09),
            pytest.approx(1.4, abs=1e-09),
            pytest.approx(1.8, abs=1e-09),
            pytest.approx(2.6, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(1.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort4_spill3_9_rj1_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=4)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 1.0
        seed_spill_here(client, WALL0 + 3.9)
        assert store.run(lambda tx: 'ok', operation=LABEL) == 'ok'
        assert retry.sleeps == [
            pytest.approx(1.2, abs=1e-09),
            pytest.approx(1.4, abs=1e-09),
            pytest.approx(1.8, abs=1e-09),
            pytest.approx(3.35, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(1.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort5_none_rj0_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=5)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.0
        with pytest.raises(storage.FirestoreContentionExhausted) as caught:
            store.run(lambda tx: True, operation=LABEL)
        assert caught.value.retry_after == pytest.approx(0.125, abs=1e-09)
        assert retry.sleeps == [
            pytest.approx(0.1, abs=1e-09),
            pytest.approx(0.2, abs=1e-09),
            pytest.approx(0.9, abs=1e-09),
            pytest.approx(1.8, abs=1e-09),
        ]
        assert clock.sleeps == []
    finally:
        reset_registries()


def test_chain_abort5_none_rj0_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=5)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.0
        with pytest.raises(storage.FirestoreContentionExhausted) as caught:
            store.run(lambda tx: True, operation=LABEL)
        assert caught.value.retry_after == pytest.approx(0.21875, abs=1e-09)
        assert retry.sleeps == [
            pytest.approx(0.1, abs=1e-09),
            pytest.approx(0.2, abs=1e-09),
            pytest.approx(1.275, abs=1e-09),
            pytest.approx(2.55, abs=1e-09),
        ]
        assert clock.sleeps == []
    finally:
        reset_registries()


def test_chain_abort5_none_rj0p25_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=5)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.25
        with pytest.raises(storage.FirestoreContentionExhausted) as caught:
            store.run(lambda tx: True, operation=LABEL)
        assert caught.value.retry_after == pytest.approx(0.125, abs=1e-09)
        assert retry.sleeps == [
            pytest.approx(0.125, abs=1e-09),
            pytest.approx(0.25, abs=1e-09),
            pytest.approx(1.0, abs=1e-09),
            pytest.approx(2.0, abs=1e-09),
        ]
        assert clock.sleeps == []
    finally:
        reset_registries()


def test_chain_abort5_none_rj0p25_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=5)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.25
        with pytest.raises(storage.FirestoreContentionExhausted) as caught:
            store.run(lambda tx: True, operation=LABEL)
        assert caught.value.retry_after == pytest.approx(0.21875, abs=1e-09)
        assert retry.sleeps == [
            pytest.approx(0.125, abs=1e-09),
            pytest.approx(0.25, abs=1e-09),
            pytest.approx(1.375, abs=1e-09),
            pytest.approx(2.75, abs=1e-09),
        ]
        assert clock.sleeps == []
    finally:
        reset_registries()


def test_chain_abort5_none_rj0p5_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=5)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.5
        with pytest.raises(storage.FirestoreContentionExhausted) as caught:
            store.run(lambda tx: True, operation=LABEL)
        assert caught.value.retry_after == pytest.approx(0.125, abs=1e-09)
        assert retry.sleeps == [
            pytest.approx(0.15000000000000002, abs=1e-09),
            pytest.approx(0.30000000000000004, abs=1e-09),
            pytest.approx(1.1, abs=1e-09),
            pytest.approx(2.2, abs=1e-09),
        ]
        assert clock.sleeps == []
    finally:
        reset_registries()


def test_chain_abort5_none_rj0p5_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=5)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.5
        with pytest.raises(storage.FirestoreContentionExhausted) as caught:
            store.run(lambda tx: True, operation=LABEL)
        assert caught.value.retry_after == pytest.approx(0.21875, abs=1e-09)
        assert retry.sleeps == [
            pytest.approx(0.15000000000000002, abs=1e-09),
            pytest.approx(0.30000000000000004, abs=1e-09),
            pytest.approx(1.475, abs=1e-09),
            pytest.approx(2.95, abs=1e-09),
        ]
        assert clock.sleeps == []
    finally:
        reset_registries()


def test_chain_abort5_none_rj0p75_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=5)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.75
        with pytest.raises(storage.FirestoreContentionExhausted) as caught:
            store.run(lambda tx: True, operation=LABEL)
        assert caught.value.retry_after == pytest.approx(0.125, abs=1e-09)
        assert retry.sleeps == [
            pytest.approx(0.17500000000000002, abs=1e-09),
            pytest.approx(0.35000000000000003, abs=1e-09),
            pytest.approx(1.2000000000000002, abs=1e-09),
            pytest.approx(2.4000000000000004, abs=1e-09),
        ]
        assert clock.sleeps == []
    finally:
        reset_registries()


def test_chain_abort5_none_rj0p75_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=5)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.75
        with pytest.raises(storage.FirestoreContentionExhausted) as caught:
            store.run(lambda tx: True, operation=LABEL)
        assert caught.value.retry_after == pytest.approx(0.21875, abs=1e-09)
        assert retry.sleeps == [
            pytest.approx(0.17500000000000002, abs=1e-09),
            pytest.approx(0.35000000000000003, abs=1e-09),
            pytest.approx(1.5750000000000002, abs=1e-09),
            pytest.approx(3.1500000000000004, abs=1e-09),
        ]
        assert clock.sleeps == []
    finally:
        reset_registries()


def test_chain_abort5_none_rj1_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=5)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 1.0
        with pytest.raises(storage.FirestoreContentionExhausted) as caught:
            store.run(lambda tx: True, operation=LABEL)
        assert caught.value.retry_after == pytest.approx(0.125, abs=1e-09)
        assert retry.sleeps == [
            pytest.approx(0.2, abs=1e-09),
            pytest.approx(0.4, abs=1e-09),
            pytest.approx(1.3, abs=1e-09),
            pytest.approx(2.6, abs=1e-09),
        ]
        assert clock.sleeps == []
    finally:
        reset_registries()


def test_chain_abort5_none_rj1_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=5)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 1.0
        with pytest.raises(storage.FirestoreContentionExhausted) as caught:
            store.run(lambda tx: True, operation=LABEL)
        assert caught.value.retry_after == pytest.approx(0.21875, abs=1e-09)
        assert retry.sleeps == [
            pytest.approx(0.2, abs=1e-09),
            pytest.approx(0.4, abs=1e-09),
            pytest.approx(1.675, abs=1e-09),
            pytest.approx(3.35, abs=1e-09),
        ]
        assert clock.sleeps == []
    finally:
        reset_registries()


def test_chain_abort5_own0_5_rj0_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=5)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.0
        damper._armed_until[LABEL] = clock.now + 0.5
        with pytest.raises(storage.FirestoreContentionExhausted) as caught:
            store.run(lambda tx: True, operation=LABEL)
        assert caught.value.retry_after == pytest.approx(0.125, abs=1e-09)
        assert retry.sleeps == [
            pytest.approx(0.1, abs=1e-09),
            pytest.approx(0.2, abs=1e-09),
            pytest.approx(0.9, abs=1e-09),
            pytest.approx(1.8, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(0.5, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort5_own0_5_rj0_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=5)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.0
        damper._armed_until[LABEL] = clock.now + 0.5
        with pytest.raises(storage.FirestoreContentionExhausted) as caught:
            store.run(lambda tx: True, operation=LABEL)
        assert caught.value.retry_after == pytest.approx(0.21875, abs=1e-09)
        assert retry.sleeps == [
            pytest.approx(0.1, abs=1e-09),
            pytest.approx(0.2, abs=1e-09),
            pytest.approx(1.275, abs=1e-09),
            pytest.approx(2.55, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(0.5, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort5_own0_5_rj0p25_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=5)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.25
        damper._armed_until[LABEL] = clock.now + 0.5
        with pytest.raises(storage.FirestoreContentionExhausted) as caught:
            store.run(lambda tx: True, operation=LABEL)
        assert caught.value.retry_after == pytest.approx(0.125, abs=1e-09)
        assert retry.sleeps == [
            pytest.approx(0.125, abs=1e-09),
            pytest.approx(0.25, abs=1e-09),
            pytest.approx(1.0, abs=1e-09),
            pytest.approx(2.0, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(0.5, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort5_own0_5_rj0p25_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=5)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.25
        damper._armed_until[LABEL] = clock.now + 0.5
        with pytest.raises(storage.FirestoreContentionExhausted) as caught:
            store.run(lambda tx: True, operation=LABEL)
        assert caught.value.retry_after == pytest.approx(0.21875, abs=1e-09)
        assert retry.sleeps == [
            pytest.approx(0.125, abs=1e-09),
            pytest.approx(0.25, abs=1e-09),
            pytest.approx(1.375, abs=1e-09),
            pytest.approx(2.75, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(0.5, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort5_own0_5_rj0p5_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=5)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.5
        damper._armed_until[LABEL] = clock.now + 0.5
        with pytest.raises(storage.FirestoreContentionExhausted) as caught:
            store.run(lambda tx: True, operation=LABEL)
        assert caught.value.retry_after == pytest.approx(0.125, abs=1e-09)
        assert retry.sleeps == [
            pytest.approx(0.15000000000000002, abs=1e-09),
            pytest.approx(0.30000000000000004, abs=1e-09),
            pytest.approx(1.1, abs=1e-09),
            pytest.approx(2.2, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(0.5, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort5_own0_5_rj0p5_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=5)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.5
        damper._armed_until[LABEL] = clock.now + 0.5
        with pytest.raises(storage.FirestoreContentionExhausted) as caught:
            store.run(lambda tx: True, operation=LABEL)
        assert caught.value.retry_after == pytest.approx(0.21875, abs=1e-09)
        assert retry.sleeps == [
            pytest.approx(0.15000000000000002, abs=1e-09),
            pytest.approx(0.30000000000000004, abs=1e-09),
            pytest.approx(1.475, abs=1e-09),
            pytest.approx(2.95, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(0.5, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort5_own0_5_rj0p75_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=5)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.75
        damper._armed_until[LABEL] = clock.now + 0.5
        with pytest.raises(storage.FirestoreContentionExhausted) as caught:
            store.run(lambda tx: True, operation=LABEL)
        assert caught.value.retry_after == pytest.approx(0.125, abs=1e-09)
        assert retry.sleeps == [
            pytest.approx(0.17500000000000002, abs=1e-09),
            pytest.approx(0.35000000000000003, abs=1e-09),
            pytest.approx(1.2000000000000002, abs=1e-09),
            pytest.approx(2.4000000000000004, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(0.5, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort5_own0_5_rj0p75_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=5)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.75
        damper._armed_until[LABEL] = clock.now + 0.5
        with pytest.raises(storage.FirestoreContentionExhausted) as caught:
            store.run(lambda tx: True, operation=LABEL)
        assert caught.value.retry_after == pytest.approx(0.21875, abs=1e-09)
        assert retry.sleeps == [
            pytest.approx(0.17500000000000002, abs=1e-09),
            pytest.approx(0.35000000000000003, abs=1e-09),
            pytest.approx(1.5750000000000002, abs=1e-09),
            pytest.approx(3.1500000000000004, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(0.5, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort5_own0_5_rj1_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=5)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 1.0
        damper._armed_until[LABEL] = clock.now + 0.5
        with pytest.raises(storage.FirestoreContentionExhausted) as caught:
            store.run(lambda tx: True, operation=LABEL)
        assert caught.value.retry_after == pytest.approx(0.125, abs=1e-09)
        assert retry.sleeps == [
            pytest.approx(0.2, abs=1e-09),
            pytest.approx(0.4, abs=1e-09),
            pytest.approx(1.3, abs=1e-09),
            pytest.approx(2.6, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(0.5, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort5_own0_5_rj1_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=5)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 1.0
        damper._armed_until[LABEL] = clock.now + 0.5
        with pytest.raises(storage.FirestoreContentionExhausted) as caught:
            store.run(lambda tx: True, operation=LABEL)
        assert caught.value.retry_after == pytest.approx(0.21875, abs=1e-09)
        assert retry.sleeps == [
            pytest.approx(0.2, abs=1e-09),
            pytest.approx(0.4, abs=1e-09),
            pytest.approx(1.675, abs=1e-09),
            pytest.approx(3.35, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(0.5, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort5_own1_5_rj0_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=5)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.0
        damper._armed_until[LABEL] = clock.now + 1.5
        with pytest.raises(storage.FirestoreContentionExhausted) as caught:
            store.run(lambda tx: True, operation=LABEL)
        assert caught.value.retry_after == pytest.approx(0.125, abs=1e-09)
        assert retry.sleeps == [
            pytest.approx(0.1, abs=1e-09),
            pytest.approx(0.2, abs=1e-09),
            pytest.approx(0.9, abs=1e-09),
            pytest.approx(1.8, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(1.5, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort5_own1_5_rj0_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=5)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.0
        damper._armed_until[LABEL] = clock.now + 1.5
        with pytest.raises(storage.FirestoreContentionExhausted) as caught:
            store.run(lambda tx: True, operation=LABEL)
        assert caught.value.retry_after == pytest.approx(0.21875, abs=1e-09)
        assert retry.sleeps == [
            pytest.approx(0.1, abs=1e-09),
            pytest.approx(0.2, abs=1e-09),
            pytest.approx(1.275, abs=1e-09),
            pytest.approx(2.55, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(1.5, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort5_own1_5_rj0p25_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=5)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.25
        damper._armed_until[LABEL] = clock.now + 1.5
        with pytest.raises(storage.FirestoreContentionExhausted) as caught:
            store.run(lambda tx: True, operation=LABEL)
        assert caught.value.retry_after == pytest.approx(0.125, abs=1e-09)
        assert retry.sleeps == [
            pytest.approx(0.125, abs=1e-09),
            pytest.approx(0.25, abs=1e-09),
            pytest.approx(1.0, abs=1e-09),
            pytest.approx(2.0, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(1.5, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort5_own1_5_rj0p25_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=5)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.25
        damper._armed_until[LABEL] = clock.now + 1.5
        with pytest.raises(storage.FirestoreContentionExhausted) as caught:
            store.run(lambda tx: True, operation=LABEL)
        assert caught.value.retry_after == pytest.approx(0.21875, abs=1e-09)
        assert retry.sleeps == [
            pytest.approx(0.125, abs=1e-09),
            pytest.approx(0.25, abs=1e-09),
            pytest.approx(1.375, abs=1e-09),
            pytest.approx(2.75, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(1.5, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort5_own1_5_rj0p5_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=5)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.5
        damper._armed_until[LABEL] = clock.now + 1.5
        with pytest.raises(storage.FirestoreContentionExhausted) as caught:
            store.run(lambda tx: True, operation=LABEL)
        assert caught.value.retry_after == pytest.approx(0.125, abs=1e-09)
        assert retry.sleeps == [
            pytest.approx(0.15000000000000002, abs=1e-09),
            pytest.approx(0.30000000000000004, abs=1e-09),
            pytest.approx(1.1, abs=1e-09),
            pytest.approx(2.2, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(1.5, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort5_own1_5_rj0p5_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=5)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.5
        damper._armed_until[LABEL] = clock.now + 1.5
        with pytest.raises(storage.FirestoreContentionExhausted) as caught:
            store.run(lambda tx: True, operation=LABEL)
        assert caught.value.retry_after == pytest.approx(0.21875, abs=1e-09)
        assert retry.sleeps == [
            pytest.approx(0.15000000000000002, abs=1e-09),
            pytest.approx(0.30000000000000004, abs=1e-09),
            pytest.approx(1.475, abs=1e-09),
            pytest.approx(2.95, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(1.5, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort5_own1_5_rj0p75_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=5)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.75
        damper._armed_until[LABEL] = clock.now + 1.5
        with pytest.raises(storage.FirestoreContentionExhausted) as caught:
            store.run(lambda tx: True, operation=LABEL)
        assert caught.value.retry_after == pytest.approx(0.125, abs=1e-09)
        assert retry.sleeps == [
            pytest.approx(0.17500000000000002, abs=1e-09),
            pytest.approx(0.35000000000000003, abs=1e-09),
            pytest.approx(1.2000000000000002, abs=1e-09),
            pytest.approx(2.4000000000000004, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(1.5, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort5_own1_5_rj0p75_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=5)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.75
        damper._armed_until[LABEL] = clock.now + 1.5
        with pytest.raises(storage.FirestoreContentionExhausted) as caught:
            store.run(lambda tx: True, operation=LABEL)
        assert caught.value.retry_after == pytest.approx(0.21875, abs=1e-09)
        assert retry.sleeps == [
            pytest.approx(0.17500000000000002, abs=1e-09),
            pytest.approx(0.35000000000000003, abs=1e-09),
            pytest.approx(1.5750000000000002, abs=1e-09),
            pytest.approx(3.1500000000000004, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(1.5, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort5_own1_5_rj1_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=5)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 1.0
        damper._armed_until[LABEL] = clock.now + 1.5
        with pytest.raises(storage.FirestoreContentionExhausted) as caught:
            store.run(lambda tx: True, operation=LABEL)
        assert caught.value.retry_after == pytest.approx(0.125, abs=1e-09)
        assert retry.sleeps == [
            pytest.approx(0.2, abs=1e-09),
            pytest.approx(0.4, abs=1e-09),
            pytest.approx(1.3, abs=1e-09),
            pytest.approx(2.6, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(1.5, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort5_own1_5_rj1_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=5)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 1.0
        damper._armed_until[LABEL] = clock.now + 1.5
        with pytest.raises(storage.FirestoreContentionExhausted) as caught:
            store.run(lambda tx: True, operation=LABEL)
        assert caught.value.retry_after == pytest.approx(0.21875, abs=1e-09)
        assert retry.sleeps == [
            pytest.approx(0.2, abs=1e-09),
            pytest.approx(0.4, abs=1e-09),
            pytest.approx(1.675, abs=1e-09),
            pytest.approx(3.35, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(1.5, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort5_fleet0_3_rj0_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=5)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.0
        seed_label_doc_here(client, WALL0 + 0.3)
        with pytest.raises(storage.FirestoreContentionExhausted) as caught:
            store.run(lambda tx: True, operation=LABEL)
        assert caught.value.retry_after == pytest.approx(0.125, abs=1e-09)
        assert retry.sleeps == [
            pytest.approx(0.4000000000465661, abs=1e-09),
            pytest.approx(0.5000000000465661, abs=1e-09),
            pytest.approx(0.9, abs=1e-09),
            pytest.approx(1.8, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(0.30000000004656613, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort5_fleet0_3_rj0_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=5)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.0
        seed_label_doc_here(client, WALL0 + 0.3)
        with pytest.raises(storage.FirestoreContentionExhausted) as caught:
            store.run(lambda tx: True, operation=LABEL)
        assert caught.value.retry_after == pytest.approx(0.21875, abs=1e-09)
        assert retry.sleeps == [
            pytest.approx(0.4000000000465661, abs=1e-09),
            pytest.approx(0.5000000000465661, abs=1e-09),
            pytest.approx(1.275, abs=1e-09),
            pytest.approx(2.55, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(0.30000000004656613, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort5_fleet0_3_rj0p25_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=5)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.25
        seed_label_doc_here(client, WALL0 + 0.3)
        with pytest.raises(storage.FirestoreContentionExhausted) as caught:
            store.run(lambda tx: True, operation=LABEL)
        assert caught.value.retry_after == pytest.approx(0.125, abs=1e-09)
        assert retry.sleeps == [
            pytest.approx(0.42500000004656613, abs=1e-09),
            pytest.approx(0.5500000000465661, abs=1e-09),
            pytest.approx(1.0, abs=1e-09),
            pytest.approx(2.0, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(0.30000000004656613, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort5_fleet0_3_rj0p25_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=5)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.25
        seed_label_doc_here(client, WALL0 + 0.3)
        with pytest.raises(storage.FirestoreContentionExhausted) as caught:
            store.run(lambda tx: True, operation=LABEL)
        assert caught.value.retry_after == pytest.approx(0.21875, abs=1e-09)
        assert retry.sleeps == [
            pytest.approx(0.42500000004656613, abs=1e-09),
            pytest.approx(0.5500000000465661, abs=1e-09),
            pytest.approx(1.375, abs=1e-09),
            pytest.approx(2.75, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(0.30000000004656613, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort5_fleet0_3_rj0p5_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=5)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.5
        seed_label_doc_here(client, WALL0 + 0.3)
        with pytest.raises(storage.FirestoreContentionExhausted) as caught:
            store.run(lambda tx: True, operation=LABEL)
        assert caught.value.retry_after == pytest.approx(0.125, abs=1e-09)
        assert retry.sleeps == [
            pytest.approx(0.45000000004656615, abs=1e-09),
            pytest.approx(0.6000000000465662, abs=1e-09),
            pytest.approx(1.1, abs=1e-09),
            pytest.approx(2.2, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(0.30000000004656613, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort5_fleet0_3_rj0p5_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=5)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.5
        seed_label_doc_here(client, WALL0 + 0.3)
        with pytest.raises(storage.FirestoreContentionExhausted) as caught:
            store.run(lambda tx: True, operation=LABEL)
        assert caught.value.retry_after == pytest.approx(0.21875, abs=1e-09)
        assert retry.sleeps == [
            pytest.approx(0.45000000004656615, abs=1e-09),
            pytest.approx(0.6000000000465662, abs=1e-09),
            pytest.approx(1.475, abs=1e-09),
            pytest.approx(2.95, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(0.30000000004656613, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort5_fleet0_3_rj0p75_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=5)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.75
        seed_label_doc_here(client, WALL0 + 0.3)
        with pytest.raises(storage.FirestoreContentionExhausted) as caught:
            store.run(lambda tx: True, operation=LABEL)
        assert caught.value.retry_after == pytest.approx(0.125, abs=1e-09)
        assert retry.sleeps == [
            pytest.approx(0.4750000000465662, abs=1e-09),
            pytest.approx(0.6500000000465662, abs=1e-09),
            pytest.approx(1.2000000000000002, abs=1e-09),
            pytest.approx(2.4000000000000004, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(0.30000000004656613, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort5_fleet0_3_rj0p75_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=5)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.75
        seed_label_doc_here(client, WALL0 + 0.3)
        with pytest.raises(storage.FirestoreContentionExhausted) as caught:
            store.run(lambda tx: True, operation=LABEL)
        assert caught.value.retry_after == pytest.approx(0.21875, abs=1e-09)
        assert retry.sleeps == [
            pytest.approx(0.4750000000465662, abs=1e-09),
            pytest.approx(0.6500000000465662, abs=1e-09),
            pytest.approx(1.5750000000000002, abs=1e-09),
            pytest.approx(3.1500000000000004, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(0.30000000004656613, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort5_fleet0_3_rj1_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=5)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 1.0
        seed_label_doc_here(client, WALL0 + 0.3)
        with pytest.raises(storage.FirestoreContentionExhausted) as caught:
            store.run(lambda tx: True, operation=LABEL)
        assert caught.value.retry_after == pytest.approx(0.125, abs=1e-09)
        assert retry.sleeps == [
            pytest.approx(0.5000000000465661, abs=1e-09),
            pytest.approx(0.7000000000465662, abs=1e-09),
            pytest.approx(1.3, abs=1e-09),
            pytest.approx(2.6, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(0.30000000004656613, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort5_fleet0_3_rj1_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=5)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 1.0
        seed_label_doc_here(client, WALL0 + 0.3)
        with pytest.raises(storage.FirestoreContentionExhausted) as caught:
            store.run(lambda tx: True, operation=LABEL)
        assert caught.value.retry_after == pytest.approx(0.21875, abs=1e-09)
        assert retry.sleeps == [
            pytest.approx(0.5000000000465661, abs=1e-09),
            pytest.approx(0.7000000000465662, abs=1e-09),
            pytest.approx(1.675, abs=1e-09),
            pytest.approx(3.35, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(0.30000000004656613, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort5_fleet2_0_rj0_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=5)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.0
        seed_label_doc_here(client, WALL0 + 2.0)
        with pytest.raises(storage.FirestoreContentionExhausted) as caught:
            store.run(lambda tx: True, operation=LABEL)
        assert caught.value.retry_after == pytest.approx(0.125, abs=1e-09)
        assert retry.sleeps == [
            pytest.approx(2.1, abs=1e-09),
            pytest.approx(2.2, abs=1e-09),
            pytest.approx(2.4, abs=1e-09),
            pytest.approx(2.8, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(2.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort5_fleet2_0_rj0_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=5)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.0
        seed_label_doc_here(client, WALL0 + 2.0)
        with pytest.raises(storage.FirestoreContentionExhausted) as caught:
            store.run(lambda tx: True, operation=LABEL)
        assert caught.value.retry_after == pytest.approx(0.21875, abs=1e-09)
        assert retry.sleeps == [
            pytest.approx(2.1, abs=1e-09),
            pytest.approx(2.2, abs=1e-09),
            pytest.approx(2.4, abs=1e-09),
            pytest.approx(2.8, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(2.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort5_fleet2_0_rj0p25_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=5)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.25
        seed_label_doc_here(client, WALL0 + 2.0)
        with pytest.raises(storage.FirestoreContentionExhausted) as caught:
            store.run(lambda tx: True, operation=LABEL)
        assert caught.value.retry_after == pytest.approx(0.125, abs=1e-09)
        assert retry.sleeps == [
            pytest.approx(2.125, abs=1e-09),
            pytest.approx(2.25, abs=1e-09),
            pytest.approx(2.5, abs=1e-09),
            pytest.approx(3.0, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(2.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort5_fleet2_0_rj0p25_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=5)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.25
        seed_label_doc_here(client, WALL0 + 2.0)
        with pytest.raises(storage.FirestoreContentionExhausted) as caught:
            store.run(lambda tx: True, operation=LABEL)
        assert caught.value.retry_after == pytest.approx(0.21875, abs=1e-09)
        assert retry.sleeps == [
            pytest.approx(2.125, abs=1e-09),
            pytest.approx(2.25, abs=1e-09),
            pytest.approx(2.5, abs=1e-09),
            pytest.approx(3.0, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(2.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort5_fleet2_0_rj0p5_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=5)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.5
        seed_label_doc_here(client, WALL0 + 2.0)
        with pytest.raises(storage.FirestoreContentionExhausted) as caught:
            store.run(lambda tx: True, operation=LABEL)
        assert caught.value.retry_after == pytest.approx(0.125, abs=1e-09)
        assert retry.sleeps == [
            pytest.approx(2.15, abs=1e-09),
            pytest.approx(2.3, abs=1e-09),
            pytest.approx(2.6, abs=1e-09),
            pytest.approx(3.2, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(2.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort5_fleet2_0_rj0p5_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=5)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.5
        seed_label_doc_here(client, WALL0 + 2.0)
        with pytest.raises(storage.FirestoreContentionExhausted) as caught:
            store.run(lambda tx: True, operation=LABEL)
        assert caught.value.retry_after == pytest.approx(0.21875, abs=1e-09)
        assert retry.sleeps == [
            pytest.approx(2.15, abs=1e-09),
            pytest.approx(2.3, abs=1e-09),
            pytest.approx(2.6, abs=1e-09),
            pytest.approx(3.2, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(2.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort5_fleet2_0_rj0p75_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=5)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.75
        seed_label_doc_here(client, WALL0 + 2.0)
        with pytest.raises(storage.FirestoreContentionExhausted) as caught:
            store.run(lambda tx: True, operation=LABEL)
        assert caught.value.retry_after == pytest.approx(0.125, abs=1e-09)
        assert retry.sleeps == [
            pytest.approx(2.175, abs=1e-09),
            pytest.approx(2.35, abs=1e-09),
            pytest.approx(2.7, abs=1e-09),
            pytest.approx(3.4000000000000004, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(2.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort5_fleet2_0_rj0p75_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=5)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.75
        seed_label_doc_here(client, WALL0 + 2.0)
        with pytest.raises(storage.FirestoreContentionExhausted) as caught:
            store.run(lambda tx: True, operation=LABEL)
        assert caught.value.retry_after == pytest.approx(0.21875, abs=1e-09)
        assert retry.sleeps == [
            pytest.approx(2.175, abs=1e-09),
            pytest.approx(2.35, abs=1e-09),
            pytest.approx(2.7, abs=1e-09),
            pytest.approx(3.4000000000000004, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(2.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort5_fleet2_0_rj1_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=5)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 1.0
        seed_label_doc_here(client, WALL0 + 2.0)
        with pytest.raises(storage.FirestoreContentionExhausted) as caught:
            store.run(lambda tx: True, operation=LABEL)
        assert caught.value.retry_after == pytest.approx(0.125, abs=1e-09)
        assert retry.sleeps == [
            pytest.approx(2.2, abs=1e-09),
            pytest.approx(2.4, abs=1e-09),
            pytest.approx(2.8, abs=1e-09),
            pytest.approx(3.6, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(2.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort5_fleet2_0_rj1_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=5)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 1.0
        seed_label_doc_here(client, WALL0 + 2.0)
        with pytest.raises(storage.FirestoreContentionExhausted) as caught:
            store.run(lambda tx: True, operation=LABEL)
        assert caught.value.retry_after == pytest.approx(0.21875, abs=1e-09)
        assert retry.sleeps == [
            pytest.approx(2.2, abs=1e-09),
            pytest.approx(2.4, abs=1e-09),
            pytest.approx(2.8, abs=1e-09),
            pytest.approx(3.6, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(2.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort5_fleet3_9_rj0_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=5)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.0
        seed_label_doc_here(client, WALL0 + 3.9)
        with pytest.raises(storage.FirestoreContentionExhausted) as caught:
            store.run(lambda tx: True, operation=LABEL)
        assert caught.value.retry_after == pytest.approx(0.125, abs=1e-09)
        assert retry.sleeps == [
            pytest.approx(4.000000000023283, abs=1e-09),
            pytest.approx(4.100000000023283, abs=1e-09),
            pytest.approx(4.300000000023283, abs=1e-09),
            pytest.approx(4.700000000023283, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(3.900000000023283, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort5_fleet3_9_rj0_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=5)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.0
        seed_label_doc_here(client, WALL0 + 3.9)
        with pytest.raises(storage.FirestoreContentionExhausted) as caught:
            store.run(lambda tx: True, operation=LABEL)
        assert caught.value.retry_after == pytest.approx(0.21875, abs=1e-09)
        assert retry.sleeps == [
            pytest.approx(4.000000000023283, abs=1e-09),
            pytest.approx(4.100000000023283, abs=1e-09),
            pytest.approx(4.300000000023283, abs=1e-09),
            pytest.approx(4.700000000023283, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(3.900000000023283, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort5_fleet3_9_rj0p25_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=5)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.25
        seed_label_doc_here(client, WALL0 + 3.9)
        with pytest.raises(storage.FirestoreContentionExhausted) as caught:
            store.run(lambda tx: True, operation=LABEL)
        assert caught.value.retry_after == pytest.approx(0.125, abs=1e-09)
        assert retry.sleeps == [
            pytest.approx(4.025000000023283, abs=1e-09),
            pytest.approx(4.150000000023283, abs=1e-09),
            pytest.approx(4.400000000023283, abs=1e-09),
            pytest.approx(4.900000000023283, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(3.900000000023283, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort5_fleet3_9_rj0p25_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=5)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.25
        seed_label_doc_here(client, WALL0 + 3.9)
        with pytest.raises(storage.FirestoreContentionExhausted) as caught:
            store.run(lambda tx: True, operation=LABEL)
        assert caught.value.retry_after == pytest.approx(0.21875, abs=1e-09)
        assert retry.sleeps == [
            pytest.approx(4.025000000023283, abs=1e-09),
            pytest.approx(4.150000000023283, abs=1e-09),
            pytest.approx(4.400000000023283, abs=1e-09),
            pytest.approx(4.900000000023283, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(3.900000000023283, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort5_fleet3_9_rj0p5_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=5)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.5
        seed_label_doc_here(client, WALL0 + 3.9)
        with pytest.raises(storage.FirestoreContentionExhausted) as caught:
            store.run(lambda tx: True, operation=LABEL)
        assert caught.value.retry_after == pytest.approx(0.125, abs=1e-09)
        assert retry.sleeps == [
            pytest.approx(4.050000000023283, abs=1e-09),
            pytest.approx(4.200000000023283, abs=1e-09),
            pytest.approx(4.500000000023283, abs=1e-09),
            pytest.approx(5.100000000023283, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(3.900000000023283, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort5_fleet3_9_rj0p5_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=5)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.5
        seed_label_doc_here(client, WALL0 + 3.9)
        with pytest.raises(storage.FirestoreContentionExhausted) as caught:
            store.run(lambda tx: True, operation=LABEL)
        assert caught.value.retry_after == pytest.approx(0.21875, abs=1e-09)
        assert retry.sleeps == [
            pytest.approx(4.050000000023283, abs=1e-09),
            pytest.approx(4.200000000023283, abs=1e-09),
            pytest.approx(4.500000000023283, abs=1e-09),
            pytest.approx(5.100000000023283, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(3.900000000023283, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort5_fleet3_9_rj0p75_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=5)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.75
        seed_label_doc_here(client, WALL0 + 3.9)
        with pytest.raises(storage.FirestoreContentionExhausted) as caught:
            store.run(lambda tx: True, operation=LABEL)
        assert caught.value.retry_after == pytest.approx(0.125, abs=1e-09)
        assert retry.sleeps == [
            pytest.approx(4.075000000023283, abs=1e-09),
            pytest.approx(4.250000000023283, abs=1e-09),
            pytest.approx(4.600000000023283, abs=1e-09),
            pytest.approx(5.300000000023283, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(3.900000000023283, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort5_fleet3_9_rj0p75_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=5)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.75
        seed_label_doc_here(client, WALL0 + 3.9)
        with pytest.raises(storage.FirestoreContentionExhausted) as caught:
            store.run(lambda tx: True, operation=LABEL)
        assert caught.value.retry_after == pytest.approx(0.21875, abs=1e-09)
        assert retry.sleeps == [
            pytest.approx(4.075000000023283, abs=1e-09),
            pytest.approx(4.250000000023283, abs=1e-09),
            pytest.approx(4.600000000023283, abs=1e-09),
            pytest.approx(5.300000000023283, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(3.900000000023283, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort5_fleet3_9_rj1_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=5)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 1.0
        seed_label_doc_here(client, WALL0 + 3.9)
        with pytest.raises(storage.FirestoreContentionExhausted) as caught:
            store.run(lambda tx: True, operation=LABEL)
        assert caught.value.retry_after == pytest.approx(0.125, abs=1e-09)
        assert retry.sleeps == [
            pytest.approx(4.100000000023283, abs=1e-09),
            pytest.approx(4.300000000023283, abs=1e-09),
            pytest.approx(4.700000000023283, abs=1e-09),
            pytest.approx(5.500000000023283, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(3.900000000023283, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort5_fleet3_9_rj1_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=5)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 1.0
        seed_label_doc_here(client, WALL0 + 3.9)
        with pytest.raises(storage.FirestoreContentionExhausted) as caught:
            store.run(lambda tx: True, operation=LABEL)
        assert caught.value.retry_after == pytest.approx(0.21875, abs=1e-09)
        assert retry.sleeps == [
            pytest.approx(4.100000000023283, abs=1e-09),
            pytest.approx(4.300000000023283, abs=1e-09),
            pytest.approx(4.700000000023283, abs=1e-09),
            pytest.approx(5.500000000023283, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(3.900000000023283, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort5_spill0_6_rj0_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=5)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.0
        seed_spill_here(client, WALL0 + 0.6)
        with pytest.raises(storage.FirestoreContentionExhausted) as caught:
            store.run(lambda tx: True, operation=LABEL)
        assert caught.value.retry_after == pytest.approx(0.125, abs=1e-09)
        assert retry.sleeps == [
            pytest.approx(0.6999999999767169, abs=1e-09),
            pytest.approx(0.7999999999767169, abs=1e-09),
            pytest.approx(0.999999999976717, abs=1e-09),
            pytest.approx(1.8, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(0.5999999999767169, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort5_spill0_6_rj0_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=5)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.0
        seed_spill_here(client, WALL0 + 0.6)
        with pytest.raises(storage.FirestoreContentionExhausted) as caught:
            store.run(lambda tx: True, operation=LABEL)
        assert caught.value.retry_after == pytest.approx(0.21875, abs=1e-09)
        assert retry.sleeps == [
            pytest.approx(0.6999999999767169, abs=1e-09),
            pytest.approx(0.7999999999767169, abs=1e-09),
            pytest.approx(1.275, abs=1e-09),
            pytest.approx(2.55, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(0.5999999999767169, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort5_spill0_6_rj0p25_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=5)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.25
        seed_spill_here(client, WALL0 + 0.6)
        with pytest.raises(storage.FirestoreContentionExhausted) as caught:
            store.run(lambda tx: True, operation=LABEL)
        assert caught.value.retry_after == pytest.approx(0.125, abs=1e-09)
        assert retry.sleeps == [
            pytest.approx(0.7249999999767169, abs=1e-09),
            pytest.approx(0.8499999999767169, abs=1e-09),
            pytest.approx(1.099999999976717, abs=1e-09),
            pytest.approx(2.0, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(0.5999999999767169, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort5_spill0_6_rj0p25_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=5)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.25
        seed_spill_here(client, WALL0 + 0.6)
        with pytest.raises(storage.FirestoreContentionExhausted) as caught:
            store.run(lambda tx: True, operation=LABEL)
        assert caught.value.retry_after == pytest.approx(0.21875, abs=1e-09)
        assert retry.sleeps == [
            pytest.approx(0.7249999999767169, abs=1e-09),
            pytest.approx(0.8499999999767169, abs=1e-09),
            pytest.approx(1.375, abs=1e-09),
            pytest.approx(2.75, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(0.5999999999767169, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort5_spill0_6_rj0p5_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=5)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.5
        seed_spill_here(client, WALL0 + 0.6)
        with pytest.raises(storage.FirestoreContentionExhausted) as caught:
            store.run(lambda tx: True, operation=LABEL)
        assert caught.value.retry_after == pytest.approx(0.125, abs=1e-09)
        assert retry.sleeps == [
            pytest.approx(0.749999999976717, abs=1e-09),
            pytest.approx(0.899999999976717, abs=1e-09),
            pytest.approx(1.199999999976717, abs=1e-09),
            pytest.approx(2.2, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(0.5999999999767169, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort5_spill0_6_rj0p5_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=5)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.5
        seed_spill_here(client, WALL0 + 0.6)
        with pytest.raises(storage.FirestoreContentionExhausted) as caught:
            store.run(lambda tx: True, operation=LABEL)
        assert caught.value.retry_after == pytest.approx(0.21875, abs=1e-09)
        assert retry.sleeps == [
            pytest.approx(0.749999999976717, abs=1e-09),
            pytest.approx(0.899999999976717, abs=1e-09),
            pytest.approx(1.475, abs=1e-09),
            pytest.approx(2.95, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(0.5999999999767169, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort5_spill0_6_rj0p75_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=5)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.75
        seed_spill_here(client, WALL0 + 0.6)
        with pytest.raises(storage.FirestoreContentionExhausted) as caught:
            store.run(lambda tx: True, operation=LABEL)
        assert caught.value.retry_after == pytest.approx(0.125, abs=1e-09)
        assert retry.sleeps == [
            pytest.approx(0.774999999976717, abs=1e-09),
            pytest.approx(0.949999999976717, abs=1e-09),
            pytest.approx(1.2999999999767171, abs=1e-09),
            pytest.approx(2.4000000000000004, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(0.5999999999767169, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort5_spill0_6_rj0p75_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=5)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.75
        seed_spill_here(client, WALL0 + 0.6)
        with pytest.raises(storage.FirestoreContentionExhausted) as caught:
            store.run(lambda tx: True, operation=LABEL)
        assert caught.value.retry_after == pytest.approx(0.21875, abs=1e-09)
        assert retry.sleeps == [
            pytest.approx(0.774999999976717, abs=1e-09),
            pytest.approx(0.949999999976717, abs=1e-09),
            pytest.approx(1.5750000000000002, abs=1e-09),
            pytest.approx(3.1500000000000004, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(0.5999999999767169, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort5_spill0_6_rj1_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=5)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 1.0
        seed_spill_here(client, WALL0 + 0.6)
        with pytest.raises(storage.FirestoreContentionExhausted) as caught:
            store.run(lambda tx: True, operation=LABEL)
        assert caught.value.retry_after == pytest.approx(0.125, abs=1e-09)
        assert retry.sleeps == [
            pytest.approx(0.7999999999767169, abs=1e-09),
            pytest.approx(0.999999999976717, abs=1e-09),
            pytest.approx(1.399999999976717, abs=1e-09),
            pytest.approx(2.6, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(0.5999999999767169, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort5_spill0_6_rj1_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=5)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 1.0
        seed_spill_here(client, WALL0 + 0.6)
        with pytest.raises(storage.FirestoreContentionExhausted) as caught:
            store.run(lambda tx: True, operation=LABEL)
        assert caught.value.retry_after == pytest.approx(0.21875, abs=1e-09)
        assert retry.sleeps == [
            pytest.approx(0.7999999999767169, abs=1e-09),
            pytest.approx(0.999999999976717, abs=1e-09),
            pytest.approx(1.675, abs=1e-09),
            pytest.approx(3.35, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(0.5999999999767169, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort5_spill2_6_rj0_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=5)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.0
        seed_spill_here(client, WALL0 + 2.6)
        with pytest.raises(storage.FirestoreContentionExhausted) as caught:
            store.run(lambda tx: True, operation=LABEL)
        assert caught.value.retry_after == pytest.approx(0.125, abs=1e-09)
        assert retry.sleeps == [
            pytest.approx(1.1, abs=1e-09),
            pytest.approx(1.2, abs=1e-09),
            pytest.approx(1.4, abs=1e-09),
            pytest.approx(1.8, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(1.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort5_spill2_6_rj0_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=5)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.0
        seed_spill_here(client, WALL0 + 2.6)
        with pytest.raises(storage.FirestoreContentionExhausted) as caught:
            store.run(lambda tx: True, operation=LABEL)
        assert caught.value.retry_after == pytest.approx(0.21875, abs=1e-09)
        assert retry.sleeps == [
            pytest.approx(1.1, abs=1e-09),
            pytest.approx(1.2, abs=1e-09),
            pytest.approx(1.4, abs=1e-09),
            pytest.approx(2.55, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(1.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort5_spill2_6_rj0p25_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=5)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.25
        seed_spill_here(client, WALL0 + 2.6)
        with pytest.raises(storage.FirestoreContentionExhausted) as caught:
            store.run(lambda tx: True, operation=LABEL)
        assert caught.value.retry_after == pytest.approx(0.125, abs=1e-09)
        assert retry.sleeps == [
            pytest.approx(1.125, abs=1e-09),
            pytest.approx(1.25, abs=1e-09),
            pytest.approx(1.5, abs=1e-09),
            pytest.approx(2.0, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(1.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort5_spill2_6_rj0p25_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=5)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.25
        seed_spill_here(client, WALL0 + 2.6)
        with pytest.raises(storage.FirestoreContentionExhausted) as caught:
            store.run(lambda tx: True, operation=LABEL)
        assert caught.value.retry_after == pytest.approx(0.21875, abs=1e-09)
        assert retry.sleeps == [
            pytest.approx(1.125, abs=1e-09),
            pytest.approx(1.25, abs=1e-09),
            pytest.approx(1.5, abs=1e-09),
            pytest.approx(2.75, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(1.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort5_spill2_6_rj0p5_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=5)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.5
        seed_spill_here(client, WALL0 + 2.6)
        with pytest.raises(storage.FirestoreContentionExhausted) as caught:
            store.run(lambda tx: True, operation=LABEL)
        assert caught.value.retry_after == pytest.approx(0.125, abs=1e-09)
        assert retry.sleeps == [
            pytest.approx(1.15, abs=1e-09),
            pytest.approx(1.3, abs=1e-09),
            pytest.approx(1.6, abs=1e-09),
            pytest.approx(2.2, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(1.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort5_spill2_6_rj0p5_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=5)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.5
        seed_spill_here(client, WALL0 + 2.6)
        with pytest.raises(storage.FirestoreContentionExhausted) as caught:
            store.run(lambda tx: True, operation=LABEL)
        assert caught.value.retry_after == pytest.approx(0.21875, abs=1e-09)
        assert retry.sleeps == [
            pytest.approx(1.15, abs=1e-09),
            pytest.approx(1.3, abs=1e-09),
            pytest.approx(1.6, abs=1e-09),
            pytest.approx(2.95, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(1.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort5_spill2_6_rj0p75_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=5)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.75
        seed_spill_here(client, WALL0 + 2.6)
        with pytest.raises(storage.FirestoreContentionExhausted) as caught:
            store.run(lambda tx: True, operation=LABEL)
        assert caught.value.retry_after == pytest.approx(0.125, abs=1e-09)
        assert retry.sleeps == [
            pytest.approx(1.175, abs=1e-09),
            pytest.approx(1.35, abs=1e-09),
            pytest.approx(1.7000000000000002, abs=1e-09),
            pytest.approx(2.4000000000000004, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(1.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort5_spill2_6_rj0p75_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=5)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.75
        seed_spill_here(client, WALL0 + 2.6)
        with pytest.raises(storage.FirestoreContentionExhausted) as caught:
            store.run(lambda tx: True, operation=LABEL)
        assert caught.value.retry_after == pytest.approx(0.21875, abs=1e-09)
        assert retry.sleeps == [
            pytest.approx(1.175, abs=1e-09),
            pytest.approx(1.35, abs=1e-09),
            pytest.approx(1.7000000000000002, abs=1e-09),
            pytest.approx(3.1500000000000004, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(1.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort5_spill2_6_rj1_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=5)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 1.0
        seed_spill_here(client, WALL0 + 2.6)
        with pytest.raises(storage.FirestoreContentionExhausted) as caught:
            store.run(lambda tx: True, operation=LABEL)
        assert caught.value.retry_after == pytest.approx(0.125, abs=1e-09)
        assert retry.sleeps == [
            pytest.approx(1.2, abs=1e-09),
            pytest.approx(1.4, abs=1e-09),
            pytest.approx(1.8, abs=1e-09),
            pytest.approx(2.6, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(1.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort5_spill2_6_rj1_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=5)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 1.0
        seed_spill_here(client, WALL0 + 2.6)
        with pytest.raises(storage.FirestoreContentionExhausted) as caught:
            store.run(lambda tx: True, operation=LABEL)
        assert caught.value.retry_after == pytest.approx(0.21875, abs=1e-09)
        assert retry.sleeps == [
            pytest.approx(1.2, abs=1e-09),
            pytest.approx(1.4, abs=1e-09),
            pytest.approx(1.8, abs=1e-09),
            pytest.approx(3.35, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(1.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort5_spill3_9_rj0_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=5)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.0
        seed_spill_here(client, WALL0 + 3.9)
        with pytest.raises(storage.FirestoreContentionExhausted) as caught:
            store.run(lambda tx: True, operation=LABEL)
        assert caught.value.retry_after == pytest.approx(0.125, abs=1e-09)
        assert retry.sleeps == [
            pytest.approx(1.1, abs=1e-09),
            pytest.approx(1.2, abs=1e-09),
            pytest.approx(1.4, abs=1e-09),
            pytest.approx(1.8, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(1.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort5_spill3_9_rj0_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=5)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.0
        seed_spill_here(client, WALL0 + 3.9)
        with pytest.raises(storage.FirestoreContentionExhausted) as caught:
            store.run(lambda tx: True, operation=LABEL)
        assert caught.value.retry_after == pytest.approx(0.21875, abs=1e-09)
        assert retry.sleeps == [
            pytest.approx(1.1, abs=1e-09),
            pytest.approx(1.2, abs=1e-09),
            pytest.approx(1.4, abs=1e-09),
            pytest.approx(2.55, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(1.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort5_spill3_9_rj0p25_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=5)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.25
        seed_spill_here(client, WALL0 + 3.9)
        with pytest.raises(storage.FirestoreContentionExhausted) as caught:
            store.run(lambda tx: True, operation=LABEL)
        assert caught.value.retry_after == pytest.approx(0.125, abs=1e-09)
        assert retry.sleeps == [
            pytest.approx(1.125, abs=1e-09),
            pytest.approx(1.25, abs=1e-09),
            pytest.approx(1.5, abs=1e-09),
            pytest.approx(2.0, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(1.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort5_spill3_9_rj0p25_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=5)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.25
        seed_spill_here(client, WALL0 + 3.9)
        with pytest.raises(storage.FirestoreContentionExhausted) as caught:
            store.run(lambda tx: True, operation=LABEL)
        assert caught.value.retry_after == pytest.approx(0.21875, abs=1e-09)
        assert retry.sleeps == [
            pytest.approx(1.125, abs=1e-09),
            pytest.approx(1.25, abs=1e-09),
            pytest.approx(1.5, abs=1e-09),
            pytest.approx(2.75, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(1.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort5_spill3_9_rj0p5_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=5)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.5
        seed_spill_here(client, WALL0 + 3.9)
        with pytest.raises(storage.FirestoreContentionExhausted) as caught:
            store.run(lambda tx: True, operation=LABEL)
        assert caught.value.retry_after == pytest.approx(0.125, abs=1e-09)
        assert retry.sleeps == [
            pytest.approx(1.15, abs=1e-09),
            pytest.approx(1.3, abs=1e-09),
            pytest.approx(1.6, abs=1e-09),
            pytest.approx(2.2, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(1.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort5_spill3_9_rj0p5_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=5)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.5
        seed_spill_here(client, WALL0 + 3.9)
        with pytest.raises(storage.FirestoreContentionExhausted) as caught:
            store.run(lambda tx: True, operation=LABEL)
        assert caught.value.retry_after == pytest.approx(0.21875, abs=1e-09)
        assert retry.sleeps == [
            pytest.approx(1.15, abs=1e-09),
            pytest.approx(1.3, abs=1e-09),
            pytest.approx(1.6, abs=1e-09),
            pytest.approx(2.95, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(1.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort5_spill3_9_rj0p75_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=5)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.75
        seed_spill_here(client, WALL0 + 3.9)
        with pytest.raises(storage.FirestoreContentionExhausted) as caught:
            store.run(lambda tx: True, operation=LABEL)
        assert caught.value.retry_after == pytest.approx(0.125, abs=1e-09)
        assert retry.sleeps == [
            pytest.approx(1.175, abs=1e-09),
            pytest.approx(1.35, abs=1e-09),
            pytest.approx(1.7000000000000002, abs=1e-09),
            pytest.approx(2.4000000000000004, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(1.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort5_spill3_9_rj0p75_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=5)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 0.75
        seed_spill_here(client, WALL0 + 3.9)
        with pytest.raises(storage.FirestoreContentionExhausted) as caught:
            store.run(lambda tx: True, operation=LABEL)
        assert caught.value.retry_after == pytest.approx(0.21875, abs=1e-09)
        assert retry.sleeps == [
            pytest.approx(1.175, abs=1e-09),
            pytest.approx(1.35, abs=1e-09),
            pytest.approx(1.7000000000000002, abs=1e-09),
            pytest.approx(3.1500000000000004, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(1.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort5_spill3_9_rj1_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=5)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 1.0
        seed_spill_here(client, WALL0 + 3.9)
        with pytest.raises(storage.FirestoreContentionExhausted) as caught:
            store.run(lambda tx: True, operation=LABEL)
        assert caught.value.retry_after == pytest.approx(0.125, abs=1e-09)
        assert retry.sleeps == [
            pytest.approx(1.2, abs=1e-09),
            pytest.approx(1.4, abs=1e-09),
            pytest.approx(1.8, abs=1e-09),
            pytest.approx(2.6, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(1.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_abort5_spill3_9_rj1_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=5)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 1.0
        seed_spill_here(client, WALL0 + 3.9)
        with pytest.raises(storage.FirestoreContentionExhausted) as caught:
            store.run(lambda tx: True, operation=LABEL)
        assert caught.value.retry_after == pytest.approx(0.21875, abs=1e-09)
        assert retry.sleeps == [
            pytest.approx(1.2, abs=1e-09),
            pytest.approx(1.4, abs=1e-09),
            pytest.approx(1.8, abs=1e-09),
            pytest.approx(3.35, abs=1e-09),
        ]
        assert clock.sleeps == [pytest.approx(1.0, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_deadline_reserve_stops_attempt2_none_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=10**6)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        deadline = time.monotonic() + 29.5  # below the 30s reserve floor
        with pytest.raises(storage.FirestoreContentionExhausted) as caught:
            with retry_deadline_scope(deadline):
                store.run(lambda tx: True, operation=LABEL)
        assert caught.value.reason == 'deadline_exhausted'
        assert retry.sleeps == [pytest.approx(0.1, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_deadline_reserve_stops_attempt2_none_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=10**6)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        deadline = time.monotonic() + 29.5  # below the 30s reserve floor
        with pytest.raises(storage.FirestoreContentionExhausted) as caught:
            with retry_deadline_scope(deadline):
                store.run(lambda tx: True, operation=LABEL)
        assert caught.value.reason == 'deadline_exhausted'
        assert retry.sleeps == [pytest.approx(0.1, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_deadline_reserve_stops_attempt2_own0_5_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=10**6)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        damper._armed_until[LABEL] = clock.now + 0.5
        deadline = time.monotonic() + 29.5  # below the 30s reserve floor
        with pytest.raises(storage.FirestoreContentionExhausted) as caught:
            with retry_deadline_scope(deadline):
                store.run(lambda tx: True, operation=LABEL)
        assert caught.value.reason == 'deadline_exhausted'
        assert retry.sleeps == [pytest.approx(0.1, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_deadline_reserve_stops_attempt2_own0_5_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=10**6)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        damper._armed_until[LABEL] = clock.now + 0.5
        deadline = time.monotonic() + 29.5  # below the 30s reserve floor
        with pytest.raises(storage.FirestoreContentionExhausted) as caught:
            with retry_deadline_scope(deadline):
                store.run(lambda tx: True, operation=LABEL)
        assert caught.value.reason == 'deadline_exhausted'
        assert retry.sleeps == [pytest.approx(0.1, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_deadline_reserve_stops_attempt2_own1_5_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=10**6)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        damper._armed_until[LABEL] = clock.now + 1.5
        deadline = time.monotonic() + 29.5  # below the 30s reserve floor
        with pytest.raises(storage.FirestoreContentionExhausted) as caught:
            with retry_deadline_scope(deadline):
                store.run(lambda tx: True, operation=LABEL)
        assert caught.value.reason == 'deadline_exhausted'
        assert retry.sleeps == [pytest.approx(0.1, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_deadline_reserve_stops_attempt2_own1_5_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=10**6)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        damper._armed_until[LABEL] = clock.now + 1.5
        deadline = time.monotonic() + 29.5  # below the 30s reserve floor
        with pytest.raises(storage.FirestoreContentionExhausted) as caught:
            with retry_deadline_scope(deadline):
                store.run(lambda tx: True, operation=LABEL)
        assert caught.value.reason == 'deadline_exhausted'
        assert retry.sleeps == [pytest.approx(0.1, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_deadline_reserve_stops_attempt2_fleet0_3_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=10**6)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        seed_label_doc_here(client, WALL0 + 0.3)
        deadline = time.monotonic() + 29.5  # below the 30s reserve floor
        with pytest.raises(storage.FirestoreContentionExhausted) as caught:
            with retry_deadline_scope(deadline):
                store.run(lambda tx: True, operation=LABEL)
        assert caught.value.reason == 'deadline_exhausted'
        assert retry.sleeps == [pytest.approx(0.4000000000465661, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_deadline_reserve_stops_attempt2_fleet0_3_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=10**6)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        seed_label_doc_here(client, WALL0 + 0.3)
        deadline = time.monotonic() + 29.5  # below the 30s reserve floor
        with pytest.raises(storage.FirestoreContentionExhausted) as caught:
            with retry_deadline_scope(deadline):
                store.run(lambda tx: True, operation=LABEL)
        assert caught.value.reason == 'deadline_exhausted'
        assert retry.sleeps == [pytest.approx(0.4000000000465661, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_deadline_reserve_stops_attempt2_fleet2_0_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=10**6)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        seed_label_doc_here(client, WALL0 + 2.0)
        deadline = time.monotonic() + 29.5  # below the 30s reserve floor
        with pytest.raises(storage.FirestoreContentionExhausted) as caught:
            with retry_deadline_scope(deadline):
                store.run(lambda tx: True, operation=LABEL)
        assert caught.value.reason == 'deadline_exhausted'
        assert retry.sleeps == [pytest.approx(2.1, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_deadline_reserve_stops_attempt2_fleet2_0_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=10**6)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        seed_label_doc_here(client, WALL0 + 2.0)
        deadline = time.monotonic() + 29.5  # below the 30s reserve floor
        with pytest.raises(storage.FirestoreContentionExhausted) as caught:
            with retry_deadline_scope(deadline):
                store.run(lambda tx: True, operation=LABEL)
        assert caught.value.reason == 'deadline_exhausted'
        assert retry.sleeps == [pytest.approx(2.1, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_deadline_reserve_stops_attempt2_fleet3_9_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=10**6)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        seed_label_doc_here(client, WALL0 + 3.9)
        deadline = time.monotonic() + 29.5  # below the 30s reserve floor
        with pytest.raises(storage.FirestoreContentionExhausted) as caught:
            with retry_deadline_scope(deadline):
                store.run(lambda tx: True, operation=LABEL)
        assert caught.value.reason == 'deadline_exhausted'
        assert retry.sleeps == [pytest.approx(4.000000000023283, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_deadline_reserve_stops_attempt2_fleet3_9_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=10**6)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        seed_label_doc_here(client, WALL0 + 3.9)
        deadline = time.monotonic() + 29.5  # below the 30s reserve floor
        with pytest.raises(storage.FirestoreContentionExhausted) as caught:
            with retry_deadline_scope(deadline):
                store.run(lambda tx: True, operation=LABEL)
        assert caught.value.reason == 'deadline_exhausted'
        assert retry.sleeps == [pytest.approx(4.000000000023283, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_deadline_reserve_stops_attempt2_spill0_6_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=10**6)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        seed_spill_here(client, WALL0 + 0.6)
        deadline = time.monotonic() + 29.5  # below the 30s reserve floor
        with pytest.raises(storage.FirestoreContentionExhausted) as caught:
            with retry_deadline_scope(deadline):
                store.run(lambda tx: True, operation=LABEL)
        assert caught.value.reason == 'deadline_exhausted'
        assert retry.sleeps == [pytest.approx(0.6999999999767169, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_deadline_reserve_stops_attempt2_spill0_6_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=10**6)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        seed_spill_here(client, WALL0 + 0.6)
        deadline = time.monotonic() + 29.5  # below the 30s reserve floor
        with pytest.raises(storage.FirestoreContentionExhausted) as caught:
            with retry_deadline_scope(deadline):
                store.run(lambda tx: True, operation=LABEL)
        assert caught.value.reason == 'deadline_exhausted'
        assert retry.sleeps == [pytest.approx(0.6999999999767169, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_deadline_reserve_stops_attempt2_spill2_6_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=10**6)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        seed_spill_here(client, WALL0 + 2.6)
        deadline = time.monotonic() + 29.5  # below the 30s reserve floor
        with pytest.raises(storage.FirestoreContentionExhausted) as caught:
            with retry_deadline_scope(deadline):
                store.run(lambda tx: True, operation=LABEL)
        assert caught.value.reason == 'deadline_exhausted'
        assert retry.sleeps == [pytest.approx(1.1, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_deadline_reserve_stops_attempt2_spill2_6_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=10**6)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        seed_spill_here(client, WALL0 + 2.6)
        deadline = time.monotonic() + 29.5  # below the 30s reserve floor
        with pytest.raises(storage.FirestoreContentionExhausted) as caught:
            with retry_deadline_scope(deadline):
                store.run(lambda tx: True, operation=LABEL)
        assert caught.value.reason == 'deadline_exhausted'
        assert retry.sleeps == [pytest.approx(1.1, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_deadline_reserve_stops_attempt2_spill3_9_dj0(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.0)
        client = StormDocsClient(abort_times=10**6)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        seed_spill_here(client, WALL0 + 3.9)
        deadline = time.monotonic() + 29.5  # below the 30s reserve floor
        with pytest.raises(storage.FirestoreContentionExhausted) as caught:
            with retry_deadline_scope(deadline):
                store.run(lambda tx: True, operation=LABEL)
        assert caught.value.reason == 'deadline_exhausted'
        assert retry.sleeps == [pytest.approx(1.1, abs=1e-09)]
    finally:
        reset_registries()


def test_chain_deadline_reserve_stops_attempt2_spill3_9_dj0p75(monkeypatch) -> None:
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks(damper_jitter=0.75)
        client = StormDocsClient(abort_times=10**6)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        seed_spill_here(client, WALL0 + 3.9)
        deadline = time.monotonic() + 29.5  # below the 30s reserve floor
        with pytest.raises(storage.FirestoreContentionExhausted) as caught:
            with retry_deadline_scope(deadline):
                store.run(lambda tx: True, operation=LABEL)
        assert caught.value.reason == 'deadline_exhausted'
        assert retry.sleeps == [pytest.approx(1.1, abs=1e-09)]
    finally:
        reset_registries()
