#!/usr/bin/env python3
"""Keep a Pusher-only record token lease override away from serving readers.

SCA-4463. ``gcp_backend_pusher.yml`` can pin Pusher alone to a literal lease
vector (mode ``off`` or ``shadow`` at serve percent 0) while the shared
``<env>-omi-backend-config`` ConfigMap keeps the vector backend-listen, Sync and
the seal readers use. That is safe only while no reader serves: a serving reader
treats a token whose producer stopped renewing as dead after the epoch plus the
lease, and a partial finish can then clear a token Pusher still holds. Pusher in
override ``shadow`` also skips the serve-side recovery the readers expect.

Operating rule: the override is ``none`` before any reader enters serve. Both
directions are refused here, in one place every writer calls:

``override``
    Before a Pusher override is applied. Any override other than ``none`` needs
    the live shared ConfigMap at ``off`` or ``shadow`` with serve percent 0, the
    live ``record-seal-worker`` Deployment and ``record-seal-repair`` CronJob not
    serving (absent objects are not readers), and, when asked, the live Cloud
    Run Sync service not serving.

``shared-serve``
    Before a writer sets ``serve`` or a non-zero serve percent on any reader
    (the shared ConfigMap, Listen, Sync or the seal readers). It reads the live
    Pusher Deployment and its pods and refuses while any ``pusher`` container
    carries a literal ``RECORD_TOKEN_LEASE_*`` entry, which only an override
    renders. A vector that does not serve needs no cluster read at all.

Only lease mode and serve percent values are read; nothing is printed beyond
them and object names.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Iterable

MODE = "RECORD_TOKEN_LEASE_MODE"
PERCENT = "RECORD_TOKEN_LEASE_MODE_SERVE_PERCENT"
LEASE_ENV = (MODE, PERCENT, "RECORD_TOKEN_LEASE_SECONDS", "RECORD_TOKEN_LEASE_DEPLOYED_AT")
NO_OVERRIDE = "none"
NON_SERVING_MODES = ("off", "shadow")
SEAL_READERS = (("deployment", "record-seal-worker"), ("cronjob", "record-seal-repair"))
SYNC_SERVICE = "backend-sync"
CLEAR_OVERRIDE = (
    "dispatch gcp_backend_pusher.yml with pusher_record_token_lease_override_mode=none (keeping the shared "
    "vector off or shadow at serve percent 0) and let it finish first"
)


class GuardError(RuntimeError):
    pass


def _nonzero_percent(raw: Any) -> bool:
    if raw is None or raw == "":
        return False
    try:
        return float(str(raw)) != 0
    except ValueError:
        return True  # Unreadable: fail closed.


def enters_serve(mode: Any, percent: Any) -> bool:
    return mode == "serve" or _nonzero_percent(percent)


def workload_containers(obj: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Containers of a Deployment, CronJob, Pod or Cloud Run Service object."""
    if not isinstance(obj, dict):
        return []
    spec = obj.get("spec") if isinstance(obj.get("spec"), dict) else {}
    kind = obj.get("kind")
    if kind == "CronJob":
        spec = (spec.get("jobTemplate") or {}).get("spec") or {}
    pod = spec if kind == "Pod" else (spec.get("template") or {}).get("spec") or {}
    return [item for item in pod.get("containers") or [] if isinstance(item, dict)]


def literal_lease_env(container: dict[str, Any]) -> dict[str, str]:
    return {
        str(entry["name"]): str(entry.get("value", ""))
        for entry in container.get("env") or []
        if isinstance(entry, dict) and entry.get("name") in LEASE_ENV and "value" in entry
    }


def reader_vectors(label: str, obj: dict[str, Any] | None) -> list[tuple[str, str | None, str | None]]:
    """(label, mode, percent) per container of a reader that sets the lease literally."""
    vectors = []
    for container in workload_containers(obj):
        env = literal_lease_env(container)
        if env:
            vectors.append((f"{label}/{container.get('name')}", env.get(MODE), env.get(PERCENT)))
    return vectors


