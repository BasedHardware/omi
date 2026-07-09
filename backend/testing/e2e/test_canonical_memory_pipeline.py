"""Hermetic canonical memory pipeline E2E and surface default-access matrix."""

from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import pytest

from config.memory_rollout import PASSED, MemoryRolloutMode, MemoryRolloutStageGate
from fakes.firestore import seed_conversation
from fakes.vector_search import install_vector_search_fakes
from models.memories import MemoryCategory
from models.memory_apply import MemoryControlState
from models.product_memory import (
    MemoryAccessPolicy,
    MemoryConsumer,
    MemoryItemStatus,
    MemoryTier,
    ProcessingState,
)
from tests.unit.canonical_cohort_test_helpers import set_canonical_cohort
from tests.unit.fixtures.memory_adapter_fakes import (
    FirestoreFake,
    enabled_rollout_doc,
    memory_item,
    stored_item,
)
from tests.unit.test_ws_i_write_convergence import (
    _sample_memory_payload,
    extraction_memory_id,
)
from utils.memory.canonical_consolidation import ConsolidationAgentBatch
from utils.memory.canonical_memory_adapter import (
    delete_canonical_memory,
    neutral_vector_id_for_memory,
    write_canonical_extraction_memory,
)
from utils.memory.chat_memory_adapter import (
    list_default_chat_memories_decision_text,
    search_memory_default_chat_memories_text,
)
from utils.memory.default_read_rollout import GLOBAL_READ_GATE_PATH, MemoryReadDecision
from utils.memory.developer_memory_adapter import search_memory_default_developer_memories
from utils.memory.memory_service import MemoryService
from utils.memory.product_memory_read_service import fetch_default_product_memory_search
from utils.memory.short_term_promotion import run_canonical_short_term_maintenance
from utils.retrieval.tool_services import memories as tool_memories_service

NOW = datetime(2026, 6, 24, 12, 0, tzinfo=timezone.utc)
PIPELINE_UID = "123"
CONV_ID = "canonical-pipeline-conv-001"
PIPELINE_CONTENT = "User prefers hermetic canonical memory pipeline coverage."


def _trusted_generation_patch(monkeypatch) -> None:
    trusted = SimpleNamespace(
        account_generation=3,
        head_commit_id="head0",
        read_error_reason=None,
    )
    for target in (
        "utils.memory.canonical_memory_adapter.read_memory_v3_trusted_account_generation",
        "utils.memory.v3_account_generation_source.read_memory_v3_trusted_account_generation",
    ):
        monkeypatch.setattr(target, lambda **_: trusted, raising=False)


def _promotion_side_effect_patches(monkeypatch) -> None:
    from utils.memory.canonical_kg_promotion import CanonicalKgPromotionResult

    monkeypatch.setattr(
        "utils.memory.short_term_promotion.extract_kg_for_promoted_memory",
        lambda *args, **kwargs: CanonicalKgPromotionResult(attempted=False, success=True),
    )
    monkeypatch.setattr(
        "utils.memory.canonical_consolidation.query_memory_vector_candidates",
        lambda *args, **kwargs: SimpleNamespace(hits=[], rejected_count=0),
        raising=False,
    )


def _seed_apply_control(db, uid: str, *, account_generation: int = 3) -> None:
    control = MemoryControlState(
        uid=uid,
        head_commit_id="head0",
        account_generation=account_generation,
        source_generation=1,
    ).model_dump(mode="json")
    (db.collection("users").document(uid).collection("memory_state").document("apply_control").set(control))


def _seed_rollout_readiness(db, uid: str, *, grant_consumer: str) -> None:
    db.collection("memory_control").document("global_read_gate").set(
        {"memory_reads_enabled": True, "kill_switch_active": False}
    )
    db.collection("memory_control").document("write_convergence_gate").set(
        {
            "durable_outbox_enabled": True,
            "dual_write_projection_ready": True,
            "delete_convergence_ready": True,
            "idempotency_contract_ready": True,
        }
    )
    rollout = enabled_rollout_doc(uid, grant_consumer=grant_consumer)
    rollout["mode"] = MemoryRolloutMode.read.value
    rollout["stage_gates"] = {
        MemoryRolloutStageGate.shadow.value: PASSED,
        MemoryRolloutStageGate.write.value: PASSED,
        MemoryRolloutStageGate.read.value: PASSED,
    }
    db.collection("users").document(uid).collection("memory_control").document("state").set(rollout)


