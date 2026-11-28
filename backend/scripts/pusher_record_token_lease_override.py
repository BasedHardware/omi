#!/usr/bin/env python3
"""Bind a Pusher-only record token lease vector for one gcp_backend_pusher.yml dispatch.

SCA-4463. ``prod-omi-pusher`` and ``prod-omi-backend-listen`` both read the four
``RECORD_TOKEN_LEASE_*`` keys from the shared ``<env>-omi-backend-config``
ConfigMap. Release needs Pusher alone in lease ``shadow`` while backend-listen
stays ``off``. This command validates an explicit dispatch vector, writes it as
a Helm values file for the chart's ``recordTokenLeaseOverride`` block, and
proves the checked-out chart renders it: the four entries become literal
values on the Pusher container (container ``env`` wins over ``envFrom``) and
the shared ``envFrom`` ConfigMap stays attached. A runtime source whose chart
predates the block would silently ignore the values, so a render that does not
carry the vector fails here, before any cluster mutation.

No input (mode ``none`` and the other three empty) binds nothing and the
deploy keeps today's ConfigMap references. Rules match the shared binding in
``.github/actions/deploy-backend-stack/action.yml``, except that every number
must be a plain decimal integer: mode in {off, shadow, serve}, serve percent
0-100, lease seconds 1800-7200, epoch >= 0 and > 0 unless mode is off.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
CHART = ROOT / "backend/charts/pusher"
MODES = ("off", "shadow", "serve")
NO_OVERRIDE = "none"
INPUT_ENV = {
    "mode": "PUSHER_LEASE_OVERRIDE_MODE",
    "servePercent": "PUSHER_LEASE_OVERRIDE_SERVE_PERCENT",
    "seconds": "PUSHER_LEASE_OVERRIDE_SECONDS",
    "deployedAt": "PUSHER_LEASE_OVERRIDE_DEPLOYED_AT",
}
ENV_NAMES = {
    "mode": "RECORD_TOKEN_LEASE_MODE",
    "servePercent": "RECORD_TOKEN_LEASE_MODE_SERVE_PERCENT",
    "seconds": "RECORD_TOKEN_LEASE_SECONDS",
    "deployedAt": "RECORD_TOKEN_LEASE_DEPLOYED_AT",
}
DECIMAL = re.compile(r"(0|[1-9][0-9]*)")
STATE_ENV = "PUSHER_RECORD_TOKEN_LEASE_OVERRIDE"
VALUES_ENV = "PUSHER_RECORD_TOKEN_LEASE_OVERRIDE_VALUES"


class OverrideError(ValueError):
    pass


def _integer(raw: str, label: str, low: int, high: int) -> str:
    if not DECIMAL.fullmatch(raw) or not low <= int(raw) <= high:
        raise OverrideError(f"{label} must be a decimal integer from {low} to {high}")
    return raw


def parse_vector(mode: str, serve_percent: str, seconds: str, deployed_at: str) -> dict[str, str] | None:
    """Return the validated vector, or None when the dispatch supplies no override."""
    mode = mode or NO_OVERRIDE
    numbers = (serve_percent, seconds, deployed_at)
    if mode == NO_OVERRIDE:
        if any(numbers):
            raise OverrideError("lease override numbers require an explicit override mode")
        return None
    if mode not in MODES:
        raise OverrideError(f"lease override mode must be one of {', '.join((NO_OVERRIDE, *MODES))}")
    if not all(numbers):
        raise OverrideError("a lease override needs serve percent, lease seconds and deployed-at epoch together")
    vector = {
        "mode": mode,
        "servePercent": _integer(serve_percent, "lease override serve percent", 0, 100),
        "seconds": _integer(seconds, "lease override seconds", 1800, 7200),
        "deployedAt": _integer(deployed_at, "lease override deployed-at epoch", 0, 10**12 - 1),
    }
    if mode != "off" and vector["deployedAt"] == "0":
        raise OverrideError("shadow or serve lease override requires a pinned release epoch")
    return vector


def values_document(vector: dict[str, str]) -> str:
    # Quoted strings: the chart rejects numbers so YAML cannot reformat an epoch.
    lines = ["recordTokenLeaseOverride:"]
    lines.extend(f'  {key}: "{vector[key]}"' for key in INPUT_ENV)
    return "\n".join(lines) + "\n"


def render(environment: str, values_file: Path | None, *, chart: Path = CHART) -> list[dict[str, Any]]:
    digest = "sha256:" + "0" * 64
    command = [
        "helm",
        "template",
        f"{environment}-omi-pusher",
        str(chart),
        "-f",
        str(chart / f"{environment}_omi_pusher_values.yaml"),
        "--set-string",
        "image.repository=gcr.io/render-check/pusher",
        "--set-string",
        f"image.digest={digest}",
        "--set-string",
        "image.tag=",
        "--set-string",
        "image.pullPolicy=IfNotPresent",
    ]
    if values_file is not None:
        command.extend(["-f", str(values_file)])
    result = subprocess.run(command, check=False, capture_output=True, text=True)
    if result.returncode:
        raise OverrideError(result.stderr.strip() or "Pusher Helm render failed")
    return [item for item in yaml.safe_load_all(result.stdout) if isinstance(item, dict)]


def pusher_container(documents: list[dict[str, Any]]) -> dict[str, Any]:
    deployments = [item for item in documents if item.get("kind") == "Deployment"]
    if len(deployments) != 1:
        raise OverrideError("Pusher render must contain exactly one Deployment")
    containers = [
        item
        for item in deployments[0].get("spec", {}).get("template", {}).get("spec", {}).get("containers", [])
        if isinstance(item, dict) and item.get("name") == "pusher"
    ]
    if len(containers) != 1:
        raise OverrideError("Pusher render must contain exactly one pusher container")
    return containers[0]


def check_rendered(container: dict[str, Any], vector: dict[str, str], *, config_map: str) -> list[str]:
    errors = []
    env = [item for item in container.get("env") or [] if isinstance(item, dict)]
    for key, name in ENV_NAMES.items():
        entries = [item for item in env if item.get("name") == name]
        if entries != [{"name": name, "value": vector[key]}]:
            errors.append(f"{name} must render once as the literal override value {vector[key]!r}")
    if {"configMapRef": {"name": config_map}} not in (container.get("envFrom") or []):
        errors.append(f"the Pusher container must keep envFrom {config_map}")
    return errors


def bind(environment: str, service: str, output: Path, environ: dict[str, str], github_env: Path | None) -> str:
    vector = parse_vector(*(environ.get(INPUT_ENV[key], "").strip() for key in INPUT_ENV))
    exports = {STATE_ENV: "absent"}
    if vector is None:
        message = "No Pusher record token lease override: the four keys keep their shared ConfigMap references."
    else:
        if service != "pusher":
            raise OverrideError("a record token lease override applies only to the pusher service")
        output.write_text(values_document(vector), encoding="utf-8")
        errors = check_rendered(
            pusher_container(render(environment, output)), vector, config_map=f"{environment}-omi-backend-config"
        )
        if errors:
            raise OverrideError("checked-out Pusher chart does not honor the override: " + "; ".join(errors))
        exports = {STATE_ENV: "active", VALUES_ENV: str(output)}
        message = (
            "Pusher-only record token lease override "
            + " ".join(f"{ENV_NAMES[key]}={vector[key]}" for key in INPUT_ENV)
            + f"; the shared {environment}-omi-backend-config ConfigMap is not written."
        )
    if github_env is not None:
        with github_env.open("a", encoding="utf-8") as handle:
            handle.writelines(f"{key}={value}\n" for key, value in exports.items())
    return message


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("bind",))
    parser.add_argument("--environment", choices=("dev", "prod"), required=True)
    parser.add_argument("--service", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    github_env = os.environ.get("GITHUB_ENV")
    try:
        message = bind(
            args.environment, args.service, args.output, dict(os.environ), Path(github_env) if github_env else None
        )
    except OverrideError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    print(message)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as handle:
            handle.write(f"- {message}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
