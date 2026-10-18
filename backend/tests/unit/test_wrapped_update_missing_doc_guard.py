"""update_wrapped_status and update_wrapped_progress must return False when doc is deleted mid-update, not crash with 500."""

import importlib.util
import os
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

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


for _p in ["google", "google.cloud", "google.api_core", "database"]:
    _pkg(_p)
_mod("google.api_core.exceptions", NotFound=_NotFound)
_mod("database._client", db=MagicMock())


def _load():
    spec = importlib.util.spec_from_file_location("database.wrapped", str(BACKEND_DIR / "database" / "wrapped.py"))
    mod = importlib.util.module_from_spec(spec)
    sys.modules["database.wrapped"] = mod
    spec.loader.exec_module(mod)
    return mod


wrapped = _load()


def _snap(exists):
    snap = MagicMock()
    snap.exists = exists
    return snap


def _wire(exists=True, update_exc=None):
    ref = MagicMock()
    ref.get.return_value = _snap(exists)
    if update_exc is not None:
        ref.update.side_effect = update_exc
    col = MagicMock()
    col.document.return_value = ref
    user_ref = MagicMock()
    user_ref.collection.return_value = col
    db_mock = MagicMock()
    db_mock.collection.return_value.document.return_value = user_ref
    return db_mock, ref


def test_missing_doc_returns_false():
    db_mock, ref = _wire(exists=False)
    with patch.object(wrapped, "db", db_mock):
        assert wrapped.update_wrapped_status("u1", 2025, "processing") is False
        assert wrapped.update_wrapped_progress("u1", 2025, {"pct": 0.1}) is False
    ref.update.assert_not_called()


def test_deleted_mid_update_returns_false():
    db_mock, ref = _wire(exists=True, update_exc=_NotFound("Concurrent deletion"))
    with patch.object(wrapped, "db", db_mock):
        assert wrapped.update_wrapped_status("u1", 2025, "done") is False
        assert wrapped.update_wrapped_progress("u1", 2025, {"pct": 0.5}) is False


def test_happy_path_returns_true():
    db_mock, ref = _wire(exists=True)
    with patch.object(wrapped, "db", db_mock):
        assert wrapped.update_wrapped_status("u1", 2025, "done") is True
        assert wrapped.update_wrapped_progress("u1", 2025, {"pct": 1.0}) is True
    assert ref.update.call_count == 2
