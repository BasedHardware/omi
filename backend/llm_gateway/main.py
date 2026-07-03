from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI

from llm_gateway.routers import health, metrics, openai_compatible
from llm_gateway.routers.dependencies import close_provider_registry


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        yield
    finally:
        with suppress(Exception):
            await openai_compatible.close_image_generation_client()
        with suppress(Exception):
            await close_provider_registry()


app = FastAPI(title='Omi LLM Gateway', lifespan=lifespan)
app.include_router(health.router)
app.include_router(openai_compatible.router)
app.include_router(metrics.router)
