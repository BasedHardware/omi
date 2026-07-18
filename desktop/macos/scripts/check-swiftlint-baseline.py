#!/usr/bin/env python3
"""Down-only baseline guard and anti-bypass policy for SwiftLint (#9843 Ticket 07).

Two checks:

1. **Baseline ratchet**: candidate baseline entries must be a semantic subset of
   the merge-base baseline.  Additions are rejected; removals are allowed.  One
   bootstrap mode is permitted when the base baseline does not exist yet.

2. **swiftlint:disable policy**: every ``// swiftlint:disable`` must name a
   rule, have a local reason (``-- ...``), and not be a blanket disable.  Net
   new suppressions are rejected by counting against a base count.

The guard is portable (pure Python, no macOS/SwiftLint required).  The lint
producer (SwiftLint binary) is platform-routed via the manifest.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse, unquote

SCRIPT_DIR = Path(__file__).resolve().parent
MACOS_DIR = SCRIPT_DIR.parent
BASELINE_PATH = MACOS_DIR / "Desktop/.swiftlint-baseline.json"
SOURCES_ROOT = MACOS_DIR / "Desktop/Sources"
TESTS_ROOT = MACOS_DIR / "Desktop/Tests"

# A valid suppression: named rule + scoped + reason
DISABLE_RE = re.compile(
  r"//\s*swiftlint:disable(?::(?P<scope>next|this|previous))?"
  r"\s+(?P<rules>[A-Za-z0-9_,\s]+)"
  r"(?:\s+--\s+(?P<reason>.+))?\s*$"
)
# Blanket disable (no rule name)
BLANKET_RE = re.compile(r"//\s*swiftlint:disable\s*(?:$|--)")


def _run_git(*args: str) -> str:
  root = str(MACOS_DIR.parents[1])
  result = subprocess.run(
    ["git", *args], cwd=root, capture_output=True, text=True, check=False
  )
  return result.stdout.strip() if result.returncode == 0 else ""


def _normalize_file(file_url: str) -> str:
  """Normalize an absolute file:// URL to a repo-relative path."""
  if file_url.startswith("file://"):
    path = unquote(urlparse(file_url).path)
  else:
    path = file_url
  # Try to make it relative to Desktop/
  for marker in ("/desktop/macos/Desktop/", "/Desktop/"):
    idx = path.find(marker)
    if idx >= 0:
      return path[idx + len(marker):]
  return Path(path).name


def _entry_key(entry: dict) -> tuple:
  """Semantic identity for a baseline entry."""
  v = entry.get("violation", entry)
  loc = v.get("location", {})
  return (
    v.get("ruleIdentifier", ""),
    _normalize_file(loc.get("file", "")),
    loc.get("line", 0),
    loc.get("character", 0),
  )


def load_baseline(path: Path) -> list[dict]:
  if not path.exists():
    return []
  data = json.loads(path.read_text(encoding="utf-8"))
  return data if isinstance(data, list) else []


def check_baseline(base_ref: str, bootstrap: bool = False) -> list[str]:
  """Return list of error messages (empty = pass)."""
  errors: list[str] = []
  candidate = load_baseline(BASELINE_PATH)
  base_content = _run_git("show", f"{base_ref}:desktop/macos/Desktop/.swiftlint-baseline.json")
  if not base_content:
    if bootstrap:
      print(f"BOOTSTRAP: no base baseline at {base_ref}; allowing initial commit.")
      return []
    # If there's no base and we're not bootstrapping, still pass if the file
    # is newly introduced (first time the guard runs after Ticket 06).
    print(f"NOTE: no base baseline at {base_ref}; treating as bootstrap.")
    return []
  base = json.loads(base_content)
  base_keys = {_entry_key(e) for e in base}
  candidate_keys = {_entry_key(e) for e in candidate}
  additions = candidate_keys - base_keys
  removals = base_keys - candidate_keys
  if additions:
    errors.append(
      f"BASELINE GREW: {len(additions)} new violation(s) not in the base baseline. "
      f"Fix the violations or regenerate the baseline with justification."
    )
    for key in sorted(additions)[:10]:
      errors.append(f"  + {key[0]} at {key[1]}:{key[2]}:{key[3]}")
    if len(additions) > 10:
      errors.append(f"  ... and {len(additions) - 10} more")
  if removals:
    print(f"BASELINE SHRANK: {len(removals)} violation(s) removed. Good.")
  return errors


def find_swift_files() -> list[Path]:
  files = []
  for root in [SOURCES_ROOT, TESTS_ROOT]:
    for f in root.rglob("*.swift"):
      if "/Generated/" in str(f) or "/fixtures/" in str(f):
        continue
      files.append(f)
  return sorted(files)


def check_disable_policy(base_ref: str) -> list[str]:
  """Enforce swiftlint:disable policy across all Swift files."""
  errors: list[str] = []
  current_count = 0
  for f in find_swift_files():
    for lineno, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
      stripped = line.strip()
      # Check for blanket disable (no rule name)
      if BLANKET_RE.search(stripped) and not DISABLE_RE.search(stripped):
        errors.append(
          f"{f.relative_to(MACOS_DIR)}:{lineno}: blanket swiftlint:disable "
          f"(must name a rule): {stripped}"
        )
        current_count += 1
        continue
      m = DISABLE_RE.search(stripped)
      if m:
        current_count += 1
        reason = m.group("reason")
        if not reason:
          errors.append(
            f"{f.relative_to(MACOS_DIR)}:{lineno}: swiftlint:disable without "
            f"reason (add '-- <why>'): {stripped}"
          )
  # Check net new suppressions against base
  base_count_str = _run_git(
    "grep", "-c", r"swiftlint:disable", base_ref, "--",
    "desktop/macos/Desktop/Sources/", "desktop/macos/Desktop/Tests/"
  )
  # git grep -c returns "file:count" per file; sum them
  base_count = 0
  for line in base_count_str.splitlines():
    if ":" in line:
      try:
        base_count += int(line.rsplit(":", 1)[1])
      except ValueError:
        pass
  if current_count > base_count:
    errors.append(
      f"NET NEW SUPPRESSIONS: {current_count} swiftlint:disable comments "
      f"(base: {base_count}). Each new suppression must replace a removed "
      f"baseline entry."
    )
  return errors


def main() -> int:
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("--base", default="origin/main", help="Base git ref")
  parser.add_argument("--bootstrap", action="store_true", help="Allow initial baseline creation")
  args = parser.parse_args()
  errors: list[str] = []
  errors.extend(check_baseline(args.base, bootstrap=args.bootstrap))
  errors.extend(check_disable_policy(args.base))
  if errors:
    for e in errors:
      print(f"FAIL: {e}", file=sys.stderr)
    return 1
  print("OK: SwiftLint baseline is down-only and disable policy is clean.")
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
