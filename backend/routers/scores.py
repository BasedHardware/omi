"""Scores — daily, weekly, and overall productivity scores computed from action items."""

from fastapi import APIRouter, Depends, HTTPException, Query

import database.action_items as action_items_db
from utils.other import endpoints as auth

router = APIRouter()


@router.get('/v1/daily-score', tags=['scores'])
def get_daily_score(
    date: str | None = Query(None, pattern=r'^\d{4}-\d{2}-\d{2}$'),
    uid: str = Depends(auth.get_current_user_uid),
):
    try:
        return action_items_db.get_daily_score(uid, date=date)
    except ValueError:
        raise HTTPException(status_code=400, detail='Invalid date. Use a real calendar date in YYYY-MM-DD format.')


@router.get('/v1/scores', tags=['scores'])
def get_scores(
    date: str | None = Query(None, pattern=r'^\d{4}-\d{2}-\d{2}$'),
    uid: str = Depends(auth.get_current_user_uid),
):
    return action_items_db.get_scores(uid, date=date)
