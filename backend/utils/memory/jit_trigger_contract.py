"""Deterministic local-watchlist trigger contracts.

This module is intentionally a pure boundary.  It compiles the bounded
``MemoryItem.trigger_condition`` payload into local predicates and evaluates
synthetic observations without model calls, network access, or persistence.
Unknown condition keys are rejected; observations that do not contain enough
context for a safe answer return ``triage`` instead of guessing.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timezone
from enum import Enum
import hashlib
import json
import re
from typing import Any, Dict, List, Mapping, Optional, Pattern, Sequence, Tuple
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from models.jit_proactivity import (
    JIT_AMBIGUOUS_NANO_TRIAGES_PER_DAY,
    JIT_CONTENT_FREE_ID_PATTERN,
    JIT_FULL_TURNS_PER_CANDIDATE,
    JIT_MAX_CALENDAR_EVENTS,
    JIT_PLANNED_NOTIFICATIONS_PER_TRIGGER_PER_DAY,
    JIT_POLICY_VALID_FOR_SECONDS,
    JIT_TOTAL_PROACTIVE_NOTIFICATIONS_PER_DAY,
)
from models.memory_evidence import SourceState
from models.product_memory import MemoryItem, MemoryItemStatus, MemoryKind, MemorySubjectScope
from utils.memory.belief_model import belief_model_enabled, record_passes_proactive_bar

TRIGGER_SCHEMA_VERSION = "jit_trigger.v1"
TRIGGER_POLICY_VERSION = "jit_trigger_policy.v1"
MAX_CONDITION_KEYS = 12
MAX_ENTITY_ALIASES = 16
MAX_ENTITY_ALIAS_CHARS = 80
MAX_KEYWORDS = 32
MAX_KEYWORD_CHARS = 80
MAX_REGEXES = 8
MAX_REGEX_CHARS = 160
MAX_APPS = 16
MAX_WINDOWS = 16
MAX_WINDOW_CHARS = 120
MAX_CONTEXT_TEXT_CHARS = 8_000
MAX_CALENDAR_EVENTS = JIT_MAX_CALENDAR_EVENTS
MAX_FEEDBACK_IDS = 32
MAX_FEEDBACK_NOTE_CHARS = 240
MAX_TRIGGER_ACTION_PROMPT_CHARS = 2_000

PLANNED_NOTIFICATIONS_PER_TRIGGER_PER_DAY = JIT_PLANNED_NOTIFICATIONS_PER_TRIGGER_PER_DAY
TOTAL_PROACTIVE_NOTIFICATIONS_PER_DAY = JIT_TOTAL_PROACTIVE_NOTIFICATIONS_PER_DAY
AMBIGUOUS_NANO_TRIAGES_PER_DAY = JIT_AMBIGUOUS_NANO_TRIAGES_PER_DAY
FULL_AGENT_TURNS_PER_CANDIDATE = JIT_FULL_TURNS_PER_CANDIDATE
EMBEDDING_MATCH_SIMILARITY = 0.82
EMBEDDING_TRIAGE_SIMILARITY = 0.74


class TriggerDecisionStatus(str, Enum):
    match = "match"
    no_match = "no_match"
    triage = "triage"


class TriggerFeedbackAction(str, Enum):
    useful = "useful"
    false_positive = "false_positive"
    missed_or_late = "missed_or_late"
    # Released aliases remain readable while new clients use the explicit
    # product vocabulary above.
    reinforce = "reinforce"
    dismiss = "dismiss"
    snooze = "snooze"
    disable = "disable"


class TriggerTimeCondition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    weekdays: Tuple[int, ...] = ()
    start: time
    end: time
    timezone_name: str = Field(default="UTC", alias="timezone")

    @field_validator("weekdays")
    @classmethod
    def validate_weekdays(cls, value: Sequence[int]) -> Tuple[int, ...]:
        normalized = tuple(sorted(set(value)))
        if any(day < 0 or day > 6 for day in normalized):
            raise ValueError("time weekdays must use ISO weekday indexes 0..6")
        return normalized

    @field_validator("timezone_name")
    @classmethod
    def validate_timezone_name(cls, value: str) -> str:
        normalized = (value or "").strip()
        if not normalized:
            raise ValueError("time timezone must not be blank")
        try:
            ZoneInfo(normalized)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("time timezone must be an installed IANA timezone") from exc
        return normalized


class TriggerCalendarCondition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_keywords: Tuple[str, ...] = ()
    event_types: Tuple[str, ...] = ()

    @field_validator("event_keywords", "event_types")
    @classmethod
    def normalize_terms(cls, value: Sequence[str]) -> Tuple[str, ...]:
        normalized = tuple(sorted({_normalize_text(term) for term in value if _normalize_text(term)}))
        if any(len(term) > MAX_KEYWORD_CHARS for term in normalized):
            raise ValueError("calendar terms exceed the length limit")
        return normalized

    @model_validator(mode="after")
    def require_selector(self) -> "TriggerCalendarCondition":
        if not self.event_keywords and not self.event_types:
            raise ValueError("calendar condition requires event_keywords or event_types")
        if len(self.event_keywords) + len(self.event_types) > MAX_KEYWORDS:
            raise ValueError("calendar condition has too many selectors")
        return self


class TriggerEmbeddingCondition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prototype_id: str
    prototype_revision: str
    model_id: str
    model_version: str
    language: str
    min_similarity: float = EMBEDDING_MATCH_SIMILARITY

    @field_validator("prototype_id", "prototype_revision", "model_id", "model_version", "language")
    @classmethod
    def validate_attestation_identifier(cls, value: str) -> str:
        normalized = (value or "").strip()
        if not normalized or len(normalized) > MAX_KEYWORD_CHARS:
            raise ValueError("embedding attestation identifier is invalid")
        return normalized

    @field_validator("min_similarity")
    @classmethod
    def validate_similarity(cls, value: float) -> float:
        if float(value) != EMBEDDING_MATCH_SIMILARITY:
            raise ValueError("embedding min_similarity must match the server policy")
        return float(value)


class TriggerEmbeddingAttestation(BaseModel):
    """Content-free identity of the exact local scorer that produced scores."""

    model_config = ConfigDict(extra="forbid")

    model_id: str
    model_version: str
    language: str
    prototype_revision: str

    @field_validator("model_id", "model_version", "language", "prototype_revision")
    @classmethod
    def validate_identifier(cls, value: str) -> str:
        normalized = (value or "").strip()
        if not normalized or len(normalized) > MAX_KEYWORD_CHARS:
            raise ValueError("embedding attestation identifier is invalid")
        return normalized


class TriggerEmbeddingPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    enabled: bool = False
    match_similarity: float = EMBEDDING_MATCH_SIMILARITY
    triage_similarity: float = EMBEDDING_TRIAGE_SIMILARITY
    model_id: Optional[str] = None
    model_version: Optional[str] = None
    language: Optional[str] = None

    @model_validator(mode="after")
    def validate_attested_enablement(self) -> "TriggerEmbeddingPolicy":
        if self.match_similarity != EMBEDDING_MATCH_SIMILARITY or self.triage_similarity != EMBEDDING_TRIAGE_SIMILARITY:
            raise ValueError("embedding policy thresholds must match the ratified v1 contract")
        identifiers = (self.model_id, self.model_version, self.language)
        if self.enabled and any(not (value or "").strip() for value in identifiers):
            raise ValueError("enabled embedding policy requires a complete scorer attestation")
        if not self.enabled and any(value is not None for value in identifiers):
            raise ValueError("disabled embedding policy must not advertise a scorer")
        return self


class TriggerRuntimePolicy(BaseModel):
    """Versioned, backend-authored budgets consumed by every JIT client."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = TRIGGER_POLICY_VERSION
    planned_notifications_per_trigger_per_day: int = PLANNED_NOTIFICATIONS_PER_TRIGGER_PER_DAY
    total_proactive_notifications_per_day: int = TOTAL_PROACTIVE_NOTIFICATIONS_PER_DAY
    ambiguous_nano_triages_per_day: int = AMBIGUOUS_NANO_TRIAGES_PER_DAY
    full_agent_turns_per_candidate: int = FULL_AGENT_TURNS_PER_CANDIDATE
    max_calendar_events: int = MAX_CALENDAR_EVENTS
    valid_for_seconds: int = JIT_POLICY_VALID_FOR_SECONDS
    paid_boundary_refresh_required: bool = True
    embedding: TriggerEmbeddingPolicy = Field(default_factory=TriggerEmbeddingPolicy)

    @field_validator("schema_version")
    @classmethod
    def validate_policy_version(cls, value: str) -> str:
        if value != TRIGGER_POLICY_VERSION:
            raise ValueError("unsupported trigger policy version")
        return value

    @field_validator(
        "planned_notifications_per_trigger_per_day",
        "total_proactive_notifications_per_day",
        "ambiguous_nano_triages_per_day",
        "full_agent_turns_per_candidate",
        "max_calendar_events",
        "valid_for_seconds",
    )
    @classmethod
    def validate_positive_budget(cls, value: int) -> int:
        if type(value) is not int or value <= 0:
            raise ValueError("trigger policy budgets must be positive integers")
        return value


