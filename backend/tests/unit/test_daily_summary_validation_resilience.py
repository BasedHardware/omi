"""Unit tests for Daily Summary response validation resilience (#8264, #1551).

Verifies that:
1. GET /v1/dev/user/daily-summaries skips malformed/corrupt summary records
   without failing the whole page with an HTTP 500 ResponseValidationError.
2. GET /v1/dev/user/daily-summaries/{summary_id} safely handles corrupt documents
   by raising HTTP 503 instead of an uncaught HTTP 500.
3. GET /v1/users/daily-summaries validates records individually and skips
   corrupt ones without HTTP 500 crashes.
4. GET /v1/users/daily-summaries/{summary_id} returns HTTP 503 when a document
   fails schema validation.
5. GET /v1/users/daily-summaries/search filters and validates matching records
   individually without failing the search query.
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException, Request

import database.daily_summaries as daily_summaries_db
import routers.users as users_router
from dependencies import ApiKeyAuth
from models.daily_summary import DailySummaryResponse
from routers.developer import get_developer_daily_summaries, get_developer_daily_summary
from routers.users import get_daily_summaries, get_daily_summary, search_daily_summaries


def _read_auth():
    return ApiKeyAuth(
        uid="uid1",
        scopes=["conversations:read"],
        app_id="test-app",
        key_id="test-key",
    )


def _make_valid_summary(summary_id="sum-1"):
    return {
        "id": summary_id,
        "date": "2026-10-12",
        "created_at": datetime(2026, 10, 12, 10, 0, 0, tzinfo=timezone.utc),
        "headline": "Productive Day",
        "overview": "Completed roadmap items.",
        "day_emoji": "🎯",
        "memories_learned": [
            {
                "memory_id": "mem-101",
                "content": "Learned about database schema migrations",
                "category": "engineering",
            }
        ],
    }


def _make_corrupt_summary(summary_id="sum-corrupt"):
    # Missing required string fields in memories_learned -> causes ValidationError in DailySummaryResponse
    return {
        "id": summary_id,
        "date": "2026-10-12",
        "memories_learned": [{"invalid_structure": 123}],
    }


class TestDeveloperDailySummaryValidationResilience:
    @patch.object(daily_summaries_db, "get_daily_summaries")
    def test_get_developer_daily_summaries_skips_malformed_records(self, mock_get_summaries):
        mock_get_summaries.return_value = [
            _make_valid_summary("sum-1"),
            _make_corrupt_summary("sum-corrupt-1"),
            "non-dict-record",
            _make_valid_summary("sum-2"),
        ]

        result = get_developer_daily_summaries(
            limit=30,
            offset=0,
            auth=_read_auth(),
            request=Request({'type': 'http', 'headers': [], 'path': '/v1/dev/user/daily-summaries', 'method': 'GET'}),
        )

        assert "summaries" in result
        summaries = result["summaries"]
        assert len(summaries) == 2
        # Verifies valid objects validate cleanly as DailySummaryResponse
        assert isinstance(summaries[0], DailySummaryResponse)
        assert summaries[0].id == "sum-1"
        assert summaries[1].id == "sum-2"

    @patch.object(daily_summaries_db, "get_daily_summary")
    def test_get_developer_daily_summary_valid(self, mock_get_summary):
        mock_get_summary.return_value = _make_valid_summary("sum-1")

        result = get_developer_daily_summary(
            summary_id="sum-1",
            auth=_read_auth(),
            request=MagicMock(),
        )

        assert isinstance(result, DailySummaryResponse)
        assert result.id == "sum-1"

    @patch.object(daily_summaries_db, "get_daily_summary")
    def test_get_developer_daily_summary_corrupt_is_unavailable(self, mock_get_summary):
        mock_get_summary.return_value = _make_corrupt_summary("sum-corrupt-1")

        with pytest.raises(HTTPException) as exc_info:
            get_developer_daily_summary(
                summary_id="sum-corrupt-1",
                auth=_read_auth(),
                request=MagicMock(),
            )

        assert exc_info.value.status_code == 503

    @patch.object(daily_summaries_db, "get_daily_summary")
    def test_get_developer_daily_summary_not_found_raises_404(self, mock_get_summary):
        mock_get_summary.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            get_developer_daily_summary(
                summary_id="sum-missing",
                auth=_read_auth(),
                request=MagicMock(),
            )

        assert exc_info.value.status_code == 404
        assert exc_info.value.detail == "Daily summary not found"


class TestUsersDailySummaryValidationResilience:
    @patch.object(daily_summaries_db, "get_daily_summaries")
    def test_get_daily_summaries_skips_malformed_records(self, mock_get_summaries):
        mock_get_summaries.return_value = [
            _make_valid_summary("sum-1"),
            _make_corrupt_summary("sum-bad"),
            {"id": "missing-date"},
            _make_valid_summary("sum-2"),
        ]

        result = get_daily_summaries(limit=30, offset=0, uid="uid1")

        assert "summaries" in result
        summaries = result["summaries"]
        assert [summary.id for summary in summaries] == ['sum-1', 'missing-date', 'sum-2']

    @patch.object(daily_summaries_db, "get_daily_summary")
    def test_get_daily_summary_corrupt_is_unavailable(self, mock_get_summary):
        mock_get_summary.return_value = _make_corrupt_summary("sum-bad")

        with pytest.raises(HTTPException) as exc_info:
            get_daily_summary(summary_id="sum-bad", uid="uid1")

        assert exc_info.value.status_code == 503
        assert exc_info.value.detail == 'Daily recap data is temporarily unavailable'

    @patch.object(daily_summaries_db, "get_daily_summaries")
    def test_search_daily_summaries_skips_malformed_matches(self, mock_get_summaries):
        valid = _make_valid_summary("sum-1")
        corrupt = _make_corrupt_summary("sum-corrupt")
        corrupt["headline"] = "Productive Day"

        mock_get_summaries.return_value = [valid, corrupt]

        result = search_daily_summaries(query="Productive", limit=10, uid="uid1")

        assert "summaries" in result
        # Only valid matching summary survives
        assert len(result["summaries"]) == 1
        assert result["summaries"][0].id == "sum-1"


def test_invalid_matches_do_not_consume_search_limit(monkeypatch):
    bad = _make_corrupt_summary()
    bad['headline'] = 'Productive'
    good = _make_valid_summary('good')
    monkeypatch.setattr(daily_summaries_db, 'get_daily_summaries', lambda *args, **kwargs: [bad, good])
    result = users_router.search_daily_summaries(query='Productive', limit=1, uid='uid1')
    assert [s.id for s in result['summaries']] == ['good']


def test_validation_logs_never_include_stored_private_content(monkeypatch, caplog):
    bad = _make_valid_summary('bad')
    bad['stats'] = {'watching_minutes': 'PRIVATE_RECAP_TEXT_DO_NOT_LOG'}
    good = _make_valid_summary('good')
    monkeypatch.setattr(daily_summaries_db, 'get_daily_summaries', lambda *args, **kwargs: [bad, good])
    users_router.get_daily_summaries(limit=30, offset=0, uid='uid1')
    assert 'PRIVATE_RECAP_TEXT_DO_NOT_LOG' not in caplog.text


def test_all_corrupt_records_are_an_unavailable_read_not_an_empty_account(monkeypatch):
    monkeypatch.setattr(daily_summaries_db, 'get_daily_summaries', lambda *args, **kwargs: [_make_corrupt_summary()])
    with pytest.raises(HTTPException) as error:
        users_router.get_daily_summaries(limit=30, offset=0, uid='uid1')
    assert error.value.status_code == 503
