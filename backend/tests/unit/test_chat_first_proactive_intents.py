"""Hermetic contracts for server-only Chat-first proactive intent state."""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from google.api_core.exceptions import GoogleAPICallError
from pydantic import BaseModel, ConfigDict
from typing import Literal

import database.chat_first_intents as intents_db
from models.chat_first import (
    CaptureLinkSpec,
    ChatFirstSubject,
    ColdStartSequence,
    ConversationLinkSpec,
    DeadLetteredProactiveIntent,
    QuestionCardSpec,
    QuestionOption,
)
from models.chat_first import ProactiveBudgetState
from models.proactive_budget import budget_allows
from models.task_intelligence import TaskWorkflowControl, TaskWorkflowMode

NOW = datetime(2026, 7, 15, 12, tzinfo=timezone.utc)
UID = 'user-1'
GENERATION = 7


class _OldStrictProactiveIntent(BaseModel):
    model_config = ConfigDict(extra='forbid')

    intent_id: str
    continuity_key: str
    account_generation: int
    source: str
    subject: object | None = None
    blocks: list[object]
    delivery_state: Literal['ready', 'pending_kernel_receipt', 'delivered'] = 'ready'
    created_at: datetime
    delivered_at: datetime | None = None
    materialization_receipt_id: str | None = None
    cold_start_sequence_terminal_state: str | None = None
    cold_start_sequence_terminal_receipt_id: str | None = None


class _Snapshot:
    def __init__(self, database, path):
        self._database = database
        self._path = path
        self.exists = path in database.rows

    def to_dict(self):
        return deepcopy(self._database.rows.get(self._path))

    @property
    def id(self):
        return self._path[-1]


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
            self._database.transaction_reads[self._path] = self._database.transaction_reads.get(self._path, 0) + 1
            hook = self._database.transaction_read_hooks.pop(self._path, None)
            if hook is not None:
                hook()
        else:
            self._database.point_reads[self._path] = self._database.point_reads.get(self._path, 0) + 1
        return _Snapshot(self._database, self._path)

    def set(self, payload, merge=False):
        existing = self._database.rows.get(self._path, {}) if merge else {}
        self._database.rows[self._path] = {**deepcopy(existing), **deepcopy(payload)}


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

    def where(self, *, filter):
        """Minimal FieldFilter mock supporting chained equality/range filters."""
        child_length = len(self._path) + 1
        snapshots = [
            _Snapshot(self._database, path)
            for path in sorted(self._database.rows)
            if path[: len(self._path)] == self._path and len(path) == child_length
        ]
        field = filter.field_path
        op = filter.op_string
        value = filter.value
        matched = []
        for snap in snapshots:
            snap_data = snap.to_dict() or {}
            actual = snap_data
            for component in field.split('.'):
                if not isinstance(actual, dict):
                    actual = None
                    break
                actual = actual.get(component)
            if op == 'in':
                if actual in value:
                    matched.append(snap)
            elif op == '==':
                if actual == value:
                    matched.append(snap)
            elif op == '<=':
                if actual is not None and actual <= value:
                    matched.append(snap)
            else:  # pragma: no cover - only ``in``/``==`` used by this suite
                matched.append(snap)
        return _FilteredCollection(matched)


class _FilteredCollection:
    """Result of ``_Collection.where`` — supports ``stream`` only."""

    def __init__(self, snapshots):
        self._snapshots = snapshots

    def stream(self):
        return self._snapshots

    def where(self, *, filter):
        field = filter.field_path
        op = filter.op_string
        value = filter.value
        matched = []
        for snap in self._snapshots:
            actual = snap.to_dict() or {}
            for component in field.split('.'):
                if not isinstance(actual, dict):
                    actual = None
                    break
                actual = actual.get(component)
            if op == '==' and actual == value:
                matched.append(snap)
            elif op == '<=' and actual is not None and actual <= value:
                matched.append(snap)
            elif op == 'in' and actual in value:
                matched.append(snap)
        return _FilteredCollection(matched)

    def limit(self, count):
        return _FilteredCollection(self._snapshots[:count])

    def order_by(self, field):
        def value(snapshot):
            actual = snapshot.to_dict() or {}
            for component in field.split('.'):
                if not isinstance(actual, dict) or component not in actual:
                    return False, None
                actual = actual.get(component)
            return True, actual

        present = [snapshot for snapshot in self._snapshots if value(snapshot)[0]]
        return _FilteredCollection(
            sorted(present, key=lambda snapshot: (value(snapshot)[1] is not None, value(snapshot)[1]))
        )


class _Transaction:
    def __init__(self, database):
        self._database = database
        self._wrote = False

    def read(self):
        if self._wrote:
            raise AssertionError('Firestore transactions must finish reads before writes')

    def set(self, ref, payload, merge=False):
        self._wrote = True
        ref.set(payload, merge=merge)

    def delete(self, ref):
        self._wrote = True
        self._database.rows.pop(ref._path, None)


class _Firestore:
    def __init__(self):
        self.rows = {}
        self.transaction_count = 0
        self.transaction_read_hooks = {}
        self.point_reads = {}
        self.transaction_reads = {}

    def collection(self, name):
        return _Collection(self, (name,))

    def transaction(self):
        self.transaction_count += 1
        return _Transaction(self)


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
    delivered_path = ('users', UID, intents_db.INTENTS_COLLECTION, intent.intent_id)
    parsed_by_old_reader = _OldStrictProactiveIntent.model_validate(firestore.rows[delivered_path])

    # The merge-base acknowledged receipts by parsing first and branching on
    # delivered state second. Preserve that exact rolling-reader shape.
    def merge_base_acknowledgement_shape(payload):
        parsed = _OldStrictProactiveIntent.model_validate(payload)
        if parsed.delivery_state == 'delivered':
            return parsed
        raise AssertionError('expected the old idempotent delivered branch')

    assert merge_base_acknowledgement_shape(firestore.rows[delivered_path]) == parsed_by_old_reader
    assert set(firestore.rows[delivered_path]) == set(_OldStrictProactiveIntent.model_fields)


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


def test_transient_kernel_error_three_times_does_not_dead_letter(firestore):
    poison, _ = intents_db.create_intent(
        UID,
        source='capture_arrival',
        continuity_key='capture:poison',
        subject=ChatFirstSubject(kind='capture', id='poison'),
        blocks=[CaptureLinkSpec(type='captureLink', conversation_id='poison', summary='Poison')],
        account_generation=GENERATION,
        now=NOW,
        firestore_client=firestore,
    )
    for attempt in range(1, intents_db.MATERIALIZATION_REJECTION_BUDGET + 1):
        rejected, reason = intents_db.record_materialization_rejection(
            UID,
            intent_id=poison.intent_id,
            code='kernel_materialization_failed',
            account_generation=GENERATION,
            now=NOW + timedelta(minutes=attempt),
            firestore_client=firestore,
        )
        assert rejected.materialization_attempts == 0
        assert reason is None

    assert rejected.delivery_state == 'ready'


def test_invalid_intent_three_times_dead_letters_and_requeued_poison_stays_terminal(firestore):
    intent, _ = intents_db.create_intent(
        UID,
        source='capture_arrival',
        continuity_key='capture:deterministic-poison',
        subject=ChatFirstSubject(kind='capture', id='deterministic-poison'),
        blocks=[CaptureLinkSpec(type='captureLink', conversation_id='deterministic-poison', summary='Poison')],
        account_generation=GENERATION,
        now=NOW,
        firestore_client=firestore,
    )
    path = ('users', UID, intents_db.DELIVERY_ATTEMPTS_COLLECTION, intent.intent_id)
    firestore.rows[path] = {'requeue_count': 1}

    for attempt in range(1, intents_db.MATERIALIZATION_REJECTION_BUDGET + 1):
        rejected, reason = intents_db.record_materialization_rejection(
            UID,
            intent_id=intent.intent_id,
            code='invalid_intent',
            account_generation=GENERATION,
            now=NOW + timedelta(minutes=attempt),
            firestore_client=firestore,
        )
        assert rejected.materialization_attempts == attempt

    assert reason == 'permanent_rejection:invalid_intent'
    assert rejected.delivery_state == 'dead_letter'
    replay, replay_reason = intents_db.record_materialization_rejection(
        UID,
        intent_id=intent.intent_id,
        code='kernel_materialization_failed',
        account_generation=GENERATION,
        now=NOW + timedelta(days=1),
        firestore_client=firestore,
    )
    assert replay is None
    assert replay_reason is None
    active_path = ('users', UID, intents_db.INTENTS_COLLECTION, intent.intent_id)
    dead_path = ('users', UID, intents_db.DEAD_LETTERS_COLLECTION, intent.intent_id)
    assert active_path not in firestore.rows
    terminal = DeadLetteredProactiveIntent.model_validate(firestore.rows[dead_path])
    assert terminal.delivery_state == 'dead_letter'
    assert terminal.last_fetched_at == NOW + timedelta(minutes=intents_db.MATERIALIZATION_REJECTION_BUDGET)


def test_legacy_transient_dead_letter_requeues_once_from_next_fetch_after_repair_age(firestore):
    intent, _ = intents_db.create_intent(
        UID,
        source='capture_arrival',
        continuity_key='capture:legacy-transient-dead-letter',
        subject=ChatFirstSubject(kind='capture', id='legacy-transient-dead-letter'),
        blocks=[CaptureLinkSpec(type='captureLink', conversation_id='legacy-transient', summary='Repair')],
        account_generation=GENERATION,
        now=NOW,
        firestore_client=firestore,
    )
    intent_path = ('users', UID, intents_db.INTENTS_COLLECTION, intent.intent_id)
    dead_path = ('users', UID, intents_db.DEAD_LETTERS_COLLECTION, intent.intent_id)
    firestore.rows[dead_path] = firestore.rows.pop(intent_path)
    firestore.rows[dead_path].update(
        delivery_state='dead_letter',
        dead_letter_reason='permanent_rejection:kernel_materialization_failed',
        materialization_attempts=3,
        last_rejection_code='kernel_materialization_failed',
        last_rejection_at=NOW,
        last_fetched_at=NOW,
        requeue_count=0,
    )

    repaired = intents_db.fetch_ready_intents(
        UID,
        account_generation=GENERATION,
        now=NOW + intents_db.TRANSIENT_DEAD_LETTER_REPAIR_AGE + timedelta(minutes=10),
        firestore_client=firestore,
    )

    assert repaired[0].delivery_state == 'ready'
    assert repaired[0].requeue_count == 1


