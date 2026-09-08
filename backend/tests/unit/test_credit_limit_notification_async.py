"""Structural test: the credit-limit notification offloads its blocking Redis calls.

send_credit_limit_notification in utils/notifications.py is an async helper. It read and wrote the
notification dedup state through the synchronous has_credit_limit_notification_been_sent and
set_credit_limit_notification_sent (Redis calls in database/redis_db.py), which block the event loop
for the duration of each call. This test parses the source (no import) and asserts both are routed
through an awaited run_blocking(db_executor, ...) and never called directly. The await check guards
against a dangling coroutine (offloaded but not awaited).
"""

import ast
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
NOTIFICATIONS = BACKEND_DIR / 'utils' / 'notifications.py'
TARGET_FN = 'send_credit_limit_notification'
BLOCKING_CALLS = ('has_credit_limit_notification_been_sent', 'set_credit_limit_notification_sent')


def _load_function(name):
    tree = ast.parse(NOTIFICATIONS.read_text(encoding='utf-8'))
    for node in ast.walk(tree):
        if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)) and node.name == name:
            return node
    raise AssertionError(f'{name} not found in {NOTIFICATIONS}')


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


def test_redis_calls_are_not_called_directly():
    fn = _load_function(TARGET_FN)
    for callee in BLOCKING_CALLS:
        assert (
            _direct_calls(fn, callee) == []
        ), f'{callee} is called directly in {TARGET_FN}; it must be offloaded via run_blocking'


def test_redis_calls_are_offloaded_and_awaited():
    fn = _load_function(TARGET_FN)
    targets = [target for _executor, target in _awaited_run_blocking_offloads(fn)]
    for callee in BLOCKING_CALLS:
        assert callee in targets, (
            f'{callee} must be offloaded via an AWAITED run_blocking(db_executor, {callee}, ...); '
            f'awaited run_blocking targets found: {targets}'
        )


def test_offloads_use_db_executor():
    fn = _load_function(TARGET_FN)
    for executor, target in _awaited_run_blocking_offloads(fn):
        if target in BLOCKING_CALLS:
            assert executor == 'db_executor', (
                f'{target} is a Redis call and must be offloaded on db_executor (Firestore/Redis '
                f'CRUD pool); found executor {executor}'
            )
