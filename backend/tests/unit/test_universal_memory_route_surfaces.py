"""Universal-memory routing guards for released backend surfaces.

These are intentionally source-level ratchets: the heavy routers are covered by
their contract suites, while this guard prevents a new UID/cohort selector or a
direct historical-store mutation from reappearing in a public memory surface.
"""

from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]

ROUTE_FILES = (
    "routers/memories.py",
    "routers/developer.py",
    "routers/integration.py",
    "routers/conversations.py",
    "routers/knowledge_graph.py",
    "routers/mcp.py",
    "routers/mcp_sse.py",
    "utils/x_connector.py",
    "utils/retrieval/tool_services/memories.py",
    "utils/retrieval/tools/memory_tools.py",
    "utils/retrieval/tools/preference_tools.py",
)


def test_public_memory_surfaces_do_not_select_legacy_or_canonical_by_uid():
    forbidden = (
        "pin_memory_system(",
        "resolve_memory_system(",
        "canonical_read_enabled(",
        "canonical_write_decision(",
        "if memory_system ==",
        "if memory_system !=",
        "import database.memories",
        "from database import memories",
    )
    for relative in ROUTE_FILES:
        source = (BACKEND / relative).read_text(encoding="utf-8")
        assert not any(marker in source for marker in forbidden), relative


def test_public_memory_writes_route_through_memory_service():
    for relative in ROUTE_FILES:
        source = (BACKEND / relative).read_text(encoding="utf-8")
        if relative.endswith(
            (
                "memories.py",
                "developer.py",
                "integration.py",
                "conversations.py",
                "mcp.py",
                "mcp_sse.py",
                "x_connector.py",
                "memory_tools.py",
                "preference_tools.py",
            )
        ):
            # Every file in this list owns either a memory write or a read path;
            # the service import is the stable routing seam for both.
            assert "MemoryService" in source, relative


def test_no_public_memory_mirror_delete_helpers_remain():
    source = (BACKEND / "routers/memories.py").read_text(encoding="utf-8")
    assert "_mirror_delete" not in source
    assert "_purge_legacy_memories" not in source


def test_v3_get_has_no_cutover_runtime_and_exposes_mixed_view_cursor():
    source = (BACKEND / "routers/memories.py").read_text(encoding="utf-8")
    assert "production_runtime" not in source
    assert "composed_get_service" not in source
    assert "memory_runtime" not in source
    assert "X-Omi-Memory-Next-Cursor" in source
    assert "read_page" in source
    assert "Memory cursor pagination is unavailable" not in source
