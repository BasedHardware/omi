from unittest.mock import MagicMock
from google.cloud.firestore_v1 import FieldFilter
import pytest

from database.batch_pipeline_privacy_queries import (
    owner_documents,
    predecessor_documents,
    segment_artifacts,
    due_artifacts,
)


def test_owner_documents_success():
    client = MagicMock()
    mock_doc = MagicMock()
    query_mock = client.collection.return_value.where.return_value.limit.return_value
    query_mock.stream.return_value = [mock_doc]

    res = owner_documents(client, "test_ns", "users", "owner_123")

    client.collection.assert_called_once_with("test_ns_users")
    assert res == [mock_doc]


def test_owner_documents_sanitization_and_after():
    client = MagicMock()
    after_cursor = MagicMock()
    query_base = client.collection.return_value.where.return_value
    start_after_mock = query_base.start_after.return_value.limit.return_value
    start_after_mock.stream.return_value = []

    res = owner_documents(client, "  test_ns  ", "  tasks  ", "  owner_abc  ", after=after_cursor, limit=50)

    client.collection.assert_called_once_with("test_ns_tasks")
    query_base.start_after.assert_called_once_with(after_cursor)
    assert res == []


@pytest.mark.parametrize(
    "ns,tbl,k",
    [
        ("", "tasks", "owner_1"),
        ("  ", "tasks", "owner_1"),
        (None, "tasks", "owner_1"),
        ("ns", "", "owner_1"),
        ("ns", "  ", "owner_1"),
        ("ns", None, "owner_1"),
        ("ns", "tasks", ""),
        ("ns", "tasks", "  "),
        ("ns", "tasks", None),
    ],
)
def test_owner_documents_invalid_inputs_returns_empty(ns, tbl, k):
    client = MagicMock()
    assert owner_documents(client, ns, tbl, k) == []
    client.collection.assert_not_called()


def test_owner_documents_exception_boundary():
    client = MagicMock()
    client.collection.side_effect = RuntimeError("Firestore unavailable")
    assert owner_documents(client, "test_ns", "tasks", "owner_1") == []


def test_predecessor_documents_success():
    client = MagicMock()
    tx = MagicMock()
    mock_job = MagicMock()
    stream_mock = client.collection.return_value.where.return_value.where.return_value.limit.return_value.stream
    stream_mock.return_value = [mock_job]

    res = predecessor_documents(client, "batch", "seg_1", tx)

    client.collection.assert_called_once_with("batch_jobs")
    stream_mock.assert_called_once_with(transaction=tx)
    assert res == [mock_job]


def test_predecessor_documents_sanitization():
    client = MagicMock()
    tx = MagicMock()
    res = predecessor_documents(client, "  batch  ", "  seg_1  ", tx)
    client.collection.assert_called_once_with("batch_jobs")


@pytest.mark.parametrize(
    "ns,seg",
    [
        ("", "seg_1"),
        ("   ", "seg_1"),
        (None, "seg_1"),
        ("batch", ""),
        ("batch", "   "),
        ("batch", None),
    ],
)
def test_predecessor_documents_invalid_inputs_returns_empty(ns, seg):
    client = MagicMock()
    assert predecessor_documents(client, ns, seg, MagicMock()) == []
    client.collection.assert_not_called()


def test_predecessor_documents_exception_boundary():
    client = MagicMock()
    client.collection.side_effect = TimeoutError("Network timeout")
    assert predecessor_documents(client, "batch", "seg_1", MagicMock()) == []


def test_segment_artifacts_success():
    client = MagicMock()
    tx = MagicMock()
    mock_artifact = MagicMock()
    stream_mock = client.collection.return_value.where.return_value.limit.return_value.stream
    stream_mock.return_value = [mock_artifact]

    res = segment_artifacts(client, "batch", "seg_99", tx)

    client.collection.assert_called_once_with("batch_artifacts")
    stream_mock.assert_called_once_with(transaction=tx)
    assert res == [mock_artifact]


def test_segment_artifacts_sanitization():
    client = MagicMock()
    res = segment_artifacts(client, "  batch_ns  ", "  seg_strip  ", MagicMock())
    client.collection.assert_called_once_with("batch_ns_artifacts")


@pytest.mark.parametrize(
    "ns,seg",
    [
        ("", "seg_1"),
        (None, "seg_1"),
        ("batch", ""),
        ("batch", None),
    ],
)
def test_segment_artifacts_invalid_inputs_returns_empty(ns, seg):
    client = MagicMock()
    assert segment_artifacts(client, ns, seg, MagicMock()) == []
    client.collection.assert_not_called()


def test_segment_artifacts_exception_boundary():
    client = MagicMock()
    client.collection.side_effect = Exception("Firestore contention")
    assert segment_artifacts(client, "batch", "seg_1", MagicMock()) == []


def test_due_artifacts_success():
    client = MagicMock()
    mock_artifact = MagicMock()
    stream_mock = client.collection.return_value.where.return_value.limit.return_value.stream
    stream_mock.return_value = [mock_artifact]

    res = due_artifacts(client, "batch", "2026-10-16T12:00:00Z", limit=50)

    client.collection.assert_called_once_with("batch_artifacts")
    assert res == [mock_artifact]


def test_due_artifacts_clamping_and_sanitization():
    client = MagicMock()
    limit_mock = client.collection.return_value.where.return_value.limit

    due_artifacts(client, "  batch_strip  ", "2026-10-16T12:00:00Z", limit=500)
    client.collection.assert_called_once_with("batch_strip_artifacts")
    limit_mock.assert_called_with(100)  # Clamped to 100 max


@pytest.mark.parametrize(
    "ns,now",
    [
        ("", "2026-10-16"),
        ("   ", "2026-10-16"),
        (None, "2026-10-16"),
        ("batch", None),
    ],
)
def test_due_artifacts_invalid_inputs_returns_empty(ns, now):
    client = MagicMock()
    assert due_artifacts(client, ns, now) == []
    client.collection.assert_not_called()


def test_due_artifacts_exception_boundary():
    client = MagicMock()
    client.collection.side_effect = RuntimeError("Deadlock")
    assert due_artifacts(client, "batch", "2026-10-16") == []
