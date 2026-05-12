"""TTS proxy route — server-side text-to-speech with pluggable providers.

Mirrors `desktop/Backend-Rust/src/routes/tts.rs`.

Providers (selected via request `provider` field):
  - "elevenlabs" (default) — premium quality, ~$99-330 per 1M chars
  - "openai"               — ~6.6x cheaper at $15/1M chars, MP3 output

Rate limits per user (Redis-backed sliding-window + daily counter):
  - 50 requests per rolling 60 seconds → 429
  - 10,000 characters per UTC day → 429
  - 5,000 characters per single request (hard cap, 400)
"""

import logging
import os

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from database import redis_db
from models.tts import TtsSynthesizeRequest
from utils.http_client import get_tts_client, get_tts_semaphore
from utils.log_sanitizer import sanitize
from utils.other import endpoints as auth

logger = logging.getLogger(__name__)

router = APIRouter()

# Limits mirror desktop/Backend-Rust/src/routes/tts.rs
_TTS_BURST_PER_MINUTE = 50
_TTS_DAILY_CHAR_LIMIT = 10_000
_TTS_BURST_WINDOW_SECS = 60
_TTS_REQUEST_CHAR_LIMIT = 5_000

_ELEVENLABS_URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
_OPENAI_TTS_URL = "https://api.openai.com/v1/audio/speech"

_OPENAI_VOICES = {
    "alloy",
    "ash",
    "ballad",
    "coral",
    "echo",
    "fable",
    "nova",
    "onyx",
    "sage",
    "shimmer",
    "verse",
}


def _is_valid_voice_id(voice_id: str) -> bool:
    """Alphanumeric only, 1-128 chars. Prevents path traversal against the
    ElevenLabs URL template (e.g. `../../history` retargeting `xi-api-key`).
    """
    return 1 <= len(voice_id) <= 128 and voice_id.isalnum()


def _is_valid_openai_voice(voice_id: str) -> bool:
    return voice_id in _OPENAI_VOICES


@router.post('/v2/tts/synthesize', tags=['tts'])
async def tts_synthesize(
    req: TtsSynthesizeRequest,
    uid: str = Depends(auth.with_rate_limit(auth.get_current_user_uid, "tts:synthesize")),
):
    """Proxy a TTS request to the selected provider. Per-user rate limited."""
    provider = (req.provider or "elevenlabs").lower()

    if provider == "elevenlabs":
        api_key = os.getenv('ELEVENLABS_API_KEY')
        if not api_key:
            logger.error("tts_synthesize: ELEVENLABS_API_KEY not configured")
            raise HTTPException(status_code=503, detail="ElevenLabs TTS not configured")
        if not _is_valid_voice_id(req.voice_id):
            raise HTTPException(status_code=400, detail="invalid voice_id")
    elif provider == "openai":
        api_key = os.getenv('OPENAI_API_KEY')
        if not api_key:
            logger.error("tts_synthesize: OPENAI_API_KEY not configured")
            raise HTTPException(status_code=503, detail="OpenAI TTS not configured")
        if not _is_valid_openai_voice(req.voice_id):
            raise HTTPException(status_code=400, detail="invalid voice_id for openai provider")
    else:
        raise HTTPException(status_code=400, detail="invalid provider (must be 'elevenlabs' or 'openai')")

    text = req.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="text must not be empty")

    char_count = len(text)
    if char_count > _TTS_REQUEST_CHAR_LIMIT:
        raise HTTPException(
            status_code=400,
            detail=f"text exceeds maximum length of {_TTS_REQUEST_CHAR_LIMIT} characters",
        )

    status, retry_after = redis_db.check_tts_rate_limit(
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

    if provider == "openai":
        openai_model = req.model_id if req.model_id in ("tts-1", "tts-1-hd") else "gpt-4o-mini-tts"
        body = {
            "model": openai_model,
            "input": text,
            "voice": req.voice_id,
            "response_format": "mp3",
        }
        url = _OPENAI_TTS_URL
        headers = {
            "Content-Type": "application/json",
            "Accept": "audio/mpeg",
            "Authorization": f"Bearer {api_key}",
        }
    else:
        body = {
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
                f"tts_synthesize: provider={provider} returned {resp.status_code} uid={uid}: {sanitize(err_text)}"
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
