"""``hold`` commands: place, release, inspect and list legal holds.

A hold blocks Omi's destructive paths for one account (account wipe, cascade
and single-conversation deletes, memory deletes, purges); it never blocks the
user's product access (P7 Decision 4). Placement and release go through
``database.legal_holds.place_legal_hold`` so they contend on the same gate as
deletion and record ticket, actor, agent and reason on the hold and its event
history.
"""

from __future__ import annotations

import argparse
from datetime import datetime, time, timedelta, timezone
from typing import Any

from database import legal_holds
from database.account_deletion_marker import account_deletion_firestore_client
from database.support_actions import ActionContext, ActionRecord, digest

HOLD_ISSUER = "admin"
DEFAULT_REVIEW_DAYS = 180
MAX_REVIEW_DAYS = 730
_EVENTS_SHOWN = 20
# Place and release are a handful a year per account; this bound is never reached in practice.
_EVENTS_SCAN = 2000
# Paged by document id; an operator read of one account, at most this many tombstones.
_TOMBSTONE_SCAN_LIMIT = 50000
_TOMBSTONE_PAGE = 500
_HOLD_SCAN_LIMIT = 2000


class HoldCommandError(RuntimeError):
    pass


def _firestore_client() -> Any:
    return account_deletion_firestore_client()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _review_by(value: str | None, now: datetime) -> datetime:
    if value is None:
        return now + timedelta(days=DEFAULT_REVIEW_DAYS)
    try:
        day = datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise HoldCommandError("--review-by must be YYYY-MM-DD") from exc
    review = datetime.combine(day, time(0, 0), tzinfo=timezone.utc)
    if review <= now:
        raise HoldCommandError("--review-by must be in the future")
    if review > now + timedelta(days=MAX_REVIEW_DAYS):
        raise HoldCommandError(f"--review-by must be within {MAX_REVIEW_DAYS} days")
    return review


def _document_dict(client: Any, path: str) -> dict[str, Any] | None:
    snapshot = client.document(path).get()
    return (snapshot.to_dict() or {}) if snapshot.exists else None


def _events(client: Any, uid: str) -> list[dict[str, Any]]:
    # Literal segments keep the path visible to the Firestore collection-budget scanner.
    collection = client.collection(f"legal_holds/{uid}/events")
    # Event ids are timestamp-prefixed, so the default (ascending) id order is time order.
    # A descending order by id needs a composite index on the events collection group
    # that does not exist; read a bounded page in the default order and keep the newest.
    rows = [{"id": snapshot.id, **(snapshot.to_dict() or {})} for snapshot in collection.limit(_EVENTS_SCAN).stream()]
    return sorted(rows, key=lambda row: row["id"])[-_EVENTS_SHOWN:]


def _held_deferred_deletes(client: Any, uid: str) -> dict[str, Any]:
    """Conversations the user deleted while held: hidden and retained, erasure owed after release."""

    collection = client.collection(f"users/{uid}/deleted_conversations")
    scanned = 0
    held: list[dict[str, Any]] = []
    last = None
    while scanned < _TOMBSTONE_SCAN_LIMIT:
        query = collection.order_by("__name__").limit(min(_TOMBSTONE_PAGE, _TOMBSTONE_SCAN_LIMIT - scanned))
        if last is not None:
            query = query.start_after(last)
        page = list(query.stream())
        for snapshot in page:
            scanned += 1
            payload = snapshot.to_dict() or {}
            if payload.get("legal_hold_deferred") is True:
                held.append({"conversation_id": snapshot.id, "erasure_armed": payload.get("erasure_armed") is True})
        if len(page) < _TOMBSTONE_PAGE:
            break
        last = page[-1]
    return {
        "count": len(held),
        "without_armed_erasure": sum(1 for row in held if not row["erasure_armed"]),
        "conversations": held,
        "tombstones_scanned": scanned,
        "capped": scanned >= _TOMBSTONE_SCAN_LIMIT,
    }


def _state(client: Any, uid: str) -> dict[str, Any]:
    return {
        "hold": legal_holds.read_legal_hold(uid, firestore_client=client),
        "deletion_gate": _document_dict(client, f"{legal_holds.LEGAL_HOLD_DELETION_GATES_COLLECTION}/{uid}"),
        "account_deletion_exists": _document_dict(client, f"account_deletions/{uid}") is not None,
        "events": _events(client, uid),
        "held_deferred_deletes": _held_deferred_deletes(client, uid),
    }


def _audit(ctx: ActionContext, review_by: datetime | None) -> dict[str, Any]:
    return {"ticket": ctx.ticket, "reason": ctx.reason, "actor": ctx.actor, "agent": ctx.agent, "review_by": review_by}


def status(args: argparse.Namespace, ctx: ActionContext, record: ActionRecord) -> dict[str, Any]:
    client = _firestore_client()
    state = _state(client, args.uid)
    hold = state["hold"] or {}
    record.summary = {"hold_exists": state["hold"] is not None, "active": hold.get("active") is True}
    return {"uid": args.uid, **state}


