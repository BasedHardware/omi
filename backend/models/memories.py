from collections import defaultdict
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, List

from pydantic import BaseModel, Field, validator

from database._client import document_id_from_seed


class MemoryCategory(str, Enum):
    # Primary categories
    interesting = "interesting"  # External wisdom/advice FROM others (with attribution) - actionable insights
    system = "system"  # Facts ABOUT the user - preferences, opinions, realizations, network, projects
    manual = "manual"  # User-created memories (highest priority)

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


# Legacy category mapping - old categories map to system (facts about user)
LEGACY_TO_NEW_CATEGORY = {
    'core': 'system',
    'hobbies': 'system',
    'lifestyle': 'system',
    'interests': 'system',
    'work': 'system',
    'skills': 'system',
    'learnings': 'interesting',  # learnings are external insights
    'habits': 'system',
    'other': 'system',
}


# Priority scoring - manual memories always rank highest
CATEGORY_PRIORITY = {
    MemoryCategory.manual.value: 100,  # User-created, always trusted
    MemoryCategory.interesting.value: 60,  # External insights
    MemoryCategory.system.value: 50,  # Facts about user
    # Legacy categories get mapped priority
    'core': 50,
    'hobbies': 50,
    'lifestyle': 50,
    'interests': 50,
    'work': 50,
    'skills': 50,
    'learnings': 60,
    'habits': 50,
    'other': 50,
}


class Memory(BaseModel):
    content: str = Field(description="The content of the memory")
    category: MemoryCategory = Field(description="The category of the memory", default=MemoryCategory.system)
    visibility: str = Field(description="The visibility of the memory", default='private')
    tags: List[str] = Field(description="The tags of the memory and learning", default=[])

    @validator('category', pre=True)
    def map_legacy_categories(cls, v):
        """Map legacy categories to system/interesting/manual"""
        if isinstance(v, MemoryCategory):
            # Primary categories stay as-is
            if v in [MemoryCategory.system, MemoryCategory.interesting, MemoryCategory.manual]:
                return v
            # Legacy enum values map via LEGACY_TO_NEW_CATEGORY
            return MemoryCategory(LEGACY_TO_NEW_CATEGORY.get(v.value, 'system'))

        if isinstance(v, str):
            # Primary categories
            if v in ['system', 'interesting', 'manual']:
                return v

            # Legacy categories map to new ones
            if v in LEGACY_TO_NEW_CATEGORY:
                return LEGACY_TO_NEW_CATEGORY[v]

            # Unknown defaults to 'system'
            return 'system'

        # For any other unexpected type, default to system
        return 'system'

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
    def calculate_score(memory: 'MemoryDB') -> str:
        """
        Calculate score for memory ordering.
        Manual memories always rank highest, then by timestamp (newer first).
        Format: {priority}_{timestamp}
        """
        # Get category priority (manual=100, interesting=60, system/legacy=50)
        cat_value = memory.category.value if isinstance(memory.category, MemoryCategory) else str(memory.category)
        priority = CATEGORY_PRIORITY.get(cat_value, 50)

        # Timestamp for ordering within same priority
        timestamp = int(memory.created_at.timestamp())

        return "{:03d}_{:010d}".format(priority, timestamp)

    @staticmethod
    def from_memory(memory: Memory, uid: str, conversation_id: str, manually_added: bool) -> 'MemoryDB':
        # Manual memories always get 'manual' category
        # System-extracted memories preserve their category (system/interesting)
        category = MemoryCategory.manual if manually_added else memory.category

        memory_db = MemoryDB(
            id=document_id_from_seed(memory.content),
            uid=uid,
            content=memory.content,
            category=category,
            tags=memory.tags,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            conversation_id=conversation_id,
            manually_added=manually_added,
            user_review=True,
            reviewed=True,
            visibility=memory.visibility,
        )
        memory_db.scoring = MemoryDB.calculate_score(memory_db)
        return memory_db
