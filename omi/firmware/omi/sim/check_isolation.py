#!/usr/bin/env python3
"""List CV1 production sources whose production view changed against a base.

Simulator and host-test code must live under CONFIG_OMI_NATIVE_SIM,
OMI_SAFE_MODE_HOST or the dev-only fault-injection configs, or in sim/. This
tool strips those branches with `unifdef` from every changed file under
omi/firmware/omi/src at both revisions and prints the files whose production
text (ignoring comments, whitespace and leading #include order) still
differs. A simulator-only change prints nothing; a release PR's
output must match the fixes it declares.

  python3 omi/firmware/omi/sim/check_isolation.py --base origin/main
  python3 omi/firmware/omi/sim/check_isolation.py --base origin/main --expect src/safe_mode.c --expect ...

Exit status: 0 when the changed set equals --expect (or nothing changed and no
--expect was given), 1 otherwise. Needs `unifdef` (macOS ships it; apt
package `unifdef`).
"""
import argparse
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
APP = "omi/firmware/omi"
SIM_ONLY = ["CONFIG_OMI_NATIVE_SIM", "OMI_SAFE_MODE_HOST", "CONFIG_OMI_FAULT_INJECT_DRIVER_HANG",
            "CONFIG_OMI_FAULT_INJECT_SETTINGS_HANG", "CONFIG_OMI_FAULT_INJECT_WDT_STARVE",
            "CONFIG_OMI_FAULT_INJECT_HARD_FAULT"]


def strip_comments(text):
    """Drop C comments, keeping string and character literals intact."""
    out, i, n = [], 0, len(text)
    while i < n:
        c = text[i]
        if text.startswith("/*", i):
            end = text.find("*/", i + 2)
            i = n if end < 0 else end + 2
            out.append(" ")
        elif text.startswith("//", i):
            end = text.find("\n", i)
            i = n if end < 0 else end
        elif c in "\"'":
            j = i + 1
            while j < n and text[j] != c:
                j += 2 if text[j] == "\\" else 1
            out.append(text[i:j + 1])
            i = j + 1
        else:
            out.append(c)
            i += 1
    return "".join(out)


def production_view(text):
    """What the production compiler sees, modulo comments, whitespace and the
    order of the leading #include block (header order is not semantic here)."""
    args = ["unifdef", "-k", "-B"] + [f"-U{name}" for name in SIM_ONLY]
    proc = subprocess.run(args, input=text, capture_output=True, text=True)
    if proc.returncode not in (0, 1):  # 1 = output differs from input
        raise RuntimeError(f"unifdef failed: {proc.stderr.strip()}")
    lines = [" ".join(line.split()) for line in strip_comments(proc.stdout).splitlines()]
    lines = [line for line in lines if line]
    head = 0
    while head < len(lines) and lines[head].startswith("#include"):
        head += 1
    return "\n".join(sorted(lines[:head]) + lines[head:]) + "\n"


def show(rev, path):
    proc = subprocess.run(["git", "-C", REPO, "show", f"{rev}:{path}"], capture_output=True, text=True)
    return proc.stdout if proc.returncode == 0 else None


def changed(base):
    out = subprocess.run(["git", "-C", REPO, "diff", "--name-only", base, "--", f"{APP}/src", f"{APP}/CMakeLists.txt",
                          f"{APP}/Kconfig", f"{APP}/prj.conf", f"{APP}/omi.conf"],
                         capture_output=True, text=True, check=True).stdout.split()
    untracked = subprocess.run(["git", "-C", REPO, "ls-files", "--others", "--exclude-standard", f"{APP}/src"],
                               capture_output=True, text=True, check=True).stdout.split()
    return sorted(set(out) | set(untracked))


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base", required=True, help="base revision, e.g. origin/main or the merge base")
    parser.add_argument("--expect", action="append", default=[], help=f"path relative to {APP} expected to change")
    args = parser.parse_args()
    if not shutil.which("unifdef"):
        raise SystemExit("unifdef is required")
    diffs = []
    for path in changed(args.base):
        before = show(args.base, path)
        file = REPO / path
        after = file.read_text() if file.exists() else None
        source = path.endswith((".c", ".h"))
        if before is not None and after is not None and source:
            before, after = production_view(before), production_view(after)
        if before != after:
            diffs.append(path[len(APP) + 1:])
    for path in diffs:
        print(path)
    unexpected = sorted(set(diffs) - set(args.expect))
    missing = sorted(set(args.expect) - set(diffs))
    for path in unexpected:
        print(f"UNEXPECTED production change: {path}", file=sys.stderr)
    for path in missing:
        print(f"expected change absent: {path}", file=sys.stderr)
    return 1 if unexpected or missing else 0


if __name__ == "__main__":
    sys.exit(main())
