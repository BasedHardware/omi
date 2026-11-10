"""Store-level storm stamping grid for the deferred-drain alignment signal.

Every ``FirestoreStore.run`` exhaustion arms the label's storm-damper window
and stamps the window it actually applied onto the raised
``FirestoreContentionExhausted.retry_after``. This grid pins that stamp per
real operation label, per ladder rung, per jitter point, plus the isolation,
success-clearing and consult-waiting contracts the stamp relies on, and the
sanitization grid the pump's deferred lane reads the signal through.

Failure-Class: FC-deferred-drain-restrike-collides-inside-the-armed-storm-window
"""

import types
from unittest.mock import Mock

import pytest
from google.api_core.exceptions import Aborted

from database import batch_pipeline_store as storage
from database.firestore_transaction_retry import FirestoreContentionExhausted

try:
    # Parent revisions without the stamp collect fine and fail at runtime below.
    from utils.batch_pipeline.pump import contention_retry_after
except ImportError:
    pass

BACKEND_CAP_SECONDS = storage.FirestoreStore.STORM_DAMPER_CAP_SECONDS
BASE_SECONDS = storage.FirestoreStore.STORM_DAMPER_BASE_SECONDS


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

    def __init__(self, now=100.0, jitter=1.0):
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

    def advance(self, seconds):
        self.now += seconds


def make_damper(clock=None):
    clock = clock or FakeClock()
    return (
        storage._ContentionStormDamper(monotonic=clock.monotonic, sleeper=clock.sleep, random_value=clock.random_value),
        clock,
    )


def exhausting_client():
    client = Mock()
    client.transaction.side_effect = lambda max_attempts=5: AbortThenCommitTx(10**6)
    return client


def build_store(monkeypatch, damper=None, client=None):
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    return storage.FirestoreStore(
        'batch_pipeline_dev',
        firestore_client=client if client is not None else exhausting_client(),
        storm_damper=damper,
    )


def exhaust_run(store, label, times=1):
    """Drive ``label`` to exhaustion ``times`` times; return the last error."""
    error = None
    for _ in range(times):
        try:
            store.run(lambda tx: True, operation=label)
        except FirestoreContentionExhausted as caught:
            error = caught
        else:
            raise AssertionError('expected exhaustion')
    return error


@pytest.fixture(autouse=True)
def fast_chain(monkeypatch):
    """Skip the retry chain's own jitter sleeps; the damper's stay injected."""
    actual = storage.run_with_transaction_contention_retry

    def factory(*args, **kwargs):
        kwargs.setdefault('sleep', lambda _seconds: None)
        return actual(*args, **kwargs)

    monkeypatch.setattr(storage, 'run_with_transaction_contention_retry', factory)


def neighbor_of(label):
    return 'batch_admit' if label != 'batch_admit' else 'batch_enqueue'


def make_healthy(store):
    """Flip the store's client from aborting to committing after a storm."""
    store._client.transaction.side_effect = lambda max_attempts=5: AbortThenCommitTx(0)
    return store


def make_exhausting(store):
    """Flip the store's client back to aborting for the next storm."""
    store._client.transaction.side_effect = lambda max_attempts=5: AbortThenCommitTx(10**6)
    return store


