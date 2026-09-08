"""get_data_plane_firestore_client(): the desktop-backend customer-data-plane seam.

OMI_FIRESTORE_DATA_PLANE_PROJECT lets a service whose compute project (bare ADC /
GOOGLE_CLOUD_PROJECT) differs from the project holding the user's actual Firestore
data pin reads/writes to that data-plane project instead. Every service that never
sets the var — which today is every service except desktop-backend — must see
byte-identical behavior to get_firestore_client(). desktop-backend fails closed
when the overlay is unset so ledger writes cannot land on the compute project.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import database._client as client_module


def _reset_caches(monkeypatch):
    monkeypatch.setattr(client_module, "_data_plane_firestore_client", None)
    monkeypatch.setattr(client_module, "_firestore_client", None)


def test_pins_project_when_var_is_set_and_emulator_is_not(monkeypatch):
    _reset_caches(monkeypatch)
    monkeypatch.delenv("FIRESTORE_EMULATOR_HOST", raising=False)
    monkeypatch.setenv("OMI_FIRESTORE_DATA_PLANE_PROJECT", "based-hardware")

    fake_client = SimpleNamespace(collection=MagicMock(return_value="pinned-ref"))
    firestore_client_ctor = MagicMock(return_value=fake_client)
    prepare_credentials = MagicMock()
    monkeypatch.setattr(client_module.firestore, "Client", firestore_client_ctor)
    monkeypatch.setattr(client_module, "prepare_google_credentials", prepare_credentials)
    monkeypatch.setattr(
        client_module,
        "_build_firestore_client",
        MagicMock(side_effect=AssertionError("must not fall back to get_firestore_client when the var is set")),
    )

    result = client_module.get_data_plane_firestore_client()

    assert result is fake_client
    prepare_credentials.assert_called_once_with()
    firestore_client_ctor.assert_called_once_with(project="based-hardware")


def test_caches_the_pinned_client_across_calls(monkeypatch):
    _reset_caches(monkeypatch)
    monkeypatch.delenv("FIRESTORE_EMULATOR_HOST", raising=False)
    monkeypatch.setenv("OMI_FIRESTORE_DATA_PLANE_PROJECT", "based-hardware")

    fake_client = SimpleNamespace()
    firestore_client_ctor = MagicMock(return_value=fake_client)
    monkeypatch.setattr(client_module.firestore, "Client", firestore_client_ctor)
    monkeypatch.setattr(client_module, "prepare_google_credentials", MagicMock())

    first = client_module.get_data_plane_firestore_client()
    second = client_module.get_data_plane_firestore_client()

    assert first is fake_client
    assert second is fake_client
    firestore_client_ctor.assert_called_once()


def test_falls_back_to_get_firestore_client_when_var_is_unset(monkeypatch):
    _reset_caches(monkeypatch)
    monkeypatch.delenv("FIRESTORE_EMULATOR_HOST", raising=False)
    monkeypatch.delenv("OMI_FIRESTORE_DATA_PLANE_PROJECT", raising=False)
    monkeypatch.delenv("K_SERVICE", raising=False)
    monkeypatch.delenv("APP_NAME", raising=False)

    fake_client = SimpleNamespace()
    monkeypatch.setattr(client_module, "_build_firestore_client", MagicMock(return_value=fake_client))
    firestore_client_ctor = MagicMock(side_effect=AssertionError("must not construct a second, pinned client"))
    monkeypatch.setattr(client_module.firestore, "Client", firestore_client_ctor)

    result = client_module.get_data_plane_firestore_client()

    assert result is fake_client
    # Identical object, not merely an equivalent one: every service that never
    # sets the var shares get_firestore_client()'s single cached client.
    assert result is client_module.get_firestore_client()
    firestore_client_ctor.assert_not_called()


def test_falls_back_when_var_is_set_to_an_empty_string(monkeypatch):
    _reset_caches(monkeypatch)
    monkeypatch.delenv("FIRESTORE_EMULATOR_HOST", raising=False)
    monkeypatch.setenv("OMI_FIRESTORE_DATA_PLANE_PROJECT", "   ")
    monkeypatch.delenv("K_SERVICE", raising=False)
    monkeypatch.delenv("APP_NAME", raising=False)

    fake_client = SimpleNamespace()
    monkeypatch.setattr(client_module, "_build_firestore_client", MagicMock(return_value=fake_client))

    result = client_module.get_data_plane_firestore_client()

    assert result is fake_client


def test_desktop_backend_fails_closed_when_data_plane_project_is_unset(monkeypatch):
    _reset_caches(monkeypatch)
    monkeypatch.delenv("FIRESTORE_EMULATOR_HOST", raising=False)
    monkeypatch.delenv("OMI_FIRESTORE_DATA_PLANE_PROJECT", raising=False)
    monkeypatch.setenv("K_SERVICE", "desktop-backend")

    with pytest.raises(RuntimeError, match="OMI_FIRESTORE_DATA_PLANE_PROJECT is required on desktop-backend"):
        client_module.get_data_plane_firestore_client()


def test_emulator_host_wins_even_when_the_var_is_set(monkeypatch):
    _reset_caches(monkeypatch)
    monkeypatch.setenv("FIRESTORE_EMULATOR_HOST", "localhost:8080")
    monkeypatch.setenv("OMI_FIRESTORE_DATA_PLANE_PROJECT", "based-hardware")

    fake_client = SimpleNamespace()
    monkeypatch.setattr(client_module, "_build_firestore_client", MagicMock(return_value=fake_client))
    firestore_client_ctor = MagicMock(side_effect=AssertionError("must not construct a second, pinned client"))
    monkeypatch.setattr(client_module.firestore, "Client", firestore_client_ctor)

    result = client_module.get_data_plane_firestore_client()

    assert result is fake_client
    firestore_client_ctor.assert_not_called()


def test_data_plane_db_lazy_proxy_defers_until_first_attribute_access(monkeypatch):
    fake_client = SimpleNamespace(collection=MagicMock(return_value="lazy-ref"))
    getter = MagicMock(return_value=fake_client)
    monkeypatch.setattr(client_module, "get_data_plane_firestore_client", getter)

    getter.assert_not_called()
    assert client_module.data_plane_db.collection("users") == "lazy-ref"
    getter.assert_called_once_with()


def test_uses_mounted_data_plane_credentials_when_available(monkeypatch):
    _reset_caches(monkeypatch)
    monkeypatch.delenv("FIRESTORE_EMULATOR_HOST", raising=False)
    monkeypatch.setenv("OMI_FIRESTORE_DATA_PLANE_PROJECT", "based-hardware")

    fake_credentials = object()
    monkeypatch.setattr(
        client_module,
        "customer_entitlement_service_account",
        MagicMock(return_value=(fake_credentials, "based-hardware")),
    )
    fake_client = SimpleNamespace()
    firestore_client_ctor = MagicMock(return_value=fake_client)
    monkeypatch.setattr(client_module.firestore, "Client", firestore_client_ctor)
    monkeypatch.setattr(
        client_module,
        "prepare_google_credentials",
        MagicMock(side_effect=AssertionError("explicit credentials must not fall back to ADC")),
    )

    result = client_module.get_data_plane_firestore_client()

    assert result is fake_client
    firestore_client_ctor.assert_called_once_with(credentials=fake_credentials, project="based-hardware")


def test_refuses_mounted_credentials_for_a_different_project(monkeypatch):
    _reset_caches(monkeypatch)
    monkeypatch.delenv("FIRESTORE_EMULATOR_HOST", raising=False)
    monkeypatch.setenv("OMI_FIRESTORE_DATA_PLANE_PROJECT", "based-hardware")

    monkeypatch.setattr(
        client_module,
        "customer_entitlement_service_account",
        MagicMock(return_value=(object(), "some-other-project")),
    )

    import pytest

    with pytest.raises(RuntimeError, match="does not match the mounted service account"):
        client_module.get_data_plane_firestore_client()


def test_falls_back_to_pinned_adc_without_mounted_credentials(monkeypatch):
    _reset_caches(monkeypatch)
    monkeypatch.delenv("FIRESTORE_EMULATOR_HOST", raising=False)
    monkeypatch.setenv("OMI_FIRESTORE_DATA_PLANE_PROJECT", "based-hardware")

    monkeypatch.setattr(client_module, "customer_entitlement_service_account", MagicMock(return_value=None))
    fake_client = SimpleNamespace()
    firestore_client_ctor = MagicMock(return_value=fake_client)
    prepare_credentials = MagicMock()
    monkeypatch.setattr(client_module.firestore, "Client", firestore_client_ctor)
    monkeypatch.setattr(client_module, "prepare_google_credentials", prepare_credentials)

    result = client_module.get_data_plane_firestore_client()

    assert result is fake_client
    prepare_credentials.assert_called_once()
    firestore_client_ctor.assert_called_once_with(project="based-hardware")


def test_named_qa_database_is_pinned_only_under_the_isolated_dev_fence(monkeypatch):
    _reset_caches(monkeypatch)
    monkeypatch.delenv("FIRESTORE_EMULATOR_HOST", raising=False)
    monkeypatch.setenv("OMI_FIRESTORE_DATA_PLANE_PROJECT", "based-hardware-dev")
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "based-hardware-dev")
    monkeypatch.setenv("OMI_ENV_STAGE", "dev")
    monkeypatch.setenv("OMI_JIT_QA_AUTH_ONLY", "true")
    monkeypatch.setenv("FIRESTORE_DATABASE_ID", "jit-qa")
    monkeypatch.setattr(client_module, "customer_entitlement_service_account", MagicMock(return_value=None))
    fake_client = SimpleNamespace()
    firestore_client_ctor = MagicMock(return_value=fake_client)
    monkeypatch.setattr(client_module.firestore, "Client", firestore_client_ctor)
    monkeypatch.setattr(client_module, "prepare_google_credentials", MagicMock())

    assert client_module.get_data_plane_firestore_client() is fake_client
    firestore_client_ctor.assert_called_once_with(project="based-hardware-dev", database="jit-qa")


def test_named_qa_database_fails_closed_outside_isolated_dev(monkeypatch):
    _reset_caches(monkeypatch)
    monkeypatch.delenv("FIRESTORE_EMULATOR_HOST", raising=False)
    monkeypatch.setenv("OMI_FIRESTORE_DATA_PLANE_PROJECT", "based-hardware")
    monkeypatch.setenv("FIRESTORE_DATABASE_ID", "jit-qa")
    with pytest.raises(RuntimeError, match="isolated development JIT QA fence"):
        client_module.get_data_plane_firestore_client()


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("OMI_ENV_STAGE", "prod"),
        ("OMI_ENV_STAGE", ""),
        ("GOOGLE_CLOUD_PROJECT", "based-hardware"),
        ("OMI_FIRESTORE_DATA_PLANE_PROJECT", None),
    ],
)
def test_named_qa_database_rejects_any_non_dev_auth_fence(monkeypatch, name, value):
    _reset_caches(monkeypatch)
    monkeypatch.delenv("FIRESTORE_EMULATOR_HOST", raising=False)
    monkeypatch.setenv("OMI_FIRESTORE_DATA_PLANE_PROJECT", "based-hardware-dev")
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "based-hardware-dev")
    monkeypatch.setenv("OMI_ENV_STAGE", "dev")
    monkeypatch.setenv("OMI_JIT_QA_AUTH_ONLY", "true")
    monkeypatch.setenv("FIRESTORE_DATABASE_ID", "jit-qa")
    if value is not None:
        monkeypatch.setenv(name, value)
    else:
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(RuntimeError, match="isolated development JIT QA fence"):
        client_module._build_firestore_client()


def test_regular_firestore_factory_uses_named_qa_database(monkeypatch):
    monkeypatch.delenv("FIRESTORE_EMULATOR_HOST", raising=False)
    monkeypatch.setenv("OMI_FIRESTORE_DATA_PLANE_PROJECT", "based-hardware-dev")
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "based-hardware-dev")
    monkeypatch.setenv("OMI_ENV_STAGE", "dev")
    monkeypatch.setenv("OMI_JIT_QA_AUTH_ONLY", "true")
    monkeypatch.setenv("FIRESTORE_DATABASE_ID", "jit-qa")
    monkeypatch.setattr(client_module, "customer_data_service_account", MagicMock(return_value=None))
    monkeypatch.setattr(client_module, "prepare_google_credentials", MagicMock())
    fake_client = SimpleNamespace()
    firestore_client_ctor = MagicMock(return_value=fake_client)
    monkeypatch.setattr(client_module.firestore, "Client", firestore_client_ctor)

    assert client_module._build_firestore_client() is fake_client
    firestore_client_ctor.assert_called_once_with(project="based-hardware-dev", database="jit-qa")


@pytest.mark.parametrize("database", [None, "(default)"])
def test_qa_firestore_factory_requires_named_database(monkeypatch, database):
    monkeypatch.delenv("FIRESTORE_EMULATOR_HOST", raising=False)
    monkeypatch.setenv("OMI_FIRESTORE_DATA_PLANE_PROJECT", "based-hardware-dev")
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "based-hardware-dev")
    monkeypatch.setenv("OMI_ENV_STAGE", "dev")
    monkeypatch.setenv("OMI_JIT_QA_AUTH_ONLY", "true")
    if database is None:
        monkeypatch.delenv("FIRESTORE_DATABASE_ID", raising=False)
    else:
        monkeypatch.setenv("FIRESTORE_DATABASE_ID", database)
    monkeypatch.setattr(client_module, "customer_data_service_account", MagicMock(return_value=None))
    monkeypatch.setattr(client_module, "prepare_google_credentials", MagicMock())
    with pytest.raises(RuntimeError, match="requires FIRESTORE_DATABASE_ID=jit-qa"):
        client_module._build_firestore_client()


def test_qa_customer_factory_requires_named_database(monkeypatch):
    monkeypatch.delenv("FIRESTORE_EMULATOR_HOST", raising=False)
    monkeypatch.setenv("OMI_FIRESTORE_DATA_PLANE_PROJECT", "based-hardware-dev")
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "based-hardware-dev")
    monkeypatch.setenv("OMI_ENV_STAGE", "dev")
    monkeypatch.setenv("OMI_JIT_QA_AUTH_ONLY", "true")
    monkeypatch.delenv("FIRESTORE_DATABASE_ID", raising=False)
    monkeypatch.setattr(
        client_module,
        "customer_entitlement_service_account",
        MagicMock(return_value=(object(), "based-hardware-dev")),
    )
    with pytest.raises(RuntimeError, match="requires FIRESTORE_DATABASE_ID=jit-qa"):
        client_module._build_customer_firestore_client()


def test_qa_data_plane_factory_rejects_default_database(monkeypatch):
    monkeypatch.delenv("FIRESTORE_EMULATOR_HOST", raising=False)
    monkeypatch.setenv("OMI_FIRESTORE_DATA_PLANE_PROJECT", "based-hardware-dev")
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "based-hardware-dev")
    monkeypatch.setenv("OMI_ENV_STAGE", "dev")
    monkeypatch.setenv("OMI_JIT_QA_AUTH_ONLY", "true")
    monkeypatch.setenv("FIRESTORE_DATABASE_ID", "(default)")
    with pytest.raises(RuntimeError, match="requires FIRESTORE_DATABASE_ID=jit-qa"):
        client_module._build_data_plane_firestore_client()


def test_customer_entitlement_factory_uses_named_qa_database(monkeypatch):
    monkeypatch.delenv("FIRESTORE_EMULATOR_HOST", raising=False)
    monkeypatch.setenv("OMI_FIRESTORE_DATA_PLANE_PROJECT", "based-hardware-dev")
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "based-hardware-dev")
    monkeypatch.setenv("OMI_ENV_STAGE", "dev")
    monkeypatch.setenv("OMI_JIT_QA_AUTH_ONLY", "true")
    monkeypatch.setenv("FIRESTORE_DATABASE_ID", "jit-qa")
    credentials = object()
    monkeypatch.setattr(
        client_module,
        "customer_entitlement_service_account",
        MagicMock(return_value=(credentials, "based-hardware-dev")),
    )
    fake_client = SimpleNamespace()
    firestore_client_ctor = MagicMock(return_value=fake_client)
    monkeypatch.setattr(client_module.firestore, "Client", firestore_client_ctor)

    assert client_module._build_customer_firestore_client() is fake_client
    firestore_client_ctor.assert_called_once_with(
        credentials=credentials, project="based-hardware-dev", database="jit-qa"
    )
