"""Phase 2 section 1: batch tools, opaque list cursors, grouped screen activity.

Covers ``get_conversations_by_ids`` (single batch read, dedupe/order, locked
and missing ids, response budget, per-item transcript bounds),
``create_memories`` (per-item charge including duplicates, per-item errors,
batch-local dedupe, category handling), ``get_screen_activity`` grouping and
keyset cursor, and the shared base64url cursor contract across every
offset-paginated list tool.
"""

import importlib
import json
import sys
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

import utils.mcp_analytics as mcp_analytics
import utils.mcp_server.transport as mcp_transport
from models.memories import MemoryCategory
from routers import mcp_sse as sse
from utils.mcp_context import MCP_SERVER_INSTRUCTIONS
from utils.mcp_server import cursors as mcp_cursors
from utils.mcp_server.auth import MCPAuthContext
from utils.mcp_server.constants import (
    MCP_CONVERSATION_BATCH_RESPONSE_MAX_CHARS,
    MCP_MEMORY_BATCH_MAX_ITEMS,
    MCP_SCREEN_ACTIVITY_OBSERVATION_GAP_SECONDS,
    MCP_SCREEN_ACTIVITY_TOP_TITLES,
)
from utils.mcp_server.errors import ToolExecutionError
from utils.mcp_server.handlers import action_items as action_items_handler
from utils.mcp_server.handlers import conversations as conversations_handler
from utils.mcp_server.handlers import memories as memories_handler
from utils.mcp_server.handlers import other as other_handler
from utils.mcp_server.payloads import tool_response_serialized_chars
from utils.mcp_server.registry import TOOLS_BY_NAME

UID = "uid-batch"
ALLOWED = SimpleNamespace(allowed=True)


