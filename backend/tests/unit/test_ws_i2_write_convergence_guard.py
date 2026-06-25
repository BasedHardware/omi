"""WS-I.2 regression guard: canonical-cohort writers must not hit legacy memories_db writes."""

from __future__ import annotations

import ast
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]

WRITER_FILES = [
    BACKEND_DIR / "routers" / "memories.py",
    BACKEND_DIR / "routers" / "mcp.py",
    BACKEND_DIR / "routers" / "mcp_sse.py",
    BACKEND_DIR / "routers" / "developer.py",
    BACKEND_DIR / "utils" / "conversations" / "memories.py",
    BACKEND_DIR / "utils" / "x_connector.py",
    BACKEND_DIR / "utils" / "consolidation" / "worker.py",
]

LEGACY_WRITE_CALLS = frozenset(
    {
        "memories_db.create_memory",
        "memories_db.save_memories",
    }
)


def _legacy_write_allowed(source_lines: list[str], lineno: int) -> bool:
    """Legacy writes are allowed only after a canonical cohort gate in the same function."""
    window = source_lines[max(0, lineno - 80) : lineno]
    if not any("CANONICAL" in line or "resolve_memory_system" in line for line in window):
        return False
    if any(line.strip().startswith("else:") for line in window[-8:]):
        return True
    # Early-return canonical branch: legacy path follows for non-canonical cohort only.
    for idx, line in enumerate(window):
        if "CANONICAL" not in line:
            continue
        following = window[idx : idx + 40]
        if any("return" in follow for follow in following):
            return True
    return False


def _canonical_guarded_legacy_writes(path: Path) -> list[str]:
    source = path.read_text(encoding="utf-8")
    source_lines = source.splitlines()
    tree = ast.parse(source, filename=str(path))
    violations: list[str] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        call_name = None
        if isinstance(node.func, ast.Attribute):
            if isinstance(node.func.value, ast.Name):
                call_name = f"{node.func.value.id}.{node.func.attr}"
        if call_name not in LEGACY_WRITE_CALLS:
            continue
        if _legacy_write_allowed(source_lines, node.lineno):
            continue
        line = source_lines[node.lineno - 1]
        violations.append(f"{path.relative_to(BACKEND_DIR)}:{node.lineno}: {line.strip()}")

    return violations


def test_canonical_writer_files_do_not_call_legacy_writes_without_cohort_gate():
    all_violations: list[str] = []
    for path in WRITER_FILES:
        assert path.exists(), f"missing writer file: {path}"
        all_violations.extend(_canonical_guarded_legacy_writes(path))

    assert not all_violations, "ungated legacy memory writes in canonical writer surfaces:\n" + "\n".join(
        all_violations
    )


def test_memories_router_routes_canonical_create_through_memory_service():
    source = (BACKEND_DIR / "routers" / "memories.py").read_text(encoding="utf-8")
    assert "pin_memory_system(uid, db_client=db_client) == MemorySystem.CANONICAL" in source
    assert "memory_service.write(uid, payload)" in source
    create_section = source.split("async def create_memory", 1)[1].split("@router.post", 1)[0]
    canonical_pos = create_section.find("MemorySystem.CANONICAL")
    legacy_pos = create_section.find("memories_db.create_memory")
    assert canonical_pos != -1 and legacy_pos != -1
    assert canonical_pos < legacy_pos
