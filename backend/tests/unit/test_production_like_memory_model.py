import asyncio
from datetime import datetime, timezone

from utils.memory_ingestion.adapters import production_like_model
from utils.memory_ingestion.adapters.production_like_model import ProductionLikeMemory, ProductionLikeMemoryModelClient
from utils.memory_ingestion.models import (
    ActorDescriptor,
    EventQuality,
    MemoryPipelineInput,
    RawContextEvent,
    SourceDescriptor,
    SourceRef,
    SpeakerRef,
    UserStateSnapshot,
)
from utils.memory_ingestion.pipeline import CoreMemoryPipeline


def _input(event, *, run_id="prodlike-test"):
    return MemoryPipelineInput(
        run_id=run_id,
        mode="offline",
        source=SourceDescriptor(source_type="benchmark_fixture", source_id="fixture-1"),
        actor=ActorDescriptor(synthetic_user_id="benchmark-user", display_name="User"),
        user_state=UserStateSnapshot(snapshot_id="state-1", snapshot_at=datetime(2026, 6, 9, tzinfo=timezone.utc)),
        raw_events=[event],
    )


def _event(text, *, event_type="transcript_segment", speaker=None, quality=None):
    return RawContextEvent(
        event_id="event-1",
        event_type=event_type,
        text=text,
        source_ref=SourceRef(conversation_id="conversation-1", fixture_id="fixture-1"),
        speaker=speaker,
        quality=quality or EventQuality(),
    )


def _patch_extractor(monkeypatch, content):
    def fake_extract_memories_with_production_prompt(**_kwargs):
        return [ProductionLikeMemory(content=content, category="system")]

    monkeypatch.setattr(
        production_like_model,
        "_extract_memories_with_production_prompt",
        fake_extract_memories_with_production_prompt,
    )


def _run(pipeline_input):
    return asyncio.run(CoreMemoryPipeline(model_client=ProductionLikeMemoryModelClient()).run(pipeline_input))


def test_prodlike_health_memories_route_to_review(monkeypatch):
    _patch_extractor(monkeypatch, "User's father has cancer and is receiving treatment.")

    output = _run(_input(_event("My father has cancer and is receiving treatment.")))

    assert output.status == "ok"
    assert output.event_frames[0].sensitivity.level == "high"
    assert output.event_frames[0].sensitivity.categories == ["health", "third_party_private_fact"]
    assert output.event_frames[0].sensitivity.review_required is True
    assert output.decisions[0].action == "route_to_review"


def test_prodlike_ocr_memories_are_medium_confidence_and_reviewed(monkeypatch):
    _patch_extractor(monkeypatch, "User has a visible account email on the screen.")

    output = _run(
        _input(
            _event(
                "visible account email in OCR",
                event_type="screen_ocr",
                quality=EventQuality(quality_flags=["ocr_noisy"]),
            )
        )
    )

    assert output.event_frames[0].confidence == "medium"
    assert output.event_frames[0].uncertainty_reasons == ["low_quality_transcript"]
    assert output.decisions[0].action == "route_to_review"


def test_prodlike_third_party_uncertain_speaker_memories_route_to_review(monkeypatch):
    _patch_extractor(monkeypatch, "John organized pickleball and Rudi invited Saru.")

    output = _run(
        _input(
            _event(
                "John organized pickleball and Rudi invited Saru.",
                speaker=SpeakerRef(speaker_id="speaker-2", label="Speaker 2", is_actor_user=False),
            )
        )
    )

    assert output.event_frames[0].confidence == "medium"
    assert output.event_frames[0].sensitivity.categories == ["third_party_private_fact"]
    assert output.event_frames[0].uncertainty_reasons == ["speaker_uncertain"]
    assert output.decisions[0].action == "route_to_review"


def test_prodlike_unknown_speaker_user_memory_can_auto_accept(monkeypatch):
    _patch_extractor(monkeypatch, "User prefers using the main Chrome instance for daily workflows.")

    output = _run(
        _input(
            _event(
                "I prefer using the main Chrome instance for my daily workflows.",
                speaker=SpeakerRef(speaker_id="speaker-2", label="Speaker 2", is_actor_user=None),
            )
        )
    )

    assert output.event_frames[0].confidence == "medium"
    assert output.event_frames[0].sensitivity.level == "none"
    assert output.event_frames[0].sensitivity.categories == ["ordinary_personal_fact"]
    assert output.event_frames[0].sensitivity.review_required is False
    assert output.event_frames[0].uncertainty_reasons == ["speaker_uncertain"]
    assert output.decisions[0].action == "create_memory"


def test_prodlike_speculative_memory_routes_to_review(monkeypatch):
    _patch_extractor(monkeypatch, "User might switch to Assembly for transcription.")

    output = _run(_input(_event("I might switch to Assembly for transcription.")))

    assert output.event_frames[0].confidence == "medium"
    assert output.event_frames[0].uncertainty_reasons == ["inferred_not_stated"]
    assert output.event_frames[0].sensitivity.review_required is True
    assert output.decisions[0].action == "route_to_review"
