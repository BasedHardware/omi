#!/usr/bin/env python3
"""Every pre-push gate that can fail on a missing toolchain must print its hatch.

AGENTS.md: "Every gated surface has a break-glass hatch. A broken gate is
never a reason to be stuck." scripts/pre-push honors a PRE_PUSH_SKIP_<X>
variable for each gate, so the hatch always exists. What is not guaranteed is
that a developer who trips the gate ever learns the variable's name -- and a
hatch nobody can find is not a hatch.

The real instance this was written for. `make setup` provisions the backend
venv only ("It does not install app or desktop runtime environments" --
AGENTS.md), while `.github/checks-manifest.yaml` remains in ROUTING_INPUTS but
selector-only changes no longer wake the Flutter codegen lane. A PR with an
actual generator input therefore hit:

    FAIL: Flutter generated-output checks need resolved app dependencies.
          Run: cd app && flutter pub get

with no mention of PRE_PUSH_SKIP_FLUTTER_GENERATED, telling a contributor with
no Flutter toolchain to install a multi-gigabyte SDK to push a docs change.
The same omission was live in check_workflows_if_needed's actionlint branch.
Both siblings in the same file already printed their hatch; these two were
simply missed, which is exactly the drift a ratchet catches and review does not.

THIS IS A STATIC CHECKER, NOT A BEHAVIORAL TEST. It reads the shell source and
matches text; it never executes pre-push. It cannot prove the message reaches
a terminal, that the variable is spelled correctly enough to work, or that the
skip branch honors it. It proves only that a failing branch mentions the hatch
name its own function honors. AGENTS.md requires static checkers be labeled as
such rather than mistaken for coverage, so: labeled.

Scope, deliberately narrow. Only functions that themselves honor a
PRE_PUSH_SKIP_<X> variable are checked, plus helpers reached from them
(HELPER_OWNERS), because a helper's failure is its caller's gate failing and
the caller's hatch is the one that clears it.
"""

from __future__ import annotations

import re
import sys
import tempfile
from pathlib import Path

# A helper has no skip variable of its own; failing inside it is the calling
# gate failing, so the caller's hatch is what a developer needs to be told.
HELPER_OWNERS = {
    "require_flutter_generated_prerequisites": "PRE_PUSH_SKIP_FLUTTER_GENERATED",
}

# How far back from a `return 1` to look for the hatch. The message block
# immediately precedes the return in every gate in this file; a larger window
# would let an unrelated function's hatch satisfy a later branch.
LOOKBACK = 10

FUNC_RE = re.compile(r"^([a-z_][a-z0-9_]*)\(\)\s*\{")
SKIP_RE = re.compile(r"PRE_PUSH_SKIP_[A-Z0-9_]+")


def parse_functions(lines: list[str]) -> dict[str, tuple[int, int]]:
    """Map function name -> (start, end) line indices.

    Relies on `}` in column zero closing a top-level function, which is how
    every function in scripts/pre-push is written. A nested block indented at
    column zero would break this; shfmt-style formatting prevents that.
    """
    funcs: dict[str, tuple[int, int]] = {}
    name: str | None = None
    start = 0
    for i, line in enumerate(lines):
        match = FUNC_RE.match(line)
        if match:
            name, start = match.group(1), i
        elif line == "}" and name is not None:
            funcs[name] = (start, i)
            name = None
    return funcs


def check_source(text: str) -> list[str]:
    lines = text.split("\n")
    errors = []

    for name, (start, end) in sorted(parse_functions(lines).items()):
        body = "\n".join(lines[start : end + 1])
        owned = set(SKIP_RE.findall(body))
        if name in HELPER_OWNERS:
            owned.add(HELPER_OWNERS[name])
        if not owned:
            continue

        for offset in range(end - start + 1):
            index = start + offset
            if not re.search(r"\breturn 1\b", lines[index]):
                continue
            # Only a line written to stderr counts. The `if
            # [ "${PRE_PUSH_SKIP_X:-}" = "1" ]` guard that honors the variable
            # also mentions it, and it sits at the top of every gate -- so
            # without this filter a short function's own skip branch would
            # satisfy the window and the check would pass on any omission.
            window = [line for line in lines[max(start, index - LOOKBACK) : index] if ">&2" in line]
            if any(skip in line for line in window for skip in owned):
                continue
            errors.append(
                f"scripts/pre-push:{index + 1}: {name} fails here without naming "
                f"its hatch ({' or '.join(sorted(owned))}). A developer missing "
                f"the toolchain cannot tell a real defect from an unprovisioned "
                f"machine. Print: "
                f'echo "      Deliberate hatch: {sorted(owned)[0]}=1 git push" >&2'
            )

    return errors


def self_test() -> None:
    good = "\n".join(
        [
            "check_thing_if_needed() {",
            '  if [ "${PRE_PUSH_SKIP_THING:-}" = "1" ]; then',
            "    return",
            "  fi",
            '  echo "FAIL: missing tool" >&2',
            '  echo "      Deliberate hatch: PRE_PUSH_SKIP_THING=1 git push" >&2',
            "  return 1",
            "}",
        ]
    )
    assert check_source(good) == [], "a disclosed hatch must pass"

    bad = good.replace('  echo "      Deliberate hatch: PRE_PUSH_SKIP_THING=1 git push" >&2\n', "")
    assert len(check_source(bad)) == 1, "an undisclosed hatch must fail"
    assert "check_thing_if_needed" in check_source(bad)[0], "the message must name the function"

    # A gate with no skip variable is out of scope and must not be reported.
    unscoped = "\n".join(["helper() {", '  echo "FAIL" >&2', "  return 1", "}"])
    assert check_source(unscoped) == [], "functions without a hatch are out of scope"

    # A helper borrows its caller's hatch; without the mapping it would be
    # unscoped and this regression would go unnoticed.
    helper_name = sorted(HELPER_OWNERS)[0]
    helper_bad = "\n".join([f"{helper_name}() {{", '  echo "FAIL" >&2', "  return 1", "}"])
    assert len(check_source(helper_bad)) == 1, "a mapped helper must be in scope"

    # Distance matters: a hatch far above a later failure must not satisfy it.
    far = "\n".join(
        [
            "check_far_if_needed() {",
            '  echo "      Deliberate hatch: PRE_PUSH_SKIP_FAR=1 git push" >&2',
            *["  : filler" for _ in range(LOOKBACK + 2)],
            "  return 1",
            "}",
        ]
    )
    assert len(check_source(far)) == 1, "a distant hatch must not satisfy a later failure"

    with tempfile.TemporaryDirectory() as tmp:
        missing = Path(tmp) / "absent"
        assert read(missing) is None, "a missing file must report, not raise"


def read(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def main() -> int:
    self_test()
    repo = Path(__file__).resolve().parents[2]
    target = repo / "scripts" / "pre-push"

    text = read(target)
    if text is None:
        print(f"FAIL: scripts/pre-push is missing or unreadable at {target}", file=sys.stderr)
        return 1

    errors = check_source(text)
    if errors:
        print("pre-push gates that fail without disclosing their hatch:\n", file=sys.stderr)
        for error in errors:
            print(f"  {error}", file=sys.stderr)
        print(
            "\nAGENTS.md: a broken gate is never a reason to be stuck. Every "
            "failure a developer can hit for an unprovisioned toolchain must "
            "name the variable that skips it.",
            file=sys.stderr,
        )
        return 1

    print("pre-push hatch disclosure OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
