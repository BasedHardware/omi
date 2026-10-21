"""Admit one service's role-image digest for a standalone deploy (plan B B3).

``resolve_service_images.py`` covers the deploy-backend-stack train, where a
blank ``service_images`` input already means "every service keeps its current
image". The standalone gateway and pusher workflows and the messaging
maintenance job opt in one service at a time, so they admit a bare digest: the
repository is not caller-supplied but derived from ``runtime_images.json``,
which maps each service to the one role image it may move onto.

A digest is admitted only when it names an image in this project's registry,
labelled with the admitted SHA and carrying that role's ``OMI_ROLE`` -- the
same properties the stack resolver enforces -- so a stale or foreign digest
fails the deploy before any mutation.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Callable

if __package__ in (None, ""):  # direct execution: python3 backend/scripts/admit_role_image.py
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from resolve_service_images import ServiceImageError, inspect_image_config
else:
    from .resolve_service_images import ServiceImageError, inspect_image_config

REGISTRY_PATH = Path(__file__).resolve().parents[1] / "runtime_images.json"
DIGEST_PATTERN = re.compile(r"sha256:[0-9a-f]{64}")

Inspector = Callable[[str], dict[str, Any]]


def service_spec(service: str, registry: dict[str, Any] | None = None) -> dict[str, Any]:
    registry = registry or json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    spec = registry.get("services", {}).get(service)
    if not isinstance(spec, dict):
        raise ServiceImageError(
            f"{service!r} is not a service runtime_images.json declares; "
            f"the registry maps {sorted(registry.get('services', {}))}"
        )
    return spec


def admit(
    service: str,
    digest: str,
    *,
    project: str,
    admitted_sha: str,
    registry: dict[str, Any] | None = None,
    inspect: Inspector = inspect_image_config,
) -> dict[str, str]:
    spec = service_spec(service, registry)
    image, role = spec.get("image"), spec.get("role")
    if not isinstance(image, str) or not image or not isinstance(role, str) or not role:
        raise ServiceImageError(f"{service}: runtime_images.json does not map the service to a role image and role")
    repository = f"gcr.io/{project}/{image}"
    if not DIGEST_PATTERN.fullmatch(digest):
        raise ServiceImageError(f"{service}: {digest!r} is not sha256:<64 lowercase hex>")
    reference = f"{repository}@{digest}"
    config = inspect(reference)
    revision = (config.get("Labels") or {}).get("org.opencontainers.image.revision")
    if revision != admitted_sha:
        raise ServiceImageError(
            f"{service}: {reference} is labelled revision {revision!r}, not the admitted {admitted_sha}"
        )
    if f"OMI_ROLE={role}" not in (config.get("Env") or []):
        raise ServiceImageError(f"{service}: {reference} does not carry OMI_ROLE={role}")
    return {"repository": repository, "digest": digest, "reference": reference}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--service", required=True)
    parser.add_argument("--digest", required=True)
    parser.add_argument("--project", required=True)
    parser.add_argument("--admitted-sha", required=True)
    parser.add_argument(
        "--prefix",
        default="ROLE_IMAGE",
        help="variable prefix for the <PREFIX>_REPOSITORY/_DIGEST/_REFERENCE assignments (default ROLE_IMAGE)",
    )
    parser.add_argument("--github-env", type=Path, help="append the assignments to this file ($GITHUB_ENV)")
    args = parser.parse_args(argv)
    if not re.fullmatch(r"[A-Z][A-Z0-9_]*", args.prefix):
        parser.error("--prefix must be an upper-case environment variable prefix")
    try:
        admitted = admit(
            args.service,
            args.digest,
            project=args.project,
            admitted_sha=args.admitted_sha,
            inspect=inspect_image_config,
        )
    except ServiceImageError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    lines = "".join(f"{args.prefix}_{key.upper()}={value}\n" for key, value in admitted.items())
    if args.github_env:
        with args.github_env.open("a", encoding="utf-8") as handle:
            handle.write(lines)
    print(f"{lines}Role-image opt-in: {args.service} runs {admitted['reference']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
