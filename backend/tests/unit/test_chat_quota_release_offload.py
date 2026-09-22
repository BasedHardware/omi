"""Releasing a charged chat question must not run on the event loop.

#15304 added the refund: when a turn fails terminally after the question was charged,
`_release_chat_quota_question_best_effort` gives it back. That helper called
`llm_usage_db.release_chat_quota_question` directly, and it is called from inside
`generate_stream`, the async generator handed to `StreamingResponse`, so the Firestore
transaction ran on the event loop.

It fires exactly when a provider is failing, so the calls arrive in bursts at the moment the
loop can least afford to stall. The same generator already offloads
`sync_user_time_zone_from_client` and already awaits `emit_done_frame`, so both the executor
and the awaited shape were established here.
"""

import ast
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
CHAT_ROUTER = BACKEND_DIR / "routers" / "chat.py"

_HELPER = "_release_chat_quota_question_best_effort"
_BLOCKING = "llm_usage_db.release_chat_quota_question"


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


def test_the_release_helper_is_async():
    node = _find(_HELPER)
    assert node is not None, f"{_HELPER} not found in routers/chat.py"
    assert isinstance(node, ast.AsyncFunctionDef), (
        f"{_HELPER} must be async so it can offload {_BLOCKING}; a plain def runs the Firestore "
        f"transaction on the event loop."
    )


def test_the_release_is_not_written_on_the_event_loop():
    node = _find(_HELPER)
    direct = [s.lineno for s in ast.walk(node) if isinstance(s, ast.Call) and _dotted(s.func) == _BLOCKING]
    assert not direct, f"{_HELPER} calls {_BLOCKING} directly at line(s) {direct}"


def test_the_release_is_offloaded_to_the_db_executor():
    node = _find(_HELPER)
    offloaded = {}
    for s in ast.walk(node):
        if isinstance(s, ast.Await) and isinstance(s.value, ast.Call):
            c = s.value
            if _dotted(c.func) == "run_blocking" and len(c.args) >= 2:
                offloaded[_dotted(c.args[1])] = _dotted(c.args[0])
    assert _BLOCKING in offloaded, f"{_BLOCKING} is not offloaded via an awaited run_blocking call"
    assert offloaded[_BLOCKING] == "db_executor"


def test_every_caller_awaits_the_release():
    tree = _tree()
    awaited = {id(s.value) for s in ast.walk(tree) if isinstance(s, ast.Await) and isinstance(s.value, ast.Call)}
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and _dotted(n.func) == _HELPER]
    assert calls, "nothing releases the chat question any more"
    for c in calls:
        assert id(c) in awaited, (
            f"routers/chat.py:{c.lineno} calls {_HELPER} without await, which leaves a coroutine "
            f"that never runs, so the question is never given back"
        )
