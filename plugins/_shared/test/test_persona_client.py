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
    """Return a configured AsyncMock httpx.AsyncClient.

    Newer persona_client (after the cubic P1 timeout fix) uses
    `client.stream("POST", ...)` as an async context manager rather than
    `client.post(...)` eagerly. Mock both paths so tests work either way:
    - `client.post(...)` returns the response (legacy behavior).
    - `client.stream(...)` returns an async context manager whose
      `__aenter__` yields the response. The response object must expose
      `aiter_bytes()` for the SSE EventSource consumer.

    For error cases we raise from `client.stream` so the context manager
    `__aenter__` propagates the exception (httpx.HTTPStatusError on 4xx/5xx
    is raised by `response.raise_for_status()` inside the `async with`).
    """
    client = AsyncMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)

    # Build a real async-iterator over the body lines so the EventSource
    # consumer (which calls `response.aiter_lines()`) can drive aiter_sse()
    # without ad-hoc mocking. Note: aiter_lines yields STR (decoded lines),
    # not bytes — EventSource does `line.rstrip("\n")` directly on the str.
    async def _aiter_lines():
        body = response.content.decode("utf-8") if isinstance(response.content, bytes) else response.content
        for line in body.splitlines(keepends=True):
            yield line

    # Attach aiter_lines to the response so EventSource can iterate it.
    # If `response` is an exception, we skip this — error paths don't reach
    # the consumer.
    if isinstance(response, httpx.Response):
        response.aiter_lines = _aiter_lines
        # The stream() context manager wraps the response. raise_for_status
        # is called inside the `async with` body so we patch it to raise
        # for 4xx/5xx just like the real httpx Response.
        if response.status_code >= 400:

            def _raise():
                raise httpx.HTTPStatusError(
                    f"HTTP {response.status_code}",
                    request=response.request,
                    response=response,
                )

            response.raise_for_status = _raise

        class _StreamCM:
            async def __aenter__(self_):
                return response

            async def __aexit__(self_, exc_type, exc, tb):
                return None

        # Use MagicMock (not AsyncMock) so client.stream(...) returns the
        # context manager directly. AsyncMock(return_value=...) wraps it in a
        # coroutine, which `async with` can't accept. .call_args still works
        # for introspection.
        client.stream = MagicMock(return_value=_StreamCM())

    if isinstance(response, Exception):
        client.post = AsyncMock(side_effect=response)

        class _ErrCM:
            async def __aenter__(self_):
                raise response

            async def __aexit__(self_, exc_type, exc, tb):
                return None

        client.stream = MagicMock(return_value=_ErrCM())
    else:
        client.post = AsyncMock(return_value=response)

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

        client.stream.assert_called_once()
        call_kwargs = client.stream.call_args.kwargs
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

        url = client.stream.call_args.args[1]
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

        call_kwargs = client.stream.call_args.kwargs
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

        call_kwargs = client.stream.call_args.kwargs
        assert call_kwargs["json"] == {"text": "what's the weather?"}

    @pytest.mark.asyncio
    async def test_accepts_previous_messages_kwarg(self):
        """P0 from cubic AI review: the shared `chat()` signature must
        accept `previous_messages=`. Otherwise the Telegram / WhatsApp
        plugins — which pass this kwarg — raise TypeError and crash the
        webhook on every auto-reply."""
        resp = _sse_response(["ok"])
        client = _mock_async_client_post(resp)

        with patch("persona_client.httpx.AsyncClient", return_value=client):
            reply = await persona_client.chat(
                app_id="app-1",
                api_key="k",
                omi_base="https://api.omi.me",
                text="hi",
                uid="u-1",
                previous_messages=[
                    {"role": "human", "text": "earlier message"},
                    {"role": "ai", "text": "earlier reply"},
                ],
            )

        assert reply == "ok"
        sent_body = client.stream.call_args.kwargs["json"]
        assert sent_body["previous_messages"] == [
            {"role": "human", "text": "earlier message"},
            {"role": "ai", "text": "earlier reply"},
        ]

    @pytest.mark.asyncio
    async def test_caps_previous_messages_at_20(self):
        """Belt-and-suspenders match for the server-side cap
        (routers/integration.persona_chat_via_integration slices to 20)."""
        resp = _sse_response(["ok"])
        client = _mock_async_client_post(resp)

        msgs = [{"role": "human", "text": f"msg-{i}"} for i in range(50)]

        with patch("persona_client.httpx.AsyncClient", return_value=client):
            await persona_client.chat(
                app_id="app-1",
                api_key="k",
                omi_base="https://api.omi.me",
                text="hi",
                uid="u-1",
                previous_messages=msgs,
            )

        sent = client.stream.call_args.kwargs["json"]["previous_messages"]
        assert len(sent) == 20

    @pytest.mark.asyncio
    async def test_caps_previous_message_text_at_8192(self):
        resp = _sse_response(["ok"])
        client = _mock_async_client_post(resp)

        with patch("persona_client.httpx.AsyncClient", return_value=client):
            await persona_client.chat(
                app_id="app-1",
                api_key="k",
                omi_base="https://api.omi.me",
                text="hi",
                uid="u-1",
                previous_messages=[{"role": "human", "text": "x" * 100_000}],
            )

        sent = client.stream.call_args.kwargs["json"]["previous_messages"]
        assert len(sent[0]["text"]) == 8192


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
# 3. [DONE] terminator regression
# ---------------------------------------------------------------------------
class TestDoneTerminator:
    """Regression: [DONE] must break the SSE loop immediately.

    Identified by cubic + maintainer review on PR #8531: filtering [DONE]
    from chunks but not breaking the loop means the client keeps waiting
    for the stream to close. If the server/proxy sends heartbeats after
    [DONE], asyncio.wait_for fires and the accumulated reply is lost.
    """

    @pytest.mark.asyncio
    async def test_done_breaks_loop_and_returns_reply(self):
        """Events: 'hello', '[DONE]' → reply should be 'hello', not ''.

        The mock body has 'data: hello\n\n' followed by 'data: [DONE]\n\n'
        and then nothing else. If the consumer doesn't break on [DONE],
        it will wait for more events until the read timeout fires,
        returning ''.
        """
        body = "data: hello\n\ndata: [DONE]\n\n"
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
                timeout_seconds=5.0,
            )
        assert reply == "hello", f"Expected 'hello', got {reply!r}"

    @pytest.mark.asyncio
    async def test_done_not_included_in_reply(self):
        """[DONE] must never appear in the reply text."""
        body = "data: hello\n\ndata: world\n\ndata: [DONE]\n\n"
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
        assert "[DONE]" not in reply
        assert reply == "helloworld"


