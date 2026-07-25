from datetime import datetime, timezone
from enum import Enum
import re
from typing import Any, Dict, List, Mapping, Optional, Sequence, cast

from pydantic import BaseModel, Field, computed_field, field_validator

from config.memory_confidence import (
    CONFIDENCE_BANDS,
    HIGH_CAPTURE_THRESHOLD,
    LOW_CAPTURE_THRESHOLD,
    SOURCE_SIGNAL_CAPTURE_PRIORS,
    VERACITY_PRIORS,
)
from database._client import document_id_from_seed
from models.memory_domain import tier_to_layer
from models.product_memory import MemoryTier


def decide_initial_memory_tier(manually_added: bool, durability: Optional[str]) -> MemoryTier:
    """Tier a memory at birth.

    Faithful to the memory design (memories are born short-term and promoted on
    corroboration): user-asserted facts and explicitly long-horizon facts are
    durable from the start; everything else starts short-term and can be
    promoted later (see the corroboration path in process_conversation).
    """
    if manually_added:
        return MemoryTier.long_term
    if (durability or '').lower() == 'long_term':
        return MemoryTier.long_term
    return MemoryTier.short_term


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


class SubjectAttribution(str, Enum):
    user = "user"
    third_party = "third_party"
    unknown = "unknown"
    legacy_assumed = "legacy_assumed"


class UncertaintyReason(str, Enum):
    single_source = "single_source"
    low_capture_signal = "low_capture_signal"
    contradicted_by = "contradicted_by"
    stale = "stale"
    third_party_subject = "third_party_subject"


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
    visibility: Optional[str] = Field(description="The visibility of the memory", default='private')
    tags: List[str] = Field(description="The tags of the memory and learning", default_factory=list)
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
    subject_attribution: SubjectAttribution = Field(
        description="How the memory subject was attributed", default=SubjectAttribution.unknown
    )
    object_entity_ids: List[str] = Field(
        description="Stable entity ids referenced by the fact arguments", default_factory=list
    )
    qualifiers: Dict[str, Any] = Field(
        description="Optional proposition qualifiers such as scope, valid_time, or epistemic_status",
        default_factory=dict,
    )
    capture_confidence: Optional[float] = Field(
        description="Fixed confidence that the source was captured correctly", default=None
    )
    veracity: Optional[float] = Field(description="Current belief that the fact is true", default=None)
    uncertainty_reasons: List[str] = Field(
        description="Reasons this fact needs caution or review", default_factory=list
    )
    durability: Optional[str] = Field(description="Expected durability horizon for the fact", default=None)

    @field_validator('category', mode='before')
    @classmethod
    def map_legacy_categories(cls, v: Any) -> Any:
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
    def get_memories_as_str(memories: Sequence[Any]) -> str:
        result = ''
        for f in memories:
            content = getattr(f, 'content', '')
            created_at = getattr(f, 'created_at', None)
            # Include created_at if available (for MemoryDB objects)
            if isinstance(created_at, datetime):
                date_str = created_at.strftime('%Y-%m-%d %H:%M:%S UTC')
                result += f"- {content} ({date_str})\n"
            else:
                result += f"- {content}\n"

        return result

    def render(self) -> str:
        return render_memory(self)


def _clean_argument(value: str) -> str:
    return value.strip().strip('.').strip()


def _default_subject(category: Optional[MemoryCategory | str]) -> Optional[str]:
    if isinstance(category, str):
        category = MemoryCategory(category) if category in MemoryCategory._value2member_map_ else None
    if category in [MemoryCategory.system, MemoryCategory.manual, MemoryCategory.workflow]:
        return 'user'
    return None


