"""Tests for metadata-only pusher ConfigMap/Secret deployment preflight."""

from __future__ import annotations

from pathlib import Path
import runpy
from types import SimpleNamespace

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "verify_pusher_config_references.py"


@pytest.fixture
def preflight() -> SimpleNamespace:
    return SimpleNamespace(**runpy.run_path(str(SCRIPT)))


def deployment(refs: list[dict]) -> list[dict]:
    return [{"kind": "Deployment", "spec": {"template": {"spec": {"containers": [{"envFrom": refs}]}}}}]


def test_extracts_object_names_without_values(preflight: SimpleNamespace):
    refs = preflight.references({"env": [{"valueFrom": {"secretKeyRef": {"name": "safe-name", "key": "KEY"}}}]})
    assert refs == {("secret", "safe-name")}


def test_rejects_missing_required_configmap_fixture(monkeypatch, preflight: SimpleNamespace):
    monkeypatch.setitem(
        preflight.pusher_references.__globals__,
        "render",
        lambda _env: deployment([{"secretRef": {"name": "dev-omi-backend-secrets"}}]),
    )
    with pytest.raises(RuntimeError, match="configmap/dev-omi-backend-config"):
        preflight.pusher_references("dev")


def test_accepts_expected_dev_reference_fixture(monkeypatch, preflight: SimpleNamespace):
    monkeypatch.setitem(
        preflight.pusher_references.__globals__,
        "render",
        lambda _env: deployment(
            [
                {"configMapRef": {"name": "dev-omi-backend-config"}},
                {"secretRef": {"name": "dev-omi-backend-secrets"}},
            ]
        ),
    )
    assert preflight.pusher_references("dev") == {
        ("configmap", "dev-omi-backend-config"),
        ("secret", "dev-omi-backend-secrets"),
    }
