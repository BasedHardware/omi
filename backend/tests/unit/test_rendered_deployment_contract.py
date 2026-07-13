"""Behavioral coverage for the offline rendered GKE deployment contracts."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import runpy
import shutil
from types import SimpleNamespace

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "validate_rendered_deployment_contract.py"


@pytest.fixture
def contracts() -> SimpleNamespace:
    """Load the standalone validator without importing or mutating sys.modules."""
    return SimpleNamespace(**runpy.run_path(str(SCRIPT)))


def _deployment(contracts: SimpleNamespace, *, image: str | None = None) -> dict:
    contract = contracts.CONTRACTS[0]
    environment = "dev"
    return {
        "apiVersion": "apps/v1",
        "kind": "Deployment",
        "metadata": {"name": contracts.release_name(contract, environment)},
        "spec": {
            "template": {
                "spec": {
                    "serviceAccountName": contracts.release_name(contract, environment),
                    "containers": [
                        {
                            "name": contract.service,
                            "image": image or contracts.expected_image(contract, environment),
                            "ports": [{"name": "http", "containerPort": 8080}],
                            "livenessProbe": {"httpGet": {"path": "/health"}},
                            "readinessProbe": {"httpGet": {"path": "/ready"}},
                            "startupProbe": {"httpGet": {"path": "/health"}},
                            "env": [
                                {"name": "OMI_ENV_STAGE", "value": "dev"},
                                {"name": "GOOGLE_CLOUD_PROJECT", "value": "based-hardware-dev"},
                                {
                                    "name": "OPENAI_API_KEY",
                                    "valueFrom": {
                                        "secretKeyRef": {
                                            "name": "dev-omi-backend-secrets",
                                            "key": "OPENAI_API_KEY",
                                        }
                                    },
                                },
                            ],
                        }
                    ],
                }
            }
        },
    }


def test_valid_rendered_deployment_satisfies_contract(contracts: SimpleNamespace):
    assert contracts.validate_rendered_deployment(contracts.CONTRACTS[0], "dev", [_deployment(contracts)]) == []


def test_stale_or_fallback_image_is_rejected_at_rendered_outcome(contracts: SimpleNamespace):
    failures = contracts.validate_rendered_deployment(
        contracts.CONTRACTS[0], "dev", [_deployment(contracts, image="gcr.io/based-hardware-dev/backend:latest")]
    )

    assert any("immutable image must be" in failure for failure in failures)
    assert any("must not be empty or use the latest tag" in failure for failure in failures)


def test_wrong_runtime_identity_and_secret_reference_are_rejected(contracts: SimpleNamespace):
    deployment = deepcopy(_deployment(contracts))
    container = deployment["spec"]["template"]["spec"]["containers"][0]
    deployment["spec"]["template"]["spec"]["serviceAccountName"] = "default"
    container["env"][1]["value"] = "based-hardware"
    container["env"][2]["valueFrom"]["secretKeyRef"]["name"] = "prod-omi-backend-secrets"

    failures = contracts.validate_rendered_deployment(contracts.CONTRACTS[0], "dev", [deployment])

    assert any("serviceAccountName must be" in failure for failure in failures)
    assert any("GOOGLE_CLOUD_PROJECT must be" in failure for failure in failures)
    assert any("secretKeyRef" in failure and "dev-omi-backend-secrets" in failure for failure in failures)


def test_render_command_uses_the_deploy_immutable_tag_override(monkeypatch, contracts: SimpleNamespace):
    captured: list[list[str]] = []

    class Result:
        returncode = 0
        stdout = ""
        stderr = ""

    def fake_run(command, **_kwargs):
        captured.append(command)
        return Result()

    monkeypatch.setattr(contracts.subprocess, "run", fake_run)

    assert contracts.render_chart(contracts.CONTRACTS[0], "dev", "helm") == []
    assert contracts.CONTRACT_IMAGE_TAG == "0123456"
    assert captured[0][-2:] == ["--set-string", f"image.tag={contracts.CONTRACT_IMAGE_TAG}"]


def test_all_owned_gke_deploy_paths_preserve_image_tags_as_strings(contracts: SimpleNamespace):
    assert contracts.validate_image_tag_deployment_paths() == []


def test_deploy_path_guard_rejects_an_untyped_numeric_image_tag(monkeypatch, tmp_path, contracts: SimpleNamespace):
    fixture = tmp_path / "deploy.sh"
    fixture.write_text('helm upgrade --set "image.tag=0123456"\n', encoding="utf-8")
    globals_ = contracts.validate_image_tag_deployment_paths.__globals__
    monkeypatch.setitem(globals_, "ROOT", tmp_path)
    monkeypatch.setitem(globals_, "IMAGE_TAG_DEPLOYMENT_PATHS", ("deploy.sh",))

    assert contracts.validate_image_tag_deployment_paths() == [
        "deploy.sh: image.tag must use --set-string, not --set",
        "deploy.sh: missing --set-string image.tag override",
    ]


def test_repository_charts_render_the_full_contract_when_helm_is_available(contracts: SimpleNamespace):
    helm = shutil.which("helm")
    assert helm is not None, "helm must be installed for the rendered deployment contract"

    assert contracts.validate_all_contracts(contracts.render_chart, helm) == []


def test_first_party_charts_reject_missing_image_tag_when_helm_is_available(contracts: SimpleNamespace):
    helm = shutil.which("helm")
    assert helm is not None, "helm must be installed for the rendered deployment contract"

    for environment in contracts.ENVIRONMENTS:
        for contract in contracts.CONTRACTS:
            result = contracts.subprocess.run(
                [
                    helm,
                    "template",
                    contracts.release_name(contract, environment),
                    str(contracts.chart_dir(contract)),
                    "-f",
                    str(contracts.values_file(contract, environment)),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            assert result.returncode != 0, f"{environment}/{contract.service} accepted an untagged image"
            assert "image.tag is required" in result.stderr
