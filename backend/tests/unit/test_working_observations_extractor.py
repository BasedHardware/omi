import json
import os

os.environ.setdefault("FIRESTORE_EMULATOR_HOST", "localhost:8787")
os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "test")

import pytest
from langchain_core.messages import AIMessage

from models.memory_contracts import L1MemoryArchiveClass, L1MemoryArchiveItem
from models.transcript_segment import TranscriptSegment
from utils.llm import working_observations
from utils.llm.conversation_prompt_prefix import ConversationPromptPrefix
from utils.llm.memories import extract_canonical_l1_memory_candidates
from utils.llm.working_observations import (
    MAX_WORKING_OBSERVATION_ITEMS,
    WorkingObservationExtractionError,
    _build_l1_messages,
    extract_l1_memory_archive_items_from_text,
)
from utils.llm.usage_tracker import get_current_context


class FakeLLM:
    def __init__(self, content):
        self.content = content
        self.calls = []
        self.usage_contexts = []

    def invoke(self, messages):
        self.calls.append(messages)
        self.usage_contexts.append(get_current_context())
        return AIMessage(content=self.content)


class FailingLLM:
    def invoke(self, messages):
        raise RuntimeError("provider unavailable")


def _l1_system_prompt() -> str:
    return _build_l1_messages(
        "David",
        "voice_transcript",
        "A source transcript long enough for prompt construction.",
        "Return the requested JSON schema.",
    )[0][1]


def test_l1_prompt_drops_unidentified_non_primary_speakers_but_keeps_named_relationships():
    prompt = _l1_system_prompt()

    assert "Do not emit an item about an unidentified non-primary speaker" in prompt
    assert "Named people and known roles" in prompt
    assert '"Sarah", "Mom", "Dr. Patel", "teammate"' in prompt
    assert "archive the item as about that speaker" not in prompt
    assert '"unidentified non-primary speaker (speaker_1)"' not in prompt


def test_l1_prompt_drops_self_hedging_attribution_instead_of_storing_uncertainty_text():
    prompt = _l1_system_prompt()

    assert "If attribution is uncertain, do not emit the item" in prompt
    assert "Do not hedge inside the item text or `about` field" in prompt
    assert "say so in the item text/about field" not in prompt


def test_l1_prompt_excludes_generic_product_descriptions_without_losing_owner_decisions():
    prompt = _l1_system_prompt()

    assert "Generic descriptions of a product or company" in prompt
    assert "owner's decision, preference, constraint, plan, or commitment" in prompt


def test_canonical_l1_wrapper_keeps_broad_source_aware_candidates_out_of_archive_routes(monkeypatch):
    extracted = [
        L1MemoryArchiveItem(
            text=f"Candidate {index}",
            evidence_quotes=[f"exact quote {index}"],
            speaker_label="speaker_0" if index != 2 else "speaker_1",
            about="the user" if index != 2 else "unidentified non-primary speaker (speaker_1)",
            archive_class="sensitive" if index == 2 else "general",
        )
        for index in range(4)
    ]
    captured = {}

    def fake_extract(**kwargs):
        captured.update(kwargs)
        return extracted

    monkeypatch.setattr(working_observations, "extract_l1_memory_archive_items_from_text", fake_extract)
    segments = [
        TranscriptSegment(
            id="segment-user",
            text="I like coffee, plan to travel, and prefer concise updates.",
            speaker="SPEAKER_00",
            is_user=True,
            start=0.0,
            end=4.0,
        ),
        TranscriptSegment(
            id="segment-other",
            text="I am preparing the launch deck for Friday.",
            speaker="SPEAKER_01",
            is_user=False,
            start=4.0,
            end=8.0,
        ),
    ]

    candidates = extract_canonical_l1_memory_candidates(
        "user_1",
        "conversation_1",
        segments,
        user_name="David",
        language="en",
    )

    assert len(candidates) == 4
    assert [candidate.evidence_quotes for candidate in candidates] == [
        ["exact quote 0"],
        ["exact quote 1"],
        ["exact quote 2"],
        ["exact quote 3"],
    ]
    assert candidates[2].about == "unidentified non-primary speaker (speaker_1)"
    assert candidates[2].archive_class == L1MemoryArchiveClass.sensitive
    assert captured["source_type"] == "voice_transcript"
    assert captured["persist_route_outcomes"] is False
    assert "David:" in captured["text"]
    assert "Speaker 1:" in captured["text"]


