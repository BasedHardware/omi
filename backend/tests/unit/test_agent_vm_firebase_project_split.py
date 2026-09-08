from __future__ import annotations

import os
from unittest.mock import MagicMock

import firebase_admin

from database import _client as firestore_client
import desktop_backend


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
    monkeypatch.setattr(firestore_client, "_customer_firestore_client", None)
    monkeypatch.setattr(firestore_client.firestore, "Client", client)

    assert firestore_client.get_firestore_client() is client.return_value

    client.assert_called_once_with()


def test_customer_firestore_client_uses_auth_credentials_path_without_overriding_adc(monkeypatch, tmp_path) -> None:
    credentials_path = tmp_path / "service-account.json"
    credentials_path.write_text(
        '{"type":"service_account","project_id":"based-hardware","client_email":"nik-164@based-hardware.iam.gserviceaccount.com"}',
        encoding="utf-8",
    )
    compute_client = MagicMock(name="compute-firestore")
    customer_client = MagicMock(name="customer-firestore")
    fake_credentials = MagicMock(name="customer-sa")

    def fake_client(**kwargs):
        if kwargs.get("project") == "based-hardware":
            return customer_client
        return compute_client

    monkeypatch.delenv("SERVICE_ACCOUNT_JSON", raising=False)
    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
    monkeypatch.delenv("FIRESTORE_EMULATOR_HOST", raising=False)
    monkeypatch.setenv("FIREBASE_AUTH_CREDENTIALS_PATH", str(credentials_path))
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "based-hardware-dev")
    monkeypatch.setattr(firestore_client, "_firestore_client", None)
    monkeypatch.setattr(firestore_client, "_customer_firestore_client", None)
    monkeypatch.setattr(firestore_client.firestore, "Client", fake_client)
    monkeypatch.setattr(
        "google.oauth2.service_account.Credentials.from_service_account_info",
        lambda _info: fake_credentials,
    )

    assert firestore_client.get_firestore_client() is compute_client
    assert firestore_client.get_customer_firestore_client() is customer_client
    assert os.environ.get("GOOGLE_APPLICATION_CREDENTIALS") is None
    assert os.environ.get("SERVICE_ACCOUNT_JSON") is None


def test_firestore_client_pins_service_account_json_over_host_project_adc(monkeypatch) -> None:
    """Listen must not let GKE compute project / pack WI win customer Firestore."""
    client = MagicMock()
    credentials = MagicMock(name="customer-data-sa")
    monkeypatch.setenv("SERVICE_ACCOUNT_JSON", '{"project_id":"based-hardware"}')
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "based-hardware-dev")
    monkeypatch.delenv("FIRESTORE_EMULATOR_HOST", raising=False)
    monkeypatch.setattr(firestore_client, "_firestore_client", None)
    monkeypatch.setattr(firestore_client, "_customer_firestore_client", None)
    monkeypatch.setattr(firestore_client.firestore, "Client", client)
    monkeypatch.setattr(
        firestore_client,
        "customer_data_service_account",
        lambda: (credentials, "based-hardware"),
    )

    assert firestore_client.get_firestore_client() is client.return_value

    client.assert_called_once_with(credentials=credentials, project="based-hardware")


def test_valid_subscription_without_provision_does_not_write_free() -> None:
    from database import users as users_db
    from models.users import PlanType

    user_ref = MagicMock()
    snapshot = MagicMock()
    snapshot.exists = False
    user_ref.get.return_value = snapshot
    client = MagicMock()
    client.collection.return_value.document.return_value = user_ref

    subscription = users_db.get_user_valid_subscription("uid", firestore_client=client, provision=False)

    assert subscription is not None
    assert subscription.plan == PlanType.basic
    user_ref.set.assert_not_called()


def test_desktop_chat_quota_reads_customer_firestore_without_provisioning() -> None:
    import inspect

    from utils.subscription import enforce_desktop_chat_quota, is_desktop_trial_paywalled

    quota_source = inspect.getsource(enforce_desktop_chat_quota)
    paywall_source = inspect.getsource(is_desktop_trial_paywalled)
    assert "get_customer_firestore_client()" in quota_source
    assert "provision=False" in quota_source
    assert "get_customer_firestore_client()" in paywall_source
    assert "provision=False" in paywall_source


def test_screen_vector_entitlement_reads_customer_firestore_without_provisioning() -> None:
    import inspect

    from utils.subscription import grants_cloud_screen_vectors

    source = inspect.getsource(grants_cloud_screen_vectors)
    assert "get_customer_firestore_client()" in source
    assert "provision=False" in source


def test_screen_vector_entitlement_does_not_write_when_customer_subscription_doc_is_missing(monkeypatch) -> None:
    from database import users as users_db
    from models.users import PlanType
    from utils.subscription import grants_cloud_screen_vectors
    import utils.subscription as subscription

    uid = "uid-missing-customer-subscription"
    subscription.clear_cloud_screen_vector_entitlement_cache(uid)

    user_ref = MagicMock()
    snapshot = MagicMock()
    snapshot.exists = False
    user_ref.get.return_value = snapshot
    customer_client = MagicMock()
    customer_client.collection.return_value.document.return_value = user_ref

    monkeypatch.setattr(subscription, "get_customer_firestore_client", lambda: customer_client)

    entitled = grants_cloud_screen_vectors(uid)
    stored = users_db.get_user_valid_subscription(uid, firestore_client=customer_client, provision=False)

    assert entitled is False
    assert stored is not None
    assert stored.plan == PlanType.basic
    user_ref.set.assert_not_called()
