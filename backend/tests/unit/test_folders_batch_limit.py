"""Unit tests for Firestore write batch limit handling in folders.py.

Firestore imposes a strict limit of 500 write operations per batch commit.
When reordering folders with more than 500 items, unchunked batches crash
with InvalidArgument (400 The write batch contains too many operations).
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

from google.api_core.exceptions import InvalidArgument

import database.folders as folders_db


class MockWriteBatch:
    """Mock Firestore WriteBatch enforcing the 500-operation limit."""

    def __init__(self, commit_callback: Any = None) -> None:
        self.operations: list[tuple[str, Any, Any]] = []
        self.commit_callback = commit_callback

    def update(self, ref: Any, data: dict[str, Any]) -> None:
        self.operations.append(("update", ref, data))

    def commit(self) -> None:
        if len(self.operations) > 500:
            raise InvalidArgument(
                "400 The write batch contains too many operations. " "The maximum number of operations allowed is 500."
            )
        if self.commit_callback:
            self.commit_callback(len(self.operations))


class MockFirestoreClient:
    """Mock Firestore Client that tracks batches and committed chunk sizes."""

    def __init__(self) -> None:
        self.batches: list[MockWriteBatch] = []
        self.committed_batch_sizes: list[int] = []

    def batch(self) -> MockWriteBatch:
        b = MockWriteBatch(commit_callback=lambda count: self.committed_batch_sizes.append(count))
        self.batches.append(b)
        return b

    def collection(self, name: str) -> MagicMock:
        col = MagicMock()
        col.document.side_effect = lambda doc_id: self._doc(doc_id)
        return col

    def _doc(self, doc_id: str) -> MagicMock:
        doc = MagicMock()
        doc.id = doc_id
        doc.collection.side_effect = lambda name: self.collection(f"{doc_id}/{name}")
        return doc


def test_reorder_folders_exceeding_batch_limit_chunks_successfully(
    monkeypatch: Any,
) -> None:
    """Reordering more than 500 folders must chunk writes into <= 450 per commit."""
    mock_db = MockFirestoreClient()
    monkeypatch.setattr(folders_db, "db", mock_db)

    folder_ids = [f"folder_{i}" for i in range(520)]
    result = folders_db.reorder_folders("test_uid", folder_ids)

    assert result is True
    # 520 items chunked at <= 450 operations -> 450 then 70
    assert mock_db.committed_batch_sizes == [450, 70]
    assert all(size <= 450 for size in mock_db.committed_batch_sizes)


def test_reorder_folders_accepts_firestore_client_kwarg() -> None:
    """reorder_folders must accept an optional firestore_client keyword argument."""
    mock_client = MockFirestoreClient()
    folder_ids = [f"folder_{i}" for i in range(520)]

    result = folders_db.reorder_folders("test_uid", folder_ids, firestore_client=mock_client)

    assert result is True
    assert mock_client.committed_batch_sizes == [450, 70]


def test_reorder_folders_under_limit_single_commit(monkeypatch: Any) -> None:
    """Reordering fewer than 450 folders commits all in a single batch."""
    mock_db = MockFirestoreClient()
    monkeypatch.setattr(folders_db, "db", mock_db)

    folder_ids = [f"folder_{i}" for i in range(25)]
    result = folders_db.reorder_folders("test_uid", folder_ids)

    assert result is True
    assert mock_db.committed_batch_sizes == [25]


def test_reorder_folders_empty_list(monkeypatch: Any) -> None:
    """Reordering an empty list of folders succeeds without committing any batch."""
    mock_db = MockFirestoreClient()
    monkeypatch.setattr(folders_db, "db", mock_db)

    result = folders_db.reorder_folders("test_uid", [])

    assert result is True
    assert mock_db.committed_batch_sizes == []


def test_reorder_folders_exact_boundary_chunks(monkeypatch: Any) -> None:
    """Reordering exactly 900 folders creates two 450-item commits with no trailing empty commit."""
    mock_db = MockFirestoreClient()
    monkeypatch.setattr(folders_db, "db", mock_db)

    folder_ids = [f"folder_{i}" for i in range(900)]
    result = folders_db.reorder_folders("test_uid", folder_ids)

    assert result is True
    assert mock_db.committed_batch_sizes == [450, 450]
