"""Behavioral regression tests for Pusher dev-to-prod digest qualification."""

from __future__ import annotations

import runpy
import subprocess
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "verify_pusher_promotion_evidence.py"
RECEIPT_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "pusher_release_receipt.py"
SEMANTIC_PROBE_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "pusher_semantic_probe.py"
PROD_CANARY_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "pusher_prod_canary.py"
DIGEST = "sha256:" + "a" * 64
SOURCE_SHA = "b" * 40
RUN_ID = 321
WORKFLOW_ID = 654
CANARY_RUN_ID = 987
CANARY_WORKFLOW_ID = 789
REPOSITORY = "gcr.io/based-hardware-dev/pusher"
LIVE_WINDOW_TRANSCRIPT = "the wizard who had vanished"


def writer_live_segment_window(
    transcript: str = LIVE_WINDOW_TRANSCRIPT,
    *,
    matched: bool = True,
) -> dict[str, object]:
    """Mirror `pusher_semantic_probe._receipt` live_segment_window emission."""

    return {
        "matched": matched,
        "segment_text_chars": len(transcript),
    }


@pytest.fixture(scope="module")
def verifier() -> SimpleNamespace:
    return SimpleNamespace(**runpy.run_path(str(SCRIPT)))


@pytest.fixture(scope="module")
def receipt_builder() -> SimpleNamespace:
    return SimpleNamespace(**runpy.run_path(str(RECEIPT_SCRIPT)))


@pytest.fixture(scope="module")
def semantic_probe() -> SimpleNamespace:
    return SimpleNamespace(**runpy.run_path(str(SEMANTIC_PROBE_SCRIPT)))


@pytest.fixture(scope="module")
def prod_canary() -> SimpleNamespace:
    return SimpleNamespace(**runpy.run_path(str(PROD_CANARY_SCRIPT)))


def _deployment_receipt(source_sha: str = SOURCE_SHA) -> dict[str, object]:
    return {
        "schema_version": 1,
        "environment": "development",
        "recorded_at": "2026-08-30T12:05:00Z",
        "run_id": RUN_ID,
        "source_sha": source_sha,
        "image": {"repository": REPOSITORY, "digest": DIGEST},
        "rendered_chart_sha256": "sha256:" + "c" * 64,
        "config_sha256": "sha256:" + "d" * 64,
        "expected_pod_template_sha256": "sha256:" + "e" * 64,
        "live_pod_template_sha256": "sha256:" + "e" * 64,
        "live_identity": {
            "deployment_name": "dev-omi-pusher",
            "deployment_uid": "deployment-uid",
            "generation": 2,
            "observed_generation": 2,
            "namespace": "dev-omi-backend",
            "ready_replicas": 2,
            "replicas": 2,
            "pods": [
                {"name": "dev-omi-pusher-1", "uid": "pod-1", "image_id": f"repo@{DIGEST}"},
                {"name": "dev-omi-pusher-2", "uid": "pod-2", "image_id": f"repo@{DIGEST}"},
            ],
        },
    }


@pytest.fixture
def deployment_receipt() -> dict[str, object]:
    return _deployment_receipt()


def _evidence(verifier: SimpleNamespace, deployment_receipt: dict[str, object]) -> dict[str, object]:
    receipt_sha = verifier.canonical_sha256(deployment_receipt)
    return {
        "schema_version": 2,
        "qualification_status": "PASS",
        "environment": "development",
        "image_digest": DIGEST,
        "image_repository": REPOSITORY,
        "run_id": RUN_ID,
        "source_sha": deployment_receipt["source_sha"],
        "workflow": "gcp_backend_pusher_auto_deploy.yml",
        "rendered_chart_sha256": deployment_receipt["rendered_chart_sha256"],
        "config_sha256": deployment_receipt["config_sha256"],
        "expected_pod_template_sha256": deployment_receipt["expected_pod_template_sha256"],
        "live_pod_template_sha256": deployment_receipt["live_pod_template_sha256"],
        "deployment_receipt_sha256": receipt_sha,
        "contract_sha256": verifier.contract_fingerprint(),
        "semantic_probe": {
            "schema_version": 1,
            "status": "PASS",
            "evidence_id": "dev-probe-321",
            "candidate": {
                "source_sha": deployment_receipt["source_sha"],
                "image_digest": DIGEST,
                "deployment_receipt_sha256": receipt_sha,
            },
            "window": {
                "started_at": "2026-08-30T12:06:00Z",
                "ended_at": "2026-08-30T12:16:00Z",
                "closed_at": "2026-08-30T12:17:00Z",
            },
            "samples": {"attempted": 8, "succeeded": 8, "failed": 0},
            "synthetic_uid_class": "firebase_release_probe",
            "producer_observation": {"status": "PASS", "candidate_pod_count": 1},
            "consumer_readback": {"status": "PASS"},
            "live_segment_window": writer_live_segment_window(),
        },
    }


@pytest.fixture
def evidence(verifier: SimpleNamespace, deployment_receipt: dict[str, object]) -> dict[str, object]:
    return _evidence(verifier, deployment_receipt)


def _run(source_sha: str = SOURCE_SHA) -> dict[str, object]:
    return {
        "id": RUN_ID,
        "workflow_id": WORKFLOW_ID,
        "event": "push",
        "head_branch": "main",
        "head_sha": source_sha,
        "status": "completed",
        "conclusion": "success",
    }


@pytest.fixture
def run() -> dict[str, object]:
    return _run()


def _canary_deployment_receipt(source_sha: str) -> dict[str, object]:
    return {
        "schema_version": 1,
        "environment": "prod",
        "recorded_at": "2026-08-30T12:19:00Z",
        "run_id": CANARY_RUN_ID,
        "source_sha": source_sha,
        "image": {"repository": "gcr.io/based-hardware/pusher", "digest": DIGEST},
        "rendered_chart_sha256": "sha256:" + "1" * 64,
        "config_sha256": "sha256:" + "2" * 64,
        "expected_pod_template_sha256": "sha256:" + "3" * 64,
        "live_pod_template_sha256": "sha256:" + "3" * 64,
        "live_identity": {
            "deployment_name": f"prod-omi-pusher-canary-{CANARY_RUN_ID}",
            "deployment_uid": "canary-pusher-deployment",
            "generation": 1,
            "observed_generation": 1,
            "namespace": "prod-omi-backend",
            "ready_replicas": 1,
            "replicas": 1,
            "pods": [{"name": "canary-pusher-1", "uid": "pod-canary", "image_id": f"repo@{DIGEST}"}],
        },
    }


