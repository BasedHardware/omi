"""Single-submit Soniox async adapter for bounded, independent held recovery.

Serving awaits async HTTP/polling outside the shared sync executor. The private
operator CLI retains a synchronous entrypoint in its own process.
No SDK retries, public audio URLs, user identifiers, or disk audio copies.
"""

import logging
import asyncio
import math
import os
import time
from uuid import UUID

import httpx
from config.batch_language_recovery import allowed
from config.batch_pipeline import second_multilingual_enabled
from config.prerecorded_stt import SONIOX_HELD_RECOVERY_MODEL, require_provider_environment
from utils.http_client import get_stt_client, get_stt_semaphore

from config.stt_provider_policy import (
    normalized_stt_language,
    soniox_accepts_language_hint,
    provider_is_enabled,
    STTServingSurface,
)

logger = logging.getLogger(__name__)
BASE_URL = 'https://api.soniox.com/v1'
MODEL = SONIOX_HELD_RECOVERY_MODEL
DEADLINE_SECONDS = 120


ERROR_KINDS = frozenset(
    {'error', 'refused', 'credit_refusal', 'rate_limited', 'error_5xx', 'timeout', 'invalid_response'}
)


class SonioxBatchError(ValueError):
    """Fixed message; ``kind`` is a closed class and ``submitted`` says a paid transcription exists.

    The provider-STT failover stage reads both to type the attempt (unbilled refusals do not spend
    the vendor). Bodies, audio and tokens never reach either field.
    """

    def __init__(self, kind: str = 'error', *, submitted: bool = False):
        self.kind = kind if kind in ERROR_KINDS else 'error'
        self.submitted = submitted
        super().__init__('soniox_batch_failed')


def _status_kind(status_code: int) -> str:
    if status_code == 402:
        return 'credit_refusal'  # organization_balance_exhausted (09-19, 09-28)
    if status_code == 429:
        return 'rate_limited'
    if 500 <= status_code <= 599:
        return 'error_5xx'
    return 'error'


def _typed(error: BaseException, submitted: bool) -> SonioxBatchError:
    if isinstance(error, SonioxBatchError):
        return SonioxBatchError(error.kind, submitted=submitted)
    if isinstance(error, (httpx.TimeoutException, TimeoutError)):
        return SonioxBatchError('timeout', submitted=submitted)
    if isinstance(error, (KeyError, TypeError, ValueError)):
        return SonioxBatchError('invalid_response', submitted=submitted)
    return SonioxBatchError('error', submitted=submitted)


def resource_id(value):
    # Never interpolate provider-controlled paths or URLs into an authed request.
    return str(UUID(value))


def transcription_body(file_id, language):
    body: dict[str, object] = {
        'model': MODEL,
        'file_id': file_id,
        'enable_speaker_diarization': True,
        'enable_language_identification': True,
    }
    hint = normalized_stt_language(language)
    if hint and soniox_accepts_language_hint(hint):
        body['language_hints'] = [hint]
        body['language_hints_strict'] = False
    return body


def _bounded_unit(duration):
    return type(duration) in (int, float) and math.isfinite(duration) and 0 < duration <= 7200


def authorization(duration, *, second_chance=False, failover=False):
    # The ordinary second chance is bounded by the admitted unit (max two
    # hours), independently of the guarded path's opt-in one-minute budget.
    # Batch provider-STT failover is bounded the same way, but is admitted by
    # the prerecorded surface and the stage's paid-once attempt record instead.
    if failover:
        admitted = _bounded_unit(duration) and provider_is_enabled('soniox', STTServingSurface.PRERECORDED)
    else:
        admitted = (
            _bounded_unit(duration) and second_multilingual_enabled() if second_chance else allowed(duration)
        ) and provider_is_enabled('soniox', STTServingSurface.HELD_RECOVERY)
    if not admitted:
        raise SonioxBatchError('refused')
    require_provider_environment('soniox')
    return {'Authorization': 'Bearer ' + os.environ['SONIOX_API_KEY']}