def test_store_stamp_merge_commit_exhaust_1_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_merge_commit', times=1)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.125)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_merge_commit_exhaust_1_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_merge_commit', times=1)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.25)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_merge_commit_exhaust_2_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_merge_commit', times=2)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.25)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_merge_commit_exhaust_2_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_merge_commit', times=2)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.5)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_merge_commit_exhaust_4_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_merge_commit', times=4)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(1.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_merge_commit_exhaust_4_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_merge_commit', times=4)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(2.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_merge_commit_exhaust_6_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_merge_commit', times=6)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(2.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_merge_commit_exhaust_6_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_merge_commit', times=6)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(4.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_admit_exhaust_1_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_admit', times=1)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.125)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_admit_exhaust_1_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_admit', times=1)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.25)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_admit_exhaust_2_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_admit', times=2)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.25)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_admit_exhaust_2_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_admit', times=2)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.5)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_admit_exhaust_4_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_admit', times=4)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(1.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_admit_exhaust_4_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_admit', times=4)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(2.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_admit_exhaust_6_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_admit', times=6)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(2.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_admit_exhaust_6_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_admit', times=6)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(4.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_content_ledger_accept_exhaust_1_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_content_ledger_accept', times=1)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.125)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_content_ledger_accept_exhaust_1_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_content_ledger_accept', times=1)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.25)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_content_ledger_accept_exhaust_2_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_content_ledger_accept', times=2)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.25)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_content_ledger_accept_exhaust_2_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_content_ledger_accept', times=2)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.5)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_content_ledger_accept_exhaust_4_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_content_ledger_accept', times=4)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(1.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_content_ledger_accept_exhaust_4_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_content_ledger_accept', times=4)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(2.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_content_ledger_accept_exhaust_6_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_content_ledger_accept', times=6)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(2.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_content_ledger_accept_exhaust_6_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_content_ledger_accept', times=6)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(4.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_recognizer_receipt_exhaust_1_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recognizer_receipt', times=1)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.125)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_recognizer_receipt_exhaust_1_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recognizer_receipt', times=1)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.25)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_recognizer_receipt_exhaust_2_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recognizer_receipt', times=2)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.25)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_recognizer_receipt_exhaust_2_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recognizer_receipt', times=2)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.5)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_recognizer_receipt_exhaust_4_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recognizer_receipt', times=4)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(1.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_recognizer_receipt_exhaust_4_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recognizer_receipt', times=4)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(2.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_recognizer_receipt_exhaust_6_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recognizer_receipt', times=6)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(2.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_recognizer_receipt_exhaust_6_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recognizer_receipt', times=6)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(4.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_recovery_prepare_exhaust_1_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recovery_prepare', times=1)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.125)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_recovery_prepare_exhaust_1_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recovery_prepare', times=1)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.25)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_recovery_prepare_exhaust_2_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recovery_prepare', times=2)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.25)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_recovery_prepare_exhaust_2_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recovery_prepare', times=2)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.5)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_recovery_prepare_exhaust_4_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recovery_prepare', times=4)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(1.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_recovery_prepare_exhaust_4_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recovery_prepare', times=4)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(2.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_recovery_prepare_exhaust_6_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recovery_prepare', times=6)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(2.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_recovery_prepare_exhaust_6_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recovery_prepare', times=6)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(4.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_recovery_claim_wake_exhaust_1_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recovery_claim_wake', times=1)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.125)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_recovery_claim_wake_exhaust_1_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recovery_claim_wake', times=1)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.25)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_recovery_claim_wake_exhaust_2_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recovery_claim_wake', times=2)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.25)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_recovery_claim_wake_exhaust_2_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recovery_claim_wake', times=2)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.5)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_recovery_claim_wake_exhaust_4_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recovery_claim_wake', times=4)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(1.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_recovery_claim_wake_exhaust_4_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recovery_claim_wake', times=4)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(2.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_recovery_claim_wake_exhaust_6_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recovery_claim_wake', times=6)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(2.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_recovery_claim_wake_exhaust_6_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recovery_claim_wake', times=6)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(4.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_recovery_extend_wake_exhaust_1_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recovery_extend_wake', times=1)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.125)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_recovery_extend_wake_exhaust_1_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recovery_extend_wake', times=1)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.25)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_recovery_extend_wake_exhaust_2_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recovery_extend_wake', times=2)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.25)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_recovery_extend_wake_exhaust_2_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recovery_extend_wake', times=2)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.5)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_recovery_extend_wake_exhaust_4_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recovery_extend_wake', times=4)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(1.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_recovery_extend_wake_exhaust_4_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recovery_extend_wake', times=4)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(2.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_recovery_extend_wake_exhaust_6_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recovery_extend_wake', times=6)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(2.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_recovery_extend_wake_exhaust_6_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recovery_extend_wake', times=6)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(4.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_recovery_shorten_wake_exhaust_1_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recovery_shorten_wake', times=1)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.125)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_recovery_shorten_wake_exhaust_1_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recovery_shorten_wake', times=1)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.25)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_recovery_shorten_wake_exhaust_2_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recovery_shorten_wake', times=2)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.25)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_recovery_shorten_wake_exhaust_2_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recovery_shorten_wake', times=2)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.5)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_recovery_shorten_wake_exhaust_4_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recovery_shorten_wake', times=4)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(1.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_recovery_shorten_wake_exhaust_4_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recovery_shorten_wake', times=4)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(2.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_recovery_shorten_wake_exhaust_6_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recovery_shorten_wake', times=6)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(2.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_recovery_shorten_wake_exhaust_6_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recovery_shorten_wake', times=6)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(4.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_recovery_start_exhaust_1_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recovery_start', times=1)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.125)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_recovery_start_exhaust_1_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recovery_start', times=1)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.25)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_recovery_start_exhaust_2_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recovery_start', times=2)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.25)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_recovery_start_exhaust_2_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recovery_start', times=2)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.5)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_recovery_start_exhaust_4_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recovery_start', times=4)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(1.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_recovery_start_exhaust_4_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recovery_start', times=4)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(2.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_recovery_start_exhaust_6_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recovery_start', times=6)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(2.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_recovery_start_exhaust_6_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recovery_start', times=6)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(4.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_recovery_observe_vad_exhaust_1_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recovery_observe_vad', times=1)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.125)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_recovery_observe_vad_exhaust_1_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recovery_observe_vad', times=1)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.25)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_recovery_observe_vad_exhaust_2_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recovery_observe_vad', times=2)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.25)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_recovery_observe_vad_exhaust_2_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recovery_observe_vad', times=2)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.5)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_recovery_observe_vad_exhaust_4_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recovery_observe_vad', times=4)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(1.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_recovery_observe_vad_exhaust_4_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recovery_observe_vad', times=4)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(2.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_recovery_observe_vad_exhaust_6_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recovery_observe_vad', times=6)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(2.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_recovery_observe_vad_exhaust_6_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recovery_observe_vad', times=6)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(4.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_recovery_retry_missing_result_exhaust_1_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recovery_retry_missing_result', times=1)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.125)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_recovery_retry_missing_result_exhaust_1_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recovery_retry_missing_result', times=1)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.25)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_recovery_retry_missing_result_exhaust_2_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recovery_retry_missing_result', times=2)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.25)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_recovery_retry_missing_result_exhaust_2_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recovery_retry_missing_result', times=2)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.5)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_recovery_retry_missing_result_exhaust_4_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recovery_retry_missing_result', times=4)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(1.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_recovery_retry_missing_result_exhaust_4_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recovery_retry_missing_result', times=4)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(2.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_recovery_retry_missing_result_exhaust_6_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recovery_retry_missing_result', times=6)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(2.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_recovery_retry_missing_result_exhaust_6_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recovery_retry_missing_result', times=6)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(4.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_recovery_hold_duration_limit_exhaust_1_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recovery_hold_duration_limit', times=1)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.125)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_recovery_hold_duration_limit_exhaust_1_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recovery_hold_duration_limit', times=1)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.25)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_recovery_hold_duration_limit_exhaust_2_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recovery_hold_duration_limit', times=2)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.25)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_recovery_hold_duration_limit_exhaust_2_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recovery_hold_duration_limit', times=2)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.5)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_recovery_hold_duration_limit_exhaust_4_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recovery_hold_duration_limit', times=4)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(1.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_recovery_hold_duration_limit_exhaust_4_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recovery_hold_duration_limit', times=4)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(2.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_recovery_hold_duration_limit_exhaust_6_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recovery_hold_duration_limit', times=6)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(2.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_recovery_hold_duration_limit_exhaust_6_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recovery_hold_duration_limit', times=6)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(4.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_recovery_hold_invalid_manifest_exhaust_1_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recovery_hold_invalid_manifest', times=1)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.125)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_recovery_hold_invalid_manifest_exhaust_1_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recovery_hold_invalid_manifest', times=1)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.25)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_recovery_hold_invalid_manifest_exhaust_2_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recovery_hold_invalid_manifest', times=2)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.25)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_recovery_hold_invalid_manifest_exhaust_2_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recovery_hold_invalid_manifest', times=2)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.5)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_recovery_hold_invalid_manifest_exhaust_4_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recovery_hold_invalid_manifest', times=4)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(1.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_recovery_hold_invalid_manifest_exhaust_4_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recovery_hold_invalid_manifest', times=4)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(2.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_recovery_hold_invalid_manifest_exhaust_6_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recovery_hold_invalid_manifest', times=6)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(2.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_recovery_hold_invalid_manifest_exhaust_6_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recovery_hold_invalid_manifest', times=6)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(4.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_recovery_start_duration_limited_exhaust_1_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recovery_start_duration_limited', times=1)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.125)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_recovery_start_duration_limited_exhaust_1_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recovery_start_duration_limited', times=1)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.25)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_recovery_start_duration_limited_exhaust_2_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recovery_start_duration_limited', times=2)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.25)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_recovery_start_duration_limited_exhaust_2_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recovery_start_duration_limited', times=2)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.5)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_recovery_start_duration_limited_exhaust_4_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recovery_start_duration_limited', times=4)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(1.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_recovery_start_duration_limited_exhaust_4_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recovery_start_duration_limited', times=4)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(2.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_recovery_start_duration_limited_exhaust_6_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recovery_start_duration_limited', times=6)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(2.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_recovery_start_duration_limited_exhaust_6_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recovery_start_duration_limited', times=6)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(4.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_recovery_paid_takeover_exhaust_1_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recovery_paid_takeover', times=1)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.125)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_recovery_paid_takeover_exhaust_1_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recovery_paid_takeover', times=1)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.25)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_recovery_paid_takeover_exhaust_2_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recovery_paid_takeover', times=2)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.25)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_recovery_paid_takeover_exhaust_2_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recovery_paid_takeover', times=2)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.5)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_recovery_paid_takeover_exhaust_4_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recovery_paid_takeover', times=4)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(1.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_recovery_paid_takeover_exhaust_4_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recovery_paid_takeover', times=4)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(2.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_recovery_paid_takeover_exhaust_6_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recovery_paid_takeover', times=6)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(2.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_recovery_paid_takeover_exhaust_6_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recovery_paid_takeover', times=6)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(4.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_recovery_settle_exhaust_1_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recovery_settle', times=1)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.125)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_recovery_settle_exhaust_1_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recovery_settle', times=1)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.25)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_recovery_settle_exhaust_2_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recovery_settle', times=2)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.25)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_recovery_settle_exhaust_2_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recovery_settle', times=2)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.5)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_recovery_settle_exhaust_4_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recovery_settle', times=4)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(1.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_recovery_settle_exhaust_4_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recovery_settle', times=4)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(2.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_recovery_settle_exhaust_6_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recovery_settle', times=6)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(2.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_recovery_settle_exhaust_6_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recovery_settle', times=6)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(4.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_recovery_silence_prepare_exhaust_1_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recovery_silence_prepare', times=1)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.125)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_recovery_silence_prepare_exhaust_1_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recovery_silence_prepare', times=1)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.25)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_recovery_silence_prepare_exhaust_2_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recovery_silence_prepare', times=2)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.25)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_recovery_silence_prepare_exhaust_2_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recovery_silence_prepare', times=2)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.5)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_recovery_silence_prepare_exhaust_4_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recovery_silence_prepare', times=4)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(1.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_recovery_silence_prepare_exhaust_4_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recovery_silence_prepare', times=4)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(2.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_recovery_silence_prepare_exhaust_6_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recovery_silence_prepare', times=6)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(2.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_recovery_silence_prepare_exhaust_6_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recovery_silence_prepare', times=6)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(4.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_recovery_silence_complete_exhaust_1_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recovery_silence_complete', times=1)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.125)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_recovery_silence_complete_exhaust_1_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recovery_silence_complete', times=1)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.25)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_recovery_silence_complete_exhaust_2_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recovery_silence_complete', times=2)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.25)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_recovery_silence_complete_exhaust_2_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recovery_silence_complete', times=2)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.5)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_recovery_silence_complete_exhaust_4_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recovery_silence_complete', times=4)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(1.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_recovery_silence_complete_exhaust_4_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recovery_silence_complete', times=4)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(2.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_recovery_silence_complete_exhaust_6_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recovery_silence_complete', times=6)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(2.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_recovery_silence_complete_exhaust_6_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recovery_silence_complete', times=6)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(4.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_terminal_empty_prepare_exhaust_1_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_terminal_empty_prepare', times=1)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.125)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_terminal_empty_prepare_exhaust_1_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_terminal_empty_prepare', times=1)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.25)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_terminal_empty_prepare_exhaust_2_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_terminal_empty_prepare', times=2)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.25)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_terminal_empty_prepare_exhaust_2_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_terminal_empty_prepare', times=2)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.5)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_terminal_empty_prepare_exhaust_4_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_terminal_empty_prepare', times=4)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(1.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_terminal_empty_prepare_exhaust_4_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_terminal_empty_prepare', times=4)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(2.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_terminal_empty_prepare_exhaust_6_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_terminal_empty_prepare', times=6)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(2.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_terminal_empty_prepare_exhaust_6_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_terminal_empty_prepare', times=6)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(4.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_terminal_empty_complete_exhaust_1_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_terminal_empty_complete', times=1)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.125)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_terminal_empty_complete_exhaust_1_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_terminal_empty_complete', times=1)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.25)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_terminal_empty_complete_exhaust_2_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_terminal_empty_complete', times=2)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.25)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_terminal_empty_complete_exhaust_2_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_terminal_empty_complete', times=2)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.5)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_terminal_empty_complete_exhaust_4_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_terminal_empty_complete', times=4)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(1.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_terminal_empty_complete_exhaust_4_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_terminal_empty_complete', times=4)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(2.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_terminal_empty_complete_exhaust_6_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_terminal_empty_complete', times=6)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(2.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_terminal_empty_complete_exhaust_6_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_terminal_empty_complete', times=6)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(4.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_artifact_stage_exhaust_1_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_artifact_stage', times=1)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.125)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_artifact_stage_exhaust_1_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_artifact_stage', times=1)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.25)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_artifact_stage_exhaust_2_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_artifact_stage', times=2)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.25)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_artifact_stage_exhaust_2_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_artifact_stage', times=2)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.5)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_artifact_stage_exhaust_4_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_artifact_stage', times=4)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(1.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_artifact_stage_exhaust_4_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_artifact_stage', times=4)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(2.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_artifact_stage_exhaust_6_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_artifact_stage', times=6)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(2.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_artifact_stage_exhaust_6_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_artifact_stage', times=6)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(4.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_artifact_missing_evidence_exhaust_1_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_artifact_missing_evidence', times=1)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.125)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_artifact_missing_evidence_exhaust_1_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_artifact_missing_evidence', times=1)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.25)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_artifact_missing_evidence_exhaust_2_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_artifact_missing_evidence', times=2)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.25)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_artifact_missing_evidence_exhaust_2_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_artifact_missing_evidence', times=2)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.5)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_artifact_missing_evidence_exhaust_4_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_artifact_missing_evidence', times=4)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(1.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_artifact_missing_evidence_exhaust_4_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_artifact_missing_evidence', times=4)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(2.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_artifact_missing_evidence_exhaust_6_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_artifact_missing_evidence', times=6)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(2.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_artifact_missing_evidence_exhaust_6_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_artifact_missing_evidence', times=6)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(4.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_artifact_missing_restore_exhaust_1_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_artifact_missing_restore', times=1)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.125)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_artifact_missing_restore_exhaust_1_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_artifact_missing_restore', times=1)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.25)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_artifact_missing_restore_exhaust_2_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_artifact_missing_restore', times=2)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.25)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_artifact_missing_restore_exhaust_2_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_artifact_missing_restore', times=2)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.5)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_artifact_missing_restore_exhaust_4_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_artifact_missing_restore', times=4)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(1.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_artifact_missing_restore_exhaust_4_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_artifact_missing_restore', times=4)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(2.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_artifact_missing_restore_exhaust_6_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_artifact_missing_restore', times=6)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(2.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_artifact_missing_restore_exhaust_6_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_artifact_missing_restore', times=6)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(4.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_artifact_missing_apply_exhaust_1_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_artifact_missing_apply', times=1)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.125)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_artifact_missing_apply_exhaust_1_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_artifact_missing_apply', times=1)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.25)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_artifact_missing_apply_exhaust_2_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_artifact_missing_apply', times=2)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.25)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_artifact_missing_apply_exhaust_2_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_artifact_missing_apply', times=2)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.5)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_artifact_missing_apply_exhaust_4_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_artifact_missing_apply', times=4)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(1.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_artifact_missing_apply_exhaust_4_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_artifact_missing_apply', times=4)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(2.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_artifact_missing_apply_exhaust_6_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_artifact_missing_apply', times=6)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(2.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_artifact_missing_apply_exhaust_6_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_artifact_missing_apply', times=6)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(4.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_partial_precheck_exhaust_1_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_partial_precheck', times=1)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.125)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_partial_precheck_exhaust_1_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_partial_precheck', times=1)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.25)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_partial_precheck_exhaust_2_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_partial_precheck', times=2)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.25)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_partial_precheck_exhaust_2_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_partial_precheck', times=2)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.5)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_partial_precheck_exhaust_4_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_partial_precheck', times=4)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(1.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_partial_precheck_exhaust_4_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_partial_precheck', times=4)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(2.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_partial_precheck_exhaust_6_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_partial_precheck', times=6)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(2.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_partial_precheck_exhaust_6_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_partial_precheck', times=6)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(4.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_language_shadow_claim_exhaust_1_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_language_shadow_claim', times=1)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.125)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_language_shadow_claim_exhaust_1_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_language_shadow_claim', times=1)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.25)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_language_shadow_claim_exhaust_2_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_language_shadow_claim', times=2)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.25)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_language_shadow_claim_exhaust_2_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_language_shadow_claim', times=2)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.5)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_language_shadow_claim_exhaust_4_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_language_shadow_claim', times=4)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(1.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_language_shadow_claim_exhaust_4_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_language_shadow_claim', times=4)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(2.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_language_shadow_claim_exhaust_6_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_language_shadow_claim', times=6)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(2.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_language_shadow_claim_exhaust_6_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_language_shadow_claim', times=6)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(4.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_language_shadow_authorize_exhaust_1_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_language_shadow_authorize', times=1)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.125)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_language_shadow_authorize_exhaust_1_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_language_shadow_authorize', times=1)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.25)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_language_shadow_authorize_exhaust_2_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_language_shadow_authorize', times=2)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.25)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_language_shadow_authorize_exhaust_2_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_language_shadow_authorize', times=2)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.5)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_language_shadow_authorize_exhaust_4_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_language_shadow_authorize', times=4)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(1.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_language_shadow_authorize_exhaust_4_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_language_shadow_authorize', times=4)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(2.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_language_shadow_authorize_exhaust_6_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_language_shadow_authorize', times=6)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(2.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_language_shadow_authorize_exhaust_6_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_language_shadow_authorize', times=6)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(4.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_language_shadow_release_exhaust_1_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_language_shadow_release', times=1)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.125)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_language_shadow_release_exhaust_1_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_language_shadow_release', times=1)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.25)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_language_shadow_release_exhaust_2_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_language_shadow_release', times=2)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.25)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_language_shadow_release_exhaust_2_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_language_shadow_release', times=2)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.5)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_language_shadow_release_exhaust_4_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_language_shadow_release', times=4)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(1.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_language_shadow_release_exhaust_4_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_language_shadow_release', times=4)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(2.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_language_shadow_release_exhaust_6_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_language_shadow_release', times=6)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(2.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_language_shadow_release_exhaust_6_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_language_shadow_release', times=6)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(4.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_provider_stt_exhaust_1_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_provider_stt', times=1)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.125)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_provider_stt_exhaust_1_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_provider_stt', times=1)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.25)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_provider_stt_exhaust_2_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_provider_stt', times=2)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.25)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_provider_stt_exhaust_2_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_provider_stt', times=2)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.5)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_provider_stt_exhaust_4_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_provider_stt', times=4)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(1.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_provider_stt_exhaust_4_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_provider_stt', times=4)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(2.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_provider_stt_exhaust_6_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_provider_stt', times=6)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(2.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_provider_stt_exhaust_6_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_provider_stt', times=6)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(4.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_enqueue_exhaust_1_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_enqueue', times=1)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.125)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_enqueue_exhaust_1_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_enqueue', times=1)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.25)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_enqueue_exhaust_2_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_enqueue', times=2)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.25)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_enqueue_exhaust_2_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_enqueue', times=2)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.5)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_enqueue_exhaust_4_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_enqueue', times=4)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(1.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_enqueue_exhaust_4_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_enqueue', times=4)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(2.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_enqueue_exhaust_6_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_enqueue', times=6)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(2.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_enqueue_exhaust_6_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_enqueue', times=6)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(4.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_heartbeat_exhaust_1_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_heartbeat', times=1)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.125)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_heartbeat_exhaust_1_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_heartbeat', times=1)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.25)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_heartbeat_exhaust_2_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_heartbeat', times=2)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.25)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_heartbeat_exhaust_2_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_heartbeat', times=2)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.5)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_heartbeat_exhaust_4_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_heartbeat', times=4)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(1.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_heartbeat_exhaust_4_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_heartbeat', times=4)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(2.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_heartbeat_exhaust_6_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_heartbeat', times=6)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(2.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_heartbeat_exhaust_6_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_heartbeat', times=6)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(4.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_complete_exhaust_1_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_complete', times=1)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.125)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_complete_exhaust_1_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_complete', times=1)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.25)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_complete_exhaust_2_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_complete', times=2)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.25)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_complete_exhaust_2_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_complete', times=2)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.5)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_complete_exhaust_4_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_complete', times=4)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(1.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_complete_exhaust_4_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_complete', times=4)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(2.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_complete_exhaust_6_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_complete', times=6)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(2.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_complete_exhaust_6_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_complete', times=6)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(4.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_fail_exhaust_1_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_fail', times=1)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.125)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_fail_exhaust_1_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_fail', times=1)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.25)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_fail_exhaust_2_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_fail', times=2)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.25)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_fail_exhaust_2_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_fail', times=2)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.5)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_fail_exhaust_4_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_fail', times=4)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(1.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_fail_exhaust_4_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_fail', times=4)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(2.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_fail_exhaust_6_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_fail', times=6)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(2.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_fail_exhaust_6_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_fail', times=6)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(4.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_defer_exhaust_1_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_defer', times=1)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.125)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_defer_exhaust_1_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_defer', times=1)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.25)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_defer_exhaust_2_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_defer', times=2)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.25)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_defer_exhaust_2_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_defer', times=2)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.5)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_defer_exhaust_4_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_defer', times=4)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(1.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_defer_exhaust_4_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_defer', times=4)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(2.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_defer_exhaust_6_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_defer', times=6)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(2.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_defer_exhaust_6_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_defer', times=6)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(4.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_release_exhaust_1_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_release', times=1)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.125)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_release_exhaust_1_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_release', times=1)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.25)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_release_exhaust_2_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_release', times=2)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.25)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_release_exhaust_2_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_release', times=2)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.5)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_release_exhaust_4_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_release', times=4)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(1.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_release_exhaust_4_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_release', times=4)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(2.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_release_exhaust_6_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_release', times=6)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(2.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_release_exhaust_6_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_release', times=6)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(4.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_recover_exhaust_1_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recover', times=1)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.125)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_recover_exhaust_1_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recover', times=1)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.25)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_recover_exhaust_2_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recover', times=2)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.25)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_recover_exhaust_2_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recover', times=2)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.5)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_recover_exhaust_4_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recover', times=4)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(1.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_recover_exhaust_4_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recover', times=4)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(2.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_recover_exhaust_6_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recover', times=6)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(2.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_recover_exhaust_6_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recover', times=6)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(4.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_redrive_exhaust_1_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_redrive', times=1)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.125)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_redrive_exhaust_1_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_redrive', times=1)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.25)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_redrive_exhaust_2_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_redrive', times=2)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.25)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_redrive_exhaust_2_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_redrive', times=2)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.5)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_redrive_exhaust_4_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_redrive', times=4)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(1.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_redrive_exhaust_4_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_redrive', times=4)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(2.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_redrive_exhaust_6_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_redrive', times=6)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(2.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_redrive_exhaust_6_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_redrive', times=6)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(4.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_gpu_release_exhaust_1_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_gpu_release', times=1)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.125)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_gpu_release_exhaust_1_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_gpu_release', times=1)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.25)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_gpu_release_exhaust_2_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_gpu_release', times=2)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.25)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_gpu_release_exhaust_2_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_gpu_release', times=2)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.5)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_gpu_release_exhaust_4_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_gpu_release', times=4)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(1.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_gpu_release_exhaust_4_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_gpu_release', times=4)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(2.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_gpu_release_exhaust_6_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_gpu_release', times=6)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(2.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_gpu_release_exhaust_6_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_gpu_release', times=6)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(4.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_shadow_offer_exhaust_1_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_shadow_offer', times=1)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.125)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_shadow_offer_exhaust_1_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_shadow_offer', times=1)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.25)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_shadow_offer_exhaust_2_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_shadow_offer', times=2)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.25)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_shadow_offer_exhaust_2_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_shadow_offer', times=2)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.5)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_shadow_offer_exhaust_4_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_shadow_offer', times=4)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(1.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_shadow_offer_exhaust_4_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_shadow_offer', times=4)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(2.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_shadow_offer_exhaust_6_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_shadow_offer', times=6)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(2.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_shadow_offer_exhaust_6_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_shadow_offer', times=6)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(4.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_shadow_take_exhaust_1_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_shadow_take', times=1)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.125)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_shadow_take_exhaust_1_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_shadow_take', times=1)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.25)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_shadow_take_exhaust_2_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_shadow_take', times=2)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.25)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_shadow_take_exhaust_2_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_shadow_take', times=2)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.5)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_shadow_take_exhaust_4_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_shadow_take', times=4)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(1.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_shadow_take_exhaust_4_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_shadow_take', times=4)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(2.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_shadow_take_exhaust_6_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_shadow_take', times=6)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(2.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_shadow_take_exhaust_6_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_shadow_take', times=6)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(4.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_shadow_reserve_exhaust_1_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_shadow_reserve', times=1)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.125)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_shadow_reserve_exhaust_1_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_shadow_reserve', times=1)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.25)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_shadow_reserve_exhaust_2_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_shadow_reserve', times=2)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.25)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_shadow_reserve_exhaust_2_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_shadow_reserve', times=2)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.5)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_shadow_reserve_exhaust_4_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_shadow_reserve', times=4)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(1.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_shadow_reserve_exhaust_4_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_shadow_reserve', times=4)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(2.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_shadow_reserve_exhaust_6_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_shadow_reserve', times=6)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(2.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_shadow_reserve_exhaust_6_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_shadow_reserve', times=6)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(4.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_shadow_finish_exhaust_1_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_shadow_finish', times=1)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.125)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_shadow_finish_exhaust_1_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_shadow_finish', times=1)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.25)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_shadow_finish_exhaust_2_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_shadow_finish', times=2)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.25)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_shadow_finish_exhaust_2_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_shadow_finish', times=2)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.5)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_shadow_finish_exhaust_4_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_shadow_finish', times=4)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(1.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_shadow_finish_exhaust_4_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_shadow_finish', times=4)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(2.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_shadow_finish_exhaust_6_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_shadow_finish', times=6)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(2.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_shadow_finish_exhaust_6_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_shadow_finish', times=6)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(4.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_shadow_reap_exhaust_1_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_shadow_reap', times=1)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.125)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_shadow_reap_exhaust_1_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_shadow_reap', times=1)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.25)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_shadow_reap_exhaust_2_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_shadow_reap', times=2)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.25)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_shadow_reap_exhaust_2_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_shadow_reap', times=2)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.5)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_shadow_reap_exhaust_4_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_shadow_reap', times=4)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(1.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_shadow_reap_exhaust_4_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_shadow_reap', times=4)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(2.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_shadow_reap_exhaust_6_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_shadow_reap', times=6)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(2.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_shadow_reap_exhaust_6_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_shadow_reap', times=6)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(4.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_shadow_ready_exhaust_1_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_shadow_ready', times=1)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.125)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_shadow_ready_exhaust_1_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_shadow_ready', times=1)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.25)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_shadow_ready_exhaust_2_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_shadow_ready', times=2)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.25)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_shadow_ready_exhaust_2_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_shadow_ready', times=2)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.5)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_shadow_ready_exhaust_4_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_shadow_ready', times=4)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(1.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_shadow_ready_exhaust_4_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_shadow_ready', times=4)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(2.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_shadow_ready_exhaust_6_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_shadow_ready', times=6)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(2.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_shadow_ready_exhaust_6_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_shadow_ready', times=6)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(4.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_shadow_projection_input_exhaust_1_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_shadow_projection_input', times=1)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.125)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_shadow_projection_input_exhaust_1_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_shadow_projection_input', times=1)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.25)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_shadow_projection_input_exhaust_2_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_shadow_projection_input', times=2)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.25)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_shadow_projection_input_exhaust_2_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_shadow_projection_input', times=2)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.5)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_shadow_projection_input_exhaust_4_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_shadow_projection_input', times=4)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(1.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_shadow_projection_input_exhaust_4_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_shadow_projection_input', times=4)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(2.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_shadow_projection_input_exhaust_6_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_shadow_projection_input', times=6)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(2.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_shadow_projection_input_exhaust_6_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_shadow_projection_input', times=6)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(4.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_shadow_paid_exhaust_1_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_shadow_paid', times=1)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.125)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_shadow_paid_exhaust_1_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_shadow_paid', times=1)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.25)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_shadow_paid_exhaust_2_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_shadow_paid', times=2)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.25)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_shadow_paid_exhaust_2_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_shadow_paid', times=2)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.5)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_shadow_paid_exhaust_4_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_shadow_paid', times=4)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(1.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_shadow_paid_exhaust_4_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_shadow_paid', times=4)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(2.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_shadow_paid_exhaust_6_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_shadow_paid', times=6)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(2.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_shadow_paid_exhaust_6_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_shadow_paid', times=6)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(4.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_shadow_handoff_exhaust_1_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_shadow_handoff', times=1)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.125)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_shadow_handoff_exhaust_1_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_shadow_handoff', times=1)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.25)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_shadow_handoff_exhaust_2_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_shadow_handoff', times=2)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.25)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_shadow_handoff_exhaust_2_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_shadow_handoff', times=2)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.5)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_shadow_handoff_exhaust_4_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_shadow_handoff', times=4)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(1.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_shadow_handoff_exhaust_4_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_shadow_handoff', times=4)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(2.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_shadow_handoff_exhaust_6_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_shadow_handoff', times=6)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(2.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_shadow_handoff_exhaust_6_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_shadow_handoff', times=6)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(4.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_shadow_start_recovery_exhaust_1_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_shadow_start_recovery', times=1)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.125)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_shadow_start_recovery_exhaust_1_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_shadow_start_recovery', times=1)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.25)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_shadow_start_recovery_exhaust_2_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_shadow_start_recovery', times=2)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.25)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_shadow_start_recovery_exhaust_2_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_shadow_start_recovery', times=2)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(0.5)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_shadow_start_recovery_exhaust_4_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_shadow_start_recovery', times=4)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(1.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_shadow_start_recovery_exhaust_4_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_shadow_start_recovery', times=4)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(2.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_shadow_start_recovery_exhaust_6_jitter_0(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_shadow_start_recovery', times=6)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(2.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_shadow_start_recovery_exhaust_6_jitter_100(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=1.0))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_shadow_start_recovery', times=6)
    assert isinstance(error, FirestoreContentionExhausted)
    assert error.retry_after == pytest.approx(4.0)
    assert error.retry_after <= BACKEND_CAP_SECONDS


def test_store_stamp_merge_commit_first_rung_jitter_250(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.25))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_merge_commit')
    assert error.retry_after == pytest.approx(0.15625)


