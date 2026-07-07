"""update_advice must return None (404) when the advice is deleted mid-update, not crash with a 500.

PATCH /v1/advice/{advice_id} -> update_advice checks the document exists, applies the update, then
re-reads it to return the fresh value. Two concurrent-deletion windows turned that into a 500:
  1. Deleted between the existence check and ref.update(...) -> Firestore update() raises NotFound.
  2. Deleted between the update and the re-read -> ref.get().to_dict() is None, so result['id'] = ...
     raised TypeError.
The router treats a None return as a 404, so both races should yield 404, not an unhandled 500. The
function now returns None in both cases. These cover the pure database-function behavior.
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


class _NotFound(Exception):
    """Stand-in for google.api_core.exceptions.NotFound."""


# Stub the heavy leaves database/advice.py imports so the real module loads.
for _p in ["google", "google.cloud", "google.api_core", "database"]:
    _pkg(_p)
_mod("google.api_core.exceptions", NotFound=_NotFound)
_mod("google.cloud.firestore", SERVER_TIMESTAMP=MagicMock(), Query=MagicMock())
_mod("google.cloud.firestore_v1.base_query", FieldFilter=MagicMock())
_mod("database._client", db=MagicMock())


def _load():
    spec = importlib.util.spec_from_file_location("database.advice", str(BACKEND_DIR / "database" / "advice.py"))
    mod = importlib.util.module_from_spec(spec)
    sys.modules["database.advice"] = mod
    spec.loader.exec_module(mod)
    return mod


advice = _load()


def _snap(exists, data=None):
    snap = MagicMock()
    snap.exists = exists
    snap.to_dict.return_value = data
    return snap


def _wire(get_results, update_exc=None):
    """A mocked advice collection whose document().get() yields the given snapshots in order."""
    ref = MagicMock()
    ref.get.side_effect = list(get_results)
    if update_exc is not None:
        ref.update.side_effect = update_exc
    col = MagicMock()
    col.document.return_value = ref
    return col, ref


def test_missing_advice_returns_none():
    # The existing existence check: a UID/advice_id with no document returns None (404), no update.
    col, ref = _wire([_snap(False)])
    with patch.object(advice, "_user_col", return_value=col):
        assert advice.update_advice("u", "adv1", is_read=True) is None
    ref.update.assert_not_called()


def test_deleted_before_update_returns_none():
    # Deleted between the existence check and the update: Firestore update() raises NotFound, which
    # must become a None return (404), not a propagated 500.
    col, ref = _wire([_snap(True)], update_exc=_NotFound)
    with patch.object(advice, "_user_col", return_value=col):
        assert advice.update_advice("u", "adv1", is_read=True) is None


def test_deleted_after_update_returns_none():
    # Deleted between the update and the re-read: to_dict() is None, which must become a None return
    # instead of a TypeError on result['id'].
    col, ref = _wire([_snap(True), _snap(False, None)])
    with patch.object(advice, "_user_col", return_value=col):
        assert advice.update_advice("u", "adv1", is_dismissed=True) is None


def test_happy_path_returns_dict_with_id():
    col, ref = _wire([_snap(True), _snap(True, {"text": "hi", "is_read": False})])
    with patch.object(advice, "_user_col", return_value=col):
        result = advice.update_advice("u", "adv1", is_read=True)
    assert result["id"] == "adv1"
    assert result["text"] == "hi"
