"""Pure Parakeet streaming release contracts and evidence validators."""

from __future__ import annotations

import math
import re
import subprocess
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence, cast

import yaml


class DeploymentError(RuntimeError):
    """Raised when a release precondition or post-deploy check fails."""


Config = dict[str, Any]
CommandRunner = Callable[[Sequence[str], bool], str]

# The qualification artifact and the live stream health endpoint must agree on
# the concrete TDT checkpoint and decoder contract.  Keeping this contract here
# makes the release gate independent of mutable environment defaults.
EXPECTED_STREAM_MODEL_IDENTITY: dict[str, str] = {
    "stream_model": "nvidia/parakeet-tdt-0.6b-v3",
    "backend": "nemo",
    "decoder_family": "tdt",
    "language_support": "multilingual",
    "model_revision": "541d1f99c6b0c3cd0b11a95167540bb8edefd82b",
}


@dataclass(frozen=True)
class StreamValues:
    peak: int
    headroom: int
    target: int
    failures: int
    warm: int
    maximum: int
    surge: int


@dataclass(frozen=True)
class StreamFleetPlan:
    environment: str
    namespace: str
    release: str
    service: str
    values_file: str
    stream_values_file: str
    node_pool: str
    peak_concurrent_streams: int
    headroom_percent: int
    target_streams_per_pod: int
    failure_replicas: int
    hard_stream_capacity: int
    warm_replicas: int
    max_replicas: int
    surge_replicas: int
    max_nodes: int
    image_repository: str
    image_digest: str

    @property
    def service_dns(self) -> str:
        return f"http://{self.service}.{self.namespace}.svc.cluster.local:8080"

    @property
    def service_selector(self) -> str:
        return f"app.kubernetes.io/instance={self.release}"

    @property
    def node_selector(self) -> str:
        return f"cloud.google.com/gke-nodepool={self.node_pool},service=parakeet-stream,env={self.environment}"

    @property
    def image_ref(self) -> str:
        return f"{self.image_repository}@{self.image_digest}"

    def as_json(self) -> Config:
        result = asdict(self)
        result.update(
            {
                "image_ref": self.image_ref,
                "service_dns": self.service_dns,
                "capacity_target": self.warm_replicas * self.target_streams_per_pod,
            }
        )
        return result


def _mapping(value: object, *, field: str) -> Config:
    if not isinstance(value, dict):
        raise DeploymentError(f"{field} must be a YAML mapping")
    return cast(Config, value)


def _positive_int(value: object, *, field: str) -> int:
    if isinstance(value, bool):
        raise DeploymentError(f"{field} must be a positive integer")
    try:
        parsed = int(cast(Any, value))
    except (TypeError, ValueError) as exc:
        raise DeploymentError(f"{field} must be a positive integer") from exc
    if parsed < 1:
        raise DeploymentError(f"{field} must be a positive integer")
    return parsed


def _nonnegative_int(value: object, *, field: str) -> int:
    if isinstance(value, bool):
        raise DeploymentError(f"{field} must be a non-negative integer")
    try:
        parsed = int(cast(Any, value))
    except (TypeError, ValueError) as exc:
        raise DeploymentError(f"{field} must be a non-negative integer") from exc
    if parsed < 0:
        raise DeploymentError(f"{field} must be a non-negative integer")
    return parsed


def _surge_count(value: object) -> int:
    if isinstance(value, str) and value.endswith("%"):
        raise DeploymentError("stream rollout must use an integer maxSurge so node capacity is explicit")
    return _nonnegative_int(value, field="strategy.rollingUpdate.maxSurge")


def _configured_stream_capacity(raw: Config) -> int:
    entries = raw.get("env")
    if not isinstance(entries, list):
        raise DeploymentError("Parakeet values must declare an env list")
    for item in entries:
        if isinstance(item, dict) and item.get("name") == "PARAKEET_STREAM_CAPACITY":
            return _positive_int(item.get("value"), field="env.PARAKEET_STREAM_CAPACITY")
    raise DeploymentError("Parakeet values must declare PARAKEET_STREAM_CAPACITY")