def propositionize(content: str, category: Optional[MemoryCategory | str] = None) -> Dict[str, Any]:
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
        memory_dict = cast(Mapping[str, Any], memory)
        content_value = memory_dict.get('content', '')
        content = content_value if isinstance(content_value, str) else str(content_value)
        category = memory_dict.get('category')
        predicate = memory_dict.get('predicate')
        arguments_value: Any = memory_dict.get('arguments') or {}
        arguments = cast(Dict[str, Any], arguments_value) if isinstance(arguments_value, dict) else {}
        subject_entity_id = memory_dict.get('subject_entity_id')
        subject_attribution = memory_dict.get('subject_attribution', SubjectAttribution.unknown)
        object_entity_ids_value: Any = memory_dict.get('object_entity_ids') or []
        object_entity_ids = (
            cast(List[str], object_entity_ids_value) if isinstance(object_entity_ids_value, list) else []
        )
        qualifiers_value: Any = memory_dict.get('qualifiers') or {}
        qualifiers = cast(Dict[str, Any], qualifiers_value) if isinstance(qualifiers_value, dict) else {}
    else:
        content_value = getattr(memory, 'content', '')
        content = content_value if isinstance(content_value, str) else str(content_value)
        category = getattr(memory, 'category', None)
        predicate = getattr(memory, 'predicate', None)
        arguments_value = getattr(memory, 'arguments', {}) or {}
        arguments = cast(Dict[str, Any], arguments_value) if isinstance(arguments_value, dict) else {}
        subject_entity_id = getattr(memory, 'subject_entity_id', None)
        subject_attribution = getattr(memory, 'subject_attribution', SubjectAttribution.unknown)
        object_entity_ids_value = getattr(memory, 'object_entity_ids', []) or []
        object_entity_ids = (
            cast(List[str], object_entity_ids_value) if isinstance(object_entity_ids_value, list) else []
        )
        qualifiers_value = getattr(memory, 'qualifiers', {}) or {}
        qualifiers = cast(Dict[str, Any], qualifiers_value) if isinstance(qualifiers_value, dict) else {}

    if predicate:
        return {
            'predicate': predicate,
            'arguments': arguments,
            'subject_entity_id': subject_entity_id,
            'subject_attribution': subject_attribution,
            'object_entity_ids': object_entity_ids,
            'qualifiers': qualifiers,
        }
    proposition = propositionize(content, category)
    proposition['subject_attribution'] = subject_attribution
    return proposition


def render_memory(memory: Any) -> str:
    if isinstance(memory, dict):
        content_value = cast(Mapping[str, Any], memory).get('content', '')
    else:
        content_value = getattr(memory, 'content', '')
    content = content_value if isinstance(content_value, str) else str(content_value)
    proposition = _coerce_proposition(memory)
    predicate = proposition.get('predicate')
    arguments_value: Any = proposition.get('arguments') or {}
    arguments = cast(Dict[str, Any], arguments_value) if isinstance(arguments_value, dict) else {}
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

    left_args_value: Any = left_prop.get('arguments') or {}
    right_args_value: Any = right_prop.get('arguments') or {}
    left_args = cast(Dict[str, Any], left_args_value) if isinstance(left_args_value, dict) else {}
    right_args = cast(Dict[str, Any], right_args_value) if isinstance(right_args_value, dict) else {}
    for slot in set(left_args).intersection(right_args):
        if left_args[slot] != right_args[slot]:
            return True
    return False


class Evidence(BaseModel):
    evidence_id: str
    source_id: Optional[str] = None
    source_type: str = "unknown"
    artifact_ref: Dict[str, Any] = Field(default_factory=dict[str, Any])
    source_signal: str = "unknown"
    extractor_id: str = "unknown"
    extractor_version: str = "unknown"
    capture_confidence: float = 0.5
    independence_group: str
    redaction_status: str = "active"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    client_device_id: Optional[str] = None

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
        client_device_id: Optional[str] = None,
    ) -> 'Evidence':
        now = created_at or datetime.now(timezone.utc)
        group = independence_group or source_id or f"{source_type}:unknown"
        ref = artifact_ref or {}
        resolved_capture = (
            capture_confidence
            if capture_confidence is not None
            else capture_confidence_for_source_signal(source_signal)
        )
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
            capture_confidence=resolved_capture,
            independence_group=group,
            created_at=now,
            client_device_id=client_device_id,
        )


def capture_confidence_for_source_signal(source_signal: str) -> float:
    return SOURCE_SIGNAL_CAPTURE_PRIORS.get(source_signal, SOURCE_SIGNAL_CAPTURE_PRIORS['unknown'])


def confidence_band(value: float) -> str:
    band = 'low'
    for name, threshold in sorted(CONFIDENCE_BANDS.items(), key=lambda item: item[1]):
        if value >= threshold:
            band = name
    return band


EvidenceInput = Evidence | Mapping[str, Any]


def _model_or_dict_to_dict(item: EvidenceInput) -> Dict[str, Any]:
    if isinstance(item, BaseModel):
        return item.model_dump()
    return dict(item)


