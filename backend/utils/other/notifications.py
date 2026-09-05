# async-blockers: no-import-scope
# async-blockers: no-changed-range-scope  # pre-existing patterns surfaced by type-annotation import changes
import asyncio
import os
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from time import monotonic
from typing import Any, Dict, List, Optional, Tuple

import pytz

import database.conversations as conversations_db
from database.durable_queue import ProcessOutcome, drain_isolated_async
import database.notifications as notification_db
from database.redis_db import release_daily_summary_lock, try_acquire_daily_summary_lock
from models.notification_message import NotificationMessage
from utils.conversations.factory import deserialize_conversation
from utils.executors import db_executor, postprocess_executor, run_blocking
from utils.llm.external_integrations import generate_comprehensive_daily_summary
from utils.memory.learned_today import memories_learned_payload, memory_review_card_block
from utils.notifications import send_bulk_notification, send_notification
from utils.other import daily_summary_budget as summary_budget
from utils.webhooks import day_summary_webhook
import database.daily_summaries as daily_summaries_db
import logging

logger = logging.getLogger(__name__)

# How far the hourly tick walks back to fill a missed day. A missed tick (deploy,
# swallowed per-chunk Firestore exception) used to mean that day was never summarized.
_DAILY_SUMMARY_BACKFILL_DAYS = 7
# One user's ten-day hole must not stall the batch: stop after this many *new*
# generations per tick (the current day is separate and always attempted).
_DAILY_SUMMARY_BACKFILL_GENERATE_CAP = 3


def local_day_bounds_utc(display_date, tz_name: Optional[str]):
    """Midnight-to-midnight of ``display_date`` in the user's timezone, as UTC datetimes.

    Same conversion the cron uses. An unusable timezone name falls back to UTC.
    """
    if tz_name:
        try:
            user_tz = pytz.timezone(tz_name)
            start_of_day = user_tz.localize(datetime.combine(display_date, time.min))
            end_of_day = user_tz.localize(datetime.combine(display_date, time.max))
            return start_of_day.astimezone(pytz.utc), end_of_day.astimezone(pytz.utc)
        except Exception as e:
            logger.error(e)
    start_date_utc = datetime.combine(display_date, time.min).replace(tzinfo=pytz.utc)
    end_date_utc = datetime.combine(display_date, time.max).replace(tzinfo=pytz.utc)
    return start_date_utc, end_date_utc


def _display_date_for_now(tz_name: Optional[str]):
    """Calendar day the cron summarizes at this instant (noon split, then UTC fallback)."""
    if tz_name:
        try:
            user_tz = pytz.timezone(tz_name)
            now_in_user_tz = datetime.now(user_tz)
            if now_in_user_tz.hour < 12:
                return now_in_user_tz.date() - timedelta(days=1)
            return now_in_user_tz.date()
        except Exception as e:
            logger.error(e)
    now_utc = datetime.now(pytz.utc)
    if now_utc.hour < 12:
        return now_utc.date() - timedelta(days=1)
    return now_utc.date()


# Why one day's generation declined. The tick needs this to decide whether walking back is
# worth anything: another worker already owns this user (``locked``), or the owner recorded
# nothing at all (``no_conversations``), and in both cases the backfill would only spend
# queries on holes it cannot fill.
_DECLINE_LOCKED = 'locked'
_DECLINE_NO_CONVERSATIONS = 'no_conversations'
# The window held conversations, but none this job may summarize (all ``is_locked``, none
# carried transcript content, or nothing carried summary body content — titles alone).
# Distinct from ``no_conversations`` because the owner *was*
# active: their earlier days are worth walking back for, and the caller may say so.
_DECLINE_NOTHING_TO_SUMMARIZE = 'nothing_to_summarize'
# Public name for the one decline a caller outside this module has to act on differently.
DAILY_SUMMARY_DECLINE_LOCKED = _DECLINE_LOCKED


