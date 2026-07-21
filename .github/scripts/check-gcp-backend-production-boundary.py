#!/usr/bin/env python3
"""Keep production Cloud Run deployment inside its supported boundary."""

from __future__ import annotations

from pathlib import Path
import re

WORKFLOW = Path(".github/workflows/gcp_backend.yml")
EARLY_PROD_ALL_REJECTION = 'if [[ "$DEPLOY_ENVIRONMENT" == "prod" && "$DEPLOY_TARGETS" == "all" ]]; then'
CANONICAL_AUDIENCE = '''identity_audience="$(gcloud run services describe "${{ env.SERVICE }}" \\
            --project="${{ vars.GCP_PROJECT_ID }}" --region="${{ env.REGION }}" --format='value(status.url)')"'''
AUDIENCE_DIFFERENCE_GUARD = '''[[ "$identity_audience" != "$candidate_url" ]] || {
            echo 'ERROR: canonical Cloud Run IAM audience must differ from tagged candidate URL' >&2; exit 1;
          }'''
CANDIDATE_REQUEST_TARGET = '--candidate-url "${{ steps.transcription-candidate.outputs.url }}"'


def _validation_job(text: str) -> str:
    match = re.search(r"(?ms)^  validate-production-boundary:\n(.*?)(?=^  [a-zA-Z0-9_-]+:\n|\Z)", text)
    return match.group(1) if match else ""


def _rejects_before_side_effects(text: str) -> bool:
    job = _validation_job(text)
    rejection = job.find(EARLY_PROD_ALL_REJECTION)
    if rejection < 0:
        return False
    before = job[:rejection]
    # The rejection is deliberately the validation job's first executable
    # action. Any action or shell step above it can acquire credentials, fetch
    # source, or mutate external state before the unsupported request stops.
    return not re.search(r"(?m)^\s*-\s+(?:uses:|run:)", before)


def validate(root: Path) -> list[str]:
    path = root / WORKFLOW
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    errors: list[str] = []
    if text.count(EARLY_PROD_ALL_REJECTION) != 1:
        errors.append("gcp_backend.yml must reject exactly environment=prod, deploy_targets=all before side effects")
    elif not _rejects_before_side_effects(text):
        errors.append("gcp_backend.yml must reject prod,all before checkout, auth, credentials, or shell side effects")
    if CANONICAL_AUDIENCE not in text or "BACKEND_CLOUD_RUN_IAM_AUDIENCE" in text:
        errors.append("gcp_backend.yml must derive the Cloud Run IAM audience only from backend status.url")
    if AUDIENCE_DIFFERENCE_GUARD not in text:
        errors.append("gcp_backend.yml must reject a canonical IAM audience equal to the tagged candidate URL")
    if text.count(CANDIDATE_REQUEST_TARGET) != 1:
        errors.append("gcp_backend.yml must retain the tagged candidate URL as the production probe request target")
    return errors


if __name__ == "__main__":
    raise SystemExit(1 if validate(Path(".")) else 0)
