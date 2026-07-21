"""Hermetic contract tests for the server-side Omi capture archive filter."""

import os
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import MagicMock

import pytest

from testing.import_isolation import AutoMockModule, load_module_fresh, stub_modules

_BACKEND = Path(__file__).resolve().parents[2]


class _FieldFilter:
    def __init__(self, field_path, op_string, value):
        self.field_path = field_path
        self.op_string = op_string
        self.value = value


class _Snapshot:
    update_time = None

    def __init__(self, row):
        self._row = row

    def to_dict(self):
        return dict(self._row)


class _CountResult:
    def __init__(self, value):
        self.value = value


class _Query:
    def __init__(self, rows):
        self._rows = rows
        self.filters = []
        self.events = []
        self._order_field = None
        self._limit = None
        self._offset = 0

    def where(self, *, filter):
        self.filters.append((filter.field_path, filter.op_string, filter.value))
        self.events.append(("where", filter.field_path, filter.op_string, filter.value))
        return self

    def order_by(self, field_path, direction=None):
        self._order_field = field_path
        self.events.append(("order_by", field_path, direction))
        return self

    def limit(self, value):
        self._limit = value
        self.events.append(("limit", value))
        return self

    def offset(self, value):
        self._offset = value
        self.events.append(("offset", value))
        return self

    def _matching_rows(self):
        rows = list(self._rows)
        for field_path, operator, expected in self.filters:
            if operator == "==":
                rows = [row for row in rows if row.get(field_path) == expected]
            elif operator == "in":
                rows = [row for row in rows if row.get(field_path) in expected]
            else:  # pragma: no cover - this test contract only uses equality and membership.
                raise AssertionError(f"unexpected Firestore operator: {operator}")
        if self._order_field:
            rows.sort(key=lambda row: row[self._order_field], reverse=True)
        return rows

    def stream(self):
        self.events.append(("stream",))
        rows = self._matching_rows()
        if self._limit is not None:
            rows = rows[self._offset : self._offset + self._limit]
        return [_Snapshot(row) for row in rows]

    def count(self):
        self.events.append(("count",))
        return SimpleNamespace(get=lambda: [[_CountResult(len(self._matching_rows()))]])


class _Firestore:
    def __init__(self, rows):
        self.rows = rows
        self.queries = []

    def document(self, uid):
        assert uid == "user-1"
        return self

    def collection(self, name):
        assert name in {"users", "conversations"}
        if name == "users":
            return self
        query = _Query(self.rows)
        self.queries.append(query)
        return query


def _decorator(*_args, **_kwargs):
    return lambda func: func


@pytest.fixture
def conversations_db():
    """Load the production query function against a minimal in-memory Firestore seam."""
    firestore = _Firestore([])

    google = ModuleType("google")
    google.__path__ = []
    google_cloud = ModuleType("google.cloud")
    google_cloud.__path__ = []
    google_api_core = ModuleType("google.api_core")
    google_api_core.__path__ = []

    firestore_module = ModuleType("google.cloud.firestore")
    firestore_module.Query = SimpleNamespace(DESCENDING="DESCENDING")
    firestore_v1_module = ModuleType("google.cloud.firestore_v1")
    firestore_v1_module.FieldFilter = _FieldFilter
    exceptions_module = ModuleType("google.api_core.exceptions")
    exceptions_module.AlreadyExists = type("AlreadyExists", (Exception,), {})
    exceptions_module.Conflict = type("Conflict", (Exception,), {})
    exceptions_module.NotFound = type("NotFound", (Exception,), {})

    database_client = ModuleType("database._client")
    database_client.db = firestore
    database_client.get_firestore_client = MagicMock()
    database_helpers = ModuleType("database.helpers")
    database_helpers.set_data_protection_level = MagicMock()
    database_helpers.prepare_for_write = _decorator
    database_helpers.prepare_for_read = _decorator
    database_helpers.with_photos = _decorator

    models = ModuleType("models")
    models.__path__ = []
    utils = ModuleType("utils")
    utils.__path__ = []
    utils_other = ModuleType("utils.other")
    utils_other.__path__ = []

    fakes = {
        "google": google,
        "google.cloud": google_cloud,
        "google.cloud.firestore": firestore_module,
        "google.cloud.firestore_v1": firestore_v1_module,
        "google.api_core": google_api_core,
        "google.api_core.exceptions": exceptions_module,
        "database._client": database_client,
        "database.helpers": database_helpers,
        "database.users": AutoMockModule("database.users"),
        "models": models,
        "models.audio_file": AutoMockModule("models.audio_file"),
        "models.conversation_enums": AutoMockModule("models.conversation_enums"),
        "models.conversation_photo": AutoMockModule("models.conversation_photo"),
        "models.transcript_segment": AutoMockModule("models.transcript_segment"),
        "utils": utils,
        "utils.encryption": AutoMockModule("utils.encryption"),
        "utils.other": utils_other,
        "utils.other.hume": AutoMockModule("utils.other.hume"),
        "utils.other.storage": AutoMockModule("utils.other.storage"),
    }

    with stub_modules(fakes):
        module = load_module_fresh(
            "database.conversations",
            os.path.join(str(_BACKEND), "database", "conversations.py"),
        )
        yield module, firestore


