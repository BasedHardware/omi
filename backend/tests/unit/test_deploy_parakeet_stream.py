"""Source and orchestration contracts for the Parakeet stream release gate."""

from __future__ import annotations

import copy
import datetime as dt
import json
import subprocess
from pathlib import Path

import pytest

from scripts.deploy_parakeet_stream import (
    DeploymentError,
    _capacity_value,
    build_plan,
    deploy_stream_fleet,
    deployment_order,
    promote_qualified_image,
    _verify_warm_fleet_once,
    merge_adapter_values,
    validate_capacity_evidence,
    validate_gpu_quota,
    validate_owned_node_pool,
)
from scripts.parakeet_stream_contract import EXPECTED_STREAM_MODEL_IDENTITY
import scripts.deploy_parakeet_stream as deploy_module

ROOT = Path(__file__).resolve().parents[2]
PARAKEET = ROOT / "charts/parakeet"


def _plan(environment: str = "prod"):
    return build_plan(
        environment=environment,
        values_file=PARAKEET / f"{environment}_omi_parakeet_values.yaml",
        stream_values_file=PARAKEET / f"{environment}_omi_parakeet_stream_values.yaml",
        image_repository=f"gcr.io/example-{environment}/parakeet",
        image_digest="sha256:" + "a" * 64,
    )


def test_capacity_plan_derives_warm_floor_and_one_surge_node():
    plan = _plan()
    assert plan.warm_replicas == 99
    assert plan.max_replicas == 150
    assert plan.max_nodes == 151
    assert plan.hard_stream_capacity == 10
    assert plan.service_dns == "http://prod-omi-parakeet-stream.prod-omi-backend.svc.cluster.local:8080"
    assert plan.image_ref.endswith("@sha256:" + "a" * 64)


def test_dev_capacity_plan_keeps_a_two_pod_floor_and_four_pod_ceiling():
    plan = _plan("dev")
    assert (plan.warm_replicas, plan.max_replicas, plan.max_nodes) == (2, 4, 5)


def test_build_plan_rejects_mutable_image_identity():
    with pytest.raises(DeploymentError, match="image_digest"):
        build_plan(
            environment="prod",
            values_file=PARAKEET / "prod_omi_parakeet_values.yaml",
            stream_values_file=PARAKEET / "prod_omi_parakeet_stream_values.yaml",
            image_repository="gcr.io/example/parakeet",
            image_digest="latest",
        )


def test_quota_gate_uses_incremental_headroom():
    document = {"quotas": [{"metric": "NVIDIA_L4_GPUS", "limit": 160, "usage": 120}]}
    validate_gpu_quota(document, 40)
    with pytest.raises(DeploymentError, match="headroom"):
        validate_gpu_quota(document, 41)


def test_owned_pool_requires_shape_and_ownership_without_mutation():
    plan = _plan()
    pool = {
        "config": {
            "machineType": "projects/p/zones/z/machineTypes/g2-standard-8",
            "accelerators": [{"acceleratorType": "nvidia-l4", "acceleratorCount": "1"}],
            "labels": {
                "service": "parakeet-stream",
                "env": "prod",
                "cloud.google.com/gke-accelerator": "nvidia-l4",
                "omi.dev/managed-by": "parakeet-stream-release",
            },
        },
        "autoscaling": {"enabled": True, "minNodeCount": 99, "maxNodeCount": 151},
        "status": {"currentNodeCount": 99},
    }
    original = copy.deepcopy(pool)
    validate_owned_node_pool(pool, plan)
    assert pool == original

    bad = copy.deepcopy(pool)
    bad["autoscaling"]["maxNodeCount"] = 160
    with pytest.raises(DeploymentError, match="maximum"):
        validate_owned_node_pool(bad, plan)


def test_adapter_merge_preserves_external_rules_and_replaces_owned_metric():
    live = {
        "rules": {
            "custom": [
                {"name": {"as": "external_metric"}, "seriesQuery": "external"},
                {"name": {"as": "parakeet_stream_demand"}, "seriesQuery": "old"},
            ]
        },
        "affinity": {"nodeAffinity": {"requiredDuringSchedulingIgnoredDuringExecution": []}},
    }
    source = {
        "rules": {
            "custom": [
                {"name": {"as": "parakeet_stream_demand"}, "seriesQuery": "new"},
            ]
        }
    }
    merged = merge_adapter_values(live, source)
    rules = merged["rules"]["custom"]
    assert [rule["name"]["as"] for rule in rules] == ["external_metric", "parakeet_stream_demand"]
    assert rules[1]["seriesQuery"] == "new"
    assert "affinity" in merged


