"""The open-loops daily pass as a dispatched sibling of the daily recap job.

Pins the wiring contract: the recap worker finishes its own work first —
summary, push, backfill, webhook — and only *returns* the pass request; the
coordinator then runs the pass on a dedicated executor under its own budget.
A slow or failing pass can never delay the webhook, spend the user's recap
budget, mark a recipient timed_out, count toward the abandoned-user limit or
change recap ordering.
"""

import asyncio
import sys
import time
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

import utils.open_loops.daily as open_loops_daily
from utils.other import notifications as notif

UID = 'u1'


@pytest.fixture
def recap_env(monkeypatch):
    today = datetime.now(timezone.utc).strftime('%Y-%m-%d')

    pass_calls = []

    def fake_run_daily_pass(uid, **kwargs):
        pass_calls.append((uid, kwargs))
        return 'ran'

    monkeypatch.setattr(open_loops_daily, 'run_daily_pass', fake_run_daily_pass)

    monkeypatch.setattr(notif, 'generated_compute_allowed', lambda *a, **k: True)
    monkeypatch.setattr(notif, 'try_acquire_daily_summary_lock', lambda *a, **k: True)
    monkeypatch.setattr(notif, 'release_daily_summary_lock', Mock())

    def summary_by_date(uid, date_str):
        # only the current day is missing: the backfill walk must not generate
        return None if date_str == today else {'id': f'old-{date_str}', 'status': 'generated'}

    monkeypatch.setattr(notif.daily_summaries_db, 'get_daily_summary_by_date', summary_by_date)
    monkeypatch.setattr(
        notif.daily_summaries_db,
        'update_daily_summary',
        lambda uid, summary_id, payload: payload.get('id') or summary_id,
    )
    monkeypatch.setattr(notif.daily_summaries_db, 'create_daily_summary', lambda uid, payload: payload['id'])
    monkeypatch.setattr(notif.daily_summaries_db, 'mark_daily_summary_delivery_completed', Mock())

    conversation = SimpleNamespace(
        discarded=False,
        transcript_segments=[object()],
        structured=SimpleNamespace(overview='Maya will send the vendor write-up.'),
        apps_results=[],
        get_person_ids=lambda: [],
    )
    monkeypatch.setattr(notif.conversations_db, 'get_conversations', lambda *a, **k: [{'id': 'c1'}])
    monkeypatch.setattr(notif, 'deserialize_conversations', lambda values: [conversation for _ in values])
    monkeypatch.setattr(notif, 'bound_daily_summary_conversations', lambda *a, **k: [conversation])
    monkeypatch.setattr(notif, 'memories_learned_payload', lambda *a, **k: [])
    monkeypatch.setattr(
        notif,
        'generate_comprehensive_daily_summary',
        lambda *a, **k: {'id': 's1', 'day_emoji': '📅', 'headline': 'Vendor day', 'overview': 'Pricing sync.'},
    )
    monkeypatch.setattr(notif.notification_db, 'get_all_tokens', lambda *a, **k: ['token-1'])
    monkeypatch.setattr(notif, 'send_notification_result', lambda *a, **k: 1)
    monkeypatch.setattr(notif, 'memory_review_card_block', lambda *a, **k: None)

    webhook_calls = []

    async def fake_webhook(uid, text, payload):
        webhook_calls.append(uid)

    monkeypatch.setattr(notif, 'day_summary_webhook', fake_webhook)
    return SimpleNamespace(pass_calls=pass_calls, webhook_calls=webhook_calls, today=today)


def _user_data():
    # (uid, tokens, tz, at, retry_delivery, retry_attempt, delivery_completed)
    return (UID, None, 'UTC', None, False, False, None)


def test_recap_returns_the_pass_request_after_its_own_work(recap_env):
    """The recap worker never runs the pass inline: it finishes delivery and
    the webhook first, then hands the coordinator a pass request."""
    request = notif._send_summary_notification(_user_data())
    assert recap_env.pass_calls == []  # nothing ran inside the recap window
    assert recap_env.webhook_calls == [UID]  # the recap itself completed fully
    assert request is not None
    uid, date_str, start_utc, end_utc, tz_name = request
    assert uid == UID
    assert date_str == recap_env.today  # the current local day only
    assert tz_name == 'UTC'
    assert start_utc is not None and end_utc is not None
    # and the dispatcher runs exactly that request
    asyncio.run(notif._dispatch_open_loops_passes([request]))
    assert len(recap_env.pass_calls) == 1


def test_no_pass_request_when_the_day_belongs_to_another_worker(recap_env, monkeypatch):
    monkeypatch.setattr(notif, 'try_acquire_daily_summary_lock', lambda *a, **k: False)
    assert notif._send_summary_notification(_user_data()) is None


def test_no_pass_request_when_the_recap_was_budget_declined(recap_env, monkeypatch):
    monkeypatch.setattr(
        notif,
        '_generate_and_store_daily_summary',
        lambda *a, **k: (None, False, notif._DECLINE_USAGE_BUDGET),
    )
    monkeypatch.setattr(notif, '_backfill_recent_daily_summaries', Mock())
    assert notif._send_summary_notification(_user_data()) is None


