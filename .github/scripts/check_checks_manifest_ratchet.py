#!/usr/bin/env python3
"""Freeze the deterministic check manifest against silent shrinkage.

``validate_manifest`` in ``run_checks.py`` only proves that the entries present
in the manifest are well-formed; it has no notion of a check that must exist.
Combined with the release-eligibility action re-running the manifest from the
commit being proved, a diff that deletes a check mints a proof certifying its
own absence.

This diff-scoped ratchet compares the check-id set against the merge base and
fails on any id that disappeared. Deliberate retirements stay possible, but only
by naming the id and a one-line reason in
``.github/scripts/checks_manifest_retired_ids.json`` -- a CODEOWNERS-covered
file, so removing a gate becomes a reviewable act rather than a diff detail.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent))

from run_checks import load_manifest  # noqa: E402

MANIFEST_RELATIVE = ".github/checks-manifest.yaml"
RETIRED_IDS_RELATIVE = ".github/scripts/checks_manifest_retired_ids.json"

# Git exports these when running inside hooks; inherited values would redirect a
# subprocess launched with an explicit cwd= at the parent repository.
_GIT_ENV_SCRUB = {
    "GIT_DIR",
    "GIT_WORK_TREE",
    "GIT_QUARANTINE_PATH",
    "GIT_INDEX_FILE",
    "GIT_OBJECT_DIRECTORY",
    "GIT_ALTERNATE_OBJECT_DIRECTORIES",
    "GIT_PREFIX",
}


def _clean_git_env() -> dict[str, str]:
    return {key: value for key, value in os.environ.items() if key not in _GIT_ENV_SCRUB}


def repo_root(explicit: str | None) -> Path:
    return Path(explicit).resolve() if explicit else Path(__file__).resolve().parents[2]


def check_ids(path: Path) -> set[str]:
    return {check.id for check in load_manifest(path).checks if check.id}


def manifest_ids_at_ref(root: Path, ref: str) -> set[str] | None:
    """Return the check-id set recorded at a git ref, or None when absent."""
    result = subprocess.run(
        ["git", "show", f"{ref}:{MANIFEST_RELATIVE}"],
        cwd=root,
        capture_output=True,
        encoding="utf-8",
        check=False,
        env=_clean_git_env(),
    )
    if result.returncode:
        return None
    with tempfile.TemporaryDirectory() as staging:
        staged = Path(staging) / "checks-manifest.yaml"
        staged.write_text(result.stdout, encoding="utf-8")
        return check_ids(staged)


def load_retired_ids(root: Path) -> dict[str, str]:
    path = root / RETIRED_IDS_RELATIVE
    if not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"invalid retired check-id ledger {RETIRED_IDS_RELATIVE}: {error}") from error
    if not isinstance(value, dict) or set(value) - {"retired"}:
        raise ValueError(f"{RETIRED_IDS_RELATIVE} must be an object with exactly a 'retired' key")
    retired = value.get("retired", {})
    if not isinstance(retired, dict):
        raise ValueError(f"{RETIRED_IDS_RELATIVE} 'retired' must be an object of check id to one-line reason")
    for check_id, reason in retired.items():
        if not isinstance(check_id, str) or not check_id:
            raise ValueError(f"{RETIRED_IDS_RELATIVE} contains a non-string check id")
        if not isinstance(reason, str) or not reason.strip() or "\n" in reason:
            raise ValueError(f"{RETIRED_IDS_RELATIVE}: retirement reason for {check_id} must be one non-empty line")
    return retired


def removal_failures(base_ids: set[str], head_ids: set[str], retired: dict[str, str]) -> list[str]:
    failures = []
    for check_id in sorted(base_ids - head_ids):
        if check_id in retired:
            continue
        failures.append(
            f"{check_id}: removed from {MANIFEST_RELATIVE}. Restore it, or record the id with a one-line "
            f"retirement reason in {RETIRED_IDS_RELATIVE} in this PR."
        )
    for check_id in sorted(set(retired) & head_ids):
        failures.append(
            f"{check_id}: listed in {RETIRED_IDS_RELATIVE} but still present in {MANIFEST_RELATIVE}; "
            "drop the stale retirement entry."
        )
    return failures


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", help="Repository root (default: inferred from this script)")
    parser.add_argument("--base", required=True, help="Merge-base git ref to compare the check-id set against")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = repo_root(args.root)
    try:
        head_ids = check_ids(root / MANIFEST_RELATIVE)
        retired = load_retired_ids(root)
        base_ids = manifest_ids_at_ref(root, args.base)
    except (OSError, ValueError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 2

    if base_ids is None:
        print(f"OK: {MANIFEST_RELATIVE} does not exist at {args.base}; nothing to ratchet against.")
        return 0

    failures = removal_failures(base_ids, head_ids, retired)
    if failures:
        print("FAIL: check manifest shrink ratchet", file=sys.stderr)
        print("\n".join(f"- {failure}" for failure in failures), file=sys.stderr)
        return 1
    print(f"OK: all {len(base_ids)} merge-base check id(s) survive in {MANIFEST_RELATIVE}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
