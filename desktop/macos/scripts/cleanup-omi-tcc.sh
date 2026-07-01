#!/usr/bin/env bash
# cleanup-omi-tcc.sh — inventory/reset Omi macOS privacy/TCC entries.
#
# Default mode is list-only and never mutates TCC, app bundles, or preferences.
# Apply mode only uses Apple's supported tccutil reset path for candidate
# bundle IDs; it never edits ~/Library/Application Support/com.apple.TCC/TCC.db.
#
# Usage:
#   scripts/cleanup-omi-tcc.sh [--list] [--apply-tccutil] [--json]
#
# Keeps by default:
#   com.omi.computer-macos  (Omi)
#   com.omi.desktop-dev     (Omi Dev)
set -euo pipefail

MODE="list"
OUTPUT="text"
KEEP_BUNDLE_IDS="com.omi.computer-macos,com.omi.desktop-dev"
CANDIDATE_PREFIXES="com.omi.omi-"

usage() {
    cat <<'USAGE'
Usage: cleanup-omi-tcc.sh [--list] [--apply-tccutil] [--json]
                          [--keep-bundle-id BUNDLE_ID]
                          [--candidate-prefix BUNDLE_ID_PREFIX] [--help]

List or reset Omi-related macOS app bundle privacy permissions.

Default mode is read-only. Apply mode calls `tccutil reset All <bundle-id>` only
for candidate bundle IDs and still does not edit the TCC SQLite database,
preferences, or app bundles.

Options:
  --list           List inventory only (default)
  --apply-tccutil  Reset TCC/privacy permissions for candidate bundle IDs
  --json           Emit deterministic JSON instead of human-readable text
  --keep-bundle-id BUNDLE_ID
                   Preserve this Omi bundle ID. May be passed more than once.
  --candidate-prefix BUNDLE_ID_PREFIX
                   Mark matching Omi bundle IDs as reset candidates. May be
                   passed more than once and is additive with the default
                   com.omi.omi- prefix.
  --help           Show this help
USAGE
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        --list)
            MODE="list"
            ;;
        --apply-tccutil|--apply)
            MODE="apply-tccutil"
            ;;
        --json)
            OUTPUT="json"
            ;;
        --keep-bundle-id)
            if [ "$#" -lt 2 ] || [ -z "$2" ]; then
                echo "--keep-bundle-id requires a non-empty bundle ID" >&2
                exit 2
            fi
            KEEP_BUNDLE_IDS="${KEEP_BUNDLE_IDS},$2"
            shift
            ;;
        --candidate-prefix)
            if [ "$#" -lt 2 ] || [ -z "$2" ]; then
                echo "--candidate-prefix requires a non-empty bundle ID prefix" >&2
                exit 2
            fi
            CANDIDATE_PREFIXES="${CANDIDATE_PREFIXES},$2"
            shift
            ;;
        --help|-h)
            usage
            exit 0
            ;;
        *)
            echo "Unknown argument: $1" >&2
            usage >&2
            exit 2
            ;;
    esac
    shift
done

if [ "$MODE" != "list" ] && [ "$MODE" != "apply-tccutil" ]; then
    echo "Unsupported mode: $MODE" >&2
    exit 2
fi

python3 - "$MODE" "$OUTPUT" "$KEEP_BUNDLE_IDS" "$CANDIDATE_PREFIXES" <<'PY'
import datetime as dt
import json
import os
import plistlib
import sqlite3
import subprocess
import sys
from pathlib import Path

MODE = sys.argv[1]
OUTPUT = sys.argv[2]
KEEP_BUNDLE_IDS = {item for item in sys.argv[3].split(",") if item}
CANDIDATE_PREFIXES = tuple(item for item in sys.argv[4].split(",") if item)
HOME = Path(os.environ.get("OMI_TCC_HOME") or Path.home())
TCC_DB = Path(
    os.environ.get("OMI_TCC_DB")
    or HOME / "Library/Application Support/com.apple.TCC/TCC.db"
)
APP_ROOTS = [
    Path(item)
    for item in (
        os.environ.get("OMI_TCC_APP_ROOTS")
        or os.pathsep.join(("/Applications", str(HOME / "Applications")))
    ).split(os.pathsep)
    if item
]
PREFS_DIR = Path(os.environ.get("OMI_TCC_PREFS_DIR") or HOME / "Library/Preferences")


