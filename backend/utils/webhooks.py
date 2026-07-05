import asyncio
import json
import os
import uuid
from datetime import datetime, timezone
from typing import List, Optional
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from database.redis_db import (
    get_user_webhook_db,
    user_webhook_status_db,
    disable_user_webhook_db,
    enable_user_webhook_db,
    set_user_webhook_db,
)
from database.webhook_health import record_dev_webhook_failure, record_dev_webhook_success, _DEV_FAILURE_THRESHOLD
from models.conversation import Conversation
from models.users import WebhookType
import database.notifications as notification_db
from utils.conversations.render import populate_speaker_names, populate_folder_names
from utils.conversations.render import conversation_to_dict
from utils.executors import db_executor, run_blocking
from utils.http_client import get_webhook_client, get_webhook_circuit_breaker, get_webhook_semaphore
from utils.notifications import send_notification
import logging

logger = logging.getLogger(__name__)

_DEV_WEBHOOK_RETRY_DELAYS = (1.0, 5.0, 30.0)


def _get_dev_webhook_retry_delays() -> tuple[float, ...]:
    raw_delays = os.getenv('DEV_WEBHOOK_RETRY_DELAYS')
    if raw_delays is None:
        return _DEV_WEBHOOK_RETRY_DELAYS
    try:
        return tuple(float(delay.strip()) for delay in raw_delays.split(',') if delay.strip())
    except ValueError:
        logger.warning(f'Invalid DEV_WEBHOOK_RETRY_DELAYS={raw_delays!r}; using default schedule')
        return _DEV_WEBHOOK_RETRY_DELAYS


def _append_query_params(url: str, params: dict) -> str:
    parts = urlsplit(url)
    param_keys = {key for key, value in params.items() if value is not None}
    query_items = [
        (key, value) for key, value in parse_qsl(parts.query, keep_blank_values=True) if key not in param_keys
    ]
    query_items.extend((key, str(value)) for key, value in params.items() if value is not None)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query_items), parts.fragment))


async def _post_dev_webhook(
    webhook_name: str,
    webhook_url: str,
    *,
    retry_delays: Optional[tuple[float, ...]] = None,
    idempotency_key: Optional[str] = None,
    **request_kwargs,
):
    if retry_delays is None:
        retry_delays = _get_dev_webhook_retry_delays()

    headers = dict(request_kwargs.pop('headers', {}) or {})
    headers.setdefault('Idempotency-Key', idempotency_key or str(uuid.uuid4()))
    request_kwargs['headers'] = headers

    client = get_webhook_client()
    attempts = len(retry_delays) + 1
    last_response = None
    last_exception = None

    for attempt_index in range(attempts):
        attempt_number = attempt_index + 1
        failure_reason = None
        try:
            async with get_webhook_semaphore():
                response = await client.post(webhook_url, **request_kwargs)
            last_response = response
            last_exception = None
            if 200 <= response.status_code < 300:
                logger.info(
                    f'{webhook_name}: delivery succeeded status={response.status_code} '
                    f'attempt={attempt_number}/{attempts} url={webhook_url}'
                )
                return response
            failure_reason = f'HTTP {response.status_code}'
        except Exception as e:
            last_response = None
            last_exception = e
            failure_reason = type(e).__name__

        if attempt_index < len(retry_delays):
            delay = retry_delays[attempt_index]
            logger.warning(
                f'{webhook_name}: delivery failed reason={failure_reason} '
                f'attempt={attempt_number}/{attempts}; retrying in {delay:g}s'
            )
            await asyncio.sleep(delay)

    if last_response is not None:
        logger.error(
            f'{webhook_name}: delivery failed status={last_response.status_code} attempts={attempts} url={webhook_url}'
        )
        return last_response

    if last_exception is None:
        raise RuntimeError(f'{webhook_name}: delivery failed without a response or exception')
    logger.error(f'{webhook_name}: delivery failed error={type(last_exception).__name__} attempts={attempts}')
    raise last_exception


async def _handle_dev_webhook_disable(uid: str, wtype: str, should_disable: bool):
    if should_disable:
        logger.warning(
            f'Dev webhook auto-disabled: uid={uid} type={wtype} after {_DEV_FAILURE_THRESHOLD} consecutive failures'
        )
        await run_blocking(db_executor, disable_user_webhook_db, uid, wtype)
        wtype_str = wtype.value if hasattr(wtype, 'value') else str(wtype)
        await run_blocking(
            db_executor,
            send_notification,
            uid,
            'Developer Webhook Auto-Disabled',
            f'Your {wtype_str} webhook has been auto-disabled after {_DEV_FAILURE_THRESHOLD} consecutive failures. '
            'Please fix your endpoint and re-enable it from developer settings.',
        )


