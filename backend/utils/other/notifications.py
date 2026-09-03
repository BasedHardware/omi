# async-blockers: no-import-scope
# async-blockers: no-changed-range-scope  # pre-existing patterns surfaced by type-annotation import changes
import asyncio
import os
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from time import monotonic
from typing import Any, Dict, List, Optional, Tuple

from utils.executors import db_executor, postprocess_executor, run_blocking

import pytz

import database.conversations as conversations_db
import database.notifications as notification_db
from database.redis_db import try_acquire_daily_summary_lock
from models.notification_message import NotificationMessage
from utils.conversations.factory import deserialize_conversation
from utils.llm.external_integrations import generate_comprehensive_daily_summary
from utils.memory.learned_today import memory_review_card_block
from utils.notifications import send_bulk_notification, send_notification
from utils.other import daily_summary_budget as summary_budget
from utils.webhooks import day_summary_webhook
import database.daily_summaries as daily_summaries_db
import logging

logger = logging.getLogger(__name__)


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name) or default)
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name) or default)
    except ValueError:
        return default


# --- Budgets for the daily-summary Cloud Run Job (#12530) --------------------
# The job's Cloud Run task timeout is 600s. Before this, an execution simply ran
# until SIGKILL: whoever sat past the 600s mark was never reached and never
# produced an error attributable to them, so their recap silently vanished.
#
# The job now runs to its own budget (below the task timeout), checkpoints where
# it stopped, and reports what it could not serve.
DAILY_SUMMARY_JOB_BUDGET_SECONDS = _env_float('DAILY_SUMMARY_JOB_BUDGET_SECONDS', 480.0)
# One account cannot own the job. A recap is one LLM call plus Firestore reads;
# 90s is generous for that and still bounds a wedged provider call.
DAILY_SUMMARY_USER_BUDGET_SECONDS = _env_float('DAILY_SUMMARY_USER_BUDGET_SECONDS', 90.0)
# Rendered-character budget for the conversation material fed to the summary
# prompt. ~360k chars is roughly 90k tokens, comfortably inside the 272k-token
# model limit even alongside the prompt scaffolding and the user's memories.
# The overflow seen in production was ~290k tokens of input.
DAILY_SUMMARY_MAX_HISTORY_CHARS = _env_int('DAILY_SUMMARY_MAX_HISTORY_CHARS', 360_000)
# A per-user timeout abandons (it cannot cancel) a worker thread. Stop the run
# once enough threads are abandoned that the pool would starve the rest.
DAILY_SUMMARY_MAX_ABANDONED_USERS = _env_int('DAILY_SUMMARY_MAX_ABANDONED_USERS', 12)

_BATCH_SIZE = 8

_FALLBACK_COMPONENT = 'daily_summary'


def _record_daily_summary_fallback(*, from_mode: str, to_mode: str, reason: str, outcome: str) -> None:
    """Emit the shared fallback counter for a daily-summary fail-open branch.

    Imported lazily so loading this module in a test harness does not drag in
    the Prometheus registry.
    """
    try:
        from utils.observability.fallback import record_fallback

        record_fallback(
            component=_FALLBACK_COMPONENT,
            from_mode=from_mode,
            to_mode=to_mode,
            reason=reason,
            outcome=outcome,
            log=logger,
        )
    except Exception as e:  # telemetry must never break the job
        logger.warning('daily_summary_fallback_record_failed error=%s', e)