# ---------------------------------------------------------------------------
# 4. Error paths
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
        # After the cubic P1 timeout fix persona_client uses client.stream()
        # (not client.post()) as an async context manager. Mock stream to
        # raise httpx.TimeoutException from __aenter__.
        class _ErrCM:
            async def __aenter__(self_):
                raise httpx.TimeoutException("timed out", request=MagicMock())

            async def __aexit__(self_, exc_type, exc, tb):
                return None

        client = AsyncMock()
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=None)
        client.stream = MagicMock(return_value=_ErrCM())

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
        class _ErrCM:
            async def __aenter__(self_):
                raise httpx.ConnectError("boom", request=MagicMock())

            async def __aexit__(self_, exc_type, exc, tb):
                return None

        client = AsyncMock()
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=None)
        client.stream = MagicMock(return_value=_ErrCM())

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
        # P2 (cubic): the test name promised log verification but never
        # asserted on caplog. Without this assertion, a regression that
        # swallows the connect-error silently (returns '' without
        # logging) would pass — defeating the whole point of the test.
        error_records = [r for r in caplog.records if r.levelno >= logging.ERROR]
        assert error_records, "expected an ERROR-level log record on connect error"
        # The message must be informative enough for on-call to diagnose,
        # but MUST NOT contain the user-supplied api_key (the literal
        # "k" we passed in) or the raw uid.
        joined = " ".join(r.getMessage() for r in error_records)
        assert (
            "boom" in joined or "connect" in joined.lower()
        ), f"expected log to mention the connect error, got: {joined!r}"
        # Negative assertions — guard against future regressions where a
        # logger.error("%s", exception) leaks sensitive args.
        assert "api_key='k'" not in joined and "api_key=k" not in joined, f"api_key leaked into log: {joined!r}"
        assert "uid='u-1'" not in joined, f"uid leaked into log: {joined!r}"

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

        # persona_client now uses client.stream() — wrap resp in an async CM.
        class _StreamCM:
            async def __aenter__(self_):
                return resp

            async def __aexit__(self_, exc_type, exc, tb):
                return None

        client.stream = MagicMock(return_value=_StreamCM())

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