def test_store_stamp_merge_commit_first_rung_jitter_500(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.5))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_merge_commit')
    assert error.retry_after == pytest.approx(0.1875)


def test_store_stamp_merge_commit_first_rung_jitter_750(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.75))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_merge_commit')
    assert error.retry_after == pytest.approx(0.21875)


def test_store_stamp_admit_first_rung_jitter_250(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.25))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_admit')
    assert error.retry_after == pytest.approx(0.15625)


def test_store_stamp_admit_first_rung_jitter_500(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.5))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_admit')
    assert error.retry_after == pytest.approx(0.1875)


def test_store_stamp_admit_first_rung_jitter_750(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.75))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_admit')
    assert error.retry_after == pytest.approx(0.21875)


def test_store_stamp_content_ledger_accept_first_rung_jitter_250(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.25))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_content_ledger_accept')
    assert error.retry_after == pytest.approx(0.15625)


def test_store_stamp_content_ledger_accept_first_rung_jitter_500(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.5))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_content_ledger_accept')
    assert error.retry_after == pytest.approx(0.1875)


def test_store_stamp_content_ledger_accept_first_rung_jitter_750(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.75))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_content_ledger_accept')
    assert error.retry_after == pytest.approx(0.21875)


def test_store_stamp_recognizer_receipt_first_rung_jitter_250(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.25))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recognizer_receipt')
    assert error.retry_after == pytest.approx(0.15625)


def test_store_stamp_recognizer_receipt_first_rung_jitter_500(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.5))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recognizer_receipt')
    assert error.retry_after == pytest.approx(0.1875)


def test_store_stamp_recognizer_receipt_first_rung_jitter_750(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.75))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recognizer_receipt')
    assert error.retry_after == pytest.approx(0.21875)


def test_store_stamp_recovery_prepare_first_rung_jitter_250(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.25))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recovery_prepare')
    assert error.retry_after == pytest.approx(0.15625)


def test_store_stamp_recovery_prepare_first_rung_jitter_500(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.5))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recovery_prepare')
    assert error.retry_after == pytest.approx(0.1875)


def test_store_stamp_recovery_prepare_first_rung_jitter_750(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.75))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recovery_prepare')
    assert error.retry_after == pytest.approx(0.21875)


def test_store_stamp_recovery_claim_wake_first_rung_jitter_250(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.25))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recovery_claim_wake')
    assert error.retry_after == pytest.approx(0.15625)


def test_store_stamp_recovery_claim_wake_first_rung_jitter_500(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.5))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recovery_claim_wake')
    assert error.retry_after == pytest.approx(0.1875)


def test_store_stamp_recovery_claim_wake_first_rung_jitter_750(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.75))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recovery_claim_wake')
    assert error.retry_after == pytest.approx(0.21875)


def test_store_stamp_recovery_extend_wake_first_rung_jitter_250(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.25))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recovery_extend_wake')
    assert error.retry_after == pytest.approx(0.15625)


def test_store_stamp_recovery_extend_wake_first_rung_jitter_500(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.5))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recovery_extend_wake')
    assert error.retry_after == pytest.approx(0.1875)


def test_store_stamp_recovery_extend_wake_first_rung_jitter_750(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.75))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recovery_extend_wake')
    assert error.retry_after == pytest.approx(0.21875)


def test_store_stamp_recovery_shorten_wake_first_rung_jitter_250(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.25))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recovery_shorten_wake')
    assert error.retry_after == pytest.approx(0.15625)


def test_store_stamp_recovery_shorten_wake_first_rung_jitter_500(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.5))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recovery_shorten_wake')
    assert error.retry_after == pytest.approx(0.1875)


def test_store_stamp_recovery_shorten_wake_first_rung_jitter_750(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.75))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recovery_shorten_wake')
    assert error.retry_after == pytest.approx(0.21875)


def test_store_stamp_recovery_start_first_rung_jitter_250(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.25))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recovery_start')
    assert error.retry_after == pytest.approx(0.15625)


def test_store_stamp_recovery_start_first_rung_jitter_500(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.5))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recovery_start')
    assert error.retry_after == pytest.approx(0.1875)


def test_store_stamp_recovery_start_first_rung_jitter_750(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.75))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recovery_start')
    assert error.retry_after == pytest.approx(0.21875)


def test_store_stamp_recovery_observe_vad_first_rung_jitter_250(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.25))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recovery_observe_vad')
    assert error.retry_after == pytest.approx(0.15625)


def test_store_stamp_recovery_observe_vad_first_rung_jitter_500(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.5))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recovery_observe_vad')
    assert error.retry_after == pytest.approx(0.1875)


def test_store_stamp_recovery_observe_vad_first_rung_jitter_750(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.75))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recovery_observe_vad')
    assert error.retry_after == pytest.approx(0.21875)


def test_store_stamp_recovery_retry_missing_result_first_rung_jitter_250(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.25))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recovery_retry_missing_result')
    assert error.retry_after == pytest.approx(0.15625)


def test_store_stamp_recovery_retry_missing_result_first_rung_jitter_500(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.5))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recovery_retry_missing_result')
    assert error.retry_after == pytest.approx(0.1875)


def test_store_stamp_recovery_retry_missing_result_first_rung_jitter_750(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.75))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recovery_retry_missing_result')
    assert error.retry_after == pytest.approx(0.21875)


def test_store_stamp_recovery_hold_duration_limit_first_rung_jitter_250(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.25))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recovery_hold_duration_limit')
    assert error.retry_after == pytest.approx(0.15625)


def test_store_stamp_recovery_hold_duration_limit_first_rung_jitter_500(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.5))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recovery_hold_duration_limit')
    assert error.retry_after == pytest.approx(0.1875)


def test_store_stamp_recovery_hold_duration_limit_first_rung_jitter_750(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.75))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recovery_hold_duration_limit')
    assert error.retry_after == pytest.approx(0.21875)


def test_store_stamp_recovery_hold_invalid_manifest_first_rung_jitter_250(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.25))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recovery_hold_invalid_manifest')
    assert error.retry_after == pytest.approx(0.15625)


def test_store_stamp_recovery_hold_invalid_manifest_first_rung_jitter_500(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.5))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recovery_hold_invalid_manifest')
    assert error.retry_after == pytest.approx(0.1875)


def test_store_stamp_recovery_hold_invalid_manifest_first_rung_jitter_750(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.75))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recovery_hold_invalid_manifest')
    assert error.retry_after == pytest.approx(0.21875)


def test_store_stamp_recovery_start_duration_limited_first_rung_jitter_250(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.25))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recovery_start_duration_limited')
    assert error.retry_after == pytest.approx(0.15625)


def test_store_stamp_recovery_start_duration_limited_first_rung_jitter_500(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.5))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recovery_start_duration_limited')
    assert error.retry_after == pytest.approx(0.1875)


def test_store_stamp_recovery_start_duration_limited_first_rung_jitter_750(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.75))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recovery_start_duration_limited')
    assert error.retry_after == pytest.approx(0.21875)


def test_store_stamp_recovery_paid_takeover_first_rung_jitter_250(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.25))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recovery_paid_takeover')
    assert error.retry_after == pytest.approx(0.15625)


def test_store_stamp_recovery_paid_takeover_first_rung_jitter_500(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.5))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recovery_paid_takeover')
    assert error.retry_after == pytest.approx(0.1875)


def test_store_stamp_recovery_paid_takeover_first_rung_jitter_750(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.75))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recovery_paid_takeover')
    assert error.retry_after == pytest.approx(0.21875)


def test_store_stamp_recovery_settle_first_rung_jitter_250(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.25))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recovery_settle')
    assert error.retry_after == pytest.approx(0.15625)


def test_store_stamp_recovery_settle_first_rung_jitter_500(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.5))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recovery_settle')
    assert error.retry_after == pytest.approx(0.1875)


def test_store_stamp_recovery_settle_first_rung_jitter_750(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.75))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recovery_settle')
    assert error.retry_after == pytest.approx(0.21875)


def test_store_stamp_recovery_silence_prepare_first_rung_jitter_250(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.25))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recovery_silence_prepare')
    assert error.retry_after == pytest.approx(0.15625)


def test_store_stamp_recovery_silence_prepare_first_rung_jitter_500(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.5))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recovery_silence_prepare')
    assert error.retry_after == pytest.approx(0.1875)


def test_store_stamp_recovery_silence_prepare_first_rung_jitter_750(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.75))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recovery_silence_prepare')
    assert error.retry_after == pytest.approx(0.21875)


def test_store_stamp_recovery_silence_complete_first_rung_jitter_250(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.25))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recovery_silence_complete')
    assert error.retry_after == pytest.approx(0.15625)


def test_store_stamp_recovery_silence_complete_first_rung_jitter_500(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.5))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recovery_silence_complete')
    assert error.retry_after == pytest.approx(0.1875)


def test_store_stamp_recovery_silence_complete_first_rung_jitter_750(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.75))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recovery_silence_complete')
    assert error.retry_after == pytest.approx(0.21875)


def test_store_stamp_terminal_empty_prepare_first_rung_jitter_250(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.25))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_terminal_empty_prepare')
    assert error.retry_after == pytest.approx(0.15625)


def test_store_stamp_terminal_empty_prepare_first_rung_jitter_500(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.5))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_terminal_empty_prepare')
    assert error.retry_after == pytest.approx(0.1875)


def test_store_stamp_terminal_empty_prepare_first_rung_jitter_750(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.75))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_terminal_empty_prepare')
    assert error.retry_after == pytest.approx(0.21875)


def test_store_stamp_terminal_empty_complete_first_rung_jitter_250(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.25))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_terminal_empty_complete')
    assert error.retry_after == pytest.approx(0.15625)


def test_store_stamp_terminal_empty_complete_first_rung_jitter_500(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.5))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_terminal_empty_complete')
    assert error.retry_after == pytest.approx(0.1875)


def test_store_stamp_terminal_empty_complete_first_rung_jitter_750(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.75))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_terminal_empty_complete')
    assert error.retry_after == pytest.approx(0.21875)


def test_store_stamp_artifact_stage_first_rung_jitter_250(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.25))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_artifact_stage')
    assert error.retry_after == pytest.approx(0.15625)


def test_store_stamp_artifact_stage_first_rung_jitter_500(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.5))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_artifact_stage')
    assert error.retry_after == pytest.approx(0.1875)


def test_store_stamp_artifact_stage_first_rung_jitter_750(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.75))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_artifact_stage')
    assert error.retry_after == pytest.approx(0.21875)


def test_store_stamp_artifact_missing_evidence_first_rung_jitter_250(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.25))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_artifact_missing_evidence')
    assert error.retry_after == pytest.approx(0.15625)


def test_store_stamp_artifact_missing_evidence_first_rung_jitter_500(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.5))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_artifact_missing_evidence')
    assert error.retry_after == pytest.approx(0.1875)


def test_store_stamp_artifact_missing_evidence_first_rung_jitter_750(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.75))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_artifact_missing_evidence')
    assert error.retry_after == pytest.approx(0.21875)


def test_store_stamp_artifact_missing_restore_first_rung_jitter_250(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.25))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_artifact_missing_restore')
    assert error.retry_after == pytest.approx(0.15625)


def test_store_stamp_artifact_missing_restore_first_rung_jitter_500(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.5))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_artifact_missing_restore')
    assert error.retry_after == pytest.approx(0.1875)


def test_store_stamp_artifact_missing_restore_first_rung_jitter_750(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.75))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_artifact_missing_restore')
    assert error.retry_after == pytest.approx(0.21875)


def test_store_stamp_artifact_missing_apply_first_rung_jitter_250(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.25))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_artifact_missing_apply')
    assert error.retry_after == pytest.approx(0.15625)


def test_store_stamp_artifact_missing_apply_first_rung_jitter_500(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.5))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_artifact_missing_apply')
    assert error.retry_after == pytest.approx(0.1875)


def test_store_stamp_artifact_missing_apply_first_rung_jitter_750(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.75))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_artifact_missing_apply')
    assert error.retry_after == pytest.approx(0.21875)


def test_store_stamp_partial_precheck_first_rung_jitter_250(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.25))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_partial_precheck')
    assert error.retry_after == pytest.approx(0.15625)


def test_store_stamp_partial_precheck_first_rung_jitter_500(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.5))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_partial_precheck')
    assert error.retry_after == pytest.approx(0.1875)


def test_store_stamp_partial_precheck_first_rung_jitter_750(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.75))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_partial_precheck')
    assert error.retry_after == pytest.approx(0.21875)


def test_store_stamp_language_shadow_claim_first_rung_jitter_250(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.25))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_language_shadow_claim')
    assert error.retry_after == pytest.approx(0.15625)


def test_store_stamp_language_shadow_claim_first_rung_jitter_500(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.5))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_language_shadow_claim')
    assert error.retry_after == pytest.approx(0.1875)


def test_store_stamp_language_shadow_claim_first_rung_jitter_750(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.75))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_language_shadow_claim')
    assert error.retry_after == pytest.approx(0.21875)


def test_store_stamp_language_shadow_authorize_first_rung_jitter_250(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.25))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_language_shadow_authorize')
    assert error.retry_after == pytest.approx(0.15625)


def test_store_stamp_language_shadow_authorize_first_rung_jitter_500(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.5))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_language_shadow_authorize')
    assert error.retry_after == pytest.approx(0.1875)


def test_store_stamp_language_shadow_authorize_first_rung_jitter_750(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.75))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_language_shadow_authorize')
    assert error.retry_after == pytest.approx(0.21875)


def test_store_stamp_language_shadow_release_first_rung_jitter_250(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.25))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_language_shadow_release')
    assert error.retry_after == pytest.approx(0.15625)


def test_store_stamp_language_shadow_release_first_rung_jitter_500(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.5))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_language_shadow_release')
    assert error.retry_after == pytest.approx(0.1875)


def test_store_stamp_language_shadow_release_first_rung_jitter_750(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.75))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_language_shadow_release')
    assert error.retry_after == pytest.approx(0.21875)


def test_store_stamp_provider_stt_first_rung_jitter_250(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.25))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_provider_stt')
    assert error.retry_after == pytest.approx(0.15625)


def test_store_stamp_provider_stt_first_rung_jitter_500(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.5))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_provider_stt')
    assert error.retry_after == pytest.approx(0.1875)


def test_store_stamp_provider_stt_first_rung_jitter_750(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.75))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_provider_stt')
    assert error.retry_after == pytest.approx(0.21875)


def test_store_stamp_enqueue_first_rung_jitter_250(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.25))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_enqueue')
    assert error.retry_after == pytest.approx(0.15625)


def test_store_stamp_enqueue_first_rung_jitter_500(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.5))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_enqueue')
    assert error.retry_after == pytest.approx(0.1875)


def test_store_stamp_enqueue_first_rung_jitter_750(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.75))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_enqueue')
    assert error.retry_after == pytest.approx(0.21875)


def test_store_stamp_heartbeat_first_rung_jitter_250(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.25))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_heartbeat')
    assert error.retry_after == pytest.approx(0.15625)


def test_store_stamp_heartbeat_first_rung_jitter_500(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.5))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_heartbeat')
    assert error.retry_after == pytest.approx(0.1875)


def test_store_stamp_heartbeat_first_rung_jitter_750(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.75))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_heartbeat')
    assert error.retry_after == pytest.approx(0.21875)


def test_store_stamp_complete_first_rung_jitter_250(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.25))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_complete')
    assert error.retry_after == pytest.approx(0.15625)


