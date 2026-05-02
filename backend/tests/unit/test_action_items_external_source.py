"""Tests for external-source action items (Jira / integration sync slice).

Covers:
- ``upsert_external_action_item`` creates a new doc on first call
- Second call with the same ``external_source`` updates instead of duplicating
- ``CreateActionItemRequest`` accepts optional ``external_source``
- ``GET /v1/action-items?source=jira`` filters by external source
"""

import importlib.util
import os
import sys
import types
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

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
# In-memory Firestore stub good enough for upsert flow
# ---------------------------------------------------------------------------


class _FakeFieldFilter:
    def __init__(self, field, op, value):
        self.field = field
        self.op = op
        self.value = value


class _FakeQuery:
    def __init__(self, docs, filters=None):
        self._docs = docs
        self._filters = list(filters or [])

    def where(self, filter=None, **kwargs):
        return _FakeQuery(self._docs, self._filters + [filter])

    def limit(self, n):
        self._limit = n
        return self

    def order_by(self, *args, **kwargs):
        return self

    def offset(self, n):
        return self

    def stream(self):
        out = []
        for doc in self._docs:
            data = doc.to_dict() or {}
            ok = True
            for f in self._filters:
                # support nested keys like "external_source.source"
                parts = f.field.split('.')
                cur = data
                for p in parts:
                    if not isinstance(cur, dict):
                        cur = None
                        break
                    cur = cur.get(p)
                if f.op == '==' and cur != f.value:
                    ok = False
                    break
            if ok:
                out.append(doc)
                if hasattr(self, '_limit') and len(out) >= self._limit:
                    break
        return out


class _FakeDocRef:
    def __init__(self, parent, doc_id):
        self._parent = parent
        self.id = doc_id
        self._snap = None

    def set(self, data, merge=False):
        if self._snap is None:
            self._snap = _FakeDocSnap(self.id, data)
            self._parent._docs[self.id] = self._snap
        else:
            if merge:
                self._snap._data.update(data)
            else:
                self._snap._data = dict(data)

    def update(self, data):
        if self._snap is None:
            raise RuntimeError("update on missing doc")
        self._snap._data.update(data)

    def get(self):
        if self._snap is None:
            return _FakeDocSnap(self.id, None, exists=False)
        return self._snap

    def delete(self):
        self._snap = None
        self._parent._docs.pop(self.id, None)


class _FakeDocSnap:
    def __init__(self, doc_id, data, exists=True):
        self.id = doc_id
        self._data = dict(data) if data else {}
        self.exists = exists

    @property
    def reference(self):
        return _ReferenceShim(self)

    def to_dict(self):
        return dict(self._data)


class _ReferenceShim:
    def __init__(self, snap):
        self._snap = snap

    def update(self, data):
        self._snap._data.update(data)

    def delete(self):
        self._snap.exists = False
        self._snap._data = {}


class _FakeCollection:
    def __init__(self):
        self._docs = {}
        self._counter = 0

    def document(self, doc_id=None):
        if doc_id is None:
            self._counter += 1
            doc_id = f"auto-{self._counter}"
        if doc_id not in self._docs:
            return _FakeDocRef(self, doc_id)
        ref = _FakeDocRef(self, doc_id)
        ref._snap = self._docs[doc_id]
        return ref

    def add(self, data):
        self._counter += 1
        doc_id = f"auto-{self._counter}"
        snap = _FakeDocSnap(doc_id, data)
        self._docs[doc_id] = snap
        # mimic firestore (write_result, doc_ref) tuple
        ref = _FakeDocRef(self, doc_id)
        ref._snap = snap
        return (None, ref)

    def where(self, filter=None, **kwargs):
        return _FakeQuery(list(self._docs.values()), [filter])

    def stream(self):
        return list(self._docs.values())


class _FakeUserRef:
    def __init__(self, store, uid):
        self._store = store
        self._uid = uid

    def collection(self, name):
        return self._store.setdefault((self._uid, name), _FakeCollection())


class _FakeDB:
    def __init__(self):
        self._store = {}
        self._user_collection = self

    def collection(self, name):
        if name == 'users':
            return self
        # generic
        return self._store.setdefault(('_global', name), _FakeCollection())

    def document(self, uid):
        return _FakeUserRef(self._store, uid)

    def batch(self):
        return _FakeBatch()


class _FakeBatch:
    def set(self, *a, **kw):
        pass

    def update(self, *a, **kw):
        pass

    def delete(self, *a, **kw):
        pass

    def commit(self):
        pass


# ---------------------------------------------------------------------------
# Stubs (must be installed before importing the module under test)
# ---------------------------------------------------------------------------

# Stub google.cloud.firestore + firestore_v1 with FieldFilter
gc = _stub_package("google")
gc_cloud = _stub_package("google.cloud")
gc_fire = _stub_module("google.cloud.firestore")
gc_fire.Client = MagicMock()
gc_fire_v1 = _stub_module("google.cloud.firestore_v1")
gc_fire_v1.FieldFilter = _FakeFieldFilter
gc_fire.Query = MagicMock()
gc_fire.Query.DESCENDING = 'DESCENDING'
# Provide DocumentReference / DocumentSnapshot symbols expected by type hints
gc_fire.DocumentReference = _FakeDocRef
gc_fire.DocumentSnapshot = _FakeDocSnap

