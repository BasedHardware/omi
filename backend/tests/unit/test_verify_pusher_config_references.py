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


def test_extracts_object_and_key_names_without_values(preflight: SimpleNamespace):
    refs = preflight.references({"env": [{"valueFrom": {"secretKeyRef": {"name": "safe-name", "key": "KEY"}}}]})
    assert refs == {("secret", "safe-name", "KEY")}


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
        ("configmap", "dev-omi-backend-config", None),
        ("secret", "dev-omi-backend-secrets", None),
    }


@pytest.mark.parametrize(
    ("environment", "expected"),
    [
        ("dev", ("configmap", "dev-omi-backend-config", "REDIS_DB_HOST")),
        ("prod", ("configmap", "prod-omi-backend-config", "REDIS_DB_HOST")),
    ],
)
def test_rendered_pusher_values_reference_configured_redis_host_key(
    preflight: SimpleNamespace, environment: str, expected: tuple[str, str, str]
):
    assert expected in preflight.pusher_references(environment)


@pytest.mark.parametrize("kind", ["configmap", "secret"])
def test_rejects_missing_referenced_key_without_reading_values(monkeypatch, preflight: SimpleNamespace, kind: str):
    calls: list[list[str]] = []

    def fake_run(argv, **_kwargs):
        calls.append(argv)
        if "go-template={{range $key, $_ := .data}}{{$key}}{{\"\\n\"}}{{end}}" in argv:
            return SimpleNamespace(returncode=0, stdout="OTHER_KEY\n", stderr="")
        return SimpleNamespace(returncode=0, stdout=f"{kind}/safe-name\n", stderr="")

    monkeypatch.setattr(preflight.subprocess, "run", fake_run)
    failures = preflight.verify("safe-ns", {(kind, "safe-name", "REQUIRED_KEY")})
    assert failures == [f"required {kind}/safe-name key REQUIRED_KEY unavailable"]
    assert all("REQUIRED_KEY" not in call[-1] for call in calls)


def test_accepts_referenced_secret_key_from_key_only_output(monkeypatch, preflight: SimpleNamespace):
    def fake_run(argv, **_kwargs):
        if "go-template={{range $key, $_ := .data}}{{$key}}{{\"\\n\"}}{{end}}" in argv:
            return SimpleNamespace(returncode=0, stdout="REQUIRED_KEY\n", stderr="")
        return SimpleNamespace(returncode=0, stdout="secret/safe-name\n", stderr="")

    monkeypatch.setattr(preflight.subprocess, "run", fake_run)
    assert preflight.verify("safe-ns", {("secret", "safe-name", "REQUIRED_KEY")}) == []
