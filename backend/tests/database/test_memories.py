import pytest
from database.memories import MemoriesDB
from models.memory import Memory, MemoryType

class TestMemoriesDB:
    @pytest.fixture
    def memories_db(self, db_client):
        return MemoriesDB(db_client)

    async def test_create_memory(self, memories_db):
        memory_data = {
            "memory_id": "test_memory_1",
            "user_id": "test_user_1",
            "type": "audio",
            "content": "Had a chat about weather",
            "timestamp": "2024-03-20T10:00:00Z"
        }
        result = await memories_db.create_memory(memory_data)
        assert result["memory_id"] == memory_data["memory_id"]
        assert result["content"] == memory_data["content"]

    async def test_get_memory(self, memories_db):
        memory_id = "test_memory_1"
        memory = await memories_db.get_memory(memory_id)
        assert memory is not None
        assert memory["memory_id"] == memory_id

    async def test_get_user_memories(self, memories_db):
        user_id = "test_user_1"
        memories = await memories_db.get_user_memories(user_id)
        assert len(memories) > 0
        assert memories[0]["user_id"] == user_id

    async def test_update_memory(self, memories_db):
        memory_id = "test_memory_1"
        updates = {
            "importance": 0.8,
            "processed": True
        }
        updated = await memories_db.update_memory(memory_id, updates)
        assert updated["importance"] == updates["importance"]
        assert updated["processed"] == updates["processed"]

    async def test_search_memories(self, memories_db):
        query = "weather"
        user_id = "test_user_1"
        results = await memories_db.search_memories(user_id, query)
        assert len(results) > 0
        assert query.lower() in results[0]["content"].lower() 