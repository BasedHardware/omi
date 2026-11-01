#!/usr/bin/env python3
"""Every workflow that checks out the repository must bound a stalled git fetch.

WHY: git has no stall timeout. A hosted-runner fetch from github.com intermittently
stops receiving data and then waits for the TCP reset, 7-10 minutes later, before
actions/checkout's built-in retry can run. On 2026-10-20 that cost Backend Hermetic
E2E run 39435458398 498 s of its 10-minute cap, and the same stall showed up in
other jobs across the last 300 runs. #22890 set GIT_HTTP_LOW_SPEED_LIMIT/TIME on six
workflows by hand and left about 66 others unbounded.

With both variables set, git aborts any transfer that stays under LIMIT bytes/s for
TIME seconds, and actions/checkout retries. They must be set at WORKFLOW level, so
they cover every job, every checkout and every script step that talks to git.

COMPOSITE ACTIONS COUNT AS CHECKOUTS. A local composite action that runs
actions/checkout cannot carry workflow-level env itself; it inherits the caller's.
So a workflow that calls such an action is held to the same rule as one that calls
actions/checkout directly. Without that, moving a checkout into an action would
launder away the bound while the guard still reported success.
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

REQUIRED_ENV = ("GIT_HTTP_LOW_SPEED_LIMIT", "GIT_HTTP_LOW_SPEED_TIME")
CHECKOUT = "actions/checkout"


def _load(path: Path):
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError:  # pragma: no cover - malformed YAML is another check's job
        return None


def _is_checkout(uses: object) -> bool:
    return isinstance(uses, str) and uses.split("@", 1)[0] == CHECKOUT


def _workflow_steps(document: dict):
    for job in (document.get("jobs") or {}).values():
        if isinstance(job, dict):
            for step in job.get("steps") or []:
                if isinstance(step, dict):
                    yield step


def _composite_steps(document: dict):
    runs = document.get("runs")
    if isinstance(runs, dict) and runs.get("using") == "composite":
        for step in runs.get("steps") or []:
            if isinstance(step, dict):
                yield step


def checkout_action_refs(repo_root: Path) -> set[str]:
    """`uses:` strings of local composite actions that run actions/checkout."""
    refs: set[str] = set()
    action_root = repo_root / ".github" / "actions"
    for path in sorted(action_root.glob("*/action.y*ml")):
        document = _load(path)
        if isinstance(document, dict) and any(
            _is_checkout(step.get("uses")) for step in _composite_steps(document)
        ):
            refs.add("./" + path.parent.relative_to(repo_root).as_posix())
    return refs


def _uses_checkout_action(uses: object, checkout_actions: set[str]) -> bool:
    """A local action call, including a staged copy of one.

    Deploy workflows check the action tree out under a prefix and call, for example,
    `./.github/firestore-workflow/.github/actions/firestore-readiness`. That is still
    the `./.github/actions/firestore-readiness` action, so match on the suffix.
    """
    if not isinstance(uses, str) or not uses.startswith("./"):
        return False
    uses = uses.rstrip("/")
    return any(uses == ref or uses.endswith("/" + ref[2:]) for ref in checkout_actions)


def check_workflow(path: Path, checkout_actions: set[str] = frozenset()) -> list[str]:
    document = _load(path)
    if not isinstance(document, dict):
        return []
    checks_out = any(
        _is_checkout(uses) or _uses_checkout_action(uses, checkout_actions)
        for uses in (step.get("uses") for step in _workflow_steps(document))
    )
    if not checks_out:
        return []
    env = document.get("env")
    env = env if isinstance(env, dict) else {}
    problems = []
    for key in REQUIRED_ENV:
        value = str(env.get(key, "")).strip()
        if not value.isdigit() or int(value) <= 0:
            problems.append(
                f"{path}: checks out the repository but workflow-level env has no positive {key}"
            )
    return problems


def main(argv: list[str]) -> int:
    repo_root = Path(argv[1]) if len(argv) > 1 else Path(".")
    workflow_root = repo_root / ".github" / "workflows"
    paths = sorted(workflow_root.glob("*.yml")) + sorted(workflow_root.glob("*.yaml"))
    checkout_actions = checkout_action_refs(repo_root)

    problems: list[str] = []
    for path in paths:
        problems.extend(check_workflow(path, checkout_actions))
    if problems:
        print("Workflows that check out without a git stall bound:\n", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        print(
            '\nAdd to the workflow-level env block:\n  GIT_HTTP_LOW_SPEED_LIMIT: "1000"\n'
            '  GIT_HTTP_LOW_SPEED_TIME: "60"',
            file=sys.stderr,
        )
        return 1
    print(f"checkout stall bounds OK ({len(paths)} workflow files)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
