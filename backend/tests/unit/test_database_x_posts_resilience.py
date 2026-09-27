"""Hermetic unit tests for input validation, boundary guards, and resilience in database/x_posts.py."""

from unittest.mock import MagicMock, patch

import pytest

import database.x_posts as x_posts_db


def _make_mock_snapshot(doc_id: str, exists: bool = True, data: dict | None = None):
    snap = MagicMock()
    snap.id = doc_id
    snap.exists = exists
    snap.to_dict.return_value = data if data is not None else {}
    return snap


# ---------------------------------------------------------------------------
# save_x_posts input validation and deduplication
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("invalid_uid", [None, "", "   ", 123])
def test_save_x_posts_rejects_invalid_uid(invalid_uid):
    with pytest.raises(ValueError, match="uid must be a non-empty string"):
        x_posts_db.save_x_posts(invalid_uid, [{"id": "1", "text": "hello"}])  # type: ignore[arg-type]


@pytest.mark.parametrize("invalid_posts", [None, "not-a-list", 123, {"id": "1"}])
def test_save_x_posts_rejects_invalid_posts(invalid_posts):
    with pytest.raises(ValueError, match="posts must be a list"):
        x_posts_db.save_x_posts("u1", invalid_posts)  # type: ignore[arg-type]


def test_save_x_posts_empty_list_returns_zero():
    fake_db = MagicMock()
    with patch.object(x_posts_db, "db", fake_db):
        assert x_posts_db.save_x_posts("u1", []) == 0
    fake_db.collection.assert_not_called()


def test_save_x_posts_skips_invalid_items_and_deduplicates():
    fake_db = MagicMock()
    batch = MagicMock()
    fake_db.batch.return_value = batch

    # Simulate post '101' already exists in Firestore, '102' is new
    snap_existing = _make_mock_snapshot("101", exists=True)
    snap_new = _make_mock_snapshot("102", exists=False)
    fake_db.get_all.return_value = [snap_existing, snap_new]

    posts = [
        None,  # non-dict
        "string-item",  # non-dict
        {"text": "missing id"},  # missing id
        {"id": "   ", "text": "whitespace id"},  # whitespace id
        {"id": "101", "text": "existing tweet"},  # existing
        {"id": 102, "text": "new tweet"},  # new (int id coerced)
    ]

    with patch.object(x_posts_db, "db", fake_db):
        new_count = x_posts_db.save_x_posts("  user-abc  ", posts)

    assert new_count == 1
    # Check that batch.set was called for both valid posts (101 updated, 102 created as new)
    assert batch.set.call_count == 2
    batch.commit.assert_called_once()


# ---------------------------------------------------------------------------
# get_pending_memory_extraction_posts
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("invalid_uid", [None, "", "   ", 123])
def test_get_pending_memory_extraction_posts_invalid_uid_returns_empty(invalid_uid):
    fake_db = MagicMock()
    with patch.object(x_posts_db, "db", fake_db):
        assert x_posts_db.get_pending_memory_extraction_posts(invalid_uid) == []  # type: ignore[arg-type]
    fake_db.collection.assert_not_called()


def test_get_pending_memory_extraction_posts_filters_completed_and_sorts():
    fake_db = MagicMock()
    snap_pending = _make_mock_snapshot("p1", exists=True, data={"text": "t1", "created_at": "2026-09-01T10:00:00Z"})
    snap_completed = _make_mock_snapshot(
        "p2", exists=True, data={"text": "t2", "memory_extraction_status": "completed"}
    )
    fake_db.collection.return_value.document.return_value.collection.return_value.stream.return_value = [
        snap_pending,
        snap_completed,
    ]

    with patch.object(x_posts_db, "db", fake_db):
        res = x_posts_db.get_pending_memory_extraction_posts("u1", limit=10)

    assert len(res) == 1
    assert res[0]["id"] == "p1"


# ---------------------------------------------------------------------------
# mark_memory_extraction_completed
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("invalid_uid", [None, "", "   ", 123])
def test_mark_memory_extraction_completed_invalid_uid_returns_safely(invalid_uid):
    fake_db = MagicMock()
    with patch.object(x_posts_db, "db", fake_db):
        x_posts_db.mark_memory_extraction_completed(invalid_uid, ["101"])  # type: ignore[arg-type]
    fake_db.collection.assert_not_called()


