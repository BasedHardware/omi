"""Behavioral regression tests for Pusher dev-to-prod digest qualification."""

from __future__ import annotations

import runpy
from pathlib import Path
from types import SimpleNamespace

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "verify_pusher_promotion_evidence.py"
DIGEST = "sha256:" + "a" * 64
SOURCE_SHA = "b" * 40
RUN_ID = 321
WORKFLOW_ID = 654
REPOSITORY = "gcr.io/based-hardware-dev/pusher"


@pytest.fixture(scope="module")
def verifier() -> SimpleNamespace:
    return SimpleNamespace(**runpy.run_path(str(SCRIPT)))


@pytest.fixture
def evidence() -> dict[str, object]:
    return {
        "schema_version": 1,
        "environment": "development",
        "image_digest": DIGEST,
        "image_repository": REPOSITORY,
        "run_id": RUN_ID,
        "source_sha": SOURCE_SHA,
        "workflow": "gcp_backend_pusher_auto_deploy.yml",
    }


@pytest.fixture
def run() -> dict[str, object]:
    return {
        "id": RUN_ID,
        "workflow_id": WORKFLOW_ID,
        "event": "push",
        "head_branch": "main",
        "head_sha": SOURCE_SHA,
        "status": "completed",
        "conclusion": "success",
    }


def validate(verifier: SimpleNamespace, evidence: dict[str, object], run: dict[str, object]) -> list[str]:
    return verifier.validate(
        evidence,
        run,
        expected_digest=DIGEST,
        expected_repository=REPOSITORY,
        expected_workflow_id=WORKFLOW_ID,
        expected_run_id=RUN_ID,
    )


def test_accepts_an_exact_digest_from_the_successful_main_dev_run(
    verifier: SimpleNamespace, evidence: dict[str, object], run: dict[str, object]
) -> None:
    assert validate(verifier, evidence, run) == []


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
    run: dict[str, object],
    target: str,
    key: str,
    value: object,
    expected: str,
) -> None:
    (evidence if target == "evidence" else run)[key] = value

    assert any(expected in error for error in validate(verifier, evidence, run))


def test_rejects_ambiguous_evidence_schema(
    verifier: SimpleNamespace, evidence: dict[str, object], run: dict[str, object]
) -> None:
    evidence["untrusted"] = True

    assert any("unexpected schema" in error for error in validate(verifier, evidence, run))