def validate_bundle_id(label, bundle_id):
    if not bundle_id or bundle_id.strip() != bundle_id or "/" in bundle_id:
        raise SystemExit(f"Invalid {label}: {bundle_id!r}")
    if not bundle_id.startswith("com.omi."):
        raise SystemExit(
            f"Invalid {label}: {bundle_id!r}; expected an Omi bundle ID starting with 'com.omi.'"
        )


for keep_bundle_id in KEEP_BUNDLE_IDS:
    validate_bundle_id("keep bundle ID", keep_bundle_id)
for candidate_prefix in CANDIDATE_PREFIXES:
    validate_bundle_id("candidate prefix", candidate_prefix)


def is_candidate_bundle_id(bundle_id):
    return isinstance(bundle_id, str) and any(bundle_id.startswith(prefix) for prefix in CANDIDATE_PREFIXES)


def classify_bundle_id(bundle_id):
    if not bundle_id:
        return "unknown"
    if bundle_id in KEEP_BUNDLE_IDS:
        return "keep"
    if is_candidate_bundle_id(bundle_id):
        return "candidate"
    if bundle_id.startswith("com.omi."):
        return "review"
    return "other"


def classify_tcc_client(client):
    classification = classify_bundle_id(client)
    if classification != "other" or not isinstance(client, str):
        return classification

    path = client.lower()
    if "/omi.app/" in path or "/omi beta.app/" in path or "/omi dev.app/" in path:
        return "keep"
    if "/omi-" in path and ".app/" in path:
        return "candidate"
    return classification


def read_plist(path):
    with path.open("rb") as handle:
        return plistlib.load(handle)


def app_info(app_path):
    info_path = app_path / "Contents/Info.plist"
    if not info_path.exists():
        return None
    try:
        info = read_plist(info_path)
    except Exception as exc:
        return {
            "path": str(app_path),
            "error": f"failed to read Info.plist: {exc}",
        }

    bundle_id = info.get("CFBundleIdentifier")
    name = (
        info.get("CFBundleDisplayName")
        or info.get("CFBundleName")
        or app_path.stem
    )
    if not (
        bundle_id in KEEP_BUNDLE_IDS
        or (isinstance(bundle_id, str) and bundle_id.startswith("com.omi."))
        or name == "Omi"
        or name == "Omi Dev"
        or name.startswith("omi-")
        or app_path.name in {"Omi.app", "Omi Dev.app", "Omi Beta.app"}
        or app_path.name.startswith("omi-")
    ):
        return None

    return {
        "bundle_id": bundle_id,
        "classification": classify_bundle_id(bundle_id),
        "name": name,
        "path": str(app_path),
    }


def iter_apps(root):
    if not root.exists():
        return
    # Keep the scan bounded and deterministic. Omi dev bundles are installed as
    # direct children of /Applications by run.sh, but include one nested level for
    # user-created folders without walking the entire filesystem.
    try:
        children = sorted(root.iterdir(), key=lambda p: str(p).lower())
    except PermissionError:
        return
    for child in children:
        if child.suffix == ".app":
            yield child
        elif child.is_dir():
            try:
                grandchildren = sorted(child.iterdir(), key=lambda p: str(p).lower())
            except PermissionError:
                continue
            for grandchild in grandchildren:
                if grandchild.suffix == ".app":
                    yield grandchild


def collect_apps():
    seen = set()
    apps = []
    for root in APP_ROOTS:
        for app_path in iter_apps(root) or []:
            resolved_key = str(app_path)
            if resolved_key in seen:
                continue
            seen.add(resolved_key)
            info = app_info(app_path)
            if info:
                apps.append(info)
    return sorted(apps, key=lambda item: (item.get("classification", ""), item.get("bundle_id") or "", item["path"]))


def collect_preferences():
    prefs = []
    if not PREFS_DIR.exists():
        return prefs
    for path in sorted(PREFS_DIR.glob("com.omi*.plist"), key=lambda p: p.name.lower()):
        domain = path.name[:-6]
        prefs.append({
            "domain": domain,
            "classification": classify_bundle_id(domain),
            "path": str(path),
        })
    return prefs


