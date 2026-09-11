#!/usr/bin/env python3
"""Prepare, deploy, and verify the dedicated Parakeet streaming fleet."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Mapping, Sequence

import yaml

try:
    from .parakeet_stream_contract import (
        CommandRunner,
        DeploymentError,
        StreamFleetPlan,
        _capacity_value,
        _mapping,
        build_plan,
        current_node_count,
        merge_adapter_values,
        promote_qualified_image,
        reserved_l4_gpus,
        validate_capacity_evidence,
        validate_gpu_quota,
        validate_tdt_model_identity,
        validate_owned_node_pool,
    )
except ImportError:  # Direct invocation from the deployment image.
    from parakeet_stream_contract import (
        CommandRunner,
        DeploymentError,
        StreamFleetPlan,
        _capacity_value,
        _mapping,
        build_plan,
        current_node_count,
        merge_adapter_values,
        promote_qualified_image,
        reserved_l4_gpus,
        validate_capacity_evidence,
        validate_gpu_quota,
        validate_tdt_model_identity,
        validate_owned_node_pool,
    )


METRIC_ATTEMPTS, METRIC_POLL_SECONDS = 36, 5
WARM_FLEET_ATTEMPTS, WARM_FLEET_POLL_SECONDS = 540, 5


def deployment_order() -> tuple[str, ...]:
    return (
        "admit-image",
        "promote-image-to-target-registry",
        "validate-quota",
        "validate-or-create-owned-node-pool",
        "upgrade-existing-metrics-adapter",
        "upgrade-stream-release",
        "verify-warm-pods-gpu-health-endpoints",
        "export-stream-ilb-url",
        "render-runtime-env",
        "deploy-backend-listen",
    )


def _run(command: Sequence[str], capture: bool = False) -> str:
    completed = subprocess.run(list(command), check=True, text=True, capture_output=capture)
    return completed.stdout if capture else ""


def _json_command(command: Sequence[str], runner: CommandRunner) -> dict[str, Any]:
    try:
        value = json.loads(runner(command, True))
    except json.JSONDecodeError as exc:
        raise DeploymentError(f"command did not return JSON: {' '.join(command)}") from exc
    return _mapping(value, field="command JSON")


def _write_output(path: Path | None, values: Mapping[str, str]) -> None:
    if path is None:
        return
    with path.open("a", encoding="utf-8") as handle:
        for key, value in values.items():
            if "\n" in value or "\r" in value:
                raise DeploymentError(f"GitHub output {key} contains a newline")
            handle.write(f"{key}={value}\n")


def _latest_revision(raw: str) -> str:
    try:
        history = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise DeploymentError("Helm history response was not JSON") from exc
    if not isinstance(history, list) or not history or not isinstance(history[-1], dict):
        raise DeploymentError("Helm release has no rollback revision")
    revision = history[-1].get("revision")
    if not str(revision).isdigit():
        raise DeploymentError("Helm history has no numeric rollback revision")
    return str(revision)


def _pool_nodes(plan: StreamFleetPlan, runner: CommandRunner) -> int:
    document = _json_command(["kubectl", "get", "nodes", "-l", plan.node_selector, "-o", "json"], runner)
    items = document.get("items")
    if not isinstance(items, list):
        raise DeploymentError("cluster node listing did not return an items list")
    return len(items)


def _other_l4_reservation(*, cluster: str, region: str, project: str, owned_pool: str, runner: CommandRunner) -> int:
    """Reserve only future growth of existing non-owned L4 pools.

    Quota usage already includes currently allocated GPUs.  Attach the live
    node count to each listed pool so its autoscaling maximum contributes only
    the remaining growth and is not double-counted against quota usage.
    """
    command = [
        "gcloud",
        "container",
        "node-pools",
        "list",
        "--cluster",
        cluster,
        "--region",
        region,
        "--project",
        project,
        "--format=json",
    ]
    try:
        raw_pools = json.loads(runner(command, True))
    except (json.JSONDecodeError, subprocess.CalledProcessError) as exc:
        raise DeploymentError("could not read complete cluster node-pool inventory for GPU quota") from exc
    if not isinstance(raw_pools, list):
        raise DeploymentError("cluster node-pool inventory is not a list")
    nodes = _json_command(
        ["kubectl", "get", "nodes", "-l", "cloud.google.com/gke-accelerator=nvidia-l4", "-o", "json"], runner
    )
    raw_items = nodes.get("items")
    if not isinstance(raw_items, list):
        raise DeploymentError("L4 node inventory did not return an items list")
    current_by_pool: dict[str, int] = {}
    for raw_node in raw_items:
        node = _mapping(raw_node, field="L4 node")
        metadata = _mapping(node.get("metadata"), field="L4 node metadata")
        labels = _mapping(metadata.get("labels"), field="L4 node labels")
        pool_name = labels.get("cloud.google.com/gke-nodepool")
        if isinstance(pool_name, str) and pool_name:
            current_by_pool[pool_name] = current_by_pool.get(pool_name, 0) + 1
    pools: list[Mapping[str, Any]] = []
    for raw_pool in raw_pools:
        pool = _mapping(raw_pool, field="node pool inventory item")
        pool_name = pool.get("name")
        if not isinstance(pool_name, str) or not pool_name:
            raise DeploymentError("node pool inventory contains a pool without a name")
        if pool_name == owned_pool:
            continue
        enriched = dict(pool)
        enriched["currentNodeCount"] = current_by_pool.get(pool_name, 0)
        pools.append(enriched)
    return reserved_l4_gpus(pools, owned_pool=owned_pool)


def _verify_warm_fleet_once(
    plan: StreamFleetPlan, runner: CommandRunner, *, expected_image_ref: str | None = None
) -> list[str]:
    deployment = _json_command(
        ["kubectl", "-n", plan.namespace, "get", "deployment", plan.release, "-o", "json"], runner
    )
    raw_status = deployment.get("status")
    status: Mapping[str, Any] = raw_status if isinstance(raw_status, dict) else {}
    try:
        counts = [int(status.get(field, 0)) for field in ("readyReplicas", "updatedReplicas", "availableReplicas")]
    except (TypeError, ValueError) as exc:
        raise DeploymentError("Parakeet deployment status has invalid replica counts") from exc
    if any(count < plan.warm_replicas for count in counts):
        raise DeploymentError(f"Parakeet stream deployment has fewer than {plan.warm_replicas} warm replicas")

    pods = _json_command(
        ["kubectl", "-n", plan.namespace, "get", "pods", "-l", plan.service_selector, "-o", "json"], runner
    )
    items = pods.get("items")
    if not isinstance(items, list) or len(items) < plan.warm_replicas:
        raise DeploymentError("Parakeet stream deployment has fewer warm pods than its configured floor")
    names: list[str] = []
    nodes: set[str] = set()
    for raw_pod in items:
        pod = _mapping(raw_pod, field="pod")
        metadata = _mapping(pod.get("metadata"), field="pod.metadata")
        pod_name = metadata.get("name")
        if not isinstance(pod_name, str) or not pod_name:
            raise DeploymentError("Parakeet stream pod has no name")
        names.append(pod_name)
        conditions = pod.get("status", {}).get("conditions", []) if isinstance(pod.get("status"), dict) else []
        if not any(isinstance(c, dict) and c.get("type") == "Ready" and c.get("status") == "True" for c in conditions):
            raise DeploymentError(f"Parakeet stream pod {pod_name} is not Ready")
        spec = _mapping(pod.get("spec"), field="pod.spec")
        node_name = spec.get("nodeName")
        if not isinstance(node_name, str) or not node_name:
            raise DeploymentError(f"Parakeet stream pod {pod_name} is not assigned to a node")
        nodes.add(node_name)
        containers = spec.get("containers")
        if not isinstance(containers, list) or not any(
            isinstance(container, dict) and container.get("image") == (expected_image_ref or plan.image_ref)
            for container in containers
        ):
            raise DeploymentError(f"Parakeet pod {pod_name} is not running the qualified image digest")
        try:
            health = json.loads(
                runner(
                    [
                        "kubectl",
                        "-n",
                        plan.namespace,
                        "exec",
                        pod_name,
                        "--",
                        "curl",
                        "-sf",
                        "http://127.0.0.1:8080/health",
                    ],
                    True,
                )
            )
        except json.JSONDecodeError as exc:
            raise DeploymentError(f"Parakeet pod {pod_name} health response was not JSON") from exc
        components = health.get("components")
        admission = health.get("admission")
        try:
            validate_tdt_model_identity(health.get("model_identity"), field=f"Parakeet pod {pod_name} model_identity")
        except DeploymentError as exc:
            raise DeploymentError(
                f"Parakeet pod {pod_name} did not report a ready stream model with exact TDT identity"
            ) from exc
        if (
            health.get("ready") is not True
            or health.get("status") != "healthy"
            or health.get("mode") != "stream"
            or not isinstance(components, dict)
            or any(components.get(name) is not True for name in ("rnnt", "vad", "diarizer"))
            or not isinstance(admission, dict)
            or _capacity_value(admission.get("capacity")) < plan.hard_stream_capacity
        ):
            raise DeploymentError(f"Parakeet pod {pod_name} did not report a ready stream model")
    if len(nodes) < plan.warm_replicas:
        raise DeploymentError("Parakeet stream warm pods are not spread across one node per pod")

    endpoint = _json_command(
        [
            "kubectl",
            "-n",
            plan.namespace,
            "get",
            "endpointslice",
            "-l",
            f"kubernetes.io/service-name={plan.service}",
            "-o",
            "json",
        ],
        runner,
    )
    ready_endpoints = sum(
        1
        for item in endpoint.get("items", [])
        if isinstance(item, dict)
        for entry in item.get("endpoints", [])
        if isinstance(entry, dict)
        and isinstance(entry.get("conditions"), dict)
        and entry["conditions"].get("ready") is True
    )
    if ready_endpoints < plan.warm_replicas:
        raise DeploymentError("Parakeet stream service has fewer ready endpoints than its warm floor")
    return names


def _verify_warm_fleet(
    plan: StreamFleetPlan, runner: CommandRunner, *, expected_image_ref: str | None = None
) -> list[str]:
    last_error: DeploymentError | None = None
    for attempt in range(WARM_FLEET_ATTEMPTS):
        try:
            return _verify_warm_fleet_once(plan, runner, expected_image_ref=expected_image_ref)
        except DeploymentError as exc:
            last_error = exc
            if attempt + 1 < WARM_FLEET_ATTEMPTS:
                time.sleep(WARM_FLEET_POLL_SECONDS)
    raise last_error or DeploymentError("Parakeet stream fleet did not become ready")


def _verify_metrics(plan: StreamFleetPlan, pods: Sequence[str], runner: CommandRunner) -> None:
    last_error: DeploymentError | None = None
    for attempt in range(METRIC_ATTEMPTS):
        try:
            now = dt.datetime.now(dt.timezone.utc)
            for pod in pods:
                path = (
                    f"/apis/custom.metrics.k8s.io/v1beta1/namespaces/{plan.namespace}/pods/{pod}/parakeet_stream_demand"
                )
                try:
                    raw = runner(["kubectl", "get", "--raw", path], True)
                    document = json.loads(raw)
                except subprocess.CalledProcessError as exc:
                    raise DeploymentError(f"Parakeet stream demand metric is not available for pod {pod}") from exc
                except json.JSONDecodeError as exc:
                    raise DeploymentError("Parakeet stream demand custom metric response was not JSON") from exc
                items = document.get("items") if isinstance(document, dict) else None
                if not isinstance(items, list) or not items:
                    raise DeploymentError(f"Parakeet stream demand metric is missing for pod {pod}")
                entry = next(
                    (
                        item
                        for item in items
                        if isinstance(item, dict) and item.get("describedObject", {}).get("name") == pod
                    ),
                    None,
                )
                if not isinstance(entry, dict) or _capacity_value(entry.get("value")) < 0:
                    raise DeploymentError(
                        f"Parakeet stream demand metric for pod {pod} is missing or not numeric and non-negative"
                    )
                timestamp = entry.get("timestamp")
                if not isinstance(timestamp, str):
                    raise DeploymentError(f"Parakeet stream demand metric for pod {pod} has no timestamp")
                try:
                    observed = dt.datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                except ValueError as exc:
                    raise DeploymentError(
                        f"Parakeet stream demand metric for pod {pod} has an invalid timestamp"
                    ) from exc
                if (
                    observed.tzinfo is None
                    or (now - observed).total_seconds() > 300
                    or (observed - now).total_seconds() > 60
                ):
                    raise DeploymentError(f"Parakeet stream demand metric for pod {pod} is stale")
            return
        except DeploymentError as exc:
            last_error = exc
            if attempt + 1 < METRIC_ATTEMPTS:
                time.sleep(METRIC_POLL_SECONDS)
    raise last_error or DeploymentError("Parakeet stream demand custom metric was not observed")


def _service_ip(plan: StreamFleetPlan, runner: CommandRunner) -> str:
    service = _json_command(["kubectl", "-n", plan.namespace, "get", "service", plan.service, "-o", "json"], runner)
    raw_status = service.get("status")
    status: Mapping[str, Any] = raw_status if isinstance(raw_status, dict) else {}
    raw_load_balancer = status.get("loadBalancer")
    load_balancer: Mapping[str, Any] = raw_load_balancer if isinstance(raw_load_balancer, dict) else {}
    ingress = load_balancer.get("ingress")
    if not isinstance(ingress, list) or not ingress:
        raise DeploymentError("Parakeet stream internal load balancer has no ready ingress IP")
    address = ingress[0].get("ip") if isinstance(ingress[0], dict) else None
    if not isinstance(address, str) or not re.fullmatch(r"(?:\d{1,3}\.){3}\d{1,3}", address):
        raise DeploymentError("Parakeet stream load balancer ingress did not return an IPv4 address")
    return address


def deploy_stream_fleet(
    plan: StreamFleetPlan,
    *,
    cluster: str,
    region: str,
    project: str,
    adapter_values_file: Path,
    adapter_release: str,
    qualification_evidence: Mapping[str, Any] | None = None,
    source_sha: str = "",
    allow_node_pool_provision: bool = False,
    runner: CommandRunner = _run,
    github_output: Path | None = None,
) -> str:
    """Apply the stream fleet and return its internal load-balancer URL."""
    if qualification_evidence is None:
        raise DeploymentError("Parakeet stream deployment requires measured qualification evidence")
    if not source_sha:
        raise DeploymentError("Parakeet stream deployment requires the admitted source SHA")
    validate_capacity_evidence(
        qualification_evidence,
        image_ref=plan.image_ref,
        required_capacity=plan.hard_stream_capacity,
        source_sha=source_sha,
    )
    promotion = promote_qualified_image(plan.image_ref, target_project=project, runner=runner)
    target_image_ref = promotion["target_image_ref"]
    target_repository = promotion["target_repository"]
    print(
        "Parakeet image promotion: "
        f"source={promotion['source_image_ref']} target={target_image_ref} mode={promotion['mode']}"
    )

    pool_command = [
        "gcloud",
        "container",
        "node-pools",
        "describe",
        plan.node_pool,
        "--cluster",
        cluster,
        "--region",
        region,
        "--project",
        project,
        "--format=json",
    ]
    try:
        pool = _json_command(pool_command, runner)
        existing_pool = True
    except subprocess.CalledProcessError:
        if not allow_node_pool_provision:
            raise DeploymentError(f"owned node pool {plan.node_pool} is absent; provisioning is not enabled")
        existing_pool = False
        cluster_doc = _json_command(
            [
                "gcloud",
                "container",
                "clusters",
                "describe",
                cluster,
                "--region",
                region,
                "--project",
                project,
                "--format=json",
            ],
            runner,
        )
        locations = cluster_doc.get("locations")
        if not isinstance(locations, list) or not locations or not isinstance(locations[0], str):
            raise DeploymentError("cannot determine a node location for the task-owned stream pool")
        pool = {}
        additional_nodes = plan.max_nodes
        node_location = locations[0]
    else:
        validate_owned_node_pool(pool, plan)
        try:
            current = current_node_count(pool)
        except DeploymentError:
            current = _pool_nodes(plan, runner)
        additional_nodes = max(0, plan.max_nodes - current)
        node_location = ""

    other_l4_growth = _other_l4_reservation(
        cluster=cluster, region=region, project=project, owned_pool=plan.node_pool, runner=runner
    )
    quota = _json_command(
        ["gcloud", "compute", "regions", "describe", region, "--project", project, "--format=json"], runner
    )
    print(f"Parakeet GPU quota reservation: other_pool_growth={other_l4_growth} stream_growth={additional_nodes}")
    validate_gpu_quota(quota, additional_nodes, reserved_gpus=other_l4_growth)
    if not existing_pool:
        runner(
            [
                "gcloud",
                "container",
                "node-pools",
                "create",
                plan.node_pool,
                "--cluster",
                cluster,
                "--region",
                region,
                "--project",
                project,
                "--machine-type=g2-standard-8",
                "--accelerator=type=nvidia-l4,count=1,gpu-driver-version=default",
                f"--num-nodes={plan.warm_replicas}",
                f"--node-locations={node_location}",
                "--enable-autoscaling",
                f"--total-min-nodes={plan.warm_replicas}",
                f"--total-max-nodes={plan.max_nodes}",
                f"--node-labels=service=parakeet-stream,env={plan.environment},omi.dev/managed-by=parakeet-stream-release",
                "--enable-autorepair",
                "--quiet",
            ],
            False,
        )
        pool = _json_command(pool_command, runner)
        validate_owned_node_pool(pool, plan)

    adapter_namespace = f"{plan.environment}-omi-monitoring"
    adapter_status = _json_command(["helm", "-n", adapter_namespace, "status", adapter_release, "-o", "json"], runner)
    chart = adapter_status.get("chart", "")
    chart_version = ""
    if isinstance(chart, dict):
        raw_metadata = chart.get("metadata")
        metadata: Mapping[str, Any] = raw_metadata if isinstance(raw_metadata, dict) else {}
        chart_name = str(metadata.get("name", ""))
        chart_version = str(metadata.get("version", ""))
        if chart_name != "prometheus-adapter" or not re.fullmatch(r"[0-9][0-9A-Za-z_.+-]*", chart_version):
            raise DeploymentError("existing prometheus-adapter release has no stable chart version")
    else:
        match = re.fullmatch(r"prometheus-adapter-(.+)", str(chart))
        if match:
            chart_version = match.group(1)
    if not chart_version:
        raise DeploymentError("existing prometheus-adapter release has no stable chart version")
    adapter_previous = _latest_revision(
        runner(["helm", "-n", adapter_namespace, "history", adapter_release, "--max", "1", "-o", "json"], True)
    )
    live_values = yaml.safe_load(
        runner(["helm", "-n", adapter_namespace, "get", "values", adapter_release, "--all", "-o", "yaml"], True)
    )
    source_values = yaml.safe_load(adapter_values_file.read_text(encoding="utf-8"))
    merged_values = merge_adapter_values(
        _mapping(live_values, field="live adapter values"), _mapping(source_values, field="source adapter values")
    )
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False, encoding="utf-8") as handle:
        yaml.safe_dump(merged_values, handle, sort_keys=False)
        merged_path = Path(handle.name)
    try:
        runner(
            [
                "helm",
                "repo",
                "add",
                "prometheus-community",
                "https://prometheus-community.github.io/helm-charts",
                "--if-not-exists",
            ],
            False,
        )
        runner(
            [
                "helm",
                "-n",
                adapter_namespace,
                "upgrade",
                adapter_release,
                "prometheus-community/prometheus-adapter",
                f"--version={chart_version}",
                f"--values={merged_path}",
                "--atomic",
                "--wait",
                "--timeout=30m",
            ],
            False,
        )
    except Exception:
        runner(
            ["helm", "-n", adapter_namespace, "rollback", adapter_release, adapter_previous, "--wait", "--timeout=30m"],
            False,
        )
        raise
    finally:
        merged_path.unlink(missing_ok=True)

    previous_stream: str | None = None
    try:
        try:
            previous_stream = _latest_revision(
                runner(["helm", "-n", plan.namespace, "history", plan.release, "--max", "1", "-o", "json"], True)
            )
        except subprocess.CalledProcessError:
            previous_stream = None
        if previous_stream:
            _write_output(github_output, {"previous_stream_helm_revision": previous_stream})
        runner(
            [
                "helm",
                "-n",
                plan.namespace,
                "upgrade",
                "--install",
                plan.release,
                "backend/charts/parakeet",
                f"--values={plan.values_file}",
                f"--values={plan.stream_values_file}",
                f"--set-string=image.repository={target_repository}",
                f"--set-string=image.digest={plan.image_digest}",
                "--set-string=image.tag=",
                "--atomic",
                "--wait",
                "--timeout=45m",
            ],
            False,
        )
        runner(
            ["kubectl", "-n", plan.namespace, "rollout", "status", f"deployment/{plan.release}", "--timeout=45m"], False
        )
        pods = _verify_warm_fleet(plan, runner, expected_image_ref=target_image_ref)
        _verify_metrics(plan, pods, runner)
        address = _service_ip(plan, runner)
    except Exception:
        try:
            if previous_stream:
                runner(
                    [
                        "helm",
                        "-n",
                        plan.namespace,
                        "rollback",
                        plan.release,
                        previous_stream,
                        "--wait",
                        "--timeout=45m",
                    ],
                    False,
                )
            else:
                runner(["helm", "-n", plan.namespace, "uninstall", plan.release, "--wait", "--timeout=45m"], False)
            runner(
                [
                    "helm",
                    "-n",
                    adapter_namespace,
                    "rollback",
                    adapter_release,
                    adapter_previous,
                    "--wait",
                    "--timeout=30m",
                ],
                False,
            )
        finally:
            raise

    url = f"http://{address}:8080"
    _write_output(
        github_output,
        {
            "hosted_parakeet_stream_api_url": url,
            "stream_ilb_ip": address,
            "image_ref": target_image_ref,
            "parakeet_source_image_ref": promotion["source_image_ref"],
            "parakeet_target_image_ref": target_image_ref,
            "parakeet_image_promotion_mode": promotion["mode"],
        },
    )
    return url


def _defaults(environment: str) -> tuple[Path, Path, Path]:
    root = Path(__file__).resolve().parents[2]
    return (
        root / "backend/charts/parakeet" / f"{environment}_omi_parakeet_values.yaml",
        root / "backend/charts/parakeet" / f"{environment}_omi_parakeet_stream_values.yaml",
        root / "backend/charts/monitoring/prometheus-adapter" / f"{environment}_omi_prometheus_adapter.yaml",
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--environment", choices=("dev", "prod"), required=True)
    parser.add_argument("--project", required=True)
    parser.add_argument("--cluster", required=True)
    parser.add_argument("--region", default="us-central1")
    parser.add_argument("--image-repository", required=True)
    parser.add_argument("--image-digest", required=True)
    parser.add_argument("--node-pool")
    parser.add_argument("--values-file", type=Path)
    parser.add_argument("--stream-values-file", type=Path)
    parser.add_argument("--adapter-values-file", type=Path)
    parser.add_argument("--adapter-release")
    parser.add_argument("--qualification-evidence", type=Path, required=False)
    parser.add_argument("--source-sha", default="", help="admitted source SHA recorded in the qualification artifact")
    parser.add_argument("--github-output", type=Path)
    parser.add_argument("--allow-node-pool-provision", action="store_true")
    parser.add_argument("--apply", action="store_true", help="perform GKE/Helm changes; omitted means source-only plan")
    args = parser.parse_args(argv)
    values_default, stream_default, adapter_default = _defaults(args.environment)
    plan = build_plan(
        environment=args.environment,
        values_file=args.values_file or values_default,
        stream_values_file=args.stream_values_file or stream_default,
        image_repository=args.image_repository,
        image_digest=args.image_digest,
        node_pool=args.node_pool,
    )
    if not args.apply:
        print(json.dumps({"plan": plan.as_json(), "order": deployment_order()}, sort_keys=True))
        return 0
    if not args.qualification_evidence:
        raise DeploymentError("--qualification-evidence is required with --apply")
    try:
        evidence = _mapping(
            json.loads(args.qualification_evidence.read_text(encoding="utf-8")), field="qualification evidence"
        )
    except (OSError, json.JSONDecodeError) as exc:
        raise DeploymentError("could not read Parakeet qualification evidence") from exc
    url = deploy_stream_fleet(
        plan,
        cluster=args.cluster,
        region=args.region,
        project=args.project,
        adapter_values_file=args.adapter_values_file or adapter_default,
        adapter_release=args.adapter_release or f"{args.environment}-omi-prometheus-adapter",
        qualification_evidence=evidence,
        source_sha=args.source_sha,
        allow_node_pool_provision=args.allow_node_pool_provision,
        github_output=args.github_output,
    )
    print(json.dumps({"plan": plan.as_json(), "hosted_parakeet_stream_api_url": url}, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except DeploymentError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
