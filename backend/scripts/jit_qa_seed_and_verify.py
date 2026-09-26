#!/usr/bin/env python3
"""Seed and verify the bounded JIT QA ledger-drain proof.

This operator is deliberately narrower than the deployment workflow.  It owns
only a deterministic, synthetic fixture in the named ``jit-qa`` Firestore
database.  The explicit ``bootstrap`` command is create-only and may only
initialize an empty user plane for the fixed QA identity.  It tolerates the
one known deployment recovery cursor in ``conversation_recovery_state`` after
validating its exact metadata shape, preserves that cursor, and rejects every
other collection or document.  It never discovers or edits another account,
never creates a production control plane, and never calls a model.  The Cloud
Run workflow owns job execution; this command consumes its content-free
execution summaries.

The fixture contains 101 canonical rows that are intentionally missing the
ledger schema marker.  The production drain's mutation budget is 100 rows per
run, so two executions prove durable ``100 + 1`` progress.  A later retry,
rollback, and rollforward prove that the canonical rows and evidence remain
present.  The fixture rows are synthetic and namespaced by ``run_id``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from google.cloud import firestore

# Keep script invocation from the repository root and direct backend invocation
# equally usable without changing the installed environment.
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from models.memory_evidence import ArtifactPreservationState, MemoryEvidence, SourceState  # noqa: E402
from models.product_memory import MemoryItem, MemoryItemStatus, MemoryLayer, ProcessingState  # noqa: E402
from models.users import PlanType, Subscription, SubscriptionStatus  # noqa: E402
from utils.memory.knowledge_ledger import LEDGER_SCHEMA_VERSION  # noqa: E402
from utils.memory.knowledge_ledger_migration import (  # noqa: E402
    rollback_ledger_writer_to_compatibility,
)
from utils.memory.memory_system import ensure_canonical_apply_control_state  # noqa: E402

PROJECT_ID = "based-hardware-dev"
DATABASE_ID = "jit-qa"
REGION = "us-central1"
QA_UID = "vi7SA9ckQCe4ccobWNxlbdcNdC23"
LEDGER_DRAIN_JOB = "knowledge-ledger-drain-qa-job"
FIXTURE_MARKER = "omi.jit.qa.seed-and-verify.v1"
BOOTSTRAP_MARKER = "omi.jit.qa.bootstrap.v1"
BOOTSTRAP_PATH = f"jit_qa_bootstrap/{QA_UID}"
TESTER_PATH = f"testers/{QA_UID}"
QA_TIME_ZONE = "America/New_York"
# The isolated QA database has no Stripe authority.  This is a named, synthetic
# entitlement used only by the QA service's fixed UID allowlist; it is never
# copied to customer data or used as production billing evidence.
QA_ENTITLEMENT_PLAN = PlanType.operator.value
QA_ENTITLEMENT_PERIOD_END = 4102444800  # 2100-01-01T00:00:00Z
ROW_COUNT = 101
MUTATION_PAGE_SIZE = 100
EXCLUSIVITY_SCAN_LIMIT = ROW_COUNT + 1
LEDGER_DRAIN_CURSOR_PATH = "knowledge_ledger_migration_control/inventory_cursor"
RUN_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,47}$")
EMPTY_SCAN_RECOVERY_COLLECTION = "conversation_recovery_state"
EMPTY_SCAN_RECOVERY_DOCUMENT = "byok_abandonment_sweep"
EMPTY_SCAN_RECOVERY_FIELDS = frozenset({"generation", "resume_after_path", "updated_at"})
EMPTY_SCAN_RECOVERY_DOCUMENT_LIMIT = 1
EMPTY_SCAN_RECOVERY_GENERATION_MAX = 2**63 - 1
SUMMARY_KEYS = (
    "inventoried_users",
    "scanned_documents",
    "attempted_users",
    "allowlist_blocked_users",
    "rollout_blocked_users",
    "authorization_revoked_users",
    "remaining_users",
    "cutover_users",
    "migrated_rows",
    "errors",
)


class JITQAVerificationError(RuntimeError):
    """A QA operator precondition or proof assertion failed."""


def validate_target(*, project: str = PROJECT_ID, database: str = DATABASE_ID, uid: str = QA_UID) -> None:
    """Reject every project, database, or identity outside the named QA plane."""

    if project != PROJECT_ID:
        raise JITQAVerificationError(f"QA project must be {PROJECT_ID}")
    if database != DATABASE_ID:
        raise JITQAVerificationError(f"QA Firestore database must be {DATABASE_ID}")
    if uid != QA_UID:
        raise JITQAVerificationError("QA UID must be the fixed isolated test identity")


def validate_environment(environ: Mapping[str, str] | None = None) -> None:
    """Fail closed when process selectors point at a different data plane."""

    env = os.environ if environ is None else environ
    for name in ("GOOGLE_CLOUD_PROJECT", "GCLOUD_PROJECT"):
        value = env.get(name, "").strip()
        if value and value != PROJECT_ID:
            raise JITQAVerificationError(f"{name} must be {PROJECT_ID}")
    database = env.get("FIRESTORE_DATABASE_ID", "").strip()
    if database and database != DATABASE_ID:
        raise JITQAVerificationError("FIRESTORE_DATABASE_ID must be jit-qa")
    if env.get("FIRESTORE_EMULATOR_HOST", "").strip():
        raise JITQAVerificationError("the QA proof must use named Cloud Firestore, not an emulator")
    if env.get("SERVICE_ACCOUNT_JSON", "").strip() or env.get("FIREBASE_AUTH_CREDENTIALS_PATH", "").strip():
        raise JITQAVerificationError("customer Firebase credential selectors are forbidden")


def validate_run_id(run_id: str) -> str:
    if not RUN_ID_RE.fullmatch(run_id):
        raise JITQAVerificationError("run_id must be lowercase, namespaced, and contain only [a-z0-9_-]")
    return run_id


def build_firestore_client() -> Any:
    """Construct an explicit named-database client; never inherit a default DB."""

    validate_environment()
    validate_target()
    return firestore.Client(project=PROJECT_ID, database=DATABASE_ID)


def _memory_path(run_id: str, index: int) -> str:
    return f"users/{QA_UID}/memory_items/jitqa-{run_id}-legacy-{index:03d}"


def _evidence_path(run_id: str, index: int) -> str:
    return f"users/{QA_UID}/memory_evidence/jitqa-{run_id}-evidence-{index:03d}"


def _control_path() -> str:
    return f"users/{QA_UID}/memory_state/apply_control"


def _completion_path() -> str:
    return f"users/{QA_UID}/memory_control/knowledge_ledger_migration"


def _projection_path() -> str:
    return f"users/{QA_UID}/memory_control/knowledge_ledger_prompt_projection"


def _bootstrap_marker_payload(*, status: str) -> dict[str, Any]:
    return {
        "schema_version": BOOTSTRAP_MARKER,
        "status": status,
        "project": PROJECT_ID,
        "database": DATABASE_ID,
        "uid": QA_UID,
        "time_zone": QA_TIME_ZONE,
        "entitlement_plan": QA_ENTITLEMENT_PLAN,
        "test_account": True,
    }


def _qa_subscription_payload() -> dict[str, Any]:
    """Return the typed subscription projection required by desktop admission.

    This is intentionally built through the shipped ``Subscription`` model.  A
    QA database has no Stripe webhook, so the period is a fixed synthetic
    horizon and is scoped by the explicit QA marker below.
    """

    return Subscription(
        plan=PlanType.operator,
        status=SubscriptionStatus.active,
        current_period_end=QA_ENTITLEMENT_PERIOD_END,
    ).model_dump(mode="json")


def _qa_profile_payload() -> dict[str, Any]:
    return {
        "uid": QA_UID,
        "time_zone": QA_TIME_ZONE,
        "subscription": _qa_subscription_payload(),
        "test_account": True,
        "jit_qa_bootstrap_marker": BOOTSTRAP_MARKER,
        "jit_qa_project": PROJECT_ID,
        "jit_qa_database": DATABASE_ID,
    }


def _qa_tester_payload() -> dict[str, Any]:
    # ``database.apps.is_tester_db`` treats existence of this canonical tester
    # document as the test-account entitlement.  Keep the apps array explicit
    # for readers that use the tester document's normal shape.
    return {
        "uid": QA_UID,
        "apps": [],
        "test_account": True,
        "jit_qa_bootstrap_marker": BOOTSTRAP_MARKER,
        "jit_qa_project": PROJECT_ID,
        "jit_qa_database": DATABASE_ID,
    }


def _assert_named_database_empty(db_client: Any) -> dict[str, Any]:
    """Prove the named database is empty before creating the QA account.

    ``collections()`` is a metadata-only inventory.  Firestore does not retain
    empty collections.  The deployed backend may, however, leave one bounded
    recovery cursor in ``conversation_recovery_state`` before first bootstrap.
    That cursor contains no user-plane data and is preserved.  Every other
    collection, document, field, or malformed cursor fails closed before any
    write.
    """

    collections_factory = getattr(db_client, "collections", None)
    if not callable(collections_factory):
        raise JITQAVerificationError("bootstrap requires a Firestore client that can inventory collections")
    try:
        collection_iterator = iter(collections_factory())
        collections = []
        for _ in range(2):
            try:
                collections.append(next(collection_iterator))
            except StopIteration:
                break
    except Exception as exc:
        raise JITQAVerificationError("bootstrap could not inventory the named Firestore database") from exc
    if len(collections) > 1:
        raise JITQAVerificationError("bootstrap requires an empty user plane; found more than one top-level collection")
    if not collections:
        return {
            "user_plane_empty": True,
            "preexisting_runtime_metadata": False,
            "runtime_metadata_documents": 0,
        }

    collection = collections[0]
    collection_id = str(getattr(collection, "id", ""))
    if collection_id != EMPTY_SCAN_RECOVERY_COLLECTION:
        raise JITQAVerificationError(
            "bootstrap requires a truly empty named database; " f"found collection {collection_id!r}"
        )

    # ``list_documents`` includes missing parent documents for nested
    # collections. That is the only bounded way to distinguish an empty
    # direct collection from an orphan descendant, so clients without it are
    # refused rather than treated as empty.
    list_documents = getattr(collection, "list_documents", None)
    if not callable(list_documents):
        raise JITQAVerificationError("bootstrap requires a bounded recovery metadata inventory")
    try:
        document_iterator = iter(list_documents(page_size=EMPTY_SCAN_RECOVERY_DOCUMENT_LIMIT + 1))
        document_refs = []
        for _ in range(EMPTY_SCAN_RECOVERY_DOCUMENT_LIMIT + 1):
            try:
                document_refs.append(next(document_iterator))
            except StopIteration:
                break
    except Exception as exc:
        raise JITQAVerificationError("bootstrap could not inventory recovery metadata") from exc
    if len(document_refs) > EMPTY_SCAN_RECOVERY_DOCUMENT_LIMIT:
        raise JITQAVerificationError("bootstrap recovery metadata inventory exceeded its hard bound")
    if len(document_refs) != 1:
        raise JITQAVerificationError("bootstrap recovery metadata inventory was empty or exceeded its allowlist")
    document_ref = document_refs[0]
    document_id = str(getattr(document_ref, "id", ""))
    if document_id != EMPTY_SCAN_RECOVERY_DOCUMENT:
        raise JITQAVerificationError("bootstrap recovery metadata has an unexpected document")
    try:
        child_iterator = iter(document_ref.collections(page_size=1))
        next(child_iterator)
    except StopIteration:
        pass
    except Exception as exc:
        raise JITQAVerificationError("bootstrap could not inventory recovery metadata descendants") from exc
    else:
        raise JITQAVerificationError("bootstrap recovery metadata has an unexpected descendant collection")
    try:
        snapshot = document_ref.get()
    except Exception as exc:
        raise JITQAVerificationError("bootstrap could not read recovery metadata") from exc
    payload = snapshot.to_dict() if getattr(snapshot, "exists", False) else None
    if document_id != EMPTY_SCAN_RECOVERY_DOCUMENT or not isinstance(payload, Mapping):
        raise JITQAVerificationError("bootstrap recovery metadata has an unexpected document")
    if set(payload) != EMPTY_SCAN_RECOVERY_FIELDS:
        raise JITQAVerificationError("bootstrap recovery metadata has an unexpected schema")
    generation = payload.get("generation")
    if (
        not isinstance(generation, int)
        or isinstance(generation, bool)
        or generation < 1
        or generation > EMPTY_SCAN_RECOVERY_GENERATION_MAX
    ):
        raise JITQAVerificationError("bootstrap recovery metadata has an invalid generation")
    if payload.get("resume_after_path") is not None:
        raise JITQAVerificationError("bootstrap recovery metadata must have a null resume cursor")
    updated_at = payload.get("updated_at")
    if not isinstance(updated_at, datetime) or updated_at.tzinfo is None or updated_at.utcoffset() is None:
        raise JITQAVerificationError("bootstrap recovery metadata has an invalid timestamp")
    if updated_at.astimezone(timezone.utc) > datetime.now(timezone.utc) + timedelta(minutes=5):
        raise JITQAVerificationError("bootstrap recovery metadata timestamp is too far in the future")
    metadata_digest = hashlib.sha256(
        json.dumps(
            {
                "collection": collection_id,
                "document": document_id,
                "generation": generation,
                "resume_after_path": None,
                "updated_at": updated_at.astimezone(timezone.utc).isoformat(),
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return {
        "user_plane_empty": True,
        "preexisting_runtime_metadata": True,
        "runtime_metadata_documents": 1,
        "runtime_metadata_collection": collection_id,
        "runtime_metadata_document": document_id,
        "runtime_metadata_generation": generation,
        "runtime_metadata_resume_after_path": None,
        "runtime_metadata_digest": metadata_digest,
    }


def _assert_owned_fields(
    db_client: Any,
    path: str,
    expected: Mapping[str, Any],
    *,
    label: str,
) -> bool:
    """Return whether a document exists with all owned fields unchanged."""

    payload = _as_dict(db_client.document(path).get())
    if not payload:
        return False
    for key, value in expected.items():
        if payload.get(key) != value:
            raise JITQAVerificationError(f"refusing to overwrite unowned or malformed QA {label}")
    return True


def _create_or_verify_owned_document(
    db_client: Any,
    path: str,
    payload: Mapping[str, Any],
    *,
    label: str,
) -> str:
    """Create a profile/tester document, never overwrite an existing document."""

    ref = db_client.document(path)
    snapshot = ref.get()
    if getattr(snapshot, "exists", False):
        existing = _as_dict(snapshot)
        for key, value in payload.items():
            if existing.get(key) != value:
                raise JITQAVerificationError(f"refusing to overwrite unowned or malformed QA {label}")
        return "existing"
    create = getattr(ref, "create", None)
    if not callable(create):
        raise JITQAVerificationError(f"bootstrap requires create-only Firestore writes for QA {label}")
    try:
        create(dict(payload))
    except Exception as exc:
        # A race is safe only if the winner wrote the exact owned projection.
        if _assert_owned_fields(db_client, path, payload, label=label):
            return "existing"
        raise JITQAVerificationError(f"QA {label} creation did not produce the owned document") from exc
    return "created"


def bootstrap_qa_account(db_client: Any) -> dict[str, Any]:
    """Create the fixed QA identity and canonical apply state in an empty DB.

    This is the only command allowed to prepare an empty ``jit-qa`` database.
    It writes a durable ownership marker first, then creates only missing
    profile/tester documents and invokes the shipped canonical apply-state
    helper.  It never fabricates a ledger completion or cutover receipt; the
    drain job remains the sole cutover authority.
    """

    validate_environment()
    validate_target()
    marker_ref = db_client.document(BOOTSTRAP_PATH)
    marker_snapshot = marker_ref.get()
    marker = _as_dict(marker_snapshot)
    precondition = {
        "mode": "resume_owned_bootstrap",
        "user_plane_empty": None,
        "preexisting_runtime_metadata": None,
        "current_inventory_verified": False,
        "previously_verified": True,
    }
    if not marker:
        precondition = _assert_named_database_empty(db_client)
        precondition["mode"] = "fresh_bootstrap"
        precondition["current_inventory_verified"] = True
        precondition["previously_verified"] = False
        create = getattr(marker_ref, "create", None)
        if not callable(create):
            raise JITQAVerificationError("bootstrap requires create-only Firestore writes for its ownership marker")
        try:
            create(_bootstrap_marker_payload(status="in_progress"))
        except Exception as exc:
            marker = _as_dict(marker_ref.get())
            if marker != _bootstrap_marker_payload(status="in_progress"):
                raise JITQAVerificationError("bootstrap ownership marker raced with an unowned document") from exc
    else:
        expected_marker = _bootstrap_marker_payload(status=str(marker.get("status", "")))
        if marker != expected_marker or marker.get("status") not in {"in_progress", "complete"}:
            raise JITQAVerificationError("QA bootstrap marker is missing, malformed, or owned by another run")

    profile_result = _create_or_verify_owned_document(
        db_client,
        f"users/{QA_UID}",
        _qa_profile_payload(),
        label="user profile",
    )
    tester_result = _create_or_verify_owned_document(db_client, TESTER_PATH, _qa_tester_payload(), label="tester")

    # This helper atomically creates the real canonical apply-control state and
    # its maintenance registry entry.  No raw MemoryControlState admission is
    # fabricated here.
    control = ensure_canonical_apply_control_state(QA_UID, db_client=db_client)
    if control.uid != QA_UID or control.writer_mode.value != "compatibility":
        raise JITQAVerificationError("canonical QA apply-control helper returned an unexpected writer state")

    complete_marker = _bootstrap_marker_payload(status="complete")
    marker_ref.set(complete_marker)
    return {
        "result": "PASS",
        "status": "complete",
        "project": PROJECT_ID,
        "database": DATABASE_ID,
        "uid": QA_UID,
        "time_zone": QA_TIME_ZONE,
        "entitlement_plan": QA_ENTITLEMENT_PLAN,
        "profile": profile_result,
        "tester": tester_result,
        "apply_control_path": _control_path(),
        "apply_control_writer_mode": control.writer_mode.value,
        "maintenance_registry": f"canonical_memory_maintenance_registry/{QA_UID}",
        "cutover_authority": "knowledge-ledger-drain-qa-job via publish_ledger_migration_cutover",
        "bootstrap_precondition": precondition,
    }


def _as_dict(snapshot: Any) -> dict[str, Any]:
    if not getattr(snapshot, "exists", False):
        return {}
    payload = snapshot.to_dict()
    return dict(payload) if isinstance(payload, Mapping) else {}


def _get_selected(ref: Any, fields: Sequence[str]) -> dict[str, Any]:
    selector = getattr(ref, "select", None)
    snapshot = selector(list(fields)).get() if callable(selector) else ref.get()
    return _as_dict(snapshot)


def _assert_fixture_exclusive(db_client: Any, *, run_id: str) -> None:
    """Ensure the allowlisted QA account contains only this proof fixture.

    The production drain scans the whole allowlisted account, so a pre-existing
    row would consume the 100-row budget and make the proof ambiguous.  The
    query projects ownership metadata only; it never fetches customer content.
    """

    collection_factory = getattr(db_client, "collection", None)
    if not callable(collection_factory):
        raise JITQAVerificationError("QA Firestore client cannot prove fixture exclusivity")
    collection = collection_factory(f"users/{QA_UID}/memory_items")
    selector = getattr(collection, "select", None)
    if not callable(selector):
        raise JITQAVerificationError("QA Firestore client cannot project fixture ownership metadata")
    collection = selector(
        ["memory_id", "uid", "jit_qa_fixture", "jit_qa_run_id", "jit_qa_row", "promotion", "ledger_schema_version"]
    )
    limiter = getattr(collection, "limit", None)
    if not callable(limiter):
        raise JITQAVerificationError("QA Firestore client cannot bound fixture exclusivity inventory")
    collection = limiter(EXCLUSIVITY_SCAN_LIMIT)
    stream = getattr(collection, "stream", None)
    if not callable(stream):
        raise JITQAVerificationError("QA Firestore client cannot prove fixture exclusivity")
    expected_ids = {f"jitqa-{run_id}-legacy-{index:03d}" for index in range(ROW_COUNT)}
    scanned = 0
    for snapshot in stream():
        scanned += 1
        if scanned > EXCLUSIVITY_SCAN_LIMIT:
            raise JITQAVerificationError("QA fixture exclusivity inventory exceeded its hard bound")
        snapshot_id = str(getattr(snapshot, "id", ""))
        payload = _as_dict(snapshot)
        expected_index = int(snapshot_id.rsplit("-", 1)[-1]) if snapshot_id in expected_ids else -1
        if snapshot_id not in expected_ids or not _owned_fields_match(
            payload,
            run_id=run_id,
            index=expected_index,
        ):
            # Stop at the first foreign row.  The query is deliberately capped
            # at 101 + 1 so a malicious/accidental large collection cannot turn
            # this proof into an unbounded inventory.
            raise JITQAVerificationError(
                "QA account contains a non-owned QA row or foreign memory row; refusing to migrate shared state"
            )


def _stored_model(model: Any) -> dict[str, Any]:
    return model.model_dump(mode="json")


def _fixture_evidence(run_id: str, index: int) -> MemoryEvidence:
    return MemoryEvidence(
        evidence_id=f"jitqa-{run_id}-evidence-{index:03d}",
        source_type="conversation",
        source_id=f"jitqa-{run_id}-synthetic-source-{index:03d}",
        source_version="jit-qa-v1",
        artifact_preservation=ArtifactPreservationState.preserved,
        source_state=SourceState.active,
    )


EVIDENCE_OWNERSHIP_FIELDS = (
    "evidence_id",
    "source_id",
    "source_version",
    "artifact_preservation",
    "source_state",
    "source_type",
)


def _expected_evidence_fields(run_id: str, index: int) -> dict[str, Any]:
    expected = _stored_model(_fixture_evidence(run_id, index))
    return {key: expected.get(key) for key in EVIDENCE_OWNERSHIP_FIELDS}


def _projected_evidence_fields(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize fake and Firestore projection responses to owned fields."""

    return {key: payload[key] for key in EVIDENCE_OWNERSHIP_FIELDS if key in payload}


