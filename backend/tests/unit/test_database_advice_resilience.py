"""Hermetic unit tests for input validation, boundary guards, batch chunking,
and error resilience in backend/database/advice.py.
"""

from unittest.mock import MagicMock, patch

import pytest

import database.advice as advice_db


def _make_mock_snapshot(doc_id: str, exists: bool = True, data: dict | None = None):
    snap = MagicMock()
    snap.id = doc_id
    snap.exists = exists
    snap.to_dict.return_value = data if data is not None else {}
    return snap


# ---------------------------------------------------------------------------
# _user_col & create_advice validation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("invalid_uid", [None, "", "   "])
def test_user_col_rejects_invalid_uid(invalid_uid):
    with pytest.raises(ValueError, match="uid must be a non-empty string"):
        advice_db._user_col(invalid_uid, "advice")  # type: ignore[arg-type]


@pytest.mark.parametrize("invalid_uid", [None, "", "   "])
def test_create_advice_rejects_invalid_uid(invalid_uid):
    with pytest.raises(ValueError, match="uid must be a non-empty string"):
        advice_db.create_advice(invalid_uid, "Focus on deep work")  # type: ignore[arg-type]


@pytest.mark.parametrize("invalid_content", [None, "", "   "])
def test_create_advice_rejects_invalid_content(invalid_content):
    with pytest.raises(ValueError, match="content must be a non-empty string"):
        advice_db.create_advice("u-1", invalid_content)  # type: ignore[arg-type]


def test_create_advice_normalizes_and_clamps_confidence():
    fake_db = MagicMock()
    doc_ref = MagicMock()
    fake_db.collection.return_value.document.return_value.collection.return_value.document.return_value = doc_ref

    with patch.object(advice_db, "db", fake_db):
        res = advice_db.create_advice(
            "  user-abc  ",
            "  Take a break now  ",
            category="  health  ",
            confidence=1.8,  # clamped to 1.0
        )

    assert res["content"] == "Take a break now"
    assert res["category"] == "health"
    assert res["confidence"] == 1.0
    assert res["is_read"] is False
    assert res["is_dismissed"] is False
    doc_ref.set.assert_called_once()
    fake_db.collection.return_value.document.assert_called_with("user-abc")


def test_create_advice_handles_invalid_confidence_type():
    fake_db = MagicMock()
    doc_ref = MagicMock()
    fake_db.collection.return_value.document.return_value.collection.return_value.document.return_value = doc_ref

    with patch.object(advice_db, "db", fake_db):
        res = advice_db.create_advice(
            "user-1",
            "Valid advice",
            confidence="not-a-float",  # defaults to 0.5
        )

    assert res["confidence"] == 0.5


# ---------------------------------------------------------------------------
# get_advice validation & limits
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("invalid_uid", [None, "", "   "])
def test_get_advice_invalid_uid_returns_empty(invalid_uid):
    fake_db = MagicMock()
    with patch.object(advice_db, "db", fake_db):
        assert advice_db.get_advice(invalid_uid) == []  # type: ignore[arg-type]
    fake_db.collection.assert_not_called()


@pytest.mark.parametrize("invalid_limit", [0, -1, -50])
def test_get_advice_invalid_limit_returns_empty(invalid_limit):
    fake_db = MagicMock()
    with patch.object(advice_db, "db", fake_db):
        assert advice_db.get_advice("u-1", limit=invalid_limit) == []
    fake_db.collection.assert_not_called()


def test_get_advice_queries_and_returns_list():
    fake_db = MagicMock()
    query_mock = MagicMock()
    fake_db.collection.return_value.document.return_value.collection.return_value.order_by.return_value = query_mock
    query_mock.where.return_value = query_mock
    query_mock.limit.return_value = query_mock
    query_mock.offset.return_value = query_mock

    snap = _make_mock_snapshot("adv-1", exists=True, data={"content": "Meditate", "is_read": False})
    query_mock.stream.return_value = [snap]

    with patch.object(advice_db, "db", fake_db):
        results = advice_db.get_advice("  user-123  ", category="  wellness  ", limit=20, offset=5)

    assert len(results) == 1
    assert results[0]["id"] == "adv-1"
    assert results[0]["content"] == "Meditate"
    fake_db.collection.return_value.document.assert_called_with("user-123")


# ---------------------------------------------------------------------------
# update_advice validation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("invalid_arg", [None, "", "   "])
def test_update_advice_invalid_coords_returns_none(invalid_arg):
    fake_db = MagicMock()
    with patch.object(advice_db, "db", fake_db):
        assert advice_db.update_advice(invalid_arg, "adv-1", is_read=True) is None  # type: ignore[arg-type]
        assert advice_db.update_advice("u-1", invalid_arg, is_read=True) is None  # type: ignore[arg-type]
    fake_db.collection.assert_not_called()


