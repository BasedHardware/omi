#!/usr/bin/env python3
"""Doc claims about code behavior must still be true.

check_agent_doc_references.py verifies that paths an agent doc *points at*
still exist. Nothing verifies that what a doc *asserts about behavior* is
still true -- a doc can keep every pointer valid while describing behavior
replaced long ago, and an agent reading it cannot tell current from stale.

Not hypothetical: an agent read a doc claiming `test.sh` "halts at the first
failing file" and proposed swapping its per-file process isolation for
`pytest -n auto --dist loadfile`. Already false -- test.sh had become a
worker pool that aggregates every failure instead of stopping at the first.
The swap would have regressed the suite: `loadfile` pins a file to a worker
but reuses the interpreter, and ~100 test files mutate `sys.modules` at
module scope (backend/docs/test_isolation.md), exactly what per-process
isolation prevents. The stale doc was the entire cause.

Real instances this would have caught, all found live on this branch:
  - .cursor/cloud-agent-environment.md claimed test.sh "halts at the first
    failing file"; it had become a worker pool that reports every failure.
  - .cursor/cloud-agent-environment.md claimed a test was broken by a rename
    with no fix in sight; a compatibility alias already fixed it.
  - .cursor/cloud-agent-environment.md claimed pytest-asyncio was unpinned
    and unconfigured; it is pinned and configured.

Each claim binds a literal substring in a doc to one in the code it
describes. Code anchor gone -> behavior changed, doc is stale: re-verify,
update the doc, then update the claim. Doc anchor gone -> the claim was
edited or reworded without re-verifying: re-verify and restore it or update
this table. The check cannot say which side is right, only that the two
stopped moving together -- exactly when a human or agent needs to look.

What this does NOT prove, stated plainly so nobody mistakes a pass for a
guarantee. Anchors are substring matches, so a surgical edit can keep the
token while removing the behavior: gut the isolation branch but leave the
default assignment, or drop one of two append sites. It catches the ordinary
case -- a refactor that removes the construct along with its token -- and
misses an adversarial one. It is a tripwire that forces a re-read, not proof
of correctness. Verifying meaning needs judgment, and a check that needs
judgment grows an allowlist.

For the same reason no claim binds a doc to another doc. Prose satisfying an
anchor proves only that someone still writes the words.
"""

from __future__ import annotations

import importlib.util
import sys
import tempfile
from pathlib import Path
from typing import NamedTuple


def read(path: Path) -> str | None:
    """None when the file cannot be read as text, rather than a traceback."""
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


CHECK_ID = "agent-doc-claims"


class Claim(NamedTuple):
    doc: str
    doc_anchor: str
    code: str
    code_anchor: str
    reason: str


CLAIMS: tuple[Claim, ...] = (
    Claim(
        doc=".cursor/cloud-agent-environment.md",
        doc_anchor="own pytest process",
        code="backend/test.sh",
        # Anchored on the default, not just the name: flipping the default to 0
        # leaves the variable in place and would slip past a bare-name anchor.
        code_anchor="BACKEND_PYTEST_FILE_ISOLATION:-1",
        reason="per-file process isolation is the documented execution model, and is the default.",
    ),
    Claim(
        doc=".cursor/cloud-agent-environment.md",
        doc_anchor="reports **all** failing files",
        code="backend/test.sh",
        # The append, not the name: a runner that early-exits on the first
        # failure could still declare the variable and pass a name-only anchor.
        code_anchor="failed_test_paths+=(",
        reason="the runner accumulates every failing file instead of halting at the first.",
    ),
)
# Deliberately no claim binding a doc to another doc. An anchor satisfied by
# prose proves only that someone still writes the words, which is the failure
# being guarded against, not a guard.


def check_claim(repo: Path, claim: Claim) -> list[str]:
    """A claim fails if either side's file or anchor is missing."""
    errors = []
    doc_text, code_text = read(repo / claim.doc), read(repo / claim.code)

    if doc_text is None:
        errors.append(
            f"{claim.doc}: missing or unreadable -- the doc this claim "
            f"points at is gone. Update or remove this claim in CLAIMS."
        )
    elif claim.doc_anchor not in doc_text:
        errors.append(
            f"{claim.doc}: doc no longer contains '{claim.doc_anchor}'. Someone "
            f"edited or reworded the claim about {claim.code} without "
            f"re-verifying it. Re-read {claim.code}, then restore the claim or "
            f"update this table. ({claim.reason})"
        )

    if code_text is None:
        errors.append(
            f"{claim.code}: missing or unreadable -- the code this claim "
            f"describes is gone. Update or remove this claim in CLAIMS."
        )
    elif claim.code_anchor not in code_text:
        errors.append(
            f"{claim.code}: code no longer contains '{claim.code_anchor}'. "
            f"Behavior changed and {claim.doc} now describes something gone. "
            f"Re-verify, update the doc, then update this claim. ({claim.reason})"
        )

    return errors


