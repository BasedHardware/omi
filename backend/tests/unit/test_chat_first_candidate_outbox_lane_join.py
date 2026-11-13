"""Every Chat-first/candidate-outbox transactional entry rides the bounded engine.

Before this change the twenty-five transactional entries across
``chat_first_intents``, ``chat_first_delivery_attempts`` and
``candidate_integration_outbox`` handed their bodies to the Firestore SDK's
bare transaction path: one transaction id replayed by the SDK's same-id
commit loop, a read-time ``Aborted`` fault escaping as an unclassified error,
and an exhaustion surfacing anonymously. Each test here drives the real site
function against a client whose transactional operations all raise ``Aborted``
and asserts the typed, labeled bounded outcome — five fresh transactions, one
SDK commit attempt each, and an exhaustion record that names the flow. On a
tree without the join these tests fail with the raw ``Aborted`` fault instead.

Failure-Class: FC-bare-chat-first-and-candidate-outbox-transactions-fail-on-first-contention
"""

import logging
from datetime import datetime, timezone

import pytest
from google.api_core.exceptions import Aborted

from database import candidate_integration_outbox as outbox_db
from database import chat_first_delivery_attempts as delivery_attempts
from database import chat_first_intents as intents_db
from database import firestore_transaction_retry as engine
from database.firestore_transaction_retry import FirestoreContentionExhausted
from models.chat_first import ChatFirstSubject, ProactiveDeferral, QuestionCardSpec

UID = 'uid-lane-join'
GENERATION = 3
NOW = datetime(2026, 11, 14, 12, 0, tzinfo=timezone.utc)
SUBJECT = ChatFirstSubject(kind='goal', id='goal-lane-join')
QUESTION = QuestionCardSpec(
    type='questionCard',
    question_id='question-lane-join',
    text='What should happen next?',
    subject=SUBJECT,
    options=[{'option_id': 'option-1', 'label': 'One', 'prepared_answer': 'Do one', 'defer': False}],
)
DEFERRAL = ProactiveDeferral(
    deferral_id='deferral-lane-join',
    continuity_key='continuity-lane-join',
    account_generation=GENERATION,
    subject=SUBJECT,
    question=QUESTION,
    created_at=NOW,
    due_at=NOW,
)


class _FaultingTransaction:
    def get(self, **_kwargs):
        raise Aborted('409 transaction contention on every operation')

    def set(self, *_args, **_kwargs):
        raise Aborted('409 transaction contention on every operation')

    def update(self, *_args, **_kwargs):
        raise Aborted('409 transaction contention on every operation')

    def delete(self, *_args, **_kwargs):
        raise Aborted('409 transaction contention on every operation')


class _FaultingDocument:
    def get(self, **_kwargs):
        raise Aborted('409 transaction contention on every operation')

    def collection(self, *_args):
        return _FaultingCollection()


class _FaultingCollection:
    def document(self, *_args):
        return _FaultingDocument()


class _FaultingClient:
    """Every mint is fresh and single-commit-attempt; every operation aborts."""

    def __init__(self):
        self.minted = []

    def transaction(self, max_attempts=None):
        self.minted.append(max_attempts)
        return _FaultingTransaction()

    def collection(self, *_args):
        return _FaultingCollection()


@pytest.fixture
def lane_env(monkeypatch):
    """Real transactional bodies on a faulting client; the jitter ladder silenced."""

    def passthrough(function):
        return lambda transaction: function(transaction)

    for module in (intents_db, outbox_db, delivery_attempts):
        monkeypatch.setattr(module.firestore, 'transactional', passthrough)
    monkeypatch.setattr(engine, 'equal_jitter_delay', lambda attempt, random_value=None: 0.0)
    return _FaultingClient()


