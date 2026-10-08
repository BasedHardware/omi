#!/usr/bin/env python3
"""Require tracked screenshot references for added or modified UI source files."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path, PurePosixPath

EVIDENCE_ROOT = ".agent-artifacts/ui-evidence/"
UI_PATTERNS = (
    ("app/lib/", (".dart",)),
    ("desktop/macos/Desktop/Sources/", (".swift",)),
    ("desktop/windows/src/", (".ts", ".tsx")),
    ("web/frontend/src/", None),
    ("web/admin/app/", None),
)
PLATFORMS = "mobile-android|mobile-ios|desktop-macos|desktop-windows|web"
IMAGE_RE = re.compile(
    rf"(?P<ordinal>[0-9]{{3}})-(?P<platform>{PLATFORMS})-(?P<slug>[a-z0-9]+(?:-[a-z0-9]+)*)\.png"
)
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".bmp", ".tif", ".tiff", ".avif", ".heic"}
BODY_IMAGE_RE = re.compile(
    r"(?<![\w./-])\.?/?(\.agent-artifacts/ui-evidence/[^\s<>\"'`()\[\]]+\.png)(?=$|[\s<>\"'`()\[\]?#.,])"
)
ESCAPE_RE = re.compile(r"UI-Evidence: none(?: -- \S[^\r\n]*)?")
CONTRACT = """UI evidence contract:
- Added/modified UI source requires at least one PR-body image reference that exists in git at HEAD.
- Store tracked screenshots in .agent-artifacts/ui-evidence/<pr-number-or-branch-slug>/.
- Filename: <NNN>-<platform>-<slug>.png; NNN is a zero-padded 3-digit ordinal starting at 001.
- Platforms: mobile-android, mobile-ios, desktop-macos, desktop-windows, web.
- Slug: lowercase kebab-case, at most 40 characters, describing the screen/state.
- Each directory contains evidence.json (JSON, 2-space indent, trailing newline):
  {"version": 1, "images": [{"file": "001-desktop-macos-chat-home.png", "platform": "desktop-macos", "description": "Chat home", "captured_by": "agent", "source": "visual-audit"}]}
- captured_by: agent|human; source: visual-audit|playwright-e2e|screencapture|manual.
- Every added image must have a valid filename and be listed in its sibling evidence.json.
- Image contents are not inspected.
Remediation:
1. Save a screenshot with the filename above and add its entry to the sibling evidence.json.
2. git add .agent-artifacts/ui-evidence/<pr-number-or-branch-slug>/ and commit the evidence.
3. Add ![Chat home](.agent-artifacts/ui-evidence/<pr-number-or-branch-slug>/001-desktop-macos-chat-home.png) to the PR body.
4. If evidence genuinely does not apply, add an exact line: UI-Evidence: none
   Optionally explain: UI-Evidence: none -- <reason>
   This escape waives the body reference only; added images still require valid filenames/manifests.
