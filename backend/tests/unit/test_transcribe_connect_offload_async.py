"""Structural test: the listen WebSocket handler offloads its connect-time blocking reads.

_stream_handler in routers/transcribe.py is the async handler for the /listen WebSocket, so it sits
on the real-time audio path shared by every live connection. At connect time it read the user's
private-cloud-sync preference through the synchronous user_db.get_user_private_cloud_sync_enabled
(a Firestore call in database/) and its speech-profile presence through get_user_has_speech_profile
(a GCS blob existence check), both of which block the event loop (#9239). This test parses the
source (no import) and asserts both are routed through an awaited run_blocking(executor, ...) and
never called directly. The await check guards against a dangling coroutine (offloaded but not
awaited).
"""

import ast
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
TRANSCRIBE = BACKEND_DIR / 'routers' / 'transcribe.py'
TARGET_FN = '_stream_handler'
# blocking call -> executor pool it must be offloaded to (Firestore -> db, GCS/file -> storage)
BLOCKING_CALLS = {
    'get_user_private_cloud_sync_enabled': 'db_executor',
    'get_user_has_speech_profile': 'storage_executor',
}


def _load_function(name):
    tree = ast.parse(TRANSCRIBE.read_text(encoding='utf-8'))
    for node in ast.walk(tree):
        if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)) and node.name == name:
            return node
    raise AssertionError(f'{name} not found in {TRANSCRIBE}')


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


def test_connect_reads_are_not_called_directly():
    fn = _load_function(TARGET_FN)
    for callee in BLOCKING_CALLS:
        assert (
            _direct_calls(fn, callee) == []
        ), f'{callee} is called directly in {TARGET_FN}; it must be offloaded via run_blocking'


def test_connect_reads_are_offloaded_and_awaited():
    fn = _load_function(TARGET_FN)
    targets = [target for _executor, target in _awaited_run_blocking_offloads(fn)]
    for callee in BLOCKING_CALLS:
        assert callee in targets, (
            f'{callee} must be offloaded via an AWAITED run_blocking(..., {callee}, ...); '
            f'awaited run_blocking targets found: {targets}'
        )


def test_offloads_use_expected_executor():
    fn = _load_function(TARGET_FN)
    for executor, target in _awaited_run_blocking_offloads(fn):
        if target in BLOCKING_CALLS:
            expected = BLOCKING_CALLS[target]
            assert executor == expected, f'{target} must be offloaded to {expected}, not {executor}'
