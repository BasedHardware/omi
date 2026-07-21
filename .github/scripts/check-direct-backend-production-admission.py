#!/usr/bin/env python3
"""Inventory direct prod writers and require checked-out main source identity."""

from __future__ import annotations

from pathlib import Path
import re

WORKFLOWS = (
    Path(".github/workflows/gcp_backend_agent_proxy.yml"),
    Path(".github/workflows/gcp_backend_listen_helm.yml"),
    Path(".github/workflows/gcp_backend_pusher.yml"),
    Path(".github/workflows/gcp_llm_gateway.yml"),
)
CHECKOUT = "ref: ${{ github.event.inputs.environment == 'prod' && 'main' || github.event.inputs.branch }}"
ORIGIN_MAIN_FETCH = "git fetch --no-tags origin +refs/heads/main:refs/remotes/origin/main"
ANCESTRY_GUARD = 'git merge-base --is-ancestor "$CHECKED_OUT_SHA" origin/main'
HEAD_IDENTITY = "CHECKED_OUT_SHA=$(git rev-parse HEAD)"
IMAGE_IDENTITY = 'IMAGE_TAG=$(git rev-parse --short=7 "$CHECKED_OUT_SHA")'
DIAGNOSTIC = "ERROR: checked-out HEAD $CHECKED_OUT_SHA is not an ancestor of fresh origin/main"


def validate(root: Path) -> list[str]:
    errors: list[str] = []
    for relative in WORKFLOWS:
        path = root / relative
        text = path.read_text(encoding="utf-8") if path.exists() else ""
        if CHECKOUT not in text:
            errors.append(f"{relative} must reject caller refs for production checkout")
        if ORIGIN_MAIN_FETCH not in text or ANCESTRY_GUARD not in text:
            errors.append(f"{relative} must prove production source is on fresh origin/main")
        if HEAD_IDENTITY not in text or IMAGE_IDENTITY not in text:
            errors.append(f"{relative} must derive image identity from checked-out HEAD")
        if DIAGNOSTIC not in text:
            errors.append(f"{relative} must diagnose a rejected checked-out source identity")
        if "${GITHUB_SHA::7}" in text:
            errors.append(f"{relative} must not label built source with GITHUB_SHA")
        if text.count("uses: actions/checkout@v7") != 1:
            errors.append(f"{relative} must not check out a second source after production admission")
        if text.count(HEAD_IDENTITY) != 1:
            errors.append(f"{relative} must establish checked-out source identity exactly once")
        unsafe_image_assignment = re.search(
            r"(?m)^\s*(?:.*\brun:\s*)?IMAGE_TAG=(?:latest|\$?\{?GITHUB_SHA\}?|[0-9a-f]{7,})",
            text,
        )
        if text.count(IMAGE_IDENTITY) != 1 or unsafe_image_assignment:
            errors.append(f"{relative} must establish its immutable image tag exactly once from checked-out HEAD")
    return errors


if __name__ == "__main__":
    raise SystemExit(1 if validate(Path(".")) else 0)
