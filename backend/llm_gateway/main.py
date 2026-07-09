import asyncio
import logging
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI

from llm_gateway.routers import anthropic_messages, health, metrics, openai_compatible
from llm_gateway.routers.dependencies import close_provider_registry

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        yield
    finally:
        await asyncio.gather(
            _run_shutdown_cleanup('image_generation_client', openai_compatible.close_image_generation_client),
            _run_shutdown_cleanup('anthropic_messages_client', anthropic_messages.close_anthropic_messages_client),
            _run_shutdown_cleanup('provider_registry', close_provider_registry),
        )


async def _run_shutdown_cleanup(name: str, cleanup: Callable[[], Awaitable[None]]) -> None:
    try:
        await cleanup()
    except Exception:
        logger.exception('LLM gateway shutdown cleanup failed: %s', name)


app = FastAPI(title='Omi LLM Gateway', lifespan=lifespan)
app.include_router(health.router)
app.include_router(openai_compatible.router)
app.include_router(anthropic_messages.router)
app.include_router(metrics.router)
