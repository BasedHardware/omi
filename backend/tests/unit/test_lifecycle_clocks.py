"""Separate actual speech from activity without changing shadow behavior."""

from datetime import datetime, timedelta, timezone

import pytest

from utils.conversations import lifecycle_clocks as clocks
from tests.unit.test_manual_speaker_assignments import world
from database import conversations as db

NOW = datetime(2026, 10, 22, tzinfo=timezone.utc)


def test_speech_does_not_advance_on_empty_heartbeats(monkeypatch):
    row = {'started_at': NOW, 'last_speech_at': NOW + timedelta(seconds=5)}
    patch = clocks.activity_updates('test-account', row, NOW + timedelta(seconds=90))
    assert patch == {'last_activity_at': NOW + timedelta(seconds=90)}
    spoken = clocks.activity_updates(
        'test-account', row, NOW + timedelta(seconds=90), segments=[{'text': ' ', 'end': 80}]
    )
    assert 'last_speech_at' not in spoken
    monkeypatch.setenv('LIFECYCLE_V2_MODE', 'off')
    assert clocks.activity_updates('test-account', row, NOW) == {}


def test_speech_readers_migrate_only_for_the_serve_cohort(monkeypatch):
    row = {'finished_at': NOW + timedelta(seconds=90), 'last_speech_at': NOW}
    monkeypatch.setenv('LIFECYCLE_V2_MODE', 'shadow')
    assert clocks.speech_clock('test-account', row) == row['finished_at']
    monkeypatch.setenv('LIFECYCLE_V2_MODE', 'serve')
    assert clocks.speech_clock('test-account', row) == NOW
    assert clocks.speech_clock('test-account', {'finished_at': NOW.isoformat()}) == NOW


def test_segment_transaction_dual_writes_all_clocks_monotonically(world):
    store, path, segments = world
    store.rows[path].update(
        started_at=NOW,
        finished_at=NOW,
        last_activity_at=NOW + timedelta(seconds=20),
        last_speech_at=NOW + timedelta(seconds=10),
    )
    db.update_conversation_segments('u', 'c', segments, live_segments=segments, finished_at=NOW + timedelta(seconds=15))
    row = store.rows[path]
    assert row['last_activity_at'] == NOW + timedelta(seconds=20)
    assert row['last_speech_at'] == NOW + timedelta(seconds=10)
    assert row['finished_at'] == NOW + timedelta(seconds=15)


def test_overlap_uses_speech_end_for_serve_and_heartbeat_for_shadow(monkeypatch):
    from utils.conversations.duplicate_capture import capture_record

    row = {
        'id': 'conversation-test',
        'source': 'omi',
        'status': 'completed',
        'started_at': NOW,
        'last_speech_at': NOW + timedelta(seconds=5),
        'finished_at': NOW + timedelta(seconds=90),
    }
    monkeypatch.setenv('LIFECYCLE_V2_MODE', 'shadow')
    assert capture_record(row, 'test-account').duration_seconds == 90
    monkeypatch.setenv('LIFECYCLE_V2_MODE', 'serve')
    assert capture_record(row, 'test-account').duration_seconds == 5
    assert clocks.overlap_fields('test-account', row)['finished_at'] == NOW + timedelta(seconds=5)