def test_fetch_budget_dead_letters_an_unacknowledged_intent(firestore):
    intent, _ = intents_db.create_intent(
        UID,
        source='capture_arrival',
        continuity_key='capture:never-acknowledged',
        subject=ChatFirstSubject(kind='capture', id='never-acknowledged'),
        blocks=[CaptureLinkSpec(type='captureLink', conversation_id='never-acknowledged', summary='Capture')],
        account_generation=GENERATION,
        now=NOW,
        firestore_client=firestore,
    )

    for fetch_index in range(intents_db.UNACKNOWLEDGED_FETCH_BUDGET - 1):
        assert intents_db.fetch_ready_intents(
            UID,
            account_generation=GENERATION,
            now=NOW + timedelta(minutes=fetch_index),
            firestore_client=firestore,
        )
    parked = intents_db.fetch_ready_intents(
        UID,
        account_generation=GENERATION,
        now=NOW + timedelta(hours=1),
        firestore_client=firestore,
    )

    assert parked == []
    active_path = ('users', UID, intents_db.INTENTS_COLLECTION, intent.intent_id)
    dead_path = ('users', UID, intents_db.DEAD_LETTERS_COLLECTION, intent.intent_id)
    assert active_path not in firestore.rows
    stored = DeadLetteredProactiveIntent.model_validate(firestore.rows[dead_path])
    assert stored.delivery_state == 'dead_letter'
    assert stored.fetch_count == intents_db.UNACKNOWLEDGED_FETCH_BUDGET
    assert stored.dead_letter_reason == 'unacknowledged_after_fetch_budget'


def test_tail_deferral_never_spends_the_unacknowledged_fetch_budget(firestore):
    deferred, _ = intents_db.create_intent(
        UID,
        source='daily_opener',
        continuity_key='daily:tail-deferred',
        subject=None,
        blocks=[CaptureLinkSpec(type='captureLink', conversation_id='tail-deferred', summary='Deferred')],
        account_generation=GENERATION,
        now=NOW,
        firestore_client=firestore,
    )
    undeferred, _ = intents_db.create_intent(
        UID,
        source='capture_arrival',
        continuity_key='capture:undeferred-sibling',
        subject=ChatFirstSubject(kind='capture', id='undeferred-sibling'),
        blocks=[CaptureLinkSpec(type='captureLink', conversation_id='undeferred-sibling', summary='Sibling')],
        account_generation=GENERATION,
        now=NOW + timedelta(seconds=1),
        firestore_client=firestore,
    )

    for index in range(25):
        request_now = NOW + timedelta(minutes=index)
        # Match the router order exactly: record deferrals and then fetch with
        # the same request timestamp and the current request's deferred IDs.
        intents_db.record_materialization_deferral(
            UID,
            intent_id=deferred.intent_id,
            account_generation=GENERATION,
            now=request_now,
            firestore_client=firestore,
        )
        batch = intents_db.fetch_ready_intent_batch(
            UID,
            account_generation=GENERATION,
            deferred_intent_ids={deferred.intent_id},
            now=request_now,
            firestore_client=firestore,
        )
        assert deferred.intent_id in [item.intent_id for item in batch.intents]

    stored_deferred = intents_db._intent_from_snapshot(
        intents_db._intent_ref(UID, deferred.intent_id, firestore_client=firestore).get()
    )
    stored_undeferred = intents_db._intent_from_snapshot(
        _Snapshot(firestore, ('users', UID, intents_db.DEAD_LETTERS_COLLECTION, undeferred.intent_id))
    )
    assert stored_deferred.delivery_state == 'ready'
    assert stored_deferred.fetch_count == 0
    assert stored_deferred.last_fetched_at is None
    assert stored_undeferred.delivery_state == 'dead_letter'
    assert stored_undeferred.fetch_count == intents_db.UNACKNOWLEDGED_FETCH_BUDGET


def test_deferred_old_intent_does_not_stall_but_never_fetched_old_intent_does(firestore):
    deferred, _ = intents_db.create_intent(
        UID,
        source='daily_opener',
        continuity_key='daily:old-deferred',
        subject=None,
        blocks=[CaptureLinkSpec(type='captureLink', conversation_id='old-deferred', summary='Deferred')],
        account_generation=GENERATION,
        now=NOW - timedelta(hours=25),
        firestore_client=firestore,
    )
    intents_db.record_materialization_deferral(
        UID,
        intent_id=deferred.intent_id,
        account_generation=GENERATION,
        now=NOW - timedelta(hours=1),
        firestore_client=firestore,
    )
    intents_db.create_intent(
        UID,
        source='capture_arrival',
        continuity_key='capture:fresh',
        subject=ChatFirstSubject(kind='capture', id='fresh'),
        blocks=[CaptureLinkSpec(type='captureLink', conversation_id='fresh', summary='Fresh')],
        account_generation=GENERATION,
        now=NOW,
        firestore_client=firestore,
    )

    without_stall = intents_db.fetch_ready_intent_batch(
        UID,
        account_generation=GENERATION,
        deferred_intent_ids={deferred.intent_id},
        now=NOW,
        firestore_client=firestore,
    )
    assert without_stall.stalled_source is None

    # Not a capture receipt: one this old is retired rather than left to
    # stall, so the stall clock is shown on a source that still waits.
    intents_db.create_intent(
        UID,
        source='deferral_reraise',
        continuity_key='capture:old-never-fetched',
        subject=ChatFirstSubject(kind='capture', id='old-never-fetched'),
        blocks=[CaptureLinkSpec(type='captureLink', conversation_id='old-never-fetched', summary='Old')],
        account_generation=GENERATION,
        now=NOW - timedelta(hours=25),
        firestore_client=firestore,
    )
    stalled = intents_db.fetch_ready_intent_batch(
        UID, account_generation=GENERATION, now=NOW, firestore_client=firestore
    )
    assert stalled.stalled_source == 'deferral_reraise'


def test_stall_age_restarts_at_last_deferral_but_eventually_pages(firestore):
    recent, _ = intents_db.create_intent(
        UID,
        source='daily_opener',
        continuity_key='daily:recently-deferred',
        subject=None,
        blocks=[CaptureLinkSpec(type='captureLink', conversation_id='recently-deferred', summary='Recent')],
        account_generation=GENERATION,
        now=NOW - timedelta(days=30),
        firestore_client=firestore,
    )
    intents_db.record_materialization_deferral(
        UID,
        intent_id=recent.intent_id,
        account_generation=GENERATION,
        now=NOW - timedelta(hours=1),
        firestore_client=firestore,
    )
    assert (
        intents_db.fetch_ready_intent_batch(
            UID,
            account_generation=GENERATION,
            deferred_intent_ids={recent.intent_id},
            now=NOW,
            firestore_client=firestore,
        ).stalled_source
        is None
    )

    attempt_path = ('users', UID, intents_db.DELIVERY_ATTEMPTS_COLLECTION, recent.intent_id)
    firestore.rows[attempt_path]['last_deferral_at'] = NOW - timedelta(days=30)
    assert (
        intents_db.fetch_ready_intent_batch(
            UID,
            account_generation=GENERATION,
            deferred_intent_ids={recent.intent_id},
            now=NOW,
            firestore_client=firestore,
        ).stalled_source
        == 'daily_opener'
    )


def test_continuous_deferral_dead_letters_at_seven_days_but_not_six(firestore):
    intent, _ = intents_db.create_intent(
        UID,
        source='daily_opener',
        continuity_key='daily:continuous-deferral',
        subject=None,
        blocks=[CaptureLinkSpec(type='captureLink', conversation_id='continuous-deferral', summary='Deferred')],
        account_generation=GENERATION,
        now=NOW,
        firestore_client=firestore,
    )

    first = intents_db.record_materialization_deferral(
        UID,
        intent_id=intent.intent_id,
        account_generation=GENERATION,
        now=NOW,
        firestore_client=firestore,
    )
    six_days = intents_db.record_materialization_deferral(
        UID,
        intent_id=intent.intent_id,
        account_generation=GENERATION,
        now=NOW + timedelta(days=6),
        firestore_client=firestore,
    )
    seven_days = intents_db.record_materialization_deferral(
        UID,
        intent_id=intent.intent_id,
        account_generation=GENERATION,
        now=NOW + timedelta(days=7),
        firestore_client=firestore,
    )

    assert first.first_deferred_at == NOW
    assert six_days.delivery_state == 'ready'
    assert seven_days.delivery_state == 'dead_letter'
    assert seven_days.dead_letter_reason == 'deferred_beyond_budget'
    active_path = ('users', UID, intents_db.INTENTS_COLLECTION, intent.intent_id)
    dead_path = ('users', UID, intents_db.DEAD_LETTERS_COLLECTION, intent.intent_id)
    assert active_path not in firestore.rows
    assert DeadLetteredProactiveIntent.model_validate(firestore.rows[dead_path]).dead_letter_reason == (
        'deferred_beyond_budget'
    )


def test_fetch_candidate_transactions_are_capped_at_twice_the_response_limit(firestore, monkeypatch):
    for index in range(7):
        intents_db.create_intent(
            UID,
            # Not a capture receipt: those collapse to the newest one, and this
            # bound is about the candidate scan rather than that rule.
            source='deferral_reraise',
            continuity_key=f'capture:scan-cap-{index}',
            subject=ChatFirstSubject(kind='capture', id=f'scan-cap-{index}'),
            blocks=[CaptureLinkSpec(type='captureLink', conversation_id=f'scan-cap-{index}', summary='Candidate')],
            account_generation=GENERATION,
            now=NOW + timedelta(seconds=index),
            firestore_client=firestore,
        )
    scanned = []

    def absorb_candidate(uid, intent_id, **kwargs):
        scanned.append(intent_id)
        return None, None

    monkeypatch.setattr(intents_db, '_advance_fetched_intent', absorb_candidate)

    batch = intents_db.fetch_ready_intent_batch(
        UID, account_generation=GENERATION, limit=2, now=NOW + timedelta(minutes=1), firestore_client=firestore
    )

    assert batch.intents == []
    assert len(scanned) == intents_db.FETCH_CANDIDATE_SCAN_MULTIPLIER * 2


