#!/usr/bin/env python3
"""Freeze growth of oversized product-source files.

This diff-scoped ratchet covers Swift and Rust under ``desktop/macos/`` and
Python under ``backend/``. Files at or above 1,500 lines are pinned to their
checked-in count. Smaller files remain free to evolve, but cannot cross the
threshold without an explicit, reviewable baseline raise.

Baselines are stored in deterministic, ownership-scoped JSON shards.  The
checker routes each source path with ``baseline_shard_relative``; there is no
mutable index file, so unrelated product areas do not contend on one shared
ledger.  Each shard keeps its file caps and raise justifications together.

After a split, run this checker with ``--update-baseline`` to remove or lower
the affected entry automatically; that mode never raises a limit. Intentional
raises are exceptional: edit the owning shard in the same diff as the source
and add a single-line ``raise_justifications`` entry for the path.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path, PurePosixPath
from typing import Any

THRESHOLD = 1500

# Git exports these when running inside hooks (pre-push, pre-receive, update).
# When the checker shells out with an explicit cwd=, inherited values would
# redirect the subprocess at the parent repository. Drop them so discovery is
# driven by the working directory the caller chose.
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


LEGACY_BASELINE_RELATIVE = ".github/scripts/product_file_line_count_ratchet_baseline.json"
BASELINE_DIRECTORY_RELATIVE = ".github/scripts/product_file_line_count_ratchet_baseline"
DESKTOP_ROOT = "desktop/macos/"
BACKEND_ROOT = "backend/"
VENDORED_PARTS = {
    ".git",
    ".venv",
    "venv",
    "vendor",
    "vendored",
    "third_party",
    "third-party",
    "node_modules",
    "Pods",
    "Carthage",
    "target",
}
TEST_PARTS = {"test", "tests", "Tests"}


def repo_root(explicit: str | None) -> Path:
    return Path(explicit).resolve() if explicit else Path(__file__).resolve().parents[2]


def is_product_source(relative: str) -> bool:
    """Return whether a repository-relative path belongs to the guarded scope."""
    path = PurePosixPath(relative)
    parts = path.parts
    if any(part in VENDORED_PARTS or part == "Generated" for part in parts):
        return False
    if any(part in TEST_PARTS for part in parts):
        return False
    name = path.name
    if ".gen." in name or ".g." in name or name.startswith("test_") or name.endswith("_test.py"):
        return False
    if relative.startswith(BACKEND_ROOT):
        return path.suffix == ".py"
    if relative.startswith(DESKTOP_ROOT):
        return path.suffix in {".swift", ".rs"}
    return False


def line_count(path: Path) -> int:
    source = path.read_text(encoding="utf-8")
    return source.count("\n") + (0 if not source or source.endswith("\n") else 1)


def baseline_shard_relative(relative: str) -> str:
    """Return the deterministic shard owning an eligible product-source path.

    Routing is deliberately code-defined instead of recorded in a mutable
    manifest.  A source's immediate stable subsystem therefore determines its
    shard, while unrelated subsystems cannot create a shared metadata conflict.
    """
    if not is_product_source(relative):
        raise ValueError(f"cannot select a baseline shard for unsupported source path: {relative!r}")

    parts = PurePosixPath(relative).parts
    if relative.startswith(BACKEND_ROOT):
        group = parts[1] if len(parts) > 2 and parts[1] in {"database", "routers", "utils"} else "other"
        return f"{BASELINE_DIRECTORY_RELATIVE}/backend-{group}.json"

    if relative.startswith("desktop/macos/Backend-Rust/"):
        return f"{BASELINE_DIRECTORY_RELATIVE}/desktop-rust.json"

    sources_prefix = ("desktop", "macos", "Desktop", "Sources")
    if parts[:4] != sources_prefix:
        return f"{BASELINE_DIRECTORY_RELATIVE}/desktop-other.json"
    subsystem = parts[4] if len(parts) > 5 else "root"
    return f"{BASELINE_DIRECTORY_RELATIVE}/desktop-swift-{subsystem.lower()}.json"


def empty_baseline() -> dict[str, Any]:
    return {"threshold": THRESHOLD, "files": {}, "raise_justifications": {}}


def validate_baseline(value: Any, shard_relative: str | None = None) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != {"files", "raise_justifications", "threshold"}:
        raise ValueError("baseline must contain exactly files, raise_justifications, and threshold")
    if value["threshold"] != THRESHOLD:
        raise ValueError(f"baseline threshold must be {THRESHOLD}")
    files = value["files"]
    justifications = value["raise_justifications"]
    if not isinstance(files, dict) or not isinstance(justifications, dict):
        raise ValueError("baseline files and raise_justifications must be objects")
    for relative, count in files.items():
        if not isinstance(relative, str) or not is_product_source(relative):
            raise ValueError(f"baseline contains unsupported source path: {relative!r}")
        if shard_relative is not None and baseline_shard_relative(relative) != shard_relative:
            raise ValueError(f"baseline path {relative!r} belongs in {baseline_shard_relative(relative)}, not {shard_relative}")
        if not isinstance(count, int) or isinstance(count, bool) or count < THRESHOLD:
            raise ValueError(f"baseline count for {relative} must be an integer at least {THRESHOLD}")
    for relative, justification in justifications.items():
        if relative not in files:
            raise ValueError(f"raise justification without a baseline entry: {relative}")
        if not isinstance(justification, str) or not justification.strip() or "\n" in justification:
            raise ValueError(f"raise justification for {relative} must be one non-empty line")
    return value


def baseline_directory(root: Path) -> Path:
    return root / BASELINE_DIRECTORY_RELATIVE


def baseline_path(root: Path) -> Path:
    """Return the retired legacy path for migration diagnostics only."""
    return root / LEGACY_BASELINE_RELATIVE


def load_baseline_file(path: Path, shard_relative: str | None = None) -> dict[str, Any]:
    try:
        return validate_baseline(json.loads(path.read_text(encoding="utf-8")), shard_relative)
    except (OSError, json.JSONDecodeError, ValueError) as error:
        raise ValueError(f"invalid line-count ratchet baseline {path}: {error}") from error


def load_baseline_shards(root: Path) -> dict[str, dict[str, Any]]:
    """Load sharded baselines, falling back to the monolith only for migration."""
    directory = baseline_directory(root)
    if directory.is_dir():
        paths = sorted(path for path in directory.glob("*.json") if path.is_file())
        if not paths:
            raise ValueError(f"no baseline shards found under {BASELINE_DIRECTORY_RELATIVE}")
        return {
            path.relative_to(root).as_posix(): load_baseline_file(path, path.relative_to(root).as_posix())
            for path in paths
        }

    legacy = baseline_path(root)
    if legacy.is_file():
        return {LEGACY_BASELINE_RELATIVE: load_baseline_file(legacy)}
    raise ValueError(
        f"no baseline shards found under {BASELINE_DIRECTORY_RELATIVE} and legacy baseline is absent"
    )


def aggregate_baseline_shards(shards: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Validate and merge shards into the checker-facing baseline shape."""
    aggregate = empty_baseline()
    for shard_relative, shard in sorted(shards.items()):
        expected = None if shard_relative == LEGACY_BASELINE_RELATIVE else shard_relative
        validate_baseline(shard, expected)
        for relative, count in shard["files"].items():
            if relative in aggregate["files"]:
                raise ValueError(f"duplicate baseline entry for {relative} across shards")
            aggregate["files"][relative] = count
        for relative, justification in shard["raise_justifications"].items():
            if relative in aggregate["raise_justifications"]:
                raise ValueError(f"duplicate raise justification for {relative} across shards")
            aggregate["raise_justifications"][relative] = justification
    return validate_baseline(aggregate)


