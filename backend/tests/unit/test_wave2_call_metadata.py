from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from utils.conversations import call_metadata as calls
from utils.episodes import boundary_store

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def signal(kind, **kwargs):
    return SimpleNamespace(kind=kind, confidence=1, external_id='event-1', started_at=NOW, **kwargs)


@pytest.mark.parametrize('kind', ['screen_meeting', 'desktop_meeting', 'media_playback'])
def test_unconfirmed_window_and_media_never_call(kind):
    assert calls.call_fields([signal(kind)])['is_call'] is False


def test_phone_and_calendar_from_positive_evidence_only():
    assert calls.call_fields([signal('phone_call')])['call_platform'] == 'phone'
    calendar = signal('calendar_event')
    context = {'calendar_event_id': 'event-1', 'meeting_link': 'https://meet.google.com/abc-defg-hij'}
    fields = calls.call_fields([calendar], context)
    assert fields == {
        'is_call': True,
        'call_platform': 'google_meet',
        'calendar_event_id': 'event-1',
        'geolocation_scope': 'owner',
        'other_participants_location': 'remote',
    }
    context['calendar_event_id'] = 'different-event'
    assert calls.call_fields([calendar], context)['is_call'] is False


@pytest.mark.parametrize(
    'url',
    [
        'https://calendar.google.com/event?id=1',
        'https://zoom.us.evil.example/j/123',
        'https://zoom.us',
        'file:///tmp/call',
        'not a url',
    ],
)
def test_calendar_pages_are_not_meeting_links(url):
    assert calls.meeting_platform(url) is None


def test_control_detection_is_required_even_for_messaging_platform():
    assert calls.call_fields([signal('screen_meeting', call_controls_detected=True, call_platform='telegram')])[
        'is_call'
    ]
    assert not calls.call_fields([signal('screen_meeting', call_controls_detected=False, call_platform='telegram')])[
        'is_call'
    ]


def test_finalizer_projection_shadow_serve_and_off(monkeypatch):
    monkeypatch.setattr(
        boundary_store, 'windows', lambda *_: {'edge': {'started_at': NOW, 'ended_at': NOW + timedelta(hours=1)}}
    )
    monkeypatch.setattr(boundary_store, 'load', lambda *_: [signal('phone_call')])
    conversation = SimpleNamespace(
        started_at=NOW, finished_at=NOW + timedelta(minutes=30), external_data={}, is_call=None, geolocation=object()
    )
    original_location = conversation.geolocation
    assert calls.apply_call_metadata('synthetic-owner', conversation).is_call is None
    monkeypatch.setenv(calls.FLAG, 'serve')
    assert calls.apply_call_metadata('synthetic-owner', conversation).is_call is True
    assert conversation.geolocation is original_location
    assert conversation.other_participants_location == 'remote'
    monkeypatch.setenv(calls.FLAG, 'off')
    monkeypatch.setattr(boundary_store, 'windows', Mock(side_effect=AssertionError('off must not read')))
    calls.apply_call_metadata('synthetic-owner', conversation)


def test_non_overlapping_and_stale_ongoing_signals_abstain(monkeypatch):
    monkeypatch.setenv(calls.FLAG, 'serve')
    monkeypatch.setattr(boundary_store, 'windows', lambda *_: {'edge': {'started_at': NOW, 'ended_at': None}})
    loaded = Mock(return_value=[])
    monkeypatch.setattr(boundary_store, 'load', loaded)
    c = SimpleNamespace(
        started_at=NOW + timedelta(days=1), finished_at=NOW + timedelta(days=1, hours=1), external_data={}
    )
    calls.apply_call_metadata('synthetic-owner', c)
    assert loaded.call_args.args[1] == []
    assert c.is_call is False