def self_test() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp)
        (repo / "backend").mkdir()
        doc, code = repo / "AGENTS.md", repo / "backend" / "test.sh"
        claim = Claim("AGENTS.md", "halts at the first", "backend/test.sh", "ISOLATION_FLAG", "test claim")

        doc.write_text("halts at the first failing file\n")
        code.write_text("use=${ISOLATION_FLAG:-1}\n")
        assert check_claim(repo, claim) == [], "both anchors present must pass"

        code.write_text("no flag here\n")
        assert "code no longer contains" in check_claim(repo, claim)[0], "code drift must fail"

        code.write_text("use=${ISOLATION_FLAG:-1}\n")
        doc.write_text("unrelated sentence\n")
        assert "doc no longer contains" in check_claim(repo, claim)[0], "doc drift must fail"

        doc.write_text("halts at the first failing file\n")
        missing_doc = check_claim(repo, claim._replace(doc="MISSING.md"))
        assert "missing or unreadable" in missing_doc[0], "missing doc file must fail"

        missing_code = check_claim(repo, claim._replace(code="backend/gone.sh"))
        assert "missing or unreadable" in missing_code[0], "missing code file must fail"

        # A file that exists but is not decodable text must report, not raise.
        code.write_bytes(b"\xff\xfe not utf-8\n")
        assert "missing or unreadable" in "".join(check_claim(repo, claim)), "undecodable code file must fail"


def _load_run_checks():
    """Import the sibling manifest reader by path, not via sys.path.

    A bare `sys.path.insert` would leave global import state mutated and would
    lose to an already-cached module of the same name.
    """
    location = Path(__file__).resolve().parent / "run_checks.py"
    spec = importlib.util.spec_from_file_location("_agent_doc_claims_run_checks", location)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {location}")
    module = importlib.util.module_from_spec(spec)
    # Register before exec: @dataclass resolves cls.__module__ through
    # sys.modules, and raises on a module that is not there yet. The name is
    # private so this cannot collide with an already-imported run_checks.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def check_trigger_coverage(repo: Path) -> list[str]:
    """This check must actually run on every file a claim names.

    Two ways the wiring can be wrong. The entry's command may not invoke this
    script, so the id proves nothing. Or a claim may name a path outside the
    entry's triggers, so the check never runs on the change that invalidates
    it -- the same drift this file guards against, hiding in its own wiring.

    A blind spot remains and cannot be closed from here: delete the manifest
    entry outright and this code simply never executes. The manifest contract
    test is what covers that.
    """
    run_checks = _load_run_checks()
    manifest_path = repo / ".github" / "checks-manifest.yaml"
    if not manifest_path.exists():
        return [f"{manifest_path} does not exist"]

    mine = next((c for c in run_checks.load_manifest(manifest_path).checks if c.id == CHECK_ID), None)
    if mine is None:
        return [f"{CHECK_ID} is not registered in .github/checks-manifest.yaml"]

    this_file = Path(__file__).resolve().relative_to(repo).as_posix()
    errors = []
    if not any(this_file in str(part) for part in mine.command):
        errors.append(
            f"the '{CHECK_ID}' manifest entry does not run {this_file}; its "
            f"command is {list(mine.command)}. An entry that matches by id "
            f"alone leaves this check registered but never executed."
        )

    # The claim paths, plus this file and the manifest: editing either of those
    # can invalidate the table just as surely as editing the code it describes.
    covered = {p for claim in CLAIMS for p in (claim.doc, claim.code)}
    covered |= {this_file, ".github/checks-manifest.yaml"}
    errors += [
        f"{path}: no '{CHECK_ID}' trigger matches it, so editing it would not "
        f"run this check. Add it to that check's triggers."
        for path in sorted(covered)
        if not any(run_checks.trigger_matches(pattern, path) for pattern in mine.triggers)
    ]
    return errors


def main() -> int:
    self_test()
    repo = Path(__file__).resolve().parents[2]
    errors = [e for claim in CLAIMS for e in check_claim(repo, claim)]
    errors += check_trigger_coverage(repo)
    if errors:
        print("Agent doc claims no longer match the code they describe:\n", file=sys.stderr)
        for e in errors:
            print(f"  {e}", file=sys.stderr)
        print(
            "\nEach claim binds a doc sentence to the code that makes it true. "
            "Re-verify both sides, fix whichever drifted, and update the CLAIMS "
            "table in this file to match.",
            file=sys.stderr,
        )
        return 1
    print("agent doc claims OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
