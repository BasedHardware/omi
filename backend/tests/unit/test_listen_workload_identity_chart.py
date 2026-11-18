"""Prod listen rollouts must preserve the keyless incident recovery."""

from pathlib import Path
import shutil
import subprocess

import pytest
import yaml

CHART = Path(__file__).resolve().parents[2] / "charts" / "backend-listen"
KEY_ENV_NAMES = {"SERVICE_ACCOUNT_JSON", "GOOGLE_APPLICATION_CREDENTIALS"}


def _render(environment, release, *arguments):
    helm = shutil.which("helm")
    assert helm is not None, "helm is required to verify the listen render"
    return subprocess.run(
        [
            helm,
            "template",
            release,
            str(CHART),
            "--namespace",
            f"{environment}-omi-backend",
            "-f",
            str(CHART / f"{environment}_omi_backend_listen_values.yaml"),
            "--set-string",
            "image.tag=0123456",
            *arguments,
        ],
        check=False,
        capture_output=True,
        text=True,
    )


@pytest.fixture(
    scope="module",
    params=(
        "prod-omi-backend-listen",
        "listen-parakeet",
        "listen-soniox",
        "listen-dg-canary",
        "listen-velma-canary",
    ),
)
def prod_listen_documents(request):
    arguments = []
    if request.param != "prod-omi-backend-listen":
        arguments.extend(["--set-string", "serviceAccount.name=prod-omi-backend-listen"])
    result = _render("prod", request.param, *arguments)
    assert result.returncode == 0, result.stderr
    return [document for document in yaml.safe_load_all(result.stdout) if document]


def test_prod_listen_renders_workload_identity_without_json_key_env(prod_listen_documents):
    documents = prod_listen_documents
    deployment = next(document for document in documents if document["kind"] == "Deployment")
    pod = deployment["spec"]["template"]["spec"]
    assert pod["serviceAccountName"] == "prod-omi-backend-listen"
    for container in pod["containers"]:
        env = {entry["name"]: entry for entry in container.get("env", [])}
        assert KEY_ENV_NAMES.isdisjoint(env)
        assert env["OMI_CUSTOMER_DATA_PROJECT"]["value"] == "based-hardware"
        assert all("secretRef" not in source for source in container.get("envFrom", []))
    service_account = next(document for document in documents if document["kind"] == "ServiceAccount")
    assert service_account["metadata"]["name"] == pod["serviceAccountName"]
    assert service_account["metadata"]["annotations"]["iam.gke.io/gcp-service-account"] == (
        "backend-listen-runtime@based-hardware.iam.gserviceaccount.com"
    )


@pytest.fixture(scope="module", params=("runtime_env.yaml", "runtime_env/prod.overlay.yaml"))
def prod_listen_runtime_env(request):
    manifest = yaml.safe_load((CHART.parents[1] / "deploy" / request.param).read_text())
    prod = manifest["environments"]["prod"] if "environments" in manifest else manifest["overlay"]
    return prod["gke"]["backend-listen"]["env"]


def test_prod_listen_runtime_manifest_cannot_restore_a_json_key(prod_listen_runtime_env):
    assert KEY_ENV_NAMES.isdisjoint(prod_listen_runtime_env)


@pytest.fixture(
    scope="module",
    params=[
        (stage, source, name)
        for stage in ("dev", "prod")
        for source in ("env", "privateEnv")
        for name in sorted(KEY_ENV_NAMES)
    ],
)
def credential_override_render(request, tmp_path_factory):
    stage, source, name = request.param
    override = (
        {source: {name: "synthetic-revoked-key"}}
        if source == "privateEnv"
        else {"env": [{"name": name, "value": "synthetic-revoked-key"}]}
    )
    values = tmp_path_factory.mktemp("listen-key-override") / "values.yaml"
    values.write_text(yaml.safe_dump(override))
    return stage, name, _render(stage, f"{stage}-omi-backend-listen", "-f", str(values))


def test_prod_rejects_key_overrides_and_dev_behavior_is_preserved(credential_override_render):
    stage, name, result = credential_override_render
    if stage == "prod":
        assert result.returncode != 0
        assert "workloadIdentityOnly forbids key credential environment variables" in result.stderr
        assert "synthetic-revoked-key" not in result.stderr
    else:
        assert result.returncode == 0, result.stderr
        documents = [document for document in yaml.safe_load_all(result.stdout) if document]
        deployment = next(document for document in documents if document["kind"] == "Deployment")
        env = deployment["spec"]["template"]["spec"]["containers"][0]["env"]
        assert {entry["name"]: entry.get("value") for entry in env}[name] == "synthetic-revoked-key"


@pytest.fixture(scope="module")
def prod_retired_private_override():
    return _render("prod", "prod-omi-backend-listen", "--set-string", "privateEnv.OMI_PRIVATE_TEST=synthetic-value")


def test_prod_refuses_the_retired_private_env_overlay(prod_retired_private_override):
    # Private values are Secret Manager references (privateSecretEnv); a literal
    # privateEnv value can no longer reach a prod render.
    assert prod_retired_private_override.returncode != 0
    assert "privateEnv is retired" in prod_retired_private_override.stderr
    assert "synthetic-value" not in prod_retired_private_override.stderr


def test_prod_private_secret_env_renders_references_only():
    result = _render(
        "prod", "prod-omi-backend-listen", "--set", "privateSecretEnv.keys={STT_CAP_DISPATCH_COHORT,OMI_PRIVATE_TEST}"
    )
    assert result.returncode == 0, result.stderr
    documents = [document for document in yaml.safe_load_all(result.stdout) if document]
    deployment = next(document for document in documents if document["kind"] == "Deployment")
    env = deployment["spec"]["template"]["spec"]["containers"][0]["env"]
    names = [entry["name"] for entry in env]
    assert len(names) == len(set(names))
    by_name = {entry["name"]: entry for entry in env}
    for name in ("STT_CAP_DISPATCH_COHORT", "OMI_PRIVATE_TEST"):
        assert "value" not in by_name[name]
        assert by_name[name]["valueFrom"] == {
            "secretKeyRef": {"name": "prod-omi-backend-listen-private-env", "key": name, "optional": False}
        }


@pytest.mark.parametrize("name", sorted(KEY_ENV_NAMES))
def test_prod_private_secret_env_cannot_carry_a_key_credential(name):
    result = _render("prod", "prod-omi-backend-listen", "--set", f"privateSecretEnv.keys={{{name}}}")
    assert result.returncode != 0
    assert "workloadIdentityOnly forbids key credential environment variables" in result.stderr


@pytest.mark.parametrize("name", ["GOOGLE_CLOUD_PROJECT", "STT_SERVICE_MODELS", "OMI_LLM_GATEWAY_FEATURE_MODE"])
def test_prod_private_secret_env_cannot_shadow_chart_or_dispatch_owned_env(name):
    # A secretKeyRef would silently win over the chart-derived value or a workflow_dispatch --set override.
    result = _render("prod", "prod-omi-backend-listen", "--set", f"privateSecretEnv.keys={{{name}}}")
    assert result.returncode != 0
    assert f"privateSecretEnv.keys cannot name {name}" in result.stderr
