from datetime import datetime, timezone
from typing import Optional

from database import user_usage as user_usage_db
from database.llm_usage import record_llm_usage_bucket
from database.user_product import normalize_product


def billable_transcription_seconds(
    last_usage_record_timestamp: Optional[float],
    last_audio_received_time: Optional[float],
    current_time: float,
) -> int:
    """Listening seconds to bill since the last usage record, clamped to the last
    audio byte actually received (#4700).

    Client keepalive pings hold the /v4/listen socket open long after the device
    stops sending audio; counting raw wall-clock time then accrues phantom
    listening minutes for hours. No audio streamed also means no STT vendor cost,
    so idle socket time must not be billed.
    """
    if not last_usage_record_timestamp:
        return 0
    billable_until = min(current_time, last_audio_received_time or current_time)
    return max(0, int(billable_until - last_usage_record_timestamp))


# Vendor STT rate used for product-tagged cost buckets (Deepgram Nova reference).
_STT_USD_PER_MINUTE = 0.0043
_CONTEXT_STT_BUCKET = 'context_for_claude_stt'


def record_usage(
    uid: str,
    transcription_seconds: int = 0,
    words_transcribed: int = 0,
    insights_gained: int = 0,
    memories_created: int = 0,
    speech_seconds: int = 0,
    idempotency_key: Optional[str] = None,
    app_product: Optional[str] = None,
):
    """Records hourly usage stats for a user.

    When ``app_product`` is ``context-for-claude``, STT seconds go to the product
    pool field (not the shared Desktop ``transcription_seconds`` counter), and an
    estimated STT ``cost_usd`` is dual-written into the product-tagged llm_usage
    bucket for admin infra-cost segmentation.
    """
    from utils.product_entitlements import CONTEXT_TRANSCRIPTION_SECONDS_FIELD, is_context_for_claude

    now = datetime.now(timezone.utc)
    product = normalize_product(app_product)
    updates = {
        'words_transcribed': words_transcribed,
        'insights_gained': insights_gained,
        'memories_created': memories_created,
        'speech_seconds': speech_seconds,
    }
    if is_context_for_claude(product):
        updates[CONTEXT_TRANSCRIPTION_SECONDS_FIELD] = transcription_seconds
        updates['transcription_seconds'] = 0
    else:
        updates['transcription_seconds'] = transcription_seconds

    if idempotency_key:
        user_usage_db.update_hourly_usage_once(uid, now, updates, idempotency_key)
    else:
        user_usage_db.update_hourly_usage(uid, now, updates)

    if product == 'context-for-claude' and transcription_seconds > 0:
        cost_usd = round((transcription_seconds / 60.0) * _STT_USD_PER_MINUTE, 6)
        record_llm_usage_bucket(
            uid,
            input_tokens=0,
            output_tokens=0,
            total_tokens=0,
            cost_usd=cost_usd,
            bucket=_CONTEXT_STT_BUCKET,
            account='omi',
        )
