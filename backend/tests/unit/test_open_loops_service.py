"""Open-loop card service: pending listing and answer transitions.

``list_pending_cards``/``answer_card`` are the functions the Review routes
call; these tests pin their contracts: the producer's recap-day rule per
cohort (legacy noon split vs ``CALLS_RECAP_MODE`` serving, with the
one-day fallback), per-timezone snooze/history days, ask-only vs strong task
links (Done completes a task only through the app's own completion path —
``mark_action_item_completed`` + reminder reconciliation #5085), the
drop → negative-example record, and the answer transaction's serialization of
concurrent answers.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from config.refactor_modes import uid_digest
import utils.open_loops.service as service
from database.open_loops import get_cards, get_loops, set_cards, upsert_loop
from tests.support.open_loops_store_fake import FakeFirestore
from utils.open_loops import store
from utils.other import daily_recap

NOW = datetime(2026, 10, 26, 15, 0, tzinfo=timezone.utc)
DATE_STR = '2026-10-26'
UID = 'u1'

LOOP_ID = 'ol-1'
TASK_TITLE = 'send Tyler the bullets for the Stably write-up'
STRONG_QUESTION = 'Did you send Tyler the bullets for the Stably write-up? (your task from Thu)'


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


def _card(
    card_id=LOOP_ID, state='pending', loop_id=LOOP_ID, question='Did Maya send the vendor write-up?', **overrides
):
    card = {
        'id': card_id,
        'loop_id': loop_id,
        'question': question,
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
    completions = []
    reminder_syncs = []
    monkeypatch.setattr(
        service.action_items_db,
        'mark_action_item_completed',
        Mock(side_effect=lambda uid, task_id, completed: completions.append((uid, task_id, completed)) or True),
    )
    monkeypatch.setattr(
        service.action_items_db,
        'get_action_item',
        Mock(
            return_value={
                'id': 'task-9',
                'description': TASK_TITLE,
                'completed': True,
                'due_at': datetime(2026, 10, 27, 9, 0, tzinfo=timezone.utc),
                'status': 'in_progress',
                'deleted': False,
            }
        ),
    )
    monkeypatch.setattr(
        service,
        'sync_action_item_reminder',
        Mock(side_effect=lambda **kwargs: reminder_syncs.append(kwargs)),
    )
    return SimpleNamespace(fake=fake, task_completions=completions, reminder_syncs=reminder_syncs)


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


def test_list_pending_cards_defaults_to_the_recaps_completed_local_day(cards_env):
    """Before noon local time the recap has only finished yesterday — that is
    the day whose pending cards list by default."""
    # 09:00 UTC = 10:00 in Europe/Lisbon (UTC+1 in October): before noon
    morning = datetime(2026, 10, 26, 9, 0, tzinfo=timezone.utc)
    set_cards(UID, '2026-10-25', [_card()], firestore_client=cards_env.fake)
    set_cards(UID, '2026-10-26', [_card(question='today card')], firestore_client=cards_env.fake)
    assert [
        c['question']
        for c in service.list_pending_cards(UID, tz='Europe/Lisbon', now=morning, firestore_client=cards_env.fake)
    ] == ['Did Maya send the vendor write-up?']
    # after noon local, the same calendar day lists
    afternoon = datetime(2026, 10, 26, 14, 0, tzinfo=timezone.utc)
    assert [
        c['question']
        for c in service.list_pending_cards(UID, tz='Europe/Lisbon', now=afternoon, firestore_client=cards_env.fake)
    ] == ['today card']


def test_list_pending_cards_for_a_day_the_pass_did_not_run(cards_env):
    assert service.list_pending_cards(UID, date_str='2026-10-20', firestore_client=cards_env.fake) == []


def test_cards_display_day_always_matches_the_producers_scheduled_date(monkeypatch):
    """Drift guard: the reader resolves the day with the producer's own rule
    (``daily_recap.scheduled_date``), every cohort and mode, so the listing can
    never aim at a day the pass did not date cards to."""
    cohorts = {'off': None, 'shadow': None, 'shadow-cohort': None, 'serve': None}
    for mode in cohorts:
        monkeypatch.setenv('CALLS_RECAP_MODE', mode)
        monkeypatch.setenv('CALLS_RECAP_MODE_SERVE_PERCENT', '0')
        if mode == 'shadow-cohort':
            monkeypatch.setenv('CALLS_RECAP_MODE_SERVE_UID_SHA256S', uid_digest(UID))
        for uid in (UID, 'someone-else'):
            for tz in ('Africa/Lagos', 'Pacific/Kiritimati', None):
                for utc_hour in (0, 2, 9, 12, 14, 23):
                    moment = datetime(2026, 10, 26, utc_hour, 30, tzinfo=timezone.utc)
                    # scheduled_date hands the caller a date or the legacy string;
                    # the reader always speaks the document id form.
                    assert service.cards_display_day(uid, tz, moment) == str(
                        daily_recap.scheduled_date(uid, tz, moment, service.recap_completed_day(tz, moment))
                    ), (mode, uid, tz, utc_hour)


def test_legacy_recap_users_keep_the_noon_split_morning_and_afternoon(cards_env, monkeypatch):
    """Without CALLS_RECAP_MODE serving, the pass dates cards with the
    noon-split rule — before noon yesterday, after noon today."""
    monkeypatch.setenv('CALLS_RECAP_MODE', 'off')
    tz = 'Africa/Lagos'  # UTC+1, no DST: 09:00/15:00 local = 08:00/14:00 UTC
    set_cards(UID, '2026-10-25', [_card(card_id='ol-25', question='yesterday card')], firestore_client=cards_env.fake)
    set_cards(UID, '2026-10-26', [_card(card_id='ol-26', question='today card')], firestore_client=cards_env.fake)
    morning = datetime(2026, 10, 26, 8, 0, tzinfo=timezone.utc)  # 09:00 local
    day, pending = service.list_owner_pending_cards(UID, tz=tz, now=morning, firestore_client=cards_env.fake)
    assert (day, [c['question'] for c in pending]) == ('2026-10-25', ['yesterday card'])
    afternoon = datetime(2026, 10, 26, 14, 0, tzinfo=timezone.utc)  # 15:00 local
    day, pending = service.list_owner_pending_cards(UID, tz=tz, now=afternoon, firestore_client=cards_env.fake)
    assert (day, [c['question'] for c in pending]) == ('2026-10-26', ['today card'])


def test_serving_recap_users_list_the_completed_day_morning_and_afternoon(cards_env, monkeypatch):
    """CALLS_RECAP_MODE serving dates cards with ``completed_day`` — always
    yesterday, no noon split (the pass runs ~01:00 local). At 15:00 local the
    noon split would read a document that does not exist until tomorrow's
    pass; the producer's rule keeps listing the day that was written."""
    monkeypatch.setenv('CALLS_RECAP_MODE', 'serve')
    tz = 'Africa/Lagos'  # UTC+1, no DST
    set_cards(UID, '2026-10-25', [_card(card_id='ol-25', question='yesterday card')], firestore_client=cards_env.fake)
    for local_hour, utc_hour in ((9, 8), (15, 14)):
        moment = datetime(2026, 10, 26, utc_hour, 0, tzinfo=timezone.utc)
        assert service.cards_display_day(UID, tz, moment) == '2026-10-25'
        day, pending = service.list_owner_pending_cards(UID, tz=tz, now=moment, firestore_client=cards_env.fake)
        assert (day, [c['question'] for c in pending]) == ('2026-10-25', ['yesterday card'])


