#!/usr/bin/env bash
# Sync all secret env-var bindings from the backend-secrets Helm chart values
# file into the Cloud Run backend service(s) for a given environment.
#
# Background: api.omi.me / api.omiapi.com route to Cloud Run services that
# have their OWN env-var configuration, separate from the GKE backend-listen
# pods. Adding a new key to backend-secrets/{env}_omi_backend_secrets_values.yaml
# updates the K8s ExternalSecret (via helm), but Cloud Run won't see it until
# someone runs `gcloud run services update --update-secrets …` for each service.
# This script does that automatically from the chart's `externalSecret.secretKeys`
# list, so every chart change reliably propagates.
#
# Usage:
#   sync_cloudrun_secrets_from_chart.sh <env> [<service> …]
#
#   env       one of: dev | prod
#   services  defaults to: backend backend-sync backend-integration
#
# Requires: yq (mikefarah), gcloud authed for the target project.

set -euo pipefail

ENV="${1:-}"
shift || true
SERVICES=("${@:-backend backend-sync backend-integration}")

case "$ENV" in
  dev)
    PROJECT="based-hardware-dev"
    VALUES_FILE="backend/charts/backend-secrets/dev_omi_backend_secrets_values.yaml"
    ;;
  prod)
    PROJECT="based-hardware"
    VALUES_FILE="backend/charts/backend-secrets/prod_omi_backend_secrets_values.yaml"
    ;;
  *)
    echo "usage: $0 <dev|prod> [<service> …]" >&2
    exit 2
    ;;
esac

if ! command -v yq >/dev/null 2>&1; then
  echo "yq (mikefarah) is required: https://github.com/mikefarah/yq" >&2
  exit 2
fi

# Build "K=GCP_KEY:latest,K2=GCP_KEY2:latest,…" from the chart's secretKeys list.
SECRETS_FLAG=$(
  yq -r '.externalSecret.secretKeys[] | "\(.secretKey)=\(.remoteKey):latest"' "$VALUES_FILE" \
    | paste -sd "," -
)

if [ -z "$SECRETS_FLAG" ]; then
  echo "No secretKeys found in $VALUES_FILE" >&2
  exit 1
fi

echo "Project: $PROJECT"
echo "Services: ${SERVICES[*]}"
echo "Secrets to sync ($(echo "$SECRETS_FLAG" | tr ',' '\n' | wc -l | tr -d ' ')): $(echo "$SECRETS_FLAG" | cut -d, -f1-3)…"

for SVC in "${SERVICES[@]}"; do
  echo ""
  echo "▶ $SVC"
  gcloud run services update "$SVC" \
    --project="$PROJECT" \
    --region="us-central1" \
    --update-secrets="$SECRETS_FLAG" \
    --quiet
done