def _final_deployment_receipt(source_sha: str, *, config_sha256: str) -> dict[str, object]:
    return {
        "schema_version": 1,
        "environment": "prod",
        "recorded_at": "2026-08-30T12:40:00Z",
        "run_id": CANARY_RUN_ID,
        "source_sha": source_sha,
        "image": {"repository": "gcr.io/based-hardware/pusher", "digest": DIGEST},
        "rendered_chart_sha256": "sha256:" + "1" * 64,
        "config_sha256": config_sha256,
        "expected_pod_template_sha256": "sha256:" + "3" * 64,
        "live_pod_template_sha256": "sha256:" + "3" * 64,
        "live_identity": {
            "namespace": "prod-omi-backend",
            "deployment_name": "prod-omi-pusher",
            "replicas": 40,
            "ready_replicas": 40,
            "generation": 9,
            "observed_generation": 9,
            "pods": [
                {"name": f"pusher-{index}", "uid": f"pod-{index}", "image_id": f"repo@{DIGEST}"} for index in range(40)
            ],
        },
    }


def _canary_run(source_sha: str) -> dict[str, object]:
    return {
        "id": CANARY_RUN_ID,
        "workflow_id": CANARY_WORKFLOW_ID,
        "event": "workflow_dispatch",
        "head_branch": "main",
        "head_sha": source_sha,
        "status": "completed",
        "conclusion": "success",
    }


def validate(
    verifier: SimpleNamespace,
    evidence: dict[str, object],
    deployment_receipt: dict[str, object],
    run: dict[str, object],
    *,
    prod_source_sha: str = SOURCE_SHA,
    expected_canary_source_sha: str | None = None,
    checkout_repository: Path | None = None,
    canary_override: dict[str, object] | None = None,
    canary_run_override: dict[str, object] | None = None,
    canary_semantic_override: dict[str, object] | None = None,
    canary_semantic_hash_override: str | None = None,
    canary_deployment_receipt_override: dict[str, object] | None = None,
    final_deployment_receipt_override: dict[str, object] | None = None,
    canary_mutator: Callable[[dict[str, object]], None] | None = None,
    require_final: bool = False,
) -> list[str]:
    expected_sha = prod_source_sha if expected_canary_source_sha is None else expected_canary_source_sha
    receipt_sha = verifier.canonical_sha256(deployment_receipt)
    canary_deployment_receipt = canary_deployment_receipt_override or _canary_deployment_receipt(prod_source_sha)
    canary_semantic = canary_semantic_override or {
        "schema_version": 1,
        "status": "PASS",
        "evidence_id": "prod-probe-987",
        "candidate": {
            "source_sha": prod_source_sha,
            "image_digest": DIGEST,
            "deployment_receipt_sha256": verifier.canonical_sha256(canary_deployment_receipt),
        },
        "window": {
            "started_at": "2026-08-30T12:20:00Z",
            "ended_at": "2026-08-30T12:30:00Z",
            "closed_at": "2026-08-30T12:31:00Z",
        },
        "samples": {"attempted": 1, "succeeded": 1, "failed": 0},
        "synthetic_uid_class": "firebase_release_probe",
        "producer_observation": {"status": "PASS", "candidate_pod_count": 1},
        "consumer_readback": {"status": "PASS"},
        "live_segment_window": writer_live_segment_window(),
    }
    canary = canary_override or {
        "schema_version": 1,
        "status": "PASS",
        "evidence_id": "prod-canary-321",
        "candidate": {
            "source_sha": prod_source_sha,
            "image_digest": DIGEST,
            "qualification_deployment_receipt_sha256": receipt_sha,
            "canary_deployment_receipt_sha256": verifier.canonical_sha256(canary_deployment_receipt),
        },
        "window": {
            "started_at": "2026-08-30T12:20:00Z",
            "ended_at": "2026-08-30T12:30:00Z",
            "closed_at": "2026-08-30T12:31:00Z",
        },
        "sessions": {"attributed": 5, "unattributed": 0},
        "outcomes": {"evaluated": 5, "terminal_success": 5, "terminal_failure": 0, "pending": 0},
        "approval_run_id": CANARY_RUN_ID,
        "protected_environment": "prod",
        "deployment_identity": {
            "pusher": canary_deployment_receipt["live_identity"],
            "listener": {
                "deployment_name": f"prod-omi-listener-canary-{CANARY_RUN_ID}",
                "deployment_uid": "listener-deployment",
                "pod_uid": "listener-pod",
                "runtime_image": "gcr.io/based-hardware/backend@sha256:" + "4" * 64,
                "ordinary_service_selector_excluded": True,
                "pusher_url_class": "isolated_cluster_service",
                "service_selectors_evaluated": 12,
                "service_selector_snapshot_sha256": "sha256:" + "6" * 64,
            },
        },
        "semantic_evidence_sha256": canary_semantic_hash_override or verifier.canonical_sha256(canary_semantic),
    }
    if canary_override is None and canary_mutator is not None:
        canary_mutator(canary)
    canary_run = canary_run_override or _canary_run(prod_source_sha)
    final_deployment_receipt = final_deployment_receipt_override or _final_deployment_receipt(
        prod_source_sha, config_sha256=str(canary_deployment_receipt["config_sha256"])
    )
    return verifier.validate(
        evidence,
        deployment_receipt,
        canary,
        canary_run,
        run,
        expected_digest=DIGEST,
        expected_repository=REPOSITORY,
        expected_workflow_id=WORKFLOW_ID,
        expected_run_id=RUN_ID,
        expected_canary_workflow_id=CANARY_WORKFLOW_ID,
        expected_canary_run_id=CANARY_RUN_ID,
        expected_canary_source_sha=expected_sha,
        canary_deployment_receipt=canary_deployment_receipt,
        canary_semantic_evidence=canary_semantic,
        final_deployment_receipt=final_deployment_receipt,
        expected_final_repository="gcr.io/based-hardware/pusher",
        require_final=require_final,
        checkout_repository=checkout_repository or verifier.ROOT,
    )


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    )


def _commit_all(repo: Path, message: str) -> str:
    _git(repo, "-c", "user.email=pusher-test@example.com", "-c", "user.name=Pusher Test", "add", "-A")
    _git(
        repo,
        "-c",
        "user.email=pusher-test@example.com",
        "-c",
        "user.name=Pusher Test",
        "-c",
        "core.hooksPath=/dev/null",
        "commit",
        "-qm",
        message,
    )
    return _git(repo, "rev-parse", "HEAD").stdout.strip()


