from enum import Enum
from typing import List

from pydantic import BaseModel, Field


class TrendEnum(str, Enum):
    acquisition = "acquisition"
    ceo = "ceo"
    company = "company"
    event = "event"
    founder = "founder"
    industry = "industry"
    innovation = "innovation"
    investment = "investment"
    partnership = "partnership"
    product = "product"
    research = "research"
    tool = "tool"


class Trend(BaseModel):
    category: TrendEnum = Field(description="The category identified")
    topics: List[str] = Field(description="The specific topic corresponding the category")
