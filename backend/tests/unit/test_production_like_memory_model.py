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


def test_prodlike_passive_media_monologue_does_not_create_user_memories(monkeypatch):
    def fail_if_called(**_kwargs):
        raise AssertionError("passive media transcripts should be filtered before extraction")

    monkeypatch.setattr(
        production_like_model,
        "_extract_memories_with_production_prompt",
        fail_if_called,
    )

    output = _run(
        _input(
            _event(
                "This video is largely based on the book Zodiac. "
                "As always, you'll find the link and all our sources in the description. "
                "The newsroom of the San Francisco Chronicle is buzzing with life.",
                speaker=SpeakerRef(speaker_id="speaker-0", label="Speaker 0", is_actor_user=None),
            )
        )
    )

    assert output.status == "ok"
    assert output.event_frames == []
    assert output.mutation_plan.creates == []
    assert output.review_items == []


def test_prodlike_speculative_memory_routes_to_review(monkeypatch):
    _patch_extractor(monkeypatch, "User might switch to Assembly for transcription.")

    output = _run(_input(_event("I might switch to Assembly for transcription.")))

    assert output.event_frames[0].confidence == "medium"
    assert output.event_frames[0].uncertainty_reasons == ["inferred_not_stated"]
    assert output.event_frames[0].sensitivity.review_required is True
    assert output.decisions[0].action == "route_to_review"


def test_prodlike_future_plans_route_to_review(monkeypatch):
    _patch_extractor(monkeypatch, "User plans to meet at the coworking space at 5pm today.")

    output = _run(_input(_event("I plan to meet at the coworking space at 5pm today.")))

    assert output.event_frames[0].confidence == "medium"
    assert output.event_frames[0].uncertainty_reasons == ["temporal_scope_unclear"]
    assert output.event_frames[0].sensitivity.review_required is True
    assert output.decisions[0].action == "route_to_review"


class _FakeLLM:
    def invoke(self, _prompt_value):
        from langchain_core.messages import AIMessage
        return AIMessage(content='{"facts":[{"content":"User uses Warp terminal","category":"system"}]}')


def test_prodlike_trace_captures_raw_response_before_parse(monkeypatch):
    trace_events = []
    monkeypatch.setattr(production_like_model, "_memory_llm", lambda: _FakeLLM())

    memories = production_like_model._extract_memories_with_production_prompt(
        segments=[production_like_model.TranscriptSegment(text="I use Warp terminal every day for coding work.", is_user=True, start=0.0, end=3.0)],
        user_name="User",
        memories_str="you do not yet know durable facts about User.\n",
        language=None,
        source_type="chat_exchange",
        high_recall=False,
        typed=False,
        trace_sink=trace_events.append,
        trace_context={"conversation_id": "conv-1", "chunk_index": 0},
    )

    assert memories[0].content == "User uses Warp terminal"
    event = next(e for e in trace_events if e.get("stage") == "model_call")
    assert event["status"] == "ok"
    raw_response = event["raw_model_response"]
    raw_content = raw_response.get("content", "") if isinstance(raw_response, dict) else str(raw_response)
    assert "User uses Warp terminal" in raw_content
    assert event["parsed_facts_before_filter"][0]["content"] == "User uses Warp terminal"


def test_prodlike_client_trace_sink_records_candidate_and_frame(monkeypatch):
    def fake_extract_memories_with_production_prompt(**kwargs):
        kwargs["trace_sink"]({
            "stage": "model_call",
            "status": "ok",
            "parsed_facts_before_filter": [{"content": "User uses Warp terminal"}],
            **kwargs.get("trace_context", {}),
        })
        return [ProductionLikeMemory(content="User uses Warp terminal", category="system")]

    monkeypatch.setattr(
        production_like_model,
        "_extract_memories_with_production_prompt",
        fake_extract_memories_with_production_prompt,
    )
    client = ProductionLikeMemoryModelClient()
    output = asyncio.run(CoreMemoryPipeline(model_client=client).run(_input(_event("I use Warp terminal every day."))))

    assert output.event_frames[0].canonical_text == "User uses Warp terminal"
    stages = [event["stage"] for event in client.trace_events]
    assert "source_route" in stages
    route_event = next(event for event in client.trace_events if event["stage"] == "source_route")
    assert route_event["declared_source_type"] == "benchmark_fixture"
    assert route_event["effective_source_type"] == "benchmark_fixture"
    assert route_event["reason"] == "declared_source_type_passthrough"
    assert "model_call" in stages
    assert "frame_created" in stages