def _assert_bounded_exhaustion(caplog, label, minted):
    assert len(minted) == 5, 'a bounded chain mints five fresh transactions'
    assert set(minted) == {1}, 'every fresh transaction carries a single SDK commit attempt'
    assert any(
        record.levelno == logging.ERROR
        and f'operation={label}' in record.getMessage()
        and 'outcome=exhausted' in record.getMessage()
        for record in caplog.records
    ), 'the exhaustion names the flow on the contention channel'


def test_claim_candidate_integration_dispatch_joins_bounded_engine(lane_env, caplog):
    with pytest.raises(FirestoreContentionExhausted):
        outbox_db.claim_candidate_integration_dispatch(
            UID, 'candidate-1', account_generation=GENERATION, now=NOW, firestore_client=lane_env
        )
    _assert_bounded_exhaustion(caplog, 'candidate_outbox_claim', lane_env.minted)


def test_refresh_candidate_integration_lease_joins_bounded_engine(lane_env, caplog):
    with pytest.raises(FirestoreContentionExhausted):
        outbox_db.refresh_candidate_integration_lease(
            UID, 'candidate-1', lease_token='lease-1', now=NOW, firestore_client=lane_env
        )
    _assert_bounded_exhaustion(caplog, 'candidate_outbox_lease_refresh', lane_env.minted)


def test_note_candidate_integration_provider_attempt_joins_bounded_engine(lane_env, caplog):
    with pytest.raises(FirestoreContentionExhausted):
        outbox_db.note_candidate_integration_provider_attempt(
            UID,
            'candidate-1',
            lease_token='lease-1',
            outcome=outbox_db.PROVIDER_ATTEMPT_NOT_SENT,
            now=NOW,
            firestore_client=lane_env,
        )
    _assert_bounded_exhaustion(caplog, 'candidate_outbox_provider_note', lane_env.minted)


def test_complete_candidate_integration_dispatch_joins_bounded_engine(lane_env, caplog):
    with pytest.raises(FirestoreContentionExhausted):
        outbox_db.complete_candidate_integration_dispatch(
            UID,
            'candidate-1',
            account_generation=GENERATION,
            lease_token='lease-1',
            succeeded=True,
            now=NOW,
            firestore_client=lane_env,
        )
    _assert_bounded_exhaustion(caplog, 'candidate_outbox_complete', lane_env.minted)


def test_redrive_candidate_integration_dead_letter_joins_bounded_engine(lane_env, caplog, monkeypatch):
    monkeypatch.setattr(outbox_db, 'db', lane_env)
    with pytest.raises(FirestoreContentionExhausted):
        outbox_db.redrive_candidate_integration_dead_letter(UID, 'candidate-1', account_generation=GENERATION, now=NOW)
    _assert_bounded_exhaustion(caplog, 'candidate_outbox_redrive', lane_env.minted)


def test_dead_letter_malformed_candidate_integration_joins_bounded_engine(lane_env, caplog, monkeypatch):
    monkeypatch.setattr(outbox_db, 'db', lane_env)
    with pytest.raises(FirestoreContentionExhausted):
        outbox_db.dead_letter_malformed_candidate_integration(
            UID, 'candidate-1', account_generation=GENERATION, error_text='bad row', now=NOW
        )
    _assert_bounded_exhaustion(caplog, 'candidate_outbox_malformed_dead_letter', lane_env.minted)


def test_write_candidate_integration_sweep_cursors_joins_bounded_engine(lane_env, caplog):
    with pytest.raises(FirestoreContentionExhausted):
        outbox_db.write_candidate_integration_sweep_cursors({'failed': 'users/u/c/1'}, firestore_client=lane_env)
    _assert_bounded_exhaustion(caplog, 'candidate_outbox_sweep_cursors', lane_env.minted)


def test_abandon_candidate_integration_dispatch_joins_bounded_engine(lane_env, caplog):
    with pytest.raises(FirestoreContentionExhausted):
        outbox_db.abandon_candidate_integration_dispatch(
            UID, 'candidate-1', reason='in_doubt', now=NOW, firestore_client=lane_env
        )
    _assert_bounded_exhaustion(caplog, 'candidate_outbox_abandon', lane_env.minted)


