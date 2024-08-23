from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

from models.memory import CategoryEnum


class FactCategory(str, Enum):
    hobbies = "hobbies"
    lifestyle = "lifestyle"
    interests = "interests"
    habits = "habits"
    work = "work"
    skills = "skills"
    other = "other"


class Fact(BaseModel):
    content: str = Field(description="The content of the fact")
    category: FactCategory = Field(description="The category of the fact", default=FactCategory.other)


class FactDB(Fact):
    id: str
    uid: str
    created_at: datetime
    updated_at: datetime

    memory_id: str
    memory_category: CategoryEnum

    reviewed: bool = False
    user_review: Optional[bool] = None

    manually_added: bool = False
    edited: bool = False
    deleted: bool = False
