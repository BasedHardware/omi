#!/usr/bin/env python3
"""Report how far serving desktop backends lag origin/main at promotion time.

Visibility only: exit 0 unless --strict is set. Missing or malformed serving
SHAs are recorded as unknown, never invented.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
SUBJECT_CAP = 30

# Desktop-backend image copies the whole backend/ tree (Dockerfile.desktop_backend).
DESKTOP_BACKEND_PATHS = (
    "backend/Dockerfile.desktop_backend",
    "backend/pylock.runtime.toml",
    "backend/",
)
# Shared API backend: desktop-relevant Python and update control plane only.
API_BACKEND_PATHS = (
    "backend/routers/desktop_*.py",
    "backend/routers/updates.py",
    "backend/utils/desktop*",
    "backend/database/desktop_*.py",
)


@dataclass(frozen=True)
class ServiceDrift:
    service: str
    serving_sha: str
    deployed_at: str | None
    commits_behind: int | None
    subjects: tuple[str, ...]
    unknown: bool


def _load_json(path: Path | None) -> dict[str, Any]:
    if path is None or not path.is_file():
        return {}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


def serving_sha(health: dict[str, Any]) -> str | None:
    value = health.get("backend_release_sha")
    if isinstance(value, str) and SHA_RE.fullmatch(value):
        return value
    return None


def deployed_at(health: dict[str, Any]) -> str | None:
    for key in ("deployed_at", "revision_create_time", "started_at"):
        value = health.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _git_env() -> dict[str, str]:
    # Pre-push/preflight hooks export GIT_DIR for the outer checkout. Fixture
    # repos and `-C` probes must not inherit that namespace.
    return {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=False,
        capture_output=True,
        text=True,
        env=_git_env(),
    )


def commits_since(repo: Path, serving: str, base: str, paths: tuple[str, ...]) -> tuple[int, tuple[str, ...]] | None:
    probe = _git(repo, "cat-file", "-e", f"{serving}^{{commit}}")
    if probe.returncode != 0:
        return None
    listed = _git(repo, "log", "--format=%s", f"{serving}..{base}", "--", *paths)
    if listed.returncode != 0:
        return None
    subjects = tuple(line for line in listed.stdout.splitlines() if line)
    return len(subjects), subjects[:SUBJECT_CAP]


def measure(
    *,
    service: str,
    health: dict[str, Any],
    repo: Path,
    base: str,
    paths: tuple[str, ...],
) -> ServiceDrift:
    sha = serving_sha(health)
    if sha is None:
        return ServiceDrift(service, "unknown", deployed_at(health), None, (), True)
    measured = commits_since(repo, sha, base, paths)
    if measured is None:
        return ServiceDrift(service, sha, deployed_at(health), None, (), True)
    count, subjects = measured
    return ServiceDrift(service, sha, deployed_at(health), count, subjects, False)


def render_table(rows: tuple[ServiceDrift, ...]) -> str:
    include_deployed = any(row.deployed_at for row in rows)
    headers = ["Service", "Serving SHA", "Commits behind `main`", "Subjects (cap 30)"]
    if include_deployed:
        headers = ["Service", "Serving SHA", "Deployed at", "Commits behind `main`", "Subjects (cap 30)"]
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        behind = "unknown" if row.commits_behind is None else str(row.commits_behind)
        subjects = "<br>".join(row.subjects) if row.subjects else ("unknown" if row.unknown else "none")
        cells = [row.service, f"`{row.serving_sha}`", behind, subjects]
        if include_deployed:
            cells = [
                row.service,
                f"`{row.serving_sha}`",
                row.deployed_at or "—",
                behind,
                subjects,
            ]
        lines.append("| " + " | ".join(cells) + " |")
    lines.append("")
    lines.append(
        "This table is provenance, not a compatibility gate. A non-zero "
        "count means `main` has commits those services have not yet deployed."
    )
    return "\n".join(lines) + "\n"


def report(
    *,
    desktop_health: dict[str, Any],
    api_health: dict[str, Any],
    repo: Path,
    base: str,
    summary_file: Path | None,
    strict: bool,
) -> int:
    rows = (
        measure(
            service="desktop-backend",
            health=desktop_health,
            repo=repo,
            base=base,
            paths=DESKTOP_BACKEND_PATHS,
        ),
        measure(
            service="api-backend",
            health=api_health,
            repo=repo,
            base=base,
            paths=API_BACKEND_PATHS,
        ),
    )
    markdown = "## Backend drift at promotion\n\n" + render_table(rows)
    sys.stdout.write(markdown)
    if summary_file is not None:
        with summary_file.open("a", encoding="utf-8") as handle:
            handle.write(markdown)
            if not markdown.endswith("\n"):
                handle.write("\n")
    if strict and any((row.commits_behind or 0) > 0 or row.unknown for row in rows):
        return 1
    return 0


def _self_test() -> int:
    import tempfile

    with tempfile.TemporaryDirectory() as raw:
        repo = Path(raw)
        def git(*args: str) -> None:
            subprocess.run(
                [
                    "git",
                    "-c",
                    "user.name=drift-self-test",
                    "-c",
                    "user.email=drift@example.test",
                    "-c",
                    "core.hooksPath=/dev/null",
                    "-c",
                    "commit.gpgsign=false",
                    *args,
                ],
                cwd=repo,
                check=True,
                capture_output=True,
                text=True,
                env=_git_env(),
            )

        git("init", "-b", "main")
        (repo / "backend" / "routers").mkdir(parents=True)
        (repo / "backend" / "Dockerfile.desktop_backend").write_text("FROM python\n", encoding="utf-8")
        (repo / "backend" / "routers" / "updates.py").write_text("old = True\n", encoding="utf-8")
        git("add", ".")
        git("commit", "-m", "base serving revision")
        serving = _git(repo, "rev-parse", "HEAD").stdout.strip()
        (repo / "backend" / "routers" / "updates.py").write_text("new = True\n", encoding="utf-8")
        git("add", "backend/routers/updates.py")
        git("commit", "-m", "desktop update control plane")
        (repo / "backend" / "unrelated.py").write_text("noise\n", encoding="utf-8")
        git("add", "backend/unrelated.py")
        git("commit", "-m", "unrelated backend change")

        known = measure(
            service="api-backend",
            health={"backend_release_sha": serving},
            repo=repo,
            base="HEAD",
            paths=API_BACKEND_PATHS,
        )
        if known.commits_behind != 1 or known.subjects != ("desktop update control plane",):
            raise SystemExit(f"expected one updates.py commit, got {known}")

        desktop = measure(
            service="desktop-backend",
            health={"backend_release_sha": serving},
            repo=repo,
            base="HEAD",
            paths=DESKTOP_BACKEND_PATHS,
        )
        if desktop.commits_behind != 2:
            raise SystemExit(f"desktop-backend should see both backend/ commits, got {desktop}")

        missing = measure(
            service="api-backend",
            health={},
            repo=repo,
            base="HEAD",
            paths=API_BACKEND_PATHS,
        )
        if missing.serving_sha != "unknown" or not missing.unknown:
            raise SystemExit(f"missing SHA must be unknown, got {missing}")

        table = render_table((missing,))
        if "`unknown`" not in table or "Deployed at" in table:
            raise SystemExit(f"unknown SHA table was wrong: {table}")

        strict = report(
            desktop_health={"backend_release_sha": serving},
            api_health={},
            repo=repo,
            base="HEAD",
            summary_file=None,
            strict=True,
        )
        if strict != 1:
            raise SystemExit("strict mode must fail when a SHA is unknown or commits lag")
        print("desktop backend drift self-test OK")
        return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--desktop-backend-health", type=Path)
    parser.add_argument("--api-backend-health", type=Path)
    parser.add_argument("--base", default="origin/main")
    parser.add_argument("--repo", type=Path, default=ROOT)
    parser.add_argument("--summary-file", type=Path)
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)
    if args.self_test:
        return _self_test()
    return report(
        desktop_health=_load_json(args.desktop_backend_health),
        api_health=_load_json(args.api_backend_health),
        repo=args.repo,
        base=args.base,
        summary_file=args.summary_file,
        strict=args.strict,
    )


if __name__ == "__main__":
    raise SystemExit(main())
