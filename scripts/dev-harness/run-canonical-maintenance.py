#!/usr/bin/env python3
"""Run the full canonical memory maintenance pipeline against the local emulator."""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, cast

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPO_ROOT / "backend"
sys.path.insert(0, str(BACKEND_ROOT))
sys.path.insert(0, str(REPO_ROOT / "scripts" / "dev-harness"))

from dev_harness import config  # noqa: E402


def _jsonable(value: object) -> object:
    if is_dataclass(value):
        return {key: _jsonable(item) for key, item in asdict(cast(Any, value)).items()}
    # Duck-type pydantic models without importing pydantic at module scope.
    # The dev-harness test lane runs under bare python3 without backend deps;
    # this script is loaded via runpy.run_path() in repo-checks CI.
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        return _jsonable(model_dump(mode="json"))
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _apply_harness_env(cfg: config.HarnessConfig) -> None:
    child_env = config.child_env_for(cfg)
    os.environ.clear()
    os.environ.update(child_env)


def _outbox_failure_counts(outbox: object) -> dict[str, int]:
    if not isinstance(outbox, dict):
        return {
            "retryable": 0,
            "dead_letter": 0,
            "ack": 0,
            "errors": 0,
        }
    raw_errors = outbox.get("errors")
    error_count = len(raw_errors) if isinstance(raw_errors, list) else int(bool(raw_errors))
    return {
        "retryable": int(outbox.get("retryable_failure_count") or 0),
        "dead_letter": int(outbox.get("dead_letter_count") or 0),
        "ack": int(outbox.get("ack_failed_count") or 0),
        "errors": error_count,
    }


def _resolve_uid(cfg: config.HarnessConfig, user: str) -> str:
    manifest_path = cfg.layout.state_root / "manifests" / "canonical-auth-uids.json"
    if manifest_path.is_file():
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        users = payload.get("users")
        if isinstance(users, dict) and user in users:
            return str(users[user])
    raise SystemExit(f"Cannot resolve Firebase uid for {user!r}; seed happy_path first.")


def _configure_local_universal_memory(uid: str) -> None:
    """Validate the synthetic emulator principal before direct maintenance."""
    if not os.environ.get("FIRESTORE_EMULATOR_HOST"):
        raise SystemExit("Canonical maintenance harness requires the Firestore emulator.")
    if os.environ.get("ENVIRONMENT") != "local-dev-harness":
        raise SystemExit("Canonical maintenance harness requires ENVIRONMENT=local-dev-harness.")

    os.environ["MEMORY_MODE"] = "read"
    if not uid.strip():
        raise SystemExit("Canonical maintenance harness requires a non-empty emulator uid.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("user", nargs="?", default="alice", help="Synthetic harness user (default: alice)")
    parser.add_argument("--run-id", default="", help="Maintenance run id (default: manual-<utc timestamp>)")
    args = parser.parse_args(argv)

    cfg = config.load_config(REPO_ROOT, create_layout=False)
    _apply_harness_env(cfg)

    uid = _resolve_uid(cfg, args.user)
    _configure_local_universal_memory(uid)

    from utils.memory.short_term_promotion import run_canonical_short_term_maintenance  # noqa: E402

    run_id = args.run_id or f"manual-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"

    report = run_canonical_short_term_maintenance(uid, run_id=run_id)

    print(json.dumps(_jsonable(report), indent=2, sort_keys=True))
    if report.skipped_reason:
        print(f"canonical maintenance skipped: {report.skipped_reason}", file=sys.stderr)
        return 2
    outbox_failures = _outbox_failure_counts(report.outbox)
    if any(outbox_failures.values()):
        print(
            "canonical maintenance outbox delivery failed: "
            f"retryable={outbox_failures['retryable']} "
            f"dead_letter={outbox_failures['dead_letter']} "
            f"ack={outbox_failures['ack']} "
            f"errors={outbox_failures['errors']}",
            file=sys.stderr,
        )
        return 2
    if report.promoted_count:
        print(f"promoted_count={report.promoted_count}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
