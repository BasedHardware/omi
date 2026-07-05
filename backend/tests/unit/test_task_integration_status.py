"""Unit tests for GET /v1/task-integrations/{app_key} (fetch one integration's status).

routers.task_integrations imports cleanly (no heavy deps), so the endpoint is tested
directly with patch.object on the users_db seam (no sys.modules mutation).
"""

import os

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)
os.environ.setdefault("OPENAI_API_KEY", "test-openai-key-not-real")

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from fastapi import HTTPException

import database.users as users_db
from routers import task_integrations as ti_router


def test_404_when_absent():
    with patch.object(users_db, "get_task_integration", return_value=None):
        with pytest.raises(HTTPException) as exc:
            ti_router.get_task_integration_status(app_key="todoist", uid="u1")
    assert exc.value.status_code == 404


def test_status_maps_and_redacts_secrets():
    integration = {
        "connected": True,
        "access_token": "SECRET",
        "refresh_token": "SECRET2",
        "workspace_name": "Acme",
        "list_name": "Inbox",
    }
    with patch.object(users_db, "get_task_integration", return_value=integration), patch.object(
        users_db, "get_default_task_integration", return_value="todoist"
    ):
        resp = ti_router.get_task_integration_status(app_key="todoist", uid="u1")
    assert resp.app_key == "todoist"
    assert resp.connected is True
    assert resp.is_default is True
    assert resp.workspace_name == "Acme"
    assert resp.list_name == "Inbox"
    # The secret fields are not even on the response model, so they cannot leak.
    dumped = str(resp.model_dump())
    assert "SECRET" not in dumped
    assert "access_token" not in dumped
    assert "refresh_token" not in dumped


def test_expired_true_for_past_token():
    past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    with patch.object(
        users_db, "get_task_integration", return_value={"connected": True, "expires_at": past}
    ), patch.object(users_db, "get_default_task_integration", return_value=None):
        resp = ti_router.get_task_integration_status(app_key="asana", uid="u1")
    assert resp.expired is True
    assert resp.is_default is False


def test_expired_false_for_future_token():
    future = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    with patch.object(
        users_db, "get_task_integration", return_value={"connected": True, "expires_at": future}
    ), patch.object(users_db, "get_default_task_integration", return_value=None):
        resp = ti_router.get_task_integration_status(app_key="asana", uid="u1")
    assert resp.expired is False


def test_malformed_expires_at_does_not_crash():
    with patch.object(
        users_db, "get_task_integration", return_value={"connected": True, "expires_at": "not-a-date"}
    ), patch.object(users_db, "get_default_task_integration", return_value=None):
        resp = ti_router.get_task_integration_status(app_key="asana", uid="u1")
    assert resp.expired is False
    assert resp.expires_at == "not-a-date"
