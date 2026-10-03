"""Daily summary generation is independent of push delivery, backfills missed days, and has a no-push create route."""

import asyncio
import time
import threading
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

import utils.other.notifications as notif


class _FakeConvo:
    """A conversation whose day has something to summarize (non-empty overview).

    The pre-LLM gate declines a day whose conversations carry titles only, so
    the default fixture must carry summary body content; the thin-day decline
    has its own tests below.
    """

    transcript_segments = [object()]
    discarded = False
    apps_results: list = []

    def __init__(self, overview: str = 'You had a productive day.') -> None:
        self.structured = SimpleNamespace(overview=overview)


class _MinimumConvo:
    """The §1.7 deterministic minimum shape: a title, an empty overview, no app results."""

    transcript_segments = [object()]
    discarded = False
    apps_results: list = []

    def __init__(self) -> None:
        self.structured = SimpleNamespace(overview='')


def _install_generation_fakes(monkeypatch, *, existing_by_date=None, tokens_unused=True):
    generated_dates = []
    created = []
    sent = []

    existing_by_date = existing_by_date if existing_by_date is not None else {}

    released = []
    monkeypatch.setattr(notif, 'try_acquire_daily_summary_lock', lambda *_a, **_k: True)
    monkeypatch.setattr(notif, 'release_daily_summary_lock', lambda uid, date_str: released.append(date_str))
    monkeypatch.setattr(
        notif.daily_summaries_db,
        'get_daily_summary_by_date',
        lambda uid, date_str: existing_by_date.get(date_str),
    )
    monkeypatch.setattr(notif.conversations_db, 'get_conversations', lambda *a, **k: [{'is_locked': False, 'id': 'c1'}])
    monkeypatch.setattr(notif, 'deserialize_conversations', lambda items: [_FakeConvo() for _ in items])

    def _generate(uid, conversations, date_str, *a, **k):
        generated_dates.append(date_str)
        return {'overview': f'summary-{date_str}', 'headline': 'H', 'day_emoji': 'X', 'id': f'id-{date_str}'}

    monkeypatch.setattr(notif, 'generate_comprehensive_daily_summary', _generate)
    monkeypatch.setattr(
        notif.daily_summaries_db,
        'create_daily_summary',
        lambda uid, payload: created.append(payload) or payload.get('id'),
    )
    monkeypatch.setattr(notif.daily_summaries_db, 'mark_daily_summary_delivery_completed', lambda *_a: None)
    # Without this stub the scheduled path reaches the real MemoryService and issues a
    # live Firestore query from a unit test, which hangs under api_core's retry (the
    # empty-overview suite documents the same trap).
    monkeypatch.setattr(notif, 'memories_learned_payload', lambda *a, **k: [])
    monkeypatch.setattr(notif, 'send_notification_result', lambda *a, **k: sent.append({'args': a, 'kwargs': k}) or 1)

    # A coroutine, like the real one. The webhook is awaited inline now, so a sync stub would
    # hand asyncio.run a None and the harness itself would be the thing under test.
    # ``pushes_before`` records how many pushes had already gone out when the webhook ran,
    # which is what pins the ordering.
    webhooks = []

    async def _day_summary_webhook(uid, summary, summary_json=None):
        webhooks.append(
            {
                'uid': uid,
                'summary': summary,
                'summary_json': summary_json,
                'pushes_before': len(sent),
                # How much of the owner's own work had already finished. The webhook
                # runs last, so every backfill generation must be behind it.
                'generations_before': len(generated_dates),
            }
        )

    monkeypatch.setattr(notif, 'day_summary_webhook', _day_summary_webhook)
    return generated_dates, created, sent, released, webhooks


def test_tokenless_user_gets_a_record_and_no_push(monkeypatch):
    generated_dates, created, sent, _released, _webhooks = _install_generation_fakes(monkeypatch)
    notif._send_summary_notification(('u1', [], 'UTC'))
    assert created, 'a tokenless user must still get a daily summary record'
    assert generated_dates, 'generation must run without an FCM token'
    assert sent == []


def test_malformed_conversation_doc_is_skipped_not_fatal(monkeypatch):
    # #19759 migrated batch readers to deserialize_conversations; this generation path was
    # missed, so one malformed stored doc raised ValidationError — the on-demand recap 500'd
    # (leaving the day's lock held) and the scheduled path counted a generation_error.
    generated_dates, _created, _sent, _released, _webhooks = _install_generation_fakes(monkeypatch)
    from utils.conversations.factory import deserialize_conversations as real_batch

    now = datetime(2026, 6, 23, 12, 0)
    monkeypatch.setattr(
        notif.conversations_db,
        'get_conversations',
        lambda *a, **k: [
            {
                'id': 'valid-1',
                'created_at': now,
                'started_at': now,
                'finished_at': now,
                'structured': {'title': 'T', 'overview': 'You had a productive day.'},
                'transcript_segments': [
                    {'text': 'hello', 'speaker': 'SPEAKER_00', 'is_user': True, 'start': 0.0, 'end': 1.0}
                ],
            },
            {'id': 'corrupt-no-structured', 'created_at': now},  # missing required 'structured'
        ],
    )
    monkeypatch.setattr(notif, 'deserialize_conversations', real_batch)

    record, declined = notif.generate_daily_summary_on_demand('u1', '2026-06-23', now, now + timedelta(hours=1))

    assert record is not None, f'a valid conversation beside a malformed one must still generate (declined={declined})'
    assert generated_dates == ['2026-06-23']