def _conversation_has_summary_content(conversation: Any) -> bool:
    """True when the recap renderer would show more than this conversation's title.

    Reads the content fields ``conversations_to_string(use_transcript=False)``
    renders as the body — the first app result's content when one exists, else
    the structured overview, plus ``structured.action_items`` and
    ``structured.events`` — so the pre-LLM decline guard cannot drift from
    what the model would actually see.

    Attendee names are rendered too, but deliberately do not count: they are
    presence labels attached to the conversation, not summary content, and a
    day that renders as titles plus a list of names is still the degenerate
    F-12 shape this gate exists to decline.
    """
    apps_results = getattr(conversation, 'apps_results', None) or []
    if apps_results:
        content = getattr(apps_results[0], 'content', None)
        if content and content.strip():
            return True
    structured = getattr(conversation, 'structured', None)
    overview = getattr(structured, 'overview', None)
    if overview and overview.strip():
        return True
    if getattr(structured, 'action_items', None):
        return True
    return bool(getattr(structured, 'events', None))


def generate_and_store_daily_summary(uid, date_str, start_date_utc, end_date_utc) -> Optional[dict]:
    """Generate one day's summary, or return the one already stored.

    Guard order is the existing contract and must not be reordered:

    1. best-effort Redis lock
    2. durable by-date idempotency (existing record → return it, no LLM)
    3. conversations exist in the window and are not ``is_locked``
    4. at least one non-discarded conversation has ``transcript_segments``
    5. the bounded day carries more than titles for the prompt: some
       conversation has a non-empty ``structured.overview``, a first app
       result, action items, or events — the body fields the recap renderer
       shows
    6. LLM generate → persist

    Returns the stored record (or the pre-existing one), or ``None`` when a guard declined.
    """
    record, _created, _declined = _generate_and_store_daily_summary(uid, date_str, start_date_utc, end_date_utc)
    return record


def generate_daily_summary_on_demand(
    uid, date_str, start_date_utc, end_date_utc
) -> Tuple[Optional[dict], Optional[str]]:
    """``generate_and_store_daily_summary`` plus the reason it declined.

    A caller with a user waiting on the other end has to tell "you have nothing recorded for
    this day" apart from "another writer is mid-generation" — the first is the answer, the
    second is a retry.
    """
    record, _created, declined = _generate_and_store_daily_summary(uid, date_str, start_date_utc, end_date_utc)
    return record, declined