def transcript_words(payload, duration, *, mark_fallback=False):
    """Join subword tokens, retaining their original capture-axis timestamps.

    ``mark_fallback`` flags every word ``speaker_fallback`` when any token lacked a
    real vendor speaker, so a caller never treats the default label as diarization.
    """
    if not isinstance(payload, dict) or not isinstance(payload.get('tokens'), list):
        raise SonioxBatchError('invalid_response')
    words, language, previous, boundary, fallback = [], 'multi', -1.0, True, False
    for token in payload['tokens']:
        text = token['text']
        if not isinstance(text, str):
            raise SonioxBatchError('invalid_response')
        if token.get('is_final') is False or token.get('translation_status') == 'translation':
            raise SonioxBatchError('invalid_response')
        if text in {'<end>', '<fin>'} or not text.strip():
            boundary = True
            continue
        start, end = token['start_ms'], token['end_ms']
        if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in (start, end)):
            raise SonioxBatchError('invalid_response')
        start, end = start / 1000, end / 1000
        if not 0 <= start <= end <= duration + 0.01 or start < previous:
            raise SonioxBatchError('invalid_response')
        previous = start
        raw_speaker = token.get('speaker')
        if raw_speaker is not None and (not str(raw_speaker).isdigit() or len(str(raw_speaker)) > 4):
            raise SonioxBatchError('invalid_response')
        fallback = fallback or raw_speaker is None or int(raw_speaker) < 1
        speaker = f'SPEAKER_{max(int(raw_speaker) - 1, 0) if raw_speaker is not None else 0:02d}'
        detected = token.get('language')
        if isinstance(detected, str) and detected:
            language = detected
        if words and not boundary and not text[0].isspace() and words[-1]['speaker'] == speaker:
            words[-1]['text'] += text
            words[-1]['timestamp'][1] = max(end, words[-1]['timestamp'][1])
        else:
            words.append({'text': text.strip(), 'timestamp': [start, end], 'speaker': speaker})
        boundary = text[-1].isspace()
    # A nonempty transcript with missing tokens is malformed, never empty evidence.
    if not isinstance(payload.get('text'), str) or (payload['text'].strip() and not words):
        raise SonioxBatchError('invalid_response')
    if mark_fallback and fallback:
        words = [{**word, 'speaker_fallback': True} for word in words]
    return words, language


def transcribe(
    audio,
    duration,
    *,
    language=None,
    second_chance=False,
    client_factory=httpx.Client,
    clock=time.monotonic,
    sleep=time.sleep,
):
    headers = authorization(duration, second_chance=second_chance)
    file_id, transcription_id = None, None
    deadline = clock() + DEADLINE_SECONDS
    # HTTP transport defaults to zero retries. Each paid POST occurs once.
    with client_factory(headers=headers, timeout=20, follow_redirects=False) as client:

        def request(method, path, **kwargs):
            remaining = deadline - clock()
            if remaining <= 0:
                raise SonioxBatchError()
            response = client.request(method, BASE_URL + path, timeout=min(20, remaining), **kwargs)
            if not 200 <= response.status_code < 300:
                raise SonioxBatchError()
            return response.json()

        try:
            file_id = resource_id(request('POST', '/files', files={'file': ('recovery.wav', audio, 'audio/wav')})['id'])
            body = transcription_body(file_id, language)
            created = request('POST', '/transcriptions', json=body)
            transcription_id = resource_id(created['id'])
            state = created
            for _ in range(60):
                status = state['status']
                if status == 'completed':
                    return transcript_words(request('GET', f'/transcriptions/{transcription_id}/transcript'), duration)
                if status not in {'queued', 'processing'}:
                    raise SonioxBatchError()
                remaining = deadline - clock()
                if remaining <= 0:
                    raise SonioxBatchError()
                sleep(min(2, remaining))
                state = request('GET', f'/transcriptions/{transcription_id}')
            raise SonioxBatchError()
        except Exception:
            # Provider bodies, audio and tokens never become exception messages.
            raise SonioxBatchError() from None
        finally:
            # Remove only this call's temporary vendor resources. Original Omi
            # artifacts stay in custody. Cleanup cannot authorize another POST.
            for path in (
                f'/transcriptions/{transcription_id}' if transcription_id else None,
                f'/files/{file_id}' if file_id else None,
            ):
                if path:
                    try:
                        response = client.request('DELETE', BASE_URL + path, timeout=5)
                        if response.status_code not in {200, 204, 404}:
                            logger.warning('event=soniox_batch_cleanup outcome=failed')
                    except Exception:
                        logger.warning('event=soniox_batch_cleanup outcome=failed')


