from utils.memory.projections import rebuild_memory_memory_projections


def test_memory_projection_rebuilds_vector_and_graph_from_active_durable_facts_only():
    facts = {
        "mem_active": {
            "id": "mem_active",
            "content": "User prefers automatic memory capture.",
            "status": "active",
            "predicate": "prefers",
            "arguments": {"object": "automatic memory capture"},
            "subject_entity_id": "user",
            "evidence_set": [{"evidence_id": "ev_1"}],
        },
        "mem_superseded": {
            "id": "mem_superseded",
            "content": "User uses manual notes.",
            "status": "superseded",
            "predicate": "uses",
            "arguments": {"object": "manual notes"},
            "subject_entity_id": "user",
        },
        "mem_review": {
            "id": "mem_review",
            "content": "Maybe user likes voice notes.",
            "status": "review",
            "predicate": "likes",
            "arguments": {"object": "voice notes"},
            "subject_entity_id": "user",
        },
    }

    projections = rebuild_memory_memory_projections(facts)

    assert [row["memory_id"] for row in projections["vector_index"]] == ["mem_active"]
    assert projections["graph"]["nodes"]["user"]["entity_id"] == "user"
    assert projections["graph"]["edges"][0]["predicate"] == "prefers"
    assert projections["review_queue"][0]["memory_id"] == "mem_review"
    assert "mem_superseded" not in [row["memory_id"] for row in projections["vector_index"]]


def test_memory_projection_is_deterministic_and_does_not_mutate_facts():
    facts = {
        "b": {
            "id": "b",
            "content": "B",
            "status": "active",
            "predicate": "likes",
            "arguments": {},
            "subject_entity_id": "user",
        },
        "a": {
            "id": "a",
            "content": "A",
            "status": "active",
            "predicate": "likes",
            "arguments": {},
            "subject_entity_id": "user",
        },
    }
    before = {key: dict(value) for key, value in facts.items()}

    first = rebuild_memory_memory_projections(facts)
    second = rebuild_memory_memory_projections(facts)

    assert first == second
    assert [row["memory_id"] for row in first["vector_index"]] == ["a", "b"]
    assert facts == before
