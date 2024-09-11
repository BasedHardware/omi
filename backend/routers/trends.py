from typing import Dict, List

import database.trends as trends_db
from fastapi import APIRouter
from models.trend import Trend

router = APIRouter()


@router.get("/v1/trends", response_model=List[Dict[str, Trend]], tags=['trends'])
def get_trends(offset: int = 0, limit: int = 10):
    trends = trends_db.get_trends_data()
    return trends
