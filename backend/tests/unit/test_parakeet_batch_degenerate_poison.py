"""Parakeet batch engine: a degenerate-audio file must not fail its whole batch.

Failure-Class: FC-batch-fault-domain-head-of-line-poison — one file shorter
than a single spectrogram frame makes NeMo's per-feature normalization raise
(``normalize_batch ... received a tensor of length 1``), and the flush path
set that same exception on EVERY future in the batch: up to max_batch_size
(32) healthy user transcriptions died with one user's broken upload. The
flush path now recognizes the input-shaped ValueError (message-identified,
raw prod line), re-runs each file of the batch as its own GPU call, and the
genuinely degenerate file fails alone with its own error. Metric:
``degenerate_batch_split_retries``.

The split path pins four contracts the grouped path never had to state:
a solo GPU call resolves its future with a per-file RESULT LIST, so the
request gets ``results[0]`` — never the raw list; already-resolved futures
are never re-submitted behind their backs; a single-file batch is never
retried (its grouped call was already the solo call); and unrelated faults
(CUDA OOM, generic ValueErrors, queue full) keep the old all-fail contract.
"""

import asyncio
import os
import sys
import wave as _wave
from pathlib import Path
from unittest.mock import MagicMock

import pytest

os.environ.setdefault("PARAKEET_MODEL", "nvidia/parakeet-tdt-0.6b-v3")
os.environ.setdefault("PARAKEET_DEVICE", "cpu")
os.environ.setdefault("PARAKEET_TORCH_COMPILE", "false")
os.environ.setdefault("PARAKEET_CUDA_GRAPHS", "false")

from testing.import_isolation import load_module_fresh, stub_modules

_PARAKEET_DIR = Path(__file__).resolve().parents[2] / "parakeet"

NORMALIZE_ERROR = (
    "normalize_batch with `per_feature` normalize_type received a tensor of length 1. "
    "This will result in torch.std() returning nan. Make sure your audio length has "
    "enough samples for a single feature (ex. at least `hop_length` for Mel Spectrograms)."
)


def _make_torch_stub():
    _torch = MagicMock()
    _torch.cuda.is_available.return_value = False
    _torch.cuda.memory_allocated.return_value = 0
    _torch_props = MagicMock()
    _torch_props.total_memory = 16 * 1024**3
    _torch.cuda.get_device_properties.return_value = _torch_props
    _torch.cuda.empty_cache = MagicMock()
    _torch.inference_mode = lambda: (lambda fn: fn)
    _torch.compile = lambda m: m
    _torch.backends.cudnn = MagicMock()
    return _torch


@pytest.fixture(scope="module", autouse=True)
def _parakeet_modules():
    _nemo_asr = MagicMock()
    _nemo = MagicMock()
    _nemo.collections.asr = _nemo_asr
    fakes = {
        "torch": _make_torch_stub(),
        "nemo": _nemo,
        "nemo.collections": _nemo.collections,
        "nemo.collections.asr": _nemo_asr,
        "pyannote": MagicMock(),
        "pyannote.audio": MagicMock(),
        "pyannote.audio.core": MagicMock(),
        "pyannote.audio.core.model": MagicMock(),
    }
    sys.path.insert(0, str(_PARAKEET_DIR))
    try:
        with stub_modules(fakes):
            gpu_worker = load_module_fresh("gpu_worker", str(_PARAKEET_DIR / "gpu_worker.py"))
            batch_engine = load_module_fresh("batch_engine", str(_PARAKEET_DIR / "batch_engine.py"))
            _g = globals()
            _g["GPUWorker"] = gpu_worker.GPUWorker
            _g["WorkItem"] = gpu_worker.WorkItem
            _g["WorkType"] = gpu_worker.WorkType
            _g["BatchEngine"] = batch_engine.BatchEngine
            _g["PendingRequest"] = batch_engine.PendingRequest
            _g["QueueFullError"] = batch_engine.QueueFullError
            _g["QueueTimeoutError"] = batch_engine.QueueTimeoutError
            _g["_is_degenerate_batch_normalization"] = batch_engine._is_degenerate_batch_normalization
            _g["_NORMALIZE_BATCH_ERROR"] = batch_engine._NORMALIZE_BATCH_ERROR
            yield
    finally:
        try:
            sys.path.remove(str(_PARAKEET_DIR))
        except ValueError:
            pass


def _make_gpu_worker(plan):
    """GPU worker whose submit result/exception comes from ``plan(payload)``.

    A plan returning a Future gets that future back verbatim — the solo call
    then hangs until the test resolves it (the never-resolves sentinel for
    cancellation tests).
    """
    gpu = MagicMock(spec=GPUWorker)
    gpu.is_ready = True
    gpu.vram_info = {"total_mb": 0, "baseline_mb": 0, "attention_mode": "full", "auto_threshold_sec": 300}

    def submit(payload, loop):
        fut = loop.create_future()
        item = WorkItem(WorkType.BATCH_TRANSCRIBE, payload, future=fut, loop=loop)
        outcome = plan(payload)
        if isinstance(outcome, asyncio.Future):
            return outcome, item
        if isinstance(outcome, Exception):
            loop.call_soon(fut.set_exception, outcome)
        else:
            loop.call_soon(fut.set_result, outcome)
        return fut, item

    gpu.submit.side_effect = submit
    return gpu


def _record_calls(gpu, calls):
    """Wrap a fake worker so every grouped/solo payload path list is recorded."""
    inner = gpu.submit.side_effect

    def recording(payload, loop):
        calls.append(list(payload["audio_paths"]))
        return inner(payload, loop)

    gpu.submit.side_effect = recording
    return gpu


def _run_engine(gpu, paths, *, engine_kw=None, submit_kw=None):
    """Submit every path, flush, and return (futures, engine) after settle."""
    engine_kw = engine_kw or {}
    submit_kw = submit_kw or {}
    engine = BatchEngine(gpu, max_batch_size=len(paths) or 1, max_wait_seconds=0.01, **engine_kw)
    loop = asyncio.new_event_loop()
    try:

        async def run():
            await engine.start()
            try:
                futs = [asyncio.ensure_future(engine.submit(p, owns_file=False, **submit_kw)) for p in paths]
                await asyncio.gather(*futs, return_exceptions=True)
            finally:
                await engine.stop()
            return futs

        return loop.run_until_complete(run()), engine
    finally:
        loop.close()


def _outcomes(futs):
    out = []
    for fut in futs:
        if fut.cancelled():
            out.append(("cancelled", None))
        elif fut.exception() is not None:
            out.append(("error", fut.exception()))
        else:
            out.append(("ok", fut.result()))
    return out


