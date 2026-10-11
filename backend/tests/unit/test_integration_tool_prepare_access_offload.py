"""Integration chat tools must not resolve their access grant on the event loop.

`prepare_access` (`utils/retrieval/tools/integration_base.py:87`) is synchronous and reaches
`get_integration_checked` -> `database.users.get_integration`, which is a Firestore document
read. The calendar and gmail tools run inside an agentic chat turn, so a direct call blocks
the loop for every other request on the pod for the length of that read.

Three of the five tool call sites already wrapped it in `await run_blocking(db_executor, ...)`;
the delete and update calendar tools did not, which is a plain omission rather than a design
choice. This asserts the offload across every async tool in both modules.
"""

import ast
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent

_GUARDED = "prepare_access"
_TOOL_MODULES = (
    "utils/retrieval/tools/calendar_tools.py",
    "utils/retrieval/tools/gmail_tools.py",
)


def _dotted(func):
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
        return f"{func.value.id}.{func.attr}"
    return None


def _async_defs(path):
    tree = ast.parse((BACKEND_DIR / path).read_text(encoding="utf-8"))
    return [n for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef)]


def _direct_calls(node):
    return [sub.lineno for sub in ast.walk(node) if isinstance(sub, ast.Call) and _dotted(sub.func) == _GUARDED]


def _offload_executor(node):
    for sub in ast.walk(node):
        if not (isinstance(sub, ast.Await) and isinstance(sub.value, ast.Call)):
            continue
        call = sub.value
        if _dotted(call.func) == "run_blocking" and len(call.args) >= 2 and _dotted(call.args[1]) == _GUARDED:
            return _dotted(call.args[0])
    return None


def test_no_async_tool_resolves_access_on_the_event_loop():
    offenders = []
    for path in _TOOL_MODULES:
        for node in _async_defs(path):
            for lineno in _direct_calls(node):
                offenders.append(f"{path}:{lineno} {node.name}")
    assert not offenders, f"{_GUARDED} must go through await run_blocking(db_executor, ...): " + "; ".join(offenders)


def test_every_tool_that_resolves_access_offloads_it_to_the_db_executor():
    offloaded = {}
    for path in _TOOL_MODULES:
        for node in _async_defs(path):
            executor = _offload_executor(node)
            if executor is not None:
                offloaded[node.name] = executor

    assert offloaded, "no tool offloads prepare_access any more"
    for name, executor in offloaded.items():
        assert executor == "db_executor", f"{name} offloads to {executor}, not db_executor"


def test_the_calendar_write_tools_still_resolve_access():
    tools = {n.name: n for n in _async_defs("utils/retrieval/tools/calendar_tools.py")}
    for name in ("delete_calendar_event_tool", "update_calendar_event_tool"):
        assert name in tools, f"{name} is no longer an async tool"
        assert _offload_executor(tools[name]) == "db_executor", f"{name} no longer resolves its access grant"