def _build_conversation_webhook_payload_sync(uid: str, memory: Conversation) -> dict:
    payload = conversation_to_dict(memory)
    populate_speaker_names(uid, [payload])
    populate_folder_names(uid, [payload])
    return payload


async def conversation_created_webhook(uid, memory: Conversation):
    if memory.is_locked:
        return

    toggled = await run_blocking(db_executor, user_webhook_status_db, uid, WebhookType.memory_created)

    if toggled:
        webhook_url = await run_blocking(db_executor, get_user_webhook_db, uid, WebhookType.memory_created)
        if not webhook_url:
            return
        webhook_url = _append_query_params(webhook_url, {'uid': uid})
        cb = get_webhook_circuit_breaker(webhook_url)
        if not cb.allow_request():
            logger.info(f'memory_created_webhook: circuit breaker open for {webhook_url[:80]}')
            return
        try:
            payload = await run_blocking(db_executor, _build_conversation_webhook_payload_sync, uid, memory)
            response = await _post_dev_webhook(
                'memory_created_webhook',
                webhook_url,
                json=payload,
                headers={'Content-Type': 'application/json'},
            )
            if response.status_code >= 200 and response.status_code < 300:
                cb.record_success()
                await run_blocking(db_executor, record_dev_webhook_success, uid, WebhookType.memory_created)
            else:
                cb.record_failure()
                should_disable = await run_blocking(
                    db_executor,
                    record_dev_webhook_failure,
                    uid,
                    WebhookType.memory_created,
                    response.status_code,
                    f'HTTP {response.status_code}',
                )
                await _handle_dev_webhook_disable(uid, WebhookType.memory_created, should_disable)
        except Exception as e:
            cb.record_failure()
            should_disable = await run_blocking(
                db_executor, record_dev_webhook_failure, uid, WebhookType.memory_created, 0, type(e).__name__
            )
            await _handle_dev_webhook_disable(uid, WebhookType.memory_created, should_disable)
            logger.error(f"Error sending memory created to developer webhook: {e}")
    else:
        return


async def day_summary_webhook(uid, summary: str, summary_json: Optional[dict] = None):
    """Send the daily summary to the developer webhook.

    ``summary`` is the legacy ``str(summary_data)`` Python repr field, kept
    for backward compatibility. ``summary_json`` is the same payload as a
    real JSON object — receivers should prefer it going forward; the
    legacy ``summary`` field will be deprecated in a future release.
    """
    toggled = await run_blocking(db_executor, user_webhook_status_db, uid, WebhookType.day_summary)
    if toggled:
        webhook_url = await run_blocking(db_executor, get_user_webhook_db, uid, WebhookType.day_summary)
        if not webhook_url:
            return
        webhook_url = _append_query_params(webhook_url, {'uid': uid})
        cb = get_webhook_circuit_breaker(webhook_url)
        if not cb.allow_request():
            logger.info(f'day_summary_webhook: circuit breaker open for {webhook_url[:80]}')
            return
        try:
            response = await _post_dev_webhook(
                'day_summary_webhook',
                webhook_url,
                json={
                    'summary': summary,
                    'summary_json': summary_json,
                    'uid': uid,
                    'created_at': datetime.now(timezone.utc).isoformat(),
                },
                headers={'Content-Type': 'application/json'},
            )
            if response.status_code >= 200 and response.status_code < 300:
                cb.record_success()
                await run_blocking(db_executor, record_dev_webhook_success, uid, WebhookType.day_summary)
            else:
                cb.record_failure()
                should_disable = await run_blocking(
                    db_executor,
                    record_dev_webhook_failure,
                    uid,
                    WebhookType.day_summary,
                    response.status_code,
                    f'HTTP {response.status_code}',
                )
                await _handle_dev_webhook_disable(uid, WebhookType.day_summary, should_disable)
        except Exception as e:
            cb.record_failure()
            should_disable = await run_blocking(
                db_executor, record_dev_webhook_failure, uid, WebhookType.day_summary, 0, type(e).__name__
            )
            await _handle_dev_webhook_disable(uid, WebhookType.day_summary, should_disable)
            logger.error(f"Error sending day summary to developer webhook: {e}")
    else:
        return


