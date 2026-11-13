"""Runner contracts for the bounded Chat-first/candidate-outbox lane join.

``run_bounded_lane_transaction`` is the single boundary every joined entry
rides. These tests pin its contracts at the unit level: the engine is
imported at call time so a harness pinning binds, a fresh transaction carries
exactly one SDK commit attempt, foreign domain refusals pass through
single-shot, expired chains replay on a fresh id and keep their ceiling only
while no deadline is in scope, an ambient deadline scope bounds the chain
even though the runner passes no deadline of its own, and both exhaustion
channels — the engine's labeled contention line and the lane's own marker —
name the flow that burned its budget.

Failure-Class: FC-bare-chat-first-and-candidate-outbox-transactions-fail-on-first-contention
"""

import logging

import pytest
from google.api_core.exceptions import Aborted as FirestoreAborted
from google.api_core.exceptions import InvalidArgument as FirestoreInvalidArgument

from database import bounded_lane_transaction as lane_module
from database import candidate_integration_outbox as outbox_db
from database import chat_first_delivery_attempts as delivery_attempts
from database import chat_first_intents as intents_db
from database import firestore_transaction_retry as engine
from database.firestore_transaction_retry import FirestoreContentionExhausted, transaction_retry_deadline_scope

LANE_LABELS = sorted(
    value
    for module in (intents_db, delivery_attempts, outbox_db)
    for name, value in vars(module).items()
    if name.endswith('_LABEL') and name.startswith(('CHAT_FIRST', 'CANDIDATE'))
)

EXPIRED_MESSAGE = '400 The referenced transaction has expired or is no longer valid'


class _ScriptedTransaction:
    def __init__(self, identifier):
        self.identifier = identifier


class _ScriptedClient:
    def __init__(self):
        self.minted = []
        self.max_attempts_kwargs = []

    def transaction(self, max_attempts=None):
        self.max_attempts_kwargs.append(max_attempts)
        transaction = _ScriptedTransaction(f'txn-{len(self.minted) + 1}')
        self.minted.append(transaction)
        return transaction


@pytest.fixture(autouse=True)
def _silence_ladder(monkeypatch):
    """The equal-jitter rungs are contract inputs here, never wall-clock waits."""
    monkeypatch.setattr(engine, 'equal_jitter_delay', lambda attempt, random_value=None: 0.0)


def test_lane_labels_are_distinct_across_the_three_modules():
    assert len(LANE_LABELS) == 25
    assert len(set(LANE_LABELS)) == 25
    assert all(label == label.strip().lower() and '_' in label for label in LANE_LABELS)


def test_engine_pin_binds_through_the_call_time_import(monkeypatch):
    seen = {}

    class _Sentinel:
        def __call__(self, transaction_factory, operation, **kwargs):
            seen['called'] = True
            seen['operation_name'] = kwargs.get('operation_name')
            return operation(transaction_factory())

    monkeypatch.setattr(engine, 'run_with_transaction_contention_retry', _Sentinel())
    result = lane_module.run_bounded_lane_transaction(
        _ScriptedClient(), lambda transaction: 'lane_ok', operation_name='candidate_outbox_claim', logger=None
    )
    assert result == 'lane_ok'
    assert seen['called'] is True
    assert seen['operation_name'] == 'candidate_outbox_claim'


def test_every_fresh_transaction_carries_one_sdk_commit_attempt():
    client = _ScriptedClient()
    result = lane_module.run_bounded_lane_transaction(
        client, lambda transaction: 'lane_ok', operation_name='candidate_outbox_claim', logger=None
    )
    assert result == 'lane_ok'
    assert client.max_attempts_kwargs == [1]
    assert client.minted[0].identifier == 'txn-1'


def test_contention_exhaustion_is_typed_and_labeled(caplog):
    client = _ScriptedClient()

    def always_aborts(_transaction):
        raise FirestoreAborted('409 preflight collision')

    with pytest.raises(FirestoreContentionExhausted) as raised:
        lane_module.run_bounded_lane_transaction(
            client, always_aborts, operation_name='candidate_outbox_claim', logger=None
        )
    assert raised.value.reason == 'attempts_exhausted'
    assert raised.value.retry_after == 0.0
    assert isinstance(raised.value.__cause__, FirestoreAborted)
    assert len(client.minted) == 5
    assert {transaction.identifier for transaction in client.minted} == {f'txn-{number}' for number in range(1, 6)}
    assert any(
        'operation=candidate_outbox_claim attempt=5/5 outcome=exhausted' in record.getMessage()
        for record in caplog.records
    )