def test_a_slow_pass_past_its_deadline_is_abandoned_cleanly(recap_env, monkeypatch):
    """A pass that sleeps past its budget is abandoned: the coroutine returns,
    nothing raises, and no recap recipient metric or counter moves."""
    started = []

    def slow_pass(uid, date_str, start_utc, end_utc, tz_name):
        started.append(uid)
        time.sleep(0.3)

    monkeypatch.setattr(notif, '_run_open_loops_daily_pass', slow_pass)
    monkeypatch.setattr(notif, 'OPEN_LOOPS_PASS_BUDGET_SECONDS', 0.05)
    began = time.monotonic()
    asyncio.run(notif._dispatch_open_loops_passes([(UID, recap_env.today, None, None, 'UTC')]))
    assert time.monotonic() - began < 0.25  # did not wait for the sleeping worker
    assert started == [UID]  # the pass did start; its thread is simply abandoned


def test_webhook_delivery_is_never_delayed_by_a_slow_pass(recap_env, monkeypatch):
    """Ordering proof: the webhook completes before a wedged pass even starts,
    because the pass only runs after the recap worker returned."""
    events = []

    async def fake_webhook(uid, text, payload):
        events.append('webhook')

    monkeypatch.setattr(notif, 'day_summary_webhook', fake_webhook)

    def slow_pass(uid, date_str, start_utc, end_utc, tz_name):
        events.append('pass_started')
        time.sleep(0.2)

    monkeypatch.setattr(notif, '_run_open_loops_daily_pass', slow_pass)
    monkeypatch.setattr(notif, 'OPEN_LOOPS_PASS_BUDGET_SECONDS', 0.05)

    async def flow():
        request = await asyncio.get_running_loop().run_in_executor(None, notif._send_summary_notification, _user_data())
        await notif._dispatch_open_loops_passes([request])

    asyncio.run(flow())
    assert events == ['webhook', 'pass_started']


def test_a_failing_pass_never_breaks_the_dispatch(recap_env, monkeypatch):
    def exploding(uid, **kwargs):
        raise RuntimeError('open loops exploded')

    monkeypatch.setattr(open_loops_daily, 'run_daily_pass', exploding)
    request = notif._send_summary_notification(_user_data())
    assert recap_env.webhook_calls == [UID]  # delivery + webhook unaffected
    asyncio.run(notif._dispatch_open_loops_passes([request]))  # must not raise
    assert recap_env.webhook_calls == [UID]


def test_a_pass_module_that_cannot_even_import_never_breaks_the_dispatch(recap_env, monkeypatch):
    """The fail-open catch owns the sibling step's import too: a stubbed or
    broken dependency graph (as import-isolation harnesses produce) must not
    take the dispatch down with it."""
    request = notif._send_summary_notification(_user_data())
    monkeypatch.setitem(sys.modules, 'utils.open_loops.daily', None)
    asyncio.run(notif._dispatch_open_loops_passes([request]))  # must not raise
    assert recap_env.webhook_calls == [UID]


def test_bulk_run_dispatches_passes_without_touching_recap_counters(recap_env):
    """End to end over the coordinator: the pass runs after the batch's
    recaps complete, and a pass that overruns its budget leaves
    ``timed_out``/abandoned-user accounting untouched."""
    stats = notif.DailySummaryJobStats()
    served = asyncio.run(
        notif._send_bulk_summary_notification([_user_data()], deadline=None, stats=stats, target_hour=12)
    )
    assert served is True
    assert stats.attempted == 1 and stats.succeeded == 1
    assert stats.timed_out == 0 and stats.failed == 0
    assert recap_env.webhook_calls == [UID]
    assert len(recap_env.pass_calls) == 1  # dispatched after the recap completed


def test_bulk_run_drops_passes_once_the_job_budget_is_spent(recap_env, monkeypatch, caplog):
    """Passes never push the job past its deadline: they are dropped loudly
    (the next tick re-requests the day), and recap accounting is unaffected."""
    import logging

    clock = {'now': 1000.0}
    monkeypatch.setattr(notif, 'monotonic', lambda: clock['now'])

    def spend_the_budget(uid, display_date, tz_name):
        clock['now'] = 1002.0  # the deadline passes while the recap work runs

    monkeypatch.setattr(notif, '_backfill_recent_daily_summaries', spend_the_budget)
    monkeypatch.setattr(notif, '_run_open_loops_daily_pass', Mock())

    stats = notif.DailySummaryJobStats()
    with caplog.at_level(logging.INFO, logger='utils.other.notifications'):
        served = asyncio.run(
            notif._send_bulk_summary_notification([_user_data()], deadline=1001.0, stats=stats, target_hour=12)
        )
    assert served is True
    assert stats.timed_out == 0 and stats.succeeded == 1  # the recap itself was fine
    assert recap_env.pass_calls == []  # the pass was dropped, not run
    assert any('open_loops_daily_passes_dropped' in record.message for record in caplog.records)


def test_pass_skipped_logs_the_reason(recap_env, monkeypatch, caplog):
    import logging

    monkeypatch.setattr(open_loops_daily, 'run_daily_pass', lambda uid, **kwargs: 'skipped_disabled')
    with caplog.at_level(logging.INFO, logger='utils.other.notifications'):
        notif._run_open_loops_daily_pass(UID, recap_env.today, None, None, 'UTC')
    assert any('skipped_disabled' in record.message for record in caplog.records)
