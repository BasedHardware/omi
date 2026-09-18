#!/usr/bin/env python3
"""Exercise authenticated memory writes against the real Firestore emulator.

This is intentionally an API-to-apply proof.  It keeps the explicit user
memory route, the batch route, and the evidence-only import route separate so
the ledger cutover cannot be proven by calling the apply adapter in isolation.
"""

from __future__ import annotations

# ruff: noqa: E402 -- emulator safety/env bootstrapping must precede backend imports.

import os
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

PROJECT_ID = os.environ.setdefault("GOOGLE_CLOUD_PROJECT", os.environ.get("GCLOUD_PROJECT", "demo-memory"))
os.environ.setdefault("GCLOUD_PROJECT", PROJECT_ID)
os.environ.setdefault("ENCRYPTION_SECRET", "omi_jit_user_write_emulator_key_32_bytes")
os.environ.setdefault("MEMORY_ENABLED", "on")
os.environ.setdefault("MEMORY_MODE", "read")
os.environ.setdefault("PROVIDER_MODE", "offline")
os.environ.setdefault("GOOGLE_AUTH_DISABLE_GCE_CHECK", "true")
os.environ.setdefault("GCE_METADATA_HOST", "127.0.0.1:9")
os.environ.setdefault("MEMORY_BELIEF_MODEL_ENABLED", "false")

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from fastapi import FastAPI
from fastapi.testclient import TestClient
from google.cloud import firestore

from database.memory_collections import MemoryCollections
from models.memory_apply import MemoryControlState, WriterMode
from utils.jit_rollout import JIT_ADMISSION_ALLOWLIST

UID = sorted(JIT_ADMISSION_ALLOWLIST)[0]
INITIAL_HEAD = "jit-user-write-emulator-head"
MANUAL_CONTENT = "[emulator] user explicitly prefers morning meetings"
REJECTED_CONTENT = "[emulator] user rejects the afternoon meeting claim"
EXTERNAL_CONTENT = "[emulator] connector observed a morning meeting"
IMPORT_EXTERNAL_ID = "jit-user-write-import-artifact"


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


def _clear_user(db_client: Any, collections: MemoryCollections) -> None:
    for path in collections.all_collection_paths():
        for snapshot in db_client.collection(path).stream():
            snapshot.reference.delete()
    db_client.document(collections.user_root).delete()


def _seed_ledger_control(db_client: Any, collections: MemoryCollections) -> None:
    control = MemoryControlState(
        uid=UID,
        head_commit_id=INITIAL_HEAD,
        account_generation=7,
        source_generation=11,
        writer_mode=WriterMode.ledger,
        writer_epoch=1,
    )
    db_client.document(collections.memory_apply_control_state).set(control.model_dump(mode="json"))


def _app() -> FastAPI:
    # Import after the emulator-only environment is established.  The route's
    # rate-limit dependency still resolves, but its authenticated UID is
    # supplied by this test's FastAPI dependency override.
    from routers import memories
    from utils.other import endpoints as auth

    app = FastAPI()
    app.include_router(memories.router)
    app.dependency_overrides[auth.get_current_user_uid] = lambda: UID
    return app


def _expect(failures: list[str], condition: bool, message: str) -> None:
    if not condition:
        failures.append(message)


