"""Phase 2 sections 2+3: REST incremental sync/export and REST consolidation.

Pins:
- the action-item ``(updated_at ASC, __name__ ASC)`` incremental feed query
  shape, equal-timestamp tie-breaks, cursor continuation, tombstone emission,
  and the ``updated_at`` watermark on every emitted row;
- REST ``updated_since`` truthfulness: action items serve the real keyset feed
  while conversations and memories return a permanent HTTP 400
  ``incremental_sync_unsupported`` capability gate — no ``Retry-After`` —
  instead of silently dropping updates;
- REST list bodies stay top-level JSON arrays (the contract the desktop client
  and the ``mcp/`` stdio package decode), with pagination state only in the
  ``X-Next-Cursor`` response header;
- released-client fields and statuses (``apps_results``, transcript
  ``speaker_name``, POST memory shape, 400/402/403/404/429) survive the
  delegation to shared MCP handler cores.

``routers.mcp`` imports cleanly in this environment, so REST tests use real
module imports plus ``monkeypatch.setattr`` on the shared-handler seams — the
sanctioned pattern from ``backend/docs/test_isolation.md``.
"""

import importlib
import sys
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import os

os.environ.setdefault('OPENAI_API_KEY', 'sk-test-not-real')
os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from routers import mcp as rest
from utils.mcp_server.errors import ToolExecutionError
from utils.mcp_server.handlers import action_items as action_items_handler

UID = "uid-sync"
NOW = datetime(2026, 6, 11, tzinfo=timezone.utc)
SINCE = datetime(2026, 6, 1, tzinfo=timezone.utc)


def _import_real_module(name):
    """Return the real module for ``name``, evicting sibling-file stubs.

    Several sibling test files install ``sys.modules`` stubs at collection and
    never restore them; a stub advertises itself by defining ``__getattr__`` on
    the module class (real modules never do).
    """
    module = sys.modules.get(name)
    if module is not None and "__getattr__" in type(module).__dict__:
        del sys.modules[name]
        parent_name, _, child_name = name.rpartition(".")
        parent = sys.modules.get(parent_name)
        if parent is not None and getattr(parent, child_name, None) is module:
            delattr(parent, child_name)
    return importlib.import_module(name)


def _import_real_firestore():
    for name in [
        candidate
        for candidate in list(sys.modules)
        if candidate == "google" or candidate.startswith("google.")
        if "firestore" in candidate or candidate in ("google", "google.cloud")
    ]:
        module = sys.modules.get(name)
        if module is not None and "__getattr__" in type(module).__dict__:
            del sys.modules[name]
    return _import_real_module("google.cloud.firestore")


@pytest.fixture
def sync_db():
    """The real incremental-sync module with a real Firestore SDK import."""
    _import_real_firestore()
    _import_real_module("database._client")
    _import_real_module("database.action_items")
    return _import_real_module("database.action_item_sync")


class _FakeDoc:
    def __init__(self, doc_id, data):
        self.id = doc_id
        self._data = dict(data)

    def to_dict(self):
        return dict(self._data)


class _FakeDocRef:
    def __init__(self, doc_id):
        self.id = doc_id


class _RecordingQuery:
    """Chainable query fake that records every builder call in ``events``."""

    def __init__(self, docs, events):
        self._docs = docs
        self._events = events

    def where(self, filter=None, **kwargs):
        self._events.append(("where", filter))
        return self

    def order_by(self, field, direction=None):
        self._events.append(("order_by", field, direction))
        return self

    def start_after(self, position):
        self._events.append(("start_after", position))
        return self

    def select(self, fields):
        self._events.append(("select", list(fields)))
        return self

    def limit(self, count):
        self._events.append(("limit", count))
        return self

    def stream(self):
        self._events.append(("stream",))
        return iter(self._docs)


class _ActionItemsCollection(_RecordingQuery):
    def __init__(self, docs, events):
        super().__init__(docs, events)
        self.requested_doc_ids = []

    def document(self, doc_id):
        self.requested_doc_ids.append(doc_id)
        return _FakeDocRef(doc_id)


class _FakeUserDoc:
    def __init__(self, leaf):
        self._leaf = leaf

    def collection(self, name):
        assert name == "action_items"
        return self._leaf


class _FakeUsersCollection:
    def __init__(self, leaf):
        self._leaf = leaf

    def document(self, uid):
        return _FakeUserDoc(self._leaf)


class _FakeClient:
    def __init__(self, leaf):
        self._leaf = leaf

    def collection(self, name):
        assert name == "users"
        return _FakeUsersCollection(self._leaf)


def _sync_client(docs):
    events = []
    leaf = _ActionItemsCollection(docs, events)
    return _FakeClient(leaf), events, leaf


def _item(doc_id, updated_at, **extra):
    data = {
        "description": f"task {doc_id}",
        "completed": False,
        "created_at": NOW - timedelta(days=2),
        "updated_at": updated_at,
    }
    data.update(extra)
    return _FakeDoc(doc_id, data)


