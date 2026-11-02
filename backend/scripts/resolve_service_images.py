"""Resolve the image each deploy-backend-stack service ships (plan B B2 opt-in).

Empty ``service_images`` (the default) resolves every service to exactly the
image the stack ships today: the fat ``gcr.io/<project>/<service>:<short sha>``
for the Cloud Run four and listen, and ``llm-gateway:<short sha>`` for the
gateway. A deploy opts a service onto its role image by passing
``service=<ref>`` pairs, separated by spaces or commas, for example::

    backend=gcr.io/based-hardware-dev/backend-api@sha256:<64 hex>

Each ref must be a digest in this project's registry, of the role image
``runtime_images.json`` maps that service to, labelled with the admitted SHA
and carrying that role's ``OMI_ROLE``. The gcp_backend.yml build-only train
publishes those digests and prints the ready-made value. Anything else fails
the deploy before it mutates a service.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable

REGISTRY_PATH = Path(__file__).resolve().parents[1] / "runtime_images.json"
# Today all four Cloud Run services ship the one fat image built for the base service.
CLOUD_RUN_SERVICES = ("backend", "backend-sync", "backend-sync-backfill", "backend-integration")
SERVICES = (*CLOUD_RUN_SERVICES, "backend-listen", "llm-gateway")

Inspector = Callable[[str], dict[str, Any]]


class ServiceImageError(ValueError):
    pass


def inspect_image_config(ref: str) -> dict[str, Any]:
    result = subprocess.run(
        ["docker", "buildx", "imagetools", "inspect", ref, "--format", "{{json .Image.Config}}"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode:
        raise ServiceImageError(f"cannot read the image config of {ref}: {result.stderr.strip()}")
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise ServiceImageError(f"{ref}: unreadable image config ({error})") from error


def parse_pairs(raw: str) -> dict[str, str]:
    pairs: dict[str, str] = {}
    for item in re.split(r"[\s,]+", raw.strip()):
        if not item:
            continue
        service, sep, ref = item.partition("=")
        if not sep or not ref:
            raise ServiceImageError(f"service_images entry {item!r} is not service=image@sha256:<digest>")
        if service not in SERVICES:
            raise ServiceImageError(f"service_images names {service!r}; deploy-backend-stack ships {list(SERVICES)}")
        if service in pairs:
            raise ServiceImageError(f"service_images names {service} twice")
        pairs[service] = ref
    return pairs


def resolve(
    raw: str,
    *,
    project: str,
    short_sha: str,
    admitted_sha: str,
    deploy_targets: str,
    deploy_gateway: bool,
    base_service: str = "backend",
    registry: dict[str, Any] | None = None,
    inspect: Inspector = inspect_image_config,
) -> dict[str, str]:
    registry = registry or json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    pairs = parse_pairs(raw)
    if "backend-listen" in pairs and deploy_targets != "all":
        raise ServiceImageError("backend-listen deploys only with deploy_targets=all")
    if "llm-gateway" in pairs and not deploy_gateway:
        raise ServiceImageError("llm-gateway deploys with the stack only with deploy_gateway=true")
    for service, ref in pairs.items():
        spec = registry["services"][service]
        repository = f"gcr.io/{project}/{spec['image']}"
        if not re.fullmatch(re.escape(repository) + r"@sha256:[0-9a-f]{64}", ref):
            raise ServiceImageError(f"{service}: {ref!r} is not {repository}@sha256:<64 hex>")
        config = inspect(ref)
        revision = (config.get("Labels") or {}).get("org.opencontainers.image.revision")
        if revision != admitted_sha:
            raise ServiceImageError(
                f"{service}: {ref} is labelled revision {revision!r}, not the admitted {admitted_sha}"
            )
        if f"OMI_ROLE={spec['role']}" not in (config.get("Env") or []):
            raise ServiceImageError(f"{service}: {ref} does not carry OMI_ROLE={spec['role']}")

    fat = f"gcr.io/{project}/{base_service}"
    outputs: dict[str, str] = {}
    for service in CLOUD_RUN_SERVICES:
        outputs[service.replace("-", "_")] = pairs.get(service, f"{fat}:{short_sha}")
    listen = pairs.get("backend-listen")
    outputs["backend_listen"] = listen or f"{fat}:{short_sha}"
    # The chart renders repository@digest when image.digest is set, else repository:tag;
    # the deploy keeps passing image.tag=<short sha> either way.
    outputs["backend_listen_repository"] = listen.split("@")[0] if listen else fat
    outputs["backend_listen_digest_args"] = f"--set-string image.digest={listen.split('@')[1]}" if listen else ""
    gateway = pairs.get("llm-gateway")
    outputs["llm_gateway"] = gateway or f"gcr.io/{project}/llm-gateway:{short_sha}"
    outputs["llm_gateway_repository"] = gateway.split("@")[0] if gateway else ""
    outputs["llm_gateway_digest"] = gateway.split("@")[1] if gateway else ""
    # The release vector covers the Cloud Run four and listen; the gateway step checks
    # its own Deployment image against the digest after rollout.
    outputs["release_vector_args"] = " ".join(
        f"--service-image {s}={r}" for s, r in sorted(pairs.items()) if s != "llm-gateway"
    )
    outputs["opted_in"] = " ".join(sorted(pairs))
    return outputs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--service-images", default="")
    parser.add_argument("--project", required=True)
    parser.add_argument("--short-sha", required=True)
    parser.add_argument("--admitted-sha", required=True)
    parser.add_argument("--deploy-targets", required=True)
    parser.add_argument("--deploy-gateway", required=True, choices=("true", "false"))
    parser.add_argument("--base-service", default="backend")
    parser.add_argument("--github-output", type=Path)
    args = parser.parse_args(argv)
    try:
        outputs = resolve(
            args.service_images,
            project=args.project,
            short_sha=args.short_sha,
            admitted_sha=args.admitted_sha,
            deploy_targets=args.deploy_targets,
            deploy_gateway=args.deploy_gateway == "true",
            base_service=args.base_service,
        )
    except ServiceImageError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    lines = "".join(f"{key}={value}\n" for key, value in outputs.items())
    if args.github_output:
        with args.github_output.open("a", encoding="utf-8") as handle:
            handle.write(lines)
    print(lines, end="")
    print(f"Role-image opt-in: {outputs['opted_in'] or 'none (every service ships its current image)'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