def test_user_with_tokens_gets_record_and_push(monkeypatch):
    generated_dates, created, sent, _released, _webhooks = _install_generation_fakes(monkeypatch)
    notif._send_summary_notification(('u1', ['tok1'], 'UTC'))
    assert created
    assert generated_dates
    assert len(sent) == 1
    # Only the tokens kwarg proves delivery targeted this user's devices. The `or` on the uid
    # positional that used to sit here was always true, so the assertion passed with the tokens
    # dropped entirely — the exact regression this test exists to catch.
    assert sent[0]['kwargs'].get('tokens') == ['tok1']


def test_backfill_generates_missing_day_skips_present_without_llm_and_never_notifies(monkeypatch):
    display = notif._display_date_for_now('UTC')
    present = (display - timedelta(days=1)).strftime('%Y-%m-%d')
    missing = (display - timedelta(days=2)).strftime('%Y-%m-%d')
    existing = {present: {'id': 'already', 'date': present}}
    generated_dates, created, sent, _released, _webhooks = _install_generation_fakes(
        monkeypatch, existing_by_date=existing
    )

    notif._send_summary_notification(('u1', ['tok1'], 'UTC'))

    assert present not in generated_dates
    assert missing in generated_dates
    # Push is current-day only. A backfilled day must never notify.
    assert len(sent) == 1
    current = display.strftime('%Y-%m-%d')
    assert current in generated_dates


def test_backfill_cap_is_honored(monkeypatch):
    generated_dates, created, sent, _released, _webhooks = _install_generation_fakes(monkeypatch)
    notif._send_summary_notification(('u1', ['tok1'], 'UTC'))
    # Current day + at most 3 backfilled generations, even if 7 days are empty.
    assert len(generated_dates) == 1 + notif._DAILY_SUMMARY_BACKFILL_GENERATE_CAP
    assert len(sent) == 1


def test_existing_day_is_one_firestore_read_and_no_llm(monkeypatch):
    display = notif._display_date_for_now('UTC')
    date_str = display.strftime('%Y-%m-%d')
    reads = []

    def _by_date(uid, value):
        reads.append(value)
        return {'id': 'existing', 'date': value}

    monkeypatch.setattr(notif, 'try_acquire_daily_summary_lock', lambda *a, **k: True)
    monkeypatch.setattr(notif.daily_summaries_db, 'get_daily_summary_by_date', _by_date)
    gen = MagicMock()
    monkeypatch.setattr(notif, 'generate_comprehensive_daily_summary', gen)
    monkeypatch.setattr(notif.conversations_db, 'get_conversations', MagicMock())
    monkeypatch.setattr(notif, 'send_notification_result', MagicMock(return_value=1))

    record = notif.generate_and_store_daily_summary('u1', date_str, datetime.utcnow(), datetime.utcnow())
    assert record['id'] == 'existing'
    assert reads == [date_str]
    gen.assert_not_called()


# ---------------------------------------------------------------------------
# POST /v1/users/daily-summaries
# ---------------------------------------------------------------------------


def _route_patches(users_router, **overrides):
    defaults = {
        'enforce_chat_quota': MagicMock(),
        'notification_db': MagicMock(),
        'daily_summaries_db': MagicMock(),
        'get_generic_cache': MagicMock(return_value=None),
        'set_generic_cache': MagicMock(),
        'generate_daily_summary_on_demand': MagicMock(
            return_value=({'id': 'new-1', 'date': '2026-08-20', 'headline': 'H'}, None)
        ),
        'local_day_bounds_utc': MagicMock(return_value=(datetime.utcnow(), datetime.utcnow())),
    }
    defaults['notification_db'].get_user_time_zone.return_value = 'UTC'
    defaults['daily_summaries_db'].get_daily_summary_by_date.return_value = None
    defaults.update(overrides)
    return defaults


def test_create_route_happy_path():
    import routers.users as users_router

    patches = _route_patches(users_router)
    request = users_router.CreateDailySummaryRequest(date='2026-08-20')
    with patch.multiple(users_router, **patches):
        result = users_router.create_user_daily_summary(request, uid='u1', x_app_platform='macos')
    assert result['id'] == 'new-1'
    patches['enforce_chat_quota'].assert_called_once_with('u1', platform='macos')
    patches['generate_daily_summary_on_demand'].assert_called_once()
    patches['set_generic_cache'].assert_called_once()


def test_create_route_already_exists_does_not_bill():
    import routers.users as users_router

    existing = {'id': 'old-1', 'date': '2026-08-20'}
    db = MagicMock()
    db.get_daily_summary_by_date.return_value = existing
    patches = _route_patches(users_router, daily_summaries_db=db)
    request = users_router.CreateDailySummaryRequest(date='2026-08-20')
    with patch.multiple(users_router, **patches):
        result = users_router.create_user_daily_summary(request, uid='u1', x_app_platform='macos')
    assert result == existing
    patches['generate_daily_summary_on_demand'].assert_not_called()
    patches['set_generic_cache'].assert_not_called()


def test_create_route_malformed_date_is_422():
    import routers.users as users_router

    patches = _route_patches(users_router)
    request = users_router.CreateDailySummaryRequest(date='not-a-date')
    with patch.multiple(users_router, **patches):
        with pytest.raises(HTTPException) as exc:
            users_router.create_user_daily_summary(request, uid='u1', x_app_platform='macos')
    assert exc.value.status_code == 422
    patches['generate_daily_summary_on_demand'].assert_not_called()


def test_create_route_future_date_is_422():
    import routers.users as users_router

    patches = _route_patches(users_router)
    request = users_router.CreateDailySummaryRequest(date='2099-01-01')
    with patch.multiple(users_router, **patches):
        with pytest.raises(HTTPException) as exc:
            users_router.create_user_daily_summary(request, uid='u1', x_app_platform='macos')
    assert exc.value.status_code == 422
    patches['generate_daily_summary_on_demand'].assert_not_called()


