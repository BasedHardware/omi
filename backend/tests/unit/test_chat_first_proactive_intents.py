"""Hermetic contracts for server-only Chat-first proactive intent state."""

from copy import deepcopy
from datetime import datetime, timedelta, timezone

import pytest

import database.chat_first_intents as intents_db
from models.chat_first import CaptureLinkSpec, ChatFirstSubject, QuestionCardSpec, QuestionOption
from models.chat_first import ProactiveBudgetState
from models.proactive_budget import budget_allows
from models.task_intelligence import TaskWorkflowControl, TaskWorkflowMode

NOW = datetime(2026, 7, 15, 12, tzinfo=timezone.utc)
UID = 'user-1'
GENERATION = 7


class _Snapshot:
    def __init__(self, database, path):
        self._database = database
        self._path = path
        self.exists = path in database.rows

    def to_dict(self):
        return deepcopy(self._database.rows.get(self._path))


class _Document:
    def __init__(self, database, path):
        self._database = database
        self._path = path

    @property
    def id(self):
        return self._path[-1]

    def collection(self, name):
        return _Collection(self._database, (*self._path, name))

    def get(self, transaction=None):
        if transaction is not None:
            transaction.read()
        return _Snapshot(self._database, self._path)

    def set(self, payload):
        self._database.rows[self._path] = deepcopy(payload)


class _Collection:
    def __init__(self, database, path):
        self._database = database
        self._path = path

    def document(self, identifier):
        return _Document(self._database, (*self._path, identifier))

    def stream(self):
        child_length = len(self._path) + 1
        return [
            _Snapshot(self._database, path)
            for path in sorted(self._database.rows)
            if path[: len(self._path)] == self._path and len(path) == child_length
        ]


class _Transaction:
    def __init__(self):
        self._wrote = False

    def read(self):
        if self._wrote:
            raise AssertionError('Firestore transactions must finish reads before writes')

    def set(self, ref, payload):
        self._wrote = True
        ref.set(payload)


class _Firestore:
    def __init__(self):
        self.rows = {}

    def collection(self, name):
        return _Collection(self, (name,))

    def transaction(self):
        return _Transaction()


@pytest.fixture
def firestore(monkeypatch):
    monkeypatch.setattr(
        intents_db.firestore, 'transactional', lambda function: lambda transaction: function(transaction)
    )
    fake = _Firestore()
    fake.rows[('users', UID, 'task_intelligence_control', 'state')] = TaskWorkflowControl(
        workflow_mode=TaskWorkflowMode.read,
        account_generation=GENERATION,
        chat_first_ui_enabled=True,
    ).persisted_payload()
    return fake


def _question(subject: ChatFirstSubject | None = None) -> QuestionCardSpec:
    return QuestionCardSpec(
        type='questionCard',
        question_id='question-1',
        text='What should happen next?',
        subject=subject or ChatFirstSubject(kind='goal', id='goal-1'),
        options=[QuestionOption(option_id='yes', label='Yes', prepared_answer='Yes')],
    )


def test_agent_intent_reserves_then_receipt_accounts_one_turn_idempotently(firestore):
    question = _question()
    intent, created = intents_db.create_intent(
        UID,
        source='agent_judgment',
        continuity_key='goal-1-complete',
        subject=question.subject,
        blocks=[question],
        account_generation=GENERATION,
        now=NOW,
        firestore_client=firestore,
    )
    retried, created_on_retry = intents_db.create_intent(
        UID,
        source='agent_judgment',
        continuity_key='goal-1-complete',
        subject=question.subject,
        blocks=[question],
        account_generation=GENERATION,
        now=NOW,
        firestore_client=firestore,
    )

    assert created is True
    assert created_on_retry is False
    assert retried.intent_id == intent.intent_id
    assert (
        len(
            intents_db.get_budget_state(
                UID, account_generation=GENERATION, now=NOW, firestore_client=firestore
            ).reservations
        )
        == 1
    )

    delivered = intents_db.acknowledge_materialization(
        UID,
        intent_id=intent.intent_id,
        receipt_id='kernel-receipt-1',
        account_generation=GENERATION,
        now=NOW,
        firestore_client=firestore,
    )
    replayed = intents_db.acknowledge_materialization(
        UID,
        intent_id=intent.intent_id,
        receipt_id='kernel-receipt-1',
        account_generation=GENERATION,
        now=NOW + timedelta(seconds=1),
        firestore_client=firestore,
    )
    budget = intents_db.get_budget_state(UID, account_generation=GENERATION, now=NOW, firestore_client=firestore)

    assert delivered.delivery_state == 'delivered'
    assert replayed == delivered
    assert budget.reservations == []
    assert budget.materialized_at == [NOW]


