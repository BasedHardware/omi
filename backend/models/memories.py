from collections import defaultdict
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, List, Dict, Any

from pydantic import BaseModel, Field, validator

from database._client import document_id_from_seed


class MemoryCategory(str, Enum):
    # New primary categories
    interesting = "interesting"
    system = "system"
    manual = "manual"
    workflow = "workflow"

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
    MemoryCategory.workflow.value: 1,
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
    headline: Optional[str] = Field(description="Short headline for notification preview (max 5 words)", default=None)

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
            if v in ['interesting', 'system', 'manual', 'workflow']:
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


class Evidence(BaseModel):
    evidence_id: str
    source_id: Optional[str] = None
    source_type: str = "unknown"
    artifact_ref: Dict[str, Any] = Field(default_factory=dict)
    source_signal: str = "unknown"
    extractor_id: str = "unknown"
    extractor_version: str = "unknown"
    capture_confidence: float = 0.5
    independence_group: str
    redaction_status: str = "active"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @staticmethod
    def from_source(
        *,
        source_id: Optional[str],
        source_type: str,
        source_signal: str,
        extractor_id: str,
        extractor_version: str,
        artifact_ref: Optional[Dict[str, Any]] = None,
        capture_confidence: Optional[float] = None,
        independence_group: Optional[str] = None,
        created_at: Optional[datetime] = None,
    ) -> 'Evidence':
        now = created_at or datetime.now(timezone.utc)
        group = independence_group or source_id or f"{source_type}:unknown"
        ref = artifact_ref or {}
        return Evidence(
            evidence_id=document_id_from_seed(
                "|".join(
                    [
                        "evidence",
                        source_id or "",
                        source_type,
                        source_signal,
                        extractor_id,
                        extractor_version,
                        str(sorted(ref.items())),
                    ]
                )
            ),
            source_id=source_id,
            source_type=source_type,
            artifact_ref=ref,
            source_signal=source_signal,
            extractor_id=extractor_id,
            extractor_version=extractor_version,
            capture_confidence=capture_confidence if capture_confidence is not None else 0.5,
            independence_group=group,
            created_at=now,
        )


def merge_evidence_sets(existing: List[dict], incoming: List[dict]) -> List[dict]:
    merged = []
    seen = set()
    for item in list(existing) + list(incoming):
        if hasattr(item, 'dict'):
            item = item.dict()
        if not isinstance(item, dict):
            continue
        evidence_id = item.get('evidence_id')
        if evidence_id and evidence_id in seen:
            continue
        if evidence_id:
            seen.add(evidence_id)
        merged.append(item)
    return merged


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
    evidence: List[Evidence] = Field(default_factory=list)

    # Temporal lifecycle — the "constantly updated brain". All optional, so existing
    # docs (which lack these fields) read back as active with no migration.
    #   valid_at:      when the fact became true (defaults to created_at)
    #   invalid_at:    when the fact stopped being true; None == currently active.
    #                  A superseded/retracted memory is invalidated (not deleted) so
    #                  history is kept, but it is excluded from every retrieval path.
    #   superseded_by: id of the newer memory that replaced this one (if any).
    valid_at: Optional[datetime] = None
    invalid_at: Optional[datetime] = None
    superseded_by: Optional[str] = None

    def __init__(self, **data):
        super().__init__(**data)
        self.memory_id = self.conversation_id

    @property
    def is_active(self) -> bool:
        """A memory is active (currently true) until it is invalidated."""
        return self.invalid_at is None

    @staticmethod
    def calculate_score(memory: 'MemoryDB') -> 'MemoryDB':
        cat_boost = (999 - CATEGORY_BOOSTS[memory.category.value]) if memory.category.value in CATEGORY_BOOSTS else 0

        user_manual_added_boost = 1
        if memory.manually_added is False:
            user_manual_added_boost = 0

        return "{:02d}_{:02d}_{:010d}".format(user_manual_added_boost, cat_boost, int(memory.created_at.timestamp()))

    @staticmethod
    def from_memory(
        memory: Memory,
        uid: str,
        conversation_id: Optional[str],
        manually_added: bool,
        *,
        source_id: Optional[str] = None,
        source_type: Optional[str] = None,
        source_signal: Optional[str] = None,
        artifact_ref: Optional[Dict[str, Any]] = None,
        extractor_id: str = "memory_extractor",
        extractor_version: str = "v1",
        capture_confidence: Optional[float] = None,
        independence_group: Optional[str] = None,
    ) -> 'MemoryDB':
        now = datetime.now(timezone.utc)
        evidence_source_id = source_id if source_id is not None else conversation_id
        evidence_source_type = source_type or ("conversation" if conversation_id else "developer_api")
        evidence_source_signal = source_signal or ("manual" if manually_added else "transcription")
        evidence = Evidence.from_source(
            source_id=evidence_source_id,
            source_type=evidence_source_type,
            source_signal=evidence_source_signal,
            extractor_id=extractor_id,
            extractor_version=extractor_version,
            artifact_ref=artifact_ref,
            capture_confidence=capture_confidence,
            independence_group=independence_group,
            created_at=now,
        )
        memory_db = MemoryDB(
            id=document_id_from_seed(memory.content),
            uid=uid,
            content=memory.content,
            category=memory.category,
            tags=memory.tags,
            created_at=now,
            updated_at=now,
            valid_at=now,
            conversation_id=conversation_id,
            manually_added=manually_added,
            user_review=True if manually_added else None,
            reviewed=True,
            visibility=memory.visibility,
            evidence=[evidence],
        )
        memory_db.scoring = MemoryDB.calculate_score(memory_db)
        return memory_db
