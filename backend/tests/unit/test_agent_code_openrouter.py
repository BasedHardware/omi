"""Unit tests for the OpenRouter SSE proxy (utils.agent_code.openrouter).

Strategy: monkeypatch httpx.AsyncClient so no real network calls are made.
We simulate the async-context-manager / async-generator stack that the real
httpx streaming API presents, then drive proxy_chat_completion through an
async for loop and assert on the collected chunks and the populated StreamUsage.
"""

import json
import os
import sys
import types
from unittest.mock import AsyncMock, MagicMock

import pytest

# ---------------------------------------------------------------------------
# Minimal env + stubs (mirror the pattern used by test_agent_code_grant.py)
# ---------------------------------------------------------------------------

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)


# ---------------------------------------------------------------------------
# Helpers — fake SSE stream
# ---------------------------------------------------------------------------

def _sse_lines(*events: dict | str) -> list[str]:
    """Return a list of raw SSE lines as proxy_chat_completion would receive them."""
    lines: list[str] = []
    for ev in events:
        if isinstance(ev, str):
            lines.append(ev)
        else:
            lines.append("data: " + json.dumps(ev))
    lines.append("data: [DONE]")
    return lines


def _make_mock_client(lines: list[str]):
    """Build a mock httpx.AsyncClient whose stream() context manager yields the given lines."""

    # The response object: resp.aiter_lines() is an async generator.
    async def _aiter_lines():
        for line in lines:
            yield line

    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.aiter_lines = _aiter_lines

    # client.stream() is an async context manager that yields mock_resp.
    class _StreamCM:
        async def __aenter__(self):
            return mock_resp

        async def __aexit__(self, *_):
            pass

    mock_client = MagicMock()
    mock_client.stream = MagicMock(return_value=_StreamCM())

    # AsyncClient() itself is an async context manager.
    class _ClientCM:
        async def __aenter__(self):
            return mock_client

        async def __aexit__(self, *_):
            pass

    return _ClientCM(), mock_client


# ---------------------------------------------------------------------------
# Import the module under test after env setup.
# ---------------------------------------------------------------------------

from utils.agent_code.openrouter import StreamUsage, proxy_chat_completion  # noqa: E402


# ---------------------------------------------------------------------------
# Helper — drive the async generator to completion.
# ---------------------------------------------------------------------------

async def _collect(monkeypatch, lines: list[str], payload: dict | None = None) -> tuple[list[bytes], StreamUsage]:
    """Run proxy_chat_completion and return (chunks, usage)."""
    client_cm, _mock_client = _make_mock_client(lines)

    import httpx

    monkeypatch.setattr(httpx, "AsyncClient", MagicMock(return_value=client_cm))

    usage = StreamUsage()
    payload = payload or {"model": "test-model", "messages": []}
    chunks: list[bytes] = []
    async for chunk in proxy_chat_completion(payload, usage):
        chunks.append(chunk)
    return chunks, usage


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_all_chunks_forwarded_verbatim(monkeypatch):
    """Every SSE line must be yielded back as bytes (plus newline)."""
    chunk1 = {"id": "c1", "model": "qwen/qwen3-235b-a22b", "choices": [{"delta": {"content": "Hello"}}]}
    chunk2 = {"id": "c2", "model": "qwen/qwen3-235b-a22b", "choices": [{"delta": {"content": " world"}}]}
    lines = _sse_lines(chunk1, chunk2)

    chunks, _ = await _collect(monkeypatch, lines)

    # Each non-empty line → (line + "\n").encode(); [DONE] forwarded the same way.
    data_lines = [c for c in chunks if c.strip()]
    assert any(b"Hello" in c for c in data_lines)
    assert any(b"world" in c for c in data_lines)
    assert any(b"[DONE]" in c for c in data_lines)


@pytest.mark.asyncio
async def test_usage_populated_from_final_chunk(monkeypatch):
    """usage.input_tokens and output_tokens must reflect prompt_tokens / completion_tokens."""
    final_chunk = {
        "id": "c3",
        "model": "qwen/qwen3-235b-a22b",
        "choices": [],
        "usage": {"prompt_tokens": 1234, "completion_tokens": 567},
    }
    lines = _sse_lines(final_chunk)

    _, usage = await _collect(monkeypatch, lines)

    assert usage.input_tokens == 1234
    assert usage.output_tokens == 567


@pytest.mark.asyncio
async def test_model_set_from_chunk(monkeypatch):
    """usage.model is populated from the first chunk that carries a model field."""
    chunk = {"id": "c4", "model": "qwen/qwen3-235b-a22b", "choices": []}
    lines = _sse_lines(chunk)

    _, usage = await _collect(monkeypatch, lines)

    assert usage.model == "qwen/qwen3-235b-a22b"


@pytest.mark.asyncio
async def test_done_line_does_not_raise(monkeypatch):
    """[DONE] sentinel must be forwarded without triggering a JSONDecodeError."""
    lines = ["data: [DONE]"]

    # Should not raise.
    chunks, _ = await _collect(monkeypatch, lines)
    assert any(b"[DONE]" in c for c in chunks)


@pytest.mark.asyncio
async def test_multiple_chunks_accumulate_usage(monkeypatch):
    """Only the chunk that contains usage matters; earlier chunks' usage does not linger."""
    early = {"id": "c5", "model": "m", "choices": [], "usage": {"prompt_tokens": 1, "completion_tokens": 1}}
    final = {"id": "c6", "model": "m", "choices": [], "usage": {"prompt_tokens": 1234, "completion_tokens": 567}}
    lines = _sse_lines(early, final)

    _, usage = await _collect(monkeypatch, lines)

    # Final chunk overwrites the earlier one.
    assert usage.input_tokens == 1234
    assert usage.output_tokens == 567


@pytest.mark.asyncio
async def test_missing_api_key_raises_runtime_error(monkeypatch):
    """proxy_chat_completion must raise RuntimeError when neither key env var is set."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    usage = StreamUsage()
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        # The generator is lazy; we must start iterating to trigger the check.
        async for _ in proxy_chat_completion({}, usage):
            pass


@pytest.mark.asyncio
async def test_empty_line_yields_newline_byte(monkeypatch):
    """Empty SSE lines (keepalive) are forwarded as b'\\n'."""
    lines = ["", "data: [DONE]"]
    chunks, _ = await _collect(monkeypatch, lines)
    assert b"\n" in chunks
