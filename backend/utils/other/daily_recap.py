"""V4 recap producer: completed local days, explicit states, revision-aware retry.

No additional model call in shadow. The scheduler reuses the existing indexed
recipient queries, including their partial-read and retry contracts.
"""

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from config.refactor_modes import cohort_configured, serving_for, shadow_or_serve
import database.conversations as conversations_db
from utils.conversations.calls_metrics import observe
from utils.daily_summary_validation import require_daily_summary
from utils.llm.daily_recap_fingerprint import input_fingerprint, FINGERPRINT_FIELD

FLAG = 'CALLS_RECAP_MODE'
GRACE = timedelta(hours=1)
DUE_HOUR = 1


def completed_day(tz_name, at=None):
    at = at or datetime.now(timezone.utc)
    try:
        zone = ZoneInfo(tz_name or 'UTC')
    except (ValueError, KeyError):
        zone = timezone.utc
    return (at.astimezone(zone) - GRACE).date() - timedelta(days=1)


def scheduled_date(uid, tz_name, at, legacy_date):
    if not shadow_or_serve(FLAG):
        return legacy_date
    date = completed_day(tz_name, at)
    observe('recap_timing', 'agree' if date == legacy_date else 'disagree')
    return date if serving_for(FLAG, uid) else legacy_date


async def select_recipients(timezones, target_hour, legacy_selector):
    rows, error, complete = await legacy_selector(timezones, target_hour)
    if not cohort_configured(FLAG):
        return rows, error, complete
    selected = {str(row[0]): row for row in rows if not serving_for(FLAG, str(row[0])) or target_hour == DUE_HOUR}
    if target_hour == DUE_HOUR:
        # Across a day, at most one extra read of each indexed enabled recipient.
        # Sequential hour partitions avoid a 24-way spike and preserve read failures.
        for hour in range(24):
            if hour == target_hour:
                continue
            extra, extra_error, extra_complete = await legacy_selector(timezones, hour)
            error = error or extra_error
            complete = complete and extra_complete
            selected.update((str(row[0]), row) for row in extra if serving_for(FLAG, str(row[0])))
    return list(selected.values()), error, complete


def _persist(n, uid, date, existing, payload):
    if existing:
        payload = {**payload, 'id': existing['id']}
        for field in ('visibility', 'notification_delivery_completed'):
            if field in existing:
                payload[field] = existing[field]
        n.daily_summaries_db.update_daily_summary(uid, existing['id'], payload)
    else:
        payload = {**payload, 'id': payload.get('id') or 'recap-' + date}
        n.daily_summaries_db.create_daily_summary(uid, payload)
    return payload


def _state(n, uid, date, existing, status, fingerprint=None):
    now = datetime.now(timezone.utc)
    payload = {
        **(existing or {}),
        'date': date,
        'created_at': (existing or {}).get('created_at') or now,
        'status': status,
        'generated_at': None,
    }
    if fingerprint is not None:
        payload[FINGERPRINT_FIELD] = fingerprint
    result = _persist(n, uid, date, existing, payload)
    observe('recap_' + status, 'agree')
    return result


