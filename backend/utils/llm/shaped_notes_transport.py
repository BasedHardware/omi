"""Own the async transport used by notes' short-lived worker event loop."""

from contextlib import asynccontextmanager
from typing import AsyncIterator

import anthropic
import httpx
from langchain_anthropic import ChatAnthropic
from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI


def _isolated_anthropic(model: ChatAnthropic, transport: httpx.AsyncClient) -> ChatAnthropic:
    """Copy a BYOK Anthropic model onto a loop-local HTTP client.

    ``ChatAnthropic._async_client`` is a process-wide cached httpx pool.
    Notes calls ``asyncio.run`` once per conversation, so reusing that pool
    binds sockets to a loop that has already closed. ``cached_property`` has
    no setter; the copy's instance dict is the override, and the cached model
    is left untouched.
    """
    isolated = model.model_copy()
    params = dict(isolated._client_params)
    params['http_client'] = transport
    isolated.__dict__['_async_client'] = anthropic.AsyncClient(**params)
    return isolated


@asynccontextmanager
async def isolated_notes_model(model: BaseChatModel) -> AsyncIterator[BaseChatModel]:
    """Copy model configuration, never reuse/mutate its cached async connection pool.

    Notes enters asyncio.run from its existing synchronous processing worker.
    A cached SDK pool can otherwise retain sockets bound to an already-closed
    loop. The clone preserves the gateway subclass, callbacks and request-time
    attribution, and closes its own transport before that worker loop exits.
    OpenAI-compatible lanes (managed gateway and OpenAI/Gemini/OpenRouter BYOK)
    clone the OpenAI client. Anthropic BYOK is a ``ChatAnthropic`` and needs
    the same loop-local client, or conversation notes die as HTTP 500.
    """
    if isinstance(model, ChatOpenAI):
        async with httpx.AsyncClient() as transport:
            client = model.root_async_client.with_options(http_client=transport)
            yield model.model_copy(
                update={
                    'http_async_client': transport,
                    'root_async_client': client,
                    'async_client': client.chat.completions,
                }
            )
        return

    if isinstance(model, ChatAnthropic):
        async with httpx.AsyncClient() as transport:
            yield _isolated_anthropic(model, transport)
        return

    raise TypeError('Shaped notes requires the configured OpenAI-compatible notes lane')
