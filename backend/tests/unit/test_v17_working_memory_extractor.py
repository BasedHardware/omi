from langchain_core.messages import AIMessage

from models.v17_memory_contracts import LifecycleState
from utils.llm.working_memory import extract_working_memory_observations_from_text


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
