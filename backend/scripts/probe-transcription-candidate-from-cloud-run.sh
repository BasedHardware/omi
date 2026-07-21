#!/usr/bin/env bash
# Launch the smallest VPC-connected Cloud Run Job that can reach an internal
# tagged backend candidate. The job gets only run.invoker on that one service;
# all temporary IAM and job state is removed on every exit path.
set -euo pipefail

PROJECT=""
REGION=""
IMAGE=""
CANDIDATE_URL=""
NETWORK=""
SUBNET=""
FIREBASE_TOKEN_FILE=""
NAME_SUFFIX=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --project) PROJECT="$2"; shift 2 ;;
    --region) REGION="$2"; shift 2 ;;
    --image) IMAGE="$2"; shift 2 ;;
    --candidate-url) CANDIDATE_URL="$2"; shift 2 ;;
    --network) NETWORK="$2"; shift 2 ;;
    --subnet) SUBNET="$2"; shift 2 ;;
    --firebase-token-file) FIREBASE_TOKEN_FILE="$2"; shift 2 ;;
    --name-suffix) NAME_SUFFIX="$2"; shift 2 ;;
    *) echo "ERROR: unknown argument: $1" >&2; exit 2 ;;
  esac
done

for required in PROJECT REGION IMAGE CANDIDATE_URL NETWORK SUBNET FIREBASE_TOKEN_FILE NAME_SUFFIX; do
  [[ -n "${!required}" ]] || { echo "ERROR: --${required,,} is required" >&2; exit 2; }
done
[[ "$NAME_SUFFIX" =~ ^[a-z0-9-]+$ ]] || { echo 'ERROR: --name-suffix must contain lowercase letters, digits, and hyphens' >&2; exit 2; }
[[ -f "$FIREBASE_TOKEN_FILE" ]] || { echo 'ERROR: Firebase token file is missing' >&2; exit 2; }

JOB_NAME="backend-candidate-vpc-probe-${NAME_SUFFIX}"
SERVICE_ACCOUNT_NAME="backend-candidate-probe-${NAME_SUFFIX}"
SERVICE_ACCOUNT="${SERVICE_ACCOUNT_NAME}@${PROJECT}.iam.gserviceaccount.com"
FIREBASE_TOKEN="$(<"$FIREBASE_TOKEN_FILE")"
[[ -n "$FIREBASE_TOKEN" ]] || { echo 'ERROR: Firebase token is empty' >&2; exit 2; }

cleanup() {
  FIREBASE_TOKEN=""
  gcloud run jobs delete "$JOB_NAME" --project="$PROJECT" --region="$REGION" --quiet >/dev/null 2>&1 || true
  gcloud run services remove-iam-policy-binding backend --project="$PROJECT" --region="$REGION" \
    --member="serviceAccount:${SERVICE_ACCOUNT}" --role=roles/run.invoker --quiet >/dev/null 2>&1 || true
  gcloud iam service-accounts delete "$SERVICE_ACCOUNT" --project="$PROJECT" --quiet >/dev/null 2>&1 || true
}
trap cleanup EXIT

gcloud iam service-accounts create "$SERVICE_ACCOUNT_NAME" --project="$PROJECT" \
  --display-name="Ephemeral backend candidate probe ${NAME_SUFFIX}" --quiet
gcloud run services add-iam-policy-binding backend --project="$PROJECT" --region="$REGION" \
  --member="serviceAccount:${SERVICE_ACCOUNT}" --role=roles/run.invoker --quiet

gcloud run jobs deploy "$JOB_NAME" --project="$PROJECT" --region="$REGION" --image="$IMAGE" \
  --service-account="$SERVICE_ACCOUNT" --network="$NETWORK" --subnet="$SUBNET" --vpc-egress=private-ranges-only \
  --set-env-vars="CANDIDATE_API_URL=${CANDIDATE_URL},FIREBASE_PROBE_TOKEN=${FIREBASE_TOKEN}" \
  --command=python --args=scripts/run_vpc_transcription_candidate_probe.py --task-timeout=120s --max-retries=0 --quiet
FIREBASE_TOKEN=""
gcloud run jobs execute "$JOB_NAME" --project="$PROJECT" --region="$REGION" --wait --quiet
