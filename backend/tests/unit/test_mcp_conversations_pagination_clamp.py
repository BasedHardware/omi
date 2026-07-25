"""Regression test: GET /v1/mcp/conversations must clamp limit/offset like every
other paginated list endpoint in routers/mcp.py.

Before the fix, `get_conversations` (routers/mcp.py) passed `limit`/`offset`
straight to `conversations_db.get_conversations(...)`, which chains Firestore
`.limit()`/`.offset()`. A negative offset/limit reaches Firestore and raises
there, escaping as an unhandled HTTP 500 instead of a clamped 200 response --
exactly the failure class the sibling MCP tool `get_conversations` in
routers/mcp_sse.py was already hardened against with `parse_mcp_int` (see
tests/unit/test_mcp_sse_pagination_bounds.py) and that every OTHER list
endpoint in routers/mcp.py already guards against: `get_memories`
(`parse_mcp_int`), `get_action_items`, `get_chat_messages`,
`get_screen_activity`, and `get_daily_summaries` (plain `max(1, min(...))` /
`max(0, ...)` clamps). `get_conversations` was the one sibling in the file
that forwarded the raw, unclamped client-supplied values.

Follows the sanctioned test seam (see tests/unit/test_workstream_router_contract.py):
import the router module normally and monkeypatch its db reference, then call
the handler function directly.
"""

import os

os.environ.setdefault('ENCRYPTION_SECRET', 'test_secret_for_ci_only_0123456789')
os.environ.setdefault('OPENAI_API_KEY', 'sk-fake')
os.environ.setdefault('PINECONE_API_KEY', 'fake')

import routers.mcp as mcp_router

UID = 'user-1'


def _make_fake_get_conversations(captured):
    def _fake(uid, limit, offset, **kwargs):
        captured['uid'] = uid
        captured['limit'] = limit
        captured['offset'] = offset
        # Mimics real google-cloud-firestore: Query.limit()/.offset() forward the raw
        # argument to the RPC, and a negative value raises there. Same simulated
        # failure used in tests/unit/test_mcp_sse_pagination_bounds.py and documented
        # throughout database/memories.py and routers/developer.py.
        if limit < 1 or offset < 0:
            raise ValueError("Firestore .limit()/.offset() requires non-negative arguments")
        return []

    return _fake


def test_negative_offset_and_limit_are_clamped_before_reaching_firestore(monkeypatch):
    """offset=-1/limit=-1 must be clamped (limit>=1, offset>=0) before the query call.

    Unclamped, this raises out of get_conversations() the same way a live Firestore
    .offset(-1) would -- an unhandled 500 for the caller.
    """
    captured = {}
    monkeypatch.setattr(mcp_router.conversations_db, "get_conversations", _make_fake_get_conversations(captured))

    result = mcp_router.get_conversations(limit=-1, offset=-1, uid=UID)

    assert result == []
    assert captured['limit'] == 1
    assert captured['offset'] == 0


def test_oversized_limit_and_offset_are_capped(monkeypatch):
    """An unbounded limit/offset must be capped so a client cannot force a full-collection
    scan (limit) or a Firestore-billed skip-scan of unbounded size (offset)."""
    captured = {}
    monkeypatch.setattr(mcp_router.conversations_db, "get_conversations", _make_fake_get_conversations(captured))

    mcp_router.get_conversations(limit=10_000_000, offset=10_000_000, uid=UID)

    assert captured['limit'] == 1000
    assert captured['offset'] == 100000


def test_normal_pagination_passes_through_unchanged(monkeypatch):
    """Sibling/normal-path control: in-range limit/offset must reach the query
    unmodified, both before and after the clamp fix."""
    captured = {}
    monkeypatch.setattr(mcp_router.conversations_db, "get_conversations", _make_fake_get_conversations(captured))

    mcp_router.get_conversations(limit=25, offset=10, uid=UID)

    assert captured['limit'] == 25
    assert captured['offset'] == 10
