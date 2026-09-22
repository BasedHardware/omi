"""The X OAuth callback must not write the stored tokens on the event loop.

`_store_tokens` (`utils/x_connector.py:189`) is a plain `def` that does two Firestore
writes: `users_db.set_integration` for the integration document and `_register_user`, which
does a `db.collection(...).document(uid).set(..., merge=True)` on the sync registry.

`x_oauth_callback` is `async def`, so both ran on the event loop while the user waited on a
browser redirect. The line directly below backgrounds the first ingest so that redirect is
instant, which is the same concern.
"""

import ast
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
X_ROUTER = BACKEND_DIR / "routers" / "x_connector.py"

_HANDLER = "x_oauth_callback"
_BLOCKING = "x_connector._store_tokens"


def _dotted(func):
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
        return f"{func.value.id}.{func.attr}"
    return None


def _handler():
    tree = ast.parse(X_ROUTER.read_text(encoding="utf-8"))
    node = next(
        (n for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef) and n.name == _HANDLER),
        None,
    )
    assert node is not None, f"async def {_HANDLER} not found in routers/x_connector.py"
    return node


def test_the_callback_is_async():
    assert isinstance(_handler(), ast.AsyncFunctionDef)


def test_the_tokens_are_not_stored_on_the_event_loop():
    node = _handler()
    direct = [s.lineno for s in ast.walk(node) if isinstance(s, ast.Call) and _dotted(s.func) == _BLOCKING]
    assert not direct, (
        f"{_HANDLER} calls {_BLOCKING} directly at line(s) {direct}. "
        f"Offload it with await run_blocking(db_executor, ...)."
    )


def test_the_tokens_are_stored_through_an_awaited_run_blocking():
    node = _handler()
    offloaded = {}
    for s in ast.walk(node):
        if isinstance(s, ast.Await) and isinstance(s.value, ast.Call):
            c = s.value
            if _dotted(c.func) == "run_blocking" and len(c.args) >= 2:
                offloaded[_dotted(c.args[1])] = _dotted(c.args[0])
    assert _BLOCKING in offloaded, f"{_BLOCKING} is not offloaded via an awaited run_blocking call"
    assert offloaded[_BLOCKING] == "db_executor"


def test_the_connection_is_still_stored_before_the_success_redirect():
    """A callback that returns success without storing the tokens would leave X unconnected."""
    node = _handler()
    stores = [
        s.lineno
        for s in ast.walk(node)
        if isinstance(s, ast.Await) and isinstance(s.value, ast.Call) and _dotted(s.value.func) == "run_blocking"
    ]
    successes = [
        s.lineno
        for s in ast.walk(node)
        if isinstance(s, ast.Call)
        and _dotted(s.func) == "_redirect_html"
        and any(isinstance(a, ast.Constant) and a.value is True for a in s.args)
    ]
    assert stores and successes
    assert min(stores) < max(successes)