def _fixture_item(
    run_id: str,
    index: int,
    *,
    account_generation: int,
    head_commit_id: str,
) -> MemoryItem:
    evidence = _fixture_evidence(run_id, index)
    item = MemoryItem(
        memory_id=f"jitqa-{run_id}-legacy-{index:03d}",
        uid=QA_UID,
        version=1,
        tier=MemoryLayer.long_term,
        status=MemoryItemStatus.active,
        processing_state=ProcessingState.processed,
        content=f"Synthetic JIT QA ledger proof row {index:03d} ({run_id})",
        evidence=[evidence],
        source_state=SourceState.active,
        sensitivity_labels=[],
        visibility="private",
        user_asserted=index == 0,
        captured_at=datetime(2026, 9, 5, tzinfo=timezone.utc),
        updated_at=datetime(2026, 9, 5, tzinfo=timezone.utc),
        ledger_commit_id=head_commit_id,
        ledger_sequence=0,
        item_revision=1,
        account_generation=account_generation,
        promotion={
            "jit_qa_fixture": FIXTURE_MARKER,
            "jit_qa_run_id": run_id,
            "jit_qa_row": index,
        },
        predicate="resides_in" if index == 0 else "likes",
    )
    # Keep the marker in a typed model field as well as the legacy top-level
    # projection.  Canonical migration rewrites a MemoryItem through
    # model_dump(), which intentionally drops unknown top-level fields; the
    # promotion marker therefore survives the migration and keeps the
    # post-cutover exclusivity proof content-free.
    payload = _stored_model(item)
    payload.update(
        {
            "jit_qa_fixture": FIXTURE_MARKER,
            "jit_qa_run_id": run_id,
            "jit_qa_row": index,
        }
    )
    # Return the model plus marker payload through a private helper below; the
    # model remains useful to tests that verify the canonical legacy shape.
    object.__setattr__(item, "_jit_qa_payload", payload)
    return item


