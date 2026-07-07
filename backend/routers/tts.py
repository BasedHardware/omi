"""TTS proxy route — proxies ElevenLabs text-to-speech server-side.

Mirrors `desktop/macos/Backend-Rust/src/routes/tts.rs` so mobile clients can play
Omi's spoken responses in background / lock-screen scenarios without shipping
an ElevenLabs API key to the client.

Rate limits per user (Redis-backed sliding-window + daily counter):
  - 50 requests per rolling 60 seconds → 429
  - 10,000 characters per UTC day → 429
  - 5,000 characters per single request (hard cap, 400)
"""

import logging
import os
import time
from typing import Any, Callable, Dict, List, Optional, Tuple, cast

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from database import redis_db
from models.tts import TtsSynthesizeRequest
from utils.http_client import get_tts_client, get_tts_semaphore
from utils.log_sanitizer import sanitize
from utils.other import endpoints as auth
from utils.executors import run_blocking, critical_executor

logger = logging.getLogger(__name__)

router = APIRouter()

# `utils.other.endpoints.with_rate_limit` has an untyped `auth_dependency`
# parameter; route access through a cast so this strict-checked file sees a
# concrete callable type instead of `Unknown`.
_auth_module = cast(Any, auth)

# Limits mirror desktop/macos/Backend-Rust/src/routes/tts.rs
_TTS_BURST_PER_MINUTE = 50
_TTS_DAILY_CHAR_LIMIT = 10_000
_TTS_BURST_WINDOW_SECS = 60
_TTS_REQUEST_CHAR_LIMIT = 5_000

_ELEVENLABS_URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
_ELEVENLABS_VOICES_URL = "https://api.elevenlabs.io/v1/voices"
_VOICES_CACHE_TTL_SECS = 3600
_voices_cache: Optional[Tuple[float, List[Dict[str, Any]]]] = None


def _is_valid_voice_id(voice_id: str) -> bool:
    """Alphanumeric only, 1-128 chars. Prevents path traversal against the
    ElevenLabs URL template (e.g. `../../history` retargeting `xi-api-key`).
    """
    return 1 <= len(voice_id) <= 128 and voice_id.isalnum()


def _normalize_voices(raw: object) -> List[Dict[str, Any]]:
    """Reduce the ElevenLabs /v1/voices payload to a minimal, client-safe voice list.

    Tolerates a missing/non-list `voices` key and non-dict/partial entries so an upstream shape
    change yields an empty or partial list rather than a 500.
    """
    raw_dict = cast(Dict[str, Any], raw) if isinstance(raw, dict) else {}
    voices = raw_dict.get("voices")
    if not isinstance(voices, list):
        return []
    result: List[Dict[str, Any]] = []
    for v in voices:
        if not isinstance(v, dict) or not v.get("voice_id"):
            continue
        voice = cast(Dict[str, Any], v)
        result.append(
            {
                "voice_id": voice.get("voice_id"),
                "name": voice.get("name"),
                "category": voice.get("category"),
                "preview_url": voice.get("preview_url"),
                "labels": voice.get("labels") if isinstance(voice.get("labels"), dict) else {},
            }
        )
    return result


def _is_cache_fresh(cached_at: float, now: float, ttl: int = _VOICES_CACHE_TTL_SECS) -> bool:
    return (now - cached_at) < ttl


