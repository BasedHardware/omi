"""A read-only snapshot of what production runs right now.

The prod-parity profile used to compose each service's settings from the
deploy files of whatever checkout the harness ran in. Those files describe a
checkout, not the running system: production deploys several times a day and
its services run different commits. A snapshot records the live system
instead: per service the image, the commit, every literal setting and the
names of the settings bound from secrets; the load balancer's path rules; the
task queues and scheduler jobs.

``make dev-parity ARGS="snapshot --out DIR"`` takes one with the operator's own
read-only gcloud access and writes it outside the repository (the command
refuses a directory inside a checkout). Nothing is written to production.
Secret values are never read: a secret-bound setting is recorded by name only.
Account identifiers never reach the file: an allow-list of user ids is recorded
as a placeholder. Values are never printed. ``load`` gives the harness the
normalized form.

Access needed: view on Cloud Run, the load balancer's URL map, the GKE cluster
(deployments and config maps of the backend namespace), Cloud Tasks, Cloud
Scheduler, and read on the one rollout document. Whatever cannot be read is
listed in the snapshot and in the parity report; the rest is still used.
"""

from __future__ import annotations

import base64
import json
import os
import re
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

SNAPSHOT_ENV = "OMI_HARNESS_PROD_SNAPSHOT"
PROJECT = "based-hardware"
REGION = "us-central1"
CLUSTER = "prod-omi-gke"
NAMESPACE = "prod-omi-backend"
URL_MAP = "custom-domains-49a4"
API_HOST = "api.omi.me"

# Live workload -> the name the harness uses for it.
CLOUD_RUN = {
    "backend": "backend",
    "backend-sync": "backend-sync",
    "backend-sync-backfill": "backend-sync-backfill",
    "backend-integration": "backend-integration",
    "backend-projection-pump": "backend-projection-pump",
}
GKE = {
    "prod-omi-backend-listen": "backend-listen",
    "prod-omi-pusher": "pusher",
    "prod-omi-batch-pipeline-worker": "batch-worker",
    "record-seal-worker": "record-seal-worker",
}


@dataclass
class Service:
    name: str
    platform: str
    image: str = ""
    commit: str = ""
    command: list[str] = field(default_factory=list)
    args: list[str] = field(default_factory=list)
    values: dict[str, str] = field(default_factory=dict)  # literal settings
    bound: list[str] = field(default_factory=list)  # settings bound from a secret: name only
    replicas: int | None = None
    concurrency: int | None = None
    timeout_seconds: int | None = None


@dataclass
class Snapshot:
    captured_at: str
    services: dict[str, Service]
    routes: list[tuple[str, str]]  # (path pattern, service) for the API host, most specific first
    default_route: str
    queues: dict[str, dict[str, Any]]
    scheduler_jobs: list[dict[str, Any]]
    unreadable: list[str]
    directory: Path | None = None
    rollout_ramp: dict[str, Any] | None = None  # the ``rollout_cohorts/_ramp`` control document


def active_directory(env: Mapping[str, str] | None = None) -> Path | None:
    raw = (os.environ if env is None else env).get(SNAPSHOT_ENV, "").strip()
    return Path(raw) if raw else None


def load(directory: Path) -> Snapshot:
    data = json.loads((directory / "snapshot.json").read_text())
    return Snapshot(
        captured_at=data["captured_at"],
        services={name: Service(**entry) for name, entry in data["services"].items()},
        routes=[tuple(route) for route in data["routes"]],
        default_route=data["default_route"],
        queues=data.get("queues", {}),
        scheduler_jobs=data.get("scheduler_jobs", []),
        unreadable=data.get("unreadable", []),
        directory=directory,
        rollout_ramp=data.get("rollout_ramp"),
    )


def load_active(env: Mapping[str, str] | None = None) -> Snapshot | None:
    directory = active_directory(env)
    if directory is None:
        return None
    if not (directory / "snapshot.json").is_file():
        raise RuntimeError(f"{SNAPSHOT_ENV} points at {directory}, which holds no snapshot.json")
    return load(directory)