def test_owner_listing_falls_back_to_the_previous_local_day(cards_env, monkeypatch):
    """A missed pass (the resolved day has no document) must not blank the
    surface: the previous day's still-pending cards are listed, under their own
    day — the answer endpoint's date path."""
    monkeypatch.setenv('CALLS_RECAP_MODE', 'serve')
    tz = 'Africa/Lagos'
    set_cards(UID, '2026-10-24', [_card(card_id='ol-24', question='older card')], firestore_client=cards_env.fake)
    afternoon = datetime(2026, 10, 26, 14, 0, tzinfo=timezone.utc)  # 15:00 local
    day, pending = service.list_owner_pending_cards(UID, tz=tz, now=afternoon, firestore_client=cards_env.fake)
    assert (day, [c['question'] for c in pending]) == ('2026-10-24', ['older card'])


def test_owner_listing_falls_back_only_over_pending_cards(cards_env, monkeypatch):
    monkeypatch.setenv('CALLS_RECAP_MODE', 'serve')
    tz = 'Africa/Lagos'
    set_cards(UID, '2026-10-25', [_card(state='done')], firestore_client=cards_env.fake)
    set_cards(UID, '2026-10-24', [_card(state='remind')], firestore_client=cards_env.fake)
    afternoon = datetime(2026, 10, 26, 14, 0, tzinfo=timezone.utc)
    assert service.list_owner_pending_cards(UID, tz=tz, now=afternoon, firestore_client=cards_env.fake) == (
        '2026-10-25',
        [],
    )


