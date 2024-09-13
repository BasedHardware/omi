from typing import Dict, List

import database.trends as trends_db
from fastapi import APIRouter

router = APIRouter()


@router.get("/v1/trends", response_model=Dict[str, List[Dict]], tags=['trends'])
def get_trends():
    trends = trends_db.get_trends_data()
    return trends