class TestActionItemSyncQueryShape:
    """The authoritative Firestore query shape must not drift."""

    def test_unfiltered_query_shape(self, sync_db):
        firestore = _import_real_firestore()
        docs = [_item("a1", NOW)]
        client, events, _ = _sync_client(docs)

        items, resume = sync_db.get_action_items_sync_page(UID, limit=10, firestore_client=client)

        assert [i["id"] for i in items] == ["a1"]
        assert resume is None
        kinds = [e[0] for e in events]
        assert kinds == ["order_by", "order_by", "select", "limit", "stream"]
        assert events[0] == ("order_by", "updated_at", firestore.Query.ASCENDING)
        assert events[1] == ("order_by", "__name__", firestore.Query.ASCENDING)
        selected = events[2][1]
        assert "updated_at" in selected and "deleted" in selected
        assert events[3] == ("limit", 11)

    def test_updated_since_filter_shape(self, sync_db):
        client, events, _ = _sync_client([])
        items, resume = sync_db.get_action_items_sync_page(UID, updated_since=SINCE, limit=5, firestore_client=client)
        assert items == [] and resume is None
        kind, field_filter = events[0]
        assert kind == "where"
        assert field_filter.field_path == "updated_at"
        assert field_filter.op_string == ">="
        assert field_filter.value == SINCE

    def test_cursor_start_after_uses_document_reference(self, sync_db):
        client, events, leaf = _sync_client([])
        sync_db.get_action_items_sync_page(
            UID, updated_since=SINCE, after=(NOW, "a1"), limit=5, firestore_client=client
        )
        kind, position = events[3]
        assert kind == "start_after"
        assert set(position.keys()) == {"updated_at", "__name__"}
        assert position["updated_at"] == NOW
        # The resume document must be a reference produced by the collection,
        # not a bare string id (production precedent in
        # utils/memory/product_memory_read_service.py).
        assert leaf.requested_doc_ids == ["a1"]
        assert position["__name__"].id == "a1"

    @pytest.mark.parametrize("after", [(None, "a1"), (NOW, ""), (NOW, "a/b")])
    def test_invalid_cursor_position_rejected_before_query(self, sync_db, after):
        client, events, _ = _sync_client([])
        with pytest.raises(ValueError):
            sync_db.get_action_items_sync_page(UID, after=after, limit=5, firestore_client=client)
        assert ("stream",) not in events

    def test_equal_timestamp_tiebreak_and_lookahead_resume(self, sync_db):
        # Three rows sharing one timestamp must paginate by document id with no
        # duplicates and no skipped rows across the page boundary.
        docs = [_item("a1", NOW), _item("a2", NOW), _item("a3", NOW)]

        client1, _, _ = _sync_client(docs)
        items1, resume1 = sync_db.get_action_items_sync_page(UID, limit=2, firestore_client=client1)
        assert [i["id"] for i in items1] == ["a1", "a2"]
        # Resume is the last EMITTED row's raw position; the lookahead row is
        # re-fetched by start_after rather than skipped.
        assert resume1 == (NOW, "a2")

        client2, events2, _ = _sync_client([_item("a3", NOW)])
        items2, resume2 = sync_db.get_action_items_sync_page(UID, after=resume1, limit=2, firestore_client=client2)
        kind, position = events2[2]
        assert kind == "start_after"
        assert position["updated_at"] == NOW
        assert position["__name__"].id == "a2"
        assert [i["id"] for i in items2] == ["a3"]
        assert resume2 is None
        assert not {i["id"] for i in items1} & {i["id"] for i in items2}

    def test_ascending_order_across_timestamps(self, sync_db):
        older, newer = NOW - timedelta(hours=1), NOW
        docs = [_item("a1", older), _item("a2", newer)]
        client, _, _ = _sync_client(docs)
        items, _ = sync_db.get_action_items_sync_page(UID, limit=10, firestore_client=client)
        assert [i["id"] for i in items] == ["a1", "a2"]

    def test_soft_tombstone_row_flows_through(self, sync_db):
        docs = [_item("a1", NOW, deleted=True)]
        client, _, _ = _sync_client(docs)
        items, _ = sync_db.get_action_items_sync_page(UID, limit=10, firestore_client=client)
        assert items[0]["deleted"] is True


class TestActionItemsUpdatedSinceTool:
    """The shared sync core used by the MCP tool and the REST feed."""

    def test_updated_since_routes_to_sync_page_and_emits_watermark(self, monkeypatch):
        seen = {}

        def fake_page(uid, *, updated_since, after, limit):
            seen.update(updated_since=updated_since, after=after, limit=limit)
            return ([{"id": "a1", "description": "task", "completed": False, "updated_at": NOW}], (NOW, "a1"))

        monkeypatch.setattr(action_items_handler.action_item_sync_db, "get_action_items_sync_page", fake_page)
        result = action_items_handler.get_action_items(UID, {"updated_since": "2026-06-01T00:00:00Z", "limit": 10})
        assert seen["updated_since"] == SINCE
        assert seen["after"] is None
        assert seen["limit"] == 10
        item = result["action_items"][0]
        assert item["updated_at"] == NOW
        assert "deleted" not in item
        assert result["next_cursor"]

        def empty_page(uid, *, updated_since, after, limit):
            seen.update(after=after)
            return ([], None)

        monkeypatch.setattr(action_items_handler.action_item_sync_db, "get_action_items_sync_page", empty_page)
        action_items_handler.get_action_items(
            UID, {"updated_since": "2026-06-01T00:00:00Z", "cursor": result["next_cursor"]}
        )
        # The opaque cursor round-trips back to the raw (updated_at, doc id) keyset.
        assert seen["after"] == (NOW, "a1")

    def test_soft_tombstone_emitted_only_for_deleted_rows(self, monkeypatch):
        rows = [
            {"id": "a1", "description": "live", "completed": False, "updated_at": NOW},
            {"id": "a2", "description": "gone", "completed": False, "updated_at": NOW, "deleted": True},
        ]
        monkeypatch.setattr(
            action_items_handler.action_item_sync_db,
            "get_action_items_sync_page",
            lambda uid, **kw: (rows, None),
        )
        result = action_items_handler.get_action_items(UID, {"updated_since": "2026-06-01T00:00:00Z"})
        live, gone = result["action_items"]
        assert "deleted" not in live
        assert gone["deleted"] is True

    @pytest.mark.parametrize(
        "arguments",
        [
            {"updated_since": "2026-06-01"},
            {"updated_since": "not-a-date"},
            {"updated_since": "2026-06-01T00:00:00Z", "completed": True},
            {"updated_since": "2026-06-01T00:00:00Z", "due_start_date": "2026-06-01"},
            {"updated_since": "2026-06-01T00:00:00Z", "due_end_date": "2026-06-30"},
            {"updated_since": "2026-06-01T00:00:00Z", "offset": 5},
        ],
    )
    def test_sync_mode_rejects_naive_and_incompatible_inputs(self, arguments):
        with pytest.raises(ToolExecutionError) as exc:
            action_items_handler.get_action_items(UID, arguments)
        assert exc.value.code == -32602


