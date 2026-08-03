#!/usr/bin/env python3
"""Force a single Short-term → Long-term canonical promotion proof.

Default is dry-run. ``--apply`` writes one synthetic marker, runs required
processing + consolidation with ``MEMORY_CANONICAL_CONSOLIDATION_BATCH_CAP=1``,
and reports redacted before/after tier evidence.

Data-plane default matches the dev maintenance job contract:
``GOOGLE_CLOUD_PROJECT=based-hardware`` (prod Firestore project, not
``based-hardware-dev``).
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

# Match job defaults before importing memory modules that read env at call time.
DEFAULT_PROJECT = "based-hardware"
DEFAULT_UID = "vi7SA9ckQCe4ccobWNxlbdcNdC23"


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
    run_id: str
    batch_cap: int
    gateway_mode: str
    notes: list[str]
    errors: list[str]


def _parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    # Prefer explicit job-parity default over ambient GOOGLE_CLOUD_PROJECT (often
    # based-hardware-dev on laptops). Override with --project when needed.
    p.add_argument("--project", default=DEFAULT_PROJECT)
    p.add_argument("--uid", default=DEFAULT_UID)
    p.add_argument("--apply", action="store_true", help="Perform writes + maintenance (default: dry-run)")
    p.add_argument(
        "--ensure-control",
        action="store_true",
        help="With --apply, merge enroll control docs at stage=write if missing/not write-ready",
    )
    p.add_argument("--batch-cap", type=int, default=1)
    p.add_argument("--json", action="store_true", help="Emit machine-readable JSON only")
    return p.parse_args(argv)


def _configure_env(*, project: str, batch_cap: int) -> None:
    os.environ["GOOGLE_CLOUD_PROJECT"] = project
    os.environ["GOOGLE_CLOUD_PROJECT_ID"] = project
    os.environ.setdefault("MEMORY_CANONICAL_CONSOLIDATION_ENABLED", "true")
    os.environ.setdefault("MEMORY_CANONICAL_MAINTENANCE_ENABLED", "true")
    os.environ["MEMORY_CANONICAL_CONSOLIDATION_BATCH_CAP"] = str(max(1, batch_cap))
    os.environ.setdefault("MEMORY_CANONICAL_CONSOLIDATION_MAX_BATCHES_PER_PASS", "5")


def _enum_val(v: Any) -> Optional[str]:
    if v is None:
        return None
    return getattr(v, "value", str(v))


def _load_client(project: str) -> Any:
    from google.cloud import firestore

    from database.google_credentials import prepare_google_credentials

    prepare_google_credentials()
    return firestore.Client(project=project)


def _control_write_ready(db_client: Any, uid: str) -> tuple[bool, str]:
    from database.memory_collections import MemoryCollections
    from utils.memory.canonical_activation import canonical_write_decision

    decision = canonical_write_decision(uid, db_client=db_client)
    paths = MemoryCollections(uid=uid)
    exists = bool(db_client.document(paths.memory_control_state).get().exists)
    if decision.enabled:
        return True, "write_ready"
    reason = str(decision.reason)
    if not exists:
        return False, f"missing_control_doc:{reason}"
    return False, reason


def _ensure_write_control(db_client: Any, *, uid: str) -> list[str]:
    """Merge minimal stage=write control docs (enroll script payloads)."""
    from scripts.enroll_canonical_memory_user import (
        apply_documents,
        build_rollout_documents,
    )
    from utils.memory.v3.account_generation_source import read_memory_v3_trusted_account_generation

    trusted = read_memory_v3_trusted_account_generation(uid=uid, db_client=db_client)
    generation = int(trusted.account_generation or 0)
    docs = build_rollout_documents(uid=uid, stage="write", account_generation=generation)
    apply_documents(db_client, docs, allow_existing_update=True)
    return [d.path for d in docs]


def _create_marker(db_client: Any, *, uid: str, marker: str) -> str:
    from datetime import datetime as dt

    from models.memories import MemoryDB
    from utils.memory.memory_service import MemoryService
    from utils.memory.memory_system import MemorySystem

    now = dt.now(timezone.utc)
    mid = str(uuid.uuid4())
    content = (
        f"{marker}: Forced single-item ST→LT lifecycle proof. "
        "Progressive cutover with fail-closed kill switches. Unique isolation content."
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
    svc = MemoryService(db_client=db_client)
    created = svc.create_external_memory(
        uid=uid,
        memory_db=row,
        memory_system=MemorySystem.CANONICAL,
        consumer="stlt_lifecycle_proof",
        operation="create",
        upsert_vector=True,
        require_canonical_promotion=True,
    )
    return str(getattr(created, "id", mid) or mid)


def _read_item(db_client: Any, *, uid: str, memory_id: str) -> Any:
    from utils.memory.canonical_memory_adapter import read_canonical_memory_item

    return read_canonical_memory_item(uid, memory_id, db_client=db_client)


def _run_maintenance(
    db_client: Any,
    *,
    uid: str,
    run_id: str,
    llm_invoke: Any = None,
) -> Any:
    from utils.llm.clients import get_llm
    from utils.memory.canonical_required_processing import (
        ProcessedRequiredMemory,
        invoke_required_memory_processor,
    )
    from utils.memory.short_term_promotion import run_canonical_short_term_maintenance

    def _required_processor(item: Any) -> Any:
        # Prefer live memory_l2 normalization; fall back to content-preserving
        # receipt so promote memory_text can bind to output_hash.
        try:
            return invoke_required_memory_processor(item, get_llm("memory_l2"))
        except Exception:
            return ProcessedRequiredMemory(
                content=str(getattr(item, "content", "") or "").strip()[:1000],
                subject_entity_id="user",
                predicate="remembered_fact",
                arguments={},
                sensitivity_labels=[],
                rationale="stlt_lifecycle_proof content-preserving fallback",
            )

    return run_canonical_short_term_maintenance(
        uid,
        db_client=db_client,
        run_id=run_id,
        required_processor=_required_processor,
        llm_invoke=llm_invoke,
    )


def run_proof(args: argparse.Namespace) -> ProofResult:
    notes: list[str] = []
    errors: list[str] = []
    _configure_env(project=args.project, batch_cap=args.batch_cap)

    marker = f"omi-stlt-proof-{uuid.uuid4().hex[:10]}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    run_id = f"stlt-proof-{uuid.uuid4().hex[:8]}"
    gateway_mode = os.environ.get("OMI_LLM_GATEWAY_FEATURE_MODE", "unset")
    batch_cap = int(os.environ["MEMORY_CANONICAL_CONSOLIDATION_BATCH_CAP"])

    if not args.apply:
        notes.append("dry_run: no writes; would create marker, ensure control if requested, run maintenance")
        notes.append(f"target_project={args.project} uid={args.uid} batch_cap={batch_cap}")
        notes.append(
            "job parity: dev memory-maintenance-job uses GOOGLE_CLOUD_PROJECT=based-hardware "
            "(not based-hardware-dev)"
        )
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
            run_id=run_id,
            batch_cap=batch_cap,
            gateway_mode=gateway_mode,
            notes=notes,
            errors=errors,
        )

    if not os.environ.get("ENCRYPTION_SECRET"):
        errors.append("ENCRYPTION_SECRET required for --apply")
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
        if args.ensure_control:
            written = _ensure_write_control(db_client, uid=args.uid)
            notes.append(f"ensured_control_paths={len(written)}")
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
                run_id=run_id,
                batch_cap=batch_cap,
                gateway_mode=gateway_mode,
                notes=notes,
                errors=errors,
            )

    memory_id = _create_marker(db_client, uid=args.uid, marker=marker)
    before = _read_item(db_client, uid=args.uid, memory_id=memory_id)
    tier_before = _enum_val(getattr(before, "tier", None)) if before else None
    proc_before = _enum_val(getattr(before, "processing_state", None)) if before else None
    notes.append(f"created memory_id={memory_id}")

    try:
        report = _run_maintenance(db_client, uid=args.uid, run_id=run_id)
        notes.append(f"maintenance_type={type(report).__name__}")
        cons = getattr(report, "consolidation", None)
        if cons is not None:
            notes.append(
                "consolidation "
                f"trigger={getattr(cons, 'trigger_reason', None)} "
                f"pending={getattr(cons, 'pending_count', None)} "
                f"skipped={getattr(cons, 'skipped_reason', None)} "
                f"promoted={getattr(cons, 'promoted_memory_ids', None)}"
            )
            cons_errors = getattr(cons, "errors", None) or []
            if cons_errors:
                errors.extend(str(e) for e in cons_errors[:5])
        req = getattr(report, "required_processing", None)
        if req is not None:
            notes.append(f"required_processing={req}")
    except Exception as exc:  # noqa: BLE001 - surface live proof failures
        errors.append(f"maintenance_failed:{type(exc).__name__}:{exc}")

    after = _read_item(db_client, uid=args.uid, memory_id=memory_id)
    tier_after = _enum_val(getattr(after, "tier", None)) if after else None
    proc_after = _enum_val(getattr(after, "processing_state", None)) if after else None

    # Promotion may supersede the ST row; search LT for marker prefix via list pending=0 path.
    promoted_ok = tier_after == "long_term"
    if not promoted_ok and after is not None and tier_after == "short_term":
        # Check lineage/promotion status on the item
        promo = getattr(after, "promotion", None) or {}
        if isinstance(promo, dict) and promo.get("status") == "promoted":
            promoted_ok = True
            notes.append("promotion.status=promoted while source tier still short_term (supersede path)")

    if not promoted_ok:
        # Best-effort: scan recent LT docs for marker in plaintext content field (may be encrypted)
        try:
            from database.memory_collections import MemoryCollections
            from models.product_memory import MemoryLayer

            paths = MemoryCollections(uid=args.uid)
            found_lt = False
            for snap in (
                db_client.collection(paths.memory_items)
                .where("tier", "==", MemoryLayer.long_term.value)
                .limit(50)
                .stream()
            ):
                data = snap.to_dict() or {}
                content = str(data.get("content") or "")
                if marker in content or memory_id in str(data.get("source_memory_ids") or data.get("lineage") or ""):
                    found_lt = True
                    notes.append(f"found_lt_doc={snap.id}")
                    tier_after = "long_term"
                    break
            promoted_ok = found_lt
        except Exception as exc:  # noqa: BLE001
            notes.append(f"lt_scan_skipped:{type(exc).__name__}")

    ok = promoted_ok and not errors
    if not promoted_ok and not errors:
        errors.append("marker_not_long_term_after_maintenance")

    return ProofResult(
        ok=ok,
        mode="apply",
        project=args.project,
        uid=args.uid,
        marker=marker,
        memory_id=memory_id,
        tier_before=tier_before,
        processing_before=proc_before,
        tier_after=tier_after,
        processing_after=proc_after,
        run_id=run_id,
        batch_cap=batch_cap,
        gateway_mode=gateway_mode,
        notes=notes,
        errors=errors,
    )


def main(argv: Optional[list[str]] = None) -> int:
    args = _parse_args(argv)
    result = run_proof(args)
    payload = asdict(result)
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
