"""Regression coverage for the digest-pinned Pusher recovery profile."""

from __future__ import annotations

import copy
from pathlib import Path
import runpy
import subprocess
from types import SimpleNamespace

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "verify_pusher_chart_only_recovery.py"
DIGEST = "sha256:" + "a" * 64


@pytest.fixture
def recovery() -> SimpleNamespace:
    return SimpleNamespace(**runpy.run_path(str(SCRIPT)))


def deployment(image: str, redis_source: dict | None = None) -> dict:
    return {
        "apiVersion": "apps/v1",
        "kind": "Deployment",
        "metadata": {"name": "prod-omi-pusher", "namespace": "prod-omi-backend", "generation": 2},
        "spec": {
            "template": {
                "spec": {
                    "containers": [
                        {
                            "name": "pusher",
                            "image": image,
                            "env": [
                                {
                                    "name": "REDIS_DB_HOST",
                                    "valueFrom": redis_source
                                    or {
                                        "configMapKeyRef": {"name": "prod-omi-backend-config", "key": "REDIS_DB_HOST"},
                                        "secretKeyRef": None,
                                    },
                                },
                                {"name": "KEEP", "value": "unchanged"},
                            ],
                            "resources": {"requests": {"cpu": "1"}},
                            "readinessProbe": {"httpGet": {"path": "/health"}},
                        }
                    ]
                }
            }
        },
        "status": {"observedGeneration": 2, "readyReplicas": 7},
    }


def test_exact_digest_identity_rejects_tag_digest_ambiguity_and_repository_mutation(recovery: SimpleNamespace):
    assert recovery.validate_identity("gcr.io/project/pusher", DIGEST, "gcr.io/project/pusher") == []
    assert recovery.validate_identity("gcr.io/project/pusher:tag", DIGEST)
    assert recovery.validate_identity("gcr.io/other/pusher", DIGEST, "gcr.io/project/pusher")
    assert recovery.validate_identity("gcr.io/project/pusher", "sha256:abc")


def test_historical_named_env_strategic_merge_removes_secret_source(recovery: SimpleNamespace):
    live = {
        "name": "REDIS_DB_HOST",
        "valueFrom": {"secretKeyRef": {"name": "prod-omi-backend-secrets", "key": "REDIS_DB_HOST"}},
    }
    desired = {
        "name": "REDIS_DB_HOST",
        "valueFrom": {
            "configMapKeyRef": {"name": "prod-omi-backend-config", "key": "REDIS_DB_HOST"},
            "secretKeyRef": None,
        },
    }
    merged = recovery.replace_env_by_name([live], desired)[0]
    assert merged == {
        "name": "REDIS_DB_HOST",
        "valueFrom": {"configMapKeyRef": {"name": "prod-omi-backend-config", "key": "REDIS_DB_HOST"}},
    }


def test_recovery_profile_allows_only_exact_image_and_redis_transition(recovery: SimpleNamespace):
    live = deployment(
        "gcr.io/project/pusher:2ae7f78", {"secretKeyRef": {"name": "prod-omi-backend-secrets", "key": "REDIS_DB_HOST"}}
    )
    rendered = deployment(f"gcr.io/project/pusher@{DIGEST}")
    assert recovery.allowed_recovery_drift(live, rendered) == []
    changed = copy.deepcopy(rendered)
    changed["spec"]["template"]["spec"]["containers"][0]["resources"]["requests"]["cpu"] = "2"
    assert recovery.allowed_recovery_drift(live, changed) == [
        "recovery profile would change Deployment fields outside the exact image and REDIS_DB_HOST transition"
    ]


def test_recovery_profile_ignores_api_server_deployment_defaults(recovery: SimpleNamespace):
    """Live Deployments include controller-populated fields absent from helm template output."""
    live = deployment(
        "gcr.io/project/pusher:2ae7f78", {"secretKeyRef": {"name": "prod-omi-backend-secrets", "key": "REDIS_DB_HOST"}}
    )
    # Simulate API-server/controller defaults present in kubectl get -o json but
    # absent from helm template output.
    live["metadata"]["annotations"] = {"deployment.kubernetes.io/revision": "3"}
    live["spec"]["revisionHistoryLimit"] = 10
    live["spec"]["template"]["spec"]["restartPolicy"] = "Always"
    live["spec"]["template"]["spec"]["dnsPolicy"] = "ClusterFirst"
    live["spec"]["template"]["spec"]["schedulerName"] = "default-scheduler"
    live["spec"]["template"]["spec"]["containers"][0]["terminationMessagePath"] = "/dev/termination-log"
    live["spec"]["template"]["spec"]["containers"][0]["terminationMessagePolicy"] = "File"

    rendered = deployment(f"gcr.io/project/pusher@{DIGEST}")
    assert recovery.allowed_recovery_drift(live, rendered) == []