def test_canonical_l1_wrapper_threads_rejection_examples_to_the_prompt_boundary(monkeypatch):
    captured = []

    def fake_extract(**kwargs):
        captured.append(kwargs)
        return []

    feedback = ["The user likes an aisle seat"]
    monkeypatch.setattr(working_observations, "extract_l1_memory_archive_items_from_text", fake_extract)
    segments = [
        TranscriptSegment(
            id="segment-user",
            text="I am booking another flight and thinking about seat selection.",
            speaker="SPEAKER_00",
            is_user=True,
            start=0.0,
            end=4.0,
        )
    ]

    extract_canonical_l1_memory_candidates(
        "user-feedback",
        "conversation-feedback",
        segments,
        user_name="David",
        language="en",
        rejected_memory_examples=feedback,
    )

    assert captured[-1]["rejected_memory_examples"] == tuple(feedback)


def test_l1_rejection_examples_stay_after_the_shared_prompt_cache_breakpoint():
    rejected_text = "The user likes an aisle seat"
    fake_llm = FakeLLM('{"items": []}')
    prefix = ConversationPromptPrefix(
        conversation_id="conversation-cache-feedback",
        context="FULL TRANSCRIPT\n" + "A long cacheable transcript. " * 300,
    )

    extract_l1_memory_archive_items_from_text(
        uid="user-cache-feedback",
        source_id="conversation-cache-feedback",
        source_type="voice_transcript",
        text="A long cacheable transcript.",
        user_name="David",
        persist_route_outcomes=False,
        llm=fake_llm,
        prompt_prefix=prefix,
        prompt_cache_enabled=True,
        rejected_memory_examples=[rejected_text],
    )

    messages = fake_llm.calls[0]
    assert messages[1]["content"][0]["prompt_cache_breakpoint"] == {"mode": "explicit"}
    assert rejected_text not in str(messages[:2])
    assert rejected_text not in str(messages[2])
    assert rejected_text in str(messages[3])


def test_canonical_l1_wrapper_sends_short_voice_transcript_to_broad_extractor(monkeypatch):
    captured = {}

    def fake_extract(**kwargs):
        captured.update(kwargs)
        return []

    monkeypatch.setattr(working_observations, "extract_l1_memory_archive_items_from_text", fake_extract)
    segments = [
        TranscriptSegment(
            id="segment-short",
            text="Call Mom",
            speaker="SPEAKER_00",
            is_user=True,
            start=0.0,
            end=1.0,
        )
    ]

    assert (
        extract_canonical_l1_memory_candidates(
            "user_short",
            "conversation_short",
            segments,
            user_name="D",
            language="en",
        )
        == []
    )

    assert captured["source_type"] == "voice_transcript"
    assert captured["text"].strip()
    assert len(captured["text"]) < 25


def test_canonical_l1_wrapper_skips_whitespace_transcript_before_rendering_speaker_labels(monkeypatch):
    def fake_extract(**kwargs):
        pytest.fail(f"whitespace transcript reached extractor: {kwargs}")

    monkeypatch.setattr(working_observations, "extract_l1_memory_archive_items_from_text", fake_extract)
    segments = [
        TranscriptSegment(
            id="segment-blank",
            text=" \n\t ",
            speaker="SPEAKER_00",
            is_user=True,
            start=0.0,
            end=1.0,
        )
    ]

    assert (
        extract_canonical_l1_memory_candidates(
            "user_blank",
            "conversation_blank",
            segments,
            user_name="D",
            language="en",
        )
        == []
    )


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
        user_name=None,
        persist_route_outcomes=False,
        llm=fake_llm,
    )

    assert len(items) == 1
    assert items[0].schema_version == "l1_memory_archive_item.v1"
    assert items[0].archive_class.value == "general"
    assert items[0].normal_search_allowed is True
    assert items[0].is_stable_profile_fact is False
    assert not hasattr(items[0], "status")
    assert not hasattr(items[0], "route_hint")
    assert fake_llm.usage_contexts[0].uid == "user_1"
    assert fake_llm.usage_contexts[0].feature == "memories"


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
        user_name=None,
        persist_route_outcomes=False,
        llm=fake_llm,
    )

    assert items[0].archive_class.value == "sensitive"
    assert items[0].normal_search_allowed is False
    assert items[0].allowed_use == "restricted_archive_only"


