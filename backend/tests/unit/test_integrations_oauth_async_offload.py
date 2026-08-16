"""The async OAuth callback handler must not block the event loop on synchronous I/O.

routers/integrations.py's `async def handle_oauth_callback` validated the OAuth state via
`validate_and_consume_oauth_state` (a synchronous Redis read/delete) and persisted the tokens via
`users_db.set_integration` (a synchronous Firestore write), both directly on the event loop. Per
backend/AGENTS.md, synchronous database/Redis calls inside `async def` block the loop (health checks,
HPA, all concurrent connections), and the async-blocker linter does not catch database.* calls. Both
now go through `await run_blocking(db_executor, ...)`. The plain `def` endpoints (save_integration,
get_integration, get_oauth_url, ...) keep calling the sync functions directly, which is correct since
FastAPI runs `def` handlers in a threadpool.

AST-level structural checks (the router has a heavy import graph).
"""

import ast
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[2] / "routers" / "integrations.py"
# Sync blocking calls that must not run directly inside an async handler.
BLOCKING_ATTR = {("users_db", "set_integration")}
BLOCKING_NAME = {"validate_and_consume_oauth_state"}


def _tree():
    return ast.parse(SOURCE.read_text(encoding="utf-8"))


def _async_funcs(tree):
    return [n for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef)]


def test_run_blocking_is_imported():
    imported = set()
    for node in ast.walk(_tree()):
        if isinstance(node, ast.ImportFrom) and node.module == "utils.executors":
            imported.update(alias.name for alias in node.names)
    assert {"db_executor", "run_blocking"} <= imported


def test_no_async_handler_blocks_on_sync_io():
    # A direct call is `Call(func=...)`. The offloaded form passes the callable as a bare argument
    # to run_blocking, so it is a Name/Attribute, not a Call.
    offenders = []
    for fn in _async_funcs(_tree()):
        for node in ast.walk(fn):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if (
                isinstance(func, ast.Attribute)
                and isinstance(func.value, ast.Name)
                and (func.value.id, func.attr) in BLOCKING_ATTR
            ):
                offenders.append((fn.name, func.attr, node.lineno))
            elif isinstance(func, ast.Name) and func.id in BLOCKING_NAME:
                offenders.append((fn.name, func.id, node.lineno))
    assert not offenders, f"async handlers call sync I/O directly (use run_blocking): {offenders}"


def test_async_handler_offloads_via_run_blocking():
    wrapped = 0
    for fn in _async_funcs(_tree()):
        for node in ast.walk(fn):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "run_blocking":
                for arg in node.args:
                    if (isinstance(arg, ast.Attribute) and arg.attr == "set_integration") or (
                        isinstance(arg, ast.Name) and arg.id in BLOCKING_NAME
                    ):
                        wrapped += 1
    assert wrapped >= 2, f"expected at least 2 offloaded sync I/O calls, found {wrapped}"