def _validate_stream_values(raw: Config, *, environment: str) -> StreamValues:
    if str(raw.get("serviceMode", "")).lower() != "stream":
        raise DeploymentError("stream values must set serviceMode=stream")
    service = _mapping(raw.get("service"), field="service")
    if service.get("type") != "LoadBalancer":
        raise DeploymentError("stream service must be an internal LoadBalancer")
    annotations = _mapping(service.get("annotations", {}), field="service.annotations")
    if annotations.get("networking.gke.io/load-balancer-type") != "Internal":
        raise DeploymentError("stream service must use an internal GKE load balancer")

    capacity = _mapping(raw.get("capacityPlan"), field="capacityPlan")
    peak = _positive_int(capacity.get("peakConcurrentStreams"), field="capacityPlan.peakConcurrentStreams")
    headroom = _nonnegative_int(capacity.get("headroomPercent"), field="capacityPlan.headroomPercent")
    failures = _positive_int(capacity.get("failureReplicas"), field="capacityPlan.failureReplicas")
    autoscaling = _mapping(raw.get("autoscaling"), field="autoscaling")
    if autoscaling.get("enabled") is not True:
        raise DeploymentError("stream autoscaling must be enabled")
    target = _positive_int(autoscaling.get("streamsPerPod"), field="autoscaling.streamsPerPod")
    minimum = _positive_int(autoscaling.get("minReplicas"), field="autoscaling.minReplicas")
    maximum = _positive_int(autoscaling.get("maxReplicas"), field="autoscaling.maxReplicas")
    if maximum < minimum:
        raise DeploymentError("autoscaling.maxReplicas must be >= minReplicas")
    required = math.ceil(peak * (100 + headroom) / (100 * target)) + failures
    if minimum != required:
        raise DeploymentError(f"stream warm floor {minimum} does not satisfy capacity plan {required}")

    strategy = _mapping(raw.get("strategy"), field="strategy")
    rolling = _mapping(strategy.get("rollingUpdate"), field="strategy.rollingUpdate")
    if _nonnegative_int(rolling.get("maxUnavailable"), field="strategy.rollingUpdate.maxUnavailable") != 0:
        raise DeploymentError("stream rollout must keep maxUnavailable=0")
    surge = _surge_count(rolling.get("maxSurge"))
    if surge < 1:
        raise DeploymentError("stream rollout must reserve at least one surge pod")

    selector = _mapping(raw.get("nodeSelector"), field="nodeSelector")
    for key, expected in {
        "cloud.google.com/gke-accelerator": "nvidia-l4",
        "service": "parakeet-stream",
        "env": environment,
    }.items():
        if selector.get(key) != expected:
            raise DeploymentError(f"nodeSelector.{key} must be {expected!r}")
    return StreamValues(
        peak=peak,
        headroom=headroom,
        target=target,
        failures=failures,
        warm=minimum,
        maximum=maximum,
        surge=surge,
    )


def build_plan(
    *,
    environment: str,
    values_file: Path,
    stream_values_file: Path,
    image_repository: str,
    image_digest: str,
    node_pool: str | None = None,
) -> StreamFleetPlan:
    """Validate source values and derive the immutable deployment plan."""
    if environment not in {"dev", "prod"}:
        raise DeploymentError("environment must be dev or prod")
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", image_digest):
        raise DeploymentError("image_digest must be a lowercase sha256 digest")
    if not image_repository or "@" in image_repository or ":" in image_repository.rsplit("/", 1)[-1]:
        raise DeploymentError("image_repository must be a repository without a tag or digest")
    expected_pool = f"{environment}-omi-parakeet-stream-pool"
    if node_pool is not None and node_pool != expected_pool:
        raise DeploymentError("node_pool must be the task-owned Parakeet stream pool name")
    try:
        stream_raw = _mapping(
            yaml.safe_load(stream_values_file.read_text(encoding="utf-8")), field=str(stream_values_file)
        )
        base_raw = _mapping(yaml.safe_load(values_file.read_text(encoding="utf-8")), field=str(values_file))
    except OSError as exc:
        raise DeploymentError("could not read Parakeet values") from exc
    hard_capacity = _configured_stream_capacity(base_raw)
    stream_values = _validate_stream_values(stream_raw, environment=environment)
    return StreamFleetPlan(
        environment=environment,
        namespace=f"{environment}-omi-backend",
        release=f"{environment}-omi-parakeet-stream",
        service=f"{environment}-omi-parakeet-stream",
        values_file=str(values_file),
        stream_values_file=str(stream_values_file),
        node_pool=node_pool or f"{environment}-omi-parakeet-stream-pool",
        peak_concurrent_streams=stream_values.peak,
        headroom_percent=stream_values.headroom,
        target_streams_per_pod=stream_values.target,
        failure_replicas=stream_values.failures,
        hard_stream_capacity=hard_capacity,
        warm_replicas=stream_values.warm,
        max_replicas=stream_values.maximum,
        surge_replicas=stream_values.surge,
        max_nodes=stream_values.maximum + stream_values.surge,
        image_repository=image_repository,
        image_digest=image_digest,
    )