def test_store_stamp_complete_first_rung_jitter_500(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.5))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_complete')
    assert error.retry_after == pytest.approx(0.1875)


def test_store_stamp_complete_first_rung_jitter_750(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.75))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_complete')
    assert error.retry_after == pytest.approx(0.21875)


def test_store_stamp_fail_first_rung_jitter_250(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.25))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_fail')
    assert error.retry_after == pytest.approx(0.15625)


def test_store_stamp_fail_first_rung_jitter_500(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.5))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_fail')
    assert error.retry_after == pytest.approx(0.1875)


def test_store_stamp_fail_first_rung_jitter_750(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.75))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_fail')
    assert error.retry_after == pytest.approx(0.21875)


def test_store_stamp_defer_first_rung_jitter_250(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.25))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_defer')
    assert error.retry_after == pytest.approx(0.15625)


def test_store_stamp_defer_first_rung_jitter_500(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.5))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_defer')
    assert error.retry_after == pytest.approx(0.1875)


def test_store_stamp_defer_first_rung_jitter_750(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.75))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_defer')
    assert error.retry_after == pytest.approx(0.21875)


def test_store_stamp_release_first_rung_jitter_250(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.25))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_release')
    assert error.retry_after == pytest.approx(0.15625)


def test_store_stamp_release_first_rung_jitter_500(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.5))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_release')
    assert error.retry_after == pytest.approx(0.1875)


def test_store_stamp_release_first_rung_jitter_750(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.75))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_release')
    assert error.retry_after == pytest.approx(0.21875)


def test_store_stamp_recover_first_rung_jitter_250(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.25))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recover')
    assert error.retry_after == pytest.approx(0.15625)


def test_store_stamp_recover_first_rung_jitter_500(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.5))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recover')
    assert error.retry_after == pytest.approx(0.1875)


def test_store_stamp_recover_first_rung_jitter_750(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.75))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_recover')
    assert error.retry_after == pytest.approx(0.21875)


def test_store_stamp_redrive_first_rung_jitter_250(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.25))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_redrive')
    assert error.retry_after == pytest.approx(0.15625)


def test_store_stamp_redrive_first_rung_jitter_500(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.5))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_redrive')
    assert error.retry_after == pytest.approx(0.1875)


def test_store_stamp_redrive_first_rung_jitter_750(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.75))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_redrive')
    assert error.retry_after == pytest.approx(0.21875)


def test_store_stamp_gpu_release_first_rung_jitter_250(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.25))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_gpu_release')
    assert error.retry_after == pytest.approx(0.15625)


def test_store_stamp_gpu_release_first_rung_jitter_500(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.5))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_gpu_release')
    assert error.retry_after == pytest.approx(0.1875)


def test_store_stamp_gpu_release_first_rung_jitter_750(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.75))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_gpu_release')
    assert error.retry_after == pytest.approx(0.21875)


def test_store_stamp_shadow_offer_first_rung_jitter_250(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.25))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_shadow_offer')
    assert error.retry_after == pytest.approx(0.15625)


def test_store_stamp_shadow_offer_first_rung_jitter_500(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.5))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_shadow_offer')
    assert error.retry_after == pytest.approx(0.1875)


def test_store_stamp_shadow_offer_first_rung_jitter_750(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.75))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_shadow_offer')
    assert error.retry_after == pytest.approx(0.21875)


def test_store_stamp_shadow_take_first_rung_jitter_250(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.25))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_shadow_take')
    assert error.retry_after == pytest.approx(0.15625)


def test_store_stamp_shadow_take_first_rung_jitter_500(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.5))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_shadow_take')
    assert error.retry_after == pytest.approx(0.1875)


def test_store_stamp_shadow_take_first_rung_jitter_750(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.75))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_shadow_take')
    assert error.retry_after == pytest.approx(0.21875)


def test_store_stamp_shadow_reserve_first_rung_jitter_250(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.25))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_shadow_reserve')
    assert error.retry_after == pytest.approx(0.15625)


def test_store_stamp_shadow_reserve_first_rung_jitter_500(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.5))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_shadow_reserve')
    assert error.retry_after == pytest.approx(0.1875)


def test_store_stamp_shadow_reserve_first_rung_jitter_750(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.75))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_shadow_reserve')
    assert error.retry_after == pytest.approx(0.21875)


def test_store_stamp_shadow_finish_first_rung_jitter_250(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.25))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_shadow_finish')
    assert error.retry_after == pytest.approx(0.15625)


def test_store_stamp_shadow_finish_first_rung_jitter_500(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.5))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_shadow_finish')
    assert error.retry_after == pytest.approx(0.1875)


def test_store_stamp_shadow_finish_first_rung_jitter_750(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.75))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_shadow_finish')
    assert error.retry_after == pytest.approx(0.21875)


def test_store_stamp_shadow_reap_first_rung_jitter_250(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.25))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_shadow_reap')
    assert error.retry_after == pytest.approx(0.15625)


def test_store_stamp_shadow_reap_first_rung_jitter_500(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.5))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_shadow_reap')
    assert error.retry_after == pytest.approx(0.1875)


def test_store_stamp_shadow_reap_first_rung_jitter_750(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.75))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_shadow_reap')
    assert error.retry_after == pytest.approx(0.21875)


def test_store_stamp_shadow_ready_first_rung_jitter_250(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.25))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_shadow_ready')
    assert error.retry_after == pytest.approx(0.15625)


def test_store_stamp_shadow_ready_first_rung_jitter_500(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.5))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_shadow_ready')
    assert error.retry_after == pytest.approx(0.1875)


def test_store_stamp_shadow_ready_first_rung_jitter_750(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.75))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_shadow_ready')
    assert error.retry_after == pytest.approx(0.21875)


def test_store_stamp_shadow_projection_input_first_rung_jitter_250(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.25))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_shadow_projection_input')
    assert error.retry_after == pytest.approx(0.15625)


def test_store_stamp_shadow_projection_input_first_rung_jitter_500(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.5))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_shadow_projection_input')
    assert error.retry_after == pytest.approx(0.1875)


def test_store_stamp_shadow_projection_input_first_rung_jitter_750(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.75))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_shadow_projection_input')
    assert error.retry_after == pytest.approx(0.21875)


def test_store_stamp_shadow_paid_first_rung_jitter_250(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.25))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_shadow_paid')
    assert error.retry_after == pytest.approx(0.15625)


def test_store_stamp_shadow_paid_first_rung_jitter_500(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.5))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_shadow_paid')
    assert error.retry_after == pytest.approx(0.1875)


def test_store_stamp_shadow_paid_first_rung_jitter_750(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.75))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_shadow_paid')
    assert error.retry_after == pytest.approx(0.21875)


def test_store_stamp_shadow_handoff_first_rung_jitter_250(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.25))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_shadow_handoff')
    assert error.retry_after == pytest.approx(0.15625)


def test_store_stamp_shadow_handoff_first_rung_jitter_500(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.5))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_shadow_handoff')
    assert error.retry_after == pytest.approx(0.1875)


def test_store_stamp_shadow_handoff_first_rung_jitter_750(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.75))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_shadow_handoff')
    assert error.retry_after == pytest.approx(0.21875)


def test_store_stamp_shadow_start_recovery_first_rung_jitter_250(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.25))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_shadow_start_recovery')
    assert error.retry_after == pytest.approx(0.15625)


def test_store_stamp_shadow_start_recovery_first_rung_jitter_500(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.5))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_shadow_start_recovery')
    assert error.retry_after == pytest.approx(0.1875)


def test_store_stamp_shadow_start_recovery_first_rung_jitter_750(monkeypatch):
    damper, _clock = make_damper(FakeClock(jitter=0.75))
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_shadow_start_recovery')
    assert error.retry_after == pytest.approx(0.21875)


def test_store_stamp_merge_commit_leaves_other_labels_unarmed(monkeypatch):
    damper, clock = make_damper()
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    error = exhaust_run(store, 'batch_merge_commit')
    assert error.retry_after > 0
    assert set(damper._armed_until) == {'batch_merge_commit'}
    make_healthy(store)
    neighbor = neighbor_of('batch_merge_commit')
    assert store.run(lambda tx: 'ok', operation=neighbor) == 'ok'
    assert clock.sleeps == []


def test_store_stamp_admit_leaves_other_labels_unarmed(monkeypatch):
    damper, clock = make_damper()
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    error = exhaust_run(store, 'batch_admit')
    assert error.retry_after > 0
    assert set(damper._armed_until) == {'batch_admit'}
    make_healthy(store)
    neighbor = neighbor_of('batch_admit')
    assert store.run(lambda tx: 'ok', operation=neighbor) == 'ok'
    assert clock.sleeps == []


def test_store_stamp_content_ledger_accept_leaves_other_labels_unarmed(monkeypatch):
    damper, clock = make_damper()
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    error = exhaust_run(store, 'batch_content_ledger_accept')
    assert error.retry_after > 0
    assert set(damper._armed_until) == {'batch_content_ledger_accept'}
    make_healthy(store)
    neighbor = neighbor_of('batch_content_ledger_accept')
    assert store.run(lambda tx: 'ok', operation=neighbor) == 'ok'
    assert clock.sleeps == []


def test_store_stamp_recognizer_receipt_leaves_other_labels_unarmed(monkeypatch):
    damper, clock = make_damper()
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    error = exhaust_run(store, 'batch_recognizer_receipt')
    assert error.retry_after > 0
    assert set(damper._armed_until) == {'batch_recognizer_receipt'}
    make_healthy(store)
    neighbor = neighbor_of('batch_recognizer_receipt')
    assert store.run(lambda tx: 'ok', operation=neighbor) == 'ok'
    assert clock.sleeps == []


def test_store_stamp_recovery_prepare_leaves_other_labels_unarmed(monkeypatch):
    damper, clock = make_damper()
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    error = exhaust_run(store, 'batch_recovery_prepare')
    assert error.retry_after > 0
    assert set(damper._armed_until) == {'batch_recovery_prepare'}
    make_healthy(store)
    neighbor = neighbor_of('batch_recovery_prepare')
    assert store.run(lambda tx: 'ok', operation=neighbor) == 'ok'
    assert clock.sleeps == []


def test_store_stamp_recovery_claim_wake_leaves_other_labels_unarmed(monkeypatch):
    damper, clock = make_damper()
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    error = exhaust_run(store, 'batch_recovery_claim_wake')
    assert error.retry_after > 0
    assert set(damper._armed_until) == {'batch_recovery_claim_wake'}
    make_healthy(store)
    neighbor = neighbor_of('batch_recovery_claim_wake')
    assert store.run(lambda tx: 'ok', operation=neighbor) == 'ok'
    assert clock.sleeps == []


def test_store_stamp_recovery_extend_wake_leaves_other_labels_unarmed(monkeypatch):
    damper, clock = make_damper()
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    error = exhaust_run(store, 'batch_recovery_extend_wake')
    assert error.retry_after > 0
    assert set(damper._armed_until) == {'batch_recovery_extend_wake'}
    make_healthy(store)
    neighbor = neighbor_of('batch_recovery_extend_wake')
    assert store.run(lambda tx: 'ok', operation=neighbor) == 'ok'
    assert clock.sleeps == []


def test_store_stamp_recovery_shorten_wake_leaves_other_labels_unarmed(monkeypatch):
    damper, clock = make_damper()
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    error = exhaust_run(store, 'batch_recovery_shorten_wake')
    assert error.retry_after > 0
    assert set(damper._armed_until) == {'batch_recovery_shorten_wake'}
    make_healthy(store)
    neighbor = neighbor_of('batch_recovery_shorten_wake')
    assert store.run(lambda tx: 'ok', operation=neighbor) == 'ok'
    assert clock.sleeps == []


def test_store_stamp_recovery_start_leaves_other_labels_unarmed(monkeypatch):
    damper, clock = make_damper()
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    error = exhaust_run(store, 'batch_recovery_start')
    assert error.retry_after > 0
    assert set(damper._armed_until) == {'batch_recovery_start'}
    make_healthy(store)
    neighbor = neighbor_of('batch_recovery_start')
    assert store.run(lambda tx: 'ok', operation=neighbor) == 'ok'
    assert clock.sleeps == []


def test_store_stamp_recovery_observe_vad_leaves_other_labels_unarmed(monkeypatch):
    damper, clock = make_damper()
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    error = exhaust_run(store, 'batch_recovery_observe_vad')
    assert error.retry_after > 0
    assert set(damper._armed_until) == {'batch_recovery_observe_vad'}
    make_healthy(store)
    neighbor = neighbor_of('batch_recovery_observe_vad')
    assert store.run(lambda tx: 'ok', operation=neighbor) == 'ok'
    assert clock.sleeps == []


def test_store_stamp_recovery_retry_missing_result_leaves_other_labels_unarmed(monkeypatch):
    damper, clock = make_damper()
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    error = exhaust_run(store, 'batch_recovery_retry_missing_result')
    assert error.retry_after > 0
    assert set(damper._armed_until) == {'batch_recovery_retry_missing_result'}
    make_healthy(store)
    neighbor = neighbor_of('batch_recovery_retry_missing_result')
    assert store.run(lambda tx: 'ok', operation=neighbor) == 'ok'
    assert clock.sleeps == []


def test_store_stamp_recovery_hold_duration_limit_leaves_other_labels_unarmed(monkeypatch):
    damper, clock = make_damper()
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    error = exhaust_run(store, 'batch_recovery_hold_duration_limit')
    assert error.retry_after > 0
    assert set(damper._armed_until) == {'batch_recovery_hold_duration_limit'}
    make_healthy(store)
    neighbor = neighbor_of('batch_recovery_hold_duration_limit')
    assert store.run(lambda tx: 'ok', operation=neighbor) == 'ok'
    assert clock.sleeps == []


def test_store_stamp_recovery_hold_invalid_manifest_leaves_other_labels_unarmed(monkeypatch):
    damper, clock = make_damper()
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    error = exhaust_run(store, 'batch_recovery_hold_invalid_manifest')
    assert error.retry_after > 0
    assert set(damper._armed_until) == {'batch_recovery_hold_invalid_manifest'}
    make_healthy(store)
    neighbor = neighbor_of('batch_recovery_hold_invalid_manifest')
    assert store.run(lambda tx: 'ok', operation=neighbor) == 'ok'
    assert clock.sleeps == []


def test_store_stamp_recovery_start_duration_limited_leaves_other_labels_unarmed(monkeypatch):
    damper, clock = make_damper()
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    error = exhaust_run(store, 'batch_recovery_start_duration_limited')
    assert error.retry_after > 0
    assert set(damper._armed_until) == {'batch_recovery_start_duration_limited'}
    make_healthy(store)
    neighbor = neighbor_of('batch_recovery_start_duration_limited')
    assert store.run(lambda tx: 'ok', operation=neighbor) == 'ok'
    assert clock.sleeps == []


def test_store_stamp_recovery_paid_takeover_leaves_other_labels_unarmed(monkeypatch):
    damper, clock = make_damper()
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    error = exhaust_run(store, 'batch_recovery_paid_takeover')
    assert error.retry_after > 0
    assert set(damper._armed_until) == {'batch_recovery_paid_takeover'}
    make_healthy(store)
    neighbor = neighbor_of('batch_recovery_paid_takeover')
    assert store.run(lambda tx: 'ok', operation=neighbor) == 'ok'
    assert clock.sleeps == []


def test_store_stamp_recovery_settle_leaves_other_labels_unarmed(monkeypatch):
    damper, clock = make_damper()
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    error = exhaust_run(store, 'batch_recovery_settle')
    assert error.retry_after > 0
    assert set(damper._armed_until) == {'batch_recovery_settle'}
    make_healthy(store)
    neighbor = neighbor_of('batch_recovery_settle')
    assert store.run(lambda tx: 'ok', operation=neighbor) == 'ok'
    assert clock.sleeps == []


def test_store_stamp_recovery_silence_prepare_leaves_other_labels_unarmed(monkeypatch):
    damper, clock = make_damper()
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    error = exhaust_run(store, 'batch_recovery_silence_prepare')
    assert error.retry_after > 0
    assert set(damper._armed_until) == {'batch_recovery_silence_prepare'}
    make_healthy(store)
    neighbor = neighbor_of('batch_recovery_silence_prepare')
    assert store.run(lambda tx: 'ok', operation=neighbor) == 'ok'
    assert clock.sleeps == []


def test_store_stamp_recovery_silence_complete_leaves_other_labels_unarmed(monkeypatch):
    damper, clock = make_damper()
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    error = exhaust_run(store, 'batch_recovery_silence_complete')
    assert error.retry_after > 0
    assert set(damper._armed_until) == {'batch_recovery_silence_complete'}
    make_healthy(store)
    neighbor = neighbor_of('batch_recovery_silence_complete')
    assert store.run(lambda tx: 'ok', operation=neighbor) == 'ok'
    assert clock.sleeps == []


def test_store_stamp_terminal_empty_prepare_leaves_other_labels_unarmed(monkeypatch):
    damper, clock = make_damper()
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    error = exhaust_run(store, 'batch_terminal_empty_prepare')
    assert error.retry_after > 0
    assert set(damper._armed_until) == {'batch_terminal_empty_prepare'}
    make_healthy(store)
    neighbor = neighbor_of('batch_terminal_empty_prepare')
    assert store.run(lambda tx: 'ok', operation=neighbor) == 'ok'
    assert clock.sleeps == []