def test_budget_gate_counts_reservations_before_a_provider_call(firestore):
    question = _question()
    for continuity_key in ('first', 'second'):
        intents_db.create_intent(
            UID,
            source='agent_judgment',
            continuity_key=continuity_key,
            subject=question.subject,
            blocks=[question],
            account_generation=GENERATION,
            now=NOW,
            firestore_client=firestore,
        )

    budget = intents_db.get_budget_state(UID, account_generation=GENERATION, now=NOW, firestore_client=firestore)

    assert budget_allows(budget, now=NOW) is False


def test_agent_judgment_admission_is_single_writer_and_decline_releases_its_slot(firestore):
    first = intents_db.admit_agent_judgment(
        UID,
        continuity_key='first',
        subject=ChatFirstSubject(kind='goal', id='goal-1'),
        account_generation=GENERATION,
        now=NOW,
        firestore_client=firestore,
    )
    duplicate = intents_db.admit_agent_judgment(
        UID,
        continuity_key='first',
        subject=ChatFirstSubject(kind='goal', id='goal-1'),
        account_generation=GENERATION,
        now=NOW,
        firestore_client=firestore,
    )
    second = intents_db.admit_agent_judgment(
        UID,
        continuity_key='second',
        subject=ChatFirstSubject(kind='goal', id='goal-2'),
        account_generation=GENERATION,
        now=NOW,
        firestore_client=firestore,
    )

    assert first.newly_reserved is True
    assert duplicate.newly_reserved is False
    assert duplicate.existing_intent is None
    assert second.newly_reserved is True
    with pytest.raises(intents_db.ProactiveBudgetExhausted):
        intents_db.admit_agent_judgment(
            UID,
            continuity_key='third',
            subject=ChatFirstSubject(kind='goal', id='goal-3'),
            account_generation=GENERATION,
            now=NOW,
            firestore_client=firestore,
        )

    intents_db.release_agent_judgment_admission(
        UID,
        continuity_key='first',
        account_generation=GENERATION,
        now=NOW,
        firestore_client=firestore,
    )
    retry = intents_db.admit_agent_judgment(
        UID,
        continuity_key='third',
        subject=ChatFirstSubject(kind='goal', id='goal-3'),
        account_generation=GENERATION,
        now=NOW,
        firestore_client=firestore,
    )

    assert retry.newly_reserved is True


def test_pre_admitted_agent_judgment_reuses_its_reservation_when_the_intent_is_persisted(firestore):
    question = _question()
    admission = intents_db.admit_agent_judgment(
        UID,
        continuity_key='goal-1-complete',
        subject=question.subject,
        account_generation=GENERATION,
        now=NOW,
        firestore_client=firestore,
    )

    intent, created = intents_db.create_intent(
        UID,
        source='agent_judgment',
        continuity_key='goal-1-complete',
        subject=question.subject,
        blocks=[question],
        account_generation=GENERATION,
        now=NOW,
        firestore_client=firestore,
    )

    assert admission.newly_reserved is True
    assert created is True
    assert intent.delivery_state == 'ready'
    assert (
        len(
            intents_db.get_budget_state(
                UID, account_generation=GENERATION, now=NOW, firestore_client=firestore
            ).reservations
        )
        == 1
    )