def test_foreign_domain_refusal_passes_through_single_shot():
    client = _ScriptedClient()

    def domain_refusal(_transaction):
        raise ValueError('continuity key was reused')

    with pytest.raises(ValueError) as raised:
        lane_module.run_bounded_lane_transaction(
            client, domain_refusal, operation_name='candidate_outbox_claim', logger=None
        )
    assert raised.value.args == ('continuity key was reused',)
    assert len(client.minted) == 1


def test_expired_chain_replays_on_a_fresh_transaction(caplog):
    caplog.set_level(logging.INFO)
    client = _ScriptedClient()
    attempts = []

    def expires_once(transaction):
        attempts.append(transaction.identifier)
        if len(attempts) == 1:
            raise FirestoreInvalidArgument(EXPIRED_MESSAGE)
        return 'lane_ok'

    result = lane_module.run_bounded_lane_transaction(
        client, expires_once, operation_name='candidate_outbox_claim', logger=None
    )
    assert result == 'lane_ok'
    assert attempts == ['txn-1', 'txn-2'], 'the retired chain is replaced, never replayed'
    assert any('outcome=recovered' in record.getMessage() for record in caplog.records)


def test_expired_chain_ceiling_holds_without_a_deadline():
    client = _ScriptedClient()

    def always_expired(_transaction):
        raise FirestoreInvalidArgument(EXPIRED_MESSAGE)

    with pytest.raises(FirestoreContentionExhausted):
        lane_module.run_bounded_lane_transaction(
            client, always_expired, operation_name='candidate_outbox_claim', logger=None
        )
    assert len(client.minted) == 3, 'without a wall-clock budget expiry keeps the three-chain ceiling'


def _run_with_pinned_monotonic(client, body, clock):
    from database._client import run_transactional

    return engine.run_with_transaction_contention_retry(
        lambda: client.transaction(max_attempts=1),
        lambda transaction: run_transactional(client, body, initial_transaction=transaction, attempts=1),
        operation_name='candidate_outbox_claim',
        monotonic=clock,
    )


def test_ambient_deadline_scope_bounds_the_chain():
    client = _ScriptedClient()
    monotonic = {'now': 100.0}

    def clock():
        return monotonic['now']

    def slow_body(_transaction):
        monotonic['now'] += 20.0
        raise FirestoreAborted('409 preflight collision')

    with transaction_retry_deadline_scope(135.0):
        with pytest.raises(FirestoreContentionExhausted) as raised:
            _run_with_pinned_monotonic(client, slow_body, clock)
    assert raised.value.reason == 'deadline_exhausted'
    assert len(client.minted) == 1, 'the reserve rule refuses a retry the budget cannot cover'


def test_lane_logger_receives_the_exhaustion_marker(caplog):
    client = _ScriptedClient()
    lane_logger = logging.getLogger('database.candidate_integration_outbox')

    def always_aborts(_transaction):
        raise FirestoreAborted('409 preflight collision')

    with pytest.raises(FirestoreContentionExhausted):
        lane_module.run_bounded_lane_transaction(
            client, always_aborts, operation_name='candidate_outbox_claim', logger=lane_logger
        )
    assert any('event=candidate_outbox_claim_contention_exhausted' in record.getMessage() for record in caplog.records)


def test_happy_path_stays_silent_on_the_contention_channel(caplog):
    client = _ScriptedClient()
    result = lane_module.run_bounded_lane_transaction(
        client, lambda transaction: 'lane_ok', operation_name='candidate_outbox_claim', logger=None
    )
    assert result == 'lane_ok'
    assert not [
        record for record in caplog.records if record.getMessage().startswith('firestore_transaction_contention')
    ]


def test_max_attempts_parameter_bounds_the_chain():
    client = _ScriptedClient()

    def always_aborts(_transaction):
        raise FirestoreAborted('409 preflight collision')

    with pytest.raises(FirestoreContentionExhausted):
        lane_module.run_bounded_lane_transaction(
            client, always_aborts, operation_name='candidate_outbox_claim', logger=None, max_attempts=2
        )
    assert len(client.minted) == 2