def _item_payload(item: MemoryItem) -> dict[str, Any]:
    payload = getattr(item, "_jit_qa_payload", None)
    if not isinstance(payload, dict):
        raise JITQAVerificationError("internal fixture payload lost its ownership marker")
    return dict(payload)


def _owned_fields_match(payload: Mapping[str, Any], *, run_id: str, index: int) -> bool:
    top_level_marker = (
        payload.get("jit_qa_fixture") == FIXTURE_MARKER
        and payload.get("jit_qa_run_id") == run_id
        and payload.get("jit_qa_row") == index
    )
    promotion = payload.get("promotion")
    promoted_marker = (
        isinstance(promotion, Mapping)
        and promotion.get("jit_qa_fixture") == FIXTURE_MARKER
        and promotion.get("jit_qa_run_id") == run_id
        and promotion.get("jit_qa_row") == index
    )
    return (
        (top_level_marker or promoted_marker)
        and payload.get("uid") == QA_UID
        and payload.get("memory_id") == f"jitqa-{run_id}-legacy-{index:03d}"
    )


def _assert_apply_control(db_client: Any, *, allow_ledger: bool = False) -> dict[str, Any]:
    payload = _get_selected(
        db_client.document(_control_path()),
        (
            "uid",
            "writer_mode",
            "writer_epoch",
            "head_commit_id",
            "account_generation",
            "source_generation",
            "commit_sequence",
        ),
    )
    if not payload:
        raise JITQAVerificationError("QA apply-control state is missing; use the deployment/database factory first")
    if payload.get("uid") != QA_UID:
        raise JITQAVerificationError("QA apply-control UID does not match the fixed identity")
    mode = payload.get("writer_mode")
    allowed = {"compatibility", "ledger"} if allow_ledger else {"compatibility"}
    if mode not in allowed:
        raise JITQAVerificationError(f"QA apply-control writer_mode must be one of {sorted(allowed)}")
    if not isinstance(payload.get("account_generation"), int) or not isinstance(payload.get("head_commit_id"), str):
        raise JITQAVerificationError("QA apply-control state is missing the canonical generation fence")
    return payload


