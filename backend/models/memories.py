from collections import defaultdict
from datetime import datetime, timezone
from enum import Enum
import re
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
    predicate: Optional[str] = Field(
        description="Canonical relation for the fact, e.g. resides_in, works_at, prefers", default=None
    )
    arguments: Dict[str, Any] = Field(
        description="Canonical proposition arguments keyed by semantic slot", default_factory=dict
    )
    subject_entity_id: Optional[str] = Field(
        description="Stable entity id for who/what the fact is about", default=None
    )
    object_entity_ids: List[str] = Field(
        description="Stable entity ids referenced by the fact arguments", default_factory=list
    )
    qualifiers: Dict[str, Any] = Field(
        description="Optional proposition qualifiers such as scope, valid_time, or epistemic_status",
        default_factory=dict,
    )

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

    def render(self) -> str:
        return render_memory(self)


def _clean_argument(value: str) -> str:
    return value.strip().strip('.').strip()


def _default_subject(category: Optional[MemoryCategory]) -> Optional[str]:
    if isinstance(category, str):
        category = MemoryCategory(category) if category in MemoryCategory._value2member_map_ else None
    if category in [MemoryCategory.system, MemoryCategory.manual, MemoryCategory.workflow]:
        return 'user'
    return None


def propositionize(content: str, category: Optional[MemoryCategory] = None) -> Dict[str, Any]:
    text = _clean_argument(content)
    lower = text.lower()
    subject = _default_subject(category)

    patterns = [
        (
            r"^(?:the user |user |they |he |she |i )?(?:currently )?(?:lives|live|resides|reside) in (?P<location>.+)$",
            'resides_in',
            'location',
        ),
        (
            r"^(?:the user |user |they |he |she |i )?(?:moved|relocated) to (?P<location>.+)$",
            'resides_in',
            'location',
        ),
        (
            r"^(?:the user |user |they |he |she |i )?(?:works|work) at (?P<organization>.+)$",
            'works_at',
            'organization',
        ),
        (
            r"^(?:the user |user |they |he |she |i )?(?:likes|like|loves|love|enjoys|enjoy|prefers|prefer) (?P<thing>.+)$",
            'prefers',
            'thing',
        ),
        (
            r"^(?:the user |user |they |he |she |i )?(?:has|have|owns|own) (?P<object>.+)$",
            'has',
            'object',
        ),
        (
            r"^(?:the user |user |they |he |she |i )?(?:is|am|are) (?P<years>\d{1,3}) years old$",
            'age_years',
            'years',
        ),
    ]

    for pattern, predicate, slot in patterns:
        match = re.match(pattern, lower, flags=re.IGNORECASE)
        if not match:
            continue
        raw_value = match.group(slot)
        value: Any = int(raw_value) if slot == 'years' else _clean_argument(text[match.start(slot) : match.end(slot)])
        return {
            'predicate': predicate,
            'arguments': {slot: value},
            'subject_entity_id': subject,
            'object_entity_ids': [],
            'qualifiers': {},
        }

    return {
        'predicate': None,
        'arguments': {},
        'subject_entity_id': subject,
        'object_entity_ids': [],
        'qualifiers': {},
    }


def _coerce_proposition(memory: Any) -> Dict[str, Any]:
    if isinstance(memory, dict):
        content = memory.get('content', '')
        category = memory.get('category')
        predicate = memory.get('predicate')
        arguments = memory.get('arguments') or {}
        subject_entity_id = memory.get('subject_entity_id')
        object_entity_ids = memory.get('object_entity_ids') or []
        qualifiers = memory.get('qualifiers') or {}
    else:
        content = getattr(memory, 'content', '')
        category = getattr(memory, 'category', None)
        predicate = getattr(memory, 'predicate', None)
        arguments = getattr(memory, 'arguments', {}) or {}
        subject_entity_id = getattr(memory, 'subject_entity_id', None)
        object_entity_ids = getattr(memory, 'object_entity_ids', []) or []
        qualifiers = getattr(memory, 'qualifiers', {}) or {}

    if predicate:
        return {
            'predicate': predicate,
            'arguments': arguments,
            'subject_entity_id': subject_entity_id,
            'object_entity_ids': object_entity_ids,
            'qualifiers': qualifiers,
        }
    return propositionize(content, category)


def render_memory(memory: Any) -> str:
    content = memory.get('content', '') if isinstance(memory, dict) else getattr(memory, 'content', '')
    proposition = _coerce_proposition(memory)
    predicate = proposition.get('predicate')
    arguments = proposition.get('arguments') or {}
    if not predicate:
        return content

    if predicate == 'resides_in' and arguments.get('location'):
        return f"Lives in {arguments['location']}"
    if predicate == 'works_at' and arguments.get('organization'):
        role = arguments.get('role')
        if role:
            return f"Works at {arguments['organization']} as {role}"
        return f"Works at {arguments['organization']}"
    if predicate == 'prefers' and arguments.get('thing'):
        return f"Prefers {arguments['thing']}"
    if predicate == 'has' and arguments.get('object'):
        return f"Has {arguments['object']}"
    if predicate == 'age_years' and arguments.get('years') is not None:
        return f"Is {arguments['years']} years old"

    rendered_args = ", ".join(f"{slot}: {value}" for slot, value in arguments.items())
    return f"{predicate.replace('_', ' ')} {rendered_args}".strip() or content


def structurally_conflicts(left: Any, right: Any) -> bool:
    left_prop = _coerce_proposition(left)
    right_prop = _coerce_proposition(right)
    if not left_prop.get('predicate') or left_prop.get('predicate') != right_prop.get('predicate'):
        return False

    left_subject = left_prop.get('subject_entity_id')
    right_subject = right_prop.get('subject_entity_id')
    if left_subject and right_subject and left_subject != right_subject:
        return False

    left_args = left_prop.get('arguments') or {}
    right_args = right_prop.get('arguments') or {}
    for slot in set(left_args).intersection(right_args):
        if left_args[slot] != right_args[slot]:
            return True
    return False


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
        proposition = _coerce_proposition(memory)
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
            predicate=proposition.get('predicate'),
            arguments=proposition.get('arguments') or {},
            subject_entity_id=proposition.get('subject_entity_id'),
            object_entity_ids=proposition.get('object_entity_ids') or [],
            qualifiers=proposition.get('qualifiers') or {},
            evidence=[evidence],
        )
        memory_db.scoring = MemoryDB.calculate_score(memory_db)
        return memory_db
