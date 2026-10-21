"""Async LLM paths must report provider errors through the async error handler.

`handle_llm_error` is synchronous and, for a BYOK error, reaches
`_send_byok_llm_error_notification`: a Firestore read of the user's tokens
(`notification_db.get_all_tokens`), a Redis lock, and `messaging.send_each`, which is a
blocking Firebase HTTPS call sent in batches of up to 500 tokens with no timeout at that
call site.

Called bare from an `async def`, one user's expired BYOK key therefore makes every later
embedding call on that pod run those on the event loop. `handle_llm_error_async` exists for
exactly this and hands the work to `storage_executor`; `utils/retrieval/agentic.py` already
uses it.

The synchronous handler stays correct in synchronous callbacks, so this asserts on `async def`
bodies only rather than banning it outright.
"""

import ast
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent

_SYNC_HANDLER = "handle_llm_error"
_ASYNC_HANDLER = "handle_llm_error_async"
_MODULES = (
    "utils/llm/clients.py",
    "utils/retrieval/agentic.py",
)


def _dotted(func):
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
        return f"{func.value.id}.{func.attr}"
    return None


def _async_defs(path):
    tree = ast.parse((BACKEND_DIR / path).read_text(encoding="utf-8"))
    return [n for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef)]


def test_no_async_function_calls_the_sync_llm_error_handler():
    offenders = []
    for path in _MODULES:
        for node in _async_defs(path):
            for sub in ast.walk(node):
                if isinstance(sub, ast.Call) and _dotted(sub.func) == _SYNC_HANDLER:
                    offenders.append(f"{path}:{sub.lineno} {node.name}")
    assert not offenders, f"use await {_ASYNC_HANDLER}(...) instead: " + "; ".join(offenders)


def test_the_async_embedding_paths_still_report_provider_errors():
    handlers = {n.name: n for n in _async_defs("utils/llm/clients.py")}
    expected = ("_agateway_embed_texts", "aembed_query", "aembed_documents")

    for name in expected:
        assert name in handlers, f"{name} is no longer an async function"
        awaited = [
            sub
            for sub in ast.walk(handlers[name])
            if isinstance(sub, ast.Await)
            and isinstance(sub.value, ast.Call)
            and _dotted(sub.value.func) == _ASYNC_HANDLER
        ]
        assert awaited, f"{name} no longer reports provider errors through {_ASYNC_HANDLER}"


def test_the_async_handler_is_awaited_everywhere_it_is_used():
    for path in _MODULES:
        tree = ast.parse((BACKEND_DIR / path).read_text(encoding="utf-8"))
        awaited = {
            id(sub.value) for sub in ast.walk(tree) if isinstance(sub, ast.Await) and isinstance(sub.value, ast.Call)
        }
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and _dotted(node.func) == _ASYNC_HANDLER:
                assert id(node) in awaited, (
                    f"{path}:{node.lineno} calls {_ASYNC_HANDLER} without await, "
                    f"which leaves a coroutine that never runs"
                )
