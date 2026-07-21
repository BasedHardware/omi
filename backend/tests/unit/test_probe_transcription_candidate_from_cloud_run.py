from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/probe-transcription-candidate-from-cloud-run.sh"


def test_ephemeral_probe_uses_bounded_deterministic_resource_ids(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log_path = tmp_path / "gcloud.log"
    fake_gcloud = bin_dir / "gcloud"
    fake_gcloud.write_text('#!/usr/bin/env bash\nprintf \'%s\\n\' "$*" >> "$GCLOUD_LOG"\n', encoding="utf-8")
    fake_gcloud.chmod(0o755)
    token_file = tmp_path / "firebase-token"
    token_file.write_text("fixture-token", encoding="utf-8")
    env = os.environ | {"PATH": f"{bin_dir}:{os.environ['PATH']}", "GCLOUD_LOG": str(log_path)}

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

    assert result.returncode == 0, result.stderr
    calls = log_path.read_text(encoding="utf-8").splitlines()
    create = next(line for line in calls if line.startswith("iam service-accounts create "))
    account_id = create.split()[3]
    assert re.fullmatch(r"bcp-[0-9a-f]{20}", account_id)
    assert 6 <= len(account_id) <= 30
    deploy = next(line for line in calls if line.startswith("run jobs deploy "))
    assert re.search(r"run jobs deploy backend-candidate-vpc-probe-[0-9a-f]{20}(?: |$)", deploy)
