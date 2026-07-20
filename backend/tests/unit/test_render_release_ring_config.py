from __future__ import annotations

import importlib.util
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[2] / "scripts" / "render_release_ring_config.py"
SPEC = importlib.util.spec_from_file_location("render_release_ring_config", MODULE_PATH)
assert SPEC and SPEC.loader
renderer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(renderer)


def test_beta_renderer_changes_stateless_identity_but_not_gpu_endpoint() -> None:
    rendered = renderer.render(
        {
            "namespace": "prod-omi-backend",
            "env": [{"name": "OMI_ENV_STAGE", "value": "prod"}],
            "pusher": "http://pusher.omi.me",
            "gpu": "http://parakeet.omi.me",
        },
        ring="beta",
    )

    assert rendered["namespace"] == "beta-omi-backend"
    assert rendered["env"][0]["value"] == "beta"
    assert rendered["pusher"] == "http://pusher-beta.omi.me"
    assert rendered["gpu"] == "http://parakeet.omi.me"


def test_prod_renderer_is_identity() -> None:
    source = {"namespace": "prod-omi-backend", "value": "prod"}

    assert renderer.render(source, ring="prod") is source


def test_beta_renderer_rewrites_ingress_resources_and_materializes_beta_runtime_lane() -> None:
    rendered = renderer.render_manifest(
        {
            "environments": {"prod": {"cloud_run": {"services": {"backend": {}}}}},
            "ingress": "prod-pusher-ilb-ip-address prod-agent-proxy-ip-address agent-proxy-cert",
        },
        ring="beta",
    )

    assert set(rendered["environments"]) == {"beta"}
    assert "beta-pusher-ilb-ip-address" in rendered["ingress"]
    assert "beta-agent-proxy-ip-address" in rendered["ingress"]
    assert "beta-agent-proxy-cert" in rendered["ingress"]