def test_create_route_cooldown_is_429():
    import routers.users as users_router

    patches = _route_patches(users_router, get_generic_cache=MagicMock(return_value={'at': 'now'}))
    request = users_router.CreateDailySummaryRequest(date='2026-08-20')
    with patch.multiple(users_router, **patches):
        with pytest.raises(HTTPException) as exc:
            users_router.create_user_daily_summary(request, uid='u1', x_app_platform='macos')
    assert exc.value.status_code == 429
    patches['generate_daily_summary_on_demand'].assert_not_called()


def test_backfill_is_skipped_for_a_user_with_no_conversations(monkeypatch):
    """Dropping the FCM-token filter widened the fan-out to every user in the timezone.

    A dormant account must cost the day's own conversation lookups and nothing more — not seven
    lock writes, seven by-date reads and seven conversation queries chasing holes it can never
    fill.
    """
    generated_dates, created, sent, _released, _webhooks = _install_generation_fakes(monkeypatch)

    conversation_queries = []

    def _no_conversations(uid, start_date=None, end_date=None, date_field=None):
        conversation_queries.append(start_date)
        return []

    monkeypatch.setattr(notif.conversations_db, 'get_conversations', _no_conversations)

    lock_dates = []
    monkeypatch.setattr(
        notif, 'try_acquire_daily_summary_lock', lambda uid, date_str: lock_dates.append(date_str) or True
    )

    notif._send_summary_notification(('u1', [], 'UTC'))

    assert generated_dates == []
    assert created == []
    assert sent == []
    # One lock for the current day, and none for the seven days behind it.
    assert len(lock_dates) == 1, f'backfill must not walk back for a dormant user: {lock_dates}'
    # The current day is looked at twice at most (generation guard + the has-conversations probe).
    assert len(conversation_queries) <= 2, conversation_queries


def test_a_day_of_minimum_conversations_costs_zero_llm_calls_and_no_push(monkeypatch):
    """A §1.7-minimum day (titles + empty overviews, no app results) renders as
    titles only for the recap prompt; generating from that input is thin or
    hallucinated and then pushed (flip-review F-12). Decline before the LLM:
    no call, no record, no push — but the owner *was* recording, so backfill
    still walks their earlier days."""
    generated_dates, created, sent, released, _webhooks = _install_generation_fakes(monkeypatch)
    display = notif._display_date_for_now('UTC')
    today_str = display.strftime('%Y-%m-%d')
    start_utc, end_utc = notif.local_day_bounds_utc(display, 'UTC')

    def _conversations(uid, start_date=None, end_date=None, **_k):
        if start_date and start_date.date() >= display:
            return [{'is_locked': False, 'id': 'thin'}]
        return [{'is_locked': False, 'id': 'full'}]

    monkeypatch.setattr(notif.conversations_db, 'get_conversations', _conversations)
    monkeypatch.setattr(
        notif,
        'deserialize_conversations',
        lambda items: [_MinimumConvo() if d['id'] == 'thin' else _FakeConvo() for d in items],
    )

    record, created_flag, declined = notif._generate_and_store_daily_summary('u1', today_str, start_utc, end_utc)

    assert record is None and created_flag is False
    assert declined == notif._DECLINE_NOTHING_TO_SUMMARIZE
    assert generated_dates == [], 'the LLM must not be called for a titles-only day'
    assert created == [], 'no DailySummary document may be written'
    assert released == [today_str], 'a declined day must not stay locked'

    notif._send_summary_notification(('u1', ['tok1'], 'UTC'))

    assert sent == [], 'nothing may be pushed for a titles-only day'
    assert today_str not in generated_dates
    assert (
        len(generated_dates) == notif._DAILY_SUMMARY_BACKFILL_GENERATE_CAP
    ), 'the owner was recording, so the backfill walk still runs on content-bearing days'


def test_a_day_with_one_nonempty_overview_generates_exactly_once(monkeypatch):
    """The gate is an any(): a single conversation carrying summary body content
    is a day worth summarizing. Paid / pre-flip / mobile days look like this —
    they generate exactly as before."""
    generated_dates, created, sent, _released, _webhooks = _install_generation_fakes(monkeypatch)
    display = notif._display_date_for_now('UTC')

    def _conversations(uid, start_date=None, end_date=None, **_k):
        if start_date and start_date.date() >= display:
            # The current day: one §1.7-minimum conversation and one enriched one.
            return [{'is_locked': False, 'id': 'thin'}, {'is_locked': False, 'id': 'full'}]
        return [{'is_locked': False, 'id': 'full'}]

    monkeypatch.setattr(notif.conversations_db, 'get_conversations', _conversations)
    monkeypatch.setattr(
        notif,
        'deserialize_conversations',
        lambda items: [_MinimumConvo() if d['id'] == 'thin' else _FakeConvo() for d in items],
    )

    notif._send_summary_notification(('u1', ['tok1'], 'UTC'))

    assert len(generated_dates) == 1 + notif._DAILY_SUMMARY_BACKFILL_GENERATE_CAP
    assert len(sent) == 1
    assert created


def test_an_app_result_content_alone_counts_as_summary_content(monkeypatch):
    """The renderer prefers the first app result over the overview; a day whose
    only content lives in ``apps_results[0].content`` is summarizable."""
    generated_dates, _created, _sent, _released, _webhooks = _install_generation_fakes(monkeypatch)

    class _AppResultConvo:
        transcript_segments = [object()]
        discarded = False
        structured = SimpleNamespace(overview='')

        def __init__(self) -> None:
            self.apps_results = [SimpleNamespace(content='A busy day of meetings.')]

    monkeypatch.setattr(notif, 'deserialize_conversations', lambda items: [_AppResultConvo() for _ in items])
    record, created, _declined = notif._generate_and_store_daily_summary(
        'u1', '2026-08-20', datetime.utcnow(), datetime.utcnow()
    )

    assert record is not None and created is True
    assert generated_dates == ['2026-08-20']


