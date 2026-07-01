#!/usr/bin/env bash
set -euo pipefail

ENVIRONMENT="${ENVIRONMENT:-${ENV:-}}"
GCP_PROJECT_ID="${GCP_PROJECT_ID:-}"
GKE_CLUSTER="${GKE_CLUSTER:-}"
REGION="${REGION:-}"
BACKEND_SECRETS_GSA="${BACKEND_SECRETS_GSA:-}"
CHART_DIR="${CHART_DIR:-backend/charts/backend-secrets}"
VALUES_FILE="${VALUES_FILE:-}"
NAMESPACE="${NAMESPACE:-}"
RELEASE_NAME="${RELEASE_NAME:-}"
DRY_RUN="${DRY_RUN:-false}"
WAIT_EXTERNAL_SECRET="${WAIT_EXTERNAL_SECRET:-true}"

if [[ -z "$ENVIRONMENT" ]]; then
  echo "ERROR: ENVIRONMENT or ENV is required" >&2
  exit 2
fi
if [[ -z "$GCP_PROJECT_ID" ]]; then
  echo "ERROR: GCP_PROJECT_ID is required" >&2
  exit 2
fi
if [[ -z "$GKE_CLUSTER" ]]; then
  echo "ERROR: GKE_CLUSTER is required" >&2
  exit 2
fi
if [[ -z "$REGION" ]]; then
  echo "ERROR: REGION is required" >&2
  exit 2
fi

if [[ -z "$VALUES_FILE" ]]; then
  VALUES_FILE="backend/charts/backend-secrets/${ENVIRONMENT}_omi_backend_secrets_values.yaml"
fi
if [[ -z "$NAMESPACE" ]]; then
  NAMESPACE="${ENVIRONMENT}-omi-backend"
fi
if [[ -z "$RELEASE_NAME" ]]; then
  RELEASE_NAME="${ENVIRONMENT}-omi-backend-secrets"
fi
if [[ -z "$BACKEND_SECRETS_GSA" ]]; then
  BACKEND_SECRETS_GSA="${ENVIRONMENT}-omi-backend-eso-gsa@${GCP_PROJECT_ID}.iam.gserviceaccount.com"
fi

if [[ ! -f "$VALUES_FILE" ]]; then
  echo "ERROR: backend-secrets values file not found: $VALUES_FILE" >&2
  exit 2
fi

HELM_ARGS=(
  "$RELEASE_NAME"
  "$CHART_DIR"
  -f "$VALUES_FILE"
  --set "gke.projectID=${GCP_PROJECT_ID}"
  --set "gke.clusterLocation=${REGION}"
  --set "gke.clusterName=${GKE_CLUSTER}"
  --set "gsa.name=${BACKEND_SECRETS_GSA}"
)

helm template "${HELM_ARGS[@]}" >/dev/null

if [[ "$DRY_RUN" == "true" ]]; then
  echo "backend-secrets render preflight OK for ${RELEASE_NAME} in ${NAMESPACE}"
  exit 0
fi

helm -n "$NAMESPACE" upgrade --install "${HELM_ARGS[@]}"
force_sync_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
kubectl -n "$NAMESPACE" annotate externalsecret \
  "${ENVIRONMENT}-omi-backend-external-secret" \
  force-sync="${force_sync_at}" --overwrite
if [[ "$WAIT_EXTERNAL_SECRET" == "true" ]]; then
  python3 backend/scripts/wait_external_secret_refresh.py \
    --namespace "$NAMESPACE" \
    --name "${ENVIRONMENT}-omi-backend-external-secret" \
    --min-refresh-time "${force_sync_at}" \
    --timeout-seconds 120
  kubectl -n "$NAMESPACE" get secret "${ENVIRONMENT}-omi-backend-secrets" -o json \
    | python3 backend/scripts/verify_k8s_secret_keys.py "$VALUES_FILE"
fi
