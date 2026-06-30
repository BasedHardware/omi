"""The conversation calendar-link handlers must not block the event loop on Firestore.

``link_calendar_event`` and ``auto_link_calendar_event`` (``routers/conversations.py``,
routes ``POST /v1/conversations/{id}/calendar-event`` and ``.../calendar-event/auto-link``)
are ``async def`` handlers. They legitimately ``await`` the httpx Google Calendar calls, but
between those awaits they ran synchronous Firestore CRUD directly on the event loop:

- ``_get_valid_conversation_by_id`` (wraps ``conversations_db.get_conversation``)
- ``users_db.get_integration``
- ``conversations_db.update_conversation``

The sync Firestore SDK blocks the loop (``database.*`` is exactly the class the async-blocker
lint does not catch), stalling every other connection while a calendar link is processed.
They must be offloaded with ``await run_blocking(db_executor, fn, ...)``. These AST checks
assert the offload stays in place.
"""

import ast
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
CONV_ROUTER = BACKEND_DIR / "routers" / "conversations.py"

_HANDLERS = {"link_calendar_event", "auto_link_calendar_event"}
# Synchronous Firestore-backed calls that must be offloaded, not run on the loop.
_BLOCKING = {"_get_valid_conversation_by_id", "users_db.get_integration", "conversations_db.update_conversation"}


def _dotted(func):
    """Render a Call.func as ``name`` or ``obj.attr``; None if it is neither."""
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
        return f"{func.value.id}.{func.attr}"
    return None


def _handler_nodes():
    tree = ast.parse(CONV_ROUTER.read_text(encoding="utf-8"))
    nodes = [n for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef) and n.name in _HANDLERS]
    found = {n.name for n in nodes}
    assert found == _HANDLERS, f"expected async handlers {_HANDLERS}, found {found}"
    return nodes


def _direct_calls(node):
    return {name for sub in ast.walk(node) if isinstance(sub, ast.Call) and (name := _dotted(sub.func))}


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
        if _dotted(call.func) == "run_blocking" and len(call.args) >= 2:
            name = _dotted(call.args[1])
            if name:
                offloaded.add(name)
    return offloaded


class TestCalendarLinkOffloadsFirestore:
    def test_no_blocking_firestore_call_runs_directly_in_the_handlers(self):
        for node in _handler_nodes():
            leaked = _BLOCKING & _direct_calls(node)
            assert not leaked, (
                f"{node.name} runs blocking Firestore calls directly on the event loop: {sorted(leaked)}. "
                f"Offload them with await run_blocking(db_executor, ...)."
            )

    def test_every_blocking_call_is_offloaded_via_run_blocking(self):
        offloaded = set()
        for node in _handler_nodes():
            offloaded |= _offloaded_via_run_blocking(node)
        missing = _BLOCKING - offloaded
        assert not missing, f"these blocking calls are not offloaded via run_blocking: {sorted(missing)}"

    def test_handlers_are_async(self):
        # Plain def handlers would run in FastAPI's threadpool and the sync calls would be
        # fine; this fix only matters because they are async (they await the calendar HTTP).
        for node in _handler_nodes():
            assert isinstance(node, ast.AsyncFunctionDef)
