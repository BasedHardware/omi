"""Behavioral coverage for the offline rendered GKE deployment contracts."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import runpy
import shutil
import subprocess
import sys
from types import SimpleNamespace
from typing import Any

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "validate_rendered_deployment_contract.py"


@pytest.fixture(scope="module")
def contracts() -> SimpleNamespace:
    """Load the standalone validator without importing or mutating sys.modules."""
    return SimpleNamespace(**runpy.run_path(str(SCRIPT)))


@pytest.fixture(scope="module")
def rendered_pusher_deployments(contracts: SimpleNamespace) -> tuple[SimpleNamespace, dict[str, dict]]:
    """Render the two Pusher charts once, outside the fast-test call phase."""
    helm = shutil.which("helm")
    assert helm is not None, "helm must be installed for the rendered deployment contract"
    contract = next(contract for contract in contracts.CONTRACTS if contract.service == "pusher")
    deployments = {}
    for environment in contracts.ENVIRONMENTS:
        documents = contracts.render_chart(contract, environment, helm)
        deployment = contracts.deployment_for(documents, contracts.release_name(contract, environment))
        assert deployment is not None
        deployments[environment] = deployment
    return contract, deployments


@pytest.fixture(scope="module")
def untagged_chart_results(contracts: SimpleNamespace) -> list[tuple[str, str, Any]]:
    """Run the intentionally broad Helm rejection matrix outside the call phase."""
    helm = shutil.which("helm")
    assert helm is not None, "helm must be installed for the rendered deployment contract"
    results = []
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
            results.append((environment, contract.service, result))
    return results


def _deployment(contracts: SimpleNamespace, *, image: str | None = None, environment: str = "dev") -> dict:
    contract = contracts.CONTRACTS[0]
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
                                {"name": "OMI_ENV_STAGE", "value": environment},
                                {
                                    "name": "GOOGLE_CLOUD_PROJECT",
                                    "value": contracts.ENVIRONMENTS[environment]["project"],
                                },
                                {
                                    "name": "OPENAI_API_KEY",
                                    "valueFrom": {
                                        "secretKeyRef": {
                                            "name": f"{environment}-omi-backend-secrets",
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


@pytest.fixture(scope="module")
def rendered_gateway_deployment(contracts: SimpleNamespace):
    helm = shutil.which("helm")
    assert helm is not None, "helm must be installed for the rendered deployment contract"
    contract = next(item for item in contracts.CONTRACTS if item.service == "llm-gateway")
    return contract, contracts.render_chart(contract, "dev", helm)


def test_gateway_rotation_keys_are_optional_and_scoped(contracts, rendered_gateway_deployment):
    contract, rendered = rendered_gateway_deployment
    assert contracts.validate_rendered_deployment(contract, "dev", rendered) == []
    mutated = deepcopy(rendered)
    deployment = contracts.deployment_for(mutated, contracts.release_name(contract, "dev"))
    env = deployment["spec"]["template"]["spec"]["containers"][0]["env"]
    entry = next(entry for entry in env if entry["name"] == "LLM_GATEWAY_IDEMPOTENCY_SECONDARY_ENCRYPTION_SECRET")
    entry["valueFrom"]["secretKeyRef"]["name"] = "dev-omi-backend-secrets"
    errors = contracts.validate_rendered_deployment(contract, "dev", mutated)
    assert any("invalid or missing optional scoped secretKeyRef" in error for error in errors)


def test_stale_or_fallback_image_is_rejected_at_rendered_outcome(contracts: SimpleNamespace):
    failures = contracts.validate_rendered_deployment(
        contracts.CONTRACTS[0], "dev", [_deployment(contracts, image="gcr.io/based-hardware-dev/backend:latest")]
    )

    assert any("immutable image must match" in failure for failure in failures)
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
    assert any("secretKeyRef" in failure and "the shared backend secret" in failure for failure in failures)


def test_failure_diagnostics_omit_rendered_values(monkeypatch, capsys, contracts: SimpleNamespace):
    deployment = _deployment(contracts, image="synthetic-image-secret")
    pod = deployment["spec"]["template"]["spec"]
    pod["serviceAccountName"] = "synthetic-account-secret"
    env = pod["containers"][0]["env"]
    env[1]["value"] = "synthetic-env-secret"
    env[2]["valueFrom"]["secretKeyRef"]["name"] = "synthetic-reference-secret"
    env.append({"name": "synthetic-name-secret", "valueFrom": {"secretKeyRef": {"key": "synthetic-key-secret"}}})
    namespace = contracts.main.__globals__

    def fake_render(_contract, environment, _helm):
        if environment == "prod":
            raise ValueError("synthetic-render-exception-secret")
        return [deployment]

    monkeypatch.setitem(namespace, "render_chart", fake_render)
    monkeypatch.setitem(namespace, "CONTRACTS", (contracts.CONTRACTS[0],))
    monkeypatch.setattr(contracts.shutil, "which", lambda _: "/test/helm")

    assert contracts.main() == 1
    diagnostics = capsys.readouterr().err
    assert "synthetic-" not in diagnostics
    assert "dev-omi-backend-secrets" not in diagnostics
    for name in ("serviceAccountName", "immutable image", "GOOGLE_CLOUD_PROJECT", "secretKeyRef", "Helm render"):
        assert name in diagnostics


@pytest.mark.parametrize(
    ("returncode", "stdout"),
    [(1, "synthetic-stdout-secret"), (0, "key: [synthetic-yaml-secret")],
)
def test_helm_output_never_escapes_in_render_error(monkeypatch, contracts, returncode, stdout):
    result = SimpleNamespace(returncode=returncode, stdout=stdout, stderr="synthetic-stderr-secret")
    monkeypatch.setattr(contracts.subprocess, "run", lambda *_args, **_kwargs: result)

    with pytest.raises(ValueError, match="Helm") as exc:
        contracts.render_chart(contracts.CONTRACTS[0], "dev", "helm")
    assert "synthetic-" not in str(exc.value)
    assert exc.value.__suppress_context__ or exc.value.__context__ is None


def test_cli_omits_scalar_from_yaml_constructor_error():
    marker = "synthetic-rendered-scalar-marker"
    # Run the CLI entry point with a stubbed Helm process and the real YAML loader.
    bootstrap = """
