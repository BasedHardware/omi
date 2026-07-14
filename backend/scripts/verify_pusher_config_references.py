#!/usr/bin/env python3
"""Fail a pusher deploy before rollout when rendered references are unavailable.

This renders committed pusher chart inputs, extracts ConfigMap/Secret object and
key identifiers, and uses kubectl metadata/key-name output only. It never prints,
stores, or otherwise exposes ConfigMap or Secret values.
"""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
ENVIRONMENTS = {"dev", "prod"}


def references(value: Any) -> set[tuple[str, str, str | None]]:
    """Return referenced object names plus explicit key names when present."""
    found: set[tuple[str, str, str | None]] = set()

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


def pusher_references(environment: str) -> set[tuple[str, str, str | None]]:
    expected_configmap = f"{environment}-omi-backend-config"
    expected_secret = f"{environment}-omi-backend-secrets"
    deployments = [doc for doc in render(environment) if doc.get("kind") == "Deployment"]
    if len(deployments) != 1:
        raise RuntimeError("pusher render did not contain exactly one Deployment")
    refs = references(deployments[0].get("spec", {}).get("template", {}).get("spec", {}))
    object_refs = {(kind, name) for kind, name, _key in refs}
    missing = {("configmap", expected_configmap), ("secret", expected_secret)} - object_refs
    if missing:
        names = ", ".join(f"{kind}/{name}" for kind, name in sorted(missing))
        raise RuntimeError(f"rendered pusher is missing required references: {names}")
    return refs


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


def verify(namespace: str, refs: set[tuple[str, str, str | None]]) -> list[str]:
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
    refs = pusher_references(args.environment)
    failures = [] if args.render_only else verify(args.namespace, refs)
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}")
        return 1
    print(
        "Pusher ConfigMap/Secret reference preflight passed: "
        + ", ".join(
            f"{kind}/{name}" + (f"#{key}" if key else "")
            for kind, name, key in sorted(refs, key=lambda ref: (ref[0], ref[1], ref[2] or ""))
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