def _promotion_repo(tmp_path: Path, *, closure_change: bool) -> tuple[Path, str, str]:
    """Build a hermetic two-commit repo: dev-qualified SHA, then moved main.

    Returns (repo, dev_sha, prod_sha). ``closure_change=False`` advances main
    only outside the Dockerfile-derived Pusher closure; ``True`` also mutates
    ``backend/pusher`` and the pusher chart so the closure gate must fire.
    """
    repo = tmp_path / "repo"
    (repo / "backend/pusher").mkdir(parents=True)
    (repo / "backend/charts/pusher").mkdir(parents=True)
    (repo / "docs").mkdir(parents=True)
    (repo / "backend/pusher/main.py").write_text("qualified\n", encoding="utf-8")
    (repo / "backend/charts/pusher/values.yaml").write_text("replicas: 1\n", encoding="utf-8")
    (repo / "docs/notes.md").write_text("one\n", encoding="utf-8")
    _git(repo, "init", "-q")
    dev_sha = _commit_all(repo, "qualified")
    if closure_change:
        (repo / "backend/pusher/main.py").write_text("moved main\n", encoding="utf-8")
        (repo / "backend/charts/pusher/values.yaml").write_text("replicas: 2\n", encoding="utf-8")
    else:
        (repo / "docs/notes.md").write_text("two\n", encoding="utf-8")
    prod_sha = _commit_all(repo, "moved main")
    return repo, dev_sha, prod_sha


def test_accepts_an_exact_digest_from_the_successful_main_dev_run(
    verifier: SimpleNamespace,
    evidence: dict[str, object],
    deployment_receipt: dict[str, object],
    run: dict[str, object],
) -> None:
    assert validate(verifier, evidence, deployment_receipt, run) == []


def test_accepts_writer_emitted_live_segment_window(
    verifier: SimpleNamespace,
    semantic_probe: SimpleNamespace,
    evidence: dict[str, object],
    deployment_receipt: dict[str, object],
    run: dict[str, object],
) -> None:
    receipt_sha = verifier.canonical_sha256(deployment_receipt)
    probe = semantic_probe._receipt(
        status="PASS",
        evidence_id="dev-probe-321",
        deployment_receipt=deployment_receipt,
        deployment_receipt_sha256=receipt_sha,
        started_at="2026-08-30T12:06:00Z",
        ended_at="2026-08-30T12:16:00Z",
        candidate_pod_count=1,
        failure_stage=None,
        live_window_matched=True,
        live_window_transcript=LIVE_WINDOW_TRANSCRIPT,
    )
    probe["window"] = {
        "started_at": "2026-08-30T12:06:00Z",
        "ended_at": "2026-08-30T12:16:00Z",
        "closed_at": "2026-08-30T12:17:00Z",
    }
    probe["samples"] = {"attempted": 8, "succeeded": 8, "failed": 0}
    evidence["semantic_probe"] = probe

    assert probe["live_segment_window"] == writer_live_segment_window()
    assert validate(verifier, evidence, deployment_receipt, run) == []


def test_rejects_semantic_probe_missing_live_segment_window(
    verifier: SimpleNamespace,
    evidence: dict[str, object],
    deployment_receipt: dict[str, object],
    run: dict[str, object],
) -> None:
    probe = evidence["semantic_probe"]
    assert isinstance(probe, dict)
    del probe["live_segment_window"]

    errors = validate(verifier, evidence, deployment_receipt, run)
    assert any("semantic probe evidence has an unexpected schema" in error for error in errors)


def test_rejects_semantic_probe_live_segment_window_with_extra_or_invalid_nested_key(
    verifier: SimpleNamespace,
    evidence: dict[str, object],
    deployment_receipt: dict[str, object],
    run: dict[str, object],
) -> None:
    probe = evidence["semantic_probe"]
    assert isinstance(probe, dict)
    extra = dict(writer_live_segment_window())
    extra["transcript"] = LIVE_WINDOW_TRANSCRIPT
    probe["live_segment_window"] = extra
    extra_errors = validate(verifier, evidence, deployment_receipt, run)
    assert any(
        "semantic probe live_segment_window must declare matched and segment_text_chars" in error
        for error in extra_errors
    )

    probe["live_segment_window"] = {"matched": True}
    missing_errors = validate(verifier, evidence, deployment_receipt, run)
    assert any(
        "semantic probe live_segment_window must declare matched and segment_text_chars" in error
        for error in missing_errors
    )

    probe["live_segment_window"] = {"matched": "yes", "segment_text_chars": len(LIVE_WINDOW_TRANSCRIPT)}
    matched_errors = validate(verifier, evidence, deployment_receipt, run)
    assert any("semantic probe live_segment_window.matched must be a boolean" in error for error in matched_errors)

    probe["live_segment_window"] = {"matched": True, "segment_text_chars": -1}
    chars_errors = validate(verifier, evidence, deployment_receipt, run)
    assert any(
        "semantic probe live_segment_window.segment_text_chars must be a non-negative integer" in error
        for error in chars_errors
    )


def test_final_receipt_requires_the_canary_qualified_config_and_ready_shared_deployment(
    verifier: SimpleNamespace,
) -> None:
    canary = {"config_sha256": "sha256:" + "2" * 64}
    final = {
        "schema_version": 1,
        "environment": "prod",
        "recorded_at": "2026-08-30T12:40:00Z",
        "run_id": CANARY_RUN_ID,
        "source_sha": SOURCE_SHA,
        "image": {"repository": "gcr.io/based-hardware/pusher", "digest": DIGEST},
        "rendered_chart_sha256": "sha256:" + "1" * 64,
        "config_sha256": canary["config_sha256"],
        "expected_pod_template_sha256": "sha256:" + "3" * 64,
        "live_pod_template_sha256": "sha256:" + "3" * 64,
        "live_identity": {
            "namespace": "prod-omi-backend",
            "deployment_name": "prod-omi-pusher",
            "replicas": 40,
            "ready_replicas": 40,
            "generation": 9,
            "observed_generation": 9,
            "pods": [
                {"name": f"pusher-{index}", "uid": f"pod-{index}", "image_id": f"repo@{DIGEST}"} for index in range(40)
            ],
        },
    }
    assert (
        verifier._validate_final_deployment(
            final,
            canary,
            source_sha=SOURCE_SHA,
            digest=DIGEST,
            repository="gcr.io/based-hardware/pusher",
            run_id=CANARY_RUN_ID,
        )
        == []
    )
    final["config_sha256"] = "sha256:" + "f" * 64
    assert any(
        "canary-qualified ConfigMap" in error
        for error in verifier._validate_final_deployment(
            final,
            canary,
            source_sha=SOURCE_SHA,
            digest=DIGEST,
            repository="gcr.io/based-hardware/pusher",
            run_id=CANARY_RUN_ID,
        )
    )


