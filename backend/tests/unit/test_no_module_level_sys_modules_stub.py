"""Guard: memory unit tests must not assign sys.modules at import time."""

from __future__ import annotations

import ast
from pathlib import Path


def _is_sys_modules_mutation(node: ast.AST) -> bool:
    if isinstance(node, ast.Assign):
        targets = node.targets
    elif isinstance(node, ast.AugAssign):
        targets = [node.target]
    else:
        return False

    for target in targets:
        if isinstance(target, ast.Subscript):
            value = target.value
            if isinstance(value, ast.Attribute) and value.attr == "modules":
                if isinstance(value.value, ast.Name) and value.value.id == "sys":
                    return True
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
            func = node.value.func
            if (
                isinstance(func, ast.Attribute)
                and func.attr == "setdefault"
                and isinstance(func.value, ast.Attribute)
                and func.value.attr == "modules"
                and isinstance(func.value.value, ast.Name)
                and func.value.value.id == "sys"
            ):
                return True
    return False


def _module_level_sys_modules_offenders(source_path: Path) -> list[str]:
    tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
    offenders: list[str] = []
    for node in tree.body:
        if _is_sys_modules_mutation(node):
            offenders.append(f"{source_path.name}:{node.lineno}")
    return offenders


def test_no_module_level_sys_modules_stub_in_unit_tests():
    unit_dir = Path(__file__).resolve().parent
    guarded_filenames = (
        "test_memory_domain.py",
        "test_memory_service_parity.py",
        "test_memory_temporal_brain.py",
        "test_ws_b_short_term_lifecycle.py",
        "test_ws_c_backfill.py",
        "test_ws_g_module_aliases.py",
        "test_ws_i_hardening.py",
        "test_ws_i_write_convergence.py",
        "test_ws_j_delete_privacy.py",
        "test_ws_k_layer_field.py",
        "test_ws_l_surface_routing.py",
        "test_ws_m_atom_keyword_index.py",
        "test_ws_n_graph_traversal.py",
        "test_mcp_search_memories.py",
        "test_upstream_boundary.py",
        "test_canonical_memory_vectors.py",
        "test_v17_read_api.py",
        "test_v17_product_memory_router.py",
    )
    guarded_paths = [unit_dir / name for name in guarded_filenames]

    all_offenders: list[str] = []
    for path in guarded_paths:
        if path.name == "test_no_module_level_sys_modules_stub.py":
            continue
        all_offenders.extend(_module_level_sys_modules_offenders(path))

    assert not all_offenders, (
        "Module-level sys.modules stubs leak across pytest collection order. "
        "Move stubs into module-scoped autouse fixtures with teardown restore "
        f"(see tests/unit/memory_import_isolation.py). Offenders:\n  " + "\n  ".join(all_offenders)
    )
