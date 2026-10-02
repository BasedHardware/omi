"""``sync_local_files`` must not run its billing and fair-use gates on the event loop.

``POST /v1/sync-local-files`` (``sync_local_files`` in ``routers/sync.py``) is an ``async``
handler that accepts large audio uploads, so its requests are long lived and concurrent.
It ran six synchronous Firestore/Redis calls directly on the loop: the hard-restriction
check, the daily audio ceiling, the transcription-credit check, the fair-use enforcement
stage, the Deepgram budget check, and the usage record written at the end.

The v2 handler in the same file (``sync_local_files_v2``) already offloads the first three
with ``await run_blocking(<executor>, fn, uid)``, and ``routers/listen/runtime.py`` offloads
the next two through ``ListenPersistence.call``, which is ``run_blocking(db_executor, ...)``.
These AST checks assert the offload stays in place for every one of them, including that the
``run_blocking`` call is awaited: a bare call would be a coroutine that never runs, so the
gate would silently stop being enforced while still looking offloaded.

A second wave (#15964) found six more plain-``def`` Redis calls reached through the backfill
and fair-use metering helpers rather than through Firestore directly: acquiring/releasing the
v1 backfill slot, reserving backfill speech, recording speech ms, reading rolling speech
totals, and recording Deepgram usage ms. The v2 handler already offloads the backfill slot
calls the same way; these checks extend the guard to the v1 handler's copies.

A third wave offloads blocking file I/O, CPU-intensive audio decoding, and temporary file
cleanups: retrieving uploaded file paths (shutil.copyfileobj disk writes), decoding Opus
files to WAV (libopus frame decoding and wave writes), and _cleanup_files (synchronous
unlinks across normal exit, budget exhaustion, and the finally block).
"""

import ast
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
SYNC_ROUTER = BACKEND_DIR / "routers" / "sync.py"

_HANDLER = "sync_local_files"
_BLOCKING_GATES = frozenset(
    {
        "get_hard_restriction_status",
        "is_daily_audio_ceiling_exceeded",
        "has_transcription_credits",
        "get_enforcement_stage",
        "is_dg_budget_exhausted",
        "record_usage",
        "try_acquire_backfill_slot",
        "release_backfill_slot",
        "reserve_backfill_speech",
        "record_speech_ms",
        "get_rolling_speech_ms",
        "record_dg_usage_ms",
        "retrieve_file_paths",
        "decode_files_to_wav",
        "_cleanup_files",
    }
)


def _dotted(func):
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
        return f"{func.value.id}.{func.attr}"
    return None


def _handler_node():
    tree = ast.parse(SYNC_ROUTER.read_text(encoding="utf-8"))
    node = next(
        (n for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef) and n.name == _HANDLER),
        None,
    )
    assert node is not None, f"async def {_HANDLER} not found in routers/sync.py"
    return node


def _direct_calls(node):
    return {name for sub in ast.walk(node) if isinstance(sub, ast.Call) and (name := _dotted(sub.func))}


def _offloaded_via_awaited_run_blocking(node):
    """Map of function name -> executor name, for AWAITED ``run_blocking(executor, fn, ...)`` calls."""
    offloaded = {}
    for sub in ast.walk(node):
        if not (isinstance(sub, ast.Await) and isinstance(sub.value, ast.Call)):
            continue
        call = sub.value
        if _dotted(call.func) == "run_blocking" and len(call.args) >= 2:
            name = _dotted(call.args[1])
            executor = _dotted(call.args[0])
            if name:
                offloaded[name] = executor
    return offloaded


class TestSyncLocalFilesOffload:
    def test_handler_is_async(self):
        assert isinstance(_handler_node(), ast.AsyncFunctionDef)

    def test_no_gate_runs_directly_on_the_event_loop(self):
        called = _direct_calls(_handler_node())
        for gate in sorted(_BLOCKING_GATES):
            assert gate not in called, (
                f"{_HANDLER} runs {gate} directly on the event loop. "
                f"Offload it with await run_blocking(<executor>, {gate}, ...)."
            )

    def test_every_gate_is_offloaded_via_awaited_run_blocking(self):
        offloaded = _offloaded_via_awaited_run_blocking(_handler_node())
        for gate in sorted(_BLOCKING_GATES):
            assert gate in offloaded, f"{gate} is not offloaded via an awaited run_blocking call"

    def test_gates_use_the_same_executors_the_rest_of_the_repo_uses(self):
        offloaded = _offloaded_via_awaited_run_blocking(_handler_node())
        assert offloaded["get_hard_restriction_status"] == "critical_executor"
        assert offloaded["has_transcription_credits"] == "critical_executor"
        assert offloaded["is_daily_audio_ceiling_exceeded"] == "db_executor"
        assert offloaded["get_enforcement_stage"] == "db_executor"
        assert offloaded["is_dg_budget_exhausted"] == "db_executor"
        assert offloaded["record_usage"] == "db_executor"
        assert offloaded["try_acquire_backfill_slot"] == "db_executor"
        assert offloaded["release_backfill_slot"] == "db_executor"
        assert offloaded["reserve_backfill_speech"] == "db_executor"
        assert offloaded["record_speech_ms"] == "db_executor"
        assert offloaded["get_rolling_speech_ms"] == "db_executor"
        assert offloaded["record_dg_usage_ms"] == "db_executor"
        assert offloaded["retrieve_file_paths"] == "sync_executor"
        assert offloaded["decode_files_to_wav"] == "sync_executor"
        assert offloaded["_cleanup_files"] == "sync_executor"
