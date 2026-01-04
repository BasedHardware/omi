import pytest
import firebase_admin
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone, timedelta

# Patch firebase_admin.initialize_app to prevent re-initialization errors
if not firebase_admin._apps:
    try:
        firebase_admin.initialize_app()
    except Exception:
        pass

# Assuming your main app instance is in backend.main
from backend.main import app as fastapi_app

@pytest.fixture(name="client")
def client_fixture():
    """Returns a TestClient for FastAPI app"""
    return TestClient(fastapi_app)

@pytest.fixture(name="test_uid")
def test_uid_fixture():
    """Returns a dummy user ID"""
    return "test_user_id_123"

@pytest.fixture(name="test_app_id")
def test_app_id_fixture():
    """Returns a dummy app ID"""
    return "test_app_id_456"

@pytest.fixture(name="test_api_key")
def test_api_key_fixture():
    """Returns a dummy API key"""
    return "Bearer sk_test_api_key_789"

@pytest.fixture(name="mock_get_app_by_id_db")
def mock_get_app_by_id_db_fixture():
    """Mocks database.apps.get_app_by_id_db"""
    with patch("database.apps.get_app_by_id_db") as mock:
        yield mock

@pytest.fixture(name="mock_get_enabled_apps")
def mock_get_enabled_apps_fixture():
    """Mocks database.redis_db.get_enabled_apps"""
    with patch("database.redis_db.get_enabled_apps") as mock:
        yield mock

@pytest.fixture(name="mock_app_can_read_tasks")
def mock_app_can_read_tasks_fixture():
    """Mocks utils.apps.app_can_read_tasks"""
    with patch("utils.apps.app_can_read_tasks") as mock:
        yield mock

@pytest.fixture(name="mock_get_action_items")
def mock_get_action_items_fixture():
    """Mocks database.action_items.get_action_items"""
    with patch("database.action_items.get_action_items") as mock:
        yield mock

@pytest.fixture(name="mock_verify_api_key")
def mock_verify_api_key_fixture():
    """Mocks utils.apps.verify_api_key"""
    with patch("utils.apps.verify_api_key") as mock:
        yield mock

# --- Test Cases ---

class TestGetTasksIntegration:

    def test_get_tasks_success(
        self,
        client: TestClient,
        test_uid: str,
        test_app_id: str,
        test_api_key: str,
        mock_get_app_by_id_db: MagicMock,
        mock_get_enabled_apps: MagicMock,
        mock_app_can_read_tasks: MagicMock,
        mock_get_action_items: MagicMock,
        mock_verify_api_key: MagicMock,
    ):
        """Test successful retrieval of tasks."""
        mock_verify_api_key.return_value = True
        mock_get_app_by_id_db.return_value = {"id": test_app_id, "external_integration": {"actions": [{"action": "read_tasks"}]}}
        mock_get_enabled_apps.return_value = {test_app_id}
        mock_app_can_read_tasks.return_value = True
        
        mock_get_action_items.return_value = [
            {"id": "task1", "description": "Buy milk", "completed": False, "created_at": datetime.now(timezone.utc)},
            {"id": "task2", "description": "Call mom", "completed": True, "created_at": datetime.now(timezone.utc)},
        ]

        response = client.get(
            f"/v2/integrations/{test_app_id}/tasks",
            headers={"Authorization": test_api_key},
            params={"uid": test_uid}
        )

        assert response.status_code == 200
        assert len(response.json()["tasks"]) == 2
        assert response.json()["tasks"][0]["id"] == "task1"
        mock_get_action_items.assert_called_once_with(
            uid=test_uid,
            conversation_id=None,
            completed=None,
            start_date=None,
            end_date=None,
            due_start_date=None,
            due_end_date=None,
            limit=100,
            offset=0,
        )

    def test_get_tasks_invalid_api_key(self, client: TestClient, test_uid: str, test_app_id: str):
        """Test retrieval with invalid API key."""
        with patch("utils.apps.verify_api_key", return_value=False):
            response = client.get(
                f"/v2/integrations/{test_app_id}/tasks",
                headers={"Authorization": "Bearer invalid_key"},
                params={"uid": test_uid}
            )
        assert response.status_code == 403
        assert "Invalid API key" in response.json()["detail"]