class TestActionItemIndexManifest:
    """Incremental sync walks (updated_at, __name__) in both directions.
    Firestore auto-serves same-direction field+__name__ orderings, so the
    registry and generated manifest must NOT declare those composites —
    test_firestore_index_config rejects them as redundant."""

    def test_registry_declares_no_same_direction_updated_at_composite(self):
        registry = _import_real_module("database.firestore_index_registry")
        for requirement in registry.INDEX_ONLY_REQUIREMENTS:
            if requirement.collection_group != "action_items":
                continue
            fields = [(f.field_path, f.order) for f in requirement.fields]
            non_name = [f for f in fields if f[0] != "__name__"]
            name = [f for f in fields if f[0] == "__name__"]
            if len(non_name) != 1 or len(name) != 1 or non_name[0][0] != "updated_at":
                continue
            assert non_name[0][1] != name[0][1], requirement.identifier

    def test_generated_manifest_declares_no_same_direction_updated_at_composite(self):
        import json
        import os.path

        manifest_path = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..", "..", "firestore.indexes.json")
        )
        with open(manifest_path) as f:
            manifest = json.load(f)
        shapes = {
            tuple((f["fieldPath"], f.get("order")) for f in i["fields"])
            for i in manifest["indexes"]
            if i.get("collectionGroup") == "action_items"
        }
        assert (("updated_at", "ASCENDING"), ("__name__", "ASCENDING")) not in shapes
        assert (("updated_at", "DESCENDING"), ("__name__", "DESCENDING")) not in shapes


# --- REST contract tests ----------------------------------------------------


def _conversation(conv_id="c1", **extra):
    conv = {
        "id": conv_id,
        "started_at": NOW,
        "finished_at": NOW,
        "structured": {"title": "Standup", "overview": "Daily sync", "category": "technology"},
        "language": "en",
        "apps_results": [{"app_id": "app-1", "content": "note"}],
    }
    conv.update(extra)
    return conv


class _FakeMemory:
    def __init__(self, data):
        self._data = dict(data)

    def model_dump(self, mode=None):
        return dict(self._data)


def _memory(mem_id):
    return _FakeMemory(
        {
            "id": mem_id,
            "content": f"fact {mem_id}",
            "category": "other",
            "created_at": NOW,
            "updated_at": NOW,
        }
    )


@pytest.fixture
def client(monkeypatch):
    app = FastAPI()
    app.include_router(rest.router)
    app.dependency_overrides[rest.get_uid_from_mcp_api_key] = lambda: UID
    app.dependency_overrides[rest.get_mcp_memory_default_memory_read_context] = lambda: SimpleNamespace(uid=UID)
    monkeypatch.setattr(
        rest,
        "authorize_memory_external_default_memory_read",
        lambda auth_context, db_client=None: SimpleNamespace(allowed=True),
    )
    return TestClient(app)


class TestRestIncrementalSyncGates:
    """Permanent capability gates where the storage model cannot serve
    revision queries — a stable 400, never a retryable 503."""

    def test_conversations_updated_since_returns_400_no_retry_after(self, client):
        resp = client.get("/v1/mcp/conversations", params={"updated_since": "2026-06-01T00:00:00Z"})
        assert resp.status_code == 400
        assert "incremental_sync_unsupported" in resp.json()["detail"]
        assert "created_at DESC, id" in resp.json()["detail"]
        assert "Retry-After" not in resp.headers

    def test_conversations_naive_updated_since_returns_400(self, client):
        resp = client.get("/v1/mcp/conversations", params={"updated_since": "2026-06-01"})
        assert resp.status_code == 400

    def test_memories_updated_since_returns_400_no_retry_after(self, client):
        resp = client.get("/v1/mcp/memories", params={"updated_since": "2026-06-01T00:00:00Z"})
        assert resp.status_code == 400
        assert "incremental_sync_unsupported" in resp.json()["detail"]
        assert "Retry-After" not in resp.headers

    def test_memories_naive_updated_since_returns_400(self, client):
        resp = client.get("/v1/mcp/memories", params={"updated_since": "2026-06-01"})
        assert resp.status_code == 400


