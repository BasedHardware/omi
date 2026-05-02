"""Tests for per-user / per-integration preferences (two-way-sync toggle).

Covers:
- get defaults to None
- set_integration_pref creates a doc with merged fields + updated_at
- set_integration_pref merges (does not blow away) on second call
- is_two_way_sync_enabled defaults to False (hard product rule)
- After set with two_way_sync_enabled=True, helper returns True
"""

import importlib.util
import os
import sys
import types
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)


def _stub_module(name):
    mod = types.ModuleType(name)
    sys.modules[name] = mod
    return mod


def _stub_package(name):
    mod = types.ModuleType(name)
    mod.__path__ = []
    sys.modules[name] = mod
    return mod


# ---------------------------------------------------------------------------
# Tiny in-memory Firestore stub focused on doc.get / set(merge=True)
# ---------------------------------------------------------------------------


class _Snap:
    def __init__(self, data, exists):
        self._data = dict(data) if data else {}
        self.exists = exists

    def to_dict(self):
        return dict(self._data)


class _DocRef:
    def __init__(self, store, key):
        self._store = store
        self._key = key

    def get(self):
        if self._key in self._store:
            return _Snap(self._store[self._key], True)
        return _Snap(None, False)

    def set(self, data, merge=False):
        if merge and self._key in self._store:
            self._store[self._key].update(data)
        else:
            self._store[self._key] = dict(data)


class _Coll:
    def __init__(self, store, prefix):
        self._store = store
        self._prefix = prefix

    def document(self, doc_id):
        return _DocRef(self._store, f"{self._prefix}/{doc_id}")


class _UserRef:
    def __init__(self, store, uid):
        self._store = store
        self._uid = uid

    def collection(self, name):
        return _Coll(self._store, f"users/{self._uid}/{name}")


class _DB:
    def __init__(self):
        self._store = {}

    def collection(self, name):
        # Only `users` is used in this module
        if name != 'users':
            raise AssertionError(f"unexpected collection {name}")
        return self

    def document(self, uid):
        return _UserRef(self._store, uid)


# ---------------------------------------------------------------------------
# Stubs
# ---------------------------------------------------------------------------

_stub_package("google")
_stub_package("google.cloud")
gc_fire = _stub_module("google.cloud.firestore")
gc_fire.Client = MagicMock()
gc_fire.DocumentReference = object  # type alias placeholder
gc_fire_v1 = _stub_module("google.cloud.firestore_v1")
gc_fire_v1.FieldFilter = MagicMock()

_stub_package("database")
sys.modules["database"].__path__ = [str(BACKEND_DIR / "database")]

fake_db = _DB()
client_mod = _stub_module("database._client")
client_mod.db = fake_db


def _load():
    spec = importlib.util.spec_from_file_location(
        "database.integration_prefs", str(BACKEND_DIR / "database" / "integration_prefs.py")
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["database.integration_prefs"] = mod
    spec.loader.exec_module(mod)
    return mod


prefs = _load()


@pytest.fixture(autouse=True)
def _reset_db():
    fake_db._store.clear()
    yield


class TestGetIntegrationPref:
    def test_returns_none_when_missing(self):
        assert prefs.get_integration_pref("uid-1", "nooto-jira") is None

    def test_returns_doc_after_set(self):
        prefs.set_integration_pref("uid-1", "nooto-jira", two_way_sync_enabled=True)
        result = prefs.get_integration_pref("uid-1", "nooto-jira")
        assert result is not None
        assert result["two_way_sync_enabled"] is True
        assert result["integration_id"] == "nooto-jira"
        assert "updated_at" in result


class TestSetIntegrationPref:
    def test_set_creates_doc(self):
        prefs.set_integration_pref("uid-1", "nooto-jira", two_way_sync_enabled=True)
        assert "users/uid-1/integration_prefs/nooto-jira" in fake_db._store
        stored = fake_db._store["users/uid-1/integration_prefs/nooto-jira"]
        assert stored["two_way_sync_enabled"] is True
        assert isinstance(stored["updated_at"], datetime)

    def test_set_merges_partial_updates(self):
        prefs.set_integration_pref("uid-1", "nooto-jira", two_way_sync_enabled=True, foo="bar")
        prefs.set_integration_pref("uid-1", "nooto-jira", two_way_sync_enabled=False)

        stored = fake_db._store["users/uid-1/integration_prefs/nooto-jira"]
        assert stored["two_way_sync_enabled"] is False
        assert stored["foo"] == "bar", "merge should preserve unrelated fields"

    def test_set_with_no_updates_is_noop(self):
        result = prefs.set_integration_pref("uid-1", "nooto-jira")
        # Should not have written anything
        assert "users/uid-1/integration_prefs/nooto-jira" not in fake_db._store
        assert result == {"integration_id": "nooto-jira"}


class TestIsTwoWaySyncEnabled:
    def test_defaults_to_false_when_no_doc(self):
        assert prefs.is_two_way_sync_enabled("uid-1", "nooto-jira") is False

    def test_defaults_to_false_when_field_absent(self):
        prefs.set_integration_pref("uid-1", "nooto-jira", some_other_field="x")
        assert prefs.is_two_way_sync_enabled("uid-1", "nooto-jira") is False

    def test_true_after_opt_in(self):
        prefs.set_integration_pref("uid-1", "nooto-jira", two_way_sync_enabled=True)
        assert prefs.is_two_way_sync_enabled("uid-1", "nooto-jira") is True

    def test_false_after_opt_out(self):
        prefs.set_integration_pref("uid-1", "nooto-jira", two_way_sync_enabled=True)
        prefs.set_integration_pref("uid-1", "nooto-jira", two_way_sync_enabled=False)
        assert prefs.is_two_way_sync_enabled("uid-1", "nooto-jira") is False

    def test_separate_users_independent(self):
        prefs.set_integration_pref("uid-A", "nooto-jira", two_way_sync_enabled=True)
        assert prefs.is_two_way_sync_enabled("uid-A", "nooto-jira") is True
        assert prefs.is_two_way_sync_enabled("uid-B", "nooto-jira") is False
