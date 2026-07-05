from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import pytest

from database.memory_collections import MemoryCollections
from scripts import apply_first_user_v3_projection as projection_tool
from scripts import first_user_memory_e2e_proof as proof_tool


@dataclass
class _Snapshot:
    data: dict | None
    exists: bool = True
    id: str = "snapshot"

    def to_dict(self):
        return self.data


class _Document:
    def __init__(self, db, path: str):
        self.db = db
        self.path = path

    def get(self):
        if self.path not in self.db.docs:
            return _Snapshot(None, exists=False, id=self.path.rsplit("/", 1)[-1])
        return _Snapshot(self.db.docs[self.path], id=self.path.rsplit("/", 1)[-1])

    def set(self, payload, merge=False):
        self.db.writes.append((self.path, payload, merge))
        current = self.db.docs.get(self.path, {}) if merge else {}
        self.db.docs[self.path] = {**current, **payload}


class _Query:
    def __init__(self, db, path: str):
        self.db = db
        self.path = path
        self.limit_value = None

    def limit(self, value):
        self.limit_value = value
        return self

    def stream(self):
        rows = []
        prefix = f"{self.path}/"
        for path, data in self.db.docs.items():
            if path.startswith(prefix):
                rows.append(_Snapshot(data, id=path.rsplit("/", 1)[-1]))
        rows = rows[: self.limit_value] if self.limit_value is not None else rows
        return rows


class _Db:
    def __init__(self, docs: dict[str, dict]):
        self.docs = dict(docs)
        self.writes = []

    def document(self, path: str):
        return _Document(self, path)

    def collection(self, path: str):
        return _Query(self, path)


def _head(uid: str, generation: int = 7) -> dict:
    return {
        "uid": uid,
        "schema_version": 1,
        "source": "memory_state_head",
        "account_generation": generation,
        "head_commit_id": "head-7",
        "commit_sequence": generation,
    }


def _memory_item(
    uid: str,
    memory_id: str = "m1",
    *,
    content: str = "private memory text",
    labels=None,
    created_at: datetime | None = None,
    updated_at: datetime | None = None,
    user_review=None,
    promotion: dict | None = None,
) -> dict:
    now = datetime(2026, 7, 4, tzinfo=timezone.utc)
    return {
        "uid": uid,
        "memory_id": memory_id,
        "version": 1,
        "tier": "short_term",
        "status": "active",
        "processing_state": "processed",
        "content": content,
        "evidence": [],
        "source_state": "active",
        "sensitivity_labels": labels or [],
        "visibility": "private",
        "user_asserted": True,
        "created_at": created_at or now,
        "captured_at": now,
        "updated_at": updated_at or now,
        "expires_at": now + timedelta(days=1),
        "user_review": user_review,
        "promotion": promotion,
    }


def _control(uid: str) -> dict:
    return {
        "uid": uid,
        "schema_version": 1,
        "mode": "read",
        "account_generation": 7,
        "grants": {"omi_chat": {"default_memory": True}},
    }


def _projection_state(uid: str) -> dict:
    return {
        "uid": uid,
        "ready": True,
        "account_generation": 7,
        "projection_generation": 7,
        "freshness_fence_generation": 7,
        "tombstone_fence_generation": 7,
        "vector_cleanup_fence_generation": 7,
    }


def _projection_item(uid: str, memory_id: str = "m1") -> dict:
    return {
        "uid": uid,
        "memory_id": memory_id,
        "account_generation": 7,
        "projection_generation": 7,
        "memorydb": {"content": "private memory text", "uid": uid, "id": memory_id, "memory_tier": "short_term"},
    }


