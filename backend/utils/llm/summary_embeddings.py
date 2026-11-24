"""Isolated summary embedding IO; preserve chat routing and notes checkpoint identity."""

import asyncio
import time
from typing import List

import httpx
from openai import AsyncOpenAI
from openai.resources.embeddings import AsyncEmbeddings

from config.summary_context import context_stage
from utils.byok import get_byok_key
from utils.generated_compute import require_current_generated_compute as _require_client_budget
from utils.llm.gateway_client import ainvoke_openai_embeddings_gateway, should_route_features_through_gateway


def _embeddings_gateway_mode() -> bool:
    try:
        return should_route_features_through_gateway()
    except RuntimeError:
        return False


def embed_query_once(text: str, *, deadline_monotonic: float) -> List[float]:
    """Optional summary IO: one key, no fallback/retry, cancellable absolute deadline."""
    with context_stage('budget'):
        _require_client_budget('openai_embeddings', provider='openai')
        byok = get_byok_key('openai')
        remaining = deadline_monotonic - time.monotonic()
        if remaining <= 0:
            raise TimeoutError('summary embedding deadline')

    async def request() -> List[float]:
        async with asyncio.timeout(remaining):
            if _embeddings_gateway_mode():
                return (
                    await ainvoke_openai_embeddings_gateway(
                        [text], timeout_seconds=remaining, byok_api_key=byok, isolated=True
                    )
                )[0]
            async with httpx.AsyncClient(timeout=remaining, transport=httpx.AsyncHTTPTransport(retries=0)) as transport:
                # Bypass LangChain's retry/chunking layers for this single,
                # already token-bounded query. Other proxy methods are unchanged.
                async with AsyncOpenAI(api_key=byok, max_retries=0, timeout=remaining, http_client=transport) as client:
                    response = await AsyncEmbeddings(client).create(model='text-embedding-3-large', input=text)
                    return response.data[0].embedding

    with context_stage('embedding'):
        return asyncio.run(request())