def test_fetch_advance_preserves_unknown_newer_revision_fields(firestore):
    intent, _ = intents_db.create_intent(
        UID,
        source='capture_arrival',
        continuity_key='capture:rolling-writer',
        subject=ChatFirstSubject(kind='capture', id='rolling-writer'),
        blocks=[CaptureLinkSpec(type='captureLink', conversation_id='rolling-writer', summary='Rolling')],
        account_generation=GENERATION,
        now=NOW,
        firestore_client=firestore,
    )
    path = ('users', UID, intents_db.INTENTS_COLLECTION, intent.intent_id)
    firestore.rows[path]['newer_revision_field'] = {'keep': True}

    fetched = intents_db.fetch_ready_intents(
        UID, account_generation=GENERATION, now=NOW + timedelta(minutes=1), firestore_client=firestore
    )

    assert fetched[0].fetch_count == 1
    assert firestore.rows[path]['newer_revision_field'] == {'keep': True}


def test_fetch_bookkeeping_stays_in_sibling_doc_and_old_strict_reader_still_parses_intent(firestore):
    intent, _ = intents_db.create_intent(
        UID,
        source='capture_arrival',
        continuity_key='capture:rolling-reader-safe',
        subject=ChatFirstSubject(kind='capture', id='rolling-reader-safe'),
        blocks=[CaptureLinkSpec(type='captureLink', conversation_id='rolling-reader-safe', summary='Safe')],
        account_generation=GENERATION,
        now=NOW,
        firestore_client=firestore,
    )
    intent_path = ('users', UID, intents_db.INTENTS_COLLECTION, intent.intent_id)

    intents_db.fetch_ready_intents(
        UID, account_generation=GENERATION, now=NOW + timedelta(minutes=1), firestore_client=firestore
    )

    assert 'fetch_count' not in firestore.rows[intent_path]
    assert 'last_fetched_at' not in firestore.rows[intent_path]
    _OldStrictProactiveIntent.model_validate(firestore.rows[intent_path])
    attempt_path = ('users', UID, intents_db.DELIVERY_ATTEMPTS_COLLECTION, intent.intent_id)
    assert firestore.rows[attempt_path]['fetch_count'] == 1


def test_ready_intent_remains_old_reader_safe_after_deferrals_and_rejections(firestore):
    intent, _ = intents_db.create_intent(
        UID,
        source='capture_arrival',
        continuity_key='capture:rolling-reader-all-active-writes',
        subject=ChatFirstSubject(kind='capture', id='rolling-reader-all-active-writes'),
        blocks=[
            CaptureLinkSpec(type='captureLink', conversation_id='rolling-reader-all-active-writes', summary='Safe')
        ],
        account_generation=GENERATION,
        now=NOW,
        firestore_client=firestore,
    )
    intent_path = ('users', UID, intents_db.INTENTS_COLLECTION, intent.intent_id)

    intents_db.fetch_ready_intents(
        UID, account_generation=GENERATION, now=NOW + timedelta(minutes=1), firestore_client=firestore
    )
    intents_db.record_materialization_deferral(
        UID,
        intent_id=intent.intent_id,
        account_generation=GENERATION,
        now=NOW + timedelta(minutes=2),
        firestore_client=firestore,
    )
    intents_db.record_materialization_rejection(
        UID,
        intent_id=intent.intent_id,
        code='kernel_materialization_failed',
        account_generation=GENERATION,
        now=NOW + timedelta(minutes=2, seconds=30),
        firestore_client=firestore,
    )
    for minute in (3, 4):
        intents_db.record_materialization_rejection(
            UID,
            intent_id=intent.intent_id,
            code='invalid_intent',
            account_generation=GENERATION,
            now=NOW + timedelta(minutes=minute),
            firestore_client=firestore,
        )
        _OldStrictProactiveIntent.model_validate(firestore.rows[intent_path])

    dead_path = ('users', UID, intents_db.DEAD_LETTERS_COLLECTION, intent.intent_id)
    firestore.rows[dead_path] = firestore.rows.pop(intent_path)
    firestore.rows[dead_path].update(
        delivery_state='dead_letter',
        dead_letter_reason='unacknowledged_after_fetch_budget',
        last_fetched_at=NOW,
        requeue_count=0,
    )
    intents_db.fetch_ready_intents(
        UID,
        account_generation=GENERATION,
        now=NOW + intents_db.TRANSIENT_DEAD_LETTER_REPAIR_AGE + timedelta(minutes=10),
        firestore_client=firestore,
    )
    _OldStrictProactiveIntent.model_validate(firestore.rows[intent_path])
    assert set(firestore.rows[intent_path]) == set(_OldStrictProactiveIntent.model_fields)


def test_fetch_requeues_transient_dead_letter_once_but_never_deterministic_death(firestore):
    transient, _ = intents_db.create_intent(
        UID,
        source='capture_arrival',
        continuity_key='capture:repair-on-fetch',
        subject=ChatFirstSubject(kind='capture', id='repair-on-fetch'),
        blocks=[CaptureLinkSpec(type='captureLink', conversation_id='repair-on-fetch', summary='Repair')],
        account_generation=GENERATION,
        now=NOW,
        firestore_client=firestore,
    )
    transient_path = ('users', UID, intents_db.INTENTS_COLLECTION, transient.intent_id)
    transient_dead_path = ('users', UID, intents_db.DEAD_LETTERS_COLLECTION, transient.intent_id)
    firestore.rows[transient_dead_path] = firestore.rows.pop(transient_path)
    firestore.rows[transient_dead_path].update(
        delivery_state='dead_letter',
        dead_letter_reason='unacknowledged_after_fetch_budget',
        last_fetched_at=NOW,
        requeue_count=0,
    )
    transient_attempt_path = ('users', UID, intents_db.DELIVERY_ATTEMPTS_COLLECTION, transient.intent_id)
    firestore.rows[transient_attempt_path] = {
        'fetch_count': intents_db.UNACKNOWLEDGED_FETCH_BUDGET + 1,
        'last_fetched_at': NOW,
        'requeue_count': 0,
        'first_deferred_at': NOW - timedelta(days=2),
        'last_deferral_at': NOW - timedelta(days=1),
    }
    deterministic_path = ('users', UID, intents_db.DEAD_LETTERS_COLLECTION, 'deterministic-death')
    deterministic = {**firestore.rows[transient_dead_path], 'intent_id': 'deterministic-death'}
    deterministic.update(dead_letter_reason='permanent_rejection:invalid_intent')
    firestore.rows[deterministic_path] = deterministic

    fetched = intents_db.fetch_ready_intents(
        UID,
        account_generation=GENERATION,
        now=NOW + intents_db.TRANSIENT_DEAD_LETTER_REPAIR_AGE,
        firestore_client=firestore,
    )
    assert [item.intent_id for item in fetched] == [transient.intent_id]
    assert fetched[0].requeue_count == 1
    assert firestore.rows[transient_attempt_path]['first_deferred_at'] == NOW - timedelta(days=2)
    assert firestore.rows[transient_attempt_path]['last_deferral_at'] == NOW - timedelta(days=1)
    assert firestore.rows[deterministic_path]['delivery_state'] == 'dead_letter'

    firestore.rows[transient_dead_path] = firestore.rows.pop(transient_path)
    firestore.rows[transient_dead_path].update(
        delivery_state='dead_letter',
        dead_letter_reason=intents_db.TRANSIENT_DEATH_AFTER_REQUEUE_REASON,
        last_fetched_at=NOW,
        requeue_count=1,
    )
    firestore.rows[transient_attempt_path].update(last_fetched_at=NOW, requeue_count=1)
    assert (
        intents_db.fetch_ready_intents(
            UID,
            account_generation=GENERATION,
            now=NOW + timedelta(days=1),
            firestore_client=firestore,
        )
        == []
    )


def test_sibling_point_reads_are_bounded_by_candidate_scan_limit(firestore):
    for index in range(200):
        intents_db.create_intent(
            UID,
            source='capture_arrival',
            continuity_key=f'capture:read-bound:{index}',
            subject=ChatFirstSubject(kind='capture', id=f'read-bound-{index}'),
            blocks=[CaptureLinkSpec(type='captureLink', conversation_id=f'read-bound-{index}', summary='Bounded')],
            account_generation=GENERATION,
            now=NOW + timedelta(seconds=index),
            firestore_client=firestore,
        )

    non_transaction_reads_before = sum(firestore.point_reads.values())
    transaction_reads_before = sum(firestore.transaction_reads.values())
    intents_db.fetch_ready_intent_batch(
        UID, account_generation=GENERATION, limit=8, now=NOW + timedelta(hours=25), firestore_client=firestore
    )
    non_transaction_reads = sum(firestore.point_reads.values()) - non_transaction_reads_before
    transaction_reads = sum(firestore.transaction_reads.values()) - transaction_reads_before
    # One control read plus, for at most 2 * limit candidates, one sibling
    # hydration read and two transactional point reads (intent + sibling).
    read_bound = 1 + (intents_db.FETCH_CANDIDATE_SCAN_MULTIPLIER * 8 * 3)
    assert non_transaction_reads + transaction_reads <= read_bound


def test_transient_dead_letter_repair_scan_is_bounded(firestore, monkeypatch):
    for index in range(100):
        intent, _ = intents_db.create_intent(
            UID,
            source='capture_arrival',
            continuity_key=f'capture:repair-bound:{index}',
            subject=ChatFirstSubject(kind='capture', id=f'repair-bound-{index}'),
            blocks=[CaptureLinkSpec(type='captureLink', conversation_id=f'repair-bound-{index}', summary='Repair')],
            account_generation=GENERATION,
            now=NOW,
            firestore_client=firestore,
        )
        active_path = ('users', UID, intents_db.INTENTS_COLLECTION, intent.intent_id)
        dead_path = ('users', UID, intents_db.DEAD_LETTERS_COLLECTION, intent.intent_id)
        firestore.rows[dead_path] = firestore.rows.pop(active_path)
        firestore.rows[dead_path].update(
            delivery_state='dead_letter',
            dead_letter_reason='unacknowledged_after_fetch_budget',
            last_fetched_at=NOW,
            requeue_count=0,
        )
    scanned = []

    def skip_repair(uid, intent_id, **kwargs):
        scanned.append(intent_id)
        return None

    monkeypatch.setattr(intents_db, '_requeue_transient_dead_letter', skip_repair)
    intents_db.fetch_ready_intent_batch(
        UID, account_generation=GENERATION, limit=8, now=NOW + timedelta(days=1), firestore_client=firestore
    )

    assert len(scanned) == intents_db.FETCH_CANDIDATE_SCAN_MULTIPLIER * 8


