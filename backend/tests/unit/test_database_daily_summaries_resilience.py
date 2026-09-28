"""Hermetic unit tests for input validation, boundary guards, and resilience in database/daily_summaries.py."""

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

import database.daily_summaries as ds_db


def _make_mock_snapshot(data: dict | None = None, exists: bool = True):
    snap = MagicMock()
    snap.exists = exists
    snap.to_dict.return_value = data if data is not None else {}
    return snap


@pytest.fixture(autouse=True)
def hermetic_firestore(monkeypatch):
    """Enforce hermetic test isolation by replacing Firestore client, redis, and transactional decorator."""
    fake_db = MagicMock()
    fake_redis = MagicMock()
    monkeypatch.setattr(ds_db, "db", fake_db)
    monkeypatch.setattr(ds_db, "redis_db", fake_redis)
    monkeypatch.setattr(ds_db.firestore, "transactional", lambda fn: fn)
    monkeypatch.setattr(ds_db.firestore.Query, "DESCENDING", "DESCENDING")
    return fake_db, fake_redis


# ---------------------------------------------------------------------------
# Input validation: uid rejection across all functions
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("invalid_uid", [None, "", "   ", 123, [], {}])
def test_upsert_desktop_daily_usage_rejects_invalid_uid(invalid_uid):
    with pytest.raises(ValueError, match="uid must be a non-empty string"):
        ds_db.upsert_desktop_daily_usage(invalid_uid, "2026-09-28", "UTC", "dev-1", {"watching_seconds": 10})  # type: ignore[arg-type]


@pytest.mark.parametrize("invalid_uid", [None, "", "   ", 123, [], {}])
def test_get_desktop_daily_usage_rejects_invalid_uid(invalid_uid):
    with pytest.raises(ValueError, match="uid must be a non-empty string"):
        ds_db.get_desktop_daily_usage(invalid_uid, "2026-09-28")  # type: ignore[arg-type]


@pytest.mark.parametrize("invalid_uid", [None, "", "   ", 123, [], {}])
def test_create_daily_summary_rejects_invalid_uid(invalid_uid):
    with pytest.raises(ValueError, match="uid must be a non-empty string"):
        ds_db.create_daily_summary(invalid_uid, {"id": "sum-1"})  # type: ignore[arg-type]


@pytest.mark.parametrize("invalid_uid", [None, "", "   ", 123, [], {}])
def test_get_daily_summary_rejects_invalid_uid(invalid_uid):
    with pytest.raises(ValueError, match="uid must be a non-empty string"):
        ds_db.get_daily_summary(invalid_uid, "sum-1")  # type: ignore[arg-type]


@pytest.mark.parametrize("invalid_uid", [None, "", "   ", 123, [], {}])
def test_get_daily_summary_by_date_rejects_invalid_uid(invalid_uid):
    with pytest.raises(ValueError, match="uid must be a non-empty string"):
        ds_db.get_daily_summary_by_date(invalid_uid, "2026-09-28")  # type: ignore[arg-type]


@pytest.mark.parametrize("invalid_uid", [None, "", "   ", 123, [], {}])
def test_get_daily_summaries_rejects_invalid_uid(invalid_uid):
    with pytest.raises(ValueError, match="uid must be a non-empty string"):
        ds_db.get_daily_summaries(invalid_uid)  # type: ignore[arg-type]


@pytest.mark.parametrize("invalid_uid", [None, "", "   ", 123, [], {}])
def test_update_daily_summary_rejects_invalid_uid(invalid_uid):
    with pytest.raises(ValueError, match="uid must be a non-empty string"):
        ds_db.update_daily_summary(invalid_uid, "sum-1", {"overview": "new"})  # type: ignore[arg-type]


@pytest.mark.parametrize("invalid_uid", [None, "", "   ", 123, [], {}])
def test_delete_daily_summary_rejects_invalid_uid(invalid_uid):
    with pytest.raises(ValueError, match="uid must be a non-empty string"):
        ds_db.delete_daily_summary(invalid_uid, "sum-1")  # type: ignore[arg-type]


@pytest.mark.parametrize("invalid_uid", [None, "", "   ", 123, [], {}])
def test_set_daily_summary_visibility_rejects_invalid_uid(invalid_uid):
    with pytest.raises(ValueError, match="uid must be a non-empty string"):
        ds_db.set_daily_summary_visibility(invalid_uid, "sum-1", "public")  # type: ignore[arg-type]


@pytest.mark.parametrize("invalid_uid", [None, "", "   ", 123, [], {}])
def test_get_summaries_count_rejects_invalid_uid(invalid_uid):
    with pytest.raises(ValueError, match="uid must be a non-empty string"):
        ds_db.get_summaries_count(invalid_uid)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Input validation: identifier & date rejection
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("invalid_id", [None, "", "   ", 123, [], {}])
def test_get_daily_summary_rejects_invalid_id(invalid_id):
    with pytest.raises(ValueError, match="summary_id must be a non-empty string"):
        ds_db.get_daily_summary("u-1", invalid_id)  # type: ignore[arg-type]


