#!/usr/bin/env python3
"""Every apt-get network call in a workflow must be bounded, and its step capped.

WHY: apt against the hosted runners' default Azure Ubuntu mirror can connect and
then never complete the transfer. It has no built-in timeout, so the step produces
no further output and the job runs until its ceiling - six hours, on a job that has
no explicit `timeout-minutes` - and then reports `cancelled`, which reads as an
infrastructure mystery rather than a stalled mirror. Two workflows were fixed by
hand after exactly that; a third line was left unbounded in a step whose own
comment said "Bound apt's network calls explicitly".

A comment is not a guard. Derive the requirement from the source signal - an
apt-get subcommand that touches the network - so a new one cannot be added
unbounded, and so the next person does not have to remember.

Two requirements per offending line:
  * `-o Acquire::Retries=N` plus http and https `Acquire::*::Timeout`, so a stalled
    mirror fails over quickly instead of hanging.
  * `timeout-minutes` on the enclosing step, as a backstop for anything the
    acquire options do not cover (dpkg, a debconf prompt, a wedged post-install).

COMPOSITE ACTIONS ARE IN SCOPE TOO, AND THE SECOND REQUIREMENT MOVES WHEN THEY ARE.
A bounded apt call may now legitimately live in `.github/actions/*/action.yml` rather
than in a workflow - #12194 moves the hermetic-gauntlet redis install into
`.github/actions/install-redis-server` so three jobs share one copy. Scanning only
`.github/workflows/*.yml` would leave that home unguarded, so "a new one cannot be
added unbounded" would quietly stop being true for the only place the bounded calls
still live.

Pointing the old checker at an `action.yml` would NOT have caught it either: a
composite action keeps its steps under `runs.steps`, not `jobs.<id>.steps`, so
`check_workflow` finds no steps and returns clean. The blind spot fails open.

`timeout-minutes` is not a valid key on a composite-action step - GitHub rejects the
workflow that uses one - so the ceiling cannot be enforced where the apt line now is.
It is enforced at every call site instead (`check_workflow_callers`). That split is
the whole point: without it, moving an install into an action would launder away the
backstop while the guard still reported success.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

NETWORK_SUBCOMMANDS = ("update", "install", "upgrade", "dist-upgrade", "build-dep", "source", "download")
REQUIRED_OPTIONS = ("Acquire::Retries", "Acquire::http::Timeout", "Acquire::https::Timeout")

_APT_LINE = re.compile(r"\bapt-get\b(?P<rest>.*)")


def _network_apt_lines(script: str) -> list[str]:
    offending = []
    for raw in script.splitlines():
        line = raw.strip()
        match = _APT_LINE.search(line)
        if not match:
            continue
        rest = match.group("rest")
        # The subcommand is the first token that is not an option or its value.
        tokens = [t for t in rest.split() if not t.startswith("-")]
        # Drop values consumed by `-o key=value` style options already filtered above.
        if not any(token in NETWORK_SUBCOMMANDS for token in tokens):
            continue
        offending.append(line)
    return offending


def _iter_steps(document: dict):
    for job_name, job in (document.get("jobs") or {}).items():
        if not isinstance(job, dict):
            continue
        for index, step in enumerate(job.get("steps") or []):
            if isinstance(step, dict):
                yield job_name, index, step


def check_workflow(path: Path) -> list[str]:
    try:
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as error:  # pragma: no cover - malformed YAML is another check's job
        return [f"{path}: could not parse ({error.__class__.__name__})"]
    if not isinstance(document, dict):
        return []

    problems: list[str] = []
    for job_name, index, step in _iter_steps(document):
        script = step.get("run")
        if not isinstance(script, str):
            continue
        lines = _network_apt_lines(script)
        if not lines:
            continue
        label = step.get("name") or f"step #{index}"
        for line in lines:
            missing = [option for option in REQUIRED_OPTIONS if option not in line]
            if missing:
                problems.append(
                    f"{path}: job {job_name!r}, {label!r}: apt-get network call is unbounded "
                    f"(missing {', '.join(missing)}): {line}"
                )
        if "timeout-minutes" not in step:
            problems.append(
                f"{path}: job {job_name!r}, {label!r}: step runs apt-get over the network "
                f"but declares no timeout-minutes backstop"
            )
    return problems


def _composite_steps(document: dict):
    """Yield the steps of a composite action. Other action kinds have no `run:` steps.

    A composite action's steps live under `runs.steps`, not `jobs.<id>.steps`, so
    `_iter_steps` yields nothing for one. That is why pointing the workflow checker at an
    `action.yml` returns clean rather than complaining: the shape simply does not match.
    """
    runs = document.get("runs")
    if not isinstance(runs, dict) or runs.get("using") != "composite":
        return
    for index, step in enumerate(runs.get("steps") or []):
        if isinstance(step, dict):
            yield index, step


def check_action(path: Path) -> list[str]:
    """Composite actions: require the acquire bounds, but NOT `timeout-minutes`.

    `timeout-minutes` is not a valid key on a composite-action step - GitHub rejects the
    workflow that uses it. The backstop can therefore only live on the CALLER, which is
    what `check_workflow_callers` enforces. Requiring it here would be unsatisfiable, and
    a guard nobody can satisfy gets deleted rather than obeyed.
    """
    try:
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as error:  # pragma: no cover - malformed YAML is another check's job
        return [f"{path}: could not parse ({error.__class__.__name__})"]
    if not isinstance(document, dict):
        return []

    problems: list[str] = []
    for index, step in _composite_steps(document):
        script = step.get("run")
        if not isinstance(script, str):
            continue
        label = step.get("name") or f"step #{index}"
        for line in _network_apt_lines(script):
            missing = [option for option in REQUIRED_OPTIONS if option not in line]
            if missing:
                problems.append(
                    f"{path}: {label!r}: apt-get network call is unbounded "
                    f"(missing {', '.join(missing)}): {line}"
                )
    return problems


def _action_reference(repo_root: Path, action_path: Path) -> str:
    """The `uses:` string a workflow writes to call this local action."""
    return "./" + action_path.parent.relative_to(repo_root).as_posix()


def check_workflow_callers(path: Path, apt_action_refs: set[str]) -> list[str]:
    """Every step that `uses:` an apt-running local action must cap itself.

    This is the other half of the bound. The acquire options are enforced inside the
    action; the ceiling cannot be, so it is enforced at each call site. Without this the
    guard would report success on a tree where an unbounded-ceiling apt install had simply
    been moved one file down.
    """
    if not apt_action_refs:
        return []
    try:
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as error:  # pragma: no cover - malformed YAML is another check's job
        return [f"{path}: could not parse ({error.__class__.__name__})"]
    if not isinstance(document, dict):
        return []

    problems: list[str] = []
    for job_name, index, step in _iter_steps(document):
        uses = step.get("uses")
        if not isinstance(uses, str) or uses.rstrip("/") not in apt_action_refs:
            continue
        if "timeout-minutes" not in step:
            label = step.get("name") or f"step #{index}"
            problems.append(
                f"{path}: job {job_name!r}, {label!r}: uses {uses}, which runs apt-get over "
                f"the network, but declares no timeout-minutes backstop"
            )
    return problems


def main(argv: list[str]) -> int:
    # The argument is the REPOSITORY ROOT, because the check now spans two directories.
    # The historical form - a path to the workflows directory - is still accepted so an
    # existing caller does not silently start scanning nothing.
    given = Path(argv[1]) if len(argv) > 1 else Path(".")
    if given.name in ("workflows", "actions") and given.parent.name == ".github":
        repo_root = given.parent.parent
    else:
        repo_root = given

    workflow_root = repo_root / ".github" / "workflows"
    action_root = repo_root / ".github" / "actions"

    paths = (sorted(p for p in workflow_root.glob("*.yml"))
             + sorted(p for p in workflow_root.glob("*.yaml")))
    action_paths = (sorted(action_root.glob("*/action.yml"))
                    + sorted(action_root.glob("*/action.yaml")))

    problems: list[str] = []
    apt_action_refs: set[str] = set()
    for path in action_paths:
        problems.extend(check_action(path))
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        if isinstance(document, dict) and any(
            _network_apt_lines(step.get("run"))
            for _, step in _composite_steps(document)
            if isinstance(step.get("run"), str)
        ):
            apt_action_refs.add(_action_reference(repo_root, path))

    for path in paths:
        problems.extend(check_workflow(path))
        problems.extend(check_workflow_callers(path, apt_action_refs))
    if problems:
        print("Unbounded apt-get network calls in workflows:\n", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        print(
            "\nAdd -o Acquire::Retries=3 -o Acquire::http::Timeout=N -o Acquire::https::Timeout=N "
            "to the apt-get line, and timeout-minutes to the step. In a composite action the "
            "ceiling belongs on each caller instead - timeout-minutes is not a valid key on a "
            "composite-action step.",
            file=sys.stderr,
        )
        return 1
    print(
        f"apt-get network bounds OK ({len(paths)} workflow files, "
        f"{len(action_paths)} composite actions)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
