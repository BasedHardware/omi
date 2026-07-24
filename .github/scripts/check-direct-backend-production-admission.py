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
GATEWAY_WORKFLOW = Path(".github/workflows/gcp_llm_gateway.yml")
GATEWAY_RELEASE_SHA_INPUT = (
    "      release_sha:\n"
    "        description: 'Production only: exact main SHA with a successful first-attempt Release Eligibility proof'\n"
    "        required: false\n"
    "        default: ''"
)


def validate_gateway_release_admission(text: str) -> list[str]:
    """Require the standalone gateway's production SHA to use the shared proof gate."""

    errors: list[str] = []
    for fragment, message in (
        (GATEWAY_RELEASE_SHA_INPUT, "gateway deploy must expose a production-only release_sha input"),
        (
            "ref: ${{ github.event.inputs.environment == 'prod' && 'main' || github.event.inputs.branch }}",
            "gateway development deploy must retain its branch checkout while production starts from main",
        ),
        (
            "sha_pattern='^[0-9a-f]{40}$'",
            "gateway production admission must reject malformed or missing release_sha",
        ),
        (
            '[[ ! "$DEPLOY_SHA" =~ $sha_pattern || "$DEPLOY_SHA" == "0000000000000000000000000000000000000000" ]]',
            "gateway production admission must reject malformed or missing release_sha",
        ),
        (
            'git cat-file -e "${DEPLOY_SHA}^{commit}"',
            "gateway production admission must require the requested SHA commit object",
        ),
        (
            'git merge-base --is-ancestor "$DEPLOY_SHA" "$main_sha"',
            "gateway production admission must require release_sha to be merged into fresh main",
        ),
        (
            "actions/workflows/release-eligibility.yml/runs?event=push&branch=main&status=completed&head_sha=${DEPLOY_SHA}",
            "gateway production admission must query Release Eligibility for the exact SHA",
        ),
        (
            ".github/scripts/verify_backend_release_admission.py",
            "gateway production admission must verify the Release Eligibility proof",
        ),
        (
            "--require-first-attempt",
            "gateway production admission must reject Release Eligibility reruns",
        ),
        (
            'git checkout --detach "$DEPLOY_SHA"',
            "gateway production admission must check out the admitted SHA",
        ),
        (
            '"$CHECKED_OUT_SHA" != "$DEPLOY_SHA"',
            "gateway production admission must bind image identity to the admitted checkout",
        ),
    ):
        if fragment not in text:
            errors.append(message)
    return errors


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
        persistent_image_writes = [
            line.strip()
            for line in re.findall(r"(?m)^[^\n]*\bIMAGE_TAG=[^\n]*>>\s*[\"']?\$GITHUB_ENV[\"']?[^\n]*$", text)
        ]
        image_authorities = []
        for line in text.splitlines():
            assignment = re.match(r"^\s*(?:run:\s+)?IMAGE_TAG=(.*)$", line)
            if assignment and not re.match(r"[\"']?\$\{?IMAGE_TAG\}?\b", assignment.group(1)):
                image_authorities.append(line.strip())
        if (
            text.count(IMAGE_IDENTITY) != 1
            or image_authorities != [IMAGE_IDENTITY]
            or persistent_image_writes != [PERSISTED_IMAGE_IDENTITY]
        ):
            errors.append(f"{relative} must establish its immutable image tag exactly once from checked-out HEAD")
        if relative == GATEWAY_WORKFLOW:
            errors.extend(validate_gateway_release_admission(text))
    return errors


if __name__ == "__main__":
    raise SystemExit(1 if validate(Path(".")) else 0)
