"""Scores — daily, weekly, and overall productivity scores computed from action items."""

import logging
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException, Query

from models.score import DailyScore, Scores
import database.action_items as action_items_db
import database.notifications as notification_db
from utils.other import endpoints as auth
from utils.request_validation import validate_calendar_date

logger = logging.getLogger(__name__)

router = APIRouter()


def _resolve_safe_timezone(uid: str) -> ZoneInfo:
    """Resolve user timezone safely; fallback to UTC on any invalid or unresolvable timezone."""
    try:
        tz_name = notification_db.resolve_user_timezone(uid)
        if tz_name:
            return ZoneInfo(tz_name)
    except Exception as exc:
        logger.warning("Falling back to UTC for uid=%s due to invalid or unresolvable timezone: %s", uid, exc)
    return ZoneInfo("UTC")


@router.get('/v1/daily-score', tags=['scores'], response_model=DailyScore)
def get_daily_score(
    date: str | None = Query(None, pattern=r'^\d{4}-\d{2}-\d{2}$'),
    uid: str = Depends(auth.get_current_user_uid),
):
    if not uid or not uid.strip():
        raise HTTPException(status_code=401, detail="User identification required")
    clean_uid = uid.strip()
    clean_date = validate_calendar_date(date)
    tz = _resolve_safe_timezone(clean_uid)
    try:
        return action_items_db.get_daily_score(clean_uid, date=clean_date, tz=tz)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Failed to calculate daily score for uid=%s date=%s", clean_uid, clean_date)
        raise HTTPException(status_code=500, detail="Failed to retrieve daily productivity score") from exc


@router.get('/v1/scores', tags=['scores'], response_model=Scores)
def get_scores(
    date: str | None = Query(None, pattern=r'^\d{4}-\d{2}-\d{2}$'),
    uid: str = Depends(auth.get_current_user_uid),
):
    if not uid or not uid.strip():
        raise HTTPException(status_code=401, detail="User identification required")
    clean_uid = uid.strip()
    clean_date = validate_calendar_date(date)
    tz = _resolve_safe_timezone(clean_uid)
    try:
        return action_items_db.get_scores(clean_uid, date=clean_date, tz=tz)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Failed to calculate scores for uid=%s date=%s", clean_uid, clean_date)
        raise HTTPException(status_code=500, detail="Failed to retrieve productivity scores") from exc
