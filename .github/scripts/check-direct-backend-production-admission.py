#!/usr/bin/env python3
"""Inventory direct prod writers and require checked-out main source identity."""

from __future__ import annotations

from pathlib import Path

WORKFLOWS = (
    Path(".github/workflows/gcp_backend_agent_proxy.yml"),
    Path(".github/workflows/gcp_backend_listen_helm.yml"),
    Path(".github/workflows/gcp_backend_pusher.yml"),
    Path(".github/workflows/gcp_llm_gateway.yml"),
)
CHECKOUT = "ref: ${{ github.event.inputs.environment == 'prod' && 'main' || github.event.inputs.branch }}"


def validate(root: Path) -> list[str]:
    errors: list[str] = []
    for relative in WORKFLOWS:
        path = root / relative
        text = path.read_text(encoding="utf-8") if path.exists() else ""
        if CHECKOUT not in text:
            errors.append(f"{relative} must reject caller refs for production checkout")
        if (
            "git fetch --no-tags origin +refs/heads/main:refs/remotes/origin/main" not in text
            or "git merge-base --is-ancestor" not in text
        ):
            errors.append(f"{relative} must prove production source is on fresh origin/main")
        if "IMAGE_TAG=$(git rev-parse --short=7 HEAD)" not in text:
            errors.append(f"{relative} must derive image identity from checked-out HEAD")
        if "${GITHUB_SHA::7}" in text:
            errors.append(f"{relative} must not label built source with GITHUB_SHA")
    return errors


if __name__ == "__main__":
    raise SystemExit(1 if validate(Path(".")) else 0)
