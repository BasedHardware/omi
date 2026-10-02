"""Scores — daily, weekly, and overall productivity scores computed from action items."""

from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query

from models.score import DailyScore, Scores
import database.action_items as action_items_db
import database.notifications as notification_db
from utils.other import endpoints as auth
from utils.request_validation import validate_calendar_date

router = APIRouter()


@router.get('/v1/daily-score', tags=['scores'], response_model=DailyScore)
def get_daily_score(
    date: str | None = Query(None, pattern=r'^\d{4}-\d{2}-\d{2}$'),
    uid: str = Depends(auth.get_current_user_uid),
):
    date = validate_calendar_date(date)
    return action_items_db.get_daily_score(uid, date=date, tz=ZoneInfo(notification_db.resolve_user_timezone(uid)))


@router.get('/v1/scores', tags=['scores'], response_model=Scores)
def get_scores(
    date: str | None = Query(None, pattern=r'^\d{4}-\d{2}-\d{2}$'),
    uid: str = Depends(auth.get_current_user_uid),
):
    date = validate_calendar_date(date)
    return action_items_db.get_scores(uid, date=date, tz=ZoneInfo(notification_db.resolve_user_timezone(uid)))