class TestRestListCursorContract:
    """List bodies stay arrays; cursors travel only in X-Next-Cursor."""

    def test_conversations_array_cursor_header_and_roundtrip(self, monkeypatch, client):
        calls = []

        def fake_page(
            uid, limit, *, after=None, start_date=None, end_date=None, categories=None, extra_field_paths=None
        ):
            calls.append(after)
            if after is None:
                return ([_conversation()], (NOW, "c1"))
            return ([_conversation("c2")], None)

        monkeypatch.setattr(
            rest.mcp_conversation_handlers.mcp_conversation_pages,
            "get_mcp_conversation_cards_page",
            fake_page,
        )
        resp = client.get("/v1/mcp/conversations", params={"limit": 1})
        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body, list) and body[0]["id"] == "c1"
        # The released desktop client consumes apps_results off list cards.
        assert body[0]["apps_results"] == [{"app_id": "app-1", "content": "note"}]
        cursor = resp.headers.get("X-Next-Cursor")
        assert cursor

        resp2 = client.get("/v1/mcp/conversations", params={"cursor": cursor})
        assert resp2.status_code == 200
        assert resp2.json()[0]["id"] == "c2"
        # The opaque cursor decoded back to the emitted (created_at, doc id) keyset.
        assert calls[1] == (NOW, "c1")

    def test_foreign_cursor_rejected_400(self, client):
        resp = client.get("/v1/mcp/conversations", params={"cursor": "not-a-cursor"})
        assert resp.status_code == 400

    def test_memories_list_stays_array(self, monkeypatch, client):
        service = MagicMock()
        service.read.return_value = [_memory("m1")]
        monkeypatch.setattr(rest.mcp_memory_handlers, "MemoryService", lambda db_client=None: service)
        resp = client.get("/v1/mcp/memories")
        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body, list)
        assert body[0]["id"] == "m1" and body[0]["content"] == "fact m1"
        assert body[0]["category"] == "other"

    def test_memories_bounded_page_emits_header_cursor(self, monkeypatch, client):
        # created_desc (the REST default) walks the bounded-scan path; an
        # in-window continuation must surface as X-Next-Cursor, not a body field.
        memories = [_memory(f"m{i}") for i in range(5)]
        service = MagicMock()
        service.read.side_effect = lambda uid, limit=None, offset=0: memories
        monkeypatch.setattr(rest.mcp_memory_handlers, "MemoryService", lambda db_client=None: service)
        resp = client.get("/v1/mcp/memories", params={"limit": 2})
        assert resp.status_code == 200
        assert [m["id"] for m in resp.json()] == ["m0", "m1"]
        cursor = resp.headers.get("X-Next-Cursor")
        assert cursor

        resp2 = client.get("/v1/mcp/memories", params={"limit": 2, "cursor": cursor})
        assert resp2.status_code == 200
        assert [m["id"] for m in resp2.json()] == ["m2", "m3"]

    def test_action_items_sync_feed(self, monkeypatch, client):
        def fake_page(uid, *, updated_since, after, limit):
            rows = [
                {"id": "a1", "description": "live", "completed": False, "updated_at": NOW},
                {
                    "id": "a2",
                    "description": "gone",
                    "completed": False,
                    "updated_at": NOW,
                    "deleted": True,
                },
            ]
            return (rows, None)

        monkeypatch.setattr(
            rest.mcp_action_item_handlers.action_item_sync_db,
            "get_action_items_sync_page",
            fake_page,
        )
        resp = client.get("/v1/mcp/action-items", params={"updated_since": "2026-06-01T00:00:00Z"})
        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body, list)
        live, gone = body
        assert live["updated_at"] is not None and live["deleted"] is not True
        assert gone["deleted"] is True

    def test_action_items_sync_rejects_incompatible_filters(self, client):
        for params in [
            {"updated_since": "2026-06-01T00:00:00Z", "completed": "true"},
            {"updated_since": "2026-06-01T00:00:00Z", "due_start_date": "2026-06-01T00:00:00Z"},
            {"updated_since": "2026-06-01T00:00:00Z", "offset": 5},
            {"updated_since": "2026-06-01"},
        ]:
            resp = client.get("/v1/mcp/action-items", params=params)
            assert resp.status_code == 400, params

    def test_action_items_normal_list_unchanged(self, monkeypatch, client):
        monkeypatch.setattr(
            rest.mcp_action_item_handlers.action_items_db,
            "get_action_items",
            lambda uid, **kw: [
                {"id": "a1", "description": "live", "completed": False},
                {"id": "a2", "description": "gone", "completed": False, "deleted": True},
            ],
        )
        resp = client.get("/v1/mcp/action-items")
        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body, list)
        assert [i["id"] for i in body] == ["a1"]

    def test_chat_screen_and_daily_summaries_stay_arrays(self, monkeypatch, client):
        monkeypatch.setattr(
            rest.mcp_other_handlers.chat_db,
            "get_messages",
            lambda uid, **kw: [
                {
                    "id": "m1",
                    "text": "hi",
                    "sender": "human",
                    "type": "text",
                    "created_at": NOW,
                    "files_id": [],
                }
            ],
        )
        resp = client.get("/v1/mcp/chat")
        assert resp.status_code == 200 and isinstance(resp.json(), list)
        assert resp.json()[0]["text"] == "hi"

        monkeypatch.setattr(
            rest.mcp_other_handlers.screen_activity_db,
            "get_screen_activity_page",
            lambda uid, **kw: (
                [
                    {
                        "id": "s1",
                        "appName": "Cursor",
                        "windowTitle": "editor",
                        "timestamp": NOW,
                        "ocrText": "code",
                    }
                ],
                None,
            ),
        )
        resp = client.get("/v1/mcp/screen-activity")
        assert resp.status_code == 200 and isinstance(resp.json(), list)
        assert resp.json()[0]["app_name"] == "Cursor"

        monkeypatch.setattr(
            rest.mcp_other_handlers.screen_activity_db,
            "get_screen_activity_summary",
            lambda uid, **kw: {"apps": {"Cursor": {"count": 1}}, "total_screenshots": 1},
        )
        resp = client.get("/v1/mcp/screen-activity", params={"summary": "true"})
        assert resp.status_code == 200
        assert resp.json()["total_screenshots"] == 1

        monkeypatch.setattr(
            rest.mcp_other_handlers.daily_summaries_db,
            "get_daily_summaries",
            lambda uid, **kw: [{"date": "2026-06-11", "content": "Worked"}],
        )
        resp = client.get("/v1/mcp/daily-summaries")
        assert resp.status_code == 200 and isinstance(resp.json(), list)
        assert resp.json()[0]["date"] == "2026-06-11"


