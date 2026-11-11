"""Mobile read-aloud TTS route with Gemini and legacy/direct providers.

Provides the mobile TTS contract so mobile clients can play
Omi's spoken responses in background / lock-screen scenarios without shipping
provider credentials to the client.

Rate limits per user (Redis-backed sliding-window + daily counter):
  - 50 requests per rolling 60 seconds → 429
  - 10,000 characters per UTC day → 429
  - 5,000 characters per single request (hard cap, 400)
"""

from utils.generated_compute import require_generated_compute, generated_compute_configured

import asyncio
import logging
import os
from typing import Any, Callable, Dict, cast

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from config.assistant_voices import ASSISTANT_VOICES, DEFAULT_ASSISTANT_VOICE
from database import redis_db, voice_preferences
from models.tts import (
    DEFAULT_MODEL_ID,
    DEFAULT_OUTPUT_FORMAT,
    DEFAULT_VOICE_ID,
    AssistantVoicePreference,
    AssistantVoicePreferenceUpdate,
    TtsSynthesizeRequest,
    TtsVoice,
    TtsVoiceCatalog,
)
from utils.http_client import get_tts_client, get_tts_semaphore
from utils.log_sanitizer import sanitize
from utils.other import endpoints as auth
from utils.executors import db_executor, run_blocking, critical_executor
from utils.tts import (
    TtsConfigurationError,
    TtsRequestLog,
    TtsResponseError,
    TtsUnavailableError,
    TtsUpstreamError,
    get_tts_provider,
    open_gemini_mp3_stream,
)

logger = logging.getLogger(__name__)

router = APIRouter()

# `utils.other.endpoints.with_rate_limit` has an untyped `auth_dependency`
# parameter; route access through a cast so this strict-checked file sees a
# concrete callable type instead of `Unknown`.
_auth_module = cast(Any, auth)

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


@router.get('/v1/tts/voices', tags=['tts'], response_model=TtsVoiceCatalog)
def list_tts_voices(uid: str = Depends(auth.get_current_user_uid)) -> TtsVoiceCatalog:
    return TtsVoiceCatalog(
        voices=[TtsVoice(id=voice_id, name=voice_id) for voice_id in ASSISTANT_VOICES],
        default_voice_id=DEFAULT_ASSISTANT_VOICE,
    )


@router.get('/v1/users/voice', tags=['tts'], response_model=AssistantVoicePreference)
def get_user_voice(uid: str = Depends(auth.get_current_user_uid)) -> AssistantVoicePreference:
    return AssistantVoicePreference(voice_id=voice_preferences.get_assistant_voice(uid))


@router.patch('/v1/users/voice', tags=['tts'], response_model=AssistantVoicePreference)
def update_user_voice(
    req: AssistantVoicePreferenceUpdate, uid: str = Depends(auth.get_current_user_uid)
) -> AssistantVoicePreference:
    return AssistantVoicePreference(voice_id=voice_preferences.set_assistant_voice(uid, req.voice_id))


def _is_valid_voice_id(voice_id: str) -> bool:
    """Alphanumeric only, 1-128 chars. Prevents path traversal against the
    ElevenLabs URL template (e.g. `../../history` retargeting `xi-api-key`).
    """
    return 1 <= len(voice_id) <= 128 and voice_id.isalnum()


def _needs_direct_output_format(output_format: str) -> bool:
    """Formats that require raw/direct provider output (not Gemini MP3 transcoding)."""
    return output_format == "ulaw_8000" or output_format.startswith("pcm_")