def compute_veracity(
    evidence_set: Optional[Sequence[EvidenceInput]],
    subject_attribution: SubjectAttribution | str = SubjectAttribution.unknown,
) -> float:
    evidence_items = [
        _model_or_dict_to_dict(item)
        for item in evidence_set or []
        if _model_or_dict_to_dict(item).get('redaction_status', 'active') != 'tombstoned'
    ]
    groups = {
        group
        for item in evidence_items
        for group in [item.get('independence_group') or item.get('source_id')]
        if isinstance(group, str) and group
    }
    if not groups:
        return VERACITY_PRIORS['base']

    score = VERACITY_PRIORS['single_independent_group']
    if len(groups) > 1:
        score += (len(groups) - 1) * VERACITY_PRIORS['additional_independent_group']

    capture_values = [
        capture
        for item in evidence_items
        for capture in [item.get('capture_confidence')]
        if isinstance(capture, (float, int))
    ]
    max_capture = max(capture_values) if capture_values else SOURCE_SIGNAL_CAPTURE_PRIORS['unknown']
    if max_capture >= HIGH_CAPTURE_THRESHOLD:
        score += VERACITY_PRIORS['high_capture_bonus']
    if max_capture < LOW_CAPTURE_THRESHOLD:
        score -= VERACITY_PRIORS['low_capture_penalty']
    if (
        subject_attribution == SubjectAttribution.third_party
        or subject_attribution == SubjectAttribution.third_party.value
    ):
        score -= VERACITY_PRIORS['third_party_penalty']

    return max(0.0, min(VERACITY_PRIORS['maximum'], score))


def uncertainty_reasons_for(
    evidence_set: Optional[Sequence[EvidenceInput]],
    subject_attribution: SubjectAttribution | str = SubjectAttribution.unknown,
) -> List[str]:
    reasons: List[str] = []
    evidence_items = [
        _model_or_dict_to_dict(item)
        for item in evidence_set or []
        if _model_or_dict_to_dict(item).get('redaction_status', 'active') != 'tombstoned'
    ]
    groups = {
        group
        for item in evidence_items
        for group in [item.get('independence_group') or item.get('source_id')]
        if isinstance(group, str) and group
    }
    if len(groups) <= 1:
        reasons.append(UncertaintyReason.single_source.value)
    if any(
        isinstance(item.get('capture_confidence'), (float, int))
        and cast(float, item.get('capture_confidence')) < LOW_CAPTURE_THRESHOLD
        for item in evidence_items
    ):
        reasons.append(UncertaintyReason.low_capture_signal.value)
    if (
        subject_attribution == SubjectAttribution.third_party
        or subject_attribution == SubjectAttribution.third_party.value
    ):
        reasons.append(UncertaintyReason.third_party_subject.value)
    return reasons


def confidence_fields_for_evidence(
    evidence_set: Optional[Sequence[EvidenceInput]],
    subject_attribution: SubjectAttribution | str = SubjectAttribution.unknown,
    existing_capture_confidence: Optional[float] = None,
) -> Dict[str, Any]:
    evidence_items = [_model_or_dict_to_dict(item) for item in evidence_set or []]
    capture = existing_capture_confidence
    if capture is None and evidence_items:
        first = evidence_items[0]
        first_capture = first.get('capture_confidence')
        capture = float(first_capture) if isinstance(first_capture, (float, int)) else None
    if capture is None:
        capture = SOURCE_SIGNAL_CAPTURE_PRIORS['unknown']
    return {
        'capture_confidence': capture,
        'veracity': compute_veracity(evidence_items, subject_attribution),
        'uncertainty_reasons': uncertainty_reasons_for(evidence_items, subject_attribution),
    }


def merge_evidence_sets(existing: Sequence[EvidenceInput], incoming: Sequence[EvidenceInput]) -> List[Dict[str, Any]]:
    merged: List[Dict[str, Any]] = []
    seen: dict[str, int] = {}
    for item in list(existing) + list(incoming):
        item = _model_or_dict_to_dict(item)
        evidence_id = item.get('evidence_id')
        if isinstance(evidence_id, str) and evidence_id in seen:
            existing_index = seen[evidence_id]
            existing_item = merged[existing_index]
            if (
                existing_item.get('redaction_status') == 'tombstoned'
                and item.get('redaction_status', 'active') != 'tombstoned'
            ):
                merged[existing_index] = item
            continue
        if isinstance(evidence_id, str):
            seen[evidence_id] = len(merged)
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
    is_baseline: bool = False
    evidence: List[Evidence] = Field(default_factory=list)

    # Canonical memory tiering. Legacy API/service boundaries set this to None
    # so non-cohort users cannot receive Short-term/Long-term rollout state.
    memory_tier: Optional[MemoryTier] = None

    @computed_field
    @property
    def layer(self) -> Optional[str]:
        """Canonical product lifecycle layer (Q6/WS-K); derived from memory_tier at serialization only."""
        if self.memory_tier is None:
            return None
        return tier_to_layer(self.memory_tier).value

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

    primary_capture_device: Optional[str] = None
    capture_device_ids: List[str] = Field(default_factory=list)

    def __init__(self, **data: Any) -> None:
        super().__init__(**data)
        # Deprecated alias for legacy clients: always mirror `id`. Older code stored
        # `memory_id = conversation_id` on the doc; serving that stored value makes
        # desktop's ServerMemory decoder reject the whole memories list, so the alias
        # must be normalized here rather than trusted from Firestore.
        self.memory_id = self.id

    @property
    def is_active(self) -> bool:
        """A memory is active (currently true) until it is invalidated."""
        return self.invalid_at is None

    @staticmethod
    def calculate_score(memory: 'MemoryDB') -> str:
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
        subject_entity_id: Optional[str] = None,
        subject_attribution: Optional[SubjectAttribution] = None,
        client_device_id: Optional[str] = None,
    ) -> 'MemoryDB':
        now = datetime.now(timezone.utc)
        proposition = _coerce_proposition(memory)
        resolved_subject = subject_entity_id or proposition.get('subject_entity_id')
        resolved_attribution = (
            subject_attribution or proposition.get('subject_attribution') or memory.subject_attribution
        )
        if resolved_subject == 'user' and resolved_attribution == SubjectAttribution.unknown:
            resolved_attribution = SubjectAttribution.user
        memory_id = document_id_from_seed(memory.content)
        evidence_source_id = source_id if source_id is not None else conversation_id
        if not evidence_source_id:
            evidence_source_id = f"external:{memory_id}"
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
            client_device_id=client_device_id,
        )
        confidence_fields = confidence_fields_for_evidence([evidence], resolved_attribution)
        memory_db = MemoryDB(
            id=memory_id,
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
            subject_entity_id=resolved_subject,
            subject_attribution=resolved_attribution,
            object_entity_ids=proposition.get('object_entity_ids') or [],
            qualifiers=proposition.get('qualifiers') or {},
            evidence=[evidence],
            capture_confidence=confidence_fields['capture_confidence'],
            veracity=confidence_fields['veracity'],
            uncertainty_reasons=confidence_fields['uncertainty_reasons'],
            durability=memory.durability,
            memory_tier=decide_initial_memory_tier(manually_added, memory.durability),
        )
        memory_db.scoring = MemoryDB.calculate_score(memory_db)
        return memory_db


