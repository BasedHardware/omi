"""Hermetic contracts for server-only Chat-first proactive intent state."""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

import database.chat_first_intents as intents_db
from tests.store_fakes import FakeDocumentStore
from tests.unit.canonical_cohort_test_helpers import set_canonical_cohort
from models.chat_first import (
    CaptureLinkSpec,
    ChatFirstSubject,
    ColdStartSequence,
    QuestionCardSpec,
    QuestionOption,
)
from models.chat_first import ProactiveBudgetState
from models.proactive_budget import budget_allows
from models.task_intelligence import TaskWorkflowControl, TaskWorkflowMode

NOW = datetime(2026, 7, 15, 12, tzinfo=timezone.utc)
UID = 'user-1'
GENERATION = 7
CONTROL_PATH = f'users/{UID}/task_intelligence_control/state'


@pytest.fixture
def store(monkeypatch):
    set_canonical_cohort(monkeypatch, UID)
    fake = FakeDocumentStore()
    monkeypatch.setattr(intents_db, '_store', lambda: fake)
    fake.set(
        CONTROL_PATH,
        TaskWorkflowControl(
            workflow_mode=TaskWorkflowMode.read,
            account_generation=GENERATION,
            chat_first_ui_enabled=True,
        ).persisted_payload(),
    )
    return fake


def _question(subject: ChatFirstSubject | None = None) -> QuestionCardSpec:
    return QuestionCardSpec(
        type='questionCard',
        question_id='question-1',
        text='What should happen next?',
        subject=subject or ChatFirstSubject(kind='goal', id='goal-1'),
        options=[QuestionOption(option_id='yes', label='Yes', prepared_answer='Yes')],
    )


