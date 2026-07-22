"""Regression coverage for the Pusher rollout quality-gate preflight + rollback contract."""

from __future__ import annotations

import json
import runpy
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = REPO_ROOT / "backend" / "scripts" / "verify_pusher_rollout_gate.py"

FIXTURE_FILES = (
    "backend/charts/pusher/dev_omi_pusher_values.yaml",
    "backend/charts/pusher/prod_omi_pusher_values.yaml",
    "backend/charts/pusher/templates/backendconfig.yaml",
    "backend/charts/pusher/templates/deployment.yaml",
    "backend/utils/metrics.py",
)


@pytest.fixture(scope="module")
def gate() -> SimpleNamespace:
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


def replace_in_section(path: Path, section_start: str, before: str, after: str) -> None:
    """Replace *before* with *after* only within the YAML block starting at *section_start*."""

    text = path.read_text(encoding="utf-8")
    start = text.index(section_start)
    end = text.index("\n\n", start)
    section = text[start:end]
    assert section.count(before) == 1, f"expected exactly one {before!r} in section {section_start!r} of {path}"
    path.write_text(text[:start] + section.replace(before, after, 1) + text[end:], encoding="utf-8")


# ---------------------------------------------------------------------------
# preflight — pass on the good chart (both repo root and hermetic fixture)
# ---------------------------------------------------------------------------


def test_preflight_passes_on_repo_root(gate: SimpleNamespace) -> None:
    assert gate.validate_preflight(REPO_ROOT) == []


def test_preflight_passes_on_good_fixture(gate: SimpleNamespace, rollout_fixture: Path) -> None:
    assert gate.validate_preflight(rollout_fixture) == []


# ---------------------------------------------------------------------------
# preflight — fail when readinessProbe regresses to /health
# ---------------------------------------------------------------------------


def test_preflight_fails_when_readiness_regresses_to_health(gate: SimpleNamespace, rollout_fixture: Path) -> None:
    values = rollout_fixture / "backend/charts/pusher/prod_omi_pusher_values.yaml"
    replace_in_section(values, "readinessProbe:", "path: /ready", "path: /health")

    errors = gate.validate_preflight(rollout_fixture)

    assert any("readinessProbe/httpGet/path must be '/ready'" in error for error in errors)


# ---------------------------------------------------------------------------
# preflight — fail when a rollout-blocking metric is removed
# ---------------------------------------------------------------------------


def test_preflight_fails_when_metric_removed(gate: SimpleNamespace, rollout_fixture: Path) -> None:
    metrics = rollout_fixture / "backend/utils/metrics.py"
    # Remove the pusher_ready metric definition entirely.
    replace_once(
        metrics,
        "PUSHER_READY = Gauge(\n    'pusher_ready',\n    '1 = serving new traffic, 0 = draining',\n)\n",
        "",
    )

    errors = gate.validate_preflight(rollout_fixture)

    assert any("'pusher_ready' is not defined" in error for error in errors)


# ---------------------------------------------------------------------------
# preflight — fail when drainingTimeoutSec > terminationGracePeriodSeconds
# ---------------------------------------------------------------------------


def test_preflight_fails_when_draining_exceeds_grace(gate: SimpleNamespace, rollout_fixture: Path) -> None:
    values = rollout_fixture / "backend/charts/pusher/prod_omi_pusher_values.yaml"
    replace_once(values, "drainingTimeoutSec: 60", "drainingTimeoutSec: 130")

    errors = gate.validate_preflight(rollout_fixture)

    assert any(
        "drainingTimeoutSec=130s must not exceed terminationGracePeriodSeconds=120s" in error for error in errors
    )


# ---------------------------------------------------------------------------
# preflight — fail when BackendConfig healthCheck is routed to /ready
# ---------------------------------------------------------------------------


def test_preflight_fails_when_healthcheck_routed_to_ready(gate: SimpleNamespace, rollout_fixture: Path) -> None:
    template = rollout_fixture / "backend/charts/pusher/templates/backendconfig.yaml"
    replace_once(template, "requestPath: /health", "requestPath: /ready")

    errors = gate.validate_preflight(rollout_fixture)

    assert any("healthCheck.requestPath must render to /health" in error for error in errors)


