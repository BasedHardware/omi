# async-blockers: no-import-scope
# async-blockers: no-changed-range-scope  # pre-existing patterns surfaced by type-annotation import changes
import asyncio
from datetime import datetime, time, timedelta
from typing import Any, Dict, List, Optional, Tuple

from utils.executors import db_executor, postprocess_executor, run_blocking

import pytz

import database.conversations as conversations_db
import database.notifications as notification_db
from database.redis_db import try_acquire_daily_summary_lock
from models.notification_message import NotificationMessage
from utils.conversations.factory import deserialize_conversation
from utils.llm.external_integrations import generate_comprehensive_daily_summary
from utils.notifications import send_bulk_notification, send_notification
from utils.push.base import DISABLED, UNIFIEDPUSH
from utils.push.selector import resolve_push_backend
from utils.webhooks import day_summary_webhook
import database.daily_summaries as daily_summaries_db
import logging

logger = logging.getLogger(__name__)


def should_run_job() -> bool:
    """
    Check if the notification cron job should run.
    Always returns True since we now handle all hours dynamically.
    """
    return True


async def start_cron_job() -> None:
    """
    Main cron job entry point. Runs at the top of every UTC hour.
    """
    logger.info(f'start_cron_job at UTC hour {datetime.now(pytz.utc).hour}')
    await send_daily_notification()
    await send_daily_summary_notification()


async def send_daily_summary_notification() -> None:
    """
    Send daily summary notifications to users based on their local hour preference.

    Groups timezones by their current local hour, then for each hour group,
    queries users in those timezones who have that hour preference.
    """
    try:
        # Group timezones by their current local hour
        timezones_by_hour = _get_timezones_grouped_by_hour()

        # Resolve the delivery backend ONCE here (utils/service layer), not inside the database helper: the
        # DB layer reads persistence but must not own delivery policy (cubic PR 10887 #427 / #3). The DB
        # returns eligible users neutrally; THIS layer picks the recipient reader for the resolved backend
        # and composes the fan-out. Resolving once also records an invalid-backend fallback once, not per
        # user (cubic other/notifications.py:58).
        backend = resolve_push_backend()

        for target_hour, timezones in timezones_by_hour.items():
            # Eligible users (uid, user_data, time_zone) — backend-neutral
            users = await _get_users_for_daily_summary(timezones, target_hour)
            if not users:
                continue
            # Fetch recipients for the resolved backend (UnifiedPush endpoints keyed by uid, or FCM tokens)
            # and shape every eligible user for the sender — including those with NO recipient.
            #
            # The fan-out used to keep only deliverable users, but the per-user path both CREATES the
            # summary (create_daily_summary below) and delivers it, so a user without a recipient never
            # got a summary generated at all and /v1/users/daily-summaries — which the app reads — stayed
            # empty for them. The daily summary is a persisted product artifact; gating its creation on
            # push deliverability is wrong in any posture, and on-prem it is the normal case
            # (PUSH_NOTIFICATION_BACKEND=disabled is first-class, ADR-0011).
            #
            # Delivery for those users is already a safe no-op: _send_to_user returns 0 for DISABLED and
            # for an empty token list, so nothing is sent and nothing fans out to anyone else.
            recipients_by_uid = await _recipients_by_uid(users, timezones, backend)
            fan_out = [(uid, recipients_by_uid.get(uid, []), tz) for uid, _user_data, tz in users]
            if fan_out:
                deliverable = sum(1 for _uid, recipients, _tz in fan_out if recipients)
                logger.info(
                    f"Daily summary for {len(fan_out)} users at local hour {target_hour} "
                    f"({deliverable} with a deliverable recipient, backend={backend})"
                )
                await _send_bulk_summary_notification(fan_out, backend)

    except Exception as e:
        logger.error(f"Error sending daily summary: {e}")
        return None


async def _get_users_for_daily_summary(
    timezones: List[str], target_hour: int
) -> List[Tuple[str, Dict[str, Any], Any]]:  # (uid, user_data, time_zone) — neutral
    timezone_chunks = [timezones[i : i + 30] for i in range(0, len(timezones), 30)]
    chunk_results = await asyncio.gather(
        *[
            run_blocking(db_executor, notification_db.get_users_for_daily_summary, chunk, target_hour)
            for chunk in timezone_chunks
        ]
    )
    return [user for chunk in chunk_results for user in chunk]


