"""Regression coverage for the static Pusher rollout-readiness guard."""

from __future__ import annotations

import runpy
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = REPO_ROOT / "backend" / "scripts" / "verify_pusher_rollout_budget.py"
FIXTURE_FILES = (
    "backend/charts/pusher/dev_omi_pusher_values.yaml",
    "backend/charts/pusher/prod_omi_pusher_values.yaml",
    "backend/charts/pusher/templates/deployment.yaml",
    "backend/charts/pusher/templates/backendconfig.yaml",
    ".github/workflows/gcp_backend_pusher.yml",
    ".github/workflows/gcp_backend_pusher_auto_deploy.yml",
)


@pytest.fixture(scope="module")
def verifier() -> SimpleNamespace:
    return SimpleNamespace(**runpy.run_path(str(SCRIPT)))


@pytest.fixture
def rollout_fixture(tmp_path: Path) -> Path:
    for relative in FIXTURE_FILES:
        source = REPO_ROOT / relative
        destination = tmp_path / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
    return tmp_path


def replace_once(path: Path, before: str, after: str) -> None:
    text = path.read_text(encoding="utf-8")
    assert text.count(before) == 1, f"expected exactly one {before!r} in {path}"
    path.write_text(text.replace(before, after, 1), encoding="utf-8")


def replace_probe_once(path: Path, probe: str, before: str, after: str) -> None:
    text = path.read_text(encoding="utf-8")
    start = text.index(f"{probe}:")
    end = text.index("\n\n", start)
    section = text[start:end]
    assert section.count(before) == 1, f"expected exactly one {before!r} in {probe} of {path}"
    path.write_text(text[:start] + section.replace(before, after, 1) + text[end:], encoding="utf-8")


def test_current_chart_and_workflows_cover_the_rollout_budget(verifier: SimpleNamespace) -> None:
    assert verifier.validate(REPO_ROOT) == []

    prod = verifier.rollout_budget(REPO_ROOT, "prod")
    assert (
        prod.replica_ceiling,
        prod.pods_in_flight,
        prod.waves,
        prod.startup_seconds_per_pod,
        prod.readiness_seconds_per_pod,
        prod.min_ready_seconds,
        prod.availability_seconds_per_pod,
    ) == (40, 3, 14, 600, 40, 0, 640)
    assert prod.required_seconds == 8960
    assert prod.progress_deadline_seconds == 9600


def test_rejects_workflow_wait_shorter_than_the_chart_budget(verifier: SimpleNamespace, rollout_fixture: Path) -> None:
    workflow = rollout_fixture / ".github/workflows/gcp_backend_pusher.yml"
    replace_once(workflow, "--timeout=9600s", "--timeout=300s")

    errors = verifier.validate(rollout_fixture)

    assert any(
        "gcp_backend_pusher.yml: Pusher rollout timeout=300s is below the 8960s healthy rollout budget" in error
        for error in errors
    )


def test_rejects_progress_deadline_shorter_than_the_chart_budget(
    verifier: SimpleNamespace, rollout_fixture: Path
) -> None:
    values = rollout_fixture / "backend/charts/pusher/prod_omi_pusher_values.yaml"
    replace_once(values, "progressDeadlineSeconds: 9600", "progressDeadlineSeconds: 8959")

    errors = verifier.validate(rollout_fixture)

    assert any(
        "prod Pusher progressDeadlineSeconds=8959s is below the 8960s healthy rollout budget" in error
        for error in errors
    )


@pytest.mark.parametrize(
    ("before", "after", "required_seconds"),
    [
        ("failureThreshold: 60", "failureThreshold: 80", 11760),
        ("maxReplicas: 40", "maxReplicas: 46", 10240),
        ("maxSurge: 2", "maxSurge: 1", 12800),
    ],
)
def test_chart_budget_changes_cannot_outgrow_the_deadline_or_wait(
    verifier: SimpleNamespace,
    rollout_fixture: Path,
    before: str,
    after: str,
    required_seconds: int,
) -> None:
    values = rollout_fixture / "backend/charts/pusher/prod_omi_pusher_values.yaml"
    replace_once(values, before, after)

    errors = verifier.validate(rollout_fixture)

    assert any(
        f"prod Pusher progressDeadlineSeconds=9600s is below the {required_seconds}s healthy rollout budget" in error
        for error in errors
    )
    assert any(
        f"gcp_backend_pusher.yml: Pusher rollout timeout=9600s is below the {required_seconds}s healthy rollout budget"
        in error
        for error in errors
    )


@pytest.mark.parametrize(
    ("probe", "before", "after", "required_seconds"),
    [
        ("startupProbe", "initialDelaySeconds: 0", "initialDelaySeconds: 100", 10360),
        ("startupProbe", "timeoutSeconds: 5", "timeoutSeconds: 15", 13160),
        ("readinessProbe", "failureThreshold: 3", "failureThreshold: 10", 9940),
        ("readinessProbe", "initialDelaySeconds: 0", "initialDelaySeconds: 50", 9660),
        ("readinessProbe", "periodSeconds: 10", "periodSeconds: 25", 9800),
        ("readinessProbe", "successThreshold: 1", "successThreshold: 6", 9660),
        ("readinessProbe", "timeoutSeconds: 5", "timeoutSeconds: 25", 9800),
    ],
)
def test_probe_availability_delays_cannot_outgrow_the_deadline_or_wait(
    verifier: SimpleNamespace,
    rollout_fixture: Path,
    probe: str,
    before: str,
    after: str,
    required_seconds: int,
) -> None:
    values = rollout_fixture / "backend/charts/pusher/prod_omi_pusher_values.yaml"
    replace_probe_once(values, probe, before, after)

    errors = verifier.validate(rollout_fixture)

    assert any(
        f"prod Pusher progressDeadlineSeconds=9600s is below the {required_seconds}s healthy rollout budget" in error
        for error in errors
    )
    assert any(
        f"gcp_backend_pusher.yml: Pusher rollout timeout=9600s is below the {required_seconds}s healthy rollout budget"
        in error
        for error in errors
    )


