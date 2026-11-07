"""Twin, simulator and protocol surfaces stay independent of the wave-bridged chain.

The wave-bridge lives entirely inside ``database/firestore_transaction_retry``.
The Postgres twin retries serialization with its own jittered sleeps, the
pipeline simulator runs transactions without a contention budget, and the
store Protocol's advisory-probe surface (``service_frontier_hint``) is
unchanged. The inner ``run_transactional`` chain shares only the
``equal_jitter_delay`` helper: its default three-attempt and nested
``attempts=1`` shapes keep the unchanged early rungs, its ``transient``
opt-in reaches the grown tail rungs, and its restart logging is a closed
taxonomy. This suite pins those independence and sharing boundaries so the
wave bridge cannot silently leak into stores that never consulted it.

Failure-Class: FC-contention-chain-spends-its-budget-inside-one-abort-wave
"""

import ast
import logging
import re
from pathlib import Path
from types import SimpleNamespace

import pytest
from google.api_core.exceptions import Aborted, DeadlineExceeded, InvalidArgument, ResourceExhausted, ServiceUnavailable

import database.firestore_transaction_retry as retry_module
from database._client import run_transactional
from database.batch_pipeline_store import Store, Transaction
from database.firestore_transaction_retry import FirestoreContentionExhausted

BACKEND = Path(__file__).resolve().parents[2]
RETRY_SOURCE = (BACKEND / 'database' / 'firestore_transaction_retry.py').read_text()

EXPIRED = 'The referenced transaction has expired or is no longer valid.'


class FakeClock:
    def __init__(self, now: float = 1000.0):
        self.now = now

    def sleep(self, seconds):
        self.now += seconds


class FakeTransaction:
    def __init__(self, marker):
        self.marker = marker


class FakeClient:
    def __init__(self):
        self.minted = []

    def transaction(self, *args, **kwargs):
        transaction = FakeTransaction(len(self.minted))
        self.minted.append(transaction)
        return transaction


# --------------------------------------------------------------------------
# Source-level independence: the chain imports no store, no twin, no sim
# --------------------------------------------------------------------------


def test_the_retry_module_imports_no_store_module():
    tree = ast.parse(RETRY_SOURCE)
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    assert not any(
        name.startswith(('database.batch_pipeline', 'database.jobstore', 'testing.pipeline_sim')) for name in imported
    )


def test_the_store_module_owns_the_damper_not_the_chain():
    store_source = (BACKEND / 'database' / 'batch_pipeline_store.py').read_text()
    assert '_ContentionStormDamper' in store_source
    assert '_ContentionStormDamper' not in RETRY_SOURCE


def test_the_retry_module_exposes_no_store_protocol():
    assert not hasattr(retry_module, 'Store')
    assert not hasattr(retry_module, 'Transaction')


# --------------------------------------------------------------------------
# The store Protocol's advisory-probe surface is unchanged
# --------------------------------------------------------------------------


def test_store_protocol_keeps_the_advisory_frontier_hint():
    assert hasattr(Store, 'service_frontier_hint')


def test_transaction_protocol_has_no_transactional_frontier_read():
    assert not hasattr(Transaction, 'service_frontier')


def test_transaction_protocol_surface_is_the_lease_fenced_minimum():
    for method in ('get', 'put', 'patch', 'first_pending', 'first_ready_pending', 'check_privacy'):
        assert hasattr(Transaction, method), method


def test_firestore_transaction_retry_module_is_not_a_store_import_source():
    # The wave-bridge module is imported BY the store, never the reverse.
    store_source = (BACKEND / 'database' / 'batch_pipeline_store.py').read_text()
    assert 'from database.firestore_transaction_retry import' in store_source
    assert 'import database.batch_pipeline_store' not in RETRY_SOURCE


# --------------------------------------------------------------------------
# The inner chain keeps the unchanged early rungs and reaches the grown tail
# --------------------------------------------------------------------------


def transient_body(errors):
    attempts = {'n': 0}

    def body(transaction, *args, **kwargs):
        attempts['n'] += 1
        if attempts['n'] <= len(errors):
            raise errors[attempts['n'] - 1]
        return 'committed'

    return body, attempts


def test_transient_chain_recovers_on_the_second_attempt_with_the_first_rung():
    clock = FakeClock()
    body, attempts = transient_body([Aborted('a')])
    assert run_transactional(FakeClient(), body, transient=True, sleep=clock.sleep, random_value=lambda: 1.0)
    assert attempts['n'] == 2
    assert clock.now - 1000.0 == pytest.approx(0.2)


def test_transient_chain_recovers_on_the_third_attempt_with_two_rungs():
    clock = FakeClock()
    body, attempts = transient_body([Aborted('a'), DeadlineExceeded('d')])
    assert run_transactional(FakeClient(), body, transient=True, sleep=clock.sleep, random_value=lambda: 1.0)
    assert attempts['n'] == 3
    assert clock.now - 1000.0 == pytest.approx(0.6)


