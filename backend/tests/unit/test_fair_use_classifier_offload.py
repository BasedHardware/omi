"""Structural test: the fair-use classifier trigger offloads its blocking Firestore read.

trigger_classifier_if_needed in utils/fair_use.py is an async helper that runs the enforcement
escalation pipeline off the WebSocket path. When an action is taken it read the latest fair-use event
through the synchronous fair_use_db.get_fair_use_events (a Firestore read in database/fair_use.py),
which blocks the event loop for the duration of that call. This test parses the source (no import)
and asserts the read is routed through an awaited run_blocking(db_executor, fair_use_db.get_fair_use_events, ...)
and never called directly inside this function. The await check guards against a dangling coroutine.
"""

import ast
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
FAIR_USE = BACKEND_DIR / 'utils' / 'fair_use.py'
TARGET_FN = 'trigger_classifier_if_needed'
BLOCKING_CALL = 'get_fair_use_events'


def _load_function(name):
    tree = ast.parse(FAIR_USE.read_text(encoding='utf-8'))
    for node in ast.walk(tree):
        if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)) and node.name == name:
            return node
    raise AssertionError(f'{name} not found in {FAIR_USE}')


def _ref_name(node):
    """Name for an ast.Name (.id) or ast.Attribute (.attr); None otherwise."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _direct_calls(fn_node, callee):
    return [n for n in ast.walk(fn_node) if isinstance(n, ast.Call) and _ref_name(n.func) == callee]


def _awaited_run_blocking_offloads(fn_node):
    """Yield (executor_name, target_name) for each AWAITED run_blocking(executor, target, ...) call.

    Only awaited calls count: a bare run_blocking(...) without await is a dangling coroutine that
    never runs, so the offload would silently do nothing.
    """
    for node in ast.walk(fn_node):
        if not isinstance(node, ast.Await):
            continue
        call = node.value
        if not isinstance(call, ast.Call) or _ref_name(call.func) != 'run_blocking':
            continue
        if len(call.args) >= 2:
            yield _ref_name(call.args[0]), _ref_name(call.args[1])


def test_events_read_is_not_called_directly():
    fn = _load_function(TARGET_FN)
    assert (
        _direct_calls(fn, BLOCKING_CALL) == []
    ), f'{BLOCKING_CALL} is called directly in {TARGET_FN}; it must be offloaded via run_blocking'


def test_events_read_is_offloaded_and_awaited():
    fn = _load_function(TARGET_FN)
    targets = [target for _executor, target in _awaited_run_blocking_offloads(fn)]
    assert BLOCKING_CALL in targets, (
        f'{BLOCKING_CALL} must be offloaded via an AWAITED run_blocking(db_executor, '
        f'fair_use_db.{BLOCKING_CALL}, ...); awaited run_blocking targets found: {targets}'
    )


def test_events_read_offload_uses_db_executor():
    fn = _load_function(TARGET_FN)
    pools = [executor for executor, target in _awaited_run_blocking_offloads(fn) if target == BLOCKING_CALL]
    assert pools == ['db_executor'], (
        f'{BLOCKING_CALL} is a Firestore read and must be offloaded on db_executor (Firestore/Redis '
        f'CRUD pool); executors found: {pools}'
    )