def test_repair_query_does_not_starve_repairable_row_behind_requeued_deaths(firestore):
    created = []
    for index in range(20):
        intent, _ = intents_db.create_intent(
            UID,
            # Not a capture receipt: a requeued one past its delivery window is
            # retired, which is a different rule than the one under test here.
            source='deferral_reraise',
            continuity_key=f'capture:repair-starvation:{index}',
            subject=ChatFirstSubject(kind='capture', id=f'repair-starvation-{index}'),
            blocks=[CaptureLinkSpec(type='captureLink', conversation_id=f'repair-{index}', summary='Repair')],
            account_generation=GENERATION,
            now=NOW + timedelta(seconds=index),
            firestore_client=firestore,
        )
        created.append(intent)
    repairable = max(created, key=lambda intent: intent.intent_id)
    for intent in created:
        intent_path = ('users', UID, intents_db.INTENTS_COLLECTION, intent.intent_id)
        dead_path = ('users', UID, intents_db.DEAD_LETTERS_COLLECTION, intent.intent_id)
        attempt_path = ('users', UID, intents_db.DELIVERY_ATTEMPTS_COLLECTION, intent.intent_id)
        requeue_count = 0 if intent == repairable else 1
        firestore.rows[dead_path] = firestore.rows.pop(intent_path)
        firestore.rows[dead_path].update(
            delivery_state='dead_letter',
            dead_letter_reason='unacknowledged_after_fetch_budget',
            last_fetched_at=NOW,
            requeue_count=requeue_count,
        )
        firestore.rows[attempt_path] = {
            'fetch_count': intents_db.UNACKNOWLEDGED_FETCH_BUDGET + 1,
            'last_fetched_at': NOW,
            'requeue_count': requeue_count,
        }

    fetched = intents_db.fetch_ready_intents(
        UID, account_generation=GENERATION, now=NOW + timedelta(days=5), firestore_client=firestore
    )

    assert [intent.intent_id for intent in fetched] == [repairable.intent_id]


def test_repair_scan_skips_young_rows_without_transactions(firestore):
    for index in range(16):
        intent, _ = intents_db.create_intent(
            UID,
            source='capture_arrival',
            continuity_key=f'capture:young-death:{index}',
            subject=ChatFirstSubject(kind='capture', id=f'young-death-{index}'),
            blocks=[CaptureLinkSpec(type='captureLink', conversation_id=f'young-{index}', summary='Young')],
            account_generation=GENERATION,
            now=NOW,
            firestore_client=firestore,
        )
        active_path = ('users', UID, intents_db.INTENTS_COLLECTION, intent.intent_id)
        dead_path = ('users', UID, intents_db.DEAD_LETTERS_COLLECTION, intent.intent_id)
        firestore.rows[dead_path] = firestore.rows.pop(active_path)
        firestore.rows[dead_path].update(
            delivery_state='dead_letter',
            dead_letter_reason='unacknowledged_after_fetch_budget',
            last_fetched_at=NOW,
            requeue_count=0,
        )
    transactions_before = firestore.transaction_count

    batch = intents_db.fetch_ready_intent_batch(
        UID, account_generation=GENERATION, now=NOW + timedelta(hours=1), firestore_client=firestore
    )

    assert batch.intents == []
    assert firestore.transaction_count == transactions_before


def test_repair_query_failure_does_not_block_ready_delivery(firestore, monkeypatch):
    intent, _ = intents_db.create_intent(
        UID,
        source='capture_arrival',
        continuity_key='capture:repair-query-failure',
        subject=ChatFirstSubject(kind='capture', id='repair-query-failure'),
        blocks=[CaptureLinkSpec(type='captureLink', conversation_id='repair-query-failure', summary='Ready')],
        account_generation=GENERATION,
        now=NOW,
        firestore_client=firestore,
    )

    class FailingQuerySpec:
        def build(self, *args, **kwargs):
            raise GoogleAPICallError('index not ready')

    monkeypatch.setattr(
        intents_db.delivery_attempts, 'CHAT_FIRST_TRANSIENT_DEAD_LETTER_REPAIR_QUERY', FailingQuerySpec()
    )
    batch = intents_db.fetch_ready_intent_batch(
        UID, account_generation=GENERATION, now=NOW + timedelta(minutes=1), firestore_client=firestore
    )

    assert [item.intent_id for item in batch.intents] == [intent.intent_id]
    assert batch.lifecycle_events[0].event == 'repair_scan_failed'


def test_null_ordered_dead_letters_do_not_hide_repairable_reason(firestore):
    for index in range(2):
        path = ('users', UID, intents_db.DEAD_LETTERS_COLLECTION, f'null-terminal-{index}')
        firestore.rows[path] = {
            'account_generation': GENERATION,
            'requeue_count': 0,
            'dead_letter_reason': 'permanent_rejection:invalid_intent',
            'last_fetched_at': None,
        }
    repairable, _ = intents_db.create_intent(
        UID,
        source='capture_arrival',
        continuity_key='capture:null-order-repairable',
        subject=ChatFirstSubject(kind='capture', id='null-order-repairable'),
        blocks=[CaptureLinkSpec(type='captureLink', conversation_id='null-order-repairable', summary='Repair')],
        account_generation=GENERATION,
        now=NOW,
        firestore_client=firestore,
    )
    active_path = ('users', UID, intents_db.INTENTS_COLLECTION, repairable.intent_id)
    dead_path = ('users', UID, intents_db.DEAD_LETTERS_COLLECTION, repairable.intent_id)
    firestore.rows[dead_path] = firestore.rows.pop(active_path)
    firestore.rows[dead_path].update(
        delivery_state='dead_letter',
        dead_letter_reason='unacknowledged_after_fetch_budget',
        fetch_count=intents_db.UNACKNOWLEDGED_FETCH_BUDGET,
        last_fetched_at=NOW,
        requeue_count=0,
    )

    fetched = intents_db.fetch_ready_intents(
        UID, account_generation=GENERATION, limit=1, now=NOW + timedelta(days=1), firestore_client=firestore
    )
    assert [intent.intent_id for intent in fetched] == [repairable.intent_id]


def test_fake_order_by_sorts_explicit_nulls_first_and_drops_missing(firestore):
    paths = [
        ('users', UID, intents_db.DEAD_LETTERS_COLLECTION, 'null-a'),
        ('users', UID, intents_db.DEAD_LETTERS_COLLECTION, 'null-b'),
        ('users', UID, intents_db.DEAD_LETTERS_COLLECTION, 'timestamped'),
        ('users', UID, intents_db.DEAD_LETTERS_COLLECTION, 'missing'),
    ]
    firestore.rows[paths[0]] = {'last_fetched_at': None}
    firestore.rows[paths[1]] = {'last_fetched_at': None}
    firestore.rows[paths[2]] = {'last_fetched_at': NOW}
    firestore.rows[paths[3]] = {}

    ordered = _FilteredCollection([_Snapshot(firestore, path) for path in paths]).order_by('last_fetched_at').stream()

    assert [snapshot.id for snapshot in ordered] == ['null-a', 'null-b', 'timestamped']


def test_twice_dead_intent_gets_terminal_reason_and_is_never_scanned_again(firestore):
    intent, _ = intents_db.create_intent(
        UID,
        source='capture_arrival',
        continuity_key='capture:twice-dead',
        subject=ChatFirstSubject(kind='capture', id='twice-dead'),
        blocks=[CaptureLinkSpec(type='captureLink', conversation_id='twice-dead', summary='Twice dead')],
        account_generation=GENERATION,
        now=NOW,
        firestore_client=firestore,
    )
    intent_path = ('users', UID, intents_db.INTENTS_COLLECTION, intent.intent_id)
    attempt_path = ('users', UID, intents_db.DELIVERY_ATTEMPTS_COLLECTION, intent.intent_id)
    firestore.rows[attempt_path] = {
        'fetch_count': intents_db.UNACKNOWLEDGED_FETCH_BUDGET,
        'requeue_count': 1,
    }

    assert (
        intents_db.fetch_ready_intents(
            UID, account_generation=GENERATION, now=NOW + timedelta(hours=1), firestore_client=firestore
        )
        == []
    )
    dead_path = ('users', UID, intents_db.DEAD_LETTERS_COLLECTION, intent.intent_id)
    assert intent_path not in firestore.rows
    assert firestore.rows[dead_path]['dead_letter_reason'] == intents_db.TRANSIENT_DEATH_AFTER_REQUEUE_REASON
    assert firestore.rows[dead_path]['requeue_count'] == 1
    transactions_before = firestore.transaction_count

    assert (
        intents_db.fetch_ready_intents(
            UID, account_generation=GENERATION, now=NOW + timedelta(days=5), firestore_client=firestore
        )
        == []
    )
    assert firestore.transaction_count == transactions_before


def test_invalid_rejection_code_is_repaired_and_fetched_with_metric_event(firestore):
    intent, _ = intents_db.create_intent(
        UID,
        source='capture_arrival',
        continuity_key='capture:malformed-attempt',
        subject=ChatFirstSubject(kind='capture', id='malformed-attempt'),
        blocks=[CaptureLinkSpec(type='captureLink', conversation_id='malformed-attempt', summary='Repair')],
        account_generation=GENERATION,
        now=NOW,
        firestore_client=firestore,
    )
    attempt_path = ('users', UID, intents_db.DELIVERY_ATTEMPTS_COLLECTION, intent.intent_id)
    firestore.rows[attempt_path] = {
        'fetch_count': 0,
        'requeue_count': 0,
        'last_rejection_code': 'Bad Code!',
    }

    batch = intents_db.fetch_ready_intent_batch(
        UID, account_generation=GENERATION, now=NOW + timedelta(minutes=1), firestore_client=firestore
    )

    assert [item.intent_id for item in batch.intents] == [intent.intent_id]
    assert firestore.rows[attempt_path]['fetch_count'] == 1
    assert firestore.rows[attempt_path]['requeue_count'] == 0
    assert firestore.rows[attempt_path]['last_rejection_code'] is None
    assert [event.event for event in batch.lifecycle_events] == ['malformed_attempt_reset']


