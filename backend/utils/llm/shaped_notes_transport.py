"""Own the async transport used by notes' short-lived worker event loop."""

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, AsyncIterator

import httpx
from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI

if TYPE_CHECKING:
    from langchain_anthropic import ChatAnthropic
else:
    try:
        from langchain_anthropic import ChatAnthropic
    except ImportError:
        # Unit tests path-load this module after replacing langchain_core in
        # sys.modules. langchain_anthropic then fails importing langchain_core
        # submodules those stubs do not provide. A placeholder keeps this module
        # importable; real Anthropic models only exist when the import succeeds.
        class ChatAnthropic:  # noqa: D101
            pass


@asynccontextmanager
async def isolated_notes_model(model: BaseChatModel) -> AsyncIterator[BaseChatModel]:
    """Copy model configuration, never reuse/mutate its cached async connection pool.

    Notes enters asyncio.run from its existing synchronous processing worker.
    A cached SDK pool can otherwise retain sockets bound to an already-closed
    loop. The clone preserves the gateway subclass, callbacks and request-time
    attribution, and closes its own transport before that worker loop exits.
    """
    if not isinstance(model, (ChatOpenAI, ChatAnthropic)):
        raise TypeError('Shaped notes requires an OpenAI-compatible or Anthropic notes lane')
    async with httpx.AsyncClient() as transport:
        if isinstance(model, ChatAnthropic):
            # Provider-switched BYOK uses the native Anthropic client. Its
            # cached property lives in __dict__, so model_copy isolates it
            # without changing the shared model or its async connection pool.
            # pyright: ignore[reportPrivateUsage] — langchain exposes no public
            # accessor for the cached client; model_copy needs the real object.
            client = model._async_client.with_options(http_client=transport)  # type: ignore[attr-defined]
            yield model.model_copy(update={'_async_client': client})  # type: ignore[dict-item]
            return
        client = model.root_async_client.with_options(http_client=transport)
        yield model.model_copy(
            update={
                'http_async_client': transport,
                'root_async_client': client,
                'async_client': client.chat.completions,
            }
        )
