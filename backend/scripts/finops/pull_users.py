#!/usr/bin/env python3
"""Snapshot the users projection from prod Firestore. Writes hashed uids only.

`users.last_active_at_*` are overwritten in place, so this file is a SNAPSHOT taken at a
point in time, not history: it says where each user was last seen as of `snapshot_at`, and
the platform cohort for a past day is inferred from it. The snapshot time is recorded in
`_users_snapshot.json` and carried into the BigQuery run manifest so a number can always be
traced back to the snapshot it was computed from. Re-running this script for an older date
does NOT reconstruct that date's cohort.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import os
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import fs  # noqa: E402
from gcpauth import assert_readonly_identity  # noqa: E402

PAGE = 5000
FIELDS = [
    "last_active_at",
    "last_active_at_desktop",
    "last_active_at_mobile",
    "last_active_at_web",
    "last_active_platform",
    "platforms_used",
    "signup_platform",
    "created_at",
    "subscription.plan",
    "subscription.status",
    "byok.active",
]
SEL = {"fields": [{"fieldPath": f} for f in FIELDS]}
ORDER_FIELDS = ["last_active_at", "last_active_at_desktop", "last_active_at_mobile", "last_active_at_web"]


def pull(order_field: str, cutoff: str) -> dict:
    out, cursor, page = {}, None, 0
    while True:
        q = {
            "from": [{"collectionId": "users"}],
            "select": SEL,
            "where": {
                "fieldFilter": {
                    "field": {"fieldPath": order_field},
                    "op": "GREATER_THAN_OR_EQUAL",
                    "value": {"timestampValue": cutoff},
                }
            },
            "orderBy": [
                {"field": {"fieldPath": order_field}, "direction": "ASCENDING"},
                {"field": {"fieldPath": "__name__"}, "direction": "ASCENDING"},
            ],
            "limit": PAGE,
        }
        if cursor:
            q["startAt"] = {"values": cursor, "before": False}
        res = fs.post(":runQuery", {"structuredQuery": q})
        docs = [r["document"] for r in res if "document" in r]
        page += 1
        if not docs:
            break
        for d in docs:
            out[d["name"].split("/")[-1]] = {k: fs.unwrap(v) for k, v in d.get("fields", {}).items()}
        last = docs[-1]
        lf = last.get("fields", {}).get(order_field)
        cursor = [lf if lf else {"nullValue": None}, {"referenceValue": last["name"]}]
        sys.stderr.write("  %s page %d: +%d (total %d)\n" % (order_field, page, len(docs), len(out)))
        if len(docs) < PAGE:
            break
    return out


def day(ts):
    return ts[:10] if ts else ""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", required=True)
    ap.add_argument(
        "--cutoff",
        default=None,
        help="ISO timestamp; users with any last_active_at_* at or after it. Default: 33 days back.",
    )
    a = ap.parse_args()
    assert_readonly_identity()
    cutoff = a.cutoff or (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=33)).strftime("%Y-%m-%dT00:00:00Z")
    snapshot_at = dt.datetime.now(dt.timezone.utc).isoformat()

    merged = {}
    for fld in ORDER_FIELDS:
        got = pull(fld, cutoff)
        sys.stderr.write("%s -> %d docs\n" % (fld, len(got)))
        merged.update(got)
    sys.stderr.write("union: %d users\n" % len(merged))

    raw = pathlib.Path(a.raw)
    raw.mkdir(parents=True, exist_ok=True)
    path = raw / "users_active_30d.csv"
    with open(path, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(
            [
                "uid_hash",
                "plan",
                "sub_status",
                "byok_active",
                "signup_platform",
                "last_active_platform",
                "platforms_used",
                "created_at",
                "last_active_at_desktop",
                "last_active_at_mobile",
                "last_active_at_web",
                "last_active_at",
            ]
        )
        for uid in sorted(merged):
            r = merged[uid]
            sub = r.get("subscription") or {}
            byok = r.get("byok") or {}
            w.writerow(
                [
                    fs.uid_hash(uid),
                    sub.get("plan") or "none",
                    sub.get("status") or "",
                    "" if byok.get("active") is None else ("true" if byok.get("active") else "false"),
                    r.get("signup_platform") or "",
                    r.get("last_active_platform") or "",
                    "|".join(r.get("platforms_used") or []),
                    day(r.get("created_at")),
                    day(r.get("last_active_at_desktop")),
                    day(r.get("last_active_at_mobile")),
                    day(r.get("last_active_at_web")),
                    day(r.get("last_active_at")),
                ]
            )
    (raw / "_users_snapshot.json").write_text(
        json.dumps(
            {
                "snapshot_at": snapshot_at,
                "cutoff": cutoff,
                "users": len(merged),
                "note": "last_active_at_* are overwritten in place; this is a point-in-time snapshot.",
            },
            indent=1,
        )
    )
    sys.stderr.write("wrote %s (%d users, snapshot_at=%s)\n" % (path, len(merged), snapshot_at))


if __name__ == "__main__":
    main()