@pytest.mark.parametrize("invalid_post_ids", [None, "not-a-list", 123, []])
def test_mark_memory_extraction_completed_invalid_post_ids_returns_safely(invalid_post_ids):
    fake_db = MagicMock()
    with patch.object(x_posts_db, "db", fake_db):
        x_posts_db.mark_memory_extraction_completed("u1", invalid_post_ids)  # type: ignore[arg-type]
    fake_db.collection.assert_not_called()


def test_mark_memory_extraction_completed_commits_batch():
    fake_db = MagicMock()
    batch = MagicMock()
    fake_db.batch.return_value = batch

    with patch.object(x_posts_db, "db", fake_db):
        x_posts_db.mark_memory_extraction_completed("u1", ["  101  ", "", "   ", "102"])

    assert batch.set.call_count == 2
    batch.commit.assert_called_once()


# ---------------------------------------------------------------------------
# get_x_posts
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("invalid_uid", [None, "", "   ", 123])
def test_get_x_posts_invalid_uid_returns_empty(invalid_uid):
    fake_db = MagicMock()
    with patch.object(x_posts_db, "db", fake_db):
        assert x_posts_db.get_x_posts(invalid_uid) == []  # type: ignore[arg-type]
    fake_db.collection.assert_not_called()


# ---------------------------------------------------------------------------
# get_x_posts_by_ids
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("invalid_uid", [None, "", "   ", 123])
def test_get_x_posts_by_ids_invalid_uid_returns_empty(invalid_uid):
    fake_db = MagicMock()
    with patch.object(x_posts_db, "db", fake_db):
        assert x_posts_db.get_x_posts_by_ids(invalid_uid, ["101"]) == []  # type: ignore[arg-type]
    fake_db.collection.assert_not_called()


@pytest.mark.parametrize("invalid_ids", [None, "not-a-list", 123, []])
def test_get_x_posts_by_ids_invalid_ids_returns_empty(invalid_ids):
    fake_db = MagicMock()
    with patch.object(x_posts_db, "db", fake_db):
        assert x_posts_db.get_x_posts_by_ids("u1", invalid_ids) == []  # type: ignore[arg-type]
    fake_db.collection.assert_not_called()


# ---------------------------------------------------------------------------
# count_x_posts & get_newest_tweet_id
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("invalid_uid", [None, "", "   ", 123])
def test_count_x_posts_invalid_uid_returns_zero(invalid_uid):
    fake_db = MagicMock()
    with patch.object(x_posts_db, "db", fake_db):
        assert x_posts_db.count_x_posts(invalid_uid) == 0  # type: ignore[arg-type]
    fake_db.collection.assert_not_called()


@pytest.mark.parametrize("invalid_uid", [None, "", "   ", 123])
def test_get_newest_tweet_id_invalid_uid_returns_none(invalid_uid):
    fake_db = MagicMock()
    with patch.object(x_posts_db, "db", fake_db):
        assert x_posts_db.get_newest_tweet_id(invalid_uid) is None  # type: ignore[arg-type]
    fake_db.collection.assert_not_called()


# ---------------------------------------------------------------------------
# Batch chunking (>500 operations) tests
# ---------------------------------------------------------------------------


def test_save_x_posts_splits_batches_at_500_ops():
    fake_db = MagicMock()
    batch_mock = MagicMock()
    fake_db.batch.return_value = batch_mock

    # 501 unique posts to force chunk split: 500 in first batch, 1 in second batch
    posts = [{"id": f"tweet_{i}", "text": f"Tweet content {i}"} for i in range(501)]

    with patch.object(x_posts_db, "db", fake_db):
        written = x_posts_db.save_x_posts("u1", posts)

    assert written == 501
    assert fake_db.batch.call_count == 2
    assert batch_mock.commit.call_count == 2
    assert batch_mock.set.call_count == 501


def test_mark_memory_extraction_completed_splits_batches_at_500_ops():
    fake_db = MagicMock()
    batch_mock = MagicMock()
    fake_db.batch.return_value = batch_mock

    post_ids = [f"post_{i}" for i in range(501)]

    with patch.object(x_posts_db, "db", fake_db):
        x_posts_db.mark_memory_extraction_completed("u1", post_ids)

    assert fake_db.batch.call_count == 2
    assert batch_mock.commit.call_count == 2
    assert batch_mock.set.call_count == 501