async def _recipients_by_uid(
    users: List[Tuple[str, Dict[str, Any], Any]], timezones: List[str], backend: str
) -> Dict[str, List[Any]]:
    """Recipients keyed by uid for the resolved delivery backend — the service-layer delivery-policy
    decision (cubic PR 10887 #427). UnifiedPush: one batched collection-group read by timezone; FCM: the
    users' subcollection tokens + legacy field. Both are neutral DB reads run on the DB worker."""
    if backend == DISABLED:
        # No branch existed for it, so `disabled` fell through to the FCM read below: a full token read,
        # every hour, for a transport that will never deliver. Nothing to fetch, so fetch nothing.
        return {}
    if backend == UNIFIEDPUSH:
        return await run_blocking(db_executor, notification_db.get_unifiedpush_endpoints_by_uid, timezones)
    return await run_blocking(db_executor, notification_db.get_fcm_tokens_for_users, users)


def _get_timezones_grouped_by_hour() -> Dict[int, List[str]]:
    """Group all timezones by their current local hour."""
    timezones_by_hour: Dict[int, List[str]] = {}
    for tz_name in pytz.all_timezones:
        tz = pytz.timezone(tz_name)
        current_hour = datetime.now(tz).hour
        if current_hour not in timezones_by_hour:
            timezones_by_hour[current_hour] = []
        timezones_by_hour[current_hour].append(tz_name)
    return timezones_by_hour


def _send_summary_notification(user_data: Tuple[Any, ...], push_backend: Optional[str] = None) -> None:
    uid = user_data[0]
    user_tz_name = user_data[2] if len(user_data) > 2 else None

    # NOTE: The daily recap is a cross-platform feature delivered by a
    # server-initiated cron that does not know the originating platform.
    # It must NOT be gated on the desktop trial paywall: passing a hardcoded
    # 'macos' to is_trial_paywalled() made the gate trip for any trial-expired
    # user, suppressing their recap on mobile/web too (#9357). The desktop
    # trial only gates desktop features, not the recap the mobile app renders.

    # Calculate local day boundaries for conversation fetching
    # date_str is set based on current hour:
    #   - Before 12 PM (noon): use previous day's date
    #   - 12 PM or after: use current day's date
    start_date_utc = None
    end_date_utc = None
    date_str = None
    if user_tz_name:
        try:
            user_tz = pytz.timezone(user_tz_name)
            now_in_user_tz = datetime.now(user_tz)

            # Determine which calendar day to summarize
            if now_in_user_tz.hour < 12:
                # Before noon: summarize previous day
                display_date = now_in_user_tz.date() - timedelta(days=1)
            else:
                # Noon or after: summarize current day
                display_date = now_in_user_tz.date()

            # Use local day boundaries (midnight-to-midnight) converted to UTC
            start_of_day = user_tz.localize(datetime.combine(display_date, time.min))
            end_of_day = user_tz.localize(datetime.combine(display_date, time.max))
            start_date_utc = start_of_day.astimezone(pytz.utc)
            end_date_utc = end_of_day.astimezone(pytz.utc)
            date_str = display_date.strftime('%Y-%m-%d')
        except Exception as e:
            logger.error(e)

    # Fallback to UTC if timezone not available
    if not start_date_utc or not end_date_utc:
        now_utc = datetime.now(pytz.utc)

        # Determine which calendar day to summarize
        if now_utc.hour < 12:
            display_date = now_utc.date() - timedelta(days=1)
        else:
            display_date = now_utc.date()

        # Use UTC day boundaries
        start_date_utc = datetime.combine(display_date, time.min).replace(tzinfo=pytz.utc)
        end_date_utc = datetime.combine(display_date, time.max).replace(tzinfo=pytz.utc)
        date_str = display_date.strftime('%Y-%m-%d')

    # Atomically acquire lock BEFORE expensive LLM work to prevent race condition
    assert date_str is not None  # set by timezone branch or UTC fallback above
    if not try_acquire_daily_summary_lock(uid, date_str):
        return

    # Durable idempotency guard (#4608): the Redis lock above is best-effort (2h TTL, evictable, lost on
    # failover), and create_daily_summary writes a fresh-uuid doc with no by-date check, so a later cron
    # tick can persist a SECOND summary for the same date. If one already exists, skip before spending
    # any LLM tokens or resending the notification. The regenerate flow stays in-place via update_daily_summary.
    existing_summary = daily_summaries_db.get_daily_summary_by_date(uid, date_str)
    if existing_summary:
        logger.info(
            f"Daily summary already exists for uid={uid} date={date_str} "
            f"id={existing_summary.get('id')}; skipping duplicate generation"
        )
        return

    conversations_data = conversations_db.get_conversations(
        uid, start_date=start_date_utc, end_date=end_date_utc, date_field='started_at'
    )
    if not conversations_data or len(conversations_data) == 0:
        return

    conversations = [
        deserialize_conversation(convo_data) for convo_data in conversations_data if not convo_data.get('is_locked')
    ]
    if not conversations:
        return

    # Skip recap if no conversation captured any speech.
    if not any(c.transcript_segments for c in conversations if not c.discarded):
        logger.info(f'Skipping daily summary for uid={uid} on {date_str}: no conversations with transcript content')
        return

    summary_data = generate_comprehensive_daily_summary(uid, conversations, date_str, start_date_utc, end_date_utc)

    # Store in database
    summary_id = daily_summaries_db.create_daily_summary(uid, summary_data)

    # Create notification with deep link to summary page
    daily_summary_title = f"{summary_data.get('day_emoji', '📅')} {summary_data.get('headline', 'Your Daily Summary')}"
    summary_body = str(summary_data.get('overview') or 'Tap to see your daily summary')

    # Truncate body for notification if too long
    if len(summary_body) > 150:
        summary_body = summary_body[:147] + "..."

    ai_message = NotificationMessage(
        text=summary_body,
        from_integration='false',
        type='day_summary',
        notification_type='daily_summary',
        navigate_to=f"/daily-summary/{summary_id}",
    )

    # Also send webhook with the full summary data (day_summary_webhook is async, so wrap in asyncio.run).
    # ``summary`` is the legacy str(...) form, kept for backward compatibility; ``summary_json``
    # carries the same payload as a real JSON object for receivers to migrate to.
    postprocess_executor.submit(asyncio.run, day_summary_webhook(uid, str(summary_data), summary_data))

    tokens = user_data[1] if len(user_data) > 1 else None
    send_notification(
        uid,
        daily_summary_title,
        summary_body,
        NotificationMessage.get_message_as_dict(ai_message),
        tokens=tokens,
        push_backend=push_backend,
    )


