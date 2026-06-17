from langchain_core.messages import AIMessage

from models.v17_memory_contracts import L1MemoryArchiveItem, LifecycleState
from utils.llm.working_memory import (
    extract_l1_memory_archive_items_from_text,
    extract_working_memory_observations_from_text,
)


class FakeLLM:
    def __init__(self, content):
        self.content = content
        self.calls = []

    def invoke(self, messages):
        self.calls.append(messages)
        return AIMessage(content=self.content)


def test_l1_working_memory_extractor_preserves_source_refs_and_status_labels():
    fake_llm = FakeLLM("""
        {
          "observations": [
            {
              "observation_id": "obs_existing",
              "packet_id": "pkt_source_1",
              "content": "User prefers automatic memory capture over manual knowledge-base maintenance.",
              "evidence_ids": ["ev_source_1_0"],
              "source_refs": [{"source_id": "source_1", "source_unit_id": "0", "quote": "I want something automatic."}],
              "subject_entity_id": "user",
              "subject_scope": "primary_user",
              "status": "working",
              "confidence": "high",
              "risk_flags": [],
              "predicate": "prefers",
              "arguments": {"thing": "automatic memory capture"}
            }
          ]
        }
        """)

    observations = extract_working_memory_observations_from_text(
        uid="user_1",
        source_id="source_1",
        source_type="chat_exchange",
        text="I want something automatic.",
        user_name="David",
        llm=fake_llm,
    )

    assert len(observations) == 1
    observation = observations[0]
    assert observation.status == LifecycleState.working
    assert observation.allowed_use == "read_with_status"
    assert observation.source_refs[0]["quote"] == "I want something automatic."
    assert observation.evidence_ids == ["ev_source_1_0"]
    assert not hasattr(observation, "memory_id")
    assert fake_llm.calls, "extractor should invoke the provided product-compatible LLM interface"


def test_l1_working_memory_extractor_derives_hidden_allowed_use_for_secret_risk():
    fake_llm = FakeLLM("""
        {
          "observations": [
            {
              "observation_id": "obs_secret",
              "content": "User displayed an API key.",
              "evidence_ids": ["ev_source_1_0"],
              "source_refs": [{"source_id": "source_1", "source_unit_id": "0", "quote": "sk-..."}],
              "status": "working",
              "confidence": "high",
              "risk_flags": ["secret"]
            }
          ]
        }
        """)

    observations = extract_working_memory_observations_from_text(
        uid="user_1",
        source_id="source_1",
        source_type="screenshot_ocr",
        text="sk-...",
        user_name="David",
        llm=fake_llm,
    )

    assert observations[0].status == LifecycleState.working
    assert observations[0].allowed_use == "hidden"


def test_l1_working_memory_extractor_preserves_literal_relationship_fields():
    fake_llm = FakeLLM("""
        {
          "observations": [
            {
              "observation_id": "obs_literal",
              "content": "Another speaker advised choosing 1440x900 as the closest normal aspect ratio.",
              "literal_observation": "Another speaker advised choosing 1440x900 as the closest normal aspect ratio.",
              "speaker_attribution": "non_primary_speaker",
              "source_mode": "conversation",
              "relationship_to_user": "other_speaker",
              "subject": "generic_content",
              "interpretation_level": "literal",
              "why_captured": "Literal device-resolution advice appeared in the source.",
              "evidence_ids": ["ev_source_1_0"],
              "source_refs": [{"source_id": "source_1", "source_unit_id": "0", "quote": "ставь 1440 на 900"}],
              "status": "working",
              "confidence": "medium",
              "risk_flags": []
            }
          ]
        }
        """)

    observations = extract_working_memory_observations_from_text(
        uid="user_1",
        source_id="source_1",
        source_type="voice_transcript",
        text="Другой спикер говорит: ставь 1440 на 900, это самое близкое к нормальному соотношению сторон.",
        user_name="David",
        llm=fake_llm,
    )

    observation = observations[0]
    assert observation.literal_observation.startswith("Another speaker advised")
    assert observation.speaker_attribution == "non_primary_speaker"
    assert observation.source_mode == "conversation"
    assert observation.relationship_to_user == "other_speaker"
    assert observation.subject == "generic_content"
    assert observation.interpretation_level == "literal"
    assert observation.why_captured == "Literal device-resolution advice appeared in the source."


def test_l1_working_memory_extractor_skips_tiny_sources_without_llm_call():
    fake_llm = FakeLLM('{"observations": []}')

    observations = extract_working_memory_observations_from_text(
        uid="user_1",
        source_id="source_1",
        source_type="chat_exchange",
        text="ok",
        user_name="David",
        llm=fake_llm,
    )

    assert observations == []
    assert fake_llm.calls == []


def test_l1_archive_extractor_emits_general_archive_items_without_lifecycle_routes():
    fake_llm = FakeLLM("""
        {
          "items": [
            {
              "text": "User was troubleshooting Rust fog and TAA settings.",
              "class": "general",
              "source_refs": [{"source_id": "source_1", "source_unit_id": "0", "quote": "why does the distance look foggy in Rust with TAA"}],
              "evidence_quotes": ["why does the distance look foggy in Rust with TAA"],
              "speaker_label": "speaker_0",
              "confidence": "medium",
              "risk_flags": []
            }
          ]
        }
        """)

    items = extract_l1_memory_archive_items_from_text(
        uid="user_1",
        source_id="source_1",
        source_type="voice_transcript",
        text="why does the distance look foggy in Rust with TAA",
        user_name="David",
        llm=fake_llm,
    )

    assert len(items) == 1
    assert items[0].schema_version == "l1_memory_archive_item.v1"
    assert items[0].archive_class.value == "general"
    assert items[0].normal_search_allowed is True
    assert items[0].is_stable_profile_fact is False
    assert not hasattr(items[0], "status")
    assert not hasattr(items[0], "route_hint")


def test_l1_archive_extractor_converts_secret_risk_to_sensitive_archive():
    fake_llm = FakeLLM("""
        {
          "items": [
            {
              "text": "A password is visible in screenshot OCR.",
              "class": "general",
              "evidence_quotes": ["password: hunter2"],
              "confidence": "high",
              "risk_flags": ["credential"]
            }
          ]
        }
        """)

    items = extract_l1_memory_archive_items_from_text(
        uid="user_1",
        source_id="source_1",
        source_type="screenshot_ocr",
        text="password: hunter2",
        user_name="David",
        llm=fake_llm,
    )

    assert items[0].archive_class.value == "sensitive"
    assert items[0].normal_search_allowed is False
    assert items[0].allowed_use == "restricted_archive_only"
