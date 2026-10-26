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

# Keep these deployed routes as ordered subsets of the broader policy; the
# unused Deepgram provider stays available in code but is absent from runtime lists.
DEV_CANARY_STREAMING_ROUTE = 'parakeet-window,modulate-velma-2,soniox'
# Soniox-first was rolled back on 2026-10-02: a Parakeet failover replays its
# ring into Soniox's bounded send queue, which overflowed and ended the session.
CANARY_STREAMING_ROUTE = 'parakeet-window,modulate-velma-2,soniox'
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
    assert 'name: OMI_FIRESTORE_DATA_PLANE_PROJECT\n              value: "based-hardware"' in rendered
    assert 'name: POSTHOG_PROJECT_API_KEY' in rendered
    if env_name == 'prod':
        token = _env_value(_load_values(expected['values_file']), 'POSTHOG_PRODUCT_CAPTURE_TOKEN')
        assert token and f'name: POSTHOG_PRODUCT_CAPTURE_TOKEN\n              value: "{token}"' in rendered
    assert f'image: "{expected["image_repository"]}:abc1234"' in rendered
    assert _env_value(_load_values(expected["values_file"]), "TRANSLATION_CACHE_TTL") == "86400"
    assert _env_value(_load_values(expected["values_file"]), "TRANSLATION_NEGATIVE_CACHE_TTL") == "21600"
    assert 'name: TRANSLATION_CACHE_TTL\n              value: "86400"' in rendered
    assert 'name: TRANSLATION_NEGATIVE_CACHE_TTL\n              value: "21600"' in rendered


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


