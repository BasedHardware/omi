import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = BACKEND_ROOT / "scripts" / "jit_qa_cloud_run_contract.py"
WORKFLOW = BACKEND_ROOT.parent / ".github" / "workflows" / "jit_qa_cloud_run.yml"
TYPESENSE_WORKFLOW = BACKEND_ROOT.parent / ".github" / "workflows" / "jit_qa_typesense_projection.yml"


def _load_contract():
    spec = importlib.util.spec_from_file_location("jit_qa_cloud_run_contract_for_test", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


CONTRACT = _load_contract()


def _resource(profile: str, kind: str, image: str) -> dict:
    literals, secrets = CONTRACT.resource_environment(profile)
    env = [{"name": name, "value": value} for name, value in literals.items()]
    env.extend(
        {
            "name": name,
            "valueSource": {
                "secretKeyRef": {"secret": reference.rsplit(":", 1)[0], "version": reference.rsplit(":", 1)[1]}
            },
        }
        for name, reference in secrets.items()
    )
    if kind == "service":
        template = {
            "spec": {
                "containers": [{"image": image, "env": env}],
                "serviceAccountName": CONTRACT.RUNTIME_SERVICE_ACCOUNT,
            }
        }
        spec = {"template": template}
    else:
        template = {
            "template": {
                "containers": [{"image": image, "env": env}],
                "serviceAccount": CONTRACT.RUNTIME_SERVICE_ACCOUNT,
            }
        }
        spec = {"template": template}
    return {"metadata": {"name": "qa-resource"}, "spec": spec}


def test_static_configuration_is_dev_only_and_requires_five_immutable_images():
    images = {
        name: f"gcr.io/based-hardware-dev/{name}@sha256:{'a' * 64}"
        for name in ("backend", "desktop", "gateway", "drain", "sweep")
    }
    CONTRACT.validate_static_configuration(
        project="based-hardware-dev",
        region="us-central1",
        auth_project="based-hardware",
        uid=CONTRACT.QA_UID,
        drain_enabled="false",
        sweep_enabled="false",
        sweep_kill_switch="false",
        run_once="false",
        confirmation="",
        images=images,
    )


def test_static_configuration_requires_all_immutable_images():
    with pytest.raises(CONTRACT.JITQAContractError, match="exactly these QA images"):
        CONTRACT.validate_static_configuration(
            project="based-hardware-dev",
            region="us-central1",
            auth_project="based-hardware",
            uid=CONTRACT.QA_UID,
            drain_enabled="false",
            sweep_enabled="false",
            sweep_kill_switch="false",
            run_once="false",
            confirmation="",
        )


@pytest.mark.parametrize(
    "kwargs",
    [
        {"project": "based-hardware"},
        {"region": "europe-west1"},
        {"auth_project": "based-hardware-dev"},
        {"uid": "9OqYLlKJv4hmeYpIhwJcHBR975i2"},
        {"drain_enabled": "true"},
        {"sweep_enabled": "true"},
        {"sweep_kill_switch": "true"},
    ],
)
def test_static_configuration_rejects_non_qa_values(kwargs):
    values = {
        "project": "based-hardware-dev",
        "region": "us-central1",
        "auth_project": "based-hardware",
        "uid": CONTRACT.QA_UID,
        "drain_enabled": "false",
        "sweep_enabled": "false",
        "sweep_kill_switch": "false",
        "run_once": "false",
        "confirmation": "",
    }
    values.update(kwargs)
    with pytest.raises(CONTRACT.JITQAContractError):
        CONTRACT.validate_static_configuration(**values)


def test_execution_requires_explicit_confirmation_and_keeps_kill_switch_closed():
    with pytest.raises(CONTRACT.JITQAContractError):
        CONTRACT.validate_execution(run_once="false", confirmation="RUN_ONCE")
    with pytest.raises(CONTRACT.JITQAContractError):
        CONTRACT.validate_execution(run_once="true", confirmation="NO")
    with pytest.raises(CONTRACT.JITQAContractError):
        CONTRACT.validate_execution(run_once="true", confirmation="RUN_ONCE", kill_switch="true")
    CONTRACT.validate_execution(run_once="true", confirmation="RUN_ONCE")


def test_environment_rejects_customer_credential_and_wrong_data_plane():
    literals, _ = CONTRACT.resource_environment("drain")
    with pytest.raises(CONTRACT.JITQAContractError):
        CONTRACT.validate_environment({**literals, "SERVICE_ACCOUNT_JSON": "customer-json"}, profile="drain")
    with pytest.raises(CONTRACT.JITQAContractError):
        CONTRACT.validate_environment(
            {**literals, "OMI_FIRESTORE_DATA_PLANE_PROJECT": "based-hardware"}, profile="drain"
        )
    CONTRACT.validate_environment({**literals}, profile="drain")


def test_environment_requires_profile_specific_drain_allowlist():
    literals, _ = CONTRACT.resource_environment("sweep")
    CONTRACT.validate_environment({**literals}, profile="sweep")
    with pytest.raises(CONTRACT.JITQAContractError, match="only valid on the drain profile"):
        CONTRACT.validate_environment(
            {**literals, "KNOWLEDGE_LEDGER_DRAIN_UID_ALLOWLIST": CONTRACT.QA_UID}, profile="sweep"
        )


def test_cloud_run_resource_requires_exact_image_env_secrets_name_and_identity():
    image = "gcr.io/based-hardware-dev/backend-jit-qa@sha256:" + "b" * 64
    resource = _resource("backend", "service", image)
    resource["metadata"]["name"] = CONTRACT.BACKEND_SERVICE
    CONTRACT.validate_cloud_run_resource(
        resource,
        kind="service",
        expected_image=image,
        expected_environment=CONTRACT.resource_environment("backend")[0],
        expected_secret_bindings=CONTRACT.resource_environment("backend")[1],
        expected_name=CONTRACT.BACKEND_SERVICE,
    )
    resource["spec"]["template"]["spec"]["containers"][0]["image"] = image.replace("@sha256:", ":")
    with pytest.raises(CONTRACT.JITQAContractError):
        CONTRACT.validate_cloud_run_resource(
            resource,
            kind="service",
            expected_image=image,
            expected_environment=CONTRACT.resource_environment("backend")[0],
            expected_secret_bindings=CONTRACT.resource_environment("backend")[1],
        )


def test_cloud_run_resource_rejects_inherited_cache_or_customer_binding():
    image = "gcr.io/based-hardware-dev/knowledge-ledger-drain-qa-job@sha256:" + "c" * 64
    resource = _resource("drain", "job", image)
    resource["metadata"]["name"] = CONTRACT.LEDGER_DRAIN_JOB
    resource["spec"]["template"]["template"]["containers"][0]["env"].append(
        {"name": "REDIS_DB_HOST", "value": "shared-cache.internal"}
    )
    with pytest.raises(CONTRACT.JITQAContractError):
        CONTRACT.validate_cloud_run_resource(
            resource,
            kind="job",
            expected_image=image,
            expected_environment=CONTRACT.resource_environment("drain")[0],
            expected_secret_bindings=CONTRACT.resource_environment("drain")[1],
        )


def test_cloud_run_resource_accepts_rest_omitted_value_for_explicitly_empty_sweep_flag():
    image = "gcr.io/based-hardware-dev/daily-memory-sweep-qa-job@sha256:" + "e" * 64
    resource = _resource("sweep", "job", image)
    resource["metadata"]["name"] = CONTRACT.DAILY_SWEEP_JOB
    env = resource["spec"]["template"]["template"]["containers"][0]["env"]
    env.remove(next(entry for entry in env if entry["name"] == "MEMORY_DAILY_MEMORY_SWEEP_COHORT_FLAG"))
    env.append({"name": "MEMORY_DAILY_MEMORY_SWEEP_COHORT_FLAG"})

    CONTRACT.validate_cloud_run_resource(
        resource,
        kind="job",
        expected_image=image,
        expected_environment=CONTRACT.resource_environment("sweep")[0],
        expected_secret_bindings=CONTRACT.resource_environment("sweep")[1],
        expected_name=CONTRACT.DAILY_SWEEP_JOB,
    )


def test_cloud_run_resource_rejects_null_for_explicitly_empty_sweep_flag():
    image = "gcr.io/based-hardware-dev/daily-memory-sweep-qa-job@sha256:" + "f" * 64
    resource = _resource("sweep", "job", image)
    resource["metadata"]["name"] = CONTRACT.DAILY_SWEEP_JOB
    cohort_flag = next(
        entry
        for entry in resource["spec"]["template"]["template"]["containers"][0]["env"]
        if entry["name"] == "MEMORY_DAILY_MEMORY_SWEEP_COHORT_FLAG"
    )
    cohort_flag["value"] = None

    with pytest.raises(CONTRACT.JITQAContractError, match="unexpected value"):
        CONTRACT.validate_cloud_run_resource(
            resource,
            kind="job",
            expected_image=image,
            expected_environment=CONTRACT.resource_environment("sweep")[0],
            expected_secret_bindings=CONTRACT.resource_environment("sweep")[1],
            expected_name=CONTRACT.DAILY_SWEEP_JOB,
        )


def test_cloud_run_v1_nested_job_fixture_is_supported():
    image = "gcr.io/based-hardware-dev/knowledge-ledger-drain-qa-job@sha256:" + "d" * 64
    fixture_path = BACKEND_ROOT / "tests" / "fixtures" / "jit_qa" / "cloud_run_v1_job.json"
    resource = json.loads(fixture_path.read_text(encoding="utf-8"))
    CONTRACT.validate_cloud_run_resource(
        resource,
        kind="job",
        expected_image=image,
        expected_environment=CONTRACT.resource_environment("drain")[0],
        expected_secret_bindings=CONTRACT.resource_environment("drain")[1],
        expected_name=CONTRACT.LEDGER_DRAIN_JOB,
    )


def test_cloud_run_v1_nested_service_fixture_is_supported():
    image = "gcr.io/based-hardware-dev/backend-jit-qa@sha256:" + "b" * 64
    fixture_path = BACKEND_ROOT / "tests" / "fixtures" / "jit_qa" / "cloud_run_v1_service.json"
    resource = json.loads(fixture_path.read_text(encoding="utf-8"))
    literals, secrets = CONTRACT.resource_environment("backend")
    CONTRACT.validate_cloud_run_resource(
        resource,
        kind="service",
        expected_image=image,
        expected_environment=literals,
        expected_secret_bindings=secrets,
        expected_name=CONTRACT.BACKEND_SERVICE,
        gateway_url=CONTRACT.DEFAULT_GATEWAY_URL,
        redis_host=CONTRACT.DEFAULT_REDIS_HOST,
    )


def test_gateway_route_and_qa_http_contract_reject_direct_fallback():
    literals, _ = CONTRACT.resource_environment("backend", gateway_url="https://gateway.example", redis_host="10.0.0.2")
    assert literals["OMI_LLM_GATEWAY_FEATURE_MODE"] == "gateway"
    assert literals["OMI_LLM_GATEWAY_ALLOW_DIRECT_MODEL_EXCEPTION"] == "false"
    with pytest.raises(CONTRACT.JITQAContractError):
        CONTRACT.validate_qa_http_environment(
            {**literals, "OMI_LLM_GATEWAY_FEATURE_MODE": "direct"},
            gateway_url="https://gateway.example",
            redis_host="10.0.0.2",
        )


def test_gateway_resource_is_fenced_to_the_fixed_qa_uid():
    literals, _ = CONTRACT.resource_environment("gateway")
    assert literals["OMI_JIT_QA_AUTH_ONLY"] == "true"
    assert literals["OMI_JIT_QA_UID_ALLOWLIST"] == CONTRACT.QA_UID


def _typesense_resource(image: str) -> dict:
    return {
        "metadata": {"name": CONTRACT.TYPESENSE_SERVICE},
        "spec": {
            "template": {
                "serviceAccountName": CONTRACT.RUNTIME_SERVICE_ACCOUNT,
                "scaling": {
                    "minInstanceCount": CONTRACT.TYPESENSE_MIN_INSTANCES,
                    "maxInstanceCount": CONTRACT.TYPESENSE_MAX_INSTANCES,
                },
                "containers": [
                    {
                        "image": image,
                        "command": [CONTRACT.TYPESENSE_ENTRYPOINT],
                        "args": [],
                        "env": [
                            {"name": "TYPESENSE_DATA_DIR", "value": "/tmp/typesense"},
                            {
                                "name": "TYPESENSE_API_KEY",
                                "valueSource": {
                                    "secretKeyRef": {
                                        "secret": CONTRACT.TYPESENSE_API_SECRET,
                                        "version": "latest",
                                    }
                                },
                            },
                        ],
                        "resources": {
                            "limits": {
                                "cpu": CONTRACT.TYPESENSE_CPU,
                                "memory": CONTRACT.TYPESENSE_MEMORY,
                            }
                        },
                    }
                ],
            }
        },
    }


def test_typesense_workflow_is_pinned_to_named_dev_firestore_and_immutable_base():
    CONTRACT.validate_typesense_workflow_configuration(
        project="based-hardware-dev",
        region="us-central1",
        auth_project="based-hardware",
        uid=CONTRACT.QA_UID,
        database="jit-qa",
        base_image=CONTRACT.TYPESENSE_BASE_IMAGE_27_1,
        source_sha="b" * 40,
    )
    with pytest.raises(CONTRACT.JITQAContractError):
        CONTRACT.validate_typesense_workflow_configuration(
            project="based-hardware",
            region="us-central1",
            auth_project="based-hardware",
            uid=CONTRACT.QA_UID,
            database="jit-qa",
            base_image="docker.io/typesense/typesense@sha256:" + "a" * 64,
            source_sha="b" * 40,
        )
    with pytest.raises(CONTRACT.JITQAContractError, match="reviewed Typesense 27.1 digest"):
        CONTRACT.validate_typesense_workflow_configuration(
            project="based-hardware-dev",
            region="us-central1",
            auth_project="based-hardware",
            uid=CONTRACT.QA_UID,
            database="jit-qa",
            base_image="docker.io/typesense/typesense@sha256:" + "a" * 64,
            source_sha="b" * 40,
        )


def test_typesense_resource_requires_single_bounded_container_and_dedicated_key():
    image = "gcr.io/based-hardware-dev/typesense-jit-qa@sha256:" + "e" * 64
    resource = _typesense_resource(image)
    CONTRACT.validate_typesense_cloud_run_resource(resource, expected_image=image)
    resource["spec"]["template"]["scaling"]["maxInstanceCount"] = 2
    with pytest.raises(CONTRACT.JITQAContractError, match="bounded to one instance"):
        CONTRACT.validate_typesense_cloud_run_resource(resource, expected_image=image)


def test_typesense_resource_rejects_extra_environment():
    image = "gcr.io/based-hardware-dev/typesense-jit-qa@sha256:" + "f" * 64
    resource = _typesense_resource(image)
    resource["spec"]["template"]["containers"][0]["env"].append(
        {"name": "GOOGLE_CLOUD_PROJECT", "value": "based-hardware"}
    )
    with pytest.raises(CONTRACT.JITQAContractError, match="unapproved environment"):
        CONTRACT.validate_typesense_cloud_run_resource(resource, expected_image=image)


def test_typesense_resource_accepts_v1_autoscaling_annotations():
    image = "gcr.io/based-hardware-dev/typesense-jit-qa@sha256:" + "f" * 64
    resource = _typesense_resource(image)
    template = resource["spec"]["template"]
    template["metadata"] = {
        "annotations": {
            "autoscaling.knative.dev/minScale": "1",
            "autoscaling.knative.dev/maxScale": "1",
        }
    }
    template.pop("scaling")
    CONTRACT.validate_typesense_cloud_run_resource(resource, expected_image=image)


def test_typesense_resource_accepts_cloud_run_service_level_scaling_and_cpu_encoding():
    image = "gcr.io/based-hardware-dev/typesense-jit-qa@sha256:" + "f" * 64
    resource = _typesense_resource(image)
    template = resource["spec"]["template"]
    template.pop("scaling")
    resource["metadata"]["annotations"] = {
        "run.googleapis.com/minScale": "1",
        "run.googleapis.com/maxScale": "1",
    }
    template["containers"][0]["resources"]["limits"]["cpu"] = "1000m"
    CONTRACT.validate_typesense_cloud_run_resource(resource, expected_image=image)


@pytest.mark.parametrize("profile", ("backend", "desktop", "drain", "sweep"))
def test_rollout_profiles_require_the_real_posthog_control_plane_secret(profile):
    _, secrets = CONTRACT.resource_environment(profile)
    assert secrets["POSTHOG_PROJECT_API_KEY"] == "POSTHOG_PROJECT_API_KEY:latest"


def test_workflow_is_manual_main_only_and_cannot_reach_prod_or_scheduler():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "workflow_dispatch:" in text
    assert '"refs/heads/main"' in text
    assert '[[ "${GITHUB_REF}"' in text
    assert "based-hardware-dev" in text
    assert "backend-jit-qa" in text
    assert "desktop-backend-jit-qa" in text
    assert "llm-gateway-jit-qa" in text
    assert "knowledge-ledger-drain-qa-job" in text
    assert "daily-memory-sweep-qa-job" in text
    assert "runWithOverrides" in text
    assert "actions/upload-artifact@v7" in text
    assert "gcloud scheduler" not in text
    assert "iam policy" not in text
    assert "--max-retries 0" in text
    assert "RUN_ONCE" in text
    assert "jobs executions describe" in text
    assert "jobs executions describe \"$execution\" --job" not in text
    assert "--set-env-vars \"$gateway_env\"" in text
    assert "--set-env-vars \"$drain_env\"" in text
    assert 'LLM_GATEWAY_ALLOWED_CALLERS=backend,desktop' in text
    assert 'gcloud firestore databases describe --database "$QA_FIRESTORE_DATABASE"' in text
    assert 'gcloud redis instances describe "$QA_REDIS_INSTANCE"' in text
    assert "POSTHOG_PROJECT_API_KEY=POSTHOG_PROJECT_API_KEY:latest" in text
    assert "RUN_MODEL_EXPERIMENT" not in text
    assert "MODEL_CONFIRMATION_INPUT" not in text
    assert "gcr.io/${QA_PROJECT}" in text
    assert "vars.GCP_PROJECT_ID" not in text
    assert "environment: prod" not in text


def test_typesense_workflow_smokes_images_before_publish_and_has_unready_bootstrap():
    text = TYPESENSE_WORKFLOW.read_text(encoding="utf-8")
    assert "mode:" in text
    assert "- bootstrap" in text and "- prove" in text
    assert "docker run --detach --name \"$smoke_name\"" in text
    assert "unauthenticated_status" in text
    assert '"$smoke_url/collections/jit_qa_smoke/documents/export?include_fields=id,content"' in text
    assert 'scripts/jit_qa_typesense_projection.py --help' in text
    assert "if: ${{ inputs.mode == 'prove' }}" in text
    assert "if: ${{ inputs.mode == 'bootstrap' }}" in text
    assert '"status": "not_qualified"' in text
    assert '"readiness_marker": "absent"' in text
    assert "group: jit-isolated-qa-cloud-run-development" in text


def test_bounded_proactivity_capability_is_required_on_qa_http_and_gateway_only():
    key = "OMI_JIT_PROACTIVITY_BUDGET_CONTRACT"
    for profile in ("backend", "desktop", "gateway"):
        literals, _ = CONTRACT.resource_environment(profile)
        assert literals[key] == "jit-cloud-qa-v1"
    for profile in ("drain", "sweep"):
        literals, _ = CONTRACT.resource_environment(profile)
        assert key not in literals


def test_qa_cloud_run_rendered_typesense_shell_accepts_real_host_and_digest():
    text = WORKFLOW.read_text(encoding="utf-8")
    start = 'typesense_image="$(python3 - "$typesense_resource" "$SOURCE_SHA" "$typesense_host" "$expected_typesense_image" <<\'PY\''
    rendered = text.split(start, 1)[1].split("\n          PY", 1)[0]
    rendered = textwrap.dedent(rendered.lstrip("\n"))
    image = "gcr.io/based-hardware-dev/typesense-jit-qa@sha256:" + "a" * 64
    resource = {
        "metadata": {"labels": {"managed-by": "github-actions", "jit-qa": "true", "source-sha": "b" * 40}},
        "spec": {
            "template": {
                "spec": {"containers": [{"image": image}]},
            }
        },
    }
    for host in (
        "typesense-jit-qa-1031333818730.us-central1.run.app",
        "typesense-jit-qa-dt5lrfkkoa-uc.a.run.app",
    ):
        with tempfile.NamedTemporaryFile("w", encoding="utf-8") as file:
            json.dump(resource, file)
            file.flush()
            result = subprocess.run(
                [sys.executable, "-", file.name, "b" * 40, host, image],
                input=rendered,
                text=True,
                capture_output=True,
                check=False,
            )
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == image

    with tempfile.NamedTemporaryFile("w", encoding="utf-8") as file:
        json.dump(resource, file)
        file.flush()
        result = subprocess.run(
            [
                sys.executable,
                "-",
                file.name,
                "b" * 40,
                "typesense-jit-qa-1031333818730.us-central1.run.app",
                "gcr.io/based-hardware-dev/typesense-jit-qa@sha256:" + "c" * 64,
            ],
            input=rendered,
            text=True,
            capture_output=True,
            check=False,
        )
    assert result.returncode != 0
    assert "source-SHA registry digest" in result.stderr


def test_qa_cloud_run_renders_typesense_host_and_key_into_both_http_services():
    text = WORKFLOW.read_text(encoding="utf-8")
    common_line = next(line.strip() for line in text.splitlines() if line.strip().startswith("common=\"^@^"))
    env = {
        "QA_PROJECT": "based-hardware-dev",
        "QA_FIRESTORE_DATABASE": "jit-qa",
        "QA_AUTH_PROJECT": "based-hardware",
        "QA_UID": CONTRACT.QA_UID,
        "QA_TYPESENSE_COLLECTION": CONTRACT.TYPESENSE_COLLECTION,
        "QA_TYPESENSE_READINESS_COLLECTION": CONTRACT.TYPESENSE_READINESS_COLLECTION,
        "GATEWAY_URL": "https://llm-gateway-jit-qa-abc.run.app",
        "REDIS_HOST": "10.0.0.10",
        "TYPESENSE_HOST": "typesense-jit-qa-1031333818730.us-central1.run.app",
        "SOURCE_SHA": "b" * 40,
    }
    rendered = subprocess.run(
        ["bash", "-c", f"set -euo pipefail\n{common_line}\nprintf '%s' \"$common\""],
        env={**os.environ, **env},
        text=True,
        capture_output=True,
        check=False,
    )
    assert rendered.returncode == 0, rendered.stderr
    common = rendered.stdout
    assert "@TYPESENSE_HOST=typesense-jit-qa-1031333818730.us-central1.run.app@" in common
    assert "@MEMORY_TYPESENSE_COLLECTION=jit_qa_canonical_memory_atoms@" in common
    assert "@MEMORY_TYPESENSE_READINESS_SOURCE_SHA=" + "b" * 40 in common
    deploy_line = next(line for line in text.splitlines() if "--set-secrets" in line and "TYPESENSE_API_KEY" in line)
    assert 'for pair in "$QA_SERVICE:$BACKEND_IMAGE" "$QA_DESKTOP_SERVICE:$DESKTOP_IMAGE"' in text
    assert "TYPESENSE_API_KEY=${QA_TYPESENSE_SECRET}:latest" in deploy_line


def test_typesense_entrypoint_uses_environment_key_without_secret_argument():
    entrypoint = (BACKEND_ROOT / "scripts" / "jit_qa_typesense_entrypoint.sh").read_text(encoding="utf-8")
    assert "TYPESENSE_API_KEY" in entrypoint
    assert "--api-key" not in entrypoint
