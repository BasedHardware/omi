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


def main(argv: list[str]) -> int:
    root = Path(argv[1]) if len(argv) > 1 else Path(".github/workflows")
    paths = sorted(p for p in root.glob("*.yml")) + sorted(p for p in root.glob("*.yaml"))
    problems: list[str] = []
    for path in paths:
        problems.extend(check_workflow(path))
    if problems:
        print("Unbounded apt-get network calls in workflows:\n", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        print(
            "\nAdd -o Acquire::Retries=3 -o Acquire::http::Timeout=N -o Acquire::https::Timeout=N "
            "to the apt-get line, and timeout-minutes to the step.",
            file=sys.stderr,
        )
        return 1
    print(f"apt-get network bounds OK ({len(paths)} workflow files)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
