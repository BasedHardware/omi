"""Hermetic coverage for the on-prem whisper STT service (backend/whisper/main.py).

The module imports faster_whisper and loads a CUDA model at import; we stub the library and set
WHISPER_SKIP_MODEL_LOAD=1 so the route, upload bound, language mapping, and admission control can be
exercised without a GPU or the real model.
"""

import asyncio
import importlib.util
import sys
import types
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[2]


def _load_main(monkeypatch, *, max_upload=1024, max_concurrency=2):
    # Stub faster_whisper so the top-level import succeeds without the real package/GPU.
    fake_fw = types.ModuleType("faster_whisper")
    fake_fw.WhisperModel = object
    monkeypatch.setitem(sys.modules, "faster_whisper", fake_fw)
    monkeypatch.setenv("WHISPER_SKIP_MODEL_LOAD", "1")
    monkeypatch.setenv("WHISPER_MAX_UPLOAD_BYTES", str(max_upload))
    monkeypatch.setenv("WHISPER_MAX_CONCURRENCY", str(max_concurrency))
    spec = importlib.util.spec_from_file_location(
        "whisper_main_under_test", BACKEND_DIR / "whisper" / "main.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _FakeUpload:
    """Minimal UploadFile stand-in: yields `data` in `chunk`-sized reads then EOF (b'')."""

    def __init__(self, data: bytes, chunk: int = 512):
        self._buf = data
        self._pos = 0
        self._chunk = chunk

    async def read(self, n: int = -1) -> bytes:
        take = self._chunk if n is None or n < 0 else n
        piece = self._buf[self._pos : self._pos + take]
        self._pos += len(piece)
        return piece


class _Seg:
    def __init__(self, text, start, end):
        self.text = text
        self.start = start
        self.end = end


class _Info:
    def __init__(self, language):
        self.language = language


class _FakeModel:
    def __init__(self, segments, language):
        self._segments = segments
        self._language = language
        self.calls = []

    def transcribe(self, audio, language=None, beam_size=None, vad_filter=None):
        self.calls.append({"language": language, "beam_size": beam_size, "vad_filter": vad_filter})
        return iter(self._segments), _Info(self._language)


def test_read_bounded_rejects_oversize_with_413(monkeypatch):
    main = _load_main(monkeypatch, max_upload=1024)
    with pytest.raises(main.HTTPException) as exc:
        asyncio.run(main._read_bounded(_FakeUpload(b"x" * 2048)))
    assert exc.value.status_code == 413


def test_read_bounded_returns_full_body_within_limit(monkeypatch):
    main = _load_main(monkeypatch, max_upload=4096)
    assert asyncio.run(main._read_bounded(_FakeUpload(b"abc" * 100))) == b"abc" * 100


def test_transcribe_output_shape(monkeypatch):
    main = _load_main(monkeypatch)
    main._model = _FakeModel([_Seg(" hello", 0.0, 1.0), _Seg(" world", 1.0, 2.0)], "en")
    assert main._transcribe(b"audio", None) == {
        "text": "hello world",
        "segments": [
            {"text": " hello", "start": 0.0, "end": 1.0},
            {"text": " world", "start": 1.0, "end": 2.0},
        ],
        "language": "en",
    }


@pytest.mark.parametrize(
    "language,expected_detect",
    [(None, None), ("", None), ("auto", None), ("multi", None), ("MULTI", None), ("it", "it")],
)
def test_route_language_mapping(monkeypatch, language, expected_detect):
    main = _load_main(monkeypatch)
    model = _FakeModel([_Seg(" ciao", 0.0, 1.0)], "it")
    main._model = model
    out = asyncio.run(main.transcribe(file=_FakeUpload(b"audio"), language=language))
    assert out["text"] == "ciao"
    assert model.calls[0]["language"] == expected_detect


def test_route_rejects_when_all_inference_slots_busy_with_503(monkeypatch):
    main = _load_main(monkeypatch, max_concurrency=1)
    main._model = _FakeModel([_Seg(" hi", 0.0, 1.0)], "en")

    async def _scenario():
        # Occupy the single inference slot, then a concurrent request must be rejected with 503
        # rather than queueing unbounded GPU work.
        await main._inference_slots.acquire()
        with pytest.raises(main.HTTPException) as exc:
            await main.transcribe(file=_FakeUpload(b"audio"), language="en")
        assert exc.value.status_code == 503
        main._inference_slots.release()

    asyncio.run(_scenario())


def test_route_releases_slot_after_success(monkeypatch):
    main = _load_main(monkeypatch, max_concurrency=1)
    main._model = _FakeModel([_Seg(" hi", 0.0, 1.0)], "en")

    async def _scenario():
        # Two sequential requests both succeed: the slot must be released after the first.
        for _ in range(2):
            out = await main.transcribe(file=_FakeUpload(b"audio"), language="en")
            assert out["text"] == "hi"
        assert not main._inference_slots.locked()

    asyncio.run(_scenario())


def test_oversize_middleware_rejects_by_content_length(monkeypatch):
    main = _load_main(monkeypatch, max_upload=1024)

    class _Req:
        method = "POST"
        url = types.SimpleNamespace(path="/v1/audio/transcriptions")
        headers = {"content-length": "2048"}

    async def _call_next(_req):
        raise AssertionError("body must not be parsed/spooled when Content-Length exceeds the limit")

    resp = asyncio.run(main._reject_oversize_before_spooling(_Req(), _call_next))
    assert resp.status_code == 413


def test_oversize_middleware_passes_through_within_limit(monkeypatch):
    main = _load_main(monkeypatch, max_upload=4096)
    sentinel = object()

    class _Req:
        method = "POST"
        url = types.SimpleNamespace(path="/v1/audio/transcriptions")
        headers = {"content-length": "100"}

    async def _call_next(_req):
        return sentinel

    assert asyncio.run(main._reject_oversize_before_spooling(_Req(), _call_next)) is sentinel