@pytest.mark.parametrize(
    ("target", "key", "value", "expected"),
    [
        ("evidence", "image_digest", "sha256:short", "exact sha256"),
        ("evidence", "image_digest", "sha256:" + "c" * 64, "requested production digest"),
        ("evidence", "run_id", RUN_ID + 1, "run_id does not match"),
        ("evidence", "source_sha", "C" * 40, "full lowercase source SHA"),
        ("run", "workflow_id", WORKFLOW_ID + 1, "not the automatic dev Pusher workflow"),
        ("run", "event", "workflow_dispatch", "main push qualification"),
        ("run", "conclusion", "failure", "did not complete successfully"),
        ("run", "head_sha", "d" * 40, "does not match the successful workflow run"),
    ],
)
def test_rejects_missing_or_mismatched_qualification_proof(
    verifier: SimpleNamespace,
    evidence: dict[str, object],
    deployment_receipt: dict[str, object],
    run: dict[str, object],
    target: str,
    key: str,
    value: object,
    expected: str,
) -> None:
    (evidence if target == "evidence" else run)[key] = value

    assert any(expected in error for error in validate(verifier, evidence, deployment_receipt, run))


def test_rejects_ambiguous_evidence_schema(
    verifier: SimpleNamespace,
    evidence: dict[str, object],
    deployment_receipt: dict[str, object],
    run: dict[str, object],
) -> None:
    evidence["untrusted"] = True

    assert any("unexpected schema" in error for error in validate(verifier, evidence, deployment_receipt, run))


def test_rejects_blocked_qualification_status(
    verifier: SimpleNamespace,
    evidence: dict[str, object],
    deployment_receipt: dict[str, object],
    run: dict[str, object],
) -> None:
    evidence["qualification_status"] = "BLOCKED"

    assert any(
        "qualification status must be PASS" in error for error in validate(verifier, evidence, deployment_receipt, run)
    )


@pytest.mark.parametrize("status", ["NOT_RUN", "FAIL", None])
def test_rejects_semantic_probe_without_explicit_pass(
    verifier: SimpleNamespace,
    evidence: dict[str, object],
    deployment_receipt: dict[str, object],
    run: dict[str, object],
    status: str | None,
) -> None:
    evidence["semantic_probe"] = {} if status is None else {"status": status}

    assert any(
        "semantic probe status must be PASS" in error for error in validate(verifier, evidence, deployment_receipt, run)
    )


def test_rejects_open_or_zero_sample_semantic_probe(
    verifier: SimpleNamespace,
    evidence: dict[str, object],
    deployment_receipt: dict[str, object],
    run: dict[str, object],
) -> None:
    probe = evidence["semantic_probe"]
    assert isinstance(probe, dict)
    probe["window"] = {
        "started_at": "2026-08-30T12:06:00Z",
        "ended_at": "2026-08-30T12:16:00Z",
        "closed_at": "2026-08-30T12:15:00Z",
    }
    probe["samples"] = {"attempted": 0, "succeeded": 0, "failed": 0}

    errors = validate(verifier, evidence, deployment_receipt, run)
    assert any("window must be closed" in error for error in errors)
    assert any("at least one sample" in error for error in errors)


def test_rejects_unattributed_or_not_run_canary(
    verifier: SimpleNamespace,
    evidence: dict[str, object],
    deployment_receipt: dict[str, object],
    run: dict[str, object],
) -> None:
    canary = {"status": "NOT_RUN", "reason": "NO_ATTRIBUTABLE_ROUTE"}

    assert any(
        "production canary status must be PASS" in error
        for error in validate(verifier, evidence, deployment_receipt, run, canary_override=canary)
    )


def test_rejects_canary_receipt_not_bound_to_protected_workflow_run(
    verifier: SimpleNamespace,
    evidence: dict[str, object],
    deployment_receipt: dict[str, object],
    run: dict[str, object],
) -> None:
    canary_run = {
        "id": CANARY_RUN_ID,
        "workflow_id": CANARY_WORKFLOW_ID,
        "event": "push",
        "head_branch": "main",
        "head_sha": SOURCE_SHA,
        "status": "completed",
        "conclusion": "success",
    }

    assert any(
        "protected main workflow dispatch" in error
        for error in validate(verifier, evidence, deployment_receipt, run, canary_run_override=canary_run)
    )


def test_rejects_canary_receipt_with_substituted_semantic_probe(
    verifier: SimpleNamespace,
    evidence: dict[str, object],
    deployment_receipt: dict[str, object],
    run: dict[str, object],
) -> None:
    substituted = {
        "status": "PASS",
        "candidate": {"source_sha": SOURCE_SHA, "image_digest": DIGEST},
    }

    errors = validate(
        verifier,
        evidence,
        deployment_receipt,
        run,
        canary_semantic_override=substituted,
        canary_semantic_hash_override="sha256:" + "5" * 64,
    )
    assert any("semantic evidence hash does not match" in error for error in errors)
    assert any("semantic probe evidence has an unexpected schema" in error for error in errors)


def test_rejects_canary_pass_with_failed_pending_or_unaccounted_sessions(
    verifier: SimpleNamespace,
    evidence: dict[str, object],
    deployment_receipt: dict[str, object],
    run: dict[str, object],
) -> None:
    canary = None
    # Start from the valid producer-shaped receipt assembled by the helper.
    valid_errors = validate(verifier, evidence, deployment_receipt, run)
    assert valid_errors == []
    # A minimal malformed PASS is sufficient to prove both outcome gates fire.
    canary = {
        "status": "PASS",
        "sessions": {"attributed": 5, "unattributed": 0},
        "outcomes": {"evaluated": 4, "terminal_success": 2, "terminal_failure": 1, "pending": 1},
    }

    errors = validate(verifier, evidence, deployment_receipt, run, canary_override=canary)
    assert any("every outcome terminal-successful" in error for error in errors)
    assert any("every and only attributable" in error for error in errors)


def test_rejects_contradictory_deployment_receipt(
    verifier: SimpleNamespace,
    evidence: dict[str, object],
    deployment_receipt: dict[str, object],
    run: dict[str, object],
) -> None:
    deployment_receipt["config_sha256"] = "sha256:" + "e" * 64

    errors = validate(verifier, evidence, deployment_receipt, run)
    assert any("does not bind the exact deployment receipt" in error for error in errors)
    assert any("config_sha256 contradicts" in error for error in errors)