def _generate_and_store_daily_summary(
    uid, date_str, start_date_utc, end_date_utc
) -> Tuple[Optional[dict], bool, Optional[str]]:
    """Like ``generate_and_store_daily_summary``, plus whether this call persisted a new record
    and, when it declined, which guard declined it.

    **Nothing happens before the lock.** A tick that loses the lock must not read conversations:
    another worker is already doing exactly that work, and probing anyway doubles the read load
    on precisely the contended user.

    **A decline before the LLM call releases the lock.** The lock's job is to stop two workers
    spending tokens on the same day, and a guard that declines has spent none. Holding it for
    the full 2h TTL instead barred the day: the on-demand button poisoned the very day it was
    pressed on — press it at 21:30 on a quiet day and the 22:00 cron tick lost the lock and
    the day never got a recap at all.
    """
    if not try_acquire_daily_summary_lock(uid, date_str):
        return None, False, _DECLINE_LOCKED

    # Durable idempotency guard (#4608): the Redis lock above is best-effort (2h TTL, evictable, lost on
    # failover), and create_daily_summary writes a fresh-uuid doc with no by-date check, so a later cron
    # tick can persist a SECOND summary for the same date. If one already exists, skip before spending
    # any LLM tokens. The regenerate flow stays in-place via update_daily_summary.
    existing_summary = daily_summaries_db.get_daily_summary_by_date(uid, date_str)
    if existing_summary:
        logger.info(
            f"Daily summary already exists for uid={uid} date={date_str} "
            f"id={existing_summary.get('id')}; skipping duplicate generation"
        )
        return existing_summary, False, None

    conversations_data = conversations_db.get_conversations(
        uid, start_date=start_date_utc, end_date=end_date_utc, date_field='started_at'
    )
    if not conversations_data or len(conversations_data) == 0:
        release_daily_summary_lock(uid, date_str)
        return None, False, _DECLINE_NO_CONVERSATIONS

    conversations = [
        deserialize_conversation(convo_data) for convo_data in conversations_data if not convo_data.get('is_locked')
    ]
    if not conversations:
        release_daily_summary_lock(uid, date_str)
        return None, False, _DECLINE_NOTHING_TO_SUMMARIZE

    # Skip recap if no conversation captured any speech.
    if not any(c.transcript_segments for c in conversations if not c.discarded):
        logger.info(f'Skipping daily summary for uid={uid} on {date_str}: no conversations with transcript content')
        release_daily_summary_lock(uid, date_str)
        return None, False, _DECLINE_NOTHING_TO_SUMMARIZE

    # Bound the generator's input (#12530). Keep the most recent conversations
    # that fit, drop the rest loudly, and always keep at least one so a recap is
    # still attempted.
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

    # The prompt is built by ``conversations_to_string(use_transcript=False)``,
    # which renders the title plus the first app result or the structured
    # overview, plus action items and events. A bounded day where no
    # conversation carries any of these leaves the model titles alone: the
    # output is thin or hallucinated
    # and then pushed (flip-review F-12 / decision 4). Decline before the LLM
    # call — no call, no record, no push. Paid, pre-flip and mobile days are
    # unchanged by construction: their overviews are non-empty, so this guard
    # never fires for them.
    if not any(_conversation_has_summary_content(c) for c in conversations if not c.discarded):
        logger.info(f'Skipping daily summary for uid={uid} on {date_str}: no conversations with summary content')
        release_daily_summary_lock(uid, date_str)
        return None, False, _DECLINE_NOTHING_TO_SUMMARIZE

    summary_data = generate_comprehensive_daily_summary(
        uid,
        conversations,
        date_str,
        start_date_utc,
        end_date_utc,
        memories_learned=memories_learned_payload(uid, conversations, start_date_utc, end_date_utc),
    )
    summary_id = daily_summaries_db.create_daily_summary(uid, summary_data)
    # The stored id rides on the returned record so the delivery step can build the
    # `/daily-summary/{id}` deep link without a second read.
    return {**summary_data, 'id': summary_id}, True, None


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
# The webhook's own slice of that per-user budget. Running it inline gave it an owner
# but also moved its cost onto the user: day_summary_webhook posts through the shared
# client (30s read timeout, retries at 1/5/30s), so a slow receiver could burn most of
# the 90s and get a user whose push had already been delivered marked
# reason=user_budget_exceeded -- which counts toward DAILY_SUMMARY_MAX_ABANDONED_USERS
# and can abort the rest of the hour group. A developer webhook must never be able to
# cost anyone else their recap, so it is bounded well inside the budget it now shares.
DAILY_SUMMARY_WEBHOOK_BUDGET_SECONDS = _env_float('DAILY_SUMMARY_WEBHOOK_BUDGET_SECONDS', 20.0)
# Rendered-character budget for the conversation material fed to the summary
# prompt. ~360k chars is roughly 90k tokens, comfortably inside the 272k-token
# model limit even alongside the prompt scaffolding and the user's memories.
# The overflow seen in production was ~290k tokens of input.
DAILY_SUMMARY_MAX_HISTORY_CHARS = _env_int('DAILY_SUMMARY_MAX_HISTORY_CHARS', summary_budget.DEFAULT_MAX_HISTORY_CHARS)
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


@dataclass(frozen=True)
class DailySummaryCronOutcome:
    ok: bool
    error_text: Optional[str] = None


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
    summary_outcome = await send_daily_summary_notification()
    if not summary_outcome.ok:
        logger.error('Daily summary cron run failed: %s', summary_outcome.error_text)