async def transcribe_async(
    audio,
    duration,
    *,
    language=None,
    second_chance=False,
    failover=False,
    client=None,
    semaphore=None,
    clock=time.monotonic,
    sleep=asyncio.sleep,
    mark_fallback=False,
):
    """Serving path: individual requests borrow a shared async HTTP permit only.

    Failures are typed ``SonioxBatchError`` kinds; ``submitted`` is set once ``POST
    /transcriptions`` left this process without a non-2xx answer (the paid step).
    """
    headers = authorization(duration, second_chance=second_chance, failover=failover)
    client = get_stt_client() if client is None else client
    semaphore = get_stt_semaphore() if semaphore is None else semaphore
    deadline, file_id, transcription_id, submitted = clock() + DEADLINE_SECONDS, None, None, False

    async def request(method, path, **kwargs):
        remaining = deadline - clock()
        if remaining <= 0:
            raise SonioxBatchError('timeout')
        async with asyncio.timeout(remaining):
            async with semaphore:
                remaining = deadline - clock()
                if remaining <= 0:
                    raise SonioxBatchError('timeout')
                response = await client.request(
                    method,
                    BASE_URL + path,
                    headers=headers,
                    timeout=min(20, remaining),
                    follow_redirects=False,
                    **kwargs,
                )
        if not 200 <= response.status_code < 300:
            raise SonioxBatchError(_status_kind(response.status_code))
        return response.json()

    try:
        file_id = resource_id(
            (await request('POST', '/files', files={'file': ('recovery.wav', audio, 'audio/wav')}))['id']
        )
        body = transcription_body(file_id, language)
        try:
            state = await request('POST', '/transcriptions', json=body)
        except SonioxBatchError:
            # A non-2xx answer (or a deadline before sending) created no transcription. Anything
            # else may have reached the vendor: count it as paid.
            raise
        except Exception:
            submitted = True
            raise
        submitted = True
        transcription_id = resource_id(state['id'])
        for _ in range(60):
            if state['status'] == 'completed':
                return transcript_words(
                    await request('GET', f'/transcriptions/{transcription_id}/transcript'),
                    duration,
                    mark_fallback=mark_fallback,
                )
            if state['status'] not in {'queued', 'processing'}:
                raise SonioxBatchError('error_5xx' if state['status'] == 'error' else 'invalid_response')
            remaining = deadline - clock()
            if remaining <= 0:
                raise SonioxBatchError('timeout')
            await sleep(min(2, remaining))
            state = await request('GET', f'/transcriptions/{transcription_id}')
        raise SonioxBatchError('timeout')
    except Exception as error:
        raise _typed(error, submitted) from None
    finally:
        for path in (
            f'/transcriptions/{transcription_id}' if transcription_id else None,
            f'/files/{file_id}' if file_id else None,
        ):
            if path:
                try:
                    async with asyncio.timeout(5):
                        async with semaphore:
                            response = await client.request(
                                'DELETE', BASE_URL + path, headers=headers, timeout=5, follow_redirects=False
                            )
                    if response.status_code not in {200, 204, 404}:
                        logger.warning('event=soniox_batch_cleanup outcome=failed')
                except Exception:
                    logger.warning('event=soniox_batch_cleanup outcome=failed')
