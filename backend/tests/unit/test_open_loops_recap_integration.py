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
import threading
import time
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

import utils.open_loops.daily as open_loops_daily
from utils.executors import ExecutorSaturatedError
from utils.other import notifications as notif

UID = 'u1'

# The recap's reference instant, pinned. _display_date_for_now applies a noon
# split: before 12:00 in the user's zone the worker summarizes *yesterday*, so a
# real-clock `today` in the fixture disagrees with the worker's day for half of
# every UTC day — the stubbed by-date read then returns a pre-generated summary,
# generation is skipped as a duplicate and the webhook never fires. 18:00 UTC
# keeps the worker's display date on this pin's own calendar day.
_AT = datetime(2026, 10, 25, 18, 0, tzinfo=timezone.utc)


async def _dispatch(pass_requests):
    notif._start_open_loops_passes(pass_requests)
    await notif._drain_open_loops_passes()


async def _bulk_then_drain(users, **kwargs):
    served = await notif._send_bulk_summary_notification(users, **kwargs)
    await notif._drain_open_loops_passes()
    return served


@pytest.fixture
def recap_env(monkeypatch):
    today = _AT.strftime('%Y-%m-%d')

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
    return (UID, None, 'UTC', _AT, False, False, None)


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
    asyncio.run(_dispatch([request]))
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
    release = threading.Event()

    def wedged_pass(uid, date_str, start_utc, end_utc, tz_name):
        started.append(uid)
        release.wait(10)

    monkeypatch.setattr(notif, '_run_open_loops_daily_pass', wedged_pass)
    monkeypatch.setattr(notif, 'OPEN_LOOPS_PASS_BUDGET_SECONDS', 0.5)
    try:
        asyncio.run(_dispatch([(UID, recap_env.today, None, None, 'UTC')]))
        assert not release.is_set()  # returned while the worker was still wedged
        assert started == [UID]  # the pass did start; its thread is simply abandoned
    finally:
        release.set()


def test_webhook_delivery_is_never_delayed_by_a_slow_pass(recap_env, monkeypatch):
    """Ordering proof: the webhook completes before a wedged pass even starts,
    because the pass only runs after the recap worker returned."""
    events = []

    async def fake_webhook(uid, text, payload):
        events.append('webhook')

    monkeypatch.setattr(notif, 'day_summary_webhook', fake_webhook)

    def slow_pass(uid, date_str, start_utc, end_utc, tz_name):
        events.append('pass_started')
        time.sleep(0.1)

    monkeypatch.setattr(notif, '_run_open_loops_daily_pass', slow_pass)

    async def flow():
        request = await asyncio.get_running_loop().run_in_executor(None, notif._send_summary_notification, _user_data())
        await _dispatch([request])

    asyncio.run(flow())
    assert events == ['webhook', 'pass_started']


def test_a_failing_pass_never_breaks_the_dispatch(recap_env, monkeypatch):
    def exploding(uid, **kwargs):
        raise RuntimeError('open loops exploded')

    monkeypatch.setattr(open_loops_daily, 'run_daily_pass', exploding)
    request = notif._send_summary_notification(_user_data())
    assert recap_env.webhook_calls == [UID]  # delivery + webhook unaffected
    asyncio.run(_dispatch([request]))  # must not raise
    assert recap_env.webhook_calls == [UID]


def test_a_pass_module_that_cannot_even_import_never_breaks_the_dispatch(recap_env, monkeypatch):
    """The fail-open catch owns the sibling step's import too: a stubbed or
    broken dependency graph (as import-isolation harnesses produce) must not
    take the dispatch down with it."""
    request = notif._send_summary_notification(_user_data())
    monkeypatch.setitem(sys.modules, 'utils.open_loops.daily', None)
    asyncio.run(_dispatch([request]))  # must not raise
    assert recap_env.webhook_calls == [UID]


def test_bulk_run_dispatches_passes_without_touching_recap_counters(recap_env):
    """End to end over the coordinator: the pass runs after the batch's
    recaps complete, and a pass that overruns its budget leaves
    ``timed_out``/abandoned-user accounting untouched."""
    stats = notif.DailySummaryJobStats()
    served = asyncio.run(_bulk_then_drain([_user_data()], deadline=None, stats=stats, target_hour=12))
    assert served is True
    assert stats.attempted == 1 and stats.succeeded == 1
    assert stats.timed_out == 0 and stats.failed == 0
    assert recap_env.webhook_calls == [UID]
    assert len(recap_env.pass_calls) == 1  # dispatched after the recap completed


def test_bulk_run_drops_passes_once_the_job_budget_is_spent(recap_env, monkeypatch, caplog):
    """Passes never push the job past its deadline: they are dropped loudly
    (not retried), and recap accounting is unaffected."""
    import logging

    clock = {'now': 1000.0}
    monkeypatch.setattr(notif, 'monotonic', lambda: clock['now'])

    def spend_the_budget(uid, display_date, tz_name):
        clock['now'] = 1002.0  # the deadline passes while the recap work runs

    monkeypatch.setattr(notif, '_backfill_recent_daily_summaries', spend_the_budget)
    monkeypatch.setattr(notif, '_run_open_loops_daily_pass', Mock())

    stats = notif.DailySummaryJobStats()
    with caplog.at_level(logging.INFO, logger='utils.other.notifications'):
        served = asyncio.run(_bulk_then_drain([_user_data()], deadline=1001.0, stats=stats, target_hour=12))
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


