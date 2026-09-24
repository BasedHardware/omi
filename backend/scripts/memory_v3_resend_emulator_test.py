#!/usr/bin/env python3
"""Prove POST /v3/memories resends across client devices stay deduped on the emulator.

A browser resend carries the same text under a different X-Device-Id-Hash. The
derived evidence id ignores the device, while the stored evidence identity
includes it: the create path surfaced that collision as a 503. The dedupe
contract instead returns the live identical row, and an evidence id still
occupied by a different source is reissued rather than overwritten.
"""

from __future__ import annotations

# ruff: noqa: E402 -- emulator safety/env bootstrapping must precede backend imports.

import os
import sys
from pathlib import Path
from typing import Any

PROJECT_ID = os.environ.setdefault("GOOGLE_CLOUD_PROJECT", os.environ.get("GCLOUD_PROJECT", "demo-memory"))
os.environ.setdefault("GCLOUD_PROJECT", PROJECT_ID)
os.environ.setdefault("FIREBASE_PROJECT_ID", PROJECT_ID)
os.environ.setdefault("ENCRYPTION_SECRET", "omi_v3_resend_emulator_key_32_bytes")
os.environ.setdefault("MEMORY_ENABLED", "on")
os.environ.setdefault("MEMORY_MODE", "read")
os.environ.setdefault("PROVIDER_MODE", "offline")
os.environ.setdefault("GOOGLE_AUTH_DISABLE_GCE_CHECK", "true")
os.environ.setdefault("GCE_METADATA_HOST", "127.0.0.1:9")
os.environ.setdefault("MEMORY_BELIEF_MODEL_ENABLED", "false")
os.environ.setdefault("NO_PROXY", "127.0.0.1,localhost,::1")
os.environ.setdefault("no_proxy", "127.0.0.1,localhost,::1")

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from fastapi import FastAPI
from fastapi.testclient import TestClient
from google.cloud import firestore

from database.document_ids import document_id_from_seed
from database.memory_collections import MemoryCollections
from models.memory_apply import MemoryControlState, WriterMode

UID = "v3-resend-emulator-uid"
INITIAL_HEAD = "v3-resend-emulator-head"
WEB_CONTENT = "[emulator] user prefers aisle seats on long flights"
OCCUPIED_CONTENT = "[emulator] occupied evidence id without a live row"
SHARED_CONTENT = "[emulator] evidence shared with no live row is reused"
OCCUPIED_VERSION_CONTENT = "[emulator] occupied evidence id with another source version"
BATCH_CONTENT = "[emulator] batch resend keeps one row"
DISTINCT_CONTENT = "[emulator] a genuinely different fact"

DEVICE_A_HEADERS = {"X-App-Platform": "web", "X-Device-Id-Hash": "11111111"}
DEVICE_B_HEADERS = {"X-App-Platform": "web", "X-Device-Id-Hash": "22222222"}
OCCUPIED_DEVICE_ID = "web_99999999"


def _assert_emulator_only() -> None:
    host = (os.environ.get("FIRESTORE_EMULATOR_HOST") or "").strip()
    if not host:
        raise RuntimeError("FIRESTORE_EMULATOR_HOST is required; run through Firebase emulators:exec")
    hostname = host.rsplit(":", 1)[0].strip("[]").lower()
    if hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise RuntimeError(f"refusing non-loopback Firestore emulator host: {hostname}")
    if not PROJECT_ID.startswith("demo-"):
        raise RuntimeError(f"refusing non-demo Firestore project: {PROJECT_ID}")


def _docs(db_client: Any, collection_path: str) -> list[dict[str, Any]]:
    return [snapshot.to_dict() or {} for snapshot in db_client.collection(collection_path).stream()]


def _docs_with_content(db_client: Any, collections: MemoryCollections, content: str) -> list[dict[str, Any]]:
    return [doc for doc in _docs(db_client, collections.memory_items) if doc.get("content") == content]


def _clear_user(db_client: Any, collections: MemoryCollections) -> None:
    for path in collections.all_collection_paths():
        for snapshot in db_client.collection(path).stream():
            snapshot.reference.delete()
    db_client.document(collections.user_root).delete()


def _seed_compatibility_control(db_client: Any, collections: MemoryCollections) -> None:
    control = MemoryControlState(
        uid=UID,
        head_commit_id=INITIAL_HEAD,
        account_generation=7,
        source_generation=11,
        writer_mode=WriterMode.compatibility,
        writer_epoch=1,
    )
    db_client.document(collections.memory_apply_control_state).set(control.model_dump(mode="json"))