def sqlite_access_columns(conn):
    rows = conn.execute("PRAGMA table_info(access)").fetchall()
    return {row[1] for row in rows}


def collect_tcc_rows():
    result = {
        "database": str(TCC_DB),
        "readable": False,
        "error": None,
        "rows": [],
    }
    if not TCC_DB.exists():
        result["error"] = "TCC database does not exist"
        return result

    try:
        conn = sqlite3.connect(f"file:{TCC_DB}?mode=ro", uri=True)
    except Exception as exc:
        result["error"] = str(exc)
        return result

    try:
        conn.row_factory = sqlite3.Row
        columns = sqlite_access_columns(conn)
        wanted = [
            "service",
            "client",
            "client_type",
            "auth_value",
            "auth_reason",
            "auth_version",
            "allowed",
            "prompt_count",
            "last_modified",
            "indirect_object_identifier",
        ]
        selected = [column for column in wanted if column in columns]
        if not {"service", "client"}.issubset(columns):
            result["error"] = "TCC access table does not contain expected service/client columns"
            return result

        sql = f"""
            SELECT {', '.join(selected)}
            FROM access
            WHERE client LIKE 'com.omi.%'
               OR client LIKE '%/Omi%.app/%'
               OR client LIKE '%/omi-%.app/%'
            ORDER BY client, service
        """
        rows = []
        for row in conn.execute(sql):
            item = {key: row[key] for key in selected}
            item["classification"] = classify_tcc_client(item.get("client"))
            if item.get("last_modified") is not None:
                try:
                    item["last_modified_iso"] = dt.datetime.fromtimestamp(
                        int(item["last_modified"]), tz=dt.timezone.utc
                    ).isoformat()
                except Exception:
                    pass
            rows.append(item)
        result["readable"] = True
        result["rows"] = rows
        return result
    except Exception as exc:
        result["error"] = str(exc)
        return result
    finally:
        conn.close()


def grouped_counts(items):
    counts = {}
    for item in items:
        key = item.get("classification", "unknown")
        counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items()))


def status_counts(items):
    counts = {}
    for item in items:
        key = item.get("status", "unknown")
        counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items()))


def candidate_bundle_ids(inventory):
    bundle_ids = set()
    for item in inventory["apps"]:
        bundle_id = item.get("bundle_id")
        if classify_bundle_id(bundle_id) == "candidate":
            bundle_ids.add(bundle_id)
    for item in inventory["preferences"]:
        domain = item.get("domain")
        if classify_bundle_id(domain) == "candidate":
            bundle_ids.add(domain)
    for item in inventory["tcc"]["rows"]:
        client = item.get("client")
        if classify_tcc_client(client) == "candidate":
            bundle_ids.add(client)

    # Defensive guard: never allow keep IDs or non-candidate com.omi IDs into apply.
    return sorted(
        bundle_id
        for bundle_id in bundle_ids
        if bundle_id not in KEEP_BUNDLE_IDS and is_candidate_bundle_id(bundle_id)
    )


def installed_candidate_bundle_ids(inventory):
    # `tccutil reset All <bundle-id>` requires LaunchServices to resolve the
    # bundle ID. Preference-only stale domains are still listed, but apply mode
    # skips them to avoid noisy deterministic failures.
    bundle_ids = set()
    for item in inventory["apps"]:
        bundle_id = item.get("bundle_id")
        if classify_bundle_id(bundle_id) == "candidate":
            bundle_ids.add(bundle_id)
    return sorted(bundle_ids)


def apply_tccutil(bundle_ids):
    results = []
    for bundle_id in bundle_ids:
        command = ["tccutil", "reset", "All", bundle_id]
        try:
            completed = subprocess.run(command, capture_output=True, text=True, check=False)
            results.append({
                "bundle_id": bundle_id,
                "command": command,
                "returncode": completed.returncode,
                "stdout": completed.stdout.strip(),
                "stderr": completed.stderr.strip(),
                "status": "ok" if completed.returncode == 0 else "failed",
            })
        except Exception as exc:
            results.append({
                "bundle_id": bundle_id,
                "command": command,
                "returncode": None,
                "stdout": "",
                "stderr": str(exc),
                "status": "error",
            })
    return results


