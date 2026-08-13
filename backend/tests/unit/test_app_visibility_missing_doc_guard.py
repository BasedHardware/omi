"""update_app_visibility_in_db must not crash when the private app document is missing.

Making a private app public deletes the `*-private` document and recreates it under a new public id.
It read the source document with `app_ref.get().to_dict()` and immediately did `app['id'] = ...`.
When the document does not exist `.to_dict()` returns None, so that line raised
`TypeError: 'NoneType' object does not support item assignment` -> a 500. The change-visibility
endpoint checks the app exists first, but that check can read a stale cache while this function does
a direct Firestore read, so the document can be gone here (deleted, or a delete-race). The function
now skips the delete-and-recreate when the document is missing. These cover the pure getter behavior.
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


# Stub the heavy leaves database/apps.py imports so the real module loads.
for _p in ["google", "google.cloud", "google.cloud.firestore_v1", "database", "models"]:
    _pkg(_p)
_mod("google.cloud.firestore_v1.base_query", BaseCompositeFilter=MagicMock(), FieldFilter=MagicMock())
_mod("google.cloud.firestore", ArrayUnion=MagicMock(), ArrayRemove=MagicMock())
_mod("ulid", ULID=lambda: "01HZZTESTULID")
_mod("models.app", UsageHistoryType=MagicMock())
_mod("database._client", db=MagicMock())


def _load():
    # Load under the real package-qualified name so `from ._client import db` resolves against the
    # stubbed `database` package above.
    spec = importlib.util.spec_from_file_location("database.apps", str(BACKEND_DIR / "database" / "apps.py"))
    mod = importlib.util.module_from_spec(spec)
    sys.modules["database.apps"] = mod
    spec.loader.exec_module(mod)
    return mod


apps = _load()


def _db_with(to_dict_result):
    """A db whose plugins_data/<id> document get().to_dict() returns the given value."""
    doc_ref = MagicMock()
    doc_ref.get.return_value.to_dict.return_value = to_dict_result
    db = MagicMock()
    db.collection.return_value.document.return_value = doc_ref
    return db, doc_ref


def test_missing_private_doc_skips_delete_and_recreate():
    # to_dict() is None when the document does not exist; the function must return without touching
    # the document (no delete, no recreate) instead of raising TypeError.
    db, doc_ref = _db_with(None)
    with patch.object(apps, "db", db):
        result = apps.update_app_visibility_in_db("plug-private", private=False)
    assert result is None
    doc_ref.delete.assert_not_called()
    doc_ref.set.assert_not_called()


def test_present_private_doc_is_republished_public():
    # Happy path is unchanged: an existing private app is deleted and recreated as a public app.
    db, doc_ref = _db_with({"name": "My App", "private": True})
    with patch.object(apps, "db", db):
        apps.update_app_visibility_in_db("plug-private", private=False)
    doc_ref.delete.assert_called_once()
    doc_ref.set.assert_called_once()
    saved = doc_ref.set.call_args[0][0]
    assert saved["private"] is False
    assert saved["id"].startswith("plug-")


def test_non_private_path_updates_flag():
    # The simple toggle path (no private->public republish) just updates the flag in place.
    db, doc_ref = _db_with({"name": "X"})
    with patch.object(apps, "db", db):
        apps.update_app_visibility_in_db("plug", private=True)
    doc_ref.update.assert_called_once_with({"private": True})
