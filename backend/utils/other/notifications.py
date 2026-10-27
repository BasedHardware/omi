from utils.generated_compute import generated_compute_allowed, require_generated_compute

# async-blockers: no-import-scope
# async-blockers: no-changed-range-scope  # pre-existing patterns surfaced by type-annotation import changes
import asyncio
import os
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta
from threading import Event
from time import monotonic
from typing import Any, Callable, Dict, List, Optional, Tuple
from uuid import uuid4

import pytz

import database.conversations as conversations_db
from database.durable_queue import ProcessOutcome, drain_isolated_async
import database.notifications as notification_db
import database.redis_db as redis_db
from database.redis_db import release_daily_summary_lock, try_acquire_daily_summary_lock
from models.notification_message import NotificationMessage
from utils.conversations.factory import deserialize_conversations
from utils.conversations.summary_selection import select_primary_summary
from utils.daily_summary_validation import require_daily_summary
from utils.executors import db_executor, open_loops_executor, postprocess_executor, run_blocking
from utils.conversations.relevance_content import exclude_from_derived
from utils.llm.external_integrations import generate_comprehensive_daily_summary
from config.refactor_modes import serving_for
from utils.llm.daily_recap_fingerprint import input_fingerprint, FINGERPRINT_FIELD
from utils.llm.notes_refactor_metrics import shadow as record_notes_shadow
from utils.memory.learned_today import memories_learned_payload, memory_review_card_block
from utils.notifications import send_bulk_notification, send_notification_result
from utils.other import daily_summary_metrics
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


def _display_date_for_now(tz_name: Optional[str], at: Optional[datetime] = None):
    """Calendar day the cron summarizes at this instant (noon split, then UTC fallback)."""
    if tz_name:
        try:
            user_tz = pytz.timezone(tz_name)
            now_in_user_tz = at.astimezone(user_tz) if at is not None else datetime.now(user_tz)
            if now_in_user_tz.hour < 12:
                return now_in_user_tz.date() - timedelta(days=1)
            return now_in_user_tz.date()
        except Exception as e:
            logger.error(e)
    now_utc = at.astimezone(pytz.utc) if at is not None else datetime.now(pytz.utc)
    if now_utc.hour < 12:
        return now_utc.date() - timedelta(days=1)
    return now_utc.date()


# Why one day's generation declined. The tick needs this to decide whether walking back is
# worth anything: another worker already owns this user (``locked``), or the owner recorded
# nothing at all (``no_conversations``), and in both cases the backfill would only spend
# queries on holes it cannot fill.
_DECLINE_LOCKED = 'locked'
_DECLINE_NO_CONVERSATIONS = 'no_conversations'
# daily_recap.generate's budget decline; a budget-declined recap spends no
# sibling-step tokens either.
_DECLINE_USAGE_BUDGET = 'usage_budget_exhausted'
# The window held conversations, but none this job may summarize (all ``is_locked``, none
# carried transcript content, or nothing carried summary body content — titles alone).
# Distinct from ``no_conversations`` because the owner *was*
# active: their earlier days are worth walking back for, and the caller may say so.
_DECLINE_NOTHING_TO_SUMMARIZE = 'nothing_to_summarize'
# Public name for the one decline a caller outside this module has to act on differently.
DAILY_SUMMARY_DECLINE_LOCKED = _DECLINE_LOCKED
DAILY_SUMMARY_DECLINE_NO_CONVERSATIONS = _DECLINE_NO_CONVERSATIONS
DAILY_SUMMARY_DECLINE_NOTHING_TO_SUMMARIZE = _DECLINE_NOTHING_TO_SUMMARIZE


def _conversation_has_summary_content(conversation: Any) -> bool:
    """True when the recap renderer would show more than this conversation's title.

    Reads the content fields ``conversations_to_string(use_transcript=False)``
    renders as the body — the canonical primary summary projection, plus
    ``structured.action_items`` and ``structured.events`` — so the pre-LLM
    decline guard cannot drift from what the model would actually see.

    Attendee names are rendered too, but deliberately do not count: they are
    presence labels attached to the conversation, not summary content, and a
    day that renders as titles plus a list of names is still the degenerate
    F-12 shape this gate exists to decline.
    """
    if select_primary_summary(conversation).content:
        return True
    structured = getattr(conversation, 'structured', None)
    if getattr(structured, 'action_items', None):
        return True
    return bool(getattr(structured, 'events', None))


conversation_has_summary_content = _conversation_has_summary_content


