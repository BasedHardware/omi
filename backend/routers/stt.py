"""STT proxy route — authed proxy in front of the parakeet transcription service.

Step 1 of the parakeet cleanup plan (issue #8854): clients must not call the
parakeet service directly (it has no auth of its own — only the internal LB
shields it). This route puts the standard Omi auth guard plus per-UID rate
limiting in front of parakeet's `/v2/transcribe`, so the mobile app's
"Omi Parakeet" provider can migrate off the direct `parakeet.omiapi.com` URL.

The response mirrors parakeet `/v2/transcribe` verbatim:
    {"text": str, "segments": [{"start", "end", "text", "speaker"}], "detected_language": str}
"""

import asyncio
import logging
import os
import re
import sys
from pathlib import Path
from typing import BinaryIO

import httpx
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile

from utils.http_client import get_stt_proxy_client, get_stt_proxy_semaphore, get_stt_probe_semaphore
from utils.log_sanitizer import sanitize
from utils.other import endpoints as auth
from utils.analytics import record_usage
from utils.executors import db_executor, storage_executor, run_blocking
from utils.subscription import resolve_transcription_allowance, TRANSCRIPTION_ALLOWANCE_TRANSIENT_REASONS
from utils.observability.fallback import record_fallback
from utils.async_tasks import create_named_task
from utils.stt import duration_probe
from utils.stt.parakeet_request_metrics import observe_parakeet_request

logger = logging.getLogger(__name__)

router = APIRouter()

# Mirrors _MAX_PCM_BODY_BYTES in routers/chat.py. Parakeet enforces its own
# duration cap (PARAKEET_MAX_FILE_DURATION); this only bounds backend memory.
_MAX_UPLOAD_BYTES = 200_000_000

# How long a request may wait for an upstream slot before failing fast with
# 503. Waiters hold no RAM (the body stays in starlette's disk spool until a
# slot is acquired), so this only bounds client-perceived latency.
_UPSTREAM_WAIT_SECS = 30.0
_PROBE_TIMEOUT_SECS = 20.0

_SAFE_FILENAME_RE = re.compile(r'[^A-Za-z0-9._-]')
_MAX_FILENAME_LEN = 64
_MAX_EXTENSION_LEN = 8


async def _probe_audio_seconds(audio_file: BinaryIO) -> int:
    # A separate bound keeps admission probes out of the provider slots and
    # out of storage_executor. Only the quick spool rollover borrows a thread.
    async with get_stt_probe_semaphore():
        descriptor = await run_blocking(storage_executor, audio_file.fileno)
        spawn = create_named_task(
            asyncio.create_subprocess_exec(
                sys.executable,
                '-m',
                duration_probe.__name__,
                cwd=str(Path(duration_probe.__file__).parents[2]),
                stdin=descriptor,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            ),
            name='stt-duration-probe-spawn',
        )
        try:
            process = await asyncio.shield(spawn)
            output, _ = await process.communicate()
        finally:
            # Shield spawn so cancellation cannot lose ownership of a child.
            # Finish reaping even if the request receives another cancellation.
            cleanup = create_named_task(_reap_probe(spawn), name='stt-duration-probe-reap')
            cancelled = False
            while not cleanup.done():
                try:
                    await asyncio.shield(cleanup)
                except asyncio.CancelledError:
                    cancelled = True
            cleanup.result()
            if cancelled:
                raise asyncio.CancelledError
        if process.returncode == 2:
            raise HTTPException(status_code=400, detail='Cannot determine audio duration')
        if process.returncode != 0:
            raise HTTPException(status_code=503, detail='Audio duration probe unavailable')
        try:
            return int(output)
        except ValueError:
            raise HTTPException(status_code=503, detail='Audio duration probe unavailable') from None


async def _reap_probe(spawn: asyncio.Task[asyncio.subprocess.Process]) -> None:
    process = await spawn
    if process.returncode is None:
        try:
            process.kill()
        except ProcessLookupError:
            pass
    await process.wait()


async def _admit(uid: str, source: str | None, seconds: int) -> None:
    # This route calls Omi-paid Parakeet; Deepgram BYOK cannot exempt it.
    allowance = await run_blocking(db_executor, resolve_transcription_allowance, uid, source=source, byok_active=False)
    if allowance.reason in TRANSCRIPTION_ALLOWANCE_TRANSIENT_REASONS:
        raise HTTPException(status_code=503, detail='Transcription allowance temporarily unavailable')
    if not allowance.managed or (allowance.remaining_seconds is not None and seconds > allowance.remaining_seconds):
        raise HTTPException(status_code=402, detail='Transcription allowance exhausted')


