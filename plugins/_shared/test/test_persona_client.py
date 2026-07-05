"""Tests for plugins/_shared/persona_client.py (T-002).

The persona_client.chat() coroutine POSTs to /v2/integrations/{app_id}/user/persona-chat
with an app API key and joins the SSE stream into a single string reply.

We exercise:
- Happy path: 200 + valid SSE stream -> full reply concatenated
- Multi-line `data:` frames: joined with newlines
- SSE comments (`: ping`) ignored
- Timeout: returns "" and logs an error (does not raise)
- 401 response: raises HTTPStatusError (caller decides whether to retry)
- 403 response: same
- Empty text -> empty stream body (still 200) -> returns ""
"""

import logging
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

# ---------------------------------------------------------------------------
# Import the module under test. The plugin lives outside the backend test tree
# so we add plugins/_shared to sys.path here, before the import.
# ---------------------------------------------------------------------------
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_SHARED = os.path.abspath(os.path.join(_HERE, ".."))
if _SHARED not in sys.path:
    sys.path.insert(0, _SHARED)

import persona_client  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _sse_response(chunks: list[str], status_code: int = 200) -> httpx.Response:
    """Build an httpx.Response whose stream() yields the given SSE bytes."""
    body = ""
    for c in chunks:
        # Each chunk becomes `data: <chunk>\\n\\n` (the SSE framing the backend uses)
        body += f"data: {c}\n\n"
    request = httpx.Request("POST", "https://api.omi.me/v2/integrations/app-1/user/persona-chat")
    return httpx.Response(
        status_code=status_code,
        headers={"content-type": "text/event-stream"},
        content=body.encode("utf-8"),
        request=request,
    )


def _mock_async_client_post(response: httpx.Response | Exception):
    """Return a configured AsyncMock httpx.AsyncClient whose .post -> response."""
    client = AsyncMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)
    if isinstance(response, Exception):
        client.post = AsyncMock(side_effect=response)
    else:
        client.post = AsyncMock(return_value=response)

    # stream() on the response yields the body bytes
    async def _stream():
        yield response.content

    response.stream = MagicMock(return_value=_stream()) if not hasattr(response, "stream") else response.stream
    return client


# ---------------------------------------------------------------------------
# 1. Happy path
# ---------------------------------------------------------------------------
class TestChatSuccess:
    @pytest.mark.asyncio
    async def test_returns_concatenated_reply(self):
        resp = _sse_response(["Hello", " ", "world"])
        client = _mock_async_client_post(resp)

        with patch("persona_client.httpx.AsyncClient", return_value=client):
            reply = await persona_client.chat(
                app_id="app-1",
                api_key="omi_dev_test",
                omi_base="https://api.omi.me",
                text="hi",
                uid="u-1",
            )

        assert reply == "Hello world"

    @pytest.mark.asyncio
    async def test_sends_bearer_auth_header(self):
        resp = _sse_response(["ok"])
        client = _mock_async_client_post(resp)

        with patch("persona_client.httpx.AsyncClient", return_value=client):
            await persona_client.chat(
                app_id="app-1",
                api_key="omi_dev_test",
                omi_base="https://api.omi.me",
                text="hi",
                uid="u-1",
            )

        client.post.assert_awaited_once()
        call_kwargs = client.post.await_args.kwargs
        assert call_kwargs["headers"]["Authorization"] == "Bearer omi_dev_test"

    @pytest.mark.asyncio
    async def test_targets_correct_url(self):
        resp = _sse_response(["ok"])
        client = _mock_async_client_post(resp)

        with patch("persona_client.httpx.AsyncClient", return_value=client):
            await persona_client.chat(
                app_id="app-abc",
                api_key="k",
                omi_base="https://api.omi.me",
                text="hi",
                uid="u-1",
            )

        url = client.post.await_args.args[0]
        assert url == "https://api.omi.me/v2/integrations/app-abc/user/persona-chat"

    @pytest.mark.asyncio
    async def test_sends_uid_as_query_param(self):
        """Contract: backend extracts `uid` from query string via FastAPI's path
        declaration. The plugin MUST send it as a query param (not body) so
        FastAPI can route it.

        This is the contract that broke v0.1 in production — backend expected
        ?uid=... but client only sent a JSON body, so every request got 422.
        """
        resp = _sse_response(["ok"])
        client = _mock_async_client_post(resp)

        with patch("persona_client.httpx.AsyncClient", return_value=client):
            await persona_client.chat(
                app_id="app-1",
                api_key="k",
                omi_base="https://api.omi.me",
                text="hi",
                uid="u-abc",
            )

        call_kwargs = client.post.await_args.kwargs
        assert call_kwargs["params"] == {
            "uid": "u-abc"
        }, f"uid must be sent as a query param; got params={call_kwargs.get('params')}"

    @pytest.mark.asyncio
    async def test_sends_text_in_json_body(self):
        resp = _sse_response(["ok"])
        client = _mock_async_client_post(resp)

        with patch("persona_client.httpx.AsyncClient", return_value=client):
            await persona_client.chat(
                app_id="app-1",
                api_key="k",
                omi_base="https://api.omi.me",
                text="what's the weather?",
                uid="u-1",
            )

        call_kwargs = client.post.await_args.kwargs
        assert call_kwargs["json"] == {"text": "what's the weather?"}


