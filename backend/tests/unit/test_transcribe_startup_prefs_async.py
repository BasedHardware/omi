"""Structural test: listen WebSocket startup offloads transcription preference read.

`_stream_handler` in routers/transcribe.py runs on the hot WebSocket connect path. It read the
user's transcription preferences through the synchronous `get_user_transcription_preferences`
(Firestore in database/users.py), which blocks the asyncio event loop. This test parses the
source (no import) and asserts the read is routed through an awaited
`run_blocking(db_executor, get_user_transcription_preferences, ...)` and never called directly.
The await check guards against a dangling coroutine (offloaded but not awaited).
"""

import ast
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
TRANSCRIBE = BACKEND_DIR / 'routers' / 'transcribe.py'
TARGET_FN = '_stream_handler'
BLOCKING_CALL = 'get_user_transcription_preferences'


def _load_function(name):
    tree = ast.parse(TRANSCRIBE.read_text(encoding='utf-8'))
    for node in ast.walk(tree):
        if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)) and node.name == name:
            return node
    raise AssertionError(f'{name} not found in {TRANSCRIBE}')


def _ref_name(node):
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _direct_calls(fn_node, callee):
    return [n for n in ast.walk(fn_node) if isinstance(n, ast.Call) and _ref_name(n.func) == callee]


def _awaited_run_blocking_offloads(fn_node):
    """Yield (executor_name, target_name) for each AWAITED run_blocking(executor, target, ...) call."""
    for node in ast.walk(fn_node):
        if not isinstance(node, ast.Await):
            continue
        call = node.value
        if not isinstance(call, ast.Call) or _ref_name(call.func) != 'run_blocking':
            continue
        if len(call.args) >= 2:
            yield _ref_name(call.args[0]), _ref_name(call.args[1])


def test_transcription_prefs_read_is_not_called_directly():
    fn = _load_function(TARGET_FN)
    assert (
        _direct_calls(fn, BLOCKING_CALL) == []
    ), f'{BLOCKING_CALL} is called directly in {TARGET_FN}; it must be offloaded via run_blocking'


def test_transcription_prefs_read_is_offloaded_and_awaited():
    fn = _load_function(TARGET_FN)
    targets = [target for _executor, target in _awaited_run_blocking_offloads(fn)]
    assert BLOCKING_CALL in targets, (
        f'{BLOCKING_CALL} must be offloaded via an AWAITED run_blocking(db_executor, '
        f'{BLOCKING_CALL}, ...); awaited run_blocking targets found: {targets}'
    )


def test_transcription_prefs_offload_uses_db_executor():
    fn = _load_function(TARGET_FN)
    pools = [executor for executor, target in _awaited_run_blocking_offloads(fn) if target == BLOCKING_CALL]
    assert pools == ['db_executor'], (
        f'{BLOCKING_CALL} is a Firestore read and must be offloaded on db_executor (Firestore/Redis '
        f'CRUD pool); executors found: {pools}'
    )


def test_stream_handler_fetches_transcription_prefs_once():
    source = TRANSCRIBE.read_text(encoding='utf-8')
    fn = _load_function(TARGET_FN)
    fn_source = ast.get_source_segment(source, fn) or ''

    assert fn_source.count('get_user_transcription_preferences') == 1
    assert "transcription_prefs.get('language', '')" in fn_source
    assert 'get_user_language_preference' not in fn_source
