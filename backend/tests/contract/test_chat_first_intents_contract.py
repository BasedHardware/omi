"""Dual-backend contract for Chat-first proactive intents (ADR-0044 facade + ADR-0002 store port).

`database/chat_first_intents.py` decides, on the server, whether Omi is allowed to speak to the user
without being asked — and how many times. It has exactly ONE at-risk shape, and the whole module is
built out of it:

    transaction   every entry point opens `client.transaction()` and runs a read-decide-write body:
                  read the capability fence, read the intent identity, read the budget, then write the
                  intent and the budget TOGETHER. Nothing here is a blind write.

What the wrong translation costs the user, concretely:

  *The budget stops being a cap.* `admit_agent_judgment` reserves one slot before any model call, and
  `acknowledge_materialization` converts that reservation into a consumed turn. Reservation and
  accounting are two documents (`chat_first_proactive_state/budget` and the intent) written in one
  commit. If the budget read leaves the transaction's view, or the two writes can land apart, the user
  gets unsolicited proactive messages past the two-per-thirty-minutes cap — and every one of them was
  a paid model call. The mirror failure is worse in the other direction: a reservation that is dropped
  without being accounted, or accounted without being dropped, permanently silences the feature for
  that account because the cap never clears.

  *The same question gets asked twice.* Intents are keyed by a derived id (`proactive_intent_id`), and
  every writer first READS that id inside the transaction. A replayed wake, a retried request, or a
  second deferral-release pass must return the intent that already exists rather than mint a second
  one. `release_due_deferrals` is the sharpest case: releasing a deferred question writes the new
  intent AND flips the deferral to `released` — if the flip can be lost, the user is asked the same
  deferred question on every foreground wake forever.

  *A revoked capability keeps spending.* `_require_control` reads `task_intelligence_control/state`
  inside the same transaction as the write it guards. A generation bump is how the account withdraws
  the capability; a fence that reads stale state lets an in-flight worker queue a proactive turn for a
  generation the client will never acknowledge, so it is billed and never seen.

Not covered, and why: cross-transaction *conflict detection* (two concurrent admissions racing for the
last budget slot). The two backends do not promise the same thing there — Firestore locks the read set,
Mongo gives a snapshot and takes no read lock (ADR-0070) — so a same-outcome assertion would be
asserting something the port deliberately does not guarantee. Measured, not assumed: rewriting
``intent_ref.get(transaction=write_transaction)`` as ``intent_ref.get()`` in ``create_intent`` — the
read escaping the transaction entirely — leaves this suite green on both backends, because a
sequential caller reads the same committed state either way. What the suite holds is the
read-decide-write body and the joint commit, which both backends do promise; the read *set* belongs to
a concurrency test the port does not underwrite.

Binding and skip rules: the shared ``bind_store`` fixture in ``conftest.py``. Every test runs TWICE.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

NOW = datetime(2026, 6, 1, 9, 0, tzinfo=timezone.utc)
GENERATION = 1

INTENTS = 'chat_first_proactive_intents'
DEFERRALS = 'chat_first_deferrals'
STATE = 'chat_first_proactive_state'


def _subject(kind: str, subject_id: str):
    from models.chat_first import ChatFirstSubject

    return ChatFirstSubject(kind=kind, id=subject_id)


def _task_block(task_id: str):
    from models.chat_first import TaskCardSpec

    return TaskCardSpec(type='taskCard', task_id=task_id)


def _question(question_id: str, subject, text: str = 'Did that meeting happen?'):
    from models.chat_first import QuestionCardSpec, QuestionOption

    return QuestionCardSpec(
        type='questionCard',
        question_id=question_id,
        text=text,
        subject=subject,
        options=[
            QuestionOption(option_id=f'{question_id}-yes', label='Yes', prepared_answer='It happened'),
            QuestionOption(option_id=f'{question_id}-later', label='Later', prepared_answer='Ask me later', defer=True),
        ],
    )


@pytest.fixture
def chat_first(bind_store):
    """One account whose Chat-first capability is live at generation 1."""
    run = uuid.uuid4().hex[:8]
    uid = f'cfi-{run}'

    bind_store.set(
        f'users/{uid}/task_intelligence_control/state',
        {'workflow_mode': 'write', 'account_generation': GENERATION},
    )

    yield {'uid': uid, 'run': run, 'store': bind_store}

    for collection in (INTENTS, DEFERRALS, STATE, 'task_intelligence_control'):
        for document in bind_store.query(f'users/{uid}/{collection}'):
            bind_store.delete(document.path)


def _budget(chat_first):
    stored = chat_first['store'].get(f"users/{chat_first['uid']}/{STATE}/budget")
    return stored.data if stored is not None and stored.exists else None


def _reserved_intent_ids(chat_first) -> set[str]:
    budget = _budget(chat_first) or {}
    return {reservation['intent_id'] for reservation in budget.get('reservations', [])}


def _materialized_count(chat_first) -> int:
    return len((_budget(chat_first) or {}).get('materialized_at', []))


def _intents(chat_first) -> list[dict]:
    return [document.data for document in chat_first['store'].query(f"users/{chat_first['uid']}/{INTENTS}")]


def _admit(chat_first, key: str, *, now=NOW, generation: int = GENERATION):
    import database.chat_first_intents as intents_db

    return intents_db.admit_agent_judgment(
        chat_first['uid'],
        continuity_key=key,
        subject=_subject('task', f"t-{chat_first['run']}"),
        account_generation=generation,
        now=now,
    )


def _create_agent_intent(chat_first, key: str, *, blocks=None, now=NOW):
    import database.chat_first_intents as intents_db

    return intents_db.create_intent(
        chat_first['uid'],
        source='agent_judgment',
        continuity_key=key,
        subject=_subject('task', f"t-{chat_first['run']}"),
        blocks=blocks if blocks is not None else [_task_block(f"t-{chat_first['run']}")],
        account_generation=GENERATION,
        now=now,
    )


# --- transaction: the capability fence --------------------------------------------------------------


def test_an_admission_under_a_withdrawn_generation_is_refused(chat_first):
    """`_require_control` reads the control document inside the same transaction as the budget write.

    The account is at generation 1; a worker still holding generation 0 must be refused BEFORE it
    reserves anything, or it spends a model call and queues a turn the client will never acknowledge.
    """
    import database.chat_first_intents as intents_db

    with pytest.raises(intents_db.ChatFirstIntentGenerationMismatch):
        _admit(chat_first, f"k0-{chat_first['run']}", generation=0)

    assert _budget(chat_first) is None, 'a refused admission must not leave a reservation behind'


def test_acknowledging_after_the_account_regenerates_neither_delivers_nor_accounts(chat_first):
    """The control fence is the ONLY guard that catches this one.

    `acknowledge_materialization` also compares the *intent's* stored generation with the caller's, and
    that second check would fire for a caller from the future. Here the caller and the intent agree —
    both are generation 1 — and the ACCOUNT has moved to 2 underneath them. Only the control document,
    read inside the same transaction as the two writes, can tell. Without it a worker that was already
    in flight when the user withdrew the capability still marks the message delivered and still bills
    the turn.
    """
    import database.chat_first_intents as intents_db

    intent, _created = _create_agent_intent(chat_first, f"k1-{chat_first['run']}")
    chat_first['store'].set(
        f"users/{chat_first['uid']}/task_intelligence_control/state",
        {'workflow_mode': 'write', 'account_generation': GENERATION + 1},
    )

    with pytest.raises(intents_db.ChatFirstIntentGenerationMismatch):
        intents_db.acknowledge_materialization(
            chat_first['uid'],
            intent_id=intent.intent_id,
            receipt_id=f"r-{chat_first['run']}",
            account_generation=GENERATION,
            now=NOW,
        )

    assert _reserved_intent_ids(chat_first) == {intent.intent_id}
    assert _materialized_count(chat_first) == 0
    assert _intents(chat_first)[0]['delivery_state'] == 'ready'


# --- transaction: the budget is a cap ---------------------------------------------------------------


def test_each_admission_reserves_one_slot_and_the_next_one_sees_it(chat_first):
    """Read-modify-write on one budget document. The second admission must read the first one's
    reservation — a budget read that misses it hands out the same slot twice."""
    first = _admit(chat_first, f"a-{chat_first['run']}")
    second = _admit(chat_first, f"b-{chat_first['run']}")

    assert first.newly_reserved is True and second.newly_reserved is True
    assert len(_reserved_intent_ids(chat_first)) == 2


def test_the_third_admission_in_the_window_is_refused_and_writes_nothing(chat_first):
    """Two agent turns per thirty minutes is the whole cost gate. The third must be refused, and the
    refusal must not partially update the budget — an account that gets a third unsolicited message is
    a user being pestered and a model call nobody authorised."""
    import database.chat_first_intents as intents_db

    _admit(chat_first, f"a-{chat_first['run']}")
    _admit(chat_first, f"b-{chat_first['run']}")

    with pytest.raises(intents_db.ProactiveBudgetExhausted):
        _admit(chat_first, f"c-{chat_first['run']}")

    assert len(_reserved_intent_ids(chat_first)) == 2, 'the refused admission must not appear'


def test_re_admitting_the_same_continuity_key_does_not_reserve_a_second_slot(chat_first):
    """A retried wake for the same continuity key is the same judgment, not a second one. Reserving
    twice would burn half the window on one question and silence the account early."""
    first = _admit(chat_first, f"a-{chat_first['run']}")
    repeat = _admit(chat_first, f"a-{chat_first['run']}")

    assert first.newly_reserved is True
    assert repeat.newly_reserved is False
    assert len(_reserved_intent_ids(chat_first)) == 1


def test_releasing_an_unused_admission_returns_the_slot(chat_first):
    """A declined or failed judgment must give the slot back, or one provider hiccup costs the user
    their whole proactive window."""
    import database.chat_first_intents as intents_db

    _admit(chat_first, f"a-{chat_first['run']}")
    _admit(chat_first, f"b-{chat_first['run']}")

    intents_db.release_agent_judgment_admission(
        chat_first['uid'],
        continuity_key=f"a-{chat_first['run']}",
        account_generation=GENERATION,
        now=NOW,
    )

    assert len(_reserved_intent_ids(chat_first)) == 1
    assert _admit(chat_first, f"c-{chat_first['run']}").newly_reserved is True


def test_a_reservation_backing_a_real_intent_is_never_released(chat_first):
    """The release reads the intent inside the same transaction as the budget write. Once the intent
    exists the reservation belongs to it; releasing anyway would let the account materialise a turn it
    never paid for and exceed the cap."""
    import database.chat_first_intents as intents_db

    key = f"a-{chat_first['run']}"
    _admit(chat_first, key)
    intent, _created = _create_agent_intent(chat_first, key)

    intents_db.release_agent_judgment_admission(
        chat_first['uid'], continuity_key=key, account_generation=GENERATION, now=NOW
    )

    assert _reserved_intent_ids(chat_first) == {intent.intent_id}


# --- transaction: the intent and its accounting commit together -------------------------------------


def test_creating_an_agent_intent_writes_the_intent_and_its_reservation_together(chat_first):
    """One commit, two documents. Only the intent lands and the cap never counts it; only the budget
    lands and the user is charged for a message that does not exist."""
    intent, created = _create_agent_intent(chat_first, f"a-{chat_first['run']}")

    assert created is True
    assert [row['intent_id'] for row in _intents(chat_first)] == [intent.intent_id]
    assert _reserved_intent_ids(chat_first) == {intent.intent_id}


def test_recreating_the_same_intent_returns_the_stored_one_instead_of_a_second(chat_first):
    """The in-transaction read of the derived id is what makes a replay a no-op. Without it the user
    sees the same proactive message twice and pays for it twice."""
    first, created_first = _create_agent_intent(chat_first, f"a-{chat_first['run']}")
    second, created_second = _create_agent_intent(chat_first, f"a-{chat_first['run']}")

    assert created_first is True and created_second is False
    assert second.intent_id == first.intent_id
    assert len(_intents(chat_first)) == 1
    assert len(_reserved_intent_ids(chat_first)) == 1


def test_a_continuity_key_reused_with_different_content_is_refused(chat_first):
    """Same identity, different message: the stored intent wins and the caller is told. Silently
    overwriting would swap the question under a user who is already looking at it."""
    import database.chat_first_intents as intents_db

    key = f"a-{chat_first['run']}"
    first, _created = _create_agent_intent(chat_first, key)

    with pytest.raises(intents_db.ChatFirstIntentConflictError):
        _create_agent_intent(chat_first, key, blocks=[_task_block(f"other-{chat_first['run']}")])

    stored = _intents(chat_first)
    assert len(stored) == 1
    assert stored[0]['blocks'] == first.model_dump(mode='python')['blocks']


def test_acknowledging_a_receipt_converts_the_reservation_into_a_consumed_turn(chat_first):
    """The joint write the cap depends on: the intent becomes `delivered` and the reservation becomes a
    materialised turn in the SAME commit. Half of that is either an account that can never speak again
    (reservation kept forever) or one with no memory of having spoken (turn never counted)."""
    import database.chat_first_intents as intents_db

    intent, _created = _create_agent_intent(chat_first, f"a-{chat_first['run']}")

    delivered = intents_db.acknowledge_materialization(
        chat_first['uid'],
        intent_id=intent.intent_id,
        receipt_id=f"r-{chat_first['run']}",
        account_generation=GENERATION,
        now=NOW,
    )

    assert delivered.delivery_state == 'delivered'
    assert delivered.materialization_receipt_id == f"r-{chat_first['run']}"
    assert _intents(chat_first)[0]['delivery_state'] == 'delivered'
    assert _reserved_intent_ids(chat_first) == set(), 'the reservation must be consumed, not stranded'
    assert _materialized_count(chat_first) == 1


def test_replaying_the_same_receipt_does_not_count_the_turn_twice(chat_first):
    """The kernel retries its receipt. Counting it again spends a second turn the user never received
    and brings the daily cap down for nothing."""
    import database.chat_first_intents as intents_db

    intent, _created = _create_agent_intent(chat_first, f"a-{chat_first['run']}")
    for _attempt in range(2):
        intents_db.acknowledge_materialization(
            chat_first['uid'],
            intent_id=intent.intent_id,
            receipt_id=f"r-{chat_first['run']}",
            account_generation=GENERATION,
            now=NOW,
        )

    assert _materialized_count(chat_first) == 1


def test_a_different_receipt_for_a_delivered_intent_is_refused(chat_first):
    """Two kernels claiming the same intent is a real divergence, not a retry: refuse rather than
    account for it twice."""
    import database.chat_first_intents as intents_db

    intent, _created = _create_agent_intent(chat_first, f"a-{chat_first['run']}")
    intents_db.acknowledge_materialization(
        chat_first['uid'],
        intent_id=intent.intent_id,
        receipt_id=f"r1-{chat_first['run']}",
        account_generation=GENERATION,
        now=NOW,
    )

    with pytest.raises(intents_db.ChatFirstIntentConflictError):
        intents_db.acknowledge_materialization(
            chat_first['uid'],
            intent_id=intent.intent_id,
            receipt_id=f"r2-{chat_first['run']}",
            account_generation=GENERATION,
            now=NOW,
        )

    assert _materialized_count(chat_first) == 1


# --- transaction: a deferred question is released exactly once --------------------------------------


def _record_deferral(chat_first, key: str, *, now=NOW):
    import database.chat_first_intents as intents_db

    subject = _subject('task', f"t-{chat_first['run']}")
    return intents_db.record_deferral(
        chat_first['uid'],
        continuity_key=key,
        subject=subject,
        question=_question(f"q-{chat_first['run']}", subject),
        account_generation=GENERATION,
        now=now,
    )


def test_recording_the_same_deferral_twice_returns_the_first_receipt(chat_first):
    """The kernel's deferral outbox is at-least-once. A second copy of the same record must not create
    a second question to re-raise later."""
    first, created_first = _record_deferral(chat_first, f"d-{chat_first['run']}")
    second, created_second = _record_deferral(chat_first, f"d-{chat_first['run']}", now=NOW + timedelta(hours=1))

    assert created_first is True and created_second is False
    assert second.deferral_id == first.deferral_id
    assert second.due_at == first.due_at, 'a replay must not push the question further into the future'
    assert len(list(chat_first['store'].query(f"users/{chat_first['uid']}/{DEFERRALS}"))) == 1


def test_a_due_deferral_is_released_into_one_intent_and_marked_released(chat_first):
    """The two writes that must not come apart: the re-raise intent is created and the deferral is
    flipped to `released` in the same commit. If the flip is lost the question is re-raised on every
    later wake; if the intent is lost the user is never asked again."""
    import database.chat_first_intents as intents_db

    receipt, _created = _record_deferral(chat_first, f"d-{chat_first['run']}")

    released = intents_db.release_due_deferrals(
        chat_first['uid'], account_generation=GENERATION, now=NOW + timedelta(hours=25)
    )

    assert len(released) == 1
    assert released[0].source == 'deferral_reraise'
    stored_deferral = chat_first['store'].get(f"users/{chat_first['uid']}/{DEFERRALS}/{receipt.deferral_id}").data
    assert stored_deferral['state'] == 'released'
    assert stored_deferral['released_intent_id'] == released[0].intent_id
    assert [row['intent_id'] for row in _intents(chat_first)] == [released[0].intent_id]


def test_a_second_release_pass_does_not_raise_the_question_again(chat_first):
    """Exactly once, across passes. The second sweep re-reads the deferral inside its transaction and
    must find it already released."""
    import database.chat_first_intents as intents_db

    _record_deferral(chat_first, f"d-{chat_first['run']}")
    later = NOW + timedelta(hours=25)

    first_pass = intents_db.release_due_deferrals(chat_first['uid'], account_generation=GENERATION, now=later)
    second_pass = intents_db.release_due_deferrals(chat_first['uid'], account_generation=GENERATION, now=later)

    assert len(first_pass) == 1
    assert second_pass == [], 'the deferral was released twice'
    assert len(_intents(chat_first)) == 1


def test_a_deferral_that_is_not_due_yet_is_left_alone(chat_first):
    """The window differs ONLY in the clock: same deferral, one hour after recording instead of
    twenty-five. A release that ignores the due bound interrupts the user with a question they
    explicitly postponed."""
    import database.chat_first_intents as intents_db

    _record_deferral(chat_first, f"d-{chat_first['run']}")

    assert (
        intents_db.release_due_deferrals(
            chat_first['uid'], account_generation=GENERATION, now=NOW + timedelta(hours=1)
        )
        == []
    )
    assert _intents(chat_first) == []