def validate_gpu_quota(region_document: Mapping[str, Any], required_gpus: int) -> None:
    """Require regional L4 headroom for only the additional fleet nodes."""
    if required_gpus < 0:
        raise DeploymentError("required GPU count cannot be negative")
    quotas = region_document.get("quotas")
    if not isinstance(quotas, list):
        raise DeploymentError("region quota response has no quotas list")
    l4 = next(
        (
            item
            for item in quotas
            if isinstance(item, dict)
            and "NVIDIA_L4" in str(item.get("metric", item.get("name", ""))).upper().replace("-", "_")
        ),
        None,
    )
    if l4 is None:
        raise DeploymentError("regional NVIDIA_L4 quota is not visible; refusing to size a GPU fleet")
    try:
        headroom = float(l4["limit"]) - float(l4.get("usage", 0))
    except (KeyError, TypeError, ValueError) as exc:
        raise DeploymentError("regional NVIDIA_L4 quota has no numeric limit/usage") from exc
    if headroom < required_gpus:
        raise DeploymentError(f"regional NVIDIA_L4 quota headroom {headroom:g} is below required {required_gpus} GPUs")


def validate_capacity_evidence(
    evidence: Mapping[str, Any], *, image_ref: str, required_capacity: int, source_sha: str = ""
) -> None:
    """Require a successful GPU result for this exact image and source."""
    if evidence.get("schema_version") != 1 or evidence.get("status") != "ok":
        raise DeploymentError("Parakeet stream qualification evidence is missing or not successful")
    if evidence.get("endpoint") != "/v3/stream":
        raise DeploymentError("Parakeet qualification evidence is not for the realtime stream endpoint")
    if evidence.get("image_ref") != image_ref:
        raise DeploymentError("Parakeet qualification evidence is not bound to the exact deployment image digest")
    validate_tdt_model_identity(
        evidence.get("expected_model_identity"),
        field="qualification expected_model_identity",
        exact=True,
    )
    runtime_health = evidence.get("runtime_health")
    if not isinstance(runtime_health, dict):
        raise DeploymentError("Parakeet qualification evidence has no runtime health result")
    validate_tdt_model_identity(
        runtime_health.get("model_identity"),
        field="qualification runtime_health.model_identity",
    )
    recorded_sha = evidence.get("source_sha")
    if not isinstance(recorded_sha, str) or not recorded_sha:
        raise DeploymentError("Parakeet qualification evidence has no source SHA")
    if source_sha and recorded_sha != source_sha:
        raise DeploymentError("Parakeet qualification evidence is not bound to the admitted source SHA")
    try:
        measured = int(evidence["expected_capacity"])
    except (KeyError, TypeError, ValueError) as exc:
        raise DeploymentError("Parakeet qualification evidence has no numeric expected_capacity") from exc
    if measured < required_capacity:
        raise DeploymentError(f"measured stream capacity {measured} is below required {required_capacity}")
    gpu = evidence.get("gpu")
    if not isinstance(gpu, dict) or gpu.get("type") != "nvidia-l4":
        raise DeploymentError("Parakeet qualification evidence was not measured on an NVIDIA L4")
    latency_gate = evidence.get("latency_gate")
    if not isinstance(latency_gate, dict):
        raise DeploymentError("Parakeet qualification evidence has no latency gate")
    declared_latency = _finite_measurement(latency_gate.get("max_p95_seconds"), field="latency_gate.max_p95_seconds")
    if declared_latency > 4:
        raise DeploymentError("Parakeet qualification latency threshold exceeds the 4 second release bound")
    levels = evidence.get("levels")
    if not isinstance(levels, list) or not levels or not all(isinstance(level, dict) for level in levels):
        raise DeploymentError("Parakeet qualification evidence has no measured stream levels")
    level_requests = [
        _positive_int(level.get("requested_streams"), field="levels.requested_streams") for level in levels
    ]
    highest_level = max(level_requests)
    if highest_level < required_capacity:
        raise DeploymentError("Parakeet qualification levels do not cover the required stream capacity")
    if measured != highest_level:
        raise DeploymentError("declared stream capacity does not equal the highest measured stream level")
    for level, requested in zip(levels, level_requests):
        accepted = _nonnegative_int(level.get("accepted_streams"), field="levels.accepted_streams")
        if accepted > requested:
            raise DeploymentError("Parakeet qualification level has an invalid accepted stream count")
        observed_latency = _finite_measurement(level.get("text_latency_p95_s"), field="levels.text_latency_p95_s")
        if observed_latency > declared_latency or observed_latency > 4:
            raise DeploymentError("Parakeet qualification measured text latency exceeds the release bound")
    sustained = evidence.get("sustained")
    if not isinstance(sustained, dict):
        raise DeploymentError("Parakeet qualification evidence has no sustained capacity result")
    sustained_requested = _positive_int(sustained.get("requested_streams"), field="sustained.requested_streams")
    sustained_accepted = _nonnegative_int(sustained.get("accepted_streams"), field="sustained.accepted_streams")
    if sustained_requested < required_capacity or sustained_accepted < required_capacity:
        raise DeploymentError("sustained qualification did not accept the required stream capacity")
    sustained_duration = _finite_measurement(
        sustained.get("audio_duration_s", sustained.get("duration_s")), field="sustained.audio_duration_s"
    )
    if sustained_duration < 180:
        raise DeploymentError("sustained qualification duration is below 180 seconds")
    sustained_latency = _finite_measurement(sustained.get("text_latency_p95_s"), field="sustained.text_latency_p95_s")
    if sustained_latency > declared_latency or sustained_latency > 4:
        raise DeploymentError("sustained qualification measured text latency exceeds the release bound")
    qualification = evidence.get("qualification")
    if not isinstance(qualification, dict):
        raise DeploymentError("Parakeet qualification evidence has no qualification result")
    required = (
        "accepted_levels_complete",
        "rejection_probe_enforced",
        "stream_readiness",
        "latency_gate",
        "sustained_capacity_complete",
        "gpu_memory_observed",
        "model_identity",
        "text_sentinel_smoke",
    )
    if any(qualification.get(flag) is not True for flag in required):
        raise DeploymentError("Parakeet stream qualification did not pass all capacity and GPU checks")