def seed_fixture(db_client: Any, *, run_id: str) -> dict[str, int | str]:
    """Create only missing, owned synthetic rows and evidence documents."""

    validate_target()
    run_id = validate_run_id(run_id)
    control = _assert_apply_control(db_client)
    if control.get("writer_mode") != "compatibility":
        raise JITQAVerificationError("seed requires compatibility writer mode")
    _assert_fixture_exclusive(db_client, run_id=run_id)

    created_rows = 0
    existing_rows = 0
    for index in range(ROW_COUNT):
        item = _fixture_item(
            run_id,
            index,
            account_generation=int(control["account_generation"]),
            head_commit_id=str(control["head_commit_id"]),
        )
        expected = _item_payload(item)
        memory_ref = db_client.document(_memory_path(run_id, index))
        existing = _get_selected(
            memory_ref,
            (
                "memory_id",
                "uid",
                "jit_qa_fixture",
                "jit_qa_run_id",
                "jit_qa_row",
                "promotion",
                "ledger_schema_version",
            ),
        )
        if existing:
            if not _owned_fields_match(existing, run_id=run_id, index=index):
                raise JITQAVerificationError(f"refusing to overwrite non-owned QA row {index:03d}")
            existing_rows += 1
            continue

        evidence_ref = db_client.document(_evidence_path(run_id, index))
        evidence = _get_selected(evidence_ref, EVIDENCE_OWNERSHIP_FIELDS)
        expected_evidence = _stored_model(_fixture_evidence(run_id, index))
        expected_evidence_ownership = _expected_evidence_fields(run_id, index)
        if evidence and _projected_evidence_fields(evidence) != expected_evidence_ownership:
            raise JITQAVerificationError(f"refusing to overwrite non-owned QA evidence {index:03d}")
        if not evidence:
            create_evidence = getattr(evidence_ref, "create", None)
            if not callable(create_evidence):
                raise JITQAVerificationError("QA fixture requires create-only Firestore writes for evidence")
            try:
                create_evidence(expected_evidence)
            except Exception as exc:
                raced_evidence = _get_selected(evidence_ref, EVIDENCE_OWNERSHIP_FIELDS)
                if _projected_evidence_fields(raced_evidence) != expected_evidence_ownership:
                    raise JITQAVerificationError(
                        f"QA fixture evidence creation raced with an unowned document {index:03d}"
                    ) from exc
        create_memory = getattr(memory_ref, "create", None)
        if not callable(create_memory):
            raise JITQAVerificationError("QA fixture requires create-only Firestore writes for memory rows")
        try:
            create_memory(expected)
        except Exception as exc:
            raced_memory = _get_selected(
                memory_ref,
                (
                    "memory_id",
                    "uid",
                    "jit_qa_fixture",
                    "jit_qa_run_id",
                    "jit_qa_row",
                    "promotion",
                    "ledger_schema_version",
                ),
            )
            if not _owned_fields_match(raced_memory, run_id=run_id, index=index):
                raise JITQAVerificationError(
                    f"QA fixture memory creation raced with an unowned document {index:03d}"
                ) from exc
        created_rows += 1

    return {
        "run_id": run_id,
        "created_rows": created_rows,
        "existing_rows": existing_rows,
        "row_count": ROW_COUNT,
        "project": PROJECT_ID,
        "database": DATABASE_ID,
        "uid": QA_UID,
    }


