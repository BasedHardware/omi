"""Dual-backend contract for the recurrence inbox (ADR-0044 facade + ADR-0002 store port).

`database/recurrence_inbox.py` is the durable handoff between the memory domain, which OBSERVES that
the user keeps failing to close the same loop, and task workflow, which may turn that observation into
a Candidate. The receipt is written before the mutation and acknowledged after it, so it is the only
thing standing between "the user gets one task for a recurring loop" and "the user gets a new task
every time consolidation runs". It carries two shapes the facade has to translate:

    transaction        every entry point re-reads state inside the transaction before writing. Three
                       separate reads, three separate user-visible failures. (a) enqueue re-reads the
                       receipt and FREEZES the first proposal: the module's own comment says why —
                       once Candidate creation has committed, mutating the proposal reuses its
                       idempotency key with different content forever, so the user's task and the
                       signal that justified it drift apart with nothing to reconcile them. (b) enqueue
                       and both acknowledgements re-read the per-user `task_intelligence_control`
                       document and refuse when the account generation has moved: after an account
                       reset, work queued against the old generation must not land in the new one, or
                       the user sees tasks resurrected from a life they already erased. (c) the
                       acknowledgements also re-read the RECEIPT's own generation, which is the case a
                       control check alone cannot see — a worker holding a receipt id from before the
                       reset, running after the control document has already advanced.
    atomic_field_ops   `firestore.Increment(1)` on `attempts`, on both the completion and the retry
                       path. It is the retry counter for a durable queue: if the increment is
                       translated as a literal write the counter sticks at 1, every failing signal
                       looks like a first attempt, and nothing can ever be escalated or given up on.
                       If it is stored as an un-translated sentinel OBJECT the damage is worse and
                       quieter — `attempts` is a strict `int` on `RecurrenceInboxReceipt`, and
                       `list_pending_recurrence_receipts` parses fail-open, so the receipt silently
                       disappears from the pending list and the loop is never processed at all.

Binding and skip rules: the shared ``bind_store`` fixture in ``conftest.py``. Every test runs TWICE.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from models.action_item import EvidenceKind, EvidenceRef, EvidenceScope
from models.memory_recurrence import CanonicalRecurrenceSignal
from models.workstream_association import RecurrenceInboxStatus, RecurrenceOutcomeKind

NOW = datetime(2026, 6, 1, 9, 0, tzinfo=timezone.utc)
GENERATION = 3


def _signal(anchor: str, *, title: str = 'Send the investor update') -> CanonicalRecurrenceSignal:
    """A canonical recurrence signal. `stable_loop_key` is derived from the FIRST evidence ref only, so
    `anchor` decides the receipt identity and `title` is free to differ between deliveries."""
    return CanonicalRecurrenceSignal(
        signal_id=f'observation-{anchor}',
        title=title,
        objective=f'{title} before the board call',
        anchor_task_description='Draft the investor email',
        occurrence_count=3,
        distinct_day_count=2,
        unresolved=True,
        confidence=0.9,
        first_seen_at=NOW - timedelta(days=1),
        last_seen_at=NOW,
        evidence_refs=[EvidenceRef(kind=EvidenceKind.memory_item, id=anchor, scope=EvidenceScope.canonical)],
    )


@pytest.fixture
def inbox(bind_store):
    """One user whose task workflow control document sits at generation 3."""
    run = uuid.uuid4().hex[:8]
    uid = f'rec-{run}'
    control = f'users/{uid}/task_intelligence_control/state'
    bind_store.set(control, {'workflow_mode': 'write', 'account_generation': GENERATION})

    yield {'uid': uid, 'run': run, 'control': control, 'store': bind_store}

    for document in bind_store.query(f'users/{uid}/task_recurrence_inbox'):
        bind_store.delete(document.path)
    bind_store.delete(control)


def _receipts(inbox) -> list[dict]:
    return [document.data for document in inbox['store'].query(f"users/{inbox['uid']}/task_recurrence_inbox")]


def _stored(inbox, receipt_id: str):
    document = inbox['store'].get(f"users/{inbox['uid']}/task_recurrence_inbox/{receipt_id}")
    return document.data if document is not None and document.exists else None


def _pending_ids(inbox, generation: int = GENERATION) -> set[str]:
    import database.recurrence_inbox as inbox_db

    return {
        receipt.receipt_id
        for receipt in inbox_db.list_pending_recurrence_receipts(inbox['uid'], account_generation=generation)
    }


# --- transaction: the frozen first proposal -----------------------------------------------------------


def test_a_new_signal_is_persisted_as_a_pending_receipt(inbox):
    import database.recurrence_inbox as inbox_db

    receipt = inbox_db.enqueue_recurrence_signal(
        inbox['uid'], _signal(f"a1-{inbox['run']}"), account_generation=GENERATION
    )

    assert receipt.status is RecurrenceInboxStatus.pending
    assert receipt.attempts == 0
    assert receipt.account_generation == GENERATION
    assert _pending_ids(inbox) == {receipt.receipt_id}, 'the workflow reader cannot see the queued signal'


def test_a_re_delivered_signal_returns_the_frozen_first_proposal(inbox):
    """What the in-transaction read is FOR, and the only way to see it.

    Both deliveries share an evidence anchor, so they share a `stable_loop_key` and therefore a receipt
    id. The second one carries a DIFFERENT title — a later consolidation pass rewording the same loop.
    The contract is that the stored proposal does not move: the first wording is what comes back and
    what stays on disk.

    Asserting only "one receipt under one id" would pass for a blind `create` that overwrote (or for one
    that raised and was swallowed), so the assertions below are about which CONTENT survived.
    """
    import database.recurrence_inbox as inbox_db

    anchor = f"a2-{inbox['run']}"
    first = inbox_db.enqueue_recurrence_signal(inbox['uid'], _signal(anchor), account_generation=GENERATION)
    # Read back rather than trusting the returned model: the first call returns the object it built in
    # memory, and BSON stores datetimes at millisecond resolution, so only two round-tripped values are
    # comparable across the two backends.
    created_at = _stored(inbox, first.receipt_id)['created_at']

    second = inbox_db.enqueue_recurrence_signal(
        inbox['uid'], _signal(anchor, title='Chase the investor update again'), account_generation=GENERATION
    )

    assert second.receipt_id == first.receipt_id
    assert second.signal.title == 'Send the investor update', 'the re-delivery rewrote the frozen proposal'
    assert second.created_at == created_at, 'the re-delivery re-stamped the receipt as new'
    assert _stored(inbox, first.receipt_id)['created_at'] == created_at
    assert _stored(inbox, first.receipt_id)['signal']['title'] == 'Send the investor update'
    assert len(_receipts(inbox)) == 1


def test_a_re_delivery_does_not_reopen_a_completed_receipt(inbox):
    """The freeze outlives the acknowledgement: a completed loop must not go back to pending, or the
    user is handed a second task for work the workflow already did."""
    import database.recurrence_inbox as inbox_db

    anchor = f"a3-{inbox['run']}"
    receipt = inbox_db.enqueue_recurrence_signal(inbox['uid'], _signal(anchor), account_generation=GENERATION)
    inbox_db.complete_recurrence_receipt(
        inbox['uid'],
        receipt.receipt_id,
        outcome=RecurrenceOutcomeKind.candidate_created,
        account_generation=GENERATION,
    )

    again = inbox_db.enqueue_recurrence_signal(inbox['uid'], _signal(anchor), account_generation=GENERATION)

    assert again.status is RecurrenceInboxStatus.completed
    assert _pending_ids(inbox) == set(), 'a completed loop reappeared in the pending queue'


# --- transaction: the generation fence ----------------------------------------------------------------


def test_a_signal_from_a_superseded_generation_is_refused_and_writes_nothing(inbox):
    """The control document reads generation 3. A signal queued against generation 2 belongs to an
    account state the user has already reset away from; accepting it would revive erased work."""
    import database.recurrence_inbox as inbox_db

    with pytest.raises(inbox_db.RecurrenceGenerationMismatchError):
        inbox_db.enqueue_recurrence_signal(
            inbox['uid'], _signal(f"a4-{inbox['run']}"), account_generation=GENERATION - 1
        )

    assert _receipts(inbox) == [], 'the refused signal still left a receipt behind'


def test_a_worker_that_slept_through_an_account_reset_cannot_acknowledge(inbox):
    """The same fence on the way out, in the one shape only the CONTROL read can catch.

    This worker is internally consistent: it holds a receipt minted at generation 3 and acknowledges at
    generation 3, so the receipt's own generation matches and that guard waves it through. What it does
    not know is that the account was reset while it was queued and the control document now reads 4.
    Only the control document read inside the transaction sees that, and it must refuse — otherwise the
    reset user's brand-new inbox is being written by a job from the account they erased.
    """
    import database.recurrence_inbox as inbox_db

    receipt = inbox_db.enqueue_recurrence_signal(
        inbox['uid'], _signal(f"a5-{inbox['run']}"), account_generation=GENERATION
    )
    inbox['store'].set(inbox['control'], {'workflow_mode': 'write', 'account_generation': GENERATION + 1})

    with pytest.raises(inbox_db.RecurrenceGenerationMismatchError):
        inbox_db.complete_recurrence_receipt(
            inbox['uid'],
            receipt.receipt_id,
            outcome=RecurrenceOutcomeKind.candidate_created,
            account_generation=GENERATION,
        )
    with pytest.raises(inbox_db.RecurrenceGenerationMismatchError):
        inbox_db.retry_recurrence_receipt(
            inbox['uid'], receipt.receipt_id, error_code='transient', account_generation=GENERATION
        )

    assert _stored(inbox, receipt.receipt_id)['status'] == RecurrenceInboxStatus.pending.value
    assert _stored(inbox, receipt.receipt_id)['attempts'] == 0, 'a refused acknowledgement burned an attempt'


def test_a_receipt_left_over_from_the_previous_generation_cannot_be_acknowledged(inbox):
    """The case the control check alone CANNOT see, and the reason the receipt carries its own
    generation.

    The worker is holding a receipt id minted at generation 3, and by the time it runs the account has
    been reset: the control document now reads 4, so the control fence lets it through. Only the second
    clause — the receipt's own `account_generation` — stops it. Without it the reset user's brand-new
    inbox is acknowledged by a job from the account they erased.
    """
    import database.recurrence_inbox as inbox_db

    receipt = inbox_db.enqueue_recurrence_signal(
        inbox['uid'], _signal(f"a6-{inbox['run']}"), account_generation=GENERATION
    )
    inbox['store'].set(inbox['control'], {'workflow_mode': 'write', 'account_generation': GENERATION + 1})

    with pytest.raises(inbox_db.RecurrenceGenerationMismatchError):
        inbox_db.complete_recurrence_receipt(
            inbox['uid'],
            receipt.receipt_id,
            outcome=RecurrenceOutcomeKind.candidate_created,
            account_generation=GENERATION + 1,
        )
    with pytest.raises(inbox_db.RecurrenceGenerationMismatchError):
        inbox_db.retry_recurrence_receipt(
            inbox['uid'], receipt.receipt_id, error_code='transient', account_generation=GENERATION + 1
        )

    assert _stored(inbox, receipt.receipt_id)['status'] == RecurrenceInboxStatus.pending.value
    assert _stored(inbox, receipt.receipt_id)['attempts'] == 0


def test_acknowledging_a_receipt_that_was_never_written_is_refused(inbox):
    """The other clause of the same guard: no document at all. It must raise rather than create one, or
    a typo'd id conjures a receipt whose `signal` field is missing and which no reader can parse."""
    import database.recurrence_inbox as inbox_db

    ghost = f"recurrence_inbox_ghost{inbox['run']}"

    with pytest.raises(inbox_db.RecurrenceGenerationMismatchError):
        inbox_db.complete_recurrence_receipt(
            inbox['uid'], ghost, outcome=RecurrenceOutcomeKind.candidate_created, account_generation=GENERATION
        )

    assert _receipts(inbox) == []


