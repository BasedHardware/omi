"""Attribute LLM calls to a stage and conversation (the chain lane calls this).

Two mechanisms; the proxy uses the first that is present for each request:

1. **Per-request headers** ``X-Pipeline-Lab-Stage`` / ``X-Pipeline-Lab-Conversation``.
   In the arm process call ``install_httpx_tagging(proxy_url)`` once, then wrap
   work in ``with lab_tag('notes', conversation_id):``. Every httpx request to
   the proxy URL (raw gateway client, OpenAI/Anthropic SDKs, LangChain) carries
   the tag of the current context. Context vars do not follow
   ``ThreadPoolExecutor.submit``; wrap submitted callables with
   ``carry_context(fn)`` (the chain's executor barrier is the natural place).
   This is correct under fan-out (K>1).
2. **Session tag** ``POST <proxy>/_lab/tag {"stage", "conversation_id"}``
   (``set_session_tag``): a proxy-wide default for requests without headers.
   Correct only while one conversation runs at a time.

The proxy strips both headers before forwarding upstream. Nothing here imports
product code; httpx is imported only inside ``install_httpx_tagging``.
"""

from __future__ import annotations

import contextlib
import contextvars
import json
import urllib.request
from typing import Any, Callable, Iterator, Optional

STAGE_HEADER = 'X-Pipeline-Lab-Stage'
CONVERSATION_HEADER = 'X-Pipeline-Lab-Conversation'
LAB_HEADER_PREFIX = 'x-pipeline-lab-'

_TAG: contextvars.ContextVar[Optional[tuple[str, Optional[str]]]] = contextvars.ContextVar(
    'pipeline_lab_llm_tag', default=None
)
_installed: dict[str, Any] = {}


@contextlib.contextmanager
def lab_tag(stage: str, conversation_id: Optional[str] = None) -> Iterator[None]:
    token = _TAG.set((stage, conversation_id))
    try:
        yield
    finally:
        _TAG.reset(token)


def current_headers() -> dict[str, str]:
    tag = _TAG.get()
    if tag is None:
        return {}
    headers = {STAGE_HEADER: tag[0]}
    if tag[1]:
        headers[CONVERSATION_HEADER] = tag[1]
    return headers


def carry_context(fn: Callable[..., Any]) -> Callable[..., Any]:
    """Bind ``fn`` to a copy of the caller's context (for executor.submit)."""
    context = contextvars.copy_context()

    def run(*args: Any, **kwargs: Any) -> Any:
        return context.run(fn, *args, **kwargs)

    return run


def install_httpx_tagging(proxy_url: str) -> Callable[[], None]:
    """Patch httpx send so requests to ``proxy_url`` carry the current tag. Idempotent; returns uninstall."""
    import httpx

    prefix = proxy_url.rstrip('/')
    if _installed:
        _installed['prefix'] = prefix
        return uninstall_httpx_tagging
    _installed['prefix'] = prefix
    sync_send = httpx.Client.send
    async_send = httpx.AsyncClient.send

    def tag(request: Any) -> None:
        if str(request.url).startswith(_installed.get('prefix', '\0')):
            for name, value in current_headers().items():
                request.headers[name] = value

    def send(self: Any, request: Any, *args: Any, **kwargs: Any) -> Any:
        tag(request)
        return sync_send(self, request, *args, **kwargs)

    async def asend(self: Any, request: Any, *args: Any, **kwargs: Any) -> Any:
        tag(request)
        return await async_send(self, request, *args, **kwargs)

    httpx.Client.send = send  # type: ignore[method-assign]
    httpx.AsyncClient.send = asend  # type: ignore[method-assign]
    _installed.update(sync=sync_send, asyncs=async_send)
    return uninstall_httpx_tagging


def uninstall_httpx_tagging() -> None:
    if not _installed:
        return
    import httpx

    httpx.Client.send = _installed['sync']  # type: ignore[method-assign]
    httpx.AsyncClient.send = _installed['asyncs']  # type: ignore[method-assign]
    _installed.clear()


def set_session_tag(proxy_url: str, stage: Optional[str], conversation_id: Optional[str] = None) -> None:
    """Set (or clear, with ``stage=None``) the proxy-wide default tag."""
    body = json.dumps({'stage': stage, 'conversation_id': conversation_id}).encode()
    request = urllib.request.Request(
        proxy_url.rstrip('/') + '/_lab/tag', data=body, headers={'Content-Type': 'application/json'}, method='POST'
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(request, timeout=10) as response:
        response.read()
