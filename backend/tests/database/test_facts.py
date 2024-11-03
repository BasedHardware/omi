import pytest
from database.facts import FactsDB
from models.facts import Fact

class TestFactsDB:
    @pytest.fixture
    def facts_db(self, db_client):
        return FactsDB(db_client)

    async def test_create_fact(self, facts_db):
        fact_data = {
            "fact_id": "test_fact_1",
            "user_id": "test_user_1",
            "content": "The sky is blue",
            "confidence": 0.95,
            "source": "observation"
        }
        result = await facts_db.create_fact(fact_data)
        assert result["fact_id"] == fact_data["fact_id"]
        assert result["content"] == fact_data["content"]

    async def test_get_fact(self, facts_db):
        fact_id = "test_fact_1"
        fact = await facts_db.get_fact(fact_id)
        assert fact is not None
        assert fact["fact_id"] == fact_id

    async def test_get_user_facts(self, facts_db):
        user_id = "test_user_1"
        facts = await facts_db.get_user_facts(user_id)
        assert len(facts) > 0
        assert facts[0]["user_id"] == user_id

    async def test_update_fact(self, facts_db):
        fact_id = "test_fact_1"
        updates = {
            "confidence": 0.98,
            "verified": True
        }
        updated = await facts_db.update_fact(fact_id, updates)
        assert updated["confidence"] == updates["confidence"]
        assert updated["verified"] == updates["verified"] 