@pytest.mark.parametrize("invalid_id", [None, "", "   ", 123, [], {}])
def test_update_daily_summary_rejects_invalid_id(invalid_id):
    with pytest.raises(ValueError, match="summary_id must be a non-empty string"):
        ds_db.update_daily_summary("u-1", invalid_id, {"overview": "new"})  # type: ignore[arg-type]


@pytest.mark.parametrize("invalid_id", [None, "", "   ", 123, [], {}])
def test_delete_daily_summary_rejects_invalid_id(invalid_id):
    with pytest.raises(ValueError, match="summary_id must be a non-empty string"):
        ds_db.delete_daily_summary("u-1", invalid_id)  # type: ignore[arg-type]


@pytest.mark.parametrize("invalid_id", [None, "", "   ", 123, [], {}])
def test_set_daily_summary_visibility_rejects_invalid_id(invalid_id):
    with pytest.raises(ValueError, match="summary_id must be a non-empty string"):
        ds_db.set_daily_summary_visibility("u-1", invalid_id, "public")  # type: ignore[arg-type]


@pytest.mark.parametrize("invalid_date", [None, "", "   ", 123, [], {}])
def test_get_daily_summary_by_date_rejects_invalid_date(invalid_date):
    with pytest.raises(ValueError, match="date must be a non-empty string"):
        ds_db.get_daily_summary_by_date("u-1", invalid_date)  # type: ignore[arg-type]


@pytest.mark.parametrize("invalid_date", [None, "", "   ", 123, [], {}])
def test_get_desktop_daily_usage_rejects_invalid_date(invalid_date):
    with pytest.raises(ValueError, match="date must be a non-empty string"):
        ds_db.get_desktop_daily_usage("u-1", invalid_date)  # type: ignore[arg-type]


@pytest.mark.parametrize("invalid_device", [None, "", "   ", 123, [], {}])
def test_upsert_desktop_daily_usage_rejects_invalid_device_id(invalid_device):
    with pytest.raises(ValueError, match="client_device_id must be a non-empty string"):
        ds_db.upsert_desktop_daily_usage("u-1", "2026-09-28", "UTC", invalid_device, {"watching_seconds": 10})  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Input validation: payload and dictionary validation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("invalid_payload", [None, "", "string", 123, []])
def test_create_daily_summary_rejects_non_dict_payload(invalid_payload):
    with pytest.raises(ValueError, match="summary_data must be a dictionary"):
        ds_db.create_daily_summary("u-1", invalid_payload)  # type: ignore[arg-type]


@pytest.mark.parametrize("invalid_id", [None, "", "   ", 123])
def test_create_daily_summary_rejects_missing_or_invalid_id(invalid_id):
    with pytest.raises(ValueError, match="summary_id must be a non-empty string"):
        ds_db.create_daily_summary("u-1", {"id": invalid_id, "headline": "Test"})  # type: ignore[arg-type]


@pytest.mark.parametrize("invalid_payload", [None, "", "string", 123, []])
def test_update_daily_summary_rejects_non_dict_payload(invalid_payload):
    with pytest.raises(ValueError, match="summary_data must be a dictionary"):
        ds_db.update_daily_summary("u-1", "sum-1", invalid_payload)  # type: ignore[arg-type]


@pytest.mark.parametrize("invalid_counters", [None, "", "string", 123, []])
def test_upsert_desktop_daily_usage_rejects_non_dict_counters(invalid_counters):
    with pytest.raises(ValueError, match="counters must be a dictionary"):
        ds_db.upsert_desktop_daily_usage("u-1", "2026-09-28", "UTC", "dev-1", invalid_counters)  # type: ignore[arg-type]


@pytest.mark.parametrize("invalid_vis", [None, "", "   ", 123, []])
def test_set_daily_summary_visibility_rejects_invalid_visibility(invalid_vis):
    with pytest.raises(ValueError, match="visibility must be a non-empty string"):
        ds_db.set_daily_summary_visibility("u-1", "sum-1", invalid_vis)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Behavioral and resilience tests
# ---------------------------------------------------------------------------


def test_upsert_desktop_daily_usage_resilience_missing_keys():
    fake_db, _ = ds_db.db, ds_db.redis_db
    user_doc = fake_db.collection.return_value.document.return_value
    usage_col = user_doc.collection.return_value
    usage_doc = usage_col.document.return_value
    usage_doc.get.return_value = _make_mock_snapshot({"watching_seconds": 150})
    txn = fake_db.transaction.return_value

    ds_db.upsert_desktop_daily_usage("u-1", "2026-09-28", "America/New_York", "dev-1", {"watching_seconds": 200})

    usage_col.document.assert_called_once_with("2026-09-28__dev-1")
    txn.set.assert_called_once()
    payload = txn.set.call_args[0][1]
    assert payload["watching_seconds"] == 200
    assert payload["listening_seconds"] == 0
    assert payload["proactive_cards_shown"] == 0
    assert payload["date"] == "2026-09-28"
    assert payload["timezone"] == "America/New_York"
    assert payload["client_device_id"] == "dev-1"


