"""The agent-VM endpoints must not block the event loop on Firestore writes.

``ensure_vm`` (``POST /v1/agent/vm-ensure``) and its background task
``_restart_vm_background`` are ``async`` and ``await`` the GCE lifecycle calls, but they
wrote the user's ``agentVm`` status to Firestore by calling the synchronous
``_update_firestore_vm`` directly on the event loop. The Firestore sync SDK blocks the loop
(``database.*`` is exactly the class the async-blocker lint does not catch), and ``ensure_vm``
already offloads its read via ``run_blocking`` one line up, so the writes were the
inconsistent part.

They must be offloaded with ``await run_blocking(db_executor, _update_firestore_vm, ...)``.
These AST checks assert the offload stays in place.
"""

import ast
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
AGENT_ROUTER = BACKEND_DIR / "routers" / "agent_tools.py"

_HANDLERS = {"ensure_vm", "_restart_vm_background"}
_BLOCKING = {"_update_firestore_vm"}


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


class TestAgentVmOffloadsFirestoreWrites:
    def test_firestore_write_is_not_called_directly_in_the_async_functions(self):
        for node in _func_nodes():
            leaked = _BLOCKING & _direct_calls(node)
            assert not leaked, (
                f"{node.name} writes Firestore directly on the event loop via {sorted(leaked)}. "
                f"Offload with await run_blocking(db_executor, _update_firestore_vm, ...)."
            )

    def test_firestore_write_is_offloaded_via_run_blocking(self):
        offloaded = set()
        for node in _func_nodes():
            offloaded |= _offloaded_via_run_blocking(node)
        missing = _BLOCKING - offloaded
        assert not missing, f"_update_firestore_vm is not offloaded via run_blocking: {sorted(missing)}"

    def test_functions_are_async(self):
        # Plain def would run in FastAPI's threadpool (background tasks excepted); this fix
        # matters because these are async and await the GCE lifecycle calls.
        for node in _func_nodes():
            assert isinstance(node, ast.AsyncFunctionDef)