@router.post(
    '/v2/tts/synthesize',
    tags=['tts'],
    response_class=StreamingResponse,
    responses={
        200: {
            "description": "MP3 audio stream.",
            "content": {"audio/mpeg": {"schema": {"type": "string", "format": "binary"}}},
        }
    },
)
async def tts_synthesize(
    req: TtsSynthesizeRequest,
    uid: str = Depends(
        cast(Callable[..., str], _auth_module.with_rate_limit(auth.get_current_user_uid, "tts:synthesize"))
    ),
):
    """Proxy a TTS request to ElevenLabs. Per-user rate limited."""
    api_key = os.getenv('ELEVENLABS_API_KEY')
    if not api_key:
        logger.error("tts_synthesize: ELEVENLABS_API_KEY not configured")
        raise HTTPException(status_code=503, detail="TTS service not configured")

    if not _is_valid_voice_id(req.voice_id):
        raise HTTPException(status_code=400, detail="invalid voice_id")

    text = req.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="text must not be empty")

    char_count = len(text)
    if char_count > _TTS_REQUEST_CHAR_LIMIT:
        raise HTTPException(
            status_code=400,
            detail=f"text exceeds maximum length of {_TTS_REQUEST_CHAR_LIMIT} characters",
        )

    status, retry_after = await run_blocking(
        critical_executor,
        redis_db.check_tts_rate_limit,
        uid,
        char_count=char_count,
        burst_limit=_TTS_BURST_PER_MINUTE,
        burst_window_secs=_TTS_BURST_WINDOW_SECS,
        daily_char_limit=_TTS_DAILY_CHAR_LIMIT,
    )
    if status == 1:
        logger.warning(f"tts_synthesize: burst rate limit exceeded uid={uid}")
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded: too many TTS requests. Try again in 60 seconds.",
            headers={"Retry-After": str(retry_after or _TTS_BURST_WINDOW_SECS)},
        )
    if status == 2:
        logger.warning(f"tts_synthesize: daily character limit exceeded uid={uid}")
        raise HTTPException(
            status_code=429,
            detail="Daily TTS character limit exceeded. Resets at midnight UTC.",
            headers={"Retry-After": str(retry_after or 3600)},
        )
    # status == -1 (Redis error): fail-open intentionally — TTS is best-effort.

    body: Dict[str, Any] = {
        "text": text,
        "model_id": req.model_id,
        "output_format": req.output_format,
    }
    if req.voice_settings is not None:
        body["voice_settings"] = req.voice_settings.model_dump(exclude_none=True)

    url = _ELEVENLABS_URL.format(voice_id=req.voice_id)
    headers = {
        "Content-Type": "application/json",
        "Accept": "audio/mpeg",
        "xi-api-key": api_key,
    }

    client = get_tts_client()
    semaphore = get_tts_semaphore()

    # Acquire the semaphore and open the upstream request OUTSIDE the generator
    # so we can raise a proper HTTPException before StreamingResponse starts
    # writing headers. The generator releases both on exit.
    try:
        await semaphore.acquire()
        try:
            upstream_cm = client.stream("POST", url, json=body, headers=headers, timeout=60.0)
            resp = await upstream_cm.__aenter__()
        except httpx.HTTPError as e:
            semaphore.release()
            logger.error(f"tts_synthesize: upstream request failed uid={uid}: {sanitize(str(e))}")
            raise HTTPException(status_code=502, detail="TTS upstream unavailable")

        if resp.status_code >= 400:
            err_body = await resp.aread()
            err_text = err_body.decode('utf-8', errors='replace')[:200]
            await upstream_cm.__aexit__(None, None, None)
            semaphore.release()
            logger.warning(
                f"tts_synthesize: ElevenLabs returned {resp.status_code} uid={uid}: " f"{sanitize(err_text)}"
            )
            raise HTTPException(status_code=resp.status_code, detail="TTS upstream error")
    except HTTPException:
        raise
    except Exception as e:
        # Defensive: never leak the semaphore on an unexpected failure above.
        try:
            semaphore.release()
        except Exception:
            pass
        logger.error(f"tts_synthesize: pre-stream failure uid={uid}: {sanitize(str(e))}")
        raise HTTPException(status_code=502, detail="TTS upstream unavailable")

    async def audio_stream():
        try:
            async for chunk in resp.aiter_bytes():
                yield chunk
        finally:
            try:
                await upstream_cm.__aexit__(None, None, None)
            except Exception:
                pass
            try:
                semaphore.release()
            except Exception:
                pass

    return StreamingResponse(audio_stream(), media_type="audio/mpeg")


@router.get('/v2/tts/voices', tags=['tts'])
async def get_voices(uid: str = Depends(auth.get_current_user_uid)) -> dict:
    """List the available ElevenLabs voices, proxied server-side (the API key is server-only).

    Cached in-process for _VOICES_CACHE_TTL_SECS so a client voice picker does not hammer the upstream.
    The synthesize endpoint already accepts any voice_id; this just lets clients discover them.
    """
    global _voices_cache
    now = time.monotonic()
    if _voices_cache is not None and _is_cache_fresh(_voices_cache[0], now):
        return {"voices": _voices_cache[1]}

    api_key = os.getenv('ELEVENLABS_API_KEY')
    if not api_key:
        logger.error("get_voices: ELEVENLABS_API_KEY not configured")
        raise HTTPException(status_code=503, detail="TTS service not configured")

    async with get_tts_semaphore():
        try:
            resp = await get_tts_client().get(_ELEVENLABS_VOICES_URL, headers={"xi-api-key": api_key}, timeout=15.0)
        except httpx.HTTPError as e:
            logger.error(f"get_voices: upstream request failed uid={uid}: {sanitize(str(e))}")
            raise HTTPException(status_code=502, detail="TTS upstream unavailable")

    if resp.status_code != 200:
        logger.warning(f"get_voices: ElevenLabs returned {resp.status_code} uid={uid}")
        raise HTTPException(status_code=502, detail="TTS upstream error")

    try:
        payload = resp.json()
    except ValueError as e:
        # Upstream replied 200 but with a non-JSON body (proxy HTML error page, truncated
        # response). Keep the documented 502-on-upstream-error contract instead of 500ing.
        logger.error(f"get_voices: upstream returned a non-JSON body uid={uid}: {sanitize(str(e))}")
        raise HTTPException(status_code=502, detail="TTS upstream error")

    voices = _normalize_voices(payload)
    _voices_cache = (now, voices)
    return {"voices": voices}
