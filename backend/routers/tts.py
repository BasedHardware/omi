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
from typing import Any, Callable, Dict, cast

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
_DEEPGRAM_SPEAK_URL = "https://api.deepgram.com/v1/speak"

# ElevenLabs honors output_format as a QUERY PARAMETER on this endpoint; a body
# field of the same name is ignored and the upstream always returns MP3. That
# silent no-op is why clients asking for PCM got an MP3 anyway. The allowlist
# also keeps the value from injecting anything into the URL it is appended to.
_EL_OUTPUT_FORMATS = frozenset(
    {
        "mp3_44100",
        "mp3_44100_32",
        "mp3_44100_64",
        "mp3_44100_96",
        "mp3_44100_128",
        "mp3_44100_192",
        "mp3_44100_256",
        "pcm_16000",
        "pcm_22050",
        "pcm_24000",
        "pcm_44100",
        "ulaw_8000",
    }
)

_EL_MEDIA_TYPES = {
    "mp3": "audio/mpeg",
    "pcm": "audio/L16",
    "ulaw": "audio/basic",
}


def _el_output_media_type(output_format: str) -> str:
    return _EL_MEDIA_TYPES.get(output_format.split("_", 1)[0], "application/octet-stream")


def _el_tts_url(voice_id: str, output_format: str) -> str:
    """Upstream URL with the format in the query string, where ElevenLabs reads it."""
    return f"{_ELEVENLABS_URL.format(voice_id=voice_id)}?output_format={output_format}"


_DG_DEFAULT_MODEL = "aura-2-thalia-en"


def _dg_params(output_format: str) -> Dict[str, str] | None:
    """Deepgram /v1/speak query params for an output_format, or None if unsupported.

    The DevKit 2 speaker path needs raw 8 kHz mu-law (ulaw_8000) — container=none
    yields headerless bytes the RN client decodes directly.
    """
    if output_format == "ulaw_8000":
        return {"encoding": "mulaw", "sample_rate": "8000", "container": "none"}
    if output_format.startswith("mp3_"):
        return {"encoding": "mp3", "container": "mp3"}
    if output_format.startswith("pcm_"):
        rate = output_format.split("_", 1)[1]
        return {"encoding": "linear16", "sample_rate": rate, "container": "none"}
    return None


def _dg_model(model_id: str) -> str:
    # RN sends ElevenLabs model ids by default; swap in an Aura model for Deepgram.
    if model_id and model_id.startswith("aura"):
        return model_id
    return _DG_DEFAULT_MODEL


def _is_valid_voice_id(voice_id: str) -> bool:
    """Alphanumeric only, 1-128 chars. Prevents path traversal against the
    ElevenLabs URL template (e.g. `../../history` retargeting `xi-api-key`).
    """
    return 1 <= len(voice_id) <= 128 and voice_id.isalnum()


@router.post(
    '/v2/tts/synthesize',
    tags=['tts'],
    response_class=StreamingResponse,
    responses={
        200: {
            "description": "Audio stream in the requested output_format (MP3 by default).",
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
    """Proxy a TTS request (ElevenLabs or Deepgram). Per-user rate limited."""
    eleven_key = os.getenv('ELEVENLABS_API_KEY')
    dg_key = os.getenv('DEEPGRAM_API_KEY')
    if not eleven_key and not dg_key:
        logger.error("tts_synthesize: no TTS provider key configured")
        raise HTTPException(status_code=503, detail="TTS service not configured")

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

    # Provider dispatch: prefer ElevenLabs when configured (preserves existing
    # behavior); fall back to Deepgram (Aura) for local/dev with just a Deepgram
    # key. The DevKit speaker path needs ulaw_8000; Deepgram serves it as raw
    # 8 kHz mu-law the RN client decodes directly.
    if eleven_key:
        if not _is_valid_voice_id(req.voice_id):
            raise HTTPException(status_code=400, detail="invalid voice_id")
        if req.output_format not in _EL_OUTPUT_FORMATS:
            raise HTTPException(
                status_code=400,
                detail=f"unsupported output_format; expected one of {sorted(_EL_OUTPUT_FORMATS)}",
            )
        body: Dict[str, Any] = {
            "text": text,
            "model_id": req.model_id,
            # output_format deliberately NOT here: ElevenLabs reads it from the
            # query string only (see _EL_OUTPUT_FORMATS above).
        }
        if req.voice_settings is not None:
            body["voice_settings"] = req.voice_settings.model_dump(exclude_none=True)
        url = _el_tts_url(req.voice_id, req.output_format)
        media_type = _el_output_media_type(req.output_format)
        headers = {"Content-Type": "application/json", "Accept": media_type, "xi-api-key": eleven_key}
        provider_name = "ElevenLabs"
    else:
        dg = _dg_params(req.output_format)
        if dg is None:
            raise HTTPException(
                status_code=400,
                detail=f"unsupported output_format for Deepgram TTS: {req.output_format}",
            )
        params = {"model": _dg_model(req.model_id), **dg}
        url = _DEEPGRAM_SPEAK_URL + "?" + "&".join(f"{k}={v}" for k, v in params.items())
        body = {"text": text}
        media_type = _el_output_media_type(req.output_format)
        headers = {"Content-Type": "application/json", "Authorization": f"Token {dg_key}"}
        provider_name = "Deepgram"

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
                f"tts_synthesize: {provider_name} returned {resp.status_code} uid={uid}: {sanitize(err_text)}"
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

    return StreamingResponse(audio_stream(), media_type=media_type)