def test_recovery_profile_ignores_helm_annotations_and_service_defaults(recovery: SimpleNamespace):
    """Helm-managed annotations and cluster-added Service fields are absent from helm template."""
    live = deployment(
        "gcr.io/project/pusher:2ae7f78", {"secretKeyRef": {"name": "prod-omi-backend-secrets", "key": "REDIS_DB_HOST"}}
    )
    live["metadata"]["annotations"] = {
        "deployment.kubernetes.io/revision": "3",
        "meta.helm.sh/release-name": "prod-omi-pusher",
        "meta.helm.sh/release-namespace": "prod-omi-backend",
    }
    rendered = deployment(f"gcr.io/project/pusher@{DIGEST}")
    assert recovery.allowed_recovery_drift(live, rendered) == []

    # Service drift comparison should also ignore cluster-added defaults.
    live_svc = {
        "kind": "Service",
        "metadata": {
            "name": "prod-omi-pusher",
            "annotations": {"meta.helm.sh/release-name": "prod-omi-pusher"},
        },
        "spec": {
            "clusterIP": "10.0.0.1",
            "clusterIPs": ["10.0.0.1"],
            "internalTrafficPolicy": "Cluster",
            "sessionAffinityConfig": {},
        },
    }
    rendered_svc = {"kind": "Service", "metadata": {"name": "prod-omi-pusher"}, "spec": {}}
    assert recovery.validate_chart_owned_resource_drift(live_svc, rendered_svc, "Service") == []


def test_redis_validation_rejects_secret_and_configmap_errors(recovery: SimpleNamespace):
    assert recovery.validate_redis_source(deployment("x").copy(), "prod-omi-backend-config") == []
    secret = deployment("x", {"secretKeyRef": {"name": "prod-omi-backend-secrets", "key": "REDIS_DB_HOST"}})
    assert recovery.validate_redis_source(secret, "prod-omi-backend-config") == [
        "REDIS_DB_HOST must use the selected backend ConfigMap key"
    ]


def test_redis_validation_accepts_post_repair_env_without_secret_key(recovery: SimpleNamespace):
    """After Helm applies secretKeyRef: null, Kubernetes stores the env without the key at all."""
    repaired = deployment("x", {"configMapKeyRef": {"name": "prod-omi-backend-config", "key": "REDIS_DB_HOST"}})
    assert recovery.validate_redis_source(repaired, "prod-omi-backend-config") == []


def test_target_and_readiness_guards_fail_closed(recovery: SimpleNamespace):
    live = deployment("x")
    live["status"]["observedGeneration"] = 1
    assert recovery.is_concurrent_rollout(live)
    assert recovery.ready_replicas(live) == 7
    assert recovery.expected_targets("prod") == (
        "prod-omi-backend",
        "prod-omi-pusher",
        "prod-omi-pusher",
        "prod-omi-backend-config",
    )


@pytest.mark.parametrize("kind", ["Service", "HorizontalPodAutoscaler", "PodDisruptionBudget"])
def test_chart_owned_resources_reject_unexpected_drift(recovery: SimpleNamespace, kind: str):
    live = {"kind": kind, "metadata": {"name": "prod-omi-pusher"}, "spec": {"guard": "unchanged"}}
    rendered = copy.deepcopy(live)
    assert recovery.validate_chart_owned_resource_drift(live, rendered, kind) == []
    rendered["spec"]["guard"] = "changed"
    assert recovery.validate_chart_owned_resource_drift(live, rendered, kind) == [
        f"recovery profile would change {kind} outside the allowlist"
    ]


