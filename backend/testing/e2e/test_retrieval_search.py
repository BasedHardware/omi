"""
Scenario: Retrieval/search critical path coverage.

These tests exercise real public retrieval/search APIs while replacing the
Pinecone/OpenAI boundary with a deterministic in-memory vector/search fake.
The fake is intentionally installed at the database.vector_db client seam:
routes, auth, Firestore persistence, vector upsert/delete calls, and result
hydration run through production code.
"""

from datetime import datetime, timedelta, timezone

from fakes.firestore import seed_conversation
from fakes.vector_search import install_vector_search_fakes


def _install_fakes(monkeypatch):
    # Import after the client fixture has patched Firestore/Redis/Storage and
    # imported the real app. Importing database.* at module collection time would
    # instantiate real Google clients before the harness boundary is installed.
    import database.vector_db as vector_db

    fake_index, fake_embeddings = install_vector_search_fakes(monkeypatch, vector_db)
    return vector_db, fake_index, fake_embeddings


def test_memory_search_reindexes_updates_and_delete_removes_result(client, auth_headers, fake_firestore, monkeypatch):
    vector_db, fake_index, fake_embeddings = _install_fakes(monkeypatch)

    from database.memory_vector_metadata import canonical_memory_provider_id
    from utils.memory.canonical_required_processing import (
        ProcessedRequiredMemory,
        process_required_memory_item,
    )
    import utils.memory.short_term_promotion as promotion
    from database.memory_outbox_worker import CanonicalMemoryOutboxSideEffects

    real_side_effects = promotion._canonical_outbox_side_effects

    def e2e_side_effects(*, db_client):
        effects = real_side_effects(db_client=db_client)
        return CanonicalMemoryOutboxSideEffects(
            projection_upsert=lambda _item, _generation: True,
            projection_delete=lambda _uid, _memory_id, _generation: True,
            vector_upsert=effects.vector_upsert,
            vector_delete=effects.vector_delete,
        )

    monkeypatch.setattr(promotion, "_canonical_outbox_side_effects", e2e_side_effects)

    def process_and_drain(memory_id: str, run_id: str, *, process: bool = True) -> None:
        if process:
            processed = process_required_memory_item(
                "123",
                memory_id,
                db_client=fake_firestore,
                processor=lambda item: ProcessedRequiredMemory(content=item.content),
                now=datetime.now(timezone.utc),
            )
            assert processed.processed is True
        result = promotion._drain_canonical_outbox(
            "123",
            db_client=fake_firestore,
            run_id=run_id,
            now=datetime.now(timezone.utc) + timedelta(days=1),
        )
        assert result["errors"] == []
        assert result["retryable_failure_count"] == 0

    create = client.post(
        "/v3/memories",
        json={
            "content": "David prefers canary deployments for backend rollouts",
            "category": "system",
            "visibility": "public",
        },
        headers=auth_headers,
    )
    assert create.status_code == 200, create.text
    memory_id = create.json()["id"]
    process_and_drain(memory_id, "e2e-retrieval-create")

    search = client.post(
        "/v1/tools/memories/search",
        json={"query": "canary deployment preference", "limit": 5},
        headers=auth_headers,
    )
    assert search.status_code == 200, search.text
    assert "canary deployments" in search.json()["result_text"]

    assert (
        fake_embeddings.text_for_id(canonical_memory_provider_id("123", memory_id))
        == "David prefers canary deployments for backend rollouts"
    )

    update = client.patch(
        f"/v3/memories/{memory_id}",
        params={"value": "David now prefers blue green releases for backend rollouts"},
        headers=auth_headers,
    )
    assert update.status_code == 200, update.text
    process_and_drain(memory_id, "e2e-retrieval-update")

    old_search = client.post(
        "/v1/tools/memories/search",
        json={"query": "canary deployment preference", "limit": 5},
        headers=auth_headers,
    )
    assert old_search.status_code == 200, old_search.text
    assert "No memories found" in old_search.json()["result_text"]

    new_search = client.post(
        "/v1/tools/memories/search",
        json={"query": "blue green backend releases", "limit": 5},
        headers=auth_headers,
    )
    assert new_search.status_code == 200, new_search.text
    assert "blue green releases" in new_search.json()["result_text"]

    delete = client.delete(f"/v3/memories/{memory_id}", headers=auth_headers)
    assert delete.status_code == 200, delete.text
    process_and_drain(memory_id, "e2e-retrieval-delete", process=False)

    after_delete = client.post(
        "/v1/tools/memories/search",
        json={"query": "blue green backend releases", "limit": 5},
        headers=auth_headers,
    )
    assert after_delete.status_code == 200, after_delete.text
    assert "No memories found" in after_delete.json()["result_text"]
    assert fake_index.count(namespace=vector_db.MEMORIES_NAMESPACE) == 0


