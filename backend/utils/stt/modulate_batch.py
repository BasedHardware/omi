"""Velma batch transcription: the async client the provider stage awaits.

Velma batch has no job/poll/webhook mode (docs.modulate.ai: the transcript is the HTTP response),
so ``modulate_batch_async`` holds a socket for the transcription, never an executor thread. The
2xx body is parsed by ``utils.stt.pre_recorded.modulate_batch_words``, as the sync client does.
"""

from io import BytesIO
import os
import wave
from typing import Any, Dict, List, Optional, Tuple, cast

import httpx

from config.prerecorded_stt import PrerecordedSTTService, require_provider_environment
from config.prerecorded_vendor import vendor_fail_fast_enabled
from utils.stt.stream_close import MODULATE_BUDGET_MARKERS
from utils.stt.vendor_guard import (
    ENDPOINT_STT,
    breaker_allows,
    breaker_budget_exhausted,
    record_breaker_other_failure,
    record_breaker_quota_error,
    record_breaker_success,
    record_vendor_burn,
)

MODULATE_TIMEOUT = httpx.Timeout(connect=10.0, read=300.0, write=30.0, pool=10.0)


def wav_duration_seconds(audio_bytes: bytes) -> float:
    """Cheap WAV-header duration for burn accounting; unparseable audio is 0 seconds."""
    try:
        with wave.open(BytesIO(audio_bytes)) as source:
            rate = source.getframerate()
            return source.getnframes() / rate if rate > 0 else 0.0
    except Exception:
        return 0.0


def modulate_budget_refusal(status_code: int, body: str) -> bool:
    """True when Velma's batch answer is account-budget, not a transient error.

    402 is credits regardless of wording; 429 is budget only when the body
    carries a budget marker such as "insufficient credits" — the answer
    Velma-2 gives when the account is out of credits (2026-10-22 outage: sync
    jobs recorded it as a retryable upstream_error under provider=unknown).
    The body is matched, never logged or labeled.
    """

    if status_code == 402:
        return True
    return status_code == 429 and any(marker in body.lower() for marker in MODULATE_BUDGET_MARKERS)


MODULATE_BATCH_URL = 'https://modulate-developer-apis.com/api/velma-2-stt-batch'
MODULATE_BATCH_ERROR_KINDS = frozenset(
    {'error', 'breaker_open', 'credit_refusal', 'rate_limited', 'error_5xx', 'timeout', 'invalid_response'}
)


class ModulateBatchError(RuntimeError):
    """Fixed message; ``kind`` is closed and ``posted`` says the POST left this process.

    Bodies, audio and keys never reach either field (the provider stage types attempts from them).
    """

    def __init__(self, kind: str = 'error', *, posted: bool = False):
        self.kind = kind if kind in MODULATE_BATCH_ERROR_KINDS else 'error'
        self.posted = posted
        super().__init__('modulate_batch_failed')


async def modulate_batch_async(
    audio_bytes: bytes, *, language: Optional[str] = None, diarize: bool = True, client: Any = None
) -> Tuple[List[Dict[str, Any]], str]:
    """One Velma batch POST awaited on the event loop: no executor thread held, no client retry.

    Velma batch has no job/poll/webhook mode (docs.modulate.ai: the transcript is the HTTP
    response), so a call necessarily stays open for the transcription; awaiting it costs a socket,
    not a thread, and instance time is shared by every concurrent call on the instance. Breaker
    and burn accounting match ``modulate_prerecorded_from_bytes`` with ``attempts=2`` exactly.
    """
    from utils.http_client import get_batch_vendor_client
    from utils.stt.pre_recorded import modulate_batch_words

    require_provider_environment(PrerecordedSTTService.MODULATE)
    api_key = os.environ['MODULATE_API_KEY']
    fail_fast = vendor_fail_fast_enabled()
    if fail_fast and not breaker_allows(ENDPOINT_STT):
        raise ModulateBatchError('credit_refusal' if breaker_budget_exhausted(ENDPOINT_STT) else 'breaker_open')
    client = get_batch_vendor_client() if client is None else client
    burn_seconds = wav_duration_seconds(audio_bytes)
    try:
        response = await client.post(
            MODULATE_BATCH_URL,
            headers={'X-API-Key': api_key},
            files={'upload_file': ('audio.wav', BytesIO(audio_bytes), 'audio/wav')},
            data={'speaker_diarization': str(diarize).lower()},
            timeout=MODULATE_TIMEOUT,
        )
    except Exception as error:
        record_vendor_burn(ENDPOINT_STT, 'error', burn_seconds)
        if fail_fast:
            record_breaker_other_failure(ENDPOINT_STT)
        kind = 'timeout' if isinstance(error, (httpx.TimeoutException, TimeoutError)) else 'error'
        raise ModulateBatchError(kind, posted=True) from None
    status = response.status_code
    if not 200 <= status < 300:
        record_vendor_burn(ENDPOINT_STT, 'error', burn_seconds)
        budget = modulate_budget_refusal(status, response.text)
        if budget or status in (401, 403):
            # Account state, not a transient: the vendor declined before processing.
            if fail_fast:
                record_breaker_quota_error(ENDPOINT_STT, budget=budget)
            raise ModulateBatchError('credit_refusal', posted=True)
        if fail_fast:
            record_breaker_other_failure(ENDPOINT_STT)
        if status == 429:
            raise ModulateBatchError('rate_limited', posted=True)
        raise ModulateBatchError('error_5xx' if status >= 500 else 'error', posted=True)
    if fail_fast:
        record_breaker_success(ENDPOINT_STT)
    record_vendor_burn(ENDPOINT_STT, 'ok', burn_seconds)
    try:
        return cast(Tuple[List[Dict[str, Any]], str], modulate_batch_words(response.json(), True, language))
    except Exception:
        raise ModulateBatchError('invalid_response', posted=True) from None