async def _send_bulk_summary_notification(users: List[Tuple[Any, ...]], push_backend: Optional[str] = None) -> None:
    _BATCH_SIZE = 8
    for i in range(0, len(users), _BATCH_SIZE):
        batch = users[i : i + _BATCH_SIZE]
        tasks = [
            run_blocking(postprocess_executor, _send_summary_notification, user_tokens, push_backend)
            for user_tokens in batch
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for j, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"Daily summary failed for user batch[{i + j}]: {result}")


async def send_daily_notification() -> None:
    try:
        morning_alert_title = "omi says"
        morning_alert_body = "Wear your omi and capture your conversations today."
        morning_target_time = "08:00"

        await _send_notification_for_time(morning_target_time, morning_alert_title, morning_alert_body)

    except Exception as e:
        logger.error(e)
        logger.error(f"Error sending message: {e}")
        return None


async def _send_notification_for_time(target_time: str, title: str, body: str) -> Any:
    # Resolve the push backend ONCE per operation and carry it into both the recipient fetch and the
    # dispatch, so a PUSH_NOTIFICATION_BACKEND typo records its fallback once, not twice (review 4939247683).
    backend = resolve_push_backend()
    user_in_time_zone = await _get_users_in_timezone(target_time, backend)
    if not user_in_time_zone:
        logger.info("No users found in time zone")
        return None
    await send_bulk_notification(user_in_time_zone, title, body, push_backend=backend)
    return user_in_time_zone


async def _get_users_in_timezone(target_time: str, backend: str) -> Any:
    timezones_in_time = _get_timezones_at_time(target_time)
    timezone_chunks = [timezones_in_time[i : i + 30] for i in range(0, len(timezones_in_time), 30)]
    # send_bulk_notification treats its list as endpoints in UnifiedPush mode, so gather endpoints (not
    # FCM tokens) as the recipients there — a UnifiedPush deployment has no tokens, so the morning
    # notification would otherwise reach nobody (cubic PR 10887 B2).
    fetch = (
        notification_db.get_users_endpoints_in_timezones
        if backend == UNIFIEDPUSH
        else notification_db.get_users_token_in_timezones
    )
    chunk_results = await asyncio.gather(
        *[run_blocking(db_executor, fetch, chunk) for chunk in timezone_chunks]
    )
    return [recipient for chunk in chunk_results for recipient in chunk]


def _get_timezones_at_time(target_time: str) -> List[str]:
    # Match on the local hour, not an exact "HH:MM" string. The cron runs at the top of
    # each UTC hour, so an exact-string match against "08:00" silently excludes every
    # sub-hour-offset timezone (e.g. India +5:30, Nepal +5:45, Iran +3:30), which read
    # "08:30"/"08:45". This mirrors _get_timezones_grouped_by_hour, which buckets by hour.
    target_hour = int(target_time.split(":")[0])
    target_timezones: List[str] = []
    for tz_name in pytz.all_timezones:
        tz = pytz.timezone(tz_name)
        if datetime.now(tz).hour == target_hour:
            target_timezones.append(tz_name)
    return target_timezones
