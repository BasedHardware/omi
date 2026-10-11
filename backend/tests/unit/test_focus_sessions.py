"""Unit tests for focus_sessions database normalization and stats aggregation."""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import database.focus_sessions as focus_sessions_db
from models.focus_session import FocusSession, FocusStats


class _FakeDoc:
    def __init__(self, doc_id: str, payload: dict):
        self.id = doc_id
        self._payload = payload

    def to_dict(self):
        return self._payload


def _mock_user_col_with_docs(docs):
    col = MagicMock()
    query = MagicMock()
    col.order_by.return_value = query
    query.where.return_value = query
    query.offset.return_value = query
    query.limit.return_value = query
    query.stream.return_value = docs
    return col


def test_get_focus_stats_clamps_negative_and_boolean_durations_without_validation_error():
    docs = [
        _FakeDoc(
            'sess-zero',
            {
                'status': 'distracted',
                'app_or_site': 'YouTube',
                'description': 'Explicit zero duration',
                'created_at': datetime(2026, 9, 24, 9, 55, tzinfo=timezone.utc),
                'duration_seconds': 0,
            },
        ),
        _FakeDoc(
            'sess-neg',
            {
                'status': 'distracted',
                'app_or_site': 'YouTube',
                'description': 'Negative legacy duration',
                'created_at': datetime(2026, 9, 24, 10, 0, tzinfo=timezone.utc),
                'duration_seconds': -120,
            },
        ),
        _FakeDoc(
            'sess-none-duration',
            {
                'status': 'distracted',
                'app_or_site': 'Reddit',
                'description': 'Missing duration defaults to 60s',
                'created_at': datetime(2026, 9, 24, 10, 2, tzinfo=timezone.utc),
                'duration_seconds': None,
            },
        ),
        _FakeDoc(
            'sess-bool',
            {
                'status': 'focused',
                'app_or_site': 'VS Code',
                'description': 'Boolean duration',
                'created_at': datetime(2026, 9, 24, 10, 5, tzinfo=timezone.utc),
                'duration_seconds': True,
            },
        ),
    ]
    with patch.object(focus_sessions_db, '_user_col', return_value=_mock_user_col_with_docs(docs)):
        stats = focus_sessions_db.get_focus_stats('uid-1', date='2026-09-24')

    validated = FocusStats.model_validate(stats)
    assert validated.distracted_count == 3
    assert validated.focused_count == 1
    assert validated.distracted_minutes == 1
    assert validated.focused_minutes == 0
    by_app = {d.app_or_site: d for d in validated.top_distractions}
    assert by_app['YouTube'].total_seconds == 0
    assert by_app['YouTube'].count == 2
    assert by_app['Reddit'].total_seconds == 60
    assert by_app['Reddit'].count == 1


def test_get_focus_stats_falls_back_to_unknown_when_app_or_site_is_none_or_blank():
    docs = [
        _FakeDoc(
            'sess-null-app',
            {
                'status': 'distracted',
                'app_or_site': None,
                'description': 'Null app',
                'created_at': datetime(2026, 9, 24, 11, 0, tzinfo=timezone.utc),
                'duration_seconds': 120,
            },
        ),
        _FakeDoc(
            'sess-blank-app',
            {
                'status': 'distracted',
                'app_or_site': '   ',
                'description': 'Blank app',
                'created_at': datetime(2026, 9, 24, 11, 5, tzinfo=timezone.utc),
                'duration_seconds': 60,
            },
        ),
    ]
    with patch.object(focus_sessions_db, '_user_col', return_value=_mock_user_col_with_docs(docs)):
        stats = focus_sessions_db.get_focus_stats('uid-1', date='2026-09-24')

    validated = FocusStats.model_validate(stats)
    assert len(validated.top_distractions) == 1
    assert validated.top_distractions[0].app_or_site == 'Unknown'
    assert validated.top_distractions[0].total_seconds == 180
    assert validated.top_distractions[0].count == 2


def test_get_focus_sessions_normalizes_null_and_malformed_firestore_fields_for_response_model():
    docs = [
        _FakeDoc(
            'sess-malformed',
            {
                'status': None,
                'app_or_site': None,
                'description': None,
                'message': None,
                'created_at': datetime(2026, 9, 24, 12, 0),  # offset-naive datetime
                'duration_seconds': -15,  # negative legacy value
            },
        ),
        _FakeDoc(
            'sess-bool-duration',
            {
                'status': 'focused',
                'app_or_site': 'VS Code',
                'description': 'Coding',
                'created_at': None,
                'duration_seconds': True,
            },
        ),
    ]
    with patch.object(focus_sessions_db, '_user_col', return_value=_mock_user_col_with_docs(docs)):
        rows = focus_sessions_db.get_focus_sessions('uid-1')

    parsed = [FocusSession.model_validate(row) for row in rows]
    assert parsed[0].id == 'sess-malformed'
    assert parsed[0].status == 'focused'
    assert parsed[0].app_or_site == 'Unknown'
    assert parsed[0].description == ''
    assert parsed[0].created_at.tzinfo == timezone.utc
    assert parsed[0].duration_seconds == 0

    assert parsed[1].id == 'sess-bool-duration'
    assert parsed[1].created_at.tzinfo == timezone.utc
    assert parsed[1].duration_seconds is None
