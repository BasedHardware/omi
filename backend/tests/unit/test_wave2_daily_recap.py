"""Legacy daily-recap generation: deletion guard, status stubs and locked retries."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from config import refactor_modes
from utils.other import notifications as notif

START = datetime(2026, 1, 1, tzinfo=timezone.utc)
END = START + timedelta(days=1, microseconds=-1)


@pytest.fixture
def producer(monkeypatch):
    monkeypatch.setattr(notif, 'account_deletion_blocks_user_work', lambda _uid: False)
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
    monkeypatch.setattr(notif, 'exclude_from_derived', lambda *_a, **_k: False)
    monkeypatch.setattr(notif.daily_summaries_db, 'set_daily_summary_generation_status', Mock())
    model = Mock(return_value={'id': 'model-chosen-id', 'date': '2026-01-01', 'headline': 'Ready'})
    monkeypatch.setattr(notif, 'generate_comprehensive_daily_summary', model)
    return SimpleNamespace(
        store=store, writes=writes, rows=rows, model=model, release=release, conversation=conversation
    )


def generate():
    return notif._generate_and_store_daily_summary('synthetic-owner', '2026-01-01', START, END)


def test_pending_deletion_owner_is_skipped_before_daily_recap_reads(producer, monkeypatch):
    monkeypatch.setattr(notif, 'account_deletion_blocks_user_work', lambda _uid: True)

    record, created, declined = generate()

    assert record is None
    assert created is False
    assert declined == 'account_pending_deletion'
    producer.model.assert_not_called()
    assert producer.writes == []


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


def test_media_dependency_delegates_to_v2_and_preserves_rollback(monkeypatch):
    from utils.conversations import media_consumers

    monkeypatch.setenv('MEDIA_NOISE_MODE', 'shadow')
    calls = []

    def policy(uid, row, **kwargs):
        calls.append(kwargs['consumer'])
        return row.get('content_kind') == 'media' and refactor_modes.serving_for('MEDIA_NOISE_MODE', uid)

    monkeypatch.setattr(media_consumers, '_policy', lambda: policy)
    rows = [{'content_kind': 'media'}, {'content_kind': 'conversation'}]
    assert media_consumers.eligible_conversations('synthetic-owner', rows) == rows
    assert calls == ['daily_summary', 'daily_summary']
    monkeypatch.setenv('MEDIA_NOISE_MODE', 'off')  # Explicit rollback preserves legacy output without shadow calls.
    assert media_consumers.eligible_conversations('synthetic-owner', rows) == rows
    assert calls == ['daily_summary', 'daily_summary']
    monkeypatch.setenv('MEDIA_NOISE_MODE', 'serve')
    assert media_consumers.eligible_conversations('synthetic-owner', rows) == rows[1:]
    assert calls == ['daily_summary'] * 4


def test_earlier_pending_stub_is_completed_in_place(producer):
    producer.store['day'] = {'id': 'recap-2026-01-01', 'date': '2026-01-01', 'status': 'pending', 'generated_at': None}
    result, created, _ = generate()
    assert created and result['id'] == 'recap-2026-01-01'
    assert result['status'] == 'generated' and result['generated_at'] is not None
    producer.model.assert_called_once()
