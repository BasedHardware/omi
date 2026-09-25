"""The chat-quota gates must not run on the event loop.

`enforce_chat_quota` and `enforce_desktop_chat_quota` are synchronous: they reach
`is_trial_paywalled`, `users_db.is_byok_active` and `get_chat_quota_snapshot`, which read
Firestore, and the desktop one additionally builds a Firestore client on first use, which
loads credentials. Called bare from an `async def` handler they pin the event loop of the
whole pod for the length of those reads.

`routers/chat_generation.py` and `routers/desktop_realtime.py` already call them through
`await run_blocking(db_executor, ...)`; the app-generation endpoints and the desktop
chat-completions path did not.

Only handlers declared `async def` are covered here. Several sibling endpoints call the same
gates from a plain `def`, where FastAPI runs the handler in its own threadpool and a direct
call is correct, so this asserts on the async ones alone rather than banning the call
outright.
"""

import ast
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent

_GATES = frozenset({"enforce_chat_quota", "enforce_desktop_chat_quota"})
_ROUTERS = (
    "routers/apps.py",
    "routers/desktop_chat.py",
    "routers/chat_generation.py",
    "routers/desktop_realtime.py",
)


def _dotted(func):
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
        return f"{func.value.id}.{func.attr}"
    return None


def _async_handlers(path):
    tree = ast.parse((BACKEND_DIR / path).read_text(encoding="utf-8"))
    return [n for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef)]


def _direct_gate_calls(node):
    found = []
    for sub in ast.walk(node):
        if isinstance(sub, ast.Call) and _dotted(sub.func) in _GATES:
            found.append((_dotted(sub.func), sub.lineno))
    return found


def _offloaded_gates(node):
    offloaded = {}
    for sub in ast.walk(node):
        if not (isinstance(sub, ast.Await) and isinstance(sub.value, ast.Call)):
            continue
        call = sub.value
        if _dotted(call.func) == "run_blocking" and len(call.args) >= 2:
            name = _dotted(call.args[1])
            if name in _GATES:
                offloaded[name] = _dotted(call.args[0])
    return offloaded


def test_no_async_handler_runs_a_chat_quota_gate_on_the_loop():
    offenders = []
    for path in _ROUTERS:
        for handler in _async_handlers(path):
            for gate, lineno in _direct_gate_calls(handler):
                offenders.append(f"{path}:{lineno} {handler.name} calls {gate} directly")
    assert not offenders, "Offload with await run_blocking(db_executor, ...): " + "; ".join(offenders)


def test_the_async_handlers_that_gate_do_so_through_an_awaited_run_blocking():
    gated = {}
    for path in _ROUTERS:
        for handler in _async_handlers(path):
            for gate, executor in _offloaded_gates(handler).items():
                gated[f"{path}:{handler.name}"] = (gate, executor)

    assert gated, "no async handler offloads a chat quota gate any more"
    for where, (_gate, executor) in gated.items():
        assert executor == "db_executor", f"{where} offloads to {executor}, not db_executor"


def test_the_app_generation_endpoints_still_gate():
    handlers = {n.name: n for n in _async_handlers("routers/apps.py")}
    for name in ("generate_sample_prompts_endpoint", "generate_app_endpoint", "generate_app_icon_endpoint"):
        assert name in handlers, f"{name} is no longer an async handler"
        assert "enforce_chat_quota" in _offloaded_gates(handlers[name]), f"{name} no longer enforces the chat quota"


def test_the_desktop_chat_completions_path_still_gates():
    handlers = {n.name: n for n in _async_handlers("routers/desktop_chat.py")}
    assert "_chat_completions_unobserved" in handlers
    offloaded = _offloaded_gates(handlers["_chat_completions_unobserved"])
    assert "enforce_desktop_chat_quota" in offloaded