def generate_and_store_daily_summary(uid, date_str, start_date_utc, end_date_utc) -> Optional[dict]:
    """Generate one day's summary, or return the one already stored.

    Legacy guard order is the existing contract and must not be reordered:

    1. best-effort Redis lock
    2. durable by-date idempotency (existing record → return it, no LLM)
    3. conversations exist in the window and are not ``is_locked``
    4. at least one non-discarded conversation has ``transcript_segments``
    5. the bounded day carries more than titles for the prompt: some
       conversation has a non-empty ``structured.overview``, a first app
       result, action items, or events — the body fields the recap renderer
       shows
    6. LLM generate → persist

    Serving recap revisions/states live in daily_recap. User-initiated partial-day
    generation is explicit through generate_daily_summary_on_demand.

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
    require_generated_compute(uid, 'daily_summary')
    record, _created, declined = _generate_and_store_daily_summary(
        uid, date_str, start_date_utc, end_date_utc, user_initiated=True
    )
    return record, declined


def _generate_and_store_daily_summary(
    uid, date_str, start_date_utc, end_date_utc, *, prepare_delivery=None, user_initiated=False
):
    from utils.other.daily_recap import generate

    return generate(
        uid,
        date_str,
        start_date_utc,
        end_date_utc,
        legacy=_legacy_generate_and_store_daily_summary,
        prepare_delivery=prepare_delivery,
        user_initiated=user_initiated,
    )


# refactor: superseded by utils.other.daily_recap when CALLS_RECAP_MODE=serve
def _legacy_generate_and_store_daily_summary(
    uid, date_str, start_date_utc, end_date_utc, *, prepare_delivery: Optional[Callable[[], None]] = None
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
    from utils.other.daily_recap import delivery_allowed, finish_legacy_stub

    if not generated_compute_allowed(uid, 'daily_summary'):
        return None, False, 'usage_budget_exhausted'
    if not try_acquire_daily_summary_lock(uid, date_str):
        return None, False, _DECLINE_LOCKED

    try:
        # Durable idempotency guard (#4608): the Redis lock above is best-effort (2h TTL, evictable, lost on
        # failover), and create_daily_summary writes a fresh-uuid doc with no by-date check, so a later cron
        # tick can persist a SECOND summary for the same date. If one already exists, skip before spending
        # any LLM tokens. The regenerate flow stays in-place via update_daily_summary.
        existing_summary = daily_summaries_db.get_daily_summary_by_date(uid, date_str)
        existing_complete = bool(existing_summary and delivery_allowed(uid, existing_summary))
        if existing_summary and existing_complete and not serving_for('NOTES_PACKET_V2_MODE', uid):
            logger.info(
                f"Daily summary already exists for uid={uid} date={date_str} "
                f"id={existing_summary.get('id')}; skipping duplicate generation"
            )
            return existing_summary, False, None

        conversations_data = conversations_db.get_conversations(
            uid, start_date=start_date_utc, end_date=end_date_utc, date_field='started_at'
        )
        fingerprint = None
        if serving_for('NOTES_PACKET_V2_MODE', uid):
            fingerprint = input_fingerprint(conversations_data or [])
            if existing_summary and existing_complete and existing_summary.get(FINGERPRINT_FIELD) == fingerprint:
                release_daily_summary_lock(uid, date_str)
                record_notes_shadow('daily_recap_inputs', 'agree')
                return existing_summary, False, None
            record_notes_shadow('daily_recap_inputs', 'disagree')
        if not conversations_data or len(conversations_data) == 0:
            release_daily_summary_lock(uid, date_str)
            return None, False, _DECLINE_NO_CONVERSATIONS

        conversations = deserialize_conversations(
            [convo_data for convo_data in conversations_data if not convo_data.get('is_locked')]
        )
        conversations = [c for c in conversations if not exclude_from_derived(uid, c, consumer='daily_summary')]
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
        conversations = bound_daily_summary_conversations(uid, date_str, conversations)

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

        if prepare_delivery is not None:
            prepare_delivery()

        _record_summary_generation_status(uid, date_str, 'pending')
        summary_data = generate_comprehensive_daily_summary(
            uid,
            conversations,
            date_str,
            start_date_utc,
            end_date_utc,
            memories_learned=memories_learned_payload(uid, conversations, start_date_utc, end_date_utc),
        )
        # Validate before any write. A saved invalid candidate would satisfy the
        # by-date idempotency guard and prevent the user's next attempt from generating.
        require_daily_summary(summary_data, uid=uid, operation='legacy_generation_candidate')
        summary_data = finish_legacy_stub(existing_summary, summary_data)
        if fingerprint is not None:
            summary_data[FINGERPRINT_FIELD] = fingerprint
        if existing_summary:
            summary_id = existing_summary['id']
            # Preserve the existing deep link and completed-delivery marker on refresh.
            # Content refresh must not send the same day's push again.
            summary_data.update(
                {
                    key: existing_summary[key]
                    for key in ('visibility', 'notification_delivery_completed')
                    if key in existing_summary
                }
            )
            daily_summaries_db.update_daily_summary(uid, summary_id, summary_data)
        else:
            summary_id = daily_summaries_db.create_daily_summary(uid, summary_data)
        # The stored id rides on the returned record so the delivery step can build the
        # `/daily-summary/{id}` deep link without a second read.
        return {**summary_data, 'id': summary_id}, True, None

    except Exception:
        # We own this day lock. Failed reads/generation/persistence must permit
        # the saved cohort to retry on the next tick, even after the due hour.
        _record_summary_generation_status(uid, date_str, 'failed')
        release_daily_summary_lock(uid, date_str)
        raise


def _record_summary_generation_status(uid: str, date: str, status: str) -> None:
    try:
        daily_summaries_db.set_daily_summary_generation_status(uid, date, status)
    except Exception:
        _record_daily_summary_fallback(from_mode='status_marker', to_mode='none', reason='other', outcome='degraded')


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
# The open-loops daily pass runs AFTER the recap's own work (push, backfill,
# webhook) is fully done, on its own executor under this deadline. It is a
# separate budget on purpose: a slow or failing pass must never spend the
# user's recap budget, delay the webhook, mark a recipient timed_out or count
# toward DAILY_SUMMARY_MAX_ABANDONED_USERS — recap metrics and ordering are
# untouched by everything below this line.
OPEN_LOOPS_PASS_BUDGET_SECONDS = _env_float('OPEN_LOOPS_PASS_BUDGET_SECONDS', 45.0)
# Passes admitted to open_loops_executor at once (its worker count), so a
# large hour group queues here instead of tripping the executor's bounded
# queue; the per-pass budget starts only once a pass holds a slot.
OPEN_LOOPS_PASS_CONCURRENCY = 4
# One drain per job, after every cohort: whatever has not finished by then is
# cancelled and counted. Keeps the job well inside its 15-minute tick.
OPEN_LOOPS_DRAIN_BUDGET_SECONDS = _env_float('OPEN_LOOPS_DRAIN_BUDGET_SECONDS', 240.0)
# Rendered-character budget for the conversation material fed to the summary
# prompt. ~360k chars is roughly 90k tokens, comfortably inside the 272k-token
# model limit even alongside the prompt scaffolding and the user's memories.
# The overflow seen in production was ~290k tokens of input.
DAILY_SUMMARY_MAX_HISTORY_CHARS = _env_int('DAILY_SUMMARY_MAX_HISTORY_CHARS', summary_budget.DEFAULT_MAX_HISTORY_CHARS)
# A per-user timeout abandons (it cannot cancel) a worker thread. Stop the run
# once enough threads are abandoned that the pool would starve the rest.
DAILY_SUMMARY_MAX_ABANDONED_USERS = _env_int('DAILY_SUMMARY_MAX_ABANDONED_USERS', 12)

# --- Recipient selection for the hourly daily-summary tick (#13210) --------
_BATCH_SIZE = 8

_FALLBACK_COMPONENT = 'daily_summary'


def bound_daily_summary_conversations(uid: str, date_str: str, conversations: List[Any]) -> List[Any]:
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
    return bounded.conversations


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
    recipient_docs_selected: int = 0
    recipient_queries: int = 0
    retry_recipients: Dict[str, bool] = field(default_factory=dict)
    retry_hour: Optional[int] = None
    retry_uid: Optional[str] = None
    # Recipients already carrying a failure from the previous pass. A second
    # failure is final, so one dead recipient cannot hold the cohort open.
    prior_retry_uids: frozenset = frozenset()
    retry_pending: int = 0
    retries_exhausted: int = 0
    # Set when the pass did not reach every recipient (budget, read failure).
    # Only then does the next pass need to re-walk the cohort.
    walk_incomplete: bool = False

    def as_log(self) -> str:
        return (
            f'groups_attempted={self.groups_attempted} groups_failed={self.groups_failed} '
            f'attempted={self.attempted} succeeded={self.succeeded} failed={self.failed} '
            f'timed_out={self.timed_out} skipped_for_budget={self.skipped_for_budget} '
            f'recipient_docs_selected={self.recipient_docs_selected} recipient_queries={self.recipient_queries} '
            f'retry_recipients={len(self.retry_recipients)} retries_exhausted={self.retries_exhausted}'
        )


@dataclass(frozen=True)
class DailySummaryCronOutcome:
    ok: bool
    error_text: Optional[str] = None
    complete: bool = True


class DailySummaryDeliveryError(RuntimeError):
    """A durable recap exists but its push failed before delivery completed."""


def should_run_job() -> bool:
    """
    Check if the notification cron job should run.
    Always returns True since we now handle all hours dynamically.
    """
    return True


async def start_cron_job() -> None:
    """
    Main cron job entry point. Runs every 15 minutes for local-hour delivery.
    """
    logger.info(f'start_cron_job at UTC hour {datetime.now(pytz.utc).hour}')
    token = uuid4().hex
    acquired = False
    try:
        try:
            acquired = await run_blocking(db_executor, redis_db.try_acquire_notifications_job_run_lock, token)
        except Exception as error:
            # Fail open: a Redis outage must not silence every recap for the hour. The cost
            # is a possible duplicate pass, which the per-user day locks already bound.
            logger.warning('notifications_job_run_lock_acquire_failed error=%s', error)
            _record_daily_summary_fallback(
                from_mode='run_locked', to_mode='run_unlocked', reason='other', outcome='degraded'
            )
        else:
            if not acquired:
                logger.warning(
                    'notifications_job_run_skipped reason=overlap utc_hour=%s',
                    datetime.now(pytz.utc).hour,
                )
                return

        # Wear FCM has no per-send idempotency on the bulk path. Never ride
        # job-lock fail-open (Redis maxmemory). Summaries still fail-open.
        if acquired:
            await send_daily_notification()
        summary_outcome = await send_daily_summary_notification()
        if not summary_outcome.ok:
            logger.error('Daily summary cron run failed: %s', summary_outcome.error_text)
    finally:
        if acquired:
            await run_blocking(db_executor, redis_db.release_notifications_job_run_lock, token)


async def send_daily_summary_notification() -> DailySummaryCronOutcome:
    """Run the due cohorts, then drain their open-loops passes once."""
    try:
        return await _send_daily_summary_cohorts()
    finally:
        await _drain_open_loops_passes()


async def _send_daily_summary_cohorts() -> DailySummaryCronOutcome:
    """Resume the original due cohort before selecting the current local hours.

    A cursor without its UTC selection instant only reorders *today's* query;
    after an hour rollover it cannot reach the owners deferred yesterday's tick.
    Preserve the instant through selection and generation (including the noon
    date split), then run the current cohort if the saved one completes.
    """
    now = datetime.now(pytz.utc)
    cursor = await run_blocking(db_executor, summary_budget.read_job_cursor, summary_budget.job_cursor_key())
    resumed_at = summary_budget.cursor_cohort_utc(cursor)
    cursor_age_seconds = (now - resumed_at).total_seconds() if resumed_at is not None else 0.0
    daily_summary_metrics.RESUMED_COHORT_AGE.set(cursor_age_seconds)
    cursor_key = summary_budget.job_cursor_key()
    # The Redis TTL is supposed to be the staleness bound (daily_summary_budget.py),
    # but every tick that resumes this cohort rewrites the checkpoint and renews
    # that TTL, so a recipient who can never succeed (e.g. a permanently invalid
    # FCM token) keeps the checkpoint alive forever. That pins every execution on
    # the same stale cohort and the *current* cohort below is never reached, so
    # every other recipient's recap silently stops too. Age the cohort out by
    # the same bound independent of the TTL renewal.
    if resumed_at is not None and now - resumed_at > timedelta(seconds=summary_budget.JOB_CURSOR_TTL_SECONDS):
        logger.error(
            'daily_summary_cursor_abandoned_stale cohort_utc=%s age_seconds=%s hour=%s uid=%s',
            resumed_at.isoformat(),
            (now - resumed_at).total_seconds(),
            summary_budget.cursor_hour(cursor),
            summary_budget.cursor_uid(cursor),
        )
        await run_blocking(db_executor, summary_budget.clear_job_cursor, cursor_key)
        resumed_at = None
        cursor = None
    # A local hour can roll over at :15/:30/:45 within the same UTC hour.
    if resumed_at is not None and resumed_at.replace(
        minute=(resumed_at.minute // 15) * 15, second=0, microsecond=0
    ) != now.replace(minute=(now.minute // 15) * 15, second=0, microsecond=0):
        resumed = await _send_daily_summary_cohort(resumed_at, cursor, cursor_age_seconds=cursor_age_seconds)
        if not resumed.complete:
            return resumed
        current = await _send_daily_summary_cohort(now, None, cursor_age_seconds=cursor_age_seconds)
        return DailySummaryCronOutcome(
            ok=resumed.ok and current.ok,
            error_text=resumed.error_text or current.error_text,
            complete=current.complete,
        )
    return await _send_daily_summary_cohort(now, cursor, cursor_age_seconds=cursor_age_seconds)


async def _send_daily_summary_cohort(
    cohort_utc: datetime, cursor: Optional[dict], *, cursor_age_seconds: float = 0.0
) -> DailySummaryCronOutcome:
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
    saved_retries = dict((cursor or {}).get('retry_recipients', {}))
    stats = DailySummaryJobStats(retry_recipients=saved_retries, prior_retry_uids=frozenset(saved_retries))
    # A pass that walked the whole cohort and left only failures behind is resumed
    # by retrying those recipients alone. Re-walking every served recipient made
    # each resume as slow as the original pass, so it ended near the deadline,
    # produced a fresh timeout, and pinned the cohort again until the 2h cutoff.
    retry_only = summary_budget.cursor_retry_only(cursor) and bool(saved_retries)
    cursor_key = summary_budget.job_cursor_key()

    try:
        timezones_by_hour = _get_timezones_grouped_by_hour(cohort_utc)
    except Exception as e:
        logger.error(f"Error grouping daily summary timezones: {e}")
        daily_summary_metrics.COHORT_COMPLETE.labels(outcome='incomplete').inc()
        return DailySummaryCronOutcome(ok=False, error_text=str(e), complete=False)

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
            stats.walk_incomplete = True
            stop_processing = True
            await _checkpoint(cursor_key, target_hour, None, cohort_utc, stats.retry_recipients)
            _record_daily_summary_fallback(
                from_mode='full_run', to_mode='resumable_tail', reason='timeout', outcome='degraded'
            )
            logger.warning('daily_summary_job_budget_exhausted resume_hour=%s', target_hour)
            return ProcessOutcome.retry('daily summary budget exhausted', reason='timeout')

        stats.groups_attempted += 1
        stats.recipient_queries += (len(timezones) + 29) // 30
        try:
            users, query_error, group_fully_read = await _get_users_for_daily_summary(timezones, target_hour)
        except Exception as e:
            # One hour group's read failing must not cost the other 23 groups.
            stats.groups_failed += 1
            completed_all = False
            stats.walk_incomplete = True
            await _checkpoint(cursor_key, target_hour, None, cohort_utc, stats.retry_recipients)
            logger.error('daily_summary_group_failed hour=%s reason=user_query error=%s', target_hour, e)
            return ProcessOutcome.reject(str(e), reason='user_query')

        if query_error and not users:
            stats.groups_failed += 1
            completed_all = False
            stats.walk_incomplete = True
            await _checkpoint(cursor_key, target_hour, None, cohort_utc, stats.retry_recipients)
            logger.error('daily_summary_group_failed hour=%s reason=user_query error=%s', target_hour, query_error)
            return ProcessOutcome.reject(str(query_error), reason='user_query')

        if not group_fully_read:
            # A dropped timezone chunk means this hour was only *partially*
            # enumerated. Serving what did read is right, but declaring the run
            # complete afterwards would clear the checkpoint and retire users the
            # job never even listed. Keep the run resumable and point the next
            # execution at this hour.
            completed_all = False
            stats.walk_incomplete = True
            await _checkpoint(cursor_key, target_hour, None, cohort_utc, stats.retry_recipients)
            _record_daily_summary_fallback(
                from_mode='full_run', to_mode='resumable_tail', reason='other', outcome='degraded'
            )

        if retry_only:
            users = [user for user in users if str(user[0]) in stats.prior_retry_uids]

        stats.recipient_docs_selected += len(users)
        daily_summary_metrics.RECIPIENTS.labels(outcome='selected').inc(len(users))
        if not users:
            return ProcessOutcome.ack()

        ordered_users = summary_budget.rotate_to(
            sorted(users, key=lambda user: str(user[0])),
            _resume_user(users, resume_uid) if target_hour == resume_hour else None,
        )
        resume_uid = None

        logger.info(f"Sending daily summary to {len(ordered_users)} users at local hour {target_hour}")
        pending_before = stats.retry_pending
        finished_group = await _send_bulk_summary_notification(
            [
                (
                    *user,
                    cohort_utc,
                    stats.retry_recipients.get(str(user[0]), False),
                    str(user[0]) in stats.retry_recipients,
                )
                for user in ordered_users
            ],
            deadline=deadline,
            stats=stats,
            target_hour=target_hour,
            cursor_key=cursor_key,
            cohort_utc=cohort_utc,
        )
        if not finished_group:
            completed_all = False
            stats.walk_incomplete = True
            stop_processing = True
            return ProcessOutcome.retry('daily summary group budget exhausted', reason='timeout')
        # Exhausted retries are logged and final; only failures still owed a
        # retry keep the cohort open.
        hour_send_failures = stats.retry_pending - pending_before
        if hour_send_failures:
            completed_all = False
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

    if stats.retry_uid is not None:
        # Later batches/groups may checkpoint their progress. Keep the earliest
        # failed recipient and the original cohort after the entire pass, so a
        # final-tick failure survives both those writes and the local-hour boundary.
        completed_all = False
        await _checkpoint(
            cursor_key,
            stats.retry_hour,
            stats.retry_uid,
            cohort_utc,
            stats.retry_recipients,
            retry_only=not stats.walk_incomplete,
        )
    if completed_all:
        await run_blocking(db_executor, summary_budget.clear_job_cursor, cursor_key)

    daily_summary_metrics.COHORT_COMPLETE.labels(outcome='complete' if completed_all else 'incomplete').inc()
    logger.info(
        'daily_summary_job_summary complete=%s %s cohort_utc=%s cursor_age_seconds=%s resumed=%s',
        completed_all,
        stats.as_log(),
        cohort_utc.isoformat(),
        cursor_age_seconds,
        summary_budget.cursor_cohort_utc(cursor) is not None,
    )
    if failures:
        return DailySummaryCronOutcome(
            ok=False,
            error_text='; '.join(result.outcome.error_text or 'hour_failed' for result in failures),
            complete=completed_all,
        )
    return DailySummaryCronOutcome(ok=True, complete=completed_all)


def _resume_user(users: List[Tuple[Any, ...]], resume_uid: Optional[str]) -> Optional[Tuple[Any, ...]]:
    """Map a checkpointed uid back onto this run's user tuple, if still present."""
    if not resume_uid:
        return None
    for user in users:
        if str(user[0]) == resume_uid:
            return user
    return None


