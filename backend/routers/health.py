import asyncio
import logging
import os
import time

import httpx
from fastapi import APIRouter
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

router = APIRouter()

TIMEOUT = 5.0  # seconds per check


async def _check_anthropic() -> dict:
    """Check Anthropic API connectivity."""
    try:
        api_key = os.getenv('ANTHROPIC_API_KEY', '')
        if not api_key:
            return {"status": "down", "error": "ANTHROPIC_API_KEY not set"}
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            r = await client.get(
                "https://api.anthropic.com/v1/models",
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                },
            )
            if r.status_code == 200:
                return {"status": "ok"}
            elif r.status_code == 401:
                return {"status": "down", "error": "invalid API key or out of credits"}
            else:
                return {"status": "down", "error": f"HTTP {r.status_code}"}
    except Exception as e:
        return {"status": "down", "error": str(e)[:200]}


async def _check_deepgram() -> dict:
    """Check Deepgram API connectivity."""
    try:
        api_key = os.getenv('DEEPGRAM_API_KEY', '')
        if not api_key:
            return {"status": "down", "error": "DEEPGRAM_API_KEY not set"}
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            r = await client.get(
                "https://api.deepgram.com/v1/projects",
                headers={"Authorization": f"Token {api_key}"},
            )
            if r.status_code == 200:
                return {"status": "ok"}
            else:
                return {"status": "down", "error": f"HTTP {r.status_code}"}
    except Exception as e:
        return {"status": "down", "error": str(e)[:200]}


async def _check_openai() -> dict:
    """Check OpenAI API connectivity."""
    try:
        api_key = os.getenv('OPENAI_API_KEY', '')
        if not api_key:
            return {"status": "down", "error": "OPENAI_API_KEY not set"}
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            r = await client.get(
                "https://api.openai.com/v1/models",
                headers={"Authorization": f"Bearer {api_key}"},
            )
            if r.status_code == 200:
                return {"status": "ok"}
            else:
                return {"status": "down", "error": f"HTTP {r.status_code}"}
    except Exception as e:
        return {"status": "down", "error": str(e)[:200]}


async def _check_firestore() -> dict:
    """Check Firestore connectivity with a minimal read."""
    try:
        from database._client import db
        # Read a nonexistent doc — fast, just checks connectivity
        doc = db.collection('_health_check').document('ping').get()
        return {"status": "ok"}
    except Exception as e:
        return {"status": "down", "error": str(e)[:200]}


async def _check_typesense() -> dict:
    """Check Typesense connectivity."""
    try:
        host = os.getenv('TYPESENSE_HOST', '')
        port = os.getenv('TYPESENSE_HOST_PORT', '443')
        api_key = os.getenv('TYPESENSE_API_KEY', '')
        if not host or not api_key:
            return {"status": "down", "error": "TYPESENSE config not set"}
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            r = await client.get(
                f"https://{host}:{port}/health",
                headers={"X-TYPESENSE-API-KEY": api_key},
            )
            if r.status_code == 200:
                return {"status": "ok"}
            else:
                return {"status": "down", "error": f"HTTP {r.status_code}"}
    except Exception as e:
        return {"status": "down", "error": str(e)[:200]}


def _make_response(service: str, result: dict) -> JSONResponse:
    body = {"service": service, **result}
    status = 200 if result.get("status") == "ok" else 503
    return JSONResponse(content=body, status_code=status, headers={"Cache-Control": "no-cache, no-store"})


@router.get("/v1/health/chat")
async def health_chat():
    """Check Anthropic (chat) API health."""
    result = await _check_anthropic()
    return _make_response("chat", result)


@router.get("/v1/health/transcription")
async def health_transcription():
    """Check Deepgram (transcription) API health."""
    result = await _check_deepgram()
    return _make_response("transcription", result)


@router.get("/v1/health/ai")
async def health_ai():
    """Check OpenAI (AI processing) API health."""
    result = await _check_openai()
    return _make_response("ai", result)


@router.get("/v1/health/storage")
async def health_storage():
    """Check Firestore (database) health."""
    result = await _check_firestore()
    return _make_response("storage", result)


@router.get("/v1/health/search")
async def health_search():
    """Check Typesense (search) health."""
    result = await _check_typesense()
    return _make_response("search", result)


@router.get("/v1/health/services")
async def health_services():
    """Aggregate health check for all services."""
    start = time.time()
    results = await asyncio.gather(
        _check_anthropic(),
        _check_deepgram(),
        _check_openai(),
        _check_firestore(),
        _check_typesense(),
        return_exceptions=True,
    )

    service_names = ["chat", "transcription", "ai", "storage", "search"]
    services = {}
    for name, result in zip(service_names, results):
        if isinstance(result, Exception):
            services[name] = {"status": "down", "error": str(result)[:200]}
        else:
            services[name] = result

    up_count = sum(1 for s in services.values() if s.get("status") == "ok")
    total = len(services)

    if up_count == total:
        overall = "ok"
        status_code = 200
    elif up_count == 0:
        overall = "down"
        status_code = 503
    else:
        overall = "degraded"
        status_code = 200  # Still return 200 for degraded so the page shows partial

    elapsed = round(time.time() - start, 2)
    body = {"status": overall, "services": services, "response_time_s": elapsed}
    return JSONResponse(content=body, status_code=status_code, headers={"Cache-Control": "no-cache, no-store"})
