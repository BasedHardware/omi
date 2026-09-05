from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


CONTRACT = _load("jit_qa_receipt_contract", ROOT / "scripts" / "jit_qa_cloud_run_contract.py")
RECEIPT = _load("jit_qa_receipt", ROOT / "scripts" / "jit_qa_receipt.py")


def _resource(profile: str, name: str, image_name: str, revision: str, kind: str = "service") -> dict:
    literals, secrets = CONTRACT.resource_environment(profile)
    env = [{"name": key, "value": value} for key, value in literals.items()]
    env.extend(
        {
            "name": key,
            "valueSource": {"secretKeyRef": {"secret": ref.split(":", 1)[0], "version": ref.split(":", 1)[1]}},
        }
        for key, ref in secrets.items()
    )
    image = f"gcr.io/based-hardware-dev/{image_name}@sha256:{'a' * 64}"
    if kind == "service":
        spec = {
            "template": {
                "spec": {
                    "serviceAccountName": CONTRACT.RUNTIME_SERVICE_ACCOUNT,
                    "containers": [{"image": image, "env": env}],
                }
            }
        }
    else:
        spec = {
            "template": {
                "template": {
                    "spec": {
                        "serviceAccountName": CONTRACT.RUNTIME_SERVICE_ACCOUNT,
                        "containers": [{"image": image, "env": env}],
                    }
                }
            }
        }
    return {
        "metadata": {"name": name},
        "spec": spec,
        "status": {
            "latestReadyRevisionName": revision,
            "url": f"https://{name}.run.app",
            "traffic": [{"revisionName": revision, "percent": 100}],
        },
    }


def test_receipt_has_activation_shape_and_dependency_vector():
    receipt = RECEIPT.build_receipt(
        source_sha="a" * 40,
        python_resource=_resource("backend", "backend-jit-qa", "backend-jit-qa", "backend-jit-qa-00001"),
        desktop_resource=_resource(
            "desktop", "desktop-backend-jit-qa", "desktop-backend-jit-qa", "desktop-backend-jit-qa-00001"
        ),
        gateway_resource=_resource("gateway", "llm-gateway-jit-qa", "llm-gateway-jit-qa", "llm-gateway-jit-qa-00001"),
        python_url="https://backend-jit-qa.run.app",
        desktop_url="https://desktop-backend-jit-qa.run.app",
        gateway_url="https://llm-gateway-jit-qa.run.app",
        app_probe=True,
        gateway_probe=True,
    )
    assert receipt["schema_version"] == "omi.jit.qa.cloud.v1"
    assert receipt["status"] == "ready"
    assert receipt["reviewed"] is False
    assert receipt["dependency_vector"]["redis"] == "jit-qa-redis:basic-1GiB"
    assert receipt["full_source_sha"] == "a" * 40
    assert receipt["exact_python_url"] == "https://backend-jit-qa.run.app"
    assert receipt["python_image_digest"] == "sha256:" + "a" * 64
    assert receipt["gateway_revision"] == "llm-gateway-jit-qa-00001"
    assert receipt["gateway_image_digest"] == "sha256:" + "a" * 64
    assert receipt["firestore_database_id"] == "jit-qa"


def test_receipt_does_not_call_a_resource_ready_without_probes():
    with pytest.raises(ValueError):
        RECEIPT.build_receipt(
            source_sha="a" * 40,
            python_resource=_resource("backend", "backend-jit-qa", "backend-jit-qa", "backend-jit-qa-00001"),
            desktop_resource=_resource(
                "desktop", "desktop-backend-jit-qa", "desktop-backend-jit-qa", "desktop-backend-jit-qa-00001"
            ),
            gateway_resource=_resource(
                "gateway", "llm-gateway-jit-qa", "llm-gateway-jit-qa", "llm-gateway-jit-qa-00001"
            ),
            python_url="https://backend-jit-qa.run.app",
            desktop_url="https://desktop-backend-jit-qa.run.app",
            gateway_url="https://llm-gateway-jit-qa.run.app",
            app_probe=False,
            gateway_probe=True,
        )