async def _stream_direct_tts(
    *,
    uid: str,
    req: TtsSynthesizeRequest,
    text: str,
    voice_id: str,
    char_count: int,
) -> StreamingResponse:
    eleven_key = os.getenv('ELEVENLABS_API_KEY')
    dg_key = os.getenv('DEEPGRAM_API_KEY')
    if not eleven_key and not dg_key:
        logger.error("tts_synthesize: no direct TTS provider key configured")
        raise HTTPException(status_code=503, detail="TTS service not configured")

    model_label = DEFAULT_MODEL_ID if req.model_id == DEFAULT_MODEL_ID else 'client-selected'
    if eleven_key and not _needs_direct_output_format(req.output_format):
        provider_name = "ElevenLabs"
        metrics = TtsRequestLog(provider='elevenlabs', model=model_label, chars=char_count)
    elif eleven_key and req.output_format in _EL_OUTPUT_FORMATS:
        provider_name = "ElevenLabs"
        metrics = TtsRequestLog(provider='elevenlabs', model=model_label, chars=char_count)
    elif dg_key and _dg_params(req.output_format) is not None:
        provider_name = "Deepgram"
        metrics = TtsRequestLog(provider='deepgram', model=_dg_model(req.model_id), chars=char_count)
    elif eleven_key:
        provider_name = "ElevenLabs"
        metrics = TtsRequestLog(provider='elevenlabs', model=model_label, chars=char_count)
    else:
        raise HTTPException(
            status_code=400,
            detail=f"unsupported output_format for available TTS providers: {req.output_format}",
        )

    if provider_name == "ElevenLabs":
        if not _is_valid_voice_id(voice_id):
            metrics.finish('invalid_voice')
            raise HTTPException(status_code=400, detail="invalid voice_id")
        if req.output_format not in _EL_OUTPUT_FORMATS:
            metrics.finish('invalid_format')
            raise HTTPException(
                status_code=400,
                detail=f"unsupported output_format; expected one of {sorted(_EL_OUTPUT_FORMATS)}",
            )
        body: Dict[str, Any] = {
            "text": text,
            "model_id": req.model_id,
        }
        if req.voice_settings is not None:
            body["voice_settings"] = req.voice_settings.model_dump(exclude_none=True)
        url = _el_tts_url(voice_id, req.output_format)
        media_type = _el_output_media_type(req.output_format)
        headers = {"Content-Type": "application/json", "Accept": media_type, "xi-api-key": eleven_key}
    else:
        dg = _dg_params(req.output_format)
        if dg is None:
            metrics.finish('invalid_format')
            raise HTTPException(
                status_code=400,
                detail=f"unsupported output_format for Deepgram TTS: {req.output_format}",
            )
        params = {"model": _dg_model(req.model_id), **dg}
        url = _DEEPGRAM_SPEAK_URL + "?" + "&".join(f"{k}={v}" for k, v in params.items())
        body = {"text": text}
        media_type = _el_output_media_type(req.output_format)
        headers = {"Content-Type": "application/json", "Authorization": f"Token {dg_key}"}

    client = get_tts_client()
    semaphore = get_tts_semaphore()

    try:
        await semaphore.acquire()
        try:
            upstream_cm = client.stream("POST", url, json=body, headers=headers, timeout=60.0)
            resp = await upstream_cm.__aenter__()
        except httpx.HTTPError as e:
            semaphore.release()
            metrics.finish('transport_error')
            logger.error(f"tts_synthesize: upstream request failed uid={uid}: {sanitize(str(e))}")
            raise HTTPException(status_code=502, detail="TTS upstream unavailable")

        if resp.status_code >= 400:
            err_body = await resp.aread()
            err_text = err_body.decode('utf-8', errors='replace')[:200]
            await upstream_cm.__aexit__(None, None, None)
            semaphore.release()
            metrics.finish(f'upstream_{resp.status_code}')
            logger.warning(
                f"tts_synthesize: {provider_name} returned {resp.status_code} uid={uid}: {sanitize(err_text)}"
            )
            raise HTTPException(status_code=resp.status_code, detail="TTS upstream error")
    except HTTPException:
        raise
    except Exception as e:
        try:
            semaphore.release()
        except Exception:
            pass
        metrics.finish('pre_stream_error')
        logger.error(f"tts_synthesize: pre-stream failure uid={uid}: {sanitize(str(e))}")
        raise HTTPException(status_code=502, detail="TTS upstream unavailable")

    async def audio_stream():
        outcome = 'success'
        try:
            async for chunk in resp.aiter_bytes():
                metrics.mark_first_byte()
                yield chunk
        except (asyncio.CancelledError, GeneratorExit):
            outcome = 'cancelled'
            raise
        except Exception:
            outcome = 'stream_error'
            raise
        finally:
            try:
                await upstream_cm.__aexit__(None, None, None)
            except Exception:
                pass
            try:
                semaphore.release()
            except Exception:
                pass
            metrics.finish(outcome)

    return StreamingResponse(audio_stream(), media_type=media_type)


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
    """Synthesize speech through Gemini (default), with legacy/direct provider paths."""
    if generated_compute_configured():
        await run_blocking(db_executor, require_generated_compute, uid, 'desktop_tts', allow_byok=False)
    if 'voice_id' in req.model_fields_set:
        voice_id = req.voice_id
    else:
        voice_id = await run_blocking(db_executor, voice_preferences.get_assistant_voice, uid)
    if not _is_valid_voice_id(voice_id):
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
        redis_db.check_tts_rate_limit_for_user,
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
            detail="Daily TTS character limit exceeded. Resets at midnight in your time zone.",
            headers={"Retry-After": str(retry_after or 3600)},
        )
    # status == -1 (Redis error): fail-open intentionally — TTS is best-effort.

    try:
        provider = get_tts_provider()
    except TtsConfigurationError as exc:
        raise HTTPException(status_code=503, detail="TTS service not configured") from exc

    # DevKit/local-dev direct formats (e.g. ulaw_8000, pcm_*) need raw provider
    # output and are not supported by Gemini MP3 transcoding.
    if _needs_direct_output_format(req.output_format) or (
        provider == 'legacy' and os.getenv('DEEPGRAM_API_KEY') and not os.getenv('ELEVENLABS_API_KEY')
    ):
        return await _stream_direct_tts(uid=uid, req=req, text=text, voice_id=voice_id, char_count=char_count)

    if provider == 'gemini':
        try:
            audio_stream = await open_gemini_mp3_stream(
                text=text,
                voice_id=voice_id,
                client='mobile',
            )
        except TtsConfigurationError as exc:
            # Allow local/dev fallback when Gemini is unavailable but a direct
            # provider is configured and the request is a standard MP3 format.
            if os.getenv('ELEVENLABS_API_KEY') or os.getenv('DEEPGRAM_API_KEY'):
                return await _stream_direct_tts(uid=uid, req=req, text=text, voice_id=voice_id, char_count=char_count)
            raise HTTPException(status_code=503, detail="TTS service not configured") from exc
        except TtsUpstreamError as exc:
            raise HTTPException(status_code=exc.status_code, detail="TTS upstream error") from exc
        except (TtsUnavailableError, TtsResponseError) as exc:
            raise HTTPException(status_code=502, detail="TTS upstream unavailable") from exc
        return StreamingResponse(audio_stream, media_type="audio/mpeg")

    # Legacy provider path (MP3-compatible). Keep direct streaming behavior for
    # non-default formats where possible.
    if req.output_format != DEFAULT_OUTPUT_FORMAT or os.getenv('DEEPGRAM_API_KEY'):
        return await _stream_direct_tts(uid=uid, req=req, text=text, voice_id=voice_id, char_count=char_count)

    api_key = os.getenv('ELEVENLABS_API_KEY')
    # model_id is client-controlled for released-client compatibility. Keep it
    # out of logs unless it is the known shipped default.
    model_label = DEFAULT_MODEL_ID if req.model_id == DEFAULT_MODEL_ID else 'client-selected'
    metrics = TtsRequestLog(provider='elevenlabs', model=model_label, chars=char_count)
    if not api_key:
        metrics.finish('not_configured')
        logger.error("tts_synthesize: ELEVENLABS_API_KEY not configured")
        raise HTTPException(status_code=503, detail="TTS service not configured")

    body: Dict[str, Any] = {
        "text": text,
        "model_id": req.model_id,
        "output_format": req.output_format,
    }
    if req.voice_settings is not None:
        body["voice_settings"] = req.voice_settings.model_dump(exclude_none=True)

    url = _ELEVENLABS_URL.format(voice_id=DEFAULT_VOICE_ID)
    headers = {
        "Content-Type": "application/json",
        "Accept": "audio/mpeg",
        "xi-api-key": api_key,
    }

    client = get_tts_client()
    semaphore = get_tts_semaphore()

    try:
        await semaphore.acquire()
        try:
            upstream_cm = client.stream("POST", url, json=body, headers=headers, timeout=60.0)
            resp = await upstream_cm.__aenter__()
        except httpx.HTTPError as e:
            semaphore.release()
            metrics.finish('transport_error')
            logger.error(f"tts_synthesize: upstream request failed uid={uid}: {sanitize(str(e))}")
            raise HTTPException(status_code=502, detail="TTS upstream unavailable")

        if resp.status_code >= 400:
            err_body = await resp.aread()
            err_text = err_body.decode('utf-8', errors='replace')[:200]
            await upstream_cm.__aexit__(None, None, None)
            semaphore.release()
            metrics.finish(f'upstream_{resp.status_code}')
            logger.warning(f"tts_synthesize: ElevenLabs returned {resp.status_code} uid={uid}: {sanitize(err_text)}")
            raise HTTPException(status_code=resp.status_code, detail="TTS upstream error")
    except HTTPException:
        raise
    except Exception as e:
        try:
            semaphore.release()
        except Exception:
            pass
        metrics.finish('pre_stream_error')
        logger.error(f"tts_synthesize: pre-stream failure uid={uid}: {sanitize(str(e))}")
        raise HTTPException(status_code=502, detail="TTS upstream unavailable")

    async def legacy_audio_stream():
        outcome = 'success'
        try:
            async for chunk in resp.aiter_bytes():
                metrics.mark_first_byte()
                yield chunk
        except (asyncio.CancelledError, GeneratorExit):
            outcome = 'cancelled'
            raise
        except Exception:
            outcome = 'stream_error'
            raise
        finally:
            try:
                await upstream_cm.__aexit__(None, None, None)
            except Exception:
                pass
            try:
                semaphore.release()
            except Exception:
                pass
            metrics.finish(outcome)

    return StreamingResponse(legacy_audio_stream(), media_type="audio/mpeg")
