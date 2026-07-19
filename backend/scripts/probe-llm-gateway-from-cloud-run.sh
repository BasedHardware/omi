#!/usr/bin/env bash
# Launch a short-lived Cloud Run Job in the same VPC path as backend serving.
# The job performs the authenticated /ready and minimal auto-lane request used
# by the gateway smoke test, then is deleted even when the probe fails.
set -euo pipefail

PROJECT=""
REGION=""
IMAGE=""
GATEWAY_URL=""
NETWORK=""
SUBNET=""
VPC_EGRESS=""
TOKEN_SECRET="OMI_LLM_GATEWAY_SERVICE_TOKEN"
NAME_SUFFIX=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --project) PROJECT="$2"; shift 2 ;;
    --region) REGION="$2"; shift 2 ;;
    --image) IMAGE="$2"; shift 2 ;;
    --gateway-url) GATEWAY_URL="$2"; shift 2 ;;
    --network) NETWORK="$2"; shift 2 ;;
    --subnet) SUBNET="$2"; shift 2 ;;
    --vpc-egress) VPC_EGRESS="$2"; shift 2 ;;
    --token-secret) TOKEN_SECRET="$2"; shift 2 ;;
    --name-suffix) NAME_SUFFIX="$2"; shift 2 ;;
    *) echo "ERROR: unknown argument: $1" >&2; exit 2 ;;
  esac
done

for required in PROJECT REGION IMAGE GATEWAY_URL NETWORK SUBNET VPC_EGRESS NAME_SUFFIX; do
  if [[ -z "${!required}" ]]; then
    echo "ERROR: --${required,,} is required" >&2
    exit 2
  fi
done
if [[ ! "$NAME_SUFFIX" =~ ^[a-z0-9-]+$ ]]; then
  echo "ERROR: --name-suffix must contain only lowercase letters, digits, and hyphens" >&2
  exit 2
fi

JOB_NAME="llm-gateway-vpc-probe-${NAME_SUFFIX}"
cleanup() {
  gcloud run jobs delete "$JOB_NAME" --project="$PROJECT" --region="$REGION" --quiet >/dev/null 2>&1 || true
}
trap cleanup EXIT

gcloud run jobs deploy "$JOB_NAME" \
  --project="$PROJECT" \
  --region="$REGION" \
  --image="$IMAGE" \
  --network="$NETWORK" \
  --subnet="$SUBNET" \
  --vpc-egress="$VPC_EGRESS" \
  --set-env-vars="SMOKE_URL=$GATEWAY_URL" \
  --set-secrets="OMI_LLM_GATEWAY_SERVICE_TOKEN=${TOKEN_SECRET}:latest" \
  --command=python \
  --args=scripts/smoke-llm-gateway.py,--url,"$GATEWAY_URL" \
  --task-timeout=90s \
  --max-retries=0 \
  --quiet

gcloud run jobs execute "$JOB_NAME" \
  --project="$PROJECT" \
  --region="$REGION" \
  --wait \
  --quiet