@dataclass(frozen=True)
class FixtureState:
    run_id: str
    retained_rows: int
    retained_evidence: int
    legacy_rows: int
    ledger_rows: int
    missing_rows: tuple[int, ...]
    writer_mode: str
    completion_present: bool
    projection_scanned_rows: int | None
    cursor_present: bool
    metadata_digest: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "retained_rows": self.retained_rows,
            "retained_evidence": self.retained_evidence,
            "legacy_rows": self.legacy_rows,
            "ledger_rows": self.ledger_rows,
            "missing_rows": list(self.missing_rows),
            "writer_mode": self.writer_mode,
            "completion_present": self.completion_present,
            "projection_scanned_rows": self.projection_scanned_rows,
            "cursor_present": self.cursor_present,
            "metadata_digest": self.metadata_digest,
        }


def inspect_fixture(db_client: Any, *, run_id: str, allow_ledger: bool = True) -> FixtureState:
    """Read only the named fixture's metadata and content-free proof documents."""

    validate_target()
    run_id = validate_run_id(run_id)
    control = _assert_apply_control(db_client, allow_ledger=allow_ledger)
    _assert_fixture_exclusive(db_client, run_id=run_id)
    retained_rows = 0
    retained_evidence = 0
    legacy_rows = 0
    ledger_rows = 0
    missing_rows: list[int] = []
    digest_rows: list[dict[str, Any]] = []

    for index in range(ROW_COUNT):
        item_payload = _get_selected(
            db_client.document(_memory_path(run_id, index)),
            (
                "memory_id",
                "uid",
                "jit_qa_fixture",
                "jit_qa_run_id",
                "jit_qa_row",
                "promotion",
                "ledger_schema_version",
                "status",
                "write_reason",
                "slot",
                "item_revision",
                "ledger_sequence",
                "content_hash",
            ),
        )
        if not item_payload:
            missing_rows.append(index)
            continue
        if not _owned_fields_match(item_payload, run_id=run_id, index=index):
            raise JITQAVerificationError(f"fixture row {index:03d} is missing or has a foreign owner marker")
        retained_rows += 1
        schema = item_payload.get("ledger_schema_version")
        if schema == LEDGER_SCHEMA_VERSION:
            ledger_rows += 1
        else:
            legacy_rows += 1
        digest_rows.append(
            {
                "id": item_payload.get("memory_id"),
                "uid": item_payload.get("uid"),
                "schema": schema,
                "status": item_payload.get("status"),
                "write_reason": item_payload.get("write_reason"),
                "slot": item_payload.get("slot"),
                "revision": item_payload.get("item_revision"),
                "sequence": item_payload.get("ledger_sequence"),
                "content_hash": item_payload.get("content_hash"),
            }
        )
        evidence_payload = _get_selected(
            db_client.document(_evidence_path(run_id, index)),
            EVIDENCE_OWNERSHIP_FIELDS,
        )
        if not evidence_payload:
            raise JITQAVerificationError(f"fixture evidence {index:03d} is missing")
        if _projected_evidence_fields(evidence_payload) != _expected_evidence_fields(run_id, index):
            raise JITQAVerificationError(f"fixture evidence {index:03d} is foreign or malformed")
        retained_evidence += 1

    completion = _get_selected(
        db_client.document(_completion_path()),
        ("schema_version", "status", "blocking_row_count", "source_head_commit_id", "writer_epoch"),
    )
    projection = _get_selected(
        db_client.document(_projection_path()),
        (
            "schema_version",
            "status",
            "uid",
            "source_head_commit_id",
            "writer_epoch",
            "legacy_row_count",
            "blocking_row_count",
            "scanned_row_count",
        ),
    )
    # A rollback intentionally leaves the old receipt documents in place while
    # the compatibility writer makes them non-authoritative. Validate their
    # fence only when ledger mode is active; the row/evidence digest is the
    # rollback preservation proof.
    if completion and control.get("writer_mode") == "ledger":
        if (
            completion.get("schema_version") != "knowledge_ledger.v1"
            or completion.get("status") != "complete"
            or completion.get("blocking_row_count") != 0
            or completion.get("source_head_commit_id") != control.get("head_commit_id")
            or completion.get("writer_epoch") != control.get("writer_epoch")
        ):
            raise JITQAVerificationError("ledger completion is malformed or stale against apply-control")
    if projection and control.get("writer_mode") == "ledger":
        if (
            projection.get("schema_version") != "knowledge_ledger_prompt_projection.v1"
            or projection.get("status") != "complete"
            or projection.get("uid") != QA_UID
            or projection.get("source_head_commit_id") != control.get("head_commit_id")
            or projection.get("writer_epoch") != control.get("writer_epoch")
            or projection.get("legacy_row_count") != 0
            or projection.get("blocking_row_count") != 0
        ):
            raise JITQAVerificationError("ledger prompt projection is malformed or stale against apply-control")
    cursor = _get_selected(db_client.document(LEDGER_DRAIN_CURSOR_PATH), ("schema_version", "generation", "last_path"))
    canonical = json.dumps(digest_rows, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    digest = hashlib.sha256(canonical).hexdigest()
    return FixtureState(
        run_id=run_id,
        retained_rows=retained_rows,
        retained_evidence=retained_evidence,
        legacy_rows=legacy_rows,
        ledger_rows=ledger_rows,
        missing_rows=tuple(missing_rows),
        writer_mode=str(control.get("writer_mode")),
        completion_present=bool(completion),
        projection_scanned_rows=(
            int(projection["scanned_row_count"]) if isinstance(projection.get("scanned_row_count"), int) else None
        ),
        cursor_present=bool(cursor),
        metadata_digest=digest,
    )


def _summary_payload(raw: Mapping[str, Any]) -> Mapping[str, Any]:
    candidate = raw.get("summary") if isinstance(raw.get("summary"), Mapping) else raw
    if not isinstance(candidate, Mapping):
        raise JITQAVerificationError("drain summary must contain an object")
    missing = [key for key in SUMMARY_KEYS if key not in candidate]
    if missing:
        raise JITQAVerificationError(f"drain summary is missing fields: {missing}")
    if not isinstance(candidate.get("errors"), list):
        raise JITQAVerificationError("drain summary errors must be a list")
    return candidate


def load_summary(path: Path) -> Mapping[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise JITQAVerificationError(f"could not read drain summary {path}") from exc
    if not isinstance(raw, Mapping):
        raise JITQAVerificationError("drain summary file must contain a JSON object")
    return _summary_payload(raw)


def _assert_summary(summary: Mapping[str, Any], expected: Mapping[str, Any], *, phase: str) -> None:
    if summary.get("errors"):
        raise JITQAVerificationError(f"{phase} drain reported errors")
    for key, value in expected.items():
        if summary.get(key) != value:
            raise JITQAVerificationError(f"{phase} drain {key}={summary.get(key)!r}; expected {value!r}")


def verify_bounded_progress(
    db_client: Any,
    *,
    run_id: str,
    first_summary: Mapping[str, Any],
    second_summary: Mapping[str, Any],
    retry_summary: Mapping[str, Any],
) -> dict[str, Any]:
    """Verify the two page summaries and the durable post-cutover state."""

    _assert_summary(
        first_summary,
        {
            "inventoried_users": 1,
            "scanned_documents": 1,
            "attempted_users": 1,
            "allowlist_blocked_users": 0,
            "rollout_blocked_users": 0,
            "authorization_revoked_users": 0,
            "remaining_users": 1,
            "cutover_users": 0,
            "migrated_rows": 100,
        },
        phase="first",
    )
    _assert_summary(
        second_summary,
        {
            "inventoried_users": 1,
            "scanned_documents": 1,
            "attempted_users": 1,
            "allowlist_blocked_users": 0,
            "rollout_blocked_users": 0,
            "authorization_revoked_users": 0,
            "remaining_users": 0,
            "cutover_users": 1,
            "migrated_rows": 1,
        },
        phase="second",
    )
    _assert_summary(
        retry_summary,
        {
            "inventoried_users": 0,
            "scanned_documents": 1,
            "attempted_users": 0,
            "allowlist_blocked_users": 0,
            "rollout_blocked_users": 0,
            "authorization_revoked_users": 0,
            "remaining_users": 0,
            "cutover_users": 0,
            "migrated_rows": 0,
        },
        phase="retry",
    )
    state = inspect_fixture(db_client, run_id=run_id, allow_ledger=True)
    if state.retained_rows != ROW_COUNT or state.retained_evidence != ROW_COUNT:
        raise JITQAVerificationError("bounded drain did not retain all 101 owned rows and evidence documents")
    if state.legacy_rows != 0 or state.ledger_rows != ROW_COUNT:
        raise JITQAVerificationError("bounded drain did not complete all 101 ledger rows")
    if state.writer_mode != "ledger" or not state.completion_present:
        raise JITQAVerificationError("bounded drain did not publish the fenced completion")
    if state.projection_scanned_rows != ROW_COUNT:
        raise JITQAVerificationError("prompt projection did not scan all 101 rows")
    if state.cursor_present:
        raise JITQAVerificationError("allowlisted QA proof unexpectedly wrote the global drain cursor")
    return {
        "result": "PASS",
        "run_id": run_id,
        "retained_rows": ROW_COUNT,
        "bounded_pages": [100, 1],
        "stable_retry": "no-op",
        "rollback": "pending",
        "rollforward": "pending",
        "metadata_digest": state.metadata_digest,
        "authority_boundary": "real QA job summaries; no injected admission",
    }


def rollback_fixture(db_client: Any, *, run_id: str, confirmation: str) -> dict[str, Any]:
    """Exercise the explicit control-plane rollback after a successful proof.

    This is a separate, opt-in operation.  It does not rewrite rows, evidence,
    or content.  The CLI requires the literal ``ROLLBACK_QA`` confirmation.
    """

    if confirmation != "ROLLBACK_QA":
        raise JITQAVerificationError("rollback requires --confirmation ROLLBACK_QA")
    before = inspect_fixture(db_client, run_id=run_id, allow_ledger=True)
    if before.retained_rows != ROW_COUNT or before.ledger_rows != ROW_COUNT or before.writer_mode != "ledger":
        raise JITQAVerificationError("rollback requires the completed 101-row ledger proof")
    control = rollback_ledger_writer_to_compatibility(
        QA_UID,
        db_client=db_client,
        rollback_authorizer=lambda: True,
    )
    after = inspect_fixture(db_client, run_id=run_id, allow_ledger=False)
    if after.writer_mode != "compatibility" or after.metadata_digest != before.metadata_digest:
        raise JITQAVerificationError("rollback changed row state or did not return compatibility mode")
    return {
        "result": "PASS",
        "run_id": run_id,
        "writer_mode": str(getattr(control.writer_mode, "value", control.writer_mode)),
        "retained_rows": after.retained_rows,
        "retained_evidence": after.retained_evidence,
        "metadata_digest": after.metadata_digest,
        "completion_authority": "hidden while compatibility mode is active",
    }


def _load_args_summary(path: Path) -> Mapping[str, Any]:
    return load_summary(path)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", help="lowercase synthetic fixture namespace")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("bootstrap", help="create the fixed QA profile in an empty QA user plane")
    sub.add_parser("prepare", help="preflight and create missing owned synthetic rows")
    sub.add_parser("inspect", help="read content-free fixture metadata")
    verify = sub.add_parser("verify", help="verify first, second, and stable retry drain summaries")
    verify.add_argument("--first-summary", type=Path, required=True)
    verify.add_argument("--second-summary", type=Path, required=True)
    verify.add_argument("--retry-summary", type=Path, required=True)
    rollback = sub.add_parser("rollback", help="explicitly rollback the writer control plane after proof")
    rollback.add_argument("--confirmation", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command != "bootstrap" and not args.run_id:
        raise JITQAVerificationError("--run-id is required for prepare, inspect, verify, and rollback")
    if args.run_id:
        validate_run_id(args.run_id)
    validate_environment()
    db_client = build_firestore_client()
    if args.command == "bootstrap":
        print(json.dumps(bootstrap_qa_account(db_client), sort_keys=True))
    elif args.command == "prepare":
        print(json.dumps(seed_fixture(db_client, run_id=args.run_id), sort_keys=True))
    elif args.command == "inspect":
        print(json.dumps(inspect_fixture(db_client, run_id=args.run_id).as_dict(), sort_keys=True))
    elif args.command == "verify":
        result = verify_bounded_progress(
            db_client,
            run_id=args.run_id,
            first_summary=_load_args_summary(args.first_summary),
            second_summary=_load_args_summary(args.second_summary),
            retry_summary=_load_args_summary(args.retry_summary),
        )
        print(json.dumps(result, sort_keys=True))
    elif args.command == "rollback":
        result = rollback_fixture(db_client, run_id=args.run_id, confirmation=args.confirmation)
        print(json.dumps(result, sort_keys=True))
    else:  # pragma: no cover - argparse enforces command choices.
        raise JITQAVerificationError(f"unknown command {args.command}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except JITQAVerificationError as exc:
        print(f"JIT QA operator refused: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