# ---------------------------------------------------------------------------
# 2. SSE edge cases
# ---------------------------------------------------------------------------
class TestSseParsing:
    @pytest.mark.asyncio
    async def test_sse_comment_lines_are_ignored(self):
        # Body has a comment line (`: ping`), an empty `data:` event, and one
        # real data event. The comment and empty data should not appear in the
        # joined reply.
        body = ": keepalive ping\n\ndata:\n\ndata: hello world\n\n"
        request = httpx.Request("POST", "https://api.omi.me/v2/integrations/app-1/user/persona-chat")
        resp = httpx.Response(
            status_code=200,
            headers={"content-type": "text/event-stream"},
            content=body.encode("utf-8"),
            request=request,
        )
        client = _mock_async_client_post(resp)

        with patch("persona_client.httpx.AsyncClient", return_value=client):
            reply = await persona_client.chat(
                app_id="app-1",
                api_key="k",
                omi_base="https://api.omi.me",
                text="hi",
                uid="u-1",
            )
        assert reply == "hello world"

    @pytest.mark.asyncio
    async def test_blank_lines_in_sse_data_are_preserved(self):
        # A single SSE event whose data spans multiple lines. Per the SSE spec
        # (https://html.spec.whatwg.org/multipage/server-sent-events.html), the
        # event data is the concatenation of all `data:` lines for that event,
        # separated by newlines. So `data: line one\ndata: line two\n\n` is one
        # event with data = "line one\nline two".
        body = "data: line one\ndata: line two\n\n"
        request = httpx.Request("POST", "https://api.omi.me/v2/integrations/app-1/user/persona-chat")
        resp = httpx.Response(
            status_code=200,
            headers={"content-type": "text/event-stream"},
            content=body.encode("utf-8"),
            request=request,
        )
        client = _mock_async_client_post(resp)

        with patch("persona_client.httpx.AsyncClient", return_value=client):
            reply = await persona_client.chat(
                app_id="app-1",
                api_key="k",
                omi_base="https://api.omi.me",
                text="hi",
                uid="u-1",
            )
        assert reply == "line one\nline two"

    @pytest.mark.asyncio
    async def test_empty_stream_returns_empty_string(self):
        request = httpx.Request("POST", "https://api.omi.me/v2/integrations/app-1/user/persona-chat")
        resp = httpx.Response(
            status_code=200,
            headers={"content-type": "text/event-stream"},
            content=b"",
            request=request,
        )
        client = _mock_async_client_post(resp)

        with patch("persona_client.httpx.AsyncClient", return_value=client):
            reply = await persona_client.chat(
                app_id="app-1",
                api_key="k",
                omi_base="https://api.omi.me",
                text="hi",
                uid="u-1",
            )
        assert reply == ""


