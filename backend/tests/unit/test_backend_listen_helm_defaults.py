"""Regression tests for backend-listen Helm env identity defaults (#9552)."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

from config.stt_provider_policy import DEFAULT_MODELS_BY_SURFACE, STTServingSurface

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

# The chart must serve exactly the policy-owned default routes; deriving the
# expected literals from the policy keeps this guard from drifting when the
# serving order changes there.
SAFE_STREAMING_ROUTE = ','.join(DEFAULT_MODELS_BY_SURFACE[STTServingSurface.STREAMING])
SAFE_PRERECORDED_ROUTE = ','.join(DEFAULT_MODELS_BY_SURFACE[STTServingSurface.PRERECORDED])


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


def test_dev_parity_pack_emptydir_is_writable_by_the_non_root_backend_image():
    """The capture root is an emptyDir, so its pod group must match the image group."""
    values = _load_values(ENV_IDENTITY_DEFAULTS["dev"]["values_file"])
    dockerfile = (ROOT / "backend" / "Dockerfile").read_text(encoding="utf-8")
    deployment_template = (CHART_DIR / "templates" / "deployment.yaml").read_text(encoding="utf-8")
    assert "groupadd --system --gid 10001 omi" in dockerfile
    assert "USER omi" in dockerfile
    assert "with .Values.podSecurityContext" in deployment_template
    assert values["podSecurityContext"] == {
        "fsGroup": 10001,
        "fsGroupChangePolicy": "OnRootMismatch",
    }
    assert {volume["name"] for volume in values["volumes"]} >= {"parity-pack"}
    assert {(mount["name"], mount["mountPath"]) for mount in values["volumeMounts"]} >= {
        ("parity-pack", "/var/omi-parity-pack")
    }
    assert _env_value(values, "OMI_PARITY_PACK_ROOT") == "/var/omi-parity-pack"


def test_prod_values_serve_the_policy_owned_stt_routes():
    values = _load_values(ENV_IDENTITY_DEFAULTS['prod']['values_file'])

    assert _env_value(values, 'STT_SERVICE_MODELS') == SAFE_STREAMING_ROUTE
    assert _env_value(values, 'STT_PRERECORDED_MODEL') == SAFE_PRERECORDED_ROUTE


def test_rendered_prod_deployment_cannot_restore_parakeet_first_streaming():
    helm = shutil.which('helm')
    if helm is None:
        pytest.skip('helm is not installed')

    rendered = subprocess.run(
        [
            helm,
            'template',
            'backend-listen',
            str(CHART_DIR),
            '-f',
            str(ENV_IDENTITY_DEFAULTS['prod']['values_file']),
            '--set-string',
            'image.tag=abc1234',
        ],
        check=True,
        capture_output=True,
        text=True,
    ).stdout

    assert f'name: STT_SERVICE_MODELS\n              value: "{SAFE_STREAMING_ROUTE}"' in rendered
    # Scoped to the streaming key: the same literal is the intended batch route, so a
    # blanket check would forbid the pre-recorded default as collateral.
    assert f'name: STT_SERVICE_MODELS\n              value: "{SAFE_PRERECORDED_ROUTE}"' not in rendered
    assert f'name: STT_PRERECORDED_MODEL\n              value: "{SAFE_PRERECORDED_ROUTE}"' in rendered