def write_wav_16000hz(directory, seconds: float = 0.0, name: str = "clip.wav") -> str:
    """Write a tiny real PCM16 WAV so submit() can measure its duration."""
    path = str(Path(directory) / name)
    with _wave.open(path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes(b"\x00\x00" * max(0, int(seconds * 16000)))
    return path


def _ok_result(path: str) -> list:
    """The per-file result list one solo/grouped file maps to."""
    return [{"text": f"ok:{path}", "timestamp": {"segment": []}}]


# ---------------------------------------------------------------------------
# Detector: the message contract that separates input-shaped faults from GPU
# faults. These run against the module-level predicate directly.
# ---------------------------------------------------------------------------


def test_detector_matches_the_exact_prod_message():
    assert _is_degenerate_batch_normalization(ValueError(NORMALIZE_ERROR))


def test_detector_matches_the_length_zero_variant():
    variant = NORMALIZE_ERROR.replace("tensor of length 1", "tensor of length 0")
    assert _is_degenerate_batch_normalization(ValueError(variant))


def test_detector_matches_other_length_values():
    variant = NORMALIZE_ERROR.replace("tensor of length 1", "tensor of length 7")
    assert _is_degenerate_batch_normalization(ValueError(variant))


def test_detector_matches_when_wrapped_in_a_runtime_error_chain():
    wrapped = RuntimeError("batch failed: " + NORMALIZE_ERROR)
    assert _is_degenerate_batch_normalization(wrapped)


def test_detector_rejects_a_generic_value_error():
    assert not _is_degenerate_batch_normalization(ValueError("audio file is not a valid wav"))


def test_detector_rejects_cuda_oom_messages():
    assert not _is_degenerate_batch_normalization(RuntimeError("CUDA out of memory"))


def test_detector_rejects_the_per_channel_normalization_spelling():
    other = NORMALIZE_ERROR.replace("`per_feature`", "`per_channel`")
    assert not _is_degenerate_batch_normalization(ValueError(other))


def test_detector_rejects_an_empty_message():
    assert not _is_degenerate_batch_normalization(ValueError(""))


def test_detector_rejects_gpu_queue_full_messages():
    assert not _is_degenerate_batch_normalization(RuntimeError("GPU queue full"))


def test_detector_rejects_key_error_strings():
    assert not _is_degenerate_batch_normalization(KeyError("audio_paths"))


def test_detector_prefix_pinned_to_the_prod_line_prefix():
    # The prefix ends at the varying length value: everything before it is the
    # stable identity, everything after is NeMo's per-length advice text.
    assert _NORMALIZE_BATCH_ERROR.endswith("received a tensor of length")
    assert _NORMALIZE_BATCH_ERROR.startswith("normalize_batch with `per_feature`")


# ---------------------------------------------------------------------------
# Core poison behavior — the RED-on-parent contracts.
# ---------------------------------------------------------------------------


def test_degenerate_batch_retries_files_individually():
    """The grouped call dies on normalization; solo retries still transcribe."""
    poison = "/avo-fake/degenerate.wav"
    healthy = ["/avo-fake/a.wav", "/avo-fake/b.wav"]
    calls = []

    def plan(payload):
        calls.append(list(payload["audio_paths"]))
        if len(payload["audio_paths"]) > 1:
            return ValueError(NORMALIZE_ERROR)
        path = payload["audio_paths"][0]
        if path == poison:
            return ValueError(NORMALIZE_ERROR)
        return _ok_result(path)

    futs, engine = _run_engine(_make_gpu_worker(plan), healthy + [poison])
    outcomes = _outcomes(futs)

    assert outcomes[0][0] == "ok" and outcomes[0][1]["text"] == "ok:/avo-fake/a.wav"
    assert outcomes[1][0] == "ok" and outcomes[1][1]["text"] == "ok:/avo-fake/b.wav"
    # The genuinely degenerate file still fails — but alone, with its own error.
    assert outcomes[2][0] == "error" and NORMALIZE_ERROR in str(outcomes[2][1])

    # One grouped call, then one solo call per file.
    assert [len(c) for c in calls] == [3, 1, 1, 1]
    assert engine.metrics["degenerate_batch_split_retries"] == 1


def test_poison_first_still_saves_batchmates():
    poison = "/avo-fake/poison.wav"
    paths = [poison, "/avo-fake/a.wav", "/avo-fake/b.wav"]

    def plan(payload):
        if len(payload["audio_paths"]) > 1:
            return ValueError(NORMALIZE_ERROR)
        path = payload["audio_paths"][0]
        if path == poison:
            return ValueError(NORMALIZE_ERROR)
        return _ok_result(path)

    futs, _ = _run_engine(_make_gpu_worker(plan), paths)
    outcomes = _outcomes(futs)
    assert outcomes[0][0] == "error" and NORMALIZE_ERROR in str(outcomes[0][1])
    assert outcomes[1] == ("ok", _ok_result(paths[1])[0])
    assert outcomes[2] == ("ok", _ok_result(paths[2])[0])


def test_poison_last_still_saves_batchmates():
    poison = "/avo-fake/poison.wav"
    paths = ["/avo-fake/a.wav", "/avo-fake/b.wav", poison]

    def plan(payload):
        if len(payload["audio_paths"]) > 1:
            return ValueError(NORMALIZE_ERROR)
        path = payload["audio_paths"][0]
        if path == poison:
            return ValueError(NORMALIZE_ERROR)
        return _ok_result(path)

    futs, _ = _run_engine(_make_gpu_worker(plan), paths)
    outcomes = _outcomes(futs)
    assert outcomes[0] == ("ok", _ok_result(paths[0])[0])
    assert outcomes[1] == ("ok", _ok_result(paths[1])[0])
    assert outcomes[2][0] == "error" and NORMALIZE_ERROR in str(outcomes[2][1])


def test_poison_middle_still_saves_batchmates():
    poison = "/avo-fake/poison.wav"
    paths = ["/avo-fake/a.wav", poison, "/avo-fake/c.wav"]

    def plan(payload):
        if len(payload["audio_paths"]) > 1:
            return ValueError(NORMALIZE_ERROR)
        path = payload["audio_paths"][0]
        if path == poison:
            return ValueError(NORMALIZE_ERROR)
        return _ok_result(path)

    futs, _ = _run_engine(_make_gpu_worker(plan), paths)
    outcomes = _outcomes(futs)
    assert outcomes[0] == ("ok", _ok_result(paths[0])[0])
    assert outcomes[1][0] == "error" and NORMALIZE_ERROR in str(outcomes[1][1])
    assert outcomes[2] == ("ok", _ok_result(paths[2])[0])


def test_two_poison_files_both_fail_alone():
    poisons = {"/avo-fake/p1.wav", "/avo-fake/p2.wav"}
    paths = ["/avo-fake/p1.wav", "/avo-fake/a.wav", "/avo-fake/p2.wav", "/avo-fake/b.wav"]
    calls = []

    def plan(payload):
        calls.append(list(payload["audio_paths"]))
        if len(payload["audio_paths"]) > 1:
            return ValueError(NORMALIZE_ERROR)
        path = payload["audio_paths"][0]
        if path in poisons:
            return ValueError(NORMALIZE_ERROR)
        return _ok_result(path)

    futs, _ = _run_engine(_make_gpu_worker(plan), paths)
    outcomes = _outcomes(futs)
    assert outcomes[0][0] == "error" and NORMALIZE_ERROR in str(outcomes[0][1])
    assert outcomes[1] == ("ok", _ok_result(paths[1])[0])
    assert outcomes[2][0] == "error" and NORMALIZE_ERROR in str(outcomes[2][1])
    assert outcomes[3] == ("ok", _ok_result(paths[3])[0])
    assert [len(c) for c in calls] == [4, 1, 1, 1, 1]


def test_full_batch_of_32_with_one_poison_saves_31():
    poison = "/avo-fake/poison.wav"
    paths = [f"/avo-fake/f{i}.wav" for i in range(31)] + [poison]
    solo_calls = []

    def plan(payload):
        if len(payload["audio_paths"]) > 1:
            return ValueError(NORMALIZE_ERROR)
        path = payload["audio_paths"][0]
        solo_calls.append(path)
        if path == poison:
            return ValueError(NORMALIZE_ERROR)
        return _ok_result(path)

    futs, engine = _run_engine(_make_gpu_worker(plan), paths)
    outcomes = _outcomes(futs)
    saved = [o for o in outcomes if o[0] == "ok"]
    failed = [o for o in outcomes if o[0] == "error"]
    assert len(saved) == 31
    assert len(failed) == 1
    assert NORMALIZE_ERROR in str(failed[0][1])
    assert len(solo_calls) == 32
    assert engine.metrics["degenerate_batch_split_retries"] == 1


def test_solo_failure_is_isolated_to_the_poisoned_file():
    """A poison file's solo failure never leaks onto its batchmates."""
    poison = "/avo-fake/degenerate.wav"
    paths = ["/avo-fake/a.wav", poison, "/avo-fake/c.wav"]

    def plan(payload):
        if len(payload["audio_paths"]) > 1:
            return ValueError(NORMALIZE_ERROR)
        path = payload["audio_paths"][0]
        if path == poison:
            return ValueError("audio file is too short for transcription")
        return _ok_result(path)

    futs, _ = _run_engine(_make_gpu_worker(plan), paths)
    outcomes = _outcomes(futs)
    assert outcomes[0] == ("ok", _ok_result(paths[0])[0])
    assert outcomes[1][0] == "error" and "too short" in str(outcomes[1][1])
    assert outcomes[2] == ("ok", _ok_result(paths[2])[0])


def test_split_warning_is_logged_with_the_file_count(caplog):
    paths = ["/avo-fake/a.wav", "/avo-fake/b.wav"]

    def plan(payload):
        if len(payload["audio_paths"]) > 1:
            return ValueError(NORMALIZE_ERROR)
        return _ok_result(payload["audio_paths"][0])

    import logging

    with caplog.at_level(logging.WARNING, logger="batch_engine"):
        _futs, _engine = _run_engine(_make_gpu_worker(plan), paths)
    assert any("retrying 2 files individually" in rec.message for rec in caplog.records)


def test_zero_second_wav_does_not_poison_its_batch(tmp_path):
    """A real empty WAV (the prod poison) fails alone; real siblings transcribe."""
    poison = write_wav_16000hz(tmp_path, 0.0, "poison.wav")
    healthy = [write_wav_16000hz(tmp_path, 0.5, "a.wav"), write_wav_16000hz(tmp_path, 0.5, "b.wav")]

    def plan(payload):
        if len(payload["audio_paths"]) > 1:
            return ValueError(NORMALIZE_ERROR)
        path = payload["audio_paths"][0]
        if path.endswith("poison.wav"):
            return ValueError(NORMALIZE_ERROR)
        return _ok_result(path)

    futs, _ = _run_engine(_make_gpu_worker(plan), [healthy[0], poison, healthy[1]])
    outcomes = _outcomes(futs)
    assert outcomes[0] == ("ok", _ok_result(healthy[0])[0])
    assert outcomes[1][0] == "error" and NORMALIZE_ERROR in str(outcomes[1][1])
    assert outcomes[2] == ("ok", _ok_result(healthy[1])[0])


def test_live_lane_poison_batch_splits():
    paths = ["/avo-fake/a.wav", "/avo-fake/poison.wav"]

    def plan(payload):
        if len(payload["audio_paths"]) > 1:
            return ValueError(NORMALIZE_ERROR)
        path = payload["audio_paths"][0]
        if path.endswith("poison.wav"):
            return ValueError(NORMALIZE_ERROR)
        return _ok_result(path)

    futs, engine = _run_engine(_make_gpu_worker(plan), paths, submit_kw={"lane": "live"})
    outcomes = _outcomes(futs)
    assert outcomes[0] == ("ok", _ok_result(paths[0])[0])
    assert outcomes[1][0] == "error" and NORMALIZE_ERROR in str(outcomes[1][1])
    assert engine.metrics["degenerate_batch_split_retries"] == 1


def test_backfill_lane_poison_batch_splits():
    paths = ["/avo-fake/a.wav", "/avo-fake/poison.wav"]

    def plan(payload):
        if len(payload["audio_paths"]) > 1:
            return ValueError(NORMALIZE_ERROR)
        path = payload["audio_paths"][0]
        if path.endswith("poison.wav"):
            return ValueError(NORMALIZE_ERROR)
        return _ok_result(path)

    futs, engine = _run_engine(_make_gpu_worker(plan), paths, submit_kw={"lane": "backfill"})
    outcomes = _outcomes(futs)
    assert outcomes[0] == ("ok", _ok_result(paths[0])[0])
    assert outcomes[1][0] == "error"
    assert engine.metrics["degenerate_batch_split_retries"] == 1


def test_two_consecutive_poison_flushes_each_count_one():
    """A second poisoned flush splits again: the metric accumulates per flush."""
    paths_round_1 = ["/avo-fake/a.wav", "/avo-fake/p1.wav"]
    paths_round_2 = ["/avo-fake/b.wav", "/avo-fake/p2.wav"]
    calls = []
    engine = None

    def plan(payload):
        calls.append(list(payload["audio_paths"]))
        if len(payload["audio_paths"]) > 1:
            return ValueError(NORMALIZE_ERROR)
        path = payload["audio_paths"][0]
        if "p1" in path or "p2" in path:
            return ValueError(NORMALIZE_ERROR)
        return _ok_result(path)

    gpu = _make_gpu_worker(plan)
    loop = asyncio.new_event_loop()
    try:

        async def run():
            nonlocal engine
            engine = BatchEngine(gpu, max_batch_size=2, max_wait_seconds=0.01)
            await engine.start()
            results = []
            for pair in (paths_round_1, paths_round_2):
                futs = [asyncio.ensure_future(engine.submit(p, owns_file=False)) for p in pair]
                results.extend(await asyncio.gather(*futs, return_exceptions=True))
            await engine.stop()
            return results

        loop.run_until_complete(run())
    finally:
        loop.close()

    assert engine.metrics["degenerate_batch_split_retries"] == 2
    assert [len(c) for c in calls] == [2, 1, 1, 2, 1, 1]


def test_stop_with_a_pending_poison_batch_still_splits():
    """The stop() drain flush splits too — queued work is not abandoned."""
    paths = ["/avo-fake/a.wav", "/avo-fake/poison.wav"]

    def plan(payload):
        if len(payload["audio_paths"]) > 1:
            return ValueError(NORMALIZE_ERROR)
        path = payload["audio_paths"][0]
        if path.endswith("poison.wav"):
            return ValueError(NORMALIZE_ERROR)
        return _ok_result(path)

    gpu = _make_gpu_worker(plan)
    engine = BatchEngine(gpu, max_batch_size=2, max_wait_seconds=30.0)
    loop = asyncio.new_event_loop()
    try:

        async def run():
            await engine.start()
            futs = [asyncio.ensure_future(engine.submit(p, owns_file=False)) for p in paths]
            await asyncio.sleep(0.05)
            await engine.stop()
            return futs

        futs = loop.run_until_complete(run())
    finally:
        loop.close()
    outcomes = _outcomes(futs)
    assert outcomes[0] == ("ok", _ok_result(paths[0])[0])
    assert outcomes[1][0] == "error" and NORMALIZE_ERROR in str(outcomes[1][1])
    assert engine.metrics["degenerate_batch_split_retries"] == 1


def test_vram_limited_engine_still_splits_on_poison():
    """The VRAM-sizing path does not bypass the split: small batches split too."""
    paths = ["/avo-fake/a.wav", "/avo-fake/poison.wav"]

    def plan(payload):
        if len(payload["audio_paths"]) > 1:
            return ValueError(NORMALIZE_ERROR)
        path = payload["audio_paths"][0]
        if path.endswith("poison.wav"):
            return ValueError(NORMALIZE_ERROR)
        return _ok_result(path)

    gpu = _make_gpu_worker(plan)
    gpu.vram_info = {
        "total_mb": 80 * 1024,
        "baseline_mb": 6 * 1024,
        "attention_mode": "full",
        "auto_threshold_sec": 300,
    }
    futs, engine = _run_engine(gpu, paths)
    outcomes = _outcomes(futs)
    assert outcomes[0] == ("ok", _ok_result(paths[0])[0])
    assert outcomes[1][0] == "error"
    assert engine.metrics["degenerate_batch_split_retries"] == 1


# ---------------------------------------------------------------------------
# Result-shape contract: solo calls deliver results[0], never the raw list.
# ---------------------------------------------------------------------------


def test_split_delivers_per_file_dict_not_the_raw_list():
    """The pinned shape bug: submit() resolves a dict, not a one-entry list."""

    def plan(payload):
        if len(payload["audio_paths"]) > 1:
            return ValueError(NORMALIZE_ERROR)
        return _ok_result(payload["audio_paths"][0])

    futs, _ = _run_engine(_make_gpu_worker(plan), ["/avo-fake/a.wav", "/avo-fake/b.wav"])
    outcomes = _outcomes(futs)
    for state, value in outcomes:
        assert state == "ok"
        assert isinstance(value, dict), f"split retry delivered {type(value).__name__}, not the per-file dict"
        assert value["text"].startswith("ok:")


def test_split_result_carries_text_and_timestamp():
    def plan(payload):
        if len(payload["audio_paths"]) > 1:
            return ValueError(NORMALIZE_ERROR)
        return [{"text": "hello", "timestamp": {"segment": [{"start": 0.0, "end": 1.0}]}}]

    futs, _ = _run_engine(_make_gpu_worker(plan), ["/avo-fake/a.wav", "/avo-fake/b.wav"])
    outcomes = _outcomes(futs)
    assert outcomes[0][1]["text"] == "hello"
    assert outcomes[0][1]["timestamp"]["segment"][0]["end"] == 1.0


def test_split_keeps_each_future_bound_to_its_own_file():
    """Mixed results never cross: every future resolves its own file's payload."""

    def plan(payload):
        if len(payload["audio_paths"]) > 1:
            return ValueError(NORMALIZE_ERROR)
        return [{"text": f"solo:{payload['audio_paths'][0]}", "timestamp": {}}]

    paths = ["/avo-fake/a.wav", "/avo-fake/b.wav", "/avo-fake/c.wav"]
    futs, _ = _run_engine(_make_gpu_worker(plan), paths)
    outcomes = _outcomes(futs)
    for path, (state, value) in zip(paths, outcomes):
        assert state == "ok"
        assert value["text"] == f"solo:{path}"


def test_split_solo_none_entry_still_resolves():
    """A GPU worker delivering [None] resolves the request with None, not an error."""

    def plan(payload):
        if len(payload["audio_paths"]) > 1:
            return ValueError(NORMALIZE_ERROR)
        return [None]

    futs, _ = _run_engine(_make_gpu_worker(plan), ["/avo-fake/a.wav", "/avo-fake/b.wav"])
    outcomes = _outcomes(futs)
    assert all(state == "ok" and value is None for state, value in outcomes)


def test_split_solo_non_list_payload_passes_through():
    """A non-list solo payload resolves as-is (forward-compatible passthrough)."""

    def plan(payload):
        if len(payload["audio_paths"]) > 1:
            return ValueError(NORMALIZE_ERROR)
        return {"text": "bare", "timestamp": {}}

    futs, _ = _run_engine(_make_gpu_worker(plan), ["/avo-fake/a.wav", "/avo-fake/b.wav"])
    outcomes = _outcomes(futs)
    assert outcomes[0] == ("ok", {"text": "bare", "timestamp": {}})


def test_grouped_success_still_delivers_per_file_dicts():
    """Control: the healthy grouped path's zipped per-file dict is unchanged."""

    def plan(payload):
        return [_ok_result(p)[0] for p in payload["audio_paths"]]

    paths = ["/avo-fake/a.wav", "/avo-fake/b.wav"]
    futs, _ = _run_engine(_make_gpu_worker(plan), paths)
    outcomes = _outcomes(futs)
    assert outcomes[0] == ("ok", _ok_result(paths[0])[0])
    assert outcomes[1] == ("ok", _ok_result(paths[1])[0])


def test_grouped_short_results_still_zip_with_empty_text_fallback():
    """Control: a results list shorter than the batch fills {"text": ""}."""

    def plan(payload):
        return [_ok_result(payload["audio_paths"][0])[0]]

    futs, _ = _run_engine(_make_gpu_worker(plan), ["/avo-fake/a.wav", "/avo-fake/b.wav"])
    outcomes = _outcomes(futs)
    assert outcomes[0] == ("ok", _ok_result("/avo-fake/a.wav")[0])
    assert outcomes[1] == ("ok", {"text": ""})


# ---------------------------------------------------------------------------
# Solo-call payload contract: what the retry submits to the GPU worker.
# ---------------------------------------------------------------------------


def test_solo_payload_carries_batch_size_one():
    payloads = []

    def plan(payload):
        payloads.append(dict(payload))
        if len(payload["audio_paths"]) > 1:
            return ValueError(NORMALIZE_ERROR)
        return _ok_result(payload["audio_paths"][0])

    _futs, _engine = _run_engine(_make_gpu_worker(plan), ["/avo-fake/a.wav", "/avo-fake/b.wav"])
    solo_payloads = [p for p in payloads if len(p["audio_paths"]) == 1]
    assert len(solo_payloads) == 2
    assert all(p["batch_size"] == 1 for p in solo_payloads)


def test_solo_payload_carries_one_audio_path_in_batch_order():
    order = []

    def plan(payload):
        if len(payload["audio_paths"]) > 1:
            return ValueError(NORMALIZE_ERROR)
        order.append(payload["audio_paths"][0])
        return _ok_result(payload["audio_paths"][0])

    paths = ["/avo-fake/a.wav", "/avo-fake/b.wav", "/avo-fake/c.wav"]
    _futs, _engine = _run_engine(_make_gpu_worker(plan), paths)
    assert order == paths


def test_solo_payload_propagates_timestamps_false():
    payloads = []

    def plan(payload):
        payloads.append(dict(payload))
        if len(payload["audio_paths"]) > 1:
            return ValueError(NORMALIZE_ERROR)
        return _ok_result(payload["audio_paths"][0])

    _futs, _engine = _run_engine(
        _make_gpu_worker(plan), ["/avo-fake/a.wav", "/avo-fake/b.wav"], submit_kw={"timestamps": False}
    )
    solo_payloads = [p for p in payloads if len(p["audio_paths"]) == 1]
    assert solo_payloads and all(p["timestamps"] is False for p in solo_payloads)


def test_solo_payload_propagates_timestamps_true_by_default():
    payloads = []

    def plan(payload):
        payloads.append(dict(payload))
        if len(payload["audio_paths"]) > 1:
            return ValueError(NORMALIZE_ERROR)
        return _ok_result(payload["audio_paths"][0])

    _futs, _engine = _run_engine(_make_gpu_worker(plan), ["/avo-fake/a.wav", "/avo-fake/b.wav"])
    solo_payloads = [p for p in payloads if len(p["audio_paths"]) == 1]
    assert solo_payloads and all(p["timestamps"] is True for p in solo_payloads)


def test_solo_payload_durations_use_the_measured_wav_duration(tmp_path):
    payloads = []
    healthy = [write_wav_16000hz(tmp_path, 0.5, "a.wav"), write_wav_16000hz(tmp_path, 0.5, "b.wav")]

    def plan(payload):
        payloads.append(dict(payload))
        if len(payload["audio_paths"]) > 1:
            return ValueError(NORMALIZE_ERROR)
        return _ok_result(payload["audio_paths"][0])

    _futs, _engine = _run_engine(_make_gpu_worker(plan), healthy)
    solo_payloads = [p for p in payloads if len(p["audio_paths"]) == 1]
    assert len(solo_payloads) == 2
    for p in solo_payloads:
        assert len(p["durations"]) == 1
        assert 0.0 < p["durations"][0] < 1.0


def test_solo_payload_durations_fall_back_to_the_auto_threshold_when_unknown():
    payloads = []

    def plan(payload):
        payloads.append(dict(payload))
        if len(payload["audio_paths"]) > 1:
            return ValueError(NORMALIZE_ERROR)
        return _ok_result(payload["audio_paths"][0])

    _futs, _engine = _run_engine(_make_gpu_worker(plan), ["/avo-fake/missing-a.wav", "/avo-fake/missing-b.wav"])
    solo_payloads = [p for p in payloads if len(p["audio_paths"]) == 1]
    assert solo_payloads and all(p["durations"] == [300.0] for p in solo_payloads)


def test_grouped_payload_keeps_its_original_shape():
    """Control: the grouped call still sends the whole batch in one payload."""
    payloads = []

    def plan(payload):
        payloads.append(dict(payload))
        return [_ok_result(p)[0] for p in payload["audio_paths"]]

    paths = ["/avo-fake/a.wav", "/avo-fake/b.wav", "/avo-fake/c.wav"]
    _futs, _engine = _run_engine(_make_gpu_worker(plan), paths)
    assert len(payloads) == 1
    assert payloads[0]["audio_paths"] == paths
    assert payloads[0]["batch_size"] == 3
    assert len(payloads[0]["durations"]) == 3


# ---------------------------------------------------------------------------
# Guard rails: what must NOT split.
# ---------------------------------------------------------------------------


def test_single_file_batch_failure_is_terminal():
    """A solo call that fails is already isolated — never retried again."""
    calls = []

    def plan(payload):
        calls.append(list(payload["audio_paths"]))
        return ValueError(NORMALIZE_ERROR)

    futs, engine = _run_engine(_make_gpu_worker(plan), ["/avo-fake/short.wav"])
    outcomes = _outcomes(futs)
    assert outcomes[0][0] == "error" and NORMALIZE_ERROR in str(outcomes[0][1])
    assert len(calls) == 1
    assert engine.metrics["degenerate_batch_split_retries"] == 0


def test_generic_batch_failure_still_fails_all_without_retry():
    calls = []

    def plan(payload):
        calls.append(list(payload["audio_paths"]))
        return ValueError("audio file is not a valid wav")

    futs, engine = _run_engine(_make_gpu_worker(plan), ["/avo-fake/a.wav", "/avo-fake/b.wav"])
    outcomes = _outcomes(futs)
    assert all(state == "error" for state, _ in outcomes)
    assert len(calls) == 1
    assert engine.metrics["degenerate_batch_split_retries"] == 0


def test_cuda_oom_message_fails_all_and_books_the_oom_callback():
    oom_calls = []

    def plan(payload):
        return RuntimeError("CUDA out of memory")

    futs, engine = _run_engine(
        _make_gpu_worker(plan),
        ["/avo-fake/a.wav", "/avo-fake/b.wav"],
        engine_kw={"on_gpu_oom": lambda: oom_calls.append(1)},
    )
    outcomes = _outcomes(futs)
    assert all(state == "error" and "CUDA out of memory" in str(value) for state, value in outcomes)
    assert len(oom_calls) == 1
    assert engine.metrics["degenerate_batch_split_retries"] == 0


def test_oom_error_type_name_books_the_oom_callback():
    class OutOfMemoryError(Exception):
        pass

    oom_calls = []

    def plan(payload):
        return OutOfMemoryError("GPU Allocation failed")

    futs, engine = _run_engine(
        _make_gpu_worker(plan),
        ["/avo-fake/a.wav", "/avo-fake/b.wav"],
        engine_kw={"on_gpu_oom": lambda: oom_calls.append(1)},
    )
    outcomes = _outcomes(futs)
    assert all(state == "error" for state, _ in outcomes)
    assert len(oom_calls) == 1
    assert engine.metrics["degenerate_batch_split_retries"] == 0


def test_no_split_when_a_future_is_already_resolved():
    """The one-shot guard: pre-resolved work is never re-submitted behind backs."""
    calls = []

    def plan(payload):
        calls.append(list(payload["audio_paths"]))
        if len(payload["audio_paths"]) > 1:
            return ValueError(NORMALIZE_ERROR)
        return _ok_result(payload["audio_paths"][0])

    gpu = _make_gpu_worker(plan)
    engine = BatchEngine(gpu, max_batch_size=2, max_wait_seconds=0.01)
    loop = asyncio.new_event_loop()
    try:

        async def run():
            await engine.start()
            original_select = engine._select_batch

            def select_with_pre_resolved_head():
                batch = original_select()
                if batch:
                    batch[0].future.set_result({"text": "pre-resolved", "timestamp": {}})
                return batch

            engine._select_batch = select_with_pre_resolved_head
            futs = [
                asyncio.ensure_future(engine.submit(p, owns_file=False)) for p in ["/avo-fake/a.wav", "/avo-fake/b.wav"]
            ]
            await asyncio.gather(*futs, return_exceptions=True)
            await engine.stop()
            return futs

        futs = loop.run_until_complete(run())
    finally:
        loop.close()
    outcomes = _outcomes(futs)
    assert outcomes[0] == ("ok", {"text": "pre-resolved", "timestamp": {}})
    assert outcomes[1][0] == "error"
    assert len(calls) == 1, "a pre-resolved batch member must not trigger solo re-submission"
    assert engine.metrics["degenerate_batch_split_retries"] == 0


def test_split_path_never_books_the_oom_callback():
    """The split is not a GPU fault: the OOM callback must stay silent."""
    oom_calls = []

    def plan(payload):
        if len(payload["audio_paths"]) > 1:
            return ValueError(NORMALIZE_ERROR)
        return _ok_result(payload["audio_paths"][0])

    futs, _engine = _run_engine(
        _make_gpu_worker(plan),
        ["/avo-fake/a.wav", "/avo-fake/b.wav"],
        engine_kw={"on_gpu_oom": lambda: oom_calls.append(1)},
    )
    outcomes = _outcomes(futs)
    assert outcomes[0][0] == "ok"
    assert oom_calls == []


def test_split_failure_of_a_single_member_still_books_that_member_once():
    """A poison solo failure books exactly one error future — no double-set."""

    def plan(payload):
        if len(payload["audio_paths"]) > 1:
            return ValueError(NORMALIZE_ERROR)
        path = payload["audio_paths"][0]
        if path.endswith("poison.wav"):
            return ValueError(NORMALIZE_ERROR)
        return _ok_result(path)

    futs, _ = _run_engine(_make_gpu_worker(plan), ["/avo-fake/a.wav", "/avo-fake/poison.wav"])
    outcomes = _outcomes(futs)
    errors = [value for state, value in outcomes if state == "error"]
    assert len(errors) == 1
    assert errors[0].args and NORMALIZE_ERROR in str(errors[0])


def test_queue_full_rejection_keeps_the_split_metric_clean():
    """Queue-depth refusals never touch the split path.

    Deterministic refusal: a live request is pre-seeded into the pending
    queue (the flush loop is parked for the whole test), so the next submit
    hits the depth check synchronously — before any flush or GPU work.
    """
    engine = BatchEngine(
        _make_gpu_worker(lambda payload: _ok_result(payload["audio_paths"][0])),
        max_batch_size=8,
        max_queue_depth=1,
        max_wait_seconds=30.0,
    )
    loop = asyncio.new_event_loop()
    refused = []

    async def run():
        await engine.start()
        blocker = PendingRequest(
            audio_path="/avo-fake/blocker.wav",
            timestamps=True,
            future=asyncio.get_running_loop().create_future(),
        )
        engine._pending.append(blocker)  # depth 1 of max_queue_depth 1
        try:
            await engine.submit("/avo-fake/b.wav", owns_file=False)
        except QueueFullError as exc:
            refused.append(exc)
        await engine.stop()

    loop.run_until_complete(run())
    loop.close()
    assert len(refused) == 1
    assert engine.metrics["degenerate_batch_split_retries"] == 0
    assert engine.metrics["rejected_requests"] == 1


def test_expired_queue_deadline_keeps_the_split_metric_clean():
    engine = BatchEngine(_make_gpu_worker(lambda payload: _ok_result(payload["audio_paths"][0])), max_batch_size=2)
    loop = asyncio.new_event_loop()
    try:

        async def run():
            await engine.start()
            with pytest.raises(QueueTimeoutError):
                await engine.submit("/avo-fake/a.wav", owns_file=False, lane="live", queue_deadline=0.0)
            await engine.stop()
            return None

        loop.run_until_complete(run())
    finally:
        loop.close()
    assert engine.metrics["degenerate_batch_split_retries"] == 0


def test_expired_queue_deadline_books_the_timeout_and_not_the_normalization_error():
    """A deadline-expired request's failure is the queue timeout, never a split."""
    engine = BatchEngine(_make_gpu_worker(lambda payload: _ok_result(payload["audio_paths"][0])), max_batch_size=2)
    loop = asyncio.new_event_loop()
    caught = []

    try:

        async def run():
            await engine.start()
            try:
                await engine.submit("/avo-fake/a.wav", owns_file=False, lane="live", queue_deadline=0.0)
            except QueueTimeoutError as exc:
                caught.append(exc)
            await engine.stop()

        loop.run_until_complete(run())
    finally:
        loop.close()
    assert len(caught) == 1
    assert "normalize_batch" not in str(caught[0])


# ---------------------------------------------------------------------------
# White-box: _retry_batch_one_by_one semantics the grouped path can't exercise.
# ---------------------------------------------------------------------------


def _retry_engine(plan=None):
    """A white-box engine whose _loop is bound to the running event loop.

    `_retry_batch_one_by_one` submits through `self._loop`, which only
    `start()` assigns; the white-box tests call the retry directly, so they
    bind it here instead. ``plan`` selects the fake GPU outcome.
    """
    if plan is None:
        plan = lambda payload: _ok_result(payload["audio_paths"][0])  # noqa: E731
    return BatchEngine(_make_gpu_worker(plan), max_batch_size=4)


def _new_request(path, loop, done_result=None):
    future = loop.create_future()
    req = PendingRequest(audio_path=path, timestamps=True, future=future)
    if done_result is not None:
        future.set_result(done_result)
    return req


def test_retry_method_skips_already_done_requests():
    calls = []

    def plan(payload):
        calls.append(list(payload["audio_paths"]))
        return _ok_result(payload["audio_paths"][0])

    async def main():
        engine = _retry_engine(plan)
        engine._loop = asyncio.get_running_loop()
        done = _new_request("/avo-fake/done.wav", asyncio.get_running_loop(), done_result={"text": "kept"})
        pending = _new_request("/avo-fake/live.wav", asyncio.get_running_loop())
        await engine._retry_batch_one_by_one([done, pending])
        return done, pending

    done, pending = asyncio.run(main())
    assert done.future.result() == {"text": "kept"}
    assert pending.future.result()["text"] == "ok:/avo-fake/live.wav"
    assert calls == [["/avo-fake/live.wav"]], "the resolved request must not be re-submitted"


def test_retry_method_with_every_request_done_makes_no_gpu_calls():
    calls = []

    def plan(payload):
        calls.append(list(payload["audio_paths"]))
        return _ok_result(payload["audio_paths"][0])

    async def main():
        engine = _retry_engine()
        engine._loop = asyncio.get_running_loop()
        reqs = [
            _new_request(f"/avo-fake/{i}.wav", asyncio.get_running_loop(), done_result={"text": f"kept{i}"})
            for i in range(3)
        ]
        await engine._retry_batch_one_by_one(reqs)
        return reqs

    reqs = asyncio.run(main())
    assert calls == []
    assert [r.future.result()["text"] for r in reqs] == ["kept0", "kept1", "kept2"]


def test_retry_method_solo_exception_books_only_that_request():
    poison = "/avo-fake/poison.wav"

    def plan(payload):
        path = payload["audio_paths"][0]
        if path == poison:
            return ValueError(NORMALIZE_ERROR)
        return _ok_result(path)

    async def main():
        engine = _retry_engine(plan)
        engine._loop = asyncio.get_running_loop()
        loop = asyncio.get_running_loop()
        r1 = _new_request("/avo-fake/a.wav", loop)
        r2 = _new_request(poison, loop)
        r3 = _new_request("/avo-fake/c.wav", loop)
        await engine._retry_batch_one_by_one([r1, r2, r3])
        return r1, r2, r3

    r1, r2, r3 = asyncio.run(main())
    assert r1.future.result()["text"] == "ok:/avo-fake/a.wav"
    assert NORMALIZE_ERROR in str(r2.future.exception())
    assert r3.future.result()["text"] == "ok:/avo-fake/c.wav"


def test_retry_method_cancel_resolves_outstanding_futures_then_raises():
    started = []

    def plan(payload):
        started.append(list(payload["audio_paths"]))
        return asyncio.get_running_loop().create_future()  # never resolves: the solo call hangs

    async def main():
        engine = _retry_engine()
        engine._loop = asyncio.get_running_loop()
        loop = asyncio.get_running_loop()
        r1 = _new_request("/avo-fake/a.wav", loop)
        r2 = _new_request("/avo-fake/b.wav", loop)
        task = asyncio.ensure_future(engine._retry_batch_one_by_one([r1, r2]))
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        return r1, r2

    r1, r2 = asyncio.run(main())
    for req in (r1, r2):
        assert req.future.done()
        assert isinstance(req.future.exception(), RuntimeError)
        assert "Batch cancelled during shutdown" in str(req.future.exception())


def test_retry_method_cancel_stops_further_solo_submissions():
    calls = []

    def plan(payload):
        calls.append(list(payload["audio_paths"]))
        return asyncio.get_running_loop().create_future()  # first solo hangs

    async def main():
        engine = _retry_engine(plan)
        engine._loop = asyncio.get_running_loop()
        loop = asyncio.get_running_loop()
        reqs = [_new_request(f"/avo-fake/{i}.wav", loop) for i in range(4)]
        task = asyncio.ensure_future(engine._retry_batch_one_by_one(reqs))
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        return reqs

    reqs = asyncio.run(main())
    assert len(calls) == 1, "cancellation must stop the remaining solo calls"
    assert all(req.future.done() for req in reqs)


def test_retry_method_non_list_solo_payload_passes_through_white_box():
    def plan(payload):
        return {"text": "bare", "timestamp": {}}

    async def main():
        engine = _retry_engine(plan)
        engine._loop = asyncio.get_running_loop()
        req = _new_request("/avo-fake/a.wav", asyncio.get_running_loop())
        await engine._retry_batch_one_by_one([req])
        return req

    req = asyncio.run(main())
    assert req.future.result() == {"text": "bare", "timestamp": {}}


# ---------------------------------------------------------------------------
# Metric surface and preserved counters.
# ---------------------------------------------------------------------------


def test_metrics_property_exposes_the_split_counter_at_zero():
    engine = BatchEngine(_make_gpu_worker(lambda payload: _ok_result(payload["audio_paths"][0])), max_batch_size=2)
    assert engine.metrics["degenerate_batch_split_retries"] == 0


def test_metrics_property_still_exposes_pending_requests():
    engine = BatchEngine(_make_gpu_worker(lambda payload: _ok_result(payload["audio_paths"][0])), max_batch_size=2)
    assert engine.metrics["pending_requests"] == 0


def test_healthy_grouped_run_keeps_batch_counters_untouched_by_split():
    paths = [f"/avo-fake/f{i}.wav" for i in range(4)]

    def plan(payload):
        return [_ok_result(p)[0] for p in payload["audio_paths"]]

    futs, engine = _run_engine(_make_gpu_worker(plan), paths)
    outcomes = _outcomes(futs)
    assert all(state == "ok" for state, _ in outcomes)
    assert engine.metrics["total_batches"] == 1
    assert engine.metrics["total_files"] == 4
    assert engine.metrics["degenerate_batch_split_retries"] == 0


def test_split_run_counts_one_batch_for_the_grouped_attempt():
    """Solo retries add files to no new batch counter: one flush, one batch."""

    def plan(payload):
        if len(payload["audio_paths"]) > 1:
            return ValueError(NORMALIZE_ERROR)
        path = payload["audio_paths"][0]
        if path.endswith("poison.wav"):
            return ValueError(NORMALIZE_ERROR)
        return _ok_result(path)

    paths = ["/avo-fake/a.wav", "/avo-fake/b.wav", "/avo-fake/poison.wav"]
    futs, engine = _run_engine(_make_gpu_worker(plan), paths)
    outcomes = _outcomes(futs)
    assert outcomes[2][0] == "error"
    assert engine.metrics["total_batches"] == 1
    assert engine.metrics["total_files"] == 3
    assert engine.metrics["degenerate_batch_split_retries"] == 1


def test_queue_full_rejection_counts_as_rejected_request():
    """The depth refusal books exactly one rejected request (its own metric)."""
    engine = BatchEngine(
        _make_gpu_worker(lambda payload: _ok_result(payload["audio_paths"][0])),
        max_batch_size=8,
        max_queue_depth=1,
        max_wait_seconds=30.0,
    )
    loop = asyncio.new_event_loop()

    async def run():
        await engine.start()
        blocker = PendingRequest(
            audio_path="/avo-fake/blocker.wav",
            timestamps=True,
            future=asyncio.get_running_loop().create_future(),
        )
        engine._pending.append(blocker)  # depth 1 of max_queue_depth 1
        try:
            await engine.submit("/avo-fake/b.wav", owns_file=False)
        except QueueFullError:
            pass
        await engine.stop()

    loop.run_until_complete(run())
    loop.close()
    assert engine.metrics["rejected_requests"] == 1


def test_pending_requests_metric_drains_to_zero_after_a_split_run():
    def plan(payload):
        if len(payload["audio_paths"]) > 1:
            return ValueError(NORMALIZE_ERROR)
        return _ok_result(payload["audio_paths"][0])

    futs, engine = _run_engine(_make_gpu_worker(plan), ["/avo-fake/a.wav", "/avo-fake/b.wav"])
    _outcomes(futs)
    assert engine.metrics["pending_requests"] == 0


# ---------------------------------------------------------------------------
# Callback accounting: which observer fires on which path.
# ---------------------------------------------------------------------------


def test_on_batch_complete_fires_once_per_healthy_grouped_flush():
    completions = []

    def plan(payload):
        return [_ok_result(p)[0] for p in payload["audio_paths"]]

    def on_complete(queue_durations, inference_seconds, batch_size):
        completions.append(batch_size)

    futs, _engine = _run_engine(
        _make_gpu_worker(plan), ["/avo-fake/a.wav", "/avo-fake/b.wav"], engine_kw={"on_batch_complete": on_complete}
    )
    assert all(state == "ok" for state, _ in _outcomes(futs))
    assert completions == [2]


def test_on_batch_complete_does_not_fire_for_a_failed_grouped_call():
    completions = []

    def plan(payload):
        if len(payload["audio_paths"]) > 1:
            return ValueError(NORMALIZE_ERROR)
        path = payload["audio_paths"][0]
        if path.endswith("poison.wav"):
            return ValueError(NORMALIZE_ERROR)
        return _ok_result(path)

    def on_complete(queue_durations, inference_seconds, batch_size):
        completions.append(batch_size)

    futs, _engine = _run_engine(
        _make_gpu_worker(plan),
        ["/avo-fake/a.wav", "/avo-fake/poison.wav"],
        engine_kw={"on_batch_complete": on_complete},
    )
    outcomes = _outcomes(futs)
    assert outcomes[0] == ("ok", _ok_result("/avo-fake/a.wav")[0])
    assert outcomes[1][0] == "error" and NORMALIZE_ERROR in str(outcomes[1][1])
    assert completions == [], "the failed grouped call must not report batch completion"


def test_on_queue_wait_fires_once_per_file_even_when_split():
    waits = []

    def plan(payload):
        if len(payload["audio_paths"]) > 1:
            return ValueError(NORMALIZE_ERROR)
        path = payload["audio_paths"][0]
        if path.endswith("poison.wav"):
            return ValueError(NORMALIZE_ERROR)
        return _ok_result(path)

    def on_wait(lane, seconds):
        waits.append(lane)

    futs, _engine = _run_engine(
        _make_gpu_worker(plan), ["/avo-fake/a.wav", "/avo-fake/poison.wav"], engine_kw={"on_queue_wait": on_wait}
    )
    outcomes = _outcomes(futs)
    assert outcomes[0] == ("ok", _ok_result("/avo-fake/a.wav")[0])
    assert outcomes[1][0] == "error"
    assert len(waits) == 2, "solo retries must not double-report queue waits"


def test_on_queue_wait_lanes_report_the_submitted_lane():
    waits = []

    def plan(payload):
        return [_ok_result(p)[0] for p in payload["audio_paths"]]

    def on_wait(lane, seconds):
        waits.append(lane)

    futs, _engine = _run_engine(
        _make_gpu_worker(plan),
        ["/avo-fake/a.wav", "/avo-fake/b.wav"],
        engine_kw={"on_queue_wait": on_wait},
        submit_kw={"lane": "live"},
    )
    assert all(state == "ok" for state, _ in _outcomes(futs))
    assert waits == ["live", "live"]


# ---------------------------------------------------------------------------
# Grouped-path preservation: the healthy contract stays byte-compatible.
# ---------------------------------------------------------------------------


def test_healthy_grouped_batch_uses_a_single_gpu_call():
    calls = []

    def plan(payload):
        calls.append(list(payload["audio_paths"]))
        return [_ok_result(p)[0] for p in payload["audio_paths"]]

    paths = [f"/avo-fake/f{i}.wav" for i in range(16)]
    futs, _engine = _run_engine(_make_gpu_worker(plan), paths)
    outcomes = _outcomes(futs)
    assert all(state == "ok" for state, _ in outcomes)
    assert [len(c) for c in calls] == [16]


def test_large_healthy_batch_grouped_failure_still_fails_all():
    def plan(payload):
        return ValueError("audio file is not a valid wav")

    paths = [f"/avo-fake/f{i}.wav" for i in range(16)]
    futs, engine = _run_engine(_make_gpu_worker(plan), paths)
    outcomes = _outcomes(futs)
    assert all(state == "error" for state, _ in outcomes)
    assert engine.metrics["degenerate_batch_split_retries"] == 0


def test_grouped_call_uses_the_first_request_timestamps_flag():
    payloads = []

    def plan(payload):
        payloads.append(dict(payload))
        return [_ok_result(p)[0] for p in payload["audio_paths"]]

    _futs, _engine = _run_engine(
        _make_gpu_worker(plan), ["/avo-fake/a.wav", "/avo-fake/b.wav"], submit_kw={"timestamps": False}
    )
    assert len(payloads) == 1
    assert payloads[0]["timestamps"] is False


def test_real_wav_healthy_batch_transcribes_through_the_grouped_path(tmp_path):
    healthy = [write_wav_16000hz(tmp_path, 0.4, "a.wav"), write_wav_16000hz(tmp_path, 0.4, "b.wav")]

    def plan(payload):
        return [_ok_result(p)[0] for p in payload["audio_paths"]]

    futs, engine = _run_engine(_make_gpu_worker(plan), healthy)
    outcomes = _outcomes(futs)
    assert all(state == "ok" for state, _ in outcomes)
    assert engine.metrics["total_files"] == 2


def test_real_wav_poison_split_measured_durations_reach_the_solo_call(tmp_path):
    poison = write_wav_16000hz(tmp_path, 0.0, "poison.wav")
    healthy = write_wav_16000hz(tmp_path, 0.5, "a.wav")
    solo_durations = []

    def plan(payload):
        if len(payload["audio_paths"]) > 1:
            return ValueError(NORMALIZE_ERROR)
        path = payload["audio_paths"][0]
        if path.endswith("poison.wav"):
            return ValueError(NORMALIZE_ERROR)
        solo_durations.extend(payload["durations"])
        return _ok_result(path)

    futs, _engine = _run_engine(_make_gpu_worker(plan), [healthy, poison])
    outcomes = _outcomes(futs)
    assert outcomes[0] == ("ok", _ok_result(healthy)[0])
    assert outcomes[1][0] == "error"
    assert len(solo_durations) == 1
    assert 0.0 < solo_durations[0] < 1.0


def test_two_member_batch_boundary_splits_like_the_large_one():
    """The minimum splittable batch size is exactly two files."""
    paths = ["/avo-fake/a.wav", "/avo-fake/poison.wav"]
    calls = []

    def plan(payload):
        calls.append(list(payload["audio_paths"]))
        if len(payload["audio_paths"]) > 1:
            return ValueError(NORMALIZE_ERROR)
        path = payload["audio_paths"][0]
        if path.endswith("poison.wav"):
            return ValueError(NORMALIZE_ERROR)
        return _ok_result(path)

    futs, engine = _run_engine(_make_gpu_worker(plan), paths)
    outcomes = _outcomes(futs)
    assert [len(c) for c in calls] == [2, 1, 1]
    assert outcomes[0][0] == "ok"
    assert outcomes[1][0] == "error"
    assert engine.metrics["degenerate_batch_split_retries"] == 1


def test_split_preserves_submit_return_shape_for_all_callers():
    """v1/v2 callers await submit() and cast the result to a per-file dict:
    after a split every surviving request must resolve to a dict."""

    def plan(payload):
        if len(payload["audio_paths"]) > 1:
            return ValueError(NORMALIZE_ERROR)
        return [{"text": "t", "timestamp": {"segment": []}}]

    paths = ["/avo-fake/a.wav", "/avo-fake/b.wav", "/avo-fake/c.wav"]
    futs, _ = _run_engine(_make_gpu_worker(plan), paths)
    for fut in futs:
        assert isinstance(fut.result(), dict)
        assert set(fut.result().keys()) == {"text", "timestamp"}


def test_engine_restart_after_a_split_run_starts_with_a_clean_counter():
    """A fresh engine instance never inherits the previous run's split count."""

    def plan(payload):
        if len(payload["audio_paths"]) > 1:
            return ValueError(NORMALIZE_ERROR)
        return _ok_result(payload["audio_paths"][0])

    futs, first = _run_engine(_make_gpu_worker(plan), ["/avo-fake/a.wav", "/avo-fake/b.wav"])
    _outcomes(futs)
    assert first.metrics["degenerate_batch_split_retries"] == 1
    second = BatchEngine(_make_gpu_worker(plan), max_batch_size=2)
    assert second.metrics["degenerate_batch_split_retries"] == 0


# ---------------------------------------------------------------------------
# owns_file cleanup: who deletes the audio under each path.
# ---------------------------------------------------------------------------


def test_split_with_owns_file_cleans_up_every_file(tmp_path):
    """The flush's finally owns cleanup; the split deletes nothing itself."""
    poison = write_wav_16000hz(tmp_path, 0.0, "poison.wav")
    healthy = write_wav_16000hz(tmp_path, 0.5, "a.wav")

    def plan(payload):
        if len(payload["audio_paths"]) > 1:
            return ValueError(NORMALIZE_ERROR)
        path = payload["audio_paths"][0]
        if path.endswith("poison.wav"):
            return ValueError(NORMALIZE_ERROR)
        return _ok_result(path)

    gpu = _make_gpu_worker(plan)
    engine = BatchEngine(gpu, max_batch_size=2, max_wait_seconds=0.01)
    loop = asyncio.new_event_loop()
    try:

        async def run():
            await engine.start()
            futs = [asyncio.ensure_future(engine.submit(p, owns_file=True)) for p in [healthy, poison]]
            await asyncio.gather(*futs, return_exceptions=True)
            await engine.stop()
            return futs

        futs = loop.run_until_complete(run())
    finally:
        loop.close()
    outcomes = _outcomes(futs)
    assert outcomes[0][0] == "ok"
    assert outcomes[1][0] == "error" and NORMALIZE_ERROR in str(outcomes[1][1])
    assert not os.path.exists(healthy), "healthy file must be unlinked after its solo success"
    assert not os.path.exists(poison), "poison file must be unlinked after its solo failure"


def test_split_with_owns_file_never_deletes_mid_retry(tmp_path):
    """Files survive until the flush's finally: the retry reads them live."""
    healthy = write_wav_16000hz(tmp_path, 0.5, "a.wav")
    poison = write_wav_16000hz(tmp_path, 0.0, "poison.wav")
    seen_at_solo_time = []

    def plan(payload):
        if len(payload["audio_paths"]) > 1:
            return ValueError(NORMALIZE_ERROR)
        path = payload["audio_paths"][0]
        seen_at_solo_time.append((path, os.path.exists(path)))
        if path.endswith("poison.wav"):
            return ValueError(NORMALIZE_ERROR)
        return _ok_result(path)

    gpu = _make_gpu_worker(plan)
    engine = BatchEngine(gpu, max_batch_size=2, max_wait_seconds=0.01)
    loop = asyncio.new_event_loop()
    try:

        async def run():
            await engine.start()
            futs = [asyncio.ensure_future(engine.submit(p, owns_file=True)) for p in [healthy, poison]]
            await asyncio.gather(*futs, return_exceptions=True)
            await engine.stop()

        loop.run_until_complete(run())
    finally:
        loop.close()
    solo_reads = [(p, exists) for p, exists in seen_at_solo_time if os.path.dirname(p) == str(tmp_path)]
    assert solo_reads, "the solo calls must observe the files"
    assert all(
        exists for _, exists in solo_reads
    ), "files must exist during solo retries (cleanup belongs to the flush finally)"


def test_grouped_owns_file_failure_still_cleans_up(tmp_path):
    """Control: the old all-fail path keeps unlinking under owns_file."""
    a = write_wav_16000hz(tmp_path, 0.5, "a.wav")
    b = write_wav_16000hz(tmp_path, 0.5, "b.wav")

    def plan(payload):
        return ValueError("audio file is not a valid wav")

    gpu = _make_gpu_worker(plan)
    engine = BatchEngine(gpu, max_batch_size=2, max_wait_seconds=0.01)
    loop = asyncio.new_event_loop()
    try:

        async def run():
            await engine.start()
            futs = [asyncio.ensure_future(engine.submit(p, owns_file=True)) for p in [a, b]]
            await asyncio.gather(*futs, return_exceptions=True)
            await engine.stop()
            return futs

        futs = loop.run_until_complete(run())
    finally:
        loop.close()
    outcomes = _outcomes(futs)
    assert all(state == "error" for state, _ in outcomes)
    assert not os.path.exists(a) and not os.path.exists(b)


# ---------------------------------------------------------------------------
# Cancel before flush: a cancelled waiter leaves nothing for the flush.
# ---------------------------------------------------------------------------


def test_cancelled_waiter_is_pruned_before_flush_and_never_splits():
    """A submit cancelled while queued is pruned; no poison batch forms."""
    calls = []

    def plan(payload):
        calls.append(list(payload["audio_paths"]))
        return [_ok_result(p)[0] for p in payload["audio_paths"]]

    gpu = _make_gpu_worker(plan)
    engine = BatchEngine(gpu, max_batch_size=4, max_wait_seconds=30.0)
    loop = asyncio.new_event_loop()
    try:

        async def run():
            await engine.start()
            task = asyncio.ensure_future(engine.submit("/avo-fake/cancelled.wav", owns_file=False))
            await asyncio.sleep(0.02)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            await engine.stop()

        loop.run_until_complete(run())
    finally:
        loop.close()
    assert engine.metrics["degenerate_batch_split_retries"] == 0
    for call in calls:
        assert "/avo-fake/cancelled.wav" not in call, "the cancelled request must not reach the GPU"


# ---------------------------------------------------------------------------
# Detector extras: spelling boundaries and message drift.
# ---------------------------------------------------------------------------


def test_detector_matches_lowercase_only_message_identity():
    # The match is case-sensitive substring identity: NeMo's exact casing.
    lowered = NORMALIZE_ERROR.replace("normalize_batch", "Normalize_Batch")
    assert not _is_degenerate_batch_normalization(ValueError(lowered))


def test_detector_matches_with_trailing_advice_present():
    full = NORMALIZE_ERROR + " Make sure your audio length has enough samples for a single feature."
    assert _is_degenerate_batch_normalization(ValueError(full))


def test_detector_ignores_the_error_type_and_trusts_the_message():
    # Even a bare Exception with the message matches: the identity is the text.
    assert _is_degenerate_batch_normalization(Exception(NORMALIZE_ERROR))


def test_detector_rejects_a_similar_but_different_op_name():
    other = NORMALIZE_ERROR.replace("normalize_batch with `per_feature`", "normalize_batch with `per_timestamp`")
    assert not _is_degenerate_batch_normalization(ValueError(other))


# ---------------------------------------------------------------------------
# Mixed faults inside one split run.
# ---------------------------------------------------------------------------


def test_split_survives_a_mixed_health_and_generic_fault_batch():
    """A batch with a generic-fault file and a poison file splits cleanly."""
    generic = "/avo-fake/generic.wav"
    poison = "/avo-fake/poison.wav"

    def plan(payload):
        if len(payload["audio_paths"]) > 1:
            return ValueError(NORMALIZE_ERROR)
        path = payload["audio_paths"][0]
        if path == generic:
            return ValueError("audio file is not a valid wav")
        if path == poison:
            return ValueError(NORMALIZE_ERROR)
        return _ok_result(path)

    paths = ["/avo-fake/a.wav", generic, poison, "/avo-fake/b.wav"]
    futs, engine = _run_engine(_make_gpu_worker(plan), paths)
    outcomes = _outcomes(futs)
    assert outcomes[0] == ("ok", _ok_result(paths[0])[0])
    assert outcomes[1][0] == "error" and "not a valid wav" in str(outcomes[1][1])
    assert outcomes[2][0] == "error" and NORMALIZE_ERROR in str(outcomes[2][1])
    assert outcomes[3] == ("ok", _ok_result(paths[3])[0])
    assert engine.metrics["degenerate_batch_split_retries"] == 1


def test_split_after_one_solo_oom_does_not_loop():
    """A solo OOM inside the split books that file's error and moves on."""
    oom = "/avo-fake/oom.wav"
    poison = "/avo-fake/poison.wav"

    def plan(payload):
        if len(payload["audio_paths"]) > 1:
            return ValueError(NORMALIZE_ERROR)
        path = payload["audio_paths"][0]
        if path == oom:
            return RuntimeError("CUDA out of memory")
        if path == poison:
            return ValueError(NORMALIZE_ERROR)
        return _ok_result(path)

    paths = [oom, "/avo-fake/a.wav", poison]
    futs, engine = _run_engine(_make_gpu_worker(plan), paths)
    outcomes = _outcomes(futs)
    assert outcomes[0][0] == "error" and "CUDA out of memory" in str(outcomes[0][1])
    assert outcomes[1] == ("ok", _ok_result(paths[1])[0])
    assert outcomes[2][0] == "error" and NORMALIZE_ERROR in str(outcomes[2][1])
    assert engine.metrics["degenerate_batch_split_retries"] == 1


def test_every_member_poison_batch_fails_all_individually_without_loop():
    """An all-poison batch splits once; every member fails with its own error."""
    paths = [f"/avo-fake/p{i}.wav" for i in range(3)]
    calls = []

    def plan(payload):
        calls.append(list(payload["audio_paths"]))
        if len(payload["audio_paths"]) > 1:
            return ValueError(NORMALIZE_ERROR)
        return ValueError(NORMALIZE_ERROR)

    futs, engine = _run_engine(_make_gpu_worker(plan), paths)
    outcomes = _outcomes(futs)
    assert all(state == "error" and NORMALIZE_ERROR in str(value) for state, value in outcomes)
    assert [len(c) for c in calls] == [3, 1, 1, 1]
    assert engine.metrics["degenerate_batch_split_retries"] == 1


def test_pressure_snapshot_unaffected_by_split_runs():
    """The pressure gauge reads the queue, not the retry path."""

    def plan(payload):
        if len(payload["audio_paths"]) > 1:
            return ValueError(NORMALIZE_ERROR)
        return _ok_result(payload["audio_paths"][0])

    futs, engine = _run_engine(_make_gpu_worker(plan), ["/avo-fake/a.wav", "/avo-fake/b.wav"])
    _outcomes(futs)
    snap = engine.pressure_snapshot()
    assert snap["pending_requests"] == 0
    assert snap["live_pending_requests"] == 0
    assert snap["backfill_pending_requests"] == 0


def test_split_metric_is_an_int_counter_not_a_string():
    engine = BatchEngine(_make_gpu_worker(lambda payload: _ok_result(payload["audio_paths"][0])), max_batch_size=2)
    value = engine.metrics["degenerate_batch_split_retries"]
    assert isinstance(value, int)


def test_split_after_starved_anchor_aging_still_completes():
    """The starvation anchor path produces a batch the split can still handle."""

    def plan(payload):
        if len(payload["audio_paths"]) > 1:
            return ValueError(NORMALIZE_ERROR)
        path = payload["audio_paths"][0]
        return _ok_result(path)

    gpu = _make_gpu_worker(plan)
    engine = BatchEngine(
        gpu,
        max_batch_size=4,
        max_wait_seconds=0.01,
        starvation_timeout_sec=0.0,  # everything is instantly "starved"
    )
    loop = asyncio.new_event_loop()
    try:

        async def run():
            await engine.start()
            futs = [
                asyncio.ensure_future(engine.submit(p, owns_file=False)) for p in ["/avo-fake/a.wav", "/avo-fake/b.wav"]
            ]
            results = await asyncio.gather(*futs, return_exceptions=True)
            await engine.stop()
            return results

        results = loop.run_until_complete(run())
    finally:
        loop.close()
    assert all(not isinstance(r, BaseException) for r in results)


def test_vram_selection_keeps_the_split_member_paths_intact():
    """The solo retry submits the same path the grouped call carried."""
    submitted_paths = []
    poison = "/avo-fake/poison.wav"
    healthy = ["/avo-fake/a.wav", "/avo-fake/b.wav"]

    def plan(payload):
        submitted_paths.append(list(payload["audio_paths"]))
        if len(payload["audio_paths"]) > 1:
            return ValueError(NORMALIZE_ERROR)
        path = payload["audio_paths"][0]
        if path == poison:
            return ValueError(NORMALIZE_ERROR)
        return _ok_result(path)

    gpu = _make_gpu_worker(plan)
    gpu.vram_info = {
        "total_mb": 80 * 1024,
        "baseline_mb": 6 * 1024,
        "attention_mode": "full",
        "auto_threshold_sec": 300,
    }
    futs, engine = _run_engine(gpu, healthy + [poison])
    outcomes = _outcomes(futs)
    assert outcomes[0][0] == "ok" and outcomes[1][0] == "ok"
    assert outcomes[2][0] == "error"
    # The poison path reached the GPU exactly twice: grouped + solo. The
    # healthy paths likewise grouped + solo.
    for path in healthy + [poison]:
        hits = [paths for paths in submitted_paths if path in paths]
        assert len(hits) == 2, f"{path} should appear in exactly grouped+solo calls, got {len(hits)}"
    assert engine.metrics["degenerate_batch_split_retries"] == 1


def test_flush_after_split_leaves_no_stranded_pending_requests():
    """A split run drains: nothing stays queued behind the retry."""

    def plan(payload):
        if len(payload["audio_paths"]) > 1:
            return ValueError(NORMALIZE_ERROR)
        path = payload["audio_paths"][0]
        if path.endswith("poison.wav"):
            return ValueError(NORMALIZE_ERROR)
        return _ok_result(path)

    futs, engine = _run_engine(_make_gpu_worker(plan), ["/avo-fake/a.wav", "/avo-fake/poison.wav", "/avo-fake/b.wav"])
    outcomes = _outcomes(futs)
    assert outcomes[0][0] == "ok" and outcomes[2][0] == "ok"
    assert outcomes[1][0] == "error"
    assert len(engine._pending) == 0


def test_live_lane_poison_split_reports_lane_waits_once():
    waits = []

    def plan(payload):
        if len(payload["audio_paths"]) > 1:
            return ValueError(NORMALIZE_ERROR)
        path = payload["audio_paths"][0]
        if path.endswith("poison.wav"):
            return ValueError(NORMALIZE_ERROR)
        return _ok_result(path)

    def on_wait(lane, seconds):
        waits.append(lane)

    futs, _engine = _run_engine(
        _make_gpu_worker(plan),
        ["/avo-fake/a.wav", "/avo-fake/poison.wav"],
        engine_kw={"on_queue_wait": on_wait},
        submit_kw={"lane": "live"},
    )
    outcomes = _outcomes(futs)
    assert outcomes[0][0] == "ok" and outcomes[1][0] == "error"
    assert waits == ["live", "live"]


def test_detector_and_metric_survive_engine_stop_start_cycle():
    """stop() does not reset the metric: the engine reports cumulative splits."""

    def plan(payload):
        if len(payload["audio_paths"]) > 1:
            return ValueError(NORMALIZE_ERROR)
        return _ok_result(payload["audio_paths"][0])

    gpu = _make_gpu_worker(plan)
    engine = BatchEngine(gpu, max_batch_size=2, max_wait_seconds=0.01)
    loop = asyncio.new_event_loop()
    try:

        async def run():
            await engine.start()
            futs = [
                asyncio.ensure_future(engine.submit(p, owns_file=False)) for p in ["/avo-fake/a.wav", "/avo-fake/b.wav"]
            ]
            await asyncio.gather(*futs, return_exceptions=True)
            await engine.stop()
            # A second start/stop on the same engine keeps the counter.
            await engine.start()
            await engine.stop()
            return None

        loop.run_until_complete(run())
    finally:
        loop.close()
    assert engine.metrics["degenerate_batch_split_retries"] == 1


def test_solo_retry_of_the_last_member_still_runs_after_earlier_successes():
    """Order independence inside the retry loop: successes never skip the tail."""

    def plan(payload):
        if len(payload["audio_paths"]) > 1:
            return ValueError(NORMALIZE_ERROR)
        path = payload["audio_paths"][0]
        if path.endswith("poison.wav"):
            return ValueError(NORMALIZE_ERROR)
        return _ok_result(path)

    paths = ["/avo-fake/a.wav", "/avo-fake/poison.wav", "/avo-fake/z-tail.wav"]
    futs, _ = _run_engine(_make_gpu_worker(plan), paths)
    outcomes = _outcomes(futs)
    assert outcomes[2] == (
        "ok",
        _ok_result(paths[2])[0],
    ), "the last member must still be retried after an earlier failure"
