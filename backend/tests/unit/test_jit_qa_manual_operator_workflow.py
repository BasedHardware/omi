import os
import json
import subprocess
from tempfile import TemporaryDirectory

from pathlib import Path

import yaml

WORKFLOW = Path(__file__).resolve().parents[2] / ".." / ".github" / "workflows" / "jit_qa_manual_operator.yml"
QA_CLOUD_WORKFLOW = Path(__file__).resolve().parents[2] / ".." / ".github" / "workflows" / "jit_qa_cloud_run.yml"


def _workflow_steps():
    document = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    return document["jobs"]["operate"]["steps"]


def _step(name: str):
    return next(step for step in _workflow_steps() if step.get("name") == name)


def _qa_cloud_steps():
    document = yaml.safe_load(QA_CLOUD_WORKFLOW.read_text(encoding="utf-8"))
    return document["jobs"]["provision"]["steps"]


def test_manual_operator_is_main_only_and_qa_fenced():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "workflow_dispatch:" in text
    assert "github.ref == 'refs/heads/main'" in text
    assert "based-hardware-dev" in text
    assert "QA_DATABASE: jit-qa" in text
    assert "QA_UID: vi7SA9ckQCe4ccobWNxlbdcNdC23" in text
    assert "QA_DRAIN_JOB: knowledge-ledger-drain-qa-job" in text
    assert "source_sha" in text
    assert "verify_backend_release_admission.py" in text
    assert "actions/upload-artifact@v7" in text


def test_manual_operator_uses_existing_seed_contract_without_deploying_resources():
    text = WORKFLOW.read_text(encoding="utf-8")
    for operation in (
        "bootstrap",
        "ensure-infrastructure-api",
        "indexes-plan",
        "indexes-apply",
        "prepare",
        "inspect",
        "drain-verify",
        "rollback",
        "rollforward",
    ):
        assert operation in text
    assert "jit_qa_seed_and_verify.py bootstrap" in text
    assert "jit_qa_seed_and_verify.py" in text
    assert "--update-env-vars \"KNOWLEDGE_LEDGER_DRAIN_ENABLED=true" in text
    assert "jobs executions describe" in text
    assert "jit_qa_manual_operator.py validate-job" in text
    assert "gcloud container images describe" in text
    assert "--expected-image \"$QA_DRAIN_IMAGE\"" in text
    assert "DRAIN_VERIFY_QA" in text
    assert "ROLLBACK_QA" in text
    assert "ENABLE_QA_API" in text
    assert "redis.googleapis.com" in text
    assert "jit_qa_firestore_index_operator.py" in text
    assert "APPLY_JIT_QA_INDEXES" in text
    assert "gcloud run deploy" not in text
    assert "gcloud run jobs deploy" not in text
    assert "gcloud scheduler" not in text
    assert "docker build" not in text
    assert "api.omi.me" not in text


def test_every_workflow_shell_block_is_valid_bash():
    for step in _workflow_steps():
        command = step.get("run")
        if command:
            result = subprocess.run(
                ["bash", "-n", "-o", "pipefail", "-c", command],
                capture_output=True,
                text=True,
            )
            assert result.returncode == 0, f"{step['name']}: {result.stderr}"