async def send_daily_summary_notification() -> DailySummaryCronOutcome:
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
    cursor_key = summary_budget.job_cursor_key()

    try:
        timezones_by_hour = _get_timezones_grouped_by_hour()
    except Exception as e:
        logger.error(f"Error grouping daily summary timezones: {e}")
        return DailySummaryCronOutcome(ok=False, error_text=str(e))

    cursor = await run_blocking(db_executor, summary_budget.read_job_cursor, cursor_key)
    resume_hour = summary_budget.cursor_hour(cursor)
    resume_uid = summary_budget.cursor_uid(cursor)

    # Deterministic order, rotated to the checkpoint: the tail is served first
    # and the head is still covered in the same pass.
    ordered_hours = summary_budget.rotate_to(sorted(timezones_by_hour.keys()), resume_hour)
    completed_all = True

    stop_processing = False

    async def process_hour(group: Tuple[int, List[str]]) -> ProcessOutcome:
        nonlocal completed_all, resume_uid, stop_processing

        target_hour, timezones = group
        if stop_processing or monotonic() >= deadline:
            completed_all = False
            stop_processing = True
            await _checkpoint(cursor_key, target_hour, None)
            _record_daily_summary_fallback(
                from_mode='full_run', to_mode='resumable_tail', reason='timeout', outcome='degraded'
            )
            logger.warning('daily_summary_job_budget_exhausted resume_hour=%s', target_hour)
            return ProcessOutcome.retry('daily summary budget exhausted', reason='timeout')

        stats.groups_attempted += 1
        try:
            users, query_error, group_fully_read = await _get_users_for_daily_summary(timezones, target_hour)
        except Exception as e:
            # One hour group's read failing must not cost the other 23 groups.
            stats.groups_failed += 1
            logger.error('daily_summary_group_failed hour=%s reason=user_query error=%s', target_hour, e)
            return ProcessOutcome.reject(str(e), reason='user_query')

        if query_error and not users:
            stats.groups_failed += 1
            logger.error('daily_summary_group_failed hour=%s reason=user_query error=%s', target_hour, query_error)
            return ProcessOutcome.reject(str(query_error), reason='user_query')

        if not group_fully_read:
            # A dropped timezone chunk means this hour was only *partially*
            # enumerated. Serving what did read is right, but declaring the run
            # complete afterwards would clear the checkpoint and retire users the
            # job never even listed. Keep the run resumable and point the next
            # execution at this hour.
            completed_all = False
            await _checkpoint(cursor_key, target_hour, None)
            _record_daily_summary_fallback(
                from_mode='full_run', to_mode='resumable_tail', reason='other', outcome='degraded'
            )

        if not users:
            return ProcessOutcome.ack()

        ordered_users = summary_budget.rotate_to(
            sorted(users, key=lambda user: str(user[0])),
            _resume_user(users, resume_uid) if target_hour == resume_hour else None,
        )
        resume_uid = None

        logger.info(f"Sending daily summary to {len(ordered_users)} users at local hour {target_hour}")
        failed_before = stats.failed
        timed_out_before = stats.timed_out
        finished_group = await _send_bulk_summary_notification(
            ordered_users, deadline=deadline, stats=stats, target_hour=target_hour, cursor_key=cursor_key
        )
        if not finished_group:
            completed_all = False
            stop_processing = True
            return ProcessOutcome.retry('daily summary group budget exhausted', reason='timeout')
        hour_send_failures = (stats.failed - failed_before) + (stats.timed_out - timed_out_before)
        if hour_send_failures:
            return ProcessOutcome.reject(
                f'{hour_send_failures} user send(s) failed at hour {target_hour}',
                reason='hour_send_failed',
            )
        if query_error:
            stats.groups_failed += 1
            return ProcessOutcome.reject(str(query_error), reason='user_query')
        return ProcessOutcome.ack()

    groups = [(hour, timezones_by_hour[hour]) for hour in ordered_hours]
    results = await drain_isolated_async(groups, process_hour)
    failures = [result for result in results if result.outcome.kind != ProcessOutcome.ack().kind]
    for result in failures:
        logger.error(
            "Daily summary hour group failed hour=%s reason=%s error=%s",
            result.item[0],
            result.outcome.reason,
            result.outcome.error_text,
        )

    if completed_all:
        await run_blocking(db_executor, summary_budget.clear_job_cursor, cursor_key)

    logger.info('daily_summary_job_summary complete=%s %s', completed_all, stats.as_log())
    if failures:
        return DailySummaryCronOutcome(
            ok=False,
            error_text='; '.join(result.outcome.error_text or 'hour_failed' for result in failures),
        )
    return DailySummaryCronOutcome(ok=True)


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


