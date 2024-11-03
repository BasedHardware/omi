import pytest
from database.tasks import TaskDB

class TestTaskDB:
    @pytest.fixture
    def task_db(self, db_client):
        return TaskDB(db_client)

    async def test_create_task(self, task_db):
        task_data = {
            "task_id": "test_task_1",
            "status": "pending",
            "type": "test_type"
        }
        result = await task_db.create_task(task_data)
        assert result["task_id"] == task_data["task_id"]
        assert result["status"] == task_data["status"]

    async def test_get_task(self, task_db):
        task_id = "test_task_1"
        task = await task_db.get_task(task_id)
        assert task is not None
        assert task["task_id"] == task_id

    async def test_update_task_status(self, task_db):
        task_id = "test_task_1"
        new_status = "completed"
        updated = await task_db.update_task_status(task_id, new_status)
        assert updated["status"] == new_status