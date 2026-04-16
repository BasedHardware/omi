"""
Per-service health check endpoints for status page monitoring (e.g. Instatus).
All endpoints are unauthenticated and return JSON with no-cache headers.
"""

import asyncio
import os
from typing import Any, Dict

import httpx
from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter()

_NO_CACHE = {"Cache-Control": "no-cache"}
_TIMEOUT = 5.0  # seconds per individual check
_AGGREGATE_TIMEOUT = 10.0  # seconds for /services aggregate


def _ok(service: str, **extra) -> Dict[str, Any]:
    return {"status": "ok", "service": service, **extra}


def _down(service: str, error: str, **extra) -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={"status": "down", "service": service, "error": error, **extra},
        headers=_NO_CACHE,
    )


# ---------------------------------------------------------------------------
# /v1/health/chat  — Anthropic
# ---------------------------------------------------------------------------

@router.get("/v1/health/chat")
async def health_chat():
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        return _down("chat", "ANTHROPIC_API_KEY not set", provider="anthropic")
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(
                "https://api.anthropic.com/v1/models",
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                },
            )
            if resp.status_code in (200, 206):
                return JSONResponse(
                    content=_ok("chat", provider="anthropic"),
                    headers=_NO_CACHE,
                )
            return _down("chat", f"Anthropic returned {resp.status_code}", provider="anthropic")
    except Exception as exc:
        return _down("chat", str(exc), provider="anthropic")


# ---------------------------------------------------------------------------
# /v1/health/transcription  — Deepgram
# ---------------------------------------------------------------------------

@router.get("/v1/health/transcription")
async def health_transcription():
    api_key = os.getenv("DEEPGRAM_API_KEY", "")
    if not api_key:
        return _down("transcription", "DEEPGRAM_API_KEY not set", provider="deepgram")
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(
                "https://api.deepgram.com/v1/projects",
                headers={"Authorization": f"Token {api_key}"},
            )
            if resp.status_code in (200, 201):
                return JSONResponse(
                    content=_ok("transcription", provider="deepgram"),
                    headers=_NO_CACHE,
                )
            return _down("transcription", f"Deepgram returned {resp.status_code}", provider="deepgram")
    except Exception as exc:
        return _down("transcription", str(exc), provider="deepgram")


# ---------------------------------------------------------------------------
# /v1/health/storage  — Firestore
# ---------------------------------------------------------------------------

@router.get("/v1/health/storage")
async def health_storage():
    try:
        from database._client import db  # noqa: PLC0415

        # Reading a nonexistent doc just checks connectivity — cheap and safe.
        doc_ref = db.collection("_health_check").document("ping")
        await asyncio.wait_for(
            asyncio.get_event_loop().run_in_executor(None, doc_ref.get),
            timeout=_TIMEOUT,
        )
        return JSONResponse(
            content=_ok("storage", provider="firestore"),
            headers=_NO_CACHE,
        )
    except Exception as exc:
        return _down("storage", str(exc), provider="firestore")


# ---------------------------------------------------------------------------
# /v1/health/ai  — OpenAI
# ---------------------------------------------------------------------------

@router.get("/v1/health/ai")
async def health_ai():
    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key:
        return _down("ai", "OPENAI_API_KEY not set", provider="openai")
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(
                "https://api.openai.com/v1/models",
                headers={"Authorization": f"Bearer {api_key}"},
            )
            if resp.status_code == 200:
                return JSONResponse(
                    content=_ok("ai", provider="openai"),
                    headers=_NO_CACHE,
                )
            return _down("ai", f"OpenAI returned {resp.status_code}", provider="openai")
    except Exception as exc:
        return _down("ai", str(exc), provider="openai")


# ---------------------------------------------------------------------------
# /v1/health/search  — Typesense
# ---------------------------------------------------------------------------

@router.get("/v1/health/search")
async def health_search():
    host = os.getenv("TYPESENSE_HOST", "")
    port = os.getenv("TYPESENSE_HOST_PORT", "443")
    api_key = os.getenv("TYPESENSE_API_KEY", "")

    if not host or not api_key:
        return _down("search", "TYPESENSE_HOST or TYPESENSE_API_KEY not set", provider="typesense")

    url = f"https://{host}:{port}/health"
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(url, headers={"X-TYPESENSE-API-KEY": api_key})
            if resp.status_code == 200:
                return JSONResponse(
                    content=_ok("search", provider="typesense"),
                    headers=_NO_CACHE,
                )
            return _down("search", f"Typesense returned {resp.status_code}", provider="typesense")
    except Exception as exc:
        return _down("search", str(exc), provider="typesense")


# ---------------------------------------------------------------------------
# /v1/health/services  — Aggregate (concurrent)
# ---------------------------------------------------------------------------

async def _check(name: str, coro) -> Dict[str, Any]:
    """Run a health coroutine, return a dict with status info."""
    try:
        result = await asyncio.wait_for(coro, timeout=_TIMEOUT)
        # result is either a plain dict (ok) or a JSONResponse (down)
        if isinstance(result, JSONResponse):
            body = result.body
            import json
            return json.loads(body)
        return result
    except asyncio.TimeoutError:
        return {"status": "down", "service": name, "error": "timeout"}
    except Exception as exc:
        return {"status": "down", "service": name, "error": str(exc)}


@router.get("/v1/health/services")
async def health_services():
    checks = await asyncio.gather(
        _check("chat", health_chat()),
        _check("transcription", health_transcription()),
        _check("storage", health_storage()),
        _check("ai", health_ai()),
        _check("search", health_search()),
        return_exceptions=False,
    )

    services = {r["service"]: r for r in checks}
    statuses = {r["status"] for r in checks}

    if statuses == {"ok"}:
        overall = "ok"
        status_code = 200
    elif "ok" in statuses:
        overall = "degraded"
        status_code = 207
    else:
        overall = "down"
        status_code = 503

    return JSONResponse(
        status_code=status_code,
        content={"status": overall, "services": services},
        headers=_NO_CACHE,
    )
