#!/usr/bin/env python3
"""Static checker: launcher-test discovery skips are derived, not hand-listed.

`test.sh` and the "Desktop launcher script tests" step in
`.github/workflows/desktop-swift-ci.yml` both discover every
`desktop/macos/tests/test-*.sh` instead of listing them, so a new test runs in
both places automatically. A few discovered scripts cannot run under that loop —
they need a running app's automation token, or an installed named bundle path —
and each declares that in its own header with a `# discovery-skip:` line.
`test.sh` derives its skips from that marker; the CI step carries a hand list
because the loop is inlined in YAML.

#11747: the CI step skipped `test-mounted-navigation-latency.sh` and
`test-named-bundle-resources.sh` while `test.sh` skipped nothing, so `test.sh`
aborted on them under `set -e` and never reached its Python or Swift sections.
The membership was hand-listed in one loop and absent from the other
(FC-hand-listed-test-isolation-membership), so this checker holds the two loops
to the marked set:

1. every script declaring `# discovery-skip:` is in the CI step's hand list;
2. the CI step's hand list contains nothing else;
3. `test.sh` still derives its skips from the marker;
4. every script named in either place exists;
5. a script that requires a positional argument declares the marker — the
   property that made #11747 reachable, so a new one cannot repeat it silently.

This is a static checker over source, not behavioral coverage of the loops.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

MACOS_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = MACOS_DIR.parent.parent
RUNNER = MACOS_DIR / "test.sh"
WORKFLOW = REPO_ROOT / ".github/workflows/desktop-swift-ci.yml"
TESTS_DIR = MACOS_DIR / "tests"

MARKER = "# discovery-skip:"
# A `case` pattern line listing one or more discovered tests, e.g.
#   tests/test-a.sh|tests/test-b.sh)
CASE_PATTERN = re.compile(r"^\s*(tests/test-[^)]*)\)\s*$")
# A guard that rejects a missing positional argument, e.g. `if [[ $# -ne 1 ]]`.
ARGUMENT_GUARD = re.compile(r"\$#\s*(-ne|-lt|-eq|==|!=)\s*\d")
NONZERO_EXIT = re.compile(r"\bexit\s+[1-9]")


def rel(path: Path) -> str:
    return str(path.relative_to(REPO_ROOT))


def marked_tests() -> set[str]:
    """Scripts that declare they cannot run under the discovery loop."""
    return {
        f"tests/{path.name}"
        for path in sorted(TESTS_DIR.glob("test-*.sh"))
        if MARKER in path.read_text()
    }


def requires_argument(path: Path) -> bool:
    """True when the script bails out non-zero on a missing positional argument.

    An argument count guard alone is not enough — a script may compare `$#` to
    default an optional argument. The property that breaks the discovery loop is
    the guard exiting non-zero, so require both.
    """
    lines = path.read_text().splitlines()
    return any(
        ARGUMENT_GUARD.search(line) and any(NONZERO_EXIT.search(nxt) for nxt in lines[index + 1 : index + 6])
        for index, line in enumerate(lines)
    )


def workflow_skips() -> set[str]:
    """The hand list the inlined CI loop carries."""
    matches = [
        match.group(1) for line in WORKFLOW.read_text().splitlines() if (match := CASE_PATTERN.match(line))
    ]
    if len(matches) > 1:
        raise SystemExit(
            f"FAIL: found {len(matches)} launcher-test skip lists in {rel(WORKFLOW)}. Keep the step's "
            "skips in one `case` pattern line so this checker can compare them."
        )
    return {name.strip() for name in matches[0].split("|") if name.strip()} if matches else set()


def main() -> int:
    marked = marked_tests()
    workflow = workflow_skips()
    failures = []

    if MARKER not in RUNNER.read_text():
        failures.append(
            f"{rel(RUNNER)} no longer derives its launcher-test skips from `{MARKER}`. Without the "
            "derivation a marked script runs in the loop that cannot supply its prerequisite and "
            "aborts the runner under `set -e` (#11747)."
        )

    unlisted = sorted(marked - workflow)
    if unlisted:
        failures.append(
            f"declared `{MARKER}` but not skipped by the CI step in {rel(WORKFLOW)}: {unlisted}. "
            "Add them to that step's `case` pattern line — the CI loop is inlined in YAML and cannot "
            "read the marker."
        )

    unmarked = sorted(workflow - marked)
    if unmarked:
        failures.append(
            f"skipped by the CI step in {rel(WORKFLOW)} but not declared with `{MARKER}`: {unmarked}. "
            f"Either declare the prerequisite in the script's header so {rel(RUNNER)} skips it too, or "
            "drop it from the CI step's list."
        )

    for name in sorted(marked | workflow):
        if not (MACOS_DIR / name).is_file():
            failures.append(f"skipped script does not exist: {name} (stale skip after a rename?)")

    for path in sorted(TESTS_DIR.glob("test-*.sh")):
        name = f"tests/{path.name}"
        if name not in marked and requires_argument(path):
            failures.append(
                f"{name} requires a positional argument the discovery loop cannot supply but does not "
                f"declare `{MARKER}`. It fails on every machine and aborts the runner (#11747)."
            )

    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        return 1

    print(f"launcher-test discovery skips are derived and agree ({len(marked)} skipped: {', '.join(sorted(marked))})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