def _import_real_module(name):
    """Return the real module for ``name``.

    Several sibling test files install ``sys.modules`` stubs at collection and
    never restore them; in a shared pytest process this file can be collected
    after one of those installs. A stub advertises itself by defining
    ``__getattr__`` on the module class (real modules never do).
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


def _conversation(cid, *, locked=False, text="hello"):
    return {
        "id": cid,
        "created_at": "2026-06-11T10:00:00Z",
        "started_at": "2026-06-11T09:55:00Z",
        "finished_at": "2026-06-11T10:05:00Z",
        "language": "en",
        "structured": {"title": f"title-{cid}", "overview": "o", "category": "personal", "emoji": "x"},
        "transcript_segments": [{"id": "s1", "text": text, "speaker_id": 0, "is_user": True, "start": 0.0, "end": 1.0}],
        "is_locked": locked,
    }


def _batch_fetch(rows_by_id):
    def _fetch(uid, ids, **kwargs):
        return [rows_by_id[i] for i in ids if i in rows_by_id]

    return _fetch


class TestGetConversationsByIds:
    def test_one_batch_read_dedupes_in_encounter_order(self):
        with patch.object(
            conversations_handler.conversations_db, "get_mcp_conversations_by_id", return_value=[]
        ) as fetch:
            result = sse.execute_tool(UID, "get_conversations_by_ids", {"conversation_ids": ["b", "a", "b", "c", "a"]})
        assert fetch.call_count == 1
        assert fetch.call_args.args[1] == ["b", "a", "c"]
        assert fetch.call_args.kwargs == {"include_transcript": True, "include_discarded": True}
        assert result == {"conversations": [], "not_found": ["b", "a", "c"], "truncated": False}

    def test_items_follow_request_order_and_missing_ids_are_listed(self):
        rows = {"a": _conversation("a"), "c": _conversation("c")}
        with patch.object(
            conversations_handler.conversations_db,
            "get_mcp_conversations_by_id",
            side_effect=_batch_fetch(rows),
        ):
            result = sse.execute_tool(UID, "get_conversations_by_ids", {"conversation_ids": ["c", "missing", "a"]})
        assert [item["id"] for item in result["conversations"]] == ["c", "a"]
        assert result["not_found"] == ["missing"]
        assert result["truncated"] is False
        card = result["conversations"][0]["conversation"]
        assert card["transcript_segments"][0]["text"] == "hello"
        assert "structured" in card
        assert "transcript_segments" not in card["structured"]

    def test_locked_item_returns_safe_error_and_never_leaks_transcript(self):
        rows = {
            "locked": _conversation("locked", locked=True, text="PRIVATE-TRANSCRIPT"),
            "open": _conversation("open"),
        }
        with patch.object(
            conversations_handler.conversations_db,
            "get_mcp_conversations_by_id",
            side_effect=_batch_fetch(rows),
        ):
            result = sse.execute_tool(UID, "get_conversations_by_ids", {"conversation_ids": ["locked", "open"]})
        locked_item, open_item = result["conversations"]
        assert locked_item["id"] == "locked"
        assert locked_item["error"]["code"] == "paid_plan_required"
        assert "conversation" not in locked_item
        assert "transcript" not in json.dumps(locked_item)
        assert "PRIVATE-TRANSCRIPT" not in json.dumps(result)
        assert open_item["conversation"]["transcript_segments"]

    def test_per_item_transcript_bounds_and_truncated_flag(self):
        conv = _conversation("c1")
        conv["transcript_segments"] = [
            {"id": "s1", "text": "alpha", "speaker_id": 0},
            {"id": "s2", "text": "beta", "speaker_id": 1},
        ]
        with patch.object(conversations_handler.conversations_db, "get_mcp_conversations_by_id", return_value=[conv]):
            result = sse.execute_tool(UID, "get_conversations_by_ids", {"conversation_ids": ["c1"], "max_segments": 1})
        item = result["conversations"][0]
        assert item["truncated"] is True
        assert len(item["conversation"]["transcript_segments"]) == 1

    def test_response_budget_omits_later_items_without_marking_not_found(self):
        big_text = "x" * 30_000
        rows = {f"c{i}": _conversation(f"c{i}", text=big_text) for i in range(6)}
        with patch.object(
            conversations_handler.conversations_db,
            "get_mcp_conversations_by_id",
            side_effect=_batch_fetch(rows),
        ):
            result = sse.execute_tool(
                UID, "get_conversations_by_ids", {"conversation_ids": [f"c{i}" for i in range(6)]}
            )
        assert result["truncated"] is True
        assert 0 < len(result["conversations"]) < 6
        # Budget-omitted ids are absent from both lists — never labeled not_found.
        returned = {item["id"] for item in result["conversations"]}
        assert result["not_found"] == []
        omitted = {f"c{i}" for i in range(6)} - returned
        assert omitted
        serialized = json.dumps(result, ensure_ascii=False, separators=(",", ":"), default=str)
        assert len(serialized) <= MCP_CONVERSATION_BATCH_RESPONSE_MAX_CHARS

    @pytest.mark.parametrize(
        "ids",
        [
            [],
            [f"c{i}" for i in range(21)],
            ["a", ""],
            ["a", 7],
            ["a" * 1501],
            ["a/b"],
            "not-a-list",
        ],
    )
    def test_invalid_id_lists_rejected(self, ids):
        with pytest.raises(ToolExecutionError) as exc:
            sse.execute_tool(UID, "get_conversations_by_ids", {"conversation_ids": ids})
        assert exc.value.code == -32602

    def test_not_found_stays_within_budget_with_max_size_ids(self):
        ids = [f"id-{i:02d}-" + "x" * 1480 for i in range(20)]
        with patch.object(
            conversations_handler.conversations_db, "get_mcp_conversations_by_id", return_value=[]
        ) as fetch:
            result = sse.execute_tool(UID, "get_conversations_by_ids", {"conversation_ids": ids})
        fetch.assert_called_once()
        assert result["not_found"] == ids
        assert result["conversations"] == []
        assert tool_response_serialized_chars(result) <= MCP_CONVERSATION_BATCH_RESPONSE_MAX_CHARS


def _memory_ctx():
    return SimpleNamespace(app_id="app-1", key_id="key-1", uid=UID)


def _memory_stubs(create_side_effect=None):
    service = MagicMock()
    if create_side_effect is None:
        service.return_value.create_external_memory.side_effect = lambda uid, memory_db, **kw: memory_db
    else:
        service.return_value.create_external_memory.side_effect = create_side_effect
    return (
        patch.object(memories_handler, "authorize_memory_external_default_memory_write", return_value=ALLOWED),
        patch.object(memories_handler, "MemoryService", service),
        patch.object(memories_handler, "identify_category_for_memory", return_value=MemoryCategory.other),
        patch.object(memories_handler, "capture_memory_write"),
        patch.object(memories_handler, "check_rate_limit_context"),
        patch.object(memories_handler, "check_rate_limit_inline"),
    ), service


class TestCreateMemories:
    def test_every_item_charged_including_duplicates(self):
        items = [{"content": "fact one"}, {"content": "fact one"}] + [{"content": f"fact {i}"} for i in range(23)]
        patches, _service = _memory_stubs()
        with patches[0], patches[1], patches[2], patches[3], patches[4] as limiter, patches[5]:
            result = sse.execute_tool(UID, "create_memories", {"items": items}, _memory_ctx())
        assert len(result["results"]) == MCP_MEMORY_BATCH_MAX_ITEMS
        assert limiter.call_count == MCP_MEMORY_BATCH_MAX_ITEMS
        assert all(call.args[1] == "memories:create" for call in limiter.call_args_list)

    def test_duplicate_points_to_first_created_id(self):
        items = [{"content": "same fact"}, {"content": "same fact"}, {"content": "other fact"}]
        patches, service = _memory_stubs()
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5]:
            result = sse.execute_tool(UID, "create_memories", {"items": items}, _memory_ctx())
        statuses = [r["status"] for r in result["results"]]
        assert statuses == ["created", "duplicate", "created"]
        assert result["results"][1]["memory_id"] == result["results"][0]["memory_id"]
        # Only the non-duplicate items reached the store.
        assert service.return_value.create_external_memory.call_count == 2

    def test_same_content_different_category_is_not_a_duplicate(self):
        items = [
            {"content": "same fact", "category": "interests"},
            {"content": "same fact", "category": "work"},
        ]
        patches, service = _memory_stubs()
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5]:
            result = sse.execute_tool(UID, "create_memories", {"items": items}, _memory_ctx())
        assert [r["status"] for r in result["results"]] == ["created", "created"]
        assert service.return_value.create_external_memory.call_count == 2

    def test_explicit_category_is_passed_through(self):
        patches, service = _memory_stubs()
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5]:
            result = sse.execute_tool(
                UID,
                "create_memories",
                {"items": [{"content": "likes espresso", "category": "interests"}]},
                _memory_ctx(),
            )
        assert result["results"][0]["status"] == "created"
        memory_db = service.return_value.create_external_memory.call_args.args[1]
        assert memory_db.category == MemoryCategory.interests

    def test_partial_write_failures_are_per_item_and_safe(self):
        def _fail_once(uid, memory_db, **kw):
            if memory_db.content == "bad":
                raise HTTPException(status_code=500, detail="private store detail")
            return memory_db

        items = [{"content": "ok one"}, {"content": "bad"}, {"content": "ok two"}]
        patches, _service = _memory_stubs(create_side_effect=_fail_once)
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5]:
            result = sse.execute_tool(UID, "create_memories", {"items": items}, _memory_ctx())
        statuses = [r["status"] for r in result["results"]]
        assert statuses == ["created", "error", "created"]
        error = result["results"][1]["error"]
        assert error["code"] == "internal"
        assert "private store detail" not in json.dumps(result)

    def test_limiter_failure_is_a_per_item_error(self):
        calls = iter([None, HTTPException(status_code=429, detail="Rate limit exceeded. Try again in 30s."), None])

        def _limiter(*args, **kwargs):
            outcome = next(calls)
            if outcome is not None:
                raise outcome

        items = [{"content": "a"}, {"content": "b"}, {"content": "c"}]
        patches, _service = _memory_stubs()
        with patches[0], patches[1], patches[2], patches[3], patches[5]:
            with patch.object(memories_handler, "check_rate_limit_context", side_effect=_limiter):
                result = sse.execute_tool(UID, "create_memories", {"items": items}, _memory_ctx())
        assert [r["status"] for r in result["results"]] == ["created", "error", "created"]
        assert result["results"][1]["error"]["code"] == "rate_limited"

    def test_invalid_item_is_per_item_error_and_not_charged(self):
        """Malformed items are rejected before their charge; only valid items
        consume write quota."""
        patches, _service = _memory_stubs()
        with patches[0], patches[1], patches[2], patches[3], patches[4] as limiter, patches[5]:
            result = sse.execute_tool(
                UID, "create_memories", {"items": [{"content": "ok"}, {"content": ""}]}, _memory_ctx()
            )
        assert [r["status"] for r in result["results"]] == ["created", "error"]
        assert result["results"][1]["error"]["code"] == "invalid_arguments"
        assert limiter.call_count == 1

    def test_non_object_item_is_per_item_error_and_not_charged(self):
        patches, _service = _memory_stubs()
        with patches[0], patches[1], patches[2], patches[3], patches[4] as limiter, patches[5]:
            result = sse.execute_tool(
                UID, "create_memories", {"items": [{"content": "ok"}, "not-an-object"]}, _memory_ctx()
            )
        assert [r["status"] for r in result["results"]] == ["created", "error"]
        assert result["results"][1]["error"]["code"] == "invalid_arguments"
        assert limiter.call_count == 1

    def test_duplicate_is_charged_like_a_write(self):
        """A within-batch duplicate still consumes write quota even though it
        never reaches the store."""
        patches, _service = _memory_stubs()
        with patches[0], patches[1], patches[2], patches[3], patches[4] as limiter, patches[5]:
            result = sse.execute_tool(
                UID, "create_memories", {"items": [{"content": "same"}, {"content": "same"}]}, _memory_ctx()
            )
        assert [r["status"] for r in result["results"]] == ["created", "duplicate"]
        assert limiter.call_count == 2

    def test_store_failure_is_charged_like_a_write(self):
        def _fail(uid, memory_db, **kw):
            raise HTTPException(status_code=500, detail="boom")

        patches, _service = _memory_stubs(create_side_effect=_fail)
        with patches[0], patches[1], patches[2], patches[3], patches[4] as limiter, patches[5]:
            result = sse.execute_tool(
                UID, "create_memories", {"items": [{"content": "a"}, {"content": "b"}]}, _memory_ctx()
            )
        assert [r["status"] for r in result["results"]] == ["error", "error"]
        assert limiter.call_count == 2

    @pytest.mark.parametrize("items", [[], [{"content": "x"}] * 26, "not-a-list"])
    def test_invalid_item_lists_rejected(self, items):
        with pytest.raises(ToolExecutionError) as exc:
            sse.execute_tool(UID, "create_memories", {"items": items}, _memory_ctx())
        assert exc.value.code == -32602

    def test_batch_tool_has_no_transport_precharge_but_keeps_write_operation(self):
        spec = TOOLS_BY_NAME["create_memories"]
        # Per-item charging lives inside the handler; a transport-level bucket
        # would charge once for up to 25 creates.
        assert spec.rate_bucket is None
        assert spec.write_operation == "memory_create"


def _screen_row(ts, *, app="Cursor", title="editor", doc_id=None):
    return {
        "id": doc_id or f"doc-{ts}",
        "timestamp": ts,
        "appName": app,
        "windowTitle": title,
        "ocrText": "ocr",
    }


class TestScreenActivityGrouping:
    def test_raw_rows_backward_compatible(self):
        rows = [_screen_row("2026-06-11 10:00:00.000"), _screen_row("2026-06-11 10:01:00.000")]
        with patch.object(
            other_handler.screen_activity_db, "get_screen_activity_page", return_value=(rows, False)
        ) as page:
            result = sse.execute_tool(UID, "get_screen_activity", {"limit": 50})
        assert [r["app_name"] for r in result["screen_activity"]] == ["Cursor", "Cursor"]
        assert "buckets" not in result
        assert "next_cursor" not in result
        assert page.call_args.kwargs["limit"] == 50

    def test_group_by_app_counts_durations_and_titles(self):
        rows = [
            _screen_row("2026-06-11 10:00:00.000", app="Cursor", title="t1"),
            _screen_row("2026-06-11 10:01:00.000", app="Cursor", title="t2"),
            _screen_row("2026-06-11 10:02:00.000", app="Cursor", title="t1"),
            # 28-minute gap exceeds the 5-minute bound: not observation time.
            _screen_row("2026-06-11 10:30:00.000", app="Cursor", title="t3"),
            # Same small gap but a different app: never bridged.
            _screen_row("2026-06-11 10:31:00.000", app="Safari", title="web"),
        ]
        with patch.object(other_handler.screen_activity_db, "get_screen_activity_page", return_value=(rows, False)):
            result = sse.execute_tool(UID, "get_screen_activity", {"group_by": "app"})
        buckets = {b["app"]: b for b in result["buckets"]}
        assert result["group_by"] == "app"
        assert buckets["Cursor"]["count"] == 4
        assert buckets["Cursor"]["estimated_observation_seconds"] == 120
        assert [t["title"] for t in buckets["Cursor"]["top_titles"]][:2] == ["t1", "t2"]
        assert buckets["Cursor"]["top_titles"][0]["count"] == 2
        assert buckets["Safari"]["count"] == 1
        assert buckets["Safari"]["estimated_observation_seconds"] == 0

    def test_group_by_day_and_hour_buckets(self):
        rows = [
            _screen_row("2026-06-11 10:00:00.000"),
            _screen_row("2026-06-11 10:30:00.000"),
            _screen_row("2026-06-12 09:00:00.000"),
        ]
        with patch.object(other_handler.screen_activity_db, "get_screen_activity_page", return_value=(rows, False)):
            day = sse.execute_tool(UID, "get_screen_activity", {"group_by": "day"})
            hour = sse.execute_tool(UID, "get_screen_activity", {"group_by": "hour"})
        assert [b["day"] for b in day["buckets"]] == ["2026-06-11", "2026-06-12"]
        assert day["buckets"][0]["count"] == 2
        # Cross-day gap is never bridged (different bucket AND >5 min).
        assert day["buckets"][1]["estimated_observation_seconds"] == 0
        # 10:00 and 10:30 share the 10:00 hour bucket.
        assert [b["hour"] for b in hour["buckets"]] == ["2026-06-11 10:00", "2026-06-12 09:00"]
        assert hour["buckets"][0]["count"] == 2

    def test_top_titles_capped(self):
        rows = [
            _screen_row(f"2026-06-11 10:{i:02d}:00.000", title=f"title-{i:02d}")
            for i in range(MCP_SCREEN_ACTIVITY_TOP_TITLES + 3)
        ]
        with patch.object(other_handler.screen_activity_db, "get_screen_activity_page", return_value=(rows, False)):
            result = sse.execute_tool(UID, "get_screen_activity", {"group_by": "app"})
        assert len(result["buckets"][0]["top_titles"]) == MCP_SCREEN_ACTIVITY_TOP_TITLES

    def test_gap_bound_constant_is_five_minutes(self):
        assert MCP_SCREEN_ACTIVITY_OBSERVATION_GAP_SECONDS == 300

    def test_keyset_cursor_roundtrip(self):
        first = [_screen_row("2026-06-11 10:00:00.000", doc_id="s1")]
        second = [_screen_row("2026-06-11 10:01:00.000", doc_id="s2")]
        page = MagicMock(side_effect=[(first, True), (second, False)])
        with patch.object(other_handler.screen_activity_db, "get_screen_activity_page", page):
            page1 = sse.execute_tool(UID, "get_screen_activity", {"limit": 1})
            cursor = page1["next_cursor"]
            page2 = sse.execute_tool(UID, "get_screen_activity", {"limit": 1, "cursor": cursor})
        assert page.call_count == 2
        # The resume position is the last row's (timestamp, doc id) keyset.
        assert page.call_args.kwargs["after"] == ("2026-06-11 10:00:00.000", "s1")
        assert page2["screen_activity"][0]["id"] == "s2"
        assert "next_cursor" not in page2

    def test_large_limit_up_to_1000(self):
        with patch.object(
            other_handler.screen_activity_db, "get_screen_activity_page", return_value=([], False)
        ) as page:
            sse.execute_tool(UID, "get_screen_activity", {"limit": 1000})
            assert page.call_args.kwargs["limit"] == 1000
            # parse_mcp_int clamps oversized limits to the cap (same convention
            # as the other list tools) — the store still sees a bounded page.
            sse.execute_tool(UID, "get_screen_activity", {"limit": 10_000})
            assert page.call_args.kwargs["limit"] == 1000

    def test_invalid_group_by_rejected(self):
        with pytest.raises(ToolExecutionError) as exc:
            sse.execute_tool(UID, "get_screen_activity", {"group_by": "minute"})
        assert exc.value.code == -32602

    def test_summary_with_group_by_rejected_before_db(self):
        with (
            patch.object(other_handler.screen_activity_db, "get_screen_activity_page") as page_fn,
            patch.object(other_handler.screen_activity_db, "get_screen_activity_summary") as summary_fn,
        ):
            with pytest.raises(ToolExecutionError) as exc:
                sse.execute_tool(UID, "get_screen_activity", {"summary": True, "group_by": "app"})
        assert exc.value.code == -32602
        page_fn.assert_not_called()
        summary_fn.assert_not_called()

    def test_legacy_summary_path_preserved_and_cursor_rejected(self):
        summary = {"apps": {}, "total_screenshots": 3, "coverage": {}}
        with (
            patch.object(
                other_handler.screen_activity_db, "get_screen_activity_summary", return_value=summary
            ) as summary_fn,
            patch.object(other_handler.screen_activity_db, "get_screen_activity_page") as page_fn,
        ):
            result = sse.execute_tool(UID, "get_screen_activity", {"summary": True})
            assert result["total_screenshots"] == 3
            page_fn.assert_not_called()
            summary_fn.assert_called_once()
            with pytest.raises(ToolExecutionError) as exc:
                sse.execute_tool(UID, "get_screen_activity", {"summary": True, "cursor": "abc"})
            assert exc.value.code == -32602


class _FakeDoc:
    def __init__(self, doc_id, data):
        self.id = doc_id
        self._data = data

    def to_dict(self):
        return dict(self._data)


class _FakeDocRef:
    """Stand-in for ``collection.document(id)`` cursor references."""

    def __init__(self, doc_id):
        self.id = doc_id


class _RecordingQuery:
    """Minimal Firestore-query fake honoring (timestamp, doc id) keyset order."""

    def __init__(self, docs):
        self.docs = docs
        self.order_fields = []
        self.after_values = None
        self.limit_value = None

    def order_by(self, field, direction=None):
        self.order_fields.append(field)
        return self

    def where(self, filter=None):
        return self

    def document(self, doc_id):
        return _FakeDocRef(doc_id)

    def start_after(self, values):
        self.after_values = dict(values)
        return self

    def limit(self, n):
        self.limit_value = n
        return self

    def stream(self):
        rows = self.docs
        if self.after_values is not None:
            ts = self.after_values["timestamp"]
            doc_id = self.after_values["__name__"].id
            rows = [d for d in rows if (d._data["timestamp"], d.id) > (ts, doc_id)]
        return iter(rows[: self.limit_value])


class TestScreenActivityPageQuery:
    def _stub_collection(self, screen_activity_db, query):
        mock_db = MagicMock()
        mock_db.collection.return_value.document.return_value.collection.return_value = query
        return patch.object(screen_activity_db, "db", mock_db)

    def test_keyset_order_lookahead_and_resume(self):
        screen_activity_db = _import_real_module("database.screen_activity")

        docs = [
            _FakeDoc("a", {"timestamp": "2026-06-11 10:00:00.000"}),
            _FakeDoc("b", {"timestamp": "2026-06-11 10:00:00.000"}),
            _FakeDoc("c", {"timestamp": "2026-06-11 10:01:00.000"}),
        ]
        query = _RecordingQuery(docs)
        with self._stub_collection(screen_activity_db, query):
            rows, has_more = screen_activity_db.get_screen_activity_page(UID, limit=2)
        assert query.order_fields == ["timestamp", "__name__"]
        assert query.limit_value == 3  # limit + 1 lookahead
        assert [r["id"] for r in rows] == ["a", "b"]
        assert has_more is True

        query2 = _RecordingQuery(docs)
        with self._stub_collection(screen_activity_db, query2):
            rows2, has_more2 = screen_activity_db.get_screen_activity_page(
                UID, limit=2, after=("2026-06-11 10:00:00.000", "b")
            )
        assert query2.after_values["timestamp"] == "2026-06-11 10:00:00.000"
        assert query2.after_values["__name__"].id == "b"
        assert [r["id"] for r in rows2] == ["c"]
        assert has_more2 is False


class TestCursorContract:
    def _foreign_cursor(self, *, kind="get_memories", uid=UID, filters=None):
        return mcp_cursors.encode_cursor(
            kind=kind,
            uid=uid,
            position={"offset": 3},
            filters=filters if filters is not None else {},
        )

    def test_encode_decode_roundtrip(self):
        filters = {"start": "2026-06-11", "app": None}
        token = mcp_cursors.encode_cursor(
            kind="get_screen_activity", uid=UID, position={"ts": "t", "id": "i"}, filters=filters
        )
        # No padding; URL-safe.
        assert "=" not in token
        position = mcp_cursors.decode_cursor(token, kind="get_screen_activity", uid=UID, filters=filters)
        assert position == {"ts": "t", "id": "i"}

    @pytest.mark.parametrize(
        "token",
        ["", "not-base64!!!", "aGVsbG8", "e30"],  # "", bad b64, "hello", "{}"
    )
    def test_malformed_cursors_rejected(self, token):
        with pytest.raises(ToolExecutionError) as exc:
            mcp_cursors.decode_cursor(token, kind="get_memories", uid=UID, filters={})
        assert exc.value.code == -32602

    def test_wrong_kind_rejected(self):
        token = self._foreign_cursor(kind="get_memories")
        with pytest.raises(ToolExecutionError):
            mcp_cursors.decode_cursor(token, kind="get_chat_messages", uid=UID, filters={})

    def test_cross_user_cursor_rejected(self):
        token = self._foreign_cursor(uid="other-user")
        with pytest.raises(ToolExecutionError):
            mcp_cursors.decode_cursor(token, kind="get_memories", uid=UID, filters={})

    def test_filter_mismatch_rejected(self):
        token = self._foreign_cursor(filters={"categories": ["work"]})
        with pytest.raises(ToolExecutionError):
            mcp_cursors.decode_cursor(token, kind="get_memories", uid=UID, filters={"categories": []})

    def test_all_offset_list_tools_advertise_cursor(self):
        for name in (
            "get_memories",
            "get_conversations",
            "get_action_items",
            "get_chat_messages",
            "get_daily_summaries",
            "get_screen_activity",
        ):
            properties = TOOLS_BY_NAME[name].input_schema["properties"]
            assert "cursor" in properties, name
            assert properties["cursor"]["type"] == "string"

    def test_action_items_cursor_roundtrip(self):
        items = [{"id": f"a{i}", "description": "d", "completed": False} for i in range(3)]
        fake = MagicMock(return_value=items)
        with patch.object(action_items_handler.action_items_db, "get_action_items", fake):
            page1 = sse.execute_tool(UID, "get_action_items", {"limit": 2})
            cursor = page1["next_cursor"]
            assert len(page1["action_items"]) == 2
            # limit+1 lookahead asked for 3 and got 3 -> more rows exist.
            assert fake.call_args.kwargs["limit"] == 3
            sse.execute_tool(UID, "get_action_items", {"limit": 2, "cursor": cursor})
            assert fake.call_args.kwargs["offset"] == 2

    def test_cursor_and_nonzero_offset_are_mutually_exclusive(self):
        token = self._foreign_cursor(
            kind="get_action_items",
            filters={
                "completed": None,
                "due_start": None,
                "due_end": None,
            },
        )
        with patch.object(action_items_handler.action_items_db, "get_action_items", MagicMock()):
            with pytest.raises(ToolExecutionError) as exc:
                sse.execute_tool(UID, "get_action_items", {"offset": 5, "cursor": token})
        assert exc.value.code == -32602

    def test_memories_cursor_roundtrip_advances_offset(self):
        collected = {"memories": [{"id": f"m{i}"} for i in range(20)], "has_more": True, "more_in_window": True}
        collector = MagicMock(return_value=dict(collected))
        with (
            patch.object(memories_handler, "collect_filtered_memories", collector),
            patch.object(memories_handler, "authorize_memory_external_default_memory_read", return_value=ALLOWED),
            patch.object(memories_handler, "MemoryService"),
        ):
            page1 = sse.execute_tool(UID, "get_memories", {"limit": 20}, _memory_ctx())
            sse.execute_tool(UID, "get_memories", {"cursor": page1["next_cursor"]}, _memory_ctx())
        assert collector.call_args.kwargs["offset"] == 20

    def test_memories_cursor_rejects_filter_change(self):
        collected = {"memories": [{"id": "m0"}], "has_more": True, "more_in_window": True}
        with (
            patch.object(memories_handler, "collect_filtered_memories", return_value=dict(collected)),
            patch.object(memories_handler, "authorize_memory_external_default_memory_read", return_value=ALLOWED),
            patch.object(memories_handler, "MemoryService"),
        ):
            page1 = sse.execute_tool(UID, "get_memories", {"limit": 20}, _memory_ctx())
            with pytest.raises(ToolExecutionError) as exc:
                sse.execute_tool(
                    UID,
                    "get_memories",
                    {"cursor": page1["next_cursor"], "categories": ["work"]},
                    _memory_ctx(),
                )
        assert exc.value.code == -32602

    def test_daily_summaries_cursor_roundtrip(self):
        rows = [{"date": f"2026-06-{10 + i}"} for i in range(3)]
        fake = MagicMock(side_effect=[rows, rows[2:]])
        with patch.object(other_handler.daily_summaries_db, "get_daily_summaries", fake):
            page1 = sse.execute_tool(UID, "get_daily_summaries", {"limit": 2})
            assert len(page1["daily_summaries"]) == 2
            page2 = sse.execute_tool(UID, "get_daily_summaries", {"limit": 2, "cursor": page1["next_cursor"]})
        assert fake.call_args_list[-1].kwargs["offset"] == 2

    def test_chat_messages_cursor_roundtrip(self):
        msgs = [{"id": f"m{i}", "text": "t", "sender": "ai", "type": "text", "created_at": None} for i in range(3)]
        fake = MagicMock(side_effect=[msgs, msgs[2:]])
        with patch.object(other_handler.chat_db, "get_messages", fake):
            page1 = sse.execute_tool(UID, "get_chat_messages", {"limit": 2})
            sse.execute_tool(UID, "get_chat_messages", {"limit": 2, "cursor": page1["next_cursor"]})
        assert fake.call_args_list[-1].kwargs["offset"] == 2
        assert fake.call_args_list[-1].kwargs["limit"] == 3  # lookahead preserved on resume

    def test_oversized_cursor_rejected_before_decode(self):
        token = "x" * (mcp_cursors.CURSOR_MAX_TOKEN_CHARS + 1)
        with pytest.raises(ToolExecutionError) as exc:
            mcp_cursors.decode_cursor(token, kind="get_memories", uid=UID, filters={})
        assert exc.value.code == -32602


class _DescKeysetQuery:
    """Firestore-query fake honoring ``(created_at DESC, __name__ DESC)`` order."""

    def __init__(self, docs):
        self.docs = docs
        self.order_fields = []
        self.after_values = None
        self.limit_value = None

    def order_by(self, field, direction=None):
        self.order_fields.append(field)
        return self

    def where(self, filter=None):
        return self

    def select(self, _fields):
        return self

    def document(self, doc_id):
        return _FakeDocRef(doc_id)

    def start_after(self, values):
        self.after_values = dict(values)
        return self

    def limit(self, n):
        self.limit_value = n
        return self

    def stream(self):
        rows = self.docs
        if self.after_values is not None:
            ts = self.after_values["created_at"]
            doc_id = self.after_values["__name__"].id
            rows = [d for d in rows if (d._data["created_at"], d.id) < (ts, doc_id)]
        return iter(rows[: self.limit_value])


class TestConversationKeysetPage:
    def _stub_client(self, query):
        pages_db = _import_real_module("database.mcp_conversation_pages")

        client = MagicMock()
        client.collection.return_value.document.return_value.collection.return_value = query
        return patch.object(pages_db, "get_firestore_client", return_value=client)

    def test_tombstones_are_skipped_and_the_lookahead_row_is_not_lost(self):
        pages_db = _import_real_module("database.mcp_conversation_pages")

        t0 = datetime(2026, 6, 11, 10, 0, tzinfo=timezone.utc)
        docs = [
            _FakeDoc("v5", {"created_at": t0 + timedelta(minutes=5), "deleted": False}),
            _FakeDoc("t4", {"created_at": t0 + timedelta(minutes=4), "deleted": True}),
            _FakeDoc("v3", {"created_at": t0 + timedelta(minutes=3), "deleted": False}),
            _FakeDoc("v2", {"created_at": t0 + timedelta(minutes=2), "deleted": False}),
            _FakeDoc("t1", {"created_at": t0 + timedelta(minutes=1), "deleted": True}),
            _FakeDoc("v0", {"created_at": t0, "deleted": False}),
        ]
        query = _DescKeysetQuery(docs)
        with self._stub_client(query):
            page, resume = pages_db.get_mcp_conversation_cards_page(UID, 2)
        # Each raw-window rebuild reorders (created_at, __name__) descending.
        assert query.order_fields[:2] == ["created_at", "__name__"]
        assert len(query.order_fields) % 2 == 0
        assert all(
            pair == ("created_at", "__name__") for pair in zip(query.order_fields[::2], query.order_fields[1::2])
        )
        assert [d["id"] for d in page] == ["v5", "v3"]
        # Resume after the last EMITTED row, not the lookahead row: v2 must be
        # re-fetched as the first row of the next page rather than skipped.
        assert resume == (t0 + timedelta(minutes=3), "v3")

        query2 = _DescKeysetQuery(docs)
        with self._stub_client(query2):
            page2, resume2 = pages_db.get_mcp_conversation_cards_page(UID, 2, after=resume)
        assert [d["id"] for d in page2] == ["v2", "v0"]
        assert resume2 is None

    def test_equal_created_at_rows_resume_by_document_id(self):
        pages_db = _import_real_module("database.mcp_conversation_pages")

        t0 = datetime(2026, 6, 11, 10, 0, tzinfo=timezone.utc)
        docs = [
            _FakeDoc("b", {"created_at": t0, "deleted": False}),
            _FakeDoc("a", {"created_at": t0, "deleted": False}),
        ]
        query = _DescKeysetQuery(docs)
        with self._stub_client(query):
            page, resume = pages_db.get_mcp_conversation_cards_page(UID, 1)
        assert [d["id"] for d in page] == ["b"]
        assert resume == (t0, "b")

        query2 = _DescKeysetQuery(docs)
        with self._stub_client(query2):
            page2, resume2 = pages_db.get_mcp_conversation_cards_page(UID, 1, after=resume)
        assert [d["id"] for d in page2] == ["a"]
        assert resume2 is None

    def test_scan_budget_resumes_past_scanned_tombstones(self):
        pages_db = _import_real_module("database.mcp_conversation_pages")

        t0 = datetime(2026, 6, 11, 10, 0, tzinfo=timezone.utc)
        docs = [
            _FakeDoc(f"t{i:03d}", {"created_at": t0 - timedelta(minutes=i), "deleted": True})
            for i in range(pages_db.MCP_CARD_PAGE_SCAN_BUDGET + 50)
        ]
        query = _DescKeysetQuery(docs)
        with self._stub_client(query):
            # limit=9 gives 10-row windows landing exactly on the scan budget.
            page, resume = pages_db.get_mcp_conversation_cards_page(UID, 9)
        assert page == []
        # The budget-truncated scan still advances the resume position past
        # every scanned tombstone, so the next page makes progress.
        assert resume is not None
        last_scanned = docs[pages_db.MCP_CARD_PAGE_SCAN_BUDGET - 1]
        assert resume == (last_scanned._data["created_at"], last_scanned.id)

        query2 = _DescKeysetQuery(docs)
        with self._stub_client(query2):
            page2, resume2 = pages_db.get_mcp_conversation_cards_page(UID, 10, after=resume)
        assert page2 == []
        assert resume2 is None

    def test_enhanced_rows_pass_through_decrypt_seam(self):
        pages_db = _import_real_module("database.mcp_conversation_pages")

        t0 = datetime(2026, 6, 11, 10, 0, tzinfo=timezone.utc)
        docs = [
            _FakeDoc(
                "e1",
                {"created_at": t0, "deleted": False, "data_protection_level": "enhanced", "structured": {}},
            ),
            _FakeDoc("p1", {"created_at": t0 - timedelta(minutes=1), "deleted": False}),
        ]
        marked = lambda data, uid: {**data, "decrypted_for": uid}
        query = _DescKeysetQuery(docs)
        with (
            self._stub_client(query),
            patch.object(
                _import_real_module("database.conversations"), "_decrypt_conversation_data", side_effect=marked
            ),
        ):
            page, _resume = pages_db.get_mcp_conversation_cards_page(UID, 5)
        assert page[0]["decrypted_for"] == UID
        assert "decrypted_for" not in page[1]  # standard level untouched

    def test_none_created_at_resume_position_is_rejected(self):
        pages_db = _import_real_module("database.mcp_conversation_pages")

        query = _DescKeysetQuery([])
        with self._stub_client(query), pytest.raises(ValueError, match="keyset timestamp"):
            pages_db.get_mcp_conversation_cards_page(UID, 1, after=(None, "x"))


class TestGetConversationsKeysetCursor:
    def test_cursor_roundtrip_resumes_keyset(self):
        t0 = datetime(2026, 6, 11, 10, 0, tzinfo=timezone.utc)
        page_fn = MagicMock(side_effect=[([_conversation("c2")], (t0, "c2")), ([_conversation("c1")], None)])
        with patch.object(conversations_handler.mcp_conversation_pages, "get_mcp_conversation_cards_page", page_fn):
            page1 = sse.execute_tool(UID, "get_conversations", {"limit": 1})
            assert page_fn.call_args.kwargs["after"] is None
            page2 = sse.execute_tool(UID, "get_conversations", {"limit": 1, "cursor": page1["next_cursor"]})
        assert page_fn.call_args_list[-1].kwargs["after"] == (t0, "c2")
        assert [c["id"] for c in page2["conversations"]] == ["c1"]
        assert "next_cursor" not in page2

    def test_cursor_and_offset_are_mutually_exclusive(self):
        token = mcp_cursors.encode_cursor(
            kind="get_conversations",
            uid=UID,
            position={"ts": "2026-06-11T10:00:00Z", "id": "c1"},
            filters={"categories": [], "start": None, "end": None},
        )
        with pytest.raises(ToolExecutionError) as exc:
            sse.execute_tool(UID, "get_conversations", {"cursor": token, "offset": 5})
        assert exc.value.code == -32602

    def test_foreign_tool_cursor_rejected(self):
        token = mcp_cursors.encode_cursor(kind="get_chat_messages", uid=UID, position={"offset": 3}, filters={})
        with pytest.raises(ToolExecutionError) as exc:
            sse.execute_tool(UID, "get_conversations", {"cursor": token})
        assert exc.value.code == -32602

    def test_bad_keyset_timestamp_rejected(self):
        token = mcp_cursors.encode_cursor(
            kind="get_conversations",
            uid=UID,
            position={"ts": "not-a-timestamp", "id": "c1"},
            filters={"categories": [], "start": None, "end": None},
        )
        with pytest.raises(ToolExecutionError) as exc:
            sse.execute_tool(UID, "get_conversations", {"cursor": token})
        assert exc.value.code == -32602


class _Mem:
    def __init__(self, memory_id, *, tags=None):
        self._data = {
            "id": memory_id,
            "content": f"fact {memory_id}",
            "category": "manual",
            "tags": tags or [],
            "created_at": "2026-06-11T10:00:00Z",
        }

    def model_dump(self, mode="json"):
        return dict(self._data)


def _uml_page(memories, *, next_cursor=None, truncated=False):
    return SimpleNamespace(memories=memories, next_cursor=next_cursor, truncated=truncated)


class TestMemoryKeysetPage:
    def _read_auth(self):
        return patch.object(memories_handler, "authorize_memory_external_default_memory_read", return_value=ALLOWED)

    def test_updated_desc_uses_read_page_and_wraps_uml_cursor(self):
        service = MagicMock()
        service.read_page.side_effect = [
            _uml_page([_Mem("m1"), _Mem("m2")], next_cursor="uml.a"),
            _uml_page([_Mem("m3")]),
        ]
        with self._read_auth(), patch.object(memories_handler, "MemoryService", return_value=service):
            page1 = sse.execute_tool(UID, "get_memories", {"limit": 2, "sort": "updated_desc"}, _memory_ctx())
            assert [m["id"] for m in page1["memories"]] == ["m1", "m2"]
            page2 = sse.execute_tool(
                UID,
                "get_memories",
                {"limit": 2, "sort": "updated_desc", "cursor": page1["next_cursor"]},
                _memory_ctx(),
            )
        assert service.read_page.call_count == 2
        assert service.read_page.call_args_list[-1].kwargs["cursor"] == "uml.a"
        assert [m["id"] for m in page2["memories"]] == ["m3"]
        assert "next_cursor" not in page2
        service.read.assert_not_called()

    def test_scoring_desc_also_uses_read_page(self):
        service = MagicMock()
        service.read_page.return_value = _uml_page([_Mem("m1")])
        with self._read_auth(), patch.object(memories_handler, "MemoryService", return_value=service):
            result = sse.execute_tool(UID, "get_memories", {"limit": 5, "sort": "scoring_desc"}, _memory_ctx())
        assert [m["id"] for m in result["memories"]] == ["m1"]
        service.read_page.assert_called_once()
        service.read.assert_not_called()

    def test_default_created_desc_uses_bounded_scan_not_read_page(self):
        service = MagicMock()
        service.read.return_value = []
        with self._read_auth(), patch.object(memories_handler, "MemoryService", return_value=service):
            sse.execute_tool(UID, "get_memories", {"limit": 5}, _memory_ctx())
        service.read.assert_called_once()
        service.read_page.assert_not_called()

    def test_truncated_inner_page_flags_scan_truncated_without_cursor(self):
        service = MagicMock()
        service.read_page.return_value = _uml_page([_Mem("m1")], truncated=True)
        with self._read_auth(), patch.object(memories_handler, "MemoryService", return_value=service):
            result = sse.execute_tool(UID, "get_memories", {"limit": 5, "sort": "updated_desc"}, _memory_ctx())
        assert result["scan_truncated"] is True
        assert result["has_more"] is False
        assert "next_cursor" not in result

    def test_activity_rows_do_not_stall_paging(self):
        service = MagicMock()
        service.read_page.side_effect = [
            _uml_page([_Mem("a1", tags=["activity"])], next_cursor="uml.1"),
            _uml_page([_Mem("d1")]),
        ]
        with self._read_auth(), patch.object(memories_handler, "MemoryService", return_value=service):
            result = sse.execute_tool(UID, "get_memories", {"limit": 2, "sort": "updated_desc"}, _memory_ctx())
        assert [m["id"] for m in result["memories"]] == ["d1"]
        assert service.read_page.call_count == 2

    def test_bounded_scan_walk_terminates_at_scan_cap(self):
        service = MagicMock()

        def _read(_uid, *, limit, offset):
            return [_Mem(f"m{offset + i}") for i in range(max(0, min(limit, 200 - offset)))]

        service.read.side_effect = _read
        seen = []
        pages = 0
        cursor = None
        with self._read_auth(), patch.object(memories_handler, "MemoryService", return_value=service):
            for _ in range(30):
                args = {"limit": 20, "sort": "created_desc"}
                if cursor is not None:
                    args["cursor"] = cursor
                result = sse.execute_tool(UID, "get_memories", args, _memory_ctx())
                pages += 1
                seen.extend(m["id"] for m in result["memories"])
                cursor = result.get("next_cursor")
                if cursor is None:
                    break
        # 200 scanned candidates drain in ten 20-item pages, then the walk
        # ends honestly: scan_truncated stays visible, no dangling cursor.
        assert pages == 10
        assert cursor is None
        assert result["scan_truncated"] is True
        assert len(seen) == len(set(seen)) == 200


class TestBatchResponseBudgetOverHttp:
    def test_serialized_body_stays_under_budget_with_unicode(self):
        # utils.executors is MagicMock-stubbed by sibling test files in shared
        # runs; bypass executor offloading entirely for the HTTP path.
        async def _run_inline(_executor, fn, *args, **kwargs):
            return fn(*args, **kwargs)

        mcp_sse = _import_real_module("routers.mcp_sse")
        app = FastAPI()
        app.include_router(mcp_sse.router)
        client = TestClient(app)
        auth = MCPAuthContext(uid=UID, auth_type="oauth", scopes=["conversations.read"], client_id="t")
        text = "x" * 10_000 + "é" * 1_000
        rows = {f"c{i}": _conversation(f"c{i}", text=text) for i in range(6)}
        body = {
            "jsonrpc": "2.0",
            "id": 7,
            "method": "tools/call",
            "params": {
                "name": "get_conversations_by_ids",
                "arguments": {"conversation_ids": list(rows)},
            },
        }
        with (
            patch.object(mcp_transport, "run_blocking", _run_inline),
            patch.object(mcp_transport, "authenticate_mcp_request", return_value=auth),
            patch.object(mcp_transport, "check_rate_limit_inline"),
            patch.object(mcp_transport, "check_rate_limit_context"),
            patch.object(mcp_transport, "log_mcp_request"),
            patch.object(mcp_transport, "schedule_mcp_active"),
            patch.object(mcp_transport, "schedule_mcp_tool_call"),
            patch.object(
                conversations_handler.conversations_db,
                "get_mcp_conversations_by_id",
                side_effect=_batch_fetch(rows),
            ),
        ):
            plain = client.post("/v1/mcp", json=body)
            framed = client.post("/v1/mcp", json=body, headers={"Accept": "text/event-stream"})
        assert plain.status_code == 200
        assert len(plain.text) <= MCP_CONVERSATION_BATCH_RESPONSE_MAX_CHARS
        assert len(framed.text) <= MCP_CONVERSATION_BATCH_RESPONSE_MAX_CHARS
        payload = plain.json()["result"]["structuredContent"]
        assert payload["truncated"] is True
        returned = {item["id"] for item in payload["conversations"]}
        omitted = set(rows) - returned
        assert omitted
        assert not (omitted & set(payload["not_found"]))


class TestFirestoreSdkCursorTransform:
    """The real SDK must translate ``__name__`` cursor values into document
    references for the query shapes both keyset paths build."""

    def _firestore(self):
        firestore = _import_real_firestore()
        if not isinstance(getattr(firestore, "__file__", None), str):
            pytest.skip("google.cloud.firestore is stubbed in this pytest process")
        return firestore

    def _client(self):
        firestore = self._firestore()
        from google.auth.credentials import AnonymousCredentials

        return firestore.Client(project="test-project", credentials=AnonymousCredentials())

    def test_screen_activity_keyset_protobuf(self):
        col = self._client().collection("users").document(UID).collection("screen_activity")
        query = (
            col.order_by("timestamp")
            .order_by("__name__")
            .start_after({"timestamp": "2026-06-11 10:00:00.000", "__name__": col.document("doc-9")})
        )
        start_at = query._to_protobuf().start_at
        assert start_at.values[0].string_value == "2026-06-11 10:00:00.000"
        assert start_at.values[1].reference_value.endswith(f"/users/{UID}/screen_activity/doc-9")

    def test_conversation_keyset_protobuf(self):
        firestore = self._firestore()

        col = self._client().collection("users").document(UID).collection("conversations")
        query = (
            col.order_by("created_at", direction=firestore.Query.DESCENDING)
            .order_by("__name__", direction=firestore.Query.DESCENDING)
            .start_after(
                {
                    "created_at": datetime(2026, 6, 11, 10, tzinfo=timezone.utc),
                    "__name__": col.document("conv-9"),
                }
            )
        )
        start_at = query._to_protobuf().start_at
        assert start_at.values[0]._pb.WhichOneof("value_type") == "timestamp_value"
        assert start_at.values[1].reference_value.endswith(f"/users/{UID}/conversations/conv-9")


class TestAnalyticsAndInstructions:
    def test_new_tools_have_closed_operations(self):
        assert mcp_analytics._TOOL_OPERATIONS["get_conversations_by_ids"] == "conversation_get"
        assert mcp_analytics._TOOL_OPERATIONS["create_memories"] == "memories_batch"
        assert "get_conversations_by_ids" in mcp_analytics._KNOWN_TOOLS
        assert "create_memories" in mcp_analytics._KNOWN_TOOLS

    def test_result_counts_for_new_tools(self):
        assert (
            mcp_analytics.result_count_for_tool_result(
                "get_conversations_by_ids",
                {"conversations": [{"id": "a"}, {"id": "b"}], "not_found": ["x"], "truncated": False},
            )
            == 2
        )
        assert (
            mcp_analytics.result_count_for_tool_result(
                "create_memories", {"results": [{"status": "created"}, {"status": "duplicate"}]}
            )
            == 2
        )
        assert (
            mcp_analytics.result_count_for_tool_result(
                "get_screen_activity", {"group_by": "day", "buckets": [{"day": "d"}]}
            )
            == 1
        )

    def test_instructions_recommend_batch_fetch_and_grouping(self):
        assert "`get_conversations_by_ids`" in MCP_SERVER_INSTRUCTIONS
        assert "group_by" in MCP_SERVER_INSTRUCTIONS
        assert "`create_memories`" in MCP_SERVER_INSTRUCTIONS
        # The stateless transport contract still bans steering toward JSON-RPC
        # batches or parallel POSTs — even though the tool is named create_memories.
        assert "batch" not in MCP_SERVER_INSTRUCTIONS
        assert "parallel" not in MCP_SERVER_INSTRUCTIONS
