"""get_data_plane_firestore_client(): the desktop-backend customer-data-plane seam.

OMI_FIRESTORE_DATA_PLANE_PROJECT lets a service whose compute project (bare ADC /
GOOGLE_CLOUD_PROJECT) differs from the project holding the user's actual Firestore
data pin reads/writes to that data-plane project instead. Every service that never
sets the var — which today is every service except desktop-backend, and even
desktop-backend in prod, where data_plane_project == compute_project by
construction — must see byte-identical behavior to get_firestore_client().
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

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

    fake_client = SimpleNamespace()
    monkeypatch.setattr(client_module, "_build_firestore_client", MagicMock(return_value=fake_client))

    result = client_module.get_data_plane_firestore_client()

    assert result is fake_client


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
