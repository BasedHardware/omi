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


def _drain_app(consumed):
    """A stand-in for the multipart parser: pulls the whole body via receive, recording bytes seen."""

    async def app(scope, receive, send):
        while True:
            message = await receive()
            if message.get("type") == "http.request":
                consumed[0] += len(message.get("body", b""))
                if not message.get("more_body"):
                    break
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    return app


def _receiver(chunks):
    idx = [0]

    async def receive():
        i = idx[0]
        idx[0] += 1
        if i < len(chunks):
            return chunks[i]
        return {"type": "http.request", "body": b"", "more_body": False}

    return receive


def test_asgi_limit_rejects_oversize_content_length_before_app(monkeypatch):
    main = _load_main(monkeypatch, max_upload=1024)

    async def _unreachable(scope, receive, send):
        raise AssertionError("body must not reach the app / parser when Content-Length exceeds the limit")

    mw = main.LimitUploadSizeMiddleware(_unreachable, max_bytes=1024)
    scope = {"type": "http", "method": "POST", "path": "/v1/audio/transcriptions",
             "headers": [(b"content-length", b"2048")]}
    sent = []

    async def send(message):
        sent.append(message)

    asyncio.run(mw(scope, _receiver([]), send))
    assert sent[0]["type"] == "http.response.start" and sent[0]["status"] == 413


def test_asgi_limit_aborts_chunked_stream_before_full_spool(monkeypatch):
    # The key fix: an undeclared-length (chunked) body is bounded as it streams, aborting before the
    # parser can spool it all. Content-Length is absent here.
    main = _load_main(monkeypatch, max_upload=1024)
    consumed = [0]
    mw = main.LimitUploadSizeMiddleware(_drain_app(consumed), max_bytes=1024)
    chunks = [{"type": "http.request", "body": b"x" * 512, "more_body": True} for _ in range(6)]  # 3072 total
    sent = []

    async def send(message):
        sent.append(message)

    scope = {"type": "http", "method": "POST", "path": "/v1/audio/transcriptions", "headers": []}
    asyncio.run(mw(scope, _receiver(chunks), send))
    assert sent[0]["status"] == 413
    # The parser never saw the whole 3072-byte body: it was aborted once the running total passed 1024.
    assert consumed[0] <= 1024 + 512


def test_asgi_limit_returns_clean_413_when_inner_app_reports_its_own_error(monkeypatch):
    # Real stack: the multipart parser catches the aborted read and sends its own 4xx. The middleware
    # must swallow that and return exactly one clean 413.
    main = _load_main(monkeypatch, max_upload=1024)

    async def app_reports_400(scope, receive, send):
        try:
            while True:
                message = await receive()
                if message.get("type") == "http.request" and not message.get("more_body"):
                    break
        except Exception:
            await send({"type": "http.response.start", "status": 400, "headers": []})
            await send({"type": "http.response.body", "body": b"bad multipart"})
            return
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    mw = main.LimitUploadSizeMiddleware(app_reports_400, max_bytes=1024)
    chunks = [{"type": "http.request", "body": b"x" * 512, "more_body": True} for _ in range(6)]
    sent = []

    async def send(message):
        sent.append(message)

    scope = {"type": "http", "method": "POST", "path": "/v1/audio/transcriptions", "headers": []}
    asyncio.run(mw(scope, _receiver(chunks), send))
    starts = [m for m in sent if m["type"] == "http.response.start"]
    assert len(starts) == 1 and starts[0]["status"] == 413


def test_asgi_limit_passes_through_within_limit(monkeypatch):
    main = _load_main(monkeypatch, max_upload=4096)
    consumed = [0]
    mw = main.LimitUploadSizeMiddleware(_drain_app(consumed), max_bytes=4096)
    chunks = [{"type": "http.request", "body": b"small", "more_body": False}]
    sent = []

    async def send(message):
        sent.append(message)

    scope = {"type": "http", "method": "POST", "path": "/v1/audio/transcriptions", "headers": []}
    asyncio.run(mw(scope, _receiver(chunks), send))
    assert sent[0]["status"] == 200
    assert consumed[0] == 5


def test_asgi_limit_ignores_non_transcription_paths(monkeypatch):
    main = _load_main(monkeypatch, max_upload=8)
    reached = [False]

    async def app(scope, receive, send):
        reached[0] = True
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    mw = main.LimitUploadSizeMiddleware(app, max_bytes=8)
    # A GET to /health with a large declared length must pass through untouched.
    scope = {"type": "http", "method": "GET", "path": "/health", "headers": [(b"content-length", b"9999")]}

    async def send(_message):
        pass

    asyncio.run(mw(scope, _receiver([]), send))
    assert reached[0] is True
