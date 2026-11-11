"""Postgres jobstore exhaustion carries the window its chain applied.

``PostgresStore.run`` spaces its serialization/deadlock retries with a
jittered, bounded wait ("two bodies that deadlocked must not collide again
in lockstep"), then raises ``JobStoreContentionExhausted`` -- a subclass of
``FirestoreContentionExhausted`` that the pump's drain and re-strike lanes
catch. Before this fix the measurement died with the chain: the exhaustion
carried the default ``retry_after=0.0``, so the very next lane-level
re-offer fired blind into the same conflicting row on the bare ladder --
exactly the lockstep burn the jitter exists to prevent, one level up.

The contract pins the store's copy of the stamp ``FirestoreStore.run``
follows: the exhaustion carries the inter-attempt window the chain actually
applied, and the family's alignment consumers (``contention_retry_after``,
``publication_restrike_storm_after``) can act on it. Without the stamp,
every downstream re-offer against a postgres-conflicted owner collides
inside the residual window instead of landing after it -- the production
``batch_merge`` / ``batch_completion`` ``outcome=retry`` ERROR family.

Failure-Class: FC-publication-restrike-collides-inside-the-armed-storm-window
"""

from contextlib import contextmanager

import pytest

import database.jobstore.postgres_store as pg
from database.firestore_transaction_retry import FirestoreContentionExhausted
from utils.batch_pipeline.pump import (
    DRAIN_RETRY_MAX_SECONDS,
    contention_retry_after,
    publication_restrike_storm_after,
)


class SqlError(Exception):
    def __init__(self, sqlstate):
        super().__init__(sqlstate)
        self.sqlstate = sqlstate


class Conn:
    """Every statement fails retryably: the chain runs its full budget."""

    sqlstate = '40001'

    @contextmanager
    def transaction(self):
        yield

    def execute(self, sql, params=()):
        raise SqlError(self.sqlstate)


class CleanConn(Conn):
    sqlstate = None

    def execute(self, sql, params=()):
        return None


class Pool:
    def __init__(self, conn):
        self.conn = conn

    @contextmanager
    def connection(self, timeout: float = 30.0):
        yield self.conn


def store(conn):
    return pg.PostgresStore('batch_pipeline_test_stamp', pool=Pool(conn), customer_client=None)


@pytest.fixture
def fixed_jitter(monkeypatch):
    """Deterministic ladder: every retry waits exactly 0.11s; sleeps recorded."""
    recorded = []
    monkeypatch.setattr(pg.random, 'uniform', lambda low, high: 0.11)
    monkeypatch.setattr(pg.time, 'sleep', lambda seconds: recorded.append(seconds))
    return recorded


def test_exhausted_chain_stamps_the_window_it_applied(fixed_jitter):
    with pytest.raises(pg.JobStoreContentionExhausted) as excinfo:
        store(Conn()).run(lambda tx: None)
    assert excinfo.value.retry_after == pytest.approx(0.11)


def test_stamped_window_is_the_final_inter_attempt_wait(fixed_jitter):
    recorded = fixed_jitter
    with pytest.raises(pg.JobStoreContentionExhausted) as excinfo:
        store(Conn()).run(lambda tx: None)
    assert recorded, 'the chain must actually have waited'
    assert excinfo.value.retry_after == pytest.approx(recorded[-1])


def test_every_retry_of_the_chain_applies_the_jitter(fixed_jitter):
    recorded = fixed_jitter
    with pytest.raises(pg.JobStoreContentionExhausted):
        store(Conn()).run(lambda tx: None)
    assert len(recorded) == pg.MAX_SERIALIZATION_RETRIES - 1
    assert recorded == [0.11] * (pg.MAX_SERIALIZATION_RETRIES - 1)


def test_downstream_alignment_consumers_can_act_on_the_stamp(fixed_jitter):
    with pytest.raises(FirestoreContentionExhausted) as excinfo:
        store(Conn()).run(lambda tx: None)
    assert contention_retry_after(excinfo.value) == pytest.approx(min(0.11, DRAIN_RETRY_MAX_SECONDS))
    assert publication_restrike_storm_after(excinfo.value) == pytest.approx(min(0.11, 4.0))


def test_the_jitter_ladder_stays_bounded_even_unpatched(monkeypatch):
    recorded = []
    monkeypatch.setattr(pg.time, 'sleep', lambda seconds: recorded.append(seconds))
    with pytest.raises(pg.JobStoreContentionExhausted):
        store(Conn()).run(lambda tx: None)
    assert recorded
    assert all(0.0 < seconds <= 0.2 for seconds in recorded)


def test_first_attempt_success_returns_without_waiting(fixed_jitter):
    recorded = fixed_jitter
    marker = object()
    assert store(CleanConn()).run(lambda tx: marker) is marker
    assert recorded == []


def test_non_retryable_errors_propagate_untouched(monkeypatch):
    recorded = []
    monkeypatch.setattr(pg.time, 'sleep', lambda seconds: recorded.append(seconds))

    def poisoned(tx):
        raise ValueError('payload contract violation')

    with pytest.raises(ValueError) as excinfo:
        store(CleanConn()).run(poisoned)
    assert not isinstance(excinfo.value, FirestoreContentionExhausted)
    assert recorded == []


def test_partial_conflicts_still_converge(monkeypatch):
    """A body that conflicts twice then commits returns its result."""
    recorded = []
    monkeypatch.setattr(pg.time, 'sleep', lambda seconds: recorded.append(seconds))

    class FlakyConn(Conn):
        calls = 0

        def execute(self, sql, params=()):
            FlakyConn.calls += 1
            if FlakyConn.calls <= 2:
                raise SqlError('40001')
            return None

    marker = object()
    assert store(FlakyConn()).run(lambda tx: marker) is marker
    assert len(recorded) == 2
