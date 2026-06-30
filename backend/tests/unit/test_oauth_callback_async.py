"""The OAuth callback handler must not block the event loop on Firestore.

``handle_oauth_callback`` (``routers/integrations.py``, the OAuth redirect endpoint that
finishes connecting an integration) is ``async`` and ``await``s the httpx token exchange and
``fetch_additional_data``, but it then persisted the tokens with a synchronous
``users_db.set_integration`` directly on the event loop. The Firestore sync SDK blocks the
loop (``database.*`` is exactly the class the async-blocker lint does not catch), stalling
every other connection during the write.

It must be offloaded with ``await run_blocking(db_executor, users_db.set_integration, ...)``.
These AST checks assert the offload stays in place. The check is scoped to
``handle_oauth_callback``; the other ``users_db.set_integration`` calls in this file are sync
``def`` endpoints that FastAPI already runs in a threadpool, so they are fine as-is.
"""

import ast
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
INTEGRATIONS_ROUTER = BACKEND_DIR / "routers" / "integrations.py"

_HANDLER = "handle_oauth_callback"
_BLOCKING = "users_db.set_integration"


def _dotted(func):
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
        return f"{func.value.id}.{func.attr}"
    return None


def _handler_node():
    tree = ast.parse(INTEGRATIONS_ROUTER.read_text(encoding="utf-8"))
    node = next(
        (n for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef) and n.name == _HANDLER),
        None,
    )
    assert node is not None, f"async def {_HANDLER} not found in routers/integrations.py"
    return node


def _direct_calls(node):
    return {name for sub in ast.walk(node) if isinstance(sub, ast.Call) and (name := _dotted(sub.func))}


def _offloaded_via_run_blocking(node):
    offloaded = set()
    for sub in ast.walk(node):
        if isinstance(sub, ast.Call) and _dotted(sub.func) == "run_blocking" and len(sub.args) >= 2:
            name = _dotted(sub.args[1])
            if name:
                offloaded.add(name)
    return offloaded


class TestOAuthCallbackOffloadsFirestore:
    def test_set_integration_is_not_called_directly_in_the_async_handler(self):
        leaked = _BLOCKING in _direct_calls(_handler_node())
        assert not leaked, (
            f"{_HANDLER} runs {_BLOCKING} directly on the event loop. "
            f"Offload it with await run_blocking(db_executor, ...)."
        )

    def test_set_integration_is_offloaded_via_run_blocking(self):
        offloaded = _offloaded_via_run_blocking(_handler_node())
        assert _BLOCKING in offloaded, f"{_BLOCKING} is not offloaded via run_blocking in {_HANDLER}"

    def test_handler_is_async(self):
        assert isinstance(_handler_node(), ast.AsyncFunctionDef)
