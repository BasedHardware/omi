"""update_advice must return None (404) when the advice is deleted mid-update, not crash with a 500.

PATCH /v1/advice/{advice_id} -> update_advice checks the document exists, applies the update, then
re-reads it to return the fresh value. Two concurrent-deletion windows turned that into a 500:
  1. Deleted between the existence check and ref.update(...) -> Firestore update() raises NotFound.
  2. Deleted between the update and the re-read -> ref.get().to_dict() is None, so result['id'] = ...
     raised TypeError.
The router treats a None return as a 404, so both races should yield 404, not an unhandled 500. The
function now returns None in both cases. These cover the pure database-function behavior.

Since the fix routes the re-read through parse_snapshot_or_none(Advice, ...), the stored payload must
be Advice-valid for the happy path — and a stored doc that validates malformed after a successful
update now yields None (PATCH -> 404), which the last test pins.
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


def _load(name, path):
    # Reuse an already-imported module — a sibling test file may have
    # imported the real package first; loading a second copy splits class
    # identity (isinstance fails across the two Advice classes).
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


class _NotFound(Exception):
    """Stand-in when google.api_core is absent; under a real env the
    module under test binds the real NotFound — see _raise_not_found."""


# Stub only the heavy leaves, and only when the real package is NOT
# importable — in the pinned CI env these exist for real, and a stub
# would poison sibling modules that import the same names.
for _p in ["google", "google.cloud", "google.api_core", "database", "models"]:
    _pkg(_p)


def _missing(name):
    try:
        return importlib.util.find_spec(name) is None
    except (ModuleNotFoundError, ValueError):
        return True


if _missing("google.api_core.exceptions"):
    _mod("google.api_core.exceptions", NotFound=_NotFound)
if _missing("google.cloud.firestore"):
    _mod("google.cloud.firestore", SERVER_TIMESTAMP=MagicMock(), Query=MagicMock())
    _mod("google.cloud.firestore_v1.base_query", FieldFilter=MagicMock())
# The shared client stub (full seam surface, not a bare MagicMock) — other
# modules import document_id_from_seed/get_firestore_client/etc from
# database._client; a bare stub would poison their imports mid-session.
sys.path.insert(0, str(BACKEND_DIR))
from tests.unit.memory_import_isolation import install_database_client_stub  # noqa: E402

install_database_client_stub()

# read_boundary binds utils.observability.fallback eagerly when importable —
# from backend/ it resolves and drags in metrics deps. Pin the recorder to a
# no-op so the drop path stays pure-validation under test.
_pkg("utils")
_pkg("utils.observability")
_mod("utils.observability.fallback", record_fallback=MagicMock())

_advice_models = _load("models.advice", BACKEND_DIR / "models" / "advice.py")
_boundary = _load("database.read_boundary", BACKEND_DIR / "database" / "read_boundary.py")
Advice = _advice_models.Advice
advice = _load("database.advice", BACKEND_DIR / "database" / "advice.py")


def _snap(exists, data=None):
    snap = MagicMock()
    snap.exists = exists
    snap.id = "adv1"
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


def _advice_doc(**over):
    doc = {
        "content": "try a walk",
        "category": "other",
        "confidence": 0.8,
        "created_at": "2026-10-14T00:00:00Z",
        "updated_at": "2026-10-14T00:00:00Z",
        "is_read": False,
    }
    doc.update(over)
    return doc


def test_missing_advice_returns_none():
    # The existing existence check: a UID/advice_id with no document returns None (404), no update.
    col, ref = _wire([_snap(False)])
    with patch.object(advice, "_user_col", return_value=col):
        assert advice.update_advice("u", "adv1", is_read=True) is None
    ref.update.assert_not_called()


def test_deleted_before_update_returns_none():
    # Deleted between the existence check and the update: Firestore update() raises NotFound, which
    # must become a None return (404), not a propagated 500. Raised via an
    # instance of the class advice.py itself bound — real or stub depending
    # on the env.
    col, ref = _wire([_snap(True)], update_exc=advice.NotFound("deleted mid-update"))
    with patch.object(advice, "_user_col", return_value=col):
        assert advice.update_advice("u", "adv1", is_read=True) is None


def test_deleted_after_update_returns_none():
    # Deleted between the update and the re-read: to_dict() is None, which must become a None return
    # instead of a TypeError on result['id'].
    col, ref = _wire([_snap(True), _snap(False, None)])
    with patch.object(advice, "_user_col", return_value=col):
        assert advice.update_advice("u", "adv1", is_dismissed=True) is None


def test_happy_path_returns_advice_model():
    # The stored doc is a real Advice payload; the re-read parses into a model.
    col, ref = _wire([_snap(True), _snap(True, _advice_doc())])
    with patch.object(advice, "_user_col", return_value=col):
        result = advice.update_advice("u", "adv1", is_read=True)
    assert isinstance(result, Advice)
    assert result.id == "adv1"
    assert result.content == "try a walk"


def test_poisoned_after_update_returns_none():
    # A stored doc that becomes Advice-invalid after a successful update must
    # surface as None (PATCH -> 404), not a response-model 500 — the exact
    # contract change the read-boundary rerouting introduces for write paths.
    bad = _advice_doc()
    del bad["content"]  # required field missing — malformed stored doc
    col, ref = _wire([_snap(True), _snap(True, bad)])
    with patch.object(advice, "_user_col", return_value=col):
        assert advice.update_advice("u", "adv1", is_read=True) is None
    ref.update.assert_called_once()