# --- atomic field ops -------------------------------------------------------------------------------


def test_every_retry_advances_the_attempt_counter(inbox):
    """`Increment(1)`. A counter that sticks makes an endlessly failing signal indistinguishable from a
    first try, so nothing ever escalates. The receipt must also stay PENDING and stay VISIBLE: an
    un-translated sentinel object would make `attempts` a non-int, and the fail-open list parser would
    drop the receipt from the pending queue without a word."""
    import database.recurrence_inbox as inbox_db

    receipt = inbox_db.enqueue_recurrence_signal(
        inbox['uid'], _signal(f"a7-{inbox['run']}"), account_generation=GENERATION
    )

    inbox_db.retry_recurrence_receipt(
        inbox['uid'], receipt.receipt_id, error_code='candidate_write_failed', account_generation=GENERATION
    )
    inbox_db.retry_recurrence_receipt(
        inbox['uid'], receipt.receipt_id, error_code='candidate_write_failed', account_generation=GENERATION
    )

    stored = _stored(inbox, receipt.receipt_id)
    assert stored['attempts'] == 2, 'the retry counter did not advance'
    assert stored['last_error_code'] == 'candidate_write_failed'
    assert stored['status'] == RecurrenceInboxStatus.pending.value
    assert _pending_ids(inbox) == {receipt.receipt_id}, 'the retried receipt vanished from the pending queue'


