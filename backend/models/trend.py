from datetime import datetime
from enum import Enum
from typing import List

from pydantic import BaseModel, Field


class TrendEnum(str, Enum):
    acquisitions = "acquisitions"
    ceos = "ceos"
    companies = "companies"
    events = "events"
    founders = "founders"
    industries = "industries"
    innovations = "innovations"
    investments = "investments"
    partnerships = "partnerships"
    products = "products"
    research = "research"
    technologies = "technologies"


class TrendData(BaseModel):
    memory_id: str
    date: datetime


class Trend(BaseModel):
    category: TrendEnum = Field(description="The category of the trend")
    topics: List[str] = Field(
        description="List of the topics for the corresponding category")
