#!/usr/bin/env python3
"""Require a down-only iOS SwiftLint baseline and reviewed suppressions."""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote, urlparse

ROOT = Path(__file__).resolve().parents[3]
IOS = ROOT / "app/ios"
BASELINE = IOS / ".swiftlint-baseline.json"

def key(entry):
    value = entry["violation"]
    loc = value["location"]
    path = Path(unquote(urlparse(loc["file"]).path))
    parts = path.parts
    indices = [i for i in range(len(parts)-1) if parts[i:i+2] == ("app", "ios")]
    if not indices:
        raise ValueError("baseline entry is outside app/ios")
    return (value["ruleIdentifier"], "/".join(parts[indices[-1]+2:]), loc["line"], loc.get("character", 0))

def git(*args):
    result = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True)
    return result.stdout if result.returncode == 0 else None

parser = argparse.ArgumentParser()
parser.add_argument("--base", default="origin/main")
args = parser.parse_args()
errors = []
current = json.loads(BASELINE.read_text())
base_text = git("show", f"{args.base}:app/ios/.swiftlint-baseline.json")
if base_text is not None:
    base = json.loads(base_text)
    additions = {key(e) for e in current} - {key(e) for e in base}
    for item in sorted(additions):
        errors.append(f"baseline grew: {item}")
else:
    print("Initial iOS SwiftLint baseline; no base baseline exists")
files = []
for directory in ("Runner", "BatteryWidget", "ImageNotification", "omiWatchApp"):
    files.extend((IOS / directory).rglob("*.swift"))
current_suppressions = 0
for file in files:
    if file.name.endswith(".g.swift"):
        continue
    for line_number, line in enumerate(file.read_text().splitlines(), 1):
        if "swiftlint:disable" not in line:
            continue
        current_suppressions += 1
        if not re.search(r"//\s*swiftlint:disable(?::(?:next|this|previous))?\s+[A-Za-z0-9_, ]+\s+--\s+\S", line):
            errors.append(f"{file.relative_to(ROOT)}:{line_number}: suppression needs named rule and reason")
base_grep = git("grep", "-c", "swiftlint:disable", args.base, "--", "app/ios/Runner", "app/ios/BatteryWidget", "app/ios/ImageNotification", "app/ios/omiWatchApp") or ""
base_suppressions = sum(int(line.rsplit(":", 1)[1]) for line in base_grep.splitlines() if line.rsplit(":", 1)[-1].isdigit())
if current_suppressions > base_suppressions:
    errors.append(f"net new swiftlint:disable comments: {current_suppressions} > {base_suppressions}")
for error in errors:
    print(f"FAIL: {error}", file=sys.stderr)
if errors:
    sys.exit(1)
print("iOS SwiftLint baseline is down-only and suppressions are clean")