def test_qualification_is_bound_to_exact_image_and_hard_capacity():
    image_ref = "gcr.io/example/parakeet@sha256:" + "b" * 64
    evidence = {
        "schema_version": 1,
        "status": "ok",
        "endpoint": "/v3/stream",
        "image_ref": image_ref,
        "source_sha": "source-123",
        "runtime_health": {"model_identity": {**EXPECTED_STREAM_MODEL_IDENTITY, "model_loaded": True}},
        "expected_model_identity": dict(EXPECTED_STREAM_MODEL_IDENTITY),
        "expected_capacity": 25,
        "gpu": {"type": "nvidia-l4"},
        "latency_gate": {"max_p95_seconds": 4},
        "levels": [{"requested_streams": 25, "accepted_streams": 25, "text_latency_p95_s": 1}],
        "sustained": {
            "requested_streams": 25,
            "accepted_streams": 25,
            "audio_duration_s": 180,
            "text_latency_p95_s": 1,
        },
        "qualification": {
            "accepted_levels_complete": True,
            "rejection_probe_enforced": True,
            "stream_readiness": True,
            "latency_gate": True,
            "sustained_capacity_complete": True,
            "gpu_memory_observed": True,
            "model_identity": True,
            "text_sentinel_smoke": True,
        },
    }
    validate_capacity_evidence(evidence, image_ref=image_ref, required_capacity=25, source_sha="source-123")
    wrong_image = dict(evidence, image_ref=image_ref.replace("b" * 64, "c" * 64))
    with pytest.raises(DeploymentError, match="exact deployment image"):
        validate_capacity_evidence(wrong_image, image_ref=image_ref, required_capacity=25)


def test_deployment_order_keeps_capacity_before_runtime_and_listener():
    order = deployment_order()
    assert order.index("upgrade-stream-release") < order.index("render-runtime-env")
    assert order.index("verify-warm-pods-gpu-health-endpoints") < order.index("deploy-backend-listen")


def test_metric_quantity_parser_accepts_milli_units_and_rejects_nan():
    assert _capacity_value("1000m") == 1
    assert _capacity_value("NaN") < 0


class _PromotionRunner:
    def __init__(self, source_digest, target_digest=None, *, target_exists=False):
        self.source_digest = source_digest
        self.target_digest = target_digest or source_digest
        self.target_exists = target_exists
        self.calls = []

    def __call__(self, command, capture=False):
        command = tuple(command)
        self.calls.append(command)
        if command[:4] == ("gcloud", "container", "images", "describe"):
            if "@" not in command[4] and not self.target_exists:
                raise subprocess.CalledProcessError(1, command)
            digest = self.source_digest if "@" in command[4] else self.target_digest
            return json.dumps({"image_summary": {"digest": digest}})
        if command[:4] == ("gcloud", "container", "images", "add-tag"):
            self.target_exists = True
        return ""


def test_cross_project_promotion_uses_digest_derived_tag_and_verifies_target():
    digest = "sha256:" + "a" * 64
    runner = _PromotionRunner(digest)
    receipt = promote_qualified_image(
        "gcr.io/based-hardware-dev/parakeet@" + digest,
        target_project="based-hardware",
        runner=runner,
    )
    assert receipt["target_image_ref"] == "gcr.io/based-hardware/parakeet@" + digest
    assert receipt["target_tag"].endswith(":sha256-" + "a" * 64)
    assert any(command[:4] == ("gcloud", "container", "images", "add-tag") for command in runner.calls)


def test_promotion_rejects_target_digest_mismatch_before_release_mutation():
    digest = "sha256:" + "a" * 64
    runner = _PromotionRunner(digest, "sha256:" + "b" * 64, target_exists=True)
    with pytest.raises(DeploymentError, match="different digest"):
        promote_qualified_image(
            "gcr.io/based-hardware-dev/parakeet@" + digest,
            target_project="based-hardware",
            runner=runner,
        )
    assert not any(command[:4] == ("gcloud", "container", "images", "add-tag") for command in runner.calls)


