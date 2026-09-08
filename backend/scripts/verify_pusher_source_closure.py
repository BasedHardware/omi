#!/usr/bin/env python3
"""Emit the full Pusher image source closure for promotion freshness checks.

Parses the final-stage COPY instructions from the registered Pusher Dockerfile
and prints the repo-relative source paths — plus the Helm chart directory — that
must be unchanged between a development-qualified SHA and the checked-out
production SHA.  Using the Dockerfile's own COPY closure instead of a hardcoded
two-directory subset prevents a stale digest from silently deploying newer shared
backend source (for example ``backend/utils/apps.py``) that the image baked in.
"""

from __future__ import annotations

import shlex
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _logical_docker_lines(path: Path) -> list[str]:
    """Fold Dockerfile continuation lines and strip comments/blanks."""
    logical_lines: list[str] = []
    pending = ""
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        pending = f"{pending}{stripped}" if pending else stripped
        if pending.endswith("\\"):
            pending = pending[:-1].rstrip() + " "
            continue
        logical_lines.append(pending)
        pending = ""
    if pending:
        logical_lines.append(pending)
    return logical_lines


def final_stage_copy_sources(dockerfile: Path) -> list[str]:
    """Return repo-relative source paths copied in the Dockerfile's final stage."""
    stages: list[list[str]] = []
    current: list[str] | None = None
    for line in _logical_docker_lines(dockerfile):
        if line.upper().startswith("FROM "):
            current = []
            stages.append(current)
            continue
        if current is not None:
            current.append(line)
    if not stages:
        raise SystemExit(f"{dockerfile}: no Docker stage found")

    sources: list[str] = []
    for line in stages[-1]:
        if not line.upper().startswith("COPY "):
            continue
        tokens = shlex.split(line[5:])
        # Skip multi-stage --from= copies (those reference builder artifacts,
        # not repo source that can drift between qualification and deploy).
        if any(token.startswith("--from=") for token in tokens):
            continue
        tokens = [token for token in tokens if not token.startswith("--")]
        if len(tokens) < 2:
            raise SystemExit(f"cannot parse COPY instruction in {dockerfile}: {line}")
        sources.extend(tokens[:-1])
    return sources


def main() -> int:
    dockerfile = ROOT / "backend/pusher/Dockerfile"
    image_sources = final_stage_copy_sources(dockerfile)
    # The Helm chart is a deployment input separate from the Docker image,
    # but a chart change also invalidates a dev qualification.
    paths = sorted(set(image_sources) | {"backend/charts/pusher"})
    print(" ".join(paths))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