inventory = {
    "keep_bundle_ids": sorted(KEEP_BUNDLE_IDS),
    "candidate_prefixes": sorted(CANDIDATE_PREFIXES),
    "candidate_rule": "bundle_id starts with one of " + json.dumps(sorted(CANDIDATE_PREFIXES)),
    "apps": collect_apps(),
    "preferences": collect_preferences(),
    "tcc": collect_tcc_rows(),
}
inventory["summary"] = {
    "apps": grouped_counts(inventory["apps"]),
    "preferences": grouped_counts(inventory["preferences"]),
    "tcc_rows": grouped_counts(inventory["tcc"]["rows"]),
    "tcc_readable": inventory["tcc"]["readable"],
}
inventory["candidate_bundle_ids"] = candidate_bundle_ids(inventory)
inventory["tccutil_bundle_ids"] = installed_candidate_bundle_ids(inventory)

if MODE == "apply-tccutil":
    inventory["apply"] = {
        "mode": MODE,
        "tool": "tccutil reset All",
        "results": apply_tccutil(inventory["tccutil_bundle_ids"]),
    }
    inventory["apply"]["summary"] = status_counts(inventory["apply"]["results"])

if OUTPUT == "json":
    print(json.dumps(inventory, indent=2, sort_keys=True))
    sys.exit(0)

if MODE == "apply-tccutil":
    print("Omi macOS permissions cleanup apply (tccutil only)")
    print("==================================================")
else:
    print("Omi macOS permissions cleanup inventory (read-only)")
    print("====================================================")
print("Keeps:")
for bundle_id in inventory["keep_bundle_ids"]:
    print(f"  - {bundle_id}")
print(f"Candidate rule: {inventory['candidate_rule']}")
print()

print("Candidate bundle IDs for tccutil reset:")
if inventory["tccutil_bundle_ids"]:
    for bundle_id in inventory["tccutil_bundle_ids"]:
        print(f"  - {bundle_id}")
else:
    print("  <none found>")
skipped = sorted(set(inventory["candidate_bundle_ids"]) - set(inventory["tccutil_bundle_ids"]))
if skipped:
    print("Preference-only candidate domains skipped by tccutil apply:")
    for bundle_id in skipped:
        print(f"  - {bundle_id}")
print()

if MODE == "apply-tccutil":
    print("tccutil reset results:")
    if inventory["apply"]["results"]:
        for item in inventory["apply"]["results"]:
            print(f"  [{item['status']:6}] {item['bundle_id']} rc={item['returncode']}")
            if item["stdout"]:
                print(f"           stdout: {item['stdout']}")
            if item["stderr"]:
                print(f"           stderr: {item['stderr']}")
    else:
        print("  <nothing to reset>")
    print()

print("Installed app bundles:")
if inventory["apps"]:
    for item in inventory["apps"]:
        bundle_id = item.get("bundle_id") or "<missing bundle id>"
        print(f"  [{item.get('classification', 'unknown'):9}] {bundle_id:32} {item.get('name', '')} — {item['path']}")
else:
    print("  <none found>")
print()

print("UserDefaults preference domains:")
if inventory["preferences"]:
    for item in inventory["preferences"]:
        print(f"  [{item['classification']:9}] {item['domain']:32} {item['path']}")
else:
    print("  <none found>")
print()

print("TCC/privacy rows:")
tcc = inventory["tcc"]
if not tcc["readable"]:
    print(f"  <not readable> {tcc['database']}")
    print(f"  Reason: {tcc['error']}")
    print("  Grant Full Disk Access to the terminal/Hermes host process, then rerun for TCC row details.")
elif tcc["rows"]:
    for item in tcc["rows"]:
        service = item.get("service", "")
        client = item.get("client", "")
        auth = item.get("auth_value", item.get("allowed", ""))
        modified = item.get("last_modified_iso", "")
        print(f"  [{item['classification']:9}] {client:32} {service:36} auth={auth} {modified}")
else:
    print("  <none found>")
print()

print("Summary:")
print(json.dumps(inventory["summary"], indent=2, sort_keys=True))
PY