def _safe_upstream_filename(filename) -> str:
    """Parakeet builds its temp file path from the client-supplied filename —
    never forward path separators, dot-prefixed names, or overlong names.
    Truncation keeps a short extension so upstream decoders that sniff by
    suffix still see it.
    """
    base = os.path.basename(filename or '')
    base = _SAFE_FILENAME_RE.sub('_', base).lstrip('.')
    if len(base) > _MAX_FILENAME_LEN:
        stem, dot, ext = base.rpartition('.')
        if dot and 0 < len(ext) <= _MAX_EXTENSION_LEN:
            base = stem[: _MAX_FILENAME_LEN - len(ext) - 1] + '.' + ext
        else:
            base = base[:_MAX_FILENAME_LEN]
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

    # Starlette has already spooled the multipart body to disk by this point;
    # these checks bound backend RAM, not the upload itself. file.size is the
    # primary size enforcement — starlette populates it for every multipart
    # part, chunked uploads included. The Content-Length check just rejects a
    # step earlier when the header is present.
    content_length = request.headers.get('content-length')
    if content_length and content_length.isdigit() and int(content_length) > _MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail=f'Body too large (max {_MAX_UPLOAD_BYTES} bytes)')
    if file.size is not None and file.size > _MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail=f'Body too large (max {_MAX_UPLOAD_BYTES} bytes)')

    if file.size == 0:
        raise HTTPException(status_code=400, detail='No audio data provided')
    if file.size is None:
        # Defense in depth for callers without Starlette's multipart size.
        sample = await file.read(_MAX_UPLOAD_BYTES + 1)
        size = len(sample)
        del sample
        if size > _MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail=f'Body too large (max {_MAX_UPLOAD_BYTES} bytes)')
        if not size:
            raise HTTPException(status_code=400, detail='No audio data provided')
        await file.seek(0)

    try:
        seconds = await asyncio.wait_for(_probe_audio_seconds(file.file), timeout=_PROBE_TIMEOUT_SECS)
    except asyncio.TimeoutError:
        raise HTTPException(status_code=503, detail='Audio duration probe timed out — try again shortly') from None
    except OSError:
        raise HTTPException(status_code=503, detail='Audio duration probe unavailable') from None
    await file.seek(0)
    source = request.headers.get('x-app-platform')
    await _admit(uid, source, seconds)

    upstream_url = api_url.rstrip('/') + '/v2/transcribe'
    client = get_stt_proxy_client()
    semaphore = get_stt_proxy_semaphore()

    try:
        await asyncio.wait_for(semaphore.acquire(), timeout=_UPSTREAM_WAIT_SECS)
    except asyncio.TimeoutError:
        logger.warning(f'stt_transcribe: no upstream slot within {_UPSTREAM_WAIT_SECS}s uid={uid}')
        raise HTTPException(status_code=503, detail='Transcription service busy — try again shortly')

    try:
        # Initial admission precedes the slot. Recheck after queueing so
        # stale admissions cannot escape the in-flight accounting bound.
        await _admit(uid, source, seconds)

        # Buffer only after holding a slot, so at most 4 request bodies are
        # resident in RAM at once — waiters keep theirs in the disk spool.
        # The bounded read is defense-in-depth should file.size be absent.
        audio_bytes = await file.read(_MAX_UPLOAD_BYTES + 1)
        if not audio_bytes:
            raise HTTPException(status_code=400, detail='No audio data provided')
        if len(audio_bytes) > _MAX_UPLOAD_BYTES:
            del audio_bytes
            raise HTTPException(status_code=413, detail=f'Body too large (max {_MAX_UPLOAD_BYTES} bytes)')

        files = {'file': (_safe_upstream_filename(file.filename), audio_bytes, file.content_type or 'audio/wav')}
        data = {'diarize': 'true' if diarize else 'false'}
        try:
            with observe_parakeet_request('v2', caller='app_proxy'):
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
                    payload = resp.json()
                except ValueError:
                    payload = None
                if isinstance(payload, dict) and payload.get('detail'):
                    detail = str(payload['detail'])
                logger.warning(f'stt_transcribe: parakeet returned {resp.status_code} uid={uid}: {sanitize(detail)}')
                raise HTTPException(status_code=resp.status_code, detail=detail)
            logger.error(f'stt_transcribe: parakeet returned {resp.status_code} uid={uid}: {sanitize(resp.text[:200])}')
            raise HTTPException(status_code=502, detail='Transcription failed upstream')

        try:
            payload = resp.json()
        except ValueError:
            logger.error(f'stt_transcribe: parakeet returned non-JSON success body uid={uid}')
            raise HTTPException(status_code=502, detail='Transcription upstream returned an invalid response')

        # Keep completed-but-unaccounted calls inside the four-slot bound too.
        # This is not a distributed monthly-quota reservation.
        try:
            await run_blocking(
                db_executor,
                record_usage,
                uid,
                transcription_seconds=seconds,
                usage_metadata={'funding': 'omi', 'provider': 'parakeet', 'source': 'parakeet_proxy'},
            )
        except Exception as error:
            # No idempotency key: withholding a completed transcript encourages
            # a retry and another paid provider call. Do not log exception text.
            logger.error('stt_transcribe: usage write failed exception_type=%s', type(error).__name__)
            record_fallback(component='other', from_mode='none', to_mode='none', reason='other', outcome='degraded')
        return payload
    finally:
        semaphore.release()
