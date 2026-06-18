from langchain_core.messages import AIMessage

from models.v17_memory_contracts import L1MemoryArchiveItem
from utils.llm.working_memory import extract_l1_memory_archive_items_from_text


class FakeLLM:
    def __init__(self, content):
        self.content = content
        self.calls = []

    def invoke(self, messages):
        self.calls.append(messages)
        return AIMessage(content=self.content)


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
        user_name=None,
        llm=fake_llm,
    )

    assert items[0].archive_class.value == "sensitive"
    assert items[0].normal_search_allowed is False
    assert items[0].allowed_use == "restricted_archive_only"


def test_l1_archive_extractor_skips_tiny_sources_without_llm_call():
    fake_llm = FakeLLM('{"items": []}')

    items = extract_l1_memory_archive_items_from_text(
        uid="user_1",
        source_id="source_1",
        source_type="chat_exchange",
        text="ok",
        user_name=None,
        llm=fake_llm,
    )

    assert items == []
    assert fake_llm.calls == []


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
        llm=fake_llm,
    )

    assert len(items) == 1
    assert items[0].archive_class.value == "sensitive"
    assert len(fake_llm.calls) == 1  # should have called LLM even for short security-relevant text
