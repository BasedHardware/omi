"""``account`` commands: allowlisted, ticket-scoped account operations.

v1 ships only the read-only ``summary``. Write operations are added one at a
time after review; deletes and refunds are never offered here.
"""

from __future__ import annotations

import argparse
from typing import Any

from database import legal_holds
from database.account_deletion_marker import account_deletion_firestore_client
from database.support_actions import ActionContext, ActionRecord

# Profile fields a support operator needs to identify and triage an account.
_SUMMARY_FIELDS = (
    "created_at",
    "language",
    "time_zone",
    "last_active_at",
    "last_active_platform",
    "signup_platform",
    "platforms_used",
)


def _firestore_client() -> Any:
    return account_deletion_firestore_client()


def summary(args: argparse.Namespace, ctx: ActionContext, record: ActionRecord) -> dict[str, Any]:
    client = _firestore_client()
    snapshot = client.document(f"users/{args.uid}").get()
    profile = (snapshot.to_dict() or {}) if snapshot.exists else {}
    subscription = profile.get("subscription") or {}
    hold = legal_holds.read_legal_hold(args.uid, firestore_client=client)
    deletion = client.document(f"account_deletions/{args.uid}").get()
    result = {
        "uid": args.uid,
        "exists": snapshot.exists,
        "profile": {field: profile.get(field) for field in _SUMMARY_FIELDS if field in profile},
        "subscription": {
            key: subscription.get(key) for key in ("plan", "status", "current_period_end") if key in subscription
        },
        "legal_hold_active": bool(hold and hold.get("active") is True),
        "account_deletion_exists": deletion.exists,
    }
    record.summary = {"exists": snapshot.exists, "legal_hold_active": result["legal_hold_active"]}
    return result


def register(groups: Any) -> None:
    group = groups.add_parser("account", help="allowlisted account operations (v1: read-only summary)")
    actions = group.add_subparsers(dest="action", required=True)
    summary_parser = actions.add_parser(
        "summary", help="identify an account: profile basics, plan, hold and deletion state"
    )
    summary_parser.add_argument("uid")
    summary_parser.set_defaults(handler=summary)
