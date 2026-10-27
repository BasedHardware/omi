import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from config import refactor_modes
from utils.other import daily_recap as recap, notifications as notif

START = datetime(2026, 1, 1, tzinfo=timezone.utc)
END = START + timedelta(days=1, microseconds=-1)


@pytest.fixture
def producer(monkeypatch):
    monkeypatch.setenv(recap.FLAG, 'serve')
    monkeypatch.setattr(notif, 'generated_compute_allowed', lambda *_: True)
    monkeypatch.setattr(notif, 'try_acquire_daily_summary_lock', lambda *_: True)
    release = Mock()
    monkeypatch.setattr(notif, 'release_daily_summary_lock', release)
    store, writes, rows = {}, [], [{'id': 'conversation-1', 'revision': 1}]
    monkeypatch.setattr(notif.daily_summaries_db, 'get_daily_summary_by_date', lambda *_: store.get('day'))

    def save(uid, *args):
        payload = args[-1]
        store['day'] = dict(payload)
        writes.append(dict(payload))
        return payload['id']

    monkeypatch.setattr(notif.daily_summaries_db, 'create_daily_summary', save)
    monkeypatch.setattr(notif.daily_summaries_db, 'update_daily_summary', save)
    monkeypatch.setattr(notif.conversations_db, 'get_conversations', lambda *_a, **_k: list(rows))
    conversation = SimpleNamespace(
        discarded=False, transcript_segments=[object()], structured=SimpleNamespace(overview='Ready'), apps_results=[]
    )
    monkeypatch.setattr(notif, 'deserialize_conversations', lambda values: [conversation for _ in values])
    monkeypatch.setattr(notif, 'bound_daily_summary_conversations', lambda *_: [conversation])
    monkeypatch.setattr(notif, 'memories_learned_payload', lambda *_: [])
    model = Mock(return_value={'id': 'model-chosen-id', 'date': '2026-01-01', 'headline': 'Ready'})
    monkeypatch.setattr(notif, 'generate_comprehensive_daily_summary', model)
    return SimpleNamespace(
        store=store, writes=writes, rows=rows, model=model, release=release, conversation=conversation
    )


def generate():
    return notif._generate_and_store_daily_summary('synthetic-owner', '2026-01-01', START, END)


def test_generated_status_and_late_input_refresh_keep_same_id(producer):
    first, created, decline = generate()
    assert created and decline is None
    assert first['status'] == 'generated' and first['generated_at'].tzinfo is not None
    assert [w['status'] for w in producer.writes] == ['pending', 'generated']
    assert generate()[1] is False and producer.model.call_count == 1
    producer.rows.append({'id': 'conversation-2', 'revision': 1})
    producer.store['day']['notification_delivery_completed'] = True
    refreshed, created, _ = generate()
    assert created and refreshed['id'] == first['id']
    assert refreshed['notification_delivery_completed'] is True
    assert producer.model.call_count == 2
    assert producer.release.call_count == 3


def test_empty_day_has_durable_no_recordings_and_late_capture_retries(producer):
    producer.rows.clear()
    assert generate()[0] is None
    assert producer.store['day']['status'] == 'no_recordings'
    assert producer.store['day']['generated_at'] is None
    producer.model.assert_not_called()
    producer.rows.append({'id': 'late-1'})
    assert generate()[0]['status'] == 'generated'


def test_missing_notes_are_pending_then_retry(producer):
    producer.conversation.structured.overview = ''
    assert generate()[0] is None
    assert producer.store['day']['status'] == 'pending'
    producer.conversation.structured.overview = 'Ready'
    assert generate()[0]['status'] == 'generated'


def test_provider_error_has_failed_row_and_releases_lock(producer):
    producer.model.side_effect = RuntimeError('synthetic failure')
    with pytest.raises(RuntimeError, match='synthetic failure'):
        generate()
    assert producer.store['day']['status'] == 'failed'
    assert producer.store['day']['generated_at'] is None
    assert len({w['id'] for w in producer.writes}) == 1
    producer.release.assert_called_once()


