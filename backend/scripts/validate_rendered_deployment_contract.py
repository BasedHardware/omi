#!/usr/bin/env python3
"""Validate the rendered identity and runtime shape of first-party GKE services.

This is intentionally an offline Helm contract.  It renders the committed dev
and prod values with the same immutable image-tag override that deploy paths
use, then validates the resulting Deployment objects.  It never contacts a
cluster or GCP.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable

import yaml

ROOT = Path(__file__).resolve().parents[2]
# A leading-zero numeric tag catches Helm's scalar coercion. Deploy paths must
# use --set-string so the rendered image preserves this exact immutable tag.
CONTRACT_IMAGE_TAG = "0123456"

IMAGE_TAG_DEPLOYMENT_PATHS = (
    ".github/workflows/gcp_backend.yml",
    ".github/workflows/gcp_backend_auto_dev.yml",
    ".github/workflows/gcp_backend_listen_helm.yml",
    ".github/workflows/gcp_backend_agent_proxy.yml",
    ".github/workflows/gcp_backend_agent_proxy_auto_deploy.yml",
    ".github/workflows/gcp_backend_pusher.yml",
    ".github/workflows/gcp_backend_pusher_auto_deploy.yml",
    ".github/workflows/gcp_diarizer.yml",
    ".github/workflows/gcp_models.yml",
    ".github/workflows/gcp_nllb_translation.yml",
    ".github/workflows/gcp_parakeet.yml",
    "backend/scripts/deploy-llm-gateway.sh",
)


@dataclass(frozen=True)
class DeploymentContract:
    """Stable deploy-shape expectations for one owned GKE service chart."""

    service: str
    image_name: str
    required_env: tuple[str, ...] = ()
    expected_env: tuple[tuple[str, str], ...] = ()
    required_secret_name: bool = False
    expected_volume_secret: tuple[tuple[str, str], ...] = ()


# Adding a first-party service means adding one concise entry here.  The
# validator deliberately checks rendered Kubernetes objects rather than chart
# implementation details, so chart refactors do not need test rewrites.
CONTRACTS = (
    DeploymentContract(
        service="backend-listen",
        image_name="backend",
        required_env=("OMI_ENV_STAGE", "GOOGLE_CLOUD_PROJECT"),
        expected_env=(("OMI_ENV_STAGE", "{environment}"), ("GOOGLE_CLOUD_PROJECT", "{project}")),
        required_secret_name=True,
    ),
    DeploymentContract(service="pusher", image_name="pusher", required_secret_name=True),
    DeploymentContract(
        service="agent-proxy",
        image_name="agent-proxy",
        expected_volume_secret=(
            ("dev", "dev-agent-proxy-gcp-credentials"),
            ("prod", "agent-proxy-gcp-credentials"),
        ),
    ),
    DeploymentContract(service="llm-gateway", image_name="llm-gateway", required_secret_name=True),
    DeploymentContract(service="diarizer", image_name="diarizer", required_secret_name=True),
    DeploymentContract(service="parakeet", image_name="parakeet", required_secret_name=True),
    DeploymentContract(service="nllb-translation", image_name="nllb-translation"),
    DeploymentContract(service="vad", image_name="models", required_secret_name=True),
)

ENVIRONMENTS = {
    "dev": {"project": "based-hardware-dev"},
    "prod": {"project": "based-hardware"},
}


def release_name(contract: DeploymentContract, environment: str) -> str:
    return f"{environment}-omi-{contract.service}"


def chart_dir(contract: DeploymentContract) -> Path:
    return ROOT / "backend" / "charts" / contract.service


def values_file(contract: DeploymentContract, environment: str) -> Path:
    return chart_dir(contract) / f"{environment}_omi_{contract.service.replace('-', '_')}_values.yaml"


def expected_image(contract: DeploymentContract, environment: str) -> str:
    project = ENVIRONMENTS[environment]["project"]
    return f"gcr.io/{project}/{contract.image_name}:{CONTRACT_IMAGE_TAG}"


def render_chart(contract: DeploymentContract, environment: str, helm_binary: str) -> list[dict[str, Any]]:
    """Render a chart exactly as a deploy path supplies its immutable tag."""
    result = subprocess.run(
        [
            helm_binary,
            "template",
            release_name(contract, environment),
            str(chart_dir(contract)),
            "-f",
            str(values_file(contract, environment)),
            "--set-string",
            f"image.tag={CONTRACT_IMAGE_TAG}",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode:
        detail = result.stderr.strip() or result.stdout.strip() or "Helm did not report an error"
        raise ValueError(f"{environment}/{contract.service}: helm template failed: {detail}")
    return [document for document in yaml.safe_load_all(result.stdout) if isinstance(document, dict)]


def deployment_for(documents: Iterable[dict[str, Any]], expected_name: str) -> dict[str, Any] | None:
    for document in documents:
        if document.get("apiVersion") == "apps/v1" and document.get("kind") == "Deployment":
            metadata = document.get("metadata")
            if isinstance(metadata, dict) and metadata.get("name") == expected_name:
                return document
    return None


def _mapping(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: object) -> list[dict[str, Any]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _container(deployment: dict[str, Any], service: str) -> dict[str, Any] | None:
    spec = _mapping(deployment.get("spec"))
    template = _mapping(spec.get("template"))
    pod_spec = _mapping(template.get("spec"))
    for container in _list(pod_spec.get("containers")):
        if container.get("name") == service:
            return container
    return None


def validate_rendered_deployment(
    contract: DeploymentContract,
    environment: str,
    documents: Iterable[dict[str, Any]],
) -> list[str]:
    """Return readable contract failures for one rendered Deployment."""
    prefix = f"{environment}/{contract.service}"
    deployment = deployment_for(documents, release_name(contract, environment))
    if deployment is None:
        return [f"{prefix}: missing Deployment {release_name(contract, environment)!r}"]

    pod_spec = _mapping(_mapping(_mapping(deployment.get("spec")).get("template")).get("spec"))
    errors: list[str] = []
    expected_service_account = release_name(contract, environment)
    if pod_spec.get("serviceAccountName") != expected_service_account:
        errors.append(
            f"{prefix}: serviceAccountName must be {expected_service_account!r}, "
            f"got {pod_spec.get('serviceAccountName')!r}"
        )

    container = _container(deployment, contract.service)
    if container is None:
        return [*errors, f"{prefix}: missing primary container {contract.service!r}"]

    image = container.get("image")
    expected = expected_image(contract, environment)
    if image != expected:
        errors.append(f"{prefix}: immutable image must be {expected!r}, got {image!r}")
    if not isinstance(image, str) or not image or image.endswith(":latest"):
        errors.append(f"{prefix}: image must not be empty or use the latest tag")

    ports = _list(container.get("ports"))
    if not any(port.get("name") == "http" and port.get("containerPort") == 8080 for port in ports):
        errors.append(f"{prefix}: primary container must expose named http port 8080")
    for probe_name in ("livenessProbe", "readinessProbe", "startupProbe"):
        if not _mapping(container.get(probe_name)):
            errors.append(f"{prefix}: primary container is missing {probe_name}")

    env = {entry.get("name"): entry for entry in _list(container.get("env")) if isinstance(entry.get("name"), str)}
    for name in contract.required_env:
        if name not in env:
            errors.append(f"{prefix}: required environment variable {name!r} is missing")
    replacements = {"environment": environment, **ENVIRONMENTS[environment]}
    for name, expected_value in contract.expected_env:
        actual = _mapping(env.get(name)).get("value")
        rendered_expected = expected_value.format(**replacements)
        if actual != rendered_expected:
            errors.append(f"{prefix}: {name} must be {rendered_expected!r}, got {actual!r}")

    expected_secret = f"{environment}-omi-backend-secrets"
    rendered_secret_refs: list[dict[str, Any]] = []
    for entry in env.values():
        ref = _mapping(_mapping(entry.get("valueFrom")).get("secretKeyRef"))
        if ref:
            rendered_secret_refs.append(ref)
            if not ref.get("name") or not ref.get("key"):
                errors.append(f"{prefix}: secretKeyRef for {entry.get('name')!r} needs non-empty name and key")
            elif ref.get("name") != expected_secret:
                errors.append(
                    f"{prefix}: secretKeyRef for {entry.get('name')!r} must target {expected_secret!r}, "
                    f"got {ref.get('name')!r}"
                )
    if contract.required_secret_name and not rendered_secret_refs:
        errors.append(f"{prefix}: expected at least one secretKeyRef to {expected_secret!r}")

    expected_volume_secret = dict(contract.expected_volume_secret).get(environment)
    if expected_volume_secret:
        volumes = _list(pod_spec.get("volumes"))
        secret_names = {_mapping(volume.get("secret")).get("secretName") for volume in volumes}
        if expected_volume_secret not in secret_names:
            errors.append(f"{prefix}: required volume secret {expected_volume_secret!r} is missing")
    return errors


Renderer = Callable[[DeploymentContract, str, str], list[dict[str, Any]]]


def validate_image_tag_deployment_paths() -> list[str]:
    """Require every owned GKE image-tag override to preserve string identity."""
    errors: list[str] = []
    for relative_path in IMAGE_TAG_DEPLOYMENT_PATHS:
        path = ROOT / relative_path
        rendered_command = path.read_text(encoding="utf-8").replace("\\\n", " ")
        untyped_overrides = re.findall(r'--set(?!-string)\s+"?image\.tag=', rendered_command)
        typed_overrides = re.findall(r'--set-string\s+"?image\.tag=', rendered_command)
        if untyped_overrides:
            errors.append(f"{relative_path}: image.tag must use --set-string, not --set")
        if not typed_overrides:
            errors.append(f"{relative_path}: missing --set-string image.tag override")
    return errors


def validate_all_contracts(renderer: Renderer, helm_binary: str = "helm") -> list[str]:
    errors = validate_image_tag_deployment_paths()
    for environment in ENVIRONMENTS:
        for contract in CONTRACTS:
            try:
                documents = renderer(contract, environment, helm_binary)
            except ValueError as exc:
                errors.append(str(exc))
                continue
            errors.extend(validate_rendered_deployment(contract, environment, documents))
    return errors


def main() -> int:
    helm_binary = shutil.which("helm")
    if helm_binary is None:
        print("FAIL: Helm is required to render deployment contracts; install helm and retry.", file=sys.stderr)
        return 2
    errors = validate_all_contracts(render_chart, helm_binary)
    if errors:
        print("Rendered deployment contract failures:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print(f"Rendered deployment contracts passed: {len(CONTRACTS)} services x {len(ENVIRONMENTS)} environments.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
