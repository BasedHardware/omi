#!/usr/bin/env python3
"""Inventory or apply a governed multi-user legacy-memory migration.

LIFECYCLE: permanent

Dry-run is the default. Apply mode is deliberately write-only: it enrolls
control docs at ``stage=write`` and stages canonical admission candidates, but
never edits the code-owned cohort, enables canonical reads, invokes L2, or
promotes memory.
"""

from __future__ import annotations

import argparse
import getpass
import json
import sys
from pathlib import Path
from typing import Any

from google.cloud import firestore

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from database.google_credentials import prepare_google_credentials
from scripts.enroll_canonical_memory_user import apply_documents, build_rollout_documents
from utils.memory.bulk_legacy_backfill import (
    BulkMigrationConfig,
    FirestoreCheckpointStore,
    read_global_pause,
    run_bulk_migration,
)
from utils.memory.legacy_backfill import backfill_user, backfill_user_bucketed
from utils.memory.legacy_backfill_inventory import inventory_legacy_user

APPLY_CONFIRMATION = "bulk-canonical-memory-backfill"
WRITABLE_BUCKET_CHOICES = ("manual_required_promotion", "reviewed_long_term")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Inventory or apply governed legacy-to-canonical memory migration for multiple UIDs"
    )
    parser.add_argument("--uid", action="append", default=[], help="Firebase UID; repeat for multiple users")
    parser.add_argument(
        "--uid-file",
        type=Path,
        help="UTF-8 newline-delimited UIDs or a JSON array of UID strings",
    )
    parser.add_argument("--firestore-project", required=True, help="Explicit Firestore data-plane project")
    parser.add_argument("--apply", action="store_true", help="Apply enrollment and staging writes")
    parser.add_argument(
        "--confirm-apply",
        help=f"Required with --apply; must be exactly {APPLY_CONFIRMATION!r}",
    )
    parser.add_argument(
        "--confirm-user-count",
        type=int,
        help="Required with --apply; must equal the deduplicated input UID count",
    )
    parser.add_argument(
        "--allow-existing-update",
        action="store_true",
        help="Acknowledge merge-updating existing differing enrollment control docs",
    )
    parser.add_argument(
        "--allow-admin-override",
        action="store_true",
        help="Stage UIDs outside CANONICAL_MEMORY_USERS (requires the second override acknowledgement)",
    )
    parser.add_argument(
        "--i-understand-uids-not-whitelisted",
        action="store_true",
        help="Second acknowledgement required with --allow-admin-override",
    )
    parser.add_argument("--account-generation", type=int, default=1)
    parser.add_argument("--owner", default="memory_platform")
    parser.add_argument("--operator-context", default=None)
    parser.add_argument("--batch-size", type=int, default=50)
    parser.add_argument("--max-users-per-run", type=int, default=10)
    parser.add_argument("--max-admitted-rows-per-user", type=int, default=100)
    parser.add_argument("--max-estimated-tokens-per-run", type=int, default=100_000)
    parser.add_argument("--wall-clock-seconds", type=float)
    parser.add_argument("--concurrency-limit", type=int, default=1)
    parser.add_argument(
        "--process-bucket",
        action="append",
        choices=WRITABLE_BUCKET_CHOICES,
        default=[],
        help="Optionally upgrade a reviewed writable bucket after staging; repeatable",
    )
    return parser