class TestRestStatusContract:
    """Released status codes survive delegation to shared cores."""

    def test_conversation_detail_transcript_speaker_name_and_apps_results(self, monkeypatch, client):
        conv = _conversation(
            transcript_segments=[{"id": "s1", "text": "hello", "speaker_id": 0, "start": 0.0, "end": 1.0}]
        )
        monkeypatch.setattr(
            rest.mcp_conversation_handlers.conversations_db,
            "get_mcp_conversations_by_id",
            lambda uid, ids, **kw: [conv],
        )

        def name_speakers(uid, conversations):
            for c in conversations:
                for seg in c.get("transcript_segments") or []:
                    seg["speaker_name"] = "Speaker 0"

        monkeypatch.setattr(rest, "populate_speaker_names", name_speakers)
        resp = client.get("/v1/mcp/conversations/c1")
        assert resp.status_code == 200
        body = resp.json()
        assert body["transcript_segments"][0]["speaker_name"] == "Speaker 0"
        assert body["truncated"] is False
        assert body["apps_results"] == [{"app_id": "app-1", "content": "note"}]

    def test_conversation_detail_locked_402_and_missing_404(self, monkeypatch, client):
        monkeypatch.setattr(rest, "populate_speaker_names", lambda uid, convs: None)
        monkeypatch.setattr(
            rest.mcp_conversation_handlers.conversations_db,
            "get_mcp_conversations_by_id",
            lambda uid, ids, **kw: [_conversation(is_locked=True)],
        )
        assert client.get("/v1/mcp/conversations/locked").status_code == 402

        monkeypatch.setattr(
            rest.mcp_conversation_handlers.conversations_db,
            "get_mcp_conversations_by_id",
            lambda uid, ids, **kw: [],
        )
        assert client.get("/v1/mcp/conversations/missing").status_code == 404

    def test_memory_write_shape_and_patch_delete_status(self, monkeypatch):
        write_grant = SimpleNamespace(allowed=True)
        monkeypatch.setattr(
            rest,
            "authorize_memory_external_default_memory_write",
            lambda auth_context, db_client=None: write_grant,
        )
        monkeypatch.setattr(rest, "identify_category_for_memory", lambda content: "other")
        monkeypatch.setattr(rest, "postprocess_executor", MagicMock())
        monkeypatch.setattr(rest, "fetch_memory_dict", lambda uid, memory_id, db_client=None: {})

        from models.memories import Memory, MemoryCategory, MemoryDB

        memory_db = MemoryDB.from_memory(
            Memory(content="remember this", category=MemoryCategory.other), UID, None, True
        )
        service = MagicMock()
        service.create_external_memory.return_value = memory_db
        monkeypatch.setattr(rest.mcp_memory_handlers, "MemoryService", lambda db_client=None: service)
        captures = []
        monkeypatch.setattr(rest.mcp_memory_handlers, "capture_memory_write", lambda **kw: captures.append(kw))
        seen = {}
        real_create_one = rest.mcp_memory_handlers._create_one_memory

        def spy_create(uid, memory, **kwargs):
            seen["memory"] = memory
            seen["kwargs"] = kwargs
            return real_create_one(uid, memory, **kwargs)

        monkeypatch.setattr(rest.mcp_memory_handlers, "_create_one_memory", spy_create)

        request_memory = Memory(content="remember this", category=MemoryCategory.other, tags=["keep"])
        created = rest.create_memory(request_memory, auth_context=SimpleNamespace(uid=UID))
        assert created.id
        assert created.content == "remember this"
        assert created.category == MemoryCategory.other
        # The full request Memory (tags/proposition fields included) reaches the
        # shared write core — not a bare Memory(content, category) rebuild.
        assert seen["memory"] is request_memory
        assert seen["kwargs"]["operation"] == "mcp_memory_create"
        # REST keeps the vector upsert its legacy path performed.
        assert seen["kwargs"]["upsert_vector"] is True
        call = service.create_external_memory.call_args
        assert call.kwargs["upsert_vector"] is True
        assert call.kwargs["operation"] == "mcp_memory_create"
        # Parity capture fires exactly once inside the shared core.
        assert len(captures) == 1 and captures[0]["source"] == "mcp_memory_create"

        # PATCH/DELETE route through the shared registry spec handler.
        spec_calls = []

        def fake_spec(name):
            return SimpleNamespace(
                handler=lambda uid, args, auth: spec_calls.append((name, uid, args, auth)) or {"success": True}
            )

        monkeypatch.setattr(rest, "spec_for_tool", fake_spec)
        assert rest.edit_memory(memory_id="m1", value="new content", auth_context=SimpleNamespace(uid=UID)) == {
            "status": "ok"
        }
        assert rest.delete_memory(memory_id="m1", auth_context=SimpleNamespace(uid=UID)) == {"status": "ok"}
        assert [c[0] for c in spec_calls] == ["edit_memory", "delete_memory"]
        assert spec_calls[0][2] == {"memory_id": "m1", "content": "new content"}
        assert spec_calls[1][2] == {"memory_id": "m1"}

    def test_memory_search_delegates_to_spec_handler(self, monkeypatch, client):
        monkeypatch.setattr(rest, "sanitize_pii", lambda v: v)
        spec_calls = []

        def fake_spec(name):
            return SimpleNamespace(
                handler=lambda uid, args, auth: spec_calls.append((name, uid, args, auth))
                or {"memories": [{"id": "m1", "content": "c", "category": "other", "relevance_score": 0.9}]}
            )

        monkeypatch.setattr(rest, "spec_for_tool", fake_spec)
        resp = client.get("/v1/mcp/memories/search", params={"query": "coffee", "limit": 30})
        assert resp.status_code == 200
        assert spec_calls[0][0] == "search_memories"
        assert spec_calls[0][2] == {"query": "coffee", "limit": 30}
        body = resp.json()
        assert isinstance(body, list) and body[0]["id"] == "m1"
        assert body[0]["relevance_score"] == 0.9

    def test_memory_edit_keeps_404_precheck(self, monkeypatch):
        write_grant = SimpleNamespace(allowed=True)
        monkeypatch.setattr(
            rest,
            "authorize_memory_external_default_memory_write",
            lambda auth_context, db_client=None: write_grant,
        )
        monkeypatch.setattr(
            rest,
            "fetch_memory_dict",
            lambda uid, memory_id, db_client=None: (_ for _ in ()).throw(
                rest.HTTPException(status_code=404, detail="Memory not found")
            ),
        )
        spec_calls = []
        monkeypatch.setattr(
            rest,
            "spec_for_tool",
            lambda name: SimpleNamespace(handler=lambda uid, args, auth: spec_calls.append(name)),
        )
        with pytest.raises(rest.HTTPException) as exc:
            rest.edit_memory(memory_id="gone", value="x", auth_context=SimpleNamespace(uid=UID))
        assert exc.value.status_code == 404
        assert spec_calls == []

    def test_memory_write_denied_grant_is_403(self, monkeypatch):
        denied = SimpleNamespace(allowed=False, status_code=403, observability={"reason": "missing_grant"})
        monkeypatch.setattr(
            rest,
            "authorize_memory_external_default_memory_write",
            lambda auth_context, db_client=None: denied,
        )
        from models.memories import Memory, MemoryCategory

        with pytest.raises(rest.HTTPException) as exc:
            rest.create_memory(
                Memory(content="x", category=MemoryCategory.other),
                auth_context=SimpleNamespace(uid=UID),
            )
        assert exc.value.status_code == 403

    def test_rate_limited_tool_error_maps_to_429_with_retry_after(self, monkeypatch, client):
        monkeypatch.setattr(
            rest.mcp_action_item_handlers,
            "action_items_list_page_core",
            MagicMock(side_effect=ToolExecutionError("rate limited", code=-32009, analytics_rate_limited=True)),
        )
        resp = client.get("/v1/mcp/action-items")
        assert resp.status_code == 429
        assert resp.headers.get("Retry-After") == "60"


