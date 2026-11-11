#!/usr/bin/env python3
"""Emit the full Pusher image source closure for promotion freshness checks.

Parses the final-stage COPY instructions from the registered Pusher Dockerfile
and prints one repo-relative source path per line — including the Helm chart — that
must be unchanged between a development-qualified SHA and the checked-out
production SHA.  Using the Dockerfile's own COPY closure instead of a hardcoded
two-directory subset prevents a stale digest from silently deploying newer shared
backend source (for example ``backend/utils/apps.py``) that the image baked in.

Plan B B3: a qualification may name the ``backend-pusher`` role image instead of
the fat ``pusher`` image.  Pass ``--image-repository`` with the repository the
qualification evidence names; a ``backend-pusher`` repository selects the
``pusher`` target of ``backend/Dockerfile.roles`` plus the role Dockerfile and
its venv lock as build inputs, so a role-image qualification cannot survive a
change to the image definition that actually built it.
"""

from __future__ import annotations

import argparse
import shlex
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FAT_DOCKERFILE = ROOT / "backend/pusher/Dockerfile"
ROLE_DOCKERFILE = ROOT / "backend/Dockerfile.roles"
ROLE_REPOSITORY_SUFFIX = "/backend-pusher"


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


def _stage_instructions(dockerfile: Path) -> tuple[dict[str, list[str]], list[str]]:
    """Map every named stage to its instructions, plus the final stage's."""
    stages: dict[str, list[str]] = {}
    order: list[str] = []
    current: list[str] | None = None
    for line in _logical_docker_lines(dockerfile):
        if line.upper().startswith("FROM "):
            tokens = shlex.split(line[5:])
            current = []
            name: str | None = None
            for index, token in enumerate(tokens):
                if token.upper() == "AS" and index + 1 < len(tokens):
                    name = tokens[index + 1]
            if name is None:
                name = f"__unnamed_{len(order)}__"
            stages[name] = current
            order.append(name)
            continue
        if current is not None:
            current.append(line)
    if not stages:
        raise SystemExit(f"{dockerfile}: no Docker stage found")
    return stages, stages[order[-1]]


def stage_copy_sources(dockerfile: Path, stage: str | None = None) -> list[str]:
    """Return repo-relative source paths copied in the named (default: final) stage."""
    stages, final_instructions = _stage_instructions(dockerfile)
    instructions = final_instructions if stage is None else stages[stage]
    sources: list[str] = []
    for line in instructions:
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


def final_stage_copy_sources(dockerfile: Path) -> list[str]:
    """Return repo-relative source paths copied in the Dockerfile's final stage."""
    return stage_copy_sources(dockerfile, None)


def closure_paths(image_repository: str = "") -> list[str]:
    """The freshness closure for the image the qualification evidence names."""
    if image_repository.endswith(ROLE_REPOSITORY_SUFFIX):
        # The role image's definition and venv lock are build inputs the COPY
        # closure alone does not cover; the venv lock also sits inside a copied
        # directory, but stay explicit so a COPY-list edit cannot drop it.
        image_sources = set(stage_copy_sources(ROLE_DOCKERFILE, "pusher"))
        image_sources |= {
            str(ROLE_DOCKERFILE.relative_to(ROOT)),
            "backend/pusher/pylock.toml",
        }
    else:
        image_sources = set(final_stage_copy_sources(FAT_DOCKERFILE))
    # Both images build from the repository root, so .dockerignore decides what
    # enters the build context; a change there can alter image contents without
    # touching any copied path (Codex round 2).
    # The Helm chart is a deployment input separate from the Docker image,
    # but a chart change also invalidates a dev qualification.
    return sorted(image_sources | {".dockerignore", "backend/charts/pusher"})


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--image-repository",
        default="",
        help="repository named by the qualification evidence; a backend-pusher repository selects the role-image closure",
    )
    args = parser.parse_args()
    print("\n".join(closure_paths(args.image_repository)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