def validate_tdt_model_identity(identity: object, *, field: str, exact: bool = False) -> None:
    """Require the release artifact or live pod to identify the qualified TDT weights."""
    if not isinstance(identity, dict) or any(
        identity.get(key) != value for key, value in EXPECTED_STREAM_MODEL_IDENTITY.items()
    ):
        raise DeploymentError(f"{field} model identity does not identify the expected Parakeet TDT model revision")
    if exact and identity != EXPECTED_STREAM_MODEL_IDENTITY:
        raise DeploymentError(f"{field} model identity contains unexpected fields")


def _finite_measurement(value: object, *, field: str) -> float:
    if isinstance(value, bool):
        raise DeploymentError(f"{field} must be a finite number")
    try:
        parsed = float(cast(Any, value))
    except (TypeError, ValueError) as exc:
        raise DeploymentError(f"{field} must be a finite number") from exc
    if not math.isfinite(parsed) or parsed < 0:
        raise DeploymentError(f"{field} must be a finite non-negative number")
    return parsed


def _capacity_value(value: object) -> float:
    if isinstance(value, bool):
        return -1
    match = re.fullmatch(
        r"(?P<number>(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)(?P<suffix>n|u|m|Ki|Mi|Gi|Ti|Pi|Ei|k|K|M|G|T|P|E)?",
        str(value),
    )
    if not match:
        return -1
    parsed = float(match.group("number"))
    parsed *= {
        "n": 1e-9,
        "u": 1e-6,
        "m": 1e-3,
        "k": 1e3,
        "K": 1e3,
        "M": 1e6,
        "G": 1e9,
        "T": 1e12,
        "P": 1e15,
        "E": 1e18,
        "Ki": 1024,
        "Mi": 1024**2,
        "Gi": 1024**3,
        "Ti": 1024**4,
        "Pi": 1024**5,
        "Ei": 1024**6,
        None: 1,
    }[match.group("suffix")]
    return parsed if math.isfinite(parsed) and parsed >= 0 else -1


