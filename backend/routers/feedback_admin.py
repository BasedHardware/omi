"""Admin endpoints for the daily thumbs-down report.

Access is deliberately narrow. Every route here requires the `X-Admin-Key`
header to match the backend `ADMIN_KEY`, the same gate `fair_use_admin` uses.
The only caller is admin.omi.me, whose route handlers add the key server-side
after checking the browser's Firebase token against `adminData/{uid}` — so
reaching this data needs both an admin account on admin.omi.me and a key that
lives only in Cloud Run's runtime secrets. Nothing here is reachable with a
user's Firebase token.

The context route is the one place negative-feedback conversation text is
decrypted. It decrypts one event's window per request and returns it without
persisting it, which is why the stored report holds pointers only.
"""

import hashlib
import hmac
import logging
import os
from datetime import date as date_cls, datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel

import database.feedback as feedback_db
from jobs.feedback_daily_report import previous_utc_day, run as run_daily_report
from models.feedback import FeedbackContextHydrated, FeedbackReport
from utils.feedback_context import hydrate_context

logger = logging.getLogger(__name__)

router = APIRouter()

ADMIN_KEY = os.getenv('ADMIN_KEY', '')


def _verify_admin_key(
    x_admin_key: str = Header(..., alias='X-Admin-Key'),
    x_admin_user: Optional[str] = Header(default=None, alias='X-Admin-User'),
) -> str:
    """Constant-time admin key check. Returns the identity to log.

    `ADMIN_KEY` is one shared secret, so its hash identifies the *deployment*,
    not the person — an audit line carrying only that cannot say which admin
    read a user's chat, which is the whole point of auditing this route.
    admin.omi.me therefore forwards the caller's Firebase uid as `X-Admin-User`
    alongside the key, server-side, after it has already verified that uid
    against `adminData/{uid}`. The uid is untrusted on its own (anything
    holding the key could set it) but it is not a second gate — it is the
    attribution that makes an authorized read traceable to a person.
    """
    if not ADMIN_KEY or not hmac.compare_digest(x_admin_key, ADMIN_KEY):
        raise HTTPException(status_code=403, detail='Invalid admin key')
    key_id = hashlib.sha256(x_admin_key.encode()).hexdigest()[:8]
    if x_admin_user:
        return f'admin:{key_id}/{x_admin_user[:64]}'
    return f'admin:{key_id}/unattributed'


def _parse_date(value: str) -> date_cls:
    """Parse a report date, rejecting anything that is not a real date.

    Returns the `date` rather than the caller's string on purpose: report
    documents are keyed by canonical `YYYY-MM-DD`, and `strptime` happily
    accepts unpadded `2026-9-1`. Looking a report up by the raw input would
    then 404 against a report that exists. Callers use `.isoformat()`.
    """
    try:
        return datetime.strptime(value, '%Y-%m-%d').date()
    except ValueError:
        raise HTTPException(status_code=400, detail='date must be YYYY-MM-DD')


class FeedbackReportDatesResponse(BaseModel):
    dates: List[str]


class FeedbackReportGenerateResponse(BaseModel):
    date: str
    total_negative: int
    truncated: bool


@router.get('/v1/admin/feedback/reports', tags=['admin'], response_model=FeedbackReportDatesResponse)
def list_feedback_reports(
    admin_id: str = Depends(_verify_admin_key),
    limit: int = Query(default=30, ge=1, le=90),
):
    """Dates that have a materialized report, newest first."""
    return FeedbackReportDatesResponse(dates=feedback_db.list_report_dates(min(limit, 90)))


@router.get('/v1/admin/feedback/reports/{report_date}', tags=['admin'], response_model=FeedbackReport)
def get_feedback_report(
    report_date: str,
    admin_id: str = Depends(_verify_admin_key),
):
    """One day's report: counts plus pointer windows. Carries no message text."""
    day = _parse_date(report_date).isoformat()
    report = feedback_db.get_report(day)
    if report is None:
        raise HTTPException(status_code=404, detail=f'No feedback report for {day}')
    return report


@router.post(
    '/v1/admin/feedback/reports/{report_date}/generate',
    tags=['admin'],
    response_model=FeedbackReportGenerateResponse,
)
def generate_feedback_report(
    report_date: str,
    admin_id: str = Depends(_verify_admin_key),
):
    """Build (or rebuild) one day's report.

    This is the scheduler's entry point and also the manual backfill path: a
    day whose nightly run failed can be regenerated as long as its events are
    still in the ledger.
    """
    day = _parse_date(report_date)
    logger.info(f'{admin_id} generating feedback report for {day.isoformat()}')
    report = run_daily_report(day)
    return FeedbackReportGenerateResponse(
        date=report.date,
        total_negative=report.total_negative,
        truncated=report.truncated,
    )


@router.post(
    '/v1/admin/feedback/reports/generate-yesterday',
    tags=['admin'],
    response_model=FeedbackReportGenerateResponse,
)
def generate_yesterdays_feedback_report(admin_id: str = Depends(_verify_admin_key)):
    """Nightly cron target — no date arithmetic in the scheduler config."""
    day = previous_utc_day()
    logger.info(f'{admin_id} generating nightly feedback report for {day.isoformat()}')
    report = run_daily_report(day)
    return FeedbackReportGenerateResponse(
        date=report.date,
        total_negative=report.total_negative,
        truncated=report.truncated,
    )


@router.get(
    '/v1/admin/feedback/events/{event_id}/context',
    tags=['admin'],
    response_model=FeedbackContextHydrated,
)
def get_feedback_event_context(
    event_id: str,
    report_date: Optional[str] = Query(
        default=None,
        description='Report containing this event. Given, the stored pointer window is reused.',
    ),
    admin_id: str = Depends(_verify_admin_key),
):
    """Decrypt and return the conversation around one thumbs-down.

    This is the only endpoint that returns user conversation text. Each call is
    logged with the event id and the admin key hash, so reads of user chat are
    attributable after the fact.
    """
    event = feedback_db.get_feedback_event(event_id)
    if event is None:
        raise HTTPException(status_code=404, detail=f'No feedback event {event_id}')

    pointer = None
    if report_date:
        report = feedback_db.get_report(_parse_date(report_date).isoformat())
        if report:
            pointer = next((e.context for e in report.entries if e.event.id == event_id), None)

    if pointer is None:
        # No stored window (event outside any report, or a report predating a
        # window-shape change) — resolve it live so the route still answers.
        from utils.feedback_context import resolve_context

        pointer = resolve_context(
            event.uid,
            event.target_kind,
            event.target_id,
            chat_session_id=event.chat_session_id,
        )
        pointer.event_id = event_id

    logger.info(
        f'{admin_id} read feedback context for event {event_id} (uid hash {hashlib.sha256(event.uid.encode()).hexdigest()[:8]})'
    )
    return hydrate_context(pointer)
