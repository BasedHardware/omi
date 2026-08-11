"""Developer-memory authorization order under universal memory authority."""

import ast
from pathlib import Path

ROUTER = Path(__file__).resolve().parents[2] / "routers" / "developer.py"


def _function_source(name: str) -> str:
    source = ROUTER.read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return ast.get_source_segment(source, node) or ""
    raise AssertionError(f"missing developer route function {name}")


def test_list_authorizes_app_key_before_universal_repository_read():
    source = _function_source("get_memories")
    grant = source.index("authorize_memory_external_default_memory_read")
    denial = source.index("if not app_key_grant.allowed")
    read = source.index("MemoryService(db_client=db).read")
    assert grant < denial < read


def test_search_authorizes_app_key_before_universal_repository_search():
    source = _function_source("search_memories_vector")
    grant = source.index("authorize_memory_external_default_memory_read")
    denial = source.index("if not app_key_grant.allowed")
    search = source.index("MemoryService(db_client=db).search")
    assert grant < denial < search


def test_developer_routes_cannot_select_a_uid_specific_memory_system_or_legacy_fallback():
    source = ROUTER.read_text(encoding="utf-8")
    for forbidden in (
        "pin_memory_system",
        "resolve_memory_system",
        "USE_LEGACY_SAFE",
        "use_legacy_safe",
        "memories_db.get_memories",
        "memories_db.get_memories_by_ids",
    ):
        assert forbidden not in source