async def _checkpoint(
    cursor_key: str,
    target_hour: Optional[int],
    uid: Optional[str],
    cohort_utc: Optional[datetime] = None,
    retry_recipients: Optional[Dict[str, bool]] = None,
    *,
    retry_only: bool = False,
) -> None:
    cursor = summary_budget.make_cursor(target_hour, uid, cohort_utc)
    if retry_recipients:
        cursor['retry_recipients'] = dict(retry_recipients)
        if retry_only:
            cursor['retry_only'] = True
    await run_blocking(
        db_executor,
        summary_budget.write_job_cursor,
        cursor_key,
        cursor,
    )


async def _query_daily_summary_chunks(selector: Any, timezone_chunks: List[List[str]], target_hour: int):
    return await asyncio.gather(
        *[run_blocking(db_executor, selector, chunk, target_hour) for chunk in timezone_chunks],
        return_exceptions=True,
    )


def _reduce_daily_summary_chunks(
    chunk_results: List[Any], target_hour: int
) -> Tuple[List[Tuple[str, Any, Any]], Optional[BaseException], bool]:
    users: List[Tuple[str, Any, Any]] = []
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


async def _get_users_for_daily_summary(timezones, target_hour):
    from utils.other.daily_recap import select_recipients

    return await select_recipients(timezones, target_hour, _legacy_get_users_for_daily_summary)


