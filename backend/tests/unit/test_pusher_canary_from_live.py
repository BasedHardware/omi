"""SCA-4763: the isolated Pusher canary must copy the live workload, not render it.

Release selected the live-template-derived canary after the protected canary
verification refused with `effective_environment_differs` (run 46139487564): a
canary rendered from the dispatching main carried ConfigMap keys and chart env
an image-only promote never applies. These tests pin the two properties that
make the rerun meaningful:

* the derived Deployment differs from the live one only in image, canary names
  and the redirected ConfigMap references, so every parity class is `equal`;
* the copied ConfigMap has exactly the live fingerprint.
"""

from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "backend" / "scripts"))
sys.path.insert(0, str(ROOT / ".github" / "scripts"))

import pusher_canary_from_live as derive  # noqa: E402
import pusher_canary_inverse as inverse  # noqa: E402
from pusher_release_receipt import config_fingerprint  # noqa: E402

LIVE_NAME = "prod-omi-pusher"
CANARY_NAME = "prod-omi-pusher-canary-46139487564"
LIVE_MAP = "prod-omi-backend-config"
CANARY_MAP = "prod-omi-backend-config-canary-46139487564"
BASELINE_IMAGE = "gcr.io/based-hardware/pusher@sha256:f26e8757759fe6907a9ef0e4c31d0a08a8ed527d777db5f472b33bffcff6d925"
CANDIDATE_IMAGE = "gcr.io/based-hardware/pusher@sha256:5770eeb94abe168c27af9792658a064362f1e88fa4329efface9aa86fd956bc5"


def live_config_map() -> dict:
    return {
        "apiVersion": "v1",
        "kind": "ConfigMap",
        "metadata": {
            "name": LIVE_MAP,
            "namespace": "prod-omi-backend",
            "uid": "config-uid",
            "resourceVersion": "1795797691642431023",
            "annotations": {"kubectl.kubernetes.io/last-applied-configuration": "{}"},
        },
        "data": {
            "BATCH_VENDOR_ROUTE_TABLE": '{"schema_version":1}',
            "REDIS_DB_HOST": "redis.example",
            "MEMORY_ENABLED": "true",
        },
    }


def live_deployment() -> dict:
    return {
        "apiVersion": "apps/v1",
        "kind": "Deployment",
        "metadata": {
            "name": LIVE_NAME,
            "namespace": "prod-omi-backend",
            "uid": "deployment-uid",
            "resourceVersion": "42",
            "generation": 3358,
            "labels": {
                "app.kubernetes.io/instance": LIVE_NAME,
                "app.kubernetes.io/managed-by": "Helm",
                "app.kubernetes.io/name": "pusher",
                "app.kubernetes.io/version": "1.16.0",
                "helm.sh/chart": "pusher-0.1.0",
            },
            "annotations": {
                "deployment.kubernetes.io/revision": "812",
                "meta.helm.sh/release-name": LIVE_NAME,
            },
        },
        "spec": {
            "replicas": 18,
            "selector": {"matchLabels": {"app.kubernetes.io/name": "pusher", "app.kubernetes.io/instance": LIVE_NAME}},
            "template": {
                "metadata": {
                    "labels": {
                        "app.kubernetes.io/instance": LIVE_NAME,
                        "app.kubernetes.io/managed-by": "Helm",
                        "app.kubernetes.io/name": "pusher",
                        "app.kubernetes.io/version": "1.16.0",
                        "helm.sh/chart": "pusher-0.1.0",
                        "service_name": "pusher",
                    },
                    "annotations": {"kubectl.kubernetes.io/restartedAt": "2026-11-18T10:09:00Z"},
                },
                "spec": {
                    "serviceAccountName": LIVE_NAME,
                    "terminationGracePeriodSeconds": 300,
                    "containers": [
                        {
                            "name": "pusher",
                            "image": BASELINE_IMAGE,
                            "imagePullPolicy": "IfNotPresent",
                            "envFrom": [{"configMapRef": {"name": LIVE_MAP}}],
                            "env": [
                                {"name": "MEMORY_ENABLED", "value": "true"},
                                {
                                    "name": "REDIS_DB_HOST",
                                    "valueFrom": {"configMapKeyRef": {"name": LIVE_MAP, "key": "REDIS_DB_HOST"}},
                                },
                                {
                                    "name": "SOME_SECRET",
                                    "valueFrom": {"secretKeyRef": {"name": "prod-omi-backend-secrets", "key": "k"}},
                                },
                            ],
                            "ports": [{"name": "http", "containerPort": 8080, "protocol": "TCP"}],
                            "resources": {"requests": {"cpu": "500m", "memory": "2Gi"}},
                        }
                    ],
                    "volumes": [
                        {"name": "route-table", "configMap": {"name": LIVE_MAP}},
                        {
                            "name": "projected",
                            "projected": {"sources": [{"configMap": {"name": LIVE_MAP}}]},
                        },
                    ],
                },
            },
        },
        "status": {"replicas": 18, "readyReplicas": 18, "observedGeneration": 3358},
    }


def live_service() -> dict:
    return {
        "apiVersion": "v1",
        "kind": "Service",
        "metadata": {
            "name": LIVE_NAME,
            "namespace": "prod-omi-backend",
            "uid": "service-uid",
            "annotations": {
                "cloud.google.com/neg": '{"ingress": true}',
                "cloud.google.com/backend-config": '{"default": "x"}',
            },
        },
        "spec": {
            "type": "ClusterIP",
            "clusterIP": "10.0.0.9",
            "selector": {"app.kubernetes.io/name": "pusher", "app.kubernetes.io/instance": LIVE_NAME},
            "ports": [{"name": "http", "port": 8080, "protocol": "TCP", "targetPort": "http"}],
        },
    }


def derived() -> tuple[dict, dict]:
    deployment = derive.derive_deployment(
        live_deployment(),
        name=CANARY_NAME,
        namespace="prod-omi-backend",
        image=CANDIDATE_IMAGE,
        canary_config_map=CANARY_MAP,
        live_config_map=LIVE_MAP,
    )
    return deployment, derive.derive_config_map(live_config_map(), name=CANARY_MAP, namespace="prod-omi-backend")


def test_only_the_candidate_image_and_canary_identity_change() -> None:
    deployment, _ = derived()
    live = live_deployment()
    live_pusher = next(item for item in live["spec"]["template"]["spec"]["containers"] if item["name"] == "pusher")
    canary_pusher = next(
        item for item in deployment["spec"]["template"]["spec"]["containers"] if item["name"] == "pusher"
    )

    assert canary_pusher["image"] == CANDIDATE_IMAGE
    assert live_pusher["image"] == BASELINE_IMAGE
    assert deployment["metadata"]["name"] == CANARY_NAME
    assert deployment["metadata"]["namespace"] == "prod-omi-backend"
    assert deployment["metadata"]["annotations"] == {}
    assert "status" not in deployment
    assert "uid" not in deployment["metadata"]
    assert "resourceVersion" not in deployment["metadata"]
    assert deployment["spec"]["replicas"] == 1
    assert deployment["spec"]["selector"]["matchLabels"]["app.kubernetes.io/instance"] == CANARY_NAME
    assert deployment["spec"]["template"]["metadata"]["labels"]["app.kubernetes.io/instance"] == CANARY_NAME
    # Everything the live template carried is still there.
    assert deployment["spec"]["template"]["spec"]["serviceAccountName"] == LIVE_NAME
    assert deployment["spec"]["template"]["spec"]["terminationGracePeriodSeconds"] == 300
    assert live["spec"]["replicas"] == 18 and live["status"]["readyReplicas"] == 18


def test_every_config_reference_points_at_the_isolated_copy() -> None:
    deployment, _ = derived()
    spec = deployment["spec"]["template"]["spec"]
    pusher = next(item for item in spec["containers"] if item["name"] == "pusher")

    assert pusher["envFrom"] == [{"configMapRef": {"name": CANARY_MAP}}]
    assert pusher["env"][1]["valueFrom"]["configMapKeyRef"]["name"] == CANARY_MAP
    assert pusher["env"][2]["valueFrom"]["secretKeyRef"]["name"] == "prod-omi-backend-secrets"
    assert spec["volumes"][0]["configMap"]["name"] == CANARY_MAP
    assert spec["volumes"][1]["projected"]["sources"][0]["configMap"]["name"] == CANARY_MAP


def test_copied_config_map_keeps_the_live_fingerprint() -> None:
    _, config_map = derived()
    live = live_config_map()

    assert config_map["data"] == live["data"]
    assert config_fingerprint(config_map, expected_name=CANARY_MAP) == config_fingerprint(live, expected_name=LIVE_MAP)


def test_canary_service_selects_only_the_canary_and_carries_no_ingress_identity() -> None:
    service = derive.derive_service(live_service(), name=CANARY_NAME, namespace="prod-omi-backend")

    assert service["spec"]["selector"] == {
        "app.kubernetes.io/name": "pusher",
        "app.kubernetes.io/instance": CANARY_NAME,
    }
    assert service["spec"]["ports"] == live_service()["spec"]["ports"]
    assert "annotations" not in service["metadata"]
    assert "clusterIP" not in service["spec"]


def test_template_parity_between_the_derived_canary_and_live_is_equal_in_every_class() -> None:
    deployment, _ = derived()

    parity = inverse.template_parity(
        deployment,
        live_deployment(),
        canary_name=CANARY_NAME,
        live_name=LIVE_NAME,
        canary_config_map=CANARY_MAP,
        live_config_map=LIVE_MAP,
    )

    assert parity["classes"], "parity produced no classes"
    assert {key: value for key, value in parity["classes"].items() if value != "equal"} == {}


def test_derivation_refuses_a_template_without_a_runtime_config_reference() -> None:
    live = live_deployment()
    spec = live["spec"]["template"]["spec"]
    for container in spec["containers"]:
        container["envFrom"] = []
        container["env"] = [entry for entry in container["env"] if "valueFrom" not in entry]
    spec["volumes"] = []

    with pytest.raises(derive.DeriveError, match="references no runtime ConfigMap"):
        derive.derive_deployment(
            live,
            name=CANARY_NAME,
            namespace="prod-omi-backend",
            image=CANDIDATE_IMAGE,
            canary_config_map=CANARY_MAP,
            live_config_map=LIVE_MAP,
        )


def test_derivation_refuses_a_candidate_equal_to_the_live_image() -> None:
    with pytest.raises(derive.DeriveError, match="candidate image equals the live image"):
        derive.derive_deployment(
            copy.deepcopy(live_deployment()),
            name=CANARY_NAME,
            namespace="prod-omi-backend",
            image=BASELINE_IMAGE,
            canary_config_map=CANARY_MAP,
            live_config_map=LIVE_MAP,
        )