def test_min_ready_delay_cannot_outgrow_the_deadline_or_wait(verifier: SimpleNamespace, rollout_fixture: Path) -> None:
    values = rollout_fixture / "backend/charts/pusher/prod_omi_pusher_values.yaml"
    replace_once(values, "minReadySeconds: 0", "minReadySeconds: 100")

    errors = verifier.validate(rollout_fixture)

    assert any(
        "prod Pusher progressDeadlineSeconds=9600s is below the 10360s healthy rollout budget" in error
        for error in errors
    )
    assert any(
        "gcp_backend_pusher.yml: Pusher rollout timeout=9600s is below the 10360s healthy rollout budget" in error
        for error in errors
    )


@pytest.mark.parametrize(
    ("path", "before", "expected"),
    [
        ("backend/charts/pusher/prod_omi_pusher_values.yaml", "minReadySeconds: 0\n", "missing scalar minReadySeconds"),
        (
            "backend/charts/pusher/prod_omi_pusher_values.yaml",
            "  successThreshold: 1\n",
            "missing scalar readinessProbe/successThreshold",
        ),
    ],
)
def test_rejects_implicit_availability_delay_defaults(
    verifier: SimpleNamespace, rollout_fixture: Path, path: str, before: str, expected: str
) -> None:
    values = rollout_fixture / path
    replace_once(values, before, "")

    errors = verifier.validate(rollout_fixture)

    assert any(expected in error for error in errors)


def test_rejects_template_that_does_not_render_the_chart_deadline(
    verifier: SimpleNamespace, rollout_fixture: Path
) -> None:
    template = rollout_fixture / "backend/charts/pusher/templates/deployment.yaml"
    replace_once(
        template,
        "minReadySeconds: {{ .Values.minReadySeconds }}",
        "minReadySeconds: 0",
    )
    replace_once(
        template,
        'progressDeadlineSeconds: {{ required "progressDeadlineSeconds is required" .Values.progressDeadlineSeconds }}',
        "progressDeadlineSeconds: 9600",
    )

    errors = verifier.validate(rollout_fixture)

    assert any(
        "Deployment spec must render progressDeadlineSeconds from .Values.progressDeadlineSeconds" in error
        for error in errors
    )
    assert any("Deployment spec must render minReadySeconds from .Values.minReadySeconds" in error for error in errors)


@pytest.mark.parametrize(
    ("environment", "probe", "before", "after"),
    [
        ("dev", "readinessProbe", "path: /ready", "path: /health"),
        ("prod", "readinessProbe", "path: /ready", "path: /health"),
        ("prod", "livenessProbe", "path: /health", "path: /ready"),
        ("prod", "startupProbe", "path: /health", "path: /ready"),
    ],
)
def test_rejects_probe_routed_away_from_its_contract_path(
    verifier: SimpleNamespace,
    rollout_fixture: Path,
    environment: str,
    probe: str,
    before: str,
    after: str,
) -> None:
    values = rollout_fixture / "backend/charts/pusher" / f"{environment}_omi_pusher_values.yaml"
    replace_probe_once(values, probe, before, after)

    errors = verifier.validate(rollout_fixture)

    expected_path = {"readinessProbe": "/ready", "livenessProbe": "/health", "startupProbe": "/health"}[probe]
    assert any(f"{probe}/httpGet/path must be '{expected_path}'" in error for error in errors)


def test_rejects_backendconfig_without_connection_draining(verifier: SimpleNamespace, rollout_fixture: Path) -> None:
    template = rollout_fixture / "backend/charts/pusher/templates/backendconfig.yaml"
    replace_once(
        template,
        "  connectionDraining:\n    drainingTimeoutSec: {{ .Values.backendConfig.connectionDraining.drainingTimeoutSec | default 60 }}\n",
        "",
    )

    errors = verifier.validate(rollout_fixture)

    assert any(
        "BackendConfig must render connectionDraining.drainingTimeoutSec from .Values" in error for error in errors
    )


def test_rejects_drain_timeout_exceeding_grace(verifier: SimpleNamespace, rollout_fixture: Path) -> None:
    values = rollout_fixture / "backend/charts/pusher/prod_omi_pusher_values.yaml"
    replace_once(values, "    drainingTimeoutSec: 60", "    drainingTimeoutSec: 999")

    errors = verifier.validate(rollout_fixture)

    assert any(
        "connectionDraining.drainingTimeoutSec=999s must be <= terminationGracePeriodSeconds=120s" in error
        for error in errors
    )


def test_rejects_backendconfig_healthcheck_routed_to_ready(verifier: SimpleNamespace, rollout_fixture: Path) -> None:
    # Routing the LB healthCheck to /ready would flip the backend unhealthy during
    # a readiness drain and defeat connectionDraining — the highest-value invariant.
    template = rollout_fixture / "backend/charts/pusher/templates/backendconfig.yaml"
    replace_once(template, "requestPath: /health", "requestPath: /ready")

    errors = verifier.validate(rollout_fixture)

    assert any("healthCheck.requestPath must render to /health" in error for error in errors)