def load_baseline(root: Path) -> dict[str, Any]:
    return aggregate_baseline_shards(load_baseline_shards(root))


def serialize_baseline(baseline: dict[str, Any], shard_relative: str | None = None) -> str:
    validate_baseline(baseline, shard_relative)
    return json.dumps(baseline, indent=2, sort_keys=True) + "\n"


def write_baseline_shards(root: Path, shards: dict[str, dict[str, Any]], paths: set[str]) -> None:
    """Rewrite only explicitly named shard paths using canonical JSON."""
    for shard_relative in sorted(paths):
        shard = shards[shard_relative]
        path = root / shard_relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(serialize_baseline(shard, shard_relative), encoding="utf-8")


def read_changed_files(path: Path) -> set[str]:
    return {line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()}


def changed_product_sources(changed: set[str]) -> list[str]:
    return sorted(relative for relative in changed if is_product_source(relative))


def source_count(root: Path, relative: str) -> int | None:
    path = root / relative
    return line_count(path) if path.is_file() else None


def check_changed_sources(
    root: Path, baseline: dict[str, Any], changed: set[str]
) -> tuple[list[str], dict[str, int | None]]:
    """Return growth failures and the safe downward updates they require."""
    failures: list[str] = []
    downward: dict[str, int | None] = {}
    for relative in changed_product_sources(changed):
        current = source_count(root, relative)
        recorded = baseline["files"].get(relative)
        owner = baseline_shard_relative(relative)
        if current is None:
            if recorded is not None:
                downward[relative] = None
            continue
        if current < THRESHOLD:
            if recorded is not None:
                downward[relative] = None
            continue
        if recorded is None:
            failures.append(
                f"{relative}: {current} lines has no baseline entry. Split the file, or add its exact count "
                f"and a one-line raise_justifications entry to {owner} in this PR."
            )
        elif current > recorded:
            failures.append(
                f"{relative}: grew from baseline {recorded} to {current} lines. Split the file, or raise its "
                f"exact baseline with a one-line justification in {owner}."
            )
        elif current < recorded:
            downward[relative] = current
    return failures, downward


