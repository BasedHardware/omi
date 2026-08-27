"""Dual-backend contract for the JIT proactivity reservation (ADR-0044 facade + ADR-0002 store port).

`database/jit_proactivity_store.py` arrived with upstream in the +30 merge as a NEW file, so it merged
cleanly and only the coverage ratchet (ADR-0030 audit) noticed it had no dual-backend cover. It spends
the user's daily budget for proactive notifications, so a translation difference between the backends
is not a cosmetic one: it either notifies somebody more than the budget allows, or refuses work that
was paid for.

The at-risk shape is `transaction`, and this module is the densest use of it in the merge: ONE
transaction reads the account-deletion marker, the memory control state, the event, the parent event,
the trigger memory, the budget-control row, the day budget and (for a full turn) the candidate row —
then decides admission and writes four documents from what it read. Every decision below is computed
from a read, which is exactly what a facade has to translate faithfully:

    replay          the same event_id with the same payload returns the STORED receipt and False.
                    Without the in-transaction read of the event, a retried request spends the budget
                    twice and the user is notified twice.
    reuse           the same event_id with a DIFFERENT payload is refused, rather than overwriting a
                    receipt somebody already acted on.
    budget          the counters are read, incremented, and written back — per day, per trigger, and
                    per candidate for a full turn.

What this suite does NOT hold, measured rather than assumed: it does not prove the reads happen inside
the transaction, and it makes no concurrency claim at all. Upstream owns that with a real contention
probe (`backend/scripts/jit_proactivity_reservation_emulator_test.py`, two threads on a barrier), and
the two backends deliberately disagree about read locks (ADR-0070). A contract suite asserts the
intersection: same admissions, same refusals, same stored shape.

Binding and skip rules: the shared ``bind_store`` fixture in ``conftest.py``. Every test runs TWICE.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone

import pytest

NOW = datetime(2026, 8, 24, 12, tzinfo=timezone.utc)


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _client():
    """The client this backend deploys, resolved through the accessor ``bind_store`` patched."""
    from database import _client as client_module

    return client_module.get_firestore_client()


@pytest.fixture
def jit(bind_store):
    from database.memory_collections import MemoryCollections
    from models.memory_apply import MemoryControlState
    from models.memory_evidence import ArtifactPreservationState, MemoryEvidence, SourceState
    from models.product_memory import (
        LedgerWriteReason,
        MemoryItem,
        MemoryItemStatus,
        MemoryKind,
        MemoryLayer,
        MemorySubjectScope,
        ProcessingState,
    )

    uid = f'jit-{uuid.uuid4().hex[:10]}'
    collections = MemoryCollections(uid=uid)
    client = _client()

    control = MemoryControlState(uid=uid, head_commit_id='head-1', account_generation=1, source_generation=1)
    trigger = MemoryItem(
        memory_id='trigger-1',
        uid=uid,
        version=1,
        tier=MemoryLayer.long_term,
        status=MemoryItemStatus.active,
        processing_state=ProcessingState.processed,
        content='Release trigger',
        evidence=[
            MemoryEvidence(
                evidence_id='evidence-1',
                source_type='chat_turn',
                source_id='turn-1',
                source_version='v1',
                artifact_preservation=ArtifactPreservationState.preserved,
            )
        ],
        source_state=SourceState.active,
        sensitivity_labels=[],
        visibility='private',
        user_asserted=True,
        captured_at=NOW,
        updated_at=NOW,
        ledger_commit_id='head-1',
        ledger_sequence=1,
        account_generation=1,
        ledger_schema_version='knowledge_ledger.v1',
        kind=MemoryKind.trigger,
        subject_scope=MemorySubjectScope.primary_user,
        trigger_condition={
            'keywords': ['release'],
            'action': {'type': 'agent_prompt', 'prompt': 'Find the next release step.'},
        },
        arguments={'wakeup_budget_per_day': 1},
        intent_backed=True,
        write_reason=LedgerWriteReason.standing_trigger,
    )
    client.document(f'users/{uid}').set({'time_zone': 'UTC'}, merge=True)
    client.document(collections.memory_apply_control_state).set(control.model_dump(mode='python'))
    client.document(f'{collections.memory_items}/{trigger.memory_id}').set(trigger.model_dump(mode='python'))

    yield {'uid': uid, 'collections': collections, 'trigger': trigger, 'store': bind_store, 'client': client}

    # Owner-scoped: every document this module writes hangs off the user root, and each test gets a
    # fresh uid, so the sweep only has to name the collections rather than discover them.
    for collection in (
        collections.jit_proactivity_events,
        collections.jit_proactivity_daily_budgets,
        collections.jit_proactivity_candidate_turns,
        collections.memory_items,
    ):
        for document in bind_store.query(collection):
            bind_store.delete(f'{collection}/{document.id}')
    bind_store.delete(collections.memory_apply_control_state)
    bind_store.delete(f'{collections.user_root}/jit_proactivity_budget_control/current')
    bind_store.delete(f'account_deletions/{uid}')
    bind_store.delete(f'users/{uid}')


def _reserve(jit, *, event_id, operation, candidate_id='candidate-1', **kwargs):
    from database.jit_proactivity_store import reserve_jit_proactivity_event

    return reserve_jit_proactivity_event(
        jit['uid'],
        event_id=_digest(event_id),
        candidate_id=_digest(candidate_id),
        operation=operation,
        account_generation=1,
        device_id=_digest('device-1'),
        now=NOW,
        db_client=jit['client'],
        **kwargs,
    )


def _planned(jit, *, event_id, candidate_id='candidate-1'):
    return _reserve(
        jit,
        event_id=event_id,
        candidate_id=candidate_id,
        operation='planned_notification',
        trigger_memory_id=jit['trigger'].memory_id,
        trigger_revision=jit['trigger'].item_revision,
    )


def _budget(jit):
    stored = jit['store'].get(f"{jit['collections'].jit_proactivity_daily_budgets}/2026-08-24")
    return stored.data if stored is not None and stored.exists else None


# --- transaction: the reservation is computed from what it read ------------------------------------


def test_a_reservation_writes_the_receipt_and_spends_the_budget(jit):
    receipt, reserved = _planned(jit, event_id='event-1')

    assert reserved is True
    assert receipt.uid == jit['uid']
    assert receipt.operation == 'planned_notification'

    stored = jit['store'].get(f"{jit['collections'].jit_proactivity_events}/{receipt.event_id}")
    assert stored is not None and stored.exists
    assert stored.data['request_hash'] == receipt.request_hash

    budget = _budget(jit)
    assert budget['total_notifications'] == 1
    assert budget['planned_by_trigger'][jit['trigger'].memory_id] == 1
    assert budget['budget_timezone'] == 'UTC'


def test_replaying_the_same_request_returns_the_stored_receipt_without_spending_again(jit):
    """The idempotency the whole module exists for: a retried request must not notify twice.

    The in-transaction read of the event is what sees the first reservation; both backends must
    return it, and neither may increment the counters a second time.
    """
    first, reserved_first = _planned(jit, event_id='event-1')
    second, reserved_second = _planned(jit, event_id='event-1')

    assert reserved_first is True
    assert reserved_second is False
    assert second.request_hash == first.request_hash
    assert second.created_at == first.created_at
    assert _budget(jit)['total_notifications'] == 1


def test_reusing_an_event_id_with_a_different_payload_is_refused(jit):
    from database.jit_proactivity_store import JITProactivityReservationError

    _planned(jit, event_id='event-1', candidate_id='candidate-1')

    with pytest.raises(JITProactivityReservationError, match='reused with a different payload'):
        _planned(jit, event_id='event-1', candidate_id='candidate-2')

    assert _budget(jit)['total_notifications'] == 1


def test_the_per_trigger_budget_is_read_and_enforced(jit):
    """JIT_PLANNED_NOTIFICATIONS_PER_TRIGGER_PER_DAY is 1: a second planned notification for the SAME
    trigger is refused even though the daily total (3) still has room."""
    from database.jit_proactivity_store import JITProactivityReservationError

    _planned(jit, event_id='event-1')

    with pytest.raises(JITProactivityReservationError, match='per-trigger budget exhausted'):
        _planned(jit, event_id='event-2')

    assert _budget(jit)['total_notifications'] == 1


def test_the_daily_notification_budget_is_read_and_enforced(jit):
    """JIT_TOTAL_PROACTIVE_NOTIFICATIONS_PER_DAY is 3, counted across operations: three ambient
    notifications exhaust it, and the fourth is refused on both backends."""
    from database.jit_proactivity_store import JITProactivityReservationError

    for index in range(3):
        _, reserved = _reserve(jit, event_id=f'ambient-{index}', operation='ambient_notification')
        assert reserved is True

    with pytest.raises(JITProactivityReservationError, match='notification budget exhausted'):
        _reserve(jit, event_id='ambient-3', operation='ambient_notification')

    assert _budget(jit)['total_notifications'] == 3


def test_a_full_turn_spends_its_candidate_once(jit):
    """A full turn is admitted by its parent notification and may happen once per candidate: the
    transaction reads the candidate row and refuses a second turn for the same candidate."""
    from database.jit_proactivity_store import JITProactivityReservationError

    parent, reserved = _reserve(jit, event_id='parent-1', operation='ambient_notification')
    assert reserved is True

    _, turn_reserved = _reserve(
        jit,
        event_id='turn-1',
        operation='full_turn',
        parent_event_id=parent.event_id,
    )
    assert turn_reserved is True
    assert _budget(jit)['full_turns'] == 1

    with pytest.raises(JITProactivityReservationError, match='full-turn budget exhausted'):
        _reserve(jit, event_id='turn-2', operation='full_turn', parent_event_id=parent.event_id)

    assert _budget(jit)['full_turns'] == 1


def test_a_reservation_is_refused_while_the_account_is_being_deleted(jit):
    """The first read in the transaction is the account-deletion marker. Spending budget for an
    account mid-wipe would resurrect state the deletion just removed."""
    from database.jit_proactivity_store import JITProactivityReservationError

    jit['store'].set(f"account_deletions/{jit['uid']}", {'wipe_status': 'running'})
    try:
        with pytest.raises(JITProactivityReservationError, match='blocked by account deletion'):
            _planned(jit, event_id='event-1')
        assert _budget(jit) is None
    finally:
        jit['store'].delete(f"account_deletions/{jit['uid']}")