def test_day_not_over_is_pending_without_model(producer):
    future = datetime.now(timezone.utc) + timedelta(hours=2)
    notif._generate_and_store_daily_summary('synthetic-owner', '2099-01-01', future - timedelta(days=1), future)
    assert producer.store['day']['status'] == 'pending'
    producer.model.assert_not_called()


def test_shadow_preserves_legacy_and_does_not_add_model_call(monkeypatch):
    legacy = Mock(return_value=('legacy', False, None))
    assert recap.generate('synthetic-owner', '2026-01-01', START, END, legacy=legacy) == ('legacy', False, None)
    legacy.assert_called_once()


@pytest.mark.parametrize(
    'zone,at,expected',
    [
        ('Asia/Ho_Chi_Minh', '2026-01-02T17:30:00+00:00', '2026-01-01'),
        ('Asia/Ho_Chi_Minh', '2026-01-02T18:00:00+00:00', '2026-01-02'),
        ('America/New_York', '2026-03-09T05:00:00+00:00', '2026-03-08'),
        ('invalid', '2026-01-02T01:00:00+00:00', '2026-01-01'),
    ],
)
def test_completed_day_grace_and_dst(zone, at, expected):
    assert recap.completed_day(zone, datetime.fromisoformat(at)).isoformat() == expected


def test_scheduler_selects_serve_at_one_and_preserves_legacy_preferences(monkeypatch):
    monkeypatch.setenv(recap.FLAG + '_SERVE_UID_SHA256S', refactor_modes.uid_digest('serve-owner'))
    calls = []

    async def selector(zones, hour):
        calls.append(hour)
        return ([('serve-owner', [], 'UTC'), ('legacy-owner', [], 'UTC')] if hour == 22 else []), None, True

    due, error, complete = asyncio.run(recap.select_recipients(['UTC'], 1, selector))
    assert [r[0] for r in due] == ['serve-owner']
    assert len(calls) == 24 and complete and error is None
    evening, _, _ = asyncio.run(recap.select_recipients(['UTC'], 22, selector))
    assert [r[0] for r in evening] == ['legacy-owner']


def test_default_shadow_scheduler_does_no_extra_queries():
    selector = Mock()

    async def select(zones, hour):
        selector(hour)
        return [], None, True

    asyncio.run(recap.select_recipients(['UTC'], 22, select))
    selector.assert_called_once_with(22)


def test_discovery_invalid_cohorts_do_not_expand_reads():
    for value in ('nan', 'inf', '-1', '101', 'broken'):
        assert not refactor_modes.cohort_configured('X_MODE', environ={'X_MODE_SERVE_PERCENT': value})
    assert refactor_modes.cohort_configured('X_MODE', environ={'X_MODE_SERVE_PERCENT': '1'})


def test_state_id_is_stable_even_when_best_effort_lock_is_lost(producer):
    producer.rows.clear()
    generate()
    first = producer.store['day']['id']
    producer.store.clear()
    generate()
    assert producer.store['day']['id'] == first


def test_failed_existing_lookup_does_not_create_duplicate_row(producer, monkeypatch):
    monkeypatch.setattr(
        notif.daily_summaries_db, 'get_daily_summary_by_date', Mock(side_effect=RuntimeError('lookup failed'))
    )
    with pytest.raises(RuntimeError, match='lookup failed'):
        generate()
    assert producer.writes == []


def test_pending_stub_during_locked_delivery_retry_never_pushes(producer, monkeypatch):
    monkeypatch.setattr(notif, 'try_acquire_daily_summary_lock', lambda *_: False)
    producer.store['day'] = {'id': 'recap-2026-01-01', 'status': 'pending', 'generated_at': None}
    sent = Mock()
    monkeypatch.setattr(notif, '_deliver_current_day_summary', sent)
    with pytest.raises(RuntimeError, match='still locked'):
        notif._send_summary_notification(('synthetic-owner', [], 'UTC', END, True, True))
    sent.assert_not_called()


