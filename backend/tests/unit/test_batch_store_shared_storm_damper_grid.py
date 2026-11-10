"""Shared-storm-damper registry parity grid.

Every cell drives real ``FirestoreStore.run`` paths through the process-shared
damper registry with an injected clock, and asserts the exact wait vector (or
log line, or stamp) the documented formulas produce. Ladder and gate
expectations are computed at generation time from the documented formulas and
written as literals:

  arm ladder    d(k, j) = min(4.0, 0.25 * 2**min(k-1, 4)) * (0.5 + 0.5*j)
  equal jitter  floor(i) = (0.2 * 2**(i-1) capped at 4.0) / 2 at chain jitter 0
  wave rung     w(i, j)  = d(i, j) (same ladder, indexed by the failed attempt)
  gate rung i   the sibling window d(f, j) below rung three;
                max(d(f, j), w(i, j)) from rung three
  entry rule    a window armed before the chain is waited exactly once, at
                entry; only a window armed mid-chain reaches the rung gates

Sections: G1 sibling entry consults; G2 gated rungs under mid-chain arms;
G3 retry-after stamp parity; G4 namespace isolation; G5 label isolation;
G6 cap plateau; G8 generation guard across instances; G9 kill-switch dormancy;
G10 reset seam and injection isolation; G12 two-label coexistence; G13 the
per-call construction shape; G14 parity pins; G15 per-chain wave draws;
G16 log taxonomy.

Failure-Class: FC-storm-damper-window-dies-with-its-store-instance
"""

import logging
from pathlib import Path
from unittest.mock import Mock

import pytest
from google.api_core.exceptions import Aborted

from database import batch_pipeline_store as storage

BACKEND = Path(__file__).resolve().parents[2]
FC_TOKEN = 'FC-storm-damper-window-dies-with-its-store-instance'
NS = 'batch_pipeline_dev'
BASE = storage.FirestoreStore.STORM_DAMPER_BASE_SECONDS
CAP = storage.FirestoreStore.STORM_DAMPER_CAP_SECONDS
STEPS = storage.FirestoreStore.STORM_DAMPER_LADDER_STEPS


class AbortThenCommitTx:
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
    def __init__(self, now=100.0, jitter=0.0):
        self.now = now
        self.jitter = jitter
        self.sleeps = []

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        assert seconds >= 0
        self.sleeps.append(seconds)
        self.now += seconds

    def random_value(self):
        return self.jitter


def shared_damper(namespace=NS, jitter=0.0, now=100.0):
    clock = FakeClock(now=now, jitter=jitter)
    damper = storage.shared_storm_damper(namespace)
    damper._monotonic = clock.monotonic
    damper._sleeper = clock.sleep
    damper._random_value = clock.random_value
    return damper, clock


def default_store(mp, ns=NS, client=None):
    mp.setenv('OMI_ENV_STAGE', 'prod' if ns == 'batch_pipeline_prod' else 'dev')
    if ns.startswith('batch_pipeline_test_'):
        # A test namespace admits only a client bound to the loopback emulator;
        # hand it a Mock whose binding attribute matches so no chain ever
        # resolves a real client.
        mp.setenv('FIRESTORE_EMULATOR_HOST', '127.0.0.1:8080')
        bound = Mock()
        bound._emulator_host = '127.0.0.1:8080'
        if client is not None:
            bound.transaction.side_effect = client.transaction.side_effect
        return storage.FirestoreStore(ns, firestore_client=bound)
    return storage.FirestoreStore(ns, firestore_client=client)


def exhausting_client(abort_times=10**6):
    client = Mock()
    client.transaction.side_effect = lambda max_attempts=5: AbortThenCommitTx(abort_times)
    return client


def healthy_client():
    client = Mock()
    client.transaction.side_effect = lambda max_attempts=5: AbortThenCommitTx(0)
    return client


def aborting_chain_client(aborts):
    client = Mock()
    remaining = {'value': aborts}

    def transaction_factory(max_attempts=5):
        if remaining['value'] > 0:
            remaining['value'] -= 1
            return AbortThenCommitTx(1)
        return AbortThenCommitTx(0)

    client.transaction.side_effect = transaction_factory
    return client


def patch_chain(mp, sleep_target):
    actual = storage.run_with_transaction_contention_retry

    def factory(*args, **kwargs):
        kwargs.setdefault('sleep', sleep_target)
        kwargs.setdefault('random_value', lambda: 0.0)
        return actual(*args, **kwargs)

    mp.setattr(storage, 'run_with_transaction_contention_retry', factory)


@pytest.fixture
def mp(monkeypatch):
    """Short alias the generated cells use for monkeypatch."""
    return monkeypatch


@pytest.fixture(autouse=True)
def _silent_chains(mp):
    """Discard the retry chain's own equal-jitter sleeps; damper sleeps stay on the clock."""
    patch_chain(mp, lambda _seconds: None)


def exhaust_run(store, label, times=1):
    error = None
    for _ in range(times):
        try:
            store.run(lambda tx: True, operation=label)
        except storage.FirestoreContentionExhausted as caught:
            error = caught
        else:
            raise AssertionError('expected exhaustion')
    return error


def mid_chain_arm_body(damper, label, arm_on):
    state = {'calls': 0}

    def body(_tx):
        state['calls'] += 1
        if state['calls'] == arm_on:
            damper.arm(label)
        return 'ok'

    return body


def test_g1_entry_consult_two_instance_batch_merge_commit_k1_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=1)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps == [0.125]


def test_g1_entry_consult_two_instance_batch_merge_commit_k1_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=1)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps == [0.15625]


def test_g1_entry_consult_two_instance_batch_merge_commit_k1_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=1)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps == [0.1875]


def test_g1_entry_consult_two_instance_batch_merge_commit_k1_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=1)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps == [0.25]


def test_g1_entry_consult_two_instance_batch_merge_commit_k2_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=2)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps == [0.125, 0.25]


def test_g1_entry_consult_two_instance_batch_merge_commit_k2_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=2)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps == [0.15625, 0.3125]


def test_g1_entry_consult_two_instance_batch_merge_commit_k2_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=2)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps == [0.1875, 0.375]


def test_g1_entry_consult_two_instance_batch_merge_commit_k2_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=2)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps == [0.25, 0.5]


def test_g1_entry_consult_two_instance_batch_merge_commit_k3_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=3)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps == [0.125, 0.25, 0.5]


def test_g1_entry_consult_two_instance_batch_merge_commit_k3_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=3)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps == [0.15625, 0.3125, 0.625]


def test_g1_entry_consult_two_instance_batch_merge_commit_k3_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=3)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps == [0.1875, 0.375, 0.75]


def test_g1_entry_consult_two_instance_batch_merge_commit_k3_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=3)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps == [0.25, 0.5, 1.0]


def test_g1_entry_consult_two_instance_batch_merge_commit_k4_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=4)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps == [0.125, 0.25, 0.5, 1.0]


def test_g1_entry_consult_two_instance_batch_merge_commit_k4_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=4)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps == [0.15625, 0.3125, 0.625, 1.25]


def test_g1_entry_consult_two_instance_batch_merge_commit_k4_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=4)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps == [0.1875, 0.375, 0.75, 1.5]


def test_g1_entry_consult_two_instance_batch_merge_commit_k4_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=4)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps == [0.25, 0.5, 1.0, 2.0]


def test_g1_entry_consult_two_instance_batch_merge_commit_k5_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=5)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps == [0.125, 0.25, 0.5, 1.0, 2.0]


def test_g1_entry_consult_two_instance_batch_merge_commit_k5_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=5)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps == [0.15625, 0.3125, 0.625, 1.25, 2.5]


def test_g1_entry_consult_two_instance_batch_merge_commit_k5_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=5)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps == [0.1875, 0.375, 0.75, 1.5, 3.0]


def test_g1_entry_consult_two_instance_batch_merge_commit_k5_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=5)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps == [0.25, 0.5, 1.0, 2.0, 4.0]


def test_g1_entry_consult_two_instance_batch_merge_commit_k6_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=6)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps == [0.125, 0.25, 0.5, 1.0, 2.0, 2.0]


def test_g1_entry_consult_two_instance_batch_merge_commit_k6_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=6)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps == [0.15625, 0.3125, 0.625, 1.25, 2.5, 2.5]


def test_g1_entry_consult_two_instance_batch_merge_commit_k6_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=6)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps == [0.1875, 0.375, 0.75, 1.5, 3.0, 3.0]


def test_g1_entry_consult_two_instance_batch_merge_commit_k6_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=6)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps == [0.25, 0.5, 1.0, 2.0, 4.0, 4.0]


def test_g1_entry_consult_two_instance_batch_merge_commit_k7_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=7)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps == [0.125, 0.25, 0.5, 1.0, 2.0, 2.0, 2.0]


def test_g1_entry_consult_two_instance_batch_merge_commit_k7_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=7)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps == [0.15625, 0.3125, 0.625, 1.25, 2.5, 2.5, 2.5]


def test_g1_entry_consult_two_instance_batch_merge_commit_k7_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=7)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps == [0.1875, 0.375, 0.75, 1.5, 3.0, 3.0, 3.0]


def test_g1_entry_consult_two_instance_batch_merge_commit_k7_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=7)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps == [0.25, 0.5, 1.0, 2.0, 4.0, 4.0, 4.0]


def test_g1_entry_consult_two_instance_batch_merge_commit_k8_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=8)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps == [0.125, 0.25, 0.5, 1.0, 2.0, 2.0, 2.0, 2.0]


def test_g1_entry_consult_two_instance_batch_merge_commit_k8_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=8)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps == [0.15625, 0.3125, 0.625, 1.25, 2.5, 2.5, 2.5, 2.5]


def test_g1_entry_consult_two_instance_batch_merge_commit_k8_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=8)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps == [0.1875, 0.375, 0.75, 1.5, 3.0, 3.0, 3.0, 3.0]


def test_g1_entry_consult_two_instance_batch_merge_commit_k8_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=8)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps == [0.25, 0.5, 1.0, 2.0, 4.0, 4.0, 4.0, 4.0]


def test_g1_entry_consult_two_instance_batch_merge_commit_k9_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=9)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps == [0.125, 0.25, 0.5, 1.0, 2.0, 2.0, 2.0, 2.0, 2.0]


def test_g1_entry_consult_two_instance_batch_merge_commit_k9_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=9)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps == [0.15625, 0.3125, 0.625, 1.25, 2.5, 2.5, 2.5, 2.5, 2.5]


def test_g1_entry_consult_two_instance_batch_merge_commit_k9_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=9)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps == [0.1875, 0.375, 0.75, 1.5, 3.0, 3.0, 3.0, 3.0, 3.0]


def test_g1_entry_consult_two_instance_batch_merge_commit_k9_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=9)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps == [0.25, 0.5, 1.0, 2.0, 4.0, 4.0, 4.0, 4.0, 4.0]


def test_g1_entry_consult_two_instance_batch_merge_commit_k10_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=10)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps == [0.125, 0.25, 0.5, 1.0, 2.0, 2.0, 2.0, 2.0, 2.0, 2.0]


def test_g1_entry_consult_two_instance_batch_merge_commit_k10_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=10)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps == [0.15625, 0.3125, 0.625, 1.25, 2.5, 2.5, 2.5, 2.5, 2.5, 2.5]


def test_g1_entry_consult_two_instance_batch_merge_commit_k10_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=10)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps == [0.1875, 0.375, 0.75, 1.5, 3.0, 3.0, 3.0, 3.0, 3.0, 3.0]


def test_g1_entry_consult_two_instance_batch_merge_commit_k10_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=10)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps == [0.25, 0.5, 1.0, 2.0, 4.0, 4.0, 4.0, 4.0, 4.0, 4.0]


def test_g1_entry_consult_two_instance_batch_provider_stt_k1_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=1)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert clock.sleeps == [0.125]


def test_g1_entry_consult_two_instance_batch_provider_stt_k1_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=1)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert clock.sleeps == [0.15625]


def test_g1_entry_consult_two_instance_batch_provider_stt_k1_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=1)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert clock.sleeps == [0.1875]


def test_g1_entry_consult_two_instance_batch_provider_stt_k1_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=1)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert clock.sleeps == [0.25]


def test_g1_entry_consult_two_instance_batch_provider_stt_k2_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=2)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert clock.sleeps == [0.125, 0.25]


def test_g1_entry_consult_two_instance_batch_provider_stt_k2_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=2)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert clock.sleeps == [0.15625, 0.3125]


def test_g1_entry_consult_two_instance_batch_provider_stt_k2_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=2)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert clock.sleeps == [0.1875, 0.375]


def test_g1_entry_consult_two_instance_batch_provider_stt_k2_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=2)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert clock.sleeps == [0.25, 0.5]


def test_g1_entry_consult_two_instance_batch_provider_stt_k3_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=3)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert clock.sleeps == [0.125, 0.25, 0.5]


def test_g1_entry_consult_two_instance_batch_provider_stt_k3_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=3)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert clock.sleeps == [0.15625, 0.3125, 0.625]


def test_g1_entry_consult_two_instance_batch_provider_stt_k3_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=3)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert clock.sleeps == [0.1875, 0.375, 0.75]


def test_g1_entry_consult_two_instance_batch_provider_stt_k3_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=3)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert clock.sleeps == [0.25, 0.5, 1.0]


def test_g1_entry_consult_two_instance_batch_provider_stt_k4_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=4)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert clock.sleeps == [0.125, 0.25, 0.5, 1.0]


def test_g1_entry_consult_two_instance_batch_provider_stt_k4_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=4)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert clock.sleeps == [0.15625, 0.3125, 0.625, 1.25]


def test_g1_entry_consult_two_instance_batch_provider_stt_k4_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=4)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert clock.sleeps == [0.1875, 0.375, 0.75, 1.5]


def test_g1_entry_consult_two_instance_batch_provider_stt_k4_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=4)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert clock.sleeps == [0.25, 0.5, 1.0, 2.0]


def test_g1_entry_consult_two_instance_batch_provider_stt_k5_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=5)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert clock.sleeps == [0.125, 0.25, 0.5, 1.0, 2.0]


def test_g1_entry_consult_two_instance_batch_provider_stt_k5_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=5)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert clock.sleeps == [0.15625, 0.3125, 0.625, 1.25, 2.5]


def test_g1_entry_consult_two_instance_batch_provider_stt_k5_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=5)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert clock.sleeps == [0.1875, 0.375, 0.75, 1.5, 3.0]


def test_g1_entry_consult_two_instance_batch_provider_stt_k5_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=5)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert clock.sleeps == [0.25, 0.5, 1.0, 2.0, 4.0]


def test_g1_entry_consult_two_instance_batch_provider_stt_k6_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=6)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert clock.sleeps == [0.125, 0.25, 0.5, 1.0, 2.0, 2.0]


def test_g1_entry_consult_two_instance_batch_provider_stt_k6_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=6)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert clock.sleeps == [0.15625, 0.3125, 0.625, 1.25, 2.5, 2.5]


def test_g1_entry_consult_two_instance_batch_provider_stt_k6_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=6)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert clock.sleeps == [0.1875, 0.375, 0.75, 1.5, 3.0, 3.0]


def test_g1_entry_consult_two_instance_batch_provider_stt_k6_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=6)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert clock.sleeps == [0.25, 0.5, 1.0, 2.0, 4.0, 4.0]


def test_g1_entry_consult_two_instance_batch_provider_stt_k7_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=7)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert clock.sleeps == [0.125, 0.25, 0.5, 1.0, 2.0, 2.0, 2.0]


def test_g1_entry_consult_two_instance_batch_provider_stt_k7_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=7)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert clock.sleeps == [0.15625, 0.3125, 0.625, 1.25, 2.5, 2.5, 2.5]


def test_g1_entry_consult_two_instance_batch_provider_stt_k7_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=7)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert clock.sleeps == [0.1875, 0.375, 0.75, 1.5, 3.0, 3.0, 3.0]


def test_g1_entry_consult_two_instance_batch_provider_stt_k7_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=7)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert clock.sleeps == [0.25, 0.5, 1.0, 2.0, 4.0, 4.0, 4.0]


def test_g1_entry_consult_two_instance_batch_provider_stt_k8_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=8)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert clock.sleeps == [0.125, 0.25, 0.5, 1.0, 2.0, 2.0, 2.0, 2.0]


def test_g1_entry_consult_two_instance_batch_provider_stt_k8_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=8)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert clock.sleeps == [0.15625, 0.3125, 0.625, 1.25, 2.5, 2.5, 2.5, 2.5]


def test_g1_entry_consult_two_instance_batch_provider_stt_k8_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=8)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert clock.sleeps == [0.1875, 0.375, 0.75, 1.5, 3.0, 3.0, 3.0, 3.0]


def test_g1_entry_consult_two_instance_batch_provider_stt_k8_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=8)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert clock.sleeps == [0.25, 0.5, 1.0, 2.0, 4.0, 4.0, 4.0, 4.0]


def test_g1_entry_consult_two_instance_batch_provider_stt_k9_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=9)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert clock.sleeps == [0.125, 0.25, 0.5, 1.0, 2.0, 2.0, 2.0, 2.0, 2.0]


def test_g1_entry_consult_two_instance_batch_provider_stt_k9_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=9)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert clock.sleeps == [0.15625, 0.3125, 0.625, 1.25, 2.5, 2.5, 2.5, 2.5, 2.5]


def test_g1_entry_consult_two_instance_batch_provider_stt_k9_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=9)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert clock.sleeps == [0.1875, 0.375, 0.75, 1.5, 3.0, 3.0, 3.0, 3.0, 3.0]


def test_g1_entry_consult_two_instance_batch_provider_stt_k9_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=9)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert clock.sleeps == [0.25, 0.5, 1.0, 2.0, 4.0, 4.0, 4.0, 4.0, 4.0]


def test_g1_entry_consult_two_instance_batch_provider_stt_k10_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=10)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert clock.sleeps == [0.125, 0.25, 0.5, 1.0, 2.0, 2.0, 2.0, 2.0, 2.0, 2.0]


def test_g1_entry_consult_two_instance_batch_provider_stt_k10_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=10)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert clock.sleeps == [0.15625, 0.3125, 0.625, 1.25, 2.5, 2.5, 2.5, 2.5, 2.5, 2.5]


def test_g1_entry_consult_two_instance_batch_provider_stt_k10_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=10)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert clock.sleeps == [0.1875, 0.375, 0.75, 1.5, 3.0, 3.0, 3.0, 3.0, 3.0, 3.0]


def test_g1_entry_consult_two_instance_batch_provider_stt_k10_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=10)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert clock.sleeps == [0.25, 0.5, 1.0, 2.0, 4.0, 4.0, 4.0, 4.0, 4.0, 4.0]


def test_g1_entry_consult_two_instance_batch_intake_status_k1_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_intake_status', times=1)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_intake_status')
    assert clock.sleeps == [0.125]


def test_g1_entry_consult_two_instance_batch_intake_status_k1_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_intake_status', times=1)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_intake_status')
    assert clock.sleeps == [0.15625]


def test_g1_entry_consult_two_instance_batch_intake_status_k1_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_intake_status', times=1)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_intake_status')
    assert clock.sleeps == [0.1875]


def test_g1_entry_consult_two_instance_batch_intake_status_k1_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_intake_status', times=1)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_intake_status')
    assert clock.sleeps == [0.25]


def test_g1_entry_consult_two_instance_batch_intake_status_k2_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_intake_status', times=2)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_intake_status')
    assert clock.sleeps == [0.125, 0.25]


def test_g1_entry_consult_two_instance_batch_intake_status_k2_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_intake_status', times=2)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_intake_status')
    assert clock.sleeps == [0.15625, 0.3125]


def test_g1_entry_consult_two_instance_batch_intake_status_k2_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_intake_status', times=2)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_intake_status')
    assert clock.sleeps == [0.1875, 0.375]


def test_g1_entry_consult_two_instance_batch_intake_status_k2_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_intake_status', times=2)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_intake_status')
    assert clock.sleeps == [0.25, 0.5]


def test_g1_entry_consult_two_instance_batch_intake_status_k3_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_intake_status', times=3)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_intake_status')
    assert clock.sleeps == [0.125, 0.25, 0.5]


def test_g1_entry_consult_two_instance_batch_intake_status_k3_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_intake_status', times=3)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_intake_status')
    assert clock.sleeps == [0.15625, 0.3125, 0.625]


def test_g1_entry_consult_two_instance_batch_intake_status_k3_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_intake_status', times=3)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_intake_status')
    assert clock.sleeps == [0.1875, 0.375, 0.75]


def test_g1_entry_consult_two_instance_batch_intake_status_k3_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_intake_status', times=3)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_intake_status')
    assert clock.sleeps == [0.25, 0.5, 1.0]


def test_g1_entry_consult_two_instance_batch_intake_status_k4_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_intake_status', times=4)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_intake_status')
    assert clock.sleeps == [0.125, 0.25, 0.5, 1.0]


def test_g1_entry_consult_two_instance_batch_intake_status_k4_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_intake_status', times=4)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_intake_status')
    assert clock.sleeps == [0.15625, 0.3125, 0.625, 1.25]


def test_g1_entry_consult_two_instance_batch_intake_status_k4_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_intake_status', times=4)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_intake_status')
    assert clock.sleeps == [0.1875, 0.375, 0.75, 1.5]


def test_g1_entry_consult_two_instance_batch_intake_status_k4_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_intake_status', times=4)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_intake_status')
    assert clock.sleeps == [0.25, 0.5, 1.0, 2.0]


def test_g1_entry_consult_two_instance_batch_intake_status_k5_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_intake_status', times=5)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_intake_status')
    assert clock.sleeps == [0.125, 0.25, 0.5, 1.0, 2.0]


def test_g1_entry_consult_two_instance_batch_intake_status_k5_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_intake_status', times=5)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_intake_status')
    assert clock.sleeps == [0.15625, 0.3125, 0.625, 1.25, 2.5]


def test_g1_entry_consult_two_instance_batch_intake_status_k5_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_intake_status', times=5)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_intake_status')
    assert clock.sleeps == [0.1875, 0.375, 0.75, 1.5, 3.0]


def test_g1_entry_consult_two_instance_batch_intake_status_k5_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_intake_status', times=5)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_intake_status')
    assert clock.sleeps == [0.25, 0.5, 1.0, 2.0, 4.0]


def test_g1_entry_consult_two_instance_batch_intake_status_k6_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_intake_status', times=6)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_intake_status')
    assert clock.sleeps == [0.125, 0.25, 0.5, 1.0, 2.0, 2.0]


def test_g1_entry_consult_two_instance_batch_intake_status_k6_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_intake_status', times=6)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_intake_status')
    assert clock.sleeps == [0.15625, 0.3125, 0.625, 1.25, 2.5, 2.5]


def test_g1_entry_consult_two_instance_batch_intake_status_k6_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_intake_status', times=6)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_intake_status')
    assert clock.sleeps == [0.1875, 0.375, 0.75, 1.5, 3.0, 3.0]


def test_g1_entry_consult_two_instance_batch_intake_status_k6_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_intake_status', times=6)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_intake_status')
    assert clock.sleeps == [0.25, 0.5, 1.0, 2.0, 4.0, 4.0]


def test_g1_entry_consult_two_instance_batch_intake_status_k7_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_intake_status', times=7)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_intake_status')
    assert clock.sleeps == [0.125, 0.25, 0.5, 1.0, 2.0, 2.0, 2.0]


def test_g1_entry_consult_two_instance_batch_intake_status_k7_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_intake_status', times=7)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_intake_status')
    assert clock.sleeps == [0.15625, 0.3125, 0.625, 1.25, 2.5, 2.5, 2.5]


def test_g1_entry_consult_two_instance_batch_intake_status_k7_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_intake_status', times=7)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_intake_status')
    assert clock.sleeps == [0.1875, 0.375, 0.75, 1.5, 3.0, 3.0, 3.0]


def test_g1_entry_consult_two_instance_batch_intake_status_k7_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_intake_status', times=7)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_intake_status')
    assert clock.sleeps == [0.25, 0.5, 1.0, 2.0, 4.0, 4.0, 4.0]


def test_g1_entry_consult_two_instance_batch_intake_status_k8_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_intake_status', times=8)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_intake_status')
    assert clock.sleeps == [0.125, 0.25, 0.5, 1.0, 2.0, 2.0, 2.0, 2.0]


def test_g1_entry_consult_two_instance_batch_intake_status_k8_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_intake_status', times=8)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_intake_status')
    assert clock.sleeps == [0.15625, 0.3125, 0.625, 1.25, 2.5, 2.5, 2.5, 2.5]


def test_g1_entry_consult_two_instance_batch_intake_status_k8_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_intake_status', times=8)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_intake_status')
    assert clock.sleeps == [0.1875, 0.375, 0.75, 1.5, 3.0, 3.0, 3.0, 3.0]


def test_g1_entry_consult_two_instance_batch_intake_status_k8_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_intake_status', times=8)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_intake_status')
    assert clock.sleeps == [0.25, 0.5, 1.0, 2.0, 4.0, 4.0, 4.0, 4.0]


def test_g1_entry_consult_two_instance_batch_intake_status_k9_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_intake_status', times=9)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_intake_status')
    assert clock.sleeps == [0.125, 0.25, 0.5, 1.0, 2.0, 2.0, 2.0, 2.0, 2.0]


def test_g1_entry_consult_two_instance_batch_intake_status_k9_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_intake_status', times=9)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_intake_status')
    assert clock.sleeps == [0.15625, 0.3125, 0.625, 1.25, 2.5, 2.5, 2.5, 2.5, 2.5]


def test_g1_entry_consult_two_instance_batch_intake_status_k9_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_intake_status', times=9)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_intake_status')
    assert clock.sleeps == [0.1875, 0.375, 0.75, 1.5, 3.0, 3.0, 3.0, 3.0, 3.0]


def test_g1_entry_consult_two_instance_batch_intake_status_k9_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_intake_status', times=9)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_intake_status')
    assert clock.sleeps == [0.25, 0.5, 1.0, 2.0, 4.0, 4.0, 4.0, 4.0, 4.0]


def test_g1_entry_consult_two_instance_batch_intake_status_k10_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_intake_status', times=10)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_intake_status')
    assert clock.sleeps == [0.125, 0.25, 0.5, 1.0, 2.0, 2.0, 2.0, 2.0, 2.0, 2.0]


def test_g1_entry_consult_two_instance_batch_intake_status_k10_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_intake_status', times=10)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_intake_status')
    assert clock.sleeps == [0.15625, 0.3125, 0.625, 1.25, 2.5, 2.5, 2.5, 2.5, 2.5, 2.5]


def test_g1_entry_consult_two_instance_batch_intake_status_k10_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_intake_status', times=10)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_intake_status')
    assert clock.sleeps == [0.1875, 0.375, 0.75, 1.5, 3.0, 3.0, 3.0, 3.0, 3.0, 3.0]


def test_g1_entry_consult_two_instance_batch_intake_status_k10_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_intake_status', times=10)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_intake_status')
    assert clock.sleeps == [0.25, 0.5, 1.0, 2.0, 4.0, 4.0, 4.0, 4.0, 4.0, 4.0]


def test_g1_entry_consult_two_instance_batch_complete_k1_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_complete', times=1)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_complete')
    assert clock.sleeps == [0.125]


def test_g1_entry_consult_two_instance_batch_complete_k1_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_complete', times=1)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_complete')
    assert clock.sleeps == [0.15625]


def test_g1_entry_consult_two_instance_batch_complete_k1_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_complete', times=1)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_complete')
    assert clock.sleeps == [0.1875]


def test_g1_entry_consult_two_instance_batch_complete_k1_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_complete', times=1)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_complete')
    assert clock.sleeps == [0.25]


def test_g1_entry_consult_two_instance_batch_complete_k2_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_complete', times=2)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_complete')
    assert clock.sleeps == [0.125, 0.25]


def test_g1_entry_consult_two_instance_batch_complete_k2_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_complete', times=2)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_complete')
    assert clock.sleeps == [0.15625, 0.3125]


def test_g1_entry_consult_two_instance_batch_complete_k2_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_complete', times=2)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_complete')
    assert clock.sleeps == [0.1875, 0.375]


def test_g1_entry_consult_two_instance_batch_complete_k2_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_complete', times=2)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_complete')
    assert clock.sleeps == [0.25, 0.5]


def test_g1_entry_consult_two_instance_batch_complete_k3_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_complete', times=3)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_complete')
    assert clock.sleeps == [0.125, 0.25, 0.5]


def test_g1_entry_consult_two_instance_batch_complete_k3_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_complete', times=3)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_complete')
    assert clock.sleeps == [0.15625, 0.3125, 0.625]


def test_g1_entry_consult_two_instance_batch_complete_k3_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_complete', times=3)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_complete')
    assert clock.sleeps == [0.1875, 0.375, 0.75]


def test_g1_entry_consult_two_instance_batch_complete_k3_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_complete', times=3)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_complete')
    assert clock.sleeps == [0.25, 0.5, 1.0]


def test_g1_entry_consult_two_instance_batch_complete_k4_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_complete', times=4)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_complete')
    assert clock.sleeps == [0.125, 0.25, 0.5, 1.0]


def test_g1_entry_consult_two_instance_batch_complete_k4_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_complete', times=4)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_complete')
    assert clock.sleeps == [0.15625, 0.3125, 0.625, 1.25]


def test_g1_entry_consult_two_instance_batch_complete_k4_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_complete', times=4)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_complete')
    assert clock.sleeps == [0.1875, 0.375, 0.75, 1.5]


def test_g1_entry_consult_two_instance_batch_complete_k4_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_complete', times=4)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_complete')
    assert clock.sleeps == [0.25, 0.5, 1.0, 2.0]


def test_g1_entry_consult_two_instance_batch_complete_k5_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_complete', times=5)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_complete')
    assert clock.sleeps == [0.125, 0.25, 0.5, 1.0, 2.0]


def test_g1_entry_consult_two_instance_batch_complete_k5_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_complete', times=5)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_complete')
    assert clock.sleeps == [0.15625, 0.3125, 0.625, 1.25, 2.5]


def test_g1_entry_consult_two_instance_batch_complete_k5_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_complete', times=5)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_complete')
    assert clock.sleeps == [0.1875, 0.375, 0.75, 1.5, 3.0]


def test_g1_entry_consult_two_instance_batch_complete_k5_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_complete', times=5)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_complete')
    assert clock.sleeps == [0.25, 0.5, 1.0, 2.0, 4.0]


def test_g1_entry_consult_two_instance_batch_complete_k6_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_complete', times=6)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_complete')
    assert clock.sleeps == [0.125, 0.25, 0.5, 1.0, 2.0, 2.0]


def test_g1_entry_consult_two_instance_batch_complete_k6_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_complete', times=6)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_complete')
    assert clock.sleeps == [0.15625, 0.3125, 0.625, 1.25, 2.5, 2.5]


def test_g1_entry_consult_two_instance_batch_complete_k6_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_complete', times=6)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_complete')
    assert clock.sleeps == [0.1875, 0.375, 0.75, 1.5, 3.0, 3.0]


def test_g1_entry_consult_two_instance_batch_complete_k6_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_complete', times=6)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_complete')
    assert clock.sleeps == [0.25, 0.5, 1.0, 2.0, 4.0, 4.0]


def test_g1_entry_consult_two_instance_batch_complete_k7_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_complete', times=7)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_complete')
    assert clock.sleeps == [0.125, 0.25, 0.5, 1.0, 2.0, 2.0, 2.0]


def test_g1_entry_consult_two_instance_batch_complete_k7_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_complete', times=7)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_complete')
    assert clock.sleeps == [0.15625, 0.3125, 0.625, 1.25, 2.5, 2.5, 2.5]


def test_g1_entry_consult_two_instance_batch_complete_k7_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_complete', times=7)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_complete')
    assert clock.sleeps == [0.1875, 0.375, 0.75, 1.5, 3.0, 3.0, 3.0]


def test_g1_entry_consult_two_instance_batch_complete_k7_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_complete', times=7)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_complete')
    assert clock.sleeps == [0.25, 0.5, 1.0, 2.0, 4.0, 4.0, 4.0]


def test_g1_entry_consult_two_instance_batch_complete_k8_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_complete', times=8)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_complete')
    assert clock.sleeps == [0.125, 0.25, 0.5, 1.0, 2.0, 2.0, 2.0, 2.0]


def test_g1_entry_consult_two_instance_batch_complete_k8_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_complete', times=8)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_complete')
    assert clock.sleeps == [0.15625, 0.3125, 0.625, 1.25, 2.5, 2.5, 2.5, 2.5]


def test_g1_entry_consult_two_instance_batch_complete_k8_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_complete', times=8)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_complete')
    assert clock.sleeps == [0.1875, 0.375, 0.75, 1.5, 3.0, 3.0, 3.0, 3.0]


def test_g1_entry_consult_two_instance_batch_complete_k8_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_complete', times=8)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_complete')
    assert clock.sleeps == [0.25, 0.5, 1.0, 2.0, 4.0, 4.0, 4.0, 4.0]


def test_g1_entry_consult_two_instance_batch_complete_k9_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_complete', times=9)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_complete')
    assert clock.sleeps == [0.125, 0.25, 0.5, 1.0, 2.0, 2.0, 2.0, 2.0, 2.0]


def test_g1_entry_consult_two_instance_batch_complete_k9_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_complete', times=9)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_complete')
    assert clock.sleeps == [0.15625, 0.3125, 0.625, 1.25, 2.5, 2.5, 2.5, 2.5, 2.5]


def test_g1_entry_consult_two_instance_batch_complete_k9_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_complete', times=9)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_complete')
    assert clock.sleeps == [0.1875, 0.375, 0.75, 1.5, 3.0, 3.0, 3.0, 3.0, 3.0]


def test_g1_entry_consult_two_instance_batch_complete_k9_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_complete', times=9)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_complete')
    assert clock.sleeps == [0.25, 0.5, 1.0, 2.0, 4.0, 4.0, 4.0, 4.0, 4.0]


def test_g1_entry_consult_two_instance_batch_complete_k10_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_complete', times=10)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_complete')
    assert clock.sleeps == [0.125, 0.25, 0.5, 1.0, 2.0, 2.0, 2.0, 2.0, 2.0, 2.0]


def test_g1_entry_consult_two_instance_batch_complete_k10_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_complete', times=10)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_complete')
    assert clock.sleeps == [0.15625, 0.3125, 0.625, 1.25, 2.5, 2.5, 2.5, 2.5, 2.5, 2.5]


def test_g1_entry_consult_two_instance_batch_complete_k10_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_complete', times=10)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_complete')
    assert clock.sleeps == [0.1875, 0.375, 0.75, 1.5, 3.0, 3.0, 3.0, 3.0, 3.0, 3.0]


def test_g1_entry_consult_two_instance_batch_complete_k10_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_complete', times=10)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_complete')
    assert clock.sleeps == [0.25, 0.5, 1.0, 2.0, 4.0, 4.0, 4.0, 4.0, 4.0, 4.0]


def test_g1_entry_consult_two_instance_batch_recovery_settle_k1_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_recovery_settle', times=1)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_recovery_settle')
    assert clock.sleeps == [0.125]


def test_g1_entry_consult_two_instance_batch_recovery_settle_k1_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_recovery_settle', times=1)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_recovery_settle')
    assert clock.sleeps == [0.15625]


def test_g1_entry_consult_two_instance_batch_recovery_settle_k1_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_recovery_settle', times=1)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_recovery_settle')
    assert clock.sleeps == [0.1875]


def test_g1_entry_consult_two_instance_batch_recovery_settle_k1_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_recovery_settle', times=1)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_recovery_settle')
    assert clock.sleeps == [0.25]


def test_g1_entry_consult_two_instance_batch_recovery_settle_k2_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_recovery_settle', times=2)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_recovery_settle')
    assert clock.sleeps == [0.125, 0.25]


def test_g1_entry_consult_two_instance_batch_recovery_settle_k2_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_recovery_settle', times=2)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_recovery_settle')
    assert clock.sleeps == [0.15625, 0.3125]


def test_g1_entry_consult_two_instance_batch_recovery_settle_k2_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_recovery_settle', times=2)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_recovery_settle')
    assert clock.sleeps == [0.1875, 0.375]


def test_g1_entry_consult_two_instance_batch_recovery_settle_k2_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_recovery_settle', times=2)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_recovery_settle')
    assert clock.sleeps == [0.25, 0.5]


def test_g1_entry_consult_two_instance_batch_recovery_settle_k3_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_recovery_settle', times=3)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_recovery_settle')
    assert clock.sleeps == [0.125, 0.25, 0.5]


def test_g1_entry_consult_two_instance_batch_recovery_settle_k3_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_recovery_settle', times=3)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_recovery_settle')
    assert clock.sleeps == [0.15625, 0.3125, 0.625]


def test_g1_entry_consult_two_instance_batch_recovery_settle_k3_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_recovery_settle', times=3)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_recovery_settle')
    assert clock.sleeps == [0.1875, 0.375, 0.75]


def test_g1_entry_consult_two_instance_batch_recovery_settle_k3_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_recovery_settle', times=3)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_recovery_settle')
    assert clock.sleeps == [0.25, 0.5, 1.0]


def test_g1_entry_consult_two_instance_batch_recovery_settle_k4_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_recovery_settle', times=4)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_recovery_settle')
    assert clock.sleeps == [0.125, 0.25, 0.5, 1.0]


def test_g1_entry_consult_two_instance_batch_recovery_settle_k4_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_recovery_settle', times=4)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_recovery_settle')
    assert clock.sleeps == [0.15625, 0.3125, 0.625, 1.25]


def test_g1_entry_consult_two_instance_batch_recovery_settle_k4_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_recovery_settle', times=4)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_recovery_settle')
    assert clock.sleeps == [0.1875, 0.375, 0.75, 1.5]


def test_g1_entry_consult_two_instance_batch_recovery_settle_k4_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_recovery_settle', times=4)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_recovery_settle')
    assert clock.sleeps == [0.25, 0.5, 1.0, 2.0]


def test_g1_entry_consult_two_instance_batch_recovery_settle_k5_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_recovery_settle', times=5)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_recovery_settle')
    assert clock.sleeps == [0.125, 0.25, 0.5, 1.0, 2.0]


def test_g1_entry_consult_two_instance_batch_recovery_settle_k5_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_recovery_settle', times=5)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_recovery_settle')
    assert clock.sleeps == [0.15625, 0.3125, 0.625, 1.25, 2.5]


def test_g1_entry_consult_two_instance_batch_recovery_settle_k5_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_recovery_settle', times=5)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_recovery_settle')
    assert clock.sleeps == [0.1875, 0.375, 0.75, 1.5, 3.0]


def test_g1_entry_consult_two_instance_batch_recovery_settle_k5_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_recovery_settle', times=5)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_recovery_settle')
    assert clock.sleeps == [0.25, 0.5, 1.0, 2.0, 4.0]


def test_g1_entry_consult_two_instance_batch_recovery_settle_k6_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_recovery_settle', times=6)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_recovery_settle')
    assert clock.sleeps == [0.125, 0.25, 0.5, 1.0, 2.0, 2.0]


def test_g1_entry_consult_two_instance_batch_recovery_settle_k6_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_recovery_settle', times=6)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_recovery_settle')
    assert clock.sleeps == [0.15625, 0.3125, 0.625, 1.25, 2.5, 2.5]


def test_g1_entry_consult_two_instance_batch_recovery_settle_k6_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_recovery_settle', times=6)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_recovery_settle')
    assert clock.sleeps == [0.1875, 0.375, 0.75, 1.5, 3.0, 3.0]


def test_g1_entry_consult_two_instance_batch_recovery_settle_k6_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_recovery_settle', times=6)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_recovery_settle')
    assert clock.sleeps == [0.25, 0.5, 1.0, 2.0, 4.0, 4.0]


def test_g1_entry_consult_two_instance_batch_recovery_settle_k7_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_recovery_settle', times=7)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_recovery_settle')
    assert clock.sleeps == [0.125, 0.25, 0.5, 1.0, 2.0, 2.0, 2.0]


def test_g1_entry_consult_two_instance_batch_recovery_settle_k7_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_recovery_settle', times=7)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_recovery_settle')
    assert clock.sleeps == [0.15625, 0.3125, 0.625, 1.25, 2.5, 2.5, 2.5]


def test_g1_entry_consult_two_instance_batch_recovery_settle_k7_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_recovery_settle', times=7)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_recovery_settle')
    assert clock.sleeps == [0.1875, 0.375, 0.75, 1.5, 3.0, 3.0, 3.0]


def test_g1_entry_consult_two_instance_batch_recovery_settle_k7_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_recovery_settle', times=7)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_recovery_settle')
    assert clock.sleeps == [0.25, 0.5, 1.0, 2.0, 4.0, 4.0, 4.0]


def test_g1_entry_consult_two_instance_batch_recovery_settle_k8_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_recovery_settle', times=8)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_recovery_settle')
    assert clock.sleeps == [0.125, 0.25, 0.5, 1.0, 2.0, 2.0, 2.0, 2.0]


def test_g1_entry_consult_two_instance_batch_recovery_settle_k8_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_recovery_settle', times=8)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_recovery_settle')
    assert clock.sleeps == [0.15625, 0.3125, 0.625, 1.25, 2.5, 2.5, 2.5, 2.5]


def test_g1_entry_consult_two_instance_batch_recovery_settle_k8_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_recovery_settle', times=8)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_recovery_settle')
    assert clock.sleeps == [0.1875, 0.375, 0.75, 1.5, 3.0, 3.0, 3.0, 3.0]


def test_g1_entry_consult_two_instance_batch_recovery_settle_k8_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_recovery_settle', times=8)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_recovery_settle')
    assert clock.sleeps == [0.25, 0.5, 1.0, 2.0, 4.0, 4.0, 4.0, 4.0]


def test_g1_entry_consult_two_instance_batch_recovery_settle_k9_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_recovery_settle', times=9)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_recovery_settle')
    assert clock.sleeps == [0.125, 0.25, 0.5, 1.0, 2.0, 2.0, 2.0, 2.0, 2.0]


def test_g1_entry_consult_two_instance_batch_recovery_settle_k9_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_recovery_settle', times=9)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_recovery_settle')
    assert clock.sleeps == [0.15625, 0.3125, 0.625, 1.25, 2.5, 2.5, 2.5, 2.5, 2.5]


def test_g1_entry_consult_two_instance_batch_recovery_settle_k9_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_recovery_settle', times=9)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_recovery_settle')
    assert clock.sleeps == [0.1875, 0.375, 0.75, 1.5, 3.0, 3.0, 3.0, 3.0, 3.0]


def test_g1_entry_consult_two_instance_batch_recovery_settle_k9_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_recovery_settle', times=9)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_recovery_settle')
    assert clock.sleeps == [0.25, 0.5, 1.0, 2.0, 4.0, 4.0, 4.0, 4.0, 4.0]


def test_g1_entry_consult_two_instance_batch_recovery_settle_k10_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_recovery_settle', times=10)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_recovery_settle')
    assert clock.sleeps == [0.125, 0.25, 0.5, 1.0, 2.0, 2.0, 2.0, 2.0, 2.0, 2.0]


def test_g1_entry_consult_two_instance_batch_recovery_settle_k10_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_recovery_settle', times=10)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_recovery_settle')
    assert clock.sleeps == [0.15625, 0.3125, 0.625, 1.25, 2.5, 2.5, 2.5, 2.5, 2.5, 2.5]


def test_g1_entry_consult_two_instance_batch_recovery_settle_k10_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_recovery_settle', times=10)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_recovery_settle')
    assert clock.sleeps == [0.1875, 0.375, 0.75, 1.5, 3.0, 3.0, 3.0, 3.0, 3.0, 3.0]


def test_g1_entry_consult_two_instance_batch_recovery_settle_k10_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_recovery_settle', times=10)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_recovery_settle')
    assert clock.sleeps == [0.25, 0.5, 1.0, 2.0, 4.0, 4.0, 4.0, 4.0, 4.0, 4.0]


def test_g1_entry_consult_two_instance_batch_pull_shard_scheduler_17_k1_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_pull shard=scheduler_17', times=1)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_pull shard=scheduler_17')
    assert clock.sleeps == [0.125]


def test_g1_entry_consult_two_instance_batch_pull_shard_scheduler_17_k1_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_pull shard=scheduler_17', times=1)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_pull shard=scheduler_17')
    assert clock.sleeps == [0.15625]


def test_g1_entry_consult_two_instance_batch_pull_shard_scheduler_17_k1_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_pull shard=scheduler_17', times=1)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_pull shard=scheduler_17')
    assert clock.sleeps == [0.1875]


def test_g1_entry_consult_two_instance_batch_pull_shard_scheduler_17_k1_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_pull shard=scheduler_17', times=1)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_pull shard=scheduler_17')
    assert clock.sleeps == [0.25]


def test_g1_entry_consult_two_instance_batch_pull_shard_scheduler_17_k2_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_pull shard=scheduler_17', times=2)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_pull shard=scheduler_17')
    assert clock.sleeps == [0.125, 0.25]


def test_g1_entry_consult_two_instance_batch_pull_shard_scheduler_17_k2_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_pull shard=scheduler_17', times=2)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_pull shard=scheduler_17')
    assert clock.sleeps == [0.15625, 0.3125]


def test_g1_entry_consult_two_instance_batch_pull_shard_scheduler_17_k2_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_pull shard=scheduler_17', times=2)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_pull shard=scheduler_17')
    assert clock.sleeps == [0.1875, 0.375]


def test_g1_entry_consult_two_instance_batch_pull_shard_scheduler_17_k2_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_pull shard=scheduler_17', times=2)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_pull shard=scheduler_17')
    assert clock.sleeps == [0.25, 0.5]


def test_g1_entry_consult_two_instance_batch_pull_shard_scheduler_17_k3_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_pull shard=scheduler_17', times=3)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_pull shard=scheduler_17')
    assert clock.sleeps == [0.125, 0.25, 0.5]


def test_g1_entry_consult_two_instance_batch_pull_shard_scheduler_17_k3_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_pull shard=scheduler_17', times=3)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_pull shard=scheduler_17')
    assert clock.sleeps == [0.15625, 0.3125, 0.625]


def test_g1_entry_consult_two_instance_batch_pull_shard_scheduler_17_k3_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_pull shard=scheduler_17', times=3)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_pull shard=scheduler_17')
    assert clock.sleeps == [0.1875, 0.375, 0.75]


def test_g1_entry_consult_two_instance_batch_pull_shard_scheduler_17_k3_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_pull shard=scheduler_17', times=3)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_pull shard=scheduler_17')
    assert clock.sleeps == [0.25, 0.5, 1.0]


def test_g1_entry_consult_two_instance_batch_pull_shard_scheduler_17_k4_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_pull shard=scheduler_17', times=4)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_pull shard=scheduler_17')
    assert clock.sleeps == [0.125, 0.25, 0.5, 1.0]


def test_g1_entry_consult_two_instance_batch_pull_shard_scheduler_17_k4_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_pull shard=scheduler_17', times=4)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_pull shard=scheduler_17')
    assert clock.sleeps == [0.15625, 0.3125, 0.625, 1.25]


def test_g1_entry_consult_two_instance_batch_pull_shard_scheduler_17_k4_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_pull shard=scheduler_17', times=4)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_pull shard=scheduler_17')
    assert clock.sleeps == [0.1875, 0.375, 0.75, 1.5]


def test_g1_entry_consult_two_instance_batch_pull_shard_scheduler_17_k4_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_pull shard=scheduler_17', times=4)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_pull shard=scheduler_17')
    assert clock.sleeps == [0.25, 0.5, 1.0, 2.0]


def test_g1_entry_consult_two_instance_batch_pull_shard_scheduler_17_k5_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_pull shard=scheduler_17', times=5)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_pull shard=scheduler_17')
    assert clock.sleeps == [0.125, 0.25, 0.5, 1.0, 2.0]


def test_g1_entry_consult_two_instance_batch_pull_shard_scheduler_17_k5_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_pull shard=scheduler_17', times=5)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_pull shard=scheduler_17')
    assert clock.sleeps == [0.15625, 0.3125, 0.625, 1.25, 2.5]


def test_g1_entry_consult_two_instance_batch_pull_shard_scheduler_17_k5_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_pull shard=scheduler_17', times=5)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_pull shard=scheduler_17')
    assert clock.sleeps == [0.1875, 0.375, 0.75, 1.5, 3.0]


def test_g1_entry_consult_two_instance_batch_pull_shard_scheduler_17_k5_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_pull shard=scheduler_17', times=5)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_pull shard=scheduler_17')
    assert clock.sleeps == [0.25, 0.5, 1.0, 2.0, 4.0]


def test_g1_entry_consult_two_instance_batch_pull_shard_scheduler_17_k6_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_pull shard=scheduler_17', times=6)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_pull shard=scheduler_17')
    assert clock.sleeps == [0.125, 0.25, 0.5, 1.0, 2.0, 2.0]


def test_g1_entry_consult_two_instance_batch_pull_shard_scheduler_17_k6_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_pull shard=scheduler_17', times=6)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_pull shard=scheduler_17')
    assert clock.sleeps == [0.15625, 0.3125, 0.625, 1.25, 2.5, 2.5]


def test_g1_entry_consult_two_instance_batch_pull_shard_scheduler_17_k6_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_pull shard=scheduler_17', times=6)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_pull shard=scheduler_17')
    assert clock.sleeps == [0.1875, 0.375, 0.75, 1.5, 3.0, 3.0]


def test_g1_entry_consult_two_instance_batch_pull_shard_scheduler_17_k6_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_pull shard=scheduler_17', times=6)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_pull shard=scheduler_17')
    assert clock.sleeps == [0.25, 0.5, 1.0, 2.0, 4.0, 4.0]


def test_g1_entry_consult_two_instance_batch_pull_shard_scheduler_17_k7_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_pull shard=scheduler_17', times=7)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_pull shard=scheduler_17')
    assert clock.sleeps == [0.125, 0.25, 0.5, 1.0, 2.0, 2.0, 2.0]


def test_g1_entry_consult_two_instance_batch_pull_shard_scheduler_17_k7_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_pull shard=scheduler_17', times=7)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_pull shard=scheduler_17')
    assert clock.sleeps == [0.15625, 0.3125, 0.625, 1.25, 2.5, 2.5, 2.5]


def test_g1_entry_consult_two_instance_batch_pull_shard_scheduler_17_k7_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_pull shard=scheduler_17', times=7)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_pull shard=scheduler_17')
    assert clock.sleeps == [0.1875, 0.375, 0.75, 1.5, 3.0, 3.0, 3.0]


def test_g1_entry_consult_two_instance_batch_pull_shard_scheduler_17_k7_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_pull shard=scheduler_17', times=7)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_pull shard=scheduler_17')
    assert clock.sleeps == [0.25, 0.5, 1.0, 2.0, 4.0, 4.0, 4.0]


def test_g1_entry_consult_two_instance_batch_pull_shard_scheduler_17_k8_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_pull shard=scheduler_17', times=8)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_pull shard=scheduler_17')
    assert clock.sleeps == [0.125, 0.25, 0.5, 1.0, 2.0, 2.0, 2.0, 2.0]


def test_g1_entry_consult_two_instance_batch_pull_shard_scheduler_17_k8_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_pull shard=scheduler_17', times=8)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_pull shard=scheduler_17')
    assert clock.sleeps == [0.15625, 0.3125, 0.625, 1.25, 2.5, 2.5, 2.5, 2.5]


def test_g1_entry_consult_two_instance_batch_pull_shard_scheduler_17_k8_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_pull shard=scheduler_17', times=8)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_pull shard=scheduler_17')
    assert clock.sleeps == [0.1875, 0.375, 0.75, 1.5, 3.0, 3.0, 3.0, 3.0]


def test_g1_entry_consult_two_instance_batch_pull_shard_scheduler_17_k8_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_pull shard=scheduler_17', times=8)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_pull shard=scheduler_17')
    assert clock.sleeps == [0.25, 0.5, 1.0, 2.0, 4.0, 4.0, 4.0, 4.0]


def test_g1_entry_consult_two_instance_batch_pull_shard_scheduler_17_k9_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_pull shard=scheduler_17', times=9)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_pull shard=scheduler_17')
    assert clock.sleeps == [0.125, 0.25, 0.5, 1.0, 2.0, 2.0, 2.0, 2.0, 2.0]


def test_g1_entry_consult_two_instance_batch_pull_shard_scheduler_17_k9_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_pull shard=scheduler_17', times=9)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_pull shard=scheduler_17')
    assert clock.sleeps == [0.15625, 0.3125, 0.625, 1.25, 2.5, 2.5, 2.5, 2.5, 2.5]


def test_g1_entry_consult_two_instance_batch_pull_shard_scheduler_17_k9_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_pull shard=scheduler_17', times=9)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_pull shard=scheduler_17')
    assert clock.sleeps == [0.1875, 0.375, 0.75, 1.5, 3.0, 3.0, 3.0, 3.0, 3.0]


def test_g1_entry_consult_two_instance_batch_pull_shard_scheduler_17_k9_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_pull shard=scheduler_17', times=9)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_pull shard=scheduler_17')
    assert clock.sleeps == [0.25, 0.5, 1.0, 2.0, 4.0, 4.0, 4.0, 4.0, 4.0]


def test_g1_entry_consult_two_instance_batch_pull_shard_scheduler_17_k10_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_pull shard=scheduler_17', times=10)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_pull shard=scheduler_17')
    assert clock.sleeps == [0.125, 0.25, 0.5, 1.0, 2.0, 2.0, 2.0, 2.0, 2.0, 2.0]


def test_g1_entry_consult_two_instance_batch_pull_shard_scheduler_17_k10_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_pull shard=scheduler_17', times=10)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_pull shard=scheduler_17')
    assert clock.sleeps == [0.15625, 0.3125, 0.625, 1.25, 2.5, 2.5, 2.5, 2.5, 2.5, 2.5]


def test_g1_entry_consult_two_instance_batch_pull_shard_scheduler_17_k10_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_pull shard=scheduler_17', times=10)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_pull shard=scheduler_17')
    assert clock.sleeps == [0.1875, 0.375, 0.75, 1.5, 3.0, 3.0, 3.0, 3.0, 3.0, 3.0]


def test_g1_entry_consult_two_instance_batch_pull_shard_scheduler_17_k10_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_pull shard=scheduler_17', times=10)
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is damper
    B.run(lambda tx: 'ok', operation='batch_pull shard=scheduler_17')
    assert clock.sleeps == [0.25, 0.5, 1.0, 2.0, 4.0, 4.0, 4.0, 4.0, 4.0, 4.0]


def test_g1_entry_consult_three_instance_batch_merge_commit_k1_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=1)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps == [0.125]


def test_g1_entry_consult_three_instance_batch_merge_commit_k1_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=1)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps == [0.15625]


def test_g1_entry_consult_three_instance_batch_merge_commit_k1_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=1)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps == [0.1875]


def test_g1_entry_consult_three_instance_batch_merge_commit_k1_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=1)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps == [0.25]


def test_g1_entry_consult_three_instance_batch_merge_commit_k2_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=2)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps == [0.125, 0.25]


def test_g1_entry_consult_three_instance_batch_merge_commit_k2_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=2)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps == [0.15625, 0.3125]


def test_g1_entry_consult_three_instance_batch_merge_commit_k2_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=2)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps == [0.1875, 0.375]


def test_g1_entry_consult_three_instance_batch_merge_commit_k2_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=2)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps == [0.25, 0.5]


def test_g1_entry_consult_three_instance_batch_merge_commit_k3_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=3)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps == [0.125, 0.25, 0.5]


def test_g1_entry_consult_three_instance_batch_merge_commit_k3_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=3)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps == [0.15625, 0.3125, 0.625]


def test_g1_entry_consult_three_instance_batch_merge_commit_k3_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=3)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps == [0.1875, 0.375, 0.75]


def test_g1_entry_consult_three_instance_batch_merge_commit_k3_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=3)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps == [0.25, 0.5, 1.0]


def test_g1_entry_consult_three_instance_batch_merge_commit_k4_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=4)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps == [0.125, 0.25, 0.5, 1.0]


def test_g1_entry_consult_three_instance_batch_merge_commit_k4_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=4)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps == [0.15625, 0.3125, 0.625, 1.25]


def test_g1_entry_consult_three_instance_batch_merge_commit_k4_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=4)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps == [0.1875, 0.375, 0.75, 1.5]


def test_g1_entry_consult_three_instance_batch_merge_commit_k4_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=4)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps == [0.25, 0.5, 1.0, 2.0]


def test_g1_entry_consult_three_instance_batch_merge_commit_k5_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=5)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps == [0.125, 0.25, 0.5, 1.0, 2.0]


def test_g1_entry_consult_three_instance_batch_merge_commit_k5_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=5)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps == [0.15625, 0.3125, 0.625, 1.25, 2.5]


def test_g1_entry_consult_three_instance_batch_merge_commit_k5_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=5)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps == [0.1875, 0.375, 0.75, 1.5, 3.0]


def test_g1_entry_consult_three_instance_batch_merge_commit_k5_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=5)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps == [0.25, 0.5, 1.0, 2.0, 4.0]


def test_g1_entry_consult_three_instance_batch_merge_commit_k6_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=6)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps == [0.125, 0.25, 0.5, 1.0, 2.0, 2.0]


def test_g1_entry_consult_three_instance_batch_merge_commit_k6_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=6)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps == [0.15625, 0.3125, 0.625, 1.25, 2.5, 2.5]


def test_g1_entry_consult_three_instance_batch_merge_commit_k6_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=6)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps == [0.1875, 0.375, 0.75, 1.5, 3.0, 3.0]


def test_g1_entry_consult_three_instance_batch_merge_commit_k6_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=6)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps == [0.25, 0.5, 1.0, 2.0, 4.0, 4.0]


def test_g1_entry_consult_three_instance_batch_merge_commit_k7_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=7)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps == [0.125, 0.25, 0.5, 1.0, 2.0, 2.0, 2.0]


def test_g1_entry_consult_three_instance_batch_merge_commit_k7_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=7)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps == [0.15625, 0.3125, 0.625, 1.25, 2.5, 2.5, 2.5]


def test_g1_entry_consult_three_instance_batch_merge_commit_k7_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=7)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps == [0.1875, 0.375, 0.75, 1.5, 3.0, 3.0, 3.0]


def test_g1_entry_consult_three_instance_batch_merge_commit_k7_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=7)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps == [0.25, 0.5, 1.0, 2.0, 4.0, 4.0, 4.0]


def test_g1_entry_consult_three_instance_batch_merge_commit_k8_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=8)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps == [0.125, 0.25, 0.5, 1.0, 2.0, 2.0, 2.0, 2.0]


def test_g1_entry_consult_three_instance_batch_merge_commit_k8_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=8)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps == [0.15625, 0.3125, 0.625, 1.25, 2.5, 2.5, 2.5, 2.5]


def test_g1_entry_consult_three_instance_batch_merge_commit_k8_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=8)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps == [0.1875, 0.375, 0.75, 1.5, 3.0, 3.0, 3.0, 3.0]


def test_g1_entry_consult_three_instance_batch_merge_commit_k8_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=8)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps == [0.25, 0.5, 1.0, 2.0, 4.0, 4.0, 4.0, 4.0]


def test_g1_entry_consult_three_instance_batch_merge_commit_k9_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=9)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps == [0.125, 0.25, 0.5, 1.0, 2.0, 2.0, 2.0, 2.0, 2.0]


def test_g1_entry_consult_three_instance_batch_merge_commit_k9_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=9)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps == [0.15625, 0.3125, 0.625, 1.25, 2.5, 2.5, 2.5, 2.5, 2.5]


def test_g1_entry_consult_three_instance_batch_merge_commit_k9_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=9)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps == [0.1875, 0.375, 0.75, 1.5, 3.0, 3.0, 3.0, 3.0, 3.0]


def test_g1_entry_consult_three_instance_batch_merge_commit_k9_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=9)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps == [0.25, 0.5, 1.0, 2.0, 4.0, 4.0, 4.0, 4.0, 4.0]


def test_g1_entry_consult_three_instance_batch_merge_commit_k10_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=10)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps == [0.125, 0.25, 0.5, 1.0, 2.0, 2.0, 2.0, 2.0, 2.0, 2.0]


def test_g1_entry_consult_three_instance_batch_merge_commit_k10_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=10)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps == [0.15625, 0.3125, 0.625, 1.25, 2.5, 2.5, 2.5, 2.5, 2.5, 2.5]


def test_g1_entry_consult_three_instance_batch_merge_commit_k10_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=10)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps == [0.1875, 0.375, 0.75, 1.5, 3.0, 3.0, 3.0, 3.0, 3.0, 3.0]


def test_g1_entry_consult_three_instance_batch_merge_commit_k10_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=10)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps == [0.25, 0.5, 1.0, 2.0, 4.0, 4.0, 4.0, 4.0, 4.0, 4.0]


def test_g1_entry_consult_three_instance_batch_provider_stt_k1_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=1)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert clock.sleeps == [0.125]


def test_g1_entry_consult_three_instance_batch_provider_stt_k1_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=1)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert clock.sleeps == [0.15625]


def test_g1_entry_consult_three_instance_batch_provider_stt_k1_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=1)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert clock.sleeps == [0.1875]


def test_g1_entry_consult_three_instance_batch_provider_stt_k1_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=1)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert clock.sleeps == [0.25]


def test_g1_entry_consult_three_instance_batch_provider_stt_k2_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=2)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert clock.sleeps == [0.125, 0.25]


def test_g1_entry_consult_three_instance_batch_provider_stt_k2_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=2)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert clock.sleeps == [0.15625, 0.3125]


def test_g1_entry_consult_three_instance_batch_provider_stt_k2_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=2)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert clock.sleeps == [0.1875, 0.375]


def test_g1_entry_consult_three_instance_batch_provider_stt_k2_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=2)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert clock.sleeps == [0.25, 0.5]


def test_g1_entry_consult_three_instance_batch_provider_stt_k3_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=3)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert clock.sleeps == [0.125, 0.25, 0.5]


def test_g1_entry_consult_three_instance_batch_provider_stt_k3_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=3)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert clock.sleeps == [0.15625, 0.3125, 0.625]


def test_g1_entry_consult_three_instance_batch_provider_stt_k3_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=3)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert clock.sleeps == [0.1875, 0.375, 0.75]


def test_g1_entry_consult_three_instance_batch_provider_stt_k3_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=3)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert clock.sleeps == [0.25, 0.5, 1.0]


def test_g1_entry_consult_three_instance_batch_provider_stt_k4_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=4)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert clock.sleeps == [0.125, 0.25, 0.5, 1.0]


def test_g1_entry_consult_three_instance_batch_provider_stt_k4_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=4)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert clock.sleeps == [0.15625, 0.3125, 0.625, 1.25]


def test_g1_entry_consult_three_instance_batch_provider_stt_k4_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=4)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert clock.sleeps == [0.1875, 0.375, 0.75, 1.5]


def test_g1_entry_consult_three_instance_batch_provider_stt_k4_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=4)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert clock.sleeps == [0.25, 0.5, 1.0, 2.0]


def test_g1_entry_consult_three_instance_batch_provider_stt_k5_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=5)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert clock.sleeps == [0.125, 0.25, 0.5, 1.0, 2.0]


def test_g1_entry_consult_three_instance_batch_provider_stt_k5_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=5)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert clock.sleeps == [0.15625, 0.3125, 0.625, 1.25, 2.5]


def test_g1_entry_consult_three_instance_batch_provider_stt_k5_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=5)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert clock.sleeps == [0.1875, 0.375, 0.75, 1.5, 3.0]


def test_g1_entry_consult_three_instance_batch_provider_stt_k5_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=5)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert clock.sleeps == [0.25, 0.5, 1.0, 2.0, 4.0]


def test_g1_entry_consult_three_instance_batch_provider_stt_k6_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=6)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert clock.sleeps == [0.125, 0.25, 0.5, 1.0, 2.0, 2.0]


def test_g1_entry_consult_three_instance_batch_provider_stt_k6_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=6)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert clock.sleeps == [0.15625, 0.3125, 0.625, 1.25, 2.5, 2.5]


def test_g1_entry_consult_three_instance_batch_provider_stt_k6_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=6)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert clock.sleeps == [0.1875, 0.375, 0.75, 1.5, 3.0, 3.0]


def test_g1_entry_consult_three_instance_batch_provider_stt_k6_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=6)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert clock.sleeps == [0.25, 0.5, 1.0, 2.0, 4.0, 4.0]


def test_g1_entry_consult_three_instance_batch_provider_stt_k7_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=7)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert clock.sleeps == [0.125, 0.25, 0.5, 1.0, 2.0, 2.0, 2.0]


def test_g1_entry_consult_three_instance_batch_provider_stt_k7_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=7)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert clock.sleeps == [0.15625, 0.3125, 0.625, 1.25, 2.5, 2.5, 2.5]


def test_g1_entry_consult_three_instance_batch_provider_stt_k7_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=7)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert clock.sleeps == [0.1875, 0.375, 0.75, 1.5, 3.0, 3.0, 3.0]


def test_g1_entry_consult_three_instance_batch_provider_stt_k7_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=7)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert clock.sleeps == [0.25, 0.5, 1.0, 2.0, 4.0, 4.0, 4.0]


def test_g1_entry_consult_three_instance_batch_provider_stt_k8_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=8)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert clock.sleeps == [0.125, 0.25, 0.5, 1.0, 2.0, 2.0, 2.0, 2.0]


def test_g1_entry_consult_three_instance_batch_provider_stt_k8_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=8)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert clock.sleeps == [0.15625, 0.3125, 0.625, 1.25, 2.5, 2.5, 2.5, 2.5]


def test_g1_entry_consult_three_instance_batch_provider_stt_k8_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=8)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert clock.sleeps == [0.1875, 0.375, 0.75, 1.5, 3.0, 3.0, 3.0, 3.0]


def test_g1_entry_consult_three_instance_batch_provider_stt_k8_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=8)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert clock.sleeps == [0.25, 0.5, 1.0, 2.0, 4.0, 4.0, 4.0, 4.0]


def test_g1_entry_consult_three_instance_batch_provider_stt_k9_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=9)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert clock.sleeps == [0.125, 0.25, 0.5, 1.0, 2.0, 2.0, 2.0, 2.0, 2.0]


def test_g1_entry_consult_three_instance_batch_provider_stt_k9_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=9)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert clock.sleeps == [0.15625, 0.3125, 0.625, 1.25, 2.5, 2.5, 2.5, 2.5, 2.5]


def test_g1_entry_consult_three_instance_batch_provider_stt_k9_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=9)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert clock.sleeps == [0.1875, 0.375, 0.75, 1.5, 3.0, 3.0, 3.0, 3.0, 3.0]


def test_g1_entry_consult_three_instance_batch_provider_stt_k9_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=9)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert clock.sleeps == [0.25, 0.5, 1.0, 2.0, 4.0, 4.0, 4.0, 4.0, 4.0]


def test_g1_entry_consult_three_instance_batch_provider_stt_k10_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=10)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert clock.sleeps == [0.125, 0.25, 0.5, 1.0, 2.0, 2.0, 2.0, 2.0, 2.0, 2.0]


def test_g1_entry_consult_three_instance_batch_provider_stt_k10_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=10)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert clock.sleeps == [0.15625, 0.3125, 0.625, 1.25, 2.5, 2.5, 2.5, 2.5, 2.5, 2.5]


def test_g1_entry_consult_three_instance_batch_provider_stt_k10_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=10)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert clock.sleeps == [0.1875, 0.375, 0.75, 1.5, 3.0, 3.0, 3.0, 3.0, 3.0, 3.0]


def test_g1_entry_consult_three_instance_batch_provider_stt_k10_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=10)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert clock.sleeps == [0.25, 0.5, 1.0, 2.0, 4.0, 4.0, 4.0, 4.0, 4.0, 4.0]


def test_g1_entry_consult_three_instance_batch_intake_status_k1_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_intake_status', times=1)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_intake_status')
    assert clock.sleeps == [0.125]


def test_g1_entry_consult_three_instance_batch_intake_status_k1_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_intake_status', times=1)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_intake_status')
    assert clock.sleeps == [0.15625]


def test_g1_entry_consult_three_instance_batch_intake_status_k1_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_intake_status', times=1)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_intake_status')
    assert clock.sleeps == [0.1875]


def test_g1_entry_consult_three_instance_batch_intake_status_k1_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_intake_status', times=1)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_intake_status')
    assert clock.sleeps == [0.25]


def test_g1_entry_consult_three_instance_batch_intake_status_k2_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_intake_status', times=2)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_intake_status')
    assert clock.sleeps == [0.125, 0.25]


def test_g1_entry_consult_three_instance_batch_intake_status_k2_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_intake_status', times=2)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_intake_status')
    assert clock.sleeps == [0.15625, 0.3125]


def test_g1_entry_consult_three_instance_batch_intake_status_k2_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_intake_status', times=2)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_intake_status')
    assert clock.sleeps == [0.1875, 0.375]


def test_g1_entry_consult_three_instance_batch_intake_status_k2_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_intake_status', times=2)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_intake_status')
    assert clock.sleeps == [0.25, 0.5]


def test_g1_entry_consult_three_instance_batch_intake_status_k3_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_intake_status', times=3)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_intake_status')
    assert clock.sleeps == [0.125, 0.25, 0.5]


def test_g1_entry_consult_three_instance_batch_intake_status_k3_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_intake_status', times=3)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_intake_status')
    assert clock.sleeps == [0.15625, 0.3125, 0.625]


def test_g1_entry_consult_three_instance_batch_intake_status_k3_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_intake_status', times=3)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_intake_status')
    assert clock.sleeps == [0.1875, 0.375, 0.75]


def test_g1_entry_consult_three_instance_batch_intake_status_k3_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_intake_status', times=3)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_intake_status')
    assert clock.sleeps == [0.25, 0.5, 1.0]


def test_g1_entry_consult_three_instance_batch_intake_status_k4_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_intake_status', times=4)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_intake_status')
    assert clock.sleeps == [0.125, 0.25, 0.5, 1.0]


def test_g1_entry_consult_three_instance_batch_intake_status_k4_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_intake_status', times=4)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_intake_status')
    assert clock.sleeps == [0.15625, 0.3125, 0.625, 1.25]


def test_g1_entry_consult_three_instance_batch_intake_status_k4_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_intake_status', times=4)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_intake_status')
    assert clock.sleeps == [0.1875, 0.375, 0.75, 1.5]


def test_g1_entry_consult_three_instance_batch_intake_status_k4_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_intake_status', times=4)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_intake_status')
    assert clock.sleeps == [0.25, 0.5, 1.0, 2.0]


def test_g1_entry_consult_three_instance_batch_intake_status_k5_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_intake_status', times=5)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_intake_status')
    assert clock.sleeps == [0.125, 0.25, 0.5, 1.0, 2.0]


def test_g1_entry_consult_three_instance_batch_intake_status_k5_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_intake_status', times=5)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_intake_status')
    assert clock.sleeps == [0.15625, 0.3125, 0.625, 1.25, 2.5]


def test_g1_entry_consult_three_instance_batch_intake_status_k5_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_intake_status', times=5)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_intake_status')
    assert clock.sleeps == [0.1875, 0.375, 0.75, 1.5, 3.0]


def test_g1_entry_consult_three_instance_batch_intake_status_k5_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_intake_status', times=5)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_intake_status')
    assert clock.sleeps == [0.25, 0.5, 1.0, 2.0, 4.0]


def test_g1_entry_consult_three_instance_batch_intake_status_k6_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_intake_status', times=6)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_intake_status')
    assert clock.sleeps == [0.125, 0.25, 0.5, 1.0, 2.0, 2.0]


def test_g1_entry_consult_three_instance_batch_intake_status_k6_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_intake_status', times=6)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_intake_status')
    assert clock.sleeps == [0.15625, 0.3125, 0.625, 1.25, 2.5, 2.5]


def test_g1_entry_consult_three_instance_batch_intake_status_k6_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_intake_status', times=6)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_intake_status')
    assert clock.sleeps == [0.1875, 0.375, 0.75, 1.5, 3.0, 3.0]


def test_g1_entry_consult_three_instance_batch_intake_status_k6_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_intake_status', times=6)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_intake_status')
    assert clock.sleeps == [0.25, 0.5, 1.0, 2.0, 4.0, 4.0]


def test_g1_entry_consult_three_instance_batch_intake_status_k7_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_intake_status', times=7)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_intake_status')
    assert clock.sleeps == [0.125, 0.25, 0.5, 1.0, 2.0, 2.0, 2.0]


def test_g1_entry_consult_three_instance_batch_intake_status_k7_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_intake_status', times=7)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_intake_status')
    assert clock.sleeps == [0.15625, 0.3125, 0.625, 1.25, 2.5, 2.5, 2.5]


def test_g1_entry_consult_three_instance_batch_intake_status_k7_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_intake_status', times=7)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_intake_status')
    assert clock.sleeps == [0.1875, 0.375, 0.75, 1.5, 3.0, 3.0, 3.0]


def test_g1_entry_consult_three_instance_batch_intake_status_k7_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_intake_status', times=7)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_intake_status')
    assert clock.sleeps == [0.25, 0.5, 1.0, 2.0, 4.0, 4.0, 4.0]


def test_g1_entry_consult_three_instance_batch_intake_status_k8_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_intake_status', times=8)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_intake_status')
    assert clock.sleeps == [0.125, 0.25, 0.5, 1.0, 2.0, 2.0, 2.0, 2.0]


def test_g1_entry_consult_three_instance_batch_intake_status_k8_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_intake_status', times=8)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_intake_status')
    assert clock.sleeps == [0.15625, 0.3125, 0.625, 1.25, 2.5, 2.5, 2.5, 2.5]


def test_g1_entry_consult_three_instance_batch_intake_status_k8_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_intake_status', times=8)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_intake_status')
    assert clock.sleeps == [0.1875, 0.375, 0.75, 1.5, 3.0, 3.0, 3.0, 3.0]


def test_g1_entry_consult_three_instance_batch_intake_status_k8_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_intake_status', times=8)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_intake_status')
    assert clock.sleeps == [0.25, 0.5, 1.0, 2.0, 4.0, 4.0, 4.0, 4.0]


def test_g1_entry_consult_three_instance_batch_intake_status_k9_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_intake_status', times=9)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_intake_status')
    assert clock.sleeps == [0.125, 0.25, 0.5, 1.0, 2.0, 2.0, 2.0, 2.0, 2.0]


def test_g1_entry_consult_three_instance_batch_intake_status_k9_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_intake_status', times=9)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_intake_status')
    assert clock.sleeps == [0.15625, 0.3125, 0.625, 1.25, 2.5, 2.5, 2.5, 2.5, 2.5]


def test_g1_entry_consult_three_instance_batch_intake_status_k9_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_intake_status', times=9)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_intake_status')
    assert clock.sleeps == [0.1875, 0.375, 0.75, 1.5, 3.0, 3.0, 3.0, 3.0, 3.0]


def test_g1_entry_consult_three_instance_batch_intake_status_k9_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_intake_status', times=9)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_intake_status')
    assert clock.sleeps == [0.25, 0.5, 1.0, 2.0, 4.0, 4.0, 4.0, 4.0, 4.0]


def test_g1_entry_consult_three_instance_batch_intake_status_k10_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_intake_status', times=10)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_intake_status')
    assert clock.sleeps == [0.125, 0.25, 0.5, 1.0, 2.0, 2.0, 2.0, 2.0, 2.0, 2.0]


def test_g1_entry_consult_three_instance_batch_intake_status_k10_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_intake_status', times=10)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_intake_status')
    assert clock.sleeps == [0.15625, 0.3125, 0.625, 1.25, 2.5, 2.5, 2.5, 2.5, 2.5, 2.5]


def test_g1_entry_consult_three_instance_batch_intake_status_k10_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_intake_status', times=10)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_intake_status')
    assert clock.sleeps == [0.1875, 0.375, 0.75, 1.5, 3.0, 3.0, 3.0, 3.0, 3.0, 3.0]


def test_g1_entry_consult_three_instance_batch_intake_status_k10_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_intake_status', times=10)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_intake_status')
    assert clock.sleeps == [0.25, 0.5, 1.0, 2.0, 4.0, 4.0, 4.0, 4.0, 4.0, 4.0]


def test_g1_entry_consult_three_instance_batch_complete_k1_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_complete', times=1)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_complete')
    assert clock.sleeps == [0.125]


def test_g1_entry_consult_three_instance_batch_complete_k1_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_complete', times=1)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_complete')
    assert clock.sleeps == [0.15625]


def test_g1_entry_consult_three_instance_batch_complete_k1_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_complete', times=1)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_complete')
    assert clock.sleeps == [0.1875]


def test_g1_entry_consult_three_instance_batch_complete_k1_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_complete', times=1)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_complete')
    assert clock.sleeps == [0.25]


def test_g1_entry_consult_three_instance_batch_complete_k2_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_complete', times=2)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_complete')
    assert clock.sleeps == [0.125, 0.25]


def test_g1_entry_consult_three_instance_batch_complete_k2_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_complete', times=2)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_complete')
    assert clock.sleeps == [0.15625, 0.3125]


def test_g1_entry_consult_three_instance_batch_complete_k2_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_complete', times=2)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_complete')
    assert clock.sleeps == [0.1875, 0.375]


def test_g1_entry_consult_three_instance_batch_complete_k2_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_complete', times=2)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_complete')
    assert clock.sleeps == [0.25, 0.5]


def test_g1_entry_consult_three_instance_batch_complete_k3_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_complete', times=3)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_complete')
    assert clock.sleeps == [0.125, 0.25, 0.5]


def test_g1_entry_consult_three_instance_batch_complete_k3_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_complete', times=3)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_complete')
    assert clock.sleeps == [0.15625, 0.3125, 0.625]


def test_g1_entry_consult_three_instance_batch_complete_k3_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_complete', times=3)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_complete')
    assert clock.sleeps == [0.1875, 0.375, 0.75]


def test_g1_entry_consult_three_instance_batch_complete_k3_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_complete', times=3)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_complete')
    assert clock.sleeps == [0.25, 0.5, 1.0]


def test_g1_entry_consult_three_instance_batch_complete_k4_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_complete', times=4)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_complete')
    assert clock.sleeps == [0.125, 0.25, 0.5, 1.0]


def test_g1_entry_consult_three_instance_batch_complete_k4_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_complete', times=4)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_complete')
    assert clock.sleeps == [0.15625, 0.3125, 0.625, 1.25]


def test_g1_entry_consult_three_instance_batch_complete_k4_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_complete', times=4)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_complete')
    assert clock.sleeps == [0.1875, 0.375, 0.75, 1.5]


def test_g1_entry_consult_three_instance_batch_complete_k4_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_complete', times=4)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_complete')
    assert clock.sleeps == [0.25, 0.5, 1.0, 2.0]


def test_g1_entry_consult_three_instance_batch_complete_k5_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_complete', times=5)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_complete')
    assert clock.sleeps == [0.125, 0.25, 0.5, 1.0, 2.0]


def test_g1_entry_consult_three_instance_batch_complete_k5_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_complete', times=5)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_complete')
    assert clock.sleeps == [0.15625, 0.3125, 0.625, 1.25, 2.5]


def test_g1_entry_consult_three_instance_batch_complete_k5_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_complete', times=5)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_complete')
    assert clock.sleeps == [0.1875, 0.375, 0.75, 1.5, 3.0]


def test_g1_entry_consult_three_instance_batch_complete_k5_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_complete', times=5)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_complete')
    assert clock.sleeps == [0.25, 0.5, 1.0, 2.0, 4.0]


def test_g1_entry_consult_three_instance_batch_complete_k6_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_complete', times=6)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_complete')
    assert clock.sleeps == [0.125, 0.25, 0.5, 1.0, 2.0, 2.0]


def test_g1_entry_consult_three_instance_batch_complete_k6_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_complete', times=6)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_complete')
    assert clock.sleeps == [0.15625, 0.3125, 0.625, 1.25, 2.5, 2.5]


def test_g1_entry_consult_three_instance_batch_complete_k6_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_complete', times=6)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_complete')
    assert clock.sleeps == [0.1875, 0.375, 0.75, 1.5, 3.0, 3.0]


def test_g1_entry_consult_three_instance_batch_complete_k6_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_complete', times=6)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_complete')
    assert clock.sleeps == [0.25, 0.5, 1.0, 2.0, 4.0, 4.0]


def test_g1_entry_consult_three_instance_batch_complete_k7_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_complete', times=7)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_complete')
    assert clock.sleeps == [0.125, 0.25, 0.5, 1.0, 2.0, 2.0, 2.0]


def test_g1_entry_consult_three_instance_batch_complete_k7_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_complete', times=7)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_complete')
    assert clock.sleeps == [0.15625, 0.3125, 0.625, 1.25, 2.5, 2.5, 2.5]


def test_g1_entry_consult_three_instance_batch_complete_k7_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_complete', times=7)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_complete')
    assert clock.sleeps == [0.1875, 0.375, 0.75, 1.5, 3.0, 3.0, 3.0]


def test_g1_entry_consult_three_instance_batch_complete_k7_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_complete', times=7)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_complete')
    assert clock.sleeps == [0.25, 0.5, 1.0, 2.0, 4.0, 4.0, 4.0]


def test_g1_entry_consult_three_instance_batch_complete_k8_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_complete', times=8)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_complete')
    assert clock.sleeps == [0.125, 0.25, 0.5, 1.0, 2.0, 2.0, 2.0, 2.0]


def test_g1_entry_consult_three_instance_batch_complete_k8_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_complete', times=8)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_complete')
    assert clock.sleeps == [0.15625, 0.3125, 0.625, 1.25, 2.5, 2.5, 2.5, 2.5]


def test_g1_entry_consult_three_instance_batch_complete_k8_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_complete', times=8)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_complete')
    assert clock.sleeps == [0.1875, 0.375, 0.75, 1.5, 3.0, 3.0, 3.0, 3.0]


def test_g1_entry_consult_three_instance_batch_complete_k8_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_complete', times=8)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_complete')
    assert clock.sleeps == [0.25, 0.5, 1.0, 2.0, 4.0, 4.0, 4.0, 4.0]


def test_g1_entry_consult_three_instance_batch_complete_k9_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_complete', times=9)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_complete')
    assert clock.sleeps == [0.125, 0.25, 0.5, 1.0, 2.0, 2.0, 2.0, 2.0, 2.0]


def test_g1_entry_consult_three_instance_batch_complete_k9_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_complete', times=9)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_complete')
    assert clock.sleeps == [0.15625, 0.3125, 0.625, 1.25, 2.5, 2.5, 2.5, 2.5, 2.5]


def test_g1_entry_consult_three_instance_batch_complete_k9_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_complete', times=9)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_complete')
    assert clock.sleeps == [0.1875, 0.375, 0.75, 1.5, 3.0, 3.0, 3.0, 3.0, 3.0]


def test_g1_entry_consult_three_instance_batch_complete_k9_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_complete', times=9)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_complete')
    assert clock.sleeps == [0.25, 0.5, 1.0, 2.0, 4.0, 4.0, 4.0, 4.0, 4.0]


def test_g1_entry_consult_three_instance_batch_complete_k10_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_complete', times=10)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_complete')
    assert clock.sleeps == [0.125, 0.25, 0.5, 1.0, 2.0, 2.0, 2.0, 2.0, 2.0, 2.0]


def test_g1_entry_consult_three_instance_batch_complete_k10_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_complete', times=10)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_complete')
    assert clock.sleeps == [0.15625, 0.3125, 0.625, 1.25, 2.5, 2.5, 2.5, 2.5, 2.5, 2.5]


def test_g1_entry_consult_three_instance_batch_complete_k10_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_complete', times=10)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_complete')
    assert clock.sleeps == [0.1875, 0.375, 0.75, 1.5, 3.0, 3.0, 3.0, 3.0, 3.0, 3.0]


def test_g1_entry_consult_three_instance_batch_complete_k10_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_complete', times=10)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_complete')
    assert clock.sleeps == [0.25, 0.5, 1.0, 2.0, 4.0, 4.0, 4.0, 4.0, 4.0, 4.0]


def test_g1_entry_consult_three_instance_batch_recovery_settle_k1_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_recovery_settle', times=1)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_recovery_settle')
    assert clock.sleeps == [0.125]


def test_g1_entry_consult_three_instance_batch_recovery_settle_k1_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_recovery_settle', times=1)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_recovery_settle')
    assert clock.sleeps == [0.15625]


def test_g1_entry_consult_three_instance_batch_recovery_settle_k1_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_recovery_settle', times=1)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_recovery_settle')
    assert clock.sleeps == [0.1875]


def test_g1_entry_consult_three_instance_batch_recovery_settle_k1_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_recovery_settle', times=1)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_recovery_settle')
    assert clock.sleeps == [0.25]


def test_g1_entry_consult_three_instance_batch_recovery_settle_k2_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_recovery_settle', times=2)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_recovery_settle')
    assert clock.sleeps == [0.125, 0.25]


def test_g1_entry_consult_three_instance_batch_recovery_settle_k2_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_recovery_settle', times=2)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_recovery_settle')
    assert clock.sleeps == [0.15625, 0.3125]


def test_g1_entry_consult_three_instance_batch_recovery_settle_k2_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_recovery_settle', times=2)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_recovery_settle')
    assert clock.sleeps == [0.1875, 0.375]


def test_g1_entry_consult_three_instance_batch_recovery_settle_k2_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_recovery_settle', times=2)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_recovery_settle')
    assert clock.sleeps == [0.25, 0.5]


def test_g1_entry_consult_three_instance_batch_recovery_settle_k3_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_recovery_settle', times=3)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_recovery_settle')
    assert clock.sleeps == [0.125, 0.25, 0.5]


def test_g1_entry_consult_three_instance_batch_recovery_settle_k3_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_recovery_settle', times=3)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_recovery_settle')
    assert clock.sleeps == [0.15625, 0.3125, 0.625]


def test_g1_entry_consult_three_instance_batch_recovery_settle_k3_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_recovery_settle', times=3)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_recovery_settle')
    assert clock.sleeps == [0.1875, 0.375, 0.75]


def test_g1_entry_consult_three_instance_batch_recovery_settle_k3_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_recovery_settle', times=3)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_recovery_settle')
    assert clock.sleeps == [0.25, 0.5, 1.0]


def test_g1_entry_consult_three_instance_batch_recovery_settle_k4_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_recovery_settle', times=4)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_recovery_settle')
    assert clock.sleeps == [0.125, 0.25, 0.5, 1.0]


def test_g1_entry_consult_three_instance_batch_recovery_settle_k4_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_recovery_settle', times=4)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_recovery_settle')
    assert clock.sleeps == [0.15625, 0.3125, 0.625, 1.25]


def test_g1_entry_consult_three_instance_batch_recovery_settle_k4_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_recovery_settle', times=4)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_recovery_settle')
    assert clock.sleeps == [0.1875, 0.375, 0.75, 1.5]


def test_g1_entry_consult_three_instance_batch_recovery_settle_k4_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_recovery_settle', times=4)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_recovery_settle')
    assert clock.sleeps == [0.25, 0.5, 1.0, 2.0]


def test_g1_entry_consult_three_instance_batch_recovery_settle_k5_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_recovery_settle', times=5)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_recovery_settle')
    assert clock.sleeps == [0.125, 0.25, 0.5, 1.0, 2.0]


def test_g1_entry_consult_three_instance_batch_recovery_settle_k5_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_recovery_settle', times=5)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_recovery_settle')
    assert clock.sleeps == [0.15625, 0.3125, 0.625, 1.25, 2.5]


def test_g1_entry_consult_three_instance_batch_recovery_settle_k5_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_recovery_settle', times=5)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_recovery_settle')
    assert clock.sleeps == [0.1875, 0.375, 0.75, 1.5, 3.0]


def test_g1_entry_consult_three_instance_batch_recovery_settle_k5_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_recovery_settle', times=5)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_recovery_settle')
    assert clock.sleeps == [0.25, 0.5, 1.0, 2.0, 4.0]


def test_g1_entry_consult_three_instance_batch_recovery_settle_k6_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_recovery_settle', times=6)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_recovery_settle')
    assert clock.sleeps == [0.125, 0.25, 0.5, 1.0, 2.0, 2.0]


def test_g1_entry_consult_three_instance_batch_recovery_settle_k6_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_recovery_settle', times=6)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_recovery_settle')
    assert clock.sleeps == [0.15625, 0.3125, 0.625, 1.25, 2.5, 2.5]


def test_g1_entry_consult_three_instance_batch_recovery_settle_k6_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_recovery_settle', times=6)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_recovery_settle')
    assert clock.sleeps == [0.1875, 0.375, 0.75, 1.5, 3.0, 3.0]


def test_g1_entry_consult_three_instance_batch_recovery_settle_k6_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_recovery_settle', times=6)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_recovery_settle')
    assert clock.sleeps == [0.25, 0.5, 1.0, 2.0, 4.0, 4.0]


def test_g1_entry_consult_three_instance_batch_recovery_settle_k7_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_recovery_settle', times=7)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_recovery_settle')
    assert clock.sleeps == [0.125, 0.25, 0.5, 1.0, 2.0, 2.0, 2.0]


def test_g1_entry_consult_three_instance_batch_recovery_settle_k7_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_recovery_settle', times=7)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_recovery_settle')
    assert clock.sleeps == [0.15625, 0.3125, 0.625, 1.25, 2.5, 2.5, 2.5]


def test_g1_entry_consult_three_instance_batch_recovery_settle_k7_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_recovery_settle', times=7)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_recovery_settle')
    assert clock.sleeps == [0.1875, 0.375, 0.75, 1.5, 3.0, 3.0, 3.0]


def test_g1_entry_consult_three_instance_batch_recovery_settle_k7_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_recovery_settle', times=7)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_recovery_settle')
    assert clock.sleeps == [0.25, 0.5, 1.0, 2.0, 4.0, 4.0, 4.0]


def test_g1_entry_consult_three_instance_batch_recovery_settle_k8_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_recovery_settle', times=8)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_recovery_settle')
    assert clock.sleeps == [0.125, 0.25, 0.5, 1.0, 2.0, 2.0, 2.0, 2.0]


def test_g1_entry_consult_three_instance_batch_recovery_settle_k8_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_recovery_settle', times=8)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_recovery_settle')
    assert clock.sleeps == [0.15625, 0.3125, 0.625, 1.25, 2.5, 2.5, 2.5, 2.5]


def test_g1_entry_consult_three_instance_batch_recovery_settle_k8_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_recovery_settle', times=8)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_recovery_settle')
    assert clock.sleeps == [0.1875, 0.375, 0.75, 1.5, 3.0, 3.0, 3.0, 3.0]


def test_g1_entry_consult_three_instance_batch_recovery_settle_k8_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_recovery_settle', times=8)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_recovery_settle')
    assert clock.sleeps == [0.25, 0.5, 1.0, 2.0, 4.0, 4.0, 4.0, 4.0]


def test_g1_entry_consult_three_instance_batch_recovery_settle_k9_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_recovery_settle', times=9)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_recovery_settle')
    assert clock.sleeps == [0.125, 0.25, 0.5, 1.0, 2.0, 2.0, 2.0, 2.0, 2.0]


def test_g1_entry_consult_three_instance_batch_recovery_settle_k9_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_recovery_settle', times=9)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_recovery_settle')
    assert clock.sleeps == [0.15625, 0.3125, 0.625, 1.25, 2.5, 2.5, 2.5, 2.5, 2.5]


def test_g1_entry_consult_three_instance_batch_recovery_settle_k9_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_recovery_settle', times=9)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_recovery_settle')
    assert clock.sleeps == [0.1875, 0.375, 0.75, 1.5, 3.0, 3.0, 3.0, 3.0, 3.0]


def test_g1_entry_consult_three_instance_batch_recovery_settle_k9_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_recovery_settle', times=9)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_recovery_settle')
    assert clock.sleeps == [0.25, 0.5, 1.0, 2.0, 4.0, 4.0, 4.0, 4.0, 4.0]


def test_g1_entry_consult_three_instance_batch_recovery_settle_k10_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_recovery_settle', times=10)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_recovery_settle')
    assert clock.sleeps == [0.125, 0.25, 0.5, 1.0, 2.0, 2.0, 2.0, 2.0, 2.0, 2.0]


def test_g1_entry_consult_three_instance_batch_recovery_settle_k10_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_recovery_settle', times=10)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_recovery_settle')
    assert clock.sleeps == [0.15625, 0.3125, 0.625, 1.25, 2.5, 2.5, 2.5, 2.5, 2.5, 2.5]


def test_g1_entry_consult_three_instance_batch_recovery_settle_k10_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_recovery_settle', times=10)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_recovery_settle')
    assert clock.sleeps == [0.1875, 0.375, 0.75, 1.5, 3.0, 3.0, 3.0, 3.0, 3.0, 3.0]


def test_g1_entry_consult_three_instance_batch_recovery_settle_k10_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_recovery_settle', times=10)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_recovery_settle')
    assert clock.sleeps == [0.25, 0.5, 1.0, 2.0, 4.0, 4.0, 4.0, 4.0, 4.0, 4.0]


def test_g1_entry_consult_three_instance_batch_pull_shard_scheduler_17_k1_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_pull shard=scheduler_17', times=1)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_pull shard=scheduler_17')
    assert clock.sleeps == [0.125]


def test_g1_entry_consult_three_instance_batch_pull_shard_scheduler_17_k1_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_pull shard=scheduler_17', times=1)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_pull shard=scheduler_17')
    assert clock.sleeps == [0.15625]


def test_g1_entry_consult_three_instance_batch_pull_shard_scheduler_17_k1_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_pull shard=scheduler_17', times=1)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_pull shard=scheduler_17')
    assert clock.sleeps == [0.1875]


def test_g1_entry_consult_three_instance_batch_pull_shard_scheduler_17_k1_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_pull shard=scheduler_17', times=1)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_pull shard=scheduler_17')
    assert clock.sleeps == [0.25]


def test_g1_entry_consult_three_instance_batch_pull_shard_scheduler_17_k2_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_pull shard=scheduler_17', times=2)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_pull shard=scheduler_17')
    assert clock.sleeps == [0.125, 0.25]


def test_g1_entry_consult_three_instance_batch_pull_shard_scheduler_17_k2_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_pull shard=scheduler_17', times=2)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_pull shard=scheduler_17')
    assert clock.sleeps == [0.15625, 0.3125]


def test_g1_entry_consult_three_instance_batch_pull_shard_scheduler_17_k2_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_pull shard=scheduler_17', times=2)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_pull shard=scheduler_17')
    assert clock.sleeps == [0.1875, 0.375]


def test_g1_entry_consult_three_instance_batch_pull_shard_scheduler_17_k2_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_pull shard=scheduler_17', times=2)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_pull shard=scheduler_17')
    assert clock.sleeps == [0.25, 0.5]


def test_g1_entry_consult_three_instance_batch_pull_shard_scheduler_17_k3_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_pull shard=scheduler_17', times=3)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_pull shard=scheduler_17')
    assert clock.sleeps == [0.125, 0.25, 0.5]


def test_g1_entry_consult_three_instance_batch_pull_shard_scheduler_17_k3_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_pull shard=scheduler_17', times=3)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_pull shard=scheduler_17')
    assert clock.sleeps == [0.15625, 0.3125, 0.625]


def test_g1_entry_consult_three_instance_batch_pull_shard_scheduler_17_k3_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_pull shard=scheduler_17', times=3)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_pull shard=scheduler_17')
    assert clock.sleeps == [0.1875, 0.375, 0.75]


def test_g1_entry_consult_three_instance_batch_pull_shard_scheduler_17_k3_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_pull shard=scheduler_17', times=3)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_pull shard=scheduler_17')
    assert clock.sleeps == [0.25, 0.5, 1.0]


def test_g1_entry_consult_three_instance_batch_pull_shard_scheduler_17_k4_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_pull shard=scheduler_17', times=4)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_pull shard=scheduler_17')
    assert clock.sleeps == [0.125, 0.25, 0.5, 1.0]


def test_g1_entry_consult_three_instance_batch_pull_shard_scheduler_17_k4_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_pull shard=scheduler_17', times=4)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_pull shard=scheduler_17')
    assert clock.sleeps == [0.15625, 0.3125, 0.625, 1.25]


def test_g1_entry_consult_three_instance_batch_pull_shard_scheduler_17_k4_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_pull shard=scheduler_17', times=4)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_pull shard=scheduler_17')
    assert clock.sleeps == [0.1875, 0.375, 0.75, 1.5]


def test_g1_entry_consult_three_instance_batch_pull_shard_scheduler_17_k4_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_pull shard=scheduler_17', times=4)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_pull shard=scheduler_17')
    assert clock.sleeps == [0.25, 0.5, 1.0, 2.0]


def test_g1_entry_consult_three_instance_batch_pull_shard_scheduler_17_k5_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_pull shard=scheduler_17', times=5)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_pull shard=scheduler_17')
    assert clock.sleeps == [0.125, 0.25, 0.5, 1.0, 2.0]


def test_g1_entry_consult_three_instance_batch_pull_shard_scheduler_17_k5_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_pull shard=scheduler_17', times=5)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_pull shard=scheduler_17')
    assert clock.sleeps == [0.15625, 0.3125, 0.625, 1.25, 2.5]


def test_g1_entry_consult_three_instance_batch_pull_shard_scheduler_17_k5_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_pull shard=scheduler_17', times=5)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_pull shard=scheduler_17')
    assert clock.sleeps == [0.1875, 0.375, 0.75, 1.5, 3.0]


def test_g1_entry_consult_three_instance_batch_pull_shard_scheduler_17_k5_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_pull shard=scheduler_17', times=5)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_pull shard=scheduler_17')
    assert clock.sleeps == [0.25, 0.5, 1.0, 2.0, 4.0]


def test_g1_entry_consult_three_instance_batch_pull_shard_scheduler_17_k6_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_pull shard=scheduler_17', times=6)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_pull shard=scheduler_17')
    assert clock.sleeps == [0.125, 0.25, 0.5, 1.0, 2.0, 2.0]


def test_g1_entry_consult_three_instance_batch_pull_shard_scheduler_17_k6_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_pull shard=scheduler_17', times=6)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_pull shard=scheduler_17')
    assert clock.sleeps == [0.15625, 0.3125, 0.625, 1.25, 2.5, 2.5]


def test_g1_entry_consult_three_instance_batch_pull_shard_scheduler_17_k6_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_pull shard=scheduler_17', times=6)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_pull shard=scheduler_17')
    assert clock.sleeps == [0.1875, 0.375, 0.75, 1.5, 3.0, 3.0]


def test_g1_entry_consult_three_instance_batch_pull_shard_scheduler_17_k6_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_pull shard=scheduler_17', times=6)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_pull shard=scheduler_17')
    assert clock.sleeps == [0.25, 0.5, 1.0, 2.0, 4.0, 4.0]


def test_g1_entry_consult_three_instance_batch_pull_shard_scheduler_17_k7_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_pull shard=scheduler_17', times=7)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_pull shard=scheduler_17')
    assert clock.sleeps == [0.125, 0.25, 0.5, 1.0, 2.0, 2.0, 2.0]


def test_g1_entry_consult_three_instance_batch_pull_shard_scheduler_17_k7_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_pull shard=scheduler_17', times=7)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_pull shard=scheduler_17')
    assert clock.sleeps == [0.15625, 0.3125, 0.625, 1.25, 2.5, 2.5, 2.5]


def test_g1_entry_consult_three_instance_batch_pull_shard_scheduler_17_k7_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_pull shard=scheduler_17', times=7)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_pull shard=scheduler_17')
    assert clock.sleeps == [0.1875, 0.375, 0.75, 1.5, 3.0, 3.0, 3.0]


def test_g1_entry_consult_three_instance_batch_pull_shard_scheduler_17_k7_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_pull shard=scheduler_17', times=7)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_pull shard=scheduler_17')
    assert clock.sleeps == [0.25, 0.5, 1.0, 2.0, 4.0, 4.0, 4.0]


def test_g1_entry_consult_three_instance_batch_pull_shard_scheduler_17_k8_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_pull shard=scheduler_17', times=8)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_pull shard=scheduler_17')
    assert clock.sleeps == [0.125, 0.25, 0.5, 1.0, 2.0, 2.0, 2.0, 2.0]


def test_g1_entry_consult_three_instance_batch_pull_shard_scheduler_17_k8_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_pull shard=scheduler_17', times=8)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_pull shard=scheduler_17')
    assert clock.sleeps == [0.15625, 0.3125, 0.625, 1.25, 2.5, 2.5, 2.5, 2.5]


def test_g1_entry_consult_three_instance_batch_pull_shard_scheduler_17_k8_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_pull shard=scheduler_17', times=8)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_pull shard=scheduler_17')
    assert clock.sleeps == [0.1875, 0.375, 0.75, 1.5, 3.0, 3.0, 3.0, 3.0]


def test_g1_entry_consult_three_instance_batch_pull_shard_scheduler_17_k8_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_pull shard=scheduler_17', times=8)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_pull shard=scheduler_17')
    assert clock.sleeps == [0.25, 0.5, 1.0, 2.0, 4.0, 4.0, 4.0, 4.0]


def test_g1_entry_consult_three_instance_batch_pull_shard_scheduler_17_k9_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_pull shard=scheduler_17', times=9)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_pull shard=scheduler_17')
    assert clock.sleeps == [0.125, 0.25, 0.5, 1.0, 2.0, 2.0, 2.0, 2.0, 2.0]


def test_g1_entry_consult_three_instance_batch_pull_shard_scheduler_17_k9_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_pull shard=scheduler_17', times=9)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_pull shard=scheduler_17')
    assert clock.sleeps == [0.15625, 0.3125, 0.625, 1.25, 2.5, 2.5, 2.5, 2.5, 2.5]


def test_g1_entry_consult_three_instance_batch_pull_shard_scheduler_17_k9_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_pull shard=scheduler_17', times=9)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_pull shard=scheduler_17')
    assert clock.sleeps == [0.1875, 0.375, 0.75, 1.5, 3.0, 3.0, 3.0, 3.0, 3.0]


def test_g1_entry_consult_three_instance_batch_pull_shard_scheduler_17_k9_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_pull shard=scheduler_17', times=9)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_pull shard=scheduler_17')
    assert clock.sleeps == [0.25, 0.5, 1.0, 2.0, 4.0, 4.0, 4.0, 4.0, 4.0]


def test_g1_entry_consult_three_instance_batch_pull_shard_scheduler_17_k10_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_pull shard=scheduler_17', times=10)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_pull shard=scheduler_17')
    assert clock.sleeps == [0.125, 0.25, 0.5, 1.0, 2.0, 2.0, 2.0, 2.0, 2.0, 2.0]


def test_g1_entry_consult_three_instance_batch_pull_shard_scheduler_17_k10_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_pull shard=scheduler_17', times=10)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_pull shard=scheduler_17')
    assert clock.sleeps == [0.15625, 0.3125, 0.625, 1.25, 2.5, 2.5, 2.5, 2.5, 2.5, 2.5]


def test_g1_entry_consult_three_instance_batch_pull_shard_scheduler_17_k10_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_pull shard=scheduler_17', times=10)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_pull shard=scheduler_17')
    assert clock.sleeps == [0.1875, 0.375, 0.75, 1.5, 3.0, 3.0, 3.0, 3.0, 3.0, 3.0]


def test_g1_entry_consult_three_instance_batch_pull_shard_scheduler_17_k10_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_pull shard=scheduler_17', times=10)
    B = default_store(mp, ns=NS, client=healthy_client())
    C = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is C._storm_damper is damper
    C.run(lambda tx: 'ok', operation='batch_pull shard=scheduler_17')
    assert clock.sleeps == [0.25, 0.5, 1.0, 2.0, 4.0, 4.0, 4.0, 4.0, 4.0, 4.0]


def test_g1_entry_consult_per_call_drop_batch_merge_commit_k1_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=1)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps == [0.125]


def test_g1_entry_consult_per_call_drop_batch_merge_commit_k1_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=1)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps == [0.15625]


def test_g1_entry_consult_per_call_drop_batch_merge_commit_k1_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=1)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps == [0.1875]


def test_g1_entry_consult_per_call_drop_batch_merge_commit_k1_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=1)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps == [0.25]


def test_g1_entry_consult_per_call_drop_batch_merge_commit_k2_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=2)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps == [0.125, 0.25]


def test_g1_entry_consult_per_call_drop_batch_merge_commit_k2_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=2)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps == [0.15625, 0.3125]


def test_g1_entry_consult_per_call_drop_batch_merge_commit_k2_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=2)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps == [0.1875, 0.375]


def test_g1_entry_consult_per_call_drop_batch_merge_commit_k2_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=2)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps == [0.25, 0.5]


def test_g1_entry_consult_per_call_drop_batch_merge_commit_k3_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=3)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps == [0.125, 0.25, 0.5]


def test_g1_entry_consult_per_call_drop_batch_merge_commit_k3_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=3)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps == [0.15625, 0.3125, 0.625]


def test_g1_entry_consult_per_call_drop_batch_merge_commit_k3_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=3)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps == [0.1875, 0.375, 0.75]


def test_g1_entry_consult_per_call_drop_batch_merge_commit_k3_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=3)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps == [0.25, 0.5, 1.0]


def test_g1_entry_consult_per_call_drop_batch_merge_commit_k4_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=4)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps == [0.125, 0.25, 0.5, 1.0]


def test_g1_entry_consult_per_call_drop_batch_merge_commit_k4_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=4)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps == [0.15625, 0.3125, 0.625, 1.25]


def test_g1_entry_consult_per_call_drop_batch_merge_commit_k4_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=4)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps == [0.1875, 0.375, 0.75, 1.5]


def test_g1_entry_consult_per_call_drop_batch_merge_commit_k4_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=4)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps == [0.25, 0.5, 1.0, 2.0]


def test_g1_entry_consult_per_call_drop_batch_merge_commit_k5_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=5)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps == [0.125, 0.25, 0.5, 1.0, 2.0]


def test_g1_entry_consult_per_call_drop_batch_merge_commit_k5_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=5)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps == [0.15625, 0.3125, 0.625, 1.25, 2.5]


def test_g1_entry_consult_per_call_drop_batch_merge_commit_k5_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=5)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps == [0.1875, 0.375, 0.75, 1.5, 3.0]


def test_g1_entry_consult_per_call_drop_batch_merge_commit_k5_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=5)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps == [0.25, 0.5, 1.0, 2.0, 4.0]


def test_g1_entry_consult_per_call_drop_batch_merge_commit_k6_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=6)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps == [0.125, 0.25, 0.5, 1.0, 2.0, 2.0]


def test_g1_entry_consult_per_call_drop_batch_merge_commit_k6_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=6)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps == [0.15625, 0.3125, 0.625, 1.25, 2.5, 2.5]


def test_g1_entry_consult_per_call_drop_batch_merge_commit_k6_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=6)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps == [0.1875, 0.375, 0.75, 1.5, 3.0, 3.0]


def test_g1_entry_consult_per_call_drop_batch_merge_commit_k6_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=6)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps == [0.25, 0.5, 1.0, 2.0, 4.0, 4.0]


def test_g1_entry_consult_per_call_drop_batch_merge_commit_k7_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=7)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps == [0.125, 0.25, 0.5, 1.0, 2.0, 2.0, 2.0]


def test_g1_entry_consult_per_call_drop_batch_merge_commit_k7_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=7)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps == [0.15625, 0.3125, 0.625, 1.25, 2.5, 2.5, 2.5]


def test_g1_entry_consult_per_call_drop_batch_merge_commit_k7_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=7)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps == [0.1875, 0.375, 0.75, 1.5, 3.0, 3.0, 3.0]


def test_g1_entry_consult_per_call_drop_batch_merge_commit_k7_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=7)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps == [0.25, 0.5, 1.0, 2.0, 4.0, 4.0, 4.0]


def test_g1_entry_consult_per_call_drop_batch_merge_commit_k8_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=8)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps == [0.125, 0.25, 0.5, 1.0, 2.0, 2.0, 2.0, 2.0]


def test_g1_entry_consult_per_call_drop_batch_merge_commit_k8_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=8)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps == [0.15625, 0.3125, 0.625, 1.25, 2.5, 2.5, 2.5, 2.5]


def test_g1_entry_consult_per_call_drop_batch_merge_commit_k8_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=8)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps == [0.1875, 0.375, 0.75, 1.5, 3.0, 3.0, 3.0, 3.0]


def test_g1_entry_consult_per_call_drop_batch_merge_commit_k8_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=8)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps == [0.25, 0.5, 1.0, 2.0, 4.0, 4.0, 4.0, 4.0]


def test_g1_entry_consult_per_call_drop_batch_merge_commit_k9_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=9)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps == [0.125, 0.25, 0.5, 1.0, 2.0, 2.0, 2.0, 2.0, 2.0]


def test_g1_entry_consult_per_call_drop_batch_merge_commit_k9_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=9)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps == [0.15625, 0.3125, 0.625, 1.25, 2.5, 2.5, 2.5, 2.5, 2.5]


def test_g1_entry_consult_per_call_drop_batch_merge_commit_k9_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=9)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps == [0.1875, 0.375, 0.75, 1.5, 3.0, 3.0, 3.0, 3.0, 3.0]


def test_g1_entry_consult_per_call_drop_batch_merge_commit_k9_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=9)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps == [0.25, 0.5, 1.0, 2.0, 4.0, 4.0, 4.0, 4.0, 4.0]


def test_g1_entry_consult_per_call_drop_batch_merge_commit_k10_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=10)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps == [0.125, 0.25, 0.5, 1.0, 2.0, 2.0, 2.0, 2.0, 2.0, 2.0]


def test_g1_entry_consult_per_call_drop_batch_merge_commit_k10_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=10)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps == [0.15625, 0.3125, 0.625, 1.25, 2.5, 2.5, 2.5, 2.5, 2.5, 2.5]


def test_g1_entry_consult_per_call_drop_batch_merge_commit_k10_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=10)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps == [0.1875, 0.375, 0.75, 1.5, 3.0, 3.0, 3.0, 3.0, 3.0, 3.0]


def test_g1_entry_consult_per_call_drop_batch_merge_commit_k10_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=10)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps == [0.25, 0.5, 1.0, 2.0, 4.0, 4.0, 4.0, 4.0, 4.0, 4.0]


def test_g1_entry_consult_per_call_drop_batch_provider_stt_k1_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=1)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert clock.sleeps == [0.125]


def test_g1_entry_consult_per_call_drop_batch_provider_stt_k1_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=1)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert clock.sleeps == [0.15625]


def test_g1_entry_consult_per_call_drop_batch_provider_stt_k1_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=1)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert clock.sleeps == [0.1875]


def test_g1_entry_consult_per_call_drop_batch_provider_stt_k1_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=1)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert clock.sleeps == [0.25]


def test_g1_entry_consult_per_call_drop_batch_provider_stt_k2_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=2)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert clock.sleeps == [0.125, 0.25]


def test_g1_entry_consult_per_call_drop_batch_provider_stt_k2_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=2)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert clock.sleeps == [0.15625, 0.3125]


def test_g1_entry_consult_per_call_drop_batch_provider_stt_k2_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=2)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert clock.sleeps == [0.1875, 0.375]


def test_g1_entry_consult_per_call_drop_batch_provider_stt_k2_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=2)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert clock.sleeps == [0.25, 0.5]


def test_g1_entry_consult_per_call_drop_batch_provider_stt_k3_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=3)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert clock.sleeps == [0.125, 0.25, 0.5]


def test_g1_entry_consult_per_call_drop_batch_provider_stt_k3_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=3)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert clock.sleeps == [0.15625, 0.3125, 0.625]


def test_g1_entry_consult_per_call_drop_batch_provider_stt_k3_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=3)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert clock.sleeps == [0.1875, 0.375, 0.75]


def test_g1_entry_consult_per_call_drop_batch_provider_stt_k3_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=3)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert clock.sleeps == [0.25, 0.5, 1.0]


def test_g1_entry_consult_per_call_drop_batch_provider_stt_k4_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=4)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert clock.sleeps == [0.125, 0.25, 0.5, 1.0]


def test_g1_entry_consult_per_call_drop_batch_provider_stt_k4_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=4)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert clock.sleeps == [0.15625, 0.3125, 0.625, 1.25]


def test_g1_entry_consult_per_call_drop_batch_provider_stt_k4_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=4)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert clock.sleeps == [0.1875, 0.375, 0.75, 1.5]


def test_g1_entry_consult_per_call_drop_batch_provider_stt_k4_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=4)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert clock.sleeps == [0.25, 0.5, 1.0, 2.0]


def test_g1_entry_consult_per_call_drop_batch_provider_stt_k5_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=5)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert clock.sleeps == [0.125, 0.25, 0.5, 1.0, 2.0]


def test_g1_entry_consult_per_call_drop_batch_provider_stt_k5_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=5)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert clock.sleeps == [0.15625, 0.3125, 0.625, 1.25, 2.5]


def test_g1_entry_consult_per_call_drop_batch_provider_stt_k5_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=5)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert clock.sleeps == [0.1875, 0.375, 0.75, 1.5, 3.0]


def test_g1_entry_consult_per_call_drop_batch_provider_stt_k5_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=5)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert clock.sleeps == [0.25, 0.5, 1.0, 2.0, 4.0]


def test_g1_entry_consult_per_call_drop_batch_provider_stt_k6_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=6)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert clock.sleeps == [0.125, 0.25, 0.5, 1.0, 2.0, 2.0]


def test_g1_entry_consult_per_call_drop_batch_provider_stt_k6_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=6)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert clock.sleeps == [0.15625, 0.3125, 0.625, 1.25, 2.5, 2.5]


def test_g1_entry_consult_per_call_drop_batch_provider_stt_k6_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=6)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert clock.sleeps == [0.1875, 0.375, 0.75, 1.5, 3.0, 3.0]


def test_g1_entry_consult_per_call_drop_batch_provider_stt_k6_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=6)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert clock.sleeps == [0.25, 0.5, 1.0, 2.0, 4.0, 4.0]


def test_g1_entry_consult_per_call_drop_batch_provider_stt_k7_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=7)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert clock.sleeps == [0.125, 0.25, 0.5, 1.0, 2.0, 2.0, 2.0]


def test_g1_entry_consult_per_call_drop_batch_provider_stt_k7_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=7)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert clock.sleeps == [0.15625, 0.3125, 0.625, 1.25, 2.5, 2.5, 2.5]


def test_g1_entry_consult_per_call_drop_batch_provider_stt_k7_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=7)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert clock.sleeps == [0.1875, 0.375, 0.75, 1.5, 3.0, 3.0, 3.0]


def test_g1_entry_consult_per_call_drop_batch_provider_stt_k7_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=7)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert clock.sleeps == [0.25, 0.5, 1.0, 2.0, 4.0, 4.0, 4.0]


def test_g1_entry_consult_per_call_drop_batch_provider_stt_k8_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=8)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert clock.sleeps == [0.125, 0.25, 0.5, 1.0, 2.0, 2.0, 2.0, 2.0]


def test_g1_entry_consult_per_call_drop_batch_provider_stt_k8_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=8)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert clock.sleeps == [0.15625, 0.3125, 0.625, 1.25, 2.5, 2.5, 2.5, 2.5]


def test_g1_entry_consult_per_call_drop_batch_provider_stt_k8_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=8)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert clock.sleeps == [0.1875, 0.375, 0.75, 1.5, 3.0, 3.0, 3.0, 3.0]


def test_g1_entry_consult_per_call_drop_batch_provider_stt_k8_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=8)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert clock.sleeps == [0.25, 0.5, 1.0, 2.0, 4.0, 4.0, 4.0, 4.0]


def test_g1_entry_consult_per_call_drop_batch_provider_stt_k9_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=9)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert clock.sleeps == [0.125, 0.25, 0.5, 1.0, 2.0, 2.0, 2.0, 2.0, 2.0]


def test_g1_entry_consult_per_call_drop_batch_provider_stt_k9_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=9)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert clock.sleeps == [0.15625, 0.3125, 0.625, 1.25, 2.5, 2.5, 2.5, 2.5, 2.5]


def test_g1_entry_consult_per_call_drop_batch_provider_stt_k9_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=9)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert clock.sleeps == [0.1875, 0.375, 0.75, 1.5, 3.0, 3.0, 3.0, 3.0, 3.0]


def test_g1_entry_consult_per_call_drop_batch_provider_stt_k9_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=9)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert clock.sleeps == [0.25, 0.5, 1.0, 2.0, 4.0, 4.0, 4.0, 4.0, 4.0]


def test_g1_entry_consult_per_call_drop_batch_provider_stt_k10_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=10)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert clock.sleeps == [0.125, 0.25, 0.5, 1.0, 2.0, 2.0, 2.0, 2.0, 2.0, 2.0]


def test_g1_entry_consult_per_call_drop_batch_provider_stt_k10_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=10)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert clock.sleeps == [0.15625, 0.3125, 0.625, 1.25, 2.5, 2.5, 2.5, 2.5, 2.5, 2.5]


def test_g1_entry_consult_per_call_drop_batch_provider_stt_k10_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=10)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert clock.sleeps == [0.1875, 0.375, 0.75, 1.5, 3.0, 3.0, 3.0, 3.0, 3.0, 3.0]


def test_g1_entry_consult_per_call_drop_batch_provider_stt_k10_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=10)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert clock.sleeps == [0.25, 0.5, 1.0, 2.0, 4.0, 4.0, 4.0, 4.0, 4.0, 4.0]


def test_g1_entry_consult_per_call_drop_batch_intake_status_k1_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_intake_status', times=1)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_intake_status')
    assert clock.sleeps == [0.125]


def test_g1_entry_consult_per_call_drop_batch_intake_status_k1_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_intake_status', times=1)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_intake_status')
    assert clock.sleeps == [0.15625]


def test_g1_entry_consult_per_call_drop_batch_intake_status_k1_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_intake_status', times=1)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_intake_status')
    assert clock.sleeps == [0.1875]


def test_g1_entry_consult_per_call_drop_batch_intake_status_k1_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_intake_status', times=1)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_intake_status')
    assert clock.sleeps == [0.25]


def test_g1_entry_consult_per_call_drop_batch_intake_status_k2_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_intake_status', times=2)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_intake_status')
    assert clock.sleeps == [0.125, 0.25]


def test_g1_entry_consult_per_call_drop_batch_intake_status_k2_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_intake_status', times=2)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_intake_status')
    assert clock.sleeps == [0.15625, 0.3125]


def test_g1_entry_consult_per_call_drop_batch_intake_status_k2_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_intake_status', times=2)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_intake_status')
    assert clock.sleeps == [0.1875, 0.375]


def test_g1_entry_consult_per_call_drop_batch_intake_status_k2_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_intake_status', times=2)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_intake_status')
    assert clock.sleeps == [0.25, 0.5]


def test_g1_entry_consult_per_call_drop_batch_intake_status_k3_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_intake_status', times=3)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_intake_status')
    assert clock.sleeps == [0.125, 0.25, 0.5]


def test_g1_entry_consult_per_call_drop_batch_intake_status_k3_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_intake_status', times=3)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_intake_status')
    assert clock.sleeps == [0.15625, 0.3125, 0.625]


def test_g1_entry_consult_per_call_drop_batch_intake_status_k3_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_intake_status', times=3)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_intake_status')
    assert clock.sleeps == [0.1875, 0.375, 0.75]


def test_g1_entry_consult_per_call_drop_batch_intake_status_k3_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_intake_status', times=3)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_intake_status')
    assert clock.sleeps == [0.25, 0.5, 1.0]


def test_g1_entry_consult_per_call_drop_batch_intake_status_k4_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_intake_status', times=4)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_intake_status')
    assert clock.sleeps == [0.125, 0.25, 0.5, 1.0]


def test_g1_entry_consult_per_call_drop_batch_intake_status_k4_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_intake_status', times=4)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_intake_status')
    assert clock.sleeps == [0.15625, 0.3125, 0.625, 1.25]


def test_g1_entry_consult_per_call_drop_batch_intake_status_k4_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_intake_status', times=4)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_intake_status')
    assert clock.sleeps == [0.1875, 0.375, 0.75, 1.5]


def test_g1_entry_consult_per_call_drop_batch_intake_status_k4_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_intake_status', times=4)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_intake_status')
    assert clock.sleeps == [0.25, 0.5, 1.0, 2.0]


def test_g1_entry_consult_per_call_drop_batch_intake_status_k5_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_intake_status', times=5)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_intake_status')
    assert clock.sleeps == [0.125, 0.25, 0.5, 1.0, 2.0]


def test_g1_entry_consult_per_call_drop_batch_intake_status_k5_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_intake_status', times=5)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_intake_status')
    assert clock.sleeps == [0.15625, 0.3125, 0.625, 1.25, 2.5]


def test_g1_entry_consult_per_call_drop_batch_intake_status_k5_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_intake_status', times=5)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_intake_status')
    assert clock.sleeps == [0.1875, 0.375, 0.75, 1.5, 3.0]


def test_g1_entry_consult_per_call_drop_batch_intake_status_k5_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_intake_status', times=5)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_intake_status')
    assert clock.sleeps == [0.25, 0.5, 1.0, 2.0, 4.0]


def test_g1_entry_consult_per_call_drop_batch_intake_status_k6_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_intake_status', times=6)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_intake_status')
    assert clock.sleeps == [0.125, 0.25, 0.5, 1.0, 2.0, 2.0]


def test_g1_entry_consult_per_call_drop_batch_intake_status_k6_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_intake_status', times=6)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_intake_status')
    assert clock.sleeps == [0.15625, 0.3125, 0.625, 1.25, 2.5, 2.5]


def test_g1_entry_consult_per_call_drop_batch_intake_status_k6_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_intake_status', times=6)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_intake_status')
    assert clock.sleeps == [0.1875, 0.375, 0.75, 1.5, 3.0, 3.0]


def test_g1_entry_consult_per_call_drop_batch_intake_status_k6_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_intake_status', times=6)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_intake_status')
    assert clock.sleeps == [0.25, 0.5, 1.0, 2.0, 4.0, 4.0]


def test_g1_entry_consult_per_call_drop_batch_intake_status_k7_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_intake_status', times=7)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_intake_status')
    assert clock.sleeps == [0.125, 0.25, 0.5, 1.0, 2.0, 2.0, 2.0]


def test_g1_entry_consult_per_call_drop_batch_intake_status_k7_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_intake_status', times=7)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_intake_status')
    assert clock.sleeps == [0.15625, 0.3125, 0.625, 1.25, 2.5, 2.5, 2.5]


def test_g1_entry_consult_per_call_drop_batch_intake_status_k7_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_intake_status', times=7)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_intake_status')
    assert clock.sleeps == [0.1875, 0.375, 0.75, 1.5, 3.0, 3.0, 3.0]


def test_g1_entry_consult_per_call_drop_batch_intake_status_k7_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_intake_status', times=7)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_intake_status')
    assert clock.sleeps == [0.25, 0.5, 1.0, 2.0, 4.0, 4.0, 4.0]


def test_g1_entry_consult_per_call_drop_batch_intake_status_k8_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_intake_status', times=8)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_intake_status')
    assert clock.sleeps == [0.125, 0.25, 0.5, 1.0, 2.0, 2.0, 2.0, 2.0]


def test_g1_entry_consult_per_call_drop_batch_intake_status_k8_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_intake_status', times=8)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_intake_status')
    assert clock.sleeps == [0.15625, 0.3125, 0.625, 1.25, 2.5, 2.5, 2.5, 2.5]


def test_g1_entry_consult_per_call_drop_batch_intake_status_k8_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_intake_status', times=8)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_intake_status')
    assert clock.sleeps == [0.1875, 0.375, 0.75, 1.5, 3.0, 3.0, 3.0, 3.0]


def test_g1_entry_consult_per_call_drop_batch_intake_status_k8_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_intake_status', times=8)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_intake_status')
    assert clock.sleeps == [0.25, 0.5, 1.0, 2.0, 4.0, 4.0, 4.0, 4.0]


def test_g1_entry_consult_per_call_drop_batch_intake_status_k9_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_intake_status', times=9)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_intake_status')
    assert clock.sleeps == [0.125, 0.25, 0.5, 1.0, 2.0, 2.0, 2.0, 2.0, 2.0]


def test_g1_entry_consult_per_call_drop_batch_intake_status_k9_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_intake_status', times=9)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_intake_status')
    assert clock.sleeps == [0.15625, 0.3125, 0.625, 1.25, 2.5, 2.5, 2.5, 2.5, 2.5]


def test_g1_entry_consult_per_call_drop_batch_intake_status_k9_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_intake_status', times=9)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_intake_status')
    assert clock.sleeps == [0.1875, 0.375, 0.75, 1.5, 3.0, 3.0, 3.0, 3.0, 3.0]


def test_g1_entry_consult_per_call_drop_batch_intake_status_k9_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_intake_status', times=9)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_intake_status')
    assert clock.sleeps == [0.25, 0.5, 1.0, 2.0, 4.0, 4.0, 4.0, 4.0, 4.0]


def test_g1_entry_consult_per_call_drop_batch_intake_status_k10_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_intake_status', times=10)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_intake_status')
    assert clock.sleeps == [0.125, 0.25, 0.5, 1.0, 2.0, 2.0, 2.0, 2.0, 2.0, 2.0]


def test_g1_entry_consult_per_call_drop_batch_intake_status_k10_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_intake_status', times=10)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_intake_status')
    assert clock.sleeps == [0.15625, 0.3125, 0.625, 1.25, 2.5, 2.5, 2.5, 2.5, 2.5, 2.5]


def test_g1_entry_consult_per_call_drop_batch_intake_status_k10_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_intake_status', times=10)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_intake_status')
    assert clock.sleeps == [0.1875, 0.375, 0.75, 1.5, 3.0, 3.0, 3.0, 3.0, 3.0, 3.0]


def test_g1_entry_consult_per_call_drop_batch_intake_status_k10_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_intake_status', times=10)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_intake_status')
    assert clock.sleeps == [0.25, 0.5, 1.0, 2.0, 4.0, 4.0, 4.0, 4.0, 4.0, 4.0]


def test_g1_entry_consult_per_call_drop_batch_complete_k1_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_complete', times=1)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_complete')
    assert clock.sleeps == [0.125]


def test_g1_entry_consult_per_call_drop_batch_complete_k1_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_complete', times=1)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_complete')
    assert clock.sleeps == [0.15625]


def test_g1_entry_consult_per_call_drop_batch_complete_k1_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_complete', times=1)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_complete')
    assert clock.sleeps == [0.1875]


def test_g1_entry_consult_per_call_drop_batch_complete_k1_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_complete', times=1)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_complete')
    assert clock.sleeps == [0.25]


def test_g1_entry_consult_per_call_drop_batch_complete_k2_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_complete', times=2)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_complete')
    assert clock.sleeps == [0.125, 0.25]


def test_g1_entry_consult_per_call_drop_batch_complete_k2_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_complete', times=2)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_complete')
    assert clock.sleeps == [0.15625, 0.3125]


def test_g1_entry_consult_per_call_drop_batch_complete_k2_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_complete', times=2)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_complete')
    assert clock.sleeps == [0.1875, 0.375]


def test_g1_entry_consult_per_call_drop_batch_complete_k2_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_complete', times=2)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_complete')
    assert clock.sleeps == [0.25, 0.5]


def test_g1_entry_consult_per_call_drop_batch_complete_k3_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_complete', times=3)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_complete')
    assert clock.sleeps == [0.125, 0.25, 0.5]


def test_g1_entry_consult_per_call_drop_batch_complete_k3_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_complete', times=3)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_complete')
    assert clock.sleeps == [0.15625, 0.3125, 0.625]


def test_g1_entry_consult_per_call_drop_batch_complete_k3_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_complete', times=3)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_complete')
    assert clock.sleeps == [0.1875, 0.375, 0.75]


def test_g1_entry_consult_per_call_drop_batch_complete_k3_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_complete', times=3)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_complete')
    assert clock.sleeps == [0.25, 0.5, 1.0]


def test_g1_entry_consult_per_call_drop_batch_complete_k4_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_complete', times=4)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_complete')
    assert clock.sleeps == [0.125, 0.25, 0.5, 1.0]


def test_g1_entry_consult_per_call_drop_batch_complete_k4_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_complete', times=4)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_complete')
    assert clock.sleeps == [0.15625, 0.3125, 0.625, 1.25]


def test_g1_entry_consult_per_call_drop_batch_complete_k4_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_complete', times=4)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_complete')
    assert clock.sleeps == [0.1875, 0.375, 0.75, 1.5]


def test_g1_entry_consult_per_call_drop_batch_complete_k4_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_complete', times=4)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_complete')
    assert clock.sleeps == [0.25, 0.5, 1.0, 2.0]


def test_g1_entry_consult_per_call_drop_batch_complete_k5_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_complete', times=5)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_complete')
    assert clock.sleeps == [0.125, 0.25, 0.5, 1.0, 2.0]


def test_g1_entry_consult_per_call_drop_batch_complete_k5_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_complete', times=5)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_complete')
    assert clock.sleeps == [0.15625, 0.3125, 0.625, 1.25, 2.5]


def test_g1_entry_consult_per_call_drop_batch_complete_k5_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_complete', times=5)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_complete')
    assert clock.sleeps == [0.1875, 0.375, 0.75, 1.5, 3.0]


def test_g1_entry_consult_per_call_drop_batch_complete_k5_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_complete', times=5)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_complete')
    assert clock.sleeps == [0.25, 0.5, 1.0, 2.0, 4.0]


def test_g1_entry_consult_per_call_drop_batch_complete_k6_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_complete', times=6)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_complete')
    assert clock.sleeps == [0.125, 0.25, 0.5, 1.0, 2.0, 2.0]


def test_g1_entry_consult_per_call_drop_batch_complete_k6_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_complete', times=6)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_complete')
    assert clock.sleeps == [0.15625, 0.3125, 0.625, 1.25, 2.5, 2.5]


def test_g1_entry_consult_per_call_drop_batch_complete_k6_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_complete', times=6)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_complete')
    assert clock.sleeps == [0.1875, 0.375, 0.75, 1.5, 3.0, 3.0]


def test_g1_entry_consult_per_call_drop_batch_complete_k6_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_complete', times=6)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_complete')
    assert clock.sleeps == [0.25, 0.5, 1.0, 2.0, 4.0, 4.0]


def test_g1_entry_consult_per_call_drop_batch_complete_k7_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_complete', times=7)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_complete')
    assert clock.sleeps == [0.125, 0.25, 0.5, 1.0, 2.0, 2.0, 2.0]


def test_g1_entry_consult_per_call_drop_batch_complete_k7_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_complete', times=7)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_complete')
    assert clock.sleeps == [0.15625, 0.3125, 0.625, 1.25, 2.5, 2.5, 2.5]


def test_g1_entry_consult_per_call_drop_batch_complete_k7_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_complete', times=7)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_complete')
    assert clock.sleeps == [0.1875, 0.375, 0.75, 1.5, 3.0, 3.0, 3.0]


def test_g1_entry_consult_per_call_drop_batch_complete_k7_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_complete', times=7)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_complete')
    assert clock.sleeps == [0.25, 0.5, 1.0, 2.0, 4.0, 4.0, 4.0]


def test_g1_entry_consult_per_call_drop_batch_complete_k8_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_complete', times=8)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_complete')
    assert clock.sleeps == [0.125, 0.25, 0.5, 1.0, 2.0, 2.0, 2.0, 2.0]


def test_g1_entry_consult_per_call_drop_batch_complete_k8_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_complete', times=8)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_complete')
    assert clock.sleeps == [0.15625, 0.3125, 0.625, 1.25, 2.5, 2.5, 2.5, 2.5]


def test_g1_entry_consult_per_call_drop_batch_complete_k8_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_complete', times=8)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_complete')
    assert clock.sleeps == [0.1875, 0.375, 0.75, 1.5, 3.0, 3.0, 3.0, 3.0]


def test_g1_entry_consult_per_call_drop_batch_complete_k8_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_complete', times=8)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_complete')
    assert clock.sleeps == [0.25, 0.5, 1.0, 2.0, 4.0, 4.0, 4.0, 4.0]


def test_g1_entry_consult_per_call_drop_batch_complete_k9_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_complete', times=9)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_complete')
    assert clock.sleeps == [0.125, 0.25, 0.5, 1.0, 2.0, 2.0, 2.0, 2.0, 2.0]


def test_g1_entry_consult_per_call_drop_batch_complete_k9_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_complete', times=9)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_complete')
    assert clock.sleeps == [0.15625, 0.3125, 0.625, 1.25, 2.5, 2.5, 2.5, 2.5, 2.5]


def test_g1_entry_consult_per_call_drop_batch_complete_k9_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_complete', times=9)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_complete')
    assert clock.sleeps == [0.1875, 0.375, 0.75, 1.5, 3.0, 3.0, 3.0, 3.0, 3.0]


def test_g1_entry_consult_per_call_drop_batch_complete_k9_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_complete', times=9)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_complete')
    assert clock.sleeps == [0.25, 0.5, 1.0, 2.0, 4.0, 4.0, 4.0, 4.0, 4.0]


def test_g1_entry_consult_per_call_drop_batch_complete_k10_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_complete', times=10)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_complete')
    assert clock.sleeps == [0.125, 0.25, 0.5, 1.0, 2.0, 2.0, 2.0, 2.0, 2.0, 2.0]


def test_g1_entry_consult_per_call_drop_batch_complete_k10_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_complete', times=10)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_complete')
    assert clock.sleeps == [0.15625, 0.3125, 0.625, 1.25, 2.5, 2.5, 2.5, 2.5, 2.5, 2.5]


def test_g1_entry_consult_per_call_drop_batch_complete_k10_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_complete', times=10)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_complete')
    assert clock.sleeps == [0.1875, 0.375, 0.75, 1.5, 3.0, 3.0, 3.0, 3.0, 3.0, 3.0]


def test_g1_entry_consult_per_call_drop_batch_complete_k10_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_complete', times=10)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_complete')
    assert clock.sleeps == [0.25, 0.5, 1.0, 2.0, 4.0, 4.0, 4.0, 4.0, 4.0, 4.0]


def test_g1_entry_consult_per_call_drop_batch_recovery_settle_k1_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_recovery_settle', times=1)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_recovery_settle')
    assert clock.sleeps == [0.125]


def test_g1_entry_consult_per_call_drop_batch_recovery_settle_k1_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_recovery_settle', times=1)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_recovery_settle')
    assert clock.sleeps == [0.15625]


def test_g1_entry_consult_per_call_drop_batch_recovery_settle_k1_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_recovery_settle', times=1)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_recovery_settle')
    assert clock.sleeps == [0.1875]


def test_g1_entry_consult_per_call_drop_batch_recovery_settle_k1_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_recovery_settle', times=1)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_recovery_settle')
    assert clock.sleeps == [0.25]


def test_g1_entry_consult_per_call_drop_batch_recovery_settle_k2_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_recovery_settle', times=2)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_recovery_settle')
    assert clock.sleeps == [0.125, 0.25]


def test_g1_entry_consult_per_call_drop_batch_recovery_settle_k2_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_recovery_settle', times=2)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_recovery_settle')
    assert clock.sleeps == [0.15625, 0.3125]


def test_g1_entry_consult_per_call_drop_batch_recovery_settle_k2_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_recovery_settle', times=2)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_recovery_settle')
    assert clock.sleeps == [0.1875, 0.375]


def test_g1_entry_consult_per_call_drop_batch_recovery_settle_k2_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_recovery_settle', times=2)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_recovery_settle')
    assert clock.sleeps == [0.25, 0.5]


def test_g1_entry_consult_per_call_drop_batch_recovery_settle_k3_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_recovery_settle', times=3)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_recovery_settle')
    assert clock.sleeps == [0.125, 0.25, 0.5]


def test_g1_entry_consult_per_call_drop_batch_recovery_settle_k3_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_recovery_settle', times=3)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_recovery_settle')
    assert clock.sleeps == [0.15625, 0.3125, 0.625]


def test_g1_entry_consult_per_call_drop_batch_recovery_settle_k3_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_recovery_settle', times=3)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_recovery_settle')
    assert clock.sleeps == [0.1875, 0.375, 0.75]


def test_g1_entry_consult_per_call_drop_batch_recovery_settle_k3_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_recovery_settle', times=3)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_recovery_settle')
    assert clock.sleeps == [0.25, 0.5, 1.0]


def test_g1_entry_consult_per_call_drop_batch_recovery_settle_k4_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_recovery_settle', times=4)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_recovery_settle')
    assert clock.sleeps == [0.125, 0.25, 0.5, 1.0]


def test_g1_entry_consult_per_call_drop_batch_recovery_settle_k4_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_recovery_settle', times=4)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_recovery_settle')
    assert clock.sleeps == [0.15625, 0.3125, 0.625, 1.25]


def test_g1_entry_consult_per_call_drop_batch_recovery_settle_k4_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_recovery_settle', times=4)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_recovery_settle')
    assert clock.sleeps == [0.1875, 0.375, 0.75, 1.5]


def test_g1_entry_consult_per_call_drop_batch_recovery_settle_k4_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_recovery_settle', times=4)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_recovery_settle')
    assert clock.sleeps == [0.25, 0.5, 1.0, 2.0]


def test_g1_entry_consult_per_call_drop_batch_recovery_settle_k5_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_recovery_settle', times=5)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_recovery_settle')
    assert clock.sleeps == [0.125, 0.25, 0.5, 1.0, 2.0]


def test_g1_entry_consult_per_call_drop_batch_recovery_settle_k5_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_recovery_settle', times=5)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_recovery_settle')
    assert clock.sleeps == [0.15625, 0.3125, 0.625, 1.25, 2.5]


def test_g1_entry_consult_per_call_drop_batch_recovery_settle_k5_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_recovery_settle', times=5)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_recovery_settle')
    assert clock.sleeps == [0.1875, 0.375, 0.75, 1.5, 3.0]


def test_g1_entry_consult_per_call_drop_batch_recovery_settle_k5_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_recovery_settle', times=5)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_recovery_settle')
    assert clock.sleeps == [0.25, 0.5, 1.0, 2.0, 4.0]


def test_g1_entry_consult_per_call_drop_batch_recovery_settle_k6_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_recovery_settle', times=6)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_recovery_settle')
    assert clock.sleeps == [0.125, 0.25, 0.5, 1.0, 2.0, 2.0]


def test_g1_entry_consult_per_call_drop_batch_recovery_settle_k6_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_recovery_settle', times=6)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_recovery_settle')
    assert clock.sleeps == [0.15625, 0.3125, 0.625, 1.25, 2.5, 2.5]


def test_g1_entry_consult_per_call_drop_batch_recovery_settle_k6_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_recovery_settle', times=6)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_recovery_settle')
    assert clock.sleeps == [0.1875, 0.375, 0.75, 1.5, 3.0, 3.0]


def test_g1_entry_consult_per_call_drop_batch_recovery_settle_k6_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_recovery_settle', times=6)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_recovery_settle')
    assert clock.sleeps == [0.25, 0.5, 1.0, 2.0, 4.0, 4.0]


def test_g1_entry_consult_per_call_drop_batch_recovery_settle_k7_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_recovery_settle', times=7)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_recovery_settle')
    assert clock.sleeps == [0.125, 0.25, 0.5, 1.0, 2.0, 2.0, 2.0]


def test_g1_entry_consult_per_call_drop_batch_recovery_settle_k7_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_recovery_settle', times=7)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_recovery_settle')
    assert clock.sleeps == [0.15625, 0.3125, 0.625, 1.25, 2.5, 2.5, 2.5]


def test_g1_entry_consult_per_call_drop_batch_recovery_settle_k7_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_recovery_settle', times=7)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_recovery_settle')
    assert clock.sleeps == [0.1875, 0.375, 0.75, 1.5, 3.0, 3.0, 3.0]


def test_g1_entry_consult_per_call_drop_batch_recovery_settle_k7_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_recovery_settle', times=7)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_recovery_settle')
    assert clock.sleeps == [0.25, 0.5, 1.0, 2.0, 4.0, 4.0, 4.0]


def test_g1_entry_consult_per_call_drop_batch_recovery_settle_k8_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_recovery_settle', times=8)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_recovery_settle')
    assert clock.sleeps == [0.125, 0.25, 0.5, 1.0, 2.0, 2.0, 2.0, 2.0]


def test_g1_entry_consult_per_call_drop_batch_recovery_settle_k8_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_recovery_settle', times=8)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_recovery_settle')
    assert clock.sleeps == [0.15625, 0.3125, 0.625, 1.25, 2.5, 2.5, 2.5, 2.5]


def test_g1_entry_consult_per_call_drop_batch_recovery_settle_k8_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_recovery_settle', times=8)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_recovery_settle')
    assert clock.sleeps == [0.1875, 0.375, 0.75, 1.5, 3.0, 3.0, 3.0, 3.0]


def test_g1_entry_consult_per_call_drop_batch_recovery_settle_k8_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_recovery_settle', times=8)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_recovery_settle')
    assert clock.sleeps == [0.25, 0.5, 1.0, 2.0, 4.0, 4.0, 4.0, 4.0]


def test_g1_entry_consult_per_call_drop_batch_recovery_settle_k9_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_recovery_settle', times=9)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_recovery_settle')
    assert clock.sleeps == [0.125, 0.25, 0.5, 1.0, 2.0, 2.0, 2.0, 2.0, 2.0]


def test_g1_entry_consult_per_call_drop_batch_recovery_settle_k9_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_recovery_settle', times=9)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_recovery_settle')
    assert clock.sleeps == [0.15625, 0.3125, 0.625, 1.25, 2.5, 2.5, 2.5, 2.5, 2.5]


def test_g1_entry_consult_per_call_drop_batch_recovery_settle_k9_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_recovery_settle', times=9)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_recovery_settle')
    assert clock.sleeps == [0.1875, 0.375, 0.75, 1.5, 3.0, 3.0, 3.0, 3.0, 3.0]


def test_g1_entry_consult_per_call_drop_batch_recovery_settle_k9_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_recovery_settle', times=9)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_recovery_settle')
    assert clock.sleeps == [0.25, 0.5, 1.0, 2.0, 4.0, 4.0, 4.0, 4.0, 4.0]


def test_g1_entry_consult_per_call_drop_batch_recovery_settle_k10_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_recovery_settle', times=10)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_recovery_settle')
    assert clock.sleeps == [0.125, 0.25, 0.5, 1.0, 2.0, 2.0, 2.0, 2.0, 2.0, 2.0]


def test_g1_entry_consult_per_call_drop_batch_recovery_settle_k10_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_recovery_settle', times=10)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_recovery_settle')
    assert clock.sleeps == [0.15625, 0.3125, 0.625, 1.25, 2.5, 2.5, 2.5, 2.5, 2.5, 2.5]


def test_g1_entry_consult_per_call_drop_batch_recovery_settle_k10_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_recovery_settle', times=10)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_recovery_settle')
    assert clock.sleeps == [0.1875, 0.375, 0.75, 1.5, 3.0, 3.0, 3.0, 3.0, 3.0, 3.0]


def test_g1_entry_consult_per_call_drop_batch_recovery_settle_k10_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_recovery_settle', times=10)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_recovery_settle')
    assert clock.sleeps == [0.25, 0.5, 1.0, 2.0, 4.0, 4.0, 4.0, 4.0, 4.0, 4.0]


def test_g1_entry_consult_per_call_drop_batch_pull_shard_scheduler_17_k1_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_pull shard=scheduler_17', times=1)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_pull shard=scheduler_17')
    assert clock.sleeps == [0.125]


def test_g1_entry_consult_per_call_drop_batch_pull_shard_scheduler_17_k1_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_pull shard=scheduler_17', times=1)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_pull shard=scheduler_17')
    assert clock.sleeps == [0.15625]


def test_g1_entry_consult_per_call_drop_batch_pull_shard_scheduler_17_k1_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_pull shard=scheduler_17', times=1)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_pull shard=scheduler_17')
    assert clock.sleeps == [0.1875]


def test_g1_entry_consult_per_call_drop_batch_pull_shard_scheduler_17_k1_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_pull shard=scheduler_17', times=1)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_pull shard=scheduler_17')
    assert clock.sleeps == [0.25]


def test_g1_entry_consult_per_call_drop_batch_pull_shard_scheduler_17_k2_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_pull shard=scheduler_17', times=2)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_pull shard=scheduler_17')
    assert clock.sleeps == [0.125, 0.25]


def test_g1_entry_consult_per_call_drop_batch_pull_shard_scheduler_17_k2_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_pull shard=scheduler_17', times=2)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_pull shard=scheduler_17')
    assert clock.sleeps == [0.15625, 0.3125]


def test_g1_entry_consult_per_call_drop_batch_pull_shard_scheduler_17_k2_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_pull shard=scheduler_17', times=2)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_pull shard=scheduler_17')
    assert clock.sleeps == [0.1875, 0.375]


def test_g1_entry_consult_per_call_drop_batch_pull_shard_scheduler_17_k2_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_pull shard=scheduler_17', times=2)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_pull shard=scheduler_17')
    assert clock.sleeps == [0.25, 0.5]


def test_g1_entry_consult_per_call_drop_batch_pull_shard_scheduler_17_k3_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_pull shard=scheduler_17', times=3)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_pull shard=scheduler_17')
    assert clock.sleeps == [0.125, 0.25, 0.5]


def test_g1_entry_consult_per_call_drop_batch_pull_shard_scheduler_17_k3_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_pull shard=scheduler_17', times=3)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_pull shard=scheduler_17')
    assert clock.sleeps == [0.15625, 0.3125, 0.625]


def test_g1_entry_consult_per_call_drop_batch_pull_shard_scheduler_17_k3_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_pull shard=scheduler_17', times=3)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_pull shard=scheduler_17')
    assert clock.sleeps == [0.1875, 0.375, 0.75]


def test_g1_entry_consult_per_call_drop_batch_pull_shard_scheduler_17_k3_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_pull shard=scheduler_17', times=3)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_pull shard=scheduler_17')
    assert clock.sleeps == [0.25, 0.5, 1.0]


def test_g1_entry_consult_per_call_drop_batch_pull_shard_scheduler_17_k4_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_pull shard=scheduler_17', times=4)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_pull shard=scheduler_17')
    assert clock.sleeps == [0.125, 0.25, 0.5, 1.0]


def test_g1_entry_consult_per_call_drop_batch_pull_shard_scheduler_17_k4_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_pull shard=scheduler_17', times=4)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_pull shard=scheduler_17')
    assert clock.sleeps == [0.15625, 0.3125, 0.625, 1.25]


def test_g1_entry_consult_per_call_drop_batch_pull_shard_scheduler_17_k4_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_pull shard=scheduler_17', times=4)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_pull shard=scheduler_17')
    assert clock.sleeps == [0.1875, 0.375, 0.75, 1.5]


def test_g1_entry_consult_per_call_drop_batch_pull_shard_scheduler_17_k4_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_pull shard=scheduler_17', times=4)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_pull shard=scheduler_17')
    assert clock.sleeps == [0.25, 0.5, 1.0, 2.0]


def test_g1_entry_consult_per_call_drop_batch_pull_shard_scheduler_17_k5_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_pull shard=scheduler_17', times=5)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_pull shard=scheduler_17')
    assert clock.sleeps == [0.125, 0.25, 0.5, 1.0, 2.0]


def test_g1_entry_consult_per_call_drop_batch_pull_shard_scheduler_17_k5_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_pull shard=scheduler_17', times=5)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_pull shard=scheduler_17')
    assert clock.sleeps == [0.15625, 0.3125, 0.625, 1.25, 2.5]


def test_g1_entry_consult_per_call_drop_batch_pull_shard_scheduler_17_k5_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_pull shard=scheduler_17', times=5)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_pull shard=scheduler_17')
    assert clock.sleeps == [0.1875, 0.375, 0.75, 1.5, 3.0]


def test_g1_entry_consult_per_call_drop_batch_pull_shard_scheduler_17_k5_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_pull shard=scheduler_17', times=5)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_pull shard=scheduler_17')
    assert clock.sleeps == [0.25, 0.5, 1.0, 2.0, 4.0]


def test_g1_entry_consult_per_call_drop_batch_pull_shard_scheduler_17_k6_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_pull shard=scheduler_17', times=6)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_pull shard=scheduler_17')
    assert clock.sleeps == [0.125, 0.25, 0.5, 1.0, 2.0, 2.0]


def test_g1_entry_consult_per_call_drop_batch_pull_shard_scheduler_17_k6_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_pull shard=scheduler_17', times=6)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_pull shard=scheduler_17')
    assert clock.sleeps == [0.15625, 0.3125, 0.625, 1.25, 2.5, 2.5]


def test_g1_entry_consult_per_call_drop_batch_pull_shard_scheduler_17_k6_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_pull shard=scheduler_17', times=6)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_pull shard=scheduler_17')
    assert clock.sleeps == [0.1875, 0.375, 0.75, 1.5, 3.0, 3.0]


def test_g1_entry_consult_per_call_drop_batch_pull_shard_scheduler_17_k6_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_pull shard=scheduler_17', times=6)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_pull shard=scheduler_17')
    assert clock.sleeps == [0.25, 0.5, 1.0, 2.0, 4.0, 4.0]


def test_g1_entry_consult_per_call_drop_batch_pull_shard_scheduler_17_k7_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_pull shard=scheduler_17', times=7)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_pull shard=scheduler_17')
    assert clock.sleeps == [0.125, 0.25, 0.5, 1.0, 2.0, 2.0, 2.0]


def test_g1_entry_consult_per_call_drop_batch_pull_shard_scheduler_17_k7_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_pull shard=scheduler_17', times=7)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_pull shard=scheduler_17')
    assert clock.sleeps == [0.15625, 0.3125, 0.625, 1.25, 2.5, 2.5, 2.5]


def test_g1_entry_consult_per_call_drop_batch_pull_shard_scheduler_17_k7_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_pull shard=scheduler_17', times=7)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_pull shard=scheduler_17')
    assert clock.sleeps == [0.1875, 0.375, 0.75, 1.5, 3.0, 3.0, 3.0]


def test_g1_entry_consult_per_call_drop_batch_pull_shard_scheduler_17_k7_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_pull shard=scheduler_17', times=7)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_pull shard=scheduler_17')
    assert clock.sleeps == [0.25, 0.5, 1.0, 2.0, 4.0, 4.0, 4.0]


def test_g1_entry_consult_per_call_drop_batch_pull_shard_scheduler_17_k8_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_pull shard=scheduler_17', times=8)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_pull shard=scheduler_17')
    assert clock.sleeps == [0.125, 0.25, 0.5, 1.0, 2.0, 2.0, 2.0, 2.0]


def test_g1_entry_consult_per_call_drop_batch_pull_shard_scheduler_17_k8_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_pull shard=scheduler_17', times=8)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_pull shard=scheduler_17')
    assert clock.sleeps == [0.15625, 0.3125, 0.625, 1.25, 2.5, 2.5, 2.5, 2.5]


def test_g1_entry_consult_per_call_drop_batch_pull_shard_scheduler_17_k8_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_pull shard=scheduler_17', times=8)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_pull shard=scheduler_17')
    assert clock.sleeps == [0.1875, 0.375, 0.75, 1.5, 3.0, 3.0, 3.0, 3.0]


def test_g1_entry_consult_per_call_drop_batch_pull_shard_scheduler_17_k8_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_pull shard=scheduler_17', times=8)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_pull shard=scheduler_17')
    assert clock.sleeps == [0.25, 0.5, 1.0, 2.0, 4.0, 4.0, 4.0, 4.0]


def test_g1_entry_consult_per_call_drop_batch_pull_shard_scheduler_17_k9_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_pull shard=scheduler_17', times=9)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_pull shard=scheduler_17')
    assert clock.sleeps == [0.125, 0.25, 0.5, 1.0, 2.0, 2.0, 2.0, 2.0, 2.0]


def test_g1_entry_consult_per_call_drop_batch_pull_shard_scheduler_17_k9_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_pull shard=scheduler_17', times=9)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_pull shard=scheduler_17')
    assert clock.sleeps == [0.15625, 0.3125, 0.625, 1.25, 2.5, 2.5, 2.5, 2.5, 2.5]


def test_g1_entry_consult_per_call_drop_batch_pull_shard_scheduler_17_k9_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_pull shard=scheduler_17', times=9)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_pull shard=scheduler_17')
    assert clock.sleeps == [0.1875, 0.375, 0.75, 1.5, 3.0, 3.0, 3.0, 3.0, 3.0]


def test_g1_entry_consult_per_call_drop_batch_pull_shard_scheduler_17_k9_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_pull shard=scheduler_17', times=9)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_pull shard=scheduler_17')
    assert clock.sleeps == [0.25, 0.5, 1.0, 2.0, 4.0, 4.0, 4.0, 4.0, 4.0]


def test_g1_entry_consult_per_call_drop_batch_pull_shard_scheduler_17_k10_j0p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_pull shard=scheduler_17', times=10)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_pull shard=scheduler_17')
    assert clock.sleeps == [0.125, 0.25, 0.5, 1.0, 2.0, 2.0, 2.0, 2.0, 2.0, 2.0]


def test_g1_entry_consult_per_call_drop_batch_pull_shard_scheduler_17_k10_j0p25(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_pull shard=scheduler_17', times=10)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_pull shard=scheduler_17')
    assert clock.sleeps == [0.15625, 0.3125, 0.625, 1.25, 2.5, 2.5, 2.5, 2.5, 2.5, 2.5]


def test_g1_entry_consult_per_call_drop_batch_pull_shard_scheduler_17_k10_j0p5(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_pull shard=scheduler_17', times=10)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_pull shard=scheduler_17')
    assert clock.sleeps == [0.1875, 0.375, 0.75, 1.5, 3.0, 3.0, 3.0, 3.0, 3.0, 3.0]


def test_g1_entry_consult_per_call_drop_batch_pull_shard_scheduler_17_k10_j1p0(mp):
    """Sibling entry consults the exhaustion window another instance armed."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_pull shard=scheduler_17', times=10)
    del A
    B = default_store(mp, ns=NS, client=healthy_client())
    assert B._storm_damper is storage._SHARED_STORM_DAMPERS[NS]
    B.run(lambda tx: 'ok', operation='batch_pull shard=scheduler_17')
    assert clock.sleeps == [0.25, 0.5, 1.0, 2.0, 4.0, 4.0, 4.0, 4.0, 4.0, 4.0]


def test_g2_no_gate_on_first_attempt_batch_merge_commit_j0p0(mp):
    """A chain that reached the transaction is never gated on its first attempt."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=1)
    rungs = []
    patch_chain(mp, rungs.append)
    B = default_store(mp, ns=NS, client=aborting_chain_client(0))
    B.run(mid_chain_arm_body(damper, 'batch_merge_commit', arm_on=1), operation='batch_merge_commit')
    assert rungs == []
    assert clock.sleeps[-1] == pytest.approx(0.125)


def test_g2_no_gate_on_first_attempt_batch_merge_commit_j0p25(mp):
    """A chain that reached the transaction is never gated on its first attempt."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=1)
    rungs = []
    patch_chain(mp, rungs.append)
    B = default_store(mp, ns=NS, client=aborting_chain_client(0))
    B.run(mid_chain_arm_body(damper, 'batch_merge_commit', arm_on=1), operation='batch_merge_commit')
    assert rungs == []
    assert clock.sleeps[-1] == pytest.approx(0.15625)


def test_g2_no_gate_on_first_attempt_batch_merge_commit_j0p5(mp):
    """A chain that reached the transaction is never gated on its first attempt."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=1)
    rungs = []
    patch_chain(mp, rungs.append)
    B = default_store(mp, ns=NS, client=aborting_chain_client(0))
    B.run(mid_chain_arm_body(damper, 'batch_merge_commit', arm_on=1), operation='batch_merge_commit')
    assert rungs == []
    assert clock.sleeps[-1] == pytest.approx(0.1875)


def test_g2_no_gate_on_first_attempt_batch_merge_commit_j1p0(mp):
    """A chain that reached the transaction is never gated on its first attempt."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=1)
    rungs = []
    patch_chain(mp, rungs.append)
    B = default_store(mp, ns=NS, client=aborting_chain_client(0))
    B.run(mid_chain_arm_body(damper, 'batch_merge_commit', arm_on=1), operation='batch_merge_commit')
    assert rungs == []
    assert clock.sleeps[-1] == pytest.approx(0.25)


def test_g2_no_gate_on_first_attempt_batch_provider_stt_j0p0(mp):
    """A chain that reached the transaction is never gated on its first attempt."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=1)
    rungs = []
    patch_chain(mp, rungs.append)
    B = default_store(mp, ns=NS, client=aborting_chain_client(0))
    B.run(mid_chain_arm_body(damper, 'batch_provider_stt', arm_on=1), operation='batch_provider_stt')
    assert rungs == []
    assert clock.sleeps[-1] == pytest.approx(0.125)


def test_g2_no_gate_on_first_attempt_batch_provider_stt_j0p25(mp):
    """A chain that reached the transaction is never gated on its first attempt."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=1)
    rungs = []
    patch_chain(mp, rungs.append)
    B = default_store(mp, ns=NS, client=aborting_chain_client(0))
    B.run(mid_chain_arm_body(damper, 'batch_provider_stt', arm_on=1), operation='batch_provider_stt')
    assert rungs == []
    assert clock.sleeps[-1] == pytest.approx(0.15625)


def test_g2_no_gate_on_first_attempt_batch_provider_stt_j0p5(mp):
    """A chain that reached the transaction is never gated on its first attempt."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=1)
    rungs = []
    patch_chain(mp, rungs.append)
    B = default_store(mp, ns=NS, client=aborting_chain_client(0))
    B.run(mid_chain_arm_body(damper, 'batch_provider_stt', arm_on=1), operation='batch_provider_stt')
    assert rungs == []
    assert clock.sleeps[-1] == pytest.approx(0.1875)


def test_g2_no_gate_on_first_attempt_batch_provider_stt_j1p0(mp):
    """A chain that reached the transaction is never gated on its first attempt."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=1)
    rungs = []
    patch_chain(mp, rungs.append)
    B = default_store(mp, ns=NS, client=aborting_chain_client(0))
    B.run(mid_chain_arm_body(damper, 'batch_provider_stt', arm_on=1), operation='batch_provider_stt')
    assert rungs == []
    assert clock.sleeps[-1] == pytest.approx(0.25)


def test_g2_gate_rung2_armdepth2_j0p0_batch_merge_commit(mp):
    """Rung 2 waits out the window a sibling armed mid-chain (failure depth 2)."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=1)
    rungs = []
    patch_chain(mp, rungs.append)
    B = default_store(mp, ns=NS, client=aborting_chain_client(2))
    B.run(mid_chain_arm_body(damper, 'batch_merge_commit', arm_on=1), operation='batch_merge_commit')
    assert rungs[-1] == pytest.approx(0.45)
    assert clock.sleeps[-1] == pytest.approx(0.125)
    assert clock.sleeps == [0.125]


def test_g2_gate_rung2_armdepth2_j0p25_batch_merge_commit(mp):
    """Rung 2 waits out the window a sibling armed mid-chain (failure depth 2)."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=1)
    rungs = []
    patch_chain(mp, rungs.append)
    B = default_store(mp, ns=NS, client=aborting_chain_client(2))
    B.run(mid_chain_arm_body(damper, 'batch_merge_commit', arm_on=1), operation='batch_merge_commit')
    assert rungs[-1] == pytest.approx(0.5125)
    assert clock.sleeps[-1] == pytest.approx(0.15625)
    assert clock.sleeps == [0.15625]


def test_g2_gate_rung2_armdepth2_j0p5_batch_merge_commit(mp):
    """Rung 2 waits out the window a sibling armed mid-chain (failure depth 2)."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=1)
    rungs = []
    patch_chain(mp, rungs.append)
    B = default_store(mp, ns=NS, client=aborting_chain_client(2))
    B.run(mid_chain_arm_body(damper, 'batch_merge_commit', arm_on=1), operation='batch_merge_commit')
    assert rungs[-1] == pytest.approx(0.575)
    assert clock.sleeps[-1] == pytest.approx(0.1875)
    assert clock.sleeps == [0.1875]


def test_g2_gate_rung2_armdepth2_j1p0_batch_merge_commit(mp):
    """Rung 2 waits out the window a sibling armed mid-chain (failure depth 2)."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=1)
    rungs = []
    patch_chain(mp, rungs.append)
    B = default_store(mp, ns=NS, client=aborting_chain_client(2))
    B.run(mid_chain_arm_body(damper, 'batch_merge_commit', arm_on=1), operation='batch_merge_commit')
    assert rungs[-1] == pytest.approx(0.7)
    assert clock.sleeps[-1] == pytest.approx(0.25)
    assert clock.sleeps == [0.25]


def test_g2_gate_rung2_armdepth3_j0p0_batch_merge_commit(mp):
    """Rung 2 waits out the window a sibling armed mid-chain (failure depth 3)."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=2)
    rungs = []
    patch_chain(mp, rungs.append)
    B = default_store(mp, ns=NS, client=aborting_chain_client(2))
    B.run(mid_chain_arm_body(damper, 'batch_merge_commit', arm_on=1), operation='batch_merge_commit')
    assert rungs[-1] == pytest.approx(0.7)
    assert clock.sleeps[-1] == pytest.approx(0.25)
    assert clock.sleeps == [0.125, 0.25]


def test_g2_gate_rung2_armdepth3_j0p25_batch_merge_commit(mp):
    """Rung 2 waits out the window a sibling armed mid-chain (failure depth 3)."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=2)
    rungs = []
    patch_chain(mp, rungs.append)
    B = default_store(mp, ns=NS, client=aborting_chain_client(2))
    B.run(mid_chain_arm_body(damper, 'batch_merge_commit', arm_on=1), operation='batch_merge_commit')
    assert rungs[-1] == pytest.approx(0.825)
    assert clock.sleeps[-1] == pytest.approx(0.3125)
    assert clock.sleeps == [0.15625, 0.3125]


def test_g2_gate_rung2_armdepth3_j0p5_batch_merge_commit(mp):
    """Rung 2 waits out the window a sibling armed mid-chain (failure depth 3)."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=2)
    rungs = []
    patch_chain(mp, rungs.append)
    B = default_store(mp, ns=NS, client=aborting_chain_client(2))
    B.run(mid_chain_arm_body(damper, 'batch_merge_commit', arm_on=1), operation='batch_merge_commit')
    assert rungs[-1] == pytest.approx(0.95)
    assert clock.sleeps[-1] == pytest.approx(0.375)
    assert clock.sleeps == [0.1875, 0.375]


def test_g2_gate_rung2_armdepth3_j1p0_batch_merge_commit(mp):
    """Rung 2 waits out the window a sibling armed mid-chain (failure depth 3)."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=2)
    rungs = []
    patch_chain(mp, rungs.append)
    B = default_store(mp, ns=NS, client=aborting_chain_client(2))
    B.run(mid_chain_arm_body(damper, 'batch_merge_commit', arm_on=1), operation='batch_merge_commit')
    assert rungs[-1] == pytest.approx(1.2)
    assert clock.sleeps[-1] == pytest.approx(0.5)
    assert clock.sleeps == [0.25, 0.5]


def test_g2_gate_rung2_armdepth4_j0p0_batch_merge_commit(mp):
    """Rung 2 waits out the window a sibling armed mid-chain (failure depth 4)."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=3)
    rungs = []
    patch_chain(mp, rungs.append)
    B = default_store(mp, ns=NS, client=aborting_chain_client(2))
    B.run(mid_chain_arm_body(damper, 'batch_merge_commit', arm_on=1), operation='batch_merge_commit')
    assert rungs[-1] == pytest.approx(1.2)
    assert clock.sleeps[-1] == pytest.approx(0.5)
    assert clock.sleeps == [0.125, 0.25, 0.5]


def test_g2_gate_rung2_armdepth4_j0p25_batch_merge_commit(mp):
    """Rung 2 waits out the window a sibling armed mid-chain (failure depth 4)."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=3)
    rungs = []
    patch_chain(mp, rungs.append)
    B = default_store(mp, ns=NS, client=aborting_chain_client(2))
    B.run(mid_chain_arm_body(damper, 'batch_merge_commit', arm_on=1), operation='batch_merge_commit')
    assert rungs[-1] == pytest.approx(1.45)
    assert clock.sleeps[-1] == pytest.approx(0.625)
    assert clock.sleeps == [0.15625, 0.3125, 0.625]


def test_g2_gate_rung2_armdepth4_j0p5_batch_merge_commit(mp):
    """Rung 2 waits out the window a sibling armed mid-chain (failure depth 4)."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=3)
    rungs = []
    patch_chain(mp, rungs.append)
    B = default_store(mp, ns=NS, client=aborting_chain_client(2))
    B.run(mid_chain_arm_body(damper, 'batch_merge_commit', arm_on=1), operation='batch_merge_commit')
    assert rungs[-1] == pytest.approx(1.7)
    assert clock.sleeps[-1] == pytest.approx(0.75)
    assert clock.sleeps == [0.1875, 0.375, 0.75]


def test_g2_gate_rung2_armdepth4_j1p0_batch_merge_commit(mp):
    """Rung 2 waits out the window a sibling armed mid-chain (failure depth 4)."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=3)
    rungs = []
    patch_chain(mp, rungs.append)
    B = default_store(mp, ns=NS, client=aborting_chain_client(2))
    B.run(mid_chain_arm_body(damper, 'batch_merge_commit', arm_on=1), operation='batch_merge_commit')
    assert rungs[-1] == pytest.approx(2.2)
    assert clock.sleeps[-1] == pytest.approx(1.0)
    assert clock.sleeps == [0.25, 0.5, 1.0]


def test_g2_gate_rung2_armdepth5_j0p0_batch_merge_commit(mp):
    """Rung 2 waits out the window a sibling armed mid-chain (failure depth 5)."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=4)
    rungs = []
    patch_chain(mp, rungs.append)
    B = default_store(mp, ns=NS, client=aborting_chain_client(2))
    B.run(mid_chain_arm_body(damper, 'batch_merge_commit', arm_on=1), operation='batch_merge_commit')
    assert rungs[-1] == pytest.approx(2.2)
    assert clock.sleeps[-1] == pytest.approx(1.0)
    assert clock.sleeps == [0.125, 0.25, 0.5, 1.0]


def test_g2_gate_rung2_armdepth5_j0p25_batch_merge_commit(mp):
    """Rung 2 waits out the window a sibling armed mid-chain (failure depth 5)."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=4)
    rungs = []
    patch_chain(mp, rungs.append)
    B = default_store(mp, ns=NS, client=aborting_chain_client(2))
    B.run(mid_chain_arm_body(damper, 'batch_merge_commit', arm_on=1), operation='batch_merge_commit')
    assert rungs[-1] == pytest.approx(2.7)
    assert clock.sleeps[-1] == pytest.approx(1.25)
    assert clock.sleeps == [0.15625, 0.3125, 0.625, 1.25]


def test_g2_gate_rung2_armdepth5_j0p5_batch_merge_commit(mp):
    """Rung 2 waits out the window a sibling armed mid-chain (failure depth 5)."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=4)
    rungs = []
    patch_chain(mp, rungs.append)
    B = default_store(mp, ns=NS, client=aborting_chain_client(2))
    B.run(mid_chain_arm_body(damper, 'batch_merge_commit', arm_on=1), operation='batch_merge_commit')
    assert rungs[-1] == pytest.approx(3.2)
    assert clock.sleeps[-1] == pytest.approx(1.5)
    assert clock.sleeps == [0.1875, 0.375, 0.75, 1.5]


def test_g2_gate_rung2_armdepth5_j1p0_batch_merge_commit(mp):
    """Rung 2 waits out the window a sibling armed mid-chain (failure depth 5)."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=4)
    rungs = []
    patch_chain(mp, rungs.append)
    B = default_store(mp, ns=NS, client=aborting_chain_client(2))
    B.run(mid_chain_arm_body(damper, 'batch_merge_commit', arm_on=1), operation='batch_merge_commit')
    assert rungs[-1] == pytest.approx(4.2)
    assert clock.sleeps[-1] == pytest.approx(2.0)
    assert clock.sleeps == [0.25, 0.5, 1.0, 2.0]


def test_g2_gate_rung2_armdepth6_j0p0_batch_merge_commit(mp):
    """Rung 2 waits out the window a sibling armed mid-chain (failure depth 6)."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=5)
    rungs = []
    patch_chain(mp, rungs.append)
    B = default_store(mp, ns=NS, client=aborting_chain_client(2))
    B.run(mid_chain_arm_body(damper, 'batch_merge_commit', arm_on=1), operation='batch_merge_commit')
    assert rungs[-1] == pytest.approx(2.2)
    assert clock.sleeps[-1] == pytest.approx(2.0)
    assert clock.sleeps == [0.125, 0.25, 0.5, 1.0, 2.0]


def test_g2_gate_rung2_armdepth6_j0p25_batch_merge_commit(mp):
    """Rung 2 waits out the window a sibling armed mid-chain (failure depth 6)."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=5)
    rungs = []
    patch_chain(mp, rungs.append)
    B = default_store(mp, ns=NS, client=aborting_chain_client(2))
    B.run(mid_chain_arm_body(damper, 'batch_merge_commit', arm_on=1), operation='batch_merge_commit')
    assert rungs[-1] == pytest.approx(2.7)
    assert clock.sleeps[-1] == pytest.approx(2.5)
    assert clock.sleeps == [0.15625, 0.3125, 0.625, 1.25, 2.5]


def test_g2_gate_rung2_armdepth6_j0p5_batch_merge_commit(mp):
    """Rung 2 waits out the window a sibling armed mid-chain (failure depth 6)."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=5)
    rungs = []
    patch_chain(mp, rungs.append)
    B = default_store(mp, ns=NS, client=aborting_chain_client(2))
    B.run(mid_chain_arm_body(damper, 'batch_merge_commit', arm_on=1), operation='batch_merge_commit')
    assert rungs[-1] == pytest.approx(3.2)
    assert clock.sleeps[-1] == pytest.approx(3.0)
    assert clock.sleeps == [0.1875, 0.375, 0.75, 1.5, 3.0]


def test_g2_gate_rung2_armdepth6_j1p0_batch_merge_commit(mp):
    """Rung 2 waits out the window a sibling armed mid-chain (failure depth 6)."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=5)
    rungs = []
    patch_chain(mp, rungs.append)
    B = default_store(mp, ns=NS, client=aborting_chain_client(2))
    B.run(mid_chain_arm_body(damper, 'batch_merge_commit', arm_on=1), operation='batch_merge_commit')
    assert rungs[-1] == pytest.approx(4.2)
    assert clock.sleeps[-1] == pytest.approx(4.0)
    assert clock.sleeps == [0.25, 0.5, 1.0, 2.0, 4.0]


def test_g2_gate_rung3_armdepth2_j0p0_batch_merge_commit(mp):
    """Rung 3 waits out the window a sibling armed mid-chain (failure depth 2)."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=1)
    rungs = []
    patch_chain(mp, rungs.append)
    B = default_store(mp, ns=NS, client=aborting_chain_client(3))
    B.run(mid_chain_arm_body(damper, 'batch_merge_commit', arm_on=1), operation='batch_merge_commit')
    assert rungs[-1] == pytest.approx(0.9)
    assert clock.sleeps[-1] == pytest.approx(0.125)
    assert clock.sleeps == [0.125]


def test_g2_gate_rung3_armdepth2_j0p25_batch_merge_commit(mp):
    """Rung 3 waits out the window a sibling armed mid-chain (failure depth 2)."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=1)
    rungs = []
    patch_chain(mp, rungs.append)
    B = default_store(mp, ns=NS, client=aborting_chain_client(3))
    B.run(mid_chain_arm_body(damper, 'batch_merge_commit', arm_on=1), operation='batch_merge_commit')
    assert rungs[-1] == pytest.approx(1.025)
    assert clock.sleeps[-1] == pytest.approx(0.15625)
    assert clock.sleeps == [0.15625]


def test_g2_gate_rung3_armdepth2_j0p5_batch_merge_commit(mp):
    """Rung 3 waits out the window a sibling armed mid-chain (failure depth 2)."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=1)
    rungs = []
    patch_chain(mp, rungs.append)
    B = default_store(mp, ns=NS, client=aborting_chain_client(3))
    B.run(mid_chain_arm_body(damper, 'batch_merge_commit', arm_on=1), operation='batch_merge_commit')
    assert rungs[-1] == pytest.approx(1.15)
    assert clock.sleeps[-1] == pytest.approx(0.1875)
    assert clock.sleeps == [0.1875]


def test_g2_gate_rung3_armdepth2_j1p0_batch_merge_commit(mp):
    """Rung 3 waits out the window a sibling armed mid-chain (failure depth 2)."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=1)
    rungs = []
    patch_chain(mp, rungs.append)
    B = default_store(mp, ns=NS, client=aborting_chain_client(3))
    B.run(mid_chain_arm_body(damper, 'batch_merge_commit', arm_on=1), operation='batch_merge_commit')
    assert rungs[-1] == pytest.approx(1.4)
    assert clock.sleeps[-1] == pytest.approx(0.25)
    assert clock.sleeps == [0.25]


def test_g2_gate_rung3_armdepth3_j0p0_batch_merge_commit(mp):
    """Rung 3 waits out the window a sibling armed mid-chain (failure depth 3)."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=2)
    rungs = []
    patch_chain(mp, rungs.append)
    B = default_store(mp, ns=NS, client=aborting_chain_client(3))
    B.run(mid_chain_arm_body(damper, 'batch_merge_commit', arm_on=1), operation='batch_merge_commit')
    assert rungs[-1] == pytest.approx(0.9)
    assert clock.sleeps[-1] == pytest.approx(0.25)
    assert clock.sleeps == [0.125, 0.25]


def test_g2_gate_rung3_armdepth3_j0p25_batch_merge_commit(mp):
    """Rung 3 waits out the window a sibling armed mid-chain (failure depth 3)."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=2)
    rungs = []
    patch_chain(mp, rungs.append)
    B = default_store(mp, ns=NS, client=aborting_chain_client(3))
    B.run(mid_chain_arm_body(damper, 'batch_merge_commit', arm_on=1), operation='batch_merge_commit')
    assert rungs[-1] == pytest.approx(1.025)
    assert clock.sleeps[-1] == pytest.approx(0.3125)
    assert clock.sleeps == [0.15625, 0.3125]


def test_g2_gate_rung3_armdepth3_j0p5_batch_merge_commit(mp):
    """Rung 3 waits out the window a sibling armed mid-chain (failure depth 3)."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=2)
    rungs = []
    patch_chain(mp, rungs.append)
    B = default_store(mp, ns=NS, client=aborting_chain_client(3))
    B.run(mid_chain_arm_body(damper, 'batch_merge_commit', arm_on=1), operation='batch_merge_commit')
    assert rungs[-1] == pytest.approx(1.15)
    assert clock.sleeps[-1] == pytest.approx(0.375)
    assert clock.sleeps == [0.1875, 0.375]


def test_g2_gate_rung3_armdepth3_j1p0_batch_merge_commit(mp):
    """Rung 3 waits out the window a sibling armed mid-chain (failure depth 3)."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=2)
    rungs = []
    patch_chain(mp, rungs.append)
    B = default_store(mp, ns=NS, client=aborting_chain_client(3))
    B.run(mid_chain_arm_body(damper, 'batch_merge_commit', arm_on=1), operation='batch_merge_commit')
    assert rungs[-1] == pytest.approx(1.4)
    assert clock.sleeps[-1] == pytest.approx(0.5)
    assert clock.sleeps == [0.25, 0.5]


def test_g2_gate_rung3_armdepth4_j0p0_batch_merge_commit(mp):
    """Rung 3 waits out the window a sibling armed mid-chain (failure depth 4)."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=3)
    rungs = []
    patch_chain(mp, rungs.append)
    B = default_store(mp, ns=NS, client=aborting_chain_client(3))
    B.run(mid_chain_arm_body(damper, 'batch_merge_commit', arm_on=1), operation='batch_merge_commit')
    assert rungs[-1] == pytest.approx(1.4)
    assert clock.sleeps[-1] == pytest.approx(0.5)
    assert clock.sleeps == [0.125, 0.25, 0.5]


def test_g2_gate_rung3_armdepth4_j0p25_batch_merge_commit(mp):
    """Rung 3 waits out the window a sibling armed mid-chain (failure depth 4)."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=3)
    rungs = []
    patch_chain(mp, rungs.append)
    B = default_store(mp, ns=NS, client=aborting_chain_client(3))
    B.run(mid_chain_arm_body(damper, 'batch_merge_commit', arm_on=1), operation='batch_merge_commit')
    assert rungs[-1] == pytest.approx(1.65)
    assert clock.sleeps[-1] == pytest.approx(0.625)
    assert clock.sleeps == [0.15625, 0.3125, 0.625]


def test_g2_gate_rung3_armdepth4_j0p5_batch_merge_commit(mp):
    """Rung 3 waits out the window a sibling armed mid-chain (failure depth 4)."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=3)
    rungs = []
    patch_chain(mp, rungs.append)
    B = default_store(mp, ns=NS, client=aborting_chain_client(3))
    B.run(mid_chain_arm_body(damper, 'batch_merge_commit', arm_on=1), operation='batch_merge_commit')
    assert rungs[-1] == pytest.approx(1.9)
    assert clock.sleeps[-1] == pytest.approx(0.75)
    assert clock.sleeps == [0.1875, 0.375, 0.75]


def test_g2_gate_rung3_armdepth4_j1p0_batch_merge_commit(mp):
    """Rung 3 waits out the window a sibling armed mid-chain (failure depth 4)."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=3)
    rungs = []
    patch_chain(mp, rungs.append)
    B = default_store(mp, ns=NS, client=aborting_chain_client(3))
    B.run(mid_chain_arm_body(damper, 'batch_merge_commit', arm_on=1), operation='batch_merge_commit')
    assert rungs[-1] == pytest.approx(2.4)
    assert clock.sleeps[-1] == pytest.approx(1.0)
    assert clock.sleeps == [0.25, 0.5, 1.0]


def test_g2_gate_rung3_armdepth5_j0p0_batch_merge_commit(mp):
    """Rung 3 waits out the window a sibling armed mid-chain (failure depth 5)."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=4)
    rungs = []
    patch_chain(mp, rungs.append)
    B = default_store(mp, ns=NS, client=aborting_chain_client(3))
    B.run(mid_chain_arm_body(damper, 'batch_merge_commit', arm_on=1), operation='batch_merge_commit')
    assert rungs[-1] == pytest.approx(2.4)
    assert clock.sleeps[-1] == pytest.approx(1.0)
    assert clock.sleeps == [0.125, 0.25, 0.5, 1.0]


def test_g2_gate_rung3_armdepth5_j0p25_batch_merge_commit(mp):
    """Rung 3 waits out the window a sibling armed mid-chain (failure depth 5)."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=4)
    rungs = []
    patch_chain(mp, rungs.append)
    B = default_store(mp, ns=NS, client=aborting_chain_client(3))
    B.run(mid_chain_arm_body(damper, 'batch_merge_commit', arm_on=1), operation='batch_merge_commit')
    assert rungs[-1] == pytest.approx(2.9)
    assert clock.sleeps[-1] == pytest.approx(1.25)
    assert clock.sleeps == [0.15625, 0.3125, 0.625, 1.25]


def test_g2_gate_rung3_armdepth5_j0p5_batch_merge_commit(mp):
    """Rung 3 waits out the window a sibling armed mid-chain (failure depth 5)."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=4)
    rungs = []
    patch_chain(mp, rungs.append)
    B = default_store(mp, ns=NS, client=aborting_chain_client(3))
    B.run(mid_chain_arm_body(damper, 'batch_merge_commit', arm_on=1), operation='batch_merge_commit')
    assert rungs[-1] == pytest.approx(3.4)
    assert clock.sleeps[-1] == pytest.approx(1.5)
    assert clock.sleeps == [0.1875, 0.375, 0.75, 1.5]


def test_g2_gate_rung3_armdepth5_j1p0_batch_merge_commit(mp):
    """Rung 3 waits out the window a sibling armed mid-chain (failure depth 5)."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=4)
    rungs = []
    patch_chain(mp, rungs.append)
    B = default_store(mp, ns=NS, client=aborting_chain_client(3))
    B.run(mid_chain_arm_body(damper, 'batch_merge_commit', arm_on=1), operation='batch_merge_commit')
    assert rungs[-1] == pytest.approx(4.4)
    assert clock.sleeps[-1] == pytest.approx(2.0)
    assert clock.sleeps == [0.25, 0.5, 1.0, 2.0]


def test_g2_gate_rung3_armdepth6_j0p0_batch_merge_commit(mp):
    """Rung 3 waits out the window a sibling armed mid-chain (failure depth 6)."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=5)
    rungs = []
    patch_chain(mp, rungs.append)
    B = default_store(mp, ns=NS, client=aborting_chain_client(3))
    B.run(mid_chain_arm_body(damper, 'batch_merge_commit', arm_on=1), operation='batch_merge_commit')
    assert rungs[-1] == pytest.approx(2.4)
    assert clock.sleeps[-1] == pytest.approx(2.0)
    assert clock.sleeps == [0.125, 0.25, 0.5, 1.0, 2.0]


def test_g2_gate_rung3_armdepth6_j0p25_batch_merge_commit(mp):
    """Rung 3 waits out the window a sibling armed mid-chain (failure depth 6)."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=5)
    rungs = []
    patch_chain(mp, rungs.append)
    B = default_store(mp, ns=NS, client=aborting_chain_client(3))
    B.run(mid_chain_arm_body(damper, 'batch_merge_commit', arm_on=1), operation='batch_merge_commit')
    assert rungs[-1] == pytest.approx(2.9)
    assert clock.sleeps[-1] == pytest.approx(2.5)
    assert clock.sleeps == [0.15625, 0.3125, 0.625, 1.25, 2.5]


def test_g2_gate_rung3_armdepth6_j0p5_batch_merge_commit(mp):
    """Rung 3 waits out the window a sibling armed mid-chain (failure depth 6)."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=5)
    rungs = []
    patch_chain(mp, rungs.append)
    B = default_store(mp, ns=NS, client=aborting_chain_client(3))
    B.run(mid_chain_arm_body(damper, 'batch_merge_commit', arm_on=1), operation='batch_merge_commit')
    assert rungs[-1] == pytest.approx(3.4)
    assert clock.sleeps[-1] == pytest.approx(3.0)
    assert clock.sleeps == [0.1875, 0.375, 0.75, 1.5, 3.0]


def test_g2_gate_rung3_armdepth6_j1p0_batch_merge_commit(mp):
    """Rung 3 waits out the window a sibling armed mid-chain (failure depth 6)."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=5)
    rungs = []
    patch_chain(mp, rungs.append)
    B = default_store(mp, ns=NS, client=aborting_chain_client(3))
    B.run(mid_chain_arm_body(damper, 'batch_merge_commit', arm_on=1), operation='batch_merge_commit')
    assert rungs[-1] == pytest.approx(4.4)
    assert clock.sleeps[-1] == pytest.approx(4.0)
    assert clock.sleeps == [0.25, 0.5, 1.0, 2.0, 4.0]


def test_g2_gate_rung4_armdepth2_j0p0_batch_merge_commit(mp):
    """Rung 4 waits out the window a sibling armed mid-chain (failure depth 2)."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=1)
    rungs = []
    patch_chain(mp, rungs.append)
    B = default_store(mp, ns=NS, client=aborting_chain_client(4))
    B.run(mid_chain_arm_body(damper, 'batch_merge_commit', arm_on=1), operation='batch_merge_commit')
    assert rungs[-1] == pytest.approx(1.8)
    assert clock.sleeps[-1] == pytest.approx(0.125)
    assert clock.sleeps == [0.125]


def test_g2_gate_rung4_armdepth2_j0p25_batch_merge_commit(mp):
    """Rung 4 waits out the window a sibling armed mid-chain (failure depth 2)."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=1)
    rungs = []
    patch_chain(mp, rungs.append)
    B = default_store(mp, ns=NS, client=aborting_chain_client(4))
    B.run(mid_chain_arm_body(damper, 'batch_merge_commit', arm_on=1), operation='batch_merge_commit')
    assert rungs[-1] == pytest.approx(2.05)
    assert clock.sleeps[-1] == pytest.approx(0.15625)
    assert clock.sleeps == [0.15625]


def test_g2_gate_rung4_armdepth2_j0p5_batch_merge_commit(mp):
    """Rung 4 waits out the window a sibling armed mid-chain (failure depth 2)."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=1)
    rungs = []
    patch_chain(mp, rungs.append)
    B = default_store(mp, ns=NS, client=aborting_chain_client(4))
    B.run(mid_chain_arm_body(damper, 'batch_merge_commit', arm_on=1), operation='batch_merge_commit')
    assert rungs[-1] == pytest.approx(2.3)
    assert clock.sleeps[-1] == pytest.approx(0.1875)
    assert clock.sleeps == [0.1875]


def test_g2_gate_rung4_armdepth2_j1p0_batch_merge_commit(mp):
    """Rung 4 waits out the window a sibling armed mid-chain (failure depth 2)."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=1)
    rungs = []
    patch_chain(mp, rungs.append)
    B = default_store(mp, ns=NS, client=aborting_chain_client(4))
    B.run(mid_chain_arm_body(damper, 'batch_merge_commit', arm_on=1), operation='batch_merge_commit')
    assert rungs[-1] == pytest.approx(2.8)
    assert clock.sleeps[-1] == pytest.approx(0.25)
    assert clock.sleeps == [0.25]


def test_g2_gate_rung4_armdepth3_j0p0_batch_merge_commit(mp):
    """Rung 4 waits out the window a sibling armed mid-chain (failure depth 3)."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=2)
    rungs = []
    patch_chain(mp, rungs.append)
    B = default_store(mp, ns=NS, client=aborting_chain_client(4))
    B.run(mid_chain_arm_body(damper, 'batch_merge_commit', arm_on=1), operation='batch_merge_commit')
    assert rungs[-1] == pytest.approx(1.8)
    assert clock.sleeps[-1] == pytest.approx(0.25)
    assert clock.sleeps == [0.125, 0.25]


def test_g2_gate_rung4_armdepth3_j0p25_batch_merge_commit(mp):
    """Rung 4 waits out the window a sibling armed mid-chain (failure depth 3)."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=2)
    rungs = []
    patch_chain(mp, rungs.append)
    B = default_store(mp, ns=NS, client=aborting_chain_client(4))
    B.run(mid_chain_arm_body(damper, 'batch_merge_commit', arm_on=1), operation='batch_merge_commit')
    assert rungs[-1] == pytest.approx(2.05)
    assert clock.sleeps[-1] == pytest.approx(0.3125)
    assert clock.sleeps == [0.15625, 0.3125]


def test_g2_gate_rung4_armdepth3_j0p5_batch_merge_commit(mp):
    """Rung 4 waits out the window a sibling armed mid-chain (failure depth 3)."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=2)
    rungs = []
    patch_chain(mp, rungs.append)
    B = default_store(mp, ns=NS, client=aborting_chain_client(4))
    B.run(mid_chain_arm_body(damper, 'batch_merge_commit', arm_on=1), operation='batch_merge_commit')
    assert rungs[-1] == pytest.approx(2.3)
    assert clock.sleeps[-1] == pytest.approx(0.375)
    assert clock.sleeps == [0.1875, 0.375]


def test_g2_gate_rung4_armdepth3_j1p0_batch_merge_commit(mp):
    """Rung 4 waits out the window a sibling armed mid-chain (failure depth 3)."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=2)
    rungs = []
    patch_chain(mp, rungs.append)
    B = default_store(mp, ns=NS, client=aborting_chain_client(4))
    B.run(mid_chain_arm_body(damper, 'batch_merge_commit', arm_on=1), operation='batch_merge_commit')
    assert rungs[-1] == pytest.approx(2.8)
    assert clock.sleeps[-1] == pytest.approx(0.5)
    assert clock.sleeps == [0.25, 0.5]


def test_g2_gate_rung4_armdepth4_j0p0_batch_merge_commit(mp):
    """Rung 4 waits out the window a sibling armed mid-chain (failure depth 4)."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=3)
    rungs = []
    patch_chain(mp, rungs.append)
    B = default_store(mp, ns=NS, client=aborting_chain_client(4))
    B.run(mid_chain_arm_body(damper, 'batch_merge_commit', arm_on=1), operation='batch_merge_commit')
    assert rungs[-1] == pytest.approx(1.8)
    assert clock.sleeps[-1] == pytest.approx(0.5)
    assert clock.sleeps == [0.125, 0.25, 0.5]


def test_g2_gate_rung4_armdepth4_j0p25_batch_merge_commit(mp):
    """Rung 4 waits out the window a sibling armed mid-chain (failure depth 4)."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=3)
    rungs = []
    patch_chain(mp, rungs.append)
    B = default_store(mp, ns=NS, client=aborting_chain_client(4))
    B.run(mid_chain_arm_body(damper, 'batch_merge_commit', arm_on=1), operation='batch_merge_commit')
    assert rungs[-1] == pytest.approx(2.05)
    assert clock.sleeps[-1] == pytest.approx(0.625)
    assert clock.sleeps == [0.15625, 0.3125, 0.625]


def test_g2_gate_rung4_armdepth4_j0p5_batch_merge_commit(mp):
    """Rung 4 waits out the window a sibling armed mid-chain (failure depth 4)."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=3)
    rungs = []
    patch_chain(mp, rungs.append)
    B = default_store(mp, ns=NS, client=aborting_chain_client(4))
    B.run(mid_chain_arm_body(damper, 'batch_merge_commit', arm_on=1), operation='batch_merge_commit')
    assert rungs[-1] == pytest.approx(2.3)
    assert clock.sleeps[-1] == pytest.approx(0.75)
    assert clock.sleeps == [0.1875, 0.375, 0.75]


def test_g2_gate_rung4_armdepth4_j1p0_batch_merge_commit(mp):
    """Rung 4 waits out the window a sibling armed mid-chain (failure depth 4)."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=3)
    rungs = []
    patch_chain(mp, rungs.append)
    B = default_store(mp, ns=NS, client=aborting_chain_client(4))
    B.run(mid_chain_arm_body(damper, 'batch_merge_commit', arm_on=1), operation='batch_merge_commit')
    assert rungs[-1] == pytest.approx(2.8)
    assert clock.sleeps[-1] == pytest.approx(1.0)
    assert clock.sleeps == [0.25, 0.5, 1.0]


def test_g2_gate_rung4_armdepth5_j0p0_batch_merge_commit(mp):
    """Rung 4 waits out the window a sibling armed mid-chain (failure depth 5)."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=4)
    rungs = []
    patch_chain(mp, rungs.append)
    B = default_store(mp, ns=NS, client=aborting_chain_client(4))
    B.run(mid_chain_arm_body(damper, 'batch_merge_commit', arm_on=1), operation='batch_merge_commit')
    assert rungs[-1] == pytest.approx(2.8)
    assert clock.sleeps[-1] == pytest.approx(1.0)
    assert clock.sleeps == [0.125, 0.25, 0.5, 1.0]


def test_g2_gate_rung4_armdepth5_j0p25_batch_merge_commit(mp):
    """Rung 4 waits out the window a sibling armed mid-chain (failure depth 5)."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=4)
    rungs = []
    patch_chain(mp, rungs.append)
    B = default_store(mp, ns=NS, client=aborting_chain_client(4))
    B.run(mid_chain_arm_body(damper, 'batch_merge_commit', arm_on=1), operation='batch_merge_commit')
    assert rungs[-1] == pytest.approx(3.3)
    assert clock.sleeps[-1] == pytest.approx(1.25)
    assert clock.sleeps == [0.15625, 0.3125, 0.625, 1.25]


def test_g2_gate_rung4_armdepth5_j0p5_batch_merge_commit(mp):
    """Rung 4 waits out the window a sibling armed mid-chain (failure depth 5)."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=4)
    rungs = []
    patch_chain(mp, rungs.append)
    B = default_store(mp, ns=NS, client=aborting_chain_client(4))
    B.run(mid_chain_arm_body(damper, 'batch_merge_commit', arm_on=1), operation='batch_merge_commit')
    assert rungs[-1] == pytest.approx(3.8)
    assert clock.sleeps[-1] == pytest.approx(1.5)
    assert clock.sleeps == [0.1875, 0.375, 0.75, 1.5]


def test_g2_gate_rung4_armdepth5_j1p0_batch_merge_commit(mp):
    """Rung 4 waits out the window a sibling armed mid-chain (failure depth 5)."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=4)
    rungs = []
    patch_chain(mp, rungs.append)
    B = default_store(mp, ns=NS, client=aborting_chain_client(4))
    B.run(mid_chain_arm_body(damper, 'batch_merge_commit', arm_on=1), operation='batch_merge_commit')
    assert rungs[-1] == pytest.approx(4.8)
    assert clock.sleeps[-1] == pytest.approx(2.0)
    assert clock.sleeps == [0.25, 0.5, 1.0, 2.0]


def test_g2_gate_rung4_armdepth6_j0p0_batch_merge_commit(mp):
    """Rung 4 waits out the window a sibling armed mid-chain (failure depth 6)."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=5)
    rungs = []
    patch_chain(mp, rungs.append)
    B = default_store(mp, ns=NS, client=aborting_chain_client(4))
    B.run(mid_chain_arm_body(damper, 'batch_merge_commit', arm_on=1), operation='batch_merge_commit')
    assert rungs[-1] == pytest.approx(2.8)
    assert clock.sleeps[-1] == pytest.approx(2.0)
    assert clock.sleeps == [0.125, 0.25, 0.5, 1.0, 2.0]


def test_g2_gate_rung4_armdepth6_j0p25_batch_merge_commit(mp):
    """Rung 4 waits out the window a sibling armed mid-chain (failure depth 6)."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=5)
    rungs = []
    patch_chain(mp, rungs.append)
    B = default_store(mp, ns=NS, client=aborting_chain_client(4))
    B.run(mid_chain_arm_body(damper, 'batch_merge_commit', arm_on=1), operation='batch_merge_commit')
    assert rungs[-1] == pytest.approx(3.3)
    assert clock.sleeps[-1] == pytest.approx(2.5)
    assert clock.sleeps == [0.15625, 0.3125, 0.625, 1.25, 2.5]


def test_g2_gate_rung4_armdepth6_j0p5_batch_merge_commit(mp):
    """Rung 4 waits out the window a sibling armed mid-chain (failure depth 6)."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=5)
    rungs = []
    patch_chain(mp, rungs.append)
    B = default_store(mp, ns=NS, client=aborting_chain_client(4))
    B.run(mid_chain_arm_body(damper, 'batch_merge_commit', arm_on=1), operation='batch_merge_commit')
    assert rungs[-1] == pytest.approx(3.8)
    assert clock.sleeps[-1] == pytest.approx(3.0)
    assert clock.sleeps == [0.1875, 0.375, 0.75, 1.5, 3.0]


def test_g2_gate_rung4_armdepth6_j1p0_batch_merge_commit(mp):
    """Rung 4 waits out the window a sibling armed mid-chain (failure depth 6)."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=5)
    rungs = []
    patch_chain(mp, rungs.append)
    B = default_store(mp, ns=NS, client=aborting_chain_client(4))
    B.run(mid_chain_arm_body(damper, 'batch_merge_commit', arm_on=1), operation='batch_merge_commit')
    assert rungs[-1] == pytest.approx(4.8)
    assert clock.sleeps[-1] == pytest.approx(4.0)
    assert clock.sleeps == [0.25, 0.5, 1.0, 2.0, 4.0]


def test_g2_gate_rung2_armdepth2_j0p0_batch_provider_stt(mp):
    """Rung 2 waits out the window a sibling armed mid-chain (failure depth 2)."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=1)
    rungs = []
    patch_chain(mp, rungs.append)
    B = default_store(mp, ns=NS, client=aborting_chain_client(2))
    B.run(mid_chain_arm_body(damper, 'batch_provider_stt', arm_on=1), operation='batch_provider_stt')
    assert rungs[-1] == pytest.approx(0.45)
    assert clock.sleeps[-1] == pytest.approx(0.125)
    assert clock.sleeps == [0.125]


def test_g2_gate_rung2_armdepth2_j0p25_batch_provider_stt(mp):
    """Rung 2 waits out the window a sibling armed mid-chain (failure depth 2)."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=1)
    rungs = []
    patch_chain(mp, rungs.append)
    B = default_store(mp, ns=NS, client=aborting_chain_client(2))
    B.run(mid_chain_arm_body(damper, 'batch_provider_stt', arm_on=1), operation='batch_provider_stt')
    assert rungs[-1] == pytest.approx(0.5125)
    assert clock.sleeps[-1] == pytest.approx(0.15625)
    assert clock.sleeps == [0.15625]


def test_g2_gate_rung2_armdepth2_j0p5_batch_provider_stt(mp):
    """Rung 2 waits out the window a sibling armed mid-chain (failure depth 2)."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=1)
    rungs = []
    patch_chain(mp, rungs.append)
    B = default_store(mp, ns=NS, client=aborting_chain_client(2))
    B.run(mid_chain_arm_body(damper, 'batch_provider_stt', arm_on=1), operation='batch_provider_stt')
    assert rungs[-1] == pytest.approx(0.575)
    assert clock.sleeps[-1] == pytest.approx(0.1875)
    assert clock.sleeps == [0.1875]


def test_g2_gate_rung2_armdepth2_j1p0_batch_provider_stt(mp):
    """Rung 2 waits out the window a sibling armed mid-chain (failure depth 2)."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=1)
    rungs = []
    patch_chain(mp, rungs.append)
    B = default_store(mp, ns=NS, client=aborting_chain_client(2))
    B.run(mid_chain_arm_body(damper, 'batch_provider_stt', arm_on=1), operation='batch_provider_stt')
    assert rungs[-1] == pytest.approx(0.7)
    assert clock.sleeps[-1] == pytest.approx(0.25)
    assert clock.sleeps == [0.25]


def test_g2_gate_rung2_armdepth3_j0p0_batch_provider_stt(mp):
    """Rung 2 waits out the window a sibling armed mid-chain (failure depth 3)."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=2)
    rungs = []
    patch_chain(mp, rungs.append)
    B = default_store(mp, ns=NS, client=aborting_chain_client(2))
    B.run(mid_chain_arm_body(damper, 'batch_provider_stt', arm_on=1), operation='batch_provider_stt')
    assert rungs[-1] == pytest.approx(0.7)
    assert clock.sleeps[-1] == pytest.approx(0.25)
    assert clock.sleeps == [0.125, 0.25]


def test_g2_gate_rung2_armdepth3_j0p25_batch_provider_stt(mp):
    """Rung 2 waits out the window a sibling armed mid-chain (failure depth 3)."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=2)
    rungs = []
    patch_chain(mp, rungs.append)
    B = default_store(mp, ns=NS, client=aborting_chain_client(2))
    B.run(mid_chain_arm_body(damper, 'batch_provider_stt', arm_on=1), operation='batch_provider_stt')
    assert rungs[-1] == pytest.approx(0.825)
    assert clock.sleeps[-1] == pytest.approx(0.3125)
    assert clock.sleeps == [0.15625, 0.3125]


def test_g2_gate_rung2_armdepth3_j0p5_batch_provider_stt(mp):
    """Rung 2 waits out the window a sibling armed mid-chain (failure depth 3)."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=2)
    rungs = []
    patch_chain(mp, rungs.append)
    B = default_store(mp, ns=NS, client=aborting_chain_client(2))
    B.run(mid_chain_arm_body(damper, 'batch_provider_stt', arm_on=1), operation='batch_provider_stt')
    assert rungs[-1] == pytest.approx(0.95)
    assert clock.sleeps[-1] == pytest.approx(0.375)
    assert clock.sleeps == [0.1875, 0.375]


def test_g2_gate_rung2_armdepth3_j1p0_batch_provider_stt(mp):
    """Rung 2 waits out the window a sibling armed mid-chain (failure depth 3)."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=2)
    rungs = []
    patch_chain(mp, rungs.append)
    B = default_store(mp, ns=NS, client=aborting_chain_client(2))
    B.run(mid_chain_arm_body(damper, 'batch_provider_stt', arm_on=1), operation='batch_provider_stt')
    assert rungs[-1] == pytest.approx(1.2)
    assert clock.sleeps[-1] == pytest.approx(0.5)
    assert clock.sleeps == [0.25, 0.5]


def test_g2_gate_rung2_armdepth4_j0p0_batch_provider_stt(mp):
    """Rung 2 waits out the window a sibling armed mid-chain (failure depth 4)."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=3)
    rungs = []
    patch_chain(mp, rungs.append)
    B = default_store(mp, ns=NS, client=aborting_chain_client(2))
    B.run(mid_chain_arm_body(damper, 'batch_provider_stt', arm_on=1), operation='batch_provider_stt')
    assert rungs[-1] == pytest.approx(1.2)
    assert clock.sleeps[-1] == pytest.approx(0.5)
    assert clock.sleeps == [0.125, 0.25, 0.5]


def test_g2_gate_rung2_armdepth4_j0p25_batch_provider_stt(mp):
    """Rung 2 waits out the window a sibling armed mid-chain (failure depth 4)."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=3)
    rungs = []
    patch_chain(mp, rungs.append)
    B = default_store(mp, ns=NS, client=aborting_chain_client(2))
    B.run(mid_chain_arm_body(damper, 'batch_provider_stt', arm_on=1), operation='batch_provider_stt')
    assert rungs[-1] == pytest.approx(1.45)
    assert clock.sleeps[-1] == pytest.approx(0.625)
    assert clock.sleeps == [0.15625, 0.3125, 0.625]


def test_g2_gate_rung2_armdepth4_j0p5_batch_provider_stt(mp):
    """Rung 2 waits out the window a sibling armed mid-chain (failure depth 4)."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=3)
    rungs = []
    patch_chain(mp, rungs.append)
    B = default_store(mp, ns=NS, client=aborting_chain_client(2))
    B.run(mid_chain_arm_body(damper, 'batch_provider_stt', arm_on=1), operation='batch_provider_stt')
    assert rungs[-1] == pytest.approx(1.7)
    assert clock.sleeps[-1] == pytest.approx(0.75)
    assert clock.sleeps == [0.1875, 0.375, 0.75]


def test_g2_gate_rung2_armdepth4_j1p0_batch_provider_stt(mp):
    """Rung 2 waits out the window a sibling armed mid-chain (failure depth 4)."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=3)
    rungs = []
    patch_chain(mp, rungs.append)
    B = default_store(mp, ns=NS, client=aborting_chain_client(2))
    B.run(mid_chain_arm_body(damper, 'batch_provider_stt', arm_on=1), operation='batch_provider_stt')
    assert rungs[-1] == pytest.approx(2.2)
    assert clock.sleeps[-1] == pytest.approx(1.0)
    assert clock.sleeps == [0.25, 0.5, 1.0]


def test_g2_gate_rung2_armdepth5_j0p0_batch_provider_stt(mp):
    """Rung 2 waits out the window a sibling armed mid-chain (failure depth 5)."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=4)
    rungs = []
    patch_chain(mp, rungs.append)
    B = default_store(mp, ns=NS, client=aborting_chain_client(2))
    B.run(mid_chain_arm_body(damper, 'batch_provider_stt', arm_on=1), operation='batch_provider_stt')
    assert rungs[-1] == pytest.approx(2.2)
    assert clock.sleeps[-1] == pytest.approx(1.0)
    assert clock.sleeps == [0.125, 0.25, 0.5, 1.0]


def test_g2_gate_rung2_armdepth5_j0p25_batch_provider_stt(mp):
    """Rung 2 waits out the window a sibling armed mid-chain (failure depth 5)."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=4)
    rungs = []
    patch_chain(mp, rungs.append)
    B = default_store(mp, ns=NS, client=aborting_chain_client(2))
    B.run(mid_chain_arm_body(damper, 'batch_provider_stt', arm_on=1), operation='batch_provider_stt')
    assert rungs[-1] == pytest.approx(2.7)
    assert clock.sleeps[-1] == pytest.approx(1.25)
    assert clock.sleeps == [0.15625, 0.3125, 0.625, 1.25]


def test_g2_gate_rung2_armdepth5_j0p5_batch_provider_stt(mp):
    """Rung 2 waits out the window a sibling armed mid-chain (failure depth 5)."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=4)
    rungs = []
    patch_chain(mp, rungs.append)
    B = default_store(mp, ns=NS, client=aborting_chain_client(2))
    B.run(mid_chain_arm_body(damper, 'batch_provider_stt', arm_on=1), operation='batch_provider_stt')
    assert rungs[-1] == pytest.approx(3.2)
    assert clock.sleeps[-1] == pytest.approx(1.5)
    assert clock.sleeps == [0.1875, 0.375, 0.75, 1.5]


def test_g2_gate_rung2_armdepth5_j1p0_batch_provider_stt(mp):
    """Rung 2 waits out the window a sibling armed mid-chain (failure depth 5)."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=4)
    rungs = []
    patch_chain(mp, rungs.append)
    B = default_store(mp, ns=NS, client=aborting_chain_client(2))
    B.run(mid_chain_arm_body(damper, 'batch_provider_stt', arm_on=1), operation='batch_provider_stt')
    assert rungs[-1] == pytest.approx(4.2)
    assert clock.sleeps[-1] == pytest.approx(2.0)
    assert clock.sleeps == [0.25, 0.5, 1.0, 2.0]


def test_g2_gate_rung2_armdepth6_j0p0_batch_provider_stt(mp):
    """Rung 2 waits out the window a sibling armed mid-chain (failure depth 6)."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=5)
    rungs = []
    patch_chain(mp, rungs.append)
    B = default_store(mp, ns=NS, client=aborting_chain_client(2))
    B.run(mid_chain_arm_body(damper, 'batch_provider_stt', arm_on=1), operation='batch_provider_stt')
    assert rungs[-1] == pytest.approx(2.2)
    assert clock.sleeps[-1] == pytest.approx(2.0)
    assert clock.sleeps == [0.125, 0.25, 0.5, 1.0, 2.0]


def test_g2_gate_rung2_armdepth6_j0p25_batch_provider_stt(mp):
    """Rung 2 waits out the window a sibling armed mid-chain (failure depth 6)."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=5)
    rungs = []
    patch_chain(mp, rungs.append)
    B = default_store(mp, ns=NS, client=aborting_chain_client(2))
    B.run(mid_chain_arm_body(damper, 'batch_provider_stt', arm_on=1), operation='batch_provider_stt')
    assert rungs[-1] == pytest.approx(2.7)
    assert clock.sleeps[-1] == pytest.approx(2.5)
    assert clock.sleeps == [0.15625, 0.3125, 0.625, 1.25, 2.5]


def test_g2_gate_rung2_armdepth6_j0p5_batch_provider_stt(mp):
    """Rung 2 waits out the window a sibling armed mid-chain (failure depth 6)."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=5)
    rungs = []
    patch_chain(mp, rungs.append)
    B = default_store(mp, ns=NS, client=aborting_chain_client(2))
    B.run(mid_chain_arm_body(damper, 'batch_provider_stt', arm_on=1), operation='batch_provider_stt')
    assert rungs[-1] == pytest.approx(3.2)
    assert clock.sleeps[-1] == pytest.approx(3.0)
    assert clock.sleeps == [0.1875, 0.375, 0.75, 1.5, 3.0]


def test_g2_gate_rung2_armdepth6_j1p0_batch_provider_stt(mp):
    """Rung 2 waits out the window a sibling armed mid-chain (failure depth 6)."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=5)
    rungs = []
    patch_chain(mp, rungs.append)
    B = default_store(mp, ns=NS, client=aborting_chain_client(2))
    B.run(mid_chain_arm_body(damper, 'batch_provider_stt', arm_on=1), operation='batch_provider_stt')
    assert rungs[-1] == pytest.approx(4.2)
    assert clock.sleeps[-1] == pytest.approx(4.0)
    assert clock.sleeps == [0.25, 0.5, 1.0, 2.0, 4.0]


def test_g2_gate_rung3_armdepth2_j0p0_batch_provider_stt(mp):
    """Rung 3 waits out the window a sibling armed mid-chain (failure depth 2)."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=1)
    rungs = []
    patch_chain(mp, rungs.append)
    B = default_store(mp, ns=NS, client=aborting_chain_client(3))
    B.run(mid_chain_arm_body(damper, 'batch_provider_stt', arm_on=1), operation='batch_provider_stt')
    assert rungs[-1] == pytest.approx(0.9)
    assert clock.sleeps[-1] == pytest.approx(0.125)
    assert clock.sleeps == [0.125]


def test_g2_gate_rung3_armdepth2_j0p25_batch_provider_stt(mp):
    """Rung 3 waits out the window a sibling armed mid-chain (failure depth 2)."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=1)
    rungs = []
    patch_chain(mp, rungs.append)
    B = default_store(mp, ns=NS, client=aborting_chain_client(3))
    B.run(mid_chain_arm_body(damper, 'batch_provider_stt', arm_on=1), operation='batch_provider_stt')
    assert rungs[-1] == pytest.approx(1.025)
    assert clock.sleeps[-1] == pytest.approx(0.15625)
    assert clock.sleeps == [0.15625]


def test_g2_gate_rung3_armdepth2_j0p5_batch_provider_stt(mp):
    """Rung 3 waits out the window a sibling armed mid-chain (failure depth 2)."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=1)
    rungs = []
    patch_chain(mp, rungs.append)
    B = default_store(mp, ns=NS, client=aborting_chain_client(3))
    B.run(mid_chain_arm_body(damper, 'batch_provider_stt', arm_on=1), operation='batch_provider_stt')
    assert rungs[-1] == pytest.approx(1.15)
    assert clock.sleeps[-1] == pytest.approx(0.1875)
    assert clock.sleeps == [0.1875]


def test_g2_gate_rung3_armdepth2_j1p0_batch_provider_stt(mp):
    """Rung 3 waits out the window a sibling armed mid-chain (failure depth 2)."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=1)
    rungs = []
    patch_chain(mp, rungs.append)
    B = default_store(mp, ns=NS, client=aborting_chain_client(3))
    B.run(mid_chain_arm_body(damper, 'batch_provider_stt', arm_on=1), operation='batch_provider_stt')
    assert rungs[-1] == pytest.approx(1.4)
    assert clock.sleeps[-1] == pytest.approx(0.25)
    assert clock.sleeps == [0.25]


def test_g2_gate_rung3_armdepth3_j0p0_batch_provider_stt(mp):
    """Rung 3 waits out the window a sibling armed mid-chain (failure depth 3)."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=2)
    rungs = []
    patch_chain(mp, rungs.append)
    B = default_store(mp, ns=NS, client=aborting_chain_client(3))
    B.run(mid_chain_arm_body(damper, 'batch_provider_stt', arm_on=1), operation='batch_provider_stt')
    assert rungs[-1] == pytest.approx(0.9)
    assert clock.sleeps[-1] == pytest.approx(0.25)
    assert clock.sleeps == [0.125, 0.25]


def test_g2_gate_rung3_armdepth3_j0p25_batch_provider_stt(mp):
    """Rung 3 waits out the window a sibling armed mid-chain (failure depth 3)."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=2)
    rungs = []
    patch_chain(mp, rungs.append)
    B = default_store(mp, ns=NS, client=aborting_chain_client(3))
    B.run(mid_chain_arm_body(damper, 'batch_provider_stt', arm_on=1), operation='batch_provider_stt')
    assert rungs[-1] == pytest.approx(1.025)
    assert clock.sleeps[-1] == pytest.approx(0.3125)
    assert clock.sleeps == [0.15625, 0.3125]


def test_g2_gate_rung3_armdepth3_j0p5_batch_provider_stt(mp):
    """Rung 3 waits out the window a sibling armed mid-chain (failure depth 3)."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=2)
    rungs = []
    patch_chain(mp, rungs.append)
    B = default_store(mp, ns=NS, client=aborting_chain_client(3))
    B.run(mid_chain_arm_body(damper, 'batch_provider_stt', arm_on=1), operation='batch_provider_stt')
    assert rungs[-1] == pytest.approx(1.15)
    assert clock.sleeps[-1] == pytest.approx(0.375)
    assert clock.sleeps == [0.1875, 0.375]


def test_g2_gate_rung3_armdepth3_j1p0_batch_provider_stt(mp):
    """Rung 3 waits out the window a sibling armed mid-chain (failure depth 3)."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=2)
    rungs = []
    patch_chain(mp, rungs.append)
    B = default_store(mp, ns=NS, client=aborting_chain_client(3))
    B.run(mid_chain_arm_body(damper, 'batch_provider_stt', arm_on=1), operation='batch_provider_stt')
    assert rungs[-1] == pytest.approx(1.4)
    assert clock.sleeps[-1] == pytest.approx(0.5)
    assert clock.sleeps == [0.25, 0.5]


def test_g2_gate_rung3_armdepth4_j0p0_batch_provider_stt(mp):
    """Rung 3 waits out the window a sibling armed mid-chain (failure depth 4)."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=3)
    rungs = []
    patch_chain(mp, rungs.append)
    B = default_store(mp, ns=NS, client=aborting_chain_client(3))
    B.run(mid_chain_arm_body(damper, 'batch_provider_stt', arm_on=1), operation='batch_provider_stt')
    assert rungs[-1] == pytest.approx(1.4)
    assert clock.sleeps[-1] == pytest.approx(0.5)
    assert clock.sleeps == [0.125, 0.25, 0.5]


def test_g2_gate_rung3_armdepth4_j0p25_batch_provider_stt(mp):
    """Rung 3 waits out the window a sibling armed mid-chain (failure depth 4)."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=3)
    rungs = []
    patch_chain(mp, rungs.append)
    B = default_store(mp, ns=NS, client=aborting_chain_client(3))
    B.run(mid_chain_arm_body(damper, 'batch_provider_stt', arm_on=1), operation='batch_provider_stt')
    assert rungs[-1] == pytest.approx(1.65)
    assert clock.sleeps[-1] == pytest.approx(0.625)
    assert clock.sleeps == [0.15625, 0.3125, 0.625]


def test_g2_gate_rung3_armdepth4_j0p5_batch_provider_stt(mp):
    """Rung 3 waits out the window a sibling armed mid-chain (failure depth 4)."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=3)
    rungs = []
    patch_chain(mp, rungs.append)
    B = default_store(mp, ns=NS, client=aborting_chain_client(3))
    B.run(mid_chain_arm_body(damper, 'batch_provider_stt', arm_on=1), operation='batch_provider_stt')
    assert rungs[-1] == pytest.approx(1.9)
    assert clock.sleeps[-1] == pytest.approx(0.75)
    assert clock.sleeps == [0.1875, 0.375, 0.75]


def test_g2_gate_rung3_armdepth4_j1p0_batch_provider_stt(mp):
    """Rung 3 waits out the window a sibling armed mid-chain (failure depth 4)."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=3)
    rungs = []
    patch_chain(mp, rungs.append)
    B = default_store(mp, ns=NS, client=aborting_chain_client(3))
    B.run(mid_chain_arm_body(damper, 'batch_provider_stt', arm_on=1), operation='batch_provider_stt')
    assert rungs[-1] == pytest.approx(2.4)
    assert clock.sleeps[-1] == pytest.approx(1.0)
    assert clock.sleeps == [0.25, 0.5, 1.0]


def test_g2_gate_rung3_armdepth5_j0p0_batch_provider_stt(mp):
    """Rung 3 waits out the window a sibling armed mid-chain (failure depth 5)."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=4)
    rungs = []
    patch_chain(mp, rungs.append)
    B = default_store(mp, ns=NS, client=aborting_chain_client(3))
    B.run(mid_chain_arm_body(damper, 'batch_provider_stt', arm_on=1), operation='batch_provider_stt')
    assert rungs[-1] == pytest.approx(2.4)
    assert clock.sleeps[-1] == pytest.approx(1.0)
    assert clock.sleeps == [0.125, 0.25, 0.5, 1.0]


def test_g2_gate_rung3_armdepth5_j0p25_batch_provider_stt(mp):
    """Rung 3 waits out the window a sibling armed mid-chain (failure depth 5)."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=4)
    rungs = []
    patch_chain(mp, rungs.append)
    B = default_store(mp, ns=NS, client=aborting_chain_client(3))
    B.run(mid_chain_arm_body(damper, 'batch_provider_stt', arm_on=1), operation='batch_provider_stt')
    assert rungs[-1] == pytest.approx(2.9)
    assert clock.sleeps[-1] == pytest.approx(1.25)
    assert clock.sleeps == [0.15625, 0.3125, 0.625, 1.25]


def test_g2_gate_rung3_armdepth5_j0p5_batch_provider_stt(mp):
    """Rung 3 waits out the window a sibling armed mid-chain (failure depth 5)."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=4)
    rungs = []
    patch_chain(mp, rungs.append)
    B = default_store(mp, ns=NS, client=aborting_chain_client(3))
    B.run(mid_chain_arm_body(damper, 'batch_provider_stt', arm_on=1), operation='batch_provider_stt')
    assert rungs[-1] == pytest.approx(3.4)
    assert clock.sleeps[-1] == pytest.approx(1.5)
    assert clock.sleeps == [0.1875, 0.375, 0.75, 1.5]


def test_g2_gate_rung3_armdepth5_j1p0_batch_provider_stt(mp):
    """Rung 3 waits out the window a sibling armed mid-chain (failure depth 5)."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=4)
    rungs = []
    patch_chain(mp, rungs.append)
    B = default_store(mp, ns=NS, client=aborting_chain_client(3))
    B.run(mid_chain_arm_body(damper, 'batch_provider_stt', arm_on=1), operation='batch_provider_stt')
    assert rungs[-1] == pytest.approx(4.4)
    assert clock.sleeps[-1] == pytest.approx(2.0)
    assert clock.sleeps == [0.25, 0.5, 1.0, 2.0]


def test_g2_gate_rung3_armdepth6_j0p0_batch_provider_stt(mp):
    """Rung 3 waits out the window a sibling armed mid-chain (failure depth 6)."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=5)
    rungs = []
    patch_chain(mp, rungs.append)
    B = default_store(mp, ns=NS, client=aborting_chain_client(3))
    B.run(mid_chain_arm_body(damper, 'batch_provider_stt', arm_on=1), operation='batch_provider_stt')
    assert rungs[-1] == pytest.approx(2.4)
    assert clock.sleeps[-1] == pytest.approx(2.0)
    assert clock.sleeps == [0.125, 0.25, 0.5, 1.0, 2.0]


def test_g2_gate_rung3_armdepth6_j0p25_batch_provider_stt(mp):
    """Rung 3 waits out the window a sibling armed mid-chain (failure depth 6)."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=5)
    rungs = []
    patch_chain(mp, rungs.append)
    B = default_store(mp, ns=NS, client=aborting_chain_client(3))
    B.run(mid_chain_arm_body(damper, 'batch_provider_stt', arm_on=1), operation='batch_provider_stt')
    assert rungs[-1] == pytest.approx(2.9)
    assert clock.sleeps[-1] == pytest.approx(2.5)
    assert clock.sleeps == [0.15625, 0.3125, 0.625, 1.25, 2.5]


def test_g2_gate_rung3_armdepth6_j0p5_batch_provider_stt(mp):
    """Rung 3 waits out the window a sibling armed mid-chain (failure depth 6)."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=5)
    rungs = []
    patch_chain(mp, rungs.append)
    B = default_store(mp, ns=NS, client=aborting_chain_client(3))
    B.run(mid_chain_arm_body(damper, 'batch_provider_stt', arm_on=1), operation='batch_provider_stt')
    assert rungs[-1] == pytest.approx(3.4)
    assert clock.sleeps[-1] == pytest.approx(3.0)
    assert clock.sleeps == [0.1875, 0.375, 0.75, 1.5, 3.0]


def test_g2_gate_rung3_armdepth6_j1p0_batch_provider_stt(mp):
    """Rung 3 waits out the window a sibling armed mid-chain (failure depth 6)."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=5)
    rungs = []
    patch_chain(mp, rungs.append)
    B = default_store(mp, ns=NS, client=aborting_chain_client(3))
    B.run(mid_chain_arm_body(damper, 'batch_provider_stt', arm_on=1), operation='batch_provider_stt')
    assert rungs[-1] == pytest.approx(4.4)
    assert clock.sleeps[-1] == pytest.approx(4.0)
    assert clock.sleeps == [0.25, 0.5, 1.0, 2.0, 4.0]


def test_g2_gate_rung4_armdepth2_j0p0_batch_provider_stt(mp):
    """Rung 4 waits out the window a sibling armed mid-chain (failure depth 2)."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=1)
    rungs = []
    patch_chain(mp, rungs.append)
    B = default_store(mp, ns=NS, client=aborting_chain_client(4))
    B.run(mid_chain_arm_body(damper, 'batch_provider_stt', arm_on=1), operation='batch_provider_stt')
    assert rungs[-1] == pytest.approx(1.8)
    assert clock.sleeps[-1] == pytest.approx(0.125)
    assert clock.sleeps == [0.125]


def test_g2_gate_rung4_armdepth2_j0p25_batch_provider_stt(mp):
    """Rung 4 waits out the window a sibling armed mid-chain (failure depth 2)."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=1)
    rungs = []
    patch_chain(mp, rungs.append)
    B = default_store(mp, ns=NS, client=aborting_chain_client(4))
    B.run(mid_chain_arm_body(damper, 'batch_provider_stt', arm_on=1), operation='batch_provider_stt')
    assert rungs[-1] == pytest.approx(2.05)
    assert clock.sleeps[-1] == pytest.approx(0.15625)
    assert clock.sleeps == [0.15625]


def test_g2_gate_rung4_armdepth2_j0p5_batch_provider_stt(mp):
    """Rung 4 waits out the window a sibling armed mid-chain (failure depth 2)."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=1)
    rungs = []
    patch_chain(mp, rungs.append)
    B = default_store(mp, ns=NS, client=aborting_chain_client(4))
    B.run(mid_chain_arm_body(damper, 'batch_provider_stt', arm_on=1), operation='batch_provider_stt')
    assert rungs[-1] == pytest.approx(2.3)
    assert clock.sleeps[-1] == pytest.approx(0.1875)
    assert clock.sleeps == [0.1875]


def test_g2_gate_rung4_armdepth2_j1p0_batch_provider_stt(mp):
    """Rung 4 waits out the window a sibling armed mid-chain (failure depth 2)."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=1)
    rungs = []
    patch_chain(mp, rungs.append)
    B = default_store(mp, ns=NS, client=aborting_chain_client(4))
    B.run(mid_chain_arm_body(damper, 'batch_provider_stt', arm_on=1), operation='batch_provider_stt')
    assert rungs[-1] == pytest.approx(2.8)
    assert clock.sleeps[-1] == pytest.approx(0.25)
    assert clock.sleeps == [0.25]


def test_g2_gate_rung4_armdepth3_j0p0_batch_provider_stt(mp):
    """Rung 4 waits out the window a sibling armed mid-chain (failure depth 3)."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=2)
    rungs = []
    patch_chain(mp, rungs.append)
    B = default_store(mp, ns=NS, client=aborting_chain_client(4))
    B.run(mid_chain_arm_body(damper, 'batch_provider_stt', arm_on=1), operation='batch_provider_stt')
    assert rungs[-1] == pytest.approx(1.8)
    assert clock.sleeps[-1] == pytest.approx(0.25)
    assert clock.sleeps == [0.125, 0.25]


def test_g2_gate_rung4_armdepth3_j0p25_batch_provider_stt(mp):
    """Rung 4 waits out the window a sibling armed mid-chain (failure depth 3)."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=2)
    rungs = []
    patch_chain(mp, rungs.append)
    B = default_store(mp, ns=NS, client=aborting_chain_client(4))
    B.run(mid_chain_arm_body(damper, 'batch_provider_stt', arm_on=1), operation='batch_provider_stt')
    assert rungs[-1] == pytest.approx(2.05)
    assert clock.sleeps[-1] == pytest.approx(0.3125)
    assert clock.sleeps == [0.15625, 0.3125]


def test_g2_gate_rung4_armdepth3_j0p5_batch_provider_stt(mp):
    """Rung 4 waits out the window a sibling armed mid-chain (failure depth 3)."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=2)
    rungs = []
    patch_chain(mp, rungs.append)
    B = default_store(mp, ns=NS, client=aborting_chain_client(4))
    B.run(mid_chain_arm_body(damper, 'batch_provider_stt', arm_on=1), operation='batch_provider_stt')
    assert rungs[-1] == pytest.approx(2.3)
    assert clock.sleeps[-1] == pytest.approx(0.375)
    assert clock.sleeps == [0.1875, 0.375]


def test_g2_gate_rung4_armdepth3_j1p0_batch_provider_stt(mp):
    """Rung 4 waits out the window a sibling armed mid-chain (failure depth 3)."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=2)
    rungs = []
    patch_chain(mp, rungs.append)
    B = default_store(mp, ns=NS, client=aborting_chain_client(4))
    B.run(mid_chain_arm_body(damper, 'batch_provider_stt', arm_on=1), operation='batch_provider_stt')
    assert rungs[-1] == pytest.approx(2.8)
    assert clock.sleeps[-1] == pytest.approx(0.5)
    assert clock.sleeps == [0.25, 0.5]


def test_g2_gate_rung4_armdepth4_j0p0_batch_provider_stt(mp):
    """Rung 4 waits out the window a sibling armed mid-chain (failure depth 4)."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=3)
    rungs = []
    patch_chain(mp, rungs.append)
    B = default_store(mp, ns=NS, client=aborting_chain_client(4))
    B.run(mid_chain_arm_body(damper, 'batch_provider_stt', arm_on=1), operation='batch_provider_stt')
    assert rungs[-1] == pytest.approx(1.8)
    assert clock.sleeps[-1] == pytest.approx(0.5)
    assert clock.sleeps == [0.125, 0.25, 0.5]


def test_g2_gate_rung4_armdepth4_j0p25_batch_provider_stt(mp):
    """Rung 4 waits out the window a sibling armed mid-chain (failure depth 4)."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=3)
    rungs = []
    patch_chain(mp, rungs.append)
    B = default_store(mp, ns=NS, client=aborting_chain_client(4))
    B.run(mid_chain_arm_body(damper, 'batch_provider_stt', arm_on=1), operation='batch_provider_stt')
    assert rungs[-1] == pytest.approx(2.05)
    assert clock.sleeps[-1] == pytest.approx(0.625)
    assert clock.sleeps == [0.15625, 0.3125, 0.625]


def test_g2_gate_rung4_armdepth4_j0p5_batch_provider_stt(mp):
    """Rung 4 waits out the window a sibling armed mid-chain (failure depth 4)."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=3)
    rungs = []
    patch_chain(mp, rungs.append)
    B = default_store(mp, ns=NS, client=aborting_chain_client(4))
    B.run(mid_chain_arm_body(damper, 'batch_provider_stt', arm_on=1), operation='batch_provider_stt')
    assert rungs[-1] == pytest.approx(2.3)
    assert clock.sleeps[-1] == pytest.approx(0.75)
    assert clock.sleeps == [0.1875, 0.375, 0.75]


def test_g2_gate_rung4_armdepth4_j1p0_batch_provider_stt(mp):
    """Rung 4 waits out the window a sibling armed mid-chain (failure depth 4)."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=3)
    rungs = []
    patch_chain(mp, rungs.append)
    B = default_store(mp, ns=NS, client=aborting_chain_client(4))
    B.run(mid_chain_arm_body(damper, 'batch_provider_stt', arm_on=1), operation='batch_provider_stt')
    assert rungs[-1] == pytest.approx(2.8)
    assert clock.sleeps[-1] == pytest.approx(1.0)
    assert clock.sleeps == [0.25, 0.5, 1.0]


def test_g2_gate_rung4_armdepth5_j0p0_batch_provider_stt(mp):
    """Rung 4 waits out the window a sibling armed mid-chain (failure depth 5)."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=4)
    rungs = []
    patch_chain(mp, rungs.append)
    B = default_store(mp, ns=NS, client=aborting_chain_client(4))
    B.run(mid_chain_arm_body(damper, 'batch_provider_stt', arm_on=1), operation='batch_provider_stt')
    assert rungs[-1] == pytest.approx(2.8)
    assert clock.sleeps[-1] == pytest.approx(1.0)
    assert clock.sleeps == [0.125, 0.25, 0.5, 1.0]


def test_g2_gate_rung4_armdepth5_j0p25_batch_provider_stt(mp):
    """Rung 4 waits out the window a sibling armed mid-chain (failure depth 5)."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=4)
    rungs = []
    patch_chain(mp, rungs.append)
    B = default_store(mp, ns=NS, client=aborting_chain_client(4))
    B.run(mid_chain_arm_body(damper, 'batch_provider_stt', arm_on=1), operation='batch_provider_stt')
    assert rungs[-1] == pytest.approx(3.3)
    assert clock.sleeps[-1] == pytest.approx(1.25)
    assert clock.sleeps == [0.15625, 0.3125, 0.625, 1.25]


def test_g2_gate_rung4_armdepth5_j0p5_batch_provider_stt(mp):
    """Rung 4 waits out the window a sibling armed mid-chain (failure depth 5)."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=4)
    rungs = []
    patch_chain(mp, rungs.append)
    B = default_store(mp, ns=NS, client=aborting_chain_client(4))
    B.run(mid_chain_arm_body(damper, 'batch_provider_stt', arm_on=1), operation='batch_provider_stt')
    assert rungs[-1] == pytest.approx(3.8)
    assert clock.sleeps[-1] == pytest.approx(1.5)
    assert clock.sleeps == [0.1875, 0.375, 0.75, 1.5]


def test_g2_gate_rung4_armdepth5_j1p0_batch_provider_stt(mp):
    """Rung 4 waits out the window a sibling armed mid-chain (failure depth 5)."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=4)
    rungs = []
    patch_chain(mp, rungs.append)
    B = default_store(mp, ns=NS, client=aborting_chain_client(4))
    B.run(mid_chain_arm_body(damper, 'batch_provider_stt', arm_on=1), operation='batch_provider_stt')
    assert rungs[-1] == pytest.approx(4.8)
    assert clock.sleeps[-1] == pytest.approx(2.0)
    assert clock.sleeps == [0.25, 0.5, 1.0, 2.0]


def test_g2_gate_rung4_armdepth6_j0p0_batch_provider_stt(mp):
    """Rung 4 waits out the window a sibling armed mid-chain (failure depth 6)."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=5)
    rungs = []
    patch_chain(mp, rungs.append)
    B = default_store(mp, ns=NS, client=aborting_chain_client(4))
    B.run(mid_chain_arm_body(damper, 'batch_provider_stt', arm_on=1), operation='batch_provider_stt')
    assert rungs[-1] == pytest.approx(2.8)
    assert clock.sleeps[-1] == pytest.approx(2.0)
    assert clock.sleeps == [0.125, 0.25, 0.5, 1.0, 2.0]


def test_g2_gate_rung4_armdepth6_j0p25_batch_provider_stt(mp):
    """Rung 4 waits out the window a sibling armed mid-chain (failure depth 6)."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=5)
    rungs = []
    patch_chain(mp, rungs.append)
    B = default_store(mp, ns=NS, client=aborting_chain_client(4))
    B.run(mid_chain_arm_body(damper, 'batch_provider_stt', arm_on=1), operation='batch_provider_stt')
    assert rungs[-1] == pytest.approx(3.3)
    assert clock.sleeps[-1] == pytest.approx(2.5)
    assert clock.sleeps == [0.15625, 0.3125, 0.625, 1.25, 2.5]


def test_g2_gate_rung4_armdepth6_j0p5_batch_provider_stt(mp):
    """Rung 4 waits out the window a sibling armed mid-chain (failure depth 6)."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=5)
    rungs = []
    patch_chain(mp, rungs.append)
    B = default_store(mp, ns=NS, client=aborting_chain_client(4))
    B.run(mid_chain_arm_body(damper, 'batch_provider_stt', arm_on=1), operation='batch_provider_stt')
    assert rungs[-1] == pytest.approx(3.8)
    assert clock.sleeps[-1] == pytest.approx(3.0)
    assert clock.sleeps == [0.1875, 0.375, 0.75, 1.5, 3.0]


def test_g2_gate_rung4_armdepth6_j1p0_batch_provider_stt(mp):
    """Rung 4 waits out the window a sibling armed mid-chain (failure depth 6)."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=5)
    rungs = []
    patch_chain(mp, rungs.append)
    B = default_store(mp, ns=NS, client=aborting_chain_client(4))
    B.run(mid_chain_arm_body(damper, 'batch_provider_stt', arm_on=1), operation='batch_provider_stt')
    assert rungs[-1] == pytest.approx(4.8)
    assert clock.sleeps[-1] == pytest.approx(4.0)
    assert clock.sleeps == [0.25, 0.5, 1.0, 2.0, 4.0]


def test_g3_retry_after_stamp_batch_pipeline_dev_k1_j0p0(mp):
    """The exhaustion stamp equals the residual the sibling waits on the shared damper."""
    damper, clock = shared_damper('batch_pipeline_dev', jitter=0.0)
    A = default_store(mp, ns='batch_pipeline_dev', client=exhausting_client())
    error = exhaust_run(A, 'batch_merge_commit', times=1)
    assert error.retry_after == pytest.approx(0.125)
    B = default_store(mp, ns='batch_pipeline_dev', client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(error.retry_after)


def test_g3_retry_after_stamp_batch_pipeline_dev_k1_j0p25(mp):
    """The exhaustion stamp equals the residual the sibling waits on the shared damper."""
    damper, clock = shared_damper('batch_pipeline_dev', jitter=0.25)
    A = default_store(mp, ns='batch_pipeline_dev', client=exhausting_client())
    error = exhaust_run(A, 'batch_merge_commit', times=1)
    assert error.retry_after == pytest.approx(0.15625)
    B = default_store(mp, ns='batch_pipeline_dev', client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(error.retry_after)


def test_g3_retry_after_stamp_batch_pipeline_dev_k1_j0p5(mp):
    """The exhaustion stamp equals the residual the sibling waits on the shared damper."""
    damper, clock = shared_damper('batch_pipeline_dev', jitter=0.5)
    A = default_store(mp, ns='batch_pipeline_dev', client=exhausting_client())
    error = exhaust_run(A, 'batch_merge_commit', times=1)
    assert error.retry_after == pytest.approx(0.1875)
    B = default_store(mp, ns='batch_pipeline_dev', client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(error.retry_after)


def test_g3_retry_after_stamp_batch_pipeline_dev_k1_j1p0(mp):
    """The exhaustion stamp equals the residual the sibling waits on the shared damper."""
    damper, clock = shared_damper('batch_pipeline_dev', jitter=1.0)
    A = default_store(mp, ns='batch_pipeline_dev', client=exhausting_client())
    error = exhaust_run(A, 'batch_merge_commit', times=1)
    assert error.retry_after == pytest.approx(0.25)
    B = default_store(mp, ns='batch_pipeline_dev', client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(error.retry_after)


def test_g3_retry_after_stamp_batch_pipeline_dev_k2_j0p0(mp):
    """The exhaustion stamp equals the residual the sibling waits on the shared damper."""
    damper, clock = shared_damper('batch_pipeline_dev', jitter=0.0)
    A = default_store(mp, ns='batch_pipeline_dev', client=exhausting_client())
    error = exhaust_run(A, 'batch_merge_commit', times=2)
    assert error.retry_after == pytest.approx(0.25)
    B = default_store(mp, ns='batch_pipeline_dev', client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(error.retry_after)


def test_g3_retry_after_stamp_batch_pipeline_dev_k2_j0p25(mp):
    """The exhaustion stamp equals the residual the sibling waits on the shared damper."""
    damper, clock = shared_damper('batch_pipeline_dev', jitter=0.25)
    A = default_store(mp, ns='batch_pipeline_dev', client=exhausting_client())
    error = exhaust_run(A, 'batch_merge_commit', times=2)
    assert error.retry_after == pytest.approx(0.3125)
    B = default_store(mp, ns='batch_pipeline_dev', client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(error.retry_after)


def test_g3_retry_after_stamp_batch_pipeline_dev_k2_j0p5(mp):
    """The exhaustion stamp equals the residual the sibling waits on the shared damper."""
    damper, clock = shared_damper('batch_pipeline_dev', jitter=0.5)
    A = default_store(mp, ns='batch_pipeline_dev', client=exhausting_client())
    error = exhaust_run(A, 'batch_merge_commit', times=2)
    assert error.retry_after == pytest.approx(0.375)
    B = default_store(mp, ns='batch_pipeline_dev', client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(error.retry_after)


def test_g3_retry_after_stamp_batch_pipeline_dev_k2_j1p0(mp):
    """The exhaustion stamp equals the residual the sibling waits on the shared damper."""
    damper, clock = shared_damper('batch_pipeline_dev', jitter=1.0)
    A = default_store(mp, ns='batch_pipeline_dev', client=exhausting_client())
    error = exhaust_run(A, 'batch_merge_commit', times=2)
    assert error.retry_after == pytest.approx(0.5)
    B = default_store(mp, ns='batch_pipeline_dev', client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(error.retry_after)


def test_g3_retry_after_stamp_batch_pipeline_dev_k3_j0p0(mp):
    """The exhaustion stamp equals the residual the sibling waits on the shared damper."""
    damper, clock = shared_damper('batch_pipeline_dev', jitter=0.0)
    A = default_store(mp, ns='batch_pipeline_dev', client=exhausting_client())
    error = exhaust_run(A, 'batch_merge_commit', times=3)
    assert error.retry_after == pytest.approx(0.5)
    B = default_store(mp, ns='batch_pipeline_dev', client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(error.retry_after)


def test_g3_retry_after_stamp_batch_pipeline_dev_k3_j0p25(mp):
    """The exhaustion stamp equals the residual the sibling waits on the shared damper."""
    damper, clock = shared_damper('batch_pipeline_dev', jitter=0.25)
    A = default_store(mp, ns='batch_pipeline_dev', client=exhausting_client())
    error = exhaust_run(A, 'batch_merge_commit', times=3)
    assert error.retry_after == pytest.approx(0.625)
    B = default_store(mp, ns='batch_pipeline_dev', client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(error.retry_after)


def test_g3_retry_after_stamp_batch_pipeline_dev_k3_j0p5(mp):
    """The exhaustion stamp equals the residual the sibling waits on the shared damper."""
    damper, clock = shared_damper('batch_pipeline_dev', jitter=0.5)
    A = default_store(mp, ns='batch_pipeline_dev', client=exhausting_client())
    error = exhaust_run(A, 'batch_merge_commit', times=3)
    assert error.retry_after == pytest.approx(0.75)
    B = default_store(mp, ns='batch_pipeline_dev', client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(error.retry_after)


def test_g3_retry_after_stamp_batch_pipeline_dev_k3_j1p0(mp):
    """The exhaustion stamp equals the residual the sibling waits on the shared damper."""
    damper, clock = shared_damper('batch_pipeline_dev', jitter=1.0)
    A = default_store(mp, ns='batch_pipeline_dev', client=exhausting_client())
    error = exhaust_run(A, 'batch_merge_commit', times=3)
    assert error.retry_after == pytest.approx(1.0)
    B = default_store(mp, ns='batch_pipeline_dev', client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(error.retry_after)


def test_g3_retry_after_stamp_batch_pipeline_dev_k4_j0p0(mp):
    """The exhaustion stamp equals the residual the sibling waits on the shared damper."""
    damper, clock = shared_damper('batch_pipeline_dev', jitter=0.0)
    A = default_store(mp, ns='batch_pipeline_dev', client=exhausting_client())
    error = exhaust_run(A, 'batch_merge_commit', times=4)
    assert error.retry_after == pytest.approx(1.0)
    B = default_store(mp, ns='batch_pipeline_dev', client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(error.retry_after)


def test_g3_retry_after_stamp_batch_pipeline_dev_k4_j0p25(mp):
    """The exhaustion stamp equals the residual the sibling waits on the shared damper."""
    damper, clock = shared_damper('batch_pipeline_dev', jitter=0.25)
    A = default_store(mp, ns='batch_pipeline_dev', client=exhausting_client())
    error = exhaust_run(A, 'batch_merge_commit', times=4)
    assert error.retry_after == pytest.approx(1.25)
    B = default_store(mp, ns='batch_pipeline_dev', client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(error.retry_after)


def test_g3_retry_after_stamp_batch_pipeline_dev_k4_j0p5(mp):
    """The exhaustion stamp equals the residual the sibling waits on the shared damper."""
    damper, clock = shared_damper('batch_pipeline_dev', jitter=0.5)
    A = default_store(mp, ns='batch_pipeline_dev', client=exhausting_client())
    error = exhaust_run(A, 'batch_merge_commit', times=4)
    assert error.retry_after == pytest.approx(1.5)
    B = default_store(mp, ns='batch_pipeline_dev', client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(error.retry_after)


def test_g3_retry_after_stamp_batch_pipeline_dev_k4_j1p0(mp):
    """The exhaustion stamp equals the residual the sibling waits on the shared damper."""
    damper, clock = shared_damper('batch_pipeline_dev', jitter=1.0)
    A = default_store(mp, ns='batch_pipeline_dev', client=exhausting_client())
    error = exhaust_run(A, 'batch_merge_commit', times=4)
    assert error.retry_after == pytest.approx(2.0)
    B = default_store(mp, ns='batch_pipeline_dev', client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(error.retry_after)


def test_g3_retry_after_stamp_batch_pipeline_dev_k5_j0p0(mp):
    """The exhaustion stamp equals the residual the sibling waits on the shared damper."""
    damper, clock = shared_damper('batch_pipeline_dev', jitter=0.0)
    A = default_store(mp, ns='batch_pipeline_dev', client=exhausting_client())
    error = exhaust_run(A, 'batch_merge_commit', times=5)
    assert error.retry_after == pytest.approx(2.0)
    B = default_store(mp, ns='batch_pipeline_dev', client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(error.retry_after)


def test_g3_retry_after_stamp_batch_pipeline_dev_k5_j0p25(mp):
    """The exhaustion stamp equals the residual the sibling waits on the shared damper."""
    damper, clock = shared_damper('batch_pipeline_dev', jitter=0.25)
    A = default_store(mp, ns='batch_pipeline_dev', client=exhausting_client())
    error = exhaust_run(A, 'batch_merge_commit', times=5)
    assert error.retry_after == pytest.approx(2.5)
    B = default_store(mp, ns='batch_pipeline_dev', client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(error.retry_after)


def test_g3_retry_after_stamp_batch_pipeline_dev_k5_j0p5(mp):
    """The exhaustion stamp equals the residual the sibling waits on the shared damper."""
    damper, clock = shared_damper('batch_pipeline_dev', jitter=0.5)
    A = default_store(mp, ns='batch_pipeline_dev', client=exhausting_client())
    error = exhaust_run(A, 'batch_merge_commit', times=5)
    assert error.retry_after == pytest.approx(3.0)
    B = default_store(mp, ns='batch_pipeline_dev', client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(error.retry_after)


def test_g3_retry_after_stamp_batch_pipeline_dev_k5_j1p0(mp):
    """The exhaustion stamp equals the residual the sibling waits on the shared damper."""
    damper, clock = shared_damper('batch_pipeline_dev', jitter=1.0)
    A = default_store(mp, ns='batch_pipeline_dev', client=exhausting_client())
    error = exhaust_run(A, 'batch_merge_commit', times=5)
    assert error.retry_after == pytest.approx(4.0)
    B = default_store(mp, ns='batch_pipeline_dev', client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(error.retry_after)


def test_g3_retry_after_stamp_batch_pipeline_dev_k6_j0p0(mp):
    """The exhaustion stamp equals the residual the sibling waits on the shared damper."""
    damper, clock = shared_damper('batch_pipeline_dev', jitter=0.0)
    A = default_store(mp, ns='batch_pipeline_dev', client=exhausting_client())
    error = exhaust_run(A, 'batch_merge_commit', times=6)
    assert error.retry_after == pytest.approx(2.0)
    B = default_store(mp, ns='batch_pipeline_dev', client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(error.retry_after)


def test_g3_retry_after_stamp_batch_pipeline_dev_k6_j0p25(mp):
    """The exhaustion stamp equals the residual the sibling waits on the shared damper."""
    damper, clock = shared_damper('batch_pipeline_dev', jitter=0.25)
    A = default_store(mp, ns='batch_pipeline_dev', client=exhausting_client())
    error = exhaust_run(A, 'batch_merge_commit', times=6)
    assert error.retry_after == pytest.approx(2.5)
    B = default_store(mp, ns='batch_pipeline_dev', client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(error.retry_after)


def test_g3_retry_after_stamp_batch_pipeline_dev_k6_j0p5(mp):
    """The exhaustion stamp equals the residual the sibling waits on the shared damper."""
    damper, clock = shared_damper('batch_pipeline_dev', jitter=0.5)
    A = default_store(mp, ns='batch_pipeline_dev', client=exhausting_client())
    error = exhaust_run(A, 'batch_merge_commit', times=6)
    assert error.retry_after == pytest.approx(3.0)
    B = default_store(mp, ns='batch_pipeline_dev', client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(error.retry_after)


def test_g3_retry_after_stamp_batch_pipeline_dev_k6_j1p0(mp):
    """The exhaustion stamp equals the residual the sibling waits on the shared damper."""
    damper, clock = shared_damper('batch_pipeline_dev', jitter=1.0)
    A = default_store(mp, ns='batch_pipeline_dev', client=exhausting_client())
    error = exhaust_run(A, 'batch_merge_commit', times=6)
    assert error.retry_after == pytest.approx(4.0)
    B = default_store(mp, ns='batch_pipeline_dev', client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(error.retry_after)


def test_g3_retry_after_stamp_batch_pipeline_dev_k7_j0p0(mp):
    """The exhaustion stamp equals the residual the sibling waits on the shared damper."""
    damper, clock = shared_damper('batch_pipeline_dev', jitter=0.0)
    A = default_store(mp, ns='batch_pipeline_dev', client=exhausting_client())
    error = exhaust_run(A, 'batch_merge_commit', times=7)
    assert error.retry_after == pytest.approx(2.0)
    B = default_store(mp, ns='batch_pipeline_dev', client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(error.retry_after)


def test_g3_retry_after_stamp_batch_pipeline_dev_k7_j0p25(mp):
    """The exhaustion stamp equals the residual the sibling waits on the shared damper."""
    damper, clock = shared_damper('batch_pipeline_dev', jitter=0.25)
    A = default_store(mp, ns='batch_pipeline_dev', client=exhausting_client())
    error = exhaust_run(A, 'batch_merge_commit', times=7)
    assert error.retry_after == pytest.approx(2.5)
    B = default_store(mp, ns='batch_pipeline_dev', client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(error.retry_after)


def test_g3_retry_after_stamp_batch_pipeline_dev_k7_j0p5(mp):
    """The exhaustion stamp equals the residual the sibling waits on the shared damper."""
    damper, clock = shared_damper('batch_pipeline_dev', jitter=0.5)
    A = default_store(mp, ns='batch_pipeline_dev', client=exhausting_client())
    error = exhaust_run(A, 'batch_merge_commit', times=7)
    assert error.retry_after == pytest.approx(3.0)
    B = default_store(mp, ns='batch_pipeline_dev', client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(error.retry_after)


def test_g3_retry_after_stamp_batch_pipeline_dev_k7_j1p0(mp):
    """The exhaustion stamp equals the residual the sibling waits on the shared damper."""
    damper, clock = shared_damper('batch_pipeline_dev', jitter=1.0)
    A = default_store(mp, ns='batch_pipeline_dev', client=exhausting_client())
    error = exhaust_run(A, 'batch_merge_commit', times=7)
    assert error.retry_after == pytest.approx(4.0)
    B = default_store(mp, ns='batch_pipeline_dev', client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(error.retry_after)


def test_g3_retry_after_stamp_batch_pipeline_dev_k8_j0p0(mp):
    """The exhaustion stamp equals the residual the sibling waits on the shared damper."""
    damper, clock = shared_damper('batch_pipeline_dev', jitter=0.0)
    A = default_store(mp, ns='batch_pipeline_dev', client=exhausting_client())
    error = exhaust_run(A, 'batch_merge_commit', times=8)
    assert error.retry_after == pytest.approx(2.0)
    B = default_store(mp, ns='batch_pipeline_dev', client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(error.retry_after)


def test_g3_retry_after_stamp_batch_pipeline_dev_k8_j0p25(mp):
    """The exhaustion stamp equals the residual the sibling waits on the shared damper."""
    damper, clock = shared_damper('batch_pipeline_dev', jitter=0.25)
    A = default_store(mp, ns='batch_pipeline_dev', client=exhausting_client())
    error = exhaust_run(A, 'batch_merge_commit', times=8)
    assert error.retry_after == pytest.approx(2.5)
    B = default_store(mp, ns='batch_pipeline_dev', client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(error.retry_after)


def test_g3_retry_after_stamp_batch_pipeline_dev_k8_j0p5(mp):
    """The exhaustion stamp equals the residual the sibling waits on the shared damper."""
    damper, clock = shared_damper('batch_pipeline_dev', jitter=0.5)
    A = default_store(mp, ns='batch_pipeline_dev', client=exhausting_client())
    error = exhaust_run(A, 'batch_merge_commit', times=8)
    assert error.retry_after == pytest.approx(3.0)
    B = default_store(mp, ns='batch_pipeline_dev', client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(error.retry_after)


def test_g3_retry_after_stamp_batch_pipeline_dev_k8_j1p0(mp):
    """The exhaustion stamp equals the residual the sibling waits on the shared damper."""
    damper, clock = shared_damper('batch_pipeline_dev', jitter=1.0)
    A = default_store(mp, ns='batch_pipeline_dev', client=exhausting_client())
    error = exhaust_run(A, 'batch_merge_commit', times=8)
    assert error.retry_after == pytest.approx(4.0)
    B = default_store(mp, ns='batch_pipeline_dev', client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(error.retry_after)


def test_g3_retry_after_stamp_batch_pipeline_dev_k9_j0p0(mp):
    """The exhaustion stamp equals the residual the sibling waits on the shared damper."""
    damper, clock = shared_damper('batch_pipeline_dev', jitter=0.0)
    A = default_store(mp, ns='batch_pipeline_dev', client=exhausting_client())
    error = exhaust_run(A, 'batch_merge_commit', times=9)
    assert error.retry_after == pytest.approx(2.0)
    B = default_store(mp, ns='batch_pipeline_dev', client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(error.retry_after)


def test_g3_retry_after_stamp_batch_pipeline_dev_k9_j0p25(mp):
    """The exhaustion stamp equals the residual the sibling waits on the shared damper."""
    damper, clock = shared_damper('batch_pipeline_dev', jitter=0.25)
    A = default_store(mp, ns='batch_pipeline_dev', client=exhausting_client())
    error = exhaust_run(A, 'batch_merge_commit', times=9)
    assert error.retry_after == pytest.approx(2.5)
    B = default_store(mp, ns='batch_pipeline_dev', client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(error.retry_after)


def test_g3_retry_after_stamp_batch_pipeline_dev_k9_j0p5(mp):
    """The exhaustion stamp equals the residual the sibling waits on the shared damper."""
    damper, clock = shared_damper('batch_pipeline_dev', jitter=0.5)
    A = default_store(mp, ns='batch_pipeline_dev', client=exhausting_client())
    error = exhaust_run(A, 'batch_merge_commit', times=9)
    assert error.retry_after == pytest.approx(3.0)
    B = default_store(mp, ns='batch_pipeline_dev', client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(error.retry_after)


def test_g3_retry_after_stamp_batch_pipeline_dev_k9_j1p0(mp):
    """The exhaustion stamp equals the residual the sibling waits on the shared damper."""
    damper, clock = shared_damper('batch_pipeline_dev', jitter=1.0)
    A = default_store(mp, ns='batch_pipeline_dev', client=exhausting_client())
    error = exhaust_run(A, 'batch_merge_commit', times=9)
    assert error.retry_after == pytest.approx(4.0)
    B = default_store(mp, ns='batch_pipeline_dev', client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(error.retry_after)


def test_g3_retry_after_stamp_batch_pipeline_dev_k10_j0p0(mp):
    """The exhaustion stamp equals the residual the sibling waits on the shared damper."""
    damper, clock = shared_damper('batch_pipeline_dev', jitter=0.0)
    A = default_store(mp, ns='batch_pipeline_dev', client=exhausting_client())
    error = exhaust_run(A, 'batch_merge_commit', times=10)
    assert error.retry_after == pytest.approx(2.0)
    B = default_store(mp, ns='batch_pipeline_dev', client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(error.retry_after)


def test_g3_retry_after_stamp_batch_pipeline_dev_k10_j0p25(mp):
    """The exhaustion stamp equals the residual the sibling waits on the shared damper."""
    damper, clock = shared_damper('batch_pipeline_dev', jitter=0.25)
    A = default_store(mp, ns='batch_pipeline_dev', client=exhausting_client())
    error = exhaust_run(A, 'batch_merge_commit', times=10)
    assert error.retry_after == pytest.approx(2.5)
    B = default_store(mp, ns='batch_pipeline_dev', client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(error.retry_after)


def test_g3_retry_after_stamp_batch_pipeline_dev_k10_j0p5(mp):
    """The exhaustion stamp equals the residual the sibling waits on the shared damper."""
    damper, clock = shared_damper('batch_pipeline_dev', jitter=0.5)
    A = default_store(mp, ns='batch_pipeline_dev', client=exhausting_client())
    error = exhaust_run(A, 'batch_merge_commit', times=10)
    assert error.retry_after == pytest.approx(3.0)
    B = default_store(mp, ns='batch_pipeline_dev', client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(error.retry_after)


def test_g3_retry_after_stamp_batch_pipeline_dev_k10_j1p0(mp):
    """The exhaustion stamp equals the residual the sibling waits on the shared damper."""
    damper, clock = shared_damper('batch_pipeline_dev', jitter=1.0)
    A = default_store(mp, ns='batch_pipeline_dev', client=exhausting_client())
    error = exhaust_run(A, 'batch_merge_commit', times=10)
    assert error.retry_after == pytest.approx(4.0)
    B = default_store(mp, ns='batch_pipeline_dev', client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(error.retry_after)


def test_g3_retry_after_stamp_batch_pipeline_prod_k1_j0p0(mp):
    """The exhaustion stamp equals the residual the sibling waits on the shared damper."""
    damper, clock = shared_damper('batch_pipeline_prod', jitter=0.0)
    A = default_store(mp, ns='batch_pipeline_prod', client=exhausting_client())
    error = exhaust_run(A, 'batch_merge_commit', times=1)
    assert error.retry_after == pytest.approx(0.125)
    B = default_store(mp, ns='batch_pipeline_prod', client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(error.retry_after)


def test_g3_retry_after_stamp_batch_pipeline_prod_k1_j0p25(mp):
    """The exhaustion stamp equals the residual the sibling waits on the shared damper."""
    damper, clock = shared_damper('batch_pipeline_prod', jitter=0.25)
    A = default_store(mp, ns='batch_pipeline_prod', client=exhausting_client())
    error = exhaust_run(A, 'batch_merge_commit', times=1)
    assert error.retry_after == pytest.approx(0.15625)
    B = default_store(mp, ns='batch_pipeline_prod', client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(error.retry_after)


def test_g3_retry_after_stamp_batch_pipeline_prod_k1_j0p5(mp):
    """The exhaustion stamp equals the residual the sibling waits on the shared damper."""
    damper, clock = shared_damper('batch_pipeline_prod', jitter=0.5)
    A = default_store(mp, ns='batch_pipeline_prod', client=exhausting_client())
    error = exhaust_run(A, 'batch_merge_commit', times=1)
    assert error.retry_after == pytest.approx(0.1875)
    B = default_store(mp, ns='batch_pipeline_prod', client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(error.retry_after)


def test_g3_retry_after_stamp_batch_pipeline_prod_k1_j1p0(mp):
    """The exhaustion stamp equals the residual the sibling waits on the shared damper."""
    damper, clock = shared_damper('batch_pipeline_prod', jitter=1.0)
    A = default_store(mp, ns='batch_pipeline_prod', client=exhausting_client())
    error = exhaust_run(A, 'batch_merge_commit', times=1)
    assert error.retry_after == pytest.approx(0.25)
    B = default_store(mp, ns='batch_pipeline_prod', client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(error.retry_after)


def test_g3_retry_after_stamp_batch_pipeline_prod_k2_j0p0(mp):
    """The exhaustion stamp equals the residual the sibling waits on the shared damper."""
    damper, clock = shared_damper('batch_pipeline_prod', jitter=0.0)
    A = default_store(mp, ns='batch_pipeline_prod', client=exhausting_client())
    error = exhaust_run(A, 'batch_merge_commit', times=2)
    assert error.retry_after == pytest.approx(0.25)
    B = default_store(mp, ns='batch_pipeline_prod', client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(error.retry_after)


def test_g3_retry_after_stamp_batch_pipeline_prod_k2_j0p25(mp):
    """The exhaustion stamp equals the residual the sibling waits on the shared damper."""
    damper, clock = shared_damper('batch_pipeline_prod', jitter=0.25)
    A = default_store(mp, ns='batch_pipeline_prod', client=exhausting_client())
    error = exhaust_run(A, 'batch_merge_commit', times=2)
    assert error.retry_after == pytest.approx(0.3125)
    B = default_store(mp, ns='batch_pipeline_prod', client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(error.retry_after)


def test_g3_retry_after_stamp_batch_pipeline_prod_k2_j0p5(mp):
    """The exhaustion stamp equals the residual the sibling waits on the shared damper."""
    damper, clock = shared_damper('batch_pipeline_prod', jitter=0.5)
    A = default_store(mp, ns='batch_pipeline_prod', client=exhausting_client())
    error = exhaust_run(A, 'batch_merge_commit', times=2)
    assert error.retry_after == pytest.approx(0.375)
    B = default_store(mp, ns='batch_pipeline_prod', client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(error.retry_after)


def test_g3_retry_after_stamp_batch_pipeline_prod_k2_j1p0(mp):
    """The exhaustion stamp equals the residual the sibling waits on the shared damper."""
    damper, clock = shared_damper('batch_pipeline_prod', jitter=1.0)
    A = default_store(mp, ns='batch_pipeline_prod', client=exhausting_client())
    error = exhaust_run(A, 'batch_merge_commit', times=2)
    assert error.retry_after == pytest.approx(0.5)
    B = default_store(mp, ns='batch_pipeline_prod', client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(error.retry_after)


def test_g3_retry_after_stamp_batch_pipeline_prod_k3_j0p0(mp):
    """The exhaustion stamp equals the residual the sibling waits on the shared damper."""
    damper, clock = shared_damper('batch_pipeline_prod', jitter=0.0)
    A = default_store(mp, ns='batch_pipeline_prod', client=exhausting_client())
    error = exhaust_run(A, 'batch_merge_commit', times=3)
    assert error.retry_after == pytest.approx(0.5)
    B = default_store(mp, ns='batch_pipeline_prod', client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(error.retry_after)


def test_g3_retry_after_stamp_batch_pipeline_prod_k3_j0p25(mp):
    """The exhaustion stamp equals the residual the sibling waits on the shared damper."""
    damper, clock = shared_damper('batch_pipeline_prod', jitter=0.25)
    A = default_store(mp, ns='batch_pipeline_prod', client=exhausting_client())
    error = exhaust_run(A, 'batch_merge_commit', times=3)
    assert error.retry_after == pytest.approx(0.625)
    B = default_store(mp, ns='batch_pipeline_prod', client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(error.retry_after)


def test_g3_retry_after_stamp_batch_pipeline_prod_k3_j0p5(mp):
    """The exhaustion stamp equals the residual the sibling waits on the shared damper."""
    damper, clock = shared_damper('batch_pipeline_prod', jitter=0.5)
    A = default_store(mp, ns='batch_pipeline_prod', client=exhausting_client())
    error = exhaust_run(A, 'batch_merge_commit', times=3)
    assert error.retry_after == pytest.approx(0.75)
    B = default_store(mp, ns='batch_pipeline_prod', client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(error.retry_after)


def test_g3_retry_after_stamp_batch_pipeline_prod_k3_j1p0(mp):
    """The exhaustion stamp equals the residual the sibling waits on the shared damper."""
    damper, clock = shared_damper('batch_pipeline_prod', jitter=1.0)
    A = default_store(mp, ns='batch_pipeline_prod', client=exhausting_client())
    error = exhaust_run(A, 'batch_merge_commit', times=3)
    assert error.retry_after == pytest.approx(1.0)
    B = default_store(mp, ns='batch_pipeline_prod', client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(error.retry_after)


def test_g3_retry_after_stamp_batch_pipeline_prod_k4_j0p0(mp):
    """The exhaustion stamp equals the residual the sibling waits on the shared damper."""
    damper, clock = shared_damper('batch_pipeline_prod', jitter=0.0)
    A = default_store(mp, ns='batch_pipeline_prod', client=exhausting_client())
    error = exhaust_run(A, 'batch_merge_commit', times=4)
    assert error.retry_after == pytest.approx(1.0)
    B = default_store(mp, ns='batch_pipeline_prod', client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(error.retry_after)


def test_g3_retry_after_stamp_batch_pipeline_prod_k4_j0p25(mp):
    """The exhaustion stamp equals the residual the sibling waits on the shared damper."""
    damper, clock = shared_damper('batch_pipeline_prod', jitter=0.25)
    A = default_store(mp, ns='batch_pipeline_prod', client=exhausting_client())
    error = exhaust_run(A, 'batch_merge_commit', times=4)
    assert error.retry_after == pytest.approx(1.25)
    B = default_store(mp, ns='batch_pipeline_prod', client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(error.retry_after)


def test_g3_retry_after_stamp_batch_pipeline_prod_k4_j0p5(mp):
    """The exhaustion stamp equals the residual the sibling waits on the shared damper."""
    damper, clock = shared_damper('batch_pipeline_prod', jitter=0.5)
    A = default_store(mp, ns='batch_pipeline_prod', client=exhausting_client())
    error = exhaust_run(A, 'batch_merge_commit', times=4)
    assert error.retry_after == pytest.approx(1.5)
    B = default_store(mp, ns='batch_pipeline_prod', client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(error.retry_after)


def test_g3_retry_after_stamp_batch_pipeline_prod_k4_j1p0(mp):
    """The exhaustion stamp equals the residual the sibling waits on the shared damper."""
    damper, clock = shared_damper('batch_pipeline_prod', jitter=1.0)
    A = default_store(mp, ns='batch_pipeline_prod', client=exhausting_client())
    error = exhaust_run(A, 'batch_merge_commit', times=4)
    assert error.retry_after == pytest.approx(2.0)
    B = default_store(mp, ns='batch_pipeline_prod', client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(error.retry_after)


def test_g3_retry_after_stamp_batch_pipeline_prod_k5_j0p0(mp):
    """The exhaustion stamp equals the residual the sibling waits on the shared damper."""
    damper, clock = shared_damper('batch_pipeline_prod', jitter=0.0)
    A = default_store(mp, ns='batch_pipeline_prod', client=exhausting_client())
    error = exhaust_run(A, 'batch_merge_commit', times=5)
    assert error.retry_after == pytest.approx(2.0)
    B = default_store(mp, ns='batch_pipeline_prod', client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(error.retry_after)


def test_g3_retry_after_stamp_batch_pipeline_prod_k5_j0p25(mp):
    """The exhaustion stamp equals the residual the sibling waits on the shared damper."""
    damper, clock = shared_damper('batch_pipeline_prod', jitter=0.25)
    A = default_store(mp, ns='batch_pipeline_prod', client=exhausting_client())
    error = exhaust_run(A, 'batch_merge_commit', times=5)
    assert error.retry_after == pytest.approx(2.5)
    B = default_store(mp, ns='batch_pipeline_prod', client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(error.retry_after)


def test_g3_retry_after_stamp_batch_pipeline_prod_k5_j0p5(mp):
    """The exhaustion stamp equals the residual the sibling waits on the shared damper."""
    damper, clock = shared_damper('batch_pipeline_prod', jitter=0.5)
    A = default_store(mp, ns='batch_pipeline_prod', client=exhausting_client())
    error = exhaust_run(A, 'batch_merge_commit', times=5)
    assert error.retry_after == pytest.approx(3.0)
    B = default_store(mp, ns='batch_pipeline_prod', client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(error.retry_after)


def test_g3_retry_after_stamp_batch_pipeline_prod_k5_j1p0(mp):
    """The exhaustion stamp equals the residual the sibling waits on the shared damper."""
    damper, clock = shared_damper('batch_pipeline_prod', jitter=1.0)
    A = default_store(mp, ns='batch_pipeline_prod', client=exhausting_client())
    error = exhaust_run(A, 'batch_merge_commit', times=5)
    assert error.retry_after == pytest.approx(4.0)
    B = default_store(mp, ns='batch_pipeline_prod', client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(error.retry_after)


def test_g3_retry_after_stamp_batch_pipeline_prod_k6_j0p0(mp):
    """The exhaustion stamp equals the residual the sibling waits on the shared damper."""
    damper, clock = shared_damper('batch_pipeline_prod', jitter=0.0)
    A = default_store(mp, ns='batch_pipeline_prod', client=exhausting_client())
    error = exhaust_run(A, 'batch_merge_commit', times=6)
    assert error.retry_after == pytest.approx(2.0)
    B = default_store(mp, ns='batch_pipeline_prod', client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(error.retry_after)


def test_g3_retry_after_stamp_batch_pipeline_prod_k6_j0p25(mp):
    """The exhaustion stamp equals the residual the sibling waits on the shared damper."""
    damper, clock = shared_damper('batch_pipeline_prod', jitter=0.25)
    A = default_store(mp, ns='batch_pipeline_prod', client=exhausting_client())
    error = exhaust_run(A, 'batch_merge_commit', times=6)
    assert error.retry_after == pytest.approx(2.5)
    B = default_store(mp, ns='batch_pipeline_prod', client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(error.retry_after)


def test_g3_retry_after_stamp_batch_pipeline_prod_k6_j0p5(mp):
    """The exhaustion stamp equals the residual the sibling waits on the shared damper."""
    damper, clock = shared_damper('batch_pipeline_prod', jitter=0.5)
    A = default_store(mp, ns='batch_pipeline_prod', client=exhausting_client())
    error = exhaust_run(A, 'batch_merge_commit', times=6)
    assert error.retry_after == pytest.approx(3.0)
    B = default_store(mp, ns='batch_pipeline_prod', client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(error.retry_after)


def test_g3_retry_after_stamp_batch_pipeline_prod_k6_j1p0(mp):
    """The exhaustion stamp equals the residual the sibling waits on the shared damper."""
    damper, clock = shared_damper('batch_pipeline_prod', jitter=1.0)
    A = default_store(mp, ns='batch_pipeline_prod', client=exhausting_client())
    error = exhaust_run(A, 'batch_merge_commit', times=6)
    assert error.retry_after == pytest.approx(4.0)
    B = default_store(mp, ns='batch_pipeline_prod', client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(error.retry_after)


def test_g3_retry_after_stamp_batch_pipeline_prod_k7_j0p0(mp):
    """The exhaustion stamp equals the residual the sibling waits on the shared damper."""
    damper, clock = shared_damper('batch_pipeline_prod', jitter=0.0)
    A = default_store(mp, ns='batch_pipeline_prod', client=exhausting_client())
    error = exhaust_run(A, 'batch_merge_commit', times=7)
    assert error.retry_after == pytest.approx(2.0)
    B = default_store(mp, ns='batch_pipeline_prod', client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(error.retry_after)


def test_g3_retry_after_stamp_batch_pipeline_prod_k7_j0p25(mp):
    """The exhaustion stamp equals the residual the sibling waits on the shared damper."""
    damper, clock = shared_damper('batch_pipeline_prod', jitter=0.25)
    A = default_store(mp, ns='batch_pipeline_prod', client=exhausting_client())
    error = exhaust_run(A, 'batch_merge_commit', times=7)
    assert error.retry_after == pytest.approx(2.5)
    B = default_store(mp, ns='batch_pipeline_prod', client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(error.retry_after)


def test_g3_retry_after_stamp_batch_pipeline_prod_k7_j0p5(mp):
    """The exhaustion stamp equals the residual the sibling waits on the shared damper."""
    damper, clock = shared_damper('batch_pipeline_prod', jitter=0.5)
    A = default_store(mp, ns='batch_pipeline_prod', client=exhausting_client())
    error = exhaust_run(A, 'batch_merge_commit', times=7)
    assert error.retry_after == pytest.approx(3.0)
    B = default_store(mp, ns='batch_pipeline_prod', client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(error.retry_after)


def test_g3_retry_after_stamp_batch_pipeline_prod_k7_j1p0(mp):
    """The exhaustion stamp equals the residual the sibling waits on the shared damper."""
    damper, clock = shared_damper('batch_pipeline_prod', jitter=1.0)
    A = default_store(mp, ns='batch_pipeline_prod', client=exhausting_client())
    error = exhaust_run(A, 'batch_merge_commit', times=7)
    assert error.retry_after == pytest.approx(4.0)
    B = default_store(mp, ns='batch_pipeline_prod', client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(error.retry_after)


def test_g3_retry_after_stamp_batch_pipeline_prod_k8_j0p0(mp):
    """The exhaustion stamp equals the residual the sibling waits on the shared damper."""
    damper, clock = shared_damper('batch_pipeline_prod', jitter=0.0)
    A = default_store(mp, ns='batch_pipeline_prod', client=exhausting_client())
    error = exhaust_run(A, 'batch_merge_commit', times=8)
    assert error.retry_after == pytest.approx(2.0)
    B = default_store(mp, ns='batch_pipeline_prod', client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(error.retry_after)


def test_g3_retry_after_stamp_batch_pipeline_prod_k8_j0p25(mp):
    """The exhaustion stamp equals the residual the sibling waits on the shared damper."""
    damper, clock = shared_damper('batch_pipeline_prod', jitter=0.25)
    A = default_store(mp, ns='batch_pipeline_prod', client=exhausting_client())
    error = exhaust_run(A, 'batch_merge_commit', times=8)
    assert error.retry_after == pytest.approx(2.5)
    B = default_store(mp, ns='batch_pipeline_prod', client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(error.retry_after)


def test_g3_retry_after_stamp_batch_pipeline_prod_k8_j0p5(mp):
    """The exhaustion stamp equals the residual the sibling waits on the shared damper."""
    damper, clock = shared_damper('batch_pipeline_prod', jitter=0.5)
    A = default_store(mp, ns='batch_pipeline_prod', client=exhausting_client())
    error = exhaust_run(A, 'batch_merge_commit', times=8)
    assert error.retry_after == pytest.approx(3.0)
    B = default_store(mp, ns='batch_pipeline_prod', client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(error.retry_after)


def test_g3_retry_after_stamp_batch_pipeline_prod_k8_j1p0(mp):
    """The exhaustion stamp equals the residual the sibling waits on the shared damper."""
    damper, clock = shared_damper('batch_pipeline_prod', jitter=1.0)
    A = default_store(mp, ns='batch_pipeline_prod', client=exhausting_client())
    error = exhaust_run(A, 'batch_merge_commit', times=8)
    assert error.retry_after == pytest.approx(4.0)
    B = default_store(mp, ns='batch_pipeline_prod', client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(error.retry_after)


def test_g3_retry_after_stamp_batch_pipeline_prod_k9_j0p0(mp):
    """The exhaustion stamp equals the residual the sibling waits on the shared damper."""
    damper, clock = shared_damper('batch_pipeline_prod', jitter=0.0)
    A = default_store(mp, ns='batch_pipeline_prod', client=exhausting_client())
    error = exhaust_run(A, 'batch_merge_commit', times=9)
    assert error.retry_after == pytest.approx(2.0)
    B = default_store(mp, ns='batch_pipeline_prod', client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(error.retry_after)


def test_g3_retry_after_stamp_batch_pipeline_prod_k9_j0p25(mp):
    """The exhaustion stamp equals the residual the sibling waits on the shared damper."""
    damper, clock = shared_damper('batch_pipeline_prod', jitter=0.25)
    A = default_store(mp, ns='batch_pipeline_prod', client=exhausting_client())
    error = exhaust_run(A, 'batch_merge_commit', times=9)
    assert error.retry_after == pytest.approx(2.5)
    B = default_store(mp, ns='batch_pipeline_prod', client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(error.retry_after)


def test_g3_retry_after_stamp_batch_pipeline_prod_k9_j0p5(mp):
    """The exhaustion stamp equals the residual the sibling waits on the shared damper."""
    damper, clock = shared_damper('batch_pipeline_prod', jitter=0.5)
    A = default_store(mp, ns='batch_pipeline_prod', client=exhausting_client())
    error = exhaust_run(A, 'batch_merge_commit', times=9)
    assert error.retry_after == pytest.approx(3.0)
    B = default_store(mp, ns='batch_pipeline_prod', client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(error.retry_after)


def test_g3_retry_after_stamp_batch_pipeline_prod_k9_j1p0(mp):
    """The exhaustion stamp equals the residual the sibling waits on the shared damper."""
    damper, clock = shared_damper('batch_pipeline_prod', jitter=1.0)
    A = default_store(mp, ns='batch_pipeline_prod', client=exhausting_client())
    error = exhaust_run(A, 'batch_merge_commit', times=9)
    assert error.retry_after == pytest.approx(4.0)
    B = default_store(mp, ns='batch_pipeline_prod', client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(error.retry_after)


def test_g3_retry_after_stamp_batch_pipeline_prod_k10_j0p0(mp):
    """The exhaustion stamp equals the residual the sibling waits on the shared damper."""
    damper, clock = shared_damper('batch_pipeline_prod', jitter=0.0)
    A = default_store(mp, ns='batch_pipeline_prod', client=exhausting_client())
    error = exhaust_run(A, 'batch_merge_commit', times=10)
    assert error.retry_after == pytest.approx(2.0)
    B = default_store(mp, ns='batch_pipeline_prod', client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(error.retry_after)


def test_g3_retry_after_stamp_batch_pipeline_prod_k10_j0p25(mp):
    """The exhaustion stamp equals the residual the sibling waits on the shared damper."""
    damper, clock = shared_damper('batch_pipeline_prod', jitter=0.25)
    A = default_store(mp, ns='batch_pipeline_prod', client=exhausting_client())
    error = exhaust_run(A, 'batch_merge_commit', times=10)
    assert error.retry_after == pytest.approx(2.5)
    B = default_store(mp, ns='batch_pipeline_prod', client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(error.retry_after)


def test_g3_retry_after_stamp_batch_pipeline_prod_k10_j0p5(mp):
    """The exhaustion stamp equals the residual the sibling waits on the shared damper."""
    damper, clock = shared_damper('batch_pipeline_prod', jitter=0.5)
    A = default_store(mp, ns='batch_pipeline_prod', client=exhausting_client())
    error = exhaust_run(A, 'batch_merge_commit', times=10)
    assert error.retry_after == pytest.approx(3.0)
    B = default_store(mp, ns='batch_pipeline_prod', client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(error.retry_after)


def test_g3_retry_after_stamp_batch_pipeline_prod_k10_j1p0(mp):
    """The exhaustion stamp equals the residual the sibling waits on the shared damper."""
    damper, clock = shared_damper('batch_pipeline_prod', jitter=1.0)
    A = default_store(mp, ns='batch_pipeline_prod', client=exhausting_client())
    error = exhaust_run(A, 'batch_merge_commit', times=10)
    assert error.retry_after == pytest.approx(4.0)
    B = default_store(mp, ns='batch_pipeline_prod', client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(error.retry_after)


def test_g3_retry_after_stamp_batch_pipeline_test_unit_k1_j0p0(mp):
    """The exhaustion stamp equals the residual the sibling waits on the shared damper."""
    damper, clock = shared_damper('batch_pipeline_test_unit', jitter=0.0)
    A = default_store(mp, ns='batch_pipeline_test_unit', client=exhausting_client())
    error = exhaust_run(A, 'batch_merge_commit', times=1)
    assert error.retry_after == pytest.approx(0.125)
    B = default_store(mp, ns='batch_pipeline_test_unit', client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(error.retry_after)


def test_g3_retry_after_stamp_batch_pipeline_test_unit_k1_j0p25(mp):
    """The exhaustion stamp equals the residual the sibling waits on the shared damper."""
    damper, clock = shared_damper('batch_pipeline_test_unit', jitter=0.25)
    A = default_store(mp, ns='batch_pipeline_test_unit', client=exhausting_client())
    error = exhaust_run(A, 'batch_merge_commit', times=1)
    assert error.retry_after == pytest.approx(0.15625)
    B = default_store(mp, ns='batch_pipeline_test_unit', client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(error.retry_after)


def test_g3_retry_after_stamp_batch_pipeline_test_unit_k1_j0p5(mp):
    """The exhaustion stamp equals the residual the sibling waits on the shared damper."""
    damper, clock = shared_damper('batch_pipeline_test_unit', jitter=0.5)
    A = default_store(mp, ns='batch_pipeline_test_unit', client=exhausting_client())
    error = exhaust_run(A, 'batch_merge_commit', times=1)
    assert error.retry_after == pytest.approx(0.1875)
    B = default_store(mp, ns='batch_pipeline_test_unit', client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(error.retry_after)


def test_g3_retry_after_stamp_batch_pipeline_test_unit_k1_j1p0(mp):
    """The exhaustion stamp equals the residual the sibling waits on the shared damper."""
    damper, clock = shared_damper('batch_pipeline_test_unit', jitter=1.0)
    A = default_store(mp, ns='batch_pipeline_test_unit', client=exhausting_client())
    error = exhaust_run(A, 'batch_merge_commit', times=1)
    assert error.retry_after == pytest.approx(0.25)
    B = default_store(mp, ns='batch_pipeline_test_unit', client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(error.retry_after)


def test_g3_retry_after_stamp_batch_pipeline_test_unit_k2_j0p0(mp):
    """The exhaustion stamp equals the residual the sibling waits on the shared damper."""
    damper, clock = shared_damper('batch_pipeline_test_unit', jitter=0.0)
    A = default_store(mp, ns='batch_pipeline_test_unit', client=exhausting_client())
    error = exhaust_run(A, 'batch_merge_commit', times=2)
    assert error.retry_after == pytest.approx(0.25)
    B = default_store(mp, ns='batch_pipeline_test_unit', client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(error.retry_after)


def test_g3_retry_after_stamp_batch_pipeline_test_unit_k2_j0p25(mp):
    """The exhaustion stamp equals the residual the sibling waits on the shared damper."""
    damper, clock = shared_damper('batch_pipeline_test_unit', jitter=0.25)
    A = default_store(mp, ns='batch_pipeline_test_unit', client=exhausting_client())
    error = exhaust_run(A, 'batch_merge_commit', times=2)
    assert error.retry_after == pytest.approx(0.3125)
    B = default_store(mp, ns='batch_pipeline_test_unit', client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(error.retry_after)


def test_g3_retry_after_stamp_batch_pipeline_test_unit_k2_j0p5(mp):
    """The exhaustion stamp equals the residual the sibling waits on the shared damper."""
    damper, clock = shared_damper('batch_pipeline_test_unit', jitter=0.5)
    A = default_store(mp, ns='batch_pipeline_test_unit', client=exhausting_client())
    error = exhaust_run(A, 'batch_merge_commit', times=2)
    assert error.retry_after == pytest.approx(0.375)
    B = default_store(mp, ns='batch_pipeline_test_unit', client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(error.retry_after)


def test_g3_retry_after_stamp_batch_pipeline_test_unit_k2_j1p0(mp):
    """The exhaustion stamp equals the residual the sibling waits on the shared damper."""
    damper, clock = shared_damper('batch_pipeline_test_unit', jitter=1.0)
    A = default_store(mp, ns='batch_pipeline_test_unit', client=exhausting_client())
    error = exhaust_run(A, 'batch_merge_commit', times=2)
    assert error.retry_after == pytest.approx(0.5)
    B = default_store(mp, ns='batch_pipeline_test_unit', client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(error.retry_after)


def test_g3_retry_after_stamp_batch_pipeline_test_unit_k3_j0p0(mp):
    """The exhaustion stamp equals the residual the sibling waits on the shared damper."""
    damper, clock = shared_damper('batch_pipeline_test_unit', jitter=0.0)
    A = default_store(mp, ns='batch_pipeline_test_unit', client=exhausting_client())
    error = exhaust_run(A, 'batch_merge_commit', times=3)
    assert error.retry_after == pytest.approx(0.5)
    B = default_store(mp, ns='batch_pipeline_test_unit', client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(error.retry_after)


def test_g3_retry_after_stamp_batch_pipeline_test_unit_k3_j0p25(mp):
    """The exhaustion stamp equals the residual the sibling waits on the shared damper."""
    damper, clock = shared_damper('batch_pipeline_test_unit', jitter=0.25)
    A = default_store(mp, ns='batch_pipeline_test_unit', client=exhausting_client())
    error = exhaust_run(A, 'batch_merge_commit', times=3)
    assert error.retry_after == pytest.approx(0.625)
    B = default_store(mp, ns='batch_pipeline_test_unit', client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(error.retry_after)


def test_g3_retry_after_stamp_batch_pipeline_test_unit_k3_j0p5(mp):
    """The exhaustion stamp equals the residual the sibling waits on the shared damper."""
    damper, clock = shared_damper('batch_pipeline_test_unit', jitter=0.5)
    A = default_store(mp, ns='batch_pipeline_test_unit', client=exhausting_client())
    error = exhaust_run(A, 'batch_merge_commit', times=3)
    assert error.retry_after == pytest.approx(0.75)
    B = default_store(mp, ns='batch_pipeline_test_unit', client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(error.retry_after)


def test_g3_retry_after_stamp_batch_pipeline_test_unit_k3_j1p0(mp):
    """The exhaustion stamp equals the residual the sibling waits on the shared damper."""
    damper, clock = shared_damper('batch_pipeline_test_unit', jitter=1.0)
    A = default_store(mp, ns='batch_pipeline_test_unit', client=exhausting_client())
    error = exhaust_run(A, 'batch_merge_commit', times=3)
    assert error.retry_after == pytest.approx(1.0)
    B = default_store(mp, ns='batch_pipeline_test_unit', client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(error.retry_after)


def test_g3_retry_after_stamp_batch_pipeline_test_unit_k4_j0p0(mp):
    """The exhaustion stamp equals the residual the sibling waits on the shared damper."""
    damper, clock = shared_damper('batch_pipeline_test_unit', jitter=0.0)
    A = default_store(mp, ns='batch_pipeline_test_unit', client=exhausting_client())
    error = exhaust_run(A, 'batch_merge_commit', times=4)
    assert error.retry_after == pytest.approx(1.0)
    B = default_store(mp, ns='batch_pipeline_test_unit', client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(error.retry_after)


def test_g3_retry_after_stamp_batch_pipeline_test_unit_k4_j0p25(mp):
    """The exhaustion stamp equals the residual the sibling waits on the shared damper."""
    damper, clock = shared_damper('batch_pipeline_test_unit', jitter=0.25)
    A = default_store(mp, ns='batch_pipeline_test_unit', client=exhausting_client())
    error = exhaust_run(A, 'batch_merge_commit', times=4)
    assert error.retry_after == pytest.approx(1.25)
    B = default_store(mp, ns='batch_pipeline_test_unit', client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(error.retry_after)


def test_g3_retry_after_stamp_batch_pipeline_test_unit_k4_j0p5(mp):
    """The exhaustion stamp equals the residual the sibling waits on the shared damper."""
    damper, clock = shared_damper('batch_pipeline_test_unit', jitter=0.5)
    A = default_store(mp, ns='batch_pipeline_test_unit', client=exhausting_client())
    error = exhaust_run(A, 'batch_merge_commit', times=4)
    assert error.retry_after == pytest.approx(1.5)
    B = default_store(mp, ns='batch_pipeline_test_unit', client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(error.retry_after)


def test_g3_retry_after_stamp_batch_pipeline_test_unit_k4_j1p0(mp):
    """The exhaustion stamp equals the residual the sibling waits on the shared damper."""
    damper, clock = shared_damper('batch_pipeline_test_unit', jitter=1.0)
    A = default_store(mp, ns='batch_pipeline_test_unit', client=exhausting_client())
    error = exhaust_run(A, 'batch_merge_commit', times=4)
    assert error.retry_after == pytest.approx(2.0)
    B = default_store(mp, ns='batch_pipeline_test_unit', client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(error.retry_after)


def test_g3_retry_after_stamp_batch_pipeline_test_unit_k5_j0p0(mp):
    """The exhaustion stamp equals the residual the sibling waits on the shared damper."""
    damper, clock = shared_damper('batch_pipeline_test_unit', jitter=0.0)
    A = default_store(mp, ns='batch_pipeline_test_unit', client=exhausting_client())
    error = exhaust_run(A, 'batch_merge_commit', times=5)
    assert error.retry_after == pytest.approx(2.0)
    B = default_store(mp, ns='batch_pipeline_test_unit', client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(error.retry_after)


def test_g3_retry_after_stamp_batch_pipeline_test_unit_k5_j0p25(mp):
    """The exhaustion stamp equals the residual the sibling waits on the shared damper."""
    damper, clock = shared_damper('batch_pipeline_test_unit', jitter=0.25)
    A = default_store(mp, ns='batch_pipeline_test_unit', client=exhausting_client())
    error = exhaust_run(A, 'batch_merge_commit', times=5)
    assert error.retry_after == pytest.approx(2.5)
    B = default_store(mp, ns='batch_pipeline_test_unit', client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(error.retry_after)


def test_g3_retry_after_stamp_batch_pipeline_test_unit_k5_j0p5(mp):
    """The exhaustion stamp equals the residual the sibling waits on the shared damper."""
    damper, clock = shared_damper('batch_pipeline_test_unit', jitter=0.5)
    A = default_store(mp, ns='batch_pipeline_test_unit', client=exhausting_client())
    error = exhaust_run(A, 'batch_merge_commit', times=5)
    assert error.retry_after == pytest.approx(3.0)
    B = default_store(mp, ns='batch_pipeline_test_unit', client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(error.retry_after)


def test_g3_retry_after_stamp_batch_pipeline_test_unit_k5_j1p0(mp):
    """The exhaustion stamp equals the residual the sibling waits on the shared damper."""
    damper, clock = shared_damper('batch_pipeline_test_unit', jitter=1.0)
    A = default_store(mp, ns='batch_pipeline_test_unit', client=exhausting_client())
    error = exhaust_run(A, 'batch_merge_commit', times=5)
    assert error.retry_after == pytest.approx(4.0)
    B = default_store(mp, ns='batch_pipeline_test_unit', client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(error.retry_after)


def test_g3_retry_after_stamp_batch_pipeline_test_unit_k6_j0p0(mp):
    """The exhaustion stamp equals the residual the sibling waits on the shared damper."""
    damper, clock = shared_damper('batch_pipeline_test_unit', jitter=0.0)
    A = default_store(mp, ns='batch_pipeline_test_unit', client=exhausting_client())
    error = exhaust_run(A, 'batch_merge_commit', times=6)
    assert error.retry_after == pytest.approx(2.0)
    B = default_store(mp, ns='batch_pipeline_test_unit', client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(error.retry_after)


def test_g3_retry_after_stamp_batch_pipeline_test_unit_k6_j0p25(mp):
    """The exhaustion stamp equals the residual the sibling waits on the shared damper."""
    damper, clock = shared_damper('batch_pipeline_test_unit', jitter=0.25)
    A = default_store(mp, ns='batch_pipeline_test_unit', client=exhausting_client())
    error = exhaust_run(A, 'batch_merge_commit', times=6)
    assert error.retry_after == pytest.approx(2.5)
    B = default_store(mp, ns='batch_pipeline_test_unit', client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(error.retry_after)


def test_g3_retry_after_stamp_batch_pipeline_test_unit_k6_j0p5(mp):
    """The exhaustion stamp equals the residual the sibling waits on the shared damper."""
    damper, clock = shared_damper('batch_pipeline_test_unit', jitter=0.5)
    A = default_store(mp, ns='batch_pipeline_test_unit', client=exhausting_client())
    error = exhaust_run(A, 'batch_merge_commit', times=6)
    assert error.retry_after == pytest.approx(3.0)
    B = default_store(mp, ns='batch_pipeline_test_unit', client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(error.retry_after)


def test_g3_retry_after_stamp_batch_pipeline_test_unit_k6_j1p0(mp):
    """The exhaustion stamp equals the residual the sibling waits on the shared damper."""
    damper, clock = shared_damper('batch_pipeline_test_unit', jitter=1.0)
    A = default_store(mp, ns='batch_pipeline_test_unit', client=exhausting_client())
    error = exhaust_run(A, 'batch_merge_commit', times=6)
    assert error.retry_after == pytest.approx(4.0)
    B = default_store(mp, ns='batch_pipeline_test_unit', client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(error.retry_after)


def test_g3_retry_after_stamp_batch_pipeline_test_unit_k7_j0p0(mp):
    """The exhaustion stamp equals the residual the sibling waits on the shared damper."""
    damper, clock = shared_damper('batch_pipeline_test_unit', jitter=0.0)
    A = default_store(mp, ns='batch_pipeline_test_unit', client=exhausting_client())
    error = exhaust_run(A, 'batch_merge_commit', times=7)
    assert error.retry_after == pytest.approx(2.0)
    B = default_store(mp, ns='batch_pipeline_test_unit', client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(error.retry_after)


def test_g3_retry_after_stamp_batch_pipeline_test_unit_k7_j0p25(mp):
    """The exhaustion stamp equals the residual the sibling waits on the shared damper."""
    damper, clock = shared_damper('batch_pipeline_test_unit', jitter=0.25)
    A = default_store(mp, ns='batch_pipeline_test_unit', client=exhausting_client())
    error = exhaust_run(A, 'batch_merge_commit', times=7)
    assert error.retry_after == pytest.approx(2.5)
    B = default_store(mp, ns='batch_pipeline_test_unit', client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(error.retry_after)


def test_g3_retry_after_stamp_batch_pipeline_test_unit_k7_j0p5(mp):
    """The exhaustion stamp equals the residual the sibling waits on the shared damper."""
    damper, clock = shared_damper('batch_pipeline_test_unit', jitter=0.5)
    A = default_store(mp, ns='batch_pipeline_test_unit', client=exhausting_client())
    error = exhaust_run(A, 'batch_merge_commit', times=7)
    assert error.retry_after == pytest.approx(3.0)
    B = default_store(mp, ns='batch_pipeline_test_unit', client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(error.retry_after)


def test_g3_retry_after_stamp_batch_pipeline_test_unit_k7_j1p0(mp):
    """The exhaustion stamp equals the residual the sibling waits on the shared damper."""
    damper, clock = shared_damper('batch_pipeline_test_unit', jitter=1.0)
    A = default_store(mp, ns='batch_pipeline_test_unit', client=exhausting_client())
    error = exhaust_run(A, 'batch_merge_commit', times=7)
    assert error.retry_after == pytest.approx(4.0)
    B = default_store(mp, ns='batch_pipeline_test_unit', client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(error.retry_after)


def test_g3_retry_after_stamp_batch_pipeline_test_unit_k8_j0p0(mp):
    """The exhaustion stamp equals the residual the sibling waits on the shared damper."""
    damper, clock = shared_damper('batch_pipeline_test_unit', jitter=0.0)
    A = default_store(mp, ns='batch_pipeline_test_unit', client=exhausting_client())
    error = exhaust_run(A, 'batch_merge_commit', times=8)
    assert error.retry_after == pytest.approx(2.0)
    B = default_store(mp, ns='batch_pipeline_test_unit', client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(error.retry_after)


def test_g3_retry_after_stamp_batch_pipeline_test_unit_k8_j0p25(mp):
    """The exhaustion stamp equals the residual the sibling waits on the shared damper."""
    damper, clock = shared_damper('batch_pipeline_test_unit', jitter=0.25)
    A = default_store(mp, ns='batch_pipeline_test_unit', client=exhausting_client())
    error = exhaust_run(A, 'batch_merge_commit', times=8)
    assert error.retry_after == pytest.approx(2.5)
    B = default_store(mp, ns='batch_pipeline_test_unit', client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(error.retry_after)


def test_g3_retry_after_stamp_batch_pipeline_test_unit_k8_j0p5(mp):
    """The exhaustion stamp equals the residual the sibling waits on the shared damper."""
    damper, clock = shared_damper('batch_pipeline_test_unit', jitter=0.5)
    A = default_store(mp, ns='batch_pipeline_test_unit', client=exhausting_client())
    error = exhaust_run(A, 'batch_merge_commit', times=8)
    assert error.retry_after == pytest.approx(3.0)
    B = default_store(mp, ns='batch_pipeline_test_unit', client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(error.retry_after)


def test_g3_retry_after_stamp_batch_pipeline_test_unit_k8_j1p0(mp):
    """The exhaustion stamp equals the residual the sibling waits on the shared damper."""
    damper, clock = shared_damper('batch_pipeline_test_unit', jitter=1.0)
    A = default_store(mp, ns='batch_pipeline_test_unit', client=exhausting_client())
    error = exhaust_run(A, 'batch_merge_commit', times=8)
    assert error.retry_after == pytest.approx(4.0)
    B = default_store(mp, ns='batch_pipeline_test_unit', client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(error.retry_after)


def test_g3_retry_after_stamp_batch_pipeline_test_unit_k9_j0p0(mp):
    """The exhaustion stamp equals the residual the sibling waits on the shared damper."""
    damper, clock = shared_damper('batch_pipeline_test_unit', jitter=0.0)
    A = default_store(mp, ns='batch_pipeline_test_unit', client=exhausting_client())
    error = exhaust_run(A, 'batch_merge_commit', times=9)
    assert error.retry_after == pytest.approx(2.0)
    B = default_store(mp, ns='batch_pipeline_test_unit', client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(error.retry_after)


def test_g3_retry_after_stamp_batch_pipeline_test_unit_k9_j0p25(mp):
    """The exhaustion stamp equals the residual the sibling waits on the shared damper."""
    damper, clock = shared_damper('batch_pipeline_test_unit', jitter=0.25)
    A = default_store(mp, ns='batch_pipeline_test_unit', client=exhausting_client())
    error = exhaust_run(A, 'batch_merge_commit', times=9)
    assert error.retry_after == pytest.approx(2.5)
    B = default_store(mp, ns='batch_pipeline_test_unit', client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(error.retry_after)


def test_g3_retry_after_stamp_batch_pipeline_test_unit_k9_j0p5(mp):
    """The exhaustion stamp equals the residual the sibling waits on the shared damper."""
    damper, clock = shared_damper('batch_pipeline_test_unit', jitter=0.5)
    A = default_store(mp, ns='batch_pipeline_test_unit', client=exhausting_client())
    error = exhaust_run(A, 'batch_merge_commit', times=9)
    assert error.retry_after == pytest.approx(3.0)
    B = default_store(mp, ns='batch_pipeline_test_unit', client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(error.retry_after)


def test_g3_retry_after_stamp_batch_pipeline_test_unit_k9_j1p0(mp):
    """The exhaustion stamp equals the residual the sibling waits on the shared damper."""
    damper, clock = shared_damper('batch_pipeline_test_unit', jitter=1.0)
    A = default_store(mp, ns='batch_pipeline_test_unit', client=exhausting_client())
    error = exhaust_run(A, 'batch_merge_commit', times=9)
    assert error.retry_after == pytest.approx(4.0)
    B = default_store(mp, ns='batch_pipeline_test_unit', client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(error.retry_after)


def test_g3_retry_after_stamp_batch_pipeline_test_unit_k10_j0p0(mp):
    """The exhaustion stamp equals the residual the sibling waits on the shared damper."""
    damper, clock = shared_damper('batch_pipeline_test_unit', jitter=0.0)
    A = default_store(mp, ns='batch_pipeline_test_unit', client=exhausting_client())
    error = exhaust_run(A, 'batch_merge_commit', times=10)
    assert error.retry_after == pytest.approx(2.0)
    B = default_store(mp, ns='batch_pipeline_test_unit', client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(error.retry_after)


def test_g3_retry_after_stamp_batch_pipeline_test_unit_k10_j0p25(mp):
    """The exhaustion stamp equals the residual the sibling waits on the shared damper."""
    damper, clock = shared_damper('batch_pipeline_test_unit', jitter=0.25)
    A = default_store(mp, ns='batch_pipeline_test_unit', client=exhausting_client())
    error = exhaust_run(A, 'batch_merge_commit', times=10)
    assert error.retry_after == pytest.approx(2.5)
    B = default_store(mp, ns='batch_pipeline_test_unit', client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(error.retry_after)


def test_g3_retry_after_stamp_batch_pipeline_test_unit_k10_j0p5(mp):
    """The exhaustion stamp equals the residual the sibling waits on the shared damper."""
    damper, clock = shared_damper('batch_pipeline_test_unit', jitter=0.5)
    A = default_store(mp, ns='batch_pipeline_test_unit', client=exhausting_client())
    error = exhaust_run(A, 'batch_merge_commit', times=10)
    assert error.retry_after == pytest.approx(3.0)
    B = default_store(mp, ns='batch_pipeline_test_unit', client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(error.retry_after)


def test_g3_retry_after_stamp_batch_pipeline_test_unit_k10_j1p0(mp):
    """The exhaustion stamp equals the residual the sibling waits on the shared damper."""
    damper, clock = shared_damper('batch_pipeline_test_unit', jitter=1.0)
    A = default_store(mp, ns='batch_pipeline_test_unit', client=exhausting_client())
    error = exhaust_run(A, 'batch_merge_commit', times=10)
    assert error.retry_after == pytest.approx(4.0)
    B = default_store(mp, ns='batch_pipeline_test_unit', client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(error.retry_after)


def test_g4_ns_isolation_batch_pipeline_dev_to_batch_pipeline_prod_k1_j0p0(mp):
    """A window in one namespace never damps a sibling namespace."""
    damper_a, clock_a = shared_damper('batch_pipeline_dev', jitter=0.0)
    damper_b, clock_b = shared_damper('batch_pipeline_prod', jitter=0.0)
    A = default_store(mp, ns='batch_pipeline_dev', client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=1)
    B = default_store(mp, ns='batch_pipeline_prod', client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock_b.sleeps == []
    assert damper_a is not damper_b
    assert damper_b._generations == {}


def test_g4_ns_isolation_batch_pipeline_dev_to_batch_pipeline_prod_k1_j0p25(mp):
    """A window in one namespace never damps a sibling namespace."""
    damper_a, clock_a = shared_damper('batch_pipeline_dev', jitter=0.25)
    damper_b, clock_b = shared_damper('batch_pipeline_prod', jitter=0.0)
    A = default_store(mp, ns='batch_pipeline_dev', client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=1)
    B = default_store(mp, ns='batch_pipeline_prod', client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock_b.sleeps == []
    assert damper_a is not damper_b
    assert damper_b._generations == {}


def test_g4_ns_isolation_batch_pipeline_dev_to_batch_pipeline_prod_k1_j0p5(mp):
    """A window in one namespace never damps a sibling namespace."""
    damper_a, clock_a = shared_damper('batch_pipeline_dev', jitter=0.5)
    damper_b, clock_b = shared_damper('batch_pipeline_prod', jitter=0.0)
    A = default_store(mp, ns='batch_pipeline_dev', client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=1)
    B = default_store(mp, ns='batch_pipeline_prod', client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock_b.sleeps == []
    assert damper_a is not damper_b
    assert damper_b._generations == {}


def test_g4_ns_isolation_batch_pipeline_dev_to_batch_pipeline_prod_k1_j1p0(mp):
    """A window in one namespace never damps a sibling namespace."""
    damper_a, clock_a = shared_damper('batch_pipeline_dev', jitter=1.0)
    damper_b, clock_b = shared_damper('batch_pipeline_prod', jitter=0.0)
    A = default_store(mp, ns='batch_pipeline_dev', client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=1)
    B = default_store(mp, ns='batch_pipeline_prod', client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock_b.sleeps == []
    assert damper_a is not damper_b
    assert damper_b._generations == {}


def test_g4_ns_isolation_batch_pipeline_dev_to_batch_pipeline_prod_k2_j0p0(mp):
    """A window in one namespace never damps a sibling namespace."""
    damper_a, clock_a = shared_damper('batch_pipeline_dev', jitter=0.0)
    damper_b, clock_b = shared_damper('batch_pipeline_prod', jitter=0.0)
    A = default_store(mp, ns='batch_pipeline_dev', client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=2)
    B = default_store(mp, ns='batch_pipeline_prod', client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock_b.sleeps == []
    assert damper_a is not damper_b
    assert damper_b._generations == {}


def test_g4_ns_isolation_batch_pipeline_dev_to_batch_pipeline_prod_k2_j0p25(mp):
    """A window in one namespace never damps a sibling namespace."""
    damper_a, clock_a = shared_damper('batch_pipeline_dev', jitter=0.25)
    damper_b, clock_b = shared_damper('batch_pipeline_prod', jitter=0.0)
    A = default_store(mp, ns='batch_pipeline_dev', client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=2)
    B = default_store(mp, ns='batch_pipeline_prod', client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock_b.sleeps == []
    assert damper_a is not damper_b
    assert damper_b._generations == {}


def test_g4_ns_isolation_batch_pipeline_dev_to_batch_pipeline_prod_k2_j0p5(mp):
    """A window in one namespace never damps a sibling namespace."""
    damper_a, clock_a = shared_damper('batch_pipeline_dev', jitter=0.5)
    damper_b, clock_b = shared_damper('batch_pipeline_prod', jitter=0.0)
    A = default_store(mp, ns='batch_pipeline_dev', client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=2)
    B = default_store(mp, ns='batch_pipeline_prod', client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock_b.sleeps == []
    assert damper_a is not damper_b
    assert damper_b._generations == {}


def test_g4_ns_isolation_batch_pipeline_dev_to_batch_pipeline_prod_k2_j1p0(mp):
    """A window in one namespace never damps a sibling namespace."""
    damper_a, clock_a = shared_damper('batch_pipeline_dev', jitter=1.0)
    damper_b, clock_b = shared_damper('batch_pipeline_prod', jitter=0.0)
    A = default_store(mp, ns='batch_pipeline_dev', client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=2)
    B = default_store(mp, ns='batch_pipeline_prod', client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock_b.sleeps == []
    assert damper_a is not damper_b
    assert damper_b._generations == {}


def test_g4_ns_isolation_batch_pipeline_dev_to_batch_pipeline_prod_k3_j0p0(mp):
    """A window in one namespace never damps a sibling namespace."""
    damper_a, clock_a = shared_damper('batch_pipeline_dev', jitter=0.0)
    damper_b, clock_b = shared_damper('batch_pipeline_prod', jitter=0.0)
    A = default_store(mp, ns='batch_pipeline_dev', client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=3)
    B = default_store(mp, ns='batch_pipeline_prod', client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock_b.sleeps == []
    assert damper_a is not damper_b
    assert damper_b._generations == {}


def test_g4_ns_isolation_batch_pipeline_dev_to_batch_pipeline_prod_k3_j0p25(mp):
    """A window in one namespace never damps a sibling namespace."""
    damper_a, clock_a = shared_damper('batch_pipeline_dev', jitter=0.25)
    damper_b, clock_b = shared_damper('batch_pipeline_prod', jitter=0.0)
    A = default_store(mp, ns='batch_pipeline_dev', client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=3)
    B = default_store(mp, ns='batch_pipeline_prod', client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock_b.sleeps == []
    assert damper_a is not damper_b
    assert damper_b._generations == {}


def test_g4_ns_isolation_batch_pipeline_dev_to_batch_pipeline_prod_k3_j0p5(mp):
    """A window in one namespace never damps a sibling namespace."""
    damper_a, clock_a = shared_damper('batch_pipeline_dev', jitter=0.5)
    damper_b, clock_b = shared_damper('batch_pipeline_prod', jitter=0.0)
    A = default_store(mp, ns='batch_pipeline_dev', client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=3)
    B = default_store(mp, ns='batch_pipeline_prod', client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock_b.sleeps == []
    assert damper_a is not damper_b
    assert damper_b._generations == {}


def test_g4_ns_isolation_batch_pipeline_dev_to_batch_pipeline_prod_k3_j1p0(mp):
    """A window in one namespace never damps a sibling namespace."""
    damper_a, clock_a = shared_damper('batch_pipeline_dev', jitter=1.0)
    damper_b, clock_b = shared_damper('batch_pipeline_prod', jitter=0.0)
    A = default_store(mp, ns='batch_pipeline_dev', client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=3)
    B = default_store(mp, ns='batch_pipeline_prod', client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock_b.sleeps == []
    assert damper_a is not damper_b
    assert damper_b._generations == {}


def test_g4_ns_isolation_batch_pipeline_dev_to_batch_pipeline_prod_k4_j0p0(mp):
    """A window in one namespace never damps a sibling namespace."""
    damper_a, clock_a = shared_damper('batch_pipeline_dev', jitter=0.0)
    damper_b, clock_b = shared_damper('batch_pipeline_prod', jitter=0.0)
    A = default_store(mp, ns='batch_pipeline_dev', client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=4)
    B = default_store(mp, ns='batch_pipeline_prod', client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock_b.sleeps == []
    assert damper_a is not damper_b
    assert damper_b._generations == {}


def test_g4_ns_isolation_batch_pipeline_dev_to_batch_pipeline_prod_k4_j0p25(mp):
    """A window in one namespace never damps a sibling namespace."""
    damper_a, clock_a = shared_damper('batch_pipeline_dev', jitter=0.25)
    damper_b, clock_b = shared_damper('batch_pipeline_prod', jitter=0.0)
    A = default_store(mp, ns='batch_pipeline_dev', client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=4)
    B = default_store(mp, ns='batch_pipeline_prod', client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock_b.sleeps == []
    assert damper_a is not damper_b
    assert damper_b._generations == {}


def test_g4_ns_isolation_batch_pipeline_dev_to_batch_pipeline_prod_k4_j0p5(mp):
    """A window in one namespace never damps a sibling namespace."""
    damper_a, clock_a = shared_damper('batch_pipeline_dev', jitter=0.5)
    damper_b, clock_b = shared_damper('batch_pipeline_prod', jitter=0.0)
    A = default_store(mp, ns='batch_pipeline_dev', client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=4)
    B = default_store(mp, ns='batch_pipeline_prod', client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock_b.sleeps == []
    assert damper_a is not damper_b
    assert damper_b._generations == {}


def test_g4_ns_isolation_batch_pipeline_dev_to_batch_pipeline_prod_k4_j1p0(mp):
    """A window in one namespace never damps a sibling namespace."""
    damper_a, clock_a = shared_damper('batch_pipeline_dev', jitter=1.0)
    damper_b, clock_b = shared_damper('batch_pipeline_prod', jitter=0.0)
    A = default_store(mp, ns='batch_pipeline_dev', client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=4)
    B = default_store(mp, ns='batch_pipeline_prod', client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock_b.sleeps == []
    assert damper_a is not damper_b
    assert damper_b._generations == {}


def test_g4_ns_isolation_batch_pipeline_prod_to_batch_pipeline_dev_k1_j0p0(mp):
    """A window in one namespace never damps a sibling namespace."""
    damper_a, clock_a = shared_damper('batch_pipeline_prod', jitter=0.0)
    damper_b, clock_b = shared_damper('batch_pipeline_dev', jitter=0.0)
    A = default_store(mp, ns='batch_pipeline_prod', client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=1)
    B = default_store(mp, ns='batch_pipeline_dev', client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock_b.sleeps == []
    assert damper_a is not damper_b
    assert damper_b._generations == {}


def test_g4_ns_isolation_batch_pipeline_prod_to_batch_pipeline_dev_k1_j0p25(mp):
    """A window in one namespace never damps a sibling namespace."""
    damper_a, clock_a = shared_damper('batch_pipeline_prod', jitter=0.25)
    damper_b, clock_b = shared_damper('batch_pipeline_dev', jitter=0.0)
    A = default_store(mp, ns='batch_pipeline_prod', client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=1)
    B = default_store(mp, ns='batch_pipeline_dev', client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock_b.sleeps == []
    assert damper_a is not damper_b
    assert damper_b._generations == {}


def test_g4_ns_isolation_batch_pipeline_prod_to_batch_pipeline_dev_k1_j0p5(mp):
    """A window in one namespace never damps a sibling namespace."""
    damper_a, clock_a = shared_damper('batch_pipeline_prod', jitter=0.5)
    damper_b, clock_b = shared_damper('batch_pipeline_dev', jitter=0.0)
    A = default_store(mp, ns='batch_pipeline_prod', client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=1)
    B = default_store(mp, ns='batch_pipeline_dev', client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock_b.sleeps == []
    assert damper_a is not damper_b
    assert damper_b._generations == {}


def test_g4_ns_isolation_batch_pipeline_prod_to_batch_pipeline_dev_k1_j1p0(mp):
    """A window in one namespace never damps a sibling namespace."""
    damper_a, clock_a = shared_damper('batch_pipeline_prod', jitter=1.0)
    damper_b, clock_b = shared_damper('batch_pipeline_dev', jitter=0.0)
    A = default_store(mp, ns='batch_pipeline_prod', client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=1)
    B = default_store(mp, ns='batch_pipeline_dev', client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock_b.sleeps == []
    assert damper_a is not damper_b
    assert damper_b._generations == {}


def test_g4_ns_isolation_batch_pipeline_prod_to_batch_pipeline_dev_k2_j0p0(mp):
    """A window in one namespace never damps a sibling namespace."""
    damper_a, clock_a = shared_damper('batch_pipeline_prod', jitter=0.0)
    damper_b, clock_b = shared_damper('batch_pipeline_dev', jitter=0.0)
    A = default_store(mp, ns='batch_pipeline_prod', client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=2)
    B = default_store(mp, ns='batch_pipeline_dev', client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock_b.sleeps == []
    assert damper_a is not damper_b
    assert damper_b._generations == {}


def test_g4_ns_isolation_batch_pipeline_prod_to_batch_pipeline_dev_k2_j0p25(mp):
    """A window in one namespace never damps a sibling namespace."""
    damper_a, clock_a = shared_damper('batch_pipeline_prod', jitter=0.25)
    damper_b, clock_b = shared_damper('batch_pipeline_dev', jitter=0.0)
    A = default_store(mp, ns='batch_pipeline_prod', client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=2)
    B = default_store(mp, ns='batch_pipeline_dev', client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock_b.sleeps == []
    assert damper_a is not damper_b
    assert damper_b._generations == {}


def test_g4_ns_isolation_batch_pipeline_prod_to_batch_pipeline_dev_k2_j0p5(mp):
    """A window in one namespace never damps a sibling namespace."""
    damper_a, clock_a = shared_damper('batch_pipeline_prod', jitter=0.5)
    damper_b, clock_b = shared_damper('batch_pipeline_dev', jitter=0.0)
    A = default_store(mp, ns='batch_pipeline_prod', client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=2)
    B = default_store(mp, ns='batch_pipeline_dev', client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock_b.sleeps == []
    assert damper_a is not damper_b
    assert damper_b._generations == {}


def test_g4_ns_isolation_batch_pipeline_prod_to_batch_pipeline_dev_k2_j1p0(mp):
    """A window in one namespace never damps a sibling namespace."""
    damper_a, clock_a = shared_damper('batch_pipeline_prod', jitter=1.0)
    damper_b, clock_b = shared_damper('batch_pipeline_dev', jitter=0.0)
    A = default_store(mp, ns='batch_pipeline_prod', client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=2)
    B = default_store(mp, ns='batch_pipeline_dev', client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock_b.sleeps == []
    assert damper_a is not damper_b
    assert damper_b._generations == {}


def test_g4_ns_isolation_batch_pipeline_prod_to_batch_pipeline_dev_k3_j0p0(mp):
    """A window in one namespace never damps a sibling namespace."""
    damper_a, clock_a = shared_damper('batch_pipeline_prod', jitter=0.0)
    damper_b, clock_b = shared_damper('batch_pipeline_dev', jitter=0.0)
    A = default_store(mp, ns='batch_pipeline_prod', client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=3)
    B = default_store(mp, ns='batch_pipeline_dev', client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock_b.sleeps == []
    assert damper_a is not damper_b
    assert damper_b._generations == {}


def test_g4_ns_isolation_batch_pipeline_prod_to_batch_pipeline_dev_k3_j0p25(mp):
    """A window in one namespace never damps a sibling namespace."""
    damper_a, clock_a = shared_damper('batch_pipeline_prod', jitter=0.25)
    damper_b, clock_b = shared_damper('batch_pipeline_dev', jitter=0.0)
    A = default_store(mp, ns='batch_pipeline_prod', client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=3)
    B = default_store(mp, ns='batch_pipeline_dev', client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock_b.sleeps == []
    assert damper_a is not damper_b
    assert damper_b._generations == {}


def test_g4_ns_isolation_batch_pipeline_prod_to_batch_pipeline_dev_k3_j0p5(mp):
    """A window in one namespace never damps a sibling namespace."""
    damper_a, clock_a = shared_damper('batch_pipeline_prod', jitter=0.5)
    damper_b, clock_b = shared_damper('batch_pipeline_dev', jitter=0.0)
    A = default_store(mp, ns='batch_pipeline_prod', client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=3)
    B = default_store(mp, ns='batch_pipeline_dev', client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock_b.sleeps == []
    assert damper_a is not damper_b
    assert damper_b._generations == {}


def test_g4_ns_isolation_batch_pipeline_prod_to_batch_pipeline_dev_k3_j1p0(mp):
    """A window in one namespace never damps a sibling namespace."""
    damper_a, clock_a = shared_damper('batch_pipeline_prod', jitter=1.0)
    damper_b, clock_b = shared_damper('batch_pipeline_dev', jitter=0.0)
    A = default_store(mp, ns='batch_pipeline_prod', client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=3)
    B = default_store(mp, ns='batch_pipeline_dev', client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock_b.sleeps == []
    assert damper_a is not damper_b
    assert damper_b._generations == {}


def test_g4_ns_isolation_batch_pipeline_prod_to_batch_pipeline_dev_k4_j0p0(mp):
    """A window in one namespace never damps a sibling namespace."""
    damper_a, clock_a = shared_damper('batch_pipeline_prod', jitter=0.0)
    damper_b, clock_b = shared_damper('batch_pipeline_dev', jitter=0.0)
    A = default_store(mp, ns='batch_pipeline_prod', client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=4)
    B = default_store(mp, ns='batch_pipeline_dev', client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock_b.sleeps == []
    assert damper_a is not damper_b
    assert damper_b._generations == {}


def test_g4_ns_isolation_batch_pipeline_prod_to_batch_pipeline_dev_k4_j0p25(mp):
    """A window in one namespace never damps a sibling namespace."""
    damper_a, clock_a = shared_damper('batch_pipeline_prod', jitter=0.25)
    damper_b, clock_b = shared_damper('batch_pipeline_dev', jitter=0.0)
    A = default_store(mp, ns='batch_pipeline_prod', client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=4)
    B = default_store(mp, ns='batch_pipeline_dev', client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock_b.sleeps == []
    assert damper_a is not damper_b
    assert damper_b._generations == {}


def test_g4_ns_isolation_batch_pipeline_prod_to_batch_pipeline_dev_k4_j0p5(mp):
    """A window in one namespace never damps a sibling namespace."""
    damper_a, clock_a = shared_damper('batch_pipeline_prod', jitter=0.5)
    damper_b, clock_b = shared_damper('batch_pipeline_dev', jitter=0.0)
    A = default_store(mp, ns='batch_pipeline_prod', client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=4)
    B = default_store(mp, ns='batch_pipeline_dev', client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock_b.sleeps == []
    assert damper_a is not damper_b
    assert damper_b._generations == {}


def test_g4_ns_isolation_batch_pipeline_prod_to_batch_pipeline_dev_k4_j1p0(mp):
    """A window in one namespace never damps a sibling namespace."""
    damper_a, clock_a = shared_damper('batch_pipeline_prod', jitter=1.0)
    damper_b, clock_b = shared_damper('batch_pipeline_dev', jitter=0.0)
    A = default_store(mp, ns='batch_pipeline_prod', client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=4)
    B = default_store(mp, ns='batch_pipeline_dev', client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock_b.sleeps == []
    assert damper_a is not damper_b
    assert damper_b._generations == {}


def test_g4_ns_isolation_batch_pipeline_test_unit_to_batch_pipeline_dev_k1_j0p0(mp):
    """A window in one namespace never damps a sibling namespace."""
    damper_a, clock_a = shared_damper('batch_pipeline_test_unit', jitter=0.0)
    damper_b, clock_b = shared_damper('batch_pipeline_dev', jitter=0.0)
    A = default_store(mp, ns='batch_pipeline_test_unit', client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=1)
    B = default_store(mp, ns='batch_pipeline_dev', client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock_b.sleeps == []
    assert damper_a is not damper_b
    assert damper_b._generations == {}


def test_g4_ns_isolation_batch_pipeline_test_unit_to_batch_pipeline_dev_k1_j0p25(mp):
    """A window in one namespace never damps a sibling namespace."""
    damper_a, clock_a = shared_damper('batch_pipeline_test_unit', jitter=0.25)
    damper_b, clock_b = shared_damper('batch_pipeline_dev', jitter=0.0)
    A = default_store(mp, ns='batch_pipeline_test_unit', client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=1)
    B = default_store(mp, ns='batch_pipeline_dev', client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock_b.sleeps == []
    assert damper_a is not damper_b
    assert damper_b._generations == {}


def test_g4_ns_isolation_batch_pipeline_test_unit_to_batch_pipeline_dev_k1_j0p5(mp):
    """A window in one namespace never damps a sibling namespace."""
    damper_a, clock_a = shared_damper('batch_pipeline_test_unit', jitter=0.5)
    damper_b, clock_b = shared_damper('batch_pipeline_dev', jitter=0.0)
    A = default_store(mp, ns='batch_pipeline_test_unit', client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=1)
    B = default_store(mp, ns='batch_pipeline_dev', client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock_b.sleeps == []
    assert damper_a is not damper_b
    assert damper_b._generations == {}


def test_g4_ns_isolation_batch_pipeline_test_unit_to_batch_pipeline_dev_k1_j1p0(mp):
    """A window in one namespace never damps a sibling namespace."""
    damper_a, clock_a = shared_damper('batch_pipeline_test_unit', jitter=1.0)
    damper_b, clock_b = shared_damper('batch_pipeline_dev', jitter=0.0)
    A = default_store(mp, ns='batch_pipeline_test_unit', client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=1)
    B = default_store(mp, ns='batch_pipeline_dev', client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock_b.sleeps == []
    assert damper_a is not damper_b
    assert damper_b._generations == {}


def test_g4_ns_isolation_batch_pipeline_test_unit_to_batch_pipeline_dev_k2_j0p0(mp):
    """A window in one namespace never damps a sibling namespace."""
    damper_a, clock_a = shared_damper('batch_pipeline_test_unit', jitter=0.0)
    damper_b, clock_b = shared_damper('batch_pipeline_dev', jitter=0.0)
    A = default_store(mp, ns='batch_pipeline_test_unit', client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=2)
    B = default_store(mp, ns='batch_pipeline_dev', client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock_b.sleeps == []
    assert damper_a is not damper_b
    assert damper_b._generations == {}


def test_g4_ns_isolation_batch_pipeline_test_unit_to_batch_pipeline_dev_k2_j0p25(mp):
    """A window in one namespace never damps a sibling namespace."""
    damper_a, clock_a = shared_damper('batch_pipeline_test_unit', jitter=0.25)
    damper_b, clock_b = shared_damper('batch_pipeline_dev', jitter=0.0)
    A = default_store(mp, ns='batch_pipeline_test_unit', client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=2)
    B = default_store(mp, ns='batch_pipeline_dev', client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock_b.sleeps == []
    assert damper_a is not damper_b
    assert damper_b._generations == {}


def test_g4_ns_isolation_batch_pipeline_test_unit_to_batch_pipeline_dev_k2_j0p5(mp):
    """A window in one namespace never damps a sibling namespace."""
    damper_a, clock_a = shared_damper('batch_pipeline_test_unit', jitter=0.5)
    damper_b, clock_b = shared_damper('batch_pipeline_dev', jitter=0.0)
    A = default_store(mp, ns='batch_pipeline_test_unit', client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=2)
    B = default_store(mp, ns='batch_pipeline_dev', client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock_b.sleeps == []
    assert damper_a is not damper_b
    assert damper_b._generations == {}


def test_g4_ns_isolation_batch_pipeline_test_unit_to_batch_pipeline_dev_k2_j1p0(mp):
    """A window in one namespace never damps a sibling namespace."""
    damper_a, clock_a = shared_damper('batch_pipeline_test_unit', jitter=1.0)
    damper_b, clock_b = shared_damper('batch_pipeline_dev', jitter=0.0)
    A = default_store(mp, ns='batch_pipeline_test_unit', client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=2)
    B = default_store(mp, ns='batch_pipeline_dev', client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock_b.sleeps == []
    assert damper_a is not damper_b
    assert damper_b._generations == {}


def test_g4_ns_isolation_batch_pipeline_test_unit_to_batch_pipeline_dev_k3_j0p0(mp):
    """A window in one namespace never damps a sibling namespace."""
    damper_a, clock_a = shared_damper('batch_pipeline_test_unit', jitter=0.0)
    damper_b, clock_b = shared_damper('batch_pipeline_dev', jitter=0.0)
    A = default_store(mp, ns='batch_pipeline_test_unit', client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=3)
    B = default_store(mp, ns='batch_pipeline_dev', client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock_b.sleeps == []
    assert damper_a is not damper_b
    assert damper_b._generations == {}


def test_g4_ns_isolation_batch_pipeline_test_unit_to_batch_pipeline_dev_k3_j0p25(mp):
    """A window in one namespace never damps a sibling namespace."""
    damper_a, clock_a = shared_damper('batch_pipeline_test_unit', jitter=0.25)
    damper_b, clock_b = shared_damper('batch_pipeline_dev', jitter=0.0)
    A = default_store(mp, ns='batch_pipeline_test_unit', client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=3)
    B = default_store(mp, ns='batch_pipeline_dev', client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock_b.sleeps == []
    assert damper_a is not damper_b
    assert damper_b._generations == {}


def test_g4_ns_isolation_batch_pipeline_test_unit_to_batch_pipeline_dev_k3_j0p5(mp):
    """A window in one namespace never damps a sibling namespace."""
    damper_a, clock_a = shared_damper('batch_pipeline_test_unit', jitter=0.5)
    damper_b, clock_b = shared_damper('batch_pipeline_dev', jitter=0.0)
    A = default_store(mp, ns='batch_pipeline_test_unit', client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=3)
    B = default_store(mp, ns='batch_pipeline_dev', client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock_b.sleeps == []
    assert damper_a is not damper_b
    assert damper_b._generations == {}


def test_g4_ns_isolation_batch_pipeline_test_unit_to_batch_pipeline_dev_k3_j1p0(mp):
    """A window in one namespace never damps a sibling namespace."""
    damper_a, clock_a = shared_damper('batch_pipeline_test_unit', jitter=1.0)
    damper_b, clock_b = shared_damper('batch_pipeline_dev', jitter=0.0)
    A = default_store(mp, ns='batch_pipeline_test_unit', client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=3)
    B = default_store(mp, ns='batch_pipeline_dev', client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock_b.sleeps == []
    assert damper_a is not damper_b
    assert damper_b._generations == {}


def test_g4_ns_isolation_batch_pipeline_test_unit_to_batch_pipeline_dev_k4_j0p0(mp):
    """A window in one namespace never damps a sibling namespace."""
    damper_a, clock_a = shared_damper('batch_pipeline_test_unit', jitter=0.0)
    damper_b, clock_b = shared_damper('batch_pipeline_dev', jitter=0.0)
    A = default_store(mp, ns='batch_pipeline_test_unit', client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=4)
    B = default_store(mp, ns='batch_pipeline_dev', client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock_b.sleeps == []
    assert damper_a is not damper_b
    assert damper_b._generations == {}


def test_g4_ns_isolation_batch_pipeline_test_unit_to_batch_pipeline_dev_k4_j0p25(mp):
    """A window in one namespace never damps a sibling namespace."""
    damper_a, clock_a = shared_damper('batch_pipeline_test_unit', jitter=0.25)
    damper_b, clock_b = shared_damper('batch_pipeline_dev', jitter=0.0)
    A = default_store(mp, ns='batch_pipeline_test_unit', client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=4)
    B = default_store(mp, ns='batch_pipeline_dev', client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock_b.sleeps == []
    assert damper_a is not damper_b
    assert damper_b._generations == {}


def test_g4_ns_isolation_batch_pipeline_test_unit_to_batch_pipeline_dev_k4_j0p5(mp):
    """A window in one namespace never damps a sibling namespace."""
    damper_a, clock_a = shared_damper('batch_pipeline_test_unit', jitter=0.5)
    damper_b, clock_b = shared_damper('batch_pipeline_dev', jitter=0.0)
    A = default_store(mp, ns='batch_pipeline_test_unit', client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=4)
    B = default_store(mp, ns='batch_pipeline_dev', client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock_b.sleeps == []
    assert damper_a is not damper_b
    assert damper_b._generations == {}


def test_g4_ns_isolation_batch_pipeline_test_unit_to_batch_pipeline_dev_k4_j1p0(mp):
    """A window in one namespace never damps a sibling namespace."""
    damper_a, clock_a = shared_damper('batch_pipeline_test_unit', jitter=1.0)
    damper_b, clock_b = shared_damper('batch_pipeline_dev', jitter=0.0)
    A = default_store(mp, ns='batch_pipeline_test_unit', client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=4)
    B = default_store(mp, ns='batch_pipeline_dev', client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock_b.sleeps == []
    assert damper_a is not damper_b
    assert damper_b._generations == {}


def test_g5_label_isolation_batch_merge_commit_runs_batch_complete_j0p0(mp):
    """A window armed for one label never damps a different label."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=1)
    B = default_store(mp, ns=NS, client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_complete')
    assert clock.sleeps == []
    assert 'batch_complete' not in damper._armed_until


def test_g5_label_isolation_batch_merge_commit_runs_batch_complete_j0p25(mp):
    """A window armed for one label never damps a different label."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=1)
    B = default_store(mp, ns=NS, client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_complete')
    assert clock.sleeps == []
    assert 'batch_complete' not in damper._armed_until


def test_g5_label_isolation_batch_merge_commit_runs_batch_complete_j0p5(mp):
    """A window armed for one label never damps a different label."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=1)
    B = default_store(mp, ns=NS, client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_complete')
    assert clock.sleeps == []
    assert 'batch_complete' not in damper._armed_until


def test_g5_label_isolation_batch_merge_commit_runs_batch_complete_j1p0(mp):
    """A window armed for one label never damps a different label."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=1)
    B = default_store(mp, ns=NS, client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_complete')
    assert clock.sleeps == []
    assert 'batch_complete' not in damper._armed_until


def test_g5_label_isolation_batch_merge_commit_runs_batch_intake_status_j0p0(mp):
    """A window armed for one label never damps a different label."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=1)
    B = default_store(mp, ns=NS, client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_intake_status')
    assert clock.sleeps == []
    assert 'batch_intake_status' not in damper._armed_until


def test_g5_label_isolation_batch_merge_commit_runs_batch_intake_status_j0p25(mp):
    """A window armed for one label never damps a different label."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=1)
    B = default_store(mp, ns=NS, client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_intake_status')
    assert clock.sleeps == []
    assert 'batch_intake_status' not in damper._armed_until


def test_g5_label_isolation_batch_merge_commit_runs_batch_intake_status_j0p5(mp):
    """A window armed for one label never damps a different label."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=1)
    B = default_store(mp, ns=NS, client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_intake_status')
    assert clock.sleeps == []
    assert 'batch_intake_status' not in damper._armed_until


def test_g5_label_isolation_batch_merge_commit_runs_batch_intake_status_j1p0(mp):
    """A window armed for one label never damps a different label."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=1)
    B = default_store(mp, ns=NS, client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_intake_status')
    assert clock.sleeps == []
    assert 'batch_intake_status' not in damper._armed_until


def test_g5_label_isolation_batch_provider_stt_runs_batch_complete_j0p0(mp):
    """A window armed for one label never damps a different label."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=1)
    B = default_store(mp, ns=NS, client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_complete')
    assert clock.sleeps == []
    assert 'batch_complete' not in damper._armed_until


def test_g5_label_isolation_batch_provider_stt_runs_batch_complete_j0p25(mp):
    """A window armed for one label never damps a different label."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=1)
    B = default_store(mp, ns=NS, client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_complete')
    assert clock.sleeps == []
    assert 'batch_complete' not in damper._armed_until


def test_g5_label_isolation_batch_provider_stt_runs_batch_complete_j0p5(mp):
    """A window armed for one label never damps a different label."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=1)
    B = default_store(mp, ns=NS, client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_complete')
    assert clock.sleeps == []
    assert 'batch_complete' not in damper._armed_until


def test_g5_label_isolation_batch_provider_stt_runs_batch_complete_j1p0(mp):
    """A window armed for one label never damps a different label."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=1)
    B = default_store(mp, ns=NS, client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_complete')
    assert clock.sleeps == []
    assert 'batch_complete' not in damper._armed_until


def test_g5_label_isolation_batch_provider_stt_runs_batch_intake_status_j0p0(mp):
    """A window armed for one label never damps a different label."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=1)
    B = default_store(mp, ns=NS, client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_intake_status')
    assert clock.sleeps == []
    assert 'batch_intake_status' not in damper._armed_until


def test_g5_label_isolation_batch_provider_stt_runs_batch_intake_status_j0p25(mp):
    """A window armed for one label never damps a different label."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=1)
    B = default_store(mp, ns=NS, client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_intake_status')
    assert clock.sleeps == []
    assert 'batch_intake_status' not in damper._armed_until


def test_g5_label_isolation_batch_provider_stt_runs_batch_intake_status_j0p5(mp):
    """A window armed for one label never damps a different label."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=1)
    B = default_store(mp, ns=NS, client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_intake_status')
    assert clock.sleeps == []
    assert 'batch_intake_status' not in damper._armed_until


def test_g5_label_isolation_batch_provider_stt_runs_batch_intake_status_j1p0(mp):
    """A window armed for one label never damps a different label."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=1)
    B = default_store(mp, ns=NS, client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_intake_status')
    assert clock.sleeps == []
    assert 'batch_intake_status' not in damper._armed_until


def test_g5_label_isolation_batch_intake_status_runs_batch_complete_j0p0(mp):
    """A window armed for one label never damps a different label."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_intake_status', times=1)
    B = default_store(mp, ns=NS, client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_complete')
    assert clock.sleeps == []
    assert 'batch_complete' not in damper._armed_until


def test_g5_label_isolation_batch_intake_status_runs_batch_complete_j0p25(mp):
    """A window armed for one label never damps a different label."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_intake_status', times=1)
    B = default_store(mp, ns=NS, client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_complete')
    assert clock.sleeps == []
    assert 'batch_complete' not in damper._armed_until


def test_g5_label_isolation_batch_intake_status_runs_batch_complete_j0p5(mp):
    """A window armed for one label never damps a different label."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_intake_status', times=1)
    B = default_store(mp, ns=NS, client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_complete')
    assert clock.sleeps == []
    assert 'batch_complete' not in damper._armed_until


def test_g5_label_isolation_batch_intake_status_runs_batch_complete_j1p0(mp):
    """A window armed for one label never damps a different label."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_intake_status', times=1)
    B = default_store(mp, ns=NS, client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_complete')
    assert clock.sleeps == []
    assert 'batch_complete' not in damper._armed_until


def test_g6_cap_plateau_k9_j0p0(mp):
    """Deep storm ladder stays at the cap through the shared damper."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=9)
    B = default_store(mp, ns=NS, client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(2.0)
    assert max(clock.sleeps) <= CAP + 1e-9


def test_g6_cap_plateau_k9_j0p25(mp):
    """Deep storm ladder stays at the cap through the shared damper."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=9)
    B = default_store(mp, ns=NS, client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(2.5)
    assert max(clock.sleeps) <= CAP + 1e-9


def test_g6_cap_plateau_k9_j0p5(mp):
    """Deep storm ladder stays at the cap through the shared damper."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=9)
    B = default_store(mp, ns=NS, client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(3.0)
    assert max(clock.sleeps) <= CAP + 1e-9


def test_g6_cap_plateau_k9_j1p0(mp):
    """Deep storm ladder stays at the cap through the shared damper."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=9)
    B = default_store(mp, ns=NS, client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(4.0)
    assert max(clock.sleeps) <= CAP + 1e-9


def test_g6_cap_plateau_k10_j0p0(mp):
    """Deep storm ladder stays at the cap through the shared damper."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=10)
    B = default_store(mp, ns=NS, client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(2.0)
    assert max(clock.sleeps) <= CAP + 1e-9


def test_g6_cap_plateau_k10_j0p25(mp):
    """Deep storm ladder stays at the cap through the shared damper."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=10)
    B = default_store(mp, ns=NS, client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(2.5)
    assert max(clock.sleeps) <= CAP + 1e-9


def test_g6_cap_plateau_k10_j0p5(mp):
    """Deep storm ladder stays at the cap through the shared damper."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=10)
    B = default_store(mp, ns=NS, client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(3.0)
    assert max(clock.sleeps) <= CAP + 1e-9


def test_g6_cap_plateau_k10_j1p0(mp):
    """Deep storm ladder stays at the cap through the shared damper."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=10)
    B = default_store(mp, ns=NS, client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(4.0)
    assert max(clock.sleeps) <= CAP + 1e-9


def test_g6_cap_plateau_k11_j0p0(mp):
    """Deep storm ladder stays at the cap through the shared damper."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=11)
    B = default_store(mp, ns=NS, client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(2.0)
    assert max(clock.sleeps) <= CAP + 1e-9


def test_g6_cap_plateau_k11_j0p25(mp):
    """Deep storm ladder stays at the cap through the shared damper."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=11)
    B = default_store(mp, ns=NS, client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(2.5)
    assert max(clock.sleeps) <= CAP + 1e-9


def test_g6_cap_plateau_k11_j0p5(mp):
    """Deep storm ladder stays at the cap through the shared damper."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=11)
    B = default_store(mp, ns=NS, client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(3.0)
    assert max(clock.sleeps) <= CAP + 1e-9


def test_g6_cap_plateau_k11_j1p0(mp):
    """Deep storm ladder stays at the cap through the shared damper."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=11)
    B = default_store(mp, ns=NS, client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(4.0)
    assert max(clock.sleeps) <= CAP + 1e-9


def test_g6_cap_plateau_k12_j0p0(mp):
    """Deep storm ladder stays at the cap through the shared damper."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=12)
    B = default_store(mp, ns=NS, client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(2.0)
    assert max(clock.sleeps) <= CAP + 1e-9


def test_g6_cap_plateau_k12_j0p25(mp):
    """Deep storm ladder stays at the cap through the shared damper."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=12)
    B = default_store(mp, ns=NS, client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(2.5)
    assert max(clock.sleeps) <= CAP + 1e-9


def test_g6_cap_plateau_k12_j0p5(mp):
    """Deep storm ladder stays at the cap through the shared damper."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=12)
    B = default_store(mp, ns=NS, client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(3.0)
    assert max(clock.sleeps) <= CAP + 1e-9


def test_g6_cap_plateau_k12_j1p0(mp):
    """Deep storm ladder stays at the cap through the shared damper."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=12)
    B = default_store(mp, ns=NS, client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(4.0)
    assert max(clock.sleeps) <= CAP + 1e-9


def test_g6_cap_plateau_k13_j0p0(mp):
    """Deep storm ladder stays at the cap through the shared damper."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=13)
    B = default_store(mp, ns=NS, client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(2.0)
    assert max(clock.sleeps) <= CAP + 1e-9


def test_g6_cap_plateau_k13_j0p25(mp):
    """Deep storm ladder stays at the cap through the shared damper."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=13)
    B = default_store(mp, ns=NS, client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(2.5)
    assert max(clock.sleeps) <= CAP + 1e-9


def test_g6_cap_plateau_k13_j0p5(mp):
    """Deep storm ladder stays at the cap through the shared damper."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=13)
    B = default_store(mp, ns=NS, client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(3.0)
    assert max(clock.sleeps) <= CAP + 1e-9


def test_g6_cap_plateau_k13_j1p0(mp):
    """Deep storm ladder stays at the cap through the shared damper."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=13)
    B = default_store(mp, ns=NS, client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(4.0)
    assert max(clock.sleeps) <= CAP + 1e-9


def test_g6_cap_plateau_k14_j0p0(mp):
    """Deep storm ladder stays at the cap through the shared damper."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=14)
    B = default_store(mp, ns=NS, client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(2.0)
    assert max(clock.sleeps) <= CAP + 1e-9


def test_g6_cap_plateau_k14_j0p25(mp):
    """Deep storm ladder stays at the cap through the shared damper."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=14)
    B = default_store(mp, ns=NS, client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(2.5)
    assert max(clock.sleeps) <= CAP + 1e-9


def test_g6_cap_plateau_k14_j0p5(mp):
    """Deep storm ladder stays at the cap through the shared damper."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=14)
    B = default_store(mp, ns=NS, client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(3.0)
    assert max(clock.sleeps) <= CAP + 1e-9


def test_g6_cap_plateau_k14_j1p0(mp):
    """Deep storm ladder stays at the cap through the shared damper."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=14)
    B = default_store(mp, ns=NS, client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(4.0)
    assert max(clock.sleeps) <= CAP + 1e-9


def test_g8_success_clears_shared_window_batch_merge_commit_j0p0(mp):
    """A sibling's success clears the shared ladder when no arm happened since consult."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=1)
    B = default_store(mp, ns=NS, client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert damper._generations == {}
    assert clock.sleeps == [0.125]


def test_g8_success_clears_shared_window_batch_merge_commit_j0p25(mp):
    """A sibling's success clears the shared ladder when no arm happened since consult."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=1)
    B = default_store(mp, ns=NS, client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert damper._generations == {}
    assert clock.sleeps == [0.15625]


def test_g8_success_clears_shared_window_batch_merge_commit_j0p5(mp):
    """A sibling's success clears the shared ladder when no arm happened since consult."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=1)
    B = default_store(mp, ns=NS, client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert damper._generations == {}
    assert clock.sleeps == [0.1875]


def test_g8_success_clears_shared_window_batch_merge_commit_j1p0(mp):
    """A sibling's success clears the shared ladder when no arm happened since consult."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=1)
    B = default_store(mp, ns=NS, client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert damper._generations == {}
    assert clock.sleeps == [0.25]


def test_g8_success_held_by_mid_chain_arm_batch_merge_commit_j0p0(mp):
    """A success does not clear a window a sibling armed during the chain."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=1)
    B = default_store(mp, ns=NS, client=healthy_client())
    B.run(mid_chain_arm_body(damper, 'batch_merge_commit', arm_on=1), operation='batch_merge_commit')
    assert 'batch_merge_commit' in damper._generations
    C = default_store(mp, ns=NS, client=healthy_client())
    C.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps == [0.125, 0.25]


def test_g8_success_held_by_mid_chain_arm_batch_merge_commit_j0p25(mp):
    """A success does not clear a window a sibling armed during the chain."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=1)
    B = default_store(mp, ns=NS, client=healthy_client())
    B.run(mid_chain_arm_body(damper, 'batch_merge_commit', arm_on=1), operation='batch_merge_commit')
    assert 'batch_merge_commit' in damper._generations
    C = default_store(mp, ns=NS, client=healthy_client())
    C.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps == [0.15625, 0.3125]


def test_g8_success_held_by_mid_chain_arm_batch_merge_commit_j0p5(mp):
    """A success does not clear a window a sibling armed during the chain."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=1)
    B = default_store(mp, ns=NS, client=healthy_client())
    B.run(mid_chain_arm_body(damper, 'batch_merge_commit', arm_on=1), operation='batch_merge_commit')
    assert 'batch_merge_commit' in damper._generations
    C = default_store(mp, ns=NS, client=healthy_client())
    C.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps == [0.1875, 0.375]


def test_g8_success_held_by_mid_chain_arm_batch_merge_commit_j1p0(mp):
    """A success does not clear a window a sibling armed during the chain."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=1)
    B = default_store(mp, ns=NS, client=healthy_client())
    B.run(mid_chain_arm_body(damper, 'batch_merge_commit', arm_on=1), operation='batch_merge_commit')
    assert 'batch_merge_commit' in damper._generations
    C = default_store(mp, ns=NS, client=healthy_client())
    C.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps == [0.25, 0.5]


def test_g8_expired_window_success_leaves_nothing_batch_merge_commit_j0p0(mp):
    """A window that expired before the sibling's entry leaves the ladder clear."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=1)
    clock.now += 0.125 + 0.001
    B = default_store(mp, ns=NS, client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert damper._generations == {}
    assert clock.sleeps == []


def test_g8_expired_window_success_leaves_nothing_batch_merge_commit_j0p25(mp):
    """A window that expired before the sibling's entry leaves the ladder clear."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=1)
    clock.now += 0.15625 + 0.001
    B = default_store(mp, ns=NS, client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert damper._generations == {}
    assert clock.sleeps == []


def test_g8_expired_window_success_leaves_nothing_batch_merge_commit_j0p5(mp):
    """A window that expired before the sibling's entry leaves the ladder clear."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=1)
    clock.now += 0.1875 + 0.001
    B = default_store(mp, ns=NS, client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert damper._generations == {}
    assert clock.sleeps == []


def test_g8_expired_window_success_leaves_nothing_batch_merge_commit_j1p0(mp):
    """A window that expired before the sibling's entry leaves the ladder clear."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=1)
    clock.now += 0.25 + 0.001
    B = default_store(mp, ns=NS, client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert damper._generations == {}
    assert clock.sleeps == []


def test_g8_success_clears_shared_window_batch_provider_stt_j0p0(mp):
    """A sibling's success clears the shared ladder when no arm happened since consult."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=1)
    B = default_store(mp, ns=NS, client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert damper._generations == {}
    assert clock.sleeps == [0.125]


def test_g8_success_clears_shared_window_batch_provider_stt_j0p25(mp):
    """A sibling's success clears the shared ladder when no arm happened since consult."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=1)
    B = default_store(mp, ns=NS, client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert damper._generations == {}
    assert clock.sleeps == [0.15625]


def test_g8_success_clears_shared_window_batch_provider_stt_j0p5(mp):
    """A sibling's success clears the shared ladder when no arm happened since consult."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=1)
    B = default_store(mp, ns=NS, client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert damper._generations == {}
    assert clock.sleeps == [0.1875]


def test_g8_success_clears_shared_window_batch_provider_stt_j1p0(mp):
    """A sibling's success clears the shared ladder when no arm happened since consult."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=1)
    B = default_store(mp, ns=NS, client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert damper._generations == {}
    assert clock.sleeps == [0.25]


def test_g8_success_held_by_mid_chain_arm_batch_provider_stt_j0p0(mp):
    """A success does not clear a window a sibling armed during the chain."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=1)
    B = default_store(mp, ns=NS, client=healthy_client())
    B.run(mid_chain_arm_body(damper, 'batch_provider_stt', arm_on=1), operation='batch_provider_stt')
    assert 'batch_provider_stt' in damper._generations
    C = default_store(mp, ns=NS, client=healthy_client())
    C.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert clock.sleeps == [0.125, 0.25]


def test_g8_success_held_by_mid_chain_arm_batch_provider_stt_j0p25(mp):
    """A success does not clear a window a sibling armed during the chain."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=1)
    B = default_store(mp, ns=NS, client=healthy_client())
    B.run(mid_chain_arm_body(damper, 'batch_provider_stt', arm_on=1), operation='batch_provider_stt')
    assert 'batch_provider_stt' in damper._generations
    C = default_store(mp, ns=NS, client=healthy_client())
    C.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert clock.sleeps == [0.15625, 0.3125]


def test_g8_success_held_by_mid_chain_arm_batch_provider_stt_j0p5(mp):
    """A success does not clear a window a sibling armed during the chain."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=1)
    B = default_store(mp, ns=NS, client=healthy_client())
    B.run(mid_chain_arm_body(damper, 'batch_provider_stt', arm_on=1), operation='batch_provider_stt')
    assert 'batch_provider_stt' in damper._generations
    C = default_store(mp, ns=NS, client=healthy_client())
    C.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert clock.sleeps == [0.1875, 0.375]


def test_g8_success_held_by_mid_chain_arm_batch_provider_stt_j1p0(mp):
    """A success does not clear a window a sibling armed during the chain."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=1)
    B = default_store(mp, ns=NS, client=healthy_client())
    B.run(mid_chain_arm_body(damper, 'batch_provider_stt', arm_on=1), operation='batch_provider_stt')
    assert 'batch_provider_stt' in damper._generations
    C = default_store(mp, ns=NS, client=healthy_client())
    C.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert clock.sleeps == [0.25, 0.5]


def test_g8_expired_window_success_leaves_nothing_batch_provider_stt_j0p0(mp):
    """A window that expired before the sibling's entry leaves the ladder clear."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=1)
    clock.now += 0.125 + 0.001
    B = default_store(mp, ns=NS, client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert damper._generations == {}
    assert clock.sleeps == []


def test_g8_expired_window_success_leaves_nothing_batch_provider_stt_j0p25(mp):
    """A window that expired before the sibling's entry leaves the ladder clear."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=1)
    clock.now += 0.15625 + 0.001
    B = default_store(mp, ns=NS, client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert damper._generations == {}
    assert clock.sleeps == []


def test_g8_expired_window_success_leaves_nothing_batch_provider_stt_j0p5(mp):
    """A window that expired before the sibling's entry leaves the ladder clear."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=1)
    clock.now += 0.1875 + 0.001
    B = default_store(mp, ns=NS, client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert damper._generations == {}
    assert clock.sleeps == []


def test_g8_expired_window_success_leaves_nothing_batch_provider_stt_j1p0(mp):
    """A window that expired before the sibling's entry leaves the ladder clear."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=1)
    clock.now += 0.25 + 0.001
    B = default_store(mp, ns=NS, client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert damper._generations == {}
    assert clock.sleeps == []


def test_g8_success_clears_shared_window_batch_intake_status_j0p0(mp):
    """A sibling's success clears the shared ladder when no arm happened since consult."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_intake_status', times=1)
    B = default_store(mp, ns=NS, client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_intake_status')
    assert damper._generations == {}
    assert clock.sleeps == [0.125]


def test_g8_success_clears_shared_window_batch_intake_status_j0p25(mp):
    """A sibling's success clears the shared ladder when no arm happened since consult."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_intake_status', times=1)
    B = default_store(mp, ns=NS, client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_intake_status')
    assert damper._generations == {}
    assert clock.sleeps == [0.15625]


def test_g8_success_clears_shared_window_batch_intake_status_j0p5(mp):
    """A sibling's success clears the shared ladder when no arm happened since consult."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_intake_status', times=1)
    B = default_store(mp, ns=NS, client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_intake_status')
    assert damper._generations == {}
    assert clock.sleeps == [0.1875]


def test_g8_success_clears_shared_window_batch_intake_status_j1p0(mp):
    """A sibling's success clears the shared ladder when no arm happened since consult."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_intake_status', times=1)
    B = default_store(mp, ns=NS, client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_intake_status')
    assert damper._generations == {}
    assert clock.sleeps == [0.25]


def test_g8_success_held_by_mid_chain_arm_batch_intake_status_j0p0(mp):
    """A success does not clear a window a sibling armed during the chain."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_intake_status', times=1)
    B = default_store(mp, ns=NS, client=healthy_client())
    B.run(mid_chain_arm_body(damper, 'batch_intake_status', arm_on=1), operation='batch_intake_status')
    assert 'batch_intake_status' in damper._generations
    C = default_store(mp, ns=NS, client=healthy_client())
    C.run(lambda tx: 'ok', operation='batch_intake_status')
    assert clock.sleeps == [0.125, 0.25]


def test_g8_success_held_by_mid_chain_arm_batch_intake_status_j0p25(mp):
    """A success does not clear a window a sibling armed during the chain."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_intake_status', times=1)
    B = default_store(mp, ns=NS, client=healthy_client())
    B.run(mid_chain_arm_body(damper, 'batch_intake_status', arm_on=1), operation='batch_intake_status')
    assert 'batch_intake_status' in damper._generations
    C = default_store(mp, ns=NS, client=healthy_client())
    C.run(lambda tx: 'ok', operation='batch_intake_status')
    assert clock.sleeps == [0.15625, 0.3125]


def test_g8_success_held_by_mid_chain_arm_batch_intake_status_j0p5(mp):
    """A success does not clear a window a sibling armed during the chain."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_intake_status', times=1)
    B = default_store(mp, ns=NS, client=healthy_client())
    B.run(mid_chain_arm_body(damper, 'batch_intake_status', arm_on=1), operation='batch_intake_status')
    assert 'batch_intake_status' in damper._generations
    C = default_store(mp, ns=NS, client=healthy_client())
    C.run(lambda tx: 'ok', operation='batch_intake_status')
    assert clock.sleeps == [0.1875, 0.375]


def test_g8_success_held_by_mid_chain_arm_batch_intake_status_j1p0(mp):
    """A success does not clear a window a sibling armed during the chain."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_intake_status', times=1)
    B = default_store(mp, ns=NS, client=healthy_client())
    B.run(mid_chain_arm_body(damper, 'batch_intake_status', arm_on=1), operation='batch_intake_status')
    assert 'batch_intake_status' in damper._generations
    C = default_store(mp, ns=NS, client=healthy_client())
    C.run(lambda tx: 'ok', operation='batch_intake_status')
    assert clock.sleeps == [0.25, 0.5]


def test_g8_expired_window_success_leaves_nothing_batch_intake_status_j0p0(mp):
    """A window that expired before the sibling's entry leaves the ladder clear."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_intake_status', times=1)
    clock.now += 0.125 + 0.001
    B = default_store(mp, ns=NS, client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_intake_status')
    assert damper._generations == {}
    assert clock.sleeps == []


def test_g8_expired_window_success_leaves_nothing_batch_intake_status_j0p25(mp):
    """A window that expired before the sibling's entry leaves the ladder clear."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_intake_status', times=1)
    clock.now += 0.15625 + 0.001
    B = default_store(mp, ns=NS, client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_intake_status')
    assert damper._generations == {}
    assert clock.sleeps == []


def test_g8_expired_window_success_leaves_nothing_batch_intake_status_j0p5(mp):
    """A window that expired before the sibling's entry leaves the ladder clear."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_intake_status', times=1)
    clock.now += 0.1875 + 0.001
    B = default_store(mp, ns=NS, client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_intake_status')
    assert damper._generations == {}
    assert clock.sleeps == []


def test_g8_expired_window_success_leaves_nothing_batch_intake_status_j1p0(mp):
    """A window that expired before the sibling's entry leaves the ladder clear."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_intake_status', times=1)
    clock.now += 0.25 + 0.001
    B = default_store(mp, ns=NS, client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_intake_status')
    assert damper._generations == {}
    assert clock.sleeps == []


def test_g8_success_clears_shared_window_batch_complete_j0p0(mp):
    """A sibling's success clears the shared ladder when no arm happened since consult."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_complete', times=1)
    B = default_store(mp, ns=NS, client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_complete')
    assert damper._generations == {}
    assert clock.sleeps == [0.125]


def test_g8_success_clears_shared_window_batch_complete_j0p25(mp):
    """A sibling's success clears the shared ladder when no arm happened since consult."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_complete', times=1)
    B = default_store(mp, ns=NS, client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_complete')
    assert damper._generations == {}
    assert clock.sleeps == [0.15625]


def test_g8_success_clears_shared_window_batch_complete_j0p5(mp):
    """A sibling's success clears the shared ladder when no arm happened since consult."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_complete', times=1)
    B = default_store(mp, ns=NS, client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_complete')
    assert damper._generations == {}
    assert clock.sleeps == [0.1875]


def test_g8_success_clears_shared_window_batch_complete_j1p0(mp):
    """A sibling's success clears the shared ladder when no arm happened since consult."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_complete', times=1)
    B = default_store(mp, ns=NS, client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_complete')
    assert damper._generations == {}
    assert clock.sleeps == [0.25]


def test_g8_success_held_by_mid_chain_arm_batch_complete_j0p0(mp):
    """A success does not clear a window a sibling armed during the chain."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_complete', times=1)
    B = default_store(mp, ns=NS, client=healthy_client())
    B.run(mid_chain_arm_body(damper, 'batch_complete', arm_on=1), operation='batch_complete')
    assert 'batch_complete' in damper._generations
    C = default_store(mp, ns=NS, client=healthy_client())
    C.run(lambda tx: 'ok', operation='batch_complete')
    assert clock.sleeps == [0.125, 0.25]


def test_g8_success_held_by_mid_chain_arm_batch_complete_j0p25(mp):
    """A success does not clear a window a sibling armed during the chain."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_complete', times=1)
    B = default_store(mp, ns=NS, client=healthy_client())
    B.run(mid_chain_arm_body(damper, 'batch_complete', arm_on=1), operation='batch_complete')
    assert 'batch_complete' in damper._generations
    C = default_store(mp, ns=NS, client=healthy_client())
    C.run(lambda tx: 'ok', operation='batch_complete')
    assert clock.sleeps == [0.15625, 0.3125]


def test_g8_success_held_by_mid_chain_arm_batch_complete_j0p5(mp):
    """A success does not clear a window a sibling armed during the chain."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_complete', times=1)
    B = default_store(mp, ns=NS, client=healthy_client())
    B.run(mid_chain_arm_body(damper, 'batch_complete', arm_on=1), operation='batch_complete')
    assert 'batch_complete' in damper._generations
    C = default_store(mp, ns=NS, client=healthy_client())
    C.run(lambda tx: 'ok', operation='batch_complete')
    assert clock.sleeps == [0.1875, 0.375]


def test_g8_success_held_by_mid_chain_arm_batch_complete_j1p0(mp):
    """A success does not clear a window a sibling armed during the chain."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_complete', times=1)
    B = default_store(mp, ns=NS, client=healthy_client())
    B.run(mid_chain_arm_body(damper, 'batch_complete', arm_on=1), operation='batch_complete')
    assert 'batch_complete' in damper._generations
    C = default_store(mp, ns=NS, client=healthy_client())
    C.run(lambda tx: 'ok', operation='batch_complete')
    assert clock.sleeps == [0.25, 0.5]


def test_g8_expired_window_success_leaves_nothing_batch_complete_j0p0(mp):
    """A window that expired before the sibling's entry leaves the ladder clear."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_complete', times=1)
    clock.now += 0.125 + 0.001
    B = default_store(mp, ns=NS, client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_complete')
    assert damper._generations == {}
    assert clock.sleeps == []


def test_g8_expired_window_success_leaves_nothing_batch_complete_j0p25(mp):
    """A window that expired before the sibling's entry leaves the ladder clear."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_complete', times=1)
    clock.now += 0.15625 + 0.001
    B = default_store(mp, ns=NS, client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_complete')
    assert damper._generations == {}
    assert clock.sleeps == []


def test_g8_expired_window_success_leaves_nothing_batch_complete_j0p5(mp):
    """A window that expired before the sibling's entry leaves the ladder clear."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_complete', times=1)
    clock.now += 0.1875 + 0.001
    B = default_store(mp, ns=NS, client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_complete')
    assert damper._generations == {}
    assert clock.sleeps == []


def test_g8_expired_window_success_leaves_nothing_batch_complete_j1p0(mp):
    """A window that expired before the sibling's entry leaves the ladder clear."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_complete', times=1)
    clock.now += 0.25 + 0.001
    B = default_store(mp, ns=NS, client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_complete')
    assert damper._generations == {}
    assert clock.sleeps == []


def test_g9_damper_switch_off_no_sibling_wait_batch_merge_commit_k1(mp):
    """With the storm damper killed, an exhaustion arms nothing and siblings wait nothing."""
    damper, clock = shared_damper(NS, jitter=0.0)
    mp.setenv('BATCH_PIPELINE_CONTENTION_STORM_DAMPER_ENABLED', 'false')
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=1)
    B = default_store(mp, ns=NS, client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps == []
    assert damper._generations == {}


def test_g9_damper_switch_off_no_sibling_wait_batch_merge_commit_k2(mp):
    """With the storm damper killed, an exhaustion arms nothing and siblings wait nothing."""
    damper, clock = shared_damper(NS, jitter=0.0)
    mp.setenv('BATCH_PIPELINE_CONTENTION_STORM_DAMPER_ENABLED', 'false')
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=2)
    B = default_store(mp, ns=NS, client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps == []
    assert damper._generations == {}


def test_g9_damper_switch_off_no_sibling_wait_batch_provider_stt_k1(mp):
    """With the storm damper killed, an exhaustion arms nothing and siblings wait nothing."""
    damper, clock = shared_damper(NS, jitter=0.0)
    mp.setenv('BATCH_PIPELINE_CONTENTION_STORM_DAMPER_ENABLED', 'false')
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=1)
    B = default_store(mp, ns=NS, client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert clock.sleeps == []
    assert damper._generations == {}


def test_g9_damper_switch_off_no_sibling_wait_batch_provider_stt_k2(mp):
    """With the storm damper killed, an exhaustion arms nothing and siblings wait nothing."""
    damper, clock = shared_damper(NS, jitter=0.0)
    mp.setenv('BATCH_PIPELINE_CONTENTION_STORM_DAMPER_ENABLED', 'false')
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=2)
    B = default_store(mp, ns=NS, client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert clock.sleeps == []
    assert damper._generations == {}


def test_g10_reset_seam_k1_j0p0(mp):
    """Resetting the registry drops armed windows; the next store starts clean."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=1)
    storage.reset_shared_storm_dampers()
    B = default_store(mp, ns=NS, client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps == []
    assert B._storm_damper is not damper
    assert 'batch_merge_commit' not in B._storm_damper._armed_until


def test_g10_reset_seam_k1_j0p25(mp):
    """Resetting the registry drops armed windows; the next store starts clean."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=1)
    storage.reset_shared_storm_dampers()
    B = default_store(mp, ns=NS, client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps == []
    assert B._storm_damper is not damper
    assert 'batch_merge_commit' not in B._storm_damper._armed_until


def test_g10_reset_seam_k1_j0p5(mp):
    """Resetting the registry drops armed windows; the next store starts clean."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=1)
    storage.reset_shared_storm_dampers()
    B = default_store(mp, ns=NS, client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps == []
    assert B._storm_damper is not damper
    assert 'batch_merge_commit' not in B._storm_damper._armed_until


def test_g10_reset_seam_k1_j1p0(mp):
    """Resetting the registry drops armed windows; the next store starts clean."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=1)
    storage.reset_shared_storm_dampers()
    B = default_store(mp, ns=NS, client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps == []
    assert B._storm_damper is not damper
    assert 'batch_merge_commit' not in B._storm_damper._armed_until


def test_g10_reset_seam_k2_j0p0(mp):
    """Resetting the registry drops armed windows; the next store starts clean."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=2)
    storage.reset_shared_storm_dampers()
    B = default_store(mp, ns=NS, client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps == [0.125]
    assert B._storm_damper is not damper
    assert 'batch_merge_commit' not in B._storm_damper._armed_until


def test_g10_reset_seam_k2_j0p25(mp):
    """Resetting the registry drops armed windows; the next store starts clean."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=2)
    storage.reset_shared_storm_dampers()
    B = default_store(mp, ns=NS, client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps == [0.15625]
    assert B._storm_damper is not damper
    assert 'batch_merge_commit' not in B._storm_damper._armed_until


def test_g10_reset_seam_k2_j0p5(mp):
    """Resetting the registry drops armed windows; the next store starts clean."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=2)
    storage.reset_shared_storm_dampers()
    B = default_store(mp, ns=NS, client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps == [0.1875]
    assert B._storm_damper is not damper
    assert 'batch_merge_commit' not in B._storm_damper._armed_until


def test_g10_reset_seam_k2_j1p0(mp):
    """Resetting the registry drops armed windows; the next store starts clean."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=2)
    storage.reset_shared_storm_dampers()
    B = default_store(mp, ns=NS, client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps == [0.25]
    assert B._storm_damper is not damper
    assert 'batch_merge_commit' not in B._storm_damper._armed_until


def test_g10_reset_seam_k3_j0p0(mp):
    """Resetting the registry drops armed windows; the next store starts clean."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=3)
    storage.reset_shared_storm_dampers()
    B = default_store(mp, ns=NS, client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps == [0.125, 0.25]
    assert B._storm_damper is not damper
    assert 'batch_merge_commit' not in B._storm_damper._armed_until


def test_g10_reset_seam_k3_j0p25(mp):
    """Resetting the registry drops armed windows; the next store starts clean."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=3)
    storage.reset_shared_storm_dampers()
    B = default_store(mp, ns=NS, client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps == [0.15625, 0.3125]
    assert B._storm_damper is not damper
    assert 'batch_merge_commit' not in B._storm_damper._armed_until


def test_g10_reset_seam_k3_j0p5(mp):
    """Resetting the registry drops armed windows; the next store starts clean."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=3)
    storage.reset_shared_storm_dampers()
    B = default_store(mp, ns=NS, client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps == [0.1875, 0.375]
    assert B._storm_damper is not damper
    assert 'batch_merge_commit' not in B._storm_damper._armed_until


def test_g10_reset_seam_k3_j1p0(mp):
    """Resetting the registry drops armed windows; the next store starts clean."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=3)
    storage.reset_shared_storm_dampers()
    B = default_store(mp, ns=NS, client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps == [0.25, 0.5]
    assert B._storm_damper is not damper
    assert 'batch_merge_commit' not in B._storm_damper._armed_until


def test_g10_reset_seam_k4_j0p0(mp):
    """Resetting the registry drops armed windows; the next store starts clean."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=4)
    storage.reset_shared_storm_dampers()
    B = default_store(mp, ns=NS, client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps == [0.125, 0.25, 0.5]
    assert B._storm_damper is not damper
    assert 'batch_merge_commit' not in B._storm_damper._armed_until


def test_g10_reset_seam_k4_j0p25(mp):
    """Resetting the registry drops armed windows; the next store starts clean."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=4)
    storage.reset_shared_storm_dampers()
    B = default_store(mp, ns=NS, client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps == [0.15625, 0.3125, 0.625]
    assert B._storm_damper is not damper
    assert 'batch_merge_commit' not in B._storm_damper._armed_until


def test_g10_reset_seam_k4_j0p5(mp):
    """Resetting the registry drops armed windows; the next store starts clean."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=4)
    storage.reset_shared_storm_dampers()
    B = default_store(mp, ns=NS, client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps == [0.1875, 0.375, 0.75]
    assert B._storm_damper is not damper
    assert 'batch_merge_commit' not in B._storm_damper._armed_until


def test_g10_reset_seam_k4_j1p0(mp):
    """Resetting the registry drops armed windows; the next store starts clean."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=4)
    storage.reset_shared_storm_dampers()
    B = default_store(mp, ns=NS, client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps == [0.25, 0.5, 1.0]
    assert B._storm_damper is not damper
    assert 'batch_merge_commit' not in B._storm_damper._armed_until


def test_g10_injected_damper_not_registered_batch_pipeline_dev(mp):
    """An injected damper never joins the shared registry."""
    mp.setenv('OMI_ENV_STAGE', 'prod' if 'batch_pipeline_dev' == 'batch_pipeline_prod' else 'dev')
    mp.setenv('FIRESTORE_EMULATOR_HOST', '127.0.0.1:8080')
    injected = storage._ContentionStormDamper()
    storage.FirestoreStore('batch_pipeline_dev', firestore_client=None, storm_damper=injected)
    assert 'batch_pipeline_dev' not in storage._SHARED_STORM_DAMPERS


def test_g10_injected_damper_not_registered_batch_pipeline_prod(mp):
    """An injected damper never joins the shared registry."""
    mp.setenv('OMI_ENV_STAGE', 'prod' if 'batch_pipeline_prod' == 'batch_pipeline_prod' else 'dev')
    mp.setenv('FIRESTORE_EMULATOR_HOST', '127.0.0.1:8080')
    injected = storage._ContentionStormDamper()
    storage.FirestoreStore('batch_pipeline_prod', firestore_client=None, storm_damper=injected)
    assert 'batch_pipeline_prod' not in storage._SHARED_STORM_DAMPERS


def test_g10_injected_damper_not_registered_batch_pipeline_test_unit(mp):
    """An injected damper never joins the shared registry."""
    mp.setenv('OMI_ENV_STAGE', 'prod' if 'batch_pipeline_test_unit' == 'batch_pipeline_prod' else 'dev')
    mp.setenv('FIRESTORE_EMULATOR_HOST', '127.0.0.1:8080')
    injected = storage._ContentionStormDamper()
    storage.FirestoreStore('batch_pipeline_test_unit', firestore_client=None, storm_damper=injected)
    assert 'batch_pipeline_test_unit' not in storage._SHARED_STORM_DAMPERS


def test_g10_post_reset_identity_batch_pipeline_dev(mp):
    """Post-reset construction resolves a fresh shared damper."""
    first = shared_damper('batch_pipeline_dev')[0]
    storage.reset_shared_storm_dampers()
    second = shared_damper('batch_pipeline_dev')[0]
    assert first is not second
    assert storage.shared_storm_damper('batch_pipeline_dev') is second


def test_g10_post_reset_identity_batch_pipeline_prod(mp):
    """Post-reset construction resolves a fresh shared damper."""
    first = shared_damper('batch_pipeline_prod')[0]
    storage.reset_shared_storm_dampers()
    second = shared_damper('batch_pipeline_prod')[0]
    assert first is not second
    assert storage.shared_storm_damper('batch_pipeline_prod') is second


def test_g12_two_labels_coexist_ka1_kb1_j0p0(mp):
    """Windows for two labels stand independently on the one shared damper."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=1)
    for _ in range(1):
        damper.arm('batch_provider_stt')
    assert damper.peek('batch_provider_stt')[0] == pytest.approx(0.125)
    B = default_store(mp, ns=NS, client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(0.125)


def test_g12_two_labels_coexist_ka1_kb1_j0p25(mp):
    """Windows for two labels stand independently on the one shared damper."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=1)
    for _ in range(1):
        damper.arm('batch_provider_stt')
    assert damper.peek('batch_provider_stt')[0] == pytest.approx(0.15625)
    B = default_store(mp, ns=NS, client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(0.15625)


def test_g12_two_labels_coexist_ka1_kb1_j0p5(mp):
    """Windows for two labels stand independently on the one shared damper."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=1)
    for _ in range(1):
        damper.arm('batch_provider_stt')
    assert damper.peek('batch_provider_stt')[0] == pytest.approx(0.1875)
    B = default_store(mp, ns=NS, client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(0.1875)


def test_g12_two_labels_coexist_ka1_kb1_j1p0(mp):
    """Windows for two labels stand independently on the one shared damper."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=1)
    for _ in range(1):
        damper.arm('batch_provider_stt')
    assert damper.peek('batch_provider_stt')[0] == pytest.approx(0.25)
    B = default_store(mp, ns=NS, client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(0.25)


def test_g12_two_labels_coexist_ka1_kb2_j0p0(mp):
    """Windows for two labels stand independently on the one shared damper."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=1)
    for _ in range(2):
        damper.arm('batch_provider_stt')
    assert damper.peek('batch_provider_stt')[0] == pytest.approx(0.25)
    B = default_store(mp, ns=NS, client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(0.125)


def test_g12_two_labels_coexist_ka1_kb2_j0p25(mp):
    """Windows for two labels stand independently on the one shared damper."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=1)
    for _ in range(2):
        damper.arm('batch_provider_stt')
    assert damper.peek('batch_provider_stt')[0] == pytest.approx(0.3125)
    B = default_store(mp, ns=NS, client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(0.15625)


def test_g12_two_labels_coexist_ka1_kb2_j0p5(mp):
    """Windows for two labels stand independently on the one shared damper."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=1)
    for _ in range(2):
        damper.arm('batch_provider_stt')
    assert damper.peek('batch_provider_stt')[0] == pytest.approx(0.375)
    B = default_store(mp, ns=NS, client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(0.1875)


def test_g12_two_labels_coexist_ka1_kb2_j1p0(mp):
    """Windows for two labels stand independently on the one shared damper."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=1)
    for _ in range(2):
        damper.arm('batch_provider_stt')
    assert damper.peek('batch_provider_stt')[0] == pytest.approx(0.5)
    B = default_store(mp, ns=NS, client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(0.25)


def test_g12_two_labels_coexist_ka1_kb3_j0p0(mp):
    """Windows for two labels stand independently on the one shared damper."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=1)
    for _ in range(3):
        damper.arm('batch_provider_stt')
    assert damper.peek('batch_provider_stt')[0] == pytest.approx(0.5)
    B = default_store(mp, ns=NS, client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(0.125)


def test_g12_two_labels_coexist_ka1_kb3_j0p25(mp):
    """Windows for two labels stand independently on the one shared damper."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=1)
    for _ in range(3):
        damper.arm('batch_provider_stt')
    assert damper.peek('batch_provider_stt')[0] == pytest.approx(0.625)
    B = default_store(mp, ns=NS, client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(0.15625)


def test_g12_two_labels_coexist_ka1_kb3_j0p5(mp):
    """Windows for two labels stand independently on the one shared damper."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=1)
    for _ in range(3):
        damper.arm('batch_provider_stt')
    assert damper.peek('batch_provider_stt')[0] == pytest.approx(0.75)
    B = default_store(mp, ns=NS, client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(0.1875)


def test_g12_two_labels_coexist_ka1_kb3_j1p0(mp):
    """Windows for two labels stand independently on the one shared damper."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=1)
    for _ in range(3):
        damper.arm('batch_provider_stt')
    assert damper.peek('batch_provider_stt')[0] == pytest.approx(1.0)
    B = default_store(mp, ns=NS, client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(0.25)


def test_g12_two_labels_coexist_ka2_kb1_j0p0(mp):
    """Windows for two labels stand independently on the one shared damper."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=2)
    for _ in range(1):
        damper.arm('batch_provider_stt')
    assert damper.peek('batch_provider_stt')[0] == pytest.approx(0.125)
    B = default_store(mp, ns=NS, client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(0.25)


def test_g12_two_labels_coexist_ka2_kb1_j0p25(mp):
    """Windows for two labels stand independently on the one shared damper."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=2)
    for _ in range(1):
        damper.arm('batch_provider_stt')
    assert damper.peek('batch_provider_stt')[0] == pytest.approx(0.15625)
    B = default_store(mp, ns=NS, client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(0.3125)


def test_g12_two_labels_coexist_ka2_kb1_j0p5(mp):
    """Windows for two labels stand independently on the one shared damper."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=2)
    for _ in range(1):
        damper.arm('batch_provider_stt')
    assert damper.peek('batch_provider_stt')[0] == pytest.approx(0.1875)
    B = default_store(mp, ns=NS, client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(0.375)


def test_g12_two_labels_coexist_ka2_kb1_j1p0(mp):
    """Windows for two labels stand independently on the one shared damper."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=2)
    for _ in range(1):
        damper.arm('batch_provider_stt')
    assert damper.peek('batch_provider_stt')[0] == pytest.approx(0.25)
    B = default_store(mp, ns=NS, client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(0.5)


def test_g12_two_labels_coexist_ka2_kb2_j0p0(mp):
    """Windows for two labels stand independently on the one shared damper."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=2)
    for _ in range(2):
        damper.arm('batch_provider_stt')
    assert damper.peek('batch_provider_stt')[0] == pytest.approx(0.25)
    B = default_store(mp, ns=NS, client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(0.25)


def test_g12_two_labels_coexist_ka2_kb2_j0p25(mp):
    """Windows for two labels stand independently on the one shared damper."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=2)
    for _ in range(2):
        damper.arm('batch_provider_stt')
    assert damper.peek('batch_provider_stt')[0] == pytest.approx(0.3125)
    B = default_store(mp, ns=NS, client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(0.3125)


def test_g12_two_labels_coexist_ka2_kb2_j0p5(mp):
    """Windows for two labels stand independently on the one shared damper."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=2)
    for _ in range(2):
        damper.arm('batch_provider_stt')
    assert damper.peek('batch_provider_stt')[0] == pytest.approx(0.375)
    B = default_store(mp, ns=NS, client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(0.375)


def test_g12_two_labels_coexist_ka2_kb2_j1p0(mp):
    """Windows for two labels stand independently on the one shared damper."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=2)
    for _ in range(2):
        damper.arm('batch_provider_stt')
    assert damper.peek('batch_provider_stt')[0] == pytest.approx(0.5)
    B = default_store(mp, ns=NS, client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(0.5)


def test_g12_two_labels_coexist_ka2_kb3_j0p0(mp):
    """Windows for two labels stand independently on the one shared damper."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=2)
    for _ in range(3):
        damper.arm('batch_provider_stt')
    assert damper.peek('batch_provider_stt')[0] == pytest.approx(0.5)
    B = default_store(mp, ns=NS, client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(0.25)


def test_g12_two_labels_coexist_ka2_kb3_j0p25(mp):
    """Windows for two labels stand independently on the one shared damper."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=2)
    for _ in range(3):
        damper.arm('batch_provider_stt')
    assert damper.peek('batch_provider_stt')[0] == pytest.approx(0.625)
    B = default_store(mp, ns=NS, client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(0.3125)


def test_g12_two_labels_coexist_ka2_kb3_j0p5(mp):
    """Windows for two labels stand independently on the one shared damper."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=2)
    for _ in range(3):
        damper.arm('batch_provider_stt')
    assert damper.peek('batch_provider_stt')[0] == pytest.approx(0.75)
    B = default_store(mp, ns=NS, client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(0.375)


def test_g12_two_labels_coexist_ka2_kb3_j1p0(mp):
    """Windows for two labels stand independently on the one shared damper."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=2)
    for _ in range(3):
        damper.arm('batch_provider_stt')
    assert damper.peek('batch_provider_stt')[0] == pytest.approx(1.0)
    B = default_store(mp, ns=NS, client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(0.5)


def test_g12_two_labels_coexist_ka3_kb1_j0p0(mp):
    """Windows for two labels stand independently on the one shared damper."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=3)
    for _ in range(1):
        damper.arm('batch_provider_stt')
    assert damper.peek('batch_provider_stt')[0] == pytest.approx(0.125)
    B = default_store(mp, ns=NS, client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(0.5)


def test_g12_two_labels_coexist_ka3_kb1_j0p25(mp):
    """Windows for two labels stand independently on the one shared damper."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=3)
    for _ in range(1):
        damper.arm('batch_provider_stt')
    assert damper.peek('batch_provider_stt')[0] == pytest.approx(0.15625)
    B = default_store(mp, ns=NS, client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(0.625)


def test_g12_two_labels_coexist_ka3_kb1_j0p5(mp):
    """Windows for two labels stand independently on the one shared damper."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=3)
    for _ in range(1):
        damper.arm('batch_provider_stt')
    assert damper.peek('batch_provider_stt')[0] == pytest.approx(0.1875)
    B = default_store(mp, ns=NS, client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(0.75)


def test_g12_two_labels_coexist_ka3_kb1_j1p0(mp):
    """Windows for two labels stand independently on the one shared damper."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=3)
    for _ in range(1):
        damper.arm('batch_provider_stt')
    assert damper.peek('batch_provider_stt')[0] == pytest.approx(0.25)
    B = default_store(mp, ns=NS, client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(1.0)


def test_g12_two_labels_coexist_ka3_kb2_j0p0(mp):
    """Windows for two labels stand independently on the one shared damper."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=3)
    for _ in range(2):
        damper.arm('batch_provider_stt')
    assert damper.peek('batch_provider_stt')[0] == pytest.approx(0.25)
    B = default_store(mp, ns=NS, client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(0.5)


def test_g12_two_labels_coexist_ka3_kb2_j0p25(mp):
    """Windows for two labels stand independently on the one shared damper."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=3)
    for _ in range(2):
        damper.arm('batch_provider_stt')
    assert damper.peek('batch_provider_stt')[0] == pytest.approx(0.3125)
    B = default_store(mp, ns=NS, client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(0.625)


def test_g12_two_labels_coexist_ka3_kb2_j0p5(mp):
    """Windows for two labels stand independently on the one shared damper."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=3)
    for _ in range(2):
        damper.arm('batch_provider_stt')
    assert damper.peek('batch_provider_stt')[0] == pytest.approx(0.375)
    B = default_store(mp, ns=NS, client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(0.75)


def test_g12_two_labels_coexist_ka3_kb2_j1p0(mp):
    """Windows for two labels stand independently on the one shared damper."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=3)
    for _ in range(2):
        damper.arm('batch_provider_stt')
    assert damper.peek('batch_provider_stt')[0] == pytest.approx(0.5)
    B = default_store(mp, ns=NS, client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(1.0)


def test_g12_two_labels_coexist_ka3_kb3_j0p0(mp):
    """Windows for two labels stand independently on the one shared damper."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=3)
    for _ in range(3):
        damper.arm('batch_provider_stt')
    assert damper.peek('batch_provider_stt')[0] == pytest.approx(0.5)
    B = default_store(mp, ns=NS, client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(0.5)


def test_g12_two_labels_coexist_ka3_kb3_j0p25(mp):
    """Windows for two labels stand independently on the one shared damper."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=3)
    for _ in range(3):
        damper.arm('batch_provider_stt')
    assert damper.peek('batch_provider_stt')[0] == pytest.approx(0.625)
    B = default_store(mp, ns=NS, client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(0.625)


def test_g12_two_labels_coexist_ka3_kb3_j0p5(mp):
    """Windows for two labels stand independently on the one shared damper."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=3)
    for _ in range(3):
        damper.arm('batch_provider_stt')
    assert damper.peek('batch_provider_stt')[0] == pytest.approx(0.75)
    B = default_store(mp, ns=NS, client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(0.75)


def test_g12_two_labels_coexist_ka3_kb3_j1p0(mp):
    """Windows for two labels stand independently on the one shared damper."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=3)
    for _ in range(3):
        damper.arm('batch_provider_stt')
    assert damper.peek('batch_provider_stt')[0] == pytest.approx(1.0)
    B = default_store(mp, ns=NS, client=healthy_client())
    B.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps[-1] == pytest.approx(1.0)


def test_g13_per_call_ladder_climb_t1_j0p0(mp):
    """Per-call store construction climbs the shared ladder across instances."""
    damper, clock = shared_damper(NS, jitter=0.0)
    for _ in range(1):
        store = default_store(mp, ns=NS, client=exhausting_client())
        exhaust_run(store, 'batch_provider_stt', times=1)
        assert store._storm_damper is damper
    final = default_store(mp, ns=NS, client=healthy_client())
    final.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert clock.sleeps == [0.125]


def test_g13_per_call_ladder_climb_t1_j0p25(mp):
    """Per-call store construction climbs the shared ladder across instances."""
    damper, clock = shared_damper(NS, jitter=0.25)
    for _ in range(1):
        store = default_store(mp, ns=NS, client=exhausting_client())
        exhaust_run(store, 'batch_provider_stt', times=1)
        assert store._storm_damper is damper
    final = default_store(mp, ns=NS, client=healthy_client())
    final.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert clock.sleeps == [0.15625]


def test_g13_per_call_ladder_climb_t1_j0p5(mp):
    """Per-call store construction climbs the shared ladder across instances."""
    damper, clock = shared_damper(NS, jitter=0.5)
    for _ in range(1):
        store = default_store(mp, ns=NS, client=exhausting_client())
        exhaust_run(store, 'batch_provider_stt', times=1)
        assert store._storm_damper is damper
    final = default_store(mp, ns=NS, client=healthy_client())
    final.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert clock.sleeps == [0.1875]


def test_g13_per_call_ladder_climb_t1_j1p0(mp):
    """Per-call store construction climbs the shared ladder across instances."""
    damper, clock = shared_damper(NS, jitter=1.0)
    for _ in range(1):
        store = default_store(mp, ns=NS, client=exhausting_client())
        exhaust_run(store, 'batch_provider_stt', times=1)
        assert store._storm_damper is damper
    final = default_store(mp, ns=NS, client=healthy_client())
    final.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert clock.sleeps == [0.25]


def test_g13_per_call_ladder_climb_t2_j0p0(mp):
    """Per-call store construction climbs the shared ladder across instances."""
    damper, clock = shared_damper(NS, jitter=0.0)
    for _ in range(2):
        store = default_store(mp, ns=NS, client=exhausting_client())
        exhaust_run(store, 'batch_provider_stt', times=1)
        assert store._storm_damper is damper
    final = default_store(mp, ns=NS, client=healthy_client())
    final.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert clock.sleeps == [0.125, 0.25]


def test_g13_per_call_ladder_climb_t2_j0p25(mp):
    """Per-call store construction climbs the shared ladder across instances."""
    damper, clock = shared_damper(NS, jitter=0.25)
    for _ in range(2):
        store = default_store(mp, ns=NS, client=exhausting_client())
        exhaust_run(store, 'batch_provider_stt', times=1)
        assert store._storm_damper is damper
    final = default_store(mp, ns=NS, client=healthy_client())
    final.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert clock.sleeps == [0.15625, 0.3125]


def test_g13_per_call_ladder_climb_t2_j0p5(mp):
    """Per-call store construction climbs the shared ladder across instances."""
    damper, clock = shared_damper(NS, jitter=0.5)
    for _ in range(2):
        store = default_store(mp, ns=NS, client=exhausting_client())
        exhaust_run(store, 'batch_provider_stt', times=1)
        assert store._storm_damper is damper
    final = default_store(mp, ns=NS, client=healthy_client())
    final.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert clock.sleeps == [0.1875, 0.375]


def test_g13_per_call_ladder_climb_t2_j1p0(mp):
    """Per-call store construction climbs the shared ladder across instances."""
    damper, clock = shared_damper(NS, jitter=1.0)
    for _ in range(2):
        store = default_store(mp, ns=NS, client=exhausting_client())
        exhaust_run(store, 'batch_provider_stt', times=1)
        assert store._storm_damper is damper
    final = default_store(mp, ns=NS, client=healthy_client())
    final.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert clock.sleeps == [0.25, 0.5]


def test_g13_per_call_ladder_climb_t3_j0p0(mp):
    """Per-call store construction climbs the shared ladder across instances."""
    damper, clock = shared_damper(NS, jitter=0.0)
    for _ in range(3):
        store = default_store(mp, ns=NS, client=exhausting_client())
        exhaust_run(store, 'batch_provider_stt', times=1)
        assert store._storm_damper is damper
    final = default_store(mp, ns=NS, client=healthy_client())
    final.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert clock.sleeps == [0.125, 0.25, 0.5]


def test_g13_per_call_ladder_climb_t3_j0p25(mp):
    """Per-call store construction climbs the shared ladder across instances."""
    damper, clock = shared_damper(NS, jitter=0.25)
    for _ in range(3):
        store = default_store(mp, ns=NS, client=exhausting_client())
        exhaust_run(store, 'batch_provider_stt', times=1)
        assert store._storm_damper is damper
    final = default_store(mp, ns=NS, client=healthy_client())
    final.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert clock.sleeps == [0.15625, 0.3125, 0.625]


def test_g13_per_call_ladder_climb_t3_j0p5(mp):
    """Per-call store construction climbs the shared ladder across instances."""
    damper, clock = shared_damper(NS, jitter=0.5)
    for _ in range(3):
        store = default_store(mp, ns=NS, client=exhausting_client())
        exhaust_run(store, 'batch_provider_stt', times=1)
        assert store._storm_damper is damper
    final = default_store(mp, ns=NS, client=healthy_client())
    final.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert clock.sleeps == [0.1875, 0.375, 0.75]


def test_g13_per_call_ladder_climb_t3_j1p0(mp):
    """Per-call store construction climbs the shared ladder across instances."""
    damper, clock = shared_damper(NS, jitter=1.0)
    for _ in range(3):
        store = default_store(mp, ns=NS, client=exhausting_client())
        exhaust_run(store, 'batch_provider_stt', times=1)
        assert store._storm_damper is damper
    final = default_store(mp, ns=NS, client=healthy_client())
    final.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert clock.sleeps == [0.25, 0.5, 1.0]


def test_g13_per_call_ladder_climb_t4_j0p0(mp):
    """Per-call store construction climbs the shared ladder across instances."""
    damper, clock = shared_damper(NS, jitter=0.0)
    for _ in range(4):
        store = default_store(mp, ns=NS, client=exhausting_client())
        exhaust_run(store, 'batch_provider_stt', times=1)
        assert store._storm_damper is damper
    final = default_store(mp, ns=NS, client=healthy_client())
    final.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert clock.sleeps == [0.125, 0.25, 0.5, 1.0]


def test_g13_per_call_ladder_climb_t4_j0p25(mp):
    """Per-call store construction climbs the shared ladder across instances."""
    damper, clock = shared_damper(NS, jitter=0.25)
    for _ in range(4):
        store = default_store(mp, ns=NS, client=exhausting_client())
        exhaust_run(store, 'batch_provider_stt', times=1)
        assert store._storm_damper is damper
    final = default_store(mp, ns=NS, client=healthy_client())
    final.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert clock.sleeps == [0.15625, 0.3125, 0.625, 1.25]


def test_g13_per_call_ladder_climb_t4_j0p5(mp):
    """Per-call store construction climbs the shared ladder across instances."""
    damper, clock = shared_damper(NS, jitter=0.5)
    for _ in range(4):
        store = default_store(mp, ns=NS, client=exhausting_client())
        exhaust_run(store, 'batch_provider_stt', times=1)
        assert store._storm_damper is damper
    final = default_store(mp, ns=NS, client=healthy_client())
    final.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert clock.sleeps == [0.1875, 0.375, 0.75, 1.5]


def test_g13_per_call_ladder_climb_t4_j1p0(mp):
    """Per-call store construction climbs the shared ladder across instances."""
    damper, clock = shared_damper(NS, jitter=1.0)
    for _ in range(4):
        store = default_store(mp, ns=NS, client=exhausting_client())
        exhaust_run(store, 'batch_provider_stt', times=1)
        assert store._storm_damper is damper
    final = default_store(mp, ns=NS, client=healthy_client())
    final.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert clock.sleeps == [0.25, 0.5, 1.0, 2.0]


def test_g13_per_call_ladder_climb_t5_j0p0(mp):
    """Per-call store construction climbs the shared ladder across instances."""
    damper, clock = shared_damper(NS, jitter=0.0)
    for _ in range(5):
        store = default_store(mp, ns=NS, client=exhausting_client())
        exhaust_run(store, 'batch_provider_stt', times=1)
        assert store._storm_damper is damper
    final = default_store(mp, ns=NS, client=healthy_client())
    final.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert clock.sleeps == [0.125, 0.25, 0.5, 1.0, 2.0]


def test_g13_per_call_ladder_climb_t5_j0p25(mp):
    """Per-call store construction climbs the shared ladder across instances."""
    damper, clock = shared_damper(NS, jitter=0.25)
    for _ in range(5):
        store = default_store(mp, ns=NS, client=exhausting_client())
        exhaust_run(store, 'batch_provider_stt', times=1)
        assert store._storm_damper is damper
    final = default_store(mp, ns=NS, client=healthy_client())
    final.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert clock.sleeps == [0.15625, 0.3125, 0.625, 1.25, 2.5]


def test_g13_per_call_ladder_climb_t5_j0p5(mp):
    """Per-call store construction climbs the shared ladder across instances."""
    damper, clock = shared_damper(NS, jitter=0.5)
    for _ in range(5):
        store = default_store(mp, ns=NS, client=exhausting_client())
        exhaust_run(store, 'batch_provider_stt', times=1)
        assert store._storm_damper is damper
    final = default_store(mp, ns=NS, client=healthy_client())
    final.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert clock.sleeps == [0.1875, 0.375, 0.75, 1.5, 3.0]


def test_g13_per_call_ladder_climb_t5_j1p0(mp):
    """Per-call store construction climbs the shared ladder across instances."""
    damper, clock = shared_damper(NS, jitter=1.0)
    for _ in range(5):
        store = default_store(mp, ns=NS, client=exhausting_client())
        exhaust_run(store, 'batch_provider_stt', times=1)
        assert store._storm_damper is damper
    final = default_store(mp, ns=NS, client=healthy_client())
    final.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert clock.sleeps == [0.25, 0.5, 1.0, 2.0, 4.0]


def test_g13_per_call_ladder_climb_t6_j0p0(mp):
    """Per-call store construction climbs the shared ladder across instances."""
    damper, clock = shared_damper(NS, jitter=0.0)
    for _ in range(6):
        store = default_store(mp, ns=NS, client=exhausting_client())
        exhaust_run(store, 'batch_provider_stt', times=1)
        assert store._storm_damper is damper
    final = default_store(mp, ns=NS, client=healthy_client())
    final.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert clock.sleeps == [0.125, 0.25, 0.5, 1.0, 2.0, 2.0]


def test_g13_per_call_ladder_climb_t6_j0p25(mp):
    """Per-call store construction climbs the shared ladder across instances."""
    damper, clock = shared_damper(NS, jitter=0.25)
    for _ in range(6):
        store = default_store(mp, ns=NS, client=exhausting_client())
        exhaust_run(store, 'batch_provider_stt', times=1)
        assert store._storm_damper is damper
    final = default_store(mp, ns=NS, client=healthy_client())
    final.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert clock.sleeps == [0.15625, 0.3125, 0.625, 1.25, 2.5, 2.5]


def test_g13_per_call_ladder_climb_t6_j0p5(mp):
    """Per-call store construction climbs the shared ladder across instances."""
    damper, clock = shared_damper(NS, jitter=0.5)
    for _ in range(6):
        store = default_store(mp, ns=NS, client=exhausting_client())
        exhaust_run(store, 'batch_provider_stt', times=1)
        assert store._storm_damper is damper
    final = default_store(mp, ns=NS, client=healthy_client())
    final.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert clock.sleeps == [0.1875, 0.375, 0.75, 1.5, 3.0, 3.0]


def test_g13_per_call_ladder_climb_t6_j1p0(mp):
    """Per-call store construction climbs the shared ladder across instances."""
    damper, clock = shared_damper(NS, jitter=1.0)
    for _ in range(6):
        store = default_store(mp, ns=NS, client=exhausting_client())
        exhaust_run(store, 'batch_provider_stt', times=1)
        assert store._storm_damper is damper
    final = default_store(mp, ns=NS, client=healthy_client())
    final.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert clock.sleeps == [0.25, 0.5, 1.0, 2.0, 4.0, 4.0]


def test_g13_per_call_ladder_climb_t7_j0p0(mp):
    """Per-call store construction climbs the shared ladder across instances."""
    damper, clock = shared_damper(NS, jitter=0.0)
    for _ in range(7):
        store = default_store(mp, ns=NS, client=exhausting_client())
        exhaust_run(store, 'batch_provider_stt', times=1)
        assert store._storm_damper is damper
    final = default_store(mp, ns=NS, client=healthy_client())
    final.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert clock.sleeps == [0.125, 0.25, 0.5, 1.0, 2.0, 2.0, 2.0]


def test_g13_per_call_ladder_climb_t7_j0p25(mp):
    """Per-call store construction climbs the shared ladder across instances."""
    damper, clock = shared_damper(NS, jitter=0.25)
    for _ in range(7):
        store = default_store(mp, ns=NS, client=exhausting_client())
        exhaust_run(store, 'batch_provider_stt', times=1)
        assert store._storm_damper is damper
    final = default_store(mp, ns=NS, client=healthy_client())
    final.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert clock.sleeps == [0.15625, 0.3125, 0.625, 1.25, 2.5, 2.5, 2.5]


def test_g13_per_call_ladder_climb_t7_j0p5(mp):
    """Per-call store construction climbs the shared ladder across instances."""
    damper, clock = shared_damper(NS, jitter=0.5)
    for _ in range(7):
        store = default_store(mp, ns=NS, client=exhausting_client())
        exhaust_run(store, 'batch_provider_stt', times=1)
        assert store._storm_damper is damper
    final = default_store(mp, ns=NS, client=healthy_client())
    final.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert clock.sleeps == [0.1875, 0.375, 0.75, 1.5, 3.0, 3.0, 3.0]


def test_g13_per_call_ladder_climb_t7_j1p0(mp):
    """Per-call store construction climbs the shared ladder across instances."""
    damper, clock = shared_damper(NS, jitter=1.0)
    for _ in range(7):
        store = default_store(mp, ns=NS, client=exhausting_client())
        exhaust_run(store, 'batch_provider_stt', times=1)
        assert store._storm_damper is damper
    final = default_store(mp, ns=NS, client=healthy_client())
    final.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert clock.sleeps == [0.25, 0.5, 1.0, 2.0, 4.0, 4.0, 4.0]


def test_g13_per_call_ladder_climb_t8_j0p0(mp):
    """Per-call store construction climbs the shared ladder across instances."""
    damper, clock = shared_damper(NS, jitter=0.0)
    for _ in range(8):
        store = default_store(mp, ns=NS, client=exhausting_client())
        exhaust_run(store, 'batch_provider_stt', times=1)
        assert store._storm_damper is damper
    final = default_store(mp, ns=NS, client=healthy_client())
    final.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert clock.sleeps == [0.125, 0.25, 0.5, 1.0, 2.0, 2.0, 2.0, 2.0]


def test_g13_per_call_ladder_climb_t8_j0p25(mp):
    """Per-call store construction climbs the shared ladder across instances."""
    damper, clock = shared_damper(NS, jitter=0.25)
    for _ in range(8):
        store = default_store(mp, ns=NS, client=exhausting_client())
        exhaust_run(store, 'batch_provider_stt', times=1)
        assert store._storm_damper is damper
    final = default_store(mp, ns=NS, client=healthy_client())
    final.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert clock.sleeps == [0.15625, 0.3125, 0.625, 1.25, 2.5, 2.5, 2.5, 2.5]


def test_g13_per_call_ladder_climb_t8_j0p5(mp):
    """Per-call store construction climbs the shared ladder across instances."""
    damper, clock = shared_damper(NS, jitter=0.5)
    for _ in range(8):
        store = default_store(mp, ns=NS, client=exhausting_client())
        exhaust_run(store, 'batch_provider_stt', times=1)
        assert store._storm_damper is damper
    final = default_store(mp, ns=NS, client=healthy_client())
    final.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert clock.sleeps == [0.1875, 0.375, 0.75, 1.5, 3.0, 3.0, 3.0, 3.0]


def test_g13_per_call_ladder_climb_t8_j1p0(mp):
    """Per-call store construction climbs the shared ladder across instances."""
    damper, clock = shared_damper(NS, jitter=1.0)
    for _ in range(8):
        store = default_store(mp, ns=NS, client=exhausting_client())
        exhaust_run(store, 'batch_provider_stt', times=1)
        assert store._storm_damper is damper
    final = default_store(mp, ns=NS, client=healthy_client())
    final.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert clock.sleeps == [0.25, 0.5, 1.0, 2.0, 4.0, 4.0, 4.0, 4.0]


def test_g13_per_call_ladder_climb_t9_j0p0(mp):
    """Per-call store construction climbs the shared ladder across instances."""
    damper, clock = shared_damper(NS, jitter=0.0)
    for _ in range(9):
        store = default_store(mp, ns=NS, client=exhausting_client())
        exhaust_run(store, 'batch_provider_stt', times=1)
        assert store._storm_damper is damper
    final = default_store(mp, ns=NS, client=healthy_client())
    final.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert clock.sleeps == [0.125, 0.25, 0.5, 1.0, 2.0, 2.0, 2.0, 2.0, 2.0]


def test_g13_per_call_ladder_climb_t9_j0p25(mp):
    """Per-call store construction climbs the shared ladder across instances."""
    damper, clock = shared_damper(NS, jitter=0.25)
    for _ in range(9):
        store = default_store(mp, ns=NS, client=exhausting_client())
        exhaust_run(store, 'batch_provider_stt', times=1)
        assert store._storm_damper is damper
    final = default_store(mp, ns=NS, client=healthy_client())
    final.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert clock.sleeps == [0.15625, 0.3125, 0.625, 1.25, 2.5, 2.5, 2.5, 2.5, 2.5]


def test_g13_per_call_ladder_climb_t9_j0p5(mp):
    """Per-call store construction climbs the shared ladder across instances."""
    damper, clock = shared_damper(NS, jitter=0.5)
    for _ in range(9):
        store = default_store(mp, ns=NS, client=exhausting_client())
        exhaust_run(store, 'batch_provider_stt', times=1)
        assert store._storm_damper is damper
    final = default_store(mp, ns=NS, client=healthy_client())
    final.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert clock.sleeps == [0.1875, 0.375, 0.75, 1.5, 3.0, 3.0, 3.0, 3.0, 3.0]


def test_g13_per_call_ladder_climb_t9_j1p0(mp):
    """Per-call store construction climbs the shared ladder across instances."""
    damper, clock = shared_damper(NS, jitter=1.0)
    for _ in range(9):
        store = default_store(mp, ns=NS, client=exhausting_client())
        exhaust_run(store, 'batch_provider_stt', times=1)
        assert store._storm_damper is damper
    final = default_store(mp, ns=NS, client=healthy_client())
    final.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert clock.sleeps == [0.25, 0.5, 1.0, 2.0, 4.0, 4.0, 4.0, 4.0, 4.0]


def test_g13_per_call_ladder_climb_t10_j0p0(mp):
    """Per-call store construction climbs the shared ladder across instances."""
    damper, clock = shared_damper(NS, jitter=0.0)
    for _ in range(10):
        store = default_store(mp, ns=NS, client=exhausting_client())
        exhaust_run(store, 'batch_provider_stt', times=1)
        assert store._storm_damper is damper
    final = default_store(mp, ns=NS, client=healthy_client())
    final.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert clock.sleeps == [0.125, 0.25, 0.5, 1.0, 2.0, 2.0, 2.0, 2.0, 2.0, 2.0]


def test_g13_per_call_ladder_climb_t10_j0p25(mp):
    """Per-call store construction climbs the shared ladder across instances."""
    damper, clock = shared_damper(NS, jitter=0.25)
    for _ in range(10):
        store = default_store(mp, ns=NS, client=exhausting_client())
        exhaust_run(store, 'batch_provider_stt', times=1)
        assert store._storm_damper is damper
    final = default_store(mp, ns=NS, client=healthy_client())
    final.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert clock.sleeps == [0.15625, 0.3125, 0.625, 1.25, 2.5, 2.5, 2.5, 2.5, 2.5, 2.5]


def test_g13_per_call_ladder_climb_t10_j0p5(mp):
    """Per-call store construction climbs the shared ladder across instances."""
    damper, clock = shared_damper(NS, jitter=0.5)
    for _ in range(10):
        store = default_store(mp, ns=NS, client=exhausting_client())
        exhaust_run(store, 'batch_provider_stt', times=1)
        assert store._storm_damper is damper
    final = default_store(mp, ns=NS, client=healthy_client())
    final.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert clock.sleeps == [0.1875, 0.375, 0.75, 1.5, 3.0, 3.0, 3.0, 3.0, 3.0, 3.0]


def test_g13_per_call_ladder_climb_t10_j1p0(mp):
    """Per-call store construction climbs the shared ladder across instances."""
    damper, clock = shared_damper(NS, jitter=1.0)
    for _ in range(10):
        store = default_store(mp, ns=NS, client=exhausting_client())
        exhaust_run(store, 'batch_provider_stt', times=1)
        assert store._storm_damper is damper
    final = default_store(mp, ns=NS, client=healthy_client())
    final.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert clock.sleeps == [0.25, 0.5, 1.0, 2.0, 4.0, 4.0, 4.0, 4.0, 4.0, 4.0]


def test_g15_wave_rung_draw_never_recorded_a3_j0p0(mp):
    """The per-rung wave wait is computed, never recorded on the shared state."""
    damper, _clock = shared_damper(NS, jitter=0.0)
    wait = damper.wave_rung_wait(3)
    assert wait == pytest.approx(0.5)
    assert damper._generations == {}
    assert damper._armed_until == {}
    assert damper._failures == {}


def test_g15_wave_rung_draw_never_recorded_a3_j0p25(mp):
    """The per-rung wave wait is computed, never recorded on the shared state."""
    damper, _clock = shared_damper(NS, jitter=0.25)
    wait = damper.wave_rung_wait(3)
    assert wait == pytest.approx(0.625)
    assert damper._generations == {}
    assert damper._armed_until == {}
    assert damper._failures == {}


def test_g15_wave_rung_draw_never_recorded_a3_j0p5(mp):
    """The per-rung wave wait is computed, never recorded on the shared state."""
    damper, _clock = shared_damper(NS, jitter=0.5)
    wait = damper.wave_rung_wait(3)
    assert wait == pytest.approx(0.75)
    assert damper._generations == {}
    assert damper._armed_until == {}
    assert damper._failures == {}


def test_g15_wave_rung_draw_never_recorded_a3_j1p0(mp):
    """The per-rung wave wait is computed, never recorded on the shared state."""
    damper, _clock = shared_damper(NS, jitter=1.0)
    wait = damper.wave_rung_wait(3)
    assert wait == pytest.approx(1.0)
    assert damper._generations == {}
    assert damper._armed_until == {}
    assert damper._failures == {}


def test_g15_wave_rung_draw_never_recorded_a4_j0p0(mp):
    """The per-rung wave wait is computed, never recorded on the shared state."""
    damper, _clock = shared_damper(NS, jitter=0.0)
    wait = damper.wave_rung_wait(4)
    assert wait == pytest.approx(1.0)
    assert damper._generations == {}
    assert damper._armed_until == {}
    assert damper._failures == {}


def test_g15_wave_rung_draw_never_recorded_a4_j0p25(mp):
    """The per-rung wave wait is computed, never recorded on the shared state."""
    damper, _clock = shared_damper(NS, jitter=0.25)
    wait = damper.wave_rung_wait(4)
    assert wait == pytest.approx(1.25)
    assert damper._generations == {}
    assert damper._armed_until == {}
    assert damper._failures == {}


def test_g15_wave_rung_draw_never_recorded_a4_j0p5(mp):
    """The per-rung wave wait is computed, never recorded on the shared state."""
    damper, _clock = shared_damper(NS, jitter=0.5)
    wait = damper.wave_rung_wait(4)
    assert wait == pytest.approx(1.5)
    assert damper._generations == {}
    assert damper._armed_until == {}
    assert damper._failures == {}


def test_g15_wave_rung_draw_never_recorded_a4_j1p0(mp):
    """The per-rung wave wait is computed, never recorded on the shared state."""
    damper, _clock = shared_damper(NS, jitter=1.0)
    wait = damper.wave_rung_wait(4)
    assert wait == pytest.approx(2.0)
    assert damper._generations == {}
    assert damper._armed_until == {}
    assert damper._failures == {}


def test_g15_wave_rung_draw_never_recorded_a5_j0p0(mp):
    """The per-rung wave wait is computed, never recorded on the shared state."""
    damper, _clock = shared_damper(NS, jitter=0.0)
    wait = damper.wave_rung_wait(5)
    assert wait == pytest.approx(2.0)
    assert damper._generations == {}
    assert damper._armed_until == {}
    assert damper._failures == {}


def test_g15_wave_rung_draw_never_recorded_a5_j0p25(mp):
    """The per-rung wave wait is computed, never recorded on the shared state."""
    damper, _clock = shared_damper(NS, jitter=0.25)
    wait = damper.wave_rung_wait(5)
    assert wait == pytest.approx(2.5)
    assert damper._generations == {}
    assert damper._armed_until == {}
    assert damper._failures == {}


def test_g15_wave_rung_draw_never_recorded_a5_j0p5(mp):
    """The per-rung wave wait is computed, never recorded on the shared state."""
    damper, _clock = shared_damper(NS, jitter=0.5)
    wait = damper.wave_rung_wait(5)
    assert wait == pytest.approx(3.0)
    assert damper._generations == {}
    assert damper._armed_until == {}
    assert damper._failures == {}


def test_g15_wave_rung_draw_never_recorded_a5_j1p0(mp):
    """The per-rung wave wait is computed, never recorded on the shared state."""
    damper, _clock = shared_damper(NS, jitter=1.0)
    wait = damper.wave_rung_wait(5)
    assert wait == pytest.approx(4.0)
    assert damper._generations == {}
    assert damper._armed_until == {}
    assert damper._failures == {}


def test_g15_wave_rung_draw_never_recorded_a6_j0p0(mp):
    """The per-rung wave wait is computed, never recorded on the shared state."""
    damper, _clock = shared_damper(NS, jitter=0.0)
    wait = damper.wave_rung_wait(6)
    assert wait == pytest.approx(2.0)
    assert damper._generations == {}
    assert damper._armed_until == {}
    assert damper._failures == {}


def test_g15_wave_rung_draw_never_recorded_a6_j0p25(mp):
    """The per-rung wave wait is computed, never recorded on the shared state."""
    damper, _clock = shared_damper(NS, jitter=0.25)
    wait = damper.wave_rung_wait(6)
    assert wait == pytest.approx(2.5)
    assert damper._generations == {}
    assert damper._armed_until == {}
    assert damper._failures == {}


def test_g15_wave_rung_draw_never_recorded_a6_j0p5(mp):
    """The per-rung wave wait is computed, never recorded on the shared state."""
    damper, _clock = shared_damper(NS, jitter=0.5)
    wait = damper.wave_rung_wait(6)
    assert wait == pytest.approx(3.0)
    assert damper._generations == {}
    assert damper._armed_until == {}
    assert damper._failures == {}


def test_g15_wave_rung_draw_never_recorded_a6_j1p0(mp):
    """The per-rung wave wait is computed, never recorded on the shared state."""
    damper, _clock = shared_damper(NS, jitter=1.0)
    wait = damper.wave_rung_wait(6)
    assert wait == pytest.approx(4.0)
    assert damper._generations == {}
    assert damper._armed_until == {}
    assert damper._failures == {}


def test_g15_wave_rung_draw_never_recorded_a7_j0p0(mp):
    """The per-rung wave wait is computed, never recorded on the shared state."""
    damper, _clock = shared_damper(NS, jitter=0.0)
    wait = damper.wave_rung_wait(7)
    assert wait == pytest.approx(2.0)
    assert damper._generations == {}
    assert damper._armed_until == {}
    assert damper._failures == {}


def test_g15_wave_rung_draw_never_recorded_a7_j0p25(mp):
    """The per-rung wave wait is computed, never recorded on the shared state."""
    damper, _clock = shared_damper(NS, jitter=0.25)
    wait = damper.wave_rung_wait(7)
    assert wait == pytest.approx(2.5)
    assert damper._generations == {}
    assert damper._armed_until == {}
    assert damper._failures == {}


def test_g15_wave_rung_draw_never_recorded_a7_j0p5(mp):
    """The per-rung wave wait is computed, never recorded on the shared state."""
    damper, _clock = shared_damper(NS, jitter=0.5)
    wait = damper.wave_rung_wait(7)
    assert wait == pytest.approx(3.0)
    assert damper._generations == {}
    assert damper._armed_until == {}
    assert damper._failures == {}


def test_g15_wave_rung_draw_never_recorded_a7_j1p0(mp):
    """The per-rung wave wait is computed, never recorded on the shared state."""
    damper, _clock = shared_damper(NS, jitter=1.0)
    wait = damper.wave_rung_wait(7)
    assert wait == pytest.approx(4.0)
    assert damper._generations == {}
    assert damper._armed_until == {}
    assert damper._failures == {}


def test_g15_wave_rung_draw_never_recorded_a8_j0p0(mp):
    """The per-rung wave wait is computed, never recorded on the shared state."""
    damper, _clock = shared_damper(NS, jitter=0.0)
    wait = damper.wave_rung_wait(8)
    assert wait == pytest.approx(2.0)
    assert damper._generations == {}
    assert damper._armed_until == {}
    assert damper._failures == {}


def test_g15_wave_rung_draw_never_recorded_a8_j0p25(mp):
    """The per-rung wave wait is computed, never recorded on the shared state."""
    damper, _clock = shared_damper(NS, jitter=0.25)
    wait = damper.wave_rung_wait(8)
    assert wait == pytest.approx(2.5)
    assert damper._generations == {}
    assert damper._armed_until == {}
    assert damper._failures == {}


def test_g15_wave_rung_draw_never_recorded_a8_j0p5(mp):
    """The per-rung wave wait is computed, never recorded on the shared state."""
    damper, _clock = shared_damper(NS, jitter=0.5)
    wait = damper.wave_rung_wait(8)
    assert wait == pytest.approx(3.0)
    assert damper._generations == {}
    assert damper._armed_until == {}
    assert damper._failures == {}


def test_g15_wave_rung_draw_never_recorded_a8_j1p0(mp):
    """The per-rung wave wait is computed, never recorded on the shared state."""
    damper, _clock = shared_damper(NS, jitter=1.0)
    wait = damper.wave_rung_wait(8)
    assert wait == pytest.approx(4.0)
    assert damper._generations == {}
    assert damper._armed_until == {}
    assert damper._failures == {}


def test_g15_wave_rung_draw_never_recorded_a9_j0p0(mp):
    """The per-rung wave wait is computed, never recorded on the shared state."""
    damper, _clock = shared_damper(NS, jitter=0.0)
    wait = damper.wave_rung_wait(9)
    assert wait == pytest.approx(2.0)
    assert damper._generations == {}
    assert damper._armed_until == {}
    assert damper._failures == {}


def test_g15_wave_rung_draw_never_recorded_a9_j0p25(mp):
    """The per-rung wave wait is computed, never recorded on the shared state."""
    damper, _clock = shared_damper(NS, jitter=0.25)
    wait = damper.wave_rung_wait(9)
    assert wait == pytest.approx(2.5)
    assert damper._generations == {}
    assert damper._armed_until == {}
    assert damper._failures == {}


def test_g15_wave_rung_draw_never_recorded_a9_j0p5(mp):
    """The per-rung wave wait is computed, never recorded on the shared state."""
    damper, _clock = shared_damper(NS, jitter=0.5)
    wait = damper.wave_rung_wait(9)
    assert wait == pytest.approx(3.0)
    assert damper._generations == {}
    assert damper._armed_until == {}
    assert damper._failures == {}


def test_g15_wave_rung_draw_never_recorded_a9_j1p0(mp):
    """The per-rung wave wait is computed, never recorded on the shared state."""
    damper, _clock = shared_damper(NS, jitter=1.0)
    wait = damper.wave_rung_wait(9)
    assert wait == pytest.approx(4.0)
    assert damper._generations == {}
    assert damper._armed_until == {}
    assert damper._failures == {}


def test_g15_wave_rung_draw_never_recorded_a10_j0p0(mp):
    """The per-rung wave wait is computed, never recorded on the shared state."""
    damper, _clock = shared_damper(NS, jitter=0.0)
    wait = damper.wave_rung_wait(10)
    assert wait == pytest.approx(2.0)
    assert damper._generations == {}
    assert damper._armed_until == {}
    assert damper._failures == {}


def test_g15_wave_rung_draw_never_recorded_a10_j0p25(mp):
    """The per-rung wave wait is computed, never recorded on the shared state."""
    damper, _clock = shared_damper(NS, jitter=0.25)
    wait = damper.wave_rung_wait(10)
    assert wait == pytest.approx(2.5)
    assert damper._generations == {}
    assert damper._armed_until == {}
    assert damper._failures == {}


def test_g15_wave_rung_draw_never_recorded_a10_j0p5(mp):
    """The per-rung wave wait is computed, never recorded on the shared state."""
    damper, _clock = shared_damper(NS, jitter=0.5)
    wait = damper.wave_rung_wait(10)
    assert wait == pytest.approx(3.0)
    assert damper._generations == {}
    assert damper._armed_until == {}
    assert damper._failures == {}


def test_g15_wave_rung_draw_never_recorded_a10_j1p0(mp):
    """The per-rung wave wait is computed, never recorded on the shared state."""
    damper, _clock = shared_damper(NS, jitter=1.0)
    wait = damper.wave_rung_wait(10)
    assert wait == pytest.approx(4.0)
    assert damper._generations == {}
    assert damper._armed_until == {}
    assert damper._failures == {}


def test_g16_entry_backoff_log_batch_merge_commit_k1_j0p0(mp, caplog):
    """The sibling's entry wait logs the exact INFO taxonomy line."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=1)
    B = default_store(mp, ns=NS, client=healthy_client())
    with caplog.at_level(logging.INFO, logger='database.batch_pipeline_store'):
        B.run(lambda tx: 'ok', operation='batch_merge_commit')
    lines = [r.getMessage() for r in caplog.records if 'event=batch_store_backoff' in r.getMessage()]
    assert lines == ['event=batch_store_backoff operation=batch_merge_commit waited_ms=125']


def test_g16_entry_backoff_log_batch_merge_commit_k1_j0p25(mp, caplog):
    """The sibling's entry wait logs the exact INFO taxonomy line."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=1)
    B = default_store(mp, ns=NS, client=healthy_client())
    with caplog.at_level(logging.INFO, logger='database.batch_pipeline_store'):
        B.run(lambda tx: 'ok', operation='batch_merge_commit')
    lines = [r.getMessage() for r in caplog.records if 'event=batch_store_backoff' in r.getMessage()]
    assert lines == ['event=batch_store_backoff operation=batch_merge_commit waited_ms=156']


def test_g16_entry_backoff_log_batch_merge_commit_k1_j0p5(mp, caplog):
    """The sibling's entry wait logs the exact INFO taxonomy line."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=1)
    B = default_store(mp, ns=NS, client=healthy_client())
    with caplog.at_level(logging.INFO, logger='database.batch_pipeline_store'):
        B.run(lambda tx: 'ok', operation='batch_merge_commit')
    lines = [r.getMessage() for r in caplog.records if 'event=batch_store_backoff' in r.getMessage()]
    assert lines == ['event=batch_store_backoff operation=batch_merge_commit waited_ms=188']


def test_g16_entry_backoff_log_batch_merge_commit_k1_j1p0(mp, caplog):
    """The sibling's entry wait logs the exact INFO taxonomy line."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=1)
    B = default_store(mp, ns=NS, client=healthy_client())
    with caplog.at_level(logging.INFO, logger='database.batch_pipeline_store'):
        B.run(lambda tx: 'ok', operation='batch_merge_commit')
    lines = [r.getMessage() for r in caplog.records if 'event=batch_store_backoff' in r.getMessage()]
    assert lines == ['event=batch_store_backoff operation=batch_merge_commit waited_ms=250']


def test_g16_entry_backoff_log_batch_merge_commit_k3_j0p0(mp, caplog):
    """The sibling's entry wait logs the exact INFO taxonomy line."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=3)
    B = default_store(mp, ns=NS, client=healthy_client())
    with caplog.at_level(logging.INFO, logger='database.batch_pipeline_store'):
        B.run(lambda tx: 'ok', operation='batch_merge_commit')
    lines = [r.getMessage() for r in caplog.records if 'event=batch_store_backoff' in r.getMessage()]
    assert lines == ['event=batch_store_backoff operation=batch_merge_commit waited_ms=500']


def test_g16_entry_backoff_log_batch_merge_commit_k3_j0p25(mp, caplog):
    """The sibling's entry wait logs the exact INFO taxonomy line."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=3)
    B = default_store(mp, ns=NS, client=healthy_client())
    with caplog.at_level(logging.INFO, logger='database.batch_pipeline_store'):
        B.run(lambda tx: 'ok', operation='batch_merge_commit')
    lines = [r.getMessage() for r in caplog.records if 'event=batch_store_backoff' in r.getMessage()]
    assert lines == ['event=batch_store_backoff operation=batch_merge_commit waited_ms=625']


def test_g16_entry_backoff_log_batch_merge_commit_k3_j0p5(mp, caplog):
    """The sibling's entry wait logs the exact INFO taxonomy line."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=3)
    B = default_store(mp, ns=NS, client=healthy_client())
    with caplog.at_level(logging.INFO, logger='database.batch_pipeline_store'):
        B.run(lambda tx: 'ok', operation='batch_merge_commit')
    lines = [r.getMessage() for r in caplog.records if 'event=batch_store_backoff' in r.getMessage()]
    assert lines == ['event=batch_store_backoff operation=batch_merge_commit waited_ms=750']


def test_g16_entry_backoff_log_batch_merge_commit_k3_j1p0(mp, caplog):
    """The sibling's entry wait logs the exact INFO taxonomy line."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_merge_commit', times=3)
    B = default_store(mp, ns=NS, client=healthy_client())
    with caplog.at_level(logging.INFO, logger='database.batch_pipeline_store'):
        B.run(lambda tx: 'ok', operation='batch_merge_commit')
    lines = [r.getMessage() for r in caplog.records if 'event=batch_store_backoff' in r.getMessage()]
    assert lines == ['event=batch_store_backoff operation=batch_merge_commit waited_ms=1000']


def test_g16_entry_backoff_log_batch_provider_stt_k1_j0p0(mp, caplog):
    """The sibling's entry wait logs the exact INFO taxonomy line."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=1)
    B = default_store(mp, ns=NS, client=healthy_client())
    with caplog.at_level(logging.INFO, logger='database.batch_pipeline_store'):
        B.run(lambda tx: 'ok', operation='batch_provider_stt')
    lines = [r.getMessage() for r in caplog.records if 'event=batch_store_backoff' in r.getMessage()]
    assert lines == ['event=batch_store_backoff operation=batch_provider_stt waited_ms=125']


def test_g16_entry_backoff_log_batch_provider_stt_k1_j0p25(mp, caplog):
    """The sibling's entry wait logs the exact INFO taxonomy line."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=1)
    B = default_store(mp, ns=NS, client=healthy_client())
    with caplog.at_level(logging.INFO, logger='database.batch_pipeline_store'):
        B.run(lambda tx: 'ok', operation='batch_provider_stt')
    lines = [r.getMessage() for r in caplog.records if 'event=batch_store_backoff' in r.getMessage()]
    assert lines == ['event=batch_store_backoff operation=batch_provider_stt waited_ms=156']


def test_g16_entry_backoff_log_batch_provider_stt_k1_j0p5(mp, caplog):
    """The sibling's entry wait logs the exact INFO taxonomy line."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=1)
    B = default_store(mp, ns=NS, client=healthy_client())
    with caplog.at_level(logging.INFO, logger='database.batch_pipeline_store'):
        B.run(lambda tx: 'ok', operation='batch_provider_stt')
    lines = [r.getMessage() for r in caplog.records if 'event=batch_store_backoff' in r.getMessage()]
    assert lines == ['event=batch_store_backoff operation=batch_provider_stt waited_ms=188']


def test_g16_entry_backoff_log_batch_provider_stt_k1_j1p0(mp, caplog):
    """The sibling's entry wait logs the exact INFO taxonomy line."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=1)
    B = default_store(mp, ns=NS, client=healthy_client())
    with caplog.at_level(logging.INFO, logger='database.batch_pipeline_store'):
        B.run(lambda tx: 'ok', operation='batch_provider_stt')
    lines = [r.getMessage() for r in caplog.records if 'event=batch_store_backoff' in r.getMessage()]
    assert lines == ['event=batch_store_backoff operation=batch_provider_stt waited_ms=250']


def test_g16_entry_backoff_log_batch_provider_stt_k3_j0p0(mp, caplog):
    """The sibling's entry wait logs the exact INFO taxonomy line."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=3)
    B = default_store(mp, ns=NS, client=healthy_client())
    with caplog.at_level(logging.INFO, logger='database.batch_pipeline_store'):
        B.run(lambda tx: 'ok', operation='batch_provider_stt')
    lines = [r.getMessage() for r in caplog.records if 'event=batch_store_backoff' in r.getMessage()]
    assert lines == ['event=batch_store_backoff operation=batch_provider_stt waited_ms=500']


def test_g16_entry_backoff_log_batch_provider_stt_k3_j0p25(mp, caplog):
    """The sibling's entry wait logs the exact INFO taxonomy line."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=3)
    B = default_store(mp, ns=NS, client=healthy_client())
    with caplog.at_level(logging.INFO, logger='database.batch_pipeline_store'):
        B.run(lambda tx: 'ok', operation='batch_provider_stt')
    lines = [r.getMessage() for r in caplog.records if 'event=batch_store_backoff' in r.getMessage()]
    assert lines == ['event=batch_store_backoff operation=batch_provider_stt waited_ms=625']


def test_g16_entry_backoff_log_batch_provider_stt_k3_j0p5(mp, caplog):
    """The sibling's entry wait logs the exact INFO taxonomy line."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=3)
    B = default_store(mp, ns=NS, client=healthy_client())
    with caplog.at_level(logging.INFO, logger='database.batch_pipeline_store'):
        B.run(lambda tx: 'ok', operation='batch_provider_stt')
    lines = [r.getMessage() for r in caplog.records if 'event=batch_store_backoff' in r.getMessage()]
    assert lines == ['event=batch_store_backoff operation=batch_provider_stt waited_ms=750']


def test_g16_entry_backoff_log_batch_provider_stt_k3_j1p0(mp, caplog):
    """The sibling's entry wait logs the exact INFO taxonomy line."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_provider_stt', times=3)
    B = default_store(mp, ns=NS, client=healthy_client())
    with caplog.at_level(logging.INFO, logger='database.batch_pipeline_store'):
        B.run(lambda tx: 'ok', operation='batch_provider_stt')
    lines = [r.getMessage() for r in caplog.records if 'event=batch_store_backoff' in r.getMessage()]
    assert lines == ['event=batch_store_backoff operation=batch_provider_stt waited_ms=1000']


def test_g16_entry_backoff_log_batch_intake_status_k1_j0p0(mp, caplog):
    """The sibling's entry wait logs the exact INFO taxonomy line."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_intake_status', times=1)
    B = default_store(mp, ns=NS, client=healthy_client())
    with caplog.at_level(logging.INFO, logger='database.batch_pipeline_store'):
        B.run(lambda tx: 'ok', operation='batch_intake_status')
    lines = [r.getMessage() for r in caplog.records if 'event=batch_store_backoff' in r.getMessage()]
    assert lines == ['event=batch_store_backoff operation=batch_intake_status waited_ms=125']


def test_g16_entry_backoff_log_batch_intake_status_k1_j0p25(mp, caplog):
    """The sibling's entry wait logs the exact INFO taxonomy line."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_intake_status', times=1)
    B = default_store(mp, ns=NS, client=healthy_client())
    with caplog.at_level(logging.INFO, logger='database.batch_pipeline_store'):
        B.run(lambda tx: 'ok', operation='batch_intake_status')
    lines = [r.getMessage() for r in caplog.records if 'event=batch_store_backoff' in r.getMessage()]
    assert lines == ['event=batch_store_backoff operation=batch_intake_status waited_ms=156']


def test_g16_entry_backoff_log_batch_intake_status_k1_j0p5(mp, caplog):
    """The sibling's entry wait logs the exact INFO taxonomy line."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_intake_status', times=1)
    B = default_store(mp, ns=NS, client=healthy_client())
    with caplog.at_level(logging.INFO, logger='database.batch_pipeline_store'):
        B.run(lambda tx: 'ok', operation='batch_intake_status')
    lines = [r.getMessage() for r in caplog.records if 'event=batch_store_backoff' in r.getMessage()]
    assert lines == ['event=batch_store_backoff operation=batch_intake_status waited_ms=188']


def test_g16_entry_backoff_log_batch_intake_status_k1_j1p0(mp, caplog):
    """The sibling's entry wait logs the exact INFO taxonomy line."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_intake_status', times=1)
    B = default_store(mp, ns=NS, client=healthy_client())
    with caplog.at_level(logging.INFO, logger='database.batch_pipeline_store'):
        B.run(lambda tx: 'ok', operation='batch_intake_status')
    lines = [r.getMessage() for r in caplog.records if 'event=batch_store_backoff' in r.getMessage()]
    assert lines == ['event=batch_store_backoff operation=batch_intake_status waited_ms=250']


def test_g16_entry_backoff_log_batch_intake_status_k3_j0p0(mp, caplog):
    """The sibling's entry wait logs the exact INFO taxonomy line."""
    damper, clock = shared_damper(NS, jitter=0.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_intake_status', times=3)
    B = default_store(mp, ns=NS, client=healthy_client())
    with caplog.at_level(logging.INFO, logger='database.batch_pipeline_store'):
        B.run(lambda tx: 'ok', operation='batch_intake_status')
    lines = [r.getMessage() for r in caplog.records if 'event=batch_store_backoff' in r.getMessage()]
    assert lines == ['event=batch_store_backoff operation=batch_intake_status waited_ms=500']


def test_g16_entry_backoff_log_batch_intake_status_k3_j0p25(mp, caplog):
    """The sibling's entry wait logs the exact INFO taxonomy line."""
    damper, clock = shared_damper(NS, jitter=0.25)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_intake_status', times=3)
    B = default_store(mp, ns=NS, client=healthy_client())
    with caplog.at_level(logging.INFO, logger='database.batch_pipeline_store'):
        B.run(lambda tx: 'ok', operation='batch_intake_status')
    lines = [r.getMessage() for r in caplog.records if 'event=batch_store_backoff' in r.getMessage()]
    assert lines == ['event=batch_store_backoff operation=batch_intake_status waited_ms=625']


def test_g16_entry_backoff_log_batch_intake_status_k3_j0p5(mp, caplog):
    """The sibling's entry wait logs the exact INFO taxonomy line."""
    damper, clock = shared_damper(NS, jitter=0.5)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_intake_status', times=3)
    B = default_store(mp, ns=NS, client=healthy_client())
    with caplog.at_level(logging.INFO, logger='database.batch_pipeline_store'):
        B.run(lambda tx: 'ok', operation='batch_intake_status')
    lines = [r.getMessage() for r in caplog.records if 'event=batch_store_backoff' in r.getMessage()]
    assert lines == ['event=batch_store_backoff operation=batch_intake_status waited_ms=750']


def test_g16_entry_backoff_log_batch_intake_status_k3_j1p0(mp, caplog):
    """The sibling's entry wait logs the exact INFO taxonomy line."""
    damper, clock = shared_damper(NS, jitter=1.0)
    A = default_store(mp, ns=NS, client=exhausting_client())
    exhaust_run(A, 'batch_intake_status', times=3)
    B = default_store(mp, ns=NS, client=healthy_client())
    with caplog.at_level(logging.INFO, logger='database.batch_pipeline_store'):
        B.run(lambda tx: 'ok', operation='batch_intake_status')
    lines = [r.getMessage() for r in caplog.records if 'event=batch_store_backoff' in r.getMessage()]
    assert lines == ['event=batch_store_backoff operation=batch_intake_status waited_ms=1000']


def test_g14_doc_names_the_failure_class():
    doc = (BACKEND / 'docs' / 'batch-store-shared-storm-damper.md').read_text(encoding='utf-8')
    assert FC_TOKEN in doc


def test_g14_doc_names_the_registry_functions():
    doc = (BACKEND / 'docs' / 'batch-store-shared-storm-damper.md').read_text(encoding='utf-8')
    assert 'shared_storm_damper' in doc and 'reset_shared_storm_dampers' in doc


def test_g14_store_module_names_the_failure_class():
    source = (BACKEND / 'database' / 'batch_pipeline_store.py').read_text(encoding='utf-8')
    assert FC_TOKEN in source


def test_g14_grid_pins_the_documented_ladder_shape():
    assert BASE == storage.FirestoreStore.STORM_DAMPER_BASE_SECONDS
    assert CAP == storage.FirestoreStore.STORM_DAMPER_CAP_SECONDS
    assert STEPS == storage.FirestoreStore.STORM_DAMPER_LADDER_STEPS


def test_g14_grid_pins_wave_engagement_attempt():
    assert storage.FirestoreStore.WAVE_ENGAGEMENT_ATTEMPT == 3


def test_g14_grid_pins_the_label_cap():
    assert storage.FirestoreStore.STORM_DAMPER_MAX_TRACKED_LABELS == 64


def test_g14_registry_docstring_names_the_scope():
    doc = storage.shared_storm_damper.__doc__ or ''
    assert 'process-shared' in doc
    assert FC_TOKEN in doc


def test_g14_reset_docstring_names_the_seam():
    doc = storage.reset_shared_storm_dampers.__doc__ or ''
    assert 'reset' in doc.lower()
