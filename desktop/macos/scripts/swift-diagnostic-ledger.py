#!/usr/bin/env python3
"""Advisory strict-concurrency diagnostic ledger (#9843 Ticket 09).

Builds the executable target with -strict-concurrency=complete (target-scoped
via -Xswiftc) and publishes normalized first-party diagnostics grouped by
module/path.  Report-only — no fake baseline, no warnings-as-errors.

The output becomes the authoritative queue for domain migrations (Tickets 10-14).
Fails closed on an unknown diagnostic format rather than reporting zero.

Usage:
    python3 scripts/swift-diagnostic-ledger.py [--package-path Desktop]

Output: JSON to stdout, human-readable summary to stderr.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
MACOS_DIR = SCRIPT_DIR.parent

DIAG_RE = re.compile(
  r"^(?P<file>.+?):(?P<line>\d+):(?P<col>\d+):\s+"
  r"(?P<level>warning|error|note):\s+"
  r"(?P<message>.+)$"
)


def run_build(package_path: Path) -> str:
  """Run swift build with strict-concurrency=complete and capture output."""
  cmd = [
    "xcrun", "swift", "build",
    "--package-path", str(package_path),
    "-Xswiftc", "-strict-concurrency=complete",
  ]
  result = subprocess.run(cmd, capture_output=True, text=True, check=False)
  return result.stderr + result.stdout


def normalize_path(path: str, package_root: Path) -> str:
  """Normalize absolute paths to package-relative."""
  try:
    rel = Path(path).resolve().relative_to(package_root.resolve())
    return str(rel)
  except ValueError:
    return Path(path).name


def parse_diagnostics(output: str, package_root: Path) -> list[dict]:
  """Parse compiler diagnostics into structured entries."""
  entries = []
  for line in output.splitlines():
    m = DIAG_RE.match(line)
    if not m:
      continue
    entries.append({
      "file": normalize_path(m.group("file"), package_root),
      "line": int(m.group("line")),
      "column": int(m.group("col")),
      "level": m.group("level"),
      "message": m.group("message").strip(),
    })
  return entries


def first_party_only(entries: list[dict]) -> list[dict]:
  """Filter to first-party source files (under Sources/, excluding Generated/ and .build/)."""
  return [
    e for e in entries
    if "Sources/" in e["file"]
    and ".build/" not in e["file"]
    and "Generated/" not in e["file"]
  ]


def group_by_file(entries: list[dict]) -> dict[str, list[dict]]:
  groups: dict[str, list[dict]] = defaultdict(list)
  for e in entries:
    groups[e["file"]].append(e)
  return dict(groups)


def main() -> int:
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("--package-path", default="Desktop", type=Path)
  parser.add_argument("--output", default=None, help="Write JSON to file instead of stdout")
  args = parser.parse_args()

  package_root = MACOS_DIR / args.package_path

  if not package_root.exists():
    print(f"FAIL: package path not found: {package_root}", file=sys.stderr)
    return 2

  print("Building with -strict-concurrency=complete (advisory)...", file=sys.stderr)
  output = run_build(package_root)
  all_diags = parse_diagnostics(output, package_root)
  fp_diags = first_party_only(all_diags)

  # Build the report
  by_file = group_by_file(fp_diags)
  warning_count = sum(1 for e in fp_diags if e["level"] == "warning")
  error_count = sum(1 for e in fp_diags if e["level"] == "error")

  # Category counts (extract rule from message if present)
  categories = Counter()
  for e in fp_diags:
    # Swift concurrency diagnostics often start with a category keyword
    msg = e["message"]
    if "Sendable" in msg or "sendable" in msg:
      categories["sendable"] += 1
    elif "actor" in msg.lower() or "isolation" in msg.lower():
      categories["actor-isolation"] += 1
    elif "concurrency" in msg.lower() or "data race" in msg.lower():
      categories["concurrency"] += 1
    elif "capture" in msg.lower():
      categories["capture"] += 1
    else:
      categories["other"] += 1

  report = {
    "total": len(fp_diags),
    "warnings": warning_count,
    "errors": error_count,
    "files_with_diagnostics": len(by_file),
    "categories": dict(categories.most_common()),
    "diagnostics": fp_diags,
  }

  report_json = json.dumps(report, indent=2)

  if args.output:
    Path(args.output).write_text(report_json, encoding="utf-8")
  else:
    print(report_json)

  # Human-readable summary to stderr
  print(f"\nDiagnostic ledger: {len(fp_diags)} first-party diagnostics", file=sys.stderr)
  print(f"  Warnings: {warning_count}, Errors: {error_count}", file=sys.stderr)
  print(f"  Files affected: {len(by_file)}", file=sys.stderr)
  for cat, count in categories.most_common():
    print(f"  {cat}: {count}", file=sys.stderr)

  # Fail-closed: if the build output contains diagnostic-looking lines that
  # were NOT parsed by DIAG_RE, the format may have changed.  Report this
  # rather than silently claiming zero diagnostics.
  raw_diag_lines = sum(
    1 for line in output.splitlines()
    if re.search(r":\d+:\d+:\s+(warning|error):", line)
  )
  if raw_diag_lines > 0 and len(all_diags) == 0:
    print(
      f"FAIL: build output has {raw_diag_lines} diagnostic-looking line(s) "
      f"but parser captured 0 — diagnostic format may have changed.",
      file=sys.stderr,
    )
    return 1

  return 0


if __name__ == "__main__":
  raise SystemExit(main())
