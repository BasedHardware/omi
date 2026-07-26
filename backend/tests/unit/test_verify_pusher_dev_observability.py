"""Regression coverage for isolated Pusher development-bake telemetry."""

from __future__ import annotations

import runpy
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "backend/scripts/verify_pusher_dev_observability.py"
FILES = (
    "backend/charts/monitoring/kube-prometheus-stack/dev_omi_monitoring_values.yaml",
    "backend/charts/pusher/dev_omi_pusher_values.yaml",
    "backend/charts/backend-listen/dev_omi_backend_listen_values.yaml",
    "backend/charts/monitoring/dashboards/gke/pusher.json",
    "backend/utils/metrics.py",
)


@pytest.fixture(scope="module")
def verifier() -> SimpleNamespace:
    return SimpleNamespace(**runpy.run_path(str(SCRIPT)))


@pytest.fixture
def fixture_root(tmp_path: Path) -> Path:
    for relative in FILES:
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, target)
    return tmp_path


def replace_once(path: Path, before: str, after: str) -> None:
    source = path.read_text(encoding="utf-8")
    assert source.count(before) == 1
    path.write_text(source.replace(before, after, 1), encoding="utf-8")


def test_dev_pusher_bake_observability_contract_passes(verifier: SimpleNamespace) -> None:
    assert verifier.validate(ROOT) == []


@pytest.mark.parametrize(
    ("relative", "before", "after", "expected"),
    [
        (
            "backend/charts/monitoring/kube-prometheus-stack/dev_omi_monitoring_values.yaml",
            "- job_name: pusher-metrics",
            "- job_name: removed-pusher-metrics",
            "must define the pusher-metrics scrape job",
        ),
        (
            "backend/charts/pusher/dev_omi_pusher_values.yaml",
            'prometheus.io/scrape: "true"',
            'prometheus.io/scrape: "false"',
            "isolated development scrape",
        ),
        (
            "backend/charts/pusher/dev_omi_pusher_values.yaml",
            "podLabels:\n  env: dev",
            "podLabels:\n  env: prod",
            "dev pusher chart must label its scrape target env: dev",
        ),
        (
            "backend/charts/backend-listen/dev_omi_backend_listen_values.yaml",
            "podLabels:\n  env: dev",
            "podLabels:\n  env: prod",
            "dev backend-listen chart must label its scrape target env: dev",
        ),
        (
            "backend/charts/monitoring/dashboards/gke/pusher.json",
            "pusher_drain_in_progress",
            "removed_drain_metric",
            "development-visible 'pusher_drain_in_progress'",
        ),
        (
            "backend/charts/monitoring/dashboards/gke/pusher.json",
            'up{job=~\\"pusher-metrics|backend-listen-metrics\\"}',
            "removed_scrape_target_health",
            "must expose the isolated scrape target health aggregate",
        ),
    ],
)
def test_rejects_missing_scrape_or_bake_signal(
    verifier: SimpleNamespace, fixture_root: Path, relative: str, before: str, after: str, expected: str
) -> None:
    replace_once(fixture_root / relative, before, after)

    assert any(expected in error for error in verifier.validate(fixture_root))


def test_rejects_pusher_scrape_outside_the_development_namespace(verifier: SimpleNamespace, fixture_root: Path) -> None:
    monitoring_values = fixture_root / "backend/charts/monitoring/kube-prometheus-stack/dev_omi_monitoring_values.yaml"
    source = monitoring_values.read_text(encoding="utf-8")
    pusher_job = verifier.scrape_block(source, "pusher-metrics")
    assert pusher_job is not None
    tampered_job = pusher_job.replace("regex: dev-omi-backend", "regex: prod-omi-backend", 1)
    monitoring_values.write_text(source.replace(pusher_job, tampered_job, 1), encoding="utf-8")

    assert any(
        "development pusher-metrics scrape must include 'regex: dev-omi-backend'" in error
        for error in verifier.validate(fixture_root)
    )