async def _get_users_for_daily_summary(
    timezones: List[str], target_hour: int
) -> Tuple[List[Tuple[str, List[str], Any]], Optional[BaseException], bool]:
    """Read one hour group's users.

    Returns ``(users, query_error, every_chunk_read)``. A dropped chunk is a
    *partial* read, and a caller that cannot tell the difference finishes the
    hour, clears the checkpoint, and permanently retires users it never listed.
    Serving the chunks that did read is still right — the flag only stops the
    run from calling itself complete.

    """
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
    chunk_errors: List[BaseException] = []
    every_chunk_read = True
    for chunk_index, chunk in enumerate(chunk_results):
        if isinstance(chunk, BaseException):
            every_chunk_read = False
            logger.error(
                'daily_summary_user_query_chunk_failed hour=%s chunk=%d error=%s', target_hour, chunk_index, chunk
            )
            chunk_errors.append(chunk)
            continue
        users.extend(chunk)
    return users, chunk_errors[0] if chunk_errors else None, every_chunk_read


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


def _deliver_current_day_summary(uid, date_str: str, summary_data: dict, tokens) -> None:
    """Push + webhook for a newly generated *current* day. Backfilled days never call this."""
    summary_id = str(summary_data.get('id') or '')
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

    if tokens:
        send_notification(
            uid, daily_summary_title, summary_body, NotificationMessage.get_message_as_dict(ai_message), tokens=tokens
        )
    else:
        logger.info(f"Skipping daily summary push for uid={uid}: no FCM tokens")


def _deliver_day_summary_webhook(uid, summary_data: dict) -> None:
    """Send the developer webhook for a freshly generated day.

    Runs inline rather than submitted (#12530). The old
    ``postprocess_executor.submit(asyncio.run, ...)`` had two defects:
    ``_send_summary_notification`` is already executing *on* postprocess_executor
    (dispatched through ``run_blocking``), so the submit made the function its own
    child on that pool -- the arrangement backend/AGENTS.md forbids -- and nothing
    owned the result, so a webhook still queued when the Cloud Run Job exited was
    never scheduled at all. That is the "coroutine 'day_summary_webhook' was never
    awaited" logged immediately before container exit in #12530's evidence.

    Called *after* the backfill walk, and last in the per-user budget. Inline
    execution moved the webhook's cost onto the user, and this function shares the
    90s ``DAILY_SUMMARY_USER_BUDGET_SECONDS`` with the owner's own work. Running it
    before the backfill let a slow receiver spend seconds the owner's missing days
    needed, which is the opposite of the rule this fix exists to uphold: a
    developer webhook must never cost the owner their recap. Last means it can only
    ever spend budget nobody else still wants.

    Bounded, contained and logged for the same reason. day_summary_webhook handles
    its own HTTP failures but not the work around them (URL assembly, the
    webhook-status reads); left bare, one of those would propagate out of a user
    whose push had already been delivered and count them as failed. The discarded
    Future used to provide that containment by accident -- this makes it a decision,
    and reports it, where the old path reported nothing at all.

    ``summary`` is the legacy str(...) form, kept for backward compatibility;
    ``summary_json`` carries the same payload as a real JSON object.
    """
    try:
        asyncio.run(
            asyncio.wait_for(
                day_summary_webhook(uid, str(summary_data), summary_data),
                timeout=DAILY_SUMMARY_WEBHOOK_BUDGET_SECONDS,
            )
        )
    except Exception as e:
        logger.error('daily_summary_webhook_failed uid=%s error=%s', uid, e, exc_info=e)


