"""Async task-integration handlers must not block the event loop on synchronous Firestore I/O.

routers/task_integrations.py has async route handlers (create_task_via_integration, the asana/clickup
readers, the OAuth token refresh/callback helpers) that called users_db.get_task_integration /
set_task_integration directly. Those are synchronous Firestore reads/writes, so running them inside an
`async def` blocks the event loop (health checks, HPA, all concurrent connections) per backend/AGENTS.md.
The async-blocker linter does not catch database.* calls, only requests/time.sleep/Thread. These now go
through `await run_blocking(db_executor, ...)`. The plain `def` endpoints (FastAPI runs them in a
threadpool) keep calling the sync functions directly, which is correct.

These are AST-level structural checks: the tool/router has a heavy import graph.
"""

import ast
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[2] / "routers" / "task_integrations.py"
BLOCKING = {"get_task_integration", "set_task_integration", "delete_task_integration"}


def _tree():
    return ast.parse(SOURCE.read_text(encoding="utf-8"))


def _async_funcs(tree):
    return [n for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef)]


def test_run_blocking_is_imported():
    # Semantic check (not an exact-string match) so import reordering or reformatting does not break it.
    imported = set()
    for node in ast.walk(_tree()):
        if isinstance(node, ast.ImportFrom) and node.module == "utils.executors":
            imported.update(alias.name for alias in node.names)
    assert {"db_executor", "run_blocking"} <= imported


def test_no_async_handler_calls_task_integration_db_directly():
    # In an async function, a direct call is `Call(func=users_db.<fn>)`. The offloaded form passes
    # `users_db.<fn>` as a bare argument to run_blocking, so it is an Attribute, not a Call.
    offenders = []
    for fn in _async_funcs(_tree()):
        for node in ast.walk(fn):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "users_db"
                and node.func.attr in BLOCKING
            ):
                offenders.append((fn.name, node.func.attr, node.lineno))
    assert (
        not offenders
    ), f"async handlers call sync task-integration Firestore directly (use run_blocking): {offenders}"


def test_async_handlers_offload_task_integration_calls():
    # Confirm the offloading is actually present (not just that the direct calls vanished).
    wrapped = 0
    for fn in _async_funcs(_tree()):
        for node in ast.walk(fn):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "run_blocking":
                if any(isinstance(a, ast.Attribute) and a.attr in BLOCKING for a in node.args):
                    wrapped += 1
    assert wrapped >= 11, f"expected at least 11 offloaded task-integration calls, found {wrapped}"
