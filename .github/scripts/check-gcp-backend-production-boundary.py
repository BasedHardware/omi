#!/usr/bin/env python3
"""Keep the canonical production backend deployment inside its supported boundary."""

from __future__ import annotations

from pathlib import Path

WORKFLOW = Path(".github/workflows/gcp_backend.yml")
OBSOLETE_PROD_ALL_REJECTION = 'if [[ "$DEPLOY_ENVIRONMENT" == "prod" && "$DEPLOY_TARGETS" == "all" ]]; then'
PROD_CANDIDATE_GATE = "if: ${{ github.event.inputs.environment == 'prod' }}"
CANDIDATE_TAG = "${{ format('--tag={0}', env.TRANSCRIPTION_CANDIDATE_TAG) }}"
CANONICAL_AUDIENCE = '''identity_audience="$(gcloud run services describe "${{ env.SERVICE }}" \\
            --project="${{ vars.GCP_PROJECT_ID }}" --region="${{ env.REGION }}" --format='value(status.url)')"'''
AUDIENCE_DIFFERENCE_GUARD = '''[[ "$identity_audience" != "$candidate_url" ]] || {
            echo 'ERROR: canonical Cloud Run IAM audience must differ from tagged candidate URL' >&2; exit 1;
          }'''
CANDIDATE_REQUEST_TARGET = '--candidate-url "${{ steps.transcription-candidate.outputs.url }}"'


def validate(root: Path) -> list[str]:
    path = root / WORKFLOW
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    errors: list[str] = []
    if OBSOLETE_PROD_ALL_REJECTION in text:
        errors.append("gcp_backend.yml must permit environment=prod, deploy_targets=all through the canonical deploy path")
    if text.count(PROD_CANDIDATE_GATE) != 2:
        errors.append("gcp_backend.yml must gate both production candidate-probe steps before full-stack mutation")
    if CANDIDATE_TAG not in text:
        errors.append("gcp_backend.yml must tag the no-traffic production candidate before validation")
    if CANONICAL_AUDIENCE not in text or "BACKEND_CLOUD_RUN_IAM_AUDIENCE" in text:
        errors.append("gcp_backend.yml must derive the Cloud Run IAM audience only from backend status.url")
    if AUDIENCE_DIFFERENCE_GUARD not in text:
        errors.append("gcp_backend.yml must reject a canonical IAM audience equal to the tagged candidate URL")
    if text.count(CANDIDATE_REQUEST_TARGET) != 1:
        errors.append("gcp_backend.yml must retain the tagged candidate URL as the production probe request target")
    return errors


if __name__ == "__main__":
    raise SystemExit(1 if validate(Path(".")) else 0)
