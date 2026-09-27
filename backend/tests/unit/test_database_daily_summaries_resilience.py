"""Unit tests for backend/database/daily_summaries.py resilience and input validation."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch
import pytest

from google.api_core.exceptions import NotFound
import database.daily_summaries as daily_summaries_db


def _mock_db():
    fake_db = MagicMock()
    user_ref = fake_db.collection.return_value.document.return_value
    col_ref = user_ref.collection.return_value
    doc_ref = col_ref.document.return_value
    return fake_db, col_ref, doc_ref


# ============================================================================
# upsert_desktop_daily_usage
# ============================================================================


def test_upsert_desktop_daily_usage_validates_inputs():
    with pytest.raises(ValueError, match="uid must be a non-empty string"):
        daily_summaries_db.upsert_desktop_daily_usage("", "2026-09-01", "UTC", "dev1", {})

    with pytest.raises(ValueError, match="uid must be a non-empty string"):
        daily_summaries_db.upsert_desktop_daily_usage("   ", "2026-09-01", "UTC", "dev1", {})

    with pytest.raises(ValueError, match="date must be a non-empty string"):
        daily_summaries_db.upsert_desktop_daily_usage("u1", "", "UTC", "dev1", {})

    with pytest.raises(ValueError, match="client_device_id must be a non-empty string"):
        daily_summaries_db.upsert_desktop_daily_usage("u1", "2026-09-01", "UTC", "  ", {})


def test_upsert_desktop_daily_usage_partial_counters_and_coercion():
    fake_db, col_ref, doc_ref = _mock_db()
    existing_data = {
        "watching_seconds": 100,
        "listening_seconds": 20,
        "proactive_cards_shown": "invalid",  # non-int in db
    }
    snapshot = MagicMock()
    snapshot.exists = True
    snapshot.to_dict.return_value = existing_data
    doc_ref.get.return_value = snapshot

    transaction = fake_db.transaction.return_value

    with patch.object(daily_summaries_db, "db", fake_db), patch.object(
        daily_summaries_db.firestore, "transactional", side_effect=lambda fn: fn
    ):
        # Only provide partial counters; others should default to 0 without KeyError
        daily_summaries_db.upsert_desktop_daily_usage(
            "u1",
            "2026-09-01",
            "UTC",
            "dev1",
            {
                "watching_seconds": 150,  # max(100, 150) -> 150
                "listening_seconds": 10,  # max(20, 10) -> 20
                "proactive_cards_shown": True,  # bool should be ignored -> 0
                "proactive_cards_acted": -5,  # negative should be ignored -> 0
                # ptt_turns is completely missing -> should default to 0
            },
        )

    col_ref.document.assert_called_once_with("2026-09-01__dev1")
    payload = transaction.set.call_args.args[1]
    assert payload["watching_seconds"] == 150
    assert payload["listening_seconds"] == 20
    assert payload["proactive_cards_shown"] == 0
    assert payload["proactive_cards_acted"] == 0
    assert payload["ptt_turns"] == 0
    assert payload["date"] == "2026-09-01"
    assert payload["client_device_id"] == "dev1"


# ============================================================================
# get_desktop_daily_usage
# ============================================================================


def test_get_desktop_daily_usage_safe_empty_defaults():
    assert daily_summaries_db.get_desktop_daily_usage("", "2026-09-01") == {
        field: 0 for field in daily_summaries_db.DESKTOP_DAILY_USAGE_COUNTER_FIELDS
    }
    assert daily_summaries_db.get_desktop_daily_usage("u1", "") == {
        field: 0 for field in daily_summaries_db.DESKTOP_DAILY_USAGE_COUNTER_FIELDS
    }
    assert daily_summaries_db.get_desktop_daily_usage(None, None) == {
        field: 0 for field in daily_summaries_db.DESKTOP_DAILY_USAGE_COUNTER_FIELDS
    }


def test_get_desktop_daily_usage_skips_malformed_docs():
    fake_db, col_ref, _ = _mock_db()
    query = col_ref.where.return_value
    query.stream.return_value = [
        SimpleNamespace(to_dict=lambda: "not-a-dict"),
        SimpleNamespace(to_dict=lambda: {"watching_seconds": 50, "listening_seconds": "bad"}),
        SimpleNamespace(to_dict=lambda: {"watching_seconds": 25, "listening_seconds": 15}),
    ]

    with patch.object(daily_summaries_db, "db", fake_db):
        res = daily_summaries_db.get_desktop_daily_usage("u1", "2026-09-01")

    assert res["watching_seconds"] == 75
    assert res["listening_seconds"] == 15
    assert res["proactive_cards_shown"] == 0


# ============================================================================
# create_daily_summary
# ============================================================================


def test_create_daily_summary_validates_inputs():
    with pytest.raises(ValueError, match="uid must be a non-empty string"):
        daily_summaries_db.create_daily_summary("", {"id": "1"})

    with pytest.raises(ValueError, match="summary_data must be a dictionary"):
        daily_summaries_db.create_daily_summary("u1", "not-a-dict")


def test_create_daily_summary_allocates_uuid_if_missing():
    fake_db, col_ref, doc_ref = _mock_db()

    with patch.object(daily_summaries_db, "db", fake_db):
        summary_id = daily_summaries_db.create_daily_summary("u1", {"date": "2026-09-01"})

    assert isinstance(summary_id, str) and len(summary_id) > 10
    col_ref.document.assert_called_once_with(summary_id)
    doc_ref.set.assert_called_once_with({"date": "2026-09-01", "id": summary_id})


def test_create_daily_summary_uses_provided_id():
    fake_db, col_ref, doc_ref = _mock_db()

    with patch.object(daily_summaries_db, "db", fake_db):
        summary_id = daily_summaries_db.create_daily_summary("u1", {"id": "custom-123", "date": "2026-09-01"})

    assert summary_id == "custom-123"
    col_ref.document.assert_called_once_with("custom-123")
    doc_ref.set.assert_called_once_with({"id": "custom-123", "date": "2026-09-01"})


# ============================================================================
# get_daily_summary
# ============================================================================


def test_get_daily_summary_safe_defaults():
    assert daily_summaries_db.get_daily_summary("", "s1") is None
    assert daily_summaries_db.get_daily_summary("u1", "") is None
    assert daily_summaries_db.get_daily_summary(None, None) is None


def test_get_daily_summary_retrieves_doc():
    fake_db, col_ref, doc_ref = _mock_db()
    snapshot = MagicMock()
    snapshot.exists = True
    snapshot.to_dict.return_value = {"id": "s1", "headline": "Good day"}
    doc_ref.get.return_value = snapshot

    with patch.object(daily_summaries_db, "db", fake_db):
        res = daily_summaries_db.get_daily_summary("u1", "s1")

    assert res == {"id": "s1", "headline": "Good day"}
    col_ref.document.assert_called_once_with("s1")


# ============================================================================
# get_daily_summary_by_date
# ============================================================================


def test_get_daily_summary_by_date_safe_defaults():
    assert daily_summaries_db.get_daily_summary_by_date("", "2026-09-01") is None
    assert daily_summaries_db.get_daily_summary_by_date("u1", "") is None
    assert daily_summaries_db.get_daily_summary_by_date(None, None) is None


def test_get_daily_summary_by_date_retrieves_doc():
    fake_db, col_ref, _ = _mock_db()
    query = col_ref.where.return_value.limit.return_value
    query.stream.return_value = [SimpleNamespace(to_dict=lambda: {"id": "s1", "date": "2026-09-01"})]

    with patch.object(daily_summaries_db, "db", fake_db):
        res = daily_summaries_db.get_daily_summary_by_date("u1", "2026-09-01")

    assert res == {"id": "s1", "date": "2026-09-01"}


# ============================================================================
# get_daily_summaries
# ============================================================================


def test_get_daily_summaries_safe_defaults_and_clamping():
    assert daily_summaries_db.get_daily_summaries("") == []
    assert daily_summaries_db.get_daily_summaries(None) == []

    fake_db, col_ref, _ = _mock_db()
    query = col_ref.where.return_value.where.return_value.order_by.return_value.limit.return_value.offset.return_value
    query.stream.return_value = [
        SimpleNamespace(to_dict=lambda: {"id": "s1"}),
        SimpleNamespace(to_dict=lambda: "invalid-dict"),
    ]

    with patch.object(daily_summaries_db, "db", fake_db):
        res = daily_summaries_db.get_daily_summaries(
            "u1", limit=-10, offset=-5, start_date="2026-09-01", end_date="2026-09-05"
        )

    assert res == [{"id": "s1"}]


# ============================================================================
# update_daily_summary
# ============================================================================


def test_update_daily_summary_validates_inputs():
    with pytest.raises(ValueError, match="uid must be a non-empty string"):
        daily_summaries_db.update_daily_summary("", "s1", {})

    with pytest.raises(ValueError, match="summary_id must be a non-empty string"):
        daily_summaries_db.update_daily_summary("u1", "", {})

    with pytest.raises(ValueError, match="summary_data must be a dictionary"):
        daily_summaries_db.update_daily_summary("u1", "s1", "not-a-dict")


def test_update_daily_summary_preserves_id():
    fake_db, col_ref, doc_ref = _mock_db()

    with patch.object(daily_summaries_db, "db", fake_db):
        daily_summaries_db.update_daily_summary("u1", "s1", {"id": "foreign-id", "overview": "Updated overview"})

    col_ref.document.assert_called_once_with("s1")
    doc_ref.set.assert_called_once_with({"id": "s1", "overview": "Updated overview"})


# ============================================================================
# delete_daily_summary
# ============================================================================


def test_delete_daily_summary_safe_defaults():
    assert daily_summaries_db.delete_daily_summary("", "s1") is False
    assert daily_summaries_db.delete_daily_summary("u1", "") is False
    assert daily_summaries_db.delete_daily_summary(None, None) is False


def test_delete_daily_summary_handles_not_found():
    fake_db, col_ref, doc_ref = _mock_db()
    doc_ref.delete.side_effect = NotFound("doc not found")

    with patch.object(daily_summaries_db, "db", fake_db):
        assert daily_summaries_db.delete_daily_summary("u1", "s1") is False


def test_delete_daily_summary_handles_redis_error_gracefully():
    fake_db, col_ref, doc_ref = _mock_db()

    with patch.object(daily_summaries_db, "db", fake_db), patch.object(
        daily_summaries_db.redis_db, "remove_daily_summary_to_uid", side_effect=Exception("redis down")
    ):
        assert daily_summaries_db.delete_daily_summary("u1", "s1") is True
    doc_ref.delete.assert_called_once()


# ============================================================================
# set_daily_summary_visibility
# ============================================================================


def test_set_daily_summary_visibility_validates_inputs():
    with pytest.raises(ValueError, match="uid must be a non-empty string"):
        daily_summaries_db.set_daily_summary_visibility("", "s1", "public")

    with pytest.raises(ValueError, match="summary_id must be a non-empty string"):
        daily_summaries_db.set_daily_summary_visibility("u1", "", "public")


def test_set_daily_summary_visibility_handles_not_found():
    fake_db, col_ref, doc_ref = _mock_db()
    doc_ref.update.side_effect = NotFound("doc not found")

    with patch.object(daily_summaries_db, "db", fake_db):
        # Should not raise exception
        daily_summaries_db.set_daily_summary_visibility("u1", "s1", "private")
    doc_ref.update.assert_called_once_with({"visibility": "private"})


# ============================================================================
# get_summaries_count
# ============================================================================


def test_get_summaries_count_safe_defaults():
    assert daily_summaries_db.get_summaries_count("") == 0
    assert daily_summaries_db.get_summaries_count(None) == 0


def test_get_summaries_count_success_and_exception_fallback():
    fake_db, col_ref, _ = _mock_db()
    count_query = col_ref.count.return_value
    count_query.get.return_value = [[SimpleNamespace(value=42)]]

    with patch.object(daily_summaries_db, "db", fake_db):
        assert daily_summaries_db.get_summaries_count("u1") == 42

    count_query.get.side_effect = Exception("firestore error")
    with patch.object(daily_summaries_db, "db", fake_db):
        assert daily_summaries_db.get_summaries_count("u1") == 0
