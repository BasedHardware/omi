"""The TTS synthesize handler must not block the event loop on its pre-flight sync work.

``tts_synthesize`` (``POST /v2/tts/synthesize`` in ``routers/tts.py``) is an ``async`` handler
that streams the upstream TTS response via an httpx async client, but it first runs two
synchronous calls directly on the event loop:

- the Redis rate-limit check ``redis_db.check_tts_rate_limit``
- the Firestore user timezone read ``_get_user_time_zone`` (via
  ``notification_db.get_user_time_zone``), which feeds that limiter's daily bucket

Both block the loop (``database.*`` is exactly the class the async-blocker lint struggles
to see through a module-local wrapper, and it reports the unwrapped timezone read as
``STRUCTURAL (mixed await+sync DB)``).

They must be offloaded with ``await run_blocking(<pool>, fn, ...)`` — ``critical_executor``
for the auth/rate-limit gate, ``db_executor`` for the Firestore read, per ``AGENTS.md`` pool
assignment. These AST checks assert each offload stays in place, including that the
``run_blocking`` call is awaited (a bare call would be a dangling coroutine that never runs).
"""

import ast
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
TTS_ROUTER = BACKEND_DIR / "routers" / "tts.py"

_HANDLER = "tts_synthesize"
_BLOCKING = "redis_db.check_tts_rate_limit"
# The Firestore read is called as a module-local helper, so it is matched by bare name.
_BLOCKING_TIMEZONE = "_get_user_time_zone"


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


class TestTtsTimezoneLookupOffload:
    """#19861: the Firestore timezone read must leave the event loop too."""

    def test_timezone_lookup_is_not_called_directly_in_the_async_handler(self):
        assert _BLOCKING_TIMEZONE not in _direct_calls(_handler_node()), (
            f"{_HANDLER} runs {_BLOCKING_TIMEZONE} directly on the event loop. "
            f"Offload it with await run_blocking(db_executor, {_BLOCKING_TIMEZONE}, uid)."
        )

    def test_timezone_lookup_is_offloaded_via_awaited_run_blocking(self):
        offloaded = _offloaded_via_awaited_run_blocking(_handler_node())
        assert _BLOCKING_TIMEZONE in offloaded, f"{_BLOCKING_TIMEZONE} is not offloaded via awaited run_blocking"