def test_valid_fetch_budget_survives_other_malformed_sibling_field(firestore):
    intent, _ = intents_db.create_intent(
        UID,
        source='capture_arrival',
        continuity_key='capture:malformed-at-budget',
        subject=ChatFirstSubject(kind='capture', id='malformed-at-budget'),
        blocks=[CaptureLinkSpec(type='captureLink', conversation_id='malformed-at-budget', summary='Budget')],
        account_generation=GENERATION,
        now=NOW,
        firestore_client=firestore,
    )
    active_path = ('users', UID, intents_db.INTENTS_COLLECTION, intent.intent_id)
    attempt_path = ('users', UID, intents_db.DELIVERY_ATTEMPTS_COLLECTION, intent.intent_id)
    firestore.rows[attempt_path] = {
        'fetch_count': intents_db.UNACKNOWLEDGED_FETCH_BUDGET - 1,
        'requeue_count': 1,
        'last_rejection_code': 'Bad Code!',
    }

    assert (
        intents_db.fetch_ready_intents(
            UID, account_generation=GENERATION, now=NOW + timedelta(minutes=1), firestore_client=firestore
        )
        == []
    )
    dead_path = ('users', UID, intents_db.DEAD_LETTERS_COLLECTION, intent.intent_id)
    assert active_path not in firestore.rows
    assert firestore.rows[dead_path]['fetch_count'] == intents_db.UNACKNOWLEDGED_FETCH_BUDGET
    assert firestore.rows[dead_path]['requeue_count'] == 1


def test_create_does_not_regenerate_dead_lettered_identity(firestore):
    kwargs = {
        'source': 'capture_arrival',
        'continuity_key': 'capture:dead-letter-conflict',
        'subject': ChatFirstSubject(kind='capture', id='dead-letter-conflict'),
        'blocks': [CaptureLinkSpec(type='captureLink', conversation_id='dead-letter-conflict', summary='Terminal')],
        'account_generation': GENERATION,
        'now': NOW,
        'firestore_client': firestore,
    }
    intent, _ = intents_db.create_intent(UID, **kwargs)
    attempt_path = ('users', UID, intents_db.DELIVERY_ATTEMPTS_COLLECTION, intent.intent_id)
    firestore.rows[attempt_path] = {'fetch_count': intents_db.UNACKNOWLEDGED_FETCH_BUDGET - 1}
    assert (
        intents_db.fetch_ready_intents(
            UID, account_generation=GENERATION, now=NOW + timedelta(minutes=1), firestore_client=firestore
        )
        == []
    )

    existing, created = intents_db.create_intent(UID, **kwargs)

    assert created is False
    assert existing.delivery_state == 'dead_letter'
    assert ('users', UID, intents_db.INTENTS_COLLECTION, intent.intent_id) not in firestore.rows


def test_malformed_fetch_count_on_requeued_intent_fails_closed_at_budget(firestore):
    intent, _ = intents_db.create_intent(
        UID,
        source='capture_arrival',
        continuity_key='capture:malformed-fetch-count',
        subject=ChatFirstSubject(kind='capture', id='malformed-fetch-count'),
        blocks=[CaptureLinkSpec(type='captureLink', conversation_id='malformed-fetch-count', summary='Repair')],
        account_generation=GENERATION,
        now=NOW,
        firestore_client=firestore,
    )
    attempt_path = ('users', UID, intents_db.DELIVERY_ATTEMPTS_COLLECTION, intent.intent_id)
    firestore.rows[attempt_path] = {'fetch_count': 'garbage', 'requeue_count': 1}

    batch = intents_db.fetch_ready_intent_batch(
        UID, account_generation=GENERATION, now=NOW + timedelta(minutes=1), firestore_client=firestore
    )

    assert batch.intents == []
    dead_path = ('users', UID, intents_db.DEAD_LETTERS_COLLECTION, intent.intent_id)
    assert firestore.rows[dead_path]['fetch_count'] == intents_db.UNACKNOWLEDGED_FETCH_BUDGET
    assert firestore.rows[dead_path]['requeue_count'] == 1
    assert firestore.rows[dead_path]['dead_letter_reason'] == intents_db.TRANSIENT_DEATH_AFTER_REQUEUE_REASON


def test_receipt_for_dead_letter_removed_from_old_reader_collection_is_missing(firestore):
    intent, _ = intents_db.create_intent(
        UID,
        source='capture_arrival',
        continuity_key='capture:late-receipt',
        subject=ChatFirstSubject(kind='capture', id='late-receipt'),
        blocks=[CaptureLinkSpec(type='captureLink', conversation_id='late-receipt', summary='Late')],
        account_generation=GENERATION,
        now=NOW,
        firestore_client=firestore,
    )
    active_path = ('users', UID, intents_db.INTENTS_COLLECTION, intent.intent_id)
    dead_path = ('users', UID, intents_db.DEAD_LETTERS_COLLECTION, intent.intent_id)
    firestore.rows[dead_path] = firestore.rows.pop(active_path)
    firestore.rows[dead_path].update(
        delivery_state='dead_letter', dead_letter_reason='unacknowledged_after_fetch_budget'
    )

    with pytest.raises(intents_db.ProactiveIntentNotReady):
        intents_db.acknowledge_materialization(
            UID,
            intent_id=intent.intent_id,
            receipt_id='late-kernel-receipt',
            account_generation=GENERATION,
            now=NOW + timedelta(hours=1),
            firestore_client=firestore,
        )


def test_stale_rejection_is_absorbed_after_other_device_delivery_or_deletion(firestore):
    intent, _ = intents_db.create_intent(
        UID,
        source='capture_arrival',
        continuity_key='capture:stale-rejection',
        subject=ChatFirstSubject(kind='capture', id='stale-rejection'),
        blocks=[CaptureLinkSpec(type='captureLink', conversation_id='stale-rejection', summary='Stale')],
        account_generation=GENERATION,
        now=NOW,
        firestore_client=firestore,
    )
    path = ('users', UID, intents_db.INTENTS_COLLECTION, intent.intent_id)
    firestore.rows[path]['delivery_state'] = 'delivered'
    delivered, reason = intents_db.record_materialization_rejection(
        UID,
        intent_id=intent.intent_id,
        code='kernel_materialization_failed',
        account_generation=GENERATION,
        now=NOW,
        firestore_client=firestore,
    )
    del firestore.rows[path]
    missing, missing_reason = intents_db.record_materialization_rejection(
        UID,
        intent_id=intent.intent_id,
        code='kernel_materialization_failed',
        account_generation=GENERATION,
        now=NOW,
        firestore_client=firestore,
    )

    assert delivered is not None and delivered.delivery_state == 'delivered' and reason is None
    assert missing is None and missing_reason is None


def test_fetch_isolates_malformed_documents_and_transactions_healthy_fetch_updates(firestore):
    healthy, _ = intents_db.create_intent(
        UID,
        source='capture_arrival',
        continuity_key='capture:healthy-batch',
        subject=ChatFirstSubject(kind='capture', id='healthy-batch'),
        blocks=[CaptureLinkSpec(type='captureLink', conversation_id='healthy-batch', summary='Healthy')],
        account_generation=GENERATION,
        now=NOW,
        firestore_client=firestore,
    )
    malformed_path = ('users', UID, intents_db.INTENTS_COLLECTION, 'malformed-ready')
    firestore.rows[malformed_path] = {'delivery_state': 'ready', 'account_generation': GENERATION}
    transactions_before = firestore.transaction_count

    batch = intents_db.fetch_ready_intent_batch(UID, account_generation=GENERATION, now=NOW, firestore_client=firestore)

    assert [item.intent_id for item in batch.intents] == [healthy.intent_id]
    malformed_dead_path = ('users', UID, intents_db.DEAD_LETTERS_COLLECTION, 'malformed-ready')
    assert malformed_path not in firestore.rows
    assert firestore.rows[malformed_dead_path]['delivery_state'] == 'dead_letter'
    assert firestore.rows[malformed_dead_path]['dead_letter_reason'] == 'malformed_document'
    assert firestore.transaction_count == transactions_before + 2


def test_concurrently_deleted_candidate_does_not_abort_fetch_or_other_writes(firestore):
    deleted, _ = intents_db.create_intent(
        UID,
        source='capture_arrival',
        continuity_key='capture:deleted-during-fetch',
        subject=ChatFirstSubject(kind='capture', id='deleted-during-fetch'),
        blocks=[CaptureLinkSpec(type='captureLink', conversation_id='deleted-during-fetch', summary='Deleted')],
        account_generation=GENERATION,
        now=NOW,
        firestore_client=firestore,
    )
    healthy, _ = intents_db.create_intent(
        UID,
        source='capture_arrival',
        continuity_key='capture:survives-peer-delete',
        subject=ChatFirstSubject(kind='capture', id='survives-peer-delete'),
        blocks=[CaptureLinkSpec(type='captureLink', conversation_id='survives-peer-delete', summary='Healthy')],
        account_generation=GENERATION,
        now=NOW + timedelta(seconds=1),
        firestore_client=firestore,
    )
    deleted_path = ('users', UID, intents_db.INTENTS_COLLECTION, deleted.intent_id)

    def delete_during_write():
        firestore.rows.pop(deleted_path)

    firestore.transaction_read_hooks[deleted_path] = delete_during_write

    batch = intents_db.fetch_ready_intent_batch(
        UID, account_generation=GENERATION, now=NOW + timedelta(minutes=1), firestore_client=firestore
    )

    assert [item.intent_id for item in batch.intents] == [healthy.intent_id]
    healthy_path = ('users', UID, intents_db.DELIVERY_ATTEMPTS_COLLECTION, healthy.intent_id)
    assert firestore.rows[healthy_path]['fetch_count'] == 1


def test_dead_letter_transition_never_overwrites_a_concurrent_delivery(firestore):
    intent, _ = intents_db.create_intent(
        UID,
        source='capture_arrival',
        continuity_key='capture:delivered-before-dead-letter',
        subject=ChatFirstSubject(kind='capture', id='delivered-before-dead-letter'),
        blocks=[CaptureLinkSpec(type='captureLink', conversation_id='delivered-before-dead-letter', summary='Race')],
        account_generation=GENERATION,
        now=NOW,
        firestore_client=firestore,
    )
    path = ('users', UID, intents_db.INTENTS_COLLECTION, intent.intent_id)
    attempt_path = ('users', UID, intents_db.DELIVERY_ATTEMPTS_COLLECTION, intent.intent_id)
    firestore.rows[attempt_path] = {'fetch_count': intents_db.UNACKNOWLEDGED_FETCH_BUDGET}

    def deliver_concurrently():
        firestore.rows[path]['delivery_state'] = 'delivered'
        firestore.rows[path]['materialization_receipt_id'] = 'other-device-receipt'

    firestore.transaction_read_hooks[path] = deliver_concurrently

    batch = intents_db.fetch_ready_intent_batch(
        UID, account_generation=GENERATION, now=NOW + timedelta(minutes=1), firestore_client=firestore
    )

    assert batch.intents == []
    assert firestore.rows[path]['delivery_state'] == 'delivered'
    assert firestore.rows[path]['materialization_receipt_id'] == 'other-device-receipt'


