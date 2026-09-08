"""Structural test: the task-sync helpers offload their blocking Firestore calls.

The auto-sync helpers in utils/task_sync.py (auto_sync_action_item, _sync_to_cloud_service,
auto_sync_action_items_batch) are async and run the task-integration sync off the request path. They
read the user's task integration, marked Apple Reminder items pending, and marked the action item
exported through synchronous Firestore calls (users_db.get_default_task_integration,
users_db.get_task_integration, action_items_db.batch_set_sync_requested,
action_items_db.update_action_item), each of which blocks the event loop for the duration of the call.
This test parses the source (no import) and asserts each is routed through an awaited
run_blocking(db_executor, ...) and never called directly. The await check guards against a dangling
coroutine (offloaded but not awaited).
"""

import ast
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
TASK_SYNC = BACKEND_DIR / 'utils' / 'task_sync.py'
BLOCKING_CALLS = (
    'get_default_task_integration',
    'get_task_integration',
    'batch_set_sync_requested',
    'update_action_item',
)


def _module():
    return ast.parse(TASK_SYNC.read_text(encoding='utf-8'))


def _ref_name(node):
    """Name for an ast.Name (.id) or ast.Attribute (.attr); None otherwise."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _direct_calls(tree, callee):
    return [n for n in ast.walk(tree) if isinstance(n, ast.Call) and _ref_name(n.func) == callee]


def _awaited_run_blocking_offloads(tree):
    """Yield (executor_name, target_name) for each AWAITED run_blocking(executor, target, ...) call.

    Only awaited calls count: a bare run_blocking(...) without await is a dangling coroutine that
    never runs, so the offload would silently do nothing.
    """
    for node in ast.walk(tree):
        if not isinstance(node, ast.Await):
            continue
        call = node.value
        if not isinstance(call, ast.Call) or _ref_name(call.func) != 'run_blocking':
            continue
        if len(call.args) >= 2:
            yield _ref_name(call.args[0]), _ref_name(call.args[1])


def test_blocking_calls_are_not_called_directly():
    tree = _module()
    for callee in BLOCKING_CALLS:
        assert (
            _direct_calls(tree, callee) == []
        ), f'{callee} is called directly in task_sync.py; it must be offloaded via run_blocking'


def test_blocking_calls_are_offloaded_and_awaited():
    tree = _module()
    targets = [target for _executor, target in _awaited_run_blocking_offloads(tree)]
    for callee in BLOCKING_CALLS:
        assert callee in targets, (
            f'{callee} must be offloaded via an AWAITED run_blocking(db_executor, ...); '
            f'awaited run_blocking targets found: {targets}'
        )


def test_offloads_use_db_executor():
    tree = _module()
    for executor, target in _awaited_run_blocking_offloads(tree):
        if target in BLOCKING_CALLS:
            assert executor == 'db_executor', (
                f'{target} is a Firestore call and must be offloaded on db_executor (Firestore/Redis '
                f'CRUD pool); found executor {executor}'
            )
