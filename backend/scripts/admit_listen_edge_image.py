"""Admit the listen-edge image a listen Helm deploy may roll (plan D D2).

``gcp_backend_listen_helm.yml`` takes ``listen_edge_image_digest``. Blank (the
default) leaves the listen-edge release untouched. Otherwise the value must be
exactly::

    gcr.io/<project>/listen-edge@sha256:<64 hex>

for the deploy's own project, and the image config must carry the admitted
checked-out SHA both as the ``org.opencontainers.image.revision`` label and as
``OMI_RELEASE_SHA`` in its environment — the way the build-only train stamps it
(``backend/scripts/role_images.py``, ``backend/edge/Dockerfile``). Anything else
fails before Helm runs. The registry read is the same ``docker buildx imagetools
inspect`` ``resolve_service_images.py`` uses, so a digest of another project,
another image, or another SHA is refused without pulling anything.

Outputs (GitHub env file, when a digest is admitted):
``LISTEN_EDGE_IMAGE_REPOSITORY`` and ``LISTEN_EDGE_IMAGE_DIGEST``.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable

IMAGE = "listen-edge"
REVISION_LABEL = "org.opencontainers.image.revision"
Inspector = Callable[[str], dict[str, Any]]


class ListenEdgeImageError(ValueError):
    pass


def inspect_image_config(ref: str) -> dict[str, Any]:
    result = subprocess.run(
        ["docker", "buildx", "imagetools", "inspect", ref, "--format", "{{json .Image.Config}}"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode:
        raise ListenEdgeImageError(f"cannot read the image config of {ref}: {result.stderr.strip()}")
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise ListenEdgeImageError(f"{ref}: unreadable image config ({error})") from error


def parse_ref(raw: str, *, project: str) -> tuple[str, str]:
    """Split ``gcr.io/<project>/listen-edge@sha256:<digest>`` into (repository, digest)."""
    ref = raw.strip()
    if not ref:
        raise ListenEdgeImageError("listen_edge_image_digest is blank")
    if any(ch.isspace() for ch in ref) or "," in ref:
        raise ListenEdgeImageError("listen_edge_image_digest must be one image reference, not a list")
    repository = f"gcr.io/{project}/{IMAGE}"
    match = re.fullmatch(re.escape(repository) + r"@(sha256:[0-9a-f]{64})", ref)
    if match is None:
        raise ListenEdgeImageError(f"{ref!r} is not {repository}@sha256:<64 hex>")
    return repository, match.group(1)


def admit(
    raw: str,
    *,
    project: str,
    sha: str,
    inspect: Inspector = inspect_image_config,
) -> dict[str, str]:
    """Return the repository/digest outputs, or an empty dict when ``raw`` is blank."""
    if not raw.strip():
        return {}
    if not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise ListenEdgeImageError("--sha must be the full 40-character checked-out commit SHA")
    repository, digest = parse_ref(raw, project=project)
    ref = f"{repository}@{digest}"
    config = inspect(ref)
    revision = (config.get("Labels") or {}).get(REVISION_LABEL)
    if revision != sha:
        raise ListenEdgeImageError(f"{ref} is labelled revision {revision!r}, not the admitted {sha}")
    if f"OMI_RELEASE_SHA={sha}" not in (config.get("Env") or []):
        raise ListenEdgeImageError(f"{ref} does not carry OMI_RELEASE_SHA={sha}")
    return {"LISTEN_EDGE_IMAGE_REPOSITORY": repository, "LISTEN_EDGE_IMAGE_DIGEST": digest}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--digest", default="", help="the listen_edge_image_digest workflow input")
    parser.add_argument("--project", required=True)
    parser.add_argument("--sha", required=True, help="the checked-out (admitted) commit SHA")
    parser.add_argument("--github-env", type=Path)
    args = parser.parse_args(argv)
    try:
        outputs = admit(args.digest, project=args.project, sha=args.sha, inspect=inspect_image_config)
    except ListenEdgeImageError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    if not outputs:
        print("listen-edge: no image digest given; the listen-edge release is left untouched")
        return 0
    lines = "".join(f"{key}={value}\n" for key, value in outputs.items())
    if args.github_env:
        with args.github_env.open("a", encoding="utf-8") as handle:
            handle.write(lines)
    print(lines, end="")
    print(f"listen-edge: admitted {outputs['LISTEN_EDGE_IMAGE_REPOSITORY']}@{outputs['LISTEN_EDGE_IMAGE_DIGEST']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