def test_live_receipt_ignores_terminating_old_replica(receipt_builder: SimpleNamespace) -> None:
    old_digest = "sha256:" + "f" * 64
    deployment = {
        "metadata": {"name": "dev-omi-pusher", "uid": "deploy", "generation": 4},
        "spec": {"template": {"spec": {"containers": [{"name": "pusher", "image": f"{REPOSITORY}@{DIGEST}"}]}}},
        "status": {"observedGeneration": 4, "replicas": 1, "readyReplicas": 1, "availableReplicas": 1},
    }
    pods = {
        "items": [
            {
                "metadata": {
                    "name": "pusher-old",
                    "uid": "pod-old",
                    "deletionTimestamp": "2026-09-10T02:13:51Z",
                },
                "spec": {"containers": [{"name": "pusher", "image": f"{REPOSITORY}@{old_digest}"}]},
                "status": {
                    "phase": "Running",
                    "containerStatuses": [
                        {"name": "pusher", "ready": False, "imageID": f"docker-pullable://{REPOSITORY}@{old_digest}"}
                    ],
                },
            },
            {
                "metadata": {"name": "pusher-new", "uid": "pod-new"},
                "spec": {"containers": [{"name": "pusher", "image": f"{REPOSITORY}@{DIGEST}"}]},
                "status": {
                    "phase": "Running",
                    "containerStatuses": [
                        {"name": "pusher", "ready": True, "imageID": f"docker-pullable://{REPOSITORY}@{DIGEST}"}
                    ],
                },
            },
        ]
    }

    identity = receipt_builder.validate_live_identity(
        deployment,
        pods,
        namespace="dev-omi-backend",
        repository=REPOSITORY,
        digest=DIGEST,
    )
    assert identity["replicas"] == 1
    assert [pod["name"] for pod in identity["pods"]] == ["pusher-new"]


def test_live_receipt_rejects_a_pod_running_another_digest(receipt_builder: SimpleNamespace) -> None:
    deployment = {
        "metadata": {"name": "dev-omi-pusher", "uid": "deploy", "generation": 4},
        "spec": {"template": {"spec": {"containers": [{"name": "pusher", "image": f"{REPOSITORY}@{DIGEST}"}]}}},
        "status": {"observedGeneration": 4, "replicas": 1, "readyReplicas": 1, "availableReplicas": 1},
    }
    pods = {
        "items": [
            {
                "metadata": {"name": "pusher-1", "uid": "pod-1"},
                "spec": {"containers": [{"name": "pusher", "image": f"{REPOSITORY}@{DIGEST}"}]},
                "status": {
                    "containerStatuses": [
                        {"name": "pusher", "ready": True, "imageID": "docker-pullable://repo@sha256:" + "f" * 64}
                    ]
                },
            }
        ]
    }

    with pytest.raises(receipt_builder.ReceiptError, match="exact candidate digest"):
        receipt_builder.validate_live_identity(
            deployment,
            pods,
            namespace="dev-omi-backend",
            repository=REPOSITORY,
            digest=DIGEST,
        )


def test_qualification_recorder_never_invents_semantic_probe_pass(
    receipt_builder: SimpleNamespace, deployment_receipt: dict[str, object]
) -> None:
    qualification = receipt_builder.record_qualification(
        deployment_receipt,
        semantic_probe_path=None,
    )

    assert qualification["semantic_probe"] == {
        "status": "NOT_RUN",
        "reason": "NO_SAFE_SEMANTIC_PROBE_EVIDENCE_PRODUCER",
    }
    assert "production_canary" not in qualification
    assert qualification["qualification_status"] == "BLOCKED"


def test_semantic_probe_pass_receipt_binds_candidate_and_is_redacted(
    semantic_probe: SimpleNamespace,
    verifier: SimpleNamespace,
    deployment_receipt: dict[str, object],
) -> None:
    receipt_sha = verifier.canonical_sha256(deployment_receipt)
    receipt = semantic_probe._receipt(
        status="PASS",
        evidence_id="pusher-dev-321-unique",
        deployment_receipt=deployment_receipt,
        deployment_receipt_sha256=receipt_sha,
        started_at="2026-08-30T12:00:00Z",
        ended_at="2026-08-30T12:01:00Z",
        candidate_pod_count=1,
        failure_stage=None,
    )

    assert receipt["candidate"] == {
        "source_sha": SOURCE_SHA,
        "image_digest": DIGEST,
        "deployment_receipt_sha256": receipt_sha,
    }
    assert receipt["samples"] == {"attempted": 1, "succeeded": 1, "failed": 0}
    assert receipt["synthetic_uid_class"] == "firebase_release_probe"
    assert receipt["producer_observation"] == {"status": "PASS", "candidate_pod_count": 1}
    assert receipt["consumer_readback"] == {"status": "PASS"}
    assert "token" not in str(receipt).lower()
    assert "transcript" not in str(receipt).lower()


def test_semantic_probe_rejects_world_readable_token_file(semantic_probe: SimpleNamespace, tmp_path: Path) -> None:
    token = tmp_path / "token"
    token.write_text("secret-token", encoding="utf-8")
    token.chmod(0o644)

    with pytest.raises(semantic_probe.ProbeError, match="token_permissions"):
        semantic_probe._read_token(token)


def test_semantic_probe_fixture_is_the_versioned_real_audio_asset(semantic_probe: SimpleNamespace) -> None:
    fixture = semantic_probe.load_fixture()

    assert semantic_probe.FIXTURE_CODEC == "pcm16"
    assert fixture.sample_rate == 16000
    assert len(fixture.pcm) > 100_000
    assert "wizard who had vanished" in fixture.expected_phrase


@pytest.mark.parametrize("env", [[], [{"name": "MEMORY_ENABLED", "value": "off"}]])
def test_pusher_template_semantics_reject_missing_or_disabled_memory_flag(
    receipt_builder: SimpleNamespace, env: list[dict[str, str]]
) -> None:
    template = {"spec": {"containers": [{"name": "pusher", "image": f"repo@{DIGEST}", "env": env}]}}

    with pytest.raises(receipt_builder.ReceiptError, match="MEMORY_ENABLED"):
        receipt_builder.pod_template_semantic_projection(template)


