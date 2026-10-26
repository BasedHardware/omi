"""Deadline-aware bounds for the outer Firestore contention retry budget.

A fake clock drives worst-case schedules: every attempt charges Firestore's
documented 270 s chain lifetime at maximum jitter, so the wall-time assertions
prove the accepted bound — total ≤ deadline + one in-flight attempt, because
the loop never refuses attempt 1 and cannot stop an attempt already running —
without waiting. Callers model the real seams: the sync handler's request
budget (1,380 s default minus a 120 s safety margin), batch projection's full
300 s claim lease, and callers that pass no deadline at all.
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
# projection claim's full 300 s lease (database/batch_pipeline_projection_claim.py).
SYNC_HANDLER_RETRY_BUDGET_SECONDS = 1380.0 - 120.0
PROJECTION_CLAIM_RETRY_BUDGET_SECONDS = 300.0


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


def aborted() -> Aborted:
    return Aborted('read contention')


@pytest.mark.parametrize(
    'budget_seconds,error_factory,expected_attempts,expected_reason',
    [
        pytest.param(None, aborted, 5, 'attempts_exhausted', id='no-deadline-caller-keeps-attempt-bound'),
        pytest.param(SYNC_HANDLER_RETRY_BUDGET_SECONDS, expired, 4, 'deadline_exhausted', id='sync-handler-budget'),
        pytest.param(
            PROJECTION_CLAIM_RETRY_BUDGET_SECONDS, expired, 1, 'deadline_exhausted', id='projection-claim-budget'
        ),
        pytest.param(0.0, expired, 1, 'deadline_exhausted', id='zero-remaining-budget'),
    ],
)
def test_worst_case_wall_time_stays_within_deadline_plus_one_attempt(
    budget_seconds, error_factory, expected_attempts, expected_reason
):
    clock = FakeClock()
    calls = []

    def operation(transaction):
        calls.append(transaction)
        clock.now += FIRESTORE_TRANSACTION_CHAIN_SECONDS  # a full chain lifetime
        raise error_factory()

    start = clock.monotonic()
    deadline = None if budget_seconds is None else start + budget_seconds
    with pytest.raises(FirestoreContentionExhausted) as raised:
        run_with_transaction_contention_retry(
            lambda: object(),
            operation,
            operation_name='bounded',
            deadline=deadline,
            sleep=clock.sleep,
            random_value=lambda: 1,  # maximum jitter
            monotonic=clock.monotonic,
        )

    assert raised.value.reason == expected_reason
    assert len(calls) == expected_attempts
    if budget_seconds is not None:
        # The accepted bound: attempt 1 always runs and an in-flight attempt
        # cannot be stopped, so the deadline alone never bounds the total.
        assert clock.monotonic() - start <= budget_seconds + FIRESTORE_TRANSACTION_CHAIN_SECONDS


def test_observed_attempt_duration_raises_the_reserve_beyond_the_floor():
    # A retry needs the remaining budget to cover the last attempt's observed
    # duration x 1.5, not just the 30 s floor: two observed-300s attempts fit
    # the 1,000 s budget and the third gate (reserve 450 s) stops the loop.
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
            random_value=lambda: 1,
            monotonic=clock.monotonic,
        )

    assert raised.value.reason == 'deadline_exhausted'
    assert clock.monotonic() - start <= 1000.0
    # 2 x 300s attempts + maximum jitter (0.2s + 0.4s); the third gate sees
    # 399.4 s remaining against a 450 s reserve.
    assert clock.monotonic() - start == pytest.approx(600.6, abs=0.001)


def test_first_attempt_never_refused_even_past_the_deadline(caplog):
    clock = FakeClock()
    calls = []

    def operation(transaction):
        calls.append(transaction)
        clock.now += 5.0
        raise expired()

    with caplog.at_level('ERROR', logger='database.firestore_transaction_retry'):
        with pytest.raises(FirestoreContentionExhausted) as raised:
            run_with_transaction_contention_retry(
                lambda: object(),
                operation,
                operation_name='never_refused',
                deadline=clock.monotonic() - 10.0,  # already exhausted
                sleep=clock.sleep,
                random_value=lambda: 1,
                monotonic=clock.monotonic,
            )

    assert raised.value.reason == 'deadline_exhausted'
    assert isinstance(raised.value.__cause__, InvalidArgument)
    assert len(calls) == 1  # a caller that reached the transaction always gets one try
    [line] = [record.getMessage() for record in caplog.records if 'deadline_exhausted' in record.getMessage()]
    assert 'operation=never_refused attempt=1/5 outcome=deadline_exhausted' in line
    assert 'delay_ms=' in line
    assert EXPIRED not in line


def test_jitter_sleep_never_runs_past_the_deadline():
    # After a full 270 s attempt only 0.05 s of the budget remains — less than
    # the 0.2 s maximum jitter — so the loop stops instead of sleeping past
    # the deadline.
    clock = FakeClock()
    calls = []

    def operation(transaction):
        calls.append(transaction)
        clock.now += FIRESTORE_TRANSACTION_CHAIN_SECONDS
        raise expired()

    start = clock.monotonic()
    with pytest.raises(FirestoreContentionExhausted) as raised:
        run_with_transaction_contention_retry(
            lambda: object(),
            operation,
            operation_name='clamped',
            deadline=start + FIRESTORE_TRANSACTION_CHAIN_SECONDS + 0.05,
            sleep=clock.sleep,
            random_value=lambda: 1,
            monotonic=clock.monotonic,
        )

    assert raised.value.reason == 'deadline_exhausted'
    assert len(calls) == 1
    # The jitter was never charged: the wall is exactly the 270 s attempt, not
    # the 270.2 s an unclamped maximum delay would have reached.
    assert clock.monotonic() - start == pytest.approx(FIRESTORE_TRANSACTION_CHAIN_SECONDS, abs=0.001)
    assert clock.monotonic() - start <= FIRESTORE_TRANSACTION_CHAIN_SECONDS + 0.05


def test_no_deadline_keeps_todays_three_expired_chain_ceiling():
    clock = FakeClock()

    def storm(error_factory):
        calls = []

        def operation(transaction):
            calls.append(transaction)
            clock.now += 0.01
            raise error_factory()

        return calls, operation

    def run(operation):
        with pytest.raises(FirestoreContentionExhausted) as raised:
            run_with_transaction_contention_retry(
                lambda: object(),
                operation,
                operation_name='ceiling',
                sleep=clock.sleep,
                random_value=lambda: 0,
                monotonic=clock.monotonic,
            )
        return raised.value.reason

    # Expired-id storm without a deadline: today's run_transactional ceiling
    # of three fresh chains, not the five-chain Aborted policy.
    calls, operation = storm(expired)
    assert run(operation) == 'attempts_exhausted'
    assert len(calls) == 3

    # Aborted contention keeps the full attempt cap without a deadline.
    calls, operation = storm(aborted)
    assert run(operation) == 'attempts_exhausted'
    assert len(calls) == 5

    # A deadline in scope moves expiry onto the deadline-bounded attempt policy.
    calls, operation = storm(expired)
    start = clock.monotonic()
    with transaction_retry_deadline_scope(start + 10_000.0):
        assert run(operation) == 'attempts_exhausted'
    assert len(calls) == 5


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
        # The scoped (not parameter) deadline governs when None is passed: one
        # 45 s attempt leaves 54.9 s against the 67.5 s reserve a retry needs.
        calls = []

        def operation(transaction):
            calls.append(transaction)
            clock.now += 45.0
            raise expired()

        with pytest.raises(FirestoreContentionExhausted) as raised:
            run_with_transaction_contention_retry(
                lambda: object(),
                operation,
                operation_name='ambient',
                sleep=clock.sleep,
                random_value=lambda: 0,
                monotonic=clock.monotonic,
            )
        assert raised.value.reason == 'deadline_exhausted'
        assert len(calls) == 1  # attempt 1 always ran; the reserve stopped the retry
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
