"""The calendar-linking helpers must not block the event loop on Firestore.

``get_overlapping_calendar_event`` and ``write_conversation_link_to_calendar_event`` in
``utils/conversations/calendar_linking.py`` are ``async`` and ``await`` the httpx Google
Calendar calls, but each first reads the user's integration with a synchronous
``users_db.get_integration`` directly on the event loop. The Firestore sync SDK blocks the
loop (``database.*`` is exactly the class the async-blocker lint does not catch). These are
awaited from the conversation calendar-link handlers, so blocking here blocks those requests.

They must be offloaded with ``await run_blocking(db_executor, users_db.get_integration, ...)``.
These AST checks assert the offload stays in place, including that the ``run_blocking`` call is
actually awaited (a bare call would be a dangling coroutine that never runs).
"""

import ast
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
CALENDAR_LINKING = BACKEND_DIR / "utils" / "conversations" / "calendar_linking.py"

_HELPERS = {"get_overlapping_calendar_event", "write_conversation_link_to_calendar_event"}
_BLOCKING = "users_db.get_integration"


def _dotted(func):
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
        return f"{func.value.id}.{func.attr}"
    return None


def _helper_nodes():
    tree = ast.parse(CALENDAR_LINKING.read_text(encoding="utf-8"))
    nodes = [n for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef) and n.name in _HELPERS]
    found = {n.name for n in nodes}
    assert found == _HELPERS, f"expected async helpers {_HELPERS}, found {found}"
    return nodes


def _direct_calls(node):
    return {name for sub in ast.walk(node) if isinstance(sub, ast.Call) and (name := _dotted(sub.func))}


def _offloaded_via_awaited_run_blocking(node):
    """Names passed as the function arg to an AWAITED ``run_blocking(executor, fn, ...)`` call.

    The run_blocking call must be the operand of an ``await``: a bare ``run_blocking(...)``
    without ``await`` returns a coroutine that never runs, so the offload would silently break
    while still passing a looser wrapped-in-run_blocking check.
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


class TestCalendarLinkingHelpersOffloadFirestore:
    def test_get_integration_is_not_called_directly_in_the_helpers(self):
        for node in _helper_nodes():
            assert _BLOCKING not in _direct_calls(node), (
                f"{node.name} runs {_BLOCKING} directly on the event loop. "
                f"Offload it with await run_blocking(db_executor, ...)."
            )

    def test_get_integration_is_offloaded_via_awaited_run_blocking_in_both(self):
        for node in _helper_nodes():
            offloaded = _offloaded_via_awaited_run_blocking(node)
            assert _BLOCKING in offloaded, f"{node.name} does not offload {_BLOCKING} via an awaited run_blocking call"

    def test_helpers_are_async(self):
        for node in _helper_nodes():
            assert isinstance(node, ast.AsyncFunctionDef)
