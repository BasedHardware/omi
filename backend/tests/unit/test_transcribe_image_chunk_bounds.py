"""
Bounds-check regression test for handle_image_chunk in routers/transcribe.py.

handle_image_chunk indexes a pre-sized list with a client-controlled `index`
(chunks_data[index]). On main the guard is `index < total` with NO lower bound,
so a sufficiently-negative index raises IndexError (tearing down the listen
WebSocket session) and an in-range-negative index silently writes the WRONG
slot. The fix adds a lower bound: `0 <= index < total`.

handle_image_chunk is a closure nested inside the ~2900-LOC `_stream_handler`,
so it cannot be imported and called directly, and importing transcribe.py pulls
in heavy top-level deps. Instead we extract the ACTUAL function node from the
real source via AST, compile only that function, inject its free (non-parameter)
names as harmless stubs, and call it. This exercises the real source lines in
transcribe.py, so the test goes RED (IndexError / wrong-slot write) without the
fix and GREEN with it -- without reproducing/forking the logic.
"""

import ast
import asyncio
from pathlib import Path

import pytest

TRANSCRIBE_SOURCE = Path(__file__).resolve().parents[2] / 'routers' / 'transcribe.py'


def _extract_handle_image_chunk_code():
    """Compile only the real handle_image_chunk async def from transcribe.py."""
    tree = ast.parse(TRANSCRIBE_SOURCE.read_text(encoding='utf-8'), filename=str(TRANSCRIBE_SOURCE))
    target = None
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == 'handle_image_chunk':
            target = node
            break
    assert target is not None, "handle_image_chunk not found in transcribe.py"
    module = ast.Module(body=[target], type_ignores=[])
    ast.fix_missing_locations(module)
    return compile(module, filename=str(TRANSCRIBE_SOURCE), mode='exec')


class _Logger:
    def error(self, *args, **kwargs):
        pass

    def info(self, *args, **kwargs):
        pass


def _build_handle_image_chunk(spawn_calls):
    """Return a callable bound to the real source with free names stubbed out."""
    import time as _time

    def _spawn(coro):
        spawn_calls.append(1)
        # The real spawn schedules process_photo(...) on the event loop; we just
        # need to close the unawaited coroutine to avoid a warning.
        if hasattr(coro, 'close'):
            coro.close()

    namespace = {
        'logger': _Logger(),
        'sanitize': lambda value: value,
        'session_id': 'sess-test',
        '_cleanup_expired_image_chunks': lambda: None,
        'MAX_IMAGE_CHUNKS': 100,
        'time': _time,
        'spawn': _spawn,
        'process_photo': lambda *args, **kwargs: None,
        'all': all,
    }
    exec(_extract_handle_image_chunk_code(), namespace)
    return namespace['handle_image_chunk']


def _call(handler, chunk_data, cache):
    async def _noop_send(*args, **kwargs):
        return None

    asyncio.run(handler('uid-1', chunk_data, cache, _noop_send, []))


def test_negative_index_does_not_raise_index_error():
    """A sufficiently-negative index must be ignored, not raise IndexError."""
    spawn_calls = []
    handler = _build_handle_image_chunk(spawn_calls)
    cache = {}

    # |index| far exceeds total -> chunks_data[index] would IndexError on main.
    chunk = {'id': 'img-1', 'index': -1_000_000, 'total': 3, 'data': 'QUJDRA=='}

    # Must not raise. (On unfixed source this raises IndexError.)
    _call(handler, chunk, cache)

    # The out-of-range chunk was ignored: the buffer stays empty and nothing
    # was dispatched for assembly.
    assert cache['img-1']['chunks'] == [None, None, None]
    assert spawn_calls == []


def test_in_range_negative_index_does_not_corrupt_wrong_slot():
    """An in-range-negative index (e.g. -1) must not write the last slot."""
    spawn_calls = []
    handler = _build_handle_image_chunk(spawn_calls)
    cache = {}

    # -1 is "in range" for Python negative indexing and on main would overwrite
    # chunks_data[-1] (the final slot) with the wrong chunk's data.
    chunk = {'id': 'img-2', 'index': -1, 'total': 3, 'data': 'WRONG'}

    _call(handler, chunk, cache)

    # Fix ignores it: no slot (including the last) is written.
    assert cache['img-2']['chunks'] == [None, None, None]
    assert spawn_calls == []


def test_valid_index_still_stored():
    """Control: a valid in-bounds index is still accepted and stored."""
    spawn_calls = []
    handler = _build_handle_image_chunk(spawn_calls)
    cache = {}

    _call(handler, {'id': 'img-3', 'index': 0, 'total': 3, 'data': 'first'}, cache)
    _call(handler, {'id': 'img-3', 'index': 2, 'total': 3, 'data': 'third'}, cache)

    assert cache['img-3']['chunks'] == ['first', None, 'third']
    # Not all chunks present yet -> not dispatched.
    assert spawn_calls == []
