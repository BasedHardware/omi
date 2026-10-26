"""Deadline-aware bounds for the outer Firestore contention retry budget.

A fake clock drives worst-case schedules: every attempt charges Firestore's
documented 270 s chain lifetime, so the wall-time assertions prove the bound
without waiting. Callers model the real seams — the sync handler's request
budget (1,380 s default minus a 120 s safety margin), batch projection's
300 s claim minus its margin, and callers that pass no deadline at all.
"""

import logging

import pytest
from google.api_core.exceptions import Aborted, InvalidArgument

import database.firestore_transaction_retry as firestore_transaction_retry
from database.firestore_transaction_retry import (
    FIRESTORE_TRANSACTION_CHAIN_SECONDS,
    FirestoreContentionExhausted,
    run_with_transaction_contention_retry,
    transaction_retry_deadline_scope,
)

EXPIRED = 'The referenced transaction has expired or is no longer valid.'

# The sync handler's derived retry budget: request budget 1,380 s minus the
# 120 s post-transaction safety margin (routers/sync.py), and the batch
# projection claim's 300 s lease minus its 30 s margin
# (database/batch_pipeline_projection_claim.py).
SYNC_HANDLER_RETRY_BUDGET_SECONDS = 1380.0 - 120.0
PROJECTION_CLAIM_RETRY_BUDGET_SECONDS = 300.0 - 30.0


class FakeClock:
    """Monotonic clock the operation and the retry loop share; sleeps advance it."""

    def __init__(self, now: float = 1000.0):
        self.now = now

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


def expired() -> InvalidArgument:
    return InvalidArgument(EXPIRED)


@pytest.mark.parametrize(
    'budget_seconds,expected_attempts,expected_reason',
    [
        pytest.param(None, 5, 'attempts_exhausted', id='no-deadline-caller-keeps-attempt-bound'),
        pytest.param(SYNC_HANDLER_RETRY_BUDGET_SECONDS, 4, 'deadline_exhausted', id='sync-handler-budget'),
        pytest.param(PROJECTION_CLAIM_RETRY_BUDGET_SECONDS, 1, 'deadline_exhausted', id='projection-claim-budget'),
    ],
)
def test_worst_case_wall_time_stays_within_each_callers_budget(budget_seconds, expected_attempts, expected_reason):
    clock = FakeClock()
    calls = []

    def operation(transaction):
        calls.append(transaction)
        clock.now += FIRESTORE_TRANSACTION_CHAIN_SECONDS - 1.0  # just inside one chain lifetime
        raise expired()

    start = clock.monotonic()
    deadline = None if budget_seconds is None else start + budget_seconds
    with pytest.raises(FirestoreContentionExhausted) as raised:
        run_with_transaction_contention_retry(
            lambda: object(),
            operation,
            operation_name='bounded',
            deadline=deadline,
            sleep=clock.sleep,
            random_value=lambda: 0,
            monotonic=clock.monotonic,
        )

    assert raised.value.reason == expected_reason
    assert len(calls) == expected_attempts
    wall = clock.monotonic() - start
    if budget_seconds is not None:
        assert wall <= budget_seconds


def test_observed_attempt_duration_tightens_the_estimate_beyond_the_chain_cap():
    # An attempt that outlived the 270 s estimate (slow transport before the
    # chain began) must gate the next attempt on its observed duration.
    clock = FakeClock()

    def operation(transaction):
        clock.now += 300.0
        raise expired()

    start = clock.monotonic()
    with pytest.raises(FirestoreContentionExhausted) as raised:
        run_with_transaction_contention_retry(
            lambda: object(),
            operation,
            operation_name='observed',
            deadline=start + 1000.0,
            sleep=clock.sleep,
            random_value=lambda: 0,
            monotonic=clock.monotonic,
        )

    assert raised.value.reason == 'deadline_exhausted'
    assert clock.monotonic() - start <= 1000.0
    # 3 observed-300s attempts fit; the fourth gate sees 99.3s remaining.
    assert clock.monotonic() - start == pytest.approx(900.7, abs=0.001)