def test_content_kind_change_invalidates_existing_recap(producer, monkeypatch):
    from utils.conversations import media_consumers

    monkeypatch.setattr(media_consumers, '_policy', lambda: lambda uid, row, **kw: row.get('content_kind') == 'media')
    assert generate()[0]['status'] == 'generated'
    monkeypatch.setenv('MEDIA_NOISE_MODE', 'serve')
    producer.rows[0]['content_kind'] = 'media'
    assert generate()[0] is None
    assert producer.store['day']['status'] == 'not_generated'
    assert producer.model.call_count == 1


def test_budget_denied_day_records_not_generated_without_spending(producer, monkeypatch):
    monkeypatch.setattr(notif, 'generated_compute_allowed', lambda *_: False)
    result, created, declined = generate()
    assert result is None and not created and declined == 'usage_budget_exhausted'
    assert producer.store['day']['status'] == 'not_generated'
    assert producer.store['day']['generated_at'] is None
    producer.model.assert_not_called()


def test_unchanged_empty_day_remains_dormant(producer):
    producer.rows.clear()
    generate()
    assert generate()[2] == notif.DAILY_SUMMARY_DECLINE_NO_CONVERSATIONS


def test_spend_denial_does_not_erase_an_already_generated_day(producer, monkeypatch):
    original = generate()[0]
    monkeypatch.setattr(notif, 'generated_compute_allowed', lambda *_: False)
    assert generate()[0] == original
    assert producer.store['day']['status'] == 'generated'
    assert producer.store['day']['generated_at'] == original['generated_at']


def test_media_dependency_delegates_to_v2_and_preserves_rollback(monkeypatch):
    from utils.conversations import media_consumers

    calls = []

    def policy(uid, row, **kwargs):
        calls.append(kwargs['consumer'])
        return row.get('content_kind') == 'media'

    monkeypatch.setattr(media_consumers, '_policy', lambda: policy)
    rows = [{'content_kind': 'media'}, {'content_kind': 'conversation'}]
    assert media_consumers.eligible_conversations('synthetic-owner', rows) == rows
    assert calls == []
    monkeypatch.setenv('MEDIA_NOISE_MODE', 'serve')
    assert media_consumers.eligible_conversations('synthetic-owner', rows) == rows[1:]
    assert calls == ['daily_summary', 'daily_summary']


def test_mode_rollback_resumes_pending_stub_in_place(producer, monkeypatch):
    producer.store['day'] = {'id': 'recap-2026-01-01', 'date': '2026-01-01', 'status': 'pending', 'generated_at': None}
    monkeypatch.setenv(recap.FLAG, 'off')
    result, created, _ = generate()
    assert created and result['id'] == 'recap-2026-01-01'
    assert result['status'] == 'generated' and result['generated_at'] is not None
    producer.model.assert_called_once()


def test_mode_rollback_cannot_deliver_a_locked_pending_stub(producer, monkeypatch):
    monkeypatch.setenv(recap.FLAG, 'off')
    test_pending_stub_during_locked_delivery_retry_never_pushes(producer, monkeypatch)


@pytest.mark.parametrize('hours_to_day_end', [2, -0.5])
def test_on_demand_partial_day_bypasses_scheduled_grace(producer, monkeypatch, hours_to_day_end):
    monkeypatch.setattr(notif, 'require_generated_compute', lambda *_: None)
    end = datetime.now(timezone.utc) + timedelta(hours=hours_to_day_end)
    start = end - timedelta(days=1)
    # The same day is still deferred for a scheduler/backfill attempt.
    assert notif._generate_and_store_daily_summary('synthetic-owner', '2026-01-01', start, end)[0] is None
    assert producer.store['day']['status'] == 'pending'
    producer.model.assert_not_called()
    record, declined = notif.generate_daily_summary_on_demand('synthetic-owner', '2026-01-01', start, end)
    assert declined is None and record['status'] == 'generated'
    producer.model.assert_called_once()