# refactor: superseded by utils.other.daily_recap when CALLS_RECAP_MODE=serve
async def _legacy_get_users_for_daily_summary(
    timezones: List[str], target_hour: int
) -> Tuple[List[Tuple[str, Any, Any]], Optional[BaseException], bool]:
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
    chunk_results = await _query_daily_summary_chunks(
        notification_db.get_users_for_daily_summary_indexed, timezone_chunks, target_hour
    )
    return _reduce_daily_summary_chunks(chunk_results, target_hour)


def _get_timezones_grouped_by_hour(at: Optional[datetime] = None) -> Dict[int, List[str]]:
    """Group all timezones by their current local hour."""
    now = at if at is not None else datetime.now(pytz.utc)
    timezones_by_hour: Dict[int, List[str]] = {}
    for tz_name in pytz.all_timezones:
        tz = pytz.timezone(tz_name)
        current_hour = now.astimezone(tz).hour
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
        delivered = send_notification_result(
            uid, daily_summary_title, summary_body, NotificationMessage.get_message_as_dict(ai_message), tokens=tokens
        )
        if delivered == 0:
            raise RuntimeError('daily summary push delivered to no devices')
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


def _run_open_loops_daily_pass(uid, date_str, start_date_utc, end_date_utc, tz_name) -> None:
    """The open-loops daily pass as a sibling step of the recap (fail-open).

    One structured call per user per local day, dispatched only after the
    recap's own work for that user fully finished (see
    ``_start_open_loops_passes``): it reuses the recap's conversation
    render, updates the loop store and stores the day's Review cards (not
    served in this PR). Its own guards — ``OPEN_LOOPS_ENABLED``, the per-day
    claim/cards marker and the no-signal cost check — decide whether the model
    call happens at all. A user whose recap was budget-declined spends nothing
    here either; a locked day belongs to the worker that holds the lock, and
    that worker runs the pass. Every failure is contained — including the pass
    module's own import — the recap must never notice this step.
    """
    try:
        from utils.open_loops.daily import run_daily_pass

        outcome = run_daily_pass(uid, date_str=date_str, start_utc=start_date_utc, end_utc=end_date_utc, tz=tz_name)
        if outcome != 'ran':
            logger.info('open_loops_daily_pass_skipped uid=%s date=%s reason=%s', uid, date_str, outcome)
    except Exception as error:
        # Fail-open, and counted: a skipped pass day is a degrade the owner
        # never sees, not a silent drop.
        try:
            _record_daily_summary_fallback(
                from_mode='open_loops_daily_pass', to_mode='skipped', reason='error', outcome='degraded'
            )
        except Exception:
            logger.exception('open_loops_daily_pass_fallback_metric_failed')
        logger.error('open_loops_daily_pass_failed uid=%s date=%s error=%s', uid, date_str, error, exc_info=error)


