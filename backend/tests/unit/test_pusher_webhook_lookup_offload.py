"""The pusher trigger must not read the webhook config on the event loop.

`get_audio_bytes_webhook_seconds` (`utils/webhooks.py:431`) is a plain `def` that does up to
two synchronous Redis round trips: `user_webhook_status_db` and, when the webhook is toggled
on, `get_user_webhook_db`.

It ran unoffloaded in `_websocket_util_trigger`, after `websocket.accept()`, so a Redis slow
period or failover stalled the pusher pod's loop and every already-connected audio stream on
it stopped draining. The three lines directly below it were already offloaded, which is what
makes this an omission rather than a choice.

The admission profile reads now ride the session-admission transient shed
(`_admission_read_with_transient_shed`, added 2026-11-02 for pod-start
cold-channel availability blips): the handler hands the shed the executor and
the read (`_admission_read_with_transient_shed(db_executor, <read>, uid)`),
and the shed awaits `run_blocking(pool, fn, *args)` on every attempt — the
offload moved inside the helper, so the pin moved with it. The contract is
unchanged: each admission read reaches its executor off the event loop, on
every shed attempt, and nothing calls a read directly in the handler body.
"""

import ast
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
PUSHER_ROUTER = BACKEND_DIR / "routers" / "pusher.py"

_HANDLER = "_run_websocket_util_trigger"
_SHED = "_admission_read_with_transient_shed"
_BLOCKING = "get_audio_bytes_webhook_seconds"
_ADMISSION_READS = (
    "get_audio_bytes_webhook_seconds",
    "is_audio_bytes_app_enabled",
    "users_db.get_user_private_cloud_sync_enabled",
    "users_db.get_data_protection_level",
)


def _dotted(func):
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
        return f"{func.value.id}.{func.attr}"
    return None


def _find_async(name):
    tree = ast.parse(PUSHER_ROUTER.read_text(encoding="utf-8"))
    node = next(
        (n for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef) and n.name == name),
        None,
    )
    assert node is not None, f"async def {name} not found in routers/pusher.py"
    return node


def _handler_node():
    return _find_async(_HANDLER)


def _shed_node():
    return _find_async(_SHED)


def _shed_calls(node):
    """Awaited ``_admission_read_with_transient_shed(pool, read, ...)`` sites:
    {read: pool}."""
    calls = {}
    for sub in ast.walk(node):
        if not (isinstance(sub, ast.Await) and isinstance(sub.value, ast.Call)):
            continue
        call = sub.value
        if _dotted(call.func) == _SHED and len(call.args) >= 2:
            calls[_dotted(call.args[1])] = _dotted(call.args[0])
    return calls


def test_the_trigger_handler_is_async():
    assert isinstance(_handler_node(), ast.AsyncFunctionDef)


def test_the_webhook_lookup_does_not_run_on_the_event_loop():
    node = _handler_node()
    direct = [sub.lineno for sub in ast.walk(node) if isinstance(sub, ast.Call) and _dotted(sub.func) == _BLOCKING]
    assert not direct, (
        f"{_HANDLER} runs {_BLOCKING} directly on the event loop at line(s) {direct}. "
        f"Route it through {_SHED}(db_executor, {_BLOCKING}, uid)."
    )


def test_the_webhook_lookup_is_offloaded_to_the_db_executor():
    """The shed call hands the read the db executor; the shed helper itself
    awaits run_blocking on the pool it was given — the Redis round trips stay
    off the event loop on every attempt."""
    calls = _shed_calls(_handler_node())
    assert _BLOCKING in calls, (
        f"{_BLOCKING} is not routed through an awaited {_SHED} call; "
        f"the webhook read must reach its executor via the admission shed"
    )
    assert calls[_BLOCKING] == "db_executor", f"{_BLOCKING} is shed on {calls[_BLOCKING]}, not db_executor"

    offloaded = _offloaded_in_shed()
    assert offloaded, f"{_SHED} no longer awaits run_blocking — the read would run on the event loop"


def _offloaded_in_shed():
    offloaded = {}
    for sub in ast.walk(_shed_node()):
        if not (isinstance(sub, ast.Await) and isinstance(sub.value, ast.Call)):
            continue
        call = sub.value
        if _dotted(call.func) == "run_blocking" and len(call.args) >= 2:
            offloaded[_dotted(call.args[1])] = _dotted(call.args[0])
    return offloaded


def test_the_shed_helper_offloads_every_read_via_run_blocking():
    """The offload lives inside the shed: ``fn`` (whatever read the handler
    passed) must reach ``run_blocking(pool, fn, ...)``, awaited."""
    offloaded = _offloaded_in_shed()
    assert offloaded.get("fn") == "pool", f"{_SHED} must await run_blocking(pool, fn, *args) — got {offloaded}"


def test_the_adjacent_lookups_stay_offloaded():
    calls = _shed_calls(_handler_node())
    for name in _ADMISSION_READS:
        assert name in calls, f"{name} is no longer routed through the admission shed"
        assert calls[name] == "db_executor", f"{name} is shed on {calls[name]}, not db_executor"
