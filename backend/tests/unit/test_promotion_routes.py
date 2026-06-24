import json

from langchain_core.messages import AIMessage
from pydantic import ValidationError
import pytest

from models.memory_contracts import L2MemoryRoute
from utils.llm.promotion_routes import classify_l2_memory_route


class FakeLLM:
    def __init__(self, payload):
        self.payload = payload
        self.messages = None

    def invoke(self, messages):
        self.messages = messages
        return AIMessage(content=json.dumps(self.payload))


def _packet():
    return {
        "packet_id": "pkt_sf_team",
        "evidence_ids": ["ev_1"],
        "source_refs": [{"quote": "So I'm going to San Francisco to find a cofounder and a team."}],
        "observations": [
            {
                "content": "User plans to go to San Francisco to find a cofounder and a team.",
                "subject_scope": "primary_user",
                "source_refs": [{"quote": "So I'm going to San Francisco to find a cofounder and a team."}],
            }
        ],
        "retrieved_memory_context": [],
    }


def test_l2_memory_route_accepts_durable_with_quote():
    route = L2MemoryRoute(
        route="durable",
        memory_text="User plans to go to San Francisco to find a cofounder and a team.",
        evidence_quotes=["So I'm going to San Francisco to find a cofounder and a team."],
        confidence="high",
        reason="Direct primary-user plan.",
    )

    assert route.route == "durable"
    assert route.drop_reason is None


def test_l2_memory_route_rejects_footgun_combinations():
    with pytest.raises(ValidationError):
        L2MemoryRoute(route="durable", memory_text="Missing quote", evidence_quotes=[], reason="bad")
    with pytest.raises(ValidationError):
        L2MemoryRoute(route="discard", reason="bad")
    with pytest.raises(ValidationError):
        L2MemoryRoute(route="hidden", drop_reason="ephemeral_chatter", reason="bad")


def test_route_classifier_prompt_hides_patch_lifecycle_details_from_model():
    fake = FakeLLM(
        {
            "route": {
                "route": "durable",
                "memory_text": "User plans to go to San Francisco to find a cofounder and a team.",
                "evidence_quotes": ["So I'm going to San Francisco to find a cofounder and a team."],
                "confidence": "high",
                "reason": "Direct primary-user plan.",
            }
        }
    )

    result = classify_l2_memory_route(
        packet=_packet(), custom_search_artifact={"search_results": []}, observed_head_commit_id="head_1", llm=fake
    )

    prompt_text = "\n".join(str(message.content) for message in fake.messages)
    assert result is not None
    assert result.route == "durable"
    assert "l2_memory_route.v1" in prompt_text
    assert "Do NOT output patch operations" in prompt_text
    assert "result_status" not in json.dumps(result.model_dump())
    assert "patch_id" not in json.dumps(result.model_dump())


def test_route_classifier_demotes_quote_wrapper_to_review():
    fake = FakeLLM(
        {
            "route": {
                "route": "durable",
                "memory_text": "User said \"I want automatic memory capture.\"",
                "evidence_quotes": ["I want automatic memory capture."],
                "confidence": "high",
                "reason": "Direct quote.",
            }
        }
    )

    result = classify_l2_memory_route(
        packet=_packet(), custom_search_artifact={"search_results": []}, observed_head_commit_id="head_1", llm=fake
    )

    assert result is not None
    assert result.route == "review"
    assert result.confidence == "low"