def test_owner_listing_does_not_reach_beyond_the_fallback_window(cards_env, monkeypatch):
    monkeypatch.setenv('CALLS_RECAP_MODE', 'serve')
    tz = 'Africa/Lagos'
    set_cards(UID, '2026-10-23', [_card(card_id='ol-23', question='stale card')], firestore_client=cards_env.fake)
    afternoon = datetime(2026, 10, 26, 14, 0, tzinfo=timezone.utc)
    assert service.list_owner_pending_cards(UID, tz=tz, now=afternoon, firestore_client=cards_env.fake) == (
        '2026-10-25',
        [],
    )


def test_answer_done_completes_a_strongly_linked_task_through_the_app_path(cards_env):
    loop = _loop(
        linked_task_id='task-9',
        task_link='model',
        linked_task_title=TASK_TITLE,
        linked_task_created_at='2026-10-22T09:00:00+00:00',
    )
    _seed(cards_env, [_card(question=STRONG_QUESTION)], loops=[loop])
    answered = service.answer_card(UID, LOOP_ID, 'done', date_str=DATE_STR, now=NOW, firestore_client=cards_env.fake)
    assert answered['state'] == 'done' and answered['answered_at']
    loop = get_loops(UID, firestore_client=cards_env.fake)[0]
    assert loop['status'] == 'resolved'
    assert loop['history'][-1]['status'] == 'resolved'
    # the app's own completion path: mark completed (stamps completed_at), then
    # reconcile the client-scheduled reminder from the task's final state
    assert cards_env.task_completions == [(UID, 'task-9', True)]
    assert len(cards_env.reminder_syncs) == 1
    sync = cards_env.reminder_syncs[0]
    assert sync['user_id'] == UID and sync['action_item_id'] == 'task-9'
    assert sync['completed'] is True and sync['deleted'] is False
    # the card document reflects the answer and no longer lists as pending
    assert service.list_pending_cards(UID, date_str=DATE_STR, firestore_client=cards_env.fake) == []


def test_answer_done_with_a_heuristic_link_is_ask_only(cards_env):
    """No model-asserted from_task_id: Done resolves the loop but never
    completes the task (the "Tyler: send deck" vs "send deck to investors"
    wrong-task completion blocker)."""
    loop = _loop(linked_task_id='task-9', task_link='heuristic', linked_task_title='send deck to investors')
    _seed(cards_env, [_card()], loops=[loop])
    answered = service.answer_card(UID, LOOP_ID, 'done', date_str=DATE_STR, now=NOW, firestore_client=cards_env.fake)
    assert answered['state'] == 'done'
    loop = get_loops(UID, firestore_client=cards_env.fake)[0]
    assert loop['status'] == 'resolved'
    assert cards_env.task_completions == []
    assert cards_env.reminder_syncs == []


def test_answer_done_skips_completion_when_the_card_text_does_not_name_the_task(cards_env):
    """Strong link, but the stored card never carried the task's description
    (e.g. an older card): the answer is not evidence about the task."""
    loop = _loop(linked_task_id='task-9', task_link='model', linked_task_title=TASK_TITLE, what='follow up with Tyler')
    _seed(cards_env, [_card(question='Did you follow up with Tyler?')], loops=[loop])
    answered = service.answer_card(UID, LOOP_ID, 'done', date_str=DATE_STR, now=NOW, firestore_client=cards_env.fake)
    assert answered['state'] == 'done'
    assert get_loops(UID, firestore_client=cards_env.fake)[0]['status'] == 'resolved'
    assert cards_env.task_completions == []


def test_answer_done_without_a_task_link_just_resolves(cards_env):
    _seed(cards_env, [_card()], loops=[_loop()])
    assert service.answer_card(UID, LOOP_ID, 'done', date_str=DATE_STR, now=NOW, firestore_client=cards_env.fake)
    assert cards_env.task_completions == []


