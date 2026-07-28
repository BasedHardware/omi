import os

os.environ.setdefault("FIRESTORE_EMULATOR_HOST", "localhost:8787")
os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "test")

from langchain_core.messages import AIMessage

from models.memory_contracts import L1MemoryArchiveItem
from utils.llm import working_observations
from utils.llm.working_observations import extract_l1_memory_archive_items_from_text
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