def rendered_reader_vectors(documents: Iterable[dict[str, Any]]) -> list[tuple[str, str | None, str | None]]:
    """Proposed seal reader vectors from a rendered batch-pipeline-worker chart."""
    names = {name for _, name in SEAL_READERS}
    vectors = []
    for document in documents:
        metadata = document.get("metadata") if isinstance(document.get("metadata"), dict) else {}
        if metadata.get("name") in names:
            vectors.extend(reader_vectors(f"proposed {metadata['name']}", document))
    return vectors


def pusher_override_sources(deployment: dict[str, Any] | None, pods: Iterable[dict[str, Any]]) -> list[str]:
    """Live Pusher objects whose pusher container carries literal lease env (an override)."""
    found = []
    for obj in [deployment, *pods]:
        if not isinstance(obj, dict):
            continue
        name = (obj.get("metadata") or {}).get("name")
        for container in workload_containers(obj):
            if container.get("name") == "pusher" and literal_lease_env(container):
                found.append(f"{str(obj.get('kind', 'object')).lower()}/{name}")
    return found


def check_override(
    override_mode: str,
    config_map: dict[str, Any] | None,
    readers: Iterable[tuple[str, str | None, str | None]],
    *,
    config_map_name: str,
) -> str:
    """Part A: refuse a Pusher override unless every live reader is non-serving."""
    if override_mode == NO_OVERRIDE:
        return "No Pusher lease override: nothing to guard."
    if override_mode not in NON_SERVING_MODES:
        raise GuardError(f"Pusher lease override mode must be off or shadow, not {override_mode!r}")
    if not isinstance(config_map, dict):
        raise GuardError(f"live {config_map_name} is missing; a Pusher lease override needs the shared vector")
    data = config_map.get("data") if isinstance(config_map.get("data"), dict) else {}
    mode, percent = data.get(MODE), data.get(PERCENT)
    if mode not in NON_SERVING_MODES or percent is None or enters_serve(mode, percent):
        raise GuardError(
            f"live {config_map_name} reads {MODE}={mode!r} {PERCENT}={percent!r}. A Pusher-only lease override "
            "is admitted only while the shared vector is off or shadow at serve percent 0; once readers serve, "
            "Pusher must read the shared vector (override none)."
        )
    serving = [label for label, reader_mode, reader_percent in readers if enters_serve(reader_mode, reader_percent)]
    if serving:
        raise GuardError(
            f"{', '.join(serving)} serves record token leases; a Pusher-only lease override is refused while any "
            "reader serves (override none before any reader enters serve)."
        )
    return (
        f"Pusher lease override {override_mode} admitted: {config_map_name} is {mode} at serve percent {percent} "
        "and no live reader serves."
    )


def check_shared_serve(
    proposed: Iterable[tuple[str, str | None, str | None]], override_sources: Iterable[str] | None
) -> str:
    """Part B: refuse a serving reader vector while a Pusher override is live.

    ``override_sources`` is consulted only when a proposed vector serves; the
    caller may pass None when it did not read the cluster.
    """
    serving = [label for label, mode, percent in proposed if enters_serve(mode, percent)]
    if not serving:
        return "No proposed reader enters record token lease serve: nothing to guard."
    if override_sources is None:
        raise GuardError("a serving vector needs the live Pusher Deployment read")
    sources = list(override_sources)
    if sources:
        raise GuardError(
            f"{', '.join(serving)} would enter record token lease serve while a Pusher-only lease override is "
            f"live on {', '.join(sources)}. The override must be none before any reader enters serve: "
            f"{CLEAR_OVERRIDE}, then retry this deploy."
        )
    return f"{', '.join(serving)} may enter serve: the live Pusher reads the shared lease vector (no override)."