def test_a_slow_pass_never_delays_the_next_batch(recap_env, monkeypatch):
    """Passes are queued, not awaited, inside the batch loop: batch two's
    recaps begin while batch one's pass is still running, and the job
    drains the passes once at the end."""
    events = []

    def slow_pass(uid, date_str, start_utc, end_utc, tz_name):
        events.append(f'pass_started:{uid}')
        time.sleep(0.3)
        events.append(f'pass_done:{uid}')

    real_send = notif._send_summary_notification

    def tracked_send(user_data):
        events.append(f'recap:{user_data[0]}')
        return real_send(user_data)

    monkeypatch.setattr(notif, '_run_open_loops_daily_pass', slow_pass)
    monkeypatch.setattr(notif, '_send_summary_notification', tracked_send)
    monkeypatch.setattr(notif, '_BATCH_SIZE', 1)
    users = [('u1',) + _user_data()[1:], ('u2',) + _user_data()[1:]]
    stats = notif.DailySummaryJobStats()
    served = asyncio.run(_bulk_then_drain(users, deadline=None, stats=stats, target_hour=12))
    assert served is True and stats.succeeded == 2
    assert events.index('recap:u2') < events.index('pass_done:u1')  # batch two did not wait
    assert 'pass_done:u1' in events and 'pass_done:u2' in events  # drained once at the end


def test_a_saturated_pass_executor_is_counted_and_never_raises(recap_env, monkeypatch):
    fallbacks = []

    def saturated(*args, **kwargs):
        raise ExecutorSaturatedError('full')

    monkeypatch.setattr(notif, 'run_blocking', saturated)
    monkeypatch.setattr(notif, '_record_daily_summary_fallback', lambda **kw: fallbacks.append(kw))
    asyncio.run(_dispatch([(UID, recap_env.today, None, None, 'UTC')]))
    assert fallbacks == [
        {'from_mode': 'open_loops_daily_pass', 'to_mode': 'skipped', 'reason': 'capacity_full', 'outcome': 'degraded'}
    ]


def test_a_large_group_queues_for_slots_instead_of_saturating(recap_env, monkeypatch):
    """More passes than the executor's workers + queue all run: they wait for a
    slot, and each pass's budget starts only once it holds one."""
    peak = {'now': 0, 'max': 0}
    lock = threading.Lock()

    def pass_fn(uid, date_str, start_utc, end_utc, tz_name):
        with lock:
            peak['now'] += 1
            peak['max'] = max(peak['max'], peak['now'])
        time.sleep(0.01)
        with lock:
            peak['now'] -= 1

    monkeypatch.setattr(notif, '_run_open_loops_daily_pass', pass_fn)
    monkeypatch.setattr(notif, 'OPEN_LOOPS_PASS_BUDGET_SECONDS', 0.5)
    fallbacks = []
    monkeypatch.setattr(notif, '_record_daily_summary_fallback', lambda **kw: fallbacks.append(kw))
    requests = [(f'u{i}', recap_env.today, None, None, 'UTC') for i in range(100)]
    asyncio.run(_dispatch(requests))
    assert fallbacks == []  # nothing saturated, timed out or was dropped
    assert peak['max'] <= notif.OPEN_LOOPS_PASS_CONCURRENCY


def test_the_job_drain_cancels_and_counts_what_misses_its_budget(recap_env, monkeypatch):
    release = threading.Event()

    def wedged_pass(uid, date_str, start_utc, end_utc, tz_name):
        release.wait(10)

    monkeypatch.setattr(notif, '_run_open_loops_daily_pass', wedged_pass)
    fallbacks = []
    monkeypatch.setattr(notif, '_record_daily_summary_fallback', lambda **kw: fallbacks.append(kw))

    async def flow():
        notif._start_open_loops_passes([(f'u{i}', recap_env.today, None, None, 'UTC') for i in range(8)])
        await notif._drain_open_loops_passes(0.5)

    try:
        asyncio.run(flow())
        assert not release.is_set()  # the drain gave up on the wedged passes
    finally:
        release.set()
    assert fallbacks == [
        {'from_mode': 'open_loops_daily_pass', 'to_mode': 'skipped', 'reason': 'timeout', 'outcome': 'degraded'}
    ]


def test_send_daily_summary_notification_drains_once_after_all_cohorts(monkeypatch):
    order = []

    async def cohorts():
        order.append('cohorts')
        return notif.DailySummaryCronOutcome(ok=True, error_text=None, complete=True)

    async def drain(budget_seconds=None):
        order.append('drain')

    monkeypatch.setattr(notif, '_send_daily_summary_cohorts', cohorts)
    monkeypatch.setattr(notif, '_drain_open_loops_passes', drain)
    assert asyncio.run(notif.send_daily_summary_notification()).ok
    assert order == ['cohorts', 'drain']