def test_blank_first_app_result_does_not_skip_later_summary_content(monkeypatch):
    """A blank integration result must not hide usable content from a later result."""
    generated_dates, _created, _sent, _released, _webhooks = _install_generation_fakes(monkeypatch)

    class _BlankFirstAppResultConvo:
        transcript_segments = [object()]
        discarded = False
        structured = SimpleNamespace(overview='')

        def __init__(self) -> None:
            self.apps_results = [
                SimpleNamespace(content='  '),
                SimpleNamespace(content='A busy day of meetings.'),
            ]

    monkeypatch.setattr(notif, 'deserialize_conversations', lambda items: [_BlankFirstAppResultConvo() for _ in items])
    record, created, _declined = notif._generate_and_store_daily_summary(
        'u1', '2026-08-20', datetime.utcnow(), datetime.utcnow()
    )

    assert record is not None and created is True
    assert generated_dates == ['2026-08-20']


def test_action_items_alone_count_as_summary_content(monkeypatch):
    """The renderer also emits ``structured.action_items`` into the prompt body
    (render.py). A day whose conversations have empty overviews, no app
    results, but real action items is summarizable — declining it would drop
    recaps that previously generated."""
    generated_dates, created, _sent, _released, _webhooks = _install_generation_fakes(monkeypatch)

    class _ActionItemsConvo:
        transcript_segments = [object()]
        discarded = False
        apps_results: list = []
        structured = SimpleNamespace(overview='', action_items=[object()], events=[])

    monkeypatch.setattr(notif, 'deserialize_conversations', lambda items: [_ActionItemsConvo() for _ in items])
    record, created_flag, declined = notif._generate_and_store_daily_summary(
        'u1', '2026-08-20', datetime.utcnow(), datetime.utcnow()
    )

    assert record is not None and created_flag is True
    assert declined is None
    assert generated_dates == ['2026-08-20']
    assert created, 'an action-items day must still persist a DailySummary'


def test_events_alone_count_as_summary_content(monkeypatch):
    """Same as above for ``structured.events``: the renderer emits them into
    the prompt body, so they are summary content."""
    generated_dates, _created, _sent, _released, _webhooks = _install_generation_fakes(monkeypatch)

    class _EventsConvo:
        transcript_segments = [object()]
        discarded = False
        apps_results: list = []
        structured = SimpleNamespace(overview='', action_items=[], events=[object()])

    monkeypatch.setattr(notif, 'deserialize_conversations', lambda items: [_EventsConvo() for _ in items])
    record, created, _declined = notif._generate_and_store_daily_summary(
        'u1', '2026-08-20', datetime.utcnow(), datetime.utcnow()
    )

    assert record is not None and created is True
    assert generated_dates == ['2026-08-20']


def test_empty_action_items_and_events_do_not_rescue_a_titles_only_day(monkeypatch):
    """``action_items=[]``/``events=[]`` are the §1.7 deterministic minimum's
    neutral empties — they must not flip the gate, and neither do attendee
    names (presence labels, not summary content): a titles-only day still
    declines before the LLM."""
    generated_dates, created, sent, released, _webhooks = _install_generation_fakes(monkeypatch)

    class _EmptyListsConvo:
        transcript_segments = [object()]
        discarded = False
        apps_results: list = []

        def __init__(self) -> None:
            self.structured = SimpleNamespace(overview='', action_items=[], events=[])

    monkeypatch.setattr(notif, 'deserialize_conversations', lambda items: [_EmptyListsConvo() for _ in items])
    record, created_flag, declined = notif._generate_and_store_daily_summary(
        'u1', '2026-08-20', datetime.utcnow(), datetime.utcnow()
    )

    assert record is None and created_flag is False
    assert declined == notif._DECLINE_NOTHING_TO_SUMMARIZE
    assert generated_dates == []
    assert created == []
    assert sent == []
    assert released == ['2026-08-20']


def test_a_day_declined_before_the_llm_releases_its_lock(monkeypatch):
    """The on-demand button used to poison the day it was pressed on.

    Every guard between the lock and the LLM call returned while still holding a 2h key, so a
    press on a quiet evening left the 22:00 cron tick unable to acquire the lock — and that day
    never got a recap at all. A guard that spends no tokens must give the day back.
    """
    _generated, _created, _sent, released, _webhooks = _install_generation_fakes(monkeypatch)
    monkeypatch.setattr(notif.conversations_db, 'get_conversations', lambda *a, **k: [])

    record, created, declined = notif._generate_and_store_daily_summary(
        'u1', '2026-08-20', datetime.utcnow(), datetime.utcnow()
    )

    assert record is None and created is False
    assert declined == notif._DECLINE_NO_CONVERSATIONS
    assert released == ['2026-08-20'], 'a declined day must not stay locked for the full TTL'


def test_losing_the_lock_does_not_release_another_workers_day(monkeypatch):
    """Releasing on decline must not turn into releasing a lock this call never took."""
    _generated, _created, _sent, released, _webhooks = _install_generation_fakes(monkeypatch)
    monkeypatch.setattr(notif, 'try_acquire_daily_summary_lock', lambda *_a, **_k: False)

    _record, _created_flag, declined = notif._generate_and_store_daily_summary(
        'u1', '2026-08-20', datetime.utcnow(), datetime.utcnow()
    )

    assert declined == notif._DECLINE_LOCKED
    assert released == []