5. Before a PR exists, write the draft body to /tmp/pr-body.md and push with:
   OMI_PR_BODY_FILE=/tmp/pr-body.md git push
   Or validate with: scripts/pr-preflight --pr-body-file /tmp/pr-body.md"""


def clean_git_env() -> dict[str, str]:
    return {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}


def git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=root, env=clean_git_env(), check=True, capture_output=True, encoding="utf-8"
    )
    return result.stdout


def is_ui_source(relative: str) -> bool:
    return any(
        relative.startswith(prefix) and (suffixes is None or relative.endswith(suffixes))
        for prefix, suffixes in UI_PATTERNS
    )


def diff_paths(root: Path, base: str, head: str, statuses: str) -> set[str]:
    output = git(root, "diff", "--name-only", "-z", "--no-renames", f"--diff-filter={statuses}", f"{base}...{head}")
    return set(output.split("\0")) - {""}


def evidence_files(root: Path, head: str) -> set[str]:
    # Regular tracked blobs only: a directory or symlink is not screenshot evidence.
    records = git(root, "ls-tree", "-rz", head, "--", EVIDENCE_ROOT).split("\0")
    return {record.split("\t", 1)[1] for record in records if record.startswith(("100644 blob ", "100755 blob "))}


def validate_added_image(root: Path, head: str, relative: str, tracked: set[str]) -> list[str]:
    path = PurePosixPath(relative)
    match = IMAGE_RE.fullmatch(path.name)
    directory = relative[len(EVIDENCE_ROOT):].split("/")[0]
    if (
        match is None
        or match.group("ordinal") == "000"
        or len(match.group("slug")) > 40
        or len(path.parts) != 4
        or re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", directory) is None
    ):
        return [f"{relative}: invalid screenshot directory or filename"]
    if relative not in tracked:
        return [f"{relative}: screenshot must be a regular tracked file at {head}"]
    manifest_path = str(path.parent / "evidence.json")
    if manifest_path not in tracked:
        return [f"{relative}: missing sibling {manifest_path} at {head}"]
    try:
        manifest = json.loads(git(root, "show", f"{head}:{manifest_path}"))
    except (ValueError, UnicodeError):
        return [f"{manifest_path}: invalid JSON"]
    if (
        not isinstance(manifest, dict)
        or type(manifest.get("version")) is not int
        or manifest["version"] != 1
        or not isinstance(manifest.get("images"), list)
    ):
        return [f"{manifest_path}: expected version 1 and an images array"]
    entries = [item for item in manifest["images"] if isinstance(item, dict) and item.get("file") == path.name]
    if len(entries) != 1:
        return [f"{manifest_path}: must list {path.name} exactly once"]
    entry = entries[0]
    if (
        entry.get("platform") != match.group("platform")
        or not isinstance(entry.get("description"), str)
        or not entry["description"].strip()
        or entry.get("captured_by") not in ("agent", "human")
        or entry.get("source") not in ("visual-audit", "playwright-e2e", "screencapture", "manual")
    ):
        return [f"{manifest_path}: invalid metadata for {path.name}"]
    return []


def evaluate(root: Path, base: str, head: str, changed: set[str], body_file: Path | None) -> list[str]:
    if not any(is_ui_source(path) for path in changed):
        return []
    active = diff_paths(root, base, head, "AM")
    if not any(is_ui_source(path) for path in changed & active):
        return []
    tracked = evidence_files(root, head)
    failures = []
    added = diff_paths(root, base, head, "A")
    for relative in sorted(added):
        if relative.startswith(EVIDENCE_ROOT) and PurePosixPath(relative).suffix.lower() in IMAGE_SUFFIXES:
            failures.extend(validate_added_image(root, head, relative, tracked))
    body = body_file.read_text(encoding="utf-8") if body_file and body_file.is_file() else ""
    escaped = any(ESCAPE_RE.fullmatch(line) for line in body.splitlines())
    referenced = any(match.group(1) in tracked for match in BODY_IMAGE_RE.finditer(body))
    if not escaped and not referenced:
        failures.append(
            "UI source changed, but the PR body has no tracked UI screenshot reference or exact "
            "UI-Evidence: none line (body may be empty/absent)."
        )
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--changed-files", type=Path, required=True)
    parser.add_argument("--base", required=True)
    parser.add_argument("--head", required=True)
    parser.add_argument("--pr-body-file", type=Path)
    args = parser.parse_args()
    try:
        changed = {line.strip() for line in args.changed_files.read_text(encoding="utf-8").splitlines() if line.strip()}
        failures = evaluate(args.root, args.base, args.head, changed, args.pr_body_file)
    except (OSError, UnicodeError, ValueError, subprocess.CalledProcessError) as error:
        print(f"FAIL: UI evidence: {error}\n{CONTRACT}", file=sys.stderr)
        return 2
    if failures:
        print(
            "FAIL: UI evidence\n" + "\n".join(f"- {failure}" for failure in failures) + "\n" + CONTRACT,
            file=sys.stderr,
        )
        return 1
    print("OK: UI evidence contract satisfied (or no added/modified UI source).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
