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
PERSISTED_IMAGE_IDENTITY = 'echo "IMAGE_TAG=$IMAGE_TAG" >> "$GITHUB_ENV"'


def _has_unadmitted_persistent_image_write(text: str) -> bool:
    """Reject IMAGE_TAG writes to GITHUB_ENV across complete shell run blocks.

    YAML literal blocks can split a printf/redirection across lines and heredocs
    put the assignment after the redirection. Search both directions after
    removing the one exact admitted persistence command.
    """
    lines = text.splitlines()
    for index, line in enumerate(lines):
        match = re.match(r"^(?P<indent>\s*)run:\s*(?P<command>.*)$", line)
        if not match:
            continue
        command = match.group("command")
        if command in {"|", ">", "|-", ">-"}:
            indent = len(match.group("indent"))
            block: list[str] = []
            for body_line in lines[index + 1 :]:
                if body_line.strip() and len(body_line) - len(body_line.lstrip()) <= indent:
                    break
                block.append(body_line)
            command = "\n".join(block)
        residual = command.replace(PERSISTED_IMAGE_IDENTITY, "")
        direct_write = re.search(
            r"(?m)(?:(?:echo|printf)\b[^\n]*\bIMAGE_TAG\s*=[^\n]*(?:\\\s*\n[^\n]*)*|\bIMAGE_TAG\s*=[^\n]*)>>\s*['\"]?\$GITHUB_ENV['\"]?",
            residual,
        )
        heredoc_write = re.search(
            r"(?s)(?:cat|tee)\b.*?(?:>>|>)\s*['\"]?\$GITHUB_ENV['\"]?.*?<<.*?\n.*?\bIMAGE_TAG\s*=",
            residual,
        )
        if direct_write or heredoc_write:
            return True
    return False


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
        image_authorities = []
        for line in text.splitlines():
            assignment = re.match(r"^\s*(?:run:\s+)?IMAGE_TAG=(.*)$", line)
            if assignment and not re.match(r"[\"']?\$\{?IMAGE_TAG\}?\b", assignment.group(1)):
                image_authorities.append(line.strip())
        if (
            text.count(IMAGE_IDENTITY) != 1
            or image_authorities != [IMAGE_IDENTITY]
            or text.count(PERSISTED_IMAGE_IDENTITY) != 1
            or _has_unadmitted_persistent_image_write(text)
        ):
            errors.append(f"{relative} must establish its immutable image tag exactly once from checked-out HEAD")
    return errors


if __name__ == "__main__":
    raise SystemExit(1 if validate(Path(".")) else 0)
