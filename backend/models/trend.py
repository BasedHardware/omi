from datetime import datetime
from enum import Enum
from typing import List

from pydantic import BaseModel


class TrendEnum(str, Enum):
    health = 'health'
    finance = 'finance'
    science = 'science'
    entrepreneurship = 'entrepreneurship'
    technology = 'technology'
    sports = 'sports'


class TrendData(BaseModel):
    memory_id: str
    date: datetime


class Trend(BaseModel):
    id: str
    name: str
    created_date: datetime
    data: int
