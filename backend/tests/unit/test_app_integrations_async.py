"""Structural test: the app-integration triggers offload their blocking Firestore calls.

trigger_external_integrations and _async_trigger_realtime_integrations in utils/app_integrations.py
are async helpers on the conversation event path. They recorded app usage and persisted app messages
through the synchronous record_app_usage (Firestore write in database/apps.py) and add_app_message
(Firestore write in database/chat.py), called directly on the event loop. A sync Firestore call on the
loop blocks it for the duration of the call, stalling health checks and every other connection sharing
the loop. This test parses the source (no import) and asserts each call is routed through an awaited
run_blocking(db_executor, ...) and never called directly. The await check guards against a dangling
coroutine (offloaded but not awaited).
"""

import ast
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
APP_INTEGRATIONS = BACKEND_DIR / 'utils' / 'app_integrations.py'

# function -> blocking calls that must be offloaded within it. ast.walk descends into nested helpers,
# so trigger_external_integrations also covers the record_app_usage calls in its inner _single().
TARGETS = {
    'trigger_external_integrations': ('record_app_usage', 'add_app_message'),
    '_async_trigger_realtime_integrations': ('add_app_message',),
}


def _load_function(name):
    tree = ast.parse(APP_INTEGRATIONS.read_text(encoding='utf-8'))
    for node in ast.walk(tree):
        if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)) and node.name == name:
            return node
    raise AssertionError(f'{name} not found in {APP_INTEGRATIONS}')


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


def test_blocking_calls_are_not_called_directly():
    for fn_name, blocking in TARGETS.items():
        fn = _load_function(fn_name)
        for callee in blocking:
            assert (
                _direct_calls(fn, callee) == []
            ), f'{callee} is called directly in {fn_name}; it must be offloaded via run_blocking'


def test_blocking_calls_are_offloaded_and_awaited():
    for fn_name, blocking in TARGETS.items():
        fn = _load_function(fn_name)
        targets = [target for _executor, target in _awaited_run_blocking_offloads(fn)]
        for callee in blocking:
            assert callee in targets, (
                f'{callee} must be offloaded via an AWAITED run_blocking(db_executor, {callee}, ...) '
                f'in {fn_name}; awaited run_blocking targets found: {targets}'
            )


def test_offloads_use_db_executor():
    all_blocking = {callee for calls in TARGETS.values() for callee in calls}
    for fn_name in TARGETS:
        fn = _load_function(fn_name)
        for executor, target in _awaited_run_blocking_offloads(fn):
            if target in all_blocking:
                assert executor == 'db_executor', (
                    f'{target} is a Firestore call and must be offloaded on db_executor (Firestore/Redis '
                    f'CRUD pool); found executor {executor} in {fn_name}'
                )
