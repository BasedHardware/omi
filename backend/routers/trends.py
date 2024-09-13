from typing import List

from fastapi import APIRouter

import database.trends as trends_db

router = APIRouter()


@router.get("/v1/trends", response_model=List, tags=['trends'])
def get_trends():
    return trends_db.get_trends_data()
