#!/usr/bin/env python3
"""Keep production deploys rollback-first and Cloud Run-only."""

from __future__ import annotations

from pathlib import Path

WORKFLOW = Path(".github/workflows/gcp_backend.yml")
PROD_ALL_REJECTION = 'if [[ "$DEPLOY_ENVIRONMENT" == "prod" && "$DEPLOY_TARGETS" == "all" ]]; then'
DEV_CANDIDATE_GATE = "if: ${{ github.event.inputs.environment == 'development' }}"
PROD_SMOKE = "Smoke promoted production serving API"
SERVING_VERIFY = "Verify serving backend release vector"
ROLLBACK_CONDITION = "steps.smoke-promoted-production-serving-api.outcome == 'failure'"
PROD_FORBIDDEN = (
    "probe-transcription-candidate-from-cloud-run.sh",
    "FIREBASE_PROBE_TOKEN",
    "identity_audience=",
)


def validate(root: Path) -> list[str]:
    path = root / WORKFLOW
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    errors: list[str] = []
    if "default: 'cloud-run-only'" not in text:
        errors.append("gcp_backend.yml must default deploy_targets to cloud-run-only")
    if PROD_ALL_REJECTION not in text:
        errors.append("gcp_backend.yml must reject environment=prod, deploy_targets=all before side effects")
    if text.count(DEV_CANDIDATE_GATE) < 2:
        errors.append("gcp_backend.yml must retain the development tagged-candidate gate")
    if text.count("resolve_cloud_run_tagged_url.py") != 1:
        errors.append("gcp_backend.yml must use the tagged candidate resolver only for development")
    for forbidden in PROD_FORBIDDEN:
        if forbidden in text:
            errors.append(f"gcp_backend.yml must not retain production candidate dependency {forbidden!r}")
    try:
        serving_verify = text.index(SERVING_VERIFY)
        prod_smoke = text.index(PROD_SMOKE)
    except ValueError:
        errors.append("gcp_backend.yml must smoke the promoted production serving API")
    else:
        if prod_smoke <= serving_verify:
            errors.append("production serving smoke must follow exact serving release-vector verification")
    for required in (
        "https://api.omi.me/v2/desktop/beta/candidates/reserve",
        "expected validation response",
        "--candidate-api-url https://api.omi.me",
        "umask 077",
        "firebase-production-serving-token",
        "trap 'rm -f \"$token_file\"' EXIT",
        ROLLBACK_CONDITION,
    ):
        if required not in text:
            errors.append(f"gcp_backend.yml is missing production serving-smoke guard {required!r}")
    smoke_text = text[text.find(PROD_SMOKE) :] if PROD_SMOKE in text else ""
    if "$GITHUB_OUTPUT" in smoke_text and "firebase-production-serving-token" in smoke_text:
        errors.append("production smoke token must not be written to GITHUB_OUTPUT")
    return errors


if __name__ == "__main__":
    raise SystemExit(1 if validate(Path(".")) else 0)
