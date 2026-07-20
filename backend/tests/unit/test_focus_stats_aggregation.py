"""Aggregation behaviour of database.focus_sessions.get_focus_stats.

``get_focus_stats`` reads sessions through ``get_focus_sessions`` and folds them into
focused/distracted totals plus a top-distractions ranking. Patching that reader is the
seam: it exercises the real aggregation without Firestore.

A distracted session whose ``duration_seconds`` is unknown is deliberately charged a
one-minute default, because a distraction that was recorded but never measured still
represents lost focus. That default must apply only to a genuinely *unknown* duration.
"""

import sys
from types import ModuleType
from unittest.mock import MagicMock

import pytest


class _AutoMockModule(ModuleType):
    """Module stub that returns a MagicMock for any missing attribute."""

    def __getattr__(self, name):
        if name.startswith('__') and name.endswith('__'):
            raise AttributeError(name)
        mock = MagicMock()
        setattr(self, name, mock)
        return mock


def _install_google_stubs() -> None:
    """Stand in for google.cloud only when it is genuinely unavailable."""
    try:  # pragma: no cover - depends on the environment
        from google.cloud import firestore  # noqa: F401
        from google.cloud.firestore_v1.base_query import FieldFilter  # noqa: F401

        return
    except ImportError:
        pass

    google_pkg = sys.modules.setdefault('google', _AutoMockModule('google'))
    google_pkg.__path__ = []  # type: ignore[attr-defined]
    cloud_pkg = _AutoMockModule('google.cloud')
    cloud_pkg.__path__ = []  # type: ignore[attr-defined]
    base_query = _AutoMockModule('google.cloud.firestore_v1.base_query')
    base_query.FieldFilter = MagicMock()  # type: ignore[attr-defined]
    firestore_v1 = _AutoMockModule('google.cloud.firestore_v1')
    firestore_v1.__path__ = []  # type: ignore[attr-defined]
    sys.modules['google.cloud'] = cloud_pkg
    sys.modules['google.cloud.firestore'] = _AutoMockModule('google.cloud.firestore')
    sys.modules['google.cloud.firestore_v1'] = firestore_v1
    sys.modules['google.cloud.firestore_v1.base_query'] = base_query


_install_google_stubs()
sys.modules.setdefault('database._client', _AutoMockModule('database._client'))

import database.focus_sessions as focus_db  # noqa: E402


@pytest.fixture
def stats(monkeypatch):
    """Return a caller that folds the supplied sessions through the real aggregation."""

    def _run(sessions):
        monkeypatch.setattr(focus_db, 'get_focus_sessions', lambda uid, date=None, limit=0, offset=0: sessions)
        return focus_db.get_focus_stats('uid', date='2026-07-21')

    return _run


def _session(status, seconds, app='Slack'):
    session = {'status': status, 'app_or_site': app}
    if seconds is not _MISSING:
        session['duration_seconds'] = seconds
    return session


_MISSING = object()


class TestFocusedSessions:
    def test_focused_durations_are_summed(self, stats):
        result = stats([_session('focused', 120), _session('focused', 60)])
        assert result['focused_minutes'] == 3
        assert result['focused_count'] == 2

    def test_focused_session_without_duration_contributes_nothing(self, stats):
        result = stats([_session('focused', _MISSING)])
        assert result['focused_minutes'] == 0
        assert result['focused_count'] == 1


class TestDistractedSessions:
    def test_distracted_durations_are_summed(self, stats):
        result = stats([_session('distracted', 90), _session('distracted', 30)])
        assert result['distracted_minutes'] == 2
        assert result['distracted_count'] == 2

    def test_unknown_distracted_duration_is_charged_one_minute(self, stats):
        # An unmeasured distraction still represents lost focus, so it is charged a
        # default minute rather than being ignored.
        result = stats([_session('distracted', _MISSING)])
        assert result['distracted_minutes'] == 1
        assert result['top_distractions'][0]['total_seconds'] == 60


class TestTopDistractions:
    def test_ranked_by_total_seconds_and_counted_per_app(self, stats):
        result = stats(
            [
                _session('distracted', 30, app='Slack'),
                _session('distracted', 30, app='Slack'),
                _session('distracted', 300, app='X'),
            ]
        )
        assert [entry['app_or_site'] for entry in result['top_distractions']] == ['X', 'Slack']
        slack = next(e for e in result['top_distractions'] if e['app_or_site'] == 'Slack')
        assert slack == {'app_or_site': 'Slack', 'total_seconds': 60, 'count': 2}

    def test_session_count_spans_both_statuses(self, stats):
        result = stats([_session('focused', 60), _session('distracted', 60)])
        assert result['session_count'] == 2
        assert result['date'] == '2026-07-21'
