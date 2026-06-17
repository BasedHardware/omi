import json

from langchain_core.messages import AIMessage

from models.v17_memory_contracts import DurablePatchDecision, LifecycleState
from utils.llm.durable_memory_patches import synthesize_durable_memory_patches


class FakeLLM:
    def __init__(self, payload):
        self.payload = payload
        self.messages = None

    def invoke(self, messages):
        self.messages = messages
        return AIMessage(content=json.dumps(self.payload))


def _packet():
    return {
        "packet_id": "pkt_auto_memory",
        "run_id": "v17_test_run",
        "evidence_ids": ["ev_1"],
        "source_refs": [{"evidence_id": "ev_1", "quote": "I want automatic memory capture."}],
        "observations": [
            {
                "content": "User wants automatic memory capture.",
                "evidence_ids": ["ev_1"],
                "source_refs": [{"evidence_id": "ev_1", "quote": "I want automatic memory capture."}],
            }
        ],
        "retrieved_memory_context": [
            {"memory_id": "mem_auto", "content": "User prefers automated memory systems.", "status": "active"}
        ],
    }


def _patch(decision, **overrides):
    payload = {
        "patch_id": "",
        "packet_id": "pkt_auto_memory",
        "run_id": "v17_test_run",
        "observed_head_commit_id": "head_1",
        "idempotency_key": "",
        "decision": decision,
        "result_status": "active" if decision in {"add", "add_evidence", "update", "merge", "keep_both"} else "review",
        "evidence_ids": ["ev_1"],
        "evidence_refs": [{"evidence_id": "ev_1", "quote": "I want automatic memory capture."}],
        "memory_text": "User prefers automatic memory capture.",
        "predicate": "prefers",
        "arguments": {"object": "automatic memory capture"},
        "rationale": "Supported by direct quote.",
    }
    payload.update(overrides)
    return payload


def test_l2_patch_synthesizer_covers_all_patch_decisions_with_mocked_llm():
    decisions = [decision.value for decision in DurablePatchDecision]
    patches = []
    for decision in decisions:
        overrides = {}
        if decision in {"merge", "update", "add_evidence", "skip_duplicate"}:
            overrides["target_memory_id"] = "mem_auto"
        if decision in {"context_only", "reject", "review", "skip_duplicate"}:
            if decision == "review":
                overrides["result_status"] = "review"
            elif decision == "reject":
                overrides["result_status"] = "rejected"
            else:
                overrides["result_status"] = decision.replace("skip_duplicate", "active")
            overrides["memory_text"] = None
        patches.append(_patch(decision, **overrides))

    result = synthesize_durable_memory_patches(
        packet=_packet(),
        custom_search_artifact={"search_results": []},
        observed_head_commit_id="head_1",
        llm=FakeLLM({"patches": patches}),
    )

    assert [patch.decision.value for patch in result] == decisions
    assert all(patch.patch_id for patch in result)
    assert all(patch.idempotency_key for patch in result)


def test_l2_patch_synthesizer_requires_target_memory_ids_for_existing_memory_decisions():
    result = synthesize_durable_memory_patches(
        packet=_packet(),
        custom_search_artifact={"search_results": []},
        observed_head_commit_id="head_1",
        llm=FakeLLM({"patches": [_patch("merge", target_memory_id=None)]}),
    )

    assert result == []


def test_l2_patch_synthesizer_rejects_quote_wrapper_card():
    result = synthesize_durable_memory_patches(
        packet=_packet(),
        custom_search_artifact={"search_results": []},
        observed_head_commit_id="head_1",
        llm=FakeLLM({"patches": [_patch("add", memory_text='User said "I want automatic memory capture."')]}),
    )

    assert result == []


def test_l2_patch_synthesizer_prompt_includes_existing_memory_context_for_merge_update_skip():
    fake = FakeLLM({"patches": [_patch("add_evidence", target_memory_id="mem_auto")]})

    result = synthesize_durable_memory_patches(
        packet=_packet(),
        custom_search_artifact={"search_results": []},
        observed_head_commit_id="head_1",
        llm=fake,
    )

    prompt_text = "\n".join(str(message.content) for message in fake.messages)
    assert result[0].target_memory_id == "mem_auto"
    assert "mem_auto" in prompt_text
    assert "User prefers automated memory systems" in prompt_text