def _ready_docs(uid: str) -> dict[str, dict]:
    paths = MemoryCollections(uid=uid)
    return {
        paths.memory_state_head: _head(uid),
        f"{paths.memory_items}/m1": _memory_item(uid),
        proof_tool.GLOBAL_READ_GATE_PATH: {"memory_reads_enabled": True, "kill_switch_active": False},
        proof_tool.WRITE_CONVERGENCE_GATE_PATH: {
            "durable_outbox_enabled": True,
            "dual_write_projection_ready": True,
            "delete_convergence_ready": True,
            "idempotency_contract_ready": True,
        },
        paths.memory_control_state: _control(uid),
        paths.v3_compatibility_projection_state: _projection_state(uid),
        f"{paths.v3_compatibility_projection_items}/m1": _projection_item(uid),
    }


def test_projection_dry_run_report_redacts_memory_content():
    uid = "uid-a"
    db = _Db(_ready_docs(uid))

    build = projection_tool.build_projection(db, uid=uid, project="based-hardware", memory_id="m1", limit=10)
    report = projection_tool.build_report(build)

    assert report["dry_run"] is True
    assert "private memory text" not in str(report)
    assert report["projection"]["items"][0]["content_length"] == len("private memory text")
    assert db.writes == []
    assert report["rollback_manifest"]["touched_doc_paths"] == sorted(build.writes.keys())


def test_projection_apply_requires_matching_confirm_uid(monkeypatch):
    uid = "uid-a"
    monkeypatch.setattr(projection_tool, "_load_firestore_client", lambda project: _Db(_ready_docs(uid)))
    monkeypatch.setattr(
        projection_tool,
        "parse_args",
        lambda: type(
            "Args",
            (),
            {
                "uid": uid,
                "project": "based-hardware",
                "memory_id": "m1",
                "limit": 10,
                "apply": True,
                "confirm_uid": "other",
            },
        )(),
    )

    with pytest.raises(SystemExit, match="--apply requires --confirm-uid"):
        projection_tool.main()


def test_projection_apply_writes_only_projection_paths():
    uid = "uid-a"
    db = _Db(_ready_docs(uid))
    build = projection_tool.build_projection(db, uid=uid, project="based-hardware", memory_id="m1", limit=10)

    written = projection_tool.apply_projection(db, build)

    assert written == sorted(build.writes)
    assert all(path.startswith(f"users/{uid}/v3_compatibility_projection") for path, _, _ in db.writes)


def test_projection_refuses_restricted_sensitivity_by_default():
    uid = "uid-a"
    docs = _ready_docs(uid)
    docs[f"{MemoryCollections(uid=uid).memory_items}/m1"] = _memory_item(uid, labels=["health"])
    db = _Db(docs)

    with pytest.raises(RuntimeError, match="restricted sensitivity"):
        projection_tool.build_projection(db, uid=uid, project="based-hardware", memory_id="m1", limit=10)


def test_projection_item_preserves_source_created_at_before_updated_at():
    uid = "uid-a"
    old_created_at = datetime(2026, 7, 1, tzinfo=timezone.utc)
    newer_updated_at = datetime(2026, 7, 4, tzinfo=timezone.utc)
    docs = _ready_docs(uid)
    docs[f"{MemoryCollections(uid=uid).memory_items}/m1"] = _memory_item(
        uid,
        created_at=old_created_at,
        updated_at=newer_updated_at,
    )
    db = _Db(docs)

    build = projection_tool.build_projection(db, uid=uid, project="based-hardware", memory_id="m1", limit=10)
    projection_item = build.writes[projection_tool.projection_target_item_path(uid, "m1")]

    assert projection_item["created_at"] == old_created_at
    assert projection_item["memorydb"]["updated_at"] == newer_updated_at


def test_projection_refuses_top_level_user_rejected_memory():
    uid = "uid-a"
    docs = _ready_docs(uid)
    docs[f"{MemoryCollections(uid=uid).memory_items}/m1"] = _memory_item(uid, user_review=False)
    db = _Db(docs)

    with pytest.raises(RuntimeError, match="user-rejected"):
        projection_tool.build_projection(db, uid=uid, project="based-hardware", memory_id="m1", limit=10)