def test_completing_after_a_failed_attempt_counts_both(inbox):
    """The increment on the completion path is a separate call site. Completion also clears the error
    code and records the outcome, which is what tells an operator whether the loop produced a Candidate
    or was dropped below threshold."""
    import database.recurrence_inbox as inbox_db

    receipt = inbox_db.enqueue_recurrence_signal(
        inbox['uid'], _signal(f"a8-{inbox['run']}"), account_generation=GENERATION
    )
    inbox_db.retry_recurrence_receipt(
        inbox['uid'], receipt.receipt_id, error_code='candidate_write_failed', account_generation=GENERATION
    )

    inbox_db.complete_recurrence_receipt(
        inbox['uid'],
        receipt.receipt_id,
        outcome=RecurrenceOutcomeKind.below_threshold,
        account_generation=GENERATION,
    )

    stored = _stored(inbox, receipt.receipt_id)
    assert stored['attempts'] == 2, 'the completion did not count as an attempt on top of the retry'
    assert stored['status'] == RecurrenceInboxStatus.completed.value
    assert stored['last_outcome'] == RecurrenceOutcomeKind.below_threshold.value
    assert stored['last_error_code'] is None, 'a completed receipt still advertises the error that preceded it'
    assert _pending_ids(inbox) == set()


def test_the_pending_queue_is_scoped_to_one_generation(inbox):
    """The two equality filters that feed the workflow reader. A receipt from another generation showing
    up here is the same resurrection the write fence exists to prevent."""
    import database.recurrence_inbox as inbox_db

    receipt = inbox_db.enqueue_recurrence_signal(
        inbox['uid'], _signal(f"a9-{inbox['run']}"), account_generation=GENERATION
    )

    assert _pending_ids(inbox, GENERATION) == {receipt.receipt_id}
    assert _pending_ids(inbox, GENERATION + 1) == set()