def test_a_day_of_only_locked_conversations_still_backfills(monkeypatch):
    """`is_locked` conversations prove the owner was recording, so their older days are worth
    walking back for. Classifying the day as `no_conversations` skipped the backfill entirely
    for exactly the accounts that had one."""
    generated_dates, _created, _sent, _released, _webhooks = _install_generation_fakes(monkeypatch)
    display = notif._display_date_for_now('UTC')
    today = display.strftime('%Y-%m-%d')

    def _conversations(uid, start_date=None, end_date=None, **k):
        # Only the current day is all-locked; the backfill days have usable conversations.
        if start_date and start_date.date() >= display:
            return [{'is_locked': True, 'id': 'c1'}]
        return [{'is_locked': False, 'id': 'c2'}]

    monkeypatch.setattr(notif.conversations_db, 'get_conversations', _conversations)
    notif._send_summary_notification(('u1', ['tok1'], 'UTC'))

    assert today not in generated_dates
    assert generated_dates, 'an owner whose day was all-locked must still have earlier days filled'


def test_create_route_does_not_arm_the_cooldown_when_nothing_was_generated():
    """Arming before the call charged a user for an attempt that spent no tokens: they got a 400
    and then 30s of 429 on the retry that would have worked once they recorded something."""
    import routers.users as users_router

    patches = _route_patches(
        users_router, generate_daily_summary_on_demand=MagicMock(return_value=(None, 'no_conversations'))
    )
    request = users_router.CreateDailySummaryRequest(date='2026-08-20')
    with patch.multiple(users_router, **patches):
        with pytest.raises(HTTPException) as exc:
            users_router.create_user_daily_summary(request, uid='u1', x_app_platform='macos')
    assert exc.value.status_code == 400
    patches['set_generic_cache'].assert_not_called()


def test_create_route_reports_contention_as_retryable_not_as_an_empty_day():
    """A held day lock means someone is summarizing this day right now. Reporting that as
    'nothing to summarize' told the user their day was empty at the moment it was being filled."""
    import routers.users as users_router

    patches = _route_patches(
        users_router,
        generate_daily_summary_on_demand=MagicMock(return_value=(None, users_router.DAILY_SUMMARY_DECLINE_LOCKED)),
    )
    request = users_router.CreateDailySummaryRequest(date='2026-08-20')
    with patch.multiple(users_router, **patches):
        with pytest.raises(HTTPException) as exc:
            users_router.create_user_daily_summary(request, uid='u1', x_app_platform='macos')
    assert exc.value.status_code == 409
    patches['set_generic_cache'].assert_not_called()


def test_webhook_completes_before_the_user_call_returns(monkeypatch):
    """The daily-summary webhook is owned by this call, not handed to a pool.

    Regression for #12530: the webhook used to be
    ``postprocess_executor.submit(asyncio.run, day_summary_webhook(...))``. That had two
    defects. ``_send_summary_notification`` is itself dispatched through
    ``run_blocking(postprocess_executor, ...)``, so the submit made the function its own
    child on the pool it was running on. And nothing owned the result: the per-user
    ``asyncio.wait_for`` budget covers only this call, and the Cloud Run Job exits without
    joining the pool, so a queued webhook died with the container — logged as
    ``coroutine 'day_summary_webhook' was never awaited`` right before exit.

    Making ``submit`` raise is what keeps this honest: asserting only that the webhook ran
    would still pass if someone reintroduced the submit alongside an inline call.
    """

    def _explode(*_args, **_kwargs):
        raise AssertionError('the daily summary webhook must not be submitted back to postprocess_executor')

    _generated, _created, sent, _released, webhooks = _install_generation_fakes(monkeypatch)
    monkeypatch.setattr(notif.postprocess_executor, 'submit', _explode)

    notif._send_summary_notification(('u1', ['tok1'], 'UTC'))

    # Populated by the time the call returns: nothing is left in flight for the job to drop.
    assert len(webhooks) == 1
    assert webhooks[0]['uid'] == 'u1'
    # The push is the owner-visible artifact and goes first; the webhook is developer integration.
    assert webhooks[0]['pushes_before'] == 1
    assert len(sent) == 1


def test_tokenless_user_still_reaches_their_webhook(monkeypatch):
    """The webhook sits outside the FCM-token guard, exactly as it did before the fix.

    The old code submitted the webhook *before* the ``if not tokens: return`` early exit.
    Moving the call after the push would silently drop the webhook for every user without a
    token unless the guard is restructured, which is why the push is a branch rather than an
    early return.
    """
    _generated, created, sent, _released, webhooks = _install_generation_fakes(monkeypatch)

    notif._send_summary_notification(('u1', [], 'UTC'))

    assert created, 'a tokenless user must still get a daily summary record'
    assert sent == [], 'no FCM token means no push'
    assert len(webhooks) == 1, 'a tokenless user must still reach their developer webhook'
    assert webhooks[0]['pushes_before'] == 0


def test_webhook_receives_the_dict_payload_as_summary_json(monkeypatch):
    """``summary_json`` carries the real object; ``summary`` stays the legacy repr string."""
    _generated, created, _sent, _released, webhooks = _install_generation_fakes(monkeypatch)

    notif._send_summary_notification(('u1', ['tok1'], 'UTC'))

    current = notif._display_date_for_now('UTC').strftime('%Y-%m-%d')

    assert len(webhooks) == 1
    payload = webhooks[0]['summary_json']
    assert isinstance(payload, dict)
    # The generated record for the current day, not merely "some dict".
    assert payload['overview'] == f'summary-{current}'
    assert payload['id'] == f'id-{current}'
    assert webhooks[0]['summary'] == str(payload)


