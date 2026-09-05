#!/usr/bin/env python3
"""Seed and verify the bounded JIT QA ledger-drain proof.

This operator is deliberately narrower than the deployment workflow.  It owns
only a deterministic, synthetic fixture in the named ``jit-qa`` Firestore
database.  It never discovers or edits another account, never creates the
apply-control document, and never calls a model.  The Cloud Run workflow owns
job execution; this command consumes its content-free execution summaries.

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
from datetime import datetime, timezone
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
from utils.memory.knowledge_ledger import LEDGER_SCHEMA_VERSION  # noqa: E402
from utils.memory.knowledge_ledger_migration import (  # noqa: E402
    rollback_ledger_writer_to_compatibility,
)

PROJECT_ID = "based-hardware-dev"
DATABASE_ID = "jit-qa"
REGION = "us-central1"
QA_UID = "vi7SA9ckQCe4ccobWNxlbdcNdC23"
LEDGER_DRAIN_JOB = "knowledge-ledger-drain-qa-job"
FIXTURE_MARKER = "omi.jit.qa.seed-and-verify.v1"
ROW_COUNT = 101
MUTATION_PAGE_SIZE = 100
LEDGER_DRAIN_CURSOR_PATH = "knowledge_ledger_migration_control/inventory_cursor"
RUN_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,47}$")
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
        # Lightweight unit fakes use point reads only.  The real Firestore
        # client always exposes collection().
        return
    collection = collection_factory(f"users/{QA_UID}/memory_items")
    selector = getattr(collection, "select", None)
    if callable(selector):
        collection = selector(["memory_id", "uid", "jit_qa_fixture", "jit_qa_run_id", "jit_qa_row"])
    stream = getattr(collection, "stream", None)
    if not callable(stream):
        raise JITQAVerificationError("QA Firestore client cannot prove fixture exclusivity")
    expected_ids = {f"jitqa-{run_id}-legacy-{index:03d}" for index in range(ROW_COUNT)}
    foreign_ids: list[str] = []
    for snapshot in stream():
        snapshot_id = str(getattr(snapshot, "id", ""))
        payload = _as_dict(snapshot)
        if snapshot_id not in expected_ids or not _owned_fields_match(
            payload,
            run_id=run_id,
            index=int(payload.get("jit_qa_row", -1)) if str(payload.get("jit_qa_row", "")).isdigit() else -1,
        ):
            foreign_ids.append(snapshot_id or "<missing-id>")
    if foreign_ids:
        raise JITQAVerificationError(
            "QA account contains pre-existing or foreign memory rows; refusing to migrate shared state"
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
        predicate="resides_in" if index == 0 else "likes",
    )
    # These are the exact fields used to prove ownership without reading the
    # synthetic content back.  They are ignored by MemoryItem validation.
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
    return (
        payload.get("jit_qa_fixture") == FIXTURE_MARKER
        and payload.get("jit_qa_run_id") == run_id
        and payload.get("jit_qa_row") == index
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
            ("memory_id", "uid", "jit_qa_fixture", "jit_qa_run_id", "jit_qa_row", "ledger_schema_version"),
        )
        if existing:
            if not _owned_fields_match(existing, run_id=run_id, index=index):
                raise JITQAVerificationError(f"refusing to overwrite non-owned QA row {index:03d}")
            existing_rows += 1
            continue

        evidence_ref = db_client.document(_evidence_path(run_id, index))
        evidence = _get_selected(evidence_ref, ("evidence_id", "source_id", "source_state", "source_type"))
        expected_evidence = _stored_model(_fixture_evidence(run_id, index))
        if evidence and evidence != {
            key: expected_evidence.get(key) for key in ("evidence_id", "source_id", "source_state", "source_type")
        }:
            raise JITQAVerificationError(f"refusing to overwrite non-owned QA evidence {index:03d}")
        if not evidence:
            evidence_ref.set(expected_evidence)
        memory_ref.set(expected)
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
            ("evidence_id", "source_id", "source_state", "source_type"),
        )
        if evidence_payload:
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
    parser.add_argument("--run-id", required=True, help="lowercase synthetic fixture namespace")
    sub = parser.add_subparsers(dest="command", required=True)
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
    validate_run_id(args.run_id)
    validate_environment()
    db_client = build_firestore_client()
    if args.command == "prepare":
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