def test_l1_archive_extractor_persists_archive_route_outcomes_with_deterministic_identity(monkeypatch):
    persisted = []

    def fake_persist(outcome, *, db_client=None):
        persisted.append(outcome)
        return outcome

    monkeypatch.setattr(working_observations, "persist_non_active_route_outcome", fake_persist)
    fake_llm = FakeLLM("""
        {
          "items": [
            {
              "text": "User adopted a rescue dog named Milo.",
              "class": "general",
              "evidence_quotes": ["we adopted Milo from the shelter"],
              "confidence": "high"
            }
          ]
        }
        """)

    items = extract_l1_memory_archive_items_from_text(
        uid="user_1",
        source_id="source_1",
        source_type="voice_transcript",
        text="we adopted Milo from the shelter and he likes carrots",
        run_id="run_1",
        llm=fake_llm,
    )

    assert len(items) == 1
    assert len(persisted) == 1
    outcome = persisted[0]
    assert outcome.uid == "user_1"
    assert outcome.route.value == "archive"
    assert outcome.source_ids == ["source_1"]
    assert outcome.run_id == "run_1"
    assert outcome.patch_id == items[0].archive_id
    assert outcome.idempotency_key == f"l1-archive:source_1:{items[0].archive_id}"
    assert outcome.default_long_term_visible is False
    assert outcome.audit_metadata["archive_id"] == items[0].archive_id
    assert outcome.audit_metadata["archive_class"] == "general"
    assert outcome.audit_metadata["preserved"] is True
    assert outcome.audit_metadata["observable_loss"] is False


def test_l1_archive_extractor_skips_tiny_sources_without_llm_call():
    fake_llm = FakeLLM('{"items": []}')

    items = extract_l1_memory_archive_items_from_text(
        uid="user_1",
        source_id="source_1",
        source_type="chat_exchange",
        text="ok",
        user_name=None,
        persist_route_outcomes=False,
        llm=fake_llm,
    )

    assert items == []
    assert fake_llm.calls == []


def test_l1_archive_extractor_accepts_short_voice_transcript():
    fake_llm = FakeLLM("""
        {
          "items": [
            {
              "text": "The user needs to call Mom.",
              "class": "general",
              "evidence_quotes": ["Call Mom"],
              "speaker_label": "speaker_0",
              "about": "the user"
            }
          ]
        }
        """)

    items = extract_l1_memory_archive_items_from_text(
        uid="user_short",
        source_id="source_short",
        source_type="voice_transcript",
        text="Call Mom",
        user_name="D",
        persist_route_outcomes=False,
        llm=fake_llm,
    )

    assert [item.text for item in items] == ["The user needs to call Mom."]
    assert len(fake_llm.calls) == 1


def test_l1_archive_extractor_skips_whitespace_voice_source_without_llm_call():
    fake_llm = FakeLLM('{"items": []}')

    items = extract_l1_memory_archive_items_from_text(
        uid="user_short",
        source_id="source_blank",
        source_type="voice_transcript",
        text=" \n\t ",
        user_name="D",
        persist_route_outcomes=False,
        llm=fake_llm,
    )

    assert items == []
    assert fake_llm.calls == []


@pytest.mark.parametrize(
    ("llm", "stage"),
    [
        (FailingLLM(), "invoke"),
        (FakeLLM("not-json"), "parse"),
    ],
)
def test_l1_archive_extractor_strict_mode_distinguishes_failures_from_valid_empty(llm, stage):
    kwargs = {
        "uid": "user_1",
        "source_id": "source_1",
        "source_type": "voice_transcript",
        "text": "This source is long enough to invoke the memory extractor.",
        "user_name": None,
        "persist_route_outcomes": False,
        "llm": llm,
    }

    with pytest.raises(WorkingObservationExtractionError) as exc_info:
        extract_l1_memory_archive_items_from_text(**kwargs, strict=True)

    assert exc_info.value.stage == stage
    assert extract_l1_memory_archive_items_from_text(**kwargs) == []


def test_l1_archive_extractor_strict_mode_accepts_valid_empty_batch():
    items = extract_l1_memory_archive_items_from_text(
        uid="user_1",
        source_id="source_1",
        source_type="voice_transcript",
        text="This source is long enough to invoke the memory extractor.",
        user_name=None,
        persist_route_outcomes=False,
        llm=FakeLLM('{"items": []}'),
        strict=True,
    )

    assert items == []