class TestRestSyncEdgeCases:
    """Present-but-empty updated_since must 400 everywhere, not pass as absent."""

    @pytest.mark.parametrize("path", ["/v1/mcp/conversations", "/v1/mcp/memories", "/v1/mcp/action-items"])
    def test_empty_updated_since_returns_400(self, client, path):
        resp = client.get(path, params={"updated_since": ""})
        assert resp.status_code == 400

    def test_tool_empty_updated_since_rejected(self):
        with pytest.raises(ToolExecutionError) as exc:
            action_items_handler.get_action_items(UID, {"updated_since": ""})
        assert exc.value.code == -32602


class TestRestRetryAfterRouteLayer:
    """The router-level APIRoute guarantees Retry-After on every 429."""

    def test_bare_429_from_dependency_gets_retry_after(self, client):
        def deny():
            raise rest.HTTPException(status_code=429, detail="Too Many Requests")

        client.app.dependency_overrides[rest.get_uid_from_mcp_api_key] = deny
        resp = client.get("/v1/mcp/action-items")
        assert resp.status_code == 429
        assert resp.headers.get("Retry-After") == "60"

    def test_429_preserves_existing_retry_after(self, client):
        def deny():
            raise rest.HTTPException(status_code=429, detail="Too Many Requests", headers={"Retry-After": "7"})

        client.app.dependency_overrides[rest.get_uid_from_mcp_api_key] = deny
        resp = client.get("/v1/mcp/action-items")
        assert resp.status_code == 429
        assert resp.headers.get("Retry-After") == "7"

    def test_non_429_errors_untouched(self, client):
        def deny():
            raise rest.HTTPException(status_code=403, detail="denied")

        client.app.dependency_overrides[rest.get_uid_from_mcp_api_key] = deny
        resp = client.get("/v1/mcp/action-items")
        assert resp.status_code == 403
        assert "Retry-After" not in resp.headers


