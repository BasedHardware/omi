#!/usr/bin/env python3
"""Manually run canonical short-term maintenance (TTL audit + promotion) against the local emulator."""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPO_ROOT / "backend"
sys.path.insert(0, str(BACKEND_ROOT))
sys.path.insert(0, str(REPO_ROOT / "scripts" / "dev-harness"))

from dev_harness import config  # noqa: E402


def _jsonable(value: object) -> object:
    if is_dataclass(value):
        return {key: _jsonable(item) for key, item in asdict(value).items()}
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _apply_harness_env(cfg: config.HarnessConfig) -> None:
    for key, value in config.child_env_for(cfg).items():
        os.environ[key] = value


def _resolve_uid(cfg: config.HarnessConfig, user: str) -> str:
    manifest_path = cfg.layout.state_root / "manifests" / "canonical-auth-uids.json"
    if manifest_path.is_file():
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        users = payload.get("users")
        if isinstance(users, dict) and user in users:
            return str(users[user])
    canonical = os.environ.get("MEMORY_CANONICAL_USERS", "").split(",")
    if canonical and canonical[0].strip():
        return canonical[0].strip()
    raise SystemExit(f"Cannot resolve Firebase uid for {user!r}; seed happy_path first.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("user", nargs="?", default="alice", help="Synthetic harness user (default: alice)")
    parser.add_argument(
        "--promotion-only",
        action="store_true",
        help="Skip TTL lifecycle audit and run promotion only",
    )
    parser.add_argument("--run-id", default="", help="Promotion run id (default: manual-<utc timestamp>)")
    args = parser.parse_args(argv)

    cfg = config.load_config(REPO_ROOT, create_layout=False)
    _apply_harness_env(cfg)

    from utils.memory.short_term_promotion import (  # noqa: E402
        run_canonical_short_term_maintenance,
        run_canonical_short_term_promotion,
    )

    uid = _resolve_uid(cfg, args.user)
    run_id = args.run_id or f"manual-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"

    if args.promotion_only:
        report = run_canonical_short_term_promotion(uid, run_id=run_id)
    else:
        report = run_canonical_short_term_maintenance(uid, run_id=run_id)

    print(json.dumps(_jsonable(report), indent=2, sort_keys=True))
    promoted = getattr(report, "promoted_memory_ids", None)
    if promoted is None and hasattr(report, "promotion"):
        promoted = getattr(report.promotion, "promoted_memory_ids", [])
    if promoted:
        print(f"promoted_count={len(promoted)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
