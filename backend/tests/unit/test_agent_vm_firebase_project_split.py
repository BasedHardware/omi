from __future__ import annotations

import os
from unittest.mock import MagicMock

import firebase_admin
import pytest

from database import _client as firestore_client
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


def test_desktop_backend_uses_an_explicit_auth_credential_without_overriding_adc(monkeypatch) -> None:
    initialize = MagicMock()
    certificate = MagicMock(return_value="production-auth-credential")
    monkeypatch.setattr(firebase_admin, "initialize_app", initialize)
    monkeypatch.setattr(firebase_admin.credentials, "Certificate", certificate)
    monkeypatch.delenv("FIREBASE_AUTH_EMULATOR_HOST", raising=False)
    monkeypatch.delenv("SERVICE_ACCOUNT_JSON", raising=False)
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", "/var/run/dev-adc.json")
    monkeypatch.setenv("FIREBASE_AUTH_PROJECT_ID", "based-hardware")
    monkeypatch.setenv("FIREBASE_AUTH_CREDENTIALS_PATH", "/secrets/firebase/service-account.json")
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "based-hardware-dev")

    desktop_backend._initialize_firebase_admin()

    certificate.assert_called_once_with("/secrets/firebase/service-account.json")
    initialize.assert_called_once_with("production-auth-credential", options={"projectId": "based-hardware"})
    assert os.environ["GOOGLE_APPLICATION_CREDENTIALS"] == "/var/run/dev-adc.json"


def test_desktop_backend_auth_emulator_clears_all_real_credential_selectors(monkeypatch) -> None:
    initialize = MagicMock()
    monkeypatch.setattr(firebase_admin, "initialize_app", initialize)
    monkeypatch.setenv("FIREBASE_AUTH_EMULATOR_HOST", "127.0.0.1:9099")
    monkeypatch.delenv("FIREBASE_AUTH_PROJECT_ID", raising=False)
    monkeypatch.delenv("FIREBASE_PROJECT_ID", raising=False)
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", "/var/run/dev-adc.json")
    monkeypatch.setenv("SERVICE_ACCOUNT_JSON", '{"type":"service_account"}')
    monkeypatch.setenv("FIREBASE_AUTH_CREDENTIALS_PATH", "/secrets/firebase/service-account.json")

    desktop_backend._initialize_firebase_admin()

    initialize.assert_called_once_with(options={"projectId": "demo-omi-local"})
    for credential_env in ("GOOGLE_APPLICATION_CREDENTIALS", "SERVICE_ACCOUNT_JSON", "FIREBASE_AUTH_CREDENTIALS_PATH"):
        assert credential_env not in os.environ


def test_firestore_client_uses_dev_adc_when_firebase_auth_path_is_separate(monkeypatch) -> None:
    client = MagicMock()
    monkeypatch.delenv("SERVICE_ACCOUNT_JSON", raising=False)
    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
    monkeypatch.setenv("FIREBASE_AUTH_CREDENTIALS_PATH", "/secrets/firebase/service-account.json")
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "based-hardware-dev")
    monkeypatch.setattr(firestore_client, "_firestore_client", None)
    monkeypatch.setattr(firestore_client.firestore, "Client", client)

    assert firestore_client.get_firestore_client() is client.return_value

    client.assert_called_once_with()


def test_firestore_client_pins_service_account_json_over_host_project_adc(monkeypatch) -> None:
    """Listen must not let GKE compute project / pack WI win customer Firestore."""
    client = MagicMock()
    credentials = MagicMock(name="customer-data-sa")
    monkeypatch.setenv("SERVICE_ACCOUNT_JSON", '{"project_id":"based-hardware"}')
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "based-hardware-dev")
    monkeypatch.delenv("FIRESTORE_EMULATOR_HOST", raising=False)
    monkeypatch.setattr(firestore_client, "_firestore_client", None)
    monkeypatch.setattr(firestore_client.firestore, "Client", client)
    monkeypatch.setattr(
        firestore_client,
        "customer_data_service_account",
        lambda: (credentials, "based-hardware"),
    )

    assert firestore_client.get_firestore_client() is client.return_value

    client.assert_called_once_with(credentials=credentials, project="based-hardware")


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
