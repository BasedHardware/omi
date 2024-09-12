from datetime import datetime
from enum import Enum
from typing import List

from pydantic import BaseModel


class TrendEnum(str, Enum):
    technologies = "technologies"
    ceos = "ceos"
    events = "events"
    companies = "companies"
    startups = "startups"
    innovations = "innovations"
    products = "products"
    acquisitions = "acquisitions"
    investments = "investments"
    partnerships = "partnerships"
    founders = "founders"
    industry = "industry"
    regulations = "regulations"
    research = "research"
    failures = "failures"


class TrendData(BaseModel):
    memory_id: str
    date: datetime


class Trend(BaseModel):
    id: str
    name: str
    created_at: datetime
