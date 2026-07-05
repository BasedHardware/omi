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
EXTERNAL_SECRET_WAIT_TIMEOUT_SECONDS="${EXTERNAL_SECRET_WAIT_TIMEOUT_SECONDS:-120}"
EXTERNAL_SECRET_NAME="${EXTERNAL_SECRET_NAME:-}"
TARGET_SECRET_NAME="${TARGET_SECRET_NAME:-}"

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

read_values_field() {
  local field_path="$1"
  python3 - "$VALUES_FILE" "$field_path" <<'PY'
from pathlib import Path
import sys

import yaml

values_path = Path(sys.argv[1])
field_path = sys.argv[2].split('.')
with values_path.open('r', encoding='utf-8') as handle:
    value = yaml.safe_load(handle)
for part in field_path:
    if not isinstance(value, dict):
        value = None
        break
    value = value.get(part)
if value is None:
    value = ''
print(value)
PY
}

if [[ -z "$EXTERNAL_SECRET_NAME" ]]; then
  EXTERNAL_SECRET_NAME="$(read_values_field externalSecret.name)"
fi
if [[ -z "$TARGET_SECRET_NAME" ]]; then
  TARGET_SECRET_NAME="$(read_values_field externalSecret.targetSecretName)"
fi
if [[ -z "$EXTERNAL_SECRET_NAME" ]]; then
  echo "ERROR: externalSecret.name is required in $VALUES_FILE or EXTERNAL_SECRET_NAME" >&2
  exit 2
fi
if [[ -z "$TARGET_SECRET_NAME" ]]; then
  echo "ERROR: externalSecret.targetSecretName is required in $VALUES_FILE or TARGET_SECRET_NAME" >&2
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

verify_target_secret_keys() {
  kubectl -n "$NAMESPACE" get secret "$TARGET_SECRET_NAME" -o json \
    | python3 backend/scripts/verify_k8s_secret_keys.py "$VALUES_FILE"
}

helm template "${HELM_ARGS[@]}" >/dev/null

if [[ "$DRY_RUN" == "true" ]]; then
  echo "backend-secrets render preflight OK for ${RELEASE_NAME} in ${NAMESPACE}"
  exit 0
fi

helm -n "$NAMESPACE" upgrade --install --create-namespace "${HELM_ARGS[@]}"
force_sync_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
kubectl -n "$NAMESPACE" annotate externalsecret \
  "$EXTERNAL_SECRET_NAME" \
  force-sync="${force_sync_at}" --overwrite
if [[ "$WAIT_EXTERNAL_SECRET" == "true" ]]; then
  wait_status=0
  python3 backend/scripts/wait_external_secret_refresh.py \
    --namespace "$NAMESPACE" \
    --name "$EXTERNAL_SECRET_NAME" \
    --min-refresh-time "${force_sync_at}" \
    --timeout-seconds "$EXTERNAL_SECRET_WAIT_TIMEOUT_SECONDS" || wait_status=$?
  if [[ "$wait_status" -eq 0 ]]; then
    verify_target_secret_keys
  elif [[ "$wait_status" -eq 2 ]]; then
    echo "WARNING: ExternalSecret did not report a fresh refresh before timeout; verifying current target secret keys." >&2
    verify_target_secret_keys
  else
    exit "$wait_status"
  fi
fi