def test_a_failing_webhook_does_not_cost_the_user_their_recap(monkeypatch, caplog):
    """A webhook fault is contained, logged, and never fails the user.

    The old ``postprocess_executor.submit`` swallowed every exception into a Future nobody
    read. That hid real faults, but it also meant a broken webhook could not cost the owner
    their recap. Running inline moves the fault onto this call, so it has to be caught
    explicitly: ``_send_summary_notification`` is what the per-user gather counts, and an
    escaping webhook error would mark a user whose push already went out as failed.
    """
    _generated, created, sent, _released, _webhooks = _install_generation_fakes(monkeypatch)

    async def _boom(*_args, **_kwargs):
        raise RuntimeError('webhook receiver is down')

    monkeypatch.setattr(notif, 'day_summary_webhook', _boom)

    notif._send_summary_notification(('u1', ['tok1'], 'UTC'))

    assert created, 'the summary record must survive a webhook failure'
    assert len(sent) == 1, 'the push must survive a webhook failure'
    # Containment without the log line is the old swallowed Future by another name: the
    # fault disappears and #12530's evidence never reappears. Assert the record, not just
    # that nothing raised.
    assert any(
        'daily_summary_webhook_failed' in record.getMessage() for record in caplog.records
    ), 'a contained webhook fault must still be reported'


def test_a_slow_webhook_cannot_spend_the_users_recap_budget(monkeypatch, caplog):
    """The webhook is bounded inside the per-user budget it now shares.

    Running it inline gave it an owner but moved its cost onto the user. day_summary_webhook
    posts through the shared client (30s read timeout, retries at 1/5/30s), so without its
    own bound a slow receiver could burn most of DAILY_SUMMARY_USER_BUDGET_SECONDS and get a
    user whose push had already been delivered marked reason=user_budget_exceeded — which
    counts toward DAILY_SUMMARY_MAX_ABANDONED_USERS and can abort the rest of the hour group.
    """
    _generated, created, sent, _released, _webhooks = _install_generation_fakes(monkeypatch)
    monkeypatch.setattr(notif, 'DAILY_SUMMARY_WEBHOOK_BUDGET_SECONDS', 0.05)

    async def _hangs(*_args, **_kwargs):
        await asyncio.sleep(30)

    monkeypatch.setattr(notif, 'day_summary_webhook', _hangs)

    started = time.monotonic()
    notif._send_summary_notification(('u1', ['tok1'], 'UTC'))
    elapsed = time.monotonic() - started

    assert elapsed < 5, f'the webhook must be abandoned at its own budget, took {elapsed:.1f}s'
    assert created, 'the summary record must survive a hanging webhook'
    assert len(sent) == 1, 'the push must survive a hanging webhook'
    assert any('daily_summary_webhook_failed' in record.getMessage() for record in caplog.records)


def test_the_webhook_runs_after_the_owner_backfill(monkeypatch):
    """The developer webhook is last, behind the owner's own backfill walk.

    Running it inline gave it an owner but put its cost inside the per-user budget
    that the backfill also spends. Ahead of the backfill, a slow receiver could take
    seconds the owner's missing days needed and tip a marginal user into
    ``user_budget_exceeded`` — a developer webhook charging the owner for its own
    latency, which is the rule this fix exists to uphold. Last means it can only
    ever spend budget nobody else still wants.
    """
    generated_dates, _created, _sent, _released, webhooks = _install_generation_fakes(monkeypatch)

    notif._send_summary_notification(('u1', ['tok1'], 'UTC'))

    assert len(webhooks) == 1
    assert len(generated_dates) == 1 + notif._DAILY_SUMMARY_BACKFILL_GENERATE_CAP
    assert webhooks[0]['generations_before'] == len(
        generated_dates
    ), 'the webhook must run after every backfill generation, not before them'


def test_a_dormant_day_sends_no_webhook(monkeypatch):
    """The ``finally`` must not invent a webhook for a day that produced nothing.

    A dormant owner declines the day, so ``_send_summary_notification`` returns
    before the backfill walk with nothing created and no payload to send. Running
    the delivery from ``finally`` puts it on that exit path too, so the guard that
    keeps it silent has to be pinned: a ``finally`` that fired unconditionally
    would push an empty recap to every dormant account every night.

    The other half of the claim — that the ``finally`` genuinely delivers on an
    unusual exit — belongs to ``test_a_backfill_failure_does_not_swallow_the_webhook``,
    which reaches it with a real payload in hand.
    """
    generated_dates, created, sent, _released, webhooks = _install_generation_fakes(monkeypatch)
    monkeypatch.setattr(notif, 'release_daily_summary_lock', lambda *_a, **_k: None)

    # Current day generates and pushes; every earlier day is declined, so the
    # dormant-owner branch returns before the backfill.
    monkeypatch.setattr(notif.conversations_db, 'get_conversations', lambda *a, **k: [])

    notif._send_summary_notification(('u1', ['tok1'], 'UTC'))

    assert generated_dates == [], 'precondition: nothing to summarise, so the run declines'
    assert webhooks == [], 'no summary was created, so there is no webhook to send'


def test_a_backfill_failure_does_not_swallow_the_webhook(monkeypatch):
    """A raising backfill must not cost the user their webhook.

    The webhook belongs to the current day, which was already generated, stored and
    pushed by the time the backfill runs. Losing it because a *later* day's walk
    blew up would be the unowned-work defect again, one frame further out.
    """
    _generated, created, sent, _released, webhooks = _install_generation_fakes(monkeypatch)

    def _boom(*_args, **_kwargs):
        raise RuntimeError('backfill exploded')

    monkeypatch.setattr(notif, '_backfill_recent_daily_summaries', _boom)

    with pytest.raises(RuntimeError):
        notif._send_summary_notification(('u1', ['tok1'], 'UTC'))

    assert created, 'the current day was stored before the backfill ran'
    assert len(sent) == 1, 'and pushed'
    assert len(webhooks) == 1, 'so its webhook must still have been sent'


