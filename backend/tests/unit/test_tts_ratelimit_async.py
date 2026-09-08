"""The TTS synthesize handler must not block the event loop on the rate-limit check.

``tts_synthesize`` (``POST /v2/tts/synthesize`` in ``routers/tts.py``) is an ``async`` handler
that streams the upstream TTS response via an httpx async client, but it first runs the
synchronous Redis rate-limit check ``redis_db.check_tts_rate_limit`` directly on the event
loop. The sync Redis call blocks the loop (``database.*`` is exactly the class the
async-blocker lint does not catch).

It must be offloaded with ``await run_blocking(critical_executor, redis_db.check_tts_rate_limit,
...)`` (the auth/rate-limit pool per ``AGENTS.md``). These AST checks assert the offload stays
in place, including that the ``run_blocking`` call is awaited (a bare call would be a dangling
coroutine that never runs).
"""

import ast
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
TTS_ROUTER = BACKEND_DIR / "routers" / "tts.py"

_HANDLER = "tts_synthesize"
_BLOCKING = "redis_db.check_tts_rate_limit"


def _dotted(func):
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
        return f"{func.value.id}.{func.attr}"
    return None


def _handler_node():
    tree = ast.parse(TTS_ROUTER.read_text(encoding="utf-8"))
    node = next(
        (n for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef) and n.name == _HANDLER),
        None,
    )
    assert node is not None, f"async def {_HANDLER} not found in routers/tts.py"
    return node


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


class TestTtsRateLimitOffload:
    def test_rate_limit_check_is_not_called_directly_in_the_async_handler(self):
        assert _BLOCKING not in _direct_calls(_handler_node()), (
            f"{_HANDLER} runs {_BLOCKING} directly on the event loop. "
            f"Offload it with await run_blocking(critical_executor, ...)."
        )

    def test_rate_limit_check_is_offloaded_via_awaited_run_blocking(self):
        offloaded = _offloaded_via_awaited_run_blocking(_handler_node())
        assert _BLOCKING in offloaded, f"{_BLOCKING} is not offloaded via an awaited run_blocking call"

    def test_handler_is_async(self):
        assert isinstance(_handler_node(), ast.AsyncFunctionDef)
