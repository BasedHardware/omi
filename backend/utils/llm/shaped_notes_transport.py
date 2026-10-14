"""Own the async transport used by notes' short-lived worker event loop."""

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any, AsyncIterator

import anthropic
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


def _anthropic_client_params(model: ChatAnthropic) -> dict[str, Any]:
    """Public-field copy of ChatAnthropic's async client settings.

    The library keeps the same mapping on a protected cached property.
    Notes must not read that name: pyright treats it as private, and the
    cached client underneath it is the loop-bound pool this helper replaces.
    """
    params: dict[str, Any] = {
        'api_key': model.anthropic_api_key.get_secret_value(),
        'base_url': model.anthropic_api_url,
        'max_retries': model.max_retries,
        'default_headers': model.default_headers or None,
    }
    timeout = model.default_request_timeout
    if timeout is None or timeout > 0:
        params['timeout'] = timeout
    return params


def _isolated_anthropic(model: ChatAnthropic, transport: httpx.AsyncClient) -> ChatAnthropic:
    """Copy a BYOK Anthropic model onto a loop-local HTTP client.

    ``ChatAnthropic`` caches one process-wide async httpx pool. Notes calls
    ``asyncio.run`` once per conversation, so reusing that pool binds sockets
    to a loop that has already closed. ``cached_property`` has no setter; the
    copy's instance dict is the override, and the cached model is left untouched.
    """
    isolated = model.model_copy()
    params = _anthropic_client_params(isolated)
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
    if not isinstance(model, (ChatOpenAI, ChatAnthropic)):
        raise TypeError('Shaped notes requires an OpenAI-compatible or Anthropic notes lane')
    async with httpx.AsyncClient() as transport:
        if isinstance(model, ChatAnthropic):
            yield _isolated_anthropic(model, transport)
            return
        client = model.root_async_client.with_options(http_client=transport)
        yield model.model_copy(
            update={
                'http_async_client': transport,
                'root_async_client': client,
                'async_client': client.chat.completions,
            }
        )