def _backfill_recent_daily_summaries(uid, display_date, tz_name: Optional[str]) -> None:
    """Fill holes behind the current day, without sending a notification for any of them."""
    generated = 0
    for offset in range(1, _DAILY_SUMMARY_BACKFILL_DAYS + 1):
        if generated >= _DAILY_SUMMARY_BACKFILL_GENERATE_CAP:
            logger.info(
                f"Daily summary backfill cap reached for uid={uid} "
                f"(generated={generated}, window={_DAILY_SUMMARY_BACKFILL_DAYS}d)"
            )
            return
        past_date = display_date - timedelta(days=offset)
        date_str = past_date.strftime('%Y-%m-%d')
        start_date_utc, end_date_utc = local_day_bounds_utc(past_date, tz_name)
        _record, created, _declined = _generate_and_store_daily_summary(uid, date_str, start_date_utc, end_date_utc)
        if created:
            generated += 1


def _send_summary_notification(user_data: Tuple[Any, ...]) -> None:
    uid = user_data[0]
    user_tz_name = user_data[2] if len(user_data) > 2 else None

    # NOTE: The daily recap is a cross-platform feature delivered by a
    # server-initiated cron that does not know the originating platform.
    # It must NOT be gated on the desktop trial paywall: passing a hardcoded
    # 'macos' to is_trial_paywalled() made the gate trip for any trial-expired
    # user, suppressing their recap on mobile/web too (#9357). The desktop
    # trial only gates desktop features, not the recap the mobile app renders.

    display_date = _display_date_for_now(user_tz_name)
    start_date_utc, end_date_utc = local_day_bounds_utc(display_date, user_tz_name)
    date_str = display_date.strftime('%Y-%m-%d')

    summary_data, created, declined = _generate_and_store_daily_summary(uid, date_str, start_date_utc, end_date_utc)
    pending_webhook: Optional[dict] = None
    if created and summary_data:
        tokens = user_data[1] if len(user_data) > 1 else None
        _deliver_current_day_summary(uid, date_str, summary_data, tokens)
        # Deferred to the end of this user's work. See _deliver_day_summary_webhook.
        pending_webhook = summary_data

    try:

        # Backfill only for owners who are actually still recording. Dropping the FCM-token filter in
        # get_users_for_daily_summary widened this fan-out to every user in the timezone, and an
        # unconditional 7-day walk would spend 7 lock writes + 7 by-date reads + 7 conversation queries
        # per dormant account per day chasing holes it can never fill.
        #
        # The reason comes from the attempt above rather than from a second query: re-reading
        # conversations here would undo the "lose the lock, do no work" guarantee that keeps a
        # contended user from being read twice.
        #
        # Only an *empty* window means dormant. A day whose conversations were all `is_locked`, or
        # carried no transcript, still proves the owner was recording — those are the accounts whose
        # earlier days most need walking back — so `_DECLINE_NOTHING_TO_SUMMARIZE` is deliberately
        # absent from this set.
        if declined in (_DECLINE_LOCKED, _DECLINE_NO_CONVERSATIONS):
            return

        _backfill_recent_daily_summaries(uid, display_date, user_tz_name)
    finally:
        # finally, not a trailing call: the dormant-owner branch above returns early
        # and backfill can raise. Either would drop the webhook for a user whose
        # summary was already stored and pushed, which is the exact loss this fix
        # exists to stop -- just moved to a different exit.
        if pending_webhook is not None:
            _deliver_day_summary_webhook(uid, pending_webhook)


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

    That per-user budget now covers the backfill walk as well as the current day,
    so a user with holes can spend up to
    ``1 + _DAILY_SUMMARY_BACKFILL_GENERATE_CAP`` generations inside one timeout.
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