# ---------------------------------------------------------------------------
# rollback — emits contract JSON with prior-restore and traffic/data split
# ---------------------------------------------------------------------------


def test_rollback_emits_contract_json(gate: SimpleNamespace, rollout_fixture: Path) -> None:
    contract = gate.rollback_contract(rollout_fixture, "prod")
    payload = contract.as_dict()

    assert payload["environment"] == "prod"
    assert payload["revision_history_limit"] == 10  # chart default (not set in template)
    assert "Prior ReplicaSets are retained" in payload["revision_history_source"]

    # Prior-restore field present and clearly operator-captured (not static).
    assert "prior image tag/digest" in payload["prior_restore"].lower()
    assert "captured at runtime" in payload["prior_restore"]
    assert "helm upgrade" in payload["restore_command"]

    # Capture must extract ONLY the tag or digest, not the full image ref,
    # and restore must use --set-string (matches the deploy workflows).
    assert "sed 's/.*://'" in payload["capture_command"]
    assert "sha256:[a-f0-9]" in payload["capture_command"]
    assert "--set-string image.tag=" in payload["restore_command"]
    assert "--set-string image.digest=" in payload["restore_command"]

    # Traffic vs data rollback separation.
    assert "SAFE" in payload["traffic_rollback"]
    assert "always available" in payload["traffic_rollback"]
    assert "IRREVERSIBLE" in payload["data_rollback"]
    assert "NEVER be auto-rolled-back" in payload["data_rollback"]

    # Must be valid JSON-serializable.
    serialized = json.dumps(payload, indent=2)
    assert json.loads(serialized) == payload


# ---------------------------------------------------------------------------
# preflight — build-once digest promotion contract (image identity)
# ---------------------------------------------------------------------------

DIGEST = "sha256:a541cd642b2f7a92519ad648da64c806734ce336d7cebbfd0cd0246db7a2f20f"


def _image_values(fixture: Path) -> Path:
    return fixture / "backend/charts/pusher/dev_omi_pusher_values.yaml"


def test_preflight_accepts_digest_pinned_release(gate: SimpleNamespace, rollout_fixture: Path) -> None:
    values = _image_values(rollout_fixture)
    replace_in_section(values, "image:", "pullPolicy: Always", "pullPolicy: IfNotPresent")
    replace_in_section(values, "image:", 'tag: ""', f"digest: {DIGEST}")

    assert gate.validate_preflight(rollout_fixture) == []


def test_preflight_rejects_malformed_digest(gate: SimpleNamespace, rollout_fixture: Path) -> None:
    values = _image_values(rollout_fixture)
    replace_in_section(values, "image:", "pullPolicy: Always", "pullPolicy: IfNotPresent")
    replace_in_section(values, "image:", 'tag: ""', "digest: not-a-digest")

    errors = gate.validate_preflight(rollout_fixture)

    assert any("image/digest must be sha256" in error for error in errors)


def test_preflight_rejects_digest_with_a_mutable_tag(gate: SimpleNamespace, rollout_fixture: Path) -> None:
    values = _image_values(rollout_fixture)
    replace_in_section(values, "image:", "pullPolicy: Always", "pullPolicy: IfNotPresent")
    replace_in_section(values, "image:", 'tag: ""', f'tag: "v1.2.3"\n  digest: {DIGEST}')

    errors = gate.validate_preflight(rollout_fixture)

    assert any("image/tag must be empty when image/digest" in error for error in errors)


def test_preflight_rejects_digest_with_always_pull(gate: SimpleNamespace, rollout_fixture: Path) -> None:
    values = _image_values(rollout_fixture)
    replace_in_section(values, "image:", 'tag: ""', f"digest: {DIGEST}")

    errors = gate.validate_preflight(rollout_fixture)

    assert any("pullPolicy must be IfNotPresent for a digest-pinned" in error for error in errors)