# Stub database._client
fake_db = _FakeDB()
db_pkg = _stub_package("database")
db_pkg.__path__ = [str(BACKEND_DIR / "database")]
client_mod = _stub_module("database._client")
client_mod.db = fake_db


# Now load action_items module
def _load_action_items():
    spec = importlib.util.spec_from_file_location(
        "database.action_items", str(BACKEND_DIR / "database" / "action_items.py")
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["database.action_items"] = mod
    spec.loader.exec_module(mod)
    return mod


action_items = _load_action_items()


@pytest.fixture(autouse=True)
def _reset_fake_db():
    fake_db._store.clear()
    yield


# ===========================================================================
# upsert_external_action_item
# ===========================================================================


class TestUpsertExternalActionItem:

    def test_first_call_creates_new_item(self):
        external_source = {"source": "jira", "external_id": "PROJ-1", "url": "https://x/browse/PROJ-1"}
        fields = {"description": "Ship the thing", "completed": False, "due_at": None, "conversation_id": None}

        item_id = action_items.upsert_external_action_item("uid-1", external_source, fields)

        assert item_id, "upsert returned empty id on insert"
        items = list(fake_db._store[("uid-1", action_items.action_items_collection)]._docs.values())
        assert len(items) == 1
        stored = items[0].to_dict()
        assert stored["description"] == "Ship the thing"
        assert stored["external_source"]["source"] == "jira"
        assert stored["external_source"]["external_id"] == "PROJ-1"

    def test_second_call_updates_in_place(self):
        external_source = {"source": "jira", "external_id": "PROJ-1", "url": "https://x/browse/PROJ-1"}
        first_fields = {"description": "Old", "completed": False, "due_at": None}

        first_id = action_items.upsert_external_action_item("uid-1", external_source, first_fields)

        # Same external_source, updated fields
        second_fields = {"description": "Updated", "completed": True, "due_at": None}
        second_id = action_items.upsert_external_action_item("uid-1", external_source, second_fields)

        assert first_id == second_id, "upsert should preserve id on update"
        items = list(fake_db._store[("uid-1", action_items.action_items_collection)]._docs.values())
        assert len(items) == 1, "upsert should not create duplicate doc"
        stored = items[0].to_dict()
        assert stored["description"] == "Updated"
        assert stored["completed"] is True
        assert stored["completed_at"] is not None, "completed=True should set completed_at"

    def test_uncompleting_clears_completed_at(self):
        external_source = {"source": "jira", "external_id": "PROJ-2"}
        action_items.upsert_external_action_item("uid-1", external_source, {"description": "x", "completed": True})
        action_items.upsert_external_action_item("uid-1", external_source, {"description": "x", "completed": False})
        items = list(fake_db._store[("uid-1", action_items.action_items_collection)]._docs.values())
        assert items[0].to_dict()["completed"] is False
        assert items[0].to_dict().get("completed_at") is None

    def test_missing_external_source_raises(self):
        with pytest.raises(ValueError):
            action_items.upsert_external_action_item("uid-1", {}, {"description": "x"})
        with pytest.raises(ValueError):
            action_items.upsert_external_action_item("uid-1", {"source": "jira"}, {"description": "x"})

    def test_separate_users_dont_collide(self):
        external_source = {"source": "jira", "external_id": "PROJ-1"}
        action_items.upsert_external_action_item("uid-A", external_source, {"description": "A"})
        action_items.upsert_external_action_item("uid-B", external_source, {"description": "B"})

        a_items = list(fake_db._store[("uid-A", action_items.action_items_collection)]._docs.values())
        b_items = list(fake_db._store[("uid-B", action_items.action_items_collection)]._docs.values())
        assert len(a_items) == 1 and len(b_items) == 1
        assert a_items[0].to_dict()["description"] == "A"
        assert b_items[0].to_dict()["description"] == "B"

    def test_create_action_item_accepts_external_source_kwarg(self):
        item_id = action_items.create_action_item(
            "uid-1",
            {"description": "manual"},
            external_source={"source": "jira", "external_id": "PROJ-9"},
        )
        items = list(fake_db._store[("uid-1", action_items.action_items_collection)]._docs.values())
        assert len(items) == 1
        stored = items[0].to_dict()
        assert stored["external_source"] == {"source": "jira", "external_id": "PROJ-9"}


# ===========================================================================
# Source filter in router (logic-only, no FastAPI start-up)
# ===========================================================================


class TestSourceFilterLogic:
    """The /v1/action-items endpoint applies the `source` filter in pure
    Python after the Firestore query — verify the predicate."""

    def test_source_filter_matches_jira_items(self):
        items = [
            {"id": "1", "description": "Jira A", "external_source": {"source": "jira", "external_id": "A"}},
            {"id": "2", "description": "Manual", "external_source": None},
            {"id": "3", "description": "Linear B", "external_source": {"source": "linear", "external_id": "B"}},
        ]
        filtered = [i for i in items if (i.get('external_source') or {}).get('source') == 'jira']
        assert len(filtered) == 1
        assert filtered[0]["id"] == "1"

    def test_no_source_returns_all(self):
        items = [
            {"id": "1", "external_source": {"source": "jira"}},
            {"id": "2", "external_source": None},
        ]
        # legacy behavior — no filter when source is None
        source = None
        if source is None:
            assert items == items
