"""Structural test: the agent tool-call path offloads the blocking geolocation Redis read.

`_call_tool_endpoint` in utils/retrieval/tools/app_tools.py runs inside the agentic RAG
tool-calling flow (an async path). It read the user's cached geolocation through the synchronous
`get_cached_user_geolocation` (a Redis read in database/redis_db.py), which blocks the event loop
for the duration of that call. This test parses the source (no import, so no heavy langchain deps)
and asserts the read is routed through an AWAITED `run_blocking(db_executor, get_cached_user_geolocation, ...)`
and never called directly. The await check guards against a dangling coroutine (offloaded but not awaited).
"""

import ast
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
APP_TOOLS = BACKEND_DIR / 'utils' / 'retrieval' / 'tools' / 'app_tools.py'
TARGET_FN = '_call_tool_endpoint'
BLOCKING_CALL = 'get_cached_user_geolocation'


def _load_function(name):
    tree = ast.parse(APP_TOOLS.read_text(encoding='utf-8'))
    for node in ast.walk(tree):
        if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)) and node.name == name:
            return node
    raise AssertionError(f'{name} not found in {APP_TOOLS}')


def _call_name(call):
    func = call.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def _direct_calls(fn_node, callee):
    return [n for n in ast.walk(fn_node) if isinstance(n, ast.Call) and _call_name(n) == callee]


def _awaited_run_blocking_offloads(fn_node):
    """Yield (executor_name, target_name) for each AWAITED run_blocking(executor, target, ...) call.

    Only awaited calls count: a bare run_blocking(...) without await is a dangling coroutine that
    never runs, so the offload would silently do nothing.
    """
    for node in ast.walk(fn_node):
        if not isinstance(node, ast.Await):
            continue
        call = node.value
        if not isinstance(call, ast.Call) or _call_name(call) != 'run_blocking':
            continue
        if len(call.args) >= 2 and isinstance(call.args[0], ast.Name) and isinstance(call.args[1], ast.Name):
            yield call.args[0].id, call.args[1].id


def test_geolocation_read_is_not_called_directly():
    fn = _load_function(TARGET_FN)
    assert (
        _direct_calls(fn, BLOCKING_CALL) == []
    ), f'{BLOCKING_CALL} is called directly in {TARGET_FN}; it must be offloaded via run_blocking'


def test_geolocation_read_is_offloaded_and_awaited():
    fn = _load_function(TARGET_FN)
    targets = [target for _executor, target in _awaited_run_blocking_offloads(fn)]
    assert BLOCKING_CALL in targets, (
        f'{BLOCKING_CALL} must be offloaded via an AWAITED run_blocking(db_executor, '
        f'{BLOCKING_CALL}, ...); awaited run_blocking targets found: {targets}'
    )


def test_geolocation_offload_uses_db_executor():
    fn = _load_function(TARGET_FN)
    pools = [executor for executor, target in _awaited_run_blocking_offloads(fn) if target == BLOCKING_CALL]
    assert pools == ['db_executor'], (
        f'{BLOCKING_CALL} is a Redis read and must be offloaded on db_executor (Firestore/Redis CRUD '
        f'pool); executors found: {pools}'
    )
