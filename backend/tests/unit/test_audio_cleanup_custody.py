from datetime import datetime, timezone

import pytest

from utils.audio_cleanup_custody import cleanup_hold_reason


@pytest.fixture(autouse=True)
def clean_config(monkeypatch):
    monkeypatch.delenv('AUDIO_CLEANUP_HOLD_ENABLED', raising=False)
    monkeypatch.delenv('AUDIO_CLEANUP_HOLD_WINDOWS', raising=False)


@pytest.mark.parametrize(
    'start,duration,held',
    [
        ('2026-10-22T13:36:30Z', 0, True),
        ('2026-10-24T07:16:00Z', 0, True),
        ('2026-10-22T13:35:30Z', 60, True),
        ('2026-10-22T13:35:30Z', 59, False),
        ('2026-10-24T07:16:00.001Z', 60, False),
        ('2026-10-21T00:00:00Z', None, True),
        ('2026-10-25T00:00:00Z', None, False),
        (None, 60, True),
        (True, 60, True),
        ('2026-10-25T00:00:00', 0, True),
        ('2026-10-25T00:00:00Z', -1, True),
        (1e308, 60, True),
        (-1e308, 60, True),
        (1792000000000, 60, True),
        ('0001-01-01T00:00:00+01:00', 60, True),
        ('9999-12-31T23:59:59-01:00', 60, True),
    ],
)
def test_capture_window_overlap_and_unknown_provenance(start, duration, held):
    assert bool(cleanup_hold_reason(start, duration)) == held


def test_utc_numeric_and_datetime_values_are_equivalent():
    capture = datetime(2026, 10, 23, tzinfo=timezone.utc)
    assert cleanup_hold_reason(capture, 1) == cleanup_hold_reason(capture.timestamp(), 1) == 'capture_window'


@pytest.mark.parametrize('config', ['', 'bad', '2026-10-25T00:00:00Z..2026-10-21T00:00:00Z'])
def test_bad_config_fails_closed(monkeypatch, config):
    monkeypatch.setenv('AUDIO_CLEANUP_HOLD_WINDOWS', config)
    assert cleanup_hold_reason('2026-10-25T00:00:00Z', 1) == 'invalid_hold_config'


def test_multiple_configured_windows_and_explicit_kill_switch(monkeypatch):
    monkeypatch.setenv(
        'AUDIO_CLEANUP_HOLD_WINDOWS',
        '2026-10-20T00:00:00Z..2026-10-21T00:00:00Z,2026-10-24T00:00:00Z..2026-10-25T00:00:00Z',
    )
    assert cleanup_hold_reason('2026-10-24T12:00:00Z', 1)
    assert cleanup_hold_reason('2026-10-22T00:00:00Z', 1) is None
    monkeypatch.setenv('AUDIO_CLEANUP_HOLD_ENABLED', 'false')
    assert cleanup_hold_reason(None) is None
