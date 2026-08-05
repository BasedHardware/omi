#!/usr/bin/env python3
"""Freeze expansion of long-lived GCP service-account JSON credential paths (#6800).

Issue #6800 is a multi-phase Workload Identity / ADC migration. Live IAM cutover
requires platform prep; this checker is the repository-only first phase: known
compatibility paths may shrink, but production surfaces must not grow new
long-lived key materialization or chart/workflow bindings.

Baselines are a JSON object of ``relative/path:kind -> count``. Counts may fall;
they may not rise. New ``path:kind`` keys fail until explicitly baselined — and
baselines only shrink after real removals (``--write-baseline`` never raises).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path, PurePosixPath

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BASELINE = Path(".github/scripts/gcp_sa_key_ratchet_baseline.json")

# Production / deploy surfaces only. Docs, tests, migrations, and ad-hoc
# scripts are intentionally out of scope so the ratchet stays mergeable while
# #6800's runtime cutover proceeds.
SCAN_PREFIXES = (
    "backend/charts/",
    "backend/deploy/",
    "backend/modal/",
    ".github/workflows/",
    ".github/actions/",
)
SCAN_EXACT_FILES = {
    "backend/main.py",
    "backend/desktop_backend.py",
    "backend/database/google_credentials.py",
    "backend/database/_client.py",
    "backend/pusher/main.py",
    "backend/agent-proxy/main.py",
    "backend/utils/other/storage.py",
    "backend/routers/listen/parity_pack_export.py",
    "backend/Dockerfile",
    "backend/pusher/Dockerfile",
    "backend/agent-proxy/Dockerfile",
}

TEXT_SUFFIXES = {
    ".py",
    ".yaml",
    ".yml",
    ".json",
    ".toml",
    ".env",
    ".sh",
    ".md",
    ".txt",
    ".tpl",
    ".gotmpl",
    "",
}
DOCKERFILE_NAMES = {"Dockerfile", "Dockerfile.dev", "Dockerfile.prod"}

SKIP_PARTS = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    "tests",
    "testing",
    "migrations",
    "scripts",
}

KIND_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "google-credentials-json",
        re.compile(r"google-credentials(?:-dev)?\.json"),
    ),
    (
        "service-account-json-env",
        re.compile(r"\bSERVICE_ACCOUNT_JSON\b"),
    ),
    (
        "google-application-credentials-env",
        re.compile(r"\bGOOGLE_APPLICATION_CREDENTIALS\b"),
    ),
    (
        "from-service-account-info",
        re.compile(r"\bfrom_service_account_info\b"),
    ),
    (
        # Match both bare and quoted YAML / action input keys
        # (credentials_json: / 'credentials_json': / "credentials_json":).
        "credentials-json-gh-action",
        re.compile(r"""['"]?credentials_json['"]?\s*:"""),
    ),
)


def repo_root(explicit: str | None) -> Path:
    return Path(explicit).resolve() if explicit else REPOSITORY_ROOT


def is_scanned_path(relative: str) -> bool:
    path = PurePosixPath(relative)
    if any(part in SKIP_PARTS for part in path.parts):
        return False
    if relative in SCAN_EXACT_FILES:
        return True
    if any(relative.startswith(prefix) for prefix in SCAN_PREFIXES):
        name = path.name
        if name in DOCKERFILE_NAMES or name.startswith("Dockerfile"):
            return True
        if path.suffix.lower() in TEXT_SUFFIXES or path.suffix == "":
            # Skip binary-ish and generated noise under charts/deploy.
            if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".lock"}:
                return False
            return True
    return False


def iter_scanned_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for prefix in SCAN_PREFIXES:
        base = root / prefix
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if not path.is_file():
                continue
            relative = path.relative_to(root).as_posix()
            if is_scanned_path(relative):
                files.append(path)
    for relative in sorted(SCAN_EXACT_FILES):
        path = root / relative
        if path.is_file():
            files.append(path)
    # Deduplicate while preserving deterministic order.
    seen: set[str] = set()
    ordered: list[Path] = []
    for path in sorted(files, key=lambda p: p.relative_to(root).as_posix()):
        key = path.relative_to(root).as_posix()
        if key in seen:
            continue
        seen.add(key)
        ordered.append(path)
    return ordered