def test_two_interleaved_device_fetches_increment_fetch_count_twice(firestore):
    intent, _ = intents_db.create_intent(
        UID,
        source='capture_arrival',
        continuity_key='capture:two-device-fetch',
        subject=ChatFirstSubject(kind='capture', id='two-device-fetch'),
        blocks=[CaptureLinkSpec(type='captureLink', conversation_id='two-device-fetch', summary='Two devices')],
        account_generation=GENERATION,
        now=NOW,
        firestore_client=firestore,
    )
    path = ('users', UID, intents_db.INTENTS_COLLECTION, intent.intent_id)
    attempt_path = ('users', UID, intents_db.DELIVERY_ATTEMPTS_COLLECTION, intent.intent_id)

    def second_device_fetch():
        intents_db.fetch_ready_intent_batch(
            UID,
            account_generation=GENERATION,
            now=NOW + timedelta(seconds=1),
            firestore_client=firestore,
        )

    firestore.transaction_read_hooks[path] = second_device_fetch
    intents_db.fetch_ready_intent_batch(
        UID, account_generation=GENERATION, now=NOW + timedelta(seconds=2), firestore_client=firestore
    )

    assert firestore.rows[attempt_path]['fetch_count'] == 2


def test_fetch_isolates_one_advance_failure_from_the_healthy_batch(firestore, monkeypatch):
    failing, _ = intents_db.create_intent(
        UID,
        source='capture_arrival',
        continuity_key='capture:advance-failure',
        subject=ChatFirstSubject(kind='capture', id='advance-failure'),
        blocks=[CaptureLinkSpec(type='captureLink', conversation_id='advance-failure', summary='Failing')],
        account_generation=GENERATION,
        now=NOW,
        firestore_client=firestore,
    )
    healthy, _ = intents_db.create_intent(
        UID,
        source='capture_arrival',
        continuity_key='capture:after-advance-failure',
        subject=ChatFirstSubject(kind='capture', id='after-advance-failure'),
        blocks=[CaptureLinkSpec(type='captureLink', conversation_id='after-advance-failure', summary='Healthy')],
        account_generation=GENERATION,
        now=NOW + timedelta(seconds=1),
        firestore_client=firestore,
    )
    failing_path = ('users', UID, intents_db.INTENTS_COLLECTION, failing.intent_id)
    firestore.rows[failing_path]['fetch_count'] = 2
    firestore.rows[('users', UID, 'messages', intents_db._stable_chat_first_turn_id(failing.intent_id))] = {
        'metadata': '{"chatFirstIntentId":"' + failing.intent_id + '"}'
    }
    advance = intents_db._advance_fetched_intent

    def fail_one_advance(uid, intent_id, **kwargs):
        if intent_id == failing.intent_id:
            raise RuntimeError('isolated advance failure')
        return advance(uid, intent_id, **kwargs)

    monkeypatch.setattr(intents_db, '_advance_fetched_intent', fail_one_advance)

    batch = intents_db.fetch_ready_intent_batch(
        UID, account_generation=GENERATION, now=NOW + timedelta(minutes=1), firestore_client=firestore
    )

    assert [item.intent_id for item in batch.intents] == [healthy.intent_id]


def test_stored_intent_model_tolerates_new_fields_and_unknown_terminal_state():
    payload = {
        'intent_id': 'intent-rolling-deploy',
        'continuity_key': 'rolling-deploy',
        'account_generation': GENERATION,
        'source': 'capture_arrival',
        'blocks': [{'type': 'captureLink', 'conversation_id': 'capture-1', 'summary': 'Capture'}],
        'delivery_state': 'future_terminal_state',
        'created_at': NOW,
        'last_deferral_at': NOW,
        'newer_revision_field': True,
    }

    parsed = intents_db.ProactiveIntent.model_validate(payload)

    assert parsed.delivery_state == 'dead_letter'


def test_stable_chat_first_turn_identity_matches_the_kernel_shared_vector():
    assert intents_db._stable_chat_first_turn_id('intent-shared-vector') == 'turn_cfi_df211fb1b31c4b849c6bb6b2'


def test_fetch_reconciles_a_stable_chat_row_and_acknowledges_a_late_real_receipt(firestore):
    intent, _ = intents_db.create_intent(
        UID,
        source='capture_arrival',
        continuity_key='capture:reconciled',
        subject=ChatFirstSubject(kind='capture', id='reconciled'),
        blocks=[CaptureLinkSpec(type='captureLink', conversation_id='reconciled', summary='Capture')],
        account_generation=GENERATION,
        now=NOW,
        firestore_client=firestore,
    )
    first = intents_db.fetch_ready_intents(UID, account_generation=GENERATION, now=NOW, firestore_client=firestore)
    turn_id = intents_db._stable_chat_first_turn_id(intent.intent_id)
    firestore.rows[('users', UID, 'messages', turn_id)] = {
        'metadata': '{"chatFirstIntentId":"' + intent.intent_id + '"}'
    }

    # Reconciliation point reads begin only after the second unacknowledged
    # delivery, avoiding a read on every ordinary poll.
    second = intents_db.fetch_ready_intents(
        UID, account_generation=GENERATION, now=NOW + timedelta(seconds=30), firestore_client=firestore
    )
    assert second

    batch = intents_db.fetch_ready_intent_batch(
        UID,
        account_generation=GENERATION,
        now=NOW + timedelta(minutes=1),
        firestore_client=firestore,
    )

    assert [item.intent_id for item in first] == [intent.intent_id]
    assert batch.intents == []
    assert batch.lifecycle_events == (
        intents_db.IntentLifecycleEvent('reconciled', 'capture_arrival', 'existing_chat_row'),
    )
    stored = intents_db._intent_with_delivery_attempt(
        intents_db._intent_from_snapshot(
            intents_db._intent_ref(UID, intent.intent_id, firestore_client=firestore).get()
        ),
        intents_db._delivery_attempt_ref(UID, intent.intent_id, firestore_client=firestore).get(),
    )
    assert stored.delivery_state == 'delivered'
    assert stored.materialization_receipt_id.startswith('cfi_reconciled_')

    acknowledged = intents_db.acknowledge_materialization(
        UID,
        intent_id=intent.intent_id,
        receipt_id='late-real-kernel-receipt',
        account_generation=GENERATION,
        now=NOW + timedelta(minutes=2),
        firestore_client=firestore,
    )
    assert acknowledged == stored


def test_two_distinct_real_materialization_receipts_conflict(firestore):
    intent, _ = intents_db.create_intent(
        UID,
        source='capture_arrival',
        continuity_key='capture:real-receipt-conflict',
        subject=ChatFirstSubject(kind='capture', id='real-receipt-conflict'),
        blocks=[CaptureLinkSpec(type='captureLink', conversation_id='real-receipt-conflict', summary='Capture')],
        account_generation=GENERATION,
        now=NOW,
        firestore_client=firestore,
    )
    intents_db.acknowledge_materialization(
        UID,
        intent_id=intent.intent_id,
        receipt_id='first-real-receipt',
        account_generation=GENERATION,
        now=NOW,
        firestore_client=firestore,
    )

    with pytest.raises(intents_db.ChatFirstIntentConflictError):
        intents_db.acknowledge_materialization(
            UID,
            intent_id=intent.intent_id,
            receipt_id='second-real-receipt',
            account_generation=GENERATION,
            now=NOW + timedelta(seconds=1),
            firestore_client=firestore,
        )


def test_fetch_orders_daily_and_meeting_intents_ahead_of_capture_link_backlog(firestore):
    for index in range(9):
        intents_db.create_intent(
            UID,
            source='capture_arrival',
            continuity_key=f'capture:backlog:{index}',
            subject=ChatFirstSubject(kind='capture', id=f'backlog-{index}'),
            blocks=[CaptureLinkSpec(type='captureLink', conversation_id=f'backlog-{index}', summary='Capture')],
            account_generation=GENERATION,
            now=NOW + timedelta(seconds=index),
            firestore_client=firestore,
        )
    daily, _ = intents_db.create_intent(
        UID,
        source='daily_opener',
        continuity_key='daily:priority',
        subject=None,
        blocks=[CaptureLinkSpec(type='captureLink', conversation_id='daily-priority', summary='Daily')],
        account_generation=GENERATION,
        now=NOW + timedelta(minutes=10),
        firestore_client=firestore,
    )
    meeting, _ = intents_db.create_intent(
        UID,
        source='capture_arrival',
        continuity_key='meeting:priority',
        subject=ChatFirstSubject(kind='capture', id='meeting-priority'),
        blocks=[
            ConversationLinkSpec(
                type='conversationLink', conversation_id='meeting-priority', summary='Meeting notes ready'
            )
        ],
        account_generation=GENERATION,
        now=NOW + timedelta(minutes=11),
        firestore_client=firestore,
    )

    batch = intents_db.fetch_ready_intent_batch(
        UID, account_generation=GENERATION, now=NOW + timedelta(days=2), firestore_client=firestore
    )

    # The daily opener and the meeting-notes intent keep their priority, and the
    # nine-deep capture backlog no longer follows them into the transcript: the
    # newest receipt is two days old, so every one of them is retired.
    assert [intent.intent_id for intent in batch.intents] == [daily.intent_id, meeting.intent_id]
    # The stall clock now pages on the opener, which is the one row still
    # waiting past the boundary rather than being retired at it.
    assert batch.stalled_source == 'daily_opener'
    dead_reasons = {
        row['dead_letter_reason']
        for path, row in firestore.rows.items()
        if path[2] == intents_db.DEAD_LETTERS_COLLECTION
    }
    assert dead_reasons == {
        intents_db.SUPERSEDED_CAPTURE_DEAD_LETTER_REASON,
        intents_db.STALE_CAPTURE_DEAD_LETTER_REASON,
    }


def _capture_receipt(firestore, key: str, *, created_at):
    intent, _ = intents_db.create_intent(
        UID,
        source='capture_arrival',
        continuity_key=f'capture:{key}',
        subject=ChatFirstSubject(kind='capture', id=key),
        blocks=[CaptureLinkSpec(type='captureLink', conversation_id=key, summary=f'Conversation {key}')],
        account_generation=GENERATION,
        now=created_at,
        firestore_client=firestore,
    )
    return intent