def test_pusher_template_semantics_normalize_kubernetes_probe_defaults_and_quantities(
    receipt_builder: SimpleNamespace,
) -> None:
    expected = {
        "spec": {
            "serviceAccountName": "prod-omi-pusher",
            "containers": [
                {
                    "name": "pusher",
                    "image": f"repo@{DIGEST}",
                    "env": [{"name": "MEMORY_ENABLED", "value": "on"}],
                    "livenessProbe": {"httpGet": {"path": "/health", "port": 8080}, "timeoutSeconds": 5},
                    "resources": {
                        "requests": {"cpu": "0.7", "memory": "4.5Gi"},
                        "limits": {"cpu": "0.7", "memory": "4.5Gi"},
                    },
                }
            ],
        }
    }
    live = {
        "spec": {
            "serviceAccountName": "prod-omi-pusher",
            "containers": [
                {
                    "name": "pusher",
                    "image": f"repo@{DIGEST}",
                    "env": [{"name": "MEMORY_ENABLED", "value": "on"}],
                    "livenessProbe": {
                        "httpGet": {"path": "/health", "port": 8080, "scheme": "HTTP"},
                        "initialDelaySeconds": 0,
                        "timeoutSeconds": 5,
                        "periodSeconds": 10,
                        "successThreshold": 1,
                        "failureThreshold": 3,
                    },
                    "resources": {
                        "requests": {"cpu": "700m", "memory": "4608Mi"},
                        "limits": {"cpu": "700m", "memory": "4608Mi"},
                    },
                }
            ],
        }
    }

    assert receipt_builder.pod_template_semantic_projection(expected) == (
        receipt_builder.pod_template_semantic_projection(live)
    )


def test_live_receipt_projection_drops_helm_empty_string_env_value(
    receipt_builder: SimpleNamespace,
) -> None:
    """Helm renders `value: ""` (unset repo variable) but the API server stores
    the env entry without the value key (omitempty marshalling). The rendered
    projection must normalize to the API form before hashing (2026-09-22 prod
    canary: FREE_TIER_LOCAL_PROCESSING_COHORT)."""
    expected = {
        "spec": {
            "serviceAccountName": "prod-omi-pusher",
            "containers": [
                {
                    "name": "pusher",
                    "image": f"repo@{DIGEST}",
                    "env": [
                        {"name": "MEMORY_ENABLED", "value": "on"},
                        {"name": "FREE_TIER_LOCAL_PROCESSING_COHORT", "value": ""},
                    ],
                }
            ],
        }
    }
    live = {
        "spec": {
            "serviceAccountName": "prod-omi-pusher",
            "containers": [
                {
                    "name": "pusher",
                    "image": f"repo@{DIGEST}",
                    "env": [
                        {"name": "MEMORY_ENABLED", "value": "on"},
                        {"name": "FREE_TIER_LOCAL_PROCESSING_COHORT"},
                    ],
                }
            ],
        }
    }

    assert receipt_builder.pod_template_semantic_projection(expected) == (
        receipt_builder.pod_template_semantic_projection(live)
    )


def test_live_receipt_treats_helm_null_secret_ref_and_empty_pod_security_as_absent(
    receipt_builder: SimpleNamespace,
) -> None:
    expected = {
        "spec": {
            "serviceAccountName": "dev-omi-pusher",
            "containers": [
                {
                    "name": "pusher",
                    "image": f"repo@{DIGEST}",
                    "env": [
                        {"name": "MEMORY_ENABLED", "value": "on"},
                        {
                            "name": "TYPESENSE_HOST",
                            "valueFrom": {
                                "configMapKeyRef": {"name": "dev-omi-backend-config", "key": "TYPESENSE_HOST"},
                                "secretKeyRef": None,
                            },
                        },
                    ],
                }
            ],
        }
    }
    live = {
        "spec": {
            "serviceAccountName": "dev-omi-pusher",
            "securityContext": {},
            "containers": [
                {
                    "name": "pusher",
                    "image": f"repo@{DIGEST}",
                    "env": [
                        {"name": "MEMORY_ENABLED", "value": "on"},
                        {
                            "name": "TYPESENSE_HOST",
                            "valueFrom": {
                                "configMapKeyRef": {"name": "dev-omi-backend-config", "key": "TYPESENSE_HOST"},
                            },
                        },
                    ],
                }
            ],
        }
    }

    assert receipt_builder.pod_template_semantic_projection(expected) == (
        receipt_builder.pod_template_semantic_projection(live)
    )


def test_isolated_canary_render_uses_one_proposed_config_map_for_every_reference(
    receipt_builder: SimpleNamespace,
) -> None:
    config_name = f"prod-omi-backend-config-canary-{CANARY_RUN_ID}"
    documents = receipt_builder.rendered_chart_documents(
        "prod",
        "gcr.io/based-hardware/pusher",
        DIGEST,
        release_name=f"prod-omi-pusher-canary-{CANARY_RUN_ID}",
        isolated_canary=True,
        config_map_name=config_name,
    )
    deployment = next(document for document in documents if document.get("kind") == "Deployment")
    container = deployment["spec"]["template"]["spec"]["containers"][0]
    assert container["envFrom"] == [{"configMapRef": {"name": config_name}}]
    explicit_refs = {
        entry["name"]: entry["valueFrom"]["configMapKeyRef"]["name"]
        for entry in container["env"]
        if isinstance(entry.get("valueFrom"), dict) and isinstance(entry["valueFrom"].get("configMapKeyRef"), dict)
    }
    assert explicit_refs == {"REDIS_DB_HOST": config_name, "TYPESENSE_HOST": config_name}


def test_semantic_probe_attributes_the_durable_finalization_handoff_not_socket_presence() -> None:
    source = SEMANTIC_PROBE_SCRIPT.read_text(encoding="utf-8")

    assert "Pusher received process_conversation request:" in source
    assert 'textPayload:"Pusher received conversation_id:' not in source