def test_store_stamp_terminal_empty_complete_leaves_other_labels_unarmed(monkeypatch):
    damper, clock = make_damper()
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    error = exhaust_run(store, 'batch_terminal_empty_complete')
    assert error.retry_after > 0
    assert set(damper._armed_until) == {'batch_terminal_empty_complete'}
    make_healthy(store)
    neighbor = neighbor_of('batch_terminal_empty_complete')
    assert store.run(lambda tx: 'ok', operation=neighbor) == 'ok'
    assert clock.sleeps == []


def test_store_stamp_artifact_stage_leaves_other_labels_unarmed(monkeypatch):
    damper, clock = make_damper()
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    error = exhaust_run(store, 'batch_artifact_stage')
    assert error.retry_after > 0
    assert set(damper._armed_until) == {'batch_artifact_stage'}
    make_healthy(store)
    neighbor = neighbor_of('batch_artifact_stage')
    assert store.run(lambda tx: 'ok', operation=neighbor) == 'ok'
    assert clock.sleeps == []


def test_store_stamp_artifact_missing_evidence_leaves_other_labels_unarmed(monkeypatch):
    damper, clock = make_damper()
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    error = exhaust_run(store, 'batch_artifact_missing_evidence')
    assert error.retry_after > 0
    assert set(damper._armed_until) == {'batch_artifact_missing_evidence'}
    make_healthy(store)
    neighbor = neighbor_of('batch_artifact_missing_evidence')
    assert store.run(lambda tx: 'ok', operation=neighbor) == 'ok'
    assert clock.sleeps == []


def test_store_stamp_artifact_missing_restore_leaves_other_labels_unarmed(monkeypatch):
    damper, clock = make_damper()
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    error = exhaust_run(store, 'batch_artifact_missing_restore')
    assert error.retry_after > 0
    assert set(damper._armed_until) == {'batch_artifact_missing_restore'}
    make_healthy(store)
    neighbor = neighbor_of('batch_artifact_missing_restore')
    assert store.run(lambda tx: 'ok', operation=neighbor) == 'ok'
    assert clock.sleeps == []


def test_store_stamp_artifact_missing_apply_leaves_other_labels_unarmed(monkeypatch):
    damper, clock = make_damper()
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    error = exhaust_run(store, 'batch_artifact_missing_apply')
    assert error.retry_after > 0
    assert set(damper._armed_until) == {'batch_artifact_missing_apply'}
    make_healthy(store)
    neighbor = neighbor_of('batch_artifact_missing_apply')
    assert store.run(lambda tx: 'ok', operation=neighbor) == 'ok'
    assert clock.sleeps == []


def test_store_stamp_partial_precheck_leaves_other_labels_unarmed(monkeypatch):
    damper, clock = make_damper()
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    error = exhaust_run(store, 'batch_partial_precheck')
    assert error.retry_after > 0
    assert set(damper._armed_until) == {'batch_partial_precheck'}
    make_healthy(store)
    neighbor = neighbor_of('batch_partial_precheck')
    assert store.run(lambda tx: 'ok', operation=neighbor) == 'ok'
    assert clock.sleeps == []


def test_store_stamp_language_shadow_claim_leaves_other_labels_unarmed(monkeypatch):
    damper, clock = make_damper()
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    error = exhaust_run(store, 'batch_language_shadow_claim')
    assert error.retry_after > 0
    assert set(damper._armed_until) == {'batch_language_shadow_claim'}
    make_healthy(store)
    neighbor = neighbor_of('batch_language_shadow_claim')
    assert store.run(lambda tx: 'ok', operation=neighbor) == 'ok'
    assert clock.sleeps == []


def test_store_stamp_language_shadow_authorize_leaves_other_labels_unarmed(monkeypatch):
    damper, clock = make_damper()
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    error = exhaust_run(store, 'batch_language_shadow_authorize')
    assert error.retry_after > 0
    assert set(damper._armed_until) == {'batch_language_shadow_authorize'}
    make_healthy(store)
    neighbor = neighbor_of('batch_language_shadow_authorize')
    assert store.run(lambda tx: 'ok', operation=neighbor) == 'ok'
    assert clock.sleeps == []


def test_store_stamp_language_shadow_release_leaves_other_labels_unarmed(monkeypatch):
    damper, clock = make_damper()
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    error = exhaust_run(store, 'batch_language_shadow_release')
    assert error.retry_after > 0
    assert set(damper._armed_until) == {'batch_language_shadow_release'}
    make_healthy(store)
    neighbor = neighbor_of('batch_language_shadow_release')
    assert store.run(lambda tx: 'ok', operation=neighbor) == 'ok'
    assert clock.sleeps == []


def test_store_stamp_provider_stt_leaves_other_labels_unarmed(monkeypatch):
    damper, clock = make_damper()
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    error = exhaust_run(store, 'batch_provider_stt')
    assert error.retry_after > 0
    assert set(damper._armed_until) == {'batch_provider_stt'}
    make_healthy(store)
    neighbor = neighbor_of('batch_provider_stt')
    assert store.run(lambda tx: 'ok', operation=neighbor) == 'ok'
    assert clock.sleeps == []


def test_store_stamp_enqueue_leaves_other_labels_unarmed(monkeypatch):
    damper, clock = make_damper()
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    error = exhaust_run(store, 'batch_enqueue')
    assert error.retry_after > 0
    assert set(damper._armed_until) == {'batch_enqueue'}
    make_healthy(store)
    neighbor = neighbor_of('batch_enqueue')
    assert store.run(lambda tx: 'ok', operation=neighbor) == 'ok'
    assert clock.sleeps == []


def test_store_stamp_heartbeat_leaves_other_labels_unarmed(monkeypatch):
    damper, clock = make_damper()
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    error = exhaust_run(store, 'batch_heartbeat')
    assert error.retry_after > 0
    assert set(damper._armed_until) == {'batch_heartbeat'}
    make_healthy(store)
    neighbor = neighbor_of('batch_heartbeat')
    assert store.run(lambda tx: 'ok', operation=neighbor) == 'ok'
    assert clock.sleeps == []


def test_store_stamp_complete_leaves_other_labels_unarmed(monkeypatch):
    damper, clock = make_damper()
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    error = exhaust_run(store, 'batch_complete')
    assert error.retry_after > 0
    assert set(damper._armed_until) == {'batch_complete'}
    make_healthy(store)
    neighbor = neighbor_of('batch_complete')
    assert store.run(lambda tx: 'ok', operation=neighbor) == 'ok'
    assert clock.sleeps == []


def test_store_stamp_fail_leaves_other_labels_unarmed(monkeypatch):
    damper, clock = make_damper()
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    error = exhaust_run(store, 'batch_fail')
    assert error.retry_after > 0
    assert set(damper._armed_until) == {'batch_fail'}
    make_healthy(store)
    neighbor = neighbor_of('batch_fail')
    assert store.run(lambda tx: 'ok', operation=neighbor) == 'ok'
    assert clock.sleeps == []


def test_store_stamp_defer_leaves_other_labels_unarmed(monkeypatch):
    damper, clock = make_damper()
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    error = exhaust_run(store, 'batch_defer')
    assert error.retry_after > 0
    assert set(damper._armed_until) == {'batch_defer'}
    make_healthy(store)
    neighbor = neighbor_of('batch_defer')
    assert store.run(lambda tx: 'ok', operation=neighbor) == 'ok'
    assert clock.sleeps == []


def test_store_stamp_release_leaves_other_labels_unarmed(monkeypatch):
    damper, clock = make_damper()
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    error = exhaust_run(store, 'batch_release')
    assert error.retry_after > 0
    assert set(damper._armed_until) == {'batch_release'}
    make_healthy(store)
    neighbor = neighbor_of('batch_release')
    assert store.run(lambda tx: 'ok', operation=neighbor) == 'ok'
    assert clock.sleeps == []


def test_store_stamp_recover_leaves_other_labels_unarmed(monkeypatch):
    damper, clock = make_damper()
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    error = exhaust_run(store, 'batch_recover')
    assert error.retry_after > 0
    assert set(damper._armed_until) == {'batch_recover'}
    make_healthy(store)
    neighbor = neighbor_of('batch_recover')
    assert store.run(lambda tx: 'ok', operation=neighbor) == 'ok'
    assert clock.sleeps == []


def test_store_stamp_redrive_leaves_other_labels_unarmed(monkeypatch):
    damper, clock = make_damper()
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    error = exhaust_run(store, 'batch_redrive')
    assert error.retry_after > 0
    assert set(damper._armed_until) == {'batch_redrive'}
    make_healthy(store)
    neighbor = neighbor_of('batch_redrive')
    assert store.run(lambda tx: 'ok', operation=neighbor) == 'ok'
    assert clock.sleeps == []


def test_store_stamp_gpu_release_leaves_other_labels_unarmed(monkeypatch):
    damper, clock = make_damper()
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    error = exhaust_run(store, 'batch_gpu_release')
    assert error.retry_after > 0
    assert set(damper._armed_until) == {'batch_gpu_release'}
    make_healthy(store)
    neighbor = neighbor_of('batch_gpu_release')
    assert store.run(lambda tx: 'ok', operation=neighbor) == 'ok'
    assert clock.sleeps == []


def test_store_stamp_shadow_offer_leaves_other_labels_unarmed(monkeypatch):
    damper, clock = make_damper()
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    error = exhaust_run(store, 'batch_shadow_offer')
    assert error.retry_after > 0
    assert set(damper._armed_until) == {'batch_shadow_offer'}
    make_healthy(store)
    neighbor = neighbor_of('batch_shadow_offer')
    assert store.run(lambda tx: 'ok', operation=neighbor) == 'ok'
    assert clock.sleeps == []


def test_store_stamp_shadow_take_leaves_other_labels_unarmed(monkeypatch):
    damper, clock = make_damper()
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    error = exhaust_run(store, 'batch_shadow_take')
    assert error.retry_after > 0
    assert set(damper._armed_until) == {'batch_shadow_take'}
    make_healthy(store)
    neighbor = neighbor_of('batch_shadow_take')
    assert store.run(lambda tx: 'ok', operation=neighbor) == 'ok'
    assert clock.sleeps == []


def test_store_stamp_shadow_reserve_leaves_other_labels_unarmed(monkeypatch):
    damper, clock = make_damper()
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    error = exhaust_run(store, 'batch_shadow_reserve')
    assert error.retry_after > 0
    assert set(damper._armed_until) == {'batch_shadow_reserve'}
    make_healthy(store)
    neighbor = neighbor_of('batch_shadow_reserve')
    assert store.run(lambda tx: 'ok', operation=neighbor) == 'ok'
    assert clock.sleeps == []


def test_store_stamp_shadow_finish_leaves_other_labels_unarmed(monkeypatch):
    damper, clock = make_damper()
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    error = exhaust_run(store, 'batch_shadow_finish')
    assert error.retry_after > 0
    assert set(damper._armed_until) == {'batch_shadow_finish'}
    make_healthy(store)
    neighbor = neighbor_of('batch_shadow_finish')
    assert store.run(lambda tx: 'ok', operation=neighbor) == 'ok'
    assert clock.sleeps == []


def test_store_stamp_shadow_reap_leaves_other_labels_unarmed(monkeypatch):
    damper, clock = make_damper()
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    error = exhaust_run(store, 'batch_shadow_reap')
    assert error.retry_after > 0
    assert set(damper._armed_until) == {'batch_shadow_reap'}
    make_healthy(store)
    neighbor = neighbor_of('batch_shadow_reap')
    assert store.run(lambda tx: 'ok', operation=neighbor) == 'ok'
    assert clock.sleeps == []


def test_store_stamp_shadow_ready_leaves_other_labels_unarmed(monkeypatch):
    damper, clock = make_damper()
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    error = exhaust_run(store, 'batch_shadow_ready')
    assert error.retry_after > 0
    assert set(damper._armed_until) == {'batch_shadow_ready'}
    make_healthy(store)
    neighbor = neighbor_of('batch_shadow_ready')
    assert store.run(lambda tx: 'ok', operation=neighbor) == 'ok'
    assert clock.sleeps == []


def test_store_stamp_shadow_projection_input_leaves_other_labels_unarmed(monkeypatch):
    damper, clock = make_damper()
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    error = exhaust_run(store, 'batch_shadow_projection_input')
    assert error.retry_after > 0
    assert set(damper._armed_until) == {'batch_shadow_projection_input'}
    make_healthy(store)
    neighbor = neighbor_of('batch_shadow_projection_input')
    assert store.run(lambda tx: 'ok', operation=neighbor) == 'ok'
    assert clock.sleeps == []


def test_store_stamp_shadow_paid_leaves_other_labels_unarmed(monkeypatch):
    damper, clock = make_damper()
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    error = exhaust_run(store, 'batch_shadow_paid')
    assert error.retry_after > 0
    assert set(damper._armed_until) == {'batch_shadow_paid'}
    make_healthy(store)
    neighbor = neighbor_of('batch_shadow_paid')
    assert store.run(lambda tx: 'ok', operation=neighbor) == 'ok'
    assert clock.sleeps == []


def test_store_stamp_shadow_handoff_leaves_other_labels_unarmed(monkeypatch):
    damper, clock = make_damper()
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    error = exhaust_run(store, 'batch_shadow_handoff')
    assert error.retry_after > 0
    assert set(damper._armed_until) == {'batch_shadow_handoff'}
    make_healthy(store)
    neighbor = neighbor_of('batch_shadow_handoff')
    assert store.run(lambda tx: 'ok', operation=neighbor) == 'ok'
    assert clock.sleeps == []


def test_store_stamp_shadow_start_recovery_leaves_other_labels_unarmed(monkeypatch):
    damper, clock = make_damper()
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    error = exhaust_run(store, 'batch_shadow_start_recovery')
    assert error.retry_after > 0
    assert set(damper._armed_until) == {'batch_shadow_start_recovery'}
    make_healthy(store)
    neighbor = neighbor_of('batch_shadow_start_recovery')
    assert store.run(lambda tx: 'ok', operation=neighbor) == 'ok'
    assert clock.sleeps == []


def test_store_stamp_composite_pull_shard_00_stamps(monkeypatch):
    damper, _clock = make_damper()
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_pull shard=scheduler_00')
    assert error.retry_after == pytest.approx(0.25)
    assert set(damper._armed_until) == {'batch_pull shard=scheduler_00'}


def test_store_stamp_composite_pull_shard_07_stamps(monkeypatch):
    damper, _clock = make_damper()
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_pull shard=scheduler_07')
    assert error.retry_after == pytest.approx(0.25)
    assert set(damper._armed_until) == {'batch_pull shard=scheduler_07'}


def test_store_stamp_composite_pull_shard_33_stamps(monkeypatch):
    damper, _clock = make_damper()
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_pull shard=scheduler_33')
    assert error.retry_after == pytest.approx(0.25)
    assert set(damper._armed_until) == {'batch_pull shard=scheduler_33'}


def test_store_stamp_composite_pull_shard_60_stamps(monkeypatch):
    damper, _clock = make_damper()
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_pull shard=scheduler_60')
    assert error.retry_after == pytest.approx(0.25)
    assert set(damper._armed_until) == {'batch_pull shard=scheduler_60'}


def test_store_stamp_merge_commit_success_clears_then_restamps_first_rung(monkeypatch):
    damper, _clock = make_damper()
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    first = exhaust_run(store, 'batch_merge_commit')
    assert first.retry_after == pytest.approx(BASE_SECONDS)
    make_healthy(store)
    assert store.run(lambda tx: 'ok', operation='batch_merge_commit') == 'ok'
    assert 'batch_merge_commit' not in damper._armed_until
    assert 'batch_merge_commit' not in damper._failures
    assert 'batch_merge_commit' not in damper._generations
    make_exhausting(store)
    second = exhaust_run(store, 'batch_merge_commit')
    assert second.retry_after == pytest.approx(BASE_SECONDS)


def test_store_stamp_admit_success_clears_then_restamps_first_rung(monkeypatch):
    damper, _clock = make_damper()
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    first = exhaust_run(store, 'batch_admit')
    assert first.retry_after == pytest.approx(BASE_SECONDS)
    make_healthy(store)
    assert store.run(lambda tx: 'ok', operation='batch_admit') == 'ok'
    assert 'batch_admit' not in damper._armed_until
    assert 'batch_admit' not in damper._failures
    assert 'batch_admit' not in damper._generations
    make_exhausting(store)
    second = exhaust_run(store, 'batch_admit')
    assert second.retry_after == pytest.approx(BASE_SECONDS)


def test_store_stamp_content_ledger_accept_success_clears_then_restamps_first_rung(monkeypatch):
    damper, _clock = make_damper()
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    first = exhaust_run(store, 'batch_content_ledger_accept')
    assert first.retry_after == pytest.approx(BASE_SECONDS)
    make_healthy(store)
    assert store.run(lambda tx: 'ok', operation='batch_content_ledger_accept') == 'ok'
    assert 'batch_content_ledger_accept' not in damper._armed_until
    assert 'batch_content_ledger_accept' not in damper._failures
    assert 'batch_content_ledger_accept' not in damper._generations
    make_exhausting(store)
    second = exhaust_run(store, 'batch_content_ledger_accept')
    assert second.retry_after == pytest.approx(BASE_SECONDS)