def test_get_desktop_daily_usage_aggregates_and_ignores_malformed():
    fake_db, _ = ds_db.db, ds_db.redis_db
    user_doc = fake_db.collection.return_value.document.return_value
    query = user_doc.collection.return_value.where.return_value
    doc1 = _make_mock_snapshot({"watching_seconds": 50, "listening_seconds": 20})
    doc2 = _make_mock_snapshot({"watching_seconds": 100, "ptt_turns": 4})
    doc3 = MagicMock()
    doc3.to_dict.return_value = "not_a_dict"
    query.stream.return_value = [doc1, doc2, doc3]

    totals = ds_db.get_desktop_daily_usage("u-1", "2026-09-28")
    assert totals["watching_seconds"] == 150
    assert totals["listening_seconds"] == 20
    assert totals["ptt_turns"] == 4
    assert totals["proactive_cards_shown"] == 0


def test_create_daily_summary_happy_path():
    fake_db, _ = ds_db.db, ds_db.redis_db
    user_doc = fake_db.collection.return_value.document.return_value
    summary_doc = user_doc.collection.return_value.document.return_value

    summary_id = ds_db.create_daily_summary("  u-1  ", {"id": "  sum-123  ", "headline": "Productive Monday"})
    assert summary_id == "sum-123"
    summary_doc.set.assert_called_once_with({"id": "sum-123", "headline": "Productive Monday"})


def test_get_daily_summary_lifecycle():
    fake_db, _ = ds_db.db, ds_db.redis_db
    user_doc = fake_db.collection.return_value.document.return_value
    summary_doc = user_doc.collection.return_value.document.return_value

    summary_doc.get.return_value = _make_mock_snapshot({"id": "sum-1", "overview": "Everything was great"})
    res = ds_db.get_daily_summary("u-1", "sum-1")
    assert res == {"id": "sum-1", "overview": "Everything was great"}

    summary_doc.get.return_value = _make_mock_snapshot(exists=False)
    assert ds_db.get_daily_summary("u-1", "sum-1") is None


def test_get_daily_summary_by_date_lifecycle():
    fake_db, _ = ds_db.db, ds_db.redis_db
    user_doc = fake_db.collection.return_value.document.return_value
    query = user_doc.collection.return_value.where.return_value.limit.return_value

    query.stream.return_value = [_make_mock_snapshot({"id": "sum-1", "date": "2026-09-28"})]
    assert ds_db.get_daily_summary_by_date("u-1", "2026-09-28") == {"id": "sum-1", "date": "2026-09-28"}

    query.stream.return_value = []
    assert ds_db.get_daily_summary_by_date("u-1", "2026-09-28") is None


def test_get_daily_summaries_pagination_clamping():
    fake_db, _ = ds_db.db, ds_db.redis_db
    user_doc = fake_db.collection.return_value.document.return_value
    col = user_doc.collection.return_value
    query = col.order_by.return_value.limit.return_value.offset.return_value
    query.stream.return_value = []

    # Negative limit and offset clamped safely
    ds_db.get_daily_summaries("u-1", limit=-10, offset=-5)
    col.order_by.return_value.limit.assert_called_with(1)
    col.order_by.return_value.limit.return_value.offset.assert_called_with(0)

    # Overflow limit clamped to 200 (accommodates MCP +1 pagination)
    ds_db.get_daily_summaries("u-1", limit=999, offset=20)
    col.order_by.return_value.limit.assert_called_with(200)
    col.order_by.return_value.limit.return_value.offset.assert_called_with(20)


def test_update_daily_summary_enforces_id():
    fake_db, _ = ds_db.db, ds_db.redis_db
    user_doc = fake_db.collection.return_value.document.return_value
    summary_doc = user_doc.collection.return_value.document.return_value

    ds_db.update_daily_summary("u-1", "sum-orig", {"id": "different-id", "overview": "Regenerated"})
    summary_doc.set.assert_called_once_with({"id": "sum-orig", "overview": "Regenerated"})


def test_delete_daily_summary_cleans_cache():
    fake_db, fake_redis = ds_db.db, ds_db.redis_db
    user_doc = fake_db.collection.return_value.document.return_value
    summary_doc = user_doc.collection.return_value.document.return_value

    res = ds_db.delete_daily_summary("u-1", "sum-1")
    assert res is True
    summary_doc.delete.assert_called_once()
    fake_redis.remove_daily_summary_to_uid.assert_called_once_with("sum-1")


def test_set_daily_summary_visibility_happy_path():
    fake_db, _ = ds_db.db, ds_db.redis_db
    user_doc = fake_db.collection.return_value.document.return_value
    summary_doc = user_doc.collection.return_value.document.return_value

    ds_db.set_daily_summary_visibility("u-1", "sum-1", "  private  ")
    summary_doc.update.assert_called_once_with({"visibility": "private"})


def test_get_summaries_count_happy_path():
    fake_db, _ = ds_db.db, ds_db.redis_db
    user_doc = fake_db.collection.return_value.document.return_value
    count_query = user_doc.collection.return_value.count.return_value
    val_item = MagicMock()
    val_item.value = 17
    count_query.get.return_value = [[val_item]]

    count = ds_db.get_summaries_count("u-1")
    assert count == 17