def test_update_advice_missing_document_returns_none():
    fake_db = MagicMock()
    doc_ref = MagicMock()
    doc_ref.get.return_value = _make_mock_snapshot("adv-1", exists=False)
    fake_db.collection.return_value.document.return_value.collection.return_value.document.return_value = doc_ref

    with patch.object(advice_db, "db", fake_db):
        res = advice_db.update_advice("u-1", "adv-1", is_read=True)

    assert res is None
    doc_ref.update.assert_not_called()


def test_update_advice_success():
    fake_db = MagicMock()
    doc_ref = MagicMock()
    snap_before = _make_mock_snapshot("adv-1", exists=True, data={"content": "Walk", "is_read": False})
    snap_after = _make_mock_snapshot("adv-1", exists=True, data={"content": "Walk", "is_read": True})
    doc_ref.get.side_effect = [snap_before, snap_after]
    fake_db.collection.return_value.document.return_value.collection.return_value.document.return_value = doc_ref

    with patch.object(advice_db, "db", fake_db):
        res = advice_db.update_advice("  u-1  ", "  adv-1  ", is_read=True, is_dismissed=False)

    assert res is not None
    assert res["id"] == "adv-1"
    assert res["is_read"] is True
    doc_ref.update.assert_called_once()
    payload = doc_ref.update.call_args[0][0]
    assert payload["is_read"] is True
    assert payload["is_dismissed"] is False


# ---------------------------------------------------------------------------
# delete_advice validation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("invalid_arg", [None, "", "   "])
def test_delete_advice_invalid_coords_returns_false(invalid_arg):
    fake_db = MagicMock()
    with patch.object(advice_db, "db", fake_db):
        assert advice_db.delete_advice(invalid_arg, "adv-1") is False  # type: ignore[arg-type]
        assert advice_db.delete_advice("u-1", invalid_arg) is False  # type: ignore[arg-type]
    fake_db.collection.assert_not_called()


def test_delete_advice_nonexistent_returns_false():
    fake_db = MagicMock()
    doc_ref = MagicMock()
    doc_ref.get.return_value = _make_mock_snapshot("adv-1", exists=False)
    fake_db.collection.return_value.document.return_value.collection.return_value.document.return_value = doc_ref

    with patch.object(advice_db, "db", fake_db):
        assert advice_db.delete_advice("u-1", "adv-1") is False

    doc_ref.delete.assert_not_called()


def test_delete_advice_existing_deletes_and_returns_true():
    fake_db = MagicMock()
    doc_ref = MagicMock()
    doc_ref.get.return_value = _make_mock_snapshot("adv-1", exists=True)
    fake_db.collection.return_value.document.return_value.collection.return_value.document.return_value = doc_ref

    with patch.object(advice_db, "db", fake_db):
        assert advice_db.delete_advice("  u-1  ", "  adv-1  ") is True

    doc_ref.delete.assert_called_once()
    fake_db.collection.return_value.document.assert_called_with("u-1")
    fake_db.collection.return_value.document.return_value.collection.return_value.document.assert_called_with("adv-1")


# ---------------------------------------------------------------------------
# mark_all_advice_read & Batch Chunking (>500 ops)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("invalid_uid", [None, "", "   "])
def test_mark_all_advice_read_invalid_uid_returns_zero(invalid_uid):
    fake_db = MagicMock()
    with patch.object(advice_db, "db", fake_db):
        assert advice_db.mark_all_advice_read(invalid_uid) == 0  # type: ignore[arg-type]
    fake_db.collection.assert_not_called()


def test_mark_all_advice_read_splits_at_500_ops():
    fake_db = MagicMock()
    batch_mock = MagicMock()
    fake_db.batch.return_value = batch_mock

    # 501 unread items -> 500 in first batch, 1 in second batch
    snaps = [_make_mock_snapshot(f"adv-{i}", exists=True) for i in range(501)]
    col_mock = fake_db.collection.return_value.document.return_value.collection.return_value
    col_mock.where.return_value.stream.return_value = iter(snaps)

    with patch.object(advice_db, "db", fake_db):
        total = advice_db.mark_all_advice_read("  u-1  ")

    assert total == 501
    assert fake_db.batch.call_count == 2
    assert batch_mock.commit.call_count == 2
    assert batch_mock.update.call_count == 501
    fake_db.collection.return_value.document.assert_called_with("u-1")