def test_store_stamp_recognizer_receipt_success_clears_then_restamps_first_rung(monkeypatch):
    damper, _clock = make_damper()
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    first = exhaust_run(store, 'batch_recognizer_receipt')
    assert first.retry_after == pytest.approx(BASE_SECONDS)
    make_healthy(store)
    assert store.run(lambda tx: 'ok', operation='batch_recognizer_receipt') == 'ok'
    assert 'batch_recognizer_receipt' not in damper._armed_until
    assert 'batch_recognizer_receipt' not in damper._failures
    assert 'batch_recognizer_receipt' not in damper._generations
    make_exhausting(store)
    second = exhaust_run(store, 'batch_recognizer_receipt')
    assert second.retry_after == pytest.approx(BASE_SECONDS)


def test_store_stamp_recovery_prepare_success_clears_then_restamps_first_rung(monkeypatch):
    damper, _clock = make_damper()
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    first = exhaust_run(store, 'batch_recovery_prepare')
    assert first.retry_after == pytest.approx(BASE_SECONDS)
    make_healthy(store)
    assert store.run(lambda tx: 'ok', operation='batch_recovery_prepare') == 'ok'
    assert 'batch_recovery_prepare' not in damper._armed_until
    assert 'batch_recovery_prepare' not in damper._failures
    assert 'batch_recovery_prepare' not in damper._generations
    make_exhausting(store)
    second = exhaust_run(store, 'batch_recovery_prepare')
    assert second.retry_after == pytest.approx(BASE_SECONDS)


def test_store_stamp_recovery_claim_wake_success_clears_then_restamps_first_rung(monkeypatch):
    damper, _clock = make_damper()
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    first = exhaust_run(store, 'batch_recovery_claim_wake')
    assert first.retry_after == pytest.approx(BASE_SECONDS)
    make_healthy(store)
    assert store.run(lambda tx: 'ok', operation='batch_recovery_claim_wake') == 'ok'
    assert 'batch_recovery_claim_wake' not in damper._armed_until
    assert 'batch_recovery_claim_wake' not in damper._failures
    assert 'batch_recovery_claim_wake' not in damper._generations
    make_exhausting(store)
    second = exhaust_run(store, 'batch_recovery_claim_wake')
    assert second.retry_after == pytest.approx(BASE_SECONDS)


def test_store_stamp_recovery_extend_wake_success_clears_then_restamps_first_rung(monkeypatch):
    damper, _clock = make_damper()
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    first = exhaust_run(store, 'batch_recovery_extend_wake')
    assert first.retry_after == pytest.approx(BASE_SECONDS)
    make_healthy(store)
    assert store.run(lambda tx: 'ok', operation='batch_recovery_extend_wake') == 'ok'
    assert 'batch_recovery_extend_wake' not in damper._armed_until
    assert 'batch_recovery_extend_wake' not in damper._failures
    assert 'batch_recovery_extend_wake' not in damper._generations
    make_exhausting(store)
    second = exhaust_run(store, 'batch_recovery_extend_wake')
    assert second.retry_after == pytest.approx(BASE_SECONDS)


def test_store_stamp_recovery_shorten_wake_success_clears_then_restamps_first_rung(monkeypatch):
    damper, _clock = make_damper()
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    first = exhaust_run(store, 'batch_recovery_shorten_wake')
    assert first.retry_after == pytest.approx(BASE_SECONDS)
    make_healthy(store)
    assert store.run(lambda tx: 'ok', operation='batch_recovery_shorten_wake') == 'ok'
    assert 'batch_recovery_shorten_wake' not in damper._armed_until
    assert 'batch_recovery_shorten_wake' not in damper._failures
    assert 'batch_recovery_shorten_wake' not in damper._generations
    make_exhausting(store)
    second = exhaust_run(store, 'batch_recovery_shorten_wake')
    assert second.retry_after == pytest.approx(BASE_SECONDS)


def test_store_stamp_recovery_start_success_clears_then_restamps_first_rung(monkeypatch):
    damper, _clock = make_damper()
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    first = exhaust_run(store, 'batch_recovery_start')
    assert first.retry_after == pytest.approx(BASE_SECONDS)
    make_healthy(store)
    assert store.run(lambda tx: 'ok', operation='batch_recovery_start') == 'ok'
    assert 'batch_recovery_start' not in damper._armed_until
    assert 'batch_recovery_start' not in damper._failures
    assert 'batch_recovery_start' not in damper._generations
    make_exhausting(store)
    second = exhaust_run(store, 'batch_recovery_start')
    assert second.retry_after == pytest.approx(BASE_SECONDS)


def test_store_stamp_recovery_observe_vad_success_clears_then_restamps_first_rung(monkeypatch):
    damper, _clock = make_damper()
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    first = exhaust_run(store, 'batch_recovery_observe_vad')
    assert first.retry_after == pytest.approx(BASE_SECONDS)
    make_healthy(store)
    assert store.run(lambda tx: 'ok', operation='batch_recovery_observe_vad') == 'ok'
    assert 'batch_recovery_observe_vad' not in damper._armed_until
    assert 'batch_recovery_observe_vad' not in damper._failures
    assert 'batch_recovery_observe_vad' not in damper._generations
    make_exhausting(store)
    second = exhaust_run(store, 'batch_recovery_observe_vad')
    assert second.retry_after == pytest.approx(BASE_SECONDS)


def test_store_stamp_recovery_retry_missing_result_success_clears_then_restamps_first_rung(monkeypatch):
    damper, _clock = make_damper()
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    first = exhaust_run(store, 'batch_recovery_retry_missing_result')
    assert first.retry_after == pytest.approx(BASE_SECONDS)
    make_healthy(store)
    assert store.run(lambda tx: 'ok', operation='batch_recovery_retry_missing_result') == 'ok'
    assert 'batch_recovery_retry_missing_result' not in damper._armed_until
    assert 'batch_recovery_retry_missing_result' not in damper._failures
    assert 'batch_recovery_retry_missing_result' not in damper._generations
    make_exhausting(store)
    second = exhaust_run(store, 'batch_recovery_retry_missing_result')
    assert second.retry_after == pytest.approx(BASE_SECONDS)


def test_store_stamp_recovery_hold_duration_limit_success_clears_then_restamps_first_rung(monkeypatch):
    damper, _clock = make_damper()
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    first = exhaust_run(store, 'batch_recovery_hold_duration_limit')
    assert first.retry_after == pytest.approx(BASE_SECONDS)
    make_healthy(store)
    assert store.run(lambda tx: 'ok', operation='batch_recovery_hold_duration_limit') == 'ok'
    assert 'batch_recovery_hold_duration_limit' not in damper._armed_until
    assert 'batch_recovery_hold_duration_limit' not in damper._failures
    assert 'batch_recovery_hold_duration_limit' not in damper._generations
    make_exhausting(store)
    second = exhaust_run(store, 'batch_recovery_hold_duration_limit')
    assert second.retry_after == pytest.approx(BASE_SECONDS)


def test_store_stamp_recovery_hold_invalid_manifest_success_clears_then_restamps_first_rung(monkeypatch):
    damper, _clock = make_damper()
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    first = exhaust_run(store, 'batch_recovery_hold_invalid_manifest')
    assert first.retry_after == pytest.approx(BASE_SECONDS)
    make_healthy(store)
    assert store.run(lambda tx: 'ok', operation='batch_recovery_hold_invalid_manifest') == 'ok'
    assert 'batch_recovery_hold_invalid_manifest' not in damper._armed_until
    assert 'batch_recovery_hold_invalid_manifest' not in damper._failures
    assert 'batch_recovery_hold_invalid_manifest' not in damper._generations
    make_exhausting(store)
    second = exhaust_run(store, 'batch_recovery_hold_invalid_manifest')
    assert second.retry_after == pytest.approx(BASE_SECONDS)


def test_store_stamp_recovery_start_duration_limited_success_clears_then_restamps_first_rung(monkeypatch):
    damper, _clock = make_damper()
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    first = exhaust_run(store, 'batch_recovery_start_duration_limited')
    assert first.retry_after == pytest.approx(BASE_SECONDS)
    make_healthy(store)
    assert store.run(lambda tx: 'ok', operation='batch_recovery_start_duration_limited') == 'ok'
    assert 'batch_recovery_start_duration_limited' not in damper._armed_until
    assert 'batch_recovery_start_duration_limited' not in damper._failures
    assert 'batch_recovery_start_duration_limited' not in damper._generations
    make_exhausting(store)
    second = exhaust_run(store, 'batch_recovery_start_duration_limited')
    assert second.retry_after == pytest.approx(BASE_SECONDS)


def test_store_stamp_recovery_paid_takeover_success_clears_then_restamps_first_rung(monkeypatch):
    damper, _clock = make_damper()
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    first = exhaust_run(store, 'batch_recovery_paid_takeover')
    assert first.retry_after == pytest.approx(BASE_SECONDS)
    make_healthy(store)
    assert store.run(lambda tx: 'ok', operation='batch_recovery_paid_takeover') == 'ok'
    assert 'batch_recovery_paid_takeover' not in damper._armed_until
    assert 'batch_recovery_paid_takeover' not in damper._failures
    assert 'batch_recovery_paid_takeover' not in damper._generations
    make_exhausting(store)
    second = exhaust_run(store, 'batch_recovery_paid_takeover')
    assert second.retry_after == pytest.approx(BASE_SECONDS)


def test_store_stamp_recovery_settle_success_clears_then_restamps_first_rung(monkeypatch):
    damper, _clock = make_damper()
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    first = exhaust_run(store, 'batch_recovery_settle')
    assert first.retry_after == pytest.approx(BASE_SECONDS)
    make_healthy(store)
    assert store.run(lambda tx: 'ok', operation='batch_recovery_settle') == 'ok'
    assert 'batch_recovery_settle' not in damper._armed_until
    assert 'batch_recovery_settle' not in damper._failures
    assert 'batch_recovery_settle' not in damper._generations
    make_exhausting(store)
    second = exhaust_run(store, 'batch_recovery_settle')
    assert second.retry_after == pytest.approx(BASE_SECONDS)


def test_store_stamp_recovery_silence_prepare_success_clears_then_restamps_first_rung(monkeypatch):
    damper, _clock = make_damper()
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    first = exhaust_run(store, 'batch_recovery_silence_prepare')
    assert first.retry_after == pytest.approx(BASE_SECONDS)
    make_healthy(store)
    assert store.run(lambda tx: 'ok', operation='batch_recovery_silence_prepare') == 'ok'
    assert 'batch_recovery_silence_prepare' not in damper._armed_until
    assert 'batch_recovery_silence_prepare' not in damper._failures
    assert 'batch_recovery_silence_prepare' not in damper._generations
    make_exhausting(store)
    second = exhaust_run(store, 'batch_recovery_silence_prepare')
    assert second.retry_after == pytest.approx(BASE_SECONDS)


def test_store_stamp_recovery_silence_complete_success_clears_then_restamps_first_rung(monkeypatch):
    damper, _clock = make_damper()
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    first = exhaust_run(store, 'batch_recovery_silence_complete')
    assert first.retry_after == pytest.approx(BASE_SECONDS)
    make_healthy(store)
    assert store.run(lambda tx: 'ok', operation='batch_recovery_silence_complete') == 'ok'
    assert 'batch_recovery_silence_complete' not in damper._armed_until
    assert 'batch_recovery_silence_complete' not in damper._failures
    assert 'batch_recovery_silence_complete' not in damper._generations
    make_exhausting(store)
    second = exhaust_run(store, 'batch_recovery_silence_complete')
    assert second.retry_after == pytest.approx(BASE_SECONDS)


def test_store_stamp_terminal_empty_prepare_success_clears_then_restamps_first_rung(monkeypatch):
    damper, _clock = make_damper()
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    first = exhaust_run(store, 'batch_terminal_empty_prepare')
    assert first.retry_after == pytest.approx(BASE_SECONDS)
    make_healthy(store)
    assert store.run(lambda tx: 'ok', operation='batch_terminal_empty_prepare') == 'ok'
    assert 'batch_terminal_empty_prepare' not in damper._armed_until
    assert 'batch_terminal_empty_prepare' not in damper._failures
    assert 'batch_terminal_empty_prepare' not in damper._generations
    make_exhausting(store)
    second = exhaust_run(store, 'batch_terminal_empty_prepare')
    assert second.retry_after == pytest.approx(BASE_SECONDS)


def test_store_stamp_terminal_empty_complete_success_clears_then_restamps_first_rung(monkeypatch):
    damper, _clock = make_damper()
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    first = exhaust_run(store, 'batch_terminal_empty_complete')
    assert first.retry_after == pytest.approx(BASE_SECONDS)
    make_healthy(store)
    assert store.run(lambda tx: 'ok', operation='batch_terminal_empty_complete') == 'ok'
    assert 'batch_terminal_empty_complete' not in damper._armed_until
    assert 'batch_terminal_empty_complete' not in damper._failures
    assert 'batch_terminal_empty_complete' not in damper._generations
    make_exhausting(store)
    second = exhaust_run(store, 'batch_terminal_empty_complete')
    assert second.retry_after == pytest.approx(BASE_SECONDS)


def test_store_stamp_artifact_stage_success_clears_then_restamps_first_rung(monkeypatch):
    damper, _clock = make_damper()
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    first = exhaust_run(store, 'batch_artifact_stage')
    assert first.retry_after == pytest.approx(BASE_SECONDS)
    make_healthy(store)
    assert store.run(lambda tx: 'ok', operation='batch_artifact_stage') == 'ok'
    assert 'batch_artifact_stage' not in damper._armed_until
    assert 'batch_artifact_stage' not in damper._failures
    assert 'batch_artifact_stage' not in damper._generations
    make_exhausting(store)
    second = exhaust_run(store, 'batch_artifact_stage')
    assert second.retry_after == pytest.approx(BASE_SECONDS)


def test_store_stamp_artifact_missing_evidence_success_clears_then_restamps_first_rung(monkeypatch):
    damper, _clock = make_damper()
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    first = exhaust_run(store, 'batch_artifact_missing_evidence')
    assert first.retry_after == pytest.approx(BASE_SECONDS)
    make_healthy(store)
    assert store.run(lambda tx: 'ok', operation='batch_artifact_missing_evidence') == 'ok'
    assert 'batch_artifact_missing_evidence' not in damper._armed_until
    assert 'batch_artifact_missing_evidence' not in damper._failures
    assert 'batch_artifact_missing_evidence' not in damper._generations
    make_exhausting(store)
    second = exhaust_run(store, 'batch_artifact_missing_evidence')
    assert second.retry_after == pytest.approx(BASE_SECONDS)


def test_store_stamp_artifact_missing_restore_success_clears_then_restamps_first_rung(monkeypatch):
    damper, _clock = make_damper()
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    first = exhaust_run(store, 'batch_artifact_missing_restore')
    assert first.retry_after == pytest.approx(BASE_SECONDS)
    make_healthy(store)
    assert store.run(lambda tx: 'ok', operation='batch_artifact_missing_restore') == 'ok'
    assert 'batch_artifact_missing_restore' not in damper._armed_until
    assert 'batch_artifact_missing_restore' not in damper._failures
    assert 'batch_artifact_missing_restore' not in damper._generations
    make_exhausting(store)
    second = exhaust_run(store, 'batch_artifact_missing_restore')
    assert second.retry_after == pytest.approx(BASE_SECONDS)


def test_store_stamp_artifact_missing_apply_success_clears_then_restamps_first_rung(monkeypatch):
    damper, _clock = make_damper()
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    first = exhaust_run(store, 'batch_artifact_missing_apply')
    assert first.retry_after == pytest.approx(BASE_SECONDS)
    make_healthy(store)
    assert store.run(lambda tx: 'ok', operation='batch_artifact_missing_apply') == 'ok'
    assert 'batch_artifact_missing_apply' not in damper._armed_until
    assert 'batch_artifact_missing_apply' not in damper._failures
    assert 'batch_artifact_missing_apply' not in damper._generations
    make_exhausting(store)
    second = exhaust_run(store, 'batch_artifact_missing_apply')
    assert second.retry_after == pytest.approx(BASE_SECONDS)


def test_store_stamp_partial_precheck_success_clears_then_restamps_first_rung(monkeypatch):
    damper, _clock = make_damper()
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    first = exhaust_run(store, 'batch_partial_precheck')
    assert first.retry_after == pytest.approx(BASE_SECONDS)
    make_healthy(store)
    assert store.run(lambda tx: 'ok', operation='batch_partial_precheck') == 'ok'
    assert 'batch_partial_precheck' not in damper._armed_until
    assert 'batch_partial_precheck' not in damper._failures
    assert 'batch_partial_precheck' not in damper._generations
    make_exhausting(store)
    second = exhaust_run(store, 'batch_partial_precheck')
    assert second.retry_after == pytest.approx(BASE_SECONDS)


