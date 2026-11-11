#!/usr/bin/env python3
"""Score call apps from desktop telemetry and propose release-catalog changes.

The macOS app sends one `Desktop Call App Audio Summary` event per app per day
(`CallAppAudioSummaryTelemetry.swift`): how often the app released the
microphone like a call ending (mic and speaker stop together), like a mute
(speaker keeps playing), or because the input device changed. An app whose
releases are almost never mute-like can use "mic released" as a call boundary,
which is what `CallAppReleasePolicy` lists. This script decides, with the
thresholds in `catalog.json`, which apps to add or remove, and reports apps we
do not know yet that behave like call apps.

    score.py --out-dir DIR               fetch 14 days from PostHog, write rows.json,
                                         scoreboard.json and report.md
    score.py --rows ROWS --out-dir DIR   score saved rows instead of fetching
    score.py --rows ROWS --apply --pr-body PATH [--today YYYY-MM-DD]
                                         apply proposals to catalog.json and the Swift
                                         block, write a changelog fragment and PR body
    score.py --check                     catalog.json and the Swift block agree

PostHog: POSTHOG_PERSONAL_API_KEY (required to fetch), POSTHOG_PROJECT_ID
(default 302298), POSTHOG_HOST (default https://us.posthog.com). Read-only.
Standard library only.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
MACOS = HERE.parents[1]
CATALOG = HERE / "catalog.json"
SWIFT_POLICY = MACOS / "Desktop/Sources/Audio/CallAppReleasePolicy.swift"
CONFERENCING_APPS = MACOS / "Desktop/Sources/ConferencingApps.swift"
CHANGELOG_DIR = MACOS / "changelog/unreleased"

EVENT = "Desktop Call App Audio Summary"
BEGIN = "  // BEGIN GENERATED: call-app-catalog (desktop/macos/scripts/call-app-catalog/score.py)"
END = "  // END GENERATED: call-app-catalog"
COUNT_FIELDS = (
    "call_like_sessions",
    "releases_call_end",
    "releases_mute_like",
    "releases_device_switch",
)


# ---------------------------------------------------------------- catalog I/O


def load_catalog(path: Path | None = None) -> dict:
    return json.loads((path or CATALOG).read_text())


def swift_set_literal(source: str, name: str) -> list[str]:
    match = re.search(rf"static let {name}: [^=]+=\s*(?:Set\()?\[(.*?)\]", source, re.S)
    if not match:
        raise SystemExit(f"could not find {name} in Swift source")
    return re.findall(r'"([^"]+)"', match.group(1))


def native_call_ids(source: str | None = None) -> set[str]:
    source = source if source is not None else CONFERENCING_APPS.read_text()
    ids = set(swift_set_literal(source, "nativeCallBundleIDs"))
    ids |= set(swift_set_literal(source, "telegramBundleIDs"))
    return {i.lower() for i in ids}


def browser_prefixes(source: str | None = None) -> list[str]:
    source = source if source is not None else CONFERENCING_APPS.read_text()
    return [p.lower() for p in swift_set_literal(source, "browserBundleIDPrefixes")]


def generated_block(bundle_ids: list[str]) -> str:
    lines = [BEGIN, "  static let releaseEndsCallBundleIDs: Set<String> = ["]
    lines += [f'    "{b}",' for b in sorted(set(bundle_ids))]
    lines += ["  ]", END]
    return "\n".join(lines)


def swift_block_ids(source: str) -> list[str]:
    start, end = source.find(BEGIN), source.find(END)
    if start < 0 or end < 0:
        raise SystemExit(f"generated markers missing from {SWIFT_POLICY}")
    return re.findall(r'"([^"]+)"', source[start:end])


def write_swift_block(bundle_ids: list[str], path: Path | None = None) -> None:
    path = path or SWIFT_POLICY
    source = path.read_text()
    start, end = source.find(BEGIN), source.find(END)
    if start < 0 or end < 0:
        raise SystemExit(f"generated markers missing from {path}")
    path.write_text(source[:start] + generated_block(bundle_ids) + source[end + len(END) :])


def catalog_ids(catalog: dict) -> list[str]:
    return [entry["bundle_id"].lower() for entry in catalog["release_ends_call"]]


# ---------------------------------------------------------------- telemetry


def hogql(query: str) -> list[list]:
    key = os.environ.get("POSTHOG_PERSONAL_API_KEY")
    if not key:
        raise SystemExit("POSTHOG_PERSONAL_API_KEY is not set")
    project = os.environ.get("POSTHOG_PROJECT_ID", "302298")
    host = os.environ.get("POSTHOG_HOST", "https://us.posthog.com").rstrip("/")
    request = urllib.request.Request(
        f"{host}/api/projects/{project}/query/",
        data=json.dumps({"query": {"kind": "HogQLQuery", "query": query}}).encode(),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        body = json.load(response)
    if "results" not in body:
        raise SystemExit(f"PostHog query failed: {json.dumps(body)[:500]}")
    return body["results"]


def fetch_rows(window_days: int) -> dict:
    where = f"event = '{EVENT}' and timestamp > now() - interval {int(window_days)} day"
    sums = ", ".join(f"sum(toInt(properties.{f}))" for f in COUNT_FIELDS)
    rows = hogql(
        f"select lower(toString(properties.bundle_id)), uniq(distinct_id), {sums} "
        f"from events where {where} group by 1 order by 3 desc limit 500"
    )
    totals = hogql(f"select uniq(distinct_id), count() from events where {where}")
    total_users, total_events = (totals[0] if totals else [0, 0])
    return {
        "fetched_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "window_days": window_days,
        "total_users": int(total_users or 0),
        "total_events": int(total_events or 0),
        "rows": [
            {"bundle_id": r[0], "users": int(r[1] or 0), **{f: int(v or 0) for f, v in zip(COUNT_FIELDS, r[2:])}}
            for r in rows
            if r[0]
        ],
    }


# ---------------------------------------------------------------- scoring


def resolve_native(bundle_id: str, native_ids: set[str]) -> str | None:
    """Same rule as ConferencingApps.nativeCallAppID: exact, or longest dotted-prefix helper."""
    lower = bundle_id.lower()
    if lower in native_ids:
        return lower
    matches = [i for i in native_ids if lower.startswith(i + ".")]
    return max(matches, key=len) if matches else None


def score(data: dict, catalog: dict, native_ids: set[str], browsers: list[str]) -> dict:
    t = catalog["thresholds"]
    listed = set(catalog_ids(catalog))
    apps = []
    for row in data["rows"]:
        bundle = row["bundle_id"].lower()
        native = resolve_native(bundle, native_ids)
        key = native or bundle
        call_end, mute_like = row["releases_call_end"], row["releases_mute_like"]
        classified = call_end + mute_like
        ratio = (mute_like / classified) if classified else None
        enough = (
            row["users"] >= t["min_users"]
            and row["call_like_sessions"] >= t["min_call_like_sessions"]
            and classified >= t["min_classified_releases"]
        )
        if bundle.startswith("com.omi."):
            kind, verdict = "own", "ignored"
        elif any(bundle.startswith(p) for p in browsers):
            kind, verdict = "browser", "ignored"
        elif native:
            kind = "native"
            if key in listed:
                if enough and ratio is not None and ratio >= t["min_mute_like_ratio_to_remove"]:
                    verdict = "remove"
                else:
                    verdict = "confirmed" if enough else "listed"
            elif not enough:
                verdict = "waiting"
            elif ratio is not None and ratio <= t["max_mute_like_ratio_to_add"]:
                verdict = "add"
            else:
                verdict = "not_eligible"
        else:
            kind = "other"
            strong = (
                row["users"] >= t["candidate_min_users"]
                and row["call_like_sessions"] >= t["candidate_min_call_like_sessions"]
            )
            verdict = "candidate" if strong else "ignored"
        apps.append(
            {
                "bundle_id": key,
                "kind": kind,
                "verdict": verdict,
                "users": row["users"],
                "call_like_sessions": row["call_like_sessions"],
                "releases_call_end": call_end,
                "releases_mute_like": mute_like,
                "releases_device_switch": row["releases_device_switch"],
                "mute_like_ratio": ratio,
                "in_catalog": key in listed,
            }
        )
    seen = {a["bundle_id"] for a in apps}
    for missing in sorted(listed - seen):
        apps.append({"bundle_id": missing, "kind": "native", "verdict": "listed", "users": 0,
                     "call_like_sessions": 0, "releases_call_end": 0, "releases_mute_like": 0,
                     "releases_device_switch": 0, "mute_like_ratio": None, "in_catalog": True})
    apps.sort(key=lambda a: (-a["call_like_sessions"], a["bundle_id"]))
    return {
        "window_days": data["window_days"],
        "fetched_at": data.get("fetched_at"),
        "total_users": data.get("total_users", 0),
        "apps": apps,
        "add": [a["bundle_id"] for a in apps if a["verdict"] == "add"],
        "remove": [a["bundle_id"] for a in apps if a["verdict"] == "remove"],
        "candidates": [a["bundle_id"] for a in apps if a["verdict"] == "candidate"],
    }


# ---------------------------------------------------------------- output


def pct(ratio: float | None) -> str:
    return "n/a" if ratio is None else f"{ratio * 100:.1f}%"


def app_line(a: dict) -> str:
    return (f"{a['bundle_id']}: {a['users']} users, {a['call_like_sessions']} calls, "
            f"{pct(a['mute_like_ratio'])} mute-like")


def report(board: dict, catalog: dict) -> str:
    t = catalog["thresholds"]
    lines = [f"Call-app catalog: last {board['window_days']} days, {board['total_users']} users reporting"]
    by = lambda verdict: [a for a in board["apps"] if a["verdict"] == verdict]
    for a in by("add"):
        lines.append(f"PROPOSE ADD {app_line(a)}")
    for a in by("remove"):
        lines.append(f"PROPOSE REMOVE {app_line(a)}")
    for a in by("confirmed") + by("listed"):
        lines.append(f"In catalog: {app_line(a)}")
    for a in by("waiting"):
        lines.append(f"Waiting (needs {t['min_users']} users, {t['min_call_like_sessions']} calls): {app_line(a)}")
    for a in by("not_eligible"):
        lines.append(f"Not eligible (mute-like releases): {app_line(a)}")
    for a in by("candidate"):
        lines.append(f"Unknown call-like app: {app_line(a)}")
    if not board["add"] and not board["remove"]:
        lines.append("No catalog change proposed.")
    return "\n".join(lines) + "\n"


def evidence(a: dict, board: dict) -> str:
    return (f"{board['window_days']}-day telemetry to {str(board.get('fetched_at'))[:10]}: {a['users']} users, "
            f"{a['call_like_sessions']} call-like sessions, {a['releases_call_end']} call-end and "
            f"{a['releases_mute_like']} mute-like releases ({pct(a['mute_like_ratio'])})")


def apply(board: dict, catalog: dict, today: str, pr_body: Path) -> list[Path]:
    if not board["add"] and not board["remove"]:
        return []
    apps = {a["bundle_id"]: a for a in board["apps"]}
    entries = [e for e in catalog["release_ends_call"] if e["bundle_id"].lower() not in board["remove"]]
    for bundle in board["add"]:
        entries.append({"bundle_id": bundle, "added": today, "source": "telemetry",
                        "evidence": evidence(apps[bundle], board)})
    catalog["release_ends_call"] = sorted(entries, key=lambda e: e["bundle_id"])
    CATALOG.write_text(json.dumps(catalog, indent=2) + "\n")
    write_swift_block(catalog_ids(catalog))

    parts = []
    if board["add"]:
        parts.append("Back-to-back calls in " + ", ".join(board["add"]) + " are now saved as separate conversations")
    if board["remove"]:
        parts.append("Stopped splitting " + ", ".join(board["remove"]) + " calls when the app releases the microphone")
    fragment = CHANGELOG_DIR / f"{today.replace('-', '')}-call-app-catalog.json"
    fragment.write_text(json.dumps({"change": "; ".join(parts)}, indent=2) + "\n")

    rows = "\n".join(
        f"| `{a['bundle_id']}` | {a['verdict']} | {a['users']} | {a['call_like_sessions']} | "
        f"{a['releases_call_end']} | {a['releases_mute_like']} | {a['releases_device_switch']} | {pct(a['mute_like_ratio'])} |"
        for a in board["apps"] if a["verdict"] in ("add", "remove")
    )
    t = catalog["thresholds"]
    pr_body.write_text(f"""## Summary