class TestRestMemoryListScanContract:
    """REST keeps its released 5000-row filtered-scan window."""

    def test_rest_passes_released_max_scan(self, monkeypatch, client):
        seen = {}

        def fake_collect(fetch_batch, **kwargs):
            seen.update(kwargs)
            return {
                "memories": [{"id": "m1", "content": "c", "category": "other"}],
                "has_more": False,
                "more_in_window": False,
                "scanned_count": 1,
                "scan_truncated": False,
            }

        monkeypatch.setattr(rest.mcp_memory_handlers, "collect_filtered_memories", fake_collect)
        resp = client.get("/v1/mcp/memories", params={"sort": "created_desc"})
        assert resp.status_code == 200
        assert resp.json()[0]["id"] == "m1"
        assert seen["max_scan"] == 5000

    def test_scan_truncated_exposed_via_header(self, monkeypatch, client):
        monkeypatch.setattr(
            rest.mcp_memory_handlers,
            "memories_page_core",
            lambda uid, **kw: {"memories": [], "scan_truncated": True},
        )
        resp = client.get("/v1/mcp/memories")
        assert resp.status_code == 200
        assert resp.headers.get("X-Scan-Truncated") == "true"

    def test_no_truncated_header_on_complete_scan(self, monkeypatch, client):
        monkeypatch.setattr(
            rest.mcp_memory_handlers,
            "memories_page_core",
            lambda uid, **kw: {"memories": [], "scan_truncated": False},
        )
        resp = client.get("/v1/mcp/memories")
        assert resp.status_code == 200
        assert "X-Scan-Truncated" not in resp.headers


class TestRestActionItemSpecDelegation:
    """REST action-item writes/search call the shared registry spec handlers."""

    def _spec_recorder(self, monkeypatch, result=None, error=None):
        calls = []

        def fake_spec(name):
            def handler(uid, args, auth):
                calls.append((name, uid, args, auth))
                if error is not None:
                    raise error
                return result or {}

            return SimpleNamespace(handler=handler)

        monkeypatch.setattr(rest, "spec_for_tool", fake_spec)
        return calls

    def test_action_item_writes_and_search_delegate(self, monkeypatch):
        calls = self._spec_recorder(
            monkeypatch,
            result={
                "success": True,
                "action_item": {"id": "a1", "description": "d", "completed": False},
                "action_items": [{"id": "a1", "description": "d"}],
            },
        )
        item = rest.create_action_item(body=rest.McpCreateActionItem(description="d"), uid=UID)
        assert item["id"] == "a1"
        item = rest.complete_action_item(action_item_id="a1", completed=True, uid=UID)
        assert item["id"] == "a1"
        item = rest.update_action_item("a1", body=rest.McpUpdateActionItem(description="n"), uid=UID)
        assert item["id"] == "a1"
        assert rest.delete_action_item(action_item_id="a1", uid=UID) == {"status": "ok"}
        items = rest.search_action_items(query="d", uid=UID)
        assert items[0]["id"] == "a1"
        assert [c[0] for c in calls] == [
            "create_action_item",
            "complete_action_item",
            "update_action_item",
            "delete_action_item",
            "search_action_items",
        ]
        assert calls[0][2] == {"description": "d", "due_at": None, "completed": False}
        assert calls[1][2] == {"action_item_id": "a1", "completed": True}
        assert calls[2][2] == {"action_item_id": "a1", "description": "n", "due_at": None}
        assert calls[3][2] == {"action_item_id": "a1"}
        assert calls[4][2] == {"query": "d", "limit": 10}

    @pytest.mark.parametrize(
        "error,status",
        [
            (ToolExecutionError("bad", code=-32602), 422),
            (ToolExecutionError("bad", code=-32000), 422),
            (ToolExecutionError("missing", code=-32001), 404),
            (ToolExecutionError("locked", code=-32002), 402),
            (ToolExecutionError("boom", code=-32010), 500),
        ],
    )
    def test_action_item_error_status_map(self, monkeypatch, error, status):
        self._spec_recorder(monkeypatch, error=error)
        with pytest.raises(rest.HTTPException) as exc:
            rest.create_action_item(body=rest.McpCreateActionItem(description="d"), uid=UID)
        assert exc.value.status_code == status