def place(args: argparse.Namespace, ctx: ActionContext, record: ActionRecord) -> dict[str, Any]:
    client = _firestore_client()
    now = _now()
    review_by = _review_by(args.review_by, now)
    before = _state(client, args.uid)
    record.before_digest = digest(before["hold"])
    record.summary = {
        "already_active": (before["hold"] or {}).get("active") is True,
        "review_days": (review_by - now).days,
    }
    if not ctx.apply:
        return {
            "uid": args.uid,
            "dry_run": True,
            "would_place": {"issuer": HOLD_ISSUER, "review_by": review_by},
            **before,
        }
    legal_holds.place_legal_hold(
        args.uid, issuer=HOLD_ISSUER, active=True, firestore_client=client, now=now, audit=_audit(ctx, review_by)
    )
    record.summary["hold_written"] = True
    after = _state(client, args.uid)
    record.after_digest = digest(after["hold"])
    _assert_fence(args.uid, client, expect_active=True)
    record.summary["fence_verified"] = True
    return {"uid": args.uid, "placed": True, **after}


def release(args: argparse.Namespace, ctx: ActionContext, record: ActionRecord) -> dict[str, Any]:
    client = _firestore_client()
    before = _state(client, args.uid)
    hold = before["hold"]
    if not hold or hold.get("active") is not True:
        raise HoldCommandError("no active legal hold to release")
    record.before_digest = digest(hold)
    record.summary = {"was_active": True}
    if not ctx.apply:
        return {"uid": args.uid, "dry_run": True, "would_release": True, **before}
    legal_holds.place_legal_hold(
        args.uid, issuer=HOLD_ISSUER, active=False, firestore_client=client, now=_now(), audit=_audit(ctx, None)
    )
    record.summary["hold_written"] = True
    after = _state(client, args.uid)
    record.after_digest = digest(after["hold"])
    _assert_fence(args.uid, client, expect_active=False)
    record.summary["fence_verified"] = True
    deferred = after["held_deferred_deletes"]
    record.summary["held_deferred_without_erasure"] = deferred["without_armed_erasure"]
    notes = []
    if deferred["without_armed_erasure"]:
        notes.append(
            f"{deferred['without_armed_erasure']} conversation(s) the user deleted while held have no armed erasure. "
            "File them on the ticket and SCA-3339 per backend/docs/runbooks/support-operator-cli.md "
            "(hold release follow-up); do not erase by hand."
        )
    if deferred["capped"]:
        notes.append(
            f"Tombstone scan stopped at {deferred['tombstones_scanned']}; deferred deletes beyond it are not listed. "
            "Escalate on SCA-3339 before closing the ticket."
        )
    follow_up = " ".join(notes) or None
    return {"uid": args.uid, "released": True, "follow_up": follow_up, **after}


def list_holds(args: argparse.Namespace, ctx: ActionContext, record: ActionRecord) -> dict[str, Any]:
    client = _firestore_client()
    now = _now()
    # Scan everything (bounded) and filter here, so a scan that hit the bound is reported.
    scanned = legal_holds.list_legal_holds(active_only=False, limit=_HOLD_SCAN_LIMIT, firestore_client=client)
    capped = len(scanned) >= _HOLD_SCAN_LIMIT
    holds = scanned if args.all else [hold for hold in scanned if hold.get("active") is True]
    for hold in holds:
        review_by = hold.get("review_by")
        hold["review_overdue"] = hold.get("active") is True and isinstance(review_by, datetime) and review_by <= now
        hold["missing_audit"] = not hold.get("ticket")
    record.summary = {
        "holds": len(holds),
        "review_overdue": sum(1 for hold in holds if hold["review_overdue"]),
        "missing_audit": sum(1 for hold in holds if hold["missing_audit"]),
        "capped": capped,
    }
    return {"holds": holds, "scanned": len(scanned), "capped": capped}


def _assert_fence(uid: str, client: Any, *, expect_active: bool) -> None:
    try:
        legal_holds.assert_account_deletion_permitted(uid, firestore_client=client)
    except legal_holds.LegalHoldActive:
        if expect_active:
            return
        raise HoldCommandError("hold release did not take effect: deletion is still fenced")
    if expect_active:
        raise HoldCommandError("hold placement did not take effect: deletion is still permitted")


def register(groups: Any) -> None:
    group = groups.add_parser("hold", help="place, release, inspect and list legal holds")
    actions = group.add_subparsers(dest="action", required=True)

    status_parser = actions.add_parser("status", help="show the hold, deletion gate and hold history")
    status_parser.add_argument("uid")
    status_parser.set_defaults(handler=status)

    place_parser = actions.add_parser("place", help="place (or refresh the audit fields of) a legal hold")
    place_parser.add_argument("uid")
    place_parser.add_argument("--review-by", help=f"YYYY-MM-DD; default {DEFAULT_REVIEW_DAYS} days from now")
    place_parser.set_defaults(handler=place)

    release_parser = actions.add_parser("release", help="release an active legal hold")
    release_parser.add_argument("uid")
    release_parser.set_defaults(handler=release)

    list_parser = actions.add_parser("list", help="list holds; flags overdue reviews and missing audit fields")
    list_parser.add_argument("--all", action="store_true", help="include released holds")
    list_parser.set_defaults(handler=list_holds)