def test_projection_refuses_nested_promotion_user_rejected_memory():
    uid = "uid-a"
    docs = _ready_docs(uid)
    docs[f"{MemoryCollections(uid=uid).memory_items}/m1"] = _memory_item(uid, promotion={"user_review": False})
    db = _Db(docs)

    with pytest.raises(RuntimeError, match="user-rejected"):
        projection_tool.build_projection(db, uid=uid, project="based-hardware", memory_id="m1", limit=10)


def test_projection_memorydb_uses_nested_promotion_user_review_when_present():
    uid = "uid-a"
    docs = _ready_docs(uid)
    docs[f"{MemoryCollections(uid=uid).memory_items}/m1"] = _memory_item(
        uid,
        user_review=None,
        promotion={"user_review": True},
    )
    db = _Db(docs)

    build = projection_tool.build_projection(db, uid=uid, project="based-hardware", memory_id="m1", limit=10)
    projection_item = build.writes[projection_tool.projection_target_item_path(uid, "m1")]

    assert projection_item["memorydb"]["user_review"] is True


def test_first_user_proof_passes_with_fake_firestore_and_http():
    uid = "uid-a"
    db = _Db(_ready_docs(uid))
    firestore_report = proof_tool.verify_firestore_state(db, uid=uid, limit=10)

    def fake_get(url, headers, timeout_seconds):
        if headers.get("Authorization"):
            return proof_tool.HttpResult(
                200,
                [{"id": "m1", "uid": uid, "content": "private memory text", "layer": "short_term"}],
                {"X-Omi-Memory-Read-Source": "memory"},
            )
        return proof_tool.HttpResult(401, {"detail": "not authenticated"}, {})

    api_report = proof_tool.verify_api_behavior(
        backend_url="https://dev.example",
        uid=uid,
        id_token="redacted-token",
        limit=10,
        timeout_seconds=1.0,
        http_get=fake_get,
    )
    report = proof_tool.build_report(
        uid=uid, project="based-hardware", firestore_report=firestore_report, api_report=api_report
    )

    assert report["status"] == "pass"
    assert "private memory text" not in str(report)
    assert report["additional_surfaces"]["search"]["status"] == "not_checked"


def test_first_user_proof_fails_generation_mismatch():
    uid = "uid-a"
    docs = _ready_docs(uid)
    docs[MemoryCollections(uid=uid).v3_compatibility_projection_state]["projection_generation"] = 8
    db = _Db(docs)

    report = proof_tool.verify_firestore_state(db, uid=uid, limit=10)

    assert report["status"] == "fail"
    assert any(
        check["name"] == "projection_generation_fences_match_head" and check["status"] == "fail"
        for check in report["checks"]
    )


def test_first_user_proof_fails_when_projection_generation_missing():
    uid = "uid-a"
    docs = _ready_docs(uid)
    del docs[MemoryCollections(uid=uid).v3_compatibility_projection_state]["projection_generation"]
    db = _Db(docs)

    report = proof_tool.verify_firestore_state(db, uid=uid, limit=10)

    assert report["status"] == "fail"
    assert any(
        check["name"] == "projection_generation_fences_match_head" and check["status"] == "fail"
        for check in report["checks"]
    )


def test_first_user_api_proof_fails_non_list_authenticated_response():
    uid = "uid-a"

    def fake_get(url, headers, timeout_seconds):
        if headers.get("Authorization"):
            return proof_tool.HttpResult(200, {"items": []}, {})
        return proof_tool.HttpResult(401, {"detail": "not authenticated"}, {})

    api_report = proof_tool.verify_api_behavior(
        backend_url="https://dev.example",
        uid=uid,
        id_token="redacted-token",
        limit=10,
        timeout_seconds=1.0,
        http_get=fake_get,
    )
    report = proof_tool.build_report(
        uid=uid,
        project="based-hardware",
        firestore_report={"status": "pass", "checks": []},
        api_report=api_report,
    )

    assert api_report["status"] == "fail"
    assert report["status"] == "fail"
    assert any(
        check["name"] == "authenticated_get_v3_memories_body_list" and check["status"] == "fail"
        for check in api_report["checks"]
    )
