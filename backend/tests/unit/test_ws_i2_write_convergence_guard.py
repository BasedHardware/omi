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
    BACKEND_DIR / "utils" / "retrieval" / "tools" / "preference_tools.py",
]

# Offline RAG script — not a live product write path (see plan WS-I.2).
EXCLUDED_OFFLINE_WRITER_FILES = [
    BACKEND_DIR / "scripts" / "rag" / "memories.py",
]

LEGACY_WRITE_CALLS = frozenset(
    {
        "memories_db.create_memory",
        "memories_db.save_memories",
        "memories_db.review_memory",
        "memories_db.refine_memory",
        "memories_db.merge_contradict_memory",
    }
)

# Explicit allowlist for deferred consolidation-wave legacy mutations (worker.py).
ALLOWLISTED_LEGACY_WRITES = frozenset(
    {
        ("utils/consolidation/worker.py", "memories_db.refine_memory"),
        ("utils/consolidation/worker.py", "memories_db.merge_contradict_memory"),
    }
)

_COHORT_GATE_MARKERS = (
    "pin_memory_system",
    "resolve_memory_system",
    "MemorySystem.CANONICAL",
)


def _legacy_write_allowed(source_lines: list[str], lineno: int, *, rel_path: str, call_name: str) -> bool:
    if (rel_path, call_name) in ALLOWLISTED_LEGACY_WRITES:
        return True

    window = source_lines[max(0, lineno - 150) : lineno]
    gate_indices = [idx for idx, line in enumerate(window) if any(marker in line for marker in _COHORT_GATE_MARKERS)]
    if not gate_indices:
        return False

    last_gate = gate_indices[-1]
    after_gate = window[last_gate:]
    if any("return" in line for line in after_gate):
        return True
    if any(line.strip().startswith("else:") for line in window[last_gate:]):
        return True
    return False


def _canonical_guarded_legacy_writes(path: Path) -> list[str]:
    source = path.read_text(encoding="utf-8")
    source_lines = source.splitlines()
    tree = ast.parse(source, filename=str(path))
    rel_path = str(path.relative_to(BACKEND_DIR))
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
        if _legacy_write_allowed(source_lines, node.lineno, rel_path=rel_path, call_name=call_name):
            continue
        line = source_lines[node.lineno - 1]
        violations.append(f"{rel_path}:{node.lineno}: {line.strip()}")

    return violations


def test_canonical_writer_files_do_not_call_legacy_writes_without_cohort_gate():
    all_violations: list[str] = []
    for path in WRITER_FILES:
        assert path.exists(), f"missing writer file: {path}"
        all_violations.extend(_canonical_guarded_legacy_writes(path))

    assert not all_violations, "ungated legacy memory writes in canonical writer surfaces:\n" + "\n".join(
        all_violations
    )


def test_offline_rag_script_excluded_from_live_writer_guard():
    for path in EXCLUDED_OFFLINE_WRITER_FILES:
        assert path.exists(), f"missing excluded offline writer: {path}"
    assert all(path not in WRITER_FILES for path in EXCLUDED_OFFLINE_WRITER_FILES)


def test_memories_router_routes_canonical_create_through_memory_service():
    source = (BACKEND_DIR / "routers" / "memories.py").read_text(encoding="utf-8")
    assert "pin_memory_system(uid, db_client=db_client) == MemorySystem.CANONICAL" in source
    assert "run_blocking(db_executor, memory_service.write, uid, payload)" in source
    create_section = source.split("async def create_memory", 1)[1].split("@router.post", 1)[0]
    canonical_pos = create_section.find("MemorySystem.CANONICAL")
    legacy_pos = create_section.find("memories_db.create_memory")
    assert canonical_pos != -1 and legacy_pos != -1
    assert canonical_pos < legacy_pos


def test_review_memory_routes_canonical_cohort_through_memory_service():
    source = (BACKEND_DIR / "routers" / "memories.py").read_text(encoding="utf-8")
    section = source.split("def review_memory", 1)[1].split("@router.patch", 1)[0]
    assert "MemorySystem.CANONICAL" in section
    assert ".review(uid, memory_id, value)" in section
    canonical_pos = section.find("MemorySystem.CANONICAL")
    legacy_pos = section.find("memories_db.review_memory")
    assert canonical_pos != -1 and legacy_pos != -1
    assert canonical_pos < legacy_pos


def test_preference_tools_routes_canonical_cohort_through_memory_service():
    source = (BACKEND_DIR / "utils" / "retrieval" / "tools" / "preference_tools.py").read_text(encoding="utf-8")
    assert "resolve_memory_system(uid) == MemorySystem.CANONICAL" in source
    assert "MemoryService().write(uid, memory_data)" in source
    canonical_pos = source.find("MemorySystem.CANONICAL")
    legacy_pos = source.find("memory_db.create_memory")
    assert canonical_pos != -1 and legacy_pos != -1
    assert canonical_pos < legacy_pos