def test_receipt_rejects_latest_ready_revision_without_full_traffic():
    python = _resource("backend", "backend-jit-qa", "backend-jit-qa", "backend-jit-qa-00001")
    python["status"]["traffic"] = [{"revisionName": "backend-jit-qa-00000", "percent": 100}]
    with pytest.raises(ValueError, match="100 percent serving revision"):
        RECEIPT.build_receipt(
            source_sha="a" * 40,
            python_resource=python,
            desktop_resource=_resource(
                "desktop", "desktop-backend-jit-qa", "desktop-backend-jit-qa", "desktop-backend-jit-qa-00001"
            ),
            gateway_resource=_resource(
                "gateway", "llm-gateway-jit-qa", "llm-gateway-jit-qa", "llm-gateway-jit-qa-00001"
            ),
            python_url="https://backend-jit-qa.run.app",
            desktop_url="https://desktop-backend-jit-qa.run.app",
            gateway_url="https://llm-gateway-jit-qa.run.app",
            app_probe=True,
            gateway_probe=True,
        )


def test_receipt_rejects_newer_created_revision_that_is_not_serving():
    gateway = _resource("gateway", "llm-gateway-jit-qa", "llm-gateway-jit-qa", "llm-gateway-jit-qa-00001")
    gateway["status"]["latestCreatedRevisionName"] = "llm-gateway-jit-qa-00002"
    with pytest.raises(ValueError, match="newer non-serving revision"):
        RECEIPT.build_receipt(
            source_sha="a" * 40,
            python_resource=_resource("backend", "backend-jit-qa", "backend-jit-qa", "backend-jit-qa-00001"),
            desktop_resource=_resource(
                "desktop", "desktop-backend-jit-qa", "desktop-backend-jit-qa", "desktop-backend-jit-qa-00001"
            ),
            gateway_resource=gateway,
            python_url="https://backend-jit-qa.run.app",
            desktop_url="https://desktop-backend-jit-qa.run.app",
            gateway_url="https://llm-gateway-jit-qa.run.app",
            app_probe=True,
            gateway_probe=True,
        )


def test_receipt_round_trips_activation_fixture_when_consumer_tree_is_present():
    fixture_path = ROOT.parent / "desktop" / "macos" / "tests" / "fixtures" / "jit-qa" / "cloud-receipt-v1.json"
    if not fixture_path.exists():
        pytest.skip("activation receipt fixture lands with the consumer change")
    expected = json.loads(fixture_path.read_text(encoding="utf-8"))

    def resource(profile: str, name: str, image_digest: str, revision: str) -> dict:
        result = _resource(profile, name, name, revision)
        result["spec"]["template"]["spec"]["containers"][0][
            "image"
        ] = f"gcr.io/based-hardware-dev/{name}@{image_digest}"
        return result

    gateway_revision = expected.get("gateway_revision", "llm-gateway-jit-qa-00001")
    gateway_digest = expected.get("gateway_image_digest", "sha256:" + "a" * 64)
    actual = RECEIPT.build_receipt(
        source_sha=expected["full_source_sha"],
        python_resource=resource(
            "backend", expected["python_service"], expected["python_image_digest"], expected["python_revision"]
        ),
        desktop_resource=resource(
            "desktop", expected["desktop_service"], expected["desktop_image_digest"], expected["desktop_revision"]
        ),
        gateway_resource=resource("gateway", expected["gateway_service"], gateway_digest, gateway_revision),
        python_url=expected["exact_python_url"],
        desktop_url=expected["exact_desktop_url"],
        gateway_url=expected["exact_gateway_url"],
        app_probe=True,
        gateway_probe=True,
    )
    expected = {**expected, "reviewed": False}
    for key, value in expected.items():
        assert actual[key] == value
