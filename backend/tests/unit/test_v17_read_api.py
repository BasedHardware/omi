from models.v17_memory_contracts import LifecycleState, WorkingMemoryObservation
from utils.memory.v17_read_api import query_durable_memory, query_memory_context, query_working_memory


def _working(content, status="working"):
    return WorkingMemoryObservation(
        observation_id=f"obs_{status}_{content[:4]}",
        content=content,
        status=status,
        confidence="medium",
        evidence_ids=["ev_1"],
        source_refs=[{"quote": "I want automatic memory capture.", "source_id": "src_1"}],
    )


def _durable(memory_id, content, status="active", superseded_by=None):
    return {
        "id": memory_id,
        "content": content,
        "status": status,
        "confidence": "high",
        "created_at": "2026-06-17T00:00:00Z",
        "source": "ledger",
        "evidence_set": [{"evidence_id": "ev_2", "quote": "Automatic memory is better.", "source_id": "src_2"}],
        "superseded_by": superseded_by,
    }


def test_query_working_memory_returns_labeled_non_stable_records():
    results = query_working_memory("automatic", [_working("User wants automatic memory capture.")])

    assert results[0]["memory_layer"] == "working"
    assert results[0]["lifecycle_status"] == "working"
    assert results[0]["agent_use"] == "working_context_not_stable_profile"
    assert results[0]["evidence"][0]["quote"] == "I want automatic memory capture."


def test_query_durable_memory_excludes_superseded_current_truth_by_default():
    records = [
        _durable("mem_old", "User uses manual notes.", status="superseded", superseded_by="mem_new"),
        _durable("mem_new", "User prefers automatic memory capture."),
    ]

    results = query_durable_memory("memory", records)

    assert [result["memory_id"] for result in results] == ["mem_new"]
    assert results[0]["agent_use"] == "stable_profile_fact"


def test_query_memory_context_mixes_l1_and_l2_but_preserves_labels():
    results = query_memory_context(
        "automatic",
        working_records=[
            _working("User may want automatic capture."),
            _working("Automatic capture needs review.", status="review"),
        ],
        durable_records=[_durable("mem_active", "User prefers automatic memory capture.")],
    )

    assert {result["memory_layer"] for result in results} == {"working", "durable"}
    uses = {result["agent_use"] for result in results}
    assert "stable_profile_fact" in uses
    assert "working_context_not_stable_profile" in uses
    assert "review_only_not_profile_fact" in uses
    assert all("lifecycle_status" in result for result in results)
