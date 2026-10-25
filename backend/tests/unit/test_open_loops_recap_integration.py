"""The open-loops daily pass as a sibling step of the daily recap job.

Pins the wiring contract: the pass runs after the recap's own outcome for the
user's local day, exactly once per day marker permitting, never for a day
another worker owns or a budget already declined — and a failing pass never
breaks the recap (delivery, backfill and webhook still complete).
"""

import asyncio
import sys
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


def test_pass_runs_once_after_a_successful_recap(recap_env):
    notif._send_summary_notification(_user_data())
    assert len(recap_env.pass_calls) == 1
    uid, kwargs = recap_env.pass_calls[0]
    assert uid == UID
    assert kwargs['date_str'] == recap_env.today  # the current local day only
    assert kwargs['tz'] == 'UTC'
    assert kwargs['start_utc'] is not None and kwargs['end_utc'] is not None
    assert recap_env.webhook_calls == [UID]  # the recap itself completed fully


def test_a_failing_pass_never_breaks_the_recap(recap_env, monkeypatch):
    def exploding(uid, **kwargs):
        raise RuntimeError('open loops exploded')

    monkeypatch.setattr(open_loops_daily, 'run_daily_pass', exploding)
    notif._send_summary_notification(_user_data())  # must not raise
    assert recap_env.webhook_calls == [UID]  # delivery + webhook unaffected


def test_a_pass_module_that_cannot_even_import_never_breaks_the_recap(recap_env, monkeypatch):
    """The fail-open catch owns the sibling step's import too: a stubbed or
    broken dependency graph (as import-isolation harnesses produce) must not
    take the recap down with it."""
    monkeypatch.setitem(sys.modules, 'utils.open_loops.daily', None)
    notif._send_summary_notification(_user_data())  # must not raise
    assert recap_env.webhook_calls == [UID]


def test_pass_skipped_when_the_day_belongs_to_another_worker(recap_env, monkeypatch):
    monkeypatch.setattr(notif, 'try_acquire_daily_summary_lock', lambda *a, **k: False)
    notif._send_summary_notification(_user_data())
    assert recap_env.pass_calls == []


def test_pass_skipped_when_the_recap_was_budget_declined(recap_env, monkeypatch):
    monkeypatch.setattr(
        notif,
        '_generate_and_store_daily_summary',
        lambda *a, **k: (None, False, notif._DECLINE_USAGE_BUDGET),
    )
    monkeypatch.setattr(notif, '_backfill_recent_daily_summaries', Mock())
    notif._send_summary_notification(_user_data())
    assert recap_env.pass_calls == []


def test_pass_skipped_for_the_kill_switch_logs_the_reason(recap_env, monkeypatch, caplog):
    import logging

    monkeypatch.setattr(open_loops_daily, 'run_daily_pass', lambda uid, **kwargs: 'skipped_disabled')
    with caplog.at_level(logging.INFO, logger='utils.other.notifications'):
        notif._run_open_loops_daily_pass(UID, recap_env.today, None, None, 'UTC')
    assert any('skipped_disabled' in record.message for record in caplog.records)
