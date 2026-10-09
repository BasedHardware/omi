"""Keyless runtime identity: the backend runs without ``SERVICE_ACCOUNT_JSON``.

The JSON key contributed two things: an identity and a ``project_id``. On an
attached Cloud Run service account / GKE Workload Identity the identity comes
from ADC and ``OMI_CUSTOMER_DATA_PROJECT`` supplies the project. These tests pin
the pieces that would otherwise break silently: Firestore following the compute
project, V4 signed URLs needing a local private key, and Firebase Admin taking
its project from ``GOOGLE_CLOUD_PROJECT``.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import google.auth.credentials as google_auth_credentials
import pytest

import database._client as client_module
from utils.env_loader import firebase_admin_options
from utils.other import local_storage


def _clear_credential_env(monkeypatch):
    for name in (
        "SERVICE_ACCOUNT_JSON",
        "GOOGLE_APPLICATION_CREDENTIALS",
        "FIREBASE_AUTH_CREDENTIALS_PATH",
        "FIRESTORE_EMULATOR_HOST",
        "FIRESTORE_DATABASE_ID",
        "OMI_JIT_QA_AUTH_ONLY",
        "OMI_FIRESTORE_DATA_PLANE_PROJECT",
        "OMI_CUSTOMER_DATA_PROJECT",
        "FIREBASE_AUTH_PROJECT_ID",
        "FIREBASE_SIGNER_SERVICE_ACCOUNT",
    ):
        monkeypatch.delenv(name, raising=False)


def test_firestore_client_follows_the_customer_pin_not_the_compute_project(monkeypatch):
    _clear_credential_env(monkeypatch)
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "based-hardware-dev")
    monkeypatch.setenv("OMI_CUSTOMER_DATA_PROJECT", "based-hardware")
    ctor = MagicMock(return_value=SimpleNamespace())
    monkeypatch.setattr(client_module.firestore, "Client", ctor)

    client_module._build_firestore_client()

    # No ``credentials`` kwarg: the runtime identity comes from ADC.
    ctor.assert_called_once_with(project="based-hardware")


def test_customer_and_data_plane_clients_share_the_pin(monkeypatch):
    _clear_credential_env(monkeypatch)
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "based-hardware-dev")
    monkeypatch.setenv("OMI_CUSTOMER_DATA_PROJECT", "based-hardware")
    monkeypatch.setenv("OMI_FIRESTORE_DATA_PLANE_PROJECT", "based-hardware")
    ctor = MagicMock(return_value=SimpleNamespace())
    monkeypatch.setattr(client_module.firestore, "Client", ctor)

    client_module._build_customer_firestore_client()
    client_module._build_data_plane_firestore_client()

    assert [call.kwargs for call in ctor.call_args_list] == [{"project": "based-hardware"}] * 2


def test_data_plane_refuses_a_pin_for_another_project(monkeypatch):
    _clear_credential_env(monkeypatch)
    monkeypatch.setenv("OMI_CUSTOMER_DATA_PROJECT", "based-hardware")
    monkeypatch.setenv("OMI_FIRESTORE_DATA_PLANE_PROJECT", "based-hardware-dev")
    monkeypatch.setattr(client_module.firestore, "Client", MagicMock())

    with pytest.raises(RuntimeError, match="does not match"):
        client_module._build_data_plane_firestore_client()


def test_storage_client_project_prefers_the_customer_pin(monkeypatch):
    _clear_credential_env(monkeypatch)
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "based-hardware-dev")
    assert local_storage.storage_client_project() == "based-hardware-dev"
    monkeypatch.setenv("OMI_CUSTOMER_DATA_PROJECT", "based-hardware")
    assert local_storage.storage_client_project() == "based-hardware"


class _TokenOnlyCredentials(google_auth_credentials.Credentials):
    """Shape of Cloud Run / Workload Identity credentials: a token, no private key."""

    def __init__(self):
        super().__init__()
        self.service_account_email = "default"
        self.refreshes = 0

    def refresh(self, request):
        self.refreshes += 1
        self.token = "access-token"
        self.service_account_email = "backend-runtime@based-hardware.iam.gserviceaccount.com"


class _SigningCredentials(_TokenOnlyCredentials, google_auth_credentials.Signing):
    def sign_bytes(self, message):
        return b"signature"

    @property
    def signer_email(self):
        return "key@example.com"

    @property
    def signer(self):
        return None


def test_token_only_identity_signs_urls_through_iam():
    credentials = _TokenOnlyCredentials()

    kwargs = local_storage.iam_signing_kwargs(SimpleNamespace(_credentials=credentials))

    assert kwargs == {
        "service_account_email": "backend-runtime@based-hardware.iam.gserviceaccount.com",
        "access_token": "access-token",
    }
    assert credentials.refreshes == 1


class _StorageScopedCredentials(google_auth_credentials.Scoped, _TokenOnlyCredentials):
    """Cloud Run metadata credentials as the storage client holds them: devstorage scopes only.

    The metadata server mints tokens for exactly the requested scopes, and IAM
    signBlob rejects a devstorage-only token (ACCESS_TOKEN_SCOPE_INSUFFICIENT).
    """

    def __init__(self, scopes=None):
        super().__init__()
        self._scopes = scopes or ["https://www.googleapis.com/auth/devstorage.full_control"]
        self.scoped_copies = []

    @property
    def requires_scopes(self):
        return False

    def with_scopes(self, scopes, default_scopes=None):
        copy = _StorageScopedCredentials(scopes=list(scopes))
        self.scoped_copies.append(copy)
        return copy

    def refresh(self, request):
        super().refresh(request)
        self.token = "token-for:" + ",".join(self._scopes)


def test_token_only_identity_signs_with_a_cloud_platform_scoped_token():
    credentials = _StorageScopedCredentials()

    kwargs = local_storage.iam_signing_kwargs(SimpleNamespace(_credentials=credentials))

    assert kwargs == {
        "service_account_email": "backend-runtime@based-hardware.iam.gserviceaccount.com",
        "access_token": "token-for:https://www.googleapis.com/auth/cloud-platform",
    }
    # The storage client's own (devstorage-scoped) credentials are never used to sign.
    assert credentials.refreshes == 0
    # The scoped copy is built once and reused, so each URL does not mint a new token.
    local_storage.iam_signing_kwargs(SimpleNamespace(_credentials=credentials))
    assert len(credentials.scoped_copies) == 1
    assert credentials.scoped_copies[0].refreshes == 1


def test_key_backed_identity_and_fakes_sign_locally():
    assert local_storage.iam_signing_kwargs(SimpleNamespace(_credentials=_SigningCredentials())) == {}
    assert local_storage.iam_signing_kwargs(MagicMock()) == {}
    assert local_storage.iam_signing_kwargs(None) == {}


def test_firebase_admin_options_for_a_keyless_identity():
    assert firebase_admin_options({}) is None
    assert firebase_admin_options({"OMI_CUSTOMER_DATA_PROJECT": "based-hardware"}) == {"projectId": "based-hardware"}
    assert firebase_admin_options(
        {
            "FIREBASE_AUTH_PROJECT_ID": "auth-project",
            "OMI_CUSTOMER_DATA_PROJECT": "based-hardware",
            "FIREBASE_SIGNER_SERVICE_ACCOUNT": "signer@based-hardware.iam.gserviceaccount.com",
        }
    ) == {"projectId": "auth-project", "serviceAccountId": "signer@based-hardware.iam.gserviceaccount.com"}
