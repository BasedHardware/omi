from collections import defaultdict
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, List

from pydantic import BaseModel, Field

from database._client import document_id_from_seed
from models.memory import CategoryEnum


class FactCategory(str, Enum):
    core = "core"
    hobbies = "hobbies"
    lifestyle = "lifestyle"
    interests = "interests"
    habits = "habits"
    work = "work"
    skills = "skills"
    # world = "world"
    learnings = "learnings"
    other = "other"


CATEGORY_BOOSTS = {FactCategory.core.value: 1,
                   FactCategory.habits.value: 1,
                   FactCategory.work.value: 1,
                   FactCategory.skills.value: 1,
                   FactCategory.lifestyle.value: 1,
                   FactCategory.hobbies.value: 1,
                   FactCategory.interests.value: 1,
                   FactCategory.other.value: 1, }


class Fact(BaseModel):
    content: str = Field(description="The content of the fact")
    category: FactCategory = Field(description="The category of the fact", default=FactCategory.other)
    visibility: str = Field(description="The visibility of the fact", default='public')
    tags: List[str] = Field(description="The tags of the fact and learning", default=[])

    @staticmethod
    def get_facts_as_str(facts: List):
        grouped_facts = defaultdict(list)
        for f in facts:
            grouped_facts[f.category].append(f"- {f.content}\n")

        result = ''
        for category, facts_list in grouped_facts.items():
            result += f"{category.value.capitalize()}:\n"
            result += ''.join(facts_list)
            result += '\n'

        return result


class FactDB(Fact):
    id: str
    uid: str
    created_at: datetime
    updated_at: datetime

    # if manually added
    memory_id: Optional[str] = None
    memory_category: Optional[CategoryEnum] = None

    reviewed: bool = False
    user_review: Optional[bool] = None
    visibility: Optional[str] = 'public'

    manually_added: bool = False
    edited: bool = False
    deleted: bool = False
    scoring: Optional[str] = None
    app_id: Optional[str] = None

    @staticmethod
    def calculate_score(fact: 'FactDB') -> 'FactDB':
        cat_boost = (999 - CATEGORY_BOOSTS[fact.category.value]) if fact.category.value in CATEGORY_BOOSTS else 0

        user_manual_added_boost = 1
        if fact.manually_added is False:
            user_manual_added_boost = 0

        return "{:02d}_{:02d}_{:010d}".format(user_manual_added_boost, cat_boost, int(fact.created_at.timestamp()))

    @staticmethod
    def from_fact(fact: Fact, uid: str, memory_id: str, memory_category: CategoryEnum,
                  manually_added: bool) -> 'FactDB':
        fact_db = FactDB(
            id=document_id_from_seed(fact.content),
            uid=uid,
            content=fact.content,
            category=fact.category,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            memory_id=memory_id,
            memory_category=memory_category,
            manually_added=manually_added,
            user_review=True if manually_added else None,
            reviewed=True if manually_added else False,
            visibility=fact.visibility,
        )
        fact_db.scoring = FactDB.calculate_score(fact_db)
        return fact_db