def _v3_external_evidence_dump(content: str, *, client_device_id: str) -> dict[str, Any]:
    """Build the exact MemoryEvidence document a /v3 interesting create proposes."""
    from models.memories import Memory, MemoryCategory, MemoryDB
    from utils.memory.canonical_memory_adapter import _legacy_evidence_to_memory

    memory_db = MemoryDB.from_memory(
        Memory(content=content, category=MemoryCategory.interesting),
        UID,
        None,
        False,
        source_type="api",
        source_signal="api",
        extractor_id="external_memory_submission",
        client_device_id=client_device_id,
    )
    evidence = _legacy_evidence_to_memory(memory_db.evidence[0].model_dump(mode="json"), conversation_id=None)
    return evidence.model_dump(mode="json")


def _app() -> FastAPI:
    from routers import memories
    from utils.other import endpoints as auth

    app = FastAPI()
    app.include_router(memories.router)
    app.dependency_overrides[auth.get_current_user_uid] = lambda: UID
    return app


def _expect(failures: list[str], condition: bool, message: str) -> None:
    if not condition:
        failures.append(message)


def _post_memory(client: TestClient, content: str, headers: dict[str, str]) -> Any:
    return client.post(
        "/v3/memories",
        json={"content": content, "category": "interesting"},
        headers=headers,
    )


def _seed_evidence(db_client: Any, collections: MemoryCollections, dump: dict[str, Any]) -> Any:
    ref = db_client.document(f"{collections.memory_evidence}/{dump['evidence_id']}")
    ref.set(dump)
    return ref


def _reissued_for_source(db_client: Any, collections: MemoryCollections, dump: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        doc
        for doc in _docs(db_client, collections.memory_evidence)
        if doc.get("source_id") == dump.get("source_id") and doc.get("evidence_id") != dump["evidence_id"]
    ]


