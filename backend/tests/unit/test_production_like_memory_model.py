import asyncio
from datetime import datetime, timezone

from utils.memory_ingestion.adapters import production_like_model
from utils.memory_ingestion.adapters.production_like_model import ProductionLikeMemory, ProductionLikeMemoryModelClient
from utils.memory_ingestion.models import (
    ActorDescriptor,
    EventQuality,
    LiberalMemoryCandidate,
    CandidateEvidenceSpan,
    CandidateEntityMention,
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
        segments=[
            production_like_model.TranscriptSegment(
                text="I use Warp terminal every day for coding work.", is_user=True, start=0.0, end=3.0
            )
        ],
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
        kwargs["trace_sink"](
            {
                "stage": "model_call",
                "status": "ok",
                "parsed_facts_before_filter": [{"content": "User uses Warp terminal"}],
                **kwargs.get("trace_context", {}),
            }
        )
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
    assert route_event["metadata"]["route_family"] == "current"
    assert "model_call" in stages
    assert "frame_created" in stages


def test_prodlike_source_route_config_records_chat_v7a(monkeypatch):
    captured = {}

    def fake_extract_memories_with_production_prompt(**kwargs):
        captured.update(kwargs)
        return [ProductionLikeMemory(content="User uses Warp terminal", category="system")]

    monkeypatch.setattr(
        production_like_model,
        "_extract_memories_with_production_prompt",
        fake_extract_memories_with_production_prompt,
    )
    event = _event("I use Warp terminal every day.")
    pipeline_input = _input(event)
    pipeline_input.source.source_type = "chat_exchange"
    client = ProductionLikeMemoryModelClient(source_route_config={"chat_exchange": "v7a"})
    output = asyncio.run(CoreMemoryPipeline(model_client=client).run(pipeline_input))

    assert output.event_frames[0].canonical_text == "User uses Warp terminal"
    assert captured["source_type"] == "chat_exchange"
    route_event = next(event for event in client.trace_events if event["stage"] == "source_route")
    assert route_event["declared_source_type"] == "chat_exchange"
    assert route_event["effective_source_type"] == "chat_exchange"
    assert route_event["metadata"]["route_family"] == "v7a"


class _FlakyLLMThenSuccess:
    def __init__(self):
        self.calls = 0

    def invoke(self, _prompt_value):
        self.calls += 1
        if self.calls == 1:
            raise TimeoutError("Request timed out.")
        from langchain_core.messages import AIMessage

        return AIMessage(
            content='{"facts":[{"content":"User is going to San Francisco to find a cofounder","category":"system"}]}'
        )


def test_prodlike_voice_recall_route_retries_model_call(monkeypatch):
    llm = _FlakyLLMThenSuccess()
    monkeypatch.setattr(production_like_model, "_memory_llm", lambda: llm)
    event = _event("I am going to San Francisco to find a cofounder and a team.")
    pipeline_input = _input(event)
    pipeline_input.source.source_type = "voice_transcript"
    client = ProductionLikeMemoryModelClient(source_route_config={"voice_transcript": "voice_recall_v1"})

    output = asyncio.run(CoreMemoryPipeline(model_client=client).run(pipeline_input))

    assert llm.calls == 2
    assert output.event_frames[0].canonical_text == "User is going to San Francisco to find a cofounder"
    stages = [event["stage"] for event in client.trace_events]
    assert "model_call_retry" in stages
    error_event = next(
        event for event in client.trace_events if event["stage"] == "model_call" and event["status"] == "error"
    )
    ok_event = next(
        event for event in client.trace_events if event["stage"] == "model_call" and event["status"] == "ok"
    )
    assert error_event["will_retry"] is True
    assert error_event["attempt"] == 1
    assert ok_event["attempt"] == 2
    assert ok_event["max_attempts"] == 2
    route_event = next(event for event in client.trace_events if event["stage"] == "source_route")
    assert route_event["metadata"]["route_family"] == "voice_recall_v1"


def test_prodlike_current_voice_route_does_not_retry(monkeypatch):
    llm = _FlakyLLMThenSuccess()
    monkeypatch.setattr(production_like_model, "_memory_llm", lambda: llm)
    event = _event("I am going to San Francisco to find a cofounder and a team.")
    pipeline_input = _input(event)
    pipeline_input.source.source_type = "voice_transcript"
    client = ProductionLikeMemoryModelClient(source_route_config={"voice_transcript": "current"})

    output = asyncio.run(CoreMemoryPipeline(model_client=client).run(pipeline_input))

    assert llm.calls == 1
    assert output.event_frames == []
    error_event = next(
        event for event in client.trace_events if event["stage"] == "model_call" and event["status"] == "error"
    )
    assert error_event["will_retry"] is False
    assert error_event["max_attempts"] == 1


def test_pipeline_output_emits_lightweight_candidates(monkeypatch):
    def fake_extract_memories_with_production_prompt(**_kwargs):
        return [
            ProductionLikeMemory(
                content="SPEAKER_1 works on Remux, a Tmux mobile app.",
                category="system",
                predicate="works_on",
                subject_entity_id="ent_speaker_1",
                subject_attribution="third_party",
                quote_anchor="work on Remux",
            )
        ]

    monkeypatch.setattr(
        production_like_model,
        "_extract_memories_with_production_prompt",
        fake_extract_memories_with_production_prompt,
    )
    event = _event("[SPEAKER_1]: I work on Remux, a Tmux mobile app.")
    pipeline_input = _input(event)
    pipeline_input.source.source_type = "voice_transcript"
    client = ProductionLikeMemoryModelClient(source_route_config={"voice_transcript": "voice_recall_v1"})

    output = asyncio.run(CoreMemoryPipeline(model_client=client).run(pipeline_input))

    assert len(output.candidates) == 1
    candidate = output.candidates[0]
    assert candidate.raw_claim == "SPEAKER_1 works on Remux, a Tmux mobile app."
    assert candidate.predicate_hint == "works_on"
    assert candidate.subject_mention == "ent_speaker_1"
    assert candidate.source_type == "voice_transcript"
    assert candidate.speaker_or_actor_attribution == "third_party"
    assert candidate.evidence_spans[0].quote == "work on Remux"
    assert {m.surface for m in candidate.entity_mentions} >= {"SPEAKER_1", "Remux"}


def test_candidate_schema_serializes_chat_and_ocr_candidates(monkeypatch):
    cases = [
        (
            "chat_exchange",
            "I use Mercury for banking.",
            ProductionLikeMemory(
                content="User uses Mercury for banking.",
                category="tool",
                predicate="uses_tool",
                subject_entity_id="ent_user",
                quote_anchor="Mercury for banking",
            ),
            "primary_user",
            "Mercury",
            "chat_message",
        ),
        (
            "ocr_screenshot_text",
            "Termius account email screen shows user@example.com.",
            ProductionLikeMemory(
                content="User has a visible Termius account email.",
                category="system",
                predicate="has_visible_account",
                subject_entity_id="ent_user",
                quote_anchor="Termius account email",
            ),
            "primary_user",
            "Termius",
            "screen_ocr",
        ),
    ]
    for idx, (source_type, text, memory, attribution, mention, event_type) in enumerate(cases):

        def fake_extract_memories_with_production_prompt(**_kwargs):
            return [memory]

        monkeypatch.setattr(
            production_like_model,
            "_extract_memories_with_production_prompt",
            fake_extract_memories_with_production_prompt,
        )
        pipeline_input = _input(_event(text, event_type=event_type), run_id=f"candidate-{idx}")
        pipeline_input.source.source_type = source_type
        output = _run(pipeline_input)
        dumped = output.model_dump(mode="json")
        assert dumped["candidates"][0]["source_type"] == source_type
        assert dumped["candidates"][0]["speaker_or_actor_attribution"] == attribution
        assert any(m["surface"] == mention for m in dumped["candidates"][0]["entity_mentions"])


def test_prodlike_voice_recall_route_preserves_non_user_subject(monkeypatch):
    def fake_extract_memories_with_production_prompt(**kwargs):
        assert kwargs["route_family"] == "voice_recall_v1"
        return [
            ProductionLikeMemory(
                content="I work on Remux, a Tmux mobile app.",
                category="system",
                predicate="works_on",
                subject_entity_id="ent_speaker_1",
                subject_attribution="third_party",
                quote_anchor="work on Remux",
            )
        ]

    monkeypatch.setattr(
        production_like_model,
        "_extract_memories_with_production_prompt",
        fake_extract_memories_with_production_prompt,
    )
    event = _event("[SPEAKER_1]: I work on Remux, a Tmux mobile app.")
    pipeline_input = _input(event)
    pipeline_input.source.source_type = "voice_transcript"
    client = ProductionLikeMemoryModelClient(source_route_config={"voice_transcript": "voice_recall_v1"})

    output = asyncio.run(CoreMemoryPipeline(model_client=client).run(pipeline_input))

    assert output.event_frames[0].subject.entity_id == "ent_speaker_1"
    assert output.event_frames[0].subject.entity_type == "person"
    assert output.event_frames[0].predicate == "works_on"


def test_prodlike_current_route_keeps_actor_subject_for_extracted_subject(monkeypatch):
    def fake_extract_memories_with_production_prompt(**_kwargs):
        return [
            ProductionLikeMemory(
                content="I work on Remux, a Tmux mobile app.",
                category="system",
                predicate="works_on",
                subject_entity_id="ent_speaker_1",
                subject_attribution="third_party",
                quote_anchor="work on Remux",
            )
        ]

    monkeypatch.setattr(
        production_like_model,
        "_extract_memories_with_production_prompt",
        fake_extract_memories_with_production_prompt,
    )
    event = _event("[SPEAKER_1]: I work on Remux, a Tmux mobile app.")
    pipeline_input = _input(event)
    pipeline_input.source.source_type = "voice_transcript"
    client = ProductionLikeMemoryModelClient(source_route_config={"voice_transcript": "current"})

    output = asyncio.run(CoreMemoryPipeline(model_client=client).run(pipeline_input))

    assert output.event_frames[0].subject.entity_id == "benchmark-user"


def test_liberal_memory_candidate_schema_is_natural_language_and_source_grounded():
    candidate = LiberalMemoryCandidate(
        candidate_id="raw_voice_x:chunk:0:cand:0",
        candidate_text="The user prefers the main Chrome profile for daily workflows.",
        source_type="voice_transcript",
        source_example_id="raw_voice_x",
        source_unit_ids=["raw_voice_x:seg:1"],
        source_artifact_ids=["raw_voice_x"],
        source_chunk_ids=["raw_voice_x:chunk:0"],
        evidence_spans=[
            CandidateEvidenceSpan(
                source_event_id="event-1",
                source_unit_id="raw_voice_x:seg:1",
                source_ref=SourceRef(conversation_id="conversation-1", fixture_id="raw_voice_x"),
                quote="I prefer the main Chrome profile",
                speaker=SpeakerRef(speaker_id="speaker-0", label="Speaker 0", is_actor_user=True),
                start_sec=1.2,
                end_sec=3.4,
            )
        ],
        raw_quotes=["I prefer the main Chrome profile"],
        speaker_or_actor_attribution="user_stated",
        attribution_confidence="high",
        candidate_kind_hint="preference",
        subject_mention="the user",
        entity_mentions=[CandidateEntityMention(surface="Chrome", type_hint="tool")],
        time_qualifiers=["daily"],
        confidence="medium",
        extractor_id="liberal_l1_v1",
        prompt_version="liberal_l1_source_grounded_v1",
    )

    dumped = candidate.model_dump(mode="json")
    assert dumped["schema_version"] == "liberal_memory_candidate.v1"
    assert dumped["candidate_text"].startswith("The user prefers")
    assert dumped["predicate_hint"] is None
    assert dumped["evidence_spans"][0]["source_unit_id"] == "raw_voice_x:seg:1"
    assert dumped["evidence_spans"][0]["start_sec"] == 1.2
    assert dumped["entity_mentions"][0]["surface"] == "Chrome"


def test_pipeline_output_can_include_liberal_candidates_without_final_frame_decision():
    output = _run(_input(_event("No memory should be emitted from this ordinary sentence.")))
    liberal = LiberalMemoryCandidate(
        candidate_id="raw_chat_x:msg:0:cand:0",
        candidate_text="The user may prefer terse benchmark reports.",
        source_type="chat",
        source_example_id="raw_chat_x",
        source_unit_ids=["raw_chat_x:msg:0"],
        source_artifact_ids=["raw_chat_x"],
        evidence_spans=[
            CandidateEvidenceSpan(
                source_event_id="event-1",
                source_unit_id="raw_chat_x:msg:0",
                source_ref=SourceRef(conversation_id="conversation-1", fixture_id="raw_chat_x"),
                quote="prefer terse benchmark reports",
            )
        ],
        raw_quotes=["prefer terse benchmark reports"],
        speaker_or_actor_attribution="user_stated",
    )
    copied = output.model_copy(update={"liberal_candidates": [liberal]})
    dumped = copied.model_dump(mode="json")

    assert dumped["liberal_candidates"][0]["candidate_text"] == liberal.candidate_text
    assert dumped["liberal_candidates"][0]["source_unit_ids"] == ["raw_chat_x:msg:0"]
    # V9 L1 candidates are allowed to exist without forcing an active/review/reject decision.
    assert "decision_state" not in dumped["liberal_candidates"][0]
