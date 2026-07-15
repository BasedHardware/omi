"""Tests that user-document getters in database/users.py fail soft on a missing user doc.

Several simple getters did `user_ref.get().to_dict().get(field)`. When the user document does not
exist, `.to_dict()` returns None, so `.get(field)` raised AttributeError, surfacing as a 500 on
authenticated endpoints (store-recording permission, private-cloud-sync, the Stripe/PayPal/default
payment-method getters, training-data opt-in) and in conversation post-processing. A UID can be
valid in auth but missing from Firestore (new user before doc creation, mid-deletion, or a data
race). These getters now use the file's existing `.to_dict() or {}` guard so a missing doc yields
the same default as a missing field instead of crashing. These cover the pure getter behavior.
"""

import importlib.util
import os
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)


def _pkg(name):
    mod = sys.modules.get(name)
    if mod is None or not hasattr(mod, "__path__"):
        mod = types.ModuleType(name)
        mod.__path__ = []
        sys.modules[name] = mod
    return mod


def _mod(name, **attrs):
    mod = types.ModuleType(name)
    for key, value in attrs.items():
        setattr(mod, key, value)
    sys.modules[name] = mod
    return mod


# Stub the heavy leaves database/users.py imports so the real module loads; the @transactional /
# CachePolicy module-level constructs become harmless mocks. None are exercised by the getters here.
for _p in ["google", "google.cloud", "database", "models", "utils"]:
    _pkg(_p)
_mod("google.cloud.firestore", SERVER_TIMESTAMP=MagicMock())
_mod("google.cloud.firestore_v1", FieldFilter=MagicMock(), transactional=lambda fn: fn)
_mod("database._client", db=MagicMock(), document_id_from_seed=lambda seed: "id")
_mod("database.read_boundary", parse_snapshot_or_none=MagicMock(), parse_snapshot_strict=MagicMock())
_mod("database.firestore_cache", CachePolicy=MagicMock(), get_or_fetch=MagicMock(), invalidate=MagicMock())
_mod(
    "database.redis_db",
    try_acquire_client_device_write_lock=MagicMock(return_value=True),
    try_acquire_user_platform_write_lock=MagicMock(return_value=True),
)
_mod(
    "models.users",
    Subscription=MagicMock(),
    PlanLimits=MagicMock(),
    PlanType=MagicMock(),
    SubscriptionStatus=MagicMock(),
)
_mod("utils.subscription", get_default_basic_subscription=MagicMock())
_mod("models.other", Person=MagicMock())


def _load():
    # Load under the real package-qualified name so the module's `from ._client import ...` relative
    # import resolves against the stubbed `database` package above.
    spec = importlib.util.spec_from_file_location("database.users", str(BACKEND_DIR / "database" / "users.py"))
    mod = importlib.util.module_from_spec(spec)
    sys.modules["database.users"] = mod
    spec.loader.exec_module(mod)
    return mod


users = _load()


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
def test_missing_user_doc_returns_default_not_crash(fn, field, default, present):
    # to_dict() is None when the user document does not exist; the getter must return the default
    # rather than raising AttributeError (which previously became a 500).
    func = getattr(users, fn)
    with patch.object(users, "db", _db_for(None)):
        assert func("uid-without-doc") == default


@pytest.mark.parametrize("fn,field,default,present", CASES)
def test_existing_user_doc_returns_field_value(fn, field, default, present):
    # Happy path is unchanged: a present field is returned as-is.
    func = getattr(users, fn)
    with patch.object(users, "db", _db_for({field: present})):
        assert func("uid") == present


@pytest.mark.parametrize("fn,field,default,present", CASES)
def test_doc_present_but_field_absent_returns_default(fn, field, default, present):
    # A doc that exists but lacks the field still yields the default (also unchanged behavior).
    func = getattr(users, fn)
    with patch.object(users, "db", _db_for({"unrelated": 1})):
        assert func("uid") == default