@dataclass
class DailySummaryJobStats:
    """Per-execution accounting, emitted as one job-end line."""

    groups_attempted: int = 0
    groups_failed: int = 0
    attempted: int = 0
    succeeded: int = 0
    failed: int = 0
    timed_out: int = 0
    skipped_for_budget: int = 0

    def as_log(self) -> str:
        return (
            f'groups_attempted={self.groups_attempted} groups_failed={self.groups_failed} '
            f'attempted={self.attempted} succeeded={self.succeeded} failed={self.failed} '
            f'timed_out={self.timed_out} skipped_for_budget={self.skipped_for_budget}'
        )


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

    Survivability contract (#12530). This runs as a Cloud Run Job with a hard
    600s task timeout, over tens of thousands of users:

    * **Nothing aborts the whole run.** One hour group's Firestore read or one
      user's provider error is caught where it happens; the run continues.
    * **The run has its own budget**, below the task timeout, so it ends by
      *deciding* to stop rather than by being killed mid-batch.
    * **Progress is checkpointed** in Redis and the next execution rotates the
      work to start at the unfinished tail. Before this, every execution
      restarted at the head and died in the same place, so the users after that
      point were never reached on any run — a permanent, silent tail loss.
    * **The run reports itself**: a structured line per failed user and one
      job-end line with attempted/succeeded/failed/skipped counts.
    """
    deadline = monotonic() + DAILY_SUMMARY_JOB_BUDGET_SECONDS
    stats = DailySummaryJobStats()
    cursor_key = summary_budget.job_cursor_key(datetime.now(pytz.utc))

    try:
        timezones_by_hour = _get_timezones_grouped_by_hour()
    except Exception as e:
        logger.error(f"Error sending daily summary: {e}")
        return None

    cursor = await run_blocking(db_executor, summary_budget.read_job_cursor, cursor_key)
    resume_hour = summary_budget.cursor_hour(cursor)
    resume_uid = summary_budget.cursor_uid(cursor)

    # Deterministic order, rotated to the checkpoint: the tail is served first
    # and the head is still covered in the same pass.
    ordered_hours = summary_budget.rotate_to(sorted(timezones_by_hour.keys()), resume_hour)
    completed_all = True

    for target_hour in ordered_hours:
        if monotonic() >= deadline:
            completed_all = False
            await _checkpoint(cursor_key, target_hour, None)
            _record_daily_summary_fallback(
                from_mode='full_run', to_mode='resumable_tail', reason='timeout', outcome='degraded'
            )
            logger.warning('daily_summary_job_budget_exhausted resume_hour=%s', target_hour)
            break

        stats.groups_attempted += 1
        try:
            users = await _get_users_for_daily_summary(timezones_by_hour[target_hour], target_hour)
        except Exception as e:
            # One hour group's read failing must not cost the other 23 groups.
            stats.groups_failed += 1
            logger.error('daily_summary_group_failed hour=%s reason=user_query error=%s', target_hour, e)
            continue

        if not users:
            continue

        ordered_users = summary_budget.rotate_to(
            sorted(users, key=lambda user: str(user[0])),
            _resume_user(users, resume_uid) if target_hour == resume_hour else None,
        )
        resume_uid = None

        logger.info(f"Sending daily summary to {len(ordered_users)} users at local hour {target_hour}")
        finished_group = await _send_bulk_summary_notification(
            ordered_users, deadline=deadline, stats=stats, target_hour=target_hour, cursor_key=cursor_key
        )
        if not finished_group:
            completed_all = False
            break

    if completed_all:
        await run_blocking(db_executor, summary_budget.clear_job_cursor, cursor_key)

    logger.info('daily_summary_job_summary complete=%s %s', completed_all, stats.as_log())
    return None


def _resume_user(users: List[Tuple[Any, ...]], resume_uid: Optional[str]) -> Optional[Tuple[Any, ...]]:
    """Map a checkpointed uid back onto this run's user tuple, if still present."""
    if not resume_uid:
        return None
    for user in users:
        if str(user[0]) == resume_uid:
            return user
    return None


async def _checkpoint(cursor_key: str, target_hour: Optional[int], uid: Optional[str]) -> None:
    await run_blocking(
        db_executor, summary_budget.write_job_cursor, cursor_key, summary_budget.make_cursor(target_hour, uid)
    )


async def _get_users_for_daily_summary(timezones: List[str], target_hour: int) -> List[Tuple[str, List[str], Any]]:
    timezone_chunks = [timezones[i : i + 30] for i in range(0, len(timezones), 30)]
    # return_exceptions: one failing timezone chunk degrades that chunk's users,
    # it does not throw away the chunks that did read successfully.
    chunk_results = await asyncio.gather(
        *[
            run_blocking(db_executor, notification_db.get_users_for_daily_summary, chunk, target_hour)
            for chunk in timezone_chunks
        ],
        return_exceptions=True,
    )
    users: List[Tuple[str, List[str], Any]] = []
    for chunk_index, chunk in enumerate(chunk_results):
        if isinstance(chunk, BaseException):
            logger.error(
                'daily_summary_user_query_chunk_failed hour=%s chunk=%d error=%s', target_hour, chunk_index, chunk
            )
            continue
        users.extend(chunk)
    return users


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


def _send_summary_notification(user_data: Tuple[Any, ...]) -> None:
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

    # Bound the generator's input (#12530). The summary prompt renders the user's
    # whole day; one account's exceptional day overflowed the model context
    # window (~290k tokens against a 272k limit) and returned a provider 400
    # every single day. Keep the most recent conversations that fit, drop the
    # rest loudly, and always keep at least one so a recap is still attempted.
    bounded = summary_budget.select_conversations_within_budget(conversations, DAILY_SUMMARY_MAX_HISTORY_CHARS)
    if bounded.truncated:
        logger.warning(
            'daily_summary_input_truncated uid=%s date=%s kept=%d dropped=%d rendered_chars=%d',
            uid,
            date_str,
            len(bounded.conversations),
            bounded.dropped,
            bounded.rendered_chars,
        )
        _record_daily_summary_fallback(
            from_mode='full_day', to_mode='truncated_day', reason='quota', outcome='degraded'
        )
    conversations = bounded.conversations

    summary_data = generate_comprehensive_daily_summary(uid, conversations, date_str, start_date_utc, end_date_utc)

    # Store in database
    summary_id = daily_summaries_db.create_daily_summary(uid, summary_data)

    # Create notification with deep link to summary page
    daily_summary_title = f"{summary_data.get('day_emoji', '📅')} {summary_data.get('headline', 'Your Daily Summary')}"
    summary_body = str(summary_data.get('overview') or 'Tap to see your daily summary')

    # Truncate body for notification if too long
    if len(summary_body) > 150:
        summary_body = summary_body[:147] + "..."

    # Native review card for the memories this day produced. The scheduled send is
    # the path users actually receive, so it must carry the same block the
    # /v1/users/daily-summary-settings/test path builds. ``text`` is untouched: a
    # client that does not know the block renders exactly what it rendered before,
    # and the block is omitted entirely when the day produced nothing to review.
    review_block = memory_review_card_block(
        summary_id,
        date=date_str,
        memories_learned=summary_data.get('memories_learned') or [],
    )

    ai_message = NotificationMessage(
        text=summary_body,
        from_integration='false',
        type='day_summary',
        notification_type='daily_summary',
        navigate_to=f"/daily-summary/{summary_id}",
        content_blocks=[review_block] if review_block else None,
    )

    # Also send webhook with the full summary data (day_summary_webhook is async, so wrap in asyncio.run).
    # ``summary`` is the legacy str(...) form, kept for backward compatibility; ``summary_json``
    # carries the same payload as a real JSON object for receivers to migrate to.
    postprocess_executor.submit(asyncio.run, day_summary_webhook(uid, str(summary_data), summary_data))

    tokens = user_data[1] if len(user_data) > 1 else None
    send_notification(
        uid, daily_summary_title, summary_body, NotificationMessage.get_message_as_dict(ai_message), tokens=tokens
    )


async def _send_bulk_summary_notification(
    users: List[Tuple[Any, ...]],
    *,
    deadline: Optional[float] = None,
    stats: Optional[DailySummaryJobStats] = None,
    target_hour: Optional[int] = None,
    cursor_key: Optional[str] = None,
) -> bool:
    """Send one hour group's summaries. Returns True if the whole group was served.

    Isolation is per user, not per batch: a provider error, a context overflow,
    or a wedged call is recorded against that uid and the remaining users in the
    same batch still complete. A user who exceeds the per-user budget is
    abandoned (a worker thread cannot be cancelled) rather than allowed to hold
    the batch barrier for the rest of the run.
    """
    counters = stats if stats is not None else DailySummaryJobStats()

    for i in range(0, len(users), _BATCH_SIZE):
        if deadline is not None and monotonic() >= deadline:
            counters.skipped_for_budget += len(users) - i
            if cursor_key:
                await _checkpoint(cursor_key, target_hour, str(users[i][0]))
            _record_daily_summary_fallback(
                from_mode='full_run', to_mode='resumable_tail', reason='timeout', outcome='degraded'
            )
            logger.warning(
                'daily_summary_group_budget_exhausted hour=%s served=%d deferred=%d resume_uid=%s',
                target_hour,
                i,
                len(users) - i,
                users[i][0],
            )
            return False

        batch = users[i : i + _BATCH_SIZE]
        per_user_timeout = DAILY_SUMMARY_USER_BUDGET_SECONDS
        if deadline is not None:
            per_user_timeout = max(1.0, min(per_user_timeout, deadline - monotonic()))

        tasks = [
            asyncio.wait_for(
                run_blocking(postprocess_executor, _send_summary_notification, user_tokens),
                timeout=per_user_timeout,
            )
            for user_tokens in batch
        ]
        counters.attempted += len(batch)
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for j, result in enumerate(results):
            uid = str(batch[j][0])
            if isinstance(result, (asyncio.TimeoutError, TimeoutError)):
                counters.timed_out += 1
                logger.error(
                    'daily_summary_user_failed uid=%s hour=%s reason=user_budget_exceeded budget_seconds=%s',
                    uid,
                    target_hour,
                    per_user_timeout,
                )
                _record_daily_summary_fallback(
                    from_mode='generated', to_mode='skipped', reason='timeout', outcome='degraded'
                )
            elif isinstance(result, BaseException):
                counters.failed += 1
                logger.error(
                    'daily_summary_user_failed uid=%s hour=%s reason=generation_error error_type=%s error=%s',
                    uid,
                    target_hour,
                    type(result).__name__,
                    result,
                )
            else:
                counters.succeeded += 1

        if cursor_key and i + _BATCH_SIZE < len(users):
            await _checkpoint(cursor_key, target_hour, str(users[i + _BATCH_SIZE][0]))

        if counters.timed_out >= DAILY_SUMMARY_MAX_ABANDONED_USERS:
            # Abandoned threads still occupy postprocess_executor slots. Past this
            # point the pool cannot serve the remaining users any faster than the
            # next execution can, so stop and let the checkpoint carry the tail.
            remaining = max(0, len(users) - (i + _BATCH_SIZE))
            counters.skipped_for_budget += remaining
            logger.error(
                'daily_summary_group_abandoned_users hour=%s timed_out=%d deferred=%d',
                target_hour,
                counters.timed_out,
                remaining,
            )
            _record_daily_summary_fallback(
                from_mode='full_run', to_mode='resumable_tail', reason='capacity_full', outcome='degraded'
            )
            return False

    return True


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
    user_in_time_zone = await _get_users_in_timezone(target_time)
    if not user_in_time_zone:
        logger.info("No users found in time zone")
        return None
    await send_bulk_notification(user_in_time_zone, title, body)
    return user_in_time_zone


async def _get_users_in_timezone(target_time: str) -> Any:
    timezones_in_time = _get_timezones_at_time(target_time)
    timezone_chunks = [timezones_in_time[i : i + 30] for i in range(0, len(timezones_in_time), 30)]
    chunk_results = await asyncio.gather(
        *[run_blocking(db_executor, notification_db.get_users_token_in_timezones, chunk) for chunk in timezone_chunks]
    )
    return [token for chunk in chunk_results for token in chunk]


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