def test_listener_canary_clone_is_digest_pinned_and_excluded_from_ordinary_service(
    prod_canary: SimpleNamespace,
) -> None:
    image = "gcr.io/based-hardware/backend@sha256:" + "6" * 64
    deployment = {
        "metadata": {"name": "prod-omi-backend-listen", "uid": "source-deployment", "generation": 7},
        "spec": {
            "replicas": 2,
            "selector": {"matchLabels": {"app": "backend-listen", "release": "prod"}},
            "template": {
                "metadata": {
                    "labels": {"app": "backend-listen", "release": "prod", "security-zone": "backend"},
                    "annotations": {"prometheus.io/scrape": "true", "policy.example/audit": "on"},
                },
                "spec": {
                    "serviceAccountName": "prod-omi-backend-listen",
                    "securityContext": {"runAsNonRoot": True},
                    "containers": [
                        {
                            "name": "backend-listen",
                            "image": "gcr.io/based-hardware/backend:old-tag",
                            "imagePullPolicy": "Always",
                            "env": [
                                {"name": "HOSTED_PUSHER_API_URL", "value": "http://pusher.omi.me"},
                                {"name": "OMI_ENV_STAGE", "value": "prod"},
                            ],
                        }
                    ],
                },
            },
        },
        "status": {"observedGeneration": 7, "readyReplicas": 2, "availableReplicas": 2},
    }
    service = {
        "metadata": {"name": "prod-omi-backend-listen"},
        "spec": {
            "selector": {"app": "backend-listen", "release": "prod"},
            "ports": [{"name": "http", "port": 8080, "targetPort": "http"}],
        },
    }
    pods = {
        "items": [
            {
                "status": {
                    "containerStatuses": [
                        {"name": "backend-listen", "ready": True, "imageID": f"docker-pullable://{image}"}
                    ]
                }
            },
            {
                "status": {
                    "containerStatuses": [
                        {"name": "backend-listen", "ready": True, "imageID": f"docker-pullable://{image}"}
                    ]
                }
            },
        ]
    }
    services = {
        "items": [
            service,
            {
                "metadata": {"name": "prod-backend-shared"},
                "spec": {"selector": {"security-zone": "backend", "release": "prod"}},
            },
        ]
    }
    network_policies = {
        "items": [
            {
                "spec": {
                    "podSelector": {"matchLabels": {"security-zone": "backend"}},
                }
            }
        ]
    }

    cloned_deployment, cloned_service, runtime_image = prod_canary.build_listener_resources(
        deployment,
        service,
        pods,
        namespace="prod-omi-backend",
        canary_name="prod-omi-listener-canary-987",
        pusher_url="http://prod-omi-pusher-canary-987:8080",
        services=services,
        network_policies=network_policies,
    )

    template = cloned_deployment["spec"]["template"]
    container = template["spec"]["containers"][0]
    assert runtime_image == image
    assert container["image"] == image
    assert container["imagePullPolicy"] == "IfNotPresent"
    assert {entry["name"]: entry.get("value") for entry in container["env"]}["HOSTED_PUSHER_API_URL"] == (
        "http://prod-omi-pusher-canary-987:8080"
    )
    assert template["spec"]["serviceAccountName"] == "prod-omi-backend-listen"
    assert template["spec"]["securityContext"] == {"runAsNonRoot": True}
    assert template["metadata"]["labels"]["security-zone"] == "backend"
    assert "prometheus.io/scrape" not in template["metadata"]["annotations"]
    ordinary_selector = service["spec"]["selector"]
    assert not all(template["metadata"]["labels"].get(key) == value for key, value in ordinary_selector.items())
    second_selector = services["items"][1]["spec"]["selector"]
    assert not all(template["metadata"]["labels"].get(key) == value for key, value in second_selector.items())
    assert cloned_service["spec"]["type"] == "ClusterIP"
    assert "annotations" not in cloned_service["metadata"]


def test_accepts_moved_production_main_with_unchanged_pusher_closure(verifier: SimpleNamespace, tmp_path: Path) -> None:
    repo, dev_sha, prod_sha = _promotion_repo(tmp_path, closure_change=False)
    deployment_receipt = _deployment_receipt(dev_sha)
    evidence = _evidence(verifier, deployment_receipt)
    run = _run(dev_sha)

    assert (
        validate(
            verifier,
            evidence,
            deployment_receipt,
            run,
            prod_source_sha=prod_sha,
            checkout_repository=repo,
        )
        == []
    )


def test_rejects_moved_production_main_when_the_pusher_source_closure_changed(
    verifier: SimpleNamespace, tmp_path: Path
) -> None:
    repo, dev_sha, prod_sha = _promotion_repo(tmp_path, closure_change=True)
    deployment_receipt = _deployment_receipt(dev_sha)
    evidence = _evidence(verifier, deployment_receipt)
    run = _run(dev_sha)

    errors = validate(
        verifier,
        evidence,
        deployment_receipt,
        run,
        prod_source_sha=prod_sha,
        checkout_repository=repo,
    )
    assert any("Pusher image source or chart changed" in error for error in errors)


def test_rejects_a_production_checkout_not_descended_from_the_qualified_source(
    verifier: SimpleNamespace, tmp_path: Path
) -> None:
    repo, dev_sha, prod_sha = _promotion_repo(tmp_path, closure_change=False)
    deployment_receipt = _deployment_receipt(prod_sha)
    evidence = _evidence(verifier, deployment_receipt)
    run = _run(prod_sha)

    errors = validate(
        verifier,
        evidence,
        deployment_receipt,
        run,
        prod_source_sha=dev_sha,
        checkout_repository=repo,
    )
    assert any("not an ancestor" in error for error in errors)


def test_rejects_prod_evidence_still_bound_to_the_dev_qualified_source(
    verifier: SimpleNamespace, tmp_path: Path
) -> None:
    """Prod run 35963192878's mirror: receipts stamped with the dev SHA while the
    checked-out production source moved on must fail every source binding."""
    repo, dev_sha, prod_sha = _promotion_repo(tmp_path, closure_change=False)
    deployment_receipt = _deployment_receipt(dev_sha)
    evidence = _evidence(verifier, deployment_receipt)
    run = _run(dev_sha)

    errors = validate(
        verifier,
        evidence,
        deployment_receipt,
        run,
        prod_source_sha=dev_sha,
        expected_canary_source_sha=prod_sha,
        checkout_repository=repo,
    )

    assert any("does not match the exact candidate receipt" in error for error in errors)
    assert any("one exact isolated candidate Pusher pod" in error for error in errors)
    assert any("semantic probe candidate does not match" in error for error in errors)
    assert any("run source does not match the checked-out production source" in error for error in errors)


def test_rejects_canary_run_head_sha_that_is_not_the_checked_out_production_source(
    verifier: SimpleNamespace,
    evidence: dict[str, object],
    deployment_receipt: dict[str, object],
    run: dict[str, object],
) -> None:
    canary_run = _canary_run(SOURCE_SHA)
    canary_run["head_sha"] = "d" * 40

    errors = validate(verifier, evidence, deployment_receipt, run, canary_run_override=canary_run)
    assert any("run source does not match the checked-out production source" in error for error in errors)


