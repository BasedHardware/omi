"""Tests that user-document getters in database/users.py fail soft on a missing user doc.

Several simple getters did `user_ref.get().to_dict().get(field)`. When the user document does not
exist, `.to_dict()` returns None, so `.get(field)` raised AttributeError, surfacing as a 500 on
authenticated endpoints (store-recording permission, private-cloud-sync, the Stripe/PayPal/default
payment-method getters, training-data opt-in) and in conversation post-processing. A UID can be
valid in auth but missing from Firestore (new user before doc creation, mid-deletion, or a data
race). These getters now use the file's existing `.to_dict() or {}` guard so a missing doc yields
the same default as a missing field instead of crashing. These cover the pure getter behavior.
"""

import os
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock, patch

import pytest

from testing.import_isolation import load_module_fresh, stub_modules

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)


def _module(name: str, **attrs: object) -> ModuleType:
    mod = ModuleType(name)
    for key, value in attrs.items():
        setattr(mod, key, value)
    return mod


@pytest.fixture(scope="module")
def users():
    """Load database.users with import-time leaves faked in a restoring context."""
    firestore = _module("google.cloud.firestore", SERVER_TIMESTAMP=MagicMock())
    firestore_v1 = _module("google.cloud.firestore_v1", FieldFilter=MagicMock(), transactional=lambda fn: fn)
    fakes = {
        "google.cloud.firestore": firestore,
        "google.cloud.firestore_v1": firestore_v1,
        "database._client": _module("database._client", db=MagicMock(), document_id_from_seed=lambda seed: "id"),
        "database.firestore_cache": _module(
            "database.firestore_cache", CachePolicy=MagicMock(), get_or_fetch=MagicMock(), invalidate=MagicMock()
        ),
        "database.redis_db": _module(
            "database.redis_db",
            try_acquire_client_device_write_lock=MagicMock(return_value=True),
            try_acquire_user_platform_write_lock=MagicMock(return_value=True),
        ),
        "models.users": _module(
            "models.users",
            Subscription=MagicMock(),
            PlanLimits=MagicMock(),
            PlanType=MagicMock(),
            SubscriptionStatus=MagicMock(),
        ),
        "utils.subscription": _module("utils.subscription", get_default_basic_subscription=MagicMock()),
        "models.other": _module("models.other", Person=MagicMock()),
    }
    with stub_modules(fakes):
        yield load_module_fresh("database.users", str(BACKEND_DIR / "database" / "users.py"))


def _db_for(to_dict_result):
    """A db whose users/<uid> document get().to_dict() returns the given value (None = missing doc)."""
    snapshot = MagicMock()
    snapshot.to_dict.return_value = to_dict_result
    db = MagicMock()
    db.collection.return_value.document.return_value.get.return_value = snapshot
    return db


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
def test_missing_user_doc_returns_default_not_crash(users, fn, field, default, present):
    # to_dict() is None when the user document does not exist; the getter must return the default
    # rather than raising AttributeError (which previously became a 500).
    func = getattr(users, fn)
    with patch.object(users, "db", _db_for(None)):
        assert func("uid-without-doc") == default


@pytest.mark.parametrize("fn,field,default,present", CASES)
def test_existing_user_doc_returns_field_value(users, fn, field, default, present):
    # Happy path is unchanged: a present field is returned as-is.
    func = getattr(users, fn)
    with patch.object(users, "db", _db_for({field: present})):
        assert func("uid") == present


@pytest.mark.parametrize("fn,field,default,present", CASES)
def test_doc_present_but_field_absent_returns_default(users, fn, field, default, present):
    # A doc that exists but lacks the field still yields the default (also unchanged behavior).
    func = getattr(users, fn)
    with patch.object(users, "db", _db_for({"unrelated": 1})):
        assert func("uid") == default
