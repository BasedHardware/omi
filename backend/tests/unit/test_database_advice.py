"""Unit tests for backend/database/advice.py input validation and batch chunking."""

from unittest.mock import MagicMock
import pytest

import database.advice as advice_db


def test_user_col_validates_uid():
    with pytest.raises(ValueError, match="uid must be a non-empty string"):
        advice_db._user_col("", "advice")

    with pytest.raises(ValueError, match="uid must be a non-empty string"):
        advice_db._user_col("   ", "advice")


def test_create_advice_validates_content(monkeypatch):
    with pytest.raises(ValueError, match="content must be a non-empty string"):
        advice_db.create_advice("user-1", "")

    with pytest.raises(ValueError, match="content must be a non-empty string"):
        advice_db.create_advice("user-1", "   ")


def test_create_advice_clamps_confidence(monkeypatch):
    mock_set = MagicMock()
    mock_doc = MagicMock()
    mock_doc.set = mock_set
    mock_col = MagicMock()
    mock_col.document.return_value = mock_doc

    monkeypatch.setattr(advice_db, "_user_col", lambda uid, col: mock_col)

    doc = advice_db.create_advice("user-1", "test advice", confidence=1.5)
    assert doc["confidence"] == 1.0

    doc2 = advice_db.create_advice("user-1", "test advice", confidence=-0.5)
    assert doc2["confidence"] == 0.0

    doc3 = advice_db.create_advice("user-1", "test advice", confidence="invalid")
    assert doc3["confidence"] == 0.5


def test_update_and_delete_validate_advice_id():
    with pytest.raises(ValueError, match="advice_id must be a non-empty string"):
        advice_db.update_advice("user-1", "   ", is_read=True)

    with pytest.raises(ValueError, match="advice_id must be a non-empty string"):
        advice_db.delete_advice("user-1", "")


def test_mark_all_advice_read_batch_chunking(monkeypatch):
    """Verify mark_all_advice_read handles >500 items by chunking batch commits."""
    mock_col = MagicMock()
    mock_batch = MagicMock()
    mock_db = MagicMock()

    # Create 550 mock documents
    mock_docs = []
    for i in range(550):
        d = MagicMock()
        d.id = f"adv-{i}"
        mock_docs.append(d)

    mock_query = MagicMock()
    mock_query.stream.return_value = mock_docs
    mock_col.where.return_value = mock_query

    batches_created = []

    def fake_batch():
        b = MagicMock()
        batches_created.append(b)
        return b

    monkeypatch.setattr(advice_db, "_user_col", lambda uid, col: mock_col)
    monkeypatch.setattr(advice_db, "db", mock_db)
    mock_db.batch = fake_batch

    total = advice_db.mark_all_advice_read("user-1")

    assert total == 550
    # Expected 2 batch commits (500 + 50)
    assert len(batches_created) == 2
    assert batches_created[0].commit.called
    assert batches_created[1].commit.called
