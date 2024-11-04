import pytest
from database.processing_memories import (
    create_processing_memory,
    get_processing_memory,
    update_processing_memory,
    delete_processing_memory,
    get_processing_memories_by_state
)
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone

@pytest.fixture
def mock_firestore():
    """Mock firestore with proper collection group queries"""
    with patch('database._client._db', None):  # Reset singleton
        with patch('database._client.firestore.Client') as mock_client:
            # Setup collection group query mocking
            mock_doc = MagicMock()
            mock_doc.to_dict.return_value = {
                "state": "PROCESSING",
                "user_id": "user123"
            }
            mock_doc.reference = MagicMock()
            
            # Setup query chain
            mock_query = MagicMock()
            mock_query.where.return_value = mock_query
            mock_query.limit.return_value = mock_query
            mock_query.stream.return_value = [mock_doc]
            
            # Setup client instance
            mock_client_instance = mock_client.return_value
            
            # Setup collection group
            mock_client_instance.collection_group.return_value = mock_query
            
            # Setup regular collection mocking
            mock_doc_ref = MagicMock()
            mock_collection = MagicMock()
            mock_collection.document.return_value = mock_doc_ref
            mock_client_instance.collection.return_value = mock_collection
            
            # Ensure the mock is returned by get_firestore()
            mock_client.return_value = mock_client_instance
            
            yield mock_client_instance

class TestProcessingMemoriesCRUD:
    def test_create_processing_memory(self, mock_firestore):
        memory_data = {
            "id": "memory123",  # Provide ID to avoid UUID generation
            "user_id": "user123",
            "state": "PENDING",
            "created_at": datetime.now(timezone.utc),
            "audio_url": "gs://bucket/audio.wav"
        }
        
        # Get the document reference that will be used
        doc_ref = mock_firestore.collection('users').document('user123').collection('processing_memories').document('memory123')
        
        result = create_processing_memory(memory_data)
        assert result == "memory123"
        doc_ref.set.assert_called_once_with(memory_data)

    def test_get_processing_memory(self, mock_firestore):
        mock_doc = mock_firestore.collection_group().where().limit().stream()[0]
        
        memory = get_processing_memory("memory123")
        assert memory == {
            "state": "PROCESSING",
            "user_id": "user123"
        }

    def test_update_processing_memory_state(self, mock_firestore):
        mock_doc = mock_firestore.collection_group().where().limit().stream()[0]
        update_processing_memory("memory123", {"state": "COMPLETED"})
        mock_doc.reference.update.assert_called_once_with({"state": "COMPLETED"})

class TestProcessingMemoriesQueries:
    def test_get_memories_by_state(self, mock_firestore):
        mock_docs = [
            MagicMock(to_dict=lambda: {"id": "1", "state": "PENDING"}),
            MagicMock(to_dict=lambda: {"id": "2", "state": "PENDING"})
        ]
        mock_query = mock_firestore.collection().document().collection()
        mock_query.where.return_value.stream.return_value = mock_docs
        
        memories = get_processing_memories_by_state("user123", "PENDING")
        assert len(memories) == 2
        assert all(m["state"] == "PENDING" for m in memories)