class TestRestDetailManualSpeakers:
    """Detail fetches the manual speaker-assignment receipt like the legacy read."""

    def test_detail_projects_manual_fields_and_maps_speaker_name(self, monkeypatch, client):
        captured = {}

        def fake_get_by_id(uid, ids, **kwargs):
            captured["extra_field_paths"] = kwargs.get("extra_field_paths")
            return [
                _conversation(
                    "c1",
                    transcript_segments=[
                        {"id": "s1", "text": "hi", "speaker_id": 0, "person_id": "p1", "start": 0.0, "end": 1.0}
                    ],
                    manual_speaker_assignments={"speakers": {"0": {"person_id": "p1", "is_user": False}}},
                )
            ]

        monkeypatch.setattr(
            rest.mcp_conversation_handlers.conversations_db,
            "get_mcp_conversations_by_id",
            fake_get_by_id,
        )
        import utils.conversations.render as render

        monkeypatch.setattr(render, "get_user_name", lambda uid, use_default=True: "Me")
        monkeypatch.setattr(
            render.users_db,
            "get_people_by_ids",
            lambda uid, ids: [{"id": "p1", "name": "Alice"}],
        )
        resp = client.get("/v1/mcp/conversations/c1")
        assert resp.status_code == 200
        assert captured["extra_field_paths"] == rest._REST_CONVERSATION_DETAIL_EXTRA_FIELD_PATHS
        assert "manual_speaker_assignments" in captured["extra_field_paths"]
        assert "manual_speaker_assignments_compressed" in captured["extra_field_paths"]
        assert resp.json()["transcript_segments"][0]["speaker_name"] == "Alice"


class TestRestOAuthGrantRevoke:
    """Grant revocation fails closed: an unwritable Redis marker is a
    retryable 503 — never a 204 for a revoke that did not happen."""

    def test_revoke_returns_503_with_retry_after_when_token_store_down(self, monkeypatch, client):
        import database.mcp_token_cache as token_cache

        def boom(uid, grant_id):
            raise token_cache.McpTokenStoreUnavailable("redis down")

        monkeypatch.setattr(rest.mcp_oauth_db, "revoke_user_grant", boom)
        client.app.dependency_overrides[rest.get_current_user_id] = lambda: UID
        resp = client.delete("/v1/mcp/oauth/grants/grant-1")
        assert resp.status_code == 503
        assert resp.headers.get("Retry-After") == "60"

    def test_revoke_unknown_grant_still_404(self, monkeypatch, client):
        monkeypatch.setattr(rest.mcp_oauth_db, "revoke_user_grant", lambda uid, grant_id: False)
        client.app.dependency_overrides[rest.get_current_user_id] = lambda: UID
        resp = client.delete("/v1/mcp/oauth/grants/missing")
        assert resp.status_code == 404

    def test_successful_revoke_still_204(self, monkeypatch, client):
        monkeypatch.setattr(rest.mcp_oauth_db, "revoke_user_grant", lambda uid, grant_id: True)
        client.app.dependency_overrides[rest.get_current_user_id] = lambda: UID
        resp = client.delete("/v1/mcp/oauth/grants/grant-1")
        assert resp.status_code == 204


class TestSyncedWriterTimestamps:
    """Every mutation that changes a sync-visible field must move
    ``updated_at`` — otherwise the row never passes the client's watermark
    and the (updated_at, __name__) feed silently loses the write."""

    def _fake_db(self, monkeypatch, action_items_db, docs):
        written = []

        class _Batch:
            def update(self, ref, data):
                written.append((ref.id, data))

            def commit(self):
                pass

        items_collection = MagicMock()
        query = MagicMock()
        query.where.return_value = query
        query.stream.return_value = iter(docs)
        items_collection.where.return_value = query
        items_collection.document.side_effect = lambda doc_id: MagicMock(id=doc_id)
        user_doc = MagicMock()
        user_doc.collection.return_value = items_collection
        users = MagicMock()
        users.document.return_value = user_doc
        fake_db = MagicMock()
        fake_db.collection.return_value = users
        fake_db.batch.side_effect = _Batch

        monkeypatch.setattr(action_items_db, "db", fake_db)
        monkeypatch.setattr(action_items_db, "bump_action_items_list_version", lambda uid: None)
        return fake_db, items_collection, written

    def test_unlock_all_action_items_stamps_updated_at(self, sync_db, monkeypatch):
        import database.action_items as action_items_db

        docs = [SimpleNamespace(reference=SimpleNamespace(id=f"a{i}")) for i in range(3)]
        _, _, written = self._fake_db(monkeypatch, action_items_db, docs)

        action_items_db.unlock_all_action_items(UID)

        assert [ref_id for ref_id, _ in written] == ["a0", "a1", "a2"]
        for _, data in written:
            assert data["is_locked"] is False
            assert isinstance(data["updated_at"], datetime)

    def test_update_action_item_stamps_updated_at(self, sync_db, monkeypatch):
        import database.action_items as action_items_db

        doc_ref = MagicMock()
        doc_ref.get.return_value = SimpleNamespace(exists=True)
        _, items_collection, _ = self._fake_db(monkeypatch, action_items_db, [])
        items_collection.document.side_effect = lambda doc_id: doc_ref

        assert action_items_db.update_action_item(UID, "a1", {"description": "new text"}) is True
        data = doc_ref.update.call_args[0][0]
        assert data["description"] == "new text"
        assert isinstance(data["updated_at"], datetime)

    def test_mark_completed_stamps_updated_at(self, sync_db, monkeypatch):
        import database.action_items as action_items_db

        doc_ref = MagicMock()
        doc_ref.get.return_value = SimpleNamespace(exists=True)
        _, items_collection, _ = self._fake_db(monkeypatch, action_items_db, [])
        items_collection.document.side_effect = lambda doc_id: doc_ref

        assert action_items_db.mark_action_item_completed(UID, "a1", completed=True) is True
        data = doc_ref.update.call_args[0][0]
        assert data["completed"] is True
        assert isinstance(data["updated_at"], datetime)