def _read_uid_file(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    stripped = text.strip()
    if not stripped:
        return []
    if stripped.startswith("["):
        payload = json.loads(stripped)
        if not isinstance(payload, list) or not all(isinstance(uid, str) for uid in payload):
            raise ValueError("--uid-file JSON must be an array of strings")
        return payload
    return [line.strip() for line in text.splitlines() if line.strip() and not line.lstrip().startswith("#")]


def _deduplicate_uids(uids: list[str]) -> list[str]:
    return list(dict.fromkeys(uid.strip() for uid in uids if uid.strip()))


def _load_uids(args: argparse.Namespace) -> list[str]:
    uids = list(args.uid)
    if args.uid_file is not None:
        uids.extend(_read_uid_file(args.uid_file))
    return _deduplicate_uids(uids)


def _validate_apply_flags(args: argparse.Namespace, uids: list[str]) -> None:
    if not uids:
        raise ValueError("at least one --uid or --uid-file entry is required")
    if not args.apply:
        return
    if args.confirm_apply != APPLY_CONFIRMATION:
        raise ValueError(f"--confirm-apply must be exactly {APPLY_CONFIRMATION!r}")
    if args.confirm_user_count != len(uids):
        raise ValueError("--confirm-user-count must equal the deduplicated input UID count")
    if args.allow_admin_override != args.i_understand_uids_not_whitelisted:
        raise ValueError("--allow-admin-override and --i-understand-uids-not-whitelisted must be supplied together")


def _load_firestore_client(*, firestore_project: str) -> Any:
    prepare_google_credentials()
    return firestore.Client(project=firestore_project)


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        uids = _load_uids(args)
        _validate_apply_flags(args, uids)
        config = BulkMigrationConfig(
            dry_run=not args.apply,
            max_users_per_run=args.max_users_per_run,
            max_admitted_rows_per_user=args.max_admitted_rows_per_user,
            max_estimated_tokens_per_run=args.max_estimated_tokens_per_run,
            wall_clock_seconds=args.wall_clock_seconds,
            concurrency_limit=args.concurrency_limit,
            process_buckets=tuple(args.process_bucket),
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        parser.error(str(exc))

    db_client = _load_firestore_client(firestore_project=args.firestore_project)
    operator_context = args.operator_context or getpass.getuser()

    def inventory_fn(uid: str):
        return inventory_legacy_user(uid, db_client=db_client)

    def enroll_fn(uid: str) -> None:
        # Global read/write gates are rollout-wide controls, not per-user bulk
        # enrollment state. Leave them untouched; only the user-owned control
        # document is safe to apply repeatedly across a cohort.
        documents = [
            document
            for document in build_rollout_documents(
                uid=uid,
                stage="write",
                account_generation=args.account_generation,
                owner=args.owner,
            )
            if document.path.startswith(f"users/{uid}/")
        ]
        apply_documents(db_client, documents, allow_existing_update=args.allow_existing_update)

    def backfill_fn(uid: str, max_rows: int, resume: bool, stop_requested):
        return backfill_user(
            uid,
            dry_run=False,
            batch_size=args.batch_size,
            resume=resume,
            max_rows=max_rows,
            continue_on_error=True,
            stop_requested=stop_requested,
            allow_admin_override=args.allow_admin_override,
            acknowledge_non_canonical_uid=args.i_understand_uids_not_whitelisted,
            operator_context=operator_context,
            db_client=db_client,
        )

    def bucket_process_fn(uid: str, bucket: str, max_rows: int, stop_requested):
        del max_rows, stop_requested  # orchestrator admits only buckets that fit the remaining row budget
        return backfill_user_bucketed(
            uid,
            bucket=bucket,
            dry_run=False,
            allow_admin_override=args.allow_admin_override,
            acknowledge_non_canonical_uid=args.i_understand_uids_not_whitelisted,
            operator_context=operator_context,
            db_client=db_client,
        )

    summary = run_bulk_migration(
        uids,
        config=config,
        inventory_fn=inventory_fn,
        pause_fn=lambda: read_global_pause(db_client),
        checkpoint_store=FirestoreCheckpointStore(db_client) if args.apply else None,
        enroll_fn=enroll_fn if args.apply else None,
        backfill_fn=backfill_fn if args.apply else None,
        bucket_process_fn=bucket_process_fn if args.apply else None,
    )
    payload = summary.to_dict()
    payload["artifact"] = "bulk_legacy_canonical_memory_migration"
    payload["firestore_project"] = args.firestore_project
    payload["cohort_patch_suggestion"] = {
        "config": "backend/config/canonical_memory_cohort.py",
        "uids": uids,
        "applied": False,
    }
    payload["ownership"] = {
        "staging": "this CLI",
        "l2_and_promotion": "memory-maintenance-job",
        "read_flip": "explicit later operator action",
    }
    print(json.dumps(payload, indent=2, sort_keys=True, default=str))
    return 1 if summary.failed_user_count else 0


if __name__ == "__main__":
    raise SystemExit(main())
