from typing import List

from fastapi import APIRouter

import database.trends as trends_db

v1_router = APIRouter(prefix="/v1", tags=['trends'])


@v1_router.get("/trends", response_model=List)
def get_trends():
    return trends_db.get_trends_data()
