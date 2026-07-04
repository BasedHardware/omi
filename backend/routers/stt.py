"""STT proxy route — authed proxy in front of the parakeet transcription service.

Step 1 of the parakeet cleanup plan (issue #8854): clients must not call the
parakeet service directly (it has no auth of its own — only the internal LB
shields it). This route puts the standard Omi auth guard plus per-UID rate
limiting in front of parakeet's `/v2/transcribe`, so the mobile app's
"Omi Parakeet" provider can migrate off the direct `parakeet.omiapi.com` URL.

The response mirrors parakeet `/v2/transcribe` verbatim:
    {"text": str, "segments": [{"start", "end", "text", "speaker"}], "detected_language": str}
"""

import logging
import os
import re

import httpx
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile

from utils.http_client import get_stt_client, get_stt_semaphore
from utils.log_sanitizer import sanitize
from utils.other import endpoints as auth

logger = logging.getLogger(__name__)

router = APIRouter()

# Mirrors _MAX_PCM_BODY_BYTES in routers/chat.py. Parakeet enforces its own
# duration cap (PARAKEET_MAX_FILE_DURATION); this only bounds backend memory.
_MAX_UPLOAD_BYTES = 200_000_000

_SAFE_FILENAME_RE = re.compile(r'[^A-Za-z0-9._-]')


def _safe_upstream_filename(filename) -> str:
    """Parakeet builds its temp file path from the client-supplied filename —
    never forward path separators or dot-prefixed names upstream.
    """
    base = os.path.basename(filename or '')
    base = _SAFE_FILENAME_RE.sub('_', base).lstrip('.')
    return base or 'audio.wav'


@router.post('/v1/stt/transcribe', tags=['stt'])
async def stt_transcribe(
    request: Request,
    file: UploadFile = File(...),
    diarize: bool = Form(True),
    uid: str = Depends(auth.with_rate_limit(auth.get_current_user_uid, "stt:transcribe")),
):
    """Transcribe an uploaded audio file via parakeet. Per-user rate limited."""
    api_url = os.getenv('HOSTED_PARAKEET_API_URL')
    if not api_url:
        logger.error('stt_transcribe: HOSTED_PARAKEET_API_URL not configured')
        raise HTTPException(status_code=503, detail='Transcription service not configured')

    # Reject oversized payloads from the Content-Length header before buffering.
    content_length = request.headers.get('content-length')
    if content_length and content_length.isdigit() and int(content_length) > _MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail=f'Body too large (max {_MAX_UPLOAD_BYTES} bytes)')

    audio_bytes = await file.read()
    if not audio_bytes:
        raise HTTPException(status_code=400, detail='No audio data provided')
    if len(audio_bytes) > _MAX_UPLOAD_BYTES:
        del audio_bytes
        raise HTTPException(status_code=413, detail=f'Body too large (max {_MAX_UPLOAD_BYTES} bytes)')

    upstream_url = api_url.rstrip('/') + '/v2/transcribe'
    files = {'file': (_safe_upstream_filename(file.filename), audio_bytes, file.content_type or 'audio/wav')}
    data = {'diarize': 'true' if diarize else 'false'}

    client = get_stt_client()
    try:
        async with get_stt_semaphore():
            resp = await client.post(upstream_url, files=files, data=data)
    except httpx.HTTPError as e:
        logger.error(f'stt_transcribe: parakeet request failed uid={uid}: {sanitize(str(e))}')
        raise HTTPException(status_code=502, detail='Transcription upstream unavailable')
    finally:
        del files
        del audio_bytes

    if resp.status_code >= 400:
        # 413 (audio too long) and 503 (model loading / overloaded) carry
        # client-actionable details — forward them as-is. Anything else is an
        # internal upstream failure the client can't act on.
        if resp.status_code in (413, 503):
            detail = 'Transcription failed upstream'
            try:
                detail = resp.json().get('detail') or detail
            except ValueError:
                pass
            logger.warning(f'stt_transcribe: parakeet returned {resp.status_code} uid={uid}: {sanitize(detail)}')
            raise HTTPException(status_code=resp.status_code, detail=detail)
        logger.error(f'stt_transcribe: parakeet returned {resp.status_code} uid={uid}: {sanitize(resp.text[:200])}')
        raise HTTPException(status_code=502, detail='Transcription failed upstream')

    try:
        return resp.json()
    except ValueError:
        logger.error(f'stt_transcribe: parakeet returned non-JSON success body uid={uid}')
        raise HTTPException(status_code=502, detail='Transcription upstream returned an invalid response')