def test_answer_remind_snoozes_two_days_in_the_users_timezone(cards_env):
    """Snooze (and history) days are the user's local day, not UTC: 23:30 UTC
    is already the next day in Pacific/Kiritimati (UTC+14)."""
    late_utc = datetime(2026, 10, 26, 23, 30, tzinfo=timezone.utc)  # 2026-10-27 13:30 local
    _seed(cards_env, [_card()])
    answered = service.answer_card(
        UID,
        LOOP_ID,
        'remind',
        date_str=DATE_STR,
        tz='Pacific/Kiritimati',
        now=late_utc,
        firestore_client=cards_env.fake,
    )
    assert answered['state'] == 'remind'
    loop = get_loops(UID, firestore_client=cards_env.fake)[0]
    assert loop['snoozed_until'] == '2026-10-29'  # local today (10-27) + 2
    assert loop['status'] == 'due_soon'  # remind never changes status
    # and the snooze gates surfacing until it passes
    assert not store.surfaceable(loop, service.local_today('Pacific/Kiritimati', late_utc))
    assert store.surfaceable(loop, service.local_today('Pacific/Kiritimati', late_utc) + timedelta(days=3))


def test_answer_drop_records_history_in_the_users_timezone(cards_env):
    late_utc = datetime(2026, 10, 26, 23, 30, tzinfo=timezone.utc)  # already 10-27 in UTC+14
    _seed(cards_env, [_card()])
    answered = service.answer_card(
        UID, LOOP_ID, 'drop', date_str=DATE_STR, tz='Pacific/Kiritimati', now=late_utc, firestore_client=cards_env.fake
    )
    assert answered['state'] == 'dropped'
    loop = get_loops(UID, firestore_client=cards_env.fake)[0]
    assert loop['status'] == 'dropped'
    assert loop['history'][-1]['date'] == '2026-10-27'  # the local day
    assert loop['negative_examples'] == [
        {'date': '2026-10-27', 'question': 'Did Maya send the vendor write-up?', 'value': 5}
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


def test_a_repeated_answer_never_touches_the_loop_again(cards_env):
    """The loop update belongs to the call whose transition committed, so a
    replayed answer is a no-op everywhere: no second snooze, resolve or
    negative example."""
    _seed(cards_env, [_card()])
    assert service.answer_card(UID, LOOP_ID, 'drop', date_str=DATE_STR, now=NOW, firestore_client=cards_env.fake)
    loop_after_answer = get_loops(UID, firestore_client=cards_env.fake)[0]
    assert loop_after_answer['status'] == 'dropped'
    assert (
        service.answer_card(UID, LOOP_ID, 'done', date_str=DATE_STR, now=NOW, firestore_client=cards_env.fake) is None
    )
    assert get_loops(UID, firestore_client=cards_env.fake)[0] == loop_after_answer


def test_answers_in_flight_never_resurrect_each_other(cards_env):
    """Done on card a while Drop on card b commits mid-flight: a's whole-
    document write used to restore b to pending from its stale read. The
    answer transaction aborts on that contention and re-reads, so both
    committed answers survive — and drop still records exactly one negative
    example."""
    _seed(
        cards_env,
        [_card(card_id='ol-a', loop_id='ol-a'), _card(card_id='ol-b', loop_id='ol-b')],
        loops=[_loop(id='ol-a', stable_key='ol-a'), _loop(id='ol-b', stable_key='ol-b')],
    )

    def drop_b_while_a_holds_its_read(path):
        cards_env.fake.on_transaction_read = None  # one shot: only a's read interleaves
        answered = service.answer_card(UID, 'ol-b', 'drop', date_str=DATE_STR, now=NOW, firestore_client=cards_env.fake)
        assert answered is not None and answered['state'] == 'dropped'

    cards_env.fake.on_transaction_read = drop_b_while_a_holds_its_read
    answered = service.answer_card(UID, 'ol-a', 'done', date_str=DATE_STR, now=NOW, firestore_client=cards_env.fake)
    assert answered is not None and answered['state'] == 'done'

    states = {c['id']: c['state'] for c in get_cards(UID, DATE_STR, firestore_client=cards_env.fake)}
    assert states == {'ol-a': 'done', 'ol-b': 'dropped'}
    loops = {l['id']: l for l in get_loops(UID, firestore_client=cards_env.fake)}
    assert loops['ol-a']['status'] == 'resolved'
    assert loops['ol-b']['status'] == 'dropped'
    assert len(loops['ol-b']['negative_examples']) == 1


def test_a_double_tap_answers_once_and_records_one_negative_example(cards_env):
    """Two identical answers racing on one card: exactly one transitions, the
    loser comes back as None (the route's 409), and the loop's drop history and
    negative examples are written once."""
    _seed(cards_env, [_card()])
    taps = []

    def first_tap_while_second_holds_its_read(path):
        cards_env.fake.on_transaction_read = None
        taps.append(
            service.answer_card(UID, LOOP_ID, 'drop', date_str=DATE_STR, now=NOW, firestore_client=cards_env.fake)
        )

    cards_env.fake.on_transaction_read = first_tap_while_second_holds_its_read
    second = service.answer_card(UID, LOOP_ID, 'drop', date_str=DATE_STR, now=NOW, firestore_client=cards_env.fake)

    assert taps[0]['state'] == 'dropped'
    assert second is None  # the retry found the card already answered
    loop = get_loops(UID, firestore_client=cards_env.fake)[0]
    assert loop['status'] == 'dropped'
    assert len(loop['negative_examples']) == 1
    assert [h['status'] for h in loop['history']].count('dropped') == 1


def test_task_completion_failure_never_rolls_back_the_loop_transition(cards_env, monkeypatch, caplog):
    _seed(
        cards_env,
        [_card(question=STRONG_QUESTION)],
        loops=[_loop(linked_task_id='task-9', task_link='model', linked_task_title=TASK_TITLE)],
    )
    monkeypatch.setattr(
        service.action_items_db,
        'mark_action_item_completed',
        Mock(side_effect=RuntimeError('tasks offline')),
    )
    answered = service.answer_card(UID, LOOP_ID, 'done', date_str=DATE_STR, now=NOW, firestore_client=cards_env.fake)
    assert answered['state'] == 'done'
    loop = get_loops(UID, firestore_client=cards_env.fake)[0]
    assert loop['status'] == 'resolved'


def test_owner_listing_never_falls_back_over_a_day_the_pass_ran(cards_env, monkeypatch):
    """Today's document exists but is fully answered (or the pass wrote zero
    cards): the listing stays empty instead of resurfacing yesterday's
    unanswered cards, whose loops may have expired or resolved since."""
    monkeypatch.setenv('CALLS_RECAP_MODE', 'serve')
    tz = 'Africa/Lagos'
    set_cards(UID, '2026-10-25', [_card(state='done')], firestore_client=cards_env.fake)
    set_cards(UID, '2026-10-24', [_card(card_id='ol-24', question='older card')], firestore_client=cards_env.fake)
    afternoon = datetime(2026, 10, 26, 14, 0, tzinfo=timezone.utc)
    assert service.list_owner_pending_cards(UID, tz=tz, now=afternoon, firestore_client=cards_env.fake) == (
        '2026-10-25',
        [],
    )
    set_cards(UID, '2026-10-25', [], firestore_client=cards_env.fake)
    assert service.list_owner_pending_cards(UID, tz=tz, now=afternoon, firestore_client=cards_env.fake) == (
        '2026-10-25',
        [],
    )


def test_answer_on_a_terminal_loop_never_re_resolves_or_completes_its_task(cards_env):
    loop = _loop(
        status='expired',
        linked_task_id='task-9',
        task_link='model',
        linked_task_title=TASK_TITLE,
    )
    _seed(cards_env, [_card(question=STRONG_QUESTION)], loops=[loop])
    answered = service.answer_card(UID, LOOP_ID, 'done', date_str=DATE_STR, now=NOW, firestore_client=cards_env.fake)
    assert answered['state'] == 'done'
    stored = get_loops(UID, firestore_client=cards_env.fake)[0]
    assert stored['status'] == 'expired' and stored['history'] == loop['history']
    assert cards_env.task_completions == []


def test_a_failed_loop_write_puts_the_card_back_so_a_retry_applies(cards_env, monkeypatch):
    _seed(cards_env, [_card()])
    real_upsert = service.open_loops_db.upsert_loop
    calls = {'n': 0}

    def flaky_upsert(*args, **kwargs):
        calls['n'] += 1
        if calls['n'] == 1:
            raise RuntimeError('firestore unavailable')
        return real_upsert(*args, **kwargs)

    monkeypatch.setattr(service.open_loops_db, 'upsert_loop', flaky_upsert)
    with pytest.raises(RuntimeError):
        service.answer_card(UID, LOOP_ID, 'drop', date_str=DATE_STR, now=NOW, firestore_client=cards_env.fake)
    # the card is pending again, not a silent 409 on retry
    assert [c['id'] for c in service.list_pending_cards(UID, date_str=DATE_STR, firestore_client=cards_env.fake)] == [
        LOOP_ID
    ]
    answered = service.answer_card(UID, LOOP_ID, 'drop', date_str=DATE_STR, now=NOW, firestore_client=cards_env.fake)
    assert answered['state'] == 'dropped'
    assert get_loops(UID, firestore_client=cards_env.fake)[0]['status'] == 'dropped'
