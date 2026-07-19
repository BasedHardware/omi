import asyncio
import logging
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.responses import Response

from llm_gateway.gateway.request_context import REQUEST_ID_HEADER, request_id_for, resolve_request_id
from llm_gateway.gateway.accounting_sink import drain_accounting_persistence_tasks
from llm_gateway.routers import anthropic_messages, health, metrics, openai_compatible
from llm_gateway.routers.dependencies import close_provider_registry

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        yield
    finally:
        await asyncio.gather(
            _run_shutdown_cleanup('accounting_persistence', drain_accounting_persistence_tasks),
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


@app.exception_handler(Exception)
async def unhandled_request_failure(request: Request, exc: Exception) -> JSONResponse:
    """Return a traceable but non-sensitive response for unexpected failures."""
    request_id = request_id_for(request)
    logger.error(
        'Unhandled LLM gateway request failure request_id=%s type=%s',
        request_id,
        type(exc).__name__,
    )
    response = JSONResponse(status_code=500, content={'detail': 'internal server error'})
    response.headers[REQUEST_ID_HEADER] = request_id
    return response


@app.middleware('http')
async def request_correlation(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    request_id = resolve_request_id(request.headers.get(REQUEST_ID_HEADER))
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers[REQUEST_ID_HEADER] = request_id
    return response


app.include_router(health.router)
app.include_router(openai_compatible.router)
app.include_router(anthropic_messages.router)
app.include_router(metrics.router)