async def realtime_transcript_webhook(uid, segments: List[dict]):
    logger.info(f"realtime_transcript_webhook {uid}")
    toggled = await run_blocking(db_executor, user_webhook_status_db, uid, WebhookType.realtime_transcript)

    if toggled:
        webhook_url = await run_blocking(db_executor, get_user_webhook_db, uid, WebhookType.realtime_transcript)
        if not webhook_url:
            return
        webhook_url = _append_query_params(webhook_url, {'uid': uid})
        cb = get_webhook_circuit_breaker(webhook_url)
        if not cb.allow_request():
            logger.info(f'realtime_transcript_webhook: circuit breaker open for {webhook_url[:80]}')
            return
        try:
            response = await _post_dev_webhook(
                'realtime_transcript_webhook',
                webhook_url,
                json={'segments': segments, 'session_id': uid},
                headers={'Content-Type': 'application/json'},
            )
            if response.status_code >= 200 and response.status_code < 300:
                cb.record_success()
                await run_blocking(db_executor, record_dev_webhook_success, uid, WebhookType.realtime_transcript)
                try:
                    if response.status_code == 200:
                        response_data = response.json()
                        if not response_data:
                            return
                        message = response_data.get('message', '')
                        if len(message) > 5:
                            await run_blocking(db_executor, send_webhook_notification, uid, message)
                except Exception:
                    pass
            else:
                cb.record_failure()
                should_disable = await run_blocking(
                    db_executor,
                    record_dev_webhook_failure,
                    uid,
                    WebhookType.realtime_transcript,
                    response.status_code,
                    f'HTTP {response.status_code}',
                )
                await _handle_dev_webhook_disable(uid, WebhookType.realtime_transcript, should_disable)
        except Exception as e:
            cb.record_failure()
            should_disable = await run_blocking(
                db_executor, record_dev_webhook_failure, uid, WebhookType.realtime_transcript, 0, type(e).__name__
            )
            await _handle_dev_webhook_disable(uid, WebhookType.realtime_transcript, should_disable)
            logger.error(f"Error sending realtime transcript to developer webhook: {e}")
    else:
        return


def get_audio_bytes_webhook_seconds(uid: str):
    toggled = user_webhook_status_db(uid, WebhookType.audio_bytes)
    if toggled:
        webhook_url = get_user_webhook_db(uid, WebhookType.audio_bytes)
        if not webhook_url:
            return
        parts = webhook_url.split(',')
        if len(parts) == 2:
            try:
                return int(parts[1])
            except ValueError:
                pass
        return 5
    else:
        return


async def send_audio_bytes_developer_webhook(uid: str, sample_rate: int, data: bytearray):
    logger.info(f"send_audio_bytes_developer_webhook {uid}")
    # TODO: add a lock, send shorter segments, validate regex.
    toggled = await run_blocking(db_executor, user_webhook_status_db, uid, WebhookType.audio_bytes)
    if toggled:
        webhook_url = await run_blocking(db_executor, get_user_webhook_db, uid, WebhookType.audio_bytes)
        if not webhook_url:
            return
        webhook_url = webhook_url.split(',')[0]
        if not webhook_url:
            return
        webhook_url = _append_query_params(webhook_url, {'sample_rate': sample_rate, 'uid': uid})
        cb = get_webhook_circuit_breaker(webhook_url)
        if not cb.allow_request():
            logger.info(f'send_audio_bytes_developer_webhook: circuit breaker open for {webhook_url[:80]}')
            return
        try:
            response = await _post_dev_webhook(
                'send_audio_bytes_developer_webhook',
                webhook_url,
                content=bytes(data),
                headers={'Content-Type': 'application/octet-stream'},
            )
            if response.status_code >= 200 and response.status_code < 300:
                cb.record_success()
                await run_blocking(db_executor, record_dev_webhook_success, uid, WebhookType.audio_bytes)
            else:
                cb.record_failure()
                should_disable = await run_blocking(
                    db_executor,
                    record_dev_webhook_failure,
                    uid,
                    WebhookType.audio_bytes,
                    response.status_code,
                    f'HTTP {response.status_code}',
                )
                await _handle_dev_webhook_disable(uid, WebhookType.audio_bytes, should_disable)
        except Exception as e:
            cb.record_failure()
            should_disable = await run_blocking(
                db_executor, record_dev_webhook_failure, uid, WebhookType.audio_bytes, 0, type(e).__name__
            )
            await _handle_dev_webhook_disable(uid, WebhookType.audio_bytes, should_disable)
            logger.error(f"Error sending audio bytes to developer webhook: {e}")
    else:
        return


def webhook_first_time_setup(uid: str, wType: WebhookType) -> bool:
    res = False
    url = get_user_webhook_db(uid, wType)
    if url == '' or url == ',':
        disable_user_webhook_db(uid, wType)
        res = False
    else:
        enable_user_webhook_db(uid, wType)
        res = True
    return res


def send_webhook_notification(user_id: str, message: str):
    send_notification(user_id, "Webhook" + ' says', message)
