import asyncio
import sys
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import pytest

from omi.stt import create_transcriber
from omi.transcribe import transcribe


@pytest.mark.parametrize(
    "options,expected", [({}, "en-US"), ({"language": "es"}, "es")]
)
def test_deepgram_connection_language(monkeypatch, options, expected):
    calls = []

    def connect(url, **kwargs):
        calls.append((url, kwargs))
        raise asyncio.CancelledError()

    monkeypatch.setitem(sys.modules, "websockets", SimpleNamespace(connect=connect))
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(transcribe(asyncio.Queue(), "synthetic-key", **options))
    assert len(calls) == 1
    url, kwargs = calls[0]
    assert parse_qs(urlsplit(url).query)["language"] == [expected]
    assert kwargs["additional_headers"] == {"Authorization": "Token synthetic-key"}


def test_deepgram_language_cannot_add_query_parameters(monkeypatch):
    calls = []

    def connect(url, **kwargs):
        calls.append(url)
        raise asyncio.CancelledError()

    monkeypatch.setitem(sys.modules, "websockets", SimpleNamespace(connect=connect))
    engine = create_transcriber(
        "deepgram", api_key="synthetic-key", language="es&channels=2"
    )
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(engine.run(asyncio.Queue()))
    query = parse_qs(urlsplit(calls[0]).query)
    assert query["language"] == ["es&channels=2"]
    assert query["channels"] == ["1"]