# --- capture -------------------------------------------------------------------------


# A setting that lists user ids (the Pipeline lab applies the same rule to what it
# writes). Cohort settings are percentages or hashes, not ids.
_UID_LIST = re.compile(r"(_UID_ALLOWLIST|_ALLOWLIST_UIDS|_UIDS|_UID)$")
_COHORT_SUFFIXES = ("_SERVE_PERCENT", "_SERVE_UID_SHA256S")
REDACTED_UID = "redacted-production-uid"


def scrub_uids(values: Mapping[str, str]) -> dict[str, str]:
    """Settings with every user-id list replaced: a local stack's account is never on production's lists,
    so a non-empty list keeps its meaning (some accounts, not this one) without its members."""
    return {
        name: (
            REDACTED_UID if value.strip() and _UID_LIST.search(name) and not name.endswith(_COHORT_SUFFIXES) else value
        )
        for name, value in values.items()
    }


def _configuration_args(configuration: str | None) -> list[str]:
    return ["--configuration", configuration] if configuration else []


def _gcloud(*args: str, configuration: str | None) -> Any:
    command = ["gcloud", *args, "--project", PROJECT, *_configuration_args(configuration), "--format", "json"]
    result = subprocess.run(command, capture_output=True, text=True, timeout=180)
    if result.returncode != 0:
        raise RuntimeError(f"gcloud {' '.join(args[:3])} failed (exit {result.returncode})")
    return json.loads(result.stdout or "null")


def _container_env(container: Mapping[str, Any], config_maps: Mapping[str, Mapping[str, str]]) -> tuple[dict, list]:
    values: dict[str, str] = {}
    bound: list[str] = []
    # envFrom is applied first; an explicit env entry with the same name wins.
    for source in container.get("envFrom") or []:
        reference = (source.get("configMapRef") or {}).get("name")
        if reference and reference in config_maps:
            values.update({name: str(value) for name, value in config_maps[reference].items()})
    for entry in container.get("env") or []:
        name = entry["name"]
        source = entry.get("valueFrom")
        if source is None:
            values[name] = str(entry.get("value") or "")
            continue
        reference = source.get("configMapKeyRef")
        if reference and reference.get("key") in config_maps.get(reference.get("name"), {}):
            # A config-map key is an ordinary readable setting.
            values[name] = str(config_maps[reference["name"]][reference["key"]])
            continue
        values.pop(name, None)
        if "fieldRef" not in source and "resourceFieldRef" not in source:
            bound.append(name)  # a secret: recorded by name only (pod metadata is not a setting)
    return scrub_uids(values), sorted(set(bound))


def _run_service(raw: Mapping[str, Any], name: str) -> Service:
    template = raw["spec"]["template"]
    container = template["spec"]["containers"][0]
    values, bound = _container_env(container, {})
    labels = {**(raw["metadata"].get("labels") or {}), **(template["metadata"].get("labels") or {})}
    return Service(
        name=name,
        platform="cloud_run",
        image=container["image"],
        commit=values.get("OMI_BACKEND_RELEASE_SHA") or labels.get("commit-sha", ""),
        command=list(container.get("command") or []),
        args=list(container.get("args") or []),
        values=values,
        bound=bound,
        concurrency=template["spec"].get("containerConcurrency"),
        timeout_seconds=template["spec"].get("timeoutSeconds"),
    )


def _commit_of_image(image: str, configuration: str | None) -> str:
    """The short commit an image was built from: its tag, or the tag the registry holds for its digest."""
    reference = image.rsplit("/", 1)[-1]
    if "@sha256:" not in image:
        tag = reference.rsplit(":", 1)[-1]
        return tag if re.fullmatch(r"[0-9a-f]{7,40}", tag) else ""
    repository, digest = image.split("@", 1)
    try:
        result = subprocess.run(
            ["gcloud", "container", "images", "list-tags", repository, "--project", PROJECT]
            + [*_configuration_args(configuration), "--filter", f"digest={digest}", "--format", "value(tags)"],
            capture_output=True,
            text=True,
            timeout=120,
        )
    except Exception:  # noqa: BLE001 - an unknown commit is reported, never fatal
        return ""
    for tag in re.split(r"[;,\s]+", result.stdout.strip()):
        if re.fullmatch(r"[0-9a-f]{7,40}", tag):
            return tag
    return ""


