#!/usr/bin/env python3
"""Fail a pusher deploy before rollout when rendered config is unavailable or drifts.

This renders committed pusher chart inputs, verifies literal rollout flags against
the runtime contract, extracts ConfigMap/Secret object and key identifiers, and
uses kubectl metadata/key-name output only. It never prints, stores, or otherwise
exposes ConfigMap or Secret values.
"""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
ENVIRONMENTS = {"dev", "prod"}
RUNTIME_ENV_MANIFEST = ROOT / "backend/deploy/runtime_env.yaml"
Reference = tuple[str, str, str | None]
Binding = tuple[str, str, str]


def references(value: Any) -> set[Reference]:
    """Return referenced object names plus explicit key names when present."""
    found: set[Reference] = set()

    def walk(item: Any) -> None:
        if isinstance(item, dict):
            for key, child in item.items():
                if key in ("configMapRef", "configMapKeyRef") and isinstance(child, dict) and child.get("name"):
                    found.add(
                        (
                            "configmap",
                            str(child["name"]),
                            str(child["key"]) if key == "configMapKeyRef" and child.get("key") else None,
                        )
                    )
                elif key in ("secretRef", "secretKeyRef") and isinstance(child, dict) and child.get("name"):
                    found.add(
                        (
                            "secret",
                            str(child["name"]),
                            str(child["key"]) if key == "secretKeyRef" and child.get("key") else None,
                        )
                    )
                else:
                    walk(child)
        elif isinstance(item, list):
            for child in item:
                walk(child)

    walk(value)
    return found


