"""Dual-backend contract for the chat-first dead-letter repair (ADR-0044 facade + ADR-0002 port).

`database/chat_first_delivery_attempts.py` arrived with upstream in the +1002 merge and the coverage
ratchet found it: a NEW file merges cleanly, so nothing else would have. Its at-risk shape is
`transaction`, and it guards a decision the user feels directly — whether a proactive message that
failed to deliver gets a second chance or is buried:

    `requeue_transient_dead_letter` reads the dead letter AND its delivery-attempt counters in ONE
    transaction, then decides from what it read: only a TRANSIENT reason, only the current account
    generation, only if it has never been requeued before, and only once the repair age has passed.
    It then writes the revived intent, resets the counters, and DELETES the dead letter — three
    documents, one commit. A backend that lost any one of them would either resurrect a message twice
    or leave a tombstone the reader keeps tripping over.

The write shapes are exactly what a facade has to get right: a full-document `set` on the revived
intent, a `set(..., merge=True)` on the counters, and a `delete` of the source — all in one commit.

What this suite does NOT hold, measured rather than assumed: it cannot prove the reads are inside the
transaction. That needs a concurrent repairer, and the two backends deliberately disagree about read
locks (ADR-0070). A contract suite asserts the intersection.

Binding and skip rules: the shared ``bind_store`` fixture in ``conftest.py``. Every test runs TWICE.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

NOW = datetime(2026, 9, 8, 12, tzinfo=timezone.utc)
GENERATION = 7


def _client():
    """The client this backend deploys, resolved through the accessor ``bind_store`` patched."""
    from database import _client as client_module

    return client_module.get_firestore_client()


@pytest.fixture
def intent(bind_store):
    import database.chat_first_delivery_attempts as attempts_db
    import database.chat_first_intents as intents_db
    from models.chat_first import ChatFirstSubject, QuestionCardSpec, QuestionOption

    from database.candidates import TASK_INTELLIGENCE_CONTROL_COLLECTION, TASK_INTELLIGENCE_CONTROL_DOCUMENT

    run = uuid.uuid4().hex[:8]
    uid = f'uid-{run}'
    client = _client()

    # `create_intent` refuses unless the account's workflow control agrees on the generation: a
    # chat-first message created against a stale capability is the thing that check exists to stop.
    control_path = f'users/{uid}/{TASK_INTELLIGENCE_CONTROL_COLLECTION}/{TASK_INTELLIGENCE_CONTROL_DOCUMENT}'
    bind_store.set(control_path, {'workflow_mode': 'off', 'account_generation': GENERATION})

    created, _ = intents_db.create_intent(
        uid,
        source='agent_judgment',
        continuity_key=f'goal-{run}',
        subject=ChatFirstSubject(kind='goal', id=f'goal-{run}'),
        blocks=[
            QuestionCardSpec(
                type='questionCard',
                question_id='question-1',
                text='What should happen next?',
                subject=ChatFirstSubject(kind='goal', id=f'goal-{run}'),
                options=[QuestionOption(option_id='yes', label='Yes', prepared_answer='Yes')],
            )
        ],
        account_generation=GENERATION,
        now=NOW,
        firestore_client=client,
    )

    context = {
        'uid': uid,
        'intent_id': created.intent_id,
        'store': bind_store,
        'active': f'users/{uid}/{attempts_db.INTENTS_COLLECTION}/{created.intent_id}',
        'dead': f'users/{uid}/{attempts_db.DEAD_LETTERS_COLLECTION}/{created.intent_id}',
        'attempt': f'users/{uid}/{attempts_db.DELIVERY_ATTEMPTS_COLLECTION}/{created.intent_id}',
        'created': created,
    }

    yield context

    for path in (context['active'], context['dead'], context['attempt'], control_path):
        bind_store.delete(path)
    for collection in (attempts_db.INTENTS_COLLECTION, attempts_db.DEAD_LETTERS_COLLECTION):
        for document in bind_store.query(f'users/{uid}/{collection}'):
            bind_store.delete(f'users/{uid}/{collection}/{document.id}')
    bind_store.delete(f'users/{uid}')


def _bury(intent, *, reason, terminal_at=NOW, requeue_count=0):
    """Put the intent in the dead-letter collection, the way the delivery path does."""
    import database.chat_first_delivery_attempts as attempts_db

    # `dead_letter_payload` validates against DeadLetteredProactiveIntent, whose delivery_state is the
    # literal 'dead_letter'; the freshly created intent is still 'ready', so the terminal state and its
    # reason go in before the record is derived — exactly as the delivery path sets them.
    buried = intent['created'].model_copy(update={'delivery_state': 'dead_letter', 'dead_letter_reason': reason})
    payload = attempts_db.dead_letter_payload(buried, terminal_at=terminal_at)
    intent['store'].set(intent['dead'], payload)
    intent['store'].delete(intent['active'])
    # The counters live in the delivery-attempts document, not in the dead letter, and
    # `intent_with_delivery_attempt` overlays the WHOLE of it onto the intent — so the repair-age clock
    # (`last_rejection_at`) has to be written here or the record reads back with no terminal time at
    # all and is never eligible. That separation is the point of the sibling collection.
    intent['store'].set(
        intent['attempt'],
        {
            'requeue_count': requeue_count,
            'fetch_count': attempts_db.UNACKNOWLEDGED_FETCH_BUDGET,
            'last_fetched_at': terminal_at,
            'last_rejection_at': terminal_at,
        },
    )


def _requeue(intent, *, now, generation=GENERATION):
    import database.chat_first_delivery_attempts as attempts_db

    return attempts_db.requeue_transient_dead_letter(
        intent['uid'], intent['intent_id'], account_generation=generation, now=now, firestore_client=_client()
    )


def _exists(intent, key):
    stored = intent['store'].get(intent[key])
    return stored is not None and stored.exists


# --- transaction: the repair -----------------------------------------------------------------------


def test_a_transient_dead_letter_past_the_repair_age_is_revived(intent):
    import database.chat_first_delivery_attempts as attempts_db

    _bury(intent, reason=attempts_db.UNACKNOWLEDGED_DEAD_LETTER_REASON)
    ripe = NOW + attempts_db.TRANSIENT_DEAD_LETTER_REPAIR_AGE + timedelta(minutes=1)

    revived = _requeue(intent, now=ripe)

    assert revived is not None
    assert revived.delivery_state == 'ready'
    assert revived.requeue_count == 1
    # Three documents, one commit: the intent is back, the counters are reset, the tombstone is gone.
    assert _exists(intent, 'active'), 'the revived intent must be readable again'
    assert not _exists(intent, 'dead'), 'the dead letter must not survive its own repair'
    counters = intent['store'].get(intent['attempt']).data
    assert counters['fetch_count'] == 0
    assert counters['requeue_count'] == 1
    assert counters['last_rejection_at'] is None


def test_a_dead_letter_younger_than_the_repair_age_is_left_alone(intent):
    """The age exists so a message that just failed is not immediately retried at the user."""
    import database.chat_first_delivery_attempts as attempts_db

    _bury(intent, reason=attempts_db.UNACKNOWLEDGED_DEAD_LETTER_REASON)

    assert _requeue(intent, now=NOW + timedelta(minutes=5)) is None
    assert _exists(intent, 'dead')
    assert not _exists(intent, 'active')


def test_a_permanent_reason_is_never_revived(intent):
    """Only TRANSIENT_DEAD_LETTER_REASONS come back. A message buried for a permanent reason must stay
    buried however long it waits."""
    import database.chat_first_delivery_attempts as attempts_db

    _bury(intent, reason='permanent_rejection:user_opted_out')
    ripe = NOW + attempts_db.TRANSIENT_DEAD_LETTER_REPAIR_AGE + timedelta(days=30)

    assert _requeue(intent, now=ripe) is None
    assert _exists(intent, 'dead')


def test_an_intent_already_requeued_once_is_not_requeued_again(intent):
    """`requeue_count != 0` stops the loop: a message that failed twice is not worth a third attempt at
    the user, and without this check the repair would revive it forever."""
    import database.chat_first_delivery_attempts as attempts_db

    _bury(intent, reason=attempts_db.UNACKNOWLEDGED_DEAD_LETTER_REASON, requeue_count=1)
    ripe = NOW + attempts_db.TRANSIENT_DEAD_LETTER_REPAIR_AGE + timedelta(minutes=1)

    assert _requeue(intent, now=ripe) is None
    assert _exists(intent, 'dead')


def test_a_stale_account_generation_is_not_revived(intent):
    """After a wipe-and-resignup the old account's undelivered messages must not surface in the new one."""
    import database.chat_first_delivery_attempts as attempts_db

    _bury(intent, reason=attempts_db.UNACKNOWLEDGED_DEAD_LETTER_REASON)
    ripe = NOW + attempts_db.TRANSIENT_DEAD_LETTER_REPAIR_AGE + timedelta(minutes=1)

    assert _requeue(intent, now=ripe, generation=GENERATION + 1) is None
    assert _exists(intent, 'dead')


def test_repairing_a_dead_letter_that_does_not_exist_is_none_not_an_error(intent):
    import database.chat_first_delivery_attempts as attempts_db

    ripe = NOW + attempts_db.TRANSIENT_DEAD_LETTER_REPAIR_AGE + timedelta(minutes=1)

    assert _requeue(intent, now=ripe) is None