def main() -> int:
    _assert_emulator_only()
    db_client: Any = firestore.Client(project=PROJECT_ID)
    collections = MemoryCollections(uid=UID)
    failures: list[str] = []
    _clear_user(db_client, collections)
    _seed_ledger_control(db_client, collections)

    try:
        with TestClient(_app(), raise_server_exceptions=False) as client:
            # A manual POST is an authenticated explicit user assertion.  In
            # ledger mode it must reach save_fact/canonical apply and return a
            # durable fact rather than a pending required-processing row.
            single = client.post(
                "/v3/memories",
                json={"content": MANUAL_CONTENT, "category": "manual"},
            )
            _expect(failures, single.status_code == 200, f"manual POST status={single.status_code}")

            items_after_single = _docs(db_client, collections.memory_items)
            _expect(failures, len(items_after_single) == 1, "manual POST did not materialize exactly one item")
            if items_after_single:
                item = items_after_single[0]
                _expect(
                    failures,
                    item.get("ledger_schema_version") == "knowledge_ledger.v1",
                    "manual POST item is not a knowledge-ledger row",
                )
                _expect(failures, item.get("kind") == "fact", "manual POST item is not a fact")
                _expect(
                    failures,
                    item.get("write_reason") == "direct_user_statement",
                    "manual POST item lacks direct-user write reason",
                )
                _expect(failures, item.get("processing_state") == "processed", "manual POST remained pending")

            operations_after_single = _docs(db_client, collections.memory_operations)
            _expect(
                failures,
                len(operations_after_single) == 1
                and operations_after_single[0].get("operation_type") == "ledger_mutation",
                "manual POST did not use one ledger mutation operation",
            )

            # A retry after the account head advances still resolves to the
            # active row for the same request identity.  It must not create a
            # second fact merely because the first operation's response was
            # lost.
            retry = client.post(
                "/v3/memories",
                json={"content": MANUAL_CONTENT, "category": "manual"},
            )
            _expect(failures, retry.status_code == 200, f"active retry status={retry.status_code}")
            _expect(
                failures,
                len(_docs(db_client, collections.memory_items)) == 1,
                "active retry created a duplicate ledger row",
            )

            # A closed row is retained as history.  A retry with its old
            # content-derived identity must fail honestly rather than
            # resurrecting that row.  A distinct explicit action identity can
            # still save the same text as a new user assertion.
            from utils.memory.canonical_memory_adapter import (
                close_canonical_ledger_item,
                mint_direct_user_write_authority,
                update_canonical_memory_review,
            )
            from utils.memory.knowledge_ledger import LedgerProvenance, save_fact
            from models.product_memory import LedgerWriteReason

            closed_item_id = items_after_single[0].get("memory_id") or items_after_single[0].get("id")
            if isinstance(closed_item_id, str):
                close_canonical_ledger_item(UID, closed_item_id, db_client=db_client)
                closed_retry = client.post(
                    "/v3/memories",
                    json={"content": MANUAL_CONTENT, "category": "manual"},
                )
                _expect(
                    failures,
                    closed_retry.status_code == 503,
                    f"closed same-content retry should fail closed status={closed_retry.status_code}",
                )
                _expect(
                    failures,
                    len(_docs(db_client, collections.memory_items)) == 1,
                    "closed same-content retry resurrected or duplicated a row",
                )
                distinct_intent_id = save_fact(
                    UID,
                    MANUAL_CONTENT,
                    provenance=LedgerProvenance(
                        source_id="v3_manual:explicit-second-intent",
                        source_type="explicit_user_statement",
                        source_version="v3_memory_create.v1",
                        action_id="v3_manual:explicit-second-intent",
                    ),
                    write_reason=LedgerWriteReason.direct_user_statement,
                    db_client=db_client,
                    _direct_user_authority=mint_direct_user_write_authority(),
                )
                _expect(
                    failures,
                    distinct_intent_id != closed_item_id,
                    "distinct explicit same-content intent reused the closed row id",
                )

            # Rejection is an active audit row, so status-only duplicate
            # handling is insufficient.  Retrying the old identity must not
            # return the rejected row as if it were a successful current fact.
            rejected = client.post(
                "/v3/memories",
                json={"content": REJECTED_CONTENT, "category": "manual"},
            )
            _expect(failures, rejected.status_code == 200, f"rejection fixture status={rejected.status_code}")
            rejected_items = [
                item for item in _docs(db_client, collections.memory_items) if item.get("content") == REJECTED_CONTENT
            ]
            if rejected_items:
                rejected_id = rejected_items[0].get("memory_id") or rejected_items[0].get("id")
                if isinstance(rejected_id, str):
                    update_canonical_memory_review(UID, rejected_id, False, db_client=db_client)
                    rejected_retry = client.post(
                        "/v3/memories",
                        json={"content": REJECTED_CONTENT, "category": "manual"},
                    )
                    _expect(
                        failures,
                        rejected_retry.status_code == 503,
                        f"rejected same-content retry should fail closed status={rejected_retry.status_code}",
                    )

            # A kill-switch or unavailable/unknown JIT result never grants the
            # direct ledger seam.  Under a ledger writer the compatibility
            # fallback consequently fails closed without creating a row.
            from utils.memory import memory_service as memory_service_module

            original_resolver = memory_service_module.resolve_jit_rollout_sync
            try:
                for denial in ("kill_switch", "unknown_authority"):
                    memory_service_module.resolve_jit_rollout_sync = lambda *_args, **_kwargs: SimpleNamespace(
                        permits_work=False
                    )
                    before_denial_items = len(_docs(db_client, collections.memory_items))
                    denied = client.post(
                        "/v3/memories",
                        json={"content": f"[emulator] denied {denial}", "category": "manual"},
                    )
                    _expect(
                        failures, denied.status_code == 503, f"{denial} should fail closed status={denied.status_code}"
                    )
                    _expect(
                        failures,
                        len(_docs(db_client, collections.memory_items)) == before_denial_items,
                        f"{denial} created a ledger row",
                    )
            finally:
                memory_service_module.resolve_jit_rollout_sync = original_resolver

            # A manual-only batch has the same explicit-user contract and must
            # remain retry-stable.  The mixed batch is checked before writes so
            # an external connector item cannot silently gain ledger authority
            # by sharing a request with a manual item.
            manual_batch = client.post(
                "/v3/memories/batch",
                json={"memories": [{"content": "[emulator] user prefers concise agendas", "category": "manual"}]},
            )
            _expect(failures, manual_batch.status_code == 200, f"manual batch status={manual_batch.status_code}")

            # Ledger batch validation runs before any commit.  Whitespace-only
            # content is accepted by the API model but rejected by LedgerWrite;
            # placing it second catches the old valid-first/invalid-later
            # partial-commit failure.
            before_invalid_batch = len(_docs(db_client, collections.memory_items))
            invalid_batch = client.post(
                "/v3/memories/batch",
                json={
                    "memories": [
                        {"content": "[emulator] valid batch item", "category": "manual"},
                        {"content": "   ", "category": "manual"},
                    ]
                },
            )
            _expect(
                failures,
                invalid_batch.status_code == 503,
                f"invalid direct batch should fail closed status={invalid_batch.status_code}",
            )
            _expect(
                failures,
                len(_docs(db_client, collections.memory_items)) == before_invalid_batch,
                "invalid direct batch partially committed its valid first item",
            )

            # A forged non-capability value cannot select the direct writer or
            # reach canonical apply, even when the caller supplies ledger data.
            before_forged_authority = len(_docs(db_client, collections.memory_items))
            try:
                save_fact(
                    UID,
                    "[emulator] forged authority must not write",
                    provenance=LedgerProvenance(
                        source_id="forged-authority",
                        source_type="explicit_user_statement",
                        source_version="v3_memory_create.v1",
                        action_id="forged-authority",
                    ),
                    write_reason=LedgerWriteReason.direct_user_statement,
                    db_client=db_client,
                    _direct_user_authority=object(),
                )
            except ValueError:
                pass
            else:
                failures.append("forged direct-user authority was accepted")
            _expect(
                failures,
                len(_docs(db_client, collections.memory_items)) == before_forged_authority,
                "forged direct-user authority committed a ledger row",
            )

            item_count_before_mixed = len(_docs(db_client, collections.memory_items))
            mixed_batch = client.post(
                "/v3/memories/batch",
                json={
                    "memories": [
                        {"content": "[emulator] user prefers concise agendas", "category": "manual"},
                        {"content": EXTERNAL_CONTENT, "category": "interesting"},
                    ]
                },
            )
            _expect(
                failures,
                mixed_batch.status_code == 503,
                f"ledger mixed batch should fail closed status={mixed_batch.status_code}",
            )
            _expect(
                failures,
                len(_docs(db_client, collections.memory_items)) == item_count_before_mixed,
                "ledger mixed batch partially committed before rejecting connector input",
            )

            # Imports are evidence ingress.  They must remain accepted in
            # ledger mode while creating no product memory or ledger row.
            before_import_items = len(_docs(db_client, collections.memory_items))
            import_response = client.post(
                "/v3/memory-imports/batch",
                json={
                    "source_type": "local_files",
                    "import_run_id": "jit-user-write-import-run",
                    "items": [{"external_id": IMPORT_EXTERNAL_ID, "title": "[emulator] imported title"}],
                },
            )
            _expect(
                failures, import_response.status_code == 200, f"evidence import status={import_response.status_code}"
            )
            if import_response.status_code == 200:
                payload = import_response.json()
                _expect(failures, payload.get("artifacts_created") == 1, "evidence import did not create one artifact")
                _expect(failures, payload.get("candidates_created") == 0, "evidence import created candidates")
            _expect(
                failures,
                len(_docs(db_client, collections.memory_items)) == before_import_items,
                "evidence import created a product memory",
            )
    finally:
        _clear_user(db_client, collections)

    if failures:
        print("FAIL: JIT ledger direct-user API emulator proof")
        for failure in failures:
            print(f"- {failure}")
        return 1
    print("PASS: JIT ledger direct-user POST, batch fencing, and evidence-import emulator proof")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
