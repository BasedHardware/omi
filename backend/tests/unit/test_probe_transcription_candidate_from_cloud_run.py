from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/probe-transcription-candidate-from-cloud-run.sh"


def _fake_gcloud(bin_dir: Path) -> Path:
    fake_gcloud = bin_dir / "gcloud"
    fake_gcloud.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
printf '%s\\n' "$*" >> "$GCLOUD_LOG"

if [[ "$*" == "compute networks subnets describe "* ]]; then
  printf '%s\\n' "${PRIVATE_GOOGLE_ACCESS:-True}"
  exit 0
fi

if [[ -n "${GCLOUD_FAIL_COMMAND:-}" && "$*" == "$GCLOUD_FAIL_COMMAND"* ]]; then
  exit 42
fi
""",
        encoding="utf-8",
    )
    fake_gcloud.chmod(0o755)
    return fake_gcloud


def _run_probe(tmp_path: Path, **env_overrides: str) -> tuple[subprocess.CompletedProcess[str], list[str]]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(parents=True)
    log_path = tmp_path / "gcloud.log"
    _fake_gcloud(bin_dir)
    token_file = tmp_path / "firebase-token"
    token_file.write_text("fixture-token", encoding="utf-8")
    env = os.environ | {"PATH": f"{bin_dir}:{os.environ['PATH']}", "GCLOUD_LOG": str(log_path)} | env_overrides

    suffix = "29797736699-123456789"
    result = subprocess.run(
        [
            "bash",
            str(SCRIPT),
            "--project",
            "example-project",
            "--region",
            "us-central1",
            "--image",
            "example.invalid/backend:abc123",
            "--candidate-url",
            "https://candidate.example.invalid",
            "--identity-audience",
            "https://backend.example.invalid",
            "--network",
            "default",
            "--subnet",
            "default",
            "--firebase-token-file",
            str(token_file),
            "--name-suffix",
            suffix,
        ],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    calls = log_path.read_text(encoding="utf-8").splitlines()
    return result, calls


def test_ephemeral_probe_uses_bounded_deterministic_resource_ids_and_all_traffic(tmp_path):
    result, calls = _run_probe(tmp_path)

    assert result.returncode == 0, result.stderr
    create = next(line for line in calls if line.startswith("iam service-accounts create "))
    account_id = create.split()[3]
    assert re.fullmatch(r"bcp-[0-9a-f]{20}", account_id)
    assert 6 <= len(account_id) <= 30
    deploy = next(line for line in calls if line.startswith("run jobs deploy "))
    assert re.search(r"run jobs deploy backend-candidate-vpc-probe-[0-9a-f]{20}(?: |$)", deploy)
    assert "--vpc-egress=all-traffic" in deploy


def test_probe_refuses_to_create_resources_without_private_google_access(tmp_path):
    result, calls = _run_probe(tmp_path, PRIVATE_GOOGLE_ACCESS="False")

    assert result.returncode != 0
    assert "Private Google Access" in result.stderr
    assert calls == [
        "compute networks subnets describe default --project=example-project --region=us-central1 "
        "--format=value(privateIpGoogleAccess)"
    ]


def test_probe_cleanup_removes_every_created_resource_at_each_failure_boundary(tmp_path):
    failures = {
        "after_service_account": "run services add-iam-policy-binding backend",
        "after_iam_binding": "run jobs deploy ",
        "after_job_deployment": "run jobs execute ",
    }
    cleanup = (
        "run jobs delete ",
        "run services remove-iam-policy-binding backend",
        "iam service-accounts delete ",
    )

    for boundary, command in failures.items():
        result, calls = _run_probe(tmp_path / boundary, GCLOUD_FAIL_COMMAND=command)

        assert result.returncode == 42, boundary
        failure_index = next(index for index, call in enumerate(calls) if call.startswith(command))
        assert all(
            any(call.startswith(expected) for call in calls[failure_index + 1 :]) for expected in cleanup
        ), boundary
        if boundary == "after_service_account":
            assert not any(call.startswith("run jobs deploy ") for call in calls[:failure_index])
        elif boundary == "after_iam_binding":
            assert any(call.startswith("run services add-iam-policy-binding backend") for call in calls[:failure_index])
        else:
            assert any(call.startswith("run jobs deploy ") for call in calls[:failure_index])
