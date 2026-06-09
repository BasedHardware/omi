from __future__ import annotations

from collections import defaultdict
from typing import Iterable

from models.transcript_segment import TranscriptSegment
from utils.memory_ingestion.ids import StableIdFactory
from utils.memory_ingestion.models import (
    ActorDescriptor,
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


class ProductionLikeMemoryModelClient(MemoryModelClient):
    """Runs Omi's current production memory extractor, then maps results into frames.

    This intentionally keeps durable application out of the core pipeline. It reuses the
    current production prompt/model path (`new_memories_extractor`) with caller-provided
    user state instead of fetching Firestore state.
    """

    def __init__(self, *, max_events_per_call: int = 250):
        self.max_events_per_call = max_events_per_call

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
                segments = [_to_transcript_segment(event, index) for index, event in enumerate(event_chunk)]
                from utils.llm.memories import new_memories_extractor

                memories = new_memories_extractor(
                    uid=pipeline_input.actor.user_id if pipeline_input.actor else "offline",
                    segments=segments,
                    user_name=user_name,
                    memories_str=memories_str,
                    language=pipeline_input.source.language,
                )
                for memory_index, memory in enumerate(memories):
                    source_events = [event.event_id for event in event_chunk]
                    evidence = [
                        EvidenceSpan(
                            evidence_id=id_factory.new_id(
                                "evidence", conversation_id, chunk_index, memory_index, event.event_id
                            ),
                            source_event_id=event.event_id,
                            source_ref=event.source_ref,
                            quote=None,
                            start_at=event.start_at,
                            end_at=event.end_at,
                            speaker=event.speaker,
                        )
                        for event in event_chunk[:5]
                    ]
                    frame = MemoryEventFrame(
                        frame_type=_frame_type(memory.category),
                        subject=_actor_subject(pipeline_input.actor),
                        predicate=_predicate(memory.category),
                        object=FrameObject(object_type="literal", value=memory.content, confidence="high"),
                        canonical_text=memory.content,
                        original_text=None,
                        temporal=TemporalScope(kind="unknown"),
                        durability="long_term",
                        sensitivity=SensitivityClassification(
                            level="none",
                            categories=(
                                ["ordinary_personal_fact"]
                                if memory.category == MemoryCategory.system
                                else ["ordinary_work_fact"]
                            ),
                            auto_store_allowed=True,
                            review_required=False,
                        ),
                        scope="conversation",
                        scope_ref=event_chunk[0].source_ref if event_chunk else None,
                        importance="high",
                        evidence=evidence,
                        source_event_ids=source_events,
                        confidence="high",
                        extraction=ExtractionMetadata(
                            extractor="omi_production_memory_extractor",
                            model="memories",
                            prompt_version="utils.prompts.extract_memories_prompt",
                            source_block_id=f"{conversation_id}:{chunk_index}",
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
        return ModelManifest(
            extractor_model=pipeline_input.config.models.extractor_model or "memories",
            provider_versions={"memory_ingestion": "production_like.v1"},
            prompt_versions={"frame_extraction": "utils.prompts.extract_memories_prompt"},
        )


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
    from utils.memory_ingestion.models import EntityRef

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