@dataclass
class _OpenLoopPassQueue:
    loop: Any
    slots: asyncio.Semaphore
    tasks: List['asyncio.Task[None]'] = field(default_factory=list)


_open_loop_pass_queue: Optional[_OpenLoopPassQueue] = None


def _current_open_loop_pass_queue() -> _OpenLoopPassQueue:
    global _open_loop_pass_queue
    loop = asyncio.get_running_loop()
    if _open_loop_pass_queue is None or _open_loop_pass_queue.loop is not loop:
        _open_loop_pass_queue = _OpenLoopPassQueue(loop=loop, slots=asyncio.Semaphore(OPEN_LOOPS_PASS_CONCURRENCY))
    return _open_loop_pass_queue


def _is_executor_saturated(error: BaseException) -> bool:
    # Imported lazily: import-isolation harnesses stub utils.executors.
    try:
        from utils.executors import ExecutorSaturatedError
    except ImportError:
        return False
    return isinstance(error, ExecutorSaturatedError)


def _start_open_loops_passes(pass_requests: List[Tuple[Any, ...]]) -> List['asyncio.Task[None]']:
    """Queue the day's open-loops passes off the recap critical path; returns their tasks.

    Each request is ``(uid, date_str, start_utc, end_utc, tz_name)`` returned
    by ``_send_summary_notification`` after that user's recap work — summary,
    push, backfill and webhook — completed. Nothing here is awaited by the
    recap loop: passes wait for one of ``OPEN_LOOPS_PASS_CONCURRENCY`` slots,
    then run on ``open_loops_executor`` under ``OPEN_LOOPS_PASS_BUDGET_SECONDS``
    (past it the coroutine abandons the worker; a thread cannot be cancelled).
    ``_drain_open_loops_passes`` settles them once per job. Nothing here ever
    touches a recap recipient metric, ``counters.timed_out``,
    ``DAILY_SUMMARY_MAX_ABANDONED_USERS`` or user ordering. The pass's own
    per-day claim bounds what an abandoned worker can spend.
    """
    if not pass_requests:
        return []
    queue = _current_open_loop_pass_queue()

    async def one_pass(request: Tuple[Any, ...]) -> None:
        uid, date_str, start_date_utc, end_date_utc, tz_name = request
        try:
            async with queue.slots:
                await asyncio.wait_for(
                    run_blocking(
                        open_loops_executor,
                        _run_open_loops_daily_pass,
                        uid,
                        date_str,
                        start_date_utc,
                        end_date_utc,
                        tz_name,
                    ),
                    timeout=OPEN_LOOPS_PASS_BUDGET_SECONDS,
                )
        except (asyncio.TimeoutError, TimeoutError):
            logger.error(
                'open_loops_daily_pass_abandoned uid=%s date=%s budget_seconds=%s',
                uid,
                date_str,
                OPEN_LOOPS_PASS_BUDGET_SECONDS,
            )
        except Exception as error:
            if _is_executor_saturated(error):
                # Only reachable if something else fills the executor. The user's
                # loops stay in the store and the next day's pass sees them.
                _record_daily_summary_fallback(
                    from_mode='open_loops_daily_pass', to_mode='skipped', reason='capacity_full', outcome='degraded'
                )
                logger.error('open_loops_daily_pass_dropped uid=%s date=%s reason=executor_saturated', uid, date_str)
            else:
                logger.error('open_loops_daily_pass_dispatch_failed uid=%s date=%s error=%s', uid, date_str, error)

    tasks = [asyncio.ensure_future(one_pass(request)) for request in pass_requests]
    queue.tasks.extend(tasks)
    return tasks


