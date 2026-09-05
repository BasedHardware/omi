#!/usr/bin/env python3
"""Real Firestore-emulator proof for the isolated JIT QA operator.

This is deliberately labelled unit proof: rollout admission is injected so the
test never calls a production flag service.  It exercises the same operator,
canonical apply helper, migration sweep, cutover publication, and rollback
against a real Firestore emulator.  The named-cloud operator still requires
real rollout admission and never accepts this injected result as cloud proof.
"""

from __future__ import annotations

import asyncio
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from google.cloud import firestore

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
os.environ.setdefault("ENCRYPTION_SECRET", "omi_jit_qa_emulator_key_32_bytes")  # pragma: allowlist secret
# Canonical migration is fenced by the deployment intake mode.  This local
# proof opts into write mode only inside the emulator process; cloud operators
# still read the real deployment environment and admission decision.
os.environ.setdefault("MEMORY_MODE", "write")

from models.memory_apply import WriterMode  # noqa: E402
from scripts import jit_qa_seed_and_verify as operator  # noqa: E402
from utils.memory import knowledge_ledger_drain as drain  # noqa: E402

PROJECT_ID = "demo-omi-jit-qa"
DATABASE_ID = "jit-qa"
NOW = datetime(2026, 9, 5, 12, tzinfo=timezone.utc)


async def _permit_injected_rollout(*_args: Any, **_kwargs: Any) -> Any:
    return SimpleNamespace(permits_work=True)


def _validate_emulator_host(value: str) -> None:
    host, separator, port = value.rpartition(":")
    if not separator or host not in {"127.0.0.1", "localhost", "::1"} or not port.isdigit():
        raise RuntimeError("FIRESTORE_EMULATOR_HOST must be a loopback host with a numeric port")


def _build_emulator_client() -> Any:
    return firestore.Client(project=PROJECT_ID, database=DATABASE_ID)


def _summary_payload(summary: Any) -> dict[str, Any]:
    return {
        "inventoried_users": summary.inventoried_users,
        "scanned_documents": summary.scanned_documents,
        "attempted_users": summary.attempted_users,
        "allowlist_blocked_users": summary.allowlist_blocked_users,
        "rollout_blocked_users": summary.rollout_blocked_users,
        "authorization_revoked_users": summary.authorization_revoked_users,
        "remaining_users": summary.remaining_users,
        "cutover_users": summary.cutover_users,
        "migrated_rows": summary.migrated_rows,
        "errors": list(summary.errors),
    }


def main() -> int:
    emulator_host = os.environ.get("FIRESTORE_EMULATOR_HOST", "").strip()
    if not emulator_host:
        raise RuntimeError("FIRESTORE_EMULATOR_HOST is required; run through firebase emulators:exec")
    _validate_emulator_host(emulator_host)
    client: Any = _build_emulator_client()
    # The operator's production entrypoint rejects emulators.  This test calls
    # the explicit bootstrap function under a labelled local override so cloud
    # mode remains fail-closed and real-admission-only.
    operator.validate_environment = lambda: None
    operator.validate_target()
    drain.resolve_jit_rollout = _permit_injected_rollout

    bootstrapped = operator.bootstrap_qa_account(client)
    if bootstrapped["apply_control_writer_mode"] != WriterMode.compatibility.value:
        raise AssertionError("bootstrap did not create canonical compatibility control")
    seeded = operator.seed_fixture(client, run_id="emulator-proof-20260905")
    if seeded["created_rows"] != operator.ROW_COUNT:
        raise AssertionError(f"unexpected emulator seed result: {seeded}")

    first = asyncio.run(
        drain.run_knowledge_ledger_drain(
            db_client=client,
            now=NOW,
            uid_allowlist=[operator.QA_UID],
        )
    )
    second = asyncio.run(
        drain.run_knowledge_ledger_drain(
            db_client=client,
            now=NOW,
            uid_allowlist=[operator.QA_UID],
        )
    )
    first_payload = _summary_payload(first)
    second_payload = _summary_payload(second)
    if first.migrated_rows != 100 or first.remaining_users != 1 or first.cutover_users != 0:
        raise AssertionError(f"emulator first page did not prove 100 + 1 progress: {first_payload}")
    if second.migrated_rows != 1 or second.remaining_users != 0 or second.cutover_users != 1:
        raise AssertionError(f"emulator second page did not publish cutover: {second_payload}")

    before = operator.inspect_fixture(client, run_id="emulator-proof-20260905")
    if before.writer_mode != WriterMode.ledger.value or before.retained_rows != operator.ROW_COUNT:
        raise AssertionError("emulator ledger proof is not authoritative or lost rows")
    rollback = operator.rollback_fixture(
        client,
        run_id="emulator-proof-20260905",
        confirmation="ROLLBACK_QA",
    )
    after = operator.inspect_fixture(client, run_id="emulator-proof-20260905", allow_ledger=False)
    if rollback["retained_rows"] != operator.ROW_COUNT or after.metadata_digest != before.metadata_digest:
        raise AssertionError("emulator rollback changed the retained fixture")

    rollforward = asyncio.run(
        drain.run_knowledge_ledger_drain(
            db_client=client,
            now=NOW,
            uid_allowlist=[operator.QA_UID],
        )
    )
    if rollforward.migrated_rows != 0 or rollforward.cutover_users != 1 or rollforward.errors:
        raise AssertionError(f"emulator roll-forward was not a stable no-op: {_summary_payload(rollforward)}")
    final = operator.inspect_fixture(client, run_id="emulator-proof-20260905")
    if final.writer_mode != WriterMode.ledger.value or final.retained_rows != operator.ROW_COUNT:
        raise AssertionError("emulator roll-forward did not restore ledger authority")

    print(
        "PASS: labelled JIT QA Firestore emulator proof "
        f"prepare=101 drain=[{first.migrated_rows},{second.migrated_rows}] "
        f"rollback=preserved rollforward={rollforward.migrated_rows} "
        "authority_boundary=injected-rollout-unit-proof-only"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