def test_dead_letter_candidate_integration_generation_mismatch_joins_bounded_engine(lane_env, caplog):
    with pytest.raises(FirestoreContentionExhausted):
        outbox_db.dead_letter_candidate_integration_generation_mismatch(
            UID, 'candidate-1', now=NOW, firestore_client=lane_env
        )
    _assert_bounded_exhaustion(caplog, 'candidate_outbox_generation_mismatch', lane_env.minted)


def test_complete_candidate_integration_recorded_export_joins_bounded_engine(lane_env, caplog):
    with pytest.raises(FirestoreContentionExhausted):
        outbox_db.complete_candidate_integration_recorded_export(
            UID, 'candidate-1', external_task_id='task-1', now=NOW, firestore_client=lane_env
        )
    _assert_bounded_exhaustion(caplog, 'candidate_outbox_recorded_export', lane_env.minted)


def test_admit_agent_judgment_joins_bounded_engine(lane_env, caplog):
    with pytest.raises(FirestoreContentionExhausted):
        intents_db.admit_agent_judgment(
            UID,
            continuity_key='continuity-lane-join',
            subject=SUBJECT,
            account_generation=GENERATION,
            now=NOW,
            firestore_client=lane_env,
        )
    _assert_bounded_exhaustion(caplog, 'chat_first_intent_judgment_admit', lane_env.minted)


def test_release_agent_judgment_admission_joins_bounded_engine(lane_env, caplog):
    with pytest.raises(FirestoreContentionExhausted):
        intents_db.release_agent_judgment_admission(
            UID,
            continuity_key='continuity-lane-join',
            account_generation=GENERATION,
            now=NOW,
            firestore_client=lane_env,
        )
    _assert_bounded_exhaustion(caplog, 'chat_first_intent_judgment_release', lane_env.minted)


def test_create_intent_joins_bounded_engine(lane_env, caplog):
    with pytest.raises(FirestoreContentionExhausted):
        intents_db.create_intent(
            UID,
            source='capture_arrival',
            continuity_key='continuity-lane-join',
            subject=SUBJECT,
            blocks=[QUESTION],
            account_generation=GENERATION,
            now=NOW,
            firestore_client=lane_env,
        )
    _assert_bounded_exhaustion(caplog, 'chat_first_intent_create', lane_env.minted)


def test_get_or_create_cold_start_intent_joins_bounded_engine(lane_env, caplog):
    with pytest.raises(FirestoreContentionExhausted):
        intents_db.get_or_create_cold_start_intent(
            UID,
            source='cold_start_rich',
            continuity_key='continuity-lane-join',
            subject=SUBJECT,
            blocks=[QUESTION],
            account_generation=GENERATION,
            now=NOW,
            firestore_client=lane_env,
        )
    _assert_bounded_exhaustion(caplog, 'chat_first_intent_cold_start_create', lane_env.minted)


def test_acknowledge_sparse_cold_start_sequence_terminal_joins_bounded_engine(lane_env, caplog):
    with pytest.raises(FirestoreContentionExhausted):
        intents_db.acknowledge_sparse_cold_start_sequence_terminal(
            UID,
            sequence_id=f'cold-start:{GENERATION}',
            receipt_id='receipt-1',
            terminal_state='completed',
            account_generation=GENERATION,
            now=NOW,
            firestore_client=lane_env,
        )
    _assert_bounded_exhaustion(caplog, 'chat_first_intent_cold_start_terminal_ack', lane_env.minted)


def test_advance_fetched_intent_joins_bounded_engine(lane_env, caplog):
    with pytest.raises(FirestoreContentionExhausted):
        intents_db._advance_fetched_intent(
            UID,
            'intent-1',
            account_generation=GENERATION,
            now=NOW,
            reconcile=False,
            firestore_client=lane_env,
        )
    _assert_bounded_exhaustion(caplog, 'chat_first_intent_fetch_advance', lane_env.minted)


