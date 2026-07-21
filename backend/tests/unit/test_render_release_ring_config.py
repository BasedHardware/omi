from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

MODULE_PATH = Path(__file__).resolve().parents[2] / "scripts" / "render_release_ring_config.py"
SPEC = importlib.util.spec_from_file_location("render_release_ring_config", MODULE_PATH)
assert SPEC and SPEC.loader
renderer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(renderer)


def test_production_renderer_is_identity() -> None:
    source = {"namespace": "prod-omi-backend", "value": "prod"}

    assert renderer.render(source, ring="prod") is source


def test_renderer_rejects_retired_backend_ring() -> None:
    with pytest.raises(ValueError, match="unsupported backend deploy target"):
        renderer.render({"namespace": "prod-omi-backend"}, ring="beta")