async def _drain_open_loops_passes(budget_seconds: Optional[float] = None) -> None:
    """Wait once for every queued pass; cancel and count what misses the budget."""
    global _open_loop_pass_queue
    queue = _open_loop_pass_queue
    if queue is None or queue.loop is not asyncio.get_running_loop():
        return
    _open_loop_pass_queue = None
    if not queue.tasks:
        return
    budget = OPEN_LOOPS_DRAIN_BUDGET_SECONDS if budget_seconds is None else budget_seconds
    _done, pending = await asyncio.wait(queue.tasks, timeout=budget)
    if pending:
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
        _record_daily_summary_fallback(
            from_mode='open_loops_daily_pass', to_mode='skipped', reason='timeout', outcome='degraded'
        )
        logger.error(
            'open_loops_daily_passes_dropped reason=drain_budget count=%d queued=%d budget_seconds=%s',
            len(pending),
            len(queue.tasks),
            budget,
        )


def _send_summary_notification(user_data: Tuple[Any, ...]) -> Optional[Tuple[str, str, Any, Any, Optional[str]]]:
    """One user's recap work. Returns the open-loops pass request, or None.

    The recap's own steps — generation, push, backfill walk, webhook — all
    complete (or raise) inside this function. The open-loops daily pass is
    deliberately NOT among them: it runs on its own executor and budget after
    this worker finishes (see ``_start_open_loops_passes``), so a slow pass
    can never delay the webhook, spend the user's 90 s recap budget or defer
    another user's recap. The return value carries
    ``(uid, date_str, start_utc, end_utc, tz_name)`` only when the pass should
    run — never for a day another worker owns or a budget already declined.
    """
    if not serving_for('CALLS_RECAP_MODE', user_data[0]) and not generated_compute_allowed(
        user_data[0], 'daily_summary'
    ):
        return
    uid = user_data[0]
    user_tz_name = user_data[2] if len(user_data) > 2 else None

    # NOTE: The daily recap is a cross-platform feature delivered by a
    # server-initiated cron that does not know the originating platform.
    # It must NOT be gated on the desktop trial paywall: passing a hardcoded
    # 'macos' to is_trial_paywalled() made the gate trip for any trial-expired
    # user, suppressing their recap on mobile/web too (#9357). The desktop
    # trial only gates desktop features, not the recap the mobile app renders.

    display_date = _display_date_for_now(user_tz_name, user_data[3] if len(user_data) > 3 else None)
    from utils.other.daily_recap import scheduled_date, delivery_allowed

    display_date = scheduled_date(uid, user_tz_name, user_data[3] if len(user_data) > 3 else None, display_date)
    start_date_utc, end_date_utc = local_day_bounds_utc(display_date, user_tz_name)
    date_str = display_date.strftime('%Y-%m-%d')

    tokens = user_data[1] if len(user_data) > 1 else None
    retry_delivery = bool(user_data[4]) if len(user_data) > 4 else False
    retry_attempt = bool(user_data[5]) if len(user_data) > 5 else False
    delivery_completed: Optional[Event] = user_data[6] if len(user_data) > 6 else None

    def prepare_delivery() -> None:
        nonlocal tokens
        if isinstance(tokens, summary_budget.DeferredTokens):
            tokens = notification_db.get_all_tokens(uid, legacy_token=tokens.legacy_token, user_document_loaded=True)
            logger.info('daily_summary_delivery_token_read owners=1 tokens=%d', len(tokens))
        elif tokens is None:
            tokens = notification_db.get_all_tokens(uid)
            logger.info('daily_summary_delivery_token_read owners=1 tokens=%d', len(tokens))

    summary_data, created, declined = _generate_and_store_daily_summary(
        uid, date_str, start_date_utc, end_date_utc, prepare_delivery=prepare_delivery
    )
    # Count current-day generation only, never the backfill walk. A generated
    # recap can also fail delivery; these are distinct recipient outcomes.
    if created:
        daily_summary_metrics.RECIPIENTS.labels(outcome='generated_retry' if retry_attempt else 'generated').inc()
        # Durable outcome token for the daily_summary_recap_generated log metric. The
        # job's in-process counters depend on a scrape sidecar; this line does not.
        logger.info('daily_summary_generated uid=%s retry=%s', uid, retry_attempt)
    elif summary_data:
        daily_summary_metrics.RECIPIENTS.labels(outcome='suppressed_existing').inc()
    pending_webhook: Optional[dict] = None
    if retry_attempt and declined == _DECLINE_LOCKED:
        # A timed-out worker may still own the day. Keep its recipient pending
        # until that worker finishes, rather than treating contention as delivery.
        # A worker that finished *after* its timeout keeps the lock for the full
        # TTL by design, so the durable record is the only proof it is done; without
        # this read the recipient stayed "locked" for 2h and pinned the whole saved
        # cohort, starving every current cohort behind it (2026-10-12).
        summary_data = daily_summaries_db.get_daily_summary_by_date(uid, date_str)
        if not summary_data or not delivery_allowed(uid, summary_data):
            raise RuntimeError('daily summary retry still locked')
        declined = None
    if summary_data and not delivery_allowed(uid, summary_data):
        raise RuntimeError('daily summary not generated')
    if summary_data and summary_data.get('notification_delivery_completed'):
        # An abandoned worker may have delivered after wait_for timed out and
        # after its coordinator saved an uncertain outcome. The receipt wins.
        if delivery_completed is not None:
            delivery_completed.set()
    elif (created or retry_delivery) and summary_data:
        try:
            prepare_delivery()
            _deliver_current_day_summary(uid, date_str, summary_data, tokens)
        except Exception as exc:
            release_daily_summary_lock(uid, date_str)
            raise DailySummaryDeliveryError(str(exc)) from exc
        # Set the local acknowledgement before any further work. Even receipt
        # persistence or backfill/webhook failure must not restore a send retry.
        if delivery_completed is not None:
            delivery_completed.set()
        daily_summaries_db.mark_daily_summary_delivery_completed(uid, str(summary_data['id']))
        # Deferred to the end of this user's work. See _deliver_day_summary_webhook.
        pending_webhook = summary_data

    # Sibling step intent: the open-loops daily pass for this user's local
    # day. Only the *request* is produced here, after the recap's own outcome
    # is settled — the coordinator dispatches it off the recap budget once
    # this worker's push, backfill and webhook have all finished. Never for a
    # day another worker owns or a budget already declined.
    pass_request: Optional[Tuple[str, str, Any, Any, Optional[str]]] = None
    if declined not in (_DECLINE_LOCKED, _DECLINE_USAGE_BUDGET):
        pass_request = (uid, date_str, start_date_utc, end_date_utc, user_tz_name)

    try:
        # Backfill only for owners who are actually still recording. Dropping the FCM-token filter in
        # get_users_for_daily_summary_indexed widened this fan-out to every user in the timezone, and an
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
            return pass_request

        _backfill_recent_daily_summaries(uid, display_date, user_tz_name)
    finally:
        # finally, not a trailing call: the dormant-owner branch above returns early
        # and backfill can raise. Either would drop the webhook for a user whose
        # summary was already stored and pushed, which is the exact loss this fix
        # exists to stop -- just moved to a different exit.
        if pending_webhook is not None:
            _deliver_day_summary_webhook(uid, pending_webhook)
    return pass_request


