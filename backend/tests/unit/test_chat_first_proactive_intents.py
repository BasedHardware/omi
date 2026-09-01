"""Hermetic contracts for server-only Chat-first proactive intent state."""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

import database.chat_first_intents as intents_db
from models.chat_first import (
    CaptureLinkSpec,
    ChatFirstSubject,
    ColdStartSequence,
    ConversationLinkSpec,
    QuestionCardSpec,
    QuestionOption,
)
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
            hook = self._database.transaction_read_hooks.pop(self._path, None)
            if hook is not None:
                hook()
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
        return _FilteredCollection(matched)

    def limit(self, count):
        return _FilteredCollection(self._snapshots[:count])


class _Transaction:
    def __init__(self, database):
        self.database = database
        self._wrote = False

    def read(self):
        if self._wrote:
            raise AssertionError('Firestore transactions must finish reads before writes')

    def set(self, ref, payload, merge=False):
        self._wrote = True
        ref.set(payload, merge=merge)


class _WriteBatch:
    def __init__(self, database):
        self.database = database
        self.writes = []

    def set(self, ref, payload):
        self.writes.append((ref, payload))

    def update(self, ref, payload):
        self.writes.append(('update', ref, payload))

    def commit(self):
        self.database.batch_commit_count += 1
        hook = self.database.batch_commit_hook
        self.database.batch_commit_hook = None
        if hook is not None:
            hook()
        for operation in self.writes:
            if len(operation) == 2:
                ref, payload = operation
                ref.set(payload)
                continue
            _, ref, payload = operation
            if ref._path not in self.database.rows:
                raise KeyError('write batch update requires an existing document')
            ref.set(payload, merge=True)


class _Firestore:
    def __init__(self):
        self.rows = {}
        self.transaction_count = 0
        self.batch_commit_count = 0
        self.transaction_read_hooks = {}
        self.batch_commit_hook = None

    def collection(self, name):
        return _Collection(self, (name,))

    def transaction(self):
        self.transaction_count += 1
        return _Transaction(self)

    def batch(self):
        return _WriteBatch(self)


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


def test_poison_item_contract_one_bad_item_never_blocks_rest_and_is_parked_with_reason_within_budget(firestore):
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
    healthy, _ = intents_db.create_intent(
        UID,
        source='daily_opener',
        continuity_key='daily:healthy',
        subject=None,
        blocks=[CaptureLinkSpec(type='captureLink', conversation_id='healthy', summary='Healthy')],
        account_generation=GENERATION,
        now=NOW + timedelta(seconds=1),
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
        assert rejected.materialization_attempts == attempt

    assert reason == 'rejection_budget_exhausted'
    assert rejected.delivery_state == 'dead_letter'
    assert rejected.last_rejection_code == 'kernel_materialization_failed'
    fetched = intents_db.fetch_ready_intents(
        UID,
        account_generation=GENERATION,
        now=NOW + timedelta(minutes=10),
        firestore_client=firestore,
    )
    assert [intent.intent_id for intent in fetched] == [healthy.intent_id]
    assert poison.intent_id not in [intent.intent_id for intent in fetched]


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

    for fetch_index in range(intents_db.UNACKNOWLEDGED_FETCH_BUDGET):
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
    stored = intents_db._intent_from_snapshot(
        intents_db._intent_ref(UID, intent.intent_id, firestore_client=firestore).get()
    )
    assert stored.delivery_state == 'dead_letter'
    assert stored.fetch_count == intents_db.UNACKNOWLEDGED_FETCH_BUDGET + 1
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
        intents_db._intent_ref(UID, undeferred.intent_id, firestore_client=firestore).get()
    )
    assert stored_deferred.delivery_state == 'ready'
    assert stored_deferred.fetch_count == 0
    assert stored_deferred.last_fetched_at is None
    assert stored_undeferred.delivery_state == 'dead_letter'
    assert stored_undeferred.fetch_count == intents_db.UNACKNOWLEDGED_FETCH_BUDGET + 1


