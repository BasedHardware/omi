import os
from unittest.mock import MagicMock, patch

os.environ.setdefault("ENCRYPTION_SECRET", "0123456789abcdef0123456789abcdef")

from database import chat


class RecordingBatch:
    """Mock Firestore batch tracking operation count and commit calls."""

    def __init__(self, commit_log: list):
        self.count = 0
        self.commit_log = commit_log

    def set(self, ref, data):
        self.count += 1

    def delete(self, ref):
        self.count += 1

    def commit(self):
        self.commit_log.append(self.count)


def setup_mock_db(commit_log: list) -> MagicMock:
    mock_db = MagicMock()
    mock_db.batch.side_effect = lambda: RecordingBatch(commit_log)
    return mock_db


def test_add_multi_files_1200_chunks():
    """Assert add_multi_files with 1200 files commits in chunks [499, 499, 202] (exactly 3 commits)."""
    commit_log = []
    mock_db = setup_mock_db(commit_log)
    files_1200 = [{"id": f"file_{i}", "name": f"test_{i}.png"} for i in range(1200)]

    with patch.object(chat, "db", mock_db):
        chat.add_multi_files("user_123", files_1200)

    assert commit_log == [499, 499, 202]
    assert len(commit_log) == 3


def test_add_multi_files_empty():
    """Assert empty files_data=[] performs 0 commits."""
    commit_log = []
    mock_db = setup_mock_db(commit_log)

    with patch.object(chat, "db", mock_db):
        chat.add_multi_files("user_123", [])

    assert commit_log == []
    assert len(commit_log) == 0


def test_add_multi_files_exact_multiples():
    """Assert exact multiples of 499 commit without empty trailing commits."""
    commit_log = []
    mock_db = setup_mock_db(commit_log)

    files_499 = [{"id": f"file_{i}", "name": f"test_{i}.png"} for i in range(499)]
    with patch.object(chat, "db", mock_db):
        chat.add_multi_files("user_123", files_499)

    assert commit_log == [499]
    assert len(commit_log) == 1

    commit_log.clear()
    files_998 = [{"id": f"file_{i}", "name": f"test_{i}.png"} for i in range(998)]
    with patch.object(chat, "db", mock_db):
        chat.add_multi_files("user_123", files_998)

    assert commit_log == [499, 499]
    assert len(commit_log) == 2


def test_add_multi_files_under_chunk_size():
    """Assert under 499 files commits once with exact item count."""
    commit_log = []
    mock_db = setup_mock_db(commit_log)
    files_50 = [{"id": f"file_{i}", "name": f"test_{i}.png"} for i in range(50)]

    with patch.object(chat, "db", mock_db):
        chat.add_multi_files("user_123", files_50)

    assert commit_log == [50]
    assert len(commit_log) == 1


def test_delete_multi_files_1200_chunks():
    """Assert delete_multi_files with 1200 files commits in chunks [499, 499, 202] (exactly 3 commits)."""
    commit_log = []
    mock_db = setup_mock_db(commit_log)
    files_1200 = [{"id": f"file_{i}"} for i in range(1200)]

    with patch.object(chat, "db", mock_db):
        chat.delete_multi_files("user_123", files_1200)

    assert commit_log == [499, 499, 202]
    assert len(commit_log) == 3


def test_delete_multi_files_empty():
    """Assert empty delete performs 0 commits."""
    commit_log = []
    mock_db = setup_mock_db(commit_log)

    with patch.object(chat, "db", mock_db):
        chat.delete_multi_files("user_123", [])

    assert commit_log == []
    assert len(commit_log) == 0


def test_delete_multi_files_exact_multiples():
    """Assert exact multiples of 499 delete without empty trailing commits."""
    commit_log = []
    mock_db = setup_mock_db(commit_log)

    files_499 = [{"id": f"file_{i}"} for i in range(499)]
    with patch.object(chat, "db", mock_db):
        chat.delete_multi_files("user_123", files_499)

    assert commit_log == [499]
    assert len(commit_log) == 1

    commit_log.clear()
    files_998 = [{"id": f"file_{i}"} for i in range(998)]
    with patch.object(chat, "db", mock_db):
        chat.delete_multi_files("user_123", files_998)

    assert commit_log == [499, 499]
    assert len(commit_log) == 2


def test_delete_multi_files_under_chunk_size():
    """Assert under 499 files delete commits once with exact item count."""
    commit_log = []
    mock_db = setup_mock_db(commit_log)
    files_50 = [{"id": f"file_{i}"} for i in range(50)]

    with patch.object(chat, "db", mock_db):
        chat.delete_multi_files("user_123", files_50)

    assert commit_log == [50]
    assert len(commit_log) == 1