def _kubernetes(endpoint: str, ca_file: str, token: str, path: str) -> Any:
    import ssl

    context = ssl.create_default_context(cafile=ca_file)
    request = urllib.request.Request(f"https://{endpoint}{path}", headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(request, timeout=40, context=context) as response:
        return json.loads(response.read())


def _firestore_plain(value: Mapping[str, Any]) -> Any:
    for key in ("stringValue", "booleanValue", "doubleValue", "timestampValue"):
        if key in value:
            return value[key]
    if "integerValue" in value:
        return int(value["integerValue"])
    if "mapValue" in value:
        return {name: _firestore_plain(item) for name, item in (value["mapValue"].get("fields") or {}).items()}
    if "arrayValue" in value:
        return [_firestore_plain(item) for item in value["arrayValue"].get("values") or []]
    return None


def _rollout_ramp(token: str) -> dict[str, Any]:
    """The one rollout control document. It holds percentages and modes, no user data."""
    url = f"https://firestore.googleapis.com/v1/projects/{PROJECT}/databases/(default)/documents/rollout_cohorts/_ramp"
    request = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(request, timeout=30) as response:
        document = json.loads(response.read())
    return {name: _firestore_plain(value) for name, value in (document.get("fields") or {}).items()}


def _routes(url_map: Mapping[str, Any]) -> tuple[list[tuple[str, str]], str]:
    matcher_name = next(
        rule["pathMatcher"] for rule in url_map.get("hostRules", []) if API_HOST in (rule.get("hosts") or [])
    )
    matcher = next(item for item in url_map["pathMatchers"] if item["name"] == matcher_name)

    def service_of(backend: str) -> str:
        label = backend.rsplit("/", 1)[-1]
        for marker, service in (
            ("backend-sync-backfill", "backend-sync-backfill"),
            ("backend-integration", "backend-integration"),
            ("backend-sync", "backend-sync"),
            ("backend-listen", "backend-listen"),
            ("backend", "backend"),
        ):
            if marker in label:
                return service
        return label

    routes: list[tuple[str, str]] = []
    for rule in matcher.get("pathRules", []):
        for path in rule.get("paths", []):
            if path != "/*":
                routes.append((path, service_of(rule["service"])))
    # Longest pattern first is the load balancer's own precedence.
    routes.sort(key=lambda route: len(route[0]), reverse=True)
    return routes, service_of(matcher["defaultService"])


def _access_token(configuration: str | None) -> str:
    return subprocess.run(
        ["gcloud", "auth", "print-access-token", *_configuration_args(configuration)],
        capture_output=True,
        text=True,
        timeout=60,
        check=True,
    ).stdout.strip()


def capture(out: Path, *, configuration: str | None = None) -> Snapshot:
    """Read production's live configuration into ``out/snapshot.json`` (owner-only)."""
    out.mkdir(parents=True, exist_ok=True)
    out.chmod(0o700)
    unreadable: list[str] = []
    services: dict[str, Service] = {}

    for live, name in CLOUD_RUN.items():
        try:
            raw = _gcloud("run", "services", "describe", live, "--region", REGION, configuration=configuration)
            services[name] = _run_service(raw, name)
        except Exception as error:  # noqa: BLE001 - one unreadable workload must not hide the others
            unreadable.append(f"cloud_run:{live}:{type(error).__name__}")

    try:
        url_map = _gcloud("compute", "url-maps", "describe", URL_MAP, configuration=configuration)
        routes, default_route = _routes(url_map)
    except Exception as error:  # noqa: BLE001
        unreadable.append(f"url_map:{type(error).__name__}")
        routes, default_route = [], "backend"

    try:
        cluster = _gcloud("container", "clusters", "describe", CLUSTER, "--region", REGION, configuration=configuration)
        token = _access_token(configuration)
        with tempfile.NamedTemporaryFile("wb", suffix=".pem") as ca:
            ca.write(base64.b64decode(cluster["masterAuth"]["clusterCaCertificate"]))
            ca.flush()
            deployments = _kubernetes(
                cluster["endpoint"], ca.name, token, f"/apis/apps/v1/namespaces/{NAMESPACE}/deployments?limit=500"
            )
            config_maps: dict[str, dict[str, str]] = {}
            for item in deployments.get("items", []):
                if item["metadata"]["name"] not in GKE:
                    continue
                for container in item["spec"]["template"]["spec"]["containers"][:1]:
                    references = [
                        (source.get("configMapRef") or {}).get("name") for source in container.get("envFrom") or []
                    ] + [
                        ((entry.get("valueFrom") or {}).get("configMapKeyRef") or {}).get("name")
                        for entry in container.get("env") or []
                    ]
                    for reference in references:
                        if reference and reference not in config_maps:
                            try:
                                data = _kubernetes(
                                    cluster["endpoint"],
                                    ca.name,
                                    token,
                                    f"/api/v1/namespaces/{NAMESPACE}/configmaps/{reference}",
                                )
                                config_maps[reference] = data.get("data") or {}
                            except Exception as error:  # noqa: BLE001
                                unreadable.append(f"config_map:{reference}:{type(error).__name__}")
        for item in deployments.get("items", []):
            live = item["metadata"]["name"]
            if live not in GKE:
                continue
            container = item["spec"]["template"]["spec"]["containers"][0]
            values, bound = _container_env(container, config_maps)
            services[GKE[live]] = Service(
                name=GKE[live],
                platform="gke",
                image=container["image"],
                commit=values.get("OMI_BACKEND_RELEASE_SHA", "") or _commit_of_image(container["image"], configuration),
                command=list(container.get("command") or []),
                args=list(container.get("args") or []),
                values=values,
                bound=bound,
                replicas=item["spec"].get("replicas"),
            )
    except Exception as error:  # noqa: BLE001
        unreadable.append(f"gke:{type(error).__name__}")

    queues: dict[str, dict[str, Any]] = {}
    try:
        for queue in _gcloud("tasks", "queues", "list", "--location", REGION, configuration=configuration) or []:
            queues[queue["name"].rsplit("/", 1)[-1]] = {
                "rate_limits": queue.get("rateLimits") or {},
                "retry_config": queue.get("retryConfig") or {},
                "state": queue.get("state"),
            }
    except Exception as error:  # noqa: BLE001
        unreadable.append(f"task_queues:{type(error).__name__}")

    scheduler_jobs: list[dict[str, Any]] = []
    try:
        for job in _gcloud("scheduler", "jobs", "list", "--location", REGION, configuration=configuration) or []:
            target = job.get("httpTarget") or {}
            scheduler_jobs.append(
                {
                    "name": job["name"].rsplit("/", 1)[-1],
                    "schedule": job.get("schedule"),
                    "state": job.get("state"),
                    "uri": target.get("uri"),
                    "method": target.get("httpMethod", "POST"),
                    "audience": (target.get("oidcToken") or {}).get("audience"),
                    "body": base64.b64decode(target["body"]).decode() if target.get("body") else None,
                    "attempt_deadline": job.get("attemptDeadline"),
                }
            )
    except Exception as error:  # noqa: BLE001
        unreadable.append(f"scheduler:{type(error).__name__}")

    rollout_ramp: dict[str, Any] | None = None
    try:
        rollout_ramp = _rollout_ramp(_access_token(configuration))
    except Exception as error:  # noqa: BLE001
        unreadable.append(f"rollout_ramp:{type(error).__name__}")

    snapshot = Snapshot(
        captured_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        services=services,
        routes=routes,
        default_route=default_route,
        queues=queues,
        scheduler_jobs=scheduler_jobs,
        unreadable=unreadable,
        directory=out,
        rollout_ramp=rollout_ramp,
    )
    path = out / "snapshot.json"
    path.write_text(
        json.dumps(
            {
                "captured_at": snapshot.captured_at,
                "services": {name: service.__dict__ for name, service in services.items()},
                "routes": routes,
                "default_route": default_route,
                "queues": queues,
                "scheduler_jobs": scheduler_jobs,
                "unreadable": unreadable,
                "rollout_ramp": rollout_ramp,
            }
        )
    )
    path.chmod(0o600)
    return snapshot


def summary(snapshot: Snapshot) -> str:
    """Names, versions and counts only: safe to print."""
    lines = [f"captured {snapshot.captured_at}"]
    for name, service in sorted(snapshot.services.items()):
        tag = (
            service.image.rsplit(":", 1)[-1]
            if "@sha256" not in service.image
            else service.image.rsplit(":", 1)[-1][:12]
        )
        lines.append(
            f"  {name}: {service.platform} image={tag} commit={service.commit[:10] or 'unknown'} "
            f"settings={len(service.values)} secret-bound={len(service.bound)}"
        )
    lines.append(f"  routes: {len(snapshot.routes)} path rules, default {snapshot.default_route}")
    lines.append(f"  task queues: {len(snapshot.queues)}, scheduler jobs: {len(snapshot.scheduler_jobs)}")
    ramp = ((snapshot.rollout_ramp or {}).get("envs") or {}).get("prod") or {}
    if ramp:
        lines.append(f"  rollout: {ramp.get('percents')} legacy_sync={ramp.get('legacy_sync')}")
    if snapshot.unreadable:
        lines.append(f"  unreadable: {', '.join(snapshot.unreadable)}")
    return "\n".join(lines)


def drift(old: Snapshot, new: Snapshot) -> list[str]:
    """What changed in production between two snapshots: names and versions only, never values."""
    lines: list[str] = []
    for name in sorted(set(old.services) | set(new.services)):
        before, after = old.services.get(name), new.services.get(name)
        if before is None or after is None:
            lines.append(f"{name}: {'appeared' if before is None else 'disappeared'}")
            continue
        if before.image != after.image:
            lines.append(f"{name}: code {before.commit[:10] or '?'} -> {after.commit[:10] or '?'}")
        changed = sorted(
            key
            for key in set(before.values) | set(after.values)
            if before.values.get(key) != after.values.get(key) and key != "OMI_BACKEND_RELEASE_SHA"
        )
        if changed:
            lines.append(f"{name}: {len(changed)} setting(s) changed: {', '.join(changed[:12])}")
        if sorted(before.bound) != sorted(after.bound):
            lines.append(f"{name}: secret-bound settings changed")
    if old.routes != new.routes or old.default_route != new.default_route:
        lines.append("routing rules changed")
    if (old.rollout_ramp or {}).get("envs") != (new.rollout_ramp or {}).get("envs"):
        lines.append("rollout document changed")
    if old.queues != new.queues:
        lines.append("task queue settings changed")
    if old.scheduler_jobs != new.scheduler_jobs:
        lines.append("scheduler jobs changed")
    return lines


def _inside_a_checkout(path: Path) -> bool:
    resolved = path.resolve()
    return any((parent / ".git").exists() for parent in (resolved, *resolved.parents))


def capture_command(out: Path, configuration: str | None) -> int:
    """``make dev-parity ARGS="snapshot --out DIR"``."""
    if _inside_a_checkout(out):
        print(f"refused: {out} is inside a git checkout; production settings stay outside the repository")
        return 2
    snapshot = capture(out, configuration=configuration)
    print(summary(snapshot))
    print(f"written to {out}")
    print(f"use it: export {SNAPSHOT_ENV}={out}")
    return 0 if snapshot.services else 1


def drift_command(old: Path, new: Path) -> int:
    """``make dev-parity ARGS="drift OLD_DIR NEW_DIR"``: 1 when production changed between the two."""
    changes = drift(load(old), load(new))
    print("\n".join(changes) if changes else "no change")
    return 1 if changes else 0