def test_action_item_search_tracks_create_update_and_delete(client, auth_headers, monkeypatch):
    vector_db, fake_index, _ = _install_fakes(monkeypatch)

    create = client.post(
        "/v1/action-items",
        json={"description": "Renew passport before Lisbon travel"},
        headers=auth_headers,
    )
    assert create.status_code == 200, create.text
    action_item_id = create.json()["id"]

    search = client.get(
        "/v1/action-items/search",
        params={"query": "passport travel", "limit": 5},
        headers=auth_headers,
    )
    assert search.status_code == 200, search.text
    assert [item["id"] for item in search.json()["action_items"]] == [action_item_id]

    update = client.patch(
        f"/v1/action-items/{action_item_id}",
        json={"description": "Book veterinarian appointment for Momo"},
        headers=auth_headers,
    )
    assert update.status_code == 200, update.text

    stale_search = client.get(
        "/v1/action-items/search",
        params={"query": "passport travel", "limit": 5},
        headers=auth_headers,
    )
    assert stale_search.status_code == 200, stale_search.text
    assert stale_search.json()["action_items"] == []

    fresh_search = client.get(
        "/v1/action-items/search",
        params={"query": "veterinarian Momo", "limit": 5},
        headers=auth_headers,
    )
    assert fresh_search.status_code == 200, fresh_search.text
    assert [item["id"] for item in fresh_search.json()["action_items"]] == [action_item_id]

    delete = client.delete(f"/v1/action-items/{action_item_id}", headers=auth_headers)
    assert delete.status_code in (200, 204), delete.text

    after_delete = client.get(
        "/v1/action-items/search",
        params={"query": "veterinarian Momo", "limit": 5},
        headers=auth_headers,
    )
    assert after_delete.status_code == 200, after_delete.text
    assert after_delete.json()["action_items"] == []
    assert fake_index.count(namespace=vector_db.ACTION_ITEMS_NAMESPACE) == 0


def test_conversation_and_transcript_chunk_search_return_persisted_conversation_text(
    client, auth_headers, sample_conversation_data, monkeypatch
):
    vector_db, fake_index, _ = _install_fakes(monkeypatch)
    from utils.conversations.transcript_chunks import build_transcript_chunks

    conversation = dict(
        sample_conversation_data,
        id="conv-search-001",
        structured={
            **sample_conversation_data["structured"],
            "title": "Infrastructure rollout",
            "overview": "Discussed using feature flags for the production rollout.",
        },
        transcript_segments=[
            {
                "id": "seg-search-1",
                "text": "The launch checklist says enable the Zagreb feature flag on Thursday.",
                "speaker": "SPEAKER_00",
                "is_user": True,
                "start": 0.0,
                "end": 3.0,
            }
        ],
    )
    conversation["created_at"] = datetime.fromisoformat(conversation["created_at"].replace("Z", "+00:00"))
    conversation["started_at"] = datetime.fromisoformat(conversation["started_at"].replace("Z", "+00:00"))
    conversation["finished_at"] = datetime.fromisoformat(conversation["finished_at"].replace("Z", "+00:00"))
    seed_conversation("123", conversation)

    vector_db.upsert_vector2(
        "123", conversation["id"], vector_db.embeddings.embed_query(conversation["structured"]["overview"]), {}
    )
    chunks = build_transcript_chunks(conversation["transcript_segments"], conversation["started_at"])
    assert vector_db.upsert_transcript_chunk_vectors("123", conversation["id"], chunks) == 1

    summary_search = client.post(
        "/v1/tools/conversations/search",
        json={"query": "production feature flags", "limit": 5, "include_transcript": False},
        headers=auth_headers,
    )
    assert summary_search.status_code == 200, summary_search.text
    assert "Infrastructure rollout" in summary_search.json()["result_text"]

    chunk_search = client.post(
        "/v1/tools/conversations/search-chunks",
        json={"query": "Zagreb feature flag Thursday", "limit": 5},
        headers=auth_headers,
    )
    assert chunk_search.status_code == 200, chunk_search.text
    assert "Zagreb feature flag" in chunk_search.json()["result_text"]

    vector_db.delete_transcript_chunk_vectors("123", conversation["id"])
    no_chunk_search = client.post(
        "/v1/tools/conversations/search-chunks",
        json={"query": "Zagreb feature flag Thursday", "limit": 5},
        headers=auth_headers,
    )
    assert no_chunk_search.status_code == 200, no_chunk_search.text
    assert "No transcript excerpts found" in no_chunk_search.json()["result_text"]
    assert fake_index.count(namespace=vector_db.TRANSCRIPT_CHUNKS_NAMESPACE) == 0