def _dead_letter_reason(firestore, intent_id: str) -> str | None:
    row = firestore.rows.get(('users', UID, intents_db.DEAD_LETTERS_COLLECTION, intent_id))
    return None if row is None else row['dead_letter_reason']


def test_capture_receipt_backlog_collapses_to_the_newest_live_receipt(firestore):
    """One conversation card, not the run of them a closed Chat used to accrue."""

    receipts = [
        _capture_receipt(firestore, f'backlog-{index}', created_at=NOW + timedelta(minutes=index)) for index in range(5)
    ]

    batch = intents_db.fetch_ready_intent_batch(
        UID, account_generation=GENERATION, now=NOW + timedelta(minutes=10), firestore_client=firestore
    )

    assert [intent.intent_id for intent in batch.intents] == [receipts[-1].intent_id]
    assert {_dead_letter_reason(firestore, intent.intent_id) for intent in receipts[:-1]} == {
        intents_db.SUPERSEDED_CAPTURE_DEAD_LETTER_REASON
    }
    assert [event.event for event in batch.lifecycle_events] == ['retired'] * 4
    # The surviving receipt is delivered, not parked for a later poll.
    assert ('users', UID, intents_db.INTENTS_COLLECTION, receipts[-1].intent_id) in firestore.rows


def test_capture_receipt_past_its_delivery_window_is_retired_rather_than_delivered(firestore):
    stale = _capture_receipt(
        firestore, 'stale', created_at=NOW - intents_db.CAPTURE_RECEIPT_DELIVERY_WINDOW - timedelta(minutes=1)
    )

    assert (
        intents_db.fetch_ready_intent_batch(
            UID, account_generation=GENERATION, now=NOW, firestore_client=firestore
        ).intents
        == []
    )
    assert _dead_letter_reason(firestore, stale.intent_id) == intents_db.STALE_CAPTURE_DEAD_LETTER_REASON

    live = _capture_receipt(
        firestore, 'live', created_at=NOW - intents_db.CAPTURE_RECEIPT_DELIVERY_WINDOW + timedelta(minutes=1)
    )
    delivered = intents_db.fetch_ready_intent_batch(
        UID, account_generation=GENERATION, now=NOW, firestore_client=firestore
    )
    assert [intent.intent_id for intent in delivered.intents] == [live.intent_id]


def test_meeting_notes_intents_keep_their_own_delivery_contract(firestore):
    """``conversationLink`` shares the source but is not a per-conversation receipt."""

    meetings = []
    for index in range(2):
        intent, _ = intents_db.create_intent(
            UID,
            source='capture_arrival',
            continuity_key=f'meeting:{index}',
            subject=ChatFirstSubject(kind='capture', id=f'meeting-{index}'),
            blocks=[
                ConversationLinkSpec(
                    type='conversationLink', conversation_id=f'meeting-{index}', summary='Meeting notes ready'
                )
            ],
            account_generation=GENERATION,
            now=NOW + timedelta(minutes=index),
            firestore_client=firestore,
        )
        meetings.append(intent)

    batch = intents_db.fetch_ready_intent_batch(
        UID, account_generation=GENERATION, now=NOW + timedelta(days=30), firestore_client=firestore
    )

    assert {intent.intent_id for intent in batch.intents} == {intent.intent_id for intent in meetings}


def test_a_capture_receipt_awaiting_its_kernel_receipt_is_never_retired(firestore):
    """The kernel already wrote that row; retiring it would strand its receipt."""

    pending = _capture_receipt(firestore, 'pending', created_at=NOW - timedelta(days=30))
    newer = _capture_receipt(firestore, 'newer', created_at=NOW)
    firestore.rows[('users', UID, intents_db.INTENTS_COLLECTION, pending.intent_id)][
        'delivery_state'
    ] = 'pending_kernel_receipt'

    batch = intents_db.fetch_ready_intent_batch(UID, account_generation=GENERATION, now=NOW, firestore_client=firestore)

    assert _dead_letter_reason(firestore, pending.intent_id) is None
    assert {intent.intent_id for intent in batch.intents} == {pending.intent_id, newer.intent_id}


def test_a_capture_receipt_a_kernel_already_holds_is_not_superseded(firestore):
    """A fetch leaves a normal intent ``ready`` -- only the sibling attempt row moves.

    So ``ready`` alone does not mean undelivered, and superseding on it would
    delete a row out from under the kernel that is about to acknowledge it.
    """

    in_flight = _capture_receipt(firestore, 'in-flight', created_at=NOW)
    first = intents_db.fetch_ready_intent_batch(
        UID, account_generation=GENERATION, now=NOW + timedelta(minutes=1), firestore_client=firestore
    )
    assert [intent.intent_id for intent in first.intents] == [in_flight.intent_id]
    assert (
        firestore.rows[('users', UID, intents_db.INTENTS_COLLECTION, in_flight.intent_id)]['delivery_state'] == 'ready'
    )

    newer = _capture_receipt(firestore, 'newer', created_at=NOW + timedelta(minutes=2))
    second = intents_db.fetch_ready_intent_batch(
        UID, account_generation=GENERATION, now=NOW + timedelta(minutes=3), firestore_client=firestore
    )

    assert _dead_letter_reason(firestore, in_flight.intent_id) is None
    assert {intent.intent_id for intent in second.intents} == {in_flight.intent_id, newer.intent_id}
    # The unacknowledged-fetch budget, not this rule, is what terminalizes it.
    assert (
        firestore.rows[('users', UID, intents_db.DELIVERY_ATTEMPTS_COLLECTION, in_flight.intent_id)]['fetch_count'] == 2
    )


def test_a_retired_receipt_keeps_its_delivery_attempt_history(firestore):
    """The terminal record is written from the hydrated intent, not the bare row."""

    superseded = _capture_receipt(firestore, 'superseded', created_at=NOW)
    _capture_receipt(firestore, 'newest', created_at=NOW + timedelta(minutes=1))
    deferred_at = NOW - timedelta(hours=2)
    firestore.rows[('users', UID, intents_db.DELIVERY_ATTEMPTS_COLLECTION, superseded.intent_id)] = {
        'fetch_count': 0,
        'first_deferred_at': deferred_at,
        'last_deferral_at': deferred_at,
    }

    intents_db.fetch_ready_intent_batch(
        UID, account_generation=GENERATION, now=NOW + timedelta(minutes=2), firestore_client=firestore
    )

    dead = DeadLetteredProactiveIntent.model_validate(
        firestore.rows[('users', UID, intents_db.DEAD_LETTERS_COLLECTION, superseded.intent_id)]
    )
    assert dead.dead_letter_reason == intents_db.SUPERSEDED_CAPTURE_DEAD_LETTER_REASON
    assert dead.first_deferred_at == deferred_at
    assert dead.last_deferral_at == deferred_at


def test_capture_retirement_writes_stay_bounded_on_one_poll(firestore):
    limit = 2
    for index in range(4 * intents_db.FETCH_CANDIDATE_SCAN_MULTIPLIER * limit):
        _capture_receipt(firestore, f'flood-{index:03d}', created_at=NOW + timedelta(seconds=index))
    transactions_before = firestore.transaction_count

    batch = intents_db.fetch_ready_intent_batch(
        UID,
        account_generation=GENERATION,
        limit=limit,
        now=NOW + timedelta(minutes=1),
        firestore_client=firestore,
    )

    # Everything but the newest is excluded from the response on this poll even
    # though only a bounded number of them can be retired by it.
    assert len(batch.intents) == 1
    retired = sum(1 for event in batch.lifecycle_events if event.event == 'retired')
    assert retired == intents_db.FETCH_CANDIDATE_SCAN_MULTIPLIER * limit
    assert firestore.transaction_count - transactions_before <= 2 * intents_db.FETCH_CANDIDATE_SCAN_MULTIPLIER * limit


def test_stall_scan_includes_old_low_priority_intent_below_response_window(firestore):
    for index in range(20):
        intents_db.create_intent(
            UID,
            source='daily_opener',
            continuity_key=f'daily:fresh-priority:{index}',
            subject=None,
            blocks=[CaptureLinkSpec(type='captureLink', conversation_id=f'fresh-{index}', summary='Fresh')],
            account_generation=GENERATION,
            now=NOW + timedelta(seconds=index),
            firestore_client=firestore,
        )
    # Not a capture receipt: one this old is retired instead of stalling.
    old, _ = intents_db.create_intent(
        UID,
        source='deferral_reraise',
        continuity_key='capture:old-low-priority',
        subject=ChatFirstSubject(kind='capture', id='old-low-priority'),
        blocks=[CaptureLinkSpec(type='captureLink', conversation_id='old-low-priority', summary='Old')],
        account_generation=GENERATION,
        now=NOW - timedelta(days=30),
        firestore_client=firestore,
    )

    batch = intents_db.fetch_ready_intent_batch(
        UID, account_generation=GENERATION, limit=8, now=NOW + timedelta(minutes=1), firestore_client=firestore
    )

    assert old.intent_id not in {intent.intent_id for intent in batch.intents}
    assert batch.stalled_source == 'deferral_reraise'


