import pytest
from backend.database.chat import ChatFileManager, BATCH_LIMIT
from unittest.mock import MagicMock

@pytest.fixture
def mock_db():
    db = MagicMock()
    db.batch.return_value = MagicMock()
    return db

def test_add_multi_files_chunking(mock_db):
    manager = ChatFileManager(mock_db)
    file_ids = [f"file_{i}" for i in range(1201)]

    manager.add_multi_files(file_ids)

    # Verify 3 batches: 500, 500, 201
    assert mock_db.batch.call_count == 3
    for i, call in enumerate(mock_db.batch.call_args_list):
        batch = call[0][0]
        chunk_size = len(call[0][1]['file_ids'])
        assert chunk_size == 500 if i < 2 else 201

def test_delete_multi_files_chunking(mock_db):
    manager = ChatFileManager(mock_db)
    file_ids = [f"file_{i}" for i in range(1201)]

    manager.delete_multi_files(file_ids)

    # Verify 3 batches: 500, 500, 201
    assert mock_db.batch.call_count == 3
    for i, call in enumerate(mock_db.batch.call_args_list):
        batch = call[0][0]
        chunk_size = len(call[0][1]['file_ids'])
        assert chunk_size == 500 if i < 2 else 201

def test_empty_file_list(mock_db):
    manager = ChatFileManager(mock_db)
    manager.add_multi_files([])
    manager.delete_multi_files([])

    # No batches should be created
    assert mock_db.batch.call_count == 0

def test_exact_batch_limit(mock_db):
    manager = ChatFileManager(mock_db)
    file_ids = [f"file_{i}" for i in range(BATCH_LIMIT)]

    manager.add_multi_files(file_ids)

    # Exactly one batch
    assert mock_db.batch.call_count == 1