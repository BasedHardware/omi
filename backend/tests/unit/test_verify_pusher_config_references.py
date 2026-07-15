"""Tests for metadata-only pusher ConfigMap/Secret deployment preflight."""

from __future__ import annotations

import copy
import json
from pathlib import Path
import runpy
import shutil
import subprocess
import textwrap
from types import SimpleNamespace

import pytest
import yaml

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "verify_pusher_config_references.py"
CLASSIFICATION = SCRIPT.parents[2] / "config" / "deployment-setting-classification.json"


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


def test_rendered_dev_pusher_google_client_id_clears_legacy_secret_source(preflight: SimpleNamespace):
    environment = "dev"
    deployment = next(document for document in preflight.render(environment) if document.get("kind") == "Deployment")
    env = deployment["spec"]["template"]["spec"]["containers"][0]["env"]
    google_client_id = next(item for item in env if item["name"] == "GOOGLE_CLIENT_ID")
    google_client_secret = next(item for item in env if item["name"] == "GOOGLE_CLIENT_SECRET")

    assert google_client_id["valueFrom"] == {
        "configMapKeyRef": {"name": f"{environment}-omi-backend-config", "key": "GOOGLE_CLIENT_ID"},
        "secretKeyRef": None,
    }
    assert google_client_secret["valueFrom"] == {
        "secretKeyRef": {"name": f"{environment}-omi-backend-secrets", "key": "GOOGLE_CLIENT_SECRET"}
    }


@pytest.mark.parametrize("environment", ["dev", "prod"])
def test_rendered_pusher_typesense_host_clears_legacy_secret_source(preflight: SimpleNamespace, environment: str):
    deployment = next(document for document in preflight.render(environment) if document.get("kind") == "Deployment")
    env = deployment["spec"]["template"]["spec"]["containers"][0]["env"]
    typesense_host = next(item for item in env if item["name"] == "TYPESENSE_HOST")
    typesense_api_key = next(item for item in env if item["name"] == "TYPESENSE_API_KEY")

    assert typesense_host["valueFrom"] == {
        "configMapKeyRef": {"name": f"{environment}-omi-backend-config", "key": "TYPESENSE_HOST"},
        "secretKeyRef": None,
    }
    assert typesense_api_key["valueFrom"] == {
        "secretKeyRef": {"name": f"{environment}-omi-backend-secrets", "key": "TYPESENSE_API_KEY"}
    }


def test_typesense_and_google_binding_classifications_are_explicit():
    kinds = json.loads(CLASSIFICATION.read_text(encoding="utf-8"))["kinds"]

    assert "TYPESENSE_HOST" in kinds["config"]
    assert {"TYPESENSE_API_KEY", "GOOGLE_CLIENT_SECRET"}.issubset(kinds["secret"])


def test_rendered_dev_pusher_direct_bindings_match_source_contract(preflight: SimpleNamespace):
    deployment = preflight.rendered_pusher_deployment("dev")
    expected, clear_historical_secret = preflight.dev_pusher_binding_contract()

    assert preflight.direct_pusher_bindings(deployment) == expected
    assert clear_historical_secret == {"REDIS_DB_HOST", "GOOGLE_CLIENT_ID", "TYPESENSE_HOST"}
    assert preflight.validate_dev_pusher_binding_contract(deployment) == []


def test_dev_pusher_contract_requires_typesense_host_secret_clear(preflight: SimpleNamespace):
    deployment = copy.deepcopy(preflight.rendered_pusher_deployment("dev"))
    env = deployment["spec"]["template"]["spec"]["containers"][0]["env"]
    typesense_host = next(item for item in env if item["name"] == "TYPESENSE_HOST")
    del typesense_host["valueFrom"]["secretKeyRef"]

    assert preflight.validate_dev_pusher_binding_contract(deployment) == [
        "dev pusher binding contract must clear historical Secret source for TYPESENSE_HOST"
    ]


@pytest.mark.skipif(shutil.which("kubectl") is None, reason="kubectl is required for the local strategic-merge fixture")
@pytest.mark.parametrize("env_name", ["REDIS_DB_HOST", "GOOGLE_CLIENT_ID", "TYPESENSE_HOST"])
def test_historical_secret_named_env_upgrade_uses_kubernetes_strategic_merge(
    tmp_path: Path, preflight: SimpleNamespace, env_name: str
):
    """Exercise Kubernetes' named-env strategic merge behavior without a cluster.

    Helm emits the new named env item for the release update. The fixture starts
    with the historical live Secret source and applies that item through
    Kustomize's Kubernetes strategic-merge implementation. Without an explicit
    null, the nested valueFrom map retains the Secret source and produces the
    invalid dual-source representation. The explicit null removes it while
    retaining the ConfigMap source.
    """

    base = tmp_path / "base"
    base.mkdir()
    (base / "kustomization.yaml").write_text("resources:\n  - deployment.yaml\n")
    (base / "deployment.yaml").write_text(textwrap.dedent(f"""\
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
                        - name: {env_name}
                          valueFrom:
                            secretKeyRef:
                              name: dev-omi-backend-secrets
                              key: {env_name}
            """))

    def render(value_from: str) -> dict:
        overlay = tmp_path / f"overlay-{len(list(tmp_path.glob('overlay-*')))}"
        overlay.mkdir()
        strategic_patch = textwrap.dedent(f"""\
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
                        - name: {env_name}
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

    broken = render(f"""\
configMapKeyRef:
  name: dev-omi-backend-config
  key: {env_name}
""")
    broken_value_from = broken["spec"]["template"]["spec"]["containers"][0]["env"][0]["valueFrom"]
    assert broken_value_from == {
        "configMapKeyRef": {"name": "dev-omi-backend-config", "key": env_name},
        "secretKeyRef": {"name": "dev-omi-backend-secrets", "key": env_name},
    }

    rendered_deployment = next(document for document in preflight.render("dev") if document.get("kind") == "Deployment")
    rendered_env = rendered_deployment["spec"]["template"]["spec"]["containers"][0]["env"]
    rendered_item = next(item for item in rendered_env if item["name"] == env_name)
    fixed = render(yaml.safe_dump(rendered_item["valueFrom"], sort_keys=False))
    fixed_value_from = fixed["spec"]["template"]["spec"]["containers"][0]["env"][0]["valueFrom"]
    assert fixed_value_from == {"configMapKeyRef": {"name": "dev-omi-backend-config", "key": env_name}}


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
