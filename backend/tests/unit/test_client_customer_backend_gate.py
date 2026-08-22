"""database._client must gate BOTH the default and the CUSTOMER Firestore client on STORAGE_BACKEND, so
an on-prem (STORAGE_BACKEND=mongo) deployment never constructs a real Google Firestore client for customer
data (identity/subscription/usage, realtime sessions, LLM usage) — even when a customer/entitlement service
account is configured. cubic review PR 10887, _client.py:95.

The gate is tested without building a real store (which needs MONGO_URI + a live server): stub
get_firestore_client to a sentinel and assert the customer builder routes to it under mongo instead of
constructing a firestore.Client.
"""

from __future__ import annotations

import pytest


def test_customer_builder_routes_to_facade_under_mongo(monkeypatch):
    monkeypatch.setenv("STORAGE_BACKEND", "mongo")
    monkeypatch.delenv("FIRESTORE_EMULATOR_HOST", raising=False)

    from database import _client

    sentinel = object()  # stands in for the neutral facade get_firestore_client() would return
    monkeypatch.setattr(_client, "get_firestore_client", lambda: sentinel)
    # Fail the test loudly if the customer builder ever reaches the real-Firestore construction path.
    monkeypatch.setattr(
        _client.firestore, "Client", lambda *a, **k: pytest.fail("built a real firestore.Client under mongo")
    )

    assert _client._build_customer_firestore_client() is sentinel


def test_customer_builder_builds_real_client_under_firestore(monkeypatch):
    # Control: with the default (firestore) backend and no emulator, an entitlement SA still builds a real
    # client — the gate must not change cloud behavior.
    monkeypatch.setenv("STORAGE_BACKEND", "firestore")
    monkeypatch.delenv("FIRESTORE_EMULATOR_HOST", raising=False)

    from database import _client

    marker = object()
    monkeypatch.setattr(_client, "customer_entitlement_service_account", lambda: ("cred", "proj"))
    monkeypatch.setattr(_client.firestore, "Client", lambda *a, **k: marker)
    assert _client._build_customer_firestore_client() is marker