@pytest.mark.parametrize("chart", ["backend-listen", "llm-gateway"])
def test_role_image_digest_opt_in_renders_repository_at_digest(chart: str):
    """Plan B B2: deploy-backend-stack service_images sets image.digest; image.tag stays the build identity."""
    helm = shutil.which("helm")
    if helm is None:
        pytest.skip("helm is not installed")
    chart_dir = ROOT / "backend" / "charts" / chart
    values = chart_dir / (
        "prod_omi_backend_listen_values.yaml" if chart == "backend-listen" else "prod_omi_llm_gateway_values.yaml"
    )
    digest = "sha256:" + "c" * 64
    rendered = subprocess.run(
        [
            helm,
            "template",
            chart,
            str(chart_dir),
            "-f",
            str(values),
            "--set",
            "image.repository=gcr.io/based-hardware/backend-role",
            "--set-string",
            f"image.digest={digest}",
            "--set-string",
            "image.tag=abc1234",
        ],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    assert f'image: "gcr.io/based-hardware/backend-role@{digest}"' in rendered
    assert ':abc1234"' not in rendered


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

    assert _env_value(values, 'STT_SERVICE_MODELS') == CANARY_STREAMING_ROUTE
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

    assert f'name: STT_SERVICE_MODELS\n              value: "{CANARY_STREAMING_ROUTE}"' in rendered
    # Scoped to the streaming key: the same literal is the intended batch route, so a
    # blanket check would forbid the pre-recorded default as collateral.
    assert f'name: STT_SERVICE_MODELS\n              value: "{SAFE_PRERECORDED_ROUTE}"' not in rendered
    assert f'name: STT_PRERECORDED_MODEL\n              value: "{SAFE_PRERECORDED_ROUTE}"' in rendered


def test_windowed_live_rollout_is_prod_canary_and_bounded():
    """July overload: changing order must never silently turn on unbounded TDT."""
    prod = _load_values(ENV_IDENTITY_DEFAULTS['prod']['values_file'])
    dev = _load_values(ENV_IDENTITY_DEFAULTS['dev']['values_file'])
    # Prod connects in configured order since the 2026-09-26 Modulate incident
    # (#19069) so Soniox backs Modulate; the guard that matters is that the
    # windowed TDT leg stays on a reviewed step of the approved ramp
    # (David, 2026-09-29), and the chart agrees with the prod runtime overlay.
    assert _env_value(prod, 'STT_CONNECT_ORDER_FROM_CONFIG') is None
    prod_allocation = _env_value(prod, 'PARAKEET_WINDOW_ALLOCATION_PERCENT')
    assert prod_allocation in {'0', '1', '2', '5', '25', '50', '100'}
    overlay = yaml.safe_load(
        (Path(__file__).resolve().parents[2] / 'deploy' / 'runtime_env' / 'prod.overlay.yaml').read_text(
            encoding='utf-8'
        )
    )
    listen_env = overlay['overlay']['gke']['backend-listen']['env']
    assert str(listen_env['PARAKEET_WINDOW_ALLOCATION_PERCENT']['value']) == prod_allocation
    assert (
        _env_value(prod, 'PARAKEET_BATCH_PRESSURE_POOL_HOST')
        == 'prod-omi-parakeet-headless.prod-omi-backend.svc.cluster.local'
    )
    assert _env_value(prod, 'PARAKEET_BATCH_PRESSURE_MIN_REPLICAS') == '3'
    assert _env_value(dev, 'STT_CONNECT_ORDER_FROM_CONFIG') is None
    assert _env_value(dev, 'PARAKEET_WINDOW_ALLOCATION_PERCENT') == '1'
    assert (
        _env_value(dev, 'PARAKEET_BATCH_PRESSURE_POOL_HOST')
        == 'dev-omi-parakeet-headless.dev-omi-backend.svc.cluster.local'
    )
    assert _env_value(dev, 'PARAKEET_BATCH_PRESSURE_MIN_REPLICAS') == '1'
    assert _env_value(dev, 'STT_SERVICE_MODELS') == DEV_CANARY_STREAMING_ROUTE
    assert _env_value(prod, 'STT_SERVICE_MODELS') == CANARY_STREAMING_ROUTE
    assert listen_env['STT_SERVICE_MODELS']['value'] == CANARY_STREAMING_ROUTE
    assert overlay['overlay']['gke']['config_map']['entries']['STT_SERVICE_MODELS']['value'] == CANARY_STREAMING_ROUTE
    assert _env_value(prod, 'PARAKEET_WINDOW_MAX_SESSIONS') == '16'

    assert _env_value(prod, 'PARAKEET_WINDOW_FIRST_TEXT_DEADLINE_SECONDS') == '12'
    assert _env_value(prod, 'PARAKEET_WINDOW_MAX_EMPTY_STREAK') == '4'
    assert _env_value(dev, 'PARAKEET_WINDOW_MAX_SESSIONS') == '1'
    for values in (prod, dev):
        assert _env_value(values, 'PARAKEET_WINDOW_DIARIZATION') == 'false'
        assert _env_value(values, 'PARAKEET_WINDOW_PACE_SECONDS') == '6'
        assert _env_value(values, 'PARAKEET_WINDOW_MAX_CONTEXT_SECONDS') == '24'
        assert _env_value(values, 'STT_CIRCUIT_HALF_OPEN_PROBES') == '1'


def test_prod_listen_hpa_scales_on_cpu_with_socket_guards():
    """D0b: CPU drives listen scaling; socket metrics stay as a floor against stranding."""
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
    hpa = next(
        doc
        for doc in yaml.safe_load_all(rendered)
        if isinstance(doc, dict) and doc.get('kind') == 'HorizontalPodAutoscaler'
    )
    metrics = hpa['spec']['metrics']
    cpu = [m['resource']['target'] for m in metrics if m['type'] == 'Resource' and m['resource']['name'] == 'cpu']
    external = {
        m['external']['metric']['name']: m['external']['target']['value'] for m in metrics if m['type'] == 'External'
    }

    # HPA ignores ratios within 10% of target; on 2026-10-19 mean listen CPU
    # peaked at 0.56-0.65 while hot pods saturated, so a target at or above 60%
    # could not have scaled out of that incident.
    assert cpu == [{'type': 'Utilization', 'averageUtilization': 55}]
    # Dropping a socket guard, or raising it until it never binds, lets a CPU
    # dip strand live sockets on too few pods. Changing these is a reviewed retune.
    assert external == {
        'backend_listen_requests_per_pod': 16,
        'backend_listen_active_ws_connections_per_pod': 35,
    }
    # 2026-10-24 right-sizing: the night fleet needs only ~31 pods at the 55%
    # target, so the floor returns to its pre-#22623 value of 30; the peak
    # path (max 60, requests, guards) is unchanged.
    assert (hpa['spec']['minReplicas'], hpa['spec']['maxReplicas']) == (30, 60)
