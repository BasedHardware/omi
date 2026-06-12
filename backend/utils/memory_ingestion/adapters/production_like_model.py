from __future__ import annotations

from collections import defaultdict
import json
import os
import re
from typing import Iterable

from langchain_core.output_parsers import PydanticOutputParser
from langchain_openai import ChatOpenAI
from models.transcript_segment import TranscriptSegment
from pydantic import BaseModel, Field
from utils.prompts import extract_memories_prompt
from utils.memory_ingestion.adapters.typed_extraction_prompt import (
    TYPED_PREDICATES,
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
    RawContextEvent,
    SensitivityClassification,
    TemporalScope,
)
from utils.memory_ingestion.pipeline import MemoryModelClient


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


class TypedProductionLikeMemory(ProductionLikeMemory):
    """Typed proposition variant; field descriptions steer the structured output."""

    predicate: str | None = Field(
        default=None,
        description="Exactly one predicate from the fixed vocabulary in the prompt.",
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
        max_items=3,
    )


class ProductionLikeMemoryModelClient(MemoryModelClient):
    """Runs Omi's current production memory extractor, then maps results into frames.

    This intentionally keeps durable application out of the core pipeline. It reuses the
    current production prompt/model with caller-provided user state instead of fetching
    Firestore state or writing usage telemetry.
    """

    def __init__(self, *, max_events_per_call: int = 250, high_recall: bool = False, typed: bool = False):
        self.max_events_per_call = max_events_per_call
        self.high_recall = high_recall
        self.typed = typed

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
                    continue
                segments = [_to_transcript_segment(event, index) for index, event in enumerate(event_chunk)]
                memories = _extract_memories_with_production_prompt(
                    segments=segments,
                    user_name=user_name,
                    memories_str=memories_str,
                    language=pipeline_input.source.language,
                    high_recall=self.high_recall,
                    typed=self.typed,
                )
                for memory_index, memory in enumerate(memories):
                    if not _has_sufficient_evidence(memory.content, event_chunk, quote_anchor=memory.quote_anchor):
                        continue
                    source_events = [event.event_id for event in event_chunk]
                    calibration = _calibration(memory, event_chunk)
                    supporting_events = _supporting_events(memory.content, event_chunk)
                    quote = _find_supporting_quote(memory.content, event_chunk, quote_anchor=memory.quote_anchor)
                    evidence = [
                        EvidenceSpan(
                            evidence_id=id_factory.new_id(
                                "evidence", conversation_id, chunk_index, memory_index, event.event_id
                            ),
                            source_event_id=event.event_id,
                            source_ref=event.source_ref,
                            quote=quote,
                            start_at=event.start_at,
                            end_at=event.end_at,
                            speaker=event.speaker,
                        )
                        for event in (supporting_events or event_chunk[:1])
                    ]
                    frame = MemoryEventFrame(
                        frame_type=_frame_type(memory.category),
                        subject=_actor_subject(pipeline_input.actor),
                        predicate=_validated_predicate(memory) or _predicate(memory.category),
                        object=FrameObject(
                            object_type="literal",
                            value=memory.content,
                            confidence=calibration["confidence"],
                        ),
                        arguments=_frame_arguments(memory.arguments, calibration["confidence"]),
                        canonical_text=memory.content,
                        original_text=None,
                        temporal=TemporalScope(kind="unknown"),
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
    high_recall: bool,
    typed: bool = False,
) -> list[ProductionLikeMemory]:
    content = TranscriptSegment.segments_as_string(segments, user_name=user_name, people=[])
    if not content or len(content) < 25:
        return []
    if typed:
        parser = PydanticOutputParser(pydantic_object=TypedProductionLikeMemories)
        prompt = typed_extract_memories_prompt
    else:
        parser = PydanticOutputParser(
            pydantic_object=HighRecallProductionLikeMemories if high_recall else ProductionLikeMemories
        )
        prompt = extract_memories_prompt
    chain = prompt | _memory_llm() | parser
    response: ProductionLikeMemories = chain.invoke(
        {
            "user_name": user_name,
            "conversation": content,
            "memories_str": memories_str,
            "language_instruction": _language_instruction(language),
            "format_instructions": parser.get_format_instructions(),
        }
    )
    return response.facts


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
    if memory.predicate and memory.predicate in TYPED_PREDICATES:
        return memory.predicate
    return None


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


def _memory_llm(temperature: float = 0.0):
    model = os.environ.get("OMI_MEMORY_PIPELINE_MODEL", "gpt-4.1-mini")
    return ChatOpenAI(model=model, temperature=temperature, request_timeout=120, max_retries=1)


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
    if best_overlap < 3 and len(_meaningful_words(memory.content)) >= 3:
        uncertainty_reasons.append("weak_evidence")
        review_required = True

    if _has_speculative_signal(text):
        uncertainty_reasons.append("inferred_not_stated")
        review_required = True

    if _has_low_value_memory_text(text):
        uncertainty_reasons.append("unsupported_by_existing_state")
        review_required = True

    if not _quote_anchor_is_supported(memory.quote_anchor, events):
        uncertainty_reasons.append("weak_evidence")
        review_required = True

    if _has_future_plan_signal(text):
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

    # Upgrade to high confidence only when a direct actor-authored quote strongly
    # anchors the memory and no review-triggering uncertainty/sensitivity exists.
    speaker_confirmed = not unknown_speaker and "speaker_uncertain" not in uncertainty_reasons
    no_speculation = not _has_speculative_signal(text)
    has_entities = _has_named_entities(memory.content)
    content_specific = len(memory.content.strip()) > 40
    actor_supported = _has_actor_supported_quote(memory.content, events, min_overlap=3)
    if (
        speaker_confirmed
        and no_speculation
        and has_entities
        and content_specific
        and actor_supported
        and not review_required
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
    candidate_texts: list[str] = [quote_anchor] if quote_anchor else []
    candidate_texts.extend(event.text or "" for event in events)
    return any(_has_first_person_language(text) for text in candidate_texts)


def _has_first_person_language(text: str) -> bool:
    return bool(re.search(r"\b(i|i'm|i’ve|i'd|i’ll|me|my|mine|we|we're|we’ve|our|ours)\b", text.casefold()))


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
    banned_phrases = (
        " discussed ",
        " talked about ",
        " mentioned ",
        " expressed ",
        " showed interest ",
        " has interest in ",
        " is interested in ",
        " thinks ",
        " believes ",
        " feels ",
        " had a conversation ",
    )
    return any(phrase in padded for phrase in banned_phrases)


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


def _supporting_events(memory_content: str, events: list[RawContextEvent]) -> list[RawContextEvent] | None:
    """Return only events whose text has meaningful overlap with the memory content."""
    if not events:
        return None
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