def test_transient_chain_of_five_attempts_carries_the_grown_fourth_rung():
    clock = FakeClock()
    body, attempts = transient_body(
        [Aborted('a'), DeadlineExceeded('d'), ServiceUnavailable('s'), ResourceExhausted('r')]
    )
    assert run_transactional(
        FakeClient(), body, transient=True, attempts=5, sleep=clock.sleep, random_value=lambda: 1.0
    )
    assert attempts['n'] == 5
    assert clock.now - 1000.0 == pytest.approx(3.0)


def test_transient_exhaustion_chain_sums_the_unchanged_early_rungs_at_depth_three():
    clock = FakeClock()

    def body(transaction, *args, **kwargs):
        raise Aborted('contention')

    with pytest.raises(Aborted):
        run_transactional(FakeClient(), body, transient=True, attempts=3, sleep=clock.sleep, random_value=lambda: 1.0)
    assert clock.now - 1000.0 == pytest.approx(0.6)


def test_expired_id_chain_sums_the_unchanged_early_rungs_at_depth_three():
    clock = FakeClock()

    def body(transaction, *args, **kwargs):
        raise InvalidArgument(EXPIRED)

    with pytest.raises(InvalidArgument):
        run_transactional(FakeClient(), body, sleep=clock.sleep, random_value=lambda: 1.0)
    assert clock.now - 1000.0 == pytest.approx(0.6)


def test_inner_restart_logging_names_the_attempt_and_reason(caplog):
    clock = FakeClock()

    def body(transaction, *args, **kwargs):
        raise Aborted('contention')

    with caplog.at_level(logging.WARNING, logger='database._client'):
        with pytest.raises(Aborted):
            run_transactional(
                FakeClient(), body, transient=True, attempts=2, sleep=clock.sleep, random_value=lambda: 1.0
            )
    restarts = [record.getMessage() for record in caplog.records if 'restart' in record.getMessage()]
    assert len(restarts) == 1
    assert 'attempt=1/2' in restarts[0]
    assert 'reason=' in restarts[0]


def test_expired_restart_logging_names_the_attempt(caplog):
    clock = FakeClock()

    def body(transaction, *args, **kwargs):
        raise InvalidArgument(EXPIRED)

    with caplog.at_level(logging.WARNING, logger='database._client'):
        with pytest.raises(InvalidArgument):
            run_transactional(FakeClient(), body, attempts=2, sleep=clock.sleep, random_value=lambda: 1.0)
    restarts = [record.getMessage() for record in caplog.records if 'expired' in record.getMessage()]
    assert len(restarts) == 1
    assert 'attempt=1/2' in restarts[0]


def test_the_inner_chain_never_replays_a_retried_transaction_id():
    client = FakeClient()

    def body(transaction, *args, **kwargs):
        raise InvalidArgument(EXPIRED)

    with pytest.raises(InvalidArgument):
        run_transactional(client, body, attempts=3, sleep=lambda s: None)
    assert len({transaction.marker for transaction in client.minted}) == 3


# --------------------------------------------------------------------------
# The outer chain's marker contract stays closed
# --------------------------------------------------------------------------


def test_expired_marker_matches_the_documented_message():
    assert retry_module._EXPIRED_TRANSACTION_MARKER == 'transaction has expired'
    assert EXPIRED.lower().startswith('the referenced transaction has expired')


def test_contention_classification_accepts_aborted_and_expired_only():
    assert retry_module.is_transaction_contention(Aborted('x'))
    assert retry_module.is_transaction_contention(InvalidArgument(EXPIRED))
    assert not retry_module.is_transaction_contention(ValueError('nope'))
    assert not retry_module.is_transaction_contention(InvalidArgument('400 other reason'))


def test_cause_chains_are_walked_for_classification():
    try:
        try:
            raise Aborted('inner')
        except Aborted as inner:
            raise RuntimeError('outer') from inner
    except RuntimeError as wrapped:
        assert retry_module.is_transaction_contention(wrapped)


def test_exhaustion_reason_tokens_are_the_closed_set():
    assert FirestoreContentionExhausted('x').reason == 'attempts_exhausted'
    assert FirestoreContentionExhausted('x', reason='deadline_exhausted').reason == 'deadline_exhausted'


def test_the_chain_constant_is_the_documented_270_seconds():
    assert retry_module.FIRESTORE_TRANSACTION_CHAIN_SECONDS == 270.0


def test_the_reserve_constants_are_unchanged():
    assert retry_module.RETRY_RESERVE_FACTOR == 1.5
    assert retry_module.RETRY_RESERVE_FLOOR_SECONDS == 30.0


def test_the_expired_chain_ceiling_is_unchanged():
    assert retry_module._EXPIRED_CHAIN_CEILING_WITHOUT_DEADLINE == 3