Weekly call-app catalog update from `desktop/macos/scripts/call-app-catalog/score.py`, run over the last {board['window_days']} days of `{EVENT}` telemetry ({board['total_users']} users reporting).

An app in `CallAppReleasePolicy` has its microphone release treated as the end of a call, so back-to-back calls in that app become separate conversations. An app qualifies when at least {t['min_users']} users and {t['min_call_like_sessions']} call-like sessions show at most {t['max_mute_like_ratio_to_add'] * 100:.0f}% mute-like releases (mic stopped while the speaker kept playing). A listed app is removed at {t['min_mute_like_ratio_to_remove'] * 100:.0f}% or more.

| App | Change | Users | Call-like sessions | Call-end releases | Mute-like releases | Device-switch releases | Mute-like share |
|---|---|---|---|---|---|---|---|
{rows}

Evidence for each entry is recorded in `catalog.json`.

## Product invariants affected

none

## Verification

- `python3 desktop/macos/scripts/call-app-catalog/score.py --check`: `catalog.json` and the generated Swift block agree.
- `python3 desktop/macos/scripts/tests/test_call_app_catalog.py`: scorer unit tests.
- Evidence layer: aggregated production telemetry. Not exercised in a live call on a build containing the change.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
""")
    return [CATALOG, SWIFT_POLICY, fragment]


# ---------------------------------------------------------------- main


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--rows", type=Path, help="score saved rows.json instead of fetching")
    parser.add_argument("--out-dir", type=Path, help="write rows.json, scoreboard.json and report.md here")
    parser.add_argument("--apply", action="store_true", help="apply proposals to the catalog and Swift block")
    parser.add_argument("--pr-body", type=Path, help="with --apply: where to write the PR body")
    parser.add_argument("--today", default=dt.date.today().isoformat())
    parser.add_argument("--check", action="store_true", help="verify catalog.json matches the Swift block")
    args = parser.parse_args(argv)

    catalog = load_catalog()
    if args.check:
        swift = sorted(swift_block_ids(SWIFT_POLICY.read_text()))
        json_ids = sorted(catalog_ids(catalog))
        if swift != json_ids:
            print(f"catalog.json {json_ids} != CallAppReleasePolicy.swift {swift}; run score.py --apply or fix by hand")
            return 1
        print(f"ok: {len(json_ids)} catalog entries match")
        return 0

    data = json.loads(args.rows.read_text()) if args.rows else fetch_rows(catalog["thresholds"]["window_days"])
    board = score(data, catalog, native_call_ids(), browser_prefixes())
    text = report(board, catalog)
    if args.out_dir:
        args.out_dir.mkdir(parents=True, exist_ok=True)
        (args.out_dir / "rows.json").write_text(json.dumps(data, indent=2) + "\n")
        (args.out_dir / "scoreboard.json").write_text(json.dumps(board, indent=2) + "\n")
        (args.out_dir / "report.md").write_text(text)
    if args.apply:
        if not args.pr_body:
            parser.error("--apply needs --pr-body")
        changed = apply(board, catalog, args.today, args.pr_body)
        print("changed: " + (", ".join(str(p.relative_to(MACOS.parents[1])) for p in changed) or "nothing"))
    sys.stdout.write(text)
    print(f"PROPOSALS={len(board['add']) + len(board['remove'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
