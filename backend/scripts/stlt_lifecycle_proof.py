#!/usr/bin/env python3
# LIFECYCLE: permanent
"""Force a single Short-term → Long-term canonical promotion proof.

Dry-run is the default. ``--apply`` requires explicit ``--uid``, ``--project``,
and ``--confirm-data-plane``, then:

1. optionally repairs only the *user* control doc (never global read gate)
2. creates one synthetic ST marker
3. runs required processing for that memory id only
4. applies one item-scoped promote decision (does not drain the user's queue)
5. requires ST→processed before and long_term after

Data-plane note: the dev ``memory-maintenance-job`` uses
``GOOGLE_CLOUD_PROJECT=based-hardware`` (not ``based-hardware-dev``).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

DEFAULT_PROJECT = "based-hardware"
DEFAULT_UID = "vi7SA9ckQCe4ccobWNxlbdcNdC23"
MAINTENANCE_ENABLED_ENV = "MEMORY_CANONICAL_MAINTENANCE_ENABLED"
CONSOLIDATION_ENABLED_ENV = "MEMORY_CANONICAL_CONSOLIDATION_ENABLED"
BATCH_CAP_ENV = "MEMORY_CANONICAL_CONSOLIDATION_BATCH_CAP"


@dataclass(frozen=True)
class ProofResult:
    ok: bool
    mode: str
    project: str
    uid: str
    marker: str
    memory_id: str
    tier_before: Optional[str]
    processing_before: Optional[str]
    tier_after: Optional[str]
    processing_after: Optional[str]
    status_after: Optional[str]
    run_id: str
    batch_cap: int
    gateway_mode: str
    notes: list[str]
    errors: list[str]


def _parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--project",
        default=DEFAULT_PROJECT,
        help=f"Firestore project (default {DEFAULT_PROJECT}; job-parity)",
    )
    p.add_argument(
        "--uid",
        default=DEFAULT_UID,
        help="Target UID (dry-run default is dogfood; --apply requires --confirm-data-plane)",
    )
    p.add_argument("--apply", action="store_true", help="Perform writes (default: dry-run)")
    p.add_argument(
        "--confirm-data-plane",
        action="store_true",
        help="Required with --apply: acknowledge writes to --project/--uid",
    )
    p.add_argument(
        "--ensure-user-control",
        action="store_true",
        help="With --apply, merge only users/{uid}/memory_control/state at stage=write if not write-ready",
    )
    p.add_argument(
        "--allow-direct-llm",
        action="store_true",
        help="Allow OMI_LLM_GATEWAY_FEATURE_MODE!=gateway (laptop proofs only)",
    )
    p.add_argument("--json", action="store_true", help="Emit JSON only")
    return p.parse_args(argv)


def _enum_val(value: Any) -> Optional[str]:
    if value is None:
        return None
    return str(getattr(value, "value", value))


def _safe_error(exc: BaseException) -> str:
    """Bounded non-content failure label for proof JSON."""
    name = type(exc).__name__
    return f"{name}"


def _configure_env(*, project: str) -> None:
    os.environ["GOOGLE_CLOUD_PROJECT"] = project
    os.environ["GOOGLE_CLOUD_PROJECT_ID"] = project
    # Force single-item canary isolation for this harness.
    os.environ[BATCH_CAP_ENV] = "1"
    os.environ.setdefault(CONSOLIDATION_ENABLED_ENV, "true")
    os.environ.setdefault(MAINTENANCE_ENABLED_ENV, "true")


def _preflight_imports() -> None:
    """Import apply-path modules before any write."""
    import utils.llm.clients as _llm_clients
    import utils.memory.canonical_consolidation as _cons
    import utils.memory.canonical_required_processing as _req
    import utils.memory.memory_service as _msvc

    assert hasattr(_llm_clients, "get_llm")
    assert hasattr(_cons, "apply_consolidation_decision")
    assert hasattr(_req, "process_required_memory_item")
    assert hasattr(_msvc, "MemoryService")


def _load_client(project: str) -> Any:
    from google.cloud import firestore

    from database.google_credentials import prepare_google_credentials

    prepare_google_credentials()
    return firestore.Client(project=project)


def _control_write_ready(db_client: Any, uid: str) -> tuple[bool, str]:
    from utils.memory.canonical_activation import canonical_write_decision

    decision = canonical_write_decision(uid, db_client=db_client)
    if decision.enabled:
        return True, "write_ready"
    return False, str(decision.reason)


def _ensure_user_control_only(db_client: Any, *, uid: str) -> list[str]:
    """Merge only the per-user control doc; never touch global read/write gates."""
    from database.memory_collections import MemoryCollections
    from scripts.enroll_canonical_memory_user import build_user_control_state
    from utils.memory.v3.account_generation_source import read_memory_v3_trusted_account_generation

    trusted = read_memory_v3_trusted_account_generation(uid=uid, db_client=db_client)
    if trusted.read_error_reason is not None or trusted.account_generation is None:
        raise RuntimeError(f"trusted_generation_unavailable:{trusted.read_error_reason or 'missing'}")
    generation = int(trusted.account_generation)
    path = MemoryCollections(uid=uid).memory_control_state
    payload = build_user_control_state(uid=uid, stage="write", account_generation=generation)
    db_client.document(path).set(payload, merge=True)
    return [path]


def _create_marker(db_client: Any, *, uid: str, marker: str) -> str:
    from models.memories import MemoryDB
    from utils.memory.memory_service import MemoryService
    from utils.memory.memory_system import MemorySystem

    now = datetime.now(timezone.utc)
    mid = str(uuid.uuid4())
    content = (
        f"{marker}: David prefers progressive Omi canonical-memory cutover: "
        "dark deploy, then David canary, then staff ring, then budgeted stage-all. "
        "He rejects all-users GA in one flip."
    )
    row = MemoryDB(
        id=mid,
        uid=uid,
        content=content,
        category="interesting",
        manually_added=True,
        created_at=now,
        updated_at=now,
        scoring="high",
        app_id=None,
        conversation_id=None,
        is_locked=False,
    )
    created = MemoryService(db_client=db_client).create_external_memory(
        uid=uid,
        memory_db=row,
        memory_system=MemorySystem.CANONICAL,
        consumer="stlt_lifecycle_proof",
        operation="create",
        upsert_vector=False,
        require_canonical_promotion=True,
    )
    return str(getattr(created, "id", mid) or mid)


def _read_item(db_client: Any, *, uid: str, memory_id: str) -> Any:
    from utils.memory.canonical_memory_adapter import read_canonical_memory_item

    return read_canonical_memory_item(uid, memory_id, db_client=db_client)


def _process_one(db_client: Any, *, uid: str, memory_id: str) -> Any:
    from utils.llm.clients import get_llm
    from utils.memory.canonical_required_processing import (
        invoke_required_memory_processor,
        process_required_memory_item,
    )

    def processor(item: Any) -> Any:
        # No silent fabricate-on-failure: surface L2 errors to the proof result.
        return invoke_required_memory_processor(item, get_llm("memory_l2"))

    return process_required_memory_item(uid, memory_id, db_client=db_client, processor=processor)


def _promote_one(db_client: Any, *, uid: str, memory_id: str, run_id: str) -> list[str]:
    """Item-scoped promote; does not drain other pending ST rows."""
    import utils.memory.canonical_consolidation as consolidation_mod
    from utils.memory.canonical_consolidation import (
        ConsolidationAgentDecision,
        apply_consolidation_decision,
    )

    read_control_state = getattr(consolidation_mod, "_read_control_state")
    item = _read_item(db_client, uid=uid, memory_id=memory_id)
    if item is None:
        raise RuntimeError("memory_missing_after_processing")
    evidence_ids = [str(e.evidence_id) for e in (item.evidence or []) if getattr(e, "evidence_id", None)]
    if not evidence_ids:
        raise RuntimeError("missing_evidence_ids")
    # Receipt binds sha256(promote memory_text) to processed ST content.
    decision = ConsolidationAgentDecision(
        source_memory_id=memory_id,
        route="promote",
        reconciliation="create",
        memory_text=str(item.content or ""),
        evidence_ids=evidence_ids,
        subject_entity_id="user",
        predicate="prefers_progressive_memory_rollout",
        arguments={"topic": "canonical_memory_cutover"},
        relationship_to_user="self",
        aboutness="primary_user",
        basis_for_memory="explicit",
        confidence="high",
        rationale="stlt_lifecycle_proof item-scoped promote; memory_text matches processed content",
    )
    control = read_control_state(uid, db_client=db_client)
    return apply_consolidation_decision(
        uid,
        decision=decision,
        pending_by_id={memory_id: item},
        control=control,
        run_id=run_id,
        now=datetime.now(timezone.utc),
        db_client=db_client,
    )


def run_proof(args: argparse.Namespace) -> ProofResult:
    notes: list[str] = []
    errors: list[str] = []
    _configure_env(project=args.project)
    marker = f"omi-stlt-proof-{uuid.uuid4().hex[:10]}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    run_id = f"stlt-proof-{uuid.uuid4().hex[:8]}"
    gateway_mode = (os.environ.get("OMI_LLM_GATEWAY_FEATURE_MODE") or "unset").strip()
    batch_cap = 1

    if not args.apply:
        notes.append("dry_run: no writes")
        notes.append(f"target_project={args.project} uid={args.uid} batch_cap={batch_cap}")
        notes.append("job parity: dev memory-maintenance-job uses GOOGLE_CLOUD_PROJECT=based-hardware")
        return ProofResult(
            ok=True,
            mode="dry_run",
            project=args.project,
            uid=args.uid,
            marker=marker,
            memory_id="",
            tier_before=None,
            processing_before=None,
            tier_after=None,
            processing_after=None,
            status_after=None,
            run_id=run_id,
            batch_cap=batch_cap,
            gateway_mode=gateway_mode,
            notes=notes,
            errors=errors,
        )

    if not args.confirm_data_plane:
        errors.append("apply_requires_--confirm-data-plane")
    if not args.uid or not args.project:
        errors.append("apply_requires_explicit_uid_and_project")
    if os.environ.get(MAINTENANCE_ENABLED_ENV, "true").lower() == "false":
        errors.append("MEMORY_CANONICAL_MAINTENANCE_ENABLED=false")
    if os.environ.get(CONSOLIDATION_ENABLED_ENV, "true").lower() == "false":
        errors.append("MEMORY_CANONICAL_CONSOLIDATION_ENABLED=false")
    if gateway_mode != "gateway" and not args.allow_direct_llm:
        errors.append("require_OMI_LLM_GATEWAY_FEATURE_MODE=gateway_or_--allow-direct-llm")
    if not os.environ.get("ENCRYPTION_SECRET"):
        errors.append("ENCRYPTION_SECRET_required")
    if errors:
        return ProofResult(
            ok=False,
            mode="apply",
            project=args.project,
            uid=args.uid,
            marker=marker,
            memory_id="",
            tier_before=None,
            processing_before=None,
            tier_after=None,
            processing_after=None,
            status_after=None,
            run_id=run_id,
            batch_cap=batch_cap,
            gateway_mode=gateway_mode,
            notes=notes,
            errors=errors,
        )

    try:
        _preflight_imports()
    except Exception as exc:  # noqa: BLE001
        errors.append(f"preflight_import:{_safe_error(exc)}")
        return ProofResult(
            ok=False,
            mode="apply",
            project=args.project,
            uid=args.uid,
            marker=marker,
            memory_id="",
            tier_before=None,
            processing_before=None,
            tier_after=None,
            processing_after=None,
            status_after=None,
            run_id=run_id,
            batch_cap=batch_cap,
            gateway_mode=gateway_mode,
            notes=notes,
            errors=errors,
        )

    db_client = _load_client(args.project)
    ready, reason = _control_write_ready(db_client, args.uid)
    notes.append(f"control_before={reason}")
    if not ready:
        if args.ensure_user_control:
            try:
                written = _ensure_user_control_only(db_client, uid=args.uid)
                notes.append(f"ensured_user_control={written[0]}")
            except Exception as exc:  # noqa: BLE001
                errors.append(f"ensure_user_control:{_safe_error(exc)}")
                return ProofResult(
                    ok=False,
                    mode="apply",
                    project=args.project,
                    uid=args.uid,
                    marker=marker,
                    memory_id="",
                    tier_before=None,
                    processing_before=None,
                    tier_after=None,
                    processing_after=None,
                    status_after=None,
                    run_id=run_id,
                    batch_cap=batch_cap,
                    gateway_mode=gateway_mode,
                    notes=notes,
                    errors=errors,
                )
            ready, reason = _control_write_ready(db_client, args.uid)
            notes.append(f"control_after_ensure={reason}")
        if not ready:
            errors.append(f"canonical_write_not_ready:{reason}")
            return ProofResult(
                ok=False,
                mode="apply",
                project=args.project,
                uid=args.uid,
                marker=marker,
                memory_id="",
                tier_before=None,
                processing_before=None,
                tier_after=None,
                processing_after=None,
                status_after=None,
                run_id=run_id,
                batch_cap=batch_cap,
                gateway_mode=gateway_mode,
                notes=notes,
                errors=errors,
            )

    memory_id = ""
    tier_before = processing_before = tier_after = processing_after = status_after = None
    try:
        memory_id = _create_marker(db_client, uid=args.uid, marker=marker)
        before = _read_item(db_client, uid=args.uid, memory_id=memory_id)
        tier_before = _enum_val(getattr(before, "tier", None)) if before else None
        processing_before = _enum_val(getattr(before, "processing_state", None)) if before else None
        notes.append(f"created memory_id={memory_id}")
        if tier_before != "short_term":
            errors.append(f"expected_short_term_before got={tier_before}")

        proc = _process_one(db_client, uid=args.uid, memory_id=memory_id)
        notes.append(
            "required_processing "
            f"processed={getattr(proc, 'processed', None)} "
            f"skipped={getattr(proc, 'skipped_reason', None)} "
            f"error={getattr(proc, 'error_code', None)}"
        )
        if not getattr(proc, "processed", False):
            errors.append(
                "required_processing_failed:"
                f"{getattr(proc, 'skipped_reason', None) or getattr(proc, 'error_code', None) or 'unknown'}"
            )
        else:
            mid_state = _read_item(db_client, uid=args.uid, memory_id=memory_id)
            processing_before = (
                _enum_val(getattr(mid_state, "processing_state", None)) if mid_state else processing_before
            )
            if processing_before != "processed":
                errors.append(f"expected_processed_before_promote got={processing_before}")
            else:
                applied = _promote_one(db_client, uid=args.uid, memory_id=memory_id, run_id=run_id)
                notes.append(f"promote_applied={applied}")

        after = _read_item(db_client, uid=args.uid, memory_id=memory_id)
        tier_after = _enum_val(getattr(after, "tier", None)) if after else None
        processing_after = _enum_val(getattr(after, "processing_state", None)) if after else None
        status_after = _enum_val(getattr(after, "status", None)) if after else None
    except Exception as exc:  # noqa: BLE001
        errors.append(f"apply_path:{_safe_error(exc)}")

    lifecycle_ok = (
        tier_before == "short_term"
        and processing_before == "processed"
        and tier_after == "long_term"
        and status_after == "active"
        and not errors
    )
    if not lifecycle_ok and not errors:
        errors.append("st_to_lt_not_proven")

    return ProofResult(
        ok=lifecycle_ok,
        mode="apply",
        project=args.project,
        uid=args.uid,
        marker=marker,
        memory_id=memory_id,
        tier_before=tier_before,
        processing_before=processing_before,
        tier_after=tier_after,
        processing_after=processing_after,
        status_after=status_after,
        run_id=run_id,
        batch_cap=batch_cap,
        gateway_mode=gateway_mode,
        notes=notes,
        errors=errors,
    )


def main(argv: Optional[list[str]] = None) -> int:
    args = _parse_args(argv)
    result = run_proof(args)
    print(json.dumps(asdict(result), indent=2, sort_keys=True))
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
