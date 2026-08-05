from __future__ import annotations

from unittest.mock import MagicMock

import firebase_admin
import pytest

import desktop_backend
import jobs.agent_vm_reconciler as reconciler
from routers import desktop_agent_vm


def test_desktop_backend_initializes_production_auth_separately_from_google_cloud_project(monkeypatch) -> None:
    initialize = MagicMock()
    monkeypatch.setattr(firebase_admin, "initialize_app", initialize)
    monkeypatch.delenv("FIREBASE_AUTH_EMULATOR_HOST", raising=False)
    monkeypatch.delenv("SERVICE_ACCOUNT_JSON", raising=False)
    monkeypatch.setenv("FIREBASE_AUTH_PROJECT_ID", "based-hardware")
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "based-hardware-dev")

    desktop_backend._initialize_firebase_admin()

    initialize.assert_called_once_with(options={"projectId": "based-hardware"})


def test_reconciler_initializes_production_auth_separately_from_google_cloud_project(monkeypatch) -> None:
    initialize = MagicMock()
    monkeypatch.setattr(firebase_admin, "get_app", MagicMock(side_effect=ValueError()))
    monkeypatch.setattr(firebase_admin, "initialize_app", initialize)
    monkeypatch.delenv("SERVICE_ACCOUNT_JSON", raising=False)
    monkeypatch.setenv("FIREBASE_AUTH_PROJECT_ID", "based-hardware")
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "based-hardware-dev")

    reconciler._init_firebase()

    initialize.assert_called_once_with(options={"projectId": "based-hardware"})


def test_agent_vm_control_requires_an_explicit_gce_project(monkeypatch) -> None:
    monkeypatch.delenv("GCE_PROJECT_ID", raising=False)
    monkeypatch.setenv("FIREBASE_PROJECT_ID", "based-hardware")

    with pytest.raises(RuntimeError, match="GCE_PROJECT_ID"):
        desktop_agent_vm._project()


@pytest.mark.asyncio
async def test_reconciler_requires_an_explicit_gce_project(monkeypatch) -> None:
    monkeypatch.setattr(reconciler, "_init_firebase", lambda: None)
    monkeypatch.setattr(reconciler, "load_active_release", lambda: (MagicMock(environment="development"), {}))
    monkeypatch.delenv("GCE_PROJECT_ID", raising=False)
    monkeypatch.setenv("FIREBASE_PROJECT_ID", "based-hardware")

    with pytest.raises(RuntimeError, match="GCE_PROJECT_ID"):
        await reconciler.run_reconciler(dry_run=True)
