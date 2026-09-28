"""The chat stream must not persist its answer on the event loop.

`process_message` (`routers/chat.py`) writes the assistant turn to Firestore: up to three
sequential round trips through `chat_db.add_message_to_chat_session`, `chat_db.add_message`
and `record_app_usage`. It was called directly from `emit_done_frame`, a plain nested
function inside the `generate_stream` async generator handed to `StreamingResponse`, so that
body runs on the event loop rather than in FastAPI's threadpool.

This is the highest-volume path in the product, so every completed chat answer stalled the
loop for the whole pod for the length of those writes. The same generator already offloads
`sync_user_time_zone_from_client` and already awaits `emit_stream_error_fallback`, so both
the executor and the awaited-yield shape were established here.
"""

import ast
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
CHAT_ROUTER = BACKEND_DIR / "routers" / "chat.py"

_GENERATOR = "generate_stream"
_EMITTER = "emit_done_frame"
_PERSIST = "process_message"


def _dotted(func):
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
        return f"{func.value.id}.{func.attr}"
    return None


def _tree():
    return ast.parse(CHAT_ROUTER.read_text(encoding="utf-8"))


def _find(name):
    return next(
        (n for n in ast.walk(_tree()) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name),
        None,
    )


def test_the_stream_generator_is_async():
    node = _find(_GENERATOR)
    assert isinstance(node, ast.AsyncFunctionDef), f"{_GENERATOR} must stay an async generator"


def test_the_done_frame_emitter_is_async():
    node = _find(_EMITTER)
    assert node is not None, f"{_EMITTER} not found in routers/chat.py"
    assert isinstance(node, ast.AsyncFunctionDef), (
        f"{_EMITTER} must be async so it can offload {_PERSIST}; a plain def would run the "
        f"Firestore writes on the event loop."
    )


def test_the_answer_is_not_persisted_on_the_event_loop():
    node = _find(_EMITTER)
    direct = [sub.lineno for sub in ast.walk(node) if isinstance(sub, ast.Call) and _dotted(sub.func) == _PERSIST]
    assert not direct, (
        f"{_EMITTER} calls {_PERSIST} directly at line(s) {direct}. "
        f"Offload it with await run_blocking(db_executor, {_PERSIST}, ...)."
    )


def test_the_answer_is_persisted_through_an_awaited_run_blocking():
    node = _find(_EMITTER)
    offloaded = {}
    for sub in ast.walk(node):
        if not (isinstance(sub, ast.Await) and isinstance(sub.value, ast.Call)):
            continue
        call = sub.value
        if _dotted(call.func) == "run_blocking" and len(call.args) >= 2:
            offloaded[_dotted(call.args[1])] = _dotted(call.args[0])

    assert _PERSIST in offloaded, f"{_PERSIST} is not offloaded via an awaited run_blocking call"
    assert offloaded[_PERSIST] == "db_executor", f"{_PERSIST} offloads to {offloaded[_PERSIST]}, not db_executor"


def test_every_done_frame_yield_awaits_the_emitter():
    node = _find(_GENERATOR)
    bare = []
    for sub in ast.walk(node):
        if not isinstance(sub, ast.Yield) or sub.value is None:
            continue
        value = sub.value
        if isinstance(value, ast.Call) and _dotted(value.func) == _EMITTER:
            bare.append(sub.lineno)

    assert not bare, (
        f"yield {_EMITTER}(...) at line(s) {bare} yields a coroutine instead of a frame. "
        f"Use yield await {_EMITTER}(...)."
    )