import runpy
import sys
from subprocess import CompletedProcess
from unittest.mock import patch

with patch("shutil.which", return_value="helm"), patch(
    "subprocess.run", return_value=CompletedProcess([], 0, stdout=sys.argv[2], stderr="")
):
    runpy.run_path(sys.argv[1], run_name="__main__")
"""
    result = subprocess.run(
        [sys.executable, "-c", bootstrap, str(SCRIPT), f"value: !!bool {marker}\n"],
        check=False,
        capture_output=True,
        text=True,
        timeout=15,
    )

    assert result.returncode == 1
    assert marker not in result.stdout
    assert marker not in result.stderr
    assert "Traceback" not in result.stderr
    assert "Helm render failed or returned invalid YAML" in result.stderr


def test_listen_private_env_secret_is_allowed_in_prod_only(contracts: SimpleNamespace):
    listen = contracts.CONTRACTS[0]
    deployment = deepcopy(_deployment(contracts))
    deployment["spec"]["template"]["spec"]["containers"][0]["env"].append(
        {
            "name": "STT_CAP_DISPATCH_COHORT",
            "valueFrom": {
                "secretKeyRef": {"name": "prod-omi-backend-listen-private-env", "key": "STT_CAP_DISPATCH_COHORT"}
            },
        }
    )
    failures = contracts.validate_rendered_deployment(listen, "dev", [deployment])
    # Diagnostics stay value-free (see test_failure_diagnostics_omit_rendered_values).
    assert any("secretKeyRef must target the shared backend secret" in failure for failure in failures)
    assert all("prod-omi-backend-listen-private-env" not in failure for failure in failures)
    prod = _deployment(contracts, environment="prod")
    prod_env = prod["spec"]["template"]["spec"]["containers"][0]["env"]
    prod_env.append(deepcopy(deployment["spec"]["template"]["spec"]["containers"][0]["env"][-1]))
    assert contracts.validate_rendered_deployment(listen, "prod", [prod]) == []
    # The prod-only private secret does not satisfy the shared-secret requirement on its own.
    prod_env[:] = [entry for entry in prod_env if entry["name"] != "OPENAI_API_KEY"]
    assert contracts.validate_rendered_deployment(listen, "prod", [prod]) == [
        "prod/backend-listen: missing required shared backend secretKeyRef"
    ]
    assert ("prod", "prod-omi-backend-listen-private-env") in listen.extra_secret
    assert all(not c.extra_secret for c in contracts.CONTRACTS if c.service != "backend-listen")


@pytest.mark.parametrize("field", ["name", "key"])
@pytest.mark.parametrize("malformed", [["synthetic-list-secret"], {"synthetic": "mapping-secret"}, 7])
def test_malformed_secret_ref_types_fail_closed_without_values(contracts: SimpleNamespace, field, malformed):
    deployment = _deployment(contracts)
    deployment["spec"]["template"]["spec"]["containers"][0]["env"][2]["valueFrom"]["secretKeyRef"][field] = malformed
    failures = contracts.validate_rendered_deployment(contracts.CONTRACTS[0], "dev", [deployment])
    assert "dev/backend-listen: secretKeyRef needs a non-empty name and key" in failures
    assert all("synthetic" not in failure for failure in failures)


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


def test_dev_pusher_rollout_preserves_the_existing_replica(
    rendered_pusher_deployments: tuple[SimpleNamespace, dict[str, dict]],
):
    _, deployments = rendered_pusher_deployments
    deployment = deployments["dev"]
    rolling_update = deployment["spec"]["strategy"]["rollingUpdate"]
    assert rolling_update["maxUnavailable"] == 0
    assert rolling_update["maxSurge"] == 1


def test_pusher_dedicated_pool_toleration_is_dev_only(
    rendered_pusher_deployments: tuple[SimpleNamespace, dict[str, dict]],
):
    _, deployments = rendered_pusher_deployments
    dev_deployment = deployments["dev"]
    prod_deployment = deployments["prod"]
    assert dev_deployment["spec"]["template"]["spec"].get("tolerations") == [
        {"key": "dedicated", "operator": "Equal", "value": "pusher", "effect": "NoSchedule"}
    ]
    assert prod_deployment["spec"]["template"]["spec"].get("tolerations") is None


@pytest.mark.parametrize("environment", ("dev", "prod"))
def test_pusher_explicit_zero_min_ready_seconds_renders(
    rendered_pusher_deployments: tuple[SimpleNamespace, dict[str, dict]], environment: str
):
    _, deployments = rendered_pusher_deployments
    deployment = deployments[environment]
    assert deployment["spec"]["minReadySeconds"] == 0


@pytest.mark.parametrize("environment", ("dev", "prod"))
def test_pusher_does_not_mount_kubernetes_api_credentials(
    rendered_pusher_deployments: tuple[SimpleNamespace, dict[str, dict]], environment: str
):
    _, deployments = rendered_pusher_deployments
    deployment = deployments[environment]
    assert deployment["spec"]["template"]["spec"]["automountServiceAccountToken"] is False
    assert deployment["spec"]["template"]["spec"]["containers"][0]["securityContext"] == {
        "allowPrivilegeEscalation": False,
        "capabilities": {"drop": ["ALL"]},
        "runAsNonRoot": True,
        "runAsUser": 10001,
    }


def test_pusher_rejects_a_missing_min_ready_seconds(contracts: SimpleNamespace, tmp_path: Path):
    helm = shutil.which("helm")
    assert helm is not None, "helm must be installed for the rendered deployment contract"
    contract = next(contract for contract in contracts.CONTRACTS if contract.service == "pusher")
    values = contracts.values_file(contract, "dev")
    missing_min_ready_values = tmp_path / values.name
    original = values.read_text(encoding="utf-8")
    assert original.count("minReadySeconds: 0\n") == 1
    missing_min_ready_values.write_text(original.replace("minReadySeconds: 0\n", "", 1), encoding="utf-8")

    result = contracts.subprocess.run(
        [
            helm,
            "template",
            contracts.release_name(contract, "dev"),
            str(contracts.chart_dir(contract)),
            "-f",
            str(missing_min_ready_values),
            "--set-string",
            f"image.tag={contracts.CONTRACT_IMAGE_TAG}",
        ],
        cwd=contracts.ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "minReadySeconds is required" in result.stderr


def test_first_party_charts_reject_missing_image_tag_when_helm_is_available(
    untagged_chart_results: list[tuple[str, str, Any]],
):
    for environment, service, result in untagged_chart_results:
        assert result.returncode != 0, f"{environment}/{service} accepted an untagged image"
        assert "image.tag is required" in result.stderr