def test_l1_archive_extractor_accepts_short_security_relevant_sources():
    fake_llm = FakeLLM("""
        {
          "items": [
            {
              "text": "API key visible: sk-abc123",
              "class": "sensitive",
              "evidence_quotes": ["sk-abc123"],
              "risk_flags": ["credential"]
            }
          ]
        }
        """)

    items = extract_l1_memory_archive_items_from_text(
        uid="user_1",
        source_id="source_1",
        source_type="screenshot_ocr",
        text="sk-abc123",
        user_name=None,
        persist_route_outcomes=False,
        llm=fake_llm,
    )

    assert len(items) == 1
    assert items[0].archive_class.value == "sensitive"
    assert len(fake_llm.calls) == 1  # should have called LLM even for short security-relevant text


def test_l1_archive_extractor_deterministically_bounds_dense_provider_output():
    provider_items = [
        {
            "text": f"Distinct observation {index}",
            "class": "general",
            "evidence_quotes": [f"exact source quote {index}"],
            "confidence": "high",
        }
        for index in range(60)
    ]
    fake_llm = FakeLLM(json.dumps({"items": provider_items}))
    kwargs = {
        "uid": "user_dense",
        "source_id": "source_dense",
        "source_type": "voice_transcript",
        "text": "A dense source with enough durable details to exercise bounded extraction.",
        "user_name": "David",
        "persist_route_outcomes": False,
        "llm": fake_llm,
        "strict": True,
    }

    first = extract_l1_memory_archive_items_from_text(**kwargs)
    second = extract_l1_memory_archive_items_from_text(**kwargs)

    assert len(first) == MAX_WORKING_OBSERVATION_ITEMS
    assert [item.text for item in first] == [
        f"Distinct observation {index}" for index in range(MAX_WORKING_OBSERVATION_ITEMS)
    ]
    assert [item.archive_id for item in second] == [item.archive_id for item in first]
    assert f"at most {MAX_WORKING_OBSERVATION_ITEMS} distinct items" in fake_llm.calls[0][0][1].lower()


def test_l1_archive_extractor_deduplicates_within_subject_without_collapsing_other_speakers():
    fake_llm = FakeLLM("""
        {
          "items": [
            {
              "text": "Prefers tea",
              "class": "general",
              "evidence_quotes": ["Alice prefers tea"],
              "speaker_label": "speaker_0",
              "about": "Alice"
            },
            {
              "text": "  PREFERS   TEA  ",
              "class": "general",
              "evidence_quotes": ["Alice prefers tea"],
              "speaker_label": "SPEAKER_0",
              "about": "alice"
            },
            {
              "text": "Prefers tea",
              "class": "general",
              "evidence_quotes": ["Bob prefers tea"],
              "speaker_label": "speaker_1",
              "about": "Bob"
            }
          ]
        }
        """)

    items = extract_l1_memory_archive_items_from_text(
        uid="user_subjects",
        source_id="source_subjects",
        source_type="voice_transcript",
        text="Alice prefers tea. Bob prefers tea.",
        user_name="D",
        persist_route_outcomes=False,
        llm=fake_llm,
    )

    assert [(item.about, item.speaker_label) for item in items] == [
        ("Alice", "speaker_0"),
        ("Bob", "speaker_1"),
    ]
    assert len({item.archive_id for item in items}) == 2


def test_l1_prompt_omits_belief_instructions_when_flag_off(monkeypatch):
    monkeypatch.delenv("MEMORY_BELIEF_MODEL_ENABLED", raising=False)
    fake_llm = FakeLLM('{"items": []}')
    extract_l1_memory_archive_items_from_text(
        uid="user_belief_off",
        source_id="source_belief_off",
        source_type="voice_transcript",
        text="User prefers dark mode and asked Omi to remember it.",
        persist_route_outcomes=False,
        llm=fake_llm,
    )
    prompt = fake_llm.calls[0][0][1]
    assert "belief_class" not in prompt
    assert "half_life_days" not in prompt
    assert "subject_scope" not in prompt


def test_l1_prompt_includes_belief_instructions_when_flag_on(monkeypatch):
    monkeypatch.setenv("MEMORY_BELIEF_MODEL_ENABLED", "true")
    fake_llm = FakeLLM('{"items": []}')
    extract_l1_memory_archive_items_from_text(
        uid="user_belief_on",
        source_id="source_belief_on",
        source_type="voice_transcript",
        text="User prefers dark mode and asked Omi to remember it.",
        persist_route_outcomes=False,
        llm=fake_llm,
    )
    prompt = fake_llm.calls[0][0][1]
    assert "belief_class" in prompt
    assert "half_life_days" in prompt
    assert "subject_scope" in prompt
    assert "media_screen" in prompt