# ---------------------------------------------------------------------------
# 3. Error paths
# ---------------------------------------------------------------------------
class TestChatErrors:
    @pytest.mark.asyncio
    async def test_401_raises(self):
        request = httpx.Request("POST", "https://api.omi.me/v2/integrations/app-1/user/persona-chat")
        resp = httpx.Response(status_code=401, content=b"", request=request)
        client = _mock_async_client_post(resp)

        with patch("persona_client.httpx.AsyncClient", return_value=client):
            with pytest.raises(httpx.HTTPStatusError):
                await persona_client.chat(
                    app_id="app-1",
                    api_key="bad",
                    omi_base="https://api.omi.me",
                    text="hi",
                    uid="u-1",
                )

    @pytest.mark.asyncio
    async def test_403_raises(self):
        request = httpx.Request("POST", "https://api.omi.me/v2/integrations/app-1/user/persona-chat")
        resp = httpx.Response(status_code=403, content=b"", request=request)
        client = _mock_async_client_post(resp)

        with patch("persona_client.httpx.AsyncClient", return_value=client):
            with pytest.raises(httpx.HTTPStatusError):
                await persona_client.chat(
                    app_id="app-1",
                    api_key="bad",
                    omi_base="https://api.omi.me",
                    text="hi",
                    uid="u-1",
                )

    @pytest.mark.asyncio
    async def test_500_raises(self):
        request = httpx.Request("POST", "https://api.omi.me/v2/integrations/app-1/user/persona-chat")
        resp = httpx.Response(status_code=500, content=b"", request=request)
        client = _mock_async_client_post(resp)

        with patch("persona_client.httpx.AsyncClient", return_value=client):
            with pytest.raises(httpx.HTTPStatusError):
                await persona_client.chat(
                    app_id="app-1",
                    api_key="k",
                    omi_base="https://api.omi.me",
                    text="hi",
                    uid="u-1",
                )

    @pytest.mark.asyncio
    async def test_timeout_returns_empty_and_logs(self, caplog):
        client = AsyncMock()
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=None)
        client.post = AsyncMock(side_effect=httpx.TimeoutException("timed out", request=MagicMock()))

        with patch("persona_client.httpx.AsyncClient", return_value=client):
            with caplog.at_level(logging.ERROR, logger="persona_client"):
                reply = await persona_client.chat(
                    app_id="app-1",
                    api_key="k",
                    omi_base="https://api.omi.me",
                    text="hi",
                    uid="u-1",
                    timeout_seconds=0.1,
                )

        assert reply == ""
        assert any("timeout" in r.message.lower() or "timed out" in r.message.lower() for r in caplog.records)

    @pytest.mark.asyncio
    async def test_connect_error_returns_empty_and_logs(self, caplog):
        client = AsyncMock()
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=None)
        client.post = AsyncMock(side_effect=httpx.ConnectError("boom", request=MagicMock()))

        with patch("persona_client.httpx.AsyncClient", return_value=client):
            with caplog.at_level(logging.ERROR, logger="persona_client"):
                reply = await persona_client.chat(
                    app_id="app-1",
                    api_key="k",
                    omi_base="https://api.omi.me",
                    text="hi",
                    uid="u-1",
                )

        assert reply == ""

    @pytest.mark.asyncio
    async def test_wall_clock_timeout_caps_long_sse_stream(self, caplog):
        """P1.4 fix: httpx.Timeout sets per-phase timeouts, not a wall-clock cap.
        For SSE the read timeout resets per chunk, so the call can run far longer
        than timeout_seconds without asyncio.wait_for. Verify that the wall-clock
        cap fires even when individual chunks arrive within their own per-phase
        timeout.
        """
        import asyncio
        import httpx
        from httpx_sse import EventSource

        # Build a fake SSE response whose aiter_sse yields chunks slowly.
        # Without asyncio.wait_for wrapping the stream consume, this would
        # run for ~1s. With the wrap + a 0.1s wall-clock cap, it should be
        # cancelled and return "".
        request = httpx.Request("POST", "https://api.omi.me/v2/integrations/app-1/user/persona-chat")
        resp = httpx.Response(200, content=b"data: chunk1\n\n", request=request)

        # Yield one chunk, then sleep past the wall-clock cap.
        async def slow_aiter_sse(self):
            yield type("SSEEvent", (), {"data": "chunk1"})()
            await asyncio.sleep(0.5)
            yield type("SSEEvent", (), {"data": "chunk2"})()

        client = AsyncMock()
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=None)
        client.post = AsyncMock(return_value=resp)

        with patch("persona_client.httpx.AsyncClient", return_value=client):
            with patch.object(EventSource, "aiter_sse", slow_aiter_sse):
                with caplog.at_level(logging.ERROR, logger="persona_client"):
                    reply = await persona_client.chat(
                        app_id="app-1",
                        api_key="k",
                        omi_base="https://api.omi.me",
                        text="hi",
                        uid="u-1",
                        timeout_seconds=0.1,
                    )

        # The wall-clock cap should have fired \u2014 reply is "" (timeout path).
        assert reply == ""
        # Should have logged the timeout.
        assert any(
            "timeout" in r.message.lower() for r in caplog.records
        ), f"Expected timeout log, got: {[r.message for r in caplog.records]}"

    @pytest.mark.asyncio
    async def test_split_lines_preserves_trailing_blank(self):
        """P2.9 fix: _split_lines must preserve trailing blank lines (splitlines
        silently drops them, contradicting the docstring)."""
        # "a\n\n" splits into ["a", "", ""] and rejoins as "a\n\n" — both
        # newlines preserved (splitlines would silently drop the trailing two).
        assert persona_client._split_lines("a\n\n") == "a\n\n"
        # Multiple trailing newlines all preserved.
        assert persona_client._split_lines("a\n\n\n") == "a\n\n\n"
        # Single newline in the middle is a no-op.
        assert persona_client._split_lines("a\nb") == "a\nb"
        # No newline is a no-op.
        assert persona_client._split_lines("hello") == "hello"
