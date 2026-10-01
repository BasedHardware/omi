from datetime import datetime, timezone
import pytest

from utils.durable_queue_policy import (
    AttemptDecision,
    EnqueueDecision,
    OutcomeKind,
    ProcessOutcome,
    QueuePolicy,
    adopt_on_identity,
    backoff_seconds,
    decide_attempt,
    _bound_error,
)


def test_bound_error_truncation():
    short_err = 'Database timeout'
    assert _bound_error(short_err) == short_err

    long_err = 'E' * 3000
    bounded = _bound_error(long_err)
    assert len(bounded) == 2000


def test_process_outcome_factory_methods():
    ack = ProcessOutcome.ack()
    assert ack.kind == OutcomeKind.ACK
    assert ack.error_text is None
    assert ack.reason is None

    retry = ProcessOutcome.retry('Transient 503', reason='network_flake')
    assert retry.kind == OutcomeKind.RETRY
    assert retry.error_text == 'Transient 503'
    assert retry.reason == 'network_flake'

    reject = ProcessOutcome.reject('Invalid schema payload', reason='bad_request')
    assert reject.kind == OutcomeKind.REJECT
    assert reject.error_text == 'Invalid schema payload'
    assert reject.reason == 'bad_request'


def test_backoff_seconds_exponential_and_cap():
    policy = QueuePolicy(max_attempts=5, base_backoff_seconds=2.0, max_backoff_seconds=50.0)
    # exponent = min(max(attempt_count - 1, 0), 30)
    assert backoff_seconds(policy, 1) == 2.0  # 2.0 * (2**0)
    assert backoff_seconds(policy, 2) == 4.0  # 2.0 * (2**1)
    assert backoff_seconds(policy, 3) == 8.0  # 2.0 * (2**2)
    assert backoff_seconds(policy, 4) == 16.0 # 2.0 * (2**3)
    assert backoff_seconds(policy, 5) == 32.0 # 2.0 * (2**4)
    assert backoff_seconds(policy, 6) == 50.0 # capped at max_backoff_seconds
    assert backoff_seconds(policy, 100) == 50.0 # capped safely


def test_decide_attempt_ack_raises_value_error():
    policy = QueuePolicy(max_attempts=3)
    now = datetime(2026, 10, 1, 12, 0, 0, tzinfo=timezone.utc)
    with pytest.raises(ValueError, match='ack is not an attempt failure'):
        decide_attempt(attempt_count=1, outcome=ProcessOutcome.ack(), policy=policy, now=now)


def test_decide_attempt_retry_within_budget():
    policy = QueuePolicy(max_attempts=3, base_backoff_seconds=5.0)
    now = datetime(2026, 10, 1, 12, 0, 0, tzinfo=timezone.utc)
    outcome = ProcessOutcome.retry('rate limited', reason='429')
    decision = decide_attempt(attempt_count=1, outcome=outcome, policy=policy, now=now)
    assert decision.terminal is False
    assert decision.status == 'retrying'
    assert decision.attempt_count == 1
    assert decision.available_at is not None
    assert decision.available_at > now


def test_decide_attempt_retry_exceeds_budget_dead_letters():
    policy = QueuePolicy(max_attempts=3)
    now = datetime(2026, 10, 1, 12, 0, 0, tzinfo=timezone.utc)
    outcome = ProcessOutcome.retry('permanent fail', reason='exhausted')
    decision = decide_attempt(attempt_count=3, outcome=outcome, policy=policy, now=now)
    assert decision.terminal is True
    assert decision.status == 'dead_letter'
    assert decision.available_at is None


def test_decide_attempt_reject_immediately_dead_letters():
    policy = QueuePolicy(max_attempts=5)
    now = datetime(2026, 10, 1, 12, 0, 0, tzinfo=timezone.utc)
    outcome = ProcessOutcome.reject('malformed payload', reason='unrecoverable')
    decision = decide_attempt(attempt_count=1, outcome=outcome, policy=policy, now=now)
    assert decision.terminal is True
    assert decision.status == 'dead_letter'


def test_adopt_on_identity():
    # existing_id == item_id -> adopted
    assert adopt_on_identity(existing_id='item_1', item_id='item_1').adopted is True
    # existing_id != item_id -> not adopted
    assert adopt_on_identity(existing_id=None, item_id='item_1').adopted is False
    with pytest.raises(ValueError, match='enqueue identity mismatch'):
        adopt_on_identity(existing_id='other_item', item_id='item_1')
