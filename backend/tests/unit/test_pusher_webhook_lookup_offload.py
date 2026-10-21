"""The pusher trigger must not read the webhook config on the event loop.

`get_audio_bytes_webhook_seconds` (`utils/webhooks.py:431`) is a plain `def` that does up to
two synchronous Redis round trips: `user_webhook_status_db` and, when the webhook is toggled
on, `get_user_webhook_db`.

It ran unoffloaded in `_websocket_util_trigger`, after `websocket.accept()`, so a Redis slow
period or failover stalled the pusher pod's loop and every already-connected audio stream on
it stopped draining. The three lines directly below it were already offloaded, which is what
makes this an omission rather than a choice.
"""

import ast
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
PUSHER_ROUTER = BACKEND_DIR / "routers" / "pusher.py"

_HANDLER = "_websocket_util_trigger"
_BLOCKING = "get_audio_bytes_webhook_seconds"


def _dotted(func):
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
        return f"{func.value.id}.{func.attr}"
    return None


def _handler_node():
    tree = ast.parse(PUSHER_ROUTER.read_text(encoding="utf-8"))
    node = next(
        (n for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef) and n.name == _HANDLER),
        None,
    )
    assert node is not None, f"async def {_HANDLER} not found in routers/pusher.py"
    return node


def _offloaded(node):
    offloaded = {}
    for sub in ast.walk(node):
        if not (isinstance(sub, ast.Await) and isinstance(sub.value, ast.Call)):
            continue
        call = sub.value
        if _dotted(call.func) == "run_blocking" and len(call.args) >= 2:
            offloaded[_dotted(call.args[1])] = _dotted(call.args[0])
    return offloaded


def test_the_trigger_handler_is_async():
    assert isinstance(_handler_node(), ast.AsyncFunctionDef)


def test_the_webhook_lookup_does_not_run_on_the_event_loop():
    node = _handler_node()
    direct = [sub.lineno for sub in ast.walk(node) if isinstance(sub, ast.Call) and _dotted(sub.func) == _BLOCKING]
    assert not direct, (
        f"{_HANDLER} runs {_BLOCKING} directly on the event loop at line(s) {direct}. "
        f"Offload it with await run_blocking(db_executor, {_BLOCKING}, uid)."
    )


def test_the_webhook_lookup_is_offloaded_to_the_db_executor():
    offloaded = _offloaded(_handler_node())
    assert _BLOCKING in offloaded, f"{_BLOCKING} is not offloaded via an awaited run_blocking call"
    assert offloaded[_BLOCKING] == "db_executor", f"{_BLOCKING} offloads to {offloaded[_BLOCKING]}, not db_executor"


def test_the_adjacent_lookups_stay_offloaded():
    offloaded = _offloaded(_handler_node())
    for name in ("is_audio_bytes_app_enabled", "users_db.get_user_private_cloud_sync_enabled"):
        assert name in offloaded, f"{name} is no longer offloaded"