def test_dependency_setup_executes_pinned_runtime_help_smoke_with_qa_environment():
    step = _step("Install pinned backend runtime and verify operator imports")
    assert step["env"]["OMI_FIRESTORE_DATA_PLANE_PROJECT"] == "${{ env.QA_PROJECT }}"
    assert step["env"]["FIREBASE_AUTH_PROJECT_ID"] == "based-hardware"
    assert "pylock.runtime.toml" in step["run"]
    assert "scripts/jit_qa_seed_and_verify.py --help" not in step["run"]
    assert "scripts/jit_qa_firestore_index_operator.py --help" in step["run"]

    with TemporaryDirectory() as temporary:
        root = Path(temporary)
        (root / "backend" / "scripts").mkdir(parents=True)
        (root / "backend" / "scripts" / "jit_qa_manual_operator.py").write_text("", encoding="utf-8")
        (root / "backend" / "scripts" / "jit_qa_firestore_index_operator.py").write_text("", encoding="utf-8")
        fake_bin = root / "fake-bin"
        fake_bin.mkdir()
        (fake_bin / "uv").write_text(
            "#!/usr/bin/env bash\n"
            "set -euo pipefail\n"
            "if [[ ${1:-} == venv ]]; then mkdir -p \"$2/bin\"; fi\n"
            "if [[ ${1:-} == venv ]]; then cat > \"$2/bin/python\" <<'PY'\n"
            "#!/usr/bin/env bash\n"
            "set -euo pipefail\n"
            "printf '%s\\n' \"$*\" >> \"$CALL_LOG\"\n"
            "exit 0\n"
            "PY\nchmod +x \"$2/bin/python\"; fi\n",
            encoding="utf-8",
        )
        (fake_bin / "uv").chmod(0o755)
        github_path = root / "github-path"
        environment = {
            "PATH": f"{fake_bin}:{os.environ['PATH']}",
            "GITHUB_PATH": str(github_path),
            "CALL_LOG": str(root / "python-calls"),
            "OMI_ENV_STAGE": "dev",
            "GOOGLE_CLOUD_PROJECT": "based-hardware-dev",
            "GCLOUD_PROJECT": "based-hardware-dev",
            "OMI_FIRESTORE_DATA_PLANE_PROJECT": "based-hardware-dev",
            "FIRESTORE_DATABASE_ID": "jit-qa",
            "FIREBASE_AUTH_PROJECT_ID": "based-hardware",
            "MEMORY_ENABLED": "on",
            "OMI_JIT_QA_AUTH_ONLY": "true",
            "OMI_JIT_QA_UID_ALLOWLIST": "vi7SA9ckQCe4ccobWNxlbdcNdC23",
            "KNOWLEDGE_LEDGER_DRAIN_ENABLED": "false",
            "KNOWLEDGE_LEDGER_DRAIN_UID_ALLOWLIST": "vi7SA9ckQCe4ccobWNxlbdcNdC23",
        }
        result = subprocess.run(
            ["bash", "-euo", "pipefail", "-c", step["run"]],
            cwd=root / "backend",
            env=environment,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr
        calls = (root / "python-calls").read_text(encoding="utf-8").splitlines()
        assert any("scripts/jit_qa_manual_operator.py --help" in call for call in calls)
        assert any("scripts/jit_qa_firestore_index_operator.py --help" in call for call in calls)


def test_seed_runtime_help_is_deferred_until_auth_and_secret_manager_resolution():
    step = _step("Verify seed runtime imports with the named QA secret")
    command = step["run"]
    assert "gcloud secrets versions access latest" in command
    assert "--secret=ENCRYPTION_SECRET" in command
    assert 'ENCRYPTION_SECRET="$(' in command
    assert 'export ENCRYPTION_SECRET="$(' not in command
    assert "export ENCRYPTION_SECRET" in command
    assert "jit_qa_seed_and_verify.py --help" in command
    assert "unset ENCRYPTION_SECRET" in command

    action_step = _step("Run read-only or seed operator action")
    action_command = action_step["run"]
    assert "gcloud secrets versions access latest" in action_command
    assert "jit_qa_seed_and_verify.py" in action_command
    assert "--secret=ENCRYPTION_SECRET" in action_command
    assert 'export ENCRYPTION_SECRET="$(' not in action_command
    assert "indexes-plan" in action_command
    assert "indexes-apply" in action_command

    drain_step = _step("Execute three bounded drain pages and verify durable proof")
    drain_command = drain_step["run"]
    assert 'ENCRYPTION_SECRET="$(' in drain_command
    assert 'export ENCRYPTION_SECRET="$(' not in drain_command
    assert "export ENCRYPTION_SECRET" in drain_command
    assert "unset ENCRYPTION_SECRET" in drain_command
    import_condition = step["if"]
    for operation in ("drain-verify", "rollforward"):
        assert f"inputs.operation == '{operation}'" in import_condition


def test_mutating_seed_step_executes_with_source_sha_and_sanitized_artifact_only():
    step = _step("Run read-only or seed operator action")
    assert "SOURCE_SHA" in step["env"]
    assert '"$operator_dir/artifacts/operator-receipt.json"' in step["run"]
    assert "unset FIRESTORE_EMULATOR_HOST SERVICE_ACCOUNT_JSON FIREBASE_AUTH_CREDENTIALS_PATH" in step["run"]
    assert "GOOGLE_APPLICATION_CREDENTIALS" not in step["run"].split("unset", 1)[1].split("\n", 1)[0]


def test_action_adc_is_retained_and_resolves_a_harmless_local_fixture_without_network(monkeypatch, tmp_path):
    auth_step = _step("Authenticate to the development project")
    assert auth_step["id"] == "auth"
    adc_step = _step("Verify action-provided development ADC")
    assert adc_step["env"]["ACTION_CREDENTIALS_PATH"] == "${{ steps.auth.outputs.credentials_file_path }}"
    drain_step = _step("Execute three bounded drain pages and verify durable proof")
    assert "unset FIRESTORE_EMULATOR_HOST SERVICE_ACCOUNT_JSON FIREBASE_AUTH_CREDENTIALS_PATH" in drain_step["run"]
    assert "GOOGLE_APPLICATION_CREDENTIALS" not in drain_step["run"].split("unset", 1)[1].split("\n", 1)[0]

    credentials_path = tmp_path / "authorized-user.json"
    credentials_path.write_text(
        json.dumps(
            {
                "type": "authorized_user",
                "client_id": "local-fixture.apps.googleusercontent.com",
                "client_secret": "local-fixture-secret",
                "refresh_token": "local-fixture-refresh-token",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", str(credentials_path))
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "based-hardware-dev")
    monkeypatch.delenv("SERVICE_ACCOUNT_JSON", raising=False)
    monkeypatch.delenv("FIREBASE_AUTH_CREDENTIALS_PATH", raising=False)
    from google.auth import default

    credentials, project = default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    assert credentials.__class__.__module__ == "google.oauth2.credentials"
    assert project == "based-hardware-dev"


def test_qa_provision_enables_only_the_fixed_development_redis_api_before_resource_creation():
    steps = _qa_cloud_steps()
    api_step = next(
        step
        for step in steps
        if step.get("name") == "Ensure named development Redis API is enabled before provisioning"
    )
    api_command = api_step["run"]
    redis_step = next(step for step in steps if step.get("name") == "Create or verify the 1 GiB Basic Redis dependency")
    assert 'service="redis.googleapis.com"' in api_command
    assert '--project "$QA_PROJECT"' in api_command
    assert "gcloud services list --enabled" in api_command
    assert "--filter=\"config.name=${service}\"" in api_command
    assert "timeout --foreground --kill-after=5s 60s gcloud services enable" in api_command
    assert steps.index(api_step) < steps.index(redis_step)
    redis_command = redis_step["run"]
    assert "gcloud redis instances create" in redis_command

    with TemporaryDirectory() as temporary:
        root = Path(temporary)
        fake_bin = root / "bin"
        fake_bin.mkdir()
        state = root / "state"
        state.write_text("disabled\n", encoding="utf-8")
        calls = root / "calls"
        (fake_bin / "gcloud").write_text(
            "#!/usr/bin/env bash\n"
            "set -euo pipefail\n"
            "printf '%s\\n' \"$*\" >> \"$CALLS\"\n"
            "if [[ \"${1:-}\" == services && \"${2:-}\" == list ]]; then\n"
            "  [[ \" $* \" != *\" --limit=1 \"* ]] || exit 0\n"
            "  [[ $(cat \"$STATE\") == enabled ]] && printf 'redis.googleapis.com\\n'; exit 0\n"
            "fi\n"
            "if [[ \"${1:-}\" == services && \"${2:-}\" == enable ]]; then "
            "printf 'enabled\\n' > \"$STATE\"; exit 0; fi\n"
            "echo \"unexpected gcloud command: $*\" >&2\n"
            "exit 2\n",
            encoding="utf-8",
        )
        (fake_bin / "gcloud").chmod(0o755)
        environment = {
            "PATH": f"{fake_bin}:{os.environ['PATH']}",
            "QA_PROJECT": "based-hardware-dev",
            "STATE": str(state),
            "CALLS": str(calls),
        }
        result = subprocess.run(
            ["bash", "-euo", "pipefail", "-c", api_command],
            env=environment,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr
        assert state.read_text(encoding="utf-8").strip() == "enabled"
        assert any(
            "services enable redis.googleapis.com" in line for line in calls.read_text(encoding="utf-8").splitlines()
        )

        calls.write_text("", encoding="utf-8")
        result = subprocess.run(
            ["bash", "-euo", "pipefail", "-c", api_command],
            env=environment,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr
        assert not any(
            "services enable redis.googleapis.com" in line for line in calls.read_text(encoding="utf-8").splitlines()
        )


def test_deployed_job_validation_uses_same_step_resolved_digest_before_github_env_propagation():
    step = _step("Verify the deployed immutable QA drain job")
    with TemporaryDirectory() as temporary:
        root = Path(temporary)
        fake_bin = root / "bin"
        fake_bin.mkdir()
        runner_temp = root / "runner-temp"
        (runner_temp / "jit-qa-operator").mkdir(parents=True)
        gcloud = fake_bin / "gcloud"
        gcloud.write_text(
            "#!/usr/bin/env bash\n"
            "set -euo pipefail\n"
            "if [[ \"${1:-}\" == container && \"${2:-}\" == images && \"${3:-}\" == describe ]]; then\n"
            "  printf 'sha256:%064d\\n' 7\n"
            "  exit 0\n"
            "fi\n"
            "if [[ \"${1:-}\" == run && \"${2:-}\" == jobs && \"${3:-}\" == describe ]]; then\n"
            "  printf '{}\\n'\n"
            "  exit 0\n"
            "fi\n"
            "echo \"unexpected gcloud command: $*\" >&2\n"
            "exit 2\n",
            encoding="utf-8",
        )
        gcloud.chmod(0o755)
        fake_python = fake_bin / "python"
        fake_python.write_text(
            "#!/usr/bin/env bash\n"
            "set -euo pipefail\n"
            "if [[ \"${1:-}\" == backend/scripts/jit_qa_manual_operator.py ]]; then\n"
            "  printf '%s\\n' \"$*\" > \"$PYTHON_CALL\"\n"
            "  printf '{}\\n'\n"
            "  exit 0\n"
            "fi\n"
            "echo \"unexpected python command: $*\" >&2\n"
            "exit 2\n",
            encoding="utf-8",
        )
        fake_python.chmod(0o755)
        environment = {
            "PATH": f"{fake_bin}:{os.environ['PATH']}",
            "RUNNER_TEMP": str(runner_temp),
            "GITHUB_ENV": str(root / "github-env"),
            "QA_PYTHON": str(fake_python),
            "QA_PROJECT": "based-hardware-dev",
            "QA_REGION": "us-central1",
            "QA_DRAIN_JOB": "knowledge-ledger-drain-qa-job",
            "SOURCE_SHA": "a" * 40,
            "PYTHON_CALL": str(root / "python-call"),
        }
        result = subprocess.run(
            ["bash", "-euo", "pipefail", "-c", step["run"]],
            env=environment,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr
        expected = "gcr.io/based-hardware-dev/knowledge-ledger-drain-qa-job@sha256:" + "0" * 63 + "7"
        assert f"QA_DRAIN_IMAGE={expected}" in (root / "github-env").read_text(encoding="utf-8")
        assert f"--expected-image {expected}" in (root / "python-call").read_text(encoding="utf-8")


def test_seed_bash_step_runs_with_fake_cli_and_cannot_lose_source_sha():
    step = _step("Run read-only or seed operator action")
    with TemporaryDirectory() as temporary:
        root = Path(temporary)
        runner_temp = root / "runner-temp"
        operator_dir = runner_temp / "jit-qa-operator"
        (operator_dir / "artifacts").mkdir(parents=True)
        (operator_dir / "source.json").write_text(
            '{"deployed_source_sha":"' + "a" * 40 + '","current_main_sha":"' + "b" * 40 + '"}',
            encoding="utf-8",
        )
        fake_bin = root / "bin"
        fake_bin.mkdir()
        (fake_bin / "gcloud").write_text(
            "#!/usr/bin/env bash\n"
            "set -euo pipefail\n"
            "if [[ ${1:-} == secrets && ${2:-} == versions && ${3:-} == access ]]; then\n"
            "  printf 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx\\n'\n"
            "  exit 0\n"
            "fi\n"
            "echo \"unexpected gcloud command: $*\" >&2\n"
            "exit 2\n",
            encoding="utf-8",
        )
        (fake_bin / "gcloud").chmod(0o755)
        fake_python = root / "fake-python"
        fake_python.write_text(
            "#!/usr/bin/env bash\n"
            "set -euo pipefail\n"
            "if [[ ${1:-} == backend/scripts/jit_qa_seed_and_verify.py ]]; then\n"
            "  echo '{\"result\":\"PASS\"}'\n"
            "  exit 0\n"
            "fi\n"
            "exec python3 \"$@\"\n",
            encoding="utf-8",
        )
        fake_python.chmod(0o755)
        environment = {
            "PATH": f"{fake_bin}:{os.environ['PATH']}",
            "RUNNER_TEMP": str(runner_temp),
            "QA_PYTHON": str(fake_python),
            "QA_PROJECT": "based-hardware-dev",
            "QA_DATABASE": "jit-qa",
            "QA_UID": "vi7SA9ckQCe4ccobWNxlbdcNdC23",
            "OPERATION": "inspect",
            "RUN_ID": "qa-proof-20260905",
            "CONFIRMATION": "",
            "SOURCE_SHA": "a" * 40,
            "GOOGLE_CLOUD_PROJECT": "based-hardware-dev",
            "GCLOUD_PROJECT": "based-hardware-dev",
            "OMI_ENV_STAGE": "dev",
            "OMI_FIRESTORE_DATA_PLANE_PROJECT": "based-hardware-dev",
            "FIRESTORE_DATABASE_ID": "jit-qa",
            "FIREBASE_AUTH_PROJECT_ID": "based-hardware",
            "MEMORY_ENABLED": "on",
            "OMI_JIT_QA_AUTH_ONLY": "true",
            "OMI_JIT_QA_UID_ALLOWLIST": "vi7SA9ckQCe4ccobWNxlbdcNdC23",
            "KNOWLEDGE_LEDGER_DRAIN_ENABLED": "false",
            "KNOWLEDGE_LEDGER_DRAIN_UID_ALLOWLIST": "vi7SA9ckQCe4ccobWNxlbdcNdC23",
        }
        result = subprocess.run(
            ["bash", "-euo", "pipefail", "-c", step["run"]],
            cwd=root,
            env=environment,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr
        receipt = json.loads((operator_dir / "artifacts" / "operator-receipt.json").read_text(encoding="utf-8"))
        assert receipt["source_sha"] == "a" * 40
        assert not (operator_dir / "operation.json").exists()
        assert [path.name for path in (operator_dir / "artifacts").iterdir()] == ["operator-receipt.json"]