def baseline_transition_errors(
    root: Path, previous: dict[str, Any] | None, current: dict[str, Any], changed: set[str]
) -> list[str]:
    """Ensure explicit raises and baseline removals remain tied to source changes."""
    if previous is None:
        return []

    failures: list[str] = []
    old_files = previous["files"]
    new_files = current["files"]
    for relative, new_count in new_files.items():
        old_count = old_files.get(relative)
        if old_count is not None and new_count <= old_count:
            continue
        actual = source_count(root, relative)
        if relative not in changed:
            failures.append(f"{relative}: a baseline raise must include the source file in the PR diff")
        if actual != new_count:
            failures.append(
                f"{relative}: raised baseline {new_count} must exactly match the changed source count {actual}"
            )
        if relative not in current["raise_justifications"]:
            failures.append(f"{relative}: a baseline raise requires a one-line raise_justifications entry")

    for relative, old_count in old_files.items():
        new_count = new_files.get(relative)
        if new_count is not None and new_count >= old_count:
            continue
        actual = source_count(root, relative)
        if relative not in changed and actual is not None:
            failures.append(f"{relative}: lowering or removing a baseline requires the source file in the PR diff")
        if new_count is None:
            if actual is not None and actual >= THRESHOLD:
                failures.append(f"{relative}: cannot remove the baseline while the source remains oversized")
        elif actual != new_count:
            failures.append(
                f"{relative}: lowered baseline {new_count} must exactly match the changed source count {actual}"
            )
    return failures


