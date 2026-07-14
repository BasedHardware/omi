"""Tests for metadata-only pusher ConfigMap/Secret deployment preflight."""

from __future__ import annotations

from pathlib import Path
import runpy
import shutil
import subprocess
import textwrap
from types import SimpleNamespace

import pytest
import yaml

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


def test_rendered_dev_pusher_redis_host_clears_legacy_secret_source(preflight: SimpleNamespace):
    environment = "dev"
    deployment = next(document for document in preflight.render(environment) if document.get("kind") == "Deployment")
    env = deployment["spec"]["template"]["spec"]["containers"][0]["env"]
    redis_host = next(item for item in env if item["name"] == "REDIS_DB_HOST")
    redis_password = next(item for item in env if item["name"] == "REDIS_DB_PASSWORD")

    assert redis_host["valueFrom"] == {
        "configMapKeyRef": {"name": f"{environment}-omi-backend-config", "key": "REDIS_DB_HOST"},
        "secretKeyRef": None,
    }
    assert redis_password["valueFrom"] == {
        "secretKeyRef": {"name": f"{environment}-omi-backend-secrets", "key": "REDIS_DB_PASSWORD"}
    }


@pytest.mark.skipif(shutil.which("kubectl") is None, reason="kubectl is required for the local strategic-merge fixture")
def test_historical_secret_redis_host_upgrade_uses_kubernetes_strategic_merge(
    tmp_path: Path, preflight: SimpleNamespace
):
    """Exercise Kubernetes' named-env strategic merge behavior without a cluster.

    Helm emits the new REDIS_DB_HOST item for the release update. The fixture
    starts with the historical live Secret source and applies that item through
    Kustomize's Kubernetes strategic-merge implementation. Without an explicit
    null, the nested valueFrom map retains the Secret source and matches the
    failed live validation. The explicit null removes it while retaining the
    ConfigMap source.
    """

    base = tmp_path / "base"
    base.mkdir()
    (base / "kustomization.yaml").write_text("resources:\n  - deployment.yaml\n")
    (base / "deployment.yaml").write_text(textwrap.dedent("""\
            apiVersion: apps/v1
            kind: Deployment
            metadata:
              name: pusher
            spec:
              selector:
                matchLabels:
                  app: pusher
              template:
                metadata:
                  labels:
                    app: pusher
                spec:
                  containers:
                    - name: pusher
                      image: example/pusher
                      env:
                        - name: REDIS_DB_HOST
                          valueFrom:
                            secretKeyRef:
                              name: dev-omi-backend-secrets
                              key: REDIS_DB_HOST
            """))

    def render(value_from: str) -> dict:
        overlay = tmp_path / f"overlay-{len(list(tmp_path.glob('overlay-*')))}"
        overlay.mkdir()
        strategic_patch = textwrap.dedent("""\
            apiVersion: apps/v1
            kind: Deployment
            metadata:
              name: pusher
            spec:
              template:
                spec:
                  containers:
                    - name: pusher
                      env:
                        - name: REDIS_DB_HOST
                          valueFrom:
            """)
        strategic_patch += textwrap.indent(value_from, " " * 16)
        kustomization = textwrap.dedent("""\
            resources:
              - ../base
            patches:
              - target:
                  kind: Deployment
                  name: pusher
                patch: |-
            """)
        (overlay / "kustomization.yaml").write_text(kustomization + textwrap.indent(strategic_patch, " " * 6))
        result = subprocess.run(["kubectl", "kustomize", str(overlay)], check=True, capture_output=True, text=True)
        return yaml.safe_load(result.stdout)

    broken = render("""\
configMapKeyRef:
  name: dev-omi-backend-config
  key: REDIS_DB_HOST
""")
    broken_value_from = broken["spec"]["template"]["spec"]["containers"][0]["env"][0]["valueFrom"]
    assert set(broken_value_from) == {"configMapKeyRef", "secretKeyRef"}

    rendered_deployment = next(document for document in preflight.render("dev") if document.get("kind") == "Deployment")
    rendered_env = rendered_deployment["spec"]["template"]["spec"]["containers"][0]["env"]
    rendered_redis_host = next(item for item in rendered_env if item["name"] == "REDIS_DB_HOST")
    fixed = render(yaml.safe_dump(rendered_redis_host["valueFrom"], sort_keys=False))
    fixed_value_from = fixed["spec"]["template"]["spec"]["containers"][0]["env"][0]["valueFrom"]
    assert fixed_value_from == {"configMapKeyRef": {"name": "dev-omi-backend-config", "key": "REDIS_DB_HOST"}}


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
