"""Daily summary generation is independent of push delivery, backfills missed days, and has a no-push create route."""

import asyncio
import time
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

import utils.other.notifications as notif


class _FakeConvo:
    transcript_segments = [object()]
    discarded = False


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
    monkeypatch.setattr(notif, 'deserialize_conversation', lambda d: _FakeConvo())

    def _generate(uid, conversations, date_str, *a, **k):
        generated_dates.append(date_str)
        return {'overview': f'summary-{date_str}', 'headline': 'H', 'day_emoji': 'X', 'id': f'id-{date_str}'}

    monkeypatch.setattr(notif, 'generate_comprehensive_daily_summary', _generate)
    monkeypatch.setattr(
        notif.daily_summaries_db,
        'create_daily_summary',
        lambda uid, payload: created.append(payload) or payload.get('id'),
    )
    monkeypatch.setattr(notif, 'send_notification', lambda *a, **k: sent.append({'args': a, 'kwargs': k}))

    # A coroutine, like the real one. The webhook is awaited inline now, so a sync stub would
    # hand asyncio.run a None and the harness itself would be the thing under test.
    # ``pushes_before`` records how many pushes had already gone out when the webhook ran,
    # which is what pins the ordering.
    webhooks = []

    async def _day_summary_webhook(uid, summary, summary_json=None):
        webhooks.append({'uid': uid, 'summary': summary, 'summary_json': summary_json, 'pushes_before': len(sent)})

    monkeypatch.setattr(notif, 'day_summary_webhook', _day_summary_webhook)
    return generated_dates, created, sent, released, webhooks


def test_tokenless_user_gets_a_record_and_no_push(monkeypatch):
    generated_dates, created, sent, _released, _webhooks = _install_generation_fakes(monkeypatch)
    notif._send_summary_notification(('u1', [], 'UTC'))
    assert created, 'a tokenless user must still get a daily summary record'
    assert generated_dates, 'generation must run without an FCM token'
    assert sent == []


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
    monkeypatch.setattr(notif, 'send_notification', MagicMock())

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