DEFAULT_TRIGGER_RUNTIME_POLICY = TriggerRuntimePolicy()


class TriggerAction(BaseModel):
    """Server-authored work purchased after a deterministic local match.

    The action deliberately carries no provider/model choice and no client
    enrollment bit.  It is an opaque instruction for one bounded agent turn;
    the backend rollout authority remains the only admission authority.
    """

    model_config = ConfigDict(extra="forbid")

    type: str = "agent_prompt"
    prompt: str

    @field_validator("type")
    @classmethod
    def validate_type(cls, value: str) -> str:
        if value != "agent_prompt":
            raise ValueError("trigger action type must be agent_prompt")
        return value

    @field_validator("prompt")
    @classmethod
    def validate_prompt(cls, value: str) -> str:
        normalized = " ".join((value or "").split())
        if not normalized or len(normalized) > MAX_TRIGGER_ACTION_PROMPT_CHARS:
            raise ValueError("trigger action prompt is blank or oversized")
        return normalized


class TriggerCondition(BaseModel):
    """Serializable condition payload stored in ``MemoryItem.trigger_condition``."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    schema_version: str = TRIGGER_SCHEMA_VERSION
    match_mode: str = "all"
    entity_aliases: Dict[str, Tuple[str, ...]] = Field(default_factory=dict)
    keywords: Tuple[str, ...] = ()
    regex: Tuple[str, ...] = ()
    apps: Tuple[str, ...] = ()
    windows: Tuple[str, ...] = ()
    time: Optional[TriggerTimeCondition] = None
    calendar: Optional[TriggerCalendarCondition] = None
    embedding: Optional[TriggerEmbeddingCondition] = None
    action: Optional[TriggerAction] = None

    @field_validator("schema_version")
    @classmethod
    def validate_schema_version(cls, value: str) -> str:
        if value != TRIGGER_SCHEMA_VERSION:
            raise ValueError(f"unsupported trigger schema version: {value!r}")
        return value

    @field_validator("match_mode")
    @classmethod
    def validate_match_mode(cls, value: str) -> str:
        if value not in {"all", "any"}:
            raise ValueError("match_mode must be 'all' or 'any'")
        return value

    @field_validator("entity_aliases")
    @classmethod
    def normalize_entity_aliases(cls, value: Mapping[str, Sequence[str]]) -> Dict[str, Tuple[str, ...]]:
        if len(value) > MAX_CONDITION_KEYS:
            raise ValueError("trigger has too many entity conditions")
        normalized: Dict[str, Tuple[str, ...]] = {}
        for raw_entity, raw_aliases in value.items():
            entity = _normalize_text(raw_entity)
            if not entity:
                raise ValueError("entity alias keys must not be blank")
            aliases = tuple(sorted({_bounded_term(alias, MAX_ENTITY_ALIAS_CHARS) for alias in raw_aliases}))
            if not aliases or len(aliases) > MAX_ENTITY_ALIASES:
                raise ValueError("each entity must have 1..16 aliases")
            normalized[entity] = aliases
        return normalized

    @field_validator("keywords", "apps")
    @classmethod
    def normalize_short_terms(cls, value: Sequence[str]) -> Tuple[str, ...]:
        normalized = tuple(sorted({_bounded_term(term, MAX_KEYWORD_CHARS) for term in value}))
        if len(normalized) > MAX_KEYWORDS:
            raise ValueError("trigger has too many keywords")
        return normalized

    @field_validator("windows")
    @classmethod
    def normalize_window_terms(cls, value: Sequence[str]) -> Tuple[str, ...]:
        normalized = tuple(sorted({_bounded_term(term, MAX_WINDOW_CHARS) for term in value}))
        if len(normalized) > MAX_WINDOWS:
            raise ValueError("trigger has too many window selectors")
        return normalized

    @field_validator("regex")
    @classmethod
    def validate_regexes(cls, value: Sequence[str]) -> Tuple[str, ...]:
        if len(value) > MAX_REGEXES:
            raise ValueError("trigger has too many regex selectors")
        normalized: List[str] = []
        for pattern in value:
            bounded = _bounded_term(pattern, MAX_REGEX_CHARS, normalize=False)
            if re.search(r"\\[1-9]|\(\?(?:[=!<]|P=)", bounded) or re.search(
                r"\([^)]*(?:\*|\+|\{\d+(?:,\d*)?\})[^)]*\)(?:\*|\+|\{)",
                bounded,
            ):
                raise ValueError("trigger regex uses an unsafe backtracking construct")
            try:
                re.compile(bounded, re.IGNORECASE)
            except re.error as exc:
                raise ValueError(f"invalid trigger regex: {exc}") from exc
            normalized.append(bounded)
        return tuple(sorted(set(normalized)))

    @model_validator(mode="after")
    def validate_nonempty_and_bounds(self) -> "TriggerCondition":
        condition_keys = sum(
            bool(value)
            for value in (
                self.entity_aliases,
                self.keywords,
                self.regex,
                self.apps,
                self.windows,
                self.time,
                self.calendar,
                self.embedding,
            )
        )
        if condition_keys == 0:
            raise ValueError("trigger condition must contain at least one selector")
        if condition_keys > MAX_CONDITION_KEYS:
            raise ValueError("trigger condition exceeds the key limit")
        return self


class CalendarObservation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = ""
    event_type: str = ""
    starts_at: Optional[datetime] = None
    ends_at: Optional[datetime] = None

    @field_validator("starts_at", "ends_at")
    @classmethod
    def validate_aware_time(cls, value: Optional[datetime]) -> Optional[datetime]:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("calendar observation timestamps must be timezone-aware")
        return value


class TriggerObservation(BaseModel):
    """Local evidence supplied by a caller; no provider/model is consulted."""

    model_config = ConfigDict(extra="forbid")

    event_id: Optional[str] = None
    text: str = ""
    entity_labels: Tuple[str, ...] = ()
    app_name: Optional[str] = None
    window_title: Optional[str] = None
    occurred_at: Optional[datetime] = None
    calendar_events: Tuple[CalendarObservation, ...] = ()
    calendar_authorized: bool = False
    embedding_scores: Dict[str, float] = Field(default_factory=dict)
    embedding_attestation: Optional[TriggerEmbeddingAttestation] = None

    @field_validator("occurred_at")
    @classmethod
    def validate_aware_time(cls, value: Optional[datetime]) -> Optional[datetime]:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("trigger observation timestamps must be timezone-aware")
        return value

    @field_validator("text")
    @classmethod
    def bound_text(cls, value: str) -> str:
        return (value or "")[:MAX_CONTEXT_TEXT_CHARS]

    @field_validator("entity_labels")
    @classmethod
    def normalize_entity_labels(cls, value: Sequence[str]) -> Tuple[str, ...]:
        return tuple(sorted({_bounded_term(item, MAX_ENTITY_ALIAS_CHARS) for item in value}))

    @field_validator("app_name", "window_title")
    @classmethod
    def normalize_optional_text(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        return value.strip()[:MAX_WINDOW_CHARS] or None

    @field_validator("calendar_events")
    @classmethod
    def bound_calendar_events(cls, value: Sequence[CalendarObservation]) -> Tuple[CalendarObservation, ...]:
        if len(value) > MAX_CALENDAR_EVENTS:
            raise ValueError("calendar observation has too many events")
        return tuple(value)

    @field_validator("embedding_scores")
    @classmethod
    def validate_embedding_scores(cls, value: Mapping[str, float]) -> Dict[str, float]:
        normalized: Dict[str, float] = {}
        for key, score in value.items():
            if not 0.0 <= float(score) <= 1.0:
                raise ValueError("embedding scores must be between 0 and 1")
            normalized[str(key).strip()] = float(score)
        return dict(sorted(normalized.items()))

    @model_validator(mode="after")
    def require_attestation_for_embedding_scores(self) -> "TriggerObservation":
        if self.embedding_scores and self.embedding_attestation is None:
            raise ValueError("embedding scores require an exact local scorer attestation")
        return self


class TriggerDecision(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: TriggerDecisionStatus
    reason: str
    matched_conditions: Tuple[str, ...] = ()
    missing_conditions: Tuple[str, ...] = ()
    matched_fraction: float = 0.0
    observation_fingerprint: str = ""


class TriggerFeedback(BaseModel):
    model_config = ConfigDict(extra="forbid")

    feedback_id: str
    action: TriggerFeedbackAction
    recorded_at: datetime
    snoozed_until: Optional[datetime] = None
    note: Optional[str] = None

    @field_validator("feedback_id")
    @classmethod
    def validate_feedback_id(cls, value: str) -> str:
        normalized = (value or "").strip()
        if not re.fullmatch(JIT_CONTENT_FREE_ID_PATTERN, normalized):
            raise ValueError("trigger feedback id must be a content-free SHA-256 digest")
        return normalized

    @field_validator("recorded_at", "snoozed_until")
    @classmethod
    def validate_aware_time(cls, value: Optional[datetime]) -> Optional[datetime]:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("trigger feedback timestamps must be timezone-aware")
        return value

    @field_validator("note")
    @classmethod
    def bound_note(cls, value: Optional[str]) -> Optional[str]:
        return value.strip()[:MAX_FEEDBACK_NOTE_CHARS] if value else None

    @model_validator(mode="after")
    def validate_snooze(self) -> "TriggerFeedback":
        if self.action == TriggerFeedbackAction.snooze and self.snoozed_until is None:
            raise ValueError("snooze feedback requires snoozed_until")
        if self.action != TriggerFeedbackAction.snooze and self.snoozed_until is not None:
            raise ValueError("snoozed_until is only valid for snooze feedback")
        return self


@dataclass(frozen=True)
class CompiledTrigger:
    condition: TriggerCondition
    regexes: Tuple[Pattern[str], ...]
    aliases: Dict[str, Tuple[str, ...]]
    ambiguous_aliases: Dict[str, Tuple[str, ...]]

    def as_condition(self) -> Dict[str, Any]:
        return self.condition.model_dump(mode="json", by_alias=True, exclude_none=True)


@dataclass(frozen=True)
class FeedbackUpdate:
    item: MemoryItem
    applied: bool
    reason: str


def _normalize_text(value: Any) -> str:
    return " ".join(str(value or "").casefold().split())


def _bounded_term(value: Any, limit: int, *, normalize: bool = True) -> str:
    text = _normalize_text(value) if normalize else str(value or "").strip()
    if not text:
        raise ValueError("trigger terms must not be blank")
    if len(text) > limit:
        raise ValueError("trigger term exceeds the length limit")
    return text


def _contains_term(text: str, term: str) -> bool:
    return bool(re.search(rf"(?<!\w){re.escape(term)}(?!\w)", text, re.IGNORECASE))


def _observation_fingerprint(observation: TriggerObservation) -> str:
    payload = observation.model_dump(mode="json", exclude_none=True)
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def compile_trigger_condition(condition: Mapping[str, Any] | TriggerCondition) -> CompiledTrigger:
    """Validate and compile one bounded MemoryItem trigger payload."""

    if isinstance(condition, TriggerCondition):
        parsed = condition
    else:
        if len(condition) > MAX_CONDITION_KEYS + (1 if "action" in condition else 0):
            raise ValueError("trigger condition exceeds the key limit")
        parsed = TriggerCondition.model_validate(dict(condition))

    regexes = tuple(re.compile(pattern, re.IGNORECASE) for pattern in parsed.regex)
    aliases: Dict[str, Tuple[str, ...]] = dict(parsed.entity_aliases)
    alias_owners: Dict[str, List[str]] = {}
    for entity, values in aliases.items():
        for alias in values:
            alias_owners.setdefault(alias, []).append(entity)
    ambiguous = {alias: tuple(sorted(owners)) for alias, owners in alias_owners.items() if len(set(owners)) > 1}
    return CompiledTrigger(condition=parsed, regexes=regexes, aliases=aliases, ambiguous_aliases=ambiguous)


def compile_memory_item_trigger(item: MemoryItem) -> CompiledTrigger:
    """Compile only active/hidden trigger rows from the canonical MemoryItem contract."""

    if item.kind != MemoryKind.trigger:
        raise ValueError("memory item is not a trigger")
    return compile_trigger_condition(item.trigger_condition)


def _time_matches(condition: TriggerTimeCondition, observed: Optional[datetime]) -> Optional[bool]:
    if observed is None:
        return None
    local = observed.astimezone(ZoneInfo(condition.timezone_name))
    if condition.weekdays and local.weekday() not in condition.weekdays:
        return False
    current = local.timetz().replace(tzinfo=None)
    if condition.start <= condition.end:
        return condition.start <= current <= condition.end
    return current >= condition.start or current <= condition.end


def _calendar_matches(
    condition: TriggerCalendarCondition,
    events: Sequence[CalendarObservation],
    *,
    authorized: bool,
) -> bool:
    # Calendar is an opportunistic local signal. Missing authorization is a
    # deterministic no-match and must never create an authorization prompt or
    # spend an ambiguous-triage budget.
    if not authorized:
        return False
    if not events:
        return False
    for event in events:
        title = _normalize_text(event.title)
        kind = _normalize_text(event.event_type)
        keyword_match = any(_contains_term(title, keyword) for keyword in condition.event_keywords)
        type_match = kind in condition.event_types if condition.event_types else False
        if keyword_match or type_match:
            return True
    return False


def evaluate_trigger(
    condition: CompiledTrigger | Mapping[str, Any] | TriggerCondition,
    observation: TriggerObservation,
    *,
    policy: TriggerRuntimePolicy = DEFAULT_TRIGGER_RUNTIME_POLICY,
) -> TriggerDecision:
    """Evaluate local evidence; missing/ambiguous context returns ``triage``."""

    compiled = condition if isinstance(condition, CompiledTrigger) else compile_trigger_condition(condition)
    text = _normalize_text(observation.text)
    entity_labels = {_normalize_text(label) for label in observation.entity_labels}
    results: Dict[str, Optional[bool]] = {}

    for entity, aliases in compiled.aliases.items():
        matched_aliases = [alias for alias in aliases if alias in entity_labels or _contains_term(text, alias)]
        if any(alias in compiled.ambiguous_aliases for alias in matched_aliases):
            results[f"entity:{entity}"] = None
        else:
            results[f"entity:{entity}"] = bool(matched_aliases)

    if compiled.condition.keywords:
        results["keywords"] = any(_contains_term(text, keyword) for keyword in compiled.condition.keywords)
    if compiled.regexes:
        results["regex"] = any(regex.search(observation.text[:MAX_CONTEXT_TEXT_CHARS]) for regex in compiled.regexes)
    if compiled.condition.apps:
        results["app"] = observation.app_name is not None and _normalize_text(observation.app_name) in set(
            compiled.condition.apps
        )
    if compiled.condition.windows:
        window = _normalize_text(observation.window_title)
        results["window"] = bool(window) and any(term in window for term in compiled.condition.windows)
    if compiled.condition.time:
        results["time"] = _time_matches(compiled.condition.time, observation.occurred_at)
    if compiled.condition.calendar:
        results["calendar"] = _calendar_matches(
            compiled.condition.calendar,
            observation.calendar_events,
            authorized=observation.calendar_authorized,
        )
    if compiled.condition.embedding:
        embedding = compiled.condition.embedding
        if not policy.embedding.enabled:
            results[f"embedding:{embedding.prototype_id}"] = False
        else:
            attestation = observation.embedding_attestation
            policy_attested = (
                embedding.model_id == policy.embedding.model_id
                and embedding.model_version == policy.embedding.model_version
                and embedding.language == policy.embedding.language
            )
            attested = (
                policy_attested
                and attestation is not None
                and attestation.model_id == embedding.model_id
                and attestation.model_version == embedding.model_version
                and attestation.language == embedding.language
                and attestation.prototype_revision == embedding.prototype_revision
            )
            score = observation.embedding_scores.get(embedding.prototype_id) if attested else None
            if score is None:
                results[f"embedding:{embedding.prototype_id}"] = False
            elif policy.embedding.triage_similarity <= score < policy.embedding.match_similarity:
                results[f"embedding:{embedding.prototype_id}"] = None
            else:
                results[f"embedding:{embedding.prototype_id}"] = score >= policy.embedding.match_similarity

    matched = tuple(sorted(key for key, value in results.items() if value is True))
    missing = tuple(sorted(key for key, value in results.items() if value is None))
    false_count = sum(value is False for value in results.values())
    if compiled.condition.match_mode == "all":
        if false_count:
            status, reason = TriggerDecisionStatus.no_match, "condition_not_satisfied"
        elif missing:
            status, reason = TriggerDecisionStatus.triage, "insufficient_or_ambiguous_context"
        else:
            status, reason = TriggerDecisionStatus.match, "all_conditions_satisfied"
    elif matched:
        status, reason = TriggerDecisionStatus.match, "one_condition_satisfied"
    elif missing:
        status, reason = TriggerDecisionStatus.triage, "insufficient_or_ambiguous_context"
    else:
        status, reason = TriggerDecisionStatus.no_match, "no_condition_satisfied"

    return TriggerDecision(
        status=status,
        reason=reason,
        matched_conditions=matched,
        missing_conditions=missing,
        matched_fraction=(len(matched) / len(results)) if results else 0.0,
        observation_fingerprint=_observation_fingerprint(observation),
    )


def evaluate_memory_item_trigger(
    item: MemoryItem,
    observation: TriggerObservation,
    *,
    policy: TriggerRuntimePolicy = DEFAULT_TRIGGER_RUNTIME_POLICY,
) -> TriggerDecision:
    """Apply row lifecycle/feedback gates before evaluating its local condition."""

    if item.kind != MemoryKind.trigger:
        return TriggerDecision(
            status=TriggerDecisionStatus.no_match,
            reason="not_a_trigger",
            observation_fingerprint=_observation_fingerprint(observation),
        )
    if item.ledger_schema_version != "knowledge_ledger.v1":
        return TriggerDecision(
            status=TriggerDecisionStatus.no_match,
            reason="trigger_not_ledger_authoritative",
            observation_fingerprint=_observation_fingerprint(observation),
        )
    if not item.intent_backed or item.subject_scope != MemorySubjectScope.primary_user:
        return TriggerDecision(
            status=TriggerDecisionStatus.no_match,
            reason="trigger_not_intent_authoritative",
            observation_fingerprint=_observation_fingerprint(observation),
        )
    if belief_model_enabled():
        at = observation.occurred_at or datetime.now(timezone.utc)
        if not record_passes_proactive_bar(item, now=at):
            return TriggerDecision(
                status=TriggerDecisionStatus.no_match,
                reason="trigger_not_current_belief",
                observation_fingerprint=_observation_fingerprint(observation),
            )
    if item.status != MemoryItemStatus.active:
        return TriggerDecision(
            status=TriggerDecisionStatus.no_match,
            reason="trigger_not_active",
            observation_fingerprint=_observation_fingerprint(observation),
        )
    if item.valid_to is not None or item.superseded_by is not None:
        return TriggerDecision(
            status=TriggerDecisionStatus.no_match,
            reason="trigger_validity_closed",
            observation_fingerprint=_observation_fingerprint(observation),
        )
    if item.source_state != SourceState.active or not any(
        evidence.source_state == SourceState.active for evidence in item.evidence
    ):
        return TriggerDecision(
            status=TriggerDecisionStatus.no_match,
            reason="trigger_source_inactive",
            observation_fingerprint=_observation_fingerprint(observation),
        )
    feedback = item.arguments.get("jit_trigger_feedback", {})
    snoozed_until = feedback.get("snoozed_until") if isinstance(feedback, Mapping) else None
    if snoozed_until:
        try:
            until = datetime.fromisoformat(str(snoozed_until))
        except ValueError:
            return TriggerDecision(
                status=TriggerDecisionStatus.no_match,
                reason="trigger_feedback_invalid",
                observation_fingerprint=_observation_fingerprint(observation),
            )
        if until.tzinfo is None or until.utcoffset() is None:
            return TriggerDecision(
                status=TriggerDecisionStatus.no_match,
                reason="trigger_feedback_invalid",
                observation_fingerprint=_observation_fingerprint(observation),
            )
        if observation.occurred_at is None:
            return TriggerDecision(
                status=TriggerDecisionStatus.triage,
                reason="trigger_snooze_requires_observation_time",
                missing_conditions=("occurred_at",),
                observation_fingerprint=_observation_fingerprint(observation),
            )
        at = observation.occurred_at
        if at < until:
            return TriggerDecision(
                status=TriggerDecisionStatus.no_match,
                reason="trigger_snoozed",
                observation_fingerprint=_observation_fingerprint(observation),
            )
    return evaluate_trigger(compile_memory_item_trigger(item), observation, policy=policy)


def apply_trigger_feedback(item: MemoryItem, feedback: TriggerFeedback) -> FeedbackUpdate:
    """Apply bounded, idempotent local feedback to a trigger MemoryItem."""

    if item.kind != MemoryKind.trigger:
        raise ValueError("feedback target is not a trigger")
    state = item.arguments.get("jit_trigger_feedback", {})
    if not isinstance(state, Mapping):
        state = {}
    applied_ids = [str(value) for value in state.get("applied_feedback_ids", []) if value]
    request_hash = hashlib.sha256(
        json.dumps(feedback.model_dump(mode="json", exclude_none=True), sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    applied_hashes = {
        str(key): str(value) for key, value in dict(state.get("applied_feedback_hashes", {})).items() if key and value
    }
    if feedback.feedback_id in applied_ids:
        if applied_hashes.get(feedback.feedback_id) not in {None, request_hash}:
            raise ValueError("feedback id was reused with a different payload")
        return FeedbackUpdate(item=item, applied=False, reason="duplicate_feedback")
    # Durable idempotency lives in the per-feedback receipt collection. The
    # trigger keeps only a rolling local state window so an account can keep
    # giving feedback for its lifetime without growing one Firestore document.
    applied_ids = (applied_ids + [feedback.feedback_id])[-MAX_FEEDBACK_IDS:]
    applied_hashes = {key: value for key, value in applied_hashes.items() if key in applied_ids}
    next_state: Dict[str, Any] = dict(state)
    next_state["applied_feedback_ids"] = applied_ids
    next_state["applied_feedback_hashes"] = {
        feedback_id: applied_hashes.get(feedback_id, request_hash if feedback_id == feedback.feedback_id else "")
        for feedback_id in applied_ids
        if applied_hashes.get(feedback_id) or feedback_id == feedback.feedback_id
    }
    next_state["last_action"] = feedback.action.value
    next_state["feedback_count"] = int(state.get("feedback_count", 0)) + 1

    weight = item.curation_weight
    status = item.status
    if feedback.action in {TriggerFeedbackAction.useful, TriggerFeedbackAction.reinforce}:
        weight = min(100, weight + 1)
    elif feedback.action in {TriggerFeedbackAction.false_positive, TriggerFeedbackAction.dismiss}:
        weight = max(-100, weight - 1)
    elif feedback.action == TriggerFeedbackAction.snooze:
        next_state["snoozed_until"] = feedback.snoozed_until.isoformat()  # type: ignore[union-attr]
    elif feedback.action == TriggerFeedbackAction.disable:
        status = MemoryItemStatus.hidden

    updated = item.model_copy(
        update={
            "arguments": {**item.arguments, "jit_trigger_feedback": next_state},
            "curation_weight": weight,
            "status": status,
            # Feedback may arrive late or be replayed from an older client. Keep
            # the MemoryItem monotonicity invariant instead of moving updated_at
            # backwards.
            "updated_at": max(item.updated_at, feedback.recorded_at),
        }
    )
    return FeedbackUpdate(item=updated, applied=True, reason="feedback_applied")


__all__ = [
    "CalendarObservation",
    "CompiledTrigger",
    "FeedbackUpdate",
    "TriggerCalendarCondition",
    "TriggerAction",
    "TriggerCondition",
    "TriggerDecision",
    "TriggerDecisionStatus",
    "TriggerEmbeddingCondition",
    "TriggerEmbeddingAttestation",
    "TriggerEmbeddingPolicy",
    "TriggerFeedback",
    "TriggerFeedbackAction",
    "TriggerObservation",
    "TriggerRuntimePolicy",
    "TriggerTimeCondition",
    "apply_trigger_feedback",
    "compile_memory_item_trigger",
    "compile_trigger_condition",
    "evaluate_memory_item_trigger",
    "evaluate_trigger",
    "MAX_CONDITION_KEYS",
    "MAX_TRIGGER_ACTION_PROMPT_CHARS",
    "TRIGGER_SCHEMA_VERSION",
    "TRIGGER_POLICY_VERSION",
    "DEFAULT_TRIGGER_RUNTIME_POLICY",
    "EMBEDDING_MATCH_SIMILARITY",
    "EMBEDDING_TRIAGE_SIMILARITY",
]