async def _send_bulk_summary_notification(
    users: List[Tuple[Any, ...]],
    *,
    deadline: Optional[float] = None,
    stats: Optional[DailySummaryJobStats] = None,
    target_hour: Optional[int] = None,
    cursor_key: Optional[str] = None,
    cohort_utc: Optional[datetime] = None,
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
            daily_summary_metrics.RECIPIENTS.labels(outcome='skipped_budget').inc(len(users) - i)
            if cursor_key:
                await _checkpoint(cursor_key, target_hour, str(users[i][0]), cohort_utc, counters.retry_recipients)
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
        delivery_completed = [Event() for _user in batch]
        per_user_timeout = DAILY_SUMMARY_USER_BUDGET_SECONDS
        if deadline is not None:
            per_user_timeout = max(1.0, min(per_user_timeout, deadline - monotonic()))

        tasks = [
            asyncio.wait_for(
                run_blocking(
                    postprocess_executor,
                    _send_summary_notification,
                    (*user_tokens, *(None for _ in range(max(0, 6 - len(user_tokens)))), delivery_completed[j]),
                ),
                timeout=per_user_timeout,
            )
            for j, user_tokens in enumerate(batch)
        ]
        counters.attempted += len(batch)
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for j, result in enumerate(results):
            uid = str(batch[j][0])
            if isinstance(result, BaseException) and uid in counters.prior_retry_uids:
                counters.retry_recipients.pop(uid, None)
                counters.retries_exhausted += 1
                logger.warning(
                    'daily_summary_retry_exhausted uid=%s hour=%s error_type=%s',
                    uid,
                    target_hour,
                    type(result).__name__,
                )
            elif isinstance(result, BaseException):
                counters.retry_recipients[uid] = not delivery_completed[j].is_set() and (
                    counters.retry_recipients.get(uid, False)
                    or isinstance(result, (DailySummaryDeliveryError, asyncio.TimeoutError, TimeoutError))
                )
                counters.retry_pending += 1
                if counters.retry_uid is None:
                    counters.retry_hour, counters.retry_uid = target_hour, uid
            else:
                counters.retry_recipients.pop(uid, None)
            if isinstance(result, (asyncio.TimeoutError, TimeoutError)):
                counters.timed_out += 1
                daily_summary_metrics.RECIPIENTS.labels(outcome='timed_out').inc()
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
                daily_summary_metrics.RECIPIENTS.labels(outcome='failed').inc()
                logger.error(
                    'daily_summary_user_failed uid=%s hour=%s reason=generation_error error_type=%s error=%s',
                    uid,
                    target_hour,
                    type(result).__name__,
                    result,
                )
            else:
                counters.succeeded += 1

        # Open-loops passes for the users whose recaps just completed — after
        # the batch barrier, so recap ordering and metrics are already
        # settled. Queued, not awaited: the next batch runs while they do, and
        # send_daily_summary_notification drains them once after every cohort.
        # Past the job deadline they are dropped loudly and not retried (the
        # next tick serves a different local hour); the user's loops stay in
        # the store for the next day's pass.
        pass_requests = [result for result in results if not isinstance(result, BaseException) and result is not None]
        if pass_requests and (deadline is None or monotonic() < deadline):
            _start_open_loops_passes(pass_requests)
        elif pass_requests:
            _record_daily_summary_fallback(
                from_mode='open_loops_daily_pass', to_mode='skipped', reason='timeout', outcome='degraded'
            )
            logger.info(
                'open_loops_daily_passes_dropped reason=job_budget count=%d hour=%s',
                len(pass_requests),
                target_hour,
            )

        if cursor_key and i + _BATCH_SIZE < len(users):
            await _checkpoint(
                cursor_key, target_hour, str(users[i + _BATCH_SIZE][0]), cohort_utc, counters.retry_recipients
            )

        if counters.timed_out >= DAILY_SUMMARY_MAX_ABANDONED_USERS:
            # Abandoned threads still occupy postprocess_executor slots. Past this
            # point the pool cannot serve the remaining users any faster than the
            # next execution can, so stop and let the checkpoint carry the tail.
            remaining = max(0, len(users) - (i + _BATCH_SIZE))
            counters.skipped_for_budget += remaining
            daily_summary_metrics.RECIPIENTS.labels(outcome='skipped_budget').inc(remaining)
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


def should_send_wear_device_reminder() -> bool:
    """Daily "wear your Omi" blast.

    Issue #3328: current devices record onboard when BLE drops, so a morning
    wear/disconnect nag does not recover lost audio and causes notification
    fatigue. Keep the helper so the cron can be re-enabled without hunting
    copy. Wear FCM is skipped unless the job run lock was acquired, and
    capped at one send per uid per UTC day even if this flag is re-enabled.
    """
    return False


async def send_daily_notification() -> None:
    try:
        if not should_send_wear_device_reminder():
            logger.info('Skipping daily wear reminder (#3328)')
            return None

        morning_alert_title = "omi says"
        morning_alert_body = "Wear your omi and capture your conversations today."
        morning_target_time = "08:00"
        date_str = datetime.now(pytz.utc).strftime('%Y-%m-%d')

        recipients = await _get_wear_recipients(morning_target_time)
        send_tokens: List[str] = []
        locked_users = 0
        for uid, tokens, _tz in recipients:
            if not tokens:
                continue
            got = await run_blocking(db_executor, redis_db.try_acquire_daily_wear_lock, uid, date_str)
            if not got:
                continue
            locked_users += 1
            send_tokens.extend(tokens)

        logger.info('notification_blast kind=wear users=%s tokens=%s', locked_users, len(send_tokens))
        if send_tokens:
            await send_bulk_notification(send_tokens, morning_alert_title, morning_alert_body)

    except Exception as e:
        logger.error(e)
        logger.error(f"Error sending message: {e}")
        return None


async def _get_wear_recipients(target_time: str) -> List[Any]:
    timezones_in_time = _get_timezones_at_time(target_time)
    timezone_chunks = [timezones_in_time[i : i + 30] for i in range(0, len(timezones_in_time), 30)]
    chunk_results = await asyncio.gather(
        *[run_blocking(db_executor, notification_db.get_users_id_in_timezones, chunk) for chunk in timezone_chunks]
    )
    users: List[Any] = []
    for chunk in chunk_results:
        users.extend(chunk)
    return users


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