class ShortTermMemory(Memory):
    id: str
    uid: str
    created_at: datetime
    updated_at: datetime
    evidence: List[Evidence] = Field(default_factory=list)
    status: str = "pending_consolidation"
    allowed_uses: List[str] = Field(default_factory=lambda: ["retrieval", "consolidation"])
    scope: str = "global"
    source_signal: str = "unknown"
    consolidated_at: Optional[datetime] = None
    consolidated_commit_id: Optional[str] = None
    soft_pruned_at: Optional[datetime] = None

    @staticmethod
    def from_memory(
        memory: Memory,
        uid: str,
        *,
        source_id: Optional[str],
        source_type: str,
        source_signal: str,
        artifact_ref: Optional[Dict[str, Any]] = None,
        extractor_id: str = "short_term_extractor",
        extractor_version: str = "v1",
        subject_entity_id: Optional[str] = None,
        subject_attribution: Optional[SubjectAttribution] = None,
        scope: str = "global",
        importance: Optional[float] = None,
    ) -> 'ShortTermMemory':
        now = datetime.now(timezone.utc)
        proposition = _coerce_proposition(memory)
        resolved_subject = subject_entity_id or proposition.get('subject_entity_id')
        resolved_attribution = (
            subject_attribution or proposition.get('subject_attribution') or memory.subject_attribution
        )
        evidence = Evidence.from_source(
            source_id=source_id,
            source_type=source_type,
            source_signal=source_signal,
            extractor_id=extractor_id,
            extractor_version=extractor_version,
            artifact_ref=artifact_ref,
            independence_group=source_id,
            created_at=now,
        )
        confidence_fields = confidence_fields_for_evidence([evidence], resolved_attribution)
        qualifiers_value: Any = proposition.get('qualifiers') or {}
        qualifiers = cast(Dict[str, Any], qualifiers_value) if isinstance(qualifiers_value, dict) else {}
        qualifiers.setdefault('valid_from', now)
        short_term = ShortTermMemory(
            id=document_id_from_seed(f"short-term|{uid}|{source_id}|{memory.content}"),
            uid=uid,
            content=memory.content,
            category=memory.category,
            visibility=memory.visibility,
            tags=memory.tags,
            headline=memory.headline,
            predicate=proposition.get('predicate'),
            arguments=proposition.get('arguments') or {},
            subject_entity_id=resolved_subject,
            subject_attribution=resolved_attribution,
            object_entity_ids=proposition.get('object_entity_ids') or [],
            qualifiers=qualifiers,
            capture_confidence=confidence_fields['capture_confidence'],
            veracity=confidence_fields['veracity'],
            uncertainty_reasons=confidence_fields['uncertainty_reasons'],
            durability=memory.durability,
            created_at=now,
            updated_at=now,
            evidence=[evidence],
            source_signal=source_signal,
            scope=scope,
        )
        if importance is not None:
            short_term.qualifiers['importance'] = importance
        return short_term