def test_promotion_rejects_digest_mismatch_after_copy_verification():
    digest = "sha256:" + "a" * 64
    runner = _PromotionRunner(digest, "sha256:" + "b" * 64)
    with pytest.raises(DeploymentError, match="does not match"):
        promote_qualified_image(
            "gcr.io/based-hardware-dev/parakeet@" + digest,
            target_project="based-hardware",
            runner=runner,
        )
    assert any(command[:4] == ("gcloud", "container", "images", "add-tag") for command in runner.calls)


def test_same_project_promotion_verifies_without_retagging_or_rewriting():
    digest = "sha256:" + "a" * 64
    runner = _PromotionRunner(digest)
    receipt = promote_qualified_image(
        "gcr.io/based-hardware-dev/parakeet@" + digest,
        target_project="based-hardware-dev",
        runner=runner,
    )
    assert receipt["mode"] == "same-project-verified"
    assert not any(command[:4] == ("gcloud", "container", "images", "add-tag") for command in runner.calls)


def test_promotion_rejects_arbitrary_source_image_rewrite():
    digest = "sha256:" + "a" * 64
    with pytest.raises(DeploymentError, match="gcr.io/<project>/parakeet"):
        promote_qualified_image(
            "gcr.io/based-hardware-dev/other@" + digest,
            target_project="based-hardware",
            runner=_PromotionRunner(digest),
        )


def _qualified_evidence(plan):
    return {
        "schema_version": 1,
        "status": "ok",
        "endpoint": "/v3/stream",
        "image_ref": plan.image_ref,
        "source_sha": "source-123",
        "runtime_health": {"model_identity": {**EXPECTED_STREAM_MODEL_IDENTITY, "model_loaded": True}},
        "expected_model_identity": dict(EXPECTED_STREAM_MODEL_IDENTITY),
        "expected_capacity": plan.hard_stream_capacity,
        "gpu": {"type": "nvidia-l4"},
        "latency_gate": {"max_p95_seconds": 4},
        "levels": [
            {
                "requested_streams": plan.hard_stream_capacity,
                "accepted_streams": plan.hard_stream_capacity,
                "text_latency_p95_s": 1,
            }
        ],
        "sustained": {
            "requested_streams": plan.hard_stream_capacity,
            "accepted_streams": plan.hard_stream_capacity,
            "audio_duration_s": 180,
            "text_latency_p95_s": 1,
        },
        "qualification": {
            "accepted_levels_complete": True,
            "rejection_probe_enforced": True,
            "stream_readiness": True,
            "latency_gate": True,
            "sustained_capacity_complete": True,
            "gpu_memory_observed": True,
            "model_identity": True,
            "text_sentinel_smoke": True,
        },
    }


def test_artifact_cannot_claim_capacity_above_highest_measured_level():
    plan = _plan()
    evidence = _qualified_evidence(plan)
    evidence["expected_capacity"] = 64
    with pytest.raises(DeploymentError, match="highest measured stream level"):
        validate_capacity_evidence(evidence, image_ref=plan.image_ref, required_capacity=plan.hard_stream_capacity)


def test_artifact_requires_at_least_three_minutes_of_sustained_capacity():
    plan = _plan()
    evidence = _qualified_evidence(plan)
    evidence["sustained"]["audio_duration_s"] = 179
    with pytest.raises(DeploymentError, match="duration"):
        validate_capacity_evidence(evidence, image_ref=plan.image_ref, required_capacity=plan.hard_stream_capacity)


def test_artifact_requires_nvidia_l4_measurement():
    plan = _plan()
    evidence = _qualified_evidence(plan)
    evidence["gpu"]["type"] = "nvidia-a100"
    with pytest.raises(DeploymentError, match="NVIDIA L4"):
        validate_capacity_evidence(evidence, image_ref=plan.image_ref, required_capacity=plan.hard_stream_capacity)


def test_artifact_requires_text_sentinel_smoke():
    plan = _plan()
    evidence = _qualified_evidence(plan)
    evidence["qualification"]["text_sentinel_smoke"] = False
    with pytest.raises(DeploymentError, match="qualification"):
        validate_capacity_evidence(evidence, image_ref=plan.image_ref, required_capacity=plan.hard_stream_capacity)