def promote_qualified_image(source_image_ref: str, *, target_project: str, runner: CommandRunner) -> Config:
    """Promote a qualified GCR digest without permitting a mutable rewrite."""
    source_match = re.fullmatch(r"gcr\.io/([^/]+)/parakeet@(sha256:[0-9a-f]{64})", source_image_ref)
    if not source_match:
        raise DeploymentError("qualified Parakeet image must be gcr.io/<project>/parakeet@sha256:digest")
    if not re.fullmatch(r"[a-z][a-z0-9-]{2,62}", target_project):
        raise DeploymentError("target project is not a valid GCP project identifier")
    source_project, digest = source_match.groups()
    target_repository = f"gcr.io/{target_project}/parakeet"
    target_tag = f"{target_repository}:sha256-{digest.removeprefix('sha256:')}"
    target_image_ref = f"{target_repository}@{digest}"

    def describe(image: str) -> Config:
        try:
            value = json.loads(runner(["gcloud", "container", "images", "describe", image, "--format=json"], True))
        except subprocess.CalledProcessError:
            raise
        except json.JSONDecodeError as exc:
            raise DeploymentError("container registry describe response was not JSON") from exc
        return _mapping(value, field="container registry image")

    source = describe(source_image_ref)
    source_summary = source.get("image_summary")
    source_digest = source_summary.get("digest") if isinstance(source_summary, dict) else source.get("digest")
    if source_digest != digest:
        raise DeploymentError("qualified source image registry digest does not match the admitted digest")
    if source_project == target_project:
        return {
            "source_image_ref": source_image_ref,
            "target_repository": target_repository,
            "target_tag": target_tag,
            "target_image_ref": target_image_ref,
            "verified_digest": digest,
            "mode": "same-project-verified",
        }

    try:
        existing = describe(target_tag)
    except subprocess.CalledProcessError:
        existing = None
    if existing is not None:
        summary = existing.get("image_summary")
        existing_digest = summary.get("digest") if isinstance(summary, dict) else existing.get("digest")
        if existing_digest != digest:
            raise DeploymentError("target promotion tag already points at a different digest")
    else:
        runner(["gcloud", "container", "images", "add-tag", source_image_ref, target_tag, "--quiet"], False)
    target = describe(target_tag)
    target_summary = target.get("image_summary")
    target_digest = target_summary.get("digest") if isinstance(target_summary, dict) else target.get("digest")
    if target_digest != digest:
        raise DeploymentError("target registry digest does not match the qualified source digest")
    return {
        "source_image_ref": source_image_ref,
        "target_repository": target_repository,
        "target_tag": target_tag,
        "target_image_ref": target_image_ref,
        "verified_digest": target_digest,
        "mode": "cross-project-copied" if existing is None else "cross-project-existing-verified",
    }


def _label_map(document: Mapping[str, Any]) -> Mapping[str, Any]:
    raw_config = document.get("config")
    config: Mapping[str, Any] = raw_config if isinstance(raw_config, dict) else {}
    for key in ("labels", "nodeLabels"):
        labels = config.get(key) if isinstance(config, dict) else None
        if isinstance(labels, dict):
            return labels
    return {}


def current_node_count(document: Mapping[str, Any]) -> int:
    """Read an explicitly reported allocated node count, never zone URLs."""
    raw_status = document.get("status")
    status: Mapping[str, Any] = raw_status if isinstance(raw_status, dict) else {}
    for value in (status.get("currentNodeCount"), status.get("nodeCount"), document.get("currentNodeCount")):
        if value is not None:
            try:
                count = int(cast(Any, value))
            except (TypeError, ValueError):
                continue
            if count >= 0:
                return count
    raise DeploymentError("owned Parakeet stream pool does not report its current node count")


