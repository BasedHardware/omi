from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

from database._client import document_id_from_seed
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

    @staticmethod
    def get_facts_as_str(facts):
        existing_facts = [f"{f.content} ({f.category.value})" for f in facts]
        return '' if not existing_facts else '\n- ' + '\n- '.join(existing_facts)


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

    @staticmethod
    def from_fact(fact: Fact, uid: str, memory_id: str, memory_category: CategoryEnum) -> 'FactDB':
        return FactDB(
            id=document_id_from_seed(fact.content),
            uid=uid,
            content=fact.content,
            category=fact.category,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            memory_id=memory_id,
            memory_category=memory_category,
        )