def test_terminal_receipt_is_acknowledged_idempotently_after_fetch_budget_dead_letter(firestore):
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
    path = ('users', UID, intents_db.INTENTS_COLLECTION, intent.intent_id)
    firestore.rows[path]['delivery_state'] = 'dead_letter'
    firestore.rows[path]['dead_letter_reason'] = 'unacknowledged_after_fetch_budget'

    acknowledged = intents_db.acknowledge_materialization(
        UID,
        intent_id=intent.intent_id,
        receipt_id='late-kernel-receipt',
        account_generation=GENERATION,
        now=NOW + timedelta(hours=1),
        firestore_client=firestore,
    )

    assert acknowledged.delivery_state == 'dead_letter'


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
    assert firestore.rows[malformed_path]['delivery_state'] == 'dead_letter'
    assert firestore.rows[malformed_path]['dead_letter_reason'] == 'malformed_document'
    assert firestore.transaction_count == transactions_before + 2
    assert firestore.batch_commit_count == 0


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
    firestore.batch_commit_hook = delete_during_write

    batch = intents_db.fetch_ready_intent_batch(
        UID, account_generation=GENERATION, now=NOW + timedelta(minutes=1), firestore_client=firestore
    )

    assert [item.intent_id for item in batch.intents] == [healthy.intent_id]
    healthy_path = ('users', UID, intents_db.INTENTS_COLLECTION, healthy.intent_id)
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
    firestore.rows[path]['fetch_count'] = intents_db.UNACKNOWLEDGED_FETCH_BUDGET

    def deliver_concurrently():
        firestore.rows[path]['delivery_state'] = 'delivered'
        firestore.rows[path]['materialization_receipt_id'] = 'other-device-receipt'

    firestore.transaction_read_hooks[path] = deliver_concurrently
    firestore.batch_commit_hook = deliver_concurrently

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

    def second_device_fetch():
        intents_db.fetch_ready_intent_batch(
            UID,
            account_generation=GENERATION,
            now=NOW + timedelta(seconds=1),
            firestore_client=firestore,
        )

    firestore.transaction_read_hooks[path] = second_device_fetch
    firestore.batch_commit_hook = second_device_fetch
    intents_db.fetch_ready_intent_batch(
        UID, account_generation=GENERATION, now=NOW + timedelta(seconds=2), firestore_client=firestore
    )

    assert firestore.rows[path]['fetch_count'] == 2


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


def test_fetch_reconciles_a_stable_chat_row_after_an_earlier_delivery(firestore):
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
    stored = intents_db._intent_from_snapshot(
        intents_db._intent_ref(UID, intent.intent_id, firestore_client=firestore).get()
    )
    assert stored.delivery_state == 'delivered'
    assert stored.materialization_receipt_id.startswith('cfi_reconciled_')


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

    assert [intent.intent_id for intent in batch.intents[:2]] == [daily.intent_id, meeting.intent_id]
    assert len(batch.intents) == 8
    assert batch.stalled_source == 'capture_arrival'


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
    assert (
        intents_db.acknowledge_materialization(
            UID,
            intent_id=first.intent_id,
            receipt_id='different-kernel-receipt',
            account_generation=GENERATION,
            now=NOW + timedelta(seconds=1),
            firestore_client=firestore,
        ).delivery_state
        == 'delivered'
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
    assert subject_change[0].blocks[0].model_copy(update={'question_id': task_question.question_id}) == task_question
    assert subject_change[0].blocks[0].question_id != task_question.question_id


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
        with pytest.raises(intents_db.ChatFirstIntentGenerationMismatch, match='proactive intent is malformed'):
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
        with pytest.raises(intents_db.ChatFirstIntentGenerationMismatch, match='deferral is malformed'):
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
        with pytest.raises(intents_db.ChatFirstIntentGenerationMismatch, match='proactive budget state is malformed'):
            intents_db.get_budget_state(UID, account_generation=GENERATION, now=NOW, firestore_client=firestore)

    fallback.assert_not_called()
    assert firestore.rows[path] == original


INTENTS_COLLECTION = intents_db.INTENTS_COLLECTION
DEFERRALS_COLLECTION = intents_db.DEFERRALS_COLLECTION