def generate(uid, date_str, start_date_utc, end_date_utc, *, legacy, prepare_delivery=None, user_initiated=False):
    # Imports stay lazy; tests can inject dependencies at the producer seam.
    from utils.other import notifications as n

    if not serving_for(FLAG, uid):
        return legacy(uid, date_str, start_date_utc, end_date_utc, prepare_delivery=prepare_delivery)
    compute_allowed = n.generated_compute_allowed(uid, 'daily_summary')
    if not n.try_acquire_daily_summary_lock(uid, date_str):
        return None, False, n.DAILY_SUMMARY_DECLINE_LOCKED
    existing = None
    looked_up = False
    try:
        existing = n.daily_summaries_db.get_daily_summary_by_date(uid, date_str)
        looked_up = True
        if not compute_allowed:
            if existing and existing.get('status') == 'generated':
                return existing, False, 'usage_budget_exhausted'
            _state(n, uid, date_str, existing, 'not_generated')
            return None, False, 'usage_budget_exhausted'
        now = datetime.now(timezone.utc)
        if not user_initiated and now < end_date_utc + GRACE:
            _state(n, uid, date_str, existing, 'pending')
            return None, False, n.DAILY_SUMMARY_DECLINE_NOTHING_TO_SUMMARIZE
        rows = (
            conversations_db.get_conversations(
                uid, start_date=start_date_utc, end_date=end_date_utc, date_field='started_at'
            )
            or []
        )
        fingerprint = input_fingerprint(rows, extra_revision_fields=('content_kind', 'status'))
        if (
            existing
            and existing.get('status') in ('generated', 'no_recordings')
            and existing.get(FINGERPRINT_FIELD) == fingerprint
        ):
            if existing['status'] == 'no_recordings':
                return None, False, n.DAILY_SUMMARY_DECLINE_NO_CONVERSATIONS
            return existing, False, None
        if not rows:
            _state(n, uid, date_str, existing, 'no_recordings', fingerprint)
            return None, False, n.DAILY_SUMMARY_DECLINE_NO_CONVERSATIONS
        # V2 is the only content classifier. Read its serving projection; never reclassify.
        from utils.conversations.media_consumers import eligible_conversations

        rows = eligible_conversations(uid, rows)
        if not rows:
            # Captures remain in history and M counts them. Exclusion from
            # derived output is not evidence that nothing was recorded.
            _state(n, uid, date_str, existing, 'not_generated', fingerprint)
            return None, False, n.DAILY_SUMMARY_DECLINE_NOTHING_TO_SUMMARIZE
        conversations = n.deserialize_conversations([row for row in rows if not row.get('is_locked')])
        conversations = [c for c in conversations if not c.discarded]
        if not conversations or not any(c.transcript_segments for c in conversations):
            _state(n, uid, date_str, existing, 'pending', fingerprint)
            return None, False, n.DAILY_SUMMARY_DECLINE_NOTHING_TO_SUMMARIZE
        conversations = n.bound_daily_summary_conversations(uid, date_str, conversations)
        if not any(n.conversation_has_summary_content(c) for c in conversations):
            _state(n, uid, date_str, existing, 'pending', fingerprint)
            return None, False, n.DAILY_SUMMARY_DECLINE_NOTHING_TO_SUMMARIZE
        pending = _state(n, uid, date_str, existing, 'pending', fingerprint)
        existing = pending
        if prepare_delivery:
            prepare_delivery()
        payload = n.generate_comprehensive_daily_summary(
            uid,
            conversations,
            date_str,
            start_date_utc,
            end_date_utc,
            memories_learned=n.memories_learned_payload(uid, conversations, start_date_utc, end_date_utc),
        )
        # Pending/failed state rows remain retryable; malformed generated content
        # must never replace them (or a previous valid recap) in the store.
        require_daily_summary(payload, uid=uid, operation='v4_generation_candidate')
        payload.update(status='generated', generated_at=datetime.now(timezone.utc), **{FINGERPRINT_FIELD: fingerprint})
        payload = _persist(n, uid, date_str, pending, payload)
        observe('recap_generated', 'agree')
        return payload, True, None
    except Exception:
        observe('recap_generation', 'error')
        # A durable failed row permits the next tick to retry; never call it generated.
        try:
            if looked_up:
                _state(n, uid, date_str, existing, 'failed')
        except Exception:
            observe('recap_state_write', 'error')
        raise
    finally:
        n.release_daily_summary_lock(uid, date_str)


def delivery_allowed(uid, payload):
    """A durable pending/failed stub is never proof that the model finished."""
    return payload.get('status') in (None, 'generated')


def finish_legacy_stub(existing, payload):
    """A mode rollback still completes already-admitted status rows in place."""
    if existing and existing.get('status') is not None:
        return {**payload, 'status': 'generated', 'generated_at': datetime.now(timezone.utc)}
    return payload
