"""Conversation finalization must not write the capture arrival intent on the event loop.

`finalize_persisted_conversation` is async and offloads everything else it touches through
`run_blocking`: the conversation read, the fanouts, `ensure_processing`, the geolocation
read, `link_duplicate_captures`. `persist_capture_arrival_intent` was the one call left
running inline.

It is not cheap. It calls `resolve_chat_first_eligibility`, which loads the task workflow
control with a Firestore `ref.get()` *before* the enabled check, so every finalized Omi
conversation paid that read on the loop even with chat-first turned off, and then
`chat_first_intents.create_intent` when it is on.
"""

import ast
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
FINALIZER = BACKEND_DIR / "utils" / "conversations" / "finalizer.py"

_HANDLER = "finalize_persisted_conversation"
_BLOCKING = "persist_capture_arrival_intent"


def _dotted(func):
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
        return f"{func.value.id}.{func.attr}"
    return None


def _handler():
    tree = ast.parse(FINALIZER.read_text(encoding="utf-8"))
    node = next(
        (n for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef) and n.name == _HANDLER),
        None,
    )
    assert node is not None, f"async def {_HANDLER} not found in utils/conversations/finalizer.py"
    return node


def _offloaded(node):
    out = {}
    for sub in ast.walk(node):
        if isinstance(sub, ast.Await) and isinstance(sub.value, ast.Call):
            call = sub.value
            if _dotted(call.func) == "run_blocking" and len(call.args) >= 2:
                out[_dotted(call.args[1])] = _dotted(call.args[0])
    return out


def test_the_finalizer_is_async():
    assert isinstance(_handler(), ast.AsyncFunctionDef)


def test_the_capture_intent_is_not_written_on_the_event_loop():
    node = _handler()
    direct = [s.lineno for s in ast.walk(node) if isinstance(s, ast.Call) and _dotted(s.func) == _BLOCKING]
    assert not direct, (
        f"{_HANDLER} calls {_BLOCKING} directly at line(s) {direct}. "
        f"Offload it with await run_blocking(db_executor, {_BLOCKING}, ...)."
    )


def test_the_capture_intent_is_offloaded_to_the_db_executor():
    offloaded = _offloaded(_handler())
    assert _BLOCKING in offloaded, f"{_BLOCKING} is not offloaded via an awaited run_blocking call"
    assert offloaded[_BLOCKING] == "db_executor", f"{_BLOCKING} offloads to {offloaded[_BLOCKING]}, not db_executor"


def test_the_neighbouring_reads_stay_offloaded():
    offloaded = _offloaded(_handler())
    for name in ("lifecycle_service.ensure_processing", "conversations_db.get_conversation"):
        assert name in offloaded, f"{name} is no longer offloaded"
