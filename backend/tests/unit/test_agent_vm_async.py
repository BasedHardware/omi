"""The Agent VM tools route must only enqueue reconciler intent off the event loop."""

import ast
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
AGENT_ROUTER = BACKEND_DIR / "routers" / "agent_tools.py"

_HANDLERS = {"ensure_vm"}
_BLOCKING = {"request_vm_start"}


def _func_nodes():
    tree = ast.parse(AGENT_ROUTER.read_text(encoding="utf-8"))
    nodes = [n for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef) and n.name in _HANDLERS]
    found = {n.name for n in nodes}
    assert found == _HANDLERS, f"expected async functions {_HANDLERS}, found {found}"
    return nodes


def _direct_calls(node):
    return {sub.func.id for sub in ast.walk(node) if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Name)}


def _offloaded_via_run_blocking(node):
    """Names passed as the function argument to an AWAITED ``run_blocking(executor, fn, ...)``.

    The run_blocking call must be the operand of an ``await``. A bare ``run_blocking(...)``
    without ``await`` returns a coroutine that never runs, so the offload would silently break
    while still passing a looser wrapped-in-run_blocking check. Requiring the await closes that
    regression gap.
    """
    offloaded = set()
    for sub in ast.walk(node):
        if not (isinstance(sub, ast.Await) and isinstance(sub.value, ast.Call)):
            continue
        call = sub.value
        if isinstance(call.func, ast.Name) and call.func.id == "run_blocking" and len(call.args) >= 2:
            if isinstance(call.args[1], ast.Name):
                offloaded.add(call.args[1].id)
    return offloaded


class TestAgentVmQueuesReconcilerIntent:
    def test_reconciler_intent_is_not_called_directly_in_the_async_handler(self):
        for node in _func_nodes():
            leaked = _BLOCKING & _direct_calls(node)
            assert not leaked, (
                f"{node.name} calls the reconciler intent directly via {sorted(leaked)}. "
                f"Offload with await run_blocking(db_executor, request_vm_start, ...)."
            )

    def test_reconciler_intent_is_offloaded_via_run_blocking(self):
        offloaded = set()
        for node in _func_nodes():
            offloaded |= _offloaded_via_run_blocking(node)
        missing = _BLOCKING - offloaded
        assert not missing, f"request_vm_start is not offloaded via run_blocking: {sorted(missing)}"

    def test_functions_are_async(self):
        for node in _func_nodes():
            assert isinstance(node, ast.AsyncFunctionDef)
