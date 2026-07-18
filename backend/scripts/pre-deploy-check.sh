#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

export CLOUD_RUN_VPC_NETWORK="${CLOUD_RUN_VPC_NETWORK:-offline-check-network}"
export CLOUD_RUN_VPC_SUBNET="${CLOUD_RUN_VPC_SUBNET:-offline-check-subnet}"

usage() {
  cat <<'EOF'
Usage: backend/scripts/pre-deploy-check.sh [--live ENV PROJECT]

Hermetic checks (default):
  - validate runtime env manifest vs workflows and rendered Cloud Run shape (dev + prod)
  - unit tests for deploy safety scripts

Live checks (--live, requires gcloud auth):
  - validate against live Cloud Run service env
  - Secret Manager + traffic preflight for the target environment
EOF
}

run_hermetic() {
  # Local dev only: CI runners use system python3 (see lint.yml) and do not pin .python-version.
  if [[ -f .python-version && -z "${CI:-}" ]]; then
    expected="$(tr -d '[:space:]' < .python-version)"
    actual="$(python3 --version 2>&1 | awk '{print $2}')"
    if [[ "$actual" != "$expected" ]]; then
      echo "ERROR: Python version mismatch: expected $expected from .python-version, got $actual" >&2
      exit 1
    fi
  fi
  python3 -m pip install -q pyyaml pytest
  python3 scripts/validate-backend-runtime-env.py --env dev --check-workflows --check-rendered-cloud-run
  python3 scripts/validate-backend-runtime-env.py --env prod --check-workflows --check-rendered-cloud-run
  python3 scripts/check_mcp_oauth_deploy_contract.py
  python3 -m pytest \
    tests/unit/test_backend_runtime_env_validator.py \
    tests/unit/test_repair_cloud_run_traffic.py \
    tests/unit/test_cloud_run_traffic_snapshot.py \
    tests/unit/test_preflight_cloud_run_deploy.py \
    tests/unit/test_deploy_status_report.py \
    tests/unit/test_verify_backend_release_vector.py \
    tests/unit/test_mcp_oauth_deploy_contract.py -q
}

run_live() {
  local env="$1"
  local project="$2"
  python3 scripts/validate-backend-runtime-env.py --env "$env" --check-workflows --check-live-cloud-run
  python3 scripts/preflight-cloud-run-deploy.py \
    --env "$env" \
    --project "$project" \
    --region us-central1 \
    --check-secrets \
    --check-traffic
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

if [[ "${1:-}" == "--live" ]]; then
  if [[ $# -ne 3 ]]; then
    echo "ERROR: --live requires ENV and GCP_PROJECT_ID arguments" >&2
    usage
    exit 2
  fi
  run_hermetic
  run_live "$2" "$3"
else
  if [[ $# -ne 0 ]]; then
    echo "ERROR: unknown arguments: $*" >&2
    usage
    exit 2
  fi
  run_hermetic
fi

echo "pre-deploy checks passed"