def test_store_stamp_language_shadow_claim_success_clears_then_restamps_first_rung(monkeypatch):
    damper, _clock = make_damper()
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    first = exhaust_run(store, 'batch_language_shadow_claim')
    assert first.retry_after == pytest.approx(BASE_SECONDS)
    make_healthy(store)
    assert store.run(lambda tx: 'ok', operation='batch_language_shadow_claim') == 'ok'
    assert 'batch_language_shadow_claim' not in damper._armed_until
    assert 'batch_language_shadow_claim' not in damper._failures
    assert 'batch_language_shadow_claim' not in damper._generations
    make_exhausting(store)
    second = exhaust_run(store, 'batch_language_shadow_claim')
    assert second.retry_after == pytest.approx(BASE_SECONDS)


def test_store_stamp_language_shadow_authorize_success_clears_then_restamps_first_rung(monkeypatch):
    damper, _clock = make_damper()
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    first = exhaust_run(store, 'batch_language_shadow_authorize')
    assert first.retry_after == pytest.approx(BASE_SECONDS)
    make_healthy(store)
    assert store.run(lambda tx: 'ok', operation='batch_language_shadow_authorize') == 'ok'
    assert 'batch_language_shadow_authorize' not in damper._armed_until
    assert 'batch_language_shadow_authorize' not in damper._failures
    assert 'batch_language_shadow_authorize' not in damper._generations
    make_exhausting(store)
    second = exhaust_run(store, 'batch_language_shadow_authorize')
    assert second.retry_after == pytest.approx(BASE_SECONDS)


def test_store_stamp_language_shadow_release_success_clears_then_restamps_first_rung(monkeypatch):
    damper, _clock = make_damper()
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    first = exhaust_run(store, 'batch_language_shadow_release')
    assert first.retry_after == pytest.approx(BASE_SECONDS)
    make_healthy(store)
    assert store.run(lambda tx: 'ok', operation='batch_language_shadow_release') == 'ok'
    assert 'batch_language_shadow_release' not in damper._armed_until
    assert 'batch_language_shadow_release' not in damper._failures
    assert 'batch_language_shadow_release' not in damper._generations
    make_exhausting(store)
    second = exhaust_run(store, 'batch_language_shadow_release')
    assert second.retry_after == pytest.approx(BASE_SECONDS)


def test_store_stamp_provider_stt_success_clears_then_restamps_first_rung(monkeypatch):
    damper, _clock = make_damper()
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    first = exhaust_run(store, 'batch_provider_stt')
    assert first.retry_after == pytest.approx(BASE_SECONDS)
    make_healthy(store)
    assert store.run(lambda tx: 'ok', operation='batch_provider_stt') == 'ok'
    assert 'batch_provider_stt' not in damper._armed_until
    assert 'batch_provider_stt' not in damper._failures
    assert 'batch_provider_stt' not in damper._generations
    make_exhausting(store)
    second = exhaust_run(store, 'batch_provider_stt')
    assert second.retry_after == pytest.approx(BASE_SECONDS)


def test_store_stamp_enqueue_success_clears_then_restamps_first_rung(monkeypatch):
    damper, _clock = make_damper()
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    first = exhaust_run(store, 'batch_enqueue')
    assert first.retry_after == pytest.approx(BASE_SECONDS)
    make_healthy(store)
    assert store.run(lambda tx: 'ok', operation='batch_enqueue') == 'ok'
    assert 'batch_enqueue' not in damper._armed_until
    assert 'batch_enqueue' not in damper._failures
    assert 'batch_enqueue' not in damper._generations
    make_exhausting(store)
    second = exhaust_run(store, 'batch_enqueue')
    assert second.retry_after == pytest.approx(BASE_SECONDS)


def test_store_stamp_heartbeat_success_clears_then_restamps_first_rung(monkeypatch):
    damper, _clock = make_damper()
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    first = exhaust_run(store, 'batch_heartbeat')
    assert first.retry_after == pytest.approx(BASE_SECONDS)
    make_healthy(store)
    assert store.run(lambda tx: 'ok', operation='batch_heartbeat') == 'ok'
    assert 'batch_heartbeat' not in damper._armed_until
    assert 'batch_heartbeat' not in damper._failures
    assert 'batch_heartbeat' not in damper._generations
    make_exhausting(store)
    second = exhaust_run(store, 'batch_heartbeat')
    assert second.retry_after == pytest.approx(BASE_SECONDS)


def test_store_stamp_complete_success_clears_then_restamps_first_rung(monkeypatch):
    damper, _clock = make_damper()
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    first = exhaust_run(store, 'batch_complete')
    assert first.retry_after == pytest.approx(BASE_SECONDS)
    make_healthy(store)
    assert store.run(lambda tx: 'ok', operation='batch_complete') == 'ok'
    assert 'batch_complete' not in damper._armed_until
    assert 'batch_complete' not in damper._failures
    assert 'batch_complete' not in damper._generations
    make_exhausting(store)
    second = exhaust_run(store, 'batch_complete')
    assert second.retry_after == pytest.approx(BASE_SECONDS)


def test_store_stamp_fail_success_clears_then_restamps_first_rung(monkeypatch):
    damper, _clock = make_damper()
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    first = exhaust_run(store, 'batch_fail')
    assert first.retry_after == pytest.approx(BASE_SECONDS)
    make_healthy(store)
    assert store.run(lambda tx: 'ok', operation='batch_fail') == 'ok'
    assert 'batch_fail' not in damper._armed_until
    assert 'batch_fail' not in damper._failures
    assert 'batch_fail' not in damper._generations
    make_exhausting(store)
    second = exhaust_run(store, 'batch_fail')
    assert second.retry_after == pytest.approx(BASE_SECONDS)


def test_store_stamp_defer_success_clears_then_restamps_first_rung(monkeypatch):
    damper, _clock = make_damper()
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    first = exhaust_run(store, 'batch_defer')
    assert first.retry_after == pytest.approx(BASE_SECONDS)
    make_healthy(store)
    assert store.run(lambda tx: 'ok', operation='batch_defer') == 'ok'
    assert 'batch_defer' not in damper._armed_until
    assert 'batch_defer' not in damper._failures
    assert 'batch_defer' not in damper._generations
    make_exhausting(store)
    second = exhaust_run(store, 'batch_defer')
    assert second.retry_after == pytest.approx(BASE_SECONDS)


def test_store_stamp_release_success_clears_then_restamps_first_rung(monkeypatch):
    damper, _clock = make_damper()
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    first = exhaust_run(store, 'batch_release')
    assert first.retry_after == pytest.approx(BASE_SECONDS)
    make_healthy(store)
    assert store.run(lambda tx: 'ok', operation='batch_release') == 'ok'
    assert 'batch_release' not in damper._armed_until
    assert 'batch_release' not in damper._failures
    assert 'batch_release' not in damper._generations
    make_exhausting(store)
    second = exhaust_run(store, 'batch_release')
    assert second.retry_after == pytest.approx(BASE_SECONDS)


def test_store_stamp_recover_success_clears_then_restamps_first_rung(monkeypatch):
    damper, _clock = make_damper()
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    first = exhaust_run(store, 'batch_recover')
    assert first.retry_after == pytest.approx(BASE_SECONDS)
    make_healthy(store)
    assert store.run(lambda tx: 'ok', operation='batch_recover') == 'ok'
    assert 'batch_recover' not in damper._armed_until
    assert 'batch_recover' not in damper._failures
    assert 'batch_recover' not in damper._generations
    make_exhausting(store)
    second = exhaust_run(store, 'batch_recover')
    assert second.retry_after == pytest.approx(BASE_SECONDS)


def test_store_consult_merge_commit_waits_out_the_stamped_window(monkeypatch):
    damper, clock = make_damper()
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    first = exhaust_run(store, 'batch_merge_commit')
    window = first.retry_after
    assert clock.sleeps == []
    make_healthy(store)
    assert store.run(lambda tx: 'ok', operation='batch_merge_commit') == 'ok'
    assert len(clock.sleeps) == 1
    assert clock.sleeps[0] == pytest.approx(window)


def test_store_consult_admit_waits_out_the_stamped_window(monkeypatch):
    damper, clock = make_damper()
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    first = exhaust_run(store, 'batch_admit')
    window = first.retry_after
    assert clock.sleeps == []
    make_healthy(store)
    assert store.run(lambda tx: 'ok', operation='batch_admit') == 'ok'
    assert len(clock.sleeps) == 1
    assert clock.sleeps[0] == pytest.approx(window)


def test_store_consult_content_ledger_accept_waits_out_the_stamped_window(monkeypatch):
    damper, clock = make_damper()
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    first = exhaust_run(store, 'batch_content_ledger_accept')
    window = first.retry_after
    assert clock.sleeps == []
    make_healthy(store)
    assert store.run(lambda tx: 'ok', operation='batch_content_ledger_accept') == 'ok'
    assert len(clock.sleeps) == 1
    assert clock.sleeps[0] == pytest.approx(window)


def test_store_consult_recognizer_receipt_waits_out_the_stamped_window(monkeypatch):
    damper, clock = make_damper()
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    first = exhaust_run(store, 'batch_recognizer_receipt')
    window = first.retry_after
    assert clock.sleeps == []
    make_healthy(store)
    assert store.run(lambda tx: 'ok', operation='batch_recognizer_receipt') == 'ok'
    assert len(clock.sleeps) == 1
    assert clock.sleeps[0] == pytest.approx(window)


def test_store_consult_recovery_prepare_waits_out_the_stamped_window(monkeypatch):
    damper, clock = make_damper()
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    first = exhaust_run(store, 'batch_recovery_prepare')
    window = first.retry_after
    assert clock.sleeps == []
    make_healthy(store)
    assert store.run(lambda tx: 'ok', operation='batch_recovery_prepare') == 'ok'
    assert len(clock.sleeps) == 1
    assert clock.sleeps[0] == pytest.approx(window)


def test_store_consult_recovery_claim_wake_waits_out_the_stamped_window(monkeypatch):
    damper, clock = make_damper()
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    first = exhaust_run(store, 'batch_recovery_claim_wake')
    window = first.retry_after
    assert clock.sleeps == []
    make_healthy(store)
    assert store.run(lambda tx: 'ok', operation='batch_recovery_claim_wake') == 'ok'
    assert len(clock.sleeps) == 1
    assert clock.sleeps[0] == pytest.approx(window)


def test_store_consult_recovery_extend_wake_waits_out_the_stamped_window(monkeypatch):
    damper, clock = make_damper()
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    first = exhaust_run(store, 'batch_recovery_extend_wake')
    window = first.retry_after
    assert clock.sleeps == []
    make_healthy(store)
    assert store.run(lambda tx: 'ok', operation='batch_recovery_extend_wake') == 'ok'
    assert len(clock.sleeps) == 1
    assert clock.sleeps[0] == pytest.approx(window)


def test_store_consult_recovery_shorten_wake_waits_out_the_stamped_window(monkeypatch):
    damper, clock = make_damper()
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    first = exhaust_run(store, 'batch_recovery_shorten_wake')
    window = first.retry_after
    assert clock.sleeps == []
    make_healthy(store)
    assert store.run(lambda tx: 'ok', operation='batch_recovery_shorten_wake') == 'ok'
    assert len(clock.sleeps) == 1
    assert clock.sleeps[0] == pytest.approx(window)


def test_store_consult_recovery_start_waits_out_the_stamped_window(monkeypatch):
    damper, clock = make_damper()
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    first = exhaust_run(store, 'batch_recovery_start')
    window = first.retry_after
    assert clock.sleeps == []
    make_healthy(store)
    assert store.run(lambda tx: 'ok', operation='batch_recovery_start') == 'ok'
    assert len(clock.sleeps) == 1
    assert clock.sleeps[0] == pytest.approx(window)


def test_store_consult_recovery_observe_vad_waits_out_the_stamped_window(monkeypatch):
    damper, clock = make_damper()
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    first = exhaust_run(store, 'batch_recovery_observe_vad')
    window = first.retry_after
    assert clock.sleeps == []
    make_healthy(store)
    assert store.run(lambda tx: 'ok', operation='batch_recovery_observe_vad') == 'ok'
    assert len(clock.sleeps) == 1
    assert clock.sleeps[0] == pytest.approx(window)


def test_store_consult_recovery_retry_missing_result_waits_out_the_stamped_window(monkeypatch):
    damper, clock = make_damper()
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    first = exhaust_run(store, 'batch_recovery_retry_missing_result')
    window = first.retry_after
    assert clock.sleeps == []
    make_healthy(store)
    assert store.run(lambda tx: 'ok', operation='batch_recovery_retry_missing_result') == 'ok'
    assert len(clock.sleeps) == 1
    assert clock.sleeps[0] == pytest.approx(window)


def test_store_consult_recovery_hold_duration_limit_waits_out_the_stamped_window(monkeypatch):
    damper, clock = make_damper()
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    first = exhaust_run(store, 'batch_recovery_hold_duration_limit')
    window = first.retry_after
    assert clock.sleeps == []
    make_healthy(store)
    assert store.run(lambda tx: 'ok', operation='batch_recovery_hold_duration_limit') == 'ok'
    assert len(clock.sleeps) == 1
    assert clock.sleeps[0] == pytest.approx(window)


def test_store_consult_recovery_hold_invalid_manifest_waits_out_the_stamped_window(monkeypatch):
    damper, clock = make_damper()
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    first = exhaust_run(store, 'batch_recovery_hold_invalid_manifest')
    window = first.retry_after
    assert clock.sleeps == []
    make_healthy(store)
    assert store.run(lambda tx: 'ok', operation='batch_recovery_hold_invalid_manifest') == 'ok'
    assert len(clock.sleeps) == 1
    assert clock.sleeps[0] == pytest.approx(window)


def test_store_consult_recovery_start_duration_limited_waits_out_the_stamped_window(monkeypatch):
    damper, clock = make_damper()
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    first = exhaust_run(store, 'batch_recovery_start_duration_limited')
    window = first.retry_after
    assert clock.sleeps == []
    make_healthy(store)
    assert store.run(lambda tx: 'ok', operation='batch_recovery_start_duration_limited') == 'ok'
    assert len(clock.sleeps) == 1
    assert clock.sleeps[0] == pytest.approx(window)


def test_store_consult_recovery_paid_takeover_waits_out_the_stamped_window(monkeypatch):
    damper, clock = make_damper()
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    first = exhaust_run(store, 'batch_recovery_paid_takeover')
    window = first.retry_after
    assert clock.sleeps == []
    make_healthy(store)
    assert store.run(lambda tx: 'ok', operation='batch_recovery_paid_takeover') == 'ok'
    assert len(clock.sleeps) == 1
    assert clock.sleeps[0] == pytest.approx(window)


def test_store_consult_recovery_settle_waits_out_the_stamped_window(monkeypatch):
    damper, clock = make_damper()
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    first = exhaust_run(store, 'batch_recovery_settle')
    window = first.retry_after
    assert clock.sleeps == []
    make_healthy(store)
    assert store.run(lambda tx: 'ok', operation='batch_recovery_settle') == 'ok'
    assert len(clock.sleeps) == 1
    assert clock.sleeps[0] == pytest.approx(window)


def test_store_consult_recovery_silence_prepare_waits_out_the_stamped_window(monkeypatch):
    damper, clock = make_damper()
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    first = exhaust_run(store, 'batch_recovery_silence_prepare')
    window = first.retry_after
    assert clock.sleeps == []
    make_healthy(store)
    assert store.run(lambda tx: 'ok', operation='batch_recovery_silence_prepare') == 'ok'
    assert len(clock.sleeps) == 1
    assert clock.sleeps[0] == pytest.approx(window)


def test_store_consult_recovery_silence_complete_waits_out_the_stamped_window(monkeypatch):
    damper, clock = make_damper()
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    first = exhaust_run(store, 'batch_recovery_silence_complete')
    window = first.retry_after
    assert clock.sleeps == []
    make_healthy(store)
    assert store.run(lambda tx: 'ok', operation='batch_recovery_silence_complete') == 'ok'
    assert len(clock.sleeps) == 1
    assert clock.sleeps[0] == pytest.approx(window)


def test_store_consult_terminal_empty_prepare_waits_out_the_stamped_window(monkeypatch):
    damper, clock = make_damper()
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    first = exhaust_run(store, 'batch_terminal_empty_prepare')
    window = first.retry_after
    assert clock.sleeps == []
    make_healthy(store)
    assert store.run(lambda tx: 'ok', operation='batch_terminal_empty_prepare') == 'ok'
    assert len(clock.sleeps) == 1
    assert clock.sleeps[0] == pytest.approx(window)


def test_store_consult_terminal_empty_complete_waits_out_the_stamped_window(monkeypatch):
    damper, clock = make_damper()
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    first = exhaust_run(store, 'batch_terminal_empty_complete')
    window = first.retry_after
    assert clock.sleeps == []
    make_healthy(store)
    assert store.run(lambda tx: 'ok', operation='batch_terminal_empty_complete') == 'ok'
    assert len(clock.sleeps) == 1
    assert clock.sleeps[0] == pytest.approx(window)