def test_budget_below_one_chain_refuses_before_the_first_attempt(caplog):
    clock = FakeClock()
    calls = []

    def operation(transaction):
        calls.append(transaction)
        raise expired()

    with caplog.at_level('ERROR', logger='database.firestore_transaction_retry'):
        with pytest.raises(FirestoreContentionExhausted) as raised:
            run_with_transaction_contention_retry(
                lambda: object(),
                operation,
                operation_name='entry_gated',
                deadline=clock.monotonic() + FIRESTORE_TRANSACTION_CHAIN_SECONDS - 1.0,
                sleep=clock.sleep,
                random_value=lambda: 0,
                monotonic=clock.monotonic,
            )

    assert raised.value.reason == 'deadline_exhausted'
    assert calls == []
    assert raised.value.__cause__ is None
    [line] = [record.getMessage() for record in caplog.records if 'deadline_exhausted' in record.getMessage()]
    assert 'operation=entry_gated attempt=1/5 outcome=deadline_exhausted' in line
    assert 'remaining_ms=' in line and 'estimate_ms=' in line
    assert EXPIRED not in line


def test_expiry_recovery_within_budget_when_time_allows():
    clock = FakeClock()
    errors = [expired(), Aborted('read contention')]

    def operation(transaction):
        clock.now += 5.0
        if errors:
            raise errors.pop(0)
        return 'persisted'

    start = clock.monotonic()
    with transaction_retry_deadline_scope(start + SYNC_HANDLER_RETRY_BUDGET_SECONDS):
        result = run_with_transaction_contention_retry(
            lambda: object(),
            operation,
            operation_name='recovers',
            sleep=clock.sleep,
            random_value=lambda: 0,
            monotonic=clock.monotonic,
        )

    assert result == 'persisted'
    assert clock.monotonic() - start <= SYNC_HANDLER_RETRY_BUDGET_SECONDS


def test_ambient_deadline_scope_inherits_overrides_and_resets():
    clock = FakeClock()
    scoped = clock.monotonic() + 100.0
    with transaction_retry_deadline_scope(scoped):
        assert firestore_transaction_retry._retry_deadline.get() == scoped
        with transaction_retry_deadline_scope(None):
            assert firestore_transaction_retry._retry_deadline.get() is None
        assert firestore_transaction_retry._retry_deadline.get() == scoped
        # The scoped (not parameter) deadline governs when None is passed.
        calls = []
        with pytest.raises(FirestoreContentionExhausted) as raised:
            run_with_transaction_contention_retry(
                lambda: object(),
                lambda transaction: calls.append(transaction) or expired(),
                operation_name='ambient',
                sleep=clock.sleep,
                random_value=lambda: 0,
                monotonic=clock.monotonic,
            )
        assert raised.value.reason == 'deadline_exhausted'
        assert calls == []  # start + 100s cannot cover a 270s chain
    assert firestore_transaction_retry._retry_deadline.get() is None


def _chained_from_expired() -> ValueError:
    try:
        raise expired()
    except InvalidArgument as inner:
        try:
            raise ValueError('failed to commit transaction after 5 attempts') from inner
        except ValueError as wrapper:
            return wrapper


def _chained_from_plain() -> ValueError:
    try:
        raise InvalidArgument('bad payload')
    except InvalidArgument as inner:
        try:
            raise ValueError('app wrapper') from inner
        except ValueError as wrapper:
            return wrapper


@pytest.mark.parametrize(
    'error',
    [
        pytest.param(expired(), id='expired-commit'),
        pytest.param(Aborted('streaming read: the referenced transaction has expired'), id='expired-read'),
        pytest.param(_chained_from_expired(), id='sdk-wrapper-cause-chain'),
    ],
)
def test_expired_chain_errors_count_as_contention(error):
    assert firestore_transaction_retry._is_transaction_contention(error)


@pytest.mark.parametrize(
    'error',
    [
        pytest.param(InvalidArgument('not an expiry marker'), id='plain-invalid-argument'),
        pytest.param(_chained_from_plain(), id='plain-cause-chain'),
    ],
)
def test_non_contention_errors_stay_unclassified(error):
    assert not firestore_transaction_retry._is_transaction_contention(error)


def test_existing_outcome_tokens_are_unchanged(caplog):
    clock = FakeClock()
    caplog.set_level(logging.DEBUG, logger='database.firestore_transaction_retry')
    errors = [expired()]

    def operation(transaction):
        clock.now += 1.0
        if errors:
            raise errors.pop(0)
        return 'persisted'

    run_with_transaction_contention_retry(
        lambda: object(),
        operation,
        operation_name='tokens',
        sleep=clock.sleep,
        random_value=lambda: 0,
        monotonic=clock.monotonic,
    )
    messages = [record.getMessage() for record in caplog.records]
    assert any('outcome=retry delay_ms=' in message for message in messages)
    assert any('outcome=recovered' in message for message in messages)