def render(environment: str, image_tag: str = "contract-test") -> list[dict[str, Any]]:
    chart = ROOT / "backend/charts/pusher"
    values = chart / f"{environment}_omi_pusher_values.yaml"
    result = subprocess.run(
        [
            "helm",
            "template",
            f"{environment}-omi-pusher",
            str(chart),
            "-f",
            str(values),
            "--set-string",
            f"image.tag={image_tag}",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or "helm template failed")
    return [doc for doc in yaml.safe_load_all(result.stdout) if isinstance(doc, dict)]


def rendered_pusher_deployment(environment: str) -> dict[str, Any]:
    deployments = [doc for doc in render(environment) if doc.get("kind") == "Deployment"]
    if len(deployments) != 1:
        raise RuntimeError("pusher render did not contain exactly one Deployment")
    return deployments[0]


def pusher_references(environment: str, deployment: dict[str, Any] | None = None) -> set[Reference]:
    expected_configmap = f"{environment}-omi-backend-config"
    expected_secret = f"{environment}-omi-backend-secrets"
    deployment = deployment or rendered_pusher_deployment(environment)
    refs = references(deployment.get("spec", {}).get("template", {}).get("spec", {}))
    object_refs = {(kind, name) for kind, name, _key in refs}
    missing = {("configmap", expected_configmap), ("secret", expected_secret)} - object_refs
    if missing:
        names = ", ".join(f"{kind}/{name}" for kind, name in sorted(missing))
        raise RuntimeError(f"rendered pusher is missing required references: {names}")
    return refs


def pusher_env_entries(deployment: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Return the rendered primary pusher container env entries keyed by name."""
    pod_spec = deployment.get("spec", {}).get("template", {}).get("spec", {})
    containers = pod_spec.get("containers", []) if isinstance(pod_spec, dict) else []
    pusher_containers = [
        container for container in containers if isinstance(container, dict) and container.get("name") == "pusher"
    ]
    if len(pusher_containers) != 1:
        raise RuntimeError("pusher render did not contain exactly one primary pusher container")
    entries: dict[str, dict[str, Any]] = {}
    for entry in pusher_containers[0].get("env", []):
        if not isinstance(entry, dict) or not isinstance(entry.get("name"), str):
            continue
        name = entry["name"]
        if name in entries:
            raise RuntimeError(f"rendered pusher has duplicate env entry {name}")
        entries[name] = entry
    return entries


def _dev_pusher_runtime_env_contract() -> dict[str, Any]:
    """Load the dev pusher source contract without reading live configuration."""
    with RUNTIME_ENV_MANIFEST.open(encoding="utf-8") as handle:
        manifest = yaml.safe_load(handle)
    try:
        env = manifest["environments"]["dev"]["gke"]["pusher"]["env"]
    except (KeyError, TypeError) as exc:
        raise RuntimeError("runtime env manifest is missing environments.dev.gke.pusher.env") from exc
    if not isinstance(env, dict):
        raise RuntimeError("dev pusher runtime env contract must be a mapping")
    return env


def dev_pusher_binding_contract() -> tuple[dict[str, Binding], set[str]]:
    """Load dev direct binding names and migration guards from the runtime contract."""
    env = _dev_pusher_runtime_env_contract()

    bindings: dict[str, Binding] = {}
    clear_historical_secret: set[str] = set()
    for env_name, raw_entry in env.items():
        if not isinstance(env_name, str) or not isinstance(raw_entry, dict):
            raise RuntimeError("dev pusher runtime env contract entries must be named mappings")
        source_entries = [("configmap", raw_entry.get("config_map")), ("secret", raw_entry.get("secret"))]
        configured = [(kind, source) for kind, source in source_entries if source is not None]
        if "value" in raw_entry:
            if configured:
                raise RuntimeError(f"dev pusher literal env {env_name} must not declare a binding source")
            if not isinstance(raw_entry["value"], str):
                raise RuntimeError(f"dev pusher literal env {env_name} must be a string")
            continue
        if len(configured) != 1:
            raise RuntimeError(f"dev pusher runtime env {env_name} must declare exactly one binding source")
        kind, source = configured[0]
        if (
            not isinstance(source, dict)
            or not isinstance(source.get("name"), str)
            or not isinstance(source.get("key"), str)
        ):
            raise RuntimeError(f"dev pusher runtime env {env_name} must declare a binding name and key")
        bindings[env_name] = (kind, source["name"], source["key"])
        if raw_entry.get("clear_historical_secret"):
            if kind != "configmap":
                raise RuntimeError(f"dev pusher runtime env {env_name} can only clear a Secret when it uses ConfigMap")
            clear_historical_secret.add(env_name)
    return bindings, clear_historical_secret


def dev_pusher_literal_env_contract() -> dict[str, str]:
    """Return literal dev pusher env values that must match the rendered chart."""
    literals: dict[str, str] = {}
    for env_name, raw_entry in _dev_pusher_runtime_env_contract().items():
        if not isinstance(env_name, str) or not isinstance(raw_entry, dict) or "value" not in raw_entry:
            continue
        value = raw_entry["value"]
        if not isinstance(value, str):
            raise RuntimeError(f"dev pusher literal env {env_name} must be a string")
        literals[env_name] = value
    return literals


def direct_pusher_bindings(deployment: dict[str, Any]) -> dict[str, Binding]:
    """Return exact direct Secret/ConfigMap bindings without reading any values."""
    bindings: dict[str, Binding] = {}
    for env_name, entry in pusher_env_entries(deployment).items():
        value_from = entry.get("valueFrom")
        if not isinstance(value_from, dict):
            continue
        found: list[Binding] = []
        for field, kind in (("configMapKeyRef", "configmap"), ("secretKeyRef", "secret")):
            if field not in value_from or value_from[field] is None:
                continue
            reference = value_from[field]
            if (
                not isinstance(reference, dict)
                or not isinstance(reference.get("name"), str)
                or not isinstance(reference.get("key"), str)
            ):
                raise RuntimeError(f"rendered pusher {env_name} has an invalid {field}")
            found.append((kind, reference["name"], reference["key"]))
        if len(found) > 1:
            raise RuntimeError(f"rendered pusher {env_name} has multiple direct binding sources")
        if found:
            bindings[env_name] = found[0]
    return bindings


def direct_pusher_literals(deployment: dict[str, Any]) -> dict[str, str]:
    """Return literal pusher env values without reading ConfigMap or Secret data."""
    literals: dict[str, str] = {}
    for env_name, entry in pusher_env_entries(deployment).items():
        value = entry.get("value")
        if isinstance(value, str):
            literals[env_name] = value
    return literals


def validate_dev_pusher_binding_contract(deployment: dict[str, Any]) -> list[str]:
    """Return dev source/Helm binding drift without contacting Kubernetes."""
    expected, clear_historical_secret = dev_pusher_binding_contract()
    actual = direct_pusher_bindings(deployment)
    failures: list[str] = []
    for env_name in sorted(expected.keys() - actual.keys()):
        failures.append(f"dev pusher binding contract missing rendered binding for {env_name}")
    for env_name in sorted(actual.keys() - expected.keys()):
        failures.append(f"dev pusher binding contract has unclassified rendered binding for {env_name}")
    for env_name in sorted(expected.keys() & actual.keys()):
        if actual[env_name] != expected[env_name]:
            expected_kind, expected_name, expected_key = expected[env_name]
            actual_kind, actual_name, actual_key = actual[env_name]
            failures.append(
                f"dev pusher binding contract mismatch for {env_name}: expected "
                f"{expected_kind}/{expected_name}#{expected_key}, got {actual_kind}/{actual_name}#{actual_key}"
            )
    entries = pusher_env_entries(deployment)
    for env_name in sorted(clear_historical_secret):
        value_from = entries[env_name].get("valueFrom")
        if not isinstance(value_from, dict) or value_from.get("secretKeyRef", object()) is not None:
            failures.append(f"dev pusher binding contract must clear historical Secret source for {env_name}")
    expected_literals = dev_pusher_literal_env_contract()
    actual_literals = direct_pusher_literals(deployment)
    for env_name, expected_value in sorted(expected_literals.items()):
        if actual_literals.get(env_name) != expected_value:
            failures.append(
                f"dev pusher literal contract mismatch for {env_name}: expected {expected_value!r}, "
                f"got {actual_literals.get(env_name)!r}"
            )
    return failures


def listed_keys(namespace: str, kind: str, name: str) -> set[str]:
    """Fetch only data-map keys, never ConfigMap or Secret values."""
    result = subprocess.run(
        [
            "kubectl",
            "-n",
            namespace,
            "get",
            kind,
            name,
            "-o",
            "go-template={{range $key, $_ := .data}}{{$key}}{{\"\\n\"}}{{end}}",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode:
        detail = (result.stderr or result.stdout).strip().splitlines()
        raise RuntimeError(detail[-1] if detail else "kubectl failed")
    return {line for line in result.stdout.splitlines() if line}


def verify(namespace: str, refs: set[Reference]) -> list[str]:
    failures: list[str] = []
    available: set[tuple[str, str]] = set()
    for kind, name in sorted({(kind, name) for kind, name, _key in refs}):
        result = subprocess.run(
            ["kubectl", "-n", namespace, "get", kind, name, "-o", "name"], check=False, capture_output=True, text=True
        )
        if result.returncode:
            detail = (result.stderr or result.stdout).strip().splitlines()
            failures.append(f"required {kind}/{name} unavailable: {detail[-1] if detail else 'kubectl failed'}")
        else:
            available.add((kind, name))
    for kind, name, key in sorted(refs, key=lambda ref: (ref[0], ref[1], ref[2] or "")):
        if key is None or (kind, name) not in available:
            continue
        try:
            if key not in listed_keys(namespace, kind, name):
                failures.append(f"required {kind}/{name} key {key} unavailable")
        except RuntimeError as exc:
            failures.append(f"required {kind}/{name} key metadata unavailable: {exc}")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--environment", required=True, choices=sorted(ENVIRONMENTS))
    parser.add_argument("--namespace", required=True)
    parser.add_argument("--render-only", action="store_true")
    args = parser.parse_args()
    deployment = rendered_pusher_deployment(args.environment)
    refs = pusher_references(args.environment, deployment)
    failures = validate_dev_pusher_binding_contract(deployment) if args.environment == "dev" else []
    if not args.render_only and not failures:
        failures.extend(verify(args.namespace, refs))
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}")
        return 1
    print(
        "Pusher configuration preflight passed: "
        + ", ".join(
            f"{kind}/{name}" + (f"#{key}" if key else "")
            for kind, name, key in sorted(refs, key=lambda ref: (ref[0], ref[1], ref[2] or ""))
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