def baseline_at_ref(root: Path, ref: str) -> dict[str, Any] | None:
    """Load either the sharded or legacy baseline from a historical git ref."""
    # Drop inherited git-hook environment so the subprocess resolves the
    # repository from cwd=root rather than the enclosing parent repository.
    env = _clean_git_env()
    listing = subprocess.run(
        ["git", "ls-tree", "-r", "--name-only", ref, "--", BASELINE_DIRECTORY_RELATIVE],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    if listing.returncode:
        raise ValueError(f"unable to inspect ratchet baseline at {ref}: {listing.stderr.strip()}")
    shard_paths = [
        line
        for line in listing.stdout.splitlines()
        if line.startswith(f"{BASELINE_DIRECTORY_RELATIVE}/") and line.endswith(".json")
    ]
    if shard_paths:
        shards: dict[str, dict[str, Any]] = {}
        for shard_relative in sorted(shard_paths):
            result = subprocess.run(
                ["git", "show", f"{ref}:{shard_relative}"],
                cwd=root,
                capture_output=True,
                text=True,
                check=False,
                env=env,
            )
            if result.returncode:
                raise ValueError(f"unable to read baseline shard {shard_relative} at {ref}")
            try:
                shards[shard_relative] = validate_baseline(json.loads(result.stdout), shard_relative)
            except (json.JSONDecodeError, ValueError) as error:
                raise ValueError(f"invalid baseline shard {shard_relative} at {ref}: {error}") from error
        return aggregate_baseline_shards(shards)

    result = subprocess.run(
        ["git", "show", f"{ref}:{LEGACY_BASELINE_RELATIVE}"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    if result.returncode:
        return None
    try:
        return validate_baseline(json.loads(result.stdout))
    except (json.JSONDecodeError, ValueError) as error:
        raise ValueError(f"invalid legacy baseline at {ref}: {error}") from error


def update_downward(root: Path, baseline: dict[str, Any], changed: set[str]) -> tuple[dict[str, Any], list[str]]:
    """Return a baseline with only safe decreases/removals applied."""
    updated = {
        "threshold": THRESHOLD,
        "files": dict(baseline["files"]),
        "raise_justifications": dict(baseline["raise_justifications"]),
    }
    failures, downward = check_changed_sources(root, baseline, changed)
    if failures:
        return updated, failures
    for relative, count in downward.items():
        if count is None:
            updated["files"].pop(relative, None)
            updated["raise_justifications"].pop(relative, None)
        else:
            updated["files"][relative] = count
    return updated, []


def update_downward_shards(
    root: Path, shards: dict[str, dict[str, Any]], changed: set[str]
) -> tuple[dict[str, dict[str, Any]], set[str], list[str]]:
    """Apply reductions only to the owning shard(s), never the aggregate ledger."""
    if LEGACY_BASELINE_RELATIVE in shards:
        raise ValueError("cannot update the retired legacy baseline; migrate to sharded baselines first")
    aggregate = aggregate_baseline_shards(shards)
    failures, downward = check_changed_sources(root, aggregate, changed)
    if failures:
        return shards, set(), failures

    updated = {
        shard_relative: {
            "threshold": shard["threshold"],
            "files": dict(shard["files"]),
            "raise_justifications": dict(shard["raise_justifications"]),
        }
        for shard_relative, shard in shards.items()
    }
    touched: set[str] = set()
    for relative, count in downward.items():
        shard_relative = baseline_shard_relative(relative)
        shard = updated[shard_relative]
        if count is None:
            shard["files"].pop(relative, None)
            shard["raise_justifications"].pop(relative, None)
        else:
            shard["files"][relative] = count
        touched.add(shard_relative)
    return updated, touched, []


def initial_baseline(root: Path) -> dict[str, Any]:
    files: dict[str, int] = {}
    for prefix in (BACKEND_ROOT, DESKTOP_ROOT):
        for path in (root / prefix).rglob("*"):
            if not path.is_file():
                continue
            relative = path.relative_to(root).as_posix()
            if is_product_source(relative):
                count = line_count(path)
                if count >= THRESHOLD:
                    files[relative] = count
    return {"threshold": THRESHOLD, "files": files, "raise_justifications": {}}


def shard_baseline(baseline: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Split a valid aggregate baseline into deterministic ownership shards."""
    validate_baseline(baseline)
    shards: dict[str, dict[str, Any]] = {}
    for relative, count in baseline["files"].items():
        shard_relative = baseline_shard_relative(relative)
        shard = shards.setdefault(shard_relative, empty_baseline())
        shard["files"][relative] = count
        if relative in baseline["raise_justifications"]:
            shard["raise_justifications"][relative] = baseline["raise_justifications"][relative]
    return {shard_relative: validate_baseline(shard, shard_relative) for shard_relative, shard in shards.items()}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", help="Repository root (default: inferred from this script)")
    parser.add_argument("--changed-files", type=Path, help="Newline-delimited repository-relative changed paths")
    parser.add_argument("--base", help="Git ref used to validate explicit baseline raises")
    parser.add_argument("--bootstrap", action="store_true", help="Create initial sharded snapshots when no baseline exists")
    parser.add_argument(
        "--update-baseline",
        action="store_true",
        help="Rewrite only owning shards for downward changes; never raises a count",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = repo_root(args.root)
    directory = baseline_directory(root)
    legacy = baseline_path(root)
    if args.bootstrap:
        if args.changed_files or args.update_baseline or directory.exists() or legacy.exists():
            print(
                "FAIL: --bootstrap requires no existing baseline and cannot be combined with other modes",
                file=sys.stderr,
            )
            return 2
        shards = shard_baseline(initial_baseline(root))
        write_baseline_shards(root, shards, set(shards))
        print(f"Wrote {len(shards)} sharded oversized-file snapshots under {BASELINE_DIRECTORY_RELATIVE}.")
        return 0
    if not args.changed_files:
        print("FAIL: --changed-files is required outside --bootstrap mode", file=sys.stderr)
        return 2

    try:
        changed = read_changed_files(args.changed_files)
        shards = load_baseline_shards(root)
        baseline = aggregate_baseline_shards(shards)
    except (OSError, ValueError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 2

    if args.update_baseline:
        try:
            updated, touched, failures = update_downward_shards(root, shards, changed)
        except ValueError as error:
            print(f"FAIL: {error}", file=sys.stderr)
            return 2
        if failures:
            print("FAIL: refusing to raise the line-count baseline", file=sys.stderr)
            print("\n".join(f"- {failure}" for failure in failures), file=sys.stderr)
            return 1
        if not touched:
            print("OK: no oversized-file baseline reduction is needed.")
            return 0
        write_baseline_shards(root, updated, touched)
        names = ", ".join(sorted(touched))
        print(f"Updated {names} downward; stage the owning shard(s) with the source split.")
        return 0

    try:
        previous = baseline_at_ref(root, args.base) if args.base else None
        failures = baseline_transition_errors(root, previous, baseline, changed)
    except ValueError as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 2
    growth_failures, downward = check_changed_sources(root, baseline, changed)
    failures.extend(growth_failures)
    if downward:
        files = ", ".join(sorted(downward))
        owners = ", ".join(sorted({baseline_shard_relative(relative) for relative in downward}))
        failures.append(
            f"owning baseline shard(s) must ratchet down for {files}; run this checker with --update-baseline and stage {owners}"
        )
    if failures:
        print("FAIL: product file line-count ratchet", file=sys.stderr)
        print("\n".join(f"- {failure}" for failure in failures), file=sys.stderr)
        return 1
    print(f"OK: no line-count increase across {len(changed_product_sources(changed))} changed product source file(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
