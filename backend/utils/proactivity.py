"""Server-only composition boundary for v2 producers and delivery."""

from __future__ import annotations

import json
import logging
from typing import Any
from uuid import NAMESPACE_URL, uuid5
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


from config.proactivity_v2 import ProactivityDenied, daily_cap, active_plan, producer_for, utc_now
from database import proactivity as ledger
from database import proactivity_redis, redis_db
from utils import proactivity_flags
from models.proactivity import ProactivityFeedItem, ProactivityTarget
from utils.executors import db_executor, run_blocking
from utils.notification_dispatch import NotificationIntent, NotificationKind, dispatch_notification_async
from utils.observability.fallback import record_fallback

logger = logging.getLogger(__name__)


def _admit(uid: str, producer: str) -> None:
    producer_for(producer)
    if not proactivity_flags.enabled(uid):
        raise ProactivityDenied('disabled')
    client = ledger.client_or_default()
    user, _ = ledger.read_owner(client, uid)
    if producer == 'conversation_mentor_v2':
        if proactivity_flags.mentor_pipeline(uid) != 'v2' or user.get('mentor_notification_frequency', 0) <= 0:
            raise ProactivityDenied('disabled')
    cap, pending = daily_cap(active_plan(user, utc_now()))
    if pending:
        record_fallback(
            component='other',
            from_mode='plan_price',
            to_mode='lowest_known_paid_cap',
            reason='price_pending',
            outcome='recovered',
            log=logger,
        )
    if cap <= 0:
        raise ProactivityDenied('not_paid')
    ledger.refresh_health(producer, firestore_client=client)


async def ensure_admitted(uid: str, producer: str) -> None:
    try:
        await run_blocking(db_executor, _admit, uid, producer)
    except ProactivityDenied as exc:
        logger.info('proactivity_v2_admission producer=%s result=denied reason=%s', producer, exc.reason)
        raise
    except Exception:
        logger.info('proactivity_v2_admission producer=%s result=denied reason=unavailable', producer)
        raise
    logger.info('proactivity_v2_admission producer=%s result=admitted', producer)


async def claim_item(*, uid: str, producer: str, source: dict[str, str]) -> dict[str, Any]:
    await ensure_admitted(uid, producer)
    item = await run_blocking(
        db_executor,
        ledger.claim_item,
        uid=uid,
        producer=producer,
        source_kind=source['source_kind'],
        source_id=source['source_id'],
        source_revision=source['source_revision'],
        source_event_id=source['source_event_id'],
        source_surface=source.get('source_surface', 'server'),
    )
    return dict(item, uid=uid)


async def run_proactivity_model(*, item: dict[str, Any], step: str, request: dict[str, Any]) -> dict[str, Any]:
    from utils.llm.gateway_client import run_proactivity_gateway

    await ensure_admitted(item['uid'], item['producer'])
    # Each named producer step is a unique invocation; retries reuse its identity.
    call_id = str(uuid5(NAMESPACE_URL, f"proactivity:{item['item_id']}:{step}"))
    return await run_proactivity_gateway(
        uid=item['uid'], item_id=item['item_id'], producer=item['producer'], call_id=call_id, step=step, request=request
    )


async def publish_item(
    *,
    item: dict[str, Any],
    content: dict[str, str],
    target: ProactivityTarget,
    source_guard: dict[str, Any] | None = None,
) -> None:
    # Content encryption belongs to backend publish/feed hosts. Admission at
    # the gateway must not require their encryption secret.
    from utils.encryption import encrypt

    uid = item['uid']
    await ensure_admitted(uid, item['producer'])
    if target.kind != item['source_kind'] or target.id != item['source_id']:
        raise ProactivityDenied('invalid_target')
    wire = ProactivityFeedItem(
        id=item['item_id'],
        producer=item['producer'],
        created_at=item['created_at'],
        title=content['title'],
        body=content['body'],
        target=target,
        acted=False,
        dismissed=False,
        feedback='none',
    )
    ciphertext = encrypt(json.dumps(dict(title=wire.title, body=wire.body, target=target.model_dump())), uid)
    await run_blocking(
        db_executor,
        ledger.publish_item,
        uid=uid,
        item_id=item['item_id'],
        claim_token=item['claim_token'],
        encrypted_content=ciphertext,
        source_guard=source_guard,
    )
    logger.info('proactivity_v2_item_terminal producer=%s state=ready', item['producer'])


async def record_mentor_chat(*, item: dict[str, Any], status: str, message_id: str = '') -> None:
    await run_blocking(
        db_executor,
        ledger.record_mentor_chat,
        uid=item['uid'],
        item_id=item['item_id'],
        claim_token=item['claim_token'],
        status=status,
        message_id=message_id,
    )