def test_cold_start_generation_retries_one_pending_intent_until_its_kernel_receipt(firestore):
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
        firestore_client=firestore,
    )
    retried, retry_created = intents_db.get_or_create_cold_start_intent(
        UID,
        source='cold_start_rich',
        continuity_key=sequence_id,
        subject=ChatFirstSubject(kind='goal', id='goal-1'),
        blocks=[CaptureLinkSpec(type='captureLink', conversation_id='capture-1', summary='Ignored retry shape')],
        account_generation=GENERATION,
        now=NOW + timedelta(minutes=1),
        firestore_client=firestore,
    )

    assert created is True
    assert retry_created is False
    assert retried == first
    assert first.delivery_state == 'pending_kernel_receipt'
    assert (
        intents_db.has_active_sparse_cold_start_sequence(UID, account_generation=GENERATION, firestore_client=firestore)
        is True
    )
    fetched = intents_db.fetch_ready_intents(UID, account_generation=GENERATION, now=NOW, firestore_client=firestore)
    assert fetched == [first.model_copy(update={'fetch_count': 1, 'last_fetched_at': NOW})]
    delivered = intents_db.acknowledge_materialization(
        UID,
        intent_id=first.intent_id,
        receipt_id='kernel-receipt-1',
        account_generation=GENERATION,
        now=NOW,
        firestore_client=firestore,
    )

    assert delivered.delivery_state == 'delivered'
    assert (
        intents_db.has_active_sparse_cold_start_sequence(UID, account_generation=GENERATION, firestore_client=firestore)
        is True
    )
    terminalized = intents_db.acknowledge_sparse_cold_start_sequence_terminal(
        UID,
        sequence_id=sequence_id,
        receipt_id='sequence-terminal-receipt-1',
        terminal_state='abandoned',
        account_generation=GENERATION,
        now=NOW + timedelta(seconds=1),
        firestore_client=firestore,
    )
    assert terminalized.cold_start_sequence_terminal_state == 'abandoned'
    assert terminalized.cold_start_sequence_terminal_receipt_id == 'sequence-terminal-receipt-1'
    assert (
        intents_db.has_active_sparse_cold_start_sequence(UID, account_generation=GENERATION, firestore_client=firestore)
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
            firestore_client=firestore,
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
            firestore_client=firestore,
        )
    with pytest.raises(intents_db.ChatFirstIntentConflictError):
        intents_db.acknowledge_materialization(
            UID,
            intent_id=first.intent_id,
            receipt_id='different-kernel-receipt',
            account_generation=GENERATION,
            now=NOW + timedelta(seconds=1),
            firestore_client=firestore,
        )
    assert intents_db.fetch_ready_intents(UID, account_generation=GENERATION, firestore_client=firestore) == []


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
        ).intents
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

    assert len(due.intents) == 1
    assert due.intents[0].source == 'deferral_reraise'
    released_question = due.intents[0].blocks[0]
    assert released_question.question_id != question.question_id
    assert released_question.model_copy(update={'question_id': question.question_id}) == question
    assert replay.intents == []

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

    assert len(subject_change.intents) == 1
    assert (
        subject_change.intents[0].blocks[0].model_copy(update={'question_id': task_question.question_id})
        == task_question
    )
    assert subject_change.intents[0].blocks[0].question_id != task_question.question_id


def test_malformed_deferral_row_does_not_block_healthy_release_or_fetch(firestore):
    question = _question()
    intents_db.record_deferral(
        UID,
        continuity_key='healthy-due-deferral',
        subject=question.subject,
        question=question,
        account_generation=GENERATION,
        now=NOW,
        firestore_client=firestore,
    )
    firestore.rows[('users', UID, intents_db.DEFERRALS_COLLECTION, 'malformed-due')] = {
        'account_generation': GENERATION,
        'state': 'pending',
        'due_at': NOW,
    }

    released = intents_db.release_due_deferrals(
        UID,
        account_generation=GENERATION,
        now=NOW + timedelta(days=1),
        firestore_client=firestore,
    )
    fetched = intents_db.fetch_ready_intents(
        UID,
        account_generation=GENERATION,
        now=NOW + timedelta(days=1),
        firestore_client=firestore,
    )

    assert released.malformed_count == 1
    assert len(released.intents) == 1
    assert [intent.intent_id for intent in fetched] == [released.intents[0].intent_id]


def test_malformed_deferral_terminalization_failure_is_counted_and_logs_document_id(firestore, monkeypatch, caplog):
    firestore.rows[('users', UID, intents_db.DEFERRALS_COLLECTION, 'malformed-warning-id')] = {
        'account_generation': GENERATION,
        'state': 'pending',
        'due_at': NOW,
    }

    def fail_terminalization(*args, **kwargs):
        raise RuntimeError('private failure detail')

    monkeypatch.setattr(intents_db, '_terminalize_malformed_deferral', fail_terminalization)
    with caplog.at_level('WARNING', logger=intents_db.__name__):
        released = intents_db.release_due_deferrals(
            UID,
            account_generation=GENERATION,
            now=NOW + timedelta(days=1),
            firestore_client=firestore,
        )

    assert released.malformed_count == 1
    assert 'id=malformed-warning-id' in caplog.text
    assert 'private failure detail' not in caplog.text


def test_thirty_three_malformed_deferrals_ahead_of_valid_due_row_are_terminalized(firestore):
    question = _question()
    receipt, _ = intents_db.record_deferral(
        UID,
        continuity_key='valid-after-malformed-head',
        subject=question.subject,
        question=question,
        account_generation=GENERATION,
        now=NOW,
        firestore_client=firestore,
    )
    malformed_paths = []
    for index in range(33):
        path = ('users', UID, intents_db.DEFERRALS_COLLECTION, f'000-malformed-{index:02d}')
        malformed_paths.append(path)
        firestore.rows[path] = {
            'account_generation': GENERATION,
            'state': 'pending',
            'due_at': NOW,
        }

    released = intents_db.release_due_deferrals(
        UID,
        account_generation=GENERATION,
        now=NOW + timedelta(days=1),
        firestore_client=firestore,
    )

    assert released.malformed_count == 33
    assert len(released.intents) == 1
    assert all(firestore.rows[path]['state'] == 'released' for path in malformed_paths)
    assert receipt.state == 'pending'


def test_materialization_deferral_rejects_stale_generation_without_writing(firestore):
    intent, _ = intents_db.create_intent(
        UID,
        source='capture_arrival',
        continuity_key='capture:stale-deferral-fence',
        subject=ChatFirstSubject(kind='capture', id='stale-deferral-fence'),
        blocks=[CaptureLinkSpec(type='captureLink', conversation_id='stale-deferral-fence', summary='Fence')],
        account_generation=GENERATION,
        now=NOW,
        firestore_client=firestore,
    )
    path = ('users', UID, intents_db.INTENTS_COLLECTION, intent.intent_id)
    before = deepcopy(firestore.rows[path])
    firestore.rows[('users', UID, 'task_intelligence_control', 'state')]['account_generation'] = GENERATION + 1

    with pytest.raises(intents_db.ChatFirstIntentGenerationMismatch):
        intents_db.record_materialization_deferral(
            UID,
            intent_id=intent.intent_id,
            account_generation=GENERATION,
            now=NOW + timedelta(minutes=1),
            firestore_client=firestore,
        )

    assert firestore.rows[path] == before


def test_workflow_mode_cannot_suppress_intent_but_stale_generation_still_rejects(firestore):
    firestore.rows[('users', UID, 'task_intelligence_control', 'state')] = TaskWorkflowControl(
        workflow_mode=TaskWorkflowMode.off,
        account_generation=GENERATION,
    ).persisted_payload()
    question = _question()

    intent, created = intents_db.create_intent(
        UID,
        source='agent_judgment',
        continuity_key='workflow-mode-is-metadata',
        subject=question.subject,
        blocks=[question],
        account_generation=GENERATION,
        now=NOW,
        firestore_client=firestore,
    )

    assert created is True
    assert intent.account_generation == GENERATION
    firestore.rows[('users', UID, 'task_intelligence_control', 'state')] = TaskWorkflowControl(
        workflow_mode=TaskWorkflowMode.off,
        account_generation=GENERATION + 1,
    ).persisted_payload()

    with pytest.raises(intents_db.ChatFirstIntentGenerationMismatch):
        intents_db.create_intent(
            UID,
            source='agent_judgment',
            continuity_key='stale-generation',
            subject=question.subject,
            blocks=[question],
            account_generation=GENERATION,
            now=NOW,
            firestore_client=firestore,
        )

    assert sum(INTENTS_COLLECTION in path for path in firestore.rows) == 1


def test_malformed_control_or_proactive_state_fails_closed_without_a_fail_open_drop(firestore):
    question = _question()
    malformed_control_path = ('users', UID, 'task_intelligence_control', 'state')
    firestore.rows[malformed_control_path]['unexpected_legacy_field'] = True

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
                firestore_client=firestore,
            )

    fallback.assert_not_called()
    assert not any(INTENTS_COLLECTION in path or DEFERRALS_COLLECTION in path for path in firestore.rows)


def test_malformed_intent_cannot_be_materialized_or_overwritten(firestore):
    path = ('users', UID, intents_db.INTENTS_COLLECTION, 'malformed-intent')
    firestore.rows[path] = {
        'account_generation': GENERATION,
        'unexpected_legacy_field': True,
    }
    original = deepcopy(firestore.rows[path])

    with patch('database.read_boundary.record_fallback') as fallback:
        with pytest.raises(intents_db.ChatFirstMalformedDocument, match='proactive intent is malformed'):
            intents_db.acknowledge_materialization(
                UID,
                intent_id='malformed-intent',
                receipt_id='kernel-receipt-1',
                account_generation=GENERATION,
                now=NOW,
                firestore_client=firestore,
            )

    fallback.assert_not_called()
    assert firestore.rows[path] == original


def test_malformed_deferral_cannot_be_accepted_or_overwritten(firestore):
    question = _question()
    continuity_key = 'malformed-deferral'
    deferral_id = intents_db._stable_id('cfd', UID, GENERATION, continuity_key)
    path = ('users', UID, intents_db.DEFERRALS_COLLECTION, deferral_id)
    firestore.rows[path] = {
        'account_generation': GENERATION,
        'unexpected_legacy_field': True,
    }
    original = deepcopy(firestore.rows[path])

    with patch('database.read_boundary.record_fallback') as fallback:
        with pytest.raises(intents_db.ChatFirstMalformedDocument, match='deferral is malformed'):
            intents_db.record_deferral(
                UID,
                continuity_key=continuity_key,
                subject=question.subject,
                question=question,
                account_generation=GENERATION,
                now=NOW,
                firestore_client=firestore,
            )

    fallback.assert_not_called()
    assert firestore.rows[path] == original


def test_malformed_budget_state_cannot_be_reset_to_an_enabled_default(firestore):
    path = ('users', UID, intents_db.STATE_COLLECTION, intents_db.BUDGET_DOCUMENT)
    firestore.rows[path] = {
        'account_generation': GENERATION,
        'unexpected_legacy_field': True,
    }
    original = deepcopy(firestore.rows[path])

    with patch('database.read_boundary.record_fallback') as fallback:
        with pytest.raises(intents_db.ChatFirstMalformedDocument, match='proactive budget state is malformed'):
            intents_db.get_budget_state(UID, account_generation=GENERATION, now=NOW, firestore_client=firestore)

    fallback.assert_not_called()
    assert firestore.rows[path] == original


INTENTS_COLLECTION = intents_db.INTENTS_COLLECTION
DEFERRALS_COLLECTION = intents_db.DEFERRALS_COLLECTION