def test_agent_intent_reserves_then_receipt_accounts_one_turn_idempotently(store):
    question = _question()
    intent, created = intents_db.create_intent(
        UID,
        source='agent_judgment',
        continuity_key='goal-1-complete',
        subject=question.subject,
        blocks=[question],
        account_generation=GENERATION,
        now=NOW,
    )
    retried, created_on_retry = intents_db.create_intent(
        UID,
        source='agent_judgment',
        continuity_key='goal-1-complete',
        subject=question.subject,
        blocks=[question],
        account_generation=GENERATION,
        now=NOW,
    )

    assert created is True
    assert created_on_retry is False
    assert retried.intent_id == intent.intent_id
    assert (
        len(
            intents_db.get_budget_state(
                UID, account_generation=GENERATION, now=NOW
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
    )
    replayed = intents_db.acknowledge_materialization(
        UID,
        intent_id=intent.intent_id,
        receipt_id='kernel-receipt-1',
        account_generation=GENERATION,
        now=NOW + timedelta(seconds=1),
    )
    budget = intents_db.get_budget_state(UID, account_generation=GENERATION, now=NOW)

    assert delivered.delivery_state == 'delivered'
    assert replayed == delivered
    assert budget.reservations == []
    assert budget.materialized_at == [NOW]


def test_budget_gate_counts_reservations_before_a_provider_call(store):
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
        )

    budget = intents_db.get_budget_state(UID, account_generation=GENERATION, now=NOW)

    assert budget_allows(budget, now=NOW) is False


def test_agent_judgment_admission_is_single_writer_and_decline_releases_its_slot(store):
    first = intents_db.admit_agent_judgment(
        UID,
        continuity_key='first',
        subject=ChatFirstSubject(kind='goal', id='goal-1'),
        account_generation=GENERATION,
        now=NOW,
    )
    duplicate = intents_db.admit_agent_judgment(
        UID,
        continuity_key='first',
        subject=ChatFirstSubject(kind='goal', id='goal-1'),
        account_generation=GENERATION,
        now=NOW,
    )
    second = intents_db.admit_agent_judgment(
        UID,
        continuity_key='second',
        subject=ChatFirstSubject(kind='goal', id='goal-2'),
        account_generation=GENERATION,
        now=NOW,
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
        )

    intents_db.release_agent_judgment_admission(
        UID,
        continuity_key='first',
        account_generation=GENERATION,
        now=NOW,
    )
    retry = intents_db.admit_agent_judgment(
        UID,
        continuity_key='third',
        subject=ChatFirstSubject(kind='goal', id='goal-3'),
        account_generation=GENERATION,
        now=NOW,
    )

    assert retry.newly_reserved is True


def test_pre_admitted_agent_judgment_reuses_its_reservation_when_the_intent_is_persisted(store):
    question = _question()
    admission = intents_db.admit_agent_judgment(
        UID,
        continuity_key='goal-1-complete',
        subject=question.subject,
        account_generation=GENERATION,
        now=NOW,
    )

    intent, created = intents_db.create_intent(
        UID,
        source='agent_judgment',
        continuity_key='goal-1-complete',
        subject=question.subject,
        blocks=[question],
        account_generation=GENERATION,
        now=NOW,
    )

    assert admission.newly_reserved is True
    assert created is True
    assert intent.delivery_state == 'ready'
    assert (
        len(
            intents_db.get_budget_state(
                UID, account_generation=GENERATION, now=NOW
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


def test_capture_arrival_retry_creates_one_deterministic_receipt_intent(store):
    blocks = [CaptureLinkSpec(type='captureLink', conversation_id='capture-1', summary='New Omi capture')]
    first, created = intents_db.create_intent(
        UID,
        source='capture_arrival',
        continuity_key='capture:capture-1',
        subject=ChatFirstSubject(kind='capture', id='capture-1'),
        blocks=blocks,
        account_generation=GENERATION,
        now=NOW,
    )
    retry, created_on_retry = intents_db.create_intent(
        UID,
        source='capture_arrival',
        continuity_key='capture:capture-1',
        subject=ChatFirstSubject(kind='capture', id='capture-1'),
        blocks=blocks,
        account_generation=GENERATION,
        now=NOW + timedelta(minutes=1),
    )

    assert created is True
    assert created_on_retry is False
    assert retry.intent_id == first.intent_id
    assert retry.source == 'capture_arrival'


def test_cold_start_generation_retries_one_pending_intent_until_its_kernel_receipt(store):
    sequence_id = f'cold-start:{GENERATION}'
    question = QuestionCardSpec(
        type='questionCard',
        question_id=f'{sequence_id}:step:1',
        text='What matters now?',
        subject=ChatFirstSubject(kind='cold_start', id=sequence_id),
        cold_start_sequence=ColdStartSequence(sequence_id=sequence_id, step=1),
        options=[QuestionOption(option_id='progress', label='Make progress', prepared_answer='Make progress.')],
    )
    first, created = intents_db.get_or_create_cold_start_intent(
        UID,
        source='cold_start_sparse',
        continuity_key=sequence_id,
        subject=question.subject,
        blocks=[question],
        account_generation=GENERATION,
        now=NOW,
    )
    retried, retry_created = intents_db.get_or_create_cold_start_intent(
        UID,
        source='cold_start_rich',
        continuity_key=sequence_id,
        subject=ChatFirstSubject(kind='goal', id='goal-1'),
        blocks=[CaptureLinkSpec(type='captureLink', conversation_id='capture-1', summary='Ignored retry shape')],
        account_generation=GENERATION,
        now=NOW + timedelta(minutes=1),
    )

    assert created is True
    assert retry_created is False
    assert retried == first
    assert first.delivery_state == 'pending_kernel_receipt'
    assert (
        intents_db.has_active_sparse_cold_start_sequence(UID, account_generation=GENERATION)
        is True
    )
    assert intents_db.fetch_ready_intents(UID, account_generation=GENERATION) == [first]
    delivered = intents_db.acknowledge_materialization(
        UID,
        intent_id=first.intent_id,
        receipt_id='kernel-receipt-1',
        account_generation=GENERATION,
        now=NOW,
    )

    assert delivered.delivery_state == 'delivered'
    assert (
        intents_db.has_active_sparse_cold_start_sequence(UID, account_generation=GENERATION)
        is True
    )
    terminalized = intents_db.acknowledge_sparse_cold_start_sequence_terminal(
        UID,
        sequence_id=sequence_id,
        receipt_id='sequence-terminal-receipt-1',
        terminal_state='abandoned',
        account_generation=GENERATION,
        now=NOW + timedelta(seconds=1),
    )
    assert terminalized.cold_start_sequence_terminal_state == 'abandoned'
    assert terminalized.cold_start_sequence_terminal_receipt_id == 'sequence-terminal-receipt-1'
    assert (
        intents_db.has_active_sparse_cold_start_sequence(UID, account_generation=GENERATION)
        is False
    )
    assert (
        intents_db.acknowledge_sparse_cold_start_sequence_terminal(
            UID,
            sequence_id=sequence_id,
            receipt_id='sequence-terminal-receipt-1',
            terminal_state='abandoned',
            account_generation=GENERATION,
            now=NOW + timedelta(seconds=2),
        )
        == terminalized
    )
    with pytest.raises(intents_db.ChatFirstIntentConflictError):
        intents_db.acknowledge_sparse_cold_start_sequence_terminal(
            UID,
            sequence_id=sequence_id,
            receipt_id='another-terminal-receipt',
            terminal_state='completed',
            account_generation=GENERATION,
            now=NOW + timedelta(seconds=3),
        )
    with pytest.raises(intents_db.ChatFirstIntentConflictError):
        intents_db.acknowledge_materialization(
            UID,
            intent_id=first.intent_id,
            receipt_id='different-kernel-receipt',
            account_generation=GENERATION,
            now=NOW + timedelta(seconds=1),
        )
    assert intents_db.fetch_ready_intents(UID, account_generation=GENERATION) == []


def test_deferral_releases_once_verbatim_when_due_or_subject_changes(store):
    question = _question()
    receipt, created = intents_db.record_deferral(
        UID,
        continuity_key='defer-goal-1',
        subject=question.subject,
        question=question,
        account_generation=GENERATION,
        now=NOW,
    )

    assert created is True
    assert receipt.state == 'pending'
    assert (
        intents_db.release_due_deferrals(
            UID,
            account_generation=GENERATION,
            now=NOW + timedelta(hours=23, minutes=59),
        )
        == []
    )

    due = intents_db.release_due_deferrals(
        UID,
        account_generation=GENERATION,
        now=NOW + timedelta(hours=24),
    )
    replay = intents_db.release_due_deferrals(
        UID,
        account_generation=GENERATION,
        now=NOW + timedelta(hours=25),
    )

    assert len(due) == 1
    assert due[0].source == 'deferral_reraise'
    released_question = due[0].blocks[0]
    assert released_question.question_id != question.question_id
    assert released_question.model_copy(update={'question_id': question.question_id}) == question
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
    )
    subject_change = intents_db.release_due_deferrals(
        UID,
        account_generation=GENERATION,
        now=NOW + timedelta(minutes=1),
        subject=task_subject,
    )

    assert len(subject_change) == 1
    assert subject_change[0].blocks[0].model_copy(update={'question_id': task_question.question_id}) == task_question
    assert subject_change[0].blocks[0].question_id != task_question.question_id


def test_workflow_mode_cannot_suppress_intent_but_stale_generation_still_rejects(store):
    store.set(
        CONTROL_PATH,
        TaskWorkflowControl(
            workflow_mode=TaskWorkflowMode.off,
            account_generation=GENERATION,
        ).persisted_payload(),
    )
    question = _question()

    intent, created = intents_db.create_intent(
        UID,
        source='agent_judgment',
        continuity_key='workflow-mode-is-metadata',
        subject=question.subject,
        blocks=[question],
        account_generation=GENERATION,
        now=NOW,
    )

    assert created is True
    assert intent.account_generation == GENERATION
    store.set(
        CONTROL_PATH,
        TaskWorkflowControl(
            workflow_mode=TaskWorkflowMode.off,
            account_generation=GENERATION + 1,
        ).persisted_payload(),
    )

    with pytest.raises(intents_db.ChatFirstIntentGenerationMismatch):
        intents_db.create_intent(
            UID,
            source='agent_judgment',
            continuity_key='stale-generation',
            subject=question.subject,
            blocks=[question],
            account_generation=GENERATION,
            now=NOW,
        )

    assert sum(INTENTS_COLLECTION in path for path in store._docs) == 1


def test_malformed_control_or_proactive_state_fails_closed_without_a_fail_open_drop(store):
    question = _question()
    malformed_control = store.get(CONTROL_PATH).to_dict()
    malformed_control['unexpected_legacy_field'] = True
    store.set(CONTROL_PATH, malformed_control)

    with patch('database.read_boundary.record_fallback') as fallback:
        with pytest.raises(intents_db.ChatFirstIntentGenerationMismatch, match='capability state is malformed'):
            intents_db.create_intent(
                UID,
                source='capture_arrival',
                continuity_key='malformed-control',
                subject=question.subject,
                blocks=[question],
                account_generation=GENERATION,
                now=NOW,
            )

    fallback.assert_not_called()
    assert not any(INTENTS_COLLECTION in path or DEFERRALS_COLLECTION in path for path in store._docs)


def test_malformed_intent_cannot_be_materialized_or_overwritten(store):
    path = f'users/{UID}/{intents_db.INTENTS_COLLECTION}/malformed-intent'
    store.set(
        path,
        {
            'account_generation': GENERATION,
            'unexpected_legacy_field': True,
        },
    )
    original = deepcopy(store._docs[path])

    with patch('database.read_boundary.record_fallback') as fallback:
        with pytest.raises(intents_db.ChatFirstIntentGenerationMismatch, match='proactive intent is malformed'):
            intents_db.acknowledge_materialization(
                UID,
                intent_id='malformed-intent',
                receipt_id='kernel-receipt-1',
                account_generation=GENERATION,
                now=NOW,
            )

    fallback.assert_not_called()
    assert store._docs[path] == original


def test_malformed_deferral_cannot_be_accepted_or_overwritten(store):
    question = _question()
    continuity_key = 'malformed-deferral'
    deferral_id = intents_db._stable_id('cfd', UID, GENERATION, continuity_key)
    path = f'users/{UID}/{intents_db.DEFERRALS_COLLECTION}/{deferral_id}'
    store.set(
        path,
        {
            'account_generation': GENERATION,
            'unexpected_legacy_field': True,
        },
    )
    original = deepcopy(store._docs[path])

    with patch('database.read_boundary.record_fallback') as fallback:
        with pytest.raises(intents_db.ChatFirstIntentGenerationMismatch, match='deferral is malformed'):
            intents_db.record_deferral(
                UID,
                continuity_key=continuity_key,
                subject=question.subject,
                question=question,
                account_generation=GENERATION,
                now=NOW,
            )

    fallback.assert_not_called()
    assert store._docs[path] == original


def test_malformed_budget_state_cannot_be_reset_to_an_enabled_default(store):
    path = f'users/{UID}/{intents_db.STATE_COLLECTION}/{intents_db.BUDGET_DOCUMENT}'
    store.set(
        path,
        {
            'account_generation': GENERATION,
            'unexpected_legacy_field': True,
        },
    )
    original = deepcopy(store._docs[path])

    with patch('database.read_boundary.record_fallback') as fallback:
        with pytest.raises(intents_db.ChatFirstIntentGenerationMismatch, match='proactive budget state is malformed'):
            intents_db.get_budget_state(UID, account_generation=GENERATION, now=NOW)

    fallback.assert_not_called()
    assert store._docs[path] == original


INTENTS_COLLECTION = intents_db.INTENTS_COLLECTION
DEFERRALS_COLLECTION = intents_db.DEFERRALS_COLLECTION
