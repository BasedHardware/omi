"""Scores — daily, weekly, and overall productivity scores computed from action items."""

import logging
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException, Query, status

from models.score import DailyScore, Scores
import database.action_items as action_items_db
import database.notifications as notification_db
from utils.other import endpoints as auth
from utils.request_validation import validate_calendar_date

router = APIRouter()
logger = logging.getLogger(__name__)


def _resolve_safe_timezone(uid: str) -> ZoneInfo:
    """Safely resolve user timezone with robust UTC fallback."""
    try:
        raw_tz = notification_db.resolve_user_timezone(uid)
        if raw_tz:
            return ZoneInfo(str(raw_tz).strip())
    except (ZoneInfoNotFoundError, ValueError, Exception) as exc:
        logger.warning(f"Failed to resolve timezone for user {uid}, falling back to UTC: {exc}")
    return ZoneInfo("UTC")


@router.get('/v1/daily-score', tags=['scores'], response_model=DailyScore)
def get_daily_score(
    date: str | None = Query(None, pattern=r'^\d{4}-\d{2}-\d{2}$'),
    uid: str = Depends(auth.get_current_user_uid),
):
    if not uid or not uid.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid user identifier")

    date = validate_calendar_date(date)
    tz = _resolve_safe_timezone(uid)
    try:
        return action_items_db.get_daily_score(uid, date=date, tz=tz)
    except Exception as exc:
        logger.error(f"Error computing daily score for user {uid}: {exc}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve daily score",
        ) from exc


@router.get('/v1/scores', tags=['scores'], response_model=Scores)
def get_scores(
    date: str | None = Query(None, pattern=r'^\d{4}-\d{2}-\d{2}$'),
    uid: str = Depends(auth.get_current_user_uid),
):
    if not uid or not uid.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid user identifier")

    date = validate_calendar_date(date)
    tz = _resolve_safe_timezone(uid)
    try:
        return action_items_db.get_scores(uid, date=date, tz=tz)
    except Exception as exc:
        logger.error(f"Error computing scores for user {uid}: {exc}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve scores",
        ) from exc
