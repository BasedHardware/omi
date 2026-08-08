"""Tests that user-document getters in database/users.py fail soft on a missing user doc.

Several simple getters did `user_ref.get().to_dict().get(field)`. When the user document does not
exist, `.to_dict()` returns None, so `.get(field)` raised AttributeError, surfacing as a 500 on
authenticated endpoints (store-recording permission, private-cloud-sync, the Stripe/PayPal/default
payment-method getters, training-data opt-in). These getters use the `.to_dict() or {}` guard so a
missing doc yields the same default as a missing field. Migrated to the WP2 storage port (ADR-0002):
the getters read through the injected `_store` seam.
"""

import os

import pytest

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)

import database.users as users
from tests.store_fakes import FakeDocumentStore


def _bind(monkeypatch, uid, data):
    store = FakeDocumentStore()
    if data is not None:
        store.set(f"users/{uid}", data)
    monkeypatch.setattr(users, "_store", lambda: store)


# (getter name, field key, default when missing, a present value)
CASES = [
    ("get_user_store_recording_permission", "store_recording_permission", False, True),
    ("get_user_private_cloud_sync_enabled", "private_cloud_sync_enabled", True, False),
    ("get_stripe_connect_account_id", "stripe_account_id", None, "acct_123"),
    ("get_paypal_payment_details", "paypal_details", None, {"email": "x@y.z"}),
    ("get_default_payment_method", "default_payment_method", None, "pm_123"),
    ("get_user_training_data_opt_in", "training_data_opt_in", None, {"opt_in": True}),
]


@pytest.mark.parametrize("fn,field,default,present", CASES)
def test_missing_user_doc_returns_default_not_crash(monkeypatch, fn, field, default, present):
    # A missing user document must return the default rather than raising (which became a 500).
    _bind(monkeypatch, "uid-without-doc", None)
    assert getattr(users, fn)("uid-without-doc") == default


@pytest.mark.parametrize("fn,field,default,present", CASES)
def test_existing_user_doc_returns_field_value(monkeypatch, fn, field, default, present):
    _bind(monkeypatch, "uid", {field: present})
    assert getattr(users, fn)("uid") == present


@pytest.mark.parametrize("fn,field,default,present", CASES)
def test_doc_present_but_field_absent_returns_default(monkeypatch, fn, field, default, present):
    _bind(monkeypatch, "uid", {"unrelated": 1})
    assert getattr(users, fn)("uid") == default