def _run_json(command: list[str], *, optional: bool = False) -> dict[str, Any] | None:
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=False, timeout=120)
    except subprocess.TimeoutExpired as exc:
        raise GuardError(f"{command[0]} timed out reading live lease state") from exc
    if result.returncode:
        detail = (result.stderr or result.stdout).strip().splitlines()
        raise GuardError(f"{' '.join(command[:5])} failed: {detail[-1] if detail else 'no output'}")
    if not result.stdout.strip():
        if optional:
            return None
        raise GuardError(f"{' '.join(command[:5])} returned nothing")
    payload = json.loads(result.stdout)
    if not isinstance(payload, dict):
        raise GuardError(f"{' '.join(command[:5])} did not return an object")
    return payload


def _kubectl(namespace: str, *args: str, optional: bool = False) -> dict[str, Any] | None:
    command = ["kubectl", "--request-timeout=30s", "-n", namespace, "get", *args, "-o", "json"]
    if optional:
        command.append("--ignore-not-found")
    return _run_json(command, optional=optional)


def live_pusher_override_sources(namespace: str, deployment_name: str) -> list[str]:
    deployment = _kubectl(namespace, "deployment", deployment_name, optional=True)
    if deployment is None:
        return []  # No Pusher Deployment, so no override can be live.
    labels = ((deployment.get("spec") or {}).get("selector") or {}).get("matchLabels") or {}
    if not labels:
        raise GuardError(f"deployment/{deployment_name} has no matchLabels selector to find its pods")
    selector = ",".join(f"{key}={value}" for key, value in sorted(labels.items()))
    # Pods too: an unfinished rollout can still run override pods under a cleared template.
    pods = (_kubectl(namespace, "pods", "-l", selector) or {}).get("items") or []
    return pusher_override_sources(deployment, pods)


def _load_rendered(path: Path) -> list[dict[str, Any]]:
    import yaml  # Only the rendered-chart path needs PyYAML.

    return [item for item in yaml.safe_load_all(path.read_text(encoding="utf-8")) if isinstance(item, dict)]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    override = commands.add_parser("override", help="before a Pusher lease override is applied")
    override.add_argument("--environment", choices=("dev", "prod"), required=True)
    override.add_argument("--override-mode", required=True)
    override.add_argument("--sync-project", help="also read the live Cloud Run backend-sync vector")
    override.add_argument("--sync-region")
    shared = commands.add_parser("shared-serve", help="before a reader's lease vector is written")
    shared.add_argument("--environment", choices=("dev", "prod"), required=True)
    shared.add_argument(
        "--vector", nargs=3, action="append", default=[], metavar=("LABEL", "MODE", "PERCENT"), help="proposed vector"
    )
    shared.add_argument("--rendered", type=Path, help="rendered batch-pipeline-worker chart (seal readers)")
    args = parser.parse_args(argv)
    namespace = f"{args.environment}-omi-backend"
    try:
        if args.command == "override":
            config_map_name = f"{args.environment}-omi-backend-config"
            readers: list[tuple[str, str | None, str | None]] = []
            config_map = None
            if args.override_mode != NO_OVERRIDE:
                config_map = _kubectl(namespace, "configmap", config_map_name, optional=True)
                for kind, name in SEAL_READERS:
                    readers.extend(reader_vectors(f"{kind}/{name}", _kubectl(namespace, kind, name, optional=True)))
                if args.sync_project:
                    if not args.sync_region:
                        raise GuardError("--sync-project needs --sync-region")
                    service = _run_json(
                        [
                            "gcloud",
                            "run",
                            "services",
                            "describe",
                            SYNC_SERVICE,
                            f"--project={args.sync_project}",
                            f"--region={args.sync_region}",
                            "--format=json",
                        ]
                    )
                    readers.extend(reader_vectors(f"cloud-run/{SYNC_SERVICE}", service))
            message = check_override(args.override_mode, config_map, readers, config_map_name=config_map_name)
        else:
            proposed = [tuple(item) for item in args.vector]
            if args.rendered is not None:
                proposed.extend(rendered_reader_vectors(_load_rendered(args.rendered)))
            sources = None
            if any(enters_serve(mode, percent) for _, mode, percent in proposed):
                sources = live_pusher_override_sources(namespace, f"{args.environment}-omi-pusher")
            message = check_shared_serve(proposed, sources)
    except GuardError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    print(f"OK: {message}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
