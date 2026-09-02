"""Storage for the unified feedback ledger and the daily thumbs-down report.

Firestore layout:

  Collection: feedback_events — Document ID: uuid4

    One append-only row per rating action, across all four rating surfaces.
    Shape is `models.feedback.FeedbackEvent`. No conversation text is stored
    here; `target_id` plus `chat_session_id` are the coordinates a reader uses
    to fetch context through the admin API, which decrypts on demand.

  Collection: feedback_reports — Document ID: YYYY-MM-DD (UTC)

    One materialized daily report, shape `models.feedback.FeedbackReport`.
    Entries hold event envelopes and *pointers* to the surrounding turns —
    message ids, senders, timestamps. Still no text.

Both collections live outside the per-user `users/{uid}` tree on purpose: they
are operator data, read by admin.omi.me and by anyone with Firestore access in
the GCP project, and never served to an end user.
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from database._client import db
from database.firestore_index_registry import NEGATIVE_FEEDBACK_EVENTS_QUERY
from database.read_boundary import parse_snapshot_or_none, parse_snapshots
from models.feedback import (
    FeedbackEvent,
    FeedbackReport,
    FeedbackReportEntry,
    FeedbackSurface,
    FeedbackTargetKind,
    MAX_COMMENT_LENGTH,
)

logger = logging.getLogger(__name__)

FEEDBACK_EVENTS_COLLECTION = 'feedback_events'
FEEDBACK_REPORTS_COLLECTION = 'feedback_reports'

# Firestore's document-id sentinel field path spelled literally, matching
# database/user_usage.py: tests that stub `google.cloud.firestore_v1` as a plain
# module cannot import its `field_path` submodule.
_DOCUMENT_ID_FIELD = '__name__'

# A single day's report is one Firestore document, and Firestore caps a
# document at 1 MiB. Each pointer entry is a few hundred bytes, so 500 entries
# leaves generous headroom while still covering far more thumbs-down than a
# normal day produces. When a day exceeds it the report says so (`truncated`)
# rather than silently showing a partial picture.
MAX_REPORT_ENTRIES = 500


def record_feedback_event(
    uid: str,
    surface: FeedbackSurface,
    target_kind: FeedbackTargetKind,
    target_id: str,
    value: int,
    *,
    reason: Optional[str] = None,
    comment: Optional[str] = None,
    platform: Optional[str] = None,
    app_version: Optional[str] = None,
    app_id: Optional[str] = None,
    chat_session_id: Optional[str] = None,
    target_created_at: Optional[datetime] = None,
    langsmith_run_id: Optional[str] = None,
    prompt_name: Optional[str] = None,
    prompt_commit: Optional[str] = None,
) -> Optional[str]:
    """Append one rating to the ledger. Returns the event id, or None on failure.

    Never raises: a rating write must not fail the user's request. Every caller
    already persists the rating to its own store first, so a dropped ledger row
    costs us a report line, not the user's feedback.
    """
    event_id = str(uuid.uuid4())
    record: Dict[str, Any] = {
        'id': event_id,
        'uid': uid,
        'surface': surface.value,
        'target_kind': target_kind.value,
        'target_id': target_id,
        'value': int(value),
        'created_at': datetime.now(timezone.utc),
    }
    if reason:
        record['reason'] = reason
    if comment:
        record['comment'] = comment.strip()[:MAX_COMMENT_LENGTH]
    if platform:
        record['platform'] = platform
    if app_version:
        record['app_version'] = app_version
    if app_id:
        record['app_id'] = app_id
    if chat_session_id:
        record['chat_session_id'] = chat_session_id
    if target_created_at:
        record['target_created_at'] = target_created_at
    if langsmith_run_id:
        record['langsmith_run_id'] = langsmith_run_id
    if prompt_name:
        record['prompt_name'] = prompt_name
    if prompt_commit:
        record['prompt_commit'] = prompt_commit

    try:
        db.collection(FEEDBACK_EVENTS_COLLECTION).document(event_id).set(record)
        return event_id
    except Exception as e:
        # The comment may hold user text, so log the shape and never the row.
        logger.error(f'Failed to record feedback event (surface={record["surface"]}, value={value}): {e}')
        return None


def get_feedback_event(event_id: str) -> Optional[FeedbackEvent]:
    doc = db.collection(FEEDBACK_EVENTS_COLLECTION).document(event_id).get()
    return parse_snapshot_or_none(FeedbackEvent, doc)


def list_negative_events(
    start_at: datetime, end_at: datetime, limit: int = MAX_REPORT_ENTRIES + 1
) -> List[FeedbackEvent]:
    """Every thumbs-down in [start_at, end_at), oldest first.

    Fetches one more than the caller's cap so the caller can tell "exactly the
    cap" apart from "more than the cap" without a second query.
    """
    # Imported here, not at module scope: several router test suites stub
    # `google.cloud.firestore_v1` out of `sys.modules` entirely, and a
    # top-level import would make merely importing this module fail there.
    from google.cloud.firestore_v1 import FieldFilter

    collection = db.collection(FEEDBACK_EVENTS_COLLECTION)
    query = NEGATIVE_FEEDBACK_EVENTS_QUERY.build(
        collection,
        {'value': -1, 'start_at': start_at, 'end_at': end_at},
        field_filter_factory=lambda path, op, value: FieldFilter(path, op, value),
    )
    query = query.order_by('created_at').limit(limit)

    # Fail-open: one malformed row must not cost the whole report.
    return parse_snapshots(FeedbackEvent, query.stream())


def save_report(report: FeedbackReport) -> None:
    payload = report.model_dump(mode='json')
    db.collection(FEEDBACK_REPORTS_COLLECTION).document(report.date).set(payload)


def get_report(date: str) -> Optional[FeedbackReport]:
    doc = db.collection(FEEDBACK_REPORTS_COLLECTION).document(date).get()
    return parse_snapshot_or_none(FeedbackReport, doc)


def list_report_dates(limit: int = 30) -> List[str]:
    """Most recent report dates, newest first. Document ids are ISO dates, so
    ordering by document id is the same as ordering by date."""
    try:
        docs = (
            db.collection(FEEDBACK_REPORTS_COLLECTION)
            .order_by(_DOCUMENT_ID_FIELD, direction='DESCENDING')
            .limit(limit)
            .stream()
        )
        return [doc.id for doc in docs]
    except Exception as e:
        logger.error(f'Failed to list feedback report dates: {e}')
        return []


def entry_from(event: FeedbackEvent, context: Any) -> FeedbackReportEntry:
    return FeedbackReportEntry(event=event, context=context)
