#!/usr/bin/env python3
"""Per-user transcription seconds per day, from the users/{uid}/hourly_usage collection group.

Only (year, month) equality is index-supported at collection-group scope; a range on `id`
needs an index that does not exist, so the day filter is applied client-side and the scan
covers whole months. Aggregates to (date, uid_hash) and writes `stt_usage_daily.csv`, which
is the DRIVER for the audio pipeline pool. `transcription_seconds` is the field to use
(wall-clock streamed audio); `speech_seconds` is sparsely populated.

No raw uid ever reaches disk.
"""

from __future__ import annotations

import argparse
import collections
import csv
import datetime as dt
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import fs  # noqa: E402
from gcpauth import assert_readonly_identity  # noqa: E402

PAGE = 3000
SEL = {
    "fields": [
        {"fieldPath": n}
        for n in ["id", "day", "transcription_seconds", "speech_seconds", "words_transcribed", "platforms"]
    ]
}


def months_in(start: str, end: str):
    """(year, month, first_day, last_day) tuples covering an inclusive date window."""
    d0, d1 = dt.date.fromisoformat(start), dt.date.fromisoformat(end)
    out, y, m = [], d0.year, d0.month
    while (y, m) <= (d1.year, d1.month):
        first = dt.date(y, m, 1)
        nxt = dt.date(y + (m == 12), (m % 12) + 1, 1)
        last = nxt - dt.timedelta(days=1)
        out.append((y, m, max(d0, first).day, min(d1, last).day))
        y, m = nxt.year, nxt.month
    return out


def pull(year: int, month: int, day_lo: int, day_hi: int, acc: dict):
    cursor, page, seen, kept = None, 0, 0, 0
    while True:
        q = {
            "from": [{"collectionId": "hourly_usage", "allDescendants": True}],
            "select": SEL,
            "where": {
                "compositeFilter": {
                    "op": "AND",
                    "filters": [
                        {
                            "fieldFilter": {
                                "field": {"fieldPath": "year"},
                                "op": "EQUAL",
                                "value": {"integerValue": str(year)},
                            }
                        },
                        {
                            "fieldFilter": {
                                "field": {"fieldPath": "month"},
                                "op": "EQUAL",
                                "value": {"integerValue": str(month)},
                            }
                        },
                    ],
                }
            },
            "orderBy": [{"field": {"fieldPath": "__name__"}, "direction": "ASCENDING"}],
            "limit": PAGE,
        }
        if cursor:
            q["startAt"] = {"values": [{"referenceValue": cursor}], "before": False}
        res = fs.post(":runQuery", {"structuredQuery": q})
        docs = [r["document"] for r in res if "document" in r]
        page += 1
        if not docs:
            break
        for d in docs:
            seen += 1
            uid = d["name"].split("/documents/")[-1].split("/")[1]
            f = d.get("fields", {})
            did = fs.unwrap(f.get("id")) if "id" in f else d["name"].split("/")[-1]
            date = did[:10]
            if not (day_lo <= int(date[8:10]) <= day_hi):
                continue
            kept += 1
            a = acc.setdefault((date, fs.uid_hash(uid)), [0, 0, 0, set()])
            a[0] += fs.unwrap(f.get("transcription_seconds")) or 0
            a[1] += fs.unwrap(f.get("speech_seconds")) or 0
            a[2] += fs.unwrap(f.get("words_transcribed")) or 0
            pf = fs.unwrap(f.get("platforms"))
            for x in (pf if isinstance(pf, list) else [pf] if pf else []):
                if x:
                    a[3].add(str(x))
        cursor = docs[-1]["name"]
        if page % 5 == 0 or len(docs) < PAGE:
            sys.stderr.write("  %d-%02d page %d seen=%d kept=%d keys=%d\n" % (year, month, page, seen, kept, len(acc)))
        if len(docs) < PAGE:
            break
    sys.stderr.write("%d-%02d done: seen=%d kept=%d\n" % (year, month, seen, kept))
    return {"seen": seen, "kept": kept}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", required=True)
    ap.add_argument("--end", required=True)
    ap.add_argument("--raw", required=True)
    a = ap.parse_args()
    assert_readonly_identity()
    raw = pathlib.Path(a.raw)
    raw.mkdir(parents=True, exist_ok=True)

    acc, stats = {}, {}
    for y, m, lo, hi in months_in(a.start, a.end):
        stats["%04d-%02d" % (y, m)] = pull(y, m, lo, hi, acc)

    users = {}
    upath = raw / "users_active_30d.csv"
    if upath.exists():
        users = {r["uid_hash"]: r for r in csv.DictReader(open(upath))}

    rows = []
    for (date, uh), v in sorted(acc.items()):
        u = users.get(uh) or {}
        rows.append(
            [
                date,
                uh,
                u.get("last_active_platform", ""),
                u.get("plan") or "unknown",
                v[0],
                v[1],
                v[2],
                "|".join(sorted(v[3])),
            ]
        )
    path = raw / "stt_usage_daily.csv"
    with open(path, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(
            [
                "date",
                "uid_hash",
                "last_active_platform",
                "plan",
                "transcription_seconds",
                "speech_seconds",
                "words_transcribed",
                "platforms_field",
            ]
        )
        w.writerows(rows)
    (raw / "_hourly_pull_stats.json").write_text(
        json.dumps({"window": [a.start, a.end], "months": stats, "rows": len(rows)}, indent=1)
    )
    byday = collections.Counter()
    for r in rows:
        byday[r[0]] += r[4]
    for d in sorted(byday):
        sys.stderr.write("  %s transcription %.1f h\n" % (d, byday[d] / 3600))
    sys.stderr.write("wrote %s rows=%d\n" % (path, len(rows)))


if __name__ == "__main__":
    main()