@pytest.mark.parametrize("expected_sha", ["", "D" * 40, "not-a-sha"])
def test_rejects_missing_or_malformed_expected_canary_source(
    verifier: SimpleNamespace,
    evidence: dict[str, object],
    deployment_receipt: dict[str, object],
    run: dict[str, object],
    expected_sha: str,
) -> None:
    errors = validate(
        verifier,
        evidence,
        deployment_receipt,
        run,
        expected_canary_source_sha=expected_sha,
    )
    assert any("canary source" in error and "full lowercase" in error for error in errors)


def test_qualification_phase_does_not_require_the_canary_source(
    verifier: SimpleNamespace,
    evidence: dict[str, object],
    deployment_receipt: dict[str, object],
    run: dict[str, object],
) -> None:
    errors = verifier.validate(
        evidence,
        deployment_receipt,
        {},
        {},
        run,
        expected_digest=DIGEST,
        expected_repository=REPOSITORY,
        expected_workflow_id=WORKFLOW_ID,
        expected_run_id=RUN_ID,
        expected_canary_workflow_id=0,
        expected_canary_run_id=0,
        require_canary=False,
    )
    assert errors == []


def test_final_phase_accepts_the_checked_out_source_and_rejects_digest_or_pod_drift(
    verifier: SimpleNamespace,
    evidence: dict[str, object],
    deployment_receipt: dict[str, object],
    run: dict[str, object],
) -> None:
    assert validate(verifier, evidence, deployment_receipt, run, require_final=True) == []

    drifted_digest = _final_deployment_receipt(SOURCE_SHA, config_sha256="sha256:" + "2" * 64)
    drifted_digest["image"] = {"repository": "gcr.io/based-hardware/pusher", "digest": "sha256:" + "f" * 64}
    digest_errors = validate(
        verifier,
        evidence,
        deployment_receipt,
        run,
        require_final=True,
        final_deployment_receipt_override=drifted_digest,
    )
    assert any("exact promoted image" in error for error in digest_errors)

    drifted_pod = _final_deployment_receipt(SOURCE_SHA, config_sha256="sha256:" + "2" * 64)
    identity = drifted_pod["live_identity"]
    assert isinstance(identity, dict)
    pods = identity["pods"]
    assert isinstance(pods, list) and isinstance(pods[0], dict)
    pods[0]["image_id"] = "repo@sha256:" + "f" * 64
    pod_errors = validate(
        verifier,
        evidence,
        deployment_receipt,
        run,
        require_final=True,
        final_deployment_receipt_override=drifted_pod,
    )
    assert any("fully ready shared production Pusher" in error for error in pod_errors)


def test_final_phase_rejects_a_receipt_bound_to_the_dev_qualified_source(
    verifier: SimpleNamespace, tmp_path: Path
) -> None:
    repo, dev_sha, prod_sha = _promotion_repo(tmp_path, closure_change=False)
    deployment_receipt = _deployment_receipt(dev_sha)
    evidence = _evidence(verifier, deployment_receipt)
    run = _run(dev_sha)
    final = _final_deployment_receipt(dev_sha, config_sha256="sha256:" + "2" * 64)

    errors = validate(
        verifier,
        evidence,
        deployment_receipt,
        run,
        prod_source_sha=prod_sha,
        checkout_repository=repo,
        require_final=True,
        final_deployment_receipt_override=final,
    )
    assert any("does not match the checked-out production source" in error for error in errors)


def test_rejects_canary_deployment_receipt_run_id_mismatch(
    verifier: SimpleNamespace,
    evidence: dict[str, object],
    deployment_receipt: dict[str, object],
    run: dict[str, object],
) -> None:
    receipt = _canary_deployment_receipt(SOURCE_SHA)
    receipt["run_id"] = CANARY_RUN_ID + 1

    errors = validate(verifier, evidence, deployment_receipt, run, canary_deployment_receipt_override=receipt)
    assert any("one exact isolated candidate Pusher pod" in error for error in errors)
    assert not any("does not match the exact candidate receipt" in error for error in errors)


def test_rejects_canary_pod_image_id_that_is_not_the_promoted_digest(
    verifier: SimpleNamespace,
    evidence: dict[str, object],
    deployment_receipt: dict[str, object],
    run: dict[str, object],
) -> None:
    receipt = _canary_deployment_receipt(SOURCE_SHA)
    identity = receipt["live_identity"]
    assert isinstance(identity, dict)
    pods = identity["pods"]
    assert isinstance(pods, list) and isinstance(pods[0], dict)
    pods[0]["image_id"] = "repo@sha256:" + "f" * 64

    errors = validate(verifier, evidence, deployment_receipt, run, canary_deployment_receipt_override=receipt)
    assert any("one exact isolated candidate Pusher pod" in error for error in errors)
    assert not any("does not match the exact candidate receipt" in error for error in errors)


@pytest.mark.parametrize(
    ("surface", "name"),
    [
        ("pusher", f"prod-omi-pusher-canary-{CANARY_RUN_ID}0"),
        ("listener", f"prod-omi-listener-canary-{CANARY_RUN_ID}0"),
    ],
)
def test_rejects_canary_deployment_names_that_only_share_the_prefix(
    verifier: SimpleNamespace,
    evidence: dict[str, object],
    deployment_receipt: dict[str, object],
    run: dict[str, object],
    surface: str,
    name: str,
) -> None:
    if surface == "pusher":
        receipt = _canary_deployment_receipt(SOURCE_SHA)
        identity = receipt["live_identity"]
        assert isinstance(identity, dict)
        identity["deployment_name"] = name
        errors = validate(
            verifier,
            evidence,
            deployment_receipt,
            run,
            canary_deployment_receipt_override=receipt,
        )
        assert any("one exact isolated candidate Pusher pod" in error for error in errors)
    else:

        def mutate(canary: dict[str, object]) -> None:
            deployment_identity = canary["deployment_identity"]
            assert isinstance(deployment_identity, dict)
            listener = deployment_identity["listener"]
            assert isinstance(listener, dict)
            listener["deployment_name"] = name

        errors = validate(verifier, evidence, deployment_receipt, run, canary_mutator=mutate)
        assert any("isolated digest-pinned listener clone" in error for error in errors)


def test_accepts_final_phase_with_distinct_dev_and_prod_sources(verifier: SimpleNamespace, tmp_path: Path) -> None:
    repo, dev_sha, prod_sha = _promotion_repo(tmp_path, closure_change=False)
    deployment_receipt = _deployment_receipt(dev_sha)
    evidence = _evidence(verifier, deployment_receipt)
    run = _run(dev_sha)

    assert (
        validate(
            verifier,
            evidence,
            deployment_receipt,
            run,
            prod_source_sha=prod_sha,
            checkout_repository=repo,
            require_final=True,
        )
        == []
    )
