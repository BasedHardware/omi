"""Content-free retirement response for already-released desktop clients."""

from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter()


@router.post('/v1/desktop/proactivity/completions', status_code=429)
def retired_desktop_proactivity() -> JSONResponse:
    # Released clients only arm their bounded cooldown on 429. No request
    # model or dependency: even stale credentials and malformed bodies are cheap.
    return JSONResponse(
        status_code=429,
        headers={
            'Retry-After': '3600',
            'X-Proactive-Quota-Limit': '0',
            'X-Proactive-Quota-Remaining': '0',
            'X-Proactive-Quota-Reset': '3600',
            'Cache-Control': 'no-store',
        },
        content={'detail': {'error': 'feature_retired', 'feature': 'desktop_proactivity'}},
    )
