from __future__ import annotations

from collections import defaultdict
import json
import logging
import os
import re
from typing import Iterable, Literal, Any, Callable

from langchain_core.output_parsers import PydanticOutputParser
from models.transcript_segment import TranscriptSegment
from pydantic import BaseModel, Field
from utils.llm.clients import get_llm
from utils.llm.model_config import get_model, get_provider
from utils.prompts import extract_memories_prompt
from utils.memory_ingestion.adapters.typed_extraction_prompt import (
    TYPED_PREDICATES,
    render_source_guidance,
    typed_extract_memories_prompt,
)
from utils.memory_ingestion.ids import StableIdFactory
from utils.memory_ingestion.models import (
    ActorDescriptor,
    EntityRef,
    EvidenceSpan,
    ExtractionMetadata,
    FrameObject,
    MemoryEventFrame,
    MemoryPipelineInput,
    ModelManifest,
    Modality,
    RawContextEvent,
    SensitivityClassification,
    TemporalScope,
)
from utils.memory_ingestion.pipeline import MemoryModelClient
from utils.memory_ingestion.source_routing import route_source

logger = logging.getLogger(__name__)


def _model_dump(obj: Any) -> Any:
    """Best-effort JSONable dump for trace events."""
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, dict):
        return {str(k): _model_dump(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [_model_dump(v) for v in obj]
    if hasattr(obj, "model_dump"):
        try:
            return obj.model_dump(mode="json")
        except Exception:
            try:
                return obj.model_dump()
            except Exception:
                pass
    if hasattr(obj, "content") and obj.__class__.__name__.endswith("Message"):
        return str(getattr(obj, "content", ""))
    if hasattr(obj, "__dict__"):
        return {str(k): _model_dump(v) for k, v in vars(obj).items() if not k.startswith("_")}
    return str(obj)


def _emit_optional_trace(trace_sink: Callable[[dict[str, Any]], None] | None, event: dict[str, Any]) -> None:
    if trace_sink is not None:
        trace_sink(event)


class ProductionLikeMemory(BaseModel):
    content: str
    quote_anchor: str | None = None
    category: str = "system"
    tags: list[str] = Field(default_factory=list)
    visibility: str = "private"
    headline: str | None = None
    predicate: str | None = None
    arguments: dict[str, object] = Field(default_factory=dict)
    subject_entity_id: str | None = None
    subject_attribution: str | None = None
    object_entity_ids: list[str] = Field(default_factory=list)
    qualifiers: dict[str, object] = Field(default_factory=dict)
    capture_confidence: float | None = None
    veracity: float | None = None
    uncertainty_reasons: list[str] = Field(default_factory=list)
    durability: str | None = None


class ProductionLikeMemories(BaseModel):
    facts: list[ProductionLikeMemory] = Field(default_factory=list, max_items=2)


class HighRecallProductionLikeMemories(BaseModel):
    facts: list[ProductionLikeMemory] = Field(
        default_factory=list,
        description="List of all memory-worthy facts from the conversation.",
    )


# Build a Literal type from TYPED_PREDICATES so Pydantic validates at parse time.
_PredicateLiteral = Literal[tuple(TYPED_PREDICATES)]  # type: ignore[misc]


class TypedProductionLikeMemory(ProductionLikeMemory):
    """Typed proposition variant; field descriptions steer the structured output."""

    subject_entity_id: str | None = Field(
        default=None,
        description=(
            "Stable subject id. Use ent_user for facts about the primary user; "
            "ent_speaker_1/ent_speaker_2 for explicitly speaker-scoped facts; "
            "or a project/person id such as ent_omi when the fact is about that entity. "
            "Leave null only when the subject is truly ambiguous."
        ),
    )
    predicate: _PredicateLiteral | None = Field(
        default=None,
        description=(
            "EXACTLY ONE predicate from the fixed vocabulary. "
            "MUST be one of: " + ", ".join(TYPED_PREDICATES) + ". "
            "This field is REQUIRED — do not leave it null or empty. "
            "Pick the most specific predicate that matches the fact."
        ),
    )
    arguments: dict[str, object] = Field(
        default_factory=dict,
        description="Named argument slots for the predicate, short literal strings.",
    )
    subject_attribution: str | None = Field(
        default=None,
        description="user | third_party | assistant_suggested",
    )
    uncertainty_reasons: list[str] = Field(
        default_factory=list,
        description="Uncertainty vocabulary from the prompt; empty when confident.",
    )


class TypedProductionLikeMemories(BaseModel):
    facts: list[TypedProductionLikeMemory] = Field(
        default_factory=list,
        description="All memory-worthy facts from the conversation, as typed propositions.",
        max_items=6,
    )


class VoiceRecallTypedProductionLikeMemories(BaseModel):
    facts: list[TypedProductionLikeMemory] = Field(
        default_factory=list,
        description=(
            "All memory-worthy voice facts from the selected claim-dense spans. "
            "Preserve user, speaker, project, organization, and tool subjects explicitly."
        ),
        max_items=10,
    )


_VOICE_RECALL_EXTRA_GUIDANCE = """
V8 voice_recall_v1 route: selected spans were chosen for claim density. Extract durable facts from task/project/action, money/deadline/progress, team/equity, tooling/security, and biographical spans.
Subject rules for this route:
  - Preserve the actual subject instead of forcing every fact onto the primary user.
  - If the selected input metadata says primary_speaker_user_alias maps_to ent_user, treat that speaker label as the primary user for subject_entity_id purposes.
  - Use subject_entity_id=ent_user only when the quoted span is about the primary user, an explicit user command/commitment, or the declared primary_speaker_user_alias.
  - Use subject_entity_id=ent_speaker_1, ent_speaker_2, etc. for facts explicitly about that speaker when no real name is known.
  - This route intentionally keeps speaker-scoped project/task facts even when the speaker's relationship to the user is unknown; do not output [] solely because a fact is about another speaker's concrete work, PR, tool, project, or commitment.
  - If a span is entirely about another speaker's concrete project/task, emit it as subject_attribution=third_party with the speaker subject instead of suppressing it.
  - Use project/entity subjects such as ent_omi when the fact is about a project/company/team rather than a person.
  - The content sentence may start with that subject/project name instead of {user_name}; do not rewrite non-user/project facts as {user_name} facts.
  - If the subject is ambiguous, include subject_ambiguous or speaker_uncertain and lower confidence instead of misattributing.
Useful voice facts include: concrete commitments, PR/merge/project work, tools used for work, bank/security/tool access, startup team/equity/state, travel/fundraising/goals, and family/health context when source-grounded.
"""


class ProductionLikeMemoryModelClient(MemoryModelClient):
    """Runs Omi's current production memory extractor, then maps results into frames.

    This intentionally keeps durable application out of the core pipeline. It reuses the
    current production prompt/model with caller-provided user state instead of fetching
    Firestore state or writing usage telemetry.
    """

    def __init__(
        self,
        *,
        max_events_per_call: int = 250,
        high_recall: bool = False,
        typed: bool = False,
        trace_sink: Callable[[dict[str, Any]], None] | None = None,
        source_route_config: dict[str, str] | None = None,
    ):
        self.max_events_per_call = max_events_per_call
        self.high_recall = high_recall
        self.typed = typed
        self.source_route_config = dict(source_route_config or {})
        self.trace_events: list[dict[str, Any]] = []
        self.trace_sink = trace_sink or self.trace_events.append

    def clear_trace_events(self) -> None:
        self.trace_events.clear()

    def _emit_trace(self, event: dict[str, Any]) -> None:
        if self.trace_sink is not None:
            self.trace_sink(event)

    async def extract_frames(
        self,
        *,
        pipeline_input: MemoryPipelineInput,
        events: list[RawContextEvent],
        input_fingerprint: str,
        id_factory: StableIdFactory,
    ) -> list[MemoryEventFrame]:
        frames: list[MemoryEventFrame] = []
        user_name = _user_name(pipeline_input.actor)
        memories_str = _memories_str(user_name, pipeline_input)
        for conversation_id, grouped_events in _events_by_conversation(events).items():
            for chunk_index, event_chunk in enumerate(_chunks(grouped_events, self.max_events_per_call)):
                if _is_passive_media_monologue(event_chunk):
                    self._emit_trace(
                        {
                            "stage": "model_client_chunk_skip",
                            "reason": "passive_media_monologue",
                            "conversation_id": conversation_id,
                            "chunk_index": chunk_index,
                            "source_event_ids": [event.event_id for event in event_chunk],
                        }
                    )
                    continue
                route_family = self.source_route_config.get(pipeline_input.source.source_type, "current")
                route = route_source(pipeline_input.source, route_family=route_family)
                self._emit_trace(
                    {
                        "stage": "source_route",
                        "conversation_id": conversation_id,
                        "chunk_index": chunk_index,
                        "source_event_ids": [event.event_id for event in event_chunk],
                        **route.model_dump(),
                    }
                )
                segments = [_to_transcript_segment(event, index) for index, event in enumerate(event_chunk)]
                is_voice_recall_route = (
                    pipeline_input.source.source_type == "voice_transcript" and route_family == "voice_recall_v1"
                )
                retry_attempts = 1 if is_voice_recall_route else 0
                memories = _extract_memories_with_production_prompt(
                    segments=segments,
                    user_name=user_name,
                    memories_str=memories_str,
                    language=pipeline_input.source.language,
                    source_type=route.effective_source_type,  # V8-3 passthrough router scaffold
                    high_recall=self.high_recall,
                    typed=self.typed,
                    trace_sink=self._emit_trace,
                    trace_context={
                        "conversation_id": conversation_id,
                        "chunk_index": chunk_index,
                        "source_event_ids": [event.event_id for event in event_chunk],
                        "route_family": route_family,
                    },
                    retry_attempts=retry_attempts,
                    route_family=route_family,
                )
                for memory_index, memory in enumerate(memories):
                    if not _has_sufficient_evidence(memory.content, event_chunk, quote_anchor=memory.quote_anchor):
                        self._emit_trace(
                            {
                                "stage": "candidate_rejected",
                                "reason": "insufficient_evidence",
                                "conversation_id": conversation_id,
                                "chunk_index": chunk_index,
                                "memory_index": memory_index,
                                "memory": _model_dump(memory),
                            }
                        )
                        continue
                    source_events = [event.event_id for event in event_chunk]
                    calibration = _calibration(memory, event_chunk)
                    supporting_events = _supporting_events(
                        memory.content,
                        event_chunk,
                        quote_anchor=memory.quote_anchor,
                    )
                    evidence = [
                        EvidenceSpan(
                            evidence_id=id_factory.new_id(
                                "evidence", conversation_id, chunk_index, memory_index, event.event_id
                            ),
                            source_event_id=event.event_id,
                            source_ref=event.source_ref,
                            quote=_find_supporting_quote_for_event(
                                memory.content,
                                event,
                                quote_anchor=memory.quote_anchor,
                            ),
                            start_at=event.start_at,
                            end_at=event.end_at,
                            speaker=event.speaker,
                        )
                        for event in (supporting_events or event_chunk[:1])
                    ]
                    frame = MemoryEventFrame(
                        frame_type=_frame_type(memory.category),
                        subject=_frame_subject(memory, pipeline_input.actor, allow_non_user=is_voice_recall_route),
                        predicate=_resolve_predicate(memory),
                        object=FrameObject(
                            object_type="literal",
                            value=memory.content,
                            confidence=calibration["confidence"],
                        ),
                        arguments=_frame_arguments(memory.arguments, calibration["confidence"]),
                        canonical_text=memory.content,
                        original_text=None,
                        temporal=TemporalScope(kind="unknown"),
                        modality=_frame_modality(memory),
                        polarity=_frame_polarity(memory),
                        durability="long_term",
                        sensitivity=calibration["sensitivity"],
                        scope="conversation",
                        scope_ref=event_chunk[0].source_ref if event_chunk else None,
                        importance="high",
                        evidence=evidence,
                        source_event_ids=source_events,
                        confidence=calibration["confidence"],
                        uncertainty_reasons=sorted(
                            set(calibration["uncertainty_reasons"]) | set(_model_uncertainty_reasons(memory))
                        ),
                        extraction=ExtractionMetadata(
                            extractor="omi_production_memory_extractor",
                            model="memories",
                            prompt_version=self._prompt_version(),
                            source_block_id=f"{conversation_id}:{chunk_index}",
                            notes=self._extraction_notes(),
                        ),
                    )
                    self._emit_trace(
                        {
                            "stage": "frame_created",
                            "conversation_id": conversation_id,
                            "chunk_index": chunk_index,
                            "memory_index": memory_index,
                            "frame": _model_dump(frame),
                        }
                    )
                    frames.append(frame)
        for frame in frames:
            frame.frame_id = id_factory.new_id(
                "frame",
                input_fingerprint,
                frame.canonical_text.casefold(),
                [evidence.evidence_id for evidence in frame.evidence],
                pipeline_input.config.ontology_version,
            )
        return frames

    def manifest(self, pipeline_input: MemoryPipelineInput) -> ModelManifest:
        if self.typed:
            version = "production_like_typed_high_recall.v1" if self.high_recall else "production_like_typed.v1"
        else:
            version = "production_like_high_recall.v1" if self.high_recall else "production_like.v1"
        return ModelManifest(
            extractor_model=pipeline_input.config.models.extractor_model or "memories",
            provider_versions={"memory_ingestion": version},
            prompt_versions={"frame_extraction": self._prompt_version()},
        )

    def _prompt_version(self) -> str:
        if self.typed:
            return "utils.memory_ingestion.adapters.typed_extraction_prompt"
        return "utils.prompts.extract_memories_prompt"

    def _extraction_notes(self) -> list[str]:
        notes = []
        if self.high_recall:
            notes.append("high_recall")
        if self.typed:
            notes.append("typed")
        return notes


def _user_name(actor: ActorDescriptor | None) -> str:
    if actor and actor.display_name:
        return actor.display_name
    return "User"


def _memories_str(user_name: str, pipeline_input: MemoryPipelineInput) -> str:
    memories = pipeline_input.user_state.active_memories[:1000]
    lines = [f"- {memory.text}" for memory in memories if memory.text]
    if not lines:
        return f"you do not yet know durable facts about {user_name}.\n"
    return f"you already know the following facts about {user_name}:\n" + "\n".join(lines) + "\n"


def _extract_memories_with_production_prompt(
    *,
    segments: list[TranscriptSegment],
    user_name: str,
    memories_str: str,
    language: str | None,
    source_type: str,  # from pipeline_input.source.source_type
    high_recall: bool,
    typed: bool = False,
    trace_sink: Callable[[dict[str, Any]], None] | None = None,
    trace_context: dict[str, Any] | None = None,
    retry_attempts: int = 0,
    route_family: str = "current",
) -> list[ProductionLikeMemory]:
    trace_context = trace_context or {}
    content = TranscriptSegment.segments_as_string(segments, user_name=user_name, people=[])
    if not content or len(content) < 25:
        _emit_optional_trace(
            trace_sink,
            {
                "stage": "model_call_skipped",
                "reason": "selected_content_too_short",
                "source_type": source_type,
                "selected_text_chars": len(content or ""),
                **trace_context,
            },
        )
        return []
    is_voice_recall_route = source_type == "voice_transcript" and route_family == "voice_recall_v1"
    if typed:
        parser = PydanticOutputParser(
            pydantic_object=(
                VoiceRecallTypedProductionLikeMemories if is_voice_recall_route else TypedProductionLikeMemories
            )
        )
        prompt = typed_extract_memories_prompt
    else:
        parser = PydanticOutputParser(
            pydantic_object=HighRecallProductionLikeMemories if high_recall else ProductionLikeMemories
        )
        prompt = extract_memories_prompt
    prompt_inputs = {
        "user_name": user_name,
        "conversation": content,
        "memories_str": memories_str,
        "language_instruction": _language_instruction(language),
        "format_instructions": parser.get_format_instructions(),
        "source_guidance": (
            render_source_guidance(source_type)
            + ("\n\n" + _VOICE_RECALL_EXTRA_GUIDANCE if is_voice_recall_route else "")
        ),  # v4: source-aware
    }
    prompt_value = prompt.invoke(prompt_inputs)
    raw_response = None
    parsed_response = None
    max_attempts = max(1, retry_attempts + 1)
    attempt = 0
    for attempt in range(1, max_attempts + 1):
        raw_response = None
        try:
            raw_response = _memory_llm().invoke(prompt_value)
            parsed_response = parser.invoke(raw_response)
            break
        except Exception as exc:
            final_attempt = attempt >= max_attempts
            _emit_optional_trace(
                trace_sink,
                {
                    "stage": "model_call",
                    "status": "error",
                    "source_type": source_type,
                    "typed": typed,
                    "high_recall": high_recall,
                    "selected_text": content,
                    "raw_model_response": _model_dump(raw_response),
                    "parser_error": str(exc),
                    "attempt": attempt,
                    "max_attempts": max_attempts,
                    "will_retry": not final_attempt,
                    **trace_context,
                },
            )
            if not final_attempt:
                _emit_optional_trace(
                    trace_sink,
                    {
                        "stage": "model_call_retry",
                        "source_type": source_type,
                        "attempt": attempt + 1,
                        "max_attempts": max_attempts,
                        "previous_error": str(exc),
                        **trace_context,
                    },
                )
                continue
            raise
    assert parsed_response is not None
    _emit_optional_trace(
        trace_sink,
        {
            "stage": "model_call",
            "status": "ok",
            "source_type": source_type,
            "typed": typed,
            "high_recall": high_recall,
            "selected_text": content,
            "raw_model_response": _model_dump(raw_response),
            "parsed_facts_before_filter": _model_dump(parsed_response.facts),
            "parser_error": None,
            "attempt": attempt,
            "max_attempts": max_attempts,
            **trace_context,
        },
    )
    return parsed_response.facts


_KNOWN_UNCERTAINTY_REASONS = {
    "speaker_uncertain",
    "inferred_not_stated",
    "temporal_scope_unclear",
    "low_quality_transcript",
    "subject_ambiguous",
    "conflicts_with_existing_memory",
    "duplicate_near_match",
}

_UNCERTAINTY_REASON_ALIASES = {
    "ambiguous_subject": "subject_ambiguous",
    "possible_duplicate": "duplicate_near_match",
}


def _validated_predicate(memory: ProductionLikeMemory) -> str | None:
    """Validate and normalize the predicate from extracted memory.

    Does fuzzy matching against TYPED_PREDICATES so that minor LLM output
    variations (extra whitespace, slight rewording, predicate: value format)
    still resolve to the correct typed predicate instead of falling through
    to the generic 'related_to' fallback.
    """
    raw = memory.predicate
    if not raw or not isinstance(raw, str):
        return None
    raw_stripped = raw.strip()

    # 1. Exact match (fast path)
    if raw_stripped in TYPED_PREDICATES:
        return raw_stripped

    # 2. Case-insensitive match
    raw_lower = raw_stripped.lower()
    for p in TYPED_PREDICATES:
        if p.lower() == raw_lower:
            logger.debug("predicate normalized case: %r → %r", raw_stripped, p)
            return p

    # 3. Substring match — LLM may emit "prefers X" or "decided_to_use tool"
    for p in TYPED_PREDICATES:
        if raw_lower.startswith(p + " ") or raw_lower.startswith(p + "_") or raw_lower == p:
            logger.debug("predicate prefix match: %r → %r", raw_stripped, p)
            return p
        if raw_lower.endswith(" " + p) or raw_lower.endswith("_" + p):
            logger.debug("predicate suffix match: %r → %r", raw_stripped, p)
            return p

    # 4. [i10 REMOVED] Containment check was too broad — substring matches on long LLM outputs
    #    produced false predicate resolutions (e.g., "is_currently_truefact" → is_currently_true).
    #    Steps 1 (exact), 2 (casefold), 3 (prefix/suffix), and 5 (alias) cover realistic LLM output space.

    # 5. Known alias / common LLM mistake mapping
    alias_map = {
        "likes": "prefers",
        "loves": "prefers",
        "hates": "dislikes",
        "planning": "committed_to_do",
        "plans": "committed_to_do",
        "using": "uses_tool",
        "uses": "uses_tool",
        "working on": "works_on",
        "work on": "works_on",
        "decided": "decided_to_use",
        "chose": "decided_to_use",
        "chosen": "decided_to_use",
        "considering": "considering_using",
        "thinking about": "considering_using",
        "knows": "knows_person",
        "met": "knows_person",
        "birthday": "has_birthday",
        "address": "has_address",
        "travel": "plans_travel_to",
        "trip": "plans_travel_to",
        "belongs to": "belongs_to_project",
        "no longer": "is_no_longer_true",
        "not true": "is_no_longer_true",
        "stopped": "is_no_longer_true",
        "currently": "is_currently_true",
        "fact": "is_currently_true",
        "related": "is_currently_true",
        "related_to": "is_currently_true",
    }
    normalized_alias = raw_lower.replace(" ", "_").replace("-", "_")
    if normalized_alias in alias_map:
        resolved = alias_map[normalized_alias]
        logger.debug("predicate alias match: %r → %r", raw_stripped, resolved)
        return resolved
    for alias, canonical in alias_map.items():
        if alias in raw_lower:
            logger.debug("predicate alias containment: %r → %r via %r", raw_stripped, canonical, alias)
            return canonical

    logger.warning(
        "predicate %r could not be matched to any TYPED_PREDICATE; "
        "will attempt content-based inference before fallback to related_to",
        raw_stripped,
    )
    return None


_CONTENT_PREDICATE_RULES: list[tuple[str, list[str]]] = [
    ("prefers", ["prefers", "likes", "favor", "rather", "over"]),
    ("dislikes", ["dislike", "hate", "can't stand", "annoy"]),
    ("works_on", ["works on", "working on", "building", "developing", "leading", "managing project"]),
    ("decided_to_use", ["decided to use", "decided on", "chose to use", "switched to", "adopted", "settled on"]),
    (
        "considering_using",
        ["considering using", "thinking about using", "looking into", "evaluating", "exploring", "might use"],
    ),
    ("committed_to_do", ["committed to", "promised to", "plan to", "going to", "will definitely", "pledged"]),
    (
        "knows_person",
        [
            "knows",
            "met",
            "friend",
            "colleague",
            "coworker",
            "partner",
            "boss",
            "manager",
            "report",
            "sibling",
            "parent",
            "spouse",
            "relative",
        ],
    ),
    ("has_birthday", ["birthday", "born on", "turns age", "age is"]),
    ("has_address", ["address", "lives at", "home is", "located at", "residence"]),
    ("uses_tool", ["uses ", "relies on", "leverages", "runs on", "built with"]),
    ("belongs_to_project", ["belongs to", "part of team", "on the team", "member of project"]),
    ("plans_travel_to", ["travel to", "trip to", "visit", "moving to", "relocating", "fly to", "drive to"]),
    ("is_no_longer_true", ["no longer", "not anymore", "stopped", "quit", "left", "cancelled", "no more"]),
]


def _infer_predicate_from_content(content: str) -> str | None:
    """Infer the best predicate from memory content text as a secondary fallback.

    When the LLM fails to provide a valid predicate (or we're running in
    non-typed mode where no predicate field exists), scan the memory content
    for signal words that indicate which typed predicate should apply.
    Returns None only when no inference is possible (truly generic content).
    """
    if not content:
        return None
    text = content.strip().lower()
    best_predicate = None
    best_score = 0

    for predicate, signals in _CONTENT_PREDICATE_RULES:
        score = sum(1 for s in signals if s in text)
        if score > best_score:
            best_score = score
            best_predicate = predicate

    if best_score >= 1:
        logger.debug("content-based predicate inference: %r → %r (score=%d)", content[:60], best_predicate, best_score)
        return best_predicate

    return None


def _resolve_predicate(memory: ProductionLikeMemory) -> str:
    """Resolve the final predicate for a memory fact with full fallback chain.

    Priority order:
      1. Validated predicate from LLM output (fuzzy-matched)
      2. Content-based inference from memory text
      3. Category-based fallback ('learned' for interesting, 'is_currently_true' otherwise)

    This replaces the old pattern of ``_validated_predicate(memory) or _predicate(memory.category)``
    so that 'related_to' is never emitted — we always try to find a specific predicate first.
    """
    # 1. Try validated predicate from LLM
    validated = _validated_predicate(memory)
    if validated:
        return validated

    # 2. Try content-based inference
    inferred = _infer_predicate_from_content(memory.content)
    if inferred:
        logger.info(
            "predicate inferred from content for %r: %s (LLM predicate was %r)",
            memory.content[:60],
            inferred,
            memory.predicate,
        )
        return inferred

    # 3. Final category-based fallback — but use specific predicates, not 'related_to'
    if _category_value(memory.category) == "interesting":
        return "learned"
    # Use is_currently_true as the last resort instead of related_to,
    # since it's semantically clearer and maps correctly in the crosswalk.
    logger.info(
        "no specific predicate found for %r; using is_currently_true fallback (category=%s)",
        memory.content[:60],
        memory.category,
    )
    return "is_currently_true"


def _model_uncertainty_reasons(memory: ProductionLikeMemory) -> list[str]:
    reasons = []
    for reason in memory.uncertainty_reasons or []:
        normalized = _UNCERTAINTY_REASON_ALIASES.get(reason, reason)
        if normalized in _KNOWN_UNCERTAINTY_REASONS:
            reasons.append(normalized)
    return reasons


def _frame_arguments(arguments: dict[str, object], confidence: str) -> dict[str, FrameObject]:
    return {
        str(key): FrameObject(object_type="literal", value=_frame_argument_value(value), confidence=confidence)
        for key, value in (arguments or {}).items()
        if value is not None and value != ""
    }


def _frame_argument_value(value: object) -> object:
    if isinstance(value, list):
        return ", ".join(str(item) for item in value)
    if isinstance(value, tuple):
        return ", ".join(str(item) for item in value)
    if isinstance(value, (str, int, float, bool, dict)) or value is None:
        return value
    return json.dumps(value, sort_keys=True, default=str)


def _frame_modality(memory: ProductionLikeMemory) -> Modality:
    """Preserve typed extractor epistemics instead of flattening every fact to asserted."""
    # Use the fully resolved predicate so modality is correct even when
    # the predicate was inferred from content rather than provided by LLM.
    predicate = _resolve_predicate(memory)
    if predicate == "considering_using":
        return Modality(kind="considered", text="typed predicate indicates consideration")
    if predicate in {"plans_travel_to", "committed_to_do"}:
        return Modality(kind="planned", text="typed predicate indicates a plan or commitment")
    if predicate == "is_no_longer_true":
        return Modality(kind="past", text="typed predicate indicates the fact no longer holds")
    if "temporal_scope_unclear" in _model_uncertainty_reasons(memory):
        return Modality(kind="uncertain", text="model marked temporal scope unclear")
    return Modality(kind="asserted")


def _frame_polarity(memory: ProductionLikeMemory) -> str:
    """Expose explicit stopped/negated state changes for conflict routing and scoring."""
    return "negative" if _resolve_predicate(memory) == "is_no_longer_true" else "neutral"


_memory_llm_logged = False  # module-level flag: has the LLM endpoint been logged?


def _memory_llm(temperature: float = 0.0):
    global _memory_llm_logged
    # Log resolved endpoint once for debuggability — catches credential mismatches early
    if not _memory_llm_logged:
        print(f"[pipeline-llm] feature=memories route={get_provider('memories')}/{get_model('memories')}")
        _memory_llm_logged = True
    if temperature is not None:
        return get_llm("memories").bind(temperature=temperature)
    return get_llm("memories")


def _language_instruction(language: str | None) -> str:
    if language and language != "en":
        return f"Write all extracted memories/learnings in {language}. Do not write them in English."
    return "Write all extracted memories/learnings in English."


def _calibration(memory: ProductionLikeMemory, events: list[RawContextEvent]) -> dict:
    text = memory.content.casefold()
    confidence = "medium"
    uncertainty_reasons: list[str] = []
    categories = ["ordinary_personal_fact"] if _category_value(memory.category) == "system" else ["ordinary_work_fact"]
    sensitivity_level = "none"
    review_required = False

    if _has_ocr_uncertainty(events):
        uncertainty_reasons.append("low_quality_transcript")

    unknown_speaker = _has_unknown_speaker(events)
    if unknown_speaker:
        uncertainty_reasons.append("speaker_uncertain")

    best_overlap = max((_evidence_overlap_count(memory.content, event.text or "") for event in events), default=0)
    direct_self_report = _has_direct_self_report_evidence(
        memory.content,
        events,
        quote_anchor=memory.quote_anchor,
    )
    # Relaxed: direct self-reports only need 2+ overlap words (was 3) since
    # first-person language already provides strong attribution signal.
    if (
        best_overlap < (2 if direct_self_report else 3)
        and len(_meaningful_words(memory.content)) >= 3
        and not direct_self_report
    ):
        uncertainty_reasons.append("weak_evidence")
        review_required = True

    if _has_speculative_signal(text):
        uncertainty_reasons.append("inferred_not_stated")
        review_required = True

    if _has_low_value_memory_text(text) or _has_external_information_signal(text, events):
        uncertainty_reasons.append("unsupported_by_existing_state")
        review_required = True

    # A8 removed (redundant with A4 quote_anchor validation at extraction gate):
    # A4 already rejects memories with unsupported anchors before they reach
    # calibration. Re-checking here only lowered confidence of what passed.

    # Relaxed: plan predicates (plans_travel_to, committed_to_do, considering_using)
    # are inherently temporally scoped — don't penalize them for future-plan signals.
    resolved_predicate = _resolve_predicate(memory) if memory else None
    is_plan_predicate = resolved_predicate in ("plans_travel_to", "committed_to_do", "considering_using")
    if _has_future_plan_signal(text) and not is_plan_predicate:
        uncertainty_reasons.append("temporal_scope_unclear")
        review_required = True

    third_party = memory.subject_attribution == "third_party" or _has_third_party_signal(text, events)
    assistant_suggested = memory.subject_attribution == "assistant_suggested"
    if (
        _is_user_attributed(memory)
        and not third_party
        and not assistant_suggested
        and not _has_ocr_uncertainty(events)
        and not _has_self_report_source(memory.content, events, quote_anchor=memory.quote_anchor)
    ):
        uncertainty_reasons.append("inferred_not_stated")
        review_required = True
    if assistant_suggested:
        uncertainty_reasons.append("inferred_not_stated")
        review_required = True
    if third_party:
        categories = ["third_party_private_fact"]
        sensitivity_level = "medium"
        review_required = True
        if _has_non_actor_speaker(events):
            uncertainty_reasons.append("speaker_uncertain")

    if _has_health_signal(text):
        categories = ["health", "third_party_private_fact"] if third_party else ["health"]
        sensitivity_level = "high"
        review_required = True

    # Upgrade to high confidence when a direct actor-authored quote anchors
    # the memory and no review-triggering uncertainty/sensitivity exists.
    # Relaxed from 6-condition gate (post-hallucination-campaign): removed
    # has_entities and content_specific>40 as hard requirements since they
    # blocked valid short memories (e.g., "I use Raycast").
    speaker_confirmed = not unknown_speaker and "speaker_uncertain" not in uncertainty_reasons
    no_speculation = not _has_speculative_signal(text)
    actor_supported = _has_actor_supported_quote(memory.content, events, min_overlap=3)
    content_words = len(_meaningful_words(memory.content))
    if (
        speaker_confirmed
        and no_speculation
        and actor_supported
        and not review_required
        and content_words >= 3  # i10 Fix #3: restore minimal specificity floor for high-conf
    ):
        confidence = "high"
    elif (
        "weak_evidence" in uncertainty_reasons
        or "unsupported_by_existing_state" in uncertainty_reasons
        or assistant_suggested
    ):
        confidence = "low"

    return {
        "confidence": confidence,
        "uncertainty_reasons": sorted(set(uncertainty_reasons)),
        "sensitivity": SensitivityClassification(
            level=sensitivity_level,
            categories=categories,
            auto_store_allowed=not review_required,
            review_required=review_required,
        ),
    }


def _has_ocr_uncertainty(events: list[RawContextEvent]) -> bool:
    return any(event.event_type == "screen_ocr" or "ocr_noisy" in event.quality.quality_flags for event in events)


def _has_unknown_speaker(events: list[RawContextEvent]) -> bool:
    return any(event.speaker and event.speaker.is_actor_user is None for event in events)


def _has_actor_supported_quote(memory_content: str, events: list[RawContextEvent], *, min_overlap: int) -> bool:
    """True when an actor-authored event directly anchors the memory wording."""
    return any(
        event.speaker
        and event.speaker.is_actor_user is True
        and _evidence_overlap_count(memory_content, event.text or "") >= min_overlap
        for event in events
    )


def _has_self_report_source(
    memory_content: str,
    events: list[RawContextEvent],
    *,
    quote_anchor: str | None = None,
) -> bool:
    """True when a user-attributed memory is backed by user/self-report wording.

    Speaker labels are often unavailable in fixture exports, so accept either an
    actor-authored event or first-person language in the literal quote/event that
    also overlaps the memory. This blocks passive media narration and team/AI
    suggestions from becoming durable facts about the recording user.
    """
    if any(
        event.speaker
        and event.speaker.is_actor_user is True
        and _evidence_overlap_count(memory_content, event.text or "") >= 1
        for event in events
    ):
        return True
    return _has_direct_self_report_evidence(memory_content, events, quote_anchor=quote_anchor)


def _has_direct_self_report_evidence(
    memory_content: str,
    events: list[RawContextEvent],
    *,
    quote_anchor: str | None = None,
) -> bool:
    """True for terse but explicit first-person support for a user memory.

    Three shared content words is too strict for valid short memories such as
    "I use Raycast" or "we chose Linear", where the quote is first-person and
    the extracted object is intentionally concise.  Keep provenance strict, but
    allow a lower overlap bar for direct self-reports.
    """
    candidates: list[tuple[str, bool]] = []
    if quote_anchor:
        candidates.append((quote_anchor, _quote_anchor_is_supported(quote_anchor, events)))
    candidates.extend((event.text or "", True) for event in events)
    return any(
        supported and _has_first_person_language(text) and _evidence_overlap_count(memory_content, text) >= 1
        for text, supported in candidates
    )


_FIRST_PERSON_RE = re.compile(
    r"\b(i|i['’]m|i['’]ve|i['’]d|i['’]ll|me|my|mine|we|we['’]re|we['’]ve|we['’]d|we['’]ll|our|ours)\b"
)


def _has_first_person_language(text: str) -> bool:
    return bool(_FIRST_PERSON_RE.search(text.casefold()))


def _is_user_attributed(memory: ProductionLikeMemory) -> bool:
    return getattr(memory, "subject_attribution", None) in (None, "", "user")


def _has_non_actor_speaker(events: list[RawContextEvent]) -> bool:
    return any(event.speaker and event.speaker.is_actor_user is False for event in events)


def _is_passive_media_monologue(events: list[RawContextEvent]) -> bool:
    if not events:
        return False
    if any(event.speaker and event.speaker.is_actor_user is True for event in events):
        return False
    text = " ".join(event.text or "" for event in events).casefold()
    if not text:
        return False
    media_markers = (
        " this video ",
        " in this video ",
        " our sources in the description ",
        " sources in the description ",
        " link in the description ",
        " links in the description ",
        " like and subscribe ",
        " welcome back to ",
        " today's episode ",
        " this episode ",
    )
    padded = f" {text} "
    return any(marker in padded for marker in media_markers)


def _has_third_party_signal(text: str, events: list[RawContextEvent]) -> bool:
    terms = (
        "father",
        "mother",
        "friend",
        "girlfriend",
        "boyfriend",
        "acquaintance",
        "peer",
        "coworker",
        "john",
        "rudi",
        "saru",
        "kristina",
    )
    return _has_non_actor_speaker(events) or any(term in text for term in terms)


def _has_speculative_signal(text: str) -> bool:
    terms = (
        " might ",
        " maybe ",
        " may ",
        " considering ",
        " consider ",
        " thinking of ",
        " thinking about ",
        " possibly ",
        " probably ",
        " could ",
    )
    padded = f" {text} "
    return any(term in padded for term in terms)


def _has_low_value_memory_text(text: str) -> bool:
    """Detect summary-shaped outputs that describe conversation activity, not durable memory.

    These phrases commonly arise when the model converts weak evidence into
    meta-commentary ("discussed X", "expressed interest in Y") instead of a
    concrete preference/decision/fact.  They are routed away from auto-create.
    """
    padded = f" {text} "
    # Relaxed post-hallucination-campaign: removed preference-indicating phrases
    # ("expressed", "showed interest", "has/is interested in") that caught valid
    # preference extractions like "David expressed interest in using Rust."
    banned_phrases = (
        " discussed ",
        " talked about ",
        " mentioned ",
        " thinks ",
        " believes ",
        " feels ",
        " had a conversation ",
    )
    return any(phrase in padded for phrase in banned_phrases)


def _has_external_information_signal(text: str, events: list[RawContextEvent]) -> bool:
    """Detect product/news/documentation facts not explicitly tied to the user.

    Prompt guardrails ban these, but a model can still convert passive media,
    docs, or meeting chatter into durable memories.  Keep direct first-person
    user reports reviewable/creatable; demote product/news-shaped statements
    that lack self-report provenance.
    """
    if _has_direct_self_report_evidence(text, events):
        return False
    padded = f" {text} "
    external_terms = (
        " announced ",
        " released ",
        " launched ",
        " acquired ",
        " acquisition ",
        " feature ",
        " capability ",
        " supports ",
        " enables ",
        " documentation ",
        " api ",
        " company ",
        " customer ",
        " survey ",
        " metric ",
        " average deal ",
    )
    return any(term in padded for term in external_terms)


def _has_future_plan_signal(text: str) -> bool:
    padded = f" {text} "
    plan_terms = (
        " plan to ",
        " plans to ",
        " planning to ",
        " scheduled to ",
        " going to ",
    )
    time_terms = (
        " today",
        " tomorrow",
        " tonight",
        " this week",
        " next week",
        " at ",
        " by ",
    )
    return any(term in padded for term in plan_terms) and any(term in padded for term in time_terms)


def _has_health_signal(text: str) -> bool:
    terms = (
        "cancer",
        "antibiotic",
        "illness",
        "sick",
        "lab test",
        "medical",
        "health",
        "treatment",
    )
    return any(term in text for term in terms)


def _has_named_entities(text: str) -> bool:
    """Check if text contains likely named entities (proper nouns, places, organizations).

    Uses simple heuristics: capitalized words that aren't sentence-starters,
    plus known patterns like multi-word capitalized sequences.
    """
    import re

    # Look for capitalized words not at start of sentence
    # Patterns like "John", "Paris", "Google", "Monday", etc.
    mid_sentence_capitalized = re.findall(r'(?:^|\.\s+|\!\s+|\?\s+)\s*([A-Z][a-z]+)\b', text)  # sentence starts
    all_capitalized = re.findall(r'\b([A-Z][a-z]{2,})\b', text)
    # Named entities are capitalized words beyond sentence starters
    non_start_capitalized = [w for w in all_capitalized if w not in set(mid_sentence_capitalized)]
    if len(non_start_capitalized) >= 1:
        return True
    # Also check for common entity patterns (dates, places with prepositions)
    entity_patterns = re.findall(
        r'\b(?:in|at|on|from|to)\s+[A-Z][a-z]+|(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)'
        r'|(?:January|February|March|April|May|June|July|August|September|October|November|December)'
        r'|\d{1,2}[/-]\d{1,2}[/-]\d{2,4}',
        text,
    )
    return len(entity_patterns) >= 1


_EVIDENCE_STOPWORDS = {
    "a",
    "about",
    "an",
    "and",
    "are",
    "at",
    "for",
    "from",
    "has",
    "have",
    "her",
    "his",
    "i",
    "in",
    "is",
    "it",
    "me",
    "my",
    "of",
    "on",
    "our",
    "the",
    "their",
    "to",
    "user",
    "was",
    "we",
    "with",
}


def _find_supporting_quote(
    memory_content: str,
    events: list[RawContextEvent],
    *,
    quote_anchor: str | None = None,
) -> str | None:
    """Return the source quote that best supports the memory content."""
    if quote_anchor and _quote_anchor_is_supported(quote_anchor, events):
        return quote_anchor.strip()
    if not events:
        return None
    best_event = max(events, key=lambda e: _evidence_overlap_count(memory_content, e.text or ""))
    if best_event.text:
        return best_event.text
    return events[0].text or None


def _find_supporting_quote_for_event(
    memory_content: str,
    event: RawContextEvent,
    *,
    quote_anchor: str | None = None,
) -> str | None:
    """Return a quote that is actually present in this evidence event.

    The best quote in a chunk may come from a different event.  Attaching that
    same quote to every EvidenceSpan makes unrelated events look grounded, so a
    span only receives a quote when the quote anchor or source text belongs to
    that exact event.
    """
    event_text = event.text or ""
    if quote_anchor:
        anchor = " ".join(quote_anchor.split())
        normalized_event = " ".join(event_text.split())
        if anchor and anchor.casefold() in normalized_event.casefold():
            return quote_anchor.strip()
        return None
    if _evidence_overlap_count(memory_content, event_text) > 0:
        return event_text
    return None


def _supporting_events(
    memory_content: str,
    events: list[RawContextEvent],
    *,
    quote_anchor: str | None = None,
) -> list[RawContextEvent] | None:
    """Return only events whose text has meaningful overlap with the memory content."""
    if not events:
        return None
    if quote_anchor:
        anchor = " ".join(quote_anchor.split()).casefold()
        supporting = [e for e in events if anchor and anchor in " ".join((e.text or "").split()).casefold()]
        return supporting if supporting else None
    supporting = [e for e in events if _evidence_overlap_count(memory_content, e.text or "") > 0]
    return supporting if supporting else None


def _has_sufficient_evidence(
    memory_content: str,
    events: list[RawContextEvent],
    *,
    quote_anchor: str | None = None,
) -> bool:
    """Reject extracted memories without grounded source support.

    The production prompt often paraphrases first-person speech into third-person
    memories, so exact containment is too strict.  But allowing evidence fallback
    when only stopwords overlap lets unsupported memories leak into the benchmark.
    Require meaningful source-token overlap, and when the typed extractor emits a
    quote_anchor, require that anchor to be a literal source substring.
    """
    memory_words = _meaningful_words(memory_content)
    if not memory_words:
        return False
    best_overlap = max((_evidence_overlap_count(memory_content, event.text or "") for event in events), default=0)
    required_overlap = 2 if len(memory_words) >= 4 else 1
    if best_overlap < required_overlap:
        return False
    return _quote_anchor_is_supported(quote_anchor, events)


def _quote_anchor_is_supported(quote_anchor: str | None, events: list[RawContextEvent]) -> bool:
    """True when no anchor is supplied or the anchor is a real source quote."""
    if quote_anchor is None:
        return True
    anchor = " ".join(quote_anchor.split()).casefold()
    if not anchor:
        return False
    return any(anchor in " ".join((event.text or "").split()).casefold() for event in events)


def _evidence_overlap_count(text_a: str, text_b: str) -> int:
    """Count meaningful words shared by two texts."""
    return len(_meaningful_words(text_a) & _meaningful_words(text_b))


def _meaningful_words(text: str) -> set[str]:
    words = set(re.findall(r"[a-z0-9][a-z0-9'_-]*", text.casefold()))
    return {word for word in words if len(word) > 2 and word not in _EVIDENCE_STOPWORDS}


def _events_by_conversation(events: list[RawContextEvent]) -> dict[str, list[RawContextEvent]]:
    grouped = defaultdict(list)
    for event in events:
        conversation_id = event.source_ref.conversation_id or "offline"
        grouped[conversation_id].append(event)
    for conversation_id, grouped_events in grouped.items():
        grouped[conversation_id] = sorted(
            grouped_events,
            key=lambda event: (
                (event.start_at or event.end_at).timestamp() if (event.start_at or event.end_at) else 0.0,
                event.order or 0,
                event.event_id,
            ),
        )
    return dict(grouped)


def _chunks(events: list[RawContextEvent], size: int) -> Iterable[list[RawContextEvent]]:
    for index in range(0, len(events), size):
        yield events[index : index + size]


def _to_transcript_segment(event: RawContextEvent, index: int) -> TranscriptSegment:
    is_user = True if not event.speaker else event.speaker.is_actor_user is not False
    start = float(index)
    end = start + 1.0
    if event.start_at and event.end_at:
        start = event.start_at.timestamp()
        end = event.end_at.timestamp()
    return TranscriptSegment(
        id=event.event_id,
        text=event.text or "",
        speaker=event.speaker.speaker_id if event.speaker and event.speaker.speaker_id else "SPEAKER_00",
        is_user=is_user,
        person_id=event.speaker.person_id if event.speaker else None,
        start=start,
        end=end,
    )


def _frame_subject(
    memory: ProductionLikeMemory,
    actor: ActorDescriptor | None,
    *,
    allow_non_user: bool = False,
):
    """Resolve frame subject, optionally preserving route-specific non-user subjects."""
    actor_ref = _actor_subject(actor)
    if not allow_non_user:
        return actor_ref
    raw_subject = (memory.subject_entity_id or "").strip()
    if not raw_subject:
        return actor_ref
    actor_id = (actor.user_id or actor.synthetic_user_id) if actor else "ent_user"
    if raw_subject in {"user", "ent_user", actor_id}:
        return actor_ref
    if not raw_subject.startswith("ent_"):
        return actor_ref
    if raw_subject.startswith("ent_speaker_"):
        canonical_name = raw_subject.replace("ent_", "").replace("_", " ")
        entity_type = "person"
    else:
        canonical_name = raw_subject.replace("ent_", "").replace("_", " ")
        entity_type = "project" if raw_subject in {"ent_omi", "ent_remux"} else "concept"
    return EntityRef(
        entity_id=raw_subject,
        entity_type=entity_type,
        canonical_name=canonical_name,
        confidence="medium",
    )


def _actor_subject(actor: ActorDescriptor | None):
    return EntityRef(
        entity_id=(actor.user_id or actor.synthetic_user_id) if actor else None,
        entity_type="user",
        canonical_name=_user_name(actor),
        confidence="high",
    )


def _category_value(category) -> str:
    return getattr(category, "value", str(category))


def _frame_type(category) -> str:
    if _category_value(category) == "interesting":
        return "interest"
    return "personal_fact"


def _predicate(category) -> str:
    if _category_value(category) == "interesting":
        return "learned"
    return "related_to"