def test_service_recovery_profile_ignores_helm_and_api_defaults_but_not_real_drift(recovery: SimpleNamespace):
    rendered = {
        "apiVersion": "v1",
        "kind": "Service",
        "metadata": {
            "name": "prod-omi-pusher",
            "annotations": {"cloud.google.com/neg": '{"ingress": true}'},
        },
        "spec": {"type": "ClusterIP", "ports": [{"name": "http", "port": 8080}], "selector": {"app": "pusher"}},
    }
    live = copy.deepcopy(rendered)
    live["metadata"]["annotations"].update(
        {"meta.helm.sh/release-name": "prod-omi-pusher", "meta.helm.sh/release-namespace": "prod-omi-backend"}
    )
    live["spec"].update({"clusterIP": "10.0.0.7", "internalTrafficPolicy": "Cluster", "sessionAffinity": "None"})

    assert recovery.validate_chart_owned_resource_drift(live, rendered, "Service") == []

    annotation_drift = copy.deepcopy(live)
    annotation_drift["metadata"]["annotations"]["cloud.google.com/neg"] = '{"ingress": false}'
    assert recovery.validate_chart_owned_resource_drift(annotation_drift, rendered, "Service") == [
        "recovery profile would change Service outside the allowlist"
    ]

    policy_drift = copy.deepcopy(live)
    policy_drift["spec"]["internalTrafficPolicy"] = "Local"
    assert recovery.validate_chart_owned_resource_drift(policy_drift, rendered, "Service") == [
        "recovery profile would change Service outside the allowlist"
    ]


def test_serving_digest_is_read_only_and_rejects_mixed_or_missing_status(recovery: SimpleNamespace):
    pods = {
        "items": [
            {
                "status": {
                    "containerStatuses": [
                        {"name": "pusher", "ready": True, "imageID": f"docker://gcr.io/project/pusher@{DIGEST}"}
                    ]
                }
            }
        ]
    }
    assert recovery.serving_pusher_digests(pods) == {DIGEST}
    mixed = copy.deepcopy(pods)
    mixed["items"].append(
        {
            "status": {
                "containerStatuses": [
                    {"name": "pusher", "ready": True, "imageID": "docker://gcr.io/project/pusher@sha256:" + "b" * 64}
                ]
            }
        }
    )
    assert recovery.serving_pusher_digests(mixed) == {DIGEST, "sha256:" + "b" * 64}
    with pytest.raises(ValueError, match="no immutable image digest"):
        recovery.serving_pusher_digests(
            {"items": [{"status": {"containerStatuses": [{"name": "pusher", "ready": True}]}}]}
        )
    assert recovery.serving_pusher_images(pods) == {f"gcr.io/project/pusher@{DIGEST}"}


def test_chart_only_workflow_skips_build_push_and_normal_paths_stay_available():
    workflow = (SCRIPT.parents[2] / ".github/workflows/gcp_backend_pusher.yml").read_text(encoding="utf-8")
    assert "deployment_mode:" in workflow
    assert "if: env.CHART_ONLY != 'true'" in workflow
    assert "Build and Push Docker image" in workflow
    assert "if: env.SERVICE == 'pusher' && env.CHART_ONLY != 'true'" in workflow
    assert "if: env.SERVICE == 'pusher' && env.CHART_ONLY == 'true'" in workflow
    assert "--expected-evidence pusher-recovery-evidence.json" in workflow


def test_chart_renders_exact_digest_and_rejects_ambiguous_or_mutated_repository():
    chart = SCRIPT.parents[1] / "charts" / "pusher"
    values = chart / "prod_omi_pusher_values.yaml"
    base = ["helm", "template", "prod-omi-pusher", str(chart), "-f", str(values)]
    valid = subprocess.run(
        [*base, "--set-string", "image.tag=", "--set-string", f"image.digest={DIGEST}"], capture_output=True, text=True
    )
    assert valid.returncode == 0, valid.stderr
    assert f"gcr.io/based-hardware/pusher@{DIGEST}" in valid.stdout
    for arguments in (
        ["--set-string", "image.tag=tag", "--set-string", f"image.digest={DIGEST}"],
        ["--set-string", "image.tag=", "--set-string", "image.digest=sha256:bad"],
        ["--set-string", "image.repository=gcr.io/based-hardware/pusher:tag", "--set-string", f"image.digest={DIGEST}"],
    ):
        result = subprocess.run([*base, *arguments], capture_output=True, text=True)
        assert result.returncode != 0
