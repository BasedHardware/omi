"""Regression tests for backend-listen Helm env identity defaults (#9552)."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]
CHART_DIR = ROOT / "backend" / "charts" / "backend-listen"

ENV_IDENTITY_DEFAULTS = {
    "prod": {
        "values_file": CHART_DIR / "prod_omi_backend_listen_values.yaml",
        "image_repository": "gcr.io/based-hardware/backend",
        "gcp_project_id": "based-hardware",
        "runtime_gcp_project_id": "based-hardware",
    },
    "dev": {
        "values_file": CHART_DIR / "dev_omi_backend_listen_values.yaml",
        "image_repository": "gcr.io/based-hardware-dev/backend",
        "gcp_project_id": "based-hardware-dev",
        "runtime_gcp_project_id": "based-hardware-dev",
    },
}


def _load_values(path: Path) -> dict:
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    return loaded if isinstance(loaded, dict) else {}


def _env_value(values: dict, name: str) -> str | None:
    for entry in values.get("env", []) or []:
        if isinstance(entry, dict) and entry.get("name") == name and "value" in entry:
            return str(entry["value"])
    return None


@pytest.mark.parametrize("env_name", ["prod", "dev"])
def test_backend_listen_values_have_env_identity_defaults(env_name: str):
    expected = ENV_IDENTITY_DEFAULTS[env_name]
    values = _load_values(expected["values_file"])

    assert values["image"]["repository"] == expected["image_repository"]
    assert values["gcpProjectId"] == expected["gcp_project_id"]
    assert values["runtimeGcpProjectId"] == expected["runtime_gcp_project_id"]
    assert _env_value(values, "GOOGLE_CLOUD_PROJECT") == expected["runtime_gcp_project_id"]


@pytest.mark.parametrize("env_name", ["prod", "dev"])
def test_backend_listen_helm_template_uses_runtime_project_for_google_cloud_project(env_name: str):
    helm = shutil.which("helm")
    if helm is None:
        pytest.skip("helm is not installed")

    expected = ENV_IDENTITY_DEFAULTS[env_name]
    rendered = subprocess.run(
        [
            helm,
            "template",
            "backend-listen",
            str(CHART_DIR),
            "-f",
            str(expected["values_file"]),
            "--set-string",
            "image.tag=abc1234",
        ],
        check=True,
        capture_output=True,
        text=True,
    ).stdout

    assert f'name: GOOGLE_CLOUD_PROJECT\n              value: "{expected["runtime_gcp_project_id"]}"' in rendered
    assert f'image: "{expected["image_repository"]}:abc1234"' in rendered


def test_backend_listen_helm_template_requires_image_tag():
    helm = shutil.which("helm")
    if helm is None:
        pytest.skip("helm is not installed")

    result = subprocess.run(
        [
            helm,
            "template",
            "backend-listen",
            str(CHART_DIR),
            "-f",
            str(ENV_IDENTITY_DEFAULTS["prod"]["values_file"]),
        ],
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "image.tag is required" in result.stderr