class _ReleaseRunner:
    """Hermetic command adapter covering the release's mutation sequence."""

    def __init__(self, plan, *, missing_metrics=False, legacy_health=False, model_identity=None):
        self.plan = plan
        self.calls = []
        self.missing_metrics = missing_metrics
        self.legacy_health = legacy_health
        self.model_identity = model_identity or {**EXPECTED_STREAM_MODEL_IDENTITY, "model_loaded": True}
        self.target_image_ref = plan.image_ref
        self.target_exists = False
        self.pool = {
            "config": {
                "machineType": "projects/p/zones/z/machineTypes/g2-standard-8",
                "accelerators": [{"acceleratorType": "nvidia-l4", "acceleratorCount": "1"}],
                "labels": {
                    "service": "parakeet-stream",
                    "env": plan.environment,
                    "omi.dev/managed-by": "parakeet-stream-release",
                },
            },
            "autoscaling": {"enabled": True, "minNodeCount": plan.warm_replicas, "maxNodeCount": plan.max_nodes},
            "status": {"currentNodeCount": plan.warm_replicas},
        }

    def __call__(self, command, capture=False):
        command = tuple(command)
        self.calls.append(command)
        if command[:4] == ("gcloud", "container", "node-pools", "describe"):
            return json.dumps(self.pool)
        if command[:4] == ("gcloud", "compute", "regions", "describe"):
            return json.dumps({"quotas": [{"metric": "NVIDIA_L4_GPUS", "limit": 100, "usage": 39}]})
        if command[:4] == ("gcloud", "container", "images", "describe"):
            if "@" not in command[4] and not self.target_exists:
                raise subprocess.CalledProcessError(1, command)
            return json.dumps({"image_summary": {"digest": self.plan.image_digest}})
        if command[:4] == ("gcloud", "container", "images", "add-tag"):
            self.target_exists = True
            target_tag = command[5]
            target_repository = target_tag.rsplit(":", 1)[0]
            self.target_image_ref = target_repository + "@" + self.plan.image_digest
            return ""
        if command[:4] == ("helm", "-n", f"{self.plan.environment}-omi-monitoring", "status"):
            return json.dumps({"chart": {"metadata": {"name": "prometheus-adapter", "version": "4.12.0"}}})
        if command[:4] == ("helm", "-n", f"{self.plan.environment}-omi-monitoring", "history"):
            return json.dumps([{"revision": 7}])
        if command[:4] == ("helm", "-n", f"{self.plan.environment}-omi-monitoring", "get"):
            return "rules:\n  custom: []\n"
        if command[:4] == ("helm", "-n", self.plan.namespace, "history"):
            raise subprocess.CalledProcessError(1, command)
        if command[:4] == ("kubectl", "-n", self.plan.namespace, "get") and "deployment" in command:
            return json.dumps(
                {
                    "status": {
                        "readyReplicas": self.plan.warm_replicas,
                        "updatedReplicas": self.plan.warm_replicas,
                        "availableReplicas": self.plan.warm_replicas,
                    }
                }
            )
        if command[:4] == ("kubectl", "-n", self.plan.namespace, "get") and "pods" in command:
            return json.dumps({"items": [self._pod(i) for i in range(self.plan.warm_replicas)]})
        if command[:4] == ("kubectl", "-n", self.plan.namespace, "get") and "endpointslice" in command:
            return json.dumps(
                {"items": [{"endpoints": [{"conditions": {"ready": True}} for _ in range(self.plan.warm_replicas)]}]}
            )
        if command[:4] == ("kubectl", "-n", self.plan.namespace, "get") and "service" in command:
            return json.dumps({"status": {"loadBalancer": {"ingress": [{"ip": "10.0.0.7"}]}}})
        if command[:3] == ("kubectl", "-n", self.plan.namespace) and "exec" in command:
            if self.legacy_health:
                return json.dumps({"status": "healthy"})
            return json.dumps(
                {
                    "status": "healthy",
                    "ready": True,
                    "mode": "stream",
                    "model_identity": self.model_identity,
                    "components": {"rnnt": True, "vad": True, "diarizer": True},
                    "admission": {"capacity": self.plan.hard_stream_capacity},
                }
            )
        if command[:3] == ("kubectl", "get", "--raw"):
            if self.missing_metrics:
                return json.dumps({"items": []})
            pod = command[-1].split("/pods/", 1)[1].split("/", 1)[0] if "/pods/" in command[-1] else ""
            return json.dumps(
                {
                    "items": [
                        {
                            "describedObject": {"name": pod},
                            "value": "0",
                            "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
                        }
                    ]
                }
            )
        return ""

    def _pod(self, index):
        return {
            "metadata": {"name": f"parakeet-{index}"},
            "spec": {"nodeName": f"gpu-node-{index}", "containers": [{"image": self.target_image_ref}]},
            "status": {"conditions": [{"type": "Ready", "status": "True"}]},
        }


