from typing import List

from fastapi import APIRouter, HTTPException

import database.trends as trends_db
from models.trend import TrendEnum

router = APIRouter()


@router.get("/v1/trends", response_model=List, tags=['trends'])
def get_trends():
    return trends_db.get_trends_data()


@router.get("/v1/trends/{category}", response_model=List, tags=['trends'])
def get_trends_by_category(category: str):
    """Return the trend entries for a single category (best and worst variants).

    The only existing trends route returns every category at once, forcing a client to
    pull the whole blob and filter locally. This exposes one category directly. Public,
    matching the sibling GET /v1/trends (trends are global, not per-user).
    """
    if category not in {c.value for c in TrendEnum}:
        raise HTTPException(status_code=404, detail="Unknown trend category")
    entries = [row for row in trends_db.get_trends_data() if row.get('category') == category]
    if not entries:
        raise HTTPException(status_code=404, detail="No trends for this category yet")
    return entries