def test_scheduled_tokens_are_read_only_for_a_new_recap(monkeypatch):
    generated_dates, created, sent, _released, _webhooks = _install_generation_fakes(monkeypatch)
    monkeypatch.setattr(notif, '_backfill_recent_daily_summaries', lambda *_a: None)
    reads = []
    monkeypatch.setattr(
        notif.notification_db, 'get_all_tokens', lambda uid, **kwargs: reads.append((uid, kwargs)) or ['tok1']
    )
    user = ('uid1', notif.summary_budget.DeferredTokens('legacy'), 'UTC')
    notif._send_summary_notification(user)
    assert reads == [('uid1', {'legacy_token': 'legacy', 'user_document_loaded': True})]
    assert len(created) == len(sent) == 1
    assert sent[0]['kwargs']['tokens'] == ['tok1']

    # A repeated tick encounters the durable record, even after Redis expiry.
    monkeypatch.setattr(notif.daily_summaries_db, 'get_daily_summary_by_date', lambda *_a: created[0])
    notif._send_summary_notification(user)
    assert len(reads) == 1
    assert len(created) == len(sent) == 1


def test_dormant_or_contended_owner_costs_no_token_reads(monkeypatch):
    _install_generation_fakes(monkeypatch)
    monkeypatch.setattr(
        notif.notification_db, 'get_all_tokens', lambda *_a: (_ for _ in ()).throw(AssertionError('token read'))
    )
    monkeypatch.setattr(notif.conversations_db, 'get_conversations', lambda *_a, **_k: [])
    notif._send_summary_notification(('uid1', None, 'UTC'))
    monkeypatch.setattr(notif, 'try_acquire_daily_summary_lock', lambda *_a: False)
    notif._send_summary_notification(('uid1', None, 'UTC'))


def test_token_read_failure_cannot_persist_an_undeliverable_recap(monkeypatch):
    generated, created, sent, released, _webhooks = _install_generation_fakes(monkeypatch)
    monkeypatch.setattr(notif, '_backfill_recent_daily_summaries', lambda *_a: None)

    def unavailable(_uid):
        raise RuntimeError('token query unavailable')

    monkeypatch.setattr(notif.notification_db, 'get_all_tokens', unavailable)
    with pytest.raises(RuntimeError, match='token query unavailable'):
        notif._send_summary_notification(('uid1', None, 'UTC'))
    assert generated == created == sent == []
    assert len(released) == 1
    monkeypatch.setattr(notif.notification_db, 'get_all_tokens', lambda _uid: ['tok1'])
    notif._send_summary_notification(('uid1', None, 'UTC'))
    assert len(generated) == len(created) == len(sent) == 1


def test_failed_generation_releases_its_day_lock_for_the_next_tick(monkeypatch):
    generated, created, sent, released, _webhooks = _install_generation_fakes(monkeypatch)
    monkeypatch.setattr(notif, '_backfill_recent_daily_summaries', lambda *_a: None)
    working_generator = notif.generate_comprehensive_daily_summary

    def unavailable(*_args, **_kwargs):
        raise RuntimeError('generation unavailable')

    monkeypatch.setattr(notif, 'generate_comprehensive_daily_summary', unavailable)
    with pytest.raises(RuntimeError, match='generation unavailable'):
        notif._send_summary_notification(('uid1', ['tok1'], 'UTC'))
    assert generated == created == sent == []
    assert len(released) == 1
    monkeypatch.setattr(notif, 'generate_comprehensive_daily_summary', working_generator)
    notif._send_summary_notification(('uid1', ['tok1'], 'UTC'))
    assert len(generated) == len(created) == len(sent) == 1


def test_failed_push_retries_stored_recap_once_without_regeneration(monkeypatch):
    generated, created, sent, released, webhooks = _install_generation_fakes(monkeypatch)
    monkeypatch.setattr(notif, '_backfill_recent_daily_summaries', lambda *_a: None)
    working_send = notif.send_notification_result
    monkeypatch.setattr(notif, 'send_notification_result', lambda *_a, **_k: 0)
    cohort = datetime(2026, 10, 3, 11, 45, tzinfo=timezone.utc)
    user = ('uid1', ['tok1'], 'UTC', cohort)

    with pytest.raises(notif.DailySummaryDeliveryError):
        notif._send_summary_notification(user)
    assert len(generated) == len(created) == len(released) == 1
    assert sent == webhooks == []

    monkeypatch.setattr(notif.daily_summaries_db, 'get_daily_summary_by_date', lambda *_a: created[0])
    monkeypatch.setattr(notif, 'send_notification_result', working_send)
    notif._send_summary_notification((*user, True, True))
    assert len(generated) == len(created) == len(sent) == len(webhooks) == 1
    notif._send_summary_notification(user)
    assert len(generated) == len(created) == len(sent) == len(webhooks) == 1


def test_contended_retry_stays_pending_without_releasing_another_workers_lock(monkeypatch):
    _generated, _created, sent, released, _webhooks = _install_generation_fakes(monkeypatch)
    monkeypatch.setattr(notif, 'try_acquire_daily_summary_lock', lambda *_a: False)
    with pytest.raises(RuntimeError, match='retry still locked'):
        notif._send_summary_notification(('uid1', ['tok1'], 'UTC', None, False, True))
    assert sent == released == []


