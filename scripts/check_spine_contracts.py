#!/usr/bin/env python3
"""List pending contracts and allow only marker removal from spine originals."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = "contracts/spine/files.json"
ROOTS = ("scripts/dev-harness/tests/spine/", "app/test/spine/")
MARKER = re.compile(r'''^\s*(?:@pending\("([A-Z][A-Z0-9-]*)"\)|pendingContract\('([A-Z][A-Z0-9-]*)'\);)\s*$''')


def git(*args: str, root: Path = ROOT) -> str:
    return subprocess.check_output(["git", "-C", str(root), *args], text=True, stderr=subprocess.DEVNULL)


def allowed(original: str, current: str) -> bool:
    # A subsequence permits deletion only, never insertion/reordering of markers.
    lines = iter(original.splitlines(keepends=True))
    for wanted in current.splitlines(keepends=True):
        for line in lines:
            if line == wanted:
                break
            if not MARKER.fullmatch(line.rstrip("\n")):
                return False
        else:
            return False
    return all(MARKER.fullmatch(line.rstrip("\n")) for line in lines)


REVISIONS = "contracts/spine/revisions"


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def revisions(root: Path, registry: dict) -> dict:
    """Reviewed, append-only exact replacements; never a builder rebaseline flag."""
    directory = root / REVISIONS
    existing = set(git("ls-tree", "-r", "--name-only", "HEAD", "--", REVISIONS, root=root).splitlines())
    present = {str(p.relative_to(root)) for p in directory.glob("*.json")}
    if existing - present:
        raise ValueError("Spine revision records cannot be removed")
    result = {}
    for path in sorted(present):
        raw = (root / path).read_text()
        commits = git("log", "--diff-filter=A", "--format=%H", "HEAD", "--", path, root=root).splitlines()
        if commits and raw != git("show", f"{commits[-1]}:{path}", root=root):
            raise ValueError(f"{path}: committed revision record is immutable")
        record = json.loads(raw)
        if set(record) != {"path", "owner", "before", "after", "reason"} or not record["reason"].strip():
            raise ValueError(f"{path}: invalid spine revision record")
        target = record["path"]
        if registry.get(target) != record["owner"]:
            raise ValueError(f"{path}: revision owner differs from registry")
        revised = git("show", f"{commits[-1]}:{target}", root=root) if commits else (root / target).read_text()
        result.setdefault(target, []).append((record, revised))
    return result


def revised_original(original: str, records: list) -> str:
    for (previous, _), (following, _) in zip(records, records[1:]):
        if previous["after"] != following["before"]:
            raise ValueError(f"{following['path']}: broken revision chain")
    # A squash introduces the corrected file and its review records together.
    # That introducing commit is already the accepted oracle. Absorb only a
    # prefix ending at its exact digest; later revisions still need exact bytes.
    absorbed = 0
    for index, (record, _) in enumerate(records):
        if record["after"] == digest(original):
            absorbed = index + 1
    for record, revised in records[absorbed:]:
        if digest(revised) != record["after"]:
            raise ValueError(f"{record['path']}: revised bytes do not match pinned digest")
        if digest(original) != record["before"]:
            raise ValueError(f"{record['path']}: broken revision chain")
        before = [line for line in original.splitlines() if MARKER.fullmatch(line)]
        after = [line for line in revised.splitlines() if MARKER.fullmatch(line)]
        if before != after:
            raise ValueError(f"{record['path']}: revision must preserve pending markers; retire separately")
        original = revised
    return original


def marker_slots(original: str, current: str) -> set[int] | None:
    """Identify retained marker occurrences, not just their count/package."""
    if not allowed(original, current):
        return None
    wanted = iter(current.splitlines(keepends=True))
    next_line = next(wanted, None)
    kept, slot = set(), 0
    for line in original.splitlines(keepends=True):
        marker = bool(MARKER.fullmatch(line.rstrip("\n")))
        if line == next_line:
            if marker:
                kept.add(slot)
            next_line = next(wanted, None)
        slot += marker
    return kept


def retirement_allowed(anchors: list[str], base: str, current: str) -> bool:
    remaining = marker_slots(anchors[-1], current)
    for anchor in anchors:
        retired_base = marker_slots(anchor, base)
        if retired_base is not None:
            return remaining is not None and remaining <= retired_base
    return False


def check(root: Path = ROOT) -> list[str]:
    errors = []
    registry = json.loads((root / REGISTRY).read_text())
    if git("rev-parse", "--is-shallow-repository", root=root).strip() == "true":
        return ["Spine protection needs full history: git fetch --unshallow origin"]
    base = git("merge-base", "HEAD", "origin/main", root=root).strip()
    try:
        previous = json.loads(git("show", f"{base}:{REGISTRY}", root=root))
    except subprocess.CalledProcessError:
        previous = {}
    registry_commits = git("log", "--diff-filter=A", "--format=%H", "HEAD", "--", REGISTRY, root=root).splitlines()
    if registry_commits:
        introduced = json.loads(git("show", f"{registry_commits[-1]}:{REGISTRY}", root=root))
        previous = {**introduced, **previous}
    for path, owner in previous.items():
        if registry.get(path) != owner:
            errors.append(f"{path}: existing registry entry changed/deleted")
    discovered = {str(p.relative_to(root)) for prefix in ROOTS for p in (root / prefix).rglob("*")
                  if p.is_file() and p.suffix in (".py", ".dart", ".json") and "__pycache__" not in p.parts}
    for path in discovered - registry.keys():
        errors.append(f"{path}: unregistered spine file")
    amendments = revisions(root, registry)
    count = 0
    for path, owner in registry.items():
        file = root / path
        if not file.is_file():
            errors.append(f"{path}: protected file missing")
            continue
        current = file.read_text()
        commits = git("log", "--diff-filter=A", "--format=%H", "HEAD", "--", path, root=root).splitlines()
        if commits:
            original = git("show", f"{commits[-1]}:{path}", root=root)
            anchors = [original] + [text for _, text in amendments.get(path, [])]
            original = revised_original(original, amendments.get(path, []))
            if not allowed(original, current):
                errors.append(f"{path}: only pending-marker removal allowed (spine {commits[-1]})")
            # Also enforce monotonic retirement against current main.
            try:
                base_text = git("show", f"{base}:{path}", root=root)
            except subprocess.CalledProcessError:
                base_text = original
            # Corrections preserve ordered marker slots. Retiring another test
            # cannot pay for restoring a marker already retired on main.
            monotonic = retirement_allowed(anchors, base_text, current) if amendments.get(path) else allowed(base_text, current)
            if not monotonic:
                errors.append(f"{path}: retired markers cannot be restored")
        else:
            try:
                git("cat-file", "-e", f"HEAD:{path}", root=root)
            except subprocess.CalledProcessError:
                pass  # new spine, not yet committed
            else:
                errors.append(f"{path}: introducing commit unavailable; fetch full history")
        for number, line in enumerate(current.splitlines(), 1):
            match = MARKER.fullmatch(line)
            if match:
                package = next(value for value in match.groups() if value)
                count += 1
                print(f"PENDING {package} {path}:{number}")
                if package != owner:
                    errors.append(f"{path}:{number}: marker owner {package} != registry {owner}")
    print(f"Spine contracts: {count} pending markers; {len(registry)} protected files")
    return errors


if __name__ == "__main__":
    try:
        problems = check()
    except (ValueError, OSError, subprocess.CalledProcessError) as exc:
        problems = [str(exc)]
    for problem in problems:
        print(problem, file=sys.stderr)
    raise SystemExit(1 if problems else 0)