async def record_usefulness_score(*, item: dict[str, Any], score: float) -> None:
    await run_blocking(
        db_executor,
        ledger.record_usefulness_score,
        uid=item['uid'],
        item_id=item['item_id'],
        claim_token=item['claim_token'],
        score=score,
    )


async def close_item(*, item: dict[str, Any], state: str, reason: str = '') -> None:
    # The reason vocabulary is kept content-free at this boundary.
    if reason not in {
        '',
        'model_silent',
        'generation_failed',
        'rollout_disabled',
        'source_deleted',
        'duplicate',
        'safety_escalation',
        'source_changed',
        'usefulness_judge',
    }:
        raise ValueError('invalid terminal reason')
    await run_blocking(
        db_executor,
        ledger.publish_item,
        uid=item['uid'],
        item_id=item['item_id'],
        claim_token=item['claim_token'],
        state=state,
        reason=reason,
    )

    logger.info('proactivity_v2_item_terminal producer=%s state=%s reason=%s', item['producer'], state, reason)


def decode_feed_item(uid: str, item: dict[str, Any]) -> ProactivityFeedItem:
    from utils.encryption import decrypt

    content = json.loads(decrypt(item['content'], uid))
    events = item['outcomes']
    feedback = 'thumbs_down' if 'thumbs_down' in events else 'thumbs_up' if 'thumbs_up' in events else 'none'
    return ProactivityFeedItem(
        id=item['item_id'],
        producer=item['producer'],
        created_at=item['created_at'],
        acted=item['acted_24h'],
        dismissed=item['dismissed'],
        feedback=feedback,
        **content,
    )


def _push_preferences(uid: str) -> None:
    user, _ = ledger.read_owner(ledger.client_or_default(), uid)
    if user.get('notifications_enabled') is False:
        raise ProactivityDenied('notifications_disabled')
    # Local quiet hours are a conservative interruption policy, separate from UTC money days.
    try:
        local = utc_now().astimezone(ZoneInfo(user['time_zone']))
    except (KeyError, ZoneInfoNotFoundError, TypeError) as exc:
        raise ProactivityDenied('quiet_hours_unknown') from exc
    if local.hour < 8 or local.hour >= 22:
        raise ProactivityDenied('quiet_hours')


def push_payload(item: dict[str, Any]) -> dict[str, str]:
    data = {
        'notification_type': 'proactivity_v2',
        'item_id': item['item_id'],
        'target_kind': item['source_kind'],
        'target_id': item['source_id'],
    }
    if item['producer'] == 'conversation_mentor_v2':
        data['navigate_to'] = '/chat/mentor'
    return data


def _publish_listen_wakeup(uid: str, payload: dict[str, str]) -> None:
    try:
        proactivity_redis.get_client().publish(redis_db.PROACTIVE_MESSAGE_CHANNEL, json.dumps(dict(payload, uid=uid)))
    except Exception:
        # Feed polling and FCM remain available; a wakeup is never exposure.
        record_fallback(
            component='other',
            from_mode='proactivity_listen',
            to_mode='feed_poll',
            reason='enqueue_failed',
            outcome='degraded',
            log=logger,
        )


async def push_item(*, item: dict[str, Any]) -> None:
    uid, producer = item['uid'], item['producer']
    await ensure_admitted(uid, producer)
    await run_blocking(db_executor, _push_preferences, uid)
    claimed = await run_blocking(db_executor, ledger.claim_push, uid=uid, item_id=item['item_id'])
    try:
        await ensure_admitted(uid, producer)
        await run_blocking(db_executor, _push_preferences, uid)
        await run_blocking(db_executor, ledger.validate_push, uid=uid, item_id=item['item_id'])
        await run_blocking(db_executor, _publish_listen_wakeup, uid, push_payload(claimed))
        outcome = await dispatch_notification_async(
            NotificationIntent(
                user_id=uid,
                title='Omi',
                body='You have a new update',
                source=producer,
                kind=NotificationKind.PROACTIVITY_V2,
                data=push_payload(claimed),
            )
        )
        status = 'accepted' if outcome.delivered and outcome.delivered > 0 else 'failed'
    except ProactivityDenied:
        status = 'suppressed'
    except Exception:
        status = 'unknown'
    await run_blocking(db_executor, ledger.finish_push, uid=uid, item_id=item['item_id'], status=status)
    logger.info('proactivity_v2_push_terminal producer=%s status=%s', producer, status)


async def record_server_outcome(item_id: str, action: str, *, uid: str) -> dict[str, Any]:
    return await run_blocking(db_executor, ledger.record_server_outcome, item_id, action, uid=uid)