def count_kinds_in_text(text: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for kind, pattern in KIND_PATTERNS:
        hits = len(pattern.findall(text))
        if hits:
            counts[kind] = hits
    return counts


def collect_counts(root: Path) -> dict[str, int]:
    totals: dict[str, int] = {}
    for path in iter_scanned_files(root):
        relative = path.relative_to(root).as_posix()
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for kind, count in count_kinds_in_text(text).items():
            key = f"{relative}:{kind}"
            totals[key] = totals.get(key, 0) + count
    return dict(sorted(totals.items()))


def load_baseline(path: Path) -> dict[str, int]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"baseline must be a JSON object: {path}")
    note = payload.get("note")
    entries = payload.get("entries")
    if note is not None and not isinstance(note, str):
        raise ValueError(f"baseline 'note' must be a string when present: {path}")
    if not isinstance(entries, dict) or not all(
        isinstance(key, str) and isinstance(value, int) and value > 0 for key, value in entries.items()
    ):
        raise ValueError(f"baseline 'entries' must map path:kind keys to positive ints: {path}")
    return entries


def baseline_document(entries: dict[str, int]) -> dict[str, object]:
    return {
        "schema_version": 1,
        "note": (
            "Grandfathered long-lived GCP service-account JSON / credentials_json / "
            "GOOGLE_APPLICATION_CREDENTIALS paths for #6800. This list only shrinks: "
            "removing a runtime binding must lower or delete the matching entry in "
            "the same change. Adding entries is an explicit admission that "
            "production surfaces gained a new key path and needs security review."
        ),
        "entries": dict(sorted(entries.items())),
    }


def violations(counts: dict[str, int], baseline: dict[str, int]) -> list[str]:
    errors: list[str] = []
    for key, count in sorted(counts.items()):
        allowed = baseline.get(key, 0)
        if count > allowed:
            errors.append(f"{key}: found {count}, baseline allows {allowed}")
    for key, allowed in sorted(baseline.items()):
        current = counts.get(key, 0)
        if current < allowed:
            errors.append(
                f"{key}: baseline still allows {allowed} but tree only has {current}; "
                "shrink the baseline in this change"
            )
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=None)
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    parser.add_argument(
        "--write-baseline",
        action="store_true",
        help="Rewrite the baseline from the current tree (never raises existing caps).",
    )
    parser.add_argument(
        "--print-counts",
        action="store_true",
        help="Print current path:kind counts as JSON and exit 0.",
    )
    args = parser.parse_args()

    root = repo_root(str(args.root) if args.root else None)
    baseline_path = args.baseline if args.baseline.is_absolute() else root / args.baseline
    counts = collect_counts(root)

    if args.print_counts:
        print(json.dumps(baseline_document(counts), indent=2) + "\n")
        return 0

    if args.write_baseline:
        if baseline_path.exists():
            previous = load_baseline(baseline_path)
            raised = []
            for key, count in counts.items():
                if count > previous.get(key, 0) and key in previous:
                    raised.append(f"{key}: {previous[key]} -> {count}")
            # Allow brand-new keys only when bootstrapping an empty/missing file;
            # once a baseline exists, --write-baseline may only lower or delete.
            if previous:
                new_keys = sorted(set(counts) - set(previous))
                if new_keys:
                    print("FAIL: --write-baseline refuses to add new path:kind keys:")
                    print(*new_keys, sep="\n")
                    return 1
                if raised:
                    print("FAIL: --write-baseline refuses to raise counts:")
                    print(*raised, sep="\n")
                    return 1
                # Keep only keys that still exist; lower counts to match tree.
                rewritten = {key: counts[key] for key in previous if key in counts}
            else:
                rewritten = counts
        else:
            rewritten = counts
        baseline_path.parent.mkdir(parents=True, exist_ok=True)
        baseline_path.write_text(json.dumps(baseline_document(rewritten), indent=2) + "\n", encoding="utf-8")
        print(f"Wrote {baseline_path.relative_to(root).as_posix()} ({len(rewritten)} entries)")
        return 0

    if not baseline_path.is_file():
        print(f"FAIL: missing baseline {baseline_path}")
        return 1

    errors = violations(counts, load_baseline(baseline_path))
    if not errors:
        print(f"OK: GCP SA key ratchet holds ({len(counts)} baselined path:kind entries).")
        return 0
    print("FAIL: long-lived GCP service-account key surface expanded or baseline is stale (#6800):")
    print(*errors, sep="\n")
    print(
        "\nRemove the new key path (prefer ADC / Workload Identity) or, after security "
        "review of a temporary compatibility need, raise the matching baseline entry "
        "in gcp_sa_key_ratchet_baseline.json with justification in the PR body."
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
