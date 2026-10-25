"""Open-loop card service: pending listing and answer transitions.

``list_pending_cards``/``answer_card`` are the functions PR 3's Review source
calls; these tests pin their contracts, including task completion through the
existing action-item update path and the drop → negative-example record.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

import utils.open_loops.service as service
from database.open_loops import get_cards, get_loops, set_cards, upsert_loop
from tests.support.open_loops_store_fake import FakeFirestore
from utils.open_loops import store

NOW = datetime(2026, 10, 26, 15, 0, tzinfo=timezone.utc)
DATE_STR = '2026-10-26'
UID = 'u1'

LOOP_ID = 'ol-1'


def _loop(**overrides):
    loop = {
        'id': LOOP_ID,
        'stable_key': 'ol-1',
        'kind': 'owed_to_user',
        'who': 'Maya',
        'what': 'send the vendor write-up',
        'by_when': None,
        'evidence': 'I will send it over tomorrow',
        'status': 'due_soon',
        'history': [{'date': '2026-10-26', 'status': 'due_soon', 'evidence': 'due Tuesday'}],
        'times_surfaced': 1,
        'last_surfaced_at': DATE_STR,
        'created_at': '2026-10-20T09:00:00+00:00',
        'last_activity_at': '2026-10-26T14:00:00+00:00',
        'source_conversation_ids': ['c1'],
        'source_title': 'Pricing sync',
        'source_started_at': '2026-10-20T10:00:00+00:00',
        'work_related': True,
    }
    loop.update(overrides)
    return loop


def _card(card_id=LOOP_ID, state='pending', loop_id=LOOP_ID, **overrides):
    card = {
        'id': card_id,
        'loop_id': loop_id,
        'question': 'Did Maya send the vendor write-up?',
        'context_line': "From Monday's Pricing sync, due Tuesday",
        'source_ref': 'Pricing sync (Monday), 2026-10-20',
        'polished': False,
        'value': 5,
        'state': state,
        'actions': ['done', 'remind', 'drop'],
        'generated_at': '2026-10-26T14:00:00+00:00',
    }
    card.update(overrides)
    return card


@pytest.fixture
def cards_env(monkeypatch):
    fake = FakeFirestore()
    task_completions = []
    update_action_item = Mock(
        side_effect=lambda uid, task_id, data: task_completions.append((uid, task_id, data)) or True
    )
    monkeypatch.setattr(service.action_items_db, 'update_action_item', update_action_item)
    return SimpleNamespace(fake=fake, task_completions=task_completions)


def _seed(env, cards, loops=None):
    set_cards(UID, DATE_STR, cards, firestore_client=env.fake)
    for loop in loops or [_loop()]:
        upsert_loop(UID, loop, firestore_client=env.fake)


def test_list_pending_cards_returns_only_pending_in_order(cards_env):
    _seed(cards_env, [_card('a'), _card('b', state='done'), _card('c')])
    pending = service.list_pending_cards(UID, date_str=DATE_STR, firestore_client=cards_env.fake)
    assert [card['id'] for card in pending] == ['a', 'c']
    limited = service.list_pending_cards(UID, limit=1, date_str=DATE_STR, firestore_client=cards_env.fake)
    assert [card['id'] for card in limited] == ['a']


def test_list_pending_cards_for_a_day_the_pass_did_not_run(cards_env):
    assert service.list_pending_cards(UID, date_str='2026-10-20', firestore_client=cards_env.fake) == []


def test_answer_done_resolves_the_loop_and_completes_a_linked_task(cards_env):
    _seed(cards_env, [_card()], loops=[_loop(linked_task_id='task-9')])
    answered = service.answer_card(UID, LOOP_ID, 'done', date_str=DATE_STR, now=NOW, firestore_client=cards_env.fake)
    assert answered['state'] == 'done' and answered['answered_at']
    loop = get_loops(UID, firestore_client=cards_env.fake)[0]
    assert loop['status'] == 'resolved'
    assert loop['history'][-1]['status'] == 'resolved'
    assert cards_env.task_completions == [(UID, 'task-9', {'completed': True})]
    # the card document reflects the answer and no longer lists as pending
    assert service.list_pending_cards(UID, date_str=DATE_STR, firestore_client=cards_env.fake) == []


def test_answer_done_without_a_task_link_just_resolves(cards_env):
    _seed(cards_env, [_card()], loops=[_loop()])
    assert service.answer_card(UID, LOOP_ID, 'done', date_str=DATE_STR, now=NOW, firestore_client=cards_env.fake)
    assert cards_env.task_completions == []


def test_answer_remind_snoozes_two_days(cards_env):
    _seed(cards_env, [_card()])
    answered = service.answer_card(UID, LOOP_ID, 'remind', date_str=DATE_STR, now=NOW, firestore_client=cards_env.fake)
    assert answered['state'] == 'remind'
    loop = get_loops(UID, firestore_client=cards_env.fake)[0]
    assert loop['snoozed_until'] == '2026-10-28'
    assert loop['status'] == 'due_soon'  # remind never changes status
    # and the snooze gates surfacing until it passes
    assert not store.surfaceable(loop, NOW.date())
    assert store.surfaceable(loop, NOW.date() + timedelta(days=3))


def test_answer_drop_marks_dropped_and_keeps_the_negative_example(cards_env):
    _seed(cards_env, [_card()])
    answered = service.answer_card(UID, LOOP_ID, 'drop', date_str=DATE_STR, now=NOW, firestore_client=cards_env.fake)
    assert answered['state'] == 'dropped'
    loop = get_loops(UID, firestore_client=cards_env.fake)[0]
    assert loop['status'] == 'dropped'
    assert loop['negative_examples'] == [
        {'date': DATE_STR, 'question': 'Did Maya send the vendor write-up?', 'value': 5}
    ]
    assert not store.surfaceable(loop, NOW.date() + timedelta(days=30))  # terminal forever


def test_answer_card_rejects_unknown_action_missing_card_and_repeats(cards_env):
    _seed(cards_env, [_card()])
    assert (
        service.answer_card(UID, LOOP_ID, 'snooze', date_str=DATE_STR, now=NOW, firestore_client=cards_env.fake) is None
    )
    assert service.answer_card(UID, 'nope', 'done', date_str=DATE_STR, now=NOW, firestore_client=cards_env.fake) is None
    first = service.answer_card(UID, LOOP_ID, 'remind', date_str=DATE_STR, now=NOW, firestore_client=cards_env.fake)
    assert first['state'] == 'remind'
    again = service.answer_card(UID, LOOP_ID, 'done', date_str=DATE_STR, now=NOW, firestore_client=cards_env.fake)
    assert again is None  # already answered
    # a missing day has nothing to answer
    assert (
        service.answer_card(UID, LOOP_ID, 'done', date_str='2026-10-01', now=NOW, firestore_client=cards_env.fake)
        is None
    )


def test_task_completion_failure_never_rolls_back_the_loop_transition(cards_env, monkeypatch, caplog):
    _seed(cards_env, [_card()], loops=[_loop(linked_task_id='task-9')])
    monkeypatch.setattr(
        service.action_items_db,
        'update_action_item',
        Mock(side_effect=RuntimeError('tasks offline')),
    )
    answered = service.answer_card(UID, LOOP_ID, 'done', date_str=DATE_STR, now=NOW, firestore_client=cards_env.fake)
    assert answered['state'] == 'done'
    loop = get_loops(UID, firestore_client=cards_env.fake)[0]
    assert loop['status'] == 'resolved'
