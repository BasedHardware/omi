"""Prod listen rollouts must preserve the keyless incident recovery."""

from pathlib import Path
import shutil
import subprocess

import pytest
import yaml

CHART = Path(__file__).resolve().parents[2] / "charts" / "backend-listen"
KEY_ENV_NAMES = {"SERVICE_ACCOUNT_JSON", "GOOGLE_APPLICATION_CREDENTIALS"}


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
    helm = shutil.which("helm")
    assert helm is not None, "helm is required to verify the prod listen render"
    command = [
        helm,
        "template",
        request.param,
        str(CHART),
        "--namespace",
        "prod-omi-backend",
        "-f",
        str(CHART / "prod_omi_backend_listen_values.yaml"),
        "--set-string",
        "image.tag=0123456",
    ]
    if request.param != "prod-omi-backend-listen":
        command.extend(["--set-string", "serviceAccount.name=prod-omi-backend-listen"])
    result = subprocess.run(
        command,
        check=True,
        capture_output=True,
        text=True,
    )
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