def _seed_memory_item_doc(db, item: MemoryItem) -> None:
    (
        db.collection("users")
        .document(item.uid)
        .collection("memory_items")
        .document(item.memory_id)
        .set(stored_item(item))
    )


def _read_memory_item(db, uid: str, memory_id: str) -> dict:
    snapshot = db.collection("users").document(uid).collection("memory_items").document(memory_id).get()
    assert snapshot.exists, f"missing memory item {memory_id}"
    return snapshot.to_dict()


def _list_outbox_records(db, uid: str) -> list[dict]:
    records = []
    for snapshot in db.collection("users").document(uid).collection("memory_outbox").stream():
        if snapshot.exists:
            records.append(snapshot.to_dict())
    return records


def _scripted_consolidation_llm(_prompt: str) -> str:
    return json.dumps(ConsolidationAgentBatch(decisions=[], reasoning="no_changes").model_dump(mode="json"))


def _enroll_canonical_pipeline(monkeypatch, uid: str = PIPELINE_UID) -> None:
    set_canonical_cohort(monkeypatch, uid)
    monkeypatch.setenv("MEMORY_CANONICAL_CONSOLIDATION_BATCH_THRESHOLD", "1")
    monkeypatch.setattr("utils.memory.short_term_promotion.promotion_batch_threshold", lambda: 1)
    monkeypatch.setattr("utils.memory.canonical_consolidation.consolidation_batch_threshold", lambda: 1)
    monkeypatch.setattr("utils.other.endpoints._enforce_rate_limit", lambda *args, **kwargs: None)
    _trusted_generation_patch(monkeypatch)
    _promotion_side_effect_patches(monkeypatch)


