#!/usr/bin/env python3
"""Validate the immutable Pusher artifact selected from a dev qualification run.

The production workflow downloads a small, non-secret attestation artifact from
the selected development Pusher deployment run.  This verifier binds the digest
to that successful run's immutable source identity before the workflow can copy
the image to the production registry or mutate the production Helm release.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import re
from pathlib import Path
from typing import Any

DIGEST_RE = re.compile(r"^sha256:[a-f0-9]{64}$")
SHA_RE = re.compile(r"^[a-f0-9]{40}$")
SCHEMA_VERSION = 2
RECEIPT_SCHEMA_VERSION = 1
ROOT = Path(__file__).resolve().parents[2]
CONTRACT_FILES = (
    ROOT / "backend/scripts/pusher_release_receipt.py",
    ROOT / "backend/scripts/pusher_semantic_probe.py",
    ROOT / "backend/scripts/pusher_prod_canary.py",
    ROOT / "backend/scripts/verify_pusher_live_alert_route.py",
    ROOT / "backend/scripts/runtime_env_capability_contracts.py",
    ROOT / "backend/scripts/runtime_env_validation/manifest.py",
    ROOT / "backend/scripts/validate-backend-runtime-env.py",
    ROOT / "backend/config/memory_rollout.py",
    ROOT / "backend/deploy/runtime_env/_base.yaml",
    ROOT / "backend/deploy/runtime_env/dev.overlay.yaml",
    ROOT / "backend/deploy/runtime_env/prod.overlay.yaml",
    ROOT / "backend/deploy/runtime_env.yaml",
    ROOT / "backend/scripts/verify_pusher_promotion_evidence.py",
    ROOT / "backend/testing/release_fixtures/transcription-release-probe.json",
    ROOT / "backend/testing/release_fixtures/transcription-release-probe.wav",
    ROOT / ".github/workflows/gcp_backend_pusher_auto_deploy.yml",
    ROOT / ".github/workflows/gcp_backend_pusher.yml",
)


class EvidenceError(ValueError):
    """The selected development run cannot prove a safe promotion."""


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise EvidenceError(f"could not read JSON evidence {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise EvidenceError(f"{path}: expected a JSON object")
    return value


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def contract_fingerprint() -> str:
    return canonical_sha256(
        {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest() for path in CONTRACT_FILES}
    )


def _timestamp(value: Any, label: str, errors: list[str]) -> datetime | None:
    if not isinstance(value, str):
        errors.append(f"{label} must be an RFC3339 timestamp")
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        errors.append(f"{label} must be an RFC3339 timestamp")
        return None
    if parsed.tzinfo is None:
        errors.append(f"{label} must include a timezone")
        return None
    return parsed.astimezone(timezone.utc)


def _validate_semantic_probe(probe: Any, *, source_sha: Any, digest: Any, deployment_receipt_sha256: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(probe, dict):
        return ["semantic probe evidence is missing"]
    if probe.get("status") != "PASS":
        return ["semantic probe status must be PASS; NOT_RUN, failure, and missing evidence block production"]
    expected_fields = {
        "schema_version",
        "status",
        "evidence_id",
        "candidate",
        "window",
        "samples",
        "synthetic_uid_class",
        "producer_observation",
        "consumer_readback",
    }
    if set(probe) != expected_fields:
        errors.append("semantic probe evidence has an unexpected schema")
    if probe.get("schema_version") != 1:
        errors.append("semantic probe evidence must use schema_version=1")
    if probe.get("synthetic_uid_class") != "firebase_release_probe":
        errors.append("semantic probe must use the isolated Firebase release-probe principal")
    if probe.get("producer_observation") != {"status": "PASS", "candidate_pod_count": 1}:
        errors.append("semantic probe must observe the run on an exact candidate Pusher pod")
    if probe.get("consumer_readback") != {"status": "PASS"}:
        errors.append("semantic probe must complete authenticated durable consumer read-back")
    if not isinstance(probe.get("evidence_id"), str) or not probe["evidence_id"].strip():
        errors.append("semantic probe evidence_id must be non-empty")
    candidate = probe.get("candidate") if isinstance(probe.get("candidate"), dict) else {}
    if candidate != {
        "source_sha": source_sha,
        "image_digest": digest,
        "deployment_receipt_sha256": deployment_receipt_sha256,
    }:
        errors.append("semantic probe candidate does not match the exact deployed candidate receipt")
    window = probe.get("window") if isinstance(probe.get("window"), dict) else {}
    if set(window) != {"started_at", "ended_at", "closed_at"}:
        errors.append("semantic probe window must declare started_at, ended_at, and closed_at")
    started = _timestamp(window.get("started_at"), "semantic probe started_at", errors)
    ended = _timestamp(window.get("ended_at"), "semantic probe ended_at", errors)
    closed = _timestamp(window.get("closed_at"), "semantic probe closed_at", errors)
    if started is not None and ended is not None and closed is not None and not (started < ended <= closed):
        errors.append("semantic probe window must be closed after its complete observation interval")
    if closed is not None and closed > datetime.now(timezone.utc):
        errors.append("semantic probe closed_at cannot be in the future")
    samples = probe.get("samples") if isinstance(probe.get("samples"), dict) else {}
    if set(samples) != {"attempted", "succeeded", "failed"}:
        errors.append("semantic probe samples must declare attempted, succeeded, and failed")
    attempted = samples.get("attempted")
    succeeded = samples.get("succeeded")
    failed = samples.get("failed")
    if (
        not isinstance(attempted, int)
        or isinstance(attempted, bool)
        or attempted < 1
        or succeeded != attempted
        or failed != 0
    ):
        errors.append("semantic probe PASS requires at least one sample, all successful and none failed")
    return errors


def _validate_canary(
    canary: Any,
    semantic_evidence: dict[str, Any],
    canary_run: dict[str, Any],
    canary_deployment_receipt: dict[str, Any],
    *,
    source_sha: Any,
    digest: Any,
    qualification_deployment_receipt_sha256: Any,
    expected_canary_workflow_id: int,
    expected_canary_run_id: int,
) -> list[str]:
    errors: list[str] = []
    if not isinstance(canary, dict):
        return ["production canary evidence is missing"]
    if canary.get("status") != "PASS":
        return ["production canary status must be PASS; unattributable or NOT_RUN evidence blocks promotion"]
    expected_fields = {
        "schema_version",
        "status",
        "evidence_id",
        "candidate",
        "window",
        "sessions",
        "outcomes",
        "approval_run_id",
        "protected_environment",
        "deployment_identity",
        "semantic_evidence_sha256",
    }
    if set(canary) != expected_fields:
        errors.append("production canary evidence has an unexpected schema")
    if canary.get("schema_version") != 1:
        errors.append("production canary evidence must use schema_version=1")
    if canary.get("approval_run_id") != expected_canary_run_id:
        errors.append("production canary approval_run_id does not match the selected protected run")
    if canary.get("protected_environment") != "prod":
        errors.append("production canary evidence must be generated under the prod environment")
    candidate = canary.get("candidate") if isinstance(canary.get("candidate"), dict) else {}
    if candidate != {
        "source_sha": source_sha,
        "image_digest": digest,
        "qualification_deployment_receipt_sha256": qualification_deployment_receipt_sha256,
        "canary_deployment_receipt_sha256": canonical_sha256(canary_deployment_receipt),
    }:
        errors.append("production canary evidence does not match the exact candidate receipt")
    canary_image = (
        canary_deployment_receipt.get("image") if isinstance(canary_deployment_receipt.get("image"), dict) else {}
    )
    pusher_identity = (
        canary_deployment_receipt.get("live_identity")
        if isinstance(canary_deployment_receipt.get("live_identity"), dict)
        else {}
    )
    identity = canary.get("deployment_identity") if isinstance(canary.get("deployment_identity"), dict) else {}
    listener_identity = identity.get("listener") if isinstance(identity.get("listener"), dict) else {}
    if (
        canary_deployment_receipt.get("environment") != "prod"
        or canary_deployment_receipt.get("source_sha") != source_sha
        or canary_image.get("digest") != digest
        or identity.get("pusher") != pusher_identity
        or pusher_identity.get("replicas") != 1
        or pusher_identity.get("ready_replicas") != 1
        or not str(pusher_identity.get("deployment_name", "")).startswith("prod-omi-pusher-canary-")
    ):
        errors.append("production canary does not prove one exact isolated candidate Pusher pod")
    if (
        listener_identity.get("ordinary_service_selector_excluded") is not True
        or listener_identity.get("pusher_url_class") != "isolated_cluster_service"
        or not str(listener_identity.get("deployment_name", "")).startswith("prod-omi-listener-canary-")
        or not isinstance(listener_identity.get("runtime_image"), str)
        or "@sha256:" not in listener_identity["runtime_image"]
        or not listener_identity.get("deployment_uid")
        or not listener_identity.get("pod_uid")
        or not isinstance(listener_identity.get("service_selectors_evaluated"), int)
        or isinstance(listener_identity.get("service_selectors_evaluated"), bool)
        or listener_identity["service_selectors_evaluated"] < 1
        or not isinstance(listener_identity.get("service_selector_snapshot_sha256"), str)
        or not DIGEST_RE.fullmatch(listener_identity["service_selector_snapshot_sha256"])
    ):
        errors.append("production canary does not prove an isolated digest-pinned listener clone")
    if not isinstance(canary.get("semantic_evidence_sha256"), str) or not DIGEST_RE.fullmatch(
        canary["semantic_evidence_sha256"]
    ):
        errors.append("production canary must bind its exact semantic evidence")
    elif canary["semantic_evidence_sha256"] != canonical_sha256(semantic_evidence):
        errors.append("production canary semantic evidence hash does not match the supplied probe receipt")
    errors.extend(
        _validate_semantic_probe(
            semantic_evidence,
            source_sha=source_sha,
            digest=digest,
            deployment_receipt_sha256=canonical_sha256(canary_deployment_receipt),
        )
    )
    if not isinstance(canary.get("evidence_id"), str) or not canary["evidence_id"].strip():
        errors.append("production canary evidence_id must be non-empty")
    window = canary.get("window") if isinstance(canary.get("window"), dict) else {}
    started = _timestamp(window.get("started_at"), "production canary started_at", errors)
    ended = _timestamp(window.get("ended_at"), "production canary ended_at", errors)
    closed = _timestamp(window.get("closed_at"), "production canary closed_at", errors)
    if set(window) != {"started_at", "ended_at", "closed_at"}:
        errors.append("production canary window must declare started_at, ended_at, and closed_at")
    if started is not None and ended is not None and closed is not None and not (started < ended <= closed):
        errors.append("production canary window must be closed after its complete observation interval")
    if closed is not None and closed > datetime.now(timezone.utc):
        errors.append("production canary closed_at cannot be in the future")
    sessions = canary.get("sessions") if isinstance(canary.get("sessions"), dict) else {}
    attributed = sessions.get("attributed")
    if set(sessions) != {"attributed", "unattributed"}:
        errors.append("production canary sessions must declare attributed and unattributed counts")
    if (
        not isinstance(attributed, int)
        or isinstance(attributed, bool)
        or attributed < 1
        or sessions.get("unattributed") != 0
    ):
        errors.append("production canary PASS requires attributable sessions and zero unattributed sessions")
    outcomes = canary.get("outcomes") if isinstance(canary.get("outcomes"), dict) else {}
    if set(outcomes) != {"evaluated", "terminal_success", "terminal_failure", "pending"}:
        errors.append("production canary outcomes must declare evaluated and every terminal or pending class")
    evaluated = outcomes.get("evaluated")
    counted_outcomes = [outcomes.get(name) for name in ("terminal_success", "terminal_failure", "pending")]
    if (
        not isinstance(evaluated, int)
        or isinstance(evaluated, bool)
        or evaluated < 1
        or any(not isinstance(value, int) or isinstance(value, bool) or value < 0 for value in counted_outcomes)
        or sum(counted_outcomes) != evaluated
        or outcomes.get("terminal_success") != evaluated
        or outcomes.get("terminal_failure") != 0
        or outcomes.get("pending") != 0
    ):
        errors.append("production canary PASS requires complete accounting with every outcome terminal-successful")
    if isinstance(attributed, int) and not isinstance(attributed, bool) and isinstance(evaluated, int):
        if attributed != evaluated:
            errors.append("production canary must evaluate every and only attributable candidate session")
    if canary_run.get("id") != expected_canary_run_id:
        errors.append("selected canary workflow API result does not match the requested run id")
    if canary_run.get("workflow_id") != expected_canary_workflow_id:
        errors.append("production canary receipt was not emitted by the protected Pusher workflow")
    if canary_run.get("event") != "workflow_dispatch" or canary_run.get("head_branch") != "main":
        errors.append("production canary receipt must come from a protected main workflow dispatch")
    if canary_run.get("status") not in {"in_progress", "completed"}:
        errors.append("production canary receipt run is not active or successfully completed")
    if canary_run.get("status") == "completed" and canary_run.get("conclusion") != "success":
        errors.append("production canary receipt run did not complete successfully")
    if canary_run.get("head_sha") != source_sha:
        errors.append("production canary receipt run source does not match the qualified source")
    return errors


def _validate_final_deployment(
    final_receipt: Any,
    canary_receipt: dict[str, Any],
    *,
    source_sha: Any,
    digest: Any,
    repository: Any,
    run_id: int,
) -> list[str]:
    errors: list[str] = []
    if not isinstance(final_receipt, dict):
        return ["final production deployment receipt is missing"]
    if final_receipt.get("schema_version") != RECEIPT_SCHEMA_VERSION:
        errors.append(f"final deployment receipt must use schema_version={RECEIPT_SCHEMA_VERSION}")
    if set(final_receipt) != {
        "schema_version",
        "environment",
        "recorded_at",
        "run_id",
        "source_sha",
        "image",
        "rendered_chart_sha256",
        "config_sha256",
        "expected_pod_template_sha256",
        "live_pod_template_sha256",
        "live_identity",
    }:
        errors.append("final deployment receipt has an unexpected schema")
    image = final_receipt.get("image") if isinstance(final_receipt.get("image"), dict) else {}
    identity = final_receipt.get("live_identity") if isinstance(final_receipt.get("live_identity"), dict) else {}
    if final_receipt.get("environment") != "prod" or final_receipt.get("source_sha") != source_sha:
        errors.append("final deployment receipt does not match the qualified production source")
    if image != {"repository": repository, "digest": digest}:
        errors.append("final deployment receipt does not match the exact promoted image")
    if final_receipt.get("run_id") != run_id:
        errors.append("final deployment receipt was not recorded by the protected canary run")
    if final_receipt.get("expected_pod_template_sha256") != final_receipt.get("live_pod_template_sha256"):
        errors.append("final production PodTemplate does not match the expected render")
    if (
        identity.get("namespace") != "prod-omi-backend"
        or identity.get("deployment_name") != "prod-omi-pusher"
        or not isinstance(identity.get("replicas"), int)
        or isinstance(identity.get("replicas"), bool)
        or identity.get("replicas", 0) < 1
        or identity.get("ready_replicas") != identity.get("replicas")
        or identity.get("observed_generation") != identity.get("generation")
        or not isinstance(identity.get("pods"), list)
        or len(identity.get("pods", [])) != identity.get("replicas")
        or any(
            not isinstance(pod, dict) or not str(pod.get("image_id", "")).endswith(f"@{digest}")
            for pod in identity.get("pods", [])
        )
    ):
        errors.append("final deployment receipt does not prove the fully ready shared production Pusher")
    if final_receipt.get("config_sha256") != canary_receipt.get("config_sha256"):
        errors.append("final production ConfigMap does not match the isolated canary-qualified ConfigMap")
    return errors


def validate(
    evidence: dict[str, Any],
    deployment_receipt: dict[str, Any],
    canary_evidence: dict[str, Any],
    canary_run: dict[str, Any],
    run: dict[str, Any],
    *,
    expected_digest: str,
    expected_repository: str,
    expected_workflow_id: int,
    expected_run_id: int,
    expected_canary_workflow_id: int,
    expected_canary_run_id: int,
    canary_deployment_receipt: dict[str, Any] | None = None,
    canary_semantic_evidence: dict[str, Any] | None = None,
    final_deployment_receipt: dict[str, Any] | None = None,
    expected_final_repository: str = "",
    require_canary: bool = True,
    require_final: bool = False,
) -> list[str]:
    """Return every missing immutable-promotion proof without exposing secrets."""

    errors: list[str] = []
    expected_fields = {
        "schema_version",
        "qualification_status",
        "environment",
        "image_digest",
        "image_repository",
        "run_id",
        "source_sha",
        "workflow",
        "rendered_chart_sha256",
        "config_sha256",
        "expected_pod_template_sha256",
        "live_pod_template_sha256",
        "deployment_receipt_sha256",
        "contract_sha256",
        "semantic_probe",
    }
    if set(evidence) != expected_fields:
        errors.append("qualification evidence has an unexpected schema")
    if evidence.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"qualification evidence must use schema_version={SCHEMA_VERSION}")
    if evidence.get("qualification_status") != "PASS":
        errors.append("qualification status must be PASS; BLOCKED evidence cannot promote")
    if evidence.get("environment") != "development":
        errors.append("qualification evidence must be from the development environment")
    if evidence.get("workflow") != "gcp_backend_pusher_auto_deploy.yml":
        errors.append("qualification evidence must be emitted by the automatic dev Pusher workflow")

    digest = evidence.get("image_digest")
    if not isinstance(digest, str) or not DIGEST_RE.fullmatch(digest):
        errors.append("qualification evidence must contain an exact sha256 image_digest")
    elif digest != expected_digest:
        errors.append("requested production digest does not match development qualification evidence")
    if not DIGEST_RE.fullmatch(expected_digest):
        errors.append("requested production digest must be an exact sha256 digest")

    if evidence.get("image_repository") != expected_repository:
        errors.append("qualification evidence repository does not match the development Pusher registry")
    if evidence.get("run_id") != expected_run_id:
        errors.append("qualification evidence run_id does not match the selected workflow run")

    source_sha = evidence.get("source_sha")
    if not isinstance(source_sha, str) or not SHA_RE.fullmatch(source_sha):
        errors.append("qualification evidence must contain a full lowercase source SHA")
    if run.get("id") != expected_run_id:
        errors.append("selected workflow API result does not match the requested run id")
    if run.get("workflow_id") != expected_workflow_id:
        errors.append("selected workflow run is not the automatic dev Pusher workflow")
    if run.get("event") != "push" or run.get("head_branch") != "main":
        errors.append("selected workflow run must be a main push qualification")
    if run.get("status") != "completed" or run.get("conclusion") != "success":
        errors.append("selected workflow run did not complete successfully")
    if isinstance(source_sha, str) and run.get("head_sha") != source_sha:
        errors.append("qualification evidence source SHA does not match the successful workflow run")
    receipt_sha256 = canonical_sha256(deployment_receipt)
    if evidence.get("deployment_receipt_sha256") != receipt_sha256:
        errors.append("qualification evidence does not bind the exact deployment receipt")
    if deployment_receipt.get("schema_version") != RECEIPT_SCHEMA_VERSION:
        errors.append(f"deployment receipt must use schema_version={RECEIPT_SCHEMA_VERSION}")
    if set(deployment_receipt) != {
        "schema_version",
        "environment",
        "recorded_at",
        "run_id",
        "source_sha",
        "image",
        "rendered_chart_sha256",
        "config_sha256",
        "expected_pod_template_sha256",
        "live_pod_template_sha256",
        "live_identity",
    }:
        errors.append("deployment receipt has an unexpected schema")
    if deployment_receipt.get("environment") != "development":
        errors.append("deployment receipt must describe development")
    receipt_image = deployment_receipt.get("image") if isinstance(deployment_receipt.get("image"), dict) else {}
    if receipt_image != {"repository": expected_repository, "digest": expected_digest}:
        errors.append("deployment receipt image does not match the exact qualified candidate")
    if deployment_receipt.get("source_sha") != source_sha or deployment_receipt.get("run_id") != expected_run_id:
        errors.append("deployment receipt source or run does not match qualification evidence")
    for field in ("rendered_chart_sha256", "config_sha256"):
        value = evidence.get(field)
        if not isinstance(value, str) or not DIGEST_RE.fullmatch(value):
            errors.append(f"qualification evidence must contain an exact {field}")
        elif deployment_receipt.get(field) != value:
            errors.append(f"qualification evidence {field} contradicts the live deployment receipt")
    expected_template_sha = evidence.get("expected_pod_template_sha256")
    live_template_sha = evidence.get("live_pod_template_sha256")
    if (
        not isinstance(expected_template_sha, str)
        or not DIGEST_RE.fullmatch(expected_template_sha)
        or live_template_sha != expected_template_sha
        or deployment_receipt.get("expected_pod_template_sha256") != expected_template_sha
        or deployment_receipt.get("live_pod_template_sha256") != live_template_sha
    ):
        errors.append("qualification evidence does not prove expected and live Pusher PodTemplate semantic equality")
    live_identity = deployment_receipt.get("live_identity")
    if not isinstance(live_identity, dict):
        errors.append("deployment receipt does not prove a fully ready live candidate identity")
    else:
        replicas = live_identity.get("replicas")
        pods = live_identity.get("pods")
        if (
            not isinstance(replicas, int)
            or isinstance(replicas, bool)
            or replicas < 1
            or live_identity.get("ready_replicas") != replicas
            or live_identity.get("observed_generation") != live_identity.get("generation")
            or live_identity.get("namespace") != "dev-omi-backend"
            or live_identity.get("deployment_name") != "dev-omi-pusher"
            or not isinstance(live_identity.get("deployment_uid"), str)
            or not live_identity["deployment_uid"]
            or not isinstance(pods, list)
            or len(pods) != replicas
            or any(
                not isinstance(pod, dict)
                or set(pod) != {"name", "uid", "image_id"}
                or not isinstance(pod.get("name"), str)
                or not pod["name"]
                or not isinstance(pod.get("uid"), str)
                or not pod["uid"]
                or not isinstance(pod.get("image_id"), str)
                or not pod["image_id"].endswith(f"@{expected_digest}")
                for pod in pods
            )
        ):
            errors.append("deployment receipt does not prove a fully ready live candidate identity")
    if evidence.get("contract_sha256") != contract_fingerprint():
        errors.append("qualification evidence contract does not match the current promotion contract")
    errors.extend(
        _validate_semantic_probe(
            evidence.get("semantic_probe"),
            source_sha=source_sha,
            digest=digest,
            deployment_receipt_sha256=receipt_sha256,
        )
    )
    if require_canary:
        errors.extend(
            _validate_canary(
                canary_evidence,
                canary_semantic_evidence or {},
                canary_run,
                canary_deployment_receipt or {},
                source_sha=source_sha,
                digest=digest,
                qualification_deployment_receipt_sha256=receipt_sha256,
                expected_canary_workflow_id=expected_canary_workflow_id,
                expected_canary_run_id=expected_canary_run_id,
            )
        )
    if require_final:
        errors.extend(
            _validate_final_deployment(
                final_deployment_receipt,
                canary_deployment_receipt or {},
                source_sha=source_sha,
                digest=digest,
                repository=expected_final_repository,
                run_id=expected_canary_run_id,
            )
        )
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--deployment-receipt", type=Path, required=True)
    parser.add_argument("--phase", choices=("qualification", "canary", "final"), default="canary")
    parser.add_argument("--canary-evidence", type=Path)
    parser.add_argument("--canary-deployment-receipt", type=Path)
    parser.add_argument("--canary-semantic-evidence", type=Path)
    parser.add_argument("--canary-run-json", type=Path)
    parser.add_argument("--final-deployment-receipt", type=Path)
    parser.add_argument("--expected-final-repository", default="")
    parser.add_argument("--run-json", type=Path, required=True)
    parser.add_argument("--expected-digest", required=True)
    parser.add_argument("--expected-repository", required=True)
    parser.add_argument("--expected-workflow-id", type=int, required=True)
    parser.add_argument("--expected-run-id", type=int, required=True)
    parser.add_argument("--expected-canary-workflow-id", type=int, default=0)
    parser.add_argument("--expected-canary-run-id", type=int, default=0)
    args = parser.parse_args()

    try:
        failures = validate(
            load_json(args.evidence),
            load_json(args.deployment_receipt),
            load_json(args.canary_evidence) if args.canary_evidence else {},
            load_json(args.canary_run_json) if args.canary_run_json else {},
            load_json(args.run_json),
            expected_digest=args.expected_digest,
            expected_repository=args.expected_repository,
            expected_workflow_id=args.expected_workflow_id,
            expected_run_id=args.expected_run_id,
            expected_canary_workflow_id=args.expected_canary_workflow_id,
            expected_canary_run_id=args.expected_canary_run_id,
            canary_deployment_receipt=(
                load_json(args.canary_deployment_receipt) if args.canary_deployment_receipt else None
            ),
            canary_semantic_evidence=(
                load_json(args.canary_semantic_evidence) if args.canary_semantic_evidence else None
            ),
            final_deployment_receipt=(
                load_json(args.final_deployment_receipt) if args.final_deployment_receipt else None
            ),
            expected_final_repository=args.expected_final_repository,
            require_canary=args.phase in {"canary", "final"},
            require_final=args.phase == "final",
        )
    except EvidenceError as exc:
        failures = [str(exc)]
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}")
        return 1
    print("OK: selected Pusher candidate has exact deployment, semantic-probe, and attributable-canary evidence.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