def main() -> int:
    _assert_emulator_only()
    db_client: Any = firestore.Client(project=PROJECT_ID)
    collections = MemoryCollections(uid=UID)
    failures: list[str] = []
    _clear_user(db_client, collections)
    _seed_compatibility_control(db_client, collections)

    try:
        with TestClient(_app(), raise_server_exceptions=False) as client:
            first = _post_memory(client, WEB_CONTENT, DEVICE_A_HEADERS)
            _expect(failures, first.status_code == 200, f"first web POST status={first.status_code}")
            first_id = first.json().get("id") if first.status_code == 200 else None
            _expect(
                failures,
                first_id == document_id_from_seed(WEB_CONTENT),
                "first web POST did not use the content-derived memory id",
            )
            _expect(
                failures,
                len(_docs_with_content(db_client, collections, WEB_CONTENT)) == 1,
                "first web POST did not materialize exactly one item",
            )
            evidence_before_resend = _docs(db_client, collections.memory_evidence)
            _expect(
                failures,
                len(evidence_before_resend) == 1
                and evidence_before_resend[0].get("client_device_id") == "web_11111111",
                "first web POST did not persist one device-stamped evidence row",
            )

            resend = _post_memory(client, WEB_CONTENT, DEVICE_B_HEADERS)
            _expect(
                failures,
                resend.status_code == 200,
                f"cross-device resend status={resend.status_code} body={resend.text[:300]}",
            )
            if resend.status_code == 200:
                _expect(
                    failures,
                    resend.json().get("id") == first_id,
                    "cross-device resend returned a different memory id",
                )
            _expect(
                failures,
                len(_docs_with_content(db_client, collections, WEB_CONTENT)) == 1,
                "cross-device resend duplicated the memory row",
            )
            _expect(
                failures,
                _docs(db_client, collections.memory_evidence) == evidence_before_resend,
                "cross-device resend mutated or duplicated the stored evidence identity",
            )

            occupied_dump = _v3_external_evidence_dump(OCCUPIED_CONTENT, client_device_id=OCCUPIED_DEVICE_ID)
            occupied_ref = _seed_evidence(db_client, collections, occupied_dump)
            occupied = _post_memory(client, OCCUPIED_CONTENT, DEVICE_A_HEADERS)
            _expect(
                failures,
                occupied.status_code == 200,
                f"occupied-evidence create status={occupied.status_code} body={occupied.text[:300]}",
            )
            if occupied.status_code == 200:
                _expect(
                    failures,
                    occupied.json().get("id") == document_id_from_seed(OCCUPIED_CONTENT),
                    "occupied-evidence create did not use the content-derived memory id",
                )
            _expect(
                failures,
                (occupied_ref.get().to_dict() or {}) == occupied_dump,
                "occupied-evidence create mutated the foreign evidence row",
            )
            occupied_reissued = _reissued_for_source(db_client, collections, occupied_dump)
            _expect(
                failures,
                len(occupied_reissued) == 1 and occupied_reissued[0].get("client_device_id") == "web_11111111",
                "occupied-evidence create did not mint exactly one reissued evidence identity",
            )
            _expect(
                failures,
                len(_docs_with_content(db_client, collections, OCCUPIED_CONTENT)) == 1,
                "occupied-evidence create did not materialize its memory row",
            )

            version_dump = _v3_external_evidence_dump(OCCUPIED_VERSION_CONTENT, client_device_id="web_11111111")
            version_dump["source_version"] = "v2-occupied"
            version_ref = _seed_evidence(db_client, collections, version_dump)
            version_create = _post_memory(client, OCCUPIED_VERSION_CONTENT, DEVICE_A_HEADERS)
            _expect(
                failures,
                version_create.status_code == 200,
                f"occupied-version create status={version_create.status_code} body={version_create.text[:300]}",
            )
            if version_create.status_code == 200:
                _expect(
                    failures,
                    version_create.json().get("id") == document_id_from_seed(OCCUPIED_VERSION_CONTENT),
                    "occupied-version create did not use the content-derived memory id",
                )
            _expect(
                failures,
                (version_ref.get().to_dict() or {}) == version_dump,
                "occupied-version create mutated the foreign evidence row",
            )
            version_reissued = _reissued_for_source(db_client, collections, version_dump)
            _expect(
                failures,
                len(version_reissued) == 1 and version_reissued[0].get("source_version") == "v1",
                "occupied-version create did not mint exactly one reissued evidence identity",
            )
            _expect(
                failures,
                len(_docs_with_content(db_client, collections, OCCUPIED_VERSION_CONTENT)) == 1,
                "occupied-version create did not materialize its memory row",
            )

            shared_dump = _v3_external_evidence_dump(SHARED_CONTENT, client_device_id="web_11111111")
            shared_ref = _seed_evidence(db_client, collections, shared_dump)
            shared = _post_memory(client, SHARED_CONTENT, DEVICE_A_HEADERS)
            _expect(
                failures,
                shared.status_code == 200,
                f"shared-evidence create status={shared.status_code} body={shared.text[:300]}",
            )
            if shared.status_code == 200:
                _expect(
                    failures,
                    shared.json().get("id") == document_id_from_seed(SHARED_CONTENT),
                    "shared-evidence create did not use the content-derived memory id",
                )
            _expect(
                failures,
                (shared_ref.get().to_dict() or {}) == shared_dump,
                "shared-evidence create overwrote the identical evidence row",
            )
            _expect(
                failures,
                not _reissued_for_source(db_client, collections, shared_dump),
                "shared-evidence create reissued an identical source identity",
            )
            _expect(
                failures,
                len(_docs_with_content(db_client, collections, SHARED_CONTENT)) == 1,
                "shared-evidence create did not materialize its memory row",
            )

            batch_first = client.post(
                "/v3/memories/batch",
                json={"memories": [{"content": BATCH_CONTENT, "category": "interesting"}]},
                headers=DEVICE_A_HEADERS,
            )
            _expect(failures, batch_first.status_code == 200, f"batch create status={batch_first.status_code}")
            batch_id = None
            if batch_first.status_code == 200:
                batch_memories = batch_first.json().get("memories") or []
                batch_id = batch_memories[0].get("id") if batch_memories else None
            batch_resend = client.post(
                "/v3/memories/batch",
                json={"memories": [{"content": BATCH_CONTENT, "category": "interesting"}]},
                headers=DEVICE_B_HEADERS,
            )
            _expect(
                failures,
                batch_resend.status_code == 200,
                f"cross-device batch resend status={batch_resend.status_code} body={batch_resend.text[:300]}",
            )
            if batch_resend.status_code == 200 and batch_id is not None:
                resend_memories = batch_resend.json().get("memories") or []
                _expect(
                    failures,
                    bool(resend_memories) and resend_memories[0].get("id") == batch_id,
                    "cross-device batch resend returned a different memory id",
                )
            _expect(
                failures,
                len(_docs_with_content(db_client, collections, BATCH_CONTENT)) == 1,
                "cross-device batch resend duplicated the memory row",
            )

            distinct = _post_memory(client, DISTINCT_CONTENT, DEVICE_A_HEADERS)
            _expect(failures, distinct.status_code == 200, f"distinct POST status={distinct.status_code}")
            if distinct.status_code == 200:
                _expect(
                    failures,
                    distinct.json().get("id") not in {first_id, batch_id},
                    "distinct content reused an existing memory id",
                )
            _expect(
                failures,
                len(_docs_with_content(db_client, collections, DISTINCT_CONTENT)) == 1,
                "distinct content did not materialize its own row",
            )
    finally:
        _clear_user(db_client, collections)

    if failures:
        print("FAIL: /v3/memories cross-device resend emulator proof")
        for failure in failures:
            print(f"- {failure}")
        return 1
    print("PASS: /v3/memories cross-device resend, occupied-evidence reissue, and batch dedupe emulator proof")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
