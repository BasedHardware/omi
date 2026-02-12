from collections import defaultdict
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, List

from pydantic import BaseModel, Field, validator

from database._client import document_id_from_seed


class MemoryCategory(str, Enum):
    # New primary categories
    interesting = "interesting"
    system = "system"
    manual = "manual"

    # Legacy categories for backward compatibility
    core = "core"
    hobbies = "hobbies"
    lifestyle = "lifestyle"
    interests = "interests"
    habits = "habits"
    work = "work"
    skills = "skills"
    learnings = "learnings"
    other = "other"
    auto = "auto"


# Only define boosts for the primary categories
CATEGORY_BOOSTS = {
    MemoryCategory.interesting.value: 1,
    MemoryCategory.system.value: 0,
    MemoryCategory.manual.value: 1,
    # Map legacy categories to appropriate new categories
    MemoryCategory.core.value: 1,
    MemoryCategory.hobbies.value: 1,
    MemoryCategory.lifestyle.value: 1,
    MemoryCategory.interests.value: 1,
    MemoryCategory.work.value: 1,
    MemoryCategory.skills.value: 1,
    MemoryCategory.learnings.value: 1,
    MemoryCategory.habits.value: 0,
    MemoryCategory.other.value: 0,
    MemoryCategory.auto.value: 0,
}


class Memory(BaseModel):
    content: str = Field(description="The content of the memory")
    category: MemoryCategory = Field(description="The category of the memory", default=MemoryCategory.interesting)
    visibility: str = Field(description="The visibility of the memory", default='private')
    tags: List[str] = Field(description="The tags of the memory and learning", default=[])

    @validator('category', pre=True)
    def map_legacy_categories(cls, v):
        """Map legacy categories to new ones when creating memories"""
        if isinstance(v, MemoryCategory):
            return v

        # If it's a string value
        legacy_to_new = {
            'core': 'system',
            'hobbies': 'system',
            'lifestyle': 'system',
            'interests': 'system',
            'work': 'system',
            'skills': 'system',
            'learnings': 'system',
            'habits': 'system',
            'other': 'system',
            'auto': 'system',
        }

        if isinstance(v, str):
            # If it's already one of our main categories, use it directly
            if v in ['interesting', 'system', 'manual']:
                return v

            # For legacy categories, map them to new ones
            if v in legacy_to_new:
                return legacy_to_new[v]

            # For any unknown string value, default to "interesting"
            return 'interesting'

        # For any other unexpected type, default to interesting
        return 'interesting'

    @staticmethod
    def get_memories_as_str(memories: List):
        result = ''
        for f in memories:
            # Include created_at if available (for MemoryDB objects)
            if hasattr(f, 'created_at') and f.created_at:
                date_str = f.created_at.strftime('%Y-%m-%d %H:%M:%S UTC')
                result += f"- {f.content} ({date_str})\n"
            else:
                result += f"- {f.content}\n"

        return result


class MemoryDB(Memory):
    id: str
    uid: str
    created_at: datetime
    updated_at: datetime

    # TODO: remove these fields and use conversation_id and conversation_category after migration
    memory_id: Optional[str] = None

    conversation_id: Optional[str] = None

    reviewed: bool = False
    user_review: Optional[bool] = None
    visibility: Optional[str] = 'public'

    manually_added: bool = False
    edited: bool = False
    scoring: Optional[str] = None
    app_id: Optional[str] = None
    data_protection_level: Optional[str] = None
    is_locked: bool = False
    kg_extracted: bool = False

    def __init__(self, **data):
        super().__init__(**data)
        self.memory_id = self.conversation_id

    @staticmethod
    def calculate_score(memory: 'MemoryDB') -> 'MemoryDB':
        cat_boost = (999 - CATEGORY_BOOSTS[memory.category.value]) if memory.category.value in CATEGORY_BOOSTS else 0

        user_manual_added_boost = 1
        if memory.manually_added is False:
            user_manual_added_boost = 0

        return "{:02d}_{:02d}_{:010d}".format(user_manual_added_boost, cat_boost, int(memory.created_at.timestamp()))

    @staticmethod
    def from_memory(memory: Memory, uid: str, conversation_id: str, manually_added: bool) -> 'MemoryDB':
        memory_db = MemoryDB(
            id=document_id_from_seed(memory.content),
            uid=uid,
            content=memory.content,
            category=memory.category,
            tags=memory.tags,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            conversation_id=conversation_id,
            manually_added=manually_added,
            user_review=True if manually_added else None,
            reviewed=True,
            visibility=memory.visibility,
        )
        memory_db.scoring = MemoryDB.calculate_score(memory_db)
        return memory_db