def test_store_consult_artifact_stage_waits_out_the_stamped_window(monkeypatch):
    damper, clock = make_damper()
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    first = exhaust_run(store, 'batch_artifact_stage')
    window = first.retry_after
    assert clock.sleeps == []
    make_healthy(store)
    assert store.run(lambda tx: 'ok', operation='batch_artifact_stage') == 'ok'
    assert len(clock.sleeps) == 1
    assert clock.sleeps[0] == pytest.approx(window)


def test_store_consult_artifact_missing_evidence_waits_out_the_stamped_window(monkeypatch):
    damper, clock = make_damper()
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    first = exhaust_run(store, 'batch_artifact_missing_evidence')
    window = first.retry_after
    assert clock.sleeps == []
    make_healthy(store)
    assert store.run(lambda tx: 'ok', operation='batch_artifact_missing_evidence') == 'ok'
    assert len(clock.sleeps) == 1
    assert clock.sleeps[0] == pytest.approx(window)


def test_store_consult_artifact_missing_restore_waits_out_the_stamped_window(monkeypatch):
    damper, clock = make_damper()
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    first = exhaust_run(store, 'batch_artifact_missing_restore')
    window = first.retry_after
    assert clock.sleeps == []
    make_healthy(store)
    assert store.run(lambda tx: 'ok', operation='batch_artifact_missing_restore') == 'ok'
    assert len(clock.sleeps) == 1
    assert clock.sleeps[0] == pytest.approx(window)


def test_store_consult_artifact_missing_apply_waits_out_the_stamped_window(monkeypatch):
    damper, clock = make_damper()
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    first = exhaust_run(store, 'batch_artifact_missing_apply')
    window = first.retry_after
    assert clock.sleeps == []
    make_healthy(store)
    assert store.run(lambda tx: 'ok', operation='batch_artifact_missing_apply') == 'ok'
    assert len(clock.sleeps) == 1
    assert clock.sleeps[0] == pytest.approx(window)


def test_store_consult_partial_precheck_waits_out_the_stamped_window(monkeypatch):
    damper, clock = make_damper()
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    first = exhaust_run(store, 'batch_partial_precheck')
    window = first.retry_after
    assert clock.sleeps == []
    make_healthy(store)
    assert store.run(lambda tx: 'ok', operation='batch_partial_precheck') == 'ok'
    assert len(clock.sleeps) == 1
    assert clock.sleeps[0] == pytest.approx(window)


def test_store_consult_language_shadow_claim_waits_out_the_stamped_window(monkeypatch):
    damper, clock = make_damper()
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    first = exhaust_run(store, 'batch_language_shadow_claim')
    window = first.retry_after
    assert clock.sleeps == []
    make_healthy(store)
    assert store.run(lambda tx: 'ok', operation='batch_language_shadow_claim') == 'ok'
    assert len(clock.sleeps) == 1
    assert clock.sleeps[0] == pytest.approx(window)


def test_store_consult_language_shadow_authorize_waits_out_the_stamped_window(monkeypatch):
    damper, clock = make_damper()
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    first = exhaust_run(store, 'batch_language_shadow_authorize')
    window = first.retry_after
    assert clock.sleeps == []
    make_healthy(store)
    assert store.run(lambda tx: 'ok', operation='batch_language_shadow_authorize') == 'ok'
    assert len(clock.sleeps) == 1
    assert clock.sleeps[0] == pytest.approx(window)


def test_store_consult_language_shadow_release_waits_out_the_stamped_window(monkeypatch):
    damper, clock = make_damper()
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    first = exhaust_run(store, 'batch_language_shadow_release')
    window = first.retry_after
    assert clock.sleeps == []
    make_healthy(store)
    assert store.run(lambda tx: 'ok', operation='batch_language_shadow_release') == 'ok'
    assert len(clock.sleeps) == 1
    assert clock.sleeps[0] == pytest.approx(window)


def test_store_consult_provider_stt_waits_out_the_stamped_window(monkeypatch):
    damper, clock = make_damper()
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    first = exhaust_run(store, 'batch_provider_stt')
    window = first.retry_after
    assert clock.sleeps == []
    make_healthy(store)
    assert store.run(lambda tx: 'ok', operation='batch_provider_stt') == 'ok'
    assert len(clock.sleeps) == 1
    assert clock.sleeps[0] == pytest.approx(window)


def test_store_consult_enqueue_waits_out_the_stamped_window(monkeypatch):
    damper, clock = make_damper()
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    first = exhaust_run(store, 'batch_enqueue')
    window = first.retry_after
    assert clock.sleeps == []
    make_healthy(store)
    assert store.run(lambda tx: 'ok', operation='batch_enqueue') == 'ok'
    assert len(clock.sleeps) == 1
    assert clock.sleeps[0] == pytest.approx(window)


def test_store_consult_heartbeat_waits_out_the_stamped_window(monkeypatch):
    damper, clock = make_damper()
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    first = exhaust_run(store, 'batch_heartbeat')
    window = first.retry_after
    assert clock.sleeps == []
    make_healthy(store)
    assert store.run(lambda tx: 'ok', operation='batch_heartbeat') == 'ok'
    assert len(clock.sleeps) == 1
    assert clock.sleeps[0] == pytest.approx(window)


def test_store_consult_complete_waits_out_the_stamped_window(monkeypatch):
    damper, clock = make_damper()
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    first = exhaust_run(store, 'batch_complete')
    window = first.retry_after
    assert clock.sleeps == []
    make_healthy(store)
    assert store.run(lambda tx: 'ok', operation='batch_complete') == 'ok'
    assert len(clock.sleeps) == 1
    assert clock.sleeps[0] == pytest.approx(window)


def test_store_consult_fail_waits_out_the_stamped_window(monkeypatch):
    damper, clock = make_damper()
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    first = exhaust_run(store, 'batch_fail')
    window = first.retry_after
    assert clock.sleeps == []
    make_healthy(store)
    assert store.run(lambda tx: 'ok', operation='batch_fail') == 'ok'
    assert len(clock.sleeps) == 1
    assert clock.sleeps[0] == pytest.approx(window)


def test_store_consult_defer_waits_out_the_stamped_window(monkeypatch):
    damper, clock = make_damper()
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    first = exhaust_run(store, 'batch_defer')
    window = first.retry_after
    assert clock.sleeps == []
    make_healthy(store)
    assert store.run(lambda tx: 'ok', operation='batch_defer') == 'ok'
    assert len(clock.sleeps) == 1
    assert clock.sleeps[0] == pytest.approx(window)


def test_store_consult_release_waits_out_the_stamped_window(monkeypatch):
    damper, clock = make_damper()
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    first = exhaust_run(store, 'batch_release')
    window = first.retry_after
    assert clock.sleeps == []
    make_healthy(store)
    assert store.run(lambda tx: 'ok', operation='batch_release') == 'ok'
    assert len(clock.sleeps) == 1
    assert clock.sleeps[0] == pytest.approx(window)


def test_store_consult_recover_waits_out_the_stamped_window(monkeypatch):
    damper, clock = make_damper()
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    first = exhaust_run(store, 'batch_recover')
    window = first.retry_after
    assert clock.sleeps == []
    make_healthy(store)
    assert store.run(lambda tx: 'ok', operation='batch_recover') == 'ok'
    assert len(clock.sleeps) == 1
    assert clock.sleeps[0] == pytest.approx(window)


def test_helper_none_input():
    assert contention_retry_after(None) == 0.0


def test_helper_plain_runtime_error():
    assert contention_retry_after(RuntimeError('not contention')) == 0.0


def test_helper_key_error():
    assert contention_retry_after(KeyError('k')) == 0.0


def test_helper_exhaustion_default_zero():
    assert contention_retry_after(FirestoreContentionExhausted('no damper')) == 0.0


def test_helper_exhaustion_explicit_zero():
    assert contention_retry_after(FirestoreContentionExhausted('x', retry_after=0.0)) == 0.0


def test_helper_exhaustion_negative():
    assert contention_retry_after(FirestoreContentionExhausted('x', retry_after=-0.5)) == 0.0


def test_helper_exhaustion_nan():
    assert contention_retry_after(FirestoreContentionExhausted('x', retry_after=float('nan'))) == 0.0


def test_helper_exhaustion_inf():
    assert contention_retry_after(FirestoreContentionExhausted('x', retry_after=float('inf'))) == 0.0


def test_helper_exhaustion_neg_inf():
    assert contention_retry_after(FirestoreContentionExhausted('x', retry_after=float('-inf'))) == 0.0


def test_helper_exhaustion_epsilon():
    assert contention_retry_after(FirestoreContentionExhausted('x', retry_after=0.001)) == 0.001


def test_helper_exhaustion_first_rung():
    assert contention_retry_after(FirestoreContentionExhausted('x', retry_after=0.25)) == 0.25


def test_helper_exhaustion_wave():
    assert contention_retry_after(FirestoreContentionExhausted('x', retry_after=3.5)) == 3.5


def test_helper_exhaustion_int_window():
    assert contention_retry_after(FirestoreContentionExhausted('x', retry_after=2)) == 2.0


def test_helper_exhaustion_just_under_max():
    assert contention_retry_after(FirestoreContentionExhausted('x', retry_after=7.999)) == 7.999


def test_helper_exhaustion_at_max():
    assert contention_retry_after(FirestoreContentionExhausted('x', retry_after=8.0)) == 8.0


def test_helper_exhaustion_over_max():
    assert contention_retry_after(FirestoreContentionExhausted('x', retry_after=8.001)) == 8.0


def test_helper_exhaustion_huge():
    assert contention_retry_after(FirestoreContentionExhausted('x', retry_after=10000.0)) == 8.0


def test_helper_bool_true_rejected():
    assert contention_retry_after(types.SimpleNamespace(retry_after=True)) == 0.0


def test_helper_bool_false_rejected():
    assert contention_retry_after(types.SimpleNamespace(retry_after=False)) == 0.0


def test_helper_string_window_rejected():
    assert contention_retry_after(types.SimpleNamespace(retry_after='3.5')) == 0.0


def test_helper_bytes_window_rejected():
    assert contention_retry_after(types.SimpleNamespace(retry_after=b'3.5')) == 0.0


def test_helper_list_window_rejected():
    assert contention_retry_after(types.SimpleNamespace(retry_after=[3.5])) == 0.0


def test_helper_dict_window_rejected():
    assert contention_retry_after(types.SimpleNamespace(retry_after={3.5: 1})) == 0.0


def test_helper_set_window_rejected():
    assert contention_retry_after(types.SimpleNamespace(retry_after={3.5})) == 0.0


def test_helper_tuple_window_rejected():
    assert contention_retry_after(types.SimpleNamespace(retry_after=(3.5,))) == 0.0


def test_helper_none_window_rejected():
    assert contention_retry_after(types.SimpleNamespace(retry_after=None)) == 0.0


def test_helper_numeric_string_rejected():
    assert contention_retry_after(types.SimpleNamespace(retry_after='2.0')) == 0.0


def test_helper_inf_string_rejected():
    assert contention_retry_after(types.SimpleNamespace(retry_after='inf')) == 0.0


def test_helper_nan_string_rejected():
    assert contention_retry_after(types.SimpleNamespace(retry_after='nan')) == 0.0


def test_helper_missing_attribute_object():
    assert contention_retry_after(types.SimpleNamespace()) == 0.0


def test_helper_zero_int():
    assert contention_retry_after(types.SimpleNamespace(retry_after=0)) == 0.0


def test_helper_negative_int():
    assert contention_retry_after(types.SimpleNamespace(retry_after=-2)) == 0.0


def test_helper_float_min_subnormal():
    assert contention_retry_after(types.SimpleNamespace(retry_after=5e-324)) == 5e-324


def test_helper_int_one():
    assert contention_retry_after(types.SimpleNamespace(retry_after=1)) == 1.0


def test_helper_int_max_plus():
    assert contention_retry_after(types.SimpleNamespace(retry_after=9)) == 8.0


def test_exception_contract_attempts_exhausted_default():
    error = FirestoreContentionExhausted('m', reason='attempts_exhausted')
    assert error.reason == 'attempts_exhausted'
    assert error.retry_after == pytest.approx(0.0)
    assert isinstance(error.retry_after, float)


def test_exception_contract_attempts_exhausted_0():
    error = FirestoreContentionExhausted('m', reason='attempts_exhausted', retry_after=0)
    assert error.reason == 'attempts_exhausted'
    assert error.retry_after == pytest.approx(0.0)
    assert isinstance(error.retry_after, float)


def test_exception_contract_attempts_exhausted_2_5():
    error = FirestoreContentionExhausted('m', reason='attempts_exhausted', retry_after=2.5)
    assert error.reason == 'attempts_exhausted'
    assert error.retry_after == pytest.approx(2.5)
    assert isinstance(error.retry_after, float)


def test_exception_contract_attempts_exhausted_3():
    error = FirestoreContentionExhausted('m', reason='attempts_exhausted', retry_after=3)
    assert error.reason == 'attempts_exhausted'
    assert error.retry_after == pytest.approx(3.0)
    assert isinstance(error.retry_after, float)


def test_exception_contract_attempts_exhausted_0_001():
    error = FirestoreContentionExhausted('m', reason='attempts_exhausted', retry_after=0.001)
    assert error.reason == 'attempts_exhausted'
    assert error.retry_after == pytest.approx(0.001)
    assert isinstance(error.retry_after, float)


def test_exception_contract_attempts_exhausted_0_25():
    error = FirestoreContentionExhausted('m', reason='attempts_exhausted', retry_after=0.25)
    assert error.reason == 'attempts_exhausted'
    assert error.retry_after == pytest.approx(0.25)
    assert isinstance(error.retry_after, float)


def test_exception_contract_attempts_exhausted_4_0():
    error = FirestoreContentionExhausted('m', reason='attempts_exhausted', retry_after=4.0)
    assert error.reason == 'attempts_exhausted'
    assert error.retry_after == pytest.approx(4.0)
    assert isinstance(error.retry_after, float)


def test_exception_contract_attempts_exhausted_17_25():
    error = FirestoreContentionExhausted('m', reason='attempts_exhausted', retry_after=17.25)
    assert error.reason == 'attempts_exhausted'
    assert error.retry_after == pytest.approx(17.25)
    assert isinstance(error.retry_after, float)


def test_exception_contract_attempts_exhausted_neg1_5():
    error = FirestoreContentionExhausted('m', reason='attempts_exhausted', retry_after=-1.5)
    assert error.reason == 'attempts_exhausted'
    assert error.retry_after == pytest.approx(-1.5)
    assert isinstance(error.retry_after, float)


def test_exception_contract_deadline_exhausted_default():
    error = FirestoreContentionExhausted('m', reason='deadline_exhausted')
    assert error.reason == 'deadline_exhausted'
    assert error.retry_after == pytest.approx(0.0)
    assert isinstance(error.retry_after, float)


def test_exception_contract_deadline_exhausted_0():
    error = FirestoreContentionExhausted('m', reason='deadline_exhausted', retry_after=0)
    assert error.reason == 'deadline_exhausted'
    assert error.retry_after == pytest.approx(0.0)
    assert isinstance(error.retry_after, float)


def test_exception_contract_deadline_exhausted_2_5():
    error = FirestoreContentionExhausted('m', reason='deadline_exhausted', retry_after=2.5)
    assert error.reason == 'deadline_exhausted'
    assert error.retry_after == pytest.approx(2.5)
    assert isinstance(error.retry_after, float)


def test_exception_contract_deadline_exhausted_3():
    error = FirestoreContentionExhausted('m', reason='deadline_exhausted', retry_after=3)
    assert error.reason == 'deadline_exhausted'
    assert error.retry_after == pytest.approx(3.0)
    assert isinstance(error.retry_after, float)


def test_exception_contract_deadline_exhausted_0_001():
    error = FirestoreContentionExhausted('m', reason='deadline_exhausted', retry_after=0.001)
    assert error.reason == 'deadline_exhausted'
    assert error.retry_after == pytest.approx(0.001)
    assert isinstance(error.retry_after, float)


def test_exception_contract_deadline_exhausted_0_25():
    error = FirestoreContentionExhausted('m', reason='deadline_exhausted', retry_after=0.25)
    assert error.reason == 'deadline_exhausted'
    assert error.retry_after == pytest.approx(0.25)
    assert isinstance(error.retry_after, float)


def test_exception_contract_deadline_exhausted_4_0():
    error = FirestoreContentionExhausted('m', reason='deadline_exhausted', retry_after=4.0)
    assert error.reason == 'deadline_exhausted'
    assert error.retry_after == pytest.approx(4.0)
    assert isinstance(error.retry_after, float)


def test_exception_contract_deadline_exhausted_17_25():
    error = FirestoreContentionExhausted('m', reason='deadline_exhausted', retry_after=17.25)
    assert error.reason == 'deadline_exhausted'
    assert error.retry_after == pytest.approx(17.25)
    assert isinstance(error.retry_after, float)


def test_exception_contract_deadline_exhausted_neg1_5():
    error = FirestoreContentionExhausted('m', reason='deadline_exhausted', retry_after=-1.5)
    assert error.reason == 'deadline_exhausted'
    assert error.retry_after == pytest.approx(-1.5)
    assert isinstance(error.retry_after, float)