@pytest.mark.parametrize('late_push_succeeds', [False, True])
def test_timeout_after_persistence_retries_uncertain_push_and_honors_late_receipt(monkeypatch, late_push_succeeds):
    generated, created, sent, _released, _webhooks = _install_generation_fakes(monkeypatch)
    monkeypatch.setattr(notif, '_backfill_recent_daily_summaries', lambda *_a: None)
    stored = {}
    receipts = []
    monkeypatch.setattr(notif.daily_summaries_db, 'get_daily_summary_by_date', lambda *_a: stored or None)

    def create(_uid, payload):
        created.append(payload)
        stored.update(payload)
        return payload['id']

    def acknowledge(_uid, summary_id):
        assert summary_id == stored['id']
        stored['notification_delivery_completed'] = True
        receipts.append(summary_id)

    monkeypatch.setattr(notif.daily_summaries_db, 'create_daily_summary', create)
    monkeypatch.setattr(notif.daily_summaries_db, 'mark_daily_summary_delivery_completed', acknowledge)
    monkeypatch.setattr(notif, 'DAILY_SUMMARY_USER_BUDGET_SECONDS', 0.05)
    entered_push, release_push, worker_finished = threading.Event(), threading.Event(), threading.Event()
    send_attempts = []
    working_send = notif.send_notification_result

    def blocked_send(*args, **kwargs):
        assert stored, 'the real worker must persist the recap before the timeout'
        send_attempts.append(args)
        entered_push.set()
        assert release_push.wait(timeout=5)
        return working_send(*args, **kwargs) if late_push_succeeds else 0

    monkeypatch.setattr(notif, 'send_notification_result', blocked_send)
    working_worker = notif._send_summary_notification

    def worker(user):
        try:
            working_worker(user)
        finally:
            worker_finished.set()

    monkeypatch.setattr(notif, '_send_summary_notification', worker)
    cohort = datetime(2026, 10, 3, 11, 45, tzinfo=timezone.utc)
    user = ('uid1', ['tok1'], 'UTC', cohort, False, False)
    stats = notif.DailySummaryJobStats()
    try:
        asyncio.run(notif._send_bulk_summary_notification([user], stats=stats, target_hour=11))
        assert entered_push.is_set()
        assert stats.timed_out == 1
        assert stats.retry_recipients == {'uid1': True}, 'wait_for must mark unacknowledged delivery as uncertain'
    finally:
        release_push.set()
        assert worker_finished.wait(timeout=5)

    monkeypatch.setattr(notif, 'send_notification_result', working_send)
    retry_stats = notif.DailySummaryJobStats(retry_recipients=dict(stats.retry_recipients))
    asyncio.run(
        notif._send_bulk_summary_notification(
            [(*user[:4], stats.retry_recipients['uid1'], True)], stats=retry_stats, target_hour=11
        )
    )
    assert len(generated) == len(created) == len(sent) == len(receipts) == 1
    assert retry_stats.retry_recipients == {}
    assert len(send_attempts) == 1


@pytest.mark.parametrize('later_failure', ['backfill', 'webhook', 'timeout'])
def test_retry_push_acknowledged_before_later_work_cannot_be_sent_again(monkeypatch, later_failure):
    generated, created, sent, _released, _webhooks = _install_generation_fakes(monkeypatch)
    cohort = datetime(2026, 10, 3, 11, 45, tzinfo=timezone.utc)
    stored = {'id': 'stored-recap', 'date': '2026-10-02', 'headline': 'H'}
    monkeypatch.setattr(notif.daily_summaries_db, 'get_daily_summary_by_date', lambda *_a: stored)
    order = []

    def acknowledge(_uid, summary_id):
        assert summary_id == stored['id']
        stored['notification_delivery_completed'] = True
        order.append('acknowledged')

    monkeypatch.setattr(notif.daily_summaries_db, 'mark_daily_summary_delivery_completed', acknowledge)
    release_later_work, worker_finished = threading.Event(), threading.Event()
    working_worker = notif._send_summary_notification

    def worker(user):
        try:
            working_worker(user)
        finally:
            worker_finished.set()

    monkeypatch.setattr(notif, '_send_summary_notification', worker)
    monkeypatch.setattr(notif, 'DAILY_SUMMARY_USER_BUDGET_SECONDS', 0.05)

    def later_work(*_args):
        assert len(sent) == 1 and stored['notification_delivery_completed']
        order.append('later_work')
        if later_failure == 'timeout':
            assert release_later_work.wait(timeout=5)
            return
        raise RuntimeError('later work failed')

    monkeypatch.setattr(
        notif, '_backfill_recent_daily_summaries', later_work if later_failure != 'webhook' else lambda *_a: None
    )
    if later_failure == 'webhook':
        monkeypatch.setattr(notif, '_deliver_day_summary_webhook', later_work)
    user = ('uid1', ['tok1'], 'UTC', cohort, True, True)
    stats = notif.DailySummaryJobStats(retry_recipients={'uid1': True})
    try:
        asyncio.run(notif._send_bulk_summary_notification([user], stats=stats, target_hour=11))
    finally:
        release_later_work.set()
        assert worker_finished.wait(timeout=5)
    if later_failure == 'timeout':
        assert stats.timed_out == 1, 'exercise wait_for abandoning work after successful delivery'
    assert stats.retry_recipients == {'uid1': False}, 'post-delivery failure must clear the push retry flag'
    assert order == ['acknowledged', 'later_work']
    assert generated == created == []

    # Even a stale saved cursor with a true delivery flag must respect the receipt.
    monkeypatch.setattr(notif, '_backfill_recent_daily_summaries', lambda *_a: None)
    retry_stats = notif.DailySummaryJobStats(retry_recipients={'uid1': True})
    asyncio.run(notif._send_bulk_summary_notification([user], stats=retry_stats, target_hour=11))
    assert retry_stats.retry_recipients == {}
    assert len(sent) == 1
