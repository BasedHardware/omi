#!/usr/bin/env bash
# Sync non-cohort secret env-var bindings from the backend-secrets Helm chart values
# file into the Cloud Run backend service(s) for a given environment.
#
# Background: api.omi.me / api.omiapi.com route to Cloud Run services that
# have their OWN env-var configuration, separate from the GKE backend-listen
# pods. Adding a new key to backend-secrets/{env}_omi_backend_secrets_values.yaml
# updates the K8s ExternalSecret (via helm), but Cloud Run won't see it until
# someone runs `gcloud run services update --update-secrets …` for each service.
# This script does that automatically from the chart's `externalSecret.secretKeys`
# list. Private cohort bindings stay on the normal per-service manifest path.
#
# Usage:
#   sync_cloudrun_secrets_from_chart.sh <env> [--project <gcp-project-id>] [<service> …]
#
#   env       one of: dev | prod
#   services  defaults to: backend backend-sync backend-integration
#
# Requires: Python 3 with PyYAML, gcloud authed for the target project.
# Private cohorts are deliberately excluded: the normal manifest deploy owns their
# per-service scope and atomic literal-to-secret migration.
# Project must be supplied via --project or GCP_PROJECT_ID.

set -euo pipefail

ENV="${1:-}"
shift || true
PROJECT_OVERRIDE=""
SERVICES=()
while [ "$#" -gt 0 ]; do
  case "$1" in
    --project)
      PROJECT_OVERRIDE="${2:-}"
      if [ -z "$PROJECT_OVERRIDE" ]; then
        echo "--project requires a GCP project id" >&2
        exit 2
      fi
      shift 2
      ;;
    *)
      SERVICES+=("$1")
      shift
      ;;
  esac
done
if [ "${#SERVICES[@]}" -eq 0 ]; then
  SERVICES=(backend backend-sync backend-integration)
fi

case "$ENV" in
  dev)
    VALUES_FILE="backend/charts/backend-secrets/dev_omi_backend_secrets_values.yaml"
    ;;
  prod)
    VALUES_FILE="backend/charts/backend-secrets/prod_omi_backend_secrets_values.yaml"
    ;;
  *)
    echo "usage: $0 <dev|prod> [<service> …]" >&2
    exit 2
    ;;
esac

PROJECT="${PROJECT_OVERRIDE:-${GCP_PROJECT_ID:-}}"
if [ -z "$PROJECT" ]; then
  echo "GCP project id required: pass --project <id> or set GCP_PROJECT_ID" >&2
  exit 2
fi

# Keep private selectors out of this legacy all-services bulk path.
SECRETS_FLAG=$(python3 - "$VALUES_FILE" <<'PYCODE'
import sys
import yaml
sys.path.insert(0, 'backend')
from scripts.private_cohort_secrets import PRIVATE_COHORT_ENV_NAMES
with open(sys.argv[1]) as handle:
    keys = yaml.safe_load(handle)['externalSecret']['secretKeys']
print(','.join(f"{row['secretKey']}={row['remoteKey']}:latest" for row in keys
               if row['secretKey'] not in PRIVATE_COHORT_ENV_NAMES and row['remoteKey'] not in PRIVATE_COHORT_ENV_NAMES))
PYCODE
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
