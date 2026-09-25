"""Unit tests for goal creation error sanitisation."""

from fastapi import status
from fastapi.testclient import TestClient

# Import the FastAPI app that includes the router.
# The repository already defines a central ``app`` in ``backend/main.py``.
# If it does not exist, we create a minimal one for the purpose of testing.
try:
    from backend.main import app  # type: ignore
except Exception:  # pragma: no cover
    from fastapi import FastAPI
    from backend.routers.goals import router as goals_router

    app = FastAPI()
    app.include_router(goals_router)


client = TestClient(app)


def test_goal_conflict_is_sanitized():
    """A ``GoalConflictError`` must result in a 409 with a clean payload."""
    response = client.post("/goals", json={"conflict": True, "name": "test"})
    assert response.status_code == status.HTTP_409_CONFLICT
    json_body = response.json()
    # The response should contain a generic error key and the sanitized detail.
    assert json_body == {
        "error": "Goal conflict",
        "detail": "A goal with the same identifier already exists.",
    }


def test_goal_store_error_is_masked():
    """Unexpected store errors must be turned into a generic 500 response."""
    response = client.post("/goals", json={"store_error": True, "name": "test"})
    assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    json_body = response.json()
    # No internal exception message should be leaked.
    assert json_body == {"error": "Internal server error"}


def test_successful_goal_creation():
    """A normal request should succeed with a 201 payload."""
    payload = {"name": "my goal", "description": "do something"}
    response = client.post("/goals", json=payload)
    assert response.status_code == status.HTTP_201_CREATED
    json_body = response.json()
    assert json_body["status"] == "created"
    assert json_body["goal"] == payload
