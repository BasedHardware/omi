#!/usr/bin/env python3
"""Fail a pusher deploy before rollout when rendered references are unavailable.

This renders committed pusher chart inputs, extracts ConfigMap/Secret names only,
and uses `kubectl get ... -o name`; it never reads Secret data or key values.
"""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
ENVIRONMENTS = {"dev", "prod"}


def references(value: Any) -> set[tuple[str, str]]:
    found: set[tuple[str, str]] = set()

    def walk(item: Any) -> None:
        if isinstance(item, dict):
            for key, child in item.items():
                if key in ("configMapRef", "configMapKeyRef") and isinstance(child, dict) and child.get("name"):
                    found.add(("configmap", str(child["name"])))
                elif key in ("secretRef", "secretKeyRef") and isinstance(child, dict) and child.get("name"):
                    found.add(("secret", str(child["name"])))
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


def pusher_references(environment: str) -> set[tuple[str, str]]:
    expected_configmap = f"{environment}-omi-backend-config"
    expected_secret = f"{environment}-omi-backend-secrets"
    deployments = [doc for doc in render(environment) if doc.get("kind") == "Deployment"]
    if len(deployments) != 1:
        raise RuntimeError("pusher render did not contain exactly one Deployment")
    refs = references(deployments[0].get("spec", {}).get("template", {}).get("spec", {}))
    missing = {("configmap", expected_configmap), ("secret", expected_secret)} - refs
    if missing:
        names = ", ".join(f"{kind}/{name}" for kind, name in sorted(missing))
        raise RuntimeError(f"rendered pusher is missing required references: {names}")
    return refs


def verify(namespace: str, refs: set[tuple[str, str]]) -> list[str]:
    failures: list[str] = []
    for kind, name in sorted(refs):
        result = subprocess.run(
            ["kubectl", "-n", namespace, "get", kind, name, "-o", "name"], check=False, capture_output=True, text=True
        )
        if result.returncode:
            detail = (result.stderr or result.stdout).strip().splitlines()
            failures.append(f"required {kind}/{name} unavailable: {detail[-1] if detail else 'kubectl failed'}")
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
        + ", ".join(f"{kind}/{name}" for kind, name in sorted(refs))
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