def test_budget_has_explicit_rolling_and_utc_day_boundaries():
    rolling = ProactiveBudgetState(account_generation=GENERATION, materialized_at=[NOW, NOW])
    daily = ProactiveBudgetState(account_generation=GENERATION, materialized_at=[NOW] * 10)

    assert budget_allows(rolling, now=NOW + timedelta(minutes=29, seconds=59)) is False
    assert budget_allows(rolling, now=NOW + timedelta(minutes=30)) is True
    assert budget_allows(daily, now=NOW + timedelta(hours=1)) is False
    assert budget_allows(daily, now=NOW + timedelta(days=1)) is True


def test_capture_arrival_retry_creates_one_deterministic_receipt_intent(firestore):
    blocks = [CaptureLinkSpec(type='captureLink', conversation_id='capture-1', summary='New Omi capture')]
    first, created = intents_db.create_intent(
        UID,
        source='capture_arrival',
        continuity_key='capture:capture-1',
        subject=ChatFirstSubject(kind='capture', id='capture-1'),
        blocks=blocks,
        account_generation=GENERATION,
        now=NOW,
        firestore_client=firestore,
    )
    retry, created_on_retry = intents_db.create_intent(
        UID,
        source='capture_arrival',
        continuity_key='capture:capture-1',
        subject=ChatFirstSubject(kind='capture', id='capture-1'),
        blocks=blocks,
        account_generation=GENERATION,
        now=NOW + timedelta(minutes=1),
        firestore_client=firestore,
    )

    assert created is True
    assert created_on_retry is False
    assert retry.intent_id == first.intent_id
    assert retry.source == 'capture_arrival'


def test_deferral_releases_once_verbatim_when_due_or_subject_changes(firestore):
    question = _question()
    receipt, created = intents_db.record_deferral(
        UID,
        continuity_key='defer-goal-1',
        subject=question.subject,
        question=question,
        account_generation=GENERATION,
        now=NOW,
        firestore_client=firestore,
    )

    assert created is True
    assert receipt.state == 'pending'
    assert (
        intents_db.release_due_deferrals(
            UID,
            account_generation=GENERATION,
            now=NOW + timedelta(hours=23, minutes=59),
            firestore_client=firestore,
        )
        == []
    )

    due = intents_db.release_due_deferrals(
        UID,
        account_generation=GENERATION,
        now=NOW + timedelta(hours=24),
        firestore_client=firestore,
    )
    replay = intents_db.release_due_deferrals(
        UID,
        account_generation=GENERATION,
        now=NOW + timedelta(hours=25),
        firestore_client=firestore,
    )

    assert len(due) == 1
    assert due[0].source == 'deferral_reraise'
    assert due[0].blocks == [question]
    assert replay == []

    task_subject = ChatFirstSubject(kind='task', id='task-1')
    task_question = _question(task_subject)
    intents_db.record_deferral(
        UID,
        continuity_key='defer-task-1',
        subject=task_subject,
        question=task_question,
        account_generation=GENERATION,
        now=NOW,
        firestore_client=firestore,
    )
    subject_change = intents_db.release_due_deferrals(
        UID,
        account_generation=GENERATION,
        now=NOW + timedelta(minutes=1),
        subject=task_subject,
        firestore_client=firestore,
    )

    assert len(subject_change) == 1
    assert subject_change[0].blocks == [task_question]


def test_off_or_stale_control_rejects_intent_before_feature_records_are_read(firestore):
    firestore.rows[('users', UID, 'task_intelligence_control', 'state')] = TaskWorkflowControl(
        workflow_mode=TaskWorkflowMode.read,
        account_generation=GENERATION,
        chat_first_ui_enabled=False,
    ).persisted_payload()
    question = _question()

    with pytest.raises(intents_db.ChatFirstIntentGenerationMismatch):
        intents_db.create_intent(
            UID,
            source='agent_judgment',
            continuity_key='off',
            subject=question.subject,
            blocks=[question],
            account_generation=GENERATION,
            now=NOW,
            firestore_client=firestore,
        )

    assert not any(INTENTS_COLLECTION in path or DEFERRALS_COLLECTION in path for path in firestore.rows)


INTENTS_COLLECTION = intents_db.INTENTS_COLLECTION
DEFERRALS_COLLECTION = intents_db.DEFERRALS_COLLECTION