def validate_owned_node_pool(document: Mapping[str, Any], plan: StreamFleetPlan) -> None:
    """Validate a pool's immutable shape and ownership before reuse."""
    raw_config = document.get("config")
    config: Mapping[str, Any] = raw_config if isinstance(raw_config, dict) else {}
    machine = str(config.get("machineType", "")).rsplit("/", 1)[-1]
    if machine != "g2-standard-8":
        raise DeploymentError("owned Parakeet stream pool is not g2-standard-8")
    accelerators = config.get("accelerators", config.get("accelerator", []))
    if isinstance(accelerators, dict):
        accelerators = [accelerators]
    if not isinstance(accelerators, list) or len(accelerators) != 1 or not isinstance(accelerators[0], dict):
        raise DeploymentError("owned Parakeet stream pool must have exactly one accelerator declaration")
    accelerator = accelerators[0]
    accelerator_type = str(accelerator.get("acceleratorType", accelerator.get("type", ""))).rsplit("/", 1)[-1]
    if accelerator_type != "nvidia-l4" or str(accelerator.get("acceleratorCount", accelerator.get("count", ""))) != "1":
        raise DeploymentError("owned Parakeet stream pool must have exactly one NVIDIA L4 per node")
    raw_autoscaling = document.get("autoscaling")
    autoscaling: Mapping[str, Any] = raw_autoscaling if isinstance(raw_autoscaling, dict) else {}
    try:
        minimum = int(autoscaling.get("totalMinNodeCount", autoscaling.get("minNodeCount", -1)))
        maximum = int(autoscaling.get("totalMaxNodeCount", autoscaling.get("maxNodeCount", -1)))
    except (TypeError, ValueError) as exc:
        raise DeploymentError("owned Parakeet stream pool has invalid autoscaling bounds") from exc
    if autoscaling.get("enabled") is not True:
        raise DeploymentError("owned Parakeet stream pool must use cluster autoscaling")
    if minimum != plan.warm_replicas:
        raise DeploymentError("owned Parakeet stream pool minimum does not match the stream warm floor")
    if maximum != plan.max_nodes:
        raise DeploymentError("owned Parakeet stream pool maximum does not match HPA plus surge")
    labels = _label_map(document)
    for key, value in {
        "service": "parakeet-stream",
        "env": plan.environment,
        "omi.dev/managed-by": "parakeet-stream-release",
    }.items():
        if str(labels.get(key, "")) != value:
            raise DeploymentError(f"owned Parakeet stream pool is missing immutable ownership label {key}={value}")
    accelerator_label = labels.get("cloud.google.com/gke-accelerator")
    if accelerator_label is not None and str(accelerator_label) != "nvidia-l4":
        raise DeploymentError("owned Parakeet stream pool has a non-L4 accelerator label")


def merge_adapter_values(live: Mapping[str, Any], source: Mapping[str, Any]) -> Config:
    """Merge owned adapter rules while preserving unrelated live settings."""

    def merge(left: object, right: object, path: tuple[str, ...] = ()) -> object:
        if isinstance(left, dict) and isinstance(right, dict):
            result = dict(left)
            for key, value in right.items():
                result[key] = merge(result[key], value, path + (str(key),)) if key in result else value
            return result
        if (
            isinstance(left, list)
            and isinstance(right, list)
            and path[-2:] in (("rules", "custom"), ("rules", "external"))
        ):
            result = list(left)
            names = {
                str(item.get("name", {}).get("as", ""))
                for item in result
                if isinstance(item, dict) and isinstance(item.get("name"), dict)
            }
            for item in right:
                name = str(item.get("name", {}).get("as", "")) if isinstance(item, dict) else ""
                if name and name in names:
                    result = [
                        old
                        for old in result
                        if not (isinstance(old, dict) and str(old.get("name", {}).get("as", "")) == name)
                    ]
                result.append(item)
                if name:
                    names.add(name)
            return result
        return right

    return cast(Config, merge(dict(live), dict(source)))