def test_dead_letter_malformed_intent_joins_bounded_engine(lane_env, caplog):
    with pytest.raises(FirestoreContentionExhausted):
        intents_db._dead_letter_malformed_intent(
            UID, 'intent-1', account_generation=GENERATION, firestore_client=lane_env
        )
    _assert_bounded_exhaustion(caplog, 'chat_first_intent_malformed_dead_letter', lane_env.minted)


def test_retire_capture_receipt_joins_bounded_engine(lane_env, caplog):
    with pytest.raises(FirestoreContentionExhausted):
        intents_db._retire_capture_receipt(
            UID,
            'intent-1',
            account_generation=GENERATION,
            reason='stale_capture_receipt',
            now=NOW,
            firestore_client=lane_env,
        )
    _assert_bounded_exhaustion(caplog, 'chat_first_intent_capture_receipt_retire', lane_env.minted)


def test_record_materialization_rejection_joins_bounded_engine(lane_env, caplog):
    with pytest.raises(FirestoreContentionExhausted):
        intents_db.record_materialization_rejection(
            UID,
            intent_id='intent-1',
            code='invalid_intent',
            account_generation=GENERATION,
            now=NOW,
            firestore_client=lane_env,
        )
    _assert_bounded_exhaustion(caplog, 'chat_first_intent_materialization_reject', lane_env.minted)


def test_record_materialization_deferral_joins_bounded_engine(lane_env, caplog):
    with pytest.raises(FirestoreContentionExhausted):
        intents_db.record_materialization_deferral(
            UID, intent_id='intent-1', account_generation=GENERATION, now=NOW, firestore_client=lane_env
        )
    _assert_bounded_exhaustion(caplog, 'chat_first_intent_materialization_defer', lane_env.minted)


def test_acknowledge_materialization_joins_bounded_engine(lane_env, caplog):
    with pytest.raises(FirestoreContentionExhausted):
        intents_db.acknowledge_materialization(
            UID,
            intent_id='intent-1',
            receipt_id='receipt-1',
            account_generation=GENERATION,
            now=NOW,
            firestore_client=lane_env,
        )
    _assert_bounded_exhaustion(caplog, 'chat_first_intent_materialization_ack', lane_env.minted)


def test_record_deferral_joins_bounded_engine(lane_env, caplog):
    with pytest.raises(FirestoreContentionExhausted):
        intents_db.record_deferral(
            UID,
            continuity_key='continuity-lane-join',
            subject=SUBJECT,
            question=QUESTION,
            account_generation=GENERATION,
            now=NOW,
            firestore_client=lane_env,
        )
    _assert_bounded_exhaustion(caplog, 'chat_first_intent_deferral_record', lane_env.minted)


def test_terminalize_malformed_deferral_joins_bounded_engine(lane_env, caplog):
    with pytest.raises(FirestoreContentionExhausted):
        intents_db._terminalize_malformed_deferral(
            UID, 'deferral-lane-join', account_generation=GENERATION, firestore_client=lane_env
        )
    _assert_bounded_exhaustion(caplog, 'chat_first_intent_deferral_malformed_release', lane_env.minted)


def test_release_deferral_transaction_joins_bounded_engine(lane_env, caplog):
    with pytest.raises(FirestoreContentionExhausted):
        intents_db._release_deferral_transaction(
            UID, DEFERRAL, account_generation=GENERATION, now=NOW, firestore_client=lane_env
        )
    _assert_bounded_exhaustion(caplog, 'chat_first_intent_deferral_release', lane_env.minted)


def test_requeue_transient_dead_letter_joins_bounded_engine(lane_env, caplog):
    with pytest.raises(FirestoreContentionExhausted):
        delivery_attempts.requeue_transient_dead_letter(
            UID, 'intent-1', account_generation=GENERATION, now=NOW, firestore_client=lane_env
        )
    _assert_bounded_exhaustion(caplog, 'chat_first_intent_transient_requeue', lane_env.minted)