def _write_short_term_via_conversation_ingress(client, auth_headers, monkeypatch, *, db) -> str:
    conv_data = {
        "id": CONV_ID,
        "created_at": "2025-01-15T12:00:00Z",
        "started_at": "2025-01-15T12:00:00Z",
        "finished_at": "2025-01-15T12:05:00Z",
        "source": "omi",
        "language": "en",
        "structured": {
            "title": "",
            "overview": "",
            "emoji": "🧠",
            "category": "other",
            "action_items": [],
            "events": [],
        },
        "transcript_segments": [
            {
                "id": "seg-1",
                "text": PIPELINE_CONTENT,
                "speaker": "SPEAKER_00",
                "is_user": True,
                "start": 0.0,
                "end": 2.0,
            }
        ],
        "discarded": False,
        "status": "completed",
        "is_locked": False,
        "data_protection_level": "standard",
    }
    seed_conversation(PIPELINE_UID, conv_data)
    _seed_apply_control(db, PIPELINE_UID)

    def fake_process_conversation(uid, language_code, conversation, **kwargs):
        payload = _sample_memory_payload(
            uid=uid,
            conversation_id=conversation.id,
            content=PIPELINE_CONTENT,
        )
        payload["category"] = MemoryCategory.system.value
        memory_id = write_canonical_extraction_memory(uid, payload, db_client=db)
        import database.conversations as conversations_db

        structured = conversation.structured.model_dump() if hasattr(conversation.structured, "model_dump") else {}
        structured.update(
            {
                "title": "Canonical pipeline capture",
                "overview": PIPELINE_CONTENT,
                "category": "work",
            }
        )
        conversations_db.update_conversation(
            uid,
            conversation.id,
            {"structured": structured, "status": "completed"},
        )
        refreshed = conversations_db.get_conversation(uid, conversation.id)
        from utils.conversations.factory import deserialize_conversation

        assert memory_id == payload["id"]
        return deserialize_conversation(refreshed)

    import routers.conversations as conversations_router

    monkeypatch.setattr(conversations_router, "process_conversation", fake_process_conversation)

    resp = client.post(f"/v1/conversations/{CONV_ID}/reprocess", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    return extraction_memory_id(uid=PIPELINE_UID, source_id=CONV_ID, content=PIPELINE_CONTENT)


@contextmanager
def _override_memory_runtime(client, runtime):
    import routers.memories as memories_router

    client.app.dependency_overrides[memories_router.get_v3_get_runtime] = lambda: runtime
    try:
        yield
    finally:
        client.app.dependency_overrides.pop(memories_router.get_v3_get_runtime, None)


def _runtime(*, enabled: bool, source_decision: str, service=None):
    import routers.memories as memories_router

    return memories_router.V3GetRuntime(
        enabled=enabled,
        source_decision=source_decision,
        service=service,
        adapters=object(),
    )


class TestCanonicalMemoryPipelineE2E:
    def test_capture_consolidate_promote_read_archive_excluded_vectors_and_delete_outbox(
        self, client, auth_headers, fake_firestore, monkeypatch
    ):
        import database.vector_db as vector_db

        _enroll_canonical_pipeline(monkeypatch)
        fake_index, _embeddings = install_vector_search_fakes(monkeypatch, vector_db)
        db = fake_firestore
        _seed_rollout_readiness(db, PIPELINE_UID, grant_consumer="omi_chat")

        memory_id = _write_short_term_via_conversation_ingress(client, auth_headers, monkeypatch, db=db)
        short_term = _read_memory_item(db, PIPELINE_UID, memory_id)
        assert short_term["tier"] == MemoryTier.short_term.value
        assert short_term["status"] == MemoryItemStatus.active.value

        maintenance = run_canonical_short_term_maintenance(
            PIPELINE_UID,
            db_client=db,
            now=NOW,
            run_id="e2e-canonical-pipeline",
            llm_invoke=_scripted_consolidation_llm,
        )
        assert maintenance.skipped_reason is None
        assert maintenance.consolidation.skipped_reason is None
        assert maintenance.promotion.promoted_count == 1
        assert maintenance.promotion.vector_sync_failures == 0

        promoted = _read_memory_item(db, PIPELINE_UID, memory_id)
        assert promoted["memory_id"] == memory_id
        assert promoted["tier"] == MemoryTier.long_term.value

        vectors = _vector_store(fake_index)
        assert memory_id in vectors, "promotion should upsert canonical vector using memory_id"
        assert vectors[memory_id]["metadata"]["memory_id"] == memory_id
        assert vectors[memory_id]["metadata"]["memory_layer"] == MemoryTier.long_term.value

        from utils.memory.product_memory_read_service import fetch_authoritative_product_memory_items
        from database.vector_db import upsert_canonical_memory_vector
        from models.product_memory import MemoryItem

        promoted_item = MemoryItem(**promoted)
        projection_commit_id = promoted_item.ledger_commit_id or "head0"
        assert upsert_canonical_memory_vector(promoted_item, projection_commit_id=projection_commit_id) is not None
        authoritative_items = {
            item.memory_id: item for item in fetch_authoritative_product_memory_items(uid=PIPELINE_UID, db_client=db)
        }
        assert memory_id in authoritative_items
        assert authoritative_items[memory_id].content == promoted_item.content
        assert vectors[memory_id]["id"] == memory_id

        archive_item = memory_item(
            "archive-hidden",
            uid=PIPELINE_UID,
            tier=MemoryTier.archive,
            now=NOW,
            content="archive should stay hidden",
            quote_text="archive quote",
        )
        visible_item = memory_item(
            "visible-long-term",
            uid=PIPELINE_UID,
            tier=MemoryTier.long_term,
            now=NOW,
            content="visible long term fact",
            quote_text="visible quote",
        )
        _seed_memory_item_doc(db, archive_item)
        _seed_memory_item_doc(db, visible_item)

        service = MemoryService(db_client=db)
        read_ids = {memory.id for memory in service.read(PIPELINE_UID, limit=50)}
        assert memory_id in read_ids
        assert "archive-hidden" not in read_ids
        assert "visible-long-term" in read_ids

        chat_text = search_memory_default_chat_memories_text(
            uid=PIPELINE_UID,
            query="visible",
            limit=10,
            db_client=db,
            now=NOW,
        )
        assert chat_text is not None
        assert "archive-hidden" not in chat_text
        assert "visible long term fact" in chat_text

        product_policy = MemoryAccessPolicy(
            consumer=MemoryConsumer.omi_chat,
            app_has_default_memory_grant=True,
            archive_capability=False,
        )
        product = fetch_default_product_memory_search(
            uid=PIPELINE_UID,
            query="visible",
            db_client=db,
            policy=product_policy,
            now=NOW,
        )
        product_ids = {row["memory_id"] for row in product["items"]}
        assert "archive-hidden" not in product_ids
        assert "visible-long-term" in product_ids

        delete_canonical_memory(PIPELINE_UID, memory_id, db_client=db)
        tombstoned = _read_memory_item(db, PIPELINE_UID, memory_id)
        assert tombstoned["status"] == MemoryItemStatus.tombstoned.value

        outbox_records = _list_outbox_records(db, PIPELINE_UID)
        purge_records = [
            record
            for record in outbox_records
            if record.get("memory_id") == memory_id and record.get("event_type") == "vector_repair_purge"
        ]
        assert purge_records, "delete should enqueue vector repair outbox records"
        assert purge_records[0]["vector_id"] == neutral_vector_id_for_memory(memory_id)
        assert purge_records[0]["reason"] == "canonical_memory_delete"

    def test_dual_stack_projection_failure_fails_closed_without_legacy_bleed(
        self, client, auth_headers, fake_firestore, monkeypatch
    ):
        from fakes.firestore import seed_memory

        _enroll_canonical_pipeline(monkeypatch)
        seed_memory(
            PIPELINE_UID,
            {
                "id": "legacy-must-not-bleed",
                "content": "legacy memory must not leak on canonical projection failure",
                "category": "manual",
                "visibility": "public",
            },
        )

        def failing_memory_service(_params, _adapters):
            from utils.memory.v3_composed_get_service import V3ComposedResponse

            return V3ComposedResponse.error(503, "infrastructure_failure")

        with _override_memory_runtime(
            client,
            _runtime(enabled=True, source_decision="memory_read", service=failing_memory_service),
        ):
            resp = client.get("/v3/memories", headers=auth_headers)

        assert resp.status_code == 503
        assert resp.json() == {"detail": "infrastructure_failure"}
        assert resp.headers["x-omi-memory-read-source"] == "none"
        assert resp.headers["x-omi-memory-read-decision"] == "infrastructure_failure"
        assert "legacy-must-not-bleed" not in resp.text


def _vector_store(fake_index, namespace: str = "ns2") -> dict:
    return fake_index._vectors[namespace]


def _invoke_surface_reader(surface_name, grant_consumer, *, uid, db, rollout, policy, now):
    if surface_name == "chat_text":
        return search_memory_default_chat_memories_text(uid=uid, query="coffee", limit=10, db_client=db, now=now)
    if surface_name == "chat_list":
        return list_default_chat_memories_decision_text(uid=uid, limit=10, offset=0, db_client=db).text
    if surface_name == "developer":
        return search_memory_default_developer_memories(
            uid=uid,
            query="coffee",
            limit=10,
            offset=0,
            db_client=db,
            rollout_decision=rollout,
            now=now,
        ).memories
    if surface_name == "agent_tools":
        return tool_memories_service.get_memories_text(uid=uid, limit=50)
    if surface_name == "mcp":
        return MemoryService(db_client=db).search_mcp(uid, "coffee", limit=10)
    if surface_name == "product_search":
        return fetch_default_product_memory_search(
            uid=uid,
            query="coffee",
            db_client=db,
            policy=policy,
            now=now,
        )["items"]
    raise AssertionError(f"unknown surface {surface_name}")


SURFACE_MATRIX_CASES = [
    pytest.param("chat_text", "omi_chat", id="chat_text"),
    pytest.param("chat_list", "omi_chat", id="chat_list"),
    pytest.param("developer", "developer_api", id="developer"),
    pytest.param("agent_tools", "omi_chat", id="agent_tools"),
    pytest.param("mcp", "mcp", id="mcp"),
    pytest.param("product_search", "omi_chat", id="product_search"),
]


class TestSurfaceDefaultAccessMatrix:
    @pytest.mark.parametrize("surface_name,grant_consumer", SURFACE_MATRIX_CASES)
    def test_surface_excludes_archive_and_respects_grants(
        self, fake_firestore, monkeypatch, surface_name, grant_consumer
    ):
        from utils.memory.default_read_rollout import read_default_read_rollout

        uid = f"uid-surface-{surface_name}"
        set_canonical_cohort(monkeypatch, uid)
        _trusted_generation_patch(monkeypatch)
        monkeypatch.setattr(
            "utils.memory.memory_service.canonical_read_enabled",
            lambda uid, **kwargs: True,
        )
        if surface_name in {"mcp", "agent_tools"}:
            import database.vector_db as vector_db

            install_vector_search_fakes(monkeypatch, vector_db)
        db = fake_firestore
        _seed_apply_control(db, uid)
        _seed_rollout_readiness(db, uid, grant_consumer=grant_consumer)

        fresh_short = memory_item(
            "fresh-short",
            uid=uid,
            now=NOW,
            content="coffee fresh short term",
            quote_text="fresh quote",
            processing_state=ProcessingState.processed,
        )
        long_term = memory_item(
            "long-term",
            uid=uid,
            tier=MemoryTier.long_term,
            now=NOW,
            content="coffee long term",
            quote_text="long quote",
        )
        archive = memory_item(
            "archive-item",
            uid=uid,
            tier=MemoryTier.archive,
            now=NOW,
            content="coffee archive memory",
            quote_text="archive quote",
        )
        for item in (archive, fresh_short, long_term):
            _seed_memory_item_doc(db, item)

        if surface_name == "mcp":
            from database.vector_db import upsert_canonical_memory_vector

            for item in (fresh_short, long_term):
                upsert_canonical_memory_vector(item, projection_commit_id="projection-1")

        rollout = read_default_read_rollout(uid=uid, db_client=db, consumer=grant_consumer)
        assert rollout.read_decision == MemoryReadDecision.USE_MEMORY

        policy = MemoryAccessPolicy(
            consumer=MemoryConsumer(grant_consumer),
            app_has_default_memory_grant=True,
            archive_capability=False,
        )
        result = _invoke_surface_reader(
            surface_name,
            grant_consumer,
            uid=uid,
            db=db,
            rollout=rollout,
            policy=policy,
            now=NOW,
        )

        if surface_name == "product_search":
            ids = [row["memory_id"] for row in result]
            assert "archive-item" not in ids
            assert set(ids) == {"fresh-short", "long-term"}
        elif surface_name == "developer":
            ids = [row["id"] for row in result]
            assert "archive-item" not in ids
            assert set(ids) == {"fresh-short", "long-term"}
        elif surface_name == "mcp":
            ids = {row["id"] for row in result}
            assert "archive-item" not in ids
            assert "long-term" in ids
        elif surface_name == "agent_tools":
            assert "archive-item" not in (result or "")
            assert "coffee archive memory" not in (result or "")
            assert "coffee fresh short term" in (result or "")
        else:
            text = result or ""
            assert "archive-item" not in text
            assert "coffee archive memory" not in text
            assert "coffee fresh short term" in text or "coffee long term" in text

        grantless_rollout = read_default_read_rollout(
            uid=uid,
            db_client=FirestoreFake(
                {
                    GLOBAL_READ_GATE_PATH: {"memory_reads_enabled": True, "kill_switch_active": False},
                    f"users/{uid}/memory_control/state": enabled_rollout_doc(uid, grant_consumer=grant_consumer)
                    | {"grants": {grant_consumer: {}}},
                }
            ),
            consumer=grant_consumer,
        )
        assert grantless_rollout.read_decision == MemoryReadDecision.DENY_MEMORY