def _conversation(conversation_id, *, created_at, source, status="completed", discarded=False):
    return {
        "id": conversation_id,
        "created_at": created_at,
        "source": source,
        "status": status,
        "discarded": discarded,
    }


def test_archive_filter_precedes_pagination_and_matches_count(conversations_db):
    module, firestore = conversations_db
    firestore.rows = [
        _conversation("discarded-omi", created_at=8, source="omi", discarded=True),
        _conversation("failed-omi", created_at=7, source="omi", status="failed"),
        _conversation("friend-new", created_at=6, source="friend"),
        _conversation("desktop-next", created_at=5, source="desktop"),
        _conversation("omi-new", created_at=4, source="omi", status="processing"),
        _conversation("friend-old", created_at=3, source="friend"),
        _conversation("omi-middle", created_at=2, source="omi"),
        _conversation("omi-old", created_at=1, source="omi"),
    ]

    query = dict(
        uid="user-1",
        limit=2,
        include_discarded=False,
        statuses=["processing", "completed"],
        sources=["omi"],
    )
    first_page = module.get_conversations_without_photos(offset=0, **query)
    second_page = module.get_conversations_without_photos(offset=2, **query)
    count = module.get_conversations_count(
        "user-1", include_discarded=False, statuses=["processing", "completed"], sources=["omi"]
    )

    assert [row["id"] for row in first_page] == ["omi-new", "omi-middle"]
    assert [row["id"] for row in second_page] == ["omi-old"]
    assert count == 3

    list_query = firestore.queries[0]
    assert list_query.filters == [
        ("discarded", "==", False),
        ("source", "==", "omi"),
        ("status", "in", ["processing", "completed"]),
    ]
    assert [event[0] for event in list_query.events] == [
        "where",
        "where",
        "where",
        "order_by",
        "limit",
        "offset",
        "stream",
    ]


def test_sources_honor_legacy_include_discarded_default(conversations_db):
    module, firestore = conversations_db
    firestore.rows = [
        _conversation("discarded-omi", created_at=3, source="omi", discarded=True),
        _conversation("friend", created_at=2, source="friend"),
        _conversation("omi", created_at=1, source="omi"),
    ]

    results = module.get_conversations_without_photos(
        "user-1",
        limit=10,
        include_discarded=True,
        statuses=["processing", "completed"],
        sources=["omi"],
    )

    assert [row["id"] for row in results] == ["discarded-omi", "omi"]
    assert firestore.queries[0].filters == [
        ("source", "==", "omi"),
        ("status", "in", ["processing", "completed"]),
    ]


def test_sources_omitted_preserves_legacy_filter_chain(conversations_db):
    module, firestore = conversations_db
    firestore.rows = [
        _conversation("discarded-omi", created_at=3, source="omi", discarded=True),
        _conversation("friend", created_at=2, source="friend"),
        _conversation("omi", created_at=1, source="omi"),
    ]

    results = module.get_conversations_without_photos(
        "user-1", limit=10, include_discarded=True, statuses=["processing", "completed"]
    )

    assert [row["id"] for row in results] == ["discarded-omi", "friend", "omi"]
    assert firestore.queries[0].filters == [("status", "in", ["processing", "completed"])]