def test_first_install_waits_for_warm_fleet_and_exports_url(tmp_path, monkeypatch):
    plan = _plan()
    runner = _ReleaseRunner(plan)
    monkeypatch.setattr(deploy_module, "WARM_FLEET_ATTEMPTS", 1)
    monkeypatch.setattr(deploy_module, "METRIC_ATTEMPTS", 1)
    url = deploy_stream_fleet(
        plan,
        cluster="omi",
        region="us-central1",
        project="example",
        adapter_values_file=ROOT / "charts/monitoring/prometheus-adapter/prod_omi_prometheus_adapter.yaml",
        adapter_release="prod-omi-prometheus-adapter",
        qualification_evidence=_qualified_evidence(plan),
        source_sha="source-123",
        runner=runner,
        github_output=tmp_path / "output",
    )
    assert url == "http://10.0.0.7:8080"
    assert any(
        command[:4] == ("helm", "-n", plan.namespace, "upgrade") and "--install" in command for command in runner.calls
    )
    assert not any("uninstall" in command for command in runner.calls)


def test_legacy_healthy_only_probe_does_not_pass_stream_readiness():
    plan = _plan()
    runner = _ReleaseRunner(plan, legacy_health=True)
    with pytest.raises(DeploymentError, match="ready stream model"):
        _verify_warm_fleet_once(plan, runner)


def test_qualification_rejects_wrong_model_identity():
    plan = _plan()
    evidence = _qualified_evidence(plan)
    evidence["runtime_health"]["model_identity"]["decoder_family"] = "rnnt"
    with pytest.raises(DeploymentError, match="model identity"):
        validate_capacity_evidence(evidence, image_ref=plan.image_ref, required_capacity=plan.hard_stream_capacity)


def test_warm_pod_with_ready_rnnt_identity_does_not_pass_tdt_gate():
    plan = _plan()
    wrong_identity = {**EXPECTED_STREAM_MODEL_IDENTITY, "decoder_family": "rnnt", "model_loaded": True}
    runner = _ReleaseRunner(plan, model_identity=wrong_identity)
    with pytest.raises(DeploymentError, match="exact TDT identity"):
        _verify_warm_fleet_once(plan, runner)


def test_bad_qualification_fails_before_any_mutation():
    plan = _plan()
    runner = _ReleaseRunner(plan)
    evidence = _qualified_evidence(plan)
    evidence["image_ref"] = plan.image_repository + "@sha256:" + "c" * 64
    with pytest.raises(DeploymentError, match="exact deployment image"):
        deploy_stream_fleet(
            plan,
            cluster="omi",
            region="us-central1",
            project="example",
            adapter_values_file=Path("unused.yaml"),
            adapter_release="prod-omi-prometheus-adapter",
            qualification_evidence=evidence,
            source_sha="source-123",
            runner=runner,
        )
    assert runner.calls == []


def test_missing_metric_rolls_back_first_install_and_adapter(monkeypatch):
    plan = _plan()
    runner = _ReleaseRunner(plan, missing_metrics=True)
    monkeypatch.setattr(deploy_module, "METRIC_ATTEMPTS", 1)
    with pytest.raises(DeploymentError, match="metric"):
        deploy_stream_fleet(
            plan,
            cluster="omi",
            region="us-central1",
            project="example",
            adapter_values_file=ROOT / "charts/monitoring/prometheus-adapter/prod_omi_prometheus_adapter.yaml",
            adapter_release="prod-omi-prometheus-adapter",
            qualification_evidence=_qualified_evidence(plan),
            source_sha="source-123",
            runner=runner,
        )
    assert any("uninstall" in command for command in runner.calls)
    assert any("rollback" in command and "prod-omi-monitoring" in command for command in runner.calls)
