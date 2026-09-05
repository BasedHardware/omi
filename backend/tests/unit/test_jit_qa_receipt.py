from __future__ import annotations

import importlib.util
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
        "status": {"latestReadyRevisionName": revision, "url": f"https://{name}.run.app"},
    }


def test_receipt_has_activation_shape_and_dependency_vector():
    receipt = RECEIPT.build_receipt(
        source_sha="a" * 40,
        python_resource=_resource("backend", "backend-jit-qa", "backend-jit-qa", "backend-jit-qa-00001"),
        desktop_resource=_resource(
            "desktop", "desktop-backend-jit-qa", "desktop-backend-jit-qa", "desktop-backend-jit-qa-00001"
        ),
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


def test_receipt_does_not_call_a_resource_ready_without_probes():
    with pytest.raises(ValueError):
        RECEIPT.build_receipt(
            source_sha="a" * 40,
            python_resource=_resource("backend", "backend-jit-qa", "backend-jit-qa", "backend-jit-qa-00001"),
            desktop_resource=_resource(
                "desktop", "desktop-backend-jit-qa", "desktop-backend-jit-qa", "desktop-backend-jit-qa-00001"
            ),
            python_url="https://backend-jit-qa.run.app",
            desktop_url="https://desktop-backend-jit-qa.run.app",
            gateway_url="https://llm-gateway-jit-qa.run.app",
            app_probe=False,
            gateway_probe=True,
        